"""Plan designator-attribute moves that clear text collisions, without touching electricity.

Why (2026-10-30, round 6): the C-board page is electrically complete and the only
remaining readability debt is text-on-text. Re-measuring the rendered SVG with net
names supplied makes the attribution honest: of 53 collisions, 10 are
``designator x net_label`` and 1 is ``designator x other``. A designator is pure
annotation: moving its box is the lowest-risk class of fix on the page.

Inputs are read-only artifacts (SVG text boxes + component bodies + the raw
attribute records read through ``getState_*``). Output is a machine-checkable
move plan; this module never talks to EasyEDA.

Anchor law (measured, not assumed): for every Designator attribute on this page
``getState_X/Y`` equals the *minimum corner* of the official measured bbox, and
the box extends +w in x and +10 in y (schematic Y-up). The SVG export uses the
mirrored frame ``svg_y = -sch_y``, so a plan computed in SVG space converts back
with ``new_sch_Y = old_sch_Y - dy_svg``.

Schema: ``easycirq-designator-move-plan/v1``.
"""

from __future__ import annotations

import json
import pathlib
import sys

STEP = 5.0
MAX_SHIFT = 30.0


def intersect(a, b):
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1, y1 = min(a[2], b[2]), min(a[3], b[3])
    if x1 <= x0 or y1 <= y0:
        return None
    return (x0, y0, x1, y1)


def area(box):
    return max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])


def cover(a, b):
    inter = intersect(a, b)
    if inter is None:
        return 0.0
    smaller = min(area(a), area(b))
    return 0.0 if smaller <= 1e-9 else area(inter) / smaller


def moved(box, dx, dy):
    return (box[0] + dx, box[1] + dy, box[2] + dx, box[3] + dy)


def plan(rows, bodies, attrs, *, min_ratio=0.20, step=STEP, max_shift=MAX_SHIFT, wires=None):
    """rows: audit rows (svg space); bodies: ref -> [x0,y0,x1,y1]; attrs: value -> raw record."""
    wires = wires or []
    by_text = {}
    for row in rows:
        by_text.setdefault(row["text"], []).append(row)
    report, moves = [], []
    for desig, rec in sorted(attrs.items()):
        mine = [r for r in by_text.get(desig, []) if r["role"] == "designator"]
        if len(mine) != 1:
            report.append({"designator": desig, "status": "ambiguous-boxes", "found": len(mine)})
            continue
        me = mine[0]
        body = bodies.get(desig)
        others = [r for r in rows if r is not me]
        hits = [(r, cover(me["bbox"], r["bbox"])) for r in others]
        hits = [(r, c) for r, c in hits if c >= min_ratio]
        body_bad = _hits_own_body(me["bbox"], body) or _hits_foreign_body(me["bbox"], bodies, desig)
        wire_bad = _hits_wire(me["bbox"], wires)
        if not hits and not body_bad and not wire_bad:
            report.append({"designator": desig, "status": "clean"})
            continue
        own = [r for r in others]
        best = None
        for dx in _axis(step, max_shift):
            for dy in _axis(step, max_shift):
                if dx == 0 and dy == 0:
                    continue
                cand = moved(me["bbox"], dx, dy)
                if any(cover(cand, r["bbox"]) >= min_ratio for r in own):
                    continue
                if _hits_foreign_body(cand, bodies, desig):
                    continue
                if _hits_own_body(cand, body):
                    continue
                if _hits_wire(cand, wires):
                    continue
                cost = abs(dx) + abs(dy)
                if best is None or cost < best[0]:
                    best = (cost, dx, dy)
        if best is None:
            report.append({"designator": desig,
                           "status": "no-clearance",
                           "covers": [{"text": r["text"], "role": r["role"], "cover": round(c, 3)} for r, c in hits]})
            continue
        _, dx, dy = best
        moves.append({
            "designator": desig,
            "primitiveId": rec["primitiveId"],
            "expected": rec,
            "dx_svg": dx,
            "dy_svg": dy,
            "new_x": rec["X"] + dx,
            "new_y": rec["Y"] - dy,
        })
        report.append({"designator": desig, "status": "planned", "dx_svg": dx, "dy_svg": dy,
                       "new_x": rec["X"] + dx, "new_y": rec["Y"] - dy,
                       "cleared": [{"text": r["text"], "role": r["role"], "cover": round(c, 3)} for r, c in hits]})
    return {"schema": "easycirq-designator-move-plan/v1", "moves": moves, "report": report}


def _axis(step, limit):
    out = [0.0]
    n = 1
    while n * step <= limit:
        out.append(n * step)
        out.append(-n * step)
        n += 1
    return out


def _hits_foreign_body(box, bodies, own_ref):
    for ref, b in bodies.items():
        if ref == own_ref:
            continue
        if cover(box, b) > 0.0:
            return True
    return False


def _hits_own_body(box, body):
    """A designator that lands inside its own symbol reads as body text, not a label.

    Measured consequence (round 6): the first C2 plan (dy +5 in SVG space) put
    35% of the "C2" box inside C2's own body and `sch check` reported
    ``designator-overlap C2``. Excluding the owning body keeps that regression out
    of the plan instead of relying on the post-write gate to catch it.
    """
    return body is not None and cover(box, body) > 0.0


def segments(dump, y_mirror=True, pad=1.0):
    """Turn wire polylines into axis-aligned segments used as text obstacles.

    ``easycirq`` returns each wire as a flat ``[x0,y0,x1,y1,...]`` list in
    schematic space (Y-up). Every text box here is measured on the SVG export
    (Y down), so mirror Y once, at the boundary, and thicken each segment by
    ``pad`` so a label never sits *on* a wire even when the boxes only touch.
    """
    out = []
    for wire in dump.get("result", {}).get("value", {}).get("wires", []):
        line = wire.get("line")
        if not isinstance(line, list) or len(line) < 4:
            continue
        pts = [(float(line[i]), float(line[i + 1])) for i in range(0, len(line) - 1, 2)]
        if y_mirror:
            pts = [(x, -y) for x, y in pts]
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            out.append((min(x0, x1) - pad, min(y0, y1) - pad,
                        max(x0, x1) + pad, max(y0, y1) + pad))
    return out


def _hits_wire(box, wires):
    return any(intersect(box, seg) is not None for seg in wires)


def build(texts_path, bodies_path, raw_path):
    rows = json.loads(pathlib.Path(texts_path).read_text(encoding="utf-8"))["rows"]
    # re-run the same classifier the audit uses so roles match exactly
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    import text_overlap_audit as audit_mod
    body_raw = json.loads(pathlib.Path(bodies_path).read_text(encoding="utf-8"))
    bodies, refs = {}, set()
    for comp in (body_raw.get("result") or body_raw).get("components") or []:
        ref, box = comp.get("designator"), comp.get("bbox")
        if ref and box and comp.get("componentType") == "part":
            # Component bboxes come from the editor in schematic space (Y-up);
            # every text row here is measured on the SVG export, which mirrors Y.
            # Mixing the two frames silently disables every body test (it compared
            # y=553 with y=-553 and always found no overlap), so convert once, here.
            bodies[ref] = [float(box["minX"]), -float(box["maxY"]),
                           float(box["maxX"]), -float(box["minY"])]
            refs.add(ref)
    designator_values = refs
    for row in rows:
        row["role"] = audit_mod.classify(row["text"], refs, set(), designator_values)
        row["area"] = audit_mod.area(row["bbox"])
    raw = json.loads(pathlib.Path(raw_path).read_text(encoding="utf-8"))
    attrs = {}
    for rec in raw["result"]["value"]:
        if isinstance(rec.get("X"), (int, float)) and "error" not in rec:
            attrs[rec["Value"]] = rec
    return rows, bodies, attrs


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--texts", required=True)
    parser.add_argument("--bodies", required=True)
    parser.add_argument("--raw", required=True, help="attr-read.json from debug exec")
    parser.add_argument("--wires", default="", help="wire-polyline dump from debug exec (obstacles)")
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    rows, bodies, attrs = build(args.texts, args.bodies, args.raw)
    wires = []
    if args.wires:
        wires = segments(json.loads(pathlib.Path(args.wires).read_text(encoding="utf-8")))
    result = plan(rows, bodies, attrs, wires=wires)
    result["wire_obstacles"] = len(wires)
    if args.out:
        pathlib.Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=1),
                                          encoding="utf-8")
    planned = [r for r in result["report"] if r["status"] == "planned"]
    print(json.dumps({"planned": len(planned), "moves": len(result["moves"]),
                      "statuses": {s: sum(1 for r in result["report"] if r["status"] == s)
                                   for s in {r["status"] for r in result["report"]}}},
                     ensure_ascii=False))
    for r in result["report"]:
        if r["status"] != "clean":
            print(" ", r["designator"], r["status"], "dx=%+.0f dy=%+.0f" % (r.get("dx_svg", 0), r.get("dy_svg", 0)),
                  "->", ", ".join(c["text"] for c in r.get("cleared", [])) or r.get("covers", ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
