"""Generated mcp.json must name a real interpreter, not bare ``python`` (#89)."""

from __future__ import annotations

import os
import sys
import unittest

from .support import LauncherTestCase, base_request


def norm(path: str) -> str:
    return os.path.normcase(os.path.normpath(path))


class McpInterpreterTests(LauncherTestCase):
    def _read_mcp(self, launcher, task_id: str) -> dict:
        path = launcher.workspace(task_id) / "mcp.json"
        import json

        return json.loads(path.read_text(encoding="utf-8"))

    def test_task_mcp_uses_the_launcher_interpreter_by_default(self) -> None:
        launcher = self.make_launcher()
        launcher.run_task(base_request("task-mcp-default"))
        document = self._read_mcp(launcher, "task-mcp-default")
        entry = document["mcpServers"]["easycirq-offline-audit"]
        self.assertTrue(entry["command"], entry)
        self.assertNotEqual(entry["command"], "python")
        self.assertEqual(norm(entry["command"]), norm(sys.executable), entry["command"])
        self.assertEqual(entry["args"], ["-m", "easycirq_mcp"])

    def test_plugin_mcp_uses_a_real_interpreter(self) -> None:
        launcher = self.make_launcher()
        launcher.run_task(base_request("task-mcp-plugin"))
        import json

        plugin_mcp = launcher.workspace("task-mcp-plugin") / "plugin" / ".mcp.json"
        document = json.loads(plugin_mcp.read_text(encoding="utf-8"))
        command = document["mcpServers"]["easycirq-offline-audit"]["command"]
        self.assertEqual(norm(command), norm(sys.executable), command)

    def test_mcp_python_override_is_honoured(self) -> None:
        launcher = self.make_launcher(extra_args=["--mcp-python", "custom-python-bin"])
        launcher.run_task(base_request("task-mcp-override"))
        document = self._read_mcp(launcher, "task-mcp-override")
        entry = document["mcpServers"]["easycirq-offline-audit"]
        self.assertEqual(entry["command"], "custom-python-bin")


if __name__ == "__main__":
    unittest.main()
