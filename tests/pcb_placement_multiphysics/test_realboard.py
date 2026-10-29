"""Tests for P4.5 real-board dump -> Scenario conversion (stdlib unittest).

Run with::

    python -m unittest tests.test_realboard -v

Covered contract
----------------
* synthetic dump conversion: mil -> mm unit verification, bbox -> unrotated
  body w/h, pad positions -> local offsets with ``R(-rotation)``, duplicate pad
  numbers merged into one pin, nets grouped from ``pad.net`` (empty/single-pin
  nets dropped), fixed J/SW components, component filtering with reasons;
* determinism of the conversion (same dump -> identical report/scenario) and
  the ``sha256_file`` helper;
* malformed payloads are rejected (no components / implausible units / no
  routable nets);
* ``run_board`` / ``run_all`` wiring on a synthetic dump (small budgets) is
  JSON-serialisable and renders markdown;
* the CLI works end-to-end on an explicit ``--source NAME=PATH`` dump;
* the three real EasyCirq dumps (read-only) are smoked when present -- skipped
  when the case repository is not on this machine.
"""

from __future__ import annotations

import hashlib
import json
import math
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2] / "benchmarks" / "pcb-placement-multiphysics"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mp_place import realboard  # noqa: E402
from mp_place.model import pad_position  # noqa: E402

MIL = realboard.MIL_TO_MM


# --------------------------------------------------------------------------- #
# synthetic dump
# --------------------------------------------------------------------------- #
def _bbox(min_x, min_y, max_x, max_y):
    return {"minX": min_x, "minY": min_y, "maxX": max_x, "maxY": max_y}


def _pad(number, net, x, y):
    return {"padNumber": number, "net": net, "x": x, "y": y}


def synthetic_dump():
    """A small 1200 x 800 mil board exercising every conversion rule."""
    return {
        "project": "synthetic-board",
        "capturedAt": "2026-01-01T00:00:00Z",
        "semanticSha256": "0" * 64,
        "outline": {
            "format": "polyline",
            "source": "synthetic",
            "bbox": _bbox(0, 0, 1200, 800),
            "points": [[0, 0], [1200, 0], [1200, 800], [0, 800]],
        },
        "components": [
            {
                "designator": "J1",
                "device": "USB-C-16P",
                "x": 100,
                "y": 400,
                "rotation": 0,
                "bbox": _bbox(40, 300, 160, 500),
                "pads": [
                    _pad("1", "VIN", 80, 350),
                    _pad("2", "GND", 80, 450),
                    _pad("3", "USB_DM", 120, 350),
                    _pad("4", "USB_DP", 120, 450),
                ],
            },
            {
                "designator": "U1",
                "device": "MCU",
                "x": 600,
                "y": 400,
                "rotation": 90,
                "bbox": _bbox(550, 300, 650, 500),
                "pads": [
                    _pad("1", "VIN", 600, 350),
                    _pad("2", "GND", 600, 450),
                    _pad("3", "USB_DM", 650, 400),
                    _pad("4", "BOOT", 550, 400),
                    _pad("5", "GND", 600, 380),
                    _pad("5", "GND", 600, 420),
                ],
            },
            {
                "designator": "C1",
                "device": "CL05B104KO5NNNC 0402",
                "x": 1000,
                "y": 400,
                "rotation": 0,
                "bbox": _bbox(962.6, 377.35, 1037.4, 422.65),
                "pads": [
                    _pad("1", "VIN", 983.5, 400),
                    _pad("2", "GND", 1016.5, 400),
                ],
            },
            {
                "designator": "SW1",
                "device": "TACT-6",
                "x": 300,
                "y": 700,
                "rotation": 0,
                "bbox": _bbox(250, 650, 350, 750),
                "pads": [
                    _pad("1", "BOOT", 275, 675),
                    _pad("2", "GND", 275, 725),
                ],
            },
            {
                "designator": "R1",
                "device": "RC0402",
                "x": 800,
                "y": 700,
                "rotation": 0,
                "bbox": _bbox(762.6, 677.35, 837.4, 722.65),
                "pads": [
                    _pad("1", "", 783.5, 700),  # unconnected copper: ignored by nets
                    _pad("2", "", 816.5, 700),
                ],
            },
            {  # out of board -> dropped
                "designator": "D1",
                "device": "1N4148",
                "x": 1300,
                "y": 400,
                "rotation": 0,
                "bbox": _bbox(1260, 350, 1340, 450),
                "pads": [_pad("1", "GND", 1270, 400)],
            },
            {  # degenerate bbox -> dropped
                "designator": "D2",
                "device": "1N4148",
                "x": 400,
                "y": 100,
                "rotation": 0,
                "bbox": _bbox(410, 90, 410, 110),
                "pads": [_pad("1", "GND", 410, 100)],
            },
            {  # duplicate designator -> dropped
                "designator": "C1",
                "device": "dup",
                "x": 500,
                "y": 600,
                "rotation": 0,
                "bbox": _bbox(490, 590, 510, 610),
                "pads": [_pad("1", "GND", 495, 600)],
            },
            {  # no usable pads -> dropped
                "designator": "E1",
                "device": "no-pads",
                "x": 700,
                "y": 100,
                "rotation": 0,
                "bbox": _bbox(690, 90, 710, 110),
                "pads": [],
            },
        ],
    }


def _write_dump(tmpdir, payload=None) -> pathlib.Path:
    path = pathlib.Path(tmpdir) / "synthetic-dump.json"
    path.write_text(json.dumps(payload or synthetic_dump()), encoding="utf-8")
    return path


def serialise_scenario(scenario):
    """JSON-ish canonical snapshot of a Scenario for equality assertions."""
    return {
        "name": scenario.name,
        "board": [round(scenario.board_w, 6), round(scenario.board_h, 6)],
        "components": {
            ref: {
                "kind": comp.kind,
                "wh": [round(comp.w, 6), round(comp.h, 6)],
                "fixed": comp.fixed,
                "rotations": list(comp.rotations),
                "pins": {pin: [round(dx, 6), round(dy, 6)] for pin, (dx, dy) in comp.pins.items()},
            }
            for ref, comp in scenario.components.items()
        },
        "nets": [
            {"name": net.name, "cls": net.cls, "pins": list(net.pins)} for net in scenario.nets
        ],
        "keepouts": list(scenario.keepouts),
        "base": {
            ref: [round(x, 6), round(y, 6), rot]
            for ref, (x, y, rot) in scenario.base_placement.items()
        },
    }


# --------------------------------------------------------------------------- #
# conversion
# --------------------------------------------------------------------------- #
class SyntheticConversionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.converted = realboard.convert_dump(
            synthetic_dump(),
            name="synthetic",
            source="memory:synthetic",
            source_sha256="deadbeef",
            source_bytes=1234,
        )
        cls.scenario = cls.converted.scenario
        cls.report = cls.converted.report

    def test_board_and_unit_conversion(self):
        self.assertAlmostEqual(self.scenario.board_w, 1200 * MIL, places=6)
        self.assertAlmostEqual(self.scenario.board_h, 800 * MIL, places=6)
        units = self.report["units"]
        self.assertTrue(units["mil_interpretation_plausible"])
        self.assertTrue(units["mm_interpretation_rejected"])
        self.assertEqual(units["declared_unit"], "mil")
        self.assertAlmostEqual(units["scale_to_mm"], 0.0254)
        self.assertEqual(units["closest_to_0402_mil"], 74.8)
        median = units["passive_bbox_long_side_mm"]["median"]
        self.assertGreaterEqual(median, 1.0)
        self.assertLessEqual(median, 3.0)
        self.assertEqual(units["board_mm"], [30.48, 20.32])

    def test_components_kept_and_filtered(self):
        self.assertEqual(sorted(self.scenario.components), ["C1", "J1", "R1", "SW1", "U1"])
        self.assertEqual(self.report["components_total"], 9)
        self.assertEqual(self.report["components_kept"], 5)
        reasons = {item["ref"]: item["reason"] for item in self.report["dropped_components"]}
        self.assertTrue(reasons["D1"].startswith("out_of_board"), reasons["D1"])
        self.assertEqual(reasons["D2"], "invalid_bbox")
        self.assertEqual(reasons["E1"], "no_usable_pads")
        self.assertEqual(reasons["C1"], "duplicate_designator")

    def test_body_size_from_bbox(self):
        c1 = self.scenario.components["C1"]
        self.assertAlmostEqual(c1.w, 74.8 * MIL, places=5)
        self.assertAlmostEqual(c1.h, 45.3 * MIL, places=5)
        # U1 rotated 90 deg: axis-aligned bbox (100 x 200 mil) -> unrotated (200 x 100 mil).
        u1 = self.scenario.components["U1"]
        self.assertAlmostEqual(u1.w, 200 * MIL, places=5)
        self.assertAlmostEqual(u1.h, 100 * MIL, places=5)

    def test_pad_local_offsets_round_trip(self):
        # U1 rotation 90: a pad 50 mil below the centre maps to local (-50, 0)
        # because pad_position() rotates +90 deg back: (-(-50), -50) = (50, -50)...
        # i.e. rotate_point(lx, ly, 90) == (-ly, lx).
        comp = self.scenario.components["U1"]
        lx, ly = comp.pins["1"]
        self.assertAlmostEqual(lx, -50 * MIL, places=6)
        self.assertAlmostEqual(ly, 0.0, places=6)
        # Reconstruct every unique captured pad position through the model helper.
        payload = synthetic_dump()
        raw = {}
        for item in payload["components"]:
            raw.setdefault(item["designator"], item)  # first occurrence wins (dup refs dropped)
        for ref, component in self.scenario.components.items():
            x, y, rot = self.converted.original_placement[ref]
            counts = {}
            for pad in raw[ref]["pads"]:
                counts[pad["padNumber"]] = counts.get(pad["padNumber"], 0) + 1
            for pad in raw[ref]["pads"]:
                pin = pad["padNumber"]
                if counts[pin] > 1:  # merged duplicate pad numbers reconstruct as a mean
                    continue
                px, py = pad_position(component, x, y, rot, pin)
                self.assertAlmostEqual(px, pad["x"] * MIL, places=5)
                self.assertAlmostEqual(py, pad["y"] * MIL, places=5)

    def test_duplicate_pad_numbers_merge(self):
        u1 = self.scenario.components["U1"]
        self.assertIn("5", u1.pins)
        self.assertAlmostEqual(u1.pins["5"][0], 0.0, places=6)
        self.assertAlmostEqual(u1.pins["5"][1], 0.0, places=6)
        self.assertEqual(self.report["pads_merged"], 1)
        self.assertEqual(self.report["pads_total"], 19)
        self.assertEqual(self.report["pads_used"], 16)

    def test_nets_grouped_from_pad_net(self):
        nets = {net.name: net for net in self.scenario.nets}
        self.assertEqual(sorted(nets), ["BOOT", "GND", "USB_DM", "VIN"])
        self.assertEqual(nets["VIN"].cls, "power")
        self.assertEqual(nets["GND"].cls, "ground")
        self.assertEqual(nets["USB_DM"].cls, "digital")
        self.assertEqual(nets["BOOT"].cls, "digital")
        self.assertEqual(nets["VIN"].pins, (("J1", "1"), ("U1", "1"), ("C1", "1")))
        self.assertEqual(nets["BOOT"].pins, (("U1", "4"), ("SW1", "1")))
        dropped = {item["name"]: item["reason"] for item in self.report["dropped_nets"]}
        self.assertEqual(dropped, {"USB_DP": "single_pin_net"})
        self.assertEqual(self.report["nets_total"], 5)
        self.assertEqual(self.report["nets_kept"], 4)

    def test_fixed_components_and_original_placement(self):
        fixed = sorted(self.report["fixed_refs"])
        self.assertEqual(fixed, ["J1", "SW1"])
        self.assertEqual(sorted(self.scenario.base_placement), fixed)
        self.assertEqual(self.report["fixed_mode"], "j_sw_prefix")
        x, y, rot = self.converted.original_placement["J1"]
        self.assertAlmostEqual(x, 100 * MIL, places=6)
        self.assertAlmostEqual(y, 400 * MIL, places=6)
        self.assertEqual(rot, 0)
        self.assertEqual(self.report["original_violations"], [])
        self.assertTrue(self.scenario.components["J1"].fixed)
        self.assertFalse(self.scenario.components["U1"].fixed)

    def test_all_movable_fallback_is_recorded(self):
        payload = synthetic_dump()
        for comp in payload["components"]:
            ref = str(comp.get("designator", "")).upper()
            if ref.startswith(("J", "SW")):
                comp["designator"] = "X" + comp["designator"]
        converted = realboard.convert_dump(payload, name="no-fixed")
        self.assertEqual(converted.report["fixed_mode"], "all_movable")
        self.assertEqual(converted.report["fixed_refs"], [])
        self.assertEqual(converted.scenario.base_placement, {})
        self.assertTrue(all(not comp.fixed for comp in converted.scenario.components.values()))

    def test_conversion_is_deterministic(self):
        first = realboard.convert_dump(synthetic_dump(), name="synthetic")
        second = realboard.convert_dump(synthetic_dump(), name="synthetic")
        self.assertEqual(first.report, second.report)
        self.assertEqual(serialise_scenario(first.scenario), serialise_scenario(second.scenario))

    def test_sha256_helper(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_dump(tmp)
            self.assertEqual(
                realboard.sha256_file(path),
                hashlib.sha256(path.read_bytes()).hexdigest(),
            )


class ConversionErrorTests(unittest.TestCase):
    def test_missing_components_rejected(self):
        with self.assertRaises(ValueError):
            realboard.convert_dump({"outline": {"bbox": _bbox(0, 0, 100, 100)}}, name="bad")

    def test_implausible_units_rejected(self):
        payload = synthetic_dump()
        payload["outline"]["bbox"] = _bbox(0, 0, 100, 80)
        payload["outline"]["points"] = [[0, 0], [100, 0], [100, 80], [0, 80]]
        for comp in payload["components"]:
            comp["bbox"] = _bbox(10, 10, 20, 15)  # 10 units -> 0.25 mm at mil scale
            comp["x"], comp["y"] = 15, 12
            for pad in comp["pads"]:
                pad["x"], pad["y"] = 15, 12
        with self.assertRaises(ValueError):
            realboard.convert_dump(payload, name="implausible-units")

    def test_no_routable_nets_rejected(self):
        payload = synthetic_dump()
        for comp in payload["components"]:
            for pad in comp["pads"]:
                pad["net"] = ""
        with self.assertRaises(ValueError):
            realboard.convert_dump(payload, name="no-nets")


# --------------------------------------------------------------------------- #
# experiment wiring on the synthetic dump
# --------------------------------------------------------------------------- #
class RunBoardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.converted = realboard.convert_dump(synthetic_dump(), name="synthetic")
        cls.row = realboard.run_board(cls.converted, steps=0, seed=0, max_routes=1)

    def test_row_structure(self):
        row = self.row
        self.assertEqual(row["name"], "synthetic")
        for group in ("original", "optimized", "repair"):
            metrics = row[group]
            self.assertIn("feasible", metrics)
            self.assertIn("truth_v1", metrics)
            self.assertIn("truth_v2", metrics)
            self.assertIn("router", metrics)
            self.assertGreaterEqual(metrics["truth_v2"], 0.0)
            router = metrics["router"]
            self.assertEqual(router["status"], "ROUTED")
            self.assertGreaterEqual(router["completion"], 0.0)
            self.assertLessEqual(router["completion"], 1.0)
        self.assertEqual(row["original"]["violations"], [])
        self.assertEqual(row["optimized"]["violations"], [])
        self.assertEqual(row["repair"]["violations"], [])

    def test_deltas_and_objective(self):
        row = self.row
        self.assertIn("objective", row)
        self.assertIn("w_route", row["objective"])
        self.assertIn("optimized_truth_v2", row["deltas"])
        self.assertIn("repair_completion", row["deltas"])
        self.assertIn("solver_stats", row)
        self.assertIn("repair_stats", row)

    def test_report_round_trip_and_markdown(self):
        report = {
            "schema": realboard.REALBOARD_SCHEMA,
            "generated_at": "2026-01-01 00:00:00 +0000",
            "runtime_s": 0.01,
            "config": {"steps": 0, "seed": 0, "max_routes": 1},
            "sources": [{"name": "synthetic", "source": "memory"}],
            "boards": [self.row],
            "missing_sources": [],
            "aggregate": realboard._aggregate([self.row]),
            "limits": list(realboard.LIMITS),
        }
        text = json.dumps(realboard._json_safe(report), ensure_ascii=False)
        self.assertIn(realboard.REALBOARD_SCHEMA, text)
        markdown = realboard.render_markdown(report)
        for token in ("# P4.5 真实板", "## 汇总", "synthetic", "单位与对象", "边界与限制"):
            self.assertIn(token, markdown)


class RunAllAndCliTests(unittest.TestCase):
    def test_run_all_from_explicit_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            dump_path = _write_dump(tmp)
            report = realboard.run_all(sources=[("synthetic", dump_path)], steps=0, max_routes=1)
            self.assertEqual(report["schema"], realboard.REALBOARD_SCHEMA)
            self.assertEqual(report["aggregate"]["n_boards"], 1)
            self.assertEqual(len(report["boards"]), 1)
            self.assertEqual(report["boards"][0]["name"], "synthetic")
            self.assertEqual(
                report["boards"][0]["source_sha256"], realboard.sha256_file(dump_path)
            )
            self.assertTrue(
                report["boards"][0]["conversion"]["units"]["mil_interpretation_plausible"]
            )
            out_dir = pathlib.Path(tmp) / "out"
            paths = realboard.write_reports(report, out_dir=out_dir)
            self.assertTrue(paths["markdown"].exists())
            self.assertTrue(paths["json"].exists())
            loaded = json.loads(paths["json"].read_text(encoding="utf-8"))
            self.assertEqual(loaded["schema"], realboard.REALBOARD_SCHEMA)
            self.assertIn("synthetic", paths["markdown"].read_text(encoding="utf-8"))

    def test_missing_source_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = realboard.run_all(
                sources=[("missing", pathlib.Path(tmp) / "nope.json")], steps=0, max_routes=1
            )
            self.assertEqual(report["aggregate"]["n_boards"], 0)
            self.assertEqual(len(report["missing_sources"]), 1)
            self.assertEqual(report["missing_sources"][0]["status"], "MISSING")

    def test_cli_with_explicit_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            dump_path = _write_dump(tmp)
            out_dir = pathlib.Path(tmp) / "out"
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "mp_place.realboard",
                    "--v1",
                    "--source",
                    f"synthetic={dump_path}",
                    "--steps",
                    "0",
                    "--max-routes",
                    "1",
                    "--out",
                    str(out_dir),
                    "--json",
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=300,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr[-3000:])
            report = json.loads(proc.stdout)
            self.assertEqual(report["schema"], realboard.REALBOARD_SCHEMA)
            self.assertEqual(report["aggregate"]["n_boards"], 1)
            self.assertTrue((out_dir / realboard.REPORT_MD).exists())
            self.assertTrue((out_dir / realboard.REPORT_JSON).exists())

    def test_cli_bad_source_spec(self):
        proc = subprocess.run(
            [sys.executable, "-m", "mp_place.realboard", "--source", "not-a-pair"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120,
        )
        self.assertEqual(proc.returncode, 2)
        self.assertIn("NAME=PATH", proc.stderr)


# --------------------------------------------------------------------------- #
# real dumps (read-only, optional smoke)
# --------------------------------------------------------------------------- #
_AVAILABLE_REAL_SOURCES = [
    (name, path) for name, path in realboard.DEFAULT_SOURCES if path.exists()
]


@unittest.skipUnless(_AVAILABLE_REAL_SOURCES, "EasyCirq case dumps are not available on this machine")
class RealDumpSmokeTests(unittest.TestCase):
    def test_real_dumps_convert_and_are_feasible(self):
        for name, path in _AVAILABLE_REAL_SOURCES:
            with self.subTest(board=name):
                converted = realboard.load_and_convert(path, name=name)
                scenario = converted.scenario
                self.assertGreaterEqual(len(scenario.components), 5)
                self.assertGreaterEqual(len(scenario.nets), 2)
                self.assertGreaterEqual(scenario.board_w, 10.0)
                self.assertLessEqual(scenario.board_w, 250.0)
                self.assertGreaterEqual(scenario.board_h, 5.0)
                units = converted.report["units"]
                self.assertTrue(units["mil_interpretation_plausible"])
                self.assertTrue(units["mm_interpretation_rejected"])
                self.assertEqual(len(converted.report["source_sha256"]), 64)
                self.assertEqual(converted.report["original_violations"], [])
                for ref, comp in scenario.components.items():
                    if ref.upper().startswith(realboard.FIXED_PREFIXES):
                        self.assertTrue(comp.fixed, ref)
                metrics = realboard.evaluate_placement(scenario, converted.original_placement)
                self.assertTrue(metrics["feasible"])
                self.assertGreaterEqual(metrics["truth_v2"], 0.0)
                self.assertEqual(metrics["router"]["status"], "ROUTED")
                self.assertGreaterEqual(metrics["router"]["completion"], 0.0)
                self.assertLessEqual(metrics["router"]["completion"], 1.0)

    def test_one_real_board_run_board(self):
        name, path = _AVAILABLE_REAL_SOURCES[0]
        converted = realboard.load_and_convert(path, name=name)
        row = realboard.run_board(converted, steps=0, seed=0, max_routes=1)
        self.assertEqual(row["name"], name)
        self.assertEqual(row["original"]["violations"], [])
        self.assertEqual(row["optimized"]["violations"], [])
        self.assertEqual(row["repair"]["violations"], [])
        json.dumps(realboard._json_safe(row), ensure_ascii=False)


# --------------------------------------------------------------------------- #
# v2: polygon outline (ray casting), discovery, keepouts, edge overhang
# --------------------------------------------------------------------------- #
class PolygonTests(unittest.TestCase):
    SQUARE = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
    LSHAPE = [(0.0, 0.0), (10.0, 0.0), (10.0, 3.0), (3.0, 3.0), (3.0, 10.0), (0.0, 10.0)]

    def test_inside_and_outside(self):
        self.assertTrue(realboard.point_in_polygon(5.0, 5.0, self.SQUARE))
        self.assertFalse(realboard.point_in_polygon(11.0, 5.0, self.SQUARE))
        self.assertFalse(realboard.point_in_polygon(-1.0, 5.0, self.SQUARE))
        self.assertFalse(realboard.point_in_polygon(5.0, -1.0, self.SQUARE))
        self.assertTrue(realboard.point_in_polygon(1.0, 1.0, self.LSHAPE))
        self.assertFalse(realboard.point_in_polygon(8.0, 8.0, self.LSHAPE))  # notch

    def test_boundary_counts_as_inside(self):
        for point in ((0.0, 0.0), (5.0, 0.0), (10.0, 5.0), (0.0, 10.0), (10.0, 10.0)):
            self.assertTrue(realboard.point_in_polygon(*point, self.SQUARE), point)
        self.assertTrue(realboard.point_in_polygon(3.0, 3.0, self.LSHAPE))  # reflex corner
        self.assertTrue(realboard.point_in_polygon(1.5, 3.0, self.LSHAPE))  # edge

    def test_polygon_area(self):
        self.assertAlmostEqual(realboard.polygon_area(self.SQUARE), 100.0)
        self.assertAlmostEqual(realboard.polygon_area(self.LSHAPE), 51.0)

    def test_board_polygon_rect_outside(self):
        polygon = realboard.BoardPolygon(self.SQUARE)
        self.assertEqual(polygon.rect_outside((1.0, 1.0, 2.0, 2.0)), (0, 0.0))
        outside, worst = polygon.rect_outside((8.0, 8.0, 11.0, 11.0))
        self.assertEqual(outside, 3)  # three corners outside the 0..10 square
        self.assertAlmostEqual(worst, math.sqrt(2.0), places=6)
        self.assertEqual(polygon.bbox, (0.0, 0.0, 10.0, 10.0))
        self.assertAlmostEqual(polygon.boundary_distance(5.0, 5.0), 5.0, places=6)
        self.assertAlmostEqual(polygon.boundary_distance(11.0, 5.0), 1.0, places=6)

    def test_degenerate_polygon_is_rejected(self):
        with self.assertRaises(ValueError):
            realboard.BoardPolygon([(0.0, 0.0), (1.0, 1.0)])


class DiscoveryTests(unittest.TestCase):
    def _case(self, root, case_name):
        evidence = pathlib.Path(root) / case_name / "evidence"
        evidence.mkdir(parents=True)
        return evidence

    def test_auto_discovery_preference_and_skipped_cases(self):
        with tempfile.TemporaryDirectory() as tmp:
            evidence = self._case(tmp, "alpha-board-2026-01-01")
            payload = synthetic_dump()
            (evidence / "pcb-dump-after-reload.json").write_text(
                json.dumps(payload), encoding="utf-8"
            )
            (evidence / "pcb-dump-final.json").write_text(json.dumps(payload), encoding="utf-8")
            beta = pathlib.Path(tmp) / "beta-case-2026-01-02"
            beta.mkdir(parents=True)
            (beta / "notes.json").write_text(json.dumps({"note": "no dump"}), encoding="utf-8")
            boards, skipped = realboard.discover_cases(tmp)
            self.assertEqual(len(boards), 1)
            source = boards[0]
            self.assertEqual(source.name, "alpha-board")
            self.assertEqual(source.case, "alpha-board-2026-01-01")
            self.assertEqual(source.path.name, "pcb-dump-final.json")
            self.assertTrue(source.alternatives and "after-reload" in source.alternatives[0])
            self.assertEqual(len(skipped), 1)
            self.assertEqual(skipped[0]["case"], "beta-case-2026-01-02")
            self.assertIn("no dump-like JSON", skipped[0]["reason"])

    def test_board_baseline_preference(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = pathlib.Path(tmp) / "buttons-20261027" / "negative"
            folder.mkdir(parents=True)
            (folder / "board-accepted-baseline.json").write_text(
                json.dumps(synthetic_dump()), encoding="utf-8"
            )
            (folder / "board-baseline.json").write_text(
                json.dumps(synthetic_dump()), encoding="utf-8"
            )
            boards, skipped = realboard.discover_cases(tmp)
            self.assertEqual(skipped, [])
            self.assertEqual(len(boards), 1)
            self.assertEqual(boards[0].path.name, "board-baseline.json")

    def test_missing_cases_root_is_reported(self):
        boards, skipped = realboard.discover_cases(
            pathlib.Path(tempfile.gettempdir()) / "definitely-missing-cases-root"
        )
        self.assertEqual(boards, [])
        self.assertTrue(skipped)
        self.assertIn("not found", skipped[0]["reason"])


class KeepoutParsingTests(unittest.TestCase):
    def _setup_case(self, tmp, plan_payload=None, plan_name="placement-plan-final.json"):
        evidence = pathlib.Path(tmp) / "case-2026-01-01" / "evidence"
        evidence.mkdir(parents=True)
        dump_path = evidence / "pcb-dump-final.json"
        dump_path.write_text(json.dumps(synthetic_dump()), encoding="utf-8")
        if plan_payload is not None:
            (evidence / plan_name).write_text(json.dumps(plan_payload), encoding="utf-8")
        return dump_path

    def test_plan_keepouts_are_applied(self):
        plan = {
            "project": "synthetic",
            "keepouts": [
                {"id": "MH-1", "center": [900, 150], "radius": 50, "source": "M3 washer"},
                {"id": "MH-2", "center": [300, 150], "radius": 50, "source": "M3 washer"},
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            dump_path = self._setup_case(tmp, plan)
            converted = realboard.load_and_convert(dump_path, name="keepout-board")
            report = converted.report
            self.assertEqual(report["keepouts"]["status"], "APPLIED")
            self.assertEqual(report["keepouts"]["count"], 2)
            self.assertEqual(len(converted.scenario.keepouts), 2)
            self.assertTrue(report["keepouts"]["source"].endswith("placement-plan-final.json"))
            self.assertEqual(report["original_violations"], [])
            self.assertEqual(report["keepouts"].get("conflicts_with_original"), None)

    def test_missing_plan_is_not_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            dump_path = self._setup_case(tmp)
            converted = realboard.load_and_convert(dump_path, name="no-plan")
            self.assertEqual(converted.report["keepouts"]["status"], "NOT RUN")
            self.assertEqual(converted.scenario.keepouts, [])
            self.assertIn("no parseable placement-plan", converted.report["keepouts"]["reason"])

    def test_unparseable_keepouts_are_not_run(self):
        plan = {"keepouts": [{"garbage": True}, {"center": "nope"}]}
        with tempfile.TemporaryDirectory() as tmp:
            dump_path = self._setup_case(tmp, plan)
            converted = realboard.load_and_convert(dump_path, name="bad-plan")
            self.assertEqual(converted.report["keepouts"]["status"], "NOT RUN")
            self.assertEqual(converted.report["keepouts"]["count"], 0)
            self.assertEqual(converted.scenario.keepouts, [])

    def test_plan_preference_final_over_plain(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = {"keepouts": [{"id": "MH", "center": [900, 150], "radius": 40}]}
            dump_path = self._setup_case(tmp, plan)
            evidence = dump_path.parent
            (evidence / "placement-plan.json").write_text(
                json.dumps({"keepouts": []}), encoding="utf-8"
            )
            found_path, found_payload = realboard.find_keepout_plan(dump_path)
            self.assertEqual(found_path.name, "placement-plan-final.json")
            self.assertEqual(len(found_payload["keepouts"]), 1)


class EdgeOverhangTests(unittest.TestCase):
    def _overhang_payload(self):
        payload = synthetic_dump()
        for comp in payload["components"]:
            if comp.get("designator") == "J1":
                comp["bbox"] = _bbox(40, -40, 160, 200)  # 40 mil = 1.016 mm below the board
                comp["y"] = 80
        return payload

    def test_small_overhang_is_kept_and_board_expands(self):
        converted = realboard.convert_dump(self._overhang_payload(), name="overhang")
        report = converted.report
        self.assertIn("J1", converted.scenario.components)
        self.assertAlmostEqual(report["board_expansion_mm"]["bottom"], 40 * MIL, places=4)
        self.assertGreater(report["board_expansion_mm"]["total_mm"], 0.0)
        self.assertEqual(report["edge_overhang_components"][0]["ref"], "J1")
        self.assertEqual(report["original_violations"], [])
        self.assertTrue(report["original_feasible_tolerant"])
        self.assertEqual(converted.scenario.board_h, round(800 * MIL + 40 * MIL, 6))
        self.assertTrue(converted.scenario.components["J1"].fixed)

    def test_large_overhang_is_dropped(self):
        payload = synthetic_dump()
        for comp in payload["components"]:
            if comp.get("designator") == "J1":
                comp["bbox"] = _bbox(40, -300, 160, 200)  # 300 mil = 7.6 mm
        converted = realboard.convert_dump(payload, name="big-overhang")
        self.assertNotIn("J1", converted.scenario.components)
        reasons = {item["ref"]: item["reason"] for item in converted.report["dropped_components"]}
        self.assertTrue(reasons["J1"].startswith("out_of_board"))


class PolygonConversionTests(unittest.TestCase):
    def test_rectangular_outline_is_polygon_ok(self):
        converted = realboard.convert_dump(synthetic_dump(), name="poly-rect")
        polygon = converted.report["polygon"]
        self.assertEqual(polygon["points"], 4)
        self.assertTrue(converted.report["polygon_ok"])
        self.assertEqual(polygon["components_outside"], [])
        self.assertAlmostEqual(polygon["area_ratio"], 1.0, places=6)

    def test_component_in_outline_notch_is_flagged(self):
        payload = synthetic_dump()
        payload["outline"]["points"] = [
            [0, 0], [1200, 0], [1200, 800], [700, 800], [700, 500], [0, 500],
        ]
        payload["outline"]["bbox"] = _bbox(0, 0, 1200, 800)
        for comp in payload["components"]:
            if comp.get("designator") == "C1":
                # top-left notch (x < 700, y > 500) is outside the L-shaped outline
                comp["bbox"] = _bbox(112.6, 627.35, 187.4, 672.65)
                comp["x"], comp["y"] = 150, 650
                for pad in comp["pads"]:
                    pad["x"], pad["y"] = 133.5, 650
        converted = realboard.convert_dump(payload, name="poly-notch")
        polygon = converted.report["polygon"]
        self.assertEqual(polygon["points"], 6)
        self.assertFalse(converted.report["polygon_ok"])
        outside = {item["ref"]: item for item in polygon["components_outside"]}
        self.assertIn("C1", outside)
        self.assertFalse(outside["C1"]["allowed"])
        self.assertGreater(outside["C1"]["max_outside_mm"], 2.0)
        self.assertIn("C1", [item["ref"] for item in polygon["violations"]])


# --------------------------------------------------------------------------- #
# v2 run_all / CLI
# --------------------------------------------------------------------------- #
class RunAllV2Tests(unittest.TestCase):
    def test_run_all_v2_explicit_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            dump_path = _write_dump(tmp)
            report = realboard.run_all_v2(
                sources=[("synthetic", dump_path)], steps=0, max_routes=1
            )
            self.assertEqual(report["schema"], realboard.REALBOARD_SCHEMA_V2)
            self.assertEqual(report["discovery"]["mode"], "explicit_sources")
            self.assertEqual(report["aggregate"]["n_boards"], 1)
            self.assertGreaterEqual(report["aggregate"]["n_polygon_ok"], 1)
            self.assertTrue(report["aggregate"]["all_feasible_original_tolerant"])
            board = report["boards"][0]
            self.assertIn("polygon", board["conversion"])
            self.assertIn("keepouts", board["conversion"])
            self.assertEqual(board["conversion"]["keepouts"]["status"], "NOT RUN")
            out_dir = pathlib.Path(tmp) / "out"
            paths = realboard.write_reports_v2(report, out_dir=out_dir)
            self.assertTrue(paths["markdown"].exists())
            self.assertTrue(paths["json"].exists())
            loaded = json.loads(paths["json"].read_text(encoding="utf-8"))
            self.assertEqual(loaded["schema"], realboard.REALBOARD_SCHEMA_V2)
            markdown = paths["markdown"].read_text(encoding="utf-8")
            self.assertIn("# P4.6", markdown)
            self.assertIn("多边形", markdown)

    def test_cli_v2_flag_writes_v2_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            dump_path = _write_dump(tmp)
            out_dir = pathlib.Path(tmp) / "out"
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "mp_place.realboard",
                    "--v2",
                    "--source",
                    f"synthetic={dump_path}",
                    "--steps",
                    "0",
                    "--max-routes",
                    "1",
                    "--out",
                    str(out_dir),
                    "--json",
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=300,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr[-3000:])
            report = json.loads(proc.stdout)
            self.assertEqual(report["schema"], realboard.REALBOARD_SCHEMA_V2)
            self.assertTrue((out_dir / realboard.REPORT_MD_V2).exists())
            self.assertTrue((out_dir / realboard.REPORT_JSON_V2).exists())
            self.assertFalse((out_dir / realboard.REPORT_MD).exists())


# --------------------------------------------------------------------------- #
# real dumps v2 smoke (read-only, optional)
# --------------------------------------------------------------------------- #
_CASES_ROOT_AVAILABLE = realboard.DEFAULT_CASES_ROOT.is_dir()


@unittest.skipUnless(_CASES_ROOT_AVAILABLE, "EasyCirq cases root is not available on this machine")
class RealBoardV2SmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.boards, cls.skipped = realboard.discover_cases()

    def test_discovery_finds_more_cases(self):
        names = {source.name for source in self.boards}
        self.assertGreaterEqual(len(self.boards), 4)
        for expected in ("mcu-i2c", "photo-led", "dual-button", "temp-alarm"):
            self.assertIn(expected, names)
        self.assertTrue(
            any(item.get("case") == "feedback-r12" for item in self.skipped),
            self.skipped,
        )

    def test_all_discovered_boards_convert(self):
        for source in self.boards:
            with self.subTest(board=source.name):
                converted = realboard.load_and_convert(source.path, name=source.name)
                report = converted.report
                self.assertEqual(report["components_kept"], report["components_total"])
                self.assertGreater(report["polygon"]["points"], 0)
                self.assertIn(report["polygon"]["validation"], ("ray casting; boundary counts as inside",))
                self.assertIsNotNone(report["polygon_ok"])
                self.assertTrue(report["original_feasible_tolerant"])
                self.assertIn(report["keepouts"]["status"], ("APPLIED", "NOT RUN"))
                self.assertGreaterEqual(converted.scenario.board_w, 10.0)
                self.assertLessEqual(converted.scenario.board_w, 250.0)
                for ref, comp in converted.scenario.components.items():
                    if ref.upper().startswith(realboard.FIXED_PREFIXES):
                        self.assertTrue(comp.fixed, ref)

    def test_keepouts_follow_evidence(self):
        by_name = {source.name: source for source in self.boards}
        for name, expected in (("mcu-i2c", "APPLIED"), ("photo-led", "APPLIED"), ("temp-alarm", "NOT RUN")):
            if name not in by_name:
                continue
            converted = realboard.load_and_convert(by_name[name].path, name=name)
            self.assertEqual(converted.report["keepouts"]["status"], expected, name)
            if expected == "APPLIED":
                self.assertGreater(converted.report["keepouts"]["count"], 0)
                self.assertEqual(len(converted.scenario.keepouts), converted.report["keepouts"]["count"])

    def test_real_v2_run_board_smoke(self):
        source = self.boards[0]
        converted = realboard.load_and_convert(source.path, name=source.name)
        row = realboard.run_board(converted, steps=0, seed=0, max_routes=1)
        self.assertEqual(row["name"], source.name)
        self.assertIn("feasible_tolerant", row["original"])
        self.assertTrue(row["optimized"]["feasible"])
        self.assertTrue(row["repair"]["feasible"])
        json.dumps(realboard._json_safe(row), ensure_ascii=False)


# --------------------------------------------------------------------------- #
# v3: full-case discovery, mechanical constraints, board-level suite
# --------------------------------------------------------------------------- #
def _synthetic_with_antenna():
    payload = synthetic_dump()
    payload["components"].append(
        {
            "designator": "ANT1",
            "device": "chip-antenna",
            "x": 1100,
            "y": 700,
            "rotation": 0,
            "bbox": _bbox(1050, 650, 1150, 750),
            "pads": [
                _pad("1", "VIN", 1100, 700),
                _pad("2", "GND", 1100, 725),
            ],
        }
    )
    return payload


class MechanicalFixedTests(unittest.TestCase):
    def test_prefixes_include_connector_switch_antenna(self):
        for prefix in ("J", "SW", "ANT"):
            self.assertIn(prefix, realboard.MECHANICAL_PREFIXES)
        roles = dict(realboard.MECHANICAL_ROLES)
        self.assertEqual(roles["J"], "connector")
        self.assertEqual(roles["SW"], "switch")
        self.assertEqual(roles["ANT"], "antenna")

    def test_j_sw_mechanical_list(self):
        converted = realboard.convert_dump(synthetic_dump(), name="mech")
        mechanical = {item["ref"]: item for item in converted.report["mechanical_fixed"]}
        self.assertEqual(sorted(mechanical), ["J1", "SW1"])
        self.assertEqual(mechanical["J1"]["role"], "connector")
        self.assertEqual(mechanical["SW1"]["role"], "switch")
        self.assertEqual(converted.report["mechanical_fixed_count"], 2)
        self.assertEqual(converted.report["fixed_mode"], "j_sw_prefix")
        for ref in ("J1", "SW1"):
            self.assertTrue(converted.scenario.components[ref].fixed)
            self.assertIn(ref, converted.scenario.base_placement)

    def test_antenna_is_fixed(self):
        converted = realboard.convert_dump(_synthetic_with_antenna(), name="antenna")
        report = converted.report
        self.assertIn("ANT1", report["fixed_refs"])
        self.assertEqual(report["fixed_mode"], "mechanical_prefix")
        self.assertTrue(converted.scenario.components["ANT1"].fixed)
        self.assertEqual(converted.scenario.components["ANT1"].kind, "antenna")
        mechanical = {item["ref"]: item for item in report["mechanical_fixed"]}
        self.assertEqual(mechanical["ANT1"]["role"], "antenna")
        self.assertEqual(mechanical["ANT1"]["prefix"], "ANT")
        self.assertEqual(report["mechanical_fixed_count"], 3)
        self.assertEqual(report["original_conflicts"], [])

    def test_original_conflicts_are_reported_not_fatal(self):
        payload = synthetic_dump()
        # Move D2 into a degenerate bbox? Use a small overlap between J1 and SW1:
        for comp in payload["components"]:
            if comp.get("designator") == "SW1":
                comp["bbox"] = _bbox(40, 300, 160, 500)  # same area as J1 -> body overlap
                comp["x"], comp["y"] = 100, 400
        converted = realboard.convert_dump(payload, name="conflict")
        report = converted.report
        self.assertFalse(report["original_feasible"])
        self.assertTrue(report["original_conflicts"])
        kinds = {item["kind"] for item in report["original_conflicts"]}
        self.assertIn("hard_violation", kinds)
        # The conversion still succeeds and the conflicts carry explicit tolerance flags.
        for item in report["original_conflicts"]:
            self.assertIn("tolerated", item)


class DiscoveryDetailedTests(unittest.TestCase):
    def _case(self, root, case_name):
        evidence = pathlib.Path(root) / case_name / "evidence"
        evidence.mkdir(parents=True)
        return evidence

    def test_case_reports_record_selection_and_skip_reasons(self):
        with tempfile.TemporaryDirectory() as tmp:
            evidence = self._case(tmp, "alpha-board-2026-01-01")
            payload = synthetic_dump()
            (evidence / "pcb-dump-after-reload.json").write_text(
                json.dumps(payload), encoding="utf-8"
            )
            (evidence / "pcb-dump-final.json").write_text(json.dumps(payload), encoding="utf-8")
            beta = pathlib.Path(tmp) / "beta-case-2026-01-02"
            beta.mkdir(parents=True)
            (beta / "notes.json").write_text(json.dumps({"note": "no dump"}), encoding="utf-8")
            boards, skipped, case_reports = realboard.discover_cases(tmp, detailed=True)
            self.assertEqual(len(boards), 1)
            self.assertEqual(len(case_reports), 2)
            by_case = {item["case"]: item for item in case_reports}
            alpha = by_case["alpha-board-2026-01-01"]
            self.assertEqual(alpha["status"], "BOARD")
            self.assertTrue(alpha["chosen"].endswith("pcb-dump-final.json"))
            self.assertEqual(len(alpha["candidates"]), 2)
            self.assertEqual(sum(1 for item in alpha["candidates"] if item["selected"]), 1)
            selected = next(item for item in alpha["candidates"] if item["selected"])
            self.assertEqual(selected["file"], alpha["chosen"])
            self.assertEqual(selected["rank_label"], "preferred_final")
            beta_report = by_case["beta-case-2026-01-02"]
            self.assertEqual(beta_report["status"], "SKIPPED")
            self.assertIn("no dump-like JSON", beta_report["reason"])
            self.assertEqual(beta_report["json_files"], 1)
            self.assertEqual(beta_report["candidates"], [])

    def test_missing_root_reports_skip(self):
        with tempfile.TemporaryDirectory() as tmp:
            boards, skipped, case_reports = realboard.discover_cases(
                pathlib.Path(tmp) / "does-not-exist", detailed=True
            )
            self.assertEqual(boards, [])
            self.assertTrue(skipped)
            self.assertEqual(case_reports[0]["status"], "SKIPPED")
            self.assertIn("not found", case_reports[0]["reason"])


class ReportV3StructureTests(unittest.TestCase):
    def test_run_all_v3_report_structure(self):
        with tempfile.TemporaryDirectory() as tmp:
            dump_path = _write_dump(tmp)
            report = realboard.run_all_v3(
                sources=[("synthetic", dump_path)], steps=0, max_routes=1
            )
            self.assertEqual(report["schema"], realboard.REALBOARD_SCHEMA_V3)
            discovery = report["discovery"]
            self.assertEqual(discovery["mode"], "explicit_sources")
            self.assertEqual(len(discovery["case_reports"]), 1)
            self.assertEqual(discovery["case_reports"][0]["status"], "BOARD")
            suite = report["suite"]
            self.assertEqual(suite["n_boards"], 1)
            for key in (
                "mean_completion",
                "mean_truth_v2",
                "mean_completion_gain",
                "mean_truth_reduction_pct",
                "all_feasible",
                "best_board",
                "worst_board",
                "ranking",
            ):
                self.assertIn(key, suite)
            self.assertEqual(suite["best_board"]["name"], "synthetic")
            self.assertEqual(suite["worst_board"]["name"], "synthetic")
            self.assertTrue(suite["all_feasible"]["optimized"])
            board = report["boards"][0]
            for key in (
                "case",
                "source_sha256",
                "conversion",
                "mechanical_fixed",
                "original_conflicts",
                "timings_s",
                "candidates",
                "selection_reason",
            ):
                self.assertIn(key, board)
            conversion = board["conversion"]
            for key in (
                "polygon",
                "keepouts",
                "units",
                "dropped_components",
                "mechanical_fixed",
                "original_conflicts",
                "original_feasible_tolerant",
            ):
                self.assertIn(key, conversion)
            self.assertGreaterEqual(conversion["polygon"]["points"], 4)
            self.assertIn("original", board["timings_s"])
            self.assertIn("optimized", board["timings_s"])
            self.assertIn("repair", board["timings_s"])
            out_dir = pathlib.Path(tmp) / "out"
            paths = realboard.write_reports_v3(report, out_dir=out_dir)
            self.assertTrue(paths["markdown"].exists())
            self.assertTrue(paths["json"].exists())
            loaded = json.loads(paths["json"].read_text(encoding="utf-8"))
            self.assertEqual(loaded["schema"], realboard.REALBOARD_SCHEMA_V3)
            markdown = paths["markdown"].read_text(encoding="utf-8")
            for token in (
                "# P4.7",
                "case → dump 选择",
                "真实板 suite 汇总",
                "最好板 / 最差板",
                "机械固定",
                "原布局冲突",
            ):
                self.assertIn(token, markdown)

    def test_case_selection_and_skip_in_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp) / "cases"
            evidence = root / "good-board-2026-01-01" / "evidence"
            evidence.mkdir(parents=True)
            (evidence / "pcb-dump-final.json").write_text(
                json.dumps(synthetic_dump()), encoding="utf-8"
            )
            empty = root / "empty-case-2026-01-02"
            empty.mkdir(parents=True)
            (empty / "notes.json").write_text("{}", encoding="utf-8")
            report = realboard.run_all_v3(cases_root=root, steps=0, max_routes=1)
            self.assertEqual(report["schema"], realboard.REALBOARD_SCHEMA_V3)
            self.assertEqual(len(report["boards"]), 1)
            self.assertEqual(report["discovery"]["mode"], "auto_discovery")
            statuses = {item["case"]: item["status"] for item in report["discovery"]["case_reports"]}
            self.assertEqual(statuses["good-board-2026-01-01"], "BOARD")
            self.assertEqual(statuses["empty-case-2026-01-02"], "SKIPPED")
            skipped = {item["case"]: item["reason"] for item in report["skipped_cases"]}
            self.assertIn("empty-case-2026-01-02", skipped)

    def test_conversion_failure_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp) / "cases"
            good = root / "good-2026-01-01" / "evidence"
            good.mkdir(parents=True)
            (good / "pcb-dump-final.json").write_text(
                json.dumps(synthetic_dump()), encoding="utf-8"
            )
            bad = root / "bad-2026-01-02" / "evidence"
            bad.mkdir(parents=True)
            bad_payload = synthetic_dump()
            bad_payload["outline"]["bbox"] = _bbox(0, 0, 100, 80)
            bad_payload["outline"]["points"] = [[0, 0], [100, 0], [100, 80], [0, 80]]
            (bad / "pcb-dump-final.json").write_text(
                json.dumps(bad_payload), encoding="utf-8"
            )
            report = realboard.run_all_v3(cases_root=root, steps=0, max_routes=1)
            self.assertEqual(len(report["boards"]), 1)
            skipped = {item["case"]: item["reason"] for item in report["skipped_cases"]}
            self.assertIn("bad-2026-01-02", skipped)
            self.assertIn("conversion failed", skipped["bad-2026-01-02"])

    def test_v3_report_is_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            dump_path = _write_dump(tmp)
            first = realboard.run_all_v3(
                sources=[("synthetic", dump_path)], steps=0, max_routes=1
            )
            second = realboard.run_all_v3(
                sources=[("synthetic", dump_path)], steps=0, max_routes=1
            )
            self.assertEqual(
                json.dumps(realboard.strip_volatile_report(first), sort_keys=True),
                json.dumps(realboard.strip_volatile_report(second), sort_keys=True),
            )
            # volatile fields are present in the raw report but stripped for comparison
            self.assertIn("generated_at", first)
            self.assertNotIn("generated_at", realboard.strip_volatile_report(first))
            self.assertIn("timings_s", first["boards"][0])
            self.assertNotIn("timings_s", realboard.strip_volatile_report(first)["boards"][0])


class CliV3Tests(unittest.TestCase):
    def _run(self, *args):
        return subprocess.run(
            [sys.executable, "-m", "mp_place.realboard", *args],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=300,
        )

    def test_cli_default_v3(self):
        with tempfile.TemporaryDirectory() as tmp:
            dump_path = _write_dump(tmp)
            out_dir = pathlib.Path(tmp) / "out"
            proc = self._run(
                "--source",
                f"synthetic={dump_path}",
                "--steps",
                "0",
                "--max-routes",
                "1",
                "--out",
                str(out_dir),
                "--json",
            )
            self.assertEqual(proc.returncode, 0, proc.stderr[-3000:])
            report = json.loads(proc.stdout)
            self.assertEqual(report["schema"], realboard.REALBOARD_SCHEMA_V3)
            self.assertTrue((out_dir / realboard.REPORT_MD_V3).exists())
            self.assertTrue((out_dir / realboard.REPORT_JSON_V3).exists())
            self.assertFalse((out_dir / realboard.REPORT_MD_V2).exists())
            self.assertFalse((out_dir / realboard.REPORT_MD).exists())

    def test_cli_v1_v2_are_mutually_exclusive(self):
        proc = self._run("--v1", "--v2")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("mutually exclusive", proc.stderr)


# --------------------------------------------------------------------------- #
# real dumps v3 smoke (read-only, optional)
# --------------------------------------------------------------------------- #
@unittest.skipUnless(_CASES_ROOT_AVAILABLE, "EasyCirq cases root is not available on this machine")
class RealBoardV3SmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.boards, cls.skipped, cls.case_reports = realboard.discover_cases(
            detailed=True
        )

    def test_detailed_discovery_records_choices(self):
        self.assertGreaterEqual(len(self.boards), 4)
        statuses = {item["case"]: item["status"] for item in self.case_reports}
        self.assertEqual(statuses.get("feedback-r12"), "SKIPPED")
        for source in self.boards:
            self.assertTrue(source.candidates)
            self.assertEqual(sum(1 for item in source.candidates if item["selected"]), 1)
            self.assertTrue(source.selection_reason)
        report = next(item for item in self.case_reports if item["status"] == "BOARD")
        self.assertTrue(report["chosen"])
        self.assertIn("candidates", report)

    def test_real_boards_have_mechanical_parts(self):
        for source in self.boards:
            with self.subTest(board=source.name):
                converted = realboard.load_and_convert(source.path, name=source.name)
                report = converted.report
                self.assertGreater(report["mechanical_fixed_count"], 0)
                for item in report["mechanical_fixed"]:
                    self.assertTrue(item["ref"].upper().startswith(realboard.MECHANICAL_PREFIXES))
                    self.assertIn(item["role"], {"connector", "switch", "antenna"})
                    self.assertTrue(converted.scenario.components[item["ref"]].fixed)
                self.assertGreater(report["polygon"]["points"], 0)
                self.assertIn(report["keepouts"]["status"], ("APPLIED", "NOT RUN"))
                self.assertIsInstance(report["original_conflicts"], list)

    def test_real_v3_run_board_timings(self):
        source = self.boards[0]
        converted = realboard.load_and_convert(source.path, name=source.name)
        row = realboard.run_board(converted, steps=0, seed=0, max_routes=1)
        self.assertIn("timings_s", row)
        self.assertIn("original", row["timings_s"])
        self.assertIn("optimized", row["timings_s"])
        self.assertIn("repair", row["timings_s"])
        self.assertGreaterEqual(row["timings_s"]["original"], 0.0)
        self.assertTrue(row["mechanical_fixed"])
        self.assertIsInstance(row["original_conflicts"], list)
        json.dumps(realboard._json_safe(row), ensure_ascii=False)


if __name__ == "__main__":
    unittest.main()
