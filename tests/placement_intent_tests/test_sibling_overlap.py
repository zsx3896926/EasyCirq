"""Sibling bbox overlap: review_required (exit 1), never 0 and never 2."""
import unittest

from . import fixtures, support


class ComponentOverlapTests(support.CliTestCase):
    def plan(self, document=None):
        path = self.write_input("overlap.json",
                                document or fixtures.overlap_case())
        result = self.run_on("plan", path)
        return result, path

    def test_overlap_is_review_required_at_exit_one(self):
        result, _path = self.plan()
        self.assertEqual(result.returncode, 1,
                         msg="sibling overlap must exit 1 (review_required), "
                             "not 0 and not 2\n" + result.context())
        self.assertNotEqual(result.returncode, 0, msg=result.context())
        self.assertNotEqual(result.returncode, 2, msg=result.context())
        payload = self.assert_status(result, "review_required")
        self.assertIn("sibling_overlap", support.finding_codes(payload),
                      msg="codes=%r\n%s" % (
                          support.finding_codes(payload), result.context()))

    def test_overlap_finding_details(self):
        result, _path = self.plan()
        payload = self.payload(result)
        findings = [item for item in payload.get("findings") or []
                    if item.get("code") == "sibling_overlap"]
        self.assertTrue(findings, msg=result.context())
        details = findings[0].get("details") or {}
        self.assertEqual({details.get("a"), details.get("b")},
                         {"cmp:A", "cmp:B"},
                         msg="details=%r\n%s" % (details, result.context()))
        self.assertEqual(findings[0].get("severity"), "review")
        self.assertEqual(findings[0].get("status"), "review_required")

    def test_overlapping_input_is_still_legal_for_validate(self):
        _result, path = self.plan()
        validate = self.run_on("validate", path)
        self.assert_exit_status(validate, 0, "valid")

    def test_touching_boxes_do_not_overlap(self):
        result, _path = self.plan(fixtures.no_overlap_case())
        self.assert_exit_status(result, 0, "planned_with_scope")
        payload = self.payload(result)
        self.assertNotIn("sibling_overlap", support.finding_codes(payload))

    def test_disjoint_boxes_with_room_are_planned(self):
        doc = fixtures.overlap_case()
        doc["modules"][1]["size_mm"] = {"w": 20.0, "h": 10.0}
        doc["modules"][0]["size_mm"] = {"w": 30.0, "h": 20.0}
        doc["constraints"][2]["dx_mm"] = 9.0
        doc["constraints"][2]["dy_mm"] = 1.0
        result, _path = self.plan(doc)
        self.assert_exit_status(result, 0, "planned_with_scope")

    def test_overlap_is_recorded_in_counts(self):
        result, _path = self.plan()
        payload = self.payload(result)
        self.assertGreaterEqual(payload.get("counts", {}).get("reviews", 0), 1,
                                msg=result.context())


class ModuleSiblingOverlapTests(support.CliTestCase):
    def test_module_bbox_overlap_is_review_required(self):
        path = self.write_input("module-overlap.json",
                                fixtures.module_overlap_case())
        result = self.run_on("plan", path)
        self.assert_exit_status(result, 1, "review_required")
        payload = self.payload(result)
        self.assertIn("sibling_overlap", support.finding_codes(payload))
        findings = [item for item in payload.get("findings") or []
                    if item.get("code") == "sibling_overlap"]
        details = findings[0].get("details") or {}
        self.assertEqual({details.get("a"), details.get("b")},
                         {"mod:m1", "mod:m2"})

    def test_touching_module_bboxes_are_planned(self):
        doc = fixtures.module_overlap_case()
        doc["constraints"][1]["dx_mm"] = 8.0
        doc["constraints"][1]["dy_mm"] = 8.0
        path = self.write_input("module-touch.json", doc)
        result = self.run_on("plan", path)
        self.assert_exit_status(result, 0, "planned_with_scope")
        self.assertNotIn("sibling_overlap",
                         support.finding_codes(self.payload(result)))

    def test_module_overlap_keeps_scope_flags(self):
        path = self.write_input("module-overlap.json",
                                fixtures.module_overlap_case())
        payload = self.payload(self.run_on("plan", path))
        self.assertIs(payload.get("placement_applied"), False)
        self.assertEqual(payload.get("real_eda"), "NOT RUN")
        self.assertEqual(payload.get("eda_calls"), 0)


if __name__ == "__main__":
    unittest.main()
