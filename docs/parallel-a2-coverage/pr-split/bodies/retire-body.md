## What

Retirement PR for the A (self-built) execution layer, per the A2 coverage
decision and the authorized write probe. **Draft: the deletion + round-1
migration are staged; the remaining references are round-2 work.**

Deletes the A toolchain and replaces the Skill/docs/installer with the pre-A
official-CLI baseline:

- `runtime/**` - Go daemon + 192 CLI entries (fork of easyeda-agent v1.15.0, MIT)
- `connector/**` - TypeScript `.eext` connector
- `protocol/**` - WebSocket contract + JSON schemas
- `third_party/easyeda-agent/**` - vendored upstream

The official `lceda-pro` CLI/MCP now covers the measured workflows, including
the authorized write probe (W04/W05/W09 `covered`,
`docs/evidence/a2-coverage-2026-10-28/write-probe-passed.json`), and the official
API additionally exposes Gerber/CPL exports that A never had.

## Gate (satisfied)

- authorization: `docs/evidence/a2-coverage-2026-10-28/write-probe/authorization.json`
- marker: `docs/evidence/a2-coverage-2026-10-28/write-probe-passed.json`
  (W04/W05/W09 all checks true; source fixture unchanged)

## Round-1 migration in this PR (2026-10-28)

**Updater CI is green** (`Skill updater packages`, ubuntu + windows: 55 updater
tests, ecosystem smoke, skill-only installer build, isolated-home smoke).

1. **Skill-only release pipeline** - `distribution/build_release.py` rewritten:
   no Go, Node, npm, connector or toolchain bundle. It emits
   `easycirq-<version>.zip`, `release.json`, `Manage-Skill.*`, the updater
   scripts, a flat `easycirq-installer-<version>.zip` and `SHA256SUMS`.
   `.github/workflows/skill-updater.yml` no longer sets up Node or runs
   `npm ci --prefix connector`.
2. **A installer removed** - `zhigou_install.py`, `Install-Zhigou.*`,
   `rebrand_runtime.py`, `rebrand_connector.py`, `verify_vendor.py`,
   `toolchain.json` deleted; `INSTALL.md` rewritten for a Skill-only install
   (no daemon/port/EDA extension).
3. **`easycirq/` restored to the pre-A official-CLI baseline** - 69 files that
   the A migration had rewritten to `zhigou` were restored from the pre-A tree
   (commit `fd4499c`, `design-hardware/`); A-only modules
   `scripts/zhigou_cli.py` and `scripts/layout_from_zhigou.py` deleted and the
   pre-A `layout_from_easyeda.py` / `layout_from_snapshot.py` restored. This
   reverts `SKILL.md`, `references/eda-execution.md`, gates, PCB docs and the
   gate scripts to official-CLI wording.
4. **Residual `zhigou` references** (intentionally kept for round 2):
   `easycirq/scripts/zhigou_mcp/**` (offline-audit MCP, unrelated to the retired
   runtime; rename tracked separately) and offline-audit schema strings such as
   `zhigou.electrical-review.input/v1`.

## Why this is still a draft and `validate` is red

Round 2 must migrate the remaining repository references; measured after
round 1:

| area | state after round 1 | required follow-up |
| --- | --- | --- |
| `easycirq/scripts/zhigou_mcp/**` | 5 files kept (offline audit MCP) | rename/module move or explicit keep note |
| `tests/**` | A-era tests still pass `--zhigou` / import `zhigou_cli` (e.g. `test_pcb_apply_plan`, `test_skill_update` fixtures) | restore/adapt tests to the official-CLI scripts |
| `tools/**` | acceptance/board scripts still shell out to `zhigou` | point at the official CLI adapter |
| `docs/**` | historical docs still link `runtime/`, `connector/`, `protocol/` | keep history, fix/retire broken links |
| `benchmarks/**`, `distribution` prose | 39 files mention the retired layer | rewrite or mark historical |

Exact `validate` failure on this head: A-era unit tests invoke the restored
scripts with `--zhigou ...` (argparse: "unrecognized arguments: --zhigou"),
plus tests importing removed modules. That is round-2 scope, not a regression of
the updater migration.

## Acceptance (before ready-for-review)

- [x] updater CI green (skill-only release, no Go/Node/connector build)
- [x] `distribution/` no longer installs runtime/connector; install/upgrade/
      rollback of the Skill unchanged (`tests/test_*update.py` 55 OK;
      release smoke passes on isolation)
- [x] `easycirq/` documents the official CLI/MCP, not the retired `zhigou`
      executor (69 files restored; 2 A-only modules removed)
- [ ] `tests/**` + `tools/**` migrated (round 2)
- [ ] `validate` (3.10/3.13) green, no markdown link points to deleted paths
- [ ] `grep -r zhigou` outside historical evidence and the offline-audit MCP is 0

## Do not

- do not merge while draft/`validate`-red;
- do not delete `docs/evidence/**` (historical evidence is kept);
- do not touch the user's installed skills/connector from this PR.
