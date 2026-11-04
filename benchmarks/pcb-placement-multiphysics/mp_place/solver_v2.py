"""Portfolio placement solver (P2) — tabu-guided, adaptive-step annealing.

Public API
----------
``solve(scenario, cost, seed=0, steps=2000, restarts=3)``
    -> ``(best_placement, best_cost, stats)``

The solver is a *portfolio* over deterministic restarts.  ``steps`` is the
**total** move budget (not per restart): it is split across ``restarts`` starts,
so ``solve(..., steps=N)`` spends the same number of move proposals as
``Annealer(..., steps=N)`` and is budget-comparable with it.

Each restart
  * starts from a hard-feasible placement built by
    :func:`mp_place.solver.random_feasible_placement` (or, for the last restart,
    from a perturbed global best — intensification);
  * runs a simulated-annealing / tabu hybrid: every proposal is gated by
    :func:`mp_place.solver.feasible_partial`, so **only hard-feasible placements
    are ever visited**; the moved component(s) are tabu for a short tenure so
    the search does not cycle on one part;
  * adapts its translation step size online (grows after accepted moves,
    shrinks after rejected ones) — a 1/5-success-rule style adaptation;
  * mixes Gaussian translation, net-guided translation (pull a component toward
    the mean centre of its electrically connected partners), rotation and swap
    moves.

Determinism: all randomness flows from ``seed`` (one RNG per restart derived
from it); identical inputs produce identical placements/costs.  The only
non-deterministic field is ``stats["runtime_s"]``.

Stats keys: ``accepted``, ``rejected``, ``attempts``, ``best_iter``,
``restarts``, ``runtime_s``, plus ``cost_evals``, ``initial_cost``,
``best_cost``, ``restart_best_costs``, ``start_modes``, ``steps``, ``seed``.

Benchmark (recorded reference run; ``build_scenarios(seed=0)`` x ``ProxyObjective``,
``steps=1200``, ``seeds=0/1/2``, ``restarts=3``; per-scenario mean final cost,
lower is better; same total move budget for both solvers; wall clock on the
recording machine, times are informative only)::

    scenario   Annealer mean   solve mean    delta     Annealer s   solve s
    mcu-min    2.4741          2.2562        -8.8%     0.285        0.248
    buck       3.1280          2.9984        -4.1%     0.249        0.238
    rs485      2.7874          2.2361       -19.8%     0.156        0.151
    motor      4.2654          3.2702       -23.3%     0.168        0.169
    wireless   3.4152          3.0965        -9.3%     0.190        0.170
    -----------------------------------------------------------------------
    total      16.0701         13.8574       -13.8%     0.210        0.195

Reproduce with::

    from mp_place.scenarios import build_scenarios
    from mp_place.objective import ProxyObjective
    from mp_place.solver import Annealer
    from mp_place.solver_v2 import solve
    for sc in build_scenarios(seed=0):
        obj = ProxyObjective(sc)
        for seed in (0, 1, 2):
            a = Annealer(sc, obj.cost, seed=seed, steps=1200).run()
            b = solve(sc, obj.cost, seed=seed, steps=1200, restarts=3)
"""

from __future__ import annotations

import math
import random
import time
from typing import Callable, Dict, List, Tuple

from .model import Placement, Scenario
from .solver import feasible_partial, random_feasible_placement

ObjectiveFn = Callable[[Placement], float]

# --- tunable search constants -------------------------------------------
_T0 = 0.06  # initial SA temperature
_T1 = 0.002  # final SA temperature
_STEP0 = 5.0  # initial translation sigma (mm)
_STEP_MIN = 1.0
_STEP_MAX = 12.0
_STEP_UP = 1.02  # sigma multiplier on accepted move
_STEP_DOWN = 0.98  # sigma multiplier on rejected move
_TABU_TENURE_DIV = 3  # tabu tenure = max(2, n_movable // this)
_P_SWAP = 0.13
_P_ROTATE = 0.15
_P_GUIDED = 0.30  # among translate moves: probability of net-guided target
_LAST_RESTART_FROM_BEST = True
_PERTURB_MOVES = 4
# Optional relative budget weights per restart (None == equal split).
_BUDGET_WEIGHTS = None


def _split_budget(steps: int, restarts: int) -> List[int]:
    """Split the total move budget across restarts; sum(budgets) == steps."""
    total = max(0, int(steps))
    n = max(1, int(restarts))
    if total == 0:
        return [0]
    n = min(n, total)
    weights = _BUDGET_WEIGHTS
    if weights and len(weights) >= n:
        w = [max(1e-9, float(x)) for x in weights[:n]]
        raw = [total * x / sum(w) for x in w]
        budgets = [max(1, int(math.floor(v))) for v in raw]
        # Fix rounding drift: hand out/remove from the largest fractions.
        drift = total - sum(budgets)
        order = sorted(range(n), key=lambda i: raw[i] - math.floor(raw[i]), reverse=(drift > 0))
        k = 0
        while drift != 0:
            i = order[k % n]
            if drift > 0:
                budgets[i] += 1
                drift -= 1
            elif budgets[i] > 1:
                budgets[i] -= 1
                drift += 1
            k += 1
        return budgets
    base, rem = divmod(total, n)
    return [base + (1 if i < rem else 0) for i in range(n)]


def _restart_rng(seed: int, index: int) -> random.Random:
    """Deterministic per-restart RNG (independent streams, seed-derived)."""
    salt = ((int(seed) * 0x9E3779B97F4A7C15) ^ (index * 0xBF58476D1CE4E5B9)) & ((1 << 64) - 1)
    return random.Random(salt)


def _partner_map(sc: Scenario) -> Dict[str, List[str]]:
    """ref -> refs sharing at least one net (for net-guided translation)."""
    partners: Dict[str, List[str]] = {ref: [] for ref in sc.components}
    for net in sc.nets:
        refs = sorted({ref for ref, _pin in net.pins if ref in sc.components})
        for a in refs:
            for b in refs:
                if a != b and b not in partners[a]:
                    partners[a].append(b)
    return partners


def _clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else hi if v > hi else v


def _perturb(
    sc: Scenario,
    rng: random.Random,
    base: Placement,
    movable: List[str],
    moves: int,
) -> Placement:
    """Feasible large-step perturbation of ``base`` (no cost evaluations)."""
    pl = dict(base)
    for _ in range(moves):
        ref = rng.choice(movable)
        comp = sc.components[ref]
        x, y, rot = pl[ref]
        trial = dict(pl)
        if len(movable) >= 2 and rng.random() < 0.35:
            other = rng.choice([r for r in movable if r != ref])
            trial[ref], trial[other] = trial[other], trial[ref]
        else:
            x = rng.uniform(0.0, sc.board_w)
            y = rng.uniform(0.0, sc.board_h)
            if len(comp.rotations) > 1 and rng.random() < 0.5:
                rot = rng.choice(comp.rotations)
            trial[ref] = (x, y, rot)
        if feasible_partial(sc, trial):
            pl = trial
    return pl


class _RestartSearch:
    """One restart of the portfolio: tabu + adaptive-step SA over placements."""

    def __init__(
        self,
        sc: Scenario,
        cost: ObjectiveFn,
        rng: random.Random,
        start: Placement,
        start_cost: float,
        movable: List[str],
        partners: Dict[str, List[str]],
    ) -> None:
        self.sc = sc
        self.cost = cost
        self.rng = rng
        self.cur = dict(start)
        self.cur_cost = start_cost
        self.movable = movable
        self.partners = partners
        self.best = dict(start)
        self.best_cost = start_cost
        self.step_mm = _STEP0
        self.tabu: Dict[str, int] = {}
        self.tenure = max(2, len(movable) // _TABU_TENURE_DIV)
        # Number of cost() calls made inside this restart (start not counted).
        self.cost_evals = 0

    # -- proposals ---------------------------------------------------------
    def _guided_target(self, ref: str) -> Tuple[float, float]:
        """Mean centre of components sharing a net with ``ref``."""
        pl = self.cur
        pts = [pl[p] for p in self.partners.get(ref, ()) if p in pl]
        if not pts:
            return pl[ref][0], pl[ref][1]
        return sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)

    def _propose(self, it: int) -> Tuple[Placement, Tuple[str, ...]]:
        rng = self.rng
        sc = self.sc
        movable = self.movable
        trial = dict(self.cur)
        # --- choose a non-tabu ref -------------------------------------
        allowed = [r for r in movable if self.tabu.get(r, -1) < it]
        ref = rng.choice(allowed) if allowed else rng.choice(movable)
        comp = sc.components[ref]
        x, y, rot = trial[ref]
        moved: List[str] = [ref]
        u = rng.random()
        if u < _P_SWAP and len(movable) >= 2:
            others = [r for r in allowed if r != ref] or [r for r in movable if r != ref]
            other = rng.choice(others)
            trial[ref], trial[other] = trial[other], trial[ref]
            moved = [ref, other]
            return trial, tuple(moved)
        # --- translation (plain or net-guided) -------------------------
        if rng.random() < _P_GUIDED:
            tx, ty = self._guided_target(ref)
            alpha = rng.uniform(0.25, 0.85)
            x = x + alpha * (tx - x) + rng.gauss(0.0, 0.15 * self.step_mm)
            y = y + alpha * (ty - y) + rng.gauss(0.0, 0.15 * self.step_mm)
        else:
            sigma = self.step_mm * (0.35 + 0.65 * rng.random())
            x += rng.gauss(0.0, sigma)
            y += rng.gauss(0.0, sigma)
        x = _clamp(x, 0.0, sc.board_w)
        y = _clamp(y, 0.0, sc.board_h)
        if len(comp.rotations) > 1 and rng.random() < _P_ROTATE:
            rot = rng.choice(comp.rotations)
        trial[ref] = (x, y, rot)
        return trial, tuple(moved)

    # -- one restart -------------------------------------------------------
    def run(self, budget: int) -> Tuple[Placement, float, Dict[str, float], int]:
        """Run ``budget`` move proposals; return (best, best_cost, counters, improved_at)."""
        accepted = 0
        rejected = 0
        improved_at = 0
        best = self.best
        best_cost = self.best_cost
        for i in range(budget):
            frac = i / max(1, budget - 1)
            temp = _T0 * ((_T1 / _T0) ** frac)
            trial, moved = self._propose(i)
            if not feasible_partial(self.sc, trial):
                rejected += 1
                self.step_mm = max(_STEP_MIN, self.step_mm * _STEP_DOWN)
                continue
            t_cost = self.cost(trial)
            self.cost_evals += 1
            delta = t_cost - self.cur_cost
            if delta <= 0.0 or self.rng.random() < math.exp(-delta / max(temp, 1e-12)):
                accepted += 1
                self.cur, self.cur_cost = trial, t_cost
                for r in moved:
                    self.tabu[r] = i + self.tenure
                self.step_mm = min(_STEP_MAX, self.step_mm * _STEP_UP)
                if t_cost < best_cost:
                    best, best_cost = dict(trial), t_cost
                    improved_at = i + 1
            else:
                rejected += 1
                self.step_mm = max(_STEP_MIN, self.step_mm * _STEP_DOWN)
        self.best, self.best_cost = best, best_cost
        return best, best_cost, {"accepted": accepted, "rejected": rejected}, improved_at


def solve(
    scenario: Scenario,
    cost: ObjectiveFn,
    seed: int = 0,
    steps: int = 2000,
    restarts: int = 3,
) -> tuple[Placement, float, Dict[str, object]]:
    """Portfolio placement search; returns ``(placement, cost, stats)``.

    ``steps`` is the total number of move proposals across all restarts, so the
    budget matches ``Annealer(..., steps=steps)``.  Hard constraints are never
    violated: starts come from ``random_feasible_placement`` and every proposal
    is accepted only after ``feasible_partial`` passes.

    Deterministic for a fixed ``(scenario, cost, seed, steps, restarts)`` except
    for ``stats["runtime_s"]``.
    """
    t_start = time.perf_counter()
    sc = scenario
    total_steps = max(0, int(steps))
    budgets = _split_budget(total_steps, restarts)
    n_restarts = len(budgets)
    movable = [ref for ref, comp in sc.components.items() if not comp.fixed]
    partners = _partner_map(sc) if movable else {ref: [] for ref in sc.components}

    global_best_cost = float("inf")
    global_best: Placement = {}
    first_cost = float("nan")
    restart_best_costs: List[float] = []
    start_modes: List[str] = []
    attempts = 0
    accepted = 0
    rejected = 0
    cost_evals = 0
    best_iter = 0
    improvements = 0

    if not movable:
        # Degenerate scenario: fixed placement is the only feasible solution.
        pl = random_feasible_placement(sc, _restart_rng(seed, 0))
        c = cost(pl)
        stats: Dict[str, object] = {
            "solver": "portfolio-v2",
            "seed": int(seed),
            "steps": total_steps,
            "restarts": 1,
            "attempts": 0,
            "accepted": 0,
            "rejected": 0,
            "best_iter": 0,
            "cost_evals": 1,
            "initial_cost": c,
            "best_cost": c,
            "restart_best_costs": [c],
            "start_modes": ["feasible"],
            "improvements": 0,
            "runtime_s": time.perf_counter() - t_start,
        }
        return pl, c, stats

    for idx, budget in enumerate(budgets):
        rng = _restart_rng(seed, idx)
        use_best_start = (
            _LAST_RESTART_FROM_BEST
            and idx == n_restarts - 1
            and idx > 0
            and bool(global_best)
        )
        if use_best_start:
            start = _perturb(sc, rng, global_best, movable, _PERTURB_MOVES)
            start_modes.append("perturbed_best")
        else:
            start = random_feasible_placement(sc, rng)
            start_modes.append("random_feasible")
        start_cost = cost(start)
        cost_evals += 1
        if math.isnan(first_cost):
            first_cost = start_cost
        search = _RestartSearch(sc, cost, rng, start, start_cost, movable, partners)
        r_best, r_best_cost, counters, improved_at = search.run(budget)
        accepted += counters["accepted"]
        rejected += counters["rejected"]
        attempts += budget
        cost_evals += search.cost_evals
        restart_best_costs.append(r_best_cost)
        if r_best_cost < global_best_cost:
            global_best = dict(r_best)
            global_best_cost = r_best_cost
            best_iter = attempts - budget + improved_at
            improvements += 1

    if not global_best:  # pragma: no cover - defensive
        global_best = random_feasible_placement(sc, _restart_rng(seed, 0))
        global_best_cost = cost(global_best)
        cost_evals += 1

    stats = {
        "solver": "portfolio-v2",
        "seed": int(seed),
        "steps": total_steps,
        "restarts": n_restarts,
        "attempts": attempts,
        "accepted": accepted,
        "rejected": rejected,
        "best_iter": best_iter,
        "cost_evals": cost_evals,
        "initial_cost": first_cost,
        "best_cost": global_best_cost,
        "restart_best_costs": restart_best_costs,
        "start_modes": start_modes,
        "improvements": improvements,
        "runtime_s": time.perf_counter() - t_start,
    }
    return global_best, global_best_cost, stats
