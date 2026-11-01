# STATUS — offline layout & routing for RetroCam-02 (one page)

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

```bash
# the best measured point (5 mil grid, reserved via discs) - ~40 min
python tools/layout/reproduce.py --dump ../retrocam-02/pcb/dump2.json \
    --place ../retrocam-02/pcb/offline/ec-placed.json \
    --grid 5 --profile strict-via --out-dir out/strict-via

# the 10 mil default, for comparison - ~12 min
python tools/layout/reproduce.py --dump ../retrocam-02/pcb/dump2.json \
    --place ../retrocam-02/pcb/offline/ec-placed.json --out-dir out/frontier
```

| KPI | strict-via (5 mil) | 10 mil default | gate |
|---|---|---|---|
| unrouted legs | 0 | 0 | ✅ |
| congestion cells | 0 | 0 | ✅ |
| unconnected nets | 0 | 0 | ✅ |
| pad layer gaps | 0 | 0 | ✅ |
| pour islands | **0** | **1** (+3V3/L3: 48439 + 190, 1 stranded via) | ✅ / ❌ |
| clearance violations | **453** = 35 track/track + 91 via/track + 31 via/pad + 296 track/pad | 511 = 8 / 174 / 104 / 225 | ❌ |
| bus skew CAM/LCD/SD | 751.1 / 165.3 / 359.3 mil | 713.1 / 165.3 / 297.6 | ❌ (design conflict) |
| vias (access / in-pad) | 172 (59 / 6) | 186 (59 / 6) | info |
| tracks / total length | 647 / 42044.2 mil | 527 / 38999.0 mil | info |
| 45-degree share | 0.405 | 0.411 | info |

`strict-via` is the first configuration that is not worse on **any** gated item and is
better on two (islands 1 → 0, clearance 511 → 453) with zero dead legs; it costs ~40 min
of runtime and +3045 mil of track.  It is reproducible: two independent runs came back
item by item identical (§57–§58).

Stackup: routed as **4 layers**, recorded override `--stackup 4` (the board's own
rules say `copperLayers = 2`, so the 4-layer stackup is an assumption — D1).

## 3. The red lines: cause, evidence, who decides

### 3.1 Clearance 453 — 60 % of what is left cannot be routed away

* Composition at `strict-via`: 296 track/pad and 31 via/pad dominate; the strict via
  disc is what bought the improvement (via/track 174 → 91, via/pad 104 → 31) at the
  price of copper hugging pads (track/pad 225 → 296).
* `forced_spacing.py` on that plan: **274–289 of the 327 pad hits are geometrically
  forced** — 175 pad pairs on this board have no legal corridor (J3 20 pads at 19.7 mil
  pitch with 49.2 mil tall pads need 68 mil of centre spacing for a track to pass; U4
  25.6 mil, J1 19.7 mil, L1 145.6 mil).  The forced share rose from 66–83 % to 84–88 %
  because the avoidable hits were removed, not because the board got worse.
* Improvable pool: `via/track` 91 + `track/track` 35 = 126, plus 38–53 open pad hits
  ⇒ ~165–180 of 453.
* Every knob around it has a measured optimum, not a direction: via disc 25 mil at
  5 mil (30 mil → 4 dead legs + a congestion cell, 35 mil → 3 dead legs + an island,
  §59); acceptance budget 56 (§57); `pour_step` saturated at 8 (§47).
* **Decision needed:** accept a documented waiver, move J3/J1/U4/L1, or change the
  rule/process (smaller vias, thinner tracks).
  on this board have no legal corridor; **216–272 of the 329 pad hits are forced**,
  i.e. no routing change can remove them.
* **Decision needed:** accept a documented waiver, move the parts (J3/J1/U4/L1 spacing
  from the routing corridors), change the rule/process (smaller vias, thinner tracks),
  or change the routing paradigm.  A "connector escape channel" is NOT available:
  at 19.7 mil pitch there is nothing to reserve (§48.5).

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
| 1 | Accept clearance 453? | 453, of which 274–289 pad hits are geometrically forced | (a) waive it with a note; (b) move J3/J1/U4/L1; (c) smaller vias / thinner tracks | `--grid 5 --profile strict-via` + `forced_spacing.py` |
| 2 | 5 mil or 10 mil? | 453 / 0 islands vs 511 / 1 island | (a) take strict-via (needs ~40 min per run); (b) stay at 10 mil | both commands in §2 |
| 3 | Bus skew | 751.1 / 165.3 / 359.3 mil (ρ −0.21 / −0.37 / 0.70) | (a) accept; (b) change the pin assignment/footprint; (c) add layers | `bus_capacity.py` |
| 4 | Stackup | 4 assumed (`--stackup 4`, board says 2) | (a) confirm 4; (b) 2 (dominated); (c) 6 with a hand-written layer plan | `--profile two-layer` / `six-layer` |

## 6. First hour for any agent

```bash
# 0. context
sed -n '1,120p' tools/layout/STATUS.md          # this file
python tools/layout/ec_layout.py --help

# 1. reproduce the frontier (10-15 min) and read the scorecard
python tools/layout/reproduce.py --dump ../retrocam-02/pcb/dump2.json \
    --place ../retrocam-02/pcb/offline/ec-placed.json --out-dir out/

# 1a. the best measured point: 5 mil, reserved via discs, 0 dead legs + 0 islands (40 min)
python tools/layout/reproduce.py --dump ../retrocam-02/pcb/dump2.json \
    --place ../retrocam-02/pcb/offline/ec-placed.json --grid 5 --profile strict-via --out-dir out/strict-via

# 1b. or compare configurations under one ranking rule (portfolio.json/md)
python tools/layout/portfolio.py --dump ../retrocam-02/pcb/dump2.json \
    --place ../retrocam-02/pcb/offline/ec-placed.json --jobs 3 --out-dir out/pf

# 2. understand the red lines instead of guessing
python tools/layout/spacing_audit.py --dump ../retrocam-02/pcb/dump2.json \
    --place ../retrocam-02/pcb/offline/ec-placed.json --out-dir out/
python tools/layout/pour_cut.py out/plan.json --dump ../retrocam-02/pcb/dump2.json \
    --place ../retrocam-02/pcb/offline/ec-placed.json
python tools/layout/bus_capacity.py --dump ../retrocam-02/pcb/dump2.json \
    --place ../retrocam-02/pcb/offline/ec-placed.json
python tools/layout/forced_spacing.py out/plan.json --dump ../retrocam-02/pcb/dump2.json \
    --place ../retrocam-02/pcb/offline/ec-placed.json

# 3. prove the delivery mechanism still works (<1 min, no routing)
python tools/layout/acceptance.py --plan out/plan.json --kpi out/kpi.json \
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














