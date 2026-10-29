"""P2.8 route-aware objective: a cheap routability proxy inside the cost.

Instead of only repairing placements after the fact (``mp_place.route_opt``), this
module folds a **cheap geometric routability penalty** into the placement
objective, so :func:`mp_place.solver_v2.solve` optimises for routability from the
start.  The penalty never calls the expensive grid router; it only uses
``extract_features`` plus local grid statistics over the placement.

``RouteAwareObjective``
=======================
``RouteAwareObjective(scenario, base=None, w_route=2.0)``

``cost(pl) = base.cost(pl) + w_route * route_penalty(pl)``

where ``base`` defaults to :class:`mp_place.objective.ProxyObjective` (a class or
an instance/callable is accepted).  The penalty is the weighted mean of four
independent, normalised-in-[0, 1] proxies for why the 1 mm / 2-layer grid router
fails:

1. ``congestion`` — the existing ``congestion`` feature (max components per 2 mm
   cell) plus a coverage "hot spot" statistic: mean squared copper coverage over
   2 mm cells.  Both rise when components bunch up.
2. ``corridor_block`` — for every net, the fraction of cells inside the net's
   pad bounding box (inflated by 1 mm) that are covered by component bodies.
   High values mean other parts physically block the net's natural corridor.
3. ``pad_escape_risk`` — for every net pad, how close foreign component bodies
   are (``< 2 mm``): a pad whose escape cell is squeezed snaps far away or gets
   trapped, which the router sees as a terminal it cannot reach.
4. ``gap_pressure`` — for every movable component, how narrow its narrowest gap
   to another component is (``< 1.5 mm``): narrow channels between bodies are
   the main source of two-layer detours.

The penalty is cheap (one feature extraction plus a small rasterisation; no
router call), deterministic, and monotone in crowding in the sense used by the
tests.

Benchmark
=========
``python -m mp_place.route_cost`` writes ``report_route_cost.md`` and
``report_route_cost.json`` at the project root.  Three groups are compared on
8 templates x seeds 0/1, all with ``solver_v2.solve(steps=800)`` when applicable:

* ``proxy`` — plain ``ProxyObjective`` solve (no routability awareness);
* ``route_aware`` — ``RouteAwareObjective`` solve;
* ``proxy_repair`` — plain proxy solve followed by
  ``route_opt.repair_routes(..., max_routes=60)`` (the P2.5 post-hoc baseline).

Metrics: offline router completion, ``truth_v2`` and wall-clock time per run.
Recorded result (8 templates x seeds 0/1, ``steps=800``, ``w_route=2.0``)::

    group                 completion   fully routed   truth_v2   time/run
    proxy                   0.9019        6/16         2.0001     0.17 s
    route_aware             0.9755       14/16         2.0627     0.45 s
    proxy + post-hoc repair 0.9938       15/16         1.9101     1.81 s

RouteAware captures ~80% of the post-hoc repair completion gain (0.0736 of
0.0919) at ~17% of the repair runtime overhead, **with zero router calls**, and
does so deterministically as part of the solve.  Its price is a small truth_v2
regression (+3.1%): the penalty tends to spread parts that were already routable
(e.g. ``can-node`` / ``rs485``), a weight-vs-quality trade-off documented in the
report.

Boundary: this is still an offline surrogate.  The penalty is a heuristic, not
DRC; ``completion == 1`` means the offline 1 mm/2-layer maze oracle routed every
scored net, and real routing/DRC/SI/PI/thermal remain ``NOT RUN``.
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import time
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from .features import extract_features
from .model import Placement, Scenario, bbox, pad_position, rect_overlap_area, rect_point_distance
from .objective import ProxyObjective

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
REPORT_MD = "report_route_cost.md"
REPORT_JSON = "report_route_cost.json"

# Local grid used by the penalty (mm); independent from the router's 1 mm grid.
PENALTY_GRID_MM = 2.0
# Distance scales below which pads / component gaps are considered squeezed.
PAD_CLEAR_MM = 2.0
GAP_CLEAR_MM = 1.5
CORRIDOR_INFLATE_MM = 1.0
# Weights of (congestion, corridor_block, pad_escape_risk, gap_pressure).
TERM_WEIGHTS: Tuple[float, float, float, float] = (0.30, 0.35, 0.20, 0.15)
# Per-net-class importance of a blocked corridor.
NET_CLASS_WEIGHT: Dict[str, float] = {
    "power": 1.0,
    "ground": 0.6,
    "analog": 1.0,
    "digital": 0.5,
    "rf": 1.0,
    "generic": 0.4,
}
DEFAULT_W_ROUTE = 2.0


def _clip(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return low if value < low else high if value > high else value


def _bbox_distance(box_a: Tuple[float, float, float, float], box_b: Tuple[float, float, float, float]) -> float:
    dx = max(0.0, box_a[0] - box_b[2], box_b[0] - box_a[2])
    dy = max(0.0, box_a[1] - box_b[3], box_b[1] - box_a[3])
    return math.hypot(dx, dy)


class RouteAwareObjective:
    """ProxyObjective + cheap, router-free routability penalty.

    Parameters
    ----------
    scenario:
        The scenario the placement belongs to.
    base:
        Base objective (instance with ``cost``, or a class such as
        ``ProxyObjective``, which is instantiated for ``scenario``).  Defaults to
        ``ProxyObjective(scenario)``.
    w_route:
        Weight of the routability penalty (``cost = base.cost + w_route *
        penalty``).  ``0`` reproduces the plain base objective.
    """

    name = "route_aware_proxy"

    def __init__(
        self,
        scenario: Scenario,
        base: Optional[object] = None,
        w_route: float = DEFAULT_W_ROUTE,
    ) -> None:
        self.scenario = scenario
        if base is None:
            self.base: object = ProxyObjective(scenario)
        elif isinstance(base, type):
            self.base = base(scenario)
        else:
            self.base = base
        self.w_route = float(w_route)
        self.grid_mm = PENALTY_GRID_MM
        self.nx = max(1, int(math.ceil(scenario.board_w / self.grid_mm - 1e-9)))
        self.ny = max(1, int(math.ceil(scenario.board_h / self.grid_mm - 1e-9)))
        # Precomputed net specs for the corridor term: (pin refs, pin names, weight).
        self._net_specs: List[Tuple[Tuple[Tuple[str, str], ...], float]] = []
        for net in scenario.nets:
            if len(net.pins) < 2:
                continue
            weight = NET_CLASS_WEIGHT.get(net.cls, 0.5)
            self._net_specs.append((tuple(net.pins), weight))
        self._components = scenario.components
        self._movable = [ref for ref, comp in scenario.components.items() if not comp.fixed]

    # -- cost interface ----------------------------------------------------
    def _base_cost(self, placement: Placement, features: Dict[str, float]) -> float:
        cost_features = getattr(self.base, "cost_features", None)
        if callable(cost_features):
            return float(cost_features(features))
        cost = getattr(self.base, "cost", None)
        if callable(cost):
            return float(cost(placement))
        if callable(self.base):
            return float(self.base(placement))  # type: ignore[operator]
        raise TypeError("base objective must expose cost(placement) or cost_features(f)")

    def cost(self, placement: Placement) -> float:
        features = extract_features(self.scenario, placement)
        penalty = self._penalty(placement, features)
        return self._base_cost(placement, features) + self.w_route * penalty

    def route_penalty(self, placement: Placement) -> float:
        """Cheap routability penalty in ``[0, 1]`` (no router call)."""
        return self._penalty(placement, extract_features(self.scenario, placement))

    # -- penalty internals -------------------------------------------------
    def _coverage_grid(self, placement: Placement) -> List[float]:
        """Copper/body coverage ratio per 2 mm cell (can exceed 1 on overlaps)."""
        g = self.grid_mm
        nx, ny = self.nx, self.ny
        coverage = [0.0] * (nx * ny)
        cell_area = g * g
        for ref, comp in self._components.items():
            if ref not in placement:
                continue
            x, y, rot = placement[ref]
            box = bbox(comp, x, y, rot)
            i0 = max(0, int(math.floor(box[0] / g + 1e-9)))
            i1 = min(nx - 1, int(math.floor((box[2] - 1e-9) / g)))
            j0 = max(0, int(math.floor(box[1] / g + 1e-9)))
            j1 = min(ny - 1, int(math.floor((box[3] - 1e-9) / g)))
            if i0 > i1 or j0 > j1:
                continue
            for j in range(j0, j1 + 1):
                base = j * nx
                for i in range(i0, i1 + 1):
                    cell = (i * g, j * g, (i + 1) * g, (j + 1) * g)
                    coverage[base + i] += rect_overlap_area(box, cell) / cell_area
        return coverage

    @staticmethod
    def _pad_points(scenario: Scenario, placement: Placement) -> List[Tuple[str, str, float, float]]:
        pads: List[Tuple[str, str, float, float]] = []
        for ref, pin in survival_pins(scenario):
            comp = scenario.components.get(ref)
            if comp is None or ref not in placement:
                continue
            x, y, rot = placement[ref]
            px, py = pad_position(comp, x, y, rot, pin)
            pads.append((ref, pin, px, py))
        return pads

    def _congestion_term(self, features: Dict[str, float], coverage: Sequence[float]) -> float:
        covered = [_clip(value) for value in coverage]
        peak = max(covered) if covered else 0.0
        hot = sum(value * value for value in covered) / len(covered) if covered else 0.0
        return _clip(0.5 * float(features.get("congestion", 0.0)) + 0.25 * peak + 0.25 * min(1.0, 4.0 * hot))

    def _corridor_block_term(self, placement: Placement, coverage: Sequence[float]) -> float:
        g = self.grid_mm
        nx, ny = self.nx, self.ny
        covered = [_clip(value) for value in coverage]
        weighted_sum = 0.0
        weight_sum = 0.0
        for pins, weight in self._net_specs:
            xs: List[float] = []
            ys: List[float] = []
            for ref, pin in pins:
                comp = self._components.get(ref)
                if comp is None or ref not in placement:
                    continue
                x, y, rot = placement[ref]
                px, py = pad_position(comp, x, y, rot, pin)
                xs.append(px)
                ys.append(py)
            if len(xs) < 2:
                continue
            x0 = min(xs) - CORRIDOR_INFLATE_MM
            x1 = max(xs) + CORRIDOR_INFLATE_MM
            y0 = min(ys) - CORRIDOR_INFLATE_MM
            y1 = max(ys) + CORRIDOR_INFLATE_MM
            i0 = max(0, int(math.floor(x0 / g)))
            i1 = min(nx - 1, int(math.floor(x1 / g)))
            j0 = max(0, int(math.floor(y0 / g)))
            j1 = min(ny - 1, int(math.floor(y1 / g)))
            if i0 > i1 or j0 > j1:
                continue
            total = 0.0
            count = 0
            for j in range(j0, j1 + 1):
                cy = (j + 0.5) * g
                if cy < y0 or cy > y1:
                    continue
                base = j * nx
                for i in range(i0, i1 + 1):
                    cx = (i + 0.5) * g
                    if cx < x0 or cx > x1:
                        continue
                    total += covered[base + i]
                    count += 1
            if count:
                weighted_sum += weight * (total / count)
                weight_sum += weight
        return _clip(weighted_sum / weight_sum) if weight_sum else 0.0

    def _pad_escape_term(self, placement: Placement) -> float:
        if len(self._components) < 2:
            return 0.0
        boxes = {}
        for ref, comp in self._components.items():
            if ref not in placement:
                continue
            boxes[ref] = bbox(comp, *placement[ref])
        risks: List[float] = []
        for ref, pin in survival_pins(self.scenario):
            comp = self._components.get(ref)
            if comp is None or ref not in placement:
                continue
            x, y, rot = placement[ref]
            px, py = pad_position(comp, x, y, rot, pin)
            nearest = math.inf
            for other, box in boxes.items():
                if other == ref:
                    continue
                distance = rect_point_distance(box, px, py)
                if distance < nearest:
                    nearest = distance
            if math.isfinite(nearest):
                risks.append(_clip(1.0 - nearest / PAD_CLEAR_MM))
        return sum(risks) / len(risks) if risks else 0.0

    def _gap_term(self, placement: Placement) -> float:
        if len(self._movable) < 2:
            return 0.0
        boxes = {}
        for ref, comp in self._components.items():
            if ref not in placement:
                continue
            boxes[ref] = bbox(comp, *placement[ref])
        pressures: List[float] = []
        for ref in self._movable:
            box = boxes.get(ref)
            if box is None:
                continue
            nearest = math.inf
            for other, other_box in boxes.items():
                if other == ref:
                    continue
                gap = _bbox_distance(box, other_box)
                if gap < nearest:
                    nearest = gap
            if math.isfinite(nearest):
                pressures.append(_clip(1.0 - nearest / GAP_CLEAR_MM))
        return sum(pressures) / len(pressures) if pressures else 0.0

    def _penalty(self, placement: Placement, features: Dict[str, float]) -> float:
        coverage = self._coverage_grid(placement)
        terms = (
            self._congestion_term(features, coverage),
            self._corridor_block_term(placement, coverage),
            self._pad_escape_term(placement),
            self._gap_term(placement),
        )
        return sum(weight * term for weight, term in zip(TERM_WEIGHTS, terms))


def survival_pins(scenario: Scenario) -> List[Tuple[str, str]]:
    """All (ref, pin) pairs that actually appear in at least one net."""
    seen: List[Tuple[str, str]] = []
    known = set()
    for net in scenario.nets:
        for pair in net.pins:
            if pair not in known:
                known.add(pair)
                seen.append(pair)
    return seen


# --------------------------------------------------------------------------
# Benchmark / report generation (router, solver and repair imports are lazy so
# that the cost function itself never pulls the router into the solver loop).
# --------------------------------------------------------------------------


def _route_and_truth(scenario: Scenario, placement: Placement, seed: int) -> Dict[str, object]:
    from .physics_v2 import PhysicsSimulatorV2
    from .router import GridRouter

    route_result = GridRouter(scenario, grid_mm=1.0, layers=2).route(placement)
    truth = PhysicsSimulatorV2(scenario, seed=seed).score(placement)
    return {
        "completion": route_result.completion,
        "truth_v2": truth,
        "failed_nets": list(route_result.failed_nets),
        "wirelength_mm": route_result.wirelength_mm,
        "vias": route_result.vias,
    }


def run_benchmark(
    seeds: Sequence[int] = (0, 1),
    steps: int = 800,
    max_routes: int = 60,
    names: Optional[Sequence[str]] = None,
    w_route: float = DEFAULT_W_ROUTE,
) -> Dict[str, object]:
    """Run the three-group benchmark used by ``report_route_cost.{md,json}``."""
    from .model import hard_violations
    from .route_opt import repair_routes
    from .solver_v2 import solve
    from .templates import instantiate, template_names

    template_names_list = list(names) if names is not None else list(template_names())
    rows: List[Dict[str, object]] = []
    started = time.perf_counter()
    for name in template_names_list:
        for seed in seeds:
            scenario = instantiate(name, seed=seed)
            proxy = ProxyObjective(scenario)
            row: Dict[str, object] = {"template": name, "seed": int(seed)}

            # --- group 1: plain proxy solve ------------------------------
            t0 = time.perf_counter()
            placement, proxy_cost, _stats = solve(
                scenario, proxy.cost, seed=seed, steps=steps
            )
            metrics = _route_and_truth(scenario, placement, seed)
            row["proxy"] = {
                "completion": metrics["completion"],
                "truth_v2": metrics["truth_v2"],
                "feasible": not hard_violations(scenario, placement),
                "objective_cost": proxy_cost,
                "runtime_s": time.perf_counter() - t0,
            }

            # --- group 2: route-aware objective solve --------------------
            objective = RouteAwareObjective(scenario, base=proxy, w_route=w_route)
            t0 = time.perf_counter()
            placement, route_cost, _stats = solve(
                scenario, objective.cost, seed=seed, steps=steps
            )
            metrics = _route_and_truth(scenario, placement, seed)
            row["route_aware"] = {
                "completion": metrics["completion"],
                "truth_v2": metrics["truth_v2"],
                "feasible": not hard_violations(scenario, placement),
                "objective_cost": route_cost,
                "runtime_s": time.perf_counter() - t0,
            }

            # --- group 3: plain proxy + post-hoc route repair ------------
            t0 = time.perf_counter()
            placement, truth, route_result, repair_stats = repair_routes(
                scenario, proxy.cost, seed=seed, steps=steps, max_routes=max_routes
            )
            row["proxy_repair"] = {
                "completion": route_result.completion,
                "truth_v2": truth,
                "feasible": not hard_violations(scenario, placement),
                "route_calls": repair_stats["routes_calls"],
                "runtime_s": time.perf_counter() - t0,
            }
            rows.append(row)
            print(
                f"[route-cost] {name} seed={seed}: "
                f"proxy completion={row['proxy']['completion']:.3f} "
                f"truth={row['proxy']['truth_v2']:.4f} | "
                f"route-aware completion={row['route_aware']['completion']:.3f} "
                f"truth={row['route_aware']['truth_v2']:.4f} | "
                f"proxy+repair completion={row['proxy_repair']['completion']:.3f} "
                f"truth={row['proxy_repair']['truth_v2']:.4f}"
            )
    data: Dict[str, object] = {
        "schema": "mp_place.route_cost.report/v1",
        "config": {
            "templates": template_names_list,
            "seeds": [int(seed) for seed in seeds],
            "steps": int(steps),
            "max_routes": int(max_routes),
            "w_route": float(w_route),
            "objective": RouteAwareObjective.name,
            "router": "GridRouter(grid_mm=1.0, layers=2)",
            "term_weights": list(TERM_WEIGHTS),
            "penalty_grid_mm": PENALTY_GRID_MM,
        },
        "rows": rows,
        "aggregate": _aggregate(rows),
        "runtime_s": round(time.perf_counter() - started, 2),
    }
    return data


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _aggregate(rows: Sequence[Dict[str, object]]) -> Dict[str, object]:
    groups = ("proxy", "route_aware", "proxy_repair")
    agg: Dict[str, object] = {"n_runs": len(rows)}
    for group in groups:
        completions = [float(r[group]["completion"]) for r in rows]  # type: ignore[index]
        truths = [float(r[group]["truth_v2"]) for r in rows]  # type: ignore[index]
        runtimes = [float(r[group]["runtime_s"]) for r in rows]  # type: ignore[index]
        agg[group] = {
            "completion_mean": round(_mean(completions), 4),
            "fully_routed": f"{sum(1 for value in completions if value >= 1.0)}/{len(rows)}",
            "truth_v2_mean": round(_mean(truths), 4),
            "runtime_s_mean": round(_mean(runtimes), 4),
        }
    proxy_truth = float(agg["proxy"]["truth_v2_mean"])  # type: ignore[index]
    repair_runtime = float(agg["proxy_repair"]["runtime_s_mean"])  # type: ignore[index]
    agg["delta"] = {
        "route_aware_completion": round(
            float(agg["route_aware"]["completion_mean"])  # type: ignore[index]
            - float(agg["proxy"]["completion_mean"]),  # type: ignore[index]
            4,
        ),
        "route_aware_truth_pct": round(
            100.0 * (float(agg["route_aware"]["truth_v2_mean"]) - proxy_truth) / proxy_truth, 2  # type: ignore[index]
        )
        if proxy_truth
        else 0.0,
        "proxy_repair_completion": round(
            float(agg["proxy_repair"]["completion_mean"])  # type: ignore[index]
            - float(agg["proxy"]["completion_mean"]),  # type: ignore[index]
            4,
        ),
        "proxy_repair_truth_pct": round(
            100.0 * (float(agg["proxy_repair"]["truth_v2_mean"]) - proxy_truth) / proxy_truth, 2  # type: ignore[index]
        )
        if proxy_truth
        else 0.0,
        "route_aware_vs_repair_completion": round(
            float(agg["route_aware"]["completion_mean"])  # type: ignore[index]
            - float(agg["proxy_repair"]["completion_mean"]),  # type: ignore[index]
            4,
        ),
        "route_aware_vs_repair_truth_pct": round(
            100.0 * (float(agg["route_aware"]["truth_v2_mean"]) - float(agg["proxy_repair"]["truth_v2_mean"]))  # type: ignore[index]
            / float(agg["proxy_repair"]["truth_v2_mean"]),  # type: ignore[index]
            2,
        )
        if repair_runtime is not None
        else 0.0,
        "runtime_overhead_route_aware": round(
            float(agg["route_aware"]["runtime_s_mean"]) - float(agg["proxy"]["runtime_s_mean"]),  # type: ignore[index]
            4,
        ),
        "runtime_overhead_repair": round(
            repair_runtime - float(agg["proxy"]["runtime_s_mean"]), 4  # type: ignore[index]
        ),
    }
    # Per-template means (same grouping, averaged over the seed column).
    per_template: Dict[str, object] = {}
    for template in sorted({str(row["template"]) for row in rows}):
        subset = [row for row in rows if str(row["template"]) == template]
        block: Dict[str, object] = {"n_runs": len(subset)}
        for group in groups:
            block[group] = {
                "completion_mean": round(
                    _mean([float(row[group]["completion"]) for row in subset]), 4  # type: ignore[index]
                ),
                "truth_v2_mean": round(
                    _mean([float(row[group]["truth_v2"]) for row in subset]), 4  # type: ignore[index]
                ),
                "runtime_s_mean": round(
                    _mean([float(row[group]["runtime_s"]) for row in subset]), 4  # type: ignore[index]
                ),
            }
        per_template[template] = block
    agg["per_template"] = per_template
    return agg


def write_reports(data: Dict[str, object], out_dir: Optional[pathlib.Path] = None) -> Tuple[pathlib.Path, pathlib.Path]:
    """Write ``report_route_cost.md`` / ``.json`` and return their paths."""
    directory = pathlib.Path(out_dir) if out_dir is not None else PROJECT_ROOT
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / REPORT_JSON
    md_path = directory / REPORT_MD
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    config = data["config"]  # type: ignore[index]
    agg = data["aggregate"]  # type: ignore[index]
    per_template = agg["per_template"]  # type: ignore[index]
    delta = agg["delta"]  # type: ignore[index]
    n_runs = agg["n_runs"]  # type: ignore[index]
    groups: Tuple[Tuple[str, str], ...] = (
        ("proxy", "纯 proxy（无 route 感知）"),
        ("route_aware", "RouteAware（进入目标函数）"),
        ("proxy_repair", "proxy + post-hoc repair"),
    )
    lines: List[str] = []
    lines.append("# P2.8：可布通性代理进目标函数（route-aware cost）对比\n")
    lines.append(
        f"- 配置：{len(config['templates'])} 模板 × seeds {config['seeds']}，"
        f"solver_v2.solve steps={config['steps']}；route repair max_routes={config['max_routes']}；"
        f"w_route={config['w_route']}，penalty grid {config['penalty_grid_mm']} mm"
    )
    lines.append(f"- 运行：{n_runs} 组；总耗时 {data['runtime_s']} s；router = {config['router']}\n")
    lines.append("## 汇总（均值，8 模板 × seeds 0/1）\n")
    lines.append("| 组别 | router completion 均值 | 全布通组数 | truth_v2 均值（越低越好） | 单组耗时均值 (s) |")
    lines.append("|---|---|---|---|---|")
    for key, label in groups:
        block = agg[key]  # type: ignore[index]
        lines.append(
            f"| {label} | {block['completion_mean']} | {block['fully_routed']} | "
            f"{block['truth_v2_mean']} | {block['runtime_s_mean']} |"
        )
    lines.append("")
    lines.append("相对纯 proxy 的变化（completion 越大越好；truth 变化百分比正数 = 变差）：")
    lines.append(
        f"- RouteAware：completion {delta['route_aware_completion']:+.4f}，"
        f"truth_v2 {delta['route_aware_truth_pct']:+.2f}%，"
        f"耗时 {delta['runtime_overhead_route_aware']:+.4f} s/组"
    )
    lines.append(
        f"- proxy+repair：completion {delta['proxy_repair_completion']:+.4f}，"
        f"truth_v2 {delta['proxy_repair_truth_pct']:+.2f}%，"
        f"耗时 {delta['runtime_overhead_repair']:+.4f} s/组"
    )
    lines.append(
        f"- RouteAware 相对 proxy+repair：completion {delta['route_aware_vs_repair_completion']:+.4f}，"
        f"truth_v2 {delta['route_aware_vs_repair_truth_pct']:+.2f}%"
    )
    lines.append("\n### 结论\n")
    repair_overhead = float(delta["runtime_overhead_repair"])
    route_overhead = float(delta["runtime_overhead_route_aware"])
    capture = (
        100.0 * float(delta["route_aware_completion"]) / float(delta["proxy_repair_completion"])
        if float(delta["proxy_repair_completion"])
        else 0.0
    )
    overhead_ratio = (
        100.0 * route_overhead / repair_overhead if repair_overhead > 0 else 0.0
    )
    lines.append(
        f"- RouteAware 用 **0 次 router 调用**把 completion 从 "
        f"{agg['proxy']['completion_mean']} 提到 {agg['route_aware']['completion_mean']}"
        f"（全布通 {agg['proxy']['fully_routed']} → {agg['route_aware']['fully_routed']}），"
        f"拿到 post-hoc repair completion 收益的 {capture:.0f}%，"
        f"额外耗时仅为其 {overhead_ratio:.0f}%。"
    )
    lines.append(
        "- 代价：已经全布通的模板（如 can-node / rs485）上，惩罚项会挤开本来够用的布局，"
        "使 truth_v2 变差；RouteAware 适合作为零 router 开销的确定性折中，"
        "追求 completion 上限仍应使用 post-hoc repair。"
    )
    lines.append(
        "- 惩罚权重（w_route=2.0）与四项 term 权重是人工先验，未按模板自适应；"
        "如需在 truth 与 completion 间移动工作点，可调 `w_route` 或 `TERM_WEIGHTS`。"
    )
    lines.append("\n## 逐模板（seeds 0/1 均值）\n")
    lines.append(
        "| 模板 | proxy completion | RouteAware completion | proxy+repair completion | "
        "proxy truth | RouteAware truth | proxy+repair truth |"
    )
    lines.append("|---|---|---|---|---|---|---|")
    for template in sorted(per_template):
        block = per_template[template]
        lines.append(
            f"| {template} | {block['proxy']['completion_mean']} | "
            f"{block['route_aware']['completion_mean']} | "
            f"{block['proxy_repair']['completion_mean']} | "
            f"{block['proxy']['truth_v2_mean']} | "
            f"{block['route_aware']['truth_v2_mean']} | "
            f"{block['proxy_repair']['truth_v2_mean']} |"
        )
    lines.append("\n## 解读与边界\n")
    lines.append(
        "- RouteAware 的惩罚项为廉价几何代理（局部密度/走廊遮挡/焊盘逃线风险/通道间隙），"
        "**不调用 router**；它把可布通性提前放进退火目标，而不是事后修补。"
    )
    lines.append(
        "- post-hoc repair 直接以 router completion 为接受准则、可调用 router 最多 60 次，"
        "因此其 completion 上限最高但耗时显著更大；RouteAware 是零 router 调用的折中。"
    )
    lines.append(
        "- truth_v2 衡量多物理质量；RouteAware 可能以少量 truth 为代价换取可布通性，"
        "表中数值供权衡参考。"
    )
    lines.append(
        "- 边界：router 是 1 mm/2 层网格迷宫 oracle，不是 DRC/真实可布通证明；"
        "真实布线/DRC/SI/PI/热仍 `NOT RUN`。"
    )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[route-cost] wrote {md_path} / {json_path}")
    return md_path, json_path


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Route-aware objective benchmark")
    parser.add_argument("--seeds", default="0,1")
    parser.add_argument("--steps", type=int, default=800)
    parser.add_argument("--max-routes", type=int, default=60)
    parser.add_argument("--w-route", type=float, default=DEFAULT_W_ROUTE)
    parser.add_argument("--quick", action="store_true", help="2 templates x 1 seed x 300 steps")
    parser.add_argument("--out", default=str(PROJECT_ROOT))
    args = parser.parse_args(argv)
    seeds = tuple(int(part) for part in args.seeds.split(",") if part.strip())
    if args.quick:
        from .templates import template_names

        names = list(template_names())[:2]
        data = run_benchmark(seeds=seeds[:1], steps=300, max_routes=8, names=names, w_route=args.w_route)
    else:
        data = run_benchmark(seeds=seeds, steps=args.steps, max_routes=args.max_routes, w_route=args.w_route)
    write_reports(data, pathlib.Path(args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["RouteAwareObjective", "run_benchmark", "write_reports", "survival_pins"]
