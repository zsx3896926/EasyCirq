"""Balanced, centred packing for schematic modules (no left-edge hugging).

``layout_engine`` shelf-packs modules to the left strip, which wastes the right
side of the sheet and splits pages early.  This packer arranges module
footprints in a balanced grid:

* candidate column counts are scored by sheet-area utilisation,
* modules are assigned to columns greedily (tallest first) so column heights
  balance,
* the whole composition is centred on the sheet and kept out of the title-block
  keepout,
* gaps between modules are the modules' own label halos (so labels never cross
  into a neighbour).

Output: ``easycirq-balanced-pack/v1``.
"""

from __future__ import annotations

import math

SCHEMA = "easycirq-balanced-pack/v1"
PAGE = (10.0, 10.0, 1160.0, 815.0)
TITLE_BLOCK = (460.0, 10.0, 1160.0, 190.0)
MIN_GAP = 12.0


def _inner(page, title_block):
    """Usable area: page minus the title-block keepout strip at the bottom."""
    x0, y0, x1, y1 = page
    tb = title_block
    # keep modules above the title block when it eats the bottom-right corner
    usable_y0 = max(y0, tb[3] + 6.0) if tb else y0
    return (x0 + 6.0, usable_y0, x1 - 6.0, y1 - 6.0)


def _gap(a, b):
    """Inter-module gap.

    When ``halo_in_size`` is set on the pack call the module size already
    contains its own label halo, so cards only need a small visual gap; the
    labels then never leave the card.  Without it, fall back to the facing
    halo maximum.
    """
    if a.get("_halo_inside") or b.get("_halo_inside"):
        return MIN_GAP
    ha = a.get("halo") or {}
    hb = b.get("halo") or {}
    return max(MIN_GAP,
               float(ha.get("right", 0)), float(hb.get("left", 0)),
               float(ha.get("left", 0)), float(hb.get("right", 0)),
               float(ha.get("top", 0)), float(hb.get("bottom", 0)),
               float(ha.get("bottom", 0)), float(hb.get("top", 0)))


def _columns(modules, count):
    """Assign modules (tallest first) to ``count`` columns, balancing height."""
    order = sorted(modules, key=lambda m: (-(m["w"] * m["h"]), m["id"]))
    cols = [[] for _ in range(count)]
    heights = [0.0] * count
    for module in order:
        index = min(range(count), key=lambda i: heights[i])
        gap = _gap(cols[index][-1], module) if cols[index] else 0.0
        cols[index].append(module)
        heights[index] += module["h"] + gap
    return cols


def _measure(cols):
    widths = [max((m["w"] for m in col), default=0.0) for col in cols]
    heights = []
    for col in cols:
        total = sum(m["h"] for m in col)
        total += sum(_gap(col[i], col[i + 1]) for i in range(len(col) - 1))
        heights.append(total)
    return widths, heights


def pack(modules, *, page=PAGE, title_block=TITLE_BLOCK, max_columns=None,
         halo_in_size=False):
    """Return ``{"placements": {id: {x, y, w, h}}, "utilization": float, ...}``."""
    if not modules:
        return {"schema": SCHEMA, "placements": {}, "utilization": 0.0,
                "columns": 0, "page": page}
    if halo_in_size:
        modules = [dict(m, _halo_inside=True) for m in modules]
    area = sum(float(m["w"]) * float(m["h"]) for m in modules)
    x0, y0, x1, y1 = _inner(page, title_block)
    max_cols = max_columns or min(len(modules), 4)
    best = None
    for count in range(1, max_cols + 1):
        cols = _columns(modules, count)
        widths, heights = _measure(cols)
        gap_x = MIN_GAP * (count - 1)
        width = sum(widths) + gap_x
        height = max(heights) if heights else 0.0
        if width > (x1 - x0) or height > (y1 - y0):
            continue
        utilization = area / (width * height) if width and height else 0.0
        score = utilization - 0.02 * count
        if best is None or score > best["score"]:
            best = {"score": score, "cols": cols, "widths": widths,
                    "heights": heights, "width": width, "height": height,
                    "utilization": utilization, "count": count}
    if best is None:
        return {"schema": SCHEMA, "placements": {}, "fit": False,
                "utilization": 0.0, "columns": 0, "page": page,
                "reason": "modules do not fit the usable sheet area"}
    # centre the composition inside the usable area
    start_x = x0 + ((x1 - x0) - best["width"]) / 2.0
    top_y = y1 - ((y1 - y0) - best["height"]) / 2.0
    placements = {}
    cursor_x = start_x
    for col_index, col in enumerate(best["cols"]):
        cursor_y = top_y
        for module in col:
            placements[module["id"]] = {
                "x": round(cursor_x + best["widths"][col_index] / 2.0, 1),
                "y": round(cursor_y - float(module["h"]) / 2.0, 1),
                "w": float(module["w"]), "h": float(module["h"]),
            }
            cursor_y -= float(module["h"]) + MIN_GAP
        cursor_x += best["widths"][col_index] + MIN_GAP
    return {"schema": SCHEMA, "fit": True, "placements": placements,
            "utilization": round(best["utilization"], 3),
            "columns": best["count"],
            "composition": {"x": round(start_x, 1), "top": round(top_y, 1),
                            "w": round(best["width"], 1),
                            "h": round(best["height"], 1)},
            "page": page}


if __name__ == "__main__":
    import json
    print(json.dumps({"schema": SCHEMA}, ensure_ascii=False))
