# Negative case: direct LED2 +2 mm move from the first baseline

This fixture preserves the **first, failed** local-edit input from the
2026-10-27 dual-button LED board. It is not a finished board and must not be
accepted.

- `board-baseline.json`: the first saved baseline, with D3/D4 at y=760 mil.
- `placement-direct-move.json`: the same placement with D4 moved +78.74 mil
  (+2.00 mm) and no other change.
- `expected.json`: the required rejection facts.

At this baseline the gap between D4's top (887.335 mil) and R3's bottom
(960.894 mil) is only 73.559 mil. Moving D4 up by 78.74 mil overlaps R3 by
5.181 mil. The correct response is to **reject the move before writing**, then
re-plan the baseline to reserve headroom (the accepted board moved D3/D4 down
30 mil and rerouted both channels).

Reproduce offline:

```bash
python design-hardware/scripts/design_engine_cli.py pcb-check-plan \
  --dump design-hardware/cases/dual-button-led-night-20261027/negative-direct-move/board-baseline.json \
  --plan design-hardware/cases/dual-button-led-night-20261027/negative-direct-move/placement-direct-move.json \
  --json
# expected: status=review, hard_ok=false, finding=bbox_overlap {D4,R3}

python design-hardware/scripts/check_move_clearance.py \
  --dump design-hardware/cases/dual-button-led-night-20261027/negative-direct-move/board-baseline.json \
  --designator D4 --dy 78.74 --clearance 10 --json
# expected: status=conflict, conflict_designator=R3
```

A clear result from either tool is only a preflight. It does not prove copper
clearance, routing, DRC, silkscreen or a legal write.
