"""Tests for P2.19 combo recommendation hold-out validation."""

import unittest

from mp_place.combo_holdout import HOLDOUT_SEEDS, run


class ComboHoldoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = run(quick=True, seeds=(2,), steps=200)

    def test_structure(self):
        self.assertIn("goals", self.data)
        self.assertIn("rows", self.data)
        for goal in ("completion_first", "zero_router", "cost_first", "truth_first"):
            self.assertIn(goal, self.data["goals"])
            self.assertIn("win_rate", self.data["goals"][goal])

    def test_deterministic(self):
        again = run(quick=True, seeds=(2,), steps=200)
        self.assertEqual(again["goals"], self.data["goals"])

    def test_feasible(self):
        self.assertTrue(all(r["feasible"] for r in self.data["rows"]))

    def test_seeds_are_holdout(self):
        self.assertEqual(tuple(self.data["config"]["seeds"]), (2,))


if __name__ == "__main__":
    unittest.main()
