#!/usr/bin/env python3
"""Offline batch layout planner: enumerate block combinations, plan and score.

No EDA access. Uses the measured envelope table, plans every requested
combination, and ranks the results so only the best candidates go to the live
EDA acceptance run.

Usage:
    python sch_layout_batch.py --pool all --sizes 2,3 --top 10
    python sch_layout_batch.py --pool block.es8311_codec_i2s,block.aw8737_classd_spk --sizes 2

Exit: 0 if at least one plan passes, 2 otherwise.
"""
from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import sch_layout_plan as planner  # noqa: E402

SCHEMA = "easycirq-sch-layout-batch/v1"


def short_title(block_id):
    return block_id.split(".", 1)[-1]


def build_spec(blocks, envelope_table, page, title_block):
    return {
        "schema": "easycirq-sch-layout-plan/v1",
        "page": page,
        "titleBlock": title_block,
        "blocks": [{"id": b, "title": short_title(b)} for b in blocks],
    }


def run(pool, sizes, envelope_data, top, page=None, title_block=None):
    envelopes = envelope_data["blocks"]
    page = page or envelope_data.get("page") or {}
    page = {"width": page.get("width", 1170), "height": page.get("height", 825),
            "margin": page.get("margin", 12)}
    title_block = title_block or envelope_data.get("page", {}).get("title_block")

    results = []
    for size in sizes:
        for combo in itertools.combinations(pool, size):
            spec = build_spec(combo, envelopes, page, title_block)
            try:
                rep = planner.plan(spec, envelopes)
            except ValueError as exc:
                results.append({"blocks": list(combo), "verdict": "blocked", "score": 0,
                                "metrics": {}, "error": str(exc)})
                continue
            results.append({"blocks": list(combo), "verdict": rep["verdict"],
                            "score": rep["metrics"].get("score", 0),
                            "metrics": {k: rep["metrics"][k] for k in
                                        ("fits", "overlaps", "area_usage", "zone_slack",
                                         "title_clearance_violations")},
                            "unplaced": rep["unplaced"]})
    results.sort(key=lambda r: (r["verdict"] == "pass", r["score"]), reverse=True)
    return {
        "schema": SCHEMA,
        "pool_size": len(pool),
        "sizes": sizes,
        "evaluated": len(results),
        "passed": sum(1 for r in results if r["verdict"] == "pass"),
        "results": results,
        "top": results[:top],
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="Offline batch layout planner + score")
    ap.add_argument("--pool", default="all",
                    help="comma-separated block ids, or 'all' for the envelope table")
    ap.add_argument("--sizes", default="2,3", help="combination sizes, e.g. 2,3,4")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--envelopes")
    ap.add_argument("--out", help="write the ranked JSON here")
    args = ap.parse_args(argv)

    envelope_data = json.loads(
        Path(args.envelopes or planner.DEFAULT_ENVELOPES).read_text(encoding="utf-8"))
    all_ids = list(envelope_data["blocks"])
    pool = all_ids if args.pool == "all" else [p.strip() for p in args.pool.split(",") if p.strip()]
    unknown = [p for p in pool if p not in envelope_data["blocks"]]
    if unknown:
        print("unknown blocks (no measured envelope): %s" % ", ".join(unknown), file=sys.stderr)
    pool = [p for p in pool if p in envelope_data["blocks"]]
    sizes = [int(s) for s in args.sizes.split(",") if s.strip()]

    report = run(pool, sizes, envelope_data, args.top)
    out = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        Path(args.out).write_text(out, encoding="utf-8", newline="\n")
    sys.stdout.write(out)
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
