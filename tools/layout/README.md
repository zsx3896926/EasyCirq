# EasyCirq offline layout & routing toolchain (`tools/layout/`)

**Mechanism:** never touch the EDA board until the offline toolchain passes the KPI
gate. Any agent can drive this: the inputs are a `pcb dump --include-copper`
snapshot and JSON files; nothing here needs a daemon or an editor write — and
`emit_apply.py` refuses to produce an apply bundle while the gate is red.

## Commands

```bash
# reproduce the current frontier in one command (11-row scorecard + gate verdict)
python tools/layout/reproduce.py --dump dump.json --place placed.json --out-dir out/
#   --profile shared-pour | exclusive-pour | two-layer   (see DECISIONS.md)

# or step by step
python tools/layout/ec_layout.py place  dump.json --iters 40000 --out placed.json
python tools/layout/ec_layout.py route  dump.json --place placed.json \
       --iters 40 --layers 4 --pour GND:4 --pour +3V3:3 --out plan.json
python tools/layout/ec_layout.py check  dump.json --place placed.json --plan plan.json

# compare profiles and mark which are non-dominated
python tools/layout/compare.py --dump dump.json --place placed.json --profiles shared-pour,exclusive-pour

# ask whether a bus can be routed as parallel lanes at all
python tools/layout/bus_capacity.py --dump dump.json --place placed.json

# turn a passing plan into an on-machine bundle (refuses a failing one)
python tools/layout/emit_apply.py plan.json --kpi kpi.json --dump dump.json --out-dir dir/
```

## KPI (single definition, enforced by tests)

| KPI | meaning | target |
|---|---|---|
| `unrouted_legs` | MST edges A* could not complete | 0 |
| `congestion_cells` | (x, y, layer) cells claimed by two nets | 0 |
| `nets_unconnected` | nets whose pads do not form one component | 0 |
| `clearance_violations` | track/track **and via/track and via/pad** pairs too close | 0 |
| `pad_layer_gaps` | pads whose copper is on the wrong layer with no via nearby | 0 |
| `pour_islands` | pour access vias landing in different copper islands | 0 |
| `vias` | layer changes (access / in-pad reported separately) | minimise |
| `total_length_mil`, `diagonal_ratio`, `layer_length_mil` | quality metrics | — |
| `bus_length_spread_mil` | max−min length per CAM/LCD/SD group | < 50 |

Every metric is computed **from the plan**, so `check` judges what would be written
to the board. Several earlier versions had router and checker disagreeing (40 vs
281, 12 vs 0, and a 2D connectivity check that called 72 physically open pads
"connected"); each is pinned by a test.

## Current frontier (RetroCam-02, 4 layers, GND + +3V3 as area pours)

```
unrouted 0 | congestion 0 | unconnected 0 | pad layer gaps 0 | pour islands 0
clearance 121 | vias 178 (59 access, 6 in-pad) | 537 segments
total length 37114 mil | 45-degree share 0.410
bus skew: CAM_D 713 / LCD_ 165 / SD_ 298 mil
```

Five of the six gate items are zero. The two that are not:

1. **clearance 121** — 68 of 178 vias sit too close to other copper (via-track and
   via-pad); the router decides layer changes during the A* search, and every
   attempt to steer that decision (veto, reserve, pre-plan, price in the search,
   post-hoc relocation) either loses legs or makes spacing worse. Only post-hoc
   relocation of *routing* vias helps (−5).
2. **bus skew** — not an implementation gap: `bus_capacity.py` shows the pin order
   of the two ends is uncorrelated (CAM ρ = −0.21 / −0.37, LCD ρ = 0.70), so a
   parallel lane bundle cannot exist. Closing it needs a pinout/stackup decision,
   and the post-hoc meander route is arithmetically impossible (§27 of HANDOFF).

## Verified behaviours worth knowing

* **A plan can be complete and still open.** `pad_layer_gaps` exists because a 2D
  connectivity check called 72 physically open pads connected.
* **A pour is not a plane.** Reserving a whole layer for GND cost more signal
  capacity than the 41 GND legs it removed; an area pour that shares the layer wins
  (unrouted 10 → 4 before later gains).
* **`check` never passes a KPI it could not measure** — unmeasured prints `null`
  and fails the gate.
* **Two vias in one cell is a short**, not a spacing nit; it is a hard invariant even
  when "best effort" routing accepts spacing violations.

## History (kept because these were measured, not guessed)

* `gradient.py`: six hard-lock escalation steps — no step satisfied
  `clearance <= 5` and `unrouted = 0` simultaneously.
* Rejected: 7/6 mil widths, inflated pad keep-out, GND on a dedicated layer,
  external rip-up + single-shot reroute (919 violations), wider spacing halo,
  failing-net-first routing, 5 mil narrow legs, wide-ring access-site ranking,
  pre-planned access vias, via-pressure pricing, four net orderings,
  pair-wise rip-up (both blocking modes). Details and numbers in `HANDOFF.md`
  §10–§31.
* `BUNDLE-DESIGN.md`: seven geometric bundle attempts, 0–3 of 8 lanes landed.

## Scripts kept for reference

`ec_repair.py`, `gradient.py`, `debug_*.py` hold the exploration helpers used while
measuring the trades above. `sweep_placement.py` re-runs placement-weight sweeps.



