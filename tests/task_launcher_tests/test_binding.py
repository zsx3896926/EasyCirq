"""Binding / listen tests (task book §3.2, §4.14).

The launcher is a local sidecar: it may only bind loopback.  ``serve`` must
therefore

* refuse ``--host 0.0.0.0`` immediately with exit code 2 and a JSON
  ``LOOPBACK_ONLY`` error on stdout (no "listening" line);
* report ``BIND_FAILED`` (exit code 2) when the requested TCP port is already
  taken instead of running degraded;
* default to ``127.0.0.1`` and print a ready line whose URL/port are the real
  loopback endpoint the client can reach.

The CLI is spawned as a plain subprocess (``python -m task_launcher serve``),
exactly like an EDA trigger surface would start it.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from .support import ROOT, LauncherTestCase


def _serve_env() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env


def _run_serve(args: list[str], *, timeout: float = 60.0) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "task_launcher", "serve", *args],
        cwd=str(ROOT),
        env=_serve_env(),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


class BindingTests(LauncherTestCase):
    def _single_json_document(self, completed: subprocess.CompletedProcess) -> dict:
        stdout = (completed.stdout or "").strip()
        self.assertTrue(stdout, f"serve printed no JSON on stdout; stderr:\n{completed.stderr}")
        try:
            document = json.loads(stdout)
        except json.JSONDecodeError:
            self.fail(f"serve stdout is not JSON: {stdout[:500]!r}; stderr:\n{completed.stderr}")
        self.assertIsInstance(document, dict)
        return document

    def test_non_loopback_host_is_refused_quickly(self) -> None:
        started = time.time()
        completed = _run_serve(["--host", "0.0.0.0", "--port", "0"])
        elapsed = time.time() - started
        self.assertNotEqual(completed.returncode, 0, completed)
        self.assertEqual(completed.returncode, 2, completed)
        self.assertLess(elapsed, 20.0, "refusing a public bind must not hang")
        document = self._single_json_document(completed)
        self.assertNotIn("event", document, "a refused bind must not print a listening line")
        error = document["error"]
        self.assertEqual(error["code"], "LOOPBACK_ONLY")
        self.assertEqual(error["detail"]["host"], "0.0.0.0")
        self.assertIn("127.0.0.1", error["detail"]["allowed"])

    def test_port_already_in_use_reports_bind_failed(self) -> None:
        state_dir = Path(tempfile.mkdtemp(prefix="zhigou-bind-test-"))
        self.addCleanup(shutil.rmtree, state_dir, True)
        holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.addCleanup(holder.close)
        holder.bind(("127.0.0.1", 0))
        holder.listen(5)
        port = int(holder.getsockname()[1])

        completed = _run_serve(["--port", str(port), "--state-dir", str(state_dir)])
        self.assertNotEqual(completed.returncode, 0, completed)
        self.assertEqual(completed.returncode, 2, completed)
        document = self._single_json_document(completed)
        self.assertNotIn("event", document)
        error = document["error"]
        self.assertEqual(error["code"], "BIND_FAILED")
        self.assertEqual(error["detail"]["port"], port)
        self.assertEqual(error["detail"]["host"], "127.0.0.1")
        self.assertIn("reason", error["detail"])

    def test_default_binding_is_loopback_and_ready_line_is_usable(self) -> None:
        launcher = self.make_launcher()  # no --host => contract default
        ready = launcher.ready
        self.assertEqual(ready["event"], "listening")
        self.assertEqual(ready["host"], "127.0.0.1")
        self.assertGreater(ready["port"], 0)
        self.assertEqual(ready["url"], f"http://127.0.0.1:{ready['port']}")
        self.assertNotIn("0.0.0.0", ready["url"])
        self.assertEqual(ready["mode"], "read_only")
        self.assertEqual(ready["real_eda"], "NOT RUN")

        status, health = launcher.health()
        self.assertEqual(status, 200, health)
        self.assertEqual(health["status"], "ok")
        self.assertEqual(health["tasks_running"], 0)


if __name__ == "__main__":
    unittest.main()
