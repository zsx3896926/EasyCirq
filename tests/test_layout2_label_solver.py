"""Tests for the offline schematic label solver (easycirq-sch-label-plan/v1)."""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.layout2.label_solver import (  # noqa: E402
    DIRECTIONS,
    SCHEMA,
    default_metrics,
    solve_label_plan,
)

PAGE = [0.0, 0.0, 400.0, 300.0]


def make_label(label_id, text="VCC", size=10, anchor=(100, 100), preferred=None):
    label = {
        "id": label_id,
        "text": text,
        "size": size,
        "anchor": list(anchor),
        "role": "net_label",
    }
    if preferred is not None:
        label["preferred"] = list(preferred)
    return label


def placement_for(result, label_id):
    for placement in result["placements"]:
        if placement["id"] == label_id:
            return placement
    raise AssertionError(f"no placement for {label_id!r}: {result!r}")


def separated(first, second, gap=2.0):
    return (
        first[2] + gap <= second[0]
        or second[2] + gap <= first[0]
        or first[3] + gap <= second[1]
        or second[3] + gap <= first[1]
    )


class LabelSolverTests(unittest.TestCase):
    def test_empty_page_places_every_label(self):
        result = solve_label_plan(
            [
                make_label("vcc", "VCC", 10, (100, 100), ["right"]),
                make_label("gnd", "GND", 10, (200, 100), ["bottom"]),
            ],
            [],
            PAGE,
        )

        self.assertEqual(result["schema"], SCHEMA)
        self.assertEqual(result["verdict"], "pass")
        self.assertEqual(result["unplaced"], [])
        self.assertEqual(result["collisions_remaining"], 0)
        self.assertEqual([item["id"] for item in result["placements"]], ["vcc", "gnd"])

        vcc = placement_for(result, "vcc")
        self.assertEqual(vcc["direction"], "right")
        self.assertEqual(vcc["distance"], 4.0)
        self.assertEqual(vcc["bbox"], [104.0, 94.0, 122.0, 106.0])

        gnd = placement_for(result, "gnd")
        self.assertEqual(gnd["direction"], "bottom")
        self.assertEqual(gnd["bbox"], [191.0, 104.0, 209.0, 116.0])

    def test_preferred_direction_is_used_when_free(self):
        result = solve_label_plan(
            [make_label("l1", "VCC", 10, (200, 150), ["left", "top"])],
            [],
            PAGE,
        )

        placement = placement_for(result, "l1")
        self.assertEqual(result["verdict"], "pass")
        self.assertEqual(placement["direction"], "left")
        self.assertEqual(placement["distance"], 4.0)
        self.assertEqual(placement["bbox"], [178.0, 144.0, 196.0, 156.0])

    def test_dense_page_switches_direction(self):
        # A tall obstacle blocks every "right" candidate distance.
        result = solve_label_plan(
            [make_label("l1", "VCC", 10, (200, 200), ["right"])],
            [[220.0, 150.0, 260.0, 250.0]],
            [0.0, 0.0, 400.0, 400.0],
        )

        placement = placement_for(result, "l1")
        self.assertEqual(result["verdict"], "pass")
        self.assertEqual(placement["direction"], "top")
        self.assertEqual(placement["distance"], 4.0)
        self.assertEqual(placement["bbox"], [191.0, 184.0, 209.0, 196.0])
        self.assertTrue(
            separated(placement["bbox"], [220.0, 150.0, 260.0, 250.0])
        )

    def test_falls_back_to_diagonal_when_cardinals_are_blocked(self):
        # Tight boxes cover every cardinal candidate, but leave diagonal lanes.
        blockers = [
            [204.0, 194.0, 234.0, 206.0],  # right
            [166.0, 194.0, 196.0, 206.0],  # left
            [191.0, 172.0, 209.0, 196.0],  # top
            [191.0, 204.0, 209.0, 228.0],  # bottom
        ]
        result = solve_label_plan(
            [
                make_label(
                    "l1", "VCC", 10, (200, 200), ["right", "top", "left", "bottom"]
                )
            ],
            blockers,
            [0.0, 0.0, 400.0, 400.0],
        )

        placement = placement_for(result, "l1")
        self.assertEqual(result["verdict"], "pass")
        self.assertEqual(placement["direction"], "right-top")
        self.assertEqual(placement["distance"], 12.0)
        self.assertEqual(placement["bbox"], [212.0, 176.0, 230.0, 188.0])
        for blocker in blockers:
            self.assertTrue(separated(placement["bbox"], blocker))

    def test_impossible_label_is_unplaced(self):
        result = solve_label_plan(
            [make_label("blocked", "LABEL", 8, (60, 60), ["right"])],
            [[0.0, 0.0, 120.0, 120.0]],
            [0.0, 0.0, 120.0, 120.0],
        )

        self.assertEqual(result["verdict"], "review")
        self.assertEqual(result["placements"], [])
        self.assertEqual(
            result["unplaced"],
            [{"id": "blocked", "reason": "no_valid_candidate"}],
        )
        self.assertEqual(result["collisions_remaining"], 0)

    def test_label_larger_than_page_is_unplaced_with_reason(self):
        result = solve_label_plan(
            [make_label("huge", "NET", 10, (5, 5), ["right"])],
            [],
            [0.0, 0.0, 10.0, 10.0],
        )

        self.assertEqual(result["verdict"], "review")
        self.assertEqual(
            result["unplaced"],
            [{"id": "huge", "reason": "label_larger_than_page"}],
        )

    def test_placements_stay_inside_page_bounds(self):
        page = [0.0, 0.0, 60.0, 60.0]
        labels = [
            make_label("br", "A", 5, (3, 3), ["right"]),
            make_label("bl", "A", 5, (57, 3), ["left"]),
            make_label("tr", "A", 5, (3, 57), ["top"]),
            make_label("tl", "A", 5, (57, 57), ["left"]),
        ]

        result = solve_label_plan(labels, [], page)

        self.assertEqual(result["verdict"], "pass")
        self.assertEqual(len(result["placements"]), 4)
        for placement in result["placements"]:
            min_x, min_y, max_x, max_y = placement["bbox"]
            self.assertGreaterEqual(min_x, page[0])
            self.assertGreaterEqual(min_y, page[1])
            self.assertLessEqual(max_x, page[2])
            self.assertLessEqual(max_y, page[3])

    def test_deterministic_output(self):
        labels = [
            make_label("l1", "VCC", 10, (120, 80), ["right"]),
            make_label("l2", "SDA", 9, (180, 120), ["top"]),
            make_label("l3", "INT", 8, (260, 200), ["left"]),
        ]
        occupied = [
            [0.0, 0.0, 50.0, 50.0],
            [300.0, 0.0, 400.0, 80.0],
            [140.0, 60.0, 170.0, 100.0],
            [220.0, 180.0, 250.0, 220.0],
        ]

        first = solve_label_plan(labels, occupied, [0.0, 0.0, 400.0, 300.0])
        second = solve_label_plan(
            [dict(label, anchor=list(label["anchor"])) for label in labels],
            list(reversed(occupied)),
            [0.0, 0.0, 400.0, 300.0],
        )

        self.assertEqual(first["verdict"], "pass")
        self.assertEqual(
            json.dumps(first, sort_keys=True),
            json.dumps(second, sort_keys=True),
        )
        self.assertEqual(first, second)

    def test_gap_boundary_and_occupied_box_avoidance(self):
        # Exactly 2 units of clearance: accepted at the nearest distance.
        touching = solve_label_plan(
            [make_label("l1", "VCC", 10, (100, 100), ["right"])],
            [[124.0, 90.0, 140.0, 110.0]],
            PAGE,
        )
        near = placement_for(touching, "l1")
        self.assertEqual(near["direction"], "right")
        self.assertEqual(near["distance"], 4.0)
        self.assertEqual(near["bbox"], [104.0, 94.0, 122.0, 106.0])

        # One unit of clearance is not enough, so the solver moves elsewhere.
        crowded = solve_label_plan(
            [make_label("l1", "VCC", 10, (100, 100), ["right"])],
            [[123.0, 90.0, 140.0, 110.0]],
            PAGE,
        )
        moved = placement_for(crowded, "l1")
        self.assertEqual(moved["direction"], "top")
        self.assertEqual(moved["distance"], 4.0)
        self.assertTrue(separated(moved["bbox"], [123.0, 90.0, 140.0, 110.0]))

    def test_placed_labels_do_not_collide_with_each_other(self):
        labels = [
            make_label("l1", "SIG", 8, (200, 200), ["right"]),
            make_label("l2", "SIG", 8, (200, 200), ["right"]),
            make_label("l3", "SIG", 8, (200, 200), ["right"]),
        ]

        result = solve_label_plan(labels, [], [0.0, 0.0, 400.0, 400.0])

        self.assertEqual(result["verdict"], "pass")
        self.assertEqual(len(result["placements"]), 3)
        boxes = [placement["bbox"] for placement in result["placements"]]
        for index, box in enumerate(boxes):
            for other in boxes[index + 1 :]:
                self.assertTrue(separated(box, other), f"{box} collides with {other}")
        self.assertEqual(result["collisions_remaining"], 0)

    def test_cjk_width_uses_full_em(self):
        self.assertEqual(default_metrics("网络", 10)["w"], 20.0)
        self.assertEqual(default_metrics("A网", 10)["w"], 16.0)
        self.assertEqual(default_metrics("VCC", 10)["h"], 12.0)

        result = solve_label_plan(
            [
                make_label("cn", "网络", 10, (100, 100), ["right"]),
                make_label("mixed", "A网", 10, (200, 100), ["bottom"]),
            ],
            [],
            PAGE,
        )

        self.assertEqual(placement_for(result, "cn")["bbox"], [104.0, 94.0, 124.0, 106.0])
        self.assertEqual(
            placement_for(result, "mixed")["bbox"], [192.0, 104.0, 208.0, 116.0]
        )

    def test_custom_metrics_callable(self):
        label = [make_label("wide", "WIDE", 10, (150, 150), ["right"])]

        dict_metrics = solve_label_plan(
            label, [], PAGE, metrics=lambda text, size: {"w": 100.0, "h": 50.0}
        )
        self.assertEqual(
            placement_for(dict_metrics, "wide")["bbox"], [154.0, 125.0, 254.0, 175.0]
        )

        tuple_metrics = solve_label_plan(
            label, [], PAGE, metrics=lambda text, size: (100.0, 50.0)
        )
        self.assertEqual(dict_metrics, tuple_metrics)

    def test_unplaced_label_does_not_block_other_labels(self):
        result = solve_label_plan(
            [
                make_label("inside", "A", 10, (50, 50), ["right"]),
                make_label("free", "B", 10, (200, 200), ["right"]),
            ],
            [[0.0, 0.0, 100.0, 100.0]],
            [0.0, 0.0, 300.0, 300.0],
        )

        self.assertEqual(result["verdict"], "review")
        self.assertEqual([item["id"] for item in result["placements"]], ["free"])
        self.assertEqual([item["id"] for item in result["unplaced"]], ["inside"])
        self.assertEqual(result["collisions_remaining"], 0)
        self.assertIn(result["placements"][0]["direction"], DIRECTIONS)


if __name__ == "__main__":
    unittest.main()
