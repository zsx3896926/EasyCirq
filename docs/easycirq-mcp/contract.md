# MCP offline-audit server — contract

Status: v0.1.0 PoC. The normative rules below are what the tests and the frozen
benchmark exercise. Nothing here grants EDA execution capability.

## 1. Transport and protocol

* stdio only: **newline-delimited JSON-RPC 2.0**, one compact JSON object per line,
  UTF-8, no embedded newlines. `Content-Length` framing and JSON-RPC batches are
  not supported (a batch array is rejected with `-32600`).
* Protocol revisions implemented: `2025-06-18`, `2025-03-26`, `2024-11-05`.
  `initialize` echoes the client's revision when supported, otherwise answers with
  `2025-06-18`; the client is expected to respect the returned revision.
* Capabilities: `{"tools": {"listChanged": false}}`. No resources or prompts.
* `notifications/initialized` and other `notifications/*` messages are accepted and
  never answered. Requests without `id` are treated as notifications.
* stdout carries protocol messages only. Diagnostics go to stderr and only when
  `EASYCIRQ_MCP_DEBUG=1`.

## 2. Methods

| method | result |
|---|---|
| `initialize` | `protocolVersion`, `capabilities`, `serverInfo` (`easycirq-offline-audit` / `0.1.0`), `instructions` |
| `ping` | `{}` |
| `tools/list` | five tool descriptors with `inputSchema` and `annotations` |
| `tools/call` | `{content:[{type:"text",text:<JSON>}], structuredContent:<same JSON>, isError}` |

JSON-RPC errors: `-32700` parse error, `-32600` invalid request (non-object,
batch), `-32601` unknown method, `-32602` invalid params or unknown tool,
`-32603` unexpected internal error (defensive only).

## 3. Tools

All tools are `readOnlyHint=true`, `destructiveHint=false`, `idempotentHint=true`,
`openWorldHint=false`.

Common optional arguments: `detail` = `summary` (default) | `full`;
`timeout_s` = integer 1..600 (default 120).

| tool | required | optional |
|---|---|---|
| `offline_electrical_review` | `input_path` | `detail`, `timeout_s` |
| `offline_return_path_audit` | `input_path` | `constraints_path`, `detail`, `timeout_s` |
| `offline_delivery_inspect` | `input_path` | `detail`, `timeout_s` |
| `offline_delivery_audit` | `input_path`, `profile` (`pcb-fabrication`/`smt-assembly`/`archive`) | `declarations_path`, `bom_path`, `cpl_path`, `detail`, `timeout_s` |
| `offline_audit_capabilities` | — | — |

`input_path` may be absolute or relative to the repository root (the server resolves
relative paths against the repository, not the client's cwd). The input is read
only; the server never writes next to it and never modifies it.

## 4. Result envelope (`easycirq.mcp.offline-audit-tool-result/v1`)

```json
{
  "schema": "easycirq.mcp.offline-audit-tool-result/v1",
  "tool": "offline_electrical_review",
  "module": "electrical_review",
  "command": {"module": "electrical_review", "argv": ["..."], "cwd": "easycirq/scripts"},
  "exit_code": 0,
  "expected_exits": [0, 1, 2, 3, 4],
  "status": "pass_with_scope",
  "verdict_class": "pass_with_scope",
  "is_pass_with_scope": true,
  "is_error": false,
  "offline": true,
  "real_eda": "NOT RUN",
  "real_eda_source": "wrapper",
  "eda_calls": 0,
  "input": {"path": "...", "kind": "file", "sha256_before": "...", "sha256_after": "...", "unchanged": true},
  "summary": {"...": "module-specific compact counts"},
  "unknown_count": 0,
  "unknown_items": [],
  "unknown_items_truncated": false,
  "not_checked": ["..."],
  "limits": ["..."],
  "report_schema": "easycirq.electrical-review.report/v1",
  "report_sha256": "<64 hex>",
  "report_bytes": 12033,
  "detail": "summary",
  "report_omitted": true,
  "report": null,
  "duration_ms": 140.2,
  "stderr_tail": "",
  "not_proof": ["..."]
}
```

Rules:

* `status` is taken from the module report (`status` or `overall_status`). The exit
  code is only a fallback and a consistency check against `expected_exits`.
* `pass_with_scope` is the only status with `is_pass_with_scope: true`; it covers
  only the declared input/rules and is not hardware acceptance.
* `unknown_items` keeps at most 50 entries; `unknown_items_truncated` says when it
  is cut. `unknown_count` is the total.
* `detail=summary` sets `report_omitted: true` and `report: null` but always keeps
  `report_sha256`/`report_bytes`, so the caller can request the full report later.
* `real_eda`/`eda_calls` describe this wrapper: no EDA executable, daemon or
  connector is started. When the module report has its own field it is copied and
  `real_eda_source` is `report`/`report.run`; otherwise the wrapper value `NOT RUN`
  is used with `real_eda_source: "wrapper"`.
* `is_error: true` means the tool could not produce a usable report (missing input,
  timeout, unexpected exit, oversized/invalid report) and includes `error.code`.
  Audit verdicts (`fail`, `review_required`, `incomplete`, `invalid_input`) are
  normal results with `is_error: false`.

## 5. Verdict mapping

| module status | `verdict_class` | `is_pass_with_scope` |
|---|---|---|
| `pass_with_scope` | `pass_with_scope` | true |
| `fail` | `fail` | false |
| `review_required` | `review_required` | false |
| `incomplete` | `incomplete` | false |
| `invalid_input` / `input_invalid` | `invalid_input` | false |
| `inspected` (delivery inspect only) | `inventory_only` | false |
| anything else | `unknown_status` | false |

Exit-code expectations: electrical review `{0,1,2,3,4}`; return-path audit
`{0,1,2,3,4}`; delivery inspect `{0}`; delivery audit `{0,1,2,3}`.

## 6. Safety and limits

* Read-only: no writes into the input; module reports are written to a private
  temporary directory and deleted after reading.
* `timeout_s` bounds the module subprocess; a timeout returns `is_error: true`
  with `error.code: "timeout"`.
* Reports above 8 MB are rejected with `report_too_large`.
* No network, no EDA, no subprocess other than `python -m <audit module>`.
* No authentication; intended to be launched as a local stdio child by the client.

## 7. Compatibility

* Python 3.10+ (CI matrix covers 3.10/3.13; local verification was 3.13).
* Module schemas stay owned by their modules; this server only wraps their CLI
  surface. If a module changes its report schema/status/exit code, the wrapper and
  its tests must be updated in the same review.
* The server version is independent of the Skill version and of the official EDA
  client version.
