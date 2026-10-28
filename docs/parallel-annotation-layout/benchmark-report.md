# Benchmark report

- tool: `annotation_layout` 0.1.0, schema `annotation-layout/v1`
- run: `python benchmarks/annotation-layout/run_benchmark.py --repeat 7`
- machine: Windows 11 (10.0.26200), Python 3.13.15, AMD64, 28 logical CPUs
- seed: 20261027 (search is deterministic; the seed is recorded for reproducibility)
- full machine result: `benchmarks/annotation-layout/result.json`
- exact command: `benchmarks/annotation-layout/command.txt`
- generated report: `benchmarks/annotation-layout/benchmark-report.md`

## What is compared

Both algorithms receive **the same candidate domain** (generated once per case
before timing), the same spacing/font/movement constraints and the same input:

- **baseline** `baseline.py`: deterministic one-by-one greedy in ID order, then a
  full `evaluate_assignment` re-check after every placement; no backtracking, no
  incremental cache;
- **improved** `solver.py`: bounded local focus, cluster decomposition, spatial
  index, static per-candidate cache, deterministic local search and budgeted
  backtracking.

Measurement is offline solver time (`time.perf_counter`), 7 repetitions,
median + min/max.  Candidate-domain generation time is recorded separately and
excluded from both solver timings.

## Cases

| case | kind | before hard | source |
|---|---|---|---|
| `real-photo-led.json` | real frozen | 3 | photo-led v14, official EasyEDA 4.1.78 SVG text bbox + `sch list`; SHA-bound in `source.files` |
| `dense.json` | synthetic | 3 | 6-value overlap chain |
| `text-text.json` | synthetic | 1 | 2-value overlap |
| `text-wire.json` | synthetic | 1 | free text crossed by a wire |
| `counterexample.json` | synthetic | 2 | per-annotation greedy introduces a new conflict |

Case hashes are in `cases/MANIFEST.json`; the real source hashes are in the
input document and re-checked on every load (stale provenance is rejected).

## Result

| case | baseline hard/moved | baseline median s (range) | improved hard/moved | improved median s (range) | baseline→improved collision checks | quality gate | speedup claim |
|---|---|---|---|---|---|---|---|
| real-photo-led | 0 / 11 | 1.923 (1.739–2.004) | 0 / 2 | 0.0236 (0.0210–0.0272) | 1,199,215 → 4,147 | pass | **81.6×** |
| dense | 0 / 3 | 0.0144 (0.0135–0.0164) | 0 / 3 | 0.00271 (0.00256–0.00303) | 2,985 → 570 | pass | 5.32× |
| text-text | 0 / 1 | 0.00163 (0.00152–0.00204) | 0 / 1 | 0.000736 (0.000715–0.00116) | 67 → 38 | pass | 2.21× |
| text-wire | 0 / 1 | 0.000529 (0.000507–0.00131) | 0 / 1 | 0.000383 (0.000368–0.000742) | 0 → 1 | pass | 1.38× |
| counterexample | 1 / 1 | 0.00403 (0.00390–0.00432) | 0 / 2 | 0.000908 (0.000880–0.000968) | 581 → 119 | **fail** (moved more) | **not claimed** |

Ranges are min–max of 7 repetitions from `result.json`; medians are rounded for
readability.  Small cases have visible run-to-run noise and are not used to claim
a general speedup.

Summary from `result.json`:

- real frozen: 1.923 s → 0.0236 s median (81.6×), 11 → 2 moved annotations,
  all 3 blocking conflicts cleared;
- synthetic: 3 of 4 cases pass the quality gate (1.4×–5.0×); the
  `counterexample` case is faster but moves more annotations than the failing
  baseline, so **no speedup is claimed** for it;
- quality gate: improved must end with zero hard conflicts, must not move more
  annotations than the baseline, must introduce no new hard conflict and must
  pass the independent geometric recheck.  A run that fails the gate is not
  reported as a speedup.

## Interpretation and honesty notes

- The 81.6× figure is an **offline solver-only** result on a frozen real page.
  It does **not** establish a whole-board, host round-trip, save/reopen or
  rendered-export speedup.  What it proves is that the baseline's full re-check
  strategy performs ~1.2M collision checks where the improved path performs
  ~4.1k, while both clear the same conflicts and the improved plan moves fewer
  texts.
- Synthetic cases are labelled and are not evidence about any real board.  The
  small-case ratios are dominated by fixed overheads and measurement noise; they
  are reported as medians with ranges, not as headline claims.
- The real case's baseline leaves 0 hard conflicts but moves 11 annotations; the
  improved solver clears the same 3 conflicts with 2 minimal moves.  This is a
  quality difference as well as a time difference.
- Python CLI round trip for the whole plan (package import, candidate generation,
  solve, independent verification, existing checker, two analysis SVGs) measured
  medians of 0.18–0.52 s per case in `result.json.cli_round_trip`.  This is
  reported separately; it is not used to claim a solver-speedup multiplier.
- EDA rendering, host write, save/reopen, connectivity readback, official export
  and installation are **NOT RUN**.  No visual/raster inspection was performed;
  the SVG check is XML/geometry-level only (`raster preview NOT RUN`).
- Wall-clock numbers are machine-dependent; the environment is recorded in
  `result.json.environment` and no cross-machine comparison is claimed.


