#!/usr/bin/env python3
"""Turn a frozen ``easycirq sch drc --json`` result into the KPI gate's ERC check.

The SDK DRC returns a normalised aggregate (fatal/error/warn/info) plus, when
the build supports it, per-item violations. This adapter keeps the distinction
that matters: **fatal + error are the hard ERC count** (output conflicts,
multiple drivers, no driver, power-to-ground); warnings are reported but do not
count against the hard KPI.

Accepted input shapes:
  * ``{"result": {...}}``       envelope from ``sch drc --json`` (current CLI)
  * ``{...}``                    bare normalised result (older builds)

It never calls EDA. A result that does not carry a recognisable summary is
``unknown`` -- absence is never a pass.

Exit codes: 0 = no findings, 1 = findings (warnings only), 2 = fatal/error or
invalid input.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

SCHEMA = "easycirq-sch-drc-check/v1"
LEVELS = ("fatal", "error", "warn", "info", "unknown")


def _load(path):
    with open(path, "rb") as stream:
        raw = stream.read(4_000_001)
    if len(raw) >= 4_000_000:
        raise ValueError(f"{path}: input exceeds 4 MB")
    return json.loads(raw.decode("utf-8-sig"))


def _summary(result):
    summary = result.get("summary")
    if isinstance(summary, dict):
        return summary
    # fall back to top-level counters
    if any(level in result for level in LEVELS):
        return {level: result.get(level, 0) for level in LEVELS}
    return None


def _num(value):
    return value if type(value) is int and value >= 0 else 0


def analyze(payload):
    if not isinstance(payload, dict):
        raise ValueError("drc result must be JSON object")
    result = payload.get("result") if isinstance(payload.get("result"), dict) else payload
    summary = _summary(result)
    if summary is None:
        return {
            "schema": SCHEMA, "tool": "sch_drc_metrics.py",
            "verdict": "unknown",
            "metrics": {"erc_violations": None, "erc_fatal": None,
                        "erc_error": None, "erc_warn": None},
            "findings": [{"severity": "warning", "code": "drc_unavailable",
                          "message": "drc result carries no summary/counters"}],
            "note": "无法从 DRC 结果读出计数，按缺证据处理",
        }

    fatal = _num(summary.get("fatal"))
    error = _num(summary.get("error"))
    warn = _num(summary.get("warn"))
    findings = []
    for item in result.get("violations") or []:
        if not isinstance(item, dict):
            continue
        level = str(item.get("level") or item.get("type") or "info").lower()
        rule = item.get("rule") or item.get("code") or "?"
        severity = ("error" if level in ("fatal", "error")
                    else "warning" if level == "warn" else "info")
        if severity == "info":
            continue
        findings.append({
            "severity": severity,
            "code": "drc_" + severity if severity != "error" else "drc_error",
            "message": f"DRC {level}: {rule}",
        })

    violations = fatal + error
    return {
        "schema": SCHEMA,
        "tool": "sch_drc_metrics.py",
        "verdict": "fail" if violations else "pass",
        "metrics": {"erc_violations": violations, "erc_fatal": fatal,
                    "erc_error": error, "erc_warn": warn},
        "findings": findings,
        "note": "erc_violations = fatal + error；warn 记录但不计入硬指标",
    }


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="easycirq sch drc --json -> sch_kpi erc check report")
    ap.add_argument("--input", required=True, help="sch drc --json output")
    ap.add_argument("--out", help="write the check report here")
    ap.add_argument("--json", action="store_true", help="print the report")
    ap.add_argument("--quiet", action="store_true", help="summary line only")
    args = ap.parse_args(argv)

    try:
        report = analyze(_load(args.input))
    except (OSError, ValueError) as exc:
        print(f"sch_drc_metrics: {exc}", file=sys.stderr)
        return 2

    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    if args.json:
        print(text)
    elif not args.quiet:
        print(f"drc: verdict={report['verdict']} metrics={report['metrics']}")
        for finding in report["findings"][:20]:
            print(f"  - {finding['severity']}: {finding['message']}")
    if report["verdict"] == "unknown":
        return 2
    return 1 if report["verdict"] == "fail" else 0


if __name__ == "__main__":
    sys.exit(main())
