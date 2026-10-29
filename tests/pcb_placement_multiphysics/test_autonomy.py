"""Unit tests for mp_place.autonomy (P4-J autonomous acceptance audit).

Run with:  python -m unittest tests.test_autonomy -v
"""

import copy
import json
from pathlib import Path
import tempfile
import unittest

from mp_place import autonomy, templates
from mp_place.pipeline import run_pipeline


class BuckSignoffTests(unittest.TestCase):
    """The buck template must pass the full certificate audit."""

    @classmethod
    def setUpClass(cls):
        cls.scenario = templates.instantiate("buck", seed=0)
        cls.report = run_pipeline(cls.scenario, budget_steps=800, seed=0,
                                  route_repair=True)
        cls.rerun = run_pipeline(cls.scenario, budget_steps=800, seed=0,
                                 route_repair=True)

    def audit(self, report, rerun=None):
        return autonomy.audit_report(self.scenario, report, seed=0,
                                     budget_steps=800, rerun=rerun)

    def test_buck_full_signoff(self):
        audit = self.audit(self.report, self.rerun)
        self.assertTrue(audit["ok"], msg=str(audit["failures"]))
        self.assertEqual(tuple(audit["checks"]), autonomy.CHECK_NAMES)
        for name, check in audit["checks"].items():
            self.assertTrue(check["ok"], msg="%s: %s" % (name,
                                                         check["detail"]))
        certificate = self.report["certificate"]
        self.assertEqual(certificate["schema"], autonomy.CERTIFICATE_SCHEMA)
        self.assertEqual(certificate["fixed_fields"],
                         {"routing_verified": False, "drc": "NOT RUN",
                          "eda_calls": 0})
        self.assertEqual(self.report["fixed_fields"],
                         certificate["fixed_fields"])
        self.assertEqual(certificate["placement_digest"],
                         self.report["placement_digest"])
        self.assertTrue(self.report["feasible"])
        self.assertEqual(self.report["violations"], [])
        self.assertTrue(self.report["intent_replay_ok"])
        self.assertTrue(self.report["router_certificate_consistent"])
        self.assertEqual(certificate["extra"]["seed"], 0)
        self.assertEqual(certificate["extra"]["budget_steps"], 800)
        # The certificate must survive a strict JSON round trip.
        text = json.dumps(certificate, ensure_ascii=False, allow_nan=False)
        self.assertEqual(json.loads(text), certificate)

    def test_tampered_certificate_is_detected(self):
        def tamper_fixed_fields(doc):
            doc["certificate"]["fixed_fields"]["drc"] = "PASS"

        def tamper_schema(doc):
            doc["certificate"]["schema"] = "bogus/v1"

        def tamper_digest(doc):
            doc["certificate"]["placement_digest"] = "sha256:deadbeef"

        def tamper_feasible(doc):
            doc["certificate"]["feasible"] = False

        def tamper_body(doc):
            doc["certificate"]["violations"] = ["tampered"]

        def tamper_router(doc):
            doc["certificate"]["routability"]["completion"] = 0.123

        def tamper_placement(doc):
            placement = doc["certificate"]["placement"]
            ref = sorted(placement)[0]
            placement[ref][0] = float(placement[ref][0]) + 1.0

        variants = [
            ("fixed_fields", tamper_fixed_fields, "certificate_fixed_fields"),
            ("schema", tamper_schema, "certificate_schema"),
            ("digest", tamper_digest, "placement_digest"),
            ("feasible", tamper_feasible, "feasible"),
            ("body", tamper_body, "certificate_matches_verify"),
            ("router", tamper_router, "router_certificate_consistent"),
            ("placement", tamper_placement, "placement_digest"),
        ]
        for label, mutate, expected_failure in variants:
            with self.subTest(label=label):
                tampered = copy.deepcopy(self.report)
                mutate(tampered)
                audit = self.audit(tampered)
                self.assertFalse(audit["ok"], label)
                self.assertIn(expected_failure, audit["failures"],
                              "%s: failures=%r" % (label, audit["failures"]))

    def test_tampered_report_fields_are_detected(self):
        variants = []

        def set_frame(key, value):
            def mutate(doc):
                doc[key] = value
            return mutate

        variants.append(("feasible", set_frame("feasible", False),
                         "feasible"))
        variants.append(("violations", set_frame("violations", ["tampered"]),
                         "feasible"))
        variants.append(("report_digest",
                         set_frame("placement_digest", "sha256:deadbeef"),
                         "placement_digest"))
        variants.append(("intent", set_frame("intent_replay_ok", False),
                         "intent_replay"))

        def tamper_router_flag(doc):
            doc["router_certificate_consistent"] = False

        def tamper_router_value(doc):
            doc["router"]["completion"] = 0.5

        variants.append(("router_flag", tamper_router_flag,
                         "router_certificate_consistent"))
        variants.append(("router_value", tamper_router_value,
                         "router_certificate_consistent"))
        for label, mutate, expected_failure in variants:
            with self.subTest(label=label):
                tampered = copy.deepcopy(self.report)
                mutate(tampered)
                audit = self.audit(tampered)
                self.assertFalse(audit["ok"], label)
                self.assertIn(expected_failure, audit["failures"],
                              "%s: failures=%r" % (label, audit["failures"]))

    def test_missing_certificate_fails_without_crashing(self):
        tampered = copy.deepcopy(self.report)
        del tampered["certificate"]
        audit = self.audit(tampered)
        self.assertFalse(audit["ok"])
        self.assertEqual(tuple(audit["checks"]), autonomy.CHECK_NAMES)
        self.assertIn("certificate_schema", audit["failures"])

    def test_determinism_detects_a_changed_rerun(self):
        changed = copy.deepcopy(self.rerun)
        ref = sorted(changed["placement"])[0]
        changed["placement"][ref][0] = float(changed["placement"][ref][0]) + 1.0
        audit = self.audit(self.report, changed)
        self.assertFalse(audit["ok"])
        self.assertIn("determinism", audit["failures"])
        self.assertFalse(audit["checks"]["determinism"]["ok"])

    def test_determinism_not_requested_is_reported_as_ok(self):
        audit = self.audit(self.report, rerun=None)
        self.assertTrue(audit["checks"]["determinism"]["ok"])
        self.assertIn("not requested",
                      audit["checks"]["determinism"]["detail"])


class RunAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.audit = autonomy.run_audit(template_names=["buck"], seeds=(0,),
                                       budget_steps=150, determinism=True)

    def test_single_template_audit_passes(self):
        audit = self.audit
        self.assertEqual(audit["schema"], autonomy.AUDIT_SCHEMA)
        summary = audit["summary"]
        self.assertEqual(summary["total_runs"], 1)
        self.assertEqual(summary["passed"], 1)
        self.assertEqual(summary["failed"], 0)
        self.assertEqual(summary["pass_rate"], 1.0)
        self.assertEqual(summary["templates_total"], 1)
        self.assertEqual(summary["templates_passed"], 1)
        self.assertGreaterEqual(summary["total_elapsed_s"], 0.0)
        run = audit["runs"][0]
        self.assertEqual(run["template"], "buck")
        self.assertEqual(run["seed"], 0)
        self.assertTrue(run["passed"])
        self.assertEqual(run["failures"], [])
        self.assertTrue(run["checks"]["determinism"]["ok"])
        # The whole audit must be JSON serialisable without NaN.
        json.dumps(audit, ensure_ascii=False, allow_nan=False)

    def test_default_grid_covers_the_eight_registered_templates(self):
        names = sorted(templates.template_names())
        self.assertEqual(len(names), 10)
        self.assertEqual(autonomy._normalise_templates(None), names)
        self.assertEqual(tuple(autonomy.DEFAULT_SEEDS), (0, 1))

    def test_unknown_template_is_rejected(self):
        with self.assertRaises(ValueError):
            autonomy.run_audit(template_names=["not-a-template"], seeds=(0,))

    def test_invalid_seed_is_rejected(self):
        with self.assertRaises(ValueError):
            autonomy.run_audit(template_names=["buck"], seeds=(-1,))

    def test_write_reports_creates_markdown_and_json(self):
        with tempfile.TemporaryDirectory(prefix="autonomy-test-") as folder:
            folder = Path(folder)
            paths = autonomy.write_reports(
                self.audit, folder / "report_autonomy.md",
                folder / "report_autonomy.json")
            markdown_path = Path(paths["markdown"])
            json_path = Path(paths["json"])
            self.assertTrue(markdown_path.is_file())
            self.assertTrue(json_path.is_file())
            loaded = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(loaded["schema"], autonomy.AUDIT_SCHEMA)
            self.assertEqual(loaded["summary"], self.audit["summary"])
            markdown = markdown_path.read_text(encoding="utf-8")
            self.assertIn("# P4-J", markdown)
            self.assertIn("buck", markdown)
            self.assertIn("通过率", markdown)
            self.assertIn("100.0%", markdown)
            self.assertIn("审计项定义", markdown)

    def test_markdown_lists_failed_checks(self):
        broken = copy.deepcopy(self.audit)
        run = broken["runs"][0]
        run["passed"] = False
        run["failures"] = ["feasible"]
        run["checks"]["feasible"]["ok"] = False
        broken["summary"]["passed"] = 0
        broken["summary"]["failed"] = 1
        broken["summary"]["pass_rate"] = 0.0
        markdown = autonomy.render_markdown(broken)
        self.assertIn("失败项", markdown)
        self.assertIn("FAIL", markdown)
        self.assertIn("feasible", markdown)


if __name__ == "__main__":
    unittest.main()
