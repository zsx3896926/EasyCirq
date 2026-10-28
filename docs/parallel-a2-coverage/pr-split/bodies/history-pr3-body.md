# Historical replay only - do not push

Part 3 of the original PR #36 split: the self-built runtime / connector /
protocol fork and the Skill migration.

- Path set: everything else in the historical diff - `runtime/**`,
  `connector/**`, `protocol/**`, `third_party/**`, `tools/**`, remaining
  `tests/**`, `design-hardware/**`, assets, README/NOTICE (`1,270` paths +
  `4` deletions).
- Base: `9a951ed...` (recorded in `manifest.json`).
- Replay-only: PR #36 is merged, so this branch would re-add already-merged
  content or conflict.

Acceptance for the equivalent fork PR (only if the A1 decision is taken):

- [ ] `go build ./...` green; `go test` failures documented against the upstream
      baseline (A's own M1 log had 40 Windows environment failures)
- [ ] connector `.eext` rebuild + fresh-machine manual import + handshake evidence
- [ ] `distribution/verify_vendor.py` PASS against the pinned upstream tag
- [ ] CI green on the PR head (PR #36 failed the updater job)
- [ ] no merge until the A1/A2 decision is final
