#!/usr/bin/env python3
"""P4-G: one-command offline placement pipeline (template/scenario -> JSON report).

    python run_auto.py --template buck --seed 0
    python run_auto.py --scenario buck --seed 0 --steps 800
    python run_auto.py --template buck --json > report.json
    python run_auto.py --template buck --objective route_aware --seed 0
    python run_auto.py --all-templates --seeds 0 --objective proxy --json
    python run_auto.py --recommend routability
    python run_auto.py --policy intent_fidelity

``--template NAME`` instantiates a parameterised product-family template with
``--seed``; ``--scenario NAME`` loads one of the fixed P1 benchmark scenarios
(``mcu-min``/``buck``/``rs485``/``motor``/``wireless``).  Default: template
``buck``, seed ``0``, budget ``800`` solver steps, objective ``proxy``.

``--objective {proxy,route_aware,tuned}`` selects the solver cost objective
(P2.11 / task-27 update):

* ``proxy`` (default) -- P1/P2 multi-physics proxy, backwards compatible;
* ``route_aware`` (**recommended safe** option) -- fixed ``w_route=2.0``
  ``route_cost.RouteAwareObjective`` (no per-template table; P2.10 held-out
  seeds 2/3/4: completion 0.9502 vs 0.8424, truth_v2 +0.48% vs baseline);
* ``tuned`` (**experimental / in-sample only, not recommended**) -- P2.9
  ``route_cost.tuned_objective`` table lookup (does not generalise: held-out
  truth_v2 +7.47%, 0/8 templates meeting the target).  Research/diagnostics only.

The chosen objective is recorded in every report (``objective_mode`` /
``objective_model`` / ``objective_config`` / ``objective_recommended`` /
``objective_generalization``) and in each ``--all-templates`` batch row under
the ``objective`` field.

``--intent-plan`` (P3.8) enables intent-constrained planning: proxy solve ->
``intent.build_intent`` from that placement -> ``intent_solver.plan_from_intent
(relax=True)`` -> verification.  It requires the default ``proxy`` objective and
records ``planning_mode="intent_relax"`` plus an ``intent_planning`` stats block
(hard-tier CCG violations, soft violations and deviations from the original
strict bounds).  ``--all-templates`` batch rows carry ``intent_plan`` and
``planning_mode`` as well.

``--recommend GOAL`` prints the P4.8 end-to-end policy recommendation and exits
**without executing** the pipeline (human-readable block by default, JSON with
``--json``).  ``--policy GOAL`` (P4.10) **executes** the pipeline with that
policy: the goal overrides ``objective`` / ``intent_plan`` / ``route_repair``
(see :func:`mp_place.policy.resolve_pipeline_policy`; default-looking CLI values
defer to the policy, conflicting explicit values raise ``ValueError`` and the
CLI exits 2).  The goal -> mode mapping, expected trade-offs and boundaries are
defined in :mod:`mp_place.policy` and summarised in ``policies.md``.

Output: a single JSON report on stdout (``--json`` -> one compact sorted line;
otherwise indented).  Human-readable status goes to stderr, so piping stdout
into ``jq``/``json`` keeps working.  Exit code is ``0`` when the resulting
placement is hard-feasible, ``1`` otherwise, ``2`` for usage/IO errors.

Everything is offline: no EDA, no DRC, no network.  The report always carries
``fixed_fields = {"routing_verified": false, "drc": "NOT RUN", "eda_calls": 0}``
and the offline-proxy limits from ``mp_place.verify``.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import List, Optional, Sequence

from mp_place import scenarios as scenarios_mod
from mp_place import templates as templates_mod
from mp_place.model import Scenario
from mp_place.pipeline import (
    DEFAULT_BUDGET_STEPS,
    DEFAULT_OBJECTIVE,
    DEFAULT_TEMPLATE,
    PIPELINE_OBJECTIVES,
    run_pipeline,
)
from mp_place.policy import POLICY_GOALS, format_recommendation, recommend

DEFAULT_SEED = 0


def _known_templates() -> List[str]:
    return list(templates_mod.template_names())


def _known_scenarios() -> List[str]:
    return [sc.name for sc in scenarios_mod.build_scenarios(seed=0)]


def load_scenario(
    template: Optional[str],
    scenario: Optional[str],
    seed: int,
) -> Scenario:
    """Resolve the CLI selection into a :class:`Scenario`.

    ``template`` wins when both are given (argparse already forbids that);
    ``None``/``None`` means the default template.
    """
    if template is not None:
        return templates_mod.instantiate(template, seed=seed)
    if scenario is not None:
        for candidate in scenarios_mod.build_scenarios(seed=seed):
            if candidate.name == scenario:
                return candidate
        raise KeyError(
            f"unknown scenario {scenario!r}; known scenarios: {sorted(_known_scenarios())}"
        )
    return templates_mod.instantiate(DEFAULT_TEMPLATE, seed=seed)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_auto.py",
        description="Offline multi-physics placement pipeline (solve -> verify -> intent -> certificate).",
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--template",
        default=None,
        metavar="NAME",
        help=f"parameterised product-family template (default: {DEFAULT_TEMPLATE}); "
        f"known: {', '.join(_known_templates())}",
    )
    source.add_argument(
        "--scenario",
        default=None,
        metavar="NAME",
        help="fixed P1 benchmark scenario; known: " + ", ".join(_known_scenarios()),
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="RNG seed (default: 0)")
    parser.add_argument(
        "--steps",
        type=int,
        default=DEFAULT_BUDGET_STEPS,
        help=f"total solver move budget (default: {DEFAULT_BUDGET_STEPS})",
    )
    parser.add_argument(
        "--objective",
        choices=list(PIPELINE_OBJECTIVES),
        default=DEFAULT_OBJECTIVE,
        help="solver cost objective (default: %(default)s); "
        "'proxy' = P1/P2 multi-physics proxy (backwards compatible); "
        "'route_aware' = RECOMMENDED SAFE option, fixed w_route=2.0 "
        "RouteAwareObjective (no per-template table, held-out safe); "
        "'tuned' = EXPERIMENTAL / in-sample only (P2.9 per-template table; "
        "does not generalise to held-out seeds, research/diagnostics only)",
    )
    parser.add_argument(
        "--intent-plan",
        action="store_true",
        help="P3.8 intent-constrained planning: after the proxy solve, build the "
        "layout intent from that placement and refine it with "
        "plan_from_intent(relax=True) before verification; requires "
        "--objective proxy (default)",
    )
    parser.add_argument(
        "--intent-ccg-weight",
        type=float,
        default=25.0,
        metavar="W",
        help="CCG penalty weight for --intent-plan (default: 25.0)",
    )
    parser.add_argument(
        "--recommend",
        metavar="GOAL",
        choices=list(POLICY_GOALS),
        default=None,
        help="print the P4.8 policy recommendation for GOAL and exit without "
        "executing the pipeline; goals: " + ", ".join(POLICY_GOALS),
    )
    parser.add_argument(
        "--policy",
        metavar="GOAL",
        choices=list(POLICY_GOALS),
        default=None,
        help="P4.10: execute the pipeline with policy GOAL (overrides objective/"
        "intent_plan/route_repair; conflicts with explicit non-default values "
        "exit 2); use --recommend to only print the policy",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print exactly one compact JSON object on stdout (sorted keys)",
    )
    parser.add_argument(
        "--all-templates",
        action="store_true",
        help="run every registered template (x --seeds) and print one batch JSON report",
    )
    parser.add_argument(
        "--seeds",
        default="0",
        help="comma-separated seeds for --all-templates (default: 0)",
    )
    return parser


def _batch(
    seeds: list[int],
    steps: int,
    objective: str = DEFAULT_OBJECTIVE,
    intent_plan: bool = False,
    intent_ccg_weight: float = 25.0,
    policy: Optional[str] = None,
) -> dict:
    rows = []
    for name in _known_templates():
        for seed in seeds:
            scenario = templates_mod.instantiate(name, seed=seed)
            report = run_pipeline(
                scenario,
                budget_steps=steps,
                seed=seed,
                objective=objective,
                intent_plan=intent_plan,
                intent_ccg_weight=intent_ccg_weight,
                policy=policy,
            )
            router = report.get("router", {})
            rows.append(
                {
                    "template": name,
                    "seed": seed,
                    "objective": objective,
                    "objective_mode": report.get("objective_mode"),
                    "objective_model": report.get("objective_model"),
                    "policy": report.get("policy"),
                    "policy_goal": report.get("policy_goal"),
                    "intent_plan": bool(intent_plan),
                    "planning_mode": report.get("planning_mode"),
                    "feasible": report.get("feasible"),
                    "truth_v1": report.get("truth_v1"),
                    "truth_v2": report.get("truth_v2"),
                    "router_completion": router.get("completion"),
                    "router_failed_nets": router.get("failed_nets", []),
                    "router_vias": router.get("vias"),
                    "intent_constraints": report.get("intent_constraints"),
                }
            )
    return {
        "schema": "mp_place.batch/v1",
        "objective": objective,
        "intent_plan": bool(intent_plan),
        "intent_ccg_weight": float(intent_ccg_weight),
        "policy": policy,
        "n_runs": len(rows),
        "all_feasible": all(r["feasible"] for r in rows),
        "rows": rows,
    }


def _emit(report: dict, as_json: bool) -> None:
    if as_json:
        text = json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    else:
        text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    print(text)


def _summary(report: dict) -> str:
    scenario = report.get("scenario", {})
    router = report.get("router", {})
    return (
        "[run_auto] "
        f"scenario={scenario.get('name')} "
        f"objective={report.get('objective_mode')} "
        f"planning={report.get('planning_mode')} "
        f"policy={report.get('policy_goal')} "
        f"feasible={report.get('feasible')} "
        f"violations={len(report.get('violations', []))} "
        f"truth_v1={report.get('truth_v1')} truth_v2={report.get('truth_v2')} "
        f"router={router.get('status')}/{router.get('completion')} "
        f"intent_replay_ok={report.get('intent_replay_ok')} "
        f"digest={(report.get('placement_digest') or '')[:12]}"
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):  # pragma: no cover - exotic streams
            pass
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.recommend is not None and args.policy is not None:
        parser.error("--recommend and --policy are mutually exclusive")

    if args.recommend is not None:
        # P4.8 policy table: print the recommendation and exit (do not solve).
        policy_entry = recommend(args.recommend)
        if args.json:
            print(
                json.dumps(
                    policy_entry,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
        else:
            print(format_recommendation(args.recommend))
        print(
            f"[run_auto] policy goal={policy_entry['goal']} "
            f"objective={policy_entry['objective']} "
            f"intent_plan={policy_entry['intent_plan']} "
            f"route_repair={policy_entry['route_repair']} "
            f"recommended={policy_entry['recommended']}",
            file=sys.stderr,
        )
        return 0

    if args.steps < 0:
        parser.error("--steps must be >= 0")
    if args.seed < 0:
        parser.error("--seed must be >= 0")
    if args.intent_plan and args.objective != DEFAULT_OBJECTIVE:
        parser.error("--intent-plan requires --objective proxy")
    if not (args.intent_ccg_weight >= 0.0):
        parser.error("--intent-ccg-weight must be >= 0")

    try:
        scenario = load_scenario(args.template, args.scenario, args.seed)
    except KeyError as exc:
        message = exc.args[0] if exc.args else str(exc)
        print(f"error: {message}", file=sys.stderr)
        return 2

    if args.all_templates:
        if args.template is not None or args.scenario is not None:
            parser.error("--all-templates cannot be combined with --template/--scenario")
        try:
            seeds = [int(s) for s in args.seeds.split(",") if s.strip()]
        except ValueError:
            parser.error("--seeds must be comma-separated integers")
        if not seeds or min(seeds) < 0:
            parser.error("--seeds must be non-empty and >= 0")
        try:
            batch = _batch(
                seeds,
                args.steps,
                args.objective,
                args.intent_plan,
                args.intent_ccg_weight,
                args.policy,
            )
        except ValueError as exc:
            if args.policy is None:
                raise
            print(f"error: {exc}", file=sys.stderr)
            return 2
        _emit(batch, args.json)
        print(
            f"[run_auto] batch templates={len(_known_templates())} seeds={seeds} "
            f"objective={args.objective} intent_plan={args.intent_plan} "
            f"policy={args.policy} "
            f"runs={batch['n_runs']} all_feasible={batch['all_feasible']}",
            file=sys.stderr,
        )
        return 0 if batch["all_feasible"] else 1

    try:
        report = run_pipeline(
            scenario,
            budget_steps=args.steps,
            seed=args.seed,
            objective=args.objective,
            intent_plan=args.intent_plan,
            intent_ccg_weight=args.intent_ccg_weight,
            policy=args.policy,
        )
    except ValueError as exc:
        if args.policy is None:
            raise
        print(f"error: {exc}", file=sys.stderr)
        return 2
    _emit(report, args.json)
    print(_summary(report), file=sys.stderr)
    return 0 if report.get("feasible") else 1


if __name__ == "__main__":
    raise SystemExit(main())
