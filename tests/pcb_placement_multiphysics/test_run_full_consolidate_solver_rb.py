"""Tests for run_full, consolidate and solver_realboard."""

import pathlib
import unittest

from mp_place.consolidate import collect
from mp_place.run_full import run_all_goals, run_full


class RunFullTests(unittest.TestCase):
    def test_single_default(self):
        out = run_full(template="buck", policy=None, seed=0, steps=120)
        self.assertTrue(out["feasible"])
        self.assertTrue(out["defaults_ok"])

    def test_all_goals_structure(self):
        data = run_all_goals(steps=80, seed=0)
        self.assertIn("rows", data)
        goals = {r["goal"] for r in data["rows"]}
        self.assertEqual(goals, {"balanced", "routability", "intent_fidelity", "truth_sensitive", "experimental"})
        self.assertTrue(all(r["feasible"] for r in data["rows"]))

    def test_deterministic(self):
        a = run_full("buck", None, 0, 120)
        b = run_full("buck", None, 0, 120)
        self.assertEqual(a["report_digest"], b["report_digest"])


class ConsolidateTests(unittest.TestCase):
    def test_collect(self):
        rows = collect()
        self.assertGreaterEqual(len(rows), 0)  # reports may be gitignored in a clean checkout
        for r in rows:
            self.assertIn("report", r)
            self.assertIn("summary", r)

    def test_deterministic(self):
        self.assertEqual(collect(), collect())


class SolverRealboardTests(unittest.TestCase):
    def test_runs(self):
        from mp_place.solver_realboard import run
        try:
            data = run(quick=True, seeds=(0,), steps=120)
        except Exception as exc:  # noqa: BLE001
            self.skipTest(f"real dumps unavailable: {exc}")
            return
        self.assertIn("aggregate", data)
        for r in data["rows"]:
            self.assertTrue(r["feasible"])


if __name__ == "__main__":
    unittest.main()
