"""P4-G: end-to-end offline placement pipeline (solve -> verify -> intent -> certificate).

One call runs the whole offline chain for a template/scenario and returns a
plain JSON-serialisable report:

    solver_v2.solve(cost=ProxyObjective.cost)   # multi-physics proxy
        -> hard_violations                       # P1 hard constraints
        -> truth_v1 = objective.PhysicsSimulator # P1 hidden pseudo-physics
        -> truth_v2 = physics_v2.PhysicsSimulatorV2
        -> router.GridRouter.route               # offline routability oracle
        -> intent.build_intent / intent_to_plan  # JSON intent + replay check
        -> verify.certificate                    # deterministic certificate

Safety contract
---------------
Everything here is **offline**.  The pipeline never applies a placement, never
runs DRC, never calls EDA and never touches the network.  The report therefore
hard-codes ``fixed_fields = {"routing_verified": false, "drc": "NOT RUN",
"eda_calls": 0}``; router completion is a 2-layer grid-maze oracle, not a
routability proof.  See ``mp_place.verify.LIMITS`` for the full boundary list.

Determinism
-----------
For the same ``(scenario, budget_steps, seed)`` two runs produce byte-identical
JSON (``json.dumps(report, sort_keys=True)``): wall-clock fields from the
solver/router are stripped, and the certificate already excludes the router
runtime.  ``stats["runtime_s"]`` is the only discarded value.

Usage
-----
>>> from mp_place.templates import instantiate
>>> from mp_place.pipeline import run_pipeline
>>> report = run_pipeline(instantiate("buck", seed=0), budget_steps=800, seed=0)
>>> report["feasible"], report["truth_v2"]
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Dict, Optional, Union

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


def run_pipeline(
    scenario: Union[Scenario, str],
    budget_steps: int = DEFAULT_BUDGET_STEPS,
    seed: int = 0,
    route_repair: bool = False,
) -> Dict[str, Any]:
    """Run the end-to-end offline pipeline for one scenario.

    Parameters
    ----------
    scenario:
        A :class:`mp_place.model.Scenario`, or a template name (``"buck"``,
        ``"mcu-min"``, ``"motor"``, ``"rs485"``, ``"wireless"``) instantiated
        with ``seed``.
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

    Returns
    -------
    dict
        JSON-serialisable report with the placement, feasibility, v1/v2 truth,
        router completion, intent constraint counts, certificate, fixed safety
        fields and limits.  Deterministic for a fixed input; see module notes.
    """
    sc = _coerce_scenario(scenario, seed=seed)
    seed = int(seed)
    try:
        budget = int(budget_steps)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"budget_steps must be an integer, got {budget_steps!r}") from exc
    if budget < 0:
        raise ValueError(f"budget_steps must be >= 0, got {budget}")

    objective = ProxyObjective(sc)
    if route_repair:
        placement, best_cost, _route_result, repair_stats = repair_routes(
            sc, objective.cost, seed=seed, steps=budget, max_routes=ROUTE_REPAIR_MAX_ROUTES
        )
        stats = {
            "solver": "route_repair",
            "route_calls": repair_stats.get("routes_calls"),
            "initial_completion": repair_stats.get("initial_completion"),
            "final_completion": repair_stats.get("final_completion"),
            "moves_accepted": repair_stats.get("moves_accepted"),
        }
    else:
        placement, best_cost, stats = solve(sc, objective.cost, seed=seed, steps=budget)

    violations = list(hard_violations(sc, placement))
    truth_v1 = PhysicsSimulator(sc, seed=seed).score(placement)
    truth_v2 = PhysicsSimulatorV2(sc, seed=seed).score(placement)
    router = _router_summary(sc, placement)
    intent = _intent_summary(sc, placement)

    solver_extra = {
        "solver": stats.get("solver"),
        "budget_steps": budget,
        "seed": seed,
        "objective": objective.name,
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
            "objective": objective.name,
            "solver": stats.get("solver"),
            "restarts": int(stats.get("restarts", 0) or 0),
            "router": f"GridRouter(grid_mm={ROUTER_GRID_MM}, layers={ROUTER_LAYERS})",
        },
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


__all__ = ["run_pipeline", "PIPELINE_SCHEMA", "DEFAULT_TEMPLATE", "DEFAULT_BUDGET_STEPS"]
