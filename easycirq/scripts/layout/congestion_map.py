#!/usr/bin/env python3
"""Where do the spacing violations actually sit, and what predicts that place?

`spacing_audit.py` says how many and of what kind; this says WHERE, and then checks the
two cheap geometric proxies a placement optimiser could use:

  * pads in the tile            - a static property of the placement
  * net legs crossing the tile  - routing demand, independent of the router's choices

Measured on the frontier plan (thin-10mil): violations vs pads per 200 mil tile gives
Spearman +0.77 and vs legs crossing +0.64, i.e. the proxies DO locate the trouble.  But
their board-level sum does NOT rank whole placements the same way the routed KPI does
(HANDOFF §73) - so a congestion-driven placement objective would have to be verified per
candidate, not assumed.

Usage
-----
    python easycirq/scripts/layout/congestion_map.py plan.json --dump dump2.json --place placed.json \
        [--tile 200] [--top 10] [--grid 10]
"""
import argparse
import json
import math
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ec_layout as ec  # noqa: E402


def _load(grid=None):
    global ec
    if grid:
        import grid_experiment
        ec = grid_experiment.load_module(float(grid))
    return ec


def spearman(xs, ys):
    n = len(xs)
    if n < 2:
        return 0.0

    def rank(v):
        order = sorted(range(n), key=lambda i: v[i])
        r = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r

    rx, ry = rank(xs), rank(ys)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return num / den if den else 0.0


def analyse(board, plan, tile=200.0):
    def cell(x, y):
        return (int(x // tile), int(y // tile))

    pads = [p for pads in board.nets.values() for p in pads]
    viol, padcnt, legcnt = Counter(), Counter(), Counter()
    for t in plan.get("tracks") or []:
        for p in pads:
            if p["net"] == t["net"]:
                continue
            lay = int(p.get("layer") or 1)
            if lay != 12 and lay != t["layer"]:
                continue
            need = t["width"] / 2 + max(p["w"], p["h"]) / 2 + ec.CLEARANCE - 0.5
            if ec.seg_seg(t["x1"], t["y1"], t["x2"], t["y2"], p["x"], p["y"], p["x"], p["y"]) < need:
                viol[cell(p["x"], p["y"])] += 1
    for v in plan.get("vias") or []:
        for p in pads:
            if p["net"] == v["net"]:
                continue
            need = ec.VIA_RADIUS + max(p["w"], p["h"]) / 2 + ec.CLEARANCE - 0.5
            if math.hypot(p["x"] - v["x"], p["y"] - v["y"]) < need:
                viol[cell(p["x"], p["y"])] += 1
    for p in pads:
        padcnt[cell(p["x"], p["y"])] += 1
    for net, ps in board.nets.items():
        if len(ps) < 2:
            continue
        for i, j in ec.mst_edges(ps):
            a, b = ps[i], ps[j]
            steps = max(2, int(math.hypot(b["x"] - a["x"], b["y"] - a["y"]) / 20))
            seen = set()
            for k in range(steps + 1):
                seen.add(cell(a["x"] + (b["x"] - a["x"]) * k / steps,
                              a["y"] + (b["y"] - a["y"]) * k / steps))
            for c in seen:
                legcnt[c] += 1
    tiles = sorted(set(list(viol) + list(padcnt) + list(legcnt)))
    ys = [viol.get(t, 0) for t in tiles]
    return {"tiles": tiles, "violations": viol, "pads": padcnt, "legs": legcnt,
            "rho_pads": spearman([padcnt.get(t, 0) for t in tiles], ys),
            "rho_legs": spearman([legcnt.get(t, 0) for t in tiles], ys),
            "pressure": sum(legcnt.get(t, 0) * padcnt.get(t, 0) for t in tiles)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("plan")
    ap.add_argument("--dump", required=True)
    ap.add_argument("--place")
    ap.add_argument("--grid", type=float, default=None,
                    help="routing grid the plan was made on (5 for strict-via, else 10)")
    ap.add_argument("--tile", type=float, default=200.0)
    ap.add_argument("--top", type=int, default=10)
    a = ap.parse_args()

    _load(a.grid)
    with open(a.dump, encoding="utf-8") as f:
        board = ec.Board(json.load(f))
    if a.place:
        with open(a.place, encoding="utf-8") as f:
            ec.apply_placement(board, json.load(f))
    with open(a.plan, encoding="utf-8") as f:
        plan = json.load(f)

    res = analyse(board, plan, a.tile)
    total = sum(res["violations"].values())
    print("tile %.0f mil: %d hit(s) spread over %d tile(s)" % (
        a.tile, total, len(res["violations"])))
    print("spearman(hits, pads in tile) = %+.2f   spearman(hits, legs crossing) = %+.2f" % (
        res["rho_pads"], res["rho_legs"]))
    print("board pressure (sum legs*pads) = %d" % res["pressure"])
    print()
    print("| tile (x, y) | hits | pads | legs |")
    print("|---|---|---|---|")
    worst = sorted(res["violations"].items(), key=lambda kv: -kv[1])[:a.top]
    for c, n in worst:
        print("| (%d, %d) | %d | %d | %d |" % (
            c[0], c[1], n, res["pads"].get(c, 0), res["legs"].get(c, 0)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
