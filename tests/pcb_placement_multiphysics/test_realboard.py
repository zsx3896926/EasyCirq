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
        self.assertEqual(reasons["D1"], "out_of_board")
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


if __name__ == "__main__":
    unittest.main()
