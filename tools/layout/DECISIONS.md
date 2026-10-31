# Open decisions (and what each one unlocks)

The toolchain is at a point where four questions need an engineering decision, not
more tuning. Each entry says what is known, what the options are, and what the next
agent should do once the decision lands. Numbers are on `HANDOFF.md` §34–§37.

---

## D1. Stackup: is RetroCam-02 2-layer or 4-layer?  **BLOCKING**

The dump says `copperLayers: 2`; every routing result in this repo assumes 4.

| option | consequence |
|---|---|
| change the board to 4 layers | all current results become applicable; clearance 290 is the main target |
| keep 2 layers | measured: 7–10 nets left open, GND pour cut into 2 islands, +6 % length |

Until now: `plan_lint` blocks a 4-layer plan on a 2-layer board, and the only way
past it is `--stackup 4`, which is written into `manifest.json` so the assumption
travels with the bundle.

**Next agent:** if the answer is 4 layers, re-run everything and delete the override
from the standard command (it should stop being needed). If it is 2 layers, the
placement has to be redone under 2-layer congestion before any routing number means
anything.

---

## D2. Pour strategy: shared layer vs exclusive layer

Measured (4 layers, board rules, 70 negotiation passes, **current KPI** — i.e.
clearance now includes track/pad; see D5):

| configuration | clearance | unrouted | pour islands | command |
|---|---|---|---|---|
| pours share their layers | 515 | **0** | **1** (fail) | `--profile shared-pour` |
| pour layers exclusive | 436 | 4 | **0** | `--profile exclusive-pour` |
| GND exclusive, no +3V3 pour | (not re-measured) | 1 | **0** | (see HANDOFF §36) |

3161 mil of track sits on the GND pour layer across 11 nets, so "a few short
crossings" is not the situation - the layer is used as a routing layer.

**Decision needed:** either accept a split ground plane (and prove the return path
elsewhere), or pay capacity for a whole pour, or move to 6 layers.

Both branches are one command now, so the comparison can be re-run at any time:

```bash
python tools/layout/reproduce.py --dump dump2.json --place ec-placed.json --profile shared-pour
python tools/layout/reproduce.py --dump dump2.json --place ec-placed.json --profile exclusive-pour
```

`--profile two-layer` covers the other branch of D1 (measured: 6 open nets,
7 pour islands, 201 clearance — under the older clearance definition).

`--profile six-layer` is the "add layers" branch. Measured (HANDOFF §43):

| profile | unrouted | clearance | islands | vias | tracks | length | skew max |
|---|---|---|---|---|---|---|---|
| shared-pour (4L) | 0 | 515 | 1 | 186 | 526 | 38832 | 713.1 |
| six-layer (6L) | 0 | 515 | **0** | 186 | 526 | 38832 | 713.1 |

Read that carefully: layers 5 and 6 carry **zero track** (`layer_length_mil` is
identical on L1–L4 in both runs), so the island disappears because the pours moved
to empty layers — not because extra layers gave the signals room. Adding layers is
therefore a **cheap** way to get whole pours (a 4-layer exclusive pour costs 4 dead
legs), and it does **not** improve clearance or skew *with the current layer
assignment*. Making the extra layers earn their cost needs an explicit net→layer
assignment in `route()`; until that is measured, D1 stays open and no "6 layers is
better" claim belongs in the docs.

### Measured comparison (70 passes, same placement)

```
| profile        | unrouted | congestion | clearance | unconn | pad gaps | islands | vias | length | skew max | pareto |
| shared-pour    | 0        | 0          | 515       | 0      | 0        | 1       | 186  | 38832  | 713.1    | yes    |
| exclusive-pour | 4        | 0          | 436       | 4      | 0        | 0       | 133  | 39948  | 1034.6   | yes    |
| trim-pour      | 0        | 0          | 515       | 0      | 0        | 1       | 186  | 38832  | 713.1    | (== shared) |
| two-layer      | 5        | 0          | 207 *     | 5      | 0        | 3       | 145  | 42482  | 1089.5   |        |
```

`*` two-layer has not been re-run under the track/pad-inclusive KPI; its 207 is the
older count and is therefore not comparable to the 4-layer rows. Re-run before
quoting it.

`two-layer` is **dominated**: worse than both 4-layer branches on every axis. So
D1 is not really a close call — a 2-layer board costs open nets, pour continuity
and length at the same time.

### The `--pour-trim` escape is now closed (was §38's answer)

A third route was measured in §38: keep the pour shared but re-route only the nets
that cross it for a long run (`--pour-trim`). It was the first configuration with
zero open legs AND a whole ground plane. §41 and §42 re-measured it twice under the
track/pad-inclusive KPI:

| configuration | clearance | track/track | unrouted | pour islands | LCD skew |
|---|---|---|---|---|---|
| shared | 515 | 5 | 0 | 1 | 165.3 |
| `--pour-trim`, no guard | 611 | **130** | 0 | **0** | 268.7 |
| `--pour-trim`, spacing guard only | 515 | 5 | 0 | 1 | 165.3 (no-op) |
| `--pour-trim`, layer-aware legal re-route | 522 | 5 | 0 | **1** | **467.3** |
| exclusive | 436 | 5 | 4 | 0 | 165.3 |

With legal re-routes the island **does not go away** and the bus skew gets worse,
so the trim is a recorded dead end (three attempts, §38/§41/§42).

### What the remaining island actually is (§42)

`pour_cut.py` on the frontier plan:

```
layer 3: pour is CUT into 2 pieces, sizes [48439, 190]
  cuts: BUZ_G 45 / CAM_VSYNC 28 / CAM_SIOD 22 / CAM_PCLK 12  (touching cells)
  STRANDED access via: net +3V3 at (1935, 1025)
```

Three consequences for this decision:

1. The cut is **+3V3 on L3**, not ground. The ground pour on L4 is one piece
   (49346 cells), so "do we accept a split ground plane" is not the question this
   board is asking today;
2. the stranded via means one +3V3 pin (J3.1) reaches only its own pocket — a real
   open, not a DRC nit;
3. it cannot be fixed by moving copper: `rescue_island_vias` finds 655 main-pour
   cells within 20 cells of that pad, 147 with a clean via disc, and **0** reachable
   by a legal pad stub. Fixing it means changing the L1 routing around J3, moving
   J3, or adding layers.

`shared-pour` and `exclusive-pour` remain non-dominated, and that is exactly D2:
open nets versus a whole ground plane. Reproduce with:

```bash
python tools/layout/compare.py --dump dump2.json --place ec-placed.json \
    --profiles shared-pour,exclusive-pour,trim-pour --out compare.md
```

---

## D3. Bus skew: a pinout problem, not a router problem

`bus_capacity.py` shows the two ends of every bus disagree on order —
CAM ρ = −0.21 / −0.37, LCD ρ = 0.70 — so a parallel lane bundle cannot exist.
Post-hoc meanders cannot close a 713 mil gap either: at 80 mil amplitude one bump
adds 37.8 mil, needing ~6080 mil of straight host on a 2756 mil board.

**Decision needed:** accept the skew, change the pin assignment/footprint, or add
layers. The gate will keep reporting it as a design conflict (`reproduce.py`
classifies it that way) rather than as unfinished work.

---

## D4. Delivery: what does "one-shot apply" mean here?

`emit_apply.py` refuses while the KPI gate is red, and writes
`apply-plan.json` + `manifest.json` + `APPLY.md` when it is green. Nothing in this
repo has ever been written to a live board.

**Decision needed:** when a green plan exists, who runs the apply, on which copy of
the project, and what is the rollback if the read-back DRC disagrees?

---

## D5. What "clearance" means in the gate, and what it does not

**Decision taken (measurable, reversible):** `clearance_violations` is the sum of
four kinds, produced by one function (`clearance_breakdown`) that the gate itself
calls:

| kind | test | enforced during routing? |
|---|---|---|
| `track_track` | two nets' tracks on the same layer closer than `(w1+w2)/2 + CLEARANCE` | yes, `path_conflicts` (per leg, with a few-conflicts fallback) |
| `via_track` | via ring vs another net's track, on **every** layer (a via is a through-hole) | overlap only (`VIA_BLOCK_MARGIN = 1.0`) |
| `via_pad` | via ring vs another net's pad | overlap only |
| `track_pad` | track vs another net's pad on the layer the pad is plated on (through-hole pads count on all layers) | pad keep-out only |

Why overlap-only for vias: enforcing the full 26 mil clear disc around every layer
change was measured at unrouted 7 → 33. The spacing then shows up as the reported
KPI instead of as a dead leg — a documented trade, not an oversight.

Why `track_pad` was added (HANDOFF §41): the gate used to ignore it, and the plan
the trim profile produced had **245** of them — a KPI can be "met" by moving the
damage into a check nobody runs.

Consequences recorded here so nobody re-litigates them silently:

* any change to `clearance_violations` changes every number in HANDOFF/README;
* `compare.py` cache keys include a fingerprint of `ec_layout.py` + `reproduce.py`,
  so a metric change cannot be compared against cached old results.

---

## Recorded defaults (do not silently change)

| constant | value | why |
|---|---|---|
| `CLEARANCE` | 6.0 mil | the board's own `clearanceMil` is 5.98 |
| `VIA_RADIUS` | 12.01 mil | the board's `viaDiameterMil` is 24.02; using 10 understated violations by half |
| `TRACE` / `BUS_TRACE` | 7.0 / 6.0 mil | board default 10, minimum 5; thinner is legal and buys fan-out room |
| `NET_ORDER` | small-first | measured better than big-first and region-first |
| `VIA_COST` | 14 | 20 buys 48 fewer violations but one more open net; the gate ranks open nets first |
| `BEST_EFFORT_MAX_CONFLICTS` | 2 | an open net is worse than a spacing violation, an overlap is not |
| `trim_pour_crossings` acceptance | new path must not add `path_conflicts` | without it the trim silently traded islands for spacing (HANDOFF §41) |

