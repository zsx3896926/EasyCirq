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

import ec_layout as ec  # noqa: E402, module-level so a grid switch can rebind it


def use_grid(grid):
    """Rebind the module-level `ec` to the same code at a different GRID constant.

    The routing grid is a first-class parameter now: D6 compares 10 mil against 5 mil,
    and both points have to be produced by the SAME scorecard/gate path, otherwise the
    comparison is between two tools.  `ec_layout.py` keeps its recorded default, so a
    plain run cannot silently change resolution.
    """
    global ec
    if grid is None or float(grid) == float(ec.GRID):
        return ec
    import grid_experiment                       # same source, one rewritten constant
    ec = grid_experiment.load_module(float(grid))
    return ec

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
    # The 10 mil reference point: shared pours with pour step 8 (clearance 511, one
    # pour island).  It was the default until the 5 mil `strict-via` point beat it on
    # the gate order; it stays as the fast (~12 min) comparison.
    "frontier-10mil": dict(
        iters=70, layers=4,
        pours=("GND:4", "+3V3:3"), pour_exclusive=False,
        pour_step=8, net_order="small",
        via_relocate=True, best_effort=True, match_lengths=True,
    ),
    # `frontier` is kept as an alias so older commands and notes still work.
    "frontier": dict(
        iters=70, layers=4,
        pours=("GND:4", "+3V3:3"), pour_exclusive=False,
        pour_step=8, net_order="small",
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
    # The best measured point on the gate order (HANDOFF §57): a 5 mil grid with the
    # via discs actually reserved, which is the first configuration that beats the
    # 10 mil baseline on BOTH gated items it used to fail (islands 1 -> 0, clearance
    # 511 -> 453) with zero dead legs.  Run it as `--grid 5 --profile strict-via`.
    "strict-via": dict(
        grid=5, iters=70, layers=4,
        pours=("GND:4", "+3V3:3"), pour_exclusive=False,
        pour_step=8, net_order="small",
        via_relocate=True, best_effort=True, match_lengths=True,
        via_sites=True, via_margin=6.0, general_budget=56,
    ),
    # Decision support for "add layers": the same pours, two extra signal layers.
    # Only meaningful because every through-hole check now reads the routed stack
    # (`_all_layers`) instead of the four layers it used to hardcode.
    "six-layer": dict(
        iters=70, layers=6,
        pours=("GND:6", "+3V3:5"), pour_exclusive=False,
        pour_step=5, net_order="small",
        via_relocate=True, best_effort=True, match_lengths=True,
    ),
    # The same 6-layer board with the pours on inner layers and the non-bus nets
    # dealt over the layers nothing else owns.  Without a net->layer assignment the
    # 6-layer run above never uses L5/L6 at all, so it cannot answer "does another
    # layer help spacing?" (HANDOFF §43/§44).
    "six-layer-split": dict(
        iters=70, layers=6,
        pours=("GND:2", "+3V3:5"), pour_exclusive=False,
        pour_step=5, net_order="small",
        via_relocate=True, best_effort=True, match_lengths=True,
        layer_spread=True, layer_force=True,
    ),
    # The control for the above: same spreading on the 4-layer board.
    "four-layer-spread": dict(
        iters=70, layers=4,
        pours=("GND:4", "+3V3:3"), pour_exclusive=False,
        pour_step=5, net_order="small",
        via_relocate=True, best_effort=True, match_lengths=True,
        layer_spread=True, layer_force=True,
    ),
}
FRONTIER = PROFILES["strict-via"]      # the best measured point (see DECISIONS D6)


def run(dump_path, place_path, out_dir=None, profile="strict-via"):
    cfg = PROFILES[profile]
    # A profile may carry its own routing grid: "the best point" is a (grid, knobs)
    # pair, and making the caller remember `--grid 5` is how two people end up with
    # two different frontiers from the same command.
    use_grid(cfg.get("grid"))
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
        # Split the pad hits into ones NO routing change can remove (the pad pitch
        # leaves no legal corridor) and ones the router could have avoided.  Without
        # this a red clearance number always reads as "unfinished work" (HANDOFF §48).
        try:
            import forced_spacing
            lo = forced_spacing.classify(board, plan, slack=0.0)
            hi = forced_spacing.classify(board, plan, slack=0.5)
            why["clearance_violations"] += "; pad hits forced by geometry %d-%d of %d" % (
                len(lo["forced"]), len(hi["forced"]), len(lo["forced"]) + len(lo["open"]))
        except Exception as exc:                      # a diagnosis must never fake 0
            why["clearance_violations"] += "; forced/open split unavailable: %s" % exc
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
        via_relocate=cfg.get("via_relocate", True),
        best_effort=cfg.get("best_effort", True),
        via_sites=cfg.get("via_sites", False),
        via_margin=cfg.get("via_margin"),
        bus_budget=cfg.get("bus_budget"),
        general_budget=cfg.get("general_budget"),
        layer_spread=cfg.get("layer_spread", False),
        layer_map=cfg.get("layer_map"),
        layer_force=cfg.get("layer_force", False),
        # Optional knobs used by portfolio.py; a profile that does not name them is
        # unchanged (they default to the frontier's values).
        priority_nets=set(cfg.get("priority_nets") or ()),
        via_cost=cfg.get("via_cost"),
        via_negotiate=cfg.get("via_negotiate", False),
        spacing_hard=cfg.get("spacing_hard", False),
        repair_pass=cfg.get("repair_pass", False),
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
    ap.add_argument("--profile", default="strict-via", choices=sorted(PROFILES))
    ap.add_argument("--iters", type=int,
                    help="negotiation passes (default from the profile, 70); use ~25 to screen")
    ap.add_argument("--grid", type=float,
                    help="routing grid in mil (default: the module constant, 10); see DECISIONS D6")
    ap.add_argument("--best-effort-budget", type=float,
                    help="override how many conflicting segment pairs a least-bad leg may keep")
    ap.add_argument("--via-sites", action="store_true",
                    help="reserve via discs during routing (needed for --via-margin to bite)")
    ap.add_argument("--via-margin", type=float,
                    help="clearance the router enforces around a via, in mil (default 1.0)")
    ap.add_argument("--bus-budget", type=float,
                    help="the same budget for CAM_/LCD_/SD_ nets only (bus corridors first)")
    a = ap.parse_args()
    use_grid(a.grid)
    if (a.best_effort_budget is not None or a.bus_budget is not None
            or a.via_margin is not None or a.via_sites):
        # Overrides go through the profile, not by monkeypatching the module: a run
        # then has every knob it used recorded in one place.
        PROFILES[a.profile] = dict(PROFILES[a.profile])
        if a.best_effort_budget is not None:
            PROFILES[a.profile]["general_budget"] = a.best_effort_budget
        if a.bus_budget is not None:
            PROFILES[a.profile]["bus_budget"] = a.bus_budget
        if a.via_sites:
            PROFILES[a.profile]["via_sites"] = True
        if a.via_margin is not None:
            PROFILES[a.profile]["via_margin"] = a.via_margin
            if a.iters is not None:
                PROFILES[a.profile]["iters"] = a.iters
    kpi, skew, ok, gate_fail, why = run(a.dump, a.place, a.out_dir, profile=a.profile)
    print("profile: `%s`  (layers %d, pours %s%s%s, grid %g mil%s)" % (
        a.profile, PROFILES[a.profile]["layers"], ", ".join(PROFILES[a.profile]["pours"]),
        ", exclusive" if PROFILES[a.profile].get("pour_exclusive") else "",
        ", trimmed" if PROFILES[a.profile].get("pour_trim") else "", ec.GRID,
        ", budget %g%s" % (PROFILES[a.profile]["general_budget"],
                           "" if PROFILES[a.profile].get("bus_budget") is None
                           else ", bus %g" % PROFILES[a.profile]["bus_budget"])
        if PROFILES[a.profile].get("general_budget") is not None
        else ("" if PROFILES[a.profile].get("bus_budget") is None
              else ", bus budget %g" % PROFILES[a.profile]["bus_budget"])))
    print(scorecard(kpi, skew, ok, gate_fail, why))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())



















