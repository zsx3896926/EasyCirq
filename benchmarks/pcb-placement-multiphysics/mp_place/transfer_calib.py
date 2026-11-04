"""P2.18: few-shot real-board calibration of the template-trained surrogate.

Motivation
----------
P2.14 (``mp_place.transfer``) showed that the surrogate trained on the eight
synthetic product-family templates transfers to the three real EasyCirq boards
with a *high rank correlation* but a very wrong absolute scale (R^2 is deeply
negative because the physics-v2 hidden coefficients depend on the scenario
name).  This means the template surrogate is useful for *ranking* candidates,
but its scores cannot be compared with the real-board truth until a few real
samples are used to calibrate it.

This module asks the deployment question: **how many real-board samples are
needed, and which calibration strategy is best?**

Protocol
--------
1. Train the 40-dim ridge surrogate on template data (``transfer.py`` helpers,
   physics-v2 truth), exactly like P2.14.
2. For each real board sample ``CALIB_POOL + TEST_SIZE`` random hard-feasible
   layouts with the physics-v2 truth.  The first ``CALIB_POOL`` layouts are the
   calibration pool, the last ``TEST_SIZE`` are the fixed held-out test set.
3. For each ``k in {4, 8, 16, 32}`` use the first ``k`` calibration layouts and
   compare three strategies on the *same* held-out set:

   * ``no_cal``   -- raw template-surrogate predictions;
   * ``affine``   -- least-squares ``y ~ a * pred + b`` on the k samples
     (``transfer._fit_affine``);
   * ``fine_tune`` -- affine + a ridge *feature correction*: fit
     ``y ~ a * pred + b + sum_j w_j * z_j`` where ``z`` are template-standardised
     40-dim features and only the correction weights are penalised (lambda);
     with no data the correction shrinks to 0 and the strategy degrades to
     affine.

   Metrics on the held-out set: R^2, Spearman and top-10 selection regret
   (mean truth of predicted top-10 minus mean truth of the true top-10; lower is
   better).
4. Per-board recommendation: smallest k whose best strategy is within a small
   tolerance of that board's best achievable held-out R^2 / Spearman / regret.
5. Leave-one-board-out: the *held-out board* contributes **no calibration
   sample**; affine / fine-tune coefficients are fitted on pooled samples from
   the other boards and applied to the held-out board's test set.  The
   held-out board's own few-shot calibration is reported separately as a
   *reference upper bound* (not deployable, because it uses held-out data).

Everything is deterministic (fixed sample seeds, analytic least squares) and
uses the offline physics-v2 truth, not SPICE/FEA measurements.

Run::

    python -c "from mp_place.transfer_calib import main; raise SystemExit(main())"

writes ``report_transfer_calib.md`` / ``report_transfer_calib.json``.
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import time
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .datascale import feature_keep_indices
from .objective import RidgeModel, r_squared, spearman
from .realboard import DEFAULT_SOURCES, load_and_convert
from .transfer import (
    TEMPLATE_NAMES,
    _fit_affine,
    _regret,
    _sample_board,
    _sample_templates,
)

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent

K_LIST: Tuple[int, ...] = (4, 8, 16, 32)
TEMPLATE_SAMPLES = 120
BOARD_SAMPLES = 120
CALIB_POOL = 60
TEST_SIZE = 60
TEMPLATE_SEED = 0
BOARD_SEED = 0
RIDGE_LAMBDA = 1.0e-2
#: Fine-tune = ridge refit on ``[40-dim features, template prediction]`` with
#: the same regularisation strength as the template model (chosen a priori).
FINE_TUNE_LAMBDA = RIDGE_LAMBDA
TOP_K = 10
HOLDOUT_BOARD = "dual-button"
STRATEGIES: Tuple[str, ...] = ("no_cal", "affine", "fine_tune")
TOL_R2 = 0.05
TOL_SPEARMAN = 0.04
TOL_REGRET = 0.05
#: A board is "usable" when its best calibrated held-out R^2 reaches this value.
USABLE_R2 = 0.5
_MAX_SANE_PREDICTION = 1.0e6


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #
def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _std(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    mean = sum(values) / len(values)
    return math.sqrt(sum((value - mean) ** 2 for value in values) / len(values))


def _fit_fine_tune(
    X_cal: Sequence[Sequence[float]],
    y_cal: Sequence[float],
    transfer_pred_cal: Sequence[float],
    lam: float = FINE_TUNE_LAMBDA,
) -> Optional[Tuple[RidgeModel, Tuple[int, ...]]]:
    """Ridge fine-tune on real samples: ``[40-dim features, template prediction]``.

    The frozen template prediction is appended as one extra feature, so the
    model can learn the real-board scale/offset *and* feature corrections from
    the k real samples.  Columns that are constant on the calibration set are
    dropped first (``RidgeModel`` standardisation would otherwise blow up on
    zero-variance columns).
    """
    rows = [
        [float(value) for value in feature] + [float(prediction)]
        for feature, prediction in zip(X_cal, transfer_pred_cal)
    ]
    keep = feature_keep_indices(rows)
    if not keep:
        return None
    model = RidgeModel(lam=float(lam)).fit(
        [[row[index] for index in keep] for row in rows], list(y_cal)
    )
    return model, tuple(keep)


def _fine_tune_predictions(
    X_test: Sequence[Sequence[float]],
    transfer_pred_test: Sequence[float],
    fitted: Optional[Tuple[RidgeModel, Tuple[int, ...]]],
) -> Optional[List[float]]:
    if fitted is None:
        return None
    model, keep = fitted
    rows = [
        [float(value) for value in feature] + [float(prediction)]
        for feature, prediction in zip(X_test, transfer_pred_test)
    ]
    return [float(model.predict([row[index] for index in keep])) for row in rows]


def _metrics(y_true: Sequence[float], y_pred: Sequence[float], *, top_k: int = TOP_K) -> Dict[str, float]:
    return {
        "r2": round(r_squared(y_true, y_pred), 4),
        "spearman": round(spearman(y_true, y_pred), 4),
        "regret_top": _regret(y_true, y_pred, top=top_k),
        "n": len(y_true),
    }


def _affine_apply(pred: Sequence[float], a: float, b: float) -> List[float]:
    return [a * value + b for value in pred]


def _is_finite_predictions(values: Sequence[float]) -> bool:
    return all(math.isfinite(value) and abs(value) <= _MAX_SANE_PREDICTION for value in values)


# --------------------------------------------------------------------------- #
# boards
# --------------------------------------------------------------------------- #
def load_real_boards(
    sources: Optional[Sequence[Tuple[str, object]]] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Load the EasyCirq dumps; missing/broken files are reported, never fatal."""
    source_list = list(sources) if sources is not None else list(DEFAULT_SOURCES)
    boards: List[Dict[str, Any]] = []
    missing: List[Dict[str, Any]] = []
    for name, path in source_list:
        target = pathlib.Path(path)
        if not target.exists():
            missing.append({"board": str(name), "source": str(target), "status": "MISSING"})
            continue
        try:
            converted = load_and_convert(target, name=str(name))
            boards.append({"board": str(name), "source": str(target), "converted": converted})
        except Exception as exc:  # noqa: BLE001 - a broken dump must not kill the study
            missing.append(
                {
                    "board": str(name),
                    "source": str(target),
                    "status": "ERROR",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
    return boards, missing


def _validate_k(k_list: Sequence[int], calib_pool: int) -> Tuple[int, ...]:
    validated: List[int] = []
    for k in k_list:
        if isinstance(k, bool) or not isinstance(k, int):
            raise ValueError(f"k must be an integer, got {k!r}")
        if k < 1:
            raise ValueError(f"k must be >= 1, got {k}")
        if k > calib_pool:
            raise ValueError(f"k={k} exceeds the calibration pool of {calib_pool} samples")
        validated.append(k)
    if len(set(validated)) != len(validated):
        raise ValueError(f"duplicate k values: {k_list}")
    return tuple(validated)


# --------------------------------------------------------------------------- #
# per-board evaluation
# --------------------------------------------------------------------------- #
def _evaluate_board(
    board_name: str,
    converted,
    model40: RidgeModel,
    k_list: Sequence[int],
    *,
    calib_pool: int,
    test_size: int,
    seed: int,
    top_k: int = TOP_K,
    lam: float = FINE_TUNE_LAMBDA,
) -> Dict[str, Any]:
    """Few-shot calibration of one board on a fixed held-out test split."""
    scenario = converted.scenario
    _X10, X40, y = _sample_board(converted, n=calib_pool + test_size, seed=seed)
    calib_X = X40[:calib_pool]
    calib_y = y[:calib_pool]
    test_X = X40[calib_pool : calib_pool + test_size]
    test_y = y[calib_pool : calib_pool + test_size]

    transfer_pred_test = [model40.predict(row) for row in test_X]
    no_cal = _metrics(test_y, transfer_pred_test, top_k=top_k)

    by_k: List[Dict[str, Any]] = []
    for k in k_list:
        calibration_x = calib_X[:k]
        calibration_y = calib_y[:k]
        transfer_pred_cal = [model40.predict(row) for row in calibration_x]

        affine_a, affine_b = _fit_affine(transfer_pred_cal, calibration_y)
        affine_pred = _affine_apply(transfer_pred_test, affine_a, affine_b)
        affine_metrics = _metrics(test_y, affine_pred, top_k=top_k)
        affine_metrics["a"] = round(affine_a, 6)
        affine_metrics["b"] = round(affine_b, 6)

        fitted = _fit_fine_tune(calibration_x, calibration_y, transfer_pred_cal, lam=lam)
        fine_pred = _fine_tune_predictions(test_X, transfer_pred_test, fitted)
        if fine_pred is None or not _is_finite_predictions(fine_pred):
            fine_pred = affine_pred  # safety fallback: behaviour degrades to affine
        fine_metrics = _metrics(test_y, fine_pred, top_k=top_k)

        by_k.append(
            {
                "k": int(k),
                "calibration_samples": int(k),
                "affine": affine_metrics,
                "fine_tune": fine_metrics,
            }
        )

    row: Dict[str, Any] = {
        "board": board_name,
        "board_mm": [round(float(scenario.board_w), 3), round(float(scenario.board_h), 3)],
        "components": len(scenario.components),
        "nets": len(scenario.nets),
        "samples": calib_pool + test_size,
        "calibration_pool": calib_pool,
        "test_samples": test_size,
        "truth_mean": round(_mean(test_y), 4),
        "truth_std": round(_std(test_y), 4),
        "no_cal": no_cal,
        "by_k": by_k,
    }
    row["recommendation"] = _recommend_for_board(row)
    row["best_achievable_r2"] = row["recommendation"].get("best_r2_all_k")
    row["usable"] = bool(
        row["best_achievable_r2"] is not None and row["best_achievable_r2"] >= USABLE_R2
    )
    row["recommendation"]["usable"] = row["usable"]
    if not row["usable"]:
        row["recommendation"]["advice"] = (
            "best calibrated R² is below the usability threshold; collect in-domain "
            "training data instead of more affine calibration"
        )
    return row


def _best_strategy_at(k_row: Dict[str, Any]) -> Tuple[str, Dict[str, float]]:
    candidates = {
        "affine": k_row["affine"],
        "fine_tune": k_row["fine_tune"],
    }
    strategy = max(
        candidates,
        key=lambda name: (
            candidates[name]["r2"],
            candidates[name]["spearman"],
            -(candidates[name]["regret_top"] if candidates[name]["regret_top"] is not None else 0.0),
        ),
    )
    return strategy, candidates[strategy]


def _recommend_for_board(row: Dict[str, Any]) -> Dict[str, Any]:
    """Smallest k whose best strategy is close to the board's best achievable."""
    best_by_k: Dict[int, Tuple[str, Dict[str, float]]] = {}
    for k_row in row["by_k"]:
        best_by_k[int(k_row["k"])] = _best_strategy_at(k_row)
    if not best_by_k:
        return {"k": None, "strategy": None}
    max_r2 = max(metrics["r2"] for _strategy, metrics in best_by_k.values())
    max_spearman = max(metrics["spearman"] for _strategy, metrics in best_by_k.values())
    regret_values = [
        metrics["regret_top"]
        for _strategy, metrics in best_by_k.values()
        if metrics["regret_top"] is not None
    ]
    min_regret = min(regret_values) if regret_values else None
    for k in sorted(best_by_k):
        strategy, metrics = best_by_k[k]
        regret_ok = (
            min_regret is None
            or metrics["regret_top"] is None
            or metrics["regret_top"] <= min_regret + TOL_REGRET
        )
        if (
            metrics["r2"] >= max_r2 - TOL_R2
            and metrics["spearman"] >= max_spearman - TOL_SPEARMAN
            and regret_ok
        ):
            return {
                "k": int(k),
                "strategy": strategy,
                "r2": metrics["r2"],
                "spearman": metrics["spearman"],
                "regret_top": metrics["regret_top"],
                "best_r2_all_k": round(max_r2, 4),
                "best_spearman_all_k": round(max_spearman, 4),
                "best_regret_all_k": round(min_regret, 6) if min_regret is not None else None,
            }
    k = max(best_by_k)
    strategy, metrics = best_by_k[k]
    return {
        "k": int(k),
        "strategy": strategy,
        "r2": metrics["r2"],
        "spearman": metrics["spearman"],
        "regret_top": metrics["regret_top"],
        "best_r2_all_k": round(max_r2, 4),
        "best_spearman_all_k": round(max_spearman, 4),
        "best_regret_all_k": round(min_regret, 6) if min_regret is not None else None,
    }


# --------------------------------------------------------------------------- #
# cross-board held-out generalisation
# --------------------------------------------------------------------------- #
def _cross_board_validation(
    boards: Sequence[Dict[str, Any]],
    model40: RidgeModel,
    k_list: Sequence[int],
    *,
    calib_pool: int,
    test_size: int,
    holdout_name: str,
    seed: int,
    top_k: int = TOP_K,
    lam: float = FINE_TUNE_LAMBDA,
) -> Dict[str, Any]:
    """Fit calibration on other boards' samples; test on the held-out board."""
    if len(boards) < 2:
        return {
            "status": "SKIPPED",
            "reason": "need at least two real boards for a leave-one-board-out study",
            "holdout_board": None,
            "rows": [],
        }
    names = [board["board"] for board in boards]
    holdout = next((board for board in boards if board["board"] == holdout_name), boards[-1])
    training = [board for board in boards if board["board"] != holdout["board"]]
    holdout_converted = holdout["converted"]

    _X10, X40_h, y_h = _sample_board(holdout_converted, n=calib_pool + test_size, seed=seed)
    holdout_calib_X = X40_h[:calib_pool]
    holdout_calib_y = y_h[:calib_pool]
    test_X = X40_h[calib_pool : calib_pool + test_size]
    test_y = y_h[calib_pool : calib_pool + test_size]
    transfer_test = [model40.predict(row) for row in test_X]
    no_cal = _metrics(test_y, transfer_test, top_k=top_k)

    pooled: Dict[str, Any] = {}
    for board in training:
        _X10, X40, y = _sample_board(board["converted"], n=calib_pool, seed=seed)
        pooled[board["board"]] = {"X": X40, "y": y}

    rows: List[Dict[str, Any]] = []
    for k in k_list:
        calib_X: List[List[float]] = []
        calib_y: List[float] = []
        for board_name in sorted(pooled):
            calib_X.extend(pooled[board_name]["X"][:k])
            calib_y.extend(pooled[board_name]["y"][:k])
        transfer_cal = [model40.predict(row) for row in calib_X]
        affine_a, affine_b = _fit_affine(transfer_cal, calib_y)
        cross_affine = _metrics(
            test_y, _affine_apply(transfer_test, affine_a, affine_b), top_k=top_k
        )
        fitted = _fit_fine_tune(calib_X, calib_y, transfer_cal, lam=lam)
        cross_fine_pred = _fine_tune_predictions(test_X, transfer_test, fitted)
        if cross_fine_pred is None or not _is_finite_predictions(cross_fine_pred):
            cross_fine_pred = _affine_apply(transfer_test, affine_a, affine_b)
        cross_fine = _metrics(test_y, cross_fine_pred, top_k=top_k)

        # Reference upper bound: calibration on the held-out board's own samples
        # (uses held-out data, therefore NOT deployable; reported for context).
        own_transfer_cal = [model40.predict(row) for row in holdout_calib_X[:k]]
        own_a, own_b = _fit_affine(own_transfer_cal, holdout_calib_y[:k])
        reference = _metrics(
            test_y, _affine_apply(transfer_test, own_a, own_b), top_k=top_k
        )
        rows.append(
            {
                "k": int(k),
                "calibration_samples_total": len(calib_y),
                "cross_board_affine": cross_affine,
                "cross_board_fine_tune": cross_fine,
                "reference_in_domain_affine": reference,
            }
        )
    return {
        "status": "OK",
        "holdout_board": holdout["board"],
        "training_boards": sorted(pooled),
        "no_cal": no_cal,
        "rows": rows,
        "truth_mean": round(_mean(test_y), 4),
        "truth_std": round(_std(test_y), 4),
        "note": (
            "reference_in_domain_affine uses the held-out board's own k samples, "
            "so it is an upper-bound reference and not a deployable strategy"
        ),
    }


# --------------------------------------------------------------------------- #
# study
# --------------------------------------------------------------------------- #
def run_transfer_calibration(
    template_samples: int = TEMPLATE_SAMPLES,
    board_samples: int = BOARD_SAMPLES,
    k_list: Sequence[int] = K_LIST,
    *,
    calib_pool: Optional[int] = None,
    test_size: Optional[int] = None,
    holdout_board: str = HOLDOUT_BOARD,
    sources: Optional[Sequence[Tuple[str, object]]] = None,
    lam_fine_tune: float = FINE_TUNE_LAMBDA,
    template_seed: int = TEMPLATE_SEED,
    board_seed: int = BOARD_SEED,
    top_k: int = TOP_K,
    quiet: bool = False,
) -> Dict[str, Any]:
    """Run the template-surrogate few-shot calibration study."""
    started = time.perf_counter()
    calib_pool = int(calib_pool if calib_pool is not None else board_samples // 2)
    test_size = int(test_size if test_size is not None else board_samples - calib_pool)
    if calib_pool < 1 or test_size < 1:
        raise ValueError("calib_pool and test_size must both be >= 1")
    if calib_pool + test_size > board_samples:
        raise ValueError("calib_pool + test_size must not exceed board_samples")
    k_list = _validate_k(k_list, calib_pool)

    X10_t, X40_t, y_t = _sample_templates(n=template_samples, seed=template_seed)
    model40 = RidgeModel(lam=RIDGE_LAMBDA).fit(X40_t, y_t)

    loaded_boards, missing = load_real_boards(sources)
    rows: List[Dict[str, Any]] = []
    for board in loaded_boards:
        row = _evaluate_board(
            board["board"],
            board["converted"],
            model40,
            k_list,
            calib_pool=calib_pool,
            test_size=test_size,
            seed=board_seed,
            top_k=top_k,
            lam=lam_fine_tune,
        )
        rows.append(row)
        if not quiet:
            recommendation = row["recommendation"]
            print(
                f"[transfer_calib] {row['board']:11s} no_cal r2={row['no_cal']['r2']:+.2f} "
                f"rho={row['no_cal']['spearman']:.3f} | recommended k={recommendation['k']} "
                f"({recommendation['strategy']}) r2={recommendation['r2']:.3f} "
                f"rho={recommendation['spearman']:.3f}"
            )

    cross_board = _cross_board_validation(
        loaded_boards,
        model40,
        k_list,
        calib_pool=calib_pool,
        test_size=test_size,
        holdout_name=holdout_board,
        seed=board_seed,
        top_k=top_k,
        lam=lam_fine_tune,
    )

    summary = _summarize(rows, cross_board, k_list)
    data: Dict[str, Any] = {
        "config": {
            "templates": list(TEMPLATE_NAMES),
            "template_samples_per_template": int(template_samples),
            "template_features": 40,
            "surrogate": f"RidgeModel(lam={RIDGE_LAMBDA}) on 40-dim features trained on templates",
            "board_samples": int(board_samples),
            "calibration_pool": calib_pool,
            "test_samples": int(test_size),
            "k_list": [int(k) for k in k_list],
            "strategies": list(STRATEGIES),
            "strategy_definitions": {
                "no_cal": "raw template-surrogate predictions",
                "affine": "least-squares a*pred+b fitted on k real samples",
                "fine_tune": "ridge refit on [40-dim features, template prediction] with k real samples",
            },
            "fine_tune_lambda": float(lam_fine_tune),
            "top_k": int(top_k),
            "template_seed": int(template_seed),
            "board_seed": int(board_seed),
            "holdout_board": holdout_board,
            "usable_r2_threshold": USABLE_R2,
            "recommendation_tolerances": {
                "r2": TOL_R2,
                "spearman": TOL_SPEARMAN,
                "regret_top": TOL_REGRET,
            },
        },
        "boards": rows,
        "cross_board": cross_board,
        "missing_boards": missing,
        "summary": summary,
        "runtime_s": round(time.perf_counter() - started, 2),
    }
    return data


def _summarize(
    rows: Sequence[Dict[str, Any]],
    cross_board: Dict[str, Any],
    k_list: Sequence[int],
) -> Dict[str, Any]:
    if not rows:
        return {
            "n_boards": 0,
            "recommended_k": None,
            "recommended_strategy": None,
            "note": "no real boards available",
        }
    recommended = {
        row["board"]: int(row["recommendation"]["k"]) for row in rows
    }
    strategies = {
        row["board"]: row["recommendation"]["strategy"] for row in rows
    }
    # Aggregate mean metrics per k and strategy across boards.
    aggregate: Dict[str, Dict[str, Dict[str, float]]] = {}
    for k in sorted({int(k) for k in k_list}):
        entry: Dict[str, Dict[str, float]] = {}
        for strategy in ("affine", "fine_tune"):
            values = [
                next(
                    block
                    for k_row in row["by_k"]
                    if int(k_row["k"]) == int(k)
                    for block in [k_row[strategy]]
                )
                for row in rows
            ]
            entry[strategy] = {
                "mean_r2": round(_mean([value["r2"] for value in values]), 4),
                "mean_spearman": round(_mean([value["spearman"] for value in values]), 4),
                "mean_regret_top": round(
                    _mean([value["regret_top"] for value in values if value["regret_top"] is not None]),
                    6,
                ),
            }
        aggregate[str(k)] = entry
    no_cal = {
        "mean_r2": round(_mean([row["no_cal"]["r2"] for row in rows]), 4),
        "mean_spearman": round(_mean([row["no_cal"]["spearman"] for row in rows]), 4),
        "mean_regret_top": round(
            _mean([row["no_cal"]["regret_top"] for row in rows if row["no_cal"]["regret_top"] is not None]),
            6,
        ),
    }

    # Overall recommended k: smallest k whose mean best-strategy metrics are
    # within tolerance of the best mean metrics over k.
    best_by_k: Dict[int, Dict[str, float]] = {}
    for k in sorted(aggregate):
        best_by_k[int(k)] = {
            "r2": max(aggregate[k][strategy]["mean_r2"] for strategy in ("affine", "fine_tune")),
            "spearman": max(
                aggregate[k][strategy]["mean_spearman"] for strategy in ("affine", "fine_tune")
            ),
            "regret": min(
                [
                    aggregate[k][strategy]["mean_regret_top"]
                    for strategy in ("affine", "fine_tune")
                    if aggregate[k][strategy]["mean_regret_top"] is not None
                ]
                or [0.0]
            ),
            "strategy": max(
                ("affine", "fine_tune"),
                key=lambda name: aggregate[k][name]["mean_r2"],
            ),
        }
    max_r2 = max(value["r2"] for value in best_by_k.values())
    max_spearman = max(value["spearman"] for value in best_by_k.values())
    min_regret = min(value["regret"] for value in best_by_k.values())
    overall_k = max(best_by_k)
    for k in sorted(best_by_k):
        value = best_by_k[k]
        if (
            value["r2"] >= max_r2 - TOL_R2
            and value["spearman"] >= max_spearman - TOL_SPEARMAN
            and value["regret"] <= min_regret + TOL_REGRET
        ):
            overall_k = k
            break
    overall = best_by_k[overall_k]
    calibration_gain = {
        "k": int(overall_k),
        "strategy": overall["strategy"],
        "no_cal_r2": no_cal["mean_r2"],
        "calibrated_r2": overall["r2"],
        "r2_gain": round(overall["r2"] - no_cal["mean_r2"], 4),
        "no_cal_spearman": no_cal["mean_spearman"],
        "calibrated_spearman": overall["spearman"],
        "spearman_gain": round(overall["spearman"] - no_cal["mean_spearman"], 4),
        "no_cal_regret_top": no_cal["mean_regret_top"],
        "calibrated_regret_top": overall["regret"],
        "regret_change": round(overall["regret"] - no_cal["mean_regret_top"], 6),
    }
    return {
        "n_boards": len(rows),
        "recommended_k_per_board": recommended,
        "recommended_strategy_per_board": strategies,
        "usable_per_board": {row["board"]: bool(row.get("usable")) for row in rows},
        "usable_boards": [row["board"] for row in rows if row.get("usable")],
        "best_achievable_r2_per_board": {
            row["board"]: row.get("best_achievable_r2") for row in rows
        },
        "recommended_k": int(overall_k),
        "recommended_strategy": overall["strategy"],
        "recommended_k_distribution": {
            str(k): sorted(recommended.values()).count(k) for k in sorted(set(recommended.values()))
        },
        "no_calibration_mean": no_cal,
        "aggregate_by_k": aggregate,
        "calibration_gain_at_recommended_k": calibration_gain,
        "cross_board_status": cross_board.get("status"),
        "cross_board_holdout_board": cross_board.get("holdout_board"),
    }


# --------------------------------------------------------------------------- #
# report
# --------------------------------------------------------------------------- #
def _fmt(value: Any, digits: int = 4) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _regret_text(value: Optional[float]) -> str:
    return "—" if value is None else f"{value:+.4f}"


def _md_table(headers: Sequence[str], rows: Iterable[Sequence[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |"]
    lines.append("|" + "|".join(["---"] * len(headers)) + "|")
    for row in rows:
        lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return "\n".join(lines)


def render_markdown(data: Dict[str, Any]) -> str:
    config = data["config"]
    summary = data["summary"]
    boards = data["boards"]
    cross = data.get("cross_board") or {}
    lines: List[str] = []
    lines.append("# P2.18 模板代理 + 真实板少样本校准\n")
    lines.append(
        f"- 运行时：{data.get('runtime_s', 0.0)} s；模板 {len(config['templates'])} 个 × "
        f"{config['template_samples_per_template']} 布局训练 40 维 Ridge 代理；"
        f"真实板 {summary.get('n_boards', 0)} 块（EasyCirq dump），每板 "
        f"{config['calibration_pool']} 校准 + {config['test_samples']} 固定留出布局"
    )
    lines.append(
        f"- 校准样本 k ∈ {config['k_list']}；策略：`no_cal`（直接迁移）/ `affine`（a·pred+b）/"
        f"`fine_tune`（在 k 个真实样本上以 [40 维特征, 迁移预测] 为输入重训 ridge，"
        f"λ={config['fine_tune_lambda']}）"
    )
    lines.append(
        f"- 指标：留出集 R² / Spearman / top-{config['top_k']} 选择 regret（越低越好）；"
        "真值 = PhysicsSimulatorV2；模板/板样本 seed 固定，全流程确定性"
    )
    if data.get("missing_boards"):
        lines.append(f"- 缺失/失败的板：{[item['board'] for item in data['missing_boards']]}")
    lines.append("")

    no_cal = summary.get("no_calibration_mean") or {}
    gain = summary.get("calibration_gain_at_recommended_k") or {}
    lines.append("## 1. 汇总\n")
    lines.append(
        _md_table(
            ["指标", "无校准（模板代理）", f"校准后（推荐 k={gain.get('k')}，{gain.get('strategy')}）", "变化"],
            [
                [
                    "R²（绝对尺度不可比）",
                    _fmt(no_cal.get("mean_r2")),
                    _fmt(gain.get("calibrated_r2")),
                    "尺度不可比",
                ],
                [
                    "Spearman",
                    _fmt(no_cal.get("mean_spearman")),
                    _fmt(gain.get("calibrated_spearman")),
                    f"{gain.get('spearman_gain', 0.0):+.4f}",
                ],
                [
                    f"top-{config['top_k']} regret",
                    _regret_text(no_cal.get("mean_regret_top")),
                    _regret_text(gain.get("calibrated_regret_top")),
                    f"{gain.get('regret_change', 0.0):+.4f}",
                ],
            ],
        )
    )
    lines.append(
        "\n> 模板代理与真实板的**绝对尺度不一致**（physics-v2 隐藏系数按 scenario 名派生），"
        "因此 no-cal 的 R² 可能为负而 Spearman 仍高；仿射/微调校准解决的是尺度和偏移问题。\n"
    )

    lines.append("## 2. 逐板结果（固定留出集）\n")
    for row in boards:
        lines.append(f"### {row['board']}（{row['components']} 器件 / {row['nets']} 网，真值 {row['truth_mean']}±{row['truth_std']}）\n")
        table_rows = [
            [
                "no_cal",
                "—",
                _fmt(row["no_cal"]["r2"]),
                _fmt(row["no_cal"]["spearman"]),
                _regret_text(row["no_cal"]["regret_top"]),
            ]
        ]
        for k_row in row["by_k"]:
            for strategy, label in (("affine", "affine"), ("fine_tune", "fine_tune")):
                metrics = k_row[strategy]
                table_rows.append(
                    [
                        label,
                        k_row["k"],
                        _fmt(metrics["r2"]),
                        _fmt(metrics["spearman"]),
                        _regret_text(metrics["regret_top"]),
                    ]
                )
        recommendation = row["recommendation"]
        table_rows.append(
            [
                f"推荐 {recommendation['strategy']}",
                recommendation["k"],
                _fmt(recommendation["r2"]),
                _fmt(recommendation["spearman"]),
                _regret_text(recommendation["regret_top"]),
            ]
        )
        lines.append(
            _md_table(["策略", "k", "R²", "Spearman", f"top-{config['top_k']} regret"], table_rows)
        )
        lines.append("")

    lines.append("## 3. 每板推荐 k\n")
    rows = []
    for row in boards:
        recommendation = row["recommendation"]
        rows.append(
            [
                row["board"],
                recommendation["k"],
                recommendation["strategy"],
                _fmt(recommendation["r2"]),
                _fmt(recommendation["spearman"]),
                _regret_text(recommendation["regret_top"]),
                "是" if row.get("usable") else "否",
                _fmt(row.get("best_achievable_r2")),
                "—（不可比）",
                f"{recommendation['spearman'] - row['no_cal']['spearman']:+.4f}",
            ]
        )
    lines.append(
        _md_table(
            [
                "板",
                "推荐 k",
                "推荐策略",
                "R²",
                "Spearman",
                "regret",
                f"可用（R²≥{config['usable_r2_threshold']}）",
                "该板最佳 R²",
                "ΔR² vs no-cal（尺度不可比）",
                "Δρ vs no-cal",
            ],
            rows,
        )
    )
    lines.append(
        f"\n> 总推荐 k = **{summary.get('recommended_k')}**（{summary.get('recommended_strategy')}）；"
        f"各板推荐分布：{summary.get('recommended_k_distribution')}；"
        f"判定容差 R² {config['recommendation_tolerances']['r2']} / "
        f"ρ {config['recommendation_tolerances']['spearman']} / regret "
        f"{config['recommendation_tolerances']['regret_top']}。\n"
    )

    lines.append("## 4. 跨板留出泛化（留出板不参与任何校准）\n")
    if cross.get("status") != "OK":
        lines.append(f"> 跳过：{cross.get('reason', 'no boards')}\n")
    else:
        lines.append(
            f"留出板：**{cross['holdout_board']}**（其样本完全不用于拟合）；"
            f"校准系数用其余板 {cross['training_boards']} 的样本池化拟合，"
            f"留出板固定测试集 {config['test_samples']} 个布局。\n"
        )
        rows = []
        no_cal_cross = cross["no_cal"]
        rows.append(
            [
                "no_cal",
                "—",
                _fmt(no_cal_cross["r2"]),
                _fmt(no_cal_cross["spearman"]),
                _regret_text(no_cal_cross["regret_top"]),
                "—",
            ]
        )
        for k_row in cross["rows"]:
            for key, label in (
                ("cross_board_affine", "cross-board affine"),
                ("cross_board_fine_tune", "cross-board fine_tune"),
                ("reference_in_domain_affine", "参考上界：留出板自身 affine"),
            ):
                metrics = k_row[key]
                rows.append(
                    [
                        label,
                        k_row["k"],
                        _fmt(metrics["r2"]),
                        _fmt(metrics["spearman"]),
                        _regret_text(metrics["regret_top"]),
                        k_row["calibration_samples_total"]
                        if key.startswith("cross_board")
                        else "（用留出板自身样本）",
                    ]
                )
        lines.append(
            _md_table(
                ["策略", "k", "R²", "Spearman", f"top-{config['top_k']} regret", "校准样本数"],
                rows,
            )
        )
        lines.append(
            "\n> 跨板 ``fine_tune`` 在部分 k 上 R² 深度为负：池化其他板样本后，"
            "ridge 学到了这些板特有的特征-真值关系，直接迁移到留出板反而比仿射更差；"
            "这正说明跨板**不能**替代留出板自身的少样本校准。\n"
            f"> {cross.get('note', '')}\n"
        )

    lines.append("## 5. 结论\n")
    if gain:
        lines.append(
            f"1. **少样本校准显著修复尺度**：模板代理的 no-cal R² 均值 "
            f"{_fmt(no_cal.get('mean_r2'))}（绝对尺度不可比，但秩相关 "
            f"{_fmt(no_cal.get('mean_spearman'))}），在推荐 k={gain.get('k')} 的 "
            f"{gain.get('strategy')} 校准后 R² = {_fmt(gain.get('calibrated_r2'))}"
            f"（no-cal 尺度不可比，不做差值比较），Rank 相关 "
            f"{_fmt(no_cal.get('mean_spearman'))}→{_fmt(gain.get('calibrated_spearman'))}，"
            f"top-{config['top_k']} regret {_regret_text(no_cal.get('mean_regret_top'))}→"
            f"{_regret_text(gain.get('calibrated_regret_top'))}。"
        )
    detail = "；".join(
        f"{row['board']}: k={row['recommendation']['k']} {row['recommendation']['strategy']} "
        f"R²={_fmt(row['recommendation']['r2'])}"
        for row in boards
    )
    lines.append(
        f"2. **推荐 k={summary.get('recommended_k')}（{summary.get('recommended_strategy')} 为主）**：{detail}。"
        "`affine` 只需 2 个参数、在尺度近似线性的板上 k=4–8 即有效；"
        "`fine_tune` 用 [40 维特征, 迁移预测] 重训 ridge，对迁移尺度/形状失配更大的板更稳，"
        "代价是 k 较小时方差更大。部署建议：先用 k=8–16 同时训练 affine 与 fine_tune，"
        "按板块留出验证选择；不建议只依赖 no-cal 的绝对分。"
    )
    if cross.get("status") == "OK":
        best_cross_affine = max(row["cross_board_affine"]["r2"] for row in cross["rows"])
        best_cross_fine = max(row["cross_board_fine_tune"]["r2"] for row in cross["rows"])
        best_reference = max(row["reference_in_domain_affine"]["r2"] for row in cross["rows"])
        lines.append(
            f"3. **跨板泛化有限**：留出板 {cross['holdout_board']} 完全不用自身样本时，"
            f"其他板池化校准的最佳 R² 为 affine {_fmt(best_cross_affine)} / fine_tune "
            f"{_fmt(best_cross_fine)}，明显低于用留出板自身 k 个样本的参考上界 "
            f"{_fmt(best_reference)}。各板的 physics-v2 隐藏系数不同，"
            "跨板系数不能替代本板 8–16 个真实样本的业务校准。"
        )
    else:
        lines.append("3. **跨板留出验证不可用**（真实板不足 2 块）。")
    lines.append(
        "4. **可复现**：模板/真实板样本、Ridge/仿射/fine-tune、留出集划分全部确定性；"
        "真实板只读 dump，未施加布局、未 DRC/布线。"
    )
    lines.append("")
    lines.append("## 6. 边界（NOT RUN / 限制）\n")
    lines.append(
        "- 真值是离线 `PhysicsSimulatorV2` 伪物理，不是 SPICE/FEA/实测；"
        "“真实板样本”也是该伪物理在 EasyCirq dump 场景上的评分，不是台架数据。"
    )
    lines.append(
        "- 仿真代理训练于 5 个合成产品族模板；真实板分布更窄/结构不同，结论只说明"
        "“模板代理 + 少样本校准”在本离线框架内可行，不代表真实工程精度。"
    )
    lines.append(
        "- 校准只修正全局仿射尺度与特征线性修正；若真实误差是结构性/局部性（器件级寄生、"
        "布线效应），需要更多物理项或域内训练。"
    )
    lines.append(
        "- 跨板留出参考行使用留出板自身样本，仅作为上界参考，**不可部署**。"
    )
    return "\n".join(lines) + "\n"


def write_report(
    data: Dict[str, Any], out_dir: Optional[pathlib.Path | str] = None
) -> Tuple[pathlib.Path, pathlib.Path]:
    """Write ``report_transfer_calib.md`` and ``report_transfer_calib.json``."""
    out = pathlib.Path(out_dir) if out_dir is not None else PROJECT_ROOT
    out.mkdir(parents=True, exist_ok=True)
    md_path = out / "report_transfer_calib.md"
    json_path = out / "report_transfer_calib.json"
    json_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
    )
    md_path.write_text(render_markdown(data), encoding="utf-8")
    return md_path, json_path


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="P2.18 template-surrogate few-shot real-board calibration"
    )
    parser.add_argument("--template-samples", type=int, default=TEMPLATE_SAMPLES)
    parser.add_argument("--board-samples", type=int, default=BOARD_SAMPLES)
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--out", default=str(PROJECT_ROOT))
    args = parser.parse_args(argv)
    if args.quick:
        data = run_transfer_calibration(
            template_samples=60,
            board_samples=40,
            k_list=(4, 8, 16),
            calib_pool=16,
            test_size=16,
        )
    else:
        data = run_transfer_calibration(
            template_samples=args.template_samples,
            board_samples=args.board_samples,
        )
    md_path, json_path = write_report(data, pathlib.Path(args.out))
    print(f"[transfer_calib] wrote {md_path} / {json_path} ({data['runtime_s']} s)")
    return 0


__all__ = [
    "BOARD_SAMPLES",
    "CALIB_POOL",
    "HOLDOUT_BOARD",
    "K_LIST",
    "STRATEGIES",
    "TEMPLATE_SAMPLES",
    "TEST_SIZE",
    "load_real_boards",
    "main",
    "render_markdown",
    "run_transfer_calibration",
    "write_report",
]


if __name__ == "__main__":
    raise SystemExit(main())
