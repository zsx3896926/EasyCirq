# EasyCirq offline layout & routing toolchain (`tools/layout/`)

**Read [`STATUS.md`](STATUS.md) first** — current numbers, the three red lines with
their evidence, the decisions on record, and what is not worth retrying.

**Mechanism:** never touch the EDA board until the offline toolchain passes the KPI
gate. Any agent can drive this: the inputs are a `pcb dump --include-copper`
snapshot and JSON files; nothing here needs a daemon or an editor write — and
`emit_apply.py` refuses to produce an apply bundle while the gate is red
(`acceptance.py` proves that refusal in under a minute).

## Commands

```bash
# reproduce the current frontier in one command (11-row scorecard + gate verdict)
python tools/layout/reproduce.py --dump dump.json --place placed.json --out-dir out/
#   --profile shared-pour | exclusive-pour | two-layer | six-layer | six-layer-split
#             | four-layer-spread | trim-pour
#   (see DECISIONS.md; six-layer* is decision support, read the caveat in D1)

# or step by step
python tools/layout/ec_layout.py place  dump.json --iters 40000 --out placed.json
python tools/layout/ec_layout.py route  dump.json --place placed.json \
       --iters 40 --layers 4 --pour GND:4 --pour +3V3:3 --out plan.json
python tools/layout/ec_layout.py check  dump.json --place placed.json --plan plan.json

# split the clearance KPI into kinds and deficits (what to work on next)
python tools/layout/spacing_audit.py --dump dump.json --place placed.json --out-dir out/

# name the nets that cut a pour (which copper made the island)
python tools/layout/pour_cut.py out/plan.json --dump dump.json --place placed.json

# compare profiles and mark which are non-dominated
python tools/layout/compare.py --dump dump.json --place placed.json --profiles shared-pour,exclusive-pour

# run several configurations and pick the best by the gate's own order
python tools/layout/portfolio.py --dump dump.json --place placed.json --jobs 3 --out-dir out/pf

# ask whether a bus can be routed as parallel lanes at all
python tools/layout/bus_capacity.py --dump dump.json --place placed.json

# turn a passing plan into an on-machine bundle (refuses a failing one)
python tools/layout/emit_apply.py plan.json --kpi kpi.json --dump dump.json --out-dir dir/

# prove the delivery contract (guard refuses red, emits green, metrics pass) - fast
python tools/layout/acceptance.py --plan out/plan.json --kpi out/kpi.json --dump dump.json --stackup 4
```

## KPI (single definition, enforced by tests)

| KPI | meaning | target |
|---|---|---|
| `unrouted_legs` | MST edges A* could not complete | 0 |
| `congestion_cells` | (x, y, layer) cells claimed by two nets | 0 |
| `nets_unconnected` | nets whose pads do not form one component | 0 |
| `clearance_violations` | track/track, via/track, via/pad **and track/pad** pairs too close (sum of `clearance_breakdown`) | 0 |
| `pad_layer_gaps` | pads whose copper is on the wrong layer with no via nearby | 0 |
| `pour_islands` | pour access vias landing in different copper islands | 0 |
| `vias` | layer changes (access / in-pad reported separately) | minimise |
| `total_length_mil`, `diagonal_ratio`, `layer_length_mil` | quality metrics | — |
| `bus_length_spread_mil` | max−min length per CAM/LCD/SD group | < 50 |
| `layer_length_mil` | copper length per layer — the check that a "6-layer" run is not quietly 4-layer | — |

Every metric is computed **from the plan**, so `check` judges what would be written
to the board. Several earlier versions had router and checker disagreeing (40 vs
281, 12 vs 0, and a 2D connectivity check that called 72 physically open pads
"connected"); each is pinned by a test.

## Current frontier (RetroCam-02, 4 layers, GND + +3V3 as area pours)
`reproduce.py` (default profile `frontier`; all numbers re-measured after the clearance
KPI started counting track/pad — see HANDOFF §41; `frontier` won §46's portfolio over
six configurations by 4 violations, see STATUS.md):

```
unrouted 0 | congestion 0 | unconnected 0 | pad layer gaps 0 | pour islands 1
clearance 511 = 8 track/track + 174 via/track + 104 via/pad + 225 track/pad
vias 186 (59 access, 6 in-pad) | 527 segments | total length 38999 mil | 45-degree 0.411
bus skew: CAM_D 713.1 / LCD_ 165.3 / SD_ 297.6 mil
```

Four of the six gate items are zero. The three that are not:

1. **clearance 515** — 285 of them are "a via too close to someone else's copper"
   and 225 are "a track too close to someone else's pad". Deficit statistics say
   these are near misses, not blunders: via/track is off by 4.5 mil on average
   (min 0.5), track/pad by 11.4. They are the recorded trade of routing with an
   overlap-only veto (enforcing full via clearance during the search cost
   unrouted 7 → 33). Every attempt to steer the layer-change decision (veto,
   reserve, pre-plan, price in the search, via-first, post-hoc relocation) either
   loses legs or makes spacing worse; only post-hoc relocation of *routing* vias
   helps (−5).
2. **pour islands 1** — and now it is a *diagnosed* design conflict, not unfinished
   work: the cut layer is **L3 (+3V3), not the ground**; `pour_cut.py` shows the
   +3V3 pour split into 48439 + 190 cells by `BUZ_G` (572 mil on that layer),
   `CAM_VSYNC`, `CAM_SIOD` and `CAM_PCLK`, with one access via (J3.1) **stranded**
   in the pocket — that pad is connected to nothing but its own island. It cannot
   be rescued by moving copper: within 20 grid cells of that pad 655 main-pour
   cells exist and 147 give the via a clean disc, but **0** of them can be reached
   by a legal pad stub (`rescue_island_vias`, HANDOFF §42.3). The two escapes were
   measured and both fail: `--pour-trim` without a spacing guard bought zero
   islands with 130 track/track violations, and with a legal, layer-aware re-route
   it leaves the island at 1 while pushing LCD skew 165 → 467. Closing this needs
   a decision on the L1 routing, the J3 placement, or the layer count.
3. **bus skew** — not an implementation gap: `bus_capacity.py` shows the pin order
   of the two ends is uncorrelated (CAM ρ = −0.21 / −0.37, LCD ρ = 0.70), so a
   parallel lane bundle cannot exist. Closing it needs a pinout/stackup decision,
   and the post-hoc meander route is arithmetically impossible (§27 of HANDOFF).

## Verified behaviours worth knowing

* **A plan can be complete and still open.** `pad_layer_gaps` exists because a 2D
  connectivity check called 72 physically open pads connected.
* **A pour is not a plane.** Reserving a whole layer for GND cost more signal
  capacity than the 41 GND legs it removed; an area pour that shares the layer wins
  (unrouted 10 → 4 before later gains).
* **"Zero islands" was bought with spacing.** The pour trim only avoided *cells*
  another net owned, so its re-routes hugged neighbours at one grid step; with a
  spacing guard it trims nothing. A KPI can be satisfied by moving the damage to a
  KPI nobody measures — which is exactly why `track/pad` was added to the gate.
* **A count is not a diagnosis.** `pour_islands` = 1 hid a 190-cell pocket in the
  +3V3 pour with a stranded access via; `spacing_audit.py` and `pour_cut.py` exist
  so a red KPI comes with its cause, its size and the nets responsible.
* **A legal fix that finds no site is still a finding.** The island rescue is
  implemented and tested, and measured to move nothing on this board (0 of 147
  legal via sites reachable): that is what turned "unfinished" into "design conflict".
* **`check` never passes a KPI it could not measure** — unmeasured prints `null`
  and fails the gate.
* **The comparison cache is keyed on the metric code**, not only on the inputs, so
  changing a KPI definition cannot silently compare new code against old numbers.
* **`--layers N` now means N.** Nine through-hole checks were hardcoded to four
  layers while the CLI and the lint accepted any stack, so a 6-layer run would have
  treated layers 5–6 as free copper. The routed stack lives on `board.route_layers`
  and `_all_layers()` reads it; a test puts a foreign track on layer 6 and requires
  the check to see it.
* **A "6-layer" result must show its layer histogram.** The six-layer profile comes
  out at islands 0 with *identical* `layer_length_mil` on L1–L4 — the extra layers
  carry no copper at all, so the island vanished because the pours moved to empty
  layers, not because signals got room. Report the histogram before claiming a
  stackup helped.
* **`route(layer_map=..., layer_force=True)` assigns nets to layers, and a naive
  assignment is measurably bad.** Dealing the non-bus nets over the free layers with
  a stable hash lowers clearance (515 → 412 on 4 layers, 478 on 6) but costs 8/6 dead
  legs and 11 pad layer gaps, and the 6-layer variant creates a *new* island because
  the forced corridors cut the GND pour it crosses (HANDOFF §44). Extra layers have
  physical value; deciding *which net goes where* needs the layout, not the net name.
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








