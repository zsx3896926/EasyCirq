"""Input contract, safety and demand-expansion CLI tests."""

import copy
import json
import tempfile
import unittest

from . import support as S


class ContractCli(unittest.TestCase):
    maxDiff = None

    def run_input(self, data, *args, name="input.json"):
        tmp = tempfile.TemporaryDirectory(prefix="pp-contract-")
        self.addCleanup(tmp.cleanup)
        path = S.write_input(tmp.name, data, name)
        return (*S.run_cli([*args, "--input", path]), path)

    def simple(self, **overrides):
        row = S.row(line_id="L1", designators=["R1"], mpn="R-10K",
                    qty_per_board=1, lcsc="C1001")
        offer = S.offer(offer_id="OF-1", mpn="R-10K", product_id="C1001",
                        tiers=[{"min_qty": 1, "unit_price": "0.0100"}])
        snap = S.snapshot("SNAP-1")
        values = {"rows": [row], "offers": [offer], "snapshots": [snap]}
        values.update(overrides)
        return S.input_doc(**values)

    def codes(self, report):
        return [finding["code"] for finding in report.get("findings", [])]

    def test_validate_basic_input_is_valid(self):
        proc, report, _ = self.run_input(self.simple(), "validate")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(report["status"], "valid")
        self.assertEqual(report["counts"]["rows"], 1)
        self.assertEqual(report["counts"]["offers"], 1)
        self.assertIn("missing_bom_source_hash", self.codes(report))

    def test_invalid_json_exits_2(self):
        tmp = tempfile.TemporaryDirectory(prefix="pp-json-")
        self.addCleanup(tmp.cleanup)
        path = S.Path(tmp.name) / "bad.json"
        path.write_text("{not json", encoding="utf-8")
        proc, report = S.run_cli(["validate", "--input", str(path)])
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(report["status"], "input_invalid")

    def test_wrong_schema_exits_2(self):
        data = self.simple()
        data["schema"] = "procurement-input/v2"
        proc, report, _ = self.run_input(data, "validate")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("invalid_schema", str(report))

    def test_duplicate_designator_blocks(self):
        data = self.simple()
        data["bom"]["rows"].append(
            S.row(line_id="L2", designators=["R1"], mpn="OTHER",
                  lcsc="C1002"))
        proc, report, _ = self.run_input(data, "validate")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("duplicate_designator", self.codes(report))

    def test_quantity_designator_mismatch_blocks(self):
        data = self.simple()
        data["bom"]["rows"][0]["qty_per_board"] = 2
        proc, report, _ = self.run_input(data, "validate")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("quantity_designator_mismatch", self.codes(report))

    def test_negative_quantity_blocks(self):
        data = self.simple()
        data["bom"]["rows"][0]["qty_per_board"] = -1
        proc, report, _ = self.run_input(data, "validate")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("integer_out_of_range", self.codes(report))

    def test_zero_boards_requires_explicit_policy(self):
        data = self.simple()
        data["project"]["board_quantity"] = 0
        proc, report, _ = self.run_input(data, "demand")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("zero_board_quantity", str(report))
        data["project"]["allow_zero_boards"] = True
        proc, report, _ = self.run_input(data, "demand")
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertEqual(report["counts"]["purchase_need"], 0)
        self.assertEqual(report["demand"][0]["excluded"],
                         "zero_board_quantity")

    def test_float_money_is_rejected(self):
        data = self.simple()
        data["offers"][0]["price_tiers"][0]["unit_price"] = 0.01
        proc, report, _ = self.run_input(data, "validate")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("float_decimal_rejected", self.codes(report))

    def test_bool_and_negative_money_are_rejected(self):
        for value, code in ((True, "float_decimal_rejected"),
                            ("-1.00", "decimal_out_of_range")):
            with self.subTest(value=value):
                data = self.simple()
                data["offers"][0]["price_tiers"][0]["unit_price"] = value
                proc, report, _ = self.run_input(data, "validate")
                self.assertEqual(proc.returncode, 2)
                self.assertIn(code, self.codes(report))

    def test_nan_json_is_rejected(self):
        data = self.simple()
        raw = json.dumps(data).replace('"0.0100"', "NaN")
        tmp = tempfile.TemporaryDirectory(prefix="pp-nan-")
        self.addCleanup(tmp.cleanup)
        path = S.Path(tmp.name) / "nan.json"
        path.write_text(raw, encoding="utf-8")
        proc, report = S.run_cli(["validate", "--input", str(path)])
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(report["status"], "input_invalid")

    def test_reversed_and_overlapping_price_tiers_block(self):
        reversed_tiers = [{"min_qty": 1, "unit_price": "1.00"},
                          {"min_qty": 100, "unit_price": "0.90"},
                          {"min_qty": 50, "unit_price": "0.95"}]
        data = self.simple()
        data["offers"][0]["price_tiers"] = reversed_tiers
        proc, report, _ = self.run_input(data, "validate")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("price_tier_order", self.codes(report))
        data = self.simple()
        data["offers"][0]["price_tiers"] = [
            {"min_qty": 1, "max_qty": 100, "unit_price": "1.00"},
            {"min_qty": 50, "unit_price": "0.90"},
        ]
        proc, report, _ = self.run_input(data, "validate")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("price_tier_overlap", self.codes(report))

    def test_invalid_currency_blocks(self):
        data = self.simple()
        data["offers"][0]["currency"] = "XYZ"
        proc, report, _ = self.run_input(data, "validate")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("invalid_enum", self.codes(report))

    def test_future_snapshot_blocks(self):
        data = self.simple()
        data["supply_snapshots"][0]["captured_at"] = "2026-10-28T08:00:00+08:00"
        proc, report, _ = self.run_input(data, "validate")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("future_timestamp", self.codes(report))

    def test_expired_snapshot_warns_and_is_not_used_for_coverage(self):
        data = self.simple()
        data["supply_snapshots"][0]["captured_at"] = "2026-10-20T08:00:00+08:00"
        data["supply_snapshots"][0]["valid_until"] = "2026-10-21T08:00:00+08:00"
        proc, report, _ = self.run_input(data, "validate")
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("stale_snapshot", self.codes(report))
        proc, report, _ = self.run_input(data, "plan")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(report["status"], "planned_with_unknowns")
        line = report["plan"]["lines"][0]
        self.assertEqual(line["ordered_qty"], 0)
        self.assertEqual(line["status"], "partial_unknown")
        self.assertTrue(any(reason["code"] == "stale_or_untrusted_snapshot"
                            for reason in line["unknown_reasons"]))
        self.assertIn("L1", report["unknowns"]["stale_or_untrusted_lines"])

    def test_bom_source_hash_mismatch_blocks(self):
        data = self.simple()
        data["project"]["bom_source_sha256"] = "0" * 64
        proc, report, _ = self.run_input(data, "validate")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("bom_source_hash_mismatch", self.codes(report))

    def test_as_of_override_replays_freshness(self):
        data = self.simple()
        proc, report, path = self.run_input(
            data, "plan", "--as-of", "2026-10-29T12:00:00+08:00")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(report["evaluation"]["as_of_source"], "cli")
        self.assertEqual(report["status"], "planned_with_unknowns")
        self.assertIn("L1", report["unknowns"]["stale_or_untrusted_lines"])

    def test_same_mpn_different_footprint_offers_warn(self):
        data = self.simple()
        other = copy.deepcopy(data["offers"][0])
        other["offer_id"] = "OF-2"
        other["footprint"] = "R0805"
        data["offers"].append(other)
        proc, report, _ = self.run_input(data, "validate")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("same_mpn_different_footprint_offers",
                      self.codes(report))

    def test_duplicate_offer_id_blocks(self):
        data = self.simple()
        data["offers"].append(copy.deepcopy(data["offers"][0]))
        proc, report, _ = self.run_input(data, "validate")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("duplicate_offer_id", self.codes(report))

    def test_unsafe_line_id_blocks(self):
        data = self.simple()
        data["bom"]["rows"][0]["line_id"] = "../escape"
        proc, report, _ = self.run_input(data, "validate")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("unsafe_identifier", self.codes(report))

    def test_unknown_top_level_key_warns(self):
        data = self.simple()
        data["future_extension"] = {"x": 1}
        proc, report, _ = self.run_input(data, "validate")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("unknown_input_key", self.codes(report))

    def test_strict_promotes_warning_to_blocking(self):
        proc, report, _ = self.run_input(self.simple(), "validate", "--strict")
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(report["status"], "input_invalid")
        self.assertTrue(any(finding.get("promoted")
                            for finding in report["findings"]))

    def test_demand_expansion_exact_numbers(self):
        proc, report = S.run_cli(
            ["demand", "--input", str(S.FIXTURES / "basic.json")])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(report["status"], "valid")
        counts = report["counts"]
        self.assertEqual(counts["assembled_qty"], 70)
        self.assertEqual(counts["spare_qty"], 7)
        self.assertEqual(counts["purchase_need"], 77)
        by_line = {item["line_id"]: item for item in report["demand"]}
        self.assertEqual(by_line["L1"]["purchase_need"], 22)
        self.assertEqual(by_line["L2"]["purchase_need"], 33)
        self.assertEqual(by_line["L5"]["purchase_need"], 0)
        self.assertEqual(by_line["L5"]["excluded"], "dnp")

    def test_output_cannot_overwrite_input(self):
        tmp = tempfile.TemporaryDirectory(prefix="pp-guard-")
        self.addCleanup(tmp.cleanup)
        path = S.write_input(tmp.name, self.simple())
        proc, report = S.run_cli(["plan", "--input", path, "--out", path])
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(report["status"], "input_invalid")
        self.assertIn("output_overwrites_input", str(report))

    def test_help_exits_zero(self):
        proc, report = S.run_cli(["--help"])
        self.assertEqual(proc.returncode, 0)
        self.assertIn("validate", proc.stdout)
        self.assertIn("plan", proc.stdout)


if __name__ == "__main__":
    unittest.main()
