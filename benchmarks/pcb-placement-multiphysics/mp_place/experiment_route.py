"""Route-repair comparison: pipeline (plain solver) vs pipeline + route_opt repair.

Runs all registered templates x seeds and reports hard feasibility, v2 truth,
router completion, failed nets and solver stats.  Writes report_route.md/json.

    python -m mp_place.experiment_route            # full (8 templates x 3 seeds)
    python -m mp_place.experiment_route --quick    # 2 templates x 1 seed
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import time
from typing import Dict, List, Optional, Sequence

from . import templates as templates_mod
from .pipeline import run_pipeline

OUT_DIR = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_SEEDS = (0, 1, 2)


def run(quick: bool = False, seeds: Sequence[int] = DEFAULT_SEEDS, steps: int = 800) -> Dict:
    names = list(templates_mod.template_names())
    if quick:
        names = names[:2]
        seeds = tuple(seeds[:1])
        steps = 300
    started = time.time()
    rows: List[Dict] = []
    for name in names:
        for seed in seeds:
            base = run_pipeline(name, budget_steps=steps, seed=seed, route_repair=False)
            rep = run_pipeline(name, budget_steps=steps, seed=seed, route_repair=True)
            rows.append(
                {
                    "template": name,
                    "seed": seed,
                    "baseline": _row(base),
                    "repair": _row(rep),
                    "delta_truth_v2": round(rep.get("truth_v2", 0.0) - base.get("truth_v2", 0.0), 4),
                    "delta_completion": round(
                        (rep.get("router", {}).get("completion") or 0.0)
                        - (base.get("router", {}).get("completion") or 0.0),
                        4,
                    ),
                }
            )
            print(
                f"[route] {name} seed={seed}: completion "
                f"{base['router']['completion']}->{rep['router']['completion']} "
                f"truth {base['truth_v2']:.3f}->{rep['truth_v2']:.3f}"
            )
    agg = _aggregate(rows)
    return {"config": {"quick": quick, "seeds": list(seeds), "steps": steps, "templates": names},
            "rows": rows, "aggregate": agg, "runtime_s": round(time.time() - started, 2)}


def _row(report: Dict) -> Dict:
    router = report.get("router", {})
    return {
        "feasible": bool(report.get("feasible")),
        "truth_v1": report.get("truth_v1"),
        "truth_v2": report.get("truth_v2"),
        "completion": router.get("completion"),
        "failed_nets": list(router.get("failed_nets") or []),
        "vias": router.get("vias"),
        "solver": report.get("solver"),
    }


def _aggregate(rows: List[Dict]) -> Dict:
    def mean(key: str) -> float:
        vals = [r["repair"][key] for r in rows if r["repair"].get(key) is not None]
        return round(sum(vals) / len(vals), 4) if vals else 0.0

    def mean_base(key: str) -> float:
        vals = [r["baseline"][key] for r in rows if r["baseline"].get(key) is not None]
        return round(sum(vals) / len(vals), 4) if vals else 0.0

    n = len(rows)
    fully_base = sum(1 for r in rows if r["baseline"].get("completion") == 1.0)
    fully_rep = sum(1 for r in rows if r["repair"].get("completion") == 1.0)
    return {
        "n_runs": n,
        "all_feasible": all(r["repair"]["feasible"] for r in rows),
        "completion_baseline_mean": mean_base("completion"),
        "completion_repair_mean": mean("completion"),
        "fully_routed_baseline": f"{fully_base}/{n}",
        "fully_routed_repair": f"{fully_rep}/{n}",
        "truth_v2_baseline_mean": mean_base("truth_v2"),
        "truth_v2_repair_mean": mean("truth_v2"),
        "truth_v2_improvement_pct": round(
            100.0 * (mean_base("truth_v2") - mean("truth_v2")) / mean_base("truth_v2"), 2
        )
        if mean_base("truth_v2")
        else 0.0,
        "truth_not_worse_runs": f"{sum(1 for r in rows if r['delta_truth_v2'] <= 1e-9)}/{n}",
    }


def write_report(data: Dict, out_dir: pathlib.Path = OUT_DIR) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report_route.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    agg = data["aggregate"]
    lines = ["# P2.5：可布通性入环（route-aware repair）对比\n"]
    lines.append(f"- 运行：{agg['n_runs']} 组（模板 × seed）；耗时 {data['runtime_s']} s\n")
    lines.append("## 汇总\n")
    lines.append("| 指标 | 纯求解器 pipeline | 求解器 + route repair |")
    lines.append("|---|---|---|")
    lines.append(f"| router completion 均值 | {agg['completion_baseline_mean']} | **{agg['completion_repair_mean']}** |")
    lines.append(f"| 全布通组数 | {agg['fully_routed_baseline']} | **{agg['fully_routed_repair']}** |")
    lines.append(f"| truth_v2 均值（越低越好） | {agg['truth_v2_baseline_mean']} | **{agg['truth_v2_repair_mean']}**（改善 {agg['truth_v2_improvement_pct']}%） |")
    lines.append(f"| truth 不变差的组数 | — | {agg['truth_not_worse_runs']} |")
    lines.append(f"| 全部硬可行 | — | {agg['all_feasible']} |")
    lines.append("\n## 逐模板/seed\n")
    lines.append("| 模板 | seed | completion 基线→修复 | truth_v2 基线→修复 | 失败网（修复后） |")
    lines.append("|---|---|---|---|---|")
    for r in data["rows"]:
        lines.append(
            f"| {r['template']} | {r['seed']} | {r['baseline']['completion']}→{r['repair']['completion']} | "
            f"{r['baseline']['truth_v2']}→{r['repair']['truth_v2']} | {r['repair']['failed_nets']} |"
        )
    lines.append("\n> 边界：router 是 1mm/2 层网格迷宫 oracle，不是 DRC、不是真实可布通证明；")
    lines.append("> repair 只在离线 router 下优化，真实布线/DRC/SI/PI/热仍 `NOT RUN`。")
    (out_dir / "report_route.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"[route] wrote {out_dir / 'report_route.md'} / report_route.json")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Route-repair comparison experiment")
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--seeds", default="0,1,2")
    parser.add_argument("--steps", type=int, default=800)
    parser.add_argument("--out", default=str(OUT_DIR))
    args = parser.parse_args(argv)
    seeds = [int(s) for s in args.seeds.split(",") if s.strip()]
    write_report(run(quick=args.quick, seeds=seeds, steps=args.steps), pathlib.Path(args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
