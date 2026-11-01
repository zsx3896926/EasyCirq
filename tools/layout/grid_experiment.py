#!/usr/bin/env python3
"""Run the frontier on a FINER routing grid, without touching the production module.

Why
---
Every "make the constraint a little stricter" attempt died at the same place: the
router works on a 10 mil grid, so its clearance decisions are quantised in 10 mil
steps (HANDOFF §49: via margins 1..5 all reserve the same 9-cell disc, and the next
step up is the unroutable full-clearance case).  A 5 mil grid halves that quantum.

How
---
The module is loaded from source with `GRID = 10` rewritten to the requested value
and executed in its own namespace, so `ec_layout.py` keeps its recorded default and
the comparison is honest (same code, one constant).  Default arguments that captured
`GRID * 1.5` at import time are re-evaluated in the patched source, so nothing is
silently left at the old resolution.

Usage
-----
    python tools/layout/grid_experiment.py --dump ../retrocam-02/pcb/dump2.json \
        --place ../retrocam-02/pcb/offline/ec-placed.json --grid 5 --out-dir out/grid5
"""
import argparse
import json
import os
import sys
import time
import types

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "ec_layout.py")


def load_module(grid, best_effort_conflicts=None):
    """Compile ec_layout.py with its GRID constant replaced, in a private namespace."""
    with open(SRC, encoding="utf-8") as f:
        src = f.read()
    marker = "\nGRID = 10.0\n"
    if marker not in src:
        raise SystemExit("could not find the GRID constant in ec_layout.py")
    src = src.replace(marker, "\nGRID = %s\n" % grid, 1)
    if best_effort_conflicts is not None:
        # A threshold measured in CELLS is not grid independent: at half the grid a
        # path is twice as long in cells, so the same "2 conflicts" budget rejects
        # legs that were fine before (measured: 34 dead legs at grid 5).
        old = "BEST_EFFORT_MAX_CONFLICTS = 2"
        if old not in src:
            raise SystemExit("could not find BEST_EFFORT_MAX_CONFLICTS in ec_layout.py")
        src = src.replace(old, "BEST_EFFORT_MAX_CONFLICTS = %s" % best_effort_conflicts, 1)
    mod = types.ModuleType("ec_layout_grid%s" % grid)
    mod.__file__ = SRC
    exec(compile(src, SRC, "exec"), mod.__dict__)
    assert mod.GRID == grid, mod.GRID
    return mod


def run(grid, dump, place, iters, pour_step, best_effort_conflicts=None):
    ec = load_module(grid, best_effort_conflicts)
    with open(dump, encoding="utf-8") as f:
        board = ec.Board(json.load(f))
    with open(place, encoding="utf-8") as f:
        ec.apply_placement(board, json.load(f))
    (_unr, _cong), routed, failures = ec.route(
        board, iters=iters, layers=4, segment_check=True,
        plane_nets=frozenset(), plane_layer=None,
        pour_specs=["GND:4", "+3V3:3"], pour_step=pour_step,
        net_order="small", via_relocate=True, best_effort=True)
    plan = ec.plan_from(board, routed)
    prev = None
    for _ in range(12):
        ec.match_lengths(board, plan, amp=ec.GRID * 8)
        total = sum(ec.quality_metrics(plan)["bus_length_spread_mil"].values())
        if prev is not None and total >= prev:
            break
        prev = total
    kpi = ec.report(board, routed, failures, [], plan)
    ok, gate_fail = ec.gate(kpi)
    return board, plan, kpi, sorted(gate_fail)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", required=True)
    ap.add_argument("--place", required=True)
    ap.add_argument("--grid", type=float, default=5)
    ap.add_argument("--iters", type=int, default=70)
    ap.add_argument("--pour-step", type=int, default=8)
    ap.add_argument("--best-effort-conflicts", type=float, default=None,
                    help="override the cell-count budget that gates a best-effort leg")
    ap.add_argument("--out-dir")
    a = ap.parse_args()

    t0 = time.time()
    board, plan, kpi, gate_fail = run(a.grid, a.dump, a.place, a.iters, a.pour_step,
                              a.best_effort_conflicts)
    skew = kpi["bus_length_spread_mil"]
    print("grid %s mil: %dx%d cells, %.1f s" % (
        a.grid, board.w, board.h, time.time() - t0))
    print()
    print("| KPI | value |")
    print("|---|---|")
    for key in ("unrouted_legs", "congestion_cells", "clearance_violations",
                "nets_unconnected", "pad_layer_gaps", "pour_islands", "vias",
                "plane_vias", "vias_in_pad", "tracks", "total_length_mil",
                "diagonal_ratio"):
        print("| %s | %s |" % (key, kpi[key]))
    print("| bus skew CAM/LCD/SD | %.1f / %.1f / %.1f |" % (
        skew.get("CAM_D", 0), skew.get("LCD_", 0), skew.get("SD_", 0)))
    print("| layer length ml | %s |" % kpi.get("layer_length_mil"))
    print()
    print("gate: %s%s" % ("PASS" if not gate_fail else "FAIL", "" if not gate_fail
                          else "  (%s)" % ", ".join(gate_fail)))

    if a.out_dir:
        os.makedirs(a.out_dir, exist_ok=True)
        with open(os.path.join(a.out_dir, "plan.json"), "w", encoding="utf-8") as f:
            json.dump(plan, f, indent=1)
        with open(os.path.join(a.out_dir, "kpi.json"), "w", encoding="utf-8") as f:
            json.dump(kpi, f, indent=1)
        print("\nwrote %s" % a.out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())


