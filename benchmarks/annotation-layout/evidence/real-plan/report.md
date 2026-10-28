# annotation-layout plan report

**status**: `planned_clear`

- schema: `annotation-layout/v1`
- tool: `annotation_layout` `0.1.0`
- input sha256: `207762af8f5b976642c84f69cafe214488f95b9b5035f00ad9deba2c6eb32da9`
- page: `cd008f919db36eba` (P1) project `photo-led-5v-20261026`
- coordinates: {'name': 'easyeda-schematic-raw-y-up', 'y_axis': 'up', 'svg_y_axis': 'down', 'transform': 'source SVG text bbox is flipped once by negating y (svg_y = -raw_y); analysis overlays use screen_y = page_height - raw_y'}
- host execution: **NOT RUN** (`not_executed`)
- verification: `plan_verified`

Analysis overlays (`before.svg` / `after.svg`) are labelled `analysis_not_official_export`: they are geometry overlays, not an EDA export and not a visual acceptance test.

## Metrics

| metric | value |
| --- | --- |
| moved annotations | 2 |
| total displacement (raw) | 10.0 |
| hard conflicts before | 3 |
| hard conflicts after | 0 |
| unknown conflicts | 0 |
| soft findings before | 9 |
| soft findings after | 11 |
| candidates generated | 640 |
| candidates truncated | 1421 |
| collision checks | 5951 |
| fixed violations | 0 |
| unrelated movable moved | [] |
| search budget exhausted | False |

## Changes

| id | role | content | dx | dy | before bbox | after bbox |
| --- | --- | --- | --- | --- | --- | --- |
| 8bd5a6b179fa7148 | value | 10kΩ | 0.0 | -5.0 | [290.0, 348.0, 311.107666015625, 358.0] | [290.0, 343.0, 311.107666015625, 353.0] |
| ad6ce27bf74e95f9 | free_text | GL5528与4.7k分压，C4滤波；光照越强电压越高 | 0.0 | 5.0 | [42.0, 759.5, 289.265625, 771.5] | [42.0, 764.5, 289.265625, 776.5] |

Every change asserts content/net/font/rotation/alignment/owner unchanged and forbids component/wire edits.

## Independent verification

| check | before | after |
| --- | --- | --- |
| independent hard | 3 | 0 |
| independent soft | 9 | 11 |
| checker blocking | 3 | 0 |
| checker informational | 5 | 6 |

- checker: `ran` (unchanged sch_layout_check.analyze)
- introduced hard findings: 0 (independent) / 0 (checker)
- remaining movable hard findings: 0 (independent) / 0 (checker)
- electrical assertion: electrically, this is a structural assertion only: this plan contains no content/net/wire/component change; host connectivity readback, save/reopen and official export are NOT RUN

## Limitations / NOT RUN

- offline planning only: no EDA call, no host write, no save/reopen, no official export
- text bboxes are measured from the frozen official SVG; glyph rendering is not re-run
- symbol bodies are conservative rectangles; shape-accurate outlines are not checked
- free-text and net-label host capabilities were not probed in this environment
- plan clearance uses the declared constraints; the existing checker is called unchanged, never with edited thresholds or ignore lists
- a search failure is not a proof of mathematical infeasibility
- visual/raster inspection: NOT RUN unless separately recorded
- EDA apply, save/reopen, official export, connectivity readback: NOT RUN
