"""Regression tests for the two planner defects found on 2026-10-30 (round 6).

Both were silent: the plan looked sane, and only `sch check` caught the damage
after the fact (``designator-overlap C2`` from a designator moved into its own
body, ``designator-wire-overlap C11`` from one moved onto its own pin stub).
These tests pin the *coordinates frames* and the *obstacle classes*, because
those are what was wrong — not the search.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))

import designator_move_plan as plan_mod  # noqa: E402


def row(text, bbox, role):
    return {"text": text, "bbox": list(bbox), "role": role, "area": plan_mod.area(bbox)}


def record(value, x, y, pid="p1"):
    return {"primitiveId": pid, "Value": value, "X": x, "Y": y, "Key": "Designator"}


def test_segments_mirror_y_and_pad():
    dump = {"result": {"value": {"wires": [{"id": "w", "line": [139, 559, 139, 581]}]}}}
    (seg,) = plan_mod.segments(dump, pad=1.0)
    # schematic y 559..581 becomes svg y -581..-559, thickened by the pad
    assert seg == (138.0, -582.0, 140.0, -558.0)


def test_wire_obstacle_blocks_a_label_that_sits_on_its_own_stub():
    # C11 measured layout: designator box 140..155.4 x -580..-570, two vertical
    # capacitor stubs at x=139..141 and x=149..151 spanning -581..-559.
    dump = {"result": {"value": {"wires": [
        {"id": "a", "line": [139, 559, 139, 581]},
        {"id": "b", "line": [149, 559, 149, 581]},
    ]}}}
    wires = plan_mod.segments(dump)
    rows = [row("C11", (140.0, -580.0, 155.4, -570.0), "designator")]
    bodies = {"C11": [139.5, -553.5, 160.5, -536.5]}   # already mirrored to svg space
    out = plan_mod.plan(rows, bodies, {"C11": record("C11", 140, 555)}, wires=wires)
    entry = out["report"][0]
    assert entry["status"] in ("planned", "no-clearance")
    if entry["status"] == "planned":
        moved = plan_mod.moved(rows[0]["bbox"], entry["dx_svg"], entry["dy_svg"])
        assert not plan_mod._hits_wire(moved, wires)


def test_clean_when_box_is_clear_of_text_body_and_wire():
    rows = [row("R1", (230.0, -515.0, 241.2, -505.0), "designator")]
    bodies = {"R1": [229.5, -505.0, 241.0, -491.0]}
    out = plan_mod.plan(rows, bodies, {"R1": record("R1", 230, 505)}, wires=[])
    assert out["report"][0]["status"] == "clean"


def test_designator_inside_its_own_body_is_forced_out():
    # A designator box straddling its body (the C2/C11 defect) must not be "clean".
    rows = [row("C2", (675.0, -560.0, 691.9, -550.0), "designator")]
    bodies = {"C2": [674.5, -553.5, 695.5, -536.5]}
    out = plan_mod.plan(rows, bodies, {"C2": record("C2", 675, 550)})
    entry = out["report"][0]
    assert entry["status"] != "clean"
    if entry["status"] == "planned":
        moved = plan_mod.moved(rows[0]["bbox"], entry["dx_svg"], entry["dy_svg"])
        assert plan_mod.cover(moved, bodies["C2"]) == 0.0


def test_move_converts_back_to_schematic_y_up():
    rows = [row("R9", (230.0, -515.0, 241.2, -505.0), "designator"),
            row("BOOST_OUT", (228.0, -512.0, 282.6, -505.0), "net_label")]
    out = plan_mod.plan(rows, {}, {"R9": record("R9", 230, 505)})
    move = out["moves"][0]
    # dy_svg is what the search found; the payload must undo it because Y is up
    assert move["new_y"] == move["expected"]["Y"] - move["dy_svg"]
    assert move["new_x"] == move["expected"]["X"] + move["dx_svg"]
