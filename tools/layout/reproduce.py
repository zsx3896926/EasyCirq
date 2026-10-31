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

# Named presets.  Two of them are the branches of the pour decision (D2 in
# DECISIONS.md) and one is the stackup branch (D1), so whichever way the engineer
# decides, the choice is one command and the numbers come out comparable.
PROFILES = {
    # Trimmed pour.  Measured twice: without a spacing guard the trim bought its
    # zero islands with 130 track/track hits, and WITH the guard every re-route is
    # rejected, so this profile is now byte-identical to `shared-pour`.  Kept as a
    # recorded dead end - do not re-try it without a layer-aware re-route.
    "trim-pour": dict(
        iters=70, layers=4,
        pours=("GND:4", "+3V3:3"), pour_exclusive=False, pour_trim=True,
        pour_step=5, net_order="small",
        via_relocate=True, best_effort=True, match_lengths=True,
    ),
    # The measured frontier: pours share their layers with signals.
    "shared-pour": dict(
        iters=70, layers=4,
        pours=("GND:4", "+3V3:3"), pour_exclusive=False,
        pour_step=5, net_order="small",
        via_relocate=True, best_effort=True, match_lengths=True,
    ),
    # Pour layers belong to the pour: whole ground, best clearance so far (153),
    # at the price of four open legs because both inner layers are gone.
    "exclusive-pour": dict(
        iters=70, layers=4,
        pours=("GND:4", "+3V3:3"), pour_exclusive=True,
        pour_step=5, net_order="small",
        via_relocate=True, best_effort=True, match_lengths=True,
    ),
    # If the board really is 2-layer (D1): only the bottom layer can be poured.
    "two-layer": dict(
        iters=70, layers=2,
        pours=("GND:2",), pour_exclusive=False,
        pour_step=5, net_order="small",
        via_relocate=True, best_effort=True, match_lengths=True,
    ),
}
FRONTIER = PROFILES["shared-pour"]


def run(dump_path, place_path, out_dir=None, profile="shared-pour"):
    cfg = PROFILES[profile]
    with open(dump_path, encoding="utf-8") as f:
        board = ec.Board(json.load(f))
    with open(place_path, encoding="utf-8") as f:
        ec.apply_placement(board, json.load(f))

    routed, failures = _route(board, cfg)
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
        br = ec.clearance_breakdown(board, plan, sample_limit=0)["counts"]
        why["clearance_violations"] = "implementation: %d track/track, %d via/track, " \
            "%d via/pad, %d track/pad" % (br.get("track_track", 0), br.get("via_track", 0),
                                          br.get("via_pad", 0), br.get("track_pad", 0))
    if kpi["pour_islands"]:
        rep = ec.pour_island_report(board, plan)
        bits = []
        for layer, info in sorted(rep.items()):
            cut = ", ".join("%s(%d)" % (n, c) for n, c in list(info["cutters"].items())[:4])
            bits.append("L%d cut into %s cells by %s; %d access via(s) stranded"
                        % (layer, "+".join(str(s) for s in info["sizes"][:2]), cut,
                           len(info["dead_vias"])))
        why["pour_islands"] = "design conflict: " + ("; ".join(bits) if bits
                                                     else "island with no movable via")

    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, "plan.json"), "w", encoding="utf-8") as f:
            json.dump(plan, f, indent=1)
        with open(os.path.join(out_dir, "kpi.json"), "w", encoding="utf-8") as f:
            json.dump(kpi, f, indent=1)
    return kpi, skew, ok, gate_fail, why


def _route(board, cfg):
    (_unr, _cong), routed, failures = ec.route(
        board, iters=cfg["iters"], layers=cfg["layers"],
        segment_check=True,
        plane_nets=frozenset(), plane_layer=None,
        pour_specs=list(cfg["pours"]), pour_step=cfg["pour_step"],
        pour_exclusive=cfg.get("pour_exclusive", False),
        pour_trim=cfg.get("pour_trim", False),
        net_order=cfg["net_order"],
        via_relocate=cfg["via_relocate"],
        best_effort=cfg["best_effort"],
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
    ap.add_argument("--profile", default="shared-pour", choices=sorted(PROFILES))
    a = ap.parse_args()
    kpi, skew, ok, gate_fail, why = run(a.dump, a.place, a.out_dir, profile=a.profile)
    print("profile: `%s`  (layers %d, pours %s%s%s)" % (
        a.profile, PROFILES[a.profile]["layers"], ", ".join(PROFILES[a.profile]["pours"]),
        ", exclusive" if PROFILES[a.profile].get("pour_exclusive") else "",
        ", trimmed" if PROFILES[a.profile].get("pour_trim") else ""))
    print(scorecard(kpi, skew, ok, gate_fail, why))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())





