"""PreToolUse hook: require the design-hardware Skill before other tools.

Optional Phase-3 quality layer (disabled by default; the real gate is the
supervisor state machine). It only looks for the marker written by
``mark_skill.py`` inside the task directory.

Output follows the Claude Code hook contract: a denial is
``{"hookSpecificOutput": {"hookEventName": "PreToolUse",
"permissionDecision": "deny", "permissionDecisionReason": "..."}}`` and the
process still exits 0.

Usage: ``python <package>/hooks/require_skill.py --task-dir <task-dir>``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SKILL_TOOL = "Skill"


def _force_utf8_stdio() -> None:
    for stream in (sys.stdin, sys.stdout):
        try:
            stream.reconfigure(encoding="utf-8", newline="\n")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass


def main(argv: list[str] | None = None) -> int:
    _force_utf8_stdio()
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--task-dir", required=True)
    args, _unknown = parser.parse_known_args(argv)
    task_dir = Path(args.task_dir)
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        payload = {}
    tool_name = payload.get("tool_name", "")
    if tool_name == SKILL_TOOL:
        sys.stdout.write("{}\n")
        return 0
    marker = task_dir / "skill.marker"
    if marker.is_file():
        sys.stdout.write("{}\n")
        return 0
    decision = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                "本任务必须先加载 design-hardware Skill（PostToolUse marker 缺失）。"
                "请先调用 Skill(design-hardware)，再使用其他工具。"
            ),
        }
    }
    sys.stdout.write(json.dumps(decision, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
