"""P4.16: definitive recommended combo across synthetic templates + real boards.

Runs the recommended "completion-first" combination (route-aware objective +
post-hoc route repair) on every registered template and every real board, and
emits a single leaderboard so the maintainer has one authoritative snapshot of
the offline pipeline's completion/truth trade-off.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import time
from typing import Dict, List, Optional, Sequence

from .model import hard_violations
from .physics_v2 import PhysicsSimulatorV2
from .realboard import DEFAULT_SOURCES, load_and_convert
from .route_cost import RouteAwareObjective
from .objective import ProxyObjective
from .route_opt import repair_routes
from .templates import instantiate, template_names

OUT_DIR = pathlib.Path(__file__).resolve().parent.parent


def _combo_placement(sc, cost_fn, seed: int, steps: int, max_routes: int = 60):
    return repair_routes(sc, cost_fn, seed=seed, steps=steps, max_routes=max_routes)


def run(quick: bool = False, seeds: Sequence[int] = (0, 1), steps: int = 800) -> Dict:
    started = time.time()
    rows: List[Dict] = []

    names = list(template_names())
    if quick:
        names = names[:2]
        seeds = seeds[:1]
        steps = 200

    # 1) synthetic templates
    for name in names:
        sc = instantiate(name, seed=0)
        base = ProxyObjective(sc)
        ra = RouteAwareObjective(sc, base=base, w_route=2.0)
        for seed in seeds:
            pl, truth, route, stats = _combo_placement(sc, ra.cost, seed=seed, steps=steps)
            rows.append(
                {
                    "domain": "template",
                    "name": name,
                    "seed": seed,
                    "completion": round(float(route.completion), 4),
                    "truth_v2": round(float(truth), 4),
                    "feasible": not hard_violations(sc, pl),
                    "routes_calls": int(stats.get("routes_calls", 0)),
                    "failed_nets": list(getattr(route, "failed_nets", [])),
                }
            )
            print(f"[final-combo] template {name} seed={seed}: comp={route.completion:.3f} truth={truth:.3f}")

    # 2) real boards
    sources = DEFAULT_SOURCES if not quick else DEFAULT_SOURCES[:1]
    for name, path in sources:
        if not pathlib.Path(path).is_file():
            continue
        converted = load_and_convert(path, name=name)
        sc = converted.scenario
        base = ProxyObjective(sc)
        ra = RouteAwareObjective(sc, base=base, w_route=2.0)
        for seed in seeds:
            pl, truth, route, stats = _combo_placement(sc, ra.cost, seed=seed, steps=steps)
            rows.append(
                {
                    "domain": "realboard",
                    "name": name,
                    "seed": seed,
                    "completion": round(float(route.completion), 4),
                    "truth_v2": round(float(truth), 4),
                    "feasible": not hard_violations(sc, pl),
                    "routes_calls": int(stats.get("routes_calls", 0)),
                    "failed_nets": list(getattr(route, "failed_nets", [])),
                }
            )
            print(f"[final-combo] realboard {name} seed={seed}: comp={route.completion:.3f} truth={truth:.3f}")

    agg = _aggregate(rows)
    return {"config": {"quick": quick, "seeds": list(seeds), "steps": steps},
            "rows": rows, "aggregate": agg, "runtime_s": round(time.time() - started, 2)}


def _aggregate(rows: List[Dict]) -> Dict:
    by_domain: Dict[str, List[Dict]] = {}
    for r in rows:
        by_domain.setdefault(r["domain"], []).append(r)
    out = {}
    for domain, rs in by_domain.items():
        comp = [r["completion"] for r in rs if r["completion"] is not None]
        truth = [r["truth_v2"] for r in rs if r["truth_v2"] is not None]
        out[domain] = {
            "n": len(rs),
            "completion": round(sum(comp) / len(comp), 4) if comp else None,
            "truth_v2": round(sum(truth) / len(truth), 4) if truth else None,
            "all_feasible": all(r["feasible"] for r in rs),
            "fully_routed": f"{sum(1 for r in rs if r['completion'] == 1.0)}/{len(rs)}",
            "unrouted_nets": sorted({n for r in rs for n in r.get("failed_nets", [])}),
        }
    return out


def write_report(data: Dict, out_dir: pathlib.Path = OUT_DIR) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report_final.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    agg = data["aggregate"]
    lines = ["# P4.16：推荐组合的最终快照（模板 + 真实板）\n"]
    lines.append(f"- 组合：route_aware(w=2.0) + post-hoc route repair；运行 {data['runtime_s']} s\n")
    lines.append("## 汇总\n")
    lines.append("| 域 | n | completion | truth_v2 | 全布通 | 全硬可行 |")
    lines.append("|---|---|---|---|---|---|")
    for domain in ("template", "realboard"):
        if domain in agg:
            a = agg[domain]
            lines.append(f"| {domain} | {a['n']} | {a['completion']} | {a['truth_v2']} | {a['fully_routed']} | {a['all_feasible']} |")
    lines.append("\n> 边界：伪物理 truth / 1mm 2层离线 router；真实 DRC/布线/SI-PI/热 `NOT RUN`。")
    (out_dir / "report_final.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"[final-combo] wrote {out_dir / 'report_final.md'} / report_final.json")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Recommended combo snapshot")
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
