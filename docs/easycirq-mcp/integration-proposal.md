# Integration proposal — how this MCP server should be wired in

This PoC is deliberately **not** wired into `SKILL.md` or the references yet: task A
(draft PR #36) rewrites `SKILL.md`, `references/*` and the installation docs, and
this window's rule is to avoid writing the same files as an active session. The
server is already usable by any MCP client via configuration; the patch below is
for the maintainer/A after A is merged or rebased.

## 1. Proposed `SKILL.md` routing (one paragraph + one command)

Under the offline-review section, add:

```markdown
涉及离线审查（电气意图、回流/参考平面、交付包）时，可走本仓库的 MCP 工具服务器：
`python -m easycirq_mcp`（需 PYTHONPATH=easycirq/scripts）。它只读、离线，
不调用 EDA；`pass_with_scope` 仅覆盖声明输入，unknown/review_required 需人工处置。
不要把本服务器与官方 `lceda-pro --mcp`（真实 EDA 执行）混为一谈。
```

Add to [references/offline-tools.md](../../easycirq/references/offline-tools.md)
or a new `references/offline-audit-mcp.md`:

* tool list and the `detail=summary|full` convention;
* verdict/`isError` semantics (audit fail is data, not tool failure);
* client registration snippet from [README.md](README.md);
* link to [contract.md](contract.md) and the frozen benchmark.

## 2. Verification gate before wiring

1. Full official suite still green with the MCP tests discovered
   (`unittest discover -s tests`).
2. `python benchmarks/mcp-tools/run_benchmark.py` → 9/9.
3. One real MCP client (Claude Code preferred, since the repo's primary client is
   Claude Code/Codex) is launched with this server registered and calls
   `offline_audit_capabilities` + `offline_electrical_review` successfully. Record
   the client name/version, config snippet and transcript; keep it as evidence
   separate from the synthetic protocol tests.
4. `skill_selftest.py` remains 5 PASS / 0 FAIL.

Until step 3 is recorded, describe the server as **protocol-tested, client
integration NOT RUN**.

## 3. Boundaries to keep

* Do not add an "auto-fix from audit" tool. The audits are read-only and their
  findings may be wrong/unknown; remediation must go through the existing
  apply/readback gates.
* Do not let the server call EDA, the daemon or the connector. The official CLI
  MCP server (`lceda-pro --mcp`) is the execution path; mixing them would make
  offline evidence indistinguishable from host results.
* Keep audit modules' own limits (`real_eda: NOT RUN`) in every payload; never
  rewrite an audit result into a product-level pass.
* If a module's schema/status/exit code changes, update this server and its tests
  in the same PR (the wrapper is intentionally coupled to the CLI contract).
