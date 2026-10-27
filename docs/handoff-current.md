# Round 13 handoff: SkyPilot X1 feedback

- Baseline: `origin/main` at `9a951ed` (= published v1.0.1, installed on this
  machine). Source version unchanged at 1.0.1; no release in this round.
- Branch `feat/feedback-round13-skypilot` in worktree
  `C:/Users/jlc/work/hds-feedback-r13`.
- Done: six field lessons from the SkyPilot X1 nine-page schematic written into
  `references/tool-gotchas.md` (table + §22–§26),
  `references/schematic-layout-engine.md` (§5, §12),
  `references/schematic-layout.md` (§3.2); `sch_layout_model.py` now publishes
  per-part `envelopes` in `model-report.json`; one new unit test.
- Evidence: `docs/feedback-round13-report.md`. Source task evidence lives
  outside this repo (`skypilot-x1/build/`), so nothing here replays live
  connector behaviour.
- Checks run: full offline suite on Python 3.13 -> 1784 tests OK;
  `skill_selftest.py` -> 5 PASS / 0 FAIL. Python 3.10 not installed locally
  (`NOT RUN`); `validate.yml` covers it in CI.
- Not covered: gate verdict after adding zone frames/title block; queue-exhaustion
  threshold on other client versions; the 40/45-raw packing margins are A4-specific
  measurements, not constants.
- Next: push branch, open PR, watch the validate matrix (3.10 + 3.13).
