import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "easycirq" / "scripts"
TOOL = SCRIPTS / "sch_decoupling_metrics.py"

sys.path.insert(0, str(SCRIPTS))
import sch_decoupling_metrics as tool  # noqa: E402


def ir(components, connections, nets):
    return {"schemaVersion": 1, "components": components,
            "connections": connections, "nets": nets}


def comp(cid, ref, pins):
    return {"id": cid, "ref": ref,
            "pins": [{"number": n, "name": name} for n, name in pins]}


def conn(cid, pin, net):
    return {"componentId": cid, "pinNumber": str(pin), "netId": net}


class DecouplingMetrics(unittest.TestCase):
    def test_ic_power_pin_with_cap_is_covered(self):
        report = tool.analyze(ir(
            [comp("u1", "U1", [("1", "VCC"), ("2", "GND")]),
             comp("c1", "C1", [("1", "1"), ("2", "2")])],
            [conn("u1", 1, "vcc"), conn("c1", 1, "vcc"),
             conn("u1", 2, "gnd"), conn("c1", 2, "gnd")],
            [{"id": "vcc", "name": "3V3"}, {"id": "gnd", "name": "GND"}]))
        self.assertEqual(report["verdict"], "pass")
        self.assertEqual(report["metrics"]["power_pins_checked"], 1)
        self.assertEqual(report["metrics"]["decap_missing"], 0)

    def test_ic_power_pin_without_cap_fails(self):
        report = tool.analyze(ir(
            [comp("u1", "U1", [("1", "VCC")]), comp("u2", "U2", [("1", "1")])],
            [conn("u1", 1, "vcc"), conn("u2", 1, "vcc")],
            [{"id": "vcc", "name": "3V3"}]))
        self.assertEqual(report["verdict"], "fail")
        self.assertEqual(report["metrics"]["decap_missing"], 1)
        self.assertEqual(report["findings"][0]["code"], "decap_missing")

    def test_connector_power_pin_is_not_a_target(self):
        report = tool.analyze(ir(
            [comp("j1", "J1", [("1", "VBUS")]), comp("u1", "U1", [("1", "1")])],
            [conn("j1", 1, "vbus"), conn("u1", 1, "vbus")],
            [{"id": "vbus", "name": "VBUS"}]))
        self.assertEqual(report["metrics"]["power_pins_checked"], 0)
        self.assertEqual(report["verdict"], "pass")

    def test_unconnected_power_pin_counts_as_missing(self):
        report = tool.analyze(ir(
            [comp("u1", "U1", [("1", "VCC")])], [],
            [{"id": "vcc", "name": "3V3"}]))
        self.assertEqual(report["metrics"]["decap_missing"], 1)

    def test_nc_power_pin_is_skipped(self):
        listing = {"result": {"components": [{
            "designator": "U1",
            "pins": [{"pinNumber": "1", "noConnected": True}]}]}}
        report = tool.analyze(ir(
            [comp("u1", "U1", [("1", "VCC")])], [],
            [{"id": "vcc", "name": "3V3"}]), listing)
        self.assertEqual(report["metrics"]["power_pins_checked"], 0)

    def test_cli(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "ir.json"
            src.write_text(json.dumps(ir(
                [comp("u1", "U1", [("1", "VCC")]), comp("u2", "U2", [("1", "1")])],
                [conn("u1", 1, "vcc"), conn("u2", 1, "vcc")],
                [{"id": "vcc", "name": "3V3"}])), encoding="utf-8")
            run = subprocess.run([sys.executable, str(TOOL), "--input", str(src),
                                  "--json"], capture_output=True, text=True,
                                 encoding="utf-8")
            self.assertEqual(run.returncode, 1, run.stderr)
            self.assertEqual(json.loads(run.stdout)["metrics"]["decap_missing"], 1)


if __name__ == "__main__":
    unittest.main()
