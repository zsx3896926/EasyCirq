"""Tests for P3.6/P3.7 intent-constrained placement planner (stdlib unittest).

Run with::

    python -m unittest tests.test_intent_solver -v
"""

import json
import os
import pathlib
import random
import tempfile
import unittest

from mp_place.intent import CCG_TYPES, build_intent, intent_to_plan, intent_violations
from mp_place.intent_solver import (
    CCG_PENALTY,
    DEFAULT_CCG_WEIGHT,
    DEFAULT_CCG_WEIGHTS,
    DEFAULT_STEPS,
    RELAX_CLUSTER_FACTOR,
    RELAX_HARD_TYPES,
    RELAX_NEAR_FACTOR,
    SOFT_VIOLATION_WEIGHT,
    benchmark,
    pareto_experiment,
    plan_from_intent,
    write_pareto_report,
)
from mp_place.model import hard_violations
from mp_place.objective import HPWLObjective, ProxyObjective
from mp_place.physics_v2 import PhysicsSimulatorV2
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


def _benchmark_case(name, seed):
    """Same reference layout / intent the P3.7 Pareto report uses."""
    sc = instantiate(name, seed=seed)
    reference = random_feasible_placement(
        sc, random.Random(f"intent-benchmark-ref:{name}:{seed}")
    )
    return sc, reference, build_intent(sc, reference)


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
        for name in template_names():
            with self.subTest(template=name):
                rng = random.Random(42 + sum(ord(c) for c in name))
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


class ConstraintRelaxationTests(unittest.TestCase):
    """P3.7 constraint tiering: near/cluster stay hard, clearance can be soft."""

    def test_default_parameters_reproduce_p36_behaviour(self):
        for name in ("buck", "wireless"):
            with self.subTest(template=name):
                sc, _reference, intent = _reference_case(name)
                plan_a, stats_a = plan_from_intent(sc, intent, seed=0, steps=250)
                plan_b, stats_b = plan_from_intent(
                    sc,
                    intent,
                    seed=0,
                    steps=250,
                    ccg_weight=DEFAULT_CCG_WEIGHT,
                    relax=False,
                    hard_constraints=None,
                )
                self.assertEqual(plan_a, plan_b)
                self.assertEqual(stats_a, stats_b)
                # P3.6 semantics and stats stay intact.
                self.assertEqual(stats_a["ccg_weight"], DEFAULT_CCG_WEIGHT)
                self.assertEqual(stats_a["penalty"], CCG_PENALTY)
                self.assertFalse(stats_a["relax"])
                self.assertEqual(stats_a["hard_constraints"], sorted(CCG_TYPES))
                self.assertEqual(stats_a["soft_constraints"], [])
                self.assertEqual(stats_a["ccg_final"], 0)
                self.assertEqual(stats_a["ccg_hard_final"], 0)
                self.assertEqual(stats_a["ccg_soft_final"], 0)
                self.assertEqual(stats_a["soft_penalty_weight"], SOFT_VIOLATION_WEIGHT)

    def test_relax_tiering_keeps_near_cluster_hard(self):
        sc, _reference, intent = _reference_case("wireless")
        plan, stats = plan_from_intent(sc, intent, seed=0, steps=600, relax=True)
        self.assertTrue(stats["relax"])
        self.assertEqual(stats["hard_constraints"], sorted(RELAX_HARD_TYPES))
        self.assertEqual(stats["soft_constraints"], ["clearance"])
        self.assertEqual(stats["ccg_weight"], DEFAULT_CCG_WEIGHT)
        self.assertEqual(stats["ccg_hard_final"], 0)
        self.assertTrue(stats["ccg_target_met"])
        self.assertEqual(hard_violations(sc, plan), [])
        # the reported original-intent deviation is the real one
        expected_original = len(intent_violations(sc, plan, intent))
        self.assertEqual(stats["original_intent_ccg_final"], expected_original)

    def test_hard_constraints_override(self):
        sc, _reference, intent = _reference_case("buck")
        plan, stats = plan_from_intent(
            sc,
            intent,
            seed=0,
            steps=200,
            hard_constraints=["near", "cluster", "edge"],
        )
        self.assertEqual(stats["hard_constraints"], ["cluster", "edge", "near"])
        self.assertEqual(stats["soft_constraints"], ["clearance"])
        self.assertEqual(stats["ccg_hard_final"], 0)
        self.assertTrue(stats["ccg_target_met"])
        self.assertEqual(hard_violations(sc, plan), [])

    def test_invalid_relaxation_parameters_rejected(self):
        sc, _reference, intent = _reference_case("buck")
        # near/cluster are hard semantics and cannot be dropped.
        with self.assertRaises(ValueError):
            plan_from_intent(sc, intent, steps=0, hard_constraints=["clearance"])
        with self.assertRaises(ValueError):
            plan_from_intent(sc, intent, steps=0, hard_constraints=["near", "bogus"])
        with self.assertRaises(ValueError):
            plan_from_intent(sc, intent, steps=0, ccg_weight=-1.0)
        with self.assertRaises(ValueError):
            plan_from_intent(sc, intent, steps=0, ccg_weight=float("nan"))
        with self.assertRaises(ValueError):
            plan_from_intent(sc, intent, steps=0, ccg_weight="heavy")

    def test_relaxed_parameters_are_deterministic(self):
        sc, _reference, intent = _reference_case("can-node")
        plan_a, stats_a = plan_from_intent(
            sc, intent, seed=7, steps=250, ccg_weight=5.0, relax=True
        )
        plan_b, stats_b = plan_from_intent(
            sc, intent, seed=7, steps=250, ccg_weight=5.0, relax=True
        )
        self.assertEqual(plan_a, plan_b)
        self.assertEqual(stats_a, stats_b)

    def test_all_eight_templates_smoke_with_relax(self):
        for name in template_names():
            with self.subTest(template=name):
                sc, _reference, intent = _reference_case(name)
                plan, stats = plan_from_intent(
                    sc, intent, seed=0, steps=150, ccg_weight=5.0, relax=True
                )
                self.assertEqual(set(plan), set(sc.components))
                self.assertEqual(hard_violations(sc, plan), [])
                self.assertTrue(stats["relax"])
                self.assertEqual(stats["ccg_hard_final"], 0)
                self.assertTrue(stats["ccg_target_met"])
                self.assertIn("ccg_hard_initial", stats)
                self.assertIn("original_intent_ccg_final", stats)

    def test_relax_reduces_truth_on_verified_case(self):
        """Deterministic report case: rs485 seed 0, strict vs relaxed truth."""
        sc, reference, intent = _benchmark_case("rs485", 0)
        self.assertEqual(hard_violations(sc, reference), [])
        truth = PhysicsSimulatorV2(sc, seed=0)
        strict_plan, strict_stats = plan_from_intent(
            sc, intent, cost=ProxyObjective(sc).cost, seed=0, steps=800
        )
        relax_plan, relax_stats = plan_from_intent(
            sc,
            intent,
            cost=ProxyObjective(sc).cost,
            seed=0,
            steps=800,
            relax=True,
        )
        self.assertEqual(strict_stats["ccg_hard_final"], 0)
        self.assertEqual(relax_stats["ccg_hard_final"], 0)
        self.assertLess(truth.score(relax_plan), truth.score(strict_plan))
        self.assertGreaterEqual(relax_stats["original_intent_ccg_final"], 0)

    def test_ccg_weight_changes_search_on_verified_case(self):
        """Weight 5 vs 100 gives different hard-feasible plans (bldc seed 0)."""
        sc, _reference, intent = _benchmark_case("bldc-driver", 0)
        plan_low, stats_low = plan_from_intent(
            sc,
            intent,
            cost=ProxyObjective(sc).cost,
            seed=0,
            steps=800,
            ccg_weight=5.0,
        )
        plan_high, stats_high = plan_from_intent(
            sc,
            intent,
            cost=ProxyObjective(sc).cost,
            seed=0,
            steps=800,
            ccg_weight=100.0,
        )
        self.assertNotEqual(plan_low, plan_high)
        self.assertEqual(stats_low["ccg_weight"], 5.0)
        self.assertEqual(stats_high["ccg_weight"], 100.0)
        self.assertEqual(stats_low["ccg_final"], 0)
        self.assertEqual(stats_high["ccg_final"], 0)
        self.assertEqual(hard_violations(sc, plan_low), [])
        self.assertEqual(hard_violations(sc, plan_high), [])

    def test_pareto_constants(self):
        self.assertEqual(tuple(DEFAULT_CCG_WEIGHTS), (5.0, 25.0, 100.0))
        self.assertEqual(RELAX_HARD_TYPES, ("near", "cluster", "edge"))
        self.assertNotIn("clearance", RELAX_HARD_TYPES)
        self.assertGreater(RELAX_NEAR_FACTOR, 1.0)
        self.assertGreater(RELAX_CLUSTER_FACTOR, 1.0)
        self.assertGreater(SOFT_VIOLATION_WEIGHT, 0.0)
        self.assertLessEqual(SOFT_VIOLATION_WEIGHT, 1.0)


class ParetoExperimentTests(unittest.TestCase):
    def test_small_pareto_sweep_structure(self):
        result = pareto_experiment(
            names=("buck",),
            seeds=(0,),
            ccg_weights=(5.0, 100.0),
            relax_values=(False, True),
            steps=120,
            pipeline_steps=80,
        )
        self.assertEqual(result["schema"], "mp_place.intent_pareto/v1")
        self.assertEqual(len(result["groups"]), 4)
        self.assertEqual(len(result["rows"]), 4)
        self.assertEqual(len(result["cases"]), 1)
        self.assertIn("target", result)
        self.assertIn("criteria", result["target"])
        self.assertIsInstance(result["target"]["met"], bool)
        for group in result["groups"]:
            self.assertEqual(group["runs"], 1)
            self.assertIn("ccg_hard_per_run", group)
            self.assertIn("ccg_soft_per_run", group)
            self.assertIn("mean_truth_vs_pipeline_pct", group)
            self.assertLessEqual(group["ccg_hard_per_run"], 0.5)
            self.assertEqual(group["hard_feasible_rate"], 1.0)
        for row in result["rows"]:
            self.assertTrue(row["hard_feasible"])
            self.assertEqual(row["ccg_hard_violations"], 0)
            self.assertIn("truth_vs_pipeline_pct", row)
            self.assertIn("original_intent_violations", row)

    def test_report_writer_writes_json_and_markdown(self):
        result = pareto_experiment(
            names=("buck",),
            seeds=(0,),
            ccg_weights=(5.0,),
            relax_values=(False, True),
            steps=80,
            pipeline_steps=80,
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            paths = write_pareto_report(result, out_dir=tmp_dir)
            self.assertEqual(set(paths), {"json", "md"})
            self.assertTrue(os.path.isfile(paths["json"]))
            self.assertTrue(os.path.isfile(paths["md"]))
            loaded = json.loads(pathlib.Path(paths["json"]).read_text(encoding="utf-8"))
            self.assertEqual(loaded, result)
            markdown = pathlib.Path(paths["md"]).read_text(encoding="utf-8")
            self.assertIn("# P3.7 Intent 约束松弛 Pareto 报告", markdown)
            self.assertIn("| ccg_weight |", markdown)
            self.assertIn("达标", markdown)
            self.assertIn("truth 折衷", markdown)


if __name__ == "__main__":
    unittest.main()
