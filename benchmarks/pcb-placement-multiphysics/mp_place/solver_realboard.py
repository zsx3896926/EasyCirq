"""P2.21: solver_v3 vs solver_v2 on the real-board route_aware pipeline."""

from __future__ import annotations

import argparse
import json
import pathlib
import time
from typing import Dict, List, Optional, Sequence

from .model import hard_violations
from .objective import ProxyObjective
from .physics_v2 import PhysicsSimulatorV2
from .realboard import DEFAULT_SOURCES, load_and_convert
from .route_cost import RouteAwareObjective
from .router import GridRouter
from .solver_v2 import solve as solve_v2
from .solver_v3 import solve_v3

OUT_DIR = pathlib.Path(__file__).resolve().parent.parent


def _objectives(sc):
    base = ProxyObjective(sc)
    return base, RouteAwareObjective(sc, base=base, w_route=2.0)


def run(quick: bool = False, seeds: Sequence[int] = (0, 1), steps: int = 800) -> Dict:
    started = time.time()
    rows: List[Dict] = []
    sources = DEFAULT_SOURCES if not quick else DEFAULT_SOURCES[:2]
    for name, path in sources:
        if not pathlib.Path(path).is_file():
            continue
        converted = load_and_convert(path, name=name)
        sc = converted.scenario
        sim = PhysicsSimulatorV2(sc, seed=0)
        router = GridRouter(sc, grid_mm=1.0, layers=2)
        _base, ra_obj = _objectives(sc)
        for seed in seeds:
            for solver_name, solver_fn in (("v2", solve_v2), ("v3", solve_v3)):
                if solver_name == "v3":
                    pl, _cost, stats = solver_fn(sc, ra_obj.cost, seed=seed, steps=steps)
                else:
                    pl, _cost, stats = solver_fn(sc, ra_obj.cost, seed=seed, steps=steps)
                truth = sim.score(pl)
                route = router.route(pl)
                rows.append(
                    {
                        "board": name,
                        "seed": seed,
                        "solver": solver_name,
                        "truth_v2": round(truth, 4),
                        "completion": round(route.completion, 4),
                        "feasible": not hard_violations(sc, pl),
                        "runtime_s": round(stats.get("runtime_s", 0.0), 3),
                    }
                )
                print(f"[solver-rb] {name} seed={seed} {solver_name}: truth={truth:.3f} comp={route.completion:.3f}")
    agg = {}
    for name in ("v2", "v3"):
        rs = [r for r in rows if r["solver"] == name]
        if rs:
            agg[name] = {
                "n": len(rs),
                "truth_v2": round(sum(r["truth_v2"] for r in rs) / len(rs), 4),
                "completion": round(sum(r["completion"] for r in rs) / len(rs), 4),
                "all_feasible": all(r["feasible"] for r in rs),
            }
    return {"config": {"quick": quick, "seeds": list(seeds), "steps": steps, "boards": [r["board"] for r in rows]},
            "rows": rows, "aggregate": agg, "runtime_s": round(time.time() - started, 2)}


def write_report(data: Dict, out_dir: pathlib.Path = OUT_DIR) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report_solver_realboard.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    agg = data["aggregate"]
    lines = ["# P2.21：solver_v3 在真实板流程的对比\n"]
    lines.append(f"- 运行 {data['runtime_s']} s；板 {sorted(set(r['board'] for r in data['rows']))}\n")
    lines.append("| solver | truth_v2 | completion | 全硬可行 |")
    lines.append("|---|---|---|---|")
    for name in ("v2", "v3"):
        if name in agg:
            lines.append(f"| {name} | {agg[name]['truth_v2']} | {agg[name]['completion']} | {agg[name]['all_feasible']} |")
    lines.append("\n> 边界：伪物理 truth / 1mm 2层离线 router；真实 DRC/布线 `NOT RUN`。")
    (out_dir / "report_solver_realboard.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"[solver-rb] wrote {out_dir / 'report_solver_realboard.md'} / report_solver_realboard.json")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="solver_v3 vs v2 on real boards")
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
