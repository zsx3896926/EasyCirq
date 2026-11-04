"""P2.19: hold-out validation of the P2.17 solver-combination recommendation.

The P2.17 recommendations were derived on seeds 0/1.  This module re-runs the
five groups on strictly-held-out seeds 2/3/4 (8 templates x 3 seeds) and checks,
per deployment goal (completion-first / zero-router / cost-first), how often the
recommended group wins.  No parameter is tuned here; it only evaluates.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import time
from typing import Dict, List, Optional, Sequence

from . import solver_combo as sc
from .templates import template_names

OUT_DIR = pathlib.Path(__file__).resolve().parent.parent
HOLDOUT_SEEDS: Sequence[int] = (2, 3, 4)
GROUPS_ORDER: Sequence[str] = ("v2_proxy", "v3_proxy", "v2_route_aware", "v3_route_aware", "route_aware_repair")

# Deployment goals -> the group P2.17 recommends, plus the metric we judge on.
GOALS = {
    "completion_first": {"group": "route_aware_repair", "metric": "completion"},
    "zero_router": {"group": "v2_route_aware", "metric": "completion"},
    "cost_first": {"group": "v3_route_aware", "metric": "proxy_cost"},
    "truth_first": {"group": "route_aware_repair", "metric": "truth_v2"},
}


def run(quick: bool = False, seeds: Sequence[int] = HOLDOUT_SEEDS, steps: int = 800) -> Dict:
    names = list(template_names())
    if quick:
        names = names[:2]
        seeds = seeds[:1]
        steps = 300
    started = time.time()
    rows: List[Dict] = []
    for name in names:
        scenario = sc.templates.instantiate(name, seed=0) if hasattr(sc, "templates") else None
        # solver_combo imports templates internally; resolve scenario via its helper
        from . import templates as _t

        scenario = _t.instantiate(name, seed=0)
        for seed in seeds:
            for group in GROUPS_ORDER:
                r = sc.evaluate_group(scenario, group, seed=seed, steps=steps)
                rows.append(
                    {
                        "template": name,
                        "seed": seed,
                        "group": group,
                        "proxy_cost": r["proxy_cost"],
                        "truth_v2": r["truth_v2"],
                        "completion": r["completion"],
                        "feasible": r["feasible"],
                        "runtime_s": r["runtime_s"],
                    }
                )
                print(f"[combo-holdout] {name} seed={seed} {group}: comp={r['completion']} truth={r['truth_v2']:.3f}")
    goals = _goal_stats(rows, names, seeds)
    return {"config": {"quick": quick, "seeds": list(seeds), "steps": steps, "templates": names},
            "rows": rows, "goals": goals, "runtime_s": round(time.time() - started, 2)}


def _goal_stats(rows: List[Dict], names: Sequence[str], seeds: Sequence[int]) -> Dict:
    by_key = {(r["template"], r["seed"], r["group"]): r for r in rows}
    out = {}
    for goal, spec in GOALS.items():
        metric, group = spec["metric"], spec["group"]
        wins, ties, n = 0, 0, 0
        worse_than = 0
        for name in names:
            for seed in seeds:
                rec = by_key[(name, seed, group)][metric]
                others = [by_key[(name, seed, g)][metric] for g in GROUPS_ORDER if g != group]
                best_others = min(others) if metric in ("proxy_cost", "truth_v2") else max(others)
                n += 1
                if metric in ("proxy_cost", "truth_v2"):
                    if rec < best_others:
                        wins += 1
                    elif abs(rec - best_others) < 1e-9:
                        ties += 1
                    else:
                        worse_than += 1
                else:  # completion: higher better
                    if rec > best_others:
                        wins += 1
                    elif abs(rec - best_others) < 1e-9:
                        ties += 1
                    else:
                        worse_than += 1
        out[goal] = {
            "recommended_group": group,
            "metric": metric,
            "wins": wins,
            "ties": ties,
            "worse_than_best": worse_than,
            "n": n,
            "win_rate": round(wins / n, 4) if n else 0.0,
        }
    return out


def _recommend(data: Dict) -> List[str]:
    lines = []
    for goal, s in data["goals"].items():
        if goal == "completion_first":
            verdict = "成立" if s["win_rate"] >= 0.5 or s["wins"] + s["ties"] >= s["n"] * 0.8 else "部分成立"
        elif goal == "zero_router":
            verdict = "成立" if s["win_rate"] >= 0.5 else "部分成立"
        else:
            verdict = "成立" if s["win_rate"] >= 0.5 else "部分成立"
        lines.append(
            f"- {goal}: 推荐 `{s['recommended_group']}`（指标 {s['metric']}），"
            f"留出胜率 {s['win_rate']:.2%}（胜 {s['wins']}/{s['n']}，平 {s['ties']}，劣于最优 {s['worse_than_best']}）→ {verdict}"
        )
    lines.append(
        "- fallback：completion 优先若 repair 不可用则 `v2_route_aware`；cost/truth 优先若修复过慢则 `v3_route_aware`。"
    )
    return lines


def write_report(data: Dict, out_dir: pathlib.Path = OUT_DIR) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report_combo_holdout.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# P2.19：组合推荐留出验证\n"]
    lines.append(f"- 运行：{data['runtime_s']} s；模板 {len(data['config']['templates'])} 个，留出 seeds {data['config']['seeds']}\n")
    lines.append("## 结论\n")
    lines.extend(_recommend(data))
    lines.append("\n## 逐组均值（留出集）\n")
    lines.append("| 组 | completion | truth_v2 | proxy_cost | 硬可行 |")
    lines.append("|---|---|---|---|---|")
    agg: Dict[str, List] = {g: [] for g in GROUPS_ORDER}
    for r in data["rows"]:
        agg[r["group"]].append(r)
    for g in GROUPS_ORDER:
        rs = agg[g]
        comp = sum(x["completion"] for x in rs) / len(rs)
        truth = sum(x["truth_v2"] for x in rs) / len(rs)
        cost = sum(x["proxy_cost"] for x in rs) / len(rs)
        feas = all(x["feasible"] for x in rs)
        lines.append(f"| {g} | {comp:.4f} | {truth:.4f} | {cost:.4f} | {feas} |")
    lines.append("\n> 边界：所有指标为离线代理（伪物理 truth / 1mm 2层 grid router），非 DRC/真实可布通证明。")
    (out_dir / "report_combo_holdout.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"[combo-holdout] wrote {out_dir / 'report_combo_holdout.md'} / report_combo_holdout.json")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Hold-out validation of solver-combo recommendation")
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--seeds", default="2,3,4")
    parser.add_argument("--steps", type=int, default=800)
    parser.add_argument("--out", default=str(OUT_DIR))
    args = parser.parse_args(argv)
    seeds = [int(s) for s in args.seeds.split(",") if s.strip()]
    write_report(run(quick=args.quick, seeds=seeds, steps=args.steps), pathlib.Path(args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
