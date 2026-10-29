"""Offline tests for the freeform (L-shaped page) layout planner.

No EDA, no daemon, no network: every fixture is a plain dict and the planner is
expected to place the modules or explicitly report them unplaced.
"""

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.layout2 import freeform  # noqa: E402

DEFAULT_PAGE = {"width": 1170, "height": 825, "margin": 10}
DEFAULT_TB = {"rect": [460, 10, 1160, 190]}
USABLE = [10, 10, 1160, 815]
TITLE_BLOCK = [460, 10, 1160, 190]


def module(module_id, w=350, h=220, **extra):
    entry = {"id": module_id, "title": module_id, "w": w, "h": h}
    entry.update(extra)
    return entry


def project(*modules, **extra):
    plan = {"name": "freeform-test", "modules": list(modules)}
    plan.update(extra)
    return plan


def area(rect):
    return (rect[2] - rect[0]) * (rect[3] - rect[1])


def intersects(first, second):
    return (first[0] < second[2] and second[0] < first[2]
            and first[1] < second[3] and second[1] < first[3])


def rect_gap(first, second):
    """Chebyshev gap between two disjoint rectangles."""
    if intersects(first, second):
        return 0.0
    dx = max(second[0] - first[2], first[0] - second[2])
    dy = max(second[1] - first[3], first[1] - second[3])
    return max(dx, dy)


def dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


class RectGeometryTests(unittest.TestCase):
    def test_subtract_rect_corner_hole_leaves_l_shape(self):
        pieces = freeform.subtract_rect(USABLE, TITLE_BLOCK)
        self.assertEqual(len(pieces), 2)
        self.assertAlmostEqual(sum(area(piece) for piece in pieces),
                               area(USABLE) - area(TITLE_BLOCK))
        for piece in pieces:
            self.assertFalse(intersects(piece, TITLE_BLOCK))
            self.assertTrue(freeform.rect_contains(USABLE, piece))

    def test_subtract_rect_interior_hole_splits_four_ways(self):
        pieces = freeform.subtract_rect([0, 0, 100, 100], [20, 20, 80, 80])
        self.assertEqual(len(pieces), 4)
        self.assertAlmostEqual(sum(area(piece) for piece in pieces),
                               100 * 100 - 60 * 60)

    def test_subtract_rect_full_and_disjoint_holes(self):
        self.assertEqual(freeform.subtract_rect([0, 0, 10, 10],
                                                [0, 0, 10, 10]), [])
        self.assertEqual(freeform.subtract_rect([0, 0, 10, 10],
                                                [20, 20, 30, 30]),
                         [[0, 0, 10, 10]])

    def test_build_regions_from_default_page(self):
        regions = freeform.build_regions(DEFAULT_PAGE, DEFAULT_TB)
        self.assertEqual(len(regions), 2)
        self.assertEqual([entry["name"] for entry in regions],
                         ["region-1", "region-2"])
        self.assertEqual(regions[0]["rect"], [10.0, 10.0, 460.0, 815.0])
        self.assertEqual(regions[1]["rect"], [460.0, 190.0, 1160.0, 815.0])
        self.assertAlmostEqual(sum(area(entry["rect"]) for entry in regions),
                               area(USABLE) - area(TITLE_BLOCK))
        for entry in regions:
            self.assertFalse(intersects(entry["rect"], TITLE_BLOCK))
            self.assertTrue(freeform.rect_contains(USABLE, entry["rect"]))
        for i in range(len(regions)):
            for j in range(i + 1, len(regions)):
                self.assertFalse(intersects(regions[i]["rect"],
                                            regions[j]["rect"]))

    def test_build_regions_without_title_block(self):
        regions = freeform.build_regions(DEFAULT_PAGE, None)
        self.assertEqual(regions, [{"name": "page", "rect": [10.0, 10.0,
                                                             1160.0, 815.0]}])

    def test_usable_rect_respects_margin(self):
        self.assertEqual(freeform.usable_rect(DEFAULT_PAGE),
                         [10.0, 10.0, 1160.0, 815.0])


class PackingTests(unittest.TestCase):
    def test_first_fit_over_free_rects_uses_split_remainder(self):
        regions = [{"name": "strip", "rect": [0, 0, 200, 100]}]
        result = freeform.place_modules(
            [module("a", 90, 90), module("b", 90, 90)], regions, 5)
        self.assertEqual([entry["id"] for entry in result["placements"]],
                         ["a", "b"])
        self.assertEqual(result["unplaced"], [])
        first, second = result["placements"]
        self.assertEqual(first["bbox"], [0.0, 0.0, 90.0, 90.0])
        self.assertEqual(second["bbox"], [95.0, 0.0, 185.0, 90.0])

    def test_area_descending_ordering(self):
        modules = [module("small", 100, 100), module("large", 400, 300),
                   module("medium", 200, 150)]
        result = freeform.place_modules(
            modules, [{"rect": [0, 0, 900, 700]}], 6)
        self.assertEqual([entry["id"] for entry in result["placements"]],
                         ["large", "medium", "small"])

    def test_too_large_module_is_unplaced(self):
        result = freeform.place_modules(
            [module("big", 800, 800), module("small", 100, 100)],
            [{"rect": [0, 0, 500, 500]}], 6)
        self.assertEqual([entry["id"] for entry in result["placements"]],
                         ["small"])
        self.assertEqual(result["unplaced"], ["big"])

    def test_invalid_modules_raise(self):
        regions = [{"rect": [0, 0, 100, 100]}]
        cases = [
            [{"id": "a", "w": 0, "h": 10}],
            [{"id": "a", "w": 10, "h": 10, "halo": -1}],
            [{"id": "a", "w": 10, "h": 10},
             {"id": "a", "w": 10, "h": 10}],
            [{"id": "", "w": 10, "h": 10}],
        ]
        for modules in cases:
            with self.subTest(modules=modules):
                with self.assertRaises(freeform.FreeformError):
                    freeform.place_modules(modules, regions, 0)


class PlanTests(unittest.TestCase):
    def test_l_shape_fits_three_modules_on_one_page(self):
        plan = freeform.plan_project_freeform(
            project(module("a"), module("b"), module("c")))
        self.assertEqual(plan["schema"], freeform.SCHEMA)
        self.assertEqual(plan["verdict"], "pass")
        self.assertEqual(plan["unplaced"], [])
        self.assertEqual(plan["findings"], [])
        self.assertEqual(plan["metrics"]["fits"], 3)
        self.assertEqual([block["id"] for block in plan["blocks"]],
                         ["a", "b", "c"])
        self.assertEqual(len(plan["zones"]), 3)
        self.assertEqual(plan["page"]["width"], 1170)
        regions = plan["regions"]
        for block in plan["blocks"]:
            self.assertTrue(any(freeform.rect_contains(entry["rect"],
                                                       block["bbox"])
                                for entry in regions))
            self.assertTrue(block["zone"])
            for zone_rect in block["zone"]:
                self.assertTrue(any(freeform.rect_contains(entry["rect"],
                                                           zone_rect)
                                    for entry in regions))
            self.assertFalse(intersects(block["bbox"], TITLE_BLOCK))
            self.assertIn(block["zone_kind"], ("rect", "union"))
        for i in range(len(plan["blocks"])):
            for j in range(i + 1, len(plan["blocks"])):
                self.assertFalse(intersects(plan["blocks"][i]["bbox"],
                                            plan["blocks"][j]["bbox"]))
        metrics = plan["metrics"]
        self.assertEqual(metrics["overlaps"], 0)
        self.assertEqual(metrics["title_block_hits"], 0)
        self.assertGreater(metrics["page_utilization"], 0.2)
        self.assertLessEqual(metrics["page_utilization"], 1.0)
        self.assertGreater(metrics["zone_fill"], 0.0)
        self.assertLessEqual(metrics["zone_fill"], 1.0)
        json.dumps(plan)  # the plan must stay JSON-serializable

    def test_too_large_module_blocks_the_plan(self):
        plan = freeform.plan_project_freeform(
            project(module("huge", 1200, 900)))
        self.assertEqual(plan["verdict"], "blocked")
        self.assertEqual(plan["unplaced"], ["huge"])
        self.assertEqual(plan["blocks"], [])
        self.assertEqual(plan["metrics"]["fits"], 0)
        self.assertEqual(plan["metrics"]["page_utilization"], 0.0)
        self.assertEqual([finding["code"] for finding in plan["findings"]],
                         ["module_does_not_fit"])
        self.assertEqual(plan["findings"][0]["id"], "huge")

    def test_title_block_area_is_never_used(self):
        plan = freeform.plan_project_freeform(
            project(module("wide", 700, 200), module("small", 300, 150),
                    module("tall", 300, 300)))
        self.assertEqual(plan["verdict"], "pass")
        self.assertEqual(plan["metrics"]["title_block_hits"], 0)
        for block in plan["blocks"]:
            self.assertFalse(intersects(block["bbox"], TITLE_BLOCK))
            self.assertFalse(intersects(block["footprint"], TITLE_BLOCK))
            for zone_rect in block["zone"]:
                self.assertFalse(intersects(zone_rect, TITLE_BLOCK))
        for entry in plan["regions"]:
            self.assertFalse(intersects(entry["rect"], TITLE_BLOCK))

    def test_rect_union_zone_near_l_corner(self):
        plan = freeform.plan_project_freeform(
            project(module("wide", 700, 200), module("small", 300, 150)))
        self.assertEqual(plan["verdict"], "pass")
        wide = next(block for block in plan["blocks"]
                    if block["id"] == "wide")
        # the L corner is (460, 190): the wide module sits exactly there and
        # its zone crosses the region split, so it must be a rectangle union
        self.assertEqual(wide["bbox"], [460.0, 190.0, 1160.0, 390.0])
        self.assertEqual(wide["zone_kind"], "union")
        self.assertGreater(len(wide["zone"]), 1)
        expanded = [wide["footprint"][0] - 4, wide["footprint"][1] - 4,
                    wide["footprint"][2] + 4, wide["footprint"][3] + 4]
        zone_area = 0.0
        for zone_rect in wide["zone"]:
            self.assertTrue(freeform.rect_contains(expanded, zone_rect))
            self.assertFalse(intersects(zone_rect, TITLE_BLOCK))
            zone_area += area(zone_rect)
        self.assertGreater(zone_area, area(wide["footprint"]))
        self.assertLess(zone_area, area(expanded))
        # ordinary zones stay single rectangles
        small = next(block for block in plan["blocks"]
                     if block["id"] == "small")
        self.assertEqual(small["zone_kind"], "rect")
        self.assertEqual(len(small["zone"]), 1)

    def test_halo_is_respected(self):
        halo = 12
        plan = freeform.plan_project_freeform(
            project(module("a", 300, 200, halo=halo),
                    module("b", 300, 200, halo=halo)))
        self.assertEqual(plan["verdict"], "pass")
        first, second = sorted(plan["blocks"], key=lambda block: block["id"])
        for block in (first, second):
            footprint = block["footprint"]
            bbox = block["bbox"]
            self.assertEqual(bbox[0], footprint[0] + halo)
            self.assertEqual(bbox[1], footprint[1] + halo)
            self.assertEqual(bbox[2], footprint[2] - halo)
            self.assertEqual(bbox[3], footprint[3] - halo)
            self.assertTrue(any(freeform.rect_contains(zone_rect, footprint)
                                for zone_rect in block["zone"]))
        gap = rect_gap(second["footprint"], first["footprint"])
        self.assertGreaterEqual(gap, 6.0)  # options.gap
        # the footprint spacing plus both halos separates the visible bboxes
        bbox_gap = rect_gap(second["bbox"], first["bbox"])
        self.assertGreaterEqual(bbox_gap, 2 * halo)

    def test_per_module_min_gap_is_respected(self):
        plan = freeform.plan_project_freeform(
            project(module("a", 300, 200, min_gap=40),
                    module("b", 300, 200)))
        self.assertEqual(plan["verdict"], "pass")
        first, second = sorted(plan["blocks"], key=lambda block: block["id"])
        gap = second["footprint"][1] - first["footprint"][3]
        self.assertGreaterEqual(gap, 40.0)

    def test_plan_is_deterministic_and_input_order_independent(self):
        modules = [module("z%d" % index) for index in range(5)]
        first = freeform.plan_project_freeform(project(*modules))
        second = freeform.plan_project_freeform(
            copy.deepcopy(project(*modules)))
        third = freeform.plan_project_freeform(project(*reversed(modules)))
        self.assertEqual(dump(first), dump(second))
        self.assertEqual(dump(first), dump(third))

    def test_metrics_are_consistent_with_geometry(self):
        plan = freeform.plan_project_freeform(
            project(module("a"), module("b"), module("c")))
        metrics = plan["metrics"]
        block_area = sum(area(block["bbox"]) for block in plan["blocks"])
        zone_area = sum(area(rect) for block in plan["blocks"]
                        for rect in block["zone"])
        usable_area = area(USABLE) - area(TITLE_BLOCK)
        self.assertAlmostEqual(metrics["page_utilization"],
                               round(block_area / usable_area, 4), places=4)
        self.assertAlmostEqual(metrics["zone_fill"],
                               round(block_area / zone_area, 4), places=4)

    def test_no_title_block_uses_the_whole_page(self):
        plan = freeform.plan_project_freeform(
            {"modules": [module("a")], "title_block": None})
        self.assertEqual(plan["verdict"], "pass")
        self.assertEqual(plan["title_block"], None)
        self.assertEqual(len(plan["regions"]), 1)
        self.assertEqual(plan["regions"][0]["rect"], [10.0, 10.0,
                                                      1160.0, 815.0])
        self.assertFalse(intersects(plan["blocks"][0]["bbox"], TITLE_BLOCK))

    def test_custom_page_and_options(self):
        plan = freeform.plan_project_freeform({
            "page": {"width": 800, "height": 600, "margin": 20},
            "title_block": None,
            "options": {"gap": 12, "zone_pad": 3},
            "modules": [module("a", 300, 200), module("b", 300, 200)],
        })
        self.assertEqual(plan["verdict"], "pass")
        self.assertEqual(plan["page"],
                         {"width": 800.0, "height": 600.0, "margin": 20.0})
        self.assertEqual(plan["regions"][0]["rect"],
                         [20.0, 20.0, 780.0, 580.0])
        first, second = plan["blocks"][:2]
        gap = rect_gap(second["footprint"], first["footprint"])
        self.assertGreaterEqual(gap, 12.0)

    def test_invalid_projects_are_blocked(self):
        cases = [None, "not-a-project", {}, {"modules": []},
                 {"modules": {}},
                 {"modules": [{"id": "a", "w": 10, "h": 10},
                              {"id": "a", "w": 10, "h": 10}]},
                 {"modules": [{"id": "a", "w": 0, "h": 10}]},
                 {"modules": [{"id": "a", "w": 10, "h": 10, "halo": -2}]},
                 {"modules": [{"id": "a", "w": 10, "h": 10}],
                  "page": {"width": 100, "height": 100, "margin": 60}},
                 {"modules": [{"id": "a", "w": 10, "h": 10}],
                  "title_block": {"rect": [10, 10, 5, 5]}}]
        for value in cases:
            with self.subTest(project=value):
                plan = freeform.plan_project_freeform(value)
                self.assertEqual(plan["verdict"], "blocked")
                self.assertEqual(plan["blocks"], [])
                self.assertEqual(plan["unplaced"], [])
                self.assertEqual(plan["findings"][0]["code"],
                                 "invalid_project")
                self.assertEqual(plan["metrics"],
                                 {"fits": 0, "overlaps": 0,
                                  "title_block_hits": 0,
                                  "page_utilization": 0.0,
                                  "zone_fill": 0.0})


if __name__ == "__main__":
    unittest.main()
