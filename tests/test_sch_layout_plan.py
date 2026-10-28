import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "easycirq" / "scripts" / "sch_layout_plan.py"


def spec(blocks=None, title_block=True):
    return {
        "schema": "easycirq-sch-layout-plan/v1",
        "page": {"width": 1170, "height": 825, "margin": 12},
        "titleBlock": {"minX": 610, "minY": 12, "maxX": 1170, "maxY": 380} if title_block else None,
        "blocks": blocks or [
            {"id": "block.es8311_codec_i2s", "title": "音频编解码 ES8311", "envelope": {"w": 560, "h": 340}},
            {"id": "block.mems_mic_analog", "title": "模拟 MEMS 麦克风", "envelope": {"w": 460, "h": 220}},
            {"id": "block.aw8737_classd_spk", "title": "D 类功放 AW8737", "envelope": {"w": 560, "h": 340}},
        ],
        "options": {"gap": 24, "zonePad": 18, "titleGap": 34},
    }


class LayoutPlan(unittest.TestCase):
    def run_plan(self, data):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "spec.json"
            p.write_text(json.dumps(data), encoding="utf-8")
            r = subprocess.run([sys.executable, str(SCRIPT), str(p)],
                               capture_output=True, text=True, encoding="utf-8")
            return r.returncode, json.loads(r.stdout)

    def test_three_blocks_pass_and_avoid_title_block(self):
        code, rep = self.run_plan(spec())
        self.assertEqual(code, 0, rep)
        self.assertEqual(rep["verdict"], "pass")
        self.assertEqual(len(rep["frames"]), 3)
        for p in rep["placements"]:
            self.assertIsNotNone(p["bbox"])
            # nothing may enter the title block rectangle
            x1, y1, x2, y2 = p["bbox"]
            self.assertFalse(x1 < 1170 and x2 > 610 and y1 < 380 and y2 > 12,
                             "block overlaps title block: %s" % (p,))

    def test_zone_contains_block_and_title_above(self):
        code, rep = self.run_plan(spec())
        for p in rep["placements"]:
            zx1, zy1, zx2, zy2 = p["zone"]
            x1, y1, x2, y2 = p["bbox"]
            self.assertTrue(zx1 <= x1 and zy1 <= y1 and zx2 >= x2 and zy2 >= y2, p)
            self.assertGreaterEqual(zy2, y2 + 34, "zone must leave title clearance above block")

    def test_too_many_blocks_blocked(self):
        blocks = [{"id": "b%d" % i, "title": "块 %d" % i,
                   "envelope": {"w": 560, "h": 340}} for i in range(6)]
        code, rep = self.run_plan(spec(blocks=blocks))
        self.assertEqual(code, 2)
        self.assertEqual(rep["verdict"], "blocked")
        self.assertTrue(rep["unplaced"])

    def test_no_title_block_uses_full_page(self):
        code, rep = self.run_plan(spec(title_block=False))
        self.assertEqual(code, 0, rep)
        self.assertEqual(rep["metrics"]["area_usage"] > 0.3, True)

    def test_invalid_spec_blocked(self):
        code, rep = self.run_plan({"schema": "wrong"})
        self.assertEqual(code, 2)
        self.assertEqual(rep["verdict"], "blocked")


if __name__ == "__main__":
    unittest.main()
