"""Hardened Claude Code launch planning (argv / task artifacts).

This module never touches B1 internals. It generates the per-task artifacts that
the B1 launcher (or the eventual B1-integrated runner) needs:

* ``request.json``      — sanitized copy of the task request;
* ``routing.md``        — hard routing text (Skill first, read-only, tool order);
* ``mcp.json``          — mounts this supervisor as the only MCP server;
* ``settings.json``     — deny/allow lists + optional hooks;
* ``agent.command.json``— argv + env whitelist, **never** a secret;
* ``bound.config.json`` — task id, versions, limits, token SHA-256, backend;
* ``task.token``        — random token (file permission 0600 best effort).

The real Claude Code spawn is implemented but deliberately **NOT RUN** in this
delivery: B1 is not delivered, so no plugin exists to mount. ``plan`` still
proves the argv/settings/mcp wiring offline; tests assert it.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from . import (
    ALLOWED_AGENT_TOOLS,
    AUDIT_ENGINE_FIXTURE,
    BACKEND_FIXTURE,
    COMMAND_FILE,
    CONFIG_FILE,
    DEFAULT_TIMEOUT_S,
    DENIED_AGENT_TOOLS,
    MCP_FILE,
    REQUEST_SCHEMA,
    REQUEST_FILE,
    ROUTING_FILE,
    SETTINGS_FILE,
    SKILL_NAME,
    SUPPORTED_AUDIT_ENGINES,
    SUPPORTED_BACKENDS,
    TOKEN_FILE,
    __version__,
)
from .backends import default_fixture_dir
from .b1 import probe_b1
from .config import (
    BoundConfig,
    Limits,
    Versions,
    generate_token,
    hash_token,
    task_dir_for,
    write_token_file,
)
from .errors import INVALID_REQUEST, BoundError
from .receipts import canonical_json
from .schema import parse_json_strict, validate
from .settings import build_settings, write_settings

#: Schema of a bound task request (launcher -> runner). ``mode`` is read-only in
#: Phase 1; Phase 2 writes are refused here as well.
REQUEST_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["schema", "task_id", "client", "goal", "context"],
    "properties": {
        "schema": {"type": "string", "const": REQUEST_SCHEMA},
        "task_id": {"type": "string", "pattern": r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}"},
        "mode": {"type": "string", "enum": ["read_only"]},
        "client": {
            "type": "object",
            "additionalProperties": False,
            "required": ["name", "version"],
            "properties": {
                "name": {"type": "string", "minLength": 1, "maxLength": 64},
                "version": {"type": "string", "minLength": 1, "maxLength": 64},
            },
        },
        "goal": {
            "type": "object",
            "additionalProperties": False,
            "required": ["user_prompt"],
            "properties": {
                "user_prompt": {"type": "string", "minLength": 1, "maxLength": 4000},
                "intent": {"type": "string", "enum": ["inspect", "review", "audit", "explain"]},
            },
        },
        "context": {
            "type": "object",
            "additionalProperties": False,
            "required": ["project", "document"],
            "properties": {
                "project": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["name"],
                    "properties": {
                        "name": {"type": "string", "minLength": 1, "maxLength": 128},
                        "revision": {"type": "string", "minLength": 1, "maxLength": 64},
                    },
                },
                "document": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["kind", "id"],
                    "properties": {
                        "kind": {"type": "string", "enum": ["schematic", "pcb", "panel", "bom"]},
                        "id": {"type": "string", "minLength": 1, "maxLength": 128},
                    },
                },
                "page": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {"name": {"type": "string", "minLength": 1, "maxLength": 128}},
                },
                "selection": {
                    "type": "array",
                    "maxItems": 256,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["kind", "designator"],
                        "properties": {
                            "kind": {"type": "string", "minLength": 1, "maxLength": 32},
                            "designator": {"type": "string", "minLength": 1, "maxLength": 64},
                        },
                    },
                },
                "snapshot_sha256": {"type": ["string", "null"], "pattern": r"[0-9a-f]{64}"},
                "missing_fields": {
                    "type": "array",
                    "maxItems": 64,
                    "items": {"type": "string", "minLength": 1, "maxLength": 64},
                },
            },
        },
        "limits": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "timeout_s": {"type": "integer", "minimum": 10, "maximum": 1800},
                "max_steps": {"type": "integer", "minimum": 1, "maximum": 1000},
                "max_tool_calls": {"type": "integer", "minimum": 1, "maximum": 1000},
            },
        },
    },
}

#: Flags that must be present in every hardened agent argv.
REQUIRED_AGENT_FLAGS = (
    "-p",
    "--mcp-config",
    "--append-system-prompt-file",
    "--settings",
    "--output-format",
    "--plugin-dir",
    "--allowedTools",
    "--disallowedTools",
)

#: Flags that would weaken the capability surface; never emitted.
FORBIDDEN_AGENT_FLAGS = (
    "--dangerously-skip-permissions",
    "--permission-mode bypassPermissions",
    "--allow-dangerously-skip-permissions",
)

#: Environment variables forwarded to the headless agent (allow-list).
AGENT_ENV_WHITELIST = (
    "PATH",
    "PATHEXT",
    "SYSTEMROOT",
    "SYSTEMDRIVE",
    "WINDIR",
    "TEMP",
    "TMP",
    "HOME",
    "USERPROFILE",
    "LANG",
    "LC_ALL",
    "PYTHONIOENCODING",
)


def load_request(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise BoundError(INVALID_REQUEST, f"request file not found: {path}", {"path": str(path)}) from exc
    request = parse_json_strict(text, source=str(path))
    try:
        validate(REQUEST_JSON_SCHEMA, request, "request")
    except BoundError as exc:
        raise BoundError(INVALID_REQUEST, exc.message, exc.detail) from exc
    context = request["context"]
    if context.get("snapshot_sha256") is None and not context.get("missing_fields"):
        raise BoundError(
            INVALID_REQUEST,
            "a null snapshot_sha256 must be declared in context.missing_fields",
            {"missing_fields": context.get("missing_fields") or []},
        )
    return request


def detect_skill_version(skill_dir: Path | None) -> str:
    if skill_dir is not None:
        version_file = Path(skill_dir) / ".version"
        try:
            return version_file.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise BoundError(
                "VERSION_MISMATCH",
                f"cannot read Skill version from {version_file}",
                {"path": str(version_file), "reason": str(exc)},
                status=409,
            ) from exc
    return "unknown"


def build_routing_text(
    request: dict[str, Any],
    *,
    task_id: str,
    phase: int = 1,
    versions: dict[str, Any] | None = None,
) -> str:
    goal = request.get("goal") or {}
    context = request.get("context") or {}
    project = (context.get("project") or {}).get("name", "?")
    document = (context.get("document") or {})
    handshake = ""
    if versions:
        handshake = (
            "- 版本握手（`task_start` 必须原样提交，不得改版本）："
            f"skill=`{versions.get('skill')}` plugin=`{versions.get('plugin')}` "
            f"server=`{versions.get('server')}` backend=`{versions.get('backend')}`\n"
        )
    lines = [
        "# 受控任务路由（B1-Bound，由 supervisor 生成）",
        "",
        f"- 任务：`{task_id}`；工程：`{project}`；文档：`{document.get('kind')}:{document.get('id')}`",
        f"- 用户目标：{goal.get('user_prompt', '')}",
        handshake,
        "",
        "## 硬规则（不可跳过）",
        "",
        f"1. 本任务由受控启动器启动；**必须先加载 `{SKILL_NAME}` Skill**，不得跳过。",
        "2. 只读任务：不得修改/保存/导出 EDA 工程，不得调用任何写接口；本任务没有 "
        "Bash/Write/Edit/Agent/Task/WebFetch/WebSearch 工具。",
        "3. 只通过 `mcp__zhigou_bound__*` 工具推进流程，顺序固定："
        "`task_start → snapshot_read → run_offline_audit → evidence_emit → finalize`。"
        "跳步、乱序、重复都会被 supervisor 以稳定错误码拒绝。",
        "4. 快照由 supervisor 读取，你不能提供快照内容、回执或报告；额外字段会被拒绝。",
        "5. 未知/缺测必须如实报告，**不得用默认值或猜测补全**；"
        "`pass_with_scope` 不是整板通过。",
        "6. 结论必须区分：离线检查 / 真实 EDA / 硬件实测；本阶段 `real_eda = NOT RUN`。",
        "7. 结束时必须调用 `finalize`，最终报告由 supervisor 生成；"
        "你不得自己编写/伪造报告，也不得声称 supervisor 未返回的结论。",
        "8. 如任务无法完成，调用 `task_abort` 说明原因；取消的任务不会得到成功报告。",
        "",
        f"## 工具面（Phase {phase}，只读）",
        "",
        "- `task_start`、`snapshot_read`、`run_offline_audit`、`evidence_emit`、`finalize`、`task_abort`",
        "- 不存在写工具；`apply/readback` 等 Phase 2 工具在本次交付中未启用。",
        "",
        "## 结束时的输出",
        "",
        "- 读了哪些资料、跑了哪些工具、supervisor 返回的 verdict/证据哈希、未知项、未运行项；",
        "- 引用 supervisor 报告，不要自行改写 verdict。",
        "",
    ]
    return "\n".join(lines)


def build_mcp_config(
    *,
    config_path: Path,
    token_file: Path,
    repo_root: Path,
    python_executable: str | None = None,
) -> dict[str, Any]:
    """Only this supervisor is mounted; secrets are *file paths*, never values."""

    python = python_executable or sys.executable
    return {
        "mcpServers": {
            # Underscore keeps the tool prefix stable: mcp__zhigou_bound__<tool>,
            # matching the allow-list entry "mcp__zhigou_bound__*".
            "zhigou_bound": {
                "type": "stdio",
                "command": python,
                "args": [
                    "-m",
                    "task_launcher.bound",
                    "serve",
                    "--config",
                    str(config_path),
                    "--token-file",
                    str(token_file),
                ],
                "env": {
                    "PYTHONPATH": str(repo_root),
                    "PYTHONIOENCODING": "utf-8",
                },
            }
        }
    }


def build_agent_argv(
    *,
    claude_exe: str,
    prompt: str,
    mcp_config: Path,
    routing_file: Path,
    settings_file: Path,
    plugin_dir: Path,
) -> list[str]:
    return [
        claude_exe,
        "-p",
        prompt,
        "--mcp-config",
        str(mcp_config),
        "--plugin-dir",
        str(plugin_dir),
        "--append-system-prompt-file",
        str(routing_file),
        "--settings",
        str(settings_file),
        "--output-format",
        "stream-json",
        "--verbose",
        "--allowedTools",
        ",".join(ALLOWED_AGENT_TOOLS),
        "--disallowedTools",
        ",".join(DENIED_AGENT_TOOLS),
    ]


def validate_agent_argv(argv: list[str]) -> list[str]:
    problems: list[str] = []
    text = "\n".join(argv)
    for flag in REQUIRED_AGENT_FLAGS:
        if flag not in argv:
            problems.append(f"missing required flag {flag}")
    for forbidden in FORBIDDEN_AGENT_FLAGS:
        if forbidden in text:
            problems.append(f"forbidden flag present: {forbidden}")
    if "-p" in argv:
        prompt_index = argv.index("-p") + 1
        if prompt_index >= len(argv) or not argv[prompt_index].strip():
            problems.append("-p must be followed by a non-empty prompt argument")
    return problems


def plan_task(
    request: dict[str, Any],
    *,
    task_dir: Path,
    skill_dir: Path | None = None,
    skill_version: str | None = None,
    plugin_version: str = "0.1.0",
    plugin_dir: Path | None = None,
    repo_root: Path | None = None,
    state_root: Path | None = None,
    backend: str = BACKEND_FIXTURE,
    audit_engine: str = AUDIT_ENGINE_FIXTURE,
    audit_case: str = "pass",
    hooks_enabled: bool = False,
    phase: int = 1,
    claude_exe: str = "claude",
    python_executable: str | None = None,
    b1_repo: Path | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Generate a complete per-task artifact bundle and return a JSON summary."""

    if backend not in SUPPORTED_BACKENDS:
        raise BoundError("BACKEND_UNAVAILABLE", f"unsupported backend {backend!r}", {"backend": backend})
    if audit_engine not in SUPPORTED_AUDIT_ENGINES:
        raise BoundError("BACKEND_UNAVAILABLE", f"unsupported audit engine {audit_engine!r}", {"audit_engine": audit_engine})
    if phase not in (1, 2):
        raise BoundError("PHASE_NOT_ENABLED", f"unsupported phase {phase!r}", {"phase": phase})
    task_dir = Path(task_dir).expanduser()
    if plugin_dir is not None and not Path(plugin_dir).expanduser().is_dir():
        raise BoundError(
            "INVALID_CONFIG",
            f"--plugin-dir is not a directory: {plugin_dir}",
            {"plugin_dir": str(plugin_dir)},
        )
    if task_dir.exists() and any(task_dir.iterdir()) and not force:
        raise BoundError(
            "INVALID_CONFIG",
            f"task directory is not empty: {task_dir} (use --force to clear)",
            {"task_dir": str(task_dir)},
        )
    task_dir.mkdir(parents=True, exist_ok=True)
    if force and task_dir.exists():
        for child in task_dir.iterdir():
            if child.is_dir():
                import shutil as _shutil

                _shutil.rmtree(child)
            else:
                child.unlink()
    request_path = task_dir / REQUEST_FILE
    request_path.write_text(
        json.dumps(request, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    resolved_skill_version = skill_version or detect_skill_version(skill_dir)
    token = generate_token()
    token_file = task_dir / TOKEN_FILE
    write_token_file(token_file, token)
    config_path = task_dir / CONFIG_FILE
    fixtures_dir = default_fixture_dir()
    b1_probe = probe_b1(b1_repo)
    config = BoundConfig(
        task_id=request["task_id"],
        task_dir=task_dir,
        token_sha256=hash_token(token),
        versions=Versions(
            skill=resolved_skill_version,
            plugin=plugin_version,
            server=__version__,
            backend=_backend_version(backend),
        ),
        state_root=state_root,
        phase=phase,
        backend=backend,
        audit_engine=audit_engine,
        audit_case=audit_case,
        eda_authorized=False,
        limits=Limits.from_dict(request.get("limits") or {}),
        plugin_dir=Path(plugin_dir).expanduser() if plugin_dir else None,
        repo_root=Path(repo_root).expanduser() if repo_root else Path(__file__).resolve().parents[2],
        fixture_dir=fixtures_dir,
        b1={
            "available": b1_probe.available,
            "delivered": b1_probe.delivered,
            "note": "BLOCKED ON B1" if not b1_probe.delivered else "B1 delivery markers found",
        },
    )
    # Round-trip through the strict loader so plan-time and serve-time
    # validation cannot drift (paths, versions, limits, b1 fields).
    config = BoundConfig.from_dict(config.to_dict())
    config.write(config_path)
    routing_path = task_dir / ROUTING_FILE
    routing_path.write_text(
        build_routing_text(
            request,
            task_id=request["task_id"],
            phase=phase,
            versions=config.versions.to_dict(),
        ),
        encoding="utf-8",
        newline="\n",
    )
    mcp_config = build_mcp_config(
        config_path=config_path,
        token_file=token_file,
        repo_root=config.repo_root or Path(__file__).resolve().parents[2],
        python_executable=python_executable,
    )
    (task_dir / MCP_FILE).write_text(
        json.dumps(mcp_config, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    settings = build_settings(task_dir, hooks_enabled=hooks_enabled)
    write_settings(task_dir / SETTINGS_FILE, settings)
    resolved_claude = shutil.which(claude_exe) or ""
    agent_ready = bool(plugin_dir) and bool(resolved_claude)
    command: dict[str, Any] = {
        "schema": "zhigou.bound.agent-command/v1",
        "claude_exe": resolved_claude or claude_exe,
        "cwd": str(task_dir),
        "env_whitelist": list(AGENT_ENV_WHITELIST),
        "argv": [],
        "agent_ready": agent_ready,
        "not_run": [] if agent_ready else ["real Claude Code spawn is NOT RUN in this delivery"],
        "notes": [
            "argv is always passed as an argument list; never a shell string",
            "no token/key is present in argv, env whitelist or settings",
        ],
    }
    if plugin_dir:
        command["argv"] = build_agent_argv(
            claude_exe=resolved_claude or claude_exe,
            prompt=request["goal"]["user_prompt"],
            mcp_config=task_dir / MCP_FILE,
            routing_file=routing_path,
            settings_file=task_dir / SETTINGS_FILE,
            plugin_dir=Path(plugin_dir).expanduser(),
        )
        problems = validate_agent_argv(command["argv"])
        if problems:
            raise BoundError("INVALID_CONFIG", "agent argv is invalid", {"problems": problems})
    else:
        command["not_run"].append(
            "no --plugin-dir: the design-hardware plugin requires a delivered B1 HEAD "
            "(BLOCKED ON B1), so no Claude Code process is started"
        )
    (task_dir / COMMAND_FILE).write_text(
        json.dumps(command, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    summary = {
        "ok": True,
        "schema": "zhigou.bound.plan/v1",
        "task_id": request["task_id"],
        "task_dir": str(task_dir),
        "config_path": str(config_path),
        "token_file": str(token_file),
        "files": [
            REQUEST_FILE,
            CONFIG_FILE,
            ROUTING_FILE,
            MCP_FILE,
            SETTINGS_FILE,
            COMMAND_FILE,
            TOKEN_FILE,
        ],
        "versions": config.versions.to_dict(),
        "limits": config.limits.to_dict(),
        "backend": backend,
        "audit_engine": audit_engine,
        "audit_case": audit_case,
        "phase": phase,
        "hooks_enabled": hooks_enabled,
        "agent_ready": agent_ready,
        "agent_argv": command["argv"],
        "agent_not_run": command["not_run"],
        "b1": config.b1,
        "real_eda": "NOT RUN",
        "eda_calls": 0,
        "wrote_repo": False,
        "notes": [
            "all artifacts are inside the task directory (state dir), never the repository",
            "the HMAC key is not generated here and is never written to disk",
        ],
    }
    return summary


def _backend_version(backend: str) -> str:
    if backend == BACKEND_FIXTURE:
        from .backends import default_fixture_dir

        try:
            document = json.loads((default_fixture_dir() / "snapshot.json").read_text(encoding="utf-8"))
            return str(document.get("fixture_version", "fixture-1"))
        except (OSError, json.JSONDecodeError):  # pragma: no cover - fixture always present
            return "fixture-1"
    return f"{backend}-unavailable"


# ---------------------------------------------------------------------------
# agent spawn (implemented, NOT RUN in this delivery)
# ---------------------------------------------------------------------------
def spawn_agent(
    *,
    argv: list[str],
    task_dir: Path,
    timeout_s: int = DEFAULT_TIMEOUT_S,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Spawn the headless agent with a hard timeout and process-tree kill.

    This path is exercised only when a caller explicitly asks for a real run
    (needs a delivered B1 plugin + user consent). Tests cover the argv builder
    and the kill helpers, not a real Claude run.
    """

    problems = validate_agent_argv(argv)
    if problems:
        raise BoundError("INVALID_CONFIG", "agent argv is invalid", {"problems": problems})
    child_env = build_agent_env(env)
    started = time.time()
    process = subprocess.Popen(
        argv,
        cwd=str(task_dir),
        env=child_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    events: list[dict[str, Any]] = []
    parse_errors: list[dict[str, Any]] = []
    timed_out = False
    try:
        assert process.stdout is not None
        deadline = started + float(timeout_s)
        for line in process.stdout:
            if time.time() > deadline:
                timed_out = True
                break
            stripped = line.strip()
            if not stripped:
                continue
            parsed = parse_stream_line(stripped)
            if parsed.get("parse_error"):
                parse_errors.append(parsed)
                events.append(parsed)
            else:
                events.append(parsed)
        if timed_out:
            kill_tree(process)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            kill_tree(process)
        stderr_text = process.stderr.read() if process.stderr is not None else ""
    finally:
        if process.poll() is None:
            kill_tree(process)
    return {
        "agent": "claude-code",
        "agent_version": None,
        "timed_out": timed_out,
        "exit_code": process.returncode,
        "elapsed_s": round(time.time() - started, 3),
        "events_count": len(events),
        "parse_errors": len(parse_errors),
        "stderr_tail": stderr_text[-2000:],
        "real_eda": "NOT RUN",
        "eda_calls": 0,
        "project_writes": 0,
        "model_used": "unknown",
    }


def build_agent_env(overrides: dict[str, str] | None = None) -> dict[str, str]:
    env = {name: os.environ[name] for name in AGENT_ENV_WHITELIST if name in os.environ}
    if overrides:
        for key, value in overrides.items():
            if key in ("ZHIGOU_BOUND_TOKEN", "ZHIGOU_BOUND_HMAC_KEY"):
                continue
            env[key] = value
    return env


def kill_tree(process: subprocess.Popen) -> dict[str, Any]:
    """Kill the agent and its descendants (no orphan processes)."""

    result: dict[str, Any] = {"killed": False, "method": None}
    if process.poll() is not None:
        return result
    try:
        if os.name == "nt":  # pragma: no cover - platform dependent
            completed = subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                text=True,
                check=False,
            )
            result.update({"killed": True, "method": "taskkill", "exit": completed.returncode})
        else:
            import signal

            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            result.update({"killed": True, "method": "killpg"})
    except Exception as exc:  # pragma: no cover - defensive
        result.update({"killed": False, "method": "failed", "error": str(exc)})
        try:
            process.kill()
            result["killed"] = True
            result["method"] = "process.kill"
        except Exception:
            pass
    return result


def parse_stream_line(line: str) -> dict[str, Any]:
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        return {"parse_error": True, "raw": line[:500]}
    if not isinstance(event, dict):
        return {"parse_error": True, "raw": str(event)[:500]}
    event.setdefault("type", "unknown")
    return event
