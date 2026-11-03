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
assignment*.

The tool can now assign nets to layers (`route(layer_map=..., layer_spread=True,
layer_force=True)`), and the first automated layer plans were measured **worse**
(HANDOFF §44):

| profile | unrouted | clearance | pad gaps | islands | vias |
|---|---|---|---|---|---|
| shared-pour (4L) | **0** | 515 | **0** | 1 | 186 |
| four-layer-spread | 8 | 412 | 11 | 0 | 148 |
| six-layer-split (6L) | 6 | 478 | 11 | 1 | 246 |

Clearance does fall (412/478 < 515), so extra layers have real value — but a
net-name hash does not know where a net goes: every forced leg pays two vias, which
costs dead legs and pad-layer gaps, and on the 6-layer stack the forced corridors
cut the GND pour on L2. **Conclusion: a 6-layer board means writing a layer plan by
hand (from the placement geometry) and reviewing it, not letting the router deal
nets out.** Until such a plan is measured, D1 stays open and "6 layers is better"
stays unsupported.

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
---

## D6. Routing resolution and track width  **OPEN**

Measured on the same placement, same code (only the `GRID` and track-width constants
differ, loaded by `grid_experiment.py`), 70 negotiation passes:

| configuration | unrouted | unconnected | pour islands | clearance | skew max | length |
|---|---|---|---|---|---|---|
| GRID=10, 7 mil tracks (`frontier-10mil`) | 0 | 0 | **1** | **511** | 713.1 | 38999 |
| **GRID=10, 5 mil tracks, budget 16 (`thin-10mil`, DEFAULT)** | **0** | **0** | **0** | **380** | 783.6 | 40038 |
| GRID=10, 5 mil tracks, budget 8 | 0 | 0 | **0** | 438 | 900.4 | 37820 |
| GRID=5 + `--profile strict-via` | 0 | 0 | **0** | 453 | 751.1 | 42044 |
| GRID=5, budget 30 (via cost scaled with the grid) | 0 | 0 | **0** | 673 | 764.7 | 39554 |
| GRID=5, budget 64 | 0 | 0 | **0** | 831 | 712.3 | 35739 |

(The fine sweeps are in HANDOFF §53 and §69.  The budget/quality relationship is NOT
monotone: at 5 mil, budget 18 is worse than 22 and budget 14 brings an island back; at
10 mil, budget 8 is worse than 16.)

**The cheapest large win was the track width, not the grid.** Dropping 7 mil -> 5 mil
(the board's own minimum) took clearance 511 -> 393, removed the pour island, and runs in
6-14 min instead of 27.  `thin-10mil` is therefore the default.  It is still a design
decision: 5 mil signal / 8.6 mil power traces instead of the board's suggested 20 mil is a
manufacturing choice, recorded here rather than assumed.

What is left is a floor, not a knob: `escape_check.py` (§65) finds pads whose footprint
leaves no legal entry, and `forced_spacing.py` puts 211-260 of the 298 pad hits in the
"no corridor at 6 mil clearance" class - a green gate needs a footprint, rule or netlist
change.

Re-measure any time with:

```bash
python tools/layout/grid_experiment.py --dump dump2.json --place ec-placed.json \
    --grid 5 --pour-step 8 --best-effort-conflicts 10 --out-dir out/grid5
```

---

## D7. The router reasons in CELLS, the DRC in GEOMETRY  **OPEN (structural)**

Three defects found by auditing the code against the board's own rules in rounds 74-79 were
all the same shape: a quantity that is computed in grid cells where the rule is geometric.

| round | what was wrong | effect | fixed? |
|---|---|---|---|
| §74 | the pad obstacle was `pad + clearance`, but a track CENTRE needs half its own width on top | 190 track/pad hits | **yes** - `pad_guard=2.0`, clearance 393 → 335 |
| §78 | the congestion checker filed vias on a pseudo-layer 0, so a via sitting on another net's track was invisible | every "congestion 0" was an undercount; the frontier really has 1 | **yes** - now visible |
| §78 | `route()` marked a layer-change cell only on the two adjacent layers | later nets could lay tracks across existing vias | **yes** - marked on every layer |
| §79 | the pad obstacle is a CELL SET, so a segment can clip a pad corner without touching a blocked cell | one in-pad via short survives; `track_pad` stuck around 180 | **no** - see below |

Two candidate fixes were measured and rejected (§79):

* `pour_pad_guard` (pour-net pad interiors hard) - bit-identical to the default, because the
  offending segment never occupies a pad cell: cell-level blocking cannot see a corner clip.
* `pad_geom` (geometric pad check when a leg is accepted) - cuts track/pad 180 → 149 and
  clearance 327 → 321, but raises congestion 1 → 3, because rejecting a path dumps its whole
  cell set into the retry blocklist and best-effort then overlaps elsewhere.

Removing the last short really needs the A* obstacle itself to be geometric (or a finer grid
where a cell is smaller than the tolerance that matters).  That is a router-core change with
its own KPI risk, so it is recorded as an open structural item rather than attempted here.

**Consequence for delivery:** the gate can report "0 congestion" only if a plan is free of
via-on-track clashes by construction; D7 is the reason the frontier still carries one.

Round 81 tested three POST-HOC fixes for that last short - a geometric guard before the in-pad
fallback, the same guard in both via relocations, and a resolver that rips the shorted track
and re-routes it.  All three were bit-identical to the default, and the controls showed why:
that pad has no legal site (even at 2x the search radius) AND the offending track has no
alternative route.  The short can therefore only be avoided DURING the A* - which is exactly
what makes D7 a router-core item rather than a patch.

**Confirmed at the discretisation level (round 89).** If D7 is really a cell-size artefact, halving
the cell should remove the clash - and it does.  The 5 mil grid had only ever run with 7 mil
tracks; with the board's own 5 mil width and `pad_guard 2.5`:

| configuration | dead | congestion | clearance | vias | tracks |
|---|---|---|---|---|---|
| `thin-10mil` (10 mil grid, 5 mil tracks) | 0 | **1** | 380 | 182 | 611 |
| `strict-via-thin` (5 mil grid, 5 mil tracks) | 0 | **0** | 394 | 166 | 717 |

So the remaining short is a discretisation artefact, not a rule conflict: at 5 mil the corner
error (±2.5 mil) is smaller than the tolerance that matters (≈2.5 mil of track half-width), and the
via-on-track clash disappears.  By the gate's order (congestion outranks clearance) the finer point
is the better one; it costs 3-4x the runtime.  Both pass `plan_lint`.
*(Determinism: confirmed - a second independent run reproduced 717 segments and 166 vias
exactly, segment for segment, with identical layer totals and 45-degree share.)*

---

## D8 — KPI 排序：**间距优先于等长**（2026-11-03，用户决策）

本仓库的字典序原本就写成 … → 间距 → 等长 → 过孔 → 线长，但没有明确它是**规则**还是**默认显示顺序**。
用户明确选择 **间距优先**，因此：

* 合法候选里按该规则最优的是 **`frontier-i`**（间距 **146**、CAM 837.8、LCD 41.4、SD 31.9）；
* 若将来改为等长优先，最优点会变成 `frontier-j`（217 / **121.8**）；
* 该选择只影响"四个合法点里选哪个作为主候选"，**不影响**任何单点的实测数字，
  也不改变"没有点同时达标"这个事实（GAPS G1/G2）。

**执行后果**：`candidates.py` 与文档以 `frontier-i` 为主候选；`frontier-j` 仍保留（等长最好的对照点），
`frontier-g`/`frontier-h` 作为中间档保留。
