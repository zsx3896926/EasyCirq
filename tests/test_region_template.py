"""Tests for the region template builder (offline)."""

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import region_template  # noqa: E402


def comp(ref, cx, cy, net="3V3", pin="1"):
    return {"ref": ref, "value": None, "mpn": None,
            "bbox": {"minX": cx - 10, "minY": cy - 10,
                     "maxX": cx + 10, "maxY": cy + 10},
            "pins": [{"number": pin, "name": pin, "net": net}]}


def snapshot():
    return {
        "schema": "easycirq-ace-snapshot/v1", "page": "p1",
        "components": [
            comp("U1", 100, 100, "3V3"),
            comp("C_LOCAL", 140, 100, "GND"),        # within radius
            comp("C_FAR", 500, 500, "3V3"),          # outside radius
            comp("U2", 520, 500, "5V"),              # outside radius
        ],
    }


class RegionTemplateTests(unittest.TestCase):
    def test_select_keeps_seed_and_local_parts(self):
        keep = region_template.select(snapshot(), ["U1"], 100)
        self.assertIn("U1", keep)
        self.assertIn("C_LOCAL", keep)
        self.assertNotIn("C_FAR", keep)
        self.assertNotIn("U2", keep)

    def test_build_marks_seed_and_radius(self):
        tpl = region_template.build(snapshot(), ["U1"], 100)
        self.assertEqual(tpl["seed"], ["U1"])
        self.assertEqual(tpl["radius"], 100.0)
        self.assertEqual(tpl["schema"], region_template.SCHEMA)

    def test_build_has_same_shape_as_page_template(self):
        tpl = region_template.build(snapshot(), ["U1"], 100)
        self.assertIn("parts", tpl)
        self.assertIn("nets", tpl)
        self.assertIn("bbox", tpl)
        refs = {p["ref"] for p in tpl["parts"]}
        self.assertEqual(refs, {"U1", "C_LOCAL"})

    def test_counts_reflect_selection(self):
        tpl = region_template.build(snapshot(), ["U1"], 100)
        self.assertEqual(tpl["counts"]["parts"], 2)
        self.assertEqual(tpl["counts"]["selected"], 2)

    def test_unknown_seed_raises(self):
        with self.assertRaises(ValueError):
            region_template.build(snapshot(), ["NOPE"], 100)

    def test_deterministic(self):
        a = region_template.build(snapshot(), ["U1"], 100)
        b = region_template.build(snapshot(), ["U1"], 100)
        self.assertEqual(a, b)


class RegionClosureTests(unittest.TestCase):
    def test_signal_net_pulls_in_connected_part(self):
        snap = {"schema": "easycirq-ace-snapshot/v1", "page": "p",
                "components": [
                    comp("U1", 100, 100, "SPK_P"),
                    comp("C_LOCAL", 140, 100, "GND"),
                    comp("U_FAR", 900, 900, "SPK_P"),   # same signal net
                ]}
        tpl = region_template.build(snap, ["U1"], 100)
        refs = {p["ref"] for p in tpl["parts"]}
        self.assertIn("U_FAR", refs)          # closed through the signal net

    def test_power_net_does_not_pull_in_far_parts(self):
        snap = {"schema": "easycirq-ace-snapshot/v1", "page": "p",
                "components": [
                    comp("U1", 100, 100, "3V3"),
                    comp("C_LOCAL", 140, 100, "GND"),
                    comp("U_FAR", 900, 900, "3V3"),     # power rail: exempt
                ]}
        tpl = region_template.build(snap, ["U1"], 100)
        refs = {p["ref"] for p in tpl["parts"]}
        self.assertNotIn("U_FAR", refs)

    def test_close_false_keeps_raw_selection(self):
        snap = {"schema": "easycirq-ace-snapshot/v1", "page": "p",
                "components": [
                    comp("U1", 100, 100, "SPK_P"),
                    comp("U_FAR", 900, 900, "SPK_P"),
                ]}
        tpl = region_template.build(snap, ["U1"], 100, close=False)
        self.assertEqual({p["ref"] for p in tpl["parts"]}, {"U1"})


if __name__ == "__main__":
    unittest.main()
