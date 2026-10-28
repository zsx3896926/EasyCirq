# EasyCirq offline-audit MCP server

**Status: working stdio PoC, independent of the EDA toolchain, not yet wired into `SKILL.md`.**
Merged into `main` through the integration window; every call here is **offline and
read-only** — no EDA/daemon/connector, no network, no host DRC, no save/reopen.

The server exposes three existing offline audit CLIs as MCP tools so an MCP-capable
AI client can call them directly instead of shelling out blind:

| MCP tool | Module | Input | Verdict |
|---|---|---|---|
| `offline_electrical_review` | `electrical_review` (task B) | `easycirq.electrical-review.input/v1` JSON | `pass_with_scope` / `fail` / `review_required` / `incomplete` / `invalid_input` |
| `offline_return_path_audit` | `return_path_audit` (task E) | `return-path-audit-input/v1` JSON | `pass_with_scope` / `fail` / `review_required` / `incomplete` / `input_invalid` |
| `offline_delivery_inspect` | `delivery_audit inspect` (task C) | directory / ZIP / single file | `inspected` (inventory only, **not** a verdict) |
| `offline_delivery_audit` | `delivery_audit audit` (task C) | package + `profile` + optional declarations | `pass_with_scope` / `fail` / `input_invalid` / `incomplete` |
| `offline_audit_capabilities` | — | none | tool/scope/NOT-RUN description |

## Why

Before this server the ten offline audit/generation modules were **isolated CLIs**:
only a human or an ad-hoc shell command could reach them. In an MCP client the
same tools now appear in the tool list with strict input schemas and explicit
verdict semantics, so the model can plan an audit, call it, and read a structured
verdict without parsing free-form stdout.

## Register it

The server is stdlib-only and starts with `python -m easycirq_mcp`; it must be able
to import `easycirq/scripts`, so pass that directory via `PYTHONPATH`.
Python 3.10+ (only 3.13 was available locally; CI covers 3.10).

Generic MCP client configuration (Claude Code, Cursor, Codex, other MCP clients —
consult each client's MCP docs for the exact file/command):

```json
{
  "mcpServers": {
    "easycirq-offline-audit": {
      "command": "python",
      "args": ["-m", "easycirq_mcp"],
      "env": {
        "PYTHONPATH": "<repo>/easycirq/scripts"
      }
    }
  }
}
```

Claude Code CLI:

```shell
claude mcp add easycirq-offline-audit \
  --env PYTHONPATH=<repo>/easycirq/scripts \
  -- python -m easycirq_mcp
```

On Windows use forward slashes or escaped backslashes in JSON paths.

**Do not confuse this server with the official EDA MCP server.** The official
client has `lceda-pro --mcp stdio|http` (easyeda-pro internationally), which can
drive the editor. This server only runs offline audits and never executes EDA; the
two can be registered side by side. The official CLI requires EasyEDA Pro
**v4.1.60+**; this server has no EDA dependency.

## What a call returns

Every tool result is a JSON object (also provided as `structuredContent`) with:

* the module's own `status` / `overall_status` **verbatim**, plus a normalised
  `verdict_class` and `is_pass_with_scope`;
* `exit_code` and the module's expected exit-code set;
* `report_schema`, `report_sha256`, `report_bytes`; `detail="summary"` (default)
  omits the full report but says so with `report_omitted: true`, `detail="full"`
  includes it;
* `unknown_count` / `unknown_items` / `not_checked` / `limits` copied from the
  module — never dropped;
* `input.path`, `input.sha256_before`, `input.sha256_after`, `input.unchanged`
  (directory inputs use a names+sizes signature and say so);
* `offline: true`, `real_eda: "NOT RUN"`, `eda_calls: 0`, and an explicit
  `not_proof` list.

`isError` is true only for a tooling failure (missing input, timeout, unexpected
module exit, oversized/invalid report). A legitimate `fail`, `review_required`,
`incomplete` or `invalid_input` verdict is returned as a **structured result**, not
as a protocol error, so it cannot be mistaken for a crash.

## Minimum viable example

```text
# 1) capability check
offline_audit_capabilities {}

# 2) scoped electrical review
offline_electrical_review {"input_path": "benchmarks/electrical-review/cases/real-mcu-i2c-ams-tab/input.json"}

# 3) full report when you need evidence
offline_return_path_audit {"input_path": "benchmarks/return-path-audit/real-replay/real-2layer-mcu-i2c.input.json", "detail": "full"}

# 4) delivery package inventory (not a pass)
offline_delivery_inspect {"input_path": "benchmarks/delivery-audit/real-sample"}
```

## Verification

| check | result |
|---|---|
| `python -m unittest discover -s tests/easycirq_mcp_tests -t tests` | **22 tests OK** |
| `python benchmarks/mcp-tools/run_benchmark.py` | **9/9 cases pass**, `real_eda=NOT RUN`, `eda_calls=0` |
| transcript | [evidence/stdio-transcript.jsonl](evidence/stdio-transcript.jsonl) |
| results | [benchmarks/mcp-tools/results.json](../../benchmarks/mcp-tools/results.json) |

## Limits / NOT RUN

* No real MCP client (Claude Code / Codex / Cursor) was launched; protocol
  conformance is exercised by the test client and the benchmark driver only.
* Messages are newline-delimited JSON-RPC 2.0; batch requests and the LSP-style
  `Content-Length` framing are not implemented.
* Reports larger than 8 MB are rejected (`report_too_large`); use the module CLI.
* The audit scope and NOT RUN limits of each module still apply: no EDA readback,
  host DRC, save/reopen, manufacturing, assembly, power-up or physical test.
* `pass_with_scope` is never a whole-board or hardware acceptance; unknown and
  review_required items require a human decision.
* No authentication: run it as a local stdio child process only.
