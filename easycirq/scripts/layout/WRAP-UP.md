# WRAP-UP — state of the offline layout & routing capability (frozen 2026-11-03, HANDOFF §174)

This document is the **hand-over and the restart conditions**. It answers three questions in order:

1. what this capability can and cannot do today,
2. what it would take to go further (and who has to decide),
3. what "frozen" means for future changes.

Everything here is measured; the section numbers point into `HANDOFF.md` for the evidence.

---

## 1. What it can do

| Capability | Evidence |
|---|---|
| Route a captured board offline (2 or 4 layers, pours, negotiated A*) and KPI it | 11 KPIs on every run; `frontier-i` 70-pass: 550 tracks / 37840.5 mil (§174) |
| Refuse to touch a live board while the gate is red | `emit_apply` exit 2 **and writes nothing at all** (§160, asserted) |
| Tell you *how far* a board is from deliverable, and why | four legal candidates: clearance 146–232 ↔ CAM 121.8–837.8; geometric floor 53–67 mil (§123/§155) |
| Prove the pipeline **can** go green | self-test board: clearance 0, skew **0.0**, `deliverable: YES`, contract PASS (§170/§172) |
| Run on a **different** board without code changes | 2-layer capture, negative coordinates, no bus groups: 129 tracks / 19857 mil (§168) |
| Produce manufacturing files and verify them by reading back | 4 copper Gerbers + `drill.drl` + `placement.cpl`; 566 tracks / 183 holes round-trip (§171) |
| Check manufacturability and parts | DFM screen (edge/mask/width/drill), footprint audit, fabrication manifest (§150–§152) |
| Electrical sanity on stated assumptions, or on yours | impedance, current (IPC-2221), thermal — all take external input files and say where the numbers came from (§131–§133, §167) |
| Reproduce a result and catch a regression | `verify.py` 13 checks / 46 s; `regress.py` refuses withdrawn candidates (§129/§148) |
| Hand over without reading 7700 lines | `README` first screen: 9 min 15 s to the first report (§169); topic index (§163) |

## 2. What it cannot do (and why that is not a code problem)

| Cannot | Reason | What would fix it |
|---|---|---|
| Make RetroCam-02 `deliverable: YES` | J3 is a 19.7 mil pitch, U5's pads are 50 mil: an 8-pin span mismatch of 212 mil implies a 53–67 mil skew floor before any detour (§123). Clearance has 213 of 244 pad-class hits with **no corridor** at the 6 mil rule (§93); a 3 mil rule still leaves 76 % (§94) | different connector footprint / SoC fanout (GAPS G1/G2) |
| Produce a fab-ready Gerber package | `gerber.py` output is syntactically valid and round-trip verified, **not CAM-validated**; slots are deliberately not emitted; no BOM with LCSC part numbers | the EasyEDA execution layer: its export + DRC + BOM (GAPS G10) |
| Promise impedance/current/thermal correctness | the tools run on **labelled assumptions** until a real stackup / loads / powers are supplied | the fabricator's stackup card + measured currents/powers (D5 makes that a one-line swap) |
| Check through-hole **slots** against a process minimum | the dump's slot payload had no documented unit; it was inferred (0.1 mm) and self-checked, and it flags J1's 0.24 mm slot against an **assumed** 0.30 mm minimum | the fabricator's slot rule (GAPS G11) |
| Judge assembly clearance, panelisation, fiducials, stencils | needs the process card and assembly data | those inputs |

## 3. What it would take to go further — three inputs, no code

1. **A connector decision** (GAPS G1+G2): a part with a coarser pitch, or a different CAM pin assignment on
   the SoC, or an explicit acceptance that this design cannot hold both targets. Any of the three unblocks
   the next measurement round.
2. **A skew spec with a source** (G3): the `<50 mil` target has never been derived from the camera interface
   timing. A datasheet hour turns it into a real requirement — which either retires the item or confirms it.
3. **EDA authorisation** (G10): Gerber/Excellon/BOM/CPL through the EDA, plus its DRC. This session never
   touched that layer; `fabrication.py` and `gerber.py` cover everything *around* it.

The ranking rule is now decided: **clearance before skew** (DECISIONS **D8**), which is why `frontier-i`
(146 / 837.8) is the primary candidate and `frontier-j` (217 / 121.8) is the comparison point.

## 4. What "frozen" means

* **No new tools.** The capability is complete for what it can honestly claim; adding more only widens the
  maintenance surface (15 scripts already).
* **Defect fixes are still welcome** — especially anything that produces a *wrong* number or a *false*
  verdict. The guards that make wrongness loud stay: `verify.py`, `regress.py`, the legality gate, the
  delivery guard.
* **A re-measurement request is fine**: `pipeline --candidate <name>` reproduces any point in 20–45 min, and
  `gaps_check --candidate all` compares all four in ~18 min.
* **Any new board** must be added as a *candidate or a capture*, never by hand-editing numbers: the recorded
  values in `candidates.py` are what `regress.py` checks against.

## 4b. The two speed tools added after the freeze review (§176/§177)

* `feasibility.py` — computes the bus-skew floor (straight-line spread **and** the span-mismatch bound
  `hypot(D, Δ) − D`), the corridor-conflict count and the capture's own physical problems **before** any
  search. On RetroCam it reports floors of 176 / 159 / 263 mil against a 50 mil target in seconds.
* `sweep.py` — parallel (`--jobs`), cached (re-runs are ~0.2 s) and **calibrated**: `--calibrate 70`
  answers "may this cheap screen be used to rank configurations?" with a Spearman threshold, which is
  exactly the mistake that cost this effort several rounds (§148).

## 4c. If you pick this up again

Read [`WORKING-RULES.md`](WORKING-RULES.md) first: eight rules bought with wasted rounds
(bounds before search, gates before metrics, parallel + cache, calibrate before ranking, few extreme
points, candidates as data, three-strikes, plan ≠ result).

## 4d. Performance work (2026-11-03) — what it bought, and what it did not

| speed item | status | evidence |
|---|---|---|
| ① bench baseline + profile | **DONE** | `bench.py`, profile in §180 (A* 72%, `dict.get` 27 s) |
| ② sweep result DB + `--progress/--brief` | **DONE** | §184 (SQLite, no duplicate rows, per-run seconds) |
| ③a early stop | **NOT KEPT** | measured 1.6%, mechanism opt-in and off (§183) |
| ③b two-phase grid | **NOT KEPT (coarse)** / same-grid protocol available | coarse ranking disagreed with the delivery run (§185) |
| ④ numpy bitmap | **DONE (opt-in, measured slower)** | equivalent paths, 27.5 s vs 26.2 s (§189) |
| ④ bucket frontier | **DONE (opt-in, no gain)** | two-level queue, identical plan digest `63de4c04…`, 21.5 s vs 21.5 s (§191) |
| ⑤ incremental re-route | **NOT RUN as an optimisation** | implemented + gated on KPI equality; KPI differs on both measured moves, so it falls back (§190/§192) |


Measured on this machine, `bench --iters 3`, each spot in its own process:

| spot | before | after | factor | KPI |
|---|---|---|---|---|
| retrocam/frontier-i (delivery grid) | 53.5 s | **26.2 s** | **2.04×** | identical |
| retrocam/frontier-i (thin-10mil) | 11.9 s | **7.0 s** | **1.70×** | identical |
| second-2layer | 2.1 s | 2.0 s | 1.05× | identical |
| selftest | 0.1 s | 0.1 s | 1.00× | identical |

What produced it (each verified against **stored plan SHA256 digests**, which must stay byte-identical):

1. A* nodes became integer indices with an int-keyed cost map (§181);
2. the A* hot path was fully inlined — `cost_of`/`idx_of`/`h`/`cell_of` were 100M+ calls (§186);
3. `candidates.build` is memoised on content: 1.2 s → 3 ms for a repeat build (§182).

Tooling around the runs (no KPI effect): `sweep.py` evaluates in parallel (~1.9× on 4 jobs), caches results
(0.2 s re-run), keeps a queryable SQLite of every run (`--db-report`), marks Pareto points, writes tables
into documents, and calibrates a cheap screen against the delivery grade before it may be trusted
(**rho 0.80 clearance / 1.00 CAM** on the same grid, §178).

### Measured and NOT kept

| Idea | Measured | Decision |
|---|---|---|
| early stop when the score plateaus | 1.6% faster, identical plan | mechanism kept, **off by default** (§183) |
| **A\* cost/g tables: dict → preallocated list** | **32.1 s → 34.0 s (slower)**, then **32.4 s** with a cached buffer + touched-reset — i.e. a wash at best | **reverted** (§193) |
| **compiled inner loop (Cython / Rust)** | — | **NOT RUN**: no C compiler, no Cython, no numba, no cargo on this machine. `cffi` is present but cannot build without a compiler (§193) |
| two-phase on a **coarse 10 mil** grid | ranking disagreed with the delivery run (wrong winner promoted) | **coarse grid not calibrated - opt-in with a warning** (§185) |
| inlining `_seg_seg` | ~0.7%, inside the noise | kept for clarity, not counted as a speed-up (§186.1) |

### ④ numpy bitmap / bucket queue — implemented, measured, one kept, one removed

* **numpy obstacle bitmap**: implemented (`astar(bitmap_obstacles=True)`), proven equivalent by an exact
  path comparison, and measured **slower** (27.5 s vs 26.2 s) because the bitmap is rebuilt per search.
  It stays **opt-in and off by default** (§189).
* **bucket frontier** (`astar(frontier="bucket")`): a two-level queue (one heap per integer f-bucket plus a
  heap of active keys). **Proven equivalent**: the same plan digest (`63de4c04…`), 365 tracks, clearance
  139, and the same 21.5 s. Two bugs were found while making it correct (entries silently dropped when a
  drained bucket was re-filled, §191.1). It is **not faster**, so it stays opt-in.
  A naive single-pointer Dial queue was tried first and did not finish in 25 minutes - non-monotone f - and
  that attempt is recorded rather than hidden (§189.2).

### ⑤ incremental re-route — implemented and measured

**Status: NOT RUN as an optimisation (it does not meet the KPI-equivalence bar).**  It exists as a tool and
an upper bound, with a gate: `incremental_run()` compares the six gate KPIs and the three bus groups against
the full re-route, and **falls back to the full result whenever they differ** (`accepted`/`fallback_used`
are printed and tested, §192).

`route()` gained `seed_routed=` and `only_nets=`; `incremental.py --run` re-routes only the dirty nets on
top of the kept copper and prints the comparison:

| part moved | incremental | full | speed-up | clearance (inc / full) |
|---|---|---|---|---|
| U4 (+40 mil, 5 of 54 nets dirty) | **1.7 s** | 21.9 s | **12.9×** | **161 / 192** |
| U5 (+50 mil, 37 of 56 nets dirty) | **16.3 s** | 22.3 s | 1.37× | **178 / 272** |

The plans are **not identical** and the KPIs are **not equal** — kept copper constrains the re-route. The
tool prints both rows, and the acceptance table records it as: **not equivalent, off by default, counted as
a tool + upper bound, not as a like-for-like replacement**. The clearance was *better* incrementally on both
moves; that is reported, not generalised (one board, three passes, two moves).


## 4e. Equivalence gate + the A* data-structure attempt (2026-11-04, §193)

### First: a gate that can fail

`bench --compare` compares **KPI fingerprints**, and two different plans can produce the same
KPI set. Before touching the inner loop, `equivalence.py` was added: it hashes the plan the same
way `emit_apply` does —

```python
sha256(json.dumps(normalise(plan), sort_keys=True))
```

— which is the identity `emit_apply` already refuses to write on. The gate is only useful if it
can fail, so it was checked both ways:

| check | result |
|---|---|
| same code, same iters | `plan identical`, exit 0 |
| same code, **iters 3 → 1** | **`PLAN CHANGED`**, exit 1, and it names what moved (tracks 555→552, vias 138→120, clearance 150→172) |

Two gates now have to pass, and they measure different things:

```
equivalence.py --compare   the ARTEFACT must be byte-identical   (stronger)
bench.py --compare         the METRICS must match, and reports time
```

### Then: the compile route, and why it did not happen

The plan was Cython or Rust for the A\* hot loop. This machine has **no C compiler** (`cl`,
`gcc`, `clang` all absent), no `cargo`/`rustc`, no `Cython`, no `numba`, and no `setuptools`.
`cffi` 2.1.1 is installed but cannot build an extension without a compiler. So the route is
**NOT RUN**, not "attempted and hard".

The substitute was the same idea without a compiler: the profile shows **194,375,071 `dict.get`
calls**, so replace the two hot dictionaries with dense preallocated lists (node indices are
dense by construction, `0 ≤ n_idx < L*W*H`, so a list subscript needs no guard).

Measured, three ways:

| variant | retrocam/frontier-i @ 3 iters | plan | verdict |
|---|---|---|---|
| dict (current) | **32.1–32.6 s** | identical | — |
| list, allocated per call | **34.0 s** (slower) | identical | reverted |
| list, cached + reset only touched | **32.4 s** (a wash) | identical | reverted |

The first version lost because a search touches ~540k nodes and this board runs **654 searches**:
initialising the buffer cost more than the hash lookups saved. Caching the buffer removed that
but bought nothing, because on CPython 3.13 `dict.get(int)` is already about as fast as a list
subscript, and the touched-list `append` on every improvement paid back the remainder.

**A caveat about the 27 s figure:** it came from `cProfile`, which inflates per-call overhead, and
194M calls is exactly the shape it inflates most. In wall time the lookups are a much smaller
share than the profile suggests. That is why replacing them did not move the needle.

**Conclusion: `astar` keeps its dictionaries.** The gate stays — it is cheap, it runs in ~35 s,
and it is the thing that would have caught this class of change going wrong.

### NOT RUN (stated, not implied)

* incremental quality at the delivery grade (25/70 passes) - only 3-pass runs were compared (§190);
* an automatic "dirty ratio > X ⇒ full re-route" policy;
* **compiled inner loop** (Cython/Rust).

## 5. Reproduce the state in three commands

```bash
python easycirq/scripts/layout/verify.py                       # 46 s: 13 health checks (incl. the green path + Gerber round trip)
python easycirq/scripts/layout/gaps_check.py --dump ../retrocam-02/pcb/dump2.json \
    --place ../retrocam-02/pcb/offline/ec-placed.json --candidate all --iters 25    # ~18 min: the four points
python easycirq/scripts/layout/pipeline.py --dump ../retrocam-02/pcb/dump2.json \
    --place ../retrocam-02/pcb/offline/ec-placed.json --candidate frontier-i --out-dir out/fi   # ~20 min: the report
```

## 6. The honest one-liner

> The toolchain knows what it can and cannot do, refuses to pretend otherwise, and can prove both. What it
> cannot do is turn this particular board into a shippable one — and that decision belongs to the person who
> chooses the connector.
