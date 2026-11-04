"""Unit tests for the P2.15 calibration interface (``mp_place.calibrate``).

Run from the project root::

    python -m unittest tests.test_calibrate -v

Coverage: no-measurement identity with ``PhysicsSimulatorV3``, per-term scales
taking effect, input validation, deterministic least-squares/NNLS fitting with
exact synthetic recovery, deterministic calibration across processes, a small
calibratability study (monotone improvement, data requirements, held-out gap)
and the report writer.
"""

from __future__ import annotations

import json
import math
import os
import pathlib
import random
import subprocess
import sys
import tempfile
import unittest

from mp_place.calibrate import (
    CAL_SIZES,
    MEASUREMENT_ALIASES,
    PERTURBATIONS,
    TERM_NAMES,
    CalibratedSimulator,
    calibrate,
    fit_scale_factors,
    model_measurements,
    normalize_scales,
    render_markdown,
    run_calibration_study,
    truth_scales_for,
    write_report,
)
from mp_place.physics_v3 import PhysicsSimulatorV3, extract_features_v3
from mp_place.solver import random_feasible_placement
from mp_place.templates import instantiate

_PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2] / "benchmarks" / "pcb-placement-multiphysics"


def _synthetic_model(n: int = 80, seed: int = 0):
    """Random well-conditioned model term matrix + known true scales."""
    rng = random.Random(seed)
    rows = [[rng.uniform(0.05, 2.0) for _ in TERM_NAMES] for _ in range(n)]
    model = {
        "terms": {
            term: [rows[i][j] for i in range(n)] for j, term in enumerate(TERM_NAMES)
        },
        "n": n,
    }
    true_scales = {term: 1.0 for term in TERM_NAMES}
    true_scales[TERM_NAMES[0]] = 1.9
    true_scales[TERM_NAMES[1]] = 1.3
    return model, rows, true_scales


class CalibrationInterfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scenario = instantiate("buck", 0)
        rng = random.Random(0)
        cls.placements = [random_feasible_placement(cls.scenario, rng) for _ in range(4)]
        cls.v3 = PhysicsSimulatorV3(cls.scenario, seed=0)

    def test_no_measurement_does_not_change_behaviour(self):
        calibrated = CalibratedSimulator(self.scenario, seed=0)
        self.assertTrue(all(value == 1.0 for value in calibrated.scales.values()))
        for placement in self.placements:
            self.assertEqual(calibrated.score(placement), self.v3.score(placement))
            features = extract_features_v3(self.scenario, placement)
            self.assertEqual(
                calibrated.score_features(features), self.v3.score_features(features)
            )
        # multi-layer v3 too
        calibrated4 = CalibratedSimulator(self.scenario, seed=0, layers=4)
        v3_4 = PhysicsSimulatorV3(self.scenario, seed=0, layers=4)
        placement = self.placements[0]
        self.assertEqual(calibrated4.score(placement), v3_4.score(placement))

    def test_scale_takes_effect_exactly(self):
        base_features = extract_features_v3(self.scenario, self.placements[0])
        base_terms = self.v3.breakdown(base_features)
        for term, factor in (("loop_inductance", 2.5), ("thermal", 0.4), ("pdn_impedance", 3.0)):
            calibrated = CalibratedSimulator(
                self.scenario, seed=0, scales={term: factor}
            )
            terms = calibrated.breakdown(base_features)
            self.assertAlmostEqual(terms[term], factor * base_terms[term], places=12)
            self.assertAlmostEqual(
                terms["total"],
                base_terms["total"] + (factor - 1.0) * base_terms[term],
                places=9,
            )
            self.assertAlmostEqual(
                calibrated.score(self.placements[0]), terms["total"], places=9
            )

    def test_invalid_scales_rejected(self):
        for bad in (
            {"not_a_term": 1.0},
            {"loop_inductance": -1.0},
            {"loop_inductance": float("nan")},
            {"loop_inductance": float("inf")},
            "not-a-dict",
        ):
            with self.assertRaises((ValueError, TypeError, KeyError)):
                CalibratedSimulator(self.scenario, scales=bad)

    def test_aliases_and_normalization(self):
        scales = normalize_scales({"loop_nh": 2.0, "thermal_c": 1.5})
        self.assertEqual(scales["loop_inductance"], 2.0)
        self.assertEqual(scales["thermal"], 1.5)
        self.assertEqual(scales["wirelength"], 1.0)
        self.assertEqual(len(scales), len(TERM_NAMES))

    def test_fit_per_term_exact_recovery(self):
        model, rows, true_scales = _synthetic_model()
        measurements = {
            term: [true_scales[term] * rows[i][j] for i in range(len(rows))]
            for j, term in enumerate(TERM_NAMES)
        }
        fitted = fit_scale_factors(measurements, model=model)
        self.assertEqual(set(fitted), set(TERM_NAMES))
        for term in TERM_NAMES:
            self.assertGreaterEqual(fitted[term], 0.0)
            self.assertAlmostEqual(fitted[term], true_scales[term], places=8)

    def test_fit_total_exact_recovery(self):
        model, rows, true_scales = _synthetic_model(n=120)
        total = [
            sum(true_scales[term] * rows[i][j] for j, term in enumerate(TERM_NAMES))
            for i in range(len(rows))
        ]
        fitted = fit_scale_factors({"total": total}, model=model)
        for term in TERM_NAMES:
            self.assertGreaterEqual(fitted[term], 0.0)
            self.assertAlmostEqual(fitted[term], true_scales[term], places=2)

    def test_fit_validation(self):
        model, _rows, _true = _synthetic_model(n=20)
        with self.assertRaises(ValueError):
            fit_scale_factors({}, model=model)
        with self.assertRaises(ValueError):
            fit_scale_factors({"thermal": [1.0, 2.0]}, model=model)  # length mismatch
        with self.assertRaises(KeyError):
            fit_scale_factors({"nope": [1.0] * 20}, model=model)
        with self.assertRaises(ValueError):
            fit_scale_factors({"thermal": [float("nan")] * 20}, model=model)
        with self.assertRaises(ValueError):
            fit_scale_factors({"thermal": [1.0] * 20})  # no model and no simulator

    def test_model_measurements_shape(self):
        measurements = model_measurements(self.v3, self.placements)
        self.assertEqual(set(measurements["terms"]), set(TERM_NAMES))
        self.assertEqual(measurements["n"], len(self.placements))
        for term in TERM_NAMES:
            self.assertEqual(len(measurements["terms"][term]), len(self.placements))
        self.assertEqual(len(measurements["total"]), len(self.placements))

    def test_calibrate_fits_and_wraps(self):
        model = model_measurements(self.v3, self.placements)
        true_scales = {term: 1.0 for term in TERM_NAMES}
        true_scales["loop_inductance"] = 1.7
        measurements = {
            term: [true_scales[term] * value for value in model["terms"][term]]
            for term in TERM_NAMES
        }
        calibrated = calibrate(self.v3, measurements, model=model)
        self.assertIsInstance(calibrated, CalibratedSimulator)
        self.assertAlmostEqual(calibrated.scales["loop_inductance"], 1.7, places=6)
        # unmeasured other terms stay near 1
        self.assertAlmostEqual(calibrated.scales["escape"], 1.0, places=6)
        self.assertTrue(math.isfinite(calibrated.score(self.placements[0])))

    def test_measurement_aliases_work(self):
        model = model_measurements(self.v3, self.placements)
        measurements = {
            "loop_nh": [2.0 * value for value in model["terms"]["loop_inductance"]],
            "thermal_c": list(model["terms"]["thermal"]),
        }
        fitted = fit_scale_factors(measurements, model=model)
        self.assertAlmostEqual(fitted["loop_inductance"], 2.0, places=6)
        self.assertAlmostEqual(fitted["thermal"], 1.0, places=6)

    def test_fit_is_deterministic(self):
        model, rows, true_scales = _synthetic_model(n=60)
        measurements = {
            term: [true_scales[term] * rows[i][j] for i in range(60)]
            for j, term in enumerate(TERM_NAMES)
        }
        first = fit_scale_factors(measurements, model=model)
        second = fit_scale_factors(measurements, model=model)
        self.assertEqual(first, second)

    def test_deterministic_across_processes(self):
        snippet = (
            "import random\n"
            "from mp_place.calibrate import TERM_NAMES, fit_scale_factors, CalibratedSimulator\n"
            "from mp_place.templates import instantiate\n"
            "from mp_place.solver import random_feasible_placement\n"
            "sc = instantiate('buck', 0)\n"
            "pl = random_feasible_placement(sc, random.Random(1))\n"
            "rng = random.Random(3)\n"
            "n = 40\n"
            "rows = [[rng.uniform(0.05, 2.0) for _ in TERM_NAMES] for _ in range(n)]\n"
            "model = {'terms': {t: [rows[i][j] for i in range(n)] for j, t in enumerate(TERM_NAMES)}, 'n': n}\n"
            "meas = {t: [1.2 * rows[i][j] for i in range(n)] for j, t in enumerate(TERM_NAMES)}\n"
            "scales = fit_scale_factors(meas, model=model)\n"
            "sim = CalibratedSimulator(sc, seed=0, scales=scales)\n"
            "print(repr(sorted((t, round(v, 8)) for t, v in scales.items())))\n"
            "print(repr(sim.score(pl)))\n"
        )

        def run(hash_seed):
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
        out_b = run("543210")
        self.assertEqual(out_a, out_b)


class StudyFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.TemporaryDirectory()
        cls.tmp = pathlib.Path(cls._tmpdir.name)
        cls.data = run_calibration_study(
            templates=("buck",),
            cal_sizes=(5, 10, 20, 40),
            cal_pool=80,
            holdout_pool=60,
            quiet=True,
        )

    @classmethod
    def tearDownClass(cls):
        cls._tmpdir.cleanup()

    def _rows(self, perturbation, observation, n_cal=None):
        rows = [
            row
            for row in self.data["aggregated"]
            if row["perturbation"] == perturbation and row["observation"] == observation
        ]
        if n_cal is not None:
            rows = [row for row in rows if int(row["n_cal"]) == n_cal]
        return rows[0] if rows else None

    def test_config_and_perturbations(self):
        config = self.data["config"]
        self.assertEqual(config["templates"], ["buck"])
        self.assertEqual(set(config["perturbations"]), set(PERTURBATIONS))
        self.assertEqual(config["observation_modes"], ["per_term", "total"])
        self.assertEqual(config["cal_sizes"], [5, 10, 20, 40])
        self.assertIn("results", self.data)
        self.assertGreaterEqual(len(self.data["results"]), 3 * 2 * 4)

    def test_no_measurement_identity_is_recorded(self):
        self.assertTrue(self.data["summary"]["no_measurement_identity"])

    def test_per_term_calibration_improves_ranking(self):
        for perturbation in PERTURBATIONS:
            row = self._rows(perturbation, "per_term", n_cal=40)
            self.assertIsNotNone(row)
            self.assertGreater(row["holdout"]["spearman_cal"], row["holdout"]["spearman_uncal"] - 1e-9)
            self.assertGreaterEqual(
                row["holdout"]["top_k_cal"], row["holdout"]["top_k_uncal"]
            )
            # the fitted perturbed scale is close to the ground truth
            truth = max(PERTURBATIONS[perturbation].values())
            self.assertLess(abs(row["fitted_perturbed_scale"] - truth), 0.1 * max(1.0, truth) + 0.05)

    def test_fit_monotone_with_more_samples(self):
        for perturbation in PERTURBATIONS:
            early = self._rows(perturbation, "per_term", n_cal=5)
            late = self._rows(perturbation, "per_term", n_cal=40)
            # more calibration samples do not hurt held-out ranking
            self.assertGreaterEqual(
                late["holdout"]["spearman_cal"],
                early["holdout"]["spearman_cal"] - 0.01,
            )
            # and the recovered scale gets no worse (within noise)
            early_error = abs(
                early["fitted_perturbed_scale"]
                - max(PERTURBATIONS[perturbation].values())
            )
            late_error = abs(
                late["fitted_perturbed_scale"]
                - max(PERTURBATIONS[perturbation].values())
            )
            self.assertLessEqual(late_error, early_error + 0.15)

    def test_total_observation_improves_ranking(self):
        for perturbation in PERTURBATIONS:
            row = self._rows(perturbation, "total", n_cal=40)
            self.assertIsNotNone(row)
            self.assertGreaterEqual(
                row["holdout"]["spearman_cal"], row["holdout"]["spearman_uncal"] - 0.02
            )
            self.assertLessEqual(
                row["holdout"]["rel_rmse_cal"], row["holdout"]["rel_rmse_uncal"]
            )

    def test_data_requirements_shape(self):
        requirements = self.data["data_requirements"]
        self.assertEqual(len(requirements), 3 * 2)
        for key, value in requirements.items():
            self.assertIn("n_min_90pct_rank_gain", value)
            self.assertIn("n_min_scale_error_5pct", value)
            self.assertIn("max_rank_gain", value)
            self.assertIn("final_holdout_spearman", value)
        per_term_keys = [key for key in requirements if key.endswith("/per_term")]
        for key in per_term_keys:
            self.assertIsNotNone(requirements[key]["n_min_scale_error_5pct"])

    def test_heldout_overfitting_small(self):
        overfitting = self.data["overfitting"]
        self.assertGreater(overfitting["n_rows"], 0)
        self.assertLess(abs(overfitting["mean_gap"]), 0.05)
        rows = self.data["heldout_validation"]
        self.assertEqual(len(rows), 3 * 2)
        for row in rows:
            self.assertLessEqual(row["in_sample_spearman"], 1.0 + 1e-9)
            self.assertGreaterEqual(row["holdout_spearman"], 0.0)

    def test_study_is_deterministic(self):
        again = run_calibration_study(
            templates=("buck",),
            cal_sizes=(5, 10, 20, 40),
            cal_pool=80,
            holdout_pool=60,
            quiet=True,
        )

        def strip(value):
            if isinstance(value, dict):
                return {k: strip(v) for k, v in value.items() if k != "runtime_s"}
            if isinstance(value, list):
                return [strip(item) for item in value]
            return value

        self.assertEqual(
            json.dumps(strip(again), sort_keys=True),
            json.dumps(strip(self.data), sort_keys=True),
        )

    def test_report_writer_and_renderer(self):
        md_path, json_path = write_report(self.data, self.tmp / "report")
        self.assertTrue(md_path.exists())
        self.assertTrue(json_path.exists())
        parsed = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertEqual(
            set(parsed),
            {
                "config",
                "results",
                "aggregated",
                "data_requirements",
                "heldout_validation",
                "overfitting",
                "summary",
                "runtime_s",
            },
        )
        text = md_path.read_text(encoding="utf-8")
        for section in ("## 1.", "## 2.", "## 3.", "## 4.", "## 5.", "## 6."):
            self.assertIn(section, text)
        self.assertIn("per_term", text)
        self.assertIn("total", text)
        self.assertGreaterEqual(text.count("|"), 20)
        self.assertIsInstance(render_markdown(self.data), str)
        md2, json2 = write_report(self.data, self.tmp / "report")
        self.assertEqual(md2.read_bytes(), md_path.read_bytes())
        self.assertEqual(json2.read_bytes(), json_path.read_bytes())


class ScaleRecoveryUnitTests(unittest.TestCase):
    """Pure least-squares sanity checks that do not touch scenarios."""

    def test_fit_single_scale_zero_signal_keeps_prior(self):
        from mp_place.calibrate import _fit_single_scale

        self.assertEqual(_fit_single_scale([0.0] * 10, [0.0] * 10), 1.0)
        self.assertAlmostEqual(
            _fit_single_scale([1.0, 2.0, 3.0], [2.0, 4.0, 6.0]), 2.0, places=6
        )

    def test_truth_scales_for(self):
        scales = truth_scales_for("loop_bigger")
        self.assertEqual(scales["loop_inductance"], PERTURBATIONS["loop_bigger"]["loop_inductance"])
        self.assertEqual(scales["thermal"], 1.0)
        self.assertEqual(len(scales), len(TERM_NAMES))
        with self.assertRaises(KeyError):
            truth_scales_for("nope")

    def test_aliases_cover_expected_names(self):
        for alias in ("loop_nh", "thermal_c", "pdn_au", "coupling_au"):
            self.assertIn(alias, MEASUREMENT_ALIASES)
            self.assertIn(MEASUREMENT_ALIASES[alias], TERM_NAMES)


if __name__ == "__main__":
    unittest.main()
