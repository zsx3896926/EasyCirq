# Bundle routing: geometry findings (offline, measured)

Context: `ec_layout.py` route pass gives acceptable congestion (9–11 cells) but bus
length spread is CAM 211 / LCD 573 / SD 754 mil. Three attempts to fix it are
recorded here with the numbers, because the failure is geometric, not parametric.

## Attempts

| # | Approach | Members placed | Spread |
|---|---|---|---|
| 1 | Post-hoc meander compensation (`match_lengths`) | **0 / 8**, 0 / 5, 0 / 4 | unchanged |
| 2 | Whole-corridor translation (`bundle_route`) | 1 / 8, 0 / 5, 0 / 4 | 1513–2658 |
| 3 | Fan-out + channel + fan-in (`bundle_route_fanout`) | 1 / 8, 0 / 5, 0 / 4 | 1529–2608 |
| 4 | Order-preserving L bundle (`bundle_route_ordered`) | 1 / 8, 1 / 5, 0 / 4 | 1472–1705 |
| 5 | Trunk bundle (single trunk, drops behind it) | 1 / 8, 1 / 5, 0 / 4 | 1552–1785 |
| 6 | Channel band clear of pad rows + 45° source staircase (`bundle_route_channel`) | **3 / 8**, 0 / 5, 0 / 4 | 3998 |

Attempt 6 is the first that places more than one member: moving the lane band above
both pad regions and rising into it on a 45° diagonal removed the horizontal-vs-drop
crossing that killed attempts 3–5. Remaining blockers, both visible in the numbers:

* the **dest-side** fan-in is still a straight diagonal to the pad, so it crosses the
  destination pad column (5 of 8 rejected);
* spread jumped to 3998 mil because each dest-side diagonal length depends on that
  member's destination y, so lengths stop being equal by construction.

Next: mirror the source staircase on the destination side (nested by destination y),
then length equality follows from the shared channel between two staircases.

## Why each failed (measured, not guessed)

1. **No room**: after the normal route pass every segment is surrounded by other
   copper, so the free-space gate rejected every meander envelope.
2. **Pitch mismatch**: a bundle pitch of 20 mil translated onto a 50 mil pad pitch
   walks into the neighbouring pad.
3. **Crossing fan-ins**: members share one L-shaped channel; the vertical fan-in of
   member *i* crosses the horizontal run of member *j* (different `y = y_ch + off`),
   which the clearance gate correctly rejects.
4. **Crossing stubs (proved)**: with all sources on one row, a pad's vertical stub
   to lane *k* must pass through every lane below it, and those lanes hold other
   members' horizontal runs. Ordering members by pad position does not remove the
   crossing — it only relabels it. A row→column bundle therefore needs a real
   channel allocator (nested 45° staircase stubs plus lane reservation), which is
   the next piece of work, not a tweak to the current function.
5. **Trunk version, cell-level evidence** (`bundle_route_ordered`, attempt 5):
   all horizontals were made to end at one trunk x with the drops behind it, yet
   member 1 still clashed at cell (92,116) owned by CAM_D0 — its horizontal at
   y=1203 ran through CAM_D0's drop vertical (x=950, spanning y 1178..1400).
   Cause: the destination column (y 1250..1400) lies ABOVE the source row (1153),
   so every drop vertical must cross the lane band that the other members'
   horizontals occupy.

   **Therefore the channel band must be clear of BOTH pad regions** (above the
   highest destination y or below the lowest source y), with the fan-out done as a
   nested 45° staircase so stubs reach the band without crossing lanes. That is the
   geometry the next implementation must build; the two regions cannot overlap.

## The geometry that is actually required

The bus sources are a **horizontal pad row** (J3: y=1153, x step ≈ 20 mil; J4:
y=350, x step ≈ 100 mil) and the destinations are a **vertical pad column**
(U5 left side, 50 mil pitch). A row→column bundle needs a **staircase fan-out**:

1. Each pad leaves along its escape direction (perpendicular to its row/column).
2. Stubs are staggered into distinct lanes (lane k at `y_src + k * pitch`), not kept
   on the pad row — otherwise stub lines overlap each other.
3. The centerline is a polyline (row band → diagonal/orthogonal run → column band);
   each member is the **perpendicular offset of the whole polyline**, never a
   per-member recomputation.
4. Length equality then falls out of the shared polyline; residual skew is levelled
   with a single meander inserted on the shortest member inside the reserved band.

`pad_escape_dirs()` already exists and returns the correct per-pad direction for
both geometries (verified: J3 pads escape vertically as a horizontal row, J5 pads
escape horizontally as a vertical column).

## Next implementation step

Rewrite `bundle_route_fanout` around an explicit centerline polyline plus lane
staggering (points 1–3), then re-run the same three groups and compare spread.
Acceptance: every member placed, spread < 50 mil, `clearance_violations` unchanged.
