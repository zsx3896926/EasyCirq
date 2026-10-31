#!/usr/bin/env python3
"""One command that reproduces the current best offline layout+routing frontier.

Why this exists
---------------
The handoff's biggest historical gap was that its "best state" could not be
reproduced by any recorded command (see HANDOFF §10.1).  This script is the
answer: the exact pipeline, the exact parameters, one Markdown scorecard, and a
gate verdict.  Any agent can run it and get the same numbers - if they differ,
something in the tree changed.

Usage
-----
    python tools/layout/reproduce.py --dump ../retrocam-02/pcb/dump2.json \
        --place ../retrocam-02/pcb/offline/ec-placed.json --out-dir /tmp/frontier

Prints the scorecard and exits 0 only when the offline gate passes (it does not
today: clearance and bus skew remain).
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ec_layout as ec  # noqa: E402

# The measured frontier configuration (HANDOFF §22-§27).  Changing any of these
# changes the numbers, so they live in one place on purpose.
FRONTIER = dict(
    iters=40,
    layers=4,
    pours=("GND:4", "+3V3:3"),   # area pours: GND on L4, +3V3 on L3
    pour_step=5,
    net_order="small",
    via_relocate=True,
    best_effort=True,
    match_lengths=True,
)


def run(dump_path, place_path, out_dir=None):
    with open(dump_path, encoding="utf-8") as f:
        board = ec.Board(json.load(f))
    with open(place_path, encoding="utf-8") as f:
        ec.apply_placement(board, json.load(f))

    routed, failures = _route(board)
    plan = ec.plan_from(board, routed)
    if FRONTIER["match_lengths"]:
        prev = None
        for _ in range(12):
            ec.match_lengths(board, plan, amp=ec.GRID * 8)
            total = sum(ec.quality_metrics(plan)["bus_length_spread_mil"].values())
            if prev is not None and total >= prev:
                break
            prev = total

    kpi = ec.report(board, routed, failures, [], plan)
    ok, gate_fail = ec.gate(kpi)
    skew = kpi["bus_length_spread_mil"]
    ok = ok and all(v < 50 for v in skew.values())

    # Classify the remaining failures instead of only counting them: a skew that
    # cannot be fixed by any router (pin order disagrees end to end) must read as a
    # design-constraint conflict, not as "not implemented yet".
    why = {}
    if any(v >= 50 for v in skew.values()):
        caps = []
        try:
            import bus_capacity
            caps = bus_capacity.report(board)
        except Exception:
            caps = []
        bad = [c for c in caps if abs(c["rho"]) < 0.99]
        if bad:
            why["bus_skew"] = "design conflict: pin order disagrees (%s)" % ", ".join(
                "%s/%s rho=%.2f" % (c["group"], c["side"], c["rho"]) for c in bad)
        else:
            why["bus_skew"] = "implementation: bundles are geometrically possible"
    if kpi["clearance_violations"]:
        why["clearance_violations"] = "implementation: %d via/track pairs too close" % (
            kpi["clearance_violations"])

    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, "plan.json"), "w", encoding="utf-8") as f:
            json.dump(plan, f, indent=1)
        with open(os.path.join(out_dir, "kpi.json"), "w", encoding="utf-8") as f:
            json.dump(kpi, f, indent=1)
    return kpi, skew, ok, gate_fail, why


def _route(board):
    specs = list(FRONTIER["pours"])
    return _route_with(board, specs)


def _route_with(board, specs):
    (_unr, _cong), routed, failures = ec.route(
        board, iters=FRONTIER["iters"], layers=FRONTIER["layers"],
        segment_check=True,
        plane_nets=frozenset(), plane_layer=None,
        pour_specs=specs, pour_step=FRONTIER["pour_step"],
        net_order=FRONTIER["net_order"],
        via_relocate=FRONTIER["via_relocate"],
        best_effort=FRONTIER["best_effort"],
    )
    return routed, failures


def scorecard(kpi, skew, ok, gate_fail, why=None):
    rows = [
        ("unrouted legs", kpi["unrouted_legs"], "gate"),
        ("congestion cells", kpi["congestion_cells"], "gate"),
        ("clearance violations", kpi["clearance_violations"], "gate"),
        ("unconnected nets", kpi["nets_unconnected"], "gate"),
        ("pad layer gaps", kpi["pad_layer_gaps"], "gate"),
        ("pour islands", kpi["pour_islands"], "gate"),
        ("vias (access / in-pad)", "%d (%d / %d)" % (
            kpi["vias"], kpi["plane_vias"], kpi["vias_in_pad"]), "info"),
        ("tracks", kpi["tracks"], "info"),
        ("total length (mil)", kpi["total_length_mil"], "info"),
        ("45-degree share", kpi["diagonal_ratio"], "info"),
        ("bus skew CAM/LCD/SD (mil)", "%.1f / %.1f / %.1f" % (
            skew.get("CAM_D", 0), skew.get("LCD_", 0), skew.get("SD_", 0)), "gate<50"),
    ]
    out = ["| KPI | value | |", "|---|---|---|"]
    for name, value, kind in rows:
        out.append("| %s | %s | %s |" % (name, value, kind))
    if why:
        out.append("")
        out.append("| failing KPI | classification |")
        out.append("|---|---|")
        for k in sorted(why):
            out.append("| %s | %s |" % (k, why[k]))
    out.append("")
    out.append("**offline gate: %s**%s" % (
        "PASS" if ok else "FAIL",
        "" if ok else "  (failing: %s)" % ", ".join(sorted(
            list(gate_fail) + [g for g in ("bus_skew",) if any(v >= 50 for v in skew.values())]))))
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", required=True)
    ap.add_argument("--place", required=True)
    ap.add_argument("--out-dir")
    a = ap.parse_args()
    kpi, skew, ok, gate_fail, why = run(a.dump, a.place, a.out_dir)
    print(scorecard(kpi, skew, ok, gate_fail, why))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())


