"""Regression tests for the read-only ``.epru`` (EasyEDA Pro native backup) adapter.

These tests build a tiny but structurally faithful ``.epru`` stream in memory, so
they run in CI without any user project data.  The real 4-layer board replay is
an operational step on a user-supplied backup (see
``benchmarks/return-path-audit/replay_epru.py`` and the incoming directory
instructions); this file only guards the parser/projection contract.
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

try:  # package-mode discovery (unittest discover -s tests)
    from . import support
except ImportError:  # directory-mode discovery (-s tests/return_path_audit)
    import support

ROOT = pathlib.Path(__file__).resolve().parents[2]
ADAPTER = ROOT / "benchmarks/return-path-audit/replay_epru.py"

BOARD = [0, 0, "L", 1000, 0, 1000, 800, 0, 800, 0, 0]


def _layer(canonical, kind, name, use=True):
    header = {"type": "LAYER", "ticket": canonical,
              "id": json.dumps(["LAYER", canonical])}
    payload = {"layerType": kind, "layerName": name, "use": use}
    return [header, payload]


def epru_records(fill_scale=10.0, zero_length=False):
    """Build a minimal 4-layer PCB document with a real-shaped fill."""
    records = [{"docType": "PCB", "uuid": "doc-epru-1", "updateTime": 1793000000000}]
    records += _layer(1, "TOP", "Top Layer")
    records += _layer(2, "BOTTOM", "Bottom Layer")
    records += _layer(11, "OUTLINE", "Board Outline Layer")
    records += _layer(15, "SIGNAL", "Inner1")
    records += _layer(16, "SIGNAL", "Inner2")
    records += [{"type": "POLY", "ticket": 10, "id": "outline-1"},
                {"layerId": 11, "path": [BOARD]}]
    records += [{"type": "POUR", "ticket": 20, "id": "pour-1"},
                {"layerId": 15, "netName": "GND", "width": 0.2,
                 "path": [BOARD]}]
    factor = fill_scale
    fill = [0, 0, "L", 1000 / factor, 0, 1000 / factor, 800 / factor,
            0, 800 / factor, 0, 0]
    records += [{"type": "POURED", "ticket": 21,
                 "id": json.dumps(["POURED", "pour-1"]), "firstTicket": 20},
                {"pourFill": [{"fill": True, "strokeWidth": 0, "path": [fill]}]}]
    records += [{"type": "LINE", "ticket": 30, "id": "line-1"},
                {"layerId": 1, "netName": "SIG", "startX": 200, "startY": 400,
                 "endX": 800, "endY": 400, "width": 10}]
    if zero_length:
        records += [{"type": "LINE", "ticket": 31, "id": "line-2"},
                    {"layerId": 1, "netName": "SIG", "startX": 300,
                     "startY": 500, "endX": 300, "endY": 500, "width": 10}]
    records += [{"type": "VIA", "ticket": 40, "id": "via-1"},
                {"netName": "SIG", "centerX": 200, "centerY": 400,
                 "viaDiameter": 24.0199, "holeDiameter": 12.01,
                 "viaType": "NORMAL"}]
    return records


def write_epru(directory, records):
    path = pathlib.Path(directory) / "board.epru"
    path.write_text("||".join(json.dumps(record) for record in records),
                    encoding="utf-8")
    return path


class EpruAdapterTests(unittest.TestCase):
    def project(self, **kwargs):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        epru = write_epru(tmp.name, epru_records(**kwargs))
        out = pathlib.Path(tmp.name) / "input.json"
        completed = subprocess.run(
            [sys.executable, str(ADAPTER), "--input", str(epru),
             "--out", str(out)],
            cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        stats = json.loads(completed.stdout)
        return json.loads(out.read_text(encoding="utf-8")), stats, tmp.name

    def audit(self, input_path):
        report_path = pathlib.Path(input_path).parent / "report.json"
        code, stdout, stderr = support.run_cli(
            ["audit", "-i", str(input_path), "-o", str(report_path)])
        report = json.loads(report_path.read_text(encoding="utf-8"))
        return code, report, stderr

    def test_four_layer_projection_and_plane_roles(self):
        document, stats, tmp = self.project()
        self.assertEqual(stats["copper_layers"], 4)
        self.assertEqual(stats["layer_order"], ["L1", "L2", "L3", "L4"])
        self.assertEqual(stats["plane_layers"], {"L2": "GND"})
        self.assertEqual([layer["role"] for layer in document["stackup"]["layers"]],
                         ["signal", "plane", "signal", "signal"])
        self.assertTrue(document["reference_copper"][0]["is_actual_fill"])
        self.assertEqual(document["reference_copper"][0]["layer"], "L2")
        self.assertEqual(document["source"]["kind"], "offline_export")
        self.assertIn("READ-ONLY", document["source"]["producer"])
        # the 1/10 fill serialisation is detected and normalised
        self.assertIn("x10", document["reference_copper"][0]["source"])
        code, report, stderr = self.audit(pathlib.Path(tmp) / "input.json")
        self.assertEqual(code, 0, stderr)
        self.assertEqual(report["overall_status"], "pass_with_scope")
        self.assertAlmostEqual(report["coverage"]["totals"]["checked_length"],
                               600.0, places=6)

    def test_fill_scale_one_is_also_supported(self):
        document, stats, tmp = self.project(fill_scale=1.0)
        self.assertIn("x1", document["reference_copper"][0]["source"])
        code, report, stderr = self.audit(pathlib.Path(tmp) / "input.json")
        self.assertEqual(code, 0, stderr)
        self.assertEqual(report["overall_status"], "pass_with_scope")

    def test_unrecognised_fill_scale_stays_unproven(self):
        document, stats, tmp = self.project(fill_scale=3.0)
        copper = document["reference_copper"][0]
        self.assertEqual(copper["availability"], "pour_boundary")
        self.assertFalse(copper["is_actual_fill"])
        code, report, stderr = self.audit(pathlib.Path(tmp) / "input.json")
        self.assertEqual(code, 3, stderr)
        self.assertEqual(report["overall_status"], "incomplete")
        self.assertEqual(report["coverage"]["totals"]["checked_length"], 0.0)
        self.assertIn("RP-E2-208", support.unknown_ids(report))

    def test_zero_length_track_is_declared_not_silently_dropped(self):
        document, stats, tmp = self.project(zero_length=True)
        self.assertTrue(any(item.get("kind") == "zero_length_track"
                            for item in document["unsupported"]))
        code, report, stderr = self.audit(pathlib.Path(tmp) / "input.json")
        self.assertEqual(code, 3, stderr)
        self.assertIn("RP-E5-502", support.unknown_ids(report))
        self.assertGreater(report["coverage"]["totals"]["checked_length"], 0)


if __name__ == "__main__":
    unittest.main()
