import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "easycirq" / "scripts"
TOOL = SCRIPTS / "sch_drc_metrics.py"

sys.path.insert(0, str(SCRIPTS))
import sch_drc_metrics as tool  # noqa: E402


def drc(fatal=0, error=0, warn=0, violations=None):
    return {"result": {
        "passed": fatal + error == 0, "nativePassed": fatal + error == 0,
        "strict": False, "fatal": fatal,
        "summary": {"fatal": fatal, "error": error, "warn": warn,
                    "info": 0, "unknown": 0,
                    "total": fatal + error + warn},
        "violations": violations or [],
    }}


class DrcMetrics(unittest.TestCase):
    def test_clean_result_passes(self):
        report = tool.analyze(drc())
        self.assertEqual(report["verdict"], "pass")
        self.assertEqual(report["metrics"]["erc_violations"], 0)

    def test_warn_only_is_not_a_hard_violation(self):
        report = tool.analyze(drc(warn=1, violations=[
            {"level": "warn", "rule": "ATTRMATCHCODE"}]))
        self.assertEqual(report["verdict"], "pass")
        self.assertEqual(report["metrics"]["erc_violations"], 0)
        self.assertEqual(report["metrics"]["erc_warn"], 1)
        self.assertEqual(report["findings"][0]["severity"], "warning")

    def test_fatal_and_error_are_hard_violations(self):
        report = tool.analyze(drc(fatal=1, error=2, violations=[
            {"level": "fatal", "rule": "SHORT"},
            {"level": "error", "rule": "MULTIDRIVE"}]))
        self.assertEqual(report["verdict"], "fail")
        self.assertEqual(report["metrics"]["erc_violations"], 3)
        self.assertTrue(all(f["severity"] == "error" for f in report["findings"]))

    def test_bare_result_without_envelope(self):
        payload = {"fatal": 0, "error": 0, "warn": 0, "info": 0, "unknown": 0}
        report = tool.analyze(payload)
        self.assertEqual(report["verdict"], "pass")

    def test_unrecognised_result_is_unknown_not_pass(self):
        report = tool.analyze({})
        self.assertEqual(report["verdict"], "unknown")
        self.assertIsNone(report["metrics"]["erc_violations"])

    def test_cli_exit_codes(self):
        with tempfile.TemporaryDirectory() as d:
            good = Path(d) / "good.json"
            good.write_text(json.dumps(drc()), encoding="utf-8")
            run = subprocess.run([sys.executable, str(TOOL), "--input", str(good),
                                  "--json"], capture_output=True, text=True,
                                 encoding="utf-8")
            self.assertEqual(run.returncode, 0, run.stderr)

            bad = Path(d) / "bad.json"
            bad.write_text(json.dumps(drc(fatal=1)), encoding="utf-8")
            run = subprocess.run([sys.executable, str(TOOL), "--input", str(bad)],
                                 capture_output=True, text=True,
                                 encoding="utf-8")
            self.assertEqual(run.returncode, 1)

            unknown = Path(d) / "unknown.json"
            unknown.write_text("{}", encoding="utf-8")
            run = subprocess.run([sys.executable, str(TOOL), "--input",
                                  str(unknown)], capture_output=True, text=True,
                                 encoding="utf-8")
            self.assertEqual(run.returncode, 2)


if __name__ == "__main__":
    unittest.main()
