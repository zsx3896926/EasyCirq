"""Optional merged offline audit engine (``--audit-engine zhigou_mcp``).

The engine is a *real* merged offline module (still no EDA). If it is missing
from the checkout the supervisor must fail honestly with ``NOT_RUN``; either way
``real_eda`` stays ``NOT RUN`` and ``eda_calls`` stays ``0``.
"""

from __future__ import annotations

import unittest

from task_launcher_bound_tests import support

HONEST_FALLBACK_CODES = ("NOT_RUN", "BACKEND_UNAVAILABLE", "EDA_NOT_AUTHORIZED")


class ZhigouMcpEngineTests(support.BoundTestCase):
    def engine_harness(self, **kwargs) -> support.TaskHarness:
        extra = ("--repo-root", str(support.WORKTREE)) + tuple(kwargs.pop("plan_extra", ()))
        return self.harness(audit_engine="zhigou_mcp", plan_extra=extra, **kwargs)

    def test_plan_records_the_requested_engine(self) -> None:
        harness = self.engine_harness()
        self.assertEqual(harness.summary["audit_engine"], "zhigou_mcp")
        self.assertEqual(harness.config()["audit_engine"], "zhigou_mcp")

    def test_engine_run_is_either_offline_success_or_honest_not_run(self) -> None:
        harness = self.engine_harness()
        completed = harness.run()
        document = support.parse_stdout_json(completed)
        if completed.returncode == 0:
            self.assertEqual(document["verdict"], "PASS")
            report = self.read_result(harness)
            self.assertEqual(report["summary"]["engine"], "zhigou_mcp")
            self.assertEqual(report["real_eda"], "NOT RUN")
            self.assertEqual(report["eda_calls"], 0)
            self.assertEqual(report["project_writes"], 0)
        else:
            self.assertEqual(completed.returncode, 1, completed.stderr)
            self.assertFalse(document["ok"])
            self.assertIn(document["error"]["code"], HONEST_FALLBACK_CODES)
            self.assertFalse((harness.task_dir / "result.json").exists())

    def test_missing_module_fails_with_not_run(self) -> None:
        empty_repo = self.temp_dir(prefix="zgb-empty-repo-")
        harness = self.engine_harness(plan_extra=("--repo-root", empty_repo))
        client = self.client(harness)
        self.start_task(client, harness)
        self.tool_ok(client, "snapshot_read", {"scope": {"kind": "full"}})
        error = self.assert_tool_error(
            client, "run_offline_audit", {"detail": "summary"}, code=HONEST_FALLBACK_CODES
        )
        self.assertIn("zhigou_mcp", error["message"].lower())
        self.assertFalse((harness.task_dir / "evidence.json").exists())

    def test_mcp_audit_never_claims_a_real_eda_call(self) -> None:
        harness = self.engine_harness()
        client = self.client(harness)
        self.start_task(client, harness)
        self.tool_ok(client, "snapshot_read", {"scope": {"kind": "full"}})
        response = client.call_tool("run_offline_audit", {"detail": "summary"})
        result = response["result"]
        payload = result["structuredContent"]
        if result["isError"]:
            self.assertIn(payload["error"]["code"], HONEST_FALLBACK_CODES)
            return
        audit = payload["audit"]
        self.assertEqual(audit["engine"], "zhigou_mcp")
        self.assertEqual(audit["real_eda"], "NOT RUN")
        self.assertEqual(audit["eda_calls"], 0)
        self.assertEqual(audit["project_writes"], 0)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
