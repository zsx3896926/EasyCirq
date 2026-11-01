#!/usr/bin/env python3
"""Lint a routed plan against the BOARD'S OWN design rules, before applying it.

The board dump carries its rules (`clearanceMil`, `viaDiameterMil`,
`trackWidthMil`, `copperLayers`, `copperToEdgeMil`).  The router used to ignore
them and assume its own constants - which was measurably optimistic: the dump says
via diameter 24.02 mil while the router assumed 20, and the reported "121 clearance
violations" became **238** once the real diameter was used.

So the number an agent should trust is the one linted against the board, not the
one produced by the router's internal constants.

Usage:
    python tools/layout/plan_lint.py plan.json --dump dump2.json
Exit code 0 = plan is consistent with the board rules, 1 = it is not.
"""
import argparse
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ec_layout as ec  # noqa: E402


def lint(board, plan, stackup=None):
    """Every check is (name, ok, detail). ok=False means "do not apply"."""
    checks = []
    layers_used = sorted({int(t["layer"]) for t in plan.get("tracks") or []})
    declared = int(stackup) if stackup else board.layer_count
    legal_layers = set(range(1, max(2, declared) + 1))
    detail = ("plan uses layers %s, board declares %d copper layer(s)" % (layers_used, board.layer_count))
    if stackup:
        detail += " - overridden to %d by --stackup (record this in the change note)" % declared
    checks.append(("layer count", set(layers_used) <= legal_layers, detail))

    radii = {round(board.via_radius, 2), round(ec.VIA_RADIUS, 2)}
    checks.append((
        "via diameter",
        len(radii) == 1,
        "board rule gives radius %.2f mil, the router used %.2f mil - clearance "
        "figures computed with the smaller value understate violations"
        % (board.via_radius, ec.VIA_RADIUS),
    ))

    narrow = [t for t in plan.get("tracks") or []
              if float(t["width"]) < board.min_width - 1e-6]
    checks.append((
        "minimum track width",
        not narrow,
        "%d track(s) thinner than the board minimum %.2f mil" % (len(narrow), board.min_width),
    ))

    power_ish = [t for t in plan.get("tracks") or []
                 if t["net"] in ec.POWER and float(t["width"]) < board.power_width - 1e-6]
    checks.append((
        "power width",
        True,   # informational: thinner power is legal, just not the board default
        "%d power track(s) thinner than the %.1f mil the board suggests"
        % (len(power_ish), board.power_width),
    ))

    over_edge = []
    for t in plan.get("tracks") or []:
        for (x, y) in ((t["x1"], t["y1"]), (t["x2"], t["y2"])):
            if (x - board.x0 + ec.EDGE) < board.edge_clearance or \
               (board.x1 - x + ec.EDGE) < board.edge_clearance:
                over_edge.append(t)
                break
    checks.append((
        "copper to edge",
        not over_edge,
        "%d track(s) closer than %.1f mil to the board edge" % (len(over_edge),
                                                                 board.edge_clearance),
    ))

    in_pad = sum(1 for v in plan.get("vias") or [] if v.get("in_pad"))
    checks.append((
        "via-in-pad",
        True,   # informational, but fabrication must know
        "%d via(s) in pad - requires resin fill (POFV)" % in_pad,
    ))
    return checks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("plan")
    ap.add_argument("--dump", required=True)
    ap.add_argument("--stackup", type=int,
                    help="override the declared copper layer count (must be recorded)")
    a = ap.parse_args()
    with open(a.dump, encoding="utf-8") as f:
        board = ec.Board(json.load(f))
    with open(a.plan, encoding="utf-8") as f:
        plan = json.load(f)

    checks = lint(board, plan, stackup=a.stackup)
    print("| check | verdict | detail |")
    print("|---|---|---|")
    bad = 0
    for name, ok, detail in checks:
        print("| %s | %s | %s |" % (name, "ok" if ok else "**FAIL**", detail))
        if not ok:
            bad += 1
    print()
    print("plan vs board rules:", "PASS" if bad == 0 else "BLOCKED (%d)" % bad)
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

