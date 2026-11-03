#!/usr/bin/env python3
"""Turn "this pad has no legal entry" into a concrete footprint/placement brief.

`escape_check.py` says which pads cannot be legally reached; this says what would have to change
for them to be reachable, in the two currencies a designer actually has:

  * **separation** - the centre distance to a blocking pad must grow to N mil (move the part, or
    widen the footprint pitch), or
  * **pad size** - the blocking pad must shrink to S mil for the corridor to open at the CURRENT
    distance.

Each blocking pad is reported separately because these are per-neighbour bounds: satisfying one may
still leave every direction covered by another.  The only way to know a change actually works is to
re-run `escape_check.py` on the changed footprint/placement - this tool is the brief, not the proof.
It also says nothing about manufacturability or about the other KPIs.

Usage
-----
    python easycirq/scripts/layout/pad_escape_spec.py --dump dump2.json --place placed.json \
        [--width 5] [--clearance 6] [--grid 10]
"""
import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ec_layout as ec  # noqa: E402
import escape_check as esc  # noqa: E402


def _load(grid=None):
    global ec
    if grid:
        import grid_experiment
        ec = grid_experiment.load_module(float(grid))
        esc.ec = ec
    return ec


def spec(board, width, clearance):
    bad = esc.unconnectable(board, width=width, clearance=clearance)
    pads = [p for pads in board.nets.values() for p in pads]
    rows = []
    for p in bad:
        r_self = max(p["w"], p["h"]) / 2.0 + width / 2.0 + 1.0
        blockers = []
        for q in pads:
            if q is p:
                continue
            lq, lp = int(q.get("layer") or 1), int(p.get("layer") or 1)
            if lq != 12 and lp != 12 and lq != lp:
                continue
            need = r_self + max(q["w"], q["h"]) / 2.0 + clearance + width / 2.0
            d = math.hypot(q["x"] - p["x"], q["y"] - p["y"])
            if d >= need:
                continue
            # largest size this neighbour could have and still leave a corridor at the CURRENT
            # distance; negative means no amount of shrinking this one neighbour helps
            s_max = 2.0 * (d - r_self - clearance - width / 2.0)
            blockers.append({"des": q["des"], "pad": q["pad"],
                             "size": max(q["w"], q["h"]), "distance": d, "needed": need,
                             "deficit": need - d, "max_size_at_this_distance": s_max})
        blockers.sort(key=lambda b: -b["deficit"])
        rows.append({"des": p["des"], "pad": p["pad"], "net": p["net"],
                     "self_size": max(p["w"], p["h"]), "blockers": blockers})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", required=True)
    ap.add_argument("--place")
    ap.add_argument("--width", type=float, default=5.0)
    ap.add_argument("--clearance", type=float, default=6.0)
    ap.add_argument("--grid", type=float, default=None)
    ap.add_argument("--top", type=int, default=3)
    a = ap.parse_args()

    _load(a.grid)
    with open(a.dump, encoding="utf-8") as f:
        board = ec.Board(json.load(f))
    if a.place:
        with open(a.place, encoding="utf-8") as f:
            ec.apply_placement(board, json.load(f))

    rows = spec(board, a.width, a.clearance)
    print("width %.1f mil, clearance %.1f mil: %d pad(s) with no legal track entry\n" % (
        a.width, a.clearance, len(rows)))
    for row in rows:
        print("%s.%s (net %s, own pad %.1f mil)" % (
            row["des"], row["pad"], row["net"], row["self_size"]))
        for b in row["blockers"][:a.top]:
            if b["max_size_at_this_distance"] <= 0:
                size_txt = "shrinking it cannot help at this distance"
            else:
                size_txt = "or shrink it to <= %.1f mil" % b["max_size_at_this_distance"]
            print("   %-4s.%-3s pad %5.1f mil at %5.1f (needs %5.1f): move apart >= %4.1f mil  %s"
                  % (b["des"], b["pad"], b["size"], b["distance"], b["needed"],
                     b["deficit"], size_txt))
        if len(row["blockers"]) > a.top:
            print("   ... %d more blocking pad(s)" % (len(row["blockers"]) - a.top))
        print()
    print("Per-neighbour bounds only: re-run escape_check.py after changing a footprint or a")
    print("placement, and re-run the pipeline to see what it does to every other KPI.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
