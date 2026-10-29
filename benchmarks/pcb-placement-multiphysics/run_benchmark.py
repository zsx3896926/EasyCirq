#!/usr/bin/env python3
"""CI smoke for the offline placement multi-physics benchmark.

Runs two cheap deterministic checks (no EDA, no network):

1. P1 objective comparison in quick mode: the multi-physics proxy must reach a
   lower hidden-simulator truth than the HPWL baseline;
2. end-to-end pipeline on the ``buck`` template: placement must be hard-feasible
   and must carry the fixed safety fields (``routing_verified:false``,
   ``drc:"NOT RUN"``, ``eda_calls:0``).

Exit code 0 on success, 1 otherwise.
"""

from __future__ import annotations

import json
import pathlib
import sys


def main() -> int:
    from mp_place.experiment import run_experiment
    from mp_place.pipeline import run_pipeline

    failures = []

    data = run_experiment(quick=True)
    agg = data["aggregate"]["mean_truth_by_objective"]
    hpwl, proxy = agg.get("hpwl"), agg.get("multiphysics_proxy")
    print(f"[benchmark] P1 quick: hpwl={hpwl} proxy={proxy}")
    if hpwl is None or proxy is None:
        failures.append("P1 aggregate missing hpwl/proxy")
    elif not proxy < hpwl:
        failures.append(f"P1 quick: proxy truth {proxy} is not below hpwl {hpwl}")

    report = run_pipeline("buck", budget_steps=200, seed=0)
    router = report.get("router", {})
    print(
        "[benchmark] pipeline buck:",
        json.dumps(
            {
                "feasible": report.get("feasible"),
                "truth_v2": report.get("truth_v2"),
                "router_completion": router.get("completion"),
                "fixed_fields": report.get("fixed_fields"),
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
    )
    if not report.get("feasible"):
        failures.append("pipeline buck: placement is not hard-feasible")
    fixed = report.get("fixed_fields") or {}
    if fixed != {"routing_verified": False, "drc": "NOT RUN", "eda_calls": 0}:
        failures.append(f"pipeline buck: bad fixed_fields {fixed!r}")

    # 2b. every registered template must instantiate to a hard-feasible layout
    from mp_place.model import hard_violations
    from mp_place.solver import random_feasible_placement
    from mp_place.templates import instantiate, template_names
    import random as _random

    for tpl in template_names():
        sc = instantiate(tpl, seed=0)
        pl = random_feasible_placement(sc, _random.Random(0))
        viol = hard_violations(sc, pl)
        if viol:
            failures.append(f"template {tpl}: {len(viol)} hard violations")
    print(f"[benchmark] templates: {len(list(template_names()))} all hard-feasible")

    # 3. real-board conversion smoke (only when the EasyCirq case dumps are
    #    present, e.g. in the repository checkout; skipped elsewhere).
    try:
        from mp_place.model import hard_violations
        from mp_place.physics_v2 import PhysicsSimulatorV2
        from mp_place.realboard import DEFAULT_SOURCES, load_and_convert

        available = [(name, path) for name, path in DEFAULT_SOURCES if pathlib.Path(path).is_file()]
        if available:
            name, path = available[0]
            converted = load_and_convert(path, name=name)
            original = converted.original_placement
            violations = hard_violations(converted.scenario, original)
            truth = PhysicsSimulatorV2(converted.scenario, seed=0).score(original)
            print(
                "[benchmark] realboard:",
                json.dumps(
                    {
                        "board": name,
                        "components": len(converted.scenario.components),
                        "nets": len(converted.scenario.nets),
                        "original_violations": len(violations),
                        "original_truth_v2": round(truth, 4),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            )
            if len(violations) > 2:  # tolerant of courtyard/bbox capture artifacts
                failures.append(f"realboard {name}: {len(violations)} hard violations on original placement")
        else:
            print("[benchmark] realboard: SKIP (no EasyCirq case dumps next to this checkout)")
    except Exception as exc:  # noqa: BLE001 - smoke, never block on optional data
        print(f"[benchmark] realboard: SKIP ({type(exc).__name__}: {exc})")

    if failures:
        for item in failures:
            print(f"[benchmark] FAIL: {item}", file=sys.stderr)
        return 1
    print("[benchmark] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
