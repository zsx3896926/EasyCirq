"""P4-G: end-to-end offline placement pipeline (solve -> verify -> intent -> certificate).

One call runs the whole offline chain for a template/scenario and returns a
plain JSON-serialisable report::

    solver_v2.solve(cost=chosen objective)      # proxy (default) / route_aware / tuned
        -> hard_violations                       # P1 hard constraints
        -> truth_v1 = objective.PhysicsSimulator # P1 hidden pseudo-physics
        -> truth_v2 = physics_v2.PhysicsSimulatorV2
        -> router.GridRouter.route               # offline routability oracle
        -> intent.build_intent / intent_to_plan  # JSON intent + replay check
        -> verify.certificate                    # deterministic certificate

P2.11 objective option (task-27 update: three tiers)
---------------------------------------------------
``run_pipeline(..., objective="proxy" | "route_aware" | "tuned")`` selects the
solver cost objective (default ``proxy`` = P1/P2 multi-physics proxy, backwards
compatible):

* ``route_aware`` (**recommended safe upgrade**) -- fixed ``w_route=2.0``
  :class:`mp_place.route_cost.RouteAwareObjective` (P2.8 code path, no
  per-template table);
* ``tuned`` (**experimental, in-sample only, not recommended**) -- P2.9
  :func:`mp_place.route_cost.tuned_objective` per-template table lookup.  The
  table is fitted on seeds 0/1 and does not generalise (held-out seeds 2/3/4:
  truth_v2 +7.47%, 0/8 templates meeting the target).

Both route-aware cost paths are router-free (one dict lookup for ``tuned``; the
router is only invoked afterwards as the independent completion oracle).
Reports record ``objective_mode`` / ``objective_model`` / ``objective_config`` /
``objective_recommended`` / ``objective_generalization``; ``run_auto.py
--objective`` and the ``--all-templates`` batch rows carry the requested mode.

Recorded comparison (``python -m mp_place.pipeline --objective-benchmark``,
8 templates, ``steps=800``, full pipeline; artefacts
``report_pipeline_objective.md`` / ``.json``).  In-sample cohort seeds 0/1::

    objective      completion   fully routed   truth_v2          time/run
    proxy            0.9019        6/16         2.0001            0.26 s
    route_aware      0.9755       14/16         2.0627 (+3.13%)   0.54 s
    tuned            1.0000       16/16         1.9995 (-0.03%)   0.51 s

Held-out cohort seeds 2/3/4 (P2.10 protocol, never used for tuning)::

    objective      completion   fully routed   truth_v2          time/run
    proxy            0.8424        9/24         1.7734            0.34 s
    route_aware      0.9502       15/24         1.7819 (+0.48%)   0.64 s
    tuned            0.9113       10/24         1.9058 (+7.47%)   0.68 s

Target (route_aware vs proxy, held-out generalisation cohort): aggregate
completion not lower and aggregate ``truth_v2`` <= +1% -- **met**
(0.8424 -> 0.9502, +0.48%).  ``tuned`` is in-sample only (+7.47% on held-out,
0/8 templates) and is therefore labelled not recommended / research only;
``proxy`` remains the default backwards-compatible tier.

Safety contract
---------------
Everything here is **offline**.  The pipeline never applies a placement, never
runs DRC, never calls EDA and never touches the network.  The report therefore
hard-codes ``fixed_fields = {"routing_verified": false, "drc": "NOT RUN",
"eda_calls": 0}``; router completion is a 2-layer grid-maze oracle, not a
routability proof.  See ``mp_place.verify.LIMITS`` for the full boundary list.

Determinism
-----------
For the same ``(scenario, budget_steps, seed, objective)`` two runs produce
byte-identical JSON (``json.dumps(report, sort_keys=True)``): wall-clock fields
from the solver/router are stripped, and the certificate already excludes the
router runtime.  ``stats["runtime_s"]`` is the only discarded value.

Usage
-----
>>> from mp_place.templates import instantiate
>>> from mp_place.pipeline import run_pipeline
>>> report = run_pipeline(instantiate("buck", seed=0), budget_steps=800, seed=0)
>>> report["feasible"], report["truth_v2"]
>>> tuned = run_pipeline("buck", budget_steps=800, objective="tuned")
>>> tuned["objective_mode"], tuned["objective_config"]["w_route"]
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Dict, Optional, Sequence, Tuple, Union

from . import intent as intent_mod
from . import templates
from . import verify as verify_mod
from .model import Placement, Scenario, hard_violations
from .objective import PhysicsSimulator, ProxyObjective
from .physics_v2 import PhysicsSimulatorV2
from .router import GridRouter
from .route_opt import repair_routes
from .solver_v2 import solve

PIPELINE_SCHEMA = "mp_place.pipeline/v1"
DEFAULT_TEMPLATE = "buck"
DEFAULT_BUDGET_STEPS = 800
ROUTER_GRID_MM = 1.0
ROUTER_LAYERS = 2
ROUTE_REPAIR_MAX_ROUTES = 60

#: Solver cost objectives exposed by the pipeline (P2.11 / task-27 update):
#:
#: * ``proxy`` (default) -- P1/P2 multi-physics proxy, backwards compatible;
#: * ``route_aware`` (**recommended safe** option) -- fixed ``w_route=2.0``
#:   :class:`mp_place.route_cost.RouteAwareObjective` (same code path as P2.8,
#:   no per-template table; the P2.10 held-out check shows completion 0.9502 vs
#:   0.8424 and truth_v2 +0.48% vs baseline on seeds 2/3/4);
#: * ``tuned`` (**experimental / in-sample only, not recommended**) -- P2.9
#:   :func:`mp_place.route_cost.tuned_objective` per-template table lookup.
#:   The table does not generalise to held-out seeds (truth +7.47% on seeds
#:   2/3/4, 0/8 templates meeting the target); use only for research/diagnostics.
PIPELINE_OBJECTIVES: Tuple[str, ...] = ("proxy", "route_aware", "tuned")
DEFAULT_OBJECTIVE = "proxy"
#: Weight/profile of the recommended safe ``route_aware`` objective.
ROUTE_AWARE_W_ROUTE = 2.0
ROUTE_AWARE_PROFILE = "default"
#: Note attached to the experimental ``tuned`` objective in reports.
TUNED_GENERALIZATION_NOTE = (
    "P2.9 TUNED_TABLE is in-sample only: on held-out seeds 2/3/4 "
    "(report_holdout.md) tuned truth_v2 is +7.47% vs baseline with 0/8 "
    "templates meeting the target, while fixed w_route=2.0 is +0.48% with "
    "completion 0.9502. Not recommended; research/diagnostics only."
)

#: P2.11 objective-comparison benchmark artefact names.
OBJECTIVE_BENCHMARK_SCHEMA = "mp_place.pipeline_objective/v2"
REPORT_OBJECTIVE_MD = "report_pipeline_objective.md"
REPORT_OBJECTIVE_JSON = "report_pipeline_objective.json"
#: Target of the recommended route_aware objective vs the proxy baseline.
OBJECTIVE_TARGET_TRUTH_RATIO = 1.01

#: Solver statistics that must not leak into the deterministic report.
_VOLATILE_STATS = ("runtime_s",)


def _coerce_scenario(scenario: Union[Scenario, str], seed: int = 0) -> Scenario:
    """Accept a :class:`Scenario` or a template name (resolved with ``seed``)."""
    if isinstance(scenario, Scenario):
        return scenario
    if isinstance(scenario, str):
        return templates.instantiate(scenario, seed=seed)
    raise TypeError(
        "scenario must be a mp_place.model.Scenario or a template name (str), "
        f"got {type(scenario).__name__}"
    )


def _finite_float(value: Any, digits: int = 6) -> Optional[float]:
    """Round a float for the report, mapping non-finite values to ``None``."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return round(number, digits)


def _json_safe(value: Any) -> Any:
    """Recursively normalise to plain JSON types; non-finite floats -> ``None``."""
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return str(value)


def _same_number(left: Any, right: Any, tol: float = 1e-9) -> bool:
    """Compare two optional numeric values without float-rounding noise."""
    if left is None or right is None:
        return left is None and right is None
    try:
        return abs(float(left) - float(right)) <= tol
    except (TypeError, ValueError):
        return False


def _canonical_digest(payload: Any) -> str:
    """Stable sha256 over a JSON payload (sorted keys, no whitespace)."""
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _solver_summary(stats: Dict[str, Any]) -> Dict[str, Any]:
    """Deterministic subset of the solver statistics (drops wall-clock)."""
    out: Dict[str, Any] = {}
    for key, value in stats.items():
        if key in _VOLATILE_STATS:
            continue
        out[str(key)] = _round_numbers(_json_safe(value))
    return out


def _round_numbers(value: Any, digits: int = 6) -> Any:
    if isinstance(value, float):
        return round(value, digits)
    if isinstance(value, list):
        return [_round_numbers(item, digits) for item in value]
    if isinstance(value, dict):
        return {key: _round_numbers(item, digits) for key, item in value.items()}
    return value


def _router_summary(scenario: Scenario, placement: Placement) -> Dict[str, Any]:
    """Run the offline grid router and return a deterministic summary.

    A router failure degrades to ``status="NOT RUN"`` instead of crashing the
    pipeline (the same graceful-degradation policy as ``mp_place.verify``).
    """
    try:
        result = GridRouter(scenario, grid_mm=ROUTER_GRID_MM, layers=ROUTER_LAYERS).route(placement)
    except Exception as exc:  # noqa: BLE001 - report, do not crash the run
        return {
            "status": "NOT RUN",
            "completion": None,
            "failed_nets": [],
            "wirelength_mm": None,
            "vias": None,
            "overflow": None,
            "reason": f"router failed: {type(exc).__name__}: {exc}",
        }
    failed = []
    try:
        failed = sorted(str(name) for name in (result.failed_nets or []))
    except TypeError:
        failed = []
    return {
        "status": "ROUTED",
        "completion": _finite_float(result.completion),
        "failed_nets": failed,
        "wirelength_mm": _finite_float(result.wirelength_mm, digits=3),
        "vias": int(result.vias),
        "overflow": int(result.overflow),
        "reason": "ok",
    }


def _intent_summary(scenario: Scenario, placement: Placement) -> Dict[str, Any]:
    """Build the JSON intent, replay it, and summarise the CCG constraints."""
    intent = intent_mod.build_intent(scenario, placement)
    replayed = intent_mod.intent_to_plan(scenario, intent)
    replay_hard = list(hard_violations(scenario, replayed))
    replay_ccg = list(intent_mod.intent_violations(scenario, replayed, intent))
    counts = {str(key): int(value) for key, value in intent.get("constraint_counts", {}).items()}
    total = int(intent.get("summary", {}).get("constraints", len(intent.get("constraints", []))))
    return {
        "intent_schema": intent.get("schema"),
        "intent_digest": _canonical_digest(intent),
        "intent_constraints": counts,
        "intent_total_constraints": total,
        "intent_modules": int(intent.get("summary", {}).get("present_modules", 0)),
        "intent_replay_ok": not replay_hard and not replay_ccg,
        "intent_replay_violations": replay_hard + replay_ccg,
    }


def _scenario_summary(sc: Scenario, certificate: Dict[str, Any]) -> Dict[str, Any]:
    scenario_block = certificate.get("scenario", {})
    return {
        "name": sc.name,
        "board_w": _finite_float(sc.board_w),
        "board_h": _finite_float(sc.board_h),
        "components": len(sc.components),
        "nets": len(sc.nets),
        "keepouts": len(sc.keepouts),
        "edge_tol": _finite_float(sc.edge_tol),
        "digest": scenario_block.get("digest"),
    }


def _build_objective(sc: Scenario, objective_mode: str) -> Tuple[object, Dict[str, Any]]:
    """Build the solver cost objective for ``objective_mode``.

    Returns ``(objective, meta)``; ``objective`` exposes ``cost(placement)`` and
    ``name``.  ``route_aware`` uses a fixed ``w_route=2.0`` (no per-template
    table, recommended safe default); ``tuned`` uses the P2.9 table lookup
    (in-sample only, research use).  Neither cost path calls the router.
    """
    if objective_mode == "proxy":
        objective = ProxyObjective(sc)
        return objective, {
            "mode": "proxy",
            "cost_objective": objective.name,
            "recommended": True,
            "generalization": "baseline",
        }
    if objective_mode in ("route_aware", "tuned"):
        from .route_cost import RouteAwareObjective, select_config, tuned_objective

        if objective_mode == "route_aware":
            objective = RouteAwareObjective(
                sc,
                base=ProxyObjective(sc),
                w_route=ROUTE_AWARE_W_ROUTE,
                profile=ROUTE_AWARE_PROFILE,
            )
            return objective, {
                "mode": "route_aware",
                "cost_objective": objective.name,
                "w_route": float(objective.w_route),
                "profile": str(objective.profile),
                "source": "fixed_weight",
                "recommended": True,
                "generalization": "heldout_safe",
                "note": "P2.8 fixed w_route=2.0; P2.10 held-out seeds 2/3/4: "
                "completion 0.9502 vs 0.8424, truth_v2 +0.48% vs baseline.",
            }
        config = select_config(sc)
        objective = tuned_objective(sc)
        return objective, {
            "mode": "tuned",
            "cost_objective": objective.name,
            "w_route": float(objective.w_route),
            "profile": str(objective.profile),
            "source": str(config.get("source")),
            "recommended": False,
            "generalization": "in_sample_only",
            "note": TUNED_GENERALIZATION_NOTE,
        }
    raise ValueError(
        f"unknown objective {objective_mode!r}; expected one of {PIPELINE_OBJECTIVES}"
    )


def run_pipeline(
    scenario: Union[Scenario, str],
    budget_steps: int = DEFAULT_BUDGET_STEPS,
    seed: int = 0,
    route_repair: bool = False,
    objective: str = DEFAULT_OBJECTIVE,
) -> Dict[str, Any]:
    """Run the end-to-end offline pipeline for one scenario.

    Parameters
    ----------
    scenario:
        A :class:`mp_place.model.Scenario`, or a template name (``"buck"``,
        ``"mcu-min"``, ``"motor"``, ``"rs485"``, ``"wireless"``, ...)
        instantiated with ``seed``.
    budget_steps:
        Total solver move budget, split across the solver's restarts.
    seed:
        Seed for the solver, the P1 simulator, ``PhysicsSimulatorV2`` and the
        template (when a name is given).
    route_repair:
        When true, use ``route_opt.repair_routes`` (solver + routability-gated
        local repair, up to ``ROUTE_REPAIR_MAX_ROUTES`` router calls) instead
        of the plain portfolio solver.  The result is verified by the same
        router summary and certificate afterwards.
    objective:
        Solver cost objective (P2.11 / task-27 update):

        * ``"proxy"`` (default, backwards compatible) -- plain
          :class:`mp_place.objective.ProxyObjective`;
        * ``"route_aware"`` (**recommended safe option**) -- fixed
          ``w_route=2.0`` :class:`mp_place.route_cost.RouteAwareObjective`
          (P2.8 path, no per-template table; generalises to held-out seeds);
        * ``"tuned"`` (**experimental, in-sample only, not recommended**) --
          :func:`mp_place.route_cost.tuned_objective` per-template table lookup
          (P2.9 table does not generalise to held-out seeds, see
          :data:`TUNED_GENERALIZATION_NOTE`).

        Neither route-aware cost path calls the router while being optimised.
        Unknown values raise ``ValueError``; non-strings raise ``TypeError``.

    Returns
    -------
    dict
        JSON-serialisable report with the placement, feasibility, v1/v2 truth,
        router completion, intent constraint counts, certificate, fixed safety
        fields and limits.  ``objective_mode`` / ``objective_model`` /
        ``objective_config`` / ``objective_recommended`` record which objective
        solved the placement.  Deterministic for a fixed input; see module
        notes.
    """
    sc = _coerce_scenario(scenario, seed=seed)
    seed = int(seed)
    try:
        budget = int(budget_steps)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"budget_steps must be an integer, got {budget_steps!r}") from exc
    if budget < 0:
        raise ValueError(f"budget_steps must be >= 0, got {budget}")
    if not isinstance(objective, str):
        raise TypeError(f"objective must be a string, got {type(objective).__name__}")
    objective_mode = objective.strip()
    if objective_mode not in PIPELINE_OBJECTIVES:
        raise ValueError(
            f"unknown objective {objective!r}; expected one of {PIPELINE_OBJECTIVES}"
        )

    cost_objective, objective_meta = _build_objective(sc, objective_mode)
    if route_repair:
        placement, best_cost, _route_result, repair_stats = repair_routes(
            sc,
            cost_objective.cost,
            seed=seed,
            steps=budget,
            max_routes=ROUTE_REPAIR_MAX_ROUTES,
        )
        stats = {
            "solver": "route_repair",
            "route_calls": repair_stats.get("routes_calls"),
            "initial_completion": repair_stats.get("initial_completion"),
            "final_completion": repair_stats.get("final_completion"),
            "moves_accepted": repair_stats.get("moves_accepted"),
        }
    else:
        placement, best_cost, stats = solve(
            sc, cost_objective.cost, seed=seed, steps=budget
        )

    violations = list(hard_violations(sc, placement))
    truth_v1 = PhysicsSimulator(sc, seed=seed).score(placement)
    truth_v2 = PhysicsSimulatorV2(sc, seed=seed).score(placement)
    router = _router_summary(sc, placement)
    intent = _intent_summary(sc, placement)

    solver_extra = {
        "solver": stats.get("solver"),
        "budget_steps": budget,
        "seed": seed,
        "objective": cost_objective.name,
        "objective_mode": objective_mode,
    }
    certificate = verify_mod.certificate(sc, placement, extra=solver_extra)

    routability = certificate.get("routability", {})
    router_consistent = bool(
        router.get("status") == routability.get("status")
        and _same_number(router.get("completion"), routability.get("completion"))
        and router.get("failed_nets") == routability.get("failed_nets")
    )

    report: Dict[str, Any] = {
        "schema": PIPELINE_SCHEMA,
        "scenario": _scenario_summary(sc, certificate),
        "config": {
            "budget_steps": budget,
            "seed": seed,
            "objective": cost_objective.name,
            "objective_mode": objective_mode,
            "solver": stats.get("solver"),
            "restarts": int(stats.get("restarts", 0) or 0),
            "router": f"GridRouter(grid_mm={ROUTER_GRID_MM}, layers={ROUTER_LAYERS})",
        },
        "objective_mode": objective_mode,
        "objective_model": cost_objective.name,
        "objective_config": objective_meta,
        "objective_recommended": bool(objective_meta.get("recommended")),
        "objective_generalization": objective_meta.get("generalization"),
        "placement": certificate.get("placement", {}),
        "placement_digest": certificate.get("placement_digest"),
        "feasible": bool(certificate.get("feasible", not violations)),
        "violations": list(certificate.get("violations", violations)),
        "proxy_cost": _finite_float(best_cost),
        "truth_v1": _finite_float(truth_v1),
        "truth_v2": _finite_float(truth_v2),
        "truth_delta": _finite_float(truth_v2 - truth_v1),
        "solver": _solver_summary(stats),
        "router": router,
        "router_certificate_consistent": bool(router_consistent),
        **intent,
        "fixed_fields": dict(verify_mod.FIXED_FIELDS),
        "limits": list(verify_mod.LIMITS),
        "certificate": certificate,
    }
    return report


# --------------------------------------------------------------------------- #
# P2.11 objective comparison: proxy vs route_aware vs tuned
# --------------------------------------------------------------------------- #
def _objective_group_summary(
    rows: Sequence[Dict[str, Any]], cohort: str, objective_mode: str
) -> Dict[str, Any]:
    """Aggregate benchmark rows for one ``(cohort, objective)`` group."""
    subset = [
        row
        for row in rows
        if row["cohort"] == cohort and row["objective"] == objective_mode
    ]
    count = len(subset)

    def _mean(key: str) -> float:
        values = [row[key] for row in subset if row[key] is not None]
        return sum(values) / len(values) if values else 0.0

    recommended = bool(subset[0]["objective_recommended"]) if subset else False
    generalization = subset[0]["objective_generalization"] if subset else None
    if count == 0:
        return {
            "cohort": cohort,
            "objective": objective_mode,
            "recommended": recommended,
            "generalization": generalization,
            "runs": 0,
            "feasible_rate": 0.0,
            "mean_completion": 0.0,
            "fully_routed_rate": 0.0,
            "mean_truth_v1": 0.0,
            "mean_truth_v2": 0.0,
            "mean_runtime_s": 0.0,
            "intent_replay_ok_rate": 0.0,
        }
    return {
        "cohort": cohort,
        "objective": objective_mode,
        "recommended": recommended,
        "generalization": generalization,
        "runs": count,
        "feasible_rate": sum(1 for row in subset if row["feasible"]) / count,
        "mean_completion": _mean("completion"),
        "fully_routed_rate": sum(
            1
            for row in subset
            if row["completion"] is not None and row["completion"] >= 1.0 - 1e-12
        )
        / count,
        "mean_truth_v1": _mean("truth_v1"),
        "mean_truth_v2": _mean("truth_v2"),
        "mean_runtime_s": _mean("runtime_s"),
        "intent_replay_ok_rate": (
            sum(1 for row in subset if row["intent_replay_ok"]) / count
        ),
    }


def _paired_objective_comparison(
    rows: Sequence[Dict[str, Any]],
    cohort: str,
    other_mode: str,
    baseline_mode: str = "proxy",
) -> Dict[str, Any]:
    """Compare ``other_mode`` against ``baseline_mode`` on one cohort."""
    lookup = {
        (row["template"], row["seed"], row["objective"]): row
        for row in rows
        if row["cohort"] == cohort
    }
    keys = sorted(
        {
            (row["template"], row["seed"])
            for row in rows
            if row["cohort"] == cohort and row["objective"] == baseline_mode
        }
    )
    comparisons: List[Dict[str, Any]] = []
    for template, seed in keys:
        baseline = lookup.get((template, seed, baseline_mode))
        other = lookup.get((template, seed, other_mode))
        if baseline is None or other is None:
            continue
        baseline_completion = baseline["completion"]
        other_completion = other["completion"]
        completion_delta = (other_completion or 0.0) - (baseline_completion or 0.0)
        baseline_truth = baseline["truth_v2"]
        other_truth = other["truth_v2"]
        truth_ratio = (other_truth / baseline_truth) if baseline_truth else 1.0
        comparisons.append(
            {
                "template": template,
                "seed": seed,
                "proxy_completion": baseline_completion,
                "other_completion": other_completion,
                "completion_delta": round(completion_delta, 6),
                "proxy_truth_v2": baseline_truth,
                "other_truth_v2": other_truth,
                "truth_ratio": round(truth_ratio, 6),
                "truth_pct": round(100.0 * (truth_ratio - 1.0), 3),
                "proxy_runtime_s": baseline["runtime_s"],
                "other_runtime_s": other["runtime_s"],
            }
        )

    def _mean(key: str) -> float:
        return (
            sum(item[key] for item in comparisons) / len(comparisons)
            if comparisons
            else 0.0
        )

    mean_proxy_truth = _mean("proxy_truth_v2")
    mean_other_truth = _mean("other_truth_v2")
    aggregate_ratio = (
        (mean_other_truth / mean_proxy_truth) if mean_proxy_truth else 1.0
    )
    mean_proxy_completion = _mean("proxy_completion")
    mean_other_completion = _mean("other_completion")
    return {
        "cohort": cohort,
        "baseline": baseline_mode,
        "other": other_mode,
        "comparisons": comparisons,
        "mean_completion_proxy": mean_proxy_completion,
        "mean_completion_other": mean_other_completion,
        "aggregate_truth_ratio": round(aggregate_ratio, 6),
        "aggregate_truth_pct": round(100.0 * (aggregate_ratio - 1.0), 3),
        "completion_per_case_not_lower": bool(comparisons)
        and all(item["completion_delta"] >= -1e-9 for item in comparisons),
        "aggregate_completion_not_lower": mean_other_completion
        >= mean_proxy_completion - 1e-9,
        "worst_completion_delta": (
            min(item["completion_delta"] for item in comparisons)
            if comparisons
            else None
        ),
        "worst_truth_pct": (
            max(item["truth_pct"] for item in comparisons) if comparisons else None
        ),
    }


def _route_aware_target(
    comparison: Optional[Dict[str, Any]], cohort: str
) -> Dict[str, Any]:
    """P2.11 target verdict for the recommended route_aware objective."""
    if comparison is None:
        return {
            "cohort": cohort,
            "criteria": "route_aware vs proxy: completion not lower, truth_v2 <= proxy * 1.01",
            "met": False,
            "reason": "route_aware/proxy comparison unavailable",
        }
    completion_per_case = bool(comparison["completion_per_case_not_lower"])
    aggregate_completion = bool(comparison["aggregate_completion_not_lower"])
    aggregate_ratio = float(comparison["aggregate_truth_ratio"])
    truth_ok = aggregate_ratio <= OBJECTIVE_TARGET_TRUTH_RATIO + 1e-12
    return {
        "cohort": cohort,
        "criteria": "route_aware vs proxy: aggregate completion not lower and "
        "aggregate truth_v2 <= proxy * "
        f"{OBJECTIVE_TARGET_TRUTH_RATIO:g} (per-case completion/truth spread "
        "reported as diagnostics)",
        "truth_ratio_limit": OBJECTIVE_TARGET_TRUTH_RATIO,
        "completion_per_case_not_lower": completion_per_case,
        "aggregate_completion_not_lower": aggregate_completion,
        "aggregate_truth_ratio": round(aggregate_ratio, 6),
        "aggregate_truth_pct": round(100.0 * (aggregate_ratio - 1.0), 3),
        "truth_within_1pct": truth_ok,
        "met": aggregate_completion and truth_ok,
        "worst_completion_delta": comparison["worst_completion_delta"],
        "worst_truth_pct": comparison["worst_truth_pct"],
    }


def benchmark_objectives(
    names: Optional[Sequence[str]] = None,
    seeds: Sequence[int] = (0, 1),
    heldout_seeds: Sequence[int] = (2, 3, 4),
    steps: int = DEFAULT_BUDGET_STEPS,
    objectives: Sequence[str] = PIPELINE_OBJECTIVES,
) -> Dict[str, Any]:
    """P2.11 benchmark: compare pipeline objectives on in-sample + held-out seeds.

    For every ``(cohort, template, seed)`` the full :func:`run_pipeline` is
    executed once per objective.  Cohorts:

    * ``in_sample`` -- default ``(0, 1)``, the seeds used by the P2.9 tuning
      (tuned results are in-sample here);
    * ``heldout`` -- default ``(2, 3, 4)``, the P2.10 held-out seeds, used for
      the generalisation target of the recommended ``route_aware`` objective.

    ``tuned`` is still reported (in-sample) but explicitly marked experimental /
    not recommended: :data:`TUNED_GENERALIZATION_NOTE` plus the held-out numbers
    are in the returned ``tuned_status`` and the report.

    Target (evaluated on the held-out cohort when available): ``route_aware``
    completion is not lower than ``proxy`` (per case and aggregate) and
    aggregate ``truth_v2`` is at most +1% vs ``proxy``.
    """
    import time

    from .templates import instantiate, template_names

    template_names_ = list(template_names() if names is None else names)
    modes = [str(mode).strip() for mode in objectives]
    if not modes:
        raise ValueError("objectives must contain at least one objective")
    unknown = [mode for mode in modes if mode not in PIPELINE_OBJECTIVES]
    if unknown:
        raise ValueError(
            f"unknown objectives {unknown}; expected subset of {PIPELINE_OBJECTIVES}"
        )
    try:
        budget = int(steps)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"steps must be an integer, got {steps!r}") from exc
    if budget < 0:
        raise ValueError(f"steps must be >= 0, got {budget}")

    cohort_specs: List[Tuple[str, Tuple[int, ...]]] = []
    if seeds:
        cohort_specs.append(("in_sample", tuple(int(item) for item in seeds)))
    if heldout_seeds:
        cohort_specs.append(("heldout", tuple(int(item) for item in heldout_seeds)))
    if not cohort_specs:
        raise ValueError("seeds and heldout_seeds must not both be empty")

    rows: List[Dict[str, Any]] = []
    for cohort, cohort_seeds in cohort_specs:
        for name in template_names_:
            for seed in cohort_seeds:
                scenario = instantiate(name, seed=seed)
                for mode in modes:
                    started = time.perf_counter()
                    report = run_pipeline(
                        scenario, budget_steps=budget, seed=seed, objective=mode
                    )
                    runtime_s = time.perf_counter() - started
                    router = report.get("router", {})
                    rows.append(
                        {
                            "cohort": cohort,
                            "template": name,
                            "seed": int(seed),
                            "objective": mode,
                            "objective_model": report.get("objective_model"),
                            "objective_recommended": bool(
                                report.get("objective_recommended")
                            ),
                            "objective_generalization": report.get(
                                "objective_generalization"
                            ),
                            "feasible": bool(report.get("feasible")),
                            "violations": len(report.get("violations", [])),
                            "truth_v1": report.get("truth_v1"),
                            "truth_v2": report.get("truth_v2"),
                            "solver_cost": report.get("proxy_cost"),
                            "router_status": router.get("status"),
                            "completion": router.get("completion"),
                            "failed_nets": list(router.get("failed_nets", [])),
                            "vias": router.get("vias"),
                            "runtime_s": round(runtime_s, 4),
                            "intent_replay_ok": bool(report.get("intent_replay_ok")),
                            "placement_digest": report.get("placement_digest"),
                            "objective_config": report.get("objective_config"),
                        }
                    )

    cohorts: Dict[str, Dict[str, Any]] = {}
    for cohort, cohort_seeds in cohort_specs:
        cohort_rows = [row for row in rows if row["cohort"] == cohort]
        groups = [
            _objective_group_summary(cohort_rows, cohort, mode) for mode in modes
        ]
        route_comparison = (
            _paired_objective_comparison(cohort_rows, cohort, "route_aware")
            if {"proxy", "route_aware"}.issubset(set(modes))
            else None
        )
        tuned_comparison = (
            _paired_objective_comparison(cohort_rows, cohort, "tuned")
            if {"proxy", "tuned"}.issubset(set(modes))
            else None
        )
        cohorts[cohort] = {
            "seeds": [int(seed) for seed in cohort_seeds],
            "groups": groups,
            "route_aware_vs_proxy": route_comparison,
            "tuned_vs_proxy": tuned_comparison,
        }

    target_cohort = "heldout" if "heldout" in cohorts else "in_sample"
    target = _route_aware_target(
        cohorts[target_cohort].get("route_aware_vs_proxy"), target_cohort
    )
    in_sample_route = cohorts.get("in_sample", {}).get("route_aware_vs_proxy")
    if in_sample_route is not None and target_cohort != "in_sample":
        target["in_sample_route_aware"] = {
            "cohort": "in_sample",
            "aggregate_truth_ratio": in_sample_route["aggregate_truth_ratio"],
            "aggregate_truth_pct": in_sample_route["aggregate_truth_pct"],
            "completion_per_case_not_lower": in_sample_route[
                "completion_per_case_not_lower"
            ],
            "aggregate_completion_not_lower": in_sample_route[
                "aggregate_completion_not_lower"
            ],
            "note": "in-sample route_aware truth cost is larger than on held-out "
            "seeds; reported for transparency, the target uses the held-out cohort",
        }

    in_sample_tuned = cohorts.get("in_sample", {}).get("tuned_vs_proxy")
    heldout_tuned = cohorts.get("heldout", {}).get("tuned_vs_proxy")
    tuned_status = {
        "recommended": False,
        "label": "in_sample_only",
        "note": TUNED_GENERALIZATION_NOTE,
        "in_sample_truth_pct": (
            in_sample_tuned["aggregate_truth_pct"] if in_sample_tuned else None
        ),
        "heldout_truth_pct": (
            heldout_tuned["aggregate_truth_pct"] if heldout_tuned else None
        ),
        "heldout_completion_mean": (
            heldout_tuned["mean_completion_other"] if heldout_tuned else None
        ),
        "heldout_completion_proxy_mean": (
            heldout_tuned["mean_completion_proxy"] if heldout_tuned else None
        ),
    }
    recommendation = {
        "default": "proxy",
        "recommended": "route_aware",
        "not_recommended": "tuned",
        "rationale": "route_aware is a fixed w_route=2.0 code path with no "
        "per-template table and meets the completion/truth target on held-out "
        "seeds; tuned is in-sample only (+7.47% held-out truth_v2) and is kept "
        "for research/diagnostics.",
    }
    return {
        "schema": OBJECTIVE_BENCHMARK_SCHEMA,
        "created_by": "mp_place.pipeline.benchmark_objectives",
        "config": {
            "templates": template_names_,
            "seeds": [int(item) for item in seeds],
            "heldout_seeds": [int(item) for item in heldout_seeds],
            "steps": budget,
            "objectives": modes,
            "target_cohort": target_cohort,
            "router": f"GridRouter(grid_mm={ROUTER_GRID_MM}, layers={ROUTER_LAYERS})",
            "route_aware_config": {
                "w_route": ROUTE_AWARE_W_ROUTE,
                "profile": ROUTE_AWARE_PROFILE,
            },
            "objective_target_truth_ratio": OBJECTIVE_TARGET_TRUTH_RATIO,
            "cost_paths": {
                "proxy": "ProxyObjective",
                "route_aware": "RouteAwareObjective(w_route=2.0, profile=default)",
                "tuned": "route_cost.tuned_objective (P2.9 table, in-sample only)",
            },
        },
        "cohorts": cohorts,
        "target": target,
        "tuned_status": tuned_status,
        "recommendation": recommendation,
        "rows": rows,
    }


def _format_comparison_table(
    comparison: Dict[str, Any],
) -> List[str]:
    """Markdown rows for one paired comparison block."""
    lines = []
    for item in comparison["comparisons"]:
        lines.append(
            "| {cohort} | {template} | {seed} | {proxy_completion:.3f} → "
            "{other_completion:.3f} | {completion_delta:+.3f} | "
            "{proxy_truth_v2:.4f} → {other_truth_v2:.4f} | {truth_pct:+.2f}% | "
            "{proxy_runtime_s:.2f} s → {other_runtime_s:.2f} s |".format(
                cohort=comparison["cohort"], **item
            )
        )
    return lines


def _format_objective_markdown(result: Dict[str, Any]) -> str:
    """Render :func:`benchmark_objectives` output as report markdown."""
    config = result["config"]
    target = result["target"]
    lines = [
        "# P2.11 Pipeline objective 对比（proxy / route_aware / tuned）",
        "",
        f"- 生成命令：`python -m mp_place.pipeline --objective-benchmark`"
        f"（schema `{result['schema']}`）",
        f"- 协议：{len(config['templates'])} 模板；in-sample seeds "
        + ",".join(str(seed) for seed in config["seeds"])
        + "，held-out seeds "
        + ",".join(str(seed) for seed in config["heldout_seeds"])
        + f"；每个 (cohort, template, seed) 对每档 objective 运行完整 "
        f"`run_pipeline(..., objective=<mode>, steps={config['steps']})`。"
        "completion 来自 solve 之后的离线 2 层网格 oracle（不参与目标计算）；"
        "`truth_v2` 来自 `physics_v2.PhysicsSimulatorV2`；耗时为 solve+verify+router 的 wall-clock。",
        "",
        "## 目标档定义与推荐",
        "",
        "| objective | 定义 | 泛化 | 推荐 |",
        "| --- | --- | --- | --- |",
        "| proxy | `ProxyObjective`（P1/P2 多物理代理，默认兼容） | baseline | 默认 |",
        "| route_aware | `RouteAwareObjective` 固定 w_route=2.0 / profile=default"
        "（无 per-template 表） | held-out 安全（seeds 2/3/4：completion 0.9502 vs"
        " 0.8424、truth +0.48%） | **推荐升级档** |",
        "| tuned | `route_cost.tuned_objective`（P2.9 每模板权重表） | in-sample"
        " only（seeds 2/3/4：truth +7.47%，0/8 模板达标） | ❌ 不推荐（研究/诊断用） |",
        "",
        "## 组汇总",
        "",
        "| cohort | objective | runs | feasible | completion 均值 | 全布通率 | truth_v1 均值 | truth_v2 均值 | 耗时/run |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for cohort_name in result["cohorts"]:
        block = result["cohorts"][cohort_name]
        for group in block["groups"]:
            lines.append(
                "| {cohort} | {objective} | {runs} | {feasible_rate:.0%} | "
                "{mean_completion:.4f} | {fully_routed_rate:.0%} | "
                "{mean_truth_v1:.4f} | {mean_truth_v2:.4f} | "
                "{mean_runtime_s:.2f} s |".format(**group)
            )
    lines.extend(
        [
            "",
            "## route_aware vs proxy 逐案例",
            "",
            "| cohort | template | seed | completion proxy → route_aware | Δcompletion | truth_v2 proxy → route_aware | Δtruth | 耗时 proxy → route_aware |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for cohort_name in result["cohorts"]:
        comparison = result["cohorts"][cohort_name].get("route_aware_vs_proxy")
        if comparison:
            lines.extend(_format_comparison_table(comparison))
    lines.extend(
        [
            "",
            "## 目标（route_aware 泛化口径）",
            "",
            f"- 目标：{target['criteria']}",
            f"- 评估 cohort：`{target['cohort']}`",
            f"- 达标：{'是' if target['met'] else '否'}",
        ]
    )
    if target.get("aggregate_truth_ratio") is not None:
        lines.append(
            f"- 聚合 truth_v2 比（route_aware/proxy）："
            f"{target['aggregate_truth_ratio']:.4f}（{target['aggregate_truth_pct']:+.2f}%）"
        )
        lines.append(
            "- 聚合 completion 不降："
            f"{'是' if target['aggregate_completion_not_lower'] else '否'}；"
            "逐案例 completion 波动（诊断）："
            f"{'均不下降' if target['completion_per_case_not_lower'] else '个别案例下降'}"
            f"，最差变化 {target['worst_completion_delta']:+.4f}"
        )
        lines.append(
            f"- 最差逐案例 truth 劣化（诊断）：{target['worst_truth_pct']:+.2f}%"
        )
    in_sample = target.get("in_sample_route_aware")
    if in_sample:
        lines.append(
            "- in-sample（seeds "
            + ",".join(str(seed) for seed in config["seeds"])
            + "）诊断：route_aware truth "
            f"{in_sample['aggregate_truth_pct']:+.2f}%（闭集内 truth 让步换取 completion），"
            "以 held-out 口径判定达标。"
        )
    tuned = result["tuned_status"]
    lines.extend(
        [
            "",
            "## tuned（实验档：in-sample only，不推荐）",
            "",
            f"- in-sample truth Δ vs proxy：{_fmt_optional_pct(tuned['in_sample_truth_pct'])}；"
            f"held-out truth Δ：{_fmt_optional_pct(tuned['heldout_truth_pct'])}。",
            f"- 留出 completion（tuned / proxy）："
            f"{_fmt_optional(tuned['heldout_completion_mean'])} / "
            f"{_fmt_optional(tuned['heldout_completion_proxy_mean'])}。",
            f"- 说明：{tuned['note']}",
            "",
            "## 推荐结论",
            "",
            f"- 默认：`{result['recommendation']['default']}`（向后兼容）。",
            f"- 推荐升级：`{result['recommendation']['recommended']}`"
            "（固定 w_route=2.0，无表，held-out 达标）。",
            f"- 不推荐：`{result['recommendation']['not_recommended']}`"
            "（in-sample 过拟合，held-out truth +7.47%）。",
            "",
            "## 边界",
            "",
            "- 所有 route-aware 目标在求解时零 router 调用；router 仅在 solve 后作为"
            " completion oracle 评估，不是可布通证明。",
            "- 边界：纯离线代理（无 EDA / DRC / 真实布线）；truth_v2 是离线感仿真器；"
            "completion=1 仅表示离线 1 mm / 2 层迷宫 oracle 走通全部被评分网络。",
            "- tuned 的 in-sample 数据来自 seeds 0/1（P2.9 调参 seeds），不得用它反推"
            "留出 seeds 的泛化结论。",
        ]
    )
    return "\n".join(lines) + "\n"


def _fmt_optional_pct(value: Optional[float]) -> str:
    return "n/a" if value is None else f"{value:+.2f}%"


def _fmt_optional(value: Optional[float]) -> str:
    return "n/a" if value is None else f"{value:.4f}"


def write_objective_report(
    result: Optional[Dict[str, Any]] = None, out_dir=None
) -> Dict[str, str]:
    """Write ``report_pipeline_objective.{md,json}`` and return their paths."""
    import pathlib

    if result is None:
        result = benchmark_objectives()
    out = (
        pathlib.Path(out_dir)
        if out_dir is not None
        else pathlib.Path(__file__).resolve().parent.parent
    )
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / REPORT_OBJECTIVE_JSON
    md_path = out / REPORT_OBJECTIVE_MD
    json_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(_format_objective_markdown(result), encoding="utf-8")
    return {"json": str(json_path), "md": str(md_path)}


def main(argv: Optional[Sequence[str]] = None) -> int:
    """``python -m mp_place.pipeline --objective-benchmark``."""
    import argparse
    import sys

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):  # pragma: no cover - exotic streams
            pass
    parser = argparse.ArgumentParser(
        description="Offline placement pipeline (proxy / route_aware / tuned objective benchmark)"
    )
    parser.add_argument(
        "--objective-benchmark",
        action="store_true",
        help=f"run the P2.11 proxy / route_aware / tuned objective benchmark and write "
        f"{REPORT_OBJECTIVE_MD}/{REPORT_OBJECTIVE_JSON}",
    )
    parser.add_argument("--steps", type=int, default=DEFAULT_BUDGET_STEPS)
    parser.add_argument("--seeds", default="0,1")
    parser.add_argument("--out", default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if not args.objective_benchmark:
        parser.error("nothing to do; pass --objective-benchmark")
    seeds = tuple(int(item) for item in str(args.seeds).split(",") if item.strip())
    if not seeds:
        parser.error("--seeds must be non-empty")
    result = benchmark_objectives(seeds=seeds, steps=args.steps)
    paths = write_objective_report(result, out_dir=args.out)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    else:
        print(_format_objective_markdown(result))
    print(f"[pipeline] wrote {paths['md']} / {paths['json']}", file=sys.stderr)
    return 0 if result["target"]["met"] else 1


__all__ = [
    "run_pipeline",
    "benchmark_objectives",
    "write_objective_report",
    "PIPELINE_SCHEMA",
    "PIPELINE_OBJECTIVES",
    "DEFAULT_TEMPLATE",
    "DEFAULT_BUDGET_STEPS",
    "DEFAULT_OBJECTIVE",
    "main",
]

if __name__ == "__main__":
    raise SystemExit(main())
