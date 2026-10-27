"""Explicit CSV import, report artifacts, determinism and immutability."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from . import support as S


def csv_document():
    doc = S.input_doc(
        rows=[],
        offers=[
            S.offer(offer_id="OF-R", mpn="R-10K", product_id="C1001",
                    tiers=[{"min_qty": 1, "unit_price": "0.0100"}]),
            S.offer(offer_id="OF-C", mpn="C-100N", product_id="C1002",
                    footprint="C0603", manufacturer="MURATA",
                    tiers=[{"min_qty": 1, "unit_price": "0.0200"}]),
        ],
        snapshots=[S.snapshot("SNAP-1")],
        fees=[S.fee("FEE-SHIP", amount="0.00")],
        board=5,
    )
    doc["bom"] = {"revision": "rev-CSV", "source": "EasyEDA-like UTF-16 TSV"}
    return doc


def csv_text():
    return ("No.\tQuantity\tDesignator\tFootprint\tManufacturer Part\t"
            "Manufacturer\tSupplier Part\tSupplier\n"
            "1\t2\tR1,R2\tR0603\tR-10K\tYAGEO\tC1001\tLCSC\n"
            "2\t1\tC1\tC0603\tC-100N\tMURATA\tC1002\tLCSC\n")


def column_map(**overrides):
    mapping = {
        "schema": "procurement-csv-map/v1",
        "encoding": "utf-16",
        "delimiter": "tab",
        "designator_separator": ",",
        "columns": {
            "line_id": "No.",
            "quantity_per_board": "Quantity",
            "designators": "Designator",
            "footprint": "Footprint",
            "mpn": "Manufacturer Part",
            "manufacturer": "Manufacturer",
            "supply_part": "Supplier Part",
            "description": "Supplier",
        },
        "defaults": {"assembly": "smt", "dnp": False},
    }
    mapping.update(overrides)
    return mapping


class CsvAndOutputs(unittest.TestCase):
    maxDiff = None

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="pp-csv-")
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def write(self, name, text, encoding="utf-8"):
        path = self.dir / name
        if encoding == "utf-16":
            path.write_bytes(text.encode("utf-16"))
        else:
            path.write_text(text, encoding=encoding)
        return str(path)

    def run_csv(self, doc=None, mapping=None, bom_text=None, *args):
        input_path = S.write_input(self.tmp.name, doc or csv_document())
        bom_path = self.write("bom.tsv", bom_text or csv_text(),
                              encoding="utf-16")
        map_path = self.write("map.json",
                              json.dumps(mapping or column_map()),
                              encoding="utf-8")
        return S.run_cli([*args, "--input", input_path, "--bom-csv", bom_path,
                          "--column-map", map_path])

    def test_csv_import_expands_utf16_easyda_style_bom(self):
        proc, report = self.run_csv(None, None, None, "demand")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(report["status"], "valid")
        self.assertEqual(report["input"]["bom_csv"]["encoding"], "utf-16")
        self.assertEqual(report["input"]["bom_csv"]["row_count"], 2)
        self.assertEqual(report["counts"]["purchase_need"], 15)
        by_line = {item["line_id"]: item for item in report["demand"]}
        self.assertEqual(by_line["1"]["purchase_need"], 10)
        self.assertEqual(by_line["2"]["purchase_need"], 5)
        self.assertEqual(by_line["1"]["designators"], ["R1", "R2"])

    def test_csv_import_plans_with_offers(self):
        proc, report = self.run_csv(None, None, None, "plan")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(report["status"], "planned_with_unknowns")
        self.assertEqual(report["plan"]["counts"]["orders"], 2)
        self.assertIn("bom_source_sha256_computed", report["project"])

    def test_mapped_header_missing_is_input_invalid(self):
        mapping = column_map()
        mapping["columns"]["mpn"] = "MPN-NOT-THERE"
        proc, report = self.run_csv(None, mapping, None, "validate")
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(report["status"], "input_invalid")
        self.assertIn("mapped_header_missing", str(report))

    def test_csv_quantity_designator_mismatch_blocks(self):
        text = ("No.\tQuantity\tDesignator\tFootprint\t"
                "Manufacturer Part\tManufacturer\tSupplier Part\tSupplier\n"
                "1\t2\tR1\tR0603\tR-10K\tYAGEO\tC1001\tLCSC\n")
        proc, report = self.run_csv(None, None, text, "validate")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("quantity_designator_mismatch", str(report))

    def test_csv_row_limit(self):
        header = ("No.\tQuantity\tDesignator\tFootprint\t"
                  "Manufacturer Part\tManufacturer\tSupplier Part\tSupplier\n")
        rows = []
        for index in range(5001):
            rows.append("%d\t1\tR%d\tR0603\tR-10K\tYAGEO\tC1001\tLCSC\n"
                        % (index + 1, index + 1))
        proc, report = self.run_csv(None, None, header + "".join(rows),
                                    "validate")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("csv_too_many_rows", str(report))

    def test_procurement_csv_is_formula_safe_but_json_keeps_exact_mpn(self):
        doc = S.input_doc(
            rows=[S.row(line_id="L1", designators=["R1"],
                        mpn="=SUM(A1:A2)", manufacturer="YAGEO",
                        footprint="R0603", lcsc="C1")],
            offers=[S.offer(offer_id="OF-1", mpn="=SUM(A1:A2)",
                            product_id="C1")],
            snapshots=[S.snapshot("SNAP-1")],
            fees=[S.fee("FEE-SHIP", amount="0.00")],
            board=2,
        )
        input_path = S.write_input(self.tmp.name, doc)
        csv_path = str(self.dir / "procurement.csv")
        proc, report = S.run_cli(
            ["plan", "--input", input_path, "--procurement-csv", csv_path])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(report["plan"]["lines"][0]["mpn"], "=SUM(A1:A2)")
        text = Path(csv_path).read_text(encoding="utf-8")
        self.assertIn("'=SUM(A1:A2)", text)
        self.assertIn("NOT_ORDER", text)
        self.assertIn("NOT_LIVE_QUOTE", text)
        self.assertIn("real_eda=NOT_RUN", text)

    def test_markdown_and_json_outputs_are_written(self):
        input_path = S.write_input(self.tmp.name, S.base_input())
        out_path = str(self.dir / "plan.json")
        md_path = str(self.dir / "plan.md")
        proc, report = S.run_cli(
            ["plan", "--input", input_path, "--out", out_path,
             "--markdown", md_path])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        written = json.loads(Path(out_path).read_text(encoding="utf-8"))
        report_again = json.loads(proc.stdout)
        self.assertEqual(written["input"]["sha256"],
                         report_again["input"]["sha256"])
        markdown = Path(md_path).read_text(encoding="utf-8")
        self.assertIn("NOT_ORDER", markdown)
        self.assertIn("NOT_LIVE_QUOTE", markdown)
        self.assertIn("real_eda=NOT RUN", markdown)
        self.assertFalse(list(self.dir.glob(".procure-*")))

    def test_plan_is_deterministic_and_does_not_modify_input(self):
        input_path = S.write_input(self.tmp.name, S.base_input())
        before = hashlib.sha256(Path(input_path).read_bytes()).hexdigest()
        first, report_one = S.run_cli(["plan", "--input", input_path])
        second, report_two = S.run_cli(["plan", "--input", input_path])
        after = hashlib.sha256(Path(input_path).read_bytes()).hexdigest()
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        self.assertEqual(second.returncode, 0)
        self.assertEqual(first.stdout, second.stdout)
        self.assertEqual(report_one, report_two)
        self.assertEqual(before, after)

    def test_explain_steps_and_unknown_line(self):
        input_path = S.write_input(self.tmp.name, S.base_input())
        proc, report = S.run_cli(
            ["explain", "--input", input_path, "--line", "L1"])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(len(report["explanations"]), 1)
        explanation = report["explanations"][0]
        self.assertEqual(explanation["demand_chain"]["purchase_need"], 22)
        self.assertEqual(explanation["selected_orders"][0]["offer_id"],
                         "OF-R-MALL")
        self.assertTrue(explanation["offers_considered"])
        self.assertIn("formula", explanation["order_policy"])
        proc, report = S.run_cli(
            ["explain", "--input", input_path, "--line", "NOPE"])
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(report["status"], "input_invalid")
        self.assertIn("unknown_line_id", str(report))

    def test_metamorphic_order_of_rows_and_offers_does_not_change_totals(self):
        doc = S.base_input()
        input_a = S.write_input(self.tmp.name, doc, "a.json")
        proc_a, report_a = S.run_cli(["plan", "--input", input_a])
        doc_reordered = json.loads(json.dumps(doc))
        doc_reordered["bom"]["rows"] = list(
            reversed(doc_reordered["bom"]["rows"]))
        doc_reordered["offers"] = list(reversed(doc_reordered["offers"]))
        input_b = S.write_input(self.tmp.name, doc_reordered, "b.json")
        proc_b, report_b = S.run_cli(["plan", "--input", input_b])
        self.assertEqual(proc_a.returncode, 0)
        self.assertEqual(proc_b.returncode, 0)
        self.assertEqual(report_a["plan"]["counts"],
                         report_b["plan"]["counts"])
        self.assertEqual(report_a["plan"]["fees"]["known_total_by_currency"],
                         report_b["plan"]["fees"]["known_total_by_currency"])
        by_line_a = {line["line_id"]: line["ordered_qty"]
                     for line in report_a["plan"]["lines"]}
        by_line_b = {line["line_id"]: line["ordered_qty"]
                     for line in report_b["plan"]["lines"]}
        self.assertEqual(by_line_a, by_line_b)


if __name__ == "__main__":
    unittest.main()
