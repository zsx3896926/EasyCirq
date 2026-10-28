"""Reference baseline for the benchmark: per-annotation greedy + full recheck.

This is deliberately the naive strategy the planner replaces: process movable
annotations one by one, choose the locally best candidate, then re-check the
whole page from scratch after every placement.  It has no cluster decomposition,
no incremental cache and no backtracking, so it can paint itself into a corner.

It shares the candidate domain and the conflict rules with the improved solver;
only the search strategy differs, which is what makes the benchmark a
same-input/same-domain/same-constraints comparison.
"""
from __future__ import annotations

from typing import Dict, Mapping, Optional, Sequence, Tuple

from .candidates import generate_candidates
from .conflicts import evaluate_assignment
from .model import (
    STATUS_BLOCKED,
    STATUS_NEEDS_GEOMETRY,
    STATUS_PARTIAL,
    STATUS_PLANNED_CLEAR,
    Candidate,
    Counters,
    Input,
    SearchResult,
    SearchStats,
    Violation,
)


def _hard(violations: Sequence[Violation]) -> int:
    return sum(1 for item in violations if item.is_hard)


def decide_order(scope_ids: Sequence[str]) -> list:
    """Baseline ordering: stable designator/id order, no conflict-degree sort."""
    return sorted(scope_ids)


def solve_baseline(inp: Input, *, scope_ids: Optional[Sequence[str]] = None,
                   frozen_ids: Sequence[str] = (),
                   candidates: Optional[Mapping[str, Sequence[Candidate]]] = None,
                   counter: Optional[Counters] = None) -> SearchResult:
    counters = counter if counter is not None else Counters()
    stats = SearchStats()
    frozen = set(frozen_ids) | set(inp.constraints.freeze_ids)
    mutable = [ann.id for ann in inp.annotations if ann.movable and ann.id not in frozen]
    if scope_ids is not None:
        wanted = set(scope_ids)
        mutable = [identity for identity in mutable if identity in wanted]
    elif inp.constraints.scope == "cluster":
        wanted = set(inp.constraints.scope_cluster_ids)
        mutable = [identity for identity in mutable if identity in wanted]
    mutable_set = set(mutable)
    if candidates is not None:
        domains = {identity: list(candidates.get(identity, ())) for identity in mutable}
    else:
        domains = generate_candidates(inp, scope_ids=mutable, frozen_ids=sorted(frozen),
                                      counter=counters, stats=stats)
    stats.freeze_count = len(inp.annotations) - len(mutable)

    # Start from the measured pose; a candidate domain always contains it.
    assignment: Dict[str, Candidate] = {}
    for identity in mutable:
        domain = domains.get(identity, [])
        if not domain:
            continue
        assignment[identity] = next(
            (candidate for candidate in domain
             if abs(candidate.dx) < 1e-9 and abs(candidate.dy) < 1e-9), domain[0])

    order = decide_order(mutable)
    for identity in order:
        domain = domains.get(identity, [])
        if not domain:
            stats.iterations += 1
            continue
        best = assignment[identity]
        best_cost = None
        for candidate in domain:
            trial = dict(assignment)
            trial[identity] = candidate
            violations = evaluate_assignment(inp, trial, mutable_ids=mutable_set,
                                             counter=counters)
            self_only = [item for item in violations
                         if identity in item.annotation_ids]
            cost = (_hard(self_only),
                    len([item for item in self_only if item.severity == "soft"]),
                    round(candidate.displacement, 9), candidate.rank)
            if best_cost is None or cost < best_cost:
                best_cost, best = cost, candidate
            stats.candidates_generated += 1
        assignment[identity] = best
        stats.iterations += 1
        # The baseline definition includes a full recheck after each placement.
        evaluate_assignment(inp, assignment, mutable_ids=mutable_set, counter=counters)

    final = evaluate_assignment(inp, assignment, mutable_ids=mutable_set, counter=counters)
    hard = [item for item in final if item.is_hard]
    uncertain = {ann.id for ann in inp.annotations if ann.bbox_source == "estimated"}
    unknown = [item for item in hard
               if any(identity in uncertain for identity in item.annotation_ids)]
    moved = [identity for identity, candidate in assignment.items()
             if abs(candidate.dx) > 1e-9 or abs(candidate.dy) > 1e-9]
    if not hard:
        status = STATUS_PLANNED_CLEAR
    elif unknown:
        status = STATUS_NEEDS_GEOMETRY
    elif moved:
        status = STATUS_PARTIAL
    else:
        status = STATUS_BLOCKED
    reasons = {
        "baseline": True,
        "failures": [
            {"annotation_id": identity,
             "blocking_objects": sorted({obj for item in hard
                                         if identity in item.annotation_ids
                                         for obj in item.objects})}
            for identity in sorted(mutable_set)
            if any(identity in item.annotation_ids for item in hard)
        ],
        "budget_exhausted": False,
        "fixed_violations": _hard([item for item in final
                                   if not mutable_set & set(item.annotation_ids)]),
    }
    return SearchResult(status=status, assignment=assignment, violations=tuple(final),
                        unknown=tuple(unknown), reasons=reasons, stats=stats,
                        noop=(not moved and not hard), scope_ids=tuple(mutable))
