"""Frozen holdout combinations with independently hand-calculated expectations."""

import hashlib
import json
import tempfile
import unittest

from . import support as S

HOLDOUTS = S.FIXTURES / "holdout"
EXPECTED = json.loads((HOLDOUTS / "expected.json").read_text(encoding="utf-8"))


class Holdouts(unittest.TestCase):
    maxDiff = None

    def run_case(self, case):
        path = HOLDOUTS / case["input"]
        proc, report = S.run_cli(["plan", "--input", str(path)])
        return proc, report, path

    def test_frozen_input_hashes(self):
        for case in EXPECTED["cases"]:
            with self.subTest(case=case["id"]):
                path = HOLDOUTS / case["input"]
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                self.assertEqual(digest, case["input_sha256"])

    def test_holdout_1_attrition_moq(self):
        case = EXPECTED["cases"][0]
        self.assertEqual(case["id"], "h1")
        proc, report, _ = self.run_case(case)
        self.assertEqual(proc.returncode,
                         0 if case["expected"]["exit_code"] == 0 else 1)
        expected = case["expected"]
        self.assertEqual(report["status"], expected["status"])
        self.assertEqual(report["preferred_strategy"],
                         expected["preferred_strategy"])
        self.assertEqual(report["evaluation"]["as_of"], expected["as_of"])
        line = report["plan"]["lines"][0]
        self.assertEqual(line["demand"]["assembled_qty"],
                         expected["assembled_qty"])
        self.assertEqual(line["demand"]["attrition"]["ratio_spare"],
                         expected["ratio_spare"])
        self.assertEqual(line["demand"]["attrition"]["spare_total"],
                         expected["spare_total"])
        self.assertEqual(line["purchase_need"], expected["purchase_need"])
        self.assertEqual(line["demand"]["consigned_applied"],
                         expected["consigned_applied"])
        self.assertEqual(line["ordered_qty"], expected["ordered_qty"])
        self.assertEqual(line["overbuy_qty"], expected["overbuy_qty"])
        self.assertEqual(line["orders"][0]["line_total"],
                         expected["line_total"])
        self.assertEqual(
            report["plan"]["fees"]["known_total_by_currency"],
            expected["known_fees"])
        self.assertEqual(report["plan"]["budget"]["converted_total"],
                         expected["budget_converted"])
        self.assertEqual(report["plan"]["budget"]["status"],
                         expected["budget_status"])
        self.assertEqual(sorted(report["unknowns"]["synthetic_snapshots"]),
                         sorted(expected["synthetic_snapshots"]))

    def test_holdout_2_shared_pool(self):
        case = EXPECTED["cases"][1]
        proc, report, _ = self.run_case(case)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        expected = case["expected"]
        self.assertEqual(report["status"], expected["status"])
        lines = {line["line_id"]: line for line in report["plan"]["lines"]}
        for line_id, values in expected["lines"].items():
            self.assertEqual(lines[line_id]["ordered_qty"],
                             values["ordered_qty"])
            self.assertEqual(lines[line_id]["shortage_qty"],
                             values["shortage_qty"])
            self.assertEqual(lines[line_id]["status"], values["status"])
        self.assertEqual(report["plan"]["budget"]["converted_total"],
                         expected["budget_converted"])
        self.assertEqual(
            sorted(report["unknowns"]["unknown_stock_lines"]),
            sorted(expected["unknown_stock_lines"]))

    def test_holdout_3_fx(self):
        case = EXPECTED["cases"][2]
        proc, report, _ = self.run_case(case)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        expected = case["expected"]
        self.assertEqual(report["status"], expected["status"])
        order = report["plan"]["orders"][0]
        self.assertEqual(order["offer_id"], expected["offer_id"])
        self.assertEqual(order["qty"], expected["qty"])
        self.assertEqual(order["line_total"], expected["line_total"])
        self.assertEqual(order["currency"], expected["currency"])
        self.assertEqual(report["plan"]["budget"]["converted_total"],
                         expected["budget_converted"])
        self.assertEqual(report["plan"]["budget"]["status"],
                         expected["budget_status"])
        self.assertEqual(report["currency"]["order_currencies"],
                         [expected["currency"]])

    def test_holdout_4_conservative_substitution(self):
        case = EXPECTED["cases"][3]
        proc, report, _ = self.run_case(case)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        expected = case["expected"]
        self.assertEqual(report["status"], expected["status"])
        self.assertEqual(report["preferred_strategy"],
                         expected["preferred_strategy"])
        strategies = {item["strategy"]: item
                      for item in report["strategies"]}
        self.assertEqual(strategies["known_cost"]["status"],
                         expected["known_cost_status"])
        line = report["plan"]["lines"][0]
        self.assertEqual(line["ordered_qty"], expected["ordered_qty"])
        self.assertEqual(line["status"], expected["line_status"])
        order = line["orders"][0]
        self.assertEqual(order["offer_id"], expected["offer_id"])
        self.assertEqual(order["qty"], expected["qty"])
        self.assertEqual(order["line_total"], expected["line_total"])
        self.assertTrue(order["substitution"])
        self.assertEqual(order["alternate_grade"],
                         "evidence_supported_candidate")


if __name__ == "__main__":
    unittest.main()
