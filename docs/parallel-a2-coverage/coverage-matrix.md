# A2 coverage matrix: official lceda-pro CLI/MCP vs A typed action

- generated: 2026-10-28T12:57:09+08:00
- evidence: `docs/evidence/a2-coverage-2026-10-28/`
- baseline main: `fd4499cd3c98dc66c96bb38a703ce562e1c3dbe5`
- A reference (read-only): `origin/feat/integrated-eda-toolchain @ dfa8f10d7149df435ab0c0be91edcdcb91990ce1 (read-only)`
- official CLI: JLCEDA Pro 4.1.78.34f5b8d9
- decision: **incomplete** (provisional)

Status vocabulary: `covered` / `partial` / `unsupported` / `blocked` / `not_run`; A additionally uses `static` (mapped from A catalog/self-evidence, not run by this spike).

| ID | workflow | official | A | critical | verdict | official evidence |
| --- | --- | --- | --- | --- | --- | --- |
| W01 | connect / session / version | **covered** | static | no | official_sufficient | `docs/evidence/a2-coverage-2026-10-28/raw/W01-doctor.stdout.json` |
| W02 | schematic read | **partial** | static | yes | official_sufficient | `docs/evidence/a2-coverage-2026-10-28/raw/W02-activate-sch.stdout.json` |
| W03 | PCB read | **partial** | static | no | official_sufficient | `docs/evidence/a2-coverage-2026-10-28/raw/W03-activate-pcb.stdout.json` |
| W04 | schematic write + readback | **covered** | static | yes | official_sufficient | `docs/evidence/a2-coverage-2026-10-28/write-probe/raw/W04a-create.stdout.json` |
| W05 | PCB write | **covered** | static | yes | official_sufficient | `docs/evidence/a2-coverage-2026-10-28/write-probe/raw/W05-pcb-write.stdout.json` |
| W06 | batch / plan application | **partial** | static | yes | both_needed | `docs/evidence/a2-coverage-2026-10-28/raw/W06-batched-read.stdout.json` |
| W07 | check / DRC / DFM | **partial** | static | yes | both_needed | `docs/evidence/a2-coverage-2026-10-28/raw/W07-sch-drc.stdout.json` |
| W08 | export | **covered** | unsupported | yes | official_sufficient | `docs/evidence/a2-coverage-2026-10-28/raw/W08-netlist-string.stdout.json` |
| W09 | save / reopen / stale | **covered** | static | yes | official_sufficient | `docs/evidence/a2-coverage-2026-10-28/write-probe/raw/W04e-save-readback.stdout.json` |
| W10 | error / permission / boundary | **covered** | static | no | official_sufficient | `docs/evidence/a2-coverage-2026-10-28/raw/W10-bad-session.stdout.json` |
| W11 | MCP entry | **covered** | unsupported | yes | official_sufficient | `docs/evidence/a2-coverage-2026-10-28/mcp-tools.json` |

## Per-workflow detail

### W01 - connect / session / version (non-critical)

- official: **covered** (measured steps=6, js_lines=18, exit=[0], scope=real-run)
- A: **static** (scope=static)
- verdict: `official_sufficient`
- official commands: `lceda-pro --help`; `lceda-pro doctor`; `lceda-pro open --path <temp-copy>.eprj2 --headless`; `lceda-pro session list`; `lceda-pro session close --session <id> --destroy`
- official observation: doctor: connected=true, versionMatch=true, resultChannel=true, bridgeVersion=4.1.78.34f5b8d9, exit 0.
- official observation: --help first line is 'JLCEDA Pro 4.1.78.34f5b8d9'; commands: activate/open/stop/doctor/session/invoke/functions/doc + --mcp.
- official observation: open --headless returns a sessionId in about 1 s, but the project keeps loading afterwards: polling getCurrentProjectInfo() needed ~3.9 s.
- official observation: getReadyState() still returned 'notLoaded' after getCurrentProjectInfo() already returned the full project tree, so it cannot be used as a load gate.
- official observation: There was exactly one origin=user session before and after the run; this spike only drove origin=cli sessions opened by itself.
- official observation: A bare headless editor exposes 0 installed extensions; the fixture session exposes 3 (eext-common, zsxedahelper, dix) and none of them is the A connector.
- official observation: open --path with a non-existent project path returns ok:true with a sessionId but creates/loads no project; ok:true is a transport-level statement.
- official risk: ok:true/exit 0 only means the call ran, not that the business state is correct
- official risk: a CLI-opened window leaks unless session close --destroy is used
- official risk: CLI sessions are half-offline by design (isHalfOfflineMode=true), not a full-online acceptance
- official risk: PowerShell cannot capture this program's stdout with $x = & ... or > file; pipes/Start-Process are required
- A actions: `zhigou doctor`; `zhigou capabilities`; `zhigou health`; `zhigou connector verify`; `handshake/register frames (protocol v1, service zhigou-agent, ws://127.0.0.1:23111-23120)`
- A observation: A self-evidence (M1, A branch): doctor verdict=degraded, connector disconnected, capabilities 0 supported / 19 unknown / 5 unsupported.
- A observation: A self-evidence (task-status): connector import was completed later by the operator; M2-M4 are claimed PASS on a dedicated project, but our spike did not run any A command.
- A observation: A isolates by service name/ports/state dir; its process model adds a daemon + WebSocket + extension that must be imported by hand and only loads at EDA startup.
- A blocker: Go toolchain is not installed on this host, so the A branch cannot be built to run (task book section 12 forbids installing Go).
- A blocker: The A connector lives only inside the user's GUI session; CLI-opened sessions list 0 extensions, so any A run would target the user's window - forbidden by task book section 4.2.
- A blocker: A exposes no MCP server; a gateway would have to be written.
- notes: Official route needs one human habit (always --headless + --destroy) and an explicit load-poll instead of getReadyState().

Evidence: `docs/evidence/a2-coverage-2026-10-28/raw/W01-doctor.stdout.json`, `docs/evidence/a2-coverage-2026-10-28/raw/W01-help.stdout.json`, `docs/evidence/a2-coverage-2026-10-28/raw/W01-open.stdout.json`, `docs/evidence/a2-coverage-2026-10-28/raw/W01-wait-project.stdout.json`, `docs/evidence/a2-coverage-2026-10-28/raw/W01-sessions-before.stdout.json`, `docs/evidence/a2-coverage-2026-10-28/raw/W01-sessions-after-open.stdout.json`, `docs/evidence/a2-coverage-2026-10-28/sessions-before.json`, `docs/evidence/a2-coverage-2026-10-28/sessions-after.json`, `docs/evidence/a2-coverage-2026-10-28/extensions-headless.json`

### W02 - schematic read (critical)

- official: **partial** (measured steps=3, js_lines=85, exit=[0], scope=real-run)
- A: **static** (scope=static)
- verdict: `official_sufficient`
- official commands: `invoke -> eda.dmt_Project.getCurrentProjectInfo`; `invoke -> eda.dmt_EditorControl.openDocument/activateDocument`; `invoke -> eda.sch_PrimitiveComponent.getAll(undefined, true)`; `invoke -> eda.sch_PrimitiveComponent.getAllPinsByPrimitiveId(id)`; `invoke -> eda.sch_PrimitiveWire.getAll()`; `invoke -> eda.sch_Net.getAllNets()/getAllNetsName()/getCurrentProjectAllNets()`; `invoke -> eda.sch_Netlist.getNetlist(Protel2)`
- official observation: Read 58 schematic components (designator/component/symbol/footprint/x/y/rotation/mirror/supplierId) and 34 wires with real geometry; pins returned actual x/y, pinNumber, pinType, noConnected.
- official observation: waitForDocumentReady() returned false for both the page uuid and the tab handle even though the page was activated and components were readable; it is not a usable readiness gate.
- official observation: sch_Net.getAllNets(), getAllNetsName() and getCurrentProjectAllNets() all returned [] on a loaded project whose Protel netlist is 34,413 bytes, so the typed net API cannot be the source of truth; parsing the netlist text is required.
- official observation: Component read required allSchematicPages=true to see the whole design; per-page reads follow the active document.
- official risk: net enumeration API returns empty on this fixture/version - silent data loss if trusted
- official risk: background/inactive pages return shallow data; explicit page activation is required
- official risk: text objects and title-block content were not probed in this run
- A actions: `zhigou sch read`; `zhigou sch list`; `zhigou sch connectivity`; `zhigou sch nets`; `schematic.designators.list / attribute.inspect / visible_text.bboxes`
- A observation: A catalog has 15 schematic read actions (including connectivity and nets) but the acceptance matrix marks every real-host row BLOCKED at M1; later self-evidence claims M2 PASS.
- A observation: A's net/pin read is a typed action with declared readback semantics, which would remove the netlist-parsing step - but we have no independent A receipt.
- A blocker: not run by this spike (no Go build; connector only in the user's window)
- A blocker: A self-evidence is not our measurement and cannot upgrade this cell beyond static
- notes: Official read works; the net API gap is closed by parsing the Protel netlist, which the Skill already does offline (netlist_diff.py).

Evidence: `docs/evidence/a2-coverage-2026-10-28/raw/W02-activate-sch.stdout.json`, `docs/evidence/a2-coverage-2026-10-28/raw/W02-sch-read.stdout.json`, `docs/evidence/a2-coverage-2026-10-28/raw/W02-nets-retry.stdout.json`, `docs/evidence/a2-coverage-2026-10-28/artifacts/schematic.net`

### W03 - PCB read (non-critical)

- official: **partial** (measured steps=2, js_lines=51, exit=[0], scope=real-run)
- A: **static** (scope=static)
- verdict: `official_sufficient`
- official commands: `invoke -> eda.dmt_Pcb.getAllPcbsInfo`; `invoke -> eda.pcb_Layer.getAllLayers / getTheNumberOfCopperLayers`; `invoke -> eda.pcb_Net.getAllNets`; `invoke -> eda.pcb_PrimitiveComponent.getAll`
- official observation: 1 PCB document, 289 layer entries (2 copper), 17 nets and 33 placed components were read from the fixture.
- official observation: Layer records carry id/name/type/color/transparency/locked; the copper layer count comes from a dedicated API.
- official observation: Coordinate units and anchor semantics were not independently measured in this run (the API exposes convertCanvasOriginToDataOrigin/convertDataOriginToCanvasOrigin but we did not probe them).
- official risk: unit / y-axis convention needs an explicit conversion step and a unit test
- official risk: primitive ids are session-scoped; re-read before any write
- official risk: outline / copper geometry were not dumped (only counts and layers), so a geometry-complete read is unproven
- A actions: `zhigou pcb dump`; `zhigou pcb list / layers / nets / outline / components`
- A observation: A catalog has 27 PCB read actions and a documented unit convention (mil, y-up, anchor vs bbox center), which is more prescriptive than the raw official API.
- A observation: No independent A receipt exists for this spike.
- A blocker: not run by this spike
- A blocker: A unit convention is documentation, not proof it matches the official host
- notes: Read is available; a thin normalization layer for units/anchor is the only obvious value-add.

Evidence: `docs/evidence/a2-coverage-2026-10-28/raw/W03-activate-pcb.stdout.json`, `docs/evidence/a2-coverage-2026-10-28/raw/W03-pcb-read.stdout.json`

### W04 - schematic write + readback (critical)

- official: **covered** (measured steps=5, js_lines=202, exit=[0], scope=real-run)
- A: **static** (scope=static)
- verdict: `official_sufficient`
- official commands: `invoke -> eda.lib_Device.search('0402', systemLibraryUuid)`; `invoke -> eda.sch_PrimitiveComponent.create(searchItem, 200, 600)`; `invoke -> eda.sch_PrimitiveWire.create([220,600,260,600], 'A2PROBE_NET')`; `invoke -> eda.sch_PrimitiveAttribute.createNetLabel(260, 600, 'A2PROBE_NET')`; `invoke -> eda.sch_PrimitiveComponent.createNetFlag('Power', 'A2PROBE_VCC', 200, 540)`; `invoke -> eda.sch_Document.save()`; `invoke -> readback: sch_PrimitiveComponent.getAll / sch_PrimitiveWire.getAll / sch_PrimitiveAttribute.getAll`
- official observation: Placed a real device from the system library (search '0402' -> item uuid 1e1c274d..., create returned primitiveId 744247fef1283782, designator 'U?'), then created wire A2PROBE_NET, net label A2PROBE_NET, net flag A2PROBE_VCC and saved (save -> true).
- official observation: Readback after save: components 58 -> 60 (device + net flag), wires 34 -> 35, flag found by name, label found via sch_PrimitiveAttribute.getAll (value A2PROBE_NET), device found by proximity.
- official observation: createNetLabel returned null while the attribute was actually persisted: the only reliable check is a readback through sch_PrimitiveAttribute.getAll.
- official observation: Creating a component from an existing component/symbol identity (libraryUuid empty or 'project', symbol uuid) hung >90 s three times; only the library-search-item path is usable in 4.1.78 half-offline mode.
- official observation: sch_PrimitiveComponent.getAllPinsByPrimitiveId on a freshly created async component blocked one 240 s invoke, so the wire is a standalone segment at fixed coordinates instead of a pin-attached wire.
- official observation: Each write is an independent invoke (create/wire/label/flag/save/readback) because a single long program can hit REQUEST_TIMEOUT and discard its result, hiding the steps that already succeeded.
- official risk: device creation must go through a library search item; identity-based create hangs
- official risk: pin lookup on a not-yet-committed component can hang; wait or avoid
- official risk: createNetLabel create return value is unreliable (null on success)
- official risk: ok:true only means the code ran; every write needs a fresh readback
- official risk: no typed idempotency: repeated create makes duplicates
- A actions: `zhigou sch place`; `zhigou sch modify`; `zhigou sch connect`; `zhigou sch netflag`; `zhigou sch no-connect`; `zhigou sch save`
- A observation: A catalog has 26 schematic write actions and its self-evidence claims a real schematic write/save/reopen chain (M2-M4).
- A observation: A typed action removes the JS-authoring and readback-batching burden; this is the strongest non-replaceable argument for A.
- A blocker: not run by this spike (no Go build, connector in user window only)
- A blocker: no independent receipt
- notes: Authorized write probe passed on a disposable %TEMP% copy: device/wire/net label/net flag + save + readback. Identity-based create hangs; use library search items.

Evidence: `docs/evidence/a2-coverage-2026-10-28/write-probe/raw/W04a-create.stdout.json`, `docs/evidence/a2-coverage-2026-10-28/write-probe/raw/W04b-wire.stdout.json`, `docs/evidence/a2-coverage-2026-10-28/write-probe/raw/W04c-label.stdout.json`, `docs/evidence/a2-coverage-2026-10-28/write-probe/raw/W04d-flag.stdout.json`, `docs/evidence/a2-coverage-2026-10-28/write-probe/raw/W04e-save-readback.stdout.json`, `docs/evidence/a2-coverage-2026-10-28/write-probe/write-probe-run.json`, `docs/evidence/a2-coverage-2026-10-28/write-probe-passed.json`, `docs/evidence/a2-coverage-2026-10-28/write-probe/authorization.json`

### W05 - PCB write (critical)

- official: **covered** (measured steps=1, js_lines=69, exit=[0], scope=real-run)
- A: **static** (scope=static)
- verdict: `official_sufficient`
- official commands: `invoke -> eda.sch_Document.importChanges(false)`; `invoke -> eda.pcb_PrimitiveComponent.getAll()`; `invoke -> eda.pcb_PrimitiveComponent.modify(primitiveId, {x+50, y+50})`; `invoke -> eda.pcb_Document.save()`; `invoke -> readback: pcb_PrimitiveComponent.getAll() by designator`
- official observation: importChanges(false) returned true and materialised the schematic onto the PCB copy.
- official observation: Moved an existing PCB component (DC1) by +50/+50 raw units via pcb_PrimitiveComponent.modify; immediate readback found the same designator at the new pose.
- official observation: pcb_Document.save() returned true; after session close + reopen, the DC1 pose matched the saved pose within 2 raw units.
- official observation: The PCB layer/net/component read surface used for readback was already measured in W03.
- official risk: importChanges is a whole-schematic rebuild of the PCB, not a minimal diff
- official risk: no undo; a wrong move is only recoverable by re-editing
- official risk: primitiveId is session-scoped: locate by designator after reopen
- official risk: save true is not persistence: the reopen readback is the evidence
- A actions: `zhigou pcb import_changes`; `zhigou pcb modify`; `zhigou pcb place`; `zhigou pcb track`; `zhigou pcb via`; `zhigou pcb save`; `zhigou pcb route.auto`
- A observation: A catalog has 58 PCB write actions plus typed route/pour/drc helpers and claims a real M4 board build (layout, autoroute 6/6, pours, DRC 0).
- A observation: A's typed write actions are a real cost advantage over hand-written JS for PCB.
- A blocker: not run by this spike
- A blocker: no independent receipt
- notes: Authorized write probe passed: importChanges + move + save + reopen pose check on a disposable copy.

Evidence: `docs/evidence/a2-coverage-2026-10-28/write-probe/raw/W05-pcb-write.stdout.json`, `docs/evidence/a2-coverage-2026-10-28/write-probe/raw/W09-readback.stdout.json`, `docs/evidence/a2-coverage-2026-10-28/write-probe/write-probe-run.json`, `docs/evidence/a2-coverage-2026-10-28/write-probe-passed.json`

### W06 - batch / plan application (critical)

- official: **partial** (measured steps=1, js_lines=12, exit=[0], scope=real-run)
- A: **static** (scope=static)
- verdict: `both_needed`
- official commands: `10 x lceda-pro invoke (separate round-trips)`; `1 x lceda-pro invoke with a 10-read JS batch`; `lceda-pro invoke --timeout 3000 (timeout semantics)`
- official observation: Measured CLI round-trip cost: 10 separate invokes took 10,082.7 ms (about 1,008 ms each); one invoke doing the same 10 reads took 995.6 ms.
- official observation: Batching inside one JS program is about 10x cheaper than one invoke per action, so the model should compose a plan per invoke instead of calling one invoke per object.
- official observation: There is no typed batch/transaction semantics: each invoke is an independent program; on timeout the CLI reports REQUEST_TIMEOUT and says the code may still be running and its result is discarded.
- official observation: Write batching could not be measured (no authorization).
- official risk: timeout leaves unknown state; blind retry can duplicate creates
- official risk: no per-action journal/idempotency key at the CLI layer
- official risk: long JS programs are opaque to review and hard to resume
- A actions: `typed batch/module plan actions`; `per-request id + planned/sent/confirmed/failed/unknown task log (~/.zhigou/audit)`; `concurrentWriter hint + single-writer discipline`
- A observation: A's daemon keeps a task log with request ids and states, which is a real advantage for resumable batches; the CLI has nothing comparable.
- A observation: Not run by this spike.
- A blocker: not run by this spike
- A blocker: no independent receipt
- notes: A thin batch plan (compose one JS program + readback + journal written by the caller) can reproduce most of this; the CLI's 1 s round-trip makes per-call-per-action designs unacceptable.

Evidence: `docs/evidence/a2-coverage-2026-10-28/raw/W06-batched-read.stdout.json`, `docs/evidence/a2-coverage-2026-10-28/raw/W10-timeout.stdout.json`, `docs/evidence/a2-coverage-2026-10-28/probe-run.json`

### W07 - check / DRC / DFM (critical)

- official: **partial** (measured steps=4, js_lines=52, exit=[0], scope=real-run)
- A: **static** (scope=static)
- verdict: `both_needed`
- official commands: `invoke -> eda.sch_Drc.check(false, false, true)`; `invoke -> eda.pcb_Drc.check(false, false, true)`; `invoke -> eda.pcb_Drc.getRealTimeDrcStatus`
- official observation: Schematic DRC with includeVerboseError=true returned a structured warning array (rule ATTRMATCHCODE, primitive ids) even though the documented return type is boolean; the receipt is usable as evidence.
- official observation: PCB DRC returned a structured error-group tree (count 1: netlist mismatch because schematic changes were never imported on this sample) and realtime status false.
- official observation: DRC acts on the active document: calling schematic DRC while a PCB document was active threw 'SCH_DrcUtil: doctype(3) not support check sch drc'.
- official observation: No DFM-equivalent audit was found in the official surface (PCB_Drc has rules/check only); A's pcb check is a rebuild-based DFM audit.
- official risk: documented return type disagrees with the observed shape
- official risk: active-document dependency; wrong doctype errors are easy to hit
- official risk: DFM/process checks are out of scope for official DRC
- A actions: `zhigou sch drc`; `zhigou sch check`; `zhigou sch layout-lint`; `zhigou pcb drc`; `zhigou pcb check`
- A observation: A self-evidence claims native schematic DRC PASS (0 violations) and PCB DRC 0 violations plus a DFM audit with 0 errors / 4 warnings on its M4 board.
- A observation: A's check actions return typed receipts with counts and scope, which formats better than the raw official arrays.
- A blocker: not run by this spike
- A blocker: no independent receipt
- notes: Official DRC is usable once the active-document rule is encoded; DFM remains an offline (Skill) or typed (A) capability.

Evidence: `docs/evidence/a2-coverage-2026-10-28/raw/W07-sch-drc.stdout.json`, `docs/evidence/a2-coverage-2026-10-28/raw/W07-pcb-drc.stdout.json`

### W08 - export (critical)

- official: **covered** (measured steps=8, js_lines=96, exit=[0], scope=real-run)
- A: **unsupported** (scope=static)
- verdict: `official_sufficient`
- official commands: `invoke -> eda.sch_Netlist.getNetlist(Protel2)`; `invoke -> eda.sch_ManufactureData.getNetlistFile`; `invoke -> eda.sch_ManufactureData.getBomFile(csv)`; `invoke -> eda.sch_ManufactureData.getPngFile`; `invoke -> eda.sch_ManufactureData.getGerberFile? (PCB_ManufactureData.getGerberFile)`; `invoke -> eda.pcb_ManufactureData.getPickAndPlaceFile(csv)`
- official observation: Real artifacts produced: Protel netlist 38,568 B sha256 7bb9874d..., BOM CSV 1,957 B, PNG 712,074 B (PNG magic), Gerber zip 1,292,203 B (zip magic), pick-and-place CSV 8,433 B.
- official observation: Gerber and CPL are available through the official API (PCB_ManufactureData.getGerberFile / getPickAndPlaceFile); A's capability matrix lists gerber/drill/cpl as unsupported.
- official observation: File objects cannot be written to disk with the independent-script permission: eda.sys_FileSystem.* throws until external-interaction permission is enabled. The workaround used here is to read the File in JS, base64 it through the invoke result and write the bytes from Python (PNG 712 KB relayed fine).
- official observation: The CLI appends the requested extension even when the name already has one ('a2spike.net.net', 'a2spike-bom.csv.csv', 'a2spike-page.png.png').
- official risk: binary relay through JSON/base64 is awkward for large files and has no path/sha contract
- official risk: file naming quirk breaks naive automation
- official risk: Gerber layer/object selection defaults must be reviewed before production use
- A actions: `zhigou sch export netlist`; `zhigou sch export bom`; `zhigou sch export image`; `zhigou bom export`; `gerber/drill/cpl: no typed action`
- A observation: A catalog: 3 export actions only; capabilities reports gerber.export/drill.export/cpl.export = unsupported (0 actions).
- A observation: A self-evidence itself records Gerber/drill/CPL as gui_only and not claimed.
- A observation: A project.export (native archive) is a capability the official CLI lacks at the same level, but it is not part of W08's manufacturing exports.
- A blocker: not run by this spike
- A blocker: typed catalog genuinely lacks gerber/drill/cpl
- notes: Official route is strictly better than A for manufacturing exports: A has no Gerber/drill/CPL action at all.

Evidence: `docs/evidence/a2-coverage-2026-10-28/raw/W08-netlist-string.stdout.json`, `docs/evidence/a2-coverage-2026-10-28/raw/W08-netlist-file.stdout.json`, `docs/evidence/a2-coverage-2026-10-28/raw/W08-bom.stdout.json`, `docs/evidence/a2-coverage-2026-10-28/raw/W08-png.stdout.json`, `docs/evidence/a2-coverage-2026-10-28/raw/W08-gerber.stdout.json`, `docs/evidence/a2-coverage-2026-10-28/raw/W08-cpl.stdout.json`, `docs/evidence/a2-coverage-2026-10-28/artifacts/schematic.net`, `docs/evidence/a2-coverage-2026-10-28/artifacts/bom.csv`, `docs/evidence/a2-coverage-2026-10-28/artifacts/page.png`, `docs/evidence/a2-coverage-2026-10-28/artifacts/gerber.zip`, `docs/evidence/a2-coverage-2026-10-28/artifacts/cpl.csv`

### W09 - save / reopen / stale (critical)

- official: **covered** (measured steps=7, js_lines=85, exit=[0], scope=real-run)
- A: **static** (scope=static)
- verdict: `official_sufficient`
- official commands: `invoke -> sch_Document.save() and pcb_Document.save()`; `lceda-pro session close --session <id> --destroy`; `lceda-pro open --path <same copy> --headless`; `invoke -> readback: project uuid + schematic flag/wire/device + PCB designator pose`; `sha256 of the project file before/after`
- official observation: After close --destroy and reopen of the same copy, the project uuid was stable and the net flag A2PROBE_VCC, the wire A2PROBE_NET, the placed device and the moved PCB component (DC1 +50/+50) were all found again.
- official observation: The project file sha256 changed from 824f6dcc... (source copy) to 4be11c20... after the writes, proving the save reached disk.
- official observation: The source fixture stayed byte-identical (sha256 unchanged) - all writes happened on the temp copy only.
- official observation: Primitive ids are not stable across sessions; the reopen readback matches by net name/designator/proximity, not by primitiveId.
- official risk: saved:true still requires the reopen readback before claiming persistence
- official risk: no stale-read token from the CLI: freshness is caller-managed
- official risk: reopen timing needs the same project-load poll as W01
- A actions: `zhigou sch save`; `zhigou pcb save`; `zhigou doc reload`; `zhigou doc ready`; `fresh dump readback`
- A observation: A defines six-state evidence (command_completed / readback_verified / save_confirmed / reopen_confirmed / electrical_passed / quality_passed) and claims save/reopen PASS on its own board.
- A observation: A documents saved:true != persisted explicitly; the official route needs the same discipline encoded by us.
- A blocker: not run by this spike
- A blocker: no independent receipt
- notes: Authorized write probe passed: save -> close --destroy -> reopen -> readback on a disposable copy; source fixture untouched.

Evidence: `docs/evidence/a2-coverage-2026-10-28/write-probe/raw/W04e-save-readback.stdout.json`, `docs/evidence/a2-coverage-2026-10-28/write-probe/raw/W09-close.stdout.json`, `docs/evidence/a2-coverage-2026-10-28/write-probe/raw/W09-reopen.stdout.json`, `docs/evidence/a2-coverage-2026-10-28/write-probe/raw/W09-readback.stdout.json`, `docs/evidence/a2-coverage-2026-10-28/write-probe/project-before.json`, `docs/evidence/a2-coverage-2026-10-28/write-probe/project-after.json`, `docs/evidence/a2-coverage-2026-10-28/write-probe/write-probe-run.json`, `docs/evidence/a2-coverage-2026-10-28/write-probe-passed.json`

### W10 - error / permission / boundary (non-critical)

- official: **covered** (measured steps=7, js_lines=6, exit=[0, 1, 3], scope=real-run)
- A: **static** (scope=static)
- verdict: `official_sufficient`
- official commands: `invoke --session <unknown>`; `invoke --args '[1,2]'`; `doc api --class-name <unknown>`; `invoke -> throw`; `invoke --timeout 3000 -> never-resolving promise`; `invoke -> eda.sys_FileSystem.getProjectsPaths (permission gate)`; `invoke -> activateDocument(<wrong id>)`
- official observation: Stable envelope {ok:false,error:{code,message}} plus a mirrored stderr line; codes observed: SESSION_NOT_FOUND (exit 3), INVALID_ARGS (1), DOC_QUERY_FAILED (1), EXECUTION_ERROR (1), REQUEST_TIMEOUT (3).
- official observation: REQUEST_TIMEOUT message explicitly says the code may still be running in the render and its result will be discarded - callers must read back, never blind-retry.
- official observation: Permission gate observed: eda.sys_FileSystem.* throws '未启用扩展和独立脚本的外部交互权限！' for independent-script invokes; this blocks direct file writes/reads outside the editor.
- official observation: activateDocument(<bogus id>) returns false instead of throwing, so confusing 'silent false' with 'success' is possible.
- official risk: exit code alone is not enough; error.code must be parsed
- official risk: silent-boolean APIs (activateDocument/waitForDocumentReady) need explicit checks
- official risk: timeout leaves unknown side effects
- A actions: `typed preconditions/refusals`; `stable error codes NO_CONNECTOR / STALE_WINDOW / AMBIGUOUS_* / PRECONDITION_REFUSED / ACTION_ABANDONED / REQUEST_TIMEOUT-equivalent`
- A observation: A protocol defines stable error classes and states that ACTION_ABANDONED may still land later, which is the same hazard the official REQUEST_TIMEOUT has.
- A observation: Not run by this spike.
- A blocker: not run by this spike
- notes: Error envelope is good enough to build a typed gate on top; the caller must map codes, not exit codes.

Evidence: `docs/evidence/a2-coverage-2026-10-28/raw/W10-bad-session.stdout.json`, `docs/evidence/a2-coverage-2026-10-28/raw/W10-bad-args.stdout.json`, `docs/evidence/a2-coverage-2026-10-28/raw/W10-bad-doc-api.stdout.json`, `docs/evidence/a2-coverage-2026-10-28/raw/W10-thrown.stdout.json`, `docs/evidence/a2-coverage-2026-10-28/raw/W10-permission.stdout.json`, `docs/evidence/a2-coverage-2026-10-28/raw/W10-timeout.stdout.json`, `docs/evidence/a2-coverage-2026-10-28/raw/W10-wrong-document.stdout.json`

### W11 - MCP entry (critical)

- official: **covered** (measured steps=4, js_lines=0, exit=[], scope=real-run)
- A: **unsupported** (scope=static)
- verdict: `official_sufficient`
- official commands: `lceda-pro --mcp stdio`; `initialize (protocol 2025-06-18)`; `notifications/initialized`; `tools/list`; `tools/call lceda-pro.help`
- official observation: The official MCP server works over stdio with newline-delimited JSON-RPC 2.0; initialize returned protocolVersion 2025-06-18, serverInfo JLCEDA Pro 4.1.78.34f5b8d9, capabilities {tools:{}}.
- official observation: tools/list exposes exactly 3 meta-tools: lceda-pro.help, lceda-pro.discover, lceda-pro.call (a proxy over the CLI command surface).
- official observation: tools/call lceda-pro.help returned the same command tree as the CLI; no parameterless read tool exists other than help, so a real read call needs discover -> call with arguments.
- official observation: HTTP transport (--mcp http --port 3030 --token ...) was not exercised in this run.
- official risk: 3 generic meta-tools mean the model must discover command paths itself
- official risk: no typed MCP tools per action, no schemas per EDA operation
- official risk: MCP calls still need a session/project context; concurrency/auth for HTTP mode is untested here
- A observation: A ships a CLI + daemon + WebSocket connector; it does not expose an MCP server, so B1 cannot use A as an MCP backend without writing a gateway.
- A observation: The repository already has an unrelated offline-audit MCP server (docs/zhigou-mcp) that never touches EDA.
- A blocker: no MCP implementation in A
- notes: For B1 Phase 2, the official MCP server is the only existing MCP entry; its three meta-tools are thin but real.

Evidence: `docs/evidence/a2-coverage-2026-10-28/mcp-tools.json`, `docs/evidence/a2-coverage-2026-10-28/raw/mcp-transcript.jsonl`, `docs/evidence/a2-coverage-2026-10-28/probe-run.json`

## Rubric

- decision: **incomplete** (provisional: missing evidence)
- provisional lean: **A2** (confidence: low)
- covered critical: W04, W05, W08, W09, W11
- partial critical: W02, W06, W07
- blocked critical: -
- unresolved: -

A2 conditions:
- official_covered_at_least_7_of_8: False
- w11_mcp_usable: True
- remaining_gaps_thin_wrapper_le_2: False
- a_retirement_does_not_break_b1_or_skill: unknown (not measured)

Missing evidence:
- W02: official status is 'partial' - the remaining gap must be closed (or accepted) by the thin wrapper
- W06: official status is 'partial' - the remaining gap must be closed (or accepted) by the thin wrapper
- W07: official status is 'partial' - the remaining gap must be closed (or accepted) by the thin wrapper
