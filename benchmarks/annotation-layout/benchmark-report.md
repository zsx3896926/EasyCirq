# annotation-layout benchmark report

- schema: `annotation-layout-benchmark/v1`
- tool: `annotation_layout` 0.1.0
- repeat: 7 (median + min/max)
- seed: 20261027
- python: 3.13.15 on Windows-11-10.0.26200-SP0
- cases: 5 (real frozen 1, synthetic 4)

Baseline = deterministic per-annotation greedy + full recheck after each placement. Improved = bounded focus/cluster search with spatial index and local search. Same candidate domains, spacing, font and displacement limits.

## Summary

| group | cases | baseline median s | improved median s | quality-equal | speedup claimed |
| --- | --- | --- | --- | --- | --- |
| real frozen | 1 | 1.923145 | 0.023574 | 1 | 1 |
| synthetic | 4 | 0.00283 | 0.000822 | 3 | 3 |
| all | 5 | 0.004033 | 0.000908 | 4 | 4 |

## Per case

| case | kind | before hard | baseline hard/moved | improved hard/moved | baseline median s (min–max) | improved median s (min–max) | quality met | speedup |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| counterexample.json | synthetic | 2 | 1/1 | 0/2 | 0.004033 (0.003902–0.004316) | 0.000908 (0.00088–0.000968) | False | not claimed |
| dense.json | synthetic | 3 | 0/3 | 0/3 | 0.014415 (0.013531–0.016427) | 0.002712 (0.002556–0.003034) | True | 5.315 |
| real-photo-led.json | real_frozen | 3 | 0/11 | 0/2 | 1.923145 (1.738616–2.004447) | 0.023574 (0.020959–0.027204) | True | 81.579 |
| text-text.json | synthetic | 1 | 0/1 | 0/1 | 0.001627 (0.001517–0.002041) | 0.000736 (0.000715–0.001155) | True | 2.211 |
| text-wire.json | synthetic | 1 | 0/1 | 0/1 | 0.000529 (0.000507–0.001306) | 0.000383 (0.000368–0.000742) | True | 1.379 |

## CLI round trip

- `counterexample.json`: median 0.194671 s (0.185603–0.201237), statuses ['planned_clear', 'planned_clear', 'planned_clear']
- `dense.json`: median 0.196368 s (0.192277–0.201592), statuses ['planned_clear', 'planned_clear', 'planned_clear']
- `real-photo-led.json`: median 0.521289 s (0.489091–0.536938), statuses ['planned_clear', 'planned_clear', 'planned_clear']
- `text-text.json`: median 0.177941 s (0.172196–0.181616), statuses ['planned_clear', 'planned_clear', 'planned_clear']
- `text-wire.json`: median 0.175363 s (0.174052–0.176157), statuses ['planned_clear', 'planned_clear', 'planned_clear']

## NOT RUN / limitations

- NOT RUN: NOT RUN: EDA render / official export
- NOT RUN: NOT RUN: host write / save / reopen / connectivity readback
- NOT RUN: NOT RUN: whole-board / host round-trip wall time
- offline solver work only; EDA render/save/reopen/readback and whole-board time NOT RUN
- timings are machine-dependent; medians/ranges are reported, not a guarantee
- synthetic cases are explicitly labelled and are not evidence about a real board
- quality gate requires equal-or-better hard conflicts and not more moved annotations
