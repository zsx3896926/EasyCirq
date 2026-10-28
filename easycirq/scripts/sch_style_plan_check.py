#!/usr/bin/env python3
"""Pre-write style-plan guard for schematics (design-time, stage 0).

Checks the layout blueprint BEFORE any component/wire is written:

    easycirq-sch-style-plan/v1 = { sheet, zones, titleBlock }

It reuses sch_style_audit.py's deterministic checks (zone count/geometry,
palette, typography, title block) with ``texts=[]``. A plan that fails must not
proceed to device placement or EDA writes (contract R12, 先版式后器件).

Exit codes: 0 PASS, 1 REVIEW, 2 BLOCKED/invalid.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import sch_style_audit as style_audit  # noqa: E402

PLAN_SCHEMA = "easycirq-sch-style-plan/v1"
REPORT_SCHEMA = "easycirq-sch-style-plan-report/v1"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Pre-write schematic style-plan guard")
    ap.add_argument("plan", help="easycirq-sch-style-plan/v1 JSON")
    ap.add_argument("--tokens", help="style-tokens.json override")
    ap.add_argument("--out", help="write the JSON report here too")
    ap.add_argument("--json", action="store_true", help="print JSON (default)")
    args = ap.parse_args(argv)

    try:
        tokens = style_audit.load_tokens(args.tokens)
        plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
        if not isinstance(plan, dict) or plan.get("schema") != PLAN_SCHEMA:
            raise ValueError("schema must be %s" % PLAN_SCHEMA)
        data = {
            "schema": style_audit.INPUT_SCHEMA,
            "sheet": plan.get("sheet"),
            "zones": plan.get("zones"),
            "texts": [],
            "titleBlock": plan.get("titleBlock"),
        }
        report = style_audit.audit(data, tokens)
        report["schema"] = REPORT_SCHEMA
        report["plan"] = args.plan
    except (OSError, ValueError) as exc:
        report = {"schema": REPORT_SCHEMA, "verdict": "blocked", "score": 0,
                  "problems": [{"severity": "blocked", "message": str(exc)}],
                  "metrics": {}, "note": "invalid plan"}

    out = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        Path(args.out).write_text(out, encoding="utf-8", newline="\n")
    sys.stdout.write(out)
    return {"pass": 0, "review": 1, "blocked": 2}[report["verdict"]]


if __name__ == "__main__":
    raise SystemExit(main())
