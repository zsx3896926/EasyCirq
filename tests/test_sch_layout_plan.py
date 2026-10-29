import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "easycirq" / "scripts" / "sch_layout_plan.py"
sys.path.insert(0, str(ROOT / "easycirq" / "scripts"))
import sch_layout_plan as planner  # noqa: E402


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


def make_spec(blocks, title_block=None, options=None):
    return {
        "schema": "easycirq-sch-layout-plan/v1",
        "page": {"width": 1170, "height": 825, "margin": 12},
        "titleBlock": title_block,
        "blocks": blocks,
        "options": options or {"gap": 24, "zonePad": 18, "titleGap": 34},
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

    def test_frames_do_not_overlap_each_other(self):
        code, rep = self.run_plan(spec())
        frames = rep["frames"]
        for i in range(len(frames)):
            for j in range(i + 1, len(frames)):
                a, b = frames[i]["rect"], frames[j]["rect"]
                ox = max(0, min(a["maxX"], b["maxX"]) - max(a["minX"], b["minX"]))
                oy = max(0, min(a["maxY"], b["maxY"]) - max(a["minY"], b["minY"]))
                self.assertEqual(ox * oy, 0, "zones overlap: %s %s" % (a, b))

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

    def test_envelope_table_fills_missing_sizes(self):
        data = spec()
        for b in data["blocks"]:
            b.pop("envelope", None)
        rep = planner.plan(data, planner.load_envelopes())
        self.assertEqual(rep["verdict"], "pass")
        self.assertEqual(len(rep["placements"]), 3)

    def test_missing_envelope_is_blocked(self):
        data = spec()
        data["blocks"] = [{"id": "block.unknown", "title": "x"}]
        code, rep = self.run_plan(data)
        self.assertEqual(code, 2)

    def test_invalid_spec_blocked(self):
        code, rep = self.run_plan({"schema": "wrong"})
        self.assertEqual(code, 2)
        self.assertEqual(rep["verdict"], "blocked")

    # --- adaptive halo -------------------------------------------------
    def test_halo_expands_zone_and_lowers_fill(self):
        def plan_one(halo=None):
            block = {"id": "block.halo_probe", "title": "halo", "envelope": {"w": 300, "h": 200}}
            if halo is not None:
                block["halo"] = halo
            return planner.plan(make_spec([block]))

        base = plan_one()
        haloed = plan_one(60)
        below_pad = plan_one(4)
        bzone = base["placements"][0]["zone"]
        hzone = haloed["placements"][0]["zone"]
        # zone padding is max(zonePad=18, halo=60): each free edge grows by 42
        self.assertEqual((hzone[2] - hzone[0]) - (bzone[2] - bzone[0]), 60 - 18)
        self.assertEqual((hzone[3] - hzone[1]) - (bzone[3] - bzone[1]), 60 - 18)
        self.assertLess(haloed["metrics"]["zone_fill_ratio"],
                        base["metrics"]["zone_fill_ratio"])
        # a halo below zonePad must not shrink the zone
        self.assertEqual(below_pad["placements"][0]["zone"], bzone)
        # halo is carried into the placement for auditability
        self.assertEqual(haloed["placements"][0]["halo"], 60)
        self.assertNotIn("halo", base["placements"][0])

    def test_negative_halo_is_rejected(self):
        block = {"id": "block.bad_halo", "title": "bad", "envelope": {"w": 100, "h": 100},
                 "halo": -5}
        code, rep = self.run_plan(make_spec([block]))
        self.assertEqual(code, 2)
        self.assertEqual(rep["verdict"], "blocked")

    # --- packing fallbacks ---------------------------------------------
    def test_tighter_gap_fallback_places_more_blocks(self):
        blocks = [{"id": "b%d" % i, "title": "块 %d" % i,
                   "envelope": {"w": 600, "h": 260}} for i in range(3)]
        data = make_spec(blocks)
        regions = planner._regions(data["page"], None)
        # nominal gap (max(gap=24, titleGap+6=40)) leaves the third block unplaced
        strict = planner._shelf_pack(copy.deepcopy(blocks), regions, 40)
        self.assertEqual(sum(1 for p in strict if p["bbox"] is None), 1)
        # the planner falls back to a tighter gap instead of giving up
        rep = planner.plan(copy.deepcopy(data))
        self.assertEqual(rep["verdict"], "pass", rep)
        self.assertFalse(rep["unplaced"])
        self.assertTrue(all(p["bbox"] for p in rep["placements"]))
        self.assertEqual(rep["metrics"]["fits"], 3)

    def test_output_is_deterministic(self):
        fallback_blocks = [{"id": "b%d" % i, "title": "块 %d" % i,
                            "envelope": {"w": 600, "h": 260}} for i in range(3)]
        for data in (spec(), make_spec(fallback_blocks)):
            first = planner.plan(copy.deepcopy(data))
            second = planner.plan(copy.deepcopy(data))
            self.assertEqual(json.dumps(first, ensure_ascii=False, sort_keys=True),
                             json.dumps(second, ensure_ascii=False, sort_keys=True))

    # --- metrics / score -----------------------------------------------
    def test_zone_fill_and_balance_metrics(self):
        code, rep = self.run_plan(spec())
        self.assertEqual(code, 0, rep)
        m = rep["metrics"]
        for key in ("fits", "overlaps", "area_usage", "zone_slack",
                    "title_clearance_violations", "score",
                    "zone_fill_ratio", "layout_balance"):
            self.assertIn(key, m)
        zone_area = sum((f["rect"]["maxX"] - f["rect"]["minX"]) *
                        (f["rect"]["maxY"] - f["rect"]["minY"]) for f in rep["frames"])
        block_area = sum((p["bbox"][2] - p["bbox"][0]) * (p["bbox"][3] - p["bbox"][1])
                         for p in rep["placements"] if p["bbox"])
        self.assertAlmostEqual(m["zone_fill_ratio"], round(block_area / zone_area, 3), places=3)
        areas = [(f["rect"]["maxX"] - f["rect"]["minX"]) *
                 (f["rect"]["maxY"] - f["rect"]["minY"]) for f in rep["frames"]]
        self.assertAlmostEqual(m["layout_balance"], round(max(areas) / min(areas), 3), places=3)
        self.assertGreaterEqual(m["layout_balance"], 1.0)
        self.assertTrue(0.0 < m["zone_fill_ratio"] <= 1.0)
        self.assertTrue(0.0 <= m["score"] <= 100.0)

    def test_score_rewards_fill_and_balance(self):
        base = {"fits": 2, "overlaps": 0, "area_usage": 0.45, "zone_fill_ratio": 0.70,
                "layout_balance": 1.0, "zone_slack": 0.10, "title_clearance_violations": 0}
        good = planner._score(base, 2)
        self.assertEqual(good, 100.0)
        self.assertGreater(good, planner._score(dict(base, zone_fill_ratio=0.30), 2))
        self.assertGreater(good, planner._score(dict(base, zone_fill_ratio=0.95), 2))
        self.assertGreater(good, planner._score(dict(base, layout_balance=3.0), 2))
        self.assertGreater(good, planner._score(dict(base, overlaps=1), 2))
        self.assertGreater(good, planner._score(dict(base, fits=1), 2))
        # the whole 0.55-0.85 band is equally rewarded
        self.assertEqual(planner._score(dict(base, zone_fill_ratio=0.55), 2), good)
        self.assertEqual(planner._score(dict(base, zone_fill_ratio=0.85), 2), good)

    def test_pass_scores_higher_than_blocked(self):
        _, good = self.run_plan(spec())
        blocks = [{"id": "b%d" % i, "title": "块 %d" % i,
                   "envelope": {"w": 560, "h": 340}} for i in range(6)]
        _, bad = self.run_plan(spec(blocks=blocks))
        self.assertEqual(good["verdict"], "pass")
        self.assertEqual(bad["verdict"], "blocked")
        self.assertEqual(bad["metrics"]["score"], 0.0)
        self.assertLess(bad["metrics"]["score"], good["metrics"]["score"])


if __name__ == "__main__":
    unittest.main()
