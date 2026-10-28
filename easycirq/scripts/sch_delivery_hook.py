#!/usr/bin/env python3
"""Claude Code Stop-hook for the schematic delivery gate.

Blocks the agent from finishing a schematic task until a `sch_delivery_check.py`
report exists at ``--evidence`` and its verdict is ``pass``. Reads the hook input
on stdin (ignored except for ``stop_hook_active``, which always lets the agent
stop to avoid an infinite loop).

Output contract (current Claude Code JSON-decision form): on block, write
``{"decision":"block","reason":"..."}`` to stdout and exit 0. On allow, write
nothing and exit 0.

Usage (in a per-task settings.json):
    {"hooks": {"Stop": [{"hooks": [{"type": "command",
       "command": "python <path>/sch_delivery_hook.py --evidence <delivery.json>"}]}]}}
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


def _log(path, line):
    if not path:
        return
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with Path(path).open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--evidence", required=True,
                    help="absolute path to the sch_delivery_check.py JSON report")
    ap.add_argument("--log", help="optional sidecar log to prove the hook ran")
    args = ap.parse_args(argv)

    evidence = Path(args.evidence)
    _log(args.log, "%s hook ran evidence=%s" % (time.time(), evidence))

    # Read hook input (best effort) to honor the loop guard.
    stop_hook_active = False
    try:
        raw = sys.stdin.read()
        if raw.strip():
            data = json.loads(raw)
            stop_hook_active = bool(data.get("stop_hook_active"))
    except (OSError, ValueError):
        pass

    if stop_hook_active:
        _log(args.log, "stop_hook_active -> allow")
        return 0

    if evidence.is_file():
        try:
            report = json.loads(evidence.read_text(encoding="utf-8"))
            if report.get("verdict") == "pass":
                _log(args.log, "verdict=pass -> allow")
                return 0
            reason = "delivery report verdict=%s; fix gaps then re-run sch_delivery_check.py" % report.get("verdict")
        except (OSError, ValueError) as exc:
            reason = "delivery report unreadable/invalid: %s" % exc
    else:
        reason = "no delivery report at %s; run sch_delivery_check.py and write a PASS before finishing" % evidence

    _log(args.log, "block: %s" % reason)
    sys.stdout.write(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
