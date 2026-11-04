#!/usr/bin/env python3
"""Roll several per-page KPI reports into one scoreboard.

A multi-page schematic is only as good as its worst page, so the scoreboard
answers one question: *can this project go to the EDA session yet?* It reads
``kpi-report.json`` files produced by ``sch_kpi.py`` (or the offline pipeline),
never recomputes a KPI, and never invents a page.

Rules (declared):
  * a page is ``PASS`` only when its own report says PASS;
  * the project is ``PASS`` only when every listed page PASSes and every page
    has ``apply_allowed=true``;
  * any page BLOCKED -> project BLOCKED; otherwise REVIEW;
  * missing pages are never assumed green: a caller must list them explicitly.

Exit codes: 0 = project PASS, 1 = REVIEW, 2 = BLOCKED.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

SCHEMA = "easycirq-sch-kpi-scoreboard/v1"


def _load(path):
    with open(path, "rb") as stream:
        raw = stream.read(8_000_001)
    if len(raw) >= 8_000_000:
        raise ValueError(f"{path}: report too large")
    return json.loads(raw.decode("utf-8-sig"))


def _page_row(report):
    kpis = report.get("kpis") or []
    counts = {"pass": 0, "fail": 0, "missing": 0, "unknown": 0}
    for row in kpis:
        status = row.get("status")
        if status in counts and not row.get("advisory"):
            counts[status] += 1
    return {
        "project": report.get("project"),
        "page": report.get("page"),
        "verdict": report.get("verdict"),
        "apply_allowed": bool((report.get("stability") or {}).get("apply_allowed")),
        "kpi_total": len(kpis),
        **counts,
        "fail": [r["id"] for r in kpis
                 if r.get("status") == "fail" and not r.get("advisory")],
        "missing": [r["id"] for r in kpis
                    if r.get("status") in ("missing", "unknown")
                    and not r.get("advisory")],
        "advisory": [r["id"] for r in kpis if r.get("advisory")],
        "blockers": [b.get("kpi") for b in report.get("blockers") or []],
    }


def summarize(reports, expected_pages=None):
    if not reports:
        raise ValueError("no KPI reports supplied")
    # one row per (project, page): keep the newest report, count the duplicates
    latest, duplicates = {}, 0
    for report in reports:
        if not isinstance(report, dict):
            raise ValueError("each report must be a JSON object")
        key = (report.get("project"), report.get("page"))
        if not all(key):
            raise ValueError("each report needs project and page")
        current = latest.get(key)
        if current is None:
            latest[key] = report
            continue
        duplicates += 1
        if str(report.get("generatedAt", "")) > str(current.get("generatedAt", "")):
            latest[key] = report
    rows = [_page_row(report) for report in latest.values()]

    seen = {row["page"] for row in rows}
    expected = set(expected_pages or [])
    absent = sorted(expected - seen)
    unexpected = sorted(seen - expected) if expected else []

    blocked = [row for row in rows if row["verdict"] == "BLOCKED"]
    review = [row for row in rows if row["verdict"] == "REVIEW"]
    if blocked:
        verdict = "BLOCKED"
    elif review:
        verdict = "REVIEW"
    else:
        verdict = "PASS"

    can_apply = (verdict == "PASS"
                 and all(row["apply_allowed"] for row in rows)
                 and not absent)
    return {
        "schema": SCHEMA,
        "verdict": verdict,
        "can_apply": can_apply,
        "pages": rows,
        "duplicates_ignored": duplicates,
        "absent_pages": absent,
        "unexpected_pages": unexpected,
        "blocked_pages": [row["page"] for row in blocked],
        "note": ("全部页面 PASS 且各自 apply_allowed 才允许上机"
                 if can_apply else "存在 BLOCKED/REVIEW/未列页面，禁止上机"),
    }


def _discover(path):
    path = Path(path)
    if path.is_file():
        return [path]
    return sorted(path.glob("*/kpi-report.json"))


def render_markdown(board):
    lines = [
        "# 原理图 KPI 汇总",
        "",
        f"- 项目裁决: **{board['verdict']}**  可上机: "
        f"{'是' if board['can_apply'] else '否'}",
        "",
        "| 页面 | 裁决 | 可上机 | 通过 | 失败 | 缺证据 | 失败项 |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in board["pages"]:
        lines.append(
            f"| {row['page']} | {row['verdict']} | "
            f"{'是' if row['apply_allowed'] else '否'} | {row['pass']} | "
            f"{row['fail']} | {row['missing']} | "
            f"{', '.join(row['fail']) or '-'} |")
    if board["absent_pages"]:
        lines += ["", f"未提供页面: {', '.join(board['absent_pages'])}"]
    if board["unexpected_pages"]:
        lines += ["", f"未声明页面: {', '.join(board['unexpected_pages'])}"]
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Multi-page KPI scoreboard (reads kpi-report.json files)")
    ap.add_argument("--reports", required=True,
                    help="directory of */kpi-report.json, or one report file")
    ap.add_argument("--expect-page", action="append",
                    help="page that must be present (repeatable)")
    ap.add_argument("--json", action="store_true", help="print JSON")
    ap.add_argument("--out", help="write JSON here")
    args = ap.parse_args(argv)

    try:
        paths = _discover(args.reports)
        if not paths:
            raise ValueError(f"no kpi-report.json under {args.reports}")
        board = summarize([_load(p) for p in paths], args.expect_page)
    except (OSError, ValueError) as exc:
        print(f"sch_kpi_scoreboard: {exc}", file=sys.stderr)
        return 2

    if args.out:
        Path(args.out).write_text(
            json.dumps(board, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(board, ensure_ascii=False, indent=2)
          if args.json else render_markdown(board))
    return {"PASS": 0, "REVIEW": 1, "BLOCKED": 2}[board["verdict"]]


if __name__ == "__main__":
    sys.exit(main())
