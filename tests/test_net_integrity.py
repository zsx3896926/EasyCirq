"""Tests for the deterministic net-integrity audit (offline)."""

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import net_integrity  # noqa: E402


def comp(ref, pins):
    return {"ref": ref,
            "bbox": {"minX": 0, "minY": 0, "maxX": 10, "maxY": 10},
            "pins": pins}


def pin(number, name, net):
    return {"number": str(number), "name": name, "net": net}


def snapshot():
    return {"schema": "easycirq-ace-snapshot/v1", "page": "1",
            "components": [
                comp("U1", [pin(1, "VDD", "3V3"), pin(2, "SCL", "I2C_SCL"),
                            pin(3, "DEAD", "ONLY_ME")]),
                comp("C1", [pin(1, "1", "3V3"), pin(2, "2", "GND")]),
                comp("R1", [pin(1, "1", "I2C_SCL"), pin(2, "2", "3V3")]),
                comp("J1", [pin(1, "1", "GND")]),
            ]}


class NetIntegrityTests(unittest.TestCase):
    def test_single_member_net_is_an_error(self):
        report = net_integrity.audit(snapshot())
        self.assertEqual(report["counts"]["errors"], 1)
        finding = report["findings"][0]
        self.assertEqual(finding["code"], "single-pin-net")
        self.assertEqual(finding["net"], "ONLY_ME")
        self.assertEqual(finding["ref"], "U1")

    def test_multi_member_nets_are_fine(self):
        report = net_integrity.audit(snapshot())
        nets = {f["net"] for f in report["findings"] if f["code"] == "single-pin-net"}
        self.assertNotIn("3V3", nets)
        self.assertNotIn("I2C_SCL", nets)

    def test_verdict_blocks_on_dead_net(self):
        report = net_integrity.audit(snapshot())
        self.assertEqual(report["verdict"], "blocked")

    def test_clean_snapshot_passes(self):
        snap = snapshot()
        snap["components"][0]["pins"] = [
            pin(1, "VDD", "3V3"), pin(2, "SCL", "I2C_SCL")]
        report = net_integrity.audit(snap)
        self.assertEqual(report["verdict"], "pass")
        self.assertEqual(report["counts"]["errors"], 0)

    def test_net_name_variants_warn(self):
        snap = snapshot()
        snap["components"][1]["pins"][0]["net"] = "+3V3"
        report = net_integrity.audit(snap)
        codes = [f["code"] for f in report["findings"]]
        self.assertIn("net-name-variant", codes)

    def test_deterministic(self):
        self.assertEqual(net_integrity.audit(snapshot()), net_integrity.audit(snapshot()))


class DeadNetActionTests(unittest.TestCase):
    def test_interface_net_is_port_ized(self):
        self.assertEqual(net_integrity.classify("I2S_MCLK", "U1", "MCLK"),
                         "port_ize")
        self.assertEqual(net_integrity.classify("SD_SCK", "J1", "CLX"),
                         "port_ize")

    def test_enable_net_gets_driver(self):
        self.assertEqual(net_integrity.classify("EXT_5V_EN", "U2", "EN"),
                         "connect_driver")
        self.assertEqual(net_integrity.classify("PWR_EN", "R1", "1"),
                         "connect_driver")

    def test_dangling_part_action(self):
        self.assertEqual(net_integrity.classify("TP_C13_1", "C13", "1"),
                         "remove_dangling_part_or_connect")

    def test_audit_emits_one_action_per_dead_net(self):
        report = net_integrity.audit(snapshot())
        dead = [f for f in report["findings"] if f["code"] == "single-pin-net"]
        self.assertEqual(len(report["actions"]), len(dead))
        self.assertTrue(all(a["net"] and a["type"] for a in report["actions"]))


if __name__ == "__main__":
    unittest.main()
