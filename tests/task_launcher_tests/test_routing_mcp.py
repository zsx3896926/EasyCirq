"""routing.md / mcp.json / agent.command.json contract tests (§3.4, §3.5, §3.8).

These tests start a real ``python -m task_launcher serve`` subprocess with the
bundled fake agent, run one read-only task and then assert on the evidence the
task workspace must contain:

* ``routing.md`` — the prompt injected with ``--append-system-prompt-file``.  It
  must carry the five normative rules of §3.8 (hardcoded here from the task book,
  *not* imported from ``task_launcher.routing``, so the test stays independent),
  name the five offline tools and state the read-only / honesty boundary.
* ``mcp.json`` (task workspace) and ``<workspace>/plugin/.mcp.json`` — must mount
  the already-merged offline-audit MCP server ``zhigou-offline-audit`` with
  ``python -m zhigou_mcp`` and a ``PYTHONPATH`` pointing at
  ``design-hardware/scripts``.
* ``agent.command.json`` — the recorded argv must be a list (never a shell
  string), contain ``--plugin-dir`` / ``--append-system-prompt-file`` /
  ``--mcp-config`` / ``--output-format`` with real values, point at a plugin
  directory that exists, and never contain the launcher token.

No test calls EDA, a daemon, a connector, the network or a real Claude Code.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from .support import ROOT, SKILL_DIR, LauncherProcess, base_request

#: The five normative rules of task book §3.8, hardcoded verbatim (markdown
#: emphasis markers stripped).  Deliberately not imported from the implementation.
REQUIRED_ROUTING_RULES = (
    "必须先加载 design-hardware Skill，不得跳过",
    "只读任务：不得修改/保存/导出 EDA 工程，不得调用任何写接口",
    "未知/缺测必须如实报告，不得用默认值或猜测补全",
    "离线检查 / 真实 EDA / 硬件实测",
    "读了哪些资料、跑了哪些工具、结果、未知项、未运行项",
)

#: The only offline tools the PoC may hand the agent.
OFFLINE_TOOL_NAMES = (
    "offline_audit_capabilities",
    "offline_electrical_review",
    "offline_return_path_audit",
    "offline_delivery_inspect",
    "offline_delivery_audit",
)

REQUIRED_AGENT_FLAGS = (
    "--plugin-dir",
    "--append-system-prompt-file",
    "--mcp-config",
    "--output-format",
)

MCP_SERVER_NAME = "zhigou-offline-audit"
MCP_MODULE = "zhigou_mcp"


def read_json(path: Path) -> dict:
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise AssertionError(f"{path} does not contain a JSON object")
    return document


def normalize_path(value: str) -> str:
    return str(value).replace("\\", "/")


class RoutingAndMcpTests(unittest.TestCase):
    """One fake-agent task, then assert the routing/MCP/command contract."""

    task_id = "task-routing-mcp-001"
    launcher: LauncherProcess
    workspace: Path
    result: dict

    @classmethod
    def setUpClass(cls) -> None:
        cls.launcher = LauncherProcess()
        cls.addClassCleanup(cls.launcher.close)
        cls.result = cls.launcher.run_task(base_request(cls.task_id))
        if cls.result.get("status") != "completed":  # pragma: no cover - reported below
            raise AssertionError(f"fake-agent task did not complete: {cls.result}")
        cls.workspace = cls.launcher.workspace(cls.task_id)

    def read_workspace_json(self, name: str) -> dict:
        return read_json(self.workspace / name)

    def test_routing_md_contains_the_five_hardcoded_rules(self) -> None:
        routing_path = self.workspace / "routing.md"
        self.assertTrue(routing_path.is_file(), "routing.md is missing from the task workspace")
        routing = routing_path.read_text(encoding="utf-8")

        missing = [rule for rule in REQUIRED_ROUTING_RULES if rule not in routing]
        self.assertEqual(missing, [], f"routing.md is missing required rule text: {missing}")

        # The routing prompt lives in the task workspace, never in the repository.
        self.assertFalse(
            str(self.workspace.resolve()).lower().startswith(str(ROOT.resolve()).lower()),
            self.workspace,
        )
        self.assertIn("design-hardware", routing)

    def test_routing_md_documents_tool_scope_and_honesty_boundary(self) -> None:
        routing = (self.workspace / "routing.md").read_text(encoding="utf-8")
        for tool in OFFLINE_TOOL_NAMES:
            self.assertIn(tool, routing, f"routing.md does not name offline tool {tool}")
        self.assertIn(MCP_SERVER_NAME, routing)
        self.assertIn("pass_with_scope", routing)
        self.assertIn("只读", routing)
        # Honesty boundary: the routing text must state the real-EDA status.
        self.assertIn("NOT RUN", routing)
        self.assertIn("eda_calls=0", routing)
        self.assertIn("project_writes=0", routing)

        summary = self.read_workspace_json("routing.summary.json")
        self.assertEqual(summary.get("mode"), "read_only")
        self.assertEqual(summary.get("real_eda"), "NOT RUN")
        self.assertEqual(tuple(summary.get("tools", ())), OFFLINE_TOOL_NAMES)
        self.assertEqual(len(summary.get("rules", ())), len(REQUIRED_ROUTING_RULES))

    def test_task_workspace_mcp_json_mounts_offline_audit(self) -> None:
        mcp = self.read_workspace_json("mcp.json")
        servers = mcp.get("mcpServers")
        self.assertIsInstance(servers, dict, mcp)
        self.assertEqual(set(servers), {MCP_SERVER_NAME})

        entry = servers[MCP_SERVER_NAME]
        self.assertEqual(entry.get("command"), "python")
        self.assertEqual(entry.get("args"), ["-m", MCP_MODULE])
        env = entry.get("env")
        self.assertIsInstance(env, dict, entry)
        pythonpath = env.get("PYTHONPATH")
        self.assertIsInstance(pythonpath, str)
        self.assertTrue(pythonpath)
        self.assertEqual(
            normalize_path(pythonpath),
            (SKILL_DIR / "scripts").resolve().as_posix(),
            "task mcp.json PYTHONPATH must point at design-hardware/scripts",
        )
        self.assertTrue(Path(pythonpath).is_dir(), pythonpath)

    def test_plugin_mcp_json_mounts_offline_audit(self) -> None:
        plugin_mcp_path = self.workspace / "plugin" / ".mcp.json"
        self.assertTrue(plugin_mcp_path.is_file(), "the materialized plugin has no .mcp.json")
        mcp = read_json(plugin_mcp_path)
        servers = mcp.get("mcpServers")
        self.assertIsInstance(servers, dict, mcp)
        self.assertEqual(set(servers), {MCP_SERVER_NAME})

        entry = servers[MCP_SERVER_NAME]
        self.assertEqual(entry.get("command"), "python")
        self.assertEqual(entry.get("args"), ["-m", MCP_MODULE])
        env = entry.get("env")
        self.assertIsInstance(env, dict, entry)
        pythonpath = env.get("PYTHONPATH")
        self.assertIsInstance(pythonpath, str)
        self.assertTrue(pythonpath)
        normalized = normalize_path(pythonpath)
        self.assertTrue(
            normalized.endswith("design-hardware/scripts"),
            f"plugin .mcp.json PYTHONPATH does not point at design-hardware/scripts: {pythonpath}",
        )
        self.assertEqual(normalized, (SKILL_DIR / "scripts").resolve().as_posix())
        self.assertTrue(Path(pythonpath).is_dir(), pythonpath)

    def test_agent_command_json_uses_explicit_flags_and_real_plugin_dir(self) -> None:
        command = self.read_workspace_json("agent.command.json")
        argv = command.get("argv")
        self.assertIsInstance(argv, list, "agent argv must be a list, never a shell string")
        self.assertTrue(all(isinstance(item, str) for item in argv), argv)
        self.assertEqual(argv[0], command["executable"])
        self.assertEqual(Path(command["cwd"]).resolve(), self.workspace.resolve())

        for flag in REQUIRED_AGENT_FLAGS:
            self.assertIn(flag, argv, f"agent argv is missing {flag}")
            index = argv.index(flag)
            self.assertLess(index + 1, len(argv), f"{flag} has no value")
            value = argv[index + 1]
            self.assertFalse(value.startswith("--"), f"{flag} has no value, next token is {value!r}")

        self.assertEqual(argv[argv.index("--output-format") + 1], "stream-json")

        plugin_dir = Path(argv[argv.index("--plugin-dir") + 1])
        self.assertTrue(plugin_dir.is_dir(), f"--plugin-dir does not exist: {plugin_dir}")
        self.assertTrue((plugin_dir / ".claude-plugin" / "plugin.json").is_file())
        self.assertTrue((plugin_dir / "skills" / "design-hardware" / "SKILL.md").is_file())
        self.assertEqual(
            plugin_dir.resolve(),
            (self.workspace / "plugin").resolve(),
        )

        self.assertEqual(
            Path(argv[argv.index("--append-system-prompt-file") + 1]).resolve(),
            (self.workspace / "routing.md").resolve(),
        )
        self.assertEqual(
            Path(argv[argv.index("--mcp-config") + 1]).resolve(),
            (self.workspace / "mcp.json").resolve(),
        )

        self.assertEqual(tuple(command.get("required_flags", ())), REQUIRED_AGENT_FLAGS)
        self.assertIs(command.get("required_flags_present"), True)
        self.assertIs(command.get("token_included"), False)
        serialized = json.dumps(command, ensure_ascii=False)
        self.assertNotIn(self.launcher.token, serialized)
        self.assertNotIn("Bearer", serialized)
        self.assertNotIn("&&", " ".join(argv))


if __name__ == "__main__":
    unittest.main()
