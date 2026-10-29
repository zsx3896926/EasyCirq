"""Offline tests for the layout v2 engine orchestrator.

No EDA, no daemon, no network: every fixture is a plain dict and the engine is
expected to fully plan or explicitly block it.
"""

import copy
import json
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.layout2 import layout_engine  # noqa: E402

DEFAULT_TB = [460, 10, 1160, 190]
DEFAULT_USABLE = [10, 10, 1160, 815]
DEFAULT_USABLE_AREA = 1150 * 805 - 700 * 180   # page minus margin minus TB

# Zone geometry of a 350x220 module with the default halo/padding:
#   350 + 22 + 22 + 2*4 = 402 wide; 20 + 16 + 220 + 10 + 2*4 = 274 high.
ZONE_W = 402
ZONE_H = 274


def module(module_id, w=350, h=220, title=None, **extra):
    entry = {"id": module_id, "title": title or module_id, "w": w, "h": h}
    entry.update(extra)
    return entry


def project(*modules, **extra):
    plan = {"name": "test-project", "modules": list(modules)}
    plan.update(extra)
    return plan


def intersects(first, second):
    return (first[0] < second[2] and second[0] < first[2]
            and first[1] < second[3] and second[1] < first[3])


def area(rect):
    return (rect[2] - rect[0]) * (rect[3] - rect[1])


def dump(plan):
    return json.dumps(plan, ensure_ascii=False, sort_keys=True)


class LayoutEngineTests(unittest.TestCase):

    # -- normal paths -------------------------------------------------------

    def test_default_template_geometry(self):
        plan = layout_engine.plan_project(project(module("only")))
        self.assertEqual(plan["verdict"], "pass")
        template = plan["template"]
        self.assertEqual(template["page"]["width"], 1170)
        self.assertEqual(template["page"]["height"], 825)
        self.assertEqual(template["page"]["margin"], 10)
        self.assertEqual(template["title_block"]["rect"], DEFAULT_TB)
        self.assertEqual(template["usable"], DEFAULT_USABLE)
        self.assertEqual(template["usable_area"], DEFAULT_USABLE_AREA)
        self.assertEqual([region["name"] for region in template["regions"]],
                         ["left", "top-right"])
        self.assertEqual(template["regions"][0]["rect"], [10, 10, 454, 190])
        self.assertEqual(template["regions"][1]["rect"], [10, 196, 1160, 815])

    def test_three_modules_single_page_passes(self):
        plan = layout_engine.plan_project(
            project(module("a"), module("b"), module("c")))
        self.assertEqual(plan["schema"], "easycirq-sch-layout-v2/v1")
        self.assertEqual(plan["verdict"], "pass")
        self.assertEqual(plan["findings"], [])
        self.assertEqual(plan["metrics"]["page_count"], 1)
        self.assertEqual(len(plan["pages"]), 1)
        page = plan["pages"][0]
        self.assertEqual(page["validator"]["verdict"], "pass")
        self.assertEqual([block["id"] for block in page["blocks"]],
                         ["a", "b", "c"])
        self.assertEqual([frame["id"] for frame in page["frames"]],
                         ["a", "b", "c"])
        self.assertEqual(len(page["labels"]), 3)
        self.assertEqual(layout_engine.validate_page(page)["verdict"], "pass")
        for zone in (frame["zone"] for frame in page["frames"]):
            self.assertEqual(zone[2] - zone[0], ZONE_W)
            self.assertEqual(zone[3] - zone[1], ZONE_H)

    def test_six_modules_split_across_two_pages(self):
        modules = [module("z%d" % index) for index in range(6)]
        plan = layout_engine.plan_project(project(*modules))
        self.assertEqual(plan["verdict"], "pass")
        self.assertEqual(plan["metrics"]["page_count"], 2)
        self.assertEqual(len(plan["pages"]), 2)
        placed = [block["id"] for page in plan["pages"]
                  for block in page["blocks"]]
        self.assertEqual(sorted(placed), [entry["id"] for entry in modules])
        for page in plan["pages"]:
            self.assertTrue(page["blocks"])
            self.assertEqual(page["validator"]["verdict"], "pass")
            self.assertEqual(layout_engine.validate_page(page)["verdict"],
                             "pass")

    def test_wide_module_moves_below_title_block(self):
        plan = layout_engine.plan_project(
            project(module("wide", 550, 220), module("a"), module("b")))
        self.assertEqual(plan["verdict"], "pass")
        page = plan["pages"][0]
        wide = next(block for block in page["blocks"]
                    if block["id"] == "wide")
        # A 550-wide module cannot use the 444-wide bottom-left strip, so it must be
        # placed in the full-width top strip, i.e. above the title block keep-out.
        self.assertGreaterEqual(wide["zone"][1], 196)
        self.assertGreaterEqual(wide["bbox"][1], 190)
        self.assertGreaterEqual(wide["zone"][1], 190)
        self.assertFalse(intersects(wide["zone"], DEFAULT_TB))
        self.assertEqual(plan["metrics"]["title_block_hits"], 0)
        for block in page["blocks"]:
            self.assertFalse(intersects(block["zone"], DEFAULT_TB))

    def test_affinity_group_stays_on_one_page(self):
        modules = []
        for group in ("power", "audio"):
            modules.extend(module("%s-%d" % (group, index),
                                  affinity_group=group)
                           for index in range(3))
        plan = layout_engine.plan_project(project(*modules))
        self.assertEqual(plan["verdict"], "pass")
        self.assertEqual(plan["metrics"]["page_count"], 2)
        pages_by_group = {}
        for page in plan["pages"]:
            for block in page["blocks"]:
                group = block["id"].split("-")[0]
                pages_by_group.setdefault(group, set()).add(page["page"])
        self.assertEqual(pages_by_group, {"power": {1}, "audio": {2}})

    def test_halo_is_inside_zone_and_labels_inside_frames(self):
        halo = {"left": 40, "right": 8, "top": 30, "bottom": 5}
        plan = layout_engine.plan_project(
            project(module("haloed", 350, 220, halo=halo), module("plain")))
        self.assertEqual(plan["verdict"], "pass")
        page = plan["pages"][0]
        haloed = next(block for block in page["blocks"]
                      if block["id"] == "haloed")
        zone = haloed["zone"]
        self.assertEqual(zone[2] - zone[0], 350 + 40 + 8 + 2 * 4)
        self.assertEqual(zone[3] - zone[1], 20 + 30 + 220 + 5 + 2 * 4)
        bbox = haloed["bbox"]
        self.assertGreaterEqual(bbox[0] - halo["left"], zone[0])
        self.assertGreaterEqual(bbox[1] - halo["top"], zone[1])
        self.assertLessEqual(bbox[2] + halo["right"], zone[2])
        self.assertLessEqual(bbox[3] + halo["bottom"], zone[3])
        zones_by_frame = {frame["id"]: frame["zone"]
                          for frame in page["frames"]}
        for label in page["labels"]:
            frame_zone = zones_by_frame[label["frame"]]
            self.assertGreaterEqual(label["bbox"][0], frame_zone[0])
            self.assertGreaterEqual(label["bbox"][1], frame_zone[1])
            self.assertLessEqual(label["bbox"][2], frame_zone[2])
            self.assertLessEqual(label["bbox"][3], frame_zone[3])
            for block in page["blocks"]:
                self.assertFalse(intersects(label["bbox"], block["bbox"]))

    def test_labels_can_be_disabled(self):
        plan = layout_engine.plan_project(project(module("a")),
                                          place_labels=False)
        self.assertEqual(plan["verdict"], "pass")
        self.assertEqual(plan["pages"][0]["labels"], [])
        self.assertEqual(plan["metrics"]["label_collisions"], 0)

    def test_custom_template_fits_more_modules(self):
        template = {
            "schema": "easycirq-page-template/v1",
            "page": {"width": 1600, "height": 1000, "margin": 10},
            "title_block": {"rect": {"minX": 600, "minY": 10,
                                     "maxX": 1590, "maxY": 100}},
        }
        modules = [module("z%d" % index) for index in range(6)]
        plan = layout_engine.plan_project(project(*modules), template)
        self.assertEqual(plan["verdict"], "pass")
        self.assertEqual(plan["metrics"]["page_count"], 1)
        self.assertEqual(plan["template"]["regions"][0]["rect"],
                         [10, 10, 594, 100])
        self.assertEqual(plan["template"]["regions"][1]["rect"],
                         [10, 106, 1590, 990])

    # -- blocked paths ------------------------------------------------------

    def test_oversized_modules_are_blocked(self):
        cases = {
            # 550 wide -> top-right strip; 20+16+580+10+8 = 634 > 619 high.
            "too-tall": module("too-tall", 550, 580),
            # A halo that no region can absorb.
            "long-halo": module("long-halo", 250, 200,
                                halo={"top": 600}),
        }
        for name, entry in cases.items():
            with self.subTest(name=name):
                plan = layout_engine.plan_project(project(entry))
                self.assertEqual(plan["schema"],
                                 "easycirq-sch-layout-v2/v1")
                self.assertEqual(plan["verdict"], "blocked")
                self.assertEqual(plan["pages"], [])
                self.assertEqual(plan["metrics"]["page_count"], 0)
                codes = {finding["code"] for finding in plan["findings"]}
                self.assertIn("module_does_not_fit", codes)

    def test_invalid_projects_are_blocked(self):
        cases = [
            ("none", None),
            ("string", "not-a-project"),
            ("no-modules-key", {"name": "x"}),
            ("empty-modules", {"modules": []}),
            ("modules-not-list", {"modules": {}}),
        ]
        for name, value in cases:
            with self.subTest(name=name):
                plan = layout_engine.plan_project(value)
                self.assertEqual(plan["verdict"], "blocked")
                self.assertEqual(plan["pages"], [])
                self.assertEqual(plan["metrics"]["page_count"], 0)
                self.assertTrue(plan["findings"])

        module_cases = [
            ("duplicate-id", [module("dup"), module("dup")], "duplicate_id"),
            ("zero-width", [{"id": "x", "w": 0, "h": 10}],
             "invalid_module"),
            ("negative-halo", [module("x", halo={"left": -1})],
             "invalid_module"),
            ("bad-title", [{"id": "x", "title": 7, "w": 10, "h": 10}],
             "invalid_module"),
            ("bad-affinity", [module("x", affinity_group=5)],
             "invalid_module"),
            ("not-an-object", ["nope"], "invalid_module"),
        ]
        for name, entries, code in module_cases:
            with self.subTest(name=name):
                plan = layout_engine.plan_project({"modules": entries})
                self.assertEqual(plan["verdict"], "blocked")
                self.assertEqual(plan["pages"], [])
                self.assertIn(code,
                              {finding["code"]
                               for finding in plan["findings"]})

    def test_invalid_templates_are_blocked(self):
        cases = [
            ("margin-eats-page",
             {"page": {"width": 100, "height": 100, "margin": 60}}),
            ("no-page", {"title_block": {"rect": [0, 0, 10, 10]}}),
            ("bad-title-block",
             {"page": {"width": 500, "height": 500, "margin": 10},
              "title_block": {"rect": [10, 10, 5, 5]}}),
            ("outside-title-block",
             {"page": {"width": 500, "height": 500, "margin": 10},
              "title_block": {"rect": [400, 400, 700, 700]}}),
            ("not-an-object", "nope"),
        ]
        for name, template in cases:
            with self.subTest(name=name):
                plan = layout_engine.plan_project(project(module("a")),
                                                  template)
                self.assertEqual(plan["verdict"], "blocked")
                self.assertEqual(plan["pages"], [])
                codes = {finding["code"] for finding in plan["findings"]}
                self.assertIn("invalid_template", codes)

    def test_validator_catches_title_block_zone(self):
        plan = layout_engine.plan_project(project(module("a")))
        page = copy.deepcopy(plan["pages"][0])
        frame = page["frames"][0]
        block = page["blocks"][0]
        frame["zone"] = [500, 10, 900, 300]
        block["zone"] = list(frame["zone"])
        block["bbox"] = [526, 50, 876, 270]
        result = layout_engine.validate_page(page)
        self.assertEqual(result["verdict"], "blocked")
        codes = {finding["code"] for finding in result["findings"]}
        self.assertIn("title_block_hit", codes)

    def test_validator_catches_block_overlap(self):
        plan = layout_engine.plan_project(
            project(module("a"), module("b")))
        page = copy.deepcopy(plan["pages"][0])
        page["blocks"][1]["bbox"] = list(page["blocks"][0]["bbox"])
        result = layout_engine.validate_page(page)
        self.assertEqual(result["verdict"], "blocked")
        codes = {finding["code"] for finding in result["findings"]}
        self.assertIn("block_overlap", codes)

    # -- determinism / metrics / fallback -----------------------------------

    def test_output_is_deterministic(self):
        modules = [module("z%d" % index) for index in range(6)]
        first = layout_engine.plan_project(project(*modules))
        second = layout_engine.plan_project(copy.deepcopy(project(*modules)))
        third = layout_engine.plan_project(project(*modules))
        self.assertEqual(dump(first), dump(second))
        self.assertEqual(dump(first), dump(third))
        self.assertEqual(first["verdict"], "pass")

    def test_metrics_shape_and_consistency(self):
        plan = layout_engine.plan_project(
            project(module("a"), module("b"), module("c")))
        metrics = plan["metrics"]
        required = {"page_count", "page_utilization", "zone_fill",
                    "label_collisions", "block_overlaps",
                    "title_block_hits"}
        self.assertTrue(required.issubset(metrics))
        self.assertEqual(metrics["page_count"], len(plan["pages"]))
        self.assertEqual(metrics["label_collisions"], 0)
        self.assertEqual(metrics["block_overlaps"], 0)
        self.assertEqual(metrics["title_block_hits"], 0)
        self.assertGreater(metrics["page_utilization"], 0.0)
        self.assertLessEqual(metrics["page_utilization"], 1.0)
        self.assertGreaterEqual(metrics["zone_fill"], 0.55)
        self.assertLessEqual(metrics["zone_fill"], 0.85)
        self.assertGreaterEqual(metrics["whitespace_balance"], 0.0)

        blocks = [block for page in plan["pages"]
                  for block in page["blocks"]]
        zones = [frame for page in plan["pages"]
                 for frame in page["frames"]]
        expected_zone_fill = (sum(area(block["bbox"]) for block in blocks)
                              / sum(area(frame["zone"]) for frame in zones))
        self.assertAlmostEqual(metrics["zone_fill"], expected_zone_fill,
                               places=3)
        expected_utilization = (sum(area(block["bbox"]) for block in blocks)
                                / DEFAULT_USABLE_AREA)
        self.assertAlmostEqual(metrics["page_utilization"],
                               expected_utilization, places=3)

    def test_missing_sibling_modules_fall_back(self):
        self.assertIsNone(
            layout_engine._optional_module("definitely_missing_sibling"))
        modules = [module("z%d" % index) for index in range(6)]
        stub = types.ModuleType("tools.layout2.pagination")

        def broken_paginate(modules_in, template, cfg):
            raise RuntimeError("sibling pagination is broken")

        stub.paginate = broken_paginate
        sys.modules["tools.layout2.pagination"] = stub
        try:
            plan = layout_engine.plan_project(project(*modules))
        finally:
            sys.modules.pop("tools.layout2.pagination", None)
        self.assertEqual(plan["verdict"], "pass")
        self.assertEqual(plan["metrics"]["page_count"], 2)


if __name__ == "__main__":
    unittest.main()

class EdgeClearanceTests(unittest.TestCase):
    def test_edge_clearance_insets_regions(self):
        project = {"name": "pin", "options": {"edge_clearance": 120},
                   "modules": [{"id": "m1", "title": "m1", "w": 200, "h": 150},
                               {"id": "m2", "title": "m2", "w": 200, "h": 150}]}
        plan = layout_engine.plan_project(project)
        self.assertEqual(plan["verdict"], "pass")
        for page in plan["pages"]:
            for block in page["blocks"]:
                self.assertGreaterEqual(block["bbox"][0], 10 + 120 - 0.5)
                self.assertGreaterEqual(block["bbox"][1], 190 + 120 - 0.5)

    def test_edge_clearance_zero_is_unchanged(self):
        base = layout_engine.plan_project(project(module("a")))
        with_zero = layout_engine.plan_project(
            {"name": "z", "options": {"edge_clearance": 0},
             "modules": [module("a")]})
        self.assertEqual(base["pages"][0]["blocks"][0]["bbox"],
                         with_zero["pages"][0]["blocks"][0]["bbox"])

