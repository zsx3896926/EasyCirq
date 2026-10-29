"""P2.12 cross-validated route-cost tuning: does CV fix the P2.9 overfit?

P2.9 selected one ``(w_route, profile)`` per template on seeds 0/1 and P2.10
showed that table does not generalise to held-out seeds.  This module replaces
the single-table search with a (small, explainable) **2-fold cross-validation**
over the tuning seeds ``{0, 1, 2}`` and evaluates the resulting per-template
configuration on strictly held-out seeds ``{3, 4}``.

Protocol
--------
* Tuning seeds: ``(0, 1, 2)``.  Two folds, each holding out exactly one seed
  (with only three seeds a strict partition into 2 x 1 is impossible, so the
  third seed is the shared training anchor)::

      fold 0: train (1, 2)   validate (0,)
      fold 1: train (0, 2)   validate (1,)

  The CV score of a candidate is the mean metric over the two held-out folds
  (i.e. seeds 0/1); candidate weights need no fitting, so the grid search is
  scored directly by this CV score.
* Candidate grid (from the task): ``w_route in {0, 0.5, 1, 1.5, 2, 3, 4, 6}``
  x ``profile in {default, pad_heavy}`` (``w_route=0`` is profile-independent and
  evaluated once).  Selection objective: among candidates whose CV completion is
  ``>= 0.97`` pick the **minimum CV truth_v2**; if none reaches the target, fall
  back to the P2.8 fixed weight ``w_route=2.0``.
* Evaluation seeds: ``(3, 4)`` — disjoint from the tuning seeds and never used by
  any selection step (enforced by :func:`assert_seed_isolation`).
* 8 templates; every trial is ``solver_v2.solve(steps=800)`` scored by the
  1 mm/2-layer ``GridRouter`` and ``physics_v2.PhysicsSimulatorV2``.

Outputs
-------
``python -m mp_place.tune_cv`` writes ``report_tune_cv.md`` / ``.json`` with the
per-template CV-selected config, the in-CV vs held-out completion/truth_v2, a
``baseline(w=0)`` / ``fixed(w=2.0)`` / ``cv_tuned`` comparison on seeds 3/4, and
a deterministic safe-default recommendation.  If CV still fails to generalise
the recommendation is to default to the plain route-aware objective
(``w_route=2.0``) and disable the P2.9 per-template ``TUNED_TABLE``.

Router usage is confined to the evaluation helper (:func:`_evaluate_config`);
selection, aggregation and recommendation are pure functions (unit-tested with
the router mocked out).  Offline only: no DRC/EDA/network, synthetic templates,
surrogate router/truth.

Recorded result (8 templates, CV seeds 0/1/2, evaluation seeds 3/4, steps=800,
408 router calls, ~358 s)::

    group          completion   fully routed   truth_v2   truth Δ vs baseline   template pass
    baseline(w=0)    0.8420        6/16          1.8110       +0.00%               0/8
    fixed(w=2.0)     0.9477       10/16          1.7657       -2.50%               3/8
    CV-tuned         0.9444        9/16          1.9103       +5.48%               2/8

CV tuning does **not** fix the generalisation problem: the fixed route-aware
weight still beats CV-tuned on both completion and truth, and no template had
both folds select the same configuration (0/8 fold agreement).  The deterministic
recommendation is therefore: safe default = plain route-aware objective with
``w_route=2.0``, **disable** the P2.9 per-template ``route_cost.TUNED_TABLE``;
for truth-sensitive work use ``w=0`` + post-hoc route repair.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import time
from typing import Dict, List, Optional, Sequence, Tuple

from . import route_cost
from .model import hard_violations
from .objective import ProxyObjective
from .physics_v2 import PhysicsSimulatorV2
from .router import GridRouter
from .solver_v2 import solve
from .templates import instantiate, template_names

REPORT_MD = "report_tune_cv.md"
REPORT_JSON = "report_tune_cv.json"
PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent

CV_SEEDS: Tuple[int, ...] = (0, 1, 2)
EVAL_SEEDS: Tuple[int, ...] = (3, 4)
#: Two folds, each holding out one tuning seed (seed 2 anchors both trainings).
CV_FOLDS: Tuple[Dict[str, Tuple[int, ...]], ...] = (
    {"name": "fold0", "train": (1, 2), "validate": (0,)},
    {"name": "fold1", "train": (0, 2), "validate": (1,)},
)
W_GRID: Tuple[float, ...] = (0.0, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0)
PROFILES: Tuple[str, ...] = ("default", "pad_heavy")
TARGET_COMPLETION = 0.97
TARGET_TRUTH_RATIO = 1.01
STEPS = 800
ROUTER_GRID_MM = 1.0
ROUTER_LAYERS = 2
BASELINE_CONFIG: Dict[str, object] = {"w_route": 0.0, "profile": "default"}
FIXED_CONFIG: Dict[str, object] = {"w_route": 2.0, "profile": "default"}
GROUP_ORDER: Tuple[str, ...] = ("baseline", "fixed", "cv_tuned")


def assert_seed_isolation(
    tuning_seeds: Sequence[int] = CV_SEEDS,
    eval_seeds: Sequence[int] = EVAL_SEEDS,
) -> None:
    """CV tuning seeds and evaluation seeds must be disjoint and non-empty."""
    tuning = {int(seed) for seed in tuning_seeds}
    evaluation = {int(seed) for seed in eval_seeds}
    if not tuning:
        raise ValueError("tuning_seeds must not be empty")
    if not evaluation:
        raise ValueError("eval_seeds must not be empty")
    overlap = sorted(tuning & evaluation)
    if overlap:
        raise ValueError(
            "CV protocol violated: seeds "
            f"{overlap} are used for both tuning and evaluation"
        )


def candidate_grid(
    w_grid: Sequence[float] = W_GRID,
    profiles: Sequence[str] = PROFILES,
) -> List[Dict[str, object]]:
    """Deterministic candidate list; ``w=0`` is profile-independent (once)."""
    grid: List[Dict[str, object]] = [dict(BASELINE_CONFIG)]
    for w_route in w_grid:
        value = float(w_route)
        if value == 0.0:
            continue
        for profile in profiles:
            grid.append({"w_route": value, "profile": str(profile)})
    return grid


def config_key(config: Dict[str, object]) -> str:
    """Stable string key for a candidate configuration."""
    return f"w={float(config['w_route']):g}|profile={str(config['profile'])}"


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _rounded(value: float, digits: int = 6) -> float:
    return round(float(value), digits)


# ---------------------------------------------------------------------------
# Evaluation: the ONLY place that calls the router / solver.
# ---------------------------------------------------------------------------


def _evaluate_config(
    name: str,
    seed: int,
    config: Dict[str, object],
    steps: int,
) -> Dict[str, object]:
    """Solve one ``(template, seed, config)`` trial and score it.

    This is the single router-using helper.  Selection/aggregation code below
    never imports or calls the router itself.
    """
    started = time.perf_counter()
    scenario = instantiate(name, seed=int(seed))
    proxy = ProxyObjective(scenario)
    w_route = float(config["w_route"])
    profile = str(config["profile"])
    if w_route == 0.0:
        objective_cost = proxy.cost
    else:
        objective = route_cost.RouteAwareObjective(
            scenario, base=proxy, w_route=w_route, profile=profile
        )
        objective_cost = objective.cost
    placement, _cost, _stats = solve(
        scenario, objective_cost, seed=int(seed), steps=steps
    )
    result = GridRouter(scenario, grid_mm=ROUTER_GRID_MM, layers=ROUTER_LAYERS).route(placement)
    truth = PhysicsSimulatorV2(scenario, seed=int(seed)).score(placement)
    return {
        "completion": float(result.completion),
        "truth_v2": float(truth),
        "feasible": not hard_violations(scenario, placement),
        "runtime_s": time.perf_counter() - started,
    }


def evaluate_grid(
    name: str,
    seeds: Sequence[int],
    grid: Sequence[Dict[str, object]],
    steps: int,
) -> Dict[str, Dict[str, object]]:
    """Evaluate every candidate config on every tuning seed (evaluation only)."""
    matrix: Dict[str, Dict[str, object]] = {}
    for config in grid:
        key = config_key(config)
        per_seed: Dict[str, Dict[str, object]] = {}
        for seed in seeds:
            metrics = _evaluate_config(name, int(seed), config, steps)
            per_seed[str(int(seed))] = metrics
        matrix[key] = {
            "config": dict(config),
            "per_seed": per_seed,
            "completion_mean": _mean(
                [float(per_seed[str(int(seed))]["completion"]) for seed in seeds]
            ),
            "truth_mean": _mean(
                [float(per_seed[str(int(seed))]["truth_v2"]) for seed in seeds]
            ),
        }
    return matrix


# ---------------------------------------------------------------------------
# Pure selection / CV logic (no router calls).
# ---------------------------------------------------------------------------


def _validation_seeds(folds: Sequence[Dict[str, Tuple[int, ...]]] = CV_FOLDS) -> Tuple[int, ...]:
    seeds: List[int] = []
    for fold in folds:
        for seed in fold["validate"]:
            if int(seed) not in seeds:
                seeds.append(int(seed))
    return tuple(sorted(seeds))


def cv_metrics(
    record: Dict[str, object],
    folds: Sequence[Dict[str, Tuple[int, ...]]] = CV_FOLDS,
) -> Dict[str, object]:
    """CV score of one candidate: mean validation metrics over the held-out folds."""
    per_seed = record["per_seed"]  # type: ignore[index]
    fold_val_completions: List[float] = []
    fold_val_truths: List[float] = []
    fold_details: List[Dict[str, object]] = []
    for fold in folds:
        val_comp = _mean(
            [float(per_seed[str(int(seed))]["completion"]) for seed in fold["validate"]]  # type: ignore[index]
        )
        val_truth = _mean(
            [float(per_seed[str(int(seed))]["truth_v2"]) for seed in fold["validate"]]  # type: ignore[index]
        )
        train_comp = _mean(
            [float(per_seed[str(int(seed))]["completion"]) for seed in fold["train"]]  # type: ignore[index]
        )
        train_truth = _mean(
            [float(per_seed[str(int(seed))]["truth_v2"]) for seed in fold["train"]]  # type: ignore[index]
        )
        fold_val_completions.append(val_comp)
        fold_val_truths.append(val_truth)
        fold_details.append(
            {
                "fold": str(fold["name"]),
                "validate_seeds": [int(seed) for seed in fold["validate"]],
                "train_seeds": [int(seed) for seed in fold["train"]],
                "validation_completion": _rounded(val_comp),
                "validation_truth_v2": _rounded(val_truth),
                "train_completion": _rounded(train_comp),
                "train_truth_v2": _rounded(train_truth),
            }
        )
    return {
        "cv_completion": _mean(fold_val_completions),
        "cv_truth_v2": _mean(fold_val_truths),
        "folds": fold_details,
    }


def _candidate_rank(config: Dict[str, object]) -> Tuple[float, int]:
    profile_index = (
        route_cost.PROFILE_ORDER.index(str(config["profile"]))
        if str(config["profile"]) in route_cost.PROFILE_ORDER
        else len(route_cost.PROFILE_ORDER)
    )
    return float(config["w_route"]), profile_index


def select_cv_config(
    matrix: Dict[str, Dict[str, object]],
    target_completion: float = TARGET_COMPLETION,
    folds: Sequence[Dict[str, Tuple[int, ...]]] = CV_FOLDS,
) -> Dict[str, object]:
    """Deterministically pick one config per template from the CV scores.

    Rule (from the task): among candidates with CV completion ``>= target``,
    choose the minimum CV truth_v2 (tie-break: smaller ``w_route``, then profile
    order).  With no feasible candidate, fall back to :data:`FIXED_CONFIG`.
    """
    if not matrix:
        raise ValueError("select_cv_config requires a non-empty candidate matrix")
    scored: List[Dict[str, object]] = []
    for key in sorted(matrix):
        record = matrix[key]
        metrics = cv_metrics(record, folds)
        scored.append(
            {
                "key": key,
                "config": dict(record["config"]),  # type: ignore[arg-type]
                "cv_completion": float(metrics["cv_completion"]),
                "cv_truth_v2": float(metrics["cv_truth_v2"]),
                "folds": metrics["folds"],
                "tuning_completion_mean": float(record["completion_mean"]),
                "tuning_truth_mean": float(record["truth_mean"]),
            }
        )
    feasible = [
        entry
        for entry in scored
        if entry["cv_completion"] >= target_completion - 1e-12  # type: ignore[operator]
    ]
    if feasible:
        best = min(
            feasible,
            key=lambda entry: (
                float(entry["cv_truth_v2"]),
                *_candidate_rank(entry["config"]),  # type: ignore[arg-type]
            ),
        )
        selected_config = dict(best["config"])  # type: ignore[arg-type]
        selected_key = str(best["key"])
        cv_completion = _rounded(float(best["cv_completion"]))
        cv_truth = _rounded(float(best["cv_truth_v2"]))
        status = "cv_selected"
    else:
        # No CV candidate reaches the completion target: deterministic fallback.
        fixed_key = config_key(FIXED_CONFIG)
        fallback_entry = next(
            (entry for entry in scored if entry["key"] == fixed_key), None
        )
        selected_config = dict(FIXED_CONFIG)
        selected_key = fixed_key
        cv_completion = (
            _rounded(float(fallback_entry["cv_completion"]))
            if fallback_entry is not None
            else 0.0
        )
        cv_truth = (
            _rounded(float(fallback_entry["cv_truth_v2"]))
            if fallback_entry is not None
            else float("inf")
        )
        status = "fallback_fixed_no_cv_candidate"

    # Per-fold winners, for the "fold agreement" diagnostic.
    fold_winners: List[Optional[str]] = []
    for fold_index, fold in enumerate(folds):
        fold_pool = [
            entry
            for entry in scored
            if float(entry["folds"][fold_index]["validation_completion"])  # type: ignore[index]
            >= target_completion - 1e-12
        ]
        if not fold_pool:
            fold_winners.append(None)
            continue
        winner = min(
            fold_pool,
            key=lambda entry: (
                float(entry["folds"][fold_index]["validation_truth_v2"]),  # type: ignore[index]
                *_candidate_rank(entry["config"]),  # type: ignore[arg-type]
            ),
        )
        fold_winners.append(str(winner["key"]))
    return {
        "selected": selected_config,
        "selected_key": selected_key,
        "status": status,
        "cv_completion": cv_completion,
        "cv_truth_v2": cv_truth,
        "feasible_candidates": len(feasible),
        "fold_winners": fold_winners,
        "fold_agreement": bool(
            fold_winners and all(winner == selected_key for winner in fold_winners)
        ),
        "candidates": scored,
        "validation_seeds": [int(seed) for seed in _validation_seeds(folds)],
    }


# ---------------------------------------------------------------------------
# Full CV experiment (selection + held-out evaluation).
# ---------------------------------------------------------------------------


def _run_group(
    name: str,
    seed: int,
    config: Dict[str, object],
    steps: int,
) -> Dict[str, object]:
    return _evaluate_config(name, int(seed), config, steps)


def _aggregate_evaluation(
    rows: Sequence[Dict[str, object]],
    template_names_list: Sequence[str],
) -> Dict[str, object]:
    base_truth = _mean([float(row["baseline"]["truth_v2"]) for row in rows])  # type: ignore[index]
    aggregate: Dict[str, object] = {
        "n_runs": len(rows),
        "n_templates": len(template_names_list),
        "eval_seeds": sorted({int(row["seed"]) for row in rows}),
        "targets": {"completion": TARGET_COMPLETION, "truth_ratio": TARGET_TRUTH_RATIO},
    }
    for group in GROUP_ORDER:
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
            "completion_mean": _rounded(_mean(completions), 4),
            "fully_routed": f"{sum(1 for value in completions if value >= 1.0)}/{len(rows)}",
            "truth_v2_mean": _rounded(truth_mean, 4),
            "truth_delta_pct": _rounded(
                100.0 * (truth_mean - base_truth) / base_truth, 2
            )
            if base_truth
            else 0.0,
            "run_target_passes": f"{run_passes}/{len(rows)}",
            "run_target_pass_rate": _rounded(run_passes / len(rows), 4) if rows else 0.0,
        }
    per_template: Dict[str, object] = {}
    template_passes = {group: 0 for group in GROUP_ORDER}
    for name in template_names_list:
        subset = [row for row in rows if str(row["template"]) == name]
        block: Dict[str, object] = {
            "cv_config": dict(subset[0]["cv_config"]) if subset else {},  # type: ignore[arg-type]
            "n_runs": len(subset),
        }
        baseline_truth = _mean([float(row["baseline"]["truth_v2"]) for row in subset])  # type: ignore[index]
        verdicts: Dict[str, bool] = {}
        for group in GROUP_ORDER:
            completions = [float(row[group]["completion"]) for row in subset]  # type: ignore[index]
            truths = [float(row[group]["truth_v2"]) for row in subset]  # type: ignore[index]
            truth_mean = _mean(truths)
            completion_mean = _mean(completions)
            block[group] = {
                "completion_mean": _rounded(completion_mean, 4),
                "truth_v2_mean": _rounded(truth_mean, 4),
                "truth_delta_pct": _rounded(
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
        for group in GROUP_ORDER:
            if verdicts[group]:
                template_passes[group] += 1
        per_template[name] = block
    aggregate["per_template"] = per_template
    aggregate["targets_met_templates"] = {
        group: f"{template_passes[group]}/{len(template_names_list)}"
        for group in GROUP_ORDER
    }
    return aggregate


def run_tune_cv(
    names: Optional[Sequence[str]] = None,
    tuning_seeds: Sequence[int] = CV_SEEDS,
    eval_seeds: Sequence[int] = EVAL_SEEDS,
    steps: int = STEPS,
    grid: Optional[Sequence[Dict[str, object]]] = None,
) -> Dict[str, object]:
    """Run the 2-fold CV tuning + held-out evaluation experiment."""
    assert_seed_isolation(tuning_seeds, eval_seeds)
    template_names_list = list(template_names() if names is None else names)
    candidate_list = [dict(config) for config in (candidate_grid() if grid is None else grid)]
    started = time.perf_counter()
    cv_per_template: Dict[str, object] = {}
    selected: Dict[str, Dict[str, object]] = {}
    for name in template_names_list:
        matrix = evaluate_grid(name, tuning_seeds, candidate_list, steps)
        selection = select_cv_config(matrix)
        selected[name] = dict(selection["selected"])  # type: ignore[arg-type]
        cv_per_template[name] = {
            "selected": selected[name],
            "selected_key": selection["selected_key"],
            "status": selection["status"],
            "cv_completion": selection["cv_completion"],
            "cv_truth_v2": selection["cv_truth_v2"],
            "fold_agreement": selection["fold_agreement"],
            "fold_winners": selection["fold_winners"],
            "validation_seeds": selection["validation_seeds"],
            "feasible_candidates": selection["feasible_candidates"],
            "candidates": selection["candidates"],
            "matrix": matrix,
        }
        print(
            f"[tune-cv] {name}: CV-selected w={selected[name]['w_route']} "
            f"{selected[name]['profile']} status={selection['status']} "
            f"cv_completion={selection['cv_completion']:.4f} cv_truth={selection['cv_truth_v2']:.4f}"
        )
    rows: List[Dict[str, object]] = []
    for name in template_names_list:
        cv_config = selected[name]
        for seed in eval_seeds:
            row: Dict[str, object] = {
                "template": name,
                "seed": int(seed),
                "cv_config": dict(cv_config),
            }
            row["baseline"] = _run_group(name, seed, dict(BASELINE_CONFIG), steps)
            row["fixed"] = _run_group(name, seed, dict(FIXED_CONFIG), steps)
            row["cv_tuned"] = _run_group(name, seed, cv_config, steps)
            rows.append(row)
            print(
                f"[tune-cv][eval] {name} seed={seed}: "
                f"baseline c={row['baseline']['completion']:.3f} t={row['baseline']['truth_v2']:.4f} | "
                f"fixed c={row['fixed']['completion']:.3f} t={row['fixed']['truth_v2']:.4f} | "
                f"cv c={row['cv_tuned']['completion']:.3f} t={row['cv_tuned']['truth_v2']:.4f}"
            )
    evaluation = {
        "runs": len(rows) * 3,
        "cases": len(rows),
        "eval_seeds": [int(seed) for seed in eval_seeds],
        "rows": rows,
        "aggregate": _aggregate_evaluation(rows, template_names_list),
    }
    tuning_calls = len(candidate_list) * len(list(tuning_seeds)) * len(template_names_list)
    eval_calls = len(rows) * 3
    data: Dict[str, object] = {
        "schema": "mp_place.tune_cv/v1",
        "protocol": {
            "tuning_seeds": [int(seed) for seed in tuning_seeds],
            "eval_seeds": [int(seed) for seed in eval_seeds],
            "seeds_disjoint": True,
            "folds": [
                {
                    "name": str(fold["name"]),
                    "train": [int(seed) for seed in fold["train"]],
                    "validate": [int(seed) for seed in fold["validate"]],
                }
                for fold in CV_FOLDS
            ],
            "note": (
                "2-fold CV with one held-out seed per fold; with three tuning "
                "seeds the third seed is the shared training anchor."
            ),
            "candidate_grid": candidate_list,
            "w_grid": [float(value) for value in W_GRID],
            "profiles": list(PROFILES),
            "targets": {"completion": TARGET_COMPLETION, "truth_ratio": TARGET_TRUTH_RATIO},
            "steps": int(steps),
            "templates": template_names_list,
            "baseline_config": dict(BASELINE_CONFIG),
            "fixed_config": dict(FIXED_CONFIG),
            "router": f"GridRouter(grid_mm={ROUTER_GRID_MM}, layers={ROUTER_LAYERS})",
        },
        "cv": {"per_template": cv_per_template},
        "evaluation": evaluation,
        "router_calls": tuning_calls + eval_calls,
        "runtime_s": _rounded(time.perf_counter() - started, 2),
    }
    data["recommendation"] = recommend_cv(data)
    return data


# ---------------------------------------------------------------------------
# Recommendation (pure).
# ---------------------------------------------------------------------------


def recommend_cv(result: Dict[str, object]) -> Dict[str, object]:
    """Turn the held-out CV numbers into a deterministic safe-default advice.

    If CV-tuned weights still fail to generalise to seeds 3/4, the recommendation
    is the plain route-aware objective (``w_route=2.0``, no per-template table)
    and disabling the P2.9 ``TUNED_TABLE``.
    """
    aggregate = result["evaluation"]["aggregate"]  # type: ignore[index]
    pass_counts = {
        group: int(aggregate["targets_met_templates"][group].split("/")[0])  # type: ignore[index]
        for group in GROUP_ORDER
    }
    n_templates = int(aggregate["n_templates"])  # type: ignore[index]
    cv_truth_delta = float(aggregate["cv_tuned"]["truth_delta_pct"])  # type: ignore[index]
    cv_generalises = bool(
        pass_counts["cv_tuned"] >= max(pass_counts["fixed"], pass_counts["baseline"])
        and cv_truth_delta <= 1.0
    )
    if cv_generalises:
        safe_default = "cv_tuned"
        safe_config: Optional[Dict[str, object]] = None
        disable_tuned_table = False
        reason = (
            "CV-tuned 的按模板权重在留出 seeds 3/4 上仍保持 completion/truth 目标；"
            "可以继续把 CV 调参作为默认（新模板上仍需注意稀疏网格的过拟合风险）。"
        )
    else:
        safe_default = "route_aware_fixed"
        safe_config = dict(FIXED_CONFIG)
        disable_tuned_table = True
        reason = (
            "CV-tuned 权重在留出 seeds 3/4 上仍不泛化"
            f"（模板达标 {pass_counts['cv_tuned']}/{n_templates}，truth Δ "
            f"{cv_truth_delta:+.2f}%）。建议安全默认使用固定权重的 route-aware 目标 "
            "（w_route=2.0），并关闭 P2.9 的 per-template TUNED_TABLE；"
            "truth 敏感场景用纯 proxy（w=0）+ post-hoc route repair。"
        )
    return {
        "cv_generalises": cv_generalises,
        "template_pass_counts": {
            group: f"{pass_counts[group]}/{n_templates}" for group in GROUP_ORDER
        },
        "safe_default": safe_default,
        "safe_default_config": safe_config,
        "disable_p29_tuned_table": disable_tuned_table,
        "reason": reason,
        "note": (
            "Diagnostic only: computed on held-out seeds 3/4; CV folds are the "
            "tuning seeds 0/1 (seed 2 trains both folds)."
        ),
    }


# ---------------------------------------------------------------------------
# Report writer.
# ---------------------------------------------------------------------------


def write_tune_cv_report(
    data: Dict[str, object],
    out_dir: Optional[pathlib.Path] = None,
) -> Tuple[pathlib.Path, pathlib.Path]:
    """Write ``report_tune_cv.md`` / ``.json`` and return their paths."""
    directory = pathlib.Path(out_dir) if out_dir is not None else PROJECT_ROOT
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / REPORT_JSON
    md_path = directory / REPORT_MD
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    protocol = data["protocol"]  # type: ignore[index]
    cv = data["cv"]["per_template"]  # type: ignore[index]
    evaluation = data["evaluation"]  # type: ignore[index]
    aggregate = evaluation["aggregate"]  # type: ignore[index]
    per_template = aggregate["per_template"]  # type: ignore[index]
    recommendation = data["recommendation"]  # type: ignore[index]
    lines: List[str] = []
    lines.append("# P2.12：route_cost 交叉验证调参（2-fold CV）与留出评估\n")
    lines.append(
        f"- 协议：**调参 seeds {protocol['tuning_seeds']}**（2-fold CV："
        + "，".join(
            f"{fold['name']} train{fold['train']} / validate{fold['validate']}"
            for fold in protocol["folds"]
        )
        + f"；seed 2 为两折共享训练锚点）；**评估 seeds {protocol['eval_seeds']}**"
        "（严格不进调参，`assert_seed_isolation` 强制互斥）"
    )
    lines.append(
        f"- 网格：w∈{protocol['w_grid']} × profile∈{protocol['profiles']}"
        f"（w=0 只评估一次），共 {len(protocol['candidate_grid'])} 个候选；"
        f"选择目标：CV completion ≥ {protocol['targets']['completion']} 下取 CV truth_v2 最小，"
        "无可行候选则回退 fixed w=2.0"
    )
    lines.append(
        f"- 运行：8 模板 × {len(protocol['eval_seeds'])} 评估 seeds；"
        f"router 调用 {data['router_calls']} 次；总耗时 {data['runtime_s']} s；"
        f"router = {protocol['router']}\n"
    )
    lines.append("## 一、每模板 CV 选中配置与 CV 表现\n")
    lines.append(
        "| 模板 | CV 选中 w | profile | 状态 | CV-val completion (seeds 0/1) | "
        "CV-val truth_v2 | 调参侧 completion (0/1/2) | 调参侧 truth | 两折一致 |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for name in protocol["templates"]:
        block = cv[name]
        selected = block["selected"]
        validation = cv_metrics(
            block["matrix"][block["selected_key"]],
            CV_FOLDS,
        )
        lines.append(
            f"| {name} | {selected['w_route']} | {selected['profile']} | "
            f"{block['status']} | {block['cv_completion']} | {block['cv_truth_v2']} | "
            f"{block['matrix'][block['selected_key']]['completion_mean']:.4f} | "
            f"{block['matrix'][block['selected_key']]['truth_mean']:.4f} | "
            f"{'✅' if block['fold_agreement'] else '❌'} |"
        )
    lines.append("")
    fold_agreements = [
        bool(cv[name]["fold_agreement"]) for name in protocol["templates"]
    ]
    lines.append(
        f"按 fold 分别取最优时，两折选中同一配置的模板数："
        f"**{sum(fold_agreements)}/{len(fold_agreements)}**——CV 选择在折间并不稳定，"
        "这本身是调参不可泛化的早期信号。\n"
    )
    lines.append("## 二、外样本（seeds 3/4）三组对比\n")
    lines.append(
        "| 组别 | completion 均值 | 全布通 | truth_v2 均值 | truth Δ% vs baseline | "
        "run 达标率 | 模板达标率 |"
    )
    lines.append("|---|---|---|---|---|---|---|")
    labels = (
        ("baseline", "baseline（w=0）"),
        ("fixed", "fixed（w=2.0）"),
        ("cv_tuned", "CV-tuned（按模板）"),
    )
    for key, label in labels:
        block = aggregate[key]
        lines.append(
            f"| {label} | {block['completion_mean']} | {block['fully_routed']} | "
            f"{block['truth_v2_mean']} | {block['truth_delta_pct']:+.2f}% | "
            f"{block['run_target_pass_rate']:.1%} ({block['run_target_passes']}) | "
            f"{aggregate['targets_met_templates'][key]} |"
        )
    lines.append("")
    cv_block = aggregate["cv_tuned"]
    fixed_block = aggregate["fixed"]
    if (
        float(cv_block["completion_mean"]) <= float(fixed_block["completion_mean"]) + 1e-9
        or float(cv_block["truth_delta_pct"]) >= float(fixed_block["truth_delta_pct"])
    ):
        lines.append(
            "关键发现：CV 调参仍未能泛化——固定权重 route-aware（w=2.0）在留出 seeds 上 "
            f"completion {fixed_block['completion_mean']}、truth Δ "
            f"{fixed_block['truth_delta_pct']:+.2f}%，而 CV-tuned 为 "
            f"{cv_block['completion_mean']}、{cv_block['truth_delta_pct']:+.2f}%。"
            "CV 选择目标只在折内（seeds 0/1）追求 completion≥0.97 后的最小 truth，"
            "把训练折的 truth 偏好带进了外样本；稀疏网格的 per-template 权重不具可迁移性。\n"
        )
    lines.append("## 三、外样本逐模板（completion / truth_v2）\n")
    lines.append(
        "| 模板 | CV 选中配置 | baseline | fixed | CV-tuned | CV-tuned 达标 |"
    )
    lines.append("|---|---|---|---|---|---|")
    for name in protocol["templates"]:
        block = per_template[name]
        selected = block["cv_config"]
        cells = []
        for key in GROUP_ORDER:
            entry = block[key]
            cells.append(f"{entry['completion_mean']} / {entry['truth_v2_mean']}")
        lines.append(
            f"| {name} | w={selected['w_route']}, {selected['profile']} | "
            + " | ".join(cells)
            + f" | {'✅' if block['targets_met']['cv_tuned'] else '❌'} |"
        )
    lines.append("")
    lines.append("## 四、泛化结论与安全默认建议\n")
    lines.append(
        f"- CV-tuned 是否泛化到 seeds 3/4：**{recommendation['cv_generalises']}**；"
        f"模板达标计数 {recommendation['template_pass_counts']}。"
    )
    lines.append(f"- **建议安全默认：`{recommendation['safe_default']}`**。")
    lines.append(f"- 理由：{recommendation['reason']}")
    if recommendation["safe_default_config"] is not None:
        lines.append(
            f"- 建议默认配置：`{recommendation['safe_default_config']}`；"
            f"关闭 P2.9 per-template tuned 表：**{recommendation['disable_p29_tuned_table']}**。"
        )
    lines.append(f"\n> {recommendation['note']}\n")
    lines.append("## 五、边界\n")
    lines.append(
        "- CV 折只覆盖 seeds 0/1（seed 2 为共享训练锚点）；评估 seeds 3/4 一次性使用、"
        "不参与任何选择，也不回写任何表。"
    )
    lines.append(
        "- 候选网格较小（w×profile 稀疏网格）；CV 结果是该网格内的最优，不代表连续权重空间的最优。"
    )
    lines.append(
        "- router 是 1 mm/2 层网格迷宫 oracle，不是 DRC/真实可布通证明；truth_v2 是离线伪物理模型；"
        "真实布线/DRC/SI/PI/热仍 `NOT RUN`；模板为合成产品族。"
    )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[tune-cv] wrote {md_path} / {json_path}")
    return md_path, json_path


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="P2.12 cross-validated route-cost tuning")
    parser.add_argument("--cv-seeds", default="0,1,2")
    parser.add_argument("--eval-seeds", default="3,4")
    parser.add_argument("--steps", type=int, default=STEPS)
    parser.add_argument("--quick", action="store_true", help="2 templates x 1 eval seed x 120 steps")
    parser.add_argument("--out", default=str(PROJECT_ROOT))
    args = parser.parse_args(argv)
    tuning_seeds = tuple(int(part) for part in args.cv_seeds.split(",") if part.strip())
    eval_seeds = tuple(int(part) for part in args.eval_seeds.split(",") if part.strip())
    if args.quick:
        data = run_tune_cv(
            names=list(template_names())[:2],
            tuning_seeds=tuning_seeds,
            eval_seeds=eval_seeds[:1],
            steps=120,
        )
    else:
        data = run_tune_cv(
            tuning_seeds=tuning_seeds,
            eval_seeds=eval_seeds,
            steps=args.steps,
        )
    write_tune_cv_report(data, pathlib.Path(args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "CV_FOLDS",
    "CV_SEEDS",
    "EVAL_SEEDS",
    "assert_seed_isolation",
    "candidate_grid",
    "config_key",
    "cv_metrics",
    "evaluate_grid",
    "recommend_cv",
    "run_tune_cv",
    "select_cv_config",
    "write_tune_cv_report",
]
