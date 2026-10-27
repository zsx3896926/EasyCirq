# Geometry support and limits

## Supported primitives

| primitive | schema | notes |
|---|---|---|
| rectangle | `{"kind":"rect","center":[x,y],"size":[w,h],"rotation_deg":d}` | local rotation before the frame transform |
| circle | `{"kind":"circle","center":[x,y],"radius":r}` | exact for containment/boundary distance; circumscribed 72-gon for polygon intersection |
| simple polygon | `{"kind":"polygon","points":[[x,y],...]}` | at least 3 points, non-degenerate, no self-intersection, no duplicate vertices |
| board outline | `outline.outer` + `outline.holes` | concave outer boundary and cut-outs are supported; bbox is not used as a substitute |
| enclosure cavity | same outline structure | inner cavity projection |
| posts | circle + Z interval | cylinder in 2.5D |
| ribs/walls/keep-outs/service spaces | shape + Z interval | extruded prism |
| plug/cable envelope | rectangle/profile + Z interval | conservative 2.5D volume derived from the declared datum |

## Operations

* point-in-polygon (boundary inclusive) and strict point-in-polygon;
* segment intersection, proper crossing, segment distance, polygon
  intersection, containment, boundary distance;
* circle-polygon intersection and circle containment (exact radius), circle as
  circumscribed 72-gon only for the generic polygon intersection path;
* polygon self-intersection and duplicate-vertex validation;
* 2.5D interference: projection overlap **and** a strictly positive Z overlap
  (a shared face alone is not a collision);
* explicit interval gap/overlap and projection gap for evidence values.

## Coordinate transforms

`Frame(origin=[x,y,z], rotation_deg, mirror?, parent)` applies mirror → rotation
→ translation. Composition is explicit; a frame has no implicit defaults. Two
nested mirrors are rejected rather than composed into an undeclared rotation.

## Tolerance policy

* No global epsilon is used to erase a collision. Geometric predicates use
  `1e-9` only for floating-point comparison, while declared tolerances and
  clearances come from the document and are reported in the finding.
* Hole-edge checks use the **maximum** hole diameter (which already includes the
  declared diameter tolerance) plus the declared edge-margin maximum. The size
  tolerance is not counted twice.
* Clearance checks use declared max/min bounds; a missing bound makes the check
  `unknown` instead of silently using nominal.
* Interference uses positive Z overlap (`> 1e-6 mm`) so a component sitting on
  the board surface is not reported as penetrating the board.

## Deliberately unsupported / unknown

* STEP/BREP, curved walls, fillets, draft, screws as helices, threads and
  tolerance stack-up;
* slot holes (rejected as `UNSUPPORTED_HOLE`, not approximated);
* flexible cable bending, retention force, connector mating force;
* top-face (`+Z`) enclosure openings: the v1 opening model is a vertical wall
  opening with an XY normal. A top-panel button must therefore be represented by
  a side opening or left as `unknown`; the tool does not invent a normal.
* electrical copper clearance (no copper geometry is supplied);
* full 3D assembly, physical fit, manufacturing release.

## Numerical behaviour

All coordinates are finite floats in mm. Normalised values are not rounded
before rules run; report evidence values are rounded to 6 decimals. Candidate
positions are rounded to 6 decimals for deterministic ordering. A determinism
test compares report bytes and SVG bytes across repeated runs.

## Circle approximation trade-off

Containment and edge-distance questions use the exact circle. Generic
polygon-intersection questions use a **circumscribed** 72-gon (effective radius
`r / cos(pi/72)`, about 0.1% larger), so the approximation can only make a
collision slightly conservative, never hide one. The approximation is recorded
in `coverage.approximations`.
