import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "easycirq" / "scripts"
TOOL = SCRIPTS / "sch_readability_metrics.py"

sys.path.insert(0, str(SCRIPTS))
import sch_readability_metrics as tool  # noqa: E402

IR = {"nets": [{"id": "n1", "name": "VBUS"}, {"id": "n2", "name": "SIG"},
               {"id": "n3", "name": "GND"}]}


class ReadabilityMetrics(unittest.TestCase):
    def test_all_labelled_gives_zero(self):
        report = tool.analyze(IR, {"net_flags": [{"net": "VBUS"}, {"net": "GND"}],
                                   "label_anchors": [{"net": "SIG"}]})
        self.assertEqual(report["metrics"]["direct_ratio"], 0.0)
        self.assertEqual(report["metrics"]["labelled_nets"], 3)

    def test_no_labels_gives_one(self):
        report = tool.analyze(IR, {"net_flags": [], "label_anchors": []})
        self.assertEqual(report["metrics"]["direct_ratio"], 1.0)

    def test_partial_labels(self):
        report = tool.analyze(IR, {"net_flags": [{"net": "GND"}]})
        self.assertAlmostEqual(report["metrics"]["direct_ratio"], 2 / 3, 3)

    def test_stale_label_is_flagged(self):
        report = tool.analyze(IR, {"net_flags": [{"net": "GHOST"}]})
        codes = {f["code"] for f in report["findings"]}
        self.assertIn("stale_label_net", codes)
        self.assertEqual(report["summary"]["stale_labelled"], 1)

    def test_empty_nets_is_invalid(self):
        with self.assertRaises(ValueError):
            tool.analyze({"nets": []}, {})

    def test_cli(self):
        with tempfile.TemporaryDirectory() as d:
            ir = Path(d) / "ir.json"
            layout = Path(d) / "layout.json"
            ir.write_text(json.dumps(IR), encoding="utf-8")
            layout.write_text(json.dumps({"net_flags": [{"net": "GND"}]}),
                              encoding="utf-8")
            run = subprocess.run([sys.executable, str(TOOL), "--ir", str(ir),
                                  "--layout", str(layout), "--json"],
                                 capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn("direct_ratio", json.loads(run.stdout)["metrics"])


if __name__ == "__main__":
    unittest.main()
