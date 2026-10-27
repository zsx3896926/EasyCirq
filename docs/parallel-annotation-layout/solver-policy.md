# Solver policy

Status: implementation policy for `candidates.py`, `solver.py`,
`baseline.py`, `conflicts.py`.  The solver proposes annotation translations only;
`planner.py` builds the plan and `verify.py` re-checks it independently.

## 1. Candidate generation (K1)

A candidate is one rigid translation of the measured bbox:
`bbox_after = bbox_before + (dx, dy)`.  Rotation, alignment, font size, content,
net, owner and instance identity are preserved by construction; a position that
would need any of them changed is never generated.

- Offsets are on the annotation grid (`constraints.grid`), bounded by the
  annotation and global `max_displacement`; diagonal candidates are on-grid on
  both axes and must still fit the displacement limit.
- Direction filters (`allowed_directions`) and role rules are applied:
  designator/value stay near the owner; free text stays in its declared zone;
  fixed or unsupported roles produce an empty domain.
- Candidates are structurally pre-filtered (usable page, title block, hard
  keep-outs, zone containment, owner distance), then scored by static hard/soft
  findings and ordered by (hard, soft, displacement, direction order).  The
  current pose is always rank 0 when applicable, so a no-op is representable.
- The domain is capped by `max_candidates_per_annotation` and
  `max_total_candidates`; truncation is recorded in `SearchStats`
  (`candidates_truncated`) and never silently hidden.  When the global cap is
  exhausted, remaining movable annotations keep the current-pose candidate, so a
  movable annotation never gets an empty domain just because the budget ran out.
- A candidate that only clears because of an estimated bbox carries a
  "visual review required" rationale; verification then refuses
  `plan_verified`.

## 2. Batch avoidance (K2)

1. **Hard filter first**: page/keep-out/zone, text-text, text-symbol,
   text-wire and owner-association violations are evaluated before any
   readability preference.
2. **Bounded focus**: starting from annotations that currently have a hard
   conflict, the solver expands at most three times to annotations whose current
   bbox lies within a focus annotation's maximum-displacement envelope.  This is
   the local-repair behaviour: everything outside the focus is a frozen obstacle
   and is never moved just to lower a score.
3. **Cluster decomposition**: the focus is split into connected components
   (current hard-conflict edges plus overlapping movement envelopes).  Clusters
   are solved independently; a candidate/assignment is always validated against
   the whole focus and then against the whole page before it can be returned.
4. **Deterministic greedy initialization**: order by domain size, then annotation
   priority/id; keep the current pose when it has zero hard conflicts; otherwise
   choose the candidate with the lexicographic minimum
   `(hard, displacement, rank)`.  No randomness.
5. **Bounded local search**: only when hard conflicts remain.  A move changes one
   annotation's candidate; a move is accepted only on a strict lexicographic
   improvement of `(hard, soft, moved count, total displacement)`.  Neighbours
   are enumerated deterministically and the step budget is a count
   (`max_local_search_steps`), never wall time.
6. **Bounded backtracking**: for still-conflicted clusters, a depth-first pass
   over the annotation order with pruning (`hard < best so far`) searches for a
   globally better assignment.  It stops at `max_search_states` and reports the
   budget, not "no solution".
7. **No independent optima**: the acceptance test is a whole-assignment
   evaluation.  The solver does not choose each annotation's local best and then
   leave a new conflict behind; the `counterexample` fixture and test demonstrate
   exactly that failure mode for the baseline and its absence for the batch
   solver.

## 3. Local repair and stability (K3)

- Input can restrict the run to a cluster (`constraints.scope=cluster`,
  `scope_cluster_ids`, or CLI `--scope-cluster`), and can freeze IDs
  (`constraints.freeze_ids`, CLI `--freeze`).  Frozen/out-of-scope annotations are
  never moved; their remaining conflicts are reported separately
  (`frozen_violations`, `fixed_violations`) and the overall status is `partial`
  rather than pretending the page is clean.
- A clean input returns `noop=true`, zero changes, and `planned_clear`; no
  meaningless write is emitted.
- The same input and tool version produce the same assignment and byte-identical
  plan JSON.  Re-planning an accepted plan (input already at the planned poses)
  is a no-op: the current pose has no hard conflict and is retained.  The test
  suite asserts both properties.
- The solver never moves unrelated annotations: changes are only produced for
  focus members, and metrics report `unrelated_movable_moved` explicitly (always
  empty in the current tests).

## 4. Failure taxonomy and budget (K4)

Per-annotation / overall reasons:

| reason | meaning |
|---|---|
| `no_candidates` | the role cannot move or its domain is truly empty |
| `all_candidates_rejected` | candidates exist but every non-current position is structurally invalid or would not clear a hard conflict |
| `budget_exhausted` | `max_search_states` / `max_local_search_steps` hit with hard conflicts remaining |
| `geometry_uncertain` | the remaining conflict involves an estimated bbox; needs a measured bbox |
| `host_capability_unsupported` | the host/input declares the annotation non-movable (or a net label cannot be detached) |
| `net_label_anchor_not_separable` | net-label text cannot move independently of its electrical anchor |
| `frozen_by_scope` | an explicitly frozen annotation still has a conflict |

- A search failure is **not** reported as mathematical infeasibility.  The plan
  is `partial`/`blocked`, with the blocking objects and a concrete minimal gap
  (allow a larger area, measure the bbox, probe the host, unfreeze the ID) — never
  "shrink the font" or "change the net".
- No page creation, font shrink/hide, content/net change, component move or wire
  reroute is ever used to reach a clear status.
- Every budget is a count.  Wall time/clock/random state is not consulted for a
  decision; the `seed` is recorded for reproducibility even though the search is
  deterministic.

## 5. Baseline (benchmark reference)

`baseline.py` is deliberately naive: process movable annotations one by one in
ID order, choose the locally best candidate against fixed geometry and already
placed annotations, then run a **full** `evaluate_assignment` re-check after each
placement.  It has no focus decomposition, no incremental cache and no
backtracking.  It shares the candidate domain and rule set with the improved
solver, so the benchmark isolates the search strategy.

## 6. Complexity controls

The improved path uses a deterministic uniform-grid spatial index for fixed
texts/components/wires and caches static per-candidate findings per cluster.
`SearchStats`/`Counters` record candidate counts, collision checks, states,
local steps and cluster sizes.  The benchmark shows ~1.20M baseline checks versus
~4.1k improved checks on the real frozen case, with equal-or-better quality.
Those counters are diagnostic, not a substitute for wall clock.
