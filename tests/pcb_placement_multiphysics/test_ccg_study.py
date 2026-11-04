"""Tests for P4.15 cross-edge CCG study."""

import unittest

from mp_place.ccg_study import cross_edge_scenario, run_study, suggest_mode


class CcgStudyTests(unittest.TestCase):
    def test_cross_edge_scenario_valid(self):
        from mp_place.solver import random_feasible_placement
        import random
        sc = cross_edge_scenario()
        pl = random_feasible_placement(sc, random.Random(0))
        from mp_place.model import hard_violations
        self.assertEqual(hard_violations(sc, pl), [])

    def test_study_has_both_modes(self):
        data = run_study(steps=300)
        self.assertIn("strict", data)
        self.assertIn("relax", data)
        self.assertIn("suggested_mode", data)

    def test_suggest_mode_near_connector(self):
        self.assertEqual(suggest_mode([{"type": "near", "a": "J1", "b": "U2"}]), "relax")
        self.assertEqual(suggest_mode([{"type": "near", "a": "U1", "b": "U2"}]), "strict")


if __name__ == "__main__":
    unittest.main()
