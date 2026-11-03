#!/usr/bin/env python3
"""Feasibility check: compute the bounds BEFORE searching (the biggest time saver in this effort).

The RetroCam work spent dozens of runs sweeping parameters whose impossibility was derivable in minutes:
the 8-pin span mismatch between a 19.7 mil connector and 50 mil SoC pads puts a floor under the bus skew
(HANDOFF §123), and 213 of 244 pad-class spacing hits have no legal corridor at all (§93).  This tool
computes those bounds up front and prints a verdict:

    POSSIBLE      - the floor is inside the targets, go and search
    IMPOSSIBLE    - the floor exceeds a target; name what would have to change
    INPUTS INVALID - the capture itself is not manufacturable (pad >= pitch, rule < router via, ...)

Usage
-----
    python easycirq/scripts/layout/feasibility.py --dump d.json --place p.json [--skew-target 50]
"""
import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import footprints as _footprints  # noqa: E402
from dfm import components, hole_mm, pad_of  # noqa: E402

GROUPS = ("CAM_D", "LCD_", "SD_")


def _mst(points):
    """Straight-line MST length of a pad set (2 pads -> the distance itself)."""
    n = len(points)
    if n < 2:
        return 0.0
    edges = []
    for i in range(n):
        for j in range(i + 1, n):
            edges.append((math.hypot(points[i][0] - points[j][0], points[i][1] - points[j][1]), i, j))
    edges.sort()
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    total = 0.0
    for d, i, j in edges:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj
            total += d
    return total


def group_floor(dump, group):
    """(floor_mil, detail) - the smallest achievable max-min length spread for one bus group.

    Two independent geometric reasons make a spread unavoidable:
      * the straight-line lengths of the nets already differ by `spread`;
      * if the two end rows have different spans, the shortest path to the far pad is longer by
        sqrt(D^2 + d^2) - D for span difference d and row distance D.
    The floor is the larger of the two, and it ignores routing detours (so reality is worse).
    """
    nets = {}
    for c in components(dump):
        for i, raw in enumerate(c.get("pads") or []):
            p = pad_of(raw, i)
            if p["net"] and str(p["net"]).startswith(group):
                nets.setdefault(p["net"], []).append((p["x"], p["y"], c.get("designator")))
    if len(nets) < 2:
        return 0.0, {"nets": len(nets), "note": "fewer than two nets in this group"}
    lengths = {n: _mst([(x, y) for x, y, _d in pts]) for n, pts in nets.items()}
    spread = max(lengths.values()) - min(lengths.values())

    # span mismatch bound: compare the extent of the two ends along their dominant axis
    ends = {}
    for n, pts in nets.items():
        for x, y, des in pts:
            ends.setdefault(des, []).append((x, y))
    span_bound = 0.0
    if len(ends) >= 2:
        keys = sorted(ends, key=lambda k: -len(ends[k]))[:2]
        a, b = ends[keys[0]], ends[keys[1]]
        ax = [p[0] for p in a]
        bx = [p[0] for p in b]
        ay = [p[1] for p in a]
        by = [p[1] for p in b]
        span_a = max(max(ax) - min(ax), max(ay) - min(ay))
        span_b = max(max(bx) - min(bx), max(by) - min(by))
        cx_a = (sum(ax) / len(ax), sum(ay) / len(ay))
        cx_b = (sum(bx) / len(bx), sum(by) / len(by))
        D = math.hypot(cx_a[0] - cx_b[0], cx_a[1] - cx_b[1])
        delta = abs(span_a - span_b)
        if D > 1e-6:
            span_bound = math.hypot(D, delta) - D
    return max(spread, span_bound), {"nets": len(nets), "straight_spread": round(spread, 1),
                                     "span_bound": round(span_bound, 1),
                                     "per_net": {k: round(v, 1) for k, v in sorted(lengths.items())}}


def no_corridor_pairs(dump, clearance=6.0, width=5.0):
    """Pad pairs whose copper plus clearance already overlap: no legal track can pass between them."""
    pads = []
    for c in components(dump):
        for i, raw in enumerate(c.get("pads") or []):
            p = pad_of(raw, i)
            pads.append((c.get("designator", "?"), p))
    hits = 0
    for i, (des_a, a) in enumerate(pads):
        for des_b, b in pads[i + 1:]:
            if des_a == des_b:
                continue
            if a["layer"] != 12 and b["layer"] != 12 and a["layer"] != b["layer"]:
                continue
            need = (max(a["w"], a["h"]) + max(b["w"], b["h"])) / 2.0 + width + 2 * clearance
            if math.hypot(a["x"] - b["x"], a["y"] - b["y"]) < need:
                hits += 1
    return hits


def input_problems(dump, rules=None):
    """Physical problems in the capture itself, and review flags that need a human eye.

    Returns (hard, review): `hard` makes every KPI meaningless (pads that physically overlap, a pad
    smaller than its own hole, a board rule below the router's own via).  `review` is for parts whose
    pads are much larger than their neighbours - legitimate for shield/thermal pads, so it is a flag,
    not a verdict (the first version of this check compared pad size to a cross-row pitch and produced
    three false "fused pads" on a real board - HANDOFF §176).
    """
    hard, review = [], []
    for c in components(dump):
        pads = [pad_of(raw, i) for i, raw in enumerate(c.get("pads") or [])]
        des = c.get("designator", "?")
        missing = [p["id"] for p in pads if p["w"] <= 0 or p["h"] <= 0]
        if missing:
            review.append("%s: %d pad(s) have no width/height in the capture (cannot be checked): %s"
                          % (des, len(missing), ", ".join(missing[:6])))
        real = [p for p in pads if p["w"] > 0 and p["h"] > 0]
        for i, a in enumerate(real):
            for b in real[i + 1:]:
                if abs(a["x"] - b["x"]) < (a["w"] + b["w"]) / 2.0 - 1e-6 and \
                        abs(a["y"] - b["y"]) < (a["h"] + b["h"]) / 2.0 - 1e-6:
                    hard.append("%s: pads %s and %s physically overlap" % (des, a["id"], b["id"]))
        for raw, p in zip([r for r in (c.get("pads") or []) if r.get("hole")], pads):
            _kind, dims = hole_mm(raw.get("hole"))
            if not dims or p["w"] <= 0 or p["h"] <= 0:
                continue
            drill_mil = min(dims) / 0.0254
            if min(p["w"], p["h"]) <= drill_mil:
                hard.append("%s.%s: pad %.1f mil is not larger than its hole %.1f mil"
                            % (des, p["id"], min(p["w"], p["h"]), drill_mil))
        widths = sorted({round(p["w"], 1) for p in pads if p["w"] > 0})
        if widths and widths[-1] >= 2.0 * widths[0]:
            review.append("%s: pad widths %.1f..%.1f (large pad may be a shield/thermal pad)"
                          % (des, widths[0], widths[-1]))
    r = (dump.get("result") or dump).get("rules") or rules or {}
    via_d = float(r.get("viaDiameterMil") or 0)
    if via_d and via_d / 2.0 < 12.0:
        hard.append("board rule via radius %.2f mil < the router's 12.01 mil - plan_lint will refuse "
                    "the plan (HANDOFF §172)" % (via_d / 2.0))
    return hard, review


def report(dump, place=None, skew_target=50.0, clearance_target=0):
    print("feasibility check - bounds before search\n")
    problems, review = input_problems(dump)
    rows = []
    for g in GROUPS:
        floor, detail = group_floor(dump, g)
        if detail.get("nets", 0) < 2:
            rows.append((g, 0.0, detail))
            continue
        rows.append((g, floor, detail))
    hits = no_corridor_pairs(dump)

    print("| bus group | nets | straight spread | span bound | floor | target | verdict |")
    print("|---|---|---|---|---|---|---|")
    worst = 0.0
    for g, floor, detail in rows:
        if detail.get("nets", 0) < 2:
            print("| %s | %d | - | - | - | %.0f | no group |" % (g, detail.get("nets", 0), skew_target))
            continue
        worst = max(worst, floor)
        verdict = "ok" if floor < skew_target else "**IMPOSSIBLE**"
        print("| %s | %d | %.1f | %.1f | **%.1f** | %.0f | %s |" % (
            g, detail["nets"], detail["straight_spread"], detail["span_bound"], floor, skew_target, verdict))

    print("\nsingle-corridor conflicts (pad pairs with no legal gap at 5 mil track / 6 mil rule): %d"
          % hits)
    print("clearance target: %d" % clearance_target)

    print("\ninput problems (hard): %s" % ("none" if not problems else ""))
    for p in problems:
        print("  - %s" % p)
    if review:
        print("review flags (not a verdict): ")
        for p in review:
            print("  - %s" % p)

    skew_ok = worst < skew_target
    spacing_ok = hits <= clearance_target
    print()
    if problems:
        print("verdict: **INPUTS INVALID** - fix the capture before measuring anything")
    elif skew_ok and spacing_ok:
        print("verdict: **POSSIBLE** - both floors are inside the targets; a search is worth running")
    else:
        bits = []
        if not skew_ok:
            bits.append("bus skew floor %.1f >= target %.0f (needs a different connector/fanout: "
                        "equalise the two end spans)" % (worst, skew_target))
        if not spacing_ok:
            bits.append("%d pad pairs have no corridor (needs smaller pads, a coarser pitch or a "
                        "larger board)" % hits)
        print("verdict: **IMPOSSIBLE as captured** - " + "; ".join(bits))
        print("Do not sweep parameters: change the part, the pitch or the board, then re-run this check.")
    return {"skew_floor": worst, "corridor_conflicts": hits,
            "input_problems": problems, "review_flags": review,
            "possible": (not problems) and skew_ok and spacing_ok}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", required=True)
    ap.add_argument("--place")
    ap.add_argument("--skew-target", type=float, default=50.0)
    a = ap.parse_args()
    with open(a.dump, encoding="utf-8") as f:
        dump = json.load(f)
    res = report(dump, a.place, a.skew_target)
    return 0 if res["possible"] else 1


if __name__ == "__main__":
    sys.exit(main())
