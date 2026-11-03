# PRESCRIPTION — legal, measured state of RetroCam-02 (rewritten §154)

This file is the **decision sheet**: what the toolchain can honestly claim, what it cannot, and what a human
has to decide. Everything here is measured by a command in this directory, and every number names the
section of `HANDOFF.md` it came from.

**Read this first if you are picking the work up.** Several earlier numbers in this repository were later
found to rest on illegal placements, and they have been withdrawn — the withdrawal is stated inline, with
the section that proves it, not quietly deleted.

Two settings are shipped:

| setting | profile | what it is | runtime |
|---|---|---|---|
| delivery grade | `strict-via-thin` | 5 mil grid, 5 mil tracks, `pad_guard 2.5`, via reserve 25 mil, budget 56 | ~45 min |
| fast iteration | `thin-10mil` (default) | 10 mil grid, 5 mil tracks, `pad_guard 2.0`, budget 16 | 6–14 min |

Neither profile is deliverable, and a DRC waiver is **not** available (the delivery contract forbids
waiving PCB DRC).

---

## 1. The one thing to understand: legality was wrong for a while

`n_overlaps` (parts physically overlapping) was **not** checked by the router, by `plan_lint` or by any KPI
until §143. When it finally was:

| candidate | overlaps | outside | verdict |
|---|---|---|---|
| `frontier-g` | 0 | 0 | **LEGAL** |
| original placement | 0 | 0 | **LEGAL** |
| `frontier-d` / `frontier-e` / `frontier-f` / `recipe-only` | 1–2 | 0–1 | **ILLEGAL — withdrawn** |

The illegal ones are marked `deprecated_illegal` in `candidates.py` and **refused by default** (§148).
Two of them also used pads **wider than the part's pitch** (J1/J3 are 19.7 mil pitch; a 20 mil wide pad
fuses into its neighbour, §144), so part of their apparent improvement was merged copper.

`pipeline` now gates legality and DFM, and `deliverable` cannot be true without them (§153).

---

## 2. The legal measurements (delivery grade, 70 passes)

| | legal baseline (as designed) | `frontier-g` | `frontier-h` | `frontier-i` | `frontier-j` |
|---|---|---|---|---|---|
| Board | 2766×1978 mil | 3266×2478 (grown, §122) | 3266×2478 | 3266×2478 | 3266×2478 |
| Connector pads | as designed | J1/J3 12×16 (§145) | J1/J3 12×16 |
| SoC pads (U5) | as designed | 36×36 | 26×26 |
| Power width | 8.6 mil | 12 mil (IPC-2221, §132) | 12 mil |
| Gate items (dead/congestion/unconnected/pad gaps/islands) | 0/0/0/0/0 | **0/0/0/0/0** | **0/0/0/0/0** |
| **Clearance violations** | **398** | 180 | 232 | **146** | 217 |
| **Bus skew CAM / LCD / SD** | 1704.6 / 165.3 / 220.1 | 398.6 / **41.4** / **31.9** | 144.9 / **41.4** / **31.9** | 837.8 / **41.4** / **31.9** | **121.8** / **41.4** / **31.9** |
| Vias / tracks / total length | 166 / 717 / 40704 | 166 / 566 / 38887 | 162 / 565 / 38054 |
| L1 share / 45° | 52.0% / — | 56.0% / 0.436 | 55.6% / 0.410 |
| Placement | LEGAL | LEGAL | LEGAL |

**The trade-off is real and measured**: a larger SoC pad buys routing room (clearance 180) and costs CAM
skew (398.6); a smaller one does the opposite (232 / 144.9). No parameter inside this design gets both.

---

## 3. Why it stops here (the two P0 walls)

### 3.1 Clearance → 0 (G1)

* Legal floor reached: **180** (`frontier-g`). The pad-size lever is **saturated** — going *below* 20 mil
  wide on the connector pads made clearance **worse** (248–251, §138), and pin/pairing/placement choices are
  already at their legal limit (any J3 left shift overlaps U5, §145).
* 213 of 244 pad-class violations had **no legal corridor at all** at 6 mil (§93); relaxing the rule to
  3 mil still left **76 %** (§94).
* What would move it: **a different connector footprint** (coarser pitch, so pads can be wider and still
  legal) or **SoC pad fanout**. Both are procurement decisions.

### 3.2 CAM skew → < 50 (G2)

* Legal floor reached: **144.9** (`frontier-h`), down from the 1704.6 legal baseline.
* Every mechanism was measured and rejected: pin blocks (§108/§123), 8 pairing permutations (§116),
  part moves (§122/§123), board area alone (§122), a 25 mil connector pitch (§124 — worse, 217),
  layer forcing (§125, 422–837), meander compensation (§126 — needs +89 mil, only 26 mil of straight run
  exists), 7 bundle geometries (§127 — 6 of 8 members at best).
* The geometry: J3's pads sit on a 19.7 mil pitch and U5's on 50 mil — an 8-pin span mismatch of 212 mil,
  which alone predicts a 53–67 mil floor before any routing detour (§123).
* What would move it: **a connector with a coarser pitch** (28 mil measured 145 clearance before the
  legality work, §139) or **a different CAM pin assignment on the SoC**.

### 3.3 The skew target itself (G3)

`< 50 mil` is an internal number. Nobody derived it from the camera interface's timing. An hour of
datasheet work could replace the target with a justified value — and would either retire this item or
confirm it.

---

## 4. What is already done and does not need re-deciding

| Item | Result | Evidence |
|---|---|---|
| One-command candidate chain | `pipeline --candidate frontier-g` | §128 |
| Regression gate on achieved numbers | `regress.py`, deprecated candidates refused | §129/§148 |
| Acceptance matrix (one command, 12 rows) | `gaps_check.py` | §135/§153 |
| Impedance / clearance-to-target | `impedance.py` — outer 5 mil is **87 Ω**, inner 5 mil is 51 Ω | §131 |
| Current capacity | `current.py` — 12 mil carries 1.01 A at a 10 °C rise | §132/§134 |
| Thermal screen | `thermal.py` (assumed powers + review checklist) | §133 |
| DFM screen | `dfm.py` — edge/mask/width pass; drill unit unresolved by design | §150 |
| Footprint audit | `footprints.py` — 2 review flags out of 42 parts | §151 |
| Fabrication manifest | `fabrication.py` — exports NOT RUN (needs the EDA layer) | §152 |

---

## 5. Measured and rejected — do not retry

| Idea | Result |
|---|---|
| Finer grid (5 mil) | free win, already on (§89) |
| Thinner copper (5 mil) | already on; 4 mil broke the board minimum (§82) |
| Shrinking U4/L1 pads for clearance | not the lever — J1/J3/U5 own 120 of 165 corridors (§137) |
| Connector pad 20 mil on a 19.7 mil pitch | **illegal** (fused pads, §144) |
| Moving J3 left to help CAM | overlaps U5 at every offset tested (§145) |
| Re-placing without locks | rotates 26 parts, lifts copper 80 % (§141/§142) |
| Bundle routing (7 geometries) | 6 of 8 members land at best (§127) |
| Meander compensation | needs +89 mil, capacity 26 mil (§126) |
| Forcing CAM onto one layer | 422–837 skew (§125) |
| Relaxing the spacing rule to 3 mil | 76 % of the violations remain (§94) |
| Pad shrink below 20 mil on the connector | clearance gets worse, 248–251 (§138) |

---

## 6. How to reproduce (all offline; minutes to tens of minutes)

```bash
# 12-row acceptance matrix, ~5 min, default candidate is the legal one
python easycirq/scripts/layout/gaps_check.py --dump ../retrocam-02/pcb/dump2.json \
    --place ../retrocam-02/pcb/offline/ec-placed.json --iters 25

# regression gate (refuses deprecated candidates)
python easycirq/scripts/layout/regress.py --dump ../retrocam-02/pcb/dump2.json \
    --place ../retrocam-02/pcb/offline/ec-placed.json --iters 25

# delivery grade run, ~45 min, writes report.md (8 sections) + summary.json
python easycirq/scripts/layout/pipeline.py --dump ../retrocam-02/pcb/dump2.json \
    --place ../retrocam-02/pcb/offline/ec-placed.json --candidate frontier-g --out-dir out/fg

# the supporting calculators
python easycirq/scripts/layout/impedance.py --plan out/fg/plan.json --target 50
python easycirq/scripts/layout/current.py   --plan out/fg/plan.json
python easycirq/scripts/layout/thermal.py
python easycirq/scripts/layout/dfm.py        --dump out/fg/candidate-dump.json --plan out/fg/plan.json
python easycirq/scripts/layout/footprints.py --dump out/fg/candidate-dump.json
python easycirq/scripts/layout/fabrication.py --dump out/fg/candidate-dump.json --plan out/fg/plan.json
```

---

## 7. What the next person needs from the engineer

1. **A connector decision** (this closes G1 and G2 together): a part with a coarser pitch, or an explicit
   acceptance that this design cannot hold both targets.
2. **The camera interface timing** (G3), so the skew target stops being a guess.
3. **Permission to touch the EDA layer** (G10): Gerber, BOM and CPL have never been produced in this
   session, and no board can ship without them.
