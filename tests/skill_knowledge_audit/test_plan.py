from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from .helpers import SKILL_ROOT, load_json, write

from ska_impl.common import AuditError
from ska_impl.plan import (build_plan, load_catalog, normalise_intent,
                                       write_cache)
from ska_impl.scan import scan_root

CATALOG = load_catalog(Path(__file__).resolve().parents[2] / "easycirq"
                       / "scripts" / "skill_knowledge_audit" / "catalog"
                       / "topics.json")
SCAN = scan_root(SKILL_ROOT)
ALLOWED_ACTIONS = {
    "read_skill", "write_eda", "read_eda", "network", "install",
    "wait_user_approval", "review_only", "offline_analysis", "order_parts",
}


def plan_for(intent, **kwargs):
    result, _ = build_plan(SKILL_ROOT, intent, CATALOG, scan_context=SCAN,
                           **kwargs)
    return result


def paths(items):
    return {item["path"] for item in items}


class BomOnly(unittest.TestCase):
    def test_bom_plan_is_minimal_and_honest_about_stage(self):
        plan = plan_for({
            "task_type": "bom_only", "stage": "unknown",
            "deliverables": ["bom"], "constraints": ["only check BOM"],
            "eda_available": False,
        })
        required = paths(plan["required"])
        self.assertIn("references/part-selection.md", required)
        self.assertIn("references/lcsc-sourcing.md", required)
        self.assertIn("references/evidence.md", required)
        excluded = paths(plan["excluded"])
        self.assertIn("references/pcb-routing-details.md", excluded)
        self.assertIn("references/thermal/topic.md", excluded)
        self.assertNotIn("references/pcb-routing-details.md", required)
        self.assertFalse(set(required) & {
            "references/pcb-execution.md", "references/pcb-routing-strategy.md"})
        codes = {item["code"] for item in plan["unknown"]}
        self.assertIn("stage_unspecified", codes)
        contract = plan["execution_contract"]
        self.assertFalse(contract["writes_allowed"])
        self.assertNotIn("write_eda", contract["actions"])
        self.assertNotIn("wait_user_approval", contract["actions"])


class ReviewAndOffline(unittest.TestCase):
    def test_review_only_does_not_require_eda_or_writes(self):
        plan = plan_for({
            "task_type": "review_only", "stage": "check",
            "deliverables": ["review-report"], "eda_available": False,
            "constraints": ["only review, do not edit the project"],
        })
        self.assertIn("references/review.md", paths(plan["required"]))
        contract = plan["execution_contract"]
        self.assertFalse(contract["writes_allowed"])
        self.assertFalse(contract["eda_required"])
        self.assertNotIn("read_eda", contract["actions"])
        self.assertNotIn("write_eda", contract["actions"])
        self.assertNotIn("eda_unavailable",
                         {item["code"] for item in plan["unknown"]})

    def test_pcb_with_eda_forbidden_reports_eda_unavailable_and_no_writes(self):
        plan = plan_for({
            "task_type": "pcb_layout", "stage": "layout",
            "deliverables": ["placement-plan"], "eda_available": False,
            "constraints": ["user explicitly forbids EDA"],
        })
        codes = {item["code"] for item in plan["unknown"]}
        self.assertIn("eda_unavailable", codes)
        contract = plan["execution_contract"]
        self.assertFalse(contract["writes_allowed"])
        self.assertNotIn("read_eda", contract["actions"])
        self.assertNotIn("write_eda", contract["actions"])
        self.assertIn("offline_analysis", contract["actions"])
        excluded = paths(plan["excluded"])
        self.assertIn("references/eda-execution.md", excluded)


class ApprovalBoundaries(unittest.TestCase):
    def _route(self, pending, autonomous):
        return plan_for({
            "task_type": "pcb_route", "stage": "route",
            "deliverables": ["pcb"], "eda_available": True,
            "autonomous_authorized": autonomous,
            "user_decision_pending": pending,
        })

    def test_autonomous_has_no_automatic_approval_wait(self):
        plan = self._route([], True)
        self.assertNotIn("wait_user_approval",
                         plan["execution_contract"]["actions"])
        self.assertTrue(plan["execution_contract"]["writes_allowed"])

    def test_user_requested_boundary_is_a_wait(self):
        plan = self._route(["before_route"], False)
        self.assertIn("wait_user_approval",
                      plan["execution_contract"]["actions"])
        self.assertEqual(plan["execution_contract"]["approval_gates"],
                         ["before_route"])

    def test_scope_change_is_a_decision_not_an_automatic_wait(self):
        plan = self._route(["scope_change"], True)
        self.assertNotIn("wait_user_approval",
                         plan["execution_contract"]["actions"])
        self.assertIn("scope_change",
                      plan["execution_contract"]["approval_gates"])
        self.assertTrue(plan["execution_contract"]["decisions_required"])


class Budget(unittest.TestCase):
    def test_required_documents_are_never_trimmed(self):
        plan = plan_for({
            "task_type": "schematic_new", "stage": "schematic",
            "deliverables": ["schematic"], "eda_available": True,
            "budget_chars": 1200,
            "constraints": ["single page schematic, sensor only"],
        })
        budget = plan["budget"]
        self.assertEqual(budget["status"], "incomplete")
        self.assertGreater(budget["required_chars"], budget["limit_chars"])
        self.assertTrue(budget["uncovered"])
        self.assertTrue(plan["required"])
        self.assertIn("budget_insufficient",
                      {item["code"] for item in plan["unknown"]})
        self.assertFalse(plan["ok"])

    def test_invalid_budget_values_fail_closed(self):
        for value in (True, 1.5, 0, -5, "100"):
            with self.subTest(value=value):
                with self.assertRaises(AuditError):
                    normalise_intent({"task_type": "bom_only",
                                      "budget_chars": value}, CATALOG)


class CacheAndUnknowns(unittest.TestCase):
    def test_hash_mismatch_is_stale(self):
        plan = plan_for({
            "task_type": "schematic_edit", "stage": "schematic",
            "already_read": [{
                "path": "easycirq/references/evidence.md",
                "sha256": "0" * 64,
                "rules_version": CATALOG["catalog_version"],
                "scope": "probe",
            }],
        })
        codes = {item["code"] for item in plan["unknown"]}
        self.assertIn("already_read_stale", codes)
        self.assertTrue(plan["cache"]["invalidated"])

    def test_rules_version_change_invalidates_cache(self):
        sha = hashlib.sha256(
            (SKILL_ROOT / "references" / "evidence.md").read_bytes()).hexdigest()
        plan = plan_for({
            "task_type": "pcb_route", "stage": "route",
            "already_read": [{
                "path": "easycirq/references/evidence.md",
                "sha256": sha,
                "rules_version": "2026-01-01.0",
                "scope": "old",
            }],
        })
        codes = {item["code"] for item in plan["unknown"]}
        self.assertIn("cache_invalidated", codes)

    def test_cache_roundtrip_and_hit(self):
        intent = {
            "task_type": "bom_only", "stage": "read",
            "already_read": [{
                "path": "easycirq/references/evidence.md",
                "sha256": hashlib.sha256(
                    (SKILL_ROOT / "references" / "evidence.md").read_bytes()
                ).hexdigest(),
                "rules_version": CATALOG["catalog_version"],
                "scope": "bom",
            }],
        }
        plan = plan_for(intent)
        payload = write_cache(
            "unused.json", plan["intent"], {"records": SCAN[1]["records"]})
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cache.json"
            write(path, json.dumps(payload))
            plan2 = plan_for(intent, cache_in=str(path))
        self.assertEqual(plan2["cache_in"]["status"], "hit")


class SchematicEda(unittest.TestCase):
    def test_schematic_requires_read_and_reports_unavailable_eda(self):
        plan = plan_for({
            "task_type": "schematic_edit", "stage": "schematic",
            "deliverables": ["schematic"], "eda_available": True,
        })
        actions = plan["execution_contract"]["actions"]
        self.assertIn("read_eda", actions)
        self.assertIn("write_eda", actions)

        plan = plan_for({
            "task_type": "schematic_edit", "stage": "schematic",
            "deliverables": ["schematic"], "eda_available": False,
        })
        self.assertIn("eda_unavailable",
                      {item["code"] for item in plan["unknown"]})
        self.assertFalse(plan["execution_contract"]["writes_allowed"])
        self.assertNotIn("read_eda", plan["execution_contract"]["actions"])
        self.assertNotIn("write_eda", plan["execution_contract"]["actions"])


class DomainRouting(unittest.TestCase):
    def test_unspecified_domain_is_reported(self):
        plan = plan_for({
            "task_type": "schematic_new", "stage": "schematic",
            "deliverables": ["schematic"],
            "constraints": ["one sensor, interface unknown, single page"],
        })
        self.assertIn("domain_unspecified",
                      {item["code"] for item in plan["unknown"]})
        self.assertNotIn("references/digital.md", paths(plan["required"]))

    def test_mcu_keyword_adds_digital_topic(self):
        plan = plan_for({
            "task_type": "schematic_new", "stage": "schematic",
            "deliverables": ["schematic"],
            "constraints": ["ESP32-S3 MCU with USB-C and I2C sensor"],
        })
        self.assertIn("references/digital.md", paths(plan["required"]))

    def test_every_action_is_from_the_declared_taxonomy(self):
        plan = plan_for({"task_type": "full_product", "stage": "requirements",
                         "deliverables": ["schematic", "pcb"],
                         "eda_available": True, "autonomous_authorized": True})
        actions = set(plan["execution_contract"]["actions"])
        self.assertTrue(actions <= ALLOWED_ACTIONS)
        self.assertIn("read_skill", actions)
        self.assertIn("write_eda", actions)
        self.assertNotIn("wait_user_approval", actions)


if __name__ == "__main__":
    unittest.main()
