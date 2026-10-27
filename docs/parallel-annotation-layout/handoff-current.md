# Handoff — annotation layout planner (task K)

## State

- worktree: `hds-al-worktree` (independent), branch `feat/parallel-annotation-layout`
- PR: https://github.com/zsx3896926/hardware-design-skill/pull/46
- base main SHA: `9a951edc21481dc3ae91460acc11aa3e08a7be8a`
- status: implementation + tests + benchmark + docs complete; branch pushed and
  independent PR open: https://github.com/zsx3896926/hardware-design-skill/pull/46
  (commit `a937b43`; base main moved on origin after the fixed base SHA, the
  branch stays based on `9a951ed` and adds only new directories).
- host execution: **NOT RUN** (no EDA, no save/reopen, no official export, no
  connectivity readback).

## Quick verification

```bash
cd design-hardware/scripts
python -m annotation_layout version
python -m annotation_layout validate ../../tests/annotation_layout/fixtures/photo-led-v14/input.json
python -m annotation_layout plan ../../tests/annotation_layout/fixtures/photo-led-v14/input.json \
  --out-dir ../../benchmarks/annotation-layout/evidence/real-plan
python -m annotation_layout verify ../../tests/annotation_layout/fixtures/photo-led-v14/input.json \
  --plan ../../benchmarks/annotation-layout/evidence/real-plan/plan.json

cd ../..
python -m unittest discover -s tests/annotation_layout -p "test_*.py"      # 86 tests
python -m unittest discover -s tests                                      # full suite
python benchmarks/annotation-layout/run_benchmark.py --repeat 7           # rewrite benchmark artifacts
```

`python -m annotation_layout` needs `PYTHONPATH=design-hardware/scripts` (or run
from `design-hardware/scripts`).  All commands are offline/read-only; outputs go
to `--out`/`--out-dir`.

## What exists

- package: `design-hardware/scripts/annotation_layout/` (see `__init__.py` for
  module map).  CLI: `validate`, `plan`, `verify`, `benchmark`, `convert`,
  `version`; JSON stdout, stderr diagnostics, atomic writes, exit codes 0/1/2.
- real frozen input: `tests/annotation_layout/fixtures/photo-led-v14/input.json`
  (SHA-bound to its four source files; regenerate with `convert` if the fixture
  changes — do not edit by hand).
- fixtures: `tests/annotation_layout/fixtures/{synthetic,holdout,invalid}` plus
  `MANIFEST.json`; regenerate with
  `PYTHONPATH=design-hardware/scripts python tests/annotation_layout/build_fixtures.py`.
- tests: 86 tests covering K1–K5, 36 CLI scenarios, metamorphic, holdouts,
  counterexample, benchmark and conversion.  `tests/annotation_layout/__init__.py`
  is a bootstrap that makes the shipped package importable under unittest
  discovery while keeping `annotation_layout.test_*` discoverable — do not remove
  it.
- benchmark: `benchmarks/annotation-layout/` with committed `result.json`,
  `benchmark-report.md`, `command.txt`, cases + SHA manifests, actual-CLI wrapper.
- docs: contract, geometry-policy, solver-policy, benchmark-report,
  acceptance-matrix, integration-proposal, report, issue-candidates.

## Merge-ref CI failure investigation (change_impact / return_path_audit)

**Observed:** the PR merge ref (`8ac3e733`, merge of head `d153a3b` into the then
base `9a4622e`) fails `validate` (3.10/3.13) with import-time
`ModuleNotFoundError`, not assertion failures: 42 `_FailedTest` errors in 6
test packages — `change_impact` 9, `return_path_audit` 8, `circuit_blocks` 7,
`delivery_audit` 7, `skill_knowledge_audit` 6, `procurement_planner` 5 (1912
tests collected).  The same class of failure also appears on `main` runs that
merge those tasks; branch-only push runs were green.

**Root cause:** `python -m unittest discover -s tests` imports each
`tests/<name>` directory as a *top-level* package `<name>`.  Several task test
bootstraps call `sys.path.insert(0, "design-hardware/scripts")` at import time
(e.g. `tests/change_impact/__init__.py:25`, `tests/bringup_planner/test_*.py`,
`tests/delivery_audit/support.py:24`, `tests/mechanical_layout/test_*.py`, and
previously this branch's `tests/annotation_layout/__init__.py`).  Once that
directory is first on `sys.path`, every later package whose name also exists
under `design-hardware/scripts` resolves to the **implementation**
(`design-hardware/scripts/<name>/__init__.py`) instead of `tests/<name>/`.
Discovery then tries to import `<name>.test_*` from the implementation path,
which contains no test modules → `ModuleNotFoundError`.  The failing package set
therefore depends on filesystem discovery order; `return_path_audit` (last) is a
victim, and `change_impact` becomes a victim when an earlier package already
poisoned `sys.path` (as this branch's old bootstrap did).

**Evidence (reproduced locally on the PR merge ref in a temporary worktree):**

1. Old tree, full discovery: 42 import errors as above.
2. Direct probe: with `tests/` first on `sys.path`, importing
   `annotation_layout` (old bootstrap) left
   `sys.path[0] = design-hardware/scripts`; a following `import change_impact`
   and `import return_path_audit` both resolved to
   `design-hardware/scripts/<name>/__init__.py`.
3. Control probe: importing `change_impact` first (from `tests/`) runs its
   `sys.path.insert(0, SCRIPTS)`; a following `import circuit_blocks` resolves
   to the implementation → same failure.
4. After removing this branch's `sys.path` mutation (fixed files copied into the
   merge worktree only): errors drop 42 → 33; all 9 `change_impact` errors
   disappear (it now resolves to `tests/change_impact`), while later packages
   still fail because that package itself inserts the path.
5. Experiment: changing only `tests/change_impact/__init__.py` from
   `insert(0, …)` to `append(…)` in the temporary merge worktree drops errors
   33 → 5 (only `delivery_audit`, attributed to another earlier insertion).
   This isolates the mechanism to global `sys.path` precedence, not to the
   failing packages' own tests.

**Mitigation made here (allowed path only):**
`tests/annotation_layout/` no longer mutates `sys.path` at import time.  It loads
the shipped `annotation_layout` implementation from its file path under a private
alias mechanism (`_bootstrap.py`), extends only that package's `__path__`, and
sets `PYTHONPATH` in CLI subprocess environments instead.  Verified: 86 tests
pass in both `discover -s tests/annotation_layout` and `discover -s tests`
modes; full local suite 1869 OK; annotation_layout tests also pass inside the
merge-ref tree after the fix.

**Remaining work is outside this task's paths:** each other task's test
bootstrap must stop making `design-hardware/scripts` first on `sys.path` during
collection (load implementation via a private alias, or `append`/restore for
subprocess needs).  Until those owners fix it, the PR merge-ref validate will
stay red on `change_impact`/`return_path_audit`/etc. even though this branch adds
no failing package.  Branch-level `validate` (3.10/3.13) and `updater`
(ubuntu/windows) pass for this branch.
## Known limitations / do not overclaim

- only offline pose planning; host capabilities were not probed; free-text and
  net-label persistence historically unreliable and explicitly not claimed;
- symbol bodies are bbox approximations; attribute rotation/alignment/font are
  unknown in the frozen read; plans are translation-only;
- estimated-bbox input can never reach `plan_verified`
  (`candidate_needs_visual_review`);
- a frozen/unsupported conflict keeps the plan `partial`/`blocked` even if the
  rest of the page is clean;
- checker skips wire checks for symbol-owned attribute texts (see
  `issue-candidates.md`); independent recheck covers it;
- analysis SVGs are not official exports; raster/visual inspection NOT RUN;
- no whole-board/EDA round-trip speedup claim; benchmark is offline solver only.

## Next steps (for A / next agent)

1. Push the branch and open the independent PR (do not merge/release/install).
2. A should probe host capabilities on a page copy using
   `integration-proposal.md` §3, then adapt its snapshot to `annotation-layout/v1`
   §2, apply one planned attribute translation, save/reopen and read back.
3. Feed the probe result back into `host.capabilities`; only then consider a
   batch apply.  A plan is a proposal, never a write authorization.
4. If A integrates, provide a post-apply snapshot so K's `verify` can re-check;
   record the real netlist readback separately (K does not execute it).

## Regeneration/care

- `build_fixtures.py` recomputes `fixtures/MANIFEST.json`; re-run the tests after
  any fixture change.
- The benchmark `cases/real-photo-led.json` references `cases/photo-led-src/`;
  do not delete that folder or the source-hash validation fails (by design).
- Never edit `tests/fixtures/photo-led-v14/` originals.
- Keep the package Python 3.10 compatible and dependency-free.




