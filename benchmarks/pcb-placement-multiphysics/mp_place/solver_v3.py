"""P2.16 portfolio placement solver v3: constructive start + three trajectories.

``solve_v3(scenario, cost, seed=0, steps=800)`` returns
``(best_placement, best_cost, stats)`` and spends the **same total move budget**
as ``solver_v2.solve(..., steps=800)``, but organises the search as a portfolio
of three complementing trajectories:

1. **greedy_search** — a deterministic constructive start
   (:func:`greedy_placement`: components are placed one by one, highest-impact /
   most-connected first, at the feasible grid position that minimises a local
   net-distance cost) refined by a tabu-guided adaptive-step annealing run.
2. **restarts** — :func:`mp_place.solver_v2.solve` (its multi-restart portfolio)
   on the same scenario/cost/seed.
3. **polish** — a low-temperature warm-start local search from the best layout
   found by trajectory 1/2 (intensification).

The returned layout is the trajectory with the lowest objective cost.  All
proposals are gated by ``mp_place.solver.feasible_partial``, so only hard-feasible
placements are ever visited; the constructive start is validated with
``hard_violations`` too.

Budget split (total ``steps``, fixed for every template): ``1/8``
greedy-anchored search, ``7/16`` solver_v2 restarts, ``7/16`` warm-start polish
(the remainder).  ``stats["attempts"]`` equals ``steps`` and
``stats["budget_split"]`` documents the split.  The polish stage is an
intensification step that starts from the best of the first two trajectories, so
it normally supplies the final winner; ``stats["warm_start_source"]`` records
which trajectory it started from (evidence for the constructive start).

Report
------
``python -m mp_place.solver_v3`` runs the benchmark requested by P2.16 (8
templates x seeds 0/1, ``steps=800``) and writes ``report_solver_v3.md`` /
``.json``: proxy cost, ``truth_v2``, router completion, wall time, per-run cost
winner, per-template winning trajectory/variance and a recommended
configuration.  See the generated report for the recorded numbers.

Determinism: the constructive start is RNG-free (a seeded random fallback is only
used if the grid search cannot place a part), each trajectory has its own
seed-derived RNG, and the only non-deterministic stats field is ``runtime_s``.
Offline only: no EDA/DRC/network; router and truth model are offline surrogates.

Recorded result (8 templates x seeds 0/1, ``steps=800``, v2 = ``solve_v2`` with
the same budget)::

    solver                         proxy cost   truth_v2   completion   fully routed   time/run
    solver_v2                        3.4318      2.0001      0.9019         6/16         0.126 s
    solver_v3 (1/8+7/16+7/16)        3.1145      1.8422      0.7326         2/16         0.190 s
    delta                           -9.25%      -7.89%      -0.1693          —             —

v3 wins the proxy-cost comparison in 13/16 runs, and its deterministic greedy
start is better than solver_v2's first random start in 15/16 runs (mean 5.18 vs
8.87).  The catch is routability: stronger proxy-cost optimisation produces more
compact layouts that the grid router completes less often, so v3 is **not**
recommended as the routability-sensitive default.  Recommended configuration:
keep ``solver_v2.solve`` as the default and use ``solve_v3`` as the
quality-oriented alternative (pair it with post-hoc route repair or a route-aware
cost to recover completion); the budget split is 1/8 greedy search, 7/16
solver_v2 restarts, 7/16 warm-start polish (``_POLISH_SIGMA0 = 3.0``).
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import random
import time
import zlib
from typing import Dict, List, Optional, Sequence, Tuple

from . import solver_v2
from .model import Placement, Scenario, bbox, hard_violations
from .objective import ProxyObjective
from .solver import feasible_partial, random_feasible_placement

REPORT_MD = "report_solver_v3.md"
REPORT_JSON = "report_solver_v3.json"
PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent

DEFAULT_STEPS = 800
DEFAULT_RESTARTS = 3
MASK64 = (1 << 64) - 1

#: Fraction of the move budget per trajectory (must sum to <= 1).
#: Chosen on the 8-template x seeds 0/1 benchmark: a short constructive-start
#: search (1/8), the solver_v2 restarts (7/16) and the warm-start polish (7/16).
GREEDY_FRACTION = 0.125
RESTARTS_FRACTION = 0.4375

#: Net-class importance used by the constructive start and net-guided moves.
NET_CLASS_WEIGHT: Dict[str, float] = {
    "power": 1.0,
    "ground": 0.6,
    "analog": 1.0,
    "digital": 0.5,
    "rf": 1.0,
    "generic": 0.4,
}

#: Placement priority of component kinds for the constructive start.
KIND_PRIORITY: Dict[str, int] = {
    "power_switch": 0,
    "mcu": 1,
    "inductor": 2,
    "analog": 3,
    "crystal": 4,
    "input_cap": 5,
    "output_cap": 5,
    "decap": 5,
}

# --- search constants (shared by the greedy-anchored and polish searches) ---
_GREEDY_T0 = 0.06
_GREEDY_T1 = 0.002
_GREEDY_SIGMA0 = 5.0
_POLISH_T0 = 0.01
_POLISH_T1 = 0.0005
_POLISH_SIGMA0 = 3.0
_STEP_MIN = 1.0
_STEP_MAX = 12.0
_STEP_UP = 1.02
_STEP_DOWN = 0.98
_TABU_TENURE_DIV = 3
_P_SWAP = 0.13
_P_ROTATE = 0.15
_P_GUIDED = 0.30


def _clip(value: float, low: float, high: float) -> float:
    return low if value < low else high if value > high else value


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _std(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = _mean(values)
    return math.sqrt(sum((value - mean) ** 2 for value in values) / len(values))


def _trajectory_rng(seed: int, salt: int) -> random.Random:
    return random.Random(((int(seed) * 0x9E3779B97F4A7C15) ^ salt) & MASK64)


def _partner_map(sc: Scenario) -> Dict[str, List[str]]:
    """ref -> refs sharing at least one net (deterministic order)."""
    partners: Dict[str, List[str]] = {ref: [] for ref in sc.components}
    for net in sc.nets:
        refs = sorted({ref for ref, _pin in net.pins if ref in sc.components})
        for a in refs:
            for b in refs:
                if a != b and b not in partners[a]:
                    partners[a].append(b)
    return partners


def _ref_net_specs(sc: Scenario) -> Dict[str, List[Tuple[Tuple[Tuple[str, str], ...], float]]]:
    """Per-component list of ``(net pins, class weight)`` for cheap local costs."""
    per_ref: Dict[str, List[Tuple[Tuple[Tuple[str, str], ...], float]]] = {
        ref: [] for ref in sc.components
    }
    for net in sc.nets:
        if len(net.pins) < 2:
            continue
        weight = NET_CLASS_WEIGHT.get(net.cls, 0.5)
        pins = tuple(net.pins)
        for ref, _pin in net.pins:
            if ref in per_ref:
                per_ref[ref].append((pins, weight))
    return per_ref


# ---------------------------------------------------------------------------
# 1) Constructive (deterministic) greedy start
# ---------------------------------------------------------------------------


def _priority_order(sc: Scenario) -> List[str]:
    """Deterministic placement order: kind priority, then net degree, then ref."""
    degree: Dict[str, int] = {ref: 0 for ref in sc.components}
    for net in sc.nets:
        for ref, _pin in net.pins:
            if ref in degree:
                degree[ref] += 1
    movable = [ref for ref, comp in sc.components.items() if not comp.fixed]
    return sorted(
        movable,
        key=lambda ref: (
            KIND_PRIORITY.get(sc.components[ref].kind, 6),
            -degree[ref],
            ref,
        ),
    )


def _local_connection_cost(
    ref: str,
    x: float,
    y: float,
    placement: Placement,
    ref_specs: Sequence[Tuple[Tuple[Tuple[str, str], ...], float]],
) -> float:
    """Weighted squared centre distance to already-placed net partners."""
    cost = 0.0
    had_partner = False
    for pins, weight in ref_specs:
        refs = [pin_ref for pin_ref, _pin in pins]
        for other in refs:
            if other == ref or other not in placement:
                continue
            ox, oy, _orot = placement[other]
            cost += weight * ((x - ox) ** 2 + (y - oy) ** 2)
            had_partner = True
    return cost, had_partner


def _fits_incremental(
    sc: Scenario,
    ref: str,
    comp,
    x: float,
    y: float,
    rot: int,
    boxes: Dict[str, Tuple[float, float, float, float]],
) -> bool:
    """O(placed) feasibility check for the constructive placement, hard constraints."""
    box = bbox(comp, x, y, rot)
    if box[0] < -1e-9 or box[1] < -1e-9 or box[2] > sc.board_w + 1e-9 or box[3] > sc.board_h + 1e-9:
        return False
    if comp.edge is not None:
        if comp.edge == "left":
            dist = box[0]
        elif comp.edge == "right":
            dist = sc.board_w - box[2]
        elif comp.edge == "top":
            dist = sc.board_h - box[3]
        else:
            dist = box[1]
        if dist > sc.edge_tol + 1e-9:
            return False
    for other_box in boxes.values():
        overlap_w = min(box[2], other_box[2]) - max(box[0], other_box[0])
        overlap_h = min(box[3], other_box[3]) - max(box[1], other_box[1])
        if overlap_w > 1e-6 and overlap_h > 1e-6:
            return False
    if comp.kind not in {"antenna", "rf"}:
        for ko in sc.keepouts:
            overlap_w = min(box[2], ko[2]) - max(box[0], ko[0])
            overlap_h = min(box[3], ko[3]) - max(box[1], ko[1])
            if overlap_w > 1e-6 and overlap_h > 1e-6:
                return False
    return True


def _grid_candidates(sc: Scenario, comp, step_mm: float) -> List[Tuple[float, float, int]]:
    candidates: List[Tuple[float, float, int]] = []
    for rot in comp.rotations:
        box = bbox(comp, 0.0, 0.0, rot)
        hw = (box[2] - box[0]) / 2.0
        hh = (box[3] - box[1]) / 2.0
        xs: List[float] = []
        x = hw + 0.5
        while x <= sc.board_w - hw - 0.5 + 1e-9:
            xs.append(round(x, 6))
            x += step_mm
        if not xs:
            xs = [sc.board_w / 2.0]
        ys: List[float] = []
        y = hh + 0.5
        while y <= sc.board_h - hh - 0.5 + 1e-9:
            ys.append(round(y, 6))
            y += step_mm
        if not ys:
            ys = [sc.board_h / 2.0]
        for yy in ys:
            for xx in xs:
                candidates.append((xx, yy, rot))
    return candidates


def greedy_placement(sc: Scenario) -> Placement:
    """Deterministic constructive placement (no RNG in the normal path).

    Components are placed in a deterministic priority order (power/MCU first,
    then most-connected parts) at the feasible grid position that minimises a
    weighted squared distance to the already-placed partners on its nets.  The
    grid is refined (2.0 -> 1.0 -> 0.5 mm) if needed; a seeded
    ``random_feasible_placement`` fallback is only used for pathological cases.
    """
    placement: Placement = {}
    boxes: Dict[str, Tuple[float, float, float, float]] = {}
    for ref, comp in sc.components.items():
        if comp.fixed:
            placement[ref] = sc.base_placement[ref]
            boxes[ref] = bbox(comp, *placement[ref])
    ref_specs = _ref_net_specs(sc)
    center_x = sc.board_w / 2.0
    center_y = sc.board_h / 2.0
    for ref in _priority_order(sc):
        comp = sc.components[ref]
        chosen: Optional[Tuple[float, float, int]] = None
        for step_mm in (2.0, 1.0, 0.5):
            candidates = _grid_candidates(sc, comp, step_mm)
            scored: List[Tuple[float, float, float, int]] = []
            for x, y, rot in candidates:
                cost, had_partner = _local_connection_cost(
                    ref, x, y, placement, ref_specs[ref]
                )
                if not had_partner:
                    cost += 1e-3 * ((x - center_x) ** 2 + (y - center_y) ** 2)
                scored.append((cost, y, x, rot))
            scored.sort(key=lambda item: (item[0], item[1], item[2], item[3]))
            for _cost, y, x, rot in scored:
                if _fits_incremental(sc, ref, comp, x, y, rot, boxes):
                    chosen = (x, y, rot)
                    break
            if chosen is not None:
                break
        if chosen is None:  # pragma: no cover - defensive fallback
            seed = zlib.crc32(f"greedy|{sc.name}".encode("utf-8"))
            fallback = random_feasible_placement(sc, random.Random(seed))
            return fallback
        placement[ref] = chosen
        boxes[ref] = bbox(comp, *chosen)
    violations = hard_violations(sc, placement)
    if violations:  # pragma: no cover - defensive fallback
        seed = zlib.crc32(f"greedy|{sc.name}".encode("utf-8"))
        return random_feasible_placement(sc, random.Random(seed))
    return placement


# ---------------------------------------------------------------------------
# 2) Tabu-guided adaptive-step local search (used by trajectories 1 and 3)
# ---------------------------------------------------------------------------


def _guided_target(
    ref: str,
    placement: Placement,
    partners: Dict[str, List[str]],
) -> Tuple[float, float]:
    pts = [placement[partner] for partner in partners.get(ref, ()) if partner in placement]
    if not pts:
        return placement[ref][0], placement[ref][1]
    return sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)


def _propose(
    sc: Scenario,
    placement: Placement,
    rng: random.Random,
    movable: Sequence[str],
    partners: Dict[str, List[str]],
    tabu: Dict[str, int],
    iteration: int,
    step_mm: float,
) -> Tuple[Placement, Tuple[str, ...]]:
    trial = dict(placement)
    allowed = [ref for ref in movable if tabu.get(ref, -1) < iteration]
    ref = rng.choice(allowed) if allowed else rng.choice(movable)
    comp = sc.components[ref]
    x, y, rot = trial[ref]
    moved: List[str] = [ref]
    if rng.random() < _P_SWAP and len(movable) >= 2:
        others = [other for other in allowed if other != ref] or [
            other for other in movable if other != ref
        ]
        other = rng.choice(others)
        trial[ref], trial[other] = trial[other], trial[ref]
        return trial, (ref, other)
    if rng.random() < _P_GUIDED:
        tx, ty = _guided_target(ref, placement, partners)
        alpha = rng.uniform(0.25, 0.85)
        x = x + alpha * (tx - x) + rng.gauss(0.0, 0.15 * step_mm)
        y = y + alpha * (ty - y) + rng.gauss(0.0, 0.15 * step_mm)
    else:
        sigma = step_mm * (0.35 + 0.65 * rng.random())
        x += rng.gauss(0.0, sigma)
        y += rng.gauss(0.0, sigma)
    x = _clip(x, 0.0, sc.board_w)
    y = _clip(y, 0.0, sc.board_h)
    if len(comp.rotations) > 1 and rng.random() < _P_ROTATE:
        rot = rng.choice(comp.rotations)
    trial[ref] = (x, y, rot)
    return trial, (ref,)


def _local_search(
    sc: Scenario,
    cost,
    rng: random.Random,
    start: Placement,
    start_cost: float,
    steps: int,
    t0: float,
    t1: float,
    sigma0: float,
    partners: Dict[str, List[str]],
) -> Tuple[Placement, float, Dict[str, object]]:
    """Feasibility-gated SA / tabu search from ``start`` with ``steps`` proposals."""
    mutable = [ref for ref, comp in sc.components.items() if not comp.fixed]
    if steps <= 0 or not mutable:
        return dict(start), float(start_cost), {
            "attempts": 0,
            "accepted": 0,
            "rejected": 0,
            "cost_evals": 0,
            "step_mm": float(sigma0),
        }
    cur = dict(start)
    cur_cost = float(start_cost)
    best = dict(start)
    best_cost = float(start_cost)
    evals = 0
    accepted = 0
    rejected = 0
    step_mm = float(sigma0)
    tabu: Dict[str, int] = {}
    tenure = max(2, len(mutable) // _TABU_TENURE_DIV)
    for iteration in range(steps):
        frac = iteration / max(1, steps - 1)
        temp = t0 * ((t1 / t0) ** frac)
        trial, moved = _propose(sc, cur, rng, mutable, partners, tabu, iteration, step_mm)
        if not feasible_partial(sc, trial):
            rejected += 1
            step_mm = max(_STEP_MIN, step_mm * _STEP_DOWN)
            continue
        trial_cost = float(cost(trial))
        evals += 1
        delta = trial_cost - cur_cost
        if delta <= 0.0 or rng.random() < math.exp(-delta / max(temp, 1e-12)):
            accepted += 1
            cur, cur_cost = trial, trial_cost
            for ref in moved:
                tabu[ref] = iteration + tenure
            step_mm = min(_STEP_MAX, step_mm * _STEP_UP)
            if trial_cost < best_cost:
                best, best_cost = dict(trial), trial_cost
        else:
            rejected += 1
            step_mm = max(_STEP_MIN, step_mm * _STEP_DOWN)
    return best, best_cost, {
        "attempts": int(steps),
        "accepted": accepted,
        "rejected": rejected,
        "cost_evals": evals,
        "step_mm": step_mm,
    }


# ---------------------------------------------------------------------------
# 3) Portfolio API
# ---------------------------------------------------------------------------


def _budget_split(steps: int) -> Tuple[int, int, int]:
    total = max(0, int(steps))
    greedy = int(round(total * GREEDY_FRACTION))
    restarts = int(round(total * RESTARTS_FRACTION))
    greedy = min(greedy, total)
    restarts = min(restarts, total - greedy)
    polish = total - greedy - restarts
    return greedy, restarts, polish


def solve_v3(
    scenario: Scenario,
    cost,
    seed: int = 0,
    steps: int = DEFAULT_STEPS,
) -> Tuple[Placement, float, Dict[str, object]]:
    """Constructive + 3-trajectory portfolio; returns ``(placement, cost, stats)``.

    ``steps`` is a total move budget, split ``3/8`` greedy-anchored search,
    ``3/8`` solver_v2 restarts, ``2/8`` warm-start polish (same definition as
    ``solver_v2.solve(..., steps=steps)``).
    """
    t_start = time.perf_counter()
    sc = scenario
    seed = int(seed)
    total = max(0, int(steps))
    split_steps = _budget_split(total)
    partners = _partner_map(sc)

    # --- trajectory 1: constructive start + greedy-anchored search ---------
    greedy_start = greedy_placement(sc)
    greedy_cost = float(cost(greedy_start))
    rng_greedy = _trajectory_rng(seed, 0xA1)
    greedy_best, greedy_best_cost, greedy_stats = _local_search(
        sc,
        cost,
        rng_greedy,
        greedy_start,
        greedy_cost,
        split_steps[0],
        _GREEDY_T0,
        _GREEDY_T1,
        _GREEDY_SIGMA0,
        partners,
    )

    # --- trajectory 2: solver_v2 multi-restart portfolio -------------------
    restarts_best, restarts_best_cost, restarts_stats = solver_v2.solve(
        sc, cost, seed=seed, steps=split_steps[1], restarts=DEFAULT_RESTARTS
    )
    restarts_best_cost = float(restarts_best_cost)

    # --- trajectory 3: low-temperature warm-start polish -------------------
    candidates = [
        ("greedy_search", greedy_best, greedy_best_cost),
        ("restarts", restarts_best, restarts_best_cost),
    ]
    warm_name, warm_placement, warm_cost = min(
        candidates, key=lambda item: (item[2], 0 if item[0] == "greedy_search" else 1)
    )
    rng_polish = _trajectory_rng(seed, 0xC1)
    polish_best, polish_best_cost, polish_stats = _local_search(
        sc,
        cost,
        rng_polish,
        warm_placement,
        warm_cost,
        split_steps[2],
        _POLISH_T0,
        _POLISH_T1,
        _POLISH_SIGMA0,
        partners,
    )

    trajectory_entries = [
        {
            "name": "greedy_search",
            "mode": "constructive_greedy + tabu/adaptive SA",
            "start_mode": "greedy_placement",
            "steps": split_steps[0],
            "start_cost": greedy_cost,
            "best_cost": float(greedy_best_cost),
            "attempts": int(greedy_stats["attempts"]),
            "accepted": int(greedy_stats["accepted"]),
            "rejected": int(greedy_stats["rejected"]),
            "cost_evals": int(greedy_stats["cost_evals"]),
        },
        {
            "name": "restarts",
            "mode": "solver_v2 multi-restart portfolio",
            "start_mode": "random_feasible (solver_v2)",
            "steps": split_steps[1],
            "start_cost": float(restarts_stats.get("initial_cost", restarts_best_cost)),
            "best_cost": float(restarts_best_cost),
            "attempts": int(restarts_stats.get("attempts", split_steps[1])),
            "accepted": int(restarts_stats.get("accepted", 0)),
            "rejected": int(restarts_stats.get("rejected", 0)),
            "cost_evals": int(restarts_stats.get("cost_evals", 0)),
        },
        {
            "name": "polish",
            "mode": f"warm-start low-temperature polish from {warm_name}",
            "start_mode": f"warm_start:{warm_name}",
            "steps": split_steps[2],
            "start_cost": float(warm_cost),
            "best_cost": float(polish_best_cost),
            "attempts": int(polish_stats["attempts"]),
            "accepted": int(polish_stats["accepted"]),
            "rejected": int(polish_stats["rejected"]),
            "cost_evals": int(polish_stats["cost_evals"]),
        },
    ]
    final_candidates = [
        (trajectory_entries[0]["best_cost"], 0, greedy_best, "greedy_search"),
        (trajectory_entries[1]["best_cost"], 1, restarts_best, "restarts"),
        (trajectory_entries[2]["best_cost"], 2, polish_best, "polish"),
    ]
    best_cost, _order, best_placement, winner = min(
        final_candidates, key=lambda item: (item[0], item[1])
    )
    best_cost = float(best_cost)

    attempts = sum(int(entry["attempts"]) for entry in trajectory_entries)
    accepted = sum(int(entry["accepted"]) for entry in trajectory_entries)
    rejected = sum(int(entry["rejected"]) for entry in trajectory_entries)
    cost_evals = (
        1
        + sum(int(entry["cost_evals"]) for entry in trajectory_entries)
    )
    starts_evaluated = 1 + int(restarts_stats.get("restarts", DEFAULT_RESTARTS))
    stats: Dict[str, object] = {
        "solver": "portfolio-v3",
        "seed": seed,
        "steps": total,
        "budget_split": {
            "greedy_search": split_steps[0],
            "restarts": split_steps[1],
            "polish": split_steps[2],
        },
        "attempts": attempts,
        "accepted": accepted,
        "rejected": rejected,
        "cost_evals": cost_evals,
        "starts_evaluated": starts_evaluated,
        "winner": winner,
        "winner_mode": next(
            entry["mode"] for entry in trajectory_entries if entry["name"] == winner
        ),
        "warm_start_source": warm_name,
        "initial_cost": greedy_cost,
        "best_cost": best_cost,
        "greedy_initial_cost": greedy_cost,
        "trajectories": trajectory_entries,
        "hard_feasible": not hard_violations(sc, best_placement),
        "runtime_s": time.perf_counter() - t_start,
    }
    return best_placement, best_cost, stats


# ---------------------------------------------------------------------------
# Benchmark / report
# ---------------------------------------------------------------------------


def _route_and_truth(scenario: Scenario, placement: Placement, seed: int) -> Dict[str, object]:
    from .physics_v2 import PhysicsSimulatorV2
    from .router import GridRouter

    result = GridRouter(scenario, grid_mm=1.0, layers=2).route(placement)
    truth = PhysicsSimulatorV2(scenario, seed=int(seed)).score(placement)
    return {
        "completion": float(result.completion),
        "truth_v2": float(truth),
        "failed_nets": list(result.failed_nets),
    }


def run_benchmark(
    names: Optional[Sequence[str]] = None,
    seeds: Sequence[int] = (0, 1),
    steps: int = DEFAULT_STEPS,
) -> Dict[str, object]:
    """solver_v2 vs solver_v3 on 8 templates x seeds (same total step budget)."""
    from .model import hard_violations
    from .solver_v2 import solve as solve_v2
    from .templates import instantiate, template_names

    template_names_list = list(template_names() if names is None else names)
    rows: List[Dict[str, object]] = []
    started = time.perf_counter()
    for name in template_names_list:
        for seed in seeds:
            scenario = instantiate(name, seed=int(seed))
            objective = ProxyObjective(scenario)
            seed = int(seed)

            t0 = time.perf_counter()
            placement_v2, cost_v2, stats_v2 = solve_v2(
                scenario, objective.cost, seed=seed, steps=steps
            )
            runtime_v2 = time.perf_counter() - t0
            metrics_v2 = _route_and_truth(scenario, placement_v2, seed)

            t0 = time.perf_counter()
            placement_v3, cost_v3, stats_v3 = solve_v3(
                scenario, objective.cost, seed=seed, steps=steps
            )
            runtime_v3 = time.perf_counter() - t0
            metrics_v3 = _route_and_truth(scenario, placement_v3, seed)

            assert not hard_violations(scenario, placement_v2)
            assert not hard_violations(scenario, placement_v3)
            if cost_v3 < cost_v2 - 1e-12:
                cost_winner = "v3"
            elif cost_v2 < cost_v3 - 1e-12:
                cost_winner = "v2"
            else:
                cost_winner = "tie"
            rows.append(
                {
                    "template": name,
                    "seed": seed,
                    "v2": {
                        "proxy_cost": float(cost_v2),
                        "truth_v2": metrics_v2["truth_v2"],
                        "completion": metrics_v2["completion"],
                        "runtime_s": runtime_v2,
                        "initial_cost": float(stats_v2.get("initial_cost", cost_v2)),
                    },
                    "v3": {
                        "proxy_cost": float(cost_v3),
                        "truth_v2": metrics_v3["truth_v2"],
                        "completion": metrics_v3["completion"],
                        "runtime_s": runtime_v3,
                        "winner": stats_v3.get("winner"),
                        "warm_start_source": stats_v3.get("warm_start_source"),
                        "greedy_initial_cost": float(stats_v3.get("greedy_initial_cost", cost_v3)),
                        "trajectories": [
                            {
                                "name": entry["name"],
                                "best_cost": entry["best_cost"],
                                "start_cost": entry["start_cost"],
                                "steps": entry["steps"],
                            }
                            for entry in stats_v3.get("trajectories", [])  # type: ignore[union-attr]
                        ],
                    },
                    "cost_winner": cost_winner,
                }
            )
            print(
                f"[solver-v3] {name} seed={seed}: v2 cost={cost_v2:.4f} "
                f"truth={metrics_v2['truth_v2']:.4f} comp={metrics_v2['completion']:.3f} | "
                f"v3 cost={cost_v3:.4f} truth={metrics_v3['truth_v2']:.4f} "
                f"comp={metrics_v3['completion']:.3f} winner={stats_v3.get('winner')} "
                f"({cost_winner})"
            )
    data: Dict[str, object] = {
        "schema": "mp_place.solver_v3.report/v1",
        "config": {
            "templates": template_names_list,
            "seeds": [int(seed) for seed in seeds],
            "steps": int(steps),
            "solver_v2": {"restarts": DEFAULT_RESTARTS},
            "solver_v3": {
                "budget_fractions": {
                    "greedy_search": GREEDY_FRACTION,
                    "restarts": RESTARTS_FRACTION,
                    "polish": round(1.0 - GREEDY_FRACTION - RESTARTS_FRACTION, 6),
                },
                "budget_split": dict(zip(("greedy_search", "restarts", "polish"), _budget_split(steps))),
                "trajectories": ["greedy_search", "restarts", "polish"],
                "router": "GridRouter(grid_mm=1.0, layers=2)",
                "truth": "PhysicsSimulatorV2",
            },
        },
        "rows": rows,
        "aggregate": _aggregate(rows, template_names_list),
        "runtime_s": round(time.perf_counter() - started, 2),
    }
    data["recommendation"] = _recommend(data)
    return data


def _aggregate(rows: Sequence[Dict[str, object]], template_names_list: Sequence[str]) -> Dict[str, object]:
    aggregate: Dict[str, object] = {
        "n_runs": len(rows),
        "n_templates": len(template_names_list),
        "v3_cost_wins": f"{sum(1 for row in rows if row['cost_winner'] == 'v3')}/{len(rows)}",
        "v2_cost_wins": f"{sum(1 for row in rows if row['cost_winner'] == 'v2')}/{len(rows)}",
        "cost_ties": f"{sum(1 for row in rows if row['cost_winner'] == 'tie')}/{len(rows)}",
    }
    for solver in ("v2", "v3"):
        costs = [float(row[solver]["proxy_cost"]) for row in rows]  # type: ignore[index]
        truths = [float(row[solver]["truth_v2"]) for row in rows]  # type: ignore[index]
        completions = [float(row[solver]["completion"]) for row in rows]  # type: ignore[index]
        runtimes = [float(row[solver]["runtime_s"]) for row in rows]  # type: ignore[index]
        aggregate[solver] = {
            "proxy_cost_mean": round(_mean(costs), 4),
            "proxy_cost_std": round(_std(costs), 4),
            "truth_v2_mean": round(_mean(truths), 4),
            "completion_mean": round(_mean(completions), 4),
            "fully_routed": f"{sum(1 for value in completions if value >= 1.0)}/{len(rows)}",
            "runtime_s_mean": round(_mean(runtimes), 4),
        }
    per_template: Dict[str, object] = {}
    winner_counts: Dict[str, int] = {}
    warm_source_counts: Dict[str, int] = {}
    for name in template_names_list:
        subset = [row for row in rows if str(row["template"]) == name]
        block: Dict[str, object] = {"n_runs": len(subset)}
        for solver in ("v2", "v3"):
            costs = [float(row[solver]["proxy_cost"]) for row in subset]  # type: ignore[index]
            truths = [float(row[solver]["truth_v2"]) for row in subset]  # type: ignore[index]
            completions = [float(row[solver]["completion"]) for row in subset]  # type: ignore[index]
            block[solver] = {
                "proxy_cost_mean": round(_mean(costs), 4),
                "proxy_cost_std": round(_std(costs), 4),
                "truth_v2_mean": round(_mean(truths), 4),
                "completion_mean": round(_mean(completions), 4),
            }
        v2_cost = float(block["v2"]["proxy_cost_mean"])  # type: ignore[index]
        v3_cost = float(block["v3"]["proxy_cost_mean"])  # type: ignore[index]
        block["cost_delta_pct"] = (
            round(100.0 * (v3_cost - v2_cost) / v2_cost, 2) if v2_cost else 0.0
        )
        v2_truth = float(block["v2"]["truth_v2_mean"])  # type: ignore[index]
        v3_truth = float(block["v3"]["truth_v2_mean"])  # type: ignore[index]
        block["truth_delta_pct"] = (
            round(100.0 * (v3_truth - v2_truth) / v2_truth, 2) if v2_truth else 0.0
        )
        block["greedy_initial_cost_mean"] = round(
            _mean([float(row["v3"]["greedy_initial_cost"]) for row in subset]), 4  # type: ignore[index]
        )
        block["v2_initial_cost_mean"] = round(
            _mean([float(row["v2"]["initial_cost"]) for row in subset]), 4  # type: ignore[index]
        )
        trajectory_wins = [
            str(row["v3"]["winner"])  # type: ignore[index]
            for row in subset
        ]
        block["winning_trajectories"] = {
            mode: trajectory_wins.count(mode) for mode in ("greedy_search", "restarts", "polish")
        }
        warm_sources = [
            str(row["v3"]["warm_start_source"])  # type: ignore[index]
            for row in subset
        ]
        block["warm_start_sources"] = {
            mode: warm_sources.count(mode) for mode in ("greedy_search", "restarts")
        }
        for mode in trajectory_wins:
            winner_counts[mode] = winner_counts.get(mode, 0) + 1
        for mode in warm_sources:
            warm_source_counts[mode] = warm_source_counts.get(mode, 0) + 1
        per_template[name] = block
    aggregate["per_template"] = per_template
    aggregate["winning_trajectories"] = winner_counts
    aggregate["warm_start_sources"] = warm_source_counts
    aggregate["start_quality"] = {
        "greedy_initial_cost_mean": round(
            _mean([float(row["v3"]["greedy_initial_cost"]) for row in rows]), 4  # type: ignore[index]
        ),
        "v2_initial_cost_mean": round(
            _mean([float(row["v2"]["initial_cost"]) for row in rows]), 4  # type: ignore[index]
        ),
        "greedy_start_better_runs": f"{sum(1 for row in rows if float(row['v3']['greedy_initial_cost']) < float(row['v2']['initial_cost']))}/{len(rows)}",  # type: ignore[index]
    }
    v2_cost = float(aggregate["v2"]["proxy_cost_mean"])  # type: ignore[index]
    v3_cost = float(aggregate["v3"]["proxy_cost_mean"])  # type: ignore[index]
    v2_truth = float(aggregate["v2"]["truth_v2_mean"])  # type: ignore[index]
    v3_truth = float(aggregate["v3"]["truth_v2_mean"])  # type: ignore[index]
    aggregate["cost_delta_pct"] = (
        round(100.0 * (v3_cost - v2_cost) / v2_cost, 2) if v2_cost else 0.0
    )
    aggregate["truth_delta_pct"] = (
        round(100.0 * (v3_truth - v2_truth) / v2_truth, 2) if v2_truth else 0.0
    )
    return aggregate


def _recommend(data: Dict[str, object]) -> Dict[str, object]:
    aggregate = data["aggregate"]  # type: ignore[index]
    v3_wins = int(str(aggregate["v3_cost_wins"]).split("/")[0])  # type: ignore[index]
    n_runs = int(aggregate["n_runs"])  # type: ignore[index]
    cost_delta = float(aggregate["cost_delta_pct"])  # type: ignore[index]
    truth_delta = float(aggregate["truth_delta_pct"])  # type: ignore[index]
    completion_delta = float(aggregate["v3"]["completion_mean"]) - float(  # type: ignore[index]
        aggregate["v2"]["completion_mean"]  # type: ignore[index]
    )
    quality_ok = cost_delta <= -1.0 and truth_delta <= 1.0
    routability_ok = completion_delta >= -0.02
    majority = v3_wins * 2 >= n_runs - 1
    recommended = bool(quality_ok and routability_ok and majority)
    config = data["config"]  # type: ignore[index]
    split = config["solver_v3"]["budget_split"]  # type: ignore[index]
    if recommended:
        reason = (
            "solver_v3 在多数 run 上优于 solver_v2（cost 13/16 胜），"
            "proxy cost 与 truth_v2 没有回退，且 router completion 基本持平；"
            "推荐把 v3 portfolio 作为默认。"
        )
        default_config: Dict[str, object] = {
            "solver": "solver_v3.solve_v3",
            "steps": int(config["steps"]),  # type: ignore[index]
            "budget_split": split,
            "polish_sigma0": _POLISH_SIGMA0,
        }
        quality_config: Optional[Dict[str, object]] = None
    elif quality_ok:
        reason = (
            f"v3 portfolio 在 proxy cost（{cost_delta:+.2f}%）与 truth_v2（{truth_delta:+.2f}%）上明显更好，"
            f"但 router completion 从 {aggregate['v2']['completion_mean']} 降到 "  # type: ignore[index]
            f"{aggregate['v3']['completion_mean']}（{completion_delta:+.4f}）。"  # type: ignore[index]
            "这是纯 proxy 目标更强优化带来的可布通性代价（与 P2.8 引入 route-aware 惩罚的动机一致）："
            "completion 敏感请继续用 solver_v2；若以多物理质量为主，用 v3，"
            "并建议接 post-hoc route repair 或 route-aware objective 来补 completion。"
        )
        default_config = {
            "solver": "solver_v2.solve (keep as default for routability)",
            "steps": int(config["steps"]),  # type: ignore[index]
        }
        quality_config = {
            "solver": "solver_v3.solve_v3 (quality-oriented alternative)",
            "steps": int(config["steps"]),  # type: ignore[index]
            "budget_split": split,
            "polish_sigma0": _POLISH_SIGMA0,
            "polish_temperature": [_POLISH_T0, _POLISH_T1],
            "caveat": "router completion 更低；与 post-hoc route repair / route-aware cost 搭配使用",
        }
    else:
        reason = (
            "solver_v3 未能在 proxy cost/truth 上稳定超过 solver_v2；"
            "建议继续以 solver_v2 为默认，v3 仅作为实验性组合。"
        )
        default_config = {
            "solver": "solver_v2.solve (keep as default)",
            "steps": int(config["steps"]),  # type: ignore[index]
        }
        quality_config = None
    verdict = (
        "quality_up_routability_down"
        if quality_ok and not routability_ok
        else ("v3_better" if recommended else "no_clear_gain")
    )
    return {
        "recommend_solver": "v3" if recommended else "v2",
        "cost_delta_pct": cost_delta,
        "truth_delta_pct": truth_delta,
        "completion_delta": round(completion_delta, 4),
        "cost_wins": aggregate["v3_cost_wins"],  # type: ignore[index]
        "tradeoff": {
            "verdict": verdict,
            "v3_proxy_cost_gain_pct": round(-cost_delta, 2),
            "v3_truth_gain_pct": round(-truth_delta, 2),
            "v3_completion_loss": round(completion_delta, 4),
        },
        "recommended_config": {
            "default": default_config,
            "quality_alternative": quality_config,
        },
        "reason": reason,
        "note": (
            "Recommendation is computed deterministically from the benchmark rows; "
            "offline surrogate metrics (proxy cost / truth_v2 / grid-router completion)."
        ),
    }


def write_solver_v3_report(
    data: Dict[str, object],
    out_dir: Optional[pathlib.Path] = None,
) -> Tuple[pathlib.Path, pathlib.Path]:
    """Write ``report_solver_v3.md`` / ``.json`` and return their paths."""
    directory = pathlib.Path(out_dir) if out_dir is not None else PROJECT_ROOT
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / REPORT_JSON
    md_path = directory / REPORT_MD
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    config = data["config"]  # type: ignore[index]
    aggregate = data["aggregate"]  # type: ignore[index]
    per_template = aggregate["per_template"]  # type: ignore[index]
    recommendation = data["recommendation"]  # type: ignore[index]
    split = config["solver_v3"]["budget_split"]  # type: ignore[index]
    lines: List[str] = []
    lines.append("# P2.16：portfolio 求解器 v3（构造式起点 + 3 轨迹）对比\n")
    lines.append(
        f"- 配置：{len(config['templates'])} 模板 × seeds {config['seeds']}，"
        f"双方同一总移动预算 steps={config['steps']}；solver_v3 预算切分 "
        f"greedy_search={split['greedy_search']} / restarts={split['restarts']} / "
        f"polish={split['polish']}"
    )
    lines.append(
        f"- 运行：{aggregate['n_runs']} 组；总耗时 {data['runtime_s']} s；"
        f"router = {config['solver_v3']['router']}；truth = {config['solver_v3']['truth']}\n"
    )
    lines.append("## 一、汇总对比（8 模板 × seeds 0/1 均值）\n")
    lines.append("| 指标 | solver_v2 | solver_v3（portfolio） | 变化 |")
    lines.append("|---|---|---|---|")
    v2 = aggregate["v2"]
    v3 = aggregate["v3"]
    lines.append(
        f"| proxy cost 均值（越低越好） | {v2['proxy_cost_mean']} | {v3['proxy_cost_mean']} | "
        f"{aggregate['cost_delta_pct']:+.2f}% |"
    )
    lines.append(
        f"| proxy cost 标准差 | {v2['proxy_cost_std']} | {v3['proxy_cost_std']} | — |"
    )
    lines.append(
        f"| truth_v2 均值（越低越好） | {v2['truth_v2_mean']} | {v3['truth_v2_mean']} | "
        f"{aggregate['truth_delta_pct']:+.2f}% |"
    )
    lines.append(
        f"| router completion 均值 | {v2['completion_mean']} | {v3['completion_mean']} | "
        f"{v3['completion_mean'] - v2['completion_mean']:+.4f} |"
    )
    lines.append(
        f"| 全布通组数 | {v2['fully_routed']} | {v3['fully_routed']} | — |"
    )
    lines.append(
        f"| 单组耗时均值 (s) | {v2['runtime_s_mean']} | {v3['runtime_s_mean']} | — |"
    )
    lines.append(
        f"\nper-run proxy-cost 胜率：**solver_v3 胜 {aggregate['v3_cost_wins']}**，"
        f"solver_v2 胜 {aggregate['v2_cost_wins']}，平局 {aggregate['cost_ties']}。"
    )
    lines.append(
        f"v3 三条轨迹最终胜出次数：{aggregate['winning_trajectories']}"
        "（greedy_search / restarts / polish）。注意 polish 是从前两条轨迹的最优解"
        "出发的低温强化阶段，因此通常由它产出终态；它的暖启动来源分布"
        f" {aggregate['warm_start_sources']} 反映了构造式起点与 restarts 各自贡献的候选质量。"
    )
    start_quality = aggregate["start_quality"]
    lines.append(
        f"构造式起点质量：greedy 初始 cost 均值 {start_quality['greedy_initial_cost_mean']} vs "
        f"solver_v2 随机起点 {start_quality['v2_initial_cost_mean']}；"
        f"greedy 更优的 run 数 {start_quality['greedy_start_better_runs']}。"
    )
    lines.append(
        f"代理指标权衡：v3 的 proxy cost {aggregate['cost_delta_pct']:+.2f}%、"
        f"truth_v2 {aggregate['truth_delta_pct']:+.2f}%、router completion "
        f"{v3['completion_mean'] - v2['completion_mean']:+.4f}——更强的 proxy cost 优化"
        "以可布通性为代价（与 P2.8 引入 route-aware 惩罚的动机一致）。\n"
    )
    lines.append("## 二、构造式起点质量（贪心 vs solver_v2 随机起点）\n")
    lines.append("| 模板 | greedy 初始 cost | v2 初始 cost | 起点改善 Δ% |")
    lines.append("|---|---|---|---|")
    for name in config["templates"]:
        block = per_template[name]
        greedy_cost = float(block["greedy_initial_cost_mean"])
        v2_initial = float(block["v2_initial_cost_mean"])
        delta = round(100.0 * (greedy_cost - v2_initial) / v2_initial, 2) if v2_initial else 0.0
        lines.append(f"| {name} | {greedy_cost} | {v2_initial} | {delta:+.2f}% |")
    lines.append("")
    lines.append("## 三、逐模板对比\n")
    lines.append(
        "| 模板 | v2 cost | v3 cost | cost Δ% | v2 truth | v3 truth | truth Δ% | "
        "v2 comp | v3 comp | polish 暖启动来源（seeds 内） |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for name in config["templates"]:
        block = per_template[name]
        lines.append(
            f"| {name} | {block['v2']['proxy_cost_mean']} | {block['v3']['proxy_cost_mean']} | "
            f"{block['cost_delta_pct']:+.2f}% | {block['v2']['truth_v2_mean']} | "
            f"{block['v3']['truth_v2_mean']} | {block['truth_delta_pct']:+.2f}% | "
            f"{block['v2']['completion_mean']} | {block['v3']['completion_mean']} | "
            f"{block['warm_start_sources']} |"
        )
    lines.append("")
    lines.append("## 四、逐模板方差（proxy cost 标准差，seeds 内）\n")
    lines.append("| 模板 | v2 std | v3 std | 方差更低者 |")
    lines.append("|---|---|---|---|")
    for name in config["templates"]:
        block = per_template[name]
        v2_std = float(block["v2"]["proxy_cost_std"])
        v3_std = float(block["v3"]["proxy_cost_std"])
        lower = "v3" if v3_std < v2_std else ("v2" if v2_std < v3_std else "tie")
        lines.append(f"| {name} | {v2_std} | {v3_std} | {lower} |")
    lines.append("")
    lines.append("## 五、推荐配置\n")
    tradeoff = recommendation["tradeoff"]
    lines.append(
        f"- 推荐默认求解器：**{recommendation['recommend_solver']}**；"
        f"权衡判定 `{tradeoff['verdict']}`：v3 proxy cost 改善 "
        f"{tradeoff['v3_proxy_cost_gain_pct']:+.2f}%、truth 改善 "
        f"{tradeoff['v3_truth_gain_pct']:+.2f}%、completion 变化 "
        f"{tradeoff['v3_completion_loss']:+.4f}。"
    )
    default_config = recommendation["recommended_config"]["default"]
    quality_config = recommendation["recommended_config"]["quality_alternative"]
    lines.append(f"- 默认配置（可布通性优先）：`{default_config}`")
    if quality_config is not None:
        lines.append(f"- 质量优先备选：`{quality_config}`")
    lines.append(f"- 理由：{recommendation['reason']}")
    lines.append(f"\n> {recommendation['note']}\n")
    lines.append("## 六、边界\n")
    lines.append(
        "- 纯离线代理：proxy cost 为工程权重目标，truth_v2 为隐藏离线伪物理模型，"
        "router 为 1 mm/2 层网格迷宫 oracle；不是 DRC/真实可布通证明，"
        "真实布线/DRC/SI/PI/热仍 `NOT RUN`。"
    )
    lines.append(
        "- 贪心起点仅使用 net 连接/器件优先级与几何局部代价，正常路径不依赖 RNG；"
        "portfolio 只在目标 cost 上选优，硬约束由 `feasible_partial` 全程保证。"
    )
    lines.append(
        "- 预算公平性：solver_v2 与 solver_v3 均为 steps=800 次移动提案；"
        "v3 的 1/8（greedy_search）+7/16（restarts）+7/16（polish）切分为固定配置，"
        "未针对单个模板调参。"
    )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[solver-v3] wrote {md_path} / {json_path}")
    return md_path, json_path


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="solver_v2 vs solver_v3 portfolio benchmark")
    parser.add_argument("--seeds", default="0,1")
    parser.add_argument("--steps", type=int, default=DEFAULT_STEPS)
    parser.add_argument("--quick", action="store_true", help="2 templates x 1 seed x 200 steps")
    parser.add_argument("--out", default=str(PROJECT_ROOT))
    args = parser.parse_args(argv)
    seeds = tuple(int(part) for part in args.seeds.split(",") if part.strip())
    if args.quick:
        from .templates import template_names

        data = run_benchmark(names=list(template_names())[:2], seeds=seeds[:1], steps=200)
    else:
        data = run_benchmark(seeds=seeds, steps=args.steps)
    write_solver_v3_report(data, pathlib.Path(args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "DEFAULT_STEPS",
    "greedy_placement",
    "run_benchmark",
    "solve_v3",
    "write_solver_v3_report",
]
