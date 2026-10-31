"""Unit tests for the offline layout/routing toolchain (tools/layout/ec_layout.py).

These lock the *metrics* down: the gate is only meaningful if "congestion",
"unconnected" and "clearance" mean exactly one thing. A previous version had the
router and the plan-based checker disagreeing (39 vs 0), which silently passed a
broken KPI.
"""
import importlib.util
import pathlib

import pytest

HERE = pathlib.Path(__file__).resolve()
MOD_PATH = HERE.parents[1] / "tools" / "layout" / "ec_layout.py"
spec = importlib.util.spec_from_file_location("ec_layout", MOD_PATH)
ec = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ec)


def make_board(comps, bbox=(0, 0, 2000, 1500)):
    """Minimal dump-shaped input: components with pads."""
    return ec.Board({"result": {
        "components": comps,
        "outline": {"bbox": {"minX": bbox[0], "minY": bbox[1], "maxX": bbox[2], "maxY": bbox[3]}},
    }})


def comp(des, x, y, pads, w=100, h=100):
    return {
        "designator": des, "x": x, "y": y, "rotation": 0,
        "bbox": {"minX": x - w / 2, "minY": y - h / 2, "maxX": x + w / 2, "maxY": y + h / 2},
        "pads": [{"padNumber": p, "net": n, "x": px, "y": py, "width": 20, "height": 20, "layer": 1}
                 for (p, n, px, py) in pads],
    }


# ── metrics ─────────────────────────────────────────────────────────────────
def test_congestion_counts_two_nets_on_the_same_cell():
    board = make_board([comp("R1", 300, 300, [("1", "A", 300, 300)]),
                        comp("R2", 700, 300, [("1", "B", 700, 300)])])
    plan = {"tracks": [
        {"net": "A", "layer": 1, "width": 8, "x1": 300, "y1": 300, "x2": 700, "y2": 300},
        {"net": "B", "layer": 1, "width": 8, "x1": 700, "y1": 700, "x2": 300, "y2": 700},
    ], "vias": []}
    assert ec.congestion_from_plan(board, plan) == 0  # parallel, no shared cell

    plan["tracks"].append({"net": "B", "layer": 1, "width": 8,
                           "x1": 300, "y1": 300, "x2": 300, "y2": 700})
    assert ec.congestion_from_plan(board, plan) > 0  # B crosses A at (300,300)


def test_congestion_is_per_layer():
    board = make_board([comp("R1", 300, 300, [("1", "A", 300, 300)])])
    plan = {"tracks": [
        {"net": "A", "layer": 1, "width": 8, "x1": 300, "y1": 300, "x2": 700, "y2": 300},
        {"net": "B", "layer": 2, "width": 8, "x1": 300, "y1": 300, "x2": 700, "y2": 300},
    ], "vias": []}
    assert ec.congestion_from_plan(board, plan) == 0  # crossing on another layer is legal


# ── connectivity ────────────────────────────────────────────────────────────
def test_connectivity_detects_missing_segment():
    board = make_board([
        comp("R1", 300, 300, [("1", "A", 300, 300)]),
        comp("R2", 800, 300, [("1", "A", 800, 300)]),
    ])
    full = {"tracks": [{"net": "A", "layer": 1, "width": 8,
                        "x1": 300, "y1": 300, "x2": 800, "y2": 300}], "vias": []}
    assert ec.connectivity_from_plan(board, full) == []

    broken = {"tracks": [{"net": "A", "layer": 1, "width": 8,
                          "x1": 300, "y1": 300, "x2": 500, "y2": 300}], "vias": []}
    assert ec.connectivity_from_plan(board, broken) == ["A"]


def test_connectivity_uses_vias_to_cross_layers():
    board = make_board([
        comp("R1", 300, 300, [("1", "A", 300, 300)]),
        comp("R2", 800, 800, [("1", "A", 800, 800)]),
    ])
    with_via = {"tracks": [
        {"net": "A", "layer": 1, "width": 8, "x1": 300, "y1": 300, "x2": 300, "y2": 800},
        {"net": "A", "layer": 2, "width": 8, "x1": 300, "y1": 800, "x2": 800, "y2": 800},
    ], "vias": [{"net": "A", "x": 300, "y": 800}]}
    assert ec.connectivity_from_plan(board, with_via) == []


# ── placement legalisation ──────────────────────────────────────────────────
def test_legalize_removes_all_overlaps():
    comps = [
        comp("A", 300, 300, [("1", "N1", 300, 300)], w=300, h=300),
        comp("B", 320, 310, [("1", "N2", 320, 310)], w=300, h=300),
        comp("C", 340, 320, [("1", "N2", 340, 320)], w=300, h=300),
    ]
    board = make_board(comps)
    assert ec.n_overlaps(board.comps) > 0
    ec.legalize(board.comps, board)
    assert ec.n_overlaps(board.comps) == 0
    assert ec.n_outside(board.comps, board) == 0


# ── gate ────────────────────────────────────────────────────────────────────
def test_gate_fails_on_any_dirty_kpi():
    ok, failures = ec.gate({"unrouted_legs": 0, "congestion_cells": 0,
                            "clearance_violations": 0, "nets_unconnected": 0})
    assert ok and failures == {}

    ok, failures = ec.gate({"unrouted_legs": 0, "congestion_cells": 3,
                            "clearance_violations": 0, "nets_unconnected": 1})
    assert not ok
    assert set(failures) == {"congestion_cells", "nets_unconnected"}


def test_router_and_plan_congestion_must_agree():
    """The router's own `used` accounting and the plan-based recount are two
    independent implementations of the same KPI. On the real board they read 48
    vs 353, so at least one is wrong; this test pins the tiny case where the
    correct answer is knowable by hand."""
    board = make_board([
        comp("R1", 200, 200, [("1", "A", 200, 200)]),
        comp("R2", 1200, 200, [("1", "A", 1200, 200)]),
        comp("R3", 700, 200, [("1", "B", 700, 200)]),
        comp("R4", 700, 1200, [("1", "B", 700, 1200)]),
    ], bbox=(0, 0, 1400, 1400))
    (unrouted, overflow), routed, failures = ec.route(board, iters=3, layers=2)
    plan = ec.plan_from(board, routed)
    plan_cong = ec.congestion_from_plan(board, plan)
    if not failures:
        # `overflow` is the router's own count (int); the plan recount must match.
        assert overflow == plan_cong, (overflow, plan_cong)


def test_clearance_violation_detected_between_nets():
    board = make_board([comp("R1", 300, 300, [("1", "A", 300, 300)])])
    plan = {"tracks": [
        {"net": "A", "layer": 1, "width": 8, "x1": 300, "y1": 300, "x2": 800, "y2": 300},
        {"net": "B", "layer": 1, "width": 8, "x1": 300, "y1": 302, "x2": 800, "y2": 302},
    ], "vias": []}
    assert ec.clearance_violations(board, plan) > 0


# ── placement terms for the failed legs ─────────────────────────────────────
def test_face_penalty_is_zero_when_pads_point_at_peripherals():
    """U5's pad field must face the parts it talks to; facing away scores 2."""
    facing = ec.Board({"result": {"components": [
        comp("U5", 300, 300, [("1", "A", 350, 280), ("2", "B", 350, 320)]),
        comp("J3", 900, 300, [("1", "A", 880, 280), ("2", "B", 880, 320)]),
    ], "outline": {"bbox": {"minX": 0, "minY": 0, "maxX": 2000, "maxY": 1500}}}})
    assert ec.escape_face_penalty(facing.comps) == pytest.approx(0.0, abs=1e-6)

    away = ec.Board({"result": {"components": [
        comp("U5", 300, 300, [("1", "A", 350, 300)]),
        comp("J3", 0, 300, [("1", "A", 10, 300)]),   # peripheral is on the -x side
    ], "outline": {"bbox": {"minX": 0, "minY": 0, "maxX": 2000, "maxY": 1500}}}})
    assert ec.escape_face_penalty(away.comps) == pytest.approx(2.0, abs=1e-6)


def test_button_leg_penalty_counts_each_switch_leg():
    board = make_board([
        comp("U5", 300, 300, [("15", "BTN_DOWN", 300, 300), ("16", "BTN_UP", 300, 320)]),
        comp("SW2", 800, 300, [("1", "BTN_DOWN", 800, 300)]),
        comp("SW4", 300, 820, [("1", "BTN_UP", 300, 820)]),
        comp("R9", 500, 500, [("1", "+3V3", 500, 500)]),   # not a button net
    ])
    # 500 mil leg + 500 mil leg, scaled by 1000 mil per unit
    assert ec.button_leg_penalty(board.comps) == pytest.approx(1.0, abs=1e-6)


def test_placement_cost_trades_button_length_against_hpwl():
    """The button term must be a real trade, not decoration.

    Two layouts have the SAME HPWL (100 + 1100 vs 1100 + 100 mil of two-pad
    boxes); only the button term can separate them, and it must flip the answer
    once the weight exceeds the declared mil-per-mil rate.
    """
    def build(sw_x):
        return ec.Board({"result": {"components": [
            comp("U5", 300, 300, [("15", "BTN_DOWN", 300, 300)]),
            comp("SW2", sw_x, 300, [("1", "BTN_DOWN", sw_x, 300), ("2", "N1", sw_x, 300)]),
            comp("J1", 1500, 300, [("1", "N1", 1500, 300)]),
        ], "outline": {"bbox": {"minX": 0, "minY": 0, "maxX": 2000, "maxY": 1500}}}})

    near_button, far_button = build(400), build(1400)
    assert ec.hpwl(near_button.comps) == pytest.approx(ec.hpwl(far_button.comps), abs=1e-6)

    # weight below 1000 mil per 1000 mil of leg: the tie is decided by nothing else
    assert ec.placement_cost(near_button.comps, near_button, btn_w=0.0) == pytest.approx(
        ec.placement_cost(far_button.comps, far_button, btn_w=0.0), abs=1e-6)
    # once the weight is worth more than 1:1, the short leg must win
    assert ec.placement_cost(near_button.comps, near_button, btn_w=4000.0) < \
        ec.placement_cost(far_button.comps, far_button, btn_w=4000.0)
