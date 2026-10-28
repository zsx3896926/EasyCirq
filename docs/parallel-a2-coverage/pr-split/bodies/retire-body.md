## Summary

Retire the self-built A execution layer (`runtime/` + `connector/` + `protocol/`)
and restore the Skill/installer/docs to the pre-A official-CLI baseline.
The official `lceda-pro` CLI/MCP covers the measured workflows, including the
authorized write probe (W04/W05/W09 `covered`,
`docs/evidence/a2-coverage-2026-10-28/write-probe-passed.json`) and Gerber/CPL
exports that A never had.

## Final changes

- **Deleted**: `runtime/**` (Go daemon + 192 CLI entries), `connector/**`
  (`.eext`), `protocol/**`, `third_party/easyeda-agent/**` - retired directories
  contain **0 tracked files** on this head.
- **Installer/release**: skill-only `distribution/build_release.py`
  (`easycirq-<v>.zip` + `release.json` + `Manage-Skill.*` + flat installer +
  `SHA256SUMS`); no Go/Node/npm or connector build. A-only installer scripts
  (`zhigou_install.py`, `Install-Zhigou.*`, `rebrand_*`, `verify_vendor.py`,
  `toolchain.json`) removed; `INSTALL.md` rewritten.
- **Skill**: `easycirq/` restored to the pre-A official-CLI docs/scripts
  (69 files); A-only executor modules removed; skill identity unified to
  `easycirq` (frontmatter, `.easycirq-state`, install docs).
- **Tests/tools**: A-era tests/tools restored to the pre-A official adapter
  (24 files), A-only test/tool artifacts deleted (20); feedback fixtures,
  knowledge-audit catalog/fixtures aligned.
- **Naming**: task-launcher + offline-MCP naming unified to EasyCirq
  (`easycirq.task-launcher.*`, `easycirq-offline-audit`, `easycirq_mcp`, ...)
  across code, tests, docs and benchmarks; `benchmarks/` has **0** `zhigou`
  references.
- **Provenance kept**: `docs/migration-easycirq.md` and the pre-retirement
  task-launcher proposal carry an explicit "历史说明" banner; their old names
  remain only as historical mapping.

## Verification

CI on head `33ed3cd` (branch synced with `main @ 7fd9e57`):

| workflow | result |
| --- | --- |
| `Validate skill` | **pass** - 3.10 (3m48s/3m49s), 3.13 (3m17s/3m30s), push + pull_request |
| `Skill updater packages` | **pass** - ubuntu 23s, windows 1m27s |
| `publish` | skipping (release-only) |

Local evidence: full suite **3373 OK** (pre-round-4 head; CI re-ran green after),
task-launcher 98 OK, MCP 22 OK, knowledge-audit 53 OK, task-launcher benchmark
12/12 PASS, `skill_selftest.py` **5 PASS**.

PR state after this change: **ready for review**, 1,288 files, +1,753/-476,385,
`MERGEABLE / CLEAN`. Write-probe gate:
`docs/evidence/a2-coverage-2026-10-28/write-probe-passed.json` (W04/W05/W09 all
checks true, source fixture unchanged).

## Notes

- Not merged; releasing is a separate decision.
- `docs/evidence/**` is intentionally kept as historical evidence.
- No user project/window, installed skill or connector was touched by this PR.
