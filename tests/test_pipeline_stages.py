"""Tests for pipeline fix-plan / autofix / accept stages (offline)."""

import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def bad_snapshot():
    return {"schema": "easycirq-ace-snapshot/v1", "page": "1",
            "titleblock": {"fields": {"Title": "x", "Rev": "A", "Sheet": "1"}},
            "components": [
                {"ref": "U1", "bbox": {"minX": 100, "minY": 100, "maxX": 160, "maxY": 160},
                 "pins": [{"number": "1", "name": "VDD", "net": "3V3"},
                          {"number": "2", "name": "GND", "net": "GND"}]},
                {"ref": "C1", "bbox": {"minX": 800, "minY": 800, "maxX": 820, "maxY": 820},
                 "pins": [{"number": "1", "name": "1", "net": "3V3"},
                          {"number": "2", "name": "2", "net": "GND"}]},
            ]}


class PipelineStagesTests(unittest.TestCase):
    def test_blocked_plan_writes_fix_plan_and_autofix(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp)
            _write(tmp / "snap.json", bad_snapshot())
            spec = {"name": "st", "modules": [{"id": "m1", "w": 300, "h": 200}],
                    "snapshot": "snap.json"}
            _write(tmp / "spec.json", spec)
            result = subprocess.run(
                [sys.executable, str(ROOT / "tools" / "pipeline.py"),
                 "--spec", str(tmp / "spec.json"), "--out-dir", str(tmp / "out"),
                 "--fix-plan", "--autofix"],
                capture_output=True, text=True, encoding="utf-8", errors="replace")
            self.assertNotEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertTrue((tmp / "out" / "st.fix-plan.json").is_file())
            self.assertTrue((tmp / "out" / "st.autofix.json").is_file())
            report = json.loads((tmp / "out" / "pipeline-report.json").read_text(encoding="utf-8"))
            self.assertIn("st.fix-plan.json", json.dumps(report))

    def test_pass_with_accept_flag_writes_accept(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp)
            # clean snapshot: cap near the IC power pin
            snap = bad_snapshot()
            snap["components"][1]["bbox"] = {"minX": 120, "minY": 120,
                                             "maxX": 140, "maxY": 140}
            _write(tmp / "snap.json", snap)
            spec = {"name": "st2", "modules": [{"id": "m1", "w": 300, "h": 200}],
                    "snapshot": "snap.json", "project_uuid": "p", "page": "pg"}
            _write(tmp / "spec.json", spec)
            result = subprocess.run(
                [sys.executable, str(ROOT / "tools" / "pipeline.py"),
                 "--spec", str(tmp / "spec.json"), "--out-dir", str(tmp / "out"),
                 "--accept"],
                capture_output=True, text=True, encoding="utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue((tmp / "out" / "st2.accept.json").is_file())

    def test_missing_modules_degrades_to_warning(self):
        # no snapshot -> no fix-plan, still exit non-2 on a clean plan
        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp)
            _write(tmp / "spec.json", {"name": "st3",
                                       "modules": [{"id": "m1", "w": 300, "h": 200}]})
            result = subprocess.run(
                [sys.executable, str(ROOT / "tools" / "pipeline.py"),
                 "--spec", str(tmp / "spec.json"), "--out-dir", str(tmp / "out"),
                 "--fix-plan"],
                capture_output=True, text=True, encoding="utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
