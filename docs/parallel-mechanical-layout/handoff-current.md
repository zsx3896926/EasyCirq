# Handoff — task G (parallel mechanical layout planner)

Date: 2026-10-28. Branch: `feat/parallel-mechanical-layout`.
Worktree: `.agents/worktrees/feat/parallel-mechanical-layout` in the local
`hardware-design-skill` checkout.
Base commit / main baseline: `9a951edc21481dc3ae91460acc11aa3e08a7be8a`
(the task's "main baseline SHA"). Independent pull request:
<https://github.com/zsx3896926/hardware-design-skill/pull/42>.
This branch is **not** merged and must not be merged or released by this task.

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
* Tests under `tests/mechanical_layout/`: 144 unittest cases (contract/units/
  transforms, G1, G3, SVG, benchmark integrity + selected CLI subprocess runs;
  G2/G4 and planner suites were authored inside the parallel team).
* Documentation in `docs/parallel-mechanical-layout/`: `contract.md`,
  `geometry-support.md`, `source-register.md`, `candidate-policy.md`,
  `acceptance-matrix.md`, `report.md`, `integration-proposal.md`, this handoff.
* Vendor facts for three classes: GCT USB4105-GF-A (USB-C receptacle), OMRON
  B3F-1000 (tactile switch, travel), ISO 4762/DIN 912 M3 (mounting screw
  standard). Primary PDFs were opened and text-extracted; the M3 row is
  explicitly marked as a standards compilation, not an OEM drawing.

## Actual verification commands and results

Run from the worktree root:

```text
python -m unittest discover -s tests/mechanical_layout -t tests/mechanical_layout
    Ran 144 tests ... OK

python benchmarks/mechanical-layout/run_benchmarks.py
    34/34 passed; results.json

python benchmarks/mechanical-layout/run_benchmarks.py --holdout
    4/4 passed; results_holdout.json

PYTHONPATH=design-hardware/scripts python -m mechanical_layout audit \
    -i benchmarks/mechanical-layout/cases/pass_panel.json --out /tmp/out
    exit 0, report.json + top.svg + bottom.svg with watermark
```

The test suite does not descend into `tests/mechanical_layout` from top-level
CI discovery (no `tests/__init__.py`, by isolation rule). Use the targeted
command above; the package entry point has no effect on the existing CI.

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

* No EDA call (including read-only), no board change, no connector/runtime/
  protocol/distribution/CI/top-level dependency change.
* No full 3D CAD/STEP, no flexible cable, no threads/tolerance-chain solver, no
  top-face enclosure opening, no slot holes. Missing data stays `unknown`.
* The vendor dimensions are design inputs, not user-project measurements. The
  composite cases are synthetic (provenance kind `synthetic`).
* `candidate_ranges[].max_move` is normalised but not enforced (documented in
  `candidate-policy.md` and the planner docstring).
* G2/G4 and the planner were implemented in the parallel team; their modules are
  included here and pass the frozen CLI suite. Lead-owned code is model/geometry/
  solids/findings/audit/report/CLI/SVG, G1/G3, benchmarks, tests and docs.

## Files touched (all inside the allowed isolation paths)

```text
design-hardware/scripts/mechanical_layout/**            (new package)
tests/mechanical_layout/**                              (new tests)
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
3. If merged, add the targeted test command to the maintainer runbook rather than
   changing CI in this task. Consider a follow-up issue for `max_move`, top-face
   openings and electrical copper keep-out geometry.
