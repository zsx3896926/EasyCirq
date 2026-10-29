"""Invalid case data: every rejection path exits 3 without a scorecard."""
import copy
import json

from . import fixtures as f
from . import support


class InvalidCaseTests(support.CliTestCase):
    def _base(self):
        return f.case()

    def _run_document(self, document):
        path = self.write_case("case.json", document)
        return self.cli("--cases", str(path), "--case", "T-1", "--json")

    def _run_raw(self, text):
        path = self.write_raw_case("case.json", text)
        return self.cli("--cases", str(path), "--case", "T-1", "--json")

    def _assert_invalid(self, document):
        result = self._run_document(document)
        payload = self.assert_error_payload(result)
        self.assertEqual(payload["message"], "invalid case data",
                         msg=result.context())
        for entry in payload["errors"]:
            self.assertIn("path", entry, msg=result.context())
            self.assertIn("message", entry, msg=result.context())
        return payload

    # -- unknown / missing fields ---------------------------------------
    def test_unknown_top_level_field_is_rejected(self):
        document = self._base()
        document["surprise"] = 1
        payload = self._assert_invalid(document)
        self.assertTrue(any("unknown field" in entry["message"]
                            for entry in payload["errors"]),
                        msg="unknown field must be named in the errors")

    def test_unknown_nested_component_field_is_rejected(self):
        document = self._base()
        document["components"][0]["footprint"] = "0402"
        self._assert_invalid(document)

    def test_missing_size_mm_is_rejected_not_defaulted(self):
        document = self._base()
        del document["components"][0]["size_mm"]
        payload = self._assert_invalid(document)
        self.assertTrue(any("size_mm" in entry["path"]
                            for entry in payload["errors"]))

    def test_missing_schema_is_rejected(self):
        document = self._base()
        del document["schema"]
        self._assert_invalid(document)

    def test_wrong_schema_is_rejected(self):
        document = self._base()
        document["schema"] = "easycirq.pcb-placement-case/v2"
        self._assert_invalid(document)

    def test_unknown_domain_is_rejected(self):
        document = self._base()
        document["domain"] = "quantum"
        self._assert_invalid(document)

    def test_units_other_than_mm_are_rejected(self):
        document = self._base()
        document["units"] = {"length": "inch"}
        self._assert_invalid(document)

    def test_derived_evidence_without_sha256_is_rejected(self):
        document = self._base()
        document["evidence_level"] = "derived"
        document["provenance"]["source_sha256"] = None
        self._assert_invalid(document)

    # -- numbers ---------------------------------------------------------
    def test_nan_literal_is_rejected(self):
        text = json.dumps(self._base(), indent=2).replace(
            '"width_mm": 40.0', '"width_mm": NaN', 1)
        self.assert_error_payload(self._run_raw(text))

    def test_infinity_literal_is_rejected(self):
        text = json.dumps(self._base(), indent=2).replace(
            '"width_mm": 40.0', '"width_mm": Infinity', 1)
        self.assert_error_payload(self._run_raw(text))

    def test_overflowing_number_is_rejected(self):
        text = json.dumps(self._base(), indent=2).replace(
            '"width_mm": 40.0', '"width_mm": 1e999', 1)
        self.assert_error_payload(self._run_raw(text))

    def test_numeric_string_is_rejected(self):
        document = self._base()
        document["board"]["width_mm"] = "40.0"
        self._assert_invalid(document)

    def test_boolean_used_as_a_number_is_rejected(self):
        document = self._base()
        document["board"]["width_mm"] = True
        self._assert_invalid(document)

    def test_negative_size_is_rejected(self):
        document = self._base()
        document["board"]["width_mm"] = -40.0
        self._assert_invalid(document)

    def test_invalid_allowed_rotation_is_rejected(self):
        document = self._base()
        document["components"][0]["allowed_rotations"] = [45]
        self._assert_invalid(document)

    # -- JSON syntax -----------------------------------------------------
    def test_duplicate_json_key_is_rejected(self):
        text = json.dumps(self._base(), indent=2).replace(
            '"id": "T-1",', '"id": "T-1",\n  "id": "T-2",', 1)
        self.assertIn('"id": "T-2"', text)
        payload = self.assert_error_payload(self._run_raw(text))
        self.assertTrue(any("duplicate" in entry["message"]
                            for entry in payload["errors"]))

    def test_invalid_json_syntax_is_rejected(self):
        self.assert_error_payload(self._run_raw("{ not json"))

    def test_invalid_utf8_is_rejected(self):
        path = self.write_bytes_case("case.json", b"\xff\xfe\xfd{")
        result = self.cli("--cases", str(path), "--case", "T-1", "--json")
        self.assert_error_payload(result)

    # -- references ------------------------------------------------------
    def test_dangling_net_component_ref_is_rejected(self):
        document = self._base()
        document["nets"] = [f.net("N1", "signal", [["U9", "A"]])]
        self._assert_invalid(document)

    def test_dangling_net_pin_name_is_rejected(self):
        document = self._base()
        document["components"][0]["pins"] = [
            {"name": "A", "x_mm": 0, "y_mm": 0}]
        document["nets"] = [f.net("N1", "signal", [["U1", "NOPE"]])]
        self._assert_invalid(document)

    def test_dangling_check_pin_is_rejected(self):
        document = self._base()
        document["components"][0]["pins"] = [
            {"name": "A", "x_mm": 0, "y_mm": 0}]
        document["checks"] = [f.check("ck-x", "max_distance",
                                      [["U1", "A"], ["U1", "NOPE"]], 1.0)]
        self._assert_invalid(document)

    def test_unknown_check_code_is_rejected(self):
        document = self._base()
        document["components"][0]["pins"] = [
            {"name": "A", "x_mm": 0, "y_mm": 0}]
        document["checks"] = [f.check("ck-x", "spline",
                                      [["U1", "A"], ["U1", "A"]], 1.0)]
        self._assert_invalid(document)

    def test_placement_referencing_unknown_component_is_rejected(self):
        document = self._base()
        document["placement"]["U9"] = f.placed(1, 1)
        self._assert_invalid(document)

    def test_fixed_component_without_fixed_xy_is_rejected(self):
        document = self._base()
        document["components"][0]["fixed"] = True
        document["components"][0]["fixed_xy_mm"] = None
        document["placement"] = {}
        self._assert_invalid(document)

    def test_expected_code_outside_the_contract_is_rejected(self):
        document = self._base()
        document["expected"] = f.expected("acceptable", ["check_failed"])
        self._assert_invalid(document)

    def test_expected_soft_fail_referencing_unknown_check_is_rejected(self):
        document = self._base()
        document["expected"] = f.expected("acceptable", [], ["ck-missing"])
        self._assert_invalid(document)

    def test_pair_with_referencing_unknown_case_is_rejected(self):
        document = self._base()
        document["pair_with"] = "T-404"
        self._assert_invalid(document)

    def test_fixed_xy_on_a_non_fixed_component_is_rejected(self):
        document = self._base()
        document["components"][0]["fixed_xy_mm"] = [10, 10]
        self._assert_invalid(document)

    def test_empty_components_list_is_rejected(self):
        document = self._base()
        document["components"] = []
        document["placement"] = {}
        self._assert_invalid(document)

    def test_duplicate_pin_names_are_rejected(self):
        document = self._base()
        document["components"][0]["pins"] = [
            {"name": "A", "x_mm": 0, "y_mm": 0},
            {"name": "A", "x_mm": 1, "y_mm": 1},
        ]
        self._assert_invalid(document)

    def test_duplicate_net_names_are_rejected(self):
        document = self._base()
        document["components"][0]["pins"] = [
            {"name": "A", "x_mm": 0, "y_mm": 0},
            {"name": "B", "x_mm": 1, "y_mm": 0},
        ]
        document["nets"] = [
            f.net("N", "signal", [["U1", "A"], ["U1", "B"]]),
            f.net("N", "ground", [["U1", "A"], ["U1", "B"]]),
        ]
        self._assert_invalid(document)

    def test_duplicate_check_ids_are_rejected(self):
        document = self._base()
        document["components"][0]["pins"] = [
            {"name": "A", "x_mm": 0, "y_mm": 0},
            {"name": "B", "x_mm": 1, "y_mm": 0},
        ]
        document["checks"] = [
            f.check("ck-dup", "max_distance",
                    [["U1", "A"], ["U1", "B"]], 1.0),
            f.check("ck-dup", "loop_span",
                    [["U1", "A"], ["U1", "B"]], 1.0),
        ]
        self._assert_invalid(document)

    def test_negative_rubric_tolerance_is_rejected(self):
        document = self._base()
        document["rubric"]["connector_edge_tol_mm"] = -1.0
        self._assert_invalid(document)

    def test_absurdly_large_distance_is_rejected_not_crashed(self):
        document = self._base()
        document["board"]["width_mm"] = 1e12
        self._assert_invalid(document)

    def test_huge_integer_literal_is_rejected_not_crashed(self):
        text = json.dumps(self._base(), indent=2).replace(
            '"width_mm": 40.0', '"width_mm": ' + "9" * 400, 1)
        self.assert_error_payload(self._run_raw(text))

    def test_net_span_beyond_the_congestion_grid_is_rejected(self):
        components = [f.component("U1", 4500, 4500, 8, 8,
                                  pins={"A": (-4500, 0), "B": (4500, 0)})]
        document = f.case(
            board=f.board_document(9000.0, 9000.0),
            components=components,
            nets=[f.net("HUGE", "signal", [["U1", "A"], ["U1", "B"]])],
            placement={"U1": f.placed(4500, 4500)})
        result = self.judge(document)
        self.assert_error_payload(result)


class InvalidCollectionTests(support.CliTestCase):
    def test_duplicate_case_ids_are_rejected(self):
        first = f.case("T-1")
        second = f.case("T-1", title="duplicate id")
        result = self.judge_all([first, second])
        self.assert_error_payload(result)

    def test_empty_collection_is_rejected(self):
        path = self.write_raw_case(
            "cases.json",
            '{"schema": "easycirq.pcb-placement-benchmarks/v1", '
            '"cases": []}')
        result = self.cli("--cases", str(path), "--all", "--json")
        self.assert_error_payload(result)

    def test_empty_json_array_is_rejected(self):
        path = self.write_raw_case("cases.json", "[]")
        result = self.cli("--cases", str(path), "--all", "--json")
        self.assert_error_payload(result)

    def test_unknown_collection_field_is_rejected(self):
        path = self.write_raw_case(
            "cases.json",
            json.dumps({"schema": "easycirq.pcb-placement-benchmarks/v1",
                        "cases": [f.case()], "extra": 1}, indent=2))
        result = self.cli("--cases", str(path), "--all", "--json")
        self.assert_error_payload(result)

    def test_non_object_case_entry_is_rejected(self):
        path = self.write_raw_case("cases.json", "[1, 2]")
        result = self.cli("--cases", str(path), "--all", "--json")
        self.assert_error_payload(result)

    def test_invalid_case_in_a_collection_reports_its_path(self):
        broken = f.case("T-2")
        del broken["components"][0]["size_mm"]
        result = self.judge_all([f.case("T-1"), broken])
        payload = self.assert_error_payload(result)
        self.assertTrue(
            any(entry["case_id"] == "T-2" for entry in payload["errors"]),
            msg="the invalid case id must be reported\n" + result.context())
        self.assertTrue(
            any("$.cases[1]" in (entry["path"] or "")
                for entry in payload["errors"]),
            msg="the collection index must be reported\n" + result.context())
