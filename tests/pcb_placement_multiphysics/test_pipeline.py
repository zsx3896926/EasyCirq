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

The pipeline is offline: no EDA, DRC or network is exercised here either.
"""

import json
import math
import pathlib
import subprocess
import sys
import unittest

from mp_place import intent as intent_mod
from mp_place.model import hard_violations
from mp_place.pipeline import PIPELINE_SCHEMA, run_pipeline
from mp_place.templates import instantiate

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


if __name__ == "__main__":
    unittest.main()
