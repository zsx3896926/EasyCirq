# Historical replay only - do not push

Part 1 of the original PR #36 split: documentation + offline methodology.

- Path set: `docs/**`, `benchmarks/**`, root README (`530` paths, see
  `../../pr-split/history/history-pr1-paths.txt`).
- Base: merge base of the task-book baseline and the historical A tip
  (`9a951ed...`, recorded in `manifest.json.refs.history_effective_base`).
- Why it is replay-only: the historical A tip is now an ancestor of `main`
  (PR #36 merged), so this content is already in `main`; a branch based on the
  current `main` would be empty.

Acceptance for a future equivalent docs PR:

- [ ] markdown links resolve (`skill_selftest.py` markdown-links check)
- [ ] offline suite green on Python 3.10/3.13
- [ ] no runtime/connector/protocol files
- [ ] no EDA or network requirement
