# WORKING-RULES — how to do this faster next time (distilled from §1–§177)

Eight rules, each one bought with wasted rounds. They are written so that a new agent can follow them
without reading the 7700-line log; where a rule is mechanical, the tool that enforces it is named.

| # | Rule | Trigger | Action | Enforced by |
|---|---|---|---|---|
| **R1** | **Bounds before search** | any new board, or any new target | run `feasibility.py` first: bus-skew floor (straight spread *and* the span-mismatch bound), corridor conflicts, capture problems. If a floor exceeds the target, stop and name what must change | `feasibility.py` (§176) |
| **R2** | **Legality and manufacturability are gates, not KPIs** | always | overlapping parts, pad ≥ pitch, pad smaller than its hole, board rule below the router's own via, DFM findings — all must fail the pipeline, and must fail it from day one | `pipeline.py` legality gate (§144/§145), `dfm.py` (§150), `footprints.py` (§151) |
| **R3** | **Evaluate in parallel, cache everything** | more than one configuration | `sweep.py --jobs N`; the cache key is the content hash of dump + placement + candidate + profile + iterations, so a re-run after a doc change is free (measured: 189 s → 0.2 s) | `sweep.py` (§177) |
| **R4** | **Never rank on a cheap screen unless calibrated** | before using a fast screen to pick a winner | `sweep.py --calibrate <delivery iters>`; only rank if the Spearman agreement is ≥ 0.8 on both clearance and skew. This effort compared a 25-pass 157.1 with a 70-pass 398.6 and paid for it | `sweep.py --calibrate` (§177) |
| **R5** | **Few extreme points, one confirmation each** | during exploration | keep the 3–4 non-dominated points (clearance-best, skew-best, the trade-offs), not fifteen middle values; confirm each published claim once at the delivery grade | `sweep.py --pareto` (§177); the four candidates are exactly this (§149/§155) |
| **R6** | **Candidates are data; documents are generated** | whenever a configuration is adopted or a KPI is quoted | add a candidate (board change + recipe + constants + measured record), never hand-edit numbers; regenerate tables from a run instead of copying them | `candidates.py` (§128), `regress.py` (§129), `sweep.py --write-table` (§179) |
| **R7** | **Three rounds without improvement → change the question** | three consecutive rounds with no KPI gain | stop tuning parameters; switch to root-cause/bound analysis or to changing the part. This effort switched only at §127, after ~20 parameter rounds | process rule — see the log §105–§127 |
| **R8** | **A plan is not a result** | any status report | unrun work is labelled `NOT RUN`; a number is quoted with the command that produced it; "done" means a command exited 0 with the asserted value | every tool prints its own NOT RUN list (§152/§156); `verify.py` (§161) |

## The one-paragraph version

Compute the bounds first (R1), make physical validity a gate rather than a metric (R2), then explore in
parallel with a cache (R3) — but only trust a fast screen after calibrating it against the delivery grade
(R4), and only keep the extreme points (R5). Record configurations as data and generate the documents from
runs (R6). If three rounds in a row buy nothing, the question is wrong: change it (R7). And never let a plan
be read as a result (R8).

## What these rules do *not* fix

The physics (a 19.7 mil connector against 50 mil pads has a 53–67 mil skew floor), and the missing external
inputs (connector choice, a sourced skew spec, EDA authorisation). Those are decisions, not speed.
