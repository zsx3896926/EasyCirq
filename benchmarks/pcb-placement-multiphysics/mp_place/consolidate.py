"""P4.12: consolidate every report*.json / docs/*.json into one overview table."""

from __future__ import annotations

import argparse
import json
import pathlib
from typing import Any, Dict, List, Optional, Sequence

OUT_DIR = pathlib.Path(__file__).resolve().parent.parent


def _dig(obj: Any, keys: Sequence[str]) -> Optional[Any]:
    cur = obj
    for k in keys:
        if isinstance(cur, dict) and k in cur:
            cur = cur[k]
        else:
            return None
    return cur


def _metric_line(data: Dict) -> str:
    parts = []
    for key in ("runtime_s", "total_runtime_s"):
        v = data.get(key)
        if isinstance(v, (int, float)):
            parts.append(f"runtime={round(v, 1)}s")
            break
    agg = data.get("aggregate")
    if isinstance(agg, dict):
        if "mean_truth_by_objective" in agg:
            m = agg["mean_truth_by_objective"]
            parts.append("truth=" + str(m)[:60])
        if "truth_v2_repair_mean" in agg:
            parts.append(f"repair_truth={agg['truth_v2_repair_mean']}")
        if "pass_rate" in agg:
            parts.append(f"pass={agg['pass_rate']}")
        if "win_rate" in agg:
            parts.append(f"win={agg['win_rate']}")
    schema = data.get("schema")
    if schema:
        parts.append(f"schema={schema}")
    return "; ".join(parts) if parts else "(no summary keys)"


def collect(root: pathlib.Path = OUT_DIR) -> List[Dict]:
    files = sorted(list(root.glob("report_*.json")) + list(root.glob("docs/*.json")))
    rows = []
    for path in files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            rows.append({"report": path.name, "schema": None, "summary": f"unreadable: {type(exc).__name__}"})
            continue
        rows.append({"report": path.name, "schema": data.get("schema"), "summary": _metric_line(data)})
    return rows


def write_markdown(rows: List[Dict], out: pathlib.Path = OUT_DIR / "docs" / "CONSOLIDATED.md") -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# 报告合并总表（自动生成）\n", f"- 共 {len(rows)} 份 report*.json / docs/*.json\n"]
    lines.append("| 报告 | schema | 关键指标摘要 |")
    lines.append("|---|---|---|")
    for r in rows:
        lines.append(f"| {r['report']} | {r.get('schema') or '-'} | {r['summary']} |")
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"[consolidate] wrote {out} ({len(rows)} reports)")


def unreadable_reports(rows: List[Dict]) -> List[str]:
    return [r["report"] for r in rows if r.get("summary", "").startswith("unreadable")]


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Consolidate report JSONs into one table")
    parser.add_argument("--root", default=str(OUT_DIR))
    parser.add_argument("--out", default=str(OUT_DIR / "docs" / "CONSOLIDATED.md"))
    parser.add_argument("--check", action="store_true", help="exit 1 if any report is unreadable")
    args = parser.parse_args(argv)
    rows = collect(pathlib.Path(args.root))
    write_markdown(rows, pathlib.Path(args.out))
    if args.check:
        bad = unreadable_reports(rows)
        if bad:
            print(f"[consolidate] UNREADABLE: {bad}")
            return 1
        print("[consolidate] check: all reports readable")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
