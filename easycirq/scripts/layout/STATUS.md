# STATUS — offline layout & routing for RetroCam-02 (one page)

## FROZEN — 2026-11-03, HANDOFF §174 (performance work appended §180–§188)

> **This capability is frozen.** [`WRAP-UP.md`](WRAP-UP.md) is the hand-over: what it can do, what it cannot,
> the three inputs that would unblock it, and what "frozen" allows. Read that first; this page is the
> evidence log.
>
> Frozen with these **known limitations**, all measured and none of them hidden:
>
> 1. **RetroCam-02 is not deliverable.** Primary candidate `frontier-i` (clearance-first, DECISIONS D8):
>    clearance **146**, CAM skew **837.8**, LCD 41.4, SD 31.9, 0 on every other gate item, placement LEGAL,
>    `plan_lint` PASS, DFM 5 drill findings (J1 slot 0.24 mm vs an *assumed* 0.30 mm), `deliverable: NO` (§174).
> 2. **The green path is proven but on a synthetic board** — self-test board: clearance 0, skew 0.0,
>    `deliverable: YES` (§170/§172). It must never be quoted as a RetroCam result.
> 3. **Manufacturing files are generated but not CAM-validated**; slots are not emitted; no BOM with LCSC
>    numbers (§171).
> 4. **Electrical numbers rest on labelled assumptions** unless external files are supplied (§131–§133, §167).
> 5. **Parameters are tuned to this board**; the generalisation evidence is one second board (§168).
> 6. **Nothing has ever been written to a live board**, and the delivery contract forbids waiving PCB DRC.
>
> Changes after this point: **defect fixes only** (a wrong number or a false verdict). No new tools.

## 0. Handover (read this first)

> The measured levers, their costs and the refuted ideas are condensed in
> [`PRESCRIPTION.md`](PRESCRIPTION.md) (measured levers + refuted ideas) and
> [`GAPS.md`](GAPS.md) (defect list with per-item acceptance conditions).  This section is the state
> of the effort.

**Status change, §143-§157 (read before trusting any number below).**  The sections further down are
frozen history.  They were written before anyone checked whether the placement was *legal*: four of the
five "improved" candidates carried overlapping parts, and two of them used connector pads wider than the
part's own pitch (20 mil pads on a 19.7 mil pitch - a footprint that cannot exist).  Those numbers are
withdrawn; the current state lives in [`GAPS.md`](GAPS.md) and [`PRESCRIPTION.md`](PRESCRIPTION.md).

**What is true now** (all four candidates LEGAL, `overlaps 0 / outside 0`, gate items 0/0/0/0/0,
LCD 41.4 and SD 31.9 inside the 50 mil target, delivery grade 70 passes):

| candidate | SoC pad / CAM window | clearance | CAM skew | what it trades |
|---|---|---|---|---|
| `frontier-i` | 26x26 / 17..24 | **146** | 837.8 | best spacing, worst CAM |
| `frontier-g` | 36x36 / 13..20 | 180 | 398.6 | middle |
| `frontier-j` | 26x26 / 11..18 | 217 | **121.8** | best CAM, worst spacing |
| `frontier-h` | 26x26 / 13..20 | 232 | 144.9 | good CAM, poor spacing |

No point satisfies both targets; the limit is the 19.7 : 50 mil pitch ratio between J3 and U5 (§123/§155).
One command compares them (`gaps_check --candidate all`), one command reproduces any of them
(`pipeline --candidate frontier-i`), and `regress.py` refuses the withdrawn candidates by default (§148).

**What this is.** The offline layout + routed toolchain The offline layout + negotiated-routing toolchain for RetroCam-02: placement,
4-layer routing with pours, the eleven KPIs the goal names, an offline DRC gate, and a delivery guard
that refuses to touch a live board while the gate is red.  Every number below came from a command run
in this repository; anything not run says `NOT RUN`.

**Where the REAL board stands** (`strict-via-thin`, 5 mil grid, 5 mil tracks, ~45 min):

| KPI | value | state |
|---|---|---|
| unrouted legs | 0 | ok |
| congestion cells | 0 | ok |
| clearance violations | **394** (15/135/27/217) | red - ~3/4 of the pad hits are geometry-forced at the 6 mil rule |
| unconnected nets | 0 | ok |
| pad layer gaps | 0 | ok |
| pour islands | 0 | ok |
| vias / tracks / length | 166 (59 access, 3 in-pad) / 717 / 40018.6 mil | info |
| 45-degree share | 0.469 | info |
| layer distribution | L1 20339.1 / L2 11752.5 / L3 4124.3 / L4 3802.6 mil | info |
| bus skew CAM/LCD/SD | 923.1 / 165.3 / 284.3 mil | red - pinout/pairing problem, not a router problem |

`plan_lint` PASSES and `acceptance.py` prints `contract: PASS` while refusing to emit.  **Nothing has
ever been written to a live board**, and the delivery contract does **not** allow waiving PCB DRC, so
this board is not deliverable as it stands.

**The reproducible simulated candidate** (`prescribe.py`, §114) - one command, idempotent, with
provenance:

```bash
python easycirq/scripts/layout/prescribe.py --dump ../retrocam-02/pcb/dump2.json \
    --place ../retrocam-02/pcb/offline/ec-placed.json --out-dir out/recipe
python easycirq/scripts/layout/reproduce.py --dump out/recipe/dump.json --place out/recipe/place.json \
    --profile strict-via-thin --out-dir out/recipe-run
```

| KPI | measured value |
|---|---|
| dead / congestion / unconnected / pad gaps / islands | **0 / 0 / 0 / 0 / 0** |
| clearance | **368** |
| bus skew CAM / LCD / SD | 1543.7 / **41.4** / **31.9** |
| vias / tracks / length | 166 (59 access, 4 in-pad) / 667 / 42671.6 mil |
| 45-degree share / layers | 0.428 / 21258.3 - 14241.2 - 4087.5 - 3084.6 mil |

Three ad-hoc points measured earlier (clearance 307 / 316 / 425 with CAM 500 / 211 / 212) are **not
reproducible** - a documented recipe produced a different pin assignment (§113) - so they are quoted only
as history.

**Why the two red lines cannot be closed from above:** length matching wants regular parallel bundles, and
regular bundles crowd exactly the copper the clearance rule already cannot place (§93: 213 of 244
pad-class hits have no corridor at 6 mil; §94: a 3 mil rule still leaves 76 % of them).  A 6-layer stack
measured **worse** (§112).  Inside the canonical recipe the remaining CAM skew is not even a pairing
problem: eight pairings measure within 45-89 mil geometrically, while one net routes a 2056 mil detour
around a congested corridor (§116) - i.e. it is the router's corridor behaviour, the same root as §79/§81.

**Frozen 2026-02-01, and the freeze was verified (§118).** Re-running the two commands above reproduced
the whole table segment for segment (667 tracks, 166 vias, identical coordinates; all KPIs equal), so this
is evidence rather than a promise - if a later run shows different numbers from these commands, something
changed in the code or the inputs.

Nothing further is attempted offline without a decision: the levers above are exhausted, and every
remaining idea is either the router core (D7) or a board-level change (area, parts, rules).

**What was fixed by auditing the code against the board's own rules** (the most productive line of work):

| finding | effect | section |
|---|---|---|
| pad obstacle was half a track width short | 393 -> 335 (illegal-width era) | §74 |
| congestion checker could not see a via on another net's track | every earlier "0 congestion" was an undercount | §78 |
| layer-change cells were marked on two layers only | later nets could cross existing vias | §78 |
| default profile routed bus traces at 4 mil where the minimum is 5 | the "327 frontier" was not deliverable; compliant value 380 | §82/§83 |
| bus pin pairing was anti-parallel with a 2:1 pitch mismatch | LCD skew 124 -> 41 on reversal (§110) | §110 |

**What remains - all of it needs a decision outside the toolchain.**

1. **Board-level change**: board area, part choice (U4/L1 are the density problem), or the rule itself.
   Every one of these can be measured with the same pipeline (~45 min per run).
2. **Accept the simulated change set** (pads 20/40/80, CAM->13..20, SD->23..26, LCD pairing reversed,
   J3 -50, J4 +120/+100) as a formal change list, then re-run the full gate.
3. **D7 (router core)**: the A* obstacle is a cell set while the DRC is geometric; four post-hoc fixes
   were measured and rejected (§74/§79/§81), and halving the cell (5 mil grid) removes the one real
   short (§89) - a geometric-obstacle A* remains the only tool-side idea not ruled out.

**How to reproduce and verify.**

```bash
# whole chain, delivery grade (~45 min): report.md + summary.json, exit 0 only if deliverable
python easycirq/scripts/layout/pipeline.py --dump ../retrocam-02/pcb/dump2.json \
    --place ../retrocam-02/pcb/offline/ec-placed.json --out-dir out/run1

# fast answer (~6-14 min; one congestion cell left)
python easycirq/scripts/layout/pipeline.py --dump ../retrocam-02/pcb/dump2.json \
    --place ../retrocam-02/pcb/offline/ec-placed.json --out-dir out/fast --profile thin-10mil

python -m pytest tests/test_ec_layout.py tests/test_bus_order.py -q     # 81 passed
python -m pytest tests -q                                              # 5416 passed, 9 skipped,
                                                                       # 1 pre-existing error outside this toolchain
```

---

## 0.1 Objective audit (round 58, superseded by the handover above for current numbers)

The goal is to deposit a toolchain that any agent can drive, with the rule "nothing goes
to the machine until the offline gate is green".  Clause by clause, with evidence:

| clause | evidence in this repo | state |
|---|---|---|
| offline placement | `ec_layout.py place`, `sweep_placement.py`, face/button terms (§31) | ✅ |
| negotiated routing | `route()` (PathFinder-style, 4 layers, pours); 0 dead legs, 0 congestion, 0 unconnected, 0 pad gaps | ✅ |
| quality metrics | `report()` / `reproduce.py` scorecard with all eight KPIs the goal names (layer distribution added in round 58) | ✅ |
| offline DRC | `check`, `plan_lint.py`, `spacing_audit.py`, `pour_cut.py`, `forced_spacing.py`, `acceptance.py` | ✅ |
| KPI-gated delivery | `emit_apply.py` refuses while red (exit 2, reasons named); `acceptance.py` proves it in <1 min | ✅ |
| everything in the repo | 13 layout tools, 59 tests, `STATUS.md`/`README.md`/`HANDOFF.md` (63 sections)/`DECISIONS.md` (D1–D6) | ✅ |
| one-shot apply to the machine | **nothing has ever been applied**: the gate is still red | ⛔ |
| "professional-grade layout & routing" | 2 gated items red: clearance **380** (~3/4 of the pad hits are geometry-forced at the 6 mil rule) and **1 congestion cell** (a real via-on-track short the old checker hid, §78); bus skew is structurally uncompensatable (§77) | ⛔ |

So the **capability** is deposited and self-verifying; the **board** is not deliverable
yet, and both remaining blockers are measured design decisions rather than router gaps
(see §3 and DECISIONS D2/D3/D6).  No plan has been written to a live board, which is the
rule working as intended.

**Blocked 2026-11-01 (proved, §65), accepted by the engineer:** the gate cannot go green
on this board - five pads (R2×2, U2×2, U1×1) have no legal track entry at the board's own
rules, so clearance has a floor of ≥11 violations, and the bus skew needs a pinout change.
The toolchain is the deliverable; the board stays undeliverable until someone decides on
the red lines.  When that happens, nothing in the pipeline needs rebuilding:

```bash
# after a pinout / placement / stackup change:
python easycirq/scripts/layout/reproduce.py --dump newdump.json --place ec-placed.json --out-dir out/
python easycirq/scripts/layout/acceptance.py --plan out/plan.json --kpi out/kpi.json \
    --dump newdump.json --stackup 4      # must print contract: PASS before any apply
```

Measured-and-rejected dimensions (§4) and the decision checklist (§5.1) are the parts
worth reading before touching the router again.

> Read this first. It is the current state, the evidence behind it, and what is
> **not** worth retrying. Details live in `HANDOFF.md` (§ numbers below) and
> `DECISIONS.md` (D1–D5); every number here was produced by the commands in §6.

## 1. What the toolchain can and cannot do today

| stage | tool | state |
|---|---|---|
| offline placement | `ec_layout.py place`, `sweep_placement.py` | works; face/button terms in use (§31) |
| negotiated routing | `ec_layout.py route` (PathFinder-style, 4 layers, pours) | works; **0 unrouted legs, 0 congestion, 0 unconnected, 0 pad-layer gaps** |
| quality metrics | `report()` / `reproduce.py` scorecard | works; 11 KPIs, all computed *from the plan* |
| offline DRC gate | `check`, `spacing_audit.py`, `pour_cut.py`, `plan_lint.py` | works; 3 of 6 gate items still red (below) |
| delivery guard | `emit_apply.py`, `acceptance.py` | works; **refuses to emit while the gate is red** (exit 2, reasons named) |
| one-shot apply to the machine | — | **NOT DONE**: gate is red, so nothing has ever been written to a live board |

## 2. Current frontier (reproduce it yourself)

> **Round 89 added a deliverable-grade point:** `strict-via-thin` (5 mil grid, 5 mil tracks,
> pad_guard 2.5) reaches **0 dead / 0 congestion / 0 unconnected / 0 pad gaps / 0 islands /
> clearance 394** - the one via-on-track short of the 10 mil grid disappears once the cell is
> half the size (D7's discretisation error).  It costs 3-4x the runtime, so `thin-10mil`
> stays the fast default for iteration and `strict-via-thin` is the one to quote for delivery.
> Both pass `plan_lint`.
>
> Numbers from `thin-10mil` before round 82 used a 4 mil bus width that the board forbids
> (228 tracks below `trackWidthMinMil = 5`); `plan_lint` refused them.  The compliant
> frontier is **380** and every figure below is from that run (§83).

```bash
# DEFAULT: the best measured point (10 mil grid, 5 mil tracks, budget 16) - ~6-14 min
python easycirq/scripts/layout/reproduce.py --dump ../retrocam-02/pcb/dump2.json \
    --place ../retrocam-02/pcb/offline/ec-placed.json --out-dir out/thin-10mil

# the finer-grid alternative (5 mil grid, reserved via discs) - ~27 min
python easycirq/scripts/layout/reproduce.py --dump ../retrocam-02/pcb/dump2.json \
    --place ../retrocam-02/pcb/offline/ec-placed.json \
    --profile strict-via --out-dir out/strict-via
```

The default is the best point on purpose: a plain `reproduce.py` must not reproduce
yesterday's frontier.  It costs ~6–14 min (measured); `--profile strict-via` is the
finer-grid alternative and `--profile frontier-10mil` the older 7 mil reference.

| KPI | **thin-10mil (new best)** | strict-via (5 mil) | 10 mil reference | gate |
|---|---|---|---|---|
| unrouted legs | 0 | 0 | 0 | ✅ |
| congestion cells | **1** (a real short the old checker hid, §78) | 0 | 0 | ❌ |
| unconnected nets | 0 | 0 | 0 | ✅ |
| pad layer gaps | 0 | 0 | 0 | ✅ |
| pour islands | **0** | **0** | 1 (+3V3/L3: 48439 + 190) | ✅ / ❌ |
| clearance violations | **380** = 17 track/track + 51 via/track + 100 via/pad + 212 track/pad | 453 = 35/91/31/296 | 511 = 8/174/104/225 | ❌ |
| bus skew CAM/LCD/SD | 783.6 / 165.3 / 297.6 mil | 751.1 / 165.3 / 359.3 | 713.1 / 165.3 / 297.6 | ❌ (design conflict) |
| vias (access / in-pad) | 182 (59 / 4) | 172 (59 / 6) | 186 (59 / 6) | info |
| tracks / total length | 611 / 40037.6 mil | 647 / 42044.2 mil | 527 / 38999.0 mil | info |
| 45-degree share | 0.476 | 0.428 | 0.411 | info |
| layer distribution | L1 17190.0 / L2 13747.7 / L3 6350.9 / L4 2749.1 mil | L1 22268.9 / L2 11023.1 / L3 4054.6 / L4 4697.6 | L1 17076.7 / L2 13529.3 / L3 5231.5 / L4 3161.5 | info |

`strict-via` is the first configuration that is not worse on **any** gated item and is
better on two (islands 1 → 0, clearance 511 → 453) with zero dead legs; superseded by
`thin-10mil` (§82/§83), which reaches clearance **380** on legal track widths with the same zero dead legs; it costs ~40 min
of runtime and +3045 mil of track.  It is reproducible: two independent runs came back
item by item identical (§57–§58).

Stackup: routed as **4 layers**, recorded override `--stackup 4` (the board's own
rules say `copperLayers = 2`, so the 4-layer stackup is an assumption — D1).

## 3. The red lines: cause, evidence, who decides

### 3.1 Clearance 394 (delivery point) — three quarters of what is left is untouched by routing

* **Composition at `strict-via-thin`:** 217 track/pad + 135 via/track + 27 via/pad + 15 track/track.
* **Thinner copper is the biggest single win found in this whole effort** (§69): dropping the
  track width from 7 to the board's own 5 mil minimum took clearance 511 → 393 (on 10 mil
  tracks: 380 at the same width, §82), and the pad obstacle turned out to be half a track
  width short (§74).  It also brought the pour island to 0, in 6–14 min instead of 27.
  The finer grid then removed the last short (§89), at +14 spacing.
* `forced_spacing.py` on the **delivery plan** (grid 5, clearance 6): **175 pad pairs have no
  legal corridor**, and of the pad hits it classifies, **213 are forced and 31 are open** - i.e.
  roughly seven hits in eight cannot be routed away, only removed by moving a part or relaxing
  the rule.
* **There is a hard floor beyond all of that - worth 6 hits on the delivery plan.**
  `escape_check.py --width 5 --clearance 6` still finds **5 pads** (R2×2, U2×2, U1×1) with no
  legal track entry, and on the grid-5 plan those pads account for U2.1 2 + U1.1 3 + R2.1 1 = **6**
  violations (R2.2 and U2.2 now pay none).  Real, but 1.5 % of 394.  `escape_check.py` (§65) asks a question
  no router, placement or stackup can change: does ANY legal track exist that can enter
  each pad, at the board's own width and clearance?  At 7 mil / 6 mil, five pads — R2×2,
  U2×2, U1×1 — have **no legal entry angle**, and they are connected anyway, each stub
  paying 1–3 violations.  Re-run at the shipped width (§93) the same five pads still have no
  legal entry, so the floor survives the thinner copper - it is now measured at 6 hits.
* Every knob around it has a measured optimum, not a direction: via disc 25 mil at 5 mil
  (30 → 4 dead legs + a congestion cell, §59); acceptance budget 56 at 5 mil / 16 at
  10 mil (§57, §69); `pour_step` saturated at 8 (§47); `row_penalty` refuted (§68).
* **Relaxing the rule is not a way out (§94).** Re-scoring the same plan at looser rules gives
  382 (5.98) / 350 (5.0) / 333 (4.02) / 324 (4.0) / **299 (3.0)** against 394 at 6 mil - even at
  a 3 mil rule **76 % of the hits remain**, so the density, not the rule, is what is binding.
* **Best simulated configuration (§109):** pad shrink + bus repin + the joint pin map (CAM 13..20,
  SD 23..26) + J4 (+120, +100) **+ J3 (-50, 0)** gives 0 dead / 0 congestion / 0 unconnected / 0 pad
  gaps / 0 islands, **clearance 316** and bus skew **211.4 / 124.3 / 31.9** - the only configuration
  that is simultaneously at the lowest clearance and closest on every bus group.
* **Previous best (§104):** footprint change + bus repin + one targeted move of J4
  by (+120, +100) mil gives 0 dead / 0 congestion / 0 unconnected / 0 pad gaps / 0 islands,
  **clearance 327** and bus skew **286.6 / 124.3 / 207.1** - the LCD group halved at zero cost
  (contrast §102, where a multi-part geometric prescription made every KPI worse).
* **Footprint change + bus repin is the closest-to-deliverable option measured (§99):** shrinking
  the pads of U1/U4/L1 **and** re-pinning 25 bus pads gives 0 dead / 0 congestion / 0 unconnected /
  0 pad gaps / 0 islands with **clearance 327** and bus skew **286.6 / 257.0 / 207.1** (from
  923.1 / 165.3 / 284.3 on the real board, and 1704.6 CAM with the footprint change alone).  All
  three groups are still above the 50 mil target, so the remaining work is pinout design, not routing.
* **A footprint change was priced in the delivery profile (§98):** shrinking the pads of U1
  (27.6 → 20 mil), U4 (57.2 → 40) and L1 (165.4 → 80) in a simulated dump and re-running
  `strict-via-thin` gives **0 dead / 0 congestion / 0 unconnected / 0 pad gaps / 0 islands and
  clearance 394 → 328** (-17 %), at the cost of CAM skew 923 → 1705 mil and +1.3 % copper.  That is
  the only measured way found to lower the spacing KPI, and it needs a manufacturing decision.
* **The brief for those pads is measured, not guessed:** `pad_escape_spec.py` (§96) names each
  blocking neighbour and the two levers - e.g. R2.1 must sit 37.0 mil further from U4.2 (or that
  57.2 mil pad must shrink to <= 0, i.e. moving is the only option there), U2.1 needs 63.8 mil more
  separation from the 165.4 mil inductor pad, and U1.1's own 19.7 mil row pitch cannot be fixed by
  placement at all - only by the footprint.
* **Decision needed:** change the footprint (R2/U2/U1 pads) or move the parts (J3/J1/U4/L1).
  **A waiver is not available for this item:** the EasyCirq delivery contract forbids waiving PCB
  DRC (only style warnings, mounting holes, connector escape, layout freeze, silkscreen and test
  plans may be waived).  So "gate green" is mandatory, and with the rule fixed the only levers are
  the footprint and the placement.
* **3.2/below:** the pour island is solved (0) on both current points; the 10 mil 7-mil
  reference still shows 1 and is kept only as a comparison.

### 3.2 Pour islands — SOLVED at 5 mil (0), still 1 at 10 mil

* At 10 mil the cure did not exist: L4 GND is one piece, the cut was **+3V3 on L3**
  (48439 + 190 cells by `BUZ_G`/`CAM_VSYNC`/`CAM_SIOD`/`CAM_PCLK`), with one access via
  (J3.1) stranded in the pocket — copper-open while every connectivity check said
  "connected" (`pour_cut.py`, §42).
* It could not be rescued by moving copper (0 of 147 legal sites reachable by a legal
  pad stub, §42.3), and both pour escapes were measured: `--pour-trim` without a guard
  bought zero islands with 130 track/track violations; with a legal layer-aware re-route
  it left the island at 1 and pushed LCD skew 165 → 467 (§41–§42).
* **At 5 mil the island is gone** (`strict-via`: `pour_islands = 0`, verified with
  `pour_island_report()` on the saved plan, §51/§57).  The gap that was one cell wide
  at 10 mil is two cells at 5 mil, so the same copper face connects.  The §42 verdict
  ("design conflict") was therefore too strong: it described the 10 mil grid, not the
  physics.

### 3.3 Bus skew — a pinout conflict

* `bus_capacity.py`: the pad order of the two ends is uncorrelated (CAM ρ = −0.21 /
  −0.37, LCD ρ = 0.70), so parallel lane bundles cannot exist (§27, D3).
* Post-hoc meanders are arithmetically impossible: 713 mil needs ~19 bumps ≈ 6080 mil
  of host on a 2756 mil board.
* **Decision needed:** accept, change the pin assignment/footprint, or add layers.

## 4. Measured and rejected — do not retry these

| dimension | attempts | verdict |
|---|---|---|
| via steering | veto / reserve / pre-plan / price-in-search / via-first / post-hoc move | only post-hoc move helps (−5) |
| net order | big / small / region / failed-first | small-first + failed-first |
| local repair | two blocking modes / pour-trim | trim trades islands for spacing |
| pour shape | whole plane / shared / exclusive / 2-layer | shared is the frontier; exclusive costs 4 legs |
| length matching | meanders / 7 bundle geometries | arithmetically impossible (ρ) |
| stackup | 2 / 4 / 6 layers, plain and with automatic net→layer assignment | 2L dominated; 6L helps only with a hand plan (§43, §44) |
| knob sweeps | portfolio over 6 configs (pour step 3/5/8, bus-first, via cost 20, exclusive pour) | best is 511 vs 515 clearance — the frontier is flat in these knobs (§46) |
| via disc radius (5 mil) | 25 / 30 / 35 mil | 25 mil (margin 6) is the optimum; 30 → 4 dead legs + a congestion cell, 35 → 3 dead legs + an island (§59) |
| acceptance budget (5 mil) | 10 / 14 / 18 / 22 / 26 / 30 / 34 / 40 / 48 / 56 / 64 | 56 is the first budget with zero dead legs at margin 6; the curve is non-monotone (§53, §57) |
| row-crossing cost | `row_penalty` 0 / 8 / 30 | does NOT reduce track/pad (263 → 275 → 260) and makes the total worse; the crowding is around the pads, not in the gaps (§68) |
| access-via radius | `pour_step` 8 / 12 / 16 / 20 | **identical results** — saturated at 8 (§47) |
| routing grid | GRID 10 vs 5 (`--grid N --profile strict-via`) | **5 mil + reserved via discs + budget 56: 0 dead legs, 0 unconnected, 0 islands, clearance 453** — the first point that beats the 10 mil baseline (511 / 1 island) on both gated items, at ~40 min and +3045 mil of track; reproducible via that profile (two independent runs identical) and ~84–88 % of the remaining pad hits are geometry-forced (§57–§58, D6) |

## 5. Decisions on record

| id | subject | state |
|---|---|---|
| D1 | 2 vs 4 vs 6 layers | **open** — 4 is the working assumption (`--stackup 4`), recorded on every plan |
| D2 | shared pour vs exclusive pour | **superseded at 5 mil** — `strict-via` already has 0 islands at 0 dead legs, so "cut ground vs open legs" is no longer the trade; what remains is whether clearance 453 is acceptable |
| D3 | bus skew | pinout conflict, not a router gap |
| D4 | delivery | `emit_apply.py` refuses while red; rollback procedure still undefined |
| D5 | what "clearance" counts | four kinds, one implementation, track/pad included |
| D6 | routing resolution / via disc | **open** — use `strict-via` (5 mil, ~40 min, −58 clearance, −1 island, +3045 mil track) or keep the 10 mil default |

### 5.1 Decision checklist for the engineer (each row = current number + options + command)

| # | question | current | options | reproduce |
|---|---|---|---|---|
| 1 | Accept clearance 380? | 380, of which ~212 of the pad hits are forced (the pad-interpretation changed twice in §74/§78). **A relaxed rule does NOT fix it**: at 2 mil / 5 mil plus a re-pinned bus the what-if still shows 267–294 violations and 12 dead legs (§67) | (a) waive it with a note; (b) move J3/J1/U4/L1 out of the routing corridors; (c) fan out those pads instead of running one 7 mil track beside them | `--grid 5 --profile strict-via` + `forced_spacing.py` + `whatif.py` |
| 2 | 10 mil thin or 5 mil? | 380 / 0 islands (10 mil, 5 mil tracks, ~6-14 min) vs 453 / 0 islands (5 mil grid, ~27 min) | (a) thin-10mil is the default; (b) strict-via for a finer grid | both commands in §2 |
| 3 | Bus skew | 751.1 / 165.3 / 359.3 mil (ρ −0.21 / −0.37 / 0.70) | (a) accept; (b) change the pin assignment/footprint; (c) add layers | `bus_capacity.py` |
| 4 | Stackup | 4 assumed (`--stackup 4`, board says 2) | (a) confirm 4; (b) 2 (dominated); (c) 6 with a hand-written layer plan | `--profile two-layer` / `six-layer` |

## 6. First hour for any agent

```bash
# 0. context
sed -n '1,120p' easycirq/scripts/layout/STATUS.md          # this file
python easycirq/scripts/layout/ec_layout.py --help

# 1. reproduce the frontier (default = strict-via, ~40 min) and read the scorecard
python easycirq/scripts/layout/reproduce.py --dump ../retrocam-02/pcb/dump2.json \
    --place ../retrocam-02/pcb/offline/ec-placed.json --out-dir out/

# 1a. the best measured point: 5 mil, reserved via discs, 0 dead legs + 0 islands (40 min)
python easycirq/scripts/layout/reproduce.py --dump ../retrocam-02/pcb/dump2.json \
    --place ../retrocam-02/pcb/offline/ec-placed.json --grid 5 --profile strict-via --out-dir out/strict-via

# 1b. or compare configurations under one ranking rule (portfolio.json/md)
python easycirq/scripts/layout/portfolio.py --dump ../retrocam-02/pcb/dump2.json \
    --place ../retrocam-02/pcb/offline/ec-placed.json --jobs 3 --out-dir out/pf

# 2. understand the red lines instead of guessing
python easycirq/scripts/layout/spacing_audit.py --dump ../retrocam-02/pcb/dump2.json \
    --place ../retrocam-02/pcb/offline/ec-placed.json --out-dir out/
python easycirq/scripts/layout/pour_cut.py out/plan.json --dump ../retrocam-02/pcb/dump2.json \
    --place ../retrocam-02/pcb/offline/ec-placed.json
python easycirq/scripts/layout/bus_capacity.py --dump ../retrocam-02/pcb/dump2.json \
    --place ../retrocam-02/pcb/offline/ec-placed.json
python easycirq/scripts/layout/forced_spacing.py out/plan.json --dump ../retrocam-02/pcb/dump2.json \
    --place ../retrocam-02/pcb/offline/ec-placed.json

# 3. prove the delivery mechanism still works (<1 min, no routing)
python easycirq/scripts/layout/acceptance.py --plan out/plan.json --kpi out/kpi.json \
    --dump ../retrocam-02/pcb/dump2.json --stackup 4

# 4. the metrics themselves
python -m pytest tests/test_ec_layout.py tests/test_bus_order.py -q
```

Expected: reproduce prints the table in §2 and **offline gate: FAIL**; acceptance
prints `contract: PASS` (it proves the guard refuses, then emits on a green stub);
the tests pass.

## 7. What is genuinely left

1. **A hand-written layer plan** for a 6-layer stack (from the placement geometry,
   not net names), then one measurement — the only remaining tool-side lever (§44).
2. **A 2D-first routing paradigm** if clearance 515 must come down: decide the
   layer/channel plan before searching, instead of pricing vias during the search.
3. Otherwise: the three decisions in §3 belong to the engineer, and this toolchain's
   job is to keep them **measured, reproducible and refused at the door** until then.






















