"""Tests for the ``easycirq-page-template/v1`` loader and keep-out geometry.

The assertions use the *measured* A4 template that ships in
``easycirq/assets/page-template.json`` (page 1170x825, margin 10, title-block
keep-out [460,10]-[1160,190] bottom-right) plus a bottom-left override to
prove the corner is data-driven, not hard-coded.
"""

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.layout2 import page_template as pt  # noqa: E402

TEMPLATE_PATH = ROOT / "easycirq" / "assets" / "page-template.json"

# Measured on EasyEDA Pro 4.1.78 (easycirq sch sheet-geometry --from-svg).
MEASURED_PAGE = {"width": 1170, "height": 825, "margin": 10}
MEASURED_INNER = pt.Rect(10, 10, 1160, 815)
MEASURED_TITLE_BLOCK = pt.Rect(460, 10, 1160, 190)
MEASURED_LEFT = pt.Rect(10, 10, 460, 815)
MEASURED_TOP_RIGHT = pt.Rect(460, 190, 1160, 815)


def read_asset_document():
    return json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))


def rect_dict(rect):
    return rect.to_dict()


class TemplateFixtureMixin(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = read_asset_document()
        cls.template = pt.load_template(TEMPLATE_PATH)

    def base_document(self):
        return copy.deepcopy(self.document)

    def assert_blocked(self, document, pattern):
        with self.assertRaisesRegex(pt.TemplateError, pattern):
            pt.PageTemplate.from_dict(document, source="fixture.json")

    def write_and_load(self, document, text=None):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "page-template.json"
            if text is None:
                path.write_text(json.dumps(document, indent=1), encoding="utf-8")
            else:
                path.write_text(text, encoding="utf-8")
            return pt.load_template(path)


class MeasuredTemplateTests(TemplateFixtureMixin):
    def test_page_size_and_margin_are_measured_values(self):
        self.assertEqual(self.template.width, 1170)
        self.assertEqual(self.template.height, 825)
        self.assertEqual(self.template.margin, 10)
        self.assertEqual(self.template.page_rect, pt.Rect(0, 0, 1170, 825))
        self.assertEqual(self.template.inner_border, MEASURED_INNER)
        self.assertEqual(self.template.usable_area, MEASURED_INNER)

    def test_title_block_measured_keepout(self):
        self.assertEqual(self.template.title_block_rect, MEASURED_TITLE_BLOCK)
        self.assertEqual(self.template.title_block_corner, "bottom-right")
        self.assertIs(self.template.title_block_visible, True)
        self.assertEqual(self.template.measured_at, "2026-10-29")
        self.assertEqual(self.template.provenance["client"], "EasyEDA Pro 4.1.78")
        self.assertTrue(any("bottom-left" in note for note in self.template.notes))

    def test_default_regions_are_measured_numbered(self):
        regions = self.template.usable_regions()
        self.assertEqual(tuple(region.name for region in regions), ("left", "top-right"))
        self.assertEqual(regions[0].rect, MEASURED_LEFT)
        self.assertEqual(regions[1].rect, MEASURED_TOP_RIGHT)
        self.assertEqual(self.template.region("left").rect, MEASURED_LEFT)
        self.assertEqual(
            self.template.regions_by_name(),
            {"left": MEASURED_LEFT, "top-right": MEASURED_TOP_RIGHT},
        )
        # Region is a named tuple: (name, rect) unpacking is part of the API.
        name, rect = regions[1]
        self.assertEqual((name, rect), ("top-right", MEASURED_TOP_RIGHT))

    def test_regions_plus_keepout_tile_the_usable_area(self):
        region_area = sum(region.rect.area for region in self.template.usable_regions())
        keepout = self.template.title_block_rect.clipped(self.template.usable_area)
        self.assertAlmostEqual(
            region_area + keepout.area, self.template.usable_area.area, places=9
        )
        self.assertAlmostEqual(region_area, 450 * 805 + 700 * 625, places=9)

    def test_asset_regions_match_derived_regions(self):
        asset_regions = self.document["regions"]
        derived = self.template.computed_regions()
        self.assertTrue(self.template.regions_overridden)
        self.assertEqual(
            asset_regions,
            [{"name": region.name, "rect": region.rect.to_dict()} for region in derived],
        )
        self.assertEqual(tuple(self.template.usable_regions()), derived)

    def test_rect_in_page_means_usable_area(self):
        self.assertTrue(self.template.rect_in_page(MEASURED_LEFT))
        self.assertTrue(self.template.rect_in_page(pt.Rect(20, 20, 40, 40)))
        # Inside the raw page but inside the margin: not usable.
        self.assertFalse(self.template.rect_in_page(pt.Rect(5, 5, 20, 20)))
        self.assertTrue(self.template.rect_in_raw_page(pt.Rect(5, 5, 20, 20)))
        # Slightly over the inner border is blocked without tolerance.
        self.assertFalse(self.template.rect_in_page(pt.Rect(1150, 10, 1170, 100)))
        self.assertTrue(self.template.rect_in_page(pt.Rect(1150, 10, 1170, 100), tolerance=10))
        # A rect fully covering the page is not inside the usable area.
        self.assertFalse(self.template.rect_in_page(pt.Rect(0, 0, 1170, 825)))

    def test_title_block_hit_blocks_overlapping_rects(self):
        self.assertTrue(self.template.title_block_hit(pt.Rect(500, 100, 520, 120)))
        self.assertTrue(self.template.title_block_hit(pt.Rect(455, 15, 465, 25)))
        self.assertTrue(
            self.template.title_block_hit(
                {"minX": 800, "minY": 50, "maxX": 900, "maxY": 150}
            )
        )
        self.assertTrue(self.template.title_block_hit([600, 20, 700, 30]))

    def test_title_block_touching_edge_is_not_a_hit(self):
        # Shared edges are legal: the left/top-right regions touch the keepout.
        self.assertFalse(self.template.title_block_hit(MEASURED_LEFT))
        self.assertFalse(self.template.title_block_hit(MEASURED_TOP_RIGHT))
        self.assertFalse(self.template.title_block_hit(pt.Rect(460, 190, 500, 200)))
        self.assertFalse(self.template.title_block_hit(pt.Rect(10, 190, 460, 250)))
        self.assertFalse(self.template.title_block_hit(pt.Rect(456, 196, 470, 210)))
        # tolerance expands the keepout, so a 5-unit gap can be closed.
        self.assertTrue(self.template.title_block_hit(pt.Rect(455, 195, 470, 210), tolerance=6))

    def test_region_of_measured_regions(self):
        self.assertEqual(self.template.region_of(pt.Rect(20, 20, 100, 100)), "left")
        self.assertEqual(self.template.region_of(pt.Rect(500, 300, 600, 400)), "top-right")
        # Straddles the two regions: ambiguous -> None.
        self.assertIsNone(self.template.region_of(pt.Rect(400, 300, 800, 400)))
        # Inside the title block keep-out: no region.
        self.assertIsNone(self.template.region_of(pt.Rect(500, 50, 600, 100)))
        # Sequence inputs are accepted too.
        self.assertEqual(self.template.region_of([20, 20, 100, 100]), "left")

    def test_region_of_tolerance(self):
        slightly_outside = pt.Rect(10, 5, 450, 800)
        self.assertIsNone(self.template.region_of(slightly_outside))
        self.assertIsNone(self.template.region_of(slightly_outside, tolerance=4))
        self.assertEqual(self.template.region_of(slightly_outside, tolerance=6), "left")
        with self.assertRaises(ValueError):
            self.template.region_of(pt.Rect(20, 20, 40, 40), tolerance=-1)

    def test_unknown_region_and_invalid_rect_raise(self):
        with self.assertRaises(KeyError):
            self.template.region("middle")
        with self.assertRaises(pt.TemplateError):
            self.template.title_block_hit({"minX": 1, "minY": 2})
        with self.assertRaises(pt.TemplateError):
            self.template.title_block_hit(pt.Rect(10, 10, 10, 100))

    def test_to_dict_round_trip(self):
        again = pt.PageTemplate.from_dict(self.template.to_dict())
        self.assertEqual(again.usable_regions(), self.template.usable_regions())
        self.assertEqual(again.title_block_rect, self.template.title_block_rect)
        self.assertEqual(again.title_block_corner, "bottom-right")
        self.assertEqual(again.to_dict(), self.template.to_dict())

    def test_inner_border_may_be_omitted_and_is_derived(self):
        document = self.base_document()
        del document["inner_border"]
        template = self.write_and_load(document)
        self.assertEqual(template.inner_border, MEASURED_INNER)
        self.assertEqual(template.usable_regions(), self.template.usable_regions())


class BottomLeftOverrideTests(TemplateFixtureMixin):
    BOTTOM_LEFT_TITLE_BLOCK = pt.Rect(10, 10, 710, 190)

    def test_bottom_left_title_block_gives_right_and_top_left_regions(self):
        template = pt.PageTemplate.from_dict(
            pt.build_template_document(
                MEASURED_PAGE,
                {"rect": rect_dict(self.BOTTOM_LEFT_TITLE_BLOCK), "visible": True},
            )
        )
        self.assertEqual(template.title_block_corner, "bottom-left")
        self.assertEqual(template.title_block_rect, self.BOTTOM_LEFT_TITLE_BLOCK)
        self.assertEqual(template.region_names(), ("right", "top-left"))
        self.assertEqual(template.region("right").rect, pt.Rect(710, 10, 1160, 815))
        self.assertEqual(template.region("top-left").rect, pt.Rect(10, 190, 710, 815))
        self.assertFalse(template.title_block_hit(template.region("right").rect))
        self.assertFalse(template.title_block_hit(template.region("top-left").rect))
        self.assertEqual(template.region_of(pt.Rect(800, 300, 900, 400)), "right")
        self.assertEqual(template.region_of(pt.Rect(100, 300, 200, 400)), "top-left")
        self.assertIsNone(template.region_of(pt.Rect(500, 50, 600, 100)))

    def test_bottom_left_corner_can_be_explicit_in_data(self):
        document = pt.build_template_document(
            MEASURED_PAGE,
            {"rect": rect_dict(self.BOTTOM_LEFT_TITLE_BLOCK), "corner": "bottom-left"},
        )
        self.assertEqual(document["title_block"]["corner"], "bottom-left")
        template = self.write_and_load(document)
        self.assertEqual(template.title_block_corner, "bottom-left")
        self.assertEqual(template.region_names(), ("right", "top-left"))

    def test_bottom_left_template_roundtrips_through_json(self):
        document = pt.build_template_document(
            MEASURED_PAGE, {"rect": rect_dict(self.BOTTOM_LEFT_TITLE_BLOCK)}
        )
        template = self.write_and_load(document)
        self.assertEqual(template.title_block_corner, "bottom-left")
        self.assertEqual(
            [region.name for region in template.computed_regions()],
            ["right", "top-left"],
        )

    def test_explicit_corner_disagreeing_with_geometry_is_blocked(self):
        with self.assertRaisesRegex(pt.TemplateError, "disagrees"):
            pt.build_template_document(
                MEASURED_PAGE,
                {
                    "rect": rect_dict(self.BOTTOM_LEFT_TITLE_BLOCK),
                    "corner": "bottom-right",
                },
            )
        document = self.base_document()
        document["title_block"]["rect"] = rect_dict(self.BOTTOM_LEFT_TITLE_BLOCK)
        self.assert_blocked(document, "disagrees")

    def test_top_title_block_is_rejected(self):
        with self.assertRaisesRegex(pt.TemplateError, "unsupported title block corner"):
            pt.build_template_document(
                MEASURED_PAGE,
                {"rect": rect_dict(pt.Rect(460, 635, 1160, 815))},
            )


class ContractShapeTests(unittest.TestCase):
    """The contract sample shape (margin 12, title block extending to page edge)."""

    def test_contract_sample_rects_are_clipped_to_usable_area(self):
        document = pt.build_template_document(
            {"width": 1170, "height": 825, "margin": 12},
            {"rect": {"minX": 610, "minY": 12, "maxX": 1170, "maxY": 380}},
        )
        template = pt.PageTemplate.from_dict(document)
        self.assertEqual(template.inner_border, pt.Rect(12, 12, 1158, 813))
        self.assertEqual(template.title_block_corner, "bottom-right")
        self.assertEqual(template.region("left").rect, pt.Rect(12, 12, 610, 813))
        self.assertEqual(template.region("top-right").rect, pt.Rect(610, 380, 1158, 813))
        self.assertFalse(template.title_block_hit(template.region("top-right").rect))

    def test_built_measured_template_matches_asset(self):
        built = pt.build_template_document(
            MEASURED_PAGE,
            {"rect": rect_dict(MEASURED_TITLE_BLOCK), "visible": True},
        )
        asset = read_asset_document()
        for key in ("page", "inner_border", "title_block", "regions"):
            self.assertEqual(built[key], asset[key], key)
        self.assertNotIn("provenance", built)

    def test_contract_title_block_provenance_is_preserved(self):
        document = pt.build_template_document(
            {"width": 1170, "height": 825, "margin": 12},
            {
                "rect": {"minX": 610, "minY": 12, "maxX": 1170, "maxY": 380},
                "provenance": "sch sheet-geometry",
            },
        )
        self.assertEqual(document["title_block"]["provenance"], "sch sheet-geometry")
        template = pt.PageTemplate.from_dict(document)
        self.assertEqual(
            template.to_dict()["title_block"]["provenance"], "sch sheet-geometry"
        )


class ValidationTests(TemplateFixtureMixin):
    def test_wrong_schema_is_blocked(self):
        document = self.base_document()
        document["schema"] = "easycirq-page-template/v2"
        self.assert_blocked(document, "schema: expected")

    def test_missing_required_top_level_fields_are_blocked(self):
        for field in ("schema", "page", "title_block"):
            with self.subTest(field=field):
                document = self.base_document()
                del document[field]
                self.assert_blocked(document, "missing required field %r" % field)

    def test_missing_title_block_rect_is_blocked(self):
        document = self.base_document()
        del document["title_block"]["rect"]
        self.assert_blocked(document, "missing required field 'rect'")

    def test_non_positive_page_sizes_are_blocked(self):
        for field, value in (("width", 0), ("height", -825)):
            with self.subTest(field=field):
                document = self.base_document()
                document["page"][field] = value
                self.assert_blocked(document, "page.%s" % field)
        document = self.base_document()
        document["page"]["width"] = "1170"
        self.assert_blocked(document, "expected a finite number")

    def test_non_finite_number_is_blocked(self):
        document = self.base_document()
        document["page"]["width"] = float("nan")
        text = json.dumps(document, indent=1)  # emits NaN, accepted by json.loads
        with self.assertRaisesRegex(pt.TemplateError, "finite number"):
            pt.load_template(self._write_text(text))

    def _write_text(self, text):
        handle = tempfile.NamedTemporaryFile(
            "w", suffix=".json", delete=False, encoding="utf-8"
        )
        try:
            handle.write(text)
        finally:
            handle.close()
        self.addCleanup(lambda: Path(handle.name).unlink(missing_ok=True))
        return Path(handle.name)

    def test_margin_too_large_is_blocked(self):
        document = self.base_document()
        document["page"]["margin"] = 500
        self.assert_blocked(document, "too large")

    def test_inner_border_disagreeing_with_margin_is_blocked(self):
        document = self.base_document()
        document["page"]["margin"] = 12
        self.assert_blocked(document, "disagrees with page.margin")

    def test_title_block_outside_page_is_blocked(self):
        document = self.base_document()
        document["title_block"]["rect"]["maxX"] = 1200
        self.assert_blocked(document, "extends outside the page")

    def test_empty_regions_list_is_blocked(self):
        document = self.base_document()
        document["regions"] = []
        self.assert_blocked(document, "non-empty list")

    def test_region_intersecting_title_block_is_blocked(self):
        document = self.base_document()
        document["regions"] = [
            {"name": "left", "rect": {"minX": 10, "minY": 10, "maxX": 600, "maxY": 190}}
        ]
        self.assert_blocked(document, "intersects the title block keep-out")

    def test_region_outside_usable_area_is_blocked(self):
        document = self.base_document()
        document["regions"] = [
            {"name": "left", "rect": {"minX": 0, "minY": 0, "maxX": 100, "maxY": 100}}
        ]
        self.assert_blocked(document, "outside the usable page area")

    def test_overlapping_regions_are_blocked(self):
        document = self.base_document()
        document["regions"] = [
            {"name": "left", "rect": rect_dict(MEASURED_LEFT)},
            {"name": "corner", "rect": {"minX": 10, "minY": 10, "maxX": 300, "maxY": 400}},
        ]
        self.assert_blocked(document, "overlap")

    def test_unknown_fields_are_blocked(self):
        document = self.base_document()
        document["mystery"] = 1
        self.assert_blocked(document, "unknown field")
        document = self.base_document()
        document["title_block"]["mystery"] = 1
        self.assert_blocked(document, "unknown field")
        document = self.base_document()
        document["regions"][0]["mystery"] = 1
        self.assert_blocked(document, "unknown field")

    def test_corner_field_must_be_a_supported_string(self):
        document = self.base_document()
        document["title_block"]["corner"] = 5
        self.assert_blocked(document, "non-empty string")
        document = self.base_document()
        document["title_block"]["corner"] = "bottom-middle"
        self.assert_blocked(document, "unsupported title block corner")

    def test_invalid_json_and_missing_file_are_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            broken = Path(tmp) / "broken.json"
            broken.write_text("{ not json", encoding="utf-8")
            with self.assertRaisesRegex(pt.TemplateError, "invalid JSON at line 1"):
                pt.load_template(broken)
            with self.assertRaisesRegex(pt.TemplateError, "cannot read page template"):
                pt.load_template(Path(tmp) / "absent.json")

    def test_notes_must_be_strings(self):
        document = self.base_document()
        document["notes"] = [1]
        self.assert_blocked(document, "expected a string")

    def test_title_block_spanning_full_width_is_blocked(self):
        document = self.base_document()
        document["title_block"]["rect"] = {
            "minX": 10,
            "minY": 10,
            "maxX": 1160,
            "maxY": 190,
        }
        self.assert_blocked(document, "derived region 'left' is empty")

    def test_template_error_is_a_value_error(self):
        self.assertTrue(issubclass(pt.TemplateError, ValueError))


if __name__ == "__main__":
    unittest.main()
