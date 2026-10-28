# Skill migration: upstream `easyeda` toolchain → own `easycirq` execution layer

Branch: `feat/integrated-eda-toolchain`
Scope of this change: `easycirq/**`, `tests/**`, `tools/**`, `benchmarks/**`,
`.github/workflows/**` (no command string there needed to change).
Read-only by rule and by practice: `runtime/**`, `connector/**`, `distribution/**`,
`protocol/**`, and docs owned by other agents.

## 1. Result

The skill now has exactly one EDA execution entry point: the repository's own
`easycirq` runtime (installed from `distribution/`). The former upstream
`easyeda` CLI / `easyeda-agent` daemon / `.easyeda-agent` state / `EASYEDA_*`
environment / `easyeda` skill are no longer referenced by any live policy,
script, test or tooling file.

- Old-toolchain references in the scanned tree: **984 before → 69 after, of
  which 0 actionable** (all 69 are allowlisted history/attribution/frozen
  evidence/defensive blocks; see §6).
- `easycirq/SKILL.md`: **323 → 315 lines**, and the top-level doc now
  opens the human-facing flow with a single “执行层入口: easycirq” section.
- Offline suite: **1832 tests, 0 failures, 0 errors, exit 0**.
- Skill self-test: **5 PASS / 0 FAIL / 0 NOT RUN, exit 0**.
- Targeted pytest: **220 passed, 217 subtests passed, exit 0**.

No claim is made about real EDA execution: this machine's `easycirq doctor`
reports `connector.status=disconnected`, so no project was written, saved or
reopened. That is recorded below as **NOT RUN**, not as a pass.

## 2. Old → new mapping

| Old (removed) | New (single entry point) |
|---|---|
| `easyeda <group> <cmd> ...` | `easycirq <group> <cmd> ...` (`sch`, `pcb`, `project`, `doc`, `bom`, `lib`, `actions`, `call`, `apply`, ...) |
| `easyeda health` preflight | `easycirq doctor` + `easycirq capabilities` (JSON on stdout, human summary on stderr) |
| `easyeda-agent` daemon | `easycirq-agent` daemon (`~/.easycirq`, ports 23111-23120) |
| `~/.easyeda-agent`, `~/.easyeda` | `~/.easycirq` (`daemon.log`, `daemon.pid`, audit, workflow) |
| `<project>/.easyeda/artifacts`, `.easyeda/stages` | `<project>/.easycirq/artifacts`, `<project>/.easycirq/stages` |
| `EASYEDA_*` env (`EASYEDA_CLI`, `EASYEDA_NO_AUTOSTART`, ...) | `EASYCIRQ_*` env (`EASYCIRQ_BIN`, `EASYCIRQ_NO_AUTOSTART`, `EASYCIRQ_WORKFLOW_DIR`, ...) |
| `easyeda-agent-connector` extension | `easycirq-connector` (own uuid; imported by the user in EasyEDA Pro) |
| load the upstream `easyeda-agent` skill + `easyeda update` | this skill is the only policy source; runtime installed/upgraded from this repo's `distribution/` bundle; `easycirq doctor` verifies |
| `python scripts/eda_exec.py doctor/read/apply/...` as a second route | not documented as an execution route; all policy points to `easycirq` typed commands |
| Python resolver `EASYEDA_CLI` → `easyeda` | single resolver in `easycirq/scripts/easycirq_cli.py`: explicit arg → `EASYCIRQ_BIN` → `easycirq` (no machine path) |

## 3. What changed, by area

### Skill entry (`easycirq/SKILL.md`)

- New §2 **执行层入口: easycirq** replaces the old “check the easyeda-agent skill /
  run easyeda health / use the official CLI adapter” block:
  preflight (`doctor` → `capabilities`) → target binding (`project info`,
  `doc ls`, explicit `--project`/`--doc`) → write → readback → save → reopen,
  plus the one explicit human step when the connector is not connected
  (`easycirq connector install-steps`). Users no longer need to know about two
  skills, daemon ports or connector internals.
- Removed the statements that require loading the upstream `easyeda-agent`
  skill or installing/upgrading an external CLI/daemon/connector from its
  release page.
- Install/update section reduced and re-pointed: this skill updates itself;
  the runtime is installed/upgraded from this repository's `distribution/`
  bundle and verified by `easycirq doctor`.
- Bulky detail was moved, not deleted: the eight “工程内容库的使用边界” bullets
  (design-card/常用硬件/failure/decision evidence levels, D0–D2 loading,
  “coverage ≠ verification”) now live in
  `references/design-experience.md` under “内容库的使用边界”, linked from §3.1.
  Engineering rules in §4/§5/§6/§7 are unchanged except the two wording fixes
  listed in §4 below.
- Table rows that pointed at `scripts/eda_exec.py` as the read/write route now
  list `easycirq` typed commands; the examples row was removed when the Lead
  moved the upstream example copies out of the skill tree (see §7).

### Scripts (`easycirq/scripts/`)

- **New `easycirq_cli.py`** — the only resolver and the only place that knows the
  CLI JSON contracts:
  - `resolve_bin()`: explicit → `EASYCIRQ_BIN` → `easycirq`;
  - `run()`: subprocess + offline guard + JSON payload, never raises for a
    missing binary/timeout;
  - `parse_doctor()`: normalises `easycirq-doctor/v1`, computes `ready` only when
    verdict/daemon/connector/protocol/checks all agree, keeps `unsupported`
    reasons;
  - `parse_capabilities()`: normalises `easycirq-capabilities/v1`, indexes every
    capability by id with `supported/unsupported/unknown + reason`, exposes
    `capability_state()`;
  - `preflight()`: doctor + capabilities as the skill's single preflight, with
    an explicit `not_proven` list (writability, persistence, electrical/manufacturing).
- `pcb_cli.py`: keeps its provenance/manifest API, but resolves and runs
  through `easycirq_cli` (`EASYCIRQ_BIN`), so every PCB/feedback/evidence tool
  inherits the same binary. `--easyeda` flags became `--easycirq`.
- `doctor_env.py`: rewritten EDA probe — no `eda_exec`/`lceda-pro` route, no
  two-route reporting; it aggregates `easycirq doctor` + `easycirq capabilities`
  (autostart disabled) with the existing client/skill-dir diagnosis, and still
  never claims project writability.
- `companion_update.py`: now a **read-only reporter** (doctor-based). It never
  downloads, replaces, backs up or restarts anything, and says explicitly that
  the runtime is installed from this repository's `distribution/` bundle.
- `skill_update.py`: `update-agent`/menu item 8 is a read-only “检查EDA执行器”
  report; `--easyeda`/`--agent-version` remain only as hidden aliases for the
  `distribution/Manage-Skill.ps1` wrapper (owned by the release pipeline).
- `offline_guard.py`: blocks the current `easycirq`/`easycirq-agent`/`lceda-pro`
  executables and (defensively) the retired `easyeda` binaries; fake CLI still
  requires an explicit marker (`HDS_FAKE_CLI`/`FAKE_EASYCIRQ`/`fake` path part);
  adds a narrowly scoped `HDS_OFFLINE_ALLOW_EASYCIRQ_READONLY=1` opt-in used only
  by the installer self-check (version/doctor/capabilities/help only).
- Mechanical command-string updates in `gate_check.py` (all `next_command`),
  `pcb_gate.py`, `pcb_case.py`, `pcb_apply_plan.py`, `feedback/*`,
  `sch_*`, `design_engine/*`, `component_identity_check.py`, etc.
- `layout_from_easyeda.py` → `layout_from_easycirq.py` (renamed; the frozen
  `coordinate_units` schema string is intentionally unchanged — see §6).

### References / assets

- `references/eda-execution.md`: rewritten from a `lceda-pro` JS-bridge contract
  into the **`easycirq` typed execution contract**; the five capability layers
  now map to `doctor`/`capabilities` fields, the write flow keeps
  read → reconcile → bind page identity → controlled actions → readback →
  save → reopen, and all historical pitfalls (async create, zero-length wires,
  same-net merge, page activation, staleRisk) are preserved.
- `references/client-compatibility.md`: single preflight, `easycirq doctor` /
  `capabilities`, connector import steps, five-step first connection and
  commands all re-pointed to `easycirq`; the old half-offline `lceda-pro` bullet
  and two-route wording removed.
- `references/installation-updates.md`: external-updater section replaced with
  “执行层由本仓库 distribution/ 安装/升级 + `easycirq doctor` 验证”; no
  `easycirq update` dependency (that command is not in the current runtime build,
  see §7).
- `references/sources.md`: upstream toolchain link replaced with this repo's
  `runtime/`, `connector/`, `distribution/` entry points.
- `references/tool-gotchas.md`, `design-gates.md`, `eda-efficiency.md`,
  `schematic-layout.md`, `design-engine.md`, `easyeda-ecosystem.md`,
  `agent-collaboration.md`, `network-discipline.md`, assets docs / checklists:
  command surface, preflight and capability claims re-pointed to `easycirq`;
  version-specific empirical notes are labelled “前代执行器 vX” (historical
  measurement) instead of pretending the current runtime was measured.
- `assets/scenarios.json`: routes that pointed at the removed upstream example
  copies now point at equivalent design cards (`p02-buck`, `p01-ldo`,
  `p12-usbc-sink`).
- `pcb-command-map.json`, `orientation.json`, `sheet-templates.json`,
  `standard-parts.json`: tokens/provenance updated.

### Tests / tools

- New `tests/test_no_legacy_toolchain_refs.py`: grep-style guard over
  `tools/toolchain_refs.py` (categories: CLI, service, state dir, env,
  connector, bare token), allowlist restricted to frozen evidence/attribution/
  defensive files, plus self-tests that the scanner catches each category and
  does not flag EasyEDA product names/format paths.
- New `tests/test_easycirq_cli.py`: resolver precedence (explicit → `EASYCIRQ_BIN`
  → path), `doctor`/`capabilities` schema parsing on **fixtures captured from
  the real runtime** (`tests/fixtures/easycirq/`; the connected/supported variants
  are marked synthetic), malformed/foreign schemas rejected, `unknown` never
  rounded up, preflight composition, `not_proven` never hidden.
- `tests/test_doctor_env.py`: rewritten around the single `easycirq` preflight.
- `tests/test_companion_update.py`: asserts the reporter never mutates and
  names `distribution/`.
- `tests/test_offline_guard.py`, `tests/test_install_lifecycle.py`: fake CLI is
  `easycirq-*`; installer self-check gets the read-only exception.
- Fake CLI fixtures renamed: `fake_easyeda.py → fake_easycirq.py`,
  `easyeda-fake.cmd/.sh → easycirq-fake.cmd/.sh`; `tests/feedback_sim.py`,
  `tests/test_pcb_*.py`, `tests/test_feedback_*.py`,
  `tests/test_sch_layout_pipeline.py`, `tests/test_geometry_primitives.py`
  now fake/parse `easycirq` and use `--easycirq`/`EASYCIRQ_BIN`.
- Frozen real-measurement fixtures (`tests/fixtures/photo-led-v14/`,
  `photo-led-acceptance.json`) were restored byte-for-byte: they carry recorded
  SHA-256 bindings and provenance text that must not be rewritten.
- `tools/offline_suite.py`: inventory flag `references_easycirq_cli`;
  `tools/toolchain_refs.py` is the shared scanner/inventory tool.

## 4. Rule mapping (old rule → new location)

| Old rule / statement | New location |
|---|---|
| “使用 easyeda-agent 时读取其 Skill、运行 `easyeda health`，依 `--help` 发现命令” | `SKILL.md` §2 预检: `easycirq doctor` + `easycirq capabilities` (and `--help` only as command discovery, never as capability proof) |
| “使用官方 CLI 时先 `eda_exec.py doctor`，区分工具存在/连通/工程可读/工程可写” | `SKILL.md` §2 + `references/eda-execution.md` §0: five layers mapped to doctor fields + capabilities; same “do not infer read from connect” rule |
| “不覆盖 easyeda-agent 或其他执行 Skill” | `SKILL.md` §2: this skill is the only policy source; no other execution skill |
| “Gerber/钻孔/CPL 在 easyeda-agent v1.14.0 没有 CLI/typed action” | `SKILL.md` §3.2 工具边界 + `references/design-gates.md`: per-item status from `easycirq capabilities`; unsupported/unknown → user exports in GUI, G6 stays `BLOCKED` |
| “同时覆盖 easyeda-agent 更新（官方 update --check）” | `references/installation-updates.md`: runtime installed/upgraded from this repo's `distribution/`; `skill_update.py update-agent` is a read-only report |
| “eda_exec.py 受控原语/JS 桥执行流程” | `references/eda-execution.md`: same read-first/reconcile/verify/save/reopen discipline over `easycirq` typed commands (`apply --dry-run`, `--journal/--resume`) |
| “工程内容库使用边界” 8 bullets | `references/design-experience.md` “内容库的使用边界”; `SKILL.md` §3.1 keeps the compact rule + link (no rule loss) |
| “多 Agent 单写入者 / 保存后重开才验收” | unchanged in `SKILL.md` §1/§2 and `references/agent-collaboration.md`, now expressed in `easycirq` terms |

## 5. Commands that verify this migration

Run from the repository root (PowerShell 7, Python 3.13). Evidence files are in
`docs/toolchain-integration/evidence/skill-migration/`.

```powershell
# 1. Offline suite (fail-closed guard, real easycirq/network blocked)
python tools/offline_suite.py --out docs/toolchain-integration/evidence/skill-migration/offline-suite.json
# status=pass, tests_run=1832, failures=0, errors=0, exit 0

# 2. Skill package self-test
python easycirq/scripts/skill_selftest.py
# 5 PASS, 0 FAIL, 0 NOT RUN -> exit 0

# 3. Targeted pytest for every touched/added test file
python -m pytest tests/test_no_legacy_toolchain_refs.py tests/test_easycirq_cli.py tests/test_doctor_env.py tests/test_offline_guard.py tests/test_companion_update.py tests/test_install_lifecycle.py tests/test_pcb_case.py tests/test_pcb_preflight.py tests/test_skill.py tests/test_design_content.py tests/test_scenarios.py tests/test_sch_acceptance_v14.py tests/test_skill_update.py -q
# 220 passed, 217 subtests passed, exit 0

# 4. Legacy-reference guard / raw inventory
python tools/toolchain_refs.py --strict
# 0 actionable references, exit 0
python tools/toolchain_refs.py --out docs/toolchain-integration/evidence/skill-migration/inventory-post-migration.txt
# total=69, actionable=0, exempt=69

# 5. Real preflight (read-only, autostart disabled)
$env:EASYCIRQ_NO_AUTOSTART='1'
easycirq doctor            # exit 0, JSON easycirq-doctor/v1 (evidence/easycirq-doctor.stdout.json)
easycirq capabilities      # exit 0, JSON easycirq-capabilities/v1 (evidence/easycirq-capabilities.stdout.json)
```

Recorded evidence:

| File | Meaning |
|---|---|
| `evidence/skill-migration/inventory.txt` | raw pre-migration inventory (984 rows) |
| `evidence/skill-migration/inventory-pre-migration.json` | machine-readable pre-migration inventory |
| `evidence/skill-migration/inventory-post-migration.txt/.json` | post-migration inventory (69 exempt rows) |
| `evidence/skill-migration/offline-suite.log/.json` | full offline suite log + machine summary |
| `evidence/skill-migration/pytest-targeted.log` | targeted pytest log |
| `evidence/skill-migration/skill-selftest.log` | `skill_selftest.py` log |
| `evidence/skill-migration/easycirq-doctor.*`, `easycirq-capabilities.*` | real preflight stdout/stderr/exit |
| `evidence/skill-migration/migrate_toolchain_refs.py` | reproducible mechanical migration script |

## 6. Remaining references, intentionally kept (69 rows, 0 actionable)

| Location | Rows | Reason |
|---|---|---|
| `easycirq/CHANGELOG.md` | 19 | release history: records what the old toolchain did; rewriting it would falsify history |
| `easycirq/cases/**` | 20 | frozen real-run evidence (case READMEs + captured CLI output); not policy |
| `easycirq/scripts/offline_guard.py` | 3 | defensive: the offline guard must still refuse to execute a retired `easyeda` binary |
| `easycirq/scripts/layout_from_easycirq.py` | 1 | frozen schema string `coordinate_units` is bound into recorded fixture SHA-256 values; changing it invalidates stored evidence |
| `tests/fixtures/photo-led-v14/**`, `tests/fixtures/photo-led-acceptance.json` | 20 | frozen real-measurement fixtures with recorded SHA-256 bindings |
| `tests/fixtures/easycirq/doctor-*.json` | 6 | faithful capture of real `easycirq doctor` output; its `legacy` field legitimately names the old daemon it detects and never uses |

There are **no** remaining `easyeda` CLI calls, `EASYEDA_*` env vars,
`.easyeda*` state paths or upstream-skill instructions in live files. The only
other “EasyEDA” strings are product/format names (`EasyEDA Pro`,
`vendor/easyeda-format`, `easyeda-ecosystem.md`, official docs URLs), which the
scanner is written not to flag.

## 7. Notes / blockers for the Lead

1. **Real EDA write path was NOT RUN.** `easycirq doctor` reports
   `daemon.status=running`, `connector.status=disconnected` (no EasyEDA window
   connected to this runtime). Therefore `apply`/save/reopen against a real
   project was not executed, and nothing here claims it works. The `legacy`
   block shows the old `easyeda-agent` daemon on port 60832 is detected but
   `used:false`; it was not started or stopped by this migration.
2. **Runtime binary changed mid-migration** (`0.1.0-dev` → `0.2.0-dev`) while
   another agent owned `runtime/`. The new build no longer exposes
   `easycirq update`, so the migration does not depend on it: the runtime is
   installed from `distribution/`, and the skill's runtime update path is a
   read-only report. The skill tests and parsing helpers are pinned to the
   `easycirq-doctor/v1` / `easycirq-capabilities/v1` contracts, whose fixtures were
   recaptured from the current binary.
3. **`distribution/Manage-Skill.ps1`** (owned by another agent) still passes
   `--easyeda`/`--agent-version`; `skill_update.py` accepts them as hidden
   aliases so the wrapper keeps working. No change to `distribution/` was made.
4. **`easycirq/scripts/eda_exec.py`** is kept as a legacy offline/JS
   reconcile module for its own unit tests, but it is no longer referenced by
   `SKILL.md`, `doctor_env.py` or any execution policy. It uses `lceda-pro`
   (the EDA client CLI), not the old `easyeda` tokens, so it does not appear in
   the legacy inventory. Removing it is a separate cleanup decision.
5. **`easycirq/references/examples/`** was being moved out to
   `runtime/internal/app/testdata/` by the Lead during this migration.
   This change therefore removes the SKILL.md link to it, re-points
   `assets/scenarios.json` routes to equivalent design cards, and marks the
   content test `Examples` as skipped while the directory is absent (reason
   stated in the skip message). No upstream example content was edited.
6. Historical `lceda-pro` mentions remain only in `eda_exec.py`,
   `ecosystem_docs.py` (read-only documentation index) and historical notes in
   `eda-execution.md` §1; they are not old-toolchain references and are not
   used as an execution route.
