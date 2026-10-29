"""Hard-rule validator for layout engine v2 page plans.

Implements invariants R1-R7 from
``docs/method/layout-engine-v2-contract.md`` section 0. This module is pure
standard library: no EDA calls, no daemon, no clock, no randomness and no
filesystem access. The same plan and template always produce the same
findings and metrics.

Plan shape (``easycirq-sch-layout-v2/v1``)::

    {
      "page_count": 2,                     # optional, checked against len(pages)
      "min_gap": 8,                        # optional, default 8
      "label_gap": 2,                      # optional, default 2
      "modules": ["mcu", "power"],         # optional, ids or {"id": ...}
      "pages": [
        {"page": 1,
         "frames": [{"id": "usable", "rect": [10, 10, 1160, 815]}],
         "blocks": [{"id": "mcu",
                     "bbox": [40, 220, 280, 380],
                     "zone": [20, 200, 300, 400],
                     "halo": {"left": 5, "right": 5, "top": 5, "bottom": 5}}],
         "labels": [{"id": "mcu.title", "bbox": [50, 230, 120, 240]}]}
      ]
    }

Rects may be ``{"minX": ..., "minY": ..., "maxX": ..., "maxY": ...}`` objects
or ``[minX, minY, maxX, maxY]`` lists, matching the repository-wide bbox
convention. ``frames`` may also be a mapping of ``id -> rect``.

Rules and result
----------------
R1  every frame and every block zone lies inside page minus margin.
R2  every block zone is disjoint from the title-block keep-out.
R3  every block bbox (expanded by its optional halo) lies inside its zone.
R4  block bboxes never overlap; separated blocks keep ``min_gap`` (default 8).
R5  label bboxes never overlap; separated labels keep ``label_gap`` (default 2).
R6  label bboxes never cross a frame or zone edge.
R7  every module is assigned exactly once and ``page_count`` matches pages.

``validate_page_plan`` returns ``{"verdict": "pass"|"blocked",
"findings": [{"rule", "severity", "detail", "ids"}], "metrics": {...}}``.
Any finding blocks the plan; there are no warnings.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import NamedTuple

EPS = 1e-9
ERROR = "error"
DEFAULT_MIN_GAP = 8.0
DEFAULT_LABEL_GAP = 2.0

_RECT_KEYS = ("minX", "minY", "maxX", "maxY")


class _Geometry(NamedTuple):
    page: tuple[float, float, float, float]
    usable: tuple[float, float, float, float]
    title_block: tuple[float, float, float, float] | None


class _Frame(NamedTuple):
    id: str
    rect: tuple[float, float, float, float]


class _Block(NamedTuple):
    id: str
    bbox: tuple[float, float, float, float]
    zone: tuple[float, float, float, float]
    check_rect: tuple[float, float, float, float]


class _Label(NamedTuple):
    id: str
    bbox: tuple[float, float, float, float]


# ---------------------------------------------------------------------------
# input normalisation
# ---------------------------------------------------------------------------


def _number(value, what):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("%s must be a number" % what)
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("%s must be finite" % what)
    return number


def _non_negative(value, what):
    number = _number(value, what)
    if number < 0:
        raise ValueError("%s must be >= 0" % what)
    return number


def _as_mapping(value, what):
    if not isinstance(value, Mapping):
        raise ValueError("%s must be an object" % what)
    return value


def _rect(value, what):
    """Return ``(minX, minY, maxX, maxY)`` as floats."""
    if isinstance(value, Mapping):
        if all(key in value for key in _RECT_KEYS):
            coords = tuple(_number(value[key], "%s.%s" % (what, key))
                           for key in _RECT_KEYS)
        elif all(key in value for key in ("x", "y", "w", "h")):
            x = _number(value["x"], what + ".x")
            y = _number(value["y"], what + ".y")
            width = _number(value["w"], what + ".w")
            height = _number(value["h"], what + ".h")
            if width < 0 or height < 0:
                raise ValueError("%s must have w >= 0 and h >= 0" % what)
            coords = (x, y, x + width, y + height)
        elif "rect" in value:
            return _rect(value["rect"], what + ".rect")
        elif "bbox" in value:
            return _rect(value["bbox"], what + ".bbox")
        else:
            raise ValueError(
                "%s must be a rect object with minX/minY/maxX/maxY "
                "or a [minX, minY, maxX, maxY] list" % what)
    elif isinstance(value, (list, tuple)) and len(value) == 4:
        coords = tuple(_number(item, "%s[%d]" % (what, index))
                       for index, item in enumerate(value))
    else:
        raise ValueError(
            "%s must be a rect object with minX/minY/maxX/maxY "
            "or a [minX, minY, maxX, maxY] list" % what)

    min_x, min_y, max_x, max_y = coords
    if max_x < min_x - EPS or max_y < min_y - EPS:
        raise ValueError(
            "%s must satisfy maxX >= minX and maxY >= minY" % what)
    return (min_x, min_y, max_x, max_y)


def _halo_rect(bbox, halo, what):
    """Expand ``bbox`` by a halo dict/number, or accept absolute halo bounds."""
    if halo is None:
        return bbox
    if isinstance(halo, Mapping):
        if all(key in halo for key in _RECT_KEYS):
            return _rect(halo, what)
        if "rect" in halo:
            return _rect(halo["rect"], what + ".rect")
        left = _non_negative(halo.get("left", 0), what + ".left")
        right = _non_negative(halo.get("right", 0), what + ".right")
        top = _non_negative(halo.get("top", 0), what + ".top")
        bottom = _non_negative(halo.get("bottom", 0), what + ".bottom")
        return (bbox[0] - left, bbox[1] - top,
                bbox[2] + right, bbox[3] + bottom)
    if isinstance(halo, (int, float)) and not isinstance(halo, bool):
        pad = _non_negative(halo, what)
        return (bbox[0] - pad, bbox[1] - pad, bbox[2] + pad, bbox[3] + pad)
    raise ValueError(
        "%s must be a number or an object with left/right/top/bottom" % what)


def _template_geometry(template):
    page_spec = _as_mapping(template.get("page"), "template.page")
    width = _non_negative(page_spec.get("width"), "template.page.width")
    height = _non_negative(page_spec.get("height"), "template.page.height")
    if width <= 0 or height <= 0:
        raise ValueError("template.page.width and height must be > 0")
    margin_value = page_spec.get("margin", 0)
    margin = _non_negative(margin_value, "template.page.margin")
    if margin * 2 >= width or margin * 2 >= height:
        raise ValueError("template.page.margin leaves no usable page area")

    page = (0.0, 0.0, width, height)
    usable = (margin, margin, width - margin, height - margin)

    raw_title = template.get("title_block")
    if raw_title is None:
        raw_title = template.get("titleBlock")
    title = None
    if raw_title is not None:
        title = _rect(raw_title, "template.title_block")
    return _Geometry(page=page, usable=usable, title_block=title)


def _page_label(page, index):
    raw = page.get("page")
    if raw is None:
        return str(index + 1)
    return str(raw)


def _frame_entries(raw, page_label):
    if raw is None:
        return []
    if isinstance(raw, Mapping):
        entries = []
        for key, value in raw.items():
            if isinstance(value, Mapping):
                entry = dict(value)
                entry.setdefault("id", key)
            else:
                entry = {"id": key, "rect": value}
            entries.append(entry)
        return entries
    if isinstance(raw, (list, tuple)):
        entries = []
        for item in raw:
            if isinstance(item, Mapping):
                entries.append(item)
            else:
                entries.append({"rect": item})
        return entries
    raise ValueError("page %s frames must be a list or an object" % page_label)


def _page_items(page, key, page_label):
    raw = page.get(key)
    if raw is None:
        return []
    if not isinstance(raw, (list, tuple)):
        raise ValueError("page %s %s must be a list" % (page_label, key))
    return list(raw)


def _declared_modules(plan):
    raw = plan.get("modules")
    if raw is None:
        raw = plan.get("module_ids")
    if raw is None:
        return None
    if isinstance(raw, Mapping):
        items = list(raw.keys())
    elif isinstance(raw, (list, tuple)):
        items = list(raw)
    else:
        raise ValueError("plan.modules must be a list")

    modules = []
    for index, item in enumerate(items):
        if isinstance(item, str) and item.strip():
            modules.append(item)
            continue
        if isinstance(item, Mapping):
            module_id = item.get("id")
            if isinstance(module_id, str) and module_id.strip():
                modules.append(module_id)
                continue
        raise ValueError(
            "plan.modules[%d] must be a non-empty string id or an object "
            "with an id" % index)
    return modules


# ---------------------------------------------------------------------------
# geometry
# ---------------------------------------------------------------------------


def _contains(outer, inner):
    return (outer[0] <= inner[0] + EPS
            and outer[1] <= inner[1] + EPS
            and inner[2] <= outer[2] + EPS
            and inner[3] <= outer[3] + EPS)


def _intersects(first, second):
    return (min(first[2], second[2]) - max(first[0], second[0]) > EPS
            and min(first[3], second[3]) - max(first[1], second[1]) > EPS)


def _separation(first, second):
    """Minimum Euclidean distance between two disjoint axis-aligned rects."""
    dx = max(first[0] - second[2], second[0] - first[2], 0.0)
    dy = max(first[1] - second[3], second[1] - first[3], 0.0)
    return math.hypot(dx, dy)


def _area(rect):
    return max(0.0, rect[2] - rect[0]) * max(0.0, rect[3] - rect[1])


def _round(value):
    if value is None:
        return None
    rounded = round(float(value), 6)
    return 0.0 if rounded == 0 else rounded


def _fmt(value):
    if value is None:
        return "-"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return "%.6g" % value


def _fmt_rect(rect):
    return "[%s]" % ", ".join(_fmt(value) for value in rect)


def _finding(rule, detail, ids):
    return {
        "rule": rule,
        "severity": ERROR,
        "detail": detail,
        "ids": [str(item) for item in ids],
    }


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------


def validate_page_plan(plan, template):
    """Run hard rules R1-R7 over a page plan.

    Parameters
    ----------
    plan:
        ``easycirq-sch-layout-v2/v1`` object with a ``pages`` list. Each page
        carries ``frames``, ``blocks`` and ``labels`` entries as described in
        the module docstring.
    template:
        Measured page template object (``easycirq-page-template/v1``), e.g.
        ``easycirq/assets/page-template.json`` loaded as a dict.

    Returns
    -------
    dict
        ``{"verdict": "pass"|"blocked", "findings": [...], "metrics": {...}}``.

    Raises
    ------
    ValueError
        If the plan or template is structurally malformed. Rule violations
        never raise; they are reported as blocking findings.
    """
    plan_obj = _as_mapping(plan, "plan")
    template_obj = _as_mapping(template, "template")
    geometry = _template_geometry(template_obj)

    raw_pages = plan_obj.get("pages")
    if not isinstance(raw_pages, (list, tuple)):
        raise ValueError("plan.pages must be a list of page objects")

    min_gap_value = plan_obj.get("min_gap")
    if min_gap_value is None:
        min_gap_value = plan_obj.get("minGap")
    if min_gap_value is None:
        min_gap_value = DEFAULT_MIN_GAP
    min_gap = _non_negative(min_gap_value, "plan.min_gap")

    label_gap_value = plan_obj.get("label_gap")
    if label_gap_value is None:
        label_gap_value = plan_obj.get("labelGap")
    if label_gap_value is None:
        label_gap_value = DEFAULT_LABEL_GAP
    label_gap = _non_negative(label_gap_value, "plan.label_gap")

    default_halo = plan_obj.get("halo")

    findings = []
    frames_total = 0
    zones_total = 0
    blocks_total = 0
    labels_total = 0
    frame_out_of_page = 0
    zone_out_of_page = 0
    title_block_hits = 0
    blocks_outside_zone = 0
    block_overlaps = 0
    block_gap_violations = 0
    label_collisions = 0
    label_gap_violations = 0
    label_frame_crossings = 0
    min_block_gap = None
    min_label_gap = None
    block_area_total = 0.0
    zone_area_total = 0.0
    assigned = []

    for page_index, raw_page in enumerate(raw_pages):
        page = _as_mapping(raw_page, "plan.pages[%d]" % page_index)
        page_label = _page_label(page, page_index)

        frames = []
        for frame_index, entry in enumerate(
                _frame_entries(page.get("frames"), page_label)):
            raw_id = entry.get("id")
            if raw_id is None or not str(raw_id).strip():
                frame_id = "frame-%s-%d" % (page_label, frame_index + 1)
            else:
                frame_id = str(raw_id)
            rect = _rect(entry, "page %s frame %s" % (page_label, frame_id))
            frames_total += 1
            frames.append(_Frame(id=frame_id, rect=rect))
            if not _contains(geometry.usable, rect):
                frame_out_of_page += 1
                findings.append(_finding(
                    "R1",
                    "page %s frame '%s' %s is not fully inside the "
                    "page-minus-margin area %s"
                    % (page_label, frame_id, _fmt_rect(rect),
                       _fmt_rect(geometry.usable)),
                    [frame_id]))

        blocks = []
        for block_index, raw_block in enumerate(
                _page_items(page, "blocks", page_label)):
            block = _as_mapping(
                raw_block,
                "page %s blocks[%d]" % (page_label, block_index))
            raw_id = block.get("id")
            if not isinstance(raw_id, str) or not raw_id.strip():
                raise ValueError(
                    "page %s blocks[%d] needs a non-empty string id"
                    % (page_label, block_index))
            block_id = raw_id
            bbox = _rect(
                block.get("bbox"),
                "page %s block '%s'.bbox" % (page_label, block_id))
            zone = _rect(
                block.get("zone"),
                "page %s block '%s'.zone" % (page_label, block_id))
            halo = block.get("halo", default_halo)
            check_rect = _halo_rect(
                bbox, halo,
                "page %s block '%s'.halo" % (page_label, block_id))

            blocks_total += 1
            zones_total += 1
            block_area_total += _area(bbox)
            zone_area_total += _area(zone)
            assigned.append((block_id, page_label))

            if not _contains(geometry.usable, zone):
                zone_out_of_page += 1
                findings.append(_finding(
                    "R1",
                    "page %s block '%s' zone %s is not fully inside the "
                    "page-minus-margin area %s"
                    % (page_label, block_id, _fmt_rect(zone),
                       _fmt_rect(geometry.usable)),
                    [block_id]))

            title = geometry.title_block
            if title is not None and _intersects(zone, title):
                title_block_hits += 1
                findings.append(_finding(
                    "R2",
                    "page %s block '%s' zone %s intersects the title-block "
                    "keep-out %s"
                    % (page_label, block_id, _fmt_rect(zone),
                       _fmt_rect(title)),
                    [block_id]))

            if not _contains(zone, check_rect):
                blocks_outside_zone += 1
                if check_rect != bbox:
                    detail = (
                        "page %s block '%s' bbox+halo %s (bbox %s) is not "
                        "fully inside zone %s"
                        % (page_label, block_id, _fmt_rect(check_rect),
                           _fmt_rect(bbox), _fmt_rect(zone)))
                else:
                    detail = (
                        "page %s block '%s' bbox %s is not fully inside "
                        "zone %s"
                        % (page_label, block_id, _fmt_rect(bbox),
                           _fmt_rect(zone)))
                findings.append(_finding("R3", detail, [block_id]))

            blocks.append(_Block(
                id=block_id, bbox=bbox, zone=zone, check_rect=check_rect))

        for first_index in range(len(blocks)):
            first = blocks[first_index]
            for second_index in range(first_index + 1, len(blocks)):
                second = blocks[second_index]
                if _intersects(first.bbox, second.bbox):
                    block_overlaps += 1
                    findings.append(_finding(
                        "R4",
                        "page %s blocks '%s' %s and '%s' %s overlap"
                        % (page_label, first.id, _fmt_rect(first.bbox),
                           second.id, _fmt_rect(second.bbox)),
                        [first.id, second.id]))
                    continue
                gap = _separation(first.bbox, second.bbox)
                if min_block_gap is None or gap < min_block_gap:
                    min_block_gap = gap
                if gap + EPS < min_gap:
                    block_gap_violations += 1
                    findings.append(_finding(
                        "R4",
                        "page %s blocks '%s' and '%s' are %s apart, below "
                        "min_gap %s"
                        % (page_label, first.id, second.id, _fmt(gap),
                           _fmt(min_gap)),
                        [first.id, second.id]))

        labels = []
        for label_index, raw_label in enumerate(
                _page_items(page, "labels", page_label)):
            label = _as_mapping(
                raw_label,
                "page %s labels[%d]" % (page_label, label_index))
            raw_id = label.get("id")
            if raw_id is None:
                raw_id = label.get("text")
            if raw_id is None or not str(raw_id).strip():
                label_id = "label-%s-%d" % (page_label, label_index + 1)
            else:
                label_id = str(raw_id)
            bbox = _rect(
                label.get("bbox"),
                "page %s label '%s'.bbox" % (page_label, label_id))
            labels_total += 1
            labels.append(_Label(id=label_id, bbox=bbox))

        for first_index in range(len(labels)):
            first = labels[first_index]
            for second_index in range(first_index + 1, len(labels)):
                second = labels[second_index]
                if _intersects(first.bbox, second.bbox):
                    label_collisions += 1
                    findings.append(_finding(
                        "R5",
                        "page %s labels '%s' %s and '%s' %s overlap"
                        % (page_label, first.id, _fmt_rect(first.bbox),
                           second.id, _fmt_rect(second.bbox)),
                        [first.id, second.id]))
                    continue
                gap = _separation(first.bbox, second.bbox)
                if min_label_gap is None or gap < min_label_gap:
                    min_label_gap = gap
                if gap + EPS < label_gap:
                    label_gap_violations += 1
                    findings.append(_finding(
                        "R5",
                        "page %s labels '%s' and '%s' are %s apart, below "
                        "label_gap %s"
                        % (page_label, first.id, second.id, _fmt(gap),
                           _fmt(label_gap)),
                        [first.id, second.id]))

        edges = [(frame.id, frame.rect, "frame") for frame in frames]
        edges.extend((block.id, block.zone, "zone") for block in blocks)
        for label in labels:
            crossing = None
            for edge_id, edge_rect, kind in edges:
                if _intersects(label.bbox, edge_rect) and not _contains(
                        edge_rect, label.bbox):
                    crossing = (edge_id, edge_rect, kind)
                    break
            if crossing is not None:
                label_frame_crossings += 1
                findings.append(_finding(
                    "R6",
                    "page %s label '%s' %s crosses the edge of %s '%s' %s"
                    % (page_label, label.id, _fmt_rect(label.bbox),
                       crossing[2], crossing[0], _fmt_rect(crossing[1])),
                    [label.id, crossing[0]]))

    # R7: module assignment and page count.
    assignment_errors = 0
    counts = {}
    pages_by_module = {}
    first_seen = []
    for module_id, page_label in assigned:
        if module_id not in counts:
            counts[module_id] = 0
            pages_by_module[module_id] = []
            first_seen.append(module_id)
        counts[module_id] += 1
        pages_by_module[module_id].append(page_label)

    declared = _declared_modules(plan_obj)
    if declared is not None:
        declared_counts = {}
        declared_order = []
        for module_id in declared:
            if module_id not in declared_counts:
                declared_counts[module_id] = 0
                declared_order.append(module_id)
            declared_counts[module_id] += 1
        for module_id in declared_order:
            if declared_counts[module_id] > 1:
                assignment_errors += 1
                findings.append(_finding(
                    "R7",
                    "module '%s' is declared %d times in plan.modules; each "
                    "module must be declared once"
                    % (module_id, declared_counts[module_id]),
                    [module_id]))
        for module_id in declared_order:
            count = counts.get(module_id, 0)
            if count == 0:
                assignment_errors += 1
                findings.append(_finding(
                    "R7",
                    "module '%s' from plan.modules is not assigned to any page"
                    % module_id,
                    [module_id]))
            elif count > 1:
                assignment_errors += 1
                findings.append(_finding(
                    "R7",
                    "module '%s' is assigned %d times (pages: %s); each "
                    "module must appear exactly once"
                    % (module_id, count, ", ".join(pages_by_module[module_id])),
                    [module_id]))
        declared_set = set(declared_order)
        for module_id in first_seen:
            if module_id not in declared_set:
                assignment_errors += 1
                findings.append(_finding(
                    "R7",
                    "block '%s' (pages: %s) is not declared in plan.modules"
                    % (module_id, ", ".join(pages_by_module[module_id])),
                    [module_id]))
    else:
        for module_id in first_seen:
            if counts[module_id] > 1:
                assignment_errors += 1
                findings.append(_finding(
                    "R7",
                    "module '%s' is assigned %d times (pages: %s); each "
                    "module must appear exactly once"
                    % (module_id, counts[module_id],
                       ", ".join(pages_by_module[module_id])),
                    [module_id]))

    declared_page_count = None
    raw_page_count = plan_obj.get("page_count")
    if raw_page_count is None:
        raw_page_count = plan_obj.get("pageCount")
    page_count_errors = 0
    if raw_page_count is not None:
        value = _number(raw_page_count, "plan.page_count")
        if value < 0 or not value.is_integer():
            raise ValueError("plan.page_count must be a non-negative integer")
        declared_page_count = int(value)
        if declared_page_count != len(raw_pages):
            page_count_errors += 1
            findings.append(_finding(
                "R7",
                "plan.page_count is %d but plan.pages has %d page(s)"
                % (declared_page_count, len(raw_pages)),
                []))

    findings.sort(key=lambda item: (item["rule"], item["detail"],
                                    item["ids"]))

    usable_area = _area(geometry.usable)
    page_count = len(raw_pages)
    total_usable = usable_area * page_count
    metrics = {
        "page_count": page_count,
        "declared_page_count": declared_page_count,
        "usable_area": _round(usable_area),
        "frame_count": frames_total,
        "zone_count": zones_total,
        "block_count": blocks_total,
        "label_count": labels_total,
        "min_gap": _round(min_gap),
        "label_gap": _round(label_gap),
        "page_utilization": (
            _round(block_area_total / total_usable) if total_usable > 0
            else 0.0),
        "zone_fill": (
            _round(block_area_total / zone_area_total) if zone_area_total > 0
            else 0.0),
        "out_of_page": frame_out_of_page + zone_out_of_page,
        "frame_out_of_page": frame_out_of_page,
        "zone_out_of_page": zone_out_of_page,
        "title_block_hits": title_block_hits,
        "blocks_outside_zone": blocks_outside_zone,
        "block_overlaps": block_overlaps,
        "block_gap_violations": block_gap_violations,
        "min_block_gap": _round(min_block_gap),
        "label_collisions": label_collisions,
        "label_gap_violations": label_gap_violations,
        "min_label_gap": _round(min_label_gap),
        "label_frame_crossings": label_frame_crossings,
        "module_assignment_errors": assignment_errors,
        "page_count_errors": page_count_errors,
    }
    return {
        "verdict": "blocked" if findings else "pass",
        "findings": findings,
        "metrics": metrics,
    }
