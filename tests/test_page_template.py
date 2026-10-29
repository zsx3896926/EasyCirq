"""Tests for the page-level template builder (offline)."""

import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import page_template  # noqa: E402


def snapshot():
    return {
        "schema": "easycirq-ace-snapshot/v1", "page": "p1",
        "titleblock": {"fields": {"Title": "t"}},
        "components": [
            {"ref": "U1", "value": None, "mpn": "ESP32",
             "bbox": {"minX": 100, "minY": 100, "maxX": 160, "maxY": 200},
             "pins": [{"number": "1", "name": "VDD", "net": "3V3"},
                      {"number": "2", "name": "GND", "net": "GND"},
                      {"number": "9", "name": "SPARE", "net": None, "nc": True}]},
            {"ref": "C1", "value": "100nF", "mpn": None,
             "bbox": {"minX": 60, "minY": 120, "maxX": 80, "maxY": 140},
             "pins": [{"number": "1", "name": "1", "net": "3V3"},
                      {"number": "2", "name": "2", "net": "GND"}]},
        ],
    }


class PageTemplateTests(unittest.TestCase):
    def test_parts_are_sorted_and_centered(self):
        tpl = page_template.build(snapshot())
        self.assertEqual([p["ref"] for p in tpl["parts"]], ["C1", "U1"])
        u1 = next(p for p in tpl["parts"] if p["ref"] == "U1")
        self.assertEqual((u1["x"], u1["y"]), (130.0, 150.0))

    def test_nets_are_grouped_with_pin_numbers(self):
        tpl = page_template.build(snapshot())
        nets = {n["name"]: n["members"] for n in tpl["nets"]}
        self.assertEqual(nets["3V3"], [["C1", "1"], ["U1", "1"]])
        self.assertEqual(nets["GND"], [["C1", "2"], ["U1", "2"]])

    def test_explicit_nc_pins_are_recorded(self):
        tpl = page_template.build(snapshot())
        nets = {n["name"]: n["members"] for n in tpl["nets"]}
        self.assertEqual(nets["__NC__"], [["U1", "9"]])

    def test_bbox_covers_every_part(self):
        tpl = page_template.build(snapshot())
        self.assertEqual(tpl["bbox"], {"minX": 60, "minY": 100,
                                       "maxX": 160, "maxY": 200})

    def test_counts_and_determinism(self):
        a = page_template.build(snapshot())
        b = page_template.build(snapshot())
        self.assertEqual(a, b)
        self.assertEqual(a["counts"]["parts"], 2)
        self.assertEqual(a["counts"]["pins"], 5)  # incl. the explicit-NC pin

    def test_schema_and_grid(self):
        tpl = page_template.build(snapshot())
        self.assertEqual(tpl["schema"], page_template.SCHEMA)
        self.assertEqual(tpl["grid"], 5.0)


if __name__ == "__main__":
    unittest.main()
