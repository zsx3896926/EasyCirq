"""P2+ integration experiment: v1 vs v2 physics, surrogate, router, portfolio solver.

This script is the Lead-owned integration harness.  It degrades gracefully while
parallel modules are still landing: missing modules are reported as NOT RUN
instead of crashing, so the same command can be used for regression at any time.

    python -m mp_place.experiment_v2            # full
    python -m mp_place.experiment_v2 --quick    # smoke
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import random
import time
from typing import Dict, List, Optional, Sequence

from .features import FEATURE_NAMES, extract_features, feature_vector
from .model import Placement, Scenario, hard_violations
from .objective import (
    HPWLObjective,
    PhysicsSimulator,
    ProxyObjective,
    RidgeModel,
    build_dataset,
    correlation,
    r_squared,
    spearman,
)
from .scenarios import build_scenarios
from .solver import Annealer, random_feasible_placement

OUT_DIR = pathlib.Path(__file__).resolve().parent.parent


def _try_import(name: str):
    try:
        return __import__(f"mp_place.{name}", fromlist=[name])
    except Exception as exc:  # noqa: BLE001 - graceful degradation is intentional
        print(f"[v2] module {name} unavailable: {exc}")
        return None


physics_v2 = _try_import("physics_v2")
router_mod = _try_import("router")
solver_v2 = _try_import("solver_v2")
templates_mod = _try_import("templates")
intent_mod = _try_import("intent")
verify_mod = _try_import("verify")
dataset_mod = _try_import("dataset")


def _simulators(scenario: Scenario):
    sims = {"physics_v1": PhysicsSimulator(scenario, seed=0)}
    if physics_v2 is not None:
        sims["physics_v2"] = physics_v2.PhysicsSimulatorV2(scenario, seed=0)
    return sims


def _sample(scenario: Scenario, n: int, seed: int) -> List[Placement]:
    if dataset_mod is not None:
        return dataset_mod.sample_layouts(scenario, None, n, seed)
    rng = random.Random(seed)
    return [random_feasible_placement(scenario, rng) for _ in range(n)]


def _fit_surrogate(scenario: Scenario, sim, placements: Sequence[Placement], train_frac: float = 0.8):
    X, y = [], []
    for pl in placements:
        f = extract_features(scenario, pl)
        X.append(feature_vector(f))
        y.append(sim.score_features(f))
    cut = max(2, int(len(X) * train_frac))
    model = RidgeModel(lam=1e-2).fit(X[:cut], y[:cut])
    pred = [model.predict(x) for x in X[cut:]]
    return model, {
        "r2_test": round(r_squared(y[cut:], pred), 4),
        "spearman_test": round(spearman(y[cut:], pred), 4),
    }


def _solve(scenario: Scenario, cost, seed: int, steps: int):
    if solver_v2 is not None:
        return solver_v2.solve(scenario, cost, seed=seed, steps=steps, restarts=3)
    ann = Annealer(scenario, cost, seed=seed, steps=steps)
    best, best_cost, _trace = ann.run()
    return best, best_cost, {"solver": "annealer_v1"}


def _route(scenario: Scenario, pl: Placement) -> dict:
    if router_mod is None:
        return {"completion": None, "note": "router NOT RUN"}
    try:
        res = router_mod.GridRouter(scenario, grid_mm=1.0, layers=2).route(pl)
        return {
            "completion": round(res.completion, 4),
            "failed_nets": list(res.failed_nets),
            "wirelength_mm": round(res.wirelength_mm, 2),
            "vias": res.vias,
        }
    except Exception as exc:  # noqa: BLE001
        return {"completion": None, "note": f"router error: {exc}"}


def _verify(scenario: Scenario, pl: Placement) -> dict:
    if verify_mod is not None:
        try:
            return verify_mod.verify_placement(scenario, pl)
        except Exception as exc:  # noqa: BLE001
            return {"feasible": not hard_violations(scenario, pl), "note": f"verify error: {exc}"}
    return {"feasible": not hard_violations(scenario, pl), "note": "verify module NOT RUN"}


def _scenario_pool(seed: int) -> List[Scenario]:
    scenarios = build_scenarios(seed=seed)
    if templates_mod is None:
        return scenarios
    out = []
    for sc in scenarios:
        try:
            tpl = templates_mod.instantiate(sc.name, seed=seed)
            out.append(tpl)
        except Exception as exc:  # noqa: BLE001
            print(f"[v2] template {sc.name} failed ({exc}); using base scenario")
            out.append(sc)
    return out


def run(quick: bool = False, seed: int = 0) -> Dict:
    n_samples = 160 if quick else 300
    steps = 500 if quick else 1200
    seeds = (0,) if quick else (0, 1)
    scenarios = _scenario_pool(seed)
    started = time.time()
    data: Dict = {"config": {"quick": quick, "samples": n_samples, "steps": steps, "seeds": list(seeds)}, "scenarios": []}

    for sc in scenarios:
        sims = _simulators(sc)
        placements = _sample(sc, n_samples, seed + 1)
        row: Dict = {"scenario": sc.name, "components": len(sc.components), "nets": len(sc.nets),
                     "simulators": list(sims.keys()), "objectives": {}}

        for sim_name, sim in sims.items():
            model, fit = _fit_surrogate(sc, sim, placements)
            row[f"surrogate_{sim_name}"] = fit
            obj_specs = [
                ("hpwl", HPWLObjective(sc).cost),
                ("multiphysics_proxy", ProxyObjective(sc).cost),
                (f"surrogate_{sim_name}", lambda pl, m=model: m.predict(feature_vector(extract_features(sc, pl)))),
                (f"oracle_{sim_name}", sim.score),
            ]
            candidate_seeds = list(seeds) + [s for s in (2,) if s not in seeds and not quick]
            for obj_name, cost in obj_specs:
                truths, hpwls, comps, times, viol, solvers = [], [], [], [], [], set()
                candidates = []
                for sd in candidate_seeds:
                    t0 = time.time()
                    best, _c, stats = _solve(sc, cost, seed=sd, steps=steps)
                    elapsed = time.time() - t0
                    solvers.add(stats.get("solver", "?"))
                    truth = round(sim.score(best), 4)
                    completion = _route(sc, best).get("completion")
                    candidates.append({"seed": sd, "truth": truth, "completion": completion,
                                       "placement": best, "elapsed": round(elapsed, 3)})
                    if sd not in seeds:
                        continue
                    times.append(elapsed)
                    viol.append(len(hard_violations(sc, best)))
                    truths.append(truth)
                    hpwls.append(round(extract_features(sc, best)["hpwl"], 4))
                    comps.append(completion)
                key = f"{obj_name}__{sim_name}"
                # Route-aware selection: among all candidates pick highest router
                # completion, then lowest truth.  This is the P4 "verifier gate"
                # preview: the objective itself does not know about routability.
                route_sel = max(
                    candidates,
                    key=lambda c: (c["completion"] if c["completion"] is not None else -1.0, -c["truth"]),
                )
                row["objectives"][key] = {
                    "mean_truth": round(sum(truths) / len(truths), 4),
                    "std_truth": round(_std(truths), 4),
                    "mean_hpwl": round(sum(hpwls) / len(hpwls), 4),
                    "router_completion": comps,
                    "max_violations": max(viol),
                    "mean_runtime_s": round(sum(times) / len(times), 3),
                    "solver": sorted(solvers),
                    "candidates": [
                        {"seed": c["seed"], "truth": c["truth"], "completion": c["completion"]}
                        for c in candidates
                    ],
                    "route_selected": {
                        "seed": route_sel["seed"],
                        "truth": route_sel["truth"],
                        "completion": route_sel["completion"],
                    },
                }
        data["scenarios"].append(row)
        keys = [k for k in row["objectives"] if k.startswith("hpwl") or k.startswith("multiphysics")]
        summary = ", ".join(f"{k}->{row['objectives'][k]['mean_truth']}" for k in keys)
        print(f"[v2] {sc.name}: {summary}")

    data["aggregate"] = _aggregate(data)
    data["runtime_s"] = round(time.time() - started, 2)
    return data


def _std(xs: Sequence[float]) -> float:
    if not xs:
        return 0.0
    m = sum(xs) / len(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / len(xs))


def _aggregate(data: Dict) -> Dict:
    sums: Dict[str, List[float]] = {}
    for row in data["scenarios"]:
        for key, val in row["objectives"].items():
            sums.setdefault(key, []).append(val["mean_truth"])
    agg = {key: {"n": len(vals), "mean": round(sum(vals) / len(vals), 4)} for key, vals in sums.items()}
    # improvement vs the HPWL objective under the same truth model
    for key, val in agg.items():
        if key.startswith("hpwl__"):
            continue
        truth = key.rsplit("__", 1)[-1] if "__" in key else ""
        base = agg.get(f"hpwl__{truth}", {}).get("mean")
        if base:
            val["improvement_vs_hpwl_pct"] = round(100.0 * (base - val["mean"]) / base, 2)
    return agg


def write_report(data: Dict, out_dir: pathlib.Path = OUT_DIR) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report_v2.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# P2 集成实验（Lead 回归）\n", f"- 运行时：{data['runtime_s']} s；配置：{data['config']}\n"]
    lines.append("## 各场景目标 -> 真值（v1 伪物理 / v2 物理感）\n")
    for row in data["scenarios"]:
        lines.append(f"### {row['scenario']}（{row['components']} 器件 / {row['nets']} 网）\n")
        for key, val in row["objectives"].items():
            rs = val.get("route_selected", {})
            lines.append(
                f"- `{key}`：truth={val['mean_truth']} (sd {val['std_truth']})，"
                f"hpwl={val['mean_hpwl']}，router={val['router_completion']}，"
                f"viol={val['max_violations']}，t={val['mean_runtime_s']}s，solver={val['solver']}，"
                f"route_selected={{seed:{rs.get('seed')},truth:{rs.get('truth')},completion:{rs.get('completion')}}}"
            )
        lines.append("")
    lines.append("## 汇总\n")
    for key, val in data["aggregate"].items():
        imp = f"，比 HPWL 好 {val['improvement_vs_hpwl_pct']}%" if "improvement_vs_hpwl_pct" in val else ""
        lines.append(f"- `{key}`：mean truth = {val['mean']}（n={val['n']}）{imp}")
    lines.append("\n> 边界：伪物理/物理感仿真，无真实 DRC/布线；`routing_verified:false`、`drc:NOT RUN`。")
    (out_dir / "report_v2.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"[v2] wrote {out_dir / 'report_v2.md'} / report_v2.json")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="P2 integration experiment")
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", default=str(OUT_DIR))
    args = parser.parse_args(argv)
    write_report(run(quick=args.quick, seed=args.seed), pathlib.Path(args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
