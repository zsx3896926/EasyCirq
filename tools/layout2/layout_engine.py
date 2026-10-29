"""Offline schematic layout engine v2 (orchestrator).

Pipeline (entirely offline, no EDA):

    device metrics (halo defaults)
      -> pagination (area lower bound + affinity groups kept whole)
      -> per-page zone packing (shelf into the left strip and the top-right
         strip, halo-aware, zone capping)
      -> optional label placement (frame titles)
      -> per-page self-contained validation of the v2 hard rules.

Output schema: ``easycirq-sch-layout-v2/v1``; see
``docs/method/layout-engine-v2-contract.md``.

Geometry model
--------------
* page template: page ``width``/``height``/``margin`` plus a ``title_block``
  keep-out.  The default is the measured template (1170x825, margin 10,
  title block [460, 10]-[1160, 190]).
* usable page area = page inset by ``margin``.
* regions partition the usable area around the title block.  For the default
  (top-right title block) that is ``left`` (full height, left of the block)
  and ``top-right`` (below the block, full remaining width).  A gap of
  ``min_gap`` is kept between regions and around the title block.
* module -> zone: the zone is the drawn module frame.  It wraps the measured
  module bbox plus its halo plus a ``header_h`` title strip plus ``zone_pad``
  on both sides.  Zone capping means a zone that does not fit a region is
  never clamped: it is left for the next region, and only a module that fits
  no region makes the plan ``blocked``.
* block bbox + halo must stay fully inside its zone (hard rule 3).

Optional sibling hooks (all in ``tools/layout2/``): when present and usable
they are called, otherwise the internal implementations below run.  A sibling
that raises is ignored, never propagated.

    ``pagination.paginate(modules, template, cfg)``
        -> list of pages, each a list of module ids (or Module objects)
    ``zone_solver.solve_page(modules, template, cfg)``
        -> {"placements": [{"id": ..., "x": ..., "y": ...}], "unplaced": [...]}
           where x/y is the zone top-left corner
    ``label_solver.place_labels(page, cfg)``
        -> [{"text": ..., "bbox": [x0, y0, x1, y1], "anchor": [x, y]}]
    ``hard_rules.validate_page(page, template, cfg)``
        -> {"verdict": "pass"|"blocked", "findings": [...]}

The internal code is deterministic: no randomness, no clock, no filesystem
state beyond the optional text-metrics asset table.
"""

from __future__ import annotations

import argparse
import copy
import importlib
import json
import math
from dataclasses import dataclass
from pathlib import Path

SCHEMA = "easycirq-sch-layout-v2/v1"
PAGE_TEMPLATE_SCHEMA = "easycirq-page-template/v1"

REPO_ROOT = Path(__file__).resolve().parents[2]
ASSETS = REPO_ROOT / "easycirq" / "assets"

EPS = 1e-9

#: Measured default page template (easycirq/assets/page-template.json,
#: EasyEDA Pro 4.1.78 / easyeda.com, 2026-10-29).
DEFAULT_TEMPLATE = {
    "schema": PAGE_TEMPLATE_SCHEMA,
    "page": {"width": 1170, "height": 825, "margin": 10},
    "title_block": {
        "rect": {"minX": 460, "minY": 10, "maxX": 1160, "maxY": 190},
    },
}

#: Measured default halo (P90 of auto-wiring stubs/flags/labels).
DEFAULT_HALO = {"left": 22.0, "right": 22.0, "top": 16.0, "bottom": 10.0}

DEFAULT_CFG = {
    "zone_pad": 4.0,
    "edge_clearance": 0.0,
    "header_h": 20.0,
    "min_gap": 6.0,
    "target_fill": 0.62,
    "label_size": 12.0,
    "label_pad": 4.0,
}

SIDES = ("left", "right", "top", "bottom")


class LayoutBlocked(Exception):
    """A hard-rule or input problem that stops the plan before EDA."""

    def __init__(self, code: str, message: str, detail=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail

    def finding(self) -> dict:
        finding = {"code": self.code, "severity": "error",
                   "message": self.message}
        if self.detail is not None:
            finding["detail"] = self.detail
        return finding


@dataclass
class Module:
    """One layout atom: measured size + measured halo + optional affinity."""

    id: str
    title: str
    w: float
    h: float
    halo: dict
    affinity_group: str | None = None
    pinned: list | None = None


@dataclass
class _Item:
    module: Module
    zone_w: float
    zone_h: float
    affinity_index: int


@dataclass
class _Unit:
    key: tuple
    index: int
    modules: list
    area: float = 0.0


# ---------------------------------------------------------------------------
# small numeric / rectangle helpers
# ---------------------------------------------------------------------------

def _is_number(value) -> bool:
    return (isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(float(value)))


def _as_rect(value):
    """Return ``(minX, minY, maxX, maxY)`` floats, or None."""
    if isinstance(value, dict):
        keys = ("minX", "minY", "maxX", "maxY")
        if all(key in value for key in keys):
            values = [value[key] for key in keys]
        else:
            return None
    elif isinstance(value, (list, tuple)) and len(value) == 4:
        values = list(value)
    else:
        return None
    if not all(_is_number(item) for item in values):
        return None
    return tuple(float(item) for item in values)


def _rect_positive(rect) -> bool:
    return rect is not None and rect[0] < rect[2] and rect[1] < rect[3]


def _rect_area(rect) -> float:
    if rect is None:
        return 0.0
    return max(0.0, rect[2] - rect[0]) * max(0.0, rect[3] - rect[1])


def _rect_intersects(a, b) -> bool:
    if a is None or b is None:
        return False
    return (a[0] < b[2] - EPS and b[0] < a[2] - EPS
            and a[1] < b[3] - EPS and b[1] < a[3] - EPS)


def _rect_within(outer, inner) -> bool:
    if outer is None or inner is None:
        return False
    return (outer[0] <= inner[0] + EPS and outer[1] <= inner[1] + EPS
            and inner[2] <= outer[2] + EPS and inner[3] <= outer[3] + EPS)


def _rect_gap(a, b) -> float:
    """Chebyshev gap between two disjoint rectangles (0 when they touch)."""
    if a is None or b is None:
        return 0.0
    if _rect_intersects(a, b):
        return 0.0
    dx = max(b[0] - a[2], a[0] - b[2])
    dy = max(b[1] - a[3], a[1] - b[3])
    return max(dx, dy)


def _intersection(a, b):
    return (max(a[0], b[0]), max(a[1], b[1]),
            min(a[2], b[2]), min(a[3], b[3]))


def _rects_equal(a, b) -> bool:
    if a is None or b is None:
        return False
    return all(abs(a[i] - b[i]) <= 1e-6 for i in range(4))


def _pstdev(values) -> float:
    if not values:
        return 0.0
    mean = sum(values) / len(values)
    return math.sqrt(sum((value - mean) ** 2 for value in values) / len(values))


def _overlap_pairs(rects) -> int:
    count = 0
    for i in range(len(rects)):
        for j in range(i + 1, len(rects)):
            if _rect_intersects(rects[i], rects[j]):
                count += 1
    return count


# ---------------------------------------------------------------------------
# optional sibling modules (missing / broken -> internal fallback)
# ---------------------------------------------------------------------------

def _optional_module(name: str):
    """Import ``tools.layout2.<name>`` if it exists; never raise."""
    packages = []
    if __package__:
        packages.append(__package__)
    if "tools.layout2" not in packages:
        packages.append("tools.layout2")
    for package in packages:
        try:
            return importlib.import_module(f"{package}.{name}")
        except Exception:
            continue
    return None


# ---------------------------------------------------------------------------
# template
# ---------------------------------------------------------------------------

def default_template() -> dict:
    return copy.deepcopy(DEFAULT_TEMPLATE)


def _template_number(value, name: str, *, positive: bool = False) -> float:
    if not _is_number(value):
        raise LayoutBlocked("invalid_template",
                            f"template {name} must be a number")
    number = float(value)
    if number < 0 or (positive and number <= 0):
        kind = "positive" if positive else "non-negative"
        raise LayoutBlocked("invalid_template",
                            f"template {name} must be {kind}")
    return number


def _derived_regions(usable, title_block, gap: float) -> list:
    """Partition the usable area around a corner title block (hard rule 1/2)."""
    ux0, uy0, ux1, uy1 = usable
    if title_block is None:
        return [{"name": "page", "rect": usable}]
    regions = []
    # bottom-left strip (left of the title block, below its top edge)
    left_x1 = min(title_block[0] - gap, ux1)
    if left_x1 - ux0 > EPS and title_block[3] - uy0 > EPS:
        regions.append({"name": "left", "rect": (ux0, uy0, left_x1, title_block[3])})
    # full-width top strip above the title block: this is where wide modules fit
    south = max(title_block[3] + gap, uy0)
    if uy1 - south > EPS:
        regions.append({"name": "top-right", "rect": (ux0, south, ux1, uy1)})
    return regions


def _apply_edge_clearance(regions, usable, title_block, clearance: float) -> list:
    """Inset placement regions away from page edges and the title block.

    ``edge_clearance`` is the empirically needed safety band (units): blocks are
    not packed against the left/right/bottom sheet edges nor directly above the
    title block, which is where block-apply tends to shift blocks on its own.
    """
    if not clearance or clearance <= 0:
        return regions
    ux0, uy0, ux1, uy1 = usable
    out = []
    eps = 0.5
    for entry in regions:
        name = entry["name"]
        x0, y0, x1, y1 = entry["rect"]
        if x0 <= ux0 + eps:
            x0 += clearance
        if x1 >= ux1 - eps:
            x1 -= clearance
        if y0 <= uy0 + eps:
            y0 += clearance
        if title_block is not None and y0 < title_block[3] + clearance - eps \
                and x1 > title_block[0] and x0 < title_block[2]:
            y0 = title_block[3] + clearance
        if x1 - x0 > 20 and y1 - y0 > 20:
            out.append({"name": name, "rect": (x0, y0, x1, y1)})
    return out


def _explicit_regions(raw, usable, title_block) -> list:
    if not isinstance(raw, list) or not raw:
        raise LayoutBlocked("invalid_template",
                            "template.regions must be a non-empty list")
    regions = []
    for index, entry in enumerate(raw):
        if isinstance(entry, dict):
            rect = _as_rect(entry.get("rect", entry))
            name = entry.get("name")
        else:
            rect = _as_rect(entry)
            name = None
        label = name.strip() if isinstance(name, str) and name.strip() \
            else f"region-{index + 1}"
        if rect is None or not _rect_positive(rect):
            raise LayoutBlocked(
                "invalid_template",
                f"template region {label!r} must be [minX, minY, maxX, maxY]")
        if not _rect_within(usable, rect):
            raise LayoutBlocked(
                "invalid_template",
                f"template region {label!r} leaves the usable page area")
        if title_block is not None and _rect_intersects(rect, title_block):
            raise LayoutBlocked(
                "invalid_template",
                f"template region {label!r} intersects the title block")
        regions.append({"name": label, "rect": rect})
    for i in range(len(regions)):
        for j in range(i + 1, len(regions)):
            if _rect_intersects(regions[i]["rect"], regions[j]["rect"]):
                raise LayoutBlocked(
                    "invalid_template",
                    f"template regions {regions[i]['name']!r} and "
                    f"{regions[j]['name']!r} overlap")
    return regions


def normalize_template(template=None, gap: float | None = None,
                      edge_clearance: float = 0.0) -> dict:
    """Return the internal page template, or raise :class:`LayoutBlocked`."""
    gap = float(DEFAULT_CFG["min_gap"] if gap is None else gap)
    if template is None:
        template = default_template()
    if not isinstance(template, dict):
        raise LayoutBlocked("invalid_template", "template must be an object")

    page = template.get("page")
    if not isinstance(page, dict):
        raise LayoutBlocked("invalid_template",
                            "template.page must be an object")
    width = _template_number(page.get("width"), "page.width", positive=True)
    height = _template_number(page.get("height"), "page.height", positive=True)
    margin = _template_number(page.get("margin", 0), "page.margin")
    if width <= 2 * margin or height <= 2 * margin:
        raise LayoutBlocked("invalid_template",
                            "page margin leaves no usable page area")
    usable = (margin, margin, width - margin, height - margin)

    title_block = None
    raw_title_block = template.get("title_block")
    if raw_title_block is not None:
        if not isinstance(raw_title_block, dict):
            raise LayoutBlocked("invalid_template",
                                "template.title_block must be an object")
        title_block = _as_rect(raw_title_block.get("rect", raw_title_block))
        if title_block is None or not _rect_positive(title_block):
            raise LayoutBlocked(
                "invalid_template",
                "template.title_block.rect must be [minX, minY, maxX, maxY]")
        if not _rect_within((0.0, 0.0, width, height), title_block):
            raise LayoutBlocked("invalid_template",
                                "title block falls outside the page")

    raw_regions = template.get("regions")
    if raw_regions is not None:
        regions = _explicit_regions(raw_regions, usable, title_block)
    else:
        regions = _derived_regions(usable, title_block, gap)
    regions = _apply_edge_clearance(regions, usable, title_block,
                                    float(edge_clearance or 0.0))
    if not regions:
        raise LayoutBlocked("invalid_template",
                            "template has no usable region after edge_clearance")

    usable_area = _rect_area(usable)
    if title_block is not None:
        usable_area -= _rect_area(_intersection(title_block, usable))
    if usable_area <= 0:
        raise LayoutBlocked("invalid_template",
                            "template leaves no usable page area")

    return {
        "page": {"width": width, "height": height, "margin": margin},
        "title_block": ({"rect": title_block}
                        if title_block is not None else None),
        "usable": usable,
        "usable_area": usable_area,
        "regions": regions,
    }


def _as_template(template) -> dict:
    """Accept either a raw template or an already-normalized template."""
    if (isinstance(template, dict) and "usable_area" in template
            and "usable" in template):
        usable = _as_rect(template.get("usable"))
        if usable is None or not _rect_positive(usable):
            raise LayoutBlocked("invalid_template",
                                "template.usable must be a positive rectangle")
        raw_title_block = template.get("title_block")
        title_block = None
        if isinstance(raw_title_block, dict):
            title_block = _as_rect(raw_title_block.get("rect"))
        if raw_title_block is not None and title_block is None:
            raise LayoutBlocked("invalid_template",
                                "template.title_block.rect is malformed")
        raw_regions = template.get("regions")
        if not isinstance(raw_regions, list) or not raw_regions:
            raise LayoutBlocked("invalid_template",
                                "template.regions must be a non-empty list")
        regions = []
        for index, entry in enumerate(raw_regions):
            rect = _as_rect(entry.get("rect", entry)
                            if isinstance(entry, dict) else entry)
            if rect is None or not _rect_positive(rect):
                raise LayoutBlocked(
                    "invalid_template",
                    f"template region #{index + 1} is malformed")
            name = entry.get("name") if isinstance(entry, dict) else None
            if not isinstance(name, str) or not name.strip():
                name = f"region-{index + 1}"
            regions.append({"name": name.strip(), "rect": rect})
        page = template.get("page")
        return {
            "page": dict(page) if isinstance(page, dict) else {},
            "title_block": ({"rect": title_block}
                            if title_block is not None else None),
            "usable": usable,
            "usable_area": float(template["usable_area"]),
            "regions": regions,
        }
    return normalize_template(template)


def _template_echo(template: dict) -> dict:
    return {
        "schema": PAGE_TEMPLATE_SCHEMA,
        "page": dict(template["page"]),
        "title_block": ({"rect": list(template["title_block"]["rect"])}
                        if template.get("title_block") else None),
        "usable": list(template["usable"]),
        "usable_area": template["usable_area"],
        "regions": [{"name": region["name"], "rect": list(region["rect"])}
                    for region in template["regions"]],
    }


# ---------------------------------------------------------------------------
# inputs
# ---------------------------------------------------------------------------

def _resolve_cfg(project) -> dict:
    cfg = dict(DEFAULT_CFG)
    if not isinstance(project, dict):
        return cfg
    options = project.get("options")
    if options is None:
        return cfg
    if not isinstance(options, dict):
        raise LayoutBlocked("invalid_project",
                            "project.options must be an object")
    for key, value in options.items():
        if key not in DEFAULT_CFG:
            continue
        if not _is_number(value) or value < 0:
            raise LayoutBlocked(
                "invalid_project",
                f"project option {key!r} must be a non-negative number")
        cfg[key] = value
    if cfg["header_h"] <= 0:
        raise LayoutBlocked("invalid_project",
                            "project option 'header_h' must be positive")
    if not isinstance(cfg["edge_clearance"], (int, float)) or cfg["edge_clearance"] < 0:
        raise LayoutBlocked("invalid_project",
                            "project option 'edge_clearance' must be >= 0")
    if not 0 < cfg["target_fill"] <= 1:
        raise LayoutBlocked("invalid_project",
                            "project option 'target_fill' must be in (0, 1]")
    if cfg["label_size"] <= 0:
        raise LayoutBlocked("invalid_project",
                            "project option 'label_size' must be positive")
    return cfg


def _merged_cfg(cfg) -> dict:
    merged = dict(DEFAULT_CFG)
    if isinstance(cfg, dict):
        for key in DEFAULT_CFG:
            value = cfg.get(key)
            if _is_number(value) and value >= 0:
                merged[key] = value
    if merged["header_h"] <= 0:
        merged["header_h"] = DEFAULT_CFG["header_h"]
    if not 0 < merged["target_fill"] <= 1:
        merged["target_fill"] = DEFAULT_CFG["target_fill"]
    if merged["label_size"] <= 0:
        merged["label_size"] = DEFAULT_CFG["label_size"]
    return merged


def _positive_number(value, field: str, module_id: str) -> float:
    if not _is_number(value) or value <= 0:
        raise LayoutBlocked(
            "invalid_module",
            f"module {module_id!r} {field} must be a positive number",
            {"id": module_id, "field": field})
    return float(value)


def _normalize_halo(value, module_id: str) -> dict:
    if value is None:
        return dict(DEFAULT_HALO)
    if _is_number(value):
        if value < 0:
            raise LayoutBlocked(
                "invalid_module",
                f"module {module_id!r} halo must be >= 0",
                {"id": module_id, "field": "halo"})
        side = float(value)
        return {name: side for name in SIDES}
    if not isinstance(value, dict):
        raise LayoutBlocked(
            "invalid_module",
            f"module {module_id!r} halo must be a number or an object",
            {"id": module_id, "field": "halo"})
    halo = dict(DEFAULT_HALO)
    for side in SIDES:
        if side not in value:
            continue
        side_value = value[side]
        if not _is_number(side_value) or side_value < 0:
            raise LayoutBlocked(
                "invalid_module",
                f"module {module_id!r} halo.{side} must be >= 0",
                {"id": module_id, "field": f"halo.{side}"})
        halo[side] = float(side_value)
    return halo


def normalize_modules(project) -> list:
    if not isinstance(project, dict):
        raise LayoutBlocked("invalid_project",
                            "project must be a JSON object")
    raw_modules = project.get("modules")
    if not isinstance(raw_modules, list):
        raise LayoutBlocked("invalid_project",
                            "project.modules must be a list")
    if not raw_modules:
        raise LayoutBlocked("invalid_project",
                            "project.modules is empty; nothing to lay out")
    modules = []
    seen = set()
    for index, entry in enumerate(raw_modules):
        if not isinstance(entry, dict):
            raise LayoutBlocked(
                "invalid_module",
                f"module #{index} must be an object",
                {"index": index})
        module_id = entry.get("id")
        if not isinstance(module_id, str) or not module_id.strip():
            raise LayoutBlocked(
                "invalid_module",
                f"module #{index} has no usable id",
                {"index": index})
        module_id = module_id.strip()
        if module_id in seen:
            raise LayoutBlocked("duplicate_id",
                                f"duplicate module id {module_id!r}",
                                {"id": module_id})
        seen.add(module_id)
        width = _positive_number(entry.get("w"), "w", module_id)
        height = _positive_number(entry.get("h"), "h", module_id)
        title = entry.get("title", module_id)
        if not isinstance(title, str) or not title.strip():
            raise LayoutBlocked(
                "invalid_module",
                f"module {module_id!r} title must be a non-empty string",
                {"id": module_id})
        halo = _normalize_halo(entry.get("halo"), module_id)
        group = entry.get("affinity_group")
        if group is not None and (not isinstance(group, str)
                                  or not group.strip()):
            raise LayoutBlocked(
                "invalid_module",
                f"module {module_id!r} affinity_group must be a non-empty "
                "string",
                {"id": module_id})
        pinned = None
        raw_pinned = entry.get("pinned_bbox")
        if raw_pinned is not None:
            rect = _as_rect(raw_pinned)
            if rect is None or not _rect_positive(rect):
                raise LayoutBlocked(
                    "invalid_module",
                    f"module {module_id!r} pinned_bbox must be "
                    "[minX, minY, maxX, maxY]",
                    {"id": module_id})
            pinned = list(rect)
        modules.append(Module(module_id, title.strip(), width, height, halo,
                              group.strip() if group else None, pinned))
    return modules


def _unit_key(module: Module) -> tuple:
    if module.affinity_group is None:
        return ("module", module.id)
    return ("group", module.affinity_group)


def zone_size(module: Module, cfg=None):
    """Return the ``(width, height)`` of the frame zone for one module."""
    cfg = _merged_cfg(cfg)
    halo = module.halo
    pad = float(cfg["zone_pad"])
    width = halo["left"] + module.w + halo["right"] + 2 * pad
    height = (float(cfg["header_h"]) + halo["top"] + module.h
              + halo["bottom"] + 2 * pad)
    return width, height


# ---------------------------------------------------------------------------
# pagination (self-contained: area lower bound + affinity)
# ---------------------------------------------------------------------------

def _affinity_units(modules, cfg) -> list:
    units = []
    by_key = {}
    for index, module in enumerate(modules):
        key = _unit_key(module)
        unit = by_key.get(key)
        if unit is None:
            unit = _Unit(key, index, [])
            by_key[key] = unit
            units.append(unit)
        unit.modules.append(module)
        zone_w, zone_h = zone_size(module, cfg)
        unit.area += zone_w * zone_h
    return units


def paginate(modules, template, cfg=None) -> list:
    """Assign modules to pages: area lower bound, affinity groups whole."""
    cfg = _merged_cfg(cfg)
    tpl = _as_template(template)
    units = _affinity_units(modules, cfg)
    if not units:
        return []
    usable_area = float(tpl["usable_area"])
    capacity = usable_area * float(cfg["target_fill"])
    if capacity <= 0:
        capacity = usable_area
    total_area = sum(unit.area for unit in units)
    page_count = max(1, int(math.ceil(total_area / capacity - 1e-9)))
    pages = [[] for _ in range(page_count)]
    loads = [0.0] * page_count
    for unit in sorted(units, key=lambda item: (-item.area, item.index)):
        target = None
        for index in range(len(pages)):
            if loads[index] + unit.area <= capacity + 1e-6:
                if target is None or loads[index] < loads[target] - 1e-9:
                    target = index
        if target is None:
            pages.append([])
            loads.append(0.0)
            target = len(pages) - 1
        pages[target].extend(unit.modules)
        loads[target] += unit.area
    return [page for page in pages if page]


def _coerce_pages(value, modules) -> list | None:
    """Validate an external pagination result; None means 'use internal'."""
    if not isinstance(value, (list, tuple)):
        return None
    by_id = {module.id: module for module in modules}
    seen = []
    pages = []
    for page in value:
        if not isinstance(page, (list, tuple)):
            return None
        page_modules = []
        for entry in page:
            if isinstance(entry, Module):
                module_id = entry.id
            elif isinstance(entry, str):
                module_id = entry
            elif isinstance(entry, dict):
                module_id = entry.get("id")
            else:
                return None
            if module_id not in by_id:
                return None
            page_modules.append(by_id[module_id])
            seen.append(module_id)
        if page_modules:
            pages.append(page_modules)
    if len(seen) != len(by_id) or sorted(seen) != sorted(by_id):
        return None
    return pages or None


def _paginate(modules, tpl, cfg) -> list:
    external = _optional_module("pagination")
    paginate_fn = getattr(external, "paginate", None) \
        if external is not None else None
    if callable(paginate_fn):
        try:
            result = paginate_fn(list(modules), tpl, dict(cfg))
        except Exception:
            result = None
        pages = _coerce_pages(result, modules)
        if pages is not None:
            return pages
    return paginate(modules, tpl, cfg)


# ---------------------------------------------------------------------------
# zone packing (shelf into regions, halo-aware, zone capping)
# ---------------------------------------------------------------------------

def _shelf_pack(region, items, gap: float):
    x0, y0, x1, y1 = region
    width = x1 - x0
    height = y1 - y0
    placed = []
    remaining = []
    cursor_x, cursor_y, shelf_h = x0, y0, 0.0
    for item in items:
        zone_w, zone_h = item.zone_w, item.zone_h
        if zone_w > width + EPS or zone_h > height + EPS:
            remaining.append(item)
            continue
        if cursor_x + zone_w > x1 + EPS:
            cursor_y += shelf_h + gap
            cursor_x = x0
            shelf_h = 0.0
        if cursor_y + zone_h > y1 + EPS:
            remaining.append(item)
            continue
        placed.append((item, cursor_x, cursor_y))
        cursor_x += zone_w + gap
        shelf_h = max(shelf_h, zone_h)
    return placed, remaining


def _external_zone_solver(modules, tpl, cfg, items):
    external = _optional_module("zone_solver")
    solve_fn = getattr(external, "solve_page", None) \
        if external is not None else None
    if not callable(solve_fn):
        return None
    try:
        result = solve_fn(list(modules), tpl, dict(cfg))
    except Exception:
        return None
    if not isinstance(result, dict):
        return None
    raw_placements = result.get("placements")
    raw_unplaced = result.get("unplaced", [])
    if not isinstance(raw_placements, list) or not isinstance(raw_unplaced, list):
        return None
    by_id = {item.module.id: item for item in items}
    seen = set()
    placements = []
    for entry in raw_placements:
        if isinstance(entry, dict):
            module_id = entry.get("id")
            x, y = entry.get("x"), entry.get("y")
        elif isinstance(entry, (list, tuple)) and len(entry) == 3:
            module_id, x, y = entry
        else:
            return None
        if (not isinstance(module_id, str) or module_id not in by_id
                or module_id in seen):
            return None
        if not _is_number(x) or not _is_number(y):
            return None
        seen.add(module_id)
        placements.append((by_id[module_id], float(x), float(y)))
    unplaced = []
    for entry in raw_unplaced:
        module_id = entry.get("id") if isinstance(entry, dict) else entry
        if (not isinstance(module_id, str) or module_id not in by_id
                or module_id in seen):
            return None
        seen.add(module_id)
        unplaced.append(by_id[module_id])
    if len(seen) != len(by_id):
        return None
    return placements, unplaced


def _split_region(region, cut, gap: float = 0.0):
    """Partition one region into rectangles covering it minus ``cut``."""
    x0, y0, x1, y1 = region
    cx0, cy0, cx1, cy1 = cut
    pieces = []
    if cx0 > x0 + EPS:
        pieces.append((x0, y0, cx0 - gap, y1))
    if cx1 < x1 - EPS:
        pieces.append((cx1 + gap, y0, x1, y1))
    mx0, mx1 = max(x0, cx0), min(x1, cx1)
    if mx1 > mx0 + EPS:
        if cy0 > y0 + EPS:
            pieces.append((mx0, y0, mx1, cy0 - gap))
        if cy1 < y1 - EPS:
            pieces.append((mx0, cy1 + gap, mx1, y1))
    return [piece for piece in pieces
            if piece[2] - piece[0] > 20 and piece[3] - piece[1] > 20]


def _pack_page(modules, tpl, cfg):
    aff_index = {}
    for index, module in enumerate(modules):
        group = module.affinity_group
        if group is not None and group not in aff_index:
            aff_index[group] = index
    items = []
    for index, module in enumerate(modules):
        zone_w, zone_h = zone_size(module, cfg)
        group = module.affinity_group
        order = aff_index.get(group, index) if group is not None else index
        items.append(_Item(module, zone_w, zone_h, order))
    items.sort(key=lambda item: (item.affinity_index, -item.zone_h,
                                 -item.zone_w, item.module.id))
    pad = float(cfg["zone_pad"])
    pinned_placements = []
    pinned_modules = [module for module in modules if module.pinned]
    regions = [dict(region) for region in tpl["regions"]]
    for module in pinned_modules:
        zone_w, zone_h = zone_size(module, cfg)
        x = module.pinned[0] - module.halo["left"] - pad
        y = (module.pinned[1] - float(cfg["header_h"])
             - module.halo["bottom"] - pad)
        zone = (x, y, x + zone_w, y + zone_h)
        if not _rect_within(tpl["usable"], zone):
            raise LayoutBlocked(
                "pinned_outside_page",
                f"pinned module {module.id!r} zone leaves the usable page",
                {"id": module.id, "zone": zone})
        if tpl.get("title_block") is not None and _rect_intersects(
                zone, tpl["title_block"]["rect"]):
            raise LayoutBlocked(
                "pinned_title_block",
                f"pinned module {module.id!r} overlaps the title block",
                {"id": module.id, "zone": zone})
        item = _Item(module, zone_w, zone_h, 0)
        pinned_placements.append((item, x, y))
        regions = [piece for region in regions
                   for piece in _split_region(region["rect"], zone,
                                                    float(cfg["min_gap"]))]
    regular = [item for item in items if not item.module.pinned]
    external = _external_zone_solver([item.module for item in regular], tpl,
                                     cfg, regular)
    if external is not None:
        return external, []
    remaining = regular
    placements = list(pinned_placements)
    for region in tpl["regions"] if not pinned_modules else regions:
        placed, remaining = _shelf_pack(region if isinstance(region, tuple)
                                        else region["rect"], remaining,
                                        float(cfg["min_gap"]))
        placements.extend(placed)
        if not remaining:
            break
    return placements, remaining


def _layout_pages(page_modules, tpl, cfg) -> list:
    """Pack page by page; spill whole affinity units instead of splitting."""
    pending = [list(page) for page in page_modules if page]
    if not pending:
        raise LayoutBlocked("empty_layout",
                            "pagination produced no pages to pack")
    layouts = []
    guard_limit = 4 * sum(len(page) for page in pending) + 8
    guard = 0
    index = 0
    while index < len(pending):
        guard += 1
        if guard > guard_limit:
            raise LayoutBlocked("layout_no_converge",
                                "layout did not converge; refusing to loop")
        modules = pending[index]
        placements, unplaced = _pack_page(modules, tpl, cfg)
        if not unplaced:
            layouts.append(placements)
            index += 1
            continue
        bad_keys = {_unit_key(item.module) for item in unplaced}
        moved = [module for module in modules if _unit_key(module) in bad_keys]
        kept = [module for module in modules
                if _unit_key(module) not in bad_keys]
        for module in moved:
            _, still_unplaced = _pack_page([module], tpl, cfg)
            if still_unplaced:
                raise LayoutBlocked(
                    "module_does_not_fit",
                    f"module {module.id!r} does not fit any usable region",
                    {"id": module.id, "w": module.w, "h": module.h,
                     "halo": dict(module.halo)})
        if not kept:
            raise LayoutBlocked(
                "module_does_not_fit",
                "a page holds no placeable module",
                {"ids": [module.id for module in moved]})
        pending[index] = kept
        if index + 1 >= len(pending):
            pending.append([])
        pending[index + 1] = moved + pending[index + 1]
    return layouts


# ---------------------------------------------------------------------------
# text metrics + labels
# ---------------------------------------------------------------------------

_TEXT_METRICS = None

_FALLBACK_TEXT = {
    12.0: {"height": 10.12, "ascii": 6.55, "cjk": 10.34, "space": 3.6},
}


def _plausible_metrics(metrics: dict) -> bool:
    if metrics["height"] <= 0 or metrics["ascii"] <= 0:
        return False
    if metrics["space"] < 0 or metrics["space"] > metrics["ascii"]:
        return False
    ratio = metrics["cjk"] / metrics["ascii"]
    # The measured table has two outliers (sizes 6/7) where the CJK width is
    # off by an order of magnitude; ignore those rows and scale instead.
    return 1.2 <= ratio <= 2.5


def _text_sizes() -> dict:
    global _TEXT_METRICS
    if _TEXT_METRICS is not None:
        return _TEXT_METRICS
    table = {}
    try:
        raw = json.loads((ASSETS / "text-metrics.json")
                         .read_text(encoding="utf-8"))
        for key, entry in (raw.get("sizes") or {}).items():
            metrics = {
                "height": float(entry["height"]),
                "ascii": float(entry["ascii_char_w"]),
                "cjk": float(entry["cjk_char_w"]),
                "space": float(entry.get("space_w", entry["ascii_char_w"])),
            }
            if _plausible_metrics(metrics):
                table[float(key)] = metrics
    except Exception:
        table = {}
    if not table:
        table = copy.deepcopy(_FALLBACK_TEXT)
    _TEXT_METRICS = table
    return table


def _metrics_for_size(size: float) -> dict:
    size = float(size)
    table = _text_sizes()
    if size in table:
        return table[size]
    base = table.get(12.0)
    if base is None:
        base = _FALLBACK_TEXT[12.0]
    scale = size / 12.0 if size > 0 else 1.0
    return {key: value * scale for key, value in base.items()}


def _is_wide(char: str) -> bool:
    return ord(char) >= 0x2E80


def _measure_text(text: str, size: float):
    metrics = _metrics_for_size(size)
    width = 0.0
    for char in text:
        if char == " ":
            width += metrics["space"]
        elif _is_wide(char):
            width += metrics["cjk"]
        else:
            width += metrics["ascii"]
    return width, metrics["height"]


def _fit_text(text: str, size: float, max_width: float) -> str:
    if max_width <= 0 or not text:
        return ""
    if _measure_text(text, size)[0] <= max_width:
        return text
    ellipsis = "\u2026"
    ellipsis_w = _measure_text(ellipsis, size)[0]
    if ellipsis_w > max_width:
        return ""
    kept = ""
    for char in text:
        candidate = kept + char
        if _measure_text(candidate, size)[0] + ellipsis_w > max_width:
            break
        kept = candidate
    return (kept + ellipsis) if kept else ""


def _coerce_labels(value):
    if not isinstance(value, (list, tuple)):
        return None
    labels = []
    for entry in value:
        if not isinstance(entry, dict):
            return None
        text = entry.get("text")
        bbox = _as_rect(entry.get("bbox"))
        anchor = entry.get("anchor")
        if not isinstance(text, str) or not text:
            return None
        if bbox is None or not _rect_positive(bbox):
            return None
        if not (isinstance(anchor, (list, tuple)) and len(anchor) == 2
                and all(_is_number(item) for item in anchor)):
            return None
        labels.append({"text": text, "bbox": list(bbox),
                       "anchor": [float(anchor[0]), float(anchor[1])]})
    return labels


def _internal_labels(page, cfg) -> list:
    size = float(cfg["label_size"])
    pad = float(cfg["label_pad"])
    labels = []
    for frame in page["frames"]:
        zone = frame["zone"]
        max_width = (zone[2] - zone[0]) - 2 * pad
        text = _fit_text(str(frame.get("title") or frame["id"]), size,
                         max_width)
        if not text:
            continue
        text_w, text_h = _measure_text(text, size)
        x = zone[0] + pad
        y = zone[1] + pad
        labels.append({"text": text,
                       "bbox": [x, y, x + text_w, y + text_h],
                       "anchor": [x, y],
                       "frame": frame["id"],
                       "size": size})
    return labels


def _place_labels(page, cfg) -> list:
    external = _optional_module("label_solver")
    place_fn = getattr(external, "place_labels", None) \
        if external is not None else None
    if callable(place_fn):
        try:
            result = place_fn(page, dict(cfg))
        except Exception:
            result = None
        labels = _coerce_labels(result)
        if labels is not None:
            return labels
    return _internal_labels(page, cfg)


# ---------------------------------------------------------------------------
# page assembly
# ---------------------------------------------------------------------------

def _build_page(number: int, placements, tpl, cfg, place_labels: bool) -> dict:
    pad = float(cfg["zone_pad"])
    header = float(cfg["header_h"])
    frames = []
    blocks = []
    for order, (item, x, y) in enumerate(placements, 1):
        module = item.module
        zone = [x, y, x + item.zone_w, y + item.zone_h]
        bbox = [
            x + pad + module.halo["left"],
            y + header + pad + module.halo["top"],
            x + pad + module.halo["left"] + module.w,
            y + header + pad + module.halo["top"] + module.h,
        ]
        frames.append({"id": module.id, "title": module.title,
                       "order": order, "zone": zone})
        blocks.append({"id": module.id, "frame": module.id, "bbox": bbox,
                       "zone": list(zone), "halo": dict(module.halo)})
    page = {
        "page": number,
        "regions": [{"name": region["name"], "rect": list(region["rect"])}
                    for region in tpl["regions"]],
        "frames": frames,
        "blocks": blocks,
        "labels": [],
    }
    if place_labels:
        page["labels"] = _place_labels(page, cfg)
    return page


# ---------------------------------------------------------------------------
# self-contained per-page validation
# ---------------------------------------------------------------------------

def _halo_from(value):
    """Parse a halo object; None means malformed."""
    if value is None:
        return dict(DEFAULT_HALO)
    if _is_number(value):
        if value < 0:
            return None
        side = float(value)
        return {name: side for name in SIDES}
    if not isinstance(value, dict):
        return None
    halo = {}
    for side in SIDES:
        side_value = value.get(side, DEFAULT_HALO[side])
        if not _is_number(side_value) or side_value < 0:
            return None
        halo[side] = float(side_value)
    return halo


def validate_page(page, template=None, min_gap=None) -> dict:
    """Run every v2 hard rule against one self-contained page plan."""
    try:
        tpl = _as_template(template)
    except LayoutBlocked as exc:
        return {"verdict": "blocked", "findings": [exc.finding()]}
    gap = float(DEFAULT_CFG["min_gap"] if min_gap is None else min_gap)
    findings = []

    def add(code, message, **extra):
        finding = {"code": code, "severity": "error", "message": message}
        finding.update(extra)
        findings.append(finding)

    if not isinstance(page, dict):
        add("invalid_page", "page plan must be an object")
        return {"verdict": "blocked", "findings": findings}

    usable = tpl["usable"]
    title_block = (tpl["title_block"]["rect"]
                   if tpl.get("title_block") else None)
    frames = page.get("frames") if isinstance(page.get("frames"), list) else []
    blocks = page.get("blocks") if isinstance(page.get("blocks"), list) else []
    labels = page.get("labels") if isinstance(page.get("labels"), list) else []
    if not frames:
        add("empty_page", "page has no frames")
    if not blocks:
        add("empty_page", "page has no blocks")

    zones = {}
    order = []
    for index, frame in enumerate(frames):
        if not isinstance(frame, dict):
            add("invalid_frame", f"frame #{index} must be an object",
                index=index)
            continue
        frame_id = frame.get("id")
        if not isinstance(frame_id, str) or not frame_id.strip():
            add("invalid_frame", f"frame #{index} has no usable id",
                index=index)
            continue
        frame_id = frame_id.strip()
        if frame_id in zones:
            add("duplicate_frame", f"duplicate frame id {frame_id!r}",
                id=frame_id)
            continue
        zone = _as_rect(frame.get("zone"))
        if zone is None or not _rect_positive(zone):
            add("invalid_frame",
                f"frame {frame_id!r} zone must be [minX, minY, maxX, maxY]",
                id=frame_id)
            continue
        zones[frame_id] = zone
        order.append(frame_id)
        if not _rect_within(usable, zone):
            add("zone_out_of_page",
                f"frame {frame_id!r} zone leaves the usable page area",
                id=frame_id)
        if title_block is not None and _rect_intersects(zone, title_block):
            add("title_block_hit",
                f"frame {frame_id!r} zone intersects the title block "
                "keep-out", id=frame_id)

    for i in range(len(order)):
        for j in range(i + 1, len(order)):
            first, second = zones[order[i]], zones[order[j]]
            if _rect_intersects(first, second):
                add("zone_overlap",
                    f"frames {order[i]!r} and {order[j]!r} overlap",
                    ids=[order[i], order[j]])
            elif _rect_gap(first, second) < gap - EPS:
                add("zone_min_gap",
                    f"frames {order[i]!r} and {order[j]!r} are closer "
                    "than min_gap", ids=[order[i], order[j]])

    block_rects = []
    for index, block in enumerate(blocks):
        if not isinstance(block, dict):
            add("invalid_block", f"block #{index} must be an object",
                index=index)
            continue
        block_id = block.get("id")
        if not isinstance(block_id, str) or not block_id.strip():
            add("invalid_block", f"block #{index} has no usable id",
                index=index)
            continue
        block_id = block_id.strip()
        bbox = _as_rect(block.get("bbox"))
        if bbox is None or not _rect_positive(bbox):
            add("invalid_block",
                f"block {block_id!r} bbox must be [minX, minY, maxX, maxY]",
                id=block_id)
            continue
        if any(block_id == existing for existing, _ in block_rects):
            add("duplicate_block", f"duplicate block id {block_id!r}",
                id=block_id)
            continue
        frame_id = block.get("frame") or block_id
        frame_zone = zones.get(frame_id) if isinstance(frame_id, str) else None
        block_zone = _as_rect(block.get("zone"))
        halo = _halo_from(block.get("halo"))
        if frame_zone is None:
            add("orphan_block",
                f"block {block_id!r} has no matching frame", id=block_id)
        else:
            if block_zone is not None and not _rects_equal(block_zone,
                                                           frame_zone):
                add("block_zone_mismatch",
                    f"block {block_id!r} zone differs from its frame zone",
                    id=block_id)
            if halo is None:
                add("invalid_halo",
                    f"block {block_id!r} halo is malformed", id=block_id)
            else:
                expanded = (bbox[0] - halo["left"], bbox[1] - halo["top"],
                            bbox[2] + halo["right"], bbox[3] + halo["bottom"])
                if not _rect_within(frame_zone, expanded):
                    add("halo_outside_zone",
                        f"block {block_id!r} bbox + halo exceeds its zone",
                        id=block_id)
                if not _rect_within(frame_zone, bbox):
                    add("block_outside_zone",
                        f"block {block_id!r} bbox exceeds its zone",
                        id=block_id)
        if not _rect_within(usable, bbox):
            add("block_out_of_page",
                f"block {block_id!r} bbox leaves the usable page area",
                id=block_id)
        if title_block is not None and _rect_intersects(bbox, title_block):
            add("block_title_block_hit",
                f"block {block_id!r} intersects the title block keep-out",
                id=block_id)
        block_rects.append((block_id, bbox))

    for i in range(len(block_rects)):
        for j in range(i + 1, len(block_rects)):
            (first_id, first), (second_id, second) = \
                block_rects[i], block_rects[j]
            if _rect_intersects(first, second):
                add("block_overlap",
                    f"blocks {first_id!r} and {second_id!r} overlap",
                    ids=[first_id, second_id])
            elif _rect_gap(first, second) < gap - EPS:
                add("min_gap",
                    f"blocks {first_id!r} and {second_id!r} are closer "
                    "than min_gap", ids=[first_id, second_id])

    label_rects = []
    for index, label in enumerate(labels):
        if not isinstance(label, dict):
            add("invalid_label", f"label #{index} must be an object",
                index=index)
            continue
        text = label.get("text")
        bbox = _as_rect(label.get("bbox"))
        anchor = label.get("anchor")
        if not isinstance(text, str) or not text.strip():
            add("invalid_label", f"label #{index} has no usable text",
                index=index)
            continue
        if bbox is None or not _rect_positive(bbox):
            add("invalid_label",
                f"label {text!r} bbox must be [minX, minY, maxX, maxY]",
                text=text)
            continue
        if anchor is not None and not (
                isinstance(anchor, (list, tuple)) and len(anchor) == 2
                and all(_is_number(item) for item in anchor)):
            add("invalid_label", f"label {text!r} anchor is malformed",
                text=text)
            continue
        if not _rect_within(usable, bbox):
            add("label_out_of_page",
                f"label {text!r} leaves the usable page area", text=text)
        if title_block is not None and _rect_intersects(bbox, title_block):
            add("label_on_title_block",
                f"label {text!r} intersects the title block keep-out",
                text=text)
        frame_id = label.get("frame")
        if isinstance(frame_id, str) and frame_id:
            frame_zone = zones.get(frame_id)
            if frame_zone is None:
                add("orphan_label",
                    f"label {text!r} has no matching frame", text=text)
            elif not _rect_within(frame_zone, bbox):
                add("label_outside_frame",
                    f"label {text!r} leaves frame {frame_id!r}", text=text)
            elif (bbox[0] <= frame_zone[0] + EPS
                  or bbox[1] <= frame_zone[1] + EPS
                  or bbox[2] >= frame_zone[2] - EPS
                  or bbox[3] >= frame_zone[3] - EPS):
                add("label_presses_frame",
                    f"label {text!r} touches the frame border of "
                    f"{frame_id!r}", text=text)
        label_rects.append((text, bbox))

    for i in range(len(label_rects)):
        for j in range(i + 1, len(label_rects)):
            if _rect_intersects(label_rects[i][1], label_rects[j][1]):
                add("label_collision",
                    f"labels {label_rects[i][0]!r} and "
                    f"{label_rects[j][0]!r} overlap",
                    texts=[label_rects[i][0], label_rects[j][0]])
    for text, label_rect in label_rects:
        for block_id, block_rect in block_rects:
            if _rect_intersects(label_rect, block_rect):
                add("label_on_block",
                    f"label {text!r} overlaps block {block_id!r}",
                    text=text, id=block_id)

    return {"verdict": "pass" if not findings else "blocked",
            "findings": findings}


def _validate(page, tpl, cfg) -> dict:
    external = _optional_module("hard_rules")
    validate_fn = getattr(external, "validate_page", None) \
        if external is not None else None
    if callable(validate_fn):
        try:
            result = validate_fn(page, tpl, dict(cfg))
        except Exception:
            result = None
        if (isinstance(result, dict)
                and result.get("verdict") in ("pass", "blocked")
                and isinstance(result.get("findings"), list)):
            return result
    return validate_page(page, tpl, cfg["min_gap"])


# ---------------------------------------------------------------------------
# metrics
# ---------------------------------------------------------------------------

def _empty_metrics() -> dict:
    return {
        "page_count": 0,
        "page_utilization": 0.0,
        "zone_fill": 0.0,
        "label_collisions": 0,
        "block_overlaps": 0,
        "title_block_hits": 0,
        "whitespace_balance": 0.0,
        "label_block_hits": 0,
        "zones": 0,
        "blocks": 0,
        "utilization_by_page": [],
    }


def _aggregate_metrics(pages, tpl) -> dict:
    if not pages:
        return _empty_metrics()
    usable_area = float(tpl["usable_area"])
    title_block = (tpl["title_block"]["rect"]
                   if tpl.get("title_block") else None)
    total_block_area = 0.0
    total_zone_area = 0.0
    utilizations = []
    collisions = 0
    overlaps = 0
    title_block_hits = 0
    label_block_hits = 0
    whitespace = []
    for page in pages:
        block_by_id = {}
        block_rects = []
        for block in page["blocks"]:
            bbox = _as_rect(block.get("bbox"))
            if bbox is None:
                continue
            block_by_id[block.get("id")] = bbox
            block_rects.append(bbox)
        page_block_area = sum(_rect_area(rect) for rect in block_rects)
        total_block_area += page_block_area
        utilizations.append(min(1.0, page_block_area / usable_area)
                            if usable_area else 0.0)
        for frame in page["frames"]:
            zone = _as_rect(frame.get("zone"))
            if zone is None:
                continue
            zone_area = _rect_area(zone)
            total_zone_area += zone_area
            if title_block is not None and _rect_intersects(zone,
                                                            title_block):
                title_block_hits += 1
            bbox = block_by_id.get(frame.get("id"))
            if bbox is not None and zone_area > 0:
                whitespace.append(max(0.0,
                                      1.0 - _rect_area(bbox) / zone_area))
        overlaps += _overlap_pairs(block_rects)
        label_rects = []
        for label in page["labels"]:
            bbox = _as_rect(label.get("bbox"))
            if bbox is not None:
                label_rects.append(bbox)
        collisions += _overlap_pairs(label_rects)
        for label_rect in label_rects:
            for block_rect in block_rects:
                if _rect_intersects(label_rect, block_rect):
                    label_block_hits += 1
    return {
        "page_count": len(pages),
        "page_utilization": round(sum(utilizations) / len(utilizations), 4),
        "zone_fill": (round(total_block_area / total_zone_area, 4)
                      if total_zone_area else 0.0),
        "label_collisions": collisions,
        "block_overlaps": overlaps,
        "title_block_hits": title_block_hits,
        "whitespace_balance": round(_pstdev(whitespace), 4),
        "label_block_hits": label_block_hits,
        "zones": sum(len(page["frames"]) for page in pages),
        "blocks": sum(len(page["blocks"]) for page in pages),
        "utilization_by_page": [round(value, 4) for value in utilizations],
    }


def _project_name(project) -> str:
    if isinstance(project, dict):
        for key in ("name", "id", "title"):
            value = project.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return "project"


def _blocked_result(exc: LayoutBlocked, project, template=None) -> dict:
    return {
        "schema": SCHEMA,
        "project": _project_name(project),
        "verdict": "blocked",
        "findings": [exc.finding()],
        "template": _template_echo(template) if template else None,
        "pages": [],
        "metrics": _empty_metrics(),
    }


# ---------------------------------------------------------------------------
# orchestrator
# ---------------------------------------------------------------------------

def plan_project(project, template=None, *, place_labels: bool = True) -> dict:
    """Plan one project into ``easycirq-sch-layout-v2/v1`` page plans.

    ``project`` must be ``{"modules": [{"id", "title", "w", "h",
    "halo"?, "affinity_group"?}, ...]}``; ``template`` overrides the measured
    default page template.  Invalid input or an unrealizable module returns a
    ``blocked`` plan instead of raising.
    """
    try:
        cfg = _resolve_cfg(project)
        tpl = normalize_template(template, cfg["min_gap"], cfg["edge_clearance"])
        modules = normalize_modules(project)
    except LayoutBlocked as exc:
        return _blocked_result(exc, project)

    try:
        page_modules = _paginate(modules, tpl, cfg)
        layouts = _layout_pages(page_modules, tpl, cfg)
        pages = [_build_page(number, placements, tpl, cfg,
                             bool(place_labels))
                 for number, placements in enumerate(layouts, 1)]
    except LayoutBlocked as exc:
        return _blocked_result(exc, project, tpl)

    findings = []
    for page in pages:
        page["validator"] = _validate(page, tpl, cfg)
        if page["validator"]["verdict"] != "pass":
            for finding in page["validator"]["findings"]:
                findings.append({"page": page["page"], **finding})
    metrics = _aggregate_metrics(pages, tpl)
    return {
        "schema": SCHEMA,
        "project": _project_name(project),
        "verdict": "pass" if not findings else "blocked",
        "template": _template_echo(tpl),
        "pages": pages,
        "findings": findings,
        "metrics": metrics,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Offline layout engine v2 (no EDA)")
    parser.add_argument("project", help="project JSON file")
    parser.add_argument("--template", help="page template JSON file")
    parser.add_argument("--no-labels", action="store_true",
                        help="skip frame title label placement")
    args = parser.parse_args(argv)
    project = json.loads(Path(args.project).read_text(encoding="utf-8"))
    template = None
    if args.template:
        template = json.loads(Path(args.template).read_text(encoding="utf-8"))
    plan = plan_project(project, template, place_labels=not args.no_labels)
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    return 0 if plan["verdict"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
