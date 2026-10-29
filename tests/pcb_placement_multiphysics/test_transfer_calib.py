"""Unit tests for P2.18 template-surrogate few-shot real-board calibration.

Run from the project root::

    python -m unittest tests.test_transfer_calib -v

The fixture uses a small deterministic configuration (60 template samples per
family, 40 board layouts split 16/16) so the tests stay in a few seconds.  If
the bundled real-board dumps are not available the board-dependent tests are
skipped (``unittest.SkipTest``), and a separate test covers the missing-file
code path explicitly.
"""

from __future__ import annotations

import json
import math
import pathlib
import tempfile
import unittest

from mp_place.transfer import _fit_affine
from mp_place.transfer_calib import (
    K_LIST,
    STRATEGIES,
    USABLE_R2,
    _fit_fine_tune,
    _fine_tune_predictions,
    _metrics,
    _recommend_for_board,
    _validate_k,
    load_real_boards,
    render_markdown,
    run_transfer_calibration,
    write_report,
)

_SMALL = dict(
    template_samples=60,
    board_samples=40,
    k_list=(4, 8, 16),
    calib_pool=16,
    test_size=16,
)

_TIMING_KEYS = {"runtime_s"}


def _strip_timing(value):
    if isinstance(value, dict):
        return {key: _strip_timing(item) for key, item in value.items() if key not in _TIMING_KEYS}
    if isinstance(value, list):
        return [_strip_timing(item) for item in value]
    return value


class CalibrationFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.TemporaryDirectory()
        cls.tmp = pathlib.Path(cls._tmpdir.name)
        cls.data = run_transfer_calibration(**_SMALL, quiet=True)
        if not cls.data["boards"]:
            raise unittest.SkipTest(f"real-board dumps unavailable: {cls.data['missing_boards']}")

    @classmethod
    def tearDownClass(cls):
        cls._tmpdir.cleanup()

    def test_board_rows_structure(self):
        self.assertEqual(len(self.data["boards"]), 3)
        for row in self.data["boards"]:
            self.assertIn(row["board"], ("mcu-i2c", "photo-led", "dual-button"))
            self.assertEqual(len(row["by_k"]), len(_SMALL["k_list"]))
            self.assertEqual(row["test_samples"], _SMALL["test_size"])
            for key in ("r2", "spearman", "regret_top", "n"):
                self.assertIn(key, row["no_cal"])
            for k_row in row["by_k"]:
                self.assertIn(k_row["k"], _SMALL["k_list"])
                for strategy in ("affine", "fine_tune"):
                    metrics = k_row[strategy]
                    self.assertEqual(metrics["n"], _SMALL["test_size"])
                    self.assertTrue(math.isfinite(metrics["r2"]))
                    self.assertTrue(-1.0 <= metrics["spearman"] <= 1.0)
            recommendation = row["recommendation"]
            self.assertIn(recommendation["k"], _SMALL["k_list"])
            self.assertIn(recommendation["strategy"], ("affine", "fine_tune"))
            self.assertIsInstance(row["usable"], bool)
            self.assertIn("best_achievable_r2", row)

    def test_summary_fields(self):
        summary = self.data["summary"]
        self.assertEqual(summary["n_boards"], 3)
        self.assertIn(summary["recommended_k"], _SMALL["k_list"])
        self.assertIn(summary["recommended_strategy"], ("affine", "fine_tune"))
        self.assertEqual(set(summary["recommended_k_per_board"]), {"mcu-i2c", "photo-led", "dual-button"})
        self.assertEqual(set(summary["aggregate_by_k"]), {str(k) for k in _SMALL["k_list"]})
        self.assertIn("no_calibration_mean", summary)
        gain = summary["calibration_gain_at_recommended_k"]
        self.assertTrue(math.isfinite(gain["calibrated_r2"]))
        self.assertGreaterEqual(gain["calibrated_r2"], -1e9)
        self.assertIn("usable_per_board", summary)
        self.assertEqual(summary["cross_board_status"], "OK")

    def test_cross_board_validation(self):
        cross = self.data["cross_board"]
        self.assertEqual(cross["status"], "OK")
        self.assertIn(cross["holdout_board"], ("mcu-i2c", "photo-led", "dual-button"))
        self.assertEqual(len(cross["rows"]), len(_SMALL["k_list"]))
        for k_row in cross["rows"]:
            for key in (
                "cross_board_affine",
                "cross_board_fine_tune",
                "reference_in_domain_affine",
            ):
                metrics = k_row[key]
                self.assertTrue(math.isfinite(metrics["r2"]))
                self.assertTrue(-1.0 <= metrics["spearman"] <= 1.0)
            self.assertGreaterEqual(k_row["calibration_samples_total"], 2 * k_row["k"])
        self.assertIn("note", cross)

    def test_ranking_improves_from_small_to_large_k(self):
        for row in self.data["boards"]:
            by_k = {k_row["k"]: k_row for k_row in row["by_k"]}
            small = by_k[4]["fine_tune"]["r2"]
            large = by_k[16]["fine_tune"]["r2"]
            self.assertGreaterEqual(large, small - 0.25, row["board"])
            # calibrated fine-tune must beat the raw transfer R² on every board
            self.assertGreater(by_k[16]["fine_tune"]["r2"], row["no_cal"]["r2"] + 1.0)

    def test_study_is_deterministic(self):
        again = run_transfer_calibration(**_SMALL, quiet=True)
        self.assertEqual(
            json.dumps(_strip_timing(again), sort_keys=True),
            json.dumps(_strip_timing(self.data), sort_keys=True),
        )

    def test_report_writer_and_renderer(self):
        md_path, json_path = write_report(self.data, self.tmp / "report")
        self.assertTrue(md_path.exists())
        self.assertTrue(json_path.exists())
        parsed = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertEqual(
            set(parsed),
            {"config", "boards", "cross_board", "missing_boards", "summary", "runtime_s"},
        )
        text = md_path.read_text(encoding="utf-8")
        for section in ("## 1.", "## 2.", "## 3.", "## 4.", "## 5.", "## 6."):
            self.assertIn(section, text)
        self.assertIn("fine_tune", text)
        self.assertIn("affine", text)
        self.assertGreaterEqual(text.count("|"), 20)
        self.assertIsInstance(render_markdown(self.data), str)
        md2, json2 = write_report(self.data, self.tmp / "report")
        self.assertEqual(md2.read_bytes(), md_path.read_bytes())
        self.assertEqual(json2.read_bytes(), json_path.read_bytes())


class MissingBoardTests(unittest.TestCase):
    def test_missing_file_is_reported_and_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing_path = pathlib.Path(tmp) / "does-not-exist.json"
            data = run_transfer_calibration(
                template_samples=20,
                board_samples=20,
                k_list=(4, 8),
                calib_pool=8,
                test_size=8,
                sources=[("missing-board", missing_path)],
                quiet=True,
            )
            self.assertEqual(data["boards"], [])
            self.assertEqual(data["missing_boards"][0]["status"], "MISSING")
            self.assertEqual(data["cross_board"]["status"], "SKIPPED")
            self.assertEqual(data["summary"]["n_boards"], 0)
            self.assertIsNone(data["summary"]["recommended_k"])
            md_path, json_path = write_report(data, pathlib.Path(tmp) / "report")
            self.assertTrue(md_path.exists() and json_path.exists())
            text = md_path.read_text(encoding="utf-8")
            self.assertIn("## 1.", text)
            self.assertIn("跳过", text)

    def test_empty_sources_yields_no_boards(self):
        data = run_transfer_calibration(
            template_samples=15,
            board_samples=20,
            k_list=(4,),
            calib_pool=8,
            test_size=8,
            sources=[],
            quiet=True,
        )
        self.assertEqual(data["boards"], [])
        self.assertEqual(data["missing_boards"], [])
        self.assertEqual(data["summary"]["n_boards"], 0)

    def test_load_real_boards_missing_source(self):
        boards, missing = load_real_boards([("nope", pathlib.Path("does/not/exist.json"))])
        self.assertEqual(boards, [])
        self.assertEqual(missing[0]["status"], "MISSING")


class BoundaryTests(unittest.TestCase):
    def test_k_validation(self):
        self.assertEqual(_validate_k((4, 8, 16, 32), 60), (4, 8, 16, 32))
        for bad in ((0,), (-1,), (2.5,), (65,), (4, 4), (True,)):
            with self.assertRaises(ValueError):
                _validate_k(bad, 60)  # type: ignore[arg-type]

    def test_k_boundary_in_run(self):
        with self.assertRaises(ValueError):
            run_transfer_calibration(
                template_samples=10, board_samples=20, k_list=(0,), calib_pool=8, test_size=8
            )
        with self.assertRaises(ValueError):
            run_transfer_calibration(
                template_samples=10, board_samples=20, k_list=(4, 100), calib_pool=8, test_size=8
            )

    def test_affine_degenerate_and_identity(self):
        a, b = _fit_affine([1.0, 2.0, 3.0], [2.0, 4.0, 6.0])
        self.assertAlmostEqual(a, 2.0, places=9)
        self.assertAlmostEqual(b, 0.0, places=9)
        a, b = _fit_affine([5.0, 5.0, 5.0], [1.0, 2.0, 3.0])
        self.assertAlmostEqual(a, 1.0, places=9)
        self.assertAlmostEqual(b, -3.0, places=9)  # mean(true) - mean(pred) = 2 - 5

    def test_metrics_perfect_and_constant(self):
        true = [float(i % 7) for i in range(40)]
        perfect = list(true)
        metrics = _metrics(true, perfect)
        self.assertAlmostEqual(metrics["r2"], 1.0, places=9)
        self.assertAlmostEqual(metrics["spearman"], 1.0, places=9)
        self.assertLessEqual(abs(metrics["regret_top"]), 1e-9)
        constant = [true[0]] * 40
        self.assertTrue(math.isfinite(_metrics(true, constant)["r2"]))

    def test_defaults_contract(self):
        self.assertEqual(K_LIST, (4, 8, 16, 32))
        self.assertEqual(STRATEGIES, ("no_cal", "affine", "fine_tune"))
        self.assertGreater(USABLE_R2, 0.0)


class FineTuneUnitTests(unittest.TestCase):
    def test_fine_tune_learns_linear_relation(self):
        import random

        rng = random.Random(0)
        n, d = 24, 6
        X = [[rng.uniform(-1.0, 1.0) for _ in range(d)] for _ in range(n)]
        transfer = [rng.uniform(0.0, 2.0) for _ in range(n)]
        y = [2.0 * transfer[i] + 3.0 + 0.5 * X[i][0] for i in range(n)]
        fitted = _fit_fine_tune(X, y, transfer)
        self.assertIsNotNone(fitted)
        predictions = _fine_tune_predictions(X, transfer, fitted)
        self.assertIsNotNone(predictions)
        # ridge (lam=1e-2) is almost exact on this well-conditioned linear relation
        from mp_place.objective import r_squared

        self.assertGreater(r_squared(y, predictions), 0.999)

    def test_fine_tune_drops_constant_columns(self):
        X = [[0.0, float(i)] for i in range(20)]
        transfer = [float(i) for i in range(20)]
        y = [3.0 + 2.0 * transfer[i] for i in range(20)]
        fitted = _fit_fine_tune(X, y, transfer)
        self.assertIsNotNone(fitted)
        model, keep = fitted
        self.assertNotIn(0, keep)  # constant feature column dropped
        self.assertIn(1, keep)

    def test_fine_tune_is_deterministic(self):
        import random

        rng = random.Random(1)
        n = 20
        X = [[rng.uniform(-1.0, 1.0) for _ in range(4)] for _ in range(n)]
        transfer = [rng.uniform(0.0, 1.0) for _ in range(n)]
        y = [transfer[i] + 0.3 * X[i][1] for i in range(n)]
        first = _fine_tune_predictions(X, transfer, _fit_fine_tune(X, y, transfer))
        second = _fine_tune_predictions(X, transfer, _fit_fine_tune(X, y, transfer))
        self.assertEqual(first, second)


class RecommendationUnitTests(unittest.TestCase):
    @staticmethod
    def _row(*k_metrics):
        """k_metrics: (k, affine (r2, rho, regret), fine (r2, rho, regret))."""
        by_k = []
        for k, affine, fine in k_metrics:
            block = {}
            for name, values in (("affine", affine), ("fine_tune", fine)):
                block[name] = {
                    "r2": values[0],
                    "spearman": values[1],
                    "regret_top": values[2],
                    "n": 60,
                }
            by_k.append({"k": k, "affine": block["affine"], "fine_tune": block["fine_tune"]})
        return {"board": "synthetic", "by_k": by_k}

    def test_recommends_smallest_k_within_tolerance(self):
        row = self._row(
            (4, (0.40, 0.80, 0.10), (0.45, 0.82, 0.09)),
            (8, (0.60, 0.85, 0.05), (0.70, 0.88, 0.04)),
            (16, (0.80, 0.90, 0.02), (0.95, 0.95, 0.01)),
            (32, (0.82, 0.91, 0.02), (0.96, 0.96, 0.01)),
        )
        recommendation = _recommend_for_board(row)
        self.assertEqual(recommendation["k"], 16)
        self.assertEqual(recommendation["strategy"], "fine_tune")

    def test_recommends_largest_when_no_plateau(self):
        row = self._row(
            (4, (0.10, 0.50, 0.30), (0.12, 0.52, 0.28)),
            (8, (0.20, 0.55, 0.25), (0.22, 0.57, 0.24)),
            (16, (0.30, 0.60, 0.20), (0.32, 0.62, 0.19)),
            (32, (0.40, 0.65, 0.15), (0.42, 0.67, 0.14)),
        )
        recommendation = _recommend_for_board(row)
        self.assertEqual(recommendation["k"], 32)

    def test_handles_missing_regret(self):
        row = self._row((4, (0.5, 0.7, None), (0.55, 0.72, None)))
        recommendation = _recommend_for_board(row)
        self.assertEqual(recommendation["k"], 4)


if __name__ == "__main__":
    unittest.main()
