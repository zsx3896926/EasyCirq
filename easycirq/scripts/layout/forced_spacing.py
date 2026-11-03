#!/usr/bin/env python3
"""How much of the spacing KPI is physically impossible without moving a part?

A clearance number is only actionable if you know which hits a router could have
avoided.  On RetroCam-02 the worst pads are connectors and an inductor, and their
pad pitch decides the answer:

    J3   20 pads, 11.8 x 49.2 mil, pitch 19.7 mil
    U4    8 pads, 13.9 x 57.2 mil, pitch 25.6 mil
    L1    2 pads, 55.1 x 165.4 mil, pitch 145.6 mil
    J1   16 pads, 39.4 x 57.1 mil, pitch 19.7 mil

A track beside a pad must keep `pad_half + track/2 + CLEARANCE` from its centre
(34.6 mil for J3).  Two 19.7 mil-apart pads therefore leave NO legal corridor
between them: a track passing there is inside the rule no matter where it goes.
The tool calls such a hit **forced** - no routing change can remove it, only a
placement or rule change can - and reports the split, so a remaining KPI can be
handed over with the part of it that is a design decision.

Usage
-----
    python easycirq/scripts/layout/forced_spacing.py plan.json --dump dump.json --place placed.json
"""
import argparse
import json
import math
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


def pad_half(p):
    return max(p["w"], p["h"]) / 2.0


def no_corridor_pairs(board, width=ec.TRACE, clearance=ec.CLEARANCE):
    """Pad pairs of one component too close for ANY legal track to pass between them.

    Returns {(des, pad_a, pad_b): gap_mil} for every such pair.  A pair is binding
    when the free gap between the two pad edges is smaller than the corridor a track
    needs (`width + 2*CLEARANCE`).
    """
    out = {}
    for des, c in board.comps.items():
        pads = [p for p in c["pads"] if p.get("net")]
        for i, a in enumerate(pads):
            for b in pads[i + 1:]:
                pitch = math.hypot(a["x"] - b["x"], a["y"] - b["y"])
                gap = pitch - pad_half(a) - pad_half(b)
                if gap < width + 2 * clearance:
                    out[(des, str(a["pad"]), str(b["pad"]))] = round(gap, 1)
    return out


def _between(p, a, b, slack=0.0):
    """Is point `p` inside the rectangle spanned by pads `a` and `b` (with slack)?"""
    x0, x1 = sorted((a["x"], b["x"]))
    y0, y1 = sorted((a["y"], b["y"]))
    margin = slack * max(pad_half(a), pad_half(b))
    return (x0 - margin <= p["x"] <= x1 + margin) and (y0 - margin <= p["y"] <= y1 + margin)


def classify(board, plan, width=ec.TRACE, clearance=ec.CLEARANCE, slack=0.0):
    """Split track/pad and via/pad hits into forced (no corridor exists) and open."""
    nopairs = no_corridor_pairs(board, width, clearance)
    forced_by_comp = {}
    for (des, pa, pb), gap in nopairs.items():
        forced_by_comp.setdefault(des, []).append((pa, pb, gap))
    pads = [p for pads in board.nets.values() for p in pads]
    forced, open_ = [], []
    for t in plan.get("tracks") or []:
        for p in pads:
            if p["net"] == t["net"]:
                continue
            lay = int(p.get("layer") or 1)
            if lay != 12 and lay != t["layer"]:
                continue
            need = t["width"] / 2 + pad_half(p) + clearance - 0.5
            if ec.seg_seg(t["x1"], t["y1"], t["x2"], t["y2"],
                          p["x"], p["y"], p["x"], p["y"]) >= need:
                continue
            hit = {"kind": "track_pad", "net": t["net"], "pad": "%s.%s" % (p["des"], p["pad"])}
            pairs = forced_by_comp.get(p["des"]) or []
            if any(str(p["pad"]) in (pa, pb) and _between(p, *_pads_of(board, p["des"], pa, pb), slack=slack)
                   for pa, pb, _gap in pairs):
                forced.append(hit)
            else:
                open_.append(hit)
    for v in plan.get("vias") or []:
        for p in pads:
            if p["net"] == v["net"]:
                continue
            need = ec.VIA_RADIUS + pad_half(p) + clearance - 0.5
            if math.hypot(p["x"] - v["x"], p["y"] - v["y"]) >= need:
                continue
            hit = {"kind": "via_pad", "net": v["net"], "pad": "%s.%s" % (p["des"], p["pad"])}
            pairs = forced_by_comp.get(p["des"]) or []
            if any(str(p["pad"]) in (pa, pb)
                   and _between({"x": v["x"], "y": v["y"]},
                                *_pads_of(board, p["des"], pa, pb), slack=slack)
                   for pa, pb, _gap in pairs):
                forced.append(hit)
            else:
                open_.append(hit)
    return {"no_corridor_pairs": {"%s.%s|%s" % k: g for k, g in nopairs.items()},
            "forced": forced, "open": open_}


def _pads_of(board, des, pa, pb):
    pads = {str(p["pad"]): p for p in board.comps[des]["pads"] if p.get("net")}
    return pads[pa], pads[pb]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("plan")
    ap.add_argument("--dump", required=True)
    ap.add_argument("--grid", type=float,
                    help="routing grid the plan was made on (5 for strict-via; default 10)")
    ap.add_argument("--place")
    ap.add_argument("--clearance", type=float, default=ec.CLEARANCE)
    ap.add_argument("--slack", type=float, default=0.0,
                    help="extra margin (x pad half) when deciding the track is BETWEEN the pair")
    a = ap.parse_args()

    _load(a.grid)
    with open(a.dump, encoding="utf-8") as f:
        board = ec.Board(json.load(f))
    if a.place:
        with open(a.place, encoding="utf-8") as f:
            ec.apply_placement(board, json.load(f))
    with open(a.plan, encoding="utf-8") as f:
        plan = json.load(f)

    res = classify(board, plan, clearance=a.clearance, slack=a.slack)
    npairs = res["no_corridor_pairs"]
    print("pad pairs with no legal track corridor between them: %d" % len(npairs))
    by_comp = {}
    for key, gap in npairs.items():
        by_comp.setdefault(key.split(".")[0], 0)
        by_comp[key.split(".")[0]] += 1
    print("  per component: %s" % ", ".join("%s(%d)" % kv for kv in sorted(by_comp.items())))
    print()
    print("| class | hits | meaning |")
    print("|---|---|---|")
    print("| forced | %d | no legal corridor exists; only moving the part or changing the"
          " rule removes it |" % len(res["forced"]))
    print("| open | %d | the router could have avoided it |" % len(res["open"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
