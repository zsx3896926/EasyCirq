# Acceptance matrix

Scope: offline annotation-pose planner only.  A checked box means the claim is
backed by a reproducible command/test in this branch, not by an EDA run.  EDA
apply, save/reopen, official export and connectivity readback remain **NOT RUN**.

Implementation: `easycirq/scripts/annotation_layout/` ·
Tests: `tests/annotation_layout/` · Benchmark: `benchmarks/annotation-layout/`

## 1. Capability matrix (K1–K5)

| capability | positive | negative / rejection | unknown / limitation | evidence |
|---|---|---|---|---|
| K1 candidate generation | on-grid, bounded, role-aware candidates; deterministic order; current pose always representable | fixed/unsupported roles produce empty domain; structural escapes discarded; over-limit domains truncated | estimated bbox candidates marked "visual review required"; rotation/align/font preserved by construction | `tests/annotation_layout/test_conflicts_candidates.py::test_candidate_generation_is_bounded_on_grid_and_rigid`, `test_candidate_domains_for_fixed_and_unsupported_roles`, `test_candidate_truncation_is_recorded` |
| K2 batch avoidance | real page: 3 blocking conflicts → 0 with 2 minimal moves; dense/text-text/text-wire/rotated/zone/title-block cases clear | no-candidate and unsupported cases return `blocked`, not a fake fix | symbol outlines are bbox approximations; checker keeps its own thresholds | `tests/annotation_layout/test_solver.py::test_real_frozen_case_clears_all_three_conflicts`, `test_cli_scenarios.py::test_12_to_21_scenario_plans` |
| K2 batch vs per-annotation | batch clears a case where greedy introduces a new conflict | greedy's introduced conflict is asserted, not hidden | fixture is synthetic; no real-board claim | `tests/annotation_layout/test_counterexample.py`, `benchmarks/annotation-layout/cases/counterexample.json` |
| K3 freeze/local repair | frozen annotation not moved; other conflict may still clear; scope cluster freezes the other cluster | remaining frozen/out-of-scope conflicts reported as `partial`, never `planned_clear` | out-of-scope remaining hard findings are classified `out_of_scope` in verification | `test_solver.py::test_frozen_annotation_is_not_moved`, `test_scope_restriction_leaves_other_cluster_untouched`, CLI scenarios 27–28 |
| K3 no-op & stability | clean input → `noop`, 0 changes; re-planning an accepted plan → noop; CLI byte-identical on repeat | no meaningless writes | n/a | `test_solver.py::test_noop_on_clean_input`, `test_replanning_an_accepted_plan_is_a_noop`, `test_cli_scenarios.py::test_31_plan_is_deterministic_at_cli_level` |
| K4 budget/failure taxonomy | budget case returns `partial` + `budget_exhausted`; no-candidate vs all-rejected distinct; unsupported net label distinct | search failure never reported as mathematical infeasibility; no page/font/net workaround | budget limits are counts, not time | `test_solver.py::test_budget_exhaustion_is_reported_not_infeasible`, `test_candidates_rejected_is_distinct_from_no_candidates`, `test_net_label_anchor_separation_unsupported`; synthetic `budget-exhausted.json`, `no-candidates.json`, `net-anchor.json` |
| K5 independent verification | real plan `plan_verified`; independent brute force + unchanged `sch_layout_check.analyze`; before/after findings retained; introduced conflict → `plan_rejected` | checker unavailable is recorded and never faked; non-rigid plan → `verify_invalid`; stale plan hash → exit 2 | checker skips wire checks for symbol-owned attribute texts; analysis SVG is not an official export; no visual pass | `test_verify_svg.py::*`; `test_cli_scenarios.py::test_29/30`; real case report in `benchmarks/annotation-layout/result.json` |

## 2. Contract and CLI requirements

| requirement | status | evidence |
|---|---|---|
| versioned JSON input + strict rejection of NaN/inf/bool/duplicate IDs/unknown units/unknown keys | done | `test_schema_geometry.py::SchemaTest::test_invalid_cases_are_rejected_with_reasons`, `test_bool_is_not_a_number`, `test_duplicate_json_key_is_rejected`, `test_unknown_top_level_key_rejected` |
| snapshot/source hash binding + stale evidence rejection | done | `test_counts_and_source_binding`, `test_stale_source_hash_is_rejected`, CLI verify stale plan test |
| `python -m annotation_layout validate/plan/verify/benchmark/convert/version` | done | CLI scenarios 1–36 |
| stdout = one pure JSON document; stderr diagnostics; UTF-8; deterministic ordering | done | `test_cli_scenarios.py::test_10_plan_real_fixture_stdout_is_pure_json`, `test_31_plan_is_deterministic_at_cli_level` |
| atomic output; no stale PASS after invalid input | done | `test_11_plan_writes_plan_report_and_analysis_svg` (no `.tmp` left), `test_33_invalid_input_does_not_leave_old_pass_output` |
| exit codes 0/1/2 | done | CLI tests (0 clear, 1 partial/blocked, 2 invalid/usage) |
| analysis SVG before/after, marked `analysis_not_official_export`, basic renderability | done (XML/geometry check) | `test_verify_svg.py::SvgTest`; raster preview **NOT RUN** (no rasterizer used) |
| machine plan + short Markdown report with input hash, coordinate convention, candidates/budgets, hard/unknown/displacement, changed/unrelated, checker result, host NOT RUN | done | `benchmark-report.md`, plan JSON `report.md`; CLI test 11 |
| no network/EDA execution, no source-file execution, inputs read-only | done | offline runs only; no network code; input files never opened for write (CLI `_ensure_distinct`) |

## 3. Test inventory required by the task

| requirement | count / status | evidence |
|---|---|---|
| ≥24 actual CLI scenarios | 36 CLI test methods; ≥50 real subprocess invocations (6 invalid sub-cases, 10 scenario plans, scope/freeze/verify/benchmark/convert) | `tests/annotation_layout/test_cli_scenarios.py` (all run the real `python -m annotation_layout`) |
| positive/negative/unknown per capability | covered | section 1 above |
| ≥4 holdout cases with authored expectations | 4 (`holdout-chain`, `holdout-rotated-cn`, `holdout-title-zone`, `holdout-unsupported`) | `fixtures/holdout/expectations.json`, `test_holdout.py` |
| counterexample proving per-annotation moves create a new conflict | done | `test_counterexample.py`; baseline introduced conflict, improved introduces none |
| metamorphic: order / translation / unit scale / grid / extra zone | done (6 tests) | `test_metamorphic.py`; hashes change honestly, relative/hard constraints stable |
| ≥24 input SHAs fixed | fixture `MANIFEST.json` + benchmark `cases/MANIFEST.json`; tests re-hash | `test_manifest_matches_committed_fixtures`, `test_convert.py` |
| benchmark not only internal calls; re-runs the actual entry | wrapper runs `python -m annotation_layout benchmark`; CLI round trip subprocess in result | `benchmarks/annotation-layout/run_benchmark.py`, `command.txt`, `result.json.cli_round_trip` |
| same input/candidate set/constraints quality gate | done; counterexample explicitly not claimed | `benchmarks/annotation-layout/README.md`, `benchmark-report.md` |
| real frozen photo-led case | done, SHA-bound, 3 conflicts → 0 | `fixtures/photo-led-v14/`, real row in `result.json` |

## 4. Explicitly NOT RUN / not claimed

- EDA host write, batch apply, save, reopen, official export/render, connectivity
  re-read, ERC/netlist readback, whole-board wall time.
- Visual/raster inspection of the analysis SVGs (XML/geometry validation only;
  raster preview NOT RUN).
- Any host capability probe (attribute/free-text/net-label movement was not
  executed in EasyEDA); `host.capability_source` says "not probed".
- Whole-page component placement, wire rerouting, font rendering engine, OCR,
  visual model service.
- Cross-machine timing comparison; small synthetic timing ratios are noisy and
  are not generalised.

## 5. Known limitations carried into the plan JSON

- symbol bodies are conservative rectangles;
- the checker skips wire checks for texts owned by a symbol (attribute texts),
  so the independent brute-force recheck is the authority for those;
- a text with only an estimated bbox can never reach `plan_verified`;
- the real fixture's attribute rotation/alignment/font are unknown, so pose
  changes are translation-only and the analysis overlay draws bboxes, not glyphs;
- a frozen/unsupported conflict is reported as `partial`/`blocked` even when the
  rest of the page is clean.
