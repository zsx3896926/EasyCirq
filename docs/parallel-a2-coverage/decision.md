# Decision memo: A1 / A2 / A3 (provisional)

**Status: `decision-provisional`** - the authorized write probe on 2026-10-28 closed
W04/W05/W09 (they are `covered` with save/reopen/readback receipts). No final
A1/A2/A3 is issued yet because the three remaining critical cells are `partial`
(thin-wrapper scope: W02 net reads, W06 batch plan, W07 DRC/DFM shaping), so the
A2 ">=7/8 covered" condition is not met. This file records the evidence-based
provisional lean only.

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
| W04 schematic write | `covered` | authorized probe: device + wire + net label + net flag + save + readback |
| W05 PCB write | `covered` | authorized probe: importChanges + move + save + reopen pose check |
| W09 save/reopen | `covered` | authorized probe: save -> close --destroy -> reopen -> readback; source untouched |
| W02 schematic read | `partial` | net API returns empty; netlist text is the fallback |
| W06 batch | `partial` | read batching measured; a typed batch/journal plan is still wrapper work |
| W07 DRC/DFM | `partial` | DRC receipts work but the shapes are undocumented and DFM has no official equivalent |

Covered critical cells: W04, W05, W08 (export, real artifacts), W09, W11 (MCP).
Non-critical: W01 and W10 covered; W03 partial. No critical cell is blocked or
not-run any more, so the decision moved from "missing evidence" to "wrapper scope".

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

**Official writes are real (authorized probe, 2026-10-28)**

1. A device was placed from the system library (`lib_Device.search('0402')` +
   `sch_PrimitiveComponent.create`), a wire/`net label`/net flag were created,
   `save` returned true, and readback went from 58 to 60 components and 34 to 35
   wires (`write-probe/raw/W04*`).
2. `importChanges(false)` returned true, a PCB component (DC1) was moved
   +50/+50, `pcb_Document.save()` returned true, and after reopening the copy the
   pose matched within 2 raw units (`W05-pcb-write`, `W09-readback`).
3. `save -> session close --destroy -> reopen -> readback` found the net flag,
   wire, placed device and moved PCB component again; the copy's sha256 changed
   from `824f6dcc...` to `4be11c20...` while the read-only source fixture stayed
   byte-identical (`write-probe-passed.json`).
4. Quirks that a wrapper must encode: creating from an existing component/symbol
   identity hangs (>90 s, 3 attempts); `getAllPinsByPrimitiveId` on a freshly
   created async component blocked one 240 s invoke; `createNetLabel` returned
   `null` while persisting (readback via `sch_PrimitiveAttribute.getAll` is the
   only truth); a single long JS program can hit `REQUEST_TIMEOUT` and discard
   everything, so the probe runs one short invoke per write step.



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

Remaining critical gaps are thin-wrapper scope, not missing host capability:
W02 net reads are already closed offline by the Protel-netlist parser
(`netlist_diff.py`); W06 needs a batch plan/journal (the CLI has none); W07 needs
shaping of the DRC receipts and a decision on DFM (A's rebuild-based check has no
official equivalent). That is 2-3 wrapper workflows, which keeps A2's "thin
wrapper" condition plausible.

## 4. What would overturn this lean

- **Toward A1**: the thin wrapper for W06/W07 proves unacceptable (e.g. DRC
  receipts are too unstable to gate on, or batch/journal semantics cannot be
  enforced without a daemon) while A's typed check/batch actions are clearly
  better; then keep A for the remaining gap instead of retiring it.
- **Toward A3**: the W02 netlist parser + Skill-side DFM are accepted as the
  wrapper, and the remaining W06/W07 gaps are judged negligible; official then
  covers 5/8 critical with 3 wrapper closures, and A's retention cost (1,700-file
  PR history, Go fork, manual connector import) dominates.
- **Toward "A2 plus keep distribution"**: if install/upgrade/branding (A's
  `distribution/`) is still wanted, keep it without runtime/connector.
- Confidence is **medium** now that the write path is proven; the remaining
  uncertainty is wrapper quality (W06/W07), not host capability.

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

## 7. Authorized write probe record (2026-10-28)

| item | value |
| --- | --- |
| authorization | `docs/evidence/a2-coverage-2026-10-28/write-probe/authorization.json` (granted_by `jlc`, scope W04/W05/W09, project_root under `%TEMP%`) |
| runner | `spike/a2-coverage/probe_writes.py` (refuses without authorization; temp copy only; user session untouched) |
| temp project | `C:\Users\jlc\AppData\Local\Temp\a2-write-probe-20261028\run-20261028-125326\a2write-run-20261028-125326.eprj2` |
| marker | `docs/evidence/a2-coverage-2026-10-28/write-probe-passed.json` (all checks true) |
| W04 | device placed (system-library `0402`), wire + net label + net flag, save true, readback 58->60 components / 34->35 wires |
| W05 | `importChanges(true)`, DC1 moved +50/+50, save true, reopen pose match within 2 raw units |
| W09 | save -> close --destroy -> reopen readback: flag/wire/device/PCB pose persisted; copy sha256 `824f6dcc...` -> `4be11c20...`; source fixture unchanged |
| failures kept | `write-probe/attempt1/` (single 240 s invoke timed out) and `attempt2/` (net label return value null) |
| cleanup | delete `%TEMP%\a2-write-probe-20261028\` after review |

This closes the Step 3 gate in `pr36-split-runbook.md`: the retire PR may now be
opened, but the A1/A2/A3 decision itself remains provisional because W02/W06/W07
are wrapper work.
