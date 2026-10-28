import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

try:
    from . import helpers
except ImportError:
    import helpers

from annotation_layout.planner import build_plan, planned_bboxes_from_changes
from annotation_layout.schema import load_input
from annotation_layout.svg_analysis import validate_svg, write_analysis_svg
from annotation_layout.verify import independent_violations, verify_plan


class VerifyTest(unittest.TestCase):
    def test_real_plan_is_verified_by_independent_path_and_checker(self):
        inp = load_input(helpers.REAL)
        plan = build_plan(inp)
        verification = plan["verification"]
        self.assertEqual(verification["status"], "plan_verified")
        self.assertEqual(verification["checker"]["status"], "ran")
        self.assertEqual(verification["checker"]["brief_before"]["blocking"], 3)
        self.assertEqual(verification["checker"]["brief_after"]["blocking"], 0)
        self.assertEqual(verification["independent"]["hard_before"], 3)
        self.assertEqual(verification["independent"]["hard_after"], 0)
        self.assertEqual(verification["independent"]["remaining_movable"], [])
        self.assertEqual(verification["independent"]["introduced_movable"], [])
        self.assertGreaterEqual(len(verification["checker"]["resolved"]), 3)
        self.assertIn("electrical", verification["electrical_assertion"])
        self.assertEqual(verification["host_execution"], "not_executed")

    def test_independent_check_agrees_with_conflict_module_codes(self):
        inp = load_input(helpers.REAL)
        independent = independent_violations(inp, {ann.id: ann.current.bbox
                                                   for ann in inp.annotations})
        from annotation_layout.conflicts import evaluate_assignment
        shared = evaluate_assignment(inp, {})
        expected = {(item.code, tuple(sorted(item.objects)))
                    for item in shared if item.is_hard}
        found = {(item["code"], tuple(sorted(item["objects"])))
                 for item in independent if item["severity"] == "hard"}
        self.assertEqual(expected, found)

    def test_introduced_conflict_rejects_plan(self):
        inp = load_input(helpers.synthetic("clean"))
        plan = build_plan(inp)
        self.assertEqual(plan["verification"]["status"], "plan_verified")
        planned = planned_bboxes_from_changes(inp, plan["changes"])
        from annotation_layout.model import Rect
        # Deliberately move a clear value text onto the designator text.
        planned["A1"] = Rect(100, 645, 125, 655)
        verification = verify_plan(inp, planned)
        self.assertEqual(verification["status"], "plan_rejected")
        self.assertTrue(verification["independent"]["introduced_movable"])
        self.assertTrue(verification["checker"]["introduced_movable"])

    def test_checker_unavailable_is_recorded_not_faked(self):
        inp = load_input(helpers.synthetic("text-text"))
        plan = build_plan(inp)
        planned = planned_bboxes_from_changes(inp, plan["changes"])
        with mock.patch("annotation_layout.verify._import_checker",
                        return_value=(None, "checker disabled for test")):
            verification = verify_plan(inp, planned)
        self.assertEqual(verification["checker"]["status"], "unavailable")
        self.assertIn("checker disabled for test", verification["checker"]["limitations"][0])
        self.assertEqual(verification["status"], "plan_verified")
        self.assertFalse(verification["checks"]["checker_available"])

    def test_stale_plan_binding_is_rejected_by_cli(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            plan_path = directory / "plan.json"
            code, payload, stderr, _ = helpers.run_cli(
                ["plan", str(helpers.synthetic("text-text")), "--out", str(plan_path)])
            self.assertEqual(code, 0, stderr)
            plan = helpers.read_json(plan_path)
            plan["input"]["canonical_sha256"] = "f" * 64
            helpers.write_json(plan_path, plan)
            code, payload, stderr, _ = helpers.run_cli(
                ["verify", str(helpers.synthetic("text-text")), "--plan", str(plan_path)])
            self.assertEqual(code, 2)
            self.assertEqual(payload["status"], "input_invalid")
            self.assertTrue(any("stale" in error for error in payload["errors"]))

    def test_verification_keeps_before_and_after_findings(self):
        inp = load_input(helpers.REAL)
        plan = build_plan(inp)
        checker = plan["verification"]["checker"]
        self.assertIsNotNone(checker["before"])
        self.assertIsNotNone(checker["after"])
        self.assertIn("blocking_findings", checker["before"])
        self.assertIn("blocking_findings", checker["after"])
        self.assertTrue(checker["before"]["blocking_findings"])
        self.assertEqual(checker["after"]["blocking_findings"], [])

    def test_verify_invalid_on_non_rigid_plan(self):
        inp = load_input(helpers.synthetic("text-text"))
        from annotation_layout.model import Rect
        planned = {ann.id: ann.current.bbox for ann in inp.annotations}
        planned["A1"] = Rect(100, 692, 160, 702)  # width changed
        verification = verify_plan(inp, planned)
        self.assertEqual(verification["status"], "verify_invalid")
        self.assertTrue(any("rigid translation" in item
                            for item in verification["errors"]))


class SvgTest(unittest.TestCase):
    def test_analysis_svg_is_well_formed_and_flips_y_once(self):
        inp = load_input(helpers.synthetic("text-text"))
        planned = {ann.id: ann.current.bbox for ann in inp.annotations}
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "overlay.svg"
            outcome = write_analysis_svg(inp, planned, path, "unit test")
            self.assertEqual(outcome["label"], "analysis_not_official_export")
            self.assertEqual(outcome["validation"]["status"], "ok")
            text = path.read_text(encoding="utf-8")
            self.assertIn("analysis_not_official_export", text)
            self.assertIn("NOT an official EDA export", text)
            self.assertIn('viewBox="0 0 1170 825"', text)
            # A1 raw top y=702 belongs to the 1170x825 synthetic page; the
            # analysis overlay flips exactly once: screen_y = 825 - 702 = 123.
            self.assertIn('data-annotation="A1"', text)
            self.assertIn('y="123"', text)

    def test_svg_is_deterministic(self):
        inp = load_input(helpers.synthetic("text-text"))
        planned = {ann.id: ann.current.bbox for ann in inp.annotations}
        with tempfile.TemporaryDirectory() as temp:
            first = Path(temp) / "a.svg"
            second = Path(temp) / "b.svg"
            write_analysis_svg(inp, planned, first, "same")
            write_analysis_svg(inp, planned, second, "same")
            self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_validate_svg_catches_broken_file(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "broken.svg"
            path.write_text("<svg><rect/></svg>", encoding="utf-8")
            outcome = validate_svg(path)
            self.assertEqual(outcome["status"], "invalid")
            self.assertTrue("viewBox" in outcome["reason"] or
                            "width/height" in outcome["reason"])

    def test_validation_mentions_preview_not_run(self):
        inp = load_input(helpers.synthetic("text-text"))
        planned = {ann.id: ann.current.bbox for ann in inp.annotations}
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "overlay.svg"
            outcome = write_analysis_svg(inp, planned, path, "preview")
            self.assertIn("NOT RUN", outcome["validation"]["render_basic_check"])


if __name__ == "__main__":
    unittest.main()
