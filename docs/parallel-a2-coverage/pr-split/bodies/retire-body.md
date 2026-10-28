## What

Retirement PR for the A (self-built) execution layer, per the A2 coverage
decision and the authorized write probe. **Draft: deletion + round-1/round-2
migration are staged; only historical docs links remain (outside the `validate`
workflow).**

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
  (no Go/Node/npm/connector/toolchain bundle); the workflow no longer sets up
  Node or runs `npm ci --prefix connector`. Emits `easycirq-<v>.zip`,
  `release.json`, `Manage-Skill.*`, updater scripts, flat installer bundle and
  `SHA256SUMS`.
- **A installer removed**: `zhigou_install.py`, `Install-Zhigou.*`,
  `rebrand_*.py`, `verify_vendor.py`, `toolchain.json`; `INSTALL.md` rewritten
  for a Skill-only install.
- **`easycirq/` restored to the pre-A official-CLI baseline**: 69 files restored
  from `fd4499c` (`design-hardware/`), A-only `scripts/zhigou_cli.py` /
  `scripts/layout_from_zhigou.py` deleted, `layout_from_easyeda.py` /
  `layout_from_snapshot.py` restored.
- **Skill identity unified to `easycirq`**: `SKILL.md` frontmatter, installer
  target/state dir (`.easycirq-state`), updater tests and install docs.
- `Skill updater packages` was **green on `e27e72a`** (ubuntu + windows: 55
  updater tests, ecosystem smoke, skill-only build, isolated-home install/
  upgrade/rollback smoke).

## Round 2 - tests/tools on the official adapter (`e2213ba`)

- Restored 24 A-migrated test/tool files from the pre-A tree (official
  `eda_exec.py` / `layout_from_easyeda.py` / `layout_from_snapshot.py` paths),
  and rewrote their repo paths to `easycirq/`.
- Deleted A-only test/tool artifacts (20 paths): `test_zhigou_cli.py`,
  `test_install_lifecycle.py`, `test_no_legacy_toolchain_refs.py`,
  `tools/toolchain_refs.py`, the eight `tools/zhigou_*.py` acceptance scripts,
  and the `tests/fixtures/zhigou/` + `fake_zhigou*` fixtures.
- Restored pre-A feedback fixtures (`fake_easyeda.py`, `easyeda-fake.*`) and
  fixed `tools/skill-feedback/apply-feedback.py` repo paths.
- Aligned the skill-knowledge-audit package/fixtures to the restored docs
  (catalog + 9 fixture line anchors).
- **`validate` is GREEN on `e2213ba`** (ubuntu, Python 3.10 + 3.13).

## Why the updater workflow has no run on `e2213ba`

The PR is currently `CONFLICTING` against `main` (main moved while this work was
in progress). GitHub cannot create the pull-request merge ref, so the
`pull_request`-triggered `Skill updater packages` workflow is skipped; its
`push` trigger only lists `main` / `feat/skill-updater`, not this branch.
Locally on `e2213ba`: 55 updater tests OK, ecosystem smoke OK, skill-only
installer build + isolated-home release smoke OK. **Rebase onto `main` before
ready-for-review**, then both workflows run again.

## Remaining before ready-for-review (round 3)

| area | state | follow-up |
| --- | --- | --- |
| branch freshness | GitHub reports `CONFLICTING` vs `main` | rebase and re-run both workflows |
| `docs/**` historical links | still point at deleted `runtime/`, `connector/`, `protocol/` paths | keep history, fix/retire links; the markdown-link check is **not** part of `validate` |
| `easycirq/scripts/zhigou_mcp/**` | 5 files kept (offline audit MCP, unrelated to retired runtime) | rename/module move or explicit keep note |
| offline-audit schemas | `zhigou.electrical-review.input/v1` etc. | rename in a separate schema-compat PR |
| `benchmarks/**` prose | mentions the retired layer | rewrite or mark historical |

## Acceptance

- [x] `validate` (3.10/3.13) green on `e2213ba`
- [x] updater pipeline green on the round-1 head; local updater suite green on round-2 head
- [x] `distribution/` installs only the Skill; no runtime/connector
- [x] `easycirq/` execution docs/scripts use the official CLI, not `zhigou`
- [x] skill name/state dir unified to `easycirq`
- [ ] rebase onto current `main`, re-run validate + updater
- [ ] docs links to deleted paths cleaned (round 3, not in `validate`)
- [ ] `grep -r zhigou` outside historical evidence / offline-audit MCP is 0

## Do not

- do not merge while draft, and do not delete `docs/evidence/**`;
- do not touch the user's installed skills/connector from this PR.
