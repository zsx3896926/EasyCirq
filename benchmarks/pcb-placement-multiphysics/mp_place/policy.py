"""P4.8 end-to-end policy table: goal -> pipeline mode, defaults, boundaries.

The framework exposes several pipeline modes (P2.11 objectives, P3.8
intent-constrained planning, P2.5 post-hoc route repair).  This module turns the
end-to-end recommendation into a **testable policy table** so the defaults
cannot silently regress:

* :data:`POLICY_GOALS` / :data:`POLICIES` -- five goals, each with the exact
  ``objective`` / ``intent_plan`` / ``route_repair`` combination, rationale,
  expected trade-off numbers and boundaries;
* :func:`recommend` -- return a JSON-safe copy of one policy entry;
* :func:`resolve_pipeline_policy` -- P4.10 executable resolution: apply a goal
  to ``objective`` / ``intent_plan`` / ``route_repair`` with explicit conflict
  rules (see :func:`resolve_pipeline_policy`; default-looking values defer to
  the policy, conflicting non-default values raise ``ValueError``);
* :func:`assert_defaults` -- regression guard for the default tier: the
  pipeline default objective must stay ``proxy``, ``route_repair`` and
  ``intent_plan`` must default to ``False``, and the ``run_auto.py`` CLI default
  objective must stay ``proxy``.

Execution entry points (P4.10): ``run_pipeline(..., policy="routability")``
applies the table to the pipeline, and ``run_auto.py --policy GOAL`` executes it
(``--recommend GOAL`` still only prints).  Consistency between
:func:`recommend` and the executed mode is asserted by
``tests/test_policy.py`` / ``tests/test_pipeline.py``.

Decision table (evidence: ``report_pipeline_objective.md``,
``report_pipeline_intent.md``, ``report_route_cost.md``, ``report_holdout.md``;
8 synthetic templates, solver ``steps=800``):

    goal             objective     intent_plan  route_repair  recommended
    balanced         proxy         False        False         default
    routability      route_aware   False        False         yes (safe)
    intent_fidelity  proxy         True         False         yes (semantics)
    truth_sensitive  proxy         False        True          yes (API, slower)
    experimental     tuned         False        False         NO (in-sample only)

Prohibitions (enforced by :func:`assert_defaults` / documented in
``policies.md``): never default to ``tuned`` (P2.9 table is in-sample only,
held-out truth +7.47%, 0/8 templates); never treat the offline proxy/routability
oracle as DRC or real routing; never claim ``routing_verified``/``drc`` results;
never tune on held-out seeds 2/3/4.

Pure standard library; importing this module is cheap (``run_auto`` is imported
lazily inside :func:`assert_defaults` only).
"""

from __future__ import annotations

import copy
import inspect
import json
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .pipeline import DEFAULT_OBJECTIVE, PIPELINE_OBJECTIVES

POLICY_SCHEMA = "mp_place.policy/v1"
DEFAULT_GOAL = "balanced"
#: Canonical goal ids, in display order.
POLICY_GOALS: Tuple[str, ...] = (
    "balanced",
    "routability",
    "intent_fidelity",
    "truth_sensitive",
    "experimental",
)
#: Values the default tier must keep (checked by :func:`assert_defaults`).
EXPECTED_DEFAULTS: Dict[str, Any] = {
    "objective": "proxy",
    "intent_plan": False,
    "route_repair": False,
}

#: Boundary list shared by every policy entry (offline surrogate limits).
COMMON_BOUNDARIES: List[str] = [
    "offline surrogate only: no EDA, no DRC, no real routing, no network",
    "reports always carry routing_verified=false, drc=\"NOT RUN\", eda_calls=0",
    "router completion is a 1 mm / 2-layer grid-maze oracle, not a routability proof",
    "truth_v2 is the offline physics_v2 simulator, not a real multi-physics solve",
    "templates are synthetic product families; real boards need realboard/EDA verification",
]

POLICIES: Dict[str, Dict[str, Any]] = {
    "balanced": {
        "goal": "balanced",
        "label": "默认平衡档",
        "recommended": True,
        "default": True,
        "objective": "proxy",
        "intent_plan": False,
        "route_repair": False,
        "intent_ccg_weight": None,
        "run_auto_args": [],
        "rationale": "Backwards-compatible default: minimises the P1/P2 multi-physics "
        "proxy with the portfolio solver. No extra machinery, deterministic, "
        "cheapest runtime; the reference layout every other mode is compared against.",
        "expected_tradeoff": {
            "in_sample_seeds": [0, 1],
            "heldout_seeds": [2, 3, 4],
            "in_sample": {
                "completion": 0.9019,
                "truth_v2": 2.0001,
                "truth_delta_pct": 0.0,
                "runtime_s": 0.26,
                "ccg_hard_per_run": 0.0,
            },
            "heldout": {
                "completion": 0.8424,
                "truth_v2": 1.7734,
                "runtime_s": 0.34,
            },
        },
        "command_template": "python run_auto.py --template <NAME> --seed <SEED>",
        "evidence": ["report_pipeline_objective.md", "report_v2.md"],
        "warnings": [],
        "boundaries": list(COMMON_BOUNDARIES),
    },
    "routability": {
        "goal": "routability",
        "label": "可布通性档（推荐安全升级）",
        "recommended": True,
        "default": False,
        "objective": "route_aware",
        "intent_plan": False,
        "route_repair": False,
        "intent_ccg_weight": None,
        "run_auto_args": ["--objective", "route_aware"],
        "rationale": "Fixed w_route=2.0 RouteAwareObjective (P2.8 code path, no "
        "per-template table): folds a cheap router-free routability penalty into "
        "the cost. Generalises to held-out seeds, unlike the P2.9 tuned table.",
        "expected_tradeoff": {
            "in_sample_seeds": [0, 1],
            "heldout_seeds": [2, 3, 4],
            "in_sample": {
                "completion": 0.9755,
                "truth_v2": 2.0627,
                "truth_delta_pct": 3.13,
                "runtime_s": 0.54,
                "ccg_hard_per_run": 8.19,
            },
            "heldout": {
                "completion": 0.9502,
                "truth_v2": 1.7819,
                "truth_delta_pct": 0.48,
                "runtime_s": 0.64,
            },
            "router_calls_for_cost": 0,
        },
        "command_template": "python run_auto.py --template <NAME> --seed <SEED> "
        "--objective route_aware",
        "evidence": [
            "report_pipeline_objective.md",
            "report_route_cost.md",
            "report_holdout.md",
        ],
        "warnings": [
            "truth_v2 cost: +3.13% in-sample, +0.48% held-out (target <= +1% held-out)",
            "direct objective mode does not preserve the reference intent (CCG != 0)",
        ],
        "boundaries": list(COMMON_BOUNDARIES),
    },
    "intent_fidelity": {
        "goal": "intent_fidelity",
        "label": "意图保真档",
        "recommended": True,
        "default": False,
        "objective": "proxy",
        "intent_plan": True,
        "route_repair": False,
        "intent_ccg_weight": 25.0,
        "run_auto_args": ["--intent-plan"],
        "rationale": "P3.8 intent-constrained planning: proxy solve -> build_intent "
        "from that placement -> plan_from_intent(relax=True). Keeps the hard "
        "near/cluster/edge layout semantics (0 violations under relaxed bounds) at a "
        "small truth cost, but does not optimise for router completion.",
        "expected_tradeoff": {
            "in_sample_seeds": [0, 1],
            "heldout_seeds": None,
            "in_sample": {
                "completion": 0.8388,
                "truth_v2": 1.8699,
                "truth_delta_pct": -6.51,
                "runtime_s": 0.94,
                "ccg_hard_per_run": 0.0,
                "ccg_soft_per_run": 0.0,
                "original_intent_deviations_per_run": 4.69,
            },
            "heldout": None,
            "intent_planner": "intent_solver.plan_from_intent(relax=True, ccg_weight=25.0)",
        },
        "command_template": "python run_auto.py --template <NAME> --seed <SEED> "
        "--intent-plan",
        "evidence": ["report_pipeline_intent.md", "report_intent_pareto.md"],
        "warnings": [
            "requires --objective proxy (intent is built from the proxy placement)",
            "relaxed hard semantics are satisfied but the original strict bounds are "
            "deviated from (~4.69 violations/run); use relax=False in the planner if "
            "strict intent bounds are mandatory (larger truth cost)",
            "router completion drops to 0.8388 (below proxy/route_aware)",
        ],
        "boundaries": list(COMMON_BOUNDARIES),
    },
    "truth_sensitive": {
        "goal": "truth_sensitive",
        "label": "truth 优先档（proxy + 事后修复）",
        "recommended": True,
        "default": False,
        "objective": "proxy",
        "intent_plan": False,
        "route_repair": True,
        "intent_ccg_weight": None,
        "run_auto_args": [],
        "rationale": "Plain proxy solve followed by route_opt.repair_routes: uses the "
        "offline router as an acceptance oracle (up to 60 calls) to repair routed "
        "nets. Best completion among the non-intent modes and best truth_v2, at a "
        "large runtime cost; this mode is API-only (run_auto has no --route-repair).",
        "expected_tradeoff": {
            "in_sample_seeds": [0, 1],
            "heldout_seeds": None,
            "in_sample": {
                "completion": 0.9938,
                "truth_v2": 1.9101,
                "truth_delta_pct": -4.50,
                "runtime_s": 1.81,
                "router_calls_max": 60,
            },
            "heldout": None,
        },
        "command_template": "python run_auto.py --template <NAME> --seed <SEED> "
        "--policy truth_sensitive",
        "evidence": ["report_route_cost.md", "report_route.md"],
        "warnings": [
            "not router-free: up to 60 offline router calls per run, ~1.8 s/run",
            "no dedicated --route-repair CLI flag; execute via --policy truth_sensitive "
            "(or run_pipeline(..., route_repair=True))",
            "no held-out generalisation measurement for post-hoc repair yet",
        ],
        "boundaries": list(COMMON_BOUNDARIES),
    },
    "experimental": {
        "goal": "experimental",
        "label": "实验档（tuned 表，不推荐）",
        "recommended": False,
        "default": False,
        "objective": "tuned",
        "intent_plan": False,
        "route_repair": False,
        "intent_ccg_weight": None,
        "run_auto_args": ["--objective", "tuned"],
        "rationale": "P2.9 per-template tuned weight table. In-sample it looks best "
        "(completion 1.0000, truth -0.03%), but the table does not generalise: on "
        "held-out seeds 2/3/4 truth is +7.47% with 0/8 templates meeting the target. "
        "Kept for research/diagnostics only.",
        "expected_tradeoff": {
            "in_sample_seeds": [0, 1],
            "heldout_seeds": [2, 3, 4],
            "in_sample": {
                "completion": 1.0000,
                "truth_v2": 1.9995,
                "truth_delta_pct": -0.03,
                "runtime_s": 0.51,
            },
            "heldout": {
                "completion": 0.9113,
                "truth_v2": 1.9058,
                "truth_delta_pct": 7.47,
            },
        },
        "command_template": "python run_auto.py --template <NAME> --seed <SEED> "
        "--objective tuned",
        "evidence": [
            "report_pipeline_objective.md",
            "report_holdout.md",
            "report_tune_cv.md",
        ],
        "warnings": [
            "NOT recommended and never a default",
            "in-sample only: held-out truth +7.47%, 0/8 templates meet the target",
            "do not tune on held-out seeds 2/3/4 (TUNED_TABLE is frozen)",
        ],
        "boundaries": list(COMMON_BOUNDARIES),
    },
}


def recommend(goal: str) -> Dict[str, Any]:
    """Return the JSON-safe policy recommendation for ``goal``.

    ``goal`` must be one of :data:`POLICY_GOALS` (``balanced``,
    ``routability``, ``intent_fidelity``, ``truth_sensitive``,
    ``experimental``).  The returned dict contains the mode
    (``objective`` / ``intent_plan`` / ``route_repair``), ``recommended``,
    rationale, expected trade-off numbers, command template, evidence and
    boundaries.  A deep copy is returned so callers cannot mutate the policy
    table.
    """
    if not isinstance(goal, str):
        raise TypeError(f"goal must be a string, got {type(goal).__name__}")
    key = goal.strip()
    if key not in POLICIES:
        raise ValueError(
            f"unknown policy goal {goal!r}; expected one of {POLICY_GOALS}"
        )
    entry = copy.deepcopy(POLICIES[key])
    # P4.10 executable command (policy based) alongside the explicit-flag example.
    entry["policy_command"] = (
        f"python run_auto.py --template <NAME> --seed <SEED> --policy {key}"
    )
    return entry


def resolve_pipeline_policy(
    goal: str,
    objective: str = DEFAULT_OBJECTIVE,
    intent_plan: bool = False,
    route_repair: bool = False,
) -> Dict[str, Any]:
    """Resolve an executable policy against explicit ``run_pipeline`` parameters.

    P4.10 precedence / conflict rules (strict and explicit so that a policy can
    never silently fight hand-written parameters):

    1. ``policy`` is authoritative for ``objective`` / ``intent_plan`` /
       ``route_repair``.
    2. A hand-written argument is a **conflict** only when it is a
       *non-default* value that differs from the policy value
       (``objective`` not in ``{policy objective, "proxy"}``,
       ``intent_plan=True`` when the policy says ``False``,
       ``route_repair=True`` when the policy says ``False``); a conflict raises
       ``ValueError`` instead of silently choosing a winner.
    3. Default-looking values (``objective="proxy"``, ``intent_plan=False``,
       ``route_repair=False``) are treated as "not specified"; the policy value
       wins.  This is what lets ``run_auto.py --policy GOAL`` reuse the CLI
       defaults.
    4. To force a custom combination, pass ``policy=None`` and set the three
       parameters explicitly (``run_pipeline(..., policy=None, objective=...)``).

    Returns a JSON-safe resolution dict with the effective mode, the observed
    explicit values and ``source="policy"``; the pipeline report records it so
    consistency between :func:`recommend` and the executed mode is testable.
    """
    entry = recommend(goal)
    if not isinstance(objective, str):
        raise TypeError(f"objective must be a string, got {type(objective).__name__}")
    objective_value = objective.strip()
    if objective_value not in PIPELINE_OBJECTIVES:
        raise ValueError(
            f"unknown objective {objective!r}; expected one of {PIPELINE_OBJECTIVES}"
        )
    intent_value = bool(intent_plan)
    repair_value = bool(route_repair)
    conflicts: List[str] = []
    if objective_value not in (entry["objective"], DEFAULT_OBJECTIVE):
        conflicts.append(
            f"objective={objective_value!r} conflicts with policy "
            f"{entry['goal']!r} (objective={entry['objective']!r})"
        )
    if intent_value and not entry["intent_plan"]:
        conflicts.append(
            f"intent_plan=True conflicts with policy {entry['goal']!r} "
            "(intent_plan=False)"
        )
    if repair_value and not entry["route_repair"]:
        conflicts.append(
            f"route_repair=True conflicts with policy {entry['goal']!r} "
            "(route_repair=False)"
        )
    if conflicts:
        raise ValueError(
            "policy conflict: "
            + "; ".join(conflicts)
            + "; pass policy=None to set objective/intent_plan/route_repair explicitly"
        )
    return {
        "goal": entry["goal"],
        "objective": entry["objective"],
        "intent_plan": bool(entry["intent_plan"]),
        "route_repair": bool(entry["route_repair"]),
        "intent_ccg_weight": entry.get("intent_ccg_weight"),
        "explicit": {
            "objective": objective_value,
            "intent_plan": intent_value,
            "route_repair": repair_value,
        },
        "source": "policy",
        "schema": POLICY_SCHEMA,
    }


# --------------------------------------------------------------------------- #
# Default regression guard
# --------------------------------------------------------------------------- #
def _pipeline_defaults() -> Dict[str, Any]:
    """Actual ``run_pipeline`` signature defaults (introspection)."""
    from .pipeline import run_pipeline

    params = inspect.signature(run_pipeline).parameters
    return {
        "objective": params["objective"].default,
        "intent_plan": params["intent_plan"].default,
        "route_repair": params["route_repair"].default,
        "budget_steps": params["budget_steps"].default,
    }


def _run_auto_defaults() -> Dict[str, Any]:
    """Actual ``run_auto.py`` CLI defaults (parser introspection)."""
    import importlib

    run_auto = importlib.import_module("run_auto")
    parser = run_auto._build_parser()
    args = parser.parse_args([])
    return {
        "objective": args.objective,
        "intent_plan": bool(args.intent_plan),
        "recommend": args.recommend,
    }


def assert_defaults() -> Dict[str, Any]:
    """Fail loudly if the default tier or the balanced policy regresses.

    Checks:

    * :func:`mp_place.pipeline.run_pipeline` defaults:
      ``objective == "proxy"``, ``intent_plan is False``,
      ``route_repair is False``;
    * ``run_auto.py`` CLI defaults: ``--objective`` defaults to ``proxy`` and
      ``--intent-plan`` to ``False``;
    * the ``balanced`` policy entry is exactly the default tier.

    Returns a JSON-safe summary on success.  Raises :class:`AssertionError`
    with a concrete message listing every mismatch on failure (so a CI smoke
    test fails when someone changes a default by accident).
    """
    pipeline_defaults = _pipeline_defaults()
    cli_defaults = _run_auto_defaults()
    balanced = POLICIES[DEFAULT_GOAL]
    errors: List[str] = []

    for key, expected in EXPECTED_DEFAULTS.items():
        actual = pipeline_defaults.get(key)
        if actual != expected:
            errors.append(
                f"run_pipeline default {key}={actual!r}, expected {expected!r}"
            )
        cli_key = key if key != "route_repair" else None
        if cli_key is not None:
            cli_actual = cli_defaults.get(cli_key)
            if cli_actual != expected:
                errors.append(
                    f"run_auto default {cli_key}={cli_actual!r}, expected {expected!r}"
                )
    if pipeline_defaults.get("objective") != DEFAULT_OBJECTIVE:
        errors.append(
            f"run_pipeline objective default {pipeline_defaults.get('objective')!r} "
            f"!= pipeline.DEFAULT_OBJECTIVE {DEFAULT_OBJECTIVE!r}"
        )
    for key in ("objective", "intent_plan", "route_repair"):
        if balanced.get(key) != EXPECTED_DEFAULTS[key]:
            errors.append(
                f"balanced policy {key}={balanced.get(key)!r}, expected "
                f"{EXPECTED_DEFAULTS[key]!r}"
            )
    if errors:
        raise AssertionError("default policy regression: " + "; ".join(errors))
    return {
        "ok": True,
        "schema": POLICY_SCHEMA,
        "default_goal": DEFAULT_GOAL,
        "pipeline": pipeline_defaults,
        "run_auto": cli_defaults,
        "balanced_policy": {
            key: balanced[key]
            for key in ("objective", "intent_plan", "route_repair")
        },
        "goals": list(POLICY_GOALS),
    }


# --------------------------------------------------------------------------- #
# Human-readable rendering / CLI
# --------------------------------------------------------------------------- #
def _fmt_num(value: Any, digits: int = 4) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "n/a"


def _fmt_pct(value: Any) -> str:
    try:
        return f"{float(value):+.2f}%"
    except (TypeError, ValueError):
        return "n/a"


def format_recommendation(goal: str) -> str:
    """Human-readable policy block (used by ``run_auto.py --recommend``)."""
    entry = recommend(goal)
    tradeoff = entry["expected_tradeoff"]
    lines = [
        f"[policy] goal={entry['goal']} ({entry['label']})",
        f"  recommended: {'yes' if entry['recommended'] else 'NO (research only)'}"
        + ("  [default]" if entry.get("default") else ""),
        "  mode: objective={objective} intent_plan={intent_plan} "
        "route_repair={route_repair}".format(**entry),
        f"  why: {entry['rationale']}",
        "  expected trade-off (8 templates, solver steps=800):",
    ]
    in_sample = tradeoff.get("in_sample") or {}
    heldout = tradeoff.get("heldout") or {}
    if in_sample:
        lines.append(
            "    in-sample seeds {seeds}: completion={completion} truth_v2={truth} "
            "(delta {delta}) runtime~{runtime}s".format(
                seeds=in_sample_seeds(tradeoff),
                completion=_fmt_num(in_sample.get("completion")),
                truth=_fmt_num(in_sample.get("truth_v2")),
                delta=_fmt_pct(in_sample.get("truth_delta_pct")),
                runtime=_fmt_num(in_sample.get("runtime_s"), 2),
            )
        )
        if in_sample.get("ccg_hard_per_run") is not None:
            lines.append(
                "      hard CCG violations/run={hard}, soft/run={soft}, "
                "original strict deviations/run={dev}".format(
                    hard=_fmt_num(in_sample.get("ccg_hard_per_run"), 2),
                    soft=_fmt_num(in_sample.get("ccg_soft_per_run"), 2),
                    dev=_fmt_num(in_sample.get("original_intent_deviations_per_run"), 2),
                )
            )
    if heldout:
        lines.append(
            "    held-out seeds {seeds}: completion={completion} truth_v2={truth} "
            "(delta {delta})".format(
                seeds=tradeoff.get("heldout_seeds"),
                completion=_fmt_num(heldout.get("completion")),
                truth=_fmt_num(heldout.get("truth_v2")),
                delta=_fmt_pct(heldout.get("truth_delta_pct")),
            )
        )
    else:
        lines.append("    held-out seeds: not measured for this mode (in-sample only)")
    lines.append(f"  run (policy executable): {entry['policy_command']}")
    lines.append(f"  run (explicit flags/API): {entry['command_template']}")
    lines.append("  evidence: " + ", ".join(entry["evidence"]))
    if entry["warnings"]:
        lines.append("  warnings:")
        lines.extend(f"    - {warning}" for warning in entry["warnings"])
    lines.append("  boundaries: offline proxy only; NOT DRC / NOT real routing "
                 "(routing_verified=false, drc=\"NOT RUN\").")
    return "\n".join(lines)


def in_sample_seeds(tradeoff: Dict[str, Any]) -> str:
    """Format the in-sample seed list of a policy trade-off block."""
    seeds = tradeoff.get("in_sample_seeds") or []
    return "[" + ", ".join(str(seed) for seed in seeds) + "]"


def _emit_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def main(argv: Optional[Sequence[str]] = None) -> int:
    """``python -m mp_place.policy``: recommend / check-defaults / list."""
    import argparse
    import sys

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):  # pragma: no cover - exotic streams
            pass
    parser = argparse.ArgumentParser(
        prog="python -m mp_place.policy",
        description="P4.8 end-to-end policy table (goal -> pipeline mode / boundaries)",
    )
    parser.add_argument(
        "--recommend",
        metavar="GOAL",
        choices=list(POLICY_GOALS),
        help="print the recommendation for GOAL and exit",
    )
    parser.add_argument(
        "--check-defaults",
        action="store_true",
        help="assert the default tier (pipeline proxy / route_repair False / intent_plan False)",
    )
    parser.add_argument("--list", action="store_true", help="list policy goals")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args(argv)

    if args.list:
        for goal in POLICY_GOALS:
            entry = POLICIES[goal]
            print(
                f"{goal:16s} objective={entry['objective']:12s} "
                f"intent_plan={entry['intent_plan']!s:5s} "
                f"route_repair={entry['route_repair']!s:5s} "
                f"recommended={entry['recommended']}"
            )
        return 0
    if args.recommend is not None:
        if args.json:
            _emit_json(recommend(args.recommend))
        else:
            print(format_recommendation(args.recommend))
        return 0
    if args.check_defaults:
        try:
            details = assert_defaults()
        except AssertionError as exc:
            print(f"[policy] DEFAULTS REGRESSED: {exc}", file=sys.stderr)
            return 1
        if args.json:
            _emit_json(details)
        else:
            print(
                "[policy] defaults OK: run_pipeline objective={objective}, "
                "intent_plan={intent_plan}, route_repair={route_repair}; "
                "run_auto --objective={auto_objective}; default goal={default_goal}".format(
                    objective=details["pipeline"]["objective"],
                    intent_plan=details["pipeline"]["intent_plan"],
                    route_repair=details["pipeline"]["route_repair"],
                    auto_objective=details["run_auto"]["objective"],
                    default_goal=details["default_goal"],
                )
            )
        return 0
    parser.error("nothing to do; pass --recommend GOAL, --check-defaults or --list")
    return 2  # pragma: no cover - argparse.error exits


__all__ = [
    "POLICY_SCHEMA",
    "POLICY_GOALS",
    "DEFAULT_GOAL",
    "POLICIES",
    "EXPECTED_DEFAULTS",
    "recommend",
    "resolve_pipeline_policy",
    "assert_defaults",
    "format_recommendation",
    "main",
]

if __name__ == "__main__":
    raise SystemExit(main())
