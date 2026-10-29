"""Tests for the P4-G end-to-end pipeline and ``run_auto.py`` CLI (stdlib unittest).

Run with::

    python -m unittest tests.test_pipeline -v

Covered contract
----------------
* ``mp_place.pipeline.run_pipeline`` runs the buck template end to end and
  returns a hard-feasible placement.
* The report is plain JSON: ``json.loads(json.dumps(report)) == report``.
* ``fixed_fields`` is exactly ``{routing_verified: False, drc: "NOT RUN",
  eda_calls: 0}`` (never derived from scenario data).
* The intent can be replayed with ``intent_to_plan`` and the replayed plan
  passes ``hard_violations`` and ``intent_violations``.
* The pipeline is deterministic for a fixed ``(scenario, steps, seed)``.
* ``run_auto.py --template buck --seed 0`` and ``--scenario/--json`` work.
* P2.11/task-27 update: ``run_pipeline(..., objective=...)`` accepts three
  tiers -- ``"proxy"`` (default, backwards compatible), ``"route_aware"``
  (recommended safe: fixed ``w_route=2.0``, no per-template table) and
  ``"tuned"`` (experimental: P2.9 table lookup, in-sample only, not
  recommended).  Reports record ``objective_mode`` / ``objective_model`` /
  ``objective_config`` / ``objective_recommended``; ``run_auto.py --objective``
  and batch rows carry the objective field.

* P3.8: ``run_pipeline(..., intent_plan=True)`` runs the proxy solve, builds the
  layout intent from it, refines it with ``plan_from_intent(relax=True)`` and
  verifies the result (``planning_mode="intent_relax"`` + ``intent_planning``
  stats; hard-tier CCG violations 0).  ``run_auto.py --intent-plan`` enables
  it; batch rows carry ``intent_plan`` / ``planning_mode``.

The pipeline is offline: no EDA, DRC or network is exercised here either.
"""

import json
import math
import pathlib
import subprocess
import sys
import tempfile
import unittest

from mp_place import intent as intent_mod
from mp_place.model import hard_violations
from mp_place.pipeline import (
    PIPELINE_OBJECTIVES,
    PIPELINE_SCHEMA,
    benchmark_intent_planning,
    benchmark_objectives,
    run_pipeline,
    write_intent_report,
    write_objective_report,
)
from mp_place.templates import instantiate, template_names

ROOT = pathlib.Path(__file__).resolve().parents[2] / "benchmarks" / "pcb-placement-multiphysics"
FIXED_FIELDS = {"routing_verified": False, "drc": "NOT RUN", "eda_calls": 0}


def plan_from_report(report):
    """Convert the JSON placement payload back into a ``Placement`` mapping."""
    return {
        ref: (float(coord[0]), float(coord[1]), int(coord[2]))
        for ref, coord in report["placement"].items()
    }


def canonical(report):
    """Canonical JSON text used for determinism assertions."""
    return json.dumps(report, ensure_ascii=False, sort_keys=True)


class BuckPipelineTest(unittest.TestCase):
    """End-to-end contract on the default buck template (seed 0)."""

    @classmethod
    def setUpClass(cls):
        cls.scenario = instantiate("buck", seed=0)
        cls.report = run_pipeline(cls.scenario, budget_steps=800, seed=0)

    def test_buck_runs_and_is_feasible(self):
        report = self.report
        self.assertEqual(report["schema"], PIPELINE_SCHEMA)
        self.assertEqual(report["scenario"]["name"], "buck")
        self.assertTrue(report["feasible"])
        self.assertEqual(report["violations"], [])
        # solver output must cover every component and pass the hard checker.
        placement = plan_from_report(report)
        self.assertEqual(set(placement), set(self.scenario.components))
        self.assertEqual(hard_violations(self.scenario, placement), [])

    def test_truth_models_and_router(self):
        report = self.report
        for key in ("truth_v1", "truth_v2"):
            self.assertTrue(math.isfinite(report[key]), key)
            self.assertGreaterEqual(report[key], 0.0, key)
        self.assertIsNotNone(report["proxy_cost"])
        router = report["router"]
        self.assertEqual(router["status"], "ROUTED")
        self.assertGreaterEqual(router["completion"], 0.0)
        self.assertLessEqual(router["completion"], 1.0)
        self.assertEqual(router["failed_nets"], [])
        self.assertIsInstance(router["vias"], int)
        self.assertTrue(report["router_certificate_consistent"])
        self.assertEqual(
            report["certificate"]["routability"]["completion"], router["completion"]
        )

    def test_fixed_fields_are_hard_coded(self):
        self.assertEqual(self.report["fixed_fields"], FIXED_FIELDS)
        self.assertEqual(self.report["certificate"]["fixed_fields"], FIXED_FIELDS)
        self.assertIs(self.report["fixed_fields"]["routing_verified"], False)
        self.assertEqual(self.report["fixed_fields"]["drc"], "NOT RUN")
        self.assertEqual(self.report["fixed_fields"]["eda_calls"], 0)
        self.assertTrue(self.report["limits"])

    def test_json_round_trip(self):
        dumped = json.dumps(self.report, ensure_ascii=False, sort_keys=True)
        loaded = json.loads(dumped)
        self.assertEqual(loaded, self.report)
        self.assertEqual(loaded["schema"], PIPELINE_SCHEMA)
        for ref, coord in loaded["placement"].items():
            self.assertEqual(len(coord), 3, ref)
            self.assertIsInstance(coord[0], float, ref)
            self.assertIsInstance(coord[2], float, ref)

    def test_intent_to_plan_replay_is_hard_feasible(self):
        placement = plan_from_report(self.report)
        intent = intent_mod.build_intent(self.scenario, placement)
        replayed = intent_mod.intent_to_plan(self.scenario, intent)
        self.assertEqual(hard_violations(self.scenario, replayed), [])
        self.assertEqual(intent_mod.intent_violations(self.scenario, replayed, intent), [])
        self.assertTrue(self.report["intent_replay_ok"])
        self.assertEqual(self.report["intent_replay_violations"], [])
        self.assertEqual(self.report["intent_constraints"], intent["constraint_counts"])
        self.assertEqual(
            sum(self.report["intent_constraints"].values()),
            self.report["intent_total_constraints"],
        )

    def test_same_input_is_deterministic(self):
        first = run_pipeline(instantiate("buck", seed=0), budget_steps=300, seed=0)
        second = run_pipeline(instantiate("buck", seed=0), budget_steps=300, seed=0)
        self.assertEqual(canonical(first), canonical(second))

    def test_template_name_is_accepted(self):
        report = run_pipeline("buck", budget_steps=200, seed=0)
        self.assertEqual(report["scenario"]["name"], "buck")
        self.assertTrue(report["feasible"])


class RunAutoCliTest(unittest.TestCase):
    """The CLI must emit exactly one JSON object on stdout and exit 0."""

    def _run(self, *args):
        return subprocess.run(
            [sys.executable, str(ROOT / "run_auto.py"), *args],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=180,
        )

    def test_default_buck_cli_prints_json(self):
        proc = self._run("--template", "buck", "--seed", "0")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = json.loads(proc.stdout)  # one JSON object, optionally indented
        self.assertEqual(report["schema"], PIPELINE_SCHEMA)
        self.assertEqual(report["scenario"]["name"], "buck")
        self.assertTrue(report["feasible"])
        self.assertEqual(report["fixed_fields"], FIXED_FIELDS)

    def test_json_flag_keeps_stdout_clean(self):
        proc = self._run("--template", "buck", "--seed", "0", "--json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = json.loads(proc.stdout)
        self.assertEqual(report["scenario"]["name"], "buck")
        self.assertNotIn("[run_auto]", proc.stdout)
        self.assertIn("[run_auto]", proc.stderr)

    def test_scenario_flag(self):
        proc = self._run("--scenario", "buck", "--seed", "0", "--steps", "200", "--json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = json.loads(proc.stdout)
        self.assertEqual(report["scenario"]["name"], "buck")
        self.assertTrue(report["feasible"])

    def test_unknown_template_exits_2(self):
        proc = self._run("--template", "no-such-template", "--json")
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout.strip(), "")
        self.assertIn("unknown template", proc.stderr)


class ObjectiveOptionTests(unittest.TestCase):
    """P2.11/task-27 update: ``run_pipeline(..., objective=...)`` three modes."""

    @classmethod
    def setUpClass(cls):
        cls.scenario = instantiate("buck", seed=0)
        cls.default_report = run_pipeline(cls.scenario, budget_steps=150, seed=0)
        cls.proxy_report = run_pipeline(
            cls.scenario, budget_steps=150, seed=0, objective="proxy"
        )
        cls.route_report = run_pipeline(
            cls.scenario, budget_steps=150, seed=0, objective="route_aware"
        )
        cls.tuned_report = run_pipeline(
            cls.scenario, budget_steps=150, seed=0, objective="tuned"
        )

    def test_default_objective_is_proxy_and_compatible(self):
        report = self.default_report
        self.assertEqual(report["objective_mode"], "proxy")
        self.assertEqual(report["objective_model"], "multiphysics_proxy")
        self.assertEqual(
            report["objective_config"]["generalization"], "baseline"
        )
        self.assertTrue(report["objective_recommended"])
        self.assertEqual(report["config"]["objective_mode"], "proxy")
        self.assertEqual(report["config"]["objective"], "multiphysics_proxy")
        # Explicit objective="proxy" is byte-identical to the default call.
        self.assertEqual(canonical(report), canonical(self.proxy_report))
        self.assertEqual(report["schema"], PIPELINE_SCHEMA)
        self.assertTrue(report["feasible"])

    def test_route_aware_is_the_recommended_safe_option(self):
        report = self.route_report
        self.assertEqual(report["objective_mode"], "route_aware")
        self.assertEqual(report["objective_model"], "route_aware_proxy")
        config = report["objective_config"]
        self.assertEqual(config["mode"], "route_aware")
        self.assertEqual(config["w_route"], 2.0)
        self.assertEqual(config["profile"], "default")
        self.assertEqual(config["source"], "fixed_weight")
        self.assertTrue(config["recommended"])
        self.assertEqual(config["generalization"], "heldout_safe")
        self.assertTrue(report["objective_recommended"])
        self.assertEqual(report["objective_generalization"], "heldout_safe")
        self.assertTrue(report["feasible"])
        self.assertEqual(report["violations"], [])
        self.assertEqual(report["router"]["status"], "ROUTED")
        self.assertTrue(report["intent_replay_ok"])
        self.assertEqual(json.loads(json.dumps(report, sort_keys=True)), report)
        # w_route=2.0 changes the solve: the placement differs from the proxy.
        self.assertNotEqual(
            report["placement_digest"], self.proxy_report["placement_digest"]
        )

    def test_tuned_is_experimental_in_sample_only(self):
        report = self.tuned_report
        self.assertEqual(report["objective_mode"], "tuned")
        self.assertEqual(report["objective_model"], "route_aware_proxy")
        config = report["objective_config"]
        self.assertEqual(config["mode"], "tuned")
        self.assertEqual(config["source"], "tuned_table")
        self.assertFalse(config["recommended"])
        self.assertEqual(config["generalization"], "in_sample_only")
        self.assertFalse(report["objective_recommended"])
        self.assertEqual(report["objective_generalization"], "in_sample_only")
        self.assertIn("in-sample", config["note"])
        self.assertIn("7.47", config["note"])
        self.assertTrue(report["feasible"])
        self.assertEqual(json.loads(json.dumps(report, sort_keys=True)), report)
        # buck's P2.9 tuned entry has w_route=0.0 -> identical proxy solve.
        self.assertEqual(config["w_route"], 0.0)
        self.assertEqual(report["placement_digest"], self.proxy_report["placement_digest"])

    def test_invalid_objectives_rejected(self):
        for bad in ("bogus", "", "tuned_route"):
            with self.assertRaises(ValueError):
                run_pipeline(self.scenario, budget_steps=60, objective=bad)
        with self.assertRaises(TypeError):
            run_pipeline(self.scenario, budget_steps=60, objective=123)
        self.assertEqual(
            PIPELINE_OBJECTIVES, ("proxy", "route_aware", "tuned")
        )


class AllTemplatesObjectiveSmokeTests(unittest.TestCase):
    def test_all_eight_templates_run_with_route_aware(self):
        names = template_names()
        self.assertEqual(len(names), 8)
        for name in names:
            with self.subTest(template=name):
                sc = instantiate(name, seed=0)
                report = run_pipeline(
                    sc, budget_steps=80, seed=0, objective="route_aware"
                )
                self.assertEqual(report["scenario"]["name"], name)
                self.assertEqual(report["objective_mode"], "route_aware")
                config = report["objective_config"]
                self.assertEqual(config["w_route"], 2.0)
                self.assertEqual(config["profile"], "default")
                self.assertTrue(report["objective_recommended"])
                self.assertTrue(report["feasible"])
                self.assertEqual(report["violations"], [])
                self.assertEqual(report["router"]["status"], "ROUTED")
                placement = plan_from_report(report)
                self.assertEqual(set(placement), set(sc.components))
                self.assertEqual(hard_violations(sc, placement), [])


class ObjectiveBenchmarkTests(unittest.TestCase):
    def test_benchmark_and_report_writer(self):
        result = benchmark_objectives(
            names=("buck",), seeds=(0,), heldout_seeds=(2,), steps=200
        )
        self.assertEqual(result["schema"], "mp_place.pipeline_objective/v2")
        self.assertEqual(set(result["cohorts"]), {"in_sample", "heldout"})
        self.assertEqual(len(result["rows"]), 6)  # 2 cohorts x 1 case x 3 modes
        for cohort in ("in_sample", "heldout"):
            block = result["cohorts"][cohort]
            self.assertEqual(
                [group["objective"] for group in block["groups"]],
                ["proxy", "route_aware", "tuned"],
            )
            self.assertIsNotNone(block["route_aware_vs_proxy"])
            self.assertIsNotNone(block["tuned_vs_proxy"])
            for group in block["groups"]:
                self.assertEqual(group["runs"], 1)
                self.assertIn("mean_completion", group)
                self.assertIn("mean_truth_v2", group)
        for row in result["rows"]:
            self.assertIn(row["objective"], PIPELINE_OBJECTIVES)
            self.assertTrue(row["feasible"])
            self.assertIsNotNone(row["completion"])
            self.assertGreaterEqual(row["runtime_s"], 0.0)
            self.assertIsInstance(row["truth_v2"], float)
        target = result["target"]
        self.assertEqual(target["cohort"], "heldout")
        for key in (
            "criteria",
            "completion_per_case_not_lower",
            "aggregate_completion_not_lower",
            "aggregate_truth_ratio",
            "truth_within_1pct",
            "met",
        ):
            self.assertIn(key, target)
        self.assertIn("in_sample_route_aware", target)
        tuned = result["tuned_status"]
        self.assertFalse(tuned["recommended"])
        self.assertEqual(tuned["label"], "in_sample_only")
        self.assertIn("in-sample", tuned["note"])
        self.assertIsNotNone(tuned["heldout_truth_pct"])
        self.assertEqual(result["recommendation"]["recommended"], "route_aware")
        self.assertEqual(result["recommendation"]["not_recommended"], "tuned")

        with tempfile.TemporaryDirectory() as tmp_dir:
            paths = write_objective_report(result, out_dir=tmp_dir)
            self.assertEqual(set(paths), {"json", "md"})
            self.assertTrue(pathlib.Path(paths["json"]).is_file())
            self.assertTrue(pathlib.Path(paths["md"]).is_file())
            loaded = json.loads(
                pathlib.Path(paths["json"]).read_text(encoding="utf-8")
            )
            self.assertEqual(loaded, result)
            markdown = pathlib.Path(paths["md"]).read_text(encoding="utf-8")
            self.assertIn("# P2.11 Pipeline objective 对比", markdown)
            self.assertIn("route_aware", markdown)
            self.assertIn("tuned", markdown)
            self.assertIn("不推荐", markdown)
            self.assertIn("达标", markdown)


class RunAutoObjectiveCliTest(unittest.TestCase):
    """CLI: ``--objective`` flag and batch ``objective`` field."""

    def _run(self, *args):
        return subprocess.run(
            [sys.executable, str(ROOT / "run_auto.py"), *args],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=180,
        )

    def test_route_aware_flag(self):
        proc = self._run(
            "--template", "buck", "--seed", "0", "--steps", "100",
            "--objective", "route_aware", "--json",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = json.loads(proc.stdout)
        self.assertEqual(report["objective_mode"], "route_aware")
        self.assertEqual(report["objective_model"], "route_aware_proxy")
        self.assertEqual(report["objective_config"]["w_route"], 2.0)
        self.assertTrue(report["objective_recommended"])
        self.assertEqual(report["fixed_fields"], FIXED_FIELDS)
        self.assertIn("objective=route_aware", proc.stderr)

    def test_tuned_flag_accepted_but_not_recommended(self):
        proc = self._run(
            "--template", "buck", "--seed", "0", "--steps", "80",
            "--objective", "tuned", "--json",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = json.loads(proc.stdout)
        self.assertEqual(report["objective_mode"], "tuned")
        self.assertFalse(report["objective_recommended"])
        self.assertEqual(report["objective_generalization"], "in_sample_only")
        self.assertEqual(report["objective_config"]["source"], "tuned_table")

    def test_bad_objective_exits_2(self):
        proc = self._run("--objective", "bogus", "--json")
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout.strip(), "")
        self.assertIn("--objective", proc.stderr)

    def test_batch_rows_carry_objective(self):
        proc = self._run(
            "--all-templates", "--seeds", "0", "--steps", "60",
            "--objective", "route_aware", "--json",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        batch = json.loads(proc.stdout)
        self.assertEqual(batch["schema"], "mp_place.batch/v1")
        self.assertEqual(batch["objective"], "route_aware")
        self.assertEqual(batch["n_runs"], len(template_names()))
        self.assertTrue(batch["all_feasible"])
        for row in batch["rows"]:
            self.assertEqual(row["objective"], "route_aware")
            self.assertTrue(row["feasible"])
        self.assertIn("objective=route_aware", proc.stderr)



class IntentPlanOptionTests(unittest.TestCase):
    """P3.8: ``run_pipeline(..., intent_plan=True)`` proxy -> intent -> replan."""

    @classmethod
    def setUpClass(cls):
        cls.scenario = instantiate("buck", seed=0)
        cls.proxy_report = run_pipeline(cls.scenario, budget_steps=150, seed=0)
        cls.intent_report = run_pipeline(
            cls.scenario, budget_steps=150, seed=0, intent_plan=True
        )

    def test_default_planning_mode_is_direct(self):
        report = self.proxy_report
        self.assertEqual(report["planning_mode"], "direct")
        self.assertFalse(report["intent_plan"])
        self.assertIsNone(report["intent_planning"])
        self.assertEqual(report["config"]["planning_mode"], "direct")
        # explicit intent_plan=False is identical to the default call
        explicit = run_pipeline(
            self.scenario, budget_steps=150, seed=0, intent_plan=False
        )
        self.assertEqual(canonical(explicit), canonical(report))

    def test_intent_plan_report_shape(self):
        report = self.intent_report
        self.assertEqual(report["planning_mode"], "intent_relax")
        self.assertTrue(report["intent_plan"])
        self.assertEqual(report["config"]["planning_mode"], "intent_relax")
        planning = report["intent_planning"]
        self.assertIsNotNone(planning)
        for key in (
            "mode",
            "relax",
            "reference_intent_digest",
            "reference_intent_constraints",
            "ccg_hard_final",
            "ccg_soft_final",
            "original_intent_ccg_final",
            "hard_feasible",
            "moves",
            "moves_accepted",
            "cost_initial",
            "cost_final",
        ):
            self.assertIn(key, planning)
        self.assertEqual(planning["mode"], "intent_relax")
        self.assertTrue(planning["relax"])
        self.assertEqual(planning["ccg_hard_final"], 0)
        self.assertEqual(planning["ccg_soft_final"], 0)
        self.assertGreaterEqual(planning["original_intent_ccg_final"], 0)
        self.assertTrue(planning["hard_feasible"])
        self.assertTrue(report["feasible"])
        self.assertEqual(report["violations"], [])
        self.assertEqual(report["router"]["status"], "ROUTED")
        self.assertTrue(report["intent_replay_ok"])
        self.assertEqual(
            report["certificate"]["extra"]["planning_mode"], "intent_relax"
        )
        self.assertEqual(json.loads(json.dumps(report, sort_keys=True)), report)
        # deterministic for the same inputs
        again = run_pipeline(
            self.scenario, budget_steps=150, seed=0, intent_plan=True
        )
        self.assertEqual(canonical(report), canonical(again))
        # the relaxed intent refinement moves parts away from the proxy layout
        self.assertNotEqual(
            report["placement_digest"], self.proxy_report["placement_digest"]
        )

    def test_intent_plan_requires_proxy_objective(self):
        with self.assertRaises(ValueError):
            run_pipeline(
                self.scenario,
                budget_steps=60,
                objective="route_aware",
                intent_plan=True,
            )


class AllTemplatesIntentPlanSmokeTests(unittest.TestCase):
    def test_all_eight_templates_run_with_intent_plan(self):
        names = template_names()
        self.assertEqual(len(names), 8)
        for name in names:
            with self.subTest(template=name):
                sc = instantiate(name, seed=0)
                report = run_pipeline(
                    sc, budget_steps=80, seed=0, intent_plan=True
                )
                self.assertEqual(report["scenario"]["name"], name)
                self.assertEqual(report["planning_mode"], "intent_relax")
                planning = report["intent_planning"]
                self.assertIsNotNone(planning)
                self.assertEqual(planning["ccg_hard_final"], 0)
                self.assertEqual(planning["ccg_soft_final"], 0)
                self.assertTrue(report["feasible"])
                self.assertEqual(report["violations"], [])
                self.assertEqual(report["router"]["status"], "ROUTED")
                placement = plan_from_report(report)
                self.assertEqual(set(placement), set(sc.components))
                self.assertEqual(hard_violations(sc, placement), [])


class IntentBenchmarkTests(unittest.TestCase):
    def test_benchmark_and_report_writer(self):
        result = benchmark_intent_planning(names=("buck",), seeds=(0,), steps=150)
        self.assertEqual(result["schema"], "mp_place.pipeline_intent/v1")
        self.assertEqual(
            [group["mode"] for group in result["groups"]],
            ["proxy", "route_aware", "intent_relax"],
        )
        self.assertEqual(len(result["rows"]), 3)
        for row in result["rows"]:
            self.assertIn(row["mode"], ("proxy", "route_aware", "intent_relax"))
            self.assertTrue(row["feasible"])
            self.assertIsNotNone(row["completion"])
            self.assertGreaterEqual(row["runtime_s"], 0.0)
            self.assertIsInstance(row["truth_v2"], float)
        target = result["target"]
        for key in (
            "criteria",
            "ccg_hard_per_run",
            "ccg_soft_per_run",
            "original_intent_deviations_per_run",
            "mean_truth_v2_proxy",
            "mean_truth_v2_intent_relax",
            "mean_truth_gap_pct",
            "ccg_target_met",
            "truth_target_met",
            "met",
        ):
            self.assertIn(key, target)
        self.assertTrue(target["ccg_target_met"])
        self.assertEqual(target["ccg_hard_per_run"], 0.0)
        self.assertEqual(result["recommendation"]["recommended_when_intent_matters"], "intent_relax")

        with tempfile.TemporaryDirectory() as tmp_dir:
            paths = write_intent_report(result, out_dir=tmp_dir)
            self.assertEqual(set(paths), {"json", "md"})
            self.assertTrue(pathlib.Path(paths["json"]).is_file())
            self.assertTrue(pathlib.Path(paths["md"]).is_file())
            loaded = json.loads(
                pathlib.Path(paths["json"]).read_text(encoding="utf-8")
            )
            self.assertEqual(loaded, result)
            markdown = pathlib.Path(paths["md"]).read_text(encoding="utf-8")
            self.assertIn("# P3.8 Pipeline intent 约束规划对比", markdown)
            self.assertIn("intent_relax", markdown)
            self.assertIn("达标", markdown)
            self.assertIn("推荐", markdown)


class RunAutoIntentPlanCliTest(unittest.TestCase):
    """CLI: ``--intent-plan`` flag and batch ``intent_plan`` fields."""

    def _run(self, *args):
        return subprocess.run(
            [sys.executable, str(ROOT / "run_auto.py"), *args],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=180,
        )

    def test_intent_plan_flag(self):
        proc = self._run(
            "--template", "buck", "--seed", "0", "--steps", "100",
            "--intent-plan", "--json",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = json.loads(proc.stdout)
        self.assertEqual(report["planning_mode"], "intent_relax")
        self.assertTrue(report["intent_plan"])
        self.assertEqual(report["intent_planning"]["ccg_hard_final"], 0)
        self.assertEqual(report["fixed_fields"], FIXED_FIELDS)
        self.assertIn("planning=intent_relax", proc.stderr)

    def test_intent_plan_requires_proxy_objective(self):
        proc = self._run(
            "--template", "buck", "--intent-plan", "--objective", "route_aware"
        )
        self.assertEqual(proc.returncode, 2)
        self.assertIn("--intent-plan", proc.stderr)

    def test_batch_rows_carry_intent_plan(self):
        proc = self._run(
            "--all-templates", "--seeds", "0", "--steps", "60",
            "--intent-plan", "--json",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        batch = json.loads(proc.stdout)
        self.assertEqual(batch["schema"], "mp_place.batch/v1")
        self.assertTrue(batch["intent_plan"])
        self.assertEqual(batch["n_runs"], len(template_names()))
        self.assertTrue(batch["all_feasible"])
        for row in batch["rows"]:
            self.assertTrue(row["intent_plan"])
            self.assertEqual(row["planning_mode"], "intent_relax")
            self.assertTrue(row["feasible"])
        self.assertIn("intent_plan=True", proc.stderr)



if __name__ == "__main__":
    unittest.main()
