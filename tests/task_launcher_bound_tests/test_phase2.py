"""Phase 2 surface: offline plan/precheck only, apply/readback never authorized."""

from __future__ import annotations

import unittest

from task_launcher_bound_tests import support

PLAN = {
    "objective": "Derating review of the 5 V rail (offline fixture)",
    "changes": [{"target": "C1", "action": "raise the voltage rating to 25 V"}],
    "rollback": "restore the previous capacitor part number",
    "expected_evidence": ["audit report", "readback delta"],
}


class Phase2SurfaceTests(support.BoundTestCase):
    def phase2_client(self) -> tuple[support.TaskHarness, support.MCPClient]:
        harness = self.harness(phase=2)
        client = self.client(harness)
        self.start_task(client, harness)
        self.tool_ok(client, "snapshot_read", {"scope": {"kind": "full"}})
        return harness, client

    def test_tools_list_returns_phase1_and_phase2_tools(self) -> None:
        harness = self.harness(phase=2)
        client = self.client(harness)
        names = [tool["name"] for tool in client.request("tools/list")["result"]["tools"]]
        self.assertEqual(len(names), 10)
        for tool in support.PHASE1_TOOLS + support.PHASE2_TOOLS:
            self.assertIn(tool, names)
        apply_tool = next(
            tool for tool in client.request("tools/list")["result"]["tools"] if tool["name"] == "apply"
        )
        self.assertFalse(apply_tool["annotations"]["readOnlyHint"])

    def test_plan_submit_validates_its_plan(self) -> None:
        harness, client = self.phase2_client()
        self.assert_tool_error(
            client, "plan_submit", {"plan": {"objective": "incomplete"}}, code="INVALID_ARGUMENTS"
        )
        broken = dict(PLAN)
        broken["changes"] = []
        self.assert_tool_error(
            client, "plan_submit", {"plan": broken}, code="INVALID_ARGUMENTS"
        )
        self.assertEqual(
            support.read_json(harness.task_dir / "status.json")["state"], "SNAPSHOT_READ"
        )

    def test_plan_submit_issues_an_immutable_plan_id(self) -> None:
        harness, client = self.phase2_client()
        payload = self.tool_ok(client, "plan_submit", {"plan": PLAN})
        self.assertEqual(payload["state"], "PLAN_SUBMITTED")
        self.assertEqual(len(payload["plan_id"]), 32)
        int(payload["plan_id"], 16)
        self.assertEqual(len(payload["plan_sha256"]), 64)

    def test_precheck_is_offline_only(self) -> None:
        harness, client = self.phase2_client()
        self.tool_ok(client, "plan_submit", {"plan": PLAN})
        payload = self.tool_ok(client, "precheck", {"checks": ["derating"]})
        self.assertEqual(payload["status"], "offline_precheck_only")
        self.assertEqual(payload["real_eda"], "NOT RUN")
        self.assertEqual(payload["eda_calls"], 0)
        self.assertEqual(payload["state"], "PRECHECKED")

    def test_apply_without_a_plan_is_refused(self) -> None:
        harness, client = self.phase2_client()
        self.assert_tool_error(
            client, "apply", {"plan_id": "a" * 32}, code="PLAN_NOT_FOUND"
        )

    def test_apply_with_a_wrong_plan_id_is_refused(self) -> None:
        harness, client = self.phase2_client()
        self.tool_ok(client, "plan_submit", {"plan": PLAN})
        self.tool_ok(client, "precheck", {"checks": []})
        self.assert_tool_error(
            client, "apply", {"plan_id": "b" * 32}, code="PLAN_HASH_MISMATCH"
        )

    def test_apply_is_always_eda_not_authorized(self) -> None:
        harness, client = self.phase2_client()
        submitted = self.tool_ok(client, "plan_submit", {"plan": PLAN})
        self.tool_ok(client, "precheck", {"checks": []})
        error = self.assert_tool_error(
            client, "apply", {"plan_id": submitted["plan_id"]}, code="EDA_NOT_AUTHORIZED"
        )
        self.assertEqual(error["detail"]["plan_id"], submitted["plan_id"])
        status = support.read_json(harness.task_dir / "status.json")
        self.assertEqual(status["state"], "FAILED")
        self.assertTrue(status["terminal"])
        self.assert_tool_error(client, "finalize", {}, code="TASK_CLOSED")
        self.assertFalse((harness.task_dir / "result.json").exists())
        self.assertEqual(support.read_json(harness.task_dir / "status.json")["state"], "FAILED")

    def test_readback_cannot_reach_the_backend(self) -> None:
        harness, client = self.phase2_client()
        submitted = self.tool_ok(client, "plan_submit", {"plan": PLAN})
        self.tool_ok(client, "precheck", {"checks": []})
        self.assert_tool_error(
            client, "apply", {"plan_id": submitted["plan_id"]}, code="EDA_NOT_AUTHORIZED"
        )
        self.assert_tool_error(
            client, "readback", {"plan_id": submitted["plan_id"]}, code="TASK_CLOSED"
        )

    def test_phase2_with_real_backend_is_refused_at_plan_time(self) -> None:
        root = self.temp_dir()
        request = support.make_request("bound-phase2-real")
        support.write_json(root / "request.json", request)
        completed = support.run_cli(
            "plan",
            "--request",
            root / "request.json",
            "--out",
            root / "task",
            "--phase",
            "2",
            "--backend",
            "official_cli",
        )
        self.assertIn(completed.returncode, (1, 2))
        self.assertEqual(
            support.parse_stdout_json(completed)["error"]["code"], "EDA_NOT_AUTHORIZED"
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
