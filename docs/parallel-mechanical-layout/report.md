# Report, artifacts and evidence

## Commands and schemas

| command | stdout schema | files |
|---|---|---|
| `validate` | `mechanical-layout-validation/v1` | none |
| `audit` | `mechanical-layout-report/v1` | `report.json`, `top.svg`, `bottom.svg` with `--out` |
| `plan` | `mechanical-layout-plan/v1` | `report.json`, `top.svg`, `bottom.svg` with `--out` |
| `explain` | `mechanical-layout-explain/v1` | none |

stdout is JSON only. Reports and SVGs are UTF-8, newline `\n`, deterministically
ordered; `report.json` contains no wall-clock timestamp. Output writes are
atomic (temp file in the same directory + `os.replace`).

## Common report fields

* `schema`, `tool {name, version, command}`;
* `input {path, sha256, bytes, document_id, source, units, snapshot,
  snapshot_check?}` — `sha256` is the SHA-256 of the exact input bytes;
* `target {board, enclosure, component_count, hole_count, interface_count,
  file, units}`;
* `status`, `summary`, `coverage`;
* `findings` — sorted by rule/objects/message and re-identified as
  `F0001`, `F0002`, …;
* `assumptions` — declared modelling assumptions (flush standoff, opening
  frame convention, "unconfirmed facts stay unknown");
* `artifacts`, `limits`.

`limits` always contains `simulated: true`, `real_eda: NOT RUN`,
`full_3d_cad: NOT RUN`, `physical_assembly: NOT RUN`, `manufacturing: NOT RUN`,
the `analysis_not_official_export` watermark and the disclaimer.

## Audit report

`status` is `pass` / `review` / `fail` and is derived only from findings:
hard violation → fail; hard unknown or preferred issue → review; else pass.
`summary` gives counts (violations, unknowns, advisories, hard failures, hard
unknowns, preferred issues). `coverage` records:

* board thickness bound and Z top/bottom;
* cavity presence, posts/ribs/walls/openings counts, cavity Z;
* components total/top/bottom, body geometry count, height-bound count and IDs
  with unknown geometry/height;
* interfaces with plug/cable space, requires-opening IDs;
* holes with hardware/tool IDs;
* `unknown_checks` — unknown finding IDs grouped by capability;
* `rule_counts`, `rules_executed`;
* explicit `not_checked` list (copper clearance, flexible cable, threads and
  tolerance chain, full 3D, safety approval, EDA writes) and
  `approximations` (circle 72-gon, 2.5D Z, courtyard separation).

## Finding fields

`id`, `rule`, `capability`, `title`, `kind` (`violation`/`unknown`/`advisory`),
`severity` (`hard`/`preferred`/`info`), `objects`, `message`,
`location {frame, x, y, z?, object?}`, `measured`, `required`, `unit`,
`tolerance?`, `evidence?`, `suggestion?`, `unknown_reason?`.

A finding with `kind: unknown` means the required check could not be completed
from declared data; it is never a silent pass. A `preferred` finding never
changes the audit status to fail.

## Plan report

The plan report adds:

* `status`: `candidates_found` / `nothing_to_plan` / `no_candidate_found` /
  `search_incomplete` / `contradiction`;
* `audit {status, summary, coverage, assumptions}` for the base model;
* combined `findings` (base G1–G4 + G5) with re-assigned IDs;
* `candidates` — ranked, each with `only_planned: true`, `executable: false`,
  objectives, explanation, before/after moves bound to object IDs and an
  independent audit summary;
* `search` — objects, total/considered combinations, budget, exhaustion,
  completeness and stop reason;
* `contradictions` when the status is `contradiction`;
* top-level `only_planned: true`, `executable: false`.

## Explain

`explain` prints the full finding, the rule contract from `RULE_CATALOG`, the
suggestion, measured/required values, evidence, and (when `--report` is used)
the source report's status and input hash. A hash mismatch between the current
input and the source report is flagged. Exit 5 when the finding ID is absent.

## SVG analysis views

Two views share one scale:

* `top.svg` — `TOP VIEW (+Z)`, world X right, world Y up; only top-side
  components, plug/cable envelopes, openings, keep-outs and service spaces;
* `bottom.svg` — `BOTTOM VIEW (looking from -Z; X mirrored)`, world X is
  mirrored around the view centre by convention, world Y stays up; only
  bottom-side components. The mirror is a viewing transform, not a component
  coordinate change.

Both carry the mandatory diagonal watermark `analysis_not_official_export`, a
scale bar, axes/legend, finding markers (red circle = violation, amber diamond =
unknown), up to three ranked candidate overlays with before ghost/arrow/after and
the footer `Offline 2.5D analysis. NOT an EDA export, NOT a complete 3D assembly.`
SVG is not an EDA screenshot and cannot be used as manufacturing data.

## Stale-PASS protection

If input validation fails and `--out` was given, the CLI writes
`report.json` with `status: "invalid"` and the error code/message, and deletes
`top.svg`/`bottom.svg` it previously produced in that directory. Verified
manually: a directory that held `status: pass` ends with `status: invalid` and no
SVG after an invalid run. A stale snapshot is the same path
(`SNAPSHOT_STALE`, exit 2).

## Benchmark evidence

`benchmarks/mechanical-layout/manifest.json` freezes input and expected SHA-256
values; `run_benchmarks.py` rejects changed bytes unless `--update-hashes` is
explicitly used. `results.json` records status/exit/rule checks and wall-clock
timings; timings are not part of any report identity. `results_holdout.json`
separately records the 4 holdout combinations. All results state
`simulated: true`, `real_eda: NOT RUN`.
