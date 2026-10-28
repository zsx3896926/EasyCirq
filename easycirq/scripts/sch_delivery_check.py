#!/usr/bin/env python3
"""Offline schematic-delivery gate: frame metadata + layout + visible text.

A schematic is only "delivered" when, for the same page/snapshot:

  1. every module frame has order + a title text id + a **distinct** purpose
     text id  (`sch_frame_meta_check.py`, blocked on title-only frames);
  2. the actual snapshot layout passes `sch_layout_check.py --strict`
     (frame order/title/purpose present, no missing/stale objects);
  3. measured visible text passes `sch_text_audit.py --strict`
     (no unowned/duplicate/rotated text, zones in reading order).

This wrapper only orchestrates the three existing offline checkers and merges
their exit codes into one verdict. It never talks to EDA, never writes the
project, and its PASS is a structural acceptance, not electrical/visual proof.

Exit codes: 0 = PASS, 1 = REVIEW (findings to fix), 2 = BLOCKED (invalid or a
required input/coverage is missing).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR = Path(__file__).resolve().parent
FRAME_META = SCRIPT_DIR / "sch_frame_meta_check.py"
LAYOUT = SCRIPT_DIR / "sch_layout_check.py"
TEXT_AUDIT = SCRIPT_DIR / "sch_text_audit.py"

SCHEMA = "easycirq-sch-delivery/v1"


def _run(args, *, timeout=120):
    proc = subprocess.run(
        [sys.executable, *args], capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=timeout)
    payload = None
    out = (proc.stdout or "").strip()
    if out:
        try:
            payload = json.loads(out)
        except json.JSONDecodeError:
            payload = {"_raw": out[:2000]}
    return proc.returncode, payload, (proc.stderr or "")[:2000]


def _file_status(path):
    if not path:
        return {"provided": False}
    p = Path(path)
    return {"provided": True, "path": str(p), "exists": p.is_file()}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Offline schematic-delivery gate (frame + layout + text)")
    ap.add_argument("--frame-plan", help="design-engine-sch-frame-plan/v1 JSON")
    ap.add_argument("--layout", help="schematic snapshot JSON for sch_layout_check.py")
    ap.add_argument("--text-audit", help="measured visible-text JSON for sch_text_audit.py")
    ap.add_argument("--official-svg", help="official exported schematic SVG (evidence only)")
    ap.add_argument("--visual-overlay", help="sch_visual_audit.py overlay SVG (evidence only)")
    ap.add_argument("--skip-layout", action="store_true",
                    help="allow a PASS without a layout snapshot (partial/offline review)")
    ap.add_argument("--allow-title-only", action="store_true",
                    help="downgrade missing purpose_text_id to review (explicit defer)")
    ap.add_argument("--require-visual", action="store_true",
                    help="require both SVGs to exist before PASS")
    ap.add_argument("--out", help="write the UTF-8 JSON report here")
    ap.add_argument("--json", action="store_true", help="print JSON to stdout")
    args = ap.parse_args(argv)

    gaps, next_steps = [], []
    checks = {
        "frame_meta": {"provided": bool(args.frame_plan), "exit": None, "status": None},
        "layout": {"provided": bool(args.layout), "exit": None, "status": None},
        "text_audit": {"provided": bool(args.text_audit), "exit": None, "status": None},
        "visual": {
            "official_svg": _file_status(args.official_svg),
            "visual_overlay": _file_status(args.visual_overlay),
        },
    }

    if not args.frame_plan:
        gaps.append("frame_plan JSON is required")
    if not args.text_audit:
        gaps.append("text-audit JSON is required")

    if args.frame_plan:
        extra = ["--allow-title-only"] if args.allow_title_only else []
        code, payload, _ = _run([str(FRAME_META), "--plan", args.frame_plan, "--json", *extra])
        checks["frame_meta"]["exit"] = code
        checks["frame_meta"]["report"] = payload
        if payload and isinstance(payload, dict):
            checks["frame_meta"]["status"] = payload.get("status")
            gaps.extend(payload.get("gaps") or [])
            if payload.get("problems"):
                gaps.extend(payload["problems"])

    if args.layout:
        code, payload, _ = _run([str(LAYOUT), args.layout, "--strict", "--fail-on-info"])
        checks["layout"]["exit"] = code
        checks["layout"]["report"] = payload
        if payload and isinstance(payload, dict):
            checks["layout"]["status"] = payload.get("status") or payload.get("verdict")
            gaps.extend(payload.get("candidates") or payload.get("findings") or [])
    elif not args.skip_layout:
        gaps.append("layout snapshot not provided (frames not verified on the actual canvas)")

    if args.text_audit:
        code, payload, _ = _run([str(TEXT_AUDIT), args.text_audit, "--strict"])
        checks["text_audit"]["exit"] = code
        checks["text_audit"]["report"] = payload
        if payload and isinstance(payload, dict):
            checks["text_audit"]["status"] = payload.get("status") or payload.get("verdict")
            checks["text_audit"]["findings"] = payload.get("findings")
            if payload.get("findings"):
                gaps.append("%d text finding(s)" % len(payload["findings"]))
            if payload.get("missing_classes"):
                gaps.append("text coverage missing: %s" % ", ".join(payload["missing_classes"]))

    if args.require_visual:
        for key in ("official_svg", "visual_overlay"):
            st = checks["visual"][key]
            if not st.get("provided") or not st.get("exists"):
                gaps.append("%s is required and missing" % key)

    exits = [checks["frame_meta"].get("exit"), checks["layout"].get("exit"),
             checks["text_audit"].get("exit")]
    exits = [e for e in exits if e is not None]

    if any(e is None for e in [checks["frame_meta"]["exit"], checks["text_audit"]["exit"]]) \
            or (not args.layout and not args.skip_layout):
        verdict = "blocked"
    elif any(e == 2 for e in exits):
        verdict = "blocked"
    elif any(e == 1 for e in exits):
        verdict = "review"
    else:
        verdict = "pass"

    if verdict == "blocked":
        next_steps.append("补齐 frame order/purpose、layout 快照与文字覆盖后重跑")
    elif verdict == "review":
        next_steps.append("处理上面列出的 review findings 后重跑")

    report = {
        "schema": SCHEMA,
        "verdict": verdict,
        "checks": checks,
        "gaps": gaps,
        "next": next_steps,
    }

    out = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        Path(args.out).write_text(out, encoding="utf-8", newline="\n")
    if args.json or not args.out:
        sys.stdout.write(out)

    return {"pass": 0, "review": 1, "blocked": 2}[verdict]


if __name__ == "__main__":
    raise SystemExit(main())
