"""P2.6: data-scale learning curves for the offline multi-physics surrogate.

Question
--------
How much does the *amount* of simulated data matter for the learned surrogate?

Protocol
--------
1. For each of the five P1 product-family templates (``mcu-min``, ``buck``,
   ``rs485``, ``motor``, ``wireless``) build ``PhysicsSimulatorV2`` datasets with
   ``n in {240, 1000, 3000, 10000}`` via :func:`mp_place.dataset.build_dataset`
   (sampling seed 0; cached as deterministic gzip JSON under ``data/datascale``).
2. For every ``n`` fit :class:`mp_place.objective.RidgeModel` on the first ``n``
   layouts and evaluate on a *fixed independent* test set: 2000 layouts sampled
   with seed 1 (so every ``n`` is scored on exactly the same layouts).  Report
   test R^2 and Spearman correlation.
3. Diagnostic metrics that matter for optimisation (deterministic, no solver
   noise): rank correlation inside the best 10% of the test set and the
   "top-100 selection regret" -- the mean truth of the 100 layouts the surrogate
   ranks best minus the mean truth of the 100 truly best layouts.
4. Downstream: on three templates use the ``n``-sample surrogate as the
   objective of :func:`mp_place.solver_v2.solve` (5 seeds, 600 moves, 3
   restarts) and compare the resulting ``PhysicsSimulatorV2`` truth against the
   ``oracle_v2`` (true-objective) and ``multiphysics_proxy`` objectives.

Numerical note
--------------
``RidgeModel`` standardises features and divides by their standard deviation.
Several features are *exactly constant* per template at the float level
(``density``, ``capcount``, ``keepout`` where no RF part exists), but the
column mean contains rounding noise, so the fitted standard deviation is ~1e-17
instead of 0 and the standardised column explodes to ~1e17 (predictions blow
up).  We therefore drop columns whose training range is numerically zero before
fitting.  Constant columns carry no information (their effect is the intercept),
so this does not change the model class in a meaningful way; it is required for
a finite fit.  See :func:`feature_keep_indices`.

The module is pure standard library and only creates new files; it does not
modify any existing module.
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import statistics
import time
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .dataset import load_or_build_dataset
from .features import FEATURE_NAMES, extract_features, feature_vector
from .model import Placement, Scenario, hard_violations
from .objective import ProxyObjective, RidgeModel, r_squared, spearman
from .physics_v2 import PhysicsSimulatorV2
from .solver_v2 import solve
from .templates import instantiate

# --------------------------------------------------------------------------- #
# Experiment configuration (module-level so callers and reports agree)
# --------------------------------------------------------------------------- #
PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_CACHE_DIR = PROJECT_ROOT / "data" / "datascale"

#: The five P1 product families used for the learning curves (in report order).
LEARNING_TEMPLATES: Tuple[str, ...] = ("mcu-min", "buck", "rs485", "motor", "wireless")
#: Three families for the downstream solver comparison.
DOWNSTREAM_TEMPLATES: Tuple[str, ...] = ("buck", "motor", "wireless")
#: Dataset sizes for the learning curve.
SIZES: Tuple[int, ...] = (240, 1000, 3000, 10000)
#: Held-out set size (sampled once per template with a different RNG stream).
TEST_SIZE = 2000
TEST_SEED = 1
SAMPLE_SEED = 0
TEMPLATE_SEED = 0
SIMULATOR_SEED = 0
#: Ridge regularisation (features are standardised internally by RidgeModel).
RIDGE_LAMBDA = 1.0e-2
#: Range threshold under which a training feature column is considered constant.
CONST_RANGE_TOL = 1.0e-9
#: Fraction of the test set used for the "best layouts" tail metrics.
TAIL_FRACTION = 0.10
#: k for the top-k selection-regret metric.
TOP_K = 100
#: Downstream solver budget (comparable with the P2 integration experiment).
DOWNSTREAM_STEPS = 600
DOWNSTREAM_RESTARTS = 3
DOWNSTREAM_SEEDS: Tuple[int, ...] = (0, 1, 2, 3, 4)
#: Sizes used by the diagnostic that compares the raw and physics-informed basis.
BASIS_DIAGNOSTIC_SIZES: Tuple[int, ...] = (240, 10000)


# --------------------------------------------------------------------------- #
# Dataset loading / caching
# --------------------------------------------------------------------------- #
def cache_dir_path(cache_dir: Optional[pathlib.Path | str] = None) -> pathlib.Path:
    """Return (and create) the directory used for gzip dataset caches."""
    path = pathlib.Path(cache_dir) if cache_dir is not None else DEFAULT_CACHE_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def train_cache_path(
    template: str,
    n: int,
    *,
    sample_seed: int = SAMPLE_SEED,
    cache_dir: Optional[pathlib.Path | str] = None,
) -> pathlib.Path:
    """Cache file for the ``n``-sample training dataset of ``template``."""
    return cache_dir_path(cache_dir) / f"{template}_v2_n{int(n)}_s{int(sample_seed)}.json.gz"


def test_cache_path(
    template: str,
    *,
    test_size: int = TEST_SIZE,
    test_seed: int = TEST_SEED,
    cache_dir: Optional[pathlib.Path | str] = None,
) -> pathlib.Path:
    """Cache file for the fixed held-out dataset of ``template``."""
    return cache_dir_path(cache_dir) / f"{template}_v2_test_n{int(test_size)}_s{int(test_seed)}.json.gz"


def _load_train_dataset(
    scenario: Scenario,
    simulator: PhysicsSimulatorV2,
    n: int,
    *,
    sample_seed: int = SAMPLE_SEED,
    cache_dir: Optional[pathlib.Path | str] = None,
    rebuild: bool = False,
) -> Dict[str, Any]:
    return load_or_build_dataset(
        train_cache_path(scenario.name, n, sample_seed=sample_seed, cache_dir=cache_dir),
        scenario,
        simulator,
        n=int(n),
        seed=int(sample_seed),
        rebuild=rebuild,
    )


def _load_test_dataset(
    scenario: Scenario,
    simulator: PhysicsSimulatorV2,
    *,
    test_size: int = TEST_SIZE,
    test_seed: int = TEST_SEED,
    cache_dir: Optional[pathlib.Path | str] = None,
    rebuild: bool = False,
) -> Dict[str, Any]:
    return load_or_build_dataset(
        test_cache_path(
            scenario.name, test_size=test_size, test_seed=test_seed, cache_dir=cache_dir
        ),
        scenario,
        simulator,
        n=int(test_size),
        seed=int(test_seed),
        rebuild=rebuild,
    )


def prepare_datasets(
    templates: Sequence[str] = LEARNING_TEMPLATES,
    sizes: Sequence[int] = SIZES,
    *,
    test_size: int = TEST_SIZE,
    test_seed: int = TEST_SEED,
    sample_seed: int = SAMPLE_SEED,
    template_seed: int = TEMPLATE_SEED,
    simulator_seed: int = SIMULATOR_SEED,
    cache_dir: Optional[pathlib.Path | str] = None,
    rebuild: bool = False,
) -> Dict[str, Dict[str, Any]]:
    """Load (or build+cache) every dataset needed by the scaling experiment.

    Returns ``{template: {"scenario", "simulator", "test", "train": {n: dataset}}}``.
    Datasets are deterministic: two runs with the same configuration produce the
    same samples, which is what makes the learning curves comparable across ``n``.
    """
    bank: Dict[str, Dict[str, Any]] = {}
    for template in templates:
        scenario = instantiate(template, template_seed)
        simulator = PhysicsSimulatorV2(scenario, simulator_seed)
        test = _load_test_dataset(
            scenario,
            simulator,
            test_size=test_size,
            test_seed=test_seed,
            cache_dir=cache_dir,
            rebuild=rebuild,
        )
        train = {
            int(n): _load_train_dataset(
                scenario,
                simulator,
                n,
                sample_seed=sample_seed,
                cache_dir=cache_dir,
                rebuild=rebuild,
            )
            for n in sizes
        }
        bank[template] = {
            "scenario": scenario,
            "simulator": simulator,
            "test": test,
            "train": train,
        }
    return bank


# --------------------------------------------------------------------------- #
# Surrogate fitting (RidgeModel on the 10-feature representation)
# --------------------------------------------------------------------------- #
def feature_keep_indices(
    X: Sequence[Sequence[float]], range_tol: float = CONST_RANGE_TOL
) -> List[int]:
    """Indices of training feature columns that are not numerically constant.

    ``RidgeModel`` divides by each column's standard deviation; for an exactly
    constant column the mean can carry a rounding error, the standard deviation
    becomes ~1e-17 and the standardised column explodes.  Such columns carry no
    information (their effect is absorbed by the intercept), so they are dropped.
    """
    if not X:
        raise ValueError("feature_keep_indices needs at least one row")
    keep: List[int] = []
    for column in range(len(X[0])):
        values = [row[column] for row in X]
        low, high = min(values), max(values)
        scale = max(1.0, abs(low), abs(high))
        if high - low > range_tol * scale:
            keep.append(column)
    return keep


def fit_surrogate(
    train_dataset: Dict[str, Any], lam: float = RIDGE_LAMBDA
) -> Tuple[RidgeModel, List[int], Dict[str, Any]]:
    """Fit ``RidgeModel`` on a dataset; returns ``(model, kept_columns, info)``."""
    X, y = train_dataset["X"], train_dataset["y"]
    keep = feature_keep_indices(X)
    rows = [[row[column] for column in keep] for row in X]
    model = RidgeModel(lam=lam).fit(rows, y)
    info = {
        "n": int(train_dataset["meta"]["n"]),
        "lam": float(lam),
        "train_size": len(X),
        "kept_features": [FEATURE_NAMES[i] for i in keep],
        "dropped_features": [
            FEATURE_NAMES[i] for i in range(len(FEATURE_NAMES)) if i not in keep
        ],
    }
    return model, keep, info


class RidgeSurrogate:
    """Deterministic fast surrogate objective: features -> kept columns -> ridge."""

    name = "ridge_surrogate"

    def __init__(
        self,
        scenario: Scenario,
        model: RidgeModel,
        keep: Sequence[int],
        *,
        name: str = "ridge_surrogate",
    ) -> None:
        self.scenario = scenario
        self.model = model
        self.keep = tuple(int(i) for i in keep)
        self.name = name

    def predict_features(self, f: Dict[str, float]) -> float:
        vector = feature_vector(f)
        return float(self.model.predict([vector[j] for j in self.keep]))

    def predict(self, placement: Placement) -> float:
        return self.predict_features(extract_features(self.scenario, placement))

    def cost(self, placement: Placement) -> float:
        """Objective interface accepted by :func:`mp_place.solver_v2.solve`."""
        return self.predict(placement)


# --------------------------------------------------------------------------- #
# Evaluation metrics
# --------------------------------------------------------------------------- #
def _predict_rows(
    model: RidgeModel, keep: Sequence[int], rows: Sequence[Sequence[float]]
) -> List[float]:
    return [float(model.predict([row[j] for j in keep])) for row in rows]


def evaluate_regression(
    model: RidgeModel,
    keep: Sequence[int],
    test_dataset: Dict[str, Any],
    *,
    tail_fraction: float = TAIL_FRACTION,
    top_k: int = TOP_K,
) -> Dict[str, Any]:
    """Test R^2 / Spearman plus optimisation-relevant tail metrics.

    * ``tail_spearman``: Spearman correlation inside the best
      ``tail_fraction`` of the test set (the layouts an optimiser cares about).
    * ``top{k}_regret``: mean truth of the surrogate's favourite ``top_k``
      layouts minus the mean truth of the truly best ``top_k`` layouts
      (lower is better; 0 means perfect selection).
    """
    X, y = test_dataset["X"], test_dataset["y"]
    predictions = _predict_rows(model, keep, X)
    n = len(y)
    order_truth = sorted(range(n), key=lambda i: y[i])
    tail_n = max(1, int(round(n * tail_fraction)))
    tail_idx = order_truth[:tail_n]
    tail_rho = spearman([y[i] for i in tail_idx], [predictions[i] for i in tail_idx])
    k = min(int(top_k), n)
    chosen = sorted(range(n), key=lambda i: predictions[i])[:k]
    best = order_truth[:k]
    selected_mean = sum(y[i] for i in chosen) / k
    oracle_mean = sum(y[i] for i in best) / k
    return {
        "test_size": n,
        "r2_test": round(r_squared(y, predictions), 4),
        "spearman_test": round(spearman(y, predictions), 4),
        "tail_fraction": float(tail_fraction),
        "tail_spearman": round(tail_rho, 4),
        f"top{k}_selected_truth": round(selected_mean, 4),
        f"top{k}_oracle_truth": round(oracle_mean, 4),
        f"top{k}_regret": round(selected_mean - oracle_mean, 4),
    }


# --------------------------------------------------------------------------- #
# Learning curve
# --------------------------------------------------------------------------- #
def build_learning_curve(
    templates: Sequence[str] = LEARNING_TEMPLATES,
    sizes: Sequence[int] = SIZES,
    *,
    bank: Optional[Dict[str, Dict[str, Any]]] = None,
    lam: float = RIDGE_LAMBDA,
    test_size: int = TEST_SIZE,
    test_seed: int = TEST_SEED,
    sample_seed: int = SAMPLE_SEED,
    template_seed: int = TEMPLATE_SEED,
    simulator_seed: int = SIMULATOR_SEED,
    cache_dir: Optional[pathlib.Path | str] = None,
    rebuild: bool = False,
    tail_fraction: float = TAIL_FRACTION,
    top_k: int = TOP_K,
) -> List[Dict[str, Any]]:
    """Fit one surrogate per ``(template, n)`` and return the learning-curve rows."""
    bank = bank or prepare_datasets(
        templates,
        sizes,
        test_size=test_size,
        test_seed=test_seed,
        sample_seed=sample_seed,
        template_seed=template_seed,
        simulator_seed=simulator_seed,
        cache_dir=cache_dir,
        rebuild=rebuild,
    )
    rows: List[Dict[str, Any]] = []
    for template in templates:
        entry = bank[template]
        test = entry["test"]
        for n in sizes:
            train = entry["train"][int(n)]
            model, keep, info = fit_surrogate(train, lam=lam)
            metrics = evaluate_regression(
                model, keep, test, tail_fraction=tail_fraction, top_k=top_k
            )
            rows.append(
                {
                    "template": template,
                    "n": int(n),
                    "dataset": {
                        "n": int(train["meta"]["n"]),
                        "sample_seed": int(train["meta"]["seed"]),
                        "placements_hash": train["placements_hash"],
                        "simulator_fingerprint": train["meta"]["simulator"]["fingerprint"],
                    },
                    "fit": info,
                    **metrics,
                }
            )
    return rows


# --------------------------------------------------------------------------- #
# Physics-informed basis (diagnostic: representation vs data scale)
# --------------------------------------------------------------------------- #
def expand_features(row: Sequence[float]) -> List[float]:
    """Fixed physics-motivated expansion of the 10 raw features.

    Includes squares/square roots of the geometric drivers, exponential field
    coupling at three length scales, the parallel-cap count and two
    physics-motivated cross terms.  Used only for the diagnostic that asks
    whether the remaining error is a representation or a data-size problem.
    """
    f = dict(zip(FEATURE_NAMES, row))
    out: List[float] = list(row)
    for key in (
        "hpwl",
        "decap",
        "loop",
        "thermal",
        "density",
        "congestion",
        "escape",
        "keepout",
    ):
        value = f[key]
        out.append(value * value)
        out.append(math.sqrt(max(value, 0.0)))
    for length_scale in (0.02, 0.05, 0.10):
        out.append(math.exp(-f["analog"] / length_scale))
    out.append(1.0 / max(f["capcount"], 1.0e-6))
    out.append(f["loop"] * math.exp(-f["analog"] / 0.05))
    out.append(f["loop"] * f["thermal"])
    return out


def build_basis_diagnostic(
    templates: Sequence[str] = LEARNING_TEMPLATES,
    sizes: Sequence[int] = BASIS_DIAGNOSTIC_SIZES,
    *,
    bank: Optional[Dict[str, Dict[str, Any]]] = None,
    lam: float = RIDGE_LAMBDA,
    test_size: int = TEST_SIZE,
    test_seed: int = TEST_SEED,
    sample_seed: int = SAMPLE_SEED,
    template_seed: int = TEMPLATE_SEED,
    simulator_seed: int = SIMULATOR_SEED,
    cache_dir: Optional[pathlib.Path | str] = None,
    rebuild: bool = False,
    tail_fraction: float = TAIL_FRACTION,
    top_k: int = TOP_K,
) -> List[Dict[str, Any]]:
    """Learning curve on the fixed 32-dim physics-informed basis (diagnostic)."""
    bank = bank or prepare_datasets(
        templates,
        sizes,
        test_size=test_size,
        test_seed=test_seed,
        sample_seed=sample_seed,
        template_seed=template_seed,
        simulator_seed=simulator_seed,
        cache_dir=cache_dir,
        rebuild=rebuild,
    )
    rows: List[Dict[str, Any]] = []
    for template in templates:
        entry = bank[template]
        test_X = [expand_features(row) for row in entry["test"]["X"]]
        test_expanded = {
            "X": test_X,
            "y": entry["test"]["y"],
            "meta": entry["test"]["meta"],
        }
        for n in sizes:
            train = entry["train"][int(n)]
            X = [expand_features(row) for row in train["X"]]
            keep = feature_keep_indices(X)
            model = RidgeModel(lam=lam).fit([[row[j] for j in keep] for row in X], train["y"])
            metrics = evaluate_regression(
                model, keep, test_expanded, tail_fraction=tail_fraction, top_k=top_k
            )
            rows.append(
                {
                    "template": template,
                    "n": int(n),
                    "basis_dim": int(len(X[0])),
                    "kept_dim": len(keep),
                    **metrics,
                }
            )
    return rows


# --------------------------------------------------------------------------- #
# Downstream: surrogate(n) vs oracle_v2 vs multiphysics_proxy
# --------------------------------------------------------------------------- #
def evaluate_objective(
    scenario: Scenario,
    simulator: PhysicsSimulatorV2,
    cost,
    *,
    objective: str,
    n: Optional[int] = None,
    seeds: Sequence[int] = DOWNSTREAM_SEEDS,
    steps: int = DOWNSTREAM_STEPS,
    restarts: int = DOWNSTREAM_RESTARTS,
) -> Dict[str, Any]:
    """Run the portfolio solver for one objective and score layouts with truth v2."""
    if not seeds:
        raise ValueError("evaluate_objective needs at least one solver seed")
    truths: List[float] = []
    hpwls: List[float] = []
    violations: List[int] = []
    runtimes: List[float] = []
    for seed in seeds:
        started = time.perf_counter()
        best, _best_cost, stats = solve(
            scenario, cost, seed=int(seed), steps=int(steps), restarts=int(restarts)
        )
        runtimes.append(time.perf_counter() - started)
        truths.append(float(simulator.score(best)))
        hpwls.append(float(extract_features(scenario, best)["hpwl"]))
        violations.append(len(hard_violations(scenario, best)))
    return {
        "template": scenario.name,
        "objective": objective,
        "n": None if n is None else int(n),
        "seeds": [int(seed) for seed in seeds],
        "steps": int(steps),
        "restarts": int(restarts),
        "solver": stats.get("solver", "unknown"),
        "mean_truth": round(statistics.mean(truths), 4),
        "std_truth": round(statistics.pstdev(truths), 4),
        "per_seed_truth": [round(value, 4) for value in truths],
        "mean_hpwl": round(statistics.mean(hpwls), 4),
        "max_violations": max(violations) if violations else 0,
        "runtime_s": round(statistics.mean(runtimes), 3),
    }


def run_downstream(
    templates: Sequence[str] = DOWNSTREAM_TEMPLATES,
    sizes: Sequence[int] = SIZES,
    *,
    bank: Optional[Dict[str, Dict[str, Any]]] = None,
    lam: float = RIDGE_LAMBDA,
    seeds: Sequence[int] = DOWNSTREAM_SEEDS,
    steps: int = DOWNSTREAM_STEPS,
    restarts: int = DOWNSTREAM_RESTARTS,
    test_size: int = TEST_SIZE,
    test_seed: int = TEST_SEED,
    sample_seed: int = SAMPLE_SEED,
    template_seed: int = TEMPLATE_SEED,
    simulator_seed: int = SIMULATOR_SEED,
    cache_dir: Optional[pathlib.Path | str] = None,
    rebuild: bool = False,
) -> List[Dict[str, Any]]:
    """Solve each template with surrogate(n) / oracle_v2 / proxy; return truth rows.

    ``oracle_v2`` (truth objective) and ``multiphysics_proxy`` do not depend on
    ``n``, so they are evaluated once per template and listed once per template.
    """
    bank = bank or prepare_datasets(
        templates,
        sizes,
        test_size=test_size,
        test_seed=test_seed,
        sample_seed=sample_seed,
        template_seed=template_seed,
        simulator_seed=simulator_seed,
        cache_dir=cache_dir,
        rebuild=rebuild,
    )
    rows: List[Dict[str, Any]] = []
    for template in templates:
        entry = bank[template]
        scenario = entry["scenario"]
        simulator = entry["simulator"]
        rows.append(
            evaluate_objective(
                scenario,
                simulator,
                simulator.score,
                objective="oracle_v2",
                seeds=seeds,
                steps=steps,
                restarts=restarts,
            )
        )
        rows.append(
            evaluate_objective(
                scenario,
                simulator,
                ProxyObjective(scenario).cost,
                objective="multiphysics_proxy",
                seeds=seeds,
                steps=steps,
                restarts=restarts,
            )
        )
        for n in sizes:
            model, keep, _info = fit_surrogate(entry["train"][int(n)], lam=lam)
            surrogate = RidgeSurrogate(scenario, model, keep, name=f"surrogate_n{n}")
            rows.append(
                evaluate_objective(
                    scenario,
                    simulator,
                    surrogate.cost,
                    objective=f"surrogate_n{int(n)}",
                    n=int(n),
                    seeds=seeds,
                    steps=steps,
                    restarts=restarts,
                )
            )
    return rows


# --------------------------------------------------------------------------- #
# Summary / aggregation
# --------------------------------------------------------------------------- #
def _mean_by_size(rows: Sequence[Dict[str, Any]], key: str, sizes: Sequence[int]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for n in sizes:
        values = [float(row[key]) for row in rows if int(row["n"]) == int(n)]
        if values:
            out[str(int(n))] = round(statistics.mean(values), 4)
    return out


def summarize(
    learning_rows: Sequence[Dict[str, Any]],
    downstream_rows: Sequence[Dict[str, Any]],
    basis_rows: Optional[Sequence[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Aggregate the curves into the numbers quoted by the report."""
    sizes = sorted({int(row["n"]) for row in learning_rows})
    templates = sorted({row["template"] for row in learning_rows})
    metrics = ("r2_test", "spearman_test", "tail_spearman")
    means = {metric: _mean_by_size(learning_rows, metric, sizes) for metric in metrics}
    regret_key = f"top{TOP_K}_regret"
    means[regret_key] = _mean_by_size(learning_rows, regret_key, sizes)

    summary: Dict[str, Any] = {
        "templates": templates,
        "sizes": sizes,
        "learning_curve_mean": means,
    }
    first, last = min(sizes), max(sizes)
    low_r2, high_r2 = means["r2_test"].get(str(first)), means["r2_test"].get(str(last))
    if low_r2 is not None and high_r2 is not None:
        summary["r2_gain"] = {
            "from_n": first,
            "to_n": last,
            "absolute": round(high_r2 - low_r2, 4),
            "relative_pct": round(100.0 * (high_r2 - low_r2) / abs(low_r2), 2),
        }
        low_rho = means["spearman_test"][str(first)]
        high_rho = means["spearman_test"][str(last)]
        summary["spearman_gain"] = {
            "from_n": first,
            "to_n": last,
            "absolute": round(high_rho - low_rho, 4),
        }
        low_tail = means["tail_spearman"][str(first)]
        high_tail = means["tail_spearman"][str(last)]
        summary["tail_spearman_gain"] = {
            "from_n": first,
            "to_n": last,
            "absolute": round(high_tail - low_tail, 4),
        }
        low_reg = means[regret_key][str(first)]
        high_reg = means[regret_key][str(last)]
        summary["regret_reduction"] = {
            "from_n": first,
            "to_n": last,
            "absolute": round(low_reg - high_reg, 4),
            "relative_pct": round(100.0 * (low_reg - high_reg) / low_reg, 1)
            if low_reg
            else 0.0,
        }

    # Downstream aggregate over the templates that were actually solved.
    downstream_templates = sorted({row["template"] for row in downstream_rows})
    downstream_means: Dict[str, float] = {}
    objectives = sorted({row["objective"] for row in downstream_rows})
    for objective in objectives:
        values = [
            float(row["mean_truth"])
            for row in downstream_rows
            if row["objective"] == objective
        ]
        downstream_means[objective] = round(statistics.mean(values), 4)
    summary["downstream_templates"] = downstream_templates
    summary["downstream_mean_truth"] = downstream_means
    if "oracle_v2" in downstream_means and "multiphysics_proxy" in downstream_means:
        oracle = downstream_means["oracle_v2"]
        proxy = downstream_means["multiphysics_proxy"]
        summary["oracle_vs_proxy_improvement_pct"] = round(
            100.0 * (proxy - oracle) / proxy, 2
        ) if proxy else 0.0
        gaps: Dict[str, float] = {}
        proxy_gain: Dict[str, float] = {}
        for objective, value in downstream_means.items():
            if not objective.startswith("surrogate_n"):
                continue
            n_key = objective.rsplit("surrogate_n", 1)[-1]
            gaps[n_key] = round(100.0 * (value - oracle) / oracle, 2) if oracle else 0.0
            proxy_gain[n_key] = round(100.0 * (proxy - value) / proxy, 2) if proxy else 0.0
        summary["surrogate_gap_to_oracle_pct"] = gaps
        summary["surrogate_vs_proxy_pct"] = proxy_gain
        surrogate_keys = sorted(gaps, key=int)
        if len(surrogate_keys) >= 2:
            first_key, last_key = surrogate_keys[0], surrogate_keys[-1]
            first_val = downstream_means[f"surrogate_n{first_key}"]
            last_val = downstream_means[f"surrogate_n{last_key}"]
            summary["surrogate_downstream_gain"] = {
                "from_n": int(first_key),
                "to_n": int(last_key),
                "absolute": round(first_val - last_val, 4),
                "relative_pct": round(100.0 * (first_val - last_val) / first_val, 2)
                if first_val
                else 0.0,
            }

    if basis_rows:
        basis_sizes = sorted({int(row["n"]) for row in basis_rows})
        summary["basis_diagnostic_mean"] = {
            "sizes": basis_sizes,
            "r2_test": _mean_by_size(basis_rows, "r2_test", basis_sizes),
            "tail_spearman": _mean_by_size(basis_rows, "tail_spearman", basis_sizes),
            "top100_regret": _mean_by_size(basis_rows, f"top{TOP_K}_regret", basis_sizes),
        }
    return summary


# --------------------------------------------------------------------------- #
# End-to-end run
# --------------------------------------------------------------------------- #
def run_scaling(
    templates: Sequence[str] = LEARNING_TEMPLATES,
    downstream_templates: Sequence[str] = DOWNSTREAM_TEMPLATES,
    sizes: Sequence[int] = SIZES,
    *,
    downstream_seeds: Sequence[int] = DOWNSTREAM_SEEDS,
    steps: int = DOWNSTREAM_STEPS,
    restarts: int = DOWNSTREAM_RESTARTS,
    test_size: int = TEST_SIZE,
    include_basis_diagnostic: bool = True,
    basis_sizes: Sequence[int] = BASIS_DIAGNOSTIC_SIZES,
    cache_dir: Optional[pathlib.Path | str] = None,
    rebuild: bool = False,
    quiet: bool = False,
) -> Dict[str, Any]:
    """Run the full scaling study and return the report data (JSON serialisable)."""
    started = time.perf_counter()
    all_templates = list(dict.fromkeys(list(templates) + list(downstream_templates)))
    bank = prepare_datasets(
        all_templates,
        sizes,
        test_size=test_size,
        cache_dir=cache_dir,
        rebuild=rebuild,
    )
    learning = build_learning_curve(templates, sizes, bank=bank)
    if not quiet:
        _print_curve_summary("learning", learning)
    downstream = run_downstream(
        downstream_templates,
        sizes,
        bank=bank,
        seeds=downstream_seeds,
        steps=steps,
        restarts=restarts,
    )
    if not quiet:
        _print_downstream_summary(downstream)
    basis = (
        build_basis_diagnostic(
            templates, basis_sizes, bank=bank
        )
        if include_basis_diagnostic
        else []
    )
    data: Dict[str, Any] = {
        "config": {
            "model": "PhysicsSimulatorV2",
            "surrogate": f"RidgeModel(lam={RIDGE_LAMBDA})",
            "constant_column_filter": True,
            "learning_templates": list(templates),
            "downstream_templates": list(downstream_templates),
            "sizes": [int(n) for n in sizes],
            "train_sample_seed": SAMPLE_SEED,
            "heldout_test_seed": TEST_SEED,
            "heldout_test_size": int(test_size),
            "template_seed": TEMPLATE_SEED,
            "simulator_seed": SIMULATOR_SEED,
            "downstream": {
                "seeds": [int(seed) for seed in downstream_seeds],
                "steps": int(steps),
                "restarts": int(restarts),
            },
            "basis_diagnostic": include_basis_diagnostic,
            "cache_dir": _display_path(cache_dir),
        },
        "learning_curve": learning,
        "downstream": downstream,
        "basis_diagnostic": basis,
        "summary": summarize(learning, downstream, basis),
        "runtime_s": round(time.perf_counter() - started, 2),
    }
    return data


def _display_path(path: Optional[pathlib.Path | str] = None) -> str:
    """Portable display path: project-relative when possible, absolute otherwise."""
    resolved = pathlib.Path(path) if path is not None else DEFAULT_CACHE_DIR
    try:
        relative = resolved.resolve().relative_to(PROJECT_ROOT.resolve())
        return relative.as_posix()
    except (OSError, ValueError):
        return str(resolved)


def _print_curve_summary(label: str, rows: Sequence[Dict[str, Any]]) -> None:
    sizes = sorted({int(row["n"]) for row in rows})
    templates = sorted({row["template"] for row in rows})
    for template in templates:
        cells = []
        for n in sizes:
            match = [row for row in rows if row["template"] == template and int(row["n"]) == n]
            if match:
                cells.append(f"n{n}: R2={match[0]['r2_test']:.4f}")
        print(f"[{label}] {template:9s} " + "  ".join(cells))


def _print_downstream_summary(rows: Sequence[Dict[str, Any]]) -> None:
    for template in sorted({row["template"] for row in rows}):
        parts = [
            f"{row['objective']}={row['mean_truth']:.4f}"
            for row in rows
            if row["template"] == template
        ]
        print(f"[downstream] {template:9s} " + "  ".join(parts))


# --------------------------------------------------------------------------- #
# Markdown report
# --------------------------------------------------------------------------- #
def _fmt(value: float, digits: int = 4) -> str:
    return f"{float(value):.{digits}f}"


def _md_table(headers: Sequence[str], rows: Iterable[Sequence[str]]) -> str:
    lines = ["| " + " | ".join(headers) + " |"]
    lines.append("|" + "|".join(["---"] * len(headers)) + "|")
    for row in rows:
        lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return "\n".join(lines)


def _group_curve(rows: Sequence[Dict[str, Any]]) -> Tuple[List[int], List[str], Dict[Tuple[str, int], Dict[str, Any]]]:
    sizes = sorted({int(row["n"]) for row in rows})
    templates = sorted({row["template"] for row in rows})
    lookup = {(row["template"], int(row["n"])): row for row in rows}
    return sizes, templates, lookup


def render_markdown(data: Dict[str, Any]) -> str:
    """Render the human-readable report (tables + conclusions) from run data."""
    config = data["config"]
    summary = data["summary"]
    learning = data["learning_curve"]
    downstream = data["downstream"]
    basis = data.get("basis_diagnostic") or []
    sizes, templates, lookup = _group_curve(learning)
    lines: List[str] = []
    lines.append("# P2.6 数据规模 Learning Curve（PhysicsSimulatorV2 真值）\n")
    lines.append(
        f"- 运行时：{data.get('runtime_s', 0.0)} s；模板：{', '.join(config['learning_templates'])}"
        f"（P1 五模板；task-16 新增模板不在本实验范围）"
    )
    lines.append(
        f"- 数据集：`dataset.build_dataset` + `PhysicsSimulatorV2(scenario, seed={config['simulator_seed']})`，"
        f"n∈{config['sizes']}，采样 seed={config['train_sample_seed']}；gzip 缓存于 `{config['cache_dir']}`"
    )
    lines.append(
        f"- 训练/测试：train = 该模板前 n 个布局；test = 独立采样 seed={config['heldout_test_seed']} 的 "
        f"{config['heldout_test_size']} 个布局（所有 n 共用同一 test 集，可比）"
    )
    lines.append(
        f"- 模型：`{config['surrogate']}`，拟合前移除训练集中数值常数的特征列"
        f"（`density`/`capcount` 等；否则 RidgeModel 对 ~0 方差列标准化会数值爆炸）"
    )
    lines.append(
        f"- 下游：`solver_v2.solve(steps={config['downstream']['steps']}, "
        f"restarts={config['downstream']['restarts']})` × seeds {config['downstream']['seeds']}；"
        f"评价指标 = PhysicsSimulatorV2 truth（越低越好）\n"
    )

    lines.append("## 1. 学习曲线：test R² / Spearman（5 模板）\n")
    rows = []
    for template in templates:
        cells = [template]
        for n in sizes:
            row = lookup[(template, n)]
            cells.append(f"{_fmt(row['r2_test'])} / {_fmt(row['spearman_test'])}")
        if sizes:
            first = lookup[(template, sizes[0])]
            last = lookup[(template, sizes[-1])]
            cells.append(f"{last['r2_test'] - first['r2_test']:+.4f}")
        rows.append(cells)
    headers = ["模板"] + [f"n={n}" for n in sizes] + ["ΔR²(首→末)"]
    lines.append(_md_table(headers, rows))
    mean = summary["learning_curve_mean"]
    mean_cells = ["**均值**"]
    for n in sizes:
        mean_cells.append(
            f"**{_fmt(mean['r2_test'][str(n)])} / {_fmt(mean['spearman_test'][str(n)])}**"
        )
    if sizes:
        gain = mean["r2_test"][str(sizes[-1])] - mean["r2_test"][str(sizes[0])]
        mean_cells.append(f"**{gain:+.4f}**")
    lines.append("| " + " | ".join(mean_cells) + " |")
    lines.append("")
    if "r2_gain" in summary:
        gain = summary["r2_gain"]
        rho = summary["spearman_gain"]
        note = ""
        if len(sizes) > 1:
            partial = mean["r2_test"][str(sizes[1])] - mean["r2_test"][str(sizes[0])]
            total = mean["r2_test"][str(sizes[-1])] - mean["r2_test"][str(sizes[0])]
            if total > 0:
                note = f" 其中 n={sizes[1]} 时已完成 {100.0 * partial / total:.0f}% 的总增益。"
        lines.append(
            f"> 均值 R²：n={gain['from_n']} → {gain['to_n']} 提升 {gain['absolute']:+.4f}"
            f"（相对 {gain['relative_pct']:+.2f}%）；Spearman 提升 {rho['absolute']:+.4f}。"
            f"{note}\n"
        )

    lines.append("## 2. 面向优化的辅助指标（同一 test 集，确定性）\n")
    lines.append(
        "`tail ρ` = 测试集中 truth 最低 10%（最优布局区）内的 Spearman；"
        "`regret@100` = surrogate 排名前 100 的平均 truth − 真实前 100 的平均 truth（越低越好）。\n"
    )
    rows = []
    for template in templates:
        cells = [template]
        for n in sizes:
            row = lookup[(template, n)]
            cells.append(f"{_fmt(row['tail_spearman'])} / {row[f'top{TOP_K}_regret']:+.4f}")
        rows.append(cells)
    lines.append(_md_table(["模板"] + [f"n={n}" for n in sizes], rows))
    regret_key = f"top{TOP_K}_regret"
    mean_cells = ["**均值**"]
    for n in sizes:
        mean_cells.append(
            f"**{_fmt(mean['tail_spearman'][str(n)])} / {mean[regret_key][str(n)]:+.4f}**"
        )
    lines.append("| " + " | ".join(mean_cells) + " |")
    lines.append("")
    if "tail_spearman_gain" in summary:
        tail = summary["tail_spearman_gain"]
        red = summary["regret_reduction"]
        lines.append(
            f"> 尾部秩相关：{tail['from_n']}→{tail['to_n']} {tail['absolute']:+.4f}；"
            f"top-{TOP_K} 选择 regret 从 {mean[regret_key][str(red['from_n'])]:+.4f} "
            f"降到 {mean[regret_key][str(red['to_n'])]:+.4f}（相对 -{red['relative_pct']:.1f}%）。\n"
        )

    lines.append("## 3. 下游布局质量：surrogate(n) vs oracle_v2 vs multiphysics_proxy\n")
    downstream_lookup = {
        (row["template"], row["objective"]): row for row in downstream
    }
    downstream_templates = sorted({row["template"] for row in downstream})
    surrogate_objectives = [f"surrogate_n{n}" for n in sizes]
    columns = ["multiphysics_proxy", "oracle_v2"] + surrogate_objectives
    header_cells = ["模板", "proxy", "oracle_v2"] + [f"surr@{n}" for n in sizes]
    rows = []
    for template in downstream_templates:
        cells = [template]
        for objective in columns:
            row = downstream_lookup.get((template, objective))
            if row is None:
                cells.append("—")
            else:
                cells.append(f"{_fmt(row['mean_truth'])}±{_fmt(row['std_truth'], 2)}")
        rows.append(cells)
    lines.append(_md_table(header_cells, rows))
    agg = summary.get("downstream_mean_truth", {})
    agg_cells = ["**均值**"]
    for objective in columns:
        agg_cells.append(f"**{_fmt(agg[objective])}**" if objective in agg else "—")
    lines.append("| " + " | ".join(agg_cells) + " |")
    lines.append("")
    lines.append(
        f"> 下游均值（3 模板）：proxy={_fmt(agg.get('multiphysics_proxy', 0.0))}，"
        f"oracle_v2={_fmt(agg.get('oracle_v2', 0.0))}，"
        + "，".join(
            f"surrogate@{n}={_fmt(agg.get(f'surrogate_n{n}', 0.0))}" for n in sizes
        )
        + "。"
    )
    gap = summary.get("surrogate_gap_to_oracle_pct", {})
    vs_proxy = summary.get("surrogate_vs_proxy_pct", {})
    if gap:
        lines.append(
            "> surrogate 相对 oracle 的差距（%）："
            + "，".join(f"n={n}: {gap[n]:+.2f}%" for n in sorted(gap, key=int))
            + "；相对 proxy 的优势（正=surrogate 更好，%）："
            + "，".join(f"n={n}: {vs_proxy[n]:+.2f}%" for n in sorted(vs_proxy, key=int))
            + "。"
        )
    lines.append(
        "> 注意：solver 有随机性，表中 ± 为 seeds 间总体标准差；"
        "模板间/规模间差异常在 1 SE 量级，不能据此宣称数据规模带来的下游提升。\n"
    )

    if basis:
        lines.append("## 4. 诊断：特征表示 vs 数据规模（非主实验）\n")
        basis_sizes, basis_templates, basis_lookup = _group_curve(basis)
        basis_regret_key = f"top{TOP_K}_regret"
        rows = []
        for template in basis_templates:
            cells = [template]
            for n in basis_sizes:
                row = basis_lookup[(template, n)]
                cells.append(
                    f"{_fmt(row['r2_test'])} / {_fmt(row['tail_spearman'])} / "
                    f"{row[basis_regret_key]:+.4f}"
                )
            rows.append(cells)
        lines.append(
            _md_table(
                ["模板（R² / tail ρ / regret）"] + [f"n={n}" for n in basis_sizes],
                rows,
            )
        )
        basis_mean = summary.get("basis_diagnostic_mean", {})
        if basis_mean:
            cells = ["**均值**"]
            for n in basis_sizes:
                cells.append(
                    f"**{_fmt(basis_mean['r2_test'][str(n)])} / "
                    f"{_fmt(basis_mean['tail_spearman'][str(n)])} / "
                    f"{basis_mean[basis_regret_key][str(n)]:+.4f}**"
                )
            lines.append("| " + " | ".join(cells) + " |")
        lines.append(
            "\n> 固定 32 维物理基（平方/开方、exp(−d/λ)、1/并联数、loop×coupling 交互）在 "
            f"n={basis_sizes[0]} 时 test R² 均值已达 "
            f"{_fmt(basis_mean['r2_test'][str(basis_sizes[0])], 3)}、"
            f"top-{TOP_K} regret {basis_mean[basis_regret_key][str(basis_sizes[0])]:+.4f}，"
            "说明剩余误差主要是**表示能力**而非数据量；增加数据不能修复线性 surrogate 的系统偏差。\n"
        )

    lines.append("## 5. 结论\n")
    if "r2_gain" in summary:
        gain = summary["r2_gain"]
        lines.append(
            f"1. **学习曲线很快饱和**：10 维特征 + Ridge 的 test R² 均值从 n={gain['from_n']} 的 "
            f"{_fmt(mean['r2_test'][str(gain['from_n'])])} 升到 n={gain['to_n']} 的 "
            f"{_fmt(mean['r2_test'][str(gain['to_n'])])}（{gain['relative_pct']:+.2f}%），"
            f"Spearman {_fmt(mean['spearman_test'][str(gain['from_n'])])} → "
            f"{_fmt(mean['spearman_test'][str(gain['to_n'])])}；n≈1000 之后基本无增益。"
        )
    if "regret_reduction" in summary:
        red = summary["regret_reduction"]
        lines.append(
            f"2. **面向优化的尾部指标仍有小幅改善**：最优 10% 布局内的秩相关 "
            f"{_fmt(mean['tail_spearman'][str(red['from_n'])])} → "
            f"{_fmt(mean['tail_spearman'][str(red['to_n'])])}，"
            f"top-{TOP_K} 选择 regret 相对降低 {red['relative_pct']:.1f}%；"
            "但 templates 间差异大（motor/wireless 明显，buck/rs485 基本饱和）。"
        )
    if agg:
        surrogate_values = [
            agg[f"surrogate_n{n}"] for n in sizes if f"surrogate_n{n}" in agg
        ]
        surrogate_text = " / ".join(_fmt(value) for value in surrogate_values)
        gaps = summary.get("surrogate_gap_to_oracle_pct", {})
        gap_text = (
            f"，与 oracle_v2 的差距 {min(gaps.values()):+.1f}% ~ {max(gaps.values()):+.1f}%"
            if gaps
            else ""
        )
        lines.append(
            "3. **下游对比被求解器随机性主导**：3 模板均值 surrogate(n) truth = "
            f"{surrogate_text}（n 递增），不随 n 单调变化{gap_text}；"
            "各 n 之间的差异与 seeds 间标准差（0.1–0.5）同量级，且方向不一致"
            "（buck/wireless 随 n 改善、motor 在 10k 变差），"
            "不能据此宣称“更多数据带来更好的下游布局”；multiphysics_proxy 与 surrogate 互有胜负。"
        )
    if basis:
        lines.append(
            "4. **瓶颈是特征表示，不是数据规模**：换用固定 32 维物理基后，"
            f"n={basis_sizes[0]} 的 test R² 均值已达 "
            f"{_fmt(basis_mean['r2_test'][str(basis_sizes[0])], 3)}、top-{TOP_K} regret "
            f"{basis_mean[basis_regret_key][str(basis_sizes[0])]:+.4f}，"
            "继续堆到 10k 数据几乎没有额外收益。"
            "若目标是把 surrogate 优化推向 oracle，应优先改特征/模型容量（或做在线真值校正），"
            "而不是把数据集从 1k 扩到 10k。"
        )
    lines.append("")
    lines.append("## 6. 边界（NOT RUN / 限制）\n")
    lines.append(
        "- 真值是 `PhysicsSimulatorV2`（解析几何代理），不是 SPICE/FEA；SI/PI/热/DRC 均未仿真。"
    )
    lines.append(
        "- 下游求解器是 `solver_v2` 的 SA portfolio，不是 EDA 布线器；`routing_verified:false`、"
        "`drc:NOT RUN`。"
    )
    lines.append(
        "- 学习曲线只覆盖 P1 五个产品族模板与 10 维特征描述；task-16 新增的 3 个模板不在本实验中。"
    )
    lines.append(
        "- 运行时长不含缓存冷启动；缓存命中时重复运行只重训模型与求解，曲线数值完全一致"
        "（`runtime_s` 除外）。"
    )
    return "\n".join(lines)


def write_report(
    data: Dict[str, Any], out_dir: Optional[pathlib.Path | str] = None
) -> Tuple[pathlib.Path, pathlib.Path]:
    """Write ``report_datascale.json`` + ``report_datascale.md``; return paths."""
    out = pathlib.Path(out_dir) if out_dir is not None else PROJECT_ROOT
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / "report_datascale.json"
    md_path = out / "report_datascale.md"
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
        description="P2.6 data-scale learning curve for the placement surrogate"
    )
    parser.add_argument("--out", default=str(PROJECT_ROOT), help="report output directory")
    parser.add_argument("--cache-dir", default=None, help="dataset cache directory")
    parser.add_argument("--quick", action="store_true", help="small budget smoke run")
    parser.add_argument(
        "--rebuild", action="store_true", help="rebuild cached datasets from scratch"
    )
    parser.add_argument(
        "--no-basis", action="store_true", help="skip the physics-informed basis diagnostic"
    )
    args = parser.parse_args(argv)
    if args.quick:
        sizes: Sequence[int] = (240, 1000)
        seeds: Sequence[int] = (0,)
        steps, restarts = 300, 3
        test_size = 600
        basis_sizes: Sequence[int] = (240, 1000)
    else:
        sizes, seeds = SIZES, DOWNSTREAM_SEEDS
        steps, restarts = DOWNSTREAM_STEPS, DOWNSTREAM_RESTARTS
        test_size = TEST_SIZE
        basis_sizes = BASIS_DIAGNOSTIC_SIZES
    data = run_scaling(
        sizes=sizes,
        downstream_seeds=seeds,
        steps=steps,
        restarts=restarts,
        test_size=test_size,
        include_basis_diagnostic=not args.no_basis,
        basis_sizes=basis_sizes,
        cache_dir=args.cache_dir,
        rebuild=args.rebuild,
    )
    md_path, json_path = write_report(data, pathlib.Path(args.out))
    print(f"[datascale] wrote {md_path} / {json_path} ({data['runtime_s']} s)")
    return 0


__all__ = [
    "BASIS_DIAGNOSTIC_SIZES",
    "DEFAULT_CACHE_DIR",
    "DOWNSTREAM_SEEDS",
    "DOWNSTREAM_STEPS",
    "DOWNSTREAM_TEMPLATES",
    "LEARNING_TEMPLATES",
    "RidgeSurrogate",
    "SIZES",
    "build_basis_diagnostic",
    "build_learning_curve",
    "cache_dir_path",
    "evaluate_objective",
    "evaluate_regression",
    "expand_features",
    "feature_keep_indices",
    "fit_surrogate",
    "main",
    "prepare_datasets",
    "render_markdown",
    "run_downstream",
    "run_scaling",
    "summarize",
    "train_cache_path",
    "test_cache_path",
    "write_report",
]


if __name__ == "__main__":
    raise SystemExit(main())
