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


def dead_net_snapshot():
    snap = bad_snapshot()
    snap["components"][0]["pins"].append(
        {"number": "9", "name": "SPARE", "net": "ONLY_ME"})
    return snap


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


    def test_net_audit_blocks_and_writes_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp)
            _write(tmp / "snap.json", dead_net_snapshot())
            spec = {"name": "na", "modules": [{"id": "m1", "w": 300, "h": 200}],
                    "snapshot": "snap.json"}
            _write(tmp / "spec.json", spec)
            result = subprocess.run(
                [sys.executable, str(ROOT / "tools" / "pipeline.py"),
                 "--spec", str(tmp / "spec.json"), "--out-dir", str(tmp / "out"),
                 "--net-audit"],
                capture_output=True, text=True, encoding="utf-8", errors="replace")
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("net audit", result.stdout)
            audit = json.loads((tmp / "out" / "na.net-audit.json").read_text(encoding="utf-8"))
            self.assertGreaterEqual(audit["counts"]["errors"], 1)
            self.assertTrue((tmp / "out" / "pipeline-report.json").is_file())


    def test_replay_flag_writes_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp)
            template = {
                "schema": "easycirq-page-template/v1", "page": "x",
                "parts": [{"ref": "U1", "x": 100, "y": 100,
                           "bbox": {"minX": 90, "minY": 90, "maxX": 110, "maxY": 110}}],
                "nets": [{"name": "GND", "members": [["U1", "1"]]}],
            }
            devices = {"U1": {"lib": "lib", "dev": "dev"}}
            _write(tmp / "tpl.json", template)
            _write(tmp / "dev.json", devices)
            _write(tmp / "spec.json", {"name": "rp",
                                       "modules": [{"id": "m1", "w": 300, "h": 200}],
                                       "project_uuid": "p", "page": "pg"})
            result = subprocess.run(
                [sys.executable, str(ROOT / "tools" / "pipeline.py"),
                 "--spec", str(tmp / "spec.json"), "--out-dir", str(tmp / "out"),
                 "--replay", "tpl.json", "--device-map", "dev.json"],
                capture_output=True, text=True, encoding="utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            plan = json.loads((tmp / "out" / "rp.replay-plan.json")
                              .read_text(encoding="utf-8"))
            self.assertEqual(plan["counts"]["parts"], 1)
            self.assertEqual(plan["project"], "p")

    def test_replay_without_device_map_warns(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp)
            _write(tmp / "tpl.json", {"schema": "easycirq-page-template/v1",
                                      "page": "x",
                                      "parts": [{"ref": "U1", "x": 100, "y": 100,
                                                 "bbox": {"minX": 90, "minY": 90,
                                                          "maxX": 110, "maxY": 110}}],
                                      "nets": []})
            _write(tmp / "spec.json", {"name": "rp2",
                                       "modules": [{"id": "m1", "w": 300, "h": 200}]})
            result = subprocess.run(
                [sys.executable, str(ROOT / "tools" / "pipeline.py"),
                 "--spec", str(tmp / "spec.json"), "--out-dir", str(tmp / "out"),
                 "--replay", "tpl.json"],
                capture_output=True, text=True, encoding="utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertFalse((tmp / "out" / "rp2.replay-plan.json").exists())
            report = json.loads((tmp / "out" / "pipeline-report.json")
                                .read_text(encoding="utf-8"))
            self.assertIn("replay plan unavailable", json.dumps(report))


if __name__ == "__main__":
    unittest.main()
