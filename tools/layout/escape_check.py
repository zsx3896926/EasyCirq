#!/usr/bin/env python3
"""Is a pad connectable AT ALL under the board's own rules?

Everything else in this toolchain measures a *layout attempt*: placement, routing, vias.
This asks a question that no router and no placement can change - given the footprint's
pad pitch, the board's clearance rule and the track width, does ANY track exist that can
enter the pad legally?

For pad P the track centre must leave P at some distance r = pad_half + w/2 (+1 mil) and,
at that point, stay at least (neighbour_half + w/2 + clearance) from every neighbour
(any net's pad on the same layer; through-hole pads count on every layer).  If no point
on that ring satisfies all neighbours, P cannot be connected inside the rules: any track
that reaches it violates clearance, so the clearance KPI has a floor above zero.

Usage
-----
    python tools/layout/escape_check.py --dump dump2.json --place ec-placed.json [--grid 5]
"""
import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ec_layout as ec  # noqa: E402


def _load(grid=None):
    """Rebind the module to the grid the placement was made on (see DECISIONS D6)."""
    global ec
    if grid:
        import grid_experiment
        ec = grid_experiment.load_module(float(grid))
    return ec


def pad_half(p):
    return max(p["w"], p["h"]) / 2.0


def unconnectable(board, width=ec.TRACE, clearance=ec.CLEARANCE, samples=180):
    """Pads with no legal track entry angle at all.  Placement-independent."""
    pads = [p for pads in board.nets.values() for p in pads]
    bad = []
    for p in pads:
        lay = int(p.get("layer") or 1)
        r = pad_half(p) + width / 2.0 + 1.0
        ok = False
        for k in range(samples):
            a = 2 * math.pi * k / samples
            qx, qy = p["x"] + r * math.cos(a), p["y"] + r * math.sin(a)
            legal = True
            for n in pads:
                if n is p:
                    continue
                nlay = int(n.get("layer") or 1)
                if nlay != 12 and lay != 12 and nlay != lay:
                    continue                     # other side of the board
                need = pad_half(n) + width / 2.0 + clearance
                if math.hypot(n["x"] - qx, n["y"] - qy) < need:
                    legal = False
                    break
            if legal:
                ok = True
                break
        if not ok:
            bad.append(p)
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", required=True)
    ap.add_argument("--place")
    ap.add_argument("--grid", type=float,
                    help="routing grid the plan uses (5 for strict-via; default 10)")
    ap.add_argument("--width", type=float, default=ec.TRACE)
    ap.add_argument("--clearance", type=float, default=ec.CLEARANCE)
    a = ap.parse_args()

    _load(a.grid)
    with open(a.dump, encoding="utf-8") as f:
        board = ec.Board(json.load(f))
    if a.place:
        with open(a.place, encoding="utf-8") as f:
            ec.apply_placement(board, json.load(f))

    bad = unconnectable(board, a.width, a.clearance)
    total = sum(1 for pads in board.nets.values() for p in pads)
    print("track width %.1f mil, clearance %.2f mil, pads %d" % (
        a.width, a.clearance, total))
    print("pads with NO legal track entry: %d (%.1f %%)" % (
        len(bad), 100.0 * len(bad) / max(1, total)))
    by_des = {}
    for p in bad:
        by_des[p["des"]] = by_des.get(p["des"], 0) + 1
    for des, n in sorted(by_des.items(), key=lambda kv: -kv[1]):
        print("  %-4s %d pad(s)" % (des, n))
    print()
    if bad:
        print("=> the clearance KPI has a floor above zero: these pads cannot be reached")
        print("   without breaking the board's own clearance rule, whatever the router,")
        print("   the placement or the layer count.  Only a rule/part change fixes it.")
    else:
        print("=> every pad has at least one legal entry angle; clearance 0 is not")
        print("   excluded by geometry.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
