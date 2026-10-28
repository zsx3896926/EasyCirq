# Decision memo: A1 / A2 / A3 (provisional)

**Status: `decision-provisional`** - no final A1/A2/A3 may be issued because the
write-critical cells (W04, W05, W09-save) are unmeasured (no write authorization).
This file records the evidence-based provisional lean only.

- Date: 2026-10-28
- Evidence: `docs/evidence/a2-coverage-2026-10-28/` (matrix: `coverage-matrix.md`)
- Decision as computed by the rubric: **incomplete** (provisional)
- Provisional lean: **A2 - thin typed layer over the official CLI/MCP; retire
  A's runtime/connector/protocol fork**
- Confidence: **low** (two decisive cells unmeasured; A not independently run)

## 1. Why not a final answer

The task book's own rule: with unrun critical cells, no final A1/A2/A3 may be
issued. The rubric returns `incomplete` because:

| critical cell | status | why |
| --- | --- | --- |
| W04 schematic write | `blocked` | design-content write probes were not authorized |
| W05 PCB write | `blocked` | same |
| W02 schematic read | `partial` | net API returns empty; netlist text is the fallback |
| W06 batch | `partial` | read batching measured, write batching not run |
| W07 DRC/DFM | `partial` | DRC receipts work but the return shape is undocumented and DFM has no official equivalent |
| W09 save/reopen | `partial` | close/reopen and non-mutation proven; save persistence not run |

Covered critical cells: W08 (export, with real artifacts) and W11 (MCP).
Non-critical: W01 and W10 covered; W03 partial.

## 2. Evidence-based facts that drive the lean

**Official route is stronger than the task book assumed in three places**

1. **Gerber and CPL exist in the official API.** `PCB_ManufactureData.getGerberFile`
   produced a 1,292,203-byte zip and `getPickAndPlaceFile` an 8,433-byte CSV
   (hashes in `artifacts/`). A's own capability matrix reports
   `gerber.export/drill.export/cpl.export = unsupported` (0 typed actions).
   For manufacturing exports the official route is strictly ahead.
2. **MCP is real.** `lceda-pro --mcp stdio` speaks JSON-RPC 2.0 (protocol
   `2025-06-18`) and exposes `lceda-pro.help/discover/call`. A has no MCP server,
   so B1 Phase 2 cannot use A without writing a gateway.
3. **`doc api` is a complete offline contract.** 388 types, 20 classes and the
   scriptable surface (create/modify/save/importChanges/DRC/export) are
   queryable with no session and no network - a much better model-facing
   discovery surface than a hand-maintained typed catalog.

**Official route has real defects that need a wrapper**

1. `open` returns `ok:true` before the project loads; `getReadyState()` still
   says `notLoaded` when `getCurrentProjectInfo()` is already populated. A
   load-poll is mandatory.
2. `sch_Net.getAllNets()/getAllNetsName()/getCurrentProjectAllNets()` returned
   `[]` on a loaded project with a 34 KB netlist. Net truth must come from the
   Protel netlist text (the Skill already has `netlist_diff.py`).
3. `sys_FileSystem.*` throws without external-interaction permission; exporting
   files required a base64 relay through the invoke result.
4. Each `invoke` costs about **1.0 s** (measured 10,082.7 ms / 10 calls); one
   batched script doing the same 10 reads cost 995.6 ms. Per-action CLI calls
   are unacceptable for a model workflow - a batch plan per invoke is mandatory.
5. Timeouts leave unknown side effects (`REQUEST_TIMEOUT`: "the code may still be
   running in the render, and its result will be discarded"); retries must be
   readback-driven.
6. Silent booleans (`activateDocument` on a bogus id returns `false`) and
   undocumented DRC return shapes need explicit checks.

**A is expensive and cannot be validated here**

- ~1,700 files in PR #36, 1,130 of them in `runtime/`+`connector/`; a Go fork of
  `easyeda-agent v1.15.0` (MIT) plus a TypeScript `.eext` that must be imported
  into EDA **by hand** and only loads at EDA startup.
- No Go toolchain on this host (and the task book forbids installing one), so A
  cannot be rebuilt; the connector exists only inside the user's GUI session, so
  an A run would drive the user's window - forbidden by the isolation rules.
- A's own M1 evidence: 0 supported / 19 unknown / 5 unsupported capabilities and
  a failing `go test` set (40 cases, claimed upstream-only). Later M2-M4 PASS
  self-evidence exists but was not independently verified.

## 3. Provisional lean: A2

Keep the official CLI/MCP as the execution backend and replace the typed-action
value with a thin local layer (`spike/a2-coverage/` is the seed):

- session lifecycle (`--headless` + `--destroy`) and a **user-session guard**;
- project-load poll + document activation + readiness checks;
- error-code mapping (`SESSION_NOT_FOUND`/`INVALID_ARGS`/`REQUEST_TIMEOUT`/...);
- plan -> execute-one-batch -> readback -> evidence (JSON receipt + hashes);
- netlist-based net truth and export relay (base64 -> file + sha256);
- offline `doc api` catalog snapshot so the model never guesses method names.

Remaining gaps that still argue for keeping something from A are limited to:
typed write plans with per-action journaling (W04-W06) and a typed DFM audit
(W07). Both are <=2 workflows, which keeps A2's "thin wrapper" condition
plausible.

## 4. What would overturn this lean

- **Toward A1**: an authorized write probe shows that official writes in
  4.1.78 are unreliable under load (async commit drops, importChanges no-op in
  half-offline, save not persisting on reopen, silent false booleans) such that
  a thin wrapper cannot enforce single-writer/rollback - i.e. W04/W05/W09-save
  come back `partial` with no feasible thin fix.
- **Toward A3**: the authorized write probe passes cleanly for W04/W05/W09
  (save+reopen+readback) and W02 net reading is fixed by netlist parsing; then
  official covers >=7/8 critical and A's remaining value is negligible.
- **Toward "A2 plus keep distribution"**: if install/upgrade/branding (A's
  `distribution/`) is still wanted, keep it without runtime/connector.
- Confidence is **low** until W04/W05/W09-save are measured on a disposable,
  authorized project.

## 5. PR #36 split recommendation (do not merge on our behalf)

> **State update after the evidence run (2026-10-28, later):** PR #36 has since
> been **merged** into `main` (`Merge pull request #36 ...`), so `main` now
> contains `runtime/`, `connector/` and `protocol/`; the A branch moved to
> `3c93015` with a **25-file** residual delta (manufacture exports). The split
> below is therefore a historical reference, not three PRs to open today. The
> executable command list for what is actionable now is
> [`pr36-split-runbook.md`](pr36-split-runbook.md) (with generated path sets in
> `pr-split/`).

The A branch was one 1,700-file PR mixing four separable concerns. Recommended
split, in merge order:

1. **PR-1 "docs + offline methodology"** (small, no EDA):
   `docs/toolchain-integration/*` methodology/capability/acceptance documents,
   `benchmarks/` additions, `tools/zhigou_acceptance.py`-style offline tests,
   `design-hardware/scripts/*` pure-offline helpers. Acceptance: offline test
   suite green on 3.10/3.13, no runtime/connector files.
2. **PR-2 "distribution / install-upgrade-diagnostics"** (no runtime):
   `distribution/`, installer lifecycle tests, doctor UI text. Acceptance:
   install/upgrade/rollback lifecycle suite green, no EDA write.
3. **PR-3 "retire runtime/connector/protocol, add thin official-CLI adapter"**
   (replaces the fork): delete `runtime/`, `connector/`, `protocol/`,
   `third_party/easyeda-agent`; keep/port `docs/zhigou-mcp`, the offline
   benchmark harness, and this spike's adapter (`spike/a2-coverage/` promoted to
   `design-hardware/scripts/official_cli_*` only after the write probe passes).
   Acceptance: 11-workflow matrix regenerated with W04/W05/W09 covered; no
   change to Skill entry points; `skill_selftest.py` 5 PASS.

Rationale: PR-1/PR-2 carry the durable value and can land without a connector;
PR-3 is the actual A2 decision and should only land **after** the authorized
write probe closes W04/W05/W09.

## 6. B1 Phase 2 conclusion

- Execution backend: **official CLI/MCP**, not A's daemon/connector. A has no
  MCP entry, needs Go to rebuild, and its connector cannot be loaded into a
  CLI-owned session.
- B1 must implement its own **write gate**: project-load polling, user-session
  refusal, plan/readback receipts, timeout -> readback (never blind retry), and
  an explicit `--headless`/`--destroy` session policy. The official CLI alone is
  not safe enough for unattended writes.
