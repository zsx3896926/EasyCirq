import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "easycirq" / "scripts" / "design_inventory.py"


def write(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def eda(parts):
    return {"result": {"components": [
        {"componentType": "part", "designator": ref,
         "pins": [{"pinNumber": "1", "net": net}]}
        for ref, net in parts
    ]}}


class DesignInventoryCli(unittest.TestCase):
    def run_tool(self, design, eda_files, checks=None):
        with tempfile.TemporaryDirectory(prefix="design-inventory-") as tmp:
            tmp = Path(tmp)
            write(tmp / "design.json", design)
            args = [sys.executable, str(SCRIPT), "--design", str(tmp / "design.json")]
            for page, data in eda_files.items():
                path = tmp / f"{page}.json"
                write(path, data)
                args += ["--eda", f"{page}={path}"]
            for page, data in (checks or {}).items():
                path = tmp / f"check-{page}.json"
                write(path, data)
                args += ["--check", f"{page}={path}"]
            proc = subprocess.run(args, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", timeout=60)
            return proc, json.loads(proc.stdout)

    def test_complete_page_passes(self):
        design = {"parts": [
            {"ref": "R1", "page": "P1", "value": "1k"},
            {"ref": "R2", "page": "P1", "value": "2k"},
        ]}
        proc, report = self.run_tool(design, {"P1": eda([("R1", "A"), ("R2", "B")])})
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertEqual(report["totals"]["missing_parts"], 0)
        self.assertEqual(report["pages"][0]["status"], "complete")
        self.assertEqual(report["pages"][0]["nets"], 2)

    def test_missing_extra_and_unplanned_pages(self):
        design = {"parts": [
            {"ref": "R1", "page": "P1"},
            {"ref": "R2", "page": "P1"},
            {"ref": "R3", "page": "P2"},
        ]}
        proc, report = self.run_tool(design, {
            "P1": eda([("R1", "A")]),
            "P2": eda([("R3", "C"), ("R9", "D")]),
            "P3": eda([("R9", "E")]),
        })
        self.assertEqual(proc.returncode, 1)
        p1 = next(row for row in report["pages"] if row["page"] == "P1")
        p2 = next(row for row in report["pages"] if row["page"] == "P2")
        p3 = next(row for row in report["pages"] if row["page"] == "P3")
        self.assertEqual(p1["missing_refs"], ["R2"])
        self.assertEqual(p2["extra_refs"], ["R9"])
        self.assertEqual(p3["status"], "unplanned")
        self.assertEqual(report["totals"]["missing_parts"], 1)
        self.assertEqual(report["totals"]["extra_parts"], 2)

    def test_blank_planned_page_and_native_check(self):
        design = {"parts": [{"ref": "R1", "page": "P1"}]}
        check = {"result": {"findings": [
            {"type": "floating-pin"}, {"type": "marker-overlap"}]}}
        proc, report = self.run_tool(
            design,
            {"P1": {"result": {"components": []}}, "P2": eda([("R1", "A")])},
            checks={"P2": check},
        )
        self.assertEqual(proc.returncode, 1)
        p1 = next(row for row in report["pages"] if row["page"] == "P1")
        p2 = next(row for row in report["pages"] if row["page"] == "P2")
        self.assertEqual(p1["status"], "blank")
        self.assertEqual(p2["native_check"]["floating_pins"], 1)
        self.assertEqual(p2["native_check"]["by_type"]["marker-overlap"], 1)

    def test_duplicate_ref_is_invalid(self):
        design = {"parts": [
            {"ref": "R1", "page": "P1"},
            {"ref": "R1", "page": "P1"},
        ]}
        proc, report = self.run_tool(design, {"P1": eda([("R1", "A")])})
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(report["status"], "invalid_input")


if __name__ == "__main__":
    unittest.main()
