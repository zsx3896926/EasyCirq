"""Tests for label-aware spec modules (offline)."""

import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import block_spec  # noqa: E402

ENVELOPES = {
    "schema": "easycirq-block-envelopes/v1",
    "blocks": {
        "block.demo": {"w": 300.0, "h": 200.0,
                       "halo": {"left": 60.0, "right": 120.0, "top": 10.0, "bottom": 4.0},
                       "label_bbox": {"w": 480.0, "h": 214.0}},
    },
}


class BlockSpecTests(unittest.TestCase):
    def _env(self):
        tmp = pathlib.Path(tempfile.mkdtemp()) / "env.json"
        tmp.write_text(json.dumps(ENVELOPES), encoding="utf-8")
        return tmp

    def test_modules_use_measured_halo_not_a_small_default(self):
        modules = block_spec.modules_for(["block.demo"], block_spec.load_envelopes(self._env()))
        halo = modules[0]["halo"]
        self.assertEqual(halo, {"left": 60.0, "right": 120.0, "top": 10.0, "bottom": 4.0})
        self.assertGreater(halo["right"], 8.0)

    def test_halo_scale_shrinks_or_grows(self):
        env = block_spec.load_envelopes(self._env())
        half = block_spec.modules_for(["block.demo"], env, halo_scale=0.5)[0]["halo"]
        self.assertEqual(half["right"], 60.0)

    def test_label_clearance_reports_extra_space(self):
        extra = block_spec.label_clearance("block.demo", block_spec.load_envelopes(self._env()))
        self.assertEqual(extra["extra_w"], 180.0)
        self.assertEqual(extra["extra_h"], 14.0)

    def test_unknown_block_fails_closed(self):
        with self.assertRaises(ValueError):
            block_spec.modules_for(["block.nope"], block_spec.load_envelopes(self._env()))

    def test_spec_carries_halo_and_engine(self):
        data = block_spec.spec("demo", ["block.demo"], envelope_path=self._env())
        self.assertEqual(data["engine"], "templates")
        self.assertEqual(data["modules"][0]["halo"]["left"], 60.0)

    def test_real_asset_has_label_aware_halos(self):
        envelopes = block_spec.load_envelopes()
        block = "block.es8311_codec_i2s"
        halo = block_spec.halo_of(block, envelopes)
        self.assertGreater(halo["right"], 50.0)   # measured label space, not 8
        extra = block_spec.label_clearance(block, envelopes)
        self.assertGreater(extra["extra_w"], 0.0)

    def test_pipeline_fills_measured_halo_for_block_modules(self):
        import pipeline
        block = "block.es8311_codec_i2s"   # real measured entry
        modules = [{"id": block, "w": 300, "h": 200, "block": block}]
        halo = pipeline._apply_measured_halos(modules)[0]["halo"]
        self.assertGreater(halo["right"], 50.0)
        self.assertGreater(halo["left"], 20.0)

    def test_pipeline_keeps_larger_declared_halo(self):
        import pipeline
        block = "block.es8311_codec_i2s"
        modules = [{"id": block, "w": 300, "h": 200, "block": block,
                    "halo": {"left": 500, "right": 500, "top": 500, "bottom": 500}}]
        halo = pipeline._apply_measured_halos(modules)[0]["halo"]
        self.assertEqual(halo, {"left": 500, "right": 500, "top": 500, "bottom": 500})


if __name__ == "__main__":
    unittest.main()
