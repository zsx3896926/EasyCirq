"""Real-snapshot replay regression (REAL EasyEDA dump, 2-layer board).

This test proves the auditor consumes a genuine EDA read-back snapshot, not only
hand-written scenes.  The committed dump is a real 2-layer board; there is no
real 4-layer snapshot in this repository, so this test must never be presented
as 4-layer validation.

It runs the real projection adapter + the real CLI as subprocesses.
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
DUMP = ROOT / "easycirq/cases/mcu-i2c-s3-2026-10-26/evidence/pcb-dump-final.json"
ADAPTER = ROOT / "benchmarks/return-path-audit/replay_real_dump.py"


class RealDumpReplayTests(unittest.TestCase):
    def setUp(self):
        if not DUMP.is_file():
            self.skipTest("real board dump not present: %s" % DUMP)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.input_path = pathlib.Path(self.tmp.name) / "real.input.json"
        completed = subprocess.run(
            [sys.executable, str(ADAPTER), "--dump", str(DUMP),
             "--signal-layer", "1", "--reference-layer", "2", "--units", "mil",
             "--corridor", "8", "--out", str(self.input_path)],
            cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.stats = json.loads(completed.stdout)
        self.input = json.loads(self.input_path.read_text(encoding="utf-8"))
        self.report_path = pathlib.Path(self.tmp.name) / "real.report.json"
        code, stdout, stderr = support.run_cli(
            ["audit", "-i", str(self.input_path), "-o", str(self.report_path)])
        self.exit_code = code
        self.stdout = stdout
        self.stderr = stderr
        self.report = json.loads(self.report_path.read_text(encoding="utf-8"))

    def test_projection_comes_from_a_real_two_layer_snapshot(self):
        self.assertEqual(self.input["source"]["kind"], "offline_export")
        self.assertIn("REAL snapshot", self.input["source"]["producer"])
        self.assertEqual(len(self.input["stackup"]["layers"]), 2)
        self.assertEqual(self.stats["copper_layers"], 2)
        self.assertEqual(self.input["units"], "mil")
        self.assertEqual(self.input["source"]["raw_input_sha256"],
                         self.stats["raw_input_sha256"])
        self.assertGreater(self.stats["raw_input_sha256"], "")
        # reference copper is the actual filled GND pour
        self.assertTrue(self.input["reference_copper"])
        self.assertTrue(self.input["reference_copper"][0]["is_actual_fill"])

    def test_only_signal_layer_tracks_are_modelled(self):
        layers = {segment["layer"] for signal in self.input["signals"]
                  for segment in signal["segments"]}
        self.assertEqual(layers, {"L1"})
        self.assertGreater(self.stats["excluded_lines_by_layer"].get("2", 0), 0)
        self.assertGreater(len(self.input["signals"]), 5)
        self.assertGreater(sum(len(signal["segments"]) for signal in self.input["signals"]), 100)

    def test_real_board_produces_concrete_reference_defects(self):
        self.assertEqual(self.exit_code, 1, self.stderr)
        self.assertEqual(self.report["overall_status"], "fail")
        totals = self.report["coverage"]["totals"]
        self.assertEqual(totals["unit"], "mil")
        self.assertGreater(totals["checked_length"], 1000)
        rules = [item["rule_id"] for item in self.report["findings"]]
        # Real GND-pour voids under top-layer traces and reference-edge endings.
        self.assertGreaterEqual(rules.count("RP-E2-202"), 1)
        self.assertGreaterEqual(rules.count("RP-E2-204"), 1)
        self.assertGreaterEqual(rules.count("RP-E2-206"), 1)
        for finding in self.report["findings"]:
            interval = finding["interval"]
            if interval is None:
                continue
            for point in (interval["start"], interval["end"]):
                self.assertTrue(all(isinstance(value, (int, float)) for value in point))
            self.assertGreater(interval["length"], 0)
            self.assertEqual(finding["unit"], "mil")

    def test_report_never_claims_four_layer_or_si_pass(self):
        self.assertEqual(self.report["run"]["real_eda"], "NOT RUN")
        self.assertTrue(self.report["run"]["simulated"])
        self.assertIn("NOT", self.report["scope"]["statement"])
        joined = json.dumps(self.report, ensure_ascii=False)
        self.assertNotIn("recovered_return_path\": true", joined)


if __name__ == "__main__":
    unittest.main()
