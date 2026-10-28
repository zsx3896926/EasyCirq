"""CLI tests (task book §3.1 / §4.13): version, health, run, JSON-only stdout."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from .support import (
    PLUGIN_CACHE,
    ROOT,
    SKILL_VERSION,
    LauncherProcess,
    base_request,
    write_request,
)


def run_cli(args: list[str], timeout: float = 180.0) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return subprocess.run(
        [sys.executable, "-m", "task_launcher", *args],
        cwd=str(ROOT),
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


class CLITests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="zhigou-cli-")
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.state = self.tmp / "state"

    def cli_json(self, completed: subprocess.CompletedProcess) -> dict:
        text = completed.stdout.strip()
        self.assertTrue(text, f"no JSON on stdout; stderr={completed.stderr}")
        try:
            document = json.loads(text)
        except json.JSONDecodeError:  # pragma: no cover - diagnostic path
            self.fail(f"stdout is not a single JSON document: {text[:500]!r}\nstderr={completed.stderr}")
        return document

    def test_version(self) -> None:
        completed = run_cli(["version"])
        self.assertEqual(completed.returncode, 0, completed.stderr)
        document = self.cli_json(completed)
        self.assertEqual(document["launcher"], "0.1.0")
        self.assertEqual(document["skill"], SKILL_VERSION)
        self.assertEqual(document["plugin"], "0.1.0")
        self.assertEqual(document["schemas"]["start"], "zhigou.task-launcher.start/v1")
        self.assertEqual(document["schemas"]["result"], "zhigou.task-launcher.result/v1")

    def test_health_local(self) -> None:
        completed = run_cli(
            ["health", "--state-dir", str(self.state), "--plugin-cache-dir", str(PLUGIN_CACHE)]
        )
        self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
        document = self.cli_json(completed)
        self.assertEqual(document["status"], "ok")
        self.assertEqual(document["skill_version"], SKILL_VERSION)
        self.assertTrue(document["agent"]["available"])
        self.assertEqual(document["agent"]["profile"], "fake")

    def test_health_against_running_launcher(self) -> None:
        launcher = LauncherProcess()
        self.addCleanup(launcher.close)
        completed = run_cli(["health", "--base-url", launcher.base_url])
        self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
        document = self.cli_json(completed)
        self.assertEqual(document["status"], "ok")
        self.assertEqual(document["version"], "0.1.0")

    def test_health_unreachable_is_exit_1(self) -> None:
        completed = run_cli(["health", "--base-url", "http://127.0.0.1:1"], timeout=60)
        self.assertEqual(completed.returncode, 1, completed.stderr)
        document = self.cli_json(completed)
        self.assertIn(document["error"]["code"], ("HEALTH_UNAVAILABLE",))

    def test_run_completes_and_prints_only_json(self) -> None:
        request = write_request(self.tmp, base_request("task-cli-run-ok"))
        completed = run_cli(
            [
                "run",
                "--request",
                str(request),
                "--state-dir",
                str(self.state),
                "--plugin-cache-dir",
                str(PLUGIN_CACHE),
            ]
        )
        self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
        document = self.cli_json(completed)
        self.assertEqual(document["status"], "completed")
        self.assertEqual(document["task_id"], "task-cli-run-ok")
        self.assertEqual(document["real_eda"], "NOT RUN")
        self.assertEqual(document["eda_calls"], 0)
        self.assertEqual(len(completed.stdout.strip().splitlines()), 1)
        self.assertTrue((self.state / "tasks" / "task-cli-run-ok" / "result.json").is_file())

    def test_run_write_mode_is_protocol_error(self) -> None:
        request = write_request(self.tmp, base_request("task-cli-write", mode="write"))
        completed = run_cli(
            [
                "run",
                "--request",
                str(request),
                "--state-dir",
                str(self.state),
                "--plugin-cache-dir",
                str(PLUGIN_CACHE),
            ]
        )
        self.assertEqual(completed.returncode, 2, completed.stderr)
        document = self.cli_json(completed)
        self.assertEqual(document["error"]["code"], "WRITE_MODE_NOT_SUPPORTED")

    def test_run_version_mismatch_is_protocol_error(self) -> None:
        request = write_request(self.tmp, base_request("task-cli-mismatch", skill_version="9.9.9"))
        completed = run_cli(
            [
                "run",
                "--request",
                str(request),
                "--state-dir",
                str(self.state),
                "--plugin-cache-dir",
                str(PLUGIN_CACHE),
            ]
        )
        self.assertEqual(completed.returncode, 2, completed.stderr)
        document = self.cli_json(completed)
        self.assertEqual(document["error"]["code"], "VERSION_MISMATCH")

    def test_run_missing_request_file(self) -> None:
        completed = run_cli(["run", "--request", str(self.tmp / "does-not-exist.json")])
        self.assertEqual(completed.returncode, 2)
        document = self.cli_json(completed)
        self.assertEqual(document["error"]["code"], "INVALID_REQUEST")


if __name__ == "__main__":
    unittest.main()
