"""Invalid input: required fields, types, enums, numbers, ids, extras.

Every case was designed directly from contract.md section 2/3 and is rejected
by ``validate`` with exit 2 and ``status=invalid_input``.
"""
import copy
import unittest

from . import fixtures, support


def mutated(change):
    doc = fixtures.small_case()
    change(doc)
    return doc


class MissingRequiredTests(support.CliTestCase):
    def test_missing_schema(self):
        doc = mutated(lambda doc: doc.pop("schema"))
        self.check_invalid(doc, "missing_required")

    def test_missing_units(self):
        doc = mutated(lambda doc: doc.pop("units"))
        self.check_invalid(doc, "missing_required")

    def test_missing_modules(self):
        doc = mutated(lambda doc: doc.pop("modules"))
        self.check_invalid(doc, "missing_required")

    def test_missing_components(self):
        doc = mutated(lambda doc: doc.pop("components"))
        self.check_invalid(doc, "missing_required")

    def test_missing_constraints(self):
        doc = mutated(lambda doc: doc.pop("constraints"))
        self.check_invalid(doc, "missing_required")

    def test_missing_provenance(self):
        doc = mutated(lambda doc: doc.pop("provenance"))
        self.check_invalid(doc, "missing_required")

    def test_missing_snapshot(self):
        doc = mutated(lambda doc: doc.pop("snapshot"))
        self.check_invalid(doc, "missing_required")

    def test_missing_constraint_dx(self):
        doc = mutated(lambda doc: doc["constraints"][0].pop("dx_mm"))
        self.check_invalid(doc, "missing_required")

    def test_missing_module_parent(self):
        doc = mutated(lambda doc: doc["modules"][0].pop("parent"))
        self.check_invalid(doc, "missing_required")


class TypeMismatchTests(support.CliTestCase):
    def test_modules_is_object(self):
        doc = mutated(lambda doc: doc.__setitem__("modules", {}))
        self.check_invalid(doc, "type_mismatch")

    def test_components_is_string(self):
        doc = mutated(lambda doc: doc.__setitem__("components", "cmp:A"))
        self.check_invalid(doc, "type_mismatch")

    def test_constraints_is_object(self):
        doc = mutated(lambda doc: doc.__setitem__("constraints", {}))
        self.check_invalid(doc, "type_mismatch")

    def test_module_children_is_string(self):
        doc = mutated(lambda doc: doc["modules"][0].__setitem__("children",
                                                               "mod:leaf"))
        self.check_invalid(doc, "type_mismatch")

    def test_confidence_is_string(self):
        doc = mutated(lambda doc: doc["modules"][1].__setitem__("confidence",
                                                               "0.9"))
        self.check_invalid(doc, "number_invalid")

    def test_fixed_is_string(self):
        doc = mutated(lambda doc: doc["components"][0].__setitem__("fixed",
                                                                  "yes"))
        self.check_invalid(doc, "type_mismatch")

    def test_snapshot_is_array(self):
        doc = mutated(lambda doc: doc.__setitem__("snapshot", []))
        self.check_invalid(doc, "type_mismatch")


class EnumTests(support.CliTestCase):
    def test_units_length_inch(self):
        doc = mutated(lambda doc: doc["units"].__setitem__("length", "inch"))
        self.check_invalid(doc, "enum_invalid")

    def test_source_type_unknown(self):
        doc = mutated(
            lambda doc: doc["snapshot"].__setitem__("source_type", "camera"))
        self.check_invalid(doc, "enum_invalid")

    def test_provenance_kind_unknown(self):
        doc = mutated(
            lambda doc: doc["provenance"].__setitem__("kind", "measured"))
        self.check_invalid(doc, "enum_invalid")

    def test_units_length_upper_case_rejected(self):
        doc = mutated(lambda doc: doc["units"].__setitem__("length", "MM"))
        self.check_invalid(doc, "enum_invalid")

    def test_source_kind_unknown(self):
        doc = mutated(
            lambda doc: doc["modules"][0].__setitem__("source",
                                                      {"kind": "guess"}))
        self.check_invalid(doc, "enum_invalid")


class EmptyStringTests(support.CliTestCase):
    def test_empty_project_id(self):
        doc = mutated(lambda doc: doc["project"].__setitem__("project_id", ""))
        self.check_invalid(doc, "empty_string")

    def test_empty_revision(self):
        doc = mutated(lambda doc: doc["project"].__setitem__("revision", ""))
        self.check_invalid(doc, "empty_string")

    def test_empty_module_id(self):
        doc = mutated(lambda doc: doc["modules"][1].__setitem__("id", ""))
        self.check_invalid(doc, "empty_string")

    def test_empty_component_instance_id(self):
        doc = mutated(
            lambda doc: doc["components"][0].__setitem__("instance_id", ""))
        self.check_invalid(doc, "empty_string")

    def test_empty_constraint_id(self):
        doc = mutated(lambda doc: doc["constraints"][0].__setitem__("id", ""))
        self.check_invalid(doc, "empty_string")

    def test_empty_designator(self):
        doc = mutated(
            lambda doc: doc["components"][0].__setitem__("designator", ""))
        self.check_invalid(doc, "empty_string")

    def test_empty_captured_at(self):
        doc = mutated(
            lambda doc: doc["snapshot"].__setitem__("captured_at", ""))
        self.check_invalid(doc, "empty_string")


class NumberTests(support.CliTestCase):
    def test_negative_weight(self):
        doc = mutated(lambda doc: doc["constraints"][0].__setitem__("weight",
                                                                    -0.5))
        self.check_invalid(doc, "number_out_of_range")

    def test_zero_weight(self):
        doc = mutated(lambda doc: doc["constraints"][0].__setitem__("weight",
                                                                    0.0))
        self.check_invalid(doc, "number_out_of_range")

    def test_bool_disguised_as_number(self):
        doc = mutated(lambda doc: doc["constraints"][0].__setitem__("dx_mm",
                                                                    True))
        self.check_invalid(doc, "number_invalid")

    def test_numeric_string_rejected(self):
        doc = mutated(lambda doc: doc["constraints"][0].__setitem__("weight",
                                                                    "0.8"))
        self.check_invalid(doc, "number_invalid")

    def test_null_is_not_zero(self):
        doc = mutated(lambda doc: doc["constraints"][0].__setitem__("dx_mm",
                                                                    None))
        self.check_invalid(doc, "number_invalid")

    def test_negative_component_size(self):
        doc = mutated(
            lambda doc: doc["components"][0].__setitem__("size_mm",
                                                         {"w": -1.0,
                                                          "h": 2.0}))
        self.check_invalid(doc, "number_out_of_range")

    def test_zero_board_width(self):
        doc = mutated(
            lambda doc: doc["board"].__setitem__("width_mm", 0.0))
        self.check_invalid(doc, "number_out_of_range")

    def test_confidence_above_one(self):
        doc = mutated(
            lambda doc: doc["modules"][1].__setitem__("confidence", 1.5))
        self.check_invalid(doc, "number_out_of_range")

    def test_confidence_below_zero(self):
        doc = mutated(
            lambda doc: doc["modules"][1].__setitem__("confidence", -0.1))
        self.check_invalid(doc, "number_out_of_range")

    def test_max_depth_zero(self):
        doc = mutated(lambda doc: doc.__setitem__("policy", {"max_depth": 0}))
        self.check_invalid(doc, "number_out_of_range")

    def test_max_depth_too_large(self):
        doc = mutated(lambda doc: doc.__setitem__("policy", {"max_depth": 13}))
        self.check_invalid(doc, "number_out_of_range")

    def test_negative_position_tolerance(self):
        doc = mutated(
            lambda doc: doc.__setitem__(
                "policy", {"position_tolerance_mm": -1.0}))
        self.check_invalid(doc, "number_out_of_range")

    def test_weight_epsilon_zero(self):
        doc = mutated(
            lambda doc: doc.__setitem__("policy", {"weight_epsilon": 0.0}))
        self.check_invalid(doc, "number_out_of_range")


class UnknownPropertyTests(support.CliTestCase):
    def test_top_level_extra_property(self):
        doc = mutated(lambda doc: doc.__setitem__("absolute_coordinates",
                                                  []))
        self.check_invalid(doc, "unknown_property")

    def test_module_extra_property(self):
        doc = mutated(lambda doc: doc["modules"][0].__setitem__(
            "placement_x_mm", 1.0))
        self.check_invalid(doc, "unknown_property")

    def test_component_extra_property(self):
        doc = mutated(lambda doc: doc["components"][0].__setitem__(
            "footprint", "0402"))
        self.check_invalid(doc, "unknown_property")

    def test_constraint_extra_property(self):
        doc = mutated(lambda doc: doc["constraints"][0].__setitem__(
            "absolute_x_mm", 3.0))
        self.check_invalid(doc, "unknown_property")

    def test_policy_extra_property(self):
        doc = mutated(lambda doc: doc.__setitem__(
            "policy", {"max_depth": 6, "solver": "anneal"}))
        self.check_invalid(doc, "unknown_property")


class IdentityTests(support.CliTestCase):
    def test_duplicate_module_id(self):
        doc = mutated(
            lambda doc: doc["modules"][1].__setitem__("id", "mod:root"))
        # The parent/children references also break; duplicate id is the point.
        path = self.write_input("dup-module-id.json", doc)
        result = self.run_on("validate", path)
        self.assert_invalid(result, "duplicate_id")

    def test_module_and_component_share_id(self):
        doc = mutated(
            lambda doc: doc["modules"][1].__setitem__("id", "cmp:A"))
        self.check_invalid(doc, "node_id_duplicate")

    def test_duplicate_instance_id(self):
        doc = mutated(lambda doc: doc["components"].append(
            copy.deepcopy(doc["components"][0])))
        self.check_invalid(doc, "node_id_duplicate")

    def test_duplicate_constraint_id(self):
        doc = mutated(lambda doc: doc["constraints"].append(
            copy.deepcopy(doc["constraints"][0])))
        self.check_invalid(doc, "duplicate_id")

    def test_duplicate_designator_is_a_warning_not_an_error(self):
        doc = fixtures.small_case()
        doc["modules"][1]["components"] = ["cmp:A", "cmp:B"]
        doc["components"].append({
            "instance_id": "cmp:B", "designator": "A",
            "size_mm": {"w": 2.0, "h": 2.0},
        })
        doc["constraints"].append({
            "id": "ccg:9", "from": "mod:leaf", "to": "cmp:B",
            "dx_mm": 8.0, "dy_mm": 1.0, "rotation_deg": 0, "weight": 1.0,
        })
        path = self.write_input("dup-designator.json", doc)
        result = self.run_on("validate", path)
        self.assert_exit_status(result, 0, "valid")
        payload = self.payload(result)
        self.assertIn("designator_duplicate",
                      support.finding_codes(payload))
        warnings = [item for item in payload.get("findings") or []
                    if item.get("code") == "designator_duplicate"]
        self.assertEqual(warnings[0].get("severity"), "warning")
        plan = self.run_on("plan", path)
        self.assert_exit_status(plan, 0, "planned_with_scope")


class ProvenanceAndSnapshotTests(support.CliTestCase):
    def test_derived_without_sources(self):
        doc = mutated(
            lambda doc: doc.__setitem__(
                "provenance", {"kind": "derived", "sources": [],
                               "note": "claims derived but has no source"}))
        self.check_invalid(doc, "provenance_source_missing")

    def test_derived_source_without_sha256(self):
        doc = mutated(
            lambda doc: doc.__setitem__(
                "provenance", {"kind": "derived",
                               "sources": [{"ref": "board.kicad_pcb"}],
                               "note": "derived without a frozen hash"}))
        self.check_invalid(doc, "provenance_source_missing")

    def test_snapshot_null_hash_not_declared(self):
        doc = mutated(
            lambda doc: doc["snapshot"].__setitem__("content_sha256", None))
        self.check_invalid(doc, "snapshot_missing_not_declared")

    def test_snapshot_hash_bad_length(self):
        doc = mutated(
            lambda doc: doc["snapshot"].__setitem__("content_sha256", "abc"))
        result, payload = self.check_invalid(doc)
        self.assertTrue(support.finding_codes(payload),
                        msg=result.context())

    def test_snapshot_missing_fields_duplicate(self):
        doc = mutated(
            lambda doc: doc["snapshot"].__setitem__("missing_fields",
                                                    ["a", "a"]))
        result, payload = self.check_invalid(doc)
        self.assertTrue(support.finding_codes(payload),
                        msg=result.context())


class MultipleErrorsTests(support.CliTestCase):
    def test_all_errors_are_reported_not_just_the_first(self):
        doc = mutated(lambda doc: None)
        doc.pop("units")
        doc["constraints"][0]["weight"] = -1.0
        doc["project"]["project_id"] = ""
        path = self.write_input("many-errors.json", doc)
        result = self.run_on("validate", path)
        payload = self.assert_invalid(result, "missing_required",
                                      "number_out_of_range", "empty_string")
        error_codes = [item.get("code") for item in payload.get("findings") or []
                       if item.get("severity") == "error"]
        self.assertGreaterEqual(len(error_codes), 3,
                                msg="expected >= 3 error findings, got %r\n%s"
                                    % (error_codes, result.context()))

    def test_plan_also_rejects_invalid_input_with_exit_two(self):
        doc = mutated(lambda doc: doc["constraints"][0].__setitem__("to",
                                                                    "mod:ghost"))
        path = self.write_input("bad-plan.json", doc)
        result = self.run_on("plan", path)
        self.assert_exit(result, 2)
        payload = self.payload(result)
        self.assertEqual(payload.get("status"), "invalid_input",
                         msg=result.context())


if __name__ == "__main__":
    unittest.main()
