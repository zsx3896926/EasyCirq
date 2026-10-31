"""Plan L-shaped stub re-routes (pin -> original anchor -> off-row flag).

Why: round 7 proved that *lengthening* a stub cannot fix anything on this sheet —
the 43 parts sit in one row, so every longer stub runs into the next part's pin
(`stub-lengthen-plan3.json`: 1 of 22 label boxes solvable). The remaining lever is
to move the flag OFF the label band instead of further along it: keep the existing
horizontal run, then turn perpendicular for 10–40 units so the flag glyph lands in
the gap between rows.

Everything here is offline prediction on measured artifacts:

* text boxes      -> `sch export-image` SVG measured by svg_text_bbox.py
* pins            -> `schematic.components.list` includePins
* wires           -> `eda.sch_PrimitiveWire.getAll()` lines
* flags           -> `schematic.components.list` componentType=netflag

A candidate is only emitted when the predicted label box clears every other text
box, every part body, and the whole L-path clears pins, wire endpoints, collinear
overlaps and existing flags — the four checks that the 18:49 incident taught.
"""

from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import designator_move_plan as geom   # noqa: E402
import stub_lengthen_plan as lengthen  # noqa: E402

STEP = 5.0
MAX_TURN = 40.0
MIN_RATIO = 0.20


def load(path):
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


def mirror(box):
    return [box[0], -box[3], box[2], -box[1]]


def resolve_anchor(box, wires, pins_svg):
    """Label box -> (anchor, pin, wire id), anchor on the box's left edge."""
    near = ((box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0)
    cands = []
    for wire in wires:
        for end in (wire["pts"][0], wire["pts"][-1]):
            dd = ((near[0] - end[0]) ** 2 + (near[1] - end[1]) ** 2) ** 0.5
            edge = abs(end[0] - box[0]) <= 4.0 and box[1] - 4.0 <= end[1] <= box[3] + 4.0
            cands.append((0 if edge else 1, dd, wire, end))
    cands.sort(key=lambda t: (t[0], t[1]))
    for _, _, wire, end in cands[:12]:
        far = wire["pts"][-1] if end == wire["pts"][0] else wire["pts"][0]
        for key, pos in pins_svg.items():
            if abs(pos[0] - far[0]) < 1.0 and abs(pos[1] - far[1]) < 1.0:
                return end, key, wire
    return None, None, None


def path_reasons(pin, anchor, new_anchor, wires, own_wire_id, pins_svg, flags):
    """The L-path pin -> anchor -> new_anchor must be electrically and visually free."""
    reasons = []
    if abs(pin[1] - anchor[1]) > 0.5 and abs(pin[0] - anchor[0]) > 0.5:
        reasons.append("original stub is not axis aligned")
        return reasons
    # segment 1: pin -> anchor (unchanged geometry, keep the existing verdict)
    # segment 2: anchor -> new_anchor (the new turn)
    why = lengthen.stub_conflict(anchor, new_anchor, wires, own_wire_id, pins_svg, flags)
    if why:
        reasons.append("turn: " + why)
    # the corner itself must not sit on another pin or flag
    for key, pos in pins_svg.items():
        if abs(pos[0] - anchor[0]) < 1.0 and abs(pos[1] - anchor[1]) < 1.0 and key != pin:
            reasons.append("corner sits on pin %s:%s" % key)
    for flag in flags:
        fx, fy = flag["x"], -flag["y"]
        if abs(fx - new_anchor[0]) < 1.5 and abs(fy - new_anchor[1]) < 1.5:
            reasons.append("new anchor lands on %s flag" % flag.get("net"))
    return reasons


def main():
    audit = load(sys.argv[1])
    bodies_raw = load(sys.argv[2])
    wires = lengthen.wire_points(load(sys.argv[3]))
    pins = lengthen.pin_map(load(sys.argv[4]))
    rows = audit["rows"]

    pins_svg = {k: (v["x"], -v["y"]) for k, v in pins.items()}
    bodies = {}
    flags = []
    for comp in bodies_raw["result"]["components"]:
        if comp.get("componentType") == "part" and comp.get("designator"):
            bodies[comp["designator"]] = mirror(comp["bbox"].values() and
                                                [comp["bbox"]["minX"], comp["bbox"]["minY"],
                                                 comp["bbox"]["maxX"], comp["bbox"]["maxY"]])
        elif comp.get("componentType") == "netflag":
            flags.append(comp)

    # colliding label boxes, with what they hit
    hits = {}
    import itertools
    for a, b in itertools.combinations(range(len(rows)), 2):
        ra, rb = rows[a], rows[b]
        c = geom.cover(ra["bbox"], rb["bbox"])
        if c < MIN_RATIO:
            continue
        for lab, other in ((ra, rb), (rb, ra)):
            if lab["role"] not in ("net_label", "value", "pin_name"):
                continue
            hits.setdefault((lab["text"], tuple(lab["bbox"])), []).append(
                (c, other["text"], other["role"], tuple(other["bbox"])))
    # prefer net_label boxes: they own a stub we can re-route
    targets = [k for k in hits if k[0] in {r["text"] for r in rows if r["role"] == "net_label"}]

    plan, unsolved = [], []
    for text, box in sorted(targets, key=lambda k: k[0]):
        box = list(box)
        anchor, pin, wire = resolve_anchor(box, wires, pins_svg)
        hitlist = hits[(text, tuple(box))]
        if anchor is None:
            unsolved.append({"label": text, "why": "no anchor/pin", "hits": len(hitlist)})
            continue
        net = pins[pin]["net"]
        kind = "ground" if net == "GND" else "net_label"
        run = abs(anchor[0] - pins_svg[pin][0]) + abs(anchor[1] - pins_svg[pin][1])
        best = None
        for turn in [STEP * k for k in range(1, int(MAX_TURN / STEP) + 1)]:
            for sign in (-1.0, 1.0):
                new_anchor = (anchor[0], anchor[1] + sign * turn)
                shift = (new_anchor[0] - anchor[0], new_anchor[1] - anchor[1])
                cand = geom.moved(box, shift[0], shift[1])
                text_hit = [r["text"] for r in rows
                            if (r["text"], tuple(r["bbox"])) != (text, tuple(box))
                            and geom.cover(cand, r["bbox"]) >= MIN_RATIO]
                body_hit = [k for k, b in bodies.items() if geom.cover(cand, b) > 0.0]
                if text_hit or body_hit:
                    continue
                reasons = path_reasons(pins_svg[pin], anchor, new_anchor, wires,
                                       wire["id"], pins_svg, flags)
                if reasons:
                    continue
                best = (new_anchor, shift, cand, turn, sign)
                break
            if best:
                break
        if not best:
            unsolved.append({"label": text, "why": "no clean turn up to %.0f" % MAX_TURN,
                             "pin": "%s:%s" % pin, "hits": len(hitlist)})
            continue
        new_anchor, shift, cand, turn, sign = best
        plan.append({
            "label": text, "pin": "%s:%s" % pin, "net": net, "kind": kind,
            "run": run, "turn": turn * (1 if sign > 0 else -1),
            "anchor_svg": [round(v, 1) for v in anchor],
            "new_anchor_svg": [round(v, 1) for v in new_anchor],
            "planned_via_schematic": [anchor[0], -anchor[1]],
            "planned_anchor_schematic": [new_anchor[0], -new_anchor[1]],
            "predicted_box": [round(v, 1) for v in cand],
            "clears": [{"text": t, "role": r, "cover": round(c, 2)} for c, t, r, _ in hitlist],
            "wire_id": wire["id"],
        })

    out = {"schema": "easycirq-via-plan/v1", "targets": len(targets),
           "planned": len(plan), "unsolved": unsolved, "plan": plan}
    print(json.dumps({"targets": len(targets), "planned": len(plan),
                      "unsolved": len(unsolved)}, ensure_ascii=False))
    for item in plan:
        print("  %-12s %-8s run=%.0f turn=%+.0f  clears %s"
              % (item["label"], item["pin"], item["run"], item["turn"],
                 ",".join(c["text"] for c in item["clears"])))
    for item in unsolved:
        print("  UNSOLVED %-12s %s (%s, hits=%d)" % (item["label"], item["why"],
                                                     item.get("pin", "-"), item["hits"]))
    if len(sys.argv) > 5:
        pathlib.Path(sys.argv[5]).write_text(json.dumps(out, ensure_ascii=False, indent=1),
                                             encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
