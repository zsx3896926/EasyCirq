"""Test support: drive a real launcher process over loopback HTTP.

The tests never import the implementation in-process.  They spawn
``python -m task_launcher serve`` exactly like an EDA trigger surface would,
talk to it with ``http.client`` and assert on the JSON bodies and on the task
workspace evidence.  That keeps ``unittest discover`` free of import/path side
effects and verifies the real entry point, argument parsing and process
behaviour.

No test in this package calls a real EDA, a daemon, a connector or the network:
the agent is the bundled fake agent, and every assertion about the real world is
``NOT RUN``.
"""

from __future__ import annotations

import http.client
import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
#: The 2026-10 rename moved the Skill from ``easycirq/`` to ``easycirq/``;
#: tests follow whatever the checkout actually contains.
SKILL_DIR = ROOT / "easycirq"
if not (SKILL_DIR / "SKILL.md").is_file():
    SKILL_DIR = ROOT / "easycirq"
SKILL_NAME = SKILL_DIR.name
TESTS_DIR = Path(__file__).resolve().parent

#: Shared plugin build cache for the whole test session.  The plugin tree is
#: ~13 MB / 622 files; rebuilding it per launcher process would dominate the
#: suite wall time.  The cache key includes the Skill fingerprint, so a stale
#: entry can never be used for a changed Skill.
PLUGIN_CACHE = Path(tempfile.gettempdir()) / "easycirq-launcher-test-plugin-cache"

START_SCHEMA = "easycirq.task-launcher.start/v1"
RESULT_SCHEMA = "easycirq.task-launcher.result/v1"
LAUNCHER_VERSION = "0.1.0"
SKILL_VERSION = (SKILL_DIR / ".version").read_text(encoding="utf-8").strip()
PLUGIN_VERSION = "0.1.0"


def base_request(
    task_id: str = "task-test-001",
    *,
    timeout_s: int = 60,
    max_events: int = 10000,
    mode: str = "read_only",
    user_prompt: str = "帮我检查这个原理图的电源部分有没有明显问题",
    skill_version: str | None = None,
    plugin_version: str | None = None,
    launcher_version: str = LAUNCHER_VERSION,
) -> dict:
    """A valid ``easycirq.task-launcher.start/v1`` request for tests."""

    return {
        "schema": START_SCHEMA,
        "task_id": task_id,
        "client": {"name": "easyeda-pro-stub", "version": "0.0.0"},
        "toolchain": {
            "launcher": launcher_version,
            "skill": skill_version if skill_version is not None else SKILL_VERSION,
            "plugin": plugin_version if plugin_version is not None else PLUGIN_VERSION,
        },
        "mode": mode,
        "context": {
            "project": {"name": "demo", "revision": "rev-A"},
            "document": {"kind": "schematic", "id": "doc-1"},
            "page": {"name": "P1"},
            "selection": [{"kind": "component", "designator": "U1"}],
            "snapshot_sha256": None,
            "missing_fields": ["snapshot_sha256", "pcb_geometry"],
        },
        "goal": {"user_prompt": user_prompt, "intent": "inspect"},
        "limits": {"timeout_s": timeout_s, "max_events": max_events},
    }


def write_request(directory: Path, document: dict, name: str = "request.json") -> Path:
    path = Path(directory) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return path


def read_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


#: Frozen case requests carry these placeholders instead of hard-coded versions,
#: so a Skill version bump on main does not invalidate the frozen benchmark.
TOOLCHAIN_PLACEHOLDERS = {
    "@launcher": LAUNCHER_VERSION,
    "@skill": SKILL_VERSION,
    "@plugin": PLUGIN_VERSION,
}


def resolve_toolchain_placeholders(request: dict) -> dict:
    """Return a copy of ``request`` with toolchain placeholders resolved."""

    document = json.loads(json.dumps(request))
    toolchain = document.get("toolchain")
    if isinstance(toolchain, dict):
        for key in ("launcher", "skill", "plugin"):
            value = toolchain.get(key)
            if isinstance(value, str) and value in TOOLCHAIN_PLACEHOLDERS:
                toolchain[key] = TOOLCHAIN_PLACEHOLDERS[value]
    return document


def resolve_frozen_case_request(case_id: str, out_dir: Path) -> Path:
    """Write a resolved copy of ``benchmarks/task-launcher/cases/<id>/request.json``."""

    source = ROOT / "benchmarks" / "task-launcher" / "cases" / case_id / "request.json"
    if not source.is_file():
        raise AssertionError(f"frozen benchmark case request is missing: {source}")
    document = resolve_toolchain_placeholders(json.loads(source.read_text(encoding="utf-8")))
    target = Path(out_dir) / case_id / "request.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return target


def pid_alive(pid: int) -> bool:
    """Cross-platform process liveness check (used for no-orphan assertions)."""

    if pid <= 0:
        return False
    if os.name == "nt":  # pragma: no cover - Windows only
        completed = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return str(pid) in (completed.stdout or "")
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:  # pragma: no cover - process exists, owned by someone else
        return True
    return True


def wait_until(predicate, timeout: float = 20.0, interval: float = 0.05) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


class LauncherProcess:
    """A ``python -m task_launcher serve`` subprocess plus a JSON HTTP client."""

    def __init__(
        self,
        *,
        state_dir: Path | None = None,
        skill_dir: Path | None = None,
        plugin_dir: Path | None = None,
        plugin_cache_dir: Path | None = None,
        agent_profile: str = "fake",
        claude_exe: str | None = None,
        fake_scenario: str = "stream",
        max_concurrent: int = 1,
        agent_argv_template: Path | None = None,
        extra_args: list[str] | None = None,
        token: str = "test-token-0123456789abcdef0123456789abcdef",
        fixed_token: bool = True,
        keep_state: bool = False,
        timeout_s: float = 60.0,
    ) -> None:
        self._temp_root = None
        if state_dir is None:
            self._temp_root = Path(tempfile.mkdtemp(prefix="easycirq-launcher-test-"))
            state_dir = self._temp_root / "state"
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.keep_state = keep_state
        self.skill_dir = Path(skill_dir) if skill_dir is not None else SKILL_DIR
        self.plugin_dir = Path(plugin_dir) if plugin_dir is not None else None
        self.plugin_cache_dir = Path(plugin_cache_dir) if plugin_cache_dir is not None else PLUGIN_CACHE
        self.token = token
        self.token_file = self.state_dir / "token.txt"
        self.token_file.write_text(token + "\n", encoding="utf-8", newline="\n") if fixed_token else None
        self.proc: subprocess.Popen | None = None
        self.base_url = ""
        self.port = 0
        self.ready: dict = {}
        self._lines: "queue.Queue[str]" = queue.Queue()
        self._stderr_lines: list[str] = []
        self._stdout_rest: list[str] = []
        self.launch_failure: str | None = None

        argv = [
            sys.executable,
            "-m",
            "task_launcher",
            "serve",
            "--port",
            "0",
            "--state-dir",
            str(self.state_dir),
            "--skill-dir",
            str(self.skill_dir),
            "--agent-profile",
            agent_profile,
            "--fake-scenario",
            fake_scenario,
            "--max-concurrent",
            str(max_concurrent),
            "--plugin-cache-dir",
            str(self.plugin_cache_dir),
            "--token-file",
            str(self.token_file),
        ]
        if plugin_dir is not None:
            argv.extend(["--plugin-dir", str(plugin_dir)])
        if claude_exe is not None:
            argv.extend(["--claude-exe", claude_exe])
        if agent_argv_template is not None:
            argv.extend(["--agent-argv-template", str(agent_argv_template)])
        if extra_args:
            argv.extend([str(item) for item in extra_args])

        env = dict(os.environ)
        env["PYTHONPATH"] = str(ROOT)
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        self.proc = subprocess.Popen(
            argv,
            cwd=str(ROOT),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()
        try:
            line = self._lines.get(timeout=timeout_s)
        except queue.Empty:
            self.launch_failure = self.stderr_text()
            self.close()
            raise AssertionError(f"launcher did not print its listening line; stderr:\n{self.launch_failure}")
        try:
            ready = json.loads(line)
        except json.JSONDecodeError:
            self.launch_failure = f"unparsable first stdout line: {line!r}\nstderr:\n{self.stderr_text()}"
            self.close()
            raise AssertionError(self.launch_failure)
        if ready.get("event") != "listening":
            self.launch_failure = f"unexpected first line: {ready!r}"
            self.close()
            raise AssertionError(self.launch_failure)
        self.ready = ready
        self.port = int(ready["port"])
        self.base_url = ready["url"]

    # -- process plumbing --------------------------------------------------
    def _read_stdout(self) -> None:
        assert self.proc is not None and self.proc.stdout is not None
        for line in self.proc.stdout:
            stripped = line.strip()
            if not stripped:
                continue
            if self._lines.empty() and stripped.startswith("{"):
                self._lines.put(stripped)
            else:
                self._stdout_rest.append(stripped)

    def _read_stderr(self) -> None:
        assert self.proc is not None and self.proc.stderr is not None
        for line in self.proc.stderr:
            self._stderr_lines.append(line.rstrip())

    def stderr_text(self) -> str:
        return "\n".join(self._stderr_lines)

    def stdout_rest(self) -> list[str]:
        return list(self._stdout_rest)

    # -- HTTP --------------------------------------------------------------
    def request(
        self,
        method: str,
        path: str,
        body: Any = None,
        *,
        token: str | None = "__default__",
        headers: dict[str, str] | None = None,
        timeout: float = 60.0,
    ) -> tuple[int, Any]:
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=timeout)
        request_headers: dict[str, str] = {"Accept": "application/json"}
        if token == "__default__":
            token = self.token
        if token is not None:
            request_headers["Authorization"] = f"Bearer {token}"
        data = None
        if body is not None:
            if isinstance(body, (bytes, str)):
                data = body.encode("utf-8") if isinstance(body, str) else body
            else:
                data = json.dumps(body, ensure_ascii=False).encode("utf-8")
                request_headers["Content-Type"] = "application/json"
        if headers:
            request_headers.update(headers)
        try:
            connection.request(method, path, body=data, headers=request_headers)
            response = connection.getresponse()
            raw = response.read().decode("utf-8")
            status = response.status
        finally:
            connection.close()
        try:
            document = json.loads(raw)
        except json.JSONDecodeError:
            raise AssertionError(f"non-JSON response from {method} {path}: status={status} body={raw[:500]}")
        return status, document

    def start(self, request: dict, **kwargs: Any) -> tuple[int, dict]:
        return self.request("POST", "/task/start", request, **kwargs)

    def send_start_bytes(self, data: bytes, *, content_type: str = "application/json", token: str | None = "__default__") -> tuple[int, Any]:
        """POST raw bytes to /task/start (malformed JSON / duplicate key tests)."""

        return self.request(
            "POST",
            "/task/start",
            data,
            token=token,
            headers={"Content-Type": content_type},
        )

    def refresh_token_from_file(self) -> str:
        self.token = self.token_file.read_text(encoding="utf-8").strip()
        return self.token

    def task(self, task_id: str, **kwargs: Any) -> tuple[int, dict]:
        return self.request("GET", f"/task/{task_id}", **kwargs)

    def events(self, task_id: str, since: int = 0, **kwargs: Any) -> tuple[int, dict]:
        return self.request("GET", f"/task/{task_id}/events?since={since}", **kwargs)

    def result(self, task_id: str, **kwargs: Any) -> tuple[int, dict]:
        return self.request("GET", f"/task/{task_id}/result", **kwargs)

    def cancel(self, task_id: str, **kwargs: Any) -> tuple[int, dict]:
        return self.request("POST", f"/task/{task_id}/cancel", **kwargs)

    def health(self, **kwargs: Any) -> tuple[int, dict]:
        return self.request("GET", "/health", token=None, **kwargs)

    # -- convenience -------------------------------------------------------
    def wait_terminal(self, task_id: str, timeout: float = 60.0, interval: float = 0.05) -> dict:
        deadline = time.time() + timeout
        while time.time() < deadline:
            status, document = self.task(task_id)
            assert status == 200, (status, document)
            if document.get("terminal"):
                return document
            time.sleep(interval)
        raise AssertionError(f"task {task_id} did not reach a terminal state within {timeout}s")

    def run_task(self, request: dict, timeout: float = 60.0) -> dict:
        status, accepted = self.start(request)
        assert status == 202, (status, accepted)
        self.wait_terminal(request["task_id"], timeout=timeout)
        status, result = self.result(request["task_id"])
        assert status == 200, (status, result)
        return result

    def workspace(self, task_id: str) -> Path:
        return self.state_dir / "tasks" / task_id

    # -- discovery helpers -------------------------------------------------
    def event_payloads(self, task_id: str) -> list[dict]:
        status, document = self.events(task_id, 0)
        assert status == 200
        return [event for event in document["events"] if event["type"] == "agent_event"]

    # -- teardown ----------------------------------------------------------
    def close(self, timeout: float = 20.0) -> None:
        proc = self.proc
        if proc is not None and proc.poll() is None:
            if os.name == "nt":  # pragma: no cover - Windows only
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                )
            else:
                proc.terminate()
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:  # pragma: no cover - defensive
                proc.kill()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    pass
        for stream in (proc.stdout if proc else None, proc.stderr if proc else None):
            try:
                if stream is not None:
                    stream.close()
            except OSError:  # pragma: no cover
                pass
        if self._temp_root is not None and not self.keep_state:
            shutil.rmtree(self._temp_root, ignore_errors=True)

    def cleanup_workspaces(self) -> None:
        shutil.rmtree(self.state_dir / "tasks", ignore_errors=True)

    def __enter__(self) -> "LauncherProcess":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


class LauncherTestCase(unittest.TestCase):
    """Base class with per-test launcher creation and reliable teardown."""

    launcher: LauncherProcess

    def make_launcher(self, **kwargs: Any) -> LauncherProcess:
        launcher = LauncherProcess(**kwargs)
        self.addCleanup(launcher.close)
        self.launcher = launcher
        return launcher

    def assert_error(self, response: tuple[int, dict], http_status: int, code: str) -> dict:
        status, document = response
        self.assertEqual(status, http_status, document)
        self.assertIn("error", document)
        self.assertEqual(document["error"]["code"], code, document)
        self.assertIn("message", document["error"])
        return document["error"]


def repo_file_snapshot(paths: list[Path]) -> dict:
    """Snapshot file paths/sizes/mtimes so a test can prove nothing was written."""

    snapshot: dict[str, tuple[int, int]] = {}
    for base in paths:
        base = Path(base)
        if base.is_file():
            stat = base.stat()
            snapshot[str(base.relative_to(ROOT)).replace("\\", "/")] = (stat.st_size, stat.st_mtime_ns)
            continue
        for path in sorted(base.rglob("*")):
            if path.is_file():
                stat = path.stat()
                snapshot[str(path.relative_to(ROOT)).replace("\\", "/")] = (stat.st_size, stat.st_mtime_ns)
    return snapshot


__all__ = [
    "ROOT",
    "SKILL_DIR",
    "SKILL_NAME",
    "PLUGIN_CACHE",
    "START_SCHEMA",
    "RESULT_SCHEMA",
    "LAUNCHER_VERSION",
    "SKILL_VERSION",
    "PLUGIN_VERSION",
    "base_request",
    "write_request",
    "read_json",
    "TOOLCHAIN_PLACEHOLDERS",
    "resolve_toolchain_placeholders",
    "resolve_frozen_case_request",
    "pid_alive",
    "wait_until",
    "LauncherProcess",
    "LauncherTestCase",
    "repo_file_snapshot",
]
