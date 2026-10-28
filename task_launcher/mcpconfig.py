"""Generation and validation of ``mcp.json`` for one task.

The task agent gets the already-merged offline-audit MCP server
(``easycirq/scripts/easycirq_mcp``; legacy checkouts use ``easycirq/scripts``)
mounted explicitly with ``--mcp-config``.  It is a **stdio** child process started
by the agent, so the launcher only writes a configuration file; it never starts
the server itself and never talks to it.

The ``PYTHONPATH`` points at the Skill's ``scripts`` directory, which is where
``python -m easycirq_mcp`` is importable from.  It is resolved to a forward-slash
absolute path so the JSON is valid on Windows and the value is stable for the
same installation.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from . import BOUND_MODULE, BOUND_SERVER_NAME, BOUND_SERVE_ARGS, MCP_MODULE, MCP_SERVER_NAME
from .protocol import LauncherError


def _posix(path: Path) -> str:
    return path.resolve().as_posix()


def _bound_entry(bound: dict, python_executable: str | None) -> dict:
    """The trusted B1-Bound supervisor entry (replaces the offline-audit one)."""

    command = python_executable or sys.executable or "python"
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


def build_mcp_config(
    skill_scripts_dir: Path,
    python_executable: str | None = None,
    *,
    bound: dict | None = None,
) -> dict:
    """Return the ``.mcp.json`` document for a task.

    ``command`` is resolved to an actual interpreter (IC-12): a bare ``python``
    does not exist on every Linux/macOS install.  Callers may override it with
    an explicit ``--mcp-python`` value, otherwise the launcher's own interpreter
    is used.

    ``bound=None`` keeps the PoC behaviour (offline-audit server only).  With
    ``bound`` given, the task MCP surface is **replaced** by the trusted
    B1-Bound supervisor, so the agent cannot call offline audit tools directly
    and bypass the signed receipt chain.
    """

    command = python_executable or sys.executable or "python"
    if bound is not None:
        return {"mcpServers": {BOUND_SERVER_NAME: _bound_entry(bound, python_executable)}}
    return {
        "mcpServers": {
            MCP_SERVER_NAME: {
                "command": command,
                "args": ["-m", MCP_MODULE],
                "env": {"PYTHONPATH": _posix(skill_scripts_dir)},
            }
        }
    }


def write_mcp_config(
    path: Path,
    skill_scripts_dir: Path,
    python_executable: str | None = None,
    *,
    bound: dict | None = None,
) -> dict:
    """Write ``mcp.json`` (LF, deterministic JSON) and return the document."""

    document = build_mcp_config(skill_scripts_dir, python_executable, bound=bound)
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
        prefix = f"mcpServers.{BOUND_SERVER_NAME}"
        command = bound.get("command")
        if not isinstance(command, str) or not command:
            problems.append(f"{prefix}.command must be a non-empty string")
        args = bound.get("args")
        if not isinstance(args, list) or not all(isinstance(item, str) for item in args):
            problems.append(f"{prefix}.args must be a list of strings")
        elif args[: len(BOUND_SERVE_ARGS)] != list(BOUND_SERVE_ARGS):
            problems.append(f"{prefix}.args must start with {list(BOUND_SERVE_ARGS)}")
        for flag in ("--config", "--token-file"):
            if not isinstance(args, list) or flag not in args or args.index(flag) + 1 >= len(args):
                problems.append(f"{prefix}.args is missing {flag} <path>")
        env = bound.get("env")
        if not isinstance(env, dict) or not isinstance(env.get("PYTHONPATH"), str) or not env["PYTHONPATH"]:
            problems.append(f"{prefix}.env.PYTHONPATH must be a non-empty string")
        return problems
    entry = offline
    if not isinstance(entry, dict):
        problems.append(f"mcpServers.{MCP_SERVER_NAME} is missing")
        return problems
    command = entry.get("command")
    if not isinstance(command, str) or not command:
        problems.append(f"mcpServers.{MCP_SERVER_NAME}.command must be a non-empty string")
    args = entry.get("args")
    if not isinstance(args, list) or not all(isinstance(item, str) for item in args):
        problems.append(f"mcpServers.{MCP_SERVER_NAME}.args must be a list of strings")
    elif args[:2] != ["-m", MCP_MODULE]:
        problems.append(f"mcpServers.{MCP_SERVER_NAME}.args must start with ['-m', '{MCP_MODULE}']")
    env = entry.get("env")
    if not isinstance(env, dict) or not isinstance(env.get("PYTHONPATH"), str) or not env["PYTHONPATH"]:
        problems.append(f"mcpServers.{MCP_SERVER_NAME}.env.PYTHONPATH must be a non-empty string")
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
