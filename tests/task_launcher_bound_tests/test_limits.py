"""Limits: max steps / max tool calls / rate limiting and config ceilings."""

from __future__ import annotations

import unittest

from task_launcher_bound_tests import support


class ToolCallLimitTests(support.BoundTestCase):
    def test_max_tool_calls_one_blocks_the_second_call(self) -> None:
        harness = self.harness()
        client = self.client(harness)
        self.start_task(client, harness, limits={"max_tool_calls": 1})
        error = self.assert_tool_error(
            client, "snapshot_read", {"scope": {"kind": "full"}}, code="LIMIT_EXCEEDED"
        )
        self.assertEqual(error["detail"]["limit"], 1)
        self.assertEqual(error["detail"]["calls"], 2)
        status = support.read_json(harness.task_dir / "status.json")
        self.assertEqual(status["state"], "STARTED")

    def test_max_steps_one_blocks_the_second_step(self) -> None:
        harness = self.harness()
        client = self.client(harness)
        self.start_task(client, harness, limits={"max_steps": 1})
        error = self.assert_tool_error(
            client, "snapshot_read", {"scope": {"kind": "full"}}, code="LIMIT_EXCEEDED"
        )
        self.assertEqual(error["detail"]["limit"], 1)
        self.assertEqual(error["detail"]["steps"], 2)

    def test_three_calls_are_enough_for_start_snapshot_audit(self) -> None:
        harness = self.harness()
        client = self.client(harness)
        self.start_task(client, harness, limits={"max_tool_calls": 3})
        self.tool_ok(client, "snapshot_read", {"scope": {"kind": "full"}})
        self.tool_ok(client, "run_offline_audit", {"detail": "summary"})
        self.assert_tool_error(client, "evidence_emit", {}, code="LIMIT_EXCEEDED")

    def test_requested_limits_are_capped_by_the_config(self) -> None:
        harness = self.harness()
        config = harness.config()
        config["limits"]["max_tool_calls"] = 2
        harness.save_config(config)
        client = self.client(harness)
        # task_start asks for 1000; the config caps the effective limit at 2.
        self.start_task(client, harness, limits={"max_tool_calls": 1000})
        self.tool_ok(client, "snapshot_read", {"scope": {"kind": "full"}})
        self.assert_tool_error(
            client, "run_offline_audit", {"detail": "summary"}, code="LIMIT_EXCEEDED"
        )

    def test_rate_limit_rejects_back_to_back_calls(self) -> None:
        harness = self.harness()
        config = harness.config()
        config["limits"]["min_tool_interval_s"] = 5.0
        harness.save_config(config)
        client = self.client(harness)
        self.start_task(client, harness)
        self.assert_tool_error(
            client, "snapshot_read", {"scope": {"kind": "full"}}, code="RATE_LIMITED"
        )

    def test_limits_ceiling_in_config_is_refused_at_serve(self) -> None:
        harness = self.harness()
        config = harness.config()
        config["limits"]["max_steps"] = 100000
        harness.save_config(config)
        completed = support.run_serve_expect_exit(
            harness.config_path, token_file=harness.token_file
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("INVALID_CONFIG", completed.stderr)

    def test_plan_request_limit_one_makes_the_cli_run_fail(self) -> None:
        harness = self.harness(request_kwargs={"limits": {"max_tool_calls": 1}})
        completed = harness.run()
        self.assertEqual(completed.returncode, 1, completed.stderr)
        document = support.parse_stdout_json(completed)
        self.assertFalse(document["ok"])
        self.assertEqual(document["error"]["code"], "LIMIT_EXCEEDED")
        self.assertFalse((harness.task_dir / "result.json").exists())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
