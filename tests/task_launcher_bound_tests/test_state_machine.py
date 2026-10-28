"""State machine: ordering, duplicates, terminal states, incomplete audits."""

from __future__ import annotations

import unittest

from task_launcher_bound_tests import support


class OrderingTests(support.BoundTestCase):
    def test_snapshot_before_task_start_is_out_of_order(self) -> None:
        harness = self.harness()
        client = self.client(harness)
        error = self.assert_tool_error(
            client,
            "snapshot_read",
            {"scope": {"kind": "full"}},
            code="OUT_OF_ORDER",
        )
        self.assertEqual(error["detail"]["next"], "task_start")
        self.assertEqual(error["detail"]["state"], "CREATED")

    def test_audit_before_snapshot_is_not_ready(self) -> None:
        harness, client = self.started()
        error = self.assert_tool_error(
            client, "run_offline_audit", {"detail": "summary"}, code="NOT_READY"
        )
        self.assertEqual(error["detail"]["state"], "STARTED")

    def test_evidence_before_audit_is_not_ready(self) -> None:
        harness, client = self.started()
        self.tool_ok(client, "snapshot_read", {"scope": {"kind": "full"}})
        error = self.assert_tool_error(client, "evidence_emit", {}, code="NOT_READY")
        self.assertEqual(error["detail"]["state"], "SNAPSHOT_READ")

    def test_finalize_before_evidence_is_refused(self) -> None:
        harness, client = self.started()
        error = self.assert_tool_error(
            client, "finalize", {}, code=("NOT_READY", "OUT_OF_ORDER")
        )
        self.assertEqual(error["detail"]["state"], "STARTED")
        self.assertFalse((harness.task_dir / "result.json").exists())

    def test_finalize_after_evidence_but_before_receipt_write_still_works(self) -> None:
        # The canonical order is the only successful path.
        harness = self.harness()
        client = self.client(harness)
        self.full_happy_path(client, harness)
        self.assertEqual(self.read_result(harness)["task"]["verdict"], "PASS")

    def test_tool_order_is_visible_in_the_contract(self) -> None:
        harness = self.harness()
        client = self.client(harness)
        payload = self.start_task(client, harness)
        self.assertEqual(
            payload["contract"]["required_order"],
            ["task_start", "snapshot_read", "run_offline_audit", "evidence_emit", "finalize"],
        )
        self.assertTrue(payload["contract"]["read_only"])
        self.assertEqual(payload["contract"]["real_eda"], "NOT RUN")


class DuplicateStepTests(support.BoundTestCase):
    def test_duplicate_task_start_is_step_already_done(self) -> None:
        harness, client = self.started()
        self.assert_tool_error(
            client, "task_start", support.start_arguments(harness), code="STEP_ALREADY_DONE"
        )

    def test_duplicate_snapshot_read_is_step_already_done(self) -> None:
        harness, client = self.started()
        self.tool_ok(client, "snapshot_read", {"scope": {"kind": "full"}})
        self.assert_tool_error(
            client, "snapshot_read", {"scope": {"kind": "full"}}, code="STEP_ALREADY_DONE"
        )

    def test_duplicate_audit_is_step_already_done(self) -> None:
        harness, client = self.started()
        self.tool_ok(client, "snapshot_read", {"scope": {"kind": "full"}})
        self.tool_ok(client, "run_offline_audit", {"detail": "summary"})
        self.assert_tool_error(
            client, "run_offline_audit", {"detail": "summary"}, code="STEP_ALREADY_DONE"
        )

    def test_duplicate_evidence_emit_is_step_already_done(self) -> None:
        harness, client = self.started()
        self.advance_to_evidence(client, harness)
        self.assert_tool_error(client, "evidence_emit", {}, code="STEP_ALREADY_DONE")


class TerminalStateTests(support.BoundTestCase):
    def test_abort_then_any_step_is_task_closed(self) -> None:
        harness, client = self.started()
        payload = self.tool_ok(client, "task_abort", {"reason": "user cancelled"})
        self.assertEqual(payload["state"], "CANCELLED")
        self.assert_tool_error(
            client, "snapshot_read", {"scope": {"kind": "full"}}, code="TASK_CLOSED"
        )
        self.assert_tool_error(client, "finalize", {}, code="TASK_CLOSED")

    def test_abort_after_evidence_blocks_finalize(self) -> None:
        harness, client = self.started()
        self.advance_to_evidence(client, harness)
        self.tool_ok(client, "task_abort", {"reason": "operator stopped"})
        self.assert_tool_error(client, "finalize", {}, code="TASK_CLOSED")
        self.assertFalse((harness.task_dir / "result.json").exists())

    def test_second_abort_is_task_closed(self) -> None:
        harness, client = self.started()
        self.tool_ok(client, "task_abort", {"reason": "first"})
        self.assert_tool_error(
            client, "task_abort", {"reason": "second"}, code="TASK_CLOSED"
        )

    def test_second_finalize_is_task_closed(self) -> None:
        harness = self.harness()
        client = self.client(harness)
        self.full_happy_path(client, harness)
        self.assert_tool_error(client, "finalize", {}, code="TASK_CLOSED")
        self.assert_tool_error(client, "task_abort", {"reason": "late"}, code="TASK_CLOSED")

    def test_aborted_task_has_no_result_report(self) -> None:
        harness, client = self.started()
        self.tool_ok(client, "task_abort", {"reason": "no EDA authorization"})
        self.assertFalse((harness.task_dir / "result.json").exists())
        status = support.read_json(harness.task_dir / "status.json")
        self.assertEqual(status["state"], "CANCELLED")
        self.assertTrue(status["terminal"])
        self.assertEqual(status["steps"], ["task_start", "task_abort"])


class IncompleteAuditTests(support.BoundTestCase):
    def test_incomplete_audit_marks_task_incomplete(self) -> None:
        harness, client = self.started(audit_case="incomplete")
        self.tool_ok(client, "snapshot_read", {"scope": {"kind": "full"}})
        payload = self.tool_ok(client, "run_offline_audit", {"detail": "summary"})
        self.assertFalse(payload["finalizable"])
        self.assertEqual(payload["audit"]["status"], "incomplete")
        self.assertEqual(payload["state"], "INCOMPLETE")
        self.assertIn("note", payload)

    def test_incomplete_audit_cannot_emit_evidence_or_finalize(self) -> None:
        harness, client = self.started(audit_case="incomplete")
        self.tool_ok(client, "snapshot_read", {"scope": {"kind": "full"}})
        self.tool_ok(client, "run_offline_audit", {"detail": "summary"})
        self.assert_tool_error(client, "evidence_emit", {}, code="TASK_CLOSED")
        self.assert_tool_error(client, "finalize", {}, code="TASK_CLOSED")
        self.assertFalse((harness.task_dir / "result.json").exists())
        self.assertFalse((harness.task_dir / "evidence.json").exists())

    def test_fail_audit_is_finalizable_with_fail_verdict(self) -> None:
        harness, client = self.started(audit_case="fail")
        self.tool_ok(client, "snapshot_read", {"scope": {"kind": "full"}})
        audit = self.tool_ok(client, "run_offline_audit", {"detail": "summary"})
        self.assertTrue(audit["finalizable"])
        self.assertEqual(audit["audit"]["status"], "fail")
        self.tool_ok(client, "evidence_emit", {})
        final = self.tool_ok(client, "finalize", {})
        self.assertEqual(final["verdict"], "FAIL")

    def test_review_audit_maps_to_review_required(self) -> None:
        harness, client = self.started(audit_case="review")
        self.tool_ok(client, "snapshot_read", {"scope": {"kind": "full"}})
        audit = self.tool_ok(client, "run_offline_audit", {"detail": "summary"})
        self.assertEqual(audit["audit"]["status"], "review_required")
        self.tool_ok(client, "evidence_emit", {})
        final = self.tool_ok(client, "finalize", {})
        self.assertEqual(final["verdict"], "REVIEW_REQUIRED")


class StateVisibilityTests(support.BoundTestCase):
    def test_each_successful_step_reports_the_new_state(self) -> None:
        harness = self.harness()
        client = self.client(harness)
        expected = [
            ("task_start", support.start_arguments(harness), "STARTED"),
            ("snapshot_read", {"scope": {"kind": "full"}}, "SNAPSHOT_READ"),
            ("run_offline_audit", {"detail": "summary"}, "AUDIT_RUN"),
            ("evidence_emit", {}, "EVIDENCE_EMITTED"),
            ("finalize", {}, "FINALIZED"),
        ]
        for tool, arguments, state in expected:
            payload = self.tool_ok(client, tool, arguments)
            self.assertEqual(payload["state"], state, tool)
            status = support.read_json(harness.task_dir / "status.json")
            self.assertEqual(status["state"], state, tool)

    def test_status_file_tracks_remaining_steps(self) -> None:
        harness = self.harness()
        client = self.client(harness)
        self.assertTrue((harness.task_dir / "status.json").is_file())
        status = support.read_json(harness.task_dir / "status.json")
        self.assertEqual(status["state"], "CREATED")
        self.assertEqual(
            status["remaining"],
            ["task_start", "snapshot_read", "run_offline_audit", "evidence_emit", "finalize"],
        )
        self.start_task(client, harness)
        status = support.read_json(harness.task_dir / "status.json")
        self.assertEqual(status["state"], "STARTED")
        self.assertNotIn("task_start", status["remaining"])

    def test_finalized_status_is_terminal(self) -> None:
        harness = self.harness()
        client = self.client(harness)
        self.full_happy_path(client, harness)
        status = support.read_json(harness.task_dir / "status.json")
        self.assertEqual(status["state"], "FINALIZED")
        self.assertTrue(status["terminal"])
        self.assertEqual(status["remaining"], [])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
