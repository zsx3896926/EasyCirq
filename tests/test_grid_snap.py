"""Tests for grid snapping (offline: pure plan + geometry dictionaries).

The failure this guards (2026-10-30, C board): plan anchors such as
``C1 = (682.8, 760.5)`` put every pin off the 5-unit schematic grid, so EasyEDA
rejected each net-label stub and the write channel degraded.  Snapping the anchor
fixes the pins only because the pin offsets are themselves grid multiples - every
case below pins one of those assumptions down.
"""

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import grid_snap  # noqa: E402


def geometry(pins_by_ref):
    """``{"U1": {"1": (dx, dy), "2": (dx, dy)}, ...}`` -> pin-geometry dict."""
    return {"schema": "easycirq-pin-geometry/v1",
            "parts": {ref: {"cx": 0.0, "cy": 0.0,
                            "pins": {str(pin): {"dx": float(dx), "dy": float(dy),
                                                "rotation": 0, "side": "right",
                                                "net": "N_%s_%s" % (ref, pin)}
                                     for pin, (dx, dy) in pins.items()}}
                      for ref, pins in pins_by_ref.items()}}


#: a two-pin passive at +-20 on x, a four-pin block at +-20/+-40
GEOMETRY = geometry({
    "C1": {"1": (-20.0, 0.0), "2": (20.0, 0.0)},
    "R1": {"1": (-20.0, 0.0), "2": (20.0, 0.0)},
    "U1": {"1": (-40.0, -20.0), "2": (-40.0, 20.0),
           "3": (40.0, -20.0), "4": (40.0, 20.0)},
})


def plan(**anchors):
    return {"schema": "test", "placements": {
        ref: {"x": x, "y": y} for ref, (x, y) in anchors.items()}}


def grid(placements, geometry=GEOMETRY, **kwargs):
    return grid_snap.snap_plan({"placements": placements}, geometry, **kwargs)


class SnapValueTests(unittest.TestCase):
    def test_rounds_to_nearest_five(self):
        self.assertEqual(grid_snap.snap_value(682.8), 685.0)
        self.assertEqual(grid_snap.snap_value(760.5), 760.0)
        self.assertEqual(grid_snap.snap_value(131.8), 130.0)
        self.assertEqual(grid_snap.snap_value(-7.4), -5.0)

    def test_on_grid_tolerates_float_residue_only(self):
        self.assertTrue(grid_snap.on_grid(130.0))
        self.assertTrue(grid_snap.on_grid(130.0 + 1e-9))
        self.assertFalse(grid_snap.on_grid(130.4))
        self.assertFalse(grid_snap.on_grid(130.0 + 1e-3))

    def test_grid_constant_is_the_only_magic_number(self):
        self.assertEqual(grid_snap.GRID, 5.0)
        self.assertEqual(grid_snap.snap_value(5 * 37 + 0.1, grid_snap.GRID), 185.0)


class SnapPlanTests(unittest.TestCase):
    def test_snaps_every_anchor_and_puts_every_pin_on_grid(self):
        original = {"C1": {"x": 682.8, "y": 760.5, "ew": 84.0, "eh": 51.0,
                           "x0": 640.8, "y0": 735.0},
                    "R1": {"x": 131.8, "y": 553.5},
                    "U1": {"x": 600.3, "y": 400.7}}
        result = grid(original)
        snapped = result["placements"]
        self.assertEqual((snapped["C1"]["x"], snapped["C1"]["y"]), (685.0, 760.0))
        self.assertEqual((snapped["R1"]["x"], snapped["R1"]["y"]), (130.0, 555.0))
        report = result["report"]
        self.assertEqual(report["parts"], 3)
        self.assertEqual(report["pins_total"], 8)
        self.assertEqual(report["pins_off_grid_after"], 0)
        self.assertEqual(report["off_grid_pins_after"], [])
        self.assertGreater(report["pins_off_grid_before"], 0)
        self.assertLessEqual(report["max_displacement"], 2.5)

    def test_envelope_follows_its_anchor(self):
        result = grid({"C1": {"x": 682.8, "y": 760.5, "ew": 84.0, "eh": 51.0,
                              "x0": 640.8, "y0": 735.0}})
        place = result["placements"]["C1"]
        self.assertAlmostEqual(place["x"] - place["ew"] / 2.0, place["x0"])
        self.assertAlmostEqual(place["y"] - place["eh"] / 2.0, place["y0"])

    def test_report_has_the_required_keys(self):
        report = grid({"C1": {"x": 100.2, "y": 200.0}})["report"]
        for key in ("parts", "pins_total", "pins_off_grid_before",
                    "pins_off_grid_after", "max_displacement", "overlaps",
                    "out_of_page", "per_part"):
            self.assertIn(key, report)
        self.assertEqual(report["per_part"]["C1"]["pins"], 2)
        self.assertEqual(report["per_part"]["C1"]["pins_off_grid_after"], 0)

    def test_max_displacement_never_exceeds_half_a_grid(self):
        report = grid({"C1": {"x": 102.4, "y": 207.6},        # worst case: +-2.5
                       "R1": {"x": 99.9, "y": 300.1}})["report"]
        self.assertLessEqual(report["max_displacement"], 2.5)

    def test_bare_placements_map_is_accepted(self):
        report = grid_snap.snap_plan({"C1": {"x": 100.4, "y": 200.0}},
                                     GEOMETRY)["report"]
        self.assertEqual(report["parts"], 1)


class RejectionTests(unittest.TestCase):
    def test_pin_offset_off_the_grid_is_refused(self):
        bad = geometry({"C1": {"1": (-20.0, 0.0), "2": (20.0, 2.5)}})
        with self.assertRaises(ValueError) as caught:
            grid_snap.snap_plan({"placements": {"C1": {"x": 100.0, "y": 200.0}}}, bad)
        message = str(caught.exception)
        self.assertIn("C1:2", message)
        self.assertIn("not multiples of 5", message)

    def test_pin_off_grid_after_placing_is_detected(self):
        """The post-condition check (b) finds a pin the anchor left off grid."""
        off = {"C1": {"x": 100.4, "y": 200.0}}          # anchor not snapped
        self.assertEqual(len(grid_snap.pin_grid_violations(off, GEOMETRY)), 2)
        snapped = grid({"C1": {"x": 100.4, "y": 200.0}})["placements"]
        self.assertEqual(grid_snap.pin_grid_violations(snapped, GEOMETRY), [])

    def test_snapping_refuses_when_the_pin_check_fails(self):
        """snap_plan raises on (b) instead of returning a plan."""
        saved = grid_snap.pin_grid_violations
        grid_snap.pin_grid_violations = lambda *a, **k: [
            {"ref": "C1", "pin": "1", "x": 100.4, "y": 200.4}]
        try:
            with self.assertRaises(ValueError) as caught:
                grid_snap.snap_plan({"placements": {"C1": {"x": 100.0, "y": 200.0}}},
                                    GEOMETRY)
        finally:
            grid_snap.pin_grid_violations = saved
        self.assertIn("still off the 5-grid", str(caught.exception))

    def test_overlapping_parts_are_refused(self):
        blocks = geometry({"U1": {"1": (-40.0, -20.0), "2": (-40.0, 20.0),
                                  "3": (40.0, -20.0), "4": (40.0, 20.0)},
                           "U2": {"1": (-40.0, -20.0), "2": (-40.0, 20.0),
                                  "3": (40.0, -20.0), "4": (40.0, 20.0)}})
        with self.assertRaises(ValueError) as caught:
            grid_snap.snap_plan({"placements": {"U1": {"x": 100.0, "y": 200.0},
                                                "U2": {"x": 150.0, "y": 200.0}}},
                                blocks)
        self.assertIn("overlapping", str(caught.exception))

    def test_parts_touching_on_a_shared_pin_row_are_allowed(self):
        """The documented rule: abutment is not a collision, coincidence is."""
        result = grid({"C1": {"x": 100.0, "y": 200.0},
                       "C2": {"x": 140.0, "y": 200.0}},
                      geometry({"C1": {"1": (-20.0, 0.0), "2": (20.0, 0.0)},
                                "C2": {"1": (-20.0, 20.0), "2": (20.0, 20.0)}}))
        self.assertEqual(result["report"]["overlaps"], [])
        self.assertEqual(result["report"]["pin_collisions"], [])

    def test_shared_pin_coordinates_are_refused(self):
        with self.assertRaises(ValueError) as caught:
            grid_snap.snap_plan(
                {"placements": {"C1": {"x": 100.0, "y": 200.0},
                                "C2": {"x": 140.0, "y": 200.0}}},
                geometry({"C1": {"1": (-20.0, 0.0), "2": (20.0, 0.0)},
                          "C2": {"1": (-20.0, 0.0), "2": (20.0, 0.0)}}))
        self.assertIn("shared pin", str(caught.exception))

    def test_pin_outside_the_sheet_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            grid_snap.snap_plan({"placements": {"C1": {"x": 1160.0, "y": 200.0}}},
                                GEOMETRY, page=(10.0, 10.0, 1160.0, 815.0))
        self.assertIn("outside the sheet", str(caught.exception))

    def test_soft_mode_reports_collisions_without_raising(self):
        result = grid_snap.snap_plan(
            {"placements": {"C1": {"x": 100.0, "y": 200.0},
                            "C2": {"x": 140.0, "y": 200.0}}},
            geometry({"C1": {"1": (-20.0, 0.0), "2": (20.0, 0.0)},
                      "C2": {"1": (-20.0, 0.0), "2": (20.0, 0.0)}}),
            strict=False)
        self.assertEqual(len(result["report"]["pin_collisions"]), 1)
        self.assertEqual(result["report"]["pins_off_grid_after"], 0)

    def test_no_plan_is_returned_when_a_check_fails(self):
        """A rejected snap must not leak a half-snapped placements map."""
        out = {}
        try:
            out["value"] = grid_snap.snap_plan(
                {"placements": {"C1": {"x": 1160.0, "y": 200.0}}}, GEOMETRY)
        except ValueError:
            pass
        self.assertEqual(out, {})


class GeometryFromSnapshotTests(unittest.TestCase):
    def test_offsets_are_rebuilt_from_pin_coordinates(self):
        snapshot = {"components": [{
            "ref": "C1", "x": 500.0, "y": 200.0,
            "pins": [{"pinNumber": "1", "x": 480.0, "y": 200.0, "rotation": 180},
                     {"pinNumber": "2", "x": 520.0, "y": 200.0, "rotation": 0}]}]}
        built = grid_snap.geometry_from_snapshot(snapshot)
        self.assertEqual(built["counts"], {"parts": 1, "pins": 2})
        self.assertEqual(built["parts"]["C1"]["pins"]["1"]["dx"], -20.0)
        self.assertEqual(built["parts"]["C1"]["pins"]["2"]["side"], "right")

    def test_snapshot_without_coordinates_yields_no_parts(self):
        snapshot = {"components": [{"ref": "C1", "pins": [{"number": "1", "net": "GND"}]}]}
        self.assertEqual(grid_snap.geometry_from_snapshot(snapshot)["parts"], {})


class PreflightGridTests(unittest.TestCase):
    """``apply_engine.preflight`` must gate the anchor *and* the pin position."""

    def _op(self, x, y, ref="C1", pin="1", direction="left"):
        return {"id": "connect:%s:%s" % (ref, pin), "kind": "connect", "ref": ref,
                "pin": pin, "net": "N", "direction": direction, "x": x, "y": y}

    def test_off_grid_anchor_is_reported_with_the_pin_coordinate(self):
        import apply_engine

        # exactly the C board failure: plan anchor 682.8/760.5, pin offset -20
        problems = apply_engine.preflight([self._op(682.8, 760.5)], GEOMETRY)
        self.assertEqual(len(problems), 1)
        self.assertEqual(problems[0]["code"], "geometry")
        self.assertIn("C1:1", problems[0]["detail"])
        self.assertIn("662.800", problems[0]["detail"])   # the coordinate EDA saw
        self.assertIn("760.500", problems[0]["detail"])

    def test_pin_offset_off_the_grid_is_reported(self):
        import apply_engine

        odd = geometry({"C1": {"1": (-20.0, 0.0), "2": (20.0, 2.5)}})
        problems = apply_engine.preflight([self._op(100.0, 200.0, pin="2")], odd)
        self.assertEqual(problems[0]["code"], "geometry")
        self.assertIn("offset", problems[0]["detail"])
        self.assertIn("C1:2", problems[0]["detail"])

    def test_snapped_op_passes(self):
        import apply_engine

        problems = apply_engine.preflight([self._op(685.0, 760.0)], GEOMETRY)
        self.assertEqual(problems, [])


class PlannerWiringTests(unittest.TestCase):
    """The two planners must publish snapped placements (offline, tiny snapshot)."""

    SNAPSHOT = {"components": [
        {"ref": "U1", "x": 300.0, "y": 300.0,
         "bbox": {"minX": 260.0, "minY": 260.0, "maxX": 340.0, "maxY": 340.0},
         "pins": [{"number": "1", "name": "1", "net": "VIN"},
                  {"number": "2", "name": "2", "net": "VOUT"}]},
        {"ref": "C1", "x": 360.0, "y": 300.0,
         "bbox": {"minX": 350.0, "minY": 292.0, "maxX": 370.0, "maxY": 308.0},
         "pins": [{"number": "1", "name": "1", "net": "VIN"},
                  {"number": "2", "name": "2", "net": "GND"}]},
    ]}
    GEOMETRY = geometry({"U1": {"1": (-30.0, -10.0), "2": (30.0, -10.0)},
                         "C1": {"1": (-10.0, 0.0), "2": (10.0, 0.0)}})

    def test_channel_layout_plan_publishes_snapped_placements(self):
        import channel_layout

        result = channel_layout.plan(self.SNAPSHOT,
                                     [{"id": "g", "title": "g",
                                       "designators": ["U1", "C1"]}],
                                     self.GEOMETRY)
        placements = {}
        for page in result["pages"]:
            placements.update(page["placements"])
        self.assertEqual(len(placements), 2)
        for place in placements.values():
            self.assertTrue(grid_snap.on_grid(place["x"]))
            self.assertTrue(grid_snap.on_grid(place["y"]))
        self.assertEqual(result["counts"]["pins_off_grid_after"], 0)

    def test_readable_plan_make_snaps_anchors_without_geometry(self):
        import readable_plan

        result = readable_plan.make(self.SNAPSHOT,
                                    [{"id": "g", "title": "g",
                                      "designators": ["U1", "C1"]}])
        self.assertEqual(result["counts"]["pins_off_grid_after"], 0)
        for place in result["placements"].values():
            self.assertTrue(grid_snap.on_grid(place["x"]))
            self.assertTrue(grid_snap.on_grid(place["y"]))


if __name__ == "__main__":
    unittest.main()
