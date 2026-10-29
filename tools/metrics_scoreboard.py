#!/usr/bin/env python3
"""Aggregate schematic layout acceptance reports into a scoreboard.

Reads `*.report.json` files produced by tools/sch_layout_apply.py and emits a
single scoreboard JSON + a markdown table, so nightly runs can be compared.

Usage:
    python tools/metrics_scoreboard.py --reports <dir> [--out scoreboard.json]

Report fields used: project, page, blocks[].wires{total,ok,failed},
metrics{blocks,fits,overlaps,wires_total,wires_ok,wires_failed}, zones_reapplied,
export.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

SCHEMA = "easycirq-sch-layout-scoreboard/v1"


def summarize(project, page, report):
    metrics = report.get("metrics") or {}
    blocks = report.get("blocks") or []
    wires_total = metrics.get("wires_total")
    if wires_total is None:
        wires_total = sum((b.get("wires") or {}).get("total", 0) for b in blocks)
    wires_ok = metrics.get("wires_ok")
    if wires_ok is None:
        wires_ok = sum((b.get("wires") or {}).get("ok", 0) for b in blocks)
    wires_failed = metrics.get("wires_failed")
    if wires_failed is None:
        wires_failed = sum((b.get("wires") or {}).get("failed", 0) for b in blocks)
    fits = metrics.get("fits", 0)
    blocks_total = metrics.get("blocks", len(blocks))
    overlaps = metrics.get("overlaps", 0)
    zones_ok = report.get("zones_reapplied") == 0
    export_ok = report.get("export") == 0
    wire_rate = round(wires_ok / wires_total, 3) if wires_total else None
    verdict = "pass" if (fits == blocks_total and overlaps == 0 and zones_ok and export_ok) else "review"
    return {
        "project": project,
        "page": page,
        "blocks": blocks_total,
        "fits": fits,
        "overlaps": overlaps,
        "zones_ok": zones_ok,
        "export_ok": export_ok,
        "wires_total": wires_total,
        "wires_ok": wires_ok,
        "wires_failed": wires_failed,
        "wire_rate": wire_rate,
        "verdict": verdict,
    }


def markdown(rows):
    head = ("| project | blocks | fits | overlaps | zones | export | wires ok/total | rate | verdict |\n"
            "|---|---|---|---|---|---|---|---|---|")
    lines = [head]
    for r in rows:
        rate = "-" if r["wire_rate"] is None else "%.1f%%" % (r["wire_rate"] * 100)
        lines.append("| %s | %d | %d | %d | %s | %s | %d/%d | %s | %s |" % (
            r["project"], r["blocks"], r["fits"], r["overlaps"],
            "ok" if r["zones_ok"] else "fail", "ok" if r["export_ok"] else "fail",
            r["wires_ok"], r["wires_total"], rate, r["verdict"]))
    return "\n".join(lines)


def build(report_dir, glob="*.report.json"):
    rows = []
    for path in sorted(Path(report_dir).glob(glob)):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        rows.append(summarize(data.get("project") or path.stem.replace(".report", ""),
                              data.get("page", ""), data))
    passed = sum(1 for r in rows if r["verdict"] == "pass")
    return {"schema": SCHEMA, "reports": len(rows), "passed": passed, "rows": rows}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Aggregate layout acceptance reports")
    ap.add_argument("--reports", required=True, help="directory with *.report.json")
    ap.add_argument("--glob", default="*.report.json")
    ap.add_argument("--out", help="write scoreboard JSON here")
    args = ap.parse_args(argv)
    report = build(args.reports, args.glob)
    out = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        Path(args.out).write_text(out, encoding="utf-8", newline="\n")
    print("# layout scoreboard (%d reports, %d pass)\n" % (report["reports"], report["passed"]))
    print(markdown(report["rows"]))
    return 0 if report["passed"] == report["reports"] and report["reports"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
