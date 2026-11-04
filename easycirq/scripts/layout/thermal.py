#!/usr/bin/env python3
"""Offline thermal screen (GAPS G9).

One question, answered honestly: given a part's dissipation and a junction-to-ambient resistance, what
junction temperature does it reach, and how much does the copper under it help?  The tool deliberately
does NOT pretend to be a thermal solver - it is a first-order screen plus a checklist of the layout
items that a thermal/EMC review always asks for.

Inputs are ASSUMPTIONS unless you pass them: the parts list below carries the powers and resistances used
for RetroCam-02, and every row prints its source.  Anything not measured is marked NOT MEASURED.

Usage
-----
    python easycirq/scripts/layout/thermal.py [--ambient 25] [--parts parts.json] [--plan out/fd/plan.json]
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ASSUMED values for RetroCam-02: dissipation (W) and theta-ja (C/W) without extra copper.
# Replace with datasheet numbers before quoting anything.
DEFAULT_PARTS = {
    "U5": {"what": "SoC / camera interface", "power_w": 0.35, "theta_ja": 60.0},
    "U1": {"what": "buck-boost (BB_VIN)", "power_w": 0.25, "theta_ja": 45.0},
    "U4": {"what": "USB / charger front end", "power_w": 0.20, "theta_ja": 50.0},
    "L1": {"what": "inductor", "power_w": 0.15, "theta_ja": 80.0},
}

# Layout items a thermal/EMC review asks for; `check` is a plan predicate where one can be computed.
CHECKLIST = [
    ("copper area under each hot part", "needs a plan: count tracks/pours in the part's bbox"),
    ("thermal via array under exposed pads", "needs pad data: count vias inside the pad"),
    ("crystal placed with a ground guard ring", "needs a plan: pour coverage around the crystal"),
    ("filter capacitors at every connector", "needs a netlist review"),
    ("unbroken ground plane under the bus routes", "needs a pour report"),
]


def junction(temp_ambient, power_w, theta_ja, improvement=1.0):
    """Tj = Ta + P * theta_ja / improvement (improvement >1 models added copper)."""
    return temp_ambient + power_w * theta_ja / improvement


def report(parts, ambient, marjin_c=20.0, tj_max=85.0, source=None):
    print("thermal screen - %s" % (source or
          "ASSUMED powers and theta-ja (datasheet numbers required before quoting)"))
    print("ambient %.1f C, Tj limit %.1f C\n" % (ambient, tj_max))
    print("| part | what | P (W) | theta_ja (C/W) | Tj (C) | headroom (C) | verdict |")
    print("|---|---|---|---|---|---|---|")
    worst = None
    for des, spec in sorted(parts.items()):
        tj = junction(ambient, spec["power_w"], spec["theta_ja"])
        head = tj_max - tj
        verdict = "ok" if head >= marjin_c else ("**tight**" if head >= 0 else "**over limit**")
        if worst is None or head < worst[1]:
            worst = (des, head)
        print("| %s | %s | %.2f | %.0f | %.1f | %.1f | %s |" % (
            des, spec["what"], spec["power_w"], spec["theta_ja"], tj, head, verdict))

    print("\ncopper effect (a plane or via array typically halves theta-ja; that is an ASSUMPTION):")
    print("| part | theta_ja x0.5 -> Tj (C) |")
    print("|---|---|")
    for des, spec in sorted(parts.items()):
        print("| %s | %.1f |" % (des, junction(ambient, spec["power_w"], spec["theta_ja"], 2.0)))

    print("\nreview checklist (none of these are measured by this tool):")
    for item, how in CHECKLIST:
        print("  [ ] %s  - %s" % (item, how))
    if worst:
        print("\ntightest part: %s with %.1f C headroom at the assumed numbers." % (worst[0], worst[1]))
    return parts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ambient", type=float, default=25.0)
    ap.add_argument("--parts", help="JSON map part -> {what, power_w, theta_ja}")
    ap.add_argument("--tj-max", type=float, default=85.0)
    a = ap.parse_args()

    parts = DEFAULT_PARTS
    if a.parts:
        with open(a.parts, encoding="utf-8") as f:
            parts = json.load(f)
    report(parts, a.ambient, tj_max=a.tj_max,
           source=("supplied from %s" % a.parts) if a.parts else None)
    print("\nNOT MEASURED here: real dissipation, real theta-ja, copper spreading, airflow, transient loads.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
