"""K1: bounded, deterministic candidate positions for movable annotations.

A candidate is a rigid translation of the measured bbox.  Rotation, alignment,
font size, content and net are preserved by construction; a position that would
need one of those changed is never generated.
"""
from __future__ import annotations

import math
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from .conflicts import Evaluator
from .model import (
    Annotation,
    Candidate,
    Counters,
    DIRECTIONS,
    Input,
    Rect,
    SearchStats,
)

_DIRECTION_ORDER = {name: index for index, name in enumerate(DIRECTIONS)}


def _allowed(dx: float, dy: float, allowed: Sequence[str]) -> bool:
    if not allowed:
        return True
    required: List[str] = []
    if dx > 0:
        required.append("right")
    elif dx < 0:
        required.append("left")
    if dy > 0:
        required.append("up")
    elif dy < 0:
        required.append("down")
    return all(direction in allowed for direction in required)


def _direction_rank(dx: float, dy: float) -> int:
    parts: List[str] = []
    if dx > 0:
        parts.append("right")
    elif dx < 0:
        parts.append("left")
    if dy > 0:
        parts.append("up")
    elif dy < 0:
        parts.append("down")
    if len(parts) == 1:
        return _DIRECTION_ORDER[parts[0]]
    if len(parts) == 2:
        return 4 + sum(_DIRECTION_ORDER[part] for part in parts)
    return 9


def _movable(ann: Annotation) -> bool:
    return ann.capability.translate != "unsupported"


def _structural_reasons(inp: Input, ann: Annotation, bbox: Rect) -> List[str]:
    """Cheap structural filters independent of other annotation positions."""
    reasons: List[str] = []
    if not inp.page.usable_bbox.contains_rect(bbox):
        reasons.append("outside usable page area")
    if inp.page.title_block is not None and bbox.intersects(inp.page.title_block):
        reasons.append("overlaps title block")
    for keepout in inp.page.keepouts:
        if keepout.hard and bbox.intersects(keepout.bbox):
            reasons.append(f"overlaps keepout {keepout.id}")
    zone = inp.zone(ann.constraints.zone_id)
    if ann.constraints.keep_in_zone and zone is not None and not zone.bbox.contains_rect(bbox):
        reasons.append(f"outside zone {zone.id}")
    if ann.owner is not None and ann.owner.kind == "component" \
            and ann.constraints.owner_max_distance > 0:
        component = inp.component(ann.owner.id)
        if component is not None:
            distance = math.hypot(bbox.center[0] - component.bbox.center[0],
                                  bbox.center[1] - component.bbox.center[1])
            if distance > ann.constraints.owner_max_distance:
                reasons.append("owner too far")
    return reasons


def _offsets(ann: Annotation, global_grid: float,
             global_max: float) -> List[Tuple[float, float, str]]:
    grid = ann.constraints.grid if ann.constraints.grid > 0 else global_grid
    if grid <= 0:
        grid = 5.0
    limit = ann.constraints.max_displacement if ann.constraints.max_displacement > 0 \
        else global_max
    if global_max > 0:
        limit = min(limit, global_max) if limit > 0 else global_max
    max_steps = max(0, int(math.floor(limit / grid + 1e-9)))
    raw: List[Tuple[float, float, str]] = [(0.0, 0.0, "current position")]
    for step in range(1, max_steps + 1):
        distance = step * grid
        for dx, dy, name in ((distance, 0.0, "right"), (-distance, 0.0, "left"),
                             (0.0, distance, "up"), (0.0, -distance, "down")):
            raw.append((dx, dy, f"{name} {distance:g} raw (grid {grid:g})"))
        # diagonal candidates stay on the same grid on both axes; the actual
        # displacement is checked against the limit before use.
        for dx, dy, name in ((distance, distance, "up-right"),
                             (-distance, distance, "up-left"),
                             (distance, -distance, "down-right"),
                             (-distance, -distance, "down-left")):
            raw.append((dx, dy, f"{name} {distance:g} raw per axis (grid {grid:g})"))
    unique: Dict[Tuple[float, float], str] = {}
    for dx, dy, note in raw:
        if math.hypot(dx, dy) > limit + 1e-9:
            continue
        if not _allowed(dx, dy, ann.constraints.allowed_directions):
            continue
        key = (round(dx, 9), round(dy, 9))
        if key not in unique:
            unique[key] = note
    ordered = sorted(unique.items(),
                     key=lambda item: (round(math.hypot(*item[0]), 9),
                                       _direction_rank(item[0][0], item[0][1]),
                                       abs(item[0][0]), abs(item[0][1]),
                                       item[0][0], item[0][1]))
    return [(dx, dy, note) for (dx, dy), note in ordered]


def generate_for(inp: Input, ann: Annotation, *,
                 counter: Optional[Counters] = None,
                 stats: Optional[SearchStats] = None,
                 frozen: Mapping[str, Rect] | None = None) -> List[Candidate]:
    """Generate and quality-order the candidate domain of one annotation."""
    if not _movable(ann):
        return []
    if ann.role not in ("designator", "value", "free_text", "purpose_text",
                        "net_label", "wire_name"):
        return []
    if ann.role in ("net_label", "wire_name") and ann.capability.translate != "supported":
        return []
    if ann.role in ("free_text", "purpose_text") and ann.bbox_source == "estimated":
        # Still generate, but the planner/verifier will require visual review.
        pass
    offsets = _offsets(ann, inp.constraints.grid, inp.constraints.max_displacement)
    if stats is not None:
        stats.candidates_possible += len(offsets)
    evaluator = Evaluator(inp, counter)
    scored: List[Tuple[int, int, float, int, Candidate]] = []
    for order, (dx, dy, note) in enumerate(offsets):
        if dx == 0 and dy == 0:
            bbox = ann.current.bbox
            rationale = (note, "current measured pose")
        else:
            bbox = ann.current.bbox.translated(dx, dy)
            reasons = _structural_reasons(inp, ann, bbox)
            if reasons:
                continue
            rationale = (note, "rigid bbox translation", "font/rotation/content/net unchanged")
        if ann.bbox_source == "estimated":
            rationale = rationale + ("measured bbox missing; visual review required",)
        violations = evaluator.static_violations(ann, bbox, frozen=frozen)
        hard = sum(1 for item in violations if item.is_hard)
        soft = sum(1 for item in violations if item.severity == "soft")
        scored.append((hard, soft, round(math.hypot(dx, dy), 9), order,
                       Candidate(ann.id, dx, dy, bbox, 0, rationale,
                                 ann.capability.translate)))
    scored.sort(key=lambda item: (item[0], item[1], item[2], item[3]))
    limit = max(1, inp.constraints.max_candidates_per_annotation)
    candidates: List[Candidate] = []
    for rank, item in enumerate(scored[:limit]):
        base = item[4]
        candidates.append(Candidate(base.annotation_id, base.dx, base.dy, base.bbox,
                                    rank, base.rationale, base.capability))
    if stats is not None:
        stats.candidates_generated += len(candidates)
        stats.candidates_truncated += max(0, len(scored) - len(candidates))
    return candidates


def generate_candidates(inp: Input, *,
                        scope_ids: Optional[Sequence[str]] = None,
                        frozen_ids: Sequence[str] = (),
                        counter: Optional[Counters] = None,
                        stats: Optional[SearchStats] = None
                        ) -> Dict[str, List[Candidate]]:
    """Generate bounded candidate domains for the selected annotations."""
    identifiers = [ann.id for ann in inp.annotations]
    if scope_ids is not None:
        wanted = set(scope_ids)
        identifiers = [identity for identity in identifiers if identity in wanted]
    frozen_set = set(frozen_ids)
    frozen_boxes = {ann.id: ann.current.bbox for ann in inp.annotations
                    if ann.id in frozen_set}
    result: Dict[str, List[Candidate]] = {}
    total = 0
    cap = max(1, inp.constraints.max_total_candidates)
    for identity in identifiers:
        if identity in frozen_set:
            continue
        ann = inp.annotation(identity)
        if not _movable(ann):
            continue
        generated = generate_for(inp, ann, counter=counter, stats=stats,
                                 frozen=frozen_boxes)
        if total >= cap:
            # Never leave a movable annotation with an empty domain: the current
            # measured pose is always a valid representation of "no move", even
            # after the global candidate budget is exhausted.
            current = [candidate for candidate in generated
                       if abs(candidate.dx) < 1e-9 and abs(candidate.dy) < 1e-9]
            result[identity] = current[:1]
            if stats is not None:
                stats.candidates_truncated += max(1, len(generated) - len(current[:1]))
            continue
        remaining = cap - total
        if len(generated) > remaining:
            generated = generated[:remaining]
            if stats is not None:
                stats.candidates_truncated += 1
        result[identity] = generated
        total += len(generated)
    return result
