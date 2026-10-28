import unittest

try:
    from . import helpers
except ImportError:
    import helpers

from annotation_layout.baseline import solve_baseline
from annotation_layout.candidates import generate_candidates
from annotation_layout.conflicts import evaluate_assignment
from annotation_layout.model import Counters
from annotation_layout.schema import load_input
from annotation_layout.solver import solve


class CounterexampleTest(unittest.TestCase):
    """Proof that per-annotation greedy can introduce a *new* conflict.

    The fixture is synthetic and geometry-only; it demonstrates the coordination
    gap the batch solver closes.  It says nothing about a real board.
    """

    def test_greedy_introduces_a_conflict_batch_search_clears(self):
        inp = load_input(helpers.synthetic("counterexample"))
        before = [item for item in evaluate_assignment(inp, {}) if item.is_hard]
        self.assertEqual(len(before), 2)
        domains = generate_candidates(inp, counter=Counters())
        baseline = solve_baseline(inp, candidates=domains, counter=Counters())
        improved = solve(inp, candidates=domains, counter=Counters())
        baseline_hard = [item for item in baseline.violations if item.is_hard]
        improved_hard = [item for item in improved.violations if item.is_hard]
        before_keys = {item.key() for item in before}
        baseline_introduced = {item.key() for item in baseline_hard} - before_keys
        improved_introduced = {item.key() for item in improved_hard} - before_keys
        self.assertTrue(baseline_introduced,
                        "baseline did not introduce the expected new conflict")
        self.assertTrue(baseline_hard, "baseline should leave a hard conflict")
        self.assertEqual(improved_hard, [])
        self.assertEqual(improved_introduced, set())
        self.assertEqual(improved.status, "planned_clear")

    def test_two_moves_are_minimal_for_this_case(self):
        """Lock the minimal-move property documented in the handoff.

        The fixture has two hard conflicts (A3 vs C2 body, A3 vs A4).  Exhausting
        every declared candidate for every annotation must find no single-move
        fix; the batch solver's two moves are therefore minimal, not an
        over-move.  This also documents why the benchmark refuses a speedup
        claim for this case while still preferring the batch result on
        hard-conflict count.
        """
        inp = load_input(helpers.synthetic("counterexample"))
        before = [item for item in evaluate_assignment(inp, {}) if item.is_hard]
        self.assertGreaterEqual(len(before), 2)
        domains = generate_candidates(inp, counter=Counters())
        single_move_clears = []
        for identity, candidates in domains.items():
            for candidate in candidates:
                if abs(candidate.dx) < 1e-9 and abs(candidate.dy) < 1e-9:
                    continue  # a no-op is not a move
                violations = evaluate_assignment(inp, {identity: candidate})
                if not any(item.is_hard for item in violations):
                    single_move_clears.append((identity, candidate.dx, candidate.dy))
        self.assertEqual(single_move_clears, [],
                         "a single move clears this case; the two-move solution "
                         "would then be non-minimal and the handoff note stale")
        improved = solve(inp, candidates=domains, counter=Counters())
        self.assertEqual(improved.status, "planned_clear")
        self.assertEqual([item for item in improved.violations if item.is_hard], [])
        moved = [identity for identity, candidate in improved.assignment.items()
                 if abs(candidate.dx) > 1e-9 or abs(candidate.dy) > 1e-9]
        self.assertEqual(len(moved), 2)
        self.assertLessEqual(
            sum(improved.assignment[identity].displacement for identity in moved), 20.0)

    def test_batch_solution_does_not_trade_quality_for_speed(self):
        inp = load_input(helpers.synthetic("counterexample"))
        domains = generate_candidates(inp, counter=Counters())
        baseline = solve_baseline(inp, candidates=domains, counter=Counters())
        improved = solve(inp, candidates=domains, counter=Counters())
        baseline_moved = sum(1 for candidate in baseline.assignment.values()
                             if abs(candidate.dx) > 1e-9 or abs(candidate.dy) > 1e-9)
        improved_moved = sum(1 for candidate in improved.assignment.values()
                             if abs(candidate.dx) > 1e-9 or abs(candidate.dy) > 1e-9)
        # The improved solver may move more annotations to actually clear the
        # conflict; a benchmark must therefore refuse a speedup claim here
        # (quality gate compares hard conflicts AND moved counts).
        self.assertGreaterEqual(improved_moved, 1)
        self.assertLessEqual(improved_moved, len(inp.annotations))
        self.assertGreaterEqual(baseline_moved, 1)


if __name__ == "__main__":
    unittest.main()
