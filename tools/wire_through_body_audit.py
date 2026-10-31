"""Find wires that pass through a component body (a readability defect no gate counts).

`sch check` has `wire-over-pin` and `wire-crossing` but no body test, and
`layout-lint` explicitly skips non-part primitives, so a stub routed across a
symbol is invisible to every existing gate. This measures it from live data:
wire polylines (schematic space) against part bboxes (schematic space).

A segment counts only when it *enters* the box: sharing an edge or touching a
pin at the boundary is normal, so endpoints are tested with a small inset.
"""

from __future__ import annotations

import json
import pathlib
import sys

INSET = 0.5


def boxes(bodies_json):
    out = {}
    data = json.loads(pathlib.Path(bodies_json).read_text(encoding="utf-8"))
    for comp in (data.get("result") or data).get("components") or []:
        ref, box = comp.get("designator"), comp.get("bbox")
        if ref and box and comp.get("componentType") == "part":
            out[ref] = (float(box["minX"]), float(box["minY"]),
                        float(box["maxX"]), float(box["maxY"]))
    return out


def segments(wires_json):
    data = json.loads(pathlib.Path(wires_json).read_text(encoding="utf-8"))
    out = []
    for wire in data.get("result", {}).get("value", {}).get("wires", []):
        line = wire.get("line")
        if not isinstance(line, list) or len(line) < 4:
            continue
        pts = [(float(line[i]), float(line[i + 1])) for i in range(0, len(line) - 1, 2)]
        for a, b in zip(pts, pts[1:]):
            out.append((wire.get("id"), a, b))
    return out


def crosses(seg, box):
    (x0, y0), (x1, y1) = seg
    bx0, by0, bx1, by1 = box
    bx0, by0, bx1, by1 = bx0 + INSET, by0 + INSET, bx1 - INSET, by1 - INSET
    if bx1 <= bx0 or by1 <= by0:
        return False
    for t in (0.0, 0.25, 0.5, 0.75, 1.0):
        x = x0 + (x1 - x0) * t
        y = y0 + (y1 - y0) * t
        if bx0 < x < bx1 and by0 < y < by1:
            return True
    return False


def main():
    bodies = boxes(sys.argv[1])
    segs = segments(sys.argv[2])
    hits = {}
    for wid, a, b in segs:
        for ref, box in bodies.items():
            if crosses((a, b), box):
                hits.setdefault(ref, []).append((wid, a, b))
    print(json.dumps({"segments": len(segs), "bodies": len(bodies),
                      "parts_with_wire_through_body": len(hits),
                      "wire_segments_through_body": sum(len(v) for v in hits.values())},
                     ensure_ascii=False))
    for ref in sorted(hits):
        print(" ", ref, len(hits[ref]), "segments; sample:", hits[ref][0][1:], "wire", hits[ref][0][0])
    return 0


if __name__ == "__main__":
    sys.exit(main())
