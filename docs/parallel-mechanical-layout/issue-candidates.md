# Cross-team issue candidates (not fixed in task G)

Task G stayed inside its isolation paths. These are candidate changes for a
future, separately reviewed task; none were applied here. They are recorded so
the findings are not lost and no second main engine is created.

1. **Snapshot mechanical facts are incomplete.** The existing PCB IR/placement
   models expose footprint centre/size but not a body height with max bound, a
   connector mating datum, a plug envelope or cable bend space. A future
   integration needs stable snapshot fields (with unknown allowed) rather than a
   second parser guessing them. Owner: tasks A/F + snapshot contract maintainer.
2. **No verified restricted pose-move operation.** `design_engine.placement`
   returns a translation plan and documents that no verified PCB component-move
   operation exists. A candidate from G5 must stay `only_planned` until an
   executor can accept a typed, preconditioned move with rollback. Owner: task A.
3. **Top-face enclosure openings have no convention.** G2 v1 models wall
   openings with an XY normal. Panel buttons/displays/LEDs on the top face need
   a declared normal-Z opening contract and a 2.5D/3D treatment. Owner:
   mechanical/enclosure reference maintainer.
4. **Electrical copper keep-out geometry is absent.** The schema separates
   `mechanical_keepout` and `electrical_keepout`, but no copper/pad layer data is
   supplied. G1 reports the electrical keep-out as unknown rather than claiming
   electrical clearance. Owner: electrical review (task B) + snapshot provider.
5. **Tool/fastener envelope convention.** `screw.diameter` is currently the head
   disk diameter; shaft diameter, washer stack and driver envelope are separate
   declarations. A shared mechanical-hardware vocabulary would prevent two teams
   from meaning different things. Owner: mechanical reference/placement docs.
6. **`max_move` semantics.** The planner normalises `candidate_ranges[].max_move`
   but does not enforce it because the budget-filtering contract is undefined.
   Define whether filtered options count against the search budget, then enforce
   it in a follow-up. Owner: G5 follow-up.
7. **Benchmark integration command.** The new tests live under
   `tests/mechanical_layout_tests_tests/` (no package marker, by isolation rule), so
   top-level CI discovery does not run them. If this branch is accepted, add the
   targeted command to the maintainer runbook/CI in a separate approved change;
   do not silently change CI here.

No existing geometry/placement/intent function was modified by task G.
