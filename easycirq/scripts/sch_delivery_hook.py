#!/usr/bin/env python3
"""Claude Code Stop-hook for the schematic delivery gate (anti-forgery mode).

Two modes:

1. Trusted re-check (preferred): pass ``--gate`` + the four input paths. On every
   Stop the hook **re-runs** ``sch_delivery_check.py`` against the actual input
   files and overwrites ``--evidence`` with the trusted report. The verdict comes
   from the re-run, so a hand-written PASS in ``--evidence`` cannot satisfy it.
   The report also records ``inputs[*].sha256``, binding it to the exact files.

2. Legacy: without ``--gate``, only the existing ``--evidence`` verdict is read.

Output contract: on block, write ``{"decision":"block","reason":"..."}`` to stdout
and exit 0. On allow, write nothing and exit 0. ``stop_hook_active`` always allows
(loop guard).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")


def _log(path, line):
    if not path:
        return
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with Path(path).open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


def _block(decision_reason):
    sys.stdout.write(json.dumps({"decision": "block", "reason": decision_reason},
                                ensure_ascii=False) + "\n")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--evidence", required=True,
                    help="path to the delivery report (overwritten by the re-check)")
    ap.add_argument("--log", help="optional sidecar log")
    ap.add_argument("--gate", help="path to sch_delivery_check.py for trusted re-check")
    ap.add_argument("--frame-plan")
    ap.add_argument("--layout")
    ap.add_argument("--text-audit")
    ap.add_argument("--style")
    ap.add_argument("--official-svg")
    ap.add_argument("--visual-overlay")
    ap.add_argument("--visual-similarity")
    ap.add_argument("--visual-reference")
    ap.add_argument("--visual-side-by-side")
    ap.add_argument("--skip-layout", action="store_true")
    ap.add_argument("--require-style", action="store_true")
    ap.add_argument("--require-visual", action="store_true")
    ap.add_argument("--allow-title-only", action="store_true")
    args = ap.parse_args(argv)

    evidence = Path(args.evidence)
    _log(args.log, "%s hook ran evidence=%s gate=%s" % (time.time(), evidence, bool(args.gate)))

    stop_hook_active = False
    try:
        raw = sys.stdin.read()
        if raw.strip():
            stop_hook_active = bool(json.loads(raw).get("stop_hook_active"))
    except (OSError, ValueError):
        pass
    if stop_hook_active:
        _log(args.log, "stop_hook_active -> allow")
        return 0

    if args.gate:
        cmd = [sys.executable, args.gate, "--out", str(evidence), "--json"]
        for flag, value in (
            ("--frame-plan", args.frame_plan),
            ("--layout", args.layout),
            ("--text-audit", args.text_audit),
            ("--style", args.style),
            ("--official-svg", args.official_svg),
            ("--visual-overlay", args.visual_overlay),
            ("--visual-similarity", args.visual_similarity),
            ("--visual-reference", args.visual_reference),
            ("--visual-side-by-side", args.visual_side_by_side),
        ):
            if value:
                cmd += [flag, value]
        for flag, enabled in (
            ("--skip-layout", args.skip_layout),
            ("--require-style", args.require_style),
            ("--require-visual", args.require_visual),
            ("--allow-title-only", args.allow_title_only),
        ):
            if enabled:
                cmd.append(flag)
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", timeout=180)
        except (OSError, subprocess.TimeoutExpired) as exc:
            _log(args.log, "gate re-check failed: %s" % exc)
            return _block("delivery gate re-check failed: %s" % exc)

        report = None
        try:
            report = json.loads((proc.stdout or "").strip())
        except ValueError:
            pass
        if report is None:
            _log(args.log, "gate produced no JSON (exit %s)" % proc.returncode)
            return _block("delivery gate produced no report (exit %s)" % proc.returncode)
        verdict = report.get("verdict")
        if verdict == "pass":
            _log(args.log, "re-check verdict=pass -> allow")
            return 0
        gaps = report.get("gaps") or []
        reason = "delivery gate verdict=%s" % verdict
        if gaps:
            reason += "; first gaps: " + "; ".join(str(g) for g in gaps[:3])
        _log(args.log, "re-check block: %s" % reason)
        return _block(reason)

    # Legacy: trust the existing report.
    if evidence.is_file():
        try:
            report = json.loads(evidence.read_text(encoding="utf-8"))
            if report.get("verdict") == "pass":
                _log(args.log, "legacy verdict=pass -> allow")
                return 0
            reason = "delivery report verdict=%s; fix gaps then re-run sch_delivery_check.py" % report.get("verdict")
        except (OSError, ValueError) as exc:
            reason = "delivery report unreadable/invalid: %s" % exc
    else:
        reason = "no delivery report at %s; run sch_delivery_check.py and write a PASS before finishing" % evidence

    _log(args.log, "legacy block: %s" % reason)
    return _block(reason)


if __name__ == "__main__":
    raise SystemExit(main())
