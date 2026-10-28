"""MCP protocol-level tests: framing, handshake, errors, purity, lifecycle."""

from __future__ import annotations

import json
import unittest

from .support import MCPServer

SUPPORTED_VERSIONS = {"2024-11-05", "2025-03-26", "2025-06-18"}


class ProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = MCPServer()
        cls.init = cls.server.handshake()

    @classmethod
    def tearDownClass(cls):
        code = cls.server.close()
        stderr = cls.server.stderr
        assert code == 0, "server exited %r: %s" % (code, stderr)
        assert "Traceback" not in stderr, stderr

    def test_initialize_negotiates_requested_version(self):
        result = self.init["result"]
        self.assertEqual(result["protocolVersion"], "2025-06-18")
        self.assertEqual(result["serverInfo"]["name"], "easycirq-offline-audit")
        self.assertEqual(result["serverInfo"]["version"], "0.1.0")
        self.assertIs(result["capabilities"]["tools"]["listChanged"], False)
        self.assertIn("never calls EDA", result["instructions"])
        self.assertIn("not a whole-board", result["instructions"])

    def test_unsupported_protocol_version_falls_back_to_a_supported_one(self):
        client = MCPServer()
        try:
            response = client.handshake(protocol_version="1999-01-01")
            self.assertIn(response["result"]["protocolVersion"], SUPPORTED_VERSIONS)
        finally:
            client.close()

    def test_notifications_never_receive_a_response(self):
        # notifications/initialized is sent by handshake(); a second notification
        # and a cancelled notification must stay silent, so the next line read is
        # the ping response.
        self.server.notify("notifications/cancelled",
                           {"requestId": 999, "reason": "test"})
        self.server.notify("notifications/initialized")
        response = self.server.request("ping")
        self.assertEqual(response["id"], self.server._next_id)
        self.assertEqual(response["result"], {})

    def test_tools_list_contract(self):
        response = self.server.request("tools/list")
        tools = response["result"]["tools"]
        names = [tool["name"] for tool in tools]
        self.assertEqual(names, [
            "offline_electrical_review",
            "offline_return_path_audit",
            "offline_delivery_inspect",
            "offline_delivery_audit",
            "offline_audit_capabilities",
        ])
        for tool in tools:
            schema = tool["inputSchema"]
            self.assertEqual(schema["type"], "object")
            self.assertIs(schema["additionalProperties"], False)
            self.assertIsInstance(schema.get("properties"), dict)
            self.assertIs(tool["annotations"]["readOnlyHint"], True)
            self.assertIs(tool["annotations"]["openWorldHint"], False)
            self.assertIn("offline", tool["description"].lower())
            self.assertIn("readonly".replace("readonly", "read-only"),
                          tool["description"].lower())

    def test_unknown_method_is_a_protocol_error(self):
        response = self.server.request("no/such/method")
        self.assertEqual(response["error"]["code"], -32601)
        self.assertIn("Method not found", response["error"]["message"])

    def test_unknown_tool_is_invalid_params(self):
        response = self.server.request(
            "tools/call", {"name": "not_a_tool", "arguments": {}})
        self.assertEqual(response["error"]["code"], -32602)
        self.assertIn("unknown tool", response["error"]["message"])

    def test_argument_schema_violations_are_invalid_params(self):
        cases = [
            ({"name": "offline_electrical_review", "arguments": {}},
             "input_path is required"),
            ({"name": "offline_electrical_review",
              "arguments": {"input_path": "x", "bogus": 1}},
             "not an allowed property"),
            ({"name": "offline_electrical_review",
              "arguments": {"input_path": 3}},
             "must be string"),
            ({"name": "offline_delivery_audit",
              "arguments": {"input_path": "x", "profile": "nope"}},
             "must be one of"),
            ({"name": "offline_electrical_review",
              "arguments": {"input_path": "x", "detail": "everything"}},
             "must be one of"),
            ({"name": "offline_electrical_review",
              "arguments": {"input_path": "x", "timeout_s": 0}},
             "must be >= 1"),
            ({"name": "offline_electrical_review",
              "arguments": {"input_path": "x", "timeout_s": True}},
             "must be integer"),
        ]
        for params, expected in cases:
            with self.subTest(expected=expected):
                response = self.server.request("tools/call", params)
                self.assertEqual(response["error"]["code"], -32602)
                self.assertIn(expected, response["error"]["message"])
        # The server must still work after rejected calls.
        self.assertEqual(self.server.request("ping")["result"], {})

    def test_parse_error_is_reported_and_recovers(self):
        client = MCPServer()
        try:
            client.handshake()
            client.send_raw("{not valid json")
            error = client.read()
            self.assertEqual(error["error"]["code"], -32700)
            self.assertIsNone(error["id"])
            self.assertEqual(client.request("ping")["result"], {})
        finally:
            self.assertEqual(client.close(), 0)

    def test_batched_requests_are_rejected(self):
        client = MCPServer()
        try:
            client.handshake()
            client.send([{"jsonrpc": "2.0", "id": 1, "method": "ping"}])
            error = client.read()
            self.assertEqual(error["error"]["code"], -32600)
            self.assertIn("batched", error["error"]["message"])
            self.assertEqual(client.request("ping")["result"], {})
        finally:
            self.assertEqual(client.close(), 0)

    def test_requests_without_id_are_not_answered(self):
        client = MCPServer()
        try:
            client.handshake()
            client.send({"jsonrpc": "2.0", "method": "ping"})
            response = client.request("ping")
            self.assertEqual(response["id"], client._next_id)
        finally:
            self.assertEqual(client.close(), 0)

    def test_stdout_carries_only_jsonrpc_messages(self):
        # Every response is a single JSON object per line; the reader in
        # support.MCPServer already json.loads each line, so reaching this point
        # proves purity for the exchanged lines.
        response = self.server.request("tools/list")
        self.assertEqual(response["jsonrpc"], "2.0")
        self.assertIn("result", response)


if __name__ == "__main__":
    unittest.main()
