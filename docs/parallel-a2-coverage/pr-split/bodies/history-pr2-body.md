# Historical replay only - do not push

Part 2 of the original PR #36 split: installer / upgrade / diagnostics.

- Path set: `distribution/**` plus installer/updater tests and tooling (`10`
  paths, see `../../pr-split/history/history-pr2-paths.txt`).
- Base: `9a951ed...` (recorded in `manifest.json`).
- Replay-only for the same reason as PR-1: PR #36 is merged.

Acceptance for a future equivalent distribution PR:

- [ ] install / idempotent reinstall / upgrade / rollback / uninstall lifecycle
      tests green in a temp directory
- [ ] no EDA write, no network, no self-update to upstream
- [ ] connector bundle steps removed (that layer is retired by the A2 step)
- [ ] `distribution/verify_vendor.py` either removed or re-scoped
