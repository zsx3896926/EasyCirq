"""Tests for the P4.8/P4.10 end-to-end policy table and default-tier guard.

Run with::

    python -m unittest tests.test_policy -v
"""

import json
import pathlib
import subprocess
import sys
import unittest
from unittest import mock

from mp_place import policy
from mp_place.pipeline import DEFAULT_OBJECTIVE, PIPELINE_OBJECTIVES, run_pipeline

ROOT = pathlib.Path(__file__).resolve().parents[2] / "benchmarks" / "pcb-placement-multiphysics"
EXPECTED_GOALS = (
    "balanced",
    "routability",
    "intent_fidelity",
    "truth_sensitive",
    "experimental",
)
#: goal -> (objective, intent_plan, route_repair); the P4.8 decision table.
EXPECTED_MODES = {
    "balanced": ("proxy", False, False),
    "routability": ("route_aware", False, False),
    "intent_fidelity": ("proxy", True, False),
    "truth_sensitive": ("proxy", False, True),
    "experimental": ("tuned", False, False),
}


class PolicyTableTests(unittest.TestCase):
    def test_five_goals_registered(self):
        self.assertEqual(policy.POLICY_GOALS, EXPECTED_GOALS)
        self.assertEqual(tuple(policy.POLICIES), EXPECTED_GOALS)
        self.assertEqual(policy.DEFAULT_GOAL, "balanced")
        self.assertEqual(policy.POLICY_SCHEMA, "mp_place.policy/v1")

    def test_each_entry_is_complete_and_json_safe(self):
        for goal in EXPECTED_GOALS:
            with self.subTest(goal=goal):
                entry = policy.recommend(goal)
                self.assertEqual(entry["goal"], goal)
                self.assertIn(entry["objective"], PIPELINE_OBJECTIVES)
                self.assertIsInstance(entry["intent_plan"], bool)
                self.assertIsInstance(entry["route_repair"], bool)
                self.assertIsInstance(entry["recommended"], bool)
                self.assertIsInstance(entry["default"], bool)
                for key in (
                    "label",
                    "rationale",
                    "expected_tradeoff",
                    "command_template",
                    "evidence",
                    "warnings",
                    "boundaries",
                    "run_auto_args",
                ):
                    self.assertIn(key, entry)
                self.assertTrue(entry["label"])
                self.assertTrue(entry["rationale"])
                self.assertTrue(entry["command_template"])
                self.assertTrue(entry["evidence"])
                self.assertTrue(entry["boundaries"])
                self.assertIsInstance(entry["run_auto_args"], list)
                tradeoff = entry["expected_tradeoff"]
                self.assertIn("in_sample", tradeoff)
                in_sample = tradeoff["in_sample"]
                self.assertIn("completion", in_sample)
                self.assertIn("truth_v2", in_sample)
                self.assertGreaterEqual(in_sample["completion"], 0.0)
                self.assertLessEqual(in_sample["completion"], 1.0)
                self.assertGreaterEqual(in_sample["truth_v2"], 0.0)
                # Every entry must be JSON serialisable (policy CLI --json).
                json.loads(json.dumps(entry, allow_nan=False))

    def test_goal_modes_match_decision_table(self):
        for goal, expected in EXPECTED_MODES.items():
            with self.subTest(goal=goal):
                entry = policy.recommend(goal)
                actual = (entry["objective"], entry["intent_plan"], entry["route_repair"])
                self.assertEqual(actual, expected)

    def test_recommended_and_default_flags(self):
        recommended = {
            "balanced": True,
            "routability": True,
            "intent_fidelity": True,
            "truth_sensitive": True,
            "experimental": False,
        }
        for goal, expected in recommended.items():
            with self.subTest(goal=goal):
                self.assertEqual(policy.recommend(goal)["recommended"], expected)
        self.assertTrue(policy.recommend("balanced")["default"])
        for goal in EXPECTED_GOALS:
            if goal != "balanced":
                self.assertFalse(policy.recommend(goal)["default"])

    def test_experimental_is_flagged_in_sample_only(self):
        entry = policy.recommend("experimental")
        self.assertFalse(entry["recommended"])
        joined = " ".join(entry["warnings"]).lower()
        self.assertIn("in-sample", joined)
        self.assertIn("not recommended", joined)
        self.assertAlmostEqual(
            entry["expected_tradeoff"]["heldout"]["truth_delta_pct"], 7.47, places=2
        )
        # No other policy is marked experimental / not recommended.
        for goal in EXPECTED_GOALS:
            if goal != "experimental":
                self.assertTrue(policy.recommend(goal)["recommended"])

    def test_recommend_returns_defensive_copy(self):
        entry = policy.recommend("balanced")
        entry["objective"] = "tuned"
        entry["expected_tradeoff"]["in_sample"]["truth_v2"] = -1.0
        again = policy.recommend("balanced")
        self.assertEqual(again["objective"], "proxy")
        self.assertEqual(policy.POLICIES["balanced"]["objective"], "proxy")
        self.assertNotEqual(
            policy.POLICIES["balanced"]["expected_tradeoff"]["in_sample"]["truth_v2"],
            -1.0,
        )

    def test_invalid_goals_rejected(self):
        for bad in ("bogus", "", "proxy", "intent_relax"):
            with self.subTest(goal=bad):
                with self.assertRaises(ValueError):
                    policy.recommend(bad)
        with self.assertRaises(TypeError):
            policy.recommend(123)
        with self.assertRaises(TypeError):
            policy.recommend(None)


class DefaultRegressionGuardTests(unittest.TestCase):
    def test_assert_defaults_passes_and_reports(self):
        details = policy.assert_defaults()
        self.assertTrue(details["ok"])
        self.assertEqual(details["schema"], "mp_place.policy/v1")
        self.assertEqual(details["default_goal"], "balanced")
        self.assertEqual(details["pipeline"]["objective"], "proxy")
        self.assertIs(details["pipeline"]["intent_plan"], False)
        self.assertIs(details["pipeline"]["route_repair"], False)
        self.assertEqual(details["run_auto"]["objective"], "proxy")
        self.assertIs(details["run_auto"]["intent_plan"], False)
        self.assertEqual(
            details["balanced_policy"],
            {"objective": "proxy", "intent_plan": False, "route_repair": False},
        )
        self.assertEqual(tuple(details["goals"]), EXPECTED_GOALS)
        json.loads(json.dumps(details, allow_nan=False))

    def test_pipeline_signature_defaults_are_expected(self):
        import inspect

        params = inspect.signature(run_pipeline).parameters
        self.assertEqual(DEFAULT_OBJECTIVE, "proxy")
        self.assertEqual(params["objective"].default, "proxy")
        self.assertIs(params["intent_plan"].default, False)
        self.assertIs(params["route_repair"].default, False)
        self.assertEqual(policy.EXPECTED_DEFAULTS["objective"], "proxy")

    def test_default_regression_is_detected(self):
        with mock.patch.object(
            policy,
            "_pipeline_defaults",
            return_value={
                "objective": "route_aware",
                "intent_plan": False,
                "route_repair": False,
                "budget_steps": 800,
            },
        ):
            with self.assertRaises(AssertionError) as ctx:
                policy.assert_defaults()
            self.assertIn("run_pipeline default objective", str(ctx.exception))

        with mock.patch.object(
            policy,
            "_run_auto_defaults",
            return_value={
                "objective": "route_aware",
                "intent_plan": False,
                "recommend": None,
            },
        ):
            with self.assertRaises(AssertionError) as ctx:
                policy.assert_defaults()
            self.assertIn("run_auto default objective", str(ctx.exception))

        with mock.patch.object(
            policy,
            "_pipeline_defaults",
            return_value={
                "objective": "proxy",
                "intent_plan": False,
                "route_repair": True,
                "budget_steps": 800,
            },
        ):
            with self.assertRaises(AssertionError) as ctx:
                policy.assert_defaults()
            self.assertIn("route_repair", str(ctx.exception))

    def test_balanced_policy_is_the_default_tier(self):
        balanced = policy.recommend("balanced")
        self.assertEqual(
            (balanced["objective"], balanced["intent_plan"], balanced["route_repair"]),
            ("proxy", False, False),
        )
        self.assertTrue(balanced["default"])
        self.assertTrue(balanced["recommended"])


class PolicyEvidenceTests(unittest.TestCase):
    """Policy numbers must match the committed P4.8 evidence reports."""

    def _read_json(self, name):
        path = ROOT / name
        if not path.is_file():
            self.skipTest(f"{name} is not present")
        return json.loads(path.read_text(encoding="utf-8"))

    def test_balanced_and_routability_match_objective_report(self):
        report = self._read_json("report_pipeline_objective.json")
        groups = {
            (cohort, group["objective"]): group
            for cohort, block in report["cohorts"].items()
            for group in block["groups"]
        }
        balanced = policy.recommend("balanced")["expected_tradeoff"]
        self.assertAlmostEqual(
            groups[("in_sample", "proxy")]["mean_completion"],
            balanced["in_sample"]["completion"],
            places=4,
        )
        self.assertAlmostEqual(
            groups[("in_sample", "proxy")]["mean_truth_v2"],
            balanced["in_sample"]["truth_v2"],
            places=4,
        )
        self.assertAlmostEqual(
            groups[("heldout", "proxy")]["mean_completion"],
            balanced["heldout"]["completion"],
            places=4,
        )
        routability = policy.recommend("routability")["expected_tradeoff"]
        self.assertAlmostEqual(
            groups[("in_sample", "route_aware")]["mean_completion"],
            routability["in_sample"]["completion"],
            places=4,
        )
        self.assertAlmostEqual(
            groups[("in_sample", "route_aware")]["mean_truth_v2"],
            routability["in_sample"]["truth_v2"],
            places=4,
        )
        self.assertAlmostEqual(
            groups[("heldout", "route_aware")]["mean_completion"],
            routability["heldout"]["completion"],
            places=4,
        )
        self.assertAlmostEqual(
            groups[("heldout", "route_aware")]["mean_truth_v2"],
            routability["heldout"]["truth_v2"],
            places=4,
        )

    def test_experimental_matches_reports(self):
        report = self._read_json("report_pipeline_objective.json")
        groups = {
            (cohort, group["objective"]): group
            for cohort, block in report["cohorts"].items()
            for group in block["groups"]
        }
        experimental = policy.recommend("experimental")["expected_tradeoff"]
        self.assertAlmostEqual(
            groups[("in_sample", "tuned")]["mean_completion"],
            experimental["in_sample"]["completion"],
            places=4,
        )
        self.assertAlmostEqual(
            groups[("in_sample", "tuned")]["mean_truth_v2"],
            experimental["in_sample"]["truth_v2"],
            places=4,
        )
        self.assertAlmostEqual(
            groups[("heldout", "tuned")]["mean_completion"],
            experimental["heldout"]["completion"],
            places=4,
        )
        self.assertAlmostEqual(
            groups[("heldout", "tuned")]["mean_truth_v2"],
            experimental["heldout"]["truth_v2"],
            places=4,
        )
        self.assertAlmostEqual(
            experimental["heldout"]["truth_delta_pct"], 7.47, places=2
        )

    def test_intent_fidelity_matches_intent_report(self):
        report = self._read_json("report_pipeline_intent.json")
        groups = {group["mode"]: group for group in report["groups"]}
        intent = policy.recommend("intent_fidelity")["expected_tradeoff"]["in_sample"]
        self.assertAlmostEqual(
            groups["intent_relax"]["mean_truth_v2"], intent["truth_v2"], places=4
        )
        self.assertAlmostEqual(
            groups["intent_relax"]["mean_completion"],
            intent["completion"],
            places=4,
        )
        self.assertAlmostEqual(
            groups["intent_relax"]["mean_intent_hard"],
            intent["ccg_hard_per_run"],
            places=4,
        )
        self.assertAlmostEqual(
            groups["intent_relax"]["mean_intent_original_deviations"],
            intent["original_intent_deviations_per_run"],
            places=2,
        )

    def test_truth_sensitive_matches_route_cost_report(self):
        path = ROOT / "report_route_cost.md"
        if not path.is_file():
            self.skipTest("report_route_cost.md is not present")
        text = path.read_text(encoding="utf-8")
        tradeoff = policy.recommend("truth_sensitive")["expected_tradeoff"][
            "in_sample"
        ]
        # The report rounds to 4 decimals in its summary table.
        self.assertIn(f"{tradeoff['completion']:.4f}", text)
        self.assertIn(f"{tradeoff['truth_v2']:.4f}", text)


class PolicyResolutionTests(unittest.TestCase):
    """P4.10: policy -> executable run_pipeline parameters (consistency)."""

    def test_resolution_matches_recommend(self):
        for goal in EXPECTED_GOALS:
            with self.subTest(goal=goal):
                entry = policy.recommend(goal)
                resolution = policy.resolve_pipeline_policy(goal)
                self.assertEqual(resolution["goal"], goal)
                self.assertEqual(resolution["objective"], entry["objective"])
                self.assertEqual(resolution["intent_plan"], entry["intent_plan"])
                self.assertEqual(resolution["route_repair"], entry["route_repair"])
                self.assertEqual(resolution["source"], "policy")
                self.assertEqual(resolution["schema"], policy.POLICY_SCHEMA)
                json.loads(json.dumps(resolution, allow_nan=False))

    def test_default_looking_values_defer_to_policy(self):
        routed = policy.resolve_pipeline_policy("routability", objective="proxy")
        self.assertEqual(routed["objective"], "route_aware")
        intent = policy.resolve_pipeline_policy("intent_fidelity", intent_plan=False)
        self.assertTrue(intent["intent_plan"])
        repaired = policy.resolve_pipeline_policy(
            "truth_sensitive", route_repair=False
        )
        self.assertTrue(repaired["route_repair"])

    def test_matching_explicit_values_are_allowed(self):
        routed = policy.resolve_pipeline_policy(
            "routability", objective="route_aware"
        )
        self.assertEqual(routed["objective"], "route_aware")
        intent = policy.resolve_pipeline_policy("intent_fidelity", intent_plan=True)
        self.assertTrue(intent["intent_plan"])
        repaired = policy.resolve_pipeline_policy(
            "truth_sensitive", route_repair=True
        )
        self.assertTrue(repaired["route_repair"])

    def test_conflicting_non_default_values_raise(self):
        with self.assertRaises(ValueError):
            policy.resolve_pipeline_policy("intent_fidelity", objective="route_aware")
        with self.assertRaises(ValueError):
            policy.resolve_pipeline_policy("experimental", objective="route_aware")
        with self.assertRaises(ValueError):
            policy.resolve_pipeline_policy("balanced", intent_plan=True)
        with self.assertRaises(ValueError):
            policy.resolve_pipeline_policy("routability", route_repair=True)
        with self.assertRaises(ValueError):
            policy.resolve_pipeline_policy("bogus")
        with self.assertRaises(TypeError):
            policy.resolve_pipeline_policy(123)
        with self.assertRaises(TypeError):
            policy.resolve_pipeline_policy("balanced", objective=123)

    def test_pipeline_execution_consistency_for_all_five_goals(self):
        from mp_place.pipeline import run_pipeline
        from mp_place.templates import instantiate

        sc = instantiate("buck", seed=0)
        for goal in EXPECTED_GOALS:
            with self.subTest(goal=goal):
                entry = policy.recommend(goal)
                report = run_pipeline(sc, budget_steps=80, seed=0, policy=goal)
                self.assertTrue(report["feasible"])
                self.assertEqual(report["policy_goal"], goal)
                self.assertEqual(report["policy"]["goal"], goal)
                # report policy block == recommend() combination
                self.assertEqual(report["objective_mode"], entry["objective"])
                self.assertEqual(bool(report["intent_plan"]), entry["intent_plan"])
                self.assertEqual(
                    bool(report["policy"]["route_repair"]), entry["route_repair"]
                )
                if entry["route_repair"]:
                    self.assertEqual(report["solver"]["solver"], "route_repair")
                else:
                    self.assertNotEqual(report["solver"]["solver"], "route_repair")
                self.assertEqual(json.loads(json.dumps(report)), report)

    def test_default_is_balanced_proxy(self):
        from mp_place.pipeline import run_pipeline
        from mp_place.templates import instantiate

        sc = instantiate("buck", seed=0)
        default = run_pipeline(sc, budget_steps=80, seed=0)
        balanced = run_pipeline(sc, budget_steps=80, seed=0, policy="balanced")
        self.assertIsNone(default["policy"])
        self.assertIsNone(default["policy_goal"])
        self.assertEqual(default["objective_mode"], "proxy")
        self.assertFalse(default["intent_plan"])
        self.assertNotEqual(default["solver"]["solver"], "route_repair")
        self.assertEqual(balanced["policy_goal"], "balanced")
        self.assertEqual(balanced["objective_mode"], "proxy")
        self.assertFalse(balanced["intent_plan"])
        self.assertEqual(default["placement_digest"], balanced["placement_digest"])


class PolicyCliTests(unittest.TestCase):
    def _run(self, *args, module=False):
        cmd = [sys.executable]
        if module:
            cmd += ["-m", "mp_place.policy"]
        else:
            cmd += [str(ROOT / "run_auto.py")]
        cmd += list(args)
        return subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=180,
        )

    def test_run_auto_recommend_json_does_not_execute(self):
        proc = self._run("--recommend", "routability", "--json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["goal"], "routability")
        self.assertEqual(payload["objective"], "route_aware")
        self.assertFalse(payload["intent_plan"])
        self.assertFalse(payload["route_repair"])
        self.assertIn("expected_tradeoff", payload)
        self.assertNotIn("placement", payload)
        self.assertNotIn("certificate", payload)
        self.assertIn("policy goal=routability", proc.stderr)
        self.assertNotIn("scenario=", proc.stderr)

    def test_run_auto_recommend_human_output(self):
        proc = self._run("--recommend", "intent_fidelity")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("intent_fidelity", proc.stdout)
        self.assertIn("--intent-plan", proc.stdout)
        self.assertIn("policy goal=intent_fidelity", proc.stderr)
        self.assertNotIn("placement_digest", proc.stdout)
        self.assertNotIn("certificate", proc.stdout)

    def test_run_auto_recommend_and_policy_are_mutually_exclusive(self):
        proc = self._run("--recommend", "balanced", "--policy", "balanced")
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout.strip(), "")
        self.assertIn("mutually exclusive", proc.stderr)

    def test_run_auto_recommend_invalid_goal_exits_2(self):
        proc = self._run("--recommend", "bogus")
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout.strip(), "")
        self.assertIn("--recommend", proc.stderr)

    def test_policy_module_check_defaults(self):
        proc = self._run("--check-defaults", module=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("defaults OK", proc.stdout)
        self.assertIn("proxy", proc.stdout)

    def test_policy_module_recommend_experimental_json(self):
        proc = self._run("--recommend", "experimental", "--json", module=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["goal"], "experimental")
        self.assertFalse(payload["recommended"])
        self.assertEqual(payload["objective"], "tuned")

    def test_policy_module_invalid_goal_exits_2(self):
        proc = self._run("--recommend", "bogus", module=True)
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout.strip(), "")
        self.assertIn("--recommend", proc.stderr)

    def test_policy_module_list(self):
        proc = self._run("--list", module=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        lines = [line for line in proc.stdout.strip().splitlines() if line.strip()]
        self.assertEqual(len(lines), len(EXPECTED_GOALS))
        for goal in EXPECTED_GOALS:
            self.assertIn(goal, proc.stdout)


class PoliciesDocTests(unittest.TestCase):
    def test_policies_md_has_decision_table_prohibitions_and_defaults(self):
        path = ROOT / "policies.md"
        self.assertTrue(path.is_file(), "policies.md is missing")
        text = path.read_text(encoding="utf-8")
        self.assertIn("# P4.8", text)
        self.assertIn("| goal |", text)
        for goal in EXPECTED_GOALS:
            self.assertIn(goal, text)
        self.assertIn("禁止", text)
        self.assertIn("assert_defaults", text)
        self.assertIn("tuned", text)
        self.assertIn("DRC", text)
        self.assertIn("--recommend", text)


if __name__ == "__main__":
    unittest.main()
