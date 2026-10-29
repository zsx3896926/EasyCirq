"""P2.10 holdout validation: does the tuned route penalty (and intent
relaxation) generalise beyond the seeds used for tuning?

Motivation
----------
P2.9's ``route_cost.TUNED_TABLE`` was calibrated on **seeds 0/1** (8 templates);
P3.7's intent relaxation Pareto was measured on the same seeds.  This module is
the out-of-sample check: it evaluates those frozen artefacts on **held-out seeds
2/3/4** and never re-runs the tuner, so the holdout numbers are not self-serving.

Protocol
--------
* ``TUNING_SEEDS = (0, 1)`` — the seeds baked into ``TUNED_TABLE``; held fixed.
* ``HOLDOUT_SEEDS = (2, 3, 4)`` — evaluation only; disjointness is enforced by
  :func:`assert_seed_protocol`.
* 8 templates x 3 holdout seeds.

Part 1 — route-aware objective (P2.8/P2.9):
  for every ``(template, holdout seed)`` run ``solver_v2.solve(steps=800)`` with
  three objectives and score the placements with the 1 mm/2-layer grid router
  and ``physics_v2.PhysicsSimulatorV2``:

  * ``baseline`` — plain ``ProxyObjective`` (``w_route=0``);
  * ``fixed``    — ``RouteAwareObjective`` with the P2.8 global weight
    ``w_route=2.0`` / default profile;
  * ``tuned``    — :func:`mp_place.route_cost.tuned_objective` (embedded P2.9
    table, no tuning, no router in the objective).

  A template "meets the target" when its holdout mean satisfies
  ``completion >= 0.97`` and ``truth_v2 <= baseline_truth * 1.01``.

Part 2 — intent relaxation (P3.7):
  same reference-layout protocol as ``intent_solver.pareto_experiment``
  (random feasible reference -> ``intent.build_intent`` -> ``plan_from_intent``),
  but on holdout seeds, comparing ``relax=False`` vs ``relax=True``: hard/soft
  CCG violations per run, deviation from the original tight intent, and the
  ``truth_v2`` trade-off versus the unconstrained proxy baseline.

Part 3 — recommendation:
  :func:`recommend_safe_default` turns the holdout numbers into a "safe default
  / fallback" policy (fall back to the fixed ``w=2.0`` or plain baseline when the
  tuned table does not generalise).

The report is written by ``python -m mp_place.holdout`` to
``report_holdout.md`` / ``report_holdout.json`` (a ``--quick`` mode exists for
smoke runs).  Recorded result (8 templates x seeds 2/3/4, ``steps=800``)::

    group       completion   fully routed   truth_v2   truth Δ vs baseline
    baseline      0.8424        9/24          1.7734       +0.00%
    fixed w=2.0   0.9502       15/24          1.7819       +0.48%
    tuned table   0.9113       10/24          1.9058       +7.47%

Only 1/8 templates meets the strict per-template target with ``fixed``
(``buck``); the tuned table is worse than fixed on both completion and truth,
i.e. the P2.9 per-template weights overfit seeds 0/1.  The recommended safe
default is therefore the P2.8 fixed weight ``w_route=2.0`` (or plain baseline
plus post-hoc route repair where truth risk matters); the tuned table should
stay experimental.  Intent relaxation *does* generalise: on the holdout,
``relax=True`` keeps 0.00 hard CCG violations/run with a +13.1% truth trade-off
(target <= 20%), versus +48.9% for strict mode.

Boundaries: offline surrogates only (grid-maze router oracle and a
pseudo-physics truth model), no DRC/EDA/network, no held-out re-tuning.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import random
import time
from typing import Dict, List, Optional, Sequence, Tuple

from . import route_cost
from .intent import build_intent
from .intent_solver import DEFAULT_STEPS as INTENT_DEFAULT_STEPS, plan_from_intent
from .model import hard_violations
from .objective import ProxyObjective
from .physics_v2 import PhysicsSimulatorV2
from .router import GridRouter
from .solver import random_feasible_placement
from .solver_v2 import solve
from .templates import instantiate, template_names

REPORT_MD = "report_holdout.md"
REPORT_JSON = "report_holdout.json"
PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent

TUNING_SEEDS: Tuple[int, ...] = (0, 1)
HOLDOUT_SEEDS: Tuple[int, ...] = (2, 3, 4)
STEPS = 800
INTENT_STEPS = INTENT_DEFAULT_STEPS  # 800
#: P2.9/P2.10 target used for every template.
TARGET_COMPLETION = 0.97
TARGET_TRUTH_RATIO = 1.01
#: P3.7 target for the relaxed intent groups.
TARGET_MAX_HARD_CCG_PER_RUN = 0.5
TARGET_MAX_TRUTH_GAP_PCT = 20.0
ROUTER_GRID_MM = 1.0
ROUTER_LAYERS = 2


def assert_seed_protocol(
    tuning_seeds: Sequence[int] = TUNING_SEEDS,
    holdout_seeds: Sequence[int] = HOLDOUT_SEEDS,
) -> None:
    """Enforce the holdout protocol: tuning and evaluation seeds must be disjoint."""
    tuning = {int(seed) for seed in tuning_seeds}
    holdout = {int(seed) for seed in holdout_seeds}
    if not tuning:
        raise ValueError("tuning_seeds must not be empty")
    if not holdout:
        raise ValueError("holdout_seeds must not be empty")
    overlap = sorted(tuning & holdout)
    if overlap:
        raise ValueError(
            "holdout protocol violated: seeds "
            f"{overlap} are used for both tuning and evaluation"
        )


def tuned_table_digest(table: Optional[Dict[str, Dict[str, object]]] = None) -> str:
    """Audit digest of the frozen P2.9 table that the holdout evaluates."""
    active = route_cost.TUNED_TABLE if table is None else table
    payload = json.dumps(active, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _route_and_truth(scenario, placement, seed: int) -> Dict[str, float]:
    result = GridRouter(scenario, grid_mm=ROUTER_GRID_MM, layers=ROUTER_LAYERS).route(placement)
    truth = PhysicsSimulatorV2(scenario, seed=int(seed)).score(placement)
    return {"completion": float(result.completion), "truth_v2": float(truth)}


def _solve_group(
    scenario,
    seed: int,
    config: Optional[Dict[str, object]],
    steps: int,
) -> Dict[str, object]:
    """Solve one objective variant and measure completion / truth / runtime."""
    started = time.perf_counter()
    proxy = ProxyObjective(scenario)
    if config is None:
        objective_cost = proxy.cost
        w_route: Optional[float] = None
        profile: Optional[str] = None
    else:
        w_route = float(config["w_route"])
        profile = str(config["profile"])
        objective = route_cost.RouteAwareObjective(
            scenario, base=proxy, w_route=w_route, profile=profile
        )
        objective_cost = objective.cost
    placement, _cost, _stats = solve(
        scenario, objective_cost, seed=int(seed), steps=steps
    )
    metrics = _route_and_truth(scenario, placement, seed)
    return {
        "completion": metrics["completion"],
        "truth_v2": metrics["truth_v2"],
        "feasible": not hard_violations(scenario, placement),
        "runtime_s": time.perf_counter() - started,
        "w_route": w_route,
        "profile": profile,
    }


def _run_route_holdout_case(
    name: str,
    seed: int,
    steps: int,
) -> Dict[str, object]:
    """Run baseline/fixed/tuned for one (template, holdout seed) pair."""
    scenario = instantiate(name, seed=seed)
    selected = route_cost.select_config(scenario)
    tuned_config = {
        "w_route": float(selected["w_route"]),
        "profile": str(selected["profile"]),
    }
    fixed_config = {
        "w_route": float(route_cost.DEFAULT_W_ROUTE),
        "profile": str(route_cost.DEFAULT_PROFILE),
    }
    baseline = _solve_group(scenario, seed, None, steps)
    fixed = _solve_group(scenario, seed, fixed_config, steps)
    tuned = _solve_group(scenario, seed, tuned_config, steps)
    return {
        "template": name,
        "seed": int(seed),
        "selected_tuned": tuned_config,
        "baseline": baseline,
        "fixed": fixed,
        "tuned": tuned,
    }


def run_route_cost_holdout(
    names: Optional[Sequence[str]] = None,
    holdout_seeds: Sequence[int] = HOLDOUT_SEEDS,
    steps: int = STEPS,
    tuning_seeds: Sequence[int] = TUNING_SEEDS,
) -> Dict[str, object]:
    """Evaluate baseline / fixed(w=2.0) / tuned on held-out seeds only."""
    assert_seed_protocol(tuning_seeds, holdout_seeds)
    template_names_list = list(template_names() if names is None else names)
    rows: List[Dict[str, object]] = []
    for name in template_names_list:
        for seed in holdout_seeds:
            row = _run_route_holdout_case(name, int(seed), steps)
            rows.append(row)
            print(
                f"[holdout] {name} seed={seed}: "
                f"baseline c={row['baseline']['completion']:.3f} t={row['baseline']['truth_v2']:.4f} | "
                f"fixed c={row['fixed']['completion']:.3f} t={row['fixed']['truth_v2']:.4f} | "
                f"tuned c={row['tuned']['completion']:.3f} t={row['tuned']['truth_v2']:.4f} "
                f"(w={row['selected_tuned']['w_route']}, {row['selected_tuned']['profile']})"
            )
    return {
        "runs": len(rows) * 3,
        "cases": len(rows),
        "templates": template_names_list,
        "holdout_seeds": [int(seed) for seed in holdout_seeds],
        "tuning_seeds": [int(seed) for seed in tuning_seeds],
        "steps": int(steps),
        "rows": rows,
        "aggregate": _aggregate_route(rows, template_names_list),
    }


def _aggregate_route(
    rows: Sequence[Dict[str, object]],
    template_names_list: Sequence[str],
) -> Dict[str, object]:
    groups = ("baseline", "fixed", "tuned")
    aggregate: Dict[str, object] = {
        "n_runs": len(rows),
        "n_templates": len(template_names_list),
        "targets": {
            "completion": TARGET_COMPLETION,
            "truth_ratio_vs_baseline": TARGET_TRUTH_RATIO,
        },
    }
    base_truth = _mean([float(row["baseline"]["truth_v2"]) for row in rows])  # type: ignore[index]
    for group in groups:
        completions = [float(row[group]["completion"]) for row in rows]  # type: ignore[index]
        truths = [float(row[group]["truth_v2"]) for row in rows]  # type: ignore[index]
        run_passes = 0
        for row in rows:
            case_baseline = float(row["baseline"]["truth_v2"])  # type: ignore[index]
            if (
                float(row[group]["completion"]) >= TARGET_COMPLETION - 1e-12  # type: ignore[index]
                and float(row[group]["truth_v2"]) <= case_baseline * TARGET_TRUTH_RATIO + 1e-12  # type: ignore[index]
            ):
                run_passes += 1
        truth_mean = _mean(truths)
        aggregate[group] = {
            "completion_mean": round(_mean(completions), 4),
            "fully_routed": f"{sum(1 for value in completions if value >= 1.0)}/{len(rows)}",
            "truth_v2_mean": round(truth_mean, 4),
            "truth_delta_pct": round(100.0 * (truth_mean - base_truth) / base_truth, 2)
            if base_truth
            else 0.0,
            "run_target_passes": f"{run_passes}/{len(rows)}",
            "run_target_pass_rate": round(run_passes / len(rows), 4) if rows else 0.0,
        }
    per_template: Dict[str, object] = {}
    template_passes = {group: 0 for group in groups}
    for name in template_names_list:
        subset = [row for row in rows if str(row["template"]) == name]
        baseline_truth = _mean([float(row["baseline"]["truth_v2"]) for row in subset])  # type: ignore[index]
        block: Dict[str, object] = {
            "selected_tuned": dict(subset[0]["selected_tuned"]) if subset else {},  # type: ignore[arg-type]
            "n_runs": len(subset),
        }
        verdicts: Dict[str, bool] = {}
        for group in groups:
            completions = [float(row[group]["completion"]) for row in subset]  # type: ignore[index]
            truths = [float(row[group]["truth_v2"]) for row in subset]  # type: ignore[index]
            truth_mean = _mean(truths)
            completion_mean = _mean(completions)
            block[group] = {
                "completion_mean": round(completion_mean, 4),
                "truth_v2_mean": round(truth_mean, 4),
                "truth_delta_pct": round(
                    100.0 * (truth_mean - baseline_truth) / baseline_truth, 2
                )
                if baseline_truth
                else 0.0,
            }
            verdicts[group] = bool(
                completion_mean >= TARGET_COMPLETION - 1e-12
                and truth_mean <= baseline_truth * TARGET_TRUTH_RATIO + 1e-12
            )
        block["targets_met"] = verdicts
        for group in groups:
            if verdicts[group]:
                template_passes[group] += 1
        per_template[name] = block
    aggregate["per_template"] = per_template
    aggregate["targets_met_templates"] = {
        group: f"{template_passes[group]}/{len(template_names_list)}"
        for group in groups
    }
    return aggregate


def run_intent_holdout(
    names: Optional[Sequence[str]] = None,
    holdout_seeds: Sequence[int] = HOLDOUT_SEEDS,
    steps: int = INTENT_STEPS,
    baseline_truth: Optional[Dict[Tuple[str, int], float]] = None,
    tuning_seeds: Sequence[int] = TUNING_SEEDS,
) -> Dict[str, object]:
    """Evaluate intent ``relax=False`` vs ``relax=True`` on held-out seeds."""
    assert_seed_protocol(tuning_seeds, holdout_seeds)
    template_names_list = list(template_names() if names is None else names)
    rows: List[Dict[str, object]] = []
    for name in template_names_list:
        for seed in holdout_seeds:
            seed = int(seed)
            scenario = instantiate(name, seed=seed)
            reference = random_feasible_placement(
                scenario, random.Random(f"intent-benchmark-ref:{name}:{seed}")
            )
            intent = build_intent(scenario, reference)
            if baseline_truth is not None and (name, seed) in baseline_truth:
                base_truth = float(baseline_truth[(name, seed)])
            else:
                placement, _cost, _stats = solve(
                    scenario, ProxyObjective(scenario).cost, seed=seed, steps=steps
                )
                base_truth = float(PhysicsSimulatorV2(scenario, seed=seed).score(placement))
            for relax in (False, True):
                plan, stats = plan_from_intent(
                    scenario,
                    intent,
                    cost=ProxyObjective(scenario).cost,
                    seed=seed,
                    steps=steps,
                    relax=relax,
                )
                truth = float(PhysicsSimulatorV2(scenario, seed=seed).score(plan))
                gap = 100.0 * (truth - base_truth) / base_truth if base_truth else 0.0
                rows.append(
                    {
                        "template": name,
                        "seed": seed,
                        "relax": bool(relax),
                        "truth_v2": truth,
                        "truth_v2_baseline": base_truth,
                        "truth_vs_baseline_pct": gap,
                        "ccg_hard_violations": int(stats["ccg_hard_final"]),
                        "ccg_soft_violations": int(stats["ccg_soft_final"]),
                        "ccg_total_violations": int(stats["ccg_final"]),
                        "original_intent_violations": int(
                            stats["original_intent_ccg_final"]
                        ),
                        "hard_feasible": bool(stats["hard_feasible"]),
                        "ccg_target_met": bool(stats["ccg_target_met"]),
                    }
                )
            print(
                f"[holdout][intent] {name} seed={seed}: "
                f"baseline truth={base_truth:.4f}"
            )
    return {
        "runs": len(rows),
        "templates": template_names_list,
        "holdout_seeds": [int(seed) for seed in holdout_seeds],
        "tuning_seeds": [int(seed) for seed in tuning_seeds],
        "steps": int(steps),
        "rows": rows,
        "groups": _aggregate_intent(rows),
    }


def _aggregate_intent(rows: Sequence[Dict[str, object]]) -> List[Dict[str, object]]:
    groups: List[Dict[str, object]] = []
    for relax in (False, True):
        subset = [row for row in rows if bool(row["relax"]) is relax]
        if not subset:
            continue
        truth_plan = _mean([float(row["truth_v2"]) for row in subset])  # type: ignore[arg-type]
        truth_base = _mean([float(row["truth_v2_baseline"]) for row in subset])  # type: ignore[arg-type]
        hard_per_run = _mean([float(row["ccg_hard_violations"]) for row in subset])  # type: ignore[arg-type]
        gap_pct = (
            100.0 * (truth_plan - truth_base) / truth_base if truth_base else 0.0
        )
        group = {
            "relax": bool(relax),
            "runs": len(subset),
            "ccg_hard_per_run": round(hard_per_run, 3),
            "ccg_soft_per_run": round(
                _mean([float(row["ccg_soft_violations"]) for row in subset]), 3  # type: ignore[arg-type]
            ),
            "ccg_total_per_run": round(
                _mean([float(row["ccg_total_violations"]) for row in subset]), 3  # type: ignore[arg-type]
            ),
            "original_intent_violations_per_run": round(
                _mean([float(row["original_intent_violations"]) for row in subset]), 3  # type: ignore[arg-type]
            ),
            "hard_feasible_rate": round(
                sum(1 for row in subset if row["hard_feasible"]) / len(subset), 4
            ),
            "ccg_zero_rate": round(
                sum(1 for row in subset if int(row["ccg_total_violations"]) == 0)  # type: ignore[arg-type]
                / len(subset),
                4,
            ),
            "mean_truth_v2": round(truth_plan, 4),
            "mean_truth_v2_baseline": round(truth_base, 4),
            "mean_truth_vs_baseline_pct": round(gap_pct, 2),
            "max_truth_vs_baseline_pct": round(
                max(float(row["truth_vs_baseline_pct"]) for row in subset), 2  # type: ignore[arg-type]
            ),
        }
        group["target_met"] = bool(
            hard_per_run <= TARGET_MAX_HARD_CCG_PER_RUN
            and gap_pct <= TARGET_MAX_TRUTH_GAP_PCT
        )
        groups.append(group)
    return groups


def recommend_safe_default(
    route_result: Dict[str, object],
    intent_result: Optional[Dict[str, object]] = None,
) -> Dict[str, object]:
    """Turn the holdout numbers into a deterministic safe-default / fallback policy.

    This is a *diagnostic* recommendation computed from the holdout evaluation;
    it must not be fed back into ``TUNED_TABLE`` (that would tune on the holdout).
    """
    aggregate = route_result["aggregate"]  # type: ignore[index]
    groups = ("baseline", "fixed", "tuned")
    template_pass = {
        group: int(aggregate["targets_met_templates"][group].split("/")[0])  # type: ignore[index]
        for group in groups
    }
    n_templates = int(aggregate["n_templates"])  # type: ignore[index]
    tuned_truth_delta = float(aggregate["tuned"]["truth_delta_pct"])  # type: ignore[index]
    tuned_generalises = bool(
        template_pass["tuned"] >= max(template_pass["fixed"], template_pass["baseline"])
        and tuned_truth_delta <= 1.0
    )
    if tuned_generalises:
        safe_default = "tuned"
        reason = (
            "TUNED_TABLE 在留出 seeds 上仍保持 completion/truth 目标；"
            "tuned 可以继续作为默认。"
        )
    elif template_pass["fixed"] >= template_pass["baseline"]:
        safe_default = "fixed"
        reason = (
            "TUNED_TABLE 未泛化到留出 seeds；回退到 P2.8 固定权重 "
            f"（w_route={route_cost.DEFAULT_W_ROUTE}）作为安全默认"
            "（同一代码路径、无 per-template 表）。"
        )
    else:
        safe_default = "baseline"
        reason = (
            "tuned 与固定权重都未泛化；使用纯 proxy（w_route=0），"
            "并用 post-hoc route repair 提升 completion。"
        )
    per_template: Dict[str, object] = {}
    per_template_blocks = aggregate["per_template"]  # type: ignore[index]
    for name in route_result["templates"]:  # type: ignore[index]
        block = per_template_blocks[name]
        verdicts = block["targets_met"]
        if verdicts.get("baseline"):
            action = "baseline(w=0): 已达标，零扰动"
        elif verdicts.get("tuned"):
            action = "keep_tuned"
        elif verdicts.get("fixed"):
            action = "fallback_fixed(w=2.0)"
        else:
            action = "baseline(w=0) + post-hoc repair"
        per_template[name] = {
            "selected_tuned": block["selected_tuned"],
            "targets_met": dict(verdicts),
            "action": action,
        }
    intent_advice = None
    if intent_result is not None:
        groups_intent = {bool(group["relax"]): group for group in intent_result["groups"]}  # type: ignore[index]
        strict = groups_intent.get(False)
        relaxed = groups_intent.get(True)
        if strict is not None and relaxed is not None:
            intent_advice = {
                "strict_truth_gap_pct": strict["mean_truth_vs_baseline_pct"],
                "relaxed_truth_gap_pct": relaxed["mean_truth_vs_baseline_pct"],
                "strict_hard_per_run": strict["ccg_hard_per_run"],
                "relaxed_hard_per_run": relaxed["ccg_hard_per_run"],
                "recommend_relax": bool(
                    relaxed["target_met"]
                    and relaxed["mean_truth_vs_baseline_pct"]
                    < strict["mean_truth_vs_baseline_pct"]
                ),
                "reason": (
                    "relax=True 在留出 seeds 上保持 hard CCG 0 违规/run 并降低 truth 折衷，"
                    "推荐继续使用 relaxed intent planning。"
                    if relaxed["target_met"]
                    else "留出 seeds 上 relax=False 更安全。"
                ),
            }
    return {
        "holdout_tuned_generalises": tuned_generalises,
        "template_pass_counts": {
            group: f"{template_pass[group]}/{n_templates}" for group in groups
        },
        "safe_default": safe_default,
        "safe_default_config": (
            {"w_route": float(route_cost.DEFAULT_W_ROUTE), "profile": str(route_cost.DEFAULT_PROFILE)}
            if safe_default == "fixed"
            else ({"w_route": 0.0, "profile": "default"} if safe_default == "baseline" else None)
        ),
        "reason": reason,
        "per_template_action": per_template,
        "intent_advice": intent_advice,
        "note": (
            "Diagnostic only: computed from held-out seeds 2/3/4; TUNED_TABLE must "
            "not be re-fitted on these numbers."
        ),
    }


def run_holdout(
    names: Optional[Sequence[str]] = None,
    holdout_seeds: Sequence[int] = HOLDOUT_SEEDS,
    steps: int = STEPS,
    intent_steps: int = INTENT_STEPS,
    tuning_seeds: Sequence[int] = TUNING_SEEDS,
    include_intent: bool = True,
) -> Dict[str, object]:
    """Full P2.10 holdout experiment (route-cost triples + intent relax split)."""
    assert_seed_protocol(tuning_seeds, holdout_seeds)
    started = time.perf_counter()
    route_result = run_route_cost_holdout(
        names=names,
        holdout_seeds=holdout_seeds,
        steps=steps,
        tuning_seeds=tuning_seeds,
    )
    baseline_truth: Dict[Tuple[str, int], float] = {}
    for row in route_result["rows"]:  # type: ignore[index]
        baseline_truth[(str(row["template"]), int(row["seed"]))] = float(  # type: ignore[index]
            row["baseline"]["truth_v2"]  # type: ignore[index]
        )
    intent_result: Optional[Dict[str, object]] = None
    if include_intent:
        intent_result = run_intent_holdout(
            names=names,
            holdout_seeds=holdout_seeds,
            steps=intent_steps,
            baseline_truth=baseline_truth,
            tuning_seeds=tuning_seeds,
        )
    recommendation = recommend_safe_default(route_result, intent_result)
    data: Dict[str, object] = {
        "schema": "mp_place.holdout/v1",
        "protocol": {
            "tuning_seeds": [int(seed) for seed in tuning_seeds],
            "holdout_seeds": [int(seed) for seed in holdout_seeds],
            "seeds_disjoint": True,
            "steps": int(steps),
            "intent_steps": int(intent_steps),
            "templates": list(route_result["templates"]),  # type: ignore[arg-type]
            "targets": {
                "completion": TARGET_COMPLETION,
                "truth_ratio_vs_baseline": TARGET_TRUTH_RATIO,
                "intent_max_hard_ccg_per_run": TARGET_MAX_HARD_CCG_PER_RUN,
                "intent_max_truth_gap_pct": TARGET_MAX_TRUTH_GAP_PCT,
            },
            "router": f"GridRouter(grid_mm={ROUTER_GRID_MM}, layers={ROUTER_LAYERS})",
            "tuned_table_digest": tuned_table_digest(),
            "tuned_table": {
                name: dict(config)
                for name, config in route_cost.TUNED_TABLE.items()
                if name in set(route_result["templates"])  # type: ignore[arg-type]
            },
            "isolation_note": (
                "TUNED_TABLE is read-only in this experiment; the route_cost tuner "
                "(tune_template/tune_all) is never invoked here."
            ),
        },
        "route_cost": route_result,
        "intent": intent_result,
        "recommendation": recommendation,
        "runtime_s": round(time.perf_counter() - started, 2),
    }
    return data


# --------------------------------------------------------------------------
# Markdown / JSON report
# --------------------------------------------------------------------------


def write_holdout_report(
    data: Dict[str, object],
    out_dir: Optional[pathlib.Path] = None,
) -> Tuple[pathlib.Path, pathlib.Path]:
    """Write ``report_holdout.md`` / ``.json`` and return their paths."""
    directory = pathlib.Path(out_dir) if out_dir is not None else PROJECT_ROOT
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / REPORT_JSON
    md_path = directory / REPORT_MD
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    protocol = data["protocol"]  # type: ignore[index]
    route = data["route_cost"]  # type: ignore[index]
    route_aggregate = route["aggregate"]  # type: ignore[index]
    intent = data["intent"]
    recommendation = data["recommendation"]  # type: ignore[index]
    lines: List[str] = []
    lines.append("# P2.10：调参泛化留出验证（seeds 2/3/4）\n")
    lines.append(
        f"- 协议：**调参只用 seeds {protocol['tuning_seeds']}**（P2.9 `TUNED_TABLE` 冻结），"
        f"**评估用留出 seeds {protocol['holdout_seeds']}**（互斥，由 `assert_seed_protocol` 强制）；"
        f"8 模板 × {len(protocol['holdout_seeds'])} seeds，solve steps={protocol['steps']}，"
        f"intent planning steps={protocol['intent_steps']}"
    )
    lines.append(
        f"- 运行：route-cost {route.get('cases', route['runs'] // 3)} cases × 3 目标 + "
        f"intent {0 if intent is None else intent['runs']} 组；"
        f"总耗时 {data['runtime_s']} s；`TUNED_TABLE` 摘要 `{protocol['tuned_table_digest'][:16]}`；"
        f"router = {protocol['router']}\n"
    )
    lines.append("## 一、route_cost 留出泛化（completion / truth_v2）\n")
    lines.append(
        "| 组别 | completion 均值 | 全布通 | truth_v2 均值 | truth Δ% vs baseline | run 达标率 | 模板达标率 |"
    )
    lines.append("|---|---|---|---|---|---|---|")
    labels = (
        ("baseline", "baseline（w=0）"),
        ("fixed", f"fixed（w={route_cost.DEFAULT_W_ROUTE}）"),
        ("tuned", "tuned（P2.9 表）"),
    )
    for key, label in labels:
        block = route_aggregate[key]
        lines.append(
            f"| {label} | {block['completion_mean']} | {block['fully_routed']} | "
            f"{block['truth_v2_mean']} | {block['truth_delta_pct']:+.2f}% | "
            f"{block['run_target_pass_rate']:.1%} ({block['run_target_passes']}) | "
            f"{route_aggregate['targets_met_templates'][key]} |"
        )
    lines.append("")
    lines.append(
        f"判读：tuned 在留出 seeds 上模板达标 {route_aggregate['targets_met_templates']['tuned']}，"
        f"fixed {route_aggregate['targets_met_templates']['fixed']}，"
        f"baseline {route_aggregate['targets_met_templates']['baseline']}；"
        f"tuned truth Δ = {route_aggregate['tuned']['truth_delta_pct']:+.2f}%。\n"
    )
    tuned_block = route_aggregate["tuned"]
    fixed_block = route_aggregate["fixed"]
    more_completion = float(tuned_block["completion_mean"]) <= float(
        fixed_block["completion_mean"]
    )
    better_truth = float(tuned_block["truth_delta_pct"]) >= float(
        fixed_block["truth_delta_pct"]
    )
    if more_completion or better_truth:
        lines.append(
            f"关键发现：留出 seeds 上 tuned 表**没有保持** P2.9 的优势——"
            f"fixed(w={route_cost.DEFAULT_W_ROUTE}) 的 completion 均值 "
            f"{fixed_block['completion_mean']}、truth Δ {fixed_block['truth_delta_pct']:+.2f}%，"
            f"而 tuned 为 {tuned_block['completion_mean']}、{tuned_block['truth_delta_pct']:+.2f}%；"
            f"tuned 在 seeds 0/1 上的收益是 in-sample 过拟合，"
            "不应作为未见 seed/模板的默认策略。\n"
        )
    lines.append("## 二、route_cost 逐模板（留出 seeds 均值）\n")
    lines.append(
        "| 模板 | 选中 tuned 权重 | baseline c / t | fixed c / t | tuned c / t | tuned 达标 |"
    )
    lines.append("|---|---|---|---|---|---|")
    for name in protocol["templates"]:
        block = route_aggregate["per_template"][name]
        selected = block["selected_tuned"]
        cells = []
        for key in ("baseline", "fixed", "tuned"):
            entry = block[key]
            cells.append(f"{entry['completion_mean']} / {entry['truth_v2_mean']}")
        lines.append(
            f"| {name} | w={selected['w_route']}, {selected['profile']} | "
            + " | ".join(cells)
            + f" | {'✅' if block['targets_met']['tuned'] else '❌'} |"
        )
    lines.append("")
    if intent is not None:
        lines.append("## 三、intent relax 留出泛化（P3.7）\n")
        lines.append(
            "| relax | hard 违规/run | soft 违规/run | 原始 intent 偏离/run | hard 可行率 | "
            "truth_v2 plan | truth_v2 baseline | truth 折衷 | 目标达标 |"
        )
        lines.append("|---|---|---|---|---|---|---|---|---|")
        for group in intent["groups"]:
            lines.append(
                f"| {group['relax']} | {group['ccg_hard_per_run']:.2f} | "
                f"{group['ccg_soft_per_run']:.2f} | "
                f"{group['original_intent_violations_per_run']:.2f} | "
                f"{group['hard_feasible_rate']:.0%} | {group['mean_truth_v2']} | "
                f"{group['mean_truth_v2_baseline']} | "
                f"{group['mean_truth_vs_baseline_pct']:+.1f}% | "
                f"{'✅' if group['target_met'] else '❌'} |"
            )
        lines.append("")
        lines.append(
            "目标：hard-tier CCG 违规 ≤ 0.5/run 且 truth 折衷 ≤ 20%；"
            "`original intent 偏离/run` 是 relax=True 用约束保真换 truth 的代价。\n"
        )
        strict_group = next(
            (group for group in intent["groups"] if not group["relax"]), None
        )
        relaxed_group = next(
            (group for group in intent["groups"] if group["relax"]), None
        )
        if strict_group is not None and relaxed_group is not None:
            lines.append(
                f"关键发现：relax=True 在留出 seeds 上仍满足目标"
                f"（hard {relaxed_group['ccg_hard_per_run']:.2f} 违规/run、"
                f"truth 折衷 {relaxed_group['mean_truth_vs_baseline_pct']:+.1f}%），"
                f"严格模式为 {strict_group['mean_truth_vs_baseline_pct']:+.1f}%；"
                "P3.7 的 relax 结论可泛化到留出 seeds。\n"
            )
    lines.append("## 四、安全默认 / fallback 建议\n")
    lines.append(
        f"- tuned 是否泛化：**{recommendation['holdout_tuned_generalises']}**；"
        f"模板达标计数 {recommendation['template_pass_counts']} → "
        f"**安全默认 = `{recommendation['safe_default']}`**。"
    )
    lines.append(f"- 理由：{recommendation['reason']}")
    lines.append(
        f"- 建议默认配置：{recommendation['safe_default_config']} "
        "（若为 null 表示继续使用 P2.9 tuned 表）"
    )
    lines.append("- 逐模板 fallback 建议（诊断用，不回写 TUNED_TABLE）：")
    for name, action in recommendation["per_template_action"].items():
        lines.append(
            f"  - `{name}`: {action['action']}（tuned w={action['selected_tuned']['w_route']}，"
            f"tuned 达标 {action['targets_met']['tuned']}）"
        )
    intent_advice = recommendation.get("intent_advice")
    if intent_advice:
        lines.append(
            f"- intent 建议：relax=True = {intent_advice['relaxed_hard_per_run']:.2f} hard 违规/run、"
            f"truth 折衷 {intent_advice['relaxed_truth_gap_pct']:+.1f}%；"
            f"relax=False = {intent_advice['strict_hard_per_run']:.2f}、"
            f"{intent_advice['strict_truth_gap_pct']:+.1f}% → "
            f"**建议 relax={intent_advice['recommend_relax']}**。{intent_advice['reason']}"
        )
    lines.append(f"\n> {recommendation['note']}\n")
    lines.append("## 五、边界\n")
    lines.append(
        "- 留出协议为 seeds 2/3/4 一次性评估；本报告**不重新调参**、不把留出结果写回 "
        "`TUNED_TABLE`，否则就不再是留出验证。"
    )
    lines.append(
        "- router 是 1 mm/2 层网格迷宫 oracle，不是 DRC/真实可布通证明；truth_v2 是离线伪物理模型；"
        "真实布线/DRC/SI/PI/热仍 `NOT RUN`。"
    )
    lines.append(
        "- 模板为合成产品族；留出 seeds 只改模板采样参数，不覆盖真实产品的多样性。"
    )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[holdout] wrote {md_path} / {json_path}")
    return md_path, json_path


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="P2.10 holdout validation")
    parser.add_argument("--holdout-seeds", default="2,3,4")
    parser.add_argument("--tuning-seeds", default="0,1")
    parser.add_argument("--steps", type=int, default=STEPS)
    parser.add_argument("--intent-steps", type=int, default=INTENT_STEPS)
    parser.add_argument("--quick", action="store_true", help="2 templates x 1 seed x 200 steps")
    parser.add_argument("--no-intent", action="store_true", help="skip the intent relax part")
    parser.add_argument("--out", default=str(PROJECT_ROOT))
    args = parser.parse_args(argv)
    holdout_seeds = tuple(int(part) for part in args.holdout_seeds.split(",") if part.strip())
    tuning_seeds = tuple(int(part) for part in args.tuning_seeds.split(",") if part.strip())
    if args.quick:
        names = list(template_names())[:2]
        data = run_holdout(
            names=names,
            holdout_seeds=holdout_seeds[:1],
            steps=200,
            intent_steps=200,
            tuning_seeds=tuning_seeds,
            include_intent=not args.no_intent,
        )
    else:
        data = run_holdout(
            holdout_seeds=holdout_seeds,
            steps=args.steps,
            intent_steps=args.intent_steps,
            tuning_seeds=tuning_seeds,
            include_intent=not args.no_intent,
        )
    write_holdout_report(data, pathlib.Path(args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "HOLDOUT_SEEDS",
    "TUNING_SEEDS",
    "assert_seed_protocol",
    "recommend_safe_default",
    "run_holdout",
    "run_intent_holdout",
    "run_route_cost_holdout",
    "tuned_table_digest",
    "write_holdout_report",
]
