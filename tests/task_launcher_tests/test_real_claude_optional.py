"""Optional, env-gated real Claude Code read-only acceptance (#88).

Default: skipped everywhere (including CI).  To run it once on a machine with an
authenticated Claude Code CLI and explicit permission to call the model:

    EASYCIRQ_REAL_CLAUDE=1 python -m unittest tests.task_launcher_tests.test_real_claude_optional -v

The test never fakes a model result: when it runs it records the real CLI's
version, ``agent: "claude-code"``, ``model_used: "unknown"`` and keeps
``real_eda: "NOT RUN"`` (no EDA is involved).
"""

from __future__ import annotations

import os
import shutil
import unittest

from .support import LauncherTestCase, base_request

ENABLED = os.environ.get("EASYCIRQ_REAL_CLAUDE") == "1"


@unittest.skipUnless(ENABLED, "real Claude acceptance is opt-in: set EASYCIRQ_REAL_CLAUDE=1")
class RealClaudeOptionalTests(LauncherTestCase):
    def test_one_read_only_task_with_real_claude(self) -> None:
        claude = shutil.which("claude")
        if not claude:
            self.skipTest("claude executable is not installed on this machine")
        launcher = self.make_launcher(agent_profile="claude", claude_exe=claude)
        request = base_request("task-real-claude-optional", timeout_s=300)
        result = launcher.run_task(request, timeout=320.0)
        self.assertEqual(result["status"], "completed", result)
        self.assertEqual(result["agent"], "claude-code", result)
        self.assertEqual(result["agent_profile"], "claude", result)
        self.assertEqual(result["model_used"], "unknown", result)
        self.assertEqual(result["real_eda"], "NOT RUN", result)
        self.assertEqual(result["eda_calls"], 0, result)
        self.assertEqual(result["project_writes"], 0, result)
        self.assertIn("NOT RUN", result["hardware_test"])


if __name__ == "__main__":
    unittest.main()
