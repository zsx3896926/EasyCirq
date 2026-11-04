#!/usr/bin/env python3
"""Incremental re-route: measure what a dirty-region router would buy, and be explicit about the gap.

The speed plan's item ⑤ is "re-route only the nets a change touched".  The router here has no
seed-plan input: `ec.route()` always routes every net from scratch, so a true incremental run needs a
refactor (accept a partial plan, treat kept copper as an obstacle, merge results).  Rather than ship a
half-working version of that, this tool **measures the upper bound**:

  * `dirty_nets()` - which nets a moved part actually touches (its pads, plus pads within a radius);
  * `estimate()`   - time a full route, then time a route of a board that contains ONLY the dirty nets,
                     and report the ratio plus what the merge would have to preserve.

The merge itself is marked NOT RUN in the output. That is deliberate: a merged plan whose KPI was never
compared with a full re-route is exactly the kind of "faster but different" result this repository rejects
(WORKING-RULES R4/R8).

Usage
-----
    python easycirq/scripts/layout/incremental.py --dump d.json --place p.json --move U5 --dx 50 --dy 0
"""
import argparse
import copy
import json
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import candidates  # noqa: E402
import ec_layout as ec  # noqa: E402
import grid_experiment  # noqa: E402
import normalise  # noqa: E402
import reproduce as rep  # noqa: E402


def components(dump):
    r = dump.get("result") or dump
    return r.get("components") or []


def dirty_nets(dump, part, radius=0.0):
    """Nets owned by `part`, plus (optionally) nets with a pad within `radius` of its pads."""
    target = next((c for c in components(dump) if c.get("designator") == part), None)
    if target is None:
        raise SystemExit("no component %r in the capture" % part)
    mine = set()
    for p in target.get("pads") or []:
        if p.get("net"):
            mine.add(p["net"])
    if radius <= 0:
        return mine
    pts = [(float(p["x"]), float(p["y"])) for p in target.get("pads") or []]
    extra = set()
    for c in components(dump):
        if c.get("designator") == part:
            continue
        for p in c.get("pads") or []:
            if not p.get("net"):
                continue
            px, py = float(p["x"]), float(p["y"])
            if any(math.hypot(px - qx, py - qy) <= radius for qx, qy in pts):
                extra.add(p["net"])
    return mine | extra


def reduced_dump(dump, keep_nets):
    """A copy of the capture containing only the given nets (other pads lose their net)."""
    out = copy.deepcopy(dump)
    for c in components(out):
        for p in c.get("pads") or []:
            if p.get("net") and p["net"] not in keep_nets:
                p["net"] = None
    return out


def _route_once(dump, placement, profile, iters):
    cfg = dict(rep.PROFILES[profile])
    cfg["iters"] = iters
    rep.use_grid(cfg.get("grid"))
    rep.ec = grid_experiment.load_module(float(cfg.get("grid") or 10), constants=cfg.get("constants"))
    board = rep.ec.Board(dump)
    rep.ec.apply_placement(board, placement)
    t0 = time.time()
    routed, fails = rep._route(board, cfg)
    dt = time.time() - t0
    plan = rep.ec.plan_from(board, routed)
    kpi = rep.ec.report(board, routed, fails, [], plan)
    return {"seconds": round(dt, 1), "tracks": len(plan.get("tracks") or []),
            "clearance": kpi.get("clearance_violations"), "nets": len(routed)}


def _route_with(dump, placement, profile, iters, seed_routed=None, only_nets=None):
    """route() with the seed-plan/dirty-net options, returning timing + plan + KPI."""
    cfg = dict(rep.PROFILES[profile])
    cfg["iters"] = iters
    rep.use_grid(cfg.get("grid"))
    rep.ec = grid_experiment.load_module(float(cfg.get("grid") or 10), constants=cfg.get("constants"))
    board = rep.ec.Board(dump)
    rep.ec.apply_placement(board, placement)
    t0 = time.time()
    _score, routed, fails = rep.ec.route(
        board, iters=cfg["iters"], layers=cfg["layers"], segment_check=True,
        plane_nets=frozenset(), plane_layer=None, pour_specs=list(cfg["pours"]),
        pour_step=cfg["pour_step"], pour_exclusive=cfg.get("pour_exclusive", False),
        pour_trim=cfg.get("pour_trim", False), net_order=cfg["net_order"],
        via_relocate=cfg.get("via_relocate", True), best_effort=cfg.get("best_effort", True),
        pad_guard=cfg.get("pad_guard", 0.0), seed_routed=seed_routed, only_nets=only_nets)
    dt = time.time() - t0
    plan = rep.ec.plan_from(board, routed)
    kpi = rep.ec.report(board, routed, fails, [], plan)
    return {"seconds": round(dt, 1), "plan": plan, "kpi": kpi, "routed": routed}


GATE_KEYS = ("unrouted_legs", "congestion_cells", "clearance_violations", "nets_unconnected",
             "pad_layer_gaps", "pour_islands")


def kpi_matches(inc_kpi, full_kpi):
    """Do the two plans produce the same KPI?  This is the acceptance test the objective demands: an
    incremental pass may only be *used* when its KPI equals the full re-route's (HANDOFF §192)."""
    for key in GATE_KEYS:
        if inc_kpi.get(key) != full_kpi.get(key):
            return False
    a = inc_kpi.get("bus_length_spread_mil") or {}
    b = full_kpi.get("bus_length_spread_mil") or {}
    return {k: round(float(v), 3) for k, v in a.items()} == {k: round(float(v), 3) for k, v in b.items()}


def incremental_run(dump, placement, part, dx=0.0, dy=0.0, profile="strict-via-thin", iters=3,
                    radius=0.0):
    """Pre-move route -> move the part -> re-route only the dirty nets -> compare with a full re-route.

    The comparison is the point: an incremental pass that is faster but lands on a worse plan is a result,
    not a win, and it must be shown (HANDOFF §190).
    """
    import copy, hashlib, json as _json
    dump, placement, _off = normalise.apply(dump, placement)
    before = _route_with(dump, placement, profile, iters)          # seed copper
    moved = copy.deepcopy(placement)
    if part in moved:
        moved[part]["x"] = float(moved[part]["x"]) + dx
        moved[part]["y"] = float(moved[part]["y"]) + dy
    nets = dirty_nets(dump, part, radius)

    inc = _route_with(dump, moved, profile, iters, seed_routed=before["routed"], only_nets=nets)
    full = _route_with(dump, moved, profile, iters)
    def digest(p):
        return hashlib.sha256(_json.dumps(p, sort_keys=True).encode()).hexdigest()[:16]
    inc_d, full_d = digest(inc["plan"]), digest(full["plan"])
    equal = kpi_matches(inc["kpi"], full["kpi"])
    return {
        "kpi_equal": equal,
        "accepted": equal,          # the incremental result is only usable when the KPI matches
        "fallback_used": (not equal),
        "part": part, "moved_by": (dx, dy), "dirty_nets": len(nets),
        "incremental": {"seconds": inc["seconds"], "tracks": len(inc["plan"].get("tracks") or []),
                        "clearance": inc["kpi"]["clearance_violations"],
                        "skew": inc["kpi"]["bus_length_spread_mil"], "digest": inc_d},
        "full": {"seconds": full["seconds"], "tracks": len(full["plan"].get("tracks") or []),
                 "clearance": full["kpi"]["clearance_violations"],
                 "skew": full["kpi"]["bus_length_spread_mil"], "digest": full_d},
        "identical_plan": inc_d == full_d,
        "ratio": round(full["seconds"] / inc["seconds"], 2) if inc["seconds"] else None,
    }


def report_run(res):
    print("incremental re-route - part %s moved by (%+.0f, %+.0f) mil, %d dirty nets"
          % (res["part"], res["moved_by"][0], res["moved_by"][1], res["dirty_nets"]))
    print("\n| route | seconds | tracks | clearance | CAM | plan digest |")
    print("|---|---|---|---|---|---|")
    for label in ("incremental", "full"):
        r = res[label]
        print("| %s | **%.1f** | %d | %s | %s | %s |" % (
            label, r["seconds"], r["tracks"], r["clearance"], r["skew"].get("CAM_D"), r["digest"]))
    print("\nidentical plan: **%s** | KPI equal: **%s** | speed-up %.2fx" % (
        res["identical_plan"], res.get("kpi_equal"), res["ratio"] if res["ratio"] else float("nan")))
    if res.get("fallback_used"):
        print("REJECTED as a replacement: the incremental KPI differs from the full re-route's, so the")
        print("supported path falls back to the full result.  The incremental row is kept only as evidence.")
    if not res["identical_plan"]:
        print("The incremental plan differs from the full one - that is expected (kept copper constrains")
        print("the re-route) and it is why the numbers above, not the speed-up, decide whether it is usable.")
    return res


def estimate(dump, placement, part, dx=0.0, dy=0.0, profile="strict-via-thin", iters=3, radius=0.0):
    dump, placement, _off = normalise.apply(dump, placement)
    moved = copy.deepcopy(placement)
    if part in moved:
        moved[part]["x"] = float(moved[part]["x"]) + dx
        moved[part]["y"] = float(moved[part]["y"]) + dy
    nets = dirty_nets(dump, part, radius)

    full = _route_once(dump, moved, profile, iters)
    sub = _route_once(reduced_dump(dump, nets), moved, profile, iters)
    ratio = (full["seconds"] / sub["seconds"]) if sub["seconds"] else float("inf")
    return {"part": part, "moved_by": (dx, dy), "dirty_nets": len(nets),
            "total_nets": full["nets"], "full_seconds": full["seconds"],
            "dirty_seconds": sub["seconds"], "ratio": round(ratio, 2),
            "full": full, "dirty": sub, "dirty_net_names": sorted(nets)}


def report(res):
    print("incremental re-route estimate - part %s moved by (%+.0f, %+.0f) mil"
          % (res["part"], res["moved_by"][0], res["moved_by"][1]))
    print("\n| | nets routed | seconds | tracks | clearance |")
    print("|---|---|---|---|---|")
    print("| full re-route | %d of %d | **%.1f** | %d | %s |" % (
        res["full"]["nets"], res["total_nets"], res["full_seconds"],
        res["full"]["tracks"], res["full"]["clearance"]))
    print("| dirty nets only | %d of %d | **%.1f** | %d | %s |" % (
        res["dirty"]["nets"], res["total_nets"], res["dirty_seconds"],
        res["dirty"]["tracks"], res["dirty"]["clearance"]))
    print("\ndirty nets: %d of %d (%.0f%%) -> upper bound on the speed-up: **%.2fx**"
          % (res["dirty_nets"], res["total_nets"],
             100.0 * res["dirty_nets"] / max(1, res["total_nets"]), res["ratio"]))
    print("dirty: %s" % ", ".join(res["dirty_net_names"][:14])
          + (" ..." if len(res["dirty_net_names"]) > 14 else ""))
    print("\nNOT RUN: the merge itself.  `ec.route()` has no seed-plan input, so a true incremental pass")
    print("needs the router to accept existing copper as an obstacle and splice the result back in.  Until")
    print("that exists, this number is an UPPER BOUND on the win, not a measured incremental run - and any")
    print("merged plan would have to be checked against a full re-route before it may be quoted (R4/R8).")
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", required=True)
    ap.add_argument("--place", required=True)
    ap.add_argument("--move", required=True, help="designator of the part being moved")
    ap.add_argument("--dx", type=float, default=0.0)
    ap.add_argument("--dy", type=float, default=0.0)
    ap.add_argument("--radius", type=float, default=0.0, help="also treat nets within this radius as dirty")
    ap.add_argument("--profile", default="strict-via-thin")
    ap.add_argument("--iters", type=int, default=3)
    ap.add_argument("--candidate", help="build a named candidate first")
    ap.add_argument("--run", action="store_true",
                    help="also run a REAL incremental re-route and compare it with a full one")
    a = ap.parse_args()
    with open(a.dump, encoding="utf-8") as f:
        dump = json.load(f)
    with open(a.place, encoding="utf-8") as f:
        place = json.load(f)
    if a.candidate:
        dump, place, _prov = candidates.build(a.candidate, dump, place)
    res = estimate(dump, place, a.move, a.dx, a.dy, a.profile, a.iters, a.radius)
    report(res)
    if a.run:
        print()
        report_run(incremental_run(dump, place, a.move, a.dx, a.dy, a.profile, a.iters, a.radius))
    return 0


if __name__ == "__main__":
    sys.exit(main())
