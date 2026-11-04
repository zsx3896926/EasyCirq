#!/usr/bin/env python3
"""Find the smallest part moves that would make a bus group's wires the same length.

Section 100 measured that routed bus skew is essentially the straight-line spread between the two
ENDS of each group (CAM 192 -> 287 routed, LCD 235 -> 257, SD 193 -> 207).  So the knob for skew is
not the router and not the pin map - it is where those two parts sit.

This tool does a coordinate-descent search over translations of the parts that terminate each bus
group, scoring by the group's geometric spread (max - min straight-line net length), and prints the
moves it would take plus the spread it reaches.  It is a placement BRIEF: no routing, no DRC, no
overlap-free guarantee beyond a simple bounding-box test, and it says nothing about the other KPIs.

MEASURED WARNING (HANDOFF 102): adopting these moves on RetroCam-02 - together with the pad shrink
and a contiguous CAM pin block - took the delivery profile from 0 dead / 0 congestion / clearance 327
to **2 dead / 1 congestion / clearance 393**, and the CAM skew got worse (286.6 -> 434.9) even though
the geometry said it should improve.  Optimising length geometry in isolation moves parts out of the
corridors that made the board routable.  Treat the output as a BOUND on what the geometry allows,
never as a placement to adopt without a full pipeline run.

Usage
-----
    python easycirq/scripts/layout/skew_place.py --dump dump2.json --place placed.json \
        [--groups CAM_D,LCD_,SD_] [--step 20] [--passes 3] [--budget 400]
"""
import argparse
import itertools
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ec_layout as ec  # noqa: E402

DEFAULT_GROUPS = ("CAM_D", "LCD_", "SD_")


def mst_length(points):
    n = len(points)
    if n < 2:
        return 0.0
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    edges = []
    for i, j in itertools.combinations(range(n), 2):
        a, b = points[i], points[j]
        edges.append((math.hypot(a[0] - b[0], a[1] - b[1]), i, j))
    edges.sort()
    total = 0.0
    for d, i, j in edges:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj
            total += d
    return total


def group_spread(nets, pads_by_net):
    """max - min straight-line (MST) length over the nets of one group."""
    lens = {}
    for net in nets:
        pads = pads_by_net.get(net) or []
        if len(pads) < 2:
            continue
        lens[net] = mst_length([(p["x"], p["y"]) for p in pads])
    if len(lens) < 2:
        return 0.0, lens
    return max(lens.values()) - min(lens.values()), lens


def endpoints(board, group):
    """The two components that terminate a bus group (most pads of that group)."""
    count = {}
    for net, pads in board.nets.items():
        if not net.startswith(group):
            continue
        for p in pads:
            count[p["des"]] = count.get(p["des"], 0) + 1
    return [d for d, _ in sorted(count.items(), key=lambda kv: -kv[1])[:2]]


def shift(board, des, dx, dy):
    c = board.comps[des]
    c["x"] += dx
    c["y"] += dy
    for p in c["pads"]:
        p["x"] += dx
        p["y"] += dy
    for net, pads in board.nets.items():
        for p in pads:
            if p["des"] == des:
                p["x"] += dx
                p["y"] += dy


def inside(board, des, margin=20.0):
    c = board.comps[des]
    xs = [p["x"] for p in c["pads"]] or [c["x"]]
    ys = [p["y"] for p in c["pads"]] or [c["y"]]
    return (min(xs) >= margin and min(ys) >= margin
            and max(xs) <= board.w * ec.GRID + margin * 2
            and max(ys) <= board.h * ec.GRID + margin * 2)


def score(board, groups, pads_by_net):
    total = 0.0
    per = {}
    for g in groups:
        nets = [n for n in pads_by_net if n.startswith(g)]
        s, _lens = group_spread(nets, pads_by_net)
        per[g] = s
        total += s
    return total, per


def search(board, groups, step, passes, budget, verbose=True):
    pads_by_net = {n: list(ps) for n, ps in board.nets.items()}
    parts = sorted({d for g in groups for d in endpoints(board, g)})
    best, per = score(board, groups, pads_by_net)
    if verbose:
        print("start spread: %s (total %.0f)" % (
            ", ".join("%s %.0f" % (g, per[g]) for g in groups), best))
    moves = {}
    for p in range(passes):
        improved = False
        for des in parts:
            for dx, dy in ((step, 0), (-step, 0), (0, step), (0, -step),
                           (step, step), (-step, -step), (step, -step), (-step, step)):
                if abs(dx) > budget or abs(dy) > budget:
                    continue
                shift(board, des, dx, dy)
                if not inside(board, des):
                    shift(board, des, -dx, -dy)
                    continue
                cand, cand_per = score(board, groups, pads_by_net)
                if cand < best - 1e-6:
                    best, per = cand, cand_per
                    moves[des] = (moves.get(des, (0, 0))[0] + dx, moves.get(des, (0, 0))[1] + dy)
                    improved = True
                    if verbose:
                        print("  pass %d: %-4s %+d,%+d -> total %.0f (%s)" % (
                            p + 1, des, dx, dy, best,
                            ", ".join("%s %.0f" % (g, per[g]) for g in groups)))
                else:
                    shift(board, des, -dx, -dy)
        if not improved:
            break
    return moves, best, per


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", required=True)
    ap.add_argument("--place")
    ap.add_argument("--groups", default=",".join(DEFAULT_GROUPS))
    ap.add_argument("--step", type=float, default=20.0)
    ap.add_argument("--passes", type=int, default=3)
    ap.add_argument("--budget", type=float, default=400.0,
                    help="max |dx|/|dy| per move, mil")
    a = ap.parse_args()

    groups = [g.strip() for g in a.groups.split(",") if g.strip()]
    with open(a.dump, encoding="utf-8") as f:
        board = ec.Board(json.load(f))
    if a.place:
        with open(a.place, encoding="utf-8") as f:
            ec.apply_placement(board, json.load(f))

    moves, total, per = search(board, groups, a.step, a.passes, a.budget)
    print("\npart moves that shrink the geometric spread:")
    for des, (dx, dy) in sorted(moves.items()):
        print("   %-4s (%+.0f, %+.0f) mil" % (des, dx, dy))
    print("final spread: %s (total %.0f)" % (
        ", ".join("%s %.0f" % (g, per[g]) for g in groups), total))
    print("\nThis is a placement brief for the SKEW KPI only.  Routing, clearance, pour continuity")
    print("and manufacturability are all unmeasured here - re-run the pipeline before trusting it.")


if __name__ == "__main__":
    main()
