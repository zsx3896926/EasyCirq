"""CLI entry points: version / selftest / probe-b1 / run / error handling."""

from __future__ import annotations

import json
import unittest

from task_launcher_bound_tests import support


class CliVersionTests(support.BoundTestCase):
    def test_dash_version_prints_json(self) -> None:
        completed = support.run_cli("--version")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        document = support.parse_stdout_json(completed)
        self.assertEqual(document["name"], "task_launcher.bound")
        self.assertEqual(document["version"], "0.1.0")
        self.assertEqual(document["phase"], 1)

    def test_version_command_reports_schemas_and_tools(self) -> None:
        document = support.run_cli_json("version")
        self.assertEqual(document["schema"], "zhigou.bound.version/v1")
        self.assertEqual(document["mcp_protocol"], support.MCP_PROTOCOL_VERSION)
        self.assertEqual(document["server_name"], support.SERVER_NAME)
        self.assertEqual(tuple(document["phase1_tools"]), support.PHASE1_TOOLS)
        self.assertEqual(tuple(document["phase2_tools"]), support.PHASE2_TOOLS)
        self.assertFalse(document["phase2_enabled"])
        self.assertEqual(document["schemas"]["report"], "zhigou.bound.report/v1")
        self.assertEqual(document["schemas"]["receipt"], "zhigou.bound.receipt/v1")

    def test_version_command_is_honest_about_eda(self) -> None:
        document = support.run_cli_json("version")
        self.assertEqual(document["real_eda"], "NOT RUN")
        self.assertEqual(document["eda_calls"], 0)
        self.assertEqual(set(document["denied_agent_tools"]), set(support.DENIED_AGENT_TOOLS))
        self.assertEqual(set(document["allowed_agent_tools"]), set(support.ALLOWED_AGENT_TOOLS))

    def test_version_stdout_is_one_json_document(self) -> None:
        completed = support.run_cli("version")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        lines = [line for line in completed.stdout.splitlines() if line.strip()]
        self.assertEqual(len(lines), 1)
        json.loads(lines[0])


class SelftestTests(support.BoundTestCase):
    def test_selftest_ok(self) -> None:
        completed = support.run_cli("selftest", timeout=180)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        document = support.parse_stdout_json(completed)
        self.assertEqual(document["schema"], "zhigou.bound.selftest/v1")
        self.assertTrue(document["ok"], document.get("checks"))
        self.assertEqual(document["failed"], 0)
        self.assertGreaterEqual(document["passed"], 10)

    def test_selftest_checks_are_all_green_and_named(self) -> None:
        document = support.run_cli_json("selftest", timeout=180)
        checks = document["checks"]
        self.assertTrue(checks)
        for check in checks:
            self.assertEqual(check["status"], "pass", check)
            self.assertIsInstance(check["id"], str)
        ids = {check["id"] for check in checks}
        for expected in (
            "canonical-json",
            "receipt-chain-valid",
            "receipt-tamper-payload-detected",
            "state-skip-refused",
            "state-duplicate-refused",
            "token-binding",
            "version-handshake",
            "incomplete-audit-blocked",
        ):
            self.assertIn(expected, ids)

    def test_selftest_never_claims_real_eda(self) -> None:
        document = support.run_cli_json("selftest", timeout=180)
        self.assertEqual(document["real_eda"], "NOT RUN")
        self.assertEqual(document["eda_calls"], 0)
        self.assertEqual(document["agent"], "none")


class ProbeB1Tests(support.BoundTestCase):
    def test_probe_b1_without_repo_is_blocked(self) -> None:
        document = support.run_cli_json("probe-b1")
        self.assertEqual(document["schema"], "zhigou.bound.b1-probe/v1")
        self.assertFalse(document["available"])
        self.assertFalse(document["delivered"])
        self.assertEqual(document["integration_status"], "BLOCKED ON B1")

    def test_probe_b1_on_this_checkout_is_blocked(self) -> None:
        document = support.run_cli_json("probe-b1", "--repo-root", support.WORKTREE)
        self.assertFalse(document["delivered"])
        self.assertEqual(document["integration_status"], "BLOCKED ON B1")
        self.assertIsInstance(document["missing"], list)
        self.assertTrue(document["notes"])
        joined = " ".join(document["notes"])
        self.assertIn("BLOCKED ON B1", joined)

    def test_probe_b1_is_read_only(self) -> None:
        before = support.stable_git_status()
        support.run_cli_json("probe-b1", "--repo-root", support.WORKTREE)
        self.assertEqual(support.stable_git_status(), before)


class RunCommandTests(support.BoundTestCase):
    def test_run_uses_scripted_in_process_driver(self) -> None:
        harness = self.harness()
        completed = harness.run()
        self.assertEqual(completed.returncode, 0, completed.stderr)
        document = support.parse_stdout_json(completed)
        self.assertEqual(document["schema"], "zhigou.bound.run/v1")
        self.assertIn("scripted-in-process", document["driver"])
        self.assertIn("not a real Claude run", document["driver"])
        self.assertEqual(document["agent"], "none")

    def test_run_reports_not_run_and_zero_eda(self) -> None:
        harness = self.harness()
        document = support.parse_stdout_json(harness.run())
        self.assertEqual(document["real_eda"], "NOT RUN")
        self.assertEqual(document["eda_calls"], 0)
        self.assertEqual(document["project_writes"], 0)
        self.assertEqual(document["report"]["real_eda"], "NOT RUN")
        self.assertEqual(document["report"]["eda_calls"], 0)
        self.assertEqual(document["report"]["project_writes"], 0)

    def test_run_writes_supervisor_result_json(self) -> None:
        harness = self.harness()
        document = support.parse_stdout_json(harness.run())
        self.assertEqual(document["state"], "FINALIZED")
        self.assertEqual(document["verdict"], "PASS")
        report = self.read_result(harness)
        self.assertEqual(report["generated_by"], "supervisor")
        self.assertEqual(report["task"]["verdict"], "PASS")
        self.assertEqual(report["report_sha256"], document["report_sha256"])
        self.assert_report_sha(report)

    def test_run_failure_exits_one_with_stable_code(self) -> None:
        harness = self.harness(audit_case="incomplete")
        completed = harness.run()
        self.assertEqual(completed.returncode, 1, completed.stderr)
        document = support.parse_stdout_json(completed)
        self.assertFalse(document["ok"])
        self.assertEqual(document["schema"], "zhigou.bound.cli-error/v1")
        self.assertIn(document["error"]["code"], ("TASK_CLOSED", "AUDIT_INCOMPLETE"))
        self.assertIn("run failed", completed.stderr)


class CliUsageTests(support.BoundTestCase):
    def test_unknown_command_exits_two(self) -> None:
        completed = support.run_cli("not-a-command")
        self.assertEqual(completed.returncode, 2)
        self.assertIn("invalid choice", completed.stderr.lower())

    def test_no_command_prints_help_and_exits_two(self) -> None:
        completed = support.run_cli()
        self.assertEqual(completed.returncode, 2)

    def test_plan_error_document_goes_to_stdout(self) -> None:
        harness_root = self.temp_dir()
        request = support.make_request("bound-cli-bad")
        request["unexpected_field"] = True
        support.write_json(harness_root / "request.json", request)
        completed = support.run_cli(
            "plan",
            "--request",
            harness_root / "request.json",
            "--out",
            harness_root / "task",
        )
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(completed.stdout.count("\n"), 1)
        document = support.parse_stdout_json(completed)
        self.assertFalse(document["ok"])
        self.assertEqual(document["error"]["code"], "INVALID_REQUEST")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
