"""Plan stub lengthenings that move a net label off a pin number.

The 13 remaining `net_label x pin_number` collisions all come from SIX label boxes:
a net_label flag renders its text *to the right of its anchor* (the connector says
so: ``connect_pin net_label creates only its stub and native attribute without
rotation calibration``). So a label on a leftward stub runs back over its own
symbol and covers the pin numbers printed inside it. Rotation cannot be calibrated
for this kind, so the only lever is the stub LENGTH: push the anchor far enough out
that the text box clears the part.

This module works entirely on measured artifacts and emits a per-pin plan:

    pin, net, direction, current_offset, new_offset, predicted_box, rule

Nothing is mutated here.
"""

from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import designator_move_plan as geom  # noqa: E402

MARGIN = 2.0
STRIDE = 5.0
MAX_EXTRA = 90.0


def load(path):
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


def pin_map(live):
    out = {}
    for comp in live.get("result", {}).get("components", []):
        ref = comp.get("designator")
        if comp.get("componentType") != "part" or not ref:
            continue
        for pin in comp.get("pins") or []:
            out[(ref, str(pin.get("pinNumber")))] = {
                "x": float(pin["x"]), "y": float(pin["y"]),
                "rotation": pin.get("rotation"), "net": pin.get("net") or "",
            }
    return out


def wire_points(dump):
    out = []
    for wire in dump.get("result", {}).get("value", {}).get("wires", []):
        line = wire.get("line")
        if not isinstance(line, list) or len(line) < 4:
            continue
        # schematic space is Y-up, every text box here is measured on the SVG
        # export (Y down): mirror once, here, or nothing ever matches.
        pts = [(float(line[i]), -float(line[i + 1])) for i in range(0, len(line) - 1, 2)]
        out.append({"id": wire.get("id"), "pts": pts})
    return out


def stub_conflict(pin, anchor, wires, own_wire_id, pins_svg, flags=()):
    """Why a lengthened stub must be checked as geometry, not only as a label move.

    Incident 2026-10-30 18:49: three lengthenings were each "text-clean" yet two of
    them ran collinear with the neighbouring part's stub (D3:1's 50-long stub met
    D2:2's at 760; R6:1's met R5:2's at 995) and merged into one wire — a real
    short — while R7:1's 50-long stub ran straight through R3:2's pin and swallowed
    that pin's stub and flag. Returns a human reason, or None when clear.
    """
    x0, y0 = pin
    x1, y1 = anchor
    horizontal = abs(y0 - y1) < 0.5
    lo, hi = (min(x0, x1), max(x0, x1)) if horizontal else (min(y0, y1), max(y0, y1))
    fixed = y0 if horizontal else x0

    # 1) no other pin may sit on the new stub
    for key, pos in pins_svg.items():
        px, py = pos
        if abs(px - x0) < 0.5 and abs(py - y0) < 0.5:
            continue
        if horizontal:
            if abs(py - fixed) < 1.5 and lo - 1.0 <= px <= hi + 1.0:
                return "runs through pin %s:%s at (%.0f,%.0f)" % (key[0], key[1], px, py)
        else:
            if abs(px - fixed) < 1.5 and lo - 1.0 <= py <= hi + 1.0:
                return "runs through pin %s:%s at (%.0f,%.0f)" % (key[0], key[1], px, py)

    # 2) no collinear overlap with an existing stub (that is what makes a bridge);
    #    a perpendicular crossing draws a crossing, not a junction, and is allowed.
    #    Touching an endpoint counts as a conflict too: R6:1 lengthened to 35 lands
    #    exactly on R5:2's flag at (995,500), which *is* the bridge even though the
    #    two x-ranges only share a single point.
    for wire in wires:
        if wire["id"] == own_wire_id:
            continue
        pts = wire["pts"]
        for point in (pts[0], pts[-1]):
            if abs(point[0] - x1) < 1.5 and abs(point[1] - y1) < 1.5:
                return "lands on wire %s endpoint (%.0f,%.0f)" % (wire["id"], point[0], point[1])
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            if horizontal and abs(ay - fixed) < 1.5 and abs(by - fixed) < 1.5:
                a, b = min(ax, bx), max(ax, bx)
                if b >= lo and a <= hi:
                    return "collinear with wire %s (%.0f..%.0f at y=%.0f)" % (wire["id"], a, b, fixed)
            if not horizontal and abs(ax - fixed) < 1.5 and abs(bx - fixed) < 1.5:
                a, b = min(ay, by), max(ay, by)
                if b >= lo and a <= hi:
                    return "collinear with wire %s (%.0f..%.0f at x=%.0f)" % (wire["id"], a, b, fixed)

    # 3) the new anchor must not land on an existing flag glyph: R8:1 lengthened to
    #    35 lands on the GND flag at (405,240), which bridge-check would see as a
    #    merge and the eye as two markers on one point.
    for flag in flags:
        if abs(flag["x"] - x1) < 1.5 and abs(-flag["y"] - y1) < 1.5:
            return "lands on %s flag %s at (%.0f,%.0f)" % (flag.get("net"), flag.get("primitiveId"), flag["x"], flag["y"])
    return None


def pair_up(rows):
    """[(cover, label_row, other_row)] for every collision that involves a net label.

    Round 6 first targeted only `pin_number` partners, which fixed 12 of 13. The
    same machinery works for the label-against-label and label-against-value
    collisions, so the filter is "any role", and the search must clear *all* of a
    label's collisions, not just the one it was found by.
    """
    import itertools
    out = []
    for a, b in itertools.combinations(range(len(rows)), 2):
        ra, rb = rows[a], rows[b]
        if "net_label" not in (ra["role"], rb["role"]):
            continue
        c = geom.cover(ra["bbox"], rb["bbox"])
        if c < 0.2:
            continue
        lab, other = (ra, rb) if ra["role"] == "net_label" else (rb, ra)
        if lab["role"] != "net_label":
            continue
        out.append((c, lab, other))
    out.sort(key=lambda t: -t[0])
    return out


def main():
    audit = load(sys.argv[1])
    bodies = load(sys.argv[2])
    wires = wire_points(load(sys.argv[3]))
    pins = pin_map(load(sys.argv[4]))
    pins_svg = {k: (v["x"], -v["y"]) for k, v in pins.items()}
    flags = [c for c in bodies["result"]["components"] if c.get("componentType") == "netflag"]
    rows = audit["rows"]

    bodies_svg = {c["designator"]: [c["bbox"]["minX"], -c["bbox"]["maxY"],
                                    c["bbox"]["maxX"], -c["bbox"]["minY"]]
                  for c in bodies["result"]["components"]
                  if c.get("componentType") == "part" and c.get("designator")}
    segs = geom.segments(load(sys.argv[3]))

    # unique label boxes that cover a pin number
    targets, seen = [], set()
    for cover, lab, num in pair_up(rows):
        key = (lab["text"], tuple(lab["bbox"]))
        if key in seen:
            continue
        seen.add(key)
        targets.append((lab, []))

    for lab, hits in targets:
        for cover, l2, num in pair_up(rows):
            if l2 is lab:
                hits.append((cover, num["text"], num["bbox"]))

    plan, unsolved = [], []
    for lab, hits in targets:
        box = lab["bbox"]
        near = ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)
        # A label box does not say which end of its wire is the anchor. A
        # net_label renders its text to the RIGHT of its anchor, so the anchor is
        # the wire endpoint sitting on the box's LEFT edge. Matching "nearest pin
        # at the other end" instead picked the wrong wire twice (TP_U1_9 was
        # attributed to TP1:1 when it belongs to J2:8), so the edge test comes
        # first and the pin test only breaks ties.
        anchor = pin = None
        candidates = []
        for wire in wires:
            for end in (wire["pts"][0], wire["pts"][-1]):
                dd = ((near[0] - end[0]) ** 2 + (near[1] - end[1]) ** 2) ** 0.5
                edge = abs(end[0] - box[0]) <= 4.0 and box[1] - 4.0 <= end[1] <= box[3] + 4.0
                candidates.append((0 if edge else 1, dd, wire, end))
        candidates.sort(key=lambda t: (t[0], t[1]))
        for _, dd, wire, end in candidates[:12]:
            far = wire["pts"][-1] if end == wire["pts"][0] else wire["pts"][0]
            found = None
            for key, pos in pins.items():
                if abs(pos["x"] - far[0]) < 1.0 and abs(pos["y"] + far[1]) < 1.0:
                    found = key
                    break
            if found:
                anchor, pin = end, found
                break
        if pin is None:
            unsolved.append((lab["text"], box, "no nearby wire whose far end is a pin"))
            continue
        pts = None
        own_wire_id = None
        for wire in wires:
            if anchor in (wire["pts"][0], wire["pts"][-1]):
                pts = wire["pts"]
                own_wire_id = wire["id"]
                break
        far = pts[-1] if anchor == pts[0] else pts[0]
        dx, dy = anchor[0] - far[0], anchor[1] - far[1]
        length = max(abs(dx), abs(dy))
        ux, uy = (dx / length if dx else 0.0), (dy / length if dy else 0.0)
        direction = ("right" if ux > 0 else "left" if ux < 0 else
                     "up" if uy < 0 else "down")
        chosen = None
        extra = STRIDE
        while extra <= MAX_EXTRA:
            new_len = length + extra
            new_anchor = (far[0] + ux * new_len, far[1] + uy * new_len)
            shift = (new_anchor[0] - anchor[0], new_anchor[1] - anchor[1])
            cand = geom.moved(box, shift[0], shift[1])
            text_hit = [r["text"] for r in rows if r is not lab
                        and geom.cover(cand, r["bbox"]) >= 0.2]
            body_hit = [k for k, b in bodies_svg.items() if geom.cover(cand, b) > 0.0]
            stub = (min(far[0], new_anchor[0]) - 1, min(far[1], new_anchor[1]) - 1,
                    max(far[0], new_anchor[0]) + 1, max(far[1], new_anchor[1]) + 1)
            stub_body = [k for k, b in bodies_svg.items() if geom.intersect(stub, b)]
            clash = stub_conflict(far, new_anchor, wires, own_wire_id, pins_svg, flags)
            if not text_hit and not body_hit and not stub_body and not clash:
                chosen = (new_len, shift, cand)
                break
            if clash and extra >= MAX_EXTRA:
                unsolved.append((lab["text"], box, "stub would " + clash))
            extra += STRIDE
        if chosen is None:
            unsolved.append((lab["text"], box, "no clearing length up to +%.0f" % MAX_EXTRA))
            continue
        new_len, shift, cand = chosen
        plan.append({
            "label": lab["text"], "pin": "%s:%s" % pin, "net": pins[pin]["net"],
            "direction": direction,
            "current_offset": length, "new_offset": new_len,
            "predicted_box": [round(v, 1) for v in cand],
            "clears": [{"number": t, "cover": round(c, 2)} for c, t, _ in hits],
        })

    out = {"schema": "easycirq-stub-lengthen-plan/v1",
           "label_boxes": len(targets), "collisions_covered": sum(len(h[1]) for h in targets),
           "plan": plan, "unsolved": [{"label": u[0], "box": u[1], "why": u[2]} for u in unsolved]}
    print(json.dumps({k: out[k] for k in ("label_boxes", "collisions_covered")}, ensure_ascii=False))
    for item in plan:
        print("  %-12s %-10s %-5s offset %.0f -> %.0f  clears %s"
              % (item["label"], item["pin"], item["direction"], item["current_offset"],
                 item["new_offset"], ",".join(c["number"] for c in item["clears"])))
    for item in out["unsolved"]:
        print("  UNSOLVED", item["label"], item["why"])
    if len(sys.argv) > 5:
        pathlib.Path(sys.argv[5]).write_text(json.dumps(out, ensure_ascii=False, indent=1),
                                             encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
