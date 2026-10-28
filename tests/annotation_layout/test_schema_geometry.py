import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

try:
    from . import helpers
except ImportError:  # targeted discovery from tests/annotation_layout
    import helpers

from annotation_layout.geometry import (
    Rect,
    SpatialIndex,
    collinear_overlap,
    segment_enters_rect,
    segments_cross,
    svg_rect,
)
from annotation_layout.model import InputError, Rect as ModelRect, canonical_sha256
from annotation_layout.schema import load_input, validate_input


def box(x0, y0, w, h):
    return [float(x0), float(y0), float(x0 + w), float(y0 + h)]


class GeometryTest(unittest.TestCase):
    def test_rect_operations(self):
        rect = Rect(0, 0, 10, 5)
        self.assertEqual(rect.width, 10)
        self.assertEqual(rect.height, 5)
        self.assertEqual(rect.center, (5.0, 2.5))
        self.assertEqual(rect.translated(3, -2).as_list(), [3, -2, 13, 3])
        self.assertTrue(rect.intersects(Rect(9, 4, 20, 20)))
        self.assertFalse(rect.intersects(Rect(10, 0, 20, 5)))  # edge contact only
        self.assertTrue(rect.contains_rect(Rect(1, 1, 9, 4)))
        self.assertTrue(rect.contains_point((0, 0)))
        self.assertEqual(rect.overlap_extent(Rect(5, 2, 20, 20)), (5, 3))

    def test_segment_clipping_is_open_rectangle(self):
        rect = Rect(10, 10, 20, 20)
        self.assertTrue(segment_enters_rect((0, 15), (30, 15), rect))
        self.assertFalse(segment_enters_rect((0, 10), (30, 10), rect))  # on edge
        self.assertFalse(segment_enters_rect((10, 10), (10, 30), rect))  # on edge
        self.assertFalse(segment_enters_rect((0, 0), (5, 5), rect))
        crossing = segment_enters_rect((5, 5), (25, 25), rect)
        self.assertTrue(crossing)

    def test_segments_cross_and_collinear(self):
        self.assertTrue(segments_cross((0, 0), (10, 10), (0, 10), (10, 0)))
        self.assertFalse(segments_cross((0, 0), (10, 0), (0, 5), (10, 5)))
        self.assertTrue(collinear_overlap((0, 0), (10, 0), (5, 0), (15, 0)))
        self.assertFalse(collinear_overlap((0, 0), (10, 0), (10, 0), (20, 0)))

    def test_svg_flip_once(self):
        flipped = svg_rect(Rect(10, 20, 30, 40), page_height=100)
        self.assertEqual(flipped.as_list(), [10, 60, 30, 80])
        twice = svg_rect(flipped, page_height=100)
        self.assertEqual(twice.as_list(), [10, 20, 30, 40])

    def test_spatial_index_queries_degenerate_segments(self):
        index = SpatialIndex(16)
        index.add_rect("r", Rect(10, 10, 20, 20))
        index.add_segment("vertical", (15, 0), (15, 40))
        index.add_segment("horizontal", (0, 15), (40, 15))
        self.assertEqual(index.query_rect(Rect(11, 11, 19, 19)), ["r"])
        found = index.query_rect_segment(Rect(12, 12, 18, 18))
        self.assertEqual(found, ["horizontal", "vertical"])
        self.assertEqual(index.query_rect(Rect(100, 100, 120, 120)), [])


class SchemaTest(unittest.TestCase):
    def setUp(self):
        self.real = helpers.read_json(helpers.REAL)

    def test_real_frozen_fixture_is_valid(self):
        inp = load_input(helpers.REAL)
        self.assertEqual(len(inp.components), 19)
        self.assertEqual(len(inp.wires), 98)
        self.assertEqual(len(inp.fixed_texts), 94)
        self.assertEqual(len(inp.annotations), 42)
        self.assertEqual(inp.canonical_sha256,
                         load_input(helpers.REAL).canonical_sha256)
        self.assertEqual(inp.units.name, "schematic_raw")
        self.assertEqual(inp.coordinate_system.y_axis, "up")

    def test_canonical_hash_is_stable_and_sensitive(self):
        first = canonical_sha256(self.real)
        reordered = dict(reversed(list(self.real.items())))
        self.assertEqual(first, canonical_sha256(reordered))
        changed = json.loads(json.dumps(self.real))
        changed["project"]["name"] += "-x"
        self.assertNotEqual(first, canonical_sha256(changed))

    def test_invalid_cases_are_rejected_with_reasons(self):
        expected = {
            "nan.json": ("finite", "NaN"),
            "duplicate-id.json": ("duplicate",),
            "unknown-unit.json": ("units.name",),
            "bool-number.json": ("integer", "number", "boolean"),
            "bad-bbox.json": ("bbox",),
            "unknown-key.json": ("unknown key", "unknown"),
        }
        for name, needles in expected.items():
            with self.subTest(name=name):
                path = helpers.invalid(name)
                with self.assertRaises(InputError) as caught:
                    load_input(path)
                text = " ".join(caught.exception.reasons).lower()
                self.assertTrue(any(needle.lower() in text for needle in needles),
                                f"{name}: unexpected reasons {caught.exception.reasons}")

    def test_bool_is_not_a_number(self):
        document = json.loads(json.dumps(self.real))
        document["constraints"]["grid"] = True
        with self.assertRaises(InputError):
            validate_input(document)

    def test_duplicate_json_key_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "dup.json"
            path.write_text('{"schema": "annotation-layout/v1", "schema": "x"}',
                            encoding="utf-8")
            with self.assertRaises(InputError) as caught:
                load_input(path)
            self.assertTrue(any("duplicate" in reason for reason in caught.exception.reasons))

    def test_stale_source_hash_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            for name in ("layout.json", "list.json", "rendered-text.json", "sheet.json"):
                (directory / name).write_bytes((helpers.REAL.parent / name).read_bytes())
            document = json.loads(json.dumps(self.real))
            document["source"]["files"][0]["sha256"] = "0" * 64
            path = directory / "input.json"
            helpers.write_json(path, document)
            with self.assertRaises(InputError) as caught:
                load_input(path)
            self.assertTrue(any("stale source file" in reason
                                for reason in caught.exception.reasons))

    def test_unknown_top_level_key_rejected(self):
        document = dict(self.real)
        document["extra"] = 1
        with self.assertRaises(InputError):
            validate_input(document)

    def test_annotation_role_contract(self):
        document = json.loads(json.dumps(self.real))
        document["movable_annotations"][0]["role"] = "designator"
        document["movable_annotations"][0]["owner"] = {
            "kind": "page", "id": "page", "requirement": "none"}
        with self.assertRaises(InputError):
            validate_input(document)


if __name__ == "__main__":
    unittest.main()
