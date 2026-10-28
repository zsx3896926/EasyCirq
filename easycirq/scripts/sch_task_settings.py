#!/usr/bin/env python3
"""Generate a per-task Claude Code settings.json that enforces the schematic
delivery gate via a Stop hook, in trusted re-check mode.

The hook re-runs ``sch_delivery_check.py`` on every Stop against the actual
input files and overwrites ``--evidence`` with the trusted report, so a
hand-written PASS cannot satisfy it.

Usage:
    python sch_task_settings.py --workdir <task> --out <task>/settings.json \
        [--frame-plan frame-plan.json --layout layout.json \
         --text-audit text-audit.json --style style-input.json] \
        [--skip-layout] [--require-style] [--require-visual] [--hook-log hook.log]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
HOOK = SCRIPT_DIR / "sch_delivery_hook.py"
GATE = SCRIPT_DIR / "sch_delivery_check.py"


def _abs(workdir: Path, value: str) -> Path:
    p = Path(value)
    return (p if p.is_absolute() else workdir / p).resolve()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--evidence", default="delivery.json")
    ap.add_argument("--frame-plan", default="frame-plan.json")
    ap.add_argument("--layout", default="layout.json")
    ap.add_argument("--text-audit", default="text-audit.json")
    ap.add_argument("--style", default="style-input.json")
    ap.add_argument("--out", default="settings.json")
    ap.add_argument("--hook-log", default="hook.log")
    ap.add_argument("--python", default=sys.executable)
    ap.add_argument("--skip-layout", action="store_true")
    ap.add_argument("--require-style", action="store_true", default=True)
    ap.add_argument("--require-visual", action="store_true")
    ap.add_argument("--visual-similarity", help="exported PNG for the reference similarity check")
    ap.add_argument("--visual-reference", help="reference image override")
    ap.add_argument("--visual-side-by-side", help="write the comparison PNG here")
    args = ap.parse_args(argv)

    workdir = Path(args.workdir).resolve()
    workdir.mkdir(parents=True, exist_ok=True)
    evidence = _abs(workdir, args.evidence)

    command = [args.python, str(HOOK), "--evidence", str(evidence),
               "--gate", str(GATE),
               "--frame-plan", str(_abs(workdir, args.frame_plan)),
               "--text-audit", str(_abs(workdir, args.text_audit)),
               "--style", str(_abs(workdir, args.style))]
    if not args.skip_layout:
        command += ["--layout", str(_abs(workdir, args.layout))]
    if args.hook_log:
        command += ["--log", str(_abs(workdir, args.hook_log))]
    if args.skip_layout:
        command.append("--skip-layout")
    if args.require_style:
        command.append("--require-style")
    if args.require_visual:
        command.append("--require-visual")
    if args.visual_similarity:
        command += ["--visual-similarity", str(_abs(workdir, args.visual_similarity))]
        if args.visual_reference:
            command += ["--visual-reference", str(_abs(workdir, args.visual_reference))]
        if args.visual_side_by_side:
            command += ["--visual-side-by-side", str(_abs(workdir, args.visual_side_by_side))]

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
