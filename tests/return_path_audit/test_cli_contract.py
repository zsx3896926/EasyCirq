"""CLI contract: exit codes, atomic writes, guards, stdout purity."""
from __future__ import annotations

import json
import pathlib
import tempfile
import unittest

try:  # package-mode discovery (unittest discover -s tests)
    from . import support
except ImportError:  # directory-mode discovery (-s tests/return_path_audit)
    import support

rect = support.rect
EXIT_CODES = support.tool_submodule("report").EXIT_CODES


def failing_document():
    """Solid plane split into GND/P3V3: a proven plane-split failure."""
    document = support.make_input()
    document["reference_copper"] = [
        {"id": "rc-gnd", "layer": "L2", "net": "GND", "availability": "actual_fill",
         "is_actual_fill": True, "connectivity_island": "g",
         "source_snapshot": support.SNAPSHOT,
         "polygons": [{"id": "g", "outer": rect(0, 0, 49.9, 80), "holes": []}]},
        {"id": "rc-pwr", "layer": "L2", "net": "P3V3", "availability": "actual_fill",
         "is_actual_fill": True, "connectivity_island": "p",
         "source_snapshot": support.SNAPSHOT,
         "polygons": [{"id": "p", "outer": rect(50.1, 0, 100, 80), "holes": []}]},
    ]
    return document


class CliContractTests(unittest.TestCase):
    def test_exit_codes_match_status(self):
        self.assertEqual(EXIT_CODES["pass_with_scope"], 0)
        self.assertEqual(EXIT_CODES["fail"], 1)
        self.assertEqual(EXIT_CODES["review_required"], 2)
        self.assertEqual(EXIT_CODES["incomplete"], 3)
        self.assertEqual(EXIT_CODES["input_invalid"], 4)

    def test_audit_stdout_is_one_json_document(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = support.write_input(tmp, support.make_input())
            code, stdout, stderr = support.run_cli(["audit", "-i", str(path)])
            self.assertEqual(code, 0, stderr)
            payload = json.loads(stdout)  # exactly one JSON document
            self.assertEqual(payload["schema"], "return-path-audit-report/v1")
            self.assertEqual(payload["overall_status"], "pass_with_scope")
            for key in ("tool", "tool_version", "input", "scope", "coverage",
                        "findings", "unknowns", "suggestions", "evidence_sources",
                        "run", "limits"):
                self.assertIn(key, payload)
            self.assertEqual(len(payload["input"]["input_sha256"]), 64)
            self.assertEqual(len(payload["input"]["semantic_sha256"]), 64)
            self.assertTrue(payload["run"]["simulated"])
            self.assertEqual(payload["run"]["real_eda"], "NOT RUN")

    def test_report_is_written_outside_input_and_input_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = support.write_input(tmp, support.make_input())
            before = path.read_bytes()
            report_path = pathlib.Path(tmp) / "out" / "report.json"
            code, _stdout, stderr = support.run_cli(
                ["audit", "-i", str(path), "-o", str(report_path)])
            self.assertEqual(code, 0, stderr)
            self.assertEqual(path.read_bytes(), before)
            self.assertTrue(report_path.is_file())

    def test_output_guard_refuses_to_overwrite_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = support.write_input(tmp, support.make_input())
            before = path.read_bytes()
            code, stdout, stderr = support.run_cli(
                ["audit", "-i", str(path), "-o", str(path)])
            self.assertEqual(code, 5, stderr)
            self.assertEqual(stdout, "")
            self.assertIn("refusing", stderr)
            self.assertEqual(path.read_bytes(), before)

    def test_atomic_write_leaves_no_temp_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = support.write_input(tmp, support.make_input())
            out_dir = pathlib.Path(tmp) / "reports"
            code, _stdout, stderr = support.run_cli(
                ["audit", "-i", str(path), "-o", str(out_dir / "report.json")])
            self.assertEqual(code, 0, stderr)
            leftovers = list(out_dir.glob("*.tmp")) + list(out_dir.glob(".*"))
            self.assertEqual(leftovers, [])
            json.loads((out_dir / "report.json").read_text(encoding="utf-8"))

    def test_failed_run_does_not_leave_old_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            good_path = support.write_input(tmp, support.make_input(), "good.json")
            out_path = pathlib.Path(tmp) / "report.json"
            code, _stdout, stderr = support.run_cli(
                ["audit", "-i", str(good_path), "-o", str(out_path)])
            self.assertEqual(code, 0, stderr)
            self.assertEqual(json.loads(out_path.read_text(encoding="utf-8"))
                             ["overall_status"], "pass_with_scope")
            broken = support.make_input()
            broken["signals"][0]["segments"][0]["width"] = -1
            broken_path = support.write_input(tmp, broken, "broken.json")
            code, _stdout, _stderr = support.run_cli(
                ["audit", "-i", str(broken_path), "-o", str(out_path)])
            self.assertEqual(code, 4)
            final = json.loads(out_path.read_text(encoding="utf-8"))
            self.assertEqual(final["overall_status"], "input_invalid")
            self.assertTrue(final["validation_issues"])

    def test_fail_verdict_exit_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = support.write_input(tmp, failing_document())
            code, stdout, stderr = support.run_cli(["audit", "-i", str(path)])
            self.assertEqual(code, 1, stderr)
            self.assertEqual(json.loads(stdout)["overall_status"], "fail")

    def test_explain_reads_report_and_returns_same_exit_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = support.write_input(tmp, failing_document())
            report_path = pathlib.Path(tmp) / "report.json"
            code, _stdout, stderr = support.run_cli(
                ["audit", "-i", str(path), "-o", str(report_path)])
            self.assertEqual(code, 1, stderr)
            code, stdout, _stderr = support.run_cli(
                ["explain", "--report", str(report_path)])
            self.assertEqual(code, 1)
            self.assertIn("FAIL", stdout)
            self.assertIn("NOT CLAIMED", stdout)

    def test_explain_from_input_runs_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = support.write_input(tmp, support.make_input())
            code, stdout, stderr = support.run_cli(["explain", "-i", str(path)])
            self.assertEqual(code, 0, stderr)
            self.assertIn("PASS_WITH_SCOPE", stdout)
            self.assertIn("checked=60", stdout)

    def test_svg_overlay_is_marked_as_analysis_not_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = support.write_input(tmp, support.make_input())
            svg_path = pathlib.Path(tmp) / "overlay.svg"
            code, _stdout, stderr = support.run_cli(
                ["audit", "-i", str(path), "--svg", str(svg_path)])
            self.assertEqual(code, 0, stderr)
            content = svg_path.read_text(encoding="utf-8")
            self.assertIn("synthetic_analysis / not_official_export", content)
            self.assertIn("ANALYSIS OVERLAY", content)
            self.assertIn("<svg", content)

    def test_constraints_file_changes_the_verdict(self):
        # Plane edge 0.15 mm from the centreline, trace half-width 0.1 mm:
        # safe with corridor=0, a corridor violation with corridor=0.2.
        document = support.make_input(
            copper=[{"id": "rc-gnd", "layer": "L2", "net": "GND",
                     "availability": "actual_fill", "is_actual_fill": True,
                     "connectivity_island": "g",
                     "source_snapshot": support.SNAPSHOT,
                     "polygons": [{"id": "g", "outer": rect(0, 0, 100, 25.15),
                                   "holes": []}]}],
            signals=[{"id": "sig", "net": "N", "segments": [
                {"id": "sig.1", "kind": "straight", "layer": "L1",
                 "start": [20, 25], "end": [80, 25], "width": 0.2}]}])
        with tempfile.TemporaryDirectory() as tmp:
            path = support.write_input(tmp, document)
            code, stdout, _stderr = support.run_cli(["audit", "-i", str(path)])
            self.assertEqual(code, 2)
            self.assertEqual(json.loads(stdout)["overall_status"],
                             "review_required")
            constraints_path = pathlib.Path(tmp) / "constraints.json"
            constraints_path.write_text(json.dumps({"corridor": 0.0}),
                                        encoding="utf-8")
            code, stdout, stderr = support.run_cli(
                ["audit", "-i", str(path), "-c", str(constraints_path)])
            self.assertEqual(code, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["overall_status"], "pass_with_scope")
            self.assertEqual(payload["scope"]["corridor"]["value"], 0.0)

    def test_missing_corridor_records_assumption(self):
        document = support.make_input()
        document["constraints"] = {"interface": "test"}
        with tempfile.TemporaryDirectory() as tmp:
            path = support.write_input(tmp, document)
            code, stdout, stderr = support.run_cli(["audit", "-i", str(path)])
            self.assertEqual(code, 0, stderr)
            payload = json.loads(stdout)
            self.assertIsNone(payload["scope"]["corridor"])

    def test_usage_error_exit_five(self):
        code, stdout, stderr = support.run_cli(["audit"])
        self.assertEqual(code, 5)
        self.assertEqual(stdout, "")
        self.assertIn("required", stderr)


if __name__ == "__main__":
    unittest.main()
