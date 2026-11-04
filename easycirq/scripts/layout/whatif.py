#!/usr/bin/env python3
"""What-if harness: does the gate go green once the DESIGN allows it?

The real board cannot pass (HANDOFF §65): five pads have no legal entry at the board's
own 6 mil clearance / 7 mil track, and the bus pin order is uncorrelated so the length
skew cannot be matched.  Both are design facts, not router gaps.

This tool changes exactly those two design inputs on a COPY of the dump, reruns the
measurement, and reports the result.  It answers two questions with numbers instead of
opinion:

  * does relaxing the rule (clearance / track width) actually remove the clearance KPI,
    or is there more geometry in the way?
  * does a correlated bus pin order actually let the router match the lengths?

Nothing here writes to the EDA board and nothing here claims the real board passes: the
output is labelled as a what-if, and the modified dump carries `whatif` markers.

Usage
-----
    python easycirq/scripts/layout/whatif.py --dump ../retrocam-02/pcb/dump2.json \
        --place ../retrocam-02/pcb/offline/ec-placed.json \
        --clearance 2.0 --track 5.0 --repin --grid 10 --out-dir out/whatif
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ec_layout  # noqa: E402
import grid_experiment  # noqa: E402

BUS_PREFIX = ("CAM_", "LCD_", "SD_")


def repin_buses(dump, order="aligned"):
    """Give each bus group a correlated pin order at its two ends.

    For every group the pads are grouped by component, and each component's pads are
    sorted along their dominant axis.  Nets are then reassigned so that rank r at one end
    maps to rank r at the other - i.e. the bundle can be parallel, which is what the
    length-matching step needs.  Returns the number of pads whose net changed.
    """
    r = dump.get("result") or dump
    by_net_ends = {}
    for c in r.get("components") or []:
        for p in c.get("pads") or []:
            net = p.get("net")
            if not net or not str(net).startswith(BUS_PREFIX):
                continue
            by_net_ends.setdefault(net, []).append((c["designator"], p))

    # group -> {designator: [pads]}
    groups = {}
    for net, ends in by_net_ends.items():
        group = next(pre for pre in BUS_PREFIX if str(net).startswith(pre))
        for des, p in ends:
            groups.setdefault(group, {}).setdefault(des, []).append(p)

    changed = 0
    for group, per_des in groups.items():
        parts = [d for d, pads in per_des.items() if len(pads) >= 2]
        if len(parts) < 2:
            continue                     # a group on one component has no skew
        # the two components holding most of the group are the two ends
        parts.sort(key=lambda d: -len(per_des[d]))
        ends = parts[:2]
        ordered = {}
        for des in ends:
            pads = per_des[des]
            xs = [float(p["x"]) for p in pads]
            ys = [float(p["y"]) for p in pads]
            key = (lambda p: float(p["x"])) if (max(xs) - min(xs)) >= (max(ys) - min(ys)) \
                else (lambda p: float(p["y"]))
            ordered[des] = sorted(pads, key=key)
        a, b = ends
        nets_a = [p["net"] for p in ordered[a]]
        nets_b = [p["net"] for p in ordered[b]]
        if len(nets_a) != len(nets_b):
            continue
        if order == "reversed":
            # the two ends may face opposite ways, in which case rank r must map to rank -r
            mapping = list(range(len(nets_a)))[::-1]
        elif order == "nearest":
            # greedy: give each pad at end b the geometry-nearest unused pad at end a, so the
            # bundle stops crossing itself (crossing is what makes one net much longer)
            pool = list(range(len(nets_a)))
            mapping = []
            for p in ordered[b]:
                best = min(pool, key=lambda i: (float(ordered[a][i]["x"]) - float(p["x"])) ** 2
                           + (float(ordered[a][i]["y"]) - float(p["y"])) ** 2)
                mapping.append(best)
                pool.remove(best)
        else:
            mapping = list(range(len(nets_a)))
        for i, p in enumerate(ordered[b]):
            if p["net"] != nets_a[mapping[i]]:
                p["net"] = nets_a[mapping[i]]
                changed += 1
    return changed



def shrink_pads(dump, specs):
    """Pretend a part's pads are smaller, so the clearance floor can be priced before a board change.

    `specs` is a list of "DES=height" (optionally "DES=WxH").  Only pads of that part change; the
    point is to answer "if U1's pads were 20 mil tall, would its BB_VIN pad become reachable, and
    what would the router do with the extra room?" - a simulation, not an edit of the board.
    """
    r = dump.get("result") or dump
    wanted = {}
    for spec in specs:
        des, _, val = spec.partition("=")
        if not des or not val:
            continue
        if "x" in val.lower():
            w, _, h = val.lower().partition("x")
            wanted[des.strip()] = (float(w), float(h))
        else:
            wanted[des.strip()] = (None, float(val))
    changed = 0
    for c in r.get("components") or []:
        des = c.get("designator")
        if des not in wanted:
            continue
        w_new, h_new = wanted[des]
        for p in c.get("pads") or []:
            # NEVER shrink a pad below its own drill: a through-hole pad smaller than its hole cannot be
            # manufactured, and the DFM check caught exactly that on J1's slot pads (HANDOFF §165).
            if p.get("hole"):
                continue
            if w_new:
                p["width"] = w_new
            if h_new:
                p["height"] = h_new
            changed += 1
    r["whatif_pads"] = "pad sizes changed by tools/layout/whatif.py - NOT the real board"
    return changed


def contiguous_repin(dump, group, des, verbose=False):
    """Move a bus group onto a CONTIGUOUS block of pads on one part, then correlate the two ends.

    Section 101 showed the CAM group cannot be equalised by moving parts because U5's CAM pads sit
    in three separate areas of the package (4-7, 12, 17-19).  A pin reassignment - the group's nets
    moving to a contiguous block of pins - is the design answer, so this simulates it: pick the
    tightest window of pads on that part, put the group's nets there, and give the pads that lost a
    net the nets that were displaced.  Every pad keeps exactly one net (a permutation, never an
    overwrite - the first draft duplicated nets and a test caught it, §102).

    Finally rank-match the two ends like `repin_buses`, which is what makes the bundle parallel.
    """
    r = dump.get("result") or dump
    target = next((c for c in r.get("components") or [] if c.get("designator") == des), None)
    if target is None:
        return 0
    pads = target.get("pads") or []
    group_pads = [p for p in pads if str(p.get("net") or "").startswith(group)]
    count = len(group_pads)
    if count < 2 or len(pads) < count:
        return 0
    group_nets = [p.get("net") for p in group_pads]

    # the tightest window in reading order = the most contiguous block of pins
    order = sorted(pads, key=lambda p: (round(float(p["y"]), 1), float(p["x"])))
    best, best_area = None, None
    for i in range(len(order) - count + 1):
        win = order[i:i + count]
        w = max(float(p["x"]) for p in win) - min(float(p["x"]) for p in win)
        h = max(float(p["y"]) for p in win) - min(float(p["y"]) for p in win)
        area = w + h
        if best_area is None or area < best_area:
            best, best_area = win, area
    if best is None:
        return 0

    displaced = [p.get("net") for p in best if p not in group_pads]
    moved_out = [p for p in group_pads if p not in best]
    if len(displaced) != len(moved_out):
        return 0
    changed = 0
    for pad, net in zip(best, group_nets):
        if pad.get("net") != net:
            pad["net"] = net
            changed += 1
    for pad, net in zip(moved_out, displaced):
        if pad.get("net") != net:
            pad["net"] = net
            changed += 1
    if verbose:
        print("   %s: %d net(s) placed on pads %s" % (
            des, count, [p.get("padNumber") for p in best]))
    repin_buses(dump, "aligned")
    return changed

def relax_rules(dump, clearance, track, power, via_diameter):
    r = dump.get("result") or dump
    rules = r.setdefault("rules", {})
    rules["clearanceMil"] = clearance
    rules["trackWidthMil"] = track
    rules["powerWidthMil"] = power
    rules["trackWidthMinMil"] = min(track, rules.get("trackWidthMinMil") or track)
    if via_diameter:
        rules["viaDiameterMil"] = via_diameter
    rules["whatif"] = "design inputs changed by tools/layout/whatif.py - NOT the real board"
    return rules


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", required=True)
    ap.add_argument("--place", required=True)
    ap.add_argument("--clearance", type=float, default=2.0)
    ap.add_argument("--track", type=float, default=5.0)
    ap.add_argument("--power", type=float, default=None)
    ap.add_argument("--via-diameter", type=float, default=None)
    ap.add_argument("--repin", action="store_true")
    ap.add_argument("--contiguous", action="append", default=[], metavar="GROUP@DES",
                    help="move this bus group onto a contiguous pad block on DES")
    ap.add_argument("--repin-order", choices=("aligned", "reversed", "nearest"),
                    default="aligned",
                    help="how bus pads are matched across the two ends")
    ap.add_argument("--shrink-pads", action="append", default=[],
                    metavar="DES=H",
                    help="pretend this part's pads are H mil tall (or WxH), e.g. U1=20")
    ap.add_argument("--via-margin", type=float, default=None,
                    help="via reserve margin in mil (default: the relaxed clearance)")
    ap.add_argument("--grid", type=float, default=10)
    ap.add_argument("--iters", type=int, default=70)
    ap.add_argument("--out-dir")
    a = ap.parse_args()

    with open(a.dump, encoding="utf-8") as f:
        dump = json.load(f)
    changed = repin_buses(dump, a.repin_order) if a.repin else 0
    contig = 0
    for spec in a.contiguous:
        grp, _, desi = spec.partition("@")
        if grp and desi:
            contig += contiguous_repin(dump, grp.strip(), desi.strip(), verbose=True)
    pad_changed = shrink_pads(dump, a.shrink_pads) if a.shrink_pads else 0
    relax_rules(dump, a.clearance, a.track, a.power or a.track * 2,
                a.via_diameter)

    consts = {"CLEARANCE": a.clearance, "TRACE": a.track,
              "POWER_TRACE": a.power or a.track * 2, "BUS_TRACE": a.track * 0.9}
    if a.via_diameter:
        consts["VIA_RADIUS"] = a.via_diameter / 2.0
    ec = grid_experiment.load_module(a.grid, constants=consts)

    board = ec.Board(dump)
    with open(a.place, encoding="utf-8") as f:
        ec.apply_placement(board, json.load(f))

    (_unr, _cong), routed, failures = ec.route(
        board, iters=a.iters, layers=4, segment_check=True,
        plane_nets=frozenset(), plane_layer=None,
        pour_specs=["GND:4", "+3V3:3"], pour_step=8,
        net_order="small", via_relocate=True, best_effort=True,
        via_sites=True,
        # The reserve must follow the RULE being tested: keeping the 6 mil reserve while
        # relaxing the rule to 2 mil blocks vias far harder than the rule does, which
        # produced 12 dead legs in the first what-if run.
        via_margin=(a.via_margin if a.via_margin is not None else a.clearance),
        general_budget=56)
    plan = ec.plan_from(board, routed)
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
    green = ok and all(v < 50 for v in skew.values())

    print("what-if: clearance %.2f mil, track %.1f mil, grid %g mil, %s%s" % (
        a.clearance, a.track, a.grid,
        "%d bus pads re-pinned" % changed if a.repin else "pinout unchanged",
        ", %d pad(s) resized (%s)" % (pad_changed, ", ".join(a.shrink_pads))
        if a.shrink_pads else ""))
    print()
    print("| KPI | value | gate |")
    print("|---|---|---|")
    for key in ("unrouted_legs", "congestion_cells", "clearance_violations",
                "nets_unconnected", "pad_layer_gaps", "pour_islands"):
        print("| %s | %s | %s |" % (key, kpi[key], "ok" if kpi[key] == 0 else "RED"))
    print("| vias (access / in-pad) | %d (%d / %d) | info |" % (
        kpi["vias"], kpi["plane_vias"], kpi["vias_in_pad"]))
    print("| tracks / total length | %d / %.1f | info |" % (
        kpi["tracks"], kpi["total_length_mil"]))
    print("| bus skew CAM/LCD/SD | %.1f / %.1f / %.1f | %s |" % (
        skew.get("CAM_D", 0), skew.get("LCD_", 0), skew.get("SD_", 0),
        "ok" if all(v < 50 for v in skew.values()) else "RED"))
    print()
    print("gate: %s%s" % ("PASS (this what-if board)" if green else "FAIL",
                          "" if green else "  (%s)" % ", ".join(sorted(
                              list(gate_fail) + ([k for k, v in skew.items() if v >= 50]
                                                 if any(v >= 50 for v in skew.values()) else [])))))

    if a.out_dir:
        os.makedirs(a.out_dir, exist_ok=True)
        with open(os.path.join(a.out_dir, "plan.json"), "w", encoding="utf-8") as f:
            json.dump(plan, f, indent=1)
        with open(os.path.join(a.out_dir, "kpi.json"), "w", encoding="utf-8") as f:
            json.dump(kpi, f, indent=1)
        with open(os.path.join(a.out_dir, "whatif.json"), "w", encoding="utf-8") as f:
            json.dump({"clearance": a.clearance, "track": a.track, "grid": a.grid,
                       "repinned_pads": changed, "green": green, "kpi": kpi,
                       "skew": skew}, f, indent=1)
        print("\nwrote %s (plan/kpi/whatif.json)" % a.out_dir)
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())

