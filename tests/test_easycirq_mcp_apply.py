import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "easycirq" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from easycirq_mcp import tools  # noqa: E402

PLAYBOOK = ROOT / "docs" / "round10" / "controlledB" / "c99-playbook.json"


def payload(result):
    return json.loads(result["content"][0]["text"])


def write_gate(folder, minutes=30):
    path = Path(folder) / "gate.json"
    expires = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    path.write_text(json.dumps({
        "schema": "easycirq-gate/v1", "project": "P", "page": "P1",
        "verdict": "PASS", "apply_allowed": True,
        "expires_at": expires.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }), encoding="utf-8")
    return path


class McpApplyTool(unittest.TestCase):
    def test_tool_is_listed_as_destructive(self):
        by_name = {tool["name"]: tool for tool in tools.list_tools()}
        self.assertIn("easycirq_apply", by_name)
        spec = by_name["easycirq_apply"]
        self.assertIs(spec["annotations"]["readOnlyHint"], False)
        self.assertIs(spec["annotations"]["destructiveHint"], True)

    def test_execute_without_gate_is_refused_before_running(self):
        if not PLAYBOOK.is_file():
            self.skipTest("no sample playbook")
        result = tools.call_tool("easycirq_apply",
                                 {"playbook": str(PLAYBOOK), "confirm": True})
        data = payload(result)
        self.assertTrue(data["is_error"])
        self.assertEqual(data["error"]["code"], "GATE_NOT_LIVE")

    def test_execute_with_expired_gate_is_refused(self):
        if not PLAYBOOK.is_file():
            self.skipTest("no sample playbook")
        with tempfile.TemporaryDirectory() as d:
            gate = write_gate(d, minutes=-5)
            result = tools.call_tool("easycirq_apply", {
                "playbook": str(PLAYBOOK), "confirm": True, "gate": str(gate)})
            data = payload(result)
            self.assertTrue(data["is_error"])
            self.assertEqual(data["error"]["code"], "GATE_NOT_LIVE")

    def test_dry_run_does_not_require_a_gate(self):
        if not PLAYBOOK.is_file():
            self.skipTest("no sample playbook")
        import shutil
        if not shutil.which("easycirq"):
            self.skipTest("easycirq CLI not on PATH")
        result = tools.call_tool("easycirq_apply",
                                 {"playbook": str(PLAYBOOK), "confirm": False})
        data = payload(result)
        self.assertFalse(data.get("is_error"), data)
        self.assertEqual(data["mode"], "dry_run")
        self.assertIn("exit_code", data)

    def test_missing_playbook_is_an_error(self):
        result = tools.call_tool("easycirq_apply", {
            "playbook": str(ROOT / "no-such-playbook.json"), "confirm": False})
        data = payload(result)
        self.assertTrue(data["is_error"])
        self.assertIn(data["error"]["code"], {"input_not_found", "APPLY_FAILED"})


if __name__ == "__main__":
    unittest.main()
