# Task K report — batch annotation avoidance / local relayout planner

## 1. Result

A standalone offline planner for schematic **text pose plans** is implemented and
runs end-to-end on the frozen real `photo-led-v14` page:

- input: 19 components, 98 wires, 136 texts (94 fixed + 42 movable annotations);
- before: 3 blocking conflicts (value text vs symbol body; purpose text vs two
  wire segments), 9 informational/clearance findings;
- planned: 2 translations (`10kΩ` −5 raw, Chinese purpose note +5 raw), 10 raw
  total displacement, no font/content/net/rotation/align/owner change;
- after: 0 blocking conflicts in the unchanged existing checker
  (`sch_layout_check.analyze`) **and** 0 hard findings in an independent
  brute-force recheck; status `planned_clear`, verification `plan_verified`;
- host execution, save/reopen, official export and connectivity readback remain
  **NOT RUN** (no EDA was called).

Commands:

```bash
# from the repository root
cd design-hardware/scripts
python -m annotation_layout validate ../../tests/annotation_layout/fixtures/photo-led-v14/input.json
python -m annotation_layout plan ../../tests/annotation_layout/fixtures/photo-led-v14/input.json \
  --out-dir ../../benchmarks/annotation-layout/evidence/real-plan
python -m annotation_layout verify ../../tests/annotation_layout/fixtures/photo-led-v14/input.json \
  --plan ../../benchmarks/annotation-layout/evidence/real-plan/plan.json
python -m annotation_layout benchmark --suite ../../benchmarks/annotation-layout/cases --repeat 7
```

## 2. What was delivered (allowed paths only)

| path | content |
|---|---|
| `design-hardware/scripts/annotation_layout/` | shipped package: `model`, `geometry`, `schema`, `conflicts`, `candidates`, `solver`, `baseline`, `planner`, `verify`, `svg_analysis`, `report`, `convert`, `benchmark`, `io_util`, `cli`, `__main__` |
| `tests/annotation_layout/` | 86 tests: schema/geometry, conflicts/candidates, solver/baseline, independent verification, SVG, 36 CLI scenarios (≥50 real subprocess invocations), metamorphic, 4 holdouts, counterexample, benchmark, convert; fixtures with SHA manifest |
| `benchmarks/annotation-layout/` | real + 4 synthetic cases, SHA manifests, actual-CLI wrapper, committed `result.json`, generated Markdown report, `command.txt`, README |
| `docs/parallel-annotation-layout/` | this report + contract, geometry/solver policy, benchmark report, acceptance matrix, integration proposal, handoff, issue candidates |

No `SKILL.md`, existing reference, README/CHANGELOG/version, runtime/connector/
protocol, distribution, CI, top-level dependency, feedback, compose,
`design_engine`, `layout_from_easyeda`, `sch_layout_check` or other task directory
was modified.

## 3. Contract highlights

- Strict versioned JSON (`annotation-layout/v1`) with SHA binding; rejects
  NaN/inf/bool-as-number, duplicate IDs, unknown units/keys, stale source hashes
  and stale junction evidence.
- Candidate = on-grid rigid translation of the measured bbox; font, rotation,
  alignment, content, net and owner are immutable.  Fixed/unsupported roles have
  empty domains.
- Focused batch search: hard-conflict filter → bounded local focus → cluster
  decomposition → deterministic greedy → bounded local search → budgeted
  backtracking; whole-assignment acceptance; no per-annotation optima left
  behind.
- Freeze/scope, no-op, deterministic output and fixpoint re-planning.
- Failure taxonomy (`no_candidates`, `all_candidates_rejected`,
  `budget_exhausted`, `geometry_uncertain`, `host_capability_unsupported`,
  `net_label_anchor_not_separable`, `frozen_by_scope`) instead of a single
  "infeasible".
- K5: independent O(n²) recheck plus the existing checker called unchanged;
  before/after findings retained; `plan_verified` only for a clean, measured
  geometry; analysis SVGs are `analysis_not_official_export`.

## 4. Test evidence

- `python -m unittest discover -s tests/annotation_layout -p "test_*.py"` →
  **86 tests OK** (≈16 s).
- Full repository suite: `python -m unittest discover -s tests` → OK
  (1869 tests; see handoff for the final recorded run).
- Offline guard and skill self-test unaffected:
  `python tools/offline_suite.py --pattern "test_no_such_round11_*.py"` still
  reports 0 tests/discovered correctly after the test-package bootstrap fix.
- 36 CLI scenario test methods, including the 6 invalid-input sub-cases, 10
  positive/negative plan cases, scope/freeze, verify/stale, benchmark, convert,
  determinism, no-stale-PASS and usage errors.

## 5. Benchmark (honest summary)

Committed run: Windows 11, Python 3.13.15, seed 20261027, 7 repetitions per case,
same candidate domain for both algorithms.

| case | baseline | improved | speedup |
|---|---|---|---|
| real-photo-led | 0 hard / 11 moved, 1.923 s, 1,199,215 checks | 0 hard / 2 moved, 0.0236 s, 4,147 checks | 81.6×, quality gate pass |
| dense (synthetic) | 0 / 3, 0.0144 s | 0 / 3, 0.00271 s | 5.32× |
| text-text (synthetic) | 0 / 1, 0.00163 s | 0 / 1, 0.000736 s | 2.21× |
| text-wire (synthetic) | 0 / 1, 0.000529 s | 0 / 1, 0.000383 s | 1.38× |
| counterexample (synthetic) | 1 / 1, 0.00403 s | 0 / 2, 0.000908 s | **not claimed** (moves more) |

Interpretation: this is **offline solver work only**.  It does not establish a
whole-board/host round-trip speedup.  Python CLI round trip for a full plan
(including verification, checker and two SVGs) was 0.18–0.52 s median; EDA
render/save/reopen/readback are **NOT RUN**.

## 6. Review notes / limitations

- Independent review was done from the test and benchmark evidence (single-agent
  environment; no visual renderer): the real plan's after-findings are empty in
  both the checker and the independent path; the counterexample is explicitly
  refused a speedup claim; stale/invalid inputs exit 2 and cannot leave a PASS.
- Known checker limitation: it skips wire checks for texts owned by a symbol
  (attribute texts); the independent recheck covers those and the plan records
  the limitation.  Not fixed here (outside allowed paths) — see
  `issue-candidates.md`.
- Symbol bodies are bbox approximations; attribute rotation/alignment/font are
  unknown in the retained host read, so plans are translation-only.
- Free-text/net-label host persistence was not probed and is not claimed.
- Visual/raster inspection of the analysis SVGs was **NOT RUN**; only XML and
  geometry-level validation was performed.
- A single-agent environment prevented a separate Team reviewer from signing
  off; the Lead performed the adversarial checks and recorded them here and in
  the acceptance matrix.

## 7. PR

Branch `feat/parallel-annotation-layout`, independent worktree, base main
`9a951edc21481dc3ae91460acc11aa3e08a7be8a`.  PR link and final SHA are recorded
in `handoff-current.md` after push.  Not merged, not released, not installed.




