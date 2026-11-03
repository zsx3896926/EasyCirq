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
    python easycirq/scripts/layout/spacing_audit.py --dump ../retrocam-02/pcb/dump2.json \
        --place ../retrocam-02/pcb/offline/ec-placed.json --out-dir /tmp/audit
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
import reproduce  # noqa: E402

from collections import Counter  # noqa: E402


def group_violations(board, plan, top=10):
    """Who is involved in every spacing hit, so a red KPI has an owner.

    `clearance_breakdown` says how many and of what kind; this says WHICH nets and
    WHICH pads.  On RetroCam-02 that changes the story: only 15 of 225 track/pad hits
    come from pour stubs, the rest are signal tracks crowding the connectors
    (J3/J1/U4) and L1's pads - an escape/placement problem, not a pour bug.
    """
    pads = [p for pads in board.nets.values() for p in pads]
    track_net, violated_pad, pairs = Counter(), Counter(), Counter()
    via_net, via_on_pad = Counter(), Counter()
    for t in plan.get("tracks") or []:
        for p in pads:
            if p["net"] == t["net"]:
                continue
            lay = int(p.get("layer") or 1)
            if lay != 12 and lay != t["layer"]:      # 12 == through-hole
                continue
            need = t["width"] / 2 + max(p["w"], p["h"]) / 2 + ec.CLEARANCE - 0.5
            if ec.seg_seg(t["x1"], t["y1"], t["x2"], t["y2"],
                          p["x"], p["y"], p["x"], p["y"]) < need:
                track_net[t["net"]] += 1
                violated_pad["%s.%s" % (p.get("des"), p.get("pad"))] += 1
                pairs["%s -> %s.%s" % (t["net"], p.get("des"), p.get("pad"))] += 1
    for v in plan.get("vias") or []:
        for t in plan.get("tracks") or []:
            if t["net"] == v["net"]:
                continue
            need = ec.VIA_RADIUS + t["width"] / 2 + ec.CLEARANCE - 0.5
            if ec.seg_seg(v["x"], v["y"], v["x"], v["y"],
                          t["x1"], t["y1"], t["x2"], t["y2"]) < need:
                via_net[v["net"]] += 1
        for p in pads:
            if p["net"] == v["net"]:
                continue
            need = ec.VIA_RADIUS + max(p["w"], p["h"]) / 2 + ec.CLEARANCE - 0.5
            if math.hypot(p["x"] - v["x"], p["y"] - v["y"]) < need:
                via_net[v["net"]] += 1
                via_on_pad["%s.%s" % (p.get("des"), p.get("pad"))] += 1
    return {"track_pad_by_track_net": track_net.most_common(top),
            "track_pad_violated_pads": violated_pad.most_common(top),
            "track_pad_pairs": pairs.most_common(top),
            "via_hits_by_net": via_net.most_common(top),
            "via_hits_violated_pads": via_on_pad.most_common(top),
            "distinct_track_pad_pairs": len(pairs),
            "track_pad_total": sum(pairs.values())}


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
    ap.add_argument("--grid", type=float,
                    help="routing grid the plan was made on (5 for strict-via; default 10)")
    ap.add_argument("--place", required=True)
    ap.add_argument("--out-dir")
    ap.add_argument("--profile", default="frontier", choices=sorted(reproduce.PROFILES))
    ap.add_argument("--top", type=int, default=10)
    a = ap.parse_args()

    cfg = reproduce.PROFILES[a.profile]
    # A profile may carry its own grid (strict-via -> 5); honour it so the audit
    # measures with the same resolution the plan was routed on.
    _load(a.grid if a.grid is not None
          else reproduce.PROFILES.get(a.profile, {}).get("grid"))
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
    if kpi["clearance_violations"] != br["total"]:
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
    grp = group_violations(board, plan, top=a.top)
    print("track/pad: %d hits over %d distinct (net, pad) pairs" % (
        grp["track_pad_total"], grp["distinct_track_pad_pairs"]))
    print("  by track net : %s" % ", ".join("%s(%d)" % kv for kv in grp["track_pad_by_track_net"]))
    print("  worst pads   : %s" % ", ".join("%s(%d)" % kv for kv in grp["track_pad_violated_pads"]))
    print("via hits by net: %s" % ", ".join("%s(%d)" % kv for kv in grp["via_hits_by_net"]))
    print("via hits on pad: %s" % ", ".join("%s(%d)" % kv for kv in grp["via_hits_violated_pads"]))
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



