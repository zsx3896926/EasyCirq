"""Tests for channel-reserved layout and balanced block pagination."""

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import channel_layout  # noqa: E402


def card(cid, w, h):
    return {"id": cid, "w": w, "h": h, "src": (0.0, 0.0)}


class PaginateTests(unittest.TestCase):
    def test_first_card_lands_on_page_one(self):
        pages = channel_layout.paginate([card("a", 300, 300), card("b", 300, 300)])
        self.assertEqual(pages[0][0]["page"], 0)
        self.assertTrue(all(p["py"] >= 0 for p in pages[0]))

    def test_cards_never_overlap(self):
        pages = channel_layout.paginate([card("a", 300, 300), card("b", 250, 400),
                                         card("c", 200, 200)])
        boxes = [(p["px"], p["py"], p["px"] + p["w"], p["py"] + p["h"])
                 for page in pages for p in page]
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                a, b = boxes[i], boxes[j]
                overlap = (min(a[2], b[2]) > max(a[0], b[0])
                           and min(a[3], b[3]) > max(a[1], b[1]))
                self.assertFalse(overlap)

    def test_oversized_card_is_rejected(self):
        with self.assertRaises(ValueError):
            channel_layout.paginate([card("huge", 5000, 500)])

    def test_union_cards_include_labels(self):
        placements = {"U1": {"x": 100, "y": 100, "w": 40, "h": 60}}
        labels = {"U1:1": [140.0, 94.0, 200.0, 106.0]}
        cards = channel_layout.union_cards([], placements, labels, {"U1": "g"})
        self.assertEqual(cards[0]["id"], "g")
        self.assertGreaterEqual(cards[0]["src"][0] + cards[0]["w"], 200.0)

    def test_blocks_stay_whole_on_one_page(self):
        blocks = {"A": {"w": 400, "h": 300, "cards": [card("a1", 400, 300)]},
                  "B": {"w": 400, "h": 300, "cards": [card("b1", 400, 300)]},
                  "C": {"w": 400, "h": 300, "cards": [card("c1", 400, 300)]}}
        pages = channel_layout.paginate_blocks(blocks)
        seen = {}
        for index, page in enumerate(pages):
            for column in page:
                for block_id, _ in column:
                    self.assertNotIn(block_id, seen)
                    seen[block_id] = index
        self.assertEqual(set(seen), {"A", "B", "C"})

    def test_page_loads_are_balanced(self):
        blocks = {name: {"w": 300, "h": 250, "cards": [card(name, 300, 250)]}
                  for name in "ABCD"}
        pages = channel_layout.paginate_blocks(blocks)
        counts = [sum(1 for col in page for _ in col) for page in pages]
        self.assertLessEqual(max(counts) - min(counts), 1)


if __name__ == "__main__":
    unittest.main()
