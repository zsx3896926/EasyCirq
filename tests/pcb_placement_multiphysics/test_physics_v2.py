"""Unit tests for the P2 realistic offline simulator (``mp_place.physics_v2``).

Run from the project root::

    python -m unittest tests.test_physics_v2 -v
"""

from __future__ import annotations

import math
import os
import pathlib
import random
import subprocess
import sys
import unittest

from mp_place.features import FEATURE_NAMES, extract_features
from mp_place.model import hard_violations
from mp_place.physics_v2 import PhysicsSimulatorV2
from mp_place.scenarios import build_scenarios
from mp_place.solver import random_feasible_placement

_PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2] / "benchmarks" / "pcb-placement-multiphysics"

# The nine physics contributions returned by ``breakdown`` plus the total.
_BREAKDOWN_KEYS = (
    "wirelength",
    "loop_inductance",
    "pdn_impedance",
    "thermal",
    "field_coupling",
    "escape",
    "congestion",
    "keepout",
    "nonlinear",
)


def _scenario(name: str):
    return next(sc for sc in build_scenarios(seed=0) if sc.name == name)


def _buck_scenario():
    return _scenario("buck")


def _buck_reference_layout() -> dict:
    """Hand-built feasible buck layout.

    Decoupling caps sit next to the nets they serve, the analog divider is far
    from the power stage.  Used as the "good" layout and as the numeric example.
    """
    return {
        "J1": (5.0, 27.5, 0),
        "U1": (20.0, 40.0, 0),
        "L1": (35.0, 40.0, 0),
        "U2": (55.0, 40.0, 0),
        "C1": (20.0, 30.0, 0),
        "C2": (28.0, 30.0, 0),
        "C3": (45.0, 30.0, 0),
        "C4": (53.0, 30.0, 0),
        "C5": (60.5, 41.0, 0),
        "C6": (60.5, 39.0, 0),
        "R1": (70.0, 12.0, 0),
        "R2": (75.0, 12.0, 0),
    }


def _buck_bad_decoupling_layout() -> dict:
    """Bad layout #1: identical to the reference except the six caps are spread
    into the far corners, stretching every PDN current loop and decoupling path.
    """
    pl = _buck_reference_layout()
    pl.update(
        {
            "C1": (12.0, 8.0, 0),
            "C2": (30.0, 8.0, 0),
            "C3": (80.0, 8.0, 0),
            "C4": (80.0, 45.0, 0),
            "C5": (60.0, 8.0, 0),
            "C6": (80.0, 30.0, 0),
        }
    )
    return pl


def _buck_bad_coupling_layout() -> dict:
    """Bad layout #2: same as the reference but the analog divider is moved right
    next to the switching power stage (strong field coupling / crosstalk).
    """
    pl = _buck_reference_layout()
    pl.update({"R1": (23.5, 40.0, 0), "R2": (23.5, 37.0, 0)})
    return pl


class DeterminismTests(unittest.TestCase):
    """Hidden coefficients and scores must be reproducible, never hash-based."""

    def test_same_scenario_and_seed_reproducible(self):
        sc = _buck_scenario()
        sim_a = PhysicsSimulatorV2(sc, seed=0)
        sim_b = PhysicsSimulatorV2(sc, seed=0)
        self.assertEqual(sim_a.coefficients(), sim_b.coefficients())
        self.assertEqual(
            tuple(sim_a.coefficients().keys()), tuple(sim_b.coefficients().keys())
        )
        pl = _buck_reference_layout()
        self.assertEqual(sim_a.score(pl), sim_b.score(pl))
        f = extract_features(sc, pl)
        self.assertEqual(sim_a.score_features(f), sim_b.score_features(f))
        # repeated calls on one instance agree too
        self.assertEqual(sim_a.score_features(f), sim_a.score_features(f))

    def test_score_features_is_pure(self):
        sc = _buck_scenario()
        sim = PhysicsSimulatorV2(sc, seed=0)
        f = extract_features(sc, _buck_reference_layout())
        before = dict(f)
        first = sim.score_features(f)
        second = sim.score_features(f)
        self.assertEqual(f, before)  # input dict untouched
        self.assertEqual(first, second)
        self.assertIsInstance(first, float)

    def test_hidden_coefficients_follow_name_and_seed(self):
        buck_seed0 = PhysicsSimulatorV2(_buck_scenario(), seed=0)
        buck_seed1 = PhysicsSimulatorV2(_buck_scenario(), seed=1)
        rs485_seed0 = PhysicsSimulatorV2(_scenario("rs485"), seed=0)
        self.assertNotEqual(buck_seed0.coefficients(), buck_seed1.coefficients())
        self.assertNotEqual(buck_seed0.coefficients(), rs485_seed0.coefficients())
        # the hidden coefficients actually change the truth score
        pl = _buck_reference_layout()
        self.assertNotEqual(buck_seed0.score(pl), buck_seed1.score(pl))
        # all coefficients are finite floats
        for name, value in buck_seed0.coefficients().items():
            self.assertIsInstance(name, str)
            self.assertTrue(math.isfinite(value), name)

    def test_coefficients_reproducible_across_processes(self):
        """Scores must not depend on PYTHONHASHSEED (i.e. no Python hash())."""
        snippet = (
            "import random\n"
            "from mp_place.scenarios import build_scenarios\n"
            "from mp_place.solver import random_feasible_placement\n"
            "from mp_place.physics_v2 import PhysicsSimulatorV2\n"
            "sc = build_scenarios(seed=0)[1]\n"
            "pl = random_feasible_placement(sc, random.Random(42))\n"
            "sim = PhysicsSimulatorV2(sc, seed=0)\n"
            "print(repr(sim.score(pl)))\n"
            "print(repr(sorted(sim.coefficients().items())))\n"
        )

        def run(hash_seed: str) -> str:
            env = dict(os.environ)
            env["PYTHONHASHSEED"] = hash_seed
            return subprocess.check_output(
                [sys.executable, "-c", snippet],
                cwd=str(_PROJECT_ROOT),
                env=env,
                text=True,
                encoding="utf-8",
            ).strip()

        out_a = run("0")
        out_b = run("424242")
        self.assertEqual(out_a, out_b)
        # and the child process agrees with this process
        sc = _buck_scenario()
        sim = PhysicsSimulatorV2(sc, seed=0)
        pl = random_feasible_placement(sc, random.Random(42))
        expected = "\n".join(
            [repr(sim.score(pl)), repr(sorted(sim.coefficients().items()))]
        )
        self.assertEqual(out_a, expected)


class InvariantTests(unittest.TestCase):
    """Non-negativity, rank-1 consistency and the expected monotone shape."""

    def test_scores_finite_and_non_negative(self):
        rng = random.Random(17)
        for sc in build_scenarios(seed=0):
            for seed in (0, 1):
                sim = PhysicsSimulatorV2(sc, seed)
                for _ in range(3):
                    value = sim.score(random_feasible_placement(sc, rng))
                    self.assertTrue(math.isfinite(value), f"{sc.name}/{seed}")
                    self.assertGreaterEqual(value, 0.0, f"{sc.name}/{seed}")

    def test_score_matches_feature_scoring(self):
        sc = _buck_scenario()
        rng = random.Random(23)
        for seed in (0, 2):
            sim = PhysicsSimulatorV2(sc, seed)
            for _ in range(3):
                pl = random_feasible_placement(sc, rng)
                self.assertEqual(
                    sim.score(pl),
                    sim.score_features(extract_features(sc, pl)),
                )

    def test_breakdown_is_consistent_and_non_negative(self):
        sc = _buck_scenario()
        sim = PhysicsSimulatorV2(sc, seed=0)
        f = extract_features(sc, _buck_reference_layout())
        parts = sim.breakdown(f)
        self.assertEqual(set(parts), set(_BREAKDOWN_KEYS) | {"total"})
        for key, value in parts.items():
            self.assertTrue(math.isfinite(value), key)
            self.assertGreaterEqual(value, 0.0, key)
        summed = math.fsum(parts[key] for key in _BREAKDOWN_KEYS)
        self.assertAlmostEqual(summed, parts["total"], places=12)
        self.assertAlmostEqual(parts["total"], sim.score_features(f), places=12)

    def test_diagnostics_are_physical_and_non_negative(self):
        sc = _buck_scenario()
        sim = PhysicsSimulatorV2(sc, seed=0)
        diag = sim.diagnostics(extract_features(sc, _buck_reference_layout()))
        self.assertAlmostEqual(
            diag["board_diagonal_mm"], math.hypot(sc.board_w, sc.board_h), places=12
        )
        self.assertAlmostEqual(diag["parallel_decaps"], 6.0, places=12)
        self.assertGreater(diag["loop_inductance_nh"], 0.0)
        self.assertGreater(diag["coupling_gap_mm"], 0.0)
        for key, value in diag.items():
            self.assertTrue(math.isfinite(value), key)
            self.assertGreaterEqual(value, 0.0, key)

    def test_score_monotone_in_bad_direction(self):
        """Every modelled physics driver must increase the cost when it worsens."""
        sc = _buck_scenario()
        sim = PhysicsSimulatorV2(sc, seed=0)
        base = extract_features(sc, _buck_reference_layout())
        baseline = sim.score_features(base)
        increments = (
            ("hpwl", 0.05),  # longer routing
            ("decap", 0.02),  # caps further from their loads
            ("loop", 0.05),  # larger power loop
            ("thermal", 0.005),  # hotter switch
            ("density", 0.005),  # denser local copper
            ("congestion", 0.02),  # more crowded routing
            ("escape", 0.02),  # less free edge margin
            ("keepout", 0.002),  # intrusions into keepouts
            ("capcount", 0.02),  # fewer effective parallel decaps
        )
        for key, delta in increments:
            worse = dict(base)
            worse[key] += delta
            self.assertGreater(
                sim.score_features(worse), baseline, f"feature {key} should worsen"
            )
        # "analog" is a distance: smaller gap -> stronger field coupling.
        closer = dict(base)
        closer["analog"] = 0.01
        self.assertGreater(sim.score_features(closer), baseline)

    def test_extra_keys_ignored_missing_or_nan_rejected(self):
        sc = _buck_scenario()
        sim = PhysicsSimulatorV2(sc, seed=0)
        f = extract_features(sc, _buck_reference_layout())
        extra = dict(f)
        extra["not_a_feature"] = 123.0
        self.assertEqual(sim.score_features(f), sim.score_features(extra))
        missing = dict(f)
        missing.pop("loop")
        with self.assertRaises(KeyError):
            sim.score_features(missing)
        nan = dict(f)
        nan["hpwl"] = float("nan")
        with self.assertRaises(ValueError):
            sim.score_features(nan)

    def test_only_the_ten_feature_keys_are_needed(self):
        sc = _buck_scenario()
        sim = PhysicsSimulatorV2(sc, seed=0)
        f = extract_features(sc, _buck_reference_layout())
        self.assertEqual(set(f), set(FEATURE_NAMES))
        self.assertEqual(sim.score_features(f), sim.score_features(dict(f)))


class PlacementMonotonicityTests(unittest.TestCase):
    """Two constructed bad-vs-good layout comparisons (the required monotonicity)."""

    def test_bad_decoupling_and_loop_layout_scores_worse(self):
        sc = _buck_scenario()
        good = _buck_reference_layout()
        bad = _buck_bad_decoupling_layout()
        self.assertEqual(hard_violations(sc, good), [])
        self.assertEqual(hard_violations(sc, bad), [])
        f_good = extract_features(sc, good)
        f_bad = extract_features(sc, bad)
        self.assertGreater(f_bad["decap"], f_good["decap"])
        self.assertGreater(f_bad["loop"], f_good["loop"])
        for seed in (0, 1, 2):
            sim = PhysicsSimulatorV2(sc, seed)
            self.assertGreater(
                sim.score(bad),
                sim.score(good) + 0.5,
                msg=f"bad decoupling/loop layout should score worse (seed={seed})",
            )

    def test_bad_field_coupling_layout_scores_worse(self):
        sc = _buck_scenario()
        good = _buck_reference_layout()
        bad = _buck_bad_coupling_layout()
        self.assertEqual(hard_violations(sc, good), [])
        self.assertEqual(hard_violations(sc, bad), [])
        f_good = extract_features(sc, good)
        f_bad = extract_features(sc, bad)
        self.assertLess(f_bad["analog"], f_good["analog"])
        for seed in (0, 1, 2):
            sim = PhysicsSimulatorV2(sc, seed)
            self.assertGreater(
                sim.score(bad),
                sim.score(good) + 0.5,
                msg=f"analog-next-to-power layout should score worse (seed={seed})",
            )


class NumericExampleTests(unittest.TestCase):
    """Concrete numbers, useful as regression constants and for reports."""

    def test_buck_reference_layout_numeric_example(self):
        sc = _buck_scenario()
        sim = PhysicsSimulatorV2(sc, seed=0)
        pl = _buck_reference_layout()
        f = extract_features(sc, pl)
        # Regression constant: truth cost of the hand-built buck reference layout.
        self.assertAlmostEqual(sim.score(pl), 3.4119662348334634, places=9)
        bd = sim.breakdown(f)
        self.assertAlmostEqual(bd["thermal"], 1.7069250594012388, places=9)
        self.assertAlmostEqual(bd["loop_inductance"], 0.5235251721752655, places=9)
        self.assertAlmostEqual(bd["pdn_impedance"], 0.14035611431496928, places=9)
        self.assertAlmostEqual(bd["field_coupling"], 0.0032806631904856243, places=9)
        self.assertAlmostEqual(bd["escape"], 0.5519703547709026, places=9)
        diag = sim.diagnostics(f)
        self.assertAlmostEqual(diag["loop_inductance_nh"], 16.52942727463822, places=9)
        self.assertAlmostEqual(
            diag["pdn_impedance_au"], 0.12061541213335952, places=9
        )
        self.assertAlmostEqual(diag["coupling_gap_mm"], 23.17671245021606, places=9)

    def test_random_buck_layout_mean_truth(self):
        sc = _buck_scenario()
        sim = PhysicsSimulatorV2(sc, seed=0)
        rng = random.Random(7)
        scores = [sim.score(random_feasible_placement(sc, rng)) for _ in range(20)]
        mean = sum(scores) / len(scores)
        self.assertTrue(math.isfinite(mean))
        self.assertGreater(mean, 4.0)  # random layouts are clearly worse than 3.41
        self.assertLess(mean, 10.0)
        self.assertGreaterEqual(mean, min(scores))
        self.assertLessEqual(mean, max(scores))


if __name__ == "__main__":
    unittest.main()
