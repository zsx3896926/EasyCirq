"""K2-K4: bounded batch avoidance solver.

The solver works on conflict clusters, freezes everything outside the selected
cluster, initializes deterministically, then improves with a bounded local
search and (for small clusters) a budgeted backtracking pass.  Every accepted
state is validated as a whole; it never picks per-annotation optima and leaves a
new conflict behind.  Wall time is measured by the caller, never used to decide.

Failure vocabulary is explicit (contract 5.5): ``no_candidates``,
``all_candidates_rejected``, ``budget_exhausted``, ``geometry_uncertain``,
``host_capability_unsupported``, ``net_label_anchor_not_separable``.  A search
failure is never reported as mathematical infeasibility.
"""
from __future__ import annotations

import math
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from .candidates import generate_candidates
from .conflicts import Evaluator, evaluate_assignment
from .model import (
    REASON_ALL_REJECTED,
    REASON_BUDGET,
    REASON_FROZEN,
    REASON_GEOMETRY_UNCERTAIN,
    REASON_HOST_UNSUPPORTED,
    REASON_NET_ANCHOR,
    REASON_NO_CANDIDATES,
    REASON_OWNER_UNKNOWN,
    STATUS_BLOCKED,
    STATUS_NEEDS_GEOMETRY,
    STATUS_PARTIAL,
    STATUS_PLANNED_CLEAR,
    Annotation,
    Candidate,
    Counters,
    Input,
    Rect,
    SearchResult,
    SearchStats,
    Violation,
)

_EPS = 1e-9


def _current_candidate(domain: Sequence[Candidate]) -> Candidate:
    for candidate in domain:
        if abs(candidate.dx) <= _EPS and abs(candidate.dy) <= _EPS:
            return candidate
    return domain[0]


def _domain_order(domain: Sequence[Candidate]) -> List[Candidate]:
    return list(domain)


def _mutable_scope(inp: Input, scope_ids: Optional[Sequence[str]],
                   frozen_ids: Sequence[str]) -> Tuple[List[str], List[str]]:
    frozen = set(frozen_ids) | set(inp.constraints.freeze_ids)
    candidates = [ann for ann in inp.annotations if ann.movable and ann.id not in frozen]
    if scope_ids is not None:
        wanted = set(scope_ids)
        candidates = [ann for ann in candidates if ann.id in wanted]
    elif inp.constraints.scope == "cluster":
        wanted = set(inp.constraints.scope_cluster_ids)
        candidates = [ann for ann in candidates if ann.id in wanted]
    else:
        candidates = list(candidates)
    return [ann.id for ann in candidates], sorted(frozen)


def _annotation_priority(inp: Input, identity: str) -> Tuple[int, str]:
    ann = inp.annotation(identity)
    return (ann.constraints.priority, identity)


def _hard_count(violations: Iterable[Violation]) -> int:
    return sum(1 for item in violations if item.is_hard)


def _soft_count(violations: Iterable[Violation]) -> int:
    return sum(1 for item in violations if item.severity == "soft")


def _unknown_involved(inp: Input, violations: Iterable[Violation]) -> Set[str]:
    uncertain = {ann.id for ann in inp.annotations if ann.bbox_source == "estimated"}
    return {identity for item in violations if item.is_hard
            for identity in item.annotation_ids if identity in uncertain}


class _ClusterSolver:
    def __init__(self, inp: Input, cluster: Sequence[str],
                 domains: Mapping[str, Sequence[Candidate]],
                 frozen_boxes: Mapping[str, Rect],
                 counter: Counters, stats: SearchStats) -> None:
        self.inp = inp
        self.cluster = list(cluster)
        self.domains = {identity: list(domains.get(identity, ()))
                        for identity in self.cluster}
        self.frozen = dict(frozen_boxes)
        self.counter = counter
        self.stats = stats
        self.evaluator = Evaluator(inp, counter)
        self.static: Dict[str, List[Tuple[int, int, List[Violation]]]] = {}
        for identity in self.cluster:
            ann = inp.annotation(identity)
            domain = self.domains[identity]
            entries: List[Tuple[int, int, List[Violation]]] = []
            for candidate in domain:
                violations = self.evaluator.static_violations(
                    ann, candidate.bbox, frozen=self.frozen)
                self.stats.states += 1
                entries.append((_hard_count(violations), _soft_count(violations),
                                violations))
            self.static[identity] = entries

    # -- local evaluation --------------------------------------------------
    def _pair_hard(self, first: str, first_candidate: Candidate,
                   second: str, second_candidate: Candidate) -> Tuple[int, int]:
        violations = self.evaluator.pair_violations(
            self.inp.annotation(first), first_candidate.bbox,
            self.inp.annotation(second), second_candidate.bbox)
        return _hard_count(violations), _soft_count(violations)

    def evaluate(self, assignment: Mapping[str, Candidate]) -> Tuple[int, int, int, float]:
        hard = 0
        soft = 0
        moved = 0
        displacement = 0.0
        for identity in self.cluster:
            index = self._candidate_index(assignment[identity])
            hard += self.static[identity][index][0]
            soft += self.static[identity][index][1]
            candidate = assignment[identity]
            if abs(candidate.dx) > _EPS or abs(candidate.dy) > _EPS:
                moved += 1
                displacement += candidate.displacement
        for position, first in enumerate(self.cluster):
            for second in self.cluster[position + 1:]:
                pair_hard, pair_soft = self._pair_hard(
                    first, assignment[first], second, assignment[second])
                hard += pair_hard
                soft += pair_soft
        self.stats.states += 1
        return hard, soft, moved, displacement

    def _candidate_index(self, candidate: Candidate) -> int:
        domain = self.domains[candidate.annotation_id]
        for index, item in enumerate(domain):
            if item is candidate:
                return index
        for index, item in enumerate(domain):
            if (abs(item.dx - candidate.dx) <= _EPS
                    and abs(item.dy - candidate.dy) <= _EPS):
                return index
        raise KeyError(candidate.annotation_id)

    def local_hard_for(self, identity: str, candidate: Candidate,
                       assignment: Mapping[str, Candidate]) -> Tuple[int, int]:
        index = self._candidate_index(candidate)
        hard = self.static[identity][index][0]
        soft = self.static[identity][index][1]
        for other in self.cluster:
            if other == identity or other not in assignment:
                continue
            pair_hard, pair_soft = self._pair_hard(identity, candidate, other,
                                                   assignment[other])
            hard += pair_hard
            soft += pair_soft
        return hard, soft

    # -- initialization ----------------------------------------------------
    def greedy(self) -> Dict[str, Candidate]:
        assignment: Dict[str, Candidate] = {}
        for identity in self.cluster:
            domain = self.domains[identity]
            if domain:
                assignment[identity] = _current_candidate(domain)
        order = sorted(self.cluster,
                       key=lambda identity: (len(self.domains[identity]),
                                             _annotation_priority(self.inp, identity)))
        for identity in order:
            domain = self.domains[identity]
            if not domain:
                continue
            current = _current_candidate(domain)
            assignment[identity] = current
            current_hard, _ = self.local_hard_for(identity, current, assignment)
            if current_hard == 0:
                continue
            best = current
            best_cost = (current_hard, current.displacement, current.rank)
            for candidate in domain:
                if candidate is current:
                    continue
                hard, soft = self.local_hard_for(identity, candidate, assignment)
                cost = (hard, round(candidate.displacement, 9), candidate.rank)
                if cost < best_cost:
                    best, best_cost = candidate, cost
            assignment[identity] = best
            self.stats.iterations += 1
        return assignment

    # -- local search ------------------------------------------------------
    def improve(self, assignment: Dict[str, Candidate]) -> Dict[str, Candidate]:
        best_cost = self.evaluate(assignment)
        steps = 0
        while steps < self.inp.constraints.max_local_search_steps:
            if best_cost[0] == 0:
                break
            move = None
            move_cost = best_cost
            for identity in self.cluster:
                domain = self.domains[identity]
                current = assignment[identity]
                for candidate in domain:
                    if candidate is current:
                        continue
                    trial = dict(assignment)
                    trial[identity] = candidate
                    cost = self.evaluate(trial)
                    if cost < move_cost:
                        move_cost = cost
                        move = (identity, candidate)
            if move is None:
                break
            assignment[move[0]] = move[1]
            best_cost = move_cost
            steps += 1
            self.stats.local_steps += 1
        return assignment

    # -- bounded backtracking ---------------------------------------------
    def backtrack(self, initial: Mapping[str, Candidate]) -> Dict[str, Candidate]:
        initial_cost = self.evaluate(dict(initial))
        if initial_cost[0] == 0:
            return dict(initial)
        order = sorted(self.cluster,
                       key=lambda identity: (len(self.domains[identity]),
                                             _annotation_priority(self.inp, identity)))
        best = dict(initial)
        best_hard = initial_cost[0]
        budget = self.inp.constraints.max_search_states
        used = [0]
        assignment: Dict[str, Candidate] = {}
        for identity in self.cluster:
            if self.domains[identity]:
                assignment[identity] = _current_candidate(self.domains[identity])

        def walk(position: int) -> None:
            nonlocal best, best_hard
            if used[0] >= budget:
                self.stats.budget_exhausted = True
                self.stats.budget_kind = "max_search_states"
                return
            if position == len(order):
                hard, _, _, _ = self.evaluate(dict(assignment))
                if hard < best_hard:
                    best_hard = hard
                    best = dict(assignment)
                return
            identity = order[position]
            for candidate in self.domains[identity]:
                assignment[identity] = candidate
                hard, _ = self.local_hard_for(identity, candidate, assignment)
                used[0] += 1
                self.stats.states += 1
                if hard < best_hard:
                    walk(position + 1)
                if used[0] >= budget:
                    break
            assignment.pop(identity, None)

        walk(0)
        return best


def _merge_assignment(inp: Input, clusters: Sequence[Sequence[str]],
                      solved: Sequence[Mapping[str, Candidate]]) -> Dict[str, Candidate]:
    result: Dict[str, Candidate] = {}
    for cluster, assignment in zip(clusters, solved):
        for identity in cluster:
            if identity in assignment:
                result[identity] = assignment[identity]
    return result


def _reason_for(inp: Input, identity: str, domain: Sequence[Candidate],
                violations: Sequence[Violation], budget: bool) -> Dict[str, object]:
    ann = inp.annotation(identity)
    hard = [item for item in violations if item.is_hard and identity in item.annotation_ids]
    reason: Optional[str] = None
    suggestion = "supply a measured bbox or widen the allowed area"
    if ann.bbox_source == "estimated":
        reason = REASON_GEOMETRY_UNCERTAIN
        suggestion = "measure the text bbox from the official SVG/host first"
    elif not ann.movable:
        if ann.role in ("net_label", "wire_name"):
            reason = REASON_NET_ANCHOR
            suggestion = "probe host text/anchor separation and declare net_label_detach"
        else:
            reason = REASON_HOST_UNSUPPORTED
            suggestion = "probe the host capability or keep the annotation fixed"
    elif not domain:
        reason = REASON_NO_CANDIDATES
        suggestion = "allow a larger displacement/area or free a keepout"
    elif all(abs(item.dx) <= _EPS and abs(item.dy) <= _EPS for item in domain):
        reason = REASON_ALL_REJECTED
        suggestion = "all candidates violate a hard constraint; widen the declared area"
    elif budget:
        reason = REASON_BUDGET
        suggestion = "raise max_search_states or reduce the conflict cluster"
    else:
        reason = REASON_ALL_REJECTED
    return {
        "reason": reason,
        "blocking_objects": sorted({obj for item in hard for obj in item.objects}),
        "missing_evidence": ("measured bbox" if reason == REASON_GEOMETRY_UNCERTAIN else None),
        "suggestion": suggestion,
    }


def _annotation_reach(inp: Input, identity: str) -> float:
    ann = inp.annotation(identity)
    reach = ann.constraints.max_displacement
    if reach <= 0:
        reach = inp.constraints.max_displacement
    return max(reach, 0.0)


def _focus_ids(inp: Input, hard_ids: Iterable[str],
               mutable_set: Set[str]) -> List[str]:
    """Bounded local focus: hard-conflict annotations plus reachable neighbours.

    Three expansion rounds are enough to include a text that a moved neighbour
    could collide with, without turning a single conflict into a whole-page
    reshuffle.
    """
    focus: Set[str] = set(hard_ids)
    for _ in range(3):
        additions: Set[str] = set()
        for identity in sorted(focus):
            envelope = inp.annotation(identity).current.bbox.inflated(
                _annotation_reach(inp, identity))
            for other in inp.annotations:
                if other.id in focus or other.id not in mutable_set or not other.movable:
                    continue
                if other.current.bbox.intersects(envelope):
                    additions.add(other.id)
        if not additions:
            break
        focus |= additions
    return sorted(focus)


def _focus_clusters(inp: Input, focus: Sequence[str]) -> List[List[str]]:
    """Connected components inside the focus (hard conflicts + reach overlap)."""
    identifiers = sorted(focus)
    parent = {identity: identity for identity in identifiers}

    def find(key: str) -> str:
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key

    def union(first: str, second: str) -> None:
        root_a, root_b = find(first), find(second)
        if root_a != root_b:
            parent[max(root_a, root_b)] = min(root_a, root_b)

    for item in evaluate_assignment(inp, {}, mutable_ids=identifiers):
        if item.is_hard and len(item.annotation_ids) == 2:
            first, second = sorted(item.annotation_ids)
            if first in parent and second in parent:
                union(first, second)
    boxes = {identity: inp.annotation(identity).current.bbox.inflated(
        _annotation_reach(inp, identity)) for identity in identifiers}
    for position, first in enumerate(identifiers):
        for second in identifiers[position + 1:]:
            if boxes[first].intersects(boxes[second]):
                union(first, second)
    groups: Dict[str, List[str]] = {}
    for identity in identifiers:
        groups.setdefault(find(identity), []).append(identity)
    return sorted((sorted(group) for group in groups.values()),
                  key=lambda group: (len(group), group[0]))


def solve(inp: Input, *, scope_ids: Optional[Sequence[str]] = None,
          frozen_ids: Sequence[str] = (),
          candidates: Optional[Mapping[str, Sequence[Candidate]]] = None,
          counter: Optional[Counters] = None) -> SearchResult:
    counters = counter if counter is not None else Counters()
    stats = SearchStats()
    mutable, frozen = _mutable_scope(inp, scope_ids, frozen_ids)
    mutable_set = set(mutable)
    current_violations = evaluate_assignment(inp, {}, mutable_ids=None, counter=counters)
    current_hard = [item for item in current_violations if item.is_hard]
    scope_hard = [item for item in current_hard
                  if mutable_set & set(item.annotation_ids)]
    unsupported_hard = [item for item in current_hard
                        if any(not inp.annotation(identity).movable
                               for identity in item.annotation_ids)]
    stats.freeze_count = len(inp.annotations) - len(mutable)
    frozen_policy = {ann.id for ann in inp.annotations
                     if ann.id in set(frozen) and ann.movable}
    frozen_hard = [item for item in current_hard
                   if any(identity in frozen_policy for identity in item.annotation_ids)]

    if not scope_hard and not unsupported_hard:
        if frozen_hard:
            reasons = {
                "per_annotation": {
                    identity: {
                        "reason": REASON_FROZEN,
                        "blocking_objects": sorted({obj for item in frozen_hard
                                                    if identity in item.annotation_ids
                                                    for obj in item.objects}),
                        "missing_evidence": None,
                        "suggestion": "unfreeze this annotation or accept the frozen conflict; "
                                      "a frozen conflict is reported, not silently ignored",
                    }
                    for identity in sorted(frozen_policy)
                    if any(identity in item.annotation_ids for item in frozen_hard)
                },
                "frozen_violations": [
                    {"code": item.code, "objects": list(item.objects),
                     "annotation_ids": list(item.annotation_ids)} for item in frozen_hard],
                "frozen_ids": sorted(frozen_policy),
                "fixed_violations": len(frozen_hard),
            }
            return SearchResult(status=STATUS_PARTIAL, assignment={},
                                violations=tuple(frozen_hard), unknown=(),
                                reasons=reasons, stats=stats, noop=False,
                                scope_ids=tuple(mutable))
        return SearchResult(status=STATUS_PLANNED_CLEAR, assignment={},
                            violations=(), unknown=(), reasons={"noop": True},
                            stats=stats, noop=True, scope_ids=tuple(mutable))

    if not scope_hard and unsupported_hard:
        unsupported_ids = sorted({identity
                                  for item in unsupported_hard
                                  for identity in item.annotation_ids
                                  if not inp.annotation(identity).movable})
        reasons: Dict[str, object] = {
            "unsupported": unsupported_ids,
            "per_annotation": {
                identity: {
                    "reason": REASON_HOST_UNSUPPORTED,
                    "blocking_objects": sorted({obj for item in unsupported_hard
                                                if identity in item.annotation_ids
                                                for obj in item.objects}),
                    "missing_evidence": "host capability probe",
                    "suggestion": "probe whether the host can move this annotation without "
                                  "detaching the electrical anchor; otherwise keep it fixed",
                }
                for identity in unsupported_ids
            },
            "frozen_violations": [],
            "fixed_violations": len(unsupported_hard),
        }
        unknown = tuple(item for item in unsupported_hard
                        if any(inp.annotation(identity).bbox_source == "estimated"
                               for identity in item.annotation_ids))
        return SearchResult(status=STATUS_BLOCKED, assignment={},
                            violations=tuple(unsupported_hard), unknown=unknown,
                            reasons=reasons, stats=stats, noop=False,
                            scope_ids=tuple(mutable))

    # Domain: use the caller-provided equal-domain set, else expand a bounded
    # focus around the current hard conflicts.  Everything outside the focus is
    # a frozen obstacle; this is the local-repair behaviour (no whole-page
    # reshuffle just to lower a score).
    hard_ids = {identity for item in scope_hard for identity in item.annotation_ids
                if identity in mutable_set}
    focus = _focus_ids(inp, hard_ids, mutable_set)
    assignment: Dict[str, Candidate] = {}
    final_violations: List[Violation] = []
    hard: List[Violation] = []
    domains: Dict[str, List[Candidate]] = {}
    for attempt in range(3):
        clusters = _focus_clusters(inp, focus)
        stats.clusters = len(clusters)
        stats.cluster_sizes = [len(cluster) for cluster in clusters]
        if candidates is None:
            domains = generate_candidates(
                inp, scope_ids=focus,
                frozen_ids=[identity for identity in mutable_set if identity not in set(focus)],
                counter=counters, stats=stats)
        else:
            domains = {identity: list(candidates.get(identity, ()))
                       for identity in mutable_set}
            stats.candidates_generated = sum(len(items) for items in domains.values())
            stats.candidates_possible = stats.candidates_generated
        solved: List[Dict[str, Candidate]] = []
        solved_clusters: List[List[str]] = []
        for cluster in clusters:
            cluster = [identity for identity in cluster if domains.get(identity)]
            if not cluster:
                continue
            solved_clusters.append(cluster)
            local_domains = {identity: domains.get(identity, []) for identity in cluster}
            frozen_local = {ann.id: (
                assignment[ann.id].bbox if ann.id in assignment else ann.current.bbox)
                for ann in inp.annotations if ann.id not in set(cluster)}
            solver = _ClusterSolver(inp, cluster, local_domains, frozen_local,
                                    counters, stats)
            cluster_assignment = solver.greedy()
            cluster_assignment = solver.improve(cluster_assignment)
            if solver.evaluate(cluster_assignment)[0] > 0:
                cluster_assignment = solver.backtrack(cluster_assignment)
            solved.append(cluster_assignment)
        assignment = _merge_assignment(inp, solved_clusters, solved)
        final_violations = evaluate_assignment(inp, assignment, mutable_ids=mutable,
                                               counter=counters)
        hard = [item for item in final_violations if item.is_hard]
        extra = {identity for item in hard for identity in item.annotation_ids
                 if identity in mutable_set and identity not in set(focus)
                 and inp.annotation(identity).movable}
        if not hard or not extra or stats.budget_exhausted:
            break
        focus = sorted(set(focus) | extra)
    final_all = evaluate_assignment(inp, assignment, mutable_ids=None,
                                    counter=counters)
    hard_all = [item for item in final_all if item.is_hard]
    hard = [item for item in hard_all if mutable_set & set(item.annotation_ids)]
    hard_frozen = [item for item in hard_all
                   if any(identity in frozen_policy for identity in item.annotation_ids)]
    hard_unsupported = [item for item in hard_all
                        if any(not inp.annotation(identity).movable
                               for identity in item.annotation_ids)]
    unknown_ids = _unknown_involved(inp, hard)
    unknown = tuple(item for item in hard
                    if any(identity in unknown_ids for identity in item.annotation_ids))

    reasons: Dict[str, object] = {"per_annotation": {}}
    failures: List[Dict[str, object]] = []
    for identity in mutable:
        violation_ids = [item for item in hard if identity in item.annotation_ids]
        if not violation_ids:
            continue
        entry = _reason_for(inp, identity, domains.get(identity, []), violation_ids,
                            stats.budget_exhausted)
        reasons["per_annotation"][identity] = entry  # type: ignore[index]
        failures.append({"annotation_id": identity, **entry})
    reasons["failures"] = failures
    unsupported_ids = sorted({identity for item in hard_unsupported
                              for identity in item.annotation_ids
                              if not inp.annotation(identity).movable})
    for identity in unsupported_ids:
        reasons["per_annotation"][identity] = {
            "reason": REASON_HOST_UNSUPPORTED,
            "blocking_objects": sorted({obj for item in hard_unsupported
                                        if identity in item.annotation_ids
                                        for obj in item.objects}),
            "missing_evidence": "host capability probe",
            "suggestion": "probe whether the host can move this annotation without detaching "
                          "the electrical anchor; otherwise keep it fixed",
        }
    for identity in sorted(frozen_policy):
        if any(identity in item.annotation_ids for item in hard_frozen):
            reasons["per_annotation"][identity] = {
                "reason": REASON_FROZEN,
                "blocking_objects": sorted({obj for item in hard_frozen
                                            if identity in item.annotation_ids
                                            for obj in item.objects}),
                "missing_evidence": None,
                "suggestion": "unfreeze this annotation or accept the frozen conflict; "
                              "a frozen conflict is reported, not silently ignored",
            }
    reasons["frozen_violations"] = [
        {"code": item.code, "objects": list(item.objects),
         "annotation_ids": list(item.annotation_ids)} for item in hard_frozen]
    reasons["frozen_ids"] = sorted(frozen_policy)
    reasons["unsupported"] = unsupported_ids
    reasons["fixed_violations"] = _hard_count(
        item for item in current_hard if not (mutable_set & set(item.annotation_ids)))
    reasons["budget_exhausted"] = stats.budget_exhausted

    moved = [identity for identity, candidate in assignment.items()
             if abs(candidate.dx) > _EPS or abs(candidate.dy) > _EPS]
    if not hard_all:
        status = STATUS_PLANNED_CLEAR
        if not moved:
            # Verify the no-op idempotence claim: current state is already clean.
            stats.freeze_count += len(mutable)
    elif unknown_ids:
        status = STATUS_NEEDS_GEOMETRY
    elif hard:
        if stats.budget_exhausted or moved:
            status = STATUS_PARTIAL
        else:
            status = STATUS_BLOCKED
    else:
        # Only frozen / unsupported annotations still have conflicts.
        status = STATUS_PARTIAL
    return SearchResult(status=status, assignment=assignment,
                        violations=tuple(final_all), unknown=unknown,
                        reasons=reasons, stats=stats,
                        noop=(not moved and not hard_all),
                        scope_ids=tuple(mutable))
