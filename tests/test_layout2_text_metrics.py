"""Tests for the offline text metrics module (``easycirq-text-metrics/v1``)."""

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.layout2.text_metrics import (  # noqa: E402
    ANCHORS,
    DEFAULT_METRICS_PATH,
    REQUIRED_SIZES,
    SCHEMA,
    TextMetrics,
    collisions,
    frame_line_hit,
    load_metrics,
    text_bbox,
    text_size,
)

MARGIN = 1.1  # 1 + safety_margin (0.10) from the measured asset


def real_asset_data():
    return json.loads(DEFAULT_METRICS_PATH.read_text(encoding="utf-8"))


def minimal_asset():
    """A valid in-memory asset with round numbers for estimator tests."""

    sizes = {}
    for size in REQUIRED_SIZES:
        sizes[str(size)] = {
            "height": 10.0,
            "ascii_char_w": 5.0,
            "cjk_char_w": 8.0,
            "space_w": 3.0,
            "provenance": "test fixture",
        }
    return {
        "schema": SCHEMA,
        "measured_at": "2026-10-29",
        "safety_margin": 0.1,
        "sizes": sizes,
    }


class AssetTests(unittest.TestCase):
    def test_default_asset_loads(self):
        metrics = load_metrics()
        self.assertIsInstance(metrics, TextMetrics)
        self.assertEqual(metrics.schema, SCHEMA)
        self.assertEqual(metrics.measured_at, "2026-10-29")
        self.assertAlmostEqual(metrics.safety_margin, 0.10)
        self.assertEqual(metrics.path, DEFAULT_METRICS_PATH)
        self.assertEqual(metrics.available_sizes(), (6, 7, 8, 9, 10, 12, 14, 20))
        for size in REQUIRED_SIZES:
            self.assertIn(size, metrics.sizes)
        self.assertIn("client", metrics.source)

    def test_measured_values_are_consumed_not_copied(self):
        metrics = load_metrics()
        self.assertAlmostEqual(metrics.sizes[20].ascii_char_w, 10.89)
        self.assertAlmostEqual(metrics.sizes[20].cjk_char_w, 17.27)
        self.assertAlmostEqual(metrics.sizes[20].space_w, 5.99)
        self.assertAlmostEqual(metrics.sizes[10].ascii_char_w, 5.5)
        self.assertAlmostEqual(metrics.sizes[8].height, 6.58)
        self.assertAlmostEqual(metrics.sizes[14].cjk_char_w, 12.1)
        self.assertIn("measured", metrics.sizes[8].provenance)

    def test_extrapolated_sizes_are_marked(self):
        metrics = load_metrics()
        for size in (6, 7):
            entry = metrics.sizes[size]
            self.assertIn("extrapolated", entry.provenance)
            self.assertIn("re-measure", entry.provenance)
        # 6/7 must not carry the corrupt merged values any more.
        self.assertAlmostEqual(metrics.sizes[6].cjk_char_w, 5.13)
        self.assertAlmostEqual(metrics.sizes[7].height, 5.68)
        # size 20 height is extrapolated, its widths are measured.
        raw = real_asset_data()
        self.assertEqual(raw["sizes"]["20"]["extrapolated_fields"], ["height"])
        self.assertAlmostEqual(metrics.sizes[20].height, 16.97)

    def test_anchor_definitions_are_recorded_in_the_asset(self):
        anchor_docs = real_asset_data()["anchors"]
        for anchor in ANCHORS:
            self.assertIn(anchor, anchor_docs)
        self.assertIn("y-up", anchor_docs["coordinate_system"])
        self.assertIn("rotation", anchor_docs)

    def test_custom_path_is_honoured(self):
        data = real_asset_data()
        data["sizes"]["10"]["ascii_char_w"] = 99.0
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "metrics.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            metrics = load_metrics(path)
        self.assertEqual(metrics.path, path)
        self.assertAlmostEqual(metrics.sizes[10].ascii_char_w, 99.0)

    def test_mapping_metrics_are_accepted_by_text_size(self):
        result = text_size("A", 10, metrics=minimal_asset())
        self.assertAlmostEqual(result["w"], 5.0 * 1.1)
        self.assertAlmostEqual(result["h"], 10.0 * 1.1)


class TextSizeTests(unittest.TestCase):
    def test_ascii_width_uses_measured_per_char_width(self):
        result = text_size("AB", 10)
        self.assertAlmostEqual(result["w"], 2 * 5.5 * MARGIN)
        self.assertAlmostEqual(result["h"], 8.6 * MARGIN)
        self.assertEqual(len(result["bbox"]), 4)

    def test_cjk_width_uses_measured_per_char_width(self):
        result = text_size("中文", 10)
        self.assertAlmostEqual(result["w"], 2 * 8.57 * MARGIN)
        # A CJK glyph is wider than a Latin one at the same size.
        self.assertGreater(result["w"], text_size("AB", 10)["w"])

    def test_mixed_text_sums_the_character_classes(self):
        result = text_size("A中B", 10)
        self.assertAlmostEqual(result["w"], (2 * 5.5 + 8.57) * MARGIN)

    def test_space_uses_its_own_width(self):
        result = text_size("A A", 10)
        self.assertAlmostEqual(result["w"], (2 * 5.5 + 3.03) * MARGIN)

    def test_width_and_height_scale_with_font_size(self):
        small = text_size("AB", 10)
        large = text_size("AB", 20)
        self.assertAlmostEqual(large["w"], small["w"] * (10.89 / 5.5))
        self.assertGreater(large["h"], small["h"])

    def test_safety_margin_is_applied(self):
        raw = load_metrics().sizes[20]
        result = text_size("A", 20)
        self.assertAlmostEqual(result["w"], raw.ascii_char_w * 1.1)
        self.assertAlmostEqual(text_size("中", 20)["w"], raw.cjk_char_w * 1.1)
        self.assertAlmostEqual(result["h"], raw.height * 1.1)

    def test_empty_text_is_degenerate_but_valid(self):
        result = text_size("", 10)
        self.assertEqual(result["w"], 0.0)
        self.assertAlmostEqual(result["h"], 8.6 * MARGIN)
        self.assertEqual(result["bbox"][0], result["bbox"][2])

    def test_unknown_size_is_blocked(self):
        for bad in (11, 8.5, 0, -3, True, "abc"):
            with self.subTest(size=bad):
                with self.assertRaises(ValueError) as ctx:
                    text_size("A", bad)
                self.assertIn("blocked", str(ctx.exception))

    def test_non_string_text_is_rejected(self):
        with self.assertRaises(ValueError):
            text_size(None, 10)  # type: ignore[arg-type]

    def test_explicit_metrics_match_the_default_asset(self):
        metrics = load_metrics()
        default = text_size("中文AB", 12)
        explicit = text_size("中文AB", 12, metrics=metrics)
        path_form = text_size("中文AB", 12, metrics=str(DEFAULT_METRICS_PATH))
        self.assertEqual(default, explicit)
        self.assertEqual(default, path_form)

    def test_text_bbox_alias_matches_text_size(self):
        for anchor in ANCHORS:
            self.assertEqual(
                text_size("AB", 10, anchor),
                text_bbox("AB", 10, anchor),
            )

    def test_anchor_geometry(self):
        width = 2 * 5.5 * MARGIN
        height = 8.6 * MARGIN
        expectations = {
            "left_top": [0.0, -height, width, 0.0],
            "left_center": [0.0, -height / 2, width, height / 2],
            "center": [-width / 2, -height / 2, width / 2, height / 2],
            "right_top": [-width, -height, 0.0, 0.0],
        }
        for anchor, expected in expectations.items():
            with self.subTest(anchor=anchor):
                result = text_size("AB", 10, anchor)
                self.assertAlmostEqual(result["w"], width)
                self.assertAlmostEqual(result["h"], height)
                for got, want in zip(result["bbox"], expected):
                    self.assertAlmostEqual(got, want)

    def test_anchor_translation_offsets_the_bbox(self):
        result = text_size("AB", 10, "center", x=100, y=200)
        self.assertAlmostEqual(result["bbox"][0], 100 - result["w"] / 2)
        self.assertAlmostEqual(result["bbox"][1], 200 - result["h"] / 2)
        self.assertAlmostEqual(result["bbox"][2], 100 + result["w"] / 2)
        self.assertAlmostEqual(result["bbox"][3], 200 + result["h"] / 2)

    def test_anchor_alias_with_hyphen_is_accepted(self):
        self.assertEqual(
            text_size("AB", 10, "left-top"),
            text_size("AB", 10, "left_top"),
        )

    def test_invalid_anchor_is_blocked(self):
        with self.assertRaises(ValueError):
            text_size("AB", 10, "baseline")


class CollisionTests(unittest.TestCase):
    def test_overlapping_boxes_collide(self):
        self.assertEqual(collisions([[0, 0, 10, 10], [5, 5, 15, 15]]), [(0, 1)])

    def test_separated_boxes_do_not_collide(self):
        self.assertEqual(collisions([[0, 0, 10, 10], [20, 0, 30, 10]]), [])
        self.assertEqual(collisions([[0, 0, 10, 10], [0, 20, 10, 30]]), [])

    def test_gap_is_the_required_clearance(self):
        # 2 units apart in x, gap 2 -> exactly clear; gap 2.5 -> too close.
        self.assertEqual(collisions([[0, 0, 10, 10], [12, 0, 22, 10]], gap=2), [])
        self.assertEqual(collisions([[0, 0, 10, 10], [12, 0, 22, 10]], gap=2.5), [(0, 1)])
        # 1.9 units apart is closer than the default gap of 2.
        self.assertEqual(collisions([[0, 0, 10, 10], [11.9, 0, 21.9, 10]]), [(0, 1)])

    def test_touching_boxes_only_collide_with_positive_gap(self):
        boxes = [[0, 0, 10, 10], [10, 0, 20, 10]]
        self.assertEqual(collisions(boxes, gap=0), [])
        self.assertEqual(collisions(boxes, gap=2), [(0, 1)])

    def test_diagonal_clearance(self):
        # 1 unit in x but 5 units in y: one axis keeps the gap -> clear.
        self.assertEqual(collisions([[0, 0, 10, 10], [11, 15, 21, 25]], gap=2), [])

    def test_pairs_are_sorted_and_deterministic(self):
        boxes = [[0, 0, 10, 10], [4, 0, 14, 10], [8, 0, 18, 10], [100, 0, 110, 10]]
        first = collisions(boxes)
        self.assertEqual(first, [(0, 1), (0, 2), (1, 2)])
        self.assertEqual(first, collisions(boxes))
        self.assertEqual(first, sorted(first))

    def test_rect_mappings_are_accepted(self):
        first = {"minX": 0, "minY": 0, "maxX": 10, "maxY": 10}
        second = {"minX": 10, "minY": 10, "maxX": 20, "maxY": 20}
        self.assertEqual(collisions([first, second], gap=2), [(0, 1)])

    def test_invalid_boxes_and_gap_are_rejected(self):
        with self.assertRaises(ValueError):
            collisions([[0, 0, 10]])
        with self.assertRaises(ValueError):
            collisions([[10, 0, 0, 10]])
        with self.assertRaises(ValueError):
            collisions([[0, 0, 10, 10]], gap=-1)


class FrameLineTests(unittest.TestCase):
    FRAME = [10, 10, 100, 50]

    def test_box_inside_the_frame_is_not_a_hit(self):
        self.assertFalse(frame_line_hit([20, 20, 40, 40], [self.FRAME]))

    def test_box_fully_outside_is_not_a_hit(self):
        self.assertFalse(frame_line_hit([110, 20, 120, 40], [self.FRAME]))
        self.assertFalse(frame_line_hit([20, 60, 40, 70], [self.FRAME]))

    def test_box_crossing_a_frame_line_is_a_hit(self):
        self.assertTrue(frame_line_hit([5, 20, 15, 40], [self.FRAME]))
        self.assertTrue(frame_line_hit([20, 45, 40, 55], [self.FRAME]))
        # A box bigger than the frame necessarily crosses its outline.
        self.assertTrue(frame_line_hit([0, 0, 120, 60], [self.FRAME]))

    def test_touching_the_outline_counts_as_a_hit(self):
        self.assertTrue(frame_line_hit([10, 20, 15, 30], [self.FRAME]))
        self.assertTrue(frame_line_hit([95, 20, 100, 30], [self.FRAME]))
        self.assertTrue(frame_line_hit([20, 50, 40, 55], [self.FRAME]))

    def test_stroke_widens_the_outline(self):
        near = [102, 20, 108, 30]  # 2 units outside the right edge
        self.assertFalse(frame_line_hit(near, [self.FRAME]))
        self.assertTrue(frame_line_hit(near, [self.FRAME], stroke=3))

    def test_mapping_frames_and_multiple_frames(self):
        frames = [{"minX": 0, "minY": 0, "maxX": 10, "maxY": 10}, self.FRAME]
        self.assertTrue(frame_line_hit([9, 5, 12, 6], frames))
        self.assertFalse(frame_line_hit([50, 20, 60, 30], frames))

    def test_invalid_inputs_are_rejected(self):
        with self.assertRaises(ValueError):
            frame_line_hit([0, 0, 10], [self.FRAME])
        with self.assertRaises(ValueError):
            frame_line_hit([0, 0, 10, 10], [[10, 10, 5, 50]])
        with self.assertRaises(ValueError):
            frame_line_hit([0, 0, 10, 10], [self.FRAME], stroke=-1)


class InvalidMetricsTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def write(self, payload, name="metrics.json"):
        path = self.tmp / name
        if isinstance(payload, str):
            path.write_text(payload, encoding="utf-8")
        else:
            path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def assert_blocked(self, path):
        with self.assertRaises(ValueError) as ctx:
            load_metrics(path)
        self.assertIn("blocked", str(ctx.exception))

    def test_valid_minimal_asset_is_accepted(self):
        metrics = load_metrics(self.write(minimal_asset()))
        self.assertEqual(metrics.available_sizes(), REQUIRED_SIZES)

    def test_missing_file_is_blocked(self):
        self.assert_blocked(self.tmp / "does-not-exist.json")

    def test_malformed_json_is_blocked(self):
        self.assert_blocked(self.write("{ not json"))

    def test_non_object_payload_is_blocked(self):
        self.assert_blocked(self.write("[1, 2, 3]"))

    def test_wrong_schema_is_blocked(self):
        data = minimal_asset()
        data["schema"] = "easycirq-text-metrics/v0"
        self.assert_blocked(self.write(data))

    def test_missing_required_size_is_blocked(self):
        data = minimal_asset()
        del data["sizes"]["7"]
        self.assert_blocked(self.write(data))

    def test_empty_sizes_is_blocked(self):
        data = minimal_asset()
        data["sizes"] = {}
        self.assert_blocked(self.write(data))

    def test_missing_measured_field_is_blocked(self):
        data = minimal_asset()
        del data["sizes"]["8"]["ascii_char_w"]
        self.assert_blocked(self.write(data))

    def test_non_positive_metric_is_blocked(self):
        for field, value in (("height", 0), ("cjk_char_w", -1), ("space_w", 0.0)):
            with self.subTest(field=field):
                data = minimal_asset()
                data["sizes"]["9"][field] = value
                self.assert_blocked(self.write(data))

    def test_non_finite_metric_is_blocked(self):
        data = minimal_asset()
        data["sizes"]["10"]["height"] = float("nan")
        self.assert_blocked(self.write(data))

    def test_negative_safety_margin_is_blocked(self):
        data = minimal_asset()
        data["safety_margin"] = -0.1
        self.assert_blocked(self.write(data))

    def test_duplicate_normalized_size_is_blocked(self):
        data = minimal_asset()
        data["sizes"]["7.0"] = copy.deepcopy(data["sizes"]["7"])
        self.assert_blocked(self.write(data))

    def test_invalid_metrics_mapping_blocks_text_size(self):
        data = minimal_asset()
        del data["sizes"]["12"]
        with self.assertRaises(ValueError):
            text_size("A", 10, metrics=data)

    def test_safety_margin_is_read_from_custom_asset(self):
        data = minimal_asset()
        data["safety_margin"] = 0.5
        path = self.write(data)
        result = text_size("A", 10, metrics=path)
        self.assertAlmostEqual(result["w"], 5.0 * 1.5)
        self.assertAlmostEqual(result["h"], 10.0 * 1.5)


class DeterminismTests(unittest.TestCase):
    def test_repeated_calls_are_identical(self):
        first = text_size("中文AB ", 12)
        for _ in range(5):
            self.assertEqual(text_size("中文AB ", 12), first)

    def test_collision_results_are_stable(self):
        boxes = [[0, 0, 10, 10], [8, 0, 18, 10], [30, 30, 40, 40]]
        expected = collisions(boxes)
        for _ in range(5):
            self.assertEqual(collisions(boxes), expected)


if __name__ == "__main__":
    unittest.main()
