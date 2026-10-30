"""Tests for content-fitted block frames (offline)."""

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import frame_fit  # noqa: E402


def part(ref, x1, y1, x2, y2):
    return {"ref": ref, "bbox": {"minX": x1, "minY": y1, "maxX": x2, "maxY": y2}}


def flag(name, x1, y1, x2, y2):
    return {"name": name, "bbox": {"minX": x1, "minY": y1, "maxX": x2, "maxY": y2}}


def text(content, x1, y1, x2, y2):
    return {"content": content,
            "bbox": {"minX": x1, "minY": y1, "maxX": x2, "maxY": y2}}


BLOCKS = [{"id": "block.a", "title": "模块 A", "designators": ["U1"]},
          {"id": "block.b", "title": "模块 B", "designators": ["U2"]}]


class FrameFitTests(unittest.TestCase):
    def test_frame_covers_wire_end_flags(self):
        parts = [part("U1", 100, 100, 160, 200)]
        flags = [flag("BIG_NET", 300, 100, 330, 115)]   # wired far to the right
        report = frame_fit.build([BLOCKS[0]], parts, flags, [],
                                 connectivity={"U1": {"1": "BIG_NET"}})
        rect = report["frames"][0]["rect"]
        self.assertGreaterEqual(rect[2], 330)

    def test_frame_ignores_other_block_flags(self):
        parts = [part("U1", 100, 100, 160, 200)]
        flags = [flag("OTHER", 800, 700, 830, 715)]
        report = frame_fit.build([BLOCKS[0]], parts, flags, [],
                                 connectivity={"U1": {"1": "MINE"}})
        rect = report["frames"][0]["rect"]
        self.assertLess(rect[2], 800)

    def test_frame_covers_matching_text_and_designator(self):
        parts = [part("U1", 100, 100, 160, 200)]
        texts = [text("U1", 150, 220, 180, 235), text("MINE_NET", 320, 190, 380, 205)]
        report = frame_fit.build([BLOCKS[0]], parts, [], texts,
                                 connectivity={"U1": {"1": "MINE_NET"}})
        rect = report["frames"][0]["rect"]
        self.assertGreaterEqual(rect[2], 380)
        self.assertGreaterEqual(rect[3], 235)

    def test_title_is_localized_and_inside(self):
        parts = [part("U1", 100, 100, 160, 200)]
        report = frame_fit.build([BLOCKS[0]], parts, [], [])
        frame = report["frames"][0]
        self.assertEqual(frame["title"], "模块 A")
        self.assertGreaterEqual(frame["titleX"], frame["rect"][0])
        self.assertLessEqual(frame["titleY"], frame["rect"][3])

    def test_overlapping_frames_are_separated(self):
        parts = [part("U1", 100, 100, 160, 200), part("U2", 140, 120, 200, 220)]
        report = frame_fit.build(BLOCKS, parts, [], [])
        a, b = report["frames"][0]["rect"], report["frames"][1]["rect"]
        ox = min(a[2], b[2]) - max(a[0], b[0])
        oy = min(a[3], b[3]) - max(a[1], b[1])
        self.assertFalse(ox > 0 and oy > 0, (a, b))

    def test_frames_stay_inside_sheet_margins(self):
        parts = [part("U1", 1100, 700, 1160, 800)]
        flags = [flag("N", 1150, 800, 1180, 815)]
        report = frame_fit.build([BLOCKS[0]], parts, flags, [],
                                 connectivity={"U1": {"1": "N"}})
        rect = report["frames"][0]["rect"]
        self.assertLessEqual(rect[2], frame_fit.SHEET_W - frame_fit.MARGIN)
        self.assertLessEqual(rect[3], frame_fit.SHEET_H - frame_fit.MARGIN)

    def test_rail_flags_do_not_expand_the_frame(self):
        parts = [part("U1", 100, 100, 160, 200)]
        flags = [flag("GND", 900, 100, 930, 115), flag("3V3_L3B_AU", 950, 100, 980, 115)]
        report = frame_fit.build([BLOCKS[0]], parts, flags, [],
                                 connectivity={"U1": {"1": "GND", "2": "3V3_L3B_AU"}})
        rect = report["frames"][0]["rect"]
        self.assertLess(rect[2], 900)

    def test_deterministic(self):
        parts = [part("U1", 100, 100, 160, 200)]
        a = frame_fit.build(BLOCKS, parts, [], [])
        b = frame_fit.build(BLOCKS, parts, [], [])
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()


    def test_rail_flags_do_not_expand_the_frame(self):
        parts = [part("U1", 100, 100, 160, 200)]
        flags = [flag("GND", 900, 100, 930, 115), flag("3V3_L3B_AU", 950, 100, 980, 115)]
        report = frame_fit.build([BLOCKS[0]], parts, flags, [],
                                 connectivity={"U1": {"1": "GND", "2": "3V3_L3B_AU"}})
        rect = report["frames"][0]["rect"]
        self.assertLess(rect[2], 900)

