## What

Retirement PR for the A (self-built) execution layer, per the A2 coverage
decision and the authorized write probe. **Draft: staged deletion only - do not
merge until the follow-up migration in the checklist below lands.**

Deletes 1,147 files / 466,740 lines:

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

## Why this is a draft and CI is expected red

The deletion is mechanically generated (`spike/a2-coverage/plan_pr36_split.py
apply --set retire`), but the repository still references the retired layer.
Measured on the merge base of this branch (`origin/main @ 441454e`), after the
staged deletion:

| area | files still referencing `zhigou` / the retired paths | required follow-up |
| --- | ---: | --- |
| `docs/**` | 303 | keep historical docs but fix/retire broken links to `runtime/`, `connector/`, `protocol/` |
| `easycirq/**` | 78 | update the application package to the official-CLI adapter / rename |
| `benchmarks/**` | 39 | point scenarios at the official adapter or mark historical |
| `tests/**` | 36 | drop runtime/connector/daemon tests, keep offline-gate tests |
| `tools/**` | 14 | update acceptance/board scripts to the official adapter |
| `distribution/**` | 9 | keep install/upgrade/rollback, remove runtime+connector bundle steps |
| `.github/workflows/skill-updater.yml` | 2 | remove connector build/package jobs (Go/Node) |
| `README.md`, `NOTICE`, `.gitignore` | 3 | update description, notices, ignore rules |

Until those follow-ups are in this PR, `validate` (full unittest + skill
selftest + markdown links) will fail. That is intentional for the draft: the
retirement is not mergeable on `main` until the references are migrated.

## Acceptance (before ready-for-review)

- [ ] `grep -r zhigou` outside historical evidence is 0
- [ ] no markdown link points to a deleted `runtime/`, `connector/`, `protocol/` path
- [ ] `python -m unittest discover -s tests` green (3.10 / 3.13)
- [ ] `python design-hardware/scripts/skill_selftest.py` 5 PASS
- [ ] CI `validate` + `updater` jobs green (updater no longer builds connector)
- [ ] `design-hardware/SKILL.md` names the official CLI/MCP adapter as executor
- [ ] linked write-probe marker stays in the PR description

## Do not

- do not merge while draft/CI-red;
- do not delete `docs/evidence/**` (historical evidence is kept);
- do not touch the user's installed skills/connector from this PR.
