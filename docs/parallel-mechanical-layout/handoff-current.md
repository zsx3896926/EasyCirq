# Handoff — task G (parallel mechanical layout planner)

Post-merge reconciliation date: 2026-10-28. Original branch:
`feat/parallel-mechanical-layout` (merged). Original worktree:
`.agents/worktrees/feat/parallel-mechanical-layout` in the local
`hardware-design-skill` checkout. Main baseline:
`9a951edc21481dc3ae91460acc11aa3e08a7be8a`.

Task G itself did **not** merge, release or install anything. Pull request #42 was
merged afterwards by the repository owner; that merge is observed/monitored here,
not an action of this task. This document is corrected by a docs-only follow-up PR
because the earlier revision listed an intermediate docs commit (`cb6e563`) as the
PR head and omitted the actual merged head (`317876c`).

## Delivery identifiers

| item | value |
|---|---|
| pull request | **#42** — https://github.com/zsx3896926/hardware-design-skill/pull/42 — **MERGED** by `@zsx3896926` at `2026-10-27T16:52:58Z` |
| merge commit on main | `ecb4c8a8c5774bdbd54b7c16789029b8fe959a82` |
| original branch | `feat/parallel-mechanical-layout` |
| main baseline | `9a951edc21481dc3ae91460acc11aa3e08a7be8a` |
| verified delivery HEAD | `0ff873c7361d653c9f7ad0d35c39f6df60543018` |
| merged PR head | `317876c0797ad04aaeee7483efb6d5f9c0526f87` |
| this docs correction | branch `docs/mechanical-layout-handoff-head`, follow-up PR (head SHA on that PR page; not merged by task G) |

## Head reconciliation (verified HEAD vs merged PR head)

The two hashes are different because three documentation-only commits landed after
the commit on which the suite and benchmark were executed:

```text
git diff --name-status 0ff873c..317876c
    M   docs/parallel-mechanical-layout/handoff-current.md

git diff --name-only 0ff873c..317876c -- \
    design-hardware/scripts/mechanical_layout tests/mechanical_layout \
    benchmarks/mechanical-layout
    (empty)
```

Therefore the 144-test and 34/34 + 4/4 benchmark results obtained at `0ff873c`
remain valid for the merged head `317876c`: no package, test or benchmark bytes
changed. The earlier revision's statement "PR head at handoff finalization =
`cb6e563`" was stale; the actual merged PR head is `317876c`.

## Commit sequence (verified against actual `git log`)

Original branch `feat/parallel-mechanical-layout` (newest first):

```text
317876c docs: record PR head in task G handoff
cb6e563 docs: finalize task G handoff with PR, HEAD, verification and limits
0ff873c docs: record task G pull request
a608e3e feat: add offline mechanical layout planner and frozen benchmark
9a951ed test: make Chinese fixture portable across Windows locales   (main baseline)
```

On `main` the branch was merged as:

```text
ecb4c8a Merge pull request #42 from zsx3896926/feat/parallel-mechanical-layout
```

A later integration commit on `main`, `a575748 test: make parallel module tests
discoverable; fix frozen-hash and benchmark portability`, moved the tests to
`tests/mechanical_layout_tests/` and added `tests/mechanical_layout_tests/__init__.py`.
That changes the test path and top-level discovery behaviour, but not the
mechanical-layout package or benchmark cases.

## What was delivered

* Offline Python package `design-hardware/scripts/mechanical_layout/`
  (`python -m mechanical_layout`): `validate`, `audit`, `plan`, `explain`.
* G1 board/fixed checks, G2 interface/opening/plug/cable/button/LED checks,
  G3 screw/tool/post/keep-out/insulation checks, G4 2.5D height/interference and
  service-space checks, G5 deterministic bounded candidate generation with
  independent re-audit and explainable objectives.
* Deterministic SVG `top.svg`/`bottom.svg` analysis overlays with the
  `analysis_not_official_export` watermark and mirrored bottom view.
* Frozen CLI benchmark: 34 scenarios + 4 holdouts, SHA-frozen inputs/expected,
  subprocess runner, results with coverage/timing and `real_eda: NOT RUN`.
* Tests under `tests/mechanical_layout_tests/`: 144 unittest cases (contract/units/
  transforms, G1, G3, SVG, benchmark integrity + selected CLI subprocess runs;
  G2/G4 and planner suites were authored inside the parallel team).
* Documentation in `docs/parallel-mechanical-layout/`: `contract.md`,
  `geometry-support.md`, `source-register.md`, `candidate-policy.md`,
  `acceptance-matrix.md`, `report.md`, `integration-proposal.md`, this handoff.
* Vendor facts for three classes: GCT USB4105-GF-A (USB-C receptacle), OMRON
  B3F-1000 (tactile switch, travel), ISO 4762/DIN 912 M3 (mounting screw
  standard). Primary PDFs were opened and text-extracted; the M3 row is
  explicitly marked as a standards compilation, not an OEM drawing.

## Actual commands and results

All commands were run from the worktree root unless noted. Results below are the
observed outputs, not projected ones.

```text
python -m unittest discover -s tests/mechanical_layout_tests -t tests/mechanical_layout_tests
    Ran 144 tests in 1.200s
    OK

python benchmarks/mechanical-layout/run_benchmarks.py
    34/34 passed; results -> benchmarks/mechanical-layout/results.json

python benchmarks/mechanical-layout/run_benchmarks.py --holdout
    4/4 passed; results -> benchmarks/mechanical-layout/results_holdout.json
```

Representative CLI checks (the same commands used for the acceptance evidence):

```text
PYTHONPATH=design-hardware/scripts python -m mechanical_layout audit \
    -i benchmarks/mechanical-layout/cases/pass_panel.json --out <dir>
    exit 0; report.json + top.svg + bottom.svg (watermark
    analysis_not_official_export)

PYTHONPATH=design-hardware/scripts python -m mechanical_layout plan \
    -i benchmarks/mechanical-layout/cases/pass_panel.json --out <dir>
    exit 0; status candidates_found; candidates are only_planned

PYTHONPATH=design-hardware/scripts python -m mechanical_layout plan \
    -i benchmarks/mechanical-layout/cases/plan_budget.json --max-combinations 2
    exit 4; status search_incomplete; G5.SEARCH_INCOMPLETE

PYTHONPATH=design-hardware/scripts python -m mechanical_layout audit \
    -i benchmarks/mechanical-layout/cases/invalid_nan.json --out <dir>
    exit 2; report.json status invalid; old PASS replaced, stale SVG removed

PYTHONPATH=design-hardware/scripts python -m mechanical_layout explain \
    -i benchmarks/mechanical-layout/cases/opening_misaligned.json --finding F0001
    exit 0; rule G2.OPENING_ALIGN, capability G2
```

Determinism and clean-tree replay:

```text
# two runs into separate --out directories
same report.json SHA-256: true; same top.svg SHA-256: true

# git archive HEAD | expand into an empty directory, then rerun there
python -m unittest discover -s tests/mechanical_layout_tests -t tests/mechanical_layout_tests
    Ran 144 tests in 1.269s; OK
python benchmarks/mechanical-layout/run_benchmarks.py
    34/34 passed
python benchmarks/mechanical-layout/run_benchmarks.py --holdout
    4/4 passed
```

The clean-archive replay also proves the frozen benchmark SHA-256 values are
stable for committed bytes (a task-local `benchmarks/mechanical-layout/.gitattributes`
keeps JSON/TXT line endings exact).

After the integration commit `a575748`, the tests live in
`tests/mechanical_layout_tests/` with an `__init__.py`, so the official top-level
`python -m unittest discover -s tests` now discovers and runs all 144 tests.
Task G itself did not change CI; the move was an integration action. The targeted
command above remains the narrow way to rerun only this task's tests. No tracked
file outside the four allowed trees was modified by task G.

## Key evidence

* `audit` statuses: pass / review / fail; `plan` statuses: candidates_found /
  nothing_to_plan / no_candidate_found / search_incomplete / contradiction.
  Exit codes 0/1/2/3/4/5 are documented in `contract.md`.
* Candidate acceptance uses the same `audit_model` path as `audit`; planner score
  is ranking only. Candidate reports are `only_planned`, `executable: false`.
* `z_separate` and the cut-out/notch regressions cover the two required false
  positives/negatives; `mating_datum_offset` covers package-centre ≠ mating datum.
* `mil_units`, `translated_rotated`, `local_frame_equiv`, `unrelated_change`
  cover legal unit conversion, global translation/90° rotation, local frame
  equivalence and irrelevant-object stability.
* Invalid input replaces an older `report.json` with `status: invalid` and
  removes stale SVG views (verified manually).

## Explicit limitations / non-claims

Status flags in every report: `simulated: true`, `real_eda: NOT RUN`,
`full_3d_cad: NOT RUN`, `physical_assembly: NOT RUN`, `manufacturing: NOT RUN`.

* **No EDA, no board change.** No EDA call (including read-only), no connector/
  runtime/protocol/distribution/CI/top-level dependency change, no board write,
  no execution of task A. A plan candidate is never an execution permit.
* **No complete 3D / physical proof.** 2.5D only (XY projection + Z interval);
  no STEP/BREP, curved walls/fillets, flexible cable bending, thread engagement,
  tolerance-chain solver, material strength or assembly validation. Missing
  geometry/height/tolerance is `unknown`, never a silent pass.
* **No EDA-equivalent DRC.** Mechanical formations only; no copper clearance,
  electrical rules, signal integrity, thermal or manufacturing release.
* **Unsupported in v1:** slot holes (rejected, not approximated); top-face
  enclosure openings (v1 opening normal is in XY, so a top-panel button must be
  represented by a side opening or stay `unknown`); arbitrary cable retention.
* **`max_move` is advisory.** `candidate_ranges[].max_move` is normalised but not
  enforced; this is recorded in `candidate-policy.md`, `issue-candidates.md` and
  the planner docstring rather than silently applied.
* **Vendor facts ≠ user measurements.** The GCT/OMRON facts come from actual
  opened vendor documents; the M3 row is a standards compilation, not an OEM
  drawing. The composite/benchmark layouts are synthetic (`provenance.kind =
  synthetic`), not a user project. The tool did not access another computer's
  project, a production system or any client archive.
* **Benchmark scope.** 34 frozen + 4 holdout synthetic CLI scenarios prove
  contract behaviour and named regressions, not that a real product fits.
  Timings in `results*.json` are wall-clock observations and are not part of any
  report identity.
* **Mechanical vs electrical quality.** A mechanically anchored candidate says
  nothing about routing quality or electrical correctness.
* **Distribution.** PR #42 was merged to `main` by the repository owner after this
  task's review; task G did not perform that merge and did not release, install or
  deploy the package. This docs-only correction is a separate follow-up PR and is
  not merged by task G.

## Files touched (all inside the allowed isolation paths)

```text
design-hardware/scripts/mechanical_layout/**            (new package)
tests/mechanical_layout_tests/**                          (new tests; moved from
                                                           tests/mechanical_layout/ by
                                                           integration commit a575748)
benchmarks/mechanical-layout/**                         (cases/expected/holdout/sources/runner/results)
docs/parallel-mechanical-layout/**                      (this task's docs)
```

No file outside those paths was modified; `git status` at delivery shows only
these trees. `SKILL.md`, existing references, README/CHANGELOG/version/handoff,
runtime/connector/protocol, distribution, CI, top-level dependencies, feedback,
compose, design_engine and other task directories were not changed.

## Next steps after review

1. Review the schema/assumptions with the mechanical owner, especially opening
   frames, mating datums and tool declarations.
2. A future adapter should follow `integration-proposal.md`; do not call task A's
   executor from this package.
3. Keep the targeted test command in the maintainer runbook; the integration commit
   already made top-level discovery run the tests. Consider follow-up issues for
   `max_move`, top-face openings and electrical copper keep-out geometry.

## Integration note (2026-10-28, main integrator)

This branch was merged to `main` by the integration lead as
`ecb4c8a8c5774bdbd54b7c16789029b8fe959a82`. The review-time statement that
top-level `python -m unittest discover -s tests` did not descend into the test
directory was accurate at review time and has been fixed on `main`: the tests
moved to `tests/mechanical_layout_tests/` with an `__init__.py` package marker, so
official CI discovery now runs all 144 tests. The mechanical-layout package,
benchmark cases and runner are unchanged by that move.

This follow-up docs-only PR (branch `docs/mechanical-layout-handoff-head`) corrects
three documentation defects from the merge: stale `tests/mechanical_layout_tests_tests`
path strings, an outdated "PR head at handoff finalization" value, and the missing
`verified HEAD` vs `merged PR head` reconciliation. Nothing here is a claim that the
planner was wired into the main schematic/PCB workflow; it remains an independent
capability and no board was changed.
