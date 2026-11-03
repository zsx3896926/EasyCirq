#!/usr/bin/env python3
"""Name the nets that actually cut a pour, instead of only counting the islands.

`pour_islands` says "the pour is in N pieces".  It does not say which copper did
it, so "0 islands" is not actionable: the trim tried twice to move the long
crossings off the pour layer and the island never changed.  This tool prints, per
cut layer: the region sizes (a 190-cell pocket is not a 1-cell nick), the nets
whose copper separates the pocket, how much track each of them has on that layer,
and which access via is stranded inside it.

Usage
-----
    python easycirq/scripts/layout/pour_cut.py plan.json --dump dump.json --place placed.json
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ec_layout as ec  # noqa: E402


def _load(grid=None):
    """Rebind the module to the grid the plan was routed on (see DECISIONS D6)."""
    global ec
    if grid:
        import grid_experiment
        ec = grid_experiment.load_module(float(grid))
    return ec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("plan")
    ap.add_argument("--dump", required=True)
    ap.add_argument("--grid", type=float,
                    help="routing grid the plan was made on (5 for strict-via; default 10)")
    ap.add_argument("--place")
    ap.add_argument("--clearance", type=float, default=ec.POUR_CLEARANCE)
    a = ap.parse_args()

    _load(a.grid)
    with open(a.dump, encoding="utf-8") as f:
        board = ec.Board(json.load(f))
    if a.place:
        with open(a.place, encoding="utf-8") as f:
            ec.apply_placement(board, json.load(f))
    with open(a.plan, encoding="utf-8") as f:
        plan = json.load(f)

    report = ec.pour_island_report(board, plan, a.clearance)
    if not report:
        print("no pour island: every pour layer is one piece (or has no stranded via)")
        return 0
    for layer in sorted(report):
        info = report[layer]
        print("layer %d: pour is CUT into %d pieces, sizes %s" % (
            layer, len(info["sizes"]), info["sizes"]))
        for net, n in info["cutters"].items():
            segs = [t for t in plan["tracks"]
                    if t["net"] == net and int(t["layer"]) == layer]
            mil = sum(ec.math.hypot(t["x2"] - t["x1"], t["y2"] - t["y1"]) for t in segs)
            print("  cuts: %-12s %3d touching cells, %2d segments, %.0f mil on this layer"
                  % (net, n, len(segs), mil))
        for v in info["dead_vias"]:
            print("  STRANDED access via: net %s at (%.0f, %.0f) - the pad it serves is"
                  " connected to nothing but its own pocket" % (v["net"], v["x"], v["y"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
