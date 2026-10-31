"""Acceptance metrics for the customer experience, measured on real CLI output.

Metric 2 (tool terms the customer must understand), metric 4 (every refusal
carries a next step) and metric 6 (the card never claims more than the
evidence supports) are testable without a physical board: run the installed
CLI and inspect what the customer actually sees.

These tests skip when the easycirq CLI is not on PATH.
"""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
P1_REPORT = ROOT / "reports" / "p1-pipeline" / "kpi-report.json"
EXE = shutil.which("easycirq")

# words a customer must never have to decode (metric 2)
FORBIDDEN = ["daemon", "connector", "typed action", "gate token", "kpi",
             "snapshot", "readback", "typed-action", "gate-token"]
# a refusal without one of these is not explainable (metric 4)
NEXT_MARKERS = ["下一步", "next", "重跑", "重新", "补齐", "修完", "运行 easycirq"]


def run(*args, cwd=None):
    return subprocess.run([EXE, *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", cwd=cwd,
                          timeout=180)


@unittest.skipUnless(EXE, "easycirq CLI not on PATH")
class CustomerTerms(unittest.TestCase):
    def assert_no_jargon(self, text, label):
        lowered = text.lower()
        hits = [word for word in FORBIDDEN if word in lowered]
        self.assertEqual(hits, [], f"{label} leaks jargon: {hits}\n{text}")

    def test_status_uses_no_tool_jargon(self):
        if not P1_REPORT.is_file():
            self.skipTest("no live KPI report")
        result = run("status", "--kpi-report", str(P1_REPORT))
        self.assert_no_jargon(result.stdout, "status")

    def test_card_uses_no_tool_jargon(self):
        if not P1_REPORT.is_file():
            self.skipTest("no live KPI report")
        result = run("card", "--kpi-report", str(P1_REPORT))
        self.assert_no_jargon(result.stdout, "card")

    def test_setup_uses_no_tool_jargon(self):
        result = run("setup")
        self.assert_no_jargon(result.stdout, "setup")


@unittest.skipUnless(EXE, "easycirq CLI not on PATH")
class RefusalsExplainThemselves(unittest.TestCase):
    def assert_has_next(self, text, label):
        self.assertTrue(any(marker in text for marker in NEXT_MARKERS),
                        f"{label} has no next step: {text}")

    def test_status_refusal_has_next(self):
        if not P1_REPORT.is_file():
            self.skipTest("no live KPI report")
        result = run("status", "--kpi-report", str(P1_REPORT))
        if result.returncode == 0:
            self.skipTest("report is PASS, nothing to refuse")
        self.assert_has_next(result.stdout, "status")

    def test_card_refusal_has_next(self):
        if not P1_REPORT.is_file():
            self.skipTest("no live KPI report")
        result = run("card", "--kpi-report", str(P1_REPORT))
        if result.returncode == 0:
            self.skipTest("report is ready, nothing to refuse")
        self.assert_has_next(result.stdout, "card")

    def test_acceptance_with_a_malformed_record_is_explained(self):
        # a silent non-zero exit is not explainable: the customer must be told
        # what is wrong and what to do next
        with tempfile.TemporaryDirectory() as d:
            bad = Path(d) / "bad.json"
            bad.write_text("{ not json", encoding="utf-8")
            result = run("acceptance", "--file", str(bad))
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(result.stdout.strip(), "the failure printed nothing")
            self.assert_has_next(result.stdout, "acceptance(bad)")

    def test_acceptance_without_record_has_next(self):
        with tempfile.TemporaryDirectory() as d:
            result = run("acceptance", "--file", str(Path(d) / "missing.json"))
            self.assertNotEqual(result.returncode, 0)
            self.assert_has_next(result.stdout, "acceptance")


@unittest.skipUnless(EXE, "easycirq CLI not on PATH")
class CardNeverOverclaims(unittest.TestCase):
    def write_report(self, folder, verdict, apply_allowed):
        path = Path(folder) / "kpi.json"
        path.write_text(json.dumps({
            "schema": "easycirq-sch-kpi-report/v1", "project": "P", "page": "P1",
            "verdict": verdict,
            "kpis": [
                {"no": 1, "id": "unconnected", "status": "pass"},
                {"no": 2, "id": "erc", "status": "missing"},
            ],
            "blockers": [{"kpi": "erc", "reason": "缺证据"}],
            "stability": {"apply_allowed": apply_allowed},
        }), encoding="utf-8")
        return path

    def test_pass_verdict_with_missing_evidence_is_not_ready(self):
        # a report that claims PASS while a check has no evidence must not be
        # turned into "can be ordered" by the card
        with tempfile.TemporaryDirectory() as d:
            report = self.write_report(d, "PASS", False)
            result = run("card", "--kpi-report", str(report))
            self.assertNotIn("✅", result.stdout)
            self.assertIn("还不能判断", result.stdout)
            self.assertIn(result.returncode, (1, 2))

    def test_blocked_verdict_is_never_ready(self):
        with tempfile.TemporaryDirectory() as d:
            report = self.write_report(d, "BLOCKED", False)
            result = run("card", "--kpi-report", str(report))
            self.assertNotIn("✅", result.stdout)
            # blocked-by-defect says "还不能打样"; blocked-only-by-evidence says
            # "还不能判断" -- neither may claim ready
            self.assertTrue("还不能打样" in result.stdout
                            or "还不能判断" in result.stdout)
            self.assertIn(result.returncode, (1, 2))


if __name__ == "__main__":
    unittest.main()
