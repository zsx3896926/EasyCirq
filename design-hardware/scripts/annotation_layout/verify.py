"""K5: independent verification of an annotation plan.

This module deliberately does **not** import ``conflicts.py``.  It rebuilds the
geometric constraints from the input document with a separate brute-force
implementation, then (when available) feeds the after-layout to the existing
``sch_layout_check.py`` checker unchanged.  Both the original and the planned
findings are retained; thresholds are never edited and findings are never
dropped.
"""
from __future__ import annotations

import importlib.util
import math
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from .model import (
    SCHEMA_ID,
    TOOL_NAME,
    TOOL_VERSION,
    Annotation,
    FixedText,
    Input,
    Rect,
    canonical_sha256,
)

HARD = "hard"
SOFT = "soft"
INFO = "info"

# Planner-controllable hard findings (objects include a movable annotation id).
_OUT_OF_SCOPE_CHECKER_CODES = {
    "different_named_wires_cross",
    "different_named_wires_collinear_overlap",
    "long_wire",
    "dangling_wire_endpoint",
    "pin_multiple_nets",
    "label_anchor_off_connection",
    "label_net_mismatch",
    "label_anchor_conflict",
    "title_block_duplicate_text",
    "title_block_outside_page",
    "module_frame_outside_page",
    "module_frame_overlaps_title_block",
    "module_frames_overlap",
    "frame_member_unknown",
    "frame_membership_gap",
    "netflag_rotation_outlier",
    "netflag_text_vertical",
    "zone_reading_order",
}

_INDEPENDENT_OUT_OF_SCOPE = {
    "fixed_text_overlap",
}


# ---------------------------------------------------------------------------
# local geometry (deliberately independent of geometry.py/conflicts.py)


def _finite(value: float) -> bool:
    return type(value) in (int, float) and math.isfinite(float(value))


def _overlap(first: Rect, second: Rect) -> bool:
    return (min(first.x1, second.x1) > max(first.x0, second.x0)
            and min(first.y1, second.y1) > max(first.y0, second.y0))


def _contains(box: Rect, other: Rect) -> bool:
    return (box.x0 <= other.x0 and box.y0 <= other.y0
            and box.x1 >= other.x1 and box.y1 >= other.y1)


def _rect_distance(first: Rect, second: Rect) -> float:
    dx = max(first.x0 - second.x1, second.x0 - first.x1, 0.0)
    dy = max(first.y0 - second.y1, second.y0 - first.y1, 0.0)
    return math.hypot(dx, dy)


def _center(box: Rect) -> Tuple[float, float]:
    return ((box.x0 + box.x1) / 2.0, (box.y0 + box.y1) / 2.0)


def _segment_enters(a: Tuple[float, float], b: Tuple[float, float], box: Rect) -> bool:
    lo, hi = 0.0, 1.0
    for axis in (0, 1):
        low = box.x0 if axis == 0 else box.y0
        high = box.x1 if axis == 0 else box.y1
        delta = b[axis] - a[axis]
        if delta == 0:
            if not low < a[axis] < high:
                return False
        else:
            t0, t1 = sorted(((low - a[axis]) / delta, (high - a[axis]) / delta))
            lo, hi = max(lo, t0), min(hi, t1)
    return lo < hi and hi > 0 and lo < 1


def _point_segment(p: Tuple[float, float], a: Tuple[float, float],
                   b: Tuple[float, float]) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    if dx == 0 and dy == 0:
        return math.hypot(p[0] - a[0], p[1] - a[1])
    t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy))


def _cross(a, b, c) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _segments_cross(a, b, c, d) -> bool:
    x, y, z, w = _cross(a, b, c), _cross(a, b, d), _cross(c, d, a), _cross(c, d, b)
    return ((x < 0 < y) or (y < 0 < x)) and ((z < 0 < w) or (w < 0 < z))


def _segment_distance(a, b, c, d) -> float:
    if _segments_cross(a, b, c, d):
        return 0.0
    return min(_point_segment(a, c, d), _point_segment(b, c, d),
               _point_segment(c, a, b), _point_segment(d, a, b))


def _rect_segment_distance(box: Rect, a, b) -> float:
    if (box.x0 <= a[0] <= box.x1 and box.y0 <= a[1] <= box.y1) or \
            (box.x0 <= b[0] <= box.x1 and box.y0 <= b[1] <= box.y1):
        return 0.0
    corners = ((box.x0, box.y0), (box.x1, box.y0), (box.x1, box.y1), (box.x0, box.y1))
    return min(_segment_distance(corners[index], corners[(index + 1) % 4], a, b)
               for index in range(4))


def _shrink(box: Rect, amount: float) -> Optional[Rect]:
    if amount <= 0:
        return box
    if box.width <= 2 * amount or box.height <= 2 * amount:
        return None
    return Rect(box.x0 + amount, box.y0 + amount, box.x1 - amount, box.y1 - amount)


# ---------------------------------------------------------------------------
# independent brute-force violations


def _violation(code: str, severity: str, objects: Sequence[str],
               annotation_ids: Sequence[str], detail: Optional[Mapping[str, Any]] = None,
               scope: Optional[str] = None) -> Dict[str, Any]:
    if scope is None:
        scope = "movable" if annotation_ids else "fixed"
    return {
        "code": code,
        "severity": severity,
        "objects": list(objects),
        "annotation_ids": list(annotation_ids),
        "scope": scope,
        "detail": dict(detail or {}),
        "source": "independent",
    }


def _annotation_set(inp: Input) -> Set[str]:
    return {ann.id for ann in inp.annotations}


def _fixed_kind(inp: Input, identity: str) -> str:
    for text in inp.fixed_texts:
        if text.id == identity:
            return text.kind
    return "unknown"


def independent_violations(inp: Input, planned_bboxes: Mapping[str, Rect]
                           ) -> List[Dict[str, Any]]:
    """Brute-force recheck; O(n^2) on purpose, no index, no reliance on solver."""
    annotations = {ann.id: ann for ann in inp.annotations}
    boxes: Dict[str, Rect] = {ann.id: ann.current.bbox for ann in inp.annotations}
    for identity, box in planned_bboxes.items():
        if identity not in annotations:
            raise ValueError(f"planned bbox for unknown annotation {identity!r}")
        boxes[identity] = box
    result: List[Dict[str, Any]] = []
    constraints = inp.constraints
    page = inp.page

    for identity in sorted(annotations):
        ann = annotations[identity]
        box = boxes[identity]
        if not _contains(page.bbox, box):
            result.append(_violation("outside_page", HARD, (identity,), (identity,),
                                     {"bbox": box.as_list()}))
        if not _contains(page.usable_bbox, box):
            result.append(_violation("outside_usable_area", HARD, (identity,), (identity,),
                                     {"bbox": box.as_list(),
                                      "usable_bbox": page.usable_bbox.as_list()}))
        if page.title_block is not None and _overlap(box, page.title_block):
            result.append(_violation("overlaps_title_block", HARD, (identity,),
                                     (identity,), {"title_block": page.title_block.as_list()}))
        for keepout in page.keepouts:
            if keepout.hard and _overlap(box, keepout.bbox):
                result.append(_violation("overlaps_keepout", HARD,
                                         (identity, keepout.id), (identity,),
                                         {"keepout": keepout.id}))
        zone = inp.zone(ann.constraints.zone_id)
        if ann.constraints.keep_in_zone and zone is not None and \
                not _contains(zone.bbox, box):
            result.append(_violation("outside_zone", HARD, (identity, zone.id),
                                     (identity,), {"zone": zone.id}))
        if ann.owner is None and ann.role in ("designator", "value"):
            result.append(_violation("owner_unknown", HARD, (identity,), (identity,),
                                     {"role": ann.role}))
        # text <-> fixed text
        for fixed in inp.fixed_texts:
            if _overlap(box, fixed.bbox):
                result.append(_violation("text_text_overlap", HARD,
                                         tuple(sorted((identity, fixed.id))),
                                         (identity,),
                                         {"fixed_kind": fixed.kind,
                                          "overlap": _extent(box, fixed.bbox)}))
            elif _rect_distance(box, fixed.bbox) <= constraints.min_text_text_gap:
                result.append(_violation("text_text_clearance", SOFT,
                                         tuple(sorted((identity, fixed.id))),
                                         (identity,),
                                         {"distance": round(_rect_distance(box, fixed.bbox), 6),
                                          "threshold": constraints.min_text_text_gap}))
        # text <-> component body
        for component in inp.components:
            own = ann.owner is not None and ann.owner.kind == "component" \
                and ann.owner.id == component.id
            if _overlap(box, component.bbox):
                extent = _extent(box, component.bbox)
                if own and min(extent) <= constraints.self_text_contact_tolerance + 1e-9:
                    result.append(_violation("symbol_text_edge_contact", INFO,
                                             tuple(sorted((identity, component.id))),
                                             (identity,),
                                             {"overlap": extent,
                                              "tolerance": constraints.self_text_contact_tolerance}))
                else:
                    result.append(_violation("text_symbol_overlap", HARD,
                                             tuple(sorted((identity, component.id))),
                                             (identity,),
                                             {"overlap": extent, "own_symbol": own}))
            elif _rect_distance(box, component.bbox) <= constraints.min_text_symbol_gap:
                result.append(_violation("text_symbol_clearance", SOFT,
                                         tuple(sorted((identity, component.id))),
                                         (identity,),
                                         {"distance": round(_rect_distance(box, component.bbox), 6),
                                          "threshold": constraints.min_text_symbol_gap}))
            if own:
                owner_center = _center(box)
                component_center = _center(component.bbox)
                distance = math.hypot(owner_center[0] - component_center[0],
                                      owner_center[1] - component_center[1])
                if distance > ann.constraints.owner_max_distance:
                    result.append(_violation("owner_too_far", HARD,
                                             (identity, component.id), (identity,),
                                             {"distance": round(distance, 6),
                                              "max_distance": ann.constraints.owner_max_distance}))
        # text <-> wires, segment by segment
        own_wire = None
        if ann.anchor_id:
            for wire in inp.wires:
                if wire.id == ann.anchor_id or wire.primitive_id == ann.anchor_id:
                    own_wire = wire.id
                    break
        for wire in inp.wires:
            for segment_index, segment in enumerate(wire.segments()):
                if _segment_enters(segment[0], segment[1], box):
                    if own_wire == wire.id:
                        inner = _shrink(box, constraints.label_own_wire_edge_tolerance)
                        if inner is not None and _segment_enters(segment[0], segment[1], inner):
                            result.append(_violation(
                                "text_wire_intrusion", HARD,
                                tuple(sorted((identity, wire.id))), (identity,),
                                {"own_wire": True, "segment_index": segment_index,
                                 "detail": "label body, not just the anchor edge"}))
                        else:
                            result.append(_violation(
                                "label_own_wire_edge_contact", INFO,
                                tuple(sorted((identity, wire.id))), (identity,),
                                {"tolerance": constraints.label_own_wire_edge_tolerance,
                                 "segment_index": segment_index}))
                    else:
                        result.append(_violation(
                            "text_wire_intrusion", HARD,
                            tuple(sorted((identity, wire.id))), (identity,),
                            {"own_wire": False, "segment_index": segment_index}))
                elif own_wire != wire.id:
                    distance = _rect_segment_distance(box, segment[0], segment[1])
                    if 0 < distance <= constraints.min_text_wire_clearance:
                        result.append(_violation(
                            "text_wire_clearance", SOFT,
                            tuple(sorted((identity, wire.id))), (identity,),
                            {"distance": round(distance, 6), "segment_index": segment_index,
                             "threshold": constraints.min_text_wire_clearance}))

    identifiers = sorted(annotations)
    for position, first in enumerate(identifiers):
        for second in identifiers[position + 1:]:
            if _overlap(boxes[first], boxes[second]):
                result.append(_violation("text_text_overlap", HARD,
                                         tuple(sorted((first, second))),
                                         (first, second),
                                         {"overlap": _extent(boxes[first], boxes[second])}))
            elif _rect_distance(boxes[first], boxes[second]) <= constraints.min_text_text_gap:
                result.append(_violation("text_text_clearance", SOFT,
                                         tuple(sorted((first, second))),
                                         (first, second),
                                         {"distance": round(_rect_distance(boxes[first],
                                                                           boxes[second]), 6),
                                          "threshold": constraints.min_text_text_gap}))
    return _dedupe(result)


def _extent(first: Rect, second: Rect) -> List[float]:
    return [round(min(first.x1, second.x1) - max(first.x0, second.x0), 6),
            round(min(first.y1, second.y1) - max(first.y0, second.y0), 6)]


def _dedupe(items: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: Set[Tuple[Any, ...]] = set()
    result: List[Dict[str, Any]] = []
    for item in items:
        key = (item["code"], tuple(item["objects"]), item["severity"])
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    result.sort(key=lambda item: (item["code"], item["objects"], item["severity"]))
    return result


# ---------------------------------------------------------------------------
# checker bridge


def checker_result(inp: Input, planned_bboxes: Mapping[str, Rect]) -> Dict[str, Any]:
    module, reason = _import_checker()
    if module is None:
        return {"status": "unavailable", "reason": reason,
                "before": None, "after": None, "limitations": [reason]}
    before_layout = build_checker_layout(inp, {ann.id: ann.current.bbox
                                               for ann in inp.annotations})
    after_layout = build_checker_layout(inp, planned_bboxes)
    try:
        before = module.analyze(before_layout, strict=False)
        after = module.analyze(after_layout, strict=False)
    except Exception as exc:  # checker refused invalid input or crashed
        return {"status": "error", "reason": f"{type(exc).__name__}: {exc}",
                "before": None, "after": None,
                "limitations": ["checker error; no acceptance claimed"]}
    return {
        "status": "ran",
        "checker": "design-hardware/scripts/sch_layout_check.py",
        "before": before,
        "after": after,
        "limitations": _checker_limitations(),
    }


def _import_checker() -> Tuple[Optional[Any], str]:
    scripts = Path(__file__).resolve().parents[1]
    checker_path = scripts / "sch_layout_check.py"
    if not checker_path.is_file():
        return None, f"checker not found at {checker_path}"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    try:
        spec = importlib.util.spec_from_file_location(
            "annotation_layout_checker_sch_layout_check", checker_path)
        if spec is None or spec.loader is None:
            return None, "checker spec could not be created"
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module, ""
    except Exception as exc:
        return None, f"checker import failed: {type(exc).__name__}: {exc}"


def _checker_limitations() -> List[str]:
    return [
        "checker skips wire intrusion/clearance for texts whose owner is a symbol id "
        "(attribute texts); the independent recheck still covers them",
        "symbol bodies are conservative rectangles, not shape-accurate outlines",
        "checker is geometric only: no rendering, no host readback, no electrical pass",
        "analysis overlay is not an official EDA export",
    ]


def build_checker_layout(inp: Input, planned_bboxes: Mapping[str, Rect]) -> Dict[str, Any]:
    texts: List[Dict[str, Any]] = []
    annotation_ids = {ann.id for ann in inp.annotations}
    for text in inp.fixed_texts:
        texts.append(text.to_checker())
    for ann in inp.annotations:
        box = planned_bboxes.get(ann.id, ann.current.bbox)
        item = ann.to_checker()
        item["bbox"] = box.as_list()
        texts.append(item)
    context = dict(inp.checker_context)
    layout: Dict[str, Any] = {
        "coordinate_units": "schematic raw units (y-up), annotation-layout/v1",
        "components": [component.to_checker() for component in inp.components],
        "texts": texts,
        "wires": [wire.to_checker() for wire in inp.wires],
        "page_bbox": inp.page.bbox.as_list(),
    }
    if inp.page.title_block is not None:
        layout["title_block"] = inp.page.title_block.as_list()
    for key in ("policy", "title_block_owned", "label_anchors", "net_flags",
                "attachment_points", "no_junction_crossings", "junction_evidence",
                "coverage", "expected_counts", "module_frames"):
        if key in context and context[key] is not None:
            layout[key] = context[key]
    if context.get("page_id") is not None:
        layout["page_id"] = context["page_id"]
    if context.get("snapshot_sha256") is not None:
        layout["snapshot_sha256"] = context["snapshot_sha256"]
    return layout


# ---------------------------------------------------------------------------
# verification result


def _finding_key(item: Mapping[str, Any]) -> Tuple[Any, ...]:
    return (item.get("code"), tuple(sorted(item.get("objects") or ())))


def _partition(before: Sequence[Mapping[str, Any]], after: Sequence[Mapping[str, Any]]
               ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    before_map: Dict[Tuple[Any, ...], Mapping[str, Any]] = {}
    for item in before:
        before_map.setdefault(_finding_key(item), item)
    after_map: Dict[Tuple[Any, ...], Mapping[str, Any]] = {}
    for item in after:
        after_map.setdefault(_finding_key(item), item)
    resolved = [dict(item) for key, item in before_map.items() if key not in after_map]
    remaining = [dict(item) for key, item in after_map.items() if key in before_map]
    introduced = [dict(item) for key, item in after_map.items() if key not in before_map]
    return resolved, remaining, introduced


def _is_hard(item: Mapping[str, Any]) -> bool:
    return item.get("severity") != SOFT and item.get("severity") != INFO


def _checker_hard_payload(result: Mapping[str, Any]) -> List[Dict[str, Any]]:
    blocking = list(result.get("blocking_findings") or [])
    for item in blocking:
        item = dict(item)
        item.setdefault("severity", HARD)
        yield item


def _checker_findings(result: Mapping[str, Any]) -> List[Dict[str, Any]]:
    return list(result.get("blocking_findings") or []) + \
        list(result.get("informational_findings") or [])


def _brief_checker(result: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(result, Mapping):
        return {}
    return {
        "status": result.get("status"),
        "counts": result.get("counts"),
        "coverage_status": result.get("coverage_status"),
        "blocking": len(result.get("blocking_findings") or []),
        "informational": len(result.get("informational_findings") or []),
        "checks_run": list(result.get("checks_run") or []),
        "checks_skipped": list(result.get("checks_skipped") or []),
    }


def verify_plan(inp: Input, planned_bboxes: Mapping[str, Rect], *,
                changes: Optional[Sequence[Mapping[str, Any]]] = None,
                scope_ids: Optional[Iterable[str]] = None) -> Dict[str, Any]:
    annotation_ids = {ann.id for ann in inp.annotations}
    scope = set(scope_ids) if scope_ids is not None else set(annotation_ids)
    constraints = inp.constraints
    before_boxes = {ann.id: ann.current.bbox for ann in inp.annotations}
    unknown_ids = {ann.id for ann in inp.annotations if ann.bbox_source == "estimated"}

    # -- input/plan binding and protection assertions ----------------------
    problems: List[str] = []
    for identity, box in planned_bboxes.items():
        if identity not in annotation_ids:
            problems.append(f"planned bbox for unknown annotation {identity!r}")
            continue
        ann = inp.annotation(identity)
        if abs(box.width - ann.current.bbox.width) > 1e-6 or \
                abs(box.height - ann.current.bbox.height) > 1e-6:
            problems.append(f"{identity}: planned bbox is not a rigid translation")
    if changes is not None:
        for change in changes:
            identity = change.get("id")
            if identity not in annotation_ids:
                problems.append(f"change for unknown annotation {identity!r}")
                continue
            ann = inp.annotation(identity)
            if change.get("content_sha256") not in (None, ann.content_sha256):
                problems.append(f"{identity}: content changed in plan")
            if change.get("after", {}).get("bbox") is not None and \
                    identity in planned_bboxes:
                if [round(value, 6) for value in change["after"]["bbox"]] != \
                        [round(value, 6) for value in planned_bboxes[identity].as_list()]:
                    problems.append(f"{identity}: plan bbox and verification bbox disagree")
            protected = change.get("protected") or {}
            for key in ("content", "net", "font_size", "rotation_deg", "align", "owner"):
                if protected.get(key) not in (None, "unchanged"):
                    problems.append(f"{identity}: protected field {key} was not asserted unchanged")
    if problems:
        return {
            "status": "verify_invalid",
            "errors": problems,
            "host_execution": "not_executed",
        }

    before = independent_violations(inp, before_boxes)
    after = independent_violations(inp, planned_bboxes)
    resolved, remaining, introduced = _partition(before, after)
    hard_before = [item for item in before if _is_hard(item)]
    hard_after = [item for item in after if _is_hard(item)]
    hard_introduced = [item for item in introduced if _is_hard(item)]
    remaining_movable = [item for item in hard_after
                         if any(identity in scope
                                for identity in item.get("annotation_ids") or ())]
    introduced_movable = [item for item in hard_introduced
                          if any(identity in scope
                                 for identity in item.get("annotation_ids") or ())]

    checker = checker_result(inp, planned_bboxes)
    checker_blocking_before: List[Dict[str, Any]] = []
    checker_blocking_after: List[Dict[str, Any]] = []
    checker_resolved: List[Dict[str, Any]] = []
    checker_remaining: List[Dict[str, Any]] = []
    checker_introduced: List[Dict[str, Any]] = []
    checker_limitations: List[str] = list(checker.get("limitations") or [])
    if checker.get("status") == "ran":
        checker_blocking_before = list(_checker_hard_payload(checker["before"]))
        checker_blocking_after = list(_checker_hard_payload(checker["after"]))
        checker_resolved, checker_remaining, checker_introduced = _partition(
            checker_blocking_before, checker_blocking_after)
        checker_limitations.extend(_attribute_limitations(
            checker_blocking_after, annotation_ids))
    checker_movable_after = [item for item in checker_blocking_after
                             if _objects_hit(item, scope)]
    checker_introduced_movable = [item for item in checker_introduced
                                  if _objects_hit(item, scope)]

    # Findings that no plan can control (pre-existing wire/frame/title issues or
    # explicitly frozen annotations).
    out_of_scope = [item for item in hard_after
                    if not _objects_hit(item, scope)]
    checker_out_of_scope = [item for item in checker_blocking_after
                            if item.get("code") in _OUT_OF_SCOPE_CHECKER_CODES
                            and not _objects_hit(item, scope)]

    estimated_involved = [identity for identity in unknown_ids
                          if identity in planned_bboxes and identity in scope
                          and (any(identity in item.get("annotation_ids") or ()
                                   for item in hard_after)
                               or any(identity in item.get("annotation_ids") or ()
                                      for item in after if item.get("severity") == SOFT))]
    estimated_moved = sorted(
        identity for identity in planned_bboxes
        if identity in unknown_ids and identity in before_boxes
        and (abs(planned_bboxes[identity].x0 - before_boxes[identity].x0) > 1e-9
             or abs(planned_bboxes[identity].y0 - before_boxes[identity].y0) > 1e-9))
    status = "plan_verified"
    if introduced_movable or checker_introduced_movable:
        status = "plan_rejected"
    elif remaining_movable or checker_movable_after:
        status = "plan_not_verified"
    elif estimated_involved or estimated_moved:
        status = "candidate_needs_visual_review"
    elif checker.get("status") not in ("ran", "unavailable"):
        status = "plan_not_verified"
    elif checker.get("status") == "unavailable":
        # Independent path is clean, but no second implementation agreed.
        status = "plan_verified"

    classification: List[Dict[str, Any]] = []
    for source, resolved_items, remaining_items, introduced_items in (
            ("independent", resolved, remaining, introduced),
            ("checker", checker_resolved, checker_remaining, checker_introduced)):
        for item in introduced_items:
            classification.append(_classification(item, False, True, "introduced", source))
        for item in remaining_items:
            classification.append(_classification(item, True, True, "pre_existing", source))
        for item in resolved_items:
            classification.append(_classification(item, True, False, "resolved", source))
    for item in hard_after:
        if item not in remaining and not any(
                _finding_key(item) == _finding_key(other) for other in introduced):
            classification.append(_classification(item, False, True, "out_of_scope",
                                                  "independent"))

    electrical_unchanged = all(
        inp.annotation(change["id"]).content_sha256 == change.get("content_sha256")
        for change in (changes or ())
    ) if changes is not None else None

    summary = {
        "status": status,
        "independent": {
            "before": before,
            "after": after,
            "hard_before": len(hard_before),
            "hard_after": len(hard_after),
            "soft_before": len([item for item in before if item["severity"] == SOFT]),
            "soft_after": len([item for item in after if item["severity"] == SOFT]),
            "resolved": resolved,
            "remaining": remaining,
            "introduced": introduced,
            "remaining_movable": remaining_movable,
            "introduced_movable": introduced_movable,
            "out_of_scope": out_of_scope,
        },
        "checker": {
            "status": checker.get("status"),
            "reason": checker.get("reason"),
            "before": checker.get("before"),
            "after": checker.get("after"),
            "brief_before": _brief_checker(checker.get("before") or {}),
            "brief_after": _brief_checker(checker.get("after") or {}),
            "resolved": checker_resolved,
            "remaining": checker_remaining,
            "introduced": checker_introduced,
            "remaining_movable": checker_movable_after,
            "introduced_movable": checker_introduced_movable,
            "out_of_scope": checker_out_of_scope,
            "limitations": checker_limitations,
        },
        "classification": classification,
        "checks": {
            "annotation_count": len(annotation_ids),
            "scope_count": len(scope),
            "scope_ids": sorted(scope),
            "moved": len([identity for identity, box in planned_bboxes.items()
                          if identity in before_boxes
                          and (abs(box.x0 - before_boxes[identity].x0) > 1e-9
                               or abs(box.y0 - before_boxes[identity].y0) > 1e-9)]),
            "estimated_bbox_annotations": sorted(unknown_ids),
            "estimated_involved": sorted(estimated_involved),
            "estimated_moved": estimated_moved,
            "checker_available": checker.get("status") == "ran",
        },
        "limitations": checker_limitations,
        "host_execution": "not_executed",
        "electrical_assertion": (
            "electrically, this is a structural assertion only: this plan contains no "
            "content/net/wire/component change; host connectivity readback, save/reopen "
            "and official export are NOT RUN"),
        "electrical_unchanged": electrical_unchanged,
    }
    return summary


def _objects_hit(item: Mapping[str, Any], annotation_ids: Set[str]) -> bool:
    objects = item.get("objects") or []
    if any(identity in annotation_ids for identity in objects):
        return True
    for identity in item.get("annotation_ids") or ():
        if identity in annotation_ids:
            return True
    return False


def _classification(item: Mapping[str, Any], before_present: bool,
                    after_present: bool, cause: str, source: str) -> Dict[str, Any]:
    return {
        "code": item.get("code"),
        "objects": list(item.get("objects") or ()),
        "severity": item.get("severity", HARD),
        "before_present": before_present,
        "after_present": after_present,
        "cause": cause,
        "source": source,
    }


def _attribute_limitations(findings: Sequence[Mapping[str, Any]],
                           annotation_ids: Set[str]) -> List[str]:
    notes = []
    for item in findings:
        objects = item.get("objects") or []
        if item.get("code") == "bbox_overlap" and _objects_hit(item, annotation_ids):
            notes.append(
                "checker bbox_overlap involving a plan annotation is retained; "
                "the independent recheck is the authority for annotation-scope conflicts")
            break
    return notes
