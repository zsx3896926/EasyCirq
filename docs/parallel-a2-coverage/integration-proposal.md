# Integration proposal (A2 provisional): typed layer on the official CLI/MCP

Status: proposal for the A2 lean, **not a final decision** (see `decision.md`).
Nothing here may be merged before the authorized write probe closes W04/W05/W09.

## 1. Boundary: what the thin layer owns

The official CLI already supplies the hard part (the `eda.*` API, sessions,
exports, MCP transport). What it does not supply, and what the thin layer must:

| # | gate | why (evidence) |
| --- | --- | --- |
| G1 | session lifecycle: always `open --headless`, always `session close --destroy`, refuse `origin:"user"` sessions | W01: CLI windows leak; user window must never be driven |
| G2 | project-load poll + document activation + readiness check | W01: `open` returns before load; `getReadyState()` lies |
| G3 | error-code mapping (`SESSION_NOT_FOUND`/`INVALID_ARGS`/`DOC_QUERY_FAILED`/`EXECUTION_ERROR`/`REQUEST_TIMEOUT`) | W10: exit code alone is not enough |
| G4 | plan -> one batched JS program -> per-item readback -> receipt | W06: ~1 s per invoke; batching is 10x cheaper |
| G5 | timeout => readback, never blind retry | W10: `REQUEST_TIMEOUT` says the code may still be running |
| G6 | net truth from Protel netlist (parse + diff) | W02: typed net API returns empty |
| G7 | export relay: `File`/Blob -> base64 -> file + sha256 | W08: `sys_FileSystem` is permission-gated |
| G8 | active-document discipline for checks/exports | W07: wrong doctype throws; exports follow the active doc |
| G9 | offline method catalog snapshot (`doc api`) so the model never guesses | `doc api` works offline, 388 types |

## 2. Action mapping (A typed action -> official CLI)

| A typed action (example) | official implementation |
| --- | --- |
| `zhigou doctor` | `lceda-pro doctor` + `session list` |
| `zhigou sch read` / `nets` / `connectivity` | `invoke` -> `dmt_Project.getCurrentProjectInfo`, `sch_PrimitiveComponent.getAll`, `getAllPinsByPrimitiveId`, `sch_PrimitiveWire.getAll`, `sch_Netlist.getNetlist` |
| `zhigou pcb dump` / `layers` / `nets` | `invoke` -> `dmt_Pcb.getAllPcbsInfo`, `pcb_Layer.getAllLayers`, `pcb_Net.getAllNets`, `pcb_PrimitiveComponent.getAll` |
| `zhigou sch place` / `connect` / `netflag` | `invoke` -> `sch_PrimitiveComponent.create`, `sch_PrimitiveWire.create`, `sch_PrimitiveComponent.createNetFlag/createNetPort`, then fresh readback |
| `zhigou sch save` / `pcb save` | `invoke` -> `sch_Document.save` / `pcb_Document.save` + close/reopen readback |
| `zhigou pcb import_changes` | `invoke` -> `sch_Document.importChanges` (verify materialization, not just `true`) |
| `zhigou pcb route.auto` | `invoke` -> `pcb_Document.autoRouting` / `startAutoRouting` + `getAutoJobStatus` |
| `zhigou sch drc` / `pcb drc` | `invoke` -> `sch_Drc.check` / `pcb_Drc.check` (parse the structured shapes observed in 4.1.78) |
| `zhigou sch export *` / `bom export` | `invoke` -> `sch_ManufactureData.get*File` + G7 relay |
| Gerber / CPL (A: unsupported) | `invoke` -> `pcb_ManufactureData.getGerberFile` / `getPickAndPlaceFile` |
| `zhigou project export` | no direct equivalent; keep as a Skilled GUI procedure or accept loss |
| typed batch/module plan | one JS program per plan + caller-side journal file |

## 3. What to retire, what to keep

- **Retire**: `runtime/` (Go daemon + 192 CLI entries), `connector/` (`.eext`),
  `protocol/`, `third_party/easyeda-agent`, the daemon-specific tests and
  `distribution/` steps that install the connector.
- **Keep**: `distribution/` install/upgrade/rollback (useful independently), the
  offline audit modules and `docs/zhigou-mcp` server (no EDA dependency), the
  Skill's offline gates, and the evidence discipline (six-state fields) which
  should be re-expressed in the thin layer's receipts.
- **Add**: `spike/a2-coverage/` promoted (after the write probe) into a small
  `design-hardware/scripts/official_cli_*` adapter + workflow definitions.

## 4. PR #36 split (concrete)

### PR-1 `docs(toolchain): offline methodology, capability matrix and acceptance design`

- Files: `docs/toolchain-integration/{architecture,capability-matrix,acceptance-matrix,environment-baseline}.md`,
  `protocol/reference/*` (read-only reference only), `benchmarks/` offline
  additions, `design-hardware/scripts/*` pure-offline helpers.
- Not included: `runtime/`, `connector/`, `protocol/schemas`, `distribution/`.
- Acceptance: offline suite green on Python 3.10/3.13; no EDA, no Go, no network;
  `skill_selftest.py` 5 PASS.

### PR-2 `feat(distribution): installer/upgrade/rollback and diagnostics`

- Files: `distribution/`, installer lifecycle tests, doctor text assets.
- Acceptance: install/upgrade/rollback suite green in a temp dir; no EDA write;
  no self-update path to upstream.

### PR-3 `feat(eda): thin official-CLI adapter, retire runtime/connector/protocol`

- Depends on: the authorized write probe (W04/W05/W09) and this spike's matrix
  regenerated with those cells `covered`.
- Files: delete `runtime/`, `connector/`, `protocol/`, `third_party/easyeda-agent`;
  add `design-hardware/scripts/official_cli_*.py` + workflow definitions + tests.
- Acceptance: 11-workflow matrix >=7/8 critical `covered`; save/reopen/readback
  receipts for W04/W05/W09; session guard proven against an `origin:"user"`
  session; `python -m unittest discover -s tests` green; `skill_selftest.py`
  5 PASS; no change to Skill entry points.

Ordering: PR-1 and PR-2 are independent and can land first. PR-3 carries the
A2 decision and must not land before the write probe.

## 5. Appendix: if the write probe overturns the lean to A1

- Keep `runtime/`+`connector/`+`protocol/` but ship PR-1/PR-2 as prerequisites.
- Required before merge: rebuild Go green on CI (3 OS), connector import and
  handshake evidence on a fresh machine, the 1700-file PR split as above but with
  PR-3 changed to `fix(runtime): green build + CI + connector lifecycle`.
- B1 then talks to A's daemon (HTTP/WS typed actions) instead of the CLI/MCP,
  but still needs its own write gate.
