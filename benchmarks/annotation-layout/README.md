# annotation-layout benchmark

Same input, same candidate domain, same spacing/font/displacement constraints:
the naive baseline (deterministic one-by-one greedy + full re-check after every
placement) versus the shipped bounded batch solver (focus/cluster decomposition,
deterministic local search/backtracking, spatial index and incremental checks).

Only **offline solver work** is measured. EDA rendering, host write,
save/reopen, connectivity readback and whole-board time are **NOT RUN**.

## Cases

| file | kind | source |
|---|---|---|
| `cases/real-photo-led.json` | real frozen | converted `photo-led-v14` (official EasyEDA 4.1.78 SVG text bbox + `sch list`), see `photo-led-src/` and `cases/MANIFEST.json` |
| `cases/dense.json` | synthetic | 6-value overlap chain |
| `cases/text-text.json` | synthetic | 2-value overlap |
| `cases/text-wire.json` | synthetic | free text crossed by a wire |
| `cases/counterexample.json` | synthetic | per-annotation greedy introduces a new conflict; batch search clears all |

`synthetic` cases are explicitly generated test geometry, not a real board.
All case hashes are recorded in `cases/MANIFEST.json` and the fixture manifest.

## Reproduce

```bash
# from the repository root
python benchmarks/annotation-layout/run_benchmark.py --repeat 7
# exact command + machine-readable result + Markdown report land in this folder:
#   command.txt, result.json, benchmark-report.md
```

The wrapper invokes the real CLI entry point in a subprocess:

```text
python -m annotation_layout benchmark --suite benchmarks/annotation-layout/cases \
  --repeat 7 --seed 20261027 --out benchmarks/annotation-layout
```

## Result (Windows 11, Python 3.13.15, repeat 7, seed 20261027)

| case | before hard | baseline hard/moved | baseline median s (range) | improved hard/moved | improved median s (range) | collision checks (base→imp) | speedup claim |
|---|---|---|---|---|---|---|---|
| real-photo-led | 3 | 0 / 11 | 1.923 (1.739–2.004) | 0 / 2 | 0.0236 (0.0210–0.0272) | 1,199,215 → 4,147 | **81.6×** |
| dense | 3 | 0 / 3 | 0.0144 (0.0135–0.0164) | 0 / 3 | 0.00271 (0.00256–0.00303) | 2,985 → 570 | 5.32× |
| text-text | 1 | 0 / 1 | 0.00163 (0.00152–0.00204) | 0 / 1 | 0.000736 (0.000715–0.00116) | 67 → 38 | 2.21× |
| text-wire | 1 | 0 / 1 | 0.000529 (0.000507–0.00131) | 0 / 1 | 0.000383 (0.000368–0.000742) | 0 → 1 | 1.38× |
| counterexample | 2 | 1 / 1 | 0.00403 (0.00390–0.00432) | 0 / 2 | 0.000908 (0.000880–0.000968) | 581 → 119 | **not claimed** |

Quality gate: the improved run must end with `hard_after=0`, must not move more
annotations than the baseline, must introduce no new hard conflict and must pass
the independent geometric recheck. The counterexample run is faster but moves
one more annotation than the failing baseline, so **no speedup is claimed** for
it; the benchmark reports the contradiction rather than hiding it.

The real frozen case improved the offline solver from 1.923 s to 0.0236 s
(81.6×) while moving 2 annotations instead of 11 and clearing all 3 blocking
conflicts. This is an **offline solver-only** result: it does not establish a
whole-board or host round-trip speedup. Python CLI round trip for the full plan
(package start + candidate generation + solve + independent verification +
checker + two SVGs) measured a median of 0.18–0.52 s, reported separately in
`result.json` (`cli_round_trip`) and not mixed into the solver comparison.

Small synthetic cases show large relative timing noise; medians/ranges are
reported, and one case (text-wire) has a ~1.4× difference that should not be
generalised. The real case is the evidence for the intended workload.

## Method notes

- Candidate domains are generated once per case and shared verbatim by both
  algorithms (`candidate_domain` in `result.json`); timing excludes domain
  generation, which is reported separately (`candidate_domain.generation_seconds`).
- Baseline counts a full `evaluate_assignment` after every placement, which is
  why the real case performs ~1.2M collision checks versus ~4.1k for the
  improved solver. The counter is not a wall-clock substitute.
- `/usr/bin/time`-style external profiling, EDA rendering, save/reopen, official
  export, connectivity readback and installation are NOT RUN.
- Timings are machine-dependent; the raw environment is recorded in
  `result.json.environment`. There is no cross-machine claim.

## Files

- `cases/` — committed case inputs + `MANIFEST.json`
- `photo-led-src/` — the four frozen source files referenced by the real case
- `run_benchmark.py` — actual CLI wrapper; writes `command.txt`
- `result.json` — full machine result (all samples, counters, quality gate)
- `benchmark-report.md` — generated Markdown report (timings + NOT RUN)
- `command.txt` — exact command used for the committed result



