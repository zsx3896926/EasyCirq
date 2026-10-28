"""Units: explicit mm/mil normalisation, no unit guessing (contract.md 2.3)."""
import unittest

from . import fixtures, support


class MilNormalisationTests(support.CliTestCase):
    def plan(self, document, name="case.json"):
        path = self.write_input(name, document)
        result = self.run_on("plan", path)
        self.assert_exit(result, 0)
        payload = self.payload(result)
        return result, path, payload

    def test_mil_input_reports_normalisation(self):
        result, _path, payload = self.plan(fixtures.mil_case(), "mil.json")
        self.assertEqual(payload.get("status"), "planned_with_scope",
                         msg=result.context())
        units = payload.get("units") or {}
        self.assertEqual(units.get("input_length"), "mil")
        self.assertEqual(units.get("normalized_length"), "mm")
        self.assert_close(result, units.get("scale_to_mm"), 0.0254,
                          label="units.scale_to_mm")

    def test_mil_constraints_are_normalised_to_mm(self):
        result, _path, payload = self.plan(fixtures.mil_case(), "mil.json")
        by_id = {item.get("id"): item
                 for item in payload.get("normalized_constraints") or []}
        self.assert_close(result, by_id["ccg:1"].get("dx_mm"), 25.4,
                          label="ccg:1 dx_mm")
        self.assert_close(result, by_id["ccg:1"].get("dy_mm"), 0.0,
                          label="ccg:1 dy_mm")
        self.assert_close(result, by_id["ccg:2"].get("dx_mm"), 2.54,
                          label="ccg:2 dx_mm")
        self.assert_close(result, by_id["ccg:2"].get("dy_mm"), 1.016,
                          label="ccg:2 dy_mm")

    def test_mil_bboxes_are_normalised_to_mm(self):
        result, _path, payload = self.plan(fixtures.mil_case(), "mil.json")
        # cmp:A 200x200 mil = 5.08x5.08 mm at (100,40) mil = (2.54,1.016) mm.
        self.assert_bbox(result, payload, "cmp:A", 0.0, 0.0, 5.08, 5.08)
        self.assert_bbox(result, payload, "mod:leaf",
                         2.54, 1.016, 5.08, 5.08)
        # leaf origin 1000 mil = 25.4 mm in the root frame.
        self.assert_bbox(result, payload, "mod:root",
                         27.94, 1.016, 5.08, 5.08)

    def test_mil_and_mm_inputs_normalise_identically(self):
        mil_result, _mil_path, mil_plan = self.plan(fixtures.mil_case(),
                                                    "mil.json")
        mm_result, _mm_path, mm_plan = self.plan(fixtures.mm_case(),
                                                 "mm.json")
        self.assertEqual(mil_plan.get("status"), mm_plan.get("status"),
                         msg=mil_result.context() + "\n---\n"
                             + mm_result.context())
        mil_nodes = support.node_map(mil_plan)
        mm_nodes = support.node_map(mm_plan)
        self.assertEqual(sorted(mil_nodes), sorted(mm_nodes))
        for node_id in mil_nodes:
            mil_frame = mil_nodes[node_id].get("frame") or {}
            mm_frame = mm_nodes[node_id].get("frame") or {}
            self.assert_close(mil_result, mil_frame["offset_mm"][0],
                              mm_frame["offset_mm"][0], 1e-9,
                              "%s frame.x (mil vs mm)" % node_id)
            self.assert_close(mil_result, mil_frame["offset_mm"][1],
                              mm_frame["offset_mm"][1], 1e-9,
                              "%s frame.y (mil vs mm)" % node_id)
            mil_box = mil_nodes[node_id].get("bbox_mm")
            mm_box = mm_nodes[node_id].get("bbox_mm")
            self.assertEqual(mil_box is None, mm_box is None)
            if mil_box is not None:
                for key in ("x", "y", "w", "h"):
                    self.assert_close(mil_result, mil_box[key],
                                      mm_box[key], 1e-9,
                                      "%s bbox.%s (mil vs mm)"
                                      % (node_id, key))

    def test_mil_and_mm_normalised_constraints_match(self):
        mil_result, _p, mil_plan = self.plan(fixtures.mil_case(), "mil.json")
        _r, _p2, mm_plan = self.plan(fixtures.mm_case(), "mm.json")
        mil_constraints = {item.get("id"): item
                           for item in mil_plan.get("normalized_constraints")
                           or []}
        mm_constraints = {item.get("id"): item
                          for item in mm_plan.get("normalized_constraints")
                          or []}
        self.assertEqual(sorted(mil_constraints), sorted(mm_constraints))
        for constraint_id in mil_constraints:
            for field in ("dx_mm", "dy_mm", "weight"):
                self.assert_close(
                    mil_result,
                    mil_constraints[constraint_id][field],
                    mm_constraints[constraint_id][field], 1e-9,
                    "%s %s (mil vs mm)" % (constraint_id, field))


class UnitDeclarationTests(support.CliTestCase):
    def test_missing_units_is_rejected_not_guessed_as_mm(self):
        doc = fixtures.small_case()
        doc.pop("units")
        path = self.write_input("no-units.json", doc)
        result = self.run_on("validate", path)
        self.assert_invalid(result, "missing_required")

    def test_units_missing_length_is_rejected(self):
        doc = fixtures.small_case()
        doc["units"] = {}
        path = self.write_input("units-empty.json", doc)
        result = self.run_on("validate", path)
        self.assert_invalid(result, "missing_required")

    def test_units_length_enum_is_enforced(self):
        doc = fixtures.small_case()
        doc["units"] = {"length": "inch"}
        path = self.write_input("units-inch.json", doc)
        result = self.run_on("validate", path)
        self.assert_invalid(result, "enum_invalid")

    def test_units_must_be_an_object(self):
        doc = fixtures.small_case()
        doc["units"] = "mm"
        path = self.write_input("units-string.json", doc)
        result = self.run_on("validate", path)
        self.assert_invalid(result, "type_mismatch")

    def test_units_extra_property_is_rejected(self):
        doc = fixtures.small_case()
        doc["units"] = {"length": "mm", "angle": "deg"}
        path = self.write_input("units-extra.json", doc)
        result = self.run_on("validate", path)
        self.assert_invalid(result, "unknown_property")


if __name__ == "__main__":
    unittest.main()
