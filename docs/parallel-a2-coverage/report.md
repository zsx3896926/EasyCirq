# Execution report (A2-COVERAGE)

## 1. What was actually executed

All commands were run on 2026-10-28 from the `spike/a2-eda-coverage` worktree.
Every receipt is under `docs/evidence/a2-coverage-2026-10-28/`.

| step | command family | result |
| --- | --- | --- |
| env | `--help`, `doc api` (class list + 20 classes + 31 method details) | exit 0, no session needed |
| W01 | `doctor`, `session list`, `open --path <temp copy> --headless`, `session list`, `session close --destroy` | exit 0; 1 user session untouched; CLI sessions closed |
| W02 | `invoke` -> activate page, project tree, components/pins/wires/nets/netlist | 58 components, 34 wires, pins OK; nets `[]`; netlist 38,568 B |
| W03 | `invoke` -> activate PCB, pcb info/layers/nets/components | 289 layer entries (2 copper), 17 nets, 33 components |
| W06 | 10 x `invoke` vs 1 batched `invoke`; `--timeout 3000` overflow | 10,082.7 ms vs 995.6 ms; `REQUEST_TIMEOUT` |
| W07 | `invoke` -> `sch_Drc.check`, `pcb_Drc.check`, realtime status | structured warning array (sch), error-group tree (pcb) |
| W08 | `invoke` -> netlist/BOM/PNG/Gerber/CPL | netlist 38,568 B, BOM 1,957 B, PNG 712,074 B, Gerber zip 1,292,203 B, CPL 8,433 B |
| W09 | `session close --destroy` + `open` + poll + re-read; project tree hash | same project/board/page/pcb uuid; fixture unchanged |
| W04/W05/W09 | **authorized write probe** (disposable `%TEMP%` copy): device/wire/net label/net flag + save + readback; importChanges + move + save; close/reopen readback | W04/W05/W09 **PASS**; marker `write-probe-passed.json`; source fixture sha256 unchanged |
| W10 | bad session, bad args, unknown class, thrown error, permission gate, timeout, wrong document | `SESSION_NOT_FOUND`(3), `INVALID_ARGS`(1), `DOC_QUERY_FAILED`(1), `EXECUTION_ERROR`(1), `REQUEST_TIMEOUT`(3), `activateDocument` -> false |
| W11 | `lceda-pro --mcp stdio` + initialize/tools list/tools call | protocol 2025-06-18, 3 tools, help call OK |
| extra | `functions --session` in a bare headless editor | 0 extensions visible |

## 2. Failures, false starts and fixes (kept, not hidden)

1. **Attempt 1 raced the project load.** `open` returned a session before the
   project was loaded; W02 and W08 ran too early: `getCurrentProjectInfo()` was
   empty, so 58 components looked like 0 and every export returned
   `File=undefined` with no error (about 186 s of hung invokes). Raw attempt kept
   in `attempt1/`.
   Fix: poll `getCurrentProjectInfo()` until boards appear (retry run in
   `probe-run.json`); do not trust `getReadyState()`.
2. **Schematic DRC failed with `doctype(3) not support check sch drc`** because
   the active document was the PCB. Fix: activate the schematic page before the
   schematic DRC probe.
3. **`sch_Net.*` returned `[]`** on a loaded project. Kept as a finding; the
   probe was re-run to confirm it is not a readiness artifact
   (`raw/W02-nets-retry.stdout.json`). Net truth comes from the netlist.
4. **File export could not use `sys_FileSystem`** (permission gate). Fix: read
   the `File` in JS, base64 it through the invoke result, decode and hash in
   Python. This is a documented workaround, not a supported contract.
5. **A throw-away project landed in the user's APP_PROJECT_DIR** when testing
   `eda.dmt_Project.createProject` (before switching to the temp fixture copy).
   It was created by us, named `a2spike 20261028`, and removed in the same
   session; the projects directory is empty again. Recorded in
   `attempt1/W04-project-create.json` and in `environment.md` §6.
6. **A second CLI (`lceda-pro.exe` lowercase install)** is byte-identical to the
   `LCEDA-Pro` one (sha256 match), so the adapter's path candidates are safe.
7. **The first write probe attempt timed out** after 240 s in one long JS
   program (create -> pins -> wire -> label -> flag -> save). The result was
   discarded but the step had already changed the copy. Fixed by splitting W04
   into five short invokes so a hang cannot hide earlier checks; attempt kept in
   `write-probe/attempt1/`.
8. **The second attempt failed only the net-label check**: `createNetLabel`
   returned `null` while the attribute was actually persisted. Fixed by trusting
   `sch_PrimitiveAttribute.getAll` readback instead of the create return;
   attempt kept in `write-probe/attempt2/`.
9. **Identity-based device create hangs**: creating from an existing
   component/symbol identity timed out >90 s three times; only the
   `lib_Device.search` item path works (diagnostics in the probe notes). A pin
   lookup on a freshly created async component also blocked one 240 s invoke, so
   the probe uses a standalone wire segment at fixed coordinates.

After the read-only probe the fixture hash was identical before/after
(`project-before.json` vs `project-after.json`). The later authorized write probe
changed only the `%TEMP%` copy (`824f6dcc...` -> `4be11c20...`) and left the
source fixture byte-identical.

## 3. Real vs static boundary

| evidence type | workflows |
| --- | --- |
| real official-CLI run (receipts) | W01, W02, W03, W04, W05, W06, W07, W08, W09, W10, W11 |
| official static catalog only (`doc api` receipts) | none - W04/W05 moved to real after the authorized probe |
| A static only | all W cells (`static`); A's own claims copied under `a-self-evidence/` |
| nothing | no A command was run by this spike |

## 4. NOT RUN / BLOCKED

- **AUTHORIZED and PASSED** (2026-10-28): W04 schematic write, W05 PCB write,
  W09 save/reopen, on a disposable `%TEMP%` copy with an explicit authorization
  file. Receipts and the `write-probe-passed.json` marker are under
  `docs/evidence/a2-coverage-2026-10-28/write-probe/`; the source fixture stayed
  byte-identical and the user session was never touched.
- **NOT RUN**: W06 write batching; `--mcp http` transport; `doc external` /
  `doc format`; library, 3D, panel, simulation surfaces; PCB geometry/outline
  dumps; multi-page or multi-board designs; A branch build/run; any network.
- **BLOCKED by this host**: A build (`go` not installed and installing it is
  forbidden by the task book); A execution (its connector only exists in the
  user's GUI window, which this spike must not drive).

## 5. Conclusion reference

The computed matrix is `docs/parallel-a2-coverage/coverage-matrix.md`; the rubric
is `rubric.json`; the decision memo is `decision.md`. The rubric returns
`incomplete` (provisional) with a **lean toward A2**: W04/W05/W09 are now
`covered` with save/reopen/readback evidence, and the only remaining critical
gaps are wrapper work (W02 net parsing, W06 batch plan, W07 DRC/DFM shaping).

## 6. Reproducibility and verification

- Offline: `python spike/a2-coverage/run_spike.py --offline` (no EDA/network).
- Static catalog: `python spike/a2-coverage/capture_api_catalog.py`.
- Read-only live probe: `python spike/a2-coverage/probe_official.py --fixture <temp copy>.eprj2`.
- New offline package: `python -m unittest discover -s tests/a2_coverage_spike_tests -t tests` -> **78 tests OK (1 skipped)**.
- Full repository suite: `python -m unittest discover -s tests` -> **3311 tests, OK (2 skipped)**.
  One earlier run hit a Windows temp-directory lock in
  `tests/test_skill_update.py` (PermissionError on rename); the test passes in
  isolation on both this branch and `main`, so it is an environment flake, not a
  regression of this spike.
- `python design-hardware/scripts/skill_selftest.py` -> **5 PASS, 0 FAIL**.
- Scope check: every new file is under `spike/a2-coverage/`,
  `tests/a2_coverage_spike_tests/`, `docs/parallel-a2-coverage/` or
  `docs/evidence/a2-coverage-2026-10-28/`; no existing file was modified.

