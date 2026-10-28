# Methodology (A2-COVERAGE)

## 1. Question

Can the **official EasyEDA Pro CLI/MCP** (`lceda-pro`, v4.1.78) cover our core
EDA workflows, and which capabilities of **A** (the self-built
`runtime/`+`connector/`+`protocol/` toolchain with 181 typed actions) remain
irreplaceable? The answer feeds A1 (keep full A) / A2 (thin A) / A3 (drop A)
and the split of PR #36 and the B1 Phase 2 execution backend.

## 2. Workflow set

Eleven workflows, W01-W11, exactly as defined in the task book section 5 and
encoded in `spike/a2-coverage/workflows.py`. The decisive set (task book
section 8) is W02, W04, W05, W06, W07, W08, W09, W11.

For every workflow both routes are assessed independently:

| route | how it is assessed |
| --- | --- |
| official CLI/MCP | real run when safe and authorized; otherwise static API catalog (`doc api`) is cited and the cell is `blocked`/`not_run` |
| A typed action | static only in this spike: A's action catalog + A's own self-evidence; **never** upgraded to `covered` by A's documentation |

Status vocabulary: `covered`, `partial`, `unsupported`, `blocked`, `not_run`
plus `static` for A (mapped catalog knowledge with no independent run).
Verdict per workflow: `official_sufficient`, `a_required`, `both_needed`,
`unclear`.

## 3. Isolation rules actually applied

1. Every live probe used a **copy** of an EDA-shipped sample project under
   `%TEMP%\a2-spike-20261028-1050\`; the source sample was only read.
2. Only `origin:"cli"` sessions opened by this spike were driven; the single
   `origin:"user"` window was recorded before/after and never activated,
   reloaded or closed.
3. The first phase was read-only: design-content writes were not authorized, so
   they were not attempted and the affected cells stayed `blocked`.
   **Later (same day) the operator explicitly authorized W04/W05/W09**; the
   authorized probe (`probe_writes.py`) enforced the authorization file, wrote
   only a disposable `%TEMP%` copy, ran one short invoke per write step, and
   required readback + a `write-probe-passed.json` marker.
4. No extension install/uninstall, no network, no A branch checkout/modification,
   no merge/release, no writes outside the four allowed paths.
5. Session hygiene: `session close --session <id> --destroy` after every probe;
   the final `session list` shows the user session still alive and all CLI
   sessions closed.

## 4. Evidence schema

`docs/evidence/a2-coverage-2026-10-28/`:

| artifact | content |
| --- | --- |
| `raw/<probe>.stdout.json` / `.stderr.txt` | unedited CLI receipts |
| `api/` | offline `doc api` catalog receipts + `index.json` (methods, params, exit codes) |
| `probe-run.json` | machine-readable run summary (steps, argv, exit codes, durations) |
| `W01-official.json` .. `W11-a.json` | per-workflow cells generated from `assessments.json` + measurements |
| `mcp-tools.json` | MCP `tools/list` result and the one `tools/call` |
| `project-before.json` / `project-after.json` | project tree hashes (prove no mutation) |
| `sessions-before.json` / `sessions-after.json` | prove the user window was untouched |
| `extensions-headless.json` | extensions visible to a CLI-opened session |
| `a-self-evidence/` | copies of A's own claims + `SHA256SUMS.txt` (clearly labelled as A's, not ours) |
| `attempt1/` | first probe attempt that raced project loading, kept per "do not overwrite failures" |

`spike/a2-coverage/assessments.json` is the single human-judgement source; the
matrix generator validates that every evidence path it cites exists on disk.

## 5. Measurement rules

- **steps**: number of distinct CLI invocations recorded for the workflow.
- **js_lines**: non-empty lines of the JS snippet actually sent to `invoke`
  (computed from the recorded argv, not hand-counted).
- **round-trip cost**: 10 separate `invoke` calls vs one batched script.
- **readiness**: `open` returns before the project is loaded; the probe polls
  `getCurrentProjectInfo()` instead of trusting `getReadyState()`.

## 6. Rubric (written before the results)

Computed by `spike/a2-coverage/build_matrix.py::evaluate_rubric`:

- **A2** (thin A, official CLI as backend): official `covered` in >=7/8 critical
  workflows with save/reopen/readback evidence, W11 usable, remaining gaps
  thin-wrapable (<=2 workflows), retirement of A's connector/daemon/fork does
  not break B1 or the existing Skill entry points.
- **A1** (keep full A): official `unsupported`/`partial` in >=2/8 critical and
  not thin-wrapable, or W11 unusable/unstable, or critical writes need
  unacceptable hand-written JS/permission risk while A typed actions are clearly
  better.
- **A3** (drop A): official covered in >=7/8 critical and W11 usable, and A's
  typed benefit is negligible while its maintenance cost is high (keep at most
  `distribution/`).
- If any critical cell is `blocked`/`not_run`, the rubric returns
  `decision: incomplete` (no final A1/A2/A3), plus a provisional lean and the
  exact missing evidence.

## 7. Known limits of this spike

- Writes: W04/W05/W09 are no longer unproven - the authorized probe on a
  disposable copy turned them to `covered` (save/reopen/readback receipts). A
  cannot be run on this host (no Go; connector only in the user's window), so the
  A column stays static and the decision is **provisional** because W02/W06/W07
  are wrapper scope, not measured host gaps.
- Only one fixture (a vendor sample). Complex designs (multi-page, multi-board,
  high-speed) were not exercised.
- The A side is static knowledge; A's later self-claimed M2-M4 PASS was not
  re-run or verified.
- HTTP MCP transport, `doc external`/`doc format`, library/3D/panel surfaces,
  and PCB geometry dumps were not probed.
