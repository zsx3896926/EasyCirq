#!/usr/bin/env python3
"""Frozen offline benchmark for the B1 task launcher (``easycirq.task-launcher``).

The benchmark is deliberately end-to-end and deterministic:

* every case owns a ``request.json`` (a real ``task.start`` request) and a
  declarative ``expected.json``;
* for each case the runner starts a **fresh** ``python -m task_launcher serve``
  process on an OS-assigned loopback port (fake agent only), then runs
  ``python -m task_launcher.stub_connector`` as a subprocess against it;
* the stub's single JSON stdout document, its process exit code and the
  launcher-owned task evidence (``events.jsonl``, ``agent.command.json``,
  ``agent.received.json``, ``result.json``) are asserted against
  ``expected.json``;
* ``results.json`` is written with the honesty fields required by the task
  book: ``simulated: true``, ``offline: true``, ``real_eda: "NOT RUN"``,
  ``eda_calls: 0``, ``project_writes: 0``, ``network_calls: 0``,
  ``agent: "fake"``.

No network, no EDA tool, no daemon, no connector and no real model are used.
``--real-claude`` never launches a real model: it only marks the real-Claude
cases ``NOT RUN``; the simulated cases still have to pass for exit code 0.

Usage::

    python benchmarks/task-launcher/run_benchmark.py
    python benchmarks/task-launcher/run_benchmark.py --cases DIR --output PATH
    python benchmarks/task-launcher/run_benchmark.py --real-claude

Exit codes: ``0`` all cases passed, ``1`` at least one case failed,
``2`` the benchmark could not run (bad arguments / no cases).
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BENCHMARK_DIR = Path(__file__).resolve().parent
DEFAULT_CASES_DIR = BENCHMARK_DIR / "cases"
DEFAULT_OUTPUT = BENCHMARK_DIR / "results.json"

BENCHMARK_SCHEMA = "easycirq.task-launcher.benchmark/v1"
CASE_SCHEMA = "easycirq.task-launcher.benchmark-case/v1"
STUB_SCHEMA = "easycirq.task-launcher.stub-result/v1"
RESULT_SCHEMA = "easycirq.task-launcher.result/v1"

LAUNCHER_VERSION = "0.1.0"
PLUGIN_VERSION = "0.1.0"
SKILL_DIR = ROOT / "easycirq"
if not (SKILL_DIR / "SKILL.md").is_file():
    SKILL_DIR = ROOT / "easycirq"
SKILL_VERSION = (SKILL_DIR / ".version").read_text(encoding="utf-8").strip()

#: Frozen case requests use placeholders instead of hard-coded versions, so a
#: Skill version bump on main does not break the benchmark.  Deliberately
#: mismatched toolchain versions in the mismatch cases stay literal.
TOOLCHAIN_PLACEHOLDERS = {
    "@launcher": LAUNCHER_VERSION,
    "@skill": SKILL_VERSION,
    "@plugin": PLUGIN_VERSION,
}

#: Fixed benchmark bearer token.  It lives only in the per-run temporary state
#: directory and is never written to ``results.json``.
TOKEN = "benchmark-token-0123456789abcdef0123456789abcdef"

CASE_TIMEOUT_S = 180.0
LAUNCHER_START_TIMEOUT_S = 120.0
DEFAULT_POLL_INTERVAL_S = 0.05
DEFAULT_STUB_TIMEOUT_S = 120.0

REQUIRED_AGENT_FLAGS = (
    "--plugin-dir",
    "--append-system-prompt-file",
    "--mcp-config",
    "--output-format",
)

NOT_PROOF = [
    "fake agent outcomes do not prove real Claude Code behaviour, and do not prove that a model read the Skill",
    "real_eda=NOT RUN: no EDA tool, daemon, connector or hardware was used; no network calls were made",
    "eda_calls=0 and project_writes=0: no design file was read, changed, saved or opened",
    "the benchmark proves the trigger -> launcher -> agent contract (HTTP, schema, version gate, timeout/cancel/concurrency, stream-json robustness), not engineering correctness",
    "plugin/system-prompt mounting is proven by argv evidence only, not by model compliance",
]

NOT_RUN = ["real_eda", "real_claude", "hardware_test", "network_calls"]


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------


def _env() -> dict[str, str]:
    """Subprocess environment: repo importable, UTF-8 output, no extra state."""

    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env


def _pid_alive(pid: int) -> bool:
    """Cross-platform process liveness check (used for the no-orphan assertion)."""

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
    except PermissionError:  # pragma: no cover - owned by someone else
        return True
    return True


def _sanitize(text: Any, temp_root: Path) -> str:
    """Remove absolute paths and the token from anything stored in results.json."""

    value = str(text)
    for absolute, placeholder in ((str(temp_root), "<temp>"), (temp_root.as_posix(), "<temp>")):
        value = value.replace(absolute, placeholder)
    for absolute, placeholder in ((str(ROOT), "<repo>"), (ROOT.as_posix(), "<repo>")):
        value = value.replace(absolute, placeholder)
    value = value.replace(TOKEN, "<token>")
    value = value.strip()
    return value[:800]


def _matches(actual: Any, expected: Any) -> bool:
    """Type-strict equality for declarative ``checks`` (True is not 1, 1 is not 1.0)."""

    if expected is None:
        return actual is None
    if isinstance(expected, bool):
        return isinstance(actual, bool) and actual is expected
    if isinstance(expected, int) and not isinstance(expected, bool):
        return isinstance(actual, int) and not isinstance(actual, bool) and actual == expected
    if isinstance(expected, float):
        return isinstance(actual, (int, float)) and not isinstance(actual, bool) and actual == expected
    return actual == expected


def _lookup(document: Any, dotted: str) -> Any:
    current = document
    for part in dotted.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            raise KeyError(dotted)
    return current


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_toolchain_placeholders(request: dict) -> dict:
    """Resolve ``@launcher``/``@skill``/``@plugin`` in a frozen case request."""

    resolved = json.loads(json.dumps(request))
    toolchain = resolved.get("toolchain")
    if isinstance(toolchain, dict):
        for key in ("launcher", "skill", "plugin"):
            value = toolchain.get(key)
            if isinstance(value, str) and value in TOOLCHAIN_PLACEHOLDERS:
                toolchain[key] = TOOLCHAIN_PLACEHOLDERS[value]
    return resolved


def _read_events(path: Path) -> list[dict]:
    events: list[dict] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(event, dict):
                    events.append(event)
    except OSError:
        return []
    return events


# ---------------------------------------------------------------------------
# launcher subprocess
# ---------------------------------------------------------------------------


class LauncherStartError(RuntimeError):
    """The launcher process did not print its listening line."""


class BenchLauncher:
    """One ``python -m task_launcher serve`` subprocess (fake agent only)."""

    def __init__(self, argv: list[str]) -> None:
        self.proc = subprocess.Popen(
            argv,
            cwd=str(ROOT),
            env=_env(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        self._first: "queue.Queue[str]" = queue.Queue()
        self._stdout_rest: list[str] = []
        self._stderr_lines: list[str] = []
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()
        try:
            line = self._first.get(timeout=LAUNCHER_START_TIMEOUT_S)
        except queue.Empty:
            self.close()
            raise LauncherStartError(
                f"launcher did not print its listening line within {LAUNCHER_START_TIMEOUT_S}s; stderr:\n"
                + self.stderr_text()
            ) from None
        try:
            ready = json.loads(line)
        except json.JSONDecodeError:
            self.close()
            raise LauncherStartError(f"launcher first stdout line is not JSON: {line!r}") from None
        if not isinstance(ready, dict) or ready.get("event") != "listening":
            self.close()
            raise LauncherStartError(f"unexpected launcher first line: {ready!r}")
        self.ready = ready
        self.base_url = str(ready["url"])
        self.port = int(ready["port"])

    def _read_stdout(self) -> None:
        assert self.proc.stdout is not None
        for line in self.proc.stdout:
            stripped = line.strip()
            if not stripped:
                continue
            if self._first.empty():
                self._first.put(stripped)
            else:
                self._stdout_rest.append(stripped)

    def _read_stderr(self) -> None:
        assert self.proc.stderr is not None
        for line in self.proc.stderr:
            self._stderr_lines.append(line.rstrip())

    def stderr_text(self) -> str:
        return "\n".join(self._stderr_lines)

    def close(self) -> None:
        proc = self.proc
        if proc.poll() is None:
            if os.name == "nt":  # pragma: no cover - Windows only
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                )
            else:
                proc.terminate()
            try:
                proc.wait(timeout=20)
            except subprocess.TimeoutExpired:  # pragma: no cover - defensive
                proc.kill()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    pass
        for stream in (proc.stdout, proc.stderr):
            try:
                if stream is not None:
                    stream.close()
            except OSError:  # pragma: no cover
                pass


def _launcher_argv(
    launcher_config: dict,
    *,
    state_dir: Path,
    token_file: Path,
    plugin_cache_dir: Path,
) -> list[str]:
    argv = [
        sys.executable,
        "-m",
        "task_launcher",
        "serve",
        "--port",
        "0",
        "--state-dir",
        str(state_dir),
        "--skill-dir",
        str(SKILL_DIR),
        "--agent-profile",
        str(launcher_config.get("agent_profile", "fake")),
        "--fake-scenario",
        str(launcher_config.get("fake_scenario", "stream")),
        "--max-concurrent",
        str(int(launcher_config.get("max_concurrent", 1))),
        "--plugin-cache-dir",
        str(plugin_cache_dir),
        "--token-file",
        str(token_file),
    ]
    claude_exe = launcher_config.get("claude_exe")
    if claude_exe:
        argv.extend(["--claude-exe", str(claude_exe)])
    return argv


def _stub_argv(
    launcher: BenchLauncher,
    *,
    request_path: Path,
    token_file: Path,
    stub_config: dict,
) -> list[str]:
    poll_interval = float(stub_config.get("poll_interval", DEFAULT_POLL_INTERVAL_S))
    timeout = float(stub_config.get("timeout", DEFAULT_STUB_TIMEOUT_S))
    argv = [
        sys.executable,
        "-m",
        "task_launcher.stub_connector",
        "--base-url",
        launcher.base_url,
        "--token-file",
        str(token_file),
        "--case",
        str(request_path),
        "--poll-interval",
        str(poll_interval),
        "--timeout",
        str(timeout),
    ]
    cancel_after_events = int(stub_config.get("cancel_after_events") or 0)
    if cancel_after_events > 0:
        argv.extend(["--cancel-after-events", str(cancel_after_events)])
    concurrent_task_id = stub_config.get("concurrent_task_id")
    if concurrent_task_id:
        argv.extend(["--concurrent-task-id", str(concurrent_task_id)])
    return argv


# ---------------------------------------------------------------------------
# per-case workspace assertions
# ---------------------------------------------------------------------------


def _workspace_problems(
    workspace: Path,
    checks: list[dict],
    *,
    temp_root: Path,
    token: str,
    result: dict | None = None,
) -> list[str]:
    problems: list[str] = []
    events_path = workspace / "events.jsonl"
    events = _read_events(events_path)
    events_required = any(
        check.get("kind")
        in ("event_count_min", "event_type_present", "parse_error_count", "agent_event_payload_type_present")
        for check in checks
    )
    if events_required and not events:
        problems.append(f"workspace evidence missing or empty: {_sanitize(events_path, temp_root)}")
        return problems

    for check in checks:
        kind = check.get("kind")
        if kind == "event_count_min":
            minimum = int(check.get("min") or 0)
            if len(events) < minimum:
                problems.append(f"launcher evidence has {len(events)} events, expected at least {minimum}")
        elif kind == "event_type_present":
            event_type = check.get("type")
            if not any(event.get("type") == event_type for event in events):
                problems.append(f"workspace events lack a {event_type!r} event")
        elif kind == "parse_error_count":
            count = sum(1 for event in events if event.get("type") == "parse_error")
            if "equals" in check and count != int(check["equals"]):
                problems.append(f"parse_error event count is {count}, expected {check['equals']}")
            if "min" in check and count < int(check["min"]):
                problems.append(f"parse_error event count is {count}, expected at least {check['min']}")
        elif kind == "agent_event_payload_type_present":
            wanted = check.get("payload_type")
            found = any(
                event.get("type") == "agent_event"
                and isinstance(event.get("payload"), dict)
                and event["payload"].get("type") == wanted
                for event in events
            )
            if not found:
                problems.append(f"no agent_event carried the unknown payload type {wanted!r}")
        elif kind == "result_file_exists":
            if not (workspace / "result.json").is_file():
                problems.append("workspace result.json is missing")
        elif kind == "agent_command_required_flags":
            command_path = workspace / "agent.command.json"
            try:
                command = _read_json(command_path)
            except (OSError, json.JSONDecodeError):
                problems.append(f"cannot read agent command evidence: {_sanitize(command_path, temp_root)}")
                continue
            if command.get("required_flags_present") is not True:
                problems.append("agent.command.json does not claim required_flags_present")
            argv = command.get("argv") or []
            missing = [flag for flag in REQUIRED_AGENT_FLAGS if flag not in argv]
            if missing:
                problems.append(f"agent argv is missing mandatory routing flags: {', '.join(missing)}")
            if command.get("token_included") is not False:
                problems.append("agent.command.json does not declare token_included=false")
            try:
                serialized = json.dumps(command, ensure_ascii=False)
            except (TypeError, ValueError):
                serialized = ""
            if token and token in serialized:
                problems.append("the launcher token leaked into agent.command.json")
        elif kind == "no_orphan_agent":
            received_path = workspace / "agent.received.json"
            try:
                received = _read_json(received_path)
            except (OSError, json.JSONDecodeError):
                if result and result.get("status") == "cancelled":
                    # A cancel can be delivered before the agent process even
                    # starts (fast POSIX CI), so there is no recorded pid to
                    # orphan-check.  Non-cancel cases still assert this evidence.
                    continue
                problems.append(f"cannot read agent evidence: {_sanitize(received_path, temp_root)}")
                continue
            pid = int(received.get("pid") or 0)
            if pid <= 0:
                problems.append("agent.received.json does not record a pid")
            elif _pid_alive(pid):
                problems.append(f"agent process {pid} is still alive after the task reached a terminal state")
        else:
            problems.append(f"unknown workspace check kind: {kind!r}")
    return problems


# ---------------------------------------------------------------------------
# one case
# ---------------------------------------------------------------------------


def _new_row(case_id: str, description: str) -> dict:
    return {
        "id": case_id,
        "description": description,
        "passed": False,
        "problems": [],
        "duration_ms": 0,
        "exit_code": None,
        "start_http_status": None,
        "final_status": None,
        "event_count": None,
        "cancel_sent": None,
        "concurrent_start_http_status": None,
        "result_status": None,
    }


def run_case(
    case_dir: Path,
    expected_path: Path,
    *,
    temp_root: Path,
    plugin_cache_dir: Path,
) -> dict:
    """Run one case and return its ``results.json`` row (never raises)."""

    case_started = time.perf_counter()
    case_id = case_dir.name
    description = ""
    problems: list[str] = []
    row = _new_row(case_id, description)
    launcher: BenchLauncher | None = None
    try:
        try:
            expected = _read_json(expected_path)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            problems.append(f"expected.json cannot be parsed: {_sanitize(exc, temp_root)}")
            return row
        if not isinstance(expected, dict):
            problems.append("expected.json must be a JSON object")
            return row
        description = str(expected.get("description", ""))
        row["description"] = description
        if expected.get("schema") != CASE_SCHEMA:
            problems.append(f"expected.json schema is not {CASE_SCHEMA!r}")
        if expected.get("id") != case_id:
            problems.append(f"expected.json id {expected.get('id')!r} does not match the directory name")
        if problems:
            return row

        request_path = case_dir / "request.json"
        if not request_path.is_file():
            problems.append("request.json is missing")
            return row
        try:
            request_document = _read_json(request_path)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            problems.append(f"request.json cannot be parsed: {_sanitize(exc, temp_root)}")
            return row
        if not isinstance(request_document, dict):
            problems.append("request.json must be a JSON object")
            return row

        launcher_config = expected.get("launcher") or {}
        stub_config = expected.get("stub_args") or {}

        case_temp = temp_root / "cases" / case_id
        state_dir = case_temp / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        token_file = state_dir / "token.txt"
        token_file.write_text(TOKEN + "\n", encoding="utf-8", newline="\n")

        # Frozen requests carry ``@launcher`` / ``@skill`` / ``@plugin`` instead
        # of hard-coded versions so the benchmark stays valid when the Skill
        # version is bumped on main; the runner resolves them to the versions it
        # measured (the deliberate mismatch cases keep their literal versions).
        resolved_request_path = case_temp / "request.resolved.json"
        resolved_request_path.write_text(
            json.dumps(
                _resolve_toolchain_placeholders(request_document),
                ensure_ascii=False,
                indent=2,
                sort_keys=False,
            )
            + "\n",
            encoding="utf-8",
            newline="\n",
        )

        try:
            launcher = BenchLauncher(
                _launcher_argv(
                    launcher_config,
                    state_dir=state_dir,
                    token_file=token_file,
                    plugin_cache_dir=plugin_cache_dir,
                )
            )
        except (LauncherStartError, OSError) as exc:
            problems.append(_sanitize(f"launcher failed to start: {exc}", temp_root))
            return row

        try:
            completed = subprocess.run(
                _stub_argv(launcher, request_path=resolved_request_path, token_file=token_file, stub_config=stub_config),
                cwd=str(ROOT),
                env=_env(),
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=CASE_TIMEOUT_S,
            )
        except subprocess.TimeoutExpired:
            problems.append(f"stub connector did not finish within {CASE_TIMEOUT_S}s")
            return row

        row["exit_code"] = completed.returncode
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        try:
            summary = json.loads(stdout)
        except json.JSONDecodeError:
            summary = None
        if not isinstance(summary, dict):
            problems.append("stub stdout is not a single JSON document")
            if stderr.strip():
                problems.append("stub stderr: " + _sanitize(stderr, temp_root))
            return row

        expected_exit = expected.get("exit_code")
        if completed.returncode != expected_exit:
            problems.append(f"stub exit code is {completed.returncode}, expected {expected_exit}")
        if summary.get("schema") != STUB_SCHEMA:
            problems.append(f"stub summary schema is not {STUB_SCHEMA!r}")
        if summary.get("exit_code") != completed.returncode:
            problems.append(
                f"stub summary exit_code {summary.get('exit_code')!r} != process exit code {completed.returncode}"
            )

        for key in ("start_http_status", "final_status", "event_count", "cancel_sent", "concurrent_start_http_status"):
            row[key] = summary.get(key)
        result = summary.get("result")
        if isinstance(result, dict):
            row["result_status"] = result.get("status")
        elif result is not None:
            problems.append("stub summary 'result' is neither an object nor null")

        expected_http_status = expected.get("http_status")
        if not _matches(summary.get("start_http_status"), expected_http_status):
            problems.append(
                f"start_http_status is {summary.get('start_http_status')!r}, expected {expected_http_status!r}"
            )
        expected_final_status = expected.get("final_status")
        if not _matches(summary.get("final_status"), expected_final_status):
            problems.append(f"final_status is {summary.get('final_status')!r}, expected {expected_final_status!r}")
        event_count_min = int(expected.get("event_count_min") or 0)
        event_count = summary.get("event_count")
        if not isinstance(event_count, int):
            problems.append("stub summary has no integer event_count")
        elif event_count < event_count_min:
            problems.append(f"event_count is {event_count}, expected at least {event_count_min}")
        if not isinstance(result, dict):
            if expected_final_status is not None:
                problems.append("a terminal task must return a result object")
        else:
            if result.get("status") != expected_final_status:
                problems.append(
                    f"result.status is {result.get('status')!r}, expected {expected_final_status!r}"
                )
            if result.get("schema") != RESULT_SCHEMA:
                problems.append(f"result.schema is not {RESULT_SCHEMA!r}")
            if not result.get("real_eda") == "NOT RUN":
                problems.append("result.real_eda is not 'NOT RUN'")
        if expected_final_status is None and result is not None:
            problems.append("a rejected start must not return a result object")
        if expected_final_status is not None:
            if summary.get("error") is not None:
                problems.append("a completed task summary must have error=null")
        elif not isinstance(summary.get("error"), dict) or not summary["error"].get("code"):
            problems.append("a rejected start must carry error.code")

        if isinstance(event_count, int) and event_count > 1 and summary.get("event_seq_monotonic") is not True:
            problems.append("event sequence numbers are not strictly increasing")
        if summary.get("real_eda") != "NOT RUN" or summary.get("eda_calls") != 0:
            problems.append("stub summary honesty fields are wrong (real_eda/eda_calls)")
        if summary.get("project_writes") != 0:
            problems.append("stub summary reports project_writes != 0")

        for check in expected.get("checks") or []:
            if not isinstance(check, dict) or "path" not in check or "equals" not in check:
                problems.append(f"invalid expected check: {check!r}")
                continue
            path = str(check["path"])
            try:
                actual = _lookup(summary, path)
            except KeyError:
                problems.append(f"summary has no field {path!r}")
                continue
            if not _matches(actual, check["equals"]):
                problems.append(f"check {path} is {actual!r}, expected {check['equals']!r}")

        task_id = summary.get("task_id")
        workspace_checks = expected.get("workspace_checks") or []
        if expected_http_status == 202:
            if not isinstance(task_id, str) or not task_id:
                problems.append("an accepted task summary must carry task_id")
            else:
                workspace = state_dir / "tasks" / task_id
                if not workspace.is_dir():
                    problems.append("launcher task workspace is missing")
                else:
                    evidence_events = _read_events(workspace / "events.jsonl")
                    if not evidence_events:
                        problems.append("launcher evidence events.jsonl is missing or empty")
                    else:
                        evidence_count = len(evidence_events)
                        if isinstance(event_count, int) and event_count != evidence_count:
                            problems.append(
                                f"stub event_count {event_count} != launcher evidence event count {evidence_count}"
                            )
                        seqs = [event.get("seq") for event in evidence_events]
                        if seqs != list(range(1, evidence_count + 1)):
                            problems.append("launcher evidence seq numbers are not contiguous 1..N")
                        if isinstance(result, dict) and result.get("event_count") != evidence_count:
                            problems.append(
                                f"result.event_count {result.get('event_count')!r} "
                                f"!= launcher evidence event count {evidence_count}"
                            )
                    if workspace_checks:
                        problems.extend(
                            _workspace_problems(
                                workspace,
                                workspace_checks,
                                temp_root=temp_root,
                                token=TOKEN,
                                result=result,
                            )
                        )
        elif workspace_checks:
            problems.append("workspace checks are only valid for accepted tasks")

        return row
    except Exception as exc:  # pragma: no cover - defensive: one case must not kill the run
        problems.append(_sanitize(f"benchmark runner error: {type(exc).__name__}: {exc}", temp_root))
        return row
    finally:
        if launcher is not None:
            launcher.close()
        row["problems"] = problems
        row["passed"] = not problems
        row["duration_ms"] = int(round((time.perf_counter() - case_started) * 1000))


# ---------------------------------------------------------------------------
# results document
# ---------------------------------------------------------------------------


def _real_claude_document(requested: bool) -> dict:
    if not requested:
        return {
            "status": "NOT RUN",
            "requested": False,
            "reason": "not requested; the frozen benchmark only uses the bundled fake agent",
            "cases": [],
        }
    return {
        "status": "NOT RUN",
        "requested": True,
        "reason": (
            "--real-claude was given, but this offline benchmark never launches a real model: no claude "
            "executable is probed and no network call is made, so the real-Claude cases are NOT RUN and "
            "only the simulated cases were executed (they must still all pass for exit code 0)"
        ),
        "cases": [
            {
                "id": "real-claude-read-only",
                "status": "NOT RUN",
                "reason": "real Claude Code execution is OPTIONAL and out of scope for this frozen offline benchmark",
            }
        ],
    }


def build_results(
    rows: list[dict],
    *,
    elapsed_ms: int,
    real_claude_requested: bool,
) -> dict:
    passed = sum(1 for row in rows if row["passed"])
    return {
        "schema": BENCHMARK_SCHEMA,
        "benchmark": "task-launcher",
        "simulated": True,
        "offline": True,
        "real_eda": "NOT RUN",
        "eda_calls": 0,
        "project_writes": 0,
        "network_calls": 0,
        "hardware_test": "NOT RUN",
        "agent": "fake",
        "launcher_version": LAUNCHER_VERSION,
        "skill_version": SKILL_VERSION,
        "plugin_version": PLUGIN_VERSION,
        "limits": {
            "case_timeout_s": CASE_TIMEOUT_S,
            "launcher_start_timeout_s": LAUNCHER_START_TIMEOUT_S,
            "stub_poll_interval_s": DEFAULT_POLL_INTERVAL_S,
            "stub_timeout_s": DEFAULT_STUB_TIMEOUT_S,
            "timeout_request_s": 10,
            "max_concurrent_tasks": 1,
            "max_events": 10000,
            "plugin_cache": "one shared per-run cache keyed by the Skill fingerprint",
        },
        "cases": rows,
        "totals": {"passed": passed, "total": len(rows)},
        "elapsed_ms": elapsed_ms,
        "real_claude": _real_claude_document(real_claude_requested),
        "not_run": list(NOT_RUN),
        "not_proof": list(NOT_PROOF),
    }


def _write_results(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python benchmarks/task-launcher/run_benchmark.py",
        description="Frozen offline benchmark for the EasyCirq B1 task launcher (fake agent + stub connector).",
    )
    parser.add_argument(
        "--real-claude",
        action="store_true",
        help="mark the real-Claude cases NOT RUN (never launches a real model; simulated cases still run)",
    )
    parser.add_argument("--cases", default=str(DEFAULT_CASES_DIR), help="case directory (default: benchmarks/task-launcher/cases)")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="results.json output path")
    parser.add_argument("--keep-workdir", action="store_true", help=argparse.SUPPRESS)
    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", newline="\n")
        except (AttributeError, ValueError):  # pragma: no cover
            pass
    args = build_parser().parse_args(argv)
    cases_dir = Path(args.cases)
    output_path = Path(args.output)
    if not cases_dir.is_dir():
        sys.stderr.write(f"benchmark: case directory not found: {cases_dir}\n")
        return 2
    case_dirs = sorted(path for path in cases_dir.iterdir() if path.is_dir())
    if not case_dirs:
        sys.stderr.write(f"benchmark: no case directories under {cases_dir}\n")
        return 2

    run_started = time.perf_counter()
    temp_root = Path(tempfile.mkdtemp(prefix="easycirq-task-launcher-benchmark-"))
    plugin_cache_dir = temp_root / "plugin-cache"
    plugin_cache_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    try:
        for case_dir in case_dirs:
            expected_path = case_dir / "expected.json"
            request_path = case_dir / "request.json"
            if not expected_path.is_file() or not request_path.is_file():
                row = _new_row(case_dir.name, "")
                row["problems"] = ["case directory must contain request.json and expected.json"]
                row["passed"] = False
                rows.append(row)
                print(f"[FAIL] {case_dir.name}: missing request.json/expected.json")
                continue
            row = run_case(case_dir, expected_path, temp_root=temp_root, plugin_cache_dir=plugin_cache_dir)
            rows.append(row)
            status = "PASS" if row["passed"] else "FAIL"
            print(
                f"[{status}] {row['id']} ({row['duration_ms']} ms, exit={row['exit_code']}, "
                f"http={row['start_http_status']}, final={row['final_status']})"
            )
            for problem in row["problems"]:
                print(f"       - {problem}")
    finally:
        elapsed_ms = int(round((time.perf_counter() - run_started) * 1000))
        if not args.keep_workdir:
            shutil.rmtree(temp_root, ignore_errors=True)

    document = build_results(rows, elapsed_ms=elapsed_ms, real_claude_requested=bool(args.real_claude))
    _write_results(output_path, document)
    totals = document["totals"]
    print(
        f"\ntotals: {totals['passed']}/{totals['total']} passed in {elapsed_ms} ms; "
        f"simulated=true real_eda=NOT RUN eda_calls=0 agent=fake"
    )
    print(f"real_claude: {document['real_claude']['status']}")
    print(f"results: {output_path}")
    if totals["total"] == 0 or totals["passed"] != totals["total"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
