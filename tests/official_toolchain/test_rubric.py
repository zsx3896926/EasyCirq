"""Rubric tests: every decision branch, including unrun inputs."""

from __future__ import annotations

import unittest

from . import _bootstrap  # noqa: F401

import build_matrix
import workflows


def make_cells(overrides: dict) -> dict:
    cells = {
        wid: {"official": "covered", "a": "static", "verdict": "official_sufficient"}
        for wid in workflows.CRITICAL_IDS
    }
    for wid, status in overrides.items():
        cells[wid]["official"] = status
    return cells


class RubricTests(unittest.TestCase):
    def test_all_critical_covered_is_a2(self):
        rubric = build_matrix.evaluate_rubric(make_cells({}))
        self.assertEqual(rubric["decision"], "A2")
        self.assertFalse(rubric["provisional"])

    def test_w11_unusable_forces_a1(self):
        rubric = build_matrix.evaluate_rubric(make_cells({"W11": "unsupported"}))
        self.assertEqual(rubric["decision"], "A1")
        self.assertFalse(rubric["provisional"])

    def test_blocked_critical_is_incomplete_not_a_guess(self):
        rubric = build_matrix.evaluate_rubric(make_cells({"W04": "blocked", "W05": "blocked"}))
        self.assertEqual(rubric["decision"], "incomplete")
        self.assertTrue(rubric["provisional"])
        self.assertEqual(rubric["counts"]["blocked"], ["W04", "W05"])
        self.assertTrue(any("W04" in item for item in rubric["missing_evidence"]))

    def test_not_run_critical_is_incomplete(self):
        rubric = build_matrix.evaluate_rubric(make_cells({"W09": "not_run"}))
        self.assertEqual(rubric["decision"], "incomplete")
        self.assertTrue(rubric["provisional"])

    def test_one_small_gap_still_a2(self):
        # 8 critical: >=7 covered means at most one gap is tolerated by the rubric.
        rubric = build_matrix.evaluate_rubric(make_cells({"W07": "partial"}))
        self.assertEqual(rubric["decision"], "A2")
        self.assertFalse(rubric["provisional"])

    def test_two_gaps_breaks_a2(self):
        rubric = build_matrix.evaluate_rubric(make_cells({"W07": "partial", "W09": "partial"}))
        self.assertNotEqual(rubric["decision"], "A2")
        self.assertTrue(rubric["provisional"])
        self.assertEqual(rubric["provisional_lean"], "A2")

    def test_covered_below_seven_is_incomplete(self):
        rubric = build_matrix.evaluate_rubric(
            make_cells({"W04": "partial", "W05": "partial", "W09": "partial"})
        )
        self.assertEqual(rubric["decision"], "incomplete")
        self.assertEqual(rubric["provisional_lean"], "A2")
        self.assertLess(len(rubric["counts"]["covered"]), 7)

    def test_rubric_shape_and_condition_keys(self):
        rubric = build_matrix.evaluate_rubric(make_cells({}))
        self.assertEqual(rubric["schema"], "easycirq.a2-coverage.rubric/v1")
        self.assertEqual(rubric["critical_ids"], list(workflows.CRITICAL_IDS))
        for key in ("a2_conditions", "a1_conditions", "a3_conditions"):
            self.assertIn(key, rubric)
            self.assertIsInstance(rubric[key], dict)
        self.assertIn("generated_at", rubric)


if __name__ == "__main__":
    unittest.main()
