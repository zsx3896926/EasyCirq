# Calculation review

Method: every hard decision is recomputed **independently** — either by hand
from the stated formula, or with a separate small calculation that does not call
the block — and then compared with the frozen CLI output (benchmark cases and
unit tests). The test files also carry the formula above each assertion. No
expected value in this review was copied from generator output without an
independent derivation.

This is a **self-review**, not a blind review: the same task authored the core and
the modules. There was no independent reviewer available in this environment, so
"independently derived" means "derived again from the physics with a different
arithmetic path", not "reviewed by a second person".

## F1 LED

| Claim | Independent derivation | Generated | Verdict |
|---|---|---|---|
| selected value (example) | nominal headroom `5.0−2.0−0.2 = 2.8 V`; `2.8/5 mA = 560 Ω`; 560 is E24 | 560 Ω | match |
| `I_max` | `(5.25−1.8−0)/(560·0.99) = 3.45/554.4 = 6.22294 mA` | 6.22294372294 mA | match |
| `I_min` | `(4.75−2.2−0.4)/(560·1.01) = 2.15/565.6 = 3.80127 mA` | 3.80127298444 mA | match |
| resistor power | `3.45²/554.4 = 21.4692 mW`; rating at 50 % derating `42.9383 mW` | same | match |
| boundary | 100 Ω, 0 %, 5 V, Vf 1.8: `(5−1.8)/100 = 32.000 mA`; 32.000 mA accepted, 31.999 mA rejected | accepted / rejected | match |
| exact point Vf | a nominal-only Vf cannot bound a worst case | `needs_device_facts` | match |

## F2 button

| Claim | Independent derivation | Generated | Verdict |
|---|---|---|---|
| RC value (example, 1 ms) | `10 kΩ · 100 nF = 1.000 ms` (E24/E12) | 10 kΩ + 100 nF | match |
| closed contact current | `3.465/(10 k·0.99 + 0) = 0.35 mA` | 0.35 mA | match |
| open-state level (pull-up) | `3.135 − 1 µA·(10 k·1.01) = 3.1249 V > V_IH 2.31 V` | 3.1249 V | match |
| rising threshold time | `t = −RC·ln(1−V_IH/Vrail)` with RC at tolerance extremes; rise_min ≈ 0.979 ms, rise_max ≈ 1.483 ms | same | match |
| RC ≠ debounce | the 5 ms declared bounce is reported as a separate consideration | constraint `rc_is_not_debounce` present | match |

## F3 open-drain pull-up

| Claim | Independent derivation | Generated | Verdict |
|---|---|---|---|
| custom 10–90 % bound | `R_max = 300 ns/(ln9·100 pF)/1.01 = 1351.84 Ω` | 1351.84043558 Ω | match |
| sink/current bound | `R_min = (3.465/3 mA)/0.99 = 1166.67 Ω` | 1166.66666667 Ω | match |
| selected value (custom) | candidates 1200, 1300 lie in window; objective max resistance → 1300 Ω | 1300 Ω | match |
| I2C fast coefficient | UM10204 30–70 %: `Rp <= 300 ns/(ln(7/3)·100 pF)/1.01 = 3506 Ω` → 3300 Ω | 3300 Ω; rise time `ln(7/3)·C·R·1.01 = 282.405 ns` | match |
| empty interval | `Cb = 1 nF`: `R_max = 135.18 Ω` but `R_min = 1166.67 Ω` → no value | `unsupported` with both bounds | match |

## F4 ADC divider

| Claim | Independent derivation | Generated | Verdict |
|---|---|---|---|
| ratio (example) | `R2/(R1+R2) = 6800/10400 = 0.653846`; required max `3.3/5 = 0.66` | 0.653846153846 | match |
| worst-case tap | `5·(6868/(3564+6868)) + 1 µA·(3.6k∥6.8k)·1.01 = 3.29179 + 0.00238 = 3.29417 V <= 3.3 V` | 3.29417186314 V | match |
| Thevenin source | `R1∥R2 = 3600·6800/10400 = 2353.85 Ω` (nominal) | 2353.84615385 Ω | match |
| required power rating | worst bottom-resistor power `×(1/(1−50 %))` | 3.2393898944 mW | match |
| settling | `k = ln(1/0.5 LSB)`, `τ = R_th·C_sample`, compare against declared 2 µs sample time | verified with 84.1 τ vs 9.01 required | match |
| no sampling facts | nothing proves sampling settling | `settling_unverified` unknown, `ready_abstract` without accuracy claim | match |

## F5 low-side NMOS

| Claim | Independent derivation | Generated | Verdict |
|---|---|---|---|
| RDS(on) row selection | drive min 3.135 V → highest specified VGS ≤ 3.135 is 2.5 V → 48 mΩ max | 0.048 Ω, `room_temperature_only` | match |
| conduction loss | `0.8²·0.048 = 30.72 mW` max, `0.5²·0.048 = 12 mW` nominal | 30.72 mW / 12 mW | match |
| freewheel | `V_R >= 12.6 V`, `I_F >= 0.8 A`, `I_FSM >= 2.5 A`, `E = ½·1 mH·0.8² = 0.32 mJ` | same four requirements, no MPN | match |
| gate resistor | `5.5 V/0.1 A = 55 Ω` minimum from drive current; E24 above it = 56 Ω | 56 Ω | match |
| ID boundary | ID = 5.7 A: exactly 5.7 A legal, 5.71 A rejected | legal / rejected | match |
| thermal in DC | `Tj = 50 + (2²·0.032)·125 = 66 °C` | 66 °C | match |
| switching loss | insufficient dynamic data in the example → must stay unknown | `switching_loss_unverified`, no thermal claim | match |

## F6 LDO

| Claim | Independent derivation | Generated | Verdict |
|---|---|---|---|
| headroom (example) | `4.5 − 3.3·1.015 = 1.1505 V`; margin vs 0.215 V = `0.9355 V` | same | match |
| headroom boundary | min input `3.3·1.015 + 0.215 = 3.5645 V` legal; 3.5644 V rejected | same | match |
| dissipation | `(5.5 − 3.2505)·0.05 + 5.5·25 µA = 0.1126125 W` | same | match |
| junction estimate | `85 + 0.1126125·231.1 = 111.02 °C` (JEDEC 2s2p condition, an estimate only) | 111.02474875 °C | match |
| thermal refusal | 500 mA: `P ≈ 1.1 W`, `Tj ≈ 339 °C > 125 °C` | `unsupported` | match |
| capacitor requirements | facts require 1 µF in / 1 µF out; voltage ratings with derating | 1 µF/1 µF, 11 V/6.699 V | match |
| caller-declared path | `Tj = 40 + ((5.5−1.764)·0.1 + 5.5e-4)·200 = 114.83 °C` | 114.83 °C, facts `verified: false` | match |

## Defects found during this review and fixed

| Defect | Where | Fix |
|---|---|---|
| pull-down button exposed both contact terminals on VCC, leaving `BTN_NODE` unexposed | `blocks/button_input.py` | `SW_B` maps to the node for `pull_down`; covered by a test and a benchmark case |
| `devices.evidence_for` crashed on list-valued facts (tabulated RDS(on)) | `devices/__init__.py` | tabulated facts are summarised with their row count instead of formatted as one value |
| compose reported `input_invalid` when a non-ready block produced no port table | `compose.py` | endpoints of non-ready blocks are skipped and the design status becomes `unsupported`/`incomplete` |
| compose treated a design-port current as demand for inbound power ports | `compose.py` | a design-port current is a boundary rating (capability), independent of direction |
| benchmark expectation errors (mine, not code): tighten-to-5 mA variant, I2C coefficient precision, holdout input outside the device envelope | benchmark cases | expectations corrected to the independent derivation |

## What this review does not cover

- No SPICE/simulation, no thermal FEA, no EMC/ESD, no tolerance Monte-Carlo.
- No measurement of any built board; `binding.host_validation` and
  `physical_validation` are `NOT RUN`.
- Datasheet facts are used only as filed in `source-register.md`; the review does
  not re-open every PDF page, it checks the arithmetic that consumes the facts.
- The reviewer is the author; a genuinely independent audit is still advisable
  before any production use.
