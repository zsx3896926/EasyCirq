#!/usr/bin/env python3
"""Placement-weight sweep: does a new objective term actually buy routing?

Every row is a full place -> route (segment_check) -> measure cycle on the same
snapshot, and all five mandated metrics are printed together.  A sweep that
reports only HPWL is worthless here: the previous session's ρ term improved
HPWL and made routing worse (unrouted 5 -> 10).

Usage:
    python tools/layout/sweep_placement.py dump2.json --place-dir DIR \
        --configs baseline,face,btn,both,strong,rhoplus --out sweep.json
"""
import argparse
import json
import math
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ec_layout as ec  # noqa: E402

CONFIGS = {
    # name            : (bus_w, face_w, btn_w)
    "baseline": (0.0, 0.0, 0.0),
    "face": (0.0, 1500.0, 0.0),
    "btn": (0.0, 0.0, 800.0),
    "both": (0.0, 1500.0, 800.0),
    "strong": (0.0, 3000.0, 1600.0),
    "btn400": (0.0, 0.0, 400.0),
    "btn1200": (0.0, 0.0, 1200.0),
    "btn2000": (0.0, 0.0, 2000.0),
    "btn800face3000": (0.0, 3000.0, 800.0),
    "rhoplus": (600.0, 1500.0, 800.0),
}


def run_one(dump_path, bus_w, face_w, btn_w, iters, route_iters, layers):
    with open(dump_path, encoding="utf-8") as f:
        board = ec.Board(json.load(f))
    placed = ec.optimize_placement(board, iters=iters, face_w=face_w, btn_w=btn_w, bus_w=bus_w)
    ec.apply_placement(board, placed)
    placement = {
        "hpwl_mil": round(ec.hpwl(board.comps), 1),
        "overlaps": ec.n_overlaps(board.comps),
        "outside": ec.n_outside(board.comps, board),
        "face_penalty": round(ec.escape_face_penalty(board.comps), 3),
        "btn_penalty": round(ec.button_leg_penalty(board.comps), 3),
        "bus_penalty": round(ec.bus_order_penalty(board.comps), 3),
    }
    (_unr, _cong), routed, failures = ec.route(
        board, iters=route_iters, layers=layers, segment_check=True)
    plan = ec.plan_from(board, routed)
    kpi = ec.report(board, routed, failures, [], plan)
    return {"weights": {"bus_w": bus_w, "face_w": face_w, "btn_w": btn_w},
            "placement": placement,
            "routing": {k: kpi[k] for k in ("clearance_violations", "congestion_cells",
                                            "unrouted_legs", "nets_unconnected", "vias",
                                            "tracks", "total_length_mil", "diagonal_ratio",
                                            "bus_length_spread_mil")},
            "failures": failures,
            "placed": placed}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dump")
    ap.add_argument("--configs", default="baseline,face,btn,both,strong,rhoplus")
    ap.add_argument("--iters", type=int, default=40000)
    ap.add_argument("--route-iters", dest="route_iters", type=int, default=20)
    ap.add_argument("--layers", type=int, default=4)
    ap.add_argument("--out")
    a = ap.parse_args()

    rows = []
    for name in [c.strip() for c in a.configs.split(",") if c.strip()]:
        bus_w, face_w, btn_w = CONFIGS[name]
        row = run_one(a.dump, bus_w, face_w, btn_w, a.iters, a.route_iters, a.layers)
        row["config"] = name
        rows.append(row)
        r = row["routing"]
        p = row["placement"]
        print("%-9s hpwl %7.0f ovl %d | clear %2d cong %2d unrouted %2d unconn %2d vias %3d "
              "| face %.3f btn %.3f bus %.3f | spread %s" % (
                  name, p["hpwl_mil"], p["overlaps"], r["clearance_violations"],
                  r["congestion_cells"], r["unrouted_legs"], r["nets_unconnected"],
                  r["vias"], p["face_penalty"], p["btn_penalty"], p["bus_penalty"],
                  r["bus_length_spread_mil"]), flush=True)
        for f in row["failures"]:
            print("          dead leg: %s %s<->%s" % (f["net"], f["a"], f["b"]), flush=True)

    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(rows, f, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
