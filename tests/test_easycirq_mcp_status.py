import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "easycirq" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from easycirq_mcp import tools  # noqa: E402

REPORT = ROOT / "reports" / "p1-pipeline" / "kpi-report.json"


def payload(result):
    return json.loads(result["content"][0]["text"])


class McpStatusTools(unittest.TestCase):
    def test_tools_are_listed(self):
        names = {tool["name"] for tool in tools.list_tools()}
        self.assertIn("easycirq_status", names)
        self.assertIn("easycirq_card", names)
        self.assertIn("easycirq_setup", names)
        for tool in tools.list_tools():
            self.assertIn("inputSchema", tool)
            self.assertIn("annotations", tool)

    def test_status_reports_blocked_for_the_live_p1_report(self):
        if not REPORT.is_file():
            self.skipTest("live P1 report not present")
        result = tools.call_tool("easycirq_status", {"kpi_report": str(REPORT)})
        data = payload(result)
        self.assertEqual(data["state"], "blocked")
        self.assertIn("next", data)
        self.assertTrue(data["offline"])
        self.assertEqual(data["eda"], "NOT RUN")
        # missing evidence is separate from defects
        self.assertTrue(any(b["kpi"] == "unconnected" for b in data["blockers"]))
        self.assertTrue(any(m["kpi"] == "pin_mux" for m in data["missing"]))

    def test_card_reports_not_ready(self):
        if not REPORT.is_file():
            self.skipTest("live P1 report not present")
        result = tools.call_tool("easycirq_card", {"kpi_report": str(REPORT)})
        data = payload(result)
        self.assertEqual(data["state"], "blocked")
        self.assertIn("还不能打样", data["headline"])

    def test_card_requires_a_report(self):
        from easycirq_mcp.errors import InvalidParams
        with self.assertRaises(InvalidParams):
            tools.call_tool("easycirq_card", {})

    def test_unreadable_report_is_an_error_not_a_pass(self):
        result = tools.call_tool("easycirq_status",
                                 {"kpi_report": str(ROOT / "no-such-report.json")})
        data = payload(result)
        self.assertTrue(data["is_error"])
        self.assertIn(data["error"]["code"],
                      {"input_not_found", "KPI_REPORT_UNREADABLE"})

    def test_setup_reads_the_local_installation(self):
        # this tool shells out to the local CLI; skip when it is not installed
        import shutil
        if not shutil.which("easycirq"):
            self.skipTest("easycirq CLI not on PATH")
        result = tools.call_tool("easycirq_setup", {"timeout_s": 60})
        data = payload(result)
        if data.get("is_error"):
            self.fail(f"setup tool failed: {data['error']}")
        self.assertIn(data["state"], ("ready", "not_ready"))
        self.assertFalse(data["offline"])  # honest: it does touch the host


if __name__ == "__main__":
    unittest.main()
