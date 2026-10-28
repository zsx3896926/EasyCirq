import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

os.environ.setdefault("PYTHONIOENCODING", "utf-8")

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "easycirq" / "scripts" / "bom_check.py"
EXAMPLE = ROOT / "easycirq" / "assets" / "parts.example.json"


def part(**overrides):
    value = {
        "role": "比较器",
        "designators": ["U1"],
        "mpn": "MCP6541T-I/OT",
        "manufacturer": "Microchip",
        "lcsc": "C80839",
        "footprint": "SOT-23-5_L3.0-W1.7-P0.95-LS2.8-BR",
        "package": "SOT-23-5",
        "assembly": "smt",
        "datasheet": "datasheet/MCP6541T-I-OT.pdf",
        "stock": {"status": "in_stock", "qty": 100, "checked_at": "2026-10-24"},
        "smt_class": "extended",
        "alternates": [],
    }
    value.update(overrides)
    return value


def payload(*parts):
    return {"schema": "parts/v1", "project": "unit-test", "parts": list(parts)}


class BomCheckCli(unittest.TestCase):
    maxDiff = None

    def run_path(self, path, args=()):
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), str(path), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        report = None
        if proc.stdout.strip():
            try:
                report = json.loads(proc.stdout)
            except json.JSONDecodeError:
                report = None
        return proc, report

    def run_check(self, data=None, args=(), raw=None):
        with tempfile.TemporaryDirectory(prefix="bom-check-") as tmp:
            path = Path(tmp) / "parts.json"
            if raw is not None:
                path.write_text(raw, encoding="utf-8")
            else:
                path.write_text(json.dumps(data, ensure_ascii=False),
                                encoding="utf-8")
            return self.run_path(path, args)

    def codes(self, report):
        return {finding["code"] for finding in report["findings"]}

    def finding(self, report, code):
        matches = [f for f in report["findings"] if f["code"] == code]
        self.assertEqual(len(matches), 1, "expected one %s in %r"
                         % (code, report["findings"]))
        return matches[0]

    def test_valid_file_passes(self):
        proc, report = self.run_check(payload(part()))
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertEqual(report["schema"], "bom-check/v1")
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["findings"], [])
        self.assertEqual(report["counts"]["designators"], 1)

    def test_shipped_example_runs_with_warnings_only(self):
        proc, report = self.run_path(EXAMPLE)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertEqual(report["status"], "pass")
        self.assertGreater(report["counts"]["warning"], 0)
        self.assertEqual(report["counts"]["dnp_designators"], 1)
        self.assertIn("R18", report["assembly"]["dnp"])
        self.assertNotIn("R18", report["assembly"]["smt"])
        self.assertEqual(report["counts"]["assembly_designators"],
                         report["counts"]["designators"]
                         - report["counts"]["dnp_designators"])

    def test_missing_mpn_blocks(self):
        proc, report = self.run_check(payload(part(mpn="  ")))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("missing_mpn", self.codes(report))

    def test_missing_manufacturer_blocks(self):
        proc, report = self.run_check(payload(part(manufacturer="")))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("missing_manufacturer", self.codes(report))

    def test_placeholder_identity_blocks(self):
        proc, report = self.run_check(payload(part(mpn="TBD")))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("placeholder_mpn", self.codes(report))
        proc, report = self.run_check(payload(part(manufacturer="待核")))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("placeholder_manufacturer", self.codes(report))

    def test_hand_solder_0402_warns_then_blocks_in_strict(self):
        hand = part(designators=["R1"], role="手焊电阻", assembly="hand",
                    package="0402", footprint="R0402")
        proc, report = self.run_check(payload(hand))
        self.assertEqual(proc.returncode, 0, proc.stdout)
        finding = self.finding(report, "hand_solder_0402")
        self.assertEqual(finding["level"], "warning")

        proc, report = self.run_check(payload(hand), args=("--strict",))
        self.assertEqual(proc.returncode, 1)
        finding = self.finding(report, "hand_solder_0402")
        self.assertEqual(finding["level"], "blocking")
        self.assertTrue(finding["promoted"])
        self.assertEqual(report["counts"]["promoted"], report["counts"]["blocking"])

    def test_hand_solder_0201_blocks_without_strict(self):
        hand = part(designators=["R1"], assembly="hand",
                    package="0201", footprint="R0201")
        proc, report = self.run_check(payload(hand))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("unsuitable_hand_solder", self.codes(report))

    def test_smt_without_smt_class_blocks(self):
        smt = part()
        del smt["smt_class"]
        proc, report = self.run_check(payload(smt))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("missing_smt_class", self.codes(report))

    def test_invalid_smt_class_blocks(self):
        proc, report = self.run_check(payload(part(smt_class="golden")))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("invalid_smt_class", self.codes(report))

    def test_duplicate_designator_blocks(self):
        first = part(designators=["R1", "R2"])
        second = part(designators=["R1"], mpn="OTHER", lcsc="C123")
        proc, report = self.run_check(payload(first, second))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("duplicate_designator", self.codes(report))

    def test_missing_designators_blocks(self):
        proc, report = self.run_check(payload(part(designators=[])))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("missing_designators", self.codes(report))

    def test_invalid_json_exits_2(self):
        proc, report = self.run_check(raw="{not json")
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(report["status"], "invalid_input")
        self.assertIn("error", report)

    def test_wrong_schema_exits_2(self):
        data = payload(part())
        data["schema"] = "parts/v2"
        proc, report = self.run_check(data)
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(report["status"], "invalid_input")

    def test_empty_parts_exits_2(self):
        proc, report = self.run_check(payload())
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(report["status"], "invalid_input")

    def test_duplicate_json_key_exits_2(self):
        raw = ('{"schema": "parts/v1", "parts": [], '
               '"parts": []}')
        proc, report = self.run_check(raw=raw)
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(report["status"], "invalid_input")

    def test_dnp_excluded_from_assembly_count(self):
        assembled = part(designators=["R1", "R2"])
        dnp = part(role="可选跳线", designators=["J2"], assembly="dnp",
                   lcsc={"status": "non_lcsc", "note": "自备料"})
        dnp.pop("smt_class")
        dnp.pop("stock")
        proc, report = self.run_check(payload(assembled, dnp))
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertEqual(report["counts"]["parts"], 2)
        self.assertEqual(report["counts"]["designators"], 3)
        self.assertEqual(report["counts"]["assembly_designators"], 2)
        self.assertEqual(report["counts"]["dnp_designators"], 1)
        self.assertEqual(report["assembly"]["smt"], ["R1", "R2"])
        self.assertEqual(report["assembly"]["dnp"], ["J2"])

    def test_out_of_stock_blocks(self):
        stock = {"status": "out_of_stock", "qty": 0, "checked_at": "2026-10-24"}
        proc, report = self.run_check(payload(part(stock=stock)))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("out_of_stock", self.codes(report))

    def test_stock_claim_requires_check_date(self):
        stock = {"status": "in_stock", "qty": 10, "checked_at": None}
        proc, report = self.run_check(payload(part(stock=stock)))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("missing_stock_check_date", self.codes(report))

    def test_unchecked_stock_warns_only(self):
        stock = {"status": "unchecked", "qty": None, "checked_at": None}
        proc, report = self.run_check(payload(part(stock=stock)))
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertEqual(self.finding(report, "stock_unchecked")["level"],
                         "warning")

    def test_lcsc_forms(self):
        cases = [
            ("ABC", 1, "invalid_lcsc"),
            ({"status": "unknown"}, 1, "invalid_lcsc_status"),
            ({"status": "non_lcsc", "note": "自备料"}, 0, None),
        ]
        for lcsc, expected_exit, code in cases:
            with self.subTest(lcsc=lcsc):
                proc, report = self.run_check(payload(part(lcsc=lcsc)))
                self.assertEqual(proc.returncode, expected_exit, proc.stdout)
                if code:
                    self.assertIn(code, self.codes(report))

    def test_lcsc_pending_warns_then_blocks_in_strict(self):
        lcsc = {"status": "pending", "note": "待核"}
        proc, report = self.run_check(payload(part(lcsc=lcsc)))
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertEqual(self.finding(report, "lcsc_pending")["level"],
                         "warning")
        proc, report = self.run_check(payload(part(lcsc=lcsc)),
                                      args=("--strict",))
        self.assertEqual(proc.returncode, 1)

    def test_invalid_assembly_blocks(self):
        proc, report = self.run_check(payload(part(assembly="smd")))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("invalid_assembly", self.codes(report))

    def test_alternates_are_validated(self):
        proc, report = self.run_check(payload(part(alternates="none")))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("invalid_alternates", self.codes(report))

        proc, report = self.run_check(
            payload(part(alternates=[{"mpn": "", "lcsc": "C123"}])))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("alternate_missing_mpn", self.codes(report))

        proc, report = self.run_check(
            payload(part(alternates=[{"mpn": "ALT-1", "lcsc": "C123"}])))
        self.assertEqual(proc.returncode, 0, proc.stdout)

    def test_help_exits_0(self):
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--help"],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=60,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("--strict", proc.stdout)
        self.assertIn("--json", proc.stdout)

    def test_stdout_is_one_json_object(self):
        proc, report = self.run_check(payload(part()))
        self.assertEqual(proc.returncode, 0)
        self.assertTrue(proc.stdout.strip().startswith("{"))
        self.assertEqual(report["schema"], "bom-check/v1")
        self.assertIsInstance(report["findings"], list)
        self.assertIn("not_checked", report)


if __name__ == "__main__":
    unittest.main()
