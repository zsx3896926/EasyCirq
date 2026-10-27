"""Tests for the BOM/CPL parsers and the BOM/CPL cross-check.

Covers contract §7.3-7.5: normal samples, negative samples and missing
information (unknown), using the synthetic builders from ``support.py``.
Assertions check statuses and rule ids, not only counts.
"""

import unittest

from tests.delivery_audit import support

from delivery_audit import assembly, bom, cpl


# ---------------------------------------------------------------------------
# Small local builders / accessors


def parse_bom_text(text, options=None):
    return bom.parse_bom(text.encode("utf-8"), "bom.csv", options)


def parse_cpl_text(text, options=None):
    return cpl.parse_cpl(text.encode("utf-8"), "cpl.csv", options)


def rule_ids(result, status=None):
    return {item["rule_id"] for item in result["findings"]
            if status is None or item["status"] == status}


def findings_for(result, rule_id):
    return [item for item in result["findings"] if item["rule_id"] == rule_id]


def finding_statuses(result, rule_id):
    return [item["status"] for item in findings_for(result, rule_id)]


def bom_row(designator="R1", quantity="1", comment="10k", **extra):
    row = {
        "Comment": comment,
        "Designator": designator,
        "Footprint": "0402",
        "Quantity": quantity,
        "MPN": "M1",
        "Manufacturer": "Yageo",
        "LCSC": "C1",
        "DNP": "",
        "Assembly": "smt",
    }
    row.update(extra)
    return row


def cpl_row(designator="R1", x="10.000", y="10.000", side="Top",
            rotation="0", **extra):
    row = {
        "Designator": designator,
        "Mid X": x,
        "Mid Y": y,
        "Layer": side,
        "Rotation": rotation,
    }
    row.update(extra)
    return row


def declarations(policies=None):
    if policies is None:
        return {"policies": {}}
    data = {"policies": {}}
    data["policies"].update(policies)
    return data


class BomParserTests(unittest.TestCase):
    maxDiff = None

    def test_legal_bom_passes(self):
        result = parse_bom_text(support.bom_text(support.default_bom_rows()))
        self.assertEqual(result["kind"], "bom")
        self.assertEqual(result["file"], "bom.csv")
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["findings"], [])
        facts = result["facts"]
        self.assertEqual(facts["encoding"], "utf-8-sig")
        self.assertEqual(facts["delimiter"], ",")
        self.assertEqual(facts["header_mapping"]["designator"], "Designator")
        self.assertEqual(facts["header_mapping"]["quantity"], "Quantity")
        self.assertEqual(facts["header_mapping"]["value"], "Comment")
        self.assertEqual(facts["header_mapping"]["footprint"], "Footprint")
        self.assertEqual(facts["header_mapping"]["mpn"], "MPN")
        self.assertEqual(facts["header_mapping"]["manufacturer"], "Manufacturer")
        self.assertEqual(facts["header_mapping"]["lcsc"], "LCSC")
        self.assertEqual(facts["header_mapping"]["dnp"], "DNP")
        self.assertEqual(facts["header_mapping"]["assembly"], "Assembly")
        self.assertEqual(len(facts["rows"]), 4)
        self.assertEqual(facts["rows"][1]["designators"], ["C1", "C2"])
        self.assertEqual(facts["rows"][1]["quantity"], 2)
        self.assertEqual(facts["counts"]["designator_occurrences"], 5)
        self.assertEqual(facts["counts"]["unique_designators"], 5)
        self.assertEqual(facts["counts"]["assembly"]["smt"], 3)
        self.assertEqual(facts["counts"]["assembly"]["tht"], 1)
        self.assertEqual(facts["counts"]["dnp_designators"], 0)

    def test_utf8_bom_bytes_decoded(self):
        data = support.bom_text(support.default_bom_rows()).encode("utf-8-sig")
        result = bom.parse_bom(data, "bom.csv")
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["facts"]["encoding"], "utf-8-sig")
        self.assertEqual(result["facts"]["rows"][0]["designator_raw"], "R1")

    def test_utf16_declared_encoding(self):
        data = support.bom_text(support.default_bom_rows()).encode("utf-16")
        result = bom.parse_bom(data, "bom.csv", {"encoding": "utf-16"})
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["facts"]["encoding"], "utf-16")
        self.assertEqual(len(result["facts"]["rows"]), 4)

    def test_unknown_declared_encoding_is_option_error(self):
        text = support.bom_text(support.default_bom_rows())
        with self.assertRaises(ValueError):
            bom.parse_bom(text.encode("utf-8"), "bom.csv",
                          {"encoding": "definitely-not-a-codec"})

    def test_wrong_encoding_bytes_are_not_replaced(self):
        data = support.bom_text(support.default_bom_rows()).encode("utf-16")
        result = bom.parse_bom(data, "bom.csv")  # default utf-8-sig
        self.assertEqual(result["status"], "fail")
        self.assertIn("bom.encoding_unspecified", rule_ids(result, "fail"))
        self.assertEqual(result["facts"]["rows"], [])
        self.assertNotIn("\ufffd", repr(result))

    def test_malformed_bytes_do_not_raise(self):
        result = bom.parse_bom(b"\xff\xfe\x00garbage", "bom.csv")
        self.assertEqual(result["status"], "fail")
        self.assertIn("bom.encoding_unspecified", rule_ids(result, "fail"))

    def test_quoted_comma_and_embedded_newline(self):
        rows = [
            bom_row("R1", comment="10k, 1%"),
            bom_row("R2", comment="multi\nline"),
        ]
        result = parse_bom_text(support.bom_text(rows))
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["facts"]["rows"][0]["value"], "10k, 1%")
        self.assertEqual(result["facts"]["rows"][1]["value"], "multi\nline")

    def test_documented_aliases(self):
        header = ["Refs", "Qty", "Value", "Package", "Manufacturer Part Number",
                  "Manufacturer", "Supplier Part", "Do Not Populate", "Side",
                  "Assembly"]
        rows = [{
            "Refs": "R1, R2",
            "Qty": "2",
            "Value": "10k",
            "Package": "0402",
            "Manufacturer Part Number": "M1",
            "Manufacturer": "Yageo",
            "Supplier Part": "C123",
            "Do Not Populate": "no",
            "Side": "Top",
            "Assembly": "SMT",
        }]
        result = parse_bom_text(support.bom_text(rows, header=header))
        self.assertEqual(result["status"], "pass")
        facts = result["facts"]
        for field in ("designator", "quantity", "value", "footprint", "mpn",
                      "manufacturer", "lcsc", "dnp", "assembly", "side"):
            self.assertIn(field, facts["header_mapping"])
        self.assertEqual(facts["rows"][0]["designators"], ["R1", "R2"])
        self.assertIs(facts["rows"][0]["dnp"], False)
        self.assertEqual(facts["rows"][0]["assembly"], "smt")
        self.assertEqual(facts["rows"][0]["side"], "Top")

    def test_one_row_multiple_designators(self):
        rows = [bom_row("R1,R2;R3 R4", quantity="4")]
        result = parse_bom_text(support.bom_text(rows))
        self.assertEqual(result["status"], "pass")
        row = result["facts"]["rows"][0]
        self.assertEqual(row["designators"], ["R1", "R2", "R3", "R4"])
        self.assertEqual(row["designator_rule"], "list")

    def test_range_expansion_both_forms(self):
        for raw in ("R1-R3", "R1-3"):
            with self.subTest(designator=raw):
                rows = [bom_row(raw, quantity="3")]
                result = parse_bom_text(support.bom_text(rows))
                self.assertEqual(result["status"], "pass")
                row = result["facts"]["rows"][0]
                self.assertEqual(row["designators"], ["R1", "R2", "R3"])
                self.assertEqual(row["designator_rule"], "range")

    def test_zero_padded_range_preserves_width(self):
        rows = [bom_row("C001-C003", quantity="3")]
        result = parse_bom_text(support.bom_text(rows))
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["facts"]["rows"][0]["designators"],
                         ["C001", "C002", "C003"])

    def test_descending_range_is_reported_not_guessed(self):
        result = parse_bom_text(support.bom_text(
            [bom_row("R3-R1", quantity="3")]))
        self.assertEqual(result["status"], "fail")
        self.assertIn("bom.designator_range_invalid", rule_ids(result, "fail"))
        self.assertEqual(result["facts"]["rows"][0]["designators"], [])

    def test_range_with_different_prefix_is_reported(self):
        result = parse_bom_text(support.bom_text(
            [bom_row("R1-C3", quantity="2")]))
        self.assertEqual(result["status"], "fail")
        self.assertIn("bom.designator_range_invalid", rule_ids(result, "fail"))

    def test_unparseable_designator_token_is_reported(self):
        result = parse_bom_text(support.bom_text(
            [bom_row("R1/R2", quantity="2")]))
        self.assertEqual(result["status"], "fail")
        self.assertIn("bom.designator_missing_invalid",
                      rule_ids(result, "fail"))

    def test_quantity_mismatch_is_failure(self):
        result = parse_bom_text(support.bom_text(
            [bom_row("R1,C1", quantity="3")]))
        self.assertEqual(result["status"], "fail")
        item = findings_for(result, "bom.quantity_mismatch")[0]
        self.assertEqual(item["status"], "fail")
        self.assertEqual(item["actual"], 3)
        self.assertEqual(item["expected"], 2)

    def test_duplicate_designator_is_failure(self):
        result = parse_bom_text(support.bom_text(
            [bom_row("R1"), bom_row("R1")]))
        self.assertEqual(result["status"], "fail")
        self.assertIn("bom.designator_duplicate", rule_ids(result, "fail"))

    def test_missing_designator_is_failure(self):
        result = parse_bom_text(support.bom_text([bom_row("", quantity="1")]))
        self.assertEqual(result["status"], "fail")
        self.assertIn("bom.designator_missing_invalid",
                      rule_ids(result, "fail"))

    def test_dnp_truth_values(self):
        rows = [
            bom_row("R1", dnp="1"),
            bom_row("R2", dnp="no"),
            bom_row("R3", DNP="FALSE"),
            bom_row("R4", DNP=""),
        ]
        rows[0]["DNP"] = "1"
        rows[1]["DNP"] = "no"
        rows[2]["DNP"] = "FALSE"
        rows[3]["DNP"] = ""
        result = parse_bom_text(support.bom_text(rows))
        self.assertEqual(result["status"], "pass")
        dnp_values = [row["dnp"] for row in result["facts"]["rows"]]
        self.assertEqual(dnp_values, [True, False, False, False])

    def test_dnp_invalid_value_is_failure(self):
        row = bom_row("R1")
        row["DNP"] = "maybe"
        result = parse_bom_text(support.bom_text([row]))
        self.assertEqual(result["status"], "fail")
        self.assertIn("bom.dnp_invalid", rule_ids(result, "fail"))

    def test_assembly_unknown_is_unknown(self):
        row = bom_row("R1")
        row["Assembly"] = "wave"
        result = parse_bom_text(support.bom_text([row]))
        self.assertEqual(result["status"], "unknown")
        self.assertIn("bom.assembly_unknown", rule_ids(result, "unknown"))
        self.assertIsNone(result["facts"]["rows"][0]["assembly"])

    def test_required_columns(self):
        header = ["Comment", "Designator", "Quantity", "Assembly"]
        rows = [{"Comment": "10k", "Designator": "R1", "Quantity": "1",
                 "Assembly": "smt"}]
        text = support.bom_text(rows, header=header)
        self.assertEqual(parse_bom_text(text)["status"], "pass")
        result = parse_bom_text(
            text, {"required_fields": ["designator", "quantity", "mpn",
                                       "footprint"]})
        self.assertEqual(result["status"], "fail")
        missing = findings_for(result, "bom.required_field_missing")
        self.assertEqual(sorted(item.get("object") for item in missing),
                         ["footprint", "mpn"])

    def test_required_row_cell(self):
        rows = [bom_row("R1", MPN="")]
        result = parse_bom_text(
            support.bom_text(rows), {"required_fields": ["designator",
                                                         "quantity", "mpn"]})
        self.assertEqual(result["status"], "fail")
        item = findings_for(result, "bom.required_field_missing")[0]
        self.assertEqual(item.get("object"), "mpn")
        self.assertEqual(item.get("line"), 2)

    def test_missing_quantity_column(self):
        header = ["Designator"]
        rows = [{"Designator": "R1"}]
        result = parse_bom_text(support.bom_text(rows, header=header))
        self.assertEqual(result["status"], "fail")
        self.assertIn("bom.required_field_missing", rule_ids(result, "fail"))

    def test_no_designator_column(self):
        header = ["Comment", "Quantity"]
        result = parse_bom_text(support.bom_text(
            [{"Comment": "10k", "Quantity": "1"}], header=header))
        self.assertEqual(result["status"], "fail")
        self.assertIn("bom.no_designator_column", rule_ids(result, "fail"))
        self.assertEqual(result["facts"]["rows"], [])

    def test_empty_bom(self):
        for payload in (b"", b"\n   \n", b"\r\n"):
            with self.subTest(payload=payload):
                result = bom.parse_bom(payload, "bom.csv")
                self.assertEqual(result["status"], "fail")
                self.assertIn("bom.empty", rule_ids(result, "fail"))

    def test_row_limit_is_unknown_not_silent(self):
        result = parse_bom_text(support.bom_text(support.default_bom_rows()),
                                {"max_rows": 2})
        self.assertEqual(result["status"], "unknown")
        self.assertIn("bom.limit_rows", rule_ids(result, "unknown"))
        self.assertTrue(result["facts"]["rows_truncated"])
        self.assertEqual(result["facts"]["counts"]["rows"], 2)

    def test_declared_delimiter(self):
        text = support.bom_text(support.default_bom_rows(), delimiter=";")
        result = parse_bom_text(text, {"delimiter": ";"})
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["facts"]["delimiter"], ";")
        self.assertEqual(result["facts"]["delimiter_source"], "declared")

    def test_sniffed_delimiters(self):
        cases = ((";", support.bom_text(support.default_bom_rows(),
                                        delimiter=";")),
                 ("\t", support.bom_text(support.default_bom_rows(),
                                         delimiter="\t")))
        for expected, text in cases:
            with self.subTest(delimiter=expected):
                result = parse_bom_text(text)
                self.assertEqual(result["status"], "pass")
                self.assertEqual(result["facts"]["delimiter"], expected)
                self.assertEqual(result["facts"]["delimiter_source"], "sniffed")

    def test_ambiguous_delimiter_is_unknown(self):
        text = "Designator,Quantity;DNP\nR1,1;1\n"
        result = parse_bom_text(text)
        self.assertEqual(result["facts"]["delimiter"], ",")
        self.assertIn("bom.delimiter_ambiguous", rule_ids(result, "unknown"))

    def test_non_bytes_payload_raises(self):
        with self.assertRaises(ValueError):
            bom.parse_bom("not-bytes", "bom.csv")

    def test_options_must_be_mapping(self):
        with self.assertRaises(ValueError):
            bom.parse_bom(b"", "bom.csv", [])

    def test_capability_lists(self):
        capability = parse_bom_text(
            support.bom_text(support.default_bom_rows()))["capability"]
        self.assertIn("csv_quotes_newlines", capability["supported"])
        self.assertIn("vendor_complex_designator_formats",
                      capability["unsupported"])
        self.assertIsInstance(capability["unknown"], list)


class CplParserTests(unittest.TestCase):
    maxDiff = None

    def test_legal_cpl_passes_with_declared_unit(self):
        result = parse_cpl_text(support.cpl_text(support.default_cpl_rows()),
                                {"unit": "mm"})
        self.assertEqual(result["kind"], "cpl")
        self.assertEqual(result["file"], "cpl.csv")
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["findings"], [])
        facts = result["facts"]
        self.assertEqual(facts["delimiter"], ",")
        self.assertEqual(facts["units"], "mm")
        self.assertEqual(facts["unit_source"], "declared")
        self.assertEqual(len(facts["rows"]), 4)
        first = facts["rows"][0]
        self.assertEqual(first["designator"], "R1")
        self.assertEqual(first["x"], 10.0)
        self.assertEqual(first["x_mm"], 10.0)
        self.assertEqual(first["side"], "top")
        self.assertEqual(first["rotation"], 0.0)
        self.assertEqual(first["rotation_norm"], 0.0)
        self.assertEqual(facts["counts"]["sides"]["top"], 4)

    def test_utf8_bom_bytes_decoded(self):
        data = support.cpl_text(support.default_cpl_rows()).encode("utf-8-sig")
        result = cpl.parse_cpl(data, "cpl.csv", {"unit": "mm"})
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["facts"]["encoding"], "utf-8-sig")

    def test_wrong_encoding_bytes_are_not_replaced(self):
        data = support.cpl_text(support.default_cpl_rows()).encode("utf-16")
        result = cpl.parse_cpl(data, "cpl.csv", {"unit": "mm"})
        self.assertEqual(result["status"], "fail")
        self.assertIn("cpl.encoding_unspecified", rule_ids(result, "fail"))
        self.assertNotIn("\ufffd", repr(result))

    def test_header_unit_mm(self):
        header = ["Designator", "X(mm)", "Y(mm)", "Side", "Rotation"]
        rows = [{"Designator": "R1", "X(mm)": "10", "Y(mm)": "20",
                 "Side": "Top", "Rotation": "0"}]
        result = parse_cpl_text(support.cpl_text(rows, header=header))
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["facts"]["units"], "mm")
        self.assertEqual(result["facts"]["unit_source"], "header")
        self.assertEqual(result["facts"]["rows"][0]["x_mm"], 10.0)

    def test_mil_conversion(self):
        header = ["Designator", "X(mil)", "Y(mil)", "Side", "Rotation"]
        rows = [{"Designator": "R1", "X(mil)": "100", "Y(mil)": "50",
                 "Side": "Top", "Rotation": "0"}]
        result = parse_cpl_text(support.cpl_text(rows, header=header))
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["facts"]["units"], "mil")
        self.assertAlmostEqual(result["facts"]["rows"][0]["x_mm"], 2.54, places=9)
        self.assertAlmostEqual(result["facts"]["rows"][0]["y_mm"], 1.27, places=9)

    def test_declared_inch_conversion(self):
        result = parse_cpl_text(
            support.cpl_text([cpl_row("R1", x="2", y="1")]),
            {"unit": "inch"})
        self.assertEqual(result["status"], "pass")
        self.assertAlmostEqual(result["facts"]["rows"][0]["x_mm"], 50.8, places=9)
        self.assertAlmostEqual(result["facts"]["rows"][0]["y_mm"], 25.4, places=9)

    def test_header_unit_wins_over_declared(self):
        header = ["Designator", "X(mm)", "Y(mm)", "Side", "Rotation"]
        rows = [{"Designator": "R1", "X(mm)": "10", "Y(mm)": "10",
                 "Side": "Top", "Rotation": "0"}]
        result = parse_cpl_text(support.cpl_text(rows, header=header),
                                {"unit": "inch"})
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["facts"]["unit_source"], "header")
        self.assertAlmostEqual(result["facts"]["rows"][0]["x_mm"], 10.0,
                               places=9)

    def test_unit_column_values(self):
        header = ["Designator", "X", "Y", "Unit", "Side", "Rotation"]
        rows = [{"Designator": "R1", "X": "100", "Y": "100", "Unit": "mil",
                 "Side": "Top", "Rotation": "0"}]
        result = parse_cpl_text(support.cpl_text(rows, header=header))
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["facts"]["units"], "mil")
        self.assertEqual(result["facts"]["unit_source"], "header")
        self.assertAlmostEqual(result["facts"]["rows"][0]["x_mm"], 2.54,
                               places=9)

    def test_unit_missing_is_failure(self):
        result = parse_cpl_text(support.cpl_text(support.default_cpl_rows()))
        self.assertEqual(result["status"], "fail")
        self.assertIn("cpl.unit_missing", rule_ids(result, "fail"))
        self.assertIsNone(result["facts"]["units"])
        self.assertIsNone(result["facts"]["unit_source"])

    def test_unknown_unit_value_is_failure(self):
        header = ["Designator", "X", "Y", "Unit", "Side", "Rotation"]
        rows = [{"Designator": "R1", "X": "10", "Y": "10", "Unit": "cm",
                 "Side": "Top", "Rotation": "0"}]
        result = parse_cpl_text(support.cpl_text(rows, header=header))
        self.assertEqual(result["status"], "fail")
        self.assertIn("cpl.position_unit_unknown", rule_ids(result, "fail"))

    def test_non_numeric_positions_rejected(self):
        bad_values = ("", "NaN", "Infinity", "-inf", "true", "false", "1e",
                      "0x10", "1_000")
        for value in bad_values:
            with self.subTest(value=value):
                result = parse_cpl_text(
                    support.cpl_text([cpl_row("R1", x=value)]),
                    {"unit": "mm"})
                self.assertEqual(result["status"], "fail")
                self.assertIn("cpl.position_not_numeric",
                              rule_ids(result, "fail"))

    def test_non_numeric_y_rejected(self):
        result = parse_cpl_text(
            support.cpl_text([cpl_row("R1", y="NaN")]), {"unit": "mm"})
        self.assertEqual(result["status"], "fail")
        self.assertIn("cpl.position_not_numeric", rule_ids(result, "fail"))

    def test_unknown_side_is_failure(self):
        result = parse_cpl_text(
            support.cpl_text([cpl_row("R1", side="middle")]), {"unit": "mm"})
        self.assertEqual(result["status"], "fail")
        self.assertIn("cpl.side_unknown", rule_ids(result, "fail"))

    def test_side_mapping(self):
        rows = [cpl_row("R1", side="T"), cpl_row("C1", side="B"),
                cpl_row("C2", side="front"), cpl_row("D1", side="back")]
        result = parse_cpl_text(support.cpl_text(rows), {"unit": "mm"})
        self.assertEqual(result["status"], "pass")
        sides = [row["side"] for row in result["facts"]["rows"]]
        self.assertEqual(sides, ["top", "bottom", "top", "bottom"])
        self.assertEqual(result["facts"]["counts"]["sides"]["top"], 2)
        self.assertEqual(result["facts"]["counts"]["sides"]["bottom"], 2)

    def test_missing_side_column_is_failure(self):
        header = ["Designator", "X(mm)", "Y(mm)", "Rotation"]
        rows = [{"Designator": "R1", "X(mm)": "10", "Y(mm)": "10",
                 "Rotation": "0"}]
        result = parse_cpl_text(support.cpl_text(rows, header=header))
        self.assertEqual(result["status"], "fail")
        self.assertIn("cpl.side_missing", rule_ids(result, "fail"))

    def test_rotation_preserved_and_normalized(self):
        rows = [cpl_row("R1", rotation="450"), cpl_row("C1", rotation="-90"),
                cpl_row("C2", rotation="720"), cpl_row("D1", rotation="359.5")]
        result = parse_cpl_text(support.cpl_text(rows), {"unit": "mm"})
        self.assertEqual(result["status"], "pass")
        facts_rows = result["facts"]["rows"]
        self.assertEqual([row["rotation"] for row in facts_rows],
                         [450.0, -90.0, 720.0, 359.5])
        self.assertEqual([row["rotation_norm"] for row in facts_rows],
                         [90.0, 270.0, 0.0, 359.5])
        self.assertEqual(facts_rows[0]["rotation_raw"], "450")

    def test_rotation_missing_column_is_failure(self):
        header = ["Designator", "X(mm)", "Y(mm)", "Side"]
        rows = [{"Designator": "R1", "X(mm)": "10", "Y(mm)": "10",
                 "Side": "Top"}]
        result = parse_cpl_text(support.cpl_text(rows, header=header))
        self.assertEqual(result["status"], "fail")
        self.assertIn("cpl.rotation_not_numeric", rule_ids(result, "fail"))

    def test_rotation_non_numeric_is_failure(self):
        result = parse_cpl_text(
            support.cpl_text([cpl_row("R1", rotation="abc")]), {"unit": "mm"})
        self.assertEqual(result["status"], "fail")
        self.assertIn("cpl.rotation_not_numeric", rule_ids(result, "fail"))

    def test_duplicate_designator(self):
        rows = [cpl_row("R1"), cpl_row("R1", x="11")]
        result = parse_cpl_text(support.cpl_text(rows), {"unit": "mm"})
        self.assertEqual(result["status"], "fail")
        self.assertIn("cpl.designator_duplicate", rule_ids(result, "fail"))

    def test_missing_designator(self):
        result = parse_cpl_text(
            support.cpl_text([cpl_row("")]), {"unit": "mm"})
        self.assertEqual(result["status"], "fail")
        self.assertIn("cpl.designator_missing_invalid",
                      rule_ids(result, "fail"))

    def test_empty_cpl(self):
        for payload in (b"", b"\n  \n"):
            with self.subTest(payload=payload):
                result = cpl.parse_cpl(payload, "cpl.csv")
                self.assertEqual(result["status"], "fail")
                self.assertIn("cpl.empty", rule_ids(result, "fail"))

    def test_no_designator_column(self):
        header = ["X(mm)", "Y(mm)", "Side", "Rotation"]
        rows = [{"X(mm)": "10", "Y(mm)": "10", "Side": "Top", "Rotation": "0"}]
        result = parse_cpl_text(support.cpl_text(rows, header=header))
        self.assertEqual(result["status"], "fail")
        self.assertIn("cpl.no_designator_column", rule_ids(result, "fail"))

    def test_missing_x_column(self):
        header = ["Designator", "Y(mm)", "Side", "Rotation"]
        rows = [{"Designator": "R1", "Y(mm)": "10", "Side": "Top",
                 "Rotation": "0"}]
        result = parse_cpl_text(support.cpl_text(rows, header=header))
        self.assertEqual(result["status"], "fail")
        missing = findings_for(result, "cpl.required_field_missing")
        self.assertEqual([item.get("object") for item in missing], ["x"])

    def test_row_limit_is_unknown_not_silent(self):
        result = parse_cpl_text(support.cpl_text(support.default_cpl_rows()),
                                {"unit": "mm", "max_rows": 2})
        self.assertEqual(result["status"], "unknown")
        self.assertIn("cpl.limit_rows", rule_ids(result, "unknown"))
        self.assertTrue(result["facts"]["rows_truncated"])

    def test_declared_and_sniffed_delimiter(self):
        text = support.cpl_text(support.default_cpl_rows(), delimiter=";")
        declared = parse_cpl_text(text, {"unit": "mm", "delimiter": ";"})
        self.assertEqual(declared["status"], "pass")
        self.assertEqual(declared["facts"]["delimiter"], ";")
        self.assertEqual(declared["facts"]["delimiter_source"], "declared")
        sniffed = parse_cpl_text(text, {"unit": "mm"})
        self.assertEqual(sniffed["status"], "pass")
        self.assertEqual(sniffed["facts"]["delimiter"], ";")
        self.assertEqual(sniffed["facts"]["delimiter_source"], "sniffed")

    def test_negative_coordinates(self):
        result = parse_cpl_text(
            support.cpl_text([cpl_row("R1", x="-5.25", y="-2.5")]),
            {"unit": "mm"})
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["facts"]["rows"][0]["x_mm"], -5.25)

    def test_capability_lists(self):
        capability = parse_cpl_text(
            support.cpl_text(support.default_cpl_rows()),
            {"unit": "mm"})["capability"]
        self.assertIn("unit_mil", capability["supported"])
        self.assertIn("arbitrary_units", capability["unsupported"])


class AssemblyAuditTests(unittest.TestCase):
    maxDiff = None

    def bom_result(self, rows=None, header=None, options=None):
        text = support.bom_text(
            support.default_bom_rows() if rows is None else rows,
            header=header)
        return bom.parse_bom(text.encode("utf-8"), "bom.csv", options)

    def cpl_result(self, rows=None, header=None, options=None):
        text = support.cpl_text(
            support.default_cpl_rows() if rows is None else rows,
            header=header)
        if options is None:
            options = {"unit": "mm"}
        return cpl.parse_cpl(text.encode("utf-8"), "cpl.csv", options)

    def _audit_bom_rows(self):
        return [dict(row) for row in support.default_bom_rows()]

    def test_legal_assembly_passes(self):
        result = assembly.audit_assembly(
            self.bom_result(), self.cpl_result(), declarations(),
            "smt-assembly")
        self.assertEqual(result["kind"], "assembly")
        self.assertEqual(result["files"], ["bom.csv", "cpl.csv"])
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["findings"], [])
        facts = result["facts"]
        self.assertTrue(facts["comparisons"]["performed"])
        self.assertEqual(facts["counts"]["bom_designators"], 5)
        self.assertEqual(facts["counts"]["cpl_designators"], 4)
        self.assertEqual(facts["counts"]["smt_required"], 4)
        self.assertEqual(facts["counts"]["missing_from_cpl"], 0)
        self.assertEqual(facts["counts"]["extra_in_cpl"], 0)
        self.assertEqual(facts["policies"]["dnp_in_cpl"], "forbidden")
        exceptions = {item["kind"] for item in facts["exceptions"]}
        self.assertIn("tht_without_cpl", exceptions)

    def test_declarations_none_is_safe(self):
        result = assembly.audit_assembly(self.bom_result(), self.cpl_result(),
                                         None, "smt-assembly")
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["facts"]["policies"]["tht_requires_cpl"], False)

    def test_cpl_missing_designator(self):
        cpl_rows = [row for row in support.default_cpl_rows()
                    if row["Designator"] != "C2"]
        result = assembly.audit_assembly(self.bom_result(),
                                         self.cpl_result(cpl_rows),
                                         declarations(), "smt-assembly")
        self.assertEqual(result["status"], "fail")
        items = findings_for(result, "assembly.cpl_missing_designator")
        self.assertEqual([item.get("object") for item in items], ["C2"])
        self.assertEqual(items[0]["status"], "fail")
        # Explained by the designator-level finding: no count mismatch.
        self.assertNotIn("assembly.count_mismatch", rule_ids(result))

    def test_cpl_extra_designator(self):
        cpl_rows = support.default_cpl_rows() + [
            {"Designator": "R99", "Mid X": "1", "Mid Y": "1",
             "Layer": "Top", "Rotation": "0"}]
        result = assembly.audit_assembly(self.bom_result(),
                                         self.cpl_result(cpl_rows),
                                         declarations(), "smt-assembly")
        self.assertEqual(result["status"], "fail")
        items = findings_for(result, "assembly.cpl_extra_designator")
        self.assertEqual([item.get("object") for item in items], ["R99"])
        self.assertNotIn("assembly.count_mismatch", rule_ids(result))

    def test_dnp_in_cpl_forbidden_is_failure(self):
        bom_rows = self._audit_bom_rows()
        bom_rows[0]["DNP"] = "1"
        result = assembly.audit_assembly(self.bom_result(bom_rows),
                                         self.cpl_result(), declarations(),
                                         "smt-assembly")
        self.assertEqual(result["status"], "fail")
        items = findings_for(result, "assembly.dnp_in_cpl")
        self.assertEqual([item.get("object") for item in items], ["R1"])
        self.assertTrue(all(item["status"] == "fail" for item in items))
        self.assertNotIn("assembly.count_mismatch", rule_ids(result))

    def test_dnp_in_cpl_allowed_is_info_only(self):
        bom_rows = self._audit_bom_rows()
        bom_rows[0]["DNP"] = "1"
        result = assembly.audit_assembly(
            self.bom_result(bom_rows), self.cpl_result(),
            declarations({"dnp_in_cpl": "allowed"}), "smt-assembly")
        items = findings_for(result, "assembly.dnp_in_cpl")
        self.assertEqual([item["status"] for item in items], ["pass"])
        self.assertEqual([item["severity"] for item in items], ["info"])
        self.assertNotIn("assembly.dnp_in_cpl", rule_ids(result, "fail"))
        self.assertNotIn("assembly.count_mismatch", rule_ids(result))
        self.assertEqual(result["status"], "pass")

    def test_tht_without_cpl_passes(self):
        result = assembly.audit_assembly(
            self.bom_result(), self.cpl_result(),
            declarations({"tht_requires_cpl": False}), "smt-assembly")
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["facts"]["counts"]["tht_designators"], 1)

    def test_tht_in_cpl_is_info_only(self):
        cpl_rows = support.default_cpl_rows() + [
            {"Designator": "J1", "Mid X": "5", "Mid Y": "5",
             "Layer": "Top", "Rotation": "0"}]
        result = assembly.audit_assembly(self.bom_result(),
                                         self.cpl_result(cpl_rows),
                                         declarations(), "smt-assembly")
        items = findings_for(result, "assembly.tht_in_cpl")
        self.assertEqual([item.get("object") for item in items], ["J1"])
        self.assertEqual([item["status"] for item in items], ["pass"])
        self.assertEqual([item["severity"] for item in items], ["info"])
        self.assertNotIn("assembly.cpl_extra_designator", rule_ids(result))
        self.assertNotIn("assembly.count_mismatch", rule_ids(result))
        self.assertEqual(result["status"], "pass")

    def test_tht_requires_cpl_missing_is_failure(self):
        result = assembly.audit_assembly(
            self.bom_result(), self.cpl_result(),
            declarations({"tht_requires_cpl": True}), "smt-assembly")
        self.assertEqual(result["status"], "fail")
        items = findings_for(result, "assembly.cpl_missing_designator")
        self.assertEqual([item.get("object") for item in items], ["J1"])
        self.assertNotIn("assembly.count_mismatch", rule_ids(result))

    def test_mechanical_without_cpl_passes(self):
        bom_rows = self._audit_bom_rows()
        bom_rows[-1]["Assembly"] = "mechanical"
        result = assembly.audit_assembly(self.bom_result(bom_rows),
                                         self.cpl_result(), declarations(),
                                         "smt-assembly")
        self.assertEqual(result["status"], "pass")
        exceptions = {item["kind"] for item in result["facts"]["exceptions"]}
        self.assertIn("mechanical_without_cpl", exceptions)

    def test_mechanical_in_cpl_is_info_only(self):
        bom_rows = self._audit_bom_rows()
        bom_rows[-1]["Assembly"] = "mechanical"
        cpl_rows = support.default_cpl_rows() + [
            {"Designator": "J1", "Mid X": "5", "Mid Y": "5",
             "Layer": "Top", "Rotation": "0"}]
        result = assembly.audit_assembly(self.bom_result(bom_rows),
                                         self.cpl_result(cpl_rows),
                                         declarations(), "smt-assembly")
        items = findings_for(result, "assembly.mechanical_in_cpl")
        self.assertEqual([item.get("object") for item in items], ["J1"])
        self.assertEqual([item["status"] for item in items], ["pass"])
        self.assertEqual(result["status"], "pass")

    def test_side_conflict(self):
        header = list(support.BOM_HEADER) + ["Side"]
        sides = {"R1": "Top", "C1": "Bottom", "C2": "Top", "D1": "Top",
                 "J1": "Top"}
        bom_rows = []
        for row in self._audit_bom_rows():
            if row["Designator"] == "C1,C2":
                for designator in ("C1", "C2"):
                    item = dict(row)
                    item["Designator"] = designator
                    item["Quantity"] = "1"
                    item["Side"] = sides[designator]
                    bom_rows.append(item)
            else:
                row["Side"] = sides[row["Designator"]]
                bom_rows.append(row)
        result = assembly.audit_assembly(self.bom_result(bom_rows, header),
                                         self.cpl_result(), declarations(),
                                         "smt-assembly")
        self.assertEqual(result["status"], "fail")
        items = findings_for(result, "assembly.side_conflict")
        fail_items = [item for item in items if item["status"] == "fail"]
        self.assertEqual([item.get("object") for item in fail_items], ["C1"])
        self.assertNotIn("assembly.count_mismatch", rule_ids(result))

    def test_unusable_bom_skips_cross_check(self):
        bom_result = parse_bom_text(support.bom_text(
            [bom_row("R1"), bom_row("R1")]))
        self.assertEqual(bom_result["status"], "fail")
        result = assembly.audit_assembly(bom_result, self.cpl_result(),
                                         declarations(), "smt-assembly")
        self.assertEqual(result["status"], "fail")
        self.assertIn("assembly.bom_unusable", rule_ids(result, "fail"))
        self.assertFalse(result["facts"]["comparisons"]["performed"])
        self.assertNotIn("assembly.cpl_missing_designator",
                         rule_ids(result))

    def test_unusable_cpl_skips_cross_check(self):
        cpl_result = parse_cpl_text(
            support.cpl_text([cpl_row("R1", x="NaN")]), {"unit": "mm"})
        self.assertEqual(cpl_result["status"], "fail")
        result = assembly.audit_assembly(self.bom_result(), cpl_result,
                                         declarations(), "smt-assembly")
        self.assertEqual(result["status"], "fail")
        self.assertIn("assembly.cpl_unusable", rule_ids(result, "fail"))
        self.assertFalse(result["facts"]["comparisons"]["performed"])

    def test_missing_cpl_result_is_unusable(self):
        result = assembly.audit_assembly(self.bom_result(), None,
                                         declarations(), "smt-assembly")
        self.assertEqual(result["status"], "fail")
        self.assertIn("assembly.cpl_unusable", rule_ids(result, "fail"))
        self.assertFalse(result["facts"]["comparisons"]["performed"])

    def test_missing_assembly_field_is_unknown(self):
        header = [name for name in support.BOM_HEADER if name != "Assembly"]
        bom_rows = self._audit_bom_rows()[:3]  # drop the THT header row
        result = assembly.audit_assembly(self.bom_result(bom_rows, header),
                                         self.cpl_result(), declarations(),
                                         "smt-assembly")
        self.assertEqual(result["status"], "unknown")
        items = findings_for(result, "assembly.assembly_field_missing")
        self.assertEqual([item["status"] for item in items], ["unknown"])
        self.assertTrue(items[0]["evidence"]["column_missing"])
        self.assertEqual(result["facts"]["counts"]["smt_required"], 4)

    def test_unexplained_count_mismatch_is_unknown(self):
        bom_rows = self._audit_bom_rows()
        bom_rows.append(bom_row("H1", Assembly="hand"))
        cpl_rows = support.default_cpl_rows() + [
            {"Designator": "H1", "Mid X": "1", "Mid Y": "1",
             "Layer": "Top", "Rotation": "0"}]
        result = assembly.audit_assembly(self.bom_result(bom_rows),
                                         self.cpl_result(cpl_rows),
                                         declarations(), "smt-assembly")
        self.assertEqual(result["status"], "unknown")
        items = findings_for(result, "assembly.count_mismatch")
        self.assertEqual([item["status"] for item in items], ["unknown"])
        self.assertEqual(items[0]["evidence"]["unexplained_designators"], ["H1"])

    def test_side_uncomparable_is_unknown(self):
        header = list(support.BOM_HEADER) + ["Side"]
        bom_rows = self._audit_bom_rows()
        for row in bom_rows:
            row["Side"] = ""  # column present but unusable
        result = assembly.audit_assembly(self.bom_result(bom_rows, header),
                                         self.cpl_result(), declarations(),
                                         "smt-assembly")
        self.assertEqual(result["status"], "unknown")
        items = findings_for(result, "assembly.side_conflict")
        self.assertEqual([item["status"] for item in items], ["unknown"])

    def test_rejects_non_parse_result(self):
        with self.assertRaises(ValueError):
            assembly.audit_assembly({"kind": "cpl"}, self.cpl_result())

    def test_capability_lists(self):
        result = assembly.audit_assembly(self.bom_result(),
                                         self.cpl_result())
        capability = result["capability"]
        self.assertIn("bom_cpl_designator_match", capability["supported"])
        self.assertIn("coordinate_consistency", capability["unsupported"])


if __name__ == "__main__":
    unittest.main()
