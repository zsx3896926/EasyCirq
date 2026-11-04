"""P4-I scoreboard: template x seed x {baseline, route_repair} regression table.

The scoreboard is the *measurement* half of the one-command nightly regression
(``nightly.py`` is the runner).  For every registered product-family template
and every requested seed it runs the end-to-end offline pipeline twice:

* ``baseline`` -- ``pipeline.run_pipeline(..., route_repair=False)`` (portfolio
  solver -> verify -> truth -> router -> intent -> certificate);
* ``repair``   -- ``pipeline.run_pipeline(..., route_repair=True)`` (the same
  chain on top of the solver + routability-gated route repair).

Both runs are collected into plain JSON rows and a deterministic summary:

* schema ``mp_place.scoreboard/v1``;
* per row: feasibility, ``truth_v1``/``truth_v2``, router completion / failed
  nets / vias, intent constraint counts, and the repair run's ``route_calls``;
* summary: baseline vs repair means (completion, truth, vias), batch
  ``all_feasible`` and the route-repair truth-degradation check
  (``truth_v2_degradation_pct`` must stay ``<= 5%``).

Everything is offline and uses the deterministic pipeline report: two calls
with the same ``(templates, seeds, steps)`` produce byte-identical JSON except
for the wall-clock ``runtime_s`` field (top level only).

Usage
-----
>>> from mp_place.scoreboard import run_scoreboard, render_markdown
>>> report = run_scoreboard(templates=["buck"], seeds=[0], steps=300)
>>> report["schema"]
'mp_place.scoreboard/v1'
>>> print(render_markdown(report))  # doctest: +SKIP

CLI::

    python -m mp_place.scoreboard                       # markdown on stdout
    python -m mp_place.scoreboard --json                # one compact JSON line
    python -m mp_place.scoreboard --out scoreboard.json # also write the JSON
    python -m mp_place.scoreboard --seeds 0,1 --steps 800
    python -m mp_place.scoreboard --templates buck,rs485 --seeds 0 --steps 200

Exit code is ``0`` when the measurement completed (even if some layouts are
infeasible -- the summary reports it), ``1`` for pipeline errors, ``2`` for
usage errors.
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import sys
import time
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from .pipeline import run_pipeline
from .templates import template_names

SCOREBOARD_SCHEMA = "mp_place.scoreboard/v1"
DEFAULT_SEEDS: Tuple[int, ...] = (0, 1)
DEFAULT_STEPS = 800
MODES: Tuple[str, ...] = ("baseline", "repair")
TRUTH_DEGRADATION_LIMIT_PCT = 5.0

PipelineFn = Callable[..., Dict[str, Any]]


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #
def _finite(value: Any, digits: int = 6) -> Optional[float]:
    """Round a float for the report; ``None`` for missing / non-finite values."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return round(number, digits)


def _mean(values: Sequence[Optional[float]]) -> Optional[float]:
    usable = [float(v) for v in values if v is not None]
    if not usable:
        return None
    return round(sum(usable) / len(usable), 6)


def _resolve_templates(templates: Optional[Sequence[str]]) -> List[str]:
    known = template_names()
    if templates is None:
        return known
    resolved: List[str] = []
    for name in templates:
        if name not in known:
            raise KeyError(f"unknown template {name!r}; known templates: {known}")
        if name not in resolved:
            resolved.append(name)
    if not resolved:
        raise ValueError("templates must not be empty")
    return resolved


def _resolve_seeds(seeds: Sequence[int]) -> List[int]:
    resolved: List[int] = []
    for seed in seeds:
        value = int(seed)
        if value < 0:
            raise ValueError(f"seeds must be >= 0, got {value}")
        if value not in resolved:
            resolved.append(value)
    if not resolved:
        raise ValueError("seeds must not be empty")
    return resolved


# --------------------------------------------------------------------------- #
# one row
# --------------------------------------------------------------------------- #
def _row(template: str, seed: int, mode: str, report: Dict[str, Any]) -> Dict[str, Any]:
    """Reduce a pipeline report to the scoreboard row fields."""
    router = report.get("router") or {}
    solver = report.get("solver") or {}
    constraints = report.get("intent_constraints") or {}
    route_calls = solver.get("route_calls")
    try:
        route_calls_int = int(route_calls) if route_calls is not None else None
    except (TypeError, ValueError):
        route_calls_int = None
    try:
        vias = int(router["vias"]) if router.get("vias") is not None else None
    except (TypeError, ValueError):
        vias = None
    return {
        "template": template,
        "seed": int(seed),
        "mode": mode,
        "feasible": bool(report.get("feasible")),
        "truth_v1": _finite(report.get("truth_v1")),
        "truth_v2": _finite(report.get("truth_v2")),
        "proxy_cost": _finite(report.get("proxy_cost")),
        "router_status": router.get("status"),
        "router_completion": _finite(router.get("completion")),
        "router_failed_nets": [str(name) for name in (router.get("failed_nets") or [])],
        "router_vias": vias,
        "intent_constraints": {
            str(key): int(value) for key, value in dict(constraints).items()
        },
        "intent_total_constraints": int(report.get("intent_total_constraints") or 0),
        "route_calls": route_calls_int,
        "solver": str(solver.get("solver") or ""),
    }


# --------------------------------------------------------------------------- #
# aggregation
# --------------------------------------------------------------------------- #
def _mode_block(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    completion = [row["router_completion"] for row in rows]
    truth_v2 = [row["truth_v2"] for row in rows]
    truth_v1 = [row["truth_v1"] for row in rows]
    vias = [row["router_vias"] for row in rows]
    route_calls = [row["route_calls"] for row in rows]
    n_runs = len(rows)
    return {
        "n_runs": n_runs,
        "all_feasible": all(bool(row["feasible"]) for row in rows),
        "mean_completion": _mean(completion),
        "min_completion": round(min(c for c in completion if c is not None), 6)
        if any(c is not None for c in completion)
        else None,
        "fully_routed": f"{sum(1 for c in completion if c == 1.0)}/{n_runs}",
        "mean_truth_v1": _mean(truth_v1),
        "mean_truth_v2": _mean(truth_v2),
        "failed_nets_total": sum(len(row["router_failed_nets"]) for row in rows),
        "vias_total": sum(int(v) for v in vias if v is not None) if any(
            v is not None for v in vias
        ) else None,
        "route_calls_total": sum(int(r) for r in route_calls if r is not None)
        if any(r is not None for r in route_calls)
        else None,
    }


def _pair_block(baseline: Dict[str, Any], repair: Dict[str, Any]) -> Dict[str, Any]:
    """Compare one baseline row with its repair twin."""
    base_truth = baseline["truth_v2"]
    rep_truth = repair["truth_v2"]
    base_completion = baseline["router_completion"]
    rep_completion = repair["router_completion"]
    delta_truth = None
    if base_truth is not None and rep_truth is not None:
        delta_truth = round(rep_truth - base_truth, 6)
    delta_completion = None
    if base_completion is not None and rep_completion is not None:
        delta_completion = round(rep_completion - base_completion, 6)
    return {
        "template": baseline["template"],
        "seed": baseline["seed"],
        "truth_v2_baseline": base_truth,
        "truth_v2_repair": rep_truth,
        "delta_truth_v2": delta_truth,
        "completion_baseline": base_completion,
        "completion_repair": rep_completion,
        "delta_completion": delta_completion,
        "repair_failed_nets": list(repair["router_failed_nets"]),
        "repair_route_calls": repair["route_calls"],
    }


def _summarize(
    rows: Sequence[Dict[str, Any]],
    templates: Sequence[str],
    seeds: Sequence[int],
    steps: int,
) -> Dict[str, Any]:
    baseline_rows = [row for row in rows if row["mode"] == "baseline"]
    repair_rows = [row for row in rows if row["mode"] == "repair"]
    baseline = _mode_block(baseline_rows)
    repair = _mode_block(repair_rows)

    index = {(row["template"], row["seed"], row["mode"]): row for row in rows}
    pairs: List[Dict[str, Any]] = []
    for template in templates:
        for seed in seeds:
            base = index.get((template, seed, "baseline"))
            rep = index.get((template, seed, "repair"))
            if base is not None and rep is not None:
                pairs.append(_pair_block(base, rep))

    base_mean = baseline["mean_truth_v2"]
    rep_mean = repair["mean_truth_v2"]
    degradation = None
    if base_mean is not None and rep_mean is not None and base_mean > 0:
        degradation = round(100.0 * (rep_mean - base_mean) / base_mean, 2)

    completion_delta = None
    if baseline["mean_completion"] is not None and repair["mean_completion"] is not None:
        completion_delta = round(
            repair["mean_completion"] - baseline["mean_completion"], 6
        )

    truth_not_worse = sum(
        1
        for pair in pairs
        if pair["delta_truth_v2"] is not None and pair["delta_truth_v2"] <= 1e-9
    )
    n_pairs = len(pairs)
    batch = {
        "n_runs": len(rows),
        "n_templates": len(templates),
        "n_pairs": n_pairs,
        "templates": list(templates),
        "seeds": list(seeds),
        "steps": int(steps),
        "modes": list(MODES),
        "all_feasible": all(bool(row["feasible"]) for row in rows),
    }
    route_repair = {
        "truth_v2_degradation_pct": degradation,
        "truth_degradation_limit_pct": TRUTH_DEGRADATION_LIMIT_PCT,
        "truth_not_worse_than_limit": bool(
            degradation is not None and degradation <= TRUTH_DEGRADATION_LIMIT_PCT
        ),
        "completion_mean_delta": completion_delta,
        "truth_v2_mean_delta": round(rep_mean - base_mean, 6)
        if base_mean is not None and rep_mean is not None
        else None,
        "runs_truth_not_worse": f"{truth_not_worse}/{n_pairs}",
        "route_calls_total": repair["route_calls_total"],
    }
    return {
        "batch": batch,
        "baseline": baseline,
        "repair": repair,
        "route_repair": route_repair,
        "pairs": pairs,
    }


# --------------------------------------------------------------------------- #
# public API
# --------------------------------------------------------------------------- #
def run_scoreboard(
    templates: Optional[Sequence[str]] = None,
    seeds: Sequence[int] = DEFAULT_SEEDS,
    steps: int = DEFAULT_STEPS,
    pipeline_fn: Optional[PipelineFn] = None,
) -> Dict[str, Any]:
    """Run the template x seed x mode matrix and return a JSON-safe report.

    Parameters
    ----------
    templates:
        Template names to run; ``None`` means every registered template
        (:func:`mp_place.templates.template_names`, 8 families).
    seeds:
        Template instantiation / solver / simulator seeds.
    steps:
        Solver move budget handed to every pipeline run (same budget for the
        baseline and the route-repair run).
    pipeline_fn:
        Optional ``run_pipeline`` replacement (tests / ablation).  Must accept
        ``(template_name, budget_steps=..., seed=..., route_repair=...)`` and
        return the pipeline report dict.

    Returns
    -------
    dict
        ``{"schema": "mp_place.scoreboard/v1", "config": ..., "rows": [...],
        "summary": {...}, "runtime_s": ...}``.  Deterministic except for the
        top-level ``runtime_s``.
    """
    template_list = _resolve_templates(templates)
    seed_list = _resolve_seeds(seeds)
    try:
        budget = int(steps)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"steps must be an integer, got {steps!r}") from exc
    if budget < 0:
        raise ValueError(f"steps must be >= 0, got {budget}")
    run = pipeline_fn or run_pipeline
    started = time.perf_counter()
    rows: List[Dict[str, Any]] = []
    for template in template_list:
        for seed in seed_list:
            for mode in MODES:
                report = run(
                    template,
                    budget_steps=budget,
                    seed=seed,
                    route_repair=(mode == "repair"),
                )
                rows.append(_row(template, seed, mode, report))
    runtime = round(time.perf_counter() - started, 2)
    return {
        "schema": SCOREBOARD_SCHEMA,
        "config": {
            "templates": template_list,
            "seeds": seed_list,
            "steps": budget,
            "modes": list(MODES),
            "router": "GridRouter(grid_mm=1.0, layers=2)",
            "solver": "portfolio-v2 + route-aware repair",
        },
        "rows": rows,
        "summary": _summarize(rows, template_list, seed_list, budget),
        "runtime_s": runtime,
    }


# --------------------------------------------------------------------------- #
# markdown rendering
# --------------------------------------------------------------------------- #
def _per_template(rows: Sequence[Dict[str, Any]], templates: Sequence[str]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for template in templates:
        base = [r for r in rows if r["template"] == template and r["mode"] == "baseline"]
        rep = [r for r in rows if r["template"] == template and r["mode"] == "repair"]
        base_truth = _mean([r["truth_v2"] for r in base])
        rep_truth = _mean([r["truth_v2"] for r in rep])
        out.append(
            {
                "template": template,
                "completion_baseline": _mean([r["router_completion"] for r in base]),
                "completion_repair": _mean([r["router_completion"] for r in rep]),
                "truth_v2_baseline": base_truth,
                "truth_v2_repair": rep_truth,
                "delta_truth": round(rep_truth - base_truth, 6)
                if base_truth is not None and rep_truth is not None
                else None,
                "feasible": all(r["feasible"] for r in base + rep),
                "repair_failed_nets": sum(len(r["router_failed_nets"]) for r in rep),
            }
        )
    return out


def render_markdown(report: Dict[str, Any]) -> str:
    """Render the scoreboard report as a markdown document."""
    config = report["config"]
    summary = report["summary"]
    batch = summary["batch"]
    baseline = summary["baseline"]
    repair = summary["repair"]
    route_repair = summary["route_repair"]
    lines: List[str] = []
    lines.append("# P4 模板基准 scoreboard（baseline vs route repair）\n")
    lines.append(f"- schema：`{report['schema']}`")
    lines.append(
        f"- 配置：{len(config['templates'])} 模板 × seeds {config['seeds']} × 模式 baseline/repair；"
        f"solver steps={config['steps']}；router {config['router']}"
    )
    lines.append(f"- 运行：{batch['n_runs']} 次 pipeline（{batch['n_pairs']} 组配对），耗时 {report['runtime_s']} s\n")

    lines.append("## 汇总\n")
    lines.append("| 模式 | completion 均值 | 全布通 | truth_v1 均值 | truth_v2 均值 | 失败网络合计 | vias 合计 | route_calls 合计 |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for label, block in (("baseline", baseline), ("repair", repair)):
        lines.append(
            f"| {label} | {_fmt(block['mean_completion'])} | {block['fully_routed']} | "
            f"{_fmt(block['mean_truth_v1'])} | {_fmt(block['mean_truth_v2'])} | "
            f"{block['failed_nets_total']} | {_fmt_int(block['vias_total'])} | "
            f"{_fmt_int(block['route_calls_total'])} |"
        )
    lines.append("")
    lines.append("## route repair 判定\n")
    degradation = route_repair["truth_v2_degradation_pct"]
    verdict = "PASS" if route_repair["truth_not_worse_than_limit"] else "FAIL"
    lines.append(
        f"- truth_v2 均值变化：{_fmt(baseline['mean_truth_v2'])} → {_fmt(repair['mean_truth_v2'])}"
        f"（{_fmt_pct(degradation)}，门槛 ≤ +{route_repair['truth_degradation_limit_pct']:.1f}% → **{verdict}**）"
    )
    lines.append(
        f"- completion 均值变化：{_fmt(route_repair['completion_mean_delta'])}；"
        f"单组 truth 不变差：{route_repair['runs_truth_not_worse']}"
    )
    lines.append(f"- 全部硬可行：**{batch['all_feasible']}**\n")

    lines.append("## 逐模板（seeds 内均值）\n")
    lines.append("| 模板 | completion baseline | completion repair | truth_v2 baseline | truth_v2 repair | Δtruth | 全可行 | repair 失败网 |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for row in _per_template(report["rows"], config["templates"]):
        lines.append(
            f"| {row['template']} | {_fmt(row['completion_baseline'])} | {_fmt(row['completion_repair'])} | "
            f"{_fmt(row['truth_v2_baseline'])} | {_fmt(row['truth_v2_repair'])} | "
            f"{_fmt(row['delta_truth'])} | {row['feasible']} | {row['repair_failed_nets']} |"
        )
    lines.append("")
    lines.append("## 逐模板 × seed\n")
    lines.append("| 模板 | seed | feasible b/r | completion b→r | truth_v2 b→r | repair failed_nets | repair route_calls |")
    lines.append("|---|---|---|---|---|---|---|")
    for pair in summary["pairs"]:
        lines.append(
            f"| {pair['template']} | {pair['seed']} | "
            f"{_fmt(pair['completion_baseline'])}→{_fmt(pair['completion_repair'])} | "
            f"{_fmt(pair['truth_v2_baseline'])}→{_fmt(pair['truth_v2_repair'])} | "
            f"{pair['repair_failed_nets']} | {_fmt_int(pair['repair_route_calls'])} |"
        )
    lines.append("")
    lines.append("> 边界：所有数值来自离线 pipeline（proxy 目标 + v1/v2 伪物理 + 1mm/2 层网格 router oracle），")
    lines.append("> 不是真实布线/DRC/SI/PI/热验证；`routing_verified:false`、`drc:\"NOT RUN\"` 仍成立。")
    lines.append("> repair 的 truth_v2 若为正变化即表示真值变差，门槛为均值不劣于 baseline 的 5%。")
    return "\n".join(lines) + "\n"


def _fmt(value: Optional[float], digits: int = 4) -> str:
    if value is None:
        return "—"
    return f"{value:.{digits}f}"


def _fmt_int(value: Optional[int]) -> str:
    return "—" if value is None else str(value)


def _fmt_pct(value: Optional[float]) -> str:
    if value is None:
        return "—"
    return f"{value:+.2f}%"


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m mp_place.scoreboard",
        description="Template x seed baseline/route-repair scoreboard (offline).",
    )
    parser.add_argument("--json", action="store_true", help="print exactly one compact JSON object on stdout")
    parser.add_argument("--out", default=None, metavar="PATH", help="write the JSON scoreboard to PATH")
    parser.add_argument("--seeds", default="0,1", help="comma-separated seeds (default: 0,1)")
    parser.add_argument("--steps", type=int, default=DEFAULT_STEPS, help=f"solver move budget (default: {DEFAULT_STEPS})")
    parser.add_argument(
        "--templates",
        default=None,
        metavar="NAMES",
        help="comma-separated template names (default: all 8 registered templates)",
    )
    return parser


def _parse_names(raw: Optional[str]) -> Optional[List[str]]:
    if raw is None:
        return None
    names = [part.strip() for part in raw.split(",") if part.strip()]
    return names or None


def main(argv: Optional[Sequence[str]] = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):  # pragma: no cover - exotic streams
            pass
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.steps < 0:
        parser.error("--steps must be >= 0")
    try:
        seeds = [int(part) for part in args.seeds.split(",") if part.strip()]
    except ValueError:
        parser.error("--seeds must be comma-separated integers")
    if not seeds or min(seeds) < 0:
        parser.error("--seeds must be non-empty and >= 0")
    templates = _parse_names(args.templates)
    try:
        report = run_scoreboard(templates=templates, seeds=seeds, steps=args.steps)
    except (KeyError, ValueError) as exc:
        message = exc.args[0] if exc.args else str(exc)
        print(f"error: {message}", file=sys.stderr)
        return 2

    if args.out:
        out_path = pathlib.Path(args.out)
        if out_path.parent and not out_path.parent.exists():
            out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"[scoreboard] wrote {out_path}", file=sys.stderr)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    else:
        print(render_markdown(report))
        summary = report["summary"]
        print(
            f"[scoreboard] runs={summary['batch']['n_runs']} "
            f"all_feasible={summary['batch']['all_feasible']} "
            f"completion {summary['baseline']['mean_completion']}->{summary['repair']['mean_completion']} "
            f"truth_v2 degradation={summary['route_repair']['truth_v2_degradation_pct']}%",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "SCOREBOARD_SCHEMA",
    "DEFAULT_SEEDS",
    "DEFAULT_STEPS",
    "MODES",
    "TRUTH_DEGRADATION_LIMIT_PCT",
    "run_scoreboard",
    "render_markdown",
    "main",
]
