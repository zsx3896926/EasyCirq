#!/usr/bin/env python3
"""Offline current-capacity check (GAPS G8).

The router picks widths for geometry (5 mil minimum, 8.6 mil for power nets), never for **current**.
This tool applies the IPC-2221 chart in closed form

    I = k * dT^0.44 * A^0.725        A = w * t (mil^2), k = 0.048 external / 0.024 internal

to answer two questions per power net: how wide must it be for a given current, and how much current the
copper that was actually routed can carry at a chosen temperature rise.

Currents are the tool's **ASSUMPTION** unless you pass a JSON map of net -> amps; the tool prints which
one it used and never silently mixes them.  Plane returns (GND, +3V3 pours) are not single traces and are
listed separately.

Usage
-----
    python easycirq/scripts/layout/current.py --plan out/fd/plan.json [--amps amps.json] [--dt 10 20]
"""
import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ASSUMED currents (amps) for the RetroCam-02 power nets until the engineer supplies real ones.
ASSUMED_AMPS = {
    "VBUS": 1.0, "VBAT_P": 1.0, "BATT_M": 1.0, "BB_VIN": 1.0,
    "+3V3": 0.5, "VDD_DW": 0.2,
}
PLANE_NETS = ("GND",)
OZ_TO_MIL = 1.37          # 1 oz copper = 1.37 mil


def capacity(area_mil2, dT, external=True):
    """IPC-2221: current (A) a copper cross-section carries for a temperature rise dT (C)."""
    k = 0.048 if external else 0.024
    return k * (dT ** 0.44) * (area_mil2 ** 0.725)


def width_for(current, dT, copper_mil, external=True):
    """Inverse of capacity(): the track width (mil) needed to carry `current` at rise `dT`."""
    k = 0.048 if external else 0.024
    area = (current / (k * (dT ** 0.44))) ** (1.0 / 0.725)
    return area / copper_mil


def plan_power(plan, nets):
    """Per net: minimum width, count, and the layers it uses."""
    out = {}
    for t in plan.get("tracks") or []:
        if t["net"] not in nets:
            continue
        rec = out.setdefault(t["net"], {"min_width": 1e9, "count": 0, "layers": set()})
        rec["min_width"] = min(rec["min_width"], float(t["width"]))
        rec["count"] += 1
        rec["layers"].add(int(t["layer"]))
    return out


def report(plan, amps, dts, source=None):
    nets = set(amps) | set(PLANE_NETS)
    found = plan_power(plan, nets)
    print("current check - IPC-2221 closed form, copper 1 oz outer (%.2f mil)" % OZ_TO_MIL)
    print("currents: %s\n" % (source or
          ("ASSUMED (pass --amps to override)" if amps is ASSUMED_AMPS else "supplied")))
    print("| net | amps | needed width @dT=%.0f C | routed min width | verdict |" % dts[0])
    print("|---|---|---|---|---|")
    rows = []
    for net in sorted(found):
        info = found[net]
        a = amps.get(net)
        if a is None:
            print("| %s | plane/unknown | - | %.1f | info |" % (net, info["min_width"]))
            continue
        need = width_for(a, dts[0], OZ_TO_MIL, external=1 in info["layers"])
        verdict = "ok" if info["min_width"] >= need else "**undersized by %.1fx**" % (need / info["min_width"])
        rows.append((net, a, need, info["min_width"], verdict))
        print("| %s | %.2f | %.1f | %.1f | %s |" % (net, a, need, info["min_width"], verdict))

    print("\nwhat the routed copper can actually carry:")
    print("| net | width | @dT=%.0f C | @dT=%.0f C |" % (dts[0], dts[-1]))
    print("|---|---|---|---|")
    for net in sorted(found):
        info = found[net]
        area = info["min_width"] * OZ_TO_MIL
        ext = 1 in info["layers"]
        print("| %s | %.1f | %.2f A | %.2f A |" % (
            net, info["min_width"], capacity(area, dts[0], ext), capacity(area, dts[-1], ext)))

    for net in PLANE_NETS:
        if net in found:
            print("\n%s is a pour on this board - its current is set by plane copper, not by a track "
                  "width; not checked here." % net)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True)
    ap.add_argument("--amps", help="JSON map net -> amps (overrides the built-in assumption)")
    ap.add_argument("--dt", type=float, nargs="+", default=[10.0, 20.0],
                    help="temperature rises to evaluate (C)")
    a = ap.parse_args()

    with open(a.plan, encoding="utf-8") as f:
        plan = json.load(f)
    amps = ASSUMED_AMPS
    if a.amps:
        with open(a.amps, encoding="utf-8") as f:
            amps = json.load(f)
    rows = report(plan, amps, a.dt, source=("supplied from %s" % a.amps) if a.amps else None)
    bad = [r for r in rows if r[4] != "ok"]
    print("\n%s" % ("all checked nets carry their assumed current" if not bad
                   else "%d net(s) undersized at dT=%.0f C" % (len(bad), a.dt[0])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
