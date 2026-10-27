# Integration proposal (for a later, separately reviewed step)

This task delivers an offline planner only. It does not call task A's executor,
does not write an EDA project, and does not modify any board. The suggestions
below describe a possible future adapter; until that adapter is implemented and
reviewed, the correct action is to read the candidate and ask the user.

## 1. Existing PCB snapshot → mechanical input

Read-only inspection of `design_engine` was done for this proposal. Its
`geometry.py`/`placement.py` are schematic/rect-oriented and its PCB IR is a
different domain; this task deliberately keeps a separate contract rather than
creating a second main engine. No existing function was changed.

A future adapter should map:

| mechanical field | likely source (must be verified per snapshot version) |
|---|---|
| `board.outline.outer/holes` | measured PCB board outline / cut-outs from a snapshot dump; never a bbox |
| `board.thickness` | stack-up/board spec with min/max; nominal-only must stay typical-only |
| `board.frame.origin` | the snapshot's board origin and Z reference; rotation/units must be explicit |
| `components[].pose` | real placement x/y/rotation/side; no default layer or rotation |
| `components[].shape` | footprint/body courtyard or a declared mechanical body; a courtyard is not a 3D body |
| `components[].height` | vendor/measured height with max; missing max → unknown |
| `holes[]` | NPTH/PTH/mounting holes as circles with finished diameter/tolerance. Slots are not supported in v1 and must not be approximated |
| `enclosure`, openings | user/mechanical files or measured drawings; every unknown stays unknown |
| `interfaces` | mating datum, insertion axis, plug/cable/tool facts from the connector and enclosure drawings |
| `constraints` | fixed/movable declarations, allowed overhang, bounded ranges, keep-outs, service spaces |

The functional mapping is intentionally **not** "copy the schematic layout
engine": the mechanical contract needs polygons, Z intervals and mating frames
that the current models do not carry. Candidate issues for a later cross-team
change (not fixed here, to respect the isolation boundary):

1. a stable snapshot field for component body height + basis (no max → unknown);
2. a stable snapshot field for mating datum and plug envelope, not just
   footprint centre;
3. a top-face opening convention (`normal +Z`) for panel buttons/displays; v1
   only models vertical wall openings;
4. mechanical vs electrical hole keep-out as separate declarations (the schema
   already separates `mechanical_keepout` and `electrical_keepout`; copper
   geometry is not supplied, so electrical clearance stays unknown);
5. a verified restricted pose-move operation in the executor. Until it exists,
   candidates stay plans.

## 2. Candidate → restricted pose plan

If a future integration is approved:

* take one ranked candidate, not the whole list, after the user chooses;
* emit only `moves` with explicit object identity (`component`/`hole` IDs),
  `before` and `after` poses, plus the candidate's audit summary and unknown
  list;
* mark the request `only_planned` → the executor must reject it unless a
  reviewed adapter converts it into its own typed plan with its own preconditions
  (target snapshot hash, fixed-object check, undo record);
* never apply a candidate whose `audit.hard_failures != 0`, whose unknown list
  touches the changed objects without user acknowledgement, or whose base input
  hash no longer matches the executor's live snapshot;
* preserve the before pose as a rollback record. Do not silently expand the
  board, move fixed holes, shrink parts, reduce clearances or relax tolerances to
  make a candidate pass.

## 3. Missing solids/heights

* A component without `shape` contributes unknown coverage; do not treat it as
  absent. Add a courtyard/body only from a footprint or vendor drawing, and a
  height with its max bound.
* If only a typical height exists, keep it typical-only (`nominal`) so the tool
  reports unknown. Do not promote a typical value to a maximum.
* For a connector without a plug/cable model, the tool proves only what was
  supplied (opening size/alignment); it does not claim any cable can be inserted.
* For an enclosure without cavity/wall/openings, opening checks are unknown and
  a top-level review is returned rather than a pass.

## 4. When the user must confirm changes

Ask the user / mechanical owner before:

* changing the enclosure cavity, wall thickness, post positions, opening size or
  panel thickness;
* moving a mounting hole, changing its diameter/tolerance or its NPTH/PTH state;
* changing a connector, its mating datum, the board edge or an allowed overhang;
* declaring a new tool/fastener/washer stack, cable space or service volume;
* accepting a candidate with residual unknown checks (e.g. no plug model, no
  height max, no wall solids).

Never present a candidate as an assembly pass. No physical board, no STEP-based
assembly, no DRC and no manufacturing release was used or produced here.

## 5. Suggested first integration steps

1. write a read-only adapter from an approved snapshot schema to
   `mechanical-layout/v1` plus a mapping report showing every unknown field;
2. run `audit` and triage findings with the user; only then run `plan` with a
   bounded `candidate_ranges`;
3. review the candidate by hand and with the existing mechanical owner;
4. only after an executor pose-move API is verified, implement the restricted
   plan conversion in a separate task with its own tests and rollback.
