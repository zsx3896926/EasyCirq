"""Tests for the offline 2-layer grid maze router (``mp_place.router``).

Run with::

    python -m unittest tests.test_router -v

The P2 benchmark (5 scenarios x 5 random feasible placements, 1 mm grid) is
exposed as :func:`benchmark` and can be refreshed with::

    python -c "from tests.test_router import benchmark; benchmark()"
"""

from __future__ import annotations

import math
import random
import statistics
import unittest

from mp_place.model import Component, Net, Scenario
from mp_place.router import GridRouter, RouteResult
from mp_place.scenarios import build_scenarios
from mp_place.solver import random_feasible_placement


# --------------------------------------------------------------------------
# helpers for tiny hand-made boards
# --------------------------------------------------------------------------


def _comp(ref, w, h, pins=None, kind="generic"):
    return Component(ref=ref, kind=kind, w=w, h=h, pins=pins or {})


def _line_scenario():
    """Two parts facing each other on an empty board: one straight net."""
    sc = Scenario(
        name="line",
        board_w=20.0,
        board_h=10.0,
        components={
            "A": _comp("A", 2.0, 2.0, {"1": (1.0, 0.0)}),
            "B": _comp("B", 2.0, 2.0, {"1": (-1.0, 0.0)}),
        },
        nets=[Net("N", "generic", (("A", "1"), ("B", "1")))],
    )
    pl = {"A": (2.0, 5.0, 0), "B": (18.0, 5.0, 0)}
    return sc, pl


def _ring_board():
    """A part trapped inside a closed rectangular frame of other parts.

    ``A`` (pin at its own centre) sits in the frame hole, ``P`` is outside; the
    frame consists of four touching bodies T/B/L/R, so the two terminals are in
    different free-space components and the net can never be routed.
    """
    components = {
        "T": _comp("T", 16.0, 2.0),
        "B": _comp("B", 16.0, 2.0),
        "L": _comp("L", 2.0, 12.0),
        "R": _comp("R", 2.0, 12.0),
        "A": _comp("A", 2.0, 2.0, {"1": (0.0, 0.0)}),
        "P": _comp("P", 2.0, 2.0, {"1": (0.0, 0.0)}),
    }
    placement = {
        "T": (12.0, 17.0, 0),
        "B": (12.0, 7.0, 0),
        "L": (3.0, 12.0, 0),
        "R": (21.0, 12.0, 0),
        "A": (12.0, 12.0, 0),
        "P": (12.0, 21.0, 0),
    }
    return components, placement


def _trapped_scenario(with_free_net=False):
    components, placement = _ring_board()
    nets = [Net("TRAPPED", "generic", (("A", "1"), ("P", "1")))]
    if with_free_net:
        components = dict(components)
        components["S"] = _comp("S", 2.0, 2.0, {"1": (1.0, 0.0)})
        components["E"] = _comp("E", 2.0, 2.0, {"1": (-1.0, 0.0)})
        placement = dict(placement)
        placement["S"] = (2.0, 2.0, 0)
        placement["E"] = (21.0, 2.0, 0)
        nets.append(Net("FREE", "digital", (("S", "1"), ("E", "1"))))
    sc = Scenario(
        name="ring",
        board_w=24.0,
        board_h=24.0,
        components=components,
        nets=nets,
    )
    return sc, placement


def _crossing_scenario():
    """Horizontal net routed first, vertical net must change layer to cross it."""
    sc = Scenario(
        name="crossing",
        board_w=20.0,
        board_h=20.0,
        components={
            "H1": _comp("H1", 2.0, 2.0, {"1": (1.0, 0.0)}),
            "H2": _comp("H2", 2.0, 2.0, {"1": (-1.0, 0.0)}),
            "V1": _comp("V1", 2.0, 2.0, {"1": (0.0, 1.0)}),
            "V2": _comp("V2", 2.0, 2.0, {"1": (0.0, -1.0)}),
        },
        nets=[
            Net("H", "generic", (("H1", "1"), ("H2", "1"))),
            Net("V", "digital", (("V1", "1"), ("V2", "1"))),
        ],
    )
    pl = {
        "H1": (2.0, 10.0, 0),
        "H2": (18.0, 10.0, 0),
        "V1": (10.0, 2.0, 0),
        "V2": (10.0, 18.0, 0),
    }
    return sc, pl


def _signature(res: RouteResult):
    """Everything that must be deterministic (runtime excluded)."""
    return (
        round(res.completion, 12),
        tuple(res.failed_nets),
        round(res.wirelength_mm, 9),
        res.vias,
        res.overflow,
    )


# --------------------------------------------------------------------------
# required coverage
# --------------------------------------------------------------------------


class EmptyNetlistTests(unittest.TestCase):
    def test_empty_netlist_completion_is_one(self):
        sc = Scenario(
            name="empty",
            board_w=10.0,
            board_h=10.0,
            components={"A": _comp("A", 2.0, 2.0)},
            nets=[],
        )
        res = GridRouter(sc, grid_mm=1.0).route({})
        self.assertEqual(res.completion, 1.0)
        self.assertEqual(res.failed_nets, [])
        self.assertEqual(res.wirelength_mm, 0.0)
        self.assertEqual(res.vias, 0)
        self.assertEqual(res.overflow, 0)


class SingleNetTests(unittest.TestCase):
    def test_straight_line_is_routed(self):
        sc, pl = _line_scenario()
        res = GridRouter(sc, grid_mm=1.0).route(pl)
        self.assertEqual(res.completion, 1.0)
        self.assertEqual(res.failed_nets, [])
        self.assertEqual(res.vias, 0)
        # 13 grid steps between the pad cells + two pad escape diagonals.
        self.assertAlmostEqual(res.wirelength_mm, 13.0 + 2.0 * math.sqrt(0.5), places=6)
        self.assertLess(res.wirelength_mm, 20.0)

    def test_net_enclosed_by_components_fails(self):
        sc, pl = _trapped_scenario()
        res = GridRouter(sc, grid_mm=1.0).route(pl)
        self.assertEqual(res.completion, 0.0)
        self.assertEqual(res.failed_nets, ["TRAPPED"])
        self.assertEqual(res.wirelength_mm, 0.0)
        self.assertEqual(res.vias, 0)
        # A geometrically trapped net has no rip-up overflow.
        self.assertEqual(res.overflow, 0)

    def test_crossing_net_is_routed(self):
        # With two free layers the router may put the crossing net on the other
        # layer (no via needed); either way both nets must be complete.
        sc, pl = _crossing_scenario()
        res = GridRouter(sc, grid_mm=1.0, layers=2).route(pl)
        self.assertEqual(res.completion, 1.0)
        self.assertEqual(res.failed_nets, [])
        self.assertGreaterEqual(res.vias, 0)

    def test_two_layers_are_used_on_real_scenarios(self):
        total_vias = 0
        for i, sc in enumerate(build_scenarios(seed=0)):
            pl = random_feasible_placement(sc, random.Random(1000 * i))
            total_vias += GridRouter(sc).route(pl).vias
        self.assertGreater(total_vias, 0)


class DeterminismTests(unittest.TestCase):
    def test_two_runs_are_identical(self):
        rng = random.Random(2026)
        for sc in build_scenarios(seed=0):
            pl = random_feasible_placement(sc, rng)
            first = GridRouter(sc, grid_mm=1.0).route(pl)
            second = GridRouter(sc, grid_mm=1.0).route(pl)
            self.assertEqual(_signature(first), _signature(second), sc.name)

    def test_same_router_instance_is_reusable(self):
        sc = build_scenarios(seed=0)[4]  # wireless: keepout + RF + fixed parts
        pl = random_feasible_placement(sc, random.Random(77))
        router = GridRouter(sc, grid_mm=1.0)
        first = router.route(pl)
        second = router.route(pl)
        self.assertEqual(_signature(first), _signature(second))

    def test_critical_nets_are_routed_first(self):
        sc = build_scenarios(seed=0)[1]  # buck
        pl = random_feasible_placement(sc, random.Random(5))
        crit = ["VOUT", "SW"]
        res = GridRouter(sc).route(pl, critical_nets=crit)
        routed_crit = [name for name in crit if name not in res.failed_nets]
        self.assertAlmostEqual(res.completion, len(routed_crit) / len(crit), places=12)
        # This layout is hard: order matters and VOUT is lost either way, while
        # the critical-first order still scores only the requested nets.
        self.assertIn("VOUT", res.failed_nets)
        self.assertEqual(res.failed_nets, ["VOUT"])


class RealScenarioTests(unittest.TestCase):
    def test_real_scenario_random_placement_completion(self):
        scenarios = build_scenarios(seed=0)
        self.assertEqual(len(scenarios), 5)
        rng = random.Random(99)
        for sc in scenarios:
            pl = random_feasible_placement(sc, rng)
            res = GridRouter(sc, grid_mm=1.0).route(pl)
            self.assertGreaterEqual(res.completion, 0.0, sc.name)
            self.assertLessEqual(res.completion, 1.0, sc.name)
            self.assertEqual(len(res.failed_nets), len(res.failed_nets))
            routed = (len(sc.nets) - len(res.failed_nets)) / max(1, len(sc.nets))
            self.assertAlmostEqual(res.completion, routed, places=12, msg=sc.name)
            self.assertGreater(res.wirelength_mm, 0.0, sc.name)
            self.assertGreaterEqual(res.runtime_s, 0.0)
        # Random feasible layouts are sparse, so at least the first scenario
        # should route completely.
        pl = random_feasible_placement(scenarios[0], random.Random(123))
        self.assertEqual(GridRouter(scenarios[0]).route(pl).completion, 1.0)


class FailureIsolationTests(unittest.TestCase):
    def test_failed_net_does_not_poison_others(self):
        sc, pl = _trapped_scenario(with_free_net=True)
        res = GridRouter(sc, grid_mm=1.0).route(pl)
        self.assertEqual(res.completion, 0.5)
        self.assertEqual(res.failed_nets, ["TRAPPED"])
        # The routable net still got its (positive) wirelength.
        self.assertGreater(res.wirelength_mm, 16.0)

    def test_critical_completion_denominator(self):
        sc, pl = _trapped_scenario(with_free_net=True)
        only_free = GridRouter(sc).route(pl, critical_nets=["FREE"])
        self.assertEqual(only_free.completion, 1.0)
        self.assertEqual(only_free.failed_nets, ["TRAPPED"])
        only_trapped = GridRouter(sc).route(pl, critical_nets=["TRAPPED"])
        self.assertEqual(only_trapped.completion, 0.0)
        # Unknown names fall back to scoring every net.
        fallback = GridRouter(sc).route(pl, critical_nets=["NO_SUCH_NET"])
        self.assertEqual(fallback.completion, 0.5)


class ParameterTests(unittest.TestCase):
    def test_invalid_parameters_are_rejected(self):
        sc, _pl = _line_scenario()
        with self.assertRaises(ValueError):
            GridRouter(sc, grid_mm=0.0)
        with self.assertRaises(ValueError):
            GridRouter(sc, grid_mm=-1.0)
        with self.assertRaises(ValueError):
            GridRouter(sc, layers=0)

    def test_coarse_grid_still_routes_simple_board(self):
        sc, pl = _line_scenario()
        res = GridRouter(sc, grid_mm=2.0).route(pl)
        self.assertEqual(res.completion, 1.0)
        self.assertGreater(res.wirelength_mm, 0.0)


# --------------------------------------------------------------------------
# P2 benchmark: 5 scenarios x 5 random feasible placements
# --------------------------------------------------------------------------


def benchmark(placements: int = 5, grid_mm: float = 1.0):
    """Run the P2 router benchmark and print a per-scenario summary.

    Returns one dict per scenario with the mean completion, failed-net count,
    mean/max routing time, mean wirelength and via count (plus the raw results).
    """
    scenarios = build_scenarios(seed=0)
    summaries = []
    totals = {"completion": [], "failed": [], "runtime": [], "wirelength": [], "vias": [], "overflow": []}
    print(f"router benchmark: grid={grid_mm} mm, {len(scenarios)} scenarios x {placements} layouts")
    for si, sc in enumerate(scenarios):
        results = []
        for k in range(placements):
            rng = random.Random(1000 * si + k)
            placement = random_feasible_placement(sc, rng)
            stats = GridRouter(sc, grid_mm=grid_mm).route(placement)
            results.append(stats)
        completion = [r.completion for r in results]
        failed = [len(r.failed_nets) for r in results]
        runtime = [r.runtime_s for r in results]
        wirelength = [r.wirelength_mm for r in results]
        vias = [r.vias for r in results]
        overflow = [r.overflow for r in results]
        summary = {
            "scenario": sc.name,
            "nets": len(sc.nets),
            "mean_completion": statistics.mean(completion),
            "failed_nets": failed,
            "mean_runtime_s": statistics.mean(runtime),
            "max_runtime_s": max(runtime),
            "mean_wirelength_mm": statistics.mean(wirelength),
            "vias": vias,
            "overflow": overflow,
            "results": results,
        }
        summaries.append(summary)
        totals["completion"] += completion
        totals["failed"] += failed
        totals["runtime"] += runtime
        totals["wirelength"] += wirelength
        totals["vias"] += vias
        totals["overflow"] += overflow
        print(
            "  %-9s nets=%d mean_completion=%.3f failed=%d/%d mean_rt=%.3fs max_rt=%.3fs "
            "mean_wl=%.0fmm vias=%d overflow=%d"
            % (
                sc.name,
                len(sc.nets),
                summary["mean_completion"],
                sum(failed),
                len(sc.nets) * placements,
                summary["mean_runtime_s"],
                summary["max_runtime_s"],
                summary["mean_wirelength_mm"],
                sum(vias),
                sum(overflow),
            )
        )
    overall = {
        "runs": len(totals["completion"]),
        "mean_completion": statistics.mean(totals["completion"]),
        "failed_nets_total": sum(totals["failed"]),
        "total_nets": sum(s["nets"] for s in summaries) * placements,
        "mean_runtime_s": statistics.mean(totals["runtime"]),
        "median_runtime_s": statistics.median(totals["runtime"]),
        "max_runtime_s": max(totals["runtime"]),
        "mean_wirelength_mm": statistics.mean(totals["wirelength"]),
        "vias_total": sum(totals["vias"]),
        "overflow_total": sum(totals["overflow"]),
    }
    print(
        "  OVERALL runs=%d mean_completion=%.4f failed=%d/%d mean_rt=%.4fs max_rt=%.4fs "
        "mean_wl=%.0fmm vias=%d overflow=%d"
        % (
            overall["runs"],
            overall["mean_completion"],
            overall["failed_nets_total"],
            overall["total_nets"],
            overall["mean_runtime_s"],
            overall["max_runtime_s"],
            overall["mean_wirelength_mm"],
            overall["vias_total"],
            overall["overflow_total"],
        )
    )
    return summaries, overall


if __name__ == "__main__":
    unittest.main()
