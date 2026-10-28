## What

Retirement PR for the A (self-built) execution layer, per the A2 coverage
decision and the authorized write probe. **Draft: migration and cleanup are
complete; `validate` and `Skill updater packages` are green on the latest `main`
sync.**

Deletes the A toolchain and restores the Skill/docs/installer to the pre-A
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

## Round 1 - updater CI + distribution + easycirq baseline (`e27e72a`)

- Skill-only release pipeline (`distribution/build_release.py`, no Go/Node/npm/
  connector); workflow drops Node setup and `npm ci --prefix connector`.
- A installer removed (`zhigou_install.py`, `Install-Zhigou.*`, `rebrand_*`,
  `verify_vendor.py`, `toolchain.json`); `INSTALL.md` rewritten.
- `easycirq/` restored to the pre-A official-CLI baseline (69 files), A-only
  executor modules removed, skill identity unified to `easycirq`.

## Round 2 - tests/tools on the official adapter (`e2213ba`)

- 24 A-migrated test/tool files restored from the pre-A tree, paths rewritten to
  `easycirq/`; 20 A-only test/tool artifacts deleted; pre-A feedback fixtures
  restored; skill-knowledge-audit catalog/fixtures aligned.
- `validate` green.

## Round 3 - synced with `main` (`f77b98b`)

- `main` advanced; the branch was synced by merging `main @ f9aa773` (1,200-file
  retirement over 570 changed files was not tractable as a plain rebase; result
  is equivalent for the PR). 442 conflicts resolved (440 retirement-side
  deletions, 2 ours); retired dirs remain empty.
- Local: 3373 tests OK, `skill_selftest.py` 5 PASS.

## Round 4 - naming + historical docs cleanup (`5d04ad3`, `a4e0b31`, `33ed3cd`)

- **task-launcher / offline-MCP naming unified to EasyCirq** across code, tests,
  docs and benchmarks: `zhigou.task-launcher.*` -> `easycirq.task-launcher.*`,
  `zhigou-launcher` -> `easycirq-launcher`, `zhigou-design-hardware` ->
  `easycirq-design-hardware`, `zhigou-offline-audit` ->
  `easycirq-offline-audit`, `zhigou_mcp` -> `easycirq_mcp`.
  task-launcher tests 98 OK; MCP tests 22 OK; benchmark 12/12 PASS.
- **`benchmarks/` `zhigou` references are now 0.**
- **`docs/` keeps only provenance notes** (see below); current-facing docs use
  EasyCirq/official-CLI wording.
- Synced with `main @ 7fd9e57` again (includes #100/#101/#102); retired dirs stay
  empty.

## Final CI (head `33ed3cd`, on `main @ 7fd9e57`)

| workflow | result |
| --- | --- |
| `Validate skill` | **pass** - 3.10 (3m48s / 3m49s), 3.13 (3m17s / 3m30s), push + pull_request |
| `Skill updater packages` | **pass** - ubuntu 23s, windows 1m27s |
| `publish` | skipping (release-only) |

Local on the same head: updater tests OK, task-launcher 98 OK, MCP 22 OK,
knowledge-audit 53 OK, `skill_selftest.py` 5 PASS (earlier full suite 3373 OK).

## Remaining `zhigou` mentions - provenance only

`grep -r zhigou` now only matches intentionally historical documents:

- `docs/migration-easycirq.md` - the old->new name map, now preceded by a
  "历史说明" banner: the `zhigou` runtime/connector is retired, the table is for
  identifying old installs only.
- `docs/parallel-task-launcher/integration-proposal.md` - B1 integration
  proposal written before the retirement; banner added that A/`zhigou` is
  retired and the comparisons are provenance.
- `docs/parallel-placement-intent/*` - describe the #99 rename mapping
  `zhigou.*` -> `easycirq.*` (provenance of that port).

Everything executable (`tools/`, `distribution/`, `task_launcher/`, `benchmarks/`)
is clean; `runtime/`, `connector/`, `protocol/`, `third_party/` are deleted.

## Acceptance

- [x] `validate` (3.10/3.13) green on latest `main` merge
- [x] `Skill updater packages` green (ubuntu + windows)
- [x] branch contains latest `main`, PR mergeable
- [x] `distribution/` installs only the Skill; no runtime/connector
- [x] `easycirq/` execution docs/scripts use the official CLI
- [x] task-launcher/MCP naming unified to EasyCirq; benchmarks clean
- [x] remaining `zhigou` text limited to provenance-bannered historical docs

## Do not

- do not merge while draft;
- do not delete `docs/evidence/**`;
- do not touch the user's installed skills/connector from this PR.
