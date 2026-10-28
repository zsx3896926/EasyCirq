# Task N (A2-COVERAGE) handoff

- Branch / worktree / baseline main:
  `spike/a2-eda-coverage` @ `C:\Users\jlc\Documents\deepseek-harness\default-workspace\hds-a2-worktree`,
  branched from `main @ fd4499cd3c98dc66c96bb38a703ce562e1c3dbe5`.
- A reference HEAD (read-only): `origin/feat/integrated-eda-toolchain @ dfa8f10d7149df435ab0c0be91edcdcb91990ce1`.
- PR: **draft PR #75** `spike(a2): official CLI/MCP vs A typed-action coverage and thin adapter`
  - https://github.com/zsx3896926/hardware-design-skill/pull/75
  - branch `spike/a2-thin-layer`, base `main`, 233 files, +26,516 / -0, draft.
  - CI at commit `1bbb674`: `validate (3.10)` PASS, `validate (3.13)` PASS,
    `updater (ubuntu-latest)` PASS, `updater (windows-latest)` PASS, publish skipped.
    The first CI run was red for two portability bugs (Windows `\` separators in
    `pr-split/manifest.json`, CRLF-vs-LF hashing of `a-self-evidence`), fixed in
    `1bbb674` ("posix split manifest paths and LF-normalised hashes").
  - Step 1 (residual manufacture export PR) is **void**: its content was already
    merged via PR #71 (`feat: 制造导出能力…`, merged 2026-10-28T04:19:45Z); the
    A branch is now an ancestor of `main`, so `origin/main...origin/feat/integrated-eda-toolchain`
    has no diff. Nothing was pushed for Step 1.
  - Step 3 (retire `runtime/connector/protocol`) remains **gated** on an authorized
    W04/W05/W09 write probe.
  - The three-step command list is `docs/parallel-a2-coverage/pr36-split-runbook.md`
    (path sets in `docs/parallel-a2-coverage/pr-split/`; regenerate after ref moves).
  - The task-book-era note "PR not created (no network)" is superseded by the
    explicit operator instruction on 2026-10-28 12:2x to push this PR.
- Exact HEAD: see `git log -1` on the branch (this file is committed with it).
- Environment: Windows, JLCEDA Pro 4.1.78.34f5b8d9 at
  `C:\Users\jlc\AppData\Local\Programs\LCEDA-Pro\lceda-pro.exe`,
  Python 3.13.15, Node 24.20.0, no Go. Temp fixture copy:
  `%TEMP%\a2-spike-20261028-1050\fixture\a2spike-quickstart.eprj2`
  (sha256 `824f6dcc...`). Authorization: **no design-write authorization**;
  write cells are `blocked`.
- Official CLI real coverage: W01, W02 (partial), W03 (partial), W04, W05,
  W06 (partial), W07 (partial), W08, W09, W10, W11.
  Receipts: `docs/evidence/a2-coverage-2026-10-28/raw/`, `api/`,
  `write-probe/`, `mcp-tools.json`.
- A side: **static only** (action catalog + A's own self-evidence under
  `a-self-evidence/`). A could not be run: no Go toolchain, and the A connector
  only exists in the user's GUI window while this spike may only drive
  `origin:"cli"` sessions (a CLI-opened editor reports 0 extensions).
- Key failures/gaps: `open` returns before the project loads;
  `getReadyState()` stays `notLoaded`; `sch_Net.*` returns `[]` (use the Protel
  netlist); `sys_FileSystem` is permission-gated (base64 relay used);
  `REQUEST_TIMEOUT` can leave unknown side effects; no official DFM audit;
  no typed batch/journal; `doc api` has no write session so W04/W05 unproven.
- Decision: **incomplete (provisional)**, lean **A2**, confidence **medium**.
  W04/W05/W09 are now `covered` by an authorized disposable-copy write probe
  (`write-probe-passed.json`); the remaining critical gaps are wrapper scope
  (W02 net parsing, W06 batch plan, W07 DRC/DFM shaping).
  Evidence: `coverage-matrix.md` / `rubric.json` / `decision.md`.
  Counterexamples that would flip it are listed in `decision.md` §4.
- #36 split (3):
  1. PR-1 docs + offline methodology (no runtime/connector);
  2. PR-2 distribution install/upgrade/rollback;
  3. PR-3 retire `runtime/`+`connector/`+`protocol/` and add the thin official-CLI
     adapter - only after an authorized W04/W05/W09 write probe turns those cells
     `covered`.
- B1 Phase 2: use the official CLI/MCP as the execution backend; B1 must still
  implement its own write gate (session guard, load poll, plan/readback,
  timeout->readback, export relay).
- NOT RUN / BLOCKED: W06 write batching; `--mcp http`; `doc external/format`;
  library/3D/panel surfaces; PCB geometry dumps; A build/run; any network.
  W04/W05/W09 writes are DONE (authorized probe, disposable `%TEMP%` copy;
  marker `docs/evidence/a2-coverage-2026-10-28/write-probe-passed.json`).
  Step 3's gate in `pr36-split-runbook.md` is satisfied; the A1/A2/A3 decision
  itself is still provisional because of the W02/W06/W07 wrapper gaps.
- Verification: new offline package 54 tests OK; full `python -m unittest
  discover -s tests` 3311 tests OK (2 skipped); `skill_selftest.py` 5 PASS;
  `run_spike.py --offline` regenerates the matrix without EDA/network.
- Next steps:
  1. Get explicit write authorization for one disposable temp project, then run
     `probe_official.py` with a write extension (to be added) covering W04/W05/W09
     and regenerate the matrix.
  2. Re-run the rubric; if >=7/8 critical covered -> A2 final, then open PR-3.
  3. If writes are unreliable -> A1, and keep the A runtime after a green CI +
     fresh-machine connector import.
