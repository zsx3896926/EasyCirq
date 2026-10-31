import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "easycirq" / "scripts"
TOOL = SCRIPTS / "sch_connectivity_metrics.py"

sys.path.insert(0, str(SCRIPTS))
import sch_connectivity_metrics as tool  # noqa: E402


def ir(components, connections, nets):
    return {"schemaVersion": 1, "components": components,
            "connections": connections, "nets": nets}


def comp(cid, ref, pins):
    return {"id": cid, "ref": ref,
            "pins": [{"number": n, "name": n} for n in pins]}


class ConnectivityMetrics(unittest.TestCase):
    def test_clean_ir_passes(self):
        report = tool.analyze(ir(
            [comp("u1", "U1", ["1", "2"]), comp("u2", "U2", ["1", "2"])],
            [{"componentId": "u1", "pinNumber": "1", "netId": "n1"},
             {"componentId": "u2", "pinNumber": "1", "netId": "n1"},
             {"componentId": "u1", "pinNumber": "2", "netId": "n2"},
             {"componentId": "u2", "pinNumber": "2", "netId": "n2"}],
            [{"id": "n1", "name": "A"}, {"id": "n2", "name": "B"}]))
        self.assertEqual(report["verdict"], "pass")
        self.assertEqual(report["metrics"]["floating_pins"], 0)

    def test_floating_pin_and_single_node_net(self):
        report = tool.analyze(ir(
            [comp("u1", "U1", ["1", "2"])],
            [{"componentId": "u1", "pinNumber": "1", "netId": "n1"}],
            [{"id": "n1", "name": "A"}]))
        self.assertEqual(report["verdict"], "fail")
        self.assertEqual(report["metrics"]["floating_pins"], 1)
        self.assertEqual(report["metrics"]["single_node_nets"], 1)
        codes = {f["code"] for f in report["findings"]}
        self.assertEqual(codes, {"floating_pin", "single_node_net"})

    def test_bus_member_gap_is_an_error(self):
        nets = [{"id": f"n{i}", "name": f"DATA[{i}]"} for i in (0, 2)]
        nets.append({"id": "gnd", "name": "GND"})
        conns = [
            {"componentId": "u1", "pinNumber": "0", "netId": "n0"},
            {"componentId": "u2", "pinNumber": "0", "netId": "n0"},
            {"componentId": "u1", "pinNumber": "1", "netId": "n2"},
            {"componentId": "u2", "pinNumber": "1", "netId": "n2"},
            {"componentId": "u1", "pinNumber": "2", "netId": "gnd"},
            {"componentId": "u2", "pinNumber": "2", "netId": "gnd"},
        ]
        report = tool.analyze(ir(
            [comp("u1", "U1", ["0", "1", "2"]), comp("u2", "U2", ["0", "1", "2"])],
            conns, nets))
        self.assertEqual(report["metrics"]["bus_members_missing"], 1)
        codes = {f["code"] for f in report["findings"]}
        self.assertIn("bus_member_missing", codes)

    def test_lone_diff_suffix_is_warning_not_error(self):
        report = tool.analyze(ir(
            [comp("u1", "U1", ["1", "2"]), comp("u2", "U2", ["1", "2"])],
            [{"componentId": "u1", "pinNumber": "1", "netId": "n1"},
             {"componentId": "u2", "pinNumber": "1", "netId": "n1"},
             {"componentId": "u1", "pinNumber": "2", "netId": "n2"},
             {"componentId": "u2", "pinNumber": "2", "netId": "n2"}],
            [{"id": "n1", "name": "VBAT_P"}, {"id": "n2", "name": "GND"}]))
        self.assertEqual(report["verdict"], "pass")
        self.assertEqual(report["metrics"]["diff_pair_mismatch"], 0)
        self.assertEqual(report["findings"][0]["severity"], "warning")

    def test_global_single_member_net_is_not_a_dangling_name(self):
        report = tool.analyze(ir(
            [comp("u1", "U1", ["1", "2"]), comp("u2", "U2", ["1"])],
            [{"componentId": "u1", "pinNumber": "1", "netId": "n1"},
             {"componentId": "u1", "pinNumber": "2", "netId": "n2"},
             {"componentId": "u2", "pinNumber": "1", "netId": "n2"}],
            [{"id": "n1", "name": "VBUS", "scope": "global"},
             {"id": "n2", "name": "LOCALX", "scope": "local"}]))
        # VBUS is global and lives on another page too; LOCALX is not
        self.assertEqual(report["metrics"]["single_node_nets"], 0)
        self.assertEqual(report["metrics"]["global_single_nets"], 1)
        self.assertEqual(report["verdict"], "pass")

    def test_local_single_member_net_is_an_error(self):
        report = tool.analyze(ir(
            [comp("u1", "U1", ["1", "2"]), comp("u2", "U2", ["1"])],
            [{"componentId": "u1", "pinNumber": "1", "netId": "n1"},
             {"componentId": "u1", "pinNumber": "2", "netId": "n2"},
             {"componentId": "u2", "pinNumber": "1", "netId": "n2"}],
            [{"id": "n1", "name": "BB_VIN", "scope": "local"},
             {"id": "n2", "name": "GND", "scope": "global"}]))
        self.assertEqual(report["metrics"]["single_node_nets"], 1)
        self.assertEqual(report["verdict"], "fail")

    def test_auto_net_residue_and_duplicate_names(self):
        report = tool.analyze(ir(
            [comp("u1", "U1", ["1", "2", "3"]), comp("u2", "U2", ["1", "2", "3"])],
            [{"componentId": "u1", "pinNumber": "1", "netId": "n1"},
             {"componentId": "u2", "pinNumber": "1", "netId": "n1"},
             {"componentId": "u1", "pinNumber": "2", "netId": "n2"},
             {"componentId": "u2", "pinNumber": "2", "netId": "n2"},
             {"componentId": "u1", "pinNumber": "3", "netId": "n3"},
             {"componentId": "u2", "pinNumber": "3", "netId": "n3"}],
            [{"id": "n1", "name": "NET0001", "scope": "local"},
             {"id": "n2", "name": "GND", "scope": "global"},
             {"id": "n3", "name": "GND", "scope": "global"}]))
        self.assertEqual(report["metrics"]["auto_net_residue"], 1)
        self.assertEqual(report["metrics"]["duplicate_net_names"], 1)
        codes = {f["code"] for f in report["findings"]}
        self.assertIn("auto_net_residue", codes)
        self.assertIn("duplicate_net_name", codes)

    def test_clean_names_have_no_naming_findings(self):
        report = tool.analyze(ir(
            [comp("u1", "U1", ["1", "2"]), comp("u2", "U2", ["1", "2"])],
            [{"componentId": "u1", "pinNumber": "1", "netId": "n1"},
             {"componentId": "u2", "pinNumber": "1", "netId": "n1"},
             {"componentId": "u1", "pinNumber": "2", "netId": "n2"},
             {"componentId": "u2", "pinNumber": "2", "netId": "n2"}],
            [{"id": "n1", "name": "VBUS", "scope": "global"},
             {"id": "n2", "name": "GND", "scope": "global"}]))
        self.assertEqual(report["metrics"]["auto_net_residue"], 0)
        self.assertEqual(report["metrics"]["duplicate_net_names"], 0)

    def test_invalid_ir_is_rejected(self):
        with self.assertRaises(ValueError):
            tool.analyze({"components": []})

    def test_explicit_nc_pin_is_not_floating(self):
        listing = {"result": {"components": [{
            "designator": "U1",
            "pins": [{"pinNumber": "1", "noConnected": True},
                     {"pinNumber": "2", "noConnected": False}],
        }]}}
        report = tool.analyze(ir(
            [comp("u1", "U1", ["1", "2"]), comp("u2", "U2", ["1"])],
            [{"componentId": "u1", "pinNumber": "2", "netId": "n1"},
             {"componentId": "u2", "pinNumber": "1", "netId": "n1"}],
            [{"id": "n1", "name": "A"}]), listing)
        self.assertEqual(report["metrics"]["floating_pins"], 0)
        self.assertEqual(report["metrics"]["nc_pins"], 1)
        self.assertEqual(report["summary"]["nc_source"], "passed")

    def test_without_list_nc_cannot_be_excluded(self):
        report = tool.analyze(ir(
            [comp("u1", "U1", ["1", "2"]), comp("u2", "U2", ["1"])],
            [{"componentId": "u1", "pinNumber": "2", "netId": "n1"},
             {"componentId": "u2", "pinNumber": "1", "netId": "n1"}],
            [{"id": "n1", "name": "A"}]))
        # pin 1 looks floating: the IR alone cannot prove it is NC
        self.assertEqual(report["metrics"]["floating_pins"], 1)
        self.assertEqual(report["summary"]["nc_source"], "absent")
        self.assertIn("可能偏高", report["note"])

    def test_cli_report_is_kpi_compatible(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "ir.json"
            out = Path(d) / "check.json"
            src.write_text(json.dumps(ir(
                [comp("u1", "U1", ["1", "2"])],
                [{"componentId": "u1", "pinNumber": "1", "netId": "n1"},
                 {"componentId": "u1", "pinNumber": "2", "netId": "n1"}],
                [{"id": "n1", "name": "A"}])), encoding="utf-8")
            run = subprocess.run([sys.executable, str(TOOL), "--input", str(src),
                                  "--out", str(out), "--json"],
                                 capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(run.returncode, 0, run.stderr)
            report = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(report["schema"], tool.SCHEMA)
            self.assertIn("floating_pins", report["metrics"])

            bad = Path(d) / "bad.json"
            bad.write_text("{}", encoding="utf-8")
            run = subprocess.run([sys.executable, str(TOOL), "--input", str(bad)],
                                 capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(run.returncode, 2)


if __name__ == "__main__":
    unittest.main()
