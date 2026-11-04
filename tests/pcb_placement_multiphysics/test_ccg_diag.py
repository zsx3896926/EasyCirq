"""Tests for P4.14 structured CCG diagnostics."""

import unittest

from mp_place.ccg_diag import diagnose_template, parse_violations


class CcgDiagTests(unittest.TestCase):
    def test_parse(self):
        rows = parse_violations(["ccg-0001:near:U1:U2:3.200>2.500", "ccg-0002:clearance:A:B:1.000<2.000"])
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["type"], "near")
        self.assertEqual(rows[0]["a"], "U1")
        self.assertAlmostEqual(rows[0]["actual"], 3.2)
        self.assertEqual(rows[1]["type"], "clearance")

    def test_parse_raw_fallback(self):
        rows = parse_violations(["malformed"])
        self.assertEqual(rows[0]["raw"], "malformed")

    def test_diagnose_buck(self):
        res = diagnose_template("buck", seed=1, steps=200)
        self.assertIn("ccg_final", res)
        self.assertIsInstance(res["residual"], list)


if __name__ == "__main__":
    unittest.main()
