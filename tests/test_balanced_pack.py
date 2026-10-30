"""Tests for the balanced, centred module packer (offline)."""

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import balanced_pack  # noqa: E402


def module(name, w, h, halo=20):
    return {"id": name, "w": float(w), "h": float(h),
            "halo": {"left": halo, "right": halo, "top": halo, "bottom": halo}}


class BalancedPackTests(unittest.TestCase):
    def test_four_modules_fit_one_sheet(self):
        result = balanced_pack.pack([module("a", 300, 200), module("b", 250, 160),
                                     module("c", 220, 180), module("d", 260, 150)])
        self.assertTrue(result["fit"])
        self.assertEqual(len(result["placements"]), 4)
        self.assertGreater(result["utilization"], 0.2)

    def test_composition_is_centred_not_left_aligned(self):
        result = balanced_pack.pack([module("a", 300, 200), module("b", 300, 200)])
        comp = result["composition"]
        x0, _, x1, _ = balanced_pack._inner(balanced_pack.PAGE, balanced_pack.TITLE_BLOCK)
        left_margin = comp["x"] - x0
        right_margin = x1 - (comp["x"] + comp["w"])
        self.assertAlmostEqual(left_margin, right_margin, delta=2.0)
        self.assertGreater(left_margin, 10.0)

    def test_modules_do_not_overlap(self):
        result = balanced_pack.pack([module("a", 300, 200), module("b", 250, 160),
                                     module("c", 220, 180)])
        boxes = [(p["x"] - p["w"] / 2, p["y"] - p["h"] / 2,
                  p["x"] + p["w"] / 2, p["y"] + p["h"] / 2)
                 for p in result["placements"].values()]
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                a, b = boxes[i], boxes[j]
                overlap = (min(a[2], b[2]) - max(a[0], b[0]) > 0
                           and min(a[3], b[3]) - max(a[1], b[1]) > 0)
                self.assertFalse(overlap, (a, b))

    def test_stays_out_of_title_block(self):
        result = balanced_pack.pack([module("a", 400, 300), module("b", 400, 300)])
        tb = balanced_pack.TITLE_BLOCK
        for place in result["placements"].values():
            bottom = place["y"] - place["h"] / 2
            self.assertGreaterEqual(bottom, tb[3] - 0.5, place)

    def test_oversized_modules_report_no_fit(self):
        result = balanced_pack.pack([module("huge", 2000, 900)])
        self.assertFalse(result["fit"])

    def test_deterministic(self):
        mods = [module("a", 300, 200), module("b", 210, 120), module("c", 260, 90)]
        self.assertEqual(balanced_pack.pack(mods), balanced_pack.pack(mods))


if __name__ == "__main__":
    unittest.main()
