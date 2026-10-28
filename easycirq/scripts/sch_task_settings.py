#!/usr/bin/env python3
"""Generate a per-task Claude Code settings.json that enforces the schematic
delivery gate via a Stop hook.

The agent cannot finish a schematic task until it has run
``sch_delivery_check.py`` and produced a PASS report at ``--evidence``.
The settings are task-scoped (not global), so they do not alter the customer's
machine-wide Claude Code config.

Usage:
    python sch_task_settings.py --workdir <task> --evidence <task>/delivery.json \
        --out <task>/settings.json [--hook-log <task>/hook.log]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
HOOK = SCRIPT_DIR / "sch_delivery_hook.py"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--evidence", required=True,
                    help="absolute path to the delivery report (verdict must be PASS)")
    ap.add_argument("--out", default="settings.json")
    ap.add_argument("--hook-log", help="optional sidecar log for the hook")
    ap.add_argument("--python", default=sys.executable)
    args = ap.parse_args(argv)

    workdir = Path(args.workdir).resolve()
    evidence = Path(args.evidence)
    if not evidence.is_absolute():
        evidence = workdir / evidence
    evidence = evidence.resolve()

    command = [args.python, str(HOOK), "--evidence", str(evidence)]
    if args.hook_log:
        log = Path(args.hook_log)
        if not log.is_absolute():
            log = workdir / log
        command += ["--log", str(log.resolve())]

    settings = {
        "hooks": {
            "Stop": [{
                "hooks": [{
                    "type": "command",
                    "command": " ".join('"%s"' % c for c in command),
                }],
            }],
        },
    }
    out = Path(args.out)
    if not out.is_absolute():
        out = workdir / out
    out.write_text(json.dumps(settings, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8", newline="\n")
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
