"""Tests for the P2.14 template -> real-board surrogate transfer experiment."""

import unittest

from mp_place.transfer import _fit_affine, _regret, run


class TransferSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = run(n_templates=8, n_boards=40, seed=0)

    def test_report_structure(self):
        self.assertIn("aggregate", self.data)
        self.assertIn("rows", self.data)
        self.assertEqual(len(self.data["rows"]), 3)
        for row in self.data["rows"]:
            self.assertIn("transfer", row)
            self.assertIn("in_domain", row)
            for key in ("r2_10", "r2_40", "spearman_10", "spearman_40",
                        "calibrated_r2_40", "calibrated_spearman_40"):
                self.assertIn(key, row["transfer"])

    def test_deterministic(self):
        again = run(n_templates=8, n_boards=40, seed=0)
        self.assertEqual(again["rows"], self.data["rows"])
        self.assertEqual(again["aggregate"], self.data["aggregate"])

    def test_affine_fit_recovers_scale(self):
        pred = [1.0, 2.0, 3.0, 4.0]
        true = [3.0, 5.0, 7.0, 9.0]  # 2x + 1
        a, b = _fit_affine(pred, true)
        self.assertAlmostEqual(a, 2.0, places=9)
        self.assertAlmostEqual(b, 1.0, places=9)

    def test_regret_non_negative_for_identity(self):
        y = [3.0, 1.0, 2.0, 5.0, 4.0, 0.5]
        self.assertAlmostEqual(_regret(y, y, top=2), 0.0, places=9)


if __name__ == "__main__":
    unittest.main()
