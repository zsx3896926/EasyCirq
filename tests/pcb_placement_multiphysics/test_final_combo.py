"""Tests for P4.16 final recommended-combo snapshot."""

import unittest

from mp_place.final_combo import run


class FinalComboTests(unittest.TestCase):
    def test_quick_structure(self):
        data = run(quick=True, seeds=(0,), steps=120)
        self.assertIn("aggregate", data)
        self.assertIn("template", data["aggregate"])
        self.assertTrue(all(r["feasible"] for r in data["rows"]))

    def test_deterministic(self):
        a = run(quick=True, seeds=(0,), steps=120)
        b = run(quick=True, seeds=(0,), steps=120)
        self.assertEqual(a["aggregate"], b["aggregate"])


if __name__ == "__main__":
    unittest.main()
