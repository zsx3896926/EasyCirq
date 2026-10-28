"""Generation and validation of ``mcp.json`` for one task.

The task agent gets the already-merged offline-audit MCP server
(``easycirq/scripts/zhigou_mcp``; legacy checkouts use ``design-hardware/scripts``)
mounted explicitly with ``--mcp-config``.  It is a **stdio** child process started
by the agent, so the launcher only writes a configuration file; it never starts
the server itself and never talks to it.

The ``PYTHONPATH`` points at the Skill's ``scripts`` directory, which is where
``python -m zhigou_mcp`` is importable from.  It is resolved to a forward-slash
absolute path so the JSON is valid on Windows and the value is stable for the
same installation.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import sys

from . import (
    BOUND_MODULE,
    BOUND_SERVER_NAME,
    BOUND_SERVE_ARGS,
    MCP_MODULE,
    MCP_MODULE_CANDIDATES,
    MCP_SERVER_NAME,
)
from .protocol import LauncherError


def _posix(path: Path) -> str:
    return path.resolve().as_posix()


def detect_mcp_module(skill_scripts_dir: Path) -> str:
    """Return the offline-audit module that exists in this Skill checkout.

    The 2026-10 rebrand renamed ``zhigou_mcp`` to ``easycirq_mcp``; both layouts
    must work, and a missing module must never be written into mcp.json.
    """

    root = Path(skill_scripts_dir)
    for candidate in MCP_MODULE_CANDIDATES:
        if (root / candidate).is_dir():
            return candidate
    return MCP_MODULE


def _bound_entry(bound: dict) -> dict:
    command = bound.get("command") or sys.executable or "python"
    return {
        "command": command,
        "args": [
            *BOUND_SERVE_ARGS,
            "--config",
            str(bound["config_path"]),
            "--token-file",
            str(bound["token_file"]),
        ],
        "env": {
            "PYTHONPATH": _posix(Path(bound["repo_root"])),
            "PYTHONIOENCODING": "utf-8",
        },
    }


def build_mcp_config(skill_scripts_dir: Path, *, bound: dict | None = None) -> dict:
    """Return the ``.mcp.json`` document for a task.

    ``bound=None`` keeps the B1 PoC behaviour (offline-audit server only).
    With ``bound`` given, the task MCP surface is **replaced** by the trusted
    B1-Bound supervisor: the agent must not be able to call offline audit tools
    directly and bypass the signed receipt chain.
    """

    if bound is not None:
        return {"mcpServers": {BOUND_SERVER_NAME: _bound_entry(bound)}}
    return {
        "mcpServers": {
            MCP_SERVER_NAME: {
                "command": "python",
                "args": ["-m", detect_mcp_module(skill_scripts_dir)],
                "env": {"PYTHONPATH": _posix(skill_scripts_dir)},
            }
        }
    }


def write_mcp_config(
    path: Path, skill_scripts_dir: Path, *, bound: dict | None = None
) -> dict:
    """Write ``mcp.json`` (LF, deterministic JSON) and return the document."""

    document = build_mcp_config(skill_scripts_dir, bound=bound)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")
    return document


def validate_mcp_config(document: Any) -> list[str]:
    """Return a list of structural problems (empty list means valid)."""

    problems: list[str] = []
    if not isinstance(document, dict):
        return ["mcp.json must be a JSON object"]
    servers = document.get("mcpServers")
    if not isinstance(servers, dict):
        return ["mcp.json must contain an object field 'mcpServers'"]
    offline = servers.get(MCP_SERVER_NAME)
    bound = servers.get(BOUND_SERVER_NAME)
    if offline is not None and bound is not None:
        problems.append("mcpServers must not mix the offline-audit and bound servers in one task")
        return problems
    if bound is not None:
        return _validate_bound_entry(bound)
    if not isinstance(offline, dict):
        problems.append(f"mcpServers.{MCP_SERVER_NAME} is missing")
        return problems
    command = offline.get("command")
    if not isinstance(command, str) or not command:
        problems.append(f"mcpServers.{MCP_SERVER_NAME}.command must be a non-empty string")
    args = offline.get("args")
    if not isinstance(args, list) or not all(isinstance(item, str) for item in args):
        problems.append(f"mcpServers.{MCP_SERVER_NAME}.args must be a list of strings")
    elif len(args) < 2 or args[0] != "-m" or args[1] not in MCP_MODULE_CANDIDATES:
        problems.append(
            f"mcpServers.{MCP_SERVER_NAME}.args must start with ['-m', one of {MCP_MODULE_CANDIDATES}]"
        )
    env = offline.get("env")
    if not isinstance(env, dict) or not isinstance(env.get("PYTHONPATH"), str) or not env["PYTHONPATH"]:
        problems.append(f"mcpServers.{MCP_SERVER_NAME}.env.PYTHONPATH must be a non-empty string")
    return problems


def _validate_bound_entry(entry: dict) -> list[str]:
    problems: list[str] = []
    prefix = f"mcpServers.{BOUND_SERVER_NAME}"
    command = entry.get("command")
    if not isinstance(command, str) or not command:
        problems.append(f"{prefix}.command must be a non-empty string")
    args = entry.get("args")
    if not isinstance(args, list) or not all(isinstance(item, str) for item in args):
        problems.append(f"{prefix}.args must be a list of strings")
        return problems
    if args[: len(BOUND_SERVE_ARGS)] != list(BOUND_SERVE_ARGS):
        problems.append(f"{prefix}.args must start with {list(BOUND_SERVE_ARGS)}")
    for flag in ("--config", "--token-file"):
        if flag not in args or args.index(flag) + 1 >= len(args):
            problems.append(f"{prefix}.args is missing {flag} <path>")
    env = entry.get("env")
    if not isinstance(env, dict) or not isinstance(env.get("PYTHONPATH"), str) or not env["PYTHONPATH"]:
        problems.append(f"{prefix}.env.PYTHONPATH must be a non-empty string")
    return problems


def read_mcp_config(path: Path) -> dict:
    """Read and validate ``mcp.json``; raise ``PLUGIN_BUILD_FAILED`` on bad input."""

    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LauncherError(
            "PLUGIN_BUILD_FAILED",
            "mcp.json cannot be read or parsed",
            {"path": str(path), "reason": str(exc)},
        ) from None
    problems = validate_mcp_config(document)
    if problems:
        raise LauncherError(
            "PLUGIN_BUILD_FAILED",
            "mcp.json is structurally invalid",
            {"path": str(path), "problems": problems},
        )
    return document
