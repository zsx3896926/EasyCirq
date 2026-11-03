# EasyCirq offline layout & routing toolchain (`tools/layout/`)

> **Handing this to another session?** Paste [`KICKOFF.md`](KICKOFF.md) — it carries the self-contained
> prompt, the three verification commands, the refuted list and the rules that must not be deleted.
>
> **Frozen 2026-11-03 (HANDOFF §174).** Start with [`WRAP-UP.md`](WRAP-UP.md) — what this can and cannot do,
> the three inputs that would unblock it, and what "frozen" allows (defect fixes only, no new tools).

**Start here — the ten-minute path (measured on this machine, HANDOFF §169):**

```bash
python tools/layout/verify.py                      #   46 s  repository health (12 checks)
python tools/layout/gaps_check.py --dump ../retrocam-02/pcb/dump2.json \
    --place ../retrocam-02/pcb/offline/ec-placed.json --candidate frontier-g --iters 25
                                                   # 4 min 47 s  12-row acceptance matrix
python tools/layout/pipeline.py --dump ../retrocam-02/pcb/dump2.json \
    --place ../retrocam-02/pcb/offline/ec-placed.json --candidate frontier-g \
    --profile thin-10mil --out-dir out/first
                                                   # 3 min 42 s  report.md (8 sections)
```

Total **≈ 9 min 15 s** from a clean checkout to a written report, and nothing is written to a board. The
delivery-grade profile (`strict-via-thin`, the default) takes ~45 min and is the one to use before any
decision, not for a first look.

That command answers "is this repository healthy?". It does **not** answer "is the board deliverable" —
read the four-candidate table below for that, and `gaps_check.py` for the KPI matrix.

**Mechanism:** never touch the EDA board while the offline gate is red. `emit_apply.py` refuses to emit a
red plan (exit 2) and writes nothing at all when it refuses; `acceptance.py` proves that refusal end to end
in under a minute.

---

## The state of the board in one screen

Four candidates are **legal** (parts do not overlap, pads are manufacturable) and measured at the delivery
grade; gate items are 0/0/0/0/0 for all four, LCD 41.4 and SD 31.9 are inside the 50 mil target:

| candidate | SoC pad / CAM window | clearance | CAM skew | trades |
|---|---|---|---|---|
| `frontier-i` | 26×26 / 17..24 | **146** | 837.8 | best spacing, worst CAM |
| `frontier-g` | 36×36 / 13..20 | 180 | 398.6 | middle |
| `frontier-j` | 26×26 / 11..18 | 217 | **121.8** | best CAM, worst spacing |
| `frontier-h` | 26×26 / 13..20 | 232 | 144.9 | good CAM, poor spacing |

**No point satisfies both targets.** The cause is geometric, not a search failure: J3's pads sit on a
19.7 mil pitch and U5's on 50 mil, so an 8-pin span mismatch of 212 mil predicts a 53–67 mil skew floor
before any routing detour (`HANDOFF.md` §123/§155/§156). Closing the last 96 clearance or getting CAM under
50 needs **a different connector footprint or SoC fanout** — a procurement decision, not a parameter.

Four candidates were **withdrawn** (§143–§146): `frontier-d`, `frontier-e`, `frontier-f`, `recipe-only`.
They carried overlapping parts, and two used connector pads wider than the part's own pitch, so their
numbers were partly merged copper. They stay in `candidates.py` as `deprecated_illegal` and
`regress.py` refuses them unless `--allow-illegal` is passed.

---

## Commands, by question

```bash
# is the repository healthy?  (unit tests, deterministic+legal candidates, calculators)
python tools/layout/verify.py

# what does each legal candidate cost?  (12-row matrix, or the four-way comparison)
python tools/layout/gaps_check.py --dump ../retrocam-02/pcb/dump2.json \
    --place ../retrocam-02/pcb/offline/ec-placed.json --candidate frontier-g --iters 25
python tools/layout/gaps_check.py ... --candidate all --iters 25      # four-way, ~18 min

# did anything regress against the recorded numbers?  (refuses withdrawn candidates)
python tools/layout/regress.py --dump ... --place ... --iters 25

# full delivery-grade run: route -> 11 KPIs -> plan_lint -> DFM -> footprints -> manifest
# writes report.md (8 sections) + summary.json; ~45 min
python tools/layout/pipeline.py --dump ../retrocam-02/pcb/dump2.json \
    --place ../retrocam-02/pcb/offline/ec-placed.json --candidate frontier-g --out-dir out/fg

# before searching: what is even possible?  (bounds in seconds, not after 30 routing runs)
python tools/layout/feasibility.py --dump ../retrocam-02/pcb/dump2.json

# many configurations at once: parallel + cached + rank-calibrated
python tools/layout/sweep.py --dump ../retrocam-02/pcb/dump2.json \
    --place ../retrocam-02/pcb/offline/ec-placed.json \
    --candidates frontier-i,frontier-j --iters 25 --jobs 4

# the offline calculators behind the report
python tools/layout/impedance.py   --plan out/fg/plan.json --target 50
python tools/layout/current.py     --plan out/fg/plan.json
python tools/layout/thermal.py
python tools/layout/dfm.py         --dump out/fg/candidate-dump.json --plan out/fg/plan.json
python tools/layout/footprints.py  --dump out/fg/candidate-dump.json
python tools/layout/fabrication.py --dump out/fg/candidate-dump.json --plan out/fg/plan.json

# proof that the delivery guard refuses a red plan and emits a green one
python tools/layout/acceptance.py --plan out/fg/plan.json --kpi out/fg/summary.json
```

Step-by-step routing, spacing audits and pour diagnosis are still available (`ec_layout.py`,
`spacing_audit.py`, `pour_cut.py`, `compare.py`, `portfolio.py`, `bus_capacity.py`) — see the docstrings.

---

## Speed (measured, 2026-11-03)

| | before | after | factor |
|---|---|---|---|
| delivery-grid screen (frontier-i, 3 passes) | 53.5 s | **26.2 s** | **2.04×** |
| fast profile (thin-10mil) | 11.9 s | **7.0 s** | **1.70×** |
| repeat `candidates.build` | 1.2 s | **3 ms** | 400× |
| re-running a cached sweep | ~28 s | **0.2 s** | ~140× |
| 4 configurations, 4 processes vs serial | ~1136 s | **612 s** | 1.9× |

Every speed change is accepted only if `bench.py --compare` reports a **byte-identical plan digest and an
identical KPI fingerprint**; three ideas were measured and rejected (early stop, coarse-grid screening,
`_seg_seg` inlining) and are recorded in `HANDOFF.md` §183–§187 rather than quietly dropped.

## KPI (single definition, enforced by tests)

| KPI | meaning | target |
|---|---|---|
| `unrouted_legs` | MST edges A* could not complete | 0 |
| `congestion_cells` | (x, y, layer) cells claimed by two nets | 0 |
| `nets_unconnected` | nets whose pads do not form one component | 0 |
| `clearance_violations` | track/track, via/track, via/pad **and track/pad** pairs too close | 0 |
| `pad_layer_gaps` | pads whose copper is on the wrong layer with no via nearby | 0 |
| `pour_islands` | pour access vias landing in different copper islands | 0 |
| `vias` | layer changes (access / in-pad reported separately) | minimise |
| `bus_length_spread_mil` | max−min length per CAM/LCD/SD group | < 50 |
| `total_length_mil`, `diagonal_ratio`, `layer_length_mil` | quality metrics | — |

Every metric is computed **from the plan**, so `check` judges what would be written to the board, and an
unmeasurable KPI prints `null` and fails the gate rather than passing silently.

**Ranking, when two plans disagree** (documented, so "best" is not a mood): unrouted → unconnected →
congestion → pad layer gaps → islands → clearance → bus skew → vias → length. Note that this puts
**clearance above skew**, which is why `frontier-i` is "best" by the rule and `frontier-j` is best if you
put skew first. That choice is yours to make (GAPS §155).

---

## Documents

| file | what it is |
|---|---|
| [`STATUS.md`](STATUS.md) | one-page state, including the §143 correction at the top |
| [`PRESCRIPTION.md`](PRESCRIPTION.md) | decision sheet: legal measurements, the two walls, refuted ideas, how to reproduce |
| [`GAPS.md`](GAPS.md) | defect list with an acceptance condition per item (P0 need a decision, P1 are tool-side) |
| [`HANDOFF.md`](HANDOFF.md) | the numbered evidence log (§1–§161) — every claim points here |
| [`DECISIONS.md`](DECISIONS.md) | decisions on record (D1–D7) with their caveats |
| [`WORKING-RULES.md`](WORKING-RULES.md) | the eight process rules bought with wasted rounds (bounds first, gates before metrics, parallel+cache, calibrate before ranking, few extreme points, data not numbers, three-strikes, plan ≠ result) |
| [`BUNDLE-DESIGN.md`](BUNDLE-DESIGN.md) | why a parallel-lane bus does not fit this pinout |

---

## Read this before quoting "deliverable"

* The **self-test board** (`selftest.py`, two 8-pin rows at 50 mil pitch) reaches `gate PASS`, `plan_lint`
  PASS, a legal placement and **`deliverable: YES`** with zero clearance and zero skew (§170/§172). That
  proves the *capability*.
* **RetroCam-02 does not.** Its four legal candidates sit at clearance 146–232 with CAM skew 121.8–837.8,
  because of the 19.7 : 50 mil pitch ratio (§123). Quoting the self-test board as if it were RetroCam would
  be exactly the kind of dishonesty this repository is built to prevent.
* The Gerber/Excellon files from `gerber.py` are **syntactically valid and round-trip verified, but not
  CAM-validated** - run the EDA export and its DRC before a fabricator sees them.

## NOT RUN (and why)

* **Gerber / Excellon / BOM / CPL** — never produced. They need the EDA execution layer, which this session
  never touched; `fabrication.py` produces everything *around* them and says so in its output.
* **Real stackup impedance** — `impedance.py` uses clearly-labelled assumed FR-4 numbers.
* **Real currents, powers, θja** — `current.py` / `thermal.py` run on labelled assumptions.
* **Through-hole drill units** — the dump's `hole` payload (`["SLOT", 2.4, 5.1181]`) is neither mil nor mm
  plausibly, so `dfm.py` reports it as UNRESOLVED instead of inventing findings.
* **Assembly clearance, panelisation, fiducials, stencils** — need the fabricator's process card.
