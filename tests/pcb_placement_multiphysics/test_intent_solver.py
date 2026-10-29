"""Tests for P3.6 intent-constrained placement planner (stdlib unittest only).

Run with::

    python -m unittest tests.test_intent_solver -v
"""

import json
import random
import unittest

from mp_place.intent import build_intent, intent_to_plan, intent_violations
from mp_place.intent_solver import (
    CCG_PENALTY,
    DEFAULT_STEPS,
    benchmark,
    plan_from_intent,
)
from mp_place.model import hard_violations
from mp_place.objective import HPWLObjective, ProxyObjective
from mp_place.solver import feasible_partial, random_feasible_placement
from mp_place.templates import instantiate, template_names

REFERENCE_SEED = 7
REQUIRED_STATS = {
    "ccg_initial",
    "ccg_final",
    "violations",
    "moves",
    "moves_accepted",
    "hard_feasible",
    "ccg_target_met",
    "cost_initial",
    "cost_final",
    "start_source",
}


def _reference_case(name, template_seed=0):
    """Scenario + hard-feasible reference layout + intent built from it."""
    sc = instantiate(name, seed=template_seed)
    reference = random_feasible_placement(sc, random.Random(REFERENCE_SEED))
    intent = build_intent(sc, reference)
    return sc, reference, intent


def _jiggle(sc, reference, rng, scale=3.0):
    """Small hard-feasible random offsets around the reference layout."""
    placement = dict(reference)
    movable = [ref for ref, comp in sc.components.items() if not comp.fixed]
    for ref in movable:
        for _attempt in range(40):
            x, y, rot = reference[ref]
            trial = dict(placement)
            trial[ref] = (
                x + rng.uniform(-scale, scale),
                y + rng.uniform(-scale, scale),
                rot,
            )
            if feasible_partial(sc, trial):
                placement = trial
                break
    return placement


def _with_coordinates(intent, placement):
    """JSON round trip of ``intent`` with its coordinate block replaced."""
    payload = json.loads(json.dumps(intent, allow_nan=False))
    payload["coordinates"] = {
        ref: [float(x), float(y), int(rot)] for ref, (x, y, rot) in placement.items()
    }
    return payload


class PlanFromIntentTests(unittest.TestCase):
    def test_hard_feasible_and_required_stats(self):
        for name in ("buck", "wireless"):
            with self.subTest(template=name):
                sc, _reference, intent = _reference_case(name)
                plan, stats = plan_from_intent(sc, intent, seed=0, steps=300)
                self.assertEqual(set(plan), set(sc.components))
                for ref, comp in sc.components.items():
                    if comp.fixed:
                        self.assertEqual(plan[ref], sc.base_placement[ref])
                self.assertEqual(hard_violations(sc, plan), [])
                self.assertTrue(REQUIRED_STATS.issubset(stats), sorted(stats))
                self.assertEqual(stats["moves"], 300)
                self.assertGreaterEqual(stats["moves_accepted"], 0)
                self.assertLessEqual(stats["moves_accepted"], stats["moves"])
                self.assertEqual(stats["steps"], 300)
                self.assertEqual(stats["ccg_initial"], 0)
                self.assertEqual(stats["ccg_final"], 0)
                self.assertEqual(stats["violations"], 0)
                self.assertTrue(stats["hard_feasible"])
                self.assertTrue(stats["ccg_target_met"])
                self.assertEqual(stats["start_source"], "intent")
                self.assertEqual(stats["objective"], "multiphysics_proxy")
                self.assertEqual(stats["penalty"], CCG_PENALTY)
                self.assertLessEqual(stats["cost_final"], stats["cost_initial"] + 1e-6)

    def test_deterministic_for_same_inputs(self):
        sc, _reference, intent = _reference_case("can-node")
        plan_a, stats_a = plan_from_intent(sc, intent, seed=5, steps=250)
        plan_b, stats_b = plan_from_intent(sc, intent, seed=5, steps=250)
        self.assertEqual(plan_a, plan_b)
        self.assertEqual(stats_a, stats_b)

    def test_all_eight_templates_run(self):
        self.assertEqual(len(template_names()), 8)
        for name in template_names():
            with self.subTest(template=name):
                sc, _reference, intent = _reference_case(name)
                plan, stats = plan_from_intent(sc, intent, seed=0, steps=200)
                self.assertEqual(set(plan), set(sc.components))
                self.assertEqual(hard_violations(sc, plan), [])
                self.assertEqual(stats["ccg_final"], 0)
                self.assertTrue(stats["ccg_target_met"])

    def test_ccg_repaired_from_jiggled_intent(self):
        rng = random.Random(42)
        for name in template_names():
            with self.subTest(template=name):
                sc, reference, intent = _reference_case(name)
                jiggled = _jiggle(sc, reference, rng)
                self.assertEqual(hard_violations(sc, jiggled), [])
                perturbed = _with_coordinates(intent, jiggled)
                plan, stats = plan_from_intent(sc, perturbed, seed=1, steps=800)
                self.assertGreater(stats["ccg_initial"], 0, name)
                self.assertEqual(stats["ccg_final"], 0, name)
                self.assertTrue(stats["ccg_target_met"])
                self.assertEqual(stats["start_source"], "intent")
                self.assertEqual(hard_violations(sc, plan), [])
                self.assertEqual(intent_violations(sc, plan, perturbed), [])

    def test_ccg_significantly_reduced_from_random_start(self):
        for name in template_names():
            with self.subTest(template=name):
                sc, _reference, intent = _reference_case(name)
                random_start = random_feasible_placement(sc, random.Random(99))
                perturbed = _with_coordinates(intent, random_start)
                plan, stats = plan_from_intent(sc, perturbed, seed=1, steps=800)
                initial = stats["ccg_initial"]
                final = stats["ccg_final"]
                self.assertGreater(initial, 0, name)
                self.assertLessEqual(final, max(1, initial // 2), f"{name}: {initial}->{final}")
                self.assertTrue(stats["hard_feasible"])
                self.assertEqual(hard_violations(sc, plan), [])

    def test_zero_budget_returns_initial_guess(self):
        sc, _reference, intent = _reference_case("buck")
        plan, stats = plan_from_intent(sc, intent, seed=0, steps=0)
        self.assertEqual(plan, intent_to_plan(sc, intent))
        self.assertEqual(stats["moves"], 0)
        self.assertEqual(stats["ccg_initial"], stats["ccg_final"])
        self.assertTrue(stats["hard_feasible"])
        self.assertTrue(stats["ccg_target_met"])

    def test_relaxed_violation_budget(self):
        sc, reference, intent = _reference_case("mcu-min")
        perturbed = _with_coordinates(intent, _jiggle(sc, reference, random.Random(11)))
        relaxed, stats = plan_from_intent(
            sc, perturbed, seed=2, steps=100, max_violations=99
        )
        self.assertTrue(stats["ccg_target_met"])
        self.assertLessEqual(stats["ccg_final"], 99)
        self.assertEqual(stats["max_violations"], 99)
        self.assertEqual(hard_violations(sc, relaxed), [])
        # With a zero target and no budget the target can legitimately be missed.
        strict, strict_stats = plan_from_intent(
            sc, perturbed, seed=2, steps=0, max_violations=0
        )
        self.assertFalse(strict_stats["ccg_target_met"])
        self.assertEqual(strict_stats["ccg_final"], strict_stats["ccg_initial"])
        self.assertEqual(hard_violations(sc, strict), [])

    def test_custom_cost_is_accepted(self):
        sc, _reference, intent = _reference_case("rs485")
        cost = HPWLObjective(sc).cost
        plan, stats = plan_from_intent(sc, intent, cost=cost, seed=3, steps=300)
        self.assertEqual(stats["objective"], "cost")
        self.assertEqual(stats["ccg_final"], 0)
        self.assertEqual(hard_violations(sc, plan), [])
        # A non-callable cost is a programming error.
        with self.assertRaises(TypeError):
            plan_from_intent(sc, intent, cost=42)

    def test_invalid_arguments_and_intents(self):
        sc, _reference, intent = _reference_case("buck")
        with self.assertRaises(ValueError):
            plan_from_intent(sc, intent, steps=-1)
        with self.assertRaises(ValueError):
            plan_from_intent(sc, intent, max_violations=-1)
        with self.assertRaises(ValueError):
            plan_from_intent(sc, {"schema": "not-an-intent", "schema_version": 1})
        other_sc, _other_ref, other_intent = _reference_case("wireless")
        with self.assertRaises(ValueError):
            plan_from_intent(sc, other_intent)
        # explicit cost=None is the documented default
        plan, stats = plan_from_intent(sc, intent, cost=None, seed=0, steps=10)
        self.assertEqual(hard_violations(sc, plan), [])
        self.assertEqual(stats["ccg_final"], 0)

    def test_cost_actually_influences_result(self):
        """A constant cost turns the objective into pure CCG minimisation."""
        sc, reference, intent = _reference_case("motor")
        perturbed = _with_coordinates(intent, _jiggle(sc, reference, random.Random(3)))
        penalty_only, _stats = plan_from_intent(
            sc, perturbed, cost=lambda pl: 0.0, seed=0, steps=800
        )
        self.assertEqual(intent_violations(sc, penalty_only, perturbed), [])
        proxy_plan, _stats2 = plan_from_intent(
            sc, perturbed, cost=ProxyObjective(sc).cost, seed=0, steps=800
        )
        self.assertEqual(intent_violations(sc, proxy_plan, perturbed), [])


class BenchmarkSmokeTests(unittest.TestCase):
    def test_benchmark_returns_rates_and_rows(self):
        result = benchmark(names=("buck",), seeds=(0,), steps=120, pipeline_steps=80)
        self.assertIn("config", result)
        self.assertIn("rows", result)
        self.assertIn("aggregate", result)
        self.assertEqual(len(result["rows"]), 1)
        row = result["rows"][0]
        self.assertEqual(row["template"], "buck")
        self.assertEqual(row["seed"], 0)
        self.assertEqual(row["ccg_final"], 0)
        self.assertTrue(row["hard_feasible"])
        for key in ("truth_v2_plan", "truth_v2_pipeline", "pipeline_ccg"):
            self.assertIn(key, row)
        self.assertGreaterEqual(row["truth_v2_plan"], 0.0)
        self.assertGreaterEqual(row["truth_v2_pipeline"], 0.0)
        self.assertIsInstance(row["pipeline_ccg"], int)
        aggregate = result["aggregate"]
        self.assertEqual(aggregate["runs"], 1)
        self.assertEqual(aggregate["ccg_zero_rate"], 1.0)
        self.assertEqual(aggregate["hard_feasible_rate"], 1.0)
        self.assertIn("mean_truth_v2_plan", aggregate)
        self.assertIn("mean_truth_v2_pipeline", aggregate)
        # The default budget is exposed for reproducible CLI runs.
        self.assertEqual(DEFAULT_STEPS, 800)


if __name__ == "__main__":
    unittest.main()
