"""Assessment-source tests: schema, evidence existence, scope honesty, secrets."""

from __future__ import annotations

import json
import re
import unittest

from . import _bootstrap

import workflows

REPO = _bootstrap.REPO_ROOT
ASSESSMENTS = _bootstrap.SPIKE_DIR / "assessments.json"
EVIDENCE = _bootstrap.EVIDENCE_DIR


class AssessmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(ASSESSMENTS.read_text(encoding="utf-8"))
        cls.by_id = {wf["id"]: wf for wf in cls.data["workflows"]}

    def test_schema_and_date(self):
        self.assertEqual(self.data["schema"], "zhigou.a2-coverage.assessments/v1")
        self.assertEqual(self.data["evidence_date"], "2026-10-28")
        self.assertEqual(EVIDENCE.name, "a2-coverage-2026-10-28")

    def test_all_eleven_workflows_in_order(self):
        self.assertEqual([wf["id"] for wf in self.data["workflows"]], list(workflows.WORKFLOW_IDS))

    def test_status_enums_respected(self):
        for wid, wf in self.by_id.items():
            with self.subTest(wid=wid):
                self.assertIn(wf["official"]["status"], workflows.OFFICIAL_STATUSES)
                self.assertIn(wf["a"]["status"], workflows.A_STATUSES)
                self.assertIn(wf["verdict"], workflows.VERDICTS)

    def test_critical_flags_match_definition(self):
        for wid, wf in self.by_id.items():
            self.assertEqual(wf["critical"], wid in workflows.CRITICAL_IDS, wid)

    def test_every_cited_evidence_file_exists(self):
        missing = []
        for wid, wf in self.by_id.items():
            for cell in ("official", "a"):
                for path in wf[cell]["evidence"]:
                    if not (REPO / path).is_file():
                        missing.append(f"{wid}.{cell}: {path}")
        self.assertEqual(missing, [])

    def test_observation_and_risk_fields_non_empty(self):
        for wid, wf in self.by_id.items():
            with self.subTest(wid=wid):
                self.assertGreaterEqual(len(wf["official"]["observations"]), 2)
                self.assertGreaterEqual(len(wf["official"]["risks"]), 1)
                self.assertGreaterEqual(len(wf["a"]["observations"]), 1)
                self.assertGreaterEqual(len(wf["a"]["blockers"]), 1)
                self.assertTrue(wf["notes"].strip())

    def test_write_cells_are_covered_after_authorized_probe(self):
        for wid in ("W04", "W05", "W09"):
            cell = self.by_id[wid]["official"]
            self.assertEqual(cell["status"], "covered", wid)
            self.assertGreater(cell["steps"], 0, wid)
            self.assertTrue(
                any("write-probe" in path or "write-probe-passed" in path for path in cell["evidence"]),
                wid,
            )
        self.assertIn("AUTHORIZED", self.data["isolation"]["design_writes"])
        self.assertTrue(self.data["isolation"]["write_probe"]["source_unchanged"])

    def test_isolation_declaration(self):
        isolation = self.data["isolation"]
        self.assertIs(isolation["user_session_touched"], False)
        self.assertIn("AUTHORIZED", isolation["design_writes"])
        self.assertIs(isolation["project_unchanged_after_probe"], True)
        self.assertIn("quickstart", isolation["fixture_copy"])

    def test_a_side_is_never_marked_covered(self):
        for wid, wf in self.by_id.items():
            self.assertIn(wf["a"]["status"], {"static", "unsupported", "not_run", "blocked"}, wid)

    def test_no_credentials_in_assessments_or_receipts(self):
        patterns = [
            re.compile(r"(?i)authorization\s*:\s*bearer\s+[A-Za-z0-9._\-]{10,}"),
            re.compile(r"(?i)\"(?:token|password|secret|api[_-]?key)\"\s*:\s*\"[^\"]{8,}\""),
        ]
        candidates = [ASSESSMENTS] + sorted((EVIDENCE / "raw").glob("*.json"))
        candidates += sorted((EVIDENCE / "api").glob("*.json"))
        hits = []
        for path in candidates:
            text = path.read_text(encoding="utf-8", errors="replace")
            for pattern in patterns:
                if pattern.search(text):
                    hits.append(str(path))
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
