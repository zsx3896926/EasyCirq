"""B1 -> B1-Bound integration wiring tests (offline; no real Claude, no EDA).

The B1 task book (task M) only promised the controlled agent start-up.  This
module covers the follow-up integration requested for task O: the launcher can
mount the trusted ``task_launcher.bound`` supervisor in the task ``mcp.json``,
hand the agent the bound capability surface, append the bound hard-routing
contract, and require the supervisor's signed FINALIZED report for real-agent
tasks.

Everything here drives the real CLI entry point in a subprocess.  The fake
agent is used to produce the task artifacts; the supervisor is then started
exactly as Claude Code would start it (command/args/env from ``mcp.json``) and
driven over stdio JSON-RPC.  A real Claude Code session and real EDA remain
``NOT RUN``.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from .support import ROOT, SKILL_DIR, SKILL_VERSION, base_request, write_request

BOUND_SERVER_NAME = "zhigou_bound"
BOUND_TOOL_NAMES = (
    "task_start",
    "snapshot_read",
    "run_offline_audit",
    "evidence_emit",
    "finalize",
    "task_abort",
)
TASK_ID = "task-bound-int-001"


def run_cli(argv: list[str], *, timeout: float = 300.0, cwd: Path = ROOT) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "task_launcher", *argv],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def read_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


class _McpClient:
    """Minimal MCP stdio client used to prove the generated mcp.json is runnable."""

    def __init__(self, entry: dict, *, cwd: Path) -> None:
        import os

        env = dict(os.environ)
        env.update(entry.get("env") or {})
        self.process = subprocess.Popen(
            [entry["command"], *entry["args"]],
            cwd=str(cwd),
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        self._next_id = 1

    def send(self, message: dict) -> None:
        assert self.process.stdin is not None
        self.process.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
        self.process.stdin.flush()

    def read(self) -> dict:
        assert self.process.stdout is not None
        line = self.process.stdout.readline()
        if not line:
            raise AssertionError(f"MCP server closed stdout; stderr={self.stderr()}")
        return json.loads(line)

    def initialize(self) -> dict:
        self.send(
            {
                "jsonrpc": "2.0",
                "id": self._next_id,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "b1-integration-test", "version": "0.0.0"},
                },
            }
        )
        self._next_id += 1
        response = self.read()
        self.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return response["result"]

    def tools(self) -> list[dict]:
        self.send({"jsonrpc": "2.0", "id": self._next_id, "method": "tools/list"})
        self._next_id += 1
        return self.read()["result"]["tools"]

    def call_tool(self, name: str, arguments: dict) -> tuple[dict, bool]:
        self.send(
            {
                "jsonrpc": "2.0",
                "id": self._next_id,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            }
        )
        self._next_id += 1
        result = self.read()["result"]
        return result["structuredContent"], bool(result["isError"])

    def stderr(self) -> str:
        assert self.process.stderr is not None
        try:
            return (self.process.stderr.read() or "")[-800:]
        except Exception:  # pragma: no cover - defensive
            return ""

    def close(self) -> None:
        if self.process.stdin is not None:
            self.process.stdin.close()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:  # pragma: no cover - defensive
            self.process.kill()
            self.process.wait()
        for stream in (self.process.stdout, self.process.stderr):
            if stream is not None:
                try:
                    stream.close()
                except OSError:  # pragma: no cover - defensive
                    pass


class BoundIntegrationTests(unittest.TestCase):
    """One bound task (fake agent) and the generated artifacts it produced."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory(prefix="b1-bound-int-")
        cls.tmp = Path(cls._tmp.name)
        cls.state_dir = cls.tmp / "state"
        cls.request = base_request(TASK_ID, timeout_s=180)
        cls.request_path = write_request(cls.tmp, cls.request)
        cls.completed = run_cli(
            [
                "run",
                "--request",
                str(cls.request_path),
                "--state-dir",
                str(cls.state_dir),
                "--bound",
                "--agent-profile",
                "fake",
            ]
        )
        cls.workspace = cls.state_dir / "tasks" / TASK_ID

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    # -- artifacts ---------------------------------------------------------
    def test_run_completes_and_records_bound_metadata(self) -> None:
        self.assertEqual(self.completed.returncode, 0, self.completed.stderr[-2000:])
        result = read_json(self.workspace / "result.json")
        self.assertEqual(result["status"], "completed", result)
        self.assertEqual(result["agent"], "fake")
        self.assertEqual(result["real_eda"], "NOT RUN")
        bound = result.get("bound")
        self.assertIsInstance(bound, dict, result)
        self.assertTrue(bound["enabled"])
        self.assertEqual(bound["server"], BOUND_SERVER_NAME)
        self.assertEqual(bound["versions"]["skill"], SKILL_VERSION)
        self.assertEqual(bound["gate"], "not_enforced_fake_agent")
        self.assertFalse(bound["finalized"])
        self.assertIn(bound["state"], ("MISSING", "CREATED", "INCOMPLETE"))
        self.assertTrue(Path(bound["config_path"]).is_file())
        self.assertTrue((self.workspace / "bound" / "task.token").is_file())

    def test_task_mcp_json_mounts_only_the_bound_supervisor(self) -> None:
        mcp = read_json(self.workspace / "mcp.json")
        servers = mcp.get("mcpServers") or {}
        self.assertEqual(list(servers), [BOUND_SERVER_NAME], mcp)
        entry = servers[BOUND_SERVER_NAME]
        self.assertEqual(entry["args"][:3], ["-m", "task_launcher.bound", "serve"])
        self.assertIn("--config", entry["args"])
        self.assertIn("--token-file", entry["args"])
        self.assertTrue(entry["env"]["PYTHONPATH"])
        token = (self.workspace / "bound" / "task.token").read_text(encoding="utf-8").strip()
        self.assertNotIn(token, (self.workspace / "mcp.json").read_text(encoding="utf-8"))
        command = (self.workspace / "agent.command.json").read_text(encoding="utf-8")
        self.assertNotIn(token, command)

    def test_routing_contains_bound_contract_and_handshake(self) -> None:
        routing_text = (self.workspace / "routing.md").read_text(encoding="utf-8")
        for marker in (
            "task_start",
            "snapshot_read",
            "run_offline_audit",
            "evidence_emit",
            "finalize",
            "mcp__zhigou_bound__*",
            f"skill=`{SKILL_VERSION}`",
            "最终报告由 supervisor 生成",
        ):
            self.assertIn(marker, routing_text, f"routing.md is missing {marker!r}")

    def test_agent_command_uses_bound_capability_surface(self) -> None:
        command = read_json(self.workspace / "agent.command.json")
        argv = command["argv"]
        allowed = argv[argv.index("--allowedTools") + 1].split(",")
        self.assertIn("mcp__zhigou_bound__*", allowed)
        self.assertNotIn("Bash", allowed)
        bound = command.get("bound")
        self.assertIsInstance(bound, dict, command)
        self.assertEqual(bound["server"], BOUND_SERVER_NAME)

    def test_bound_supervisor_runs_from_the_generated_mcp_json(self) -> None:
        mcp = read_json(self.workspace / "mcp.json")
        entry = mcp["mcpServers"][BOUND_SERVER_NAME]
        config = read_json(self.workspace / "bound" / "bound.config.json")
        request = read_json(self.workspace / "bound" / "request.json")

        client = _McpClient(entry, cwd=self.tmp)
        try:
            init = client.initialize()
            self.assertEqual(init["serverInfo"]["name"], "zhigou-bound-supervisor")
            self.assertEqual([tool["name"] for tool in client.tools()], list(BOUND_TOOL_NAMES))
            toolchain = config["versions"]
            task_start = {
                "client": request["client"],
                "toolchain": toolchain,
                "task_id": request["task_id"],
                "goal": request["goal"],
                "context": request["context"],
                "limits": request.get("limits") or {},
            }
            payload, is_error = client.call_tool("task_start", task_start)
            self.assertFalse(is_error, payload)
            payload, is_error = client.call_tool("snapshot_read", {"scope": {"kind": "full"}})
            self.assertFalse(is_error, payload)
            payload, is_error = client.call_tool("run_offline_audit", {"detail": "summary"})
            self.assertFalse(is_error, payload)
            payload, is_error = client.call_tool("evidence_emit", {})
            self.assertFalse(is_error, payload)
            final, is_error = client.call_tool("finalize", {})
            self.assertFalse(is_error, final)
            self.assertEqual(final["state"], "FINALIZED")
            self.assertEqual(final["verdict"], "PASS")
        finally:
            client.close()

        report = read_json(self.workspace / "bound" / "result.json")
        self.assertEqual(report["task"]["verdict"], "PASS")
        self.assertEqual(report["generated_by"], "supervisor")
        self.assertEqual(report["real_eda"], "NOT RUN")
        self.assertEqual(report["eda_calls"], 0)
        self.assertEqual(report["project_writes"], 0)
        status = read_json(self.workspace / "bound" / "status.json")
        self.assertEqual(status["state"], "FINALIZED")


class OfflineAuditMCPRebrandTests(unittest.TestCase):
    """The 2026-10 rebrand renamed zhigou_mcp -> easycirq_mcp; mcp.json must match disk."""

    def test_offline_mcp_uses_the_module_that_exists(self) -> None:
        with tempfile.TemporaryDirectory(prefix="b1-offline-mcp-") as raw:
            tmp = Path(raw)
            state_dir = tmp / "state"
            task_id = "task-offline-mcp-001"
            request_path = write_request(tmp, base_request(task_id, timeout_s=120))
            completed = run_cli(
                ["run", "--request", str(request_path), "--state-dir", str(state_dir), "--agent-profile", "fake"]
            )
            self.assertEqual(completed.returncode, 0, completed.stderr[-2000:])
            workspace = state_dir / "tasks" / task_id
            scripts = SKILL_DIR / "scripts"
            expected_module = "zhigou_mcp"
            for candidate in ("easycirq_mcp", "zhigou_mcp"):
                if (scripts / candidate).is_dir():
                    expected_module = candidate
                    break
            task_mcp = read_json(workspace / "mcp.json")["mcpServers"]["easycirq-offline-audit"]
            self.assertEqual(task_mcp["args"], ["-m", expected_module])
            self.assertTrue((scripts / expected_module).is_dir(), "mcp.json mounts a module that does not exist")
            plugin_mcp = read_json(workspace / "plugin" / ".mcp.json")["mcpServers"]["easycirq-offline-audit"]
            self.assertEqual(plugin_mcp["args"], ["-m", expected_module])

            # And the configured server really starts and speaks MCP.
            entry = {
                "command": sys.executable,
                "args": ["-m", expected_module],
                "env": {"PYTHONPATH": str(scripts).replace("\\", "/")},
            }
            client = _McpClient(entry, cwd=tmp)
            try:
                init = client.initialize()
                self.assertIn("serverInfo", init)
                names = [tool["name"] for tool in client.tools()]
                self.assertIn("offline_electrical_review", names)
            finally:
                client.close()


class BoundGateTests(unittest.TestCase):
    """Real-agent profile must not complete when the supervisor has not finalized."""

    def test_claude_profile_without_supervisor_report_fails_the_task(self) -> None:
        with tempfile.TemporaryDirectory(prefix="b1-bound-gate-") as raw:
            tmp = Path(raw)
            state_dir = tmp / "state"
            task_id = "task-bound-gate-001"
            request_path = write_request(tmp, base_request(task_id, timeout_s=120))
            template = {
                "argv": [
                    "{python}",
                    "-m",
                    "task_launcher.fake_agent",
                    "-p",
                    "{user_prompt}",
                    "--plugin-dir",
                    "{plugin_dir}",
                    "--append-system-prompt-file",
                    "{routing_file}",
                    "--mcp-config",
                    "{mcp_config}",
                    "--output-format",
                    "stream-json",
                    "--verbose",
                    "--allowedTools",
                    "{allowed_tools}",
                    "--settings",
                    "{settings}",
                    "--disallowedTools",
                    "{disallowed_tools}",
                    "--add-dir",
                    "{task_dir}",
                ]
            }
            template_path = tmp / "claude-template.json"
            template_path.write_text(json.dumps(template), encoding="utf-8")
            completed = run_cli(
                [
                    "run",
                    "--request",
                    str(request_path),
                    "--state-dir",
                    str(state_dir),
                    "--bound",
                    "--agent-profile",
                    "claude",
                    "--claude-exe",
                    sys.executable,
                    "--agent-argv-template",
                    str(template_path),
                ]
            )
            self.assertEqual(completed.returncode, 1, completed.stderr[-2000:])
            workspace = state_dir / "tasks" / task_id
            result = read_json(workspace / "result.json")
            self.assertEqual(result["status"], "failed", result)
            self.assertEqual(result["agent"], "claude-code")
            bound = result["bound"]
            self.assertEqual(bound["gate"], "enforced")
            self.assertFalse(bound["finalized"])
            argv = read_json(workspace / "agent.command.json")["argv"]
            self.assertIn("--settings", argv)
            self.assertIn("--disallowedTools", argv)
            self.assertEqual(
                argv[argv.index("--allowedTools") + 1].split(","),
                ["Skill", "Read", "Glob", "Grep", "mcp__zhigou_bound__*"],
            )
            events = [
                json.loads(line)
                for line in (workspace / "events.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertTrue(any(event.get("type") == "bound_gate_failed" for event in events), events[-5:])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
