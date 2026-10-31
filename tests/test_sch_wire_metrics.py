import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "easycirq" / "scripts"
TOOL = SCRIPTS / "sch_wire_metrics.py"

sys.path.insert(0, str(SCRIPTS))
import sch_wire_metrics as tool  # noqa: E402


def layout(wires, frames=None, components=None):
    return {"coordinate_units": "raw", "page_bbox": [0, 0, 1170, 825],
            "wires": wires, "module_frames": frames or [],
            "components": components or []}


class WireMetrics(unittest.TestCase):
    def test_lengths_and_short_lead_ratio(self):
        # 10 units = 2.54 mm; 100 units = 25.4 mm
        report = tool.analyze(layout([
            {"id": "a", "points": [[0, 0], [10, 0]]},
            {"id": "b", "points": [[0, 0], [100, 0]]},
            {"id": "c", "points": [[0, 0], [10, 0], [10, 10]]},
        ]))
        self.assertEqual(report["metrics"]["longest_wire_mm"], 25.4)
        self.assertAlmostEqual(report["metrics"]["avg_wire_mm"], (2.54 + 25.4 + 5.08) / 3, 2)
        self.assertAlmostEqual(report["metrics"]["short_lead_ratio"], 2 / 3, 3)
        self.assertEqual(report["verdict"], "pass")

    def test_long_wire_is_warning_only(self):
        report = tool.analyze(layout([{"id": "a", "points": [[0, 0], [600, 0]]}]))
        self.assertEqual(report["metrics"]["longest_wire_mm"], 152.4)
        self.assertEqual(report["findings"][0]["code"], "long_wire")
        self.assertEqual(report["verdict"], "pass")

    def test_single_zone_reports_zero_deviation(self):
        report = tool.analyze(layout(
            [{"id": "a", "points": [[0, 0], [10, 0]]}],
            [{"id": "f1", "bbox": [0, 0, 100, 100], "contains": ["x", "y", "z"]}]))
        self.assertEqual(report["metrics"]["zones"], 1)
        self.assertEqual(report["metrics"]["zone_balance_deviation"], 0.0)

    def test_zone_balance_counts_parts_not_flags(self):
        # "contains" also lists flags/stubs; only components may be balanced
        report = tool.analyze({
            "wires": [{"id": "a", "points": [[0, 0], [10, 0]]}],
            "components": [{"id": "c1"}, {"id": "c2"}],
            "module_frames": [
                {"id": "z1", "contains": ["c1", "flag1", "stub1"]},
                {"id": "z2", "contains": ["c2"]}],
        })
        self.assertEqual(report["metrics"]["zone_balance_deviation"], 0.0)

    def test_multi_zone_deviation(self):
        report = tool.analyze(layout(
            [{"id": "a", "points": [[0, 0], [10, 0]]}],
            [{"id": "f1", "contains": ["a", "b", "c", "d"]},
             {"id": "f2", "contains": ["e"]}],
            components=[{"id": x} for x in "abcde"]))
        # (4 - 1) / 2.5 = 1.2
        self.assertAlmostEqual(report["metrics"]["zone_balance_deviation"], 1.2, 3)

    def test_cross_zone_wire_is_an_error(self):
        report = tool.analyze(layout(
            [{"id": "a", "points": [[0, 0], [300, 0]]}],
            [{"id": "z1", "bbox": [0, -50, 100, 50], "contains": ["x"]},
             {"id": "z2", "bbox": [200, -50, 400, 50], "contains": ["y"]}]))
        self.assertEqual(report["metrics"]["cross_zone_crossings"], 1)
        self.assertEqual(report["findings"][0]["code"], "cross_zone_crossing")
        self.assertEqual(report["findings"][0]["severity"], "error")

    def test_wire_to_open_sheet_is_not_a_crossing(self):
        # one end leaves the frame into open space: a label stub, not a crossing
        report = tool.analyze(layout(
            [{"id": "a", "points": [[0, 0], [300, 0]]}],
            [{"id": "z1", "bbox": [0, -50, 100, 50], "contains": ["x"]}]))
        self.assertEqual(report["metrics"]["cross_zone_crossings"], 0)
        self.assertEqual(report["findings"], [])

    def test_single_zone_has_no_crossings(self):
        report = tool.analyze(layout(
            [{"id": "a", "points": [[0, 0], [10, 0]]}],
            [{"id": "z1", "bbox": [-10, -10, 20, 20], "contains": ["x"]}]))
        self.assertEqual(report["metrics"]["cross_zone_crossings"], 0)

    def test_empty_wires_is_invalid(self):
        with self.assertRaises(ValueError):
            tool.analyze(layout([]))

    def test_cli(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "layout.json"
            out = Path(d) / "check.json"
            src.write_text(json.dumps(layout(
                [{"id": "a", "points": [[0, 0], [10, 0]]}])), encoding="utf-8")
            run = subprocess.run([sys.executable, str(TOOL), str(src),
                                  "--out", str(out), "--json"],
                                 capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(run.returncode, 0, run.stderr)
            report = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(report["schema"], tool.SCHEMA)
            self.assertEqual(report["metrics"]["wire_count"], 1)


if __name__ == "__main__":
    unittest.main()
