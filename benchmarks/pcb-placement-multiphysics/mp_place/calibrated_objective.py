"""P2.20: use a few-shot-calibrated surrogate as the downstream layout objective.

Reuses the P2.18 template surrogate and its fine-tune calibration on k=16 real
board samples.  Then three objectives (proxy, uncalibrated template surrogate,
calibrated) are each given to solver_v2 on every real board and the resulting
placements are scored by the hidden physics-v2 truth + the offline router.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import time
from typing import Dict, List, Optional, Sequence, Tuple

from . import transfer, transfer_calib
from .features_v2 import extract_features_v2, feature_vector_v2
from .model import Placement, Scenario, hard_violations
from .objective import ProxyObjective, RidgeModel
from .physics_v2 import PhysicsSimulatorV2
from .router import GridRouter
from .solver_v2 import solve

OUT_DIR = pathlib.Path(__file__).resolve().parent.parent
K_CALIB = 16


class _SurrogateObjective:
    name = "template_surrogate"

    def __init__(self, scenario: Scenario, model: RidgeModel):
        self.scenario = scenario
        self.model = model

    def cost(self, pl: Placement) -> float:
        return self.model.predict(feature_vector_v2(extract_features_v2(self.scenario, pl)))


class CalibratedObjective:
    name = "calibrated"

    def __init__(self, scenario: Scenario, fine_model: RidgeModel, keep: Tuple[int, ...], transfer_model: RidgeModel):
        self.scenario = scenario
        self.fine_model = fine_model
        self.keep = keep
        self.transfer_model = transfer_model

    def cost(self, pl: Placement) -> float:
        x = feature_vector_v2(extract_features_v2(self.scenario, pl))
        tp = self.transfer_model.predict(x)
        row = x + [tp]
        return self.fine_model.predict([row[i] for i in self.keep])


def _template_model(seed: int = 0) -> RidgeModel:
    _x10, x40, y = transfer._sample_templates(transfer.SAMPLES_PER_TEMPLATE, seed=seed)
    return RidgeModel(lam=1e-2).fit(x40, y)


def _board_objectives(converted, model40: RidgeModel, k: int = K_CALIB, seed: int = 0):
    sc = converted.scenario
    _x10b, x40b, yb = transfer._sample_board(converted, transfer.SAMPLES_PER_BOARD, seed=seed)
    pred_cal = [model40.predict(x) for x in x40b[:k]]
    fitted = transfer_calib._fit_fine_tune(x40b[:k], yb[:k], pred_cal)
    proxy = ProxyObjective(sc)
    surrogate = _SurrogateObjective(sc, model40)
    calibrated = CalibratedObjective(sc, fitted[0], fitted[1], model40)
    return proxy, surrogate, calibrated


def run(quick: bool = False, seeds: Sequence[int] = (0, 1), steps: int = 800) -> Dict:
    boards, missing = transfer_calib.load_real_boards()
    if quick:
        boards = boards[:2]
        seeds = seeds[:1]
        steps = 200
    model40 = _template_model(seed=0)
    started = time.time()
    rows: List[Dict] = []
    for board in boards:
        converted = board["converted"]
        sc = converted.scenario
        sim = PhysicsSimulatorV2(sc, seed=0)
        router = GridRouter(sc, grid_mm=1.0, layers=2)
        for seed in seeds:
            objs = _board_objectives(converted, model40, k=K_CALIB, seed=seed)
            for obj in objs:
                pl, _cost, stats = solve(sc, obj.cost, seed=seed, steps=steps)
                truth = sim.score(pl)
                route = router.route(pl)
                rows.append(
                    {
                        "board": board["board"],
                        "seed": seed,
                        "objective": obj.name,
                        "truth_v2": round(truth, 4),
                        "completion": round(route.completion, 4),
                        "feasible": not hard_violations(sc, pl),
                        "runtime_s": round(stats.get("runtime_s", 0.0), 3),
                    }
                )
                print(
                    f"[calib-obj] {board['board']} seed={seed} {obj.name}: "
                    f"truth={truth:.3f} comp={route.completion:.3f} feasible={not hard_violations(sc, pl)}"
                )
    agg = _aggregate(rows, boards)
    return {
        "config": {"quick": quick, "seeds": list(seeds), "steps": steps, "k": K_CALIB, "boards": [b["board"] for b in boards], "missing": missing},
        "rows": rows,
        "aggregate": agg,
        "runtime_s": round(time.time() - started, 2),
    }


def _aggregate(rows: List[Dict], boards) -> Dict:
    per_obj: Dict[str, List] = {"multiphysics_proxy": [], "template_surrogate": [], "calibrated": []}
    for r in rows:
        per_obj[r["objective"]].append(r)
    out = {}
    for name, rs in per_obj.items():
        if not rs:
            continue
        out[name] = {
            "n": len(rs),
            "truth_v2": round(sum(x["truth_v2"] for x in rs) / len(rs), 4),
            "completion": round(sum(x["completion"] for x in rs) / len(rs), 4),
            "all_feasible": all(x["feasible"] for x in rs),
        }
    return out


def write_report(data: Dict, out_dir: pathlib.Path = OUT_DIR) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report_calibrated_objective.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    agg = data["aggregate"]
    lines = ["# P2.20：校准目标接入下游布局优化\n"]
    lines.append(f"- 运行：{data['runtime_s']} s；板 {data['config']['boards']}；seeds {data['config']['seeds']}；校准 k={data['config']['k']}\n")
    lines.append("## 汇总（最终布局，越低 truth 越好）\n")
    lines.append("| 目标 | truth_v2 | router completion | 硬可行 |")
    lines.append("|---|---|---|---|")
    for name in ("multiphysics_proxy", "template_surrogate", "calibrated"):
        if name not in agg:
            continue
        a = agg[name]
        lines.append(f"| {name} | {a['truth_v2']} | {a['completion']} | {a['all_feasible']} |")
    lines.append("\n## 结论\n")
    if "calibrated" in agg and "multiphysics_proxy" in agg:
        if agg["calibrated"]["truth_v2"] < agg["multiphysics_proxy"]["truth_v2"]:
            lines.append("- calibrated 在最终 truth 上优于 proxy（更接近真实物理）。")
        else:
            lines.append("- calibrated 未在最终 truth 上优于 proxy（可能 k 太小或代理结构有限）。")
    lines.append("- 边界：truth 为离线伪物理模型；router 为 1mm/2层离线 oracle；真实 DRC/布线/SI-PI/热 `NOT RUN`。")
    (out_dir / "report_calibrated_objective.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"[calib-obj] wrote {out_dir / 'report_calibrated_objective.md'} / report_calibrated_objective.json")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Calibrated-objective downstream experiment")
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--seeds", default="0,1")
    parser.add_argument("--steps", type=int, default=800)
    parser.add_argument("--out", default=str(OUT_DIR))
    args = parser.parse_args(argv)
    seeds = [int(s) for s in args.seeds.split(",") if s.strip()]
    write_report(run(quick=args.quick, seeds=seeds, steps=args.steps), pathlib.Path(args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
