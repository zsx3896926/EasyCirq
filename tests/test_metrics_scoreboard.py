import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "metrics_scoreboard.py"


def report(fits=3, blocks=3, overlaps=0, zones_ok=True, export_ok=True,
           wires_total=30, wires_ok=28, project="demo"):
    return {
        "project": project,
        "page": "page-1",
        "blocks": [{"wires": {"total": wires_total, "ok": wires_ok,
                              "failed": wires_total - wires_ok}}],
        "metrics": {"blocks": blocks, "fits": fits, "overlaps": overlaps,
                    "wires_total": wires_total, "wires_ok": wires_ok,
                    "wires_failed": wires_total - wires_ok},
        "zones_reapplied": 0 if zones_ok else 1,
        "export": 0 if export_ok else 1,
    }


class Scoreboard(unittest.TestCase):
    def run_tool(self, reports):
        with tempfile.TemporaryDirectory() as d:
            for i, rep in enumerate(reports):
                (Path(d) / ("r%d.report.json" % i)).write_text(
                    json.dumps(rep), encoding="utf-8")
            out = Path(d) / "scoreboard.json"
            r = subprocess.run([sys.executable, str(TOOL), "--reports", d,
                                "--out", str(out)],
                               capture_output=True, text=True, encoding="utf-8")
            data = json.loads(out.read_text(encoding="utf-8")) if out.exists() else None
            return r.returncode, r.stdout, data

    def test_all_pass(self):
        code, stdout, data = self.run_tool([report(), report(project="demo2")])
        self.assertEqual(code, 0)
        self.assertEqual(data["reports"], 2)
        self.assertEqual(data["passed"], 2)
        self.assertIn("28/30", stdout)

    def test_mixed_review_and_fail_exit(self):
        code, stdout, data = self.run_tool([report(), report(overlaps=2)])
        self.assertEqual(code, 1)
        self.assertEqual(data["passed"], 1)
        self.assertTrue(any(r["verdict"] == "review" for r in data["rows"]))

    def test_fit_shortfall_marks_review(self):
        code, stdout, data = self.run_tool([report(fits=2, blocks=3)])
        self.assertEqual(data["rows"][0]["verdict"], "review")


if __name__ == "__main__":
    unittest.main()
