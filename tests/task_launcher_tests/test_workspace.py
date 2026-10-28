"""Task workspace evidence tests (task book §3.5 / §4.5).

The workspace is the only place a task writes.  These tests assert the evidence
set, event-log integrity, the absence of credentials, and that the repository /
Skill tree is byte-for-byte untouched by a task run.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from .support import (
    ROOT,
    SKILL_DIR,
    SKILL_NAME,
    LauncherProcess,
    base_request,
    repo_file_snapshot,
)

EXPECTED_WORKSPACE_FILES = {
    "request.json",
    "context.json",
    "routing.md",
    "mcp.json",
    "agent.command.json",
    "events.jsonl",
    "agent.stdout.log",
    "agent.stderr.log",
    "result.json",
}


class WorkspaceTests(unittest.TestCase):
    launcher: LauncherProcess
    task_id = "task-workspace-001"

    @classmethod
    def setUpClass(cls) -> None:
        cls.launcher = LauncherProcess()
        cls.before = repo_file_snapshot([SKILL_DIR])
        cls.result = cls.launcher.run_task(base_request(cls.task_id))
        cls.workspace = cls.launcher.workspace(cls.task_id)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.launcher.close()

    def read(self, name: str):
        return json.loads((self.workspace / name).read_text(encoding="utf-8"))

    def test_all_evidence_files_exist(self) -> None:
        names = {path.name for path in self.workspace.iterdir() if path.is_file()}
        missing = EXPECTED_WORKSPACE_FILES - names
        self.assertFalse(missing, f"missing workspace evidence: {sorted(missing)}")
        self.assertTrue((self.workspace / "plugin").is_dir())
        self.assertTrue((self.workspace / "agent.received.json").is_file())

    def test_workspace_lives_outside_the_repository(self) -> None:
        workspace = self.workspace.resolve()
        self.assertFalse(str(workspace).lower().startswith(str(ROOT.resolve()).lower()), workspace)
        self.assertIn("tasks", workspace.parts)

    def test_events_jsonl_is_complete_and_ordered(self) -> None:
        lines = (self.workspace / "events.jsonl").read_text(encoding="utf-8").splitlines()
        events = [json.loads(line) for line in lines if line.strip()]
        self.assertGreaterEqual(len(events), 3)
        seqs = [event["seq"] for event in events]
        self.assertEqual(seqs, list(range(1, len(events) + 1)))
        self.assertEqual(events[-1]["type"], "task_finished")
        self.assertEqual(self.result["event_count"], len(events))
        status, document = self.launcher.events(self.task_id, 0)
        self.assertEqual(status, 200, document)
        self.assertEqual([event["seq"] for event in document["events"]], seqs)
        self.assertEqual(document["next_seq"], len(events) + 1)
        self.assertTrue(document["terminal"])
        # Replay from the middle must return exactly the tail.
        status, replay = self.launcher.events(self.task_id, 3)
        self.assertEqual([event["seq"] for event in replay["events"]], seqs[3:])

    def test_no_credential_appears_in_the_workspace(self) -> None:
        token = self.launcher.token
        self.assertTrue(token)
        for path in self.workspace.rglob("*"):
            if not path.is_file() or "plugin" in path.parts:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            self.assertNotIn(token, text, f"token leaked into {path.name}")
            self.assertNotIn("Bearer", text, f"Authorization header leaked into {path.name}")
        command = self.read("agent.command.json")
        self.assertFalse(command["token_included"])
        self.assertNotIn(token, json.dumps(command, ensure_ascii=False))

    def test_agent_command_is_argv_not_shell(self) -> None:
        command = self.read("agent.command.json")
        argv = command["argv"]
        self.assertIsInstance(argv, list)
        self.assertTrue(all(isinstance(item, str) for item in argv))
        self.assertEqual(argv[0], command["executable"])
        joined = " ".join(argv)
        self.assertNotIn("&&", joined)
        self.assertNotIn("|", joined)
        for flag in ("--plugin-dir", "--append-system-prompt-file", "--mcp-config", "--output-format"):
            self.assertIn(flag, argv)
        self.assertEqual(command["cwd"], str(self.workspace))
        self.assertTrue((self.workspace / "plugin" / ".claude-plugin" / "plugin.json").is_file())
        env_keys = set(command["env"])
        self.assertNotIn("LAUNCHER_TOKEN", env_keys)
        self.assertTrue({"ZHIGOU_TASK_ID", "ZHIGOU_MODE", "PYTHONPATH"} <= env_keys)

    def test_agent_received_the_expected_command(self) -> None:
        received = self.read("agent.received.json")
        self.assertEqual(received["agent"], "fake")
        self.assertEqual(received["model"], "fake")
        received_argv = received["argv"]
        self.assertEqual(received_argv[0], "-p")
        command = self.read("agent.command.json")
        # `python -m task_launcher.fake_agent` consumes argv[0..2]; the rest is
        # what the agent sees, which is what agent.command.json recorded.
        self.assertEqual(received_argv, command["argv"][3:])
        for flag in ("--plugin-dir", "--append-system-prompt-file", "--mcp-config", "--output-format"):
            self.assertIn(flag, received_argv)
        self.assertIn("stream-json", received_argv)
        env = received["env"]
        self.assertEqual(env.get("ZHIGOU_TASK_ID"), self.task_id)
        self.assertEqual(env.get("ZHIGOU_MODE"), "read_only")
        self.assertIn("PYTHONPATH", env)
        self.assertNotIn(self.launcher.token, json.dumps(received, ensure_ascii=False))

    def test_repository_and_skill_tree_are_untouched(self) -> None:
        after = repo_file_snapshot([SKILL_DIR])
        self.assertEqual(
            set(after) - set(self.before),
            set(),
            f"a task wrote new files into {SKILL_NAME}/",
        )
        self.assertEqual(
            {path: after[path] for path in self.before if path in after},
            self.before,
            f"a task modified files under {SKILL_NAME}/",
        )

    def test_result_json_matches_the_api(self) -> None:
        on_disk = self.read("result.json")
        status, api = self.launcher.result(self.task_id)
        self.assertEqual(status, 200, api)
        self.assertEqual(on_disk, api)
        self.assertEqual(on_disk["schema"], "zhigou.task-launcher.result/v1")
        self.assertEqual(on_disk["real_eda"], "NOT RUN")
        self.assertEqual(on_disk["eda_calls"], 0)
        self.assertEqual(on_disk["project_writes"], 0)
        self.assertEqual(on_disk["network_calls"], 0)
        self.assertEqual(on_disk["status"], "completed")
        self.assertEqual(on_disk["agent"], "fake")
        self.assertIn("not_proof", on_disk)

    def test_request_context_and_routing_evidence(self) -> None:
        request = self.read("request.json")
        self.assertEqual(request["task_id"], self.task_id)
        self.assertEqual(request["mode"], "read_only")
        self.assertNotIn("token", json.dumps(request, ensure_ascii=False).lower())
        context = self.read("context.json")
        self.assertEqual(context["project"]["name"], "demo")
        self.assertEqual(context["document"]["kind"], "schematic")
        self.assertIn("snapshot_sha256", context["missing_fields"])
        routing = (self.workspace / "routing.md").read_text(encoding="utf-8")
        self.assertIn(SKILL_NAME, routing)
        self.assertIn("只读任务", routing)
        mcp = self.read("mcp.json")
        self.assertIn("zhigou-offline-audit", mcp["mcpServers"])


if __name__ == "__main__":
    unittest.main()
