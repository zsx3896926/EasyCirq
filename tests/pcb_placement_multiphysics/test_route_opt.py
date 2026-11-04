"""Tests for the P2.5 route-aware repair ``mp_place.route_opt`` (stdlib unittest).

Run with::

    python -m unittest tests.test_route_opt -v

The Annealer/pipeline benchmark table (8 templates x seeds 0/1/2) is recorded in
the module docstring of :mod:`mp_place.route_opt`; these tests are the fast
behavioural guards: feasibility, determinism, the ``max_routes`` hard cap, and
``buck`` completion never dropping.
"""

import math
import unittest
from unittest import mock

import mp_place.route_opt as route_opt
from mp_place.model import hard_violations
from mp_place.objective import ProxyObjective
from mp_place.physics_v2 import PhysicsSimulatorV2
from mp_place.router import GridRouter
from mp_place.templates import instantiate

repair_routes = route_opt.repair_routes


def _stats_without_runtime(stats):
    return {key: value for key, value in stats.items() if key != "runtime_s"}


class FeasibilityTests(unittest.TestCase):
    """repair_routes must only return hard-feasible placements."""

    def test_repaired_placements_are_hard_feasible(self):
        for name in ("buck", "mcu-min", "wireless"):
            for seed in (0, 1):
                sc = instantiate(name, seed=seed)
                obj = ProxyObjective(sc)
                placement, truth, result, stats = repair_routes(
                    sc, obj.cost, seed=seed, steps=120, max_routes=8
                )
                self.assertEqual(hard_violations(sc, placement), [], f"{name}:{seed}")
                self.assertTrue(math.isfinite(truth), f"{name}:{seed}")
                self.assertAlmostEqual(
                    truth,
                    PhysicsSimulatorV2(sc, seed=seed).score(placement),
                    places=9,
                    msg=f"{name}:{seed}",
                )
                self.assertAlmostEqual(
                    result.completion, stats["final_completion"], places=12, msg=f"{name}:{seed}"
                )
                # Completion is monotone: only improving moves are accepted.
                self.assertGreaterEqual(
                    stats["final_completion"], stats["initial_completion"], f"{name}:{seed}"
                )

    def test_stats_contract(self):
        sc = instantiate("buck", seed=1)
        obj = ProxyObjective(sc)
        _pl, _truth, _result, stats = repair_routes(
            sc, obj.cost, seed=0, steps=100, max_routes=6
        )
        for key in ("routes_calls", "initial_completion", "final_completion", "moves_accepted"):
            self.assertIn(key, stats)
        self.assertGreaterEqual(stats["routes_calls"], 1)
        self.assertGreaterEqual(stats["moves_accepted"], 0)
        self.assertEqual(stats["routes_calls"], stats["moves_tried"] + 1)
        self.assertIsInstance(stats["initial_failed_nets"], list)
        self.assertIsInstance(stats["final_failed_nets"], list)
        self.assertTrue(
            all(isinstance(name, str) for name in stats["final_failed_nets"])
        )


class BuckCompletionTests(unittest.TestCase):
    """buck completion must improve or stay the same (never regress)."""

    def test_buck_completion_not_worse(self):
        for seed in (0, 1, 2):
            sc = instantiate("buck", seed=seed)
            obj = ProxyObjective(sc)
            _pl, _truth, result, stats = repair_routes(sc, obj.cost, seed=seed)
            self.assertGreaterEqual(
                stats["final_completion"],
                stats["initial_completion"],
                f"buck seed {seed}: {stats['initial_completion']} -> "
                f"{stats['final_completion']}",
            )
            self.assertGreaterEqual(stats["final_completion"], 0.999, f"buck seed {seed}")
            self.assertGreaterEqual(result.completion, 0.999, f"buck seed {seed}")


class DeterminismTests(unittest.TestCase):
    """Same seed -> identical placement / truth / stats (runtime excluded)."""

    def test_same_seed_same_repair(self):
        sc = instantiate("mcu-min", seed=1)
        obj = ProxyObjective(sc)
        first = repair_routes(sc, obj.cost, seed=3, steps=200, max_routes=12)
        second = repair_routes(sc, obj.cost, seed=3, steps=200, max_routes=12)
        self.assertEqual(first[0], second[0])
        self.assertEqual(first[1], second[1])
        self.assertEqual(_stats_without_runtime(first[3]), _stats_without_runtime(second[3]))
        self.assertEqual(first[2].completion, second[2].completion)
        self.assertEqual(first[2].failed_nets, second[2].failed_nets)
        self.assertEqual(first[2].wirelength_mm, second[2].wirelength_mm)
        self.assertEqual(first[2].vias, second[2].vias)
        self.assertEqual(first[2].overflow, second[2].overflow)


class RouteBudgetTests(unittest.TestCase):
    """max_routes is a hard cap on the number of router calls."""

    def test_max_routes_hard_cap(self):
        base_router = GridRouter

        class CountingRouter(base_router):  # type: ignore[misc, valid-type]
            calls = 0

            def route(self, placement, critical_nets=None):
                CountingRouter.calls += 1
                return super().route(placement, critical_nets)

        sc = instantiate("buck", seed=1)
        obj = ProxyObjective(sc)
        for max_routes in (0, 1, 2, 5, 12):
            CountingRouter.calls = 0
            with mock.patch.object(route_opt, "GridRouter", CountingRouter):
                _pl, _truth, _result, stats = repair_routes(
                    sc, obj.cost, seed=0, steps=80, max_routes=max_routes
                )
            cap = max(1, max_routes)
            self.assertLessEqual(CountingRouter.calls, cap, f"max_routes={max_routes}")
            self.assertEqual(stats["routes_calls"], CountingRouter.calls)
            self.assertEqual(stats["max_routes"], cap)


if __name__ == "__main__":
    unittest.main()
