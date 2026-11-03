#!/usr/bin/env python3
"""Run several routing configurations and pick the best one by the GATE's order.

Why this exists
---------------
Every round so far improved or rejected ONE configuration at a time.  The router is
stochastic in its ordering, and the remaining red lines (clearance, pour islands) are
known to be sensitive to small changes - net order, pour step, via price.  Instead of
arguing about which knob is "obviously" better, this tool measures the candidates
**under one ranking rule** and reports the winner with its numbers.

The ranking rule (documented so it cannot drift silently) is the gate's own order:

    unrouted_legs  ->  nets_unconnected  ->  congestion_cells  ->  pad_layer_gaps
      ->  pour_islands  ->  clearance_violations  ->  skew_max  ->  vias  ->  length

Dead legs first (a missing connection is the whole failure), then open nets, then
overlaps (a short), then an open pad, then pour continuity, then spacing, then bus
skew, then the cost metrics.  Any configuration whose numbers are worse at every
level loses; a configuration that wins on level N is not compared further.

Usage
-----
    python easycirq/scripts/layout/portfolio.py --dump ../retrocam-02/pcb/dump2.json \
        --place ../retrocam-02/pcb/offline/ec-placed.json --jobs 3 --out-dir out/
"""
import argparse
import json
import multiprocessing as mp
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ec_layout as ec  # noqa: E402
import reproduce  # noqa: E402

# Candidates.  Each is a full configuration, not a single flag, so a result can be
# reproduced by name.  They are the knobs that measured differences before:
# net order, pour step, via price, and the pour strategies.
VARIANTS = {
    "base": dict(iters=70, layers=4, pours=("GND:4", "+3V3:3"), pour_step=5,
                 net_order="small"),
    "pour-step-3": dict(iters=70, layers=4, pours=("GND:4", "+3V3:3"), pour_step=3,
                        net_order="small"),
    "pour-step-8": dict(iters=70, layers=4, pours=("GND:4", "+3V3:3"), pour_step=8,
                        net_order="small"),
    # The access-via search radius IS pour_step (`plane_access` + `relocate_pour_vias`),
    # so 5 -> 8 cut clearance 515 -> 511 by letting crowded access vias move further.
    # These test whether that trend is real or noise.
    "pour-step-12": dict(iters=70, layers=4, pours=("GND:4", "+3V3:3"), pour_step=12,
                         net_order="small"),
    "pour-step-16": dict(iters=70, layers=4, pours=("GND:4", "+3V3:3"), pour_step=16,
                         net_order="small"),
    "pour-step-20": dict(iters=70, layers=4, pours=("GND:4", "+3V3:3"), pour_step=20,
                         net_order="small"),
    "bus-first": dict(iters=70, layers=4, pours=("GND:4", "+3V3:3"), pour_step=5,
                      net_order="small", priority_nets=["CAM_D0", "CAM_PCLK", "LCD_CS", "SD_MOSI"]),
    "via-cost-20": dict(iters=70, layers=4, pours=("GND:4", "+3V3:3"), pour_step=5,
                        net_order="small", via_cost=20),
    # Middle of the via-clearance trade the router has never sampled: the two
    # extremes were overlap-only (VIA_BLOCK_MARGIN 1.0, spacing left to the KPI) and
    # full clearance (6.0, measured unroutable).  `via_sites` must be on for the
    # margin to have anything to apply to.
    "via-margin-2": dict(iters=70, layers=4, pours=("GND:4", "+3V3:3"), pour_step=8,
                         net_order="small", via_sites=True, via_margin=2.0),
    "via-margin-3": dict(iters=70, layers=4, pours=("GND:4", "+3V3:3"), pour_step=8,
                         net_order="small", via_sites=True, via_margin=3.0),
    "via-margin-4": dict(iters=70, layers=4, pours=("GND:4", "+3V3:3"), pour_step=8,
                         net_order="small", via_sites=True, via_margin=4.0),
    "exclusive-pour": dict(iters=70, layers=4, pours=("GND:4", "+3V3:3"), pour_step=5,
                           net_order="small", pour_exclusive=True),
}

RANK = ("unrouted_legs", "nets_unconnected", "congestion_cells", "pad_layer_gaps",
        "pour_islands", "clearance_violations", "skew_max", "vias", "total_length_mil")


def rank_key(row):
    return tuple(row["kpi"].get(k) if row["kpi"].get(k) is not None else 0 for k in RANK)


def _worker(job):
    name, cfg, dump, place = job
    with open(dump, encoding="utf-8") as f:
        board = ec.Board(json.load(f))
    with open(place, encoding="utf-8") as f:
        ec.apply_placement(board, json.load(f))
    routed, failures = reproduce._route(board, cfg)
    plan = ec.plan_from(board, routed)
    if cfg.get("match_lengths", True):
        prev = None
        for _ in range(12):
            ec.match_lengths(board, plan, amp=ec.GRID * 8)
            total = sum(ec.quality_metrics(plan)["bus_length_spread_mil"].values())
            if prev is not None and total >= prev:
                break
            prev = total
    kpi = ec.report(board, routed, failures, [], plan)
    skew = kpi["bus_length_spread_mil"]
    ok, gate_fail = ec.gate(kpi)
    return {"variant": name, "kpi": kpi, "skew": skew,
            "skew_max": max(skew.values()) if skew else 0.0,
            "gate_fail": sorted(gate_fail),
            "ok": ok and not any(v >= 50 for v in (skew or {}).values())}


def table(rows):
    head = ("| variant | unrouted | unconn | congestion | pad gaps | islands | "
            "clearance | skew max | vias | length | rank |")
    out = ["|" + "---|" * 11, head]
    order = sorted(rows, key=rank_key)
    for i, r in enumerate(order):
        k = r["kpi"]
        out.append("| %s | %s | %s | %s | %s | %s | %s | %.1f | %s | %.0f | %d |" % (
            r["variant"], k["unrouted_legs"], k["nets_unconnected"],
            k["congestion_cells"], k["pad_layer_gaps"], k["pour_islands"],
            k["clearance_violations"], r["skew_max"], k["vias"],
            k["total_length_mil"] or 0, i + 1))
    out[0], out[1] = head, "|" + "---|" * 11
    return "\n".join(out), order


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", required=True)
    ap.add_argument("--place", required=True)
    ap.add_argument("--variants", default=",".join(VARIANTS))
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--out-dir")
    a = ap.parse_args()

    names = [n.strip() for n in a.variants.split(",") if n.strip()]
    unknown = [n for n in names if n not in VARIANTS]
    if unknown:
        raise SystemExit("unknown variant(s): %s (have: %s)" % (
            ", ".join(unknown), ", ".join(sorted(VARIANTS))))

    jobs = [(n, VARIANTS[n], a.dump, a.place) for n in names]
    print("running %d variant(s) on %d process(es): %s" % (
        len(jobs), min(a.jobs, len(jobs)), ", ".join(names)), flush=True)
    with mp.Pool(min(a.jobs, len(jobs))) as pool:
        rows = pool.map(_worker, jobs)

    text, order = table(rows)
    print()
    print(text)
    print()
    best = order[0]
    print("winner (by gate order): **%s**  gate %s" % (
        best["variant"], "PASS" if best["ok"] else "FAIL (%s)" % ", ".join(best["gate_fail"])))
    if len(order) > 1:
        second = order[1]
        diff = [k for k in RANK if rank_key(best)[RANK.index(k)] != rank_key(second)[RANK.index(k)]]
        print("it beats `%s` first on: %s" % (second["variant"], diff[0] if diff else "(equal)"))

    if a.out_dir:
        os.makedirs(a.out_dir, exist_ok=True)
        path = os.path.join(a.out_dir, "portfolio.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"rank": list(RANK), "rows": order}, f, indent=1)
        with open(os.path.join(a.out_dir, "portfolio.md"), "w", encoding="utf-8") as f:
            f.write(text + "\n")
        print("\nwrote %s and portfolio.md" % path)
    return 0


if __name__ == "__main__":
    sys.exit(main())


