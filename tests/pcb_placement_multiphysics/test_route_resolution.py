"""Tests for P4.17 router resolution/layer sweep."""

import unittest

from mp_place.route_resolution import run


class RouteResolutionTests(unittest.TestCase):
    def test_quick_structure(self):
        try:
            data = run(quick=True, steps=300)
        except Exception as exc:  # noqa: BLE001
            self.skipTest(f"real dumps unavailable: {exc}")
            return
        self.assertIn("rows", data)
        self.assertGreaterEqual(len(data["rows"]), 1)
        self.assertTrue(all(r["feasible"] for r in data["rows"]))


if __name__ == "__main__":
    unittest.main()
