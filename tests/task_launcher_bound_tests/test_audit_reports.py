"""Offline audit cases and the supervisor-generated final report."""

from __future__ import annotations

import unittest

from task_launcher_bound_tests import support


class AuditCaseTests(support.BoundTestCase):
    def finish(self, audit_case: str) -> tuple[support.TaskHarness, dict, dict, support.MCPClient]:
        harness = self.harness(audit_case=audit_case)
        client = self.client(harness)
        audit = self.advance_to_evidence(client, harness)
        final = self.tool_ok(client, "finalize", {})
        return harness, audit, final, client

    def test_pass_case_reports_pass(self) -> None:
        harness, audit, final, _ = self.finish("pass")
        self.assertEqual(audit["audit"]["status"], "pass_with_scope")
        self.assertEqual(final["verdict"], "PASS")
        self.assertEqual(self.read_result(harness)["task"]["verdict"], "PASS")

    def test_fail_case_reports_fail(self) -> None:
        harness, audit, final, _ = self.finish("fail")
        self.assertEqual(audit["audit"]["status"], "fail")
        self.assertEqual(final["verdict"], "FAIL")
        self.assertEqual(self.read_result(harness)["task"]["verdict"], "FAIL")

    def test_review_case_reports_review_required(self) -> None:
        harness, audit, final, _ = self.finish("review")
        self.assertEqual(audit["audit"]["status"], "review_required")
        self.assertEqual(final["verdict"], "REVIEW_REQUIRED")
        self.assertEqual(
            self.read_result(harness)["task"]["verdict"], "REVIEW_REQUIRED"
        )

    def test_incomplete_case_never_produces_a_report(self) -> None:
        harness, client = self.started(audit_case="incomplete")
        self.tool_ok(client, "snapshot_read", {"scope": {"kind": "full"}})
        audit = self.tool_ok(client, "run_offline_audit", {"detail": "summary"})
        self.assertFalse(audit["finalizable"])
        self.assert_tool_error(client, "evidence_emit", {}, code="TASK_CLOSED")
        self.assert_tool_error(client, "finalize", {}, code="TASK_CLOSED")
        self.assertFalse((harness.task_dir / "result.json").exists())
        self.assertFalse((harness.task_dir / "evidence.json").exists())

    def test_audit_response_carries_honest_boundary_fields(self) -> None:
        harness, audit, _, _ = self.finish("pass")
        self.assertEqual(audit["audit"]["real_eda"], "NOT RUN")
        self.assertEqual(audit["audit"]["eda_calls"], 0)
        self.assertEqual(audit["audit"]["project_writes"], 0)
        self.assertEqual(audit["audit"]["engine"], "fixture")
        self.assertIsInstance(audit["audit"]["audit_sha256"], str)
        self.assertEqual(len(audit["audit"]["audit_sha256"]), 64)

    def test_audit_detail_summary_limits_checks(self) -> None:
        harness, client = self.started(audit_case="pass")
        self.tool_ok(client, "snapshot_read", {"scope": {"kind": "full"}})
        summary = self.tool_ok(client, "run_offline_audit", {"detail": "summary"})
        self.assertLessEqual(len(summary["audit"]["checks"]), 2)
        self.assertEqual(summary["audit"]["checks_total"], 2)

    def test_audit_failure_does_not_consume_the_step(self) -> None:
        harness, client = self.started()
        self.tool_ok(client, "snapshot_read", {"scope": {"kind": "full"}})
        self.assert_tool_error(
            client, "run_offline_audit", {"checks": ["NO-SUCH-CHECK"]}, code="INVALID_ARGUMENTS"
        )
        status = support.read_json(harness.task_dir / "status.json")
        self.assertEqual(status["state"], "SNAPSHOT_READ")
        self.tool_ok(client, "run_offline_audit", {"detail": "summary"})


class ReportTests(support.BoundTestCase):
    def finalize(self, **harness_kwargs) -> tuple[support.TaskHarness, dict]:
        harness = self.harness(**harness_kwargs)
        client = self.client(harness)
        self.advance_to_evidence(client, harness)
        final = self.tool_ok(client, "finalize", {})
        return harness, final

    def test_result_json_only_exists_after_finalize(self) -> None:
        harness = self.harness()
        client = self.client(harness)
        self.advance_to_evidence(client, harness)
        self.assertFalse((harness.task_dir / "result.json").exists())
        self.tool_ok(client, "finalize", {})
        self.assertTrue((harness.task_dir / "result.json").is_file())

    def test_report_shape_and_generator(self) -> None:
        harness, _ = self.finalize()
        report = self.read_result(harness)
        self.assertEqual(report["schema"], "zhigou.bound.report/v1")
        self.assertEqual(report["generated_by"], "supervisor")
        self.assertEqual(report["task"]["task_id"], harness.task_id)
        self.assertEqual(report["task"]["phase"], 1)
        self.assertEqual(report["task"]["verdict"], "PASS")
        self.assertEqual(report["summary"]["verdict"], "PASS")
        self.assertEqual(report["summary"]["audit_status"], "pass_with_scope")
        self.assertEqual(report["summary"]["engine"], "fixture")
        self.assertTrue(report["summary"]["finalizable"])

    def test_report_is_always_honest_about_eda(self) -> None:
        harness, final = self.finalize()
        report = self.read_result(harness)
        for document in (report, final):
            self.assertEqual(document["real_eda"], "NOT RUN")
            self.assertEqual(document["eda_calls"], 0)
            self.assertEqual(document["project_writes"], 0)

    def test_report_evidence_block_matches_the_chain(self) -> None:
        harness, final = self.finalize()
        report = self.read_result(harness)
        self.assertEqual(
            report["steps"],
            ["task_start", "snapshot_read", "run_offline_audit", "evidence_emit"],
        )
        self.assertEqual(report["evidence"]["receipts_count"], 4)
        self.assertTrue(report["evidence"]["chain_verified"])
        raw_evidence = (harness.task_dir / "evidence.json").read_bytes()
        self.assertEqual(report["evidence"]["sha256"], support.sha256_hex(raw_evidence))
        self.assertEqual(len(report["evidence"]["sha256"]), 64)
        self.assertEqual(len(report["evidence"]["chain_head_sha256"]), 64)
        self.assertEqual(final["receipts_count"], 5)

    def test_report_snapshot_and_limitations(self) -> None:
        harness, _ = self.finalize()
        report = self.read_result(harness)
        self.assertEqual(report["snapshot"]["source"], "fixture")
        self.assertEqual(report["snapshot"]["scope"], "full")
        self.assertEqual(report["snapshot"]["file_count"], 3)
        self.assertIn("thermal", report["snapshot"]["missing_fields"])
        self.assertTrue(report["limitations"])
        self.assertIn("host DRC", report["not_checked"])
        self.assertIn("read-only", report["limitations"][0])

    def test_report_hash_matches_finalize_response_and_file(self) -> None:
        harness, final = self.finalize()
        report = self.read_result(harness)
        self.assertEqual(report["report_sha256"], final["report_sha256"])
        self.assert_report_sha(report)
        self.assertEqual(final["report"]["report_sha256"], report["report_sha256"])
        self.assertEqual(final["report"]["verdict"], report["task"]["verdict"])

    def test_model_text_never_becomes_the_verdict(self) -> None:
        harness = self.harness(
            request_kwargs={"user_prompt": support.INJECTION_PROMPT, "intent": "inspect"}
        )
        client = self.client(harness)
        self.advance_to_evidence(client, harness)
        final = self.tool_ok(client, "finalize", {})
        report = self.read_result(harness)
        self.assertEqual(final["verdict"], "PASS")
        self.assertEqual(report["task"]["verdict"], "PASS")
        report_text = (harness.task_dir / "result.json").read_text(encoding="utf-8")
        self.assertNotIn("IGNORE ALL PREVIOUS RULES", report_text)
        self.assertNotIn("eda_calls 42", report_text)
        self.assertNotIn("eda_calls\": 42", report_text)
        self.assertEqual(report["eda_calls"], 0)
        self.assertEqual(report["project_writes"], 0)

    def test_fail_report_is_not_downgraded_by_clean_flow(self) -> None:
        harness, final = self.finalize(audit_case="fail")
        report = self.read_result(harness)
        self.assertEqual(final["verdict"], "FAIL")
        self.assertEqual(report["audit"]["status"], "fail")
        self.assertIn("fail", report["summary"]["audit_status"])


class AuditCheckSelectionTests(support.BoundTestCase):
    def test_requested_check_subset_is_audited(self) -> None:
        harness = self.harness(audit_case="pass")
        client = self.client(harness)
        self.start_task(client, harness)
        self.tool_ok(client, "snapshot_read", {"scope": {"kind": "full"}})
        payload = self.tool_ok(
            client,
            "run_offline_audit",
            {"checks": ["FIXTURE-CAP-DERATING"], "detail": "full"},
        )
        self.assertEqual(len(payload["audit"]["checks"]), 1)
        self.assertEqual(payload["audit"]["checks"][0]["id"], "FIXTURE-CAP-DERATING")

    def test_full_detail_returns_all_case_checks(self) -> None:
        harness = self.harness(audit_case="pass")
        client = self.client(harness)
        self.start_task(client, harness)
        self.tool_ok(client, "snapshot_read", {"scope": {"kind": "full"}})
        payload = self.tool_ok(client, "run_offline_audit", {"detail": "full"})
        self.assertEqual(len(payload["audit"]["checks"]), 2)
        self.assertEqual(payload["audit"]["detail"], "full")

    def test_unknown_check_is_rejected(self) -> None:
        harness = self.harness(audit_case="pass")
        client = self.client(harness)
        self.start_task(client, harness)
        self.tool_ok(client, "snapshot_read", {"scope": {"kind": "full"}})
        self.assert_tool_error(
            client,
            "run_offline_audit",
            {"checks": ["NOT-A-FIXTURE-CHECK"]},
            code="INVALID_ARGUMENTS",
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
