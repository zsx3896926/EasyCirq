import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "easycirq" / "scripts"
HOOK = SCRIPTS / "sch_delivery_hook.py"
SETTINGS_GEN = SCRIPTS / "sch_task_settings.py"


class StopHook(unittest.TestCase):
    def run_hook(self, evidence, stdin=None):
        r = subprocess.run(
            [sys.executable, str(HOOK), "--evidence", str(evidence)],
            input=stdin, capture_output=True, text=True, encoding="utf-8")
        return r.returncode, r.stdout.strip()

    def test_block_when_evidence_missing(self):
        with tempfile.TemporaryDirectory() as d:
            code, out = self.run_hook(Path(d) / "delivery.json")
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out)["decision"], "block")

    def test_block_when_verdict_not_pass(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "delivery.json"
            p.write_text(json.dumps({"schema": "x", "verdict": "review"}), encoding="utf-8")
            code, out = self.run_hook(p)
            self.assertEqual(json.loads(out)["decision"], "block")

    def test_allow_when_verdict_pass(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "delivery.json"
            p.write_text(json.dumps({"schema": "easycirq-sch-delivery/v1", "verdict": "pass"}), encoding="utf-8")
            code, out = self.run_hook(p)
            self.assertEqual(code, 0)
            self.assertEqual(out, "")

    def test_allow_when_stop_hook_active(self):
        with tempfile.TemporaryDirectory() as d:
            code, out = self.run_hook(Path(d) / "delivery.json",
                                      stdin=json.dumps({"stop_hook_active": True}))
            self.assertEqual(out, "")


class SettingsGen(unittest.TestCase):
    def test_generates_stop_hook(self):
        with tempfile.TemporaryDirectory() as d:
            wd = Path(d)
            r = subprocess.run(
                [sys.executable, str(SETTINGS_GEN), "--workdir", str(wd),
                 "--evidence", "delivery.json", "--out", "settings.json",
                 "--hook-log", "hook.log"],
                capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(r.returncode, 0)
            settings = json.loads((wd / "settings.json").read_text(encoding="utf-8"))
            cmd = settings["hooks"]["Stop"][0]["hooks"][0]["command"]
            self.assertIn("sch_delivery_hook.py", cmd)
            self.assertIn("delivery.json", cmd)
            self.assertIn("hook.log", cmd)
            self.assertEqual(settings["hooks"]["Stop"][0]["hooks"][0]["type"], "command")


if __name__ == "__main__":
    unittest.main()
