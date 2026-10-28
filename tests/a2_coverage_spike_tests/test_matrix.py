"""Matrix generation tests: measured facts, JSON/Markdown consistency, outputs."""

from __future__ import annotations

import json
import unittest

from . import _bootstrap

import build_matrix
import workflows

REPO = _bootstrap.REPO_ROOT
DOCS = _bootstrap.DOCS_DIR


class MatrixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.assessments, cls.measured, cls.problems = build_matrix.load_all("2026-10-28")
        cls.cells = {
            wf["id"]: {
                "official": wf["official"]["status"],
                "a": wf["a"]["status"],
                "verdict": wf["verdict"],
            }
            for wf in cls.assessments["workflows"]
        }
        cls.rubric = build_matrix.evaluate_rubric(cls.cells)
        cls.matrix = build_matrix.build_matrix(cls.assessments, cls.measured, cls.rubric)
        cls.markdown = build_matrix.render_markdown(cls.matrix)

    def test_assessment_validation_passes(self):
        self.assertEqual(self.problems, [])

    def test_measured_extraction_has_real_runs(self):
        self.assertGreaterEqual(self.measured["W01"]["steps"], 5)
        self.assertGreater(self.measured["W01"]["js_lines"], 0)
        self.assertGreater(self.measured["W02"]["js_lines"], 0)
        self.assertGreaterEqual(self.measured["W11"]["steps"], 3)
        self.assertGreaterEqual(self.measured["W04"]["steps"], 5)
        self.assertGreater(self.measured["W04"]["js_lines"], 0)
        self.assertGreaterEqual(self.measured["W05"]["steps"], 1)
        self.assertGreater(self.measured["W05"]["js_lines"], 0)
        self.assertGreaterEqual(self.measured["W09"]["steps"], 3)

    def test_w10_exit_codes_show_failures(self):
        self.assertIn(1, self.measured["W10"]["exit_codes"])
        self.assertIn(3, self.measured["W10"]["exit_codes"])

    def test_matrix_shape(self):
        self.assertEqual(self.matrix["schema"], "zhigou.a2-coverage.matrix/v1")
        self.assertEqual(len(self.matrix["workflows"]), 11)
        self.assertEqual(len(self.matrix["summary"]), 11)
        self.assertEqual(self.matrix["evidence_date"], "2026-10-28")
        self.assertIn("rubric", self.matrix)
        for wid in workflows.WORKFLOW_IDS:
            row = next(r for r in self.matrix["workflows"] if r["id"] == wid)
            self.assertIn("official", row)
            self.assertIn("a", row)
            self.assertIn("verdict", row)
            self.assertIn(row["official"]["evidence_scope"], {"real-run", "static-catalog"})

    def test_evidence_scope_classification(self):
        scopes = {r["id"]: r["official"]["evidence_scope"] for r in self.matrix["workflows"]}
        self.assertEqual(scopes["W01"], "real-run")
        self.assertEqual(scopes["W04"], "real-run")
        self.assertEqual(scopes["W05"], "real-run")
        self.assertEqual(scopes["W08"], "real-run")
        self.assertEqual(scopes["W09"], "real-run")
        self.assertEqual(scopes["W11"], "real-run")

    def test_markdown_contains_every_row_and_status(self):
        self.assertIn("| ID | workflow | official | A | critical | verdict |", self.markdown)
        for row in self.matrix["workflows"]:
            self.assertIn(f"| {row['id']} |", self.markdown)
            self.assertIn(f"**{row['official']['status']}**", self.markdown)

    def test_json_markdown_consistency(self):
        matrix_json = json.loads((DOCS / "coverage-matrix.json").read_text(encoding="utf-8"))
        md = (DOCS / "coverage-matrix.md").read_text(encoding="utf-8")
        self.assertEqual([r["id"] for r in matrix_json["workflows"]], list(workflows.WORKFLOW_IDS))
        for row in matrix_json["workflows"]:
            self.assertIn(row["id"], md)
            self.assertIn(row["verdict"], md)

    def test_write_outputs_creates_receipts(self):
        build_matrix.write_outputs(self.assessments, self.measured)
        self.assertTrue((DOCS / "coverage-matrix.json").is_file())
        self.assertTrue((DOCS / "coverage-matrix.md").is_file())
        self.assertTrue((DOCS / "rubric.json").is_file())
        for wid in workflows.WORKFLOW_IDS:
            for suffix in ("official", "a"):
                path = _bootstrap.EVIDENCE_DIR / f"{wid}-{suffix}.json"
                self.assertTrue(path.is_file(), path)
                payload = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(payload["schema"], "zhigou.a2-coverage.workflow-cell/v1")
                self.assertEqual(payload["id"], wid)

    def test_current_evidence_is_provisional_with_wrapper_gaps(self):
        rubric = json.loads((DOCS / "rubric.json").read_text(encoding="utf-8"))
        self.assertEqual(rubric["decision"], "incomplete")
        self.assertTrue(rubric["provisional"])
        self.assertEqual(rubric["provisional_lean"], "A2")
        self.assertEqual(rubric["counts"]["unresolved_critical"], [])
        self.assertEqual(set(rubric["counts"]["covered"]), {"W04", "W05", "W08", "W09", "W11"})
        self.assertEqual(set(rubric["counts"]["partial"]), {"W02", "W06", "W07"})

    def test_markdown_has_no_placeholders(self):
        for token in ("TODO", "TBD", "{{", "None"):
            self.assertNotIn(token, self.markdown)


if __name__ == "__main__":
    unittest.main()
