# Independent verification of the parallel round-7 EDA result

Date: 2026-10-24. This session (`feat/sch-layout-engine-round7`) did **not** perform
the real relayout described here. A parallel session (`jlc-ea`) performed it on
`temp-alarm-r7-scratch`; this document records an independent read-only check of its
final archive.

## Inputs

- Archive: `C:\Users\jlc\work\temp-alarm-20261024\evidence\round7\temp-alarm-r7-final.epro2`
- Size: 387,055 bytes; SHA-256
  `E4BD1B9E80E39FBF87D9F38FD34EA5D9C7341DE7B5DFC4A0DE931CED7B41A13E`
- Imported as a new project `temp-alarm-r7-verify`
  (`a5689d21f19c4d5ea34d273a8577edce`); schematic page `6a8364999a809cb4`.
- Baseline for comparison: `evidence/round7/final/before-conn.json`, imported from
  `before-round7.epro2` (SHA-256 `f5f1b33f…`).

## Result

| Check | Result |
|---|---|
| Components | 26 / 26, same refs, same `deviceUuid` and footprint |
| Pin→net partition | **Identical**. 65/65 pin keys, 14 nets, net-name changes (`D1_N1→VBUS`, `D1_N3→CC1`, `D1_N4→CC2`) do not change any pin partition |
| NC | 6 J1 data pins (B6/B7/B8/A6/A7/A8), unchanged |
| `sch gate` | **pass** (layout-lint, clusters, check, bridge-check, drc) |
| `layout-lint` | 0 overlap, 0 tight, 0 pin-coincidence, 0 off-grid, 0 out-of-sheet |
| `sch clusters` | 24 findings, all WARN `tight`; no ERROR |
| `layout-score` | **60.7 / fair** — folded 100, reversed-labels **0**, proximity 57.9, stub-tidiness 72, frame-fit 100 |
| Independent `sch_layout_quality.py` | **0 error**, 6 warn, 3 info; before was 5 error, 6 warn, 2 info |
| PCB `pcb drc` | **passed: true, total 0** |
| PCB `layout-lint` | 92 / easy, 26 parts, 71/71 pads measured, 2 crossings, ratsnest 5,632.51 mil |

### Quality comparison

| Metric | Before | Parallel final | This session's offline candidate |
|---|---|---|---|
| Quality errors (independent) | 5 | **0** | **0** |
| Warnings | 6 | 6 | 2 |
| Module overlaps | 5 pairs | **0** | **0** |
| Component side balance (left/right) | 4 / 22 | **16 / 10** | 14 / 12 |
| Wire length | 2310 | **1940** | 1805 |
| Different-net crossings | 0 | 0 | 5 |
| Official `layout-score` | 94 (misleading) | **60.7 / fair** | not run (offline) |
| Applied to EDA | — | **yes** | no |

## Interpretation

- The parallel result is a real, electrically equivalent improvement: no module
  overlaps, balanced page, gate pass, 65/65 pin partition unchanged, PCB DRC 0.
- It is not "done": the official score exposes 8 reversed netport labels and poor
  proximity (57.9); our checker additionally sees top/bottom imbalance, sparse page
  and four fragmented modules (labels/ports far from their core). These are
  readability issues, not electrical ones.
- This session's compose candidate is more compact (1805 wire length, 2 warnings) but
  **has not been applied**; its driver module is blocked by the D4 off-grid symbol.
- The two approaches are complementary: the parallel session's netport + group-move
  path achieved the real apply; this session's engine produced the independent
  measurement/quality gate and the blocked compose candidate.

## Files

- Snapshots and reports: `evidence/round7/verify/` (external)
- `connectivity.json`, `list.json`, `gate.json`, `lint.json`, `score.json`,
  `clusters.json`, `quality.json`, `sch.svg`, `sch.png`
- PCB: `pcb drc` and `pcb layout-lint` were run read-only on the imported copy.
