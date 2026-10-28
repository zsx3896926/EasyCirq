"""Stop hook: refuse to stop before the supervisor says FINALIZED.

Optional Phase-3 quality layer (disabled by default). It reads the
supervisor-written ``status.json`` from the task directory, so it verifies the
*supervisor's* state, not the model's claim.

Honors ``stop_hook_active`` to avoid a stop/continue loop. Output follows the
Claude Code hook contract: ``{"decision": "block", "reason": "..."}`` blocks the
stop and tells the model to continue.

Usage: ``python <package>/hooks/verify_stop.py --task-dir <task-dir>``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

FINALIZED = "FINALIZED"


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
    if payload.get("stop_hook_active"):
        sys.stdout.write("{}\n")
        return 0
    status_path = task_dir / "status.json"
    state = "MISSING"
    remaining: list[str] = []
    try:
        status = json.loads(status_path.read_text(encoding="utf-8"))
        state = str(status.get("state", "MISSING"))
        remaining = list(status.get("remaining") or [])
    except (OSError, json.JSONDecodeError):
        pass
    if state == FINALIZED:
        sys.stdout.write("{}\n")
        return 0
    reason = f"任务未完成：supervisor 状态为 {state}"
    if remaining:
        reason += f"，缺少步骤 {', '.join(remaining)}"
    reason += "。请继续按顺序调用 mcp__easycirq_bound__ 工具，直到 finalize 返回报告。"
    sys.stdout.write(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
