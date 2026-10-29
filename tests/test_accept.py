"""Tests for the deterministic EDA acceptance plan (offline)."""

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import accept  # noqa: E402

BUNDLE = {
    "schema": "easycirq-sch-apply/v1",
    "project": "demo",
    "engine": "templates",
    "post_apply": {"save": "doc reload", "required": True},
    "pages": [{
        "page": 1,
        "frames": [{"id": "f1", "title": "f1", "rect": [10, 10, 300, 200]}],
        "placements": [{
            "id": "m1", "title": "m1", "bbox": [10, 10, 300, 200],
            "zone": [10, 10, 300, 200], "at": "20,20",
            "parts": [{"ref": "U1", "x": 20, "y": 20, "rotation": 0},
                      {"ref": "C1", "x": 40, "y": 20, "rotation": 0}],
        }],
    }],
}


class AcceptTests(unittest.TestCase):
    def test_plan_is_ordered_with_save_and_verify(self):
        result = accept.build(BUNDLE, project_uuid="p", page="pg")
        text = "\n".join(result["commands"])
        self.assertLess(text.index("sch clear-page"),
                        text.index("sch place --designator U1"))
        self.assertLess(text.index("sch place --designator C1"),
                        text.index("doc reload"))
        self.assertIn("export-image", text)

    def test_parts_are_placed_individually(self):
        result = accept.build(BUNDLE, project_uuid="p", page="pg")
        self.assertTrue(any("sch place --designator U1" in c
                            for c in result["commands"]))

    def test_no_parts_uses_block_apply(self):
        bundle = {"schema": "easycirq-sch-apply/v1", "project": "d",
                  "post_apply": {}, "pages": [{"page": 1, "frames": [],
                  "placements": [{"id": "m1", "bbox": [10, 10, 200, 200],
                                  "at": "20,20"}]}]}
        result = accept.build(bundle, project_uuid="p", page="pg")
        self.assertTrue(any("sch block-apply" in c for c in result["commands"]))

    def test_geometry_check_flags_title_block(self):
        bundle = {"schema": "easycirq-sch-apply/v1", "project": "d",
                  "post_apply": {}, "pages": [{"page": 1, "frames": [],
                  "placements": [{"id": "m1", "bbox": [500, 50, 600, 150],
                                  "at": "500,50"}]}]}
        result = accept.build(bundle, project_uuid="p", page="pg")
        checks = {c["check"]: c for c in result["checks"]}
        self.assertTrue(checks["geometry"]["title_block_hit"])

    def test_deterministic(self):
        a = accept.build(BUNDLE, project_uuid="p", page="pg")
        b = accept.build(BUNDLE, project_uuid="p", page="pg")
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
