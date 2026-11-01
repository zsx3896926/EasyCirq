"""Real-body stub preflight: decide each pin's stub direction from MEASURED geometry.

Why: the 2026-10-30 replay lost one write to

    wire-through-body (U1): wire segment 0 (725,655)->(705,655) enters component body

The pin was on-grid and the coordinates were exactly what the plan asked for — the
plan simply had C3 tucked against U1 so that C3's left pin sits ON U1's rendered
box, and a 20-unit stub to the left runs through U1. ``stub_planner`` could not
catch this because its collision model uses pin extents only (``_part_box``), not
the drawn body.

This module is the missing check: it takes the LIVE page (``sch list
--include-pins`` for pins, ``schematic.components.list {"includeBBox":true}`` for
bodies), models each candidate stub as a segment plus its label box, and reports
which directions are actually clear. A pin with no clear direction is a
layout/channel defect (B3) and must be fixed in the plan, not retried on the
canvas (B8: no blind direction thrash on the live page).

Schema: ``easycirq-stub-geom-preflight/v1``.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

BIN = r"C:\Users\jlc\AppData\Local\EasyCirq\bin\easycirq.exe"
GRID = 5.0
STUB = 20.0
MARGIN = 2.0            # kept for compatibility with earlier reports
SOFT_MARGIN = 2.0       # buffer used only by the soft (label / grazing) test
LABEL_H = 12.0
LABEL_MIN_W = 24.0
DIR_VECTOR = {"right": (1, 0), "left": (-1, 0), "up": (0, 1), "down": (0, -1)}
SIDE2DIR = {"right": "right", "left": "left", "top": "up", "bottom": "down"}
ROT2DIR = {0: "right", 90: "up", 180: "left", 270: "down"}
# Preferred order once the pin's own side is blocked: perpendicular first (a
# vertical stub reads fine and keeps flow), the opposite side last (it would run
# back across the part's own body).
PERPENDICULAR = {"right": ("up", "down"), "left": ("up", "down"),
                 "up": ("left", "right"), "down": ("left", "right")}
OPPOSITE = {"right": "left", "left": "right", "up": "down", "down": "up"}


def cli(*args, window=None, timeout=180):
    argv = [BIN, *args]
    if window:
        argv += ["--window", window]
    result = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8",
                            errors="replace", timeout=timeout)
    return (result.stdout or "") + (result.stderr or "")


def js(text):
    start = text.find("{")
    if start < 0:
        return {}
    try:
        return json.JSONDecoder().raw_decode(text[start:])[0]
    except ValueError:
        return {}


def read_live(window):
    parts = {}
    pins = js(cli("sch", "list", "--include-pins", window=window))
    for comp in (pins.get("result") or {}).get("components") or []:
        if comp.get("componentType") != "part" or not comp.get("designator"):
            continue
        parts[comp["designator"]] = {
            "anchor": (float(comp.get("x", 0.0)), float(comp.get("y", 0.0))),
            "pins": {str(p.get("pinNumber")): {"x": float(p["x"]), "y": float(p["y"]),
                                               "rotation": p.get("rotation")}
                     for p in comp.get("pins") or []},
            "bbox": None,
        }
    boxes = js(cli("call", "schematic.components.list", "--payload",
                   '{"includeBBox":true}', window=window))
    for comp in (boxes.get("result") or {}).get("components") or []:
        ref = comp.get("designator")
        if ref in parts and comp.get("bbox"):
            box = comp["bbox"]
            exact = (float(box["minX"]), float(box["minY"]),
                     float(box["maxX"]), float(box["maxY"]))
            # HARD test uses the EXACT body (the connector's guard has no margin);
            # the SOFT preference keeps a small buffer so the drawing does not end
            # up with stubs grazing a neighbour.
            parts[ref]["bbox"] = exact
            parts[ref]["bbox_soft"] = (exact[0] - SOFT_MARGIN, exact[1] - SOFT_MARGIN,
                                       exact[2] + SOFT_MARGIN, exact[3] + SOFT_MARGIN)
    return parts


def on_grid_pt(point):
    return all(abs(float(v) / GRID - round(float(v) / GRID)) < 1e-6 for v in point)


def segment_hits_box(p0, p1, box):
    """Axis-aligned segment vs expanded rectangle (Liang-Barsky clipping)."""
    if box is None:
        return False
    x0, y0, x1, y1 = box
    (ax, ay), (bx, by) = p0, p1
    dx, dy = bx - ax, by - ay
    t0, t1 = 0.0, 1.0
    for denom, numer in ((-dx, ax - x0), (dx, x1 - ax), (-dy, ay - y0), (dy, y1 - ay)):
        if abs(denom) < 1e-12:
            if numer < 0:
                return False
            continue
        t = numer / denom
        if denom < 0:
            t0 = max(t0, t)
        else:
            t1 = min(t1, t)
        if t0 > t1:
            return False
    return True


def label_box(anchor, direction, offset, width):
    x, y = anchor
    if direction == "right":
        return (x + offset, y - LABEL_H / 2.0, x + offset + width, y + LABEL_H / 2.0)
    if direction == "left":
        return (x - offset - width, y - LABEL_H / 2.0, x - offset, y + LABEL_H / 2.0)
    if direction == "up":
        return (x - width / 2.0, y + offset, x + width / 2.0, y + offset + LABEL_H)
    return (x - width / 2.0, y - offset - LABEL_H, x + width / 2.0, y - offset)


def boxes_overlap(a, b):
    return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])


def _segment(p0, p1):
    """Normalised axis-aligned segment (x0, x1, y0, y1) with an orientation tag."""
    x0, x1 = sorted((p0[0], p1[0]))
    y0, y1 = sorted((p0[1], p1[1]))
    orient = "h" if abs(y1 - y0) < 1e-9 else ("v" if abs(x1 - x0) < 1e-9 else "d")
    return (x0, x1, y0, y1, orient)


def segments_conflict(a, b):
    """Two stubs collide if they share any point: a shared point is a junction,
    and two collinear runs merging is exactly the EXT_5V_EN<->GND short seen on
    2026-10-30 (`BRIDGE nets=[EXT_5V_EN,GND] pins=[U2:3,U2:4]`)."""
    ax0, ax1, ay0, ay1, ao = a
    bx0, bx1, by0, by1, bo = b
    if ao == "h" and bo == "h":
        return abs(ay0 - by0) < 1e-6 and min(ax1, bx1) >= max(ax0, bx0) - 1e-6
    if ao == "v" and bo == "v":
        return abs(ax0 - bx0) < 1e-6 and min(ay1, by1) >= max(ay0, by0) - 1e-6
    # mixed: crossing count as a conflict (no junction, but the guard flags it)
    h, v = (a, b) if ao == "h" else (b, a)
    if h[4] != "h" or v[4] != "v":
        return False
    return (h[0] - 1e-6 <= v[0] <= h[1] + 1e-6) and (v[2] - 1e-6 <= h[2] <= v[3] + 1e-6)


def stub_free(occupied, segs):
    return not any(segments_conflict(s, o) for s in segs for o in occupied)


def hard_crossings(parts, ref, p0, p1):
    """Other components whose body the segment p0->p1 enters."""
    hits = []
    for other, info in parts.items():
        bbox = info["bbox"]
        if other == ref or bbox is None:
            continue
        if segment_hits_box(p0, p1, bbox):
            hits.append(other)
    return hits


VIA_STEPS = (10.0, 15.0, 20.0)


def _pin_sort_key(item):
    num = item[0]
    return (0, int(num)) if str(num).isdigit() else (1, str(num))


def plan(parts, nets_by_pin, offset=STUB, *, widths=None, avoid=None,
         shelves=6, step=None):
    """Decide direction + offset (+ elbow via) per pin, and prove the LABEL fits.

    Four hard rules, all measured on the live channel on 2026-10-30:

    1. the FIRST wire segment must leave along the pin's own outward normal
       (`pin-exit-direction (C3:1): pin 1 outward rotation 180° requires its first
       wire segment to leave outward`), so a pin cannot simply be re-aimed;
    2. a stub must not enter ANOTHER component's body (`wire-through-body`);
    3. two stubs must not share a point (a shared point is a junction; two
       collinear runs merging is the `BRIDGE nets=[EXT_5V_EN,GND]` short);
    4. **no two labels, and no label and measured text, may overlap.** This one
       was missing until the page showed 67 text collisions (32 label-vs-label,
       20 label-vs-pin-number, 10 label-vs-designator, 3 label-vs-value) while
       every gate said "clean".

    Rule 4 is why the offset is not a constant any more. Two cases:

    * vertical pin (up/down): the label box is side-by-side with its neighbours'
      boxes, so going FURTHER OUT separates them — ``offset + shelf*(label height
      + gap)``.
    * horizontal pin (left/right): going further out keeps the same y, so the
      boxes still overlap — the only separation is an elbow that turns
      perpendicular and staggers the run.

    ``widths`` = measured label width per net (from the SVG text measurement);
    ``avoid`` = measured designator/value/pin-name boxes that must stay clear.
    A pin with no legal candidate is reported, never retried on the canvas.
    """
    widths = widths or {}
    step = (LABEL_H + 6.0) if step is None else step
    rows, impossible = [], []
    occupied_segs = []
    occupied_boxes = list(avoid or [])

    def box_clash(box):
        return any(boxes_overlap(box, other) for other in occupied_boxes)

    for ref in sorted(parts):
        for num, pin in sorted(parts[ref]["pins"].items(), key=_pin_sort_key):
            point = (pin["x"], pin["y"])
            own = ROT2DIR.get(int(pin.get("rotation") or 0) % 360) or "right"
            key = "%s:%s" % (ref, num)
            net = nets_by_pin.get(key)
            width = widths.get(net) or max(LABEL_MIN_W, 7.0 * float(len(str(net or ""))))
            vec = DIR_VECTOR[own]
            row = {"pin": key, "net": net, "side": own, "own_side_clear": True,
                   "hard": [], "direction": None, "via": None, "offset": None,
                   "shelf": None, "label_bbox": None, "clean": False, "rule": None}

            chosen = None
            # (1) own side: stagger outward. Legal only when the box is free, which
            # for horizontal pins is usually impossible at the same y.
            for shelf in range(shelves):
                dist = offset + shelf * step
                end = (point[0] + vec[0] * dist, point[1] + vec[1] * dist)
                if not on_grid_pt(end):
                    continue
                segs = [_segment(point, end)]
                if hard_crossings(parts, ref, point, end):
                    continue
                if not stub_free(occupied_segs, segs):
                    continue
                box = label_box(point, own, dist, width)
                if box_clash(box):
                    continue
                chosen = {"direction": own, "via": None, "offset": dist,
                          "shelf": shelf, "segs": segs, "box": box, "rule": "own"}
                break
            # (2) elbow: leave outward to a via, then turn and stagger the run.
            if chosen is None:
                for via_dist in VIA_STEPS:
                    via = (point[0] + vec[0] * via_dist, point[1] + vec[1] * via_dist)
                    if not on_grid_pt(via):
                        continue
                    approach = [_segment(point, via)]
                    if hard_crossings(parts, ref, point, via):
                        continue
                    if not stub_free(occupied_segs, approach):
                        continue
                    found = None
                    for turn_rank, turn in enumerate([*PERPENDICULAR[own], OPPOSITE[own]]):
                        vec2 = DIR_VECTOR[turn]
                        for shelf in range(shelves):
                            run = offset + shelf * step
                            end = (via[0] + vec2[0] * run, via[1] + vec2[1] * run)
                            if not on_grid_pt(end):
                                continue
                            segs = approach + [_segment(via, end)]
                            if hard_crossings(parts, ref, via, end):
                                continue
                            if not stub_free(occupied_segs, segs):
                                continue
                            box = label_box(via, turn, run, width)
                            if box_clash(box):
                                continue
                            found = {"direction": turn, "via": via, "offset": run,
                                     "shelf": shelf, "segs": segs, "box": box,
                                     "rule": "elbow", "turn_rank": turn_rank,
                                     "via_dist": via_dist}
                            break
                        if found:
                            break
                    if found:
                        chosen = found
                        break
                    row["own_side_clear"] = False
            if chosen is None:
                row["hard"] = hard_crossings(
                    parts, ref, point,
                    (point[0] + vec[0] * offset, point[1] + vec[1] * offset))
                rows.append(row)
                impossible.append(row)
                continue
            row.update({k: v for k, v in chosen.items() if k not in ("segs", "box")})
            row["label_bbox"] = [round(v, 1) for v in chosen["box"]]
            rows.append(row)
            occupied_segs.extend(chosen["segs"])
            occupied_boxes.append(chosen["box"])

    return {"schema": "easycirq-stub-geom-preflight/v2",
            "pins": len(rows),
            "own_side_clear": sum(1 for r in rows if r["own_side_clear"]),
            "elbows": sum(1 for r in rows if r["rule"] == "elbow"),
            "shelved": sum(1 for r in rows if (r["shelf"] or 0) > 0),
            "impossible": len(impossible),
            "avoid_boxes": len(avoid or []),
            "rows": rows, "impossible_rows": impossible}


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--window", required=True)
    parser.add_argument("--nets", default=r"C:\Users\jlc\Documents\deepseek-harness"
                                       r"\default-workspace\easycirq-2h-deliverables"
                                       r"\pipeline-demo\C-relayout.nets.json")
    parser.add_argument("--texts", default="", help="text-bboxes.json: measured label "
                                                   "widths + designator/value avoid boxes")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    nets = json.loads(pathlib.Path(args.nets).read_text(encoding="utf-8"))["nets"]
    nets_by_pin = {"%s:%s" % (ref, pin): n["name"] for n in nets for ref, pin in n["members"]}
    widths, avoid = {}, []
    if args.texts:
        data = json.loads(pathlib.Path(args.texts).read_text(encoding="utf-8"))
        for row in data.get("rows") or []:
            role = row.get("role") or ""
            if role == "net_label":
                text = row["text"]
                widths[text] = max(widths.get(text, 0.0),
                                   row["bbox"][2] - row["bbox"][0])
            elif role in ("designator", "value", "designator?", "pin_name"):
                avoid.append(row["bbox"])
    parts = read_live(args.window)
    report = plan(parts, nets_by_pin, widths=widths, avoid=avoid)
    text = json.dumps(report, ensure_ascii=False, indent=1)
    if args.out:
        pathlib.Path(args.out).write_text(text, encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k not in ("rows", "impossible_rows")},
                     ensure_ascii=False))
    for row in report["impossible_rows"]:
        print("IMPOSSIBLE %s net=%s side=%s hard=%s"
              % (row["pin"], row["net"], row["side"], row["hard"]))
    for row in report["rows"]:
        if row["rule"] == "elbow":
            print("ELBOW      %s net=%-12s %s -> %s run=%s via=%s"
                  % (row["pin"], row["net"], row["side"], row["direction"],
                     row["offset"], row["via"]))
    return 0 if not report["impossible"] else 7


if __name__ == "__main__":
    sys.exit(main())
