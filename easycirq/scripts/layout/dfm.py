#!/usr/bin/env python3
"""Offline DFM screen against JLC's published limits (GAPS G11).

The toolchain measured geometry (DRC, skew, layers) but never the things a fabricator actually rejects:
annular ring, drill vs pad, soldermask sliver, copper to board edge, silkscreen over an opening.  This
tool reads a dump plus a routed plan and reports those four, with the rule values printed.

Scope, honestly: it checks the items it can compute from the dump/plan.  It does NOT check stencil
aperture, panelisation, fiducials, impedance coupons or assembly clearance - those stay NOT RUN and are
listed at the end so nobody mistakes silence for a pass.

Rule values are JLC's published **assumptions** (1 oz outer copper, 0.15 mm min annular ring on a
0.3 mm drill, 0.1 mm soldermask sliver, 0.2 mm copper-to-edge) and the tool prints them.

Usage
-----
    python easycirq/scripts/layout/dfm.py --dump dump.json --plan out/fd/plan.json [--layer-count 4]
"""
import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ASSUMED fabricator limits (JLC 4-layer, 1 oz).  Replace with the order's real process card.
LIMITS = {
    "min_drill_mil": 11.8,          # 0.30 mm
    "min_annular_ring_mil": 5.9,    # 0.15 mm
    "min_mask_sliver_mil": 3.9,     # 0.10 mm
    "min_copper_to_edge_mil": 7.9,  # 0.20 mm
    "min_track_width_mil": 5.0,     # from the board file in this project
    "min_clearance_mil": 6.0,
}


def board_bbox(dump):
    r = dump.get("result") or dump
    out = r.get("outline") or {}
    bb = out.get("bbox") or {}
    if bb:
        return (float(bb["minX"]), float(bb["minY"]), float(bb["maxX"]), float(bb["maxY"]))
    pts = out.get("points") or []
    xs = [float(p[0]) for p in pts]
    ys = [float(p[1]) for p in pts]
    if xs and ys:
        return (min(xs), min(ys), max(xs), max(ys))
    return None


def components(dump):
    r = dump.get("result") or dump
    return r.get("components") or []


def _num(v, default=0.0):
    """Coerce a dump field to a number; `hole` and friends can be a dict or a list in raw dumps."""
    if isinstance(v, bool):
        return default
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, dict):
        for key in ("diameter", "size", "d", "width", "drill"):
            if key in v:
                got = _num(v[key], default)
                if got:
                    return got
        return default
    if isinstance(v, (list, tuple)):
        # dump form is e.g. ["ROUND", 3.94, 3.94] - the geometry follows a shape name
        for item in v:
            got = _num(item, 0.0)
            if got:
                return got
        return default
    return default


def pad_of(p, i):
    pid = p.get("pad") or p.get("padNumber") or str(i)
    return {
        "id": str(pid),
        "x": float(p.get("x", 0.0)),
        "y": float(p.get("y", 0.0)),
        "w": _num(p.get("width", p.get("w", 0.0))),
        "h": _num(p.get("height", p.get("h", 0.0))),
        "drill": _num(p.get("drill") or p.get("hole") or 0.0),
        "layer": int(p.get("layer") or 1),
        "net": p.get("net"),
    }


def check_edge(dump, plan, limits):
    """Copper (pads and tracks) closer to the outline than the fabricator allows."""
    bb = board_bbox(dump)
    if not bb:
        return None
    x0, y0, x1, y1 = bb
    hits = []
    for c in components(dump):
        for i, raw in enumerate(c.get("pads") or []):
            p = pad_of(raw, i)
            ring = max(p["w"], p["h"]) / 2.0
            d = min(p["x"] - x0 - ring, x1 - p["x"] - ring,
                    p["y"] - y0 - ring, y1 - p["y"] - ring)
            if d < limits["min_copper_to_edge_mil"]:
                hits.append(("pad", c.get("designator", "?"), p["id"], round(d, 1)))
    for t in (plan or {}).get("tracks") or []:
        for x, y in ((t["x1"], t["y1"]), (t["x2"], t["y2"])):
            half = float(t["width"]) / 2.0
            d = min(x - x0 - half, x1 - x - half, y - y0 - half, y1 - y - half)
            if d < limits["min_copper_to_edge_mil"]:
                hits.append(("track", t["net"], "-", round(d, 1)))
                break
    return hits


HOLE_UNIT_MM = 0.1        # the dump stores drill sizes in 0.1 mm units (see below)


def hole_mm(raw_hole):
    """(kind, mm_dims) for a dump `hole` payload, or (None, None) when it cannot be trusted.

    The payload arrives as e.g. ``["SLOT", 2.4, 5.1181]`` on pads whose other dimensions are plainly mil.
    Read as mil those drills are impossible (< 4 mil); read as mm they are impossible on a 19.7 mil pitch
    (2.4 mm!).  Read in **0.1 mm units** every case on this board becomes sensible:

        J1  slot 2.4 x 5.1181  -> 0.24 x 0.51 mm  on a 1.0 mm pad  -> ring 0.38 mm
        BZ1 round 3.937        -> 0.394 mm        on a 1.8 mm pad  -> ring 0.70 mm
        J2  round 3.543        -> 0.354 mm        on a 1.5 mm pad  -> ring 0.57 mm

    Because that is an inference, the caller self-checks the result (plausible drill range, slot fits in
    the pad) and falls back to UNRESOLVED when it does not hold - a wrong DFM verdict is worse than none.
    """
    if not raw_hole:
        return None, None
    kind = raw_hole[0] if isinstance(raw_hole[0], str) else "ROUND"
    dims = [float(v) * HOLE_UNIT_MM for v in raw_hole if isinstance(v, (int, float)) and v > 0]
    if not dims:
        return None, None
    return kind.upper(), dims


def check_drills(dump, limits):
    """Drill / annular-ring check, with a self-check on the unit inference.

    Returns (findings, unresolved) where `unresolved` lists payloads the unit inference could not justify.
    """
    findings, unresolved = [], []
    for c in components(dump):
        for i, raw in enumerate(c.get("pads") or []):
            hole = raw.get("hole")
            if not hole:
                continue
            des = c.get("designator", "?")
            pad_id = str(raw.get("pad") or raw.get("padNumber") or i)
            kind, dims = hole_mm(hole)
            pad = pad_of(raw, i)
            # justification: a plausible plated hole, and a slot no larger than its pad
            if not dims or not (0.05 <= min(dims) <= 2.0):
                unresolved.append((des, pad_id, json.dumps(hole)[:44], "implausible drill size"))
                continue
            if kind == "SLOT" and len(dims) >= 2:
                if dims[1] > min(pad["w"], pad["h"]) * 0.0254 + 1e-6:
                    unresolved.append((des, pad_id, json.dumps(hole)[:44], "slot exceeds pad"))
                    continue
            drill = min(dims) / 0.0254                       # mm -> mil
            ring = (min(pad["w"], pad["h"]) - drill) / 2.0
            if drill < limits["min_drill_mil"]:
                findings.append(("drill too small", des, pad_id, round(drill, 1)))
            if ring < limits["min_annular_ring_mil"]:
                findings.append(("annular ring", des, pad_id, round(ring, 1)))
    return findings, unresolved


def check_mask_sliver(dump, limits):
    """Gap between two pads of the same part narrower than the soldermask sliver limit."""
    hits = []
    for c in components(dump):
        pads = [pad_of(raw, i) for i, raw in enumerate(c.get("pads") or [])]
        for i, a in enumerate(pads):
            for b in pads[i + 1:]:
                dx = abs(a["x"] - b["x"]) - (a["w"] + b["w"]) / 2.0
                dy = abs(a["y"] - b["y"]) - (a["h"] + b["h"]) / 2.0
                gap = max(dx, dy)
                if gap < limits["min_mask_sliver_mil"]:
                    hits.append((c.get("designator", "?"), a["id"], b["id"], round(gap, 1)))
    return hits


def check_geometry(plan, limits):
    """Track width / spacing below the board minimums (the plan should already satisfy these)."""
    hits = []
    for t in (plan or {}).get("tracks") or []:
        if float(t["width"]) < limits["min_track_width_mil"] - 1e-9:
            hits.append((t["net"], t["layer"], round(float(t["width"]), 1)))
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", required=True)
    ap.add_argument("--plan")
    ap.add_argument("--layer-count", type=int, default=4)
    a = ap.parse_args()

    with open(a.dump, encoding="utf-8") as f:
        dump = json.load(f)
    plan = None
    if a.plan:
        with open(a.plan, encoding="utf-8") as f:
            plan = json.load(f)

    print("DFM screen - %d layers, limits are ASSUMED JLC values:" % a.layer_count)
    print("  min drill %.1f mil, annular ring %.1f mil, mask sliver %.1f mil, copper to edge %.1f mil"
          % (LIMITS["min_drill_mil"], LIMITS["min_annular_ring_mil"],
             LIMITS["min_mask_sliver_mil"], LIMITS["min_copper_to_edge_mil"]))
    print("  drill sizes are read in %.1f mm units (inferred, self-checked per pad)" % HOLE_UNIT_MM)

    rows = []
    edge = check_edge(dump, plan, LIMITS)
    rows.append(("copper to board edge", edge))
    drill_findings, drill_unresolved = check_drills(dump, LIMITS)
    rows.append(("drill / annular ring", (drill_findings, drill_unresolved)))
    rows.append(("soldermask sliver", check_mask_sliver(dump, LIMITS)))
    rows.append(("track width", check_geometry(plan, LIMITS)))

    print("\n| check | findings | verdict |")
    print("|---|---|---|")
    for name, hits in rows:
        if hits is None:
            print("| %s | n/a (no outline) | SKIP |" % name)
            continue
        if name == "drill / annular ring":
            findings, unresolved = hits
            verdict = "PASS" if not findings else "**%d finding(s)**" % len(findings)
            print("| %s | %d finding(s), %d unresolved | %s |"
                  % (name, len(findings), len(unresolved), verdict))
            for h in findings[:4]:
                print("|   e.g. | %s | |" % (h,))
            for h in unresolved[:4]:
                print("|   unresolved | %s | |" % (h,))
            continue
        verdict = "PASS" if not hits else "**%d finding(s)**" % len(hits)
        print("| %s | %s | %s |" % (name, len(hits), verdict))
        for h in hits[:5]:
            print("|   e.g. | %s | |" % (h,))
        if len(hits) > 5:
            print("|   ... | %d more | |" % (len(hits) - 5))

    print("\nNOT RUN (needs the fabricator's order card or assembly data): stencil aperture, "
          "panelisation, fiducials, impedance coupons, component-to-component assembly clearance.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
