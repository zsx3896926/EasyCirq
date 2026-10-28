import copy
import json
import tempfile
import unittest
from pathlib import Path

try:
    from . import helpers
except ImportError:
    import helpers

from annotation_layout.model import Counters, STATUS_PLANNED_CLEAR
from annotation_layout.planner import build_plan, planned_bboxes_from_changes
from annotation_layout.schema import load_input, validate_input
from annotation_layout.solver import solve
from annotation_layout.verify import verify_plan


class SolverTest(unittest.TestCase):
    def test_real_frozen_case_clears_all_three_conflicts(self):
        inp = load_input(helpers.REAL)
        counter = Counters()
        result = solve(inp, counter=counter)
        self.assertEqual(result.status, STATUS_PLANNED_CLEAR)
        self.assertEqual(len(result.hard), 0)
        moved = {identity: (candidate.dx, candidate.dy)
                 for identity, candidate in result.assignment.items()
                 if abs(candidate.dx) > 1e-9 or abs(candidate.dy) > 1e-9}
        self.assertEqual(set(moved), {"8bd5a6b179fa7148", "ad6ce27bf74e95f9"})
        self.assertAlmostEqual(sum(abs(value) for pair in moved.values() for value in pair), 10)
        self.assertGreater(counter.collision_checks, 0)
        self.assertGreater(result.stats.candidates_generated, 0)
        self.assertFalse(result.stats.budget_exhausted)

    def test_deterministic_assignment(self):
        inp = load_input(helpers.REAL)
        first = solve(inp, counter=Counters())
        second = solve(inp, counter=Counters())
        self.assertEqual(
            {key: (value.dx, value.dy, value.rank) for key, value in first.assignment.items()},
            {key: (value.dx, value.dy, value.rank) for key, value in second.assignment.items()})
        self.assertEqual(first.status, second.status)

    def test_noop_on_clean_input(self):
        inp = load_input(helpers.synthetic("clean"))
        result = solve(inp, counter=Counters())
        self.assertTrue(result.noop)
        self.assertEqual(result.status, STATUS_PLANNED_CLEAR)
        self.assertFalse(any(abs(candidate.dx) > 1e-9 or abs(candidate.dy) > 1e-9
                             for candidate in result.assignment.values()))

    def test_replanning_an_accepted_plan_is_a_noop(self):
        path = helpers.synthetic("text-text")
        document = helpers.read_json(path)
        inp = load_input(path)
        plan = build_plan(inp)
        self.assertEqual(plan["status"], "planned_clear")
        applied = helpers.apply_changes(document, plan["changes"])
        validated = validate_input(applied, origin="applied")
        replanned = build_plan(validated)
        self.assertTrue(replanned["noop"])
        self.assertEqual(replanned["changes"], [])
        self.assertEqual(replanned["status"], "planned_clear")

    def test_frozen_annotation_is_not_moved(self):
        inp = load_input(helpers.synthetic("lock-frozen"))
        result = solve(inp, counter=Counters())
        self.assertEqual(result.status, "planned_clear")
        moved = {identity for identity, candidate in result.assignment.items()
                 if abs(candidate.dx) > 1e-9 or abs(candidate.dy) > 1e-9}
        self.assertNotIn("A2", moved)
        self.assertIn("A1", moved)

    def test_scope_restriction_leaves_other_cluster_untouched(self):
        inp = load_input(helpers.synthetic("cluster-a"))
        result = solve(inp, scope_ids=["A1", "A2"], counter=Counters())
        self.assertEqual(result.status, "partial")
        moved = {identity for identity, candidate in result.assignment.items()
                 if abs(candidate.dx) > 1e-9 or abs(candidate.dy) > 1e-9}
        self.assertTrue(moved <= {"A1", "A2"})
        self.assertTrue(any("A3" in item.annotation_ids for item in result.hard))

    def test_budget_exhaustion_is_reported_not_infeasible(self):
        inp = load_input(helpers.synthetic("budget-exhausted"))
        result = solve(inp, counter=Counters())
        self.assertEqual(result.status, "partial")
        self.assertTrue(result.stats.budget_exhausted)
        self.assertEqual(result.stats.budget_kind, "max_search_states")
        self.assertTrue(result.hard)
        self.assertTrue(result.reasons["per_annotation"])

    def test_candidates_rejected_is_distinct_from_no_candidates(self):
        inp = load_input(helpers.synthetic("no-candidates"))
        result = solve(inp, counter=Counters())
        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.reasons["per_annotation"]["A1"]["reason"],
                         "all_candidates_rejected")

    def test_net_label_anchor_separation_unsupported(self):
        inp = load_input(helpers.synthetic("net-anchor"))
        result = solve(inp, counter=Counters())
        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.reasons["unsupported"], ["A1"])
        self.assertEqual(result.reasons["per_annotation"]["A1"]["reason"],
                         "host_capability_unsupported")

    def test_estimated_bbox_never_claims_plan_verified(self):
        inp = load_input(helpers.synthetic("estimated"))
        plan = build_plan(inp)
        self.assertEqual(plan["status"], "partial")
        self.assertEqual(plan["verification"]["status"], "candidate_needs_visual_review")
        self.assertEqual(plan["verification"]["checks"]["estimated_moved"], ["A1"])
        self.assertNotEqual(plan["verification"]["status"], "plan_verified")

    def test_title_block_escape(self):
        inp = load_input(helpers.synthetic("title-block"))
        plan = build_plan(inp)
        self.assertEqual(plan["status"], "planned_clear")
        self.assertEqual(plan["verification"]["status"], "plan_verified")
        self.assertGreaterEqual(plan["metrics"]["moved_annotations"], 1)

    def test_real_plan_binds_input_and_builds_expected_changes(self):
        inp = load_input(helpers.REAL)
        plan = build_plan(inp)
        self.assertEqual(plan["input"]["canonical_sha256"], inp.canonical_sha256)
        self.assertEqual(plan["status"], "planned_clear")
        self.assertEqual(plan["metrics"]["changes"], 2)
        for change in plan["changes"]:
            self.assertEqual(change["protected"]["content"], "unchanged")
            self.assertEqual(change["protected"]["net"], "unchanged")
            self.assertEqual(change["before"]["rotation_deg"],
                             change["after"]["rotation_deg"])
            self.assertEqual(change["before"]["font_size"], change["after"]["font_size"])
        planned = planned_bboxes_from_changes(inp, plan["changes"])
        self.assertEqual(planned["8bd5a6b179fa7148"].y0, 343.0)
        self.assertEqual(planned["ad6ce27bf74e95f9"].y0, 764.5)


if __name__ == "__main__":
    unittest.main()
