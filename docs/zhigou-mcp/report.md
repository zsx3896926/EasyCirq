# Report — zhigou offline-audit MCP server (v0.1.0 PoC)

## 1. What was built

`design-hardware/scripts/zhigou_mcp/` — a stdlib-only MCP stdio server exposing
three existing offline audit CLIs as five tools:

* `offline_electrical_review` (task B),
* `offline_return_path_audit` (task E),
* `offline_delivery_inspect` and `offline_delivery_audit` (task C),
* `offline_audit_capabilities`.

Also delivered: 22 subprocess-level protocol/tool tests, a frozen 9-case benchmark
with transcript, and these docs. No product module was changed; no EDA, daemon,
connector, network or user client was touched.

## 2. Actual results (2026-10-28, Windows 11, Python 3.13.15)

| command | result |
|---|---|
| `python -m unittest discover -s tests/zhigou_mcp_tests -t tests -p "test_*.py"` | **22 tests OK** (~5.8 s) |
| `python benchmarks/mcp-tools/run_benchmark.py` | **9/9 cases pass** |
| benchmark transcript | `docs/zhigou-mcp/evidence/stdio-transcript.jsonl` (4.4 KB) |
| full repository suite (official entry, includes the new tests) | see `docs/integration/` runbook; recorded in the merge PR |
| `python -m zhigou_mcp --version` | `0.1.0` |

Benchmark cases and observed verdicts (all `real_eda="NOT RUN"`, `eda_calls=0`):

| case | tool | observed |
|---|---|---|
| capabilities | capabilities | 5 tools, offline/NOT RUN |
| electrical_review_summary | electrical review | `pass_with_scope`, exit 0, report omitted with SHA-256 |
| electrical_review_full | electrical review | full report, schema `zhigou.electrical-review.report/v1` |
| electrical_review_invalid_input | electrical review | `invalid_input`, exit 2, not a pass |
| return_path_audit_fail | return-path audit | `fail`, exit 1, unknowns preserved |
| delivery_inspect | delivery inspect | `inspected` / `inventory_only`, exit 0 |
| delivery_audit_incomplete | delivery audit | `incomplete`, exit 3, `unknown_count > 0` |
| missing_input | electrical review | `isError=true`, `input_not_found` |
| schema_violation | electrical review | JSON-RPC `-32602` |

## 3. Design decisions and boundaries

* **Verdicts are data, not errors.** A `fail` / `review_required` / `incomplete` /
  `invalid_input` audit outcome is a normal tool result. `isError` is reserved for
  tooling failures, so a model cannot mistake "audit found a problem" for "the tool
  broke", and cannot mistake "the tool broke" for a pass.
* **Unknown is preserved.** `unknown_count`, up to 50 `unknown_items`,
  `not_checked` and module `limits` are copied; `inventory_only` is never promoted
  to `pass_with_scope`.
* **Read-only is measured.** File inputs are SHA-256 hashed before and after the
  call and must be identical; directory inputs use a names+sizes signature and the
  payload states that limitation instead of claiming a full content hash.
* **Honest NOT RUN.** The wrapper never calls EDA. When the module report has its
  own `real_eda` field it is copied (`real_eda_source: report`/`report.run`);
  otherwise `NOT RUN`/`wrapper` is reported with the reason in `not_proof`.
* **Explicit omission.** Default `summary` detail omits the full report but keeps
  `report_omitted: true`, `report_sha256` and `report_bytes`.

## 4. Integration status

* Discoverable by the official test entry; independent of the EDA window.
* **Not yet wired into `SKILL.md`/references.** Task A's draft PR owns those files
  and is still unmerged; the exact proposed patch is in
  [integration-proposal.md](integration-proposal.md).
* Can be registered in any MCP client today; it is already a real entry point
  (unlike an unreferenced script), because MCP clients launch it by configuration.

## 5. NOT RUN

Real MCP client end-to-end (Claude Code / Codex / Cursor), official EDA MCP
interaction, host EDA readback/DRC/save-reopen, manufacturing/assembly/power-up,
physical measurements, local Python 3.10 runtime (CI matrix covers it), and a real
four-layer board return-path case. Protocol conformance is against this repository's
test/benchmark client only, not a specific client implementation.
