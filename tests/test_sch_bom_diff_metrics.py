import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "easycirq" / "scripts"
DIFF = SCRIPTS / "sch_connectivity_diff.py"
BOM = SCRIPTS / "sch_bom_metrics.py"

sys.path.insert(0, str(SCRIPTS))
import sch_bom_metrics as bom  # noqa: E402
import sch_connectivity_diff as diff  # noqa: E402

IR = {
    "components": [
        {"id": "u1", "ref": "U1", "pins": [{"number": "1"}, {"number": "2"}]},
        {"id": "c1", "ref": "C1", "pins": [{"number": "1"}]},
    ],
    "connections": [
        {"componentId": "u1", "pinNumber": "1", "netId": "n1"},
        {"componentId": "c1", "pinNumber": "1", "netId": "n1"},
        {"componentId": "u1", "pinNumber": "2", "netId": "n2"},
    ],
    "nets": [{"id": "n1", "name": "VCC"}, {"id": "n2", "name": "GND"}],
}

BOM_TSV = "\n".join([
    "No.\tQuantity\tDesignator\tFootprint\tValue\tManufacturer Part\tSupplier Part",
    "1\t1\tU1\tSOT-23\tX\tTPL7407\tC12345",
    "2\t2\tC1,C2\tC0402\t100nF\tCL05B104\tC98765",
]) + "\n"


class ConnectivityDiff(unittest.TestCase):
    def test_identical_snapshots_have_zero_diff(self):
        report = diff.analyze(IR, json.loads(json.dumps(IR)))
        self.assertEqual(report["verdict"], "pass")
        self.assertEqual(report["metrics"]["netlist_diff"], 0)

    def test_single_binding_change_is_counted(self):
        after = json.loads(json.dumps(IR))
        after["connections"][2]["netId"] = "n1"
        report = diff.analyze(IR, after)
        self.assertEqual(report["verdict"], "fail")
        self.assertEqual(report["metrics"]["netlist_diff"], 2)  # -1 removed, +1 added
        codes = {f["code"] for f in report["findings"]}
        self.assertEqual(codes, {"binding_removed", "binding_added"})

    def test_component_removal_is_reported(self):
        after = json.loads(json.dumps(IR))
        after["components"] = after["components"][:1]
        after["connections"] = [c for c in after["connections"]
                                if c["componentId"] != "c1"]
        report = diff.analyze(IR, after)
        self.assertIn("component_removed", {f["code"] for f in report["findings"]})

    def test_metric_name_can_be_readback_diff(self):
        report = diff.analyze(IR, json.loads(json.dumps(IR)),
                              metric_name="readback_diff")
        self.assertIn("readback_diff", report["metrics"])
        self.assertNotIn("netlist_diff", report["metrics"])

    def test_invalid_input(self):
        with self.assertRaises(ValueError):
            diff.analyze({"components": []}, IR)


class BomMetrics(unittest.TestCase):
    def test_complete_bom_passes(self):
        report = bom.analyze(BOM_TSV)
        self.assertEqual(report["verdict"], "pass")
        self.assertEqual(report["metrics"]["bom_mapping_missing"], 0)

    def test_missing_lcsc_is_counted_once_per_row(self):
        text = BOM_TSV.replace("C98765", "")
        report = bom.analyze(text)
        self.assertEqual(report["metrics"]["bom_mapping_missing"], 1)
        self.assertEqual(report["findings"][0]["code"], "lcsc_missing")

    def test_empty_footprint_and_mpn_on_one_row_counts_once(self):
        line = "3\t1\tR1\t\t\t\tC11111"
        report = bom.analyze(BOM_TSV + line + "\n")
        self.assertEqual(report["metrics"]["bom_mapping_missing"], 1)
        codes = {f["code"] for f in report["findings"]}
        self.assertEqual(codes, {"footprint_missing", "mpn_missing"})

    def test_non_c_supplier_part_is_invalid(self):
        report = bom.analyze(BOM_TSV.replace("C12345", "R-123"))
        self.assertEqual(report["metrics"]["bom_mapping_missing"], 1)
        self.assertEqual(report["findings"][0]["code"], "lcsc_invalid")

    def test_unknown_columns_are_unknown_not_pass(self):
        report = bom.analyze("a\tb\n1\t2\n")
        self.assertEqual(report["verdict"], "unknown")

    def test_cli_bom(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "bom.tsv"
            path.write_text(BOM_TSV, encoding="utf-8")
            run = subprocess.run([sys.executable, str(BOM), str(path), "--json"],
                                 capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(run.returncode, 0, run.stderr)

    def test_cli_diff(self):
        with tempfile.TemporaryDirectory() as d:
            before = Path(d) / "before.json"
            after = Path(d) / "after.json"
            before.write_text(json.dumps(IR), encoding="utf-8")
            after.write_text(json.dumps(IR), encoding="utf-8")
            run = subprocess.run([sys.executable, str(DIFF), "--before", str(before),
                                  "--after", str(after), "--json"],
                                 capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(run.returncode, 0, run.stderr)


if __name__ == "__main__":
    unittest.main()
