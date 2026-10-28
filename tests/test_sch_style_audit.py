import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "easycirq" / "scripts" / "sch_style_audit.py"


def good_input():
    return {
        "schema": "easycirq-sch-style-input/v1",
        "sheet": {"width_mm": 297, "height_mm": 210, "size": "A4"},
        "zones": [
            {"id": "a", "title": "CODEC", "order": 1, "purpose": "音频编解码",
             "rect_mm": [10, 10, 120, 80], "borderColor": "#00B3B3", "titleSize": 14},
            {"id": "b", "title": "PA", "order": 2, "purpose": "功率放大",
             "rect_mm": [150, 110, 120, 80], "borderColor": "#C800C8", "titleSize": 14},
        ],
        "texts": [
            {"id": "t1", "role": "zone_title", "text": "CODEC", "size": 14,
             "color": "#000000", "bbox_mm": [12, 12, 20, 4]},
            {"id": "t2", "role": "net_label", "text": "AUD_3V3", "size": 9,
             "color": "#CC0000", "bbox_mm": [20, 40, 14, 2]},
            {"id": "t3", "role": "value", "text": "10uF", "size": 8,
             "color": "#000000", "bbox_mm": [40, 40, 8, 2]},
            {"id": "t4", "role": "note", "text": "CLOSE TO IC", "size": 7,
             "color": "#666666", "bbox_mm": [60, 60, 20, 2]},
        ],
        "titleBlock": {"project": "ESP32-S31", "version": "V0.4", "date": "2026-10-28",
                       "sheet": "Schematic2", "page": "3/5", "size": "A4"},
    }


class StyleAudit(unittest.TestCase):
    def run_audit(self, data):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "in.json"
            p.write_text(json.dumps(data), encoding="utf-8")
            r = subprocess.run([sys.executable, str(SCRIPT), str(p)],
                               capture_output=True, text=True, encoding="utf-8")
            return r.returncode, json.loads(r.stdout)

    def test_good_passes(self):
        code, rep = self.run_audit(good_input())
        self.assertEqual(code, 0, rep)
        self.assertEqual(rep["verdict"], "pass")

    def test_missing_zone_title_blocked(self):
        d = good_input(); d["zones"][0]["title"] = ""
        code, rep = self.run_audit(d)
        self.assertEqual(code, 2)
        self.assertEqual(rep["verdict"], "blocked")

    def test_zone_overlap_blocked(self):
        d = good_input(); d["zones"][1]["rect_mm"] = [50, 50, 120, 80]
        code, rep = self.run_audit(d)
        self.assertEqual(code, 2)
        self.assertEqual(rep["verdict"], "blocked")

    def test_bad_palette_review(self):
        d = good_input(); d["zones"][0]["borderColor"] = "#123456"
        code, rep = self.run_audit(d)
        self.assertEqual(code, 1)
        self.assertEqual(rep["verdict"], "review")

    def test_missing_title_block_field_blocked(self):
        d = good_input(); d["titleBlock"]["page"] = ""
        code, rep = self.run_audit(d)
        self.assertEqual(code, 2)

    def test_invalid_schema_blocked(self):
        d = good_input(); d["schema"] = "wrong"
        code, rep = self.run_audit(d)
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
