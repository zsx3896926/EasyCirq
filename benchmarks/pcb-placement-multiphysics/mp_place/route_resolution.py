"""P4.17: router resolution/layer sweep on real boards.

Quantifies how the 1 mm / 2-layer grid-maze oracle's completion ceiling changes
with grid resolution and layer count, on the recommended-combo placement of
each real board.  This turns the "2-layer grid is not DRC" boundary into a
measurable knob and names the limiting nets.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import time
from typing import Dict, List, Optional, Sequence

from .model import hard_violations
from .objective import ProxyObjective
from .realboard import DEFAULT_SOURCES, load_and_convert
from .route_cost import RouteAwareObjective
from .route_opt import repair_routes
from .router import GridRouter

OUT_DIR = pathlib.Path(__file__).resolve().parent.parent
GRIDS = (1.0, 0.5)
LAYERS = (2, 4)


def run(quick: bool = False, steps: int = 800) -> Dict:
    started = time.time()
    sources = DEFAULT_SOURCES if not quick else DEFAULT_SOURCES[:1]
    rows: List[Dict] = []
    for name, path in sources:
        if not pathlib.Path(path).is_file():
            continue
        converted = load_and_convert(path, name=name)
        sc = converted.scenario
        ra = RouteAwareObjective(sc, base=ProxyObjective(sc), w_route=2.0)
        pl, truth, _r, _s = repair_routes(sc, ra.cost, seed=0, steps=steps, max_routes=60)
        for gm in GRIDS:
            for layers in LAYERS:
                r = GridRouter(sc, grid_mm=gm, layers=layers).route(pl)
                rows.append(
                    {
                        "board": name,
                        "grid_mm": gm,
                        "layers": layers,
                        "completion": round(float(r.completion), 4),
                        "failed_nets": sorted(r.failed_nets),
                        "feasible": not hard_violations(sc, pl),
                    }
                )
                print(f"[res-study] {name} grid={gm} layers={layers}: comp={r.completion:.3f} failed={sorted(r.failed_nets)}")
    return {"config": {"grids": list(GRIDS), "layers": list(LAYERS), "steps": steps},
            "rows": rows, "runtime_s": round(time.time() - started, 2)}


def write_report(data: Dict, out_dir: pathlib.Path = OUT_DIR) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report_route_resolution.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# P4.17：router 分辨率/层数扫描（真实板）\n"]
    lines.append(f"- 运行 {data['runtime_s']} s；grid {data['config']['grids']} mm × layers {data['config']['layers']}\n")
    lines.append("| board | grid_mm | layers | completion | failed_nets |")
    lines.append("|---|---|---|---|---|")
    for r in data["rows"]:
        lines.append(f"| {r['board']} | {r['grid_mm']} | {r['layers']} | {r['completion']} | {', '.join(r['failed_nets']) or '-'} |")
    lines.append("\n> 边界：伪物理 truth / 离线网格 oracle；真实 DRC/布线 `NOT RUN`。")
    (out_dir / "report_route_resolution.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"[res-study] wrote {out_dir / 'report_route_resolution.md'} / report_route_resolution.json")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Router resolution/layer sweep on real boards")
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--steps", type=int, default=800)
    parser.add_argument("--out", default=str(OUT_DIR))
    args = parser.parse_args(argv)
    write_report(run(quick=args.quick, steps=args.steps), pathlib.Path(args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
