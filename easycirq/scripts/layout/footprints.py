#!/usr/bin/env python3
"""Footprint audit: does each part's own pads make sense? (GAPS G12)

Every big win and every wasted round in this effort traced back to a footprint assumption:
J1/J3 are a 19.7 mil pitch, so a 20 mil wide pad fuses into its neighbour; L1's 165 mil pad walls off
U2's fanout; U5's 50 mil pads are the CAM bus's whole geometric problem.  This tool audits those
properties from the dump alone, so the next person sees them in one table instead of discovering them
one failure at a time.

It flags, per component:
  * **pad wider than the pitch** - physically impossible on that part (the failure of §144)
  * **no soldermask sliver between neighbours** - smaller than the fabricator minimum
  * **very large pad** - a pad over 100 mil on a side is either a power pad or a mistake (L1)
  * the pad pitch itself, which is what the connector trade-offs are made of

Usage
-----
    python easycirq/scripts/layout/footprints.py --dump dump.json [--min-sliver 3.9]
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dfm import components, pad_of  # noqa: E402

LARGE_PAD_MIL = 100.0


def axis_pitch(pads, axis, other, tol=1.0):
    """Smallest centre-to-centre spacing along `axis` between pads that share a row/column.

    Pads must be grouped by `other` first: taking every pad's coordinate at once mixes rows and columns
    and invents absurd pitches (U5 reported 1.2 mil on the y axis when its pads sit in several rows).
    """
    groups = {}
    for p in pads:
        key = round(p[other] / tol) * tol
        groups.setdefault(key, []).append(p[axis])
    best = None
    for vals in groups.values():
        vals = sorted(set(round(v, 3) for v in vals))
        for a, b in zip(vals, vals[1:]):
            gap = b - a
            if gap > 1e-6 and (best is None or gap < best):
                best = gap
    return best


def audit(dump, min_sliver=3.9, large_pad=LARGE_PAD_MIL):
    rows = []
    for c in components(dump):
        pads = [pad_of(raw, i) for i, raw in enumerate(c.get("pads") or [])]
        if not pads:
            continue
        des = c.get("designator", "?")
        pitch_x = axis_pitch(pads, "x", "y")
        pitch_y = axis_pitch(pads, "y", "x")
        widest = max(p["w"] for p in pads)
        tallest = max(p["h"] for p in pads)
        flags = []
        # a pad cannot be wider than the pitch between pad centres
        if pitch_x is not None and widest >= pitch_x - 1e-6:
            flags.append("pad %.1f >= x-pitch %.1f (review: fused if on one row)" % (widest, pitch_x))
        if pitch_y is not None and tallest >= pitch_y - 1e-6:
            flags.append("pad %.1f >= y-pitch %.1f (review: fused if in one column)" % (tallest, pitch_y))
        if max(widest, tallest) >= large_pad:
            flags.append("large pad %.1fx%.1f (review: shield/thermal pad?)" % (widest, tallest))
        worst_gap = None
        for i, a in enumerate(pads):
            for b in pads[i + 1:]:
                dx = abs(a["x"] - b["x"]) - (a["w"] + b["w"]) / 2.0
                dy = abs(a["y"] - b["y"]) - (a["h"] + b["h"]) / 2.0
                gap = max(dx, dy)
                if gap < 0:          # they overlap somewhere: only report the masking case
                    gap = 0.0
                worst_gap = gap if worst_gap is None else min(worst_gap, gap)
        if worst_gap is not None and worst_gap < min_sliver:
            flags.append("copper gap %.1f < sliver %.1f" % (worst_gap, min_sliver))
        rows.append({"designator": des, "pads": len(pads),
                     "pitch_x": pitch_x, "pitch_y": pitch_y,
                     "widest": widest, "tallest": tallest,
                     "worst_gap": worst_gap, "flags": flags})
    return rows


def report(rows, min_sliver):
    bad = [r for r in rows if r["flags"]]
    print("footprint audit - %d components, %d with a flag (min sliver %.1f mil)\n"
          % (len(rows), len(bad), min_sliver))
    print("| part | pads | x-pitch | y-pitch | widest | worst copper gap | flags |")
    print("|---|---|---|---|---|---|---|")
    order = sorted(rows, key=lambda r: (-len(r["flags"]), r["designator"]))
    for r in order:
        px = "-" if r["pitch_x"] is None else "%.1f" % r["pitch_x"]
        py = "-" if r["pitch_y"] is None else "%.1f" % r["pitch_y"]
        gap = "-" if r["worst_gap"] is None else "%.1f" % r["worst_gap"]
        print("| %s | %d | %s | %s | %.1f | %s | %s |" % (
            r["designator"], r["pads"], px, py, r["widest"], gap,
            "; ".join(r["flags"]) or ""))
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", required=True)
    ap.add_argument("--min-sliver", type=float, default=3.9)
    a = ap.parse_args()
    with open(a.dump, encoding="utf-8") as f:
        dump = json.load(f)
    rows = audit(dump, a.min_sliver)
    bad = report(rows, a.min_sliver)
    print("\n%d part(s) flagged. Flags are facts about the footprint, not decisions: a 'large pad' may be "
          "a power pad, but a 'pad >= pitch' cannot be manufactured." % len(bad))
    return 0


if __name__ == "__main__":
    sys.exit(main())
