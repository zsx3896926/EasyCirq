"""Controlled agent start-up: fixed argv, stream-json parsing, tree kill.

Two rules make this module the security boundary of the PoC:

1. **No shell.**  The command is an argument list handed to ``Popen``.  The
   user prompt is one argument, never interpolated into a command string.
2. **No missing routing flags.**  ``--plugin-dir``,
   ``--append-system-prompt-file``, ``--mcp-config`` and ``--output-format`` are
   mandatory; a replacement command template that omits any of them is refused
   before a process is spawned.  This is what keeps the Skill/routing injection
   from silently degrading to "just a prompt".

The only agent executable used by tests and the frozen benchmark is the bundled
fake agent (``task_launcher.fake_agent``).  A real Claude Code executable is
optional: when it is missing, task start returns ``503 AGENT_UNAVAILABLE`` and
nothing is installed automatically.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import (
    AGENT_PROFILE_CLAUDE,
    AGENT_PROFILE_FAKE,
    ALLOWED_TOOLS_ARG,
    FAKE_AGENT_VERSION,
    PERMISSION_MODE,
)
from .protocol import LauncherError

#: Flags that MUST be present in every agent command (hard routing mechanism).
REQUIRED_AGENT_FLAGS = (
    "--plugin-dir",
    "--append-system-prompt-file",
    "--mcp-config",
    "--output-format",
)

#: Environment variables inherited by the agent.  Everything else is dropped so
#: no launcher credential (token) can leak into the child process.
ENV_WHITELIST = (
    "PATH",
    "PATHEXT",
    "SYSTEMROOT",
    "SYSTEMDRIVE",
    "WINDIR",
    "COMSPEC",
    "TEMP",
    "TMP",
    "HOME",
    "USERPROFILE",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "TZ",
    "PYTHONIOENCODING",
    "PYTHONUTF8",
)

#: Placeholders understood by ``--agent-argv-template``.
TEMPLATE_PLACEHOLDERS = (
    "{exe}",
    "{python}",
    "{user_prompt}",
    "{plugin_dir}",
    "{routing_file}",
    "{mcp_config}",
    "{task_dir}",
    "{task_id}",
    "{scenario}",
    "{allowed_tools}",
    "{permission_mode}",
)

MAX_AGENT_VERSION_TIMEOUT_S = 10


@dataclass(frozen=True)
class AgentProfileInfo:
    """Resolved agent executable and honesty fields."""

    kind: str
    executable: str
    version: str | None
    available: bool
    reason: str | None = None

    def to_dict(self) -> dict:
        return {
            "profile": self.kind,
            "executable": self.executable,
            "version": self.version,
            "available": self.available,
            "reason": self.reason,
        }


def _probe_version(executable: str) -> str | None:
    try:
        completed = subprocess.run(
            [executable, "--version"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=MAX_AGENT_VERSION_TIMEOUT_S,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    text = (completed.stdout or completed.stderr or "").strip()
    if not text:
        return None
    # "2.1.303 (Claude Code)" -> "2.1.303"
    first = text.splitlines()[0].strip()
    token = first.split(" ")[0].strip()
    return token or first[:64]


def resolve_agent(profile: str, claude_exe: str | None) -> AgentProfileInfo:
    """Resolve the agent executable or return an unavailable profile."""

    if profile == AGENT_PROFILE_FAKE:
        executable = sys.executable or "python"
        if not executable or (not Path(executable).exists() and shutil.which(executable) is None):
            return AgentProfileInfo(profile, executable or "python", FAKE_AGENT_VERSION, False, "python_missing")
        return AgentProfileInfo(profile, executable, FAKE_AGENT_VERSION, True)

    if profile == AGENT_PROFILE_CLAUDE:
        requested = claude_exe or "claude"
        candidate = requested
        if not Path(candidate).is_file():
            resolved = shutil.which(candidate)
            if resolved:
                candidate = resolved
        if not Path(candidate).is_file():
            return AgentProfileInfo(profile, requested, None, False, "claude_executable_not_found")
        return AgentProfileInfo(profile, candidate, _probe_version(candidate), True)

    return AgentProfileInfo(profile, "", None, False, "unknown_agent_profile")


def require_agent(profile_info: AgentProfileInfo) -> AgentProfileInfo:
    """Raise ``503 AGENT_UNAVAILABLE`` when the resolved profile is not runnable."""

    if profile_info.available:
        return profile_info
    raise LauncherError(
        "AGENT_UNAVAILABLE",
        "the configured agent executable is not available; nothing was installed",
        {
            "profile": profile_info.kind,
            "executable": profile_info.executable,
            "reason": profile_info.reason,
            "hint": "安装 Claude Code 或使用 --agent-profile fake（测试用）；启动器不会自动安装",
        },
    )


def load_argv_template(path: Path) -> list[str]:
    """Load a replacement agent argv template (JSON ``{"argv": [...]}``)."""

    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LauncherError(
            "AGENT_COMMAND_INVALID",
            "agent command template cannot be read",
            {"path": str(path), "reason": str(exc)},
        ) from None
    argv = document.get("argv") if isinstance(document, dict) else None
    if not isinstance(argv, list) or not argv or not all(isinstance(item, str) for item in argv):
        raise LauncherError(
            "AGENT_COMMAND_INVALID",
            "agent command template must be a JSON object with a non-empty string array 'argv'",
            {"path": str(path)},
        )
    return list(argv)


def _substitute(template: list[str], values: dict[str, str]) -> list[str]:
    argv = []
    for item in template:
        rendered = item
        for placeholder, value in values.items():
            rendered = rendered.replace(placeholder, value)
        argv.append(rendered)
    return argv


def validate_agent_argv(argv: list[str]) -> None:
    """Refuse a command that drops any mandatory routing flag."""

    missing = []
    for flag in REQUIRED_AGENT_FLAGS:
        if flag not in argv:
            missing.append(flag)
            continue
        index = argv.index(flag)
        if index + 1 >= len(argv) or argv[index + 1].startswith("--"):
            missing.append(flag)
    if missing:
        raise LauncherError(
            "AGENT_COMMAND_INVALID",
            "agent command is missing mandatory routing flags; refusing to start",
            {"missing_flags": missing, "required_flags": list(REQUIRED_AGENT_FLAGS)},
        )


def build_agent_argv(
    request: dict,
    *,
    profile: str,
    executable: str,
    plugin_dir: Path,
    routing_file: Path,
    mcp_file: Path,
    task_dir: Path,
    scenario: str | None = None,
    template: list[str] | None = None,
    template_path: Path | None = None,
) -> list[str]:
    """Build the agent argv (list, never a shell string) and validate it."""

    prompt = request["goal"]["user_prompt"]
    task_id = request["task_id"]
    if template is not None:
        values = {
            "{exe}": executable,
            "{python}": sys.executable or "python",
            "{user_prompt}": prompt,
            "{plugin_dir}": str(plugin_dir),
            "{routing_file}": str(routing_file),
            "{mcp_config}": str(mcp_file),
            "{task_dir}": str(task_dir),
            "{task_id}": task_id,
            "{scenario}": scenario or "",
            "{allowed_tools}": ALLOWED_TOOLS_ARG,
            "{permission_mode}": PERMISSION_MODE,
        }
        argv = _substitute(template, values)
        validate_agent_argv(argv)
        return argv

    if profile == AGENT_PROFILE_FAKE:
        argv = [
            executable,
            "-m",
            "task_launcher.fake_agent",
            "-p",
            prompt,
            "--plugin-dir",
            str(plugin_dir),
            "--append-system-prompt-file",
            str(routing_file),
            "--mcp-config",
            str(mcp_file),
            "--output-format",
            "stream-json",
            "--verbose",
            "--permission-mode",
            PERMISSION_MODE,
            "--allowedTools",
            ALLOWED_TOOLS_ARG,
            "--add-dir",
            str(task_dir),
            "--scenario",
            scenario or "stream",
        ]
    else:
        argv = [
            executable,
            "-p",
            prompt,
            "--plugin-dir",
            str(plugin_dir),
            "--append-system-prompt-file",
            str(routing_file),
            "--mcp-config",
            str(mcp_file),
            "--output-format",
            "stream-json",
            "--verbose",
            "--permission-mode",
            PERMISSION_MODE,
            "--allowedTools",
            ALLOWED_TOOLS_ARG,
            "--add-dir",
            str(task_dir),
        ]
    validate_agent_argv(argv)
    return argv


def build_agent_env(
    base_env: dict[str, str],
    *,
    task_id: str,
    mode: str,
    scenario: str | None,
    state_dir: Path,
    package_root: Path,
    skill_name: str = "easycirq",
) -> dict[str, str]:
    """Return the whitelisted child environment (never contains the token)."""

    env: dict[str, str] = {}
    for name in ENV_WHITELIST:
        if name in base_env and base_env[name]:
            env[name] = base_env[name]
    env["PYTHONPATH"] = str(package_root)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env["ZHIGOU_TASK_ID"] = task_id
    env["ZHIGOU_MODE"] = mode
    env["ZHIGOU_STATE_DIR"] = str(state_dir)
    env["ZHIGOU_SKILL_NAME"] = skill_name
    if scenario:
        env["ZHIGOU_FAKE_SCENARIO"] = scenario
    return env


def spawn_agent(argv: list[str], *, cwd: Path, env: dict[str, str]) -> subprocess.Popen:
    """Spawn the agent with piped stdout/stderr and no stdin."""

    kwargs: dict[str, Any] = {
        "cwd": str(cwd),
        "env": env,
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "bufsize": 1,
    }
    if os.name == "nt":  # pragma: no cover - exercised on Windows CI/dev
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(argv, **kwargs)


def kill_tree(process: subprocess.Popen) -> dict:
    """Terminate the whole process tree (no orphan agents left behind)."""

    if process.poll() is not None:
        return {"killed": False, "already_exited": True, "method": "none"}
    pid = process.pid
    if os.name == "nt":  # pragma: no cover - exercised on Windows CI/dev
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=30,
            )
            method = "taskkill"
        except (OSError, subprocess.SubprocessError):
            method = "terminate"
            process.terminate()
    else:
        try:
            os.killpg(os.getpgid(pid), 9)
            method = "killpg"
        except (ProcessLookupError, PermissionError):
            method = "terminate"
            try:
                process.terminate()
            except OSError:
                pass
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:  # pragma: no cover - defensive
        try:
            process.kill()
        except OSError:
            pass
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            pass
    return {"killed": True, "already_exited": False, "method": method, "pid": pid}


def parse_stream_line(line: str) -> dict:
    """Parse one stdout line from the agent.

    Returns ``{"ok": True, "payload": {...}}`` for a JSON object, or
    ``{"ok": False, "error": "...", "raw": "..."}`` for a malformed line.  A
    malformed line is recorded as a ``parse_error`` event but never aborts the
    task: unknown event types must stay forward compatible.
    """

    text = line.strip()
    if not text:
        return {"ok": False, "error": "empty_line", "raw": ""}
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        return {"ok": False, "error": f"invalid_json: {exc.msg}", "raw": text[:2048]}
    if isinstance(payload, dict):
        return {"ok": True, "payload": payload}
    return {"ok": False, "error": f"json_{type(payload).__name__}_not_object", "raw": text[:2048]}
