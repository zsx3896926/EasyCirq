"""P2.5 route-aware placement repair: pull the offline router into the loop.

``repair_routes`` closes the gap between the multi-physics placement objective
and *manufacturability*: it starts from the :func:`mp_place.solver_v2.solve`
layout, runs the offline two-layer :class:`mp_place.router.GridRouter`, and when
some nets fail to route it makes bounded, hard-feasible local moves around the
failed nets, re-routes, and keeps only lexicographic improvements
(**completion first, then truth**).

Public API
----------
``repair_routes(scenario, cost, seed=0, steps=600, max_routes=60)``
    -> ``(placement, truth, route_result, stats)``

* ``placement`` — the (still hard-feasible) repaired layout.
* ``truth`` — :class:`mp_place.physics_v2.PhysicsSimulatorV2` score of the final
  placement (the same truth model the pipeline reports as ``truth_v2``; built
  with ``seed`` so it is deterministic).
* ``route_result`` — final :class:`mp_place.router.RouteResult`.
* ``stats`` — includes ``routes_calls``, ``initial_completion``,
  ``final_completion``, ``moves_accepted`` (plus ``moves_tried``,
  ``initial_truth``, ``final_truth``, failed-net lists, timings, ...).

Budget semantics
----------------
* ``steps`` is the **total** solver move budget handed to ``solver_v2.solve``
  (same definition as in that module).
* ``max_routes`` is the **total number of router calls** (including the initial
  route).  At least one route is always made, so the effective budget is
  ``max(1, max_routes)``.  No candidate is routed without counting it, and the
  solver/router calls are the only expensive work performed.

Repair strategy
---------------
1. Solve once with ``solve(scenario, cost, seed=seed, steps=steps)``; route it.
2. While ``completion < 1`` and route budget remains:
   * build **bounded local move candidates** around the failed nets: the failed
     net's endpoint components and their net-neighbours are translated toward or
     around the rest of the net (small grid of 1.5/3/5 mm offsets), and movable
     components sitting in the failed net's routing corridor are pushed away
     from it; a small set of seeded random translations adds diversity;
   * cheaply score every candidate with the truth model, then route candidates
     truth-aware: the lowest-truth few are tried first (so repairs tend not to
     destroy multi-physics quality), followed by the interleaved
     targeted/random candidate order to keep exploration;
   * accept the first candidate that improves ``(completion, -truth)``
     lexicographically, i.e. a completion increase always wins; a completion tie
     is accepted only when truth is lower.
3. Once ``completion == 1``, spend the remaining route budget on truth polish:
   random feasible moves are accepted only if the layout still routes fully and
   truth drops.  This never lowers completion.

Every visited placement is hard-feasible: candidates are filtered with
``mp_place.solver.feasible_partial`` before they can be scored or routed, and
starts come from the (feasible-only) ``solve``.

Determinism: all randomness comes from ``seed``; the router is deterministic;
``stats["runtime_s"]`` and ``RouteResult.runtime_s`` are the only
non-deterministic fields.

Benchmark (recorded reference run; ``templates.instantiate(name, seed)`` x
``ProxyObjective``; seeds 0/1/2; baseline = ``pipeline.run_pipeline(sc, seed)``
with its default ``budget_steps=800``; repair = ``repair_routes`` with the
solver budget matched to 800 and ``max_routes=60``; means over seeds; completion
is the router's scored-net completion, truth is ``truth_v2``; lower truth is
better)::

    template       completion               truth (truth_v2)
                   pipe    repair   delta   pipe     repair    delta
    mcu-min        0.741   1.000   +0.259   1.0683   1.0493    -1.8%
    buck           0.905   1.000   +0.095   1.6673   1.5499    -7.0%
    rs485          0.905   1.000   +0.095   1.0520   1.0276    -2.3%
    motor          0.867   0.967   +0.100   1.9018   1.7961    -5.6%
    wireless       0.917   1.000   +0.083   2.2299   2.2130    -0.8%
    esp32-sensor   0.792   1.000   +0.208   3.0750   2.9001    -5.7%
    can-node       1.000   1.000   +0.000   1.6103   1.4907    -7.4%
    bldc-driver    0.933   1.000   +0.067   2.5909   2.4186    -6.7%
    ---------------------------------------------------------------
    mean (8)       0.882   0.996   +0.114   1.8994   1.8057    -4.9%

23 of the 24 repair runs end fully routed (completion == 1); the single miss is
``motor`` seed 0, which still improves its truth (2.2935 -> 1.8308) but cannot
clear its last failed net within 60 router calls.  Repair wall time averages
~1.4 s per run (0.1 s when already routed, up to ~7 s on the hard motor/mcu-min
cases on the recording machine).

The five original P1/P2 families are the first five rows; the last three are the
later template packs (both are covered because ``templates.TEMPLATES`` exposes
all of them).  Reproduce with::

    from mp_place.objective import ProxyObjective
    from mp_place.pipeline import run_pipeline
    from mp_place.route_opt import repair_routes
    from mp_place.templates import instantiate, template_names
    for name in template_names():
        for seed in (0, 1, 2):
            sc = instantiate(name, seed=seed)
            base = run_pipeline(sc, seed=seed)
            pl, truth, route, stats = repair_routes(
                sc, ProxyObjective(sc).cost, seed=seed, steps=800, max_routes=60
            )

Limits: the router is a 2-layer grid-maze oracle, not a DRC/routability proof;
"completion == 1" means this oracle found a route for every scored net, and the
fixed safety fields of the pipeline (``drc: "NOT RUN"``) still apply.
"""

from __future__ import annotations

import math
import random
import time
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from .model import Placement, Scenario, bbox, pad_position, rect_overlap_area
from .physics_v2 import PhysicsSimulatorV2
from .router import GridRouter, RouteResult
from .solver import feasible_partial
from .solver_v2 import solve

ObjectiveFn = Callable[[Placement], float]

# Router configuration mirrored from ``mp_place.pipeline`` (1 mm / 2 layers).
ROUTER_GRID_MM = 1.0
ROUTER_LAYERS = 2

# --- repair search constants -------------------------------------------
_TRUTH_SHORTLIST = 5  # lowest-truth candidates tried first in the repair phase
_TARGETED_GRID_MM = (1.5, 3.0, 5.0)  # bounded local translation distances
_RANDOM_CANDIDATES = 24  # seeded random translations per repair iteration
_POLISH_CANDIDATES = 16  # seeded random translations per truth-polish iteration
_MAX_TARGETED = 160  # deterministic cap on the targeted candidate list

_DIRECTIONS: Tuple[Tuple[float, float], ...] = (
    (1.0, 0.0),
    (-1.0, 0.0),
    (0.0, 1.0),
    (0.0, -1.0),
    (0.7071067811865476, 0.7071067811865476),
    (-0.7071067811865476, 0.7071067811865476),
    (0.7071067811865476, -0.7071067811865476),
    (-0.7071067811865476, -0.7071067811865476),
)

_MASK64 = (1 << 64) - 1


# ----------------------------------------------------------------- helpers


def _clamp(value: float, low: float, high: float) -> float:
    return low if value < low else high if value > high else value


def _repair_rng(seed: int) -> random.Random:
    """Deterministic RNG stream for the repair moves (seed-derived)."""
    salt = ((int(seed) * 0x9E3779B97F4A7C15) ^ 0x524F5554455F5632) & _MASK64
    return random.Random(salt)


def _movable_refs(sc: Scenario) -> List[str]:
    return [ref for ref, comp in sc.components.items() if not comp.fixed]


def _net_partner_map(sc: Scenario) -> Dict[str, List[str]]:
    """ref -> movable refs sharing at least one net (deterministic order)."""
    partners: Dict[str, List[str]] = {ref: [] for ref in sc.components}
    for net in sc.nets:
        refs = sorted({ref for ref, _pin in net.pins if ref in sc.components})
        for a in refs:
            for b in refs:
                if a != b and b not in partners[a]:
                    partners[a].append(b)
    return partners


def _half_extents(sc: Scenario, ref: str, rot: int) -> Tuple[float, float]:
    box = bbox(sc.components[ref], 0.0, 0.0, rot)
    return (box[2] - box[0]) / 2.0, (box[3] - box[1]) / 2.0


def _clamped_trial(
    sc: Scenario,
    placement: Placement,
    ref: str,
    nx: float,
    ny: float,
    rot: int,
) -> Optional[Placement]:
    """Translate ``ref`` to ``(nx, ny)``; return the trial only if hard-feasible."""
    hw, hh = _half_extents(sc, ref, rot)
    nx = _clamp(nx, hw, sc.board_w - hw)
    ny = _clamp(ny, hh, sc.board_h - hh)
    trial = dict(placement)
    trial[ref] = (nx, ny, rot)
    return trial if feasible_partial(sc, trial) else None


def _targeted_moves(
    sc: Scenario,
    placement: Placement,
    route_result: RouteResult,
    net_by_name: Dict[str, object],
) -> List[Placement]:
    """Bounded local moves around the failed nets (endpoints, neighbours, blockers)."""
    moves: List[Placement] = []
    for name in route_result.failed_nets:
        net = net_by_name.get(name)
        if net is None:
            continue
        # Terminal pad positions and their bounding corridor.
        points: List[Tuple[float, float]] = []
        for ref, pin in net.pins:  # type: ignore[attr-defined]
            if ref not in placement:
                continue
            comp = sc.components.get(ref)
            if comp is None:
                continue
            x, y, rot = placement[ref]
            points.append(pad_position(comp, x, y, rot, pin))
        if len(points) < 2:
            continue
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        corridor = (min(xs) - 1.5, min(ys) - 1.5, max(xs) + 1.5, max(ys) + 1.5)
        cx = (corridor[0] + corridor[2]) / 2.0
        cy = (corridor[1] + corridor[3]) / 2.0
        net_refs = {ref for ref, _pin in net.pins}  # type: ignore[attr-defined]
        # (1) failed-net endpoints: pull toward the rest of the net, nudge around.
        for ref, _pin in net.pins:  # type: ignore[attr-defined]
            comp = sc.components.get(ref)
            if comp is None or comp.fixed or ref not in placement:
                continue
            x, y, rot = placement[ref]
            others: List[Tuple[float, float]] = []
            for other, other_pin in net.pins:  # type: ignore[attr-defined]
                if other == ref or other not in placement:
                    continue
                ocomp = sc.components.get(other)
                if ocomp is None:
                    continue
                ox, oy, orot = placement[other]
                others.append(pad_position(ocomp, ox, oy, orot, other_pin))
            if others:
                tx = sum(p[0] for p in others) / len(others)
                ty = sum(p[1] for p in others) / len(others)
                for alpha in (0.4, 0.75):
                    trial = _clamped_trial(
                        sc, placement, ref, x + alpha * (tx - x), y + alpha * (ty - y), rot
                    )
                    if trial is not None:
                        moves.append(trial)
            for dist in _TARGETED_GRID_MM:
                for dx, dy in _DIRECTIONS:
                    trial = _clamped_trial(sc, placement, ref, x + dx * dist, y + dy * dist, rot)
                    if trial is not None:
                        moves.append(trial)
        # (2) movable blockers inside the corridor: push away from the corridor.
        for ref, comp in sc.components.items():
            if comp.fixed or ref not in placement or ref in net_refs:
                continue
            box = bbox(comp, *placement[ref])
            if rect_overlap_area(box, corridor) <= 0.0:
                continue
            x, y, rot = placement[ref]
            dx = x - cx
            dy = y - cy
            norm = math.hypot(dx, dy) or 1.0
            for dist in (2.5, 5.0):
                trial = _clamped_trial(
                    sc, placement, ref, x + dx / norm * dist, y + dy / norm * dist, rot
                )
                if trial is not None:
                    moves.append(trial)
    if len(moves) > _MAX_TARGETED:
        return moves[:_MAX_TARGETED]
    return moves


def _random_moves(
    sc: Scenario,
    placement: Placement,
    rng: random.Random,
    moveable: Sequence[str],
    partners: Dict[str, List[str]],
    count: int,
) -> List[Placement]:
    """Seeded bounded random translations of movable components (hard-feasible)."""
    moves: List[Placement] = []
    if not moveable:
        return moves
    for _ in range(count):
        ref = moveable[rng.randrange(len(moveable))]
        comp = sc.components[ref]
        x, y, rot = placement[ref]
        if rng.random() < 0.7:
            angle = rng.uniform(0.0, 2.0 * math.pi)
            dist = rng.uniform(1.0, 5.0)
            nx = x + math.cos(angle) * dist
            ny = y + math.sin(angle) * dist
        else:  # toward the mean of net partners
            pts = [placement[p][:2] for p in partners.get(ref, ()) if p in placement]
            if pts:
                tx = sum(p[0] for p in pts) / len(pts)
                ty = sum(p[1] for p in pts) / len(pts)
                alpha = rng.uniform(0.3, 0.9)
                nx = x + alpha * (tx - x)
                ny = y + alpha * (ty - y)
            else:
                nx = x + rng.uniform(-4.0, 4.0)
                ny = y + rng.uniform(-4.0, 4.0)
        trial = _clamped_trial(sc, placement, ref, nx, ny, rot)
        if trial is not None:
            moves.append(trial)
    return moves


def _interleave(first: Sequence[Placement], second: Sequence[Placement]) -> List[Placement]:
    """Deterministic round-robin merge of two candidate lists."""
    out: List[Placement] = []
    for i in range(max(len(first), len(second))):
        if i < len(first):
            out.append(first[i])
        if i < len(second):
            out.append(second[i])
    return out


def _rank_candidates(
    candidates: Sequence[Placement],
    truth_fn: Callable[[Placement], float],
    shortlist: int,
) -> List[Tuple[float, Placement]]:
    """Truth-score candidates; try the lowest-truth ``shortlist`` first, then the rest."""
    scores = [truth_fn(candidate) for candidate in candidates]
    order = sorted(range(len(candidates)), key=lambda i: (scores[i], i))
    head = order[: max(0, shortlist)]
    seen = set(head)
    tail = [i for i in range(len(candidates)) if i not in seen]
    return [(scores[i], candidates[i]) for i in head + tail]


# -------------------------------------------------------------------- API


def repair_routes(
    scenario: Scenario,
    cost: ObjectiveFn,
    seed: int = 0,
    steps: int = 600,
    max_routes: int = 60,
) -> Tuple[Placement, float, RouteResult, Dict[str, object]]:
    """Route-aware local repair around a ``solver_v2`` placement.

    See the module docstring for the strategy, budget semantics and the recorded
    benchmark.  Returns ``(placement, truth, route_result, stats)``; the
    placement is always hard-feasible, and ``truth`` is the
    :class:`~mp_place.physics_v2.PhysicsSimulatorV2` score of that placement.
    """
    t_start = time.perf_counter()
    sc = scenario
    seed = int(seed)
    solve_steps = max(0, int(steps))
    route_budget = max(1, int(max_routes))
    truth_fn = PhysicsSimulatorV2(sc, seed=seed).score
    rng = _repair_rng(seed)
    movable = _movable_refs(sc)
    partners = _net_partner_map(sc)
    net_by_name = {net.name: net for net in sc.nets}

    placement, _proxy_cost, _solver_stats = solve(
        sc, cost, seed=seed, steps=solve_steps
    )
    router = GridRouter(sc, grid_mm=ROUTER_GRID_MM, layers=ROUTER_LAYERS)
    route_result = router.route(placement)
    initial_failed_nets = list(route_result.failed_nets)
    routes_calls = 1
    moves_tried = 0
    moves_accepted = 0
    truth = truth_fn(placement)
    initial_completion = route_result.completion
    initial_truth = truth

    while routes_calls < route_budget:
        if route_result.completion >= 1.0:
            # ---- truth polish: keep full routability, only accept truth drops
            candidates = _random_moves(
                sc, placement, rng, movable, partners, _POLISH_CANDIDATES
            )
            if not candidates:
                break
            scored = sorted(
                ((truth_fn(candidate), candidate) for candidate in candidates),
                key=lambda item: item[0],
            )
            accepted = False
            for candidate_truth, candidate in scored:
                if candidate_truth >= truth or routes_calls >= route_budget:
                    break
                candidate_result = router.route(candidate)
                routes_calls += 1
                moves_tried += 1
                if candidate_result.completion >= 1.0:
                    placement, route_result, truth = (
                        candidate,
                        candidate_result,
                        candidate_truth,
                    )
                    moves_accepted += 1
                    accepted = True
                    break
            if not accepted:
                break
        else:
            # ---- repair: lexicographic (completion, -truth) hill climbing
            targeted = _targeted_moves(sc, placement, route_result, net_by_name)
            random_moves = _random_moves(
                sc, placement, rng, movable, partners, _RANDOM_CANDIDATES
            )
            candidates = _interleave(targeted, random_moves)
            if not candidates:
                break
            ranked = _rank_candidates(candidates, truth_fn, _TRUTH_SHORTLIST)
            improved = False
            for candidate_truth, candidate in ranked:
                if routes_calls >= route_budget:
                    break
                candidate_result = router.route(candidate)
                routes_calls += 1
                moves_tried += 1
                better = candidate_result.completion > route_result.completion or (
                    candidate_result.completion == route_result.completion
                    and candidate_truth < truth
                )
                if better:
                    placement, route_result, truth = (
                        candidate,
                        candidate_result,
                        candidate_truth,
                    )
                    moves_accepted += 1
                    improved = True
                    break
            if not improved:
                break

    stats: Dict[str, object] = {
        "solver": "route-opt-v1",
        "seed": seed,
        "steps": solve_steps,
        "max_routes": route_budget,
        "routes_calls": routes_calls,
        "moves_tried": moves_tried,
        "moves_accepted": moves_accepted,
        "initial_completion": initial_completion,
        "final_completion": route_result.completion,
        "initial_truth": initial_truth,
        "final_truth": truth,
        "initial_failed_nets": initial_failed_nets,
        "final_failed_nets": list(route_result.failed_nets),
        "fully_routed": route_result.completion >= 1.0,
        "runtime_s": time.perf_counter() - t_start,
    }
    return placement, truth, route_result, stats


__all__ = ["repair_routes", "ROUTER_GRID_MM", "ROUTER_LAYERS"]
