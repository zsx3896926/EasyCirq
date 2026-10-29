#!/usr/bin/env python3
"""One-page zone solver: modules -> frames, block bboxes and hard invariants.

Input (``easycirq-sch-zone-plan/v1``)::

    {"page_index": 0,
     "modules": [{"id": "block.a", "title": "A", "w": 160, "h": 120, "halo": 12}],
     "template": {"page": {"width": 1170, "height": 825, "margin": 12},
                  "title_block": {"rect": {"minX": 610, "minY": 12,
                                           "maxX": 1170, "maxY": 380}}},
     "gap": 40,
     "title_gap": 36}

The solver packs the modules into the usable regions derived from the page
template: a left strip (left of the title block, full usable height) and a
top-right strip (right of the title block, above it). Modules are shelf-packed
tallest-first, with a deterministic id tiebreak. Every module reserves its
zone padding while packing, so a placed block never ends up with a clipped
zone:

* ``pad = max(DEFAULT_ZONE_PAD, halo)`` on the left, right and bottom edges;
* ``pad + title_gap`` on the top edge, leaving room for the zone title above
  the block;
* horizontal shelf spacing is ``max(gap, pad_a + pad_b)`` and vertical shelf
  spacing is ``max(gap, title_gap + pad_upper + pad_lower)``, so adjacent
  zones meet exactly instead of overlapping.

Each zone is derived as ``bbox + pad`` (plus ``title_gap`` on top) and clipped
to its region. Zone edges are additionally capped at the midpoint of any
residual overlap as a safety net. The caps are normally a no-op because the
packing spacing already separates the zones.

Hard invariants guaranteed for every placed block:

(a) the zone lies inside the page minus margin;
(b) the zone does not intersect the title-block keep-out;
(c) the block bbox and its halo clearance lie inside its zone;
(d) no two block bboxes overlap, and no two zones overlap.

A module that cannot fit is reported in ``unplaced`` and the plan verdict is
``blocked``. Output schema is ``easycirq-sch-zone-plan/v1`` with ``frames``,
``blocks`` (``bbox``/``zone`` are ``null`` when unplaced) and ``metrics``
(``fits``, ``overlaps``, ``zone_overlaps``, ``title_block_hits``,
``zone_slack``, ``zone_fill``, ``score``). The result is deterministic for a
given input.

This module is offline by design: it uses only the standard library and never
talks to an EDA tool.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

SCHEMA = "easycirq-sch-zone-plan/v1"
INPUT_SCHEMA = SCHEMA

# Zone padding when a module has no (or a smaller) halo.
DEFAULT_ZONE_PAD = 8
# Zone fill band rewarded by the quality score (contract section 3).
ZONE_FILL_MIN = 0.55
ZONE_FILL_MAX = 0.85
# Zone slack (padding area / page area) above which the layout is penalised.
ZONE_SLACK_LIMIT = 0.25
_EPS = 1e-9


def _number(value, label, *, positive=False):
    """Validate a finite numeric input (bools are rejected)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("%s must be a number" % label)
    if not math.isfinite(value):
        raise ValueError("%s must be finite" % label)
    if positive and value <= 0:
        raise ValueError("%s must be positive" % label)
    if not positive and value < 0:
        raise ValueError("%s must be non-negative" % label)
    return value


def _title_block(raw, page):
    """Normalise and validate ``template.title_block`` (or null)."""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError("template.title_block must be an object or null")
    rect = raw.get("rect")
    if rect is None and all(key in raw for key in ("minX", "minY", "maxX", "maxY")):
        # Accept the flat rect form used by easycirq-sch-layout-plan/v1 too.
        rect = raw
    if not isinstance(rect, dict):
        raise ValueError("template.title_block.rect must be an object")
    block = {}
    for key in ("minX", "minY", "maxX", "maxY"):
        block[key] = _number(rect.get(key), "title_block.rect.%s" % key)
    if block["maxX"] <= block["minX"] or block["maxY"] <= block["minY"]:
        raise ValueError("title block rect must have positive area")
    if (block["minX"] < 0 or block["minY"] < 0
            or block["maxX"] > page["width"] or block["maxY"] > page["height"]):
        raise ValueError("title block rect must lie inside the page")
    return block


def _modules(raw):
    """Validate the module list and return normalised module dicts."""
    if not isinstance(raw, list) or not raw:
        raise ValueError("modules must be a non-empty list")
    modules, seen = [], set()
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError("modules[%d] must be an object" % index)
        module_id = item.get("id")
        if not isinstance(module_id, str) or not module_id:
            raise ValueError("modules[%d].id must be a non-empty string" % index)
        if module_id in seen:
            raise ValueError("duplicate module id %r" % module_id)
        seen.add(module_id)
        title = item.get("title")
        if not isinstance(title, str):
            raise ValueError("module %r title must be a string" % module_id)
        width = _number(item.get("w"), "module %r w" % module_id, positive=True)
        height = _number(item.get("h"), "module %r h" % module_id, positive=True)
        halo = item.get("halo")
        halo = 0 if halo is None else _number(halo, "module %r halo" % module_id)
        modules.append({"id": module_id, "title": title,
                        "w": width, "h": height, "halo": halo})
    return modules


def _request_parts(request):
    """Validate the request envelope and return its normalised parts."""
    if not isinstance(request, dict):
        raise ValueError("request must be an object")
    schema = request.get("schema")
    if schema is not None and schema != INPUT_SCHEMA:
        raise ValueError("schema must be %s" % INPUT_SCHEMA)
    page_index = request.get("page_index")
    if isinstance(page_index, bool) or not isinstance(page_index, int) or page_index < 0:
        raise ValueError("page_index must be a non-negative integer")
    template = request.get("template")
    if not isinstance(template, dict):
        raise ValueError("template must be an object")
    page_raw = template.get("page")
    if not isinstance(page_raw, dict):
        raise ValueError("template.page must be an object")
    page = {}
    for key in ("width", "height"):
        page[key] = _number(page_raw.get(key), "template.page.%s" % key, positive=True)
    page["margin"] = _number(page_raw.get("margin"), "template.page.margin")
    if page["margin"] * 2 >= page["width"] or page["margin"] * 2 >= page["height"]:
        raise ValueError("template.page.margin leaves no usable area")
    title_block = _title_block(template.get("title_block"), page)
    modules = _modules(request.get("modules"))
    gap = _number(request.get("gap"), "gap")
    title_gap = _number(request.get("title_gap"), "title_gap")
    return page_index, page, title_block, modules, gap, title_gap


def usable_regions(page, title_block):
    """Return the usable rectangles of one page as ``{name, rect}`` dicts.

    Without a title block the whole content area is one region. With a title
    block the page is split into the left strip (left of ``minX``, full usable
    height) and the top-right strip (right of ``minX``, above ``maxY``).
    Regions are clipped to the page minus margin and empty ones are dropped.
    """
    margin = page["margin"]
    content = {"minX": margin, "minY": margin,
               "maxX": page["width"] - margin, "maxY": page["height"] - margin}

    def clipped(rect):
        rect = {"minX": max(rect["minX"], content["minX"]),
                "minY": max(rect["minY"], content["minY"]),
                "maxX": min(rect["maxX"], content["maxX"]),
                "maxY": min(rect["maxY"], content["maxY"])}
        if rect["maxX"] <= rect["minX"] or rect["maxY"] <= rect["minY"]:
            return None
        return rect

    regions = []
    if title_block:
        left = clipped({"minX": content["minX"], "minY": content["minY"],
                        "maxX": title_block["minX"], "maxY": content["maxY"]})
        if left is not None:
            regions.append({"name": "left", "rect": left})
        top_right = clipped({"minX": title_block["minX"], "minY": title_block["maxY"],
                             "maxX": content["maxX"], "maxY": content["maxY"]})
        if top_right is not None:
            regions.append({"name": "top-right", "rect": top_right})
    else:
        regions.append({"name": "page", "rect": content})
    return regions


def _pad(module):
    """Zone padding for a module: never thinner than its halo clearance."""
    return max(DEFAULT_ZONE_PAD, module["halo"])


def _col_spacing(gap, previous_pad, pad):
    """Horizontal spacing between shelf neighbours (zones then meet)."""
    return max(gap, previous_pad + pad)


def _row_spacing(gap, title_gap, upper_pad, lower_pad):
    """Vertical spacing between shelves, including the upper zone title."""
    return max(gap, title_gap + upper_pad + lower_pad)


def _pack(modules, regions, gap, title_gap):
    """Deterministic shelf packing; returns placements with bbox or ``None``.

    Modules are ordered by descending height, then width, then id. A module is
    only appended to an existing shelf when its pad does not exceed the shelf's
    established max pad, which keeps the spacing guarantees for every zone.
    """
    ordered = sorted(modules, key=lambda m: (-m["h"], -m["w"], m["id"]))
    shelves = {region["name"]: [] for region in regions}
    placements = []
    for module in ordered:
        pad = _pad(module)
        placed = False
        for region in regions:
            rect = region["rect"]
            width = rect["maxX"] - rect["minX"]
            height = rect["maxY"] - rect["minY"]
            rows = shelves[region["name"]]
            for row in rows:
                if module["h"] > row["h"] or pad > row["max_pad"]:
                    continue
                spacing = _col_spacing(gap, row["last_pad"], pad)
                if row["used_w"] + spacing + module["w"] + pad > width:
                    continue
                if row["y_off"] + module["h"] + pad + title_gap > height:
                    continue
                x = rect["minX"] + row["used_w"] + spacing
                y = rect["minY"] + row["y_off"]
                row["used_w"] += spacing + module["w"]
                row["last_pad"] = pad
                placements.append({"module": module, "region": region,
                                   "bbox": [x, y, x + module["w"], y + module["h"]]})
                placed = True
                break
            if placed:
                break
            if rows:
                spacing = _row_spacing(gap, title_gap, rows[-1]["max_pad"], pad)
                y_off = rows[-1]["y_off"] + rows[-1]["h"] + spacing
            else:
                y_off = pad
            if pad + module["w"] + pad > width:
                continue
            if y_off + module["h"] + pad + title_gap > height:
                continue
            rows.append({"y_off": y_off, "h": module["h"],
                         "used_w": pad + module["w"], "last_pad": pad,
                         "max_pad": pad})
            x = rect["minX"] + pad
            y = rect["minY"] + y_off
            placements.append({"module": module, "region": region,
                               "bbox": [x, y, x + module["w"], y + module["h"]]})
            placed = True
            break
        if not placed:
            placements.append({"module": module, "region": None, "bbox": None})
    return placements


def _zone_for(placement, title_gap):
    """Desired zone: bbox + pad, with ``title_gap`` above, clipped to region."""
    module = placement["module"]
    x1, y1, x2, y2 = placement["bbox"]
    pad = _pad(module)
    rect = placement["region"]["rect"]
    return [max(x1 - pad, rect["minX"]),
            max(y1 - pad, rect["minY"]),
            min(x2 + pad, rect["maxX"]),
            min(y2 + pad + title_gap, rect["maxY"])]


def _overlap(a, b):
    """Positive-area intersection of two ``[x1, y1, x2, y2]`` rects, as (ox, oy)."""
    return (max(0, min(a[2], b[2]) - max(a[0], b[0])),
            max(0, min(a[3], b[3]) - max(a[1], b[1])))


def _has_overlap(a, b):
    """True when two rects share a positive-area region (touching is fine)."""
    ox, oy = _overlap(a, b)
    return ox > _EPS and oy > _EPS


def _cap_zones(placements):
    """Trim any residual zone overlap at the midpoint of the overlap interval.

    Packing spacing normally makes this a no-op; it is kept as a hard safety
    net so the "no zone overlap" invariant never depends on the packer alone.
    """
    for i in range(len(placements)):
        a = placements[i]["zone"]
        for j in range(i + 1, len(placements)):
            b = placements[j]["zone"]
            ox, oy = _overlap(a, b)
            if ox <= _EPS or oy <= _EPS:
                continue
            if ox <= oy:
                split = (max(a[0], b[0]) + min(a[2], b[2])) / 2
                if a[0] <= b[0]:
                    a[2] = min(a[2], split)
                    b[0] = max(b[0], split)
                else:
                    b[2] = min(b[2], split)
                    a[0] = max(a[0], split)
            else:
                split = (max(a[1], b[1]) + min(a[3], b[3])) / 2
                if a[1] <= b[1]:
                    a[3] = min(a[3], split)
                    b[1] = max(b[1], split)
                else:
                    b[3] = min(b[3], split)
                    a[1] = max(a[1], split)


def _contains(rect, box):
    """True when ``box`` lies inside ``rect`` (edges may touch)."""
    return (box[0] >= rect[0] - _EPS and box[1] >= rect[1] - _EPS
            and box[2] <= rect[2] + _EPS and box[3] <= rect[3] + _EPS)


def _zone_invariants(placement):
    """Check halo containment for one placed module; page/region clipping is
    already guaranteed by construction."""
    module = placement["module"]
    bbox = placement["bbox"]
    zone = placement["zone"]
    halo = module["halo"]
    halo_box = [bbox[0] - halo, bbox[1] - halo,
                bbox[2] + halo, bbox[3] + halo]
    return _contains(zone, bbox) and _contains(zone, halo_box)


def _score(metrics):
    """Deterministic 0-100 quality score (higher is better)."""
    score = 100.0
    score -= (metrics["modules"] - metrics["fits"]) * 30
    score -= metrics["overlaps"] * 25
    score -= metrics["zone_overlaps"] * 25
    score -= metrics["title_block_hits"] * 40
    score -= max(0.0, metrics["zone_slack"] - ZONE_SLACK_LIMIT) * 60
    fill = metrics["zone_fill"]
    if fill < ZONE_FILL_MIN:
        score -= (ZONE_FILL_MIN - fill) * 40
    elif fill > ZONE_FILL_MAX:
        score -= (fill - ZONE_FILL_MAX) * 40
    return round(max(0.0, score), 1)


def solve_page(request):
    """Solve one page and return an ``easycirq-sch-zone-plan/v1`` plan."""
    page_index, page, title_block, modules, gap, title_gap = _request_parts(request)

    placements = _pack(modules, usable_regions(page, title_block), gap, title_gap)
    for placement in placements:
        placement["zone"] = (None if placement["bbox"] is None
                             else _zone_for(placement, title_gap))

    # Safety net: cap residual overlaps; if capping would clip a halo (it does
    # not with the packing spacing above), the module is reported unplaced
    # instead of returning a plan that violates a hard invariant.
    while True:
        live = [p for p in placements if p["zone"] is not None]
        _cap_zones(live)
        broken = [p for p in live if not _zone_invariants(p)]
        if not broken:
            break
        for placement in broken:
            placement["bbox"] = None
            placement["zone"] = None
            placement["region"] = None

    live = [p for p in placements if p["zone"] is not None]
    frames = []
    for placement in live:
        zone = placement["zone"]
        frames.append({
            "id": "zone-%02d" % (len(frames) + 1),
            "title": placement["module"]["title"],
            "rect": {"minX": zone[0], "minY": zone[1],
                     "maxX": zone[2], "maxY": zone[3]},
            "titleX": zone[0] + 8,
            "titleY": zone[3] - 8,
            "fontSize": 20,
            "color": "#AA00AA",
            "lineType": 1,
        })

    by_id = {placement["module"]["id"]: placement for placement in placements}
    blocks, unplaced = [], []
    for module in modules:
        placement = by_id[module["id"]]
        placed = placement["zone"] is not None
        block = {"id": module["id"], "title": module["title"],
                 "bbox": list(placement["bbox"]) if placed else None,
                 "zone": list(placement["zone"]) if placed else None,
                 "halo": module["halo"]}
        if placed:
            block["region"] = placement["region"]["name"]
        else:
            unplaced.append(module["id"])
        blocks.append(block)

    block_boxes = [placement["bbox"] for placement in live]
    zone_boxes = [placement["zone"] for placement in live]
    overlaps = sum(1 for i in range(len(block_boxes))
                   for j in range(i + 1, len(block_boxes))
                   if _has_overlap(block_boxes[i], block_boxes[j]))
    zone_overlaps = sum(1 for i in range(len(zone_boxes))
                        for j in range(i + 1, len(zone_boxes))
                        if _has_overlap(zone_boxes[i], zone_boxes[j]))
    title_hits = 0
    if title_block:
        title_box = [title_block["minX"], title_block["minY"],
                     title_block["maxX"], title_block["maxY"]]
        title_hits = sum(1 for zone in zone_boxes if _has_overlap(zone, title_box))

    block_area = sum((box[2] - box[0]) * (box[3] - box[1]) for box in block_boxes)
    zone_area = sum((box[2] - box[0]) * (box[3] - box[1]) for box in zone_boxes)
    page_area = page["width"] * page["height"]
    metrics = {
        "modules": len(modules),
        "fits": len(live),
        "all_fit": len(live) == len(modules),
        "overlaps": overlaps,
        "zone_overlaps": zone_overlaps,
        "title_block_hits": title_hits,
        "zone_slack": round(max(0.0, (zone_area - block_area) / page_area), 3),
        "zone_fill": round(block_area / zone_area, 3) if zone_area else 0.0,
    }
    metrics["score"] = _score(metrics)

    verdict = "pass" if (metrics["all_fit"] and overlaps == 0
                         and zone_overlaps == 0 and title_hits == 0) else "blocked"
    return {
        "schema": SCHEMA,
        "page_index": page_index,
        "page": page,
        "title_block": {"rect": title_block} if title_block else None,
        "regions": usable_regions(page, title_block),
        "frames": frames,
        "blocks": blocks,
        "unplaced": unplaced,
        "metrics": metrics,
        "verdict": verdict,
    }


# Alias kept for callers that spell the entry point `plan`.
def plan(request):
    """Alias of :func:`solve_page`."""
    return solve_page(request)


solve = solve_page


def main(argv=None):
    parser = argparse.ArgumentParser(description="Solve one schematic page zone plan")
    parser.add_argument("request", help="easycirq-sch-zone-plan/v1 request JSON")
    parser.add_argument("--out", help="write the plan JSON here")
    args = parser.parse_args(argv)
    try:
        request = json.loads(Path(args.request).read_text(encoding="utf-8"))
        report = solve_page(request)
    except (OSError, ValueError) as exc:
        report = {"schema": SCHEMA, "verdict": "blocked", "frames": [],
                  "blocks": [], "metrics": {}, "unplaced": [], "error": str(exc)}
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8", newline="\n")
    sys.stdout.write(text)
    return 0 if report["verdict"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
