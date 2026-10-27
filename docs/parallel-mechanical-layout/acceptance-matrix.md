# Acceptance matrix

Evidence collected 2026-10-28 on branch `feat/parallel-mechanical-layout`
(base `9a951edc21481dc3ae91460acc11aa3e08a7be8a`). All runs are offline; no EDA,
no full 3D CAD and no physical assembly. `real_eda = NOT RUN`,
`full_3d_cad = NOT RUN`, `physical_assembly = NOT RUN`.

## Commands actually used

```text
python -m unittest discover -s tests/mechanical_layout -t tests/mechanical_layout
    -> 144 tests, OK
python benchmarks/mechanical-layout/run_benchmarks.py
    -> 34/34 frozen CLI scenarios passed; results.json
python benchmarks/mechanical-layout/run_benchmarks.py --holdout
    -> 4/4 holdout scenarios passed; results_holdout.json
```

Tests run the CLI as a real subprocess and rebuild candidates via the public
`audit_model` path, never via planner-internal scores.

## Capability coverage

| Capability | Positive | Negative / regression | Unknown / boundary |
|---|---|---|---|
| G1 board/fixed | `pass_panel`, `overhang_allowed`, `mil_units` | `hole_near_edge`, `concave_notch`, `overhang_exceeds`, `mating_datum_offset` (datum identity), unit tests for circle overhang and cut-out-spanning body | `no_enclosure` (enclosure missing), missing edge margin unit test |
| G2 opening/plug | `pass_panel`, `composite_panel`, `composite_handheld`, `holdout_connector_pass` | `opening_misaligned`, `opening_angle`, `mating_datum_offset`, `plug_blocked`, `button_travel`, `led_pipe`, `holdout_opening_offset` | `cable_unknown`, unit tests for missing tolerance/plug geometry |
| G3 mounting/tool | `pass_panel`, composites, flush-post unit test | `screw_head_blocked`, `tool_blocked`, `preferred_keepout` (review), post-misalignment unit test | `cable_unknown` not applicable; missing tool unit test, headless-tool unit test, hole keep-out unit test |
| G4 height/interference | `z_separate`, `pass_panel` | `bottom_post_collision`, unit test for real Z collision | `missing_height`, `holdout_height_unknown`, typical-only height unit test |
| G5 candidates | `fixed_plan`, `holdout_plan` | `plan_no_feasible`, `plan_budget`, contradiction path in planner tests | budget/missing-range statuses; unknown coverage is surfaced on candidates |
| Input/coordinate | `mil_units`, `translated_rotated`, `local_frame_equiv`, `unrelated_change` | `invalid_mirror`, `invalid_nan`, `duplicate_ids`, `contradictory`, `snapshot_stale`, self-intersection/negative/bool unit tests | missing frame/rotation/mirror are input errors by contract |

## Frozen CLI scenarios (34)

| Scenario | Command | Status (exit) | Required rule(s) |
|---|---|---|---|
| pass_panel | audit | pass (0) | — |
| composite_panel | audit | pass (0) | — |
| composite_handheld | audit | pass (0) | — |
| opening_misaligned | audit | fail (3) | G2.OPENING_ALIGN |
| opening_angle | audit | fail (3) | G2.OPENING_ANGLE |
| mating_datum_offset | audit | fail (3) | G2.OPENING_ALIGN |
| plug_blocked | audit | fail (3) | G2.PLUG_BLOCKED |
| cable_unknown | audit | review (1) | G2.CABLE_UNKNOWN |
| hole_near_edge | audit | fail (3) | G1.HOLE_EDGE |
| screw_head_blocked | audit | fail (3) | G3.SCREW_HEAD |
| tool_blocked | audit | fail (3) | G3.TOOL_SPACE |
| bottom_post_collision | audit | fail (3) | G4.POST_COLLISION |
| z_separate | audit | pass (0) | — (no G4.COLLISION) |
| missing_height | audit | review (1) | G4.HEIGHT_UNKNOWN |
| concave_notch | audit | fail (3) | G1.OBJECT_INSIDE_BOARD |
| overhang_allowed | audit | pass (0) | G1.EDGE_OVERHANG (advisory) |
| overhang_exceeds | audit | fail (3) | G1.EDGE_OVERHANG |
| preferred_keepout | audit | review (1) | G3.KEEPOUT |
| button_travel | audit | fail (3) | G2.BUTTON_TRAVEL |
| led_pipe | audit | fail (3) | G2.LED_PIPE |
| no_enclosure | audit | review (1) | G4.ENCLOSURE_HEIGHT |
| mil_units | audit | pass (0) | — |
| translated_rotated | audit | pass (0) | — |
| local_frame_equiv | audit | pass (0) | — |
| unrelated_change | audit | pass (0) | — |
| order_deformation | audit | pass (0) | — |
| fixed_plan | plan | candidates_found (0) | — |
| plan_no_feasible | plan | no_candidate_found (3) | G5.NO_CANDIDATE |
| plan_budget | plan | search_incomplete (4) | G5.SEARCH_INCOMPLETE |
| invalid_mirror | audit | invalid (2) | — |
| invalid_nan | audit | invalid (2) | — |
| duplicate_ids | audit | invalid (2) | — |
| contradictory | audit | invalid (2) | — |
| snapshot_stale | audit --snapshot | invalid (2) | — |

## Holdout (4, not referenced by implementation tests)

| Scenario | Command | Status | Purpose |
|---|---|---|---|
| holdout_connector_pass | audit | pass | independent aligned connector geometry |
| holdout_opening_offset | audit | fail G2.OPENING_ALIGN | independent opening offset |
| holdout_plan | plan | candidates_found | independent 2-axis movable search |
| holdout_height_unknown | audit | review G4.HEIGHT_UNKNOWN | independent missing height |

## Named regressions

* **bbox looks fine but a concave notch is crossed**:
  `concave_notch` (benchmark) and the cut-out-spanning-body unit test; both fail
  G1 even though the component bbox is inside the board bbox.
* **package centre aligned but mating datum is not**:
  `mating_datum_offset` fails G2.OPENING_ALIGN while the component pose/body
  centre remains on the opening centre line.
* **projection overlap but Z separated**: `z_separate` passes with no
  G4.COLLISION; a real Z overlap fails in the unit suite.
* **circle overhang**: unit test places a circle centre inside the board whose
  disk leaves the material; it is not a pass.
* **hole full diameter**: hole-edge checks use diameter maximum; unit tests
  cover a disk crossing the edge and a missing margin (unknown).
* **headless tool**: `tool.start.from=head_top` without a screw is an unknown,
  not a verified tool cylinder (unit test).
* **self mounting post**: a flush declared post does not fail its own hole
  (unit test), while a misaligned post fails G3.MOUNT_ALIGN.
* **stale PASS**: `snapshot_stale` exits 2; `--out` invalid handling overwrites
  `report.json` with `status: invalid` and removes stale SVG views (tested by
  manual CLI run; see `report.md`).

## Boundary and deformation checks

* legal `mil` unit conversion produces the same pass conclusion
  (`mil_units`);
* a global translation + 90° board/enclosure frame rotation keeps the pass
  conclusion (`translated_rotated`);
* an equivalent local frame (board moved in world, local coords shifted back)
  keeps the same conclusion (`local_frame_equiv`);
* an unrelated extra component does not change the pass conclusion
  (`unrelated_change`);
* reversing the order of components/holes/interfaces/opening lists keeps the
  mechanical conclusion (`order_deformation` plus the unit-level signature test);
* input SHA-256 changes when the input truly changes; benchmark manifest freezes
  input and expected hashes; the runner rejects stale hashes.

## What this matrix does not prove

* no real PCB was read or modified; no EDA DRC/DRC-like electrical check;
* no complete 3D assembly, no STEP/BREP, no flexible cable, no tolerance stack,
  no thread engagement, no manufacturing or material strength;
* no user project was accessed; every fixture is synthetic and the source facts
  are vendor dimensions only, never user measurements;
* candidate quality is not electrical routing quality, and a `pass` audit is not
  a permission to execute a pose change.
