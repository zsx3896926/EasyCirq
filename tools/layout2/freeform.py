#!/usr/bin/env python3
"""Freeform schematic layout planner: L-shaped page + rectangle-union zones.

The v2 engine (``tools.layout2.layout_engine``) splits the page around a corner
title block into two fixed shelves.  This module keeps the same offline
contract (plain dicts in, plain dicts out, no EDA, no daemon, no network) but
models the printable area as an explicit list of rectangles:

* the usable page rectangle is inset by ``page.margin``;
* the title-block keep-out is subtracted from it with :func:`subtract_rect`,
  leaving the L-shaped (or generally rectangular-complement) printable area;
* modules are packed with a deterministic first-fit over a list of free
  rectangles: a placed module consumes its footprint at the top-left corner of
  a free rectangle and the remainder is split into a right strip and a top
  strip, each separated from the module by the placement gap;
* zones are decoration around a module (``bbox + halo + zone_pad``) clipped to
  the printable region union.  Near the concave L corner a zone crosses the
  region split, so it is emitted as a rectangle union with ``zone_kind``
  ``"rect"`` or ``"union"``.

Input (``plan_project_freeform``)::

    {
      "name": "audio",                       # optional project label
      "page": {"width": 1170, "height": 825, "margin": 10},   # optional
      "title_block": {"rect": [460, 10, 1160, 190]},          # optional; None = none
      "options": {"gap": 6, "zone_pad": 4},                   # optional
      "modules": [
        {"id": "a", "title": "A", "w": 350, "h": 220},
        {"id": "b", "w": 300, "h": 200, "halo": 12, "min_gap": 20},
      ],
    }

The page/title-block defaults mirror the measured defaults used by
``layout_engine`` (EasyEDA Pro 4.1.78, 2026-10-29) so both planners can be
compared on the same fixture.

Output (``easycirq-sch-layout-freeform/v1``)::

    {
      "schema": ..., "project": ..., "verdict": "pass"|"blocked",
      "page": ..., "title_block": ..., "regions": [...],
      "blocks": [{"id", "title", "bbox", "footprint", "halo", "region",
                  "zone": [[x0, y0, x1, y1], ...], "zone_kind"}],
      "zones": [{"id", "rects", "kind"}],
      "unplaced": [...],
      "metrics": {"fits", "overlaps", "title_block_hits",
                  "page_utilization", "zone_fill"},
      "findings": [...],
    }

Exit codes for the CLI: 0 pass, 1 blocked.
"""
from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

SCHEMA = "easycirq-sch-layout-freeform/v1"

#: Measured default page template (same values as tools/layout2/layout_engine.py).
DEFAULT_PAGE = {"width": 1170, "height": 825, "margin": 10}
DEFAULT_TITLE_BLOCK = {"rect": [460, 10, 1160, 190]}
DEFAULT_OPTIONS = {"gap": 6.0, "zone_pad": 4.0}

SIDES = ("left", "right", "top", "bottom")
EPS = 1e-9


class FreeformError(ValueError):
    """Invalid input or geometry that cannot be planned offline."""


# ---------------------------------------------------------------------------
# numbers and rectangles (rects are (x0, y0, x1, y1) float tuples)
# ---------------------------------------------------------------------------


def _is_number(value) -> bool:
    return (isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(float(value)))


def _number(value, label: str, *, minimum: float | None = None,
            positive: bool = False) -> float:
    if not _is_number(value):
        raise FreeformError("%s must be a finite number" % label)
    number = float(value)
    if positive and number <= 0:
        raise FreeformError("%s must be positive" % label)
    if minimum is not None and number < minimum:
        raise FreeformError("%s must be >= %s" % (label, minimum))
    return number


def _as_rect(value):
    """Return a ``(x0, y0, x1, y1)`` tuple, or None when malformed."""
    if isinstance(value, Mapping):
        keys = ("minX", "minY", "maxX", "maxY")
        if not all(key in value for key in keys):
            return None
        values = [value[key] for key in keys]
    elif isinstance(value, (list, tuple)) and len(value) == 4:
        values = list(value)
    else:
        return None
    if not all(_is_number(item) for item in values):
        return None
    return tuple(float(item) for item in values)


def _rect_list(rect) -> list:
    return [float(value) for value in rect]


def rect_area(rect) -> float:
    """Area of a ``(x0, y0, x1, y1)`` rectangle."""
    parsed = _as_rect(rect)
    if parsed is None:
        raise FreeformError("rect must be [x0, y0, x1, y1]")
    return max(0.0, parsed[2] - parsed[0]) * max(0.0, parsed[3] - parsed[1])


def _rect_positive(rect) -> bool:
    return rect is not None and rect[2] - rect[0] > EPS and rect[3] - rect[1] > EPS


def rect_intersects(first, second) -> bool:
    """True for a positive-area overlap (edge touching is not a hit)."""
    a, b = _as_rect(first), _as_rect(second)
    if a is None or b is None:
        return False
    return (a[0] < b[2] - EPS and b[0] < a[2] - EPS
            and a[1] < b[3] - EPS and b[1] < a[3] - EPS)


def rect_contains(outer, inner) -> bool:
    """True when ``inner`` lies inside ``outer`` (touching allowed)."""
    a, b = _as_rect(outer), _as_rect(inner)
    if a is None or b is None:
        return False
    return (a[0] <= b[0] + EPS and a[1] <= b[1] + EPS
            and b[2] <= a[2] + EPS and b[3] <= a[3] + EPS)


def _rect_clip(rect, bounds):
    a, b = _as_rect(rect), _as_rect(bounds)
    if a is None or b is None:
        return None
    return (max(a[0], b[0]), max(a[1], b[1]),
            min(a[2], b[2]), min(a[3], b[3]))


def _rect_gap(first, second) -> float:
    """Chebyshev gap between two rectangles (0 when they touch or overlap)."""
    a, b = _as_rect(first), _as_rect(second)
    if a is None or b is None or rect_intersects(a, b):
        return 0.0
    dx = max(b[0] - a[2], a[0] - b[2])
    dy = max(b[1] - a[3], a[1] - b[3])
    return max(dx, dy)


def _rects_equal(first, second) -> bool:
    return (first is not None and second is not None
            and all(abs(first[i] - second[i]) <= 1e-6 for i in range(4)))


def _overlap_pairs(rects) -> int:
    count = 0
    for index in range(len(rects)):
        for other in range(index + 1, len(rects)):
            if rect_intersects(rects[index], rects[other]):
                count += 1
    return count


# ---------------------------------------------------------------------------
# region model: usable page minus title block
# ---------------------------------------------------------------------------


def subtract_rect(rect, hole) -> list:
    """Rectangular complement of ``hole`` inside ``rect``.

    Returns up to four disjoint rectangles that together cover ``rect`` minus
    ``hole`` (edge-touching holes produce fewer pieces).  The order is stable:
    left, right, bottom, top.
    """
    base = _as_rect(rect)
    cut = _as_rect(hole)
    if base is None or not _rect_positive(base):
        raise FreeformError("rect must be a positive [x0, y0, x1, y1] rectangle")
    if cut is None:
        raise FreeformError("hole must be [x0, y0, x1, y1]")
    if not rect_intersects(base, cut):
        return [_rect_list(base)]
    pieces = []
    if cut[0] > base[0] + EPS:
        pieces.append((base[0], base[1], min(cut[0], base[2]), base[3]))
    if cut[2] < base[2] - EPS:
        pieces.append((max(cut[2], base[0]), base[1], base[2], base[3]))
    x0, x1 = max(base[0], cut[0]), min(base[2], cut[2])
    if x1 > x0 + EPS:
        if cut[1] > base[1] + EPS:
            pieces.append((x0, base[1], x1, min(cut[1], base[3])))
        if cut[3] < base[3] - EPS:
            pieces.append((x0, max(cut[3], base[1]), x1, base[3]))
    return [_rect_list(piece) for piece in pieces
            if piece[2] - piece[0] > EPS and piece[3] - piece[1] > EPS]


def _normalize_page(page) -> dict:
    if page is None:
        page = DEFAULT_PAGE
    if not isinstance(page, Mapping):
        raise FreeformError("page must be an object")
    width = _number(page.get("width"), "page.width", positive=True)
    height = _number(page.get("height"), "page.height", positive=True)
    margin = _number(page.get("margin", 0), "page.margin", minimum=0)
    if width <= 2 * margin or height <= 2 * margin:
        raise FreeformError("page margin leaves no usable page area")
    return {"width": width, "height": height, "margin": margin}


def _normalize_title_block(raw):
    if raw is None:
        return None
    if isinstance(raw, Mapping) and "rect" in raw:
        raw = raw["rect"]
    rect = _as_rect(raw)
    if rect is None or not _rect_positive(rect):
        raise FreeformError("title_block.rect must be [x0, y0, x1, y1]")
    return rect


def usable_rect(page) -> list:
    """Inner printable rectangle of a page (before the title block is cut out)."""
    normalized = _normalize_page(page)
    margin = normalized["margin"]
    return [margin, margin,
            normalized["width"] - margin, normalized["height"] - margin]


def build_regions(page, title_block=None) -> list:
    """Printable region model: usable page minus the title-block keep-out.

    Returns ``[{"name", "rect"}, ...]``; the pieces are disjoint and, for a
    title block anchored in a corner, form the L-shaped printable area.
    """
    usable = tuple(usable_rect(page))
    block = _normalize_title_block(title_block)
    if block is None:
        return [{"name": "page", "rect": _rect_list(usable)}]
    block = _rect_clip(block, usable)
    if not _rect_positive(block):
        return [{"name": "page", "rect": _rect_list(usable)}]
    pieces = subtract_rect(usable, block)
    if not pieces:
        raise FreeformError("title block covers the whole usable page area")
    if len(pieces) == 1:
        return [{"name": "page", "rect": pieces[0]}]
    return [{"name": "region-%d" % (index + 1), "rect": piece}
            for index, piece in enumerate(pieces)]


def _normalize_regions(regions) -> list:
    if not isinstance(regions, (list, tuple)) or not regions:
        raise FreeformError("regions must be a non-empty list")
    normalized = []
    for index, entry in enumerate(regions):
        if isinstance(entry, Mapping):
            name = entry.get("name")
            if not isinstance(name, str) or not name.strip():
                name = "region-%d" % (index + 1)
            rect = _as_rect(entry.get("rect", entry))
        else:
            name = "region-%d" % (index + 1)
            rect = _as_rect(entry)
        if rect is None or not _rect_positive(rect):
            raise FreeformError("region %r rect must be [x0, y0, x1, y1]"
                                % (name,))
        normalized.append({"name": name.strip(), "rect": rect})
    return normalized


# ---------------------------------------------------------------------------
# modules
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Module:
    """One layout atom: size, halo clearance and per-module minimum gap."""

    id: str
    title: str
    w: float
    h: float
    halo: Mapping[str, float]
    min_gap: float

    @property
    def area(self) -> float:
        return self.w * self.h

    @property
    def footprint_w(self) -> float:
        return self.halo["left"] + self.w + self.halo["right"]

    @property
    def footprint_h(self) -> float:
        return self.halo["top"] + self.h + self.halo["bottom"]


def _normalize_halo(value, module_id: str) -> dict:
    if value is None:
        return {side: 0.0 for side in SIDES}
    if _is_number(value):
        side = float(value)
        if side < 0:
            raise FreeformError("module %r halo must be >= 0" % (module_id,))
        return {name: side for name in SIDES}
    if not isinstance(value, Mapping):
        raise FreeformError("module %r halo must be a number or an object"
                            % (module_id,))
    halo = {}
    for side in SIDES:
        side_value = value.get(side, 0.0)
        if not _is_number(side_value) or float(side_value) < 0:
            raise FreeformError("module %r halo.%s must be >= 0"
                                % (module_id, side))
        halo[side] = float(side_value)
    unknown = sorted(set(value) - set(SIDES))
    if unknown:
        raise FreeformError("module %r halo has unknown sides: %s"
                            % (module_id, ", ".join(unknown)))
    return halo


def _normalize_modules(modules) -> list:
    if not isinstance(modules, (list, tuple)) or not modules:
        raise FreeformError("modules must be a non-empty list")
    out = []
    seen = set()
    for index, entry in enumerate(modules):
        if isinstance(entry, Module):
            if entry.id in seen:
                raise FreeformError("duplicate module id %r" % entry.id)
            seen.add(entry.id)
            out.append(entry)
            continue
        if not isinstance(entry, Mapping):
            raise FreeformError("module #%d must be an object" % index)
        module_id = entry.get("id")
        if not isinstance(module_id, str) or not module_id.strip():
            raise FreeformError("module #%d has no usable id" % index)
        module_id = module_id.strip()
        if module_id in seen:
            raise FreeformError("duplicate module id %r" % module_id)
        seen.add(module_id)
        title = entry.get("title")
        if not isinstance(title, str) or not title.strip():
            title = module_id
        width = _number(entry.get("w"), "module %r w" % module_id, positive=True)
        height = _number(entry.get("h"), "module %r h" % module_id, positive=True)
        halo = _normalize_halo(entry.get("halo"), module_id)
        min_gap = _number(entry.get("min_gap", 0.0),
                          "module %r min_gap" % module_id, minimum=0)
        out.append(Module(module_id, title.strip(), width, height, halo, min_gap))
    return out


# ---------------------------------------------------------------------------
# packing: first fit over free rectangles, splitting the remainder
# ---------------------------------------------------------------------------


def _placement(module: Module, footprint, bbox, region_name: str) -> dict:
    return {
        "id": module.id,
        "title": module.title,
        "w": module.w,
        "h": module.h,
        "halo": {side: module.halo[side] for side in SIDES},
        "min_gap": module.min_gap,
        "area": module.w * module.h,
        "footprint": _rect_list(footprint),
        "bbox": _rect_list(bbox),
        "region": region_name,
    }


def place_modules(modules, regions, gap=0.0) -> dict:
    """Place modules first-fit into the free rectangle list, deterministically.

    Modules are ordered by descending area (ties by id), so the layout does not
    depend on the caller's list order.  A module is placed at the top-left id
    corner of the first free rectangle that can hold its halo-expanded
    footprint; the free rectangle is split into a right strip and a top strip,
    each offset by ``max(gap, module.min_gap)``.  A candidate must also keep
    that clearance from every already placed footprint.

    Returns ``{"placements": [...], "unplaced": [...], "free_rects": [...]}``.
    """
    entries = _normalize_modules(modules)
    spacing_default = _number(gap, "gap", minimum=0)
    region_entries = _normalize_regions(regions)
    free = [(entry["name"], entry["rect"]) for entry in region_entries]
    ordered = sorted(entries, key=lambda module: (-module.area, module.id))
    placements = []
    unplaced = []
    footprints = []  # (footprint, min_gap) of accepted placements
    for module in ordered:
        spacing = max(spacing_default, module.min_gap)
        fw, fh = module.footprint_w, module.footprint_h
        placed = False
        for index, (name, rect) in enumerate(free):
            if fw > rect[2] - rect[0] + EPS or fh > rect[3] - rect[1] + EPS:
                continue
            footprint = (rect[0], rect[1], rect[0] + fw, rect[1] + fh)
            clear = True
            for other, other_min_gap in footprints:
                required = max(spacing, other_min_gap)
                if _rect_gap(footprint, other) < required - EPS:
                    clear = False
                    break
            if not clear:
                continue
            bbox = (footprint[0] + module.halo["left"],
                    footprint[1] + module.halo["top"],
                    footprint[0] + module.halo["left"] + module.w,
                    footprint[1] + module.halo["top"] + module.h)
            placements.append(_placement(module, footprint, bbox, name))
            footprints.append((footprint, module.min_gap))
            right = (footprint[2] + spacing, rect[1], rect[2], rect[3])
            top = (rect[0], footprint[3] + spacing,
                   min(rect[2], footprint[2] + spacing), rect[3])
            remainder = [(name, piece) for piece in (right, top)
                         if _rect_positive(piece)]
            free[index:index + 1] = remainder
            placed = True
            break
        if not placed:
            unplaced.append(module.id)
    return {"placements": placements, "unplaced": unplaced,
            "free_rects": [_rect_list(rect) for _name, rect in free]}


# ---------------------------------------------------------------------------
# zones: rectangle union clipped to the region model
# ---------------------------------------------------------------------------


def zone_rects(footprint, regions, pad=0.0) -> list:
    """Rectangle union around a module footprint, clipped to the regions.

    The footprint is expanded by ``pad`` on every side and intersected with
    each region rectangle; the surviving pieces are the zone.  Near the
    concave L corner this yields more than one rectangle.
    """
    base = _as_rect(footprint)
    if base is None or not _rect_positive(base):
        raise FreeformError("footprint must be a positive [x0, y0, x1, y1]"
                            " rectangle")
    distance = _number(pad, "zone_pad", minimum=0)
    region_entries = _normalize_regions(regions)
    expanded = (base[0] - distance, base[1] - distance,
                base[2] + distance, base[3] + distance)
    pieces = []
    for entry in region_entries:
        piece = _rect_clip(expanded, entry["rect"])
        if not _rect_positive(piece):
            continue
        if any(_rects_equal(piece, existing) for existing in pieces):
            continue
        pieces.append(piece)
    pieces.sort(key=lambda rect: (round(rect[1], 6), round(rect[0], 6),
                                  round(rect[2], 6), round(rect[3], 6)))
    return [_rect_list(piece) for piece in pieces]


# ---------------------------------------------------------------------------
# project plan
# ---------------------------------------------------------------------------


def _project_name(project) -> str:
    if isinstance(project, Mapping):
        for key in ("name", "id", "title"):
            value = project.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return "project"


def _normalize_options(raw) -> dict:
    options = dict(DEFAULT_OPTIONS)
    if raw is None:
        return options
    if not isinstance(raw, Mapping):
        raise FreeformError("options must be an object")
    for key in DEFAULT_OPTIONS:
        if key in raw:
            options[key] = _number(raw[key], "option %r" % key, minimum=0)
    return options


def _normalize_project(project):
    if not isinstance(project, Mapping):
        raise FreeformError("project must be an object")
    template = project.get("template")
    if template is not None:
        if not isinstance(template, Mapping):
            raise FreeformError("project.template must be an object")
        page_raw = template.get("page")
        title_raw = template.get("title_block", DEFAULT_TITLE_BLOCK)
        options_raw = template.get("options")
    else:
        page_raw = project.get("page")
        title_raw = project.get("title_block", DEFAULT_TITLE_BLOCK)
        options_raw = project.get("options")
    page = _normalize_page(page_raw)
    title_block = _normalize_title_block(title_raw)
    options = _normalize_options(options_raw)
    modules = _normalize_modules(project.get("modules"))
    return page, title_block, options, modules


def _title_block_dict(rect) -> dict | None:
    return {"rect": _rect_list(rect)} if rect is not None else None


def _empty_metrics() -> dict:
    return {"fits": 0, "overlaps": 0, "title_block_hits": 0,
            "page_utilization": 0.0, "zone_fill": 0.0}


def _blocked_result(name: str, exc: FreeformError) -> dict:
    return {
        "schema": SCHEMA,
        "project": name,
        "verdict": "blocked",
        "page": None,
        "title_block": None,
        "regions": [],
        "blocks": [],
        "zones": [],
        "unplaced": [],
        "metrics": _empty_metrics(),
        "findings": [{"code": "invalid_project", "severity": "error",
                      "message": str(exc)}],
    }


def _metrics(page, title_block, blocks) -> dict:
    usable = tuple(usable_rect(page))
    usable_area = rect_area(usable)
    if title_block is not None:
        usable_area -= rect_area(_rect_clip(title_block, usable))
    block_area = sum((block["bbox"][2] - block["bbox"][0])
                     * (block["bbox"][3] - block["bbox"][1])
                     for block in blocks)
    zone_area = sum(rect_area(rect) for block in blocks
                    for rect in block["zone"])
    bboxes = [block["bbox"] for block in blocks]
    title_block_hits = 0
    if title_block is not None:
        for block in blocks:
            hit = rect_intersects(block["bbox"], title_block)
            if not hit:
                hit = any(rect_intersects(rect, title_block)
                          for rect in block["zone"])
            title_block_hits += 1 if hit else 0
    return {
        "fits": len(blocks),
        "overlaps": _overlap_pairs(bboxes),
        "title_block_hits": title_block_hits,
        "page_utilization": (round(block_area / usable_area, 4)
                             if usable_area else 0.0),
        "zone_fill": (round(block_area / zone_area, 4)
                      if zone_area else 0.0),
    }


def plan_project_freeform(project) -> dict:
    """Plan one project onto a single freeform page.

    Returns an ``easycirq-sch-layout-freeform/v1`` page plan.  Invalid input
    yields a ``blocked`` plan with a finding; modules that do not fit the
    printable region matrix are reported in ``unplaced`` (verdict ``blocked``).
    """
    name = _project_name(project)
    try:
        page, title_block, options, modules = _normalize_project(project)
    except FreeformError as exc:
        return _blocked_result(name, exc)

    regions = build_regions(page, title_block)
    # keep decoration zones disjoint: the gap must cover both zone bands
    gap = max(options["gap"], 2 * options["zone_pad"] + 2
              if options["zone_pad"] else 0.0)
    packed = place_modules(modules, regions, gap)

    blocks = []
    for placement in packed["placements"]:
        footprint = tuple(placement["footprint"])
        zone = zone_rects(footprint, regions, options["zone_pad"])
        blocks.append({
            "id": placement["id"],
            "title": placement["title"],
            "w": placement["w"],
            "h": placement["h"],
            "halo": placement["halo"],
            "region": placement["region"],
            "bbox": placement["bbox"],
            "footprint": placement["footprint"],
            "zone": zone,
            "zone_kind": "rect" if len(zone) == 1 else "union",
        })
    zones = [{"id": block["id"], "rects": block["zone"],
              "kind": block["zone_kind"]} for block in blocks]

    findings = [{
        "code": "module_does_not_fit",
        "severity": "error",
        "message": "module %r does not fit the printable region model"
                   % (module_id,),
        "id": module_id,
    } for module_id in packed["unplaced"]]
    return {
        "schema": SCHEMA,
        "project": name,
        "verdict": "pass" if not findings else "blocked",
        "page": {key: page[key] for key in ("width", "height", "margin")},
        "title_block": _title_block_dict(title_block),
        "regions": [{"name": entry["name"], "rect": _rect_list(entry["rect"])}
                    for entry in regions],
        "blocks": blocks,
        "zones": zones,
        "unplaced": packed["unplaced"],
        "metrics": _metrics(page, title_block, blocks),
        "findings": findings,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Offline freeform layout planner (L-shape, no EDA)")
    parser.add_argument("project", help="project JSON file")
    args = parser.parse_args(argv)
    project = json.loads(Path(args.project).read_text(encoding="utf-8"))
    plan = plan_project_freeform(project)
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    return 0 if plan["verdict"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
