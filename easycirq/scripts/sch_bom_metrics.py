#!/usr/bin/env python3
"""BOM mapping coverage: every row needs footprint, MPN and LCSC C-number.

EasyEDA's BOM export (``easycirq bom export --type csv``) is a tab-separated
table. This checker reads the exported file (never EDA) and reports which rows
cannot be ordered as-is:

  * ``footprint``  empty            -> cannot place / manufacture
  * ``mpn``        empty            -> no authoritative part
  * ``lcsc``       empty or not C*  -> not directly orderable at LCSC

One row counts once in ``bom_mapping_missing`` even if several columns are
empty; the per-column findings say which column(s) failed.

Exit codes: 0 = complete, 1 = missing mapping, 2 = invalid/unreadable input.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

SCHEMA = "easycirq-sch-bom-check/v1"
COLUMNS = {
    "designator": ("designator", "ref", "reference"),
    "footprint": ("footprint", "package"),
    "mpn": ("manufacturer part", "mpn", "part number", "comment"),
    "lcsc": ("supplier part", "lcsc", "lcsc part", "cnumber"),
    "quantity": ("quantity", "qty"),
}
LCSC = re.compile(r"^C\d{4,12}$")


def _read_text(path):
    with open(path, "rb") as stream:
        raw = stream.read(4_000_001)
    if len(raw) >= 4_000_000:
        raise ValueError(f"{path}: input exceeds 4 MB")
    for encoding in ("utf-8-sig", "utf-16", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"{path}: cannot decode")


def _detect(text):
    first = text.splitlines()[0] if text.strip() else ""
    delimiter = "\t" if first.count("\t") >= first.count(",") else ","
    return delimiter


def _index(header):
    lowered = [cell.strip().lower() for cell in header]
    index = {}
    for key, names in COLUMNS.items():
        for position, cell in enumerate(lowered):
            if cell in names:
                index[key] = position
                break
    return index


def analyze(text):
    delimiter = _detect(text)
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    rows = [row for row in reader if any(cell.strip() for cell in row)]
    if not rows:
        raise ValueError("BOM file has no rows")
    index = _index(rows[0])
    missing_columns = [key for key in ("designator", "footprint", "mpn", "lcsc")
                       if key not in index]
    if missing_columns:
        return {
            "schema": SCHEMA, "tool": "sch_bom_metrics.py",
            "verdict": "unknown",
            "metrics": {"bom_mapping_missing": None},
            "findings": [{"severity": "warning", "code": "bom_columns_missing",
                          "message": f"缺少列: {missing_columns}"}],
            "note": "无法识别 BOM 列，按缺证据处理",
        }

    findings, bad_rows = [], 0
    for row in rows[1:]:
        def cell(key):
            position = index.get(key)
            if position is None or position >= len(row):
                return ""
            return row[position].strip()

        designator = cell("designator") or "?"
        problems = []
        if not cell("footprint"):
            problems.append(("footprint_missing", "封装为空"))
        if not cell("mpn"):
            problems.append(("mpn_missing", "型号为空"))
        lcsc = cell("lcsc")
        if not lcsc:
            problems.append(("lcsc_missing", "C 号为空"))
        elif not LCSC.match(lcsc):
            problems.append(("lcsc_invalid", f"供应商料号 {lcsc} 不是 C 号"))
        if not problems:
            continue
        bad_rows += 1
        for code, message in problems:
            findings.append({"severity": "error", "code": code,
                             "message": f"{designator}: {message}"})

    return {
        "schema": SCHEMA,
        "tool": "sch_bom_metrics.py",
        "verdict": "fail" if bad_rows else "pass",
        "metrics": {"bom_mapping_missing": bad_rows,
                    "bom_rows": len(rows) - 1},
        "findings": findings,
        "note": "按行计：同一位号多列缺失只计一次；空表头列视为无法识别",
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="BOM export -> KPI bom_map check")
    ap.add_argument("bom", help="easycirq bom export CSV/TSV file")
    ap.add_argument("--out", help="write the check report here")
    ap.add_argument("--json", action="store_true", help="print the report")
    ap.add_argument("--quiet", action="store_true", help="summary line only")
    args = ap.parse_args(argv)

    try:
        report = analyze(_read_text(args.bom))
    except (OSError, ValueError) as exc:
        print(f"sch_bom_metrics: {exc}", file=sys.stderr)
        return 2

    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    if args.json:
        print(text)
    elif not args.quiet:
        print(f"bom: verdict={report['verdict']} metrics={report['metrics']}")
        for finding in report["findings"][:20]:
            print(f"  - {finding['message']}")
    if report["verdict"] == "unknown":
        return 2
    return 1 if report["verdict"] == "fail" else 0


if __name__ == "__main__":
    sys.exit(main())
