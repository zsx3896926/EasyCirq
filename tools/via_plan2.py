"""Plan off-row flag moves (L-shaped stub) with exact flag attribution.

Round 7 learned two things the hard way, and both are baked in here:

1. A flag glyph's text box does not reveal which pin it belongs to. `GND` glyphs are
   rotated text (10x20) and the left-edge heuristic used for horizontal net labels
   attributes them to the WRONG pin — it produced "GND at D3:1" for a pin whose net
   is +3V3_SW, i.e. exactly the kind of attribution error that caused the 18:49
   short. Ground flags ARE enumerable as `componentType=netflag` with a real
   `primitiveId` and anchor, so they are matched by anchor, never by text.
2. Lengthening a stub cannot work on this sheet (one-row layout); moving the flag
   perpendicular to the run can. So every candidate here is `pin -> anchor -> turn`.

Predicted geometry is checked against the four obstacles from the incident: text
boxes, part bodies, other pins / wire endpooints / collinear spans, other flags.
"""

from __future__ import annotations

import itertools
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import designator_move_plan as geom   # noqa: E402
import stub_lengthen_plan as lengthen  # noqa: E402

STEP = 5.0
MAX_TURN = 40.0
MIN_RATIO = 0.20
FLAG_MATCH = 30.0


def load(path):
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


def svg_box(b):
    return [float(b["minX"]), -float(b["maxY"]), float(b["maxX"]), -float(b["minY"])]


def build(live, wires_dump):
    comps = live["result"]["components"]
    bodies, flags, pins = {}, [], {}
    for comp in comps:
        kind = comp.get("componentType")
        if kind == "part" and comp.get("designator"):
            bodies[comp["designator"]] = svg_box(comp["bbox"])
            for pin in comp.get("pins") or []:
                pins[(comp["designator"], str(pin.get("pinNumber")))] = {
                    "x": float(pin["x"]), "y": float(pin["y"]), "net": pin.get("net") or "",
                }
        elif kind == "netflag":
            flags.append({"id": comp["primitiveId"], "net": comp.get("net"),
                          "x": float(comp["x"]), "y": float(comp["y"])})
    wires = lengthen.wire_points(wires_dump)
    return bodies, flags, pins, wires


def flag_rows(flags, rows, wires, pins_svg):
    """Attach each ground flag to its text row, its wire and its pin — by anchor."""
    out = []
    for flag in flags:
        anchor = (flag["x"], -flag["y"])
        row = None
        best = None
        for r in rows:
            if r["text"] != flag["net"]:
                continue
            cx = (r["bbox"][0] + r["bbox"][2]) / 2.0
            cy = (r["bbox"][1] + r["bbox"][3]) / 2.0
            d = ((cx - anchor[0]) ** 2 + (cy - anchor[1]) ** 2) ** 0.5
            if best is None or d < best:
                best, row = d, r
        if row is None or best > FLAG_MATCH:
            continue
        wire = pin = None
        for w in wires:
            if any(abs(p[0] - anchor[0]) < 1.5 and abs(p[1] - anchor[1]) < 1.5
                   for p in (w["pts"][0], w["pts"][-1])):
                far = w["pts"][-1] if (abs(w["pts"][0][0] - anchor[0]) < 1.5
                                       and abs(w["pts"][0][1] - anchor[1]) < 1.5) else w["pts"][0]
                for key, pos in pins_svg.items():
                    if abs(pos[0] - far[0]) < 1.0 and abs(pos[1] - far[1]) < 1.0:
                        wire, pin = w, key
                        break
                if wire:
                    break
        if wire is None:
            continue
        out.append({"flag": flag, "row": row, "wire": wire, "pin": pin, "anchor": anchor})
    return out


def label_row(rows, wires, pins_svg):
    """Attach each horizontal net-label row to its wire and pin (left-edge anchor)."""
    out = []
    for r in rows:
        if r["role"] != "net_label":
            continue
        box = r["bbox"]
        near = ((box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0)
        cands = []
        for w in wires:
            for end in (w["pts"][0], w["pts"][-1]):
                dd = ((near[0] - end[0]) ** 2 + (near[1] - end[1]) ** 2) ** 0.5
                edge = abs(end[0] - box[0]) <= 4.0 and box[1] - 4.0 <= end[1] <= box[3] + 4.0
                cands.append((0 if edge else 1, dd, w, end))
        cands.sort(key=lambda t: (t[0], t[1]))
        for _, _, w, end in cands[:12]:
            far = w["pts"][-1] if end == w["pts"][0] else w["pts"][0]
            for key, pos in pins_svg.items():
                if abs(pos[0] - far[0]) < 1.0 and abs(pos[1] - far[1]) < 1.0:
                    out.append({"row": r, "wire": w, "pin": key, "anchor": end})
                    break
            if out and out[-1]["row"] is r:
                break
    return out


def try_turn(entry, rows, bodies, wires, pins_svg, flags, steps=STEP, maxturn=MAX_TURN):
    anchor = entry["anchor"]
    box = entry["row"]["bbox"]
    own = entry["wire"]["id"]
    for turn in [steps * k for k in range(1, int(maxturn / steps) + 1)]:
        for sign in (-1.0, 1.0):
            new_anchor = (anchor[0], anchor[1] + sign * turn)
            shift = (new_anchor[0] - anchor[0], new_anchor[1] - anchor[1])
            cand = geom.moved(box, shift[0], shift[1])
            text_hit = [r["text"] for r in rows if r is not entry["row"]
                        and geom.cover(cand, r["bbox"]) >= MIN_RATIO]
            body_hit = [k for k, b in bodies.items() if geom.cover(cand, b) > 0.0]
            if text_hit or body_hit:
                continue
            why = lengthen.stub_conflict(anchor, new_anchor, wires, own, pins_svg,
                                         [f for f in flags if f["id"] != entry["flag"]["id"]]
                                         if "flag" in entry else flags)
            if why:
                continue
            return {"turn": turn * sign, "new_anchor": new_anchor,
                    "predicted_box": [round(v, 1) for v in cand]}
    return None


def main():
    audit = load(sys.argv[1])
    live = load(sys.argv[2])
    wires_dump = load(sys.argv[3])
    rows = audit["rows"]
    bodies, flags, pins, wires = build(live, wires_dump)
    pins_svg = {k: (v["x"], -v["y"]) for k, v in pins.items()}
    flag_entries = flag_rows(flags, rows, wires, pins_svg)
    label_entries = label_row(rows, wires, pins_svg)

    collisions = []
    for a, b in itertools.combinations(range(len(rows)), 2):
        ra, rb = rows[a], rows[b]
        c = geom.cover(ra["bbox"], rb["bbox"])
        if c >= MIN_RATIO:
            collisions.append((c, ra, rb))

    def key_of(row):
        return (row["text"], tuple(row["bbox"]))

    plan, unsolved, used = [], [], set()
    for cover, ra, rb in sorted(collisions, key=lambda t: -t[0]):
        solved = False
        for entry, kind in ([(e, "flag") for e in flag_entries]
                            + [(e, "label") for e in label_entries]):
            if key_of(entry["row"]) not in (key_of(ra), key_of(rb)):
                continue
            ident = ("flag", entry["flag"]["id"]) if kind == "flag" else ("label", entry["pin"])
            if ident in used:
                solved = True       # already planned for this stub
                break
            res = try_turn(entry, rows, bodies, wires, pins_svg, flags)
            if not res:
                continue
            used.add(ident)
            plan.append({
                "kind": kind, "label": entry["row"]["text"], "pin": "%s:%s" % entry["pin"],
                "net": (entry["flag"]["net"] if kind == "flag" else pins[entry["pin"]]["net"]),
                "anchor_schematic": [entry["anchor"][0], -entry["anchor"][1]],
                "via_schematic": [entry["anchor"][0], -entry["anchor"][1]],
                "new_anchor_schematic": [res["new_anchor"][0], -res["new_anchor"][1]],
                "turn": res["turn"], "predicted_box": res["predicted_box"],
                "run": (abs(entry["anchor"][0] - pins_svg[entry["pin"]][0])
                        + abs(entry["anchor"][1] - pins_svg[entry["pin"]][1])),
                "flag_id": entry["flag"]["id"] if kind == "flag" else None,
                "wire_id": entry["wire"]["id"],
            })
            solved = True
            break
        if not solved:
            unsolved.append({"a": ra["text"], "b": rb["text"], "cover": round(cover, 2)})

    out = {"schema": "easycirq-via-plan/v2", "collisions": len(collisions),
           "planned_moves": len(plan), "unsolved": unsolved, "plan": plan}
    print(json.dumps({"collisions": len(collisions), "planned_moves": len(plan),
                      "unsolved": len(unsolved)}, ensure_ascii=False))
    for item in plan:
        print("  %-8s %-12s %-8s run=%.0f turn=%+.0f net=%s"
              % (item["kind"], item["label"], item["pin"], item["run"], item["turn"], item["net"]))
    for item in unsolved:
        print("  UNSOLVED %s x %s (%.2f)" % (item["a"], item["b"], item["cover"]))
    if len(sys.argv) > 4:
        pathlib.Path(sys.argv[4]).write_text(json.dumps(out, ensure_ascii=False, indent=1),
                                             encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
