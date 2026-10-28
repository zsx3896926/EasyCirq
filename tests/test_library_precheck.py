import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "easycirq" / "scripts" / "library_precheck.py"


def write(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def part(ref, **overrides):
    value = {
        "ref": ref, "page": "P1", "value": "10k", "package": "0603",
        "mpn": "RC0603FR-0710KL", "lcsc": "C25804",
        "lib": "lib-1", "dev": "dev-1",
    }
    value.update(overrides)
    return value


def devices(*entries):
    return {entry.get("deviceUuid", f"dev-{index}"): {"deviceUuid": entry.get("deviceUuid", f"dev-{index}"),
                                                      "lcsc": entry.get("lcsc", "C25804"),
                                                      "package": entry.get("package", "0603")}
            for index, entry in enumerate(entries)}


class LibraryPrecheckCli(unittest.TestCase):
    def run_tool(self, parts, device_table=None, strict=False):
        with tempfile.TemporaryDirectory(prefix="library-precheck-") as tmp:
            tmp = Path(tmp)
            write(tmp / "design.json", {"parts": parts})
            args = [sys.executable, str(SCRIPT), "--design", str(tmp / "design.json")]
            if device_table is not None:
                write(tmp / "devices.json", device_table)
                args += ["--devices", str(tmp / "devices.json")]
            if strict:
                args.append("--strict")
            proc = subprocess.run(args, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", timeout=60)
            return proc, json.loads(proc.stdout)

    def test_complete_parts_pass(self):
        proc, report = self.run_tool(
            [part("R1"), part("R2", dev="dev-2")],
            devices({"deviceUuid": "dev-1", "lcsc": "C25804"},
                    {"deviceUuid": "dev-2", "lcsc": "C25804"}),
        )
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["summary"]["parts"], 2)
        self.assertEqual(report["summary"]["device_identities"], 2)

    def test_missing_lcsc_blocks(self):
        proc, report = self.run_tool([part("R1", lcsc=None)])
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(report["status"], "blocking")
        self.assertIn("missing_lcsc", {f["code"] for f in report["findings"]})

    def test_declared_non_lcsc_is_warning(self):
        proc, report = self.run_tool(
            [part("R1", lcsc={"status": "non_lcsc", "note": "module"})])
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertEqual(report["status"], "warning")
        self.assertIn("non_lcsc_declared", {f["code"] for f in report["findings"]})
        strict, strict_report = self.run_tool(
            [part("R1", lcsc={"status": "non_lcsc", "note": "module"})], strict=True)
        self.assertEqual(strict.returncode, 1)
        self.assertEqual(strict_report["status"], "warning")

    def test_identity_not_in_table_blocks(self):
        proc, report = self.run_tool(
            [part("R1", dev="dev-unknown")],
            devices({"deviceUuid": "dev-1"}),
        )
        self.assertEqual(proc.returncode, 1)
        self.assertIn("identity_not_in_table", {f["code"] for f in report["findings"]})

    def test_same_device_different_package_blocks(self):
        proc, report = self.run_tool([
            part("R1", package="0603"),
            part("R2", package="0805"),
        ])
        self.assertEqual(proc.returncode, 1)
        self.assertIn("device_identity_conflict", {f["code"] for f in report["findings"]})

    def test_duplicate_ref_is_invalid(self):
        proc, report = self.run_tool([part("R1"), part("R1")])
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(report["status"], "invalid_input")


if __name__ == "__main__":
    unittest.main()
