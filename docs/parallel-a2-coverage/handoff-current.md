# Task N (A2-COVERAGE) handoff

- Branch / worktree / baseline main:
  `spike/a2-eda-coverage` @ `C:\Users\jlc\Documents\deepseek-harness\default-workspace\hds-a2-worktree`,
  branched from `main @ fd4499cd3c98dc66c96bb38a703ce562e1c3dbe5`.
- A reference HEAD (read-only): `origin/feat/integrated-eda-toolchain @ dfa8f10d7149df435ab0c0be91edcdcb91990ce1`.
- PR: **not created** - the task book forbids network use, and pushing was
  therefore not attempted. The branch is local and ready; the operator can open
  the PR with the title `spike(a2): official CLI/MCP vs A typed-action coverage`
  (body: `docs/parallel-a2-coverage/report.md`, do not merge).
  Follow-up note: PR #36 has since been merged into `main`, so the three-step
  push / create-PR command list for the residual work lives in
  `docs/parallel-a2-coverage/pr36-split-runbook.md` (path sets generated in
  `docs/parallel-a2-coverage/pr-split/`).
- Exact HEAD: see `git log -1` on the branch (this file is committed with it).
- Environment: Windows, JLCEDA Pro 4.1.78.34f5b8d9 at
  `C:\Users\jlc\AppData\Local\Programs\LCEDA-Pro\lceda-pro.exe`,
  Python 3.13.15, Node 24.20.0, no Go. Temp fixture copy:
  `%TEMP%\a2-spike-20261028-1050\fixture\a2spike-quickstart.eprj2`
  (sha256 `824f6dcc...`). Authorization: **no design-write authorization**;
  write cells are `blocked`.
- Official CLI real coverage: W01, W02 (partial), W03 (partial), W06 (partial),
  W07 (partial), W08 (covered), W09 (reopen only; save blocked), W10, W11.
  Receipts: `docs/evidence/a2-coverage-2026-10-28/raw/`, `api/`, `mcp-tools.json`.
- A side: **static only** (action catalog + A's own self-evidence under
  `a-self-evidence/`). A could not be run: no Go toolchain, and the A connector
  only exists in the user's GUI window while this spike may only drive
  `origin:"cli"` sessions (a CLI-opened editor reports 0 extensions).
- Key failures/gaps: `open` returns before the project loads;
  `getReadyState()` stays `notLoaded`; `sch_Net.*` returns `[]` (use the Protel
  netlist); `sys_FileSystem` is permission-gated (base64 relay used);
  `REQUEST_TIMEOUT` can leave unknown side effects; no official DFM audit;
  no typed batch/journal; `doc api` has no write session so W04/W05 unproven.
- Decision: **incomplete (provisional)**, lean **A2**, confidence **low**.
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
- NOT RUN / BLOCKED: W04/W05 writes, W09 save, write batching (no authorization);
  `--mcp http`; `doc external/format`; library/3D/panel surfaces; PCB geometry
  dumps; A build/run; any network.
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
