"""Fixed-node conflicts and review_required state (contract.md 4.5, 7.1)."""
import unittest

from . import fixtures, support


class FixedRotationConflictTests(support.CliTestCase):
    def test_validate_accepts_fixed_conflict_as_legal_input(self):
        path = self.write_input("fixed-rotation.json",
                                fixtures.fixed_rotation_conflict_case())
        result = self.run_on("validate", path)
        self.assert_exit_status(result, 0, "valid")

    def test_plan_reports_review_required(self):
        path = self.write_input("fixed-rotation.json",
                                fixtures.fixed_rotation_conflict_case())
        result = self.run_on("plan", path)
        self.assert_exit_status(result, 1, "review_required")
        self.assertNotEqual(result.returncode, 2,
                            msg="fixed conflicts are review, not invalid\n"
                                + result.context())

    def test_finding_code_and_severity(self):
        path = self.write_input("fixed-rotation.json",
                                fixtures.fixed_rotation_conflict_case())
        result = self.run_on("plan", path)
        payload = self.assert_has_finding(result, "fixed_conflict",
                                          severity="review")
        item = [entry for entry in payload.get("findings") or []
                if entry.get("code") == "fixed_conflict"][0]
        self.assertEqual(item.get("status"), "review_required")
        self.assertEqual(item.get("subject"), "cmp:A")

    def test_plan_still_emits_relative_levels(self):
        path = self.write_input("fixed-rotation.json",
                                fixtures.fixed_rotation_conflict_case())
        payload = self.payload(self.run_on("plan", path))
        self.assertTrue(payload.get("levels"))
        self.assertGreaterEqual(payload.get("counts", {}).get("reviews", 0), 1)


class FixedDistanceConflictTests(support.CliTestCase):
    def test_distance_conflict_is_review_required(self):
        path = self.write_input("fixed-distance.json",
                                fixtures.fixed_distance_conflict_case())
        validate = self.run_on("validate", path)
        self.assert_exit_status(validate, 0, "valid")
        result = self.run_on("plan", path)
        self.assert_exit_status(result, 1, "review_required")
        self.assert_has_finding(result, "fixed_conflict", severity="review")

    def test_declared_distance_mismatch_is_reported(self):
        path = self.write_input("fixed-distance.json",
                                fixtures.fixed_distance_conflict_case())
        payload = self.payload(self.run_on("plan", path))
        subjects = {item.get("subject")
                    for item in payload.get("findings") or []
                    if item.get("code") == "fixed_conflict"}
        self.assertTrue(subjects & {"cmp:A", "cmp:B"},
                        msg="fixed_conflict should name a fixed node; got %r"
                            % (subjects,))


class FixedPositionUnknownTests(support.CliTestCase):
    def test_missing_position_is_only_a_warning(self):
        path = self.write_input("fixed-unknown.json",
                                fixtures.fixed_position_unknown_case())
        result = self.run_on("plan", path)
        # A warning does not change the plan status.
        self.assert_exit_status(result, 0, "planned_with_scope")
        payload = self.payload(result)
        self.assertIn("fixed_position_unknown",
                      support.finding_codes(payload))
        warnings = [item for item in payload.get("findings") or []
                    if item.get("code") == "fixed_position_unknown"]
        self.assertEqual(warnings[0].get("severity"), "warning")

    def test_validate_stays_valid(self):
        path = self.write_input("fixed-unknown.json",
                                fixtures.fixed_position_unknown_case())
        self.assert_exit_status(self.run_on("validate", path), 0, "valid")


class ModuleSizeExceededTests(support.CliTestCase):
    def test_exceeded_declared_size_is_review_required(self):
        path = self.write_input("size-exceeded.json",
                                fixtures.module_size_exceeded_case())
        validate = self.run_on("validate", path)
        self.assert_exit_status(validate, 0, "valid")
        result = self.run_on("plan", path)
        self.assert_exit_status(result, 1, "review_required")
        self.assert_has_finding(result, "module_size_exceeded",
                                severity="review")


class ReviewScopeFlagsTests(support.CliTestCase):
    def test_review_required_keeps_not_run_flags(self):
        path = self.write_input("fixed-rotation.json",
                                fixtures.fixed_rotation_conflict_case())
        payload = self.payload(self.run_on("plan", path))
        self.assertIs(payload.get("placement_applied"), False)
        self.assertIs(payload.get("routing_verified"), False)
        self.assertEqual(payload.get("physical_validation"), "NOT RUN")
        self.assertEqual(payload.get("real_eda"), "NOT RUN")
        self.assertEqual(payload.get("eda_calls"), 0)

    def test_review_required_never_becomes_planned_with_scope(self):
        path = self.write_input("fixed-rotation.json",
                                fixtures.fixed_rotation_conflict_case())
        payload = self.payload(self.run_on("plan", path))
        self.assertNotEqual(payload.get("status"), "planned_with_scope")
        self.assertEqual(payload.get("exit_code"), 1)


if __name__ == "__main__":
    unittest.main()
