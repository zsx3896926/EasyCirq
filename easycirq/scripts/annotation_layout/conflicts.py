"""Conflict evaluation for annotation positions.

This module is the solver's fast path: it answers "what is wrong with this
candidate/assignment against the fixed drawing and against other annotations".
It intentionally mirrors the conservative rules from the existing checker
(``sch_layout_check.py``) but is not the acceptance path: ``verify.py`` rebuilds
the geometry independently and also calls the existing checker unchanged.

Rule decisions (documented in docs/parallel-annotation-layout/geometry-policy.md):
* text-text overlap, text-symbol overlap, wire entering a text bbox and
  page/keepout/zone escapes are hard;
* near misses (gaps/clearance) are soft readability findings;
* a net label's own anchored wire may touch only the outer edge margin
  (``label_own_wire_edge_tolerance``); entering the shrunk bbox stays hard;
* a symbol's own text may only touch by ``self_text_contact_tolerance``;
* thresholds come from the input; this module never changes them.
"""
from __future__ import annotations

from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from .geometry import (
    centers_distance,
    collinear_overlap,
    point_point_distance,
    rect_distance,
    rect_segment_distance,
    segment_enters_rect,
    segments_cross,
    SpatialIndex,
)
from .model import (
    SCOPE_FIXED,
    SCOPE_MIXED,
    SCOPE_MOVABLE,
    SEVERITY_HARD,
    SEVERITY_INFO,
    SEVERITY_SOFT,
    Annotation,
    Candidate,
    Counters,
    Input,
    Rect,
    Violation,
    Wire,
)

HARD_CODES = frozenset({
    "outside_page",
    "outside_usable_area",
    "overlaps_title_block",
    "overlaps_keepout",
    "outside_zone",
    "text_text_overlap",
    "text_symbol_overlap",
    "text_wire_intrusion",
    "owner_too_far",
    "owner_unknown",
    "net_label_anchor_not_separable",
})

SOFT_CODES = frozenset({
    "text_text_clearance",
    "text_symbol_clearance",
    "symbol_text_edge_contact",
    "label_own_wire_edge_contact",
    "text_wire_clearance",
})


def _severity_for(code: str) -> str:
    return SEVERITY_HARD if code in HARD_CODES else SEVERITY_SOFT


def _scope(annotation_ids: Sequence[str], fixed: bool) -> str:
    if annotation_ids and fixed:
        return SCOPE_MIXED
    if annotation_ids:
        return SCOPE_MOVABLE
    return SCOPE_FIXED


def _violation(code: str, objects: Sequence[str], annotation_ids: Sequence[str],
               fixed: bool, detail: Optional[Mapping[str, object]] = None,
               severity: Optional[str] = None) -> Violation:
    return Violation(
        code=code,
        severity=severity or _severity_for(code),
        objects=tuple(objects),
        detail=detail or {},
        scope=_scope(annotation_ids, fixed),
        annotation_ids=tuple(annotation_ids),
    )


def _defused(annotation: Annotation, bbox: Rect) -> Rect:
    return bbox


class Evaluator:
    """Holds precomputed fixed geometry for fast candidate checks."""

    def __init__(self, inp: Input, counter: Optional[Counters] = None,
                 cell_size: float = 64.0):
        self.inp = inp
        self.counter = counter
        self.page = inp.page
        self.constraints = inp.constraints
        self._component_index = SpatialIndex(cell_size)
        for component in inp.components:
            self._component_index.add_rect(component.id, component.bbox)
        self._fixed_text_index = SpatialIndex(cell_size)
        for text in inp.fixed_texts:
            self._fixed_text_index.add_rect(text.id, text.bbox)
        self._wire_index = SpatialIndex(cell_size)
        self._wire_segments: Dict[str, List[Tuple[Tuple[float, float],
                                                  Tuple[float, float]]]] = {}
        for wire in inp.wires:
            self._wire_segments[wire.id] = list(wire.segments())
            for index, (a, b) in enumerate(wire.segments()):
                self._wire_index.add_segment(f"{wire.id}#{index}", a, b)

    def bump(self, name: str = "collision_checks", amount: int = 1) -> None:
        if self.counter is not None:
            self.counter.bump(name, amount)

    # -- static checks: annotation candidate vs fixed drawing -------------
    def static_violations(self, ann: Annotation, bbox: Rect,
                          frozen: Mapping[str, Rect] | None = None,
                          frozen_ids: Iterable[str] = ()) -> List[Violation]:
        out: List[Violation] = []
        constraints = self.constraints
        page = self.page
        if not page.bbox.contains_rect(bbox):
            out.append(_violation("outside_page", (ann.id,), (ann.id,), False,
                                  {"bbox": bbox.as_list()}))
        if not page.usable_bbox.contains_rect(bbox):
            out.append(_violation("outside_usable_area", (ann.id,), (ann.id,), False,
                                  {"bbox": bbox.as_list(),
                                   "usable_bbox": page.usable_bbox.as_list()}))
        if page.title_block is not None and bbox.intersects(page.title_block):
            out.append(_violation("overlaps_title_block", (ann.id,), (ann.id,), False,
                                  {"bbox": bbox.as_list(),
                                   "title_block": page.title_block.as_list()}))
        for keepout in page.keepouts:
            if keepout.hard and bbox.intersects(keepout.bbox):
                out.append(_violation("overlaps_keepout", (ann.id, keepout.id),
                                      (ann.id,), False,
                                      {"keepout": keepout.id,
                                       "bbox": bbox.as_list()}))
        zone = self.inp.zone(ann.constraints.zone_id)
        if ann.constraints.keep_in_zone and zone is not None and not \
                zone.bbox.contains_rect(bbox):
            out.append(_violation("outside_zone", (ann.id, zone.id), (ann.id,), False,
                                  {"zone": zone.id, "bbox": bbox.as_list(),
                                   "zone_bbox": zone.bbox.as_list()}))

        # text <-> fixed text
        for fixed in self._fixed_text_index.query_rect(bbox.inflated(
                max(constraints.min_text_text_gap, 0.0))):
            self.bump()
            other = _fixed_bbox(self.inp, fixed)
            if other is None:
                continue
            if bbox.intersects(other):
                out.append(_violation("text_text_overlap", tuple(sorted((ann.id, fixed))),
                                      (ann.id,), True,
                                      {"overlap": _extent(bbox, other),
                                       "fixed_kind": _fixed_kind(self.inp, fixed)}))
            elif rect_distance(bbox, other) <= constraints.min_text_text_gap:
                out.append(_violation("text_text_clearance", tuple(sorted((ann.id, fixed))),
                                      (ann.id,), True,
                                      {"distance": round(rect_distance(bbox, other), 6),
                                       "threshold": constraints.min_text_text_gap},
                                      severity=SEVERITY_SOFT))

        # text <-> frozen (movable but out-of-scope) annotations
        if frozen:
            for other_id, other_bbox in frozen.items():
                if other_id == ann.id:
                    continue
                if bbox.intersects(other_bbox):
                    out.append(_violation("text_text_overlap",
                                          tuple(sorted((ann.id, other_id))),
                                          (ann.id,), False,
                                          {"overlap": _extent(bbox, other_bbox),
                                           "frozen": True}))
                elif rect_distance(bbox, other_bbox) <= constraints.min_text_text_gap:
                    out.append(_violation("text_text_clearance",
                                          tuple(sorted((ann.id, other_id))),
                                          (ann.id,), False,
                                          {"distance": round(rect_distance(bbox, other_bbox), 6),
                                           "threshold": constraints.min_text_text_gap,
                                           "frozen": True},
                                          severity=SEVERITY_SOFT))

        # text <-> component bodies
        for component_id in self._component_index.query_rect(
                bbox.inflated(max(constraints.min_text_symbol_gap, 0.0))):
            self.bump()
            component = self.inp.component(component_id)
            if component is None:
                continue
            own = ann.owner is not None and ann.owner.kind == "component" \
                and ann.owner.id == component.id
            if bbox.intersects(component.bbox):
                extent = _extent(bbox, component.bbox)
                if own and min(extent) <= constraints.self_text_contact_tolerance + 1e-9:
                    out.append(_violation("symbol_text_edge_contact",
                                          tuple(sorted((ann.id, component.id))),
                                          (ann.id,), False,
                                          {"overlap": extent,
                                           "tolerance": constraints.self_text_contact_tolerance},
                                          severity=SEVERITY_INFO))
                else:
                    out.append(_violation("text_symbol_overlap",
                                          tuple(sorted((ann.id, component.id))),
                                          (ann.id,), True,
                                          {"overlap": extent, "own_symbol": own}))
            elif rect_distance(bbox, component.bbox) <= constraints.min_text_symbol_gap:
                out.append(_violation("text_symbol_clearance",
                                      tuple(sorted((ann.id, component.id))),
                                      (ann.id,), True,
                                      {"distance": round(rect_distance(bbox, component.bbox), 6),
                                       "threshold": constraints.min_text_symbol_gap},
                                      severity=SEVERITY_SOFT))
            if own and ann.constraints.owner_max_distance > 0:
                distance = centers_distance(bbox, component.bbox)
                if distance > ann.constraints.owner_max_distance:
                    out.append(_violation("owner_too_far", (ann.id, component.id),
                                          (ann.id,), True,
                                          {"distance": round(distance, 6),
                                           "max_distance": ann.constraints.owner_max_distance}))

        # text <-> wires (segment by segment; own anchored wire keeps only the
        # outer-edge tolerance, never a whole-wire exemption)
        ownership = _own_wire(self.inp, ann)
        margin = bbox.inflated(max(constraints.min_text_wire_clearance, 0.0) + 1e-9)
        wire_lookup = {wire.id: wire for wire in self.inp.wires}
        for key in self._wire_index.query_rect_segment(margin):
            wire_id, segment_index = _split_segment_key(key)
            wire = wire_lookup.get(wire_id)
            if wire is None:
                continue
            segments = self._wire_segments.get(wire_id, [])
            if segment_index is not None and 0 <= segment_index < len(segments):
                segments = [segments[segment_index]]
            for segment in segments:
                self.bump()
                if segment_enters_rect(segment[0], segment[1], bbox):
                    if ownership is not None and ownership == wire.id:
                        inner = _shrink(bbox, constraints.label_own_wire_edge_tolerance)
                        if inner is not None and segment_enters_rect(segment[0], segment[1],
                                                                     inner):
                            out.append(_violation(
                                "text_wire_intrusion", tuple(sorted((ann.id, wire.id))),
                                (ann.id,), True,
                                {"own_wire": True,
                                 "detail": "label body, not just the anchor edge",
                                 "segment": _segment_dict(segment)}))
                        else:
                            out.append(_violation(
                                "label_own_wire_edge_contact",
                                tuple(sorted((ann.id, wire.id))), (ann.id,), False,
                                {"tolerance": constraints.label_own_wire_edge_tolerance,
                                 "segment": _segment_dict(segment)},
                                severity=SEVERITY_INFO))
                    else:
                        out.append(_violation(
                            "text_wire_intrusion", tuple(sorted((ann.id, wire.id))),
                            (ann.id,), True,
                            {"own_wire": False, "segment": _segment_dict(segment)}))
                elif ownership is None or ownership != wire.id:
                    distance = rect_segment_distance(bbox, segment[0], segment[1])
                    if 0 < distance <= constraints.min_text_wire_clearance:
                        out.append(_violation(
                            "text_wire_clearance", tuple(sorted((ann.id, wire.id))),
                            (ann.id,), True,
                            {"distance": round(distance, 6),
                             "threshold": constraints.min_text_wire_clearance},
                            severity=SEVERITY_SOFT))
        if ann.owner is None and ann.role in ("designator", "value"):
            out.append(_violation("owner_unknown", (ann.id,), (ann.id,), False,
                                  {"role": ann.role}))
        return out

    # -- pair checks: two movable annotations -----------------------------
    def pair_violations(self, first: Annotation, first_bbox: Rect,
                        second: Annotation, second_bbox: Rect) -> List[Violation]:
        out: List[Violation] = []
        self.bump()
        if first_bbox.intersects(second_bbox):
            out.append(_violation("text_text_overlap",
                                  tuple(sorted((first.id, second.id))),
                                  (first.id, second.id), False,
                                  {"overlap": _extent(first_bbox, second_bbox)}))
        elif rect_distance(first_bbox, second_bbox) <= self.constraints.min_text_text_gap:
            out.append(_violation("text_text_clearance",
                                  tuple(sorted((first.id, second.id))),
                                  (first.id, second.id), False,
                                  {"distance": round(rect_distance(first_bbox, second_bbox), 6),
                                   "threshold": self.constraints.min_text_text_gap},
                                  severity=SEVERITY_SOFT))
        return out

    def evaluate(self, bboxes: Mapping[str, Rect],
                 mutable_ids: Optional[Iterable[str]] = None) -> List[Violation]:
        """Full evaluation over the supplied bboxes (current or planned)."""
        annotations = {ann.id: ann for ann in self.inp.annotations}
        identifiers = list(bboxes.keys())
        mutable = set(mutable_ids) if mutable_ids is not None else set(identifiers)
        frozen = {key: box for key, box in bboxes.items() if key not in mutable}
        violations: List[Violation] = []
        for key in sorted(identifiers):
            if key not in mutable:
                continue
            violations.extend(self.static_violations(annotations[key], bboxes[key],
                                                     frozen=frozen))
        for index, first_id in enumerate(sorted(identifiers)):
            if first_id not in mutable:
                continue
            for second_id in sorted(identifiers)[index + 1:]:
                if second_id not in mutable:
                    continue
                violations.extend(self.pair_violations(
                    annotations[first_id], bboxes[first_id],
                    annotations[second_id], bboxes[second_id]))
        return _dedupe(violations)


def _fixed_bbox(inp: Input, identity: str) -> Optional[Rect]:
    for text in inp.fixed_texts:
        if text.id == identity:
            return text.bbox
    return None


def _fixed_kind(inp: Input, identity: str) -> str:
    for text in inp.fixed_texts:
        if text.id == identity:
            return text.kind
    return "unknown"


def _own_wire(inp: Input, ann: Annotation) -> Optional[str]:
    if not ann.anchor_id:
        return None
    for wire in inp.wires:
        if wire.id == ann.anchor_id or wire.primitive_id == ann.anchor_id:
            return wire.id
    return None


def _bbox_near_wire(bbox: Rect, wire: Wire, clearance: float) -> bool:
    margin = bbox.inflated(max(clearance, 0.0) + 1e-9)
    for a, b in wire.segments():
        if margin.contains_point(a) or margin.contains_point(b):
            return True
        if segment_enters_rect(a, b, margin):
            return True
        if rect_segment_distance(margin, a, b) <= 0.0:
            return True
    return False


def _shrink(bbox: Rect, amount: float) -> Optional[Rect]:
    if amount <= 0:
        return bbox
    if bbox.width <= 2 * amount or bbox.height <= 2 * amount:
        return None
    return Rect(bbox.x0 + amount, bbox.y0 + amount, bbox.x1 - amount, bbox.y1 - amount)


def _extent(first: Rect, second: Rect) -> List[float]:
    width, height = first.overlap_extent(second)
    return [round(width, 6), round(height, 6)]


def _segment_dict(segment: Tuple[Tuple[float, float], Tuple[float, float]]) -> List[List[float]]:
    return [[segment[0][0], segment[0][1]], [segment[1][0], segment[1][1]]]


def _split_segment_key(key: str) -> Tuple[str, Optional[int]]:
    if "#" in key:
        wire, _, index = key.rpartition("#")
        try:
            return wire, int(index)
        except ValueError:
            return key, None
    return key, None


def _dedupe(violations: Sequence[Violation]) -> List[Violation]:
    seen: Set[Tuple[object, ...]] = set()
    result: List[Violation] = []
    for item in violations:
        key = (item.code, item.objects, item.severity)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    result.sort(key=lambda item: (item.code, item.objects, item.severity))
    return result


# ---------------------------------------------------------------------------
# public helper API used by planner/candidates/solver/benchmark


def static_violations(inp: Input, ann: Annotation, candidate: Candidate,
                      counter: Optional[Counters] = None,
                      frozen: Mapping[str, Rect] | None = None) -> List[Violation]:
    evaluator = Evaluator(inp, counter)
    return evaluator.static_violations(ann, candidate.bbox, frozen=frozen)


def pair_violations(inp: Input, first: Annotation, first_candidate: Candidate,
                    second: Annotation, second_candidate: Candidate,
                    counter: Optional[Counters] = None) -> List[Violation]:
    evaluator = Evaluator(inp, counter)
    return evaluator.pair_violations(first, first_candidate.bbox,
                                     second, second_candidate.bbox)


def evaluate_assignment(inp: Input, assignment: Mapping[str, Candidate],
                        mutable_ids: Optional[Iterable[str]] = None,
                        counter: Optional[Counters] = None) -> List[Violation]:
    bboxes: Dict[str, Rect] = {ann.id: ann.current.bbox for ann in inp.annotations}
    for key, candidate in assignment.items():
        bboxes[key] = candidate.bbox
    evaluator = Evaluator(inp, counter)
    return evaluator.evaluate(bboxes, mutable_ids=mutable_ids)


def hard_violations(violations: Iterable[Violation]) -> List[Violation]:
    return [item for item in violations if item.is_hard]


def soft_violations(violations: Iterable[Violation]) -> List[Violation]:
    return [item for item in violations if item.severity == SEVERITY_SOFT]


def conflict_edges(inp: Input, assignment: Mapping[str, Candidate],
                   mutable_ids: Optional[Iterable[str]] = None) -> List[Tuple[str, str]]:
    """Hard-conflict graph edges among mutable annotations (deterministic)."""
    violations = evaluate_assignment(inp, assignment, mutable_ids=mutable_ids)
    edges: Set[Tuple[str, str]] = set()
    for item in violations:
        if not item.is_hard or len(item.annotation_ids) != 2:
            continue
        first, second = sorted(item.annotation_ids)
        edges.add((first, second))
    return sorted(edges)


def cluster_annotations(inp: Input, assignment: Mapping[str, Candidate],
                        mutable_ids: Optional[Iterable[str]] = None,
                        expansion: Optional[float] = None
                        ) -> List[List[str]]:
    """Connected components of the hard-conflict + movement-influence graph.

    Annotations outside every component are frozen by the planner.  Components
    are built from current hard conflicts plus overlapping maximum-displacement
    envelopes, so two annotations that could newly collide are still solved
    together instead of one-by-one.
    """
    identifiers = sorted(mutable_ids if mutable_ids is not None else
                         [ann.id for ann in inp.annotations])
    identifier_set = set(identifiers)
    parent = {key: key for key in identifiers}

    def find(key: str) -> str:
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key

    def union(first: str, second: str) -> None:
        root_a, root_b = find(first), find(second)
        if root_a != root_b:
            parent[max(root_a, root_b)] = min(root_a, root_b)

    for first, second in conflict_edges(inp, assignment, identifiers):
        if first in identifier_set and second in identifier_set:
            union(first, second)

    boxes: Dict[str, Rect] = {}
    for ann in inp.annotations:
        if ann.id not in identifier_set:
            continue
        box = assignment[ann.id].bbox if ann.id in assignment else ann.current.bbox
        reach = expansion if expansion is not None else ann.constraints.max_displacement
        boxes[ann.id] = box.inflated(max(reach, 0.0))
    for index, first in enumerate(identifiers):
        for second in identifiers[index + 1:]:
            if boxes[first].intersects(boxes[second]):
                union(first, second)

    groups: Dict[str, List[str]] = {}
    for key in identifiers:
        groups.setdefault(find(key), []).append(key)
    return sorted((sorted(group) for group in groups.values()),
                  key=lambda group: (len(group), group[0]))
