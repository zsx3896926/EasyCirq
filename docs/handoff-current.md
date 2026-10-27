# v1.0 ecosystem integration handoff

Date: 2026-10-27 (Asia/Shanghai).

- User expanded v1.0 scope to absorb the eight reviewed EasyEDA ecosystem sources.
- Worktree C:/Users/jlc/work/hds-release-v1, local and remote branch release/v1.0.0;
  PR #33. Previous remote head 81c7f57; consult GitHub for current head/status.
- Source version 1.0.0, Apache-2.0. Copied upstream schemas retain MIT license.
- Unified entry: design-hardware/scripts/ecosystem.py registry / run.
- Report: docs/releases/ecosystem-integration.md; machine acceptance:
  docs/releases/ecosystem-acceptance.json. Each subsystem has its own reference.
- Validated: 123 focused tests; full guarded suite 1782 OK (skipped=1), 100 imports
  clean, zero blocked attempts; selftest 5 PASS; benchmarks 9/9 and 16/16;
  unified offline CLI smoke 12/12. Independent cross-review failures fixed.
- Local guarded suite uses short temp root C:/Users/jlc/work/hds-test-temp because
  the managed sandbox's default Windows temp paths are too deep for updater tests.
- Package rebuild and installed-archive smoke must use this final candidate;
  previous package success does not cover the new ecosystem code.
- New live EDA calls, external plugin installation, actual viewer rendering,
  hardware/manufacturing: NOT RUN. No shared GUI/window ownership requested.
- Existing feedback final-code live write BLOCKED; compose strict/full-playbook
  success remains unverified. Refer to docs/round12/report.md and round12-real-machine.md.
- No long-running EDA/daemon process owned. No tag, merge or Release authorized
  by this integration step. Next: push exact tested tree to #33, wait for CI,
  then separately complete formal publication and online asset checks.
