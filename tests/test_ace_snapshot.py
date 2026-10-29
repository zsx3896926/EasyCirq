"""Tests for the ACE snapshot builder normalization (offline, no EDA)."""

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import ace_snapshot as snap  # noqa: E402


class PlaceholderTests(unittest.TestCase):
    def test_unresolved_parameters_are_dropped(self):
        self.assertIsNone(snap._real_or_none("={Value}"))
        self.assertIsNone(snap._real_or_none("={Manufacturer Part}"))
        self.assertIsNone(snap._real_or_none("  "))
        self.assertIsNone(snap._real_or_none(None))

    def test_real_values_are_kept(self):
        self.assertEqual(snap._real_or_none("100nF"), "100nF")
        self.assertEqual(snap._real_or_none("BQ24074RGTR"), "BQ24074RGTR")


class ComponentNormalizationTests(unittest.TestCase):
    def _raw(self):
        return {"designator": "U1",
                "component": {"name": "BQ24074RGTR"},
                "device": {"name": "={Manufacturer Part}"},
                "bbox": {"minX": 0, "minY": 0, "maxX": 10, "maxY": 10}}

    def test_placeholder_value_becomes_none_but_mpn_survives(self):
        comp = snap._component(self._raw(), {"U1": []}, {})
        self.assertIsNone(comp["value"])
        self.assertEqual(comp["mpn"], "BQ24074RGTR")

    def test_pin_net_and_nc_are_preserved(self):
        pins = [{"number": "1", "name": "VDD", "nc": False},
                {"number": "2", "name": "NC", "nc": True}]
        comp = snap._component(self._raw(), {"U1": pins},
                               {("U1", "1"): "3V3"})
        by_num = {p["number"]: p for p in comp["pins"]}
        self.assertEqual(by_num["1"]["net"], "3V3")
        self.assertFalse(by_num["1"]["nc"])
        self.assertTrue(by_num["2"]["nc"])


class NetVoltageTests(unittest.TestCase):
    def test_common_rail_names(self):
        self.assertEqual(snap.infer_net_voltage("3V3"), 3.3)
        self.assertEqual(snap.infer_net_voltage("+5V"), 5.0)
        self.assertEqual(snap.infer_net_voltage("VBUS"), 5.0)
        self.assertIsNone(snap.infer_net_voltage("I2C_SCL"))


if __name__ == "__main__":
    unittest.main()
