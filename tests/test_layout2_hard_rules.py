"""Offline tests for tools/layout2/hard_rules.py (layout engine v2 R1-R7).

No EDA, no daemon, no clock, no network. The measured page template is read
from ``easycirq/assets/page-template.json`` so the fixture numbers match what
the executor actually measures (1170x825, margin 10, title block
[460, 10]-[1160, 190]).
"""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.layout2.hard_rules import (  # noqa: E402
    DEFAULT_LABEL_GAP,
    DEFAULT_MIN_GAP,
    validate_page_plan,
)

TEMPLATE_PATH = ROOT / "easycirq" / "assets" / "page-template.json"

# Page 1170x825 with margin 10 => usable [10, 10]-[1160, 815].
USABLE_FRAME = {"id": "usable", "rect": [10, 10, 1160, 815]}


def make_page(blocks=None, labels=None, frames=None, number=1):
    return {
        "page": number,
        "frames": [dict(USABLE_FRAME)] if frames is None else frames,
        "blocks": list(blocks or []),
        "labels": list(labels or []),
    }


def make_plan(pages=None, page_count=1, modules=None, min_gap=None,
              label_gap=None):
    if pages is None:
        pages = [make_page()]
    plan = {
        "schema": "easycirq-sch-layout-v2/v1",
        "pages": pages,
    }
    if page_count is not None:
        plan["page_count"] = page_count
    if modules is not None:
        plan["modules"] = modules
    if min_gap is not None:
        plan["min_gap"] = min_gap
    if label_gap is not None:
        plan["label_gap"] = label_gap
    return plan


def block(block_id, bbox, zone, **extra):
    item = {"id": block_id, "bbox": bbox, "zone": zone}
    item.update(extra)
    return item


def label(label_id, bbox):
    return {"id": label_id, "bbox": bbox}


def valid_blocks():
    return [
        block("mcu", [40, 220, 280, 380], [20, 200, 300, 400]),
        block("power", [340, 220, 500, 320], [320, 200, 520, 340]),
        block("gpio", [560, 220, 740, 400], [540, 200, 760, 420]),
    ]


def valid_labels():
    return [
        label("mcu.title", [50, 230, 120, 240]),
        label("power.title", [350, 230, 420, 240]),
        label("gpio.title", [570, 230, 640, 240]),
    ]


def valid_plan():
    return make_plan(
        [make_page(valid_blocks(), valid_labels())],
        modules=["mcu", "power", "gpio"],
    )


def findings_for(result, rule):
    return [item for item in result["findings"] if item["rule"] == rule]


class HardRulesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))

    # -- measured template -------------------------------------------------
    def test_measured_template_numbers(self):
        self.assertEqual(self.template["page"]["width"], 1170)
        self.assertEqual(self.template["page"]["height"], 825)
        self.assertEqual(self.template["page"]["margin"], 10)
        self.assertEqual(
            self.template["title_block"]["rect"],
            {"minX": 460, "minY": 10, "maxX": 1160, "maxY": 190},
        )

    def test_measured_usable_boundaries_are_inclusive(self):
        # A zone that exactly touches all page-minus-margin edges is legal;
        # it stops left of the title block (maxX 459 < 460).
        plan = make_plan(
            [make_page([block("left", [11, 11, 458, 814],
                               [10, 10, 459, 815])])],
            modules=["left"],
        )
        result = validate_page_plan(plan, self.template)
        self.assertEqual(result["verdict"], "pass", result["findings"])
        self.assertEqual(result["findings"], [])

    def test_measured_margin_is_page_minus_10(self):
        plan = make_plan(
            [make_page([block("mcu", [40, 220, 280, 380],
                               [9, 200, 300, 400])])],
            modules=["mcu"],
        )
        result = validate_page_plan(plan, self.template)
        self.assertEqual(result["verdict"], "blocked")
        self.assertTrue(findings_for(result, "R1"))
        self.assertEqual(result["metrics"]["zone_out_of_page"], 1)

    def test_measured_title_block_starts_at_x_460_y_10(self):
        plan = make_plan(
            [make_page([block("mcu", [11, 11, 460, 814],
                               [10, 10, 461, 815])])],
            modules=["mcu"],
        )
        result = validate_page_plan(plan, self.template)
        self.assertEqual(result["verdict"], "blocked")
        hits = findings_for(result, "R2")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["ids"], ["mcu"])
        self.assertEqual(result["metrics"]["title_block_hits"], 1)

    # -- happy path and metrics -------------------------------------------
    def test_valid_plan_passes(self):
        result = validate_page_plan(valid_plan(), self.template)
        self.assertEqual(result["verdict"], "pass")
        self.assertEqual(result["findings"], [])
        metrics = result["metrics"]
        self.assertEqual(metrics["page_count"], 1)
        self.assertEqual(metrics["declared_page_count"], 1)
        self.assertEqual(metrics["block_count"], 3)
        self.assertEqual(metrics["label_count"], 3)
        self.assertEqual(metrics["frame_count"], 1)
        self.assertEqual(metrics["zone_count"], 3)
        self.assertEqual(metrics["block_overlaps"], 0)
        self.assertEqual(metrics["block_gap_violations"], 0)
        self.assertEqual(metrics["label_collisions"], 0)
        self.assertEqual(metrics["label_gap_violations"], 0)
        self.assertEqual(metrics["label_frame_crossings"], 0)
        self.assertEqual(metrics["title_block_hits"], 0)
        self.assertEqual(metrics["blocks_outside_zone"], 0)
        self.assertEqual(metrics["module_assignment_errors"], 0)
        self.assertEqual(metrics["page_count_errors"], 0)
        self.assertEqual(metrics["min_block_gap"], 60.0)
        self.assertEqual(metrics["min_gap"], DEFAULT_MIN_GAP)
        self.assertEqual(metrics["label_gap"], DEFAULT_LABEL_GAP)

    def test_valid_plan_metrics_use_measured_page_area(self):
        result = validate_page_plan(valid_plan(), self.template)
        metrics = result["metrics"]
        # (1170 - 2*10) * (825 - 2*10)
        usable_area = 1150 * 805
        block_area = 240 * 160 + 160 * 100 + 180 * 180
        zone_area = 280 * 200 + 200 * 140 + 220 * 220
        self.assertAlmostEqual(metrics["usable_area"], usable_area, places=6)
        self.assertAlmostEqual(
            metrics["page_utilization"], block_area / usable_area, places=6)
        self.assertAlmostEqual(
            metrics["zone_fill"], block_area / zone_area, places=6)

    def test_rect_dicts_are_accepted(self):
        plan = make_plan(
            [make_page([{
                "id": "mcu",
                "bbox": {"minX": 40, "minY": 220, "maxX": 280, "maxY": 380},
                "zone": {"minX": 20, "minY": 200, "maxX": 300, "maxY": 400},
            }])],
            modules=["mcu"],
        )
        result = validate_page_plan(plan, self.template)
        self.assertEqual(result["verdict"], "pass", result["findings"])

    def test_empty_page_plan_passes_vacuously(self):
        result = validate_page_plan(make_plan([make_page()], page_count=1),
                                    self.template)
        self.assertEqual(result["verdict"], "pass")
        self.assertEqual(result["metrics"]["block_count"], 0)
        self.assertEqual(result["metrics"]["page_utilization"], 0.0)

    # -- R1 ---------------------------------------------------------------
    def test_r1_zone_outside_page_is_blocked(self):
        plan = make_plan(
            [make_page([block("mcu", [40, 220, 280, 380],
                               [5, 200, 300, 400])])],
            modules=["mcu"],
        )
        result = validate_page_plan(plan, self.template)
        self.assertEqual(result["verdict"], "blocked")
        findings = findings_for(result, "R1")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["ids"], ["mcu"])
        self.assertEqual(findings[0]["severity"], "error")
        self.assertIn("page-minus-margin", findings[0]["detail"])
        self.assertEqual(result["metrics"]["zone_out_of_page"], 1)
        self.assertEqual(result["metrics"]["out_of_page"], 1)

    def test_r1_frame_outside_page_is_blocked(self):
        frames = [{"id": "overflow", "rect": [0, 0, 1170, 825]}]
        plan = make_plan([make_page(frames=frames)], modules=None,
                         page_count=1)
        result = validate_page_plan(plan, self.template)
        self.assertEqual(result["verdict"], "blocked")
        findings = findings_for(result, "R1")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["ids"], ["overflow"])
        self.assertEqual(result["metrics"]["frame_out_of_page"], 1)

    # -- R2 ---------------------------------------------------------------
    def test_r2_zone_hitting_title_block_is_blocked(self):
        # Title block is [460, 10]-[1160, 190].
        plan = make_plan(
            [make_page([block("mcu", [410, 110, 490, 170],
                               [400, 100, 500, 180])])],
            modules=["mcu"],
        )
        result = validate_page_plan(plan, self.template)
        self.assertEqual(result["verdict"], "blocked")
        findings = findings_for(result, "R2")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["ids"], ["mcu"])
        self.assertIn("title-block", findings[0]["detail"])
        self.assertEqual(result["metrics"]["title_block_hits"], 1)

    def test_r2_touching_title_block_edge_is_allowed(self):
        # minY == title maxY (190) is a shared edge, not an intersection.
        plan = make_plan(
            [make_page([block("mcu", [510, 200, 590, 290],
                               [500, 190, 600, 300])])],
            modules=["mcu"],
        )
        result = validate_page_plan(plan, self.template)
        self.assertEqual(result["verdict"], "pass", result["findings"])
        self.assertEqual(result["metrics"]["title_block_hits"], 0)

    # -- R3 ---------------------------------------------------------------
    def test_r3_block_bbox_outside_zone_is_blocked(self):
        plan = make_plan(
            [make_page([block("mcu", [40, 190, 280, 380],
                               [20, 200, 300, 400])])],
            modules=["mcu"],
        )
        result = validate_page_plan(plan, self.template)
        self.assertEqual(result["verdict"], "blocked")
        findings = findings_for(result, "R3")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["ids"], ["mcu"])
        self.assertEqual(result["metrics"]["blocks_outside_zone"], 1)

    def test_r3_halo_outside_zone_is_blocked(self):
        item = block("mcu", [60, 220, 280, 380], [50, 200, 300, 400],
                     halo={"left": 20, "right": 0, "top": 0, "bottom": 0})
        plan = make_plan([make_page([item])], modules=["mcu"])
        result = validate_page_plan(plan, self.template)
        self.assertEqual(result["verdict"], "blocked")
        findings = findings_for(result, "R3")
        self.assertEqual(len(findings), 1)
        self.assertIn("bbox+halo", findings[0]["detail"])
        self.assertEqual(result["metrics"]["blocks_outside_zone"], 1)

    def test_r3_halo_inside_zone_passes(self):
        item = block("mcu", [60, 220, 280, 380], [50, 200, 300, 400],
                     halo={"left": 5, "right": 5, "top": 5, "bottom": 5})
        plan = make_plan([make_page([item])], modules=["mcu"])
        result = validate_page_plan(plan, self.template)
        self.assertEqual(result["verdict"], "pass", result["findings"])

    # -- R4 ---------------------------------------------------------------
    def test_r4_block_overlap_is_blocked(self):
        blocks = [
            block("a", [40, 220, 180, 380], [20, 200, 200, 400]),
            block("b", [100, 250, 280, 350], [150, 200, 300, 400]),
        ]
        plan = make_plan([make_page(blocks)], modules=["a", "b"])
        result = validate_page_plan(plan, self.template)
        self.assertEqual(result["verdict"], "blocked")
        findings = findings_for(result, "R4")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["ids"], ["a", "b"])
        self.assertIn("overlap", findings[0]["detail"])
        self.assertEqual(result["metrics"]["block_overlaps"], 1)

    def test_r4_default_min_gap_is_8(self):
        blocks = [
            block("a", [20, 200, 100, 300], [15, 195, 104, 305]),
            block("b", [107, 200, 185, 300], [107, 195, 190, 305]),
        ]
        plan = make_plan([make_page(blocks)], modules=["a", "b"])
        result = validate_page_plan(plan, self.template)
        self.assertEqual(result["verdict"], "blocked")
        findings = findings_for(result, "R4")
        self.assertEqual(len(findings), 1)
        self.assertIn("min_gap 8", findings[0]["detail"])
        self.assertEqual(result["metrics"]["min_block_gap"], 7.0)
        self.assertEqual(result["metrics"]["block_gap_violations"], 1)

    def test_r4_gap_equal_to_min_gap_passes(self):
        blocks = [
            block("a", [20, 200, 100, 300], [15, 195, 104, 305]),
            block("b", [108, 200, 185, 300], [107, 195, 190, 305]),
        ]
        plan = make_plan([make_page(blocks)], modules=["a", "b"])
        result = validate_page_plan(plan, self.template)
        self.assertEqual(result["verdict"], "pass", result["findings"])
        self.assertEqual(result["metrics"]["min_block_gap"], 8.0)

    def test_r4_min_gap_can_be_overridden_by_plan(self):
        blocks = [
            block("a", [20, 200, 100, 300], [15, 195, 104, 305]),
            block("b", [105, 200, 185, 300], [105, 195, 190, 305]),
        ]
        result = validate_page_plan(
            make_plan([make_page(blocks)], modules=["a", "b"], min_gap=4),
            self.template)
        self.assertEqual(result["verdict"], "pass", result["findings"])
        self.assertEqual(result["metrics"]["min_gap"], 4.0)

    def test_r4_blocks_on_different_pages_are_not_compared(self):
        pages = [
            make_page([block("a", [40, 220, 280, 380],
                             [20, 200, 300, 400])], number=1),
            make_page([block("b", [40, 220, 280, 380],
                             [20, 200, 300, 400])], number=2),
        ]
        result = validate_page_plan(
            make_plan(pages, page_count=2, modules=["a", "b"]),
            self.template)
        self.assertEqual(result["verdict"], "pass", result["findings"])

    # -- R5 ---------------------------------------------------------------
    def test_r5_label_overlap_is_blocked(self):
        blocks = [block("mcu", [40, 220, 380, 480], [20, 200, 400, 500])]
        labels = [label("first", [30, 210, 100, 240]),
                  label("second", [90, 220, 160, 250])]
        plan = make_plan([make_page(blocks, labels)], modules=["mcu"])
        result = validate_page_plan(plan, self.template)
        self.assertEqual(result["verdict"], "blocked")
        findings = findings_for(result, "R5")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["ids"], ["first", "second"])
        self.assertEqual(result["metrics"]["label_collisions"], 1)

    def test_r5_label_gap_default_is_2(self):
        blocks = [block("mcu", [40, 220, 380, 480], [20, 200, 400, 500])]
        labels = [label("first", [30, 210, 100, 240]),
                  label("second", [101, 210, 170, 240])]
        plan = make_plan([make_page(blocks, labels)], modules=["mcu"])
        result = validate_page_plan(plan, self.template)
        self.assertEqual(result["verdict"], "blocked")
        findings = findings_for(result, "R5")
        self.assertEqual(len(findings), 1)
        self.assertIn("label_gap 2", findings[0]["detail"])
        self.assertEqual(result["metrics"]["label_gap_violations"], 1)
        self.assertEqual(result["metrics"]["min_label_gap"], 1.0)

    def test_r5_label_gap_equal_to_2_passes(self):
        blocks = [block("mcu", [40, 220, 380, 480], [20, 200, 400, 500])]
        labels = [label("first", [30, 210, 100, 240]),
                  label("second", [102, 210, 170, 240])]
        plan = make_plan([make_page(blocks, labels)], modules=["mcu"])
        result = validate_page_plan(plan, self.template)
        self.assertEqual(result["verdict"], "pass", result["findings"])

    # -- R6 ---------------------------------------------------------------
    def test_r6_label_crossing_zone_edge_is_blocked(self):
        blocks = [block("mcu", [40, 220, 280, 380], [20, 200, 300, 400])]
        labels = [label("mcu.title", [295, 210, 320, 230])]
        plan = make_plan([make_page(blocks, labels)], modules=["mcu"])
        result = validate_page_plan(plan, self.template)
        self.assertEqual(result["verdict"], "blocked")
        findings = findings_for(result, "R6")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["ids"], ["mcu.title", "mcu"])
        self.assertIn("zone", findings[0]["detail"])
        self.assertEqual(result["metrics"]["label_frame_crossings"], 1)

    def test_r6_label_crossing_page_frame_edge_is_blocked(self):
        labels = [label("edge", [1150, 300, 1170, 320])]
        plan = make_plan([make_page(labels=labels)], modules=None,
                         page_count=1)
        result = validate_page_plan(plan, self.template)
        self.assertEqual(result["verdict"], "blocked")
        findings = findings_for(result, "R6")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["ids"], ["edge", "usable"])
        self.assertIn("frame", findings[0]["detail"])

    # -- R7 ---------------------------------------------------------------
    def test_r7_module_assigned_twice_is_blocked(self):
        pages = [
            make_page([block("mcu", [40, 220, 280, 380],
                             [20, 200, 300, 400])], number=1),
            make_page([block("mcu", [40, 220, 280, 380],
                             [20, 200, 300, 400])], number=2),
        ]
        result = validate_page_plan(make_plan(pages, page_count=2),
                                    self.template)
        self.assertEqual(result["verdict"], "blocked")
        findings = findings_for(result, "R7")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["ids"], ["mcu"])
        self.assertIn("exactly once", findings[0]["detail"])
        self.assertEqual(result["metrics"]["module_assignment_errors"], 1)

    def test_r7_declared_module_missing_from_pages_is_blocked(self):
        plan = make_plan(
            [make_page([block("mcu", [40, 220, 280, 380],
                               [20, 200, 300, 400])])],
            modules=["mcu", "power"],
        )
        result = validate_page_plan(plan, self.template)
        self.assertEqual(result["verdict"], "blocked")
        findings = findings_for(result, "R7")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["ids"], ["power"])
        self.assertIn("not assigned", findings[0]["detail"])

    def test_r7_undeclared_block_is_blocked(self):
        blocks = [
            block("mcu", [40, 220, 280, 380], [20, 200, 300, 400]),
            block("extra", [340, 220, 500, 320], [320, 200, 520, 340]),
        ]
        plan = make_plan([make_page(blocks)], modules=["mcu"])
        result = validate_page_plan(plan, self.template)
        self.assertEqual(result["verdict"], "blocked")
        findings = findings_for(result, "R7")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["ids"], ["extra"])
        self.assertIn("not declared", findings[0]["detail"])

    def test_r7_module_declared_twice_is_blocked(self):
        plan = make_plan(
            [make_page([block("mcu", [40, 220, 280, 380],
                               [20, 200, 300, 400])])],
            modules=["mcu", "mcu"],
        )
        result = validate_page_plan(plan, self.template)
        self.assertEqual(result["verdict"], "blocked")
        findings = findings_for(result, "R7")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["ids"], ["mcu"])
        self.assertIn("declared 2 times", findings[0]["detail"])

    def test_r7_page_count_mismatch_is_blocked(self):
        plan = valid_plan()
        plan["page_count"] = 2
        result = validate_page_plan(plan, self.template)
        self.assertEqual(result["verdict"], "blocked")
        findings = findings_for(result, "R7")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["ids"], [])
        self.assertIn("plan.page_count is 2", findings[0]["detail"])
        self.assertEqual(result["metrics"]["page_count_errors"], 1)

    def test_r7_page_count_may_be_omitted(self):
        plan = valid_plan()
        del plan["page_count"]
        result = validate_page_plan(plan, self.template)
        self.assertEqual(result["verdict"], "pass", result["findings"])
        self.assertIsNone(result["metrics"]["declared_page_count"])

    # -- determinism and malformed input ----------------------------------
    def test_result_is_deterministic_and_rule_sorted(self):
        plan = make_plan(
            [make_page(
                [block("mcu", [40, 190, 280, 380], [5, 200, 300, 400]),
                 block("power", [100, 250, 280, 350],
                       [150, 200, 300, 400])],
                [label("first", [30, 210, 100, 240]),
                 label("second", [90, 220, 160, 250])],
            )],
            modules=["mcu", "power", "unused"],
            page_count=2,
        )
        first = validate_page_plan(plan, self.template)
        second = validate_page_plan(plan, self.template)
        self.assertEqual(first, second)
        self.assertEqual(json.dumps(first, sort_keys=True),
                         json.dumps(second, sort_keys=True))
        rules = [item["rule"] for item in first["findings"]]
        self.assertEqual(rules, sorted(rules))
        self.assertEqual(set(rules), {"R1", "R3", "R4", "R5", "R6", "R7"})

    def test_malformed_plan_raises_value_error(self):
        cases = [
            None,
            {},
            {"pages": "not-a-list"},
            {"page_count": 1},
            make_plan([make_page([{"id": "mcu", "bbox": [0, 0, 10, 10]}])]),
            make_plan([make_page([{"bbox": [0, 0, 10, 10],
                                   "zone": [0, 0, 20, 20]}])]),
            make_plan([make_page([block("mcu", [10, 10, 20, 20],
                                        [20, 20, 10, 10])])]),
            make_plan([make_page([block("mcu", [True, 10, 20, 20],
                                        [0, 0, 30, 30])])]),
            make_plan([make_page()], page_count=1.5),
        ]
        for case in cases:
            with self.subTest(case=case):
                with self.assertRaises(ValueError):
                    validate_page_plan(case, self.template)

    def test_malformed_template_raises_value_error(self):
        plan = valid_plan()
        cases = [None, {}, {"page": {"width": 0, "height": 825,
                                     "margin": 10}},
                 {"page": {"width": 1170, "height": 825, "margin": -1}}]
        for case in cases:
            with self.subTest(case=case):
                with self.assertRaises(ValueError):
                    validate_page_plan(plan, case)


if __name__ == "__main__":
    unittest.main()
