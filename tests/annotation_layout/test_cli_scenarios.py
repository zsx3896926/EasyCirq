import json
import shutil
import tempfile
import unittest
from pathlib import Path

try:
    from . import helpers
except ImportError:
    import helpers

REAL = helpers.REAL


class CliScenarios(unittest.TestCase):
    """At least 24 real ``python -m annotation_layout`` CLI scenarios.

    Every case below runs the actual module entry point in a subprocess; none of
    them calls an internal helper to fake the CLI.
    """

    maxDiff = None

    def test_01_version(self):
        code, payload, stderr, _ = helpers.run_cli(["version"])
        self.assertEqual(code, 0, stderr)
        self.assertEqual(payload["schema"], "annotation-layout/v1")
        self.assertEqual(payload["host_execution"], "not_executed")

    def test_02_validate_real_fixture(self):
        code, payload, stderr, _ = helpers.run_cli(["validate", str(REAL)])
        self.assertEqual(code, 0, stderr)
        self.assertEqual(payload["status"], "valid")
        self.assertEqual(payload["counts"], {"components": 19, "wires": 98,
                                             "fixed_texts": 94,
                                             "movable_annotations": 42})
        self.assertIn("schematic_raw", json.dumps(payload))

    def test_03_validate_synthetic_fixture(self):
        code, payload, stderr, _ = helpers.run_cli(
            ["validate", str(helpers.synthetic("text-text"))])
        self.assertEqual(code, 0, stderr)
        self.assertEqual(payload["status"], "valid")

    def test_04_to_09_invalid_inputs_exit_2_without_pass(self):
        cases = ["nan.json", "duplicate-id.json", "unknown-unit.json",
                 "bool-number.json", "bad-bbox.json", "unknown-key.json"]
        for name in cases:
            with self.subTest(case=name):
                code, payload, stderr, _ = helpers.run_cli(
                    ["validate", str(helpers.invalid(name))])
                self.assertEqual(code, 2)
                self.assertEqual(payload["status"], "input_invalid")
                self.assertTrue(payload["errors"])

    def test_10_plan_real_fixture_stdout_is_pure_json(self):
        code, payload, stderr, raw = helpers.run_cli(["plan", str(REAL)])
        self.assertEqual(code, 0, stderr)
        self.assertEqual(payload["status"], "planned_clear")
        self.assertEqual(payload["verification"]["status"], "plan_verified")
        self.assertEqual(payload["metrics"]["changes"], 2)
        self.assertEqual(payload["host_execution"], "not_executed")
        # stdout must be one JSON document, not log lines around it.
        json.loads(raw)

    def test_11_plan_writes_plan_report_and_analysis_svg(self):
        with tempfile.TemporaryDirectory() as temp:
            out_dir = Path(temp) / "out"
            code, payload, stderr, _ = helpers.run_cli(
                ["plan", str(REAL), "--out-dir", str(out_dir)])
            self.assertEqual(code, 0, stderr)
            for name in ("plan.json", "report.md", "before.svg", "after.svg"):
                path = out_dir / name
                self.assertTrue(path.is_file(), name)
                self.assertGreater(path.stat().st_size, 0)
            self.assertFalse(list(out_dir.glob("*.tmp")))
            plan = helpers.read_json(out_dir / "plan.json")
            self.assertEqual(plan["artifacts"]["svg_label"],
                             "analysis_not_official_export")
            report = (out_dir / "report.md").read_text(encoding="utf-8")
            self.assertIn("NOT RUN", report)
            self.assertIn("analysis_not_official_export", report)
            self.assertIn("status", report)

    def test_12_to_21_scenario_plans(self):
        expectations = {
            "text-text": ("planned_clear", 1),
            "text-symbol": ("planned_clear", 1),
            "text-wire": ("planned_clear", 1),
            "rotated": ("planned_clear", 1),
            "chinese-purpose": ("planned_clear", 1),
            "title-block": ("planned_clear", 1),
            "zone-boundary": ("planned_clear", 1),
            "dense": ("planned_clear", 3),
            "clean": ("planned_clear", 0),
            "lock-frozen": ("planned_clear", 1),
        }
        for name, (status, changes) in expectations.items():
            with self.subTest(case=name):
                code, payload, stderr, _ = helpers.run_cli(
                    ["plan", str(helpers.synthetic(name))])
                self.assertEqual(code, 0, stderr)
                self.assertEqual(payload["status"], status)
                self.assertEqual(payload["metrics"]["changes"], changes)
                self.assertEqual(payload["noop"], changes == 0)
                if changes:
                    self.assertEqual(payload["verification"]["status"], "plan_verified")
                    self.assertEqual(payload["metrics"]["after_hard"], 0)

    def test_22_rotated_annotation_keeps_rotation_and_font(self):
        code, payload, stderr, _ = helpers.run_cli(
            ["plan", str(helpers.synthetic("rotated"))])
        self.assertEqual(code, 0, stderr)
        change = payload["changes"][0]
        self.assertEqual(change["before"]["rotation_deg"], 90.0)
        self.assertEqual(change["after"]["rotation_deg"], 90.0)
        self.assertEqual(change["protected"]["rotation_deg"], "unchanged")
        self.assertEqual(change["protected"]["font_size"], "unchanged")

    def test_23_no_candidates_is_blocked_with_reason(self):
        code, payload, stderr, _ = helpers.run_cli(
            ["plan", str(helpers.synthetic("no-candidates"))])
        self.assertEqual(code, 1)
        self.assertEqual(payload["status"], "blocked")
        self.assertEqual(payload["metrics"]["changes"], 0)
        reason = payload["status_detail"]["solver_reasons"]["A1"]["reason"]
        self.assertEqual(reason, "all_candidates_rejected")

    def test_24_budget_exhaustion_is_reported(self):
        code, payload, stderr, _ = helpers.run_cli(
            ["plan", str(helpers.synthetic("budget-exhausted"))])
        self.assertEqual(code, 1)
        self.assertEqual(payload["status"], "partial")
        self.assertTrue(payload["search"]["budget_exhausted"])
        self.assertEqual(payload["search"]["budget_kind"], "max_search_states")
        self.assertNotEqual(payload["verification"]["status"], "plan_verified")

    def test_25_estimated_geometry_needs_visual_review(self):
        code, payload, stderr, _ = helpers.run_cli(
            ["plan", str(helpers.synthetic("estimated"))])
        self.assertEqual(code, 1)
        self.assertEqual(payload["verification"]["status"],
                         "candidate_needs_visual_review")
        self.assertIn("A1", payload["verification"]["checks"]["estimated_moved"])

    def test_26_net_label_anchor_unsupported(self):
        code, payload, stderr, _ = helpers.run_cli(
            ["plan", str(helpers.synthetic("net-anchor"))])
        self.assertEqual(code, 1)
        self.assertEqual(payload["status"], "blocked")
        self.assertEqual(payload["scope"]["unsupported"], ["A1"])
        self.assertEqual(payload["metrics"]["changes"], 0)
        self.assertTrue(payload["status_detail"]["remaining_hard"])

    def test_27_cluster_scope_cli_freezes_other_cluster(self):
        code, payload, stderr, _ = helpers.run_cli(
            ["plan", str(helpers.synthetic("cluster-a")),
             "--scope-cluster", "A1", "--scope-cluster", "A2"])
        self.assertEqual(code, 1)
        self.assertEqual(payload["status"], "partial")
        moved = {change["id"] for change in payload["changes"]}
        self.assertTrue(moved <= {"A1", "A2"})
        self.assertTrue(any("A3" in item["annotation_ids"]
                            for item in payload["status_detail"]["remaining_hard"]))

    def test_28_freeze_cli_never_moves_frozen_id(self):
        code, payload, stderr, _ = helpers.run_cli(
            ["plan", str(helpers.synthetic("text-text")), "--freeze", "A2"])
        self.assertEqual(code, 0, stderr)
        moved = {change["id"] for change in payload["changes"]}
        self.assertNotIn("A2", moved)
        self.assertIn("A1", moved)
        self.assertEqual(payload["scope"]["frozen_ids"], ["A2"])

    def test_29_verify_accepts_a_good_plan(self):
        with tempfile.TemporaryDirectory() as temp:
            plan_path = Path(temp) / "plan.json"
            code, payload, stderr, _ = helpers.run_cli(
                ["plan", str(REAL), "--out", str(plan_path)])
            self.assertEqual(code, 0, stderr)
            code, verified, stderr, _ = helpers.run_cli(
                ["verify", str(REAL), "--plan", str(plan_path)])
            self.assertEqual(code, 0, stderr)
            self.assertEqual(verified["status"], "plan_verified")
            self.assertEqual(verified["verification"]["checker"]["status"], "ran")

    def test_30_verify_rejects_broken_and_stale_plans(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            broken = directory / "broken.json"
            broken.write_text("{not json", encoding="utf-8")
            code, payload, stderr, _ = helpers.run_cli(
                ["verify", str(REAL), "--plan", str(broken)])
            self.assertEqual(code, 2)
            plan_path = directory / "plan.json"
            helpers.run_cli(["plan", str(REAL), "--out", str(plan_path)])
            plan = helpers.read_json(plan_path)
            plan["input"]["canonical_sha256"] = "0" * 64
            helpers.write_json(plan_path, plan)
            code, payload, stderr, _ = helpers.run_cli(
                ["verify", str(REAL), "--plan", str(plan_path)])
            self.assertEqual(code, 2)
            self.assertEqual(payload["status"], "input_invalid")

    def test_31_plan_is_deterministic_at_cli_level(self):
        first = helpers.run_cli(["plan", str(helpers.synthetic("dense"))])
        second = helpers.run_cli(["plan", str(helpers.synthetic("dense"))])
        self.assertEqual(first[0], 0)
        self.assertEqual(first[3], second[3])
        self.assertEqual(first[1]["status"], second[1]["status"])

    def test_32_plan_rejects_output_equal_to_input(self):
        code, payload, stderr, _ = helpers.run_cli(
            ["plan", str(helpers.synthetic("text-text")),
             "--out", str(helpers.synthetic("text-text"))])
        self.assertEqual(code, 2)
        self.assertIn("refusing", stderr.lower() + (payload or {}).get("status", ""))

    def test_33_invalid_input_does_not_leave_old_pass_output(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "plan.json"
            helpers.run_cli(["plan", str(helpers.synthetic("text-text")),
                             "--out", str(out)])
            self.assertEqual(helpers.read_json(out)["status"], "planned_clear")
            code, payload, stderr, _ = helpers.run_cli(
                ["plan", str(helpers.invalid("nan.json")), "--out", str(out)])
            self.assertEqual(code, 2)
            self.assertEqual(helpers.read_json(out)["status"], "input_invalid")

    def test_34_benchmark_cli_runs_small_suite(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            suite = directory / "cases"
            suite.mkdir()
            for name in ("text-text", "dense"):
                shutil.copyfile(helpers.synthetic(name), suite / f"{name}.json")
            out = directory / "bench"
            code, payload, stderr, _ = helpers.run_cli(
                ["benchmark", "--suite", str(suite), "--repeat", "1",
                 "--no-cli-timing", "--out", str(out)])
            self.assertEqual(code, 0, stderr)
            self.assertEqual(payload["suite"]["cases"], 2)
            self.assertIn("NOT RUN", json.dumps(payload["not_run"]))
            self.assertTrue((out / "result.json").is_file())
            self.assertTrue((out / "benchmark-report.md").is_file())

    def test_35_convert_writes_a_valid_v1_document(self):
        with tempfile.TemporaryDirectory() as temp:
            source = REAL.parent
            out = Path(temp) / "converted.json"
            code, payload, stderr, _ = helpers.run_cli([
                "convert",
                "--layout", str(source / "layout.json"),
                "--list", str(source / "list.json"),
                "--rendered", str(source / "rendered-text.json"),
                "--sheet", str(source / "sheet.json"),
                "--out", str(out),
                "--copy-sources",
            ])
            self.assertEqual(code, 0, stderr)
            self.assertEqual(payload["counts"], {"components": 19, "wires": 98,
                                                 "fixed_texts": 94,
                                                 "movable_annotations": 42})
            validated = helpers.run_cli(["validate", str(out)])
            self.assertEqual(validated[0], 0)
            for name in ("layout.json", "list.json", "rendered-text.json",
                         "sheet.json"):
                self.assertTrue((Path(temp) / name).is_file())

    def test_36_usage_error_exit_2(self):
        code, payload, stderr, _ = helpers.run_cli(["plan"])
        self.assertEqual(code, 2)
        self.assertIn("usage", stderr.lower())


if __name__ == "__main__":
    unittest.main()
