"""Contradictory constraints: duplicate pairs, multi-path mismatch, cycles.

Contract.md section 4.4: duplicates with different values and inconsistent
paths are ``invalid_input``; a cycle is only legal when its composition is the
identity within tolerance (info finding, not an error).
"""
import unittest

from . import fixtures, support


class DuplicatePairTests(support.CliTestCase):
    def test_same_pair_different_offset_is_invalid(self):
        path = self.write_input("dup-offset.json",
                                fixtures.duplicate_constraint_values_case())
        result = self.run_on("validate", path)
        self.assert_invalid(result, "constraint_duplicate_conflict")

    def test_same_pair_different_rotation_is_invalid(self):
        doc = fixtures.small_case()
        doc["constraints"].append({
            "id": "ccg:9", "from": "mod:root", "to": "mod:leaf",
            "dx_mm": 0.0, "dy_mm": 0.0, "rotation_deg": 90, "weight": 1.0,
        })
        path = self.write_input("dup-rotation.json", doc)
        result = self.run_on("validate", path)
        self.assert_invalid(result, "constraint_duplicate_conflict")

    def test_same_pair_different_weight_is_invalid(self):
        doc = fixtures.small_case()
        doc["constraints"].append({
            "id": "ccg:9", "from": "mod:root", "to": "mod:leaf",
            "dx_mm": 0.0, "dy_mm": 0.0, "rotation_deg": 0, "weight": 0.4,
        })
        path = self.write_input("dup-weight.json", doc)
        result = self.run_on("validate", path)
        self.assert_invalid(result, "constraint_duplicate_conflict")

    def test_identical_duplicate_is_deduplicated(self):
        path = self.write_input("dup-identical.json",
                                fixtures.identical_duplicate_constraint_case())
        validate = self.run_on("validate", path)
        self.assert_exit_status(validate, 0, "valid")
        payload = self.payload(validate)
        self.assertEqual(payload.get("counts", {}).get("constraints_input"), 3)
        self.assertEqual(
            payload.get("counts", {}).get("constraints_normalized"), 2)
        self.assertIn("constraint_duplicate_deduped",
                      support.finding_codes(payload))
        plan = self.run_on("plan", path)
        self.assert_exit_status(plan, 0, "planned_with_scope")
        plan_payload = self.payload(plan)
        self.assertEqual(len(plan_payload.get("normalized_constraints") or []),
                         2)
        by_id = {item.get("id"): item
                 for item in plan_payload.get("normalized_constraints") or []}
        self.assertEqual(by_id["ccg:1"].get("aliases"), ["ccg:9"])


class MultiPathTests(support.CliTestCase):
    def test_inconsistent_paths_are_invalid(self):
        path = self.write_input("path-mismatch.json",
                                fixtures.multi_path_mismatch_case())
        result = self.run_on("validate", path)
        self.assert_invalid(result, "constraint_path_mismatch")

    def test_consistent_redundant_path_is_accepted(self):
        path = self.write_input("path-consistent.json",
                                fixtures.identity_cycle_case())
        result = self.run_on("validate", path)
        self.assert_exit_status(result, 0, "valid")
        # The plan must keep the redundant edge as a normalized constraint.
        plan = self.run_on("plan", path)
        self.assert_exit_status(plan, 0, "planned_with_scope")
        payload = self.payload(plan)
        ids = support.constraint_ids(payload)
        self.assertIn("ccg:9", ids)


class CycleTests(support.CliTestCase):
    def test_non_identity_cycle_is_invalid(self):
        path = self.write_input("cycle-bad.json",
                                fixtures.non_identity_cycle_case())
        result = self.run_on("validate", path)
        self.assert_invalid(result, "constraint_cycle_nonidentity")

    def test_identity_cycle_is_allowed_as_info(self):
        path = self.write_input("cycle-ok.json",
                                fixtures.identity_cycle_case())
        result = self.run_on("validate", path)
        self.assert_exit_status(result, 0, "valid")
        payload = self.payload(result)
        self.assertIn("constraint_cycle_identity",
                      support.finding_codes(payload),
                      msg="identity cycle should be recorded as info\n"
                          + result.context())
        info = [item for item in payload.get("findings") or []
                if item.get("code") == "constraint_cycle_identity"]
        self.assertTrue(info)
        self.assertEqual(info[0].get("severity"), "info")

    def test_identity_rotation_cycle_is_allowed(self):
        path = self.write_input("rotation-cycle.json",
                                fixtures.identity_rotation_cycle_case())
        validate = self.run_on("validate", path)
        self.assert_exit_status(validate, 0, "valid")
        plan = self.run_on("plan", path)
        self.assert_exit_status(plan, 0, "planned_with_scope")
        payload = self.payload(plan)
        self.assertIn("constraint_cycle_identity",
                      support.finding_codes(payload))

    def test_rotation_mismatch_across_paths_is_invalid(self):
        doc = fixtures.identity_rotation_cycle_case()
        doc["constraints"][2]["rotation_deg"] = 180
        path = self.write_input("rotation-cycle-bad.json", doc)
        result = self.run_on("validate", path)
        self.assert_invalid(result, "constraint_path_mismatch")

    def test_identity_cycle_with_offset_is_multi_path_consistent(self):
        """A cycle whose translation cancels exactly must not be flagged."""
        doc = fixtures.small_case()
        # root -> leaf (0,0); add leaf -> root (0,0): translation sum zero.
        doc["constraints"].append({
            "id": "ccg:3", "from": "mod:leaf", "to": "mod:root",
            "dx_mm": 0.0, "dy_mm": 0.0, "rotation_deg": 0, "weight": 1.0,
        })
        path = self.write_input("cycle-offset.json", doc)
        validate = self.run_on("validate", path)
        self.assert_exit_status(validate, 0, "valid")
        self.assertIn("constraint_cycle_identity",
                      support.finding_codes(self.payload(validate)))


class EdgeValidityTests(support.CliTestCase):
    def test_self_loop_is_invalid(self):
        doc = fixtures.small_case()
        doc["constraints"][0]["to"] = doc["constraints"][0]["from"]
        path = self.write_input("self-loop.json", doc)
        result = self.run_on("validate", path)
        self.assert_invalid(result, "constraint_self_loop")

    def test_unknown_from_endpoint(self):
        doc = fixtures.small_case()
        doc["constraints"][0]["from"] = "mod:ghost"
        path = self.write_input("unknown-from.json", doc)
        result = self.run_on("validate", path)
        self.assert_invalid(result, "constraint_endpoint_unknown")

    def test_unknown_to_endpoint(self):
        doc = fixtures.small_case()
        doc["constraints"][0]["to"] = "mod:ghost"
        path = self.write_input("unknown-to.json", doc)
        result = self.run_on("validate", path)
        self.assert_invalid(result, "constraint_endpoint_unknown")

    def test_unknown_component_endpoint(self):
        doc = fixtures.small_case()
        doc["constraints"][1]["to"] = "cmp:ghost"
        path = self.write_input("unknown-component.json", doc)
        result = self.run_on("validate", path)
        self.assert_invalid(result, "constraint_endpoint_unknown")

    def test_zero_weight_is_out_of_range(self):
        doc = fixtures.small_case()
        doc["constraints"][0]["weight"] = 0.0
        path = self.write_input("zero-weight.json", doc)
        result = self.run_on("validate", path)
        self.assert_invalid(result, "number_out_of_range")

    def test_weight_nan_literal_is_rejected(self):
        text = fixtures.json_text(fixtures.small_case()).replace(
            '"weight": 1.0', '"weight": NaN', 1)
        path = self.write_raw_input("weight-nan.json", text)
        result = self.run_on("validate", path)
        self.assert_invalid(result, "json_invalid")


if __name__ == "__main__":
    unittest.main()
