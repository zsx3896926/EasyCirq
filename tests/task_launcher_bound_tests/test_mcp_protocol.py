"""MCP stdio protocol surface: initialize, notifications, tools/list, errors."""

from __future__ import annotations

import json
import unittest

from task_launcher_bound_tests import support


class InitializeTests(support.BoundTestCase):
    def test_initialize_returns_contract_fields(self) -> None:
        harness = self.harness()
        client = self.mcp_client(harness)
        response = client.initialize()
        self.assertIn("result", response)
        result = response["result"]
        self.assertEqual(result["protocolVersion"], support.MCP_PROTOCOL_VERSION)
        self.assertEqual(result["capabilities"], {"tools": {"listChanged": False}})
        self.assertEqual(result["serverInfo"]["name"], support.SERVER_NAME)
        self.assertEqual(result["serverInfo"]["version"], "0.1.0")
        self.assertIsInstance(result["instructions"], str)
        self.assertIn("supervisor", result["instructions"])
        self.assertIn("task_start", result["instructions"])

    def test_initialize_response_echoes_request_id(self) -> None:
        harness = self.harness()
        client = self.mcp_client(harness)
        request_id = client.next_request_id()
        client.send_message(
            {"jsonrpc": "2.0", "id": request_id, "method": "initialize", "params": {}}
        )
        response = client.read_message()
        self.assertEqual(response["jsonrpc"], "2.0")
        self.assertEqual(response["id"], request_id)

    def test_initialized_notification_has_no_response(self) -> None:
        harness = self.harness()
        client = self.mcp_client(harness)
        client.initialize()
        client.notify("notifications/initialized")
        client.expect_no_message(timeout=0.6)
        # The loop is still alive and serving requests.
        self.assertEqual(client.request("ping")["result"], {})

    def test_notification_before_initialize_is_silent(self) -> None:
        harness = self.harness()
        client = self.mcp_client(harness)
        client.notify("notifications/whatever")
        client.expect_no_message(timeout=0.6)
        response = client.request("ping")
        self.assert_protocol_error(response, code=-32002)

    def test_unknown_notification_is_ignored(self) -> None:
        harness = self.harness()
        client = self.mcp_client(harness)
        client.initialize()
        client.notify("notifications/progress", {"progressToken": "x", "progress": 1})
        client.expect_no_message(timeout=0.6)
        self.assertEqual(client.request("ping")["result"], {})


class PingAndListTests(support.BoundTestCase):
    def test_ping_returns_empty_object(self) -> None:
        client = self.client()
        response = client.request("ping")
        self.assertEqual(response["result"], {})

    def test_ping_before_initialize_is_rejected(self) -> None:
        harness = self.harness()
        client = self.mcp_client(harness)
        response = client.request("ping")
        self.assert_protocol_error(response, code=-32002)
        self.assertIn("not initialized", response["error"]["message"].lower())

    def test_tools_list_phase1_has_exactly_six_tools(self) -> None:
        client = self.client()
        response = client.request("tools/list")
        names = [tool["name"] for tool in response["result"]["tools"]]
        self.assertEqual(sorted(names), sorted(support.PHASE1_TOOLS))
        self.assertEqual(len(names), 6)

    def test_tools_list_excludes_phase2_tools(self) -> None:
        client = self.client()
        names = {tool["name"] for tool in client.request("tools/list")["result"]["tools"]}
        for phase2_tool in support.PHASE2_TOOLS:
            self.assertNotIn(phase2_tool, names)

    def test_tools_list_schemas_are_strict_objects(self) -> None:
        client = self.client()
        tools = client.request("tools/list")["result"]["tools"]
        for tool in tools:
            schema = tool["inputSchema"]
            self.assertEqual(schema["type"], "object", tool["name"])
            self.assertIs(
                schema.get("additionalProperties"),
                False,
                "%s must reject additional properties" % tool["name"],
            )
            self.assertIsInstance(tool["description"], str)
            self.assertTrue(tool["description"].strip())

    def test_tools_list_annotations_are_read_only(self) -> None:
        client = self.client()
        tools = client.request("tools/list")["result"]["tools"]
        for tool in tools:
            annotations = tool["annotations"]
            self.assertTrue(annotations["readOnlyHint"], tool["name"])
            self.assertFalse(annotations["destructiveHint"])
            self.assertFalse(annotations["openWorldHint"])
            self.assertIsInstance(annotations["title"], str)

    def test_task_start_schema_requires_the_contract_fields(self) -> None:
        client = self.client()
        tools = {tool["name"]: tool for tool in client.request("tools/list")["result"]["tools"]}
        required = set(tools["task_start"]["inputSchema"]["required"])
        self.assertEqual(
            required, {"client", "toolchain", "task_id", "goal", "context"}
        )
        empty_tools = {"evidence_emit", "finalize"}
        for name in empty_tools:
            self.assertEqual(tools[name]["inputSchema"]["properties"], {})
        self.assertEqual(
            set(tools["snapshot_read"]["inputSchema"]["required"]), {"scope"}
        )


class ProtocolErrorTests(support.BoundTestCase):
    def test_unknown_method_is_method_not_found(self) -> None:
        client = self.client()
        response = client.request("tools/does-not-exist")
        self.assert_protocol_error(response, code=-32601)

    def test_unknown_tool_is_invalid_params(self) -> None:
        client = self.client()
        response = client.call_tool("no_such_tool", {})
        self.assert_protocol_error(response, code=-32602)
        self.assertIn("Unknown tool", response["error"]["message"])

    def test_phase2_tool_is_not_available_in_phase1(self) -> None:
        client = self.client()
        response = client.call_tool("apply", {"plan_id": "0" * 32})
        self.assert_protocol_error(response, code=-32602)

    def test_malformed_json_is_parse_error_and_loop_survives(self) -> None:
        client = self.client()
        client.send_line("{this is not json")
        response = client.read_message()
        self.assertEqual(response["error"]["code"], -32700)
        self.assertIsNone(response["id"])
        # The next request must still work.
        self.assertEqual(client.request("ping")["result"], {})

    def test_batch_array_is_invalid_request(self) -> None:
        client = self.client()
        client.send_line('[{"jsonrpc": "2.0", "id": 1, "method": "ping"}]')
        response = client.read_message()
        self.assertEqual(response["error"]["code"], -32600)
        self.assertEqual(client.request("ping")["result"], {})

    def test_wrong_jsonrpc_version_is_invalid_request(self) -> None:
        client = self.client()
        client.send_line('{"jsonrpc": "1.0", "id": 7, "method": "ping"}')
        response = client.read_message()
        self.assertEqual(response["error"]["code"], -32600)

    def test_request_without_method_is_invalid_request(self) -> None:
        client = self.client()
        client.send_line('{"jsonrpc": "2.0", "id": 7}')
        response = client.read_message()
        self.assertEqual(response["error"]["code"], -32600)

    def test_double_initialize_is_rejected(self) -> None:
        client = self.client()
        response = client.request("initialize", {"protocolVersion": support.MCP_PROTOCOL_VERSION})
        self.assert_protocol_error(response, code=-32600)

    def test_tools_call_without_params_is_invalid_params(self) -> None:
        client = self.client()
        response = client.request("tools/call")
        self.assert_protocol_error(response, code=-32602)

    def test_tools_call_with_non_object_params_is_invalid_params(self) -> None:
        client = self.client()
        request_id = client.next_request_id()
        client.send_message(
            {"jsonrpc": "2.0", "id": request_id, "method": "tools/call", "params": []}
        )
        response = client.read_message()
        self.assertEqual(response["error"]["code"], -32602)


class ToolResultShapeTests(support.BoundTestCase):
    def test_successful_tool_call_has_text_and_structured_content(self) -> None:
        harness = self.harness()
        client = self.client(harness)
        response = client.call_tool("task_start", support.start_arguments(harness))
        result = response["result"]
        self.assertFalse(result["isError"])
        self.assertEqual(result["content"][0]["type"], "text")
        self.assertEqual(
            json.loads(result["content"][0]["text"]), result["structuredContent"]
        )
        self.assertEqual(result["structuredContent"]["state"], "STARTED")

    def test_refusal_is_error_result_with_stable_code_and_state(self) -> None:
        harness = self.harness()
        client = self.client(harness)
        response = client.call_tool("snapshot_read", {"scope": {"kind": "full"}})
        result = response["result"]
        self.assertTrue(result["isError"])
        payload = result["structuredContent"]
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["state"], "CREATED")
        self.assertEqual(payload["error"]["code"], "OUT_OF_ORDER")
        self.assertEqual(payload["error"]["detail"]["next"], "task_start")

    def test_tool_text_roundtrips_chinese_utf8(self) -> None:
        harness = self.harness(
            request_kwargs={"user_prompt": "请检查原理图电源部分，中文路径/空格 也要正常"}
        )
        client = self.client(harness)
        result = self.tool_ok(client, "task_start", support.start_arguments(harness))
        rules_text = json.dumps(result["contract"]["rules"], ensure_ascii=False)
        self.assertIn("必须先加载", rules_text)
        self.assertIn("状态机", rules_text)
        raw_text = client.call_tool("task_start", support.start_arguments(harness))
        self.assertEqual(
            raw_text["result"]["structuredContent"]["error"]["code"], "STEP_ALREADY_DONE"
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
