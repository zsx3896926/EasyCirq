"""Path / encoding tests (task book §3.5, §4.12).

The launcher runs on Chinese Windows machines, so the state directory and the
plugin build cache can contain spaces **and** Chinese characters, ``task_id``
values legitimately use dots/dashes/underscores, and ``goal.user_prompt`` is
Chinese.  None of that may break task start, evidence files or the agent argv.

Every task here still runs through a real launcher subprocess and the bundled
fake agent; the workspace evidence is read back from disk as UTF-8.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from .support import ROOT, LauncherTestCase, base_request, read_json

EVIDENCE_FILES = (
    "request.json",
    "context.json",
    "routing.md",
    "mcp.json",
    "agent.command.json",
    "events.jsonl",
    "agent.stdout.log",
    "agent.stderr.log",
    "result.json",
    "agent.received.json",
)


class PathsTests(LauncherTestCase):
    def _temp_root(self) -> Path:
        root = Path(tempfile.mkdtemp(prefix="zhigou-paths-test-"))
        self.addCleanup(shutil.rmtree, root, True)
        return root

    def test_state_and_plugin_cache_dirs_with_spaces_and_chinese(self) -> None:
        root = self._temp_root()
        odd_state = root / "任务 空间" / "state dir"
        odd_cache = root / "任务 空间" / "plugin cache"
        launcher = self.make_launcher(state_dir=odd_state, plugin_cache_dir=odd_cache)

        task_id = "task-paths-odd-dir"
        result = launcher.run_task(base_request(task_id), timeout=90.0)
        self.assertEqual(result["status"], "completed", result)
        self.assertEqual(result["exit_code"], 0)

        workspace = launcher.workspace(task_id)
        self.assertTrue(workspace.is_dir(), workspace)
        self.assertEqual(workspace.name, task_id)
        self.assertEqual(workspace.parent.parent.resolve(), odd_state.resolve())
        self.assertTrue((workspace / "plugin").is_dir(), "the plugin must be materialized in the task workspace")

        for name in EVIDENCE_FILES:
            path = workspace / name
            self.assertTrue(path.is_file(), f"missing workspace evidence file: {name}")
            text = path.read_text(encoding="utf-8")  # must be valid UTF-8, even on a Chinese path
            self.assertNotIn("\ufffd", text)

        for name in ("request.json", "context.json", "mcp.json", "agent.command.json", "result.json", "agent.received.json"):
            read_json(workspace / name)
        for line in (workspace / "events.jsonl").read_text(encoding="utf-8").splitlines():
            if line.strip():
                json.loads(line)

        cache_dir = Path(result["plugin"]["cache_dir"])
        self.assertTrue(cache_dir.is_dir(), cache_dir)
        self.assertEqual(cache_dir.resolve().parent, odd_cache.resolve())

        # Evidence only ever lives below the launcher state dir, never in the repo.
        state = odd_state.resolve()
        self.assertFalse(state.is_relative_to(ROOT.resolve()), f"{state} must not be inside {ROOT}")
        self.assertFalse((ROOT / "tasks").exists(), "the launcher must not create a 'tasks' directory in the repo")

    def test_task_id_with_dots_dashes_and_underscores(self) -> None:
        launcher = self.make_launcher()
        task_id = "Task.01_A-b"
        result = launcher.run_task(base_request(task_id), timeout=90.0)
        self.assertEqual(result["task_id"], task_id)
        self.assertEqual(result["status"], "completed", result)
        self.assertEqual(result["exit_code"], 0)

        workspace = launcher.workspace(task_id)
        self.assertEqual(workspace.name, task_id)
        self.assertTrue(workspace.is_dir(), workspace)
        status, document = launcher.task(task_id)
        self.assertEqual(status, 200, document)
        self.assertEqual(document["task_id"], task_id)
        self.assertTrue(document["terminal"])
        status, events_document = launcher.events(task_id, 0)
        self.assertEqual(status, 200, events_document)
        self.assertGreaterEqual(len(events_document["events"]), 1)

    def test_chinese_user_prompt_is_preserved_end_to_end(self) -> None:
        launcher = self.make_launcher()
        prompt = "帮我检查这个原理图的电源部分：±5V、3.3V 与 GND 是否存在明显问题？"
        task_id = "task-paths-chinese-prompt"
        result = launcher.run_task(base_request(task_id, user_prompt=prompt), timeout=90.0)
        self.assertEqual(result["status"], "completed", result)

        workspace = launcher.workspace(task_id)
        request_document = read_json(workspace / "request.json")
        self.assertEqual(request_document["goal"]["user_prompt"], prompt)

        # The prompt reaches the agent as one exact argv element (never re-encoded,
        # never shell-split).
        received = read_json(workspace / "agent.received.json")
        self.assertIn(prompt, received["argv"])
        self.assertEqual(received["argv"].count(prompt), 1)
        self.assertEqual(received["env"]["ZHIGOU_TASK_ID"], task_id)
        self.assertEqual(received["model"], "fake")
        self.assertEqual(received["real_eda"], "NOT RUN")

        # Chinese text survives the stream-json -> log pipeline as UTF-8.
        stdout_log = (workspace / "agent.stdout.log").read_text(encoding="utf-8")
        self.assertIn("加载 design-hardware Skill（fake）。", stdout_log)


if __name__ == "__main__":
    unittest.main()
