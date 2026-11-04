"""Tests for functional subdivision into finer frames (offline)."""

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import subdivide  # noqa: E402


def comp(ref, *nets):
    return {"ref": ref, "bbox": {"minX": 0, "minY": 0, "maxX": 10, "maxY": 10},
            "pins": [{"number": str(i + 1), "net": net} for i, net in enumerate(nets)]}


SNAP = {"components": [
    comp("U1", "VBUS", "GND", "U1_ILIM", "U1_ISET", "VSYS"),
    comp("R4", "U1_ILIM", "GND"),
    comp("R5", "U1_ISET", "GND"),
    comp("C2", "VBUS", "GND"),
    comp("C3", "VSYS", "GND"),
    comp("U2", "VSYS", "GND", "U2_FB"),
    comp("R9", "U2_FB", "GND"),
    comp("L1", "U2_SW", "VBUS"),
]}

IFACE = {"components": [
    comp("J2", "GND", "3V3", "EXT_5V_EN"),
    comp("TP1", "+3V3", "GND"),
    comp("TP2", "+5V", "GND"),
    comp("D1", "GND", "AUDIO_I2C_SDA"),
    comp("D2", "GND", "AUDIO_I2C_SCL"),
]}


class SubdivideTests(unittest.TestCase):
    def test_core_get_their_net_attached_passives(self):
        subs = subdivide.subdivide(SNAP, {"id": "block.x", "designators":
                                          ["U1", "R4", "R5", "C2", "C3", "U2", "R9", "L1"]})
        by_id = {s["id"]: s for s in subs}
        u1 = by_id["block.x::U1"]
        self.assertIn("R4", u1["designators"])
        self.assertIn("R5", u1["designators"])
        self.assertNotIn("C2", u1["designators"])     # C2 only touches rails
        u2 = by_id["block.x::U2"]
        self.assertIn("R9", u2["designators"])
        # L1 only touches rails/SW -> it is not part of U2's core module
        self.assertNotIn("L1", u2["designators"])

    def test_rail_only_passives_become_decoupling_module(self):
        subs = subdivide.subdivide(SNAP, {"id": "block.x", "designators":
                                          ["U1", "R4", "R5", "C2", "C3"]})
        titles = {s["title"] for s in subs}
        self.assertIn("去耦/滤波", titles)

    def test_interface_group_splits_by_family(self):
        subs = subdivide.subdivide(IFACE, {"id": "group.iface", "designators":
                                           ["J2", "TP1", "TP2", "D1", "D2", "D3"]})
        titles = {s["title"] for s in subs}
        self.assertIn("测试点", titles)
        self.assertIn("ESD 保护", titles)
        # a lone connector is folded into the biggest sibling instead of a tiny card
        refs = [ref for s in subs for ref in s["designators"]]
        self.assertIn("J2", refs)

    def test_every_part_appears_exactly_once(self):
        subs = subdivide.subdivide(SNAP, {"id": "g", "designators":
                                          list({c["ref"] for c in SNAP["components"]})})
        refs = [ref for s in subs for ref in s["designators"]]
        self.assertEqual(sorted(refs), sorted({c["ref"] for c in SNAP["components"]}))
        self.assertEqual(len(refs), len(set(refs)))

    def test_rails_do_not_glue_everything(self):
        subs = subdivide.subdivide(SNAP, {"id": "g", "designators":
                                          ["U1", "U2", "C2", "C3"]})
        self.assertGreaterEqual(len(subs), 1)

    def test_empty_group_returns_nothing(self):
        self.assertEqual(subdivide.subdivide(SNAP, {"id": "g", "designators": []}), [])


if __name__ == "__main__":
    unittest.main()
