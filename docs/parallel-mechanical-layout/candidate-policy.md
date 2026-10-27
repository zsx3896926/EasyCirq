# Candidate policy (G5)

The planner proposes mechanical-anchored poses for **declared movable** objects.
It never writes to a PCB and never claims an assembly is complete. Every record
is `only_planned: true`, `executable: false`.

## 1. What may move

* `constraints.movable` lists component/hole IDs; `constraints.fixed` and
  component `locked`/`fixed` are immovable. Listing the same object in both is
  an input error (`CONTRADICTORY_CONSTRAINTS`).
* A movable object must have exactly one `candidate_ranges` entry. Without a
  bounded range the planner returns `search_incomplete`; it never invents a
  default position or angle. Holes translate only (rotation is not a hole
  degree of freedom; a non-zero hole rotation is ignored with a note).
* `allowed_overhang` is not a licence to move a fixed connector: it only
  explains an existing body overhang.

## 2. Enumeration

Deterministic order:

1. object IDs sorted;
2. declared `rotations_deg` order;
3. declared `positions` order;
4. a `region` grid row-major: x from min to max by `step`, then y, values
   rounded to 6 decimals.

`total_combinations` is the product of the declared option counts. A search
budget (`--max-combinations`, default 20000) counts fully enumerated and audited
combinations. If the budget is exhausted the status is `search_incomplete`,
with `search.budget_exhausted = true`; this is never presented as proof that no
solution exists. Reaching `--max-candidates` early (default 12) stops the
search with `stopped_reason = candidate_limit` and `space_complete = false`.

`max_move` is normalised by the schema but **not enforced** by this first
implementation: the contract does not define how a range option filtered by
`max_move` should count against the search budget. This is reported here and in
the planner module docstring rather than silently applied.

## 3. Hard filtering then ranking

For every combination the planner rebuilds the model and calls
`audit_model(candidate)` — the same G1–G4 rule path as `audit`. Acceptance is
**only** "no hard violation". The score never accepts a candidate. Fixed/locked
poses are checked to be unchanged defensively. A candidate with residual
`unknown` checks is kept but listed as unverified.

Ranking uses explicit raw objectives (all mm, lower cost better), each visible in
`candidate.objectives`:

| objective | definition |
|---|---|
| `alignment_mm` | mean in-plane offset between each interface mating datum and its opening centre |
| `mounting_deficit_mm` | sum of positive deficits between movable-hole material clearance and declared edge margin |
| `insertion_surplus_mm` | minimum opening-fit surplus over interfaces with plug+opening (higher is better) |
| `preference_mm` | declared preference-position distance (positions only; rotation-only preference contributes 0) |
| `movement_mm` | total Euclidean movement from the before pose |
| `weighted_cost` | `w_alignment*alignment + w_mounting*mounting_deficit + w_insertion*max(0,-insertion_surplus) + w_preference*preference + w_movement*movement` |

Default weights are all 1.0 and can be overridden by
`constraints.weights` or the CLI `plan` call. Ties are broken by
`(-insertion_surplus, movement_mm, deterministic move key)`. Candidate
`explanation` is a list of human-readable strings; there is no hidden score.

## 4. Status decision

| status | condition | exit |
|---|---|---|
| `candidates_found` | at least one independently audited candidate | 0 |
| `nothing_to_plan` | no movable objects | 0 |
| `no_candidate_found` | complete space enumerated, no accepted candidate | 3 |
| `search_incomplete` | budget exhausted, or a movable object lacks a range | 4 |
| `contradiction` | no candidate and a hard base-model violation involves only fixed objects | 3 |

`contradiction` names the specific finding(s), e.g. a locked connector whose
mating datum cannot meet an opening. It does not claim a minimal unsatisfiable
core.

## 5. Candidate record

Each candidate contains rank, objectives, score, before/after pose moves with
object identity and kind, an independent audit summary (hard failures must be 0,
unknown rule list, findings checked), and an explanation. Moves bind component
or hole IDs; a zero-movement candidate is allowed when the current pose lies in
the declared range and emits `moves: []`.

## 6. Non-promises

The candidate is not written to a board, not imported into an EDA plan, and not
a permission to execute. Integration with the task-A execution layer is a later,
separately reviewed step (see `integration-proposal.md`). Mechanical-anchored
candidate quality is not a claim about electrical routing quality.
