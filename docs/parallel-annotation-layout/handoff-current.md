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


