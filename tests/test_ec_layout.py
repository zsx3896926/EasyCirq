"""Unit tests for the offline layout/routing toolchain (tools/layout/ec_layout.py).

These lock the *metrics* down: the gate is only meaningful if "congestion",
"unconnected" and "clearance" mean exactly one thing. A previous version had the
router and the plan-based checker disagreeing (39 vs 0), which silently passed a
broken KPI.
"""
import importlib.util
import json
import math
import pathlib
import sys

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


def test_gate_refuses_a_kpi_it_could_not_measure():
    """`check` reads a plan from disk, which has no router `paths`; the leg count
    is then UNMEASURED. Passing it as 0 is the handoff's bug #3 all over again."""
    ok, failures = ec.gate({"unrouted_legs": None, "congestion_cells": 0,
                            "clearance_violations": 0, "nets_unconnected": 0})
    assert not ok
    assert "unrouted_legs" in failures


def test_via_violation_cells_points_at_the_offending_via():
    """The negotiator needs WHERE, not just how many, or it cannot push back."""
    board = make_board([comp("R1", 300, 300, [("1", "A", 300, 300)])])
    plan = {"tracks": [{"net": "B", "layer": 2, "width": 7,
                        "x1": 480, "y1": 505, "x2": 520, "y2": 505}],
            "vias": [{"net": "A", "x": 500, "y": 500},
                     {"net": "A", "x": 900, "y": 900}]}
    cells = ec.via_violation_cells(board, plan)
    assert cells == {(500.0, 500.0)}

    # a via may sit on its OWN net's pad, which is not a violation
    plan["vias"] = [{"net": "A", "x": 300, "y": 300}]
    plan["tracks"] = []
    assert ec.via_violation_cells(board, plan) == set()


def test_pad_layer_gaps_sees_an_open_circuit_2d_connectivity_misses():
    """A track that ends next to a pad but on the WRONG LAYER is an open circuit,
    even though `connectivity_from_plan` (a 2D check) calls it connected."""
    board = make_board([comp("R1", 300, 300, [("1", "A", 300, 300)])])
    on_layer = {"tracks": [{"net": "A", "layer": 1, "width": 7,
                            "x1": 300, "y1": 300, "x2": 600, "y2": 300}], "vias": []}
    assert ec.pad_layer_gaps(board, on_layer) == 0

    wrong_layer = {"tracks": [{"net": "A", "layer": 3, "width": 7,
                               "x1": 300, "y1": 300, "x2": 600, "y2": 300}], "vias": []}
    assert ec.pad_layer_gaps(board, wrong_layer) == 1

    # a via at the pad makes the same geometry legal
    wrong_layer["vias"] = [{"net": "A", "x": 300, "y": 300}]
    assert ec.pad_layer_gaps(board, wrong_layer) == 0


def test_flat_route_never_changes_layer():
    """Via-directed routing must be able to say "this segment has no via"."""
    board = make_board([
        comp("R1", 300, 300, [("1", "A", 300, 300)]),
        comp("R2", 1200, 300, [("1", "A", 1200, 300)]),
    ])
    sc, gc = board.cell(300, 300), board.cell(1200, 300)
    path = ec.flat_route(board, sc, gc, 1, set(), {}, set())
    assert path and all(cell[2] == 1 for cell in path)


def test_free_via_site_steps_away_from_another_nets_pad():
    """A via may not be planted in another net's keep-out; the site search has to
    walk outward until it is legal, or give up."""
    board = make_board([
        comp("R1", 300, 300, [("1", "A", 300, 300)]),
        comp("R2", 320, 300, [("1", "B", 320, 300), ("2", "B", 320, 340), ("3", "B", 320, 260)]),
    ])
    pad_forbid, _own = board.pad_blocked()
    used = {}
    cell = board.cell(300, 300)
    site = ec.free_via_site(board, cell, "A", pad_forbid, used, ec.TRACE)
    assert site is not None
    owner = pad_forbid.get(site)
    assert not owner or "A" in owner


def test_pour_islands_sees_a_pour_cut_in_two():
    """A pour shares its layer with tracks, so they can cut it into islands.
    Two access vias in different islands = a broken net that 2D connectivity
    happily calls connected."""
    board = make_board([
        comp("R1", 300, 700, [("1", "GND", 300, 700)]),
        comp("R2", 1700, 700, [("1", "GND", 1700, 700)]),
    ])
    vias = [{"net": "GND", "x": 300, "y": 700, "plane_layer": 4},
            {"net": "GND", "x": 1700, "y": 700, "plane_layer": 4}]
    open_pour = {"tracks": [], "vias": list(vias)}
    assert ec.pour_islands(board, open_pour) == 0

    wall = {"tracks": [{"net": "B", "layer": 4, "width": 7,
                        "x1": 1000, "y1": 0, "x2": 1000, "y2": 1500}], "vias": list(vias)}
    assert ec.pour_islands(board, wall) >= 1


def test_via_disc_needs_the_whole_circle_not_just_the_centre():
    """Checking only the centre cell put access vias on neighbours' keep-out
    rings; the disc test has to see copper anywhere inside the radius."""
    board = make_board([
        comp("R1", 300, 300, [("1", "A", 300, 300)]),
        comp("R2", 365, 300, [("1", "B", 365, 300)]),
    ])
    pad_forbid, _own = board.pad_blocked()
    probe = board.cell(300, 300)
    # copper one cell away: the CENTRE is free, the disc is not
    assert ec._disc_clear(board, probe, "A", pad_forbid,
                          {(probe[0] + 1, probe[1])}, ec.TRACE) is False
    # copper three cells away: clear
    assert ec._disc_clear(board, probe, "A", pad_forbid,
                          {(probe[0] + 3, probe[1])}, ec.TRACE) is True


def test_reproduce_scorecard_states_the_gate_verdict():
    """The one-command reproduction must print every gate KPI, including the bus
    skew that `gate()` cannot see, and must not call a dirty board PASS."""
    import importlib.util as _ilu
    spec = _ilu.spec_from_file_location(
        "reproduce", MOD_PATH.parent / "reproduce.py")
    rep = _ilu.module_from_spec(spec)
    spec.loader.exec_module(rep)

    kpi = {"unrouted_legs": 0, "congestion_cells": 0, "clearance_violations": 3,
           "nets_unconnected": 0, "pad_layer_gaps": 0, "pour_islands": 0,
           "vias": 10, "plane_vias": 4, "vias_in_pad": 1, "tracks": 20,
           "total_length_mil": 100.0, "diagonal_ratio": 0.4}
    skew = {"CAM_D": 713.0, "LCD_": 20.0, "SD_": 10.0}
    text = rep.scorecard(kpi, skew, False, {"clearance_violations": 3})
    assert "clearance violations" in text and "713.0" in text
    assert "FAIL" in text and "bus_skew" in text

    kpi["clearance_violations"] = 0
    text = rep.scorecard(kpi, {"CAM_D": 10.0, "LCD_": 5.0, "SD_": 5.0}, True, {})
    assert "PASS" in text


def test_reproduce_scorecard_separates_design_conflict_from_bug():
    """A skew the pin order makes impossible must not read like unfinished work."""
    import importlib.util as _ilu
    spec = _ilu.spec_from_file_location("reproduce2", MOD_PATH.parent / "reproduce.py")
    rep = _ilu.module_from_spec(spec)
    spec.loader.exec_module(rep)
    kpi = {"unrouted_legs": 0, "congestion_cells": 0, "clearance_violations": 0,
           "nets_unconnected": 0, "pad_layer_gaps": 0, "pour_islands": 0,
           "vias": 1, "plane_vias": 1, "vias_in_pad": 0, "tracks": 2,
           "total_length_mil": 10.0, "diagonal_ratio": 0.5}
    text = rep.scorecard(kpi, {"CAM_D": 713.0}, False, {"bus_skew": None},
                         why={"bus_skew": "design conflict: pin order disagrees"})
    assert "design conflict" in text and "failing KPI" in text


def test_emit_apply_refuses_a_plan_that_did_not_pass_the_gate():
    """The project rule is one-way: nothing goes to the machine until the offline
    gate is green. The refusal must name every open KPI."""
    import importlib.util as _ilu
    spec = _ilu.spec_from_file_location("emit_apply", MOD_PATH.parent / "emit_apply.py")
    ea = _ilu.module_from_spec(spec)
    spec.loader.exec_module(ea)

    dirty = {"unrouted_legs": 0, "congestion_cells": 0, "clearance_violations": 121,
             "nets_unconnected": 0, "pad_layer_gaps": 0, "pour_islands": 0,
             "bus_length_spread_mil": {"CAM_D": 713.1, "LCD_": 10.0}}
    reasons = ea.gate_reasons(dirty)
    assert any("clearance_violations: 121" in r for r in reasons)
    assert any("CAM_D" in r for r in reasons)
    assert not any("LCD_" in r for r in reasons)

    clean = dict(dirty)
    clean["clearance_violations"] = 0
    clean["bus_length_spread_mil"] = {"CAM_D": 10.0}
    assert ea.gate_reasons(clean) == []

    # an unmeasured KPI is not a pass
    unmeasured = dict(clean)
    unmeasured["pad_layer_gaps"] = None
    assert any("NOT MEASURED" in r for r in ea.gate_reasons(unmeasured))


def test_emit_apply_manifest_records_what_fabrication_must_know():
    import importlib.util as _ilu
    spec = _ilu.spec_from_file_location("emit_apply2", MOD_PATH.parent / "emit_apply.py")
    ea = _ilu.module_from_spec(spec)
    spec.loader.exec_module(ea)

    plan = {"tracks": [{"net": "A", "layer": 1, "width": 7.0, "x1": 0, "y1": 0, "x2": 10, "y2": 0}],
            "vias": [{"net": "GND", "x": 5, "y": 5, "plane_layer": 4},
                     {"net": "B", "x": 9, "y": 9, "in_pad": True}]}
    norm = ea.normalise(plan)
    man = ea.build_manifest(norm, {}, "dump2.json", "sha")
    assert man["counts"]["tracks"] == 1
    assert man["counts"]["vias"] == 2
    assert man["counts"]["access_vias"] == 1
    assert man["counts"]["vias_in_pad"] == 1
    assert any("POFV" in n for n in man["fabrication_notes"])
    assert any("pour" in n.lower() for n in man["fabrication_notes"])


def test_plan_lint_blocks_a_plan_for_the_wrong_stackup_unless_overridden():
    """The board declares 2 copper layers while the plan uses 4. That must block,
    and the only way past it is an explicit, recorded override."""
    import importlib.util as _ilu
    spec = _ilu.spec_from_file_location("plan_lint", MOD_PATH.parent / "plan_lint.py")
    pl = _ilu.module_from_spec(spec)
    spec.loader.exec_module(pl)

    board = make_board([comp("R1", 300, 300, [("1", "A", 300, 300)])])
    board.layer_count = 2
    board.via_radius = 12.01
    board.clearance = 6.0
    board.track_width = 10.0
    board.power_width = 20.0
    board.min_width = 5.0
    board.edge_clearance = 10.0
    plan = {"tracks": [{"net": "A", "layer": 3, "width": 7.0,
                        "x1": 300, "y1": 300, "x2": 600, "y2": 300}], "vias": []}

    checks = dict((name, ok) for name, ok, _d in pl.lint(board, plan))
    assert checks["layer count"] is False
    checks = dict((name, ok) for name, ok, _d in pl.lint(board, plan, stackup=4))
    assert checks["layer count"] is True


def test_compare_marks_the_dominated_profile():
    """The comparison table has to say WHICH branch wins, not just list numbers."""
    import importlib.util as _ilu
    spec = _ilu.spec_from_file_location("compare", MOD_PATH.parent / "compare.py")
    cmp_mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(cmp_mod)

    def row(name, **kw):
        kpi = {k: 0 for k in cmp_mod.GATE_VECTOR}
        kpi.update(kw)
        kpi.update({"vias": 100, "plane_vias": 0, "vias_in_pad": 0,
                    "tracks": 500, "total_length_mil": 30000.0, "diagonal_ratio": 0.4})
        return {"profile": name, "kpi": kpi, "skew_max": 100.0}

    better = row("better")
    worse = row("worse", clearance_violations=5)
    assert cmp_mod.pareto([better, worse]) == ["better"]
    # two configs that trade one KPI against another are both non-dominated
    trade = row("trade", clearance_violations=3, unrouted_legs=-0)
    trade["kpi"]["clearance_violations"] = 3
    trade["kpi"]["unrouted_legs"] = 0
    other = row("other")
    other["kpi"]["clearance_violations"] = 0
    other["kpi"]["unrouted_legs"] = 1
    assert sorted(cmp_mod.pareto([trade, other])) == ["other", "trade"]
    text, front = cmp_mod.table([better, worse])
    assert "**yes**" in text and front == ["better"]


def test_compare_cache_key_changes_when_the_metric_changes(tmp_path):
    """A cache keyed only on (profile, dump, placement) would replay yesterday's
    numbers after the KPI definition changed - exactly what happened when
    track/pad was added to the clearance count."""
    import importlib.util as _ilu
    spec = _ilu.spec_from_file_location("compare", MOD_PATH.parent / "compare.py")
    cmp_mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(cmp_mod)

    dump = tmp_path / "dump.json"
    place = tmp_path / "place.json"
    dump.write_text("{}", encoding="utf-8")
    place.write_text("{}", encoding="utf-8")

    before = cmp_mod._cache_key("trim-pour", str(dump), str(place))
    real = cmp_mod._metric_version
    try:
        cmp_mod._metric_version = lambda: real() + "|changed"
        after = cmp_mod._cache_key("trim-pour", str(dump), str(place))
    finally:
        cmp_mod._metric_version = real
    assert before != after
    assert cmp_mod._cache_key("trim-pour", str(dump), str(place)) == before  # stable


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


# ── plane (GND carried by an inner layer) ───────────────────────────────────
def test_plane_net_gets_no_tracks_but_still_connects():
    """A plane net must spend vias, not tracks — and must still be connected."""
    board = make_board([
        comp("R1", 300, 300, [("1", "GND", 300, 300)]),
        comp("R2", 1200, 300, [("1", "GND", 1200, 300)]),
        comp("R3", 300, 600, [("1", "A", 300, 600)]),
        comp("R4", 1200, 600, [("1", "A", 1200, 600)]),
    ])
    (_u, _c), routed, _f = ec.route(board, iters=1, layers=4, segment_check=True,
                                    plane_nets=frozenset({"GND"}), plane_layer=2)
    plan = ec.plan_from(board, routed)

    # The only GND copper allowed on a plane net is the short pad->via stub.
    gnd_tracks = [t for t in plan["tracks"] if t["net"] == "GND"]
    assert all(math.hypot(t["x2"] - t["x1"], t["y2"] - t["y1"]) <= 3 * ec.GRID
               for t in gnd_tracks), gnd_tracks
    gnd_vias = [v for v in plan["vias"] if v["net"] == "GND"]
    assert len(gnd_vias) == 2
    assert all(v.get("plane_layer") == 2 for v in gnd_vias)
    assert ec.connectivity_from_plan(board, plan) == []


def test_plane_layer_is_reserved_for_the_plane():
    board = make_board([
        comp("R1", 300, 300, [("1", "GND", 300, 300)]),
        comp("R2", 1200, 300, [("1", "GND", 1200, 300)]),
        comp("R3", 300, 1100, [("1", "A", 300, 1100)]),
        comp("R4", 1200, 1100, [("1", "A", 1200, 1100)]),
    ])
    (_u, _c), routed, _f = ec.route(board, iters=1, layers=4, segment_check=True,
                                    plane_nets=frozenset({"GND"}), plane_layer=2)
    plan = ec.plan_from(board, routed)
    assert plan["tracks"], "the signal net should still be routed somewhere"
    assert [t for t in plan["tracks"] if t["layer"] == 2] == []


def test_via_counts_as_copper_on_every_layer():
    """A through-hole via is copper on all layers, so it must clash with a track
    on ANY layer and with other nets' pads — otherwise plane vias were free."""
    board = make_board([comp("R1", 300, 300, [("1", "A", 300, 300)])])
    plan = {"tracks": [{"net": "B", "layer": 2, "width": 7,
                        "x1": 480, "y1": 515, "x2": 520, "y2": 515}],
            "vias": [{"net": "A", "x": 500, "y": 500}]}
    assert ec.clearance_violations(board, plan) > 0

    plan["tracks"][0]["y1"] = plan["tracks"][0]["y2"] = 700   # now 200 mil away
    assert ec.clearance_violations(board, plan) == 0


# ── clearance breakdown: which kind of hit is it? ────────────────────────────
def test_clearance_breakdown_names_track_track():
    board = make_board([comp("R1", 300, 300, [("1", "A", 300, 300)])])
    plan = {"tracks": [
        {"net": "A", "layer": 1, "width": 8, "x1": 300, "y1": 300, "x2": 800, "y2": 300},
        {"net": "B", "layer": 1, "width": 8, "x1": 300, "y1": 302, "x2": 800, "y2": 302},
    ], "vias": []}
    br = ec.clearance_breakdown(board, plan)
    # B's track also passes right over A's pad, so the breakdown reports both the
    # track/track pair and the track/pad pair: the KPI is the sum of kinds.
    assert br["counts"] == {"track_track": 1, "track_pad": 1}
    assert br["total"] == 2 == ec.clearance_violations(board, plan)
    assert br["samples"][0]["kind"] == "track_track"
    assert br["samples"][0]["need"] == pytest.approx(13.5, abs=1e-6)


def test_clearance_breakdown_separates_via_over_pad_from_via_over_track():
    board = make_board([comp("R1", 300, 300, [("1", "A", 300, 300)]),
                        comp("R2", 900, 300, [("1", "B", 900, 300)])])
    # via of A close to B's pad, nothing else near
    plan = {"tracks": [], "vias": [{"net": "A", "x": 900, "y": 315}]}
    br = ec.clearance_breakdown(board, plan)
    assert br["counts"].get("via_pad") == 1
    assert br["counts"].get("via_track", 0) == 0

    # same via, but now a track of B runs 15 mil away on another layer
    plan = {"tracks": [{"net": "B", "layer": 3, "width": 7,
                        "x1": 870, "y1": 385, "x2": 930, "y2": 385}],
            "vias": [{"net": "A", "x": 900, "y": 400}]}
    br = ec.clearance_breakdown(board, plan)
    assert br["counts"].get("via_track") == 1
    assert br["counts"].get("via_pad", 0) == 0


def test_clearance_breakdown_also_checks_track_over_pad():
    """The gate used to count track/track, via/track and via/pad only, so a track
    laid straight across another net's pad scored zero.  It is now a real
    violation in the KPI (`track_pad`), and the breakdown names it."""
    board = make_board([comp("R1", 200, 300, [("1", "A", 200, 300)]),
                        comp("R2", 400, 300, [("1", "B", 400, 300)])])
    plan = {"tracks": [{"net": "A", "layer": 1, "width": 8,
                        "x1": 200, "y1": 300, "x2": 600, "y2": 300}], "vias": []}
    br = ec.clearance_breakdown(board, plan)
    assert br["counts"].get("track_pad") == 1
    assert ec.clearance_violations(board, plan) == 1   # counted by the gate

    # the same pad is not in the way on a layer it is not plated on
    plan["tracks"][0]["layer"] = 2
    assert ec.clearance_breakdown(board, plan)["counts"].get("track_pad", 0) == 0
    assert ec.clearance_violations(board, plan) == 0


def test_clearance_breakdown_treats_through_hole_pads_as_every_layer():
    board = ec.Board({"result": {"components": [
        {"designator": "J1", "x": 400, "y": 300, "rotation": 0,
         "bbox": {"minX": 350, "minY": 250, "maxX": 450, "maxY": 350},
         "pads": [{"padNumber": "1", "net": "B", "x": 400, "y": 300,
                   "width": 20, "height": 20, "layer": 12}]},
    ], "outline": {"bbox": {"minX": 0, "minY": 0, "maxX": 2000, "maxY": 1500}}}})
    plan = {"tracks": [{"net": "A", "layer": 4, "width": 8,
                        "x1": 380, "y1": 300, "x2": 420, "y2": 300}], "vias": []}
    assert ec.clearance_breakdown(board, plan)["counts"].get("track_pad") == 1


# ── pour trim must not buy islands with spacing ──────────────────────────────
def _trim_fixture():
    board = make_board([comp("U1", 300, 300, [("1", "A", 300, 300),
                                              ("2", "A", 1500, 300),
                                              ("3", "A", 900, 700)])])
    routed = {"A": [[(30, 30, 4), (150, 30, 4)]]}      # long run on the pour layer
    return board, routed


def test_trim_refuses_a_reroute_that_costs_more_spacing(monkeypatch):
    """The trimmed re-route only avoids cells another net owns, so it used to be
    allowed to hug a neighbour: 130 track/track violations against 5 without the
    trim.  When the new path is closer to foreign copper, the old one stays."""
    board, routed = _trim_fixture()
    old = routed["A"]

    calls = {"n": 0}

    def fake(_b, _path, _others, _net, _width, count=False):
        calls["n"] += 1
        return 0 if calls["n"] == 1 else 3         # old path clean, new paths dirty

    monkeypatch.setattr(ec, "path_conflicts", fake)
    trimmed, _removed = ec.trim_pour_crossings(board, routed, {4}, limit_cells=1, layers=4)
    assert trimmed == 0
    assert routed["A"] is old, "the pour must not be bought with a spacing violation"


def test_trim_still_takes_a_reroute_that_is_clean(monkeypatch):
    board, routed = _trim_fixture()
    old = routed["A"]
    monkeypatch.setattr(ec, "path_conflicts",
                        lambda *_a, **_kw: 0)
    trimmed, removed = ec.trim_pour_crossings(board, routed, {4}, limit_cells=1, layers=4)
    assert trimmed == 1
    assert routed["A"] is not old
    assert removed > 0


# ── an access via inside an isolated pour pocket is a dead pad ───────────────
def _pocket_fixture():
    """+3V3 poured on layer 4; a foreign track traces a closed square, isolating a
    pocket that contains one access via, while another via sits in the main pour.

    Mils throughout: the square runs (700,700)-(800,800), the pocket via is at
    (750,750) inside it, the other at (200,200) in the open pour.
    """
    board = make_board([comp("U1", 795, 795, [("1", "+3V3", 795, 795)]),
                        comp("U2", 200, 200, [("1", "+3V3", 200, 200)])], bbox=(0, 0, 1000, 1000))
    wall = [(70, 70, 4), (80, 70, 4), (80, 80, 4), (70, 80, 4), (70, 70, 4)]
    routed = {
        "B": [wall],
        "+3V3": [[(75, 75, 1), (75, 75, 1)]],
        ec.PLANE_VIA_KEY: [
            {"net": "+3V3", "x": 795, "y": 795, "plane_layer": 4},   # inside the pocket
            {"net": "+3V3", "x": 205, "y": 205, "plane_layer": 4},   # main pour
        ],
    }
    return board, routed


def test_island_via_is_rescued_into_the_main_pour():
    board, routed = _pocket_fixture()
    before = ec.pour_islands(board, ec.plan_from(board, routed))
    assert before == 1, "fixture must start with a genuinely isolated pocket"

    moved = ec.rescue_island_vias(board, routed, layers=4)
    assert moved == 1
    via = routed[ec.PLANE_VIA_KEY][0]
    assert board.cell(via["x"], via["y"]) not in {
        (x, y) for x in range(69, 82) for y in range(69, 82)}
    assert ec.pour_islands(board, ec.plan_from(board, routed)) == 0


def test_pour_island_report_names_the_layer_cutters_and_stranded_via():
    """A count cannot be acted on: the report must say which layer is cut, how big
    the pocket is, which nets cut it and which access via is stranded in it."""
    board, routed = _pocket_fixture()
    rep = ec.pour_island_report(board, ec.plan_from(board, routed))
    assert list(rep) == [4]
    info = rep[4]
    assert len(info["sizes"]) == 2 and min(info["sizes"]) > 0
    assert set(info["cutters"]) == {"B"}
    assert [v["net"] for v in info["dead_vias"]] == ["+3V3"]

    # a pour with no stranded via is not an island the gate should act on
    routed[ec.PLANE_VIA_KEY][0]["x"] = routed[ec.PLANE_VIA_KEY][1]["x"]
    routed[ec.PLANE_VIA_KEY][0]["y"] = routed[ec.PLANE_VIA_KEY][1]["y"]
    assert ec.pour_island_report(board, ec.plan_from(board, routed)) == {}






# ── the routing stack is not always 4 layers ─────────────────────────────────
def test_via_checks_every_layer_of_the_routed_stack():
    """A via is a through-hole, so it must be checked against the stack being
    routed.  These checks were hardcoded to four layers while `--layers N` accepted
    any stack, which would have made layers 5 and 6 free copper on a 6-layer run."""
    used = {(10, 10, 6): {"B"}}
    via_path = [(10, 10, 1), (10, 10, 6)]
    assert ec._via_cells_clear(via_path, used, "A", layers=6) is False
    assert ec._via_cells_clear(via_path, used, "A", layers=4) is True   # the old hole

    occ = {(10, 10, 6): {"B"}}
    assert ec._via_site_ok(occ, "A", (10, 10), layers=6) is False
    assert ec._via_site_ok(occ, "A", (10, 10), layers=4) is True


def test_route_records_the_stack_it_routed_on():
    board = make_board([comp("R1", 300, 300, [("1", "A", 300, 300)]),
                        comp("R2", 900, 300, [("1", "A", 900, 300)])])
    assert board.route_layers == 4
    ec.route(board, iters=2, layers=6, segment_check=True)
    assert board.route_layers == 6
    assert list(ec._all_layers(board)) == [1, 2, 3, 4, 5, 6]


# ── explicit net -> layer assignment (stackup experiments) ───────────────────
def test_layer_pref_overrides_the_default_bus_mapping():
    board = make_board([comp("R1", 300, 300, [("1", "CAM_D0", 300, 300)])])
    assert ec.preferred_layer("CAM_D0", 6, board) == 3        # default mapping
    board.layer_pref = {"CAM_D0": 6}
    assert ec.preferred_layer("CAM_D0", 6, board) == 6         # explicit assignment
    assert ec.preferred_layer("LCD_CS", 6, board) == 4         # untouched net keeps its layer


def test_route_follows_an_explicit_layer_map():
    board = make_board([comp("R1", 300, 300, [("1", "A", 300, 300)]),
                        comp("R2", 1300, 300, [("1", "A", 1300, 300)])])
    (_u, _c), routed, _f = ec.route(board, iters=2, layers=6, segment_check=True,
                                    layer_map={"A": 5}, layer_force=True)
    plan = ec.plan_from(board, routed)
    assert plan["tracks"], "the net must still route"
    layers = {int(t["layer"]) for t in plan["tracks"]}
    assert 5 in layers, "the mapped layer must carry the run"
    assert layers <= {1, 5}, "only the pad layer and the mapped layer are allowed"


def test_layer_spread_deals_nets_over_free_layers_deterministically():
    """A 6-layer run that never touches L5/L6 cannot answer a stackup question, so
    the spread has to be real, deterministic, and must leave buses and pours alone."""
    comps = [comp("R%d" % i, 200 + 100 * i, 300,
                  [("1", "SIG_%d" % i, 200 + 100 * i, 300)]) for i in range(6)]
    comps.append(comp("R9", 400, 600, [("1", "CAM_D0", 400, 600)]))
    comps.append(comp("R8", 400, 900, [("1", "+3V3", 400, 900)]))
    board = make_board(comps)
    ec.route(board, iters=2, layers=6, pour_specs=["GND:2", "+3V3:6"], layer_spread=True)
    pref = board.layer_pref
    assert "CAM_D0" not in pref and "+3V3" not in pref and "GND" not in pref
    assert pref and set(pref.values()) <= {1, 3, 4, 5, 6}
    assert not (set(pref.values()) & {2, 6}), "2 and 6 are poured, nets must stay off them"

    board2 = make_board(comps)
    ec.route(board2, iters=2, layers=6, pour_specs=["GND:2", "+3V3:6"], layer_spread=True)
    assert board2.layer_pref == pref, "the spread must be deterministic"




# ── the delivery contract itself (fast, no routing) ─────────────────────────
def _mod(name, filename):
    import importlib.util as _ilu
    spec = _ilu.spec_from_file_location(name, MOD_PATH.parent / filename)
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_acceptance_green_kpi_is_actually_green():
    """The acceptance script pairs the REAL plan with a KPI whose gated items are at
    target, to prove the emit path works.  That stub must pass the same gate the real
    KPI fails, or the script would 'prove' nothing."""
    emit = _mod("emit_apply_gate", "emit_apply.py")
    acc = _mod("acceptance", "acceptance.py")
    red = {"unrouted_legs": 0, "congestion_cells": 0, "clearance_violations": 515,
           "nets_unconnected": 0, "pad_layer_gaps": 0, "pour_islands": 1,
           "bus_length_spread_mil": {"CAM_D": 713.1, "LCD_": 165.3, "SD_": 297.6}}
    assert emit.gate_reasons(red), "the fixture must start red"
    assert emit.gate_reasons(acc.green_kpi(red)) == []


def test_acceptance_script_refuses_a_red_plan_then_emits_a_green_one(tmp_path):
    import subprocess
    plan = {"grid": 10, "tracks": [], "vias": []}
    (tmp_path / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
    (tmp_path / "kpi.json").write_text(json.dumps({
        "unrouted_legs": 0, "congestion_cells": 0, "clearance_violations": 3,
        "nets_unconnected": 0, "pad_layer_gaps": 0, "pour_islands": 0,
        "bus_length_spread_mil": {"CAM_D": 80.0, "LCD_": 10.0, "SD_": 10.0},
    }), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(MOD_PATH.parent / "acceptance.py"),
         "--plan", str(tmp_path / "plan.json"), "--kpi", str(tmp_path / "kpi.json"),
         "--skip-tests"],
        capture_output=True, text=True)
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, out
    assert "REFUSED" in out and "emitted" in out
    assert "contract: PASS" in out


# ── the portfolio ranks by the gate's order, not by what looks good ─────────
def test_portfolio_ranks_by_gate_order():
    pf = _mod("portfolio", "portfolio.py")

    def row(name, skew_max=0.0, **kw):
        kpi = {k: 0 for k in ("unrouted_legs", "nets_unconnected", "congestion_cells",
                              "pad_layer_gaps", "pour_islands",
                              "clearance_violations", "vias", "total_length_mil")}
        kpi.update(kw)
        return {"variant": name, "kpi": kpi, "skew": {}, "skew_max": skew_max,
                "ok": False, "gate_fail": []}

    # a dead leg beats every cosmetic advantage of the other run
    dead = row("dead", unrouted_legs=1, clearance_violations=0)
    clean = row("clean", unrouted_legs=0, clearance_violations=600)
    assert pf.rank_key(clean) < pf.rank_key(dead)
    # ... and an overlap (a short) is worse than a spacing violation
    overlap = row("overlap", congestion_cells=1)
    spacing = row("spacing", clearance_violations=40)
    assert pf.rank_key(spacing) < pf.rank_key(overlap)
    # pour continuity ranks before raw spacing, per the documented rule
    island = row("island", pour_islands=1, clearance_violations=0)
    messy = row("messy", pour_islands=0, clearance_violations=500)
    assert pf.rank_key(messy) < pf.rank_key(island)

    text, order = pf.table([dead, clean, overlap, spacing, island, messy])
    assert order[0]["variant"] == "spacing", text          # 40 < 500 < 600
    assert text.index("clean") < text.index("dead")
    assert order[-1]["variant"] == "dead"



def test_spacing_audit_groups_violations_by_owner():
    """A count has no owner.  The grouping must name the net that runs over a pad and
    the pad that got run over, so the fix has an address."""
    import importlib.util as _ilu
    spec = _ilu.spec_from_file_location("spacing_audit", MOD_PATH.parent / "spacing_audit.py")
    sa = _ilu.module_from_spec(spec)
    sys.path.insert(0, str(MOD_PATH.parent))
    spec.loader.exec_module(sa)

    board = make_board([comp("R1", 200, 300, [("1", "A", 200, 300)]),
                        comp("R2", 400, 300, [("1", "B", 400, 300)])])
    plan = {"tracks": [{"net": "A", "layer": 1, "width": 8,
                        "x1": 200, "y1": 300, "x2": 600, "y2": 300}],
            "vias": [{"net": "A", "x": 400, "y": 320}]}
    g = sa.group_violations(board, plan)
    assert g["track_pad_total"] == 1 and g["distinct_track_pad_pairs"] == 1
    assert g["track_pad_by_track_net"][0] == ("A", 1)
    assert g["track_pad_violated_pads"][0] == ("R2.1", 1)
    assert g["track_pad_pairs"][0][0] == "A -> R2.1"
    assert g["via_hits_by_net"][0] == ("A", 1)          # the via is 20 mil from R2.1


# ── how much of the spacing KPI can no layout change of the router remove? ───
def test_forced_spacing_separates_impossible_from_avoidable():
    """A track between two pads whose gap is smaller than the corridor a track needs
    cannot be legal anywhere: that hit is FORCED.  A track that merely runs too close
    to an isolated pad is the router's to avoid."""
    fs = _mod("forced_spacing", "forced_spacing.py")

    def comp_pads(des, pads):
        c = comp(des, pads[0][2], pads[0][3], [(p, n, x, y) for (p, n, x, y) in pads])
        return c

    # J9: two pads 19.7 mil apart with 49 mil height -> no corridor between them
    tight = make_board([comp_pads("J9", [("1", "A", 400, 300), ("2", "B", 400, 320)])])
    for p in tight.comps["J9"]["pads"]:
        p["w"], p["h"] = 11.8, 49.2
    pairs = fs.no_corridor_pairs(tight)
    assert any(k[0] == "J9" for k in pairs), pairs

    plan = {"tracks": [{"net": "X", "layer": 1, "width": 7,
                        "x1": 350, "y1": 310, "x2": 450, "y2": 310}], "vias": []}
    res = fs.classify(tight, plan)
    assert res["forced"], "a track squeezed between two 19.7 mil pads is forced"
    assert not res["open"]

    # an isolated pad with room around it: the same kind of hit is avoidable
    loose = make_board([comp_pads("R9", [("1", "B", 400, 400)])])
    for p in loose.comps["R9"]["pads"]:
        p["w"], p["h"] = 20, 20
    assert fs.no_corridor_pairs(loose) == {}
    res = fs.classify(loose, {"tracks": [{"net": "X", "layer": 1, "width": 7,
                                          "x1": 380, "y1": 410, "x2": 440, "y2": 410}],
                              "vias": []})
    assert res["open"] and not res["forced"]


# ── the via clearance the router enforces is a knob, not a constant ─────────
def test_via_margin_widens_the_reserved_disc_and_is_recorded():
    """The router has only ever been run at the two extremes (overlap-only 1.0 and
    full clearance 6.0, which was unroutable).  A middle value must actually reserve
    more cells, and the run must record what it used."""
    board = make_board([comp("R1", 300, 300, [("1", "A", 300, 300)]),
                        comp("R2", 900, 300, [("1", "A", 900, 300)])])
    # The 10 mil grid QUANTISES this knob: for a 7 mil track the disc only changes
    # when the required reach crosses a cell boundary, so margins 1..5 reserve the
    # same 9 cells and there is no "slightly stricter" middle ground.
    discs = {}
    for margin in (1.0, 3.0, 4.0, 6.0):
        block = {}
        ec.stamp_via_block(block, [(10, 10, 1)], "A", 7, margin=margin)
        discs[margin] = len(block)
    assert discs[1.0] == discs[3.0] == discs[4.0] == 9
    assert discs[6.0] > discs[1.0], discs

    ec.route(board, iters=2, layers=4, segment_check=True, via_sites=True, via_margin=4.0)
    assert board.via_margin == 4.0
    ec.route(board, iters=2, layers=4, segment_check=True)
    assert board.via_margin == ec.VIA_BLOCK_MARGIN



# ── the routing grid is the quantum of every clearance decision ─────────────
def test_grid_experiment_loads_the_same_code_at_half_the_grid():
    """Half the grid must mean twice the cells and a correct cell<->mil round trip,
    otherwise a 'finer grid' run would silently be a different board."""
    ge = _mod("grid_experiment", "grid_experiment.py")
    ec10 = ge.load_module(10)
    ec5 = ge.load_module(5)
    assert ec10.GRID == 10 and ec5.GRID == 5
    dump = {"result": {"components": [], "outline": {
        "bbox": {"minX": 0, "minY": 0, "maxX": 1000, "maxY": 1000}}}}
    b10, b5 = ec10.Board(dump), ec5.Board(dump)
    assert (b5.w, b5.h) == (2 * b10.w, 2 * b10.h)
    for cell in ((3, 4), (17, 9)):
        assert b5.cell(*b5.center(*cell)) == cell
    # the production module is untouched
    assert ec.GRID == 10.0


def test_best_effort_budget_scales_with_the_grid():
    """The budget counts conflicting segment PAIRS; both the candidate and the copper
    it fights get denser as the grid shrinks, so at half the grid the same physical
    situation is four times the count.  At the recorded 10 mil it must stay 2."""
    assert ec._best_effort_budget() == ec.BEST_EFFORT_MAX_CONFLICTS == 2
    ge = _mod("grid_experiment", "grid_experiment.py")
    ec5 = ge.load_module(5)
    assert ec5._best_effort_budget() == 8          # (10/5)^2 = 4x
    ec20 = ge.load_module(20)
    assert ec20._best_effort_budget() >= 1          # never below one pair


def test_reproduce_can_switch_the_routing_grid():
    """D6 compares 10 mil against 5 mil; both points must come out of the SAME
    scorecard path, so reproduce rebinds its module instead of having a second tool."""
    rep = _mod("reproduce_grid", "reproduce.py")
    assert rep.ec.GRID == 10.0
    rep.use_grid(5)
    try:
        assert rep.ec.GRID == 5.0
        assert rep.ec._best_effort_budget() == 8
    finally:
        rep.use_grid(10)
    assert rep.ec.GRID == 10.0
    assert rep.ec._best_effort_budget() == 2


def test_per_net_class_budget_splits_buses_from_the_rest():
    """A finer grid makes the BUSES the worst offender (track/track 8 -> 45), so the
    budget has to be settable per net class.  Both None must reproduce the single
    global budget exactly, or the recorded frontier would move silently."""
    import inspect
    src = inspect.getsource(ec.route)
    assert "_budget_for(net)" in src, "the acceptance test must use the per-net budget"
    assert "best_bad <= _budget_for(net)" in src
    # the default path still reduces to the global budget
    assert ec._best_effort_budget() == ec.BEST_EFFORT_MAX_CONFLICTS


def test_via_cost_scales_with_the_grid():
    """VIA_COST is in grid cells; at half the grid the same number is half the physical
    distance, which silently made vias cheaper at 5 mil (measured: more vias, more
    via/track hits).  The cost must be the same physical trade at any grid."""
    ge = _mod("grid_experiment", "grid_experiment.py")
    ec5 = ge.load_module(5)
    # astar itself is the only consumer; compare what a via costs on each grid
    assert ec._best_effort_budget() == 2              # 10 mil default untouched
    assert ec5._best_effort_budget() == 8
    import inspect
    src10 = inspect.getsource(ec.astar)
    src5 = inspect.getsource(ec5.astar)
    assert "10.0 / GRID" in src10 and "10.0 / GRID" in src5


def test_reproduce_cli_flags_reach_the_route_config(monkeypatch):
    """A knob that is accepted by argparse but never copied into the profile is a
    silent no-op: that is exactly how one grid-5 experiment "measured" identical
    numbers twice.  Every override flag must land in the config."""
    rep = _mod("reproduce_cli", "reproduce.py")
    seen = {}

    def fake_run(dump, place, out_dir=None, profile="frontier"):
        seen["cfg"] = dict(rep.PROFILES[profile])
        kpi = {k: 0 for k in ("unrouted_legs", "congestion_cells", "clearance_violations",
                             "nets_unconnected", "pad_layer_gaps", "pour_islands",
                             "vias", "plane_vias", "vias_in_pad", "tracks",
                             "total_length_mil", "diagonal_ratio")}
        kpi["bus_length_spread_mil"] = {}
        return kpi, {}, True, set(), {}

    monkeypatch.setattr(rep, "run", fake_run)
    monkeypatch.setattr(sys, "argv", [
        "reproduce.py", "--dump", "d.json", "--place", "p.json",
        "--grid", "5", "--best-effort-budget", "30",
        "--via-sites", "--via-margin", "6", "--bus-budget", "8", "--iters", "25"])
    rep.main()
    cfg = seen["cfg"]
    assert cfg["general_budget"] == 30
    assert cfg["bus_budget"] == 8
    assert cfg["via_sites"] is True
    assert cfg["via_margin"] == 6
    assert cfg["iters"] == 25



def test_profile_can_carry_its_grid():
    """A profile is a (grid, knobs) pair: `strict-via` must switch the module itself,
    otherwise the same command gives two different frontiers depending on whether the
    caller remembered --grid."""
    rep = _mod("reproduce_gridprof", "reproduce.py")
    assert rep.PROFILES["strict-via"]["grid"] == 5
    rep.use_grid(None)
    assert rep.ec.GRID == 10.0
    rep.use_grid(rep.PROFILES["strict-via"]["grid"])
    try:
        assert rep.ec.GRID == 5.0
    finally:
        rep.use_grid(10)
    assert rep.ec.GRID == 10.0


def test_the_best_measured_point_is_the_default_profile():
    """A plain `reproduce.py` call must give the best point, not the older 10 mil one -
    otherwise every agent that follows the docs reproduces yesterday's frontier."""
    import inspect
    rep = _mod("reproduce_default", "reproduce.py")
    assert inspect.signature(rep.run).parameters["profile"].default == "strict-via"
    assert rep.FRONTIER is rep.PROFILES["strict-via"]
    assert rep.PROFILES["strict-via"]["grid"] == 5
    assert rep.PROFILES["strict-via"]["via_sites"] is True
    assert rep.PROFILES["strict-via"]["general_budget"] == 56
    # the fast comparison is still one word away
    assert "frontier-10mil" in rep.PROFILES
    assert rep.PROFILES["frontier-10mil"].get("grid") is None      # stays at 10 mil
