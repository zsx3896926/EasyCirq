"""Unit tests for the P2.6 data-scale learning-curve module (``mp_place.datascale``).

Run from the project root::

    python -m unittest tests.test_datascale -v

The fixture builds the smallest meaningful experiment (2 templates, n=240/1000,
one downstream template, 400 held-out layouts) into a temporary cache, so the
tests never depend on (or pollute) the repository ``data/`` cache.
"""

from __future__ import annotations

import json
import math
import pathlib
import random
import tempfile
import time
import unittest

from mp_place.datascale import (
    DEFAULT_CACHE_DIR,
    RidgeSurrogate,
    build_basis_diagnostic,
    build_learning_curve,
    evaluate_regression,
    expand_features,
    feature_keep_indices,
    fit_surrogate,
    prepare_datasets,
    render_markdown,
    run_downstream,
    run_scaling,
    summarize,
    test_cache_path,
    train_cache_path,
    write_report,
)
from mp_place.features import FEATURE_NAMES, extract_features, feature_vector
from mp_place.solver import random_feasible_placement
from mp_place.templates import instantiate

_HEX_DIGITS = set("0123456789abcdef")
_TIMING_KEYS = {"runtime_s", "mean_runtime_s"}


def _strip_timing(value):
    """Recursively drop wall-clock fields so two runs are comparable."""
    if isinstance(value, dict):
        return {
            key: _strip_timing(item)
            for key, item in value.items()
            if key not in _TIMING_KEYS
        }
    if isinstance(value, list):
        return [_strip_timing(item) for item in value]
    return value


class DataScaleFixture(unittest.TestCase):
    """Shared small experiment used by the read-only tests below."""

    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.TemporaryDirectory()
        cls.tmp = pathlib.Path(cls._tmpdir.name)
        cls.cache = cls.tmp / "cache"
        started = time.perf_counter()
        cls.data = run_scaling(
            templates=("mcu-min", "buck"),
            downstream_templates=("mcu-min",),
            sizes=(240, 1000),
            downstream_seeds=(0, 1),
            steps=60,
            restarts=2,
            test_size=400,
            include_basis_diagnostic=True,
            basis_sizes=(240, 1000),
            cache_dir=cls.cache,
            quiet=True,
        )
        cls.build_seconds = time.perf_counter() - started
        cls.learning = cls.data["learning_curve"]
        cls.downstream = cls.data["downstream"]
        cls.summary = cls.data["summary"]
        cls.basis = cls.data["basis_diagnostic"]

    @classmethod
    def tearDownClass(cls):
        cls._tmpdir.cleanup()

    def test_fixture_and_cache_paths(self):
        self.assertLess(self.build_seconds, 120.0)
        self.assertEqual(len(self.learning), 4)  # 2 templates x 2 sizes
        for template in ("mcu-min", "buck"):
            for n in (240, 1000):
                self.assertTrue(train_cache_path(template, n, cache_dir=self.cache).exists())
            self.assertTrue(test_cache_path(template, test_size=400, cache_dir=self.cache).exists())
        self.assertEqual(
            train_cache_path("buck", 240).name, "buck_v2_n240_s0.json.gz"
        )
        self.assertEqual(
            test_cache_path("buck", test_size=400).name, "buck_v2_test_n400_s1.json.gz"
        )

    def test_learning_curve_rows_complete(self):
        self.assertEqual(len(self.learning), 4)
        seen = set()
        for row in self.learning:
            self.assertIn(row["template"], ("mcu-min", "buck"))
            self.assertIn(int(row["n"]), (240, 1000))
            seen.add((row["template"], int(row["n"])))
            fit = row["fit"]
            self.assertEqual(fit["train_size"], int(row["n"]))
            self.assertEqual(
                len(fit["kept_features"]) + len(fit["dropped_features"]),
                len(FEATURE_NAMES),
            )
            self.assertTrue(fit["kept_features"])
            # constant columns are dropped (they would blow up RidgeModel's std)
            self.assertIn("density", fit["dropped_features"])
            self.assertIn("capcount", fit["dropped_features"])
            self.assertEqual(row["test_size"], 400)
            for metric in ("r2_test", "spearman_test", "tail_spearman"):
                self.assertTrue(math.isfinite(row[metric]), metric)
            self.assertIn("top100_regret", row)
            self.assertLessEqual(row["r2_test"], 1.0 + 1e-6)
            self.assertGreater(row["r2_test"], 0.5)  # well-defined, not a blow-up
            self.assertGreaterEqual(row["spearman_test"], -1.0)
            self.assertLessEqual(row["spearman_test"], 1.0)
            digest = row["dataset"]["placements_hash"]
            self.assertEqual(len(digest), 64)
            self.assertTrue(set(digest) <= _HEX_DIGITS)
            self.assertEqual(row["dataset"]["n"], int(row["n"]))
        self.assertEqual(
            seen,
            {
                ("mcu-min", 240),
                ("mcu-min", 1000),
                ("buck", 240),
                ("buck", 1000),
            },
        )

    def test_curve_is_deterministic(self):
        repeat = build_learning_curve(
            ("mcu-min", "buck"),
            (240, 1000),
            test_size=400,
            cache_dir=self.cache,
        )
        self.assertEqual(
            json.dumps(_strip_timing(repeat), sort_keys=True),
            json.dumps(_strip_timing(self.learning), sort_keys=True),
        )

    def test_dataset_reproducible_in_fresh_cache(self):
        with tempfile.TemporaryDirectory() as other:
            rows = build_learning_curve(
                ("mcu-min",),
                (240,),
                test_size=400,
                cache_dir=pathlib.Path(other) / "cache",
            )
        self.assertEqual(len(rows), 1)
        reference = next(
            row
            for row in self.learning
            if row["template"] == "mcu-min" and int(row["n"]) == 240
        )
        for field in (
            "r2_test",
            "spearman_test",
            "tail_spearman",
            "top100_regret",
            "dataset",
        ):
            self.assertEqual(rows[0][field], reference[field], field)

    def test_summary_aggregates(self):
        summary = self.summary
        self.assertEqual(summary["templates"], ["buck", "mcu-min"])
        self.assertEqual(summary["sizes"], [240, 1000])
        for metric in ("r2_test", "spearman_test", "tail_spearman"):
            self.assertEqual(set(summary["learning_curve_mean"][metric]), {"240", "1000"})
        self.assertIn("r2_gain", summary)
        self.assertEqual(summary["r2_gain"]["from_n"], 240)
        self.assertEqual(summary["r2_gain"]["to_n"], 1000)
        self.assertIn("regret_reduction", summary)
        # downstream aggregate
        means = summary["downstream_mean_truth"]
        self.assertIn("oracle_v2", means)
        self.assertIn("multiphysics_proxy", means)
        self.assertIn("surrogate_n240", means)
        self.assertIn("surrogate_n1000", means)
        self.assertIn("240", summary["surrogate_gap_to_oracle_pct"])
        # basis diagnostic aggregate
        self.assertIn("basis_diagnostic_mean", summary)
        basis_mean = summary["basis_diagnostic_mean"]
        self.assertEqual(set(basis_mean["r2_test"]), {"240", "1000"})
        self.assertEqual(set(basis_mean["top100_regret"]), {"240", "1000"})

    def test_downstream_rows_complete(self):
        objectives = {row["objective"] for row in self.downstream}
        self.assertEqual(
            objectives,
            {
                "multiphysics_proxy",
                "oracle_v2",
                "surrogate_n240",
                "surrogate_n1000",
            },
        )
        for row in self.downstream:
            self.assertEqual(row["template"], "mcu-min")
            self.assertTrue(math.isfinite(row["mean_truth"]))
            self.assertGreaterEqual(row["mean_truth"], 0.0)
            self.assertTrue(math.isfinite(row["std_truth"]))
            self.assertEqual(len(row["per_seed_truth"]), 2)
            self.assertEqual(row["max_violations"], 0)
            self.assertEqual(row["solver"], "portfolio-v2")
            if row["objective"].startswith("surrogate_n"):
                self.assertIn(row["n"], (240, 1000))
            else:
                self.assertIsNone(row["n"])

    def test_downstream_is_deterministic(self):
        repeat = run_downstream(
            ("mcu-min",),
            (240, 1000),
            seeds=(0, 1),
            steps=60,
            restarts=2,
            test_size=400,
            cache_dir=self.cache,
        )
        self.assertEqual(
            json.dumps(_strip_timing(repeat), sort_keys=True),
            json.dumps(_strip_timing(self.downstream), sort_keys=True),
        )

    def test_basis_diagnostic(self):
        self.assertEqual(len(self.basis), 4)  # 2 templates x 2 sizes
        for row in self.basis:
            self.assertEqual(row["basis_dim"], len(expand_features([0.1] * 10)))
            self.assertGreater(row["kept_dim"], 0)
            self.assertGreater(row["r2_test"], 0.9)  # physics basis is much better
            self.assertTrue(math.isfinite(row["tail_spearman"]))
            self.assertTrue(math.isfinite(row["top100_regret"]))
        # rebuilding the diagnostic from a fresh cache is deterministic too
        again = build_basis_diagnostic(
            ("mcu-min",), (240,), test_size=400, cache_dir=self.cache
        )
        reference = next(
            row
            for row in self.basis
            if row["template"] == "mcu-min" and int(row["n"]) == 240
        )
        self.assertEqual(again[0]["r2_test"], reference["r2_test"])
        self.assertEqual(again[0]["tail_spearman"], reference["tail_spearman"])

    def test_report_writer_and_renderer(self):
        out = self.tmp / "report"
        md_path, json_path = write_report(self.data, out)
        self.assertTrue(md_path.exists())
        self.assertTrue(json_path.exists())
        raw = json_path.read_text(encoding="utf-8")
        parsed = json.loads(raw)  # writer uses allow_nan=False, so this also checks NaN
        self.assertEqual(
            set(parsed), {"config", "learning_curve", "downstream", "basis_diagnostic", "summary", "runtime_s"}
        )
        self.assertEqual(len(parsed["learning_curve"]), 4)
        text = md_path.read_text(encoding="utf-8")
        self.assertIn("learning curve", text.lower())
        self.assertIn("mcu-min", text)
        self.assertIn("buck", text)
        for section in ("## 1.", "## 2.", "## 3.", "## 4.", "## 5.", "## 6."):
            self.assertIn(section, text)
        self.assertGreaterEqual(text.count("|"), 20)
        # identical data -> identical bytes
        md_path2, json_path2 = write_report(self.data, out)
        self.assertEqual(md_path2.read_bytes(), md_path.read_bytes())
        self.assertEqual(json_path2.read_bytes(), json_path.read_bytes())
        # renderer can be called directly
        self.assertIsInstance(render_markdown(self.data), str)


class MetricAndModelTests(unittest.TestCase):
    """Small deterministic unit tests for the metric/fit helpers (no datasets)."""

    def test_constant_column_filter(self):
        rows = [[0.1 + i * 0.02, 5.0, i * 0.01] for i in range(20)]
        keep = feature_keep_indices(rows)
        self.assertEqual(keep, [0, 2])  # column 1 is constant -> dropped
        # a single row has zero range in every column
        self.assertEqual(feature_keep_indices([[1.0, 2.0]]), [])
        with self.assertRaises(ValueError):
            feature_keep_indices([])

    def test_fit_surrogate_survives_all_constant_features(self):
        dataset = {
            "X": [[0.0] * len(FEATURE_NAMES) for _ in range(50)],
            "y": [1.5] * 50,
            "meta": {"n": 50},
        }
        model, keep, info = fit_surrogate(dataset)
        self.assertEqual(keep, [])
        self.assertEqual(info["kept_features"], [])
        self.assertEqual(len(info["dropped_features"]), len(FEATURE_NAMES))
        self.assertAlmostEqual(model.predict([]), 1.5, places=9)

    def test_evaluate_regression_perfect_predictions(self):
        class _Perfect:
            def predict(self, row):
                return row[0]

        X = [[float(i % 7)] for i in range(200)]
        y = [row[0] for row in X]
        test = {"X": X, "y": y, "meta": {"n": len(X)}}
        metrics = evaluate_regression(_Perfect(), [0], test, top_k=10)
        self.assertAlmostEqual(metrics["r2_test"], 1.0, places=9)
        self.assertAlmostEqual(metrics["spearman_test"], 1.0, places=9)
        self.assertGreaterEqual(metrics["top10_regret"], 0.0)
        self.assertLess(metrics["top10_regret"], 1e-9)

    def test_expand_features_shape_and_finiteness(self):
        base = {
            "hpwl": 0.6,
            "decap": 0.1,
            "loop": 0.4,
            "analog": 0.05,
            "thermal": 0.02,
            "density": 0.04,
            "congestion": 0.1,
            "escape": 0.8,
            "keepout": 0.0,
            "capcount": 0.25,
        }
        expanded = expand_features(feature_vector(base))
        self.assertGreater(len(expanded), len(FEATURE_NAMES))
        self.assertTrue(all(math.isfinite(value) for value in expanded))
        self.assertEqual(expanded[: len(FEATURE_NAMES)], feature_vector(base))

    def test_ridge_surrogate_consistency(self):
        scenario = instantiate("mcu-min", 0)
        with tempfile.TemporaryDirectory() as tmp:
            bank = prepare_datasets(
                ("mcu-min",),
                (240,),
                test_size=400,
                cache_dir=pathlib.Path(tmp) / "cache",
            )
        dataset = bank["mcu-min"]["train"][240]
        model, keep, _info = fit_surrogate(dataset)
        surrogate = RidgeSurrogate(scenario, model, keep)
        row = dataset["X"][0]
        features = dict(zip(FEATURE_NAMES, row))
        expected = model.predict([row[j] for j in keep])
        self.assertAlmostEqual(surrogate.predict_features(features), expected, places=12)
        self.assertEqual(len(surrogate.keep), len(keep))
        placement = random_feasible_placement(scenario, random.Random(0))
        self.assertAlmostEqual(
            surrogate.cost(placement),
            surrogate.predict_features(extract_features(scenario, placement)),
            places=12,
        )
        self.assertTrue(math.isfinite(surrogate.cost(placement)))

    def test_default_cache_dir_is_project_relative(self):
        self.assertEqual(DEFAULT_CACHE_DIR.name, "datascale")
        self.assertEqual(DEFAULT_CACHE_DIR.parent.name, "data")

    def test_summarize_handles_missing_basis(self):
        # build a minimal learning/downstream row pair without running the solver
        learning = [
            {
                "template": "t",
                "n": 240,
                "r2_test": 0.5,
                "spearman_test": 0.5,
                "tail_spearman": 0.4,
                "top100_regret": 0.2,
            }
        ]
        downstream = [
            {"template": "t", "objective": "oracle_v2", "n": None, "mean_truth": 1.0},
            {"template": "t", "objective": "multiphysics_proxy", "n": None, "mean_truth": 1.2},
            {"template": "t", "objective": "surrogate_n240", "n": 240, "mean_truth": 1.1},
        ]
        summary = summarize(learning, downstream)
        self.assertIn("learning_curve_mean", summary)
        self.assertNotIn("basis_diagnostic_mean", summary)
        self.assertEqual(summary["downstream_mean_truth"]["oracle_v2"], 1.0)


if __name__ == "__main__":
    unittest.main()
