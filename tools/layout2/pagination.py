#!/usr/bin/env python3
"""Deterministic offline pagination planner for schematic layout engine v2.

Implements ``easycirq-sch-pagination/v1`` (see
``docs/method/layout-engine-v2-contract.md`` §5).  The planner is fully
offline: it only reads module sizes and a page template and never talks to
EDA.

Input document::

    {"modules": [{"id": "m1", "w": 400, "h": 300, "affinity_group": "power"},
                 {"id": "m2", "w": 350, "h": 300, "affinity_group": "mcu"}],
     "page_template": {"page": {"width": 1170, "height": 825, "margin": 12},
                       "title_block": {"minX": 610, "minY": 12,
                                       "maxX": 1170, "maxY": 380}},
     "options": {"min_pages": 1, "max_pages": 8}}

The page template may also be the contract shape where ``title_block`` wraps
its rectangle (``{"rect": {...}, "provenance": ...}``), and a template without
a title block simply has no keep-out.

Algorithm
---------
1. Usable area = the inner page rectangle (margins removed) minus the clipped
   title-block keep-out.  The keep-out may split the page into an L-shape, so
   the usable region is kept as a list of positive-area rectangles.
2. Area lower bound ``N0 = ceil(total_module_area / usable_area)`` (>= 1).
3. Modules are clustered by ``affinity_group``.  A cluster that cannot fit a
   single page by area is split between whole modules only (a module is never
   split), and the split is reported in ``gaps``.
4. Clusters (or cluster chunks) are assigned with first-fit-decreasing into
   pages of ``usable_area`` capacity.  A page is opened whenever no existing
   page has room, so the page count grows until every module is placed.
5. ``min_pages`` pads the plan with empty pages; ``max_pages`` blocks a plan
   that would need more pages than allowed.

Output::

    {"schema": "easycirq-sch-pagination/v1",
     "pages": [{"page": 1, "modules": ["m1", "m2"], "estimated_area": 225000}],
     "page_count": 1,
     "verdict": "pass",
     "gaps": []}

``pages[].modules`` holds module ids (input order) and ``estimated_area`` is
the sum of their ``w * h``.  ``gaps`` is empty for an ideal plan and otherwise
lists structured, non-fatal relaxations (for example ``affinity_split``), or
the fatal reason(s) when ``verdict`` is ``blocked`` (for example
``module_over_page`` or ``max_pages_exceeded``).  A blocked result carries no
pages.

The ordering is deterministic: clusters are sorted by descending area, ties
by affinity group key, and modules keep their input order inside a page.

CLI::

    python tools/layout2/pagination.py plan.json [--out plan.pagination.json]

Exit codes: 0 pass, 1 blocked, 2 invalid input.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

__all__ = [
    "SCHEMA",
    "VERDICT_BLOCKED",
    "VERDICT_PASS",
    "Module",
    "PageTemplate",
    "PaginationError",
    "Rect",
    "area_lower_bound",
    "main",
    "paginate",
    "parse_template",
    "plan",
    "plan_pagination",
    "usable_area",
    "usable_rects",
    "validate_plan",
]

#: Output schema id required by the layout-engine-v2 contract.
SCHEMA = "easycirq-sch-pagination/v1"

VERDICT_PASS = "pass"
VERDICT_BLOCKED = "blocked"

#: Relative tolerance used for all area/size comparisons.
_EPS = 1e-9


class PaginationError(ValueError):
    """Raised when the input document is malformed.

    This is an input error, not a planning outcome: a well-formed request that
    cannot be paginated returns ``verdict == "blocked"`` instead.
    """


def _close(a: float, b: float) -> bool:
    return abs(a - b) <= _EPS * max(1.0, abs(a), abs(b))


def _fits_within(value: float, limit: float) -> bool:
    return value <= limit + _EPS * max(1.0, abs(limit))


def _number(value: Any, field: str, *, positive: bool = False,
            non_negative: bool = False) -> float:
    """Validate and return a finite number."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PaginationError(f"{field} must be a number, got {value!r}")
    number = float(value)
    if not math.isfinite(number):
        raise PaginationError(f"{field} must be finite, got {value!r}")
    if positive and number <= 0:
        raise PaginationError(f"{field} must be > 0, got {value!r}")
    if non_negative and number < 0:
        raise PaginationError(f"{field} must be >= 0, got {value!r}")
    return number


def _clean_number(value: float) -> int | float:
    """Return an int when integral, else a 6-decimal float (JSON stable)."""
    value = round(float(value), 6)
    if value == int(value):
        return int(value)
    return value


@dataclass(frozen=True)
class Rect:
    """Axis-aligned rectangle in page units."""

    min_x: float
    min_y: float
    max_x: float
    max_y: float

    @property
    def width(self) -> float:
        return self.max_x - self.min_x

    @property
    def height(self) -> float:
        return self.max_y - self.min_y

    @property
    def area(self) -> float:
        return self.width * self.height

    def holds(self, width: float, height: float) -> bool:
        return (_fits_within(width, self.width)
                and _fits_within(height, self.height))

    def as_dict(self) -> dict[str, int | float]:
        return {"minX": _clean_number(self.min_x),
                "minY": _clean_number(self.min_y),
                "maxX": _clean_number(self.max_x),
                "maxY": _clean_number(self.max_y)}


@dataclass(frozen=True)
class Module:
    """One indivisible layout module."""

    id: str
    w: float
    h: float
    affinity_group: str | None
    index: int

    @property
    def area(self) -> float:
        return self.w * self.h

    def as_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"id": self.id,
                                "w": _clean_number(self.w),
                                "h": _clean_number(self.h)}
        if self.affinity_group is not None:
            data["affinity_group"] = self.affinity_group
        return data


@dataclass(frozen=True)
class PageTemplate:
    """Parsed page geometry, including the usable rectangles."""

    width: float
    height: float
    margin: float
    title_block: Rect | None
    inner: Rect
    usable_rects: tuple[Rect, ...]
    placement_rects: tuple[Rect, ...] = ()

    @property
    def usable_area(self) -> float:
        return sum(rect.area for rect in self.usable_rects)


# ---------------------------------------------------------------------------
# Input parsing
# ---------------------------------------------------------------------------
def _parse_title_block(raw: Any, width: float, height: float) -> Rect | None:
    if raw is None:
        return None
    if isinstance(raw, Rect):
        return raw
    if not isinstance(raw, Mapping):
        raise PaginationError("title_block must be an object or null")
    rect = raw.get("rect", raw)
    if not isinstance(rect, Mapping):
        raise PaginationError("title_block.rect must be an object")

    def coord(*names: str, default: Any = None) -> Any:
        for name in names:
            if name in rect:
                return rect[name]
        return default

    min_x = _number(coord("minX", "min_x"), "title_block.minX")
    min_y = _number(coord("minY", "min_y"), "title_block.minY")
    max_x = _number(coord("maxX", "max_x"), "title_block.maxX")
    max_y = _number(coord("maxY", "max_y"), "title_block.maxY")

    if min_x > max_x or min_y > max_y:
        raise PaginationError(
            "title_block is inverted: "
            f"({min_x}, {min_y})-({max_x}, {max_y})")
    if min_x < 0 or min_y < 0 or max_x > width or max_y > height:
        raise PaginationError(
            f"title_block ({min_x}, {min_y})-({max_x}, {max_y}) "
            f"is outside the {_clean_number(width)}x{_clean_number(height)} page")
    if _close(min_x, max_x) or _close(min_y, max_y):
        return None
    return Rect(min_x, min_y, max_x, max_y)


def parse_template(template: Any) -> PageTemplate:
    """Normalise a page-template document.

    Accepts the task shape ``{"page": {...}, "title_block": {...}}``, the
    contract shape (``title_block.rect`` plus provenance), a template without
    a title block, and a flattened page (``width``/``height``/``margin`` at the
    top level, as used by some asset files).
    """
    if isinstance(template, PageTemplate):
        return template
    if not isinstance(template, Mapping):
        raise PaginationError("page_template must be an object")

    page = template.get("page")
    if page is None:
        page = template
    if not isinstance(page, Mapping):
        raise PaginationError("page_template.page must be an object")

    width = _number(page.get("width"), "page.width", positive=True)
    height = _number(page.get("height"), "page.height", positive=True)
    margin = _number(page.get("margin", 0), "page.margin", non_negative=True)
    if width <= 2 * margin or height <= 2 * margin:
        raise PaginationError(
            f"page {_clean_number(width)}x{_clean_number(height)} with margin "
            f"{_clean_number(margin)} has no interior")

    raw_title = template.get("title_block")
    if raw_title is None:
        raw_title = page.get("title_block")
    title_block = _parse_title_block(raw_title, width, height)

    inner = Rect(margin, margin, width - margin, height - margin)
    rects = _subtract(inner, title_block) if title_block is not None else [inner]
    usable = tuple(sorted((rect for rect in rects if rect.area > _EPS),
                          key=lambda rect: (rect.min_y, rect.min_x,
                                            rect.max_y, rect.max_x)))
    strips = _placement_strips(inner, title_block)
    return PageTemplate(width=width, height=height, margin=margin,
                        title_block=title_block, inner=inner,
                        usable_rects=usable, placement_rects=strips)


def _placement_strips(inner: Rect, cut: Rect | None) -> tuple[Rect, ...]:
    """Maximal free strips used to test whether one module can fit at all.

    Unlike :func:`_subtract` these strips overlap; they are a cover of the free
    space, which is exactly what a single-rectangle fit test needs.  A module
    that fits anywhere in ``inner \\ cut`` fits one of them.
    """
    if cut is None:
        return (inner,)
    clipped = Rect(max(inner.min_x, cut.min_x), max(inner.min_y, cut.min_y),
                   min(inner.max_x, cut.max_x), min(inner.max_y, cut.max_y))
    if clipped.width <= _EPS or clipped.height <= _EPS:
        return (inner,)
    strips: list[Rect] = []
    if clipped.min_y > inner.min_y:
        strips.append(Rect(inner.min_x, inner.min_y,
                           inner.max_x, clipped.min_y))
    if clipped.max_y < inner.max_y:
        strips.append(Rect(inner.min_x, clipped.max_y,
                           inner.max_x, inner.max_y))
    if clipped.min_x > inner.min_x:
        strips.append(Rect(inner.min_x, inner.min_y,
                           clipped.min_x, inner.max_y))
    if clipped.max_x < inner.max_x:
        strips.append(Rect(clipped.max_x, inner.min_y,
                           inner.max_x, inner.max_y))
    return tuple(strips) or (inner,)


def _subtract(rect: Rect, cut: Rect) -> list[Rect]:
    """Split ``rect`` around ``cut``; returns up to four disjoint pieces."""
    x0 = max(rect.min_x, cut.min_x)
    x1 = min(rect.max_x, cut.max_x)
    y0 = max(rect.min_y, cut.min_y)
    y1 = min(rect.max_y, cut.max_y)
    if x0 >= x1 or y0 >= y1:  # no overlap (touching edges do not overlap)
        return [rect]

    pieces: list[Rect] = []
    if y0 > rect.min_y:
        pieces.append(Rect(rect.min_x, rect.min_y, rect.max_x, y0))
    if y1 < rect.max_y:
        pieces.append(Rect(rect.min_x, y1, rect.max_x, rect.max_y))
    if x0 > rect.min_x:
        pieces.append(Rect(rect.min_x, y0, x0, y1))
    if x1 < rect.max_x:
        pieces.append(Rect(x1, y0, rect.max_x, y1))
    return pieces


def _parse_modules(modules: Any) -> list[Module]:
    if isinstance(modules, (str, bytes)) or not isinstance(modules, Sequence):
        raise PaginationError("modules must be a list")
    if all(isinstance(module, Module) for module in modules):
        return list(modules)
    parsed: list[Module] = []
    seen: set[str] = set()
    for index, raw in enumerate(modules):
        if not isinstance(raw, Mapping):
            raise PaginationError(f"modules[{index}] must be an object")
        module_id = raw.get("id")
        if not isinstance(module_id, str) or not module_id.strip():
            raise PaginationError(f"modules[{index}].id must be a non-empty string")
        module_id = module_id.strip()
        if module_id in seen:
            raise PaginationError(f"duplicate module id {module_id!r}")
        seen.add(module_id)

        width = raw.get("w", raw.get("width"))
        height = raw.get("h", raw.get("height"))
        w = _number(width, f"modules[{index}].w", positive=True)
        h = _number(height, f"modules[{index}].h", positive=True)

        group = raw.get("affinity_group", raw.get("affinityGroup"))
        if group is not None:
            if not isinstance(group, str):
                raise PaginationError(
                    f"modules[{index}].affinity_group must be a string or null")
            group = group.strip() or None
        parsed.append(Module(id=module_id, w=w, h=h,
                             affinity_group=group, index=index))
    return parsed


def _parse_options(options: Any, min_pages: int | None,
                   max_pages: int | None) -> tuple[int, int | None]:
    opts: Mapping[str, Any] = {}
    if options is not None:
        if not isinstance(options, Mapping):
            raise PaginationError("options must be an object")
        opts = options
    if min_pages is None:
        min_pages = opts.get("min_pages", 1)
    if max_pages is None:
        max_pages = opts.get("max_pages")
    min_pages = _as_page_count(min_pages, "min_pages", allow_zero=True)
    if max_pages is not None:
        max_pages = _as_page_count(max_pages, "max_pages", allow_zero=False)
    if max_pages is not None and min_pages > max_pages:
        raise PaginationError(
            f"min_pages ({min_pages}) must not exceed max_pages ({max_pages})")
    return min_pages, max_pages


def _as_page_count(value: Any, field: str, *, allow_zero: bool) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise PaginationError(f"{field} must be an integer, got {value!r}")
    low = 0 if allow_zero else 1
    if value < low:
        raise PaginationError(f"{field} must be >= {low}, got {value!r}")
    return value


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------
def usable_rects(template: Any) -> tuple[Rect, ...]:
    """Return the positive-area usable rectangles of a page template."""
    return parse_template(template).usable_rects


def usable_area(template: Any) -> float:
    """Return the usable area (page minus margins minus title block)."""
    return parse_template(template).usable_area


def area_lower_bound(total_area: float, usable_page_area: float) -> int:
    """Area-only lower bound on the page count (always >= 1)."""
    if usable_page_area <= 0:
        raise PaginationError("usable page area must be positive")
    if total_area <= 0:
        return 1
    return max(1, int(math.ceil(total_area / usable_page_area - 1e-12)))


# ---------------------------------------------------------------------------
# Planning
# ---------------------------------------------------------------------------
@dataclass
class _Cluster:
    group: str | None
    modules: list[Module]
    sort_key: str

    @property
    def area(self) -> float:
        return sum(module.area for module in self.modules)

    def copy_with(self, modules: Sequence[Module]) -> "_Cluster":
        return _Cluster(self.group,
                        sorted(modules, key=lambda module: module.index),
                        self.sort_key)


def _cluster_modules(modules: Sequence[Module]) -> list[_Cluster]:
    clusters: list[_Cluster] = []
    by_group: dict[str, _Cluster] = {}
    for module in modules:
        if module.affinity_group is None:
            clusters.append(_Cluster(None, [module], f"\x00module:{module.id}"))
            continue
        cluster = by_group.get(module.affinity_group)
        if cluster is None:
            cluster = _Cluster(module.affinity_group, [],
                               f"group:{module.affinity_group}")
            by_group[module.affinity_group] = cluster
            clusters.append(cluster)
        cluster.modules.append(module)
    return clusters


def _split_cluster(cluster: _Cluster, capacity: float) -> list[_Cluster]:
    """Split a cluster that exceeds one page, only between whole modules."""
    if _fits_within(cluster.area, capacity):
        return [cluster]
    ordered = sorted(cluster.modules, key=lambda m: (-m.area, m.index))
    chunks: list[list[Module]] = []
    current: list[Module] = []
    current_area = 0.0
    for module in ordered:
        if current and not _fits_within(current_area + module.area, capacity):
            chunks.append(current)
            current, current_area = [], 0.0
        current.append(module)
        current_area += module.area
    if current:
        chunks.append(current)
    return [cluster.copy_with(chunk) for chunk in chunks]


def _blocked(gaps: list[dict[str, Any]]) -> dict[str, Any]:
    return {"schema": SCHEMA, "pages": [], "page_count": 0,
            "verdict": VERDICT_BLOCKED, "gaps": gaps}


def _gap(code: str, message: str, **fields: Any) -> dict[str, Any]:
    gap: dict[str, Any] = {"code": code}
    gap.update(fields)
    gap["message"] = message
    return gap


def _build_result(pages: Sequence[Sequence[Module]],
                  gaps: list[dict[str, Any]]) -> dict[str, Any]:
    rendered = []
    for number, page_modules in enumerate(pages, start=1):
        rendered.append({
            "page": number,
            "modules": [module.id for module in page_modules],
            "estimated_area": _clean_number(
                sum(module.area for module in page_modules)),
        })
    return {"schema": SCHEMA, "pages": rendered,
            "page_count": len(rendered), "verdict": VERDICT_PASS,
            "gaps": gaps}


def plan_pagination(modules: Any, template: Any = None, options: Any = None,
                    *, page_template: Any = None,
                    min_pages: int | None = None,
                    max_pages: int | None = None) -> dict[str, Any]:
    """Plan the page count and per-page module assignment.

    ``modules`` may be the module list, or the whole input document (then
    ``page_template``/``options`` are read from it).  ``template`` and
    ``page_template`` are aliases; a document form also accepts a flattened
    template.  Returns the ``easycirq-sch-pagination/v1`` result object.
    """
    if template is not None and page_template is not None \
            and template is not page_template:
        raise PaginationError("pass template or page_template, not both")
    if template is None:
        template = page_template

    if isinstance(modules, Mapping):
        document = modules
        if "modules" not in document:
            raise PaginationError("input document must contain a modules list")
        module_list = document["modules"]
        if template is None:
            template = document.get("page_template")
            if template is None:
                template = document.get("template")
            if template is None:
                template = document
        if options is None:
            options = document.get("options")
        modules = module_list

    min_pages, max_pages = _parse_options(options, min_pages, max_pages)
    if template is None:
        raise PaginationError("page_template is required")
    page = parse_template(template)
    parsed_modules = _parse_modules(modules)

    if page.usable_area <= _EPS or not page.usable_rects:
        return _blocked([_gap(
            "no_usable_area",
            "page margins and title block leave no usable area")])

    # An indivisible module must fit one of the usable strips.
    oversized = []
    strips = page.placement_rects or page.usable_rects
    max_width = max(rect.width for rect in strips)
    max_height = max(rect.height for rect in strips)
    for module in parsed_modules:
        if not any(rect.holds(module.w, module.h) for rect in strips):
            oversized.append(_gap(
                "module_over_page",
                f"module {module.id!r} ({_clean_number(module.w)}x"
                f"{_clean_number(module.h)}) cannot fit any usable page region "
                f"(at most {_clean_number(max_width)}x{_clean_number(max_height)})",
                module=module.id,
                w=_clean_number(module.w),
                h=_clean_number(module.h),
                max_usable_width=_clean_number(max_width),
                max_usable_height=_clean_number(max_height)))
    if oversized:
        return _blocked(oversized)

    if not parsed_modules:
        pages: list[list[Module]] = [[] for _ in range(min_pages)]
        return _build_result(pages, [])

    capacity = page.usable_area
    clusters = _cluster_modules(parsed_modules)
    chunks: list[_Cluster] = []
    for cluster in clusters:
        chunks.extend(_split_cluster(cluster, capacity))

    # First-fit decreasing over clusters/chunks; pages open until all fit.
    chunks.sort(key=lambda chunk: (-chunk.area, chunk.sort_key))
    page_modules: list[list[Module]] = []
    page_areas: list[float] = []
    for chunk in chunks:
        for index, used in enumerate(page_areas):
            if _fits_within(used + chunk.area, capacity):
                page_modules[index].extend(chunk.modules)
                page_areas[index] = used + chunk.area
                break
        else:
            page_modules.append(list(chunk.modules))
            page_areas.append(chunk.area)

    if max_pages is not None and len(page_modules) > max_pages:
        return _blocked([_gap(
            "max_pages_exceeded",
            f"layout needs {len(page_modules)} pages, max_pages is {max_pages}",
            required_pages=len(page_modules),
            max_pages=max_pages)])

    while len(page_modules) < min_pages:
        page_modules.append([])
        page_areas.append(0.0)

    # Report affinity groups that had to span pages (non-fatal planning gap).
    page_of: dict[str, int] = {}
    for number, assigned in enumerate(page_modules, start=1):
        for module in assigned:
            page_of[module.id] = number
    gaps: list[dict[str, Any]] = []
    for cluster in clusters:
        if cluster.group is None or len(cluster.modules) < 2:
            continue
        used_pages = sorted({page_of[module.id] for module in cluster.modules})
        if len(used_pages) > 1:
            gaps.append(_gap(
                "affinity_split",
                f"affinity group {cluster.group!r} spans pages "
                f"{used_pages} because it does not fit one page",
                group=cluster.group,
                pages=used_pages))

    result = _build_result(page_modules, gaps)
    issues = validate_plan(result, parsed_modules, page,
                           min_pages=min_pages, max_pages=max_pages)
    if issues:  # defensive: the algorithm above must never produce this
        return _blocked([_gap("invalid_assignment", "; ".join(issues),
                              issues=issues)])
    return result


# Friendly aliases for callers that prefer a short or verb-style name.
paginate = plan_pagination


def plan(modules: Any, template: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Alias of :func:`plan_pagination`."""
    return plan_pagination(modules, template, **kwargs)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def validate_plan(result: Any, modules: Any = None, template: Any = None, *,
                  min_pages: int | None = None,
                  max_pages: int | None = None) -> list[str]:
    """Check a pagination result; returns a list of human-readable issues.

    Checks the output contract (schema, page numbering, ``page_count``), that
    every module appears exactly once, that page areas are consistent with the
    module sizes and fit the usable page area, and the page-count limits.
    """
    issues: list[str] = []
    if not isinstance(result, Mapping):
        return ["result must be an object"]
    if result.get("schema") != SCHEMA:
        issues.append(f"schema must be {SCHEMA!r}")
    pages = result.get("pages")
    if not isinstance(pages, list):
        return issues + ["pages must be a list"]
    if result.get("page_count") != len(pages):
        issues.append("page_count does not match len(pages)")
    if result.get("verdict") not in (VERDICT_PASS, VERDICT_BLOCKED):
        issues.append("verdict must be 'pass' or 'blocked'")
    if not isinstance(result.get("gaps"), list):
        issues.append("gaps must be a list")

    module_map: dict[str, Module] | None = None
    if modules is not None:
        parsed = _parse_modules(modules)
        module_map = {module.id: module for module in parsed}

    page_area = None
    if template is not None:
        page_area = parse_template(template).usable_area

    seen: dict[str, int] = {}
    for position, entry in enumerate(pages):
        if not isinstance(entry, Mapping):
            issues.append(f"pages[{position}] must be an object")
            continue
        if entry.get("page") != position + 1:
            issues.append(f"pages[{position}].page must be {position + 1}")
        ids = entry.get("modules")
        if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
            issues.append(f"pages[{position}].modules must be a list of ids")
            continue
        area = entry.get("estimated_area")
        if isinstance(area, bool) or not isinstance(area, (int, float)):
            issues.append(f"pages[{position}].estimated_area must be a number")
        elif page_area is not None and not _fits_within(float(area), page_area):
            issues.append(
                f"pages[{position}].estimated_area {area} exceeds usable "
                f"area {_clean_number(page_area)}")
        if module_map is not None:
            expected = sum(module_map[i].area for i in ids if i in module_map)
            if isinstance(area, (int, float)) and not isinstance(area, bool) \
                    and not _close(float(area), expected):
                issues.append(
                    f"pages[{position}].estimated_area does not match its modules")
        for module_id in ids:
            if module_id in seen:
                issues.append(f"module {module_id!r} is assigned more than once")
            seen[module_id] = position + 1
            if module_map is not None and module_id not in module_map:
                issues.append(f"unknown module {module_id!r}")

    if module_map is not None:
        for module_id in module_map:
            if module_id not in seen:
                issues.append(f"module {module_id!r} is not assigned")
    if min_pages is not None and len(pages) < min_pages:
        issues.append(f"page_count {len(pages)} is below min_pages {min_pages}")
    if max_pages is not None and len(pages) > max_pages:
        issues.append(f"page_count {len(pages)} exceeds max_pages {max_pages}")
    return issues


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv: Sequence[str] | None = None) -> int:
    """Read an input document, print the pagination plan, return an exit code."""
    parser = argparse.ArgumentParser(
        description="Plan schematic page count and module assignment "
                    f"({SCHEMA}).")
    parser.add_argument("input", nargs="?", default="-",
                        help="input JSON file, or - for stdin (default)")
    parser.add_argument("--out", help="write the plan JSON to this file")
    args = parser.parse_args(argv)

    try:
        if args.input == "-":
            raw = sys.stdin.read()
        else:
            raw = Path(args.input).read_text(encoding="utf-8")
        document = json.loads(raw)
        result = plan_pagination(document)
    except (OSError, json.JSONDecodeError, PaginationError) as exc:
        gap = _gap("invalid_input", str(exc))
        result = {"schema": SCHEMA, "pages": [], "page_count": 0,
                  "verdict": VERDICT_BLOCKED, "gaps": [gap]}
        rendered = json.dumps(result, indent=2)
        if args.out:
            Path(args.out).write_text(rendered + "\n", encoding="utf-8")
        else:
            print(rendered)
        return 2

    rendered = json.dumps(result, indent=2)
    if args.out:
        Path(args.out).write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0 if result["verdict"] == VERDICT_PASS else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
