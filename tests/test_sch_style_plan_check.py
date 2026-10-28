import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "easycirq" / "scripts" / "sch_style_plan_check.py"


def plan(good=True):
    d = {
        "schema": "easycirq-sch-style-plan/v1",
        "sheet": {"width_mm": 297, "height_mm": 210, "size": "A4"},
        "zones": [
            {"id": "a", "title": "CODEC", "order": 1, "purpose": "音频",
             "rect_mm": [10, 10, 120, 80], "borderColor": "#00B3B3", "titleSize": 14},
            {"id": "b", "title": "PA", "order": 2, "purpose": "功放",
             "rect_mm": [150, 110, 120, 80], "borderColor": "#C800C8", "titleSize": 14},
        ],
        "titleBlock": {"project": "ESP32", "version": "V0.4", "date": "2026-10-28",
                       "sheet": "Schematic2", "page": "3/5", "size": "A4"},
    }
    if not good:
        d["zones"][0]["title"] = ""
    return d


class StylePlanCheck(unittest.TestCase):
    def run_plan(self, data):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "plan.json"
            p.write_text(json.dumps(data), encoding="utf-8")
            r = subprocess.run([sys.executable, str(SCRIPT), str(p)],
                               capture_output=True, text=True, encoding="utf-8")
            return r.returncode, json.loads(r.stdout)

    def test_good_plan_passes(self):
        code, rep = self.run_plan(plan())
        self.assertEqual(code, 0, rep)
        self.assertEqual(rep["verdict"], "pass")

    def test_missing_title_blocked(self):
        code, rep = self.run_plan(plan(good=False))
        self.assertEqual(code, 2)
        self.assertEqual(rep["verdict"], "blocked")

    def test_wrong_schema_blocked(self):
        d = plan(); d["schema"] = "wrong"
        code, rep = self.run_plan(d)
        self.assertEqual(code, 2)

    def test_empty_zones_blocked(self):
        d = plan(); d["zones"] = []
        code, rep = self.run_plan(d)
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
