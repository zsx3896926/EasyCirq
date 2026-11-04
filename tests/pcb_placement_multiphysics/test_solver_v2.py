"""Tests for the P2 portfolio solver ``mp_place.solver_v2`` (stdlib unittest).

Run with::

    python -m unittest tests.test_solver_v2 -v

The full Annealer-vs-solve benchmark table (5 scenarios x ProxyObjective,
steps=1200, seeds=0/1/2) is recorded in the module docstring of
:mod:`mp_place.solver_v2`; the comparison test at the bottom re-runs one of its
scenarios (rs485, the largest recorded margin) as a regression guard.
"""

import math
import unittest

from mp_place.model import hard_violations
from mp_place.objective import ProxyObjective
from mp_place.scenarios import build_scenarios
from mp_place.solver import Annealer
from mp_place.solver_v2 import solve


def _stats_without_runtime(stats):
    return {key: value for key, value in stats.items() if key != "runtime_s"}


class FeasibilityTests(unittest.TestCase):
    """The solver must only ever return hard-feasible placements."""

    def test_all_scenarios_return_hard_feasible(self):
        scenarios = build_scenarios(seed=0)
        self.assertEqual(len(scenarios), 5)
        for sc in scenarios:
            obj = ProxyObjective(sc)
            for seed in (0, 1):
                pl, cost, stats = solve(sc, obj.cost, seed=seed, steps=120, restarts=3)
                self.assertEqual(hard_violations(sc, pl), [], sc.name)
                self.assertTrue(math.isfinite(cost), sc.name)
                self.assertAlmostEqual(obj.cost(pl), cost, places=9, msg=sc.name)
                self.assertAlmostEqual(stats["best_cost"], cost, places=9, msg=sc.name)

    def test_only_feasible_placements_are_scored(self):
        """Wrap cost() and assert that every scored placement is feasible."""
        for sc in build_scenarios(seed=0):
            obj = ProxyObjective(sc)

            def checked_cost(pl, _sc=sc, _obj=obj):
                self.assertEqual(hard_violations(_sc, pl), [], _sc.name)
                return _obj.cost(pl)

            pl, cost, _stats = solve(sc, checked_cost, seed=2, steps=80, restarts=2)
            self.assertEqual(hard_violations(sc, pl), [], sc.name)

    def test_fixed_components_never_move(self):
        for sc in build_scenarios(seed=0):
            obj = ProxyObjective(sc)
            pl, _cost, _stats = solve(sc, obj.cost, seed=5, steps=100, restarts=2)
            for ref, comp in sc.components.items():
                if comp.fixed:
                    self.assertEqual(pl[ref], sc.base_placement[ref], f"{sc.name}:{ref}")

    def test_zero_steps_still_returns_feasible_start(self):
        sc = build_scenarios(seed=0)[0]
        obj = ProxyObjective(sc)
        pl, cost, stats = solve(sc, obj.cost, seed=0, steps=0, restarts=3)
        self.assertEqual(hard_violations(sc, pl), [])
        self.assertAlmostEqual(obj.cost(pl), cost, places=9)
        self.assertEqual(stats["attempts"], 0)
        self.assertEqual(stats["accepted"] + stats["rejected"], 0)
        self.assertGreaterEqual(stats["restarts"], 1)

    def test_stats_schema(self):
        sc = build_scenarios(seed=0)[1]
        obj = ProxyObjective(sc)
        _pl, _cost, stats = solve(sc, obj.cost, seed=1, steps=100, restarts=3)
        for key in ("accepted", "rejected", "best_iter", "restarts", "runtime_s"):
            self.assertIn(key, stats)
        self.assertGreaterEqual(stats["runtime_s"], 0.0)
        self.assertEqual(stats["accepted"] + stats["rejected"], stats["attempts"])
        self.assertGreaterEqual(stats["best_iter"], 0)
        self.assertLessEqual(stats["best_iter"], stats["attempts"])
        self.assertLessEqual(stats["restarts"], 3)
        self.assertEqual(len(stats["restart_best_costs"]), stats["restarts"])


class DeterminismTests(unittest.TestCase):
    """Same seed -> same placement/cost/stats (runtime allowed to vary)."""

    def test_same_seed_same_result(self):
        sc = build_scenarios(seed=0)[3]  # motor
        obj = ProxyObjective(sc)
        pl_a, cost_a, stats_a = solve(sc, obj.cost, seed=7, steps=300, restarts=3)
        pl_b, cost_b, stats_b = solve(sc, obj.cost, seed=7, steps=300, restarts=3)
        self.assertEqual(pl_a, pl_b)
        self.assertEqual(cost_a, cost_b)
        self.assertEqual(_stats_without_runtime(stats_a), _stats_without_runtime(stats_b))

    def test_determinism_with_multiple_restarts_and_seeds(self):
        sc = build_scenarios(seed=0)[2]  # rs485
        obj = ProxyObjective(sc)
        for seed in (0, 1, 2):
            first = solve(sc, obj.cost, seed=seed, steps=240, restarts=3)
            second = solve(sc, obj.cost, seed=seed, steps=240, restarts=3)
            self.assertEqual(first[0], second[0])
            self.assertEqual(_stats_without_runtime(first[2]), _stats_without_runtime(second[2]))


class BudgetTests(unittest.TestCase):
    """``steps`` is a total budget, not a per-restart budget."""

    def test_total_budget_is_not_multiplied_by_restarts(self):
        sc = build_scenarios(seed=0)[0]
        obj = ProxyObjective(sc)
        calls = {"n": 0}

        def counted(pl):
            calls["n"] += 1
            return obj.cost(pl)

        for steps in (0, 1, 20, 200, 1200):
            for restarts in (1, 2, 3, 5):
                calls["n"] = 0
                _pl, _cost, stats = solve(sc, counted, seed=3, steps=steps, restarts=restarts)
                self.assertEqual(stats["attempts"], steps)
                self.assertEqual(stats["accepted"] + stats["rejected"], steps)
                self.assertEqual(stats["steps"], steps)
                # Actual restart count may shrink when steps < restarts.
                self.assertGreaterEqual(stats["restarts"], 1)
                self.assertLessEqual(stats["restarts"], restarts)
                # One cost() per start + at most one per (feasible) move.
                self.assertLessEqual(calls["n"], steps + stats["restarts"])
                self.assertEqual(stats["cost_evals"], calls["n"])

    def test_budget_overhead_vs_annealer_is_only_restart_starts(self):
        sc = build_scenarios(seed=0)[1]  # buck
        obj = ProxyObjective(sc)
        steps = 300
        solve_calls = {"n": 0}
        anneal_calls = {"n": 0}

        def counted_solve(pl):
            solve_calls["n"] += 1
            return obj.cost(pl)

        def counted_anneal(pl):
            anneal_calls["n"] += 1
            return obj.cost(pl)

        _pl, _cost, stats = solve(sc, counted_solve, seed=0, steps=steps, restarts=3)
        Annealer(sc, counted_anneal, seed=0, steps=steps).run()
        # Same move budget; solve only pays one extra initial score per restart.
        self.assertEqual(stats["attempts"], steps)
        self.assertEqual(solve_calls["n"], stats["cost_evals"])
        self.assertLessEqual(solve_calls["n"] - steps, stats["restarts"])
        self.assertLessEqual(anneal_calls["n"] - steps, 1)


class PortfolioVsAnnealerTests(unittest.TestCase):
    """Regression guard for the recorded benchmark (module docstring)."""

    def test_not_worse_than_annealer_mean_on_at_least_one_scenario(self):
        sc = build_scenarios(seed=0)[2]  # rs485
        obj = ProxyObjective(sc)
        seeds = (0, 1, 2)
        steps = 1200
        annealer_costs = [
            Annealer(sc, obj.cost, seed=seed, steps=steps).run()[1] for seed in seeds
        ]
        solve_costs = [
            solve(sc, obj.cost, seed=seed, steps=steps, restarts=3)[1] for seed in seeds
        ]
        annealer_mean = sum(annealer_costs) / len(annealer_costs)
        solve_mean = sum(solve_costs) / len(solve_costs)
        self.assertLessEqual(
            solve_mean,
            annealer_mean,
            f"rs485: solve mean {solve_mean:.4f} > Annealer mean {annealer_mean:.4f}",
        )


if __name__ == "__main__":
    unittest.main()
