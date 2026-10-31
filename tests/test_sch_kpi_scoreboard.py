import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "easycirq" / "scripts"
TOOL = SCRIPTS / "sch_kpi_scoreboard.py"

sys.path.insert(0, str(SCRIPTS))
import sch_kpi_scoreboard as board  # noqa: E402


def report(page, verdict="PASS", apply_allowed=True, fails=(), missing=(),
           advisory=()):
    kpis = []
    for index, kpi in enumerate(fails):
        kpis.append({"no": index + 1, "id": kpi, "status": "fail"})
    for index, kpi in enumerate(missing):
        kpis.append({"no": index + 10, "id": kpi, "status": "missing"})
    for index, kpi in enumerate(advisory):
        kpis.append({"no": index + 20, "id": kpi, "status": "fail",
                     "advisory": True})
    kpis.append({"no": 99, "id": "ok", "status": "pass"})
    return {"schema": "easycirq-sch-kpi-report/v1", "project": "P",
            "page": page, "verdict": verdict, "kpis": kpis,
            "blockers": [{"kpi": k} for k in fails],
            "stability": {"apply_allowed": apply_allowed}}


class Scoreboard(unittest.TestCase):
    def test_all_pass_allows_apply(self):
        result = board.summarize([report("P1"), report("P2")], ["P1", "P2"])
        self.assertEqual(result["verdict"], "PASS")
        self.assertTrue(result["can_apply"])

    def test_one_blocked_page_blocks_project(self):
        result = board.summarize([report("P1"),
                                  report("P2", verdict="BLOCKED",
                                         apply_allowed=False,
                                         fails=["unconnected"])])
        self.assertEqual(result["verdict"], "BLOCKED")
        self.assertFalse(result["can_apply"])
        self.assertEqual(result["blocked_pages"], ["P2"])

    def test_missing_expected_page_blocks_apply(self):
        result = board.summarize([report("P1"), report("P2")], ["P1", "P2", "P3"])
        self.assertEqual(result["verdict"], "PASS")
        self.assertFalse(result["can_apply"])
        self.assertEqual(result["absent_pages"], ["P3"])

    def test_advisory_failure_does_not_block(self):
        result = board.summarize([report("P1", advisory=["readability"])], ["P1"])
        self.assertEqual(result["verdict"], "PASS")

    def test_review_when_soft_fails(self):
        result = board.summarize([report("P1", verdict="REVIEW",
                                         apply_allowed=False)], ["P1"])
        self.assertEqual(result["verdict"], "REVIEW")
        self.assertFalse(result["can_apply"])

    def test_duplicate_page_keeps_newest(self):
        older = report("P1", verdict="BLOCKED", apply_allowed=False,
                       fails=["unconnected"])
        older["generatedAt"] = "2026-10-31T10:00:00Z"
        newer = report("P1")
        newer["generatedAt"] = "2026-10-31T11:00:00Z"
        result = board.summarize([older, newer], ["P1"])
        self.assertEqual(result["verdict"], "PASS")
        self.assertEqual(result["duplicates_ignored"], 1)
        self.assertEqual(len(result["pages"]), 1)

    def test_cli_against_directory(self):
        with tempfile.TemporaryDirectory() as d:
            for page in ("P1", "P2"):
                folder = Path(d) / page
                folder.mkdir()
                (folder / "kpi-report.json").write_text(
                    json.dumps(report(page)), encoding="utf-8")
            run = subprocess.run([sys.executable, str(TOOL), "--reports", d,
                                  "--expect-page", "P1", "--expect-page", "P2",
                                  "--json"], capture_output=True, text=True,
                                 encoding="utf-8")
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertTrue(json.loads(run.stdout)["can_apply"])


if __name__ == "__main__":
    unittest.main()
