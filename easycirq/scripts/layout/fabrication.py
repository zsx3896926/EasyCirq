#!/usr/bin/env python3
"""Fabrication manifest: what a board house would need, and what it would be made of (GAPS G10).

This tool does the part of "prepare for manufacture" that can be done **offline and honestly**: it reads
the final plan and prints the manifest a fabricator/quotation needs - board size, layer stack, per-layer
object counts, net/pad census, and the assumptions behind the copper weight.  It also lists the checks
that are still NOT RUN, so nobody mistakes a manifest for a Gerber package.

What it does NOT do (explicitly): write Gerber/Excellon files, a BOM, or a placement (CPL) file.  Those
need the EDA execution layer (EasyEDA/`easycirq`), which this session never touched.

Usage
-----
    python easycirq/scripts/layout/fabrication.py --dump dump.json --plan out/fg/plan.json [--layers 4] [--oz 1]
"""
import argparse
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dfm import board_bbox, components, pad_of  # noqa: E402

NOT_RUN = [
    "Gerber (RS-274X) export",
    "Excellon drill file",
    "BOM with LCSC part numbers",
    "placement / CPL file",
    "stackup drawing with impedance coupons",
]


def census(dump):
    pads = []
    for c in components(dump):
        for i, raw in enumerate(c.get("pads") or []):
            p = pad_of(raw, i)
            p["des"] = c.get("designator", "?")
            pads.append(p)
    nets = defaultdict(set)
    for p in pads:
        if p["net"]:
            nets[p["net"]].add((p["des"], p["id"]))
    smd = [p for p in pads if p["drill"] <= 0]
    tht = [p for p in pads if p["drill"] > 0]
    return pads, nets, smd, tht


def per_layer(plan):
    out = defaultdict(lambda: {"tracks": 0, "length_mil": 0.0, "vias": 0})
    for t in plan.get("tracks") or []:
        lay = int(t["layer"])
        d = ((t["x2"] - t["x1"]) ** 2 + (t["y2"] - t["y1"]) ** 2) ** 0.5
        out[lay]["tracks"] += 1
        out[lay]["length_mil"] += d
    for v in plan.get("vias") or []:
        # the plan's vias carry no layer span (they are through-hole); only count when the plan says so
        if "layer" not in v and "layer2" not in v:
            out.setdefault(0, {"tracks": 0, "length_mil": 0.0, "vias": 0})["vias"] += 1
            continue
        span = sorted({int(v.get("layer") or 0), int(v.get("layer2") or v.get("layer") or 0)})
        for lay in range(span[0], span[-1] + 1):
            if lay:
                out[lay]["vias"] += 1
    return out


def report(dump, plan, layers, oz):
    bb = board_bbox(dump)
    pads, nets, smd, tht = census(dump)
    lay = per_layer(plan or {})
    total_len = sum(v["length_mil"] for v in lay.values())
    total_tracks = sum(v["tracks"] for v in lay.values())

    print("fabrication manifest (offline part only)\n")
    if bb:
        print("board: %.1f x %.1f mil (%.2f x %.2f mm), %d copper layers, outer %g oz"
              % (bb[2] - bb[0], bb[3] - bb[1],
                 (bb[2] - bb[0]) * 0.0254, (bb[3] - bb[1]) * 0.0254, layers, oz))
    print("parts: %d | pads: %d (SMD %d, through-hole %d) | nets: %d"
          % (len(components(dump)), len(pads), len(smd), len(tht), len(nets)))
    print("routed: %d tracks, %.1f mil of copper, %d vias"
          % (total_tracks, total_len, len((plan or {}).get("vias") or [])))

    print("\n| layer | tracks | length (mil) | share | vias touched |")
    print("|---|---|---|---|---|")
    for l in sorted(lay):
        v = lay[l]
        name = "through" if l == 0 else "L%d" % l
        vias = "n/a (through-hole, no span in the plan)" if l == 0 else str(v["vias"])
        print("| %s | %d | %.1f | %.1f%% | %s |" % (
            name, v["tracks"], v["length_mil"],
            100.0 * v["length_mil"] / total_len if total_len else 0.0, vias))

    orphans = sorted(n for n, members in nets.items() if len(members) < 2)
    print("\nsingle-pad nets (check they are intentional test points / mounting): %s"
          % (", ".join(orphans[:12]) + (" ..." if len(orphans) > 12 else "") if orphans else "none"))
    unconnected_pads = [p for p in pads if not p["net"]]
    print("pads with no net: %d" % len(unconnected_pads))

    print("\nstill NOT RUN (need the EDA execution layer - this session never touched it):")
    for item in NOT_RUN:
        print("  [ ] %s" % item)
    return {"tracks": total_tracks, "length_mil": round(total_len, 1),
            "nets": len(nets), "pads": len(pads), "orphans": len(orphans)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", required=True)
    ap.add_argument("--plan")
    ap.add_argument("--layers", type=int, default=4)
    ap.add_argument("--oz", type=float, default=1.0)
    a = ap.parse_args()
    with open(a.dump, encoding="utf-8") as f:
        dump = json.load(f)
    plan = None
    if a.plan:
        with open(a.plan, encoding="utf-8") as f:
            plan = json.load(f)
    report(dump, plan, a.layers, a.oz)
    return 0


if __name__ == "__main__":
    sys.exit(main())
