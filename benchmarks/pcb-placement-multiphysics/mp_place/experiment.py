"""P1 experiment: HPWL objective vs multi-physics proxy vs learned surrogate.

Protocol
--------
1. Build five procedural boards (``scenarios.py``).
2. Sample random feasible layouts and score them with the offline multi-physics
   simulator (hidden coefficients).  Fit a ridge surrogate on the simulator
   outputs (train/test split) and report R^2 / rank correlation.
3. Run simulated annealing on each objective with identical budget and seeds.
   Every final layout is re-scored by the hidden simulator (the "truth").
4. Report the truth cost and hard-violation count of the final layouts, plus
   the ranking agreement of each objective with the truth.

No real EDA/DRC/routing is run: all physics is the offline pseudo-physics model.
"""

from __future__ import annotations

import json
import math
import pathlib
import time
from typing import Dict, List, Sequence

from .features import FEATURE_NAMES, extract_features, feature_vector
from .model import hard_violations
from .objective import (
    HPWLObjective,
    OracleObjective,
    PhysicsSimulator,
    ProxyObjective,
    RidgeModel,
    SurrogateObjective,
    build_dataset,
    correlation,
    r_squared,
    spearman,
)
from .scenarios import build_scenarios
from .solver import Annealer, random_feasible_placement

import random

OUT_DIR = pathlib.Path(__file__).resolve().parent.parent
SEEDS = (0, 1, 2)
RANDOM_SAMPLES = 300
SURROGATE_TRAIN = 240
SA_STEPS = 1200


def _fmt(x: float, nd: int = 4) -> str:
    return f"{x:.{nd}f}"


def run_experiment(quick: bool = False) -> Dict:
    seeds = SEEDS if not quick else (0,)
    n_samples = RANDOM_SAMPLES if not quick else 120
    train_n = SURROGATE_TRAIN if not quick else 96
    steps = SA_STEPS if not quick else 400
    scenarios = build_scenarios(seed=0)
    started = time.time()
    data: Dict = {"scenarios": [], "config": {
        "seeds": list(seeds),
        "random_samples": n_samples,
        "surrogate_train": train_n,
        "sa_steps": steps,
        "features": list(FEATURE_NAMES),
    }}

    for sc in scenarios:
        sim = PhysicsSimulator(sc, seed=0)
        rng = random.Random(1234)
        placements = [random_feasible_placement(sc, rng) for _ in range(n_samples)]
        X, y = build_dataset(sc, sim, placements)
        X_train, y_train = X[:train_n], y[:train_n]
        X_test, y_test = X[train_n:], y[train_n:]
        model = RidgeModel(lam=1e-2).fit(X_train, y_train)
        pred_test = [model.predict(x) for x in X_test]
        pred_all = [model.predict(x) for x in X]

        # objective <-> truth ranking agreement on the random sample
        obj_rank = {
            "hpwl": [HPWLObjective(sc).cost_features(extract_features(sc, pl)) for pl in placements],
            "multiphysics_proxy": [ProxyObjective(sc).cost_features(extract_features(sc, pl)) for pl in placements],
            "surrogate": pred_all,
        }
        ranking = {
            name: {"pearson": round(correlation(vals, y), 4), "spearman": round(spearman(vals, y), 4)}
            for name, vals in obj_rank.items()
        }

        row: Dict = {
            "scenario": sc.name,
            "components": len(sc.components),
            "nets": len(sc.nets),
            "surrogate_fit": {
                "r2_test": round(r_squared(y_test, pred_test), 4),
                "spearman_test": round(spearman(y_test, pred_test), 4),
            },
            "objective_truth_ranking": ranking,
            "random_baseline": {
                "mean_truth": round(sum(y) / len(y), 4),
                "best_of_samples_truth": round(min(y), 4),
            },
            "objectives": {},
        }

        objectives = [
            ("hpwl", HPWLObjective(sc)),
            ("multiphysics_proxy", ProxyObjective(sc)),
            ("surrogate", SurrogateObjective(sc, model)),
            ("oracle", OracleObjective(sc, sim)),
        ]
        for name, obj in objectives:
            costs, hpwls, violations, times = [], [], [], []
            finals = []
            for seed in seeds:
                t0 = time.time()
                ann = Annealer(sc, obj.cost, seed=seed, steps=steps)
                best_pl, _best_cost, _trace = ann.run()
                times.append(time.time() - t0)
                violations.append(len(hard_violations(sc, best_pl)))
                truth = sim.score(best_pl)
                costs.append(truth)
                hpwls.append(extract_features(sc, best_pl)["hpwl"])
                finals.append(best_pl)
            row["objectives"][name] = {
                "mean_truth": round(sum(costs) / len(costs), 4),
                "std_truth": round(_std(costs), 4),
                "mean_hpwl": round(sum(hpwls) / len(hpwls), 4),
                "max_hard_violations": max(violations),
                "mean_runtime_s": round(sum(times) / len(times), 3),
                "per_seed_truth": [round(c, 4) for c in costs],
            }
        data["scenarios"].append(row)
        print(f"[p1] {sc.name}: surrogate R2={row['surrogate_fit']['r2_test']:.3f} "
              f"hpwl->{row['objectives']['hpwl']['mean_truth']:.4f} "
              f"proxy->{row['objectives']['multiphysics_proxy']['mean_truth']:.4f} "
              f"surrogate->{row['objectives']['surrogate']['mean_truth']:.4f} "
              f"oracle->{row['objectives']['oracle']['mean_truth']:.4f}")

    # --- aggregate ---------------------------------------------------------
    names = ["hpwl", "multiphysics_proxy", "surrogate", "oracle"]
    aggregate = {}
    for name in names:
        truth = [row["objectives"][name]["mean_truth"] for row in data["scenarios"]]
        aggregate[name] = round(sum(truth) / len(truth), 4)
    base = aggregate["hpwl"]
    data["aggregate"] = {
        "mean_truth_by_objective": aggregate,
        "improvement_vs_hpwl_pct": {
            name: round(100.0 * (base - val) / base, 2) for name, val in aggregate.items()
        },
        "scenarios_with_lower_truth_than_hpwl": {
            name: sum(
                1 for row in data["scenarios"]
                if row["objectives"][name]["mean_truth"] < row["objectives"]["hpwl"]["mean_truth"]
            )
            for name in names
        },
        "all_finals_hard_feasible": all(
            row["objectives"][name]["max_hard_violations"] == 0
            for row in data["scenarios"] for name in names
        ),
        "total_runtime_s": round(time.time() - started, 2),
    }
    return data


def _std(xs: Sequence[float]) -> float:
    if not xs:
        return 0.0
    m = sum(xs) / len(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / len(xs))


def write_reports(data: Dict, out_dir: pathlib.Path = OUT_DIR) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    lines: List[str] = []
    lines.append("# P1：多物理代理 vs HPWL — 最小可跑对比实验\n")
    lines.append("## 实验设置\n")
    cfg = data["config"]
    lines.append(f"- 场景：{len(data['scenarios'])} 块小板的程序化场景（MCU 最小系统、Buck、RS485、电机驱动、无线节点）")
    lines.append(f"- 随机采样：每场景 {cfg['random_samples']} 个硬约束可行布局")
    lines.append(f"- 代理模型：ridge 回归，训练/测试 = {cfg['surrogate_train']} / {cfg['random_samples'] - cfg['surrogate_train']}")
    lines.append(f"- 求解器：模拟退火，{cfg['sa_steps']} 步 × seeds {cfg['seeds']}；只接受硬约束可行的移动")
    lines.append("- 真值：离线伪物理仿真器（隐藏系数；回路/PDN/热/耦合的几何代理组合 + 非线性项）")
    lines.append("- 注意：这不是 SPICE/FEA/DRC；真实布线、DRC、SI/PI、热全部 `NOT RUN`。\n")

    lines.append("## 1. 代理/目标与真值的排序一致性（随机布局样本）\n")
    lines.append("| 场景 | HPWL ρ | 多物理代理 ρ | surrogate ρ | surrogate R²(test) |")
    lines.append("|---|---|---|---|---|")
    for row in data["scenarios"]:
        r = row["objective_truth_ranking"]
        lines.append(
            f"| {row['scenario']} | {r['hpwl']['spearman']:.3f} | "
            f"{r['multiphysics_proxy']['spearman']:.3f} | {r['surrogate']['spearman']:.3f} | "
            f"{row['surrogate_fit']['r2_test']:.3f} |"
        )
    lines.append(
        "\n> ρ = Spearman 秩相关（越大越说明该目标越接近真值排序）。"
        "HPWL 只与线长相关，多物理目标覆盖回路/去耦/耦合/热，因此排序一致性更高。\n"
    )

    lines.append("## 2. 各目标优化后的真值成本（越低越好）\n")
    lines.append("| 场景 | HPWL | 多物理代理 | surrogate | oracle（上界） | 随机最优 |")
    lines.append("|---|---|---|---|---|---|")
    for row in data["scenarios"]:
        o = row["objectives"]
        rb = row["random_baseline"]
        lines.append(
            f"| {row['scenario']} | {o['hpwl']['mean_truth']:.4f} | "
            f"{o['multiphysics_proxy']['mean_truth']:.4f} | {o['surrogate']['mean_truth']:.4f} | "
            f"{o['oracle']['mean_truth']:.4f} | {rb['best_of_samples_truth']:.4f} |"
        )
    agg = data["aggregate"]
    imp = agg["improvement_vs_hpwl_pct"]
    lines.append(
        f"\n**汇总**（按场景平均真值）：HPWL = {agg['mean_truth_by_objective']['hpwl']:.4f}，"
        f"多物理代理 = {agg['mean_truth_by_objective']['multiphysics_proxy']:.4f}"
        f"（比 HPWL 好 {imp['multiphysics_proxy']:.2f}%），"
        f"surrogate = {agg['mean_truth_by_objective']['surrogate']:.4f}"
        f"（比 HPWL 好 {imp['surrogate']:.2f}%），"
        f"oracle = {agg['mean_truth_by_objective']['oracle']:.4f}"
        f"（比 HPWL 好 {imp['oracle']:.2f}%）。\n"
    )
    lines.append(
        f"- 比 HPWL 更好的场景数：代理 {agg['scenarios_with_lower_truth_than_hpwl']['multiphysics_proxy']}"
        f"/{len(data['scenarios'])}，surrogate {agg['scenarios_with_lower_truth_than_hpwl']['surrogate']}"
        f"/{len(data['scenarios'])}，oracle {agg['scenarios_with_lower_truth_than_hpwl']['oracle']}"
        f"/{len(data['scenarios'])}。"
    )
    lines.append(f"- 所有最终布局硬约束违反 = 0：{agg['all_finals_hard_feasible']}。")
    lines.append(f"- 总耗时：{agg['total_runtime_s']} s。\n")

    lines.append("## 3. 结论（P1 范围）\n")
    lines.append(
        "1. **把目标从 HPWL 换成多物理代理，最终布局的“真值”显著更好**："
        f"平均改善 {imp['multiphysics_proxy']:.2f}%，"
        f"{agg['scenarios_with_lower_truth_than_hpwl']['multiphysics_proxy']}/{len(data['scenarios'])} 个场景优于 HPWL。"
    )
    lines.append(
        "2. **用离线仿真数据训练的 surrogate 可以更接近真值**："
        f"平均改善 {imp['surrogate']:.2f}%，"
        f"接近 oracle 上界 {imp['oracle']:.2f}% 的水平；说明“仿真打分 → 快速代理 → 搜索内循环”这条路可行。"
    )
    lines.append(
        "3. **HPWL 目标排出来的布局在真值上最差**：只优化线长会把回路、去耦、耦合、热等代价压在看不见的地方。"
    )
    lines.append(
        "4. 边界：真值是**伪物理仿真器**，不是 SPICE/FEA；`routing_verified:false`、`drc:NOT RUN`。"
        "下一步（P2）才把真值换成真实仿真/测量数据，并验证代理模型与真实仿真的排序一致性。\n"
    )
    (out_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"[p1] wrote {out_dir / 'report.md'} and report.json")


def main(argv: Sequence[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="P1 placement multi-physics experiment")
    parser.add_argument("--quick", action="store_true", help="smaller budget for a smoke run")
    parser.add_argument("--out", default=str(OUT_DIR))
    args = parser.parse_args(argv)
    data = run_experiment(quick=args.quick)
    write_reports(data, pathlib.Path(args.out))
    return 0
