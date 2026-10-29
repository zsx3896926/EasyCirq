"""Tests for the P2.8 route-aware objective ``mp_place.route_cost``.

Run with::

    python -m unittest tests.test_route_cost -v

The three-group benchmark (proxy / RouteAware / proxy+post-hoc repair, 8
templates x seeds 0/1) is recorded in ``report_route_cost.{md,json}`` at the
project root (see ``python -m mp_place.route_cost``); these tests are the fast
behavioural guards: cost decomposition, determinism, crowding monotonicity,
feasibility and a smoke run on every registered template.
"""

import math
import random
import unittest
from unittest import mock

from mp_place.model import Component, Net, Scenario, hard_violations
from mp_place.objective import ProxyObjective
from mp_place.route_cost import RouteAwareObjective
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
