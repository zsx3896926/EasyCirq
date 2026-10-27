from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from .helpers import BENCH, SKILL_ROOT, load_json, write

from skill_knowledge_audit.bench import (load_scenarios, evaluate_plan,
                                        run_benchmark, run_transforms)
from skill_knowledge_audit.plan import build_plan, load_catalog

PACKAGE = BENCH.parents[1] / "design-hardware" / "scripts" / "skill_knowledge_audit"
CATALOG = load_catalog(PACKAGE / "catalog" / "topics.json")
SCENARIOS, WARNINGS = load_scenarios(BENCH / "scenarios")


class Scenarios(unittest.TestCase):
    def test_twenty_frozen_scenarios_with_holdout(self):
        self.assertEqual(len(SCENARIOS), 20)
        self.assertEqual(sum(1 for item in SCENARIOS
                             if item["_split"] == "dev"), 15)
        self.assertEqual(sum(1 for item in SCENARIOS
                             if item["_split"] == "holdout"), 5)
        ids = [item["id"] for item in SCENARIOS]
        self.assertEqual(len(ids), len(set(ids)))

    def test_every_referenced_path_exists(self):
        for scenario in SCENARIOS:
            expected = scenario["expected"]
            for key in ("must_include", "must_exclude", "may_include"):
                for path in expected[key]:
                    rel = path.replace("design-hardware/", "", 1)
                    self.assertTrue((SKILL_ROOT / rel).is_file(),
                                    f"{scenario['id']}: missing {path}")

    def test_implementation_does_not_branch_on_scenario_ids(self):
        package = PACKAGE / "skill_knowledge_audit"
        for path in package.glob("*.py"):
            text = path.read_text(encoding="utf-8")
            for scenario in SCENARIOS:
                self.assertNotIn(scenario["id"], text,
                                 f"{path.name} hardcodes {scenario['id']}")

    def test_duplicate_scenario_ids_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "dev.json"
            data = load_json(BENCH / "scenarios" / "dev.json")
            data["scenarios"].append(copy.deepcopy(data["scenarios"][0]))
            write(path, json.dumps(data))
            with self.assertRaises(Exception):
                load_scenarios(path)


class Benchmark(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = run_benchmark(SKILL_ROOT, SCENARIOS, CATALOG,
                                   stability=True)

    def test_all_scenarios_pass_with_zero_critical_misses(self):
        self.assertTrue(self.result["ok"])
        self.assertEqual(self.result["scenarios"]["passed"], 20)
        self.assertEqual(self.result["metrics"]["missing_critical_total"], 0)
        self.assertEqual(self.result["metrics"]["required_recall"], 1.0)
        self.assertEqual(self.result["metrics"]["forbidden_selected_total"], 0)
        self.assertEqual(self.result["metrics"]["forbidden_actions_total"], 0)
        self.assertEqual(
            self.result["metrics"]["unknown_expected_missing_total"], 0)
        self.assertEqual(self.result["metrics"]["stable_scenarios"], 20)
        self.assertEqual(self.result["scenarios"]["holdout"], 5)

    def test_reading_is_smaller_than_the_all_markdown_baseline(self):
        for item in self.result["results"]:
            self.assertLess(item["selected_bytes"],
                            item["baseline_all_markdown_bytes"], item["scenario"])
            self.assertFalse(item["pass"] is False)

    def test_missing_critical_constraint_fails_a_scenario(self):
        scenario = copy.deepcopy(SCENARIOS[0])
        scenario["expected"]["must_include"] = [
            "design-hardware/references/not-a-real-doc.md"]
        plan, context = build_plan(SKILL_ROOT, scenario["intent"], CATALOG)
        metrics = evaluate_plan(
            scenario, plan,
            sum(record.bytes for record in context["index"]["records"].values()))
        self.assertFalse(metrics["pass"])
        self.assertTrue(metrics["missing_critical"])

    def test_forbidden_reading_and_action_fail_a_scenario(self):
        scenario = copy.deepcopy(SCENARIOS[0])
        scenario["expected"]["forbidden_plan_actions"] = ["read_skill"]
        scenario["expected"]["must_exclude"] = ["design-hardware/SKILL.md"]
        plan, context = build_plan(SKILL_ROOT, scenario["intent"], CATALOG)
        metrics = evaluate_plan(
            scenario, plan,
            sum(record.bytes for record in context["index"]["records"].values()))
        self.assertFalse(metrics["pass"])
        self.assertTrue(metrics["forbidden_actions"])
        self.assertTrue(metrics["forbidden_selected"])


class Transforms(unittest.TestCase):
    def test_unrelated_document_changes_do_not_break_required_coverage(self):
        scenario = next(item for item in SCENARIOS
                        if item["_split"] == "dev")
        result = run_transforms(SKILL_ROOT, scenario, CATALOG)
        self.assertTrue(result["ok"], result)
        names = {item["transform"] for item in result["transforms"]}
        self.assertIn("smaller_budget", names)
        self.assertIn("content_hash_changed", names)


if __name__ == "__main__":
    unittest.main()
