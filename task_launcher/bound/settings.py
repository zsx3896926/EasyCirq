"""Per-task Claude Code ``settings.json`` generation.

Belt and braces: ``--allowedTools`` is only "pre-approval" in some Claude Code
versions, so the same allow/deny lists are written to a per-task settings file.
Hooks are an **optional** Phase-3 quality layer: the real gate is the supervisor
state machine, not the hook. Hooks therefore default to disabled and never carry
the HMAC key or the task token (only the task directory path).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from . import (
    ALLOWED_AGENT_TOOLS,
    DENIED_AGENT_TOOLS,
    SKILL_NAME,
    SKILL_NAME_CANDIDATES,
    allowed_agent_tools,
    normalize_skill_name,
)

#: Hint for the documentation: permissions.deny names are tool names / rules,
#: not shell globs.
PERMISSION_MODE = "default"


def _hook_command(script: str, task_dir: Path) -> str:
    hooks_dir = Path(__file__).resolve().parent / "hooks"
    return f'"{sys.executable}" "{hooks_dir / script}" --task-dir "{task_dir}"'


def build_settings(
    task_dir: Path,
    *,
    hooks_enabled: bool = False,
    skill_name: str = SKILL_NAME,
) -> dict[str, Any]:
    """Build the per-task settings document (no secrets)."""

    settings: dict[str, Any] = {
        "permissions": {
            "deny": list(DENIED_AGENT_TOOLS),
            "allow": list(allowed_agent_tools(skill_name)),
            "defaultMode": "default",
        },
        "env": {
            # Phase 1 must not need network; keep the agent env minimal.
            "EASYCIRQ_BOUND_PHASE": "1",
        },
    }
    if hooks_enabled:
        settings["hooks"] = {
            "PostToolUse": [
                {
                    "matcher": "Skill",
                    "hooks": [
                        {
                            "type": "command",
                            "command": _hook_command("mark_skill.py", task_dir),
                            "timeout": 10,
                        }
                    ],
                }
            ],
            "PreToolUse": [
                {
                    "matcher": ".*",
                    "hooks": [
                        {
                            "type": "command",
                            "command": _hook_command("require_skill.py", task_dir),
                            "timeout": 10,
                        }
                    ],
                }
            ],
            "Stop": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": _hook_command("verify_stop.py", task_dir),
                            "timeout": 10,
                        }
                    ]
                }
            ],
        }
    return settings


def validate_settings(settings: Any, skill_name: str | None = None) -> list[str]:
    """Return a list of structural problems (empty means valid)."""

    problems: list[str] = []
    if not isinstance(settings, dict):
        return ["settings must be a JSON object"]
    permissions = settings.get("permissions")
    if not isinstance(permissions, dict):
        problems.append("permissions must be an object")
        return problems
    deny = permissions.get("deny")
    allow = permissions.get("allow")
    if not isinstance(deny, list) or not isinstance(allow, list):
        problems.append("permissions.deny/allow must be arrays")
        return problems
    missing_deny = [tool for tool in DENIED_AGENT_TOOLS if tool not in deny]
    if missing_deny:
        problems.append(f"permissions.deny is missing: {', '.join(missing_deny)}")
    for tool in ("Bash", "Write", "Edit", "Agent", "Task", "WebFetch", "WebSearch"):
        if tool not in deny:
            problems.append(f"permissions.deny must contain {tool}")
    # With an explicit skill_name, require that exact Skill(...) entry; without
    # one (validation of an arbitrary task settings file), accept either layout.
    expected_tools = (
        ("Read", "Glob", "Grep", "mcp__easycirq_bound__*")
        if skill_name is None
        else allowed_agent_tools(skill_name)
    )
    for expected in expected_tools:
        if expected not in allow:
            problems.append(f"permissions.allow is missing {expected}")
    # Tolerate the other Skill name (transitional repos may have either one);
    # the plan/argv path always uses the detected name.
    skill_entries = [entry for entry in allow if isinstance(entry, str) and entry.startswith("Skill(")]
    if len(skill_entries) != 1:
        problems.append("permissions.allow must contain exactly one Skill(...) entry")
    elif not any(entry == f"Skill({name})" for entry in skill_entries for name in SKILL_NAME_CANDIDATES):
        problems.append(f"permissions.allow Skill entry is not one of {SKILL_NAME_CANDIDATES}")
    if "Bash" in allow:
        problems.append("permissions.allow must not contain Bash")
    hooks = settings.get("hooks")
    if hooks is not None and not isinstance(hooks, dict):
        problems.append("hooks must be an object when present")
    return problems


def write_settings(path: Path, settings: dict[str, Any]) -> None:
    problems = validate_settings(settings)
    if problems:
        raise ValueError("invalid settings document: " + "; ".join(problems))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(settings, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
