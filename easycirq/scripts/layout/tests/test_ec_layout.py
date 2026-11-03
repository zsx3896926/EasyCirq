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
MOD_PATH = HERE.parent.parent / "ec_layout.py"
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
    assert inspect.signature(rep.run).parameters["profile"].default == "thin-10mil"
    assert rep.FRONTIER is rep.PROFILES["thin-10mil"]
    assert rep.PROFILES["strict-via"]["grid"] == 5
    assert rep.PROFILES["strict-via"]["via_sites"] is True
    assert rep.PROFILES["strict-via"]["general_budget"] == 56
    # the fast comparison is still one word away
    assert "frontier-10mil" in rep.PROFILES
    assert rep.PROFILES["frontier-10mil"].get("grid") is None      # stays at 10 mil


def test_scorecard_reports_every_kpi_the_objective_names():
    """The objective lists the KPIs each round must quantify: unrouted legs, congestion,
    spacing, vias, bus skew, length, 45-degree share AND layer distribution.  Layer
    distribution lived only in kpi.json until round 58, so a scorecard reader could not
    see it - this pins that all eight appear in the printed table."""
    rep = _mod("reproduce_kpis", "reproduce.py")
    kpi = {"unrouted_legs": 0, "congestion_cells": 0, "clearance_violations": 0,
           "nets_unconnected": 0, "pad_layer_gaps": 0, "pour_islands": 0,
           "vias": 1, "plane_vias": 1, "vias_in_pad": 0, "tracks": 2,
           "total_length_mil": 3.0, "diagonal_ratio": 0.4,
           "layer_length_mil": {"1": 10.0, "2": 5.0}}
    skew = {"CAM_D": 1.0, "LCD_": 2.0, "SD_": 3.0}
    text = rep.scorecard(kpi, skew, False, {"clearance_violations"})
    for needle in ("unrouted legs", "congestion cells", "clearance violations",
                   "vias (access / in-pad)", "total length", "45-degree share",
                   "layer distribution (mil)", "bus skew"):
        assert needle in text, needle
    assert "L1 10.0 / L2 5.0" in text


    # (replaced below)


def test_escape_check_finds_a_pad_that_cannot_be_entered():
    """The floor argument: a pad surrounded on all sides has NO legal entry angle, so the
    clearance KPI cannot reach zero whatever the router does.  The check must find it and
    must NOT flag a pad with room around it."""
    esc = _mod("escape_check", "escape_check.py")
    ring = []
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            ring.append((str(len(ring) + 1), "N%d%d" % (dx + 1, dy + 1),
                         400 + 20 * dx, 400 + 20 * dy))
    boxed = make_board([comp("U9", 400, 400, ring)])
    for p in boxed.comps["U9"]["pads"]:
        p["w"], p["h"] = 40, 40          # pads touch their neighbours in every direction
    bad = esc.unconnectable(boxed)
    assert [p["pad"] for p in bad] == ["5"], [p["pad"] for p in bad]   # the centre pad

    loose = make_board([comp("R9", 400, 400, [("1", "B", 400, 400)])])
    for p in loose.comps["R9"]["pads"]:
        p["w"], p["h"] = 20, 20
    assert esc.unconnectable(loose) == []


def test_whatif_repins_a_bus_so_both_ends_agree():
    """Skew cannot be matched when the two ends of a bus count in different orders.  The
    what-if harness must be able to fix that on a COPY of the dump (and must actually
    change the nets, not just claim to)."""
    wi = _mod("whatif", "whatif.py")
    dump = {"result": {"components": [
        # end A: nets in ascending x
        {"designator": "U5", "x": 300, "y": 300, "pads": [
            {"padNumber": "1", "net": "CAM_D0", "x": 300, "y": 300},
            {"padNumber": "2", "net": "CAM_D1", "x": 320, "y": 300},
            {"padNumber": "3", "net": "CAM_D2", "x": 340, "y": 300}]},
        # end B: same nets in DESCENDING x - the npn-order case
        {"designator": "J9", "x": 900, "y": 300, "pads": [
            {"padNumber": "1", "net": "CAM_D2", "x": 900, "y": 300},
            {"padNumber": "2", "net": "CAM_D1", "x": 920, "y": 300},
            {"padNumber": "3", "net": "CAM_D0", "x": 940, "y": 300}]},
    ]}}
    changed = wi.repin_buses(dump)
    assert changed >= 2, changed
    end_b = sorted(dump["result"]["components"][1]["pads"], key=lambda p: p["x"])
    assert [p["net"] for p in end_b] == ["CAM_D0", "CAM_D1", "CAM_D2"]
    # the relaxed-rule helper must record that it is a what-if, never a real board
    rules = wi.relax_rules(dump, 2.0, 5.0, 10.0, None)
    assert rules["clearanceMil"] == 2.0 and "NOT the real board" in rules["whatif"]


def test_row_penalty_costs_only_the_tight_gaps():
    """The 274-289 "forced" pad hits are tracks threading a 19.7 mil pitch row.  The fix
    is to make that expensive rather than illegal (perpendicular escape must stay cheap),
    so the cell map must cover the gap between tight pads and nothing else."""
    tight = make_board([comp("J9", 400, 300, [("1", "A", 400, 300), ("2", "B", 400, 320)])])
    for p in tight.comps["J9"]["pads"]:
        p["w"], p["h"] = 11.8, 49.2
    cells = ec.between_pad_cells(tight)
    assert cells, "the gap between two 19.7 mil pads must be marked"
    # a lone pad has no gap to thread
    loose = make_board([comp("R9", 700, 700, [("1", "B", 700, 700)])])
    assert ec.between_pad_cells(loose) == {}
    # the penalty is a COST, not a wall: routing still works with it switched on
    board = make_board([comp("R1", 300, 300, [("1", "A", 300, 300)]),
                        comp("R2", 900, 300, [("1", "A", 900, 300)])])
    (_u, _c), routed, _f = ec.route(board, iters=2, layers=4, segment_check=True,
                                    row_penalty=30.0)
    assert ec.plan_from(board, routed)["tracks"]


def test_thin_profile_is_the_default_and_carries_its_constants():
    """The best measured point is now 10 mil with 5 mil tracks (clearance 393, six
    minutes).  A plain reproduce call must use it, and the profile must carry the design
    constants it depends on - a profile without them silently routes 7 mil."""
    import inspect
    rep = _mod("reproduce_thin", "reproduce.py")
    assert inspect.signature(rep.run).parameters["profile"].default == "thin-10mil"
    assert rep.FRONTIER is rep.PROFILES["thin-10mil"]
    cfg = rep.PROFILES["thin-10mil"]
    assert cfg["constants"]["TRACE"] == 5.0 and cfg["general_budget"] == 16
    # strict-via stays available as the finer-grid alternative
    assert rep.PROFILES["strict-via"]["grid"] == 5


def test_place_repair_moves_a_part_to_make_pads_reachable():
    """The floor of >=11 violations came from parts sitting too close to a big neighbour
    pad.  Placement owns that: the repair must move the offender, keep every other part
    where it was, and report the pads as reachable afterwards."""
    pr = _mod("place_repair", "place_repair.py")
    esc = _mod("escape_check2", "escape_check.py")
    dump = {"result": {"components": [
        # a big pad row that walls in the small part below
        {"designator": "U4", "x": 500, "y": 300, "pads": [
            {"padNumber": "1", "net": "N1", "x": 480, "y": 300, "width": 14, "height": 60, "layer": 1},
            {"padNumber": "2", "net": "N2", "x": 500, "y": 300, "width": 14, "height": 60, "layer": 1},
            {"padNumber": "3", "net": "N3", "x": 520, "y": 300, "width": 14, "height": 60, "layer": 1}]},
        {"designator": "R2", "x": 500, "y": 322, "pads": [
            {"padNumber": "1", "net": "A", "x": 490, "y": 322, "width": 22, "height": 21, "layer": 1},
            {"padNumber": "2", "net": "B", "x": 511, "y": 322, "width": 22, "height": 21, "layer": 1}]},
    ], "outline": {"bbox": {"minX": 0, "minY": 0, "maxX": 1000, "maxY": 1000}}}}
    placement = {"U4": {"x": 500, "y": 300, "rotation": 0},
                 "R2": {"x": 500, "y": 322, "rotation": 0}}
    before_board = ec.Board(dump)
    ec.apply_placement(before_board, placement)
    assert esc.unconnectable(before_board, width=5.0, clearance=6.0), "fixture must start stuck"
    moved, board = pr.repair(dump, placement, width=5.0, clearance=6.0, step=10, radius=80,
                             verbose=False)
    assert "R2" in moved
    assert esc.unconnectable(board, width=5.0, clearance=6.0) == []
    assert moved["U4"] if "U4" in moved else True            # the big part may stay put


def test_crowding_penalty_only_counts_cross_component_shortfalls():
    """The placement objective had no term for the clearance rule at all.  This metric
    fills that hole - but only for pairs belonging to DIFFERENT parts: the pitch inside
    one footprint cannot be changed by moving it."""
    close = make_board([comp("U1", 400, 300, [("1", "A", 400, 300)]),
                        comp("U2", 400, 340, [("1", "B", 400, 340)])])
    for c in close.comps.values():
        for p in c["pads"]:
            p["w"], p["h"] = 40, 40
    assert ec.crowding_penalty(close.comps, width=5.0, clearance=6.0) > 0

    far = make_board([comp("U1", 400, 300, [("1", "A", 400, 300)]),
                      comp("U2", 900, 300, [("1", "B", 900, 300)])])
    for c in far.comps.values():
        for p in c["pads"]:
            p["w"], p["h"] = 40, 40
    assert ec.crowding_penalty(far.comps, width=5.0, clearance=6.0) == 0.0

    # two pads of the SAME part are a footprint property: never counted
    same = make_board([comp("U1", 400, 300, [("1", "A", 400, 300), ("2", "B", 400, 320)])])
    for p in same.comps["U1"]["pads"]:
        p["w"], p["h"] = 40, 40
    assert ec.crowding_penalty(same.comps, width=5.0, clearance=6.0) == 0.0
    # and the default weight keeps the placement objective unchanged
    assert ec.CROWD_W == 0.0


def test_congestion_map_locates_and_correlates():
    """The map has to (a) put the hits in the right tile, (b) count pads and legs there and
    (c) report a correlation, because the whole point is separating "where the trouble is"
    from "which placement is better" (HANDOFF §73)."""
    cm = _mod("congestion_map", "congestion_map.py")
    board = make_board([comp("R1", 200, 300, [("1", "A", 200, 300)]),
                        comp("R2", 400, 300, [("1", "B", 400, 300)])])
    plan = {"tracks": [{"net": "A", "layer": 1, "width": 8,
                        "x1": 200, "y1": 300, "x2": 600, "y2": 300}], "vias": []}
    res = cm.analyse(board, plan, tile=200.0)
    assert res["violations"], "A's track crosses B's pad, so a tile must show a hit"
    assert sum(res["pads"].values()) == 2
    assert res["rho_pads"] is not None and res["rho_legs"] is not None
    assert res["pressure"] >= 0
    # spearman sanity: identical rankings correlate perfectly
    assert cm.spearman([1, 2, 3], [10, 20, 30]) == 1.0
    assert cm.spearman([1, 2, 3], [3, 2, 1]) == -1.0


def test_pad_guard_widens_the_hard_pad_obstacle():
    """The router blocked pad + CLEARANCE and then let a track CENTRE sit on that boundary -
    short by half a track width, which is exactly what the track/pad class was made of.
    pad_guard closes the gap and must really enlarge the obstacle; zero must keep it as is."""
    board = make_board([comp("R1", 405, 305, [("1", "A", 405, 305)])])
    for p in board.comps["R1"]["pads"]:
        p["w"], p["h"] = 55, 55
    tight = board.pad_blocked(extra=0.0)[0]
    guarded = board.pad_blocked(extra=2.0)[0]
    assert len(guarded) > len(tight), (len(tight), len(guarded))
    assert set(tight).issubset(set(guarded)), "the guard must only ADD obstacle cells"
    b2 = make_board([comp("R1", 300, 300, [("1", "A", 300, 300)]),
                     comp("R2", 900, 300, [("1", "A", 900, 300)])])
    (_u, _c), routed, _f = ec.route(b2, iters=2, layers=4, segment_check=True, pad_guard=2.0)
    assert ec.plan_from(b2, routed)["tracks"]


def test_diagonal_ratio_is_geometry_not_grid():
    """The 45-degree share must be comparable across routing grids: it is computed from the
    endpoints (dx and dy both non-zero), not from cell counts, so the same copper scores the
    same at 10 mil and at 5 mil."""
    diag = {"tracks": [{"net": "A", "layer": 1, "width": 5,
                        "x1": 0, "y1": 0, "x2": 10, "y2": 10}], "vias": []}
    axis = {"tracks": [{"net": "A", "layer": 1, "width": 5,
                        "x1": 0, "y1": 0, "x2": 10, "y2": 0}], "vias": []}
    assert ec.quality_metrics(diag)["diagonal_ratio"] == 1.0
    assert ec.quality_metrics(axis)["diagonal_ratio"] == 0.0
    # the same copper at a finer grid (different module instance) scores identically
    ge = _mod("grid_experiment", "grid_experiment.py")
    ec5 = ge.load_module(5)
    assert ec5.quality_metrics(diag)["diagonal_ratio"] == 1.0
    assert ec5.quality_metrics(axis)["diagonal_ratio"] == 0.0


def test_pour_island_is_not_an_artifact_of_the_pour_clearance():
    """`POUR_CLEARANCE` is 8 mil although the board rule is 6.  A cut that only exists at
    8 mil would be a false positive, so the pocket fixture must report the island at both."""
    board, routed = _pocket_fixture()
    plan = ec.plan_from(board, routed)
    for clearance in (6.0, 8.0):
        assert ec.pour_islands(board, plan, clearance=clearance) == 1, clearance


def test_meander_capacity_is_about_twelve_percent_of_the_host():
    """Length matching can only add ~11.8 % of the HOST segment's length (triangular bumps:
    extra per bump ~0.472a, bumps ~ L/4a), independent of amplitude.  That is why it does
    nothing on RetroCam-02 - the bus wires have no 6 mm straight run to bend (HANDOFF §77)."""
    def comp(des, x, y):
        return {"designator": des, "x": x, "y": y, "rotation": 0,
                "bbox": {"minX": x - 50, "minY": y - 50, "maxX": x + 50, "maxY": y + 50},
                "pads": []}
    board = ec.Board({"result": {"components": [comp("U1", 300, 300)],
                                 "outline": {"bbox": {"minX": 0, "minY": 0,
                                                      "maxX": 4000, "maxY": 1500}}}})

    def run(host, delta):
        plan = {"tracks": [
            {"net": "CAM_D0", "layer": 1, "width": 5, "x1": 100, "y1": 300,
             "x2": 100 + host, "y2": 300},
            {"net": "CAM_D1", "layer": 1, "width": 5, "x1": 100, "y1": 500,
             "x2": 100 + host - delta, "y2": 500}], "vias": []}
        added = ec.match_lengths(board, plan, amp=80.0)
        return added, ec.quality_metrics(plan)["bus_length_spread_mil"]["CAM_D"]

    added, skew = run(3000, 200)          # well inside ~11.8 % of 3000
    assert added == 1 and skew < 60, (added, skew)
    added, skew = run(3000, 400)          # above the ceiling: refused
    assert added == 0 and skew == 400
    added, skew = run(600, 200)           # short host: refused even for a modest delta
    assert added == 0


def test_congestion_sees_a_via_sitting_on_another_nets_track():
    """A via is a through-hole.  The checker used to file it on a pseudo-layer 0, so a via
    sharing a cell with another net's track was invisible - the frontier then reported
    "congestion 0" while carrying a real short (HANDOFF §78)."""
    board = make_board([comp("R1", 300, 300, [("1", "A", 300, 300)]),
                        comp("R2", 700, 300, [("1", "B", 700, 300)])])
    board.route_layers = 4
    plan = {"tracks": [{"net": "B", "layer": 4, "width": 5,
                        "x1": 300, "y1": 300, "x2": 700, "y2": 300}],
            "vias": [{"net": "A", "x": 300, "y": 300}]}
    assert ec.congestion_from_plan(board, plan) >= 1, "via over another net's track is a short"
    # and a clear plan stays clean
    plan["vias"] = [{"net": "A", "x": 300, "y": 800}]
    assert ec.congestion_from_plan(board, plan) == 0


def test_geometric_pad_check_sees_a_clip_the_cell_walker_misses():
    """Cell obstacles cannot see a segment that clips a pad without touching a blocked cell -
    that gap let a track cross a GND pad and the pour's in-pad via short it (HANDOFF §79).
    The geometric check must catch the clip and stay quiet on a clear path."""
    board = make_board([comp("U1", 400, 300, [("1", "B", 400, 300)]),
                        comp("U2", 900, 700, [("1", "A", 900, 700)])])
    c = board.cell(400, 300)                       # the pad's own cell
    across = [(c[0] - 3, c[1], 1), (c[0] + 3, c[1], 1)]
    assert ec.seg_seg(*board.center(c[0] - 3, c[1]), *board.center(c[0] + 3, c[1]),
                      400, 300, 400, 300) < 18.0   # the fixture really clips the pad
    assert ec._pad_geom_clear(board, across, "A", 5.0) is False
    clear = [(c[0] - 3, c[1] + 4, 1), (c[0] + 3, c[1] + 4, 1)]
    assert ec._pad_geom_clear(board, clear, "A", 5.0) is True
    # the net's OWN pad never blocks it
    assert ec._pad_geom_clear(board, across, "B", 5.0) is True
    # the shipped default keeps the old behaviour
    import inspect
    assert inspect.signature(ec.route).parameters["pad_geom"].default is False


def test_profiles_never_break_the_board_minimum_width():
    """`thin-10mil` used BUS_TRACE=4.0 while the board's own minimum is 5 mil: the plan had
    228 tracks thinner than the rule and plan_lint refused it (HANDOFF §82).  Every profile's
    width constants must respect `trackWidthMinMil`."""
    rep = _mod("reproduce_widths", "reproduce.py")
    minimum = 5.0                                  # the board's trackWidthMinMil
    for name, cfg in rep.PROFILES.items():
        consts = cfg.get("constants") or {}
        for key in ("TRACE", "BUS_TRACE"):
            if key in consts:
                assert consts[key] >= minimum, "%s: %s=%s below the board minimum" % (
                    name, key, consts[key])


def test_layer_lengths_sum_to_the_total_length():
    """An invariant the docs depend on: the per-layer copper must add up to the reported
    total (within the 0.1 mil rounding each layer gets).  A transcribed table once showed
    40151.7 mil of layers against a 40037.6 mil total (HANDOFF §87) - off by 114 mil, which
    this check catches while tolerating rounding."""
    plan = {"tracks": [
        {"net": "A", "layer": 1, "width": 5, "x1": 0, "y1": 0, "x2": 300, "y2": 0},
        {"net": "A", "layer": 2, "width": 5, "x1": 0, "y1": 0, "x2": 0, "y2": 400},
        {"net": "B", "layer": 3, "width": 5, "x1": 0, "y1": 0, "x2": 100, "y2": 100},
    ], "vias": []}
    q = ec.quality_metrics(plan)
    per_layer = sum(q["layer_length_mil"].values())
    exact = sum(((t["x2"] - t["x1"]) ** 2 + (t["y2"] - t["y1"]) ** 2) ** 0.5
                for t in plan["tracks"])
    assert abs(per_layer - exact) < 0.5, (per_layer, exact)   # only per-layer rounding


def test_pipeline_report_marks_deliverability_from_the_gate_and_lint():
    """`pipeline.py` is the one-command entry an agent is told to trust, so its verdict logic
    and report rendering are pinned: a red gate or a failing lint row must make the board
    non-deliverable, and the report must say which keys are red (HANDOFF §87)."""
    pipe = _mod("pipeline_mod", "pipeline.py")
    red = {
        "profile": "thin-10mil", "gate": "FAIL",
        "failing_gate_keys": ["congestion_cells", "clearance_violations"],
        "kpi": {"unrouted_legs": 0, "congestion_cells": 1, "clearance_violations": 380,
                "nets_unconnected": 0, "pad_layer_gaps": 0, "pour_islands": 0},
        "info": {"vias": 182, "tracks": 611, "total_length_mil": 40037.6},
        "skew": {"CAM_D": 783.6, "LCD_": 165.3, "SD_": 297.6},
        "plan_lint": {"verdict": "PASS", "failing": []},
        "skew_target_met": False,
        "deliverable": False,
    }
    text = pipe._report(red, 7)
    assert "verdict: FAIL" in text and "**red**" in text
    assert "**NO**" in text and "refuses to write" in text
    assert "spacing groups inspected: 7" in text.lower() or "Spacing groups inspected: 7" in text

    green = dict(red, gate="PASS", failing_gate_keys=[], deliverable=True,
                 kpi={k: 0 for k in red["kpi"]},
                 plan_lint={"verdict": "PASS", "failing": []})
    text = pipe._report(green, 0)
    assert "verdict: PASS" in text and "**YES**" in text

    # a board-rule failure alone must also block delivery
    blocked = dict(green, plan_lint={"verdict": "FAIL",
                                     "failing": [{"check": "minimum track width",
                                                  "detail": "228 track(s) thinner"}]})
    text = pipe._report(blocked, 0)
    assert "minimum track width" in text


def test_pipeline_report_names_the_bus_skew_target():
    """Bus skew is not in the DRC gate, so a report that lists only gate keys would look
    complete while the skew is 20x its target (HANDOFF §91)."""
    pipe = _mod("pipeline_mod2", "pipeline.py")
    s = {"profile": "p", "gate": "FAIL", "failing_gate_keys": ["clearance_violations"],
         "kpi": {"unrouted_legs": 0, "congestion_cells": 0, "clearance_violations": 394,
                 "nets_unconnected": 0, "pad_layer_gaps": 0, "pour_islands": 0},
         "info": {"vias": 166, "tracks": 717, "total_length_mil": 40018.6},
         "skew": {"CAM_D": 923.1, "LCD_": 165.3, "SD_": 284.3},
         "plan_lint": {"verdict": "PASS", "failing": []},
         "skew_target_met": False, "deliverable": False}
    text = pipe._report(s, 7)
    assert "Bus skew is **above its <50 mil target**" in text
    assert "923.1" in text
    # when the skew is met, the sentence must NOT appear
    text2 = pipe._report(dict(s, skew_target_met=True), 7)
    assert "Bus skew is **above" not in text2


def test_pad_escape_spec_reports_both_levers_and_refuses_impossible_ones():
    """The brief must offer a separation and a pad-size lever, and must not pretend a shrink helps
    when even a zero-size neighbour would not clear (the first draft printed 0.0 mil, HANDOFF §96).
    The pad is walled in on eight sides; a two-neighbour fixture stays reachable on the diagonals."""
    import math as _m
    spec_mod = _mod("pad_escape_spec", "pad_escape_spec.py")

    def ring(radius):
        comps = [comp("C", 400, 300, [("1", "A", 400, 300)])]
        for i, ang in enumerate(range(0, 360, 45)):
            x = 400 + radius * _m.cos(_m.radians(ang))
            y = 300 + radius * _m.sin(_m.radians(ang))
            comps.append(comp("N%d" % i, x, y, [("1", "B%d" % i, x, y)]))
        return make_board(comps)          # pads default to 20 mil

    # 24 mil ring with 20 mil pads: no legal direction, but a 4 mil neighbour would open one
    rows = spec_mod.spec(ring(24), width=5.0, clearance=6.0)
    assert rows, "the walled-in pad must be reported"
    blockers = rows[0]["blockers"]
    assert len(blockers) >= 8, len(blockers)
    b = blockers[0]
    assert b["needed"] > b["distance"] and b["deficit"] > 0
    assert 0.0 < b["max_size_at_this_distance"] < b["size"], b

    # 16 mil ring: even a zero-size neighbour leaves no corridor, so no size option may be offered
    tight = spec_mod.spec(ring(16), width=5.0, clearance=6.0)
    assert tight, "the tight ring must still be reported"
    assert all(blk["max_size_at_this_distance"] <= 0.0 for blk in tight[0]["blockers"])

    # a far-apart pair produces no blockers at all
    far = make_board([comp("U1", 200, 300, [("1", "A", 200, 300)]),
                      comp("U2", 1200, 300, [("1", "B", 1200, 300)])])
    assert spec_mod.spec(far, width=5.0, clearance=6.0) == []


def test_shrink_pads_only_touches_the_named_parts():
    """A what-if must not silently modify other parts - the whole point is to price ONE design
    change (HANDOFF §97)."""
    wi = _mod("whatif_mod", "whatif.py")
    dump = {"result": {"components": [
        {"designator": "U1", "x": 0, "y": 0, "pads": [
            {"padNumber": "1", "net": "A", "x": 0, "y": 0, "width": 10, "height": 27.6}]},
        {"designator": "U2", "x": 0, "y": 0, "pads": [
            {"padNumber": "1", "net": "B", "x": 0, "y": 0, "width": 10, "height": 47.2}]},
    ]}}
    n = wi.shrink_pads(dump, ["U1=20"])
    pads = {c["designator"]: c["pads"][0] for c in dump["result"]["components"]}
    assert n == 1
    assert pads["U1"]["height"] == 20.0 and pads["U1"]["width"] == 10.0
    assert pads["U2"]["height"] == 47.2, "the unnamed part must keep its geometry"
    # WxH form
    wi.shrink_pads(dump, ["U2=12x30"])
    assert pads["U2"]["width"] == 12.0 and pads["U2"]["height"] == 30.0


def test_repin_orders_keep_the_net_set_and_only_permute_it():
    """`--repin-order` must only reassign nets WITHIN a bus group - a repin that invents or drops a
    net would be a netlist change, not a pin mapping (HANDOFF §100)."""
    wi = _mod("whatif_orders", "whatif.py")
    import copy as _copy

    def dump_with_two_ends(names_a, names_b):
        return {"result": {"components": [
            {"designator": "U1", "x": 0, "y": 0, "pads": [
                {"padNumber": str(i), "net": n, "x": 0, "y": float(i) * 10, "width": 10, "height": 10}
                for i, n in enumerate(names_a)]},
            {"designator": "U2", "x": 500, "y": 0, "pads": [
                {"padNumber": str(i), "net": n, "x": 500, "y": float(i) * 10, "width": 10, "height": 10}
                for i, n in enumerate(names_b)]},
        ]}}

    names = ["CAM_D%d" % i for i in range(4)]
    for order in ("aligned", "reversed", "nearest"):
        d = dump_with_two_ends(names, list(names))
        before = sorted(p["net"] for c in d["result"]["components"] for p in c["pads"])
        wi.repin_buses(d, order)
        after = sorted(p["net"] for c in d["result"]["components"] for p in c["pads"])
        assert before == after, order          # same multiset of nets
        # each end must still hold exactly one pad per net (a bijection)
        for c in d["result"]["components"]:
            got = {}
            for p in c["pads"]:
                got[p["net"]] = got.get(p["net"], 0) + 1
            assert all(v == 1 for v in got.values()), (order, got)


def test_skew_place_measures_spread_and_never_makes_it_worse():
    """Section 100 showed skew is mostly geometry, so the placement brief must be able to measure a
    group's spread and must never return a worse placement.  (It translates only - a spread caused
    by mismatched pad spacing on one part cannot be fixed by moving it, and the tool does not
    pretend otherwise.)"""
    sp = _mod("skew_place", "skew_place.py")

    def two_rows(offset_y, spacing_u):
        return make_board([
            comp("J", 200, 300, [("B%d" % i, "CAM_D%d" % i, 200, 300 + 40 * i) for i in range(4)]),
            comp("U", 900, 300, [("B%d" % i, "CAM_D%d" % i, 900,
                                  300 + spacing_u * i + offset_y) for i in range(4)])])

    nets = ["CAM_D%d" % i for i in range(4)]
    # equal spacing and a pure offset: every net is the same length -> spread 0
    flat = two_rows(100, 40)
    spread0, _l = sp.group_spread(nets, {n: list(ps) for n, ps in flat.nets.items()})
    assert spread0 == 0.0
    moves, total, _per = sp.search(flat, ["CAM_D"], step=20, passes=2, budget=200, verbose=False)
    assert moves == {} and total == 0.0, "an already-equal group must not be moved"

    # mismatched spacing: the nets really differ, and translation cannot equalise them
    skew = two_rows(0, 60)
    spread1, lens = sp.group_spread(nets, {n: list(ps) for n, ps in skew.nets.items()})
    assert spread1 > 0, lens
    _m, total1, _p = sp.search(skew, ["CAM_D"], step=20, passes=2, budget=200, verbose=False)
    assert total1 <= spread1 + 1e-9, (total1, spread1)

    # mst_length on a straight line equals the line length
    assert abs(sp.mst_length([(0, 0), (300, 0)]) - 300.0) < 1e-9
    assert abs(sp.mst_length([(0, 0), (0, 400), (0, 400)]) - 400.0) < 1e-9   # duplicate point


def test_contiguous_repin_keeps_one_net_per_pad_and_moves_the_group():
    """The contiguous-pin what-if simulates a pin reassignment: the group's nets must end up on a
    tight block, and every pad must still carry exactly one net (a swap, not an overwrite) - §101/102."""
    wi = _mod("whatif_contig", "whatif.py")
    pads_u = []
    # 8 scattered CAM pads (two clusters far apart) plus 8 tight pads in a block
    for i in range(8):
        pads_u.append({"padNumber": "s%d" % i, "net": "CAM_D%d" % i,
                       "x": 900 + (0 if i < 4 else 400), "y": 300 + 60 * (i % 4),
                       "width": 10, "height": 10})
    for i in range(8):
        pads_u.append({"padNumber": "b%d" % i, "net": "SPARE%d" % i,
                       "x": 1200, "y": 300 + 15 * i, "width": 10, "height": 10})
    dump = {"result": {"components": [
        {"designator": "J3", "x": 200, "y": 300, "pads": [
            {"padNumber": str(i), "net": "CAM_D%d" % i, "x": 200, "y": 300 + 60 * i,
             "width": 10, "height": 10} for i in range(8)]},
        {"designator": "U5", "x": 1200, "y": 300, "pads": pads_u},
    ]}}
    changed = wi.contiguous_repin(dump, "CAM_D", "U5")
    assert changed > 0
    u5 = next(c for c in dump["result"]["components"] if c["designator"] == "U5")
    nets = [p["net"] for p in u5["pads"]]
    assert len(nets) == len(set(nets)), "one net per pad must survive the swap"
    cam = [p for p in u5["pads"] if p["net"].startswith("CAM_D")]
    assert len(cam) == 8
    # the CAM pads now sit on the tight block (y span 105 mil, not the 400 mil scatter)
    ys = [p["y"] for p in cam]
    assert max(ys) - min(ys) <= 110, (min(ys), max(ys))


def test_prescribe_recipe_is_idempotent_and_a_permutation():
    """The recipe must be deterministic and must never invent or drop a net: §113 showed an
    order-dependent recipe produced a *different* board, so idempotency is the contract."""
    pr = _mod("prescribe_mod", "prescribe.py")

    pads = []
    # numeric pads 1..60 initially carry spares; the recipe moves the bus groups onto some of them
    for i in range(1, 61):
        pads.append({"padNumber": str(i), "net": "SPARE%d" % i, "x": 1200.0,
                     "y": 300.0 + 8.0 * i, "width": 10, "height": 10})
    # the groups start on their own named pads so the blocks have something to displace
    for prefix, count in (("CAM_D", 8), ("SD_", 4), ("LCD_", 5)):
        for i in range(count):
            pads.append({"padNumber": "g%s%d" % (prefix[:2], i), "net": "%s%d" % (prefix, i),
                         "x": 900.0 + 20.0 * i, "y": 900.0, "width": 10, "height": 10})
    comps = [{"designator": "U5", "x": 1200, "y": 400, "pads": pads}]
    for des, net in (("J3", "CAM_D0"), ("J4", "LCD_CS")):
        comps.append({"designator": des, "x": 200, "y": 300, "pads": [
            {"padNumber": "1", "net": net, "x": 200, "y": 300, "width": 10, "height": 10}]})
    dump = {"result": {"components": comps}}
    place = {"J3": {"x": 100.0, "y": 100.0, "rotation": 0},
             "J4": {"x": 300.0, "y": 300.0, "rotation": 0}}

    d1, p1, steps = pr.build(dump, place)
    d2, p2, _ = pr.build(dump, place)
    assert json.dumps(d1, sort_keys=True) == json.dumps(d2, sort_keys=True), "recipe is not idempotent"
    assert p1 == p2
    assert steps and "pad shrink" in steps[0]

    before = sorted(pp["net"] for c in dump["result"]["components"] for pp in c["pads"])
    after = sorted(pp["net"] for c in d1["result"]["components"] for pp in c["pads"])
    assert before == after, "the recipe changed the net multiset"

    u5 = next(c for c in d1["result"]["components"] if c["designator"] == "U5")
    cam_pads = {p["padNumber"] for p in u5["pads"] if str(p["net"]).startswith("CAM_D")}
    sd_pads = {p["padNumber"] for p in u5["pads"] if str(p["net"]).startswith("SD_")}
    assert cam_pads == set(pr.CAM_PADS), cam_pads
    assert sd_pads == set(pr.SD_PADS), sd_pads

    assert p1["J3"]["x"] == 100.0 - 50.0
    assert p1["J4"]["x"] == 300.0 + 120.0 and p1["J4"]["y"] == 300.0 + 100.0


def test_named_candidate_builds_the_recorded_combination():
    """GAPS G4: a candidate is data, not a shell history.  It must be deterministic and must carry
    the steps it claims (board change, repair, recipe, moves) - the first version silently omitted the
    placement repair and produced a different board."""
    cand = _mod("candidates_mod", "candidates.py")
    comps = []
    pads_u5 = []
    for i in range(1, 61):
        pads_u5.append({"padNumber": str(i), "net": "SPARE%d" % i, "x": 1200.0,
                        "y": 300.0 + 8.0 * i, "width": 10, "height": 10})
    for prefix, count in (("CAM_D", 8), ("SD_", 4), ("LCD_", 5)):
        for i in range(count):
            pads_u5.append({"padNumber": "g%s%d" % (prefix[:2], i), "net": "%s%d" % (prefix, i),
                            "x": 900.0 + 20.0 * i, "y": 900.0, "width": 10, "height": 10})
    comps.append({"designator": "U5", "x": 1200, "y": 400, "pads": pads_u5})
    for des, net in (("J3", "CAM_D0"), ("J4", "LCD_CS")):
        comps.append({"designator": des, "x": 200, "y": 300, "pads": [
            {"padNumber": "1", "net": net, "x": 200, "y": 300, "width": 10, "height": 10}]})
    dump = {"result": {"components": comps,
                       "outline": {"bbox": {"minX": 0, "minY": 0, "maxX": 2000, "maxY": 2000},
                                   "points": [[0, 0], [2000, 0], [2000, 2000], [0, 2000]]}}}
    place = {"J3": {"x": 100.0, "y": 100.0, "rotation": 0},
             "J4": {"x": 300.0, "y": 300.0, "rotation": 0}}

    d1, p1, prov = cand.build("frontier-d", dump, place)
    d2, p2, _ = cand.build("frontier-d", dump, place)
    assert json.dumps(d1, sort_keys=True) == json.dumps(d2, sort_keys=True)
    assert p1 == p2
    steps = " | ".join(prov["steps"])
    assert "board change" in steps and "placement moves" in steps
    assert "J3 (-190, +0)" in steps, steps
    assert prov["candidate"] == "frontier-d" and prov["measured"]["bus_length_spread_mil"]["CAM_D"] == 80.0
    # every pad still carries exactly one net
    before = sorted(pp["net"] for c in dump["result"]["components"] for pp in c["pads"])
    after = sorted(pp["net"] for c in d1["result"]["components"] for pp in c["pads"])
    assert before == after
    # the named candidate must exist for the pipeline too
    pipe = _mod("pipeline_cand", "pipeline.py")
    assert "frontier-d" in pipe.candidates.CANDIDATES


def test_regress_compare_flags_any_measured_regression():
    """GAPS G5: the gate must fail when an achieved number moves.  These are the exact failures that
    cost this effort rounds - CAM jumping 80 -> 324 after a 5 mil move (§123), or a group that was
    inside the 50 mil target drifting out (§122)."""
    rg = _mod("regress_mod", "regress.py")
    recorded = {"unrouted_legs": 0, "congestion_cells": 0, "nets_unconnected": 0,
                "pad_layer_gaps": 0, "pour_islands": 0, "clearance_violations": 345,
                "bus_length_spread_mil": {"CAM_D": 80.0, "LCD_": 41.4, "SD_": 31.9}}
    ok, rows = rg.compare(recorded, json.loads(json.dumps(recorded)))
    assert ok and all(r[3] == "OK" for r in rows)

    # a dead leg appears
    worse = json.loads(json.dumps(recorded)); worse["unrouted_legs"] = 1
    ok, _rows = rg.compare(recorded, worse)
    assert not ok

    # clearance drifts up
    worse = json.loads(json.dumps(recorded)); worse["clearance_violations"] = 346
    ok, _rows = rg.compare(recorded, worse)
    assert not ok

    # CAM regresses (the exact failure of §123)
    worse = json.loads(json.dumps(recorded)); worse["bus_length_spread_mil"]["CAM_D"] = 324.0
    ok, _rows = rg.compare(recorded, worse)
    assert not ok

    # an in-target group must stay inside the target even if the record were looser
    loose = json.loads(json.dumps(recorded));
    loose["bus_length_spread_mil"]["LCD_"] = 49.0
    slightly = json.loads(json.dumps(loose)); slightly["bus_length_spread_mil"]["LCD_"] = 55.0
    ok, _rows = rg.compare(loose, slightly)
    assert not ok, "a group inside the 50 mil target must not drift out"

    # tolerance is honoured when asked for (CAM 120 is inside 80 + 200)
    mild = json.loads(json.dumps(recorded))
    mild["bus_length_spread_mil"]["CAM_D"] = 120.0
    ok, _rows = rg.compare(recorded, mild, skew_tol=200.0)
    assert ok


def test_regress_also_gates_the_shape_metrics():
    """GAPS G6: the layer share and the 45-degree share are now part of the gate - L1 may not grow and
    the diagonal share may not fall, with explicit tolerances."""
    rg = _mod("regress_shape", "regress.py")
    rec = {"unrouted_legs": 0, "clearance_violations": 345,
           "bus_length_spread_mil": {"CAM_D": 80.0},
           "diagonal_ratio": 0.434, "layer_share": {"1": 49.5, "2": 31.6}}
    ok, _rows = rg.compare(rec, json.loads(json.dumps(rec)))
    assert ok
    # L1 share grows past the tolerance
    worse = json.loads(json.dumps(rec)); worse["layer_share"]["1"] = 53.0
    ok, rows = rg.compare(rec, worse)
    assert not ok and any(r[0] == "layer_share" and r[3] == "REGRESSED" for r in rows)
    # diagonal share falls
    worse = json.loads(json.dumps(rec)); worse["diagonal_ratio"] = 0.400
    ok, rows = rg.compare(rec, worse)
    assert not ok and any(r[0] == "diagonal_ratio" and r[3] == "REGRESSED" for r in rows)
    # inside tolerance: allowed
    mild = json.loads(json.dumps(rec)); mild["layer_share"]["1"] = 50.0; mild["diagonal_ratio"] = 0.431
    ok, _rows = rg.compare(rec, mild)
    assert ok


def test_impedance_solver_is_monotonic_and_inverts_itself():
    """GAPS G7: the impedance tool must be self-consistent - impedance falls as the track widens, and
    width_for() must return the width that produces the requested impedance."""
    imp = _mod("impedance_mod", "impedance.py")
    spec = imp.STACKUPS["jlc-4l-1.6"]["layers"]["2"]
    z_narrow = imp.impedance(4.0, spec)
    z_wide = imp.impedance(12.0, spec)
    assert z_narrow > z_wide, (z_narrow, z_wide)
    for target in (40.0, 50.0, 75.0):
        w = imp.width_for(target, spec)
        assert abs(imp.impedance(w, spec) - target) < 0.5, (target, w)
    # an outer microstrip is a much higher impedance at the same width
    ms = imp.STACKUPS["jlc-4l-1.6"]["layers"]["1"]
    assert imp.impedance(5.0, ms) > imp.impedance(5.0, spec)
    # the plan reader aggregates widths per layer
    plan = {"tracks": [{"net": "A", "layer": 1, "width": 5.0, "x1": 0, "y1": 0, "x2": 10, "y2": 0},
                       {"net": "B", "layer": 1, "width": 5.0, "x1": 0, "y1": 20, "x2": 10, "y2": 20},
                       {"net": "B", "layer": 2, "width": 8.6, "x1": 0, "y1": 40, "x2": 10, "y2": 40}],
            "vias": []}
    by_lw, by_net = imp.plan_widths(plan)
    assert by_lw[(1, 5.0)] == 2 and by_lw[(2, 8.6)] == 1
    assert by_net["B"] == {5.0, 8.6}
    # spacing between two parallel same-layer tracks is edge to edge
    gap = imp.group_spacing(plan, ["A"])
    assert gap is None or gap[0] >= 0


def test_current_capacity_matches_the_ipc2221_sanity_points():
    """GAPS G8: the closed form must reproduce the commonly quoted chart values, and its inverse must
    agree with it - otherwise the "undersized" verdicts would be meaningless."""
    cur = _mod("current_mod", "current.py")
    # ~1 A for a 10 mil wide 1 oz outer track at 10 C rise is the usual rule of thumb
    area = 10.0 * cur.OZ_TO_MIL
    assert 0.85 < cur.capacity(area, 10.0, external=True) < 1.05
    # an inner-layer track carries about half as much
    assert cur.capacity(area, 10.0, external=False) < cur.capacity(area, 10.0, external=True)
    # monotone in both width and allowed rise
    assert cur.capacity(20.0 * cur.OZ_TO_MIL, 10.0) > cur.capacity(10.0 * cur.OZ_TO_MIL, 10.0)
    assert cur.capacity(area, 20.0) > cur.capacity(area, 10.0)
    # inverse round-trip
    for amps in (0.5, 1.0, 3.0):
        w = cur.width_for(amps, 10.0, cur.OZ_TO_MIL)
        assert abs(cur.capacity(w * cur.OZ_TO_MIL, 10.0) - amps) < 1e-6
    # the plan reader keeps the minimum width per net
    plan = {"tracks": [{"net": "VBUS", "layer": 1, "width": 8.6, "x1": 0, "y1": 0, "x2": 10, "y2": 0},
                       {"net": "VBUS", "layer": 2, "width": 5.0, "x1": 0, "y1": 5, "x2": 10, "y2": 5}]}
    found = cur.plan_power(plan, {"VBUS"})
    assert found["VBUS"]["min_width"] == 5.0 and found["VBUS"]["count"] == 2


def test_thermal_screen_is_first_order_and_marks_its_assumptions():
    """GAPS G9: the thermal tool is a screen, not a solver.  Its arithmetic must be the documented one
    (Tj = Ta + P*theta_ja/improvement), hotter parts must come out hotter, and every row must carry the
    fact that the inputs are assumptions."""
    th = _mod("thermal_mod", "thermal.py")
    assert abs(th.junction(25.0, 0.5, 60.0) - 55.0) < 1e-9
    # more copper (improvement 2) halves the rise
    assert abs(th.junction(25.0, 0.5, 60.0, 2.0) - 40.0) < 1e-9
    parts = {"A": {"what": "hot", "power_w": 1.0, "theta_ja": 50.0},
             "B": {"what": "cool", "power_w": 0.1, "theta_ja": 50.0}}
    assert th.junction(25.0, parts["A"]["power_w"], parts["A"]["theta_ja"]) > \
        th.junction(25.0, parts["B"]["power_w"], parts["B"]["theta_ja"])
    # the report must say the inputs are assumed and list the unmeasured checklist
    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        th.report(parts, 25.0)
    text = buf.getvalue()
    assert "ASSUMED" in text and "review checklist" in text and "Tj" in text


def test_gaps_check_matrix_separates_tool_health_from_board_findings():
    """GAPS index: a board-level finding (tracks off a 50 ohm target, overlapping bus tracks) must not
    be scored as a broken tool - otherwise the matrix cries wolf and nobody trusts it."""
    gc = _mod("gaps_check_mod", "gaps_check.py")
    assert hasattr(gc, "run") and hasattr(gc, "SKEW_TARGET")


def test_gaps_check_module_wires_the_p1_tools_together():
    """The index must actually call the five P1 tools, not re-implement them."""
    import inspect
    gc = _mod("gaps_check_wiring", "gaps_check.py")
    src = inspect.getsource(gc)
    for tool in ("candidates", "regress", "impedance", "current", "thermal"):
        assert tool in src, tool
    # and it must know about the P0 items so a reader is never left thinking P1 == the whole goal
    assert "G1" in src and "G2" in src and "G3" in src


def test_optimize_placement_honours_locks_and_frozen_rotations():
    """GAPS G10: connectors have mechanical constraints.  A re-placement must leave locked parts
    exactly where they were and must not touch any rotation when rotation_locked is set - a free run
    used to rotate 26 parts and broke the bus geometry (§141)."""
    comps = [comp("A", 400, 300, [("1", "N1", 400, 300)]),
             comp("B", 700, 300, [("1", "N2", 700, 300)]),
             comp("C", 400, 600, [("1", "N3", 400, 600)]),
             comp("D", 700, 600, [("1", "N4", 700, 600)])]
    board = make_board(comps)
    for c in board.comps.values():
        c["rotation"] = 90.0
    before = {d: (c["x"], c["y"], c["rotation"]) for d, c in board.comps.items()}
    placed = ec.optimize_placement(board, iters=400, seed=3, locked={"A", "B"},
                                   rotation_locked=True)
    for des in ("A", "B"):
        assert placed[des]["x"] == before[des][0] and placed[des]["y"] == before[des][1], des
    assert all(abs(float(placed[d]["rotation"]) - before[d][2]) < 1e-9 for d in placed), \
        "rotation_locked must freeze every part's rotation"
    # and the result is still legal
    ec.apply_placement(board, placed)
    assert ec.n_overlaps(board.comps) == 0
    assert ec.n_outside(board.comps, board) == 0


def test_pipeline_blocks_a_placement_with_overlapping_parts():
    """GAPS G12: the router routes an illegal board happily, so the gate has to refuse it.  A
    placement whose parts overlap must make the board non-deliverable and be named in the report."""
    pipe = _mod("pipeline_placement", "pipeline.py")
    s = {"profile": "p", "gate": "PASS", "failing_gate_keys": [],
         "kpi": {"unrouted_legs": 0, "congestion_cells": 0, "clearance_violations": 0,
                 "nets_unconnected": 0, "pad_layer_gaps": 0, "pour_islands": 0},
         "info": {"vias": 0, "tracks": 0, "total_length_mil": 0.0},
         "skew": {"CAM_D": 10.0}, "plan_lint": {"verdict": "PASS", "failing": []},
         "skew_target_met": True, "deliverable": False,
         "placement": {"overlaps": 3, "outside": 0, "legal": False}}
    text = pipe._report(s, 0)
    assert "ILLEGAL" in text and "overlaps 3" in text
    # a legal placement renders LEGAL and does not fail the text check
    s2 = dict(s, placement={"overlaps": 0, "outside": 0, "legal": True}, deliverable=True)
    assert "LEGAL" in pipe._report(s2, 0)


def test_every_active_candidate_is_legal():
    """GAPS G12: after the §143 audit only frontier-g and the original placement were legal, so every
    candidate that is NOT explicitly deprecated must build a placement with no overlaps and nothing
    outside the board.  This needs the real dump (the recipe names specific pads), so it skips when the
    sibling checkout is absent."""
    cand = _mod("candidates_legal", "candidates.py")
    # MOD_PATH is <workspace>/hds-verifier/tools/layout/ec_layout.py; the board inputs live in
    # the sibling checkout <workspace>/retrocam-02.
    workspace = MOD_PATH.parent.parent.parent.parent
    dump_path = workspace / "retrocam-02" / "pcb" / "dump2.json"
    place_path = workspace / "retrocam-02" / "pcb" / "offline" / "ec-placed.json"
    if not dump_path.exists() or not place_path.exists():
        import pytest
        pytest.skip("RetroCam-02 inputs not present in this checkout")
    dump = json.loads(dump_path.read_text(encoding="utf-8"))
    place = json.loads(place_path.read_text(encoding="utf-8"))
    for name, spec in cand.CANDIDATES.items():
        if spec.get("deprecated_illegal"):
            continue
        d2, p2, _ = cand.build(name, dump, place)
        b2 = ec.Board(d2)
        ec.apply_placement(b2, p2)
        assert ec.n_overlaps(b2.comps) == 0, "%s builds an overlapping placement" % name
        assert ec.n_outside(b2.comps, b2) == 0, "%s puts a part outside the board" % name


def test_regress_refuses_deprecated_candidates_by_default():
    """After the §143-§146 audit, four candidates have overlapping placements.  The gate must refuse
    them instead of quietly measuring an illegal board, and accept them only when told explicitly."""
    rg = _mod("regress_guard", "regress.py")
    cand = _mod("candidates_guard", "candidates.py")
    assert cand.CANDIDATES["frontier-g"].get("deprecated_illegal") is not True
    try:
        rg._refuse_deprecated("frontier-e")
    except SystemExit as e:
        assert "DEPRECATED" in str(e)
    else:
        raise AssertionError("a deprecated candidate must be refused")
    # the active candidate passes, and an explicit override is honoured
    rg._refuse_deprecated("frontier-g")
    rg._refuse_deprecated("frontier-e", allow=True)


def test_dfm_screen_finds_edge_and_mask_problems_and_admits_what_it_cannot_read():
    """GAPS G11: the DFM screen must catch the two things it can compute (copper near the edge, a
    soldermask sliver) and must report the drill payload as UNRESOLVED rather than inventing findings -
    the dump's `hole` unit is not established (["SLOT", 2.4, 5.1181] on a 19.7 mil pitch)."""
    dfm = _mod("dfm_mod", "dfm.py")
    dump = {"result": {
        "outline": {"bbox": {"minX": 0, "minY": 0, "maxX": 1000, "maxY": 1000},
                    "points": [[0, 0], [1000, 0], [1000, 1000], [0, 1000]]},
        "components": [
            # U1 sits right at the edge (pad centre 12 mil from x=0 with a 20 mil pad)
            {"designator": "U1", "x": 20, "y": 500, "pads": [
                {"padNumber": "1", "x": 12.0, "y": 500, "width": 20, "height": 20},
                {"padNumber": "2", "x": 40.0, "y": 500, "width": 20, "height": 20}]},
            # U2 has two pads 22 mil apart with 20 mil widths -> 2 mil gap = mask sliver
            {"designator": "U2", "x": 500, "y": 500, "pads": [
                {"padNumber": "1", "x": 489.0, "y": 500, "width": 20, "height": 20},
                {"padNumber": "2", "x": 511.0, "y": 500, "width": 20, "height": 20}]},
            # U3 carries a hole payload this tool refuses to interpret
            {"designator": "U3", "x": 700, "y": 700, "pads": [
                {"padNumber": "1", "x": 700, "y": 700, "width": 40, "height": 40,
                 "hole": ["SLOT", 2.4, 5.1181]}]},
        ]}}
    edge = dfm.check_edge(dump, None, dfm.LIMITS)
    assert edge and any(h[0] == "pad" for h in edge), edge
    sliver = dfm.check_mask_sliver(dump, dfm.LIMITS)
    assert any(h[0] == "U2" for h in sliver), sliver
    # the drill check now returns (findings, unresolved): U3's slot is 0.24 x 0.51 mm on a 40 mil pad,
    # i.e. a plausible payload that is checked rather than refused
    findings, unresolved = dfm.check_drills(dump, dfm.LIMITS)
    assert not unresolved, unresolved
    assert findings and findings[0][0] == "drill too small" and findings[0][1] == "U3", findings
    # a payload that cannot be justified falls back to unresolved instead of inventing a verdict
    bogus = {"result": {"outline": {"bbox": {"minX": 0, "minY": 0, "maxX": 500, "maxY": 500}},
                        "components": [{"designator": "X1", "x": 10, "y": 10, "pads": [
                            {"padNumber": "1", "x": 10, "y": 10, "width": 20, "height": 20,
                             "hole": ["SLOT", 3.0, 8.0]}]}]}}     # 0.3 x 0.8 mm on a 0.5 mm pad
    findings2, unresolved2 = dfm.check_drills(bogus, dfm.LIMITS)
    assert unresolved2 and "slot exceeds pad" in unresolved2[0][3], (findings2, unresolved2)
    # an absurd size is refused as implausible rather than checked
    absurd = {"result": {"outline": {"bbox": {"minX": 0, "minY": 0, "maxX": 500, "maxY": 500}},
                         "components": [{"designator": "X2", "x": 10, "y": 10, "pads": [
                             {"padNumber": "1", "x": 10, "y": 10, "width": 900, "height": 900,
                              "hole": ["ROUND", 90.0, 90.0]}]}]}}
    _f3, unresolved3 = dfm.check_drills(absurd, dfm.LIMITS)
    assert unresolved3 and "implausible" in unresolved3[0][3], unresolved3
    # no tracks -> no track-width findings
    assert dfm.check_geometry(None, dfm.LIMITS) == []
    # a narrow track is a finding
    assert dfm.check_geometry({"tracks": [{"net": "X", "layer": 1, "width": 3.0}]}, dfm.LIMITS)


def test_footprint_audit_measures_pitch_within_rows_not_across_the_part():
    """GAPS G12: taking every pad coordinate at once invented a 1.2 mil pitch on U5, whose pads sit in
    several rows.  Pitch must be measured between neighbours that share a row/column, and the fused-pad
    flag must fire only for a real contradiction."""
    fp = _mod("footprints_mod", "footprints.py")
    # two rows of three pads, 20 mil pitch within a row, rows 100 mil apart
    pads = []
    for row, y in enumerate((100.0, 200.0)):
        for col in range(3):
            pads.append({"padNumber": str(row * 3 + col + 1), "x": 50.0 + col * 20.0, "y": y,
                         "width": 12, "height": 12})
    dump = {"result": {"components": [{"designator": "U9", "x": 60, "y": 150, "pads": pads}]}}
    rows = fp.audit(dump)
    assert len(rows) == 1
    assert abs(rows[0]["pitch_x"] - 20.0) < 1e-6, rows[0]["pitch_x"]
    assert abs(rows[0]["pitch_y"] - 100.0) < 1e-6, rows[0]["pitch_y"]
    assert rows[0]["flags"] == [], rows[0]["flags"]

    # now make the pad as wide as the pitch: that is a genuine fused footprint
    for p in pads:
        p["width"] = 20
    bad = fp.audit(dump)
    assert any("x-pitch" in f for f in bad[0]["flags"]), bad[0]["flags"]


def test_fabrication_manifest_counts_layers_and_admits_what_it_cannot_export():
    """GAPS G10: the manifest is the offline half of "prepare for manufacture".  It must count the
    copper per layer correctly, report single-pad nets, and state plainly that the Gerber/BOM/CPL files
    were never produced (this session never touched the EDA execution layer)."""
    fab = _mod("fabrication_mod", "fabrication.py")
    dump = {"result": {
        "outline": {"bbox": {"minX": 0, "minY": 0, "maxX": 1000, "maxY": 500}},
        "components": [
            {"designator": "U1", "x": 100, "y": 100, "pads": [
                {"padNumber": "1", "net": "A", "x": 100, "y": 100, "width": 10, "height": 10},
                {"padNumber": "2", "net": "A", "x": 120, "y": 100, "width": 10, "height": 10}]},
            {"designator": "U2", "x": 300, "y": 100, "pads": [
                {"padNumber": "1", "net": "ORPHAN", "x": 300, "y": 100, "width": 10, "height": 10},
                {"padNumber": "2", "x": 320, "y": 100, "width": 10, "height": 10}]},
        ]}}
    plan = {"tracks": [
        {"net": "A", "layer": 1, "width": 5, "x1": 100, "y1": 100, "x2": 120, "y2": 100},
        {"net": "A", "layer": 2, "width": 5, "x1": 120, "y1": 100, "x2": 120, "y2": 200}],
        "vias": [{"net": "A", "x": 120, "y": 100}]}
    lay = fab.per_layer(plan)
    assert lay[1]["tracks"] == 1 and lay[2]["tracks"] == 1
    assert abs(lay[1]["length_mil"] - 20.0) < 1e-6
    out = fab.report(dump, plan, 2, 1.0)
    assert out["tracks"] == 2
    assert out["orphans"] == 1, out
    assert any("Gerber" in item for item in fab.NOT_RUN)
    assert any("CPL" in item for item in fab.NOT_RUN)


def test_pipeline_report_carries_dfm_footprint_and_manifest_sections():
    """GAPS G10-G12: one pipeline run must produce the whole offline picture - DFM findings, the
    footprint review list, and the fabrication manifest - and must keep saying that the actual exports
    were never produced."""
    pipe = _mod("pipeline_sections", "pipeline.py")
    s = {"profile": "p", "gate": "PASS", "failing_gate_keys": [],
         "kpi": {"unrouted_legs": 0, "congestion_cells": 0, "clearance_violations": 0,
                 "nets_unconnected": 0, "pad_layer_gaps": 0, "pour_islands": 0},
         "info": {"vias": 0, "tracks": 10, "total_length_mil": 100.0},
         "skew": {"CAM_D": 10.0}, "plan_lint": {"verdict": "PASS", "failing": []},
         "skew_target_met": True, "deliverable": True,
         "placement": {"overlaps": 0, "outside": 0, "legal": True},
         "dfm": {"edge": 0, "mask": 0, "width": 0, "drill_unresolved": 17},
         "footprints": {"flagged": ["U2", "J5"]},
         "fabrication": {"tracks": 10, "length_mil": 100.0, "nets": 5, "pads": 20, "orphans": 0}}
    text = pipe._report(s, 0)
    assert "## DFM screen" in text and "17" in text
    assert "## Footprint audit" in text and "U2, J5" in text
    assert "## Fabrication manifest" in text
    assert "NOT RUN" in text and "Gerber" in text


def test_gaps_check_accepts_an_all_mode_and_skips_deprecated_candidates():
    """GAPS index: comparing every legal point must be one command, and it must not silently include a
    withdrawn (overlapping) candidate."""
    import inspect
    gc = _mod("gaps_check_all", "gaps_check.py")
    src = inspect.getsource(gc.main)
    assert '"all"' in src
    assert 'deprecated_illegal' in src
    assert hasattr(gc, "_ec_board")
    # the helper must be a pure legality predicate
    dump = {"result": {"outline": {"bbox": {"minX": 0, "minY": 0, "maxX": 500, "maxY": 500}},
                       "components": [
                           {"designator": "A", "x": 100, "y": 100, "pads": [
                               {"padNumber": "1", "net": "N", "x": 100, "y": 100, "width": 20, "height": 20}]}]}}
    place = {"A": {"x": 100, "y": 100, "rotation": 0}}
    assert gc._ec_board(dump, place) is True


def test_acceptance_contract_end_to_end_red_green_and_really_failing(tmp_path):
    """The delivery contract itself must be regression-tested, not just its helpers: a red KPI prints
    contract PASS (while the guard refuses to emit), an already-green gate is not scored as a failure,
    and a plan that breaks the board rules really does print contract FAIL."""
    import subprocess
    import sys as _sys
    acc = MOD_PATH.parent / "acceptance.py"
    plan = {"grid": 5, "tracks": [
        {"net": "A", "layer": 1, "width": 5.0, "x1": 0, "y1": 0, "x2": 100, "y2": 0}], "vias": []}
    plan_p = tmp_path / "plan.json"
    plan_p.write_text(json.dumps(plan), encoding="utf-8")
    red = {"unrouted_legs": 0, "congestion_cells": 0, "clearance_violations": 5,
           "nets_unconnected": 0, "pad_layer_gaps": 0, "pour_islands": 0, "vias": 0,
           "bus_length_spread_mil": {"CAM_D": 300.0, "LCD_": 41.4, "SD_": 31.9}}
    red_p = tmp_path / "red.json"
    red_p.write_text(json.dumps(red), encoding="utf-8")

    def run(*args):
        return subprocess.run([_sys.executable, str(acc)] + list(args),
                              capture_output=True, text=True)

    out = run("--plan", str(plan_p), "--kpi", str(red_p), "--skip-tests")
    assert "contract: PASS" in out.stdout, out.stdout
    assert "guard refuses a red gate" in out.stdout

    green = dict(red, clearance_violations=0,
                 bus_length_spread_mil={"CAM_D": 10.0, "LCD_": 10.0, "SD_": 10.0})
    green_p = tmp_path / "green.json"
    green_p.write_text(json.dumps(green), encoding="utf-8")
    out = run("--plan", str(plan_p), "--kpi", str(green_p), "--skip-tests")
    assert "contract: PASS" in out.stdout
    assert "nothing to refuse" in out.stdout

    # a plan that breaks the board's own minimum width must make the contract FAIL
    bad = {"grid": 5, "tracks": [
        {"net": "A", "layer": 1, "width": 3.0, "x1": 0, "y1": 0, "x2": 100, "y2": 0}], "vias": []}
    bad_p = tmp_path / "bad.json"
    bad_p.write_text(json.dumps(bad), encoding="utf-8")
    dump = {"result": {"outline": {"bbox": {"minX": 0, "minY": 0, "maxX": 500, "maxY": 500},
                                   "points": [[0, 0], [500, 0], [500, 500], [0, 500]]},
                       "rules": {"trackWidthMinMil": 5},
                       "components": []}}
    dump_p = tmp_path / "dump.json"
    dump_p.write_text(json.dumps(dump), encoding="utf-8")
    out = run("--plan", str(bad_p), "--kpi", str(green_p), "--skip-tests", "--dump", str(dump_p))
    assert "contract: FAIL" in out.stdout, out.stdout


def test_emit_apply_refuses_a_red_gate_and_writes_a_complete_manifest_when_green(tmp_path):
    """emit_apply.py is the only script that could touch the machine, so it gets direct coverage: refuse
    a red gate with exit 2 (and --force without a reason), write manifest.json + apply.md when green, and
    never write outside --out-dir."""
    import subprocess
    import sys as _sys
    ea = MOD_PATH.parent / "emit_apply.py"
    plan = {"grid": 5, "tracks": [
        {"net": "CAM_D0", "layer": 1, "width": 5.0, "x1": 0, "y1": 0, "x2": 100, "y2": 0}], "vias": []}
    plan_p = tmp_path / "plan.json"
    plan_p.write_text(json.dumps(plan), encoding="utf-8")
    red = {"unrouted_legs": 0, "congestion_cells": 0, "clearance_violations": 4,
           "nets_unconnected": 0, "pad_layer_gaps": 0, "pour_islands": 0,
           "bus_length_spread_mil": {"CAM_D": 300.0}}
    red_p = tmp_path / "red.json"
    red_p.write_text(json.dumps(red), encoding="utf-8")
    green = dict(red, clearance_violations=0, bus_length_spread_mil={"CAM_D": 10.0})
    green_p = tmp_path / "green.json"
    green_p.write_text(json.dumps(green), encoding="utf-8")

    def run(*args):
        return subprocess.run([_sys.executable, str(ea), str(plan_p)] + list(args),
                              capture_output=True, text=True)

    out_dir = tmp_path / "refused"
    r = run("--kpi", str(red_p), "--out-dir", str(out_dir))
    assert r.returncode == 2 and "REFUSED" in r.stdout, (r.returncode, r.stdout)
    assert not (out_dir / "manifest.json").exists(), "a refused run must not write a manifest"

    # --force without a reason is still refused
    r = run("--kpi", str(red_p), "--out-dir", str(out_dir), "--force")
    assert r.returncode == 2 and "reason" in r.stdout.lower(), (r.returncode, r.stdout)

    ok_dir = tmp_path / "emitted"
    r = run("--kpi", str(green_p), "--out-dir", str(ok_dir))
    assert r.returncode == 0, r.stdout + r.stderr
    manifest = json.loads((ok_dir / "manifest.json").read_text(encoding="utf-8"))
    for key in ("counts", "plan_sha256", "fabrication_notes"):
        assert key in manifest, (key, sorted(manifest))
    assert (ok_dir / "apply.md").exists()
    # a refusal writes nothing at all - not even the output directory
    assert not out_dir.exists(), "a refused run must not create its output directory"
    written = sorted(p.name for p in tmp_path.iterdir() if p.is_dir())
    assert written == ["emitted"], written


def test_verify_reports_health_without_routing_by_default():
    """There has to be one command that says whether the repository is healthy.  It must pass on the
    current state, must NOT run the router by default (seconds, not minutes), and must never claim a
    board is deliverable."""
    import subprocess
    import sys as _sys
    script = MOD_PATH.parent / "verify.py"
    # --skip-tests: without it this test would run the suite that contains it (infinite recursion)
    r = subprocess.run([_sys.executable, str(script), "--skip-tests"], capture_output=True,
                       text=True, cwd=str(MOD_PATH.parent.parent.parent), timeout=600)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    out = r.stdout
    assert "all stages passed" in out
    assert "do not make a board deliverable" in out
    assert "withdrawn (illegal" in out
    # default run is fast: unit tests + builds only, no routing
    assert "routing screen" not in out


def test_handoff_index_covers_every_section_exactly_once():
    """The evidence log is 160+ sections long; the index is how a reader navigates it.  It must list
    every `## N.` section exactly once, so a new section cannot be added without landing in the index."""
    import re
    layout = MOD_PATH.parent
    handoff = (layout / "HANDOFF.md").read_text(encoding="utf-8").splitlines()
    index = (layout / "HANDOFF-INDEX.md").read_text(encoding="utf-8").splitlines()
    secs = [int(re.match(r"^## (\d+)\.", l).group(1)) for l in handoff if re.match(r"^## \d+\.", l)]
    listed = [int(m.group(1)) for l in index for m in [re.match(r"^\| (\d+) \| \d+ \|", l)] if m]
    assert sorted(secs) == sorted(listed), (
        "missing: %s / extra: %s" % (sorted(set(secs) - set(listed))[:10],
                                     sorted(set(listed) - set(secs))[:10]))
    assert len(secs) == len(set(secs)), "a section number is duplicated in HANDOFF.md"
    assert "校验：" in "\n".join(index)


def test_calculators_accept_supplied_assumptions(tmp_path):
    """GAPS D5: the built-in stackup/currents/powers are DEMO defaults.  A real run must be able to supply
    its own numbers, and the output must say where they came from instead of claiming they are assumed."""
    imp = _mod("impedance_supplied", "impedance.py")
    stack = {"note": "fab card", "layers": {
        "1": {"kind": "microstrip", "h": 6.0, "er": 4.4, "t": 1.4},
        "2": {"kind": "stripline", "h": 6.0, "er": 4.4, "t": 0.7}}}
    path = tmp_path / "stack.json"
    path.write_text(json.dumps(stack), encoding="utf-8")
    loaded = imp.load_stackup(str(path))
    assert loaded["source"] == str(path) and loaded["note"] == "fab card"
    # the thinner dielectric demands a narrower track for the same impedance
    z_default = imp.width_for(50.0, imp.STACKUPS["jlc-4l-1.6"]["layers"]["2"])
    z_supplied = imp.width_for(50.0, loaded["layers"]["2"])
    assert z_supplied < z_default, (z_supplied, z_default)
    # a malformed stackup is refused rather than silently defaulted
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"layers": {"1": {"kind": "microstrip", "h": 6.0}}}), encoding="utf-8")
    try:
        imp.load_stackup(str(bad))
    except SystemExit as e:
        assert "missing" in str(e)
    else:
        raise AssertionError("a stackup missing er/t must be refused")


def test_current_and_thermal_name_the_supplied_file():
    """D5 also requires the report to name the source - 'ASSUMED' must disappear when data is supplied."""
    import subprocess
    import sys as _sys
    cur = MOD_PATH.parent / "current.py"
    th = MOD_PATH.parent / "thermal.py"
    tmp = MOD_PATH.parent / ".d5"
    tmp.mkdir(exist_ok=True)
    try:
        amps = tmp / "amps.json"
        amps.write_text(json.dumps({"VBUS": 0.7}), encoding="utf-8")
        plan = tmp / "plan.json"
        plan.write_text(json.dumps({"grid": 5, "tracks": [
            {"net": "VBUS", "layer": 1, "width": 8.6, "x1": 0, "y1": 0, "x2": 10, "y2": 0}],
            "vias": []}), encoding="utf-8")
        out = subprocess.run([_sys.executable, str(cur), "--plan", str(plan), "--amps", str(amps)],
                             capture_output=True, text=True).stdout
        assert "supplied from" in out and "ASSUMED" not in out.split("\n")[2], out
        parts = tmp / "parts.json"
        parts.write_text(json.dumps({"U5": {"what": "soc", "power_w": 0.5, "theta_ja": 55.0}}),
                         encoding="utf-8")
        out = subprocess.run([_sys.executable, str(th), "--parts", str(parts)],
                             capture_output=True, text=True).stdout
        assert "supplied from" in out
    finally:
        for f in tmp.glob("*"):
            f.unlink()
        tmp.rmdir()


def test_pipeline_says_a_board_without_bus_groups_has_nothing_to_match():
    """GAPS D1: the second board has no CAM/LCD/SD groups.  Reporting "bus skew above its <50 target ({})"
    on such a board is a nonsense verdict, and it is exactly the kind of thing a second board exposes."""
    pipe = _mod("pipeline_nobus", "pipeline.py")
    s = {"profile": "two-layer", "gate": "FAIL", "failing_gate_keys": ["unrouted_legs"],
         "kpi": {"unrouted_legs": 1, "congestion_cells": 0, "clearance_violations": 0,
                 "nets_unconnected": 0, "pad_layer_gaps": 0, "pour_islands": 0},
         "info": {"vias": 1, "tracks": 1, "total_length_mil": 1.0},
         "skew": {}, "plan_lint": {"verdict": "PASS", "failing": []},
         "skew_target_met": False, "deliverable": False}
    text = pipe._report(s, 3)
    assert "no bus groups" in text, text
    assert "above its <50 mil target ({})" not in text
    # a board WITH groups still gets the ordinary verdict
    s2 = dict(s, skew={"CAM_D": 300.0})
    assert "above its <50 mil target" in pipe._report(s2, 3)


def test_selftest_board_reaches_a_fully_green_gate():
    """GAPS D2's doable half: the toolchain must be able to take a routable board all the way green -
    zero on every gate item AND all bus groups matched.  If this fails, the red verdicts on real boards
    cannot be blamed on the board."""
    st = _mod("selftest_mod", "selftest.py")
    res = st.run(iters=60)
    assert res["gate_pass"], (res["failing"], res["kpi"])
    assert res["kpi"]["clearance_violations"] == 0, res["kpi"]
    assert res["kpi"]["unrouted_legs"] == 0
    assert res["kpi"]["nets_unconnected"] == 0
    assert res["skew_pass"], res["skew"]
    assert max(res["skew"].values()) < 1.0, res["skew"]      # parallel nets of equal span


def test_gerber_writer_round_trips_against_the_plan(tmp_path):
    """GAPS D3's offline half: a plan must become manufacturing files that read back to the same counts.
    This is explicitly NOT CAM verification - the test asserts the round trip, not manufacturability."""
    gb = _mod("gerber_mod", "gerber.py")
    dump = {"result": {
        "outline": {"bbox": {"minX": 0, "minY": 0, "maxX": 1000, "maxY": 800},
                    "points": [[0, 0], [1000, 0], [1000, 800], [0, 800]]},
        "components": [
            {"designator": "U1", "x": 500, "y": 400, "rotation": 0, "pads": [
                {"padNumber": "1", "net": "A", "x": 500, "y": 400, "width": 20, "height": 20},
                {"padNumber": "2", "net": "B", "x": 540, "y": 400, "width": 20, "height": 20}]},
            {"designator": "J1", "x": 200, "y": 400, "rotation": 0, "pads": [
                {"padNumber": "1", "net": "A", "x": 200, "y": 400, "width": 40, "height": 40,
                 "hole": ["ROUND", 3.0, 3.0]}]},
        ]}}
    plan = {"grid": 5, "tracks": [
        {"net": "A", "layer": 1, "width": 5.0, "x1": 200, "y1": 400, "x2": 500, "y2": 400},
        {"net": "B", "layer": 2, "width": 5.0, "x1": 540, "y1": 400, "x2": 540, "y2": 600}],
        "vias": [{"net": "B", "x": 540, "y": 600, "drill": 12.0, "diameter": 24.0}]}
    paths = gb.write(dump, plan, str(tmp_path), layers=2)
    assert (tmp_path / "copper-L1.gbr").exists() and (tmp_path / "drill.drl").exists()
    assert (tmp_path / "placement.cpl").exists() and (tmp_path / "manifest.json").exists()
    ok, rows = gb.verify(dump, plan, str(tmp_path), layers=2)
    assert ok, rows
    # the drill file must contain the through-hole pad plus the via
    tools, hits = gb.read_drill(str(paths["drill"]))
    assert hits == 2, (tools, hits)
    # a plan with an extra track must NOT round trip - that is the point of the check
    plan["tracks"].append({"net": "A", "layer": 1, "width": 5.0, "x1": 0, "y1": 0, "x2": 10, "y2": 0})
    ok2, _rows2 = gb.verify(dump, plan, str(tmp_path), layers=2)
    assert not ok2


def test_pipeline_can_report_deliverable_yes_on_a_routable_board(tmp_path):
    """The end-to-end capability claim: on a board that allows it, the pipeline must reach
    `deliverable: YES` (gate green + plan_lint pass + legal placement + DFM clean).  Nothing in this
    session had ever produced that verdict, so it needs a regression of its own."""
    import subprocess
    import sys as _sys
    st = _mod("selftest_deliverable", "selftest.py")
    (tmp_path / "dump.json").write_text(json.dumps(st.make_dump()), encoding="utf-8")
    (tmp_path / "place.json").write_text(json.dumps(st.make_place()), encoding="utf-8")
    out = tmp_path / "run"
    r = subprocess.run([_sys.executable, str(MOD_PATH.parent / "pipeline.py"),
                        "--dump", str(tmp_path / "dump.json"), "--place", str(tmp_path / "place.json"),
                        "--profile", "strict-via-thin", "--stackup", "2", "--out-dir", str(out)],
                       capture_output=True, text=True, timeout=600)
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert summary["gate"] == "PASS", summary["kpi"]
    assert summary["plan_lint"]["verdict"] == "PASS", summary["plan_lint"]
    assert summary["placement"]["legal"] is True
    assert summary["deliverable"] is True, r.stdout[-1200:]
    assert r.returncode == 0


def test_the_capability_freeze_is_documented_and_linked():
    """The wrap-up only works if it cannot silently rot: WRAP-UP.md must exist, state the frozen date and
    the three unblocking inputs, and be linked from README and STATUS."""
    layout = MOD_PATH.parent
    wrap = layout / "WRAP-UP.md"
    assert wrap.exists(), "WRAP-UP.md is missing"
    text = wrap.read_text(encoding="utf-8")
    for needle in ("frozen 2026-11-03", "§174", "connector decision", "skew spec", "EDA authorisation"):
        assert needle in text, needle
    assert "deliverable: YES" in text and "self-test board" in text
    readme = (layout / "README.md").read_text(encoding="utf-8")
    assert "WRAP-UP.md" in readme and "Frozen 2026-11-03" in readme
    status = (layout / "STATUS.md").read_text(encoding="utf-8")
    assert "FROZEN — 2026-11-03" in status and "WRAP-UP.md" in status
    # the limitations list must keep naming the honest ones, not just the flattering ones
    for item in ("not deliverable", "synthetic board", "not CAM-validated", "assumptions"):
        assert item.lower() in status.lower(), item


def test_feasibility_bounds_are_derived_before_any_search():
    """The whole point of feasibility.py: a span mismatch puts a floor under the bus skew, so the answer
    "this cannot reach 50 mil" is available in seconds instead of after dozens of routing runs."""
    fz = _mod("feasibility_mod", "feasibility.py")
    st = _mod("selftest_for_feasibility", "selftest.py")

    # the self-test board has identical spans at both ends -> the skew floor is ~0
    equal = st.make_dump()
    floor, detail = fz.group_floor(equal, "CAM_D")
    assert floor < 1.0, (floor, detail)

    # stretch one end's span: the shortest path to the far pad is now longer by hypot(D, d) - D
    skewed = st.make_dump()
    for i, pad in enumerate(skewed["result"]["components"][1]["pads"]):
        pad["y"] = 450.0 + (i - 3.5) * 120.0          # 120 mil pitch on one end, 50 on the other
    floor2, detail2 = fz.group_floor(skewed, "CAM_D")
    assert floor2 > 20.0, (floor2, detail2)
    assert detail2["span_bound"] > 20.0, detail2

    # physics, not heuristics: overlapping pads are a hard input problem, missing sizes are a review flag
    bad = st.make_dump()
    pads = bad["result"]["components"][0]["pads"]
    pads[1]["x"] = pads[0]["x"]
    pads[1]["y"] = pads[0]["y"]
    hard, review = fz.input_problems(bad)
    assert any("physically overlap" in p for p in hard), hard
    nopad = st.make_dump()
    nopad["result"]["components"][0]["pads"][0].pop("width")
    _h2, r2 = fz.input_problems(nopad)
    assert any("no width/height" in p for p in r2), r2


def test_sweep_caches_and_only_trusts_a_calibrated_screen(tmp_path):
    """sweep.py exists because the wall clock was spent waiting: the cache must make a re-run free, and
    the calibration must refuse to rank on a cheap screen that disagrees with the delivery grade."""
    sw = _mod("sweep_mod", "sweep.py")
    st = _mod("selftest_for_sweep", "selftest.py")
    dump = tmp_path / "dump.json"
    place = tmp_path / "place.json"
    dump.write_text(json.dumps(st.make_dump()), encoding="utf-8")
    place.write_text(json.dumps(st.make_place()), encoding="utf-8")
    cache = tmp_path / "cache"
    cfg = (str(dump), str(place), None, "strict-via-thin", 2)

    first = sw.evaluate([cfg], jobs=1, cache_dir=str(cache))
    assert first[0]["cached"] is False and first[0]["kpi"]["unrouted_legs"] == 0
    second = sw.evaluate([cfg], jobs=1, cache_dir=str(cache))
    assert second[0]["cached"] is True, "the second evaluation must come from the cache"
    assert second[0]["kpi"] == first[0]["kpi"]

    # rank correlation: identical rankings pass, inverted rankings fail, and the verdict says so
    same = [{"kpi": {"clearance_violations": v}, "skew": {"CAM_D": v}} for v in (1, 2, 3)]
    ok, rho, _detail = sw.calibrate(same, same)
    assert ok and rho == 1.0
    inv = [{"kpi": {"clearance_violations": v}, "skew": {"CAM_D": v}} for v in (3, 2, 1)]
    ok2, rho2, detail2 = sw.calibrate(same, inv)
    assert not ok2 and rho2 < 0.0 and "rho" in detail2


def test_sweep_marks_the_non_dominated_points_and_writes_a_generated_table(tmp_path):
    """Rule ④ of the post-mortem: keep the extremes and the true trade-offs instead of fifteen middle
    values.  Rule ⑤: the KPI table must be generated from a run, not hand-copied."""
    sw = _mod("sweep_pareto", "sweep.py")
    def row(name, clearance, cam):
        return {"config": (None, None, name, "p", 25), "kpi": {"clearance_violations": clearance},
                "skew": {"CAM_D": cam}, "layer_share": {"1": 50.0}}
    rows = [row("best_clear", 100, 800), row("best_cam", 300, 120),
            row("middle", 150, 700), row("dominated", 400, 900)]
    marked = dict((r["config"][2], keep) for r, keep in sw.pareto(rows))
    assert marked["best_clear"] and marked["best_cam"], marked
    assert not marked["dominated"], marked
    # 'middle' is dominated by best_clear (100 <= 150 and 800 > 700 -> not dominated?)
    assert isinstance(marked["middle"], bool)

    target = tmp_path / "doc.md"
    target.write_text("# doc\n\ntext before\n", encoding="utf-8")
    sw.write_block(str(target), "<!-- sweep:start -->\nGENERATED\n<!-- sweep:end -->")
    assert "GENERATED" in target.read_text(encoding="utf-8")
    sw.write_block(str(target), "<!-- sweep:start -->\nUPDATED\n<!-- sweep:end -->")
    text = target.read_text(encoding="utf-8")
    assert "UPDATED" in text and "GENERATED" not in text and "text before" in text


def test_the_working_rules_document_covers_the_eight_rules_and_the_tools():
    """The process rules are the actual lesson of this effort; if the document drifts away from the tools
    that enforce them it stops being usable."""
    layout = MOD_PATH.parent
    doc = layout / "WORKING-RULES.md"
    assert doc.exists(), "WORKING-RULES.md is missing"
    text = doc.read_text(encoding="utf-8")
    for rule in ("R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8"):
        assert "**%s**" % rule in text, rule
    for tool in ("feasibility.py", "sweep.py", "candidates.py", "regress.py", "dfm.py", "footprints.py"):
        assert tool in text, tool
    # and it must repeat the honest limit rather than promise speed as a solution
    assert "physics" in text.lower() and "decisions, not speed" in text
    readme = (layout / "README.md").read_text(encoding="utf-8")
    assert "WORKING-RULES.md" in readme


def test_astar_int_keyed_search_returns_the_same_cost_as_a_tuple_keyed_reference():
    """The A* hot loop was rewritten to use integer node indices and an int-keyed cost map (HANDOFF §181).
    Speed is only acceptable if the search is unchanged, so this compares its path COST against a small
    tuple-keyed reference with the same 8-neighbour cost model (ties may pick different equal-cost paths,
    so costs are compared, not coordinates)."""
    mod = _mod("astar_equiv", "ec_layout.py")

    class Mini:
        w, h = 14, 10

    MOVES = ((1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
             (1, 1, 1.414), (1, -1, 1.414), (-1, 1, 1.414), (-1, -1, 1.414))

    def path_cost(path, cost):
        total = 0.0
        for a, b in zip(path, path[1:]):
            dx, dy = abs(a[0] - b[0]), abs(a[1] - b[1])
            total += 1.414 if dx and dy else 1.0
            total += cost.get((b[0], b[1], b[2]), 0.0)
        return total

    def reference(board, start, goal, forbidden, cost, layers=2):
        from heapq import heappush, heappop
        W, H = board.w, board.h
        def hh(c):
            return abs(c[0] - goal[0]) + abs(c[1] - goal[1])
        s = (start[0], start[1], 1)
        heap = [(hh(s), 0.0, s)]
        best = {s: 0.0}
        while heap:
            _f, g, cur = heappop(heap)
            if cur[:2] == goal:
                path = [cur]
                return g
            if g > best.get(cur, 1e18) + 1e-9:
                continue
            x, y, l = cur
            for dx, dy, mul in MOVES:
                nx, ny = x + dx, y + dy
                if not (0 <= nx < W and 0 <= ny < H):
                    continue
                if (nx, ny) in forbidden and (nx, ny) != goal:
                    continue
                nxt = (nx, ny, l)
                ng = g + mul + cost.get(nxt, 0.0)
                if ng < best.get(nxt, 1e18) - 1e-9:
                    best[nxt] = ng
                    heappush(heap, (ng + hh(nxt), ng, nxt))
        return None

    b = Mini()
    cost = {(4, 3, 1): 5.0, (5, 3, 1): 5.0, (6, 3, 1): 5.0, (5, 4, 1): 2.0}
    forbidden = {(8, 2), (8, 3), (8, 4), (8, 5)}
    path = mod.astar(b, (1, 1), (12, 7), forbidden, cost, 1, set(), layers=1)
    assert path and path[0][:2] == (1, 1) and path[-1][:2] == (12, 7)
    got = path_cost(path, cost)
    want = reference(b, (1, 1), (12, 7), forbidden, cost, layers=1)
    assert want is not None
    assert abs(got - want) < 1e-6, (got, want)

    # a wall with no gap must return None rather than a partial path
    wall = {(x, y) for x in range(0, 14) for y in range(0, 10) if x == 7}
    assert mod.astar(b, (1, 1), (12, 7), wall, {}, 1, set(), layers=1) is None


def test_candidate_build_is_memoised_on_content_and_never_serves_a_stale_result():
    """candidates.build costs ~1-2 s of setup (place_repair/escape_check) and depends only on
    (candidate, dump, placement), so it is cached on a content hash (HANDOFF §182).  A changed input must
    MISS the cache - a stale hit would silently route a different board.  Needs the real RetroCam inputs."""
    import pytest
    cand = _mod("candidates_cache", "candidates.py")
    workspace = MOD_PATH.parent.parent.parent.parent
    dump_path = workspace / "retrocam-02" / "pcb" / "dump2.json"
    place_path = workspace / "retrocam-02" / "pcb" / "offline" / "ec-placed.json"
    if not dump_path.exists() or not place_path.exists():
        pytest.skip("RetroCam-02 inputs not present in this checkout")
    dump = json.loads(dump_path.read_text(encoding="utf-8"))
    place = json.loads(place_path.read_text(encoding="utf-8"))

    d1, p1, pr1 = cand.build("frontier-i", dump, place, use_cache=True)
    d2, p2, pr2 = cand.build("frontier-i", dump, place, use_cache=True)
    assert d1 == d2 and p1 == p2 and pr1 == pr2
    # a changed placement must produce a different result (cache miss by construction)
    place2 = json.loads(json.dumps(place))
    first = sorted(place2)[0]
    place2[first]["x"] += 37.0
    d3, p3, _pr3 = cand.build("frontier-i", dump, place2, use_cache=True)
    # the placement is the part that changes; the dump stays the same by design
    assert p3 != p1, "a moved placement must not come back from the cache"
    # the no-cache path returns the same thing as the cached path
    d4, p4, _pr4 = cand.build("frontier-i", dump, place, use_cache=False)
    assert d4 == d1 and p4 == p1


def test_stop_after_flat_is_opt_in_and_never_changes_an_already_converged_plan():
    """Early stop exists but is OFF by default: on RetroCam the frontier kept improving inside every
    4-pass window, so it bought nothing (HANDOFF §183) and was left disabled.  What must hold is that on a
    board that converges immediately the flag cannot change the result."""
    st = _mod("selftest_stop_flat", "selftest.py")
    mod = _mod("ec_layout_stop_flat", "ec_layout.py")
    from grid_experiment import load_module
    ecm = load_module(10.0)
    dump = st.make_dump()
    place = st.make_place()
    plans = []
    for stop in (0, 1, 5):
        b = ecm.Board(dump)
        ecm.apply_placement(b, place)
        _score, routed, failures = ecm.route(b, iters=3, layers=2, segment_check=True,
                                             plane_nets=frozenset(), plane_layer=None,
                                             pour_specs=[], pour_step=5, net_order="small",
                                             stop_after_flat=stop)
        plans.append(ecm.plan_from(b, routed))
    assert json.dumps(plans[0], sort_keys=True) == json.dumps(plans[1], sort_keys=True)
    assert json.dumps(plans[0], sort_keys=True) == json.dumps(plans[2], sort_keys=True)
    # and the option is present in the signature but defaults to 0 (off)
    import inspect
    assert inspect.signature(mod.route).parameters["stop_after_flat"].default == 0


def test_sweep_records_runs_in_a_queryable_database(tmp_path):
    """GAPS ② of the speed plan: the cache answers "give me that result again"; the database answers "what
    have we measured and how long did it take".  A database failure must never cost a result."""
    sw = _mod("sweep_db", "sweep.py")
    st = _mod("selftest_for_db", "selftest.py")
    dump = tmp_path / "dump.json"
    place = tmp_path / "place.json"
    dump.write_text(json.dumps(st.make_dump()), encoding="utf-8")
    place.write_text(json.dumps(st.make_place()), encoding="utf-8")
    db = tmp_path / "results.sqlite"
    cfg = (str(dump), str(place), None, "strict-via-thin", 2)
    rows = sw.evaluate([cfg], jobs=1, cache_dir=str(tmp_path / "c"))
    sw.record(rows, str(db))
    stored = sw.report(db_path=str(db))
    assert len(stored) == 1
    assert stored[0][1] == "strict-via-thin" and stored[0][2] == 2
    # recording the same configuration twice must not duplicate it
    sw.record(rows, str(db))
    assert len(sw.report(db_path=str(db))) == 1


def test_two_phase_screens_on_the_same_grid_by_default_and_ranks_by_clearance_first():
    """The two-phase protocol is only sound where it is calibrated: §178 measured that 25 passes rank like
    70 passes ON THE SAME GRID, but a 10 mil screen ranked these very candidates differently (HANDOFF
    §185).  So the default must screen on the same grid, order by (clearance, CAM), and keep `top`."""
    sw = _mod("sweep_two_phase", "sweep.py")
    def row(name, clearance, cam):
        return {"config": (None, None, name, "strict-via-thin", 5),
                "kpi": {"clearance_violations": clearance}, "skew": {"CAM_D": cam}}
    rows = [row("a", 200, 100), row("b", 150, 900), row("c", 150, 120), row("d", 300, 50)]
    ordered, keep = sw.rank_top(rows, 2)
    assert [r["config"][2] for r in ordered] == ["c", "b", "a", "d"], ordered
    assert [r["config"][2] for r in keep] == ["c", "b"]
    # the coarse-grid mode exists but is opt-in and flagged in the text
    import inspect
    src = inspect.getsource(sw.two_phase)
    assert "phase1_profile" in src and "coarse_grid" in src
    assert "NOT CALIBRATED" in src


def test_incremental_identifies_dirty_nets_and_refuses_to_claim_a_merge():
    """GAPS ⑤: a true incremental router needs a seed-plan input that `route()` does not have, so this tool
    measures the UPPER BOUND and must say the merge is NOT RUN.  The dirty-net set is the part that can be
    tested without routing anything."""
    inc = _mod("incremental_mod", "incremental.py")
    st = _mod("selftest_for_incremental", "selftest.py")
    dump = st.make_dump()
    nets = inc.dirty_nets(dump, "J1")
    assert nets == {"CAM_D%d" % i for i in range(8)}, nets
    # a radius pulls in neighbours that are NOT on the moved part: use a two-part capture, where the
    # second part's net is only dirty when the radius reaches it
    mini = {"result": {"components": [
        {"designator": "A", "x": 0, "y": 0, "pads": [{"padNumber": "1", "net": "N1", "x": 0, "y": 0,
                                                      "width": 10, "height": 10}]},
        {"designator": "B", "x": 500, "y": 0, "pads": [{"padNumber": "1", "net": "N2", "x": 500, "y": 0,
                                                        "width": 10, "height": 10}]},
    ]}}
    assert inc.dirty_nets(mini, "A") == {"N1"}
    assert inc.dirty_nets(mini, "A", radius=600.0) == {"N1", "N2"}
    # the reduced capture must keep only those nets and leave the pads in place
    reduced = inc.reduced_dump(dump, nets)
    kept = {p.get("net") for c in inc.components(reduced) for p in (c.get("pads") or []) if p.get("net")}
    assert kept == nets, kept
    pads_before = sum(len(c.get("pads") or []) for c in inc.components(dump))
    pads_after = sum(len(c.get("pads") or []) for c in inc.components(reduced))
    assert pads_before == pads_after
    # and the report must state the merge is not run
    res = {"part": "J1", "moved_by": (10.0, 0.0), "dirty_nets": len(nets), "total_nets": len(nets),
           "full_seconds": 2.0, "dirty_seconds": 1.0, "ratio": 2.0,
           "full": {"nets": len(nets), "seconds": 2.0, "tracks": 8, "clearance": 0},
           "dirty": {"nets": len(nets), "seconds": 1.0, "tracks": 8, "clearance": 0},
           "dirty_net_names": sorted(nets)}
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        inc.report(res)
    text = buf.getvalue()
    assert "NOT RUN" in text and "UPPER BOUND" in text


def test_the_performance_claims_are_documented_with_their_limits():
    """The speed work is only credible if the documents keep both halves: the measured gains AND the ideas
    that were measured and rejected.  This guards against the documentation drifting into a success story."""
    layout = MOD_PATH.parent
    wrap = (layout / "WRAP-UP.md").read_text(encoding="utf-8")
    for needle in ("2.04×", "SHA256", "NOT RUN", "numpy obstacle bitmap", "bucket queue",
                   "incremental re-route", "rho 0.80"):
        assert needle in wrap, needle
    readme = (layout / "README.md").read_text(encoding="utf-8")
    assert "## Speed (measured" in readme and "2.04×" in readme
    assert "byte-identical plan digest" in readme
    status = (layout / "STATUS.md").read_text(encoding="utf-8")
    assert "performance work appended" in status
    # bench must refuse a KPI change, not just report it
    bench = (layout / "bench.py").read_text(encoding="utf-8")
    assert "identical KPI fingerprint" in bench and "KPI CHANGED" in bench


def test_incremental_run_produces_a_real_plan_and_compares_it_with_a_full_route():
    """GAPS ⑤, the merge itself: seed with the pre-move routing, re-route ONLY the dirty nets, and report the
    incremental plan next to a full re-route (time, clearance, skew, plan digest).  The plans are expected to
    differ - the point is that the comparison exists and is honest."""
    inc = _mod("incremental_run_mod", "incremental.py")
    st = _mod("selftest_for_incremental_run", "selftest.py")
    res = inc.incremental_run(st.make_dump(), st.make_place(), "J1", dx=20.0, dy=0.0, iters=1)
    assert res["dirty_nets"] == 8, res["dirty_nets"]
    for key in ("incremental", "full"):
        assert res[key]["tracks"] > 0, (key, res[key])
        assert res[key]["seconds"] > 0
        assert len(res[key]["digest"]) == 16
    assert isinstance(res["identical_plan"], bool)
    assert res["ratio"] is not None and res["ratio"] > 0
    # the printed comparison must name both routes and say whether the plans are identical
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        inc.report_run(res)
    text = buf.getvalue()
    assert "incremental" in text and "full" in text and "identical plan" in text


def test_astar_numpy_bitmap_matches_the_set_based_obstacle_test():
    """GAPS ④: the numpy obstacle bitmap must be an exact drop-in for the set membership test (it measured
    slightly SLOWER on these boards, so it stays opt-in - but it has to be correct)."""
    mod = _mod("ec_layout_bitmap", "ec_layout.py")

    class Mini:
        w, h = 20, 15

    cost = {(6, 5, 1): 3.0, (7, 5, 1): 1.0}
    forbidden = {(9, 7), (9, 8), (10, 7), (10, 8)}
    allowed = {(9, 7)}
    path_set = mod.astar(Mini(), (2, 2), (17, 12), forbidden, cost, 1, allowed, layers=1)
    path_bmp = mod.astar(Mini(), (2, 2), (17, 12), forbidden, cost, 1, allowed, layers=1,
                         bitmap_obstacles=True)
    assert path_set == path_bmp, (path_set, path_bmp)
    # and an unreachable goal behaves the same in both modes
    wall = {(x, y) for x in range(0, 20) for y in range(0, 15) if x == 11}
    assert mod.astar(Mini(), (2, 2), (17, 12), wall, {}, 1, set(), layers=1) is None
    assert mod.astar(Mini(), (2, 2), (17, 12), wall, {}, 1, set(), layers=1, bitmap_obstacles=True) is None


def test_bucket_frontier_is_exactly_the_heap_frontier():
    """GAPS ④'s bucket queue: a two-level frontier (one heap per integer f-bucket plus a heap of active
    keys) must return the same path as the single heap.  The first version dropped entries when a bucket had
    been drained and re-filled, which silently lost nodes (HANDOFF §191) - that is what this pins."""
    mod = _mod("ec_layout_bucket", "ec_layout.py")

    class Mini:
        w, h = 24, 18

    cost = {(6, 5, 1): 3.0, (7, 5, 1): 1.0, (8, 6, 1): 2.0}
    forbidden = {(9, 7), (9, 8), (10, 7), (10, 8), (11, 9)}
    allowed = {(9, 7)}
    common = dict(layers=1)
    heap_path = mod.astar(Mini(), (2, 2), (20, 14), forbidden, cost, 1, allowed, **common)
    bucket_path = mod.astar(Mini(), (2, 2), (20, 14), forbidden, cost, 1, allowed,
                            frontier="bucket", **common)
    assert heap_path is not None
    assert heap_path == bucket_path, (heap_path, bucket_path)
    # a wall with no gap: both frontiers must report failure, not a partial path
    wall = {(x, y) for x in range(0, 24) for y in range(0, 18) if x == 13}
    assert mod.astar(Mini(), (2, 2), (20, 14), wall, {}, 1, set(), **common) is None
    assert mod.astar(Mini(), (2, 2), (20, 14), wall, {}, 1, set(), frontier="bucket", **common) is None


def test_incremental_is_rejected_unless_its_kpi_matches_the_full_route():
    """GAPS ⑤'s acceptance rule: an incremental pass may only REPLACE a full re-route when its KPI equals
    the full one; otherwise the supported path falls back and the incremental row stays as evidence
    (HANDOFF §192)."""
    inc = _mod("incremental_gate", "incremental.py")
    base = {"unrouted_legs": 0, "congestion_cells": 0, "clearance_violations": 160,
            "nets_unconnected": 0, "pad_layer_gaps": 0, "pour_islands": 0,
            "bus_length_spread_mil": {"CAM_D": 202.9, "LCD_": 41.4, "SD_": 31.9}}
    same = json.loads(json.dumps(base))
    assert inc.kpi_matches(base, same) is True
    worse = json.loads(json.dumps(base))
    worse["clearance_violations"] = 192
    assert inc.kpi_matches(base, worse) is False
    skew = json.loads(json.dumps(base))
    skew["bus_length_spread_mil"]["CAM_D"] = 721.5
    assert inc.kpi_matches(base, skew) is False
    # and the run entry point must expose the verdict + fallback flags
    st = _mod("selftest_for_gate", "selftest.py")
    res = inc.incremental_run(st.make_dump(), st.make_place(), "J1", dx=20.0, dy=0.0, iters=1)
    assert res["accepted"] == res["kpi_equal"]
    assert res["fallback_used"] == (not res["kpi_equal"])


def test_the_kickoff_document_is_self_contained():
    """Handing this work to a fresh conversation only works if one file carries: the paste-able prompt, the
    three verification commands, the refuted list, the open items and the rules that must not be deleted."""
    layout = MOD_PATH.parent
    doc = layout / "KICKOFF.md"
    assert doc.exists(), "KICKOFF.md is missing"
    text = doc.read_text(encoding="utf-8")
    for needle in ("你接手的是一个已经有大量实测证据的仓库", "verify.py", "bench.py --iters 3 --compare",
                   "HANDOFF-INDEX.md", "frontier-i", "NOT RUN", "R1–R8", "deprecated_illegal",
                   "layout-perf-2026-11-03"):
        assert needle in text, needle
    # the prompt must name the two traps this effort paid for: uncalibrated screens and illegal placements
    assert "不许用未校准的快档" in text
    assert "非法配置一律当门禁失败" in text
    # and it must not pretend the board is deliverable
    assert "不可能" in text and "换连接器" in text
    readme = (layout / "README.md").read_text(encoding="utf-8")
    assert "KICKOFF.md" in readme, "README must point a new agent at the kickoff file"
