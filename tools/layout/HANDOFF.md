# HANDOFF: offline layout/routing toolchain (agent-facing)

Read this before touching `ec_layout.py`. Everything below is measured, not planned.

## Where the code is

```
tools/layout/ec_layout.py     place / route / report / check  (the pipeline)
tools/layout/check_bus_order.py  bus pin-order planarity + MCU orientation advice
tools/layout/BUNDLE-DESIGN.md    7 measured attempts at equal-length bundles
tools/layout/README.md           KPI definitions, rejected approaches, trade-off table
tests/test_ec_layout.py          8 tests (metrics, legalisation, gate)
tests/test_bus_order.py          3 tests (rho identity, spearman, mirror)
```

Commands:

```bash
python tools/layout/ec_layout.py place  dump.json --iters 40000 --out placed.json
python tools/layout/ec_layout.py route  dump.json --place placed.json --iters 20 --layers 4 --out plan.json
python tools/layout/ec_layout.py check  dump.json --place placed.json --plan plan.json   # exit 1 = do not apply
```

`route` also takes `segment_check=True` (line-segment spacing as a hard constraint),
`priority_nets={...}`, `escape_nets={...}`, `hard_nets={...}`.

## Current measured frontier (RetroCam-02)

| mode | clearance | congestion | unrouted | unconnected | vias |
|---|---|---|---|---|---|
| soft spacing | 26 | 1 | **0** | **5** | 79 |
| `segment_check` + GND-as-pour | **0** (3 GND↔FB need pour rules) | **0** | 5 | 8 | 83 |

Placement: HPWL 71641 → 43301 mil, zero overlaps, zero outside.

## The three bugs already fixed (do not reintroduce)

1. **Stale pads**: `Board.nets` holds copies; `apply_placement` must rebuild it or the
   router uses pre-placement coordinates (this poisoned every metric for ~10 rounds).
2. **Cross-layer occupancy**: bundle occupancy must be keyed `(x, y, layer)`.
3. **`check` zeroing a KPI**: it used to overwrite congestion with 0 before gating.

## Rejected approaches (measured, with numbers, do not retry)

trace width 7/6 (violations unchanged) · pad keep-out +trace/2 (26→32, unconn 5→8) ·
GND on its own layer (26→32) · external rip-up reroute (919 violations) · halo 2 cells
(39, vias 105) · priority-first routing (unrouted unchanged, vias 76→64) · per-net
5 mil width (unrouted 5→6) · fan-out escape band (5→6).

Equal-length bundles: 7 geometries tried, 0–3 of 8 members placed. Root cause is
documented in `BUNDLE-DESIGN.md` (row→column needs a channel allocator; the 97 mil
gap cannot host 8 lanes at legal pitch plus jog headroom).

## Next concrete step

Put **routability into the placement objective**: penalise
`(1 - |rho|)` per bus group (already computed by `check_bus_order.rho_for`) and the
pin-side escape distance, then re-run place → route(segment_check) → check. The five
failing legs (+3V3, GND, BTN_DOWN, BTN_SHUTTER) all fail at the U5 pad column, which
is a placement property, not a router parameter.

## Working discipline for whoever continues

* **Never edit this file's Python with `python -c "..."` under PowerShell.** Quotes
  and backslashes get mangled, the command exits non-zero, and a silent no-op edit
  can be mistaken for a result. Use an editor/`edit` tool, then run the tests.
* Always record `(clearance, congestion, unrouted, unconnected, vias)` together —
  single-number claims have been misleading here.
* `pytest tests/test_ec_layout.py tests/test_bus_order.py` must stay green (11 tests).
