import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "easycirq" / "scripts"
BATCH = SCRIPTS / "sch_layout_batch.py"

sys.path.insert(0, str(SCRIPTS))
import sch_layout_plan as planner  # noqa: E402


def spec(blocks):
    return {
        "schema": "easycirq-sch-layout-plan/v1",
        "page": {"width": 1170, "height": 825, "margin": 12},
        "titleBlock": {"minX": 610, "minY": 12, "maxX": 1170, "maxY": 380},
        "blocks": [{"id": b, "title": b.split(".", 1)[-1]} for b in blocks],
    }


class PlannerScore(unittest.TestCase):
    def test_pass_plan_has_score(self):
        env = planner.load_envelopes()
        rep = planner.plan(spec(["block.es8311_codec_i2s", "block.mems_mic_analog"]), env)
        self.assertEqual(rep["verdict"], "pass")
        self.assertGreater(rep["metrics"]["score"], 0)
        self.assertIn("zone_slack", rep["metrics"])
        self.assertEqual(rep["metrics"]["title_clearance_violations"], 0)

    def test_blocked_plan_scores_lower_than_pass(self):
        env = planner.load_envelopes()
        small = planner.plan(spec(["block.es8311_codec_i2s", "block.mems_mic_analog"]), env)
        big = planner.plan(spec(["block.es8311_codec_i2s", "block.aw8737_classd_spk",
                                 "block.bq24074_powerpath_charger",
                                 "block.sy7088_boost_5v"]), env)
        self.assertEqual(big["verdict"], "blocked")
        self.assertLess(big["metrics"]["score"], small["metrics"]["score"])


class BatchPlanner(unittest.TestCase):
    def run_batch(self, *args):
        r = subprocess.run([sys.executable, str(BATCH), *args],
                           capture_output=True, text=True, encoding="utf-8")
        return r.returncode, json.loads(r.stdout)

    def test_batch_ranks_combinations(self):
        code, rep = self.run_batch("--pool", "block.es8311_codec_i2s,block.mems_mic_analog,"
                                            "block.aw8737_classd_spk,block.esp32s3_wroom1_module", "--sizes", "2",
                                   "--top", "5")
        self.assertEqual(code, 0, rep)
        self.assertEqual(rep["evaluated"], 6)
        self.assertEqual(len(rep["top"]), 5)
        scores = [r["score"] for r in rep["results"]]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertGreater(rep["passed"], 0)

    def test_batch_unknown_block_is_skipped(self):
        code, rep = self.run_batch("--pool", "block.unknown,block.mems_mic_analog",
                                   "--sizes", "1")
        self.assertEqual(rep["pool_size"], 1)
        self.assertEqual(rep["evaluated"], 1)

    def test_batch_all_pool_deterministic(self):
        code1, rep1 = self.run_batch("--sizes", "2", "--top", "3")
        code2, rep2 = self.run_batch("--sizes", "2", "--top", "3")
        self.assertEqual(rep1["top"], rep2["top"])


if __name__ == "__main__":
    unittest.main()
