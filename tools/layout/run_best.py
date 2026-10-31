#!/usr/bin/env python3
"""Reproduce / benchmark the documented "best" routing configuration.

`ec_layout.py route` on the CLI cannot pass `segment_check` (it is a keyword of
`route()`), so the handoff's best numbers were produced programmatically.  This
driver makes that configuration reproducible from one command and prints the
FIVE metrics the handoff mandates together — a single metric has misled this
project several times (e.g. clearance improved while unrouted doubled).

Usage:
    python tools/layout/run_best.py dump.json --place ec-placed.json \
        --iters 20 --layers 4 --segment-check --out plan.json
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ec_layout as ec  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="run the best known route config")
    ap.add_argument("dump")
    ap.add_argument("--place", required=True)
    ap.add_argument("--iters", type=int, default=20)
    ap.add_argument("--layers", type=int, default=4)
    ap.add_argument("--segment-check", dest="segment_check", action="store_true", default=True)
    ap.add_argument("--no-segment-check", dest="segment_check", action="store_false")
    ap.add_argument("--plane-net", dest="plane_nets", action="append", default=[],
                    help="net carried by a plane instead of tracks (e.g. GND)")
    ap.add_argument("--plane-layer", dest="plane_layer", type=int)
    ap.add_argument("--out", help="write the ROUTE PLAN here (tracks/vias)")
    ap.add_argument("--kpi", help="write the KPI report here")
    ap.add_argument("--failures", action="store_true", help="print per-leg failure detail")
    a = ap.parse_args()

    with open(a.dump, encoding="utf-8") as f:
        board = ec.Board(json.load(f))
    with open(a.place, encoding="utf-8") as f:
        ec.apply_placement(board, json.load(f))

    placed_kpi = {
        "placement_hpwl_mil": round(ec.hpwl(board.comps), 1),
        "placement_overlaps": ec.n_overlaps(board.comps),
        "placement_outside": ec.n_outside(board.comps, board),
    }

    (_unr, _cong), routed, failures = ec.route(
        board, iters=a.iters, layers=a.layers, segment_check=a.segment_check,
        plane_nets=frozenset(a.plane_nets), plane_layer=a.plane_layer)
    plan = ec.plan_from(board, routed)
    kpi = ec.report(board, routed, failures, [], plan)
    out = {**placed_kpi, **kpi}
    out["failures"] = failures

    # The plan and the KPI are DIFFERENT artifacts: writing the report to --out
    # made `clearance_pairs(board, plan)` fail on `plan["tracks"]` being an int.
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(plan, f, indent=1)
    if a.kpi:
        with open(a.kpi, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=1)

    print(json.dumps({
        "segment_check": a.segment_check,
        "iters": a.iters,
        "layers": a.layers,
        "hpwl_mil": placed_kpi["placement_hpwl_mil"],
        "overlaps": placed_kpi["placement_overlaps"],
        "clearance_violations": kpi["clearance_violations"],
        "congestion_cells": kpi["congestion_cells"],
        "unrouted_legs": kpi["unrouted_legs"],
        "nets_unconnected": kpi["nets_unconnected"],
        "vias": kpi["vias"],
        "plane_vias": kpi["plane_vias"],
        "tracks": kpi["tracks"],
        "total_length_mil": kpi["total_length_mil"],
        "diagonal_ratio": kpi["diagonal_ratio"],
        "bus_length_spread_mil": kpi["bus_length_spread_mil"],
    }, ensure_ascii=False, indent=1))
    if a.failures and failures:
        print(json.dumps(failures, ensure_ascii=False, indent=1))
    return 0 if kpi["unrouted_legs"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
