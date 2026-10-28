"""Tool-level tests: verdict semantics, unknown preservation, read-only inputs."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from .support import B_REAL, C_SAMPLE, E_REAL, MCPServer, structured

NOT_PROOF_FRAGMENT = "not a whole-board"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _listing(path: Path):
    return sorted(item.relative_to(path).as_posix()
                  for item in path.rglob("*") if item.is_file())


class ToolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = MCPServer()
        cls.server.handshake()

    @classmethod
    def tearDownClass(cls):
        code = cls.server.close()
        assert code == 0, cls.server.stderr

    def call(self, name: str, arguments: dict) -> dict:
        return structured(self.server.call_tool(name, arguments))

    def test_capabilities(self):
        payload = self.call("offline_audit_capabilities", {})
        self.assertFalse(payload["is_error"])
        self.assertEqual(payload["schema"], "zhigou.mcp.offline-audit-capabilities/v1")
        self.assertEqual(payload["server"]["name"], "zhigou-offline-audit")
        self.assertTrue(payload["offline"])
        self.assertEqual(payload["real_eda"], "NOT RUN")
        self.assertEqual(payload["eda_calls"], 0)
        self.assertEqual(len(payload["tools"]), 5)
        self.assertIn("never", payload["boundary"])
        self.assertTrue(any(NOT_PROOF_FRAGMENT in line
                            for line in payload["not_proof"]))

    def test_electrical_review_summary_preserves_verdict(self):
        payload = self.call("offline_electrical_review",
                            {"input_path": str(B_REAL)})
        self.assertFalse(payload["is_error"])
        self.assertEqual(payload["exit_code"], 0)
        self.assertEqual(payload["status"], "pass_with_scope")
        self.assertEqual(payload["verdict_class"], "pass_with_scope")
        self.assertTrue(payload["is_pass_with_scope"])
        self.assertTrue(payload["report_omitted"])
        self.assertIsNone(payload["report"])
        self.assertEqual(len(payload["report_sha256"]), 64)
        self.assertGreater(payload["report_bytes"], 0)
        self.assertEqual(payload["input"]["unchanged"], True)
        self.assertEqual(payload["real_eda"], "NOT RUN")
        self.assertEqual(payload["eda_calls"], 0)
        self.assertEqual(payload["report_schema"], "zhigou.electrical-review.report/v1")
        self.assertTrue(any(NOT_PROOF_FRAGMENT in line
                            for line in payload["not_proof"]))

    def test_electrical_review_full_returns_module_report(self):
        payload = self.call("offline_electrical_review",
                            {"input_path": str(B_REAL), "detail": "full"})
        self.assertFalse(payload["report_omitted"])
        self.assertIsInstance(payload["report"], dict)
        self.assertEqual(payload["report"]["status"], payload["status"])
        self.assertEqual(payload["report"]["schema"],
                         "zhigou.electrical-review.report/v1")

    def test_electrical_review_invalid_input_is_a_structured_verdict(self):
        with tempfile.TemporaryDirectory(prefix="zhigou-mcp-test-") as folder:
            bad = Path(folder) / "bad.json"
            bad.write_text('{"schema": "bogus"}', encoding="utf-8")
            payload = self.call("offline_electrical_review",
                                {"input_path": str(bad)})
        self.assertFalse(payload["is_error"])  # invalid input is a verdict, not a crash
        self.assertEqual(payload["exit_code"], 2)
        self.assertEqual(payload["status"], "invalid_input")
        self.assertEqual(payload["verdict_class"], "invalid_input")
        self.assertFalse(payload["is_pass_with_scope"])
        self.assertEqual(payload["input"]["unchanged"], True)

    def test_missing_input_is_a_tool_error_and_server_survives(self):
        response = self.server.call_tool(
            "offline_electrical_review",
            {"input_path": "benchmarks/does-not-exist-anywhere.json"})
        self.assertTrue(response["result"]["isError"])
        payload = structured(response)
        self.assertTrue(payload["is_error"])
        self.assertEqual(payload["error"]["code"], "input_not_found")
        self.assertEqual(payload["real_eda"], "NOT RUN")
        self.assertEqual(self.server.request("ping")["result"], {})

    def test_return_path_audit_keeps_fail_and_unknowns(self):
        before = _sha256(E_REAL)
        payload = self.call("offline_return_path_audit",
                            {"input_path": str(E_REAL), "detail": "full"})
        self.assertFalse(payload["is_error"])
        self.assertEqual(payload["exit_code"], 1)
        self.assertEqual(payload["status"], "fail")
        self.assertEqual(payload["verdict_class"], "fail")
        self.assertFalse(payload["is_pass_with_scope"])
        self.assertEqual(payload["report_schema"], "return-path-audit-report/v1")
        self.assertEqual(payload["report"]["overall_status"], "fail")
        self.assertEqual(payload["report"]["run"]["real_eda"], "NOT RUN")
        self.assertGreaterEqual(len(payload["report"].get("unknowns") or []), 0)
        self.assertEqual(payload["input"]["unchanged"], True)
        self.assertEqual(before, _sha256(E_REAL))
        self.assertEqual(payload["real_eda"], "NOT RUN")
        self.assertEqual(payload["eda_calls"], 0)

    def test_delivery_inspect_is_inventory_only_not_a_pass(self):
        before = _listing(C_SAMPLE)
        payload = self.call("offline_delivery_inspect",
                            {"input_path": str(C_SAMPLE)})
        self.assertFalse(payload["is_error"])
        self.assertEqual(payload["exit_code"], 0)
        self.assertEqual(payload["status"], "inspected")
        self.assertEqual(payload["verdict_class"], "inventory_only")
        self.assertFalse(payload["is_pass_with_scope"])
        self.assertEqual(payload["report_schema"], "delivery-inspect/v1")
        self.assertEqual(payload["input"]["kind"], "directory")
        self.assertEqual(payload["input"]["unchanged"], True)
        self.assertEqual(before, _listing(C_SAMPLE))

    def test_delivery_audit_incomplete_keeps_unknowns(self):
        payload = self.call("offline_delivery_audit",
                            {"input_path": str(C_SAMPLE), "profile": "archive",
                             "detail": "full"})
        self.assertFalse(payload["is_error"])
        self.assertEqual(payload["exit_code"], 3)
        self.assertEqual(payload["status"], "incomplete")
        self.assertEqual(payload["verdict_class"], "incomplete")
        self.assertFalse(payload["is_pass_with_scope"])
        self.assertGreater(payload["unknown_count"], 0)
        self.assertTrue(payload["unknown_items"])
        self.assertEqual(payload["report_schema"], "delivery-audit/v1")
        self.assertEqual(payload["report"]["real_eda"], "NOT RUN")
        self.assertEqual(payload["report"]["status"], "incomplete")
        self.assertEqual(payload["input"]["unchanged"], True)

    def test_delivery_audit_requires_a_valid_profile(self):
        response = self.server.call_tool(
            "offline_delivery_audit",
            {"input_path": str(C_SAMPLE), "profile": "not-a-profile"})
        self.assertEqual(response["error"]["code"], -32602)

    def test_report_omission_is_explicit_in_summary_mode(self):
        payload = self.call("offline_return_path_audit",
                            {"input_path": str(E_REAL)})
        self.assertTrue(payload["report_omitted"])
        self.assertIsNone(payload["report"])
        self.assertEqual(len(payload["report_sha256"]), 64)
        self.assertGreater(payload["report_bytes"], 0)
        self.assertEqual(payload["detail"], "summary")

    def test_all_payloads_are_offline_and_no_eda_was_called(self):
        for name, arguments in (
                ("offline_electrical_review", {"input_path": str(B_REAL)}),
                ("offline_return_path_audit", {"input_path": str(E_REAL)}),
                ("offline_delivery_inspect", {"input_path": str(C_SAMPLE)}),
                ("offline_audit_capabilities", {})):
            with self.subTest(tool=name):
                payload = self.call(name, arguments)
                self.assertEqual(payload["real_eda"], "NOT RUN")
                self.assertEqual(payload["eda_calls"], 0)
                self.assertTrue(payload["offline"])


if __name__ == "__main__":
    unittest.main()
