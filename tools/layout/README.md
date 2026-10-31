# EasyCirq offline layout & routing toolchain (`tools/layout/`)

**Mechanism:** never touch the EDA board until the offline toolchain passes the KPI
gate. Any agent can drive this: the inputs are a `pcb dump --include-copper`
snapshot and JSON files; nothing here needs a daemon or an editor write.

## Commands

```bash
# 1) place: layout for routing (HPWL annealing + deterministic legalisation)
python tools/layout/ec_layout.py place  dump.json --iters 40000 --out placed.json

# 2) route: negotiated congestion routing (PathFinder-style, 45° moves, vias)
python tools/layout/ec_layout.py route  dump.json --place placed.json \
       --iters 25 --layers 4 --out plan.json

# 3) gate: judge the plan exactly as it would be applied
python tools/layout/ec_layout.py check  dump.json --place placed.json --plan plan.json
# exit 0 = all KPI clean, exit 1 = do NOT apply this plan to the board
```

## KPI (single definition, enforced by tests)

| KPI | meaning | target |
|---|---|---|
| `unrouted_legs` | MST edges A* could not complete | 0 |
| `congestion_cells` | (x, y, layer) cells claimed by two nets | 0 |
| `nets_unconnected` | nets whose pads do not form one component in the plan | 0 |
| `clearance_violations` | segment pairs closer than rule (width/2 + 6 mil) | 0 |
| `vias` | layer changes | minimise |
| `total_length_mil` | sum of track length | minimise |
| `hpwl_mil` | placement wirelength proxy | minimise |
| `diagonal_ratio` | share of length on 45° segments | higher is better |
| `layer_length_mil` | length per copper layer | balanced |
| `bus_length_spread_mil` | max−min length inside CAM/LCD/SD groups | < 50 |

All metrics are computed **from the plan**, so `check` measures what will be written
to the board. Three earlier versions had the router and the checker disagree (40 vs
281, 12 vs 0); each is now pinned by a test in `tests/test_ec_layout.py` (8 tests).

## What works today (measured on RetroCam-02)

* Placement: HPWL 71641 → **43301 mil** (−40 %), overlaps 0, outside 0.
* Routing: 0–3 unrouted legs, congestion **9–11** cells, clearance **39–44**,
  vias **90**, `diagonal_ratio` **≈0.40**.
* Gate correctly returns FAIL for the numbers above.

## Known gaps (do not claim these work)

1. **Length matching is not achieved.** Bus spread CAM 211 / LCD 573 / SD 754 mil.
   Three approaches failed: post-hoc meanders (0 placed — board is full), whole
   corridor bundle translation (1–2 of 8 placed), fan-out bundle (1 of 8). Cause:
   the fan-out must leave each pad along its **pin escape direction** (J3 pads are
   50 mil apart, so a vertical fan-out immediately hits the neighbour pad).
2. **Clearance 39–44 remains**, concentrated at 0.5 mm-pitch parts (U1/U5/J3);
   these need pad-escape vias, not cost tuning.
3. **3 unrouted legs / 6–7 unconnected nets** survive the negotiated pass.
4. Not implemented at all: differential pairs, impedance/return-path checks,
   power-plane planning, test points, silkscreen/assembly checks.

## Next concrete steps

1. Pad-escape table (per footprint: which direction each pad may leave) and use it
   for both normal routing and bundle fan-out.
2. Bundle routing on top of that: fan-out → parallel run → fan-in, with equal
   length by construction.
3. Rip-up & reroute the 3 stuck legs, then re-gate.

## Measured trade-off: clearance vs connectivity (do not re-litigate)

Six escalation steps, each a fresh negotiated route (`tools/layout/gradient.py`,
15 iterations, hard-locking the worst offenders two at a time):

| step | nets hard-locked | clearance | unrouted legs | unconnected nets | vias |
|---|---|---|---|---|---|
| 0 | 0 (all soft) | 26 | **0** | **5** | 79 |
| 1 | 2 | 31 | 2 | 7 | 68 |
| 2 | 4 | 15 | 6 | 10 | 69 |
| 3 | 6 | 11 | 8 | 12 | 65 |
| 4 | 8 | 13 | 9 | 14 | 60 |
| 5 | 10 | **9** | 12 | 15 | 57 |

No step satisfies `clearance <= 5` and `unrouted = 0` at the same time. Spacing as a
cost leaves too many violations; spacing as a hard lock breaks connectivity. The
gate therefore cannot be turned green by tuning widths, layer assignment or the
hard/soft mix — that was tried and measured. The structural change still missing is
**line-segment-level spacing inside the router** (reject a parallel run closer than
6 mil during the search, accelerated with a spatial grid), and on top of it the
channel allocator described in `BUNDLE-DESIGN.md`.

Also measured and rejected: trace width 7/6 mil (26 violations unchanged — they are
not width-driven), pad keep-out inflated by trace/2 (clearance 26 -> 32, unconnected
5 -> 8), GND on a dedicated layer (26 -> 32), external rip-up + single-shot reroute
(919 violations — the repair path destroys the negotiated solution), a wider spacing
halo of 2 cells (clearance 39, unconnected 6, vias 105), priority-first routing of
the failing nets (unrouted unchanged at 7, vias 76 -> 64), and a per-net narrow
width of 5 mil for the failing legs (unrouted 5 -> 6: narrowing a leg makes the
SPACING demand on its neighbours worse, it does not create space).

## Current frontier with segment-level spacing (the working direction)

| mode | clearance (track↔track) | congestion | unrouted | unconnected | vias |
|---|---|---|---|---|---|
| soft spacing (baseline) | 26 | 1 | **0** | **5** | 79 |
| segment_check, GND treated as pour | **0** (3 GND↔FB need pour rules) | **0** | 5 | 8 | 83 |

The remaining 5 legs (+3V3, GND, BTN_DOWN, BTN_SHUTTER) all fail at the U5 pad
column; the only untried remedy is a **fan-out via band** outside the module edge,
which is what a real engineer does on a dense 100 mil pad row.

## Scripts kept for reference

`ec_repair.py` holds the earlier repair-pass helpers (clearance pairs, cell
ownership) used while exploring the soft-vs-hard spacing trade-off.
