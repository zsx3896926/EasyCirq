# Handoff — annotation layout planner (task K)

## State

- worktree: `hds-al-worktree` (independent), branch `feat/parallel-annotation-layout`
- PR: https://github.com/zsx3896926/EasyCirq/pull/46
- base main SHA: `9a951edc21481dc3ae91460acc11aa3e08a7be8a`
- status: implementation + tests + benchmark + docs complete; branch pushed and
  independent PR open: https://github.com/zsx3896926/EasyCirq/pull/46
  (feature commit `a937b43`; follow-up commits include the test-bootstrap fix
  `d2e539f`; base main moved on origin after the fixed base SHA, the branch stays
  based on `9a951ed` and adds only new directories).
- host execution: **NOT RUN** (no EDA, no save/reopen, no official export, no
  connectivity readback).

## Quick verification

```bash
cd easycirq/scripts
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

`python -m annotation_layout` needs `PYTHONPATH=easycirq/scripts` (or run
from `easycirq/scripts`).  All commands are offline/read-only; outputs go
to `--out`/`--out-dir`.

## What exists

- package: `easycirq/scripts/annotation_layout/` (see `__init__.py` for
  module map).  CLI: `validate`, `plan`, `verify`, `benchmark`, `convert`,
  `version`; JSON stdout, stderr diagnostics, atomic writes, exit codes 0/1/2.
- real frozen input: `tests/annotation_layout/fixtures/photo-led-v14/input.json`
  (SHA-bound to its four source files; regenerate with `convert` if the fixture
  changes — do not edit by hand).
- fixtures: `tests/annotation_layout/fixtures/{synthetic,holdout,invalid}` plus
  `MANIFEST.json`; regenerate with
  `PYTHONPATH=easycirq/scripts python tests/annotation_layout/build_fixtures.py`.
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
bootstraps call `sys.path.insert(0, "easycirq/scripts")` at import time
(e.g. `tests/change_impact/__init__.py:25`, `tests/bringup_planner/test_*.py`,
`tests/delivery_audit/support.py:24`, `tests/mechanical_layout/test_*.py`, and
previously this branch's `tests/annotation_layout/__init__.py`).  Once that
directory is first on `sys.path`, every later package whose name also exists
under `easycirq/scripts` resolves to the **implementation**
(`easycirq/scripts/<name>/__init__.py`) instead of `tests/<name>/`.
Discovery then tries to import `<name>.test_*` from the implementation path,
which contains no test modules → `ModuleNotFoundError`.  The failing package set
therefore depends on filesystem discovery order; `return_path_audit` (last) is a
victim, and `change_impact` becomes a victim when an earlier package already
poisoned `sys.path` (as this branch's old bootstrap did).

**Evidence (reproduced locally on the PR merge ref in a temporary worktree):**

1. Old tree, full discovery: 42 import errors as above.
2. Direct probe: with `tests/` first on `sys.path`, importing
   `annotation_layout` (old bootstrap) left
   `sys.path[0] = easycirq/scripts`; a following `import change_impact`
   and `import return_path_audit` both resolved to
   `easycirq/scripts/<name>/__init__.py`.
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

**Resolution observed:** after this bootstrap fix was pushed (`d2e539f`), the PR
merge-ref `validate` jobs passed (Python 3.10 and 3.13, runs `40551679212` push
and `40551688536` pull_request) as did the updater workflow
(ubuntu/windows, run `40551687932`).  So the merge-ref is green at this point.
The underlying cross-task hazard remains: any other test bootstrap that puts
`easycirq/scripts` at the front of `sys.path` during collection can
reintroduce the same import-time failure for packages discovered later.
Recommended follow-up (outside this task's allowed paths): load implementations
via a private alias, use `append`/restore instead of `insert(0, …)`, and pass
`PYTHONPATH` in subprocess environments for CLI tests.
## Counterexample move count is expected, not a solver regression

The synthetic `counterexample` case starts with two hard conflicts:

- `A3` (`3k`, bbox y 585–595) overlaps component body `C2` (y 570–590);
- `A3` overlaps `A4` (`4k`, bbox y 585–595).

Exhaustive enumeration over the declared candidate domains (`A1` 32, `A2` 13,
`A3` 11, `A4` 25 candidates) finds **zero single-annotation moves that clear all
hard conflicts**.  A single move cannot work: moving `A3` up 5 raw clears `C2`
but still overlaps `A4`; moving it up 10–20 raw clears `A4` but enters `A2`
(y 600–610); moving `A3` left/up-left only increases the `C2` body overlap
(its `max_displacement` is 20); moving `A4` alone cannot clear `A3`↔`C2`.
The minimum is therefore **two moves**.

The batch solver's solution is exactly that minimum: `A3` +5 raw and `A4`
−5 raw (total displacement 10 raw), all hard conflicts cleared.  The naive
baseline moves only `A3` (+15 raw) and leaves `A2`↔`A3` overlapping, so it ends
`partial` with one hard conflict.  "Moves more objects" here is the cost of
actually solving the page, not a regression: the 1-move baseline is not a
higher-quality solution.

The benchmark still reports `quality_equal_or_better=false` and
`speedup_claimed=null` for this case because the task's rule is intentionally
strict: a faster run that does not clear conflicts or moves more objects must
not claim a speedup.  The improved run does clear conflicts but moves one more
object than the failing baseline, so it appropriately gets no speedup claim.
If a future benchmark policy wants a "dominates" gate (strictly fewer hard
conflicts may justify extra moves), that is a separate policy decision; it still
must not be labelled a speedup under the current contract.

No code fix is planned for this case.  The fixture and its assertion remain:
baseline introduces/leaves a hard conflict, batch solver clears all conflicts
without introducing one.
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
2. A should probe host capabilities on a page copy using the readiness package:
   `integration-host-probe.md`, `integration-adapter-contract.md` and
   `integration-apply-checklist.md`; then adapt its snapshot to
   `annotation-layout/v1`, apply one planned attribute translation on the copy,
   save/reopen and read back.
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







