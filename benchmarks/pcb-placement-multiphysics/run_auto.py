#!/usr/bin/env python3
"""P4-G: one-command offline placement pipeline (template/scenario -> JSON report).

    python run_auto.py --template buck --seed 0
    python run_auto.py --scenario buck --seed 0 --steps 800
    python run_auto.py --template buck --json > report.json

``--template NAME`` instantiates a parameterised product-family template with
``--seed``; ``--scenario NAME`` loads one of the fixed P1 benchmark scenarios
(``mcu-min``/``buck``/``rs485``/``motor``/``wireless``).  Default: template
``buck``, seed ``0``, budget ``800`` solver steps.

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
from mp_place.pipeline import DEFAULT_BUDGET_STEPS, DEFAULT_TEMPLATE, run_pipeline

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


def _batch(seeds: list[int], steps: int) -> dict:
    rows = []
    for name in _known_templates():
        for seed in seeds:
            scenario = templates_mod.instantiate(name, seed=seed)
            report = run_pipeline(scenario, budget_steps=steps, seed=seed)
            router = report.get("router", {})
            rows.append(
                {
                    "template": name,
                    "seed": seed,
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

    if args.steps < 0:
        parser.error("--steps must be >= 0")
    if args.seed < 0:
        parser.error("--seed must be >= 0")

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
        batch = _batch(seeds, args.steps)
        _emit(batch, args.json)
        print(
            f"[run_auto] batch templates={len(_known_templates())} seeds={seeds} "
            f"runs={batch['n_runs']} all_feasible={batch['all_feasible']}",
            file=sys.stderr,
        )
        return 0 if batch["all_feasible"] else 1

    report = run_pipeline(scenario, budget_steps=args.steps, seed=args.seed)
    _emit(report, args.json)
    print(_summary(report), file=sys.stderr)
    return 0 if report.get("feasible") else 1


if __name__ == "__main__":
    raise SystemExit(main())
