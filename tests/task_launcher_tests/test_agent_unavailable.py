"""Agent availability tests (task book §3.6, §4.9).

Two rules from the contract:

* when ``--agent-profile claude`` points at a missing executable, task start is
  refused with ``503 AGENT_UNAVAILABLE`` (nothing is installed automatically),
  while ``GET /health`` keeps answering ``200``;
* the ``fake`` profile is a test fixture and must not be affected by a bogus
  ``--claude-exe`` path.

The last test fixes the 404 contract for unknown task ids on every read
endpoint (state / events / result).
"""

from __future__ import annotations

import unittest

from .support import ROOT, LauncherTestCase, base_request

MISSING_CLAUDE = str(ROOT / "no-such-agent-dir" / "claude.exe")


class AgentUnavailableTests(LauncherTestCase):
    def test_missing_claude_executable_returns_503_and_creates_no_task(self) -> None:
        launcher = self.make_launcher(agent_profile="claude", claude_exe=MISSING_CLAUDE)
        self.assertFalse(launcher.ready["agent_available"], launcher.ready)

        status, health = launcher.health()
        self.assertEqual(status, 200, health)
        self.assertEqual(health["status"], "degraded")
        self.assertIn("agent_unavailable", health["degraded_reasons"])
        self.assertEqual(health["tasks_running"], 0)

        task_id = "task-agent-unavailable"
        error = self.assert_error(launcher.start(base_request(task_id)), 503, "AGENT_UNAVAILABLE")
        self.assertEqual(error["detail"]["profile"], "claude")
        self.assertEqual(error["detail"]["reason"], "claude_executable_not_found")
        self.assertEqual(error["detail"]["executable"], MISSING_CLAUDE)
        self.assertIn("hint", error["detail"])

        # Nothing was started, nothing was created, nothing was installed.
        self.assert_error(launcher.task(task_id), 404, "TASK_NOT_FOUND")
        self.assertFalse(launcher.workspace(task_id).exists())
        status, health = launcher.health()
        self.assertEqual(status, 200, health)
        self.assertEqual(health["tasks_running"], 0)

    def test_fake_profile_is_unaffected_by_a_missing_claude_executable(self) -> None:
        launcher = self.make_launcher(agent_profile="fake", claude_exe=MISSING_CLAUDE)
        self.assertTrue(launcher.ready["agent_available"], launcher.ready)
        result = launcher.run_task(base_request("task-agent-fake-ok"), timeout=60.0)
        self.assertEqual(result["status"], "completed", result)
        self.assertEqual(result["agent"], "fake")
        self.assertEqual(result["model_used"], "fake")
        self.assertEqual(result["exit_code"], 0)

    def test_unknown_task_endpoints_are_404(self) -> None:
        launcher = self.make_launcher()
        task_id = "task-unknown-id"
        for response in (
            launcher.task(task_id),
            launcher.events(task_id, 0),
            launcher.result(task_id),
        ):
            error = self.assert_error(response, 404, "TASK_NOT_FOUND")
            self.assertEqual(error["detail"]["task_id"], task_id)


if __name__ == "__main__":
    unittest.main()
