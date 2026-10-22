import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

os.environ.setdefault("PYTHONIOENCODING", "utf-8")

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "design-hardware" / "scripts" / "interface_contract_check.py"
ASSETS = ROOT / "design-hardware" / "assets" / "decisions"


def connector():
    return {
        "ref": "J1",
        "mpn": "FIXTURE-CONN",
        "pin_count": "2",
        "mating_part": "FIXTURE-MATE",
        "crimp_tool": "FIXTURE-TOOL",
        "view": "板端正视",
    }


def iface(**overrides):
    base = {
        "id": "IF-SIG",
        "connector": "J1",
        "connector_pin": "1",
        "net": "SIG",
        "domain": "3.3 V",
        "direction": "A->B",
        "drive": "push-pull",
        "drivers": ["U1.GPIO1"],
        "receivers": ["U2.GPIO1"],
        "multi_driver": False,
        "arbitration": "not_applicable",
        "thresholds": {
            "voh_min": "2.4 V",
            "vih_max": "2.0 V",
            "vol_max": "0.4 V",
            "vil_min": "0.8 V",
            "absolute_max": "3.6 V",
        },
        "leakage": "1 uA",
        "load": "<1 mA",
        "supply_state": "3.3 V 常开",
        "switchable": False,
        "off_behavior": "not_applicable",
        "owners": ["A（上拉）"],
        "state_behavior": {
            "A_reset": "高阻",
            "B_reset": "高阻",
            "A_off": "不得驱动",
            "B_off": "不得驱动",
        },
        "peer_obligations": ["B 在自身断电时释放"],
        "hotplug": {"user_accessible": False, "mating_sequence": "not_applicable"},
        "verification": "NOT RUN",
        "firmware": "GPIO1 输入",
        "change_triggers": ["换连接器/线束"],
        "basis": "fixture.md:1-2",
        "stale": False,
    }
    base.update(overrides)
    return base


def contract(interfaces=None, connectors=None, unresolved=None):
    return {
        "schema": "interface-contract/v1",
        "project": "FIXTURE",
        "revision": "R0",
        "connectors": [connector()] if connectors is None else connectors,
        "interfaces": [iface()] if interfaces is None else interfaces,
        "unresolved": [] if unresolved is None else unresolved,
    }


def child_env():
    env = os.environ.copy()
    env.pop("PYTHONIOENCODING", None)
    env.pop("PYTHONUTF8", None)
    env.pop("PYTHONLEGACYWINDOWSSTDIO", None)
    return env


def run_cli(payload, raw=None):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "contract.json"
        path.write_text(
            raw if raw is not None else json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), str(path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=child_env(),
        )
    return proc


def codes(result):
    return {finding["code"] for finding in result["findings"]}


class InterfaceContractPass(unittest.TestCase):
    def test_complete_fixture_exit_0(self):
        proc = run_cli(contract())
        self.assertEqual(proc.returncode, 0, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["findings"], [])
        self.assertFalse(result["board_verified"])
        self.assertEqual(result["execution"], "OFFLINE_PLANNING")
        self.assertEqual(result["hardware_execution"], "NOT RUN")
        self.assertTrue(result["not_checked"])
        self.assertEqual(result["summary"], {
            "interfaces": 1,
            "connectors": 1,
            "blocking": 0,
            "warning": 0,
            "unknown": 0,
        })


class InterfaceContractBlocking(unittest.TestCase):
    def test_multi_driver_without_arbitration_exit_1(self):
        item = iface(
            drivers=["U1.GPIO1", "U2.GPIO1"],
            multi_driver=True,
            arbitration="待查",
        )
        proc = run_cli(contract(interfaces=[item]))
        self.assertEqual(proc.returncode, 1, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["summary"]["blocking"], 1)
        self.assertEqual(codes(result), {"MULTI_DRIVER_NO_ARBITRATION"})

    def test_switchable_rail_without_off_behavior_exit_1(self):
        item = iface(switchable=True, off_behavior="待查")
        proc = run_cli(contract(interfaces=[item]))
        self.assertEqual(proc.returncode, 1, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result["summary"]["blocking"], 1)
        self.assertEqual(codes(result), {"SWITCHABLE_RAIL_NO_OFF_BEHAVIOR"})

    def test_user_hotplug_without_sequence_exit_1(self):
        item = iface(
            hotplug={"user_accessible": True, "mating_sequence": "待查"}
        )
        proc = run_cli(contract(interfaces=[item]))
        self.assertEqual(proc.returncode, 1, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result["summary"]["blocking"], 1)
        self.assertEqual(codes(result), {"HOTPLUG_NO_MATING_SEQUENCE"})


class InterfaceContractUnknown(unittest.TestCase):
    def test_stale_true_is_unknown_not_pass(self):
        proc = run_cli(contract(interfaces=[iface(stale=True)]))
        self.assertEqual(proc.returncode, 1, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result["status"], "needs_review")
        self.assertEqual(result["summary"]["blocking"], 0)
        self.assertEqual(codes(result), {"STALE_INTERFACE"})

    def test_unknown_thresholds_are_unknown(self):
        item = iface(
            thresholds={
                "voh_min": "待查",
                "vih_max": "待查",
                "vol_max": "待查",
                "vil_min": "待查",
                "absolute_max": "待查",
            }
        )
        proc = run_cli(contract(interfaces=[item]))
        self.assertEqual(proc.returncode, 1, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result["summary"]["blocking"], 0)
        self.assertEqual(result["summary"]["unknown"], 1)
        self.assertEqual(codes(result), {"MISSING_THRESHOLD"})

    def test_missing_groups_report_unknown(self):
        item = iface()
        del item["thresholds"]
        del item["state_behavior"]
        del item["peer_obligations"]
        del item["change_triggers"]
        del item["stale"]
        proc = run_cli(contract(interfaces=[item]))
        self.assertEqual(proc.returncode, 1, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result["summary"]["blocking"], 0)
        self.assertEqual(
            codes(result),
            {
                "MISSING_THRESHOLD",
                "STATE_BEHAVIOR_UNKNOWN",
                "MISSING_FIELD",
                "STALE_UNKNOWN",
            },
        )
        self.assertGreaterEqual(result["summary"]["unknown"], 4)

    def test_open_drain_without_owner_is_unknown(self):
        item = iface(drive="open-drain", owners=[])
        proc = run_cli(contract(interfaces=[item]))
        self.assertEqual(proc.returncode, 1, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result["summary"]["blocking"], 0)
        self.assertEqual(codes(result), {"OPEN_DRAIN_NO_OWNER"})

    def test_signal_without_driver_is_unknown(self):
        item = iface(drivers=[])
        proc = run_cli(contract(interfaces=[item]))
        self.assertEqual(proc.returncode, 1, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result["summary"]["blocking"], 0)
        self.assertEqual(codes(result), {"NO_DRIVER"})

    def test_unknown_connector_reference_is_unknown(self):
        item = iface(connector="J9")
        proc = run_cli(contract(interfaces=[item]))
        self.assertEqual(proc.returncode, 1, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result["summary"]["blocking"], 0)
        self.assertEqual(codes(result), {"UNKNOWN_CONNECTOR"})

    def test_empty_interfaces_is_warning_not_pass(self):
        proc = run_cli(contract(interfaces=[]))
        self.assertEqual(proc.returncode, 1, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result["status"], "needs_review")
        self.assertEqual(result["summary"]["warning"], 1)
        self.assertEqual(codes(result), {"NO_INTERFACES"})


class InterfaceContractInvalidInput(unittest.TestCase):
    def test_malformed_json_exit_2(self):
        proc = run_cli(None, raw="{")
        self.assertEqual(proc.returncode, 2, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result["status"], "invalid_input")
        self.assertEqual(result["error"]["code"], "invalid_input")
        self.assertFalse(result["board_verified"])

    def test_wrong_schema_exit_2(self):
        payload = contract()
        payload["schema"] = "interface-contract/v2"
        proc = run_cli(payload)
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertIn("schema", json.loads(proc.stdout)["error"]["message"])

    def test_interfaces_not_array_exit_2(self):
        payload = contract()
        payload["interfaces"] = {}
        proc = run_cli(payload)
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["status"], "invalid_input")

    def test_invalid_direction_exit_2(self):
        payload = contract(interfaces=[iface(direction="sideways")])
        proc = run_cli(payload)
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertIn("direction", json.loads(proc.stdout)["error"]["message"])

    def test_invalid_drive_exit_2(self):
        payload = contract(interfaces=[iface(drive="totem")])
        proc = run_cli(payload)
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertIn("drive", json.loads(proc.stdout)["error"]["message"])

    def test_duplicate_json_key_exit_2(self):
        proc = run_cli(None, raw='{"schema": "interface-contract/v1", "interfaces": [], "interfaces": []}')
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertIn("duplicate JSON key", json.loads(proc.stdout)["error"]["message"])

    def test_missing_file_exit_2(self):
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), str(ROOT / "does-not-exist.json")],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=child_env(),
        )
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(json.loads(proc.stdout)["status"], "invalid_input")


class DecisionsAssets(unittest.TestCase):
    def test_templates_parse_and_keep_agent_note(self):
        for name, schema in (
            ("state-transition.template.json", "state-transition/v1"),
            ("interface-contract.template.json", "interface-contract/v1"),
        ):
            path = ASSETS / name
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["schema"], schema)
            self.assertIn("Agent 填写，用户不填", data["_note"])

    def test_state_example_has_axes_and_complete_records(self):
        path = ASSETS / "state-transition.r4p2.example.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["schema"], "state-transition/v1")
        self.assertEqual(set(data["axes"]), {
            "product_state",
            "supply_condition",
            "reset_cause",
        })
        states = data["states"]
        transitions = data["transitions"]
        self.assertGreaterEqual(len(states), 10)
        self.assertGreaterEqual(len(transitions), 10)
        for state in states:
            for field in ("id", "entry", "exit", "completion"):
                self.assertTrue(state[field].strip())
        for transition in transitions:
            for field in (
                "id",
                "from",
                "to",
                "trigger",
                "supply_change",
                "control",
                "load_state",
                "completion",
                "abort",
            ):
                self.assertTrue(transition[field].strip())
        state_ids = {state["id"] for state in states}
        self.assertTrue(all(t["from"] in state_ids for t in transitions))
        self.assertTrue(all(t["to"] in state_ids for t in transitions))
        matrix_ids = {row["state"] for row in data["state_interface_matrix"]}
        self.assertEqual(matrix_ids, state_ids)
        self.assertFalse(data["upgrade"]["applicable"])
        self.assertEqual(data["upgrade"]["acceptance"], "NOT RUN")
        self.assertEqual(data["upgrade"]["coverage"], "PARTIAL")

    def test_interface_example_is_blocked_not_passed(self):
        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                str(ASSETS / "interface-contract.r4p4.example.json"),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=child_env(),
        )
        self.assertEqual(proc.returncode, 1, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["summary"]["interfaces"], 10)
        self.assertEqual(result["summary"]["blocking"], 2)
        self.assertEqual(
            codes(result),
            {
                "MULTI_DRIVER_NO_ARBITRATION",
                "SWITCHABLE_RAIL_NO_OFF_BEHAVIOR",
                "MISSING_FIELD",
                "MISSING_THRESHOLD",
                "CONNECTOR_FIELD_UNKNOWN",
                "STATE_BEHAVIOR_UNKNOWN",
                "UNRESOLVED_ITEM",
            },
        )
        self.assertFalse(result["board_verified"])


DOCS = ROOT / "design-hardware" / "references" / "decisions"
CASES = DOCS / "cases"


def frontmatter(path):
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---", 4)
    data = {}
    for line in text[4:end].splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            data[key.strip()] = value.strip()
    return data


def section_body_lines(text, heading):
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(heading))
    end = next(
        (i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")),
        len(lines),
    )
    return [line for line in lines[start + 1:end] if line.strip()]


class ReferenceAndCaseDocuments(unittest.TestCase):
    """C/E 的参考文档与案例必须被直接读取，而不是只测脚本。"""

    REFS = {
        "c01-state-transition-contract.md": {
            "id": "R4-C01",
            "package": "[C]",
            "keywords": ["reset_cause", "POR", "applicable", "PARTIAL"],
        },
        "e01-interface-contract.md": {
            "id": "R4-E01",
            "package": "[E]",
            "keywords": ["connector_pin", "off_behavior", "blocking", "stale"],
        },
    }
    CASES = {
        "r4-case-c01-battery-plus-external-supply-states.md": {
            "id": "R4-CASE-C01",
            "project": "R4-P2",
            "keywords": ["product_state", "supply_condition", "reset_cause", "applicable:false", "NOT RUN"],
        },
        "r4-case-e01-multiboard-interface-contract.md": {
            "id": "R4-CASE-E01",
            "project": "R4-P4",
            "keywords": ["blocking", "off_behavior", "unknown", "NOT RUN"],
        },
    }

    def test_reference_documents(self):
        for name, spec in self.REFS.items():
            path = DOCS / name
            text = path.read_text(encoding="utf-8")
            meta = frontmatter(path)
            with self.subTest(name=name):
                self.assertEqual(meta.get("id"), spec["id"])
                self.assertEqual(meta.get("packages"), spec["package"])
                self.assertTrue(meta.get("sources"))
                self.assertGreaterEqual(len(text.splitlines()), 60)
                self.assertLessEqual(len(text.splitlines()), 110)
                for heading in [f"## {i}." for i in range(1, 11)]:
                    self.assertIn(heading, text)
                for keyword in spec["keywords"]:
                    self.assertIn(keyword, text)
                self.assertLessEqual(len(section_body_lines(text, "## 9.")), 8)
                self.assertGreaterEqual(
                    len(re.findall(r"`[^`]+\.md:\d+(?:-\d+)?`", text)), 2
                )

    def test_case_documents(self):
        for name, spec in self.CASES.items():
            path = CASES / name
            text = path.read_text(encoding="utf-8")
            meta = frontmatter(path)
            with self.subTest(name=name):
                self.assertEqual(meta.get("id"), spec["id"])
                self.assertEqual(meta.get("project"), spec["project"])
                self.assertEqual(meta.get("execution"), "OFFLINE_PLANNING")
                self.assertEqual(meta.get("hardware_execution"), "NOT RUN")
                self.assertTrue(meta.get("record_types"))
                self.assertTrue(meta.get("facts_source"))
                self.assertGreaterEqual(len(text.splitlines()), 50)
                self.assertLessEqual(len(text.splitlines()), 100)
                for heading in [f"## {i}." for i in range(1, 10)]:
                    self.assertIn(heading, text)
                for keyword in spec["keywords"]:
                    self.assertIn(keyword, text)


if __name__ == "__main__":
    unittest.main()
