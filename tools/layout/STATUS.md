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
python tools/layout/reproduce.py --dump ../retrocam-02/pcb/dump2.json \
    --place ../retrocam-02/pcb/offline/ec-placed.json          # default profile: frontier
```

| KPI | value | gate |
|---|---|---|
| unrouted legs | 0 | ✅ |
| congestion cells | 0 | ✅ |
| unconnected nets | 0 | ✅ |
| pad layer gaps | 0 | ✅ |
| clearance violations | **511** = 8 track/track + 174 via/track + 104 via/pad + 225 track/pad | ❌ |
| pour islands | **1** (+3V3 on L3: 48439 + 190 cells, 1 access via stranded) | ❌ |
| bus skew CAM/LCD/SD | **713.1 / 165.3 / 297.6 mil** | ❌ (design conflict) |
| vias (access / in-pad) | 186 (59 / 6) | info |
| tracks / total length | 527 / 38999.0 mil | info |
| 45-degree share | 0.411 | info |
| layer distribution | L1 17076.7 / L2 13529.3 / L3 5231.5 / L4 3161.5 mil | info |

`frontier` = shared pours with `pour_step=8`; it is the best point `portfolio.py`
found over six configurations (clearance 511 vs 515 for `pour_step=5`, every other
KPI identical). The gain is 0.8 % — reported because it is real and deterministic,
not because it is meaningful.

Stackup: routed as **4 layers**, recorded override `--stackup 4` (the board's own
rules say `copperLayers = 2`, so the 4-layer stackup is an assumption — D1).

## 3. The three red lines: cause, evidence, who decides

### 3.1 Clearance 511 — a deliberate trade, and mostly a connector-escape problem

* Composition is in the table above; `spacing_audit.py` prints it per profile, and
  `spacing_audit.py --top` names the owners of every hit.
* Where it actually lives (HANDOFF §47): of the 225 track/pad hits only **15** come
  from pour-net stubs. The violated pads are the **connectors and the inductor** —
  `L1.1` (7), `J1.A5` (7), `J3.10–J3.14` (5–6 each), `U4.3` (6) — and the via-on-pad
  hits are `J3.3/5/6/7`, `U5.15`, `L1.1`. So this KPI is dominated by **not enough
  escape channels at J3/J1/U4/L1**: a placement/escape problem, not a pour or
  via-steering problem.
* Deficits are small (`via/track` mean 4.5 mil, `via/pad` mean 11.4 mil): near misses
  from routing with an **overlap-only veto** for vias. Enforcing full via clearance
  during the search was measured at **unrouted 7 → 33** (HANDOFF §35).
* `pour_step` is saturated (8/12/16/20 identical, §47), so that knob is closed — as
  are veto / reserve / pre-plan / price-in-search / via-first (§40.4).
* **Most of it is geometry, not implementation** (`forced_spacing.py`, §48): the pads
  that get run over are on parts whose pitch leaves no legal corridor at all —
  J3 20 pads at 19.7 mil pitch with 49.2 mil tall pads (a track beside one needs
  68 mil of centre spacing), U4 25.6 mil, J1 19.7 mil, L1 145.6 mil.  175 pad pairs
  on this board have no legal corridor; **216–272 of the 329 pad hits are forced**,
  i.e. no routing change can remove them.
* **Decision needed:** accept a documented waiver, move the parts (J3/J1/U4/L1 spacing
  from the routing corridors), change the rule/process (smaller vias, thinner tracks),
  or change the routing paradigm.  A "connector escape channel" is NOT available:
  at 19.7 mil pitch there is nothing to reserve (§48.5).

### 3.2 Pour islands 1 — a design conflict

* It is **not** the ground: L4 GND is one piece (49346 cells). The cut is **+3V3 on
  L3**, split into 48439 + 190 cells by `BUZ_G` (572 mil on that layer), `CAM_VSYNC`,
  `CAM_SIOD`, `CAM_PCLK` (`pour_cut.py`).
* One access via (J3.1) sits in the pocket, so that +3V3 pin reaches **only its own
  island**: copper-open while every connectivity check says "connected".
* It cannot be rescued by moving copper: within 20 grid cells there are 655 main-pour
  cells, 147 with a clean via disc, and **0 reachable by a legal pad stub**
  (`rescue_island_vias`, §42.3).
* Both pour escapes were measured: `--pour-trim` without a spacing guard bought zero
  islands with 130 track/track violations; with a legal, layer-aware re-route it
  leaves the island at 1 and pushes LCD skew 165 → 467 (§41, §42).
* **Decision needed:** move/reroute the L1 copper around J3, move J3, or add layers.

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
| access-via radius | `pour_step` 8 / 12 / 16 / 20 | **identical results** — saturated at 8 (§47) |
| via clearance margin | `via_margin` 2 / 3 / 4 | **identical** — the 10 mil grid quantises it: margins 1–5 reserve the same 9-cell disc, ≥6 is the unroutable full-clearance case (§49) |
| routing grid | GRID 10 vs 5 (`reproduce.py --grid N`) | 10 mil: 0 dead legs + 1 island + clearance 511.  5 mil budget 26: **0 dead legs + 0 islands at clearance 738** (budget 10 gives 525 but 5 dead legs; budget 64 gives best skew 712.3 but clearance 831).  Open trade, D6 (§50–§53) |

## 5. Decisions on record

| id | subject | state |
|---|---|---|
| D1 | 2 vs 4 vs 6 layers | **open** — 4 is the working assumption (`--stackup 4`), recorded on every plan |
| D2 | shared pour vs exclusive pour | **open** — both non-dominated (open legs vs whole ground); needs engineering call |
| D3 | bus skew | pinout conflict, not a router gap |
| D4 | delivery | `emit_apply.py` refuses while red; rollback procedure still undefined |
| D5 | what "clearance" counts | four kinds, one implementation, track/pad included |

## 6. First hour for any agent

```bash
# 0. context
sed -n '1,120p' tools/layout/STATUS.md          # this file
python tools/layout/ec_layout.py --help

# 1. reproduce the frontier (10-15 min) and read the scorecard
python tools/layout/reproduce.py --dump ../retrocam-02/pcb/dump2.json \
    --place ../retrocam-02/pcb/offline/ec-placed.json --out-dir out/

# 1a. the other side of D6: 5 mil grid, 0 dead legs + 0 islands (20 min)
python tools/layout/reproduce.py --dump ../retrocam-02/pcb/dump2.json \
    --place ../retrocam-02/pcb/offline/ec-placed.json --grid 5 --best-effort-budget 26 --out-dir out/grid5

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











