# Acceptance matrix — zhigou offline-audit MCP server

| # | Requirement | Evidence | Result |
|---|---|---|---|
| M1 | stdio framing: one JSON-RPC line per message, UTF-8, no banner | `tests/zhigou_mcp_tests/test_protocol.py::test_stdout_carries_only_jsonrpc_messages`, `test_parse_error_is_reported_and_recovers` | PASS |
| M2 | `initialize` negotiates a supported protocol revision and returns server identity/capabilities | `test_initialize_negotiates_requested_version`, `test_unsupported_protocol_version_falls_back_to_a_supported_one` | PASS |
| M3 | notifications are never answered; id-less requests are notifications | `test_notifications_never_receive_a_response`, `test_requests_without_id_are_not_answered` | PASS |
| M4 | `tools/list` exposes 5 tools with object schemas, `additionalProperties:false`, read-only annotations | `test_tools_list_contract` | PASS |
| M5 | schema violations → `-32602`; unknown tool → `-32602`; unknown method → `-32601`; batch → `-32600`; bad JSON → `-32700` | `test_argument_schema_violations_are_invalid_params`, `test_unknown_tool_is_invalid_params`, `test_unknown_method_is_a_protocol_error`, `test_batched_requests_are_rejected`, `test_parse_error_is_reported_and_recovers` | PASS |
| M6 | electrical review runs offline and returns the module status verbatim | `test_electrical_review_summary_preserves_verdict`, benchmark `electrical_review_summary` | PASS |
| M7 | `detail=full` returns the complete module report with its schema | `test_electrical_review_full_returns_module_report`, benchmark `electrical_review_full` | PASS |
| M8 | `invalid_input` is a structured verdict, not a pass and not a crash | `test_electrical_review_invalid_input_is_a_structured_verdict`, benchmark `electrical_review_invalid_input` | PASS |
| M9 | return-path audit keeps `fail` and unknown items; module's own `real_eda` copied | `test_return_path_audit_keeps_fail_and_unknowns`, benchmark `return_path_audit_fail` | PASS |
| M10 | delivery inspect is `inventory_only`, never `pass_with_scope` | `test_delivery_inspect_is_inventory_only_not_a_pass`, benchmark `delivery_inspect` | PASS |
| M11 | delivery audit returns `incomplete` with non-empty unknown items | `test_delivery_audit_incomplete_keeps_unknowns`, benchmark `delivery_audit_incomplete` | PASS |
| M12 | missing input is a tool error (`isError=true`, `input_not_found`) and the server survives | `test_missing_input_is_a_tool_error_and_server_survives`, benchmark `missing_input` | PASS |
| M13 | audited inputs are not modified (file hash / directory listing before-after) | `test_all_payloads_are_offline_and_no_eda_was_called`, `test_delivery_inspect_is_inventory_only_not_a_pass` | PASS |
| M14 | every payload states `offline:true`, `real_eda: NOT RUN`, `eda_calls: 0`, `not_proof` | `test_capabilities`, `test_all_payloads_are_offline_and_no_eda_was_called`, benchmark cases | PASS |
| M15 | `summary` mode never hides omission: `report_omitted:true` + SHA-256 + byte size | `test_report_omission_is_explicit_in_summary_mode`, benchmark `electrical_review_summary` | PASS |
| M16 | server exits 0 on stdin close; no traceback on stderr | `test_protocol` class teardown (`close()==0`, no "Traceback") | PASS |
| M17 | frozen benchmark reproduces 9/9 cases with recorded transcript | `benchmarks/mcp-tools/results.json`, `docs/zhigou-mcp/evidence/stdio-transcript.jsonl` | PASS |
| M18 | official test entry discovers the MCP tests | `python -m unittest discover -s tests` includes `zhigou_mcp_tests` (22 tests) | PASS |
| N1 | launch a real MCP client (Claude Code / Codex / Cursor) and call a tool from it | not executed in this environment | **NOT RUN** |
| N2 | interact with the official EDA MCP server (`lceda-pro --mcp`) at the same time | not executed; no EDA session used | **NOT RUN** |
| N3 | local Python 3.10 runtime | local machine has 3.13 only; CI matrix covers 3.10 | **NOT RUN (CI)** |
| N4 | EDA readback/DRC/save-reopen/manufacturing/physical test | out of scope: audit modules are offline | **NOT RUN** |

A "PASS" above is offline protocol/tool conformance only. It does not prove an
audit result is correct for a real board, and it does not prove hardware or
manufacturing acceptance.
