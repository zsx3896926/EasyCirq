import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.layout2.zone_solver import solve_page

SCHEMA = "easycirq-sch-zone-plan/v1"
FULL_PAGE = {"width": 1170, "height": 825, "margin": 12}
FULL_TITLE = {"minX": 610, "minY": 12, "maxX": 1170, "maxY": 380}


def template(width=1170, height=825, margin=12, title_block=FULL_TITLE):
    data = {"page": {"width": width, "height": height, "margin": margin}}
    data["title_block"] = None if title_block is None else {"rect": dict(title_block)}
    return data


def make_request(modules, gap=40, title_gap=36, template_data=None, page_index=0):
    return {"page_index": page_index,
            "modules": modules,
            "template": copy.deepcopy(template_data) if template_data is not None
            else template(width=1170, height=825),
            "gap": gap,
            "title_gap": title_gap}


def module(module_id, width, height, halo=None):
    data = {"id": module_id, "title": module_id.upper(), "w": width, "h": height}
    if halo is not None:
        data["halo"] = halo
    return data


def box(rect):
    return [rect["minX"], rect["minY"], rect["maxX"], rect["maxY"]]


def overlap_area(a, b):
    ox = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    oy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    return ox * oy


def contains(outer, inner):
    return (inner[0] >= outer[0] and inner[1] >= outer[1]
            and inner[2] <= outer[2] and inner[3] <= outer[3])


class ThreeBlocksFit(unittest.TestCase):
    def test_three_blocks_fit_in_left_strip(self):
        modules = [module("b1", 160, 120), module("b2", 160, 120), module("b3", 160, 120)]
        result = solve_page(make_request(modules))

        self.assertEqual(result["schema"], SCHEMA)
        self.assertEqual(result["page_index"], 0)
        self.assertEqual(result["verdict"], "pass")
        self.assertEqual(result["metrics"]["fits"], 3)
        self.assertTrue(result["metrics"]["all_fit"])
        self.assertEqual(len(result["frames"]), 3)
        self.assertEqual(result["metrics"]["overlaps"], 0)
        self.assertEqual(result["metrics"]["zone_overlaps"], 0)
        self.assertEqual(result["metrics"]["title_block_hits"], 0)
        self.assertGreaterEqual(result["metrics"]["zone_slack"], 0)
        self.assertEqual(result["metrics"]["score"], 100.0)
        self.assertEqual(result["unplaced"], [])

        # deterministic shelf: one row, in id order, padded by the default zone pad
        bboxes = sorted((block["bbox"] for block in result["blocks"]), key=lambda b: b[0])
        self.assertEqual(bboxes, [[20, 20, 180, 140],
                                  [220, 20, 380, 140],
                                  [420, 20, 580, 140]])
        # title room above the block: pad (8) + title_gap (36)
        self.assertEqual(result["frames"][0]["rect"]["maxY"], 140 + 8 + 36)
        self.assertTrue(all(block["region"] == "left" for block in result["blocks"]))


class TitleBlockAdjacency(unittest.TestCase):
    def test_layout_next_to_title_block_avoids_keepout(self):
        page = template(width=400, height=300, margin=10,
                        title_block={"minX": 180, "minY": 10, "maxX": 390, "maxY": 120})
        modules = [module("m1", 150, 100), module("m2", 180, 60)]
        result = solve_page(make_request(modules, gap=20, title_gap=10, template_data=page))

        self.assertEqual(result["verdict"], "pass")
        self.assertEqual(result["metrics"]["fits"], 2)
        self.assertEqual(result["metrics"]["title_block_hits"], 0)
        self.assertEqual(result["metrics"]["zone_overlaps"], 0)

        title_rect = [180, 10, 390, 120]
        zones = [box(frame["rect"]) for frame in result["frames"]]
        for zone in zones:
            self.assertEqual(overlap_area(zone, title_rect), 0)

        # the second module only fits the top-right strip, so its zone must sit
        # on the title-block edge without crossing into the keep-out
        by_id = {block["id"]: block for block in result["blocks"]}
        self.assertEqual(by_id["m2"]["region"], "top-right")
        zone_m2 = by_id["m2"]["zone"]
        self.assertEqual(zone_m2[1], 120)
        self.assertEqual(overlap_area(zone_m2, title_rect), 0)


class HaloPadding(unittest.TestCase):
    def test_halo_increases_the_zone(self):
        page = template(width=400, height=300, margin=10,
                        title_block={"minX": 300, "minY": 10, "maxX": 390, "maxY": 100})
        plain = solve_page(make_request([module("m", 100, 60)], gap=20,
                                        title_gap=10, template_data=page))
        haloed = solve_page(make_request([module("m", 100, 60, halo=30)], gap=20,
                                         title_gap=10, template_data=page))

        plain_zone = box(plain["frames"][0]["rect"])
        halo_zone = box(haloed["frames"][0]["rect"])
        plain_area = (plain_zone[2] - plain_zone[0]) * (plain_zone[3] - plain_zone[1])
        halo_area = (halo_zone[2] - halo_zone[0]) * (halo_zone[3] - halo_zone[1])
        self.assertGreater(halo_area, plain_area)
        self.assertEqual(haloed["verdict"], "pass")

        bbox = haloed["blocks"][0]["bbox"]
        halo_box = [bbox[0] - 30, bbox[1] - 30, bbox[2] + 30, bbox[3] + 30]
        self.assertTrue(contains(halo_zone, halo_box))
        self.assertTrue(contains(halo_zone, bbox))
        self.assertTrue(contains(box(plain["frames"][0]["rect"]), plain["blocks"][0]["bbox"]))


class TooLargeBlock(unittest.TestCase):
    def test_too_large_block_is_blocked(self):
        page = template(width=400, height=300, margin=10, title_block=None)
        result = solve_page(make_request([module("huge", 1000, 900)], template_data=page))

        self.assertEqual(result["verdict"], "blocked")
        self.assertEqual(result["metrics"]["fits"], 0)
        self.assertFalse(result["metrics"]["all_fit"])
        self.assertEqual(result["frames"], [])
        self.assertEqual(result["unplaced"], ["huge"])
        self.assertIsNone(result["blocks"][0]["bbox"])
        self.assertIsNone(result["blocks"][0]["zone"])
        self.assertEqual(result["metrics"]["overlaps"], 0)
        self.assertEqual(result["metrics"]["title_block_hits"], 0)
        self.assertLess(result["metrics"]["score"], 100.0)


class Determinism(unittest.TestCase):
    def test_same_input_gives_identical_plan_and_is_not_mutated(self):
        page = template()
        modules = [module("a", 200, 150, halo=12), module("b", 180, 120),
                   module("c", 160, 140, halo=24), module("d", 140, 110, halo=16)]
        request = make_request(modules, template_data=page)
        before = copy.deepcopy(request)

        first = solve_page(request)
        second = solve_page(copy.deepcopy(request))

        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))
        self.assertEqual(request, before)


class HardInvariants(unittest.TestCase):
    MODULES = [module("m1", 200, 150, halo=12), module("m2", 180, 120),
               module("m3", 160, 140, halo=24), module("m4", 120, 100),
               module("m5", 140, 110, halo=16)]

    def test_all_invariants_hold(self):
        result = solve_page(make_request(self.MODULES))

        self.assertEqual(result["verdict"], "pass")
        self.assertEqual(result["metrics"]["fits"], len(self.MODULES))
        self.assertEqual(result["metrics"]["overlaps"], 0)
        self.assertEqual(result["metrics"]["zone_overlaps"], 0)
        self.assertEqual(result["metrics"]["title_block_hits"], 0)
        self.assertEqual(len(result["frames"]), len(self.MODULES))

        margin = 12
        content = [margin, margin, 1170 - margin, 825 - margin]
        title_rect = box(result["title_block"]["rect"])
        blocks = result["blocks"]

        for block in blocks:
            bbox = block["bbox"]
            zone = block["zone"]
            self.assertIsNotNone(bbox)
            self.assertIsNotNone(zone)
            # (a) zone inside page minus margin
            self.assertTrue(contains(content, zone))
            # (b) zone clear of the title block keep-out
            self.assertEqual(overlap_area(zone, title_rect), 0)
            # (c) bbox and its halo inside the zone
            self.assertTrue(contains(zone, bbox))
            halo = block["halo"]
            halo_box = [bbox[0] - halo, bbox[1] - halo, bbox[2] + halo, bbox[3] + halo]
            self.assertTrue(contains(zone, halo_box))
            # title is reserved above the block
            self.assertGreaterEqual(zone[3] - bbox[3], 36)

        # (d) no block overlap and no zone overlap
        for i in range(len(blocks)):
            for j in range(i + 1, len(blocks)):
                self.assertEqual(overlap_area(blocks[i]["bbox"], blocks[j]["bbox"]), 0)
                self.assertEqual(overlap_area(blocks[i]["zone"], blocks[j]["zone"]), 0)


class RejectsBadInput(unittest.TestCase):
    def test_duplicate_module_id(self):
        modules = [module("same", 100, 80), module("same", 90, 70)]
        with self.assertRaises(ValueError):
            solve_page(make_request(modules))

    def test_negative_halo(self):
        with self.assertRaises(ValueError):
            solve_page(make_request([module("m", 100, 80, halo=-1)]))

    def test_wrong_schema(self):
        request = make_request([module("m", 100, 80)])
        request["schema"] = "easycirq-sch-zone-plan/v0"
        with self.assertRaises(ValueError):
            solve_page(request)

    def test_missing_gap(self):
        request = make_request([module("m", 100, 80)])
        del request["gap"]
        with self.assertRaises(ValueError):
            solve_page(request)

    def test_margin_leaves_no_usable_area(self):
        page = template(width=100, height=100, margin=50, title_block=None)
        with self.assertRaises(ValueError):
            solve_page(make_request([module("m", 10, 10)], template_data=page))

    def test_empty_module_list(self):
        with self.assertRaises(ValueError):
            solve_page(make_request([]))


if __name__ == "__main__":
    unittest.main()
