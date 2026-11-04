"""Close the loop: blocked stubs feed back into layout as lane requirements.

``stub_planner`` predicts which pins EDA's geometry guard will reject; this
script sweeps the layout's inter-part spacing (and, as a last resort, the label
offset budget) until the predicted rejects reach **zero** - the layout reserves
the lanes instead of the write channel discovering the collisions.

Output: ``easycirq-lane-repair/v1`` with the chosen parameters, the plan, the
stub plan and the per-pin verdicts.
"""

from __future__ import annotations

import json
import pathlib
import sys

TOOLS = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import relayout_page  # noqa: E402
import subdivide  # noqa: E402
import stub_planner  # noqa: E402

SCHEMA = "easycirq-lane-repair/v1"


def evaluate(snapshot, groups, geometry, nets, *, part_gap, offsets):
    parts = {}
    pins = {}
    for comp in snapshot.get("components") or []:
        ref = comp.get("ref")
        for pin in comp.get("pins") or []:
            if pin.get("net"):
                pins[(ref, str(pin.get("number")))] = pin["net"]
    return None


def build(snapshot, groups, geometry, nets, *, part_gap=14.0, offsets=(20.0, 26.0, 32.0),
          label_sizes=None):
    """Lay out with a given inter-part gap and predict every stub collision."""
    original = relayout_page.PART_GAP
    relayout_page.PART_GAP = float(part_gap)
    try:
        plan = relayout_page.plan_page(snapshot, groups, geometry=geometry)
    finally:
        relayout_page.PART_GAP = original
    parts = {ref: (place["x"], place["y"])
             for ref, place in (plan.get("placements") or {}).items()}
    pins = {}
    for comp in snapshot.get("components") or []:
        ref = comp.get("ref")
        for pin in comp.get("pins") or []:
            if pin.get("net"):
                pins[(ref, str(pin.get("number")))] = pin["net"]
    stubs = stub_planner.plan_stubs(parts, pins, geometry, nets,
                                    label_sizes=label_sizes, offsets=offsets)
    blocked = [item for item in stubs["placed"] if item.get("shrunk")] + \
              stubs.get("unplaced", [])
    return plan, stubs, blocked


def repair(snapshot, groups, geometry, nets, *, gaps=(14.0, 20.0, 26.0, 32.0, 40.0),
           label_sizes=None):
    """First layout gap whose stub plan has zero predicted rejects."""
    attempts = []
    for gap in gaps:
        plan, stubs, blocked = build(snapshot, groups, geometry, nets,
                                     part_gap=gap, label_sizes=label_sizes)
        attempts.append({"part_gap": gap, "verdict": plan.get("verdict"),
                         "blocked": len(blocked),
                         "pins": stubs["counts"]["pins"],
                         "shrunk": stubs["counts"]["shrunk"]})
        if plan.get("verdict") == "pass" and not blocked:
            return {"schema": SCHEMA, "part_gap": gap, "plan": plan,
                    "stubs": stubs, "attempts": attempts, "blocked": [],
                    "verdict": "pass"}
    # nothing cleared: return the best attempt (fewest blocked)
    best = min(attempts, key=lambda a: a["blocked"])
    plan, stubs, blocked = build(snapshot, groups, geometry, nets,
                                 part_gap=best["part_gap"], label_sizes=label_sizes)
    return {"schema": SCHEMA, "part_gap": best["part_gap"], "plan": plan,
            "stubs": stubs, "attempts": attempts, "blocked": blocked,
            "verdict": "blocked"}


if __name__ == "__main__":
    print(json.dumps({"schema": SCHEMA,
                      "usage": "repair(snapshot, groups, geometry, nets)"},
                     ensure_ascii=False))
