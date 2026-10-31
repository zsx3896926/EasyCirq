#!/usr/bin/env python3
"""Bus capacity report: can a group be routed as parallel lanes, and where?

The equalisation work kept failing for a reason nobody had written down: a "bus"
on this board is not one bundle.  CAM has 16 nets whose destinations sit on TWO
sides of U5 (the top pad row and the right pad column), so it is really two
bundles with different geometry - and the lane count, span and pitch decide
whether a single layer can hold them at all.

This tool answers, per group and per destination side:

  nets, source span, destination span, lanes needed at a given pitch,
  available corridor width, and the verdict.

Usage:
    python tools/layout/bus_capacity.py --dump dump2.json --place ec-placed.json
"""
import argparse
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ec_layout as ec  # noqa: E402


def side_of(pad):
    """Which side of the MCU does this destination pad sit on?"""
    return "top-row" if abs(pad["y"] - 880.1) < 5 else "right-column"


def report(board, groups=("CAM_", "LCD_", "SD_"), pitch=12.0):
    rows = []
    for prefix in groups:
        per_side = defaultdict(list)
        for net in sorted(n for n in board.nets if n.startswith(prefix)):
            pads = board.nets[net]
            src = next((p for p in pads if p["des"] in ("J3", "J4", "J2", "J1")), None)
            dst = next((p for p in pads if p["des"] == "U5"), None)
            if src is None or dst is None:
                continue
            per_side[side_of(dst)].append((net, src, dst))
        for side, members in sorted(per_side.items()):
            srcs = [m[1] for m in members]
            dsts = [m[2] for m in members]
            lanes = len(members)
            need = lanes * pitch
            src_span = max(p["x"] for p in srcs) - min(p["x"] for p in srcs)
            dst_span = (max(p["x"] for p in dsts) - min(p["x"] for p in dsts)
                        if side == "top-row" else
                        max(p["y"] for p in dsts) - min(p["y"] for p in dsts))
            # the corridor has to fit between the two pad fields; use the smaller
            # of the two spans as the honest bottleneck
            corridor = min(src_span, dst_span) if min(src_span, dst_span) > 0 else max(src_span, dst_span)
            # A lane bundle also demands that the two ends agree on ORDER: lanes
            # cannot cross inside a channel.  +1 = same order, -1 = reversed,
            # |rho| < 1 = crossings are unavoidable, and no lane geometry fixes it.
            src_order = [m[0] for m in sorted(members, key=lambda m: m[1]["x"])]
            dst_key = (lambda m: m[2]["x"]) if side == "top-row" else (lambda m: m[2]["y"])
            dst_order = [m[0] for m in sorted(members, key=dst_key)]
            pos = {n: i for i, n in enumerate(dst_order)}
            rho = ec._spearman([float(i) for i in range(len(src_order))],
                               [float(pos[n]) for n in src_order])
            if need <= corridor:
                verdict = "capacity OK, order" if abs(rho) > 0.999 else "capacity OK, but rho=%.2f (crossings)" % rho
            elif need <= 2 * corridor:
                verdict = "needs TWO layers (split %d+%d)" % (
                    lanes // 2, lanes - lanes // 2)
            else:
                verdict = "INFEASIBLE at this pitch"
            rows.append({
                "group": prefix.rstrip("_"), "side": side, "nets": lanes,
                "src_span": round(src_span, 1), "dst_span": round(dst_span, 1),
                "lanes_need": round(need, 1), "corridor": round(corridor, 1),
                "rho": round(rho, 2), "verdict": verdict,
                "members": [m[0] for m in members],
            })
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", required=True)
    ap.add_argument("--place", required=True)
    ap.add_argument("--pitch", type=float, default=12.0)
    a = ap.parse_args()
    with open(a.dump, encoding="utf-8") as f:
        board = ec.Board(json.load(f))
    with open(a.place, encoding="utf-8") as f:
        ec.apply_placement(board, json.load(f))

    print("| group | dest side | nets | src span | dst span | lanes need | corridor | rho | verdict |")
    print("|---|---|---|---|---|---|---|---|---|")
    for r in report(board, pitch=a.pitch):
        print("| %s | %s | %d | %.1f | %.1f | %.1f | %.1f | %.2f | %s |" % (
            r["group"], r["side"], r["nets"], r["src_span"], r["dst_span"],
            r["lanes_need"], r["corridor"], r["rho"], r["verdict"]))
        print("    members: %s" % ", ".join(r["members"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())


