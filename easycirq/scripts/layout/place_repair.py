#!/usr/bin/env python3
"""Move the few parts that make pads unreachable, and nothing else.

`escape_check.py` shows that on RetroCam-02 a handful of pads have no legal track entry
because their part sits too close to a big neighbouring pad (R2 near U4, U2 near L1, U1
near U4).  That is a PLACEMENT fact, and placement is what this toolchain owns - so
instead of reporting it as unfixable, this pass translates only the offending components
by the minimum distance that makes their pads reachable again.

Conservative by construction: a candidate must remove the failure, must not create a new
one, and the smallest translation wins.  Everything else is copied through unchanged.

Usage
-----
    python easycirq/scripts/layout/place_repair.py --dump dump2.json --place ec-placed.json \
        --out ec-placed-repaired.json [--width 5] [--clearance 6] [--step 10] [--radius 100]
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ec_layout as ec  # noqa: E402
import escape_check as esc  # noqa: E402


def _rebuild_nets(board):
    from collections import defaultdict
    board.nets = defaultdict(list)
    for des, c in board.comps.items():
        for p in c["pads"]:
            board.nets[p["net"]].append({**p, "des": des})


def _shift(board, des, dx, dy):
    c = board.comps[des]
    c["x"] += dx
    c["y"] += dy
    for p in c["pads"]:
        p["x"] += dx
        p["y"] += dy
    _rebuild_nets(board)


def repair(dump, placement, width, clearance, step, radius, rounds=3, verbose=True):
    board = ec.Board(dump)
    ec.apply_placement(board, placement)
    moved = {}

    for _r in range(rounds):
        bad = esc.unconnectable(board, width=width, clearance=clearance)
        stuck = sorted({p["des"] for p in bad})
        if not stuck:
            break
        progress = False
        for des in stuck:
            if des not in board.comps:
                continue
            best = None
            n_before = len(bad)
            step_i = max(1, int(round(step)))
            for r in range(step_i, int(radius) + 1, step_i):
                for dx in (-r, 0, r):
                    for dy in (-r, 0, r):
                        if max(abs(dx), abs(dy)) != r:
                            continue
                        _shift(board, des, dx, dy)
                        still = esc.unconnectable(board, width=width, clearance=clearance)
                        # GAPS G12: never buy reachability with a component overlap - the router would
                        # happily route the illegal board (frontier-g first shipped with 2 overlaps).
                        clashes = ec.n_overlaps(board.comps)
                        _shift(board, des, -dx, -dy)
                        if clashes:
                            continue
                        if any(p["des"] == des for p in still):
                            continue
                        if len(still) < n_before:
                            best = (dx, dy)
                            break
                    if best:
                        break
                if best:
                    break
            if best is None:
                if verbose:
                    print("  %-4s: no translation within %d mil fixes it" % (des, radius))
                continue
            _shift(board, des, best[0], best[1])
            moved[des] = best
            progress = True
            if verbose:
                print("  %-4s moved by (%+.0f, %+.0f) mil" % (des, best[0], best[1]))
        if not progress:
            break
    return moved, board


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", required=True)
    ap.add_argument("--place", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--width", type=float, default=ec.TRACE)
    ap.add_argument("--clearance", type=float, default=ec.CLEARANCE)
    ap.add_argument("--step", type=float, default=10.0)
    ap.add_argument("--radius", type=float, default=100.0)
    a = ap.parse_args()

    with open(a.dump, encoding="utf-8") as f:
        dump = json.load(f)
    with open(a.place, encoding="utf-8") as f:
        placement = json.load(f)

    before_board = ec.Board(dump)
    ec.apply_placement(before_board, placement)
    before = len(esc.unconnectable(before_board, width=a.width, clearance=a.clearance))

    print("repairing unreachable pads (width %.1f, clearance %.1f, step %.0f, radius %.0f)" % (
        a.width, a.clearance, a.step, a.radius))
    moved, board = repair(dump, placement, a.width, a.clearance, a.step, a.radius)
    after = len(esc.unconnectable(board, width=a.width, clearance=a.clearance))

    out = json.loads(json.dumps(placement))
    for des, (dx, dy) in moved.items():
        out[des]["x"] = float(out[des]["x"]) + dx
        out[des]["y"] = float(out[des]["y"]) + dy
    print("\nmoved %d part(s): %s" % (len(moved), ", ".join(
        "%s(%+.0f,%+.0f)" % (k, v[0], v[1]) for k, v in sorted(moved.items())) or "(none)"))
    print("unreachable pads: %d -> %d" % (before, after))
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    print("wrote %s" % a.out)
    return 0 if not after else 1


if __name__ == "__main__":
    sys.exit(main())


