"""Tests for the P2.8/P2.9 route-aware objective ``mp_place.route_cost``.

Run with::

    python -m unittest tests.test_route_cost -v

The three-group benchmark (proxy / RouteAware / proxy+post-hoc repair) is
recorded in ``report_route_cost.{md,json}`` and the P2.9 adaptive-weight
four-group benchmark in ``report_route_cost_tuned.{md,json}`` at the project
root (see ``python -m mp_place.route_cost --tuned``).  These tests are the fast
behavioural guards: cost decomposition, determinism, crowding monotonicity,
router-free costs, deterministic tuning/selection, the embedded tuned table,
feasibility and a smoke run on every registered template.
"""

import json
import math
import random
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mp_place.model import Component, Net, Scenario, hard_violations
from mp_place.objective import ProxyObjective
from mp_place.route_cost import (
    PROFILE_TERM_WEIGHTS,
    TUNED_TABLE,
    RouteAwareObjective,
    run_tuned_benchmark,
    select_candidate,
    select_config,
    tune_template,
    tuned_objective,
    write_tuned_reports,
)
from mp_place.router import GridRouter
from mp_place.solver import random_feasible_placement
from mp_place.solver_v2 import solve
from mp_place.templates import instantiate, template_names


class CostDecompositionTests(unittest.TestCase):
    def test_cost_is_base_plus_weighted_penalty(self):
        sc = instantiate("buck", seed=0)
        base = ProxyObjective(sc)
        rng = random.Random(3)
        for w_route in (0.0, 1.0, 2.5):
            objective = RouteAwareObjective(sc, base=base, w_route=w_route)
            for _ in range(5):
                placement = random_feasible_placement(sc, rng)
                penalty = objective.route_penalty(placement)
                self.assertGreaterEqual(penalty, 0.0)
                self.assertLessEqual(penalty, 1.0)
                self.assertAlmostEqual(
                    objective.cost(placement),
                    base.cost(placement) + w_route * penalty,
                    places=12,
                )

    def test_w_route_zero_reproduces_base(self):
        sc = instantiate("motor", seed=1)
        base = ProxyObjective(sc)
        plain = RouteAwareObjective(sc, base=base, w_route=0.0)
        placement = random_feasible_placement(sc, random.Random(11))
        self.assertAlmostEqual(plain.cost(placement), base.cost(placement), places=12)

    def test_base_may_be_a_class_or_instance(self):
        sc = instantiate("rs485", seed=0)
        placement = random_feasible_placement(sc, random.Random(5))
        by_instance = RouteAwareObjective(sc, base=ProxyObjective(sc))
        by_class = RouteAwareObjective(sc, base=ProxyObjective)
        self.assertAlmostEqual(
            by_instance.cost(placement), by_class.cost(placement), places=12
        )


class PenaltyTests(unittest.TestCase):
    def test_penalty_finite_on_all_templates(self):
        rng = random.Random(7)
        for name in template_names():
            sc = instantiate(name, seed=0)
            objective = RouteAwareObjective(sc)
            placement = random_feasible_placement(sc, rng)
            penalty = objective.route_penalty(placement)
            self.assertTrue(math.isfinite(penalty), name)
            self.assertGreaterEqual(penalty, 0.0, name)
            self.assertLessEqual(penalty, 1.0, name)
            self.assertTrue(math.isfinite(objective.cost(placement)), name)

    def test_penalty_increases_with_crowding(self):
        scenario = _crowding_scenario()
        objective = RouteAwareObjective(scenario, w_route=1.0)
        spread = _placement(scenario, {
            "U1": (6.0, 6.0), "U2": (14.0, 6.0), "U3": (22.0, 6.0),
            "U4": (30.0, 6.0), "U5": (10.0, 24.0), "U6": (26.0, 24.0),
        })
        medium = _placement(scenario, {
            "U1": (16.0, 13.0), "U2": (19.5, 13.0), "U3": (23.0, 13.0),
            "U4": (16.0, 16.5), "U5": (19.5, 16.5), "U6": (23.0, 16.5),
        })
        tight = _placement(scenario, {
            "U1": (3.0, 3.0), "U2": (5.2, 3.0), "U3": (7.4, 3.0),
            "U4": (3.0, 5.2), "U5": (5.2, 5.2), "U6": (7.4, 5.2),
        })
        # All three layouts are hard-feasible (2 mm bodies, no overlaps).
        for placement in (spread, medium, tight):
            self.assertEqual(hard_violations(scenario, placement), [])
        p_spread = objective.route_penalty(spread)
        p_medium = objective.route_penalty(medium)
        p_tight = objective.route_penalty(tight)
        self.assertLess(p_spread, p_medium)
        self.assertLess(p_medium, p_tight)
        # The full cost follows the penalty when the base cost is constant-ish.
        self.assertLess(objective.cost(spread), objective.cost(tight))

    def test_penalty_never_calls_the_router(self):
        def _forbidden(*_args, **_kwargs):
            raise AssertionError("RouteAwareObjective must not call the grid router")

        sc = instantiate("wireless", seed=0)
        objective = RouteAwareObjective(sc)
        placement = random_feasible_placement(sc, random.Random(2))
        with mock.patch.object(GridRouter, "route", _forbidden):
            for _ in range(3):
                value = objective.cost(placement)
                self.assertTrue(math.isfinite(value))


class SolverIntegrationTests(unittest.TestCase):
    def test_smoke_solve_on_all_templates(self):
        for name in template_names():
            sc = instantiate(name, seed=1)
            objective = RouteAwareObjective(sc)
            placement, cost, _stats = solve(
                sc, objective.cost, seed=1, steps=100, restarts=2
            )
            self.assertEqual(hard_violations(sc, placement), [], name)
            self.assertTrue(math.isfinite(cost), name)
            self.assertAlmostEqual(objective.cost(placement), cost, places=9, msg=name)

    def test_same_seed_same_result(self):
        sc = instantiate("esp32-sensor", seed=0)
        objective = RouteAwareObjective(sc)
        first = solve(sc, objective.cost, seed=4, steps=120, restarts=2)
        second = solve(sc, objective.cost, seed=4, steps=120, restarts=2)
        self.assertEqual(first[0], second[0])
        self.assertEqual(first[1], second[1])


class AdaptiveWeightTests(unittest.TestCase):
    """P2.9: deterministic per-template tuning and router-free weight selection."""

    def test_select_candidate_rule_is_deterministic(self):
        proxy_truth = 10.0
        evaluations = [
            {"config": {"w_route": 0.0, "profile": "default"}, "completion_mean": 1.0, "truth_mean": 10.0},
            {"config": {"w_route": 2.0, "profile": "default"}, "completion_mean": 1.0, "truth_mean": 10.05},
            {"config": {"w_route": 1.0, "profile": "default"}, "completion_mean": 0.95, "truth_mean": 9.0},
            {"config": {"w_route": 3.0, "profile": "default"}, "completion_mean": 1.0, "truth_mean": 10.5},
        ]
        first = select_candidate(proxy_truth, evaluations)
        second = select_candidate(proxy_truth, evaluations)
        self.assertEqual(first, second)
        config, feasible, _best = first
        self.assertTrue(feasible)
        # w=0 keeps completion 1.0 with zero truth change -> minimal intervention.
        self.assertEqual(config, {"w_route": 0.0, "profile": "default"})
        # No feasible candidate -> deterministic fallback, never a crash.
        infeasible = [evaluations[2], evaluations[3]]
        fallback_a = select_candidate(proxy_truth, infeasible)
        fallback_b = select_candidate(proxy_truth, infeasible)
        self.assertEqual(fallback_a, fallback_b)
        self.assertFalse(fallback_a[1])

    def test_tune_template_deterministic_with_injected_evaluator(self):
        calls = []

        def evaluator(name, config, seeds, steps):
            calls.append(
                (str(name), float(config["w_route"]), str(config["profile"]))
            )
            w_route = float(config["w_route"])
            completion = min(1.0, 0.8 + 0.1 * w_route)
            truth = 100.0 + 0.5 * w_route
            return {
                "config": dict(config),
                "completion": [completion],
                "truth": [truth],
                "completion_mean": completion,
                "truth_mean": truth,
            }

        first = tune_template("fake-template", seeds=(0,), steps=1, evaluator=evaluator)
        first_calls = list(calls)
        calls.clear()
        second = tune_template("fake-template", seeds=(0,), steps=1, evaluator=evaluator)
        self.assertEqual(first_calls, calls)
        self.assertEqual(_evaluation_signature(first), _evaluation_signature(second))
        # completion target needs w>=2, truth budget allows exactly w=2.0.
        self.assertEqual(first["selected"], {"w_route": 2.0, "profile": "default"})
        self.assertTrue(first["feasible"])
        self.assertEqual(first["stage"], "weight_grid")

    def test_tuned_table_covers_all_templates(self):
        self.assertTrue(set(TUNED_TABLE) <= set(template_names()))
        for name, config in TUNED_TABLE.items():
            self.assertIn(config["profile"], PROFILE_TERM_WEIGHTS, name)
            self.assertGreaterEqual(float(config["w_route"]), 0.0, name)

    def test_select_config_table_and_tier_fallback_are_deterministic(self):
        for name in TUNED_TABLE:
            sc = instantiate(name, seed=0)
            config = select_config(sc)
            self.assertEqual(config["source"], "tuned_table", name)
            self.assertEqual(float(config["w_route"]), float(TUNED_TABLE[name]["w_route"]), name)
            self.assertEqual(str(config["profile"]), str(TUNED_TABLE[name]["profile"]), name)
            self.assertEqual(select_config(sc), config, name)
        unknown = _crowding_scenario()  # name "crowd-test" is not in the table
        fallback_a = select_config(unknown)
        fallback_b = select_config(unknown)
        self.assertEqual(fallback_a, fallback_b)
        self.assertEqual(fallback_a["source"], "tier_fallback")
        self.assertIn(fallback_a["profile"], PROFILE_TERM_WEIGHTS)

    def test_tuned_objective_matches_table_and_never_calls_router(self):
        def _forbidden(*_args, **_kwargs):
            raise AssertionError("tuned_objective must not call the grid router")

        rng = random.Random(9)
        for name in TUNED_TABLE:
            sc = instantiate(name, seed=0)
            objective = tuned_objective(sc)
            self.assertEqual(objective.w_route, float(TUNED_TABLE[name]["w_route"]), name)
            self.assertEqual(objective.profile, str(TUNED_TABLE[name]["profile"]), name)
            placement = random_feasible_placement(sc, rng)
            with mock.patch.object(GridRouter, "route", _forbidden):
                value = objective.cost(placement)
            self.assertTrue(math.isfinite(value), name)

    def test_tuned_smoke_solve_on_all_templates(self):
        for name in template_names():
            sc = instantiate(name, seed=1)
            objective = tuned_objective(sc)
            first = solve(sc, objective.cost, seed=2, steps=100, restarts=2)
            second = solve(sc, objective.cost, seed=2, steps=100, restarts=2)
            self.assertEqual(hard_violations(sc, first[0]), [], name)
            self.assertTrue(math.isfinite(first[1]), name)
            self.assertEqual(first[0], second[0], name)
            self.assertEqual(first[1], second[1], name)

    def test_run_tuned_benchmark_quick_retune_and_report(self):
        data = run_tuned_benchmark(seeds=(0,), steps=120, retune=True, names=("buck",))
        self.assertIsNotNone(data["tuning"])
        aggregate = data["aggregate"]
        for group in ("baseline", "route_aware", "fixed_weight", "tuned"):
            self.assertIn(group, aggregate)
            self.assertIn(group, aggregate["per_template"]["buck"])
        self.assertEqual(
            data["config"]["tuned_table"]["buck"],
            {
                "w_route": float(TUNED_TABLE["buck"]["w_route"]),
                "profile": str(TUNED_TABLE["buck"]["profile"]),
            },
        )
        self.assertIsNone(data["holdout"])
        with tempfile.TemporaryDirectory() as tmp:
            md_path, json_path = write_tuned_reports(data, Path(tmp))
            self.assertTrue(md_path.exists())
            self.assertTrue(json_path.exists())
            loaded = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(loaded["schema"], "mp_place.route_cost.tuned_report/v1")
            self.assertIn("tuned", loaded["aggregate"])
            text = md_path.read_text(encoding="utf-8")
            self.assertIn("baseline", text)
            self.assertIn("tuned", text)


def _evaluation_signature(result):
    """Hashable-ish digest of a tuning result for determinism assertions."""
    return {
        "selected": result["selected"],
        "feasible": result["feasible"],
        "stage": result["stage"],
        "evaluations": [
            (
                record["config"],
                round(float(record["completion_mean"]), 12),
                round(float(record["truth_mean"]), 12),
            )
            for record in result["evaluations"]
        ],
    }


def _crowding_scenario() -> Scenario:
    """Six 2x2 mm parts + three nets, for the crowding-monotonicity test."""
    components = {}
    for index in range(6):
        ref = f"U{index + 1}"
        components[ref] = Component(
            ref=ref,
            kind="generic",
            w=2.0,
            h=2.0,
            rotations=(0,),
            pins={"1": (-1.0, 0.0), "2": (1.0, 0.0)},
        )
    nets = [
        Net("N1", "digital", (("U1", "2"), ("U2", "1"))),
        Net("N2", "digital", (("U3", "2"), ("U4", "1"))),
        Net("N3", "analog", (("U5", "2"), ("U6", "1"))),
    ]
    return Scenario(
        name="crowd-test",
        board_w=40.0,
        board_h=30.0,
        components=components,
        nets=nets,
        keepouts=[],
        edge_tol=2.0,
        base_placement={},
    )


def _placement(scenario: Scenario, positions):
    return {ref: (x, y, 0) for ref, (x, y) in positions.items()}


if __name__ == "__main__":
    unittest.main()
