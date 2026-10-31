#!/usr/bin/env python3
"""Split the remaining clearance KPI into kinds an engineer can act on.

The offline gate currently fails on `clearance_violations` alone (366 in the
trimmed-pour frontier).  A single number hides the difference between

  * "the router still has room to yield"  -> implementation work, and
  * "no copper at this via size can satisfy the rule"  -> a board/rule decision,

so this script re-runs the frontier and prints the breakdown from
`ec.clearance_breakdown`, plus the geometry that decides which bucket a hit
belongs to (deficit = need - actual, and whether the via was forced into a pad).

Usage
-----
    python tools/layout/spacing_audit.py --dump ../retrocam-02/pcb/dump2.json \
        --place ../retrocam-02/pcb/offline/ec-placed.json --out-dir /tmp/audit
"""
import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ec_layout as ec  # noqa: E402
import reproduce  # noqa: E402


def _deficits(board, plan):
    """Per-kind deficit statistics: how far from legal each hit is."""
    tracks = plan.get("tracks") or []
    out = {}

    def add(kind, deficit):
        out.setdefault(kind, []).append(deficit)

    for i in range(len(tracks)):
        a = tracks[i]
        for j in range(i + 1, len(tracks)):
            b = tracks[j]
            if a["net"] == b["net"] or a["layer"] != b["layer"]:
                continue
            d = ec.seg_seg(a["x1"], a["y1"], a["x2"], a["y2"],
                           b["x1"], b["y1"], b["x2"], b["y2"])
            need = (a["width"] + b["width"]) / 2 + ec.CLEARANCE - 0.5
            if d < need:
                add("track_track", need - d)
    for v in plan.get("vias") or []:
        for t in tracks:
            if t["net"] == v["net"]:
                continue
            d = ec.seg_seg(v["x"], v["y"], v["x"], v["y"],
                           t["x1"], t["y1"], t["x2"], t["y2"])
            need = ec.VIA_RADIUS + t["width"] / 2 + ec.CLEARANCE - 0.5
            if d < need:
                add("via_track", need - d)
        for pads in board.nets.values():
            for p in pads:
                if p["net"] == v["net"]:
                    continue
                d = math.hypot(p["x"] - v["x"], p["y"] - v["y"])
                need = ec.VIA_RADIUS + max(p["w"], p["h"]) / 2 + ec.CLEARANCE - 0.5
                if d < need:
                    add("via_pad_%s" % ("in_pad" if v.get("in_pad") else "placed"), need - d)
    return {k: {"n": len(v), "min": round(min(v), 2), "max": round(max(v), 2),
                "mean": round(sum(v) / len(v), 2)} for k, v in sorted(out.items())}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", required=True)
    ap.add_argument("--place", required=True)
    ap.add_argument("--out-dir")
    ap.add_argument("--profile", default="trim-pour", choices=sorted(reproduce.PROFILES))
    a = ap.parse_args()

    cfg = reproduce.PROFILES[a.profile]
    with open(a.dump, encoding="utf-8") as f:
        board = ec.Board(json.load(f))
    with open(a.place, encoding="utf-8") as f:
        ec.apply_placement(board, json.load(f))

    routed, failures = reproduce._route(board, cfg)
    plan = ec.plan_from(board, routed)
    if cfg["match_lengths"]:
        prev = None
        for _ in range(12):
            ec.match_lengths(board, plan, amp=ec.GRID * 8)
            total = sum(ec.quality_metrics(plan)["bus_length_spread_mil"].values())
            if prev is not None and total >= prev:
                break
            prev = total

    kpi = ec.report(board, routed, failures, [], plan)
    br = ec.clearance_breakdown(board, plan, sample_limit=int(os.environ.get("SAMPLES", 25)))
    deficits = _deficits(board, plan)

    print("profile: `%s`  clearance KPI (gate): %d   breakdown total: %d" % (
        a.profile, kpi["clearance_violations"], br["total"]))
    if kpi["clearance_violations"] != sum(
            v for k, v in br["counts"].items() if k != "track_pad"):
        print("  NOTE: gate count and breakdown disagree -> the gate is not measuring"
              " what this script measures (investigate before acting).")
    print()
    print("| kind | hits | deficit min/mean/max (mil) |")
    print("|---|---|---|")
    for kind in ("track_track", "via_track", "via_pad", "track_pad",
                 "via_pad_in_pad", "via_pad_placed"):
        c = br["counts"].get(kind, 0)
        d = deficits.get(kind)
        print("| %s | %d | %s |" % (kind, c,
                                    "%.2f / %.2f / %.2f" % (d["min"], d["mean"], d["max"])
                                    if d else "-"))
    print()
    print("samples:")
    for s in br["samples"]:
        print("  " + json.dumps(s, sort_keys=True))

    if a.out_dir:
        os.makedirs(a.out_dir, exist_ok=True)
        with open(os.path.join(a.out_dir, "spacing-audit.json"), "w", encoding="utf-8") as f:
            json.dump({"profile": a.profile, "kpi": kpi, "breakdown": br,
                       "deficits": deficits}, f, indent=1)
        print("\nwrote %s" % os.path.join(a.out_dir, "spacing-audit.json"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
