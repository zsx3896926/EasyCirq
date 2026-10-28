# Mechanical layout contract (schema `mechanical-layout/v1`)

Status: task G (parallel mechanical layout planner), first 2D/2.5D implementation.
This contract is enforced by `easycirq/scripts/mechanical_layout/model.py`.
Everything here is offline: no EDA call, no board write, no full 3D CAD.

## 1. Scope and non-goals

The planner answers mechanical anchoring questions before electrical placement:

* does a fixed connector/button/LED line up with a declared enclosure opening;
* is there declared space for a plug, cable route, fastener head and tool;
* do mounting holes keep enough material, and do they meet their posts;
* do component bodies collide in XY **and** Z, and do they fit inside the cavity;
* which bounded poses of the declared movable objects satisfy the hard rules.

It does **not** optimise all resistors/capacitors, route copper, check electronics,
solve a tolerance chain, simulate a flexible cable, or prove a physical assembly.
A candidate is an `only_planned` proposal, never an execution permit.

## 2. Units, coordinates and faces

* `document.units` is `mm`, `mil`, `inch` or `in`; every raw coordinate and
  dimension in that document uses it. Normalisation converts everything to mm
  (including frame origins and Z values). A per-dimension `unit` may override
  the document unit only for that dimension.
* World frame: right-handed XY plane, Z up, rotations CCW in degrees.
* Board frame, enclosure frame, component pose, interface frame and opening
  frame are **all explicit**; a missing `origin`/`rotation_deg` is an input
  error, never silently 0.
* Component transform order: mirror (if declared) → rotate → translate in the
  board frame. Bottom-side components **must** declare
  `pose.mirror = {"axis": "x"|"y", "view": "bottom"}`; a mirror is never
  guessed by negating an angle. Top-side components must not declare one.
* Component local Z points away from the board on its mounting side (up for
  top, down for bottom). `height` is that local positive distance.
* Board top Z is `board.frame.origin[2]`. The board volume is
  `[z_top - thickness.max, z_top]` when the thickness maximum is declared;
  the nominal thickness is used only to place bottom-side components. Board
  thickness `max` is required for a proof about bottom-side parts.
* Enclosure opening frame: origin `[x,y,z]` where X/Y are in the enclosure frame
  and **Z is a world Z**. Local +X is the outward normal, local +Y is the
  opening width direction. The opening is a rectangle in that plane.
* Interface frame origin is the **mating datum**, expressed in component-local
  coordinates. Package centre or component pose must never be substituted for it.

## 3. Dimensions

A dimension is either a number (exact nominal) or an object:

```json
{"nominal": 3.2, "min": 3.1, "max": 3.3, "unit": "mm", "source": "vendor drawing p.4"}
```

Rules:

* `min <= nominal <= max` when present;
* a `nominal`-only object is **typical-only**: both bounds stay unknown, and
  rules report `unknown` instead of using the typical value as a maximum;
* missing bounds are visible in reports; no rule invents a maximum;
* negative dimensions are rejected, Z positions may be negative.

## 4. Document sections

Required top-level keys: `schema`, `document`, `board`, `components`.
Optional: `enclosure`, `holes`, `interfaces`, `constraints`, `provenance`.

* `document`: `id`, `units`, `source`, `snapshot {id, source, content_sha256?}`,
  optional `title`/`revision`.
* `board`: `id`, `frame`, `outline {outer, holes}`, `thickness`. The outline is
  a simple polygon with simple non-overlapping cut-outs; a bbox is never a
  substitute for a concave outline. `outline.holes` are board cut-outs (not
  mounting holes).
* `enclosure`: `id`, `frame`, `cavity {outer, holes}`, `z {bottom, top}`,
  optional `posts`, `ribs`, `openings`, `walls`, `wall_thickness`.
  A post is a circle + `z {min,max}`; a rib/wall is a prism + Z interval.
  `posts[].mounting_hole` and optional `position_tolerance` declare a mounting
  pair. `walls` are optional explicit solid wall pieces; without them the
  wall solid is not claimed to be modelled.
* `components`: `id`, `side` (`top`/`bottom`), `pose {x,y,rotation_deg,mirror?}`,
  optional `library`, `shape`, `courtyard`, `shell`, `pads`, `height`,
  `standoff`, `locked`, `fixed`. A missing `shape` is unknown geometry, not an
  empty part. `standoff` defaults to 0 (flush) and is recorded as an assumption;
  `height` is never defaulted.
* `holes`: `id`, `center` (board frame), `diameter`, `kind`
  (`mounting`/`via`/`tooling`), optional `plated`, `screw`, `washer`, `tool`,
  `mechanical_keepout`, `electrical_keepout`. Slots are rejected in v1 rather
  than approximated silently. `plated` stays unknown when null/omitted.
  `screw.diameter` is the **head** disk diameter in this version (documented
  ambiguity: no separate shaft diameter is modelled).
* `interfaces`: `id`, `kind` (`connector`/`button`/`led`/`other`), `component`,
  `frame`, optional `opening`, `requires_opening`, `alignment`, `plug`, `cable`,
  `button`, `led`.
  * `plug` profile is a rectangle in the interface plane (width × height) plus
    `length` and `clearance`; the envelope starts at the mating datum.
  * `cable.space` is a declared 2.5D free-space volume, not a flexible-cable
    proof.
  * `alignment.max_offset`/`max_angle_deg` override, then
    `constraints.interface_alignment`, then the opening's declared tolerances;
    without any declared tolerance the alignment result is **unknown**.
* `constraints`: `movable`, `fixed`, `board_edge_margin`,
  `component_edge_margin`, `allowed_overhang`, `candidate_ranges`,
  `preferences`, `weights`, `keepouts`, `service_spaces`, `insulation`,
  `interface_alignment`, `max_search_combinations`, `max_candidates`.
  * `allowed_overhang` is the only permission for a body to leave the board;
    each entry has an explicit maximum.
  * `candidate_ranges[].rotations_deg` are the only allowed rotations;
    `positions` or a `region {x:[min,max], y:[min,max], step}` defines the
    bounded search.
  * keep-out/service-space Z intervals are optional for keep-outs (full-height
    2D), required for service spaces.

## 5. Input validation and errors

The loader rejects, with a stable `code`:

| code | example |
|---|---|
| `SCHEMA_MISMATCH` | wrong schema string |
| `INVALID_UNIT`, `INVALID_NUMBER`, `NEGATIVE_VALUE` | unknown unit, NaN/Infinity/bool, negative size |
| `INVALID_SHAPE` | < 3 points, self-intersection, degenerate area, duplicate vertices |
| `INVALID_OUTLINE` | cut-out outside the outer outline or overlapping another cut-out |
| `INVALID_MIRROR` | bottom side without/with wrong mirror declaration |
| `INVALID_SIDE`, `INVALID_ANGLE`, `INVALID_FRAME` | layer/angle/frame errors |
| `DUPLICATE_ID` | duplicate id in a collection or across components/holes/interfaces |
| `DUPLICATE_CONSTRAINT` | two candidate ranges for one object |
| `CONTRADICTORY_CONSTRAINTS` | locked/fixed object declared movable, movable+fixed |
| `UNKNOWN_REFERENCE` | interface/opening/hole/post reference that does not exist |
| `UNSUPPORTED_HOLE` | slot or unsupported hole kind |
| `SNAPSHOT_STALE` | `--snapshot` hash does not match the declared snapshot hash |
| `INPUT_IO`, `INVALID_ENCODING`, `INVALID_JSON` | unreadable/non-UTF-8/invalid JSON |

All file paths are read-only inputs. Outputs go only below `--out`.

## 6. CLI

```
python -m mechanical_layout validate -i input.json
python -m mechanical_layout audit    -i input.json [--out DIR] [--no-svg]
                                     [--groups G1,G2] [--snapshot FILE]
                                     [--expect-snapshot-sha HEX]
python -m mechanical_layout plan     -i input.json [--out DIR] [--no-svg]
                                     [--max-combinations N] [--max-candidates N]
                                     [--snapshot FILE] [--expect-snapshot-sha HEX]
python -m mechanical_layout explain  -i input.json --finding F0001 [--report REPORT]
```

Run with `PYTHONPATH=easycirq/scripts` from the repository root, or from
`easycirq/scripts`. stdout is machine-readable JSON only; errors are also
JSON. `plan`/report JSON has no wall-clock timestamp, so identical input bytes
produce identical bytes.

Exit codes:

| code | meaning |
|---|---|
| 0 | valid input; audit `pass`; plan `candidates_found` or `nothing_to_plan` |
| 1 | audit `review` (unknown coverage or only preferred findings) |
| 2 | invalid input / usage / stale snapshot |
| 3 | audit `fail`; plan `no_candidate_found` or `contradiction` |
| 4 | plan `search_incomplete` (budget or missing candidate range) |
| 5 | `explain` finding not found |

A plan never returns an empty candidate list with a pass status: an empty list
is always paired with `no_candidate_found`, `search_incomplete`,
`contradiction` or `nothing_to_plan`.

## 7. Status semantics and unknown policy

Audit status: `pass` (no hard violation, no hard unknown), `review` (hard unknown
or preferred-only issue), `fail` (hard violation). A preferred constraint never
turns into a fail. Missing data becomes `kind: "unknown"` with a reason; it is
never silently dropped and never counted as zero. `coverage.unknown_checks`
groups unknown finding IDs by capability.

A finding always carries: stable `id`, rule ID, capability, title, kind
(`violation`/`unknown`/`advisory`), severity (`hard`/`preferred`/`info`),
objects, measured value, required value, unit, declared tolerance when known,
evidence, suggestion and a location in the world frame when available.

## 8. Outputs and stale-PASS protection

`--out DIR` writes `report.json` atomically (temp file + `os.replace`) and, unless
`--no-svg`, `top.svg` and `bottom.svg`. Both SVG views carry the watermark
`analysis_not_official_export`, a scale bar and the footer
`Offline 2.5D analysis. NOT an EDA export, NOT a complete 3D assembly.`.
On invalid input with `--out`, the tool overwrites `report.json` with status
`invalid` and removes its stale SVG views, so an old PASS cannot be mistaken for
the current result.

Input identity is the SHA-256 of the input bytes, recorded in every report.
`--snapshot FILE` additionally verifies `document.snapshot.content_sha256`;
a mismatch is a `SNAPSHOT_STALE` input error (exit 2).
