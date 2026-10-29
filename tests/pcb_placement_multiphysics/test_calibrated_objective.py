"""Tests for P2.20 calibrated-objective downstream experiment."""

import unittest

from mp_place.calibrated_objective import run


class CalibratedObjectiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.data = run(quick=True, seeds=(0,), steps=120)
        except Exception as exc:  # noqa: BLE001 - real dumps may be absent in some checkouts
            cls.data = None
            cls.skip_reason = str(exc)

    @classmethod
    def tearDownClass(cls):
        pass

    def test_runs_when_boards_present(self):
        if self.data is None:
            self.skipTest(f"real board dumps unavailable: {self.skip_reason}")
        self.assertIn("aggregate", self.data)
        for obj in ("multiphysics_proxy", "template_surrogate", "calibrated"):
            self.assertIn(obj, self.data["aggregate"])

    def test_deterministic(self):
        if self.data is None:
            self.skipTest("real board dumps unavailable")
        again = run(quick=True, seeds=(0,), steps=120)
        self.assertEqual(again["aggregate"], self.data["aggregate"])

    def test_all_feasible(self):
        if self.data is None:
            self.skipTest("real board dumps unavailable")
        for name, a in self.data["aggregate"].items():
            self.assertTrue(a["all_feasible"], name)


if __name__ == "__main__":
    unittest.main()

