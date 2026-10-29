"""Tests for P4.9 realboard regression benchmark (stdlib unittest).

Run with::

    python -m unittest tests.test_realboard_benchmark -v

Covered contract
----------------
* baseline JSON round-trip in a temporary directory, strict schema validation
  on read/write and ``BenchmarkError`` for corrupted / incomplete baselines;
* ``collect_baseline`` freezes the 4-board suite metrics (schema/time/config/
  source SHA256/per-board metrics/suite means);
* ``compare_to_baseline`` drift detection with injected fake data: truth +5%
  boundary passes / +5.01% fails, completion drop 0.02 passes / 0.021 fails,
  board-count decrease fails, feasibility loss fails, source-SHA change and new
  boards are warnings, suite means are checked too;
* missing cases produce ``SKIP`` (and ``--update-baseline`` refuses to freeze);
* determinism: two suite runs give identical frozen baselines after stripping
  wall-clock/generation fields;
* the CLI ``--update-baseline`` / ``--check`` works end-to-end on an explicit
  synthetic dump and fails (exit 1) on an injected drift.
"""

from __future__ import annotations

import copy
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2] / "benchmarks" / "pcb-placement-multiphysics"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mp_place import realboard  # noqa: E402
from mp_place import realboard_benchmark as bench  # noqa: E402
from .test_realboard import synthetic_dump  # noqa: E402


# --------------------------------------------------------------------------- #
# shared fixtures
# --------------------------------------------------------------------------- #
def _write_dump(tmp_dir) -> pathlib.Path:
    path = pathlib.Path(tmp_dir) / "synthetic-dump.json"
    path.write_text(json.dumps(synthetic_dump()), encoding="utf-8")
    return path


def _synthetic_report(tmp_dir) -> dict:
    """A fast but realistic realboard v3 suite report (steps=0)."""
    dump_path = _write_dump(tmp_dir)
    return realboard.run_all_v3(
        sources=[("synthetic", dump_path)], steps=0, max_routes=1
    )


class _SharedReport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.report = _synthetic_report(cls._tmp.name)
        cls.baseline = bench.collect_baseline(cls.report)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()


# --------------------------------------------------------------------------- #
# baseline IO / validation
# --------------------------------------------------------------------------- #
class BaselineIOTests(_SharedReport):
    def test_round_trip_into_temp_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = pathlib.Path(tmp) / "nested" / "REALBOARD_BASELINE.json"
            written = bench.save_baseline(self.baseline, target)
            self.assertEqual(written, target)
            loaded = bench.load_baseline(target)
            self.assertEqual(
                bench.strip_volatile_baseline(loaded),
                bench.strip_volatile_baseline(self.baseline),
            )
            self.assertEqual(loaded["schema"], bench.BASELINE_SCHEMA)
            self.assertIn("tolerances", loaded)
            self.assertEqual(loaded["tolerances"]["truth_relative_degradation"], 0.05)
            self.assertEqual(loaded["tolerances"]["completion_drop"], 0.02)
            text = target.read_text(encoding="utf-8")
            self.assertIn('"schema": "mp_place.realboard-baseline/v1"', text)

    def test_collected_baseline_fields(self):
        baseline = self.baseline
        self.assertEqual(baseline["schema"], bench.BASELINE_SCHEMA)
        self.assertTrue(baseline["generated_at"])
        self.assertEqual(baseline["generated_by"], "python -m mp_place.realboard_benchmark --update-baseline")
        self.assertIn("environment", baseline)
        self.assertEqual(baseline["config"]["steps"], 0)
        self.assertEqual(len(baseline["boards"]), 1)
        board = baseline["boards"][0]
        self.assertEqual(board["name"], "synthetic")
        self.assertEqual(len(board["source_sha256"]), 64)
        for group in ("original", "optimized", "repair"):
            metrics = board["metrics"][group]
            for key in ("completion", "truth_v2", "feasible"):
                self.assertIn(key, metrics)
            self.assertIsInstance(metrics["truth_v2"], float)
            self.assertIsInstance(metrics["completion"], float)
            self.assertIsInstance(metrics["feasible"], bool)
        suite = baseline["suite"]
        self.assertEqual(suite["n_boards"], 1)
        self.assertIn("optimized", suite["mean_completion"])
        self.assertIn("repair", suite["mean_truth_v2"])
        self.assertEqual(suite["best_board"]["name"], "synthetic")

    def test_collect_rejects_wrong_schema(self):
        with self.assertRaises(bench.BenchmarkError):
            bench.collect_baseline({"schema": "something/else", "boards": []})

    def test_collect_rejects_empty_boards(self):
        report = copy.deepcopy(self.report)
        report["boards"] = []
        with self.assertRaises(bench.BenchmarkError):
            bench.collect_baseline(report)

    def test_save_rejects_incomplete_payload(self):
        payload = copy.deepcopy(self.baseline)
        del payload["suite"]
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(bench.BenchmarkError):
                bench.save_baseline(payload, pathlib.Path(tmp) / "baseline.json")

    def test_load_missing_file_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                bench.load_baseline(pathlib.Path(tmp) / "nope.json")

    def test_corrupted_json_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = pathlib.Path(tmp) / "REALBOARD_BASELINE.json"
            target.write_text("{not json", encoding="utf-8")
            with self.assertRaises(bench.BenchmarkError) as ctx:
                bench.load_baseline(target)
            self.assertIn("not valid JSON", str(ctx.exception))

    def test_missing_board_metrics_raises(self):
        payload = copy.deepcopy(self.baseline)
        del payload["boards"][0]["metrics"]["optimized"]
        with self.assertRaises(bench.BenchmarkError):
            bench.validate_baseline(payload)

    def test_bad_tolerance_raises(self):
        payload = copy.deepcopy(self.baseline)
        payload["tolerances"]["truth_relative_degradation"] = "not-a-number"
        with self.assertRaises(bench.BenchmarkError):
            bench.validate_baseline(payload)

    def test_read_status_ok_missing_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = pathlib.Path(tmp) / "missing.json"
            self.assertEqual(bench.read_baseline_status(missing)["status"], "MISSING")

            invalid = pathlib.Path(tmp) / "invalid.json"
            invalid.write_text("not json", encoding="utf-8")
            status = bench.read_baseline_status(invalid)
            self.assertEqual(status["status"], "INVALID")
            self.assertTrue(status["error"])

            valid = pathlib.Path(tmp) / "REALBOARD_BASELINE.json"
            bench.save_baseline(self.baseline, valid)
            status = bench.read_baseline_status(valid)
            self.assertEqual(status["status"], "OK")
            self.assertTrue(status["readable"])


# --------------------------------------------------------------------------- #
# drift detection (injected fake data)
# --------------------------------------------------------------------------- #
class DriftDetectionTests(_SharedReport):
    def _compare(self, current=None):
        return bench.compare_to_baseline(current or self.baseline, self.baseline)

    def _mutate(self, mutate):
        payload = copy.deepcopy(self.baseline)
        mutate(payload)
        return payload

    def test_identical_metrics_pass(self):
        comparison = self._compare()
        self.assertEqual(comparison["schema"], bench.COMPARISON_SCHEMA)
        self.assertEqual(comparison["status"], "PASS")
        self.assertEqual(comparison["hard_drifts"], 0)
        self.assertEqual(comparison["drifts"], [])
        self.assertGreater(len(comparison["checks"]), 10)
        self.assertEqual(comparison["baseline"]["schema"], bench.BASELINE_SCHEMA)

    def test_truth_boundary_passes(self):
        def mutate(payload):
            board = payload["boards"][0]
            board["metrics"]["optimized"]["truth_v2"] = round(
                board["metrics"]["optimized"]["truth_v2"] * 1.05, 9
            )

        comparison = self._compare(self._mutate(mutate))
        self.assertEqual(comparison["status"], "PASS", comparison["drifts"])
        self.assertEqual(comparison["hard_drifts"], 0)

    def test_truth_beyond_limit_fails(self):
        def mutate(payload):
            board = payload["boards"][0]
            board["metrics"]["optimized"]["truth_v2"] = (
                board["metrics"]["optimized"]["truth_v2"] * 1.0501
            )

        comparison = self._compare(self._mutate(mutate))
        self.assertEqual(comparison["status"], "FAIL")
        names = {drift["name"] for drift in comparison["drifts"]}
        self.assertIn("board.synthetic.optimized.truth_v2", names)
        drift = next(
            item for item in comparison["drifts"]
            if item["name"] == "board.synthetic.optimized.truth_v2"
        )
        self.assertEqual(drift["severity"], "hard")
        self.assertGreater(drift["delta"], 0.0)

    def test_completion_drop_boundary_passes_and_beyond_fails(self):
        def at_drop(payload, drop):
            board = payload["boards"][0]
            base = self.baseline["boards"][0]["metrics"]["repair"]["completion"]
            board["metrics"]["repair"]["completion"] = base - drop

        passing = self._compare(self._mutate(lambda p: at_drop(p, 0.02)))
        self.assertEqual(passing["status"], "PASS", passing["drifts"])
        failing = self._compare(self._mutate(lambda p: at_drop(p, 0.021)))
        self.assertEqual(failing["status"], "FAIL")
        self.assertIn(
            "board.synthetic.repair.completion",
            {drift["name"] for drift in failing["drifts"]},
        )

    def test_board_count_decrease_fails(self):
        # baseline with two boards; a current run that measures only one board
        two_board_baseline = copy.deepcopy(self.baseline)
        second = copy.deepcopy(two_board_baseline["boards"][0])
        second["name"] = "second-board"
        two_board_baseline["boards"].append(second)
        two_board_baseline["suite"]["n_boards"] = 2
        comparison = bench.compare_to_baseline(self.baseline, two_board_baseline)
        self.assertEqual(comparison["status"], "FAIL")
        names = {drift["name"] for drift in comparison["drifts"]}
        self.assertIn("suite.n_boards", names)
        self.assertIn("board.second-board.missing", names)
        # same board count passes
        self.assertEqual(
            bench.compare_to_baseline(
                copy.deepcopy(two_board_baseline), two_board_baseline
            )["status"],
            "PASS",
        )

    def test_missing_board_fails(self):
        def mutate(payload):
            payload["boards"][0]["name"] = "another-board"

        comparison = self._compare(self._mutate(mutate))
        self.assertEqual(comparison["status"], "FAIL")
        names = {drift["name"] for drift in comparison["drifts"]}
        self.assertIn("board.synthetic.missing", names)

    def test_new_board_is_warning_only(self):
        def mutate(payload):
            extra = copy.deepcopy(payload["boards"][0])
            extra["name"] = "extra-board"
            payload["boards"].append(extra)
            payload["suite"]["n_boards"] += 1

        comparison = self._compare(self._mutate(mutate))
        self.assertEqual(comparison["status"], "PASS")
        self.assertGreaterEqual(comparison["warnings"], 1)
        self.assertIn(
            "board.extra-board.new",
            {drift["name"] for drift in comparison["drifts"]},
        )

    def test_source_sha_change_is_warning_only(self):
        def mutate(payload):
            payload["boards"][0]["source_sha256"] = "f" * 64

        comparison = self._compare(self._mutate(mutate))
        self.assertEqual(comparison["status"], "PASS")
        self.assertIn(
            "board.synthetic.source_sha256",
            {drift["name"] for drift in comparison["drifts"]},
        )

    def test_feasibility_loss_fails(self):
        def mutate(payload):
            payload["boards"][0]["metrics"]["optimized"]["feasible"] = False
            payload["suite"]["all_feasible"]["optimized"] = False

        comparison = self._compare(self._mutate(mutate))
        self.assertEqual(comparison["status"], "FAIL")
        names = {drift["name"] for drift in comparison["drifts"]}
        self.assertIn("board.synthetic.optimized.feasible", names)
        self.assertIn("suite.all_feasible.optimized", names)

    def test_suite_mean_checks(self):
        def mutate(payload):
            for board in payload["boards"]:
                for group in ("optimized", "repair"):
                    board["metrics"][group]["truth_v2"] *= 1.06
            for group in ("optimized", "repair"):
                payload["suite"]["mean_truth_v2"][group] *= 1.06

        comparison = self._compare(self._mutate(mutate))
        self.assertEqual(comparison["status"], "FAIL")
        names = {drift["name"] for drift in comparison["drifts"]}
        self.assertIn("suite.mean_truth_v2.optimized", names)
        self.assertIn("suite.mean_truth_v2.repair", names)

    def test_custom_tolerances_are_applied(self):
        def mutate(payload):
            board = payload["boards"][0]
            board["metrics"]["optimized"]["truth_v2"] *= 1.075

        current = self._mutate(mutate)
        strict = bench.compare_to_baseline(current, self.baseline)
        relaxed = bench.compare_to_baseline(
            current, self.baseline, tolerances={"truth_relative_degradation": 0.10}
        )
        self.assertEqual(strict["status"], "FAIL")
        self.assertEqual(relaxed["status"], "PASS")

    def test_missing_current_is_skip(self):
        comparison = bench.compare_to_baseline(
            None, self.baseline, skip_reason="cases root missing"
        )
        self.assertEqual(comparison["status"], "SKIP")
        self.assertIn("cases root missing", comparison["summary"])
        self.assertEqual(comparison["checks"], [])

    def test_missing_baseline_is_graceful(self):
        comparison = bench.compare_to_baseline(self.baseline, None)
        self.assertEqual(comparison["status"], "NO BASELINE")
        self.assertIn("--update-baseline", comparison["summary"])

    def test_corrupted_inputs_raise(self):
        with self.assertRaises(bench.BenchmarkError):
            bench.compare_to_baseline(self.baseline, {"schema": "bad"})
        with self.assertRaises(bench.BenchmarkError):
            bench.compare_to_baseline({"schema": "bad"}, self.baseline)


# --------------------------------------------------------------------------- #
# suite operations: update / check / skip / determinism
# --------------------------------------------------------------------------- #
class SuiteOperationsTests(unittest.TestCase):
    def test_update_and_check_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            dump_path = _write_dump(tmp)
            baseline_path = pathlib.Path(tmp) / "docs" / "REALBOARD_BASELINE.json"
            md_path = pathlib.Path(tmp) / "docs" / "REALBOARD.md"
            updated = bench.update_baseline(
                baseline_path=baseline_path,
                md_path=md_path,
                sources=[("synthetic", dump_path)],
                steps=0,
                max_routes=1,
            )
            self.assertEqual(updated["status"], "UPDATED")
            self.assertTrue(baseline_path.exists())
            self.assertTrue(md_path.exists())
            md = md_path.read_text(encoding="utf-8")
            for token in ("# P4.9", "冻结快照", "suite 均值", "板级指标", "synthetic"):
                self.assertIn(token, md)
            loaded = bench.load_baseline(baseline_path)
            self.assertEqual(loaded["boards"][0]["name"], "synthetic")

            checked = bench.check_baseline(
                baseline_path=baseline_path,
                md_path=md_path,
                sources=[("synthetic", dump_path)],
                steps=0,
                max_routes=1,
            )
            self.assertEqual(checked["status"], "PASS", checked.get("comparison"))
            self.assertEqual(checked["comparison"]["hard_drifts"], 0)
            md = md_path.read_text(encoding="utf-8")
            for token in ("# P4.9", "漂移项", "检查明细", "board.synthetic"):
                self.assertIn(token, md)

    def test_check_detects_injected_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            dump_path = _write_dump(tmp)
            baseline_path = pathlib.Path(tmp) / "base.json"
            md_path = pathlib.Path(tmp) / "REALBOARD.md"
            bench.update_baseline(
                baseline_path=baseline_path,
                md_path=md_path,
                sources=[("synthetic", dump_path)],
                steps=0,
                max_routes=1,
            )
            tampered = json.loads(baseline_path.read_text(encoding="utf-8"))
            for board in tampered["boards"]:
                board["metrics"]["optimized"]["truth_v2"] *= 0.9  # baseline "better"
                board["metrics"]["repair"]["completion"] = 1.0
            baseline_path.write_text(json.dumps(tampered), encoding="utf-8")
            checked = bench.check_baseline(
                baseline_path=baseline_path,
                md_path=md_path,
                sources=[("synthetic", dump_path)],
                steps=0,
                max_routes=1,
            )
            self.assertEqual(checked["status"], "FAIL")
            self.assertGreater(checked["comparison"]["hard_drifts"], 0)
            self.assertIn("漂移项", md_path.read_text(encoding="utf-8"))

    def test_missing_cases_skip(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing_root = pathlib.Path(tmp) / "no-cases-here"
            evaluation = bench.evaluate_current(cases_root=missing_root, steps=0, max_routes=1)
            self.assertEqual(evaluation["status"], "SKIP")
            self.assertTrue(evaluation["reason"])
            with self.assertRaises(bench.BenchmarkError):
                bench.update_baseline(
                    baseline_path=pathlib.Path(tmp) / "base.json",
                    md_path=pathlib.Path(tmp) / "REALBOARD.md",
                    cases_root=missing_root,
                    steps=0,
                    max_routes=1,
                )
            self.assertFalse((pathlib.Path(tmp) / "base.json").exists())

            # A frozen baseline + missing cases -> graceful SKIP (not a crash).
            baseline_path = pathlib.Path(tmp) / "frozen.json"
            bench.save_baseline(
                bench.collect_baseline(_synthetic_report(tmp)), baseline_path
            )
            result = bench.check_baseline(
                baseline_path=baseline_path,
                md_path=pathlib.Path(tmp) / "SKIP.md",
                cases_root=missing_root,
                steps=0,
                max_routes=1,
            )
            self.assertEqual(result["status"], "SKIP")
            self.assertTrue((pathlib.Path(tmp) / "SKIP.md").exists())
            self.assertIn("SKIP", result["status"])

    def test_missing_baseline_check_is_graceful(self):
        with tempfile.TemporaryDirectory() as tmp:
            dump_path = _write_dump(tmp)
            result = bench.check_baseline(
                baseline_path=pathlib.Path(tmp) / "missing.json",
                md_path=pathlib.Path(tmp) / "md" / "REALBOARD.md",
                sources=[("synthetic", dump_path)],
                steps=0,
                max_routes=1,
            )
            self.assertEqual(result["status"], "NO BASELINE")
            self.assertTrue((pathlib.Path(tmp) / "md" / "REALBOARD.md").exists())

    def test_determinism_of_frozen_baseline(self):
        with tempfile.TemporaryDirectory() as tmp:
            dump_path = _write_dump(tmp)
            first = bench.evaluate_current(
                sources=[("synthetic", dump_path)], steps=0, max_routes=1
            )
            second = bench.evaluate_current(
                sources=[("synthetic", dump_path)], steps=0, max_routes=1
            )
            self.assertEqual(first["status"], "OK")
            self.assertEqual(second["status"], "OK")
            self.assertEqual(
                bench.strip_volatile_baseline(first["baseline"]),
                bench.strip_volatile_baseline(second["baseline"]),
            )
            comparison = bench.compare_to_baseline(
                second["baseline"], first["baseline"]
            )
            self.assertEqual(comparison["status"], "PASS")
            # generated_at exists in the raw payload but is stripped for comparison
            self.assertIn("generated_at", first["baseline"])
            self.assertNotIn(
                "generated_at", bench.strip_volatile_baseline(first["baseline"])
            )


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
class CliTests(unittest.TestCase):
    def _run(self, *args):
        return subprocess.run(
            [sys.executable, "-m", "mp_place.realboard_benchmark", *args],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=300,
        )

    def test_cli_update_then_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            dump_path = _write_dump(tmp)
            baseline_path = pathlib.Path(tmp) / "base.json"
            md_path = pathlib.Path(tmp) / "REALBOARD.md"
            common = [
                "--source",
                f"synthetic={dump_path}",
                "--steps",
                "0",
                "--max-routes",
                "1",
                "--baseline",
                str(baseline_path),
                "--md",
                str(md_path),
                "--json",
            ]
            proc = self._run("--update-baseline", *common)
            self.assertEqual(proc.returncode, 0, proc.stderr[-3000:])
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["status"], "UPDATED")
            self.assertTrue(baseline_path.exists())
            self.assertTrue(md_path.exists())

            proc = self._run("--check", *common)
            self.assertEqual(proc.returncode, 0, proc.stderr[-3000:])
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["status"], "PASS")
            self.assertEqual(payload["comparison"]["hard_drifts"], 0)

    def test_cli_drift_exit_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            dump_path = _write_dump(tmp)
            baseline_path = pathlib.Path(tmp) / "base.json"
            md_path = pathlib.Path(tmp) / "REALBOARD.md"
            common = [
                "--source",
                f"synthetic={dump_path}",
                "--steps",
                "0",
                "--max-routes",
                "1",
                "--baseline",
                str(baseline_path),
                "--md",
                str(md_path),
                "--json",
            ]
            self.assertEqual(self._run("--update-baseline", *common).returncode, 0)
            tampered = json.loads(baseline_path.read_text(encoding="utf-8"))
            tampered["boards"][0]["metrics"]["repair"]["completion"] = 1.0
            tampered["boards"][0]["metrics"]["optimized"]["truth_v2"] *= 0.8
            tampered["suite"]["mean_completion"]["repair"] = 1.0
            tampered["suite"]["mean_truth_v2"]["optimized"] *= 0.8
            baseline_path.write_text(json.dumps(tampered), encoding="utf-8")
            proc = self._run("--check", *common)
            self.assertEqual(proc.returncode, 1, proc.stderr[-3000:])
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["status"], "FAIL")
            self.assertGreater(payload["comparison"]["hard_drifts"], 0)

    def test_cli_missing_cases(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = pathlib.Path(tmp) / "missing-cases"
            baseline_path = pathlib.Path(tmp) / "base.json"
            bench.save_baseline(
                bench.collect_baseline(_synthetic_report(tmp)), baseline_path
            )
            common = [
                "--cases-root",
                str(missing),
                "--baseline",
                str(baseline_path),
                "--md",
                str(pathlib.Path(tmp) / "md" / "REALBOARD.md"),
                "--steps",
                "0",
            ]
            proc = self._run("--check", *common)
            self.assertEqual(proc.returncode, 0, proc.stderr[-3000:])
            self.assertIn("SKIP", proc.stdout)
            proc = self._run("--update-baseline", *common)
            self.assertEqual(proc.returncode, 2)
            self.assertIn("no real boards measured", proc.stderr)


# --------------------------------------------------------------------------- #
# real-data smoke (read-only, optional)
# --------------------------------------------------------------------------- #
_CASES_ROOT_AVAILABLE = realboard.DEFAULT_CASES_ROOT.is_dir()


@unittest.skipUnless(_CASES_ROOT_AVAILABLE, "EasyCirq cases root is not available on this machine")
class RealDataSmokeTests(unittest.TestCase):
    def test_real_discovery_has_boards_for_baseline(self):
        boards, skipped = realboard.discover_cases()
        self.assertGreaterEqual(len(boards), 4)
        self.assertTrue(all(source.name for source in boards))
        # The frozen docs baseline (when present) must load and validate.
        if bench.DEFAULT_BASELINE_PATH.exists():
            baseline = bench.load_baseline(bench.DEFAULT_BASELINE_PATH)
            bench.validate_baseline(baseline)
            self.assertGreaterEqual(baseline["suite"]["n_boards"], 1)


if __name__ == "__main__":
    unittest.main()
