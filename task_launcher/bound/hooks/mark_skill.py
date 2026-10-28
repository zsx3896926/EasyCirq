"""PostToolUse hook: mark that the design-hardware Skill was loaded.

Optional Phase-3 quality layer (disabled by default). It never reads the HMAC
key or the task token; it only writes a marker file inside the task directory so
``require_skill.py`` can distinguish "Skill loaded" from "model claims it did".

Usage (from settings.json)::

    python <package>/hooks/mark_skill.py --task-dir <task-dir>

Reads the hook JSON from stdin. Always exits 0; hook failures must not hang the
session.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


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
    tool_input = payload.get("tool_input") or {}
    skill = tool_input.get("skill") or tool_input.get("name") or ""
    if tool_name == "Skill" and "design-hardware" in str(skill):
        marker = task_dir / "skill.marker"
        marker.write_text(
            json.dumps(
                {
                    "skill": "design-hardware",
                    "marked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "tool_name": tool_name,
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
    # PostToolUse: no decision, always allow.
    sys.stdout.write("{}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
