import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "easycirq" / "scripts"
TOOL = SCRIPTS / "sch_offline_pipeline.py"
SNAPSHOT = ROOT / "tests" / "fixtures" / "sch-pipeline-p1"


class OfflinePipeline(unittest.TestCase):
    def invoke(self, snapshot, out):
        return subprocess.run(
            [sys.executable, str(TOOL), "--snapshot-dir", str(snapshot),
             "--project", "RetroCam-02", "--page", "P1",
             "--out-dir", str(out), "--json"],
            capture_output=True, text=True, encoding="utf-8")

    def test_missing_connectivity_is_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            snap = Path(d) / "snap"
            snap.mkdir()
            run = self.invoke(snap, Path(d) / "out")
            self.assertEqual(run.returncode, 2)
            summary = json.loads(run.stdout)
            self.assertEqual(summary["verdict"], "BLOCKED")
            self.assertIn("connectivity.json", summary["error"])

    def test_real_snapshot_runs_through_to_kpi_report(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "out"
            run = self.invoke(SNAPSHOT, out)
            self.assertEqual(run.returncode, 2, run.stderr)
            summary = json.loads(run.stdout)
            self.assertEqual(summary["verdict"], "BLOCKED")
            self.assertFalse(summary["apply_allowed"])
            # measured from the frozen snapshot, not invented; the list fixture
            # proves all 11 no-connect pins, so only the single-node net remains
            self.assertEqual(summary["kpi"]["unconnected"]["value"], 1.0)
            self.assertEqual(summary["kpi"]["wire_length"]["status"], "pass")
            self.assertEqual(summary["kpi"]["readback"]["status"], "missing")
            report = json.loads((out / "kpi-report.json").read_text(encoding="utf-8"))
            self.assertEqual(len(report["kpis"]), 16)
            self.assertTrue((out / "kpi-report.md").is_file())
            self.assertTrue((out / "kpi-history.jsonl").is_file())

    def test_second_round_compares_history(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "out"
            self.invoke(SNAPSHOT, out)
            run = self.invoke(SNAPSHOT, out)
            self.assertEqual(run.returncode, 2)
            report = json.loads((out / "kpi-report.json").read_text(encoding="utf-8"))
            self.assertTrue(report["stability"]["history_compared"])
            self.assertFalse(report["stability"]["regression"])

    def test_readback_evidence_is_wired(self):
        # a pre-write read plus a post-reopen read makes KPI 15 measurable;
        # identical reads must give readback_diff=0
        with tempfile.TemporaryDirectory() as d:
            snap = Path(d) / "snap"
            snap.mkdir()
            for name in ("connectivity.json", "list.json", "layout.json"):
                (snap / name).write_bytes((SNAPSHOT / name).read_bytes())
            (snap / "connectivity-reopen.json").write_bytes(
                (SNAPSHOT / "connectivity.json").read_bytes())
            out = Path(d) / "out"
            run = self.invoke(snap, out)
            self.assertEqual(run.returncode, 2)
            summary = json.loads(run.stdout)
            self.assertEqual(summary["kpi"]["readback"]["value"], 0.0)
            self.assertEqual(summary["kpi"]["readback"]["status"], "pass")


if __name__ == "__main__":
    unittest.main()
