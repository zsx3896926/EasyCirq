"""Strict JSON-Schema input validation: extra fields, wrong types, NaN, booleans."""

from __future__ import annotations

import copy
import unittest

from task_launcher_bound_tests import support


class SchemaBase(support.BoundTestCase):
    def arguments(self, harness: support.TaskHarness) -> dict:
        return copy.deepcopy(support.start_arguments(harness))

    def assert_invalid_arguments(self, client: support.MCPClient, error: dict) -> None:
        self.assertEqual(error["code"], "INVALID_ARGUMENTS", error)
        self.assertTrue(error["message"])


class TaskStartSchemaTests(SchemaBase):
    def test_minimal_valid_arguments_are_accepted(self) -> None:
        harness = self.harness()
        client = self.client(harness)
        payload = self.tool_ok(client, "task_start", self.arguments(harness))
        self.assertEqual(payload["task_id"], harness.task_id)
        self.assertEqual(payload["versions"], harness.summary["versions"])

    def test_missing_required_field_is_rejected(self) -> None:
        harness = self.harness()
        client = self.client(harness)
        arguments = self.arguments(harness)
        del arguments["client"]
        error = self.assert_tool_error(
            client, "task_start", arguments, code="INVALID_ARGUMENTS"
        )
        self.assertIn("client", error["message"])

    def test_unknown_top_level_field_is_rejected(self) -> None:
        harness = self.harness()
        client = self.client(harness)
        arguments = self.arguments(harness)
        arguments["verdict"] = "PASS"
        self.assert_tool_error(
            client, "task_start", arguments, code="INVALID_ARGUMENTS"
        )

    def test_unknown_nested_client_field_is_rejected(self) -> None:
        harness = self.harness()
        client = self.client(harness)
        arguments = self.arguments(harness)
        arguments["client"]["api_key"] = "secret"
        self.assert_tool_error(
            client, "task_start", arguments, code="INVALID_ARGUMENTS"
        )

    def test_unknown_toolchain_field_is_rejected(self) -> None:
        harness = self.harness()
        client = self.client(harness)
        arguments = self.arguments(harness)
        arguments["toolchain"]["edition"] = "pro"
        self.assert_tool_error(
            client, "task_start", arguments, code="INVALID_ARGUMENTS"
        )

    def test_smuggled_snapshot_field_is_rejected(self) -> None:
        harness = self.harness()
        client = self.client(harness)
        arguments = self.arguments(harness)
        arguments["context"]["snapshot"] = {"files": [], "snapshot_sha256": "0" * 64}
        self.assert_tool_error(
            client, "task_start", arguments, code="INVALID_ARGUMENTS"
        )

    def test_unknown_goal_field_and_bad_intent_are_rejected(self) -> None:
        harness = self.harness()
        client = self.client(harness)
        for mutate in (
            lambda args: args["goal"].__setitem__("intent", "execute"),
            lambda args: args["goal"].__setitem__("report", "PASS"),
        ):
            arguments = self.arguments(harness)
            mutate(arguments)
            self.assert_tool_error(
                client, "task_start", arguments, code="INVALID_ARGUMENTS"
            )

    def test_client_wrong_type_is_rejected(self) -> None:
        harness = self.harness()
        client = self.client(harness)
        arguments = self.arguments(harness)
        arguments["client"] = "bound-tests/0.0.0"
        self.assert_tool_error(
            client, "task_start", arguments, code="INVALID_ARGUMENTS"
        )

    def test_toolchain_wrong_type_is_rejected(self) -> None:
        harness = self.harness()
        client = self.client(harness)
        arguments = self.arguments(harness)
        arguments["toolchain"] = "1.0.2"
        self.assert_tool_error(
            client, "task_start", arguments, code="INVALID_ARGUMENTS"
        )

    def test_task_id_with_chinese_or_space_is_rejected(self) -> None:
        harness = self.harness()
        client = self.client(harness)
        for bad_task_id in ("任务一", "task one", "../escape", ""):
            arguments = self.arguments(harness)
            arguments["task_id"] = bad_task_id
            self.assert_tool_error(
                client, "task_start", arguments, code="INVALID_ARGUMENTS"
            )
        self.assertEqual(self._status_state(harness), "CREATED")

    def test_boolean_cannot_impersonate_integer_limit(self) -> None:
        harness = self.harness()
        client = self.client(harness)
        arguments = self.arguments(harness)
        arguments["limits"] = {"max_tool_calls": True}
        self.assert_tool_error(
            client, "task_start", arguments, code="INVALID_ARGUMENTS"
        )

    def test_nan_limit_is_rejected(self) -> None:
        harness = self.harness()
        client = self.client(harness)
        arguments = self.arguments(harness)
        arguments["limits"] = {"max_tool_calls": float("nan")}
        # ``json.dumps`` emits the NaN literal; the supervisor must not accept it.
        response = client.call_tool("task_start", arguments)
        self.assertTrue(response["result"]["isError"])
        self.assertEqual(
            response["result"]["structuredContent"]["error"]["code"], "INVALID_ARGUMENTS"
        )

    def test_unknown_limit_field_and_out_of_range_limit_are_rejected(self) -> None:
        harness = self.harness()
        client = self.client(harness)
        for limits in (
            {"max_tool_calls": 5, "max_writes": 1},
            {"timeout_s": 5},
            {"max_steps": 0},
        ):
            arguments = self.arguments(harness)
            arguments["limits"] = limits
            self.assert_tool_error(
                client, "task_start", arguments, code="INVALID_ARGUMENTS"
            )

    def test_null_snapshot_requires_missing_fields(self) -> None:
        harness = self.harness()
        client = self.client(harness)
        arguments = self.arguments(harness)
        arguments["context"]["snapshot_sha256"] = None
        arguments["context"].pop("missing_fields", None)
        self.assert_tool_error(
            client, "task_start", arguments, code="INVALID_ARGUMENTS"
        )

    def test_selection_item_requires_declared_shape(self) -> None:
        harness = self.harness()
        client = self.client(harness)
        arguments = self.arguments(harness)
        arguments["context"]["selection"] = [{"kind": "component"}]
        self.assert_tool_error(
            client, "task_start", arguments, code="INVALID_ARGUMENTS"
        )

    def test_rejected_task_start_does_not_advance_state(self) -> None:
        harness = self.harness()
        client = self.client(harness)
        arguments = self.arguments(harness)
        arguments["unexpected"] = 1
        self.assert_tool_error(
            client, "task_start", arguments, code="INVALID_ARGUMENTS"
        )
        self.assertEqual(self._status_state(harness), "CREATED")
        payload = self.tool_ok(client, "task_start", self.arguments(harness))
        self.assertEqual(payload["state"], "STARTED")

    # -- helpers ----------------------------------------------------------
    def _status_state(self, harness: support.TaskHarness) -> str | None:
        path = harness.task_dir / "status.json"
        if not path.is_file():
            return None
        return support.read_json(path)["state"]


class OtherToolSchemaTests(SchemaBase):
    def test_snapshot_read_rejects_extra_top_level_field(self) -> None:
        harness = self.harness()
        client = self.client(harness)
        self.start_task(client, harness)
        self.assert_tool_error(
            client,
            "snapshot_read",
            {"scope": {"kind": "full"}, "snapshot": {"files": []}},
            code="INVALID_ARGUMENTS",
        )

    def test_snapshot_read_scope_accepts_only_kind_and_designators(self) -> None:
        harness, client = self.started()
        self.assert_tool_error(
            client,
            "snapshot_read",
            {"scope": {"kind": "full", "files": [{"path": "x"}]}},
            code="INVALID_ARGUMENTS",
        )

    def test_snapshot_read_rejects_unknown_kind(self) -> None:
        harness, client = self.started()
        self.assert_tool_error(
            client, "snapshot_read", {"scope": {"kind": "partial"}}, code="INVALID_ARGUMENTS"
        )

    def test_snapshot_read_rejects_undeclared_designator(self) -> None:
        harness, client = self.started()
        self.assert_tool_error(
            client,
            "snapshot_read",
            {"scope": {"kind": "selection", "designators": ["U9"]}},
            code="INVALID_ARGUMENTS",
        )

    def test_snapshot_read_rejects_non_object_arguments(self) -> None:
        harness, client = self.started()
        self.assert_tool_error(
            client, "snapshot_read", "full", code="INVALID_ARGUMENTS"
        )

    def test_run_offline_audit_rejects_unknown_detail(self) -> None:
        harness, client = self.started()
        self.tool_ok(client, "snapshot_read", {"scope": {"kind": "full"}})
        self.assert_tool_error(
            client, "run_offline_audit", {"detail": "deep"}, code="INVALID_ARGUMENTS"
        )

    def test_run_offline_audit_rejects_unknown_field(self) -> None:
        harness, client = self.started()
        self.tool_ok(client, "snapshot_read", {"scope": {"kind": "full"}})
        self.assert_tool_error(
            client,
            "run_offline_audit",
            {"detail": "summary", "snapshot_sha256": "0" * 64},
            code="INVALID_ARGUMENTS",
        )

    def test_evidence_emit_takes_no_fields(self) -> None:
        harness, client = self.started()
        result = client.call_tool("evidence_emit", {"evidence": {"verdict": "PASS"}})
        self.assertTrue(result["result"]["isError"])
        self.assertEqual(
            result["result"]["structuredContent"]["error"]["code"], "INVALID_ARGUMENTS"
        )

    def test_finalize_takes_no_fields(self) -> None:
        harness, client = self.started()
        result = client.call_tool("finalize", {"report": {"verdict": "PASS"}})
        self.assertTrue(result["result"]["isError"])
        self.assertEqual(
            result["result"]["structuredContent"]["error"]["code"], "INVALID_ARGUMENTS"
        )

    def test_task_abort_requires_reason_and_rejects_extra_fields(self) -> None:
        harness, client = self.started()
        self.assert_tool_error(client, "task_abort", {}, code="INVALID_ARGUMENTS")
        self.assert_tool_error(
            client,
            "task_abort",
            {"reason": "user cancelled", "state": "FINALIZED"},
            code="INVALID_ARGUMENTS",
        )

    def test_missing_field_detail_names_the_path(self) -> None:
        harness = self.harness()
        client = self.client(harness)
        arguments = self.arguments(harness)
        del arguments["context"]["document"]
        error = self.assert_tool_error(
            client, "task_start", arguments, code="INVALID_ARGUMENTS"
        )
        self.assertIn("context", error["detail"].get("path", ""))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
