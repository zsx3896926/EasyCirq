"""Tests for P4.13 gates."""

import unittest

from mp_place.gates import run


class GatesTests(unittest.TestCase):
    def test_quick_all_pass(self):
        data = run(quick=True)
        self.assertTrue(data["all_pass"])
        self.assertIn("policy_defaults", data["results"])

    def test_quick_deterministic(self):
        self.assertEqual(run(quick=True)["results"], run(quick=True)["results"])


if __name__ == "__main__":
    unittest.main()
