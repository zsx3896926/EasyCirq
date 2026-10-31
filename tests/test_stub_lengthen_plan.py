"""Regression tests for the 2026-10-30 18:49 stub-bridge incident.

Three lengthenings were each "text-clean" and were applied. Two ran collinear with
a neighbouring part's stub and merged (two real shorts); one ran straight through
another part's pin and swallowed that pin's stub and flag. `bridge-check` caught it
only after the batch, at 102/109.

These tests pin the three rejections. Coordinates are the live ones, mirrored into
the SVG frame the planner works in (schematic y is up, text boxes are y-down).
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))

import stub_lengthen_plan as plan  # noqa: E402

# pins as (x, -y): schematic (x, y_up) mirrored
PINS = {
    ("D2", "2"): (740.0, -430.0),
    ("D3", "1"): (790.0, -430.0),
    ("R3", "1"): (255.0, -240.0),
    ("R3", "2"): (295.0, -240.0),
    ("R5", "2"): (975.0, -500.0),
    ("R6", "1"): (1030.0, -500.0),
    ("R7", "1"): (345.0, -240.0),
}

# stubs as they stood before the batch
WIRES = [
    {"id": "d2stub", "pts": [(760.0, -430.0), (740.0, -430.0)]},
    {"id": "d3stub", "pts": [(770.0, -430.0), (790.0, -430.0)]},
    {"id": "r3stub", "pts": [(315.0, -240.0), (295.0, -240.0)]},
    {"id": "r5stub", "pts": [(995.0, -500.0), (975.0, -500.0)]},
    {"id": "r6stub", "pts": [(1010.0, -500.0), (1030.0, -500.0)]},
    {"id": "r7stub", "pts": [(325.0, -240.0), (345.0, -240.0)]},
]

FLAGS = [
    {"primitiveId": "gndD2", "net": "GND", "x": 760, "y": 430},
    {"primitiveId": "gndR5", "net": "GND", "x": 995, "y": 500},
    {"primitiveId": "gndR8", "net": "GND", "x": 405, "y": 240},
]


def test_d3_lengthened_to_50_is_rejected():
    # 740 is both D2:2's pin and the far end of D2's stub: the guard may cite
    # either reason, both mean "you are about to join two nets"
    why = plan.stub_conflict(PINS[("D3", "1")], (740.0, -430.0), WIRES, "d3stub", PINS, FLAGS)
    assert why and ("d2stub" in why or "D2:2" in why), why


def test_r6_lengthened_to_50_is_rejected_as_collinear_with_r5():
    why = plan.stub_conflict(PINS[("R6", "1")], (980.0, -500.0), WIRES, "r6stub", PINS, FLAGS)
    assert why, "a 50-long R6 stub overlaps R5's stub at y=500"


def test_r6_lengthened_to_35_lands_on_r5_flag_and_is_rejected():
    why = plan.stub_conflict(PINS[("R6", "1")], (995.0, -500.0), WIRES, "r6stub", PINS, FLAGS)
    assert why and ("gndR5" in why or "endpoint" in why), why


def test_r7_lengthened_to_50_runs_through_r3_pin_and_is_rejected():
    why = plan.stub_conflict(PINS[("R7", "1")], (295.0, -240.0), WIRES, "r7stub", PINS, FLAGS)
    assert why and "R3:2" in why.replace(" ", ""), why


def test_original_20_long_stubs_are_accepted():
    # the geometry that was live before the batch must stay feasible, otherwise the
    # guard is too strict to plan anything
    assert plan.stub_conflict(PINS[("D3", "1")], (770.0, -430.0), WIRES, "d3stub", PINS, FLAGS) is None
    assert plan.stub_conflict(PINS[("R6", "1")], (1010.0, -500.0), WIRES, "r6stub", PINS, FLAGS) is None
    assert plan.stub_conflict(PINS[("R7", "1")], (325.0, -240.0), WIRES, "r7stub", PINS, FLAGS) is None


def test_perpendicular_crossing_is_allowed():
    # a wire crossing at right angles draws a crossing, not a junction
    wires = [{"id": "vert", "pts": [(710.0, -500.0), (710.0, -400.0)]}]
    assert plan.stub_conflict((740.0, -430.0), (700.0, -430.0), wires, "own", PINS, FLAGS) is None
