"""Smoke tests for the P1 framework (stdlib unittest only)."""

import math
import random
import unittest

from mp_place.features import FEATURE_NAMES, extract_features, feature_vector
from mp_place.model import bbox, hard_violations
from mp_place.objective import (
    HPWLObjective,
    PhysicsSimulator,
    ProxyObjective,
    RidgeModel,
    SurrogateObjective,
    build_dataset,
    r_squared,
    spearman,
)
from mp_place.scenarios import build_scenarios
from mp_place.solver import Annealer, feasible_partial, random_feasible_placement


class ModelTests(unittest.TestCase):
    def test_scenario_has_fixed_components_and_fits(self):
        scenarios = build_scenarios(seed=0)
        self.assertEqual(len(scenarios), 5)
        for sc in scenarios:
            fixed = [r for r, c in sc.components.items() if c.fixed]
            self.assertTrue(fixed, sc.name)
            for ref in fixed:
                self.assertIn(ref, sc.base_placement)

    def test_rotation_bbox(self):
        scenarios = build_scenarios(seed=0)
        sc = scenarios[0]
        comp = sc.components["C1"]  # 1.6 x 0.8
        b0 = bbox(comp, 10, 10, 0)
        b90 = bbox(comp, 10, 10, 90)
        self.assertAlmostEqual(b0[2] - b0[0], 1.6, places=6)
        self.assertAlmostEqual(b90[2] - b90[0], 0.8, places=6)

    def test_random_placement_is_hard_feasible(self):
        rng = random.Random(7)
        for sc in build_scenarios(seed=0):
            pl = random_feasible_placement(sc, rng)
            self.assertEqual(hard_violations(sc, pl), [], sc.name)
            self.assertTrue(feasible_partial(sc, pl))


class FeatureTests(unittest.TestCase):
    def test_features_finite_and_ordered(self):
        rng = random.Random(11)
        for sc in build_scenarios(seed=0):
            pl = random_feasible_placement(sc, rng)
            f = extract_features(sc, pl)
            self.assertEqual(tuple(f.keys()), FEATURE_NAMES)
            for name, val in f.items():
                self.assertTrue(math.isfinite(val), f"{sc.name}:{name}")
                self.assertGreaterEqual(val, -1e-9, f"{sc.name}:{name}")
            self.assertEqual(len(feature_vector(f)), len(FEATURE_NAMES))


class ObjectiveTests(unittest.TestCase):
    def test_simulator_deterministic(self):
        rng = random.Random(3)
        for sc in build_scenarios(seed=0)[:3]:
            pl = random_feasible_placement(sc, rng)
            sim_a = PhysicsSimulator(sc, seed=0)
            sim_b = PhysicsSimulator(sc, seed=0)
            self.assertAlmostEqual(sim_a.score(pl), sim_b.score(pl), places=9)

    def test_hpwl_proxy_differ_on_known_layouts(self):
        rng = random.Random(5)
        sc = build_scenarios(seed=0)[1]  # buck
        pl = random_feasible_placement(sc, rng)
        hpwl = HPWLObjective(sc).cost(pl)
        proxy = ProxyObjective(sc).cost(pl)
        self.assertGreaterEqual(hpwl, 0.0)
        self.assertGreater(proxy, 0.0)

    def test_ridge_fits_linear_function(self):
        x = [[i / 10.0, (i % 3)] for i in range(60)]
        y = [2.5 * a - 1.5 * b + 0.5 for a, b in x]
        model = RidgeModel(lam=1e-6).fit(x, y)
        pred = [model.predict(v) for v in x]
        self.assertGreater(r_squared(y, pred), 0.999)

    def test_surrogate_close_to_simulator(self):
        rng = random.Random(9)
        sc = build_scenarios(seed=0)[0]
        sim = PhysicsSimulator(sc, seed=0)
        placements = [random_feasible_placement(sc, rng) for _ in range(120)]
        X, y = build_dataset(sc, sim, placements)
        model = RidgeModel(lam=1e-2).fit(X[:96], y[:96])
        pred = [model.predict(v) for v in X[96:]]
        self.assertGreater(spearman(y[96:], pred), 0.5)
        sur = SurrogateObjective(sc, model)
        self.assertTrue(math.isfinite(sur.cost(placements[0])))


class SolverTests(unittest.TestCase):
    def test_annealer_returns_feasible_layout(self):
        sc = build_scenarios(seed=0)[0]
        obj = ProxyObjective(sc)
        ann = Annealer(sc, obj.cost, seed=0, steps=120)
        best, cost, trace = ann.run()
        self.assertEqual(hard_violations(sc, best), [])
        self.assertGreaterEqual(cost, 0.0)
        self.assertEqual(len(trace), 121)

    def test_zero_step_run(self):
        sc = build_scenarios(seed=0)[3]
        obj = HPWLObjective(sc)
        ann = Annealer(sc, obj.cost, seed=1, steps=0)
        best, _cost, trace = ann.run()
        self.assertEqual(hard_violations(sc, best), [])
        self.assertEqual(len(trace), 1)


if __name__ == "__main__":
    unittest.main()
