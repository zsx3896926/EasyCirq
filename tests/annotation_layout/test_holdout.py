import json
import unittest
from pathlib import Path

try:
    from . import helpers
except ImportError:
    import helpers

from annotation_layout.planner import build_plan
from annotation_layout.schema import load_input


class HoldoutTest(unittest.TestCase):
    """Holdout cases authored from scenario design, not back-filled from output."""

    def setUp(self):
        self.expectations = helpers.read_json(helpers.HOLDOUT / "expectations.json")
        self.cases = self.expectations["cases"]

    def test_all_holdouts_meet_authored_bounds(self):
        real = 0
        for name, expected in self.cases.items():
            with self.subTest(case=name):
                path = helpers.holdout(name)
                inp = load_input(path)
                real += 1
                plan = build_plan(inp)
                self.assertIn(plan["status"], expected["acceptable_statuses"])
                self.assertLessEqual(plan["metrics"]["after_hard"],
                                     expected["max_hard_after"])
                self.assertLessEqual(plan["metrics"]["moved_annotations"],
                                     expected["max_moved"])
                self.assertEqual(plan["verification"]["independent"]["introduced_movable"],
                                 [])
                if plan["metrics"]["after_hard"] == 0:
                    self.assertEqual(plan["verification"]["status"], "plan_verified")
        self.assertGreaterEqual(real, 4)

    def test_holdout_unsupported_does_not_move_the_anchor_text(self):
        plan = build_plan(load_input(helpers.holdout("holdout-unsupported")))
        self.assertEqual(plan["metrics"]["changes"], 0)
        self.assertEqual(plan["status"], "blocked")
        self.assertEqual(plan["scope"]["unsupported"], ["A1"])
        self.assertTrue(plan["status_detail"]["remaining_hard"])


if __name__ == "__main__":
    unittest.main()
