## What

Retirement PR for the A (self-built) execution layer, per the A2 coverage
decision and the authorized write probe. **Draft: migration is complete and CI
is green; remaining items are prose/rename cleanups, not CI blockers.**

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

- **Skill-only release pipeline**: `distribution/build_release.py` rewritten
  (no Go/Node/npm/connector/toolchain bundle); workflow no longer sets up Node
  or runs `npm ci --prefix connector`. Emits `easycirq-<v>.zip`, `release.json`,
  `Manage-Skill.*`, updater scripts, flat installer and `SHA256SUMS`.
- **A installer removed**: `zhigou_install.py`, `Install-Zhigou.*`,
  `rebrand_*.py`, `verify_vendor.py`, `toolchain.json`; `INSTALL.md` rewritten
  for a Skill-only install.
- **`easycirq/` restored to the pre-A official-CLI baseline**: 69 files restored
  from `fd4499c` (`design-hardware/`), A-only `scripts/zhigou_cli.py` /
  `scripts/layout_from_zhigou.py` deleted, `layout_from_easyeda.py` /
  `layout_from_snapshot.py` restored; skill identity unified to `easycirq`
  (SKILL frontmatter, `.easycirq-state`, install docs).

## Round 2 - tests/tools on the official adapter (`e2213ba`)

- Restored 24 A-migrated test/tool files from the pre-A tree, repo paths
  rewritten to `easycirq/`; deleted 20 A-only test/tool artifacts (zhigou CLI
  test, legacy-ref guard, installer-lifecycle test, 8 `tools/zhigou_*`
  acceptance scripts, zhigou fixtures); restored pre-A feedback fixtures.
- Aligned the skill-knowledge-audit catalog and 9 fixture line anchors.
- `validate` green on the pre-merge head (3.10 + 3.13).

## Round 3 - rebased onto latest main and both workflows green (`f77b98b`)

- `main` advanced during this work (`#74`, `#98`, `#99`, launcher rebase...).
  The branch was **rebased by merging `main @ f9aa773` into it** (a plain
  rebase of a 1,200-file retirement over 570 changed files was not tractable;
  the merge result is equivalent for the PR: branch now contains `main` HEAD
  and the PR is conflict-free).
- 442 conflicts resolved: 440 retirement-side deletions (main-modified
  `runtime/**`, `connector/**`, `protocol/**`, plus A tools renamed to
  `easycirq_*` by the branding pass) and 2 files kept from this branch.
  Retired directories remain empty after the merge.
- Local run on the merge commit: `python -m unittest discover -s tests` ->
  **3373 tests OK (2 skipped)**; `easycirq/scripts/skill_selftest.py` ->
  **5 PASS**.
- CI on `f77b98b`:
  - `Validate skill`: **pass** (3.10 + 3.13)
  - `Skill updater packages`: **pass** (updater ubuntu 22s + windows 1m11s)
  - PR state: **MERGEABLE / CLEAN**, draft.

## Remaining (non-blocking cleanups, round 4)

| area | state |
| --- | --- |
| `docs/**` historical prose | 303 files still mention the retired layer (history kept; no broken links - selftest markdown-links PASS) |
| `benchmarks/**` prose | 39 files mention `zhigou` |
| `easycirq/scripts/zhigou_mcp/**` | 5 files kept (offline audit MCP, unrelated to retired runtime) |
| offline-audit schemas | `zhigou.electrical-review.input/v1` etc. (separate schema-compat PR) |

`grep -r zhigou` outside those exceptions is 0 (`tools/`, `distribution/` clean;
`tests/` only the offline-audit MCP tests).

## Acceptance

- [x] `validate` (3.10/3.13) green on latest `main` merge
- [x] `Skill updater packages` green (ubuntu + windows)
- [x] full unit test suite green locally (3373 tests)
- [x] `distribution/` installs only the Skill; no runtime/connector
- [x] `easycirq/` execution docs/scripts use the official CLI, not `zhigou`
- [x] branch rebased onto latest `main`, PR `MERGEABLE / CLEAN`
- [ ] round-4 prose cleanup / offline-audit MCP rename (optional, separate PRs)

## Do not

- do not merge while draft;
- do not delete `docs/evidence/**`;
- do not touch the user's installed skills/connector from this PR.
