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

    if failures:
        for item in failures:
            print(f"[benchmark] FAIL: {item}", file=sys.stderr)
        return 1
    print("[benchmark] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
