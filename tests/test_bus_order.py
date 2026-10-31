"""Tests for check_bus_order: the identity override must reproduce the direct rho.

The tool reported CAM_D rho = -0.90 directly but +1.00 for "rotate 0, no mirror",
which is the same geometry — a self-contradiction that would have led an agent to
rotate a part for no reason. This test pins the invariant.
"""
import importlib.util
import json
import math
import pathlib

HERE = pathlib.Path(__file__).resolve()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


EC = load("ec_layout", HERE.parents[1] / "tools" / "layout" / "ec_layout.py")
CB = load("check_bus_order", HERE.parents[1] / "tools" / "layout" / "check_bus_order.py")


def make_board():
    """J3-like row on the right, U5-like column on the left, 4 nets."""
    comps = []
    j3_pads = []
    u5_pads = []
    for i in range(4):
        j3_pads.append({"padNumber": str(i + 1), "net": f"BUS_{i}", "layer": 1,
                        "x": 2200 + i * 20, "y": 1153, "width": 20, "height": 40})
        u5_pads.append({"padNumber": str(i + 1), "net": f"BUS_{i}", "layer": 1,
                        "x": 1016, "y": 1400 - i * 50, "width": 60, "height": 35})
    comps.append({"designator": "J3", "x": 2230, "y": 1153, "rotation": 0,
                  "bbox": {"minX": 2100, "minY": 1100, "maxX": 2360, "maxY": 1200}, "pads": j3_pads})
    comps.append({"designator": "U5", "x": 1016, "y": 1325, "rotation": 0,
                  "bbox": {"minX": 700, "minY": 800, "maxX": 1300, "maxY": 1450}, "pads": u5_pads})
    return EC.Board({"result": {"components": comps,
                                "outline": {"bbox": {"minX": 0, "minY": 0, "maxX": 2756, "maxY": 1968}}}})


def test_identity_override_matches_direct_rho():
    board = make_board()
    direct = CB.rho_for(board, "BUS_")
    override = CB.transform_component(board, "U5", 0, False)
    via_override = CB.rho_for(board, "BUS_", override)
    assert direct is not None
    assert abs(direct - via_override) < 1e-9, (direct, via_override)


def test_spearman_extremes():
    assert abs(CB.spearman([1, 2, 3, 4], [10, 20, 30, 40]) - 1.0) < 1e-9
    assert abs(CB.spearman([1, 2, 3, 4], [40, 30, 20, 10]) + 1.0) < 1e-9


def test_mirror_flips_order():
    board = make_board()
    direct = CB.rho_for(board, "BUS_")
    mirrored = CB.transform_component(board, "U5", 0, True, mirror_axis="y")
    flipped = CB.rho_for(board, "BUS_", mirrored)
    assert abs(direct + flipped) < 1e-6, (direct, flipped)
