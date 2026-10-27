# Module catalog (template version 1.0.0)

Six parameterized standard blocks. Each one validates declared constraints,
computes the circuit, selects standard component values, and emits an abstract
net/endpoint/port contract. None of them binds a part, a library footprint, a
board or a physical measurement.

Run `python -m circuit_blocks describe <module_type>` for the full field list
(units, defaults, docs) and `python -m circuit_blocks generate <module_type>
--example` for the documented example.

| module_type | circuit | documented example result | tests |
|---|---|---|---|
| `led_indicator` | series ballast + LED, high/low-side switch | 5 V, E24 560 Ω, `ready_abstract` | 23 |
| `button_input` | pull resistor + optional RC + abstract two-terminal contact | 3.3 V, 10 kΩ + 100 nF, `ready_abstract` | 36 |
| `open_drain_pullup` | pull-up for an open-drain bus | 3.0–3.6 V, E24 1.6 kΩ, `ready_abstract` | 36 |
| `adc_divider` | R_top/R_bottom divider into an ADC | 1–5 V → 0–3.3 V, 3.6 kΩ/6.8 kΩ | 26 |
| `low_side_nmos` | low-side N-MOSFET load switch | 12 V/0.8 A, AO3400A facts, 56 Ω gate | 37 |
| `ldo_supply` | fixed-output LDO from exact device facts | 5 V→3.3 V, TLV75533P facts, 1 µF/1 µF | 33 |

Composition: 19 tests (`tests/circuit_blocks/test_compose.py`).

---

## F1 `led_indicator` — LED current limit and indicator interface

**Topology.** `always_on`, `low_side_switch` or `high_side_switch`, combined
with `resistor_position` = `supply_side|ground_side`. The resistor is the only
value selected; the LED stays an abstract role with a Vf range requirement.

**Required inputs.** `supply_voltage` (range), `led_vf` (range), `target_current`,
`max_current`, `resistor_tolerance_pct`. **Optional.** `min_current`,
`led_max_current`, `series`/`allowed_values`, `value_range`,
`resistor_power_rating`, `power_derating_pct`, `control`, `resistor_position`,
`switch_facts` (sink/source current + voltage drop), `objective`.

**Key formulas.**
- `R >= (Vs_hi − Vf_lo − Vd_lo) / (Imax·(1−tol))`
- `R <= (Vs_lo − Vf_hi − Vd_hi) / (Imin·(1+tol))`
- `I_max = (Vs_hi − Vf_lo − Vd_lo) / R_min`, `I_min = (Vs_lo − Vf_hi − Vd_hi) / R_max`
- `P = (Vs_hi − Vf_lo − Vd_lo)² / R_min`, required rating `P/(1−derating)`

**Refusals.** Point-only `led_vf` (nominal treated as constant) →
`needs_device_facts`; missing LED absolute maximum → `needs_device_facts`;
switched topology without declared switch capability → `needs_device_facts`;
inverted current window or no standard value in the window → `unsupported`;
declared package rating insufficient → `unsupported`.

**Ports.** `VCC` (input power), `GND`, plus `SW` (low-side) or `VSW` (high-side).
**Sources.** IEC 60063; LED and driver datasheet facts are caller-supplied or
from a verified fact file (no LED fact file is bundled; the LED in the example is
an abstract role).

## F2 `button_input` — button input with pull resistor and optional RC

**Topology.** `variant` = `pull_up` (resistor to VCC, contact to GND) or
`pull_down` (resistor to GND, contact to VCC), each with or without an RC filter.
Contact is an abstract two-terminal model; no physical pin number is claimed.

**Required inputs.** `supply_voltage`, `variant`, `resistor_tolerance_pct`.
**Optional.** `v_ih`/`v_il` (ranges; highest/lowest endpoint used), `logic_source`,
`input_leakage`, `active_level`, `series`/`allowed_values`, `value_range`,
`contact` facts (contact current limit, contact resistance, bounce, pin
configuration), `rc_filter` target.

**Key formulas.**
- closed contact current `I = V_rail_max / (R_min + Rc_min)`
- open-state level with leakage `V_open = V_rail − I_leak·R` (pull-up) or
  `I_leak·R` (pull-down), checked against `V_IH`/`V_IL` at tolerance extremes
- RC threshold crossing `t = −RC·ln(1 − Vth/Vrail)` — reported as time, never as a
  guaranteed debounce

**Refusals.** Missing thresholds or leakage → `needs_device_facts`; no standard
resistor in the legal window → `unsupported`; `active_level` contradicting the
variant → `input_invalid`.

**Ports.** `VCC`, `GND`, `SW_A`/`SW_B` (abstract contact terminals; pull-up:
`SW_A`=node, `SW_B`=GND; pull-down: `SW_A`=VCC, `SW_B`=node), `OUT` (digital,
with declared legal levels).
**Explicit non-claims.** RC ≠ debounce; mechanical bounce, slow edges (Schmitt
trigger) and software debounce are separate preconditions listed as constraints.

## F3 `open_drain_pullup` — open-drain / open-collector pull-up

**Topology.** one pull-up resistor from the bus rail to the bus node.

**Required inputs.** `supply_voltage`, `bus_capacitance`, `device` facts
(`vol_max`, `iol`, provenance), `resistor_tolerance_pct`. **Optional.**
`bus_spec` (`standard|fast|fast_plus|custom`), `max_rise_time`,
`rise_time_definition` (`10_90|30_70|vil_vih`), `bus_v_il`/`bus_v_ih`,
`static_current_budget`, `series`/`allowed_values`, `value_range`, `objective`.

**Key formulas.**
- rise-time bound `R <= t_rise / (k·C_bus·(1+tol))` with
  `k = ln(9)` for 10–90 %, `k = ln(7/3)` for 30–70 % (I2C `0.8473` coefficient),
  or the declared V_IL→V_IH coefficient
- sink bound `R >= (V_pu_max − V_OL_min) / (I_OL·(1−tol))`
- static budget `R >= V_pu_max / I_budget`
- recomputed `t_rise`, static current, power and worst-case low level

**Refusals.** Empty interval → `unsupported` with both conflicting bounds;
missing V_OL/I_OL or bus capacitance → `needs_device_facts` and no bus-frequency
claim; `max_rise_time` together with a fixed `bus_spec` → `input_invalid`.
A mathematically valid pull-up does not prove the pull-up rail is safe for every
device pin — that stays a constraint.

**Bus modes** are backed by the verified `bus_i2c_um10204` fact file (NXP
UM10204 Rev. 7.0: tr max 1000/300/120 ns, Cb max 400/400/550 pF, VOL 0.4 V at
3 mA). The table is data, not one coefficient for every interface.

**Ports.** `VCC` (pull-up rail), `BUS` (open-drain node), `GND`.

## F4 `adc_divider` — voltage divider into an ADC

**Topology.** `divider_to_ground` or `divider_to_vref`.

**Required inputs.** `topology`, `input_voltage` (range), `adc_input_range`
(range), `resistor_tolerance_pct`. **Optional.** `adc_leakage_current`,
`adc_vref`, `adc_reference_tolerance_pct`, `adc_resolution_bits`,
`adc_max_source_impedance`, `adc_margin`, `adc_sampling`
(`sample_time`, `sample_hold_capacitance`), `series`/`allowed_values`,
`value_range`, `resistor_power_rating`, `power_derating_pct`, `objective`,
`rc_filter`.

**Key formulas.**
- required ratio window from the input range and the ADC legal range with margin
- worst-case tap `V = Vin_hi · R_b_max/(R_t_min+R_b_max) + I_leak·(R_t||R_b)·(1+tol)`
- Thevenin source `R_t||R_b`, divider power, per-resistor power with derating
- settling `k·R_source·C_sample` against the declared sample time when given
  (`k` from the declared error target), else explicitly unverified

**Refusals.** Missing ADC leakage (needed for the worst-case tap) →
`needs_device_facts`; no pair inside the ratio/source-impedance/power constraints
→ `unsupported`; a buffer need becomes an integration gap with required specs (no
op-amp is picked); protection (negative/overvoltage/reverse feed/series R) is
four explicit unverified constraints.

**Ports.** `VIN`, `VOUT`, `GND`, optional `VREF`.

## F5 `low_side_nmos` — low-side N-MOSFET load switch

**Topology.** load between `VLOAD` and the switched node; MOSFET source to GND;
gate network from a declared drive level.

**Required inputs.** `load_supply_voltage` (range), `load_current_nominal`,
`load_current_max`, `load_inrush_current`, `gate_drive_voltage` (range) and one
fact source: `device_fact_id` (bundled `mosfet_ao3400a`) or caller-declared
`device_facts`. **Optional.** `switching_frequency`/`dc_operation`,
`inductive_load` + `load_inductance`/`load_energy_mj`, `ambient_temperature`,
`gate_series`, `gate_resistor_target`, `gate_pulldown_value`,
`max_gate_drive_current`.

**Key formulas.**
- RDS(on) at the highest datasheet VGS row ≤ drive minimum (no upward
  interpolation); VGS(th) only as a necessary condition
- conduction loss `P = I²·RDS(on)`; thermal estimate only when the ambient and
  θJA with its board condition are declared, and never with switching loss
- freewheel requirement for inductive loads: `V_R >= V_load_max`,
  `I_F >= I_load_max`, `I_FSM >= inrush`, energy `E = ½·L·I²`; no diode MPN
- gate: series resistor from the declared target bounded by the drive current,
  pulldown always emitted with rationale

**Refusals.** Missing MOSFET facts → `needs_device_facts`; ID/VDS/VGS/Pd/Tj
violation → `unsupported`; switching loss and dynamic thermal behaviour stay
`unknown` — a static calculation never proves temperature rise.
**Ports.** `VLOAD`, `SW`, `GATE`, `GND`. **Source.** verified
`mosfet_ao3400a` (AOS Rev 3.1) facts when the fact file is used.

## F6 `ldo_supply` — LDO from exact device facts

**Topology.** fixed-output LDO from a verified or caller-declared fact file; the
adjustable variant is refused unless the facts describe the requested variant.

**Required inputs.** `input_voltage` (range), `output_voltage`, `load_current`
(range), `ambient_temperature` (range) and either `device_fact_id` (bundled
`ldo_tlv75533p`) or `device_facts`. **Optional.** `bleed_resistor`,
`bleed_*` selection inputs, `capacitor_derating_pct`.

**Key formulas.**
- envelope: input range inside the device range; requested output matches the
  fixed variant
- headroom `Vin_min − Vout_max >= dropout(Iout_max)` using the datasheet row at
  or above the actual load, preferring the row covering the ambient range
- dissipation `P = (Vin_max − Vout_min)·Iout_max + Vin_max·Iq`;
  `Tj = Ta_max + P·θJA` **only under the datasheet board condition**, reported as
  an estimate
- capacitor requirements from the facts (minimum, ESR window if stated, voltage
  rating with derating); no generic capacitor invented
- minimum load: hard constraint / required bleed path; a bleed is never added
  silently
- enable pin, reverse current and out-of-range operation are explicit
  constraints

**Refusals.** Missing required fact → `needs_device_facts` naming the key;
headroom/Tj/current/variant/envelope violation → `unsupported`.
**Ports.** `VIN`, `VOUT`, `GND`, `EN` when the device has one.
**Source.** verified `ldo_tlv75533p` (TI SBVS320D) facts when the fact file is
used; `device_fact_verification` stays `partial` because a document fact is not a
bound part.

---

## Cross-cutting result contract

All modules emit the same envelope (`contract.md` §3): `schema`, `module_type`,
`template_version`, `instance_id`, `display_name`, `status`, `status_reasons`,
`inputs` (normalised), `units`, `components` (abstract, unbound), `ports`
(voltage/current ranges), `connectivity` (namespaced nets + endpoints),
`calculations` (formula + inputs + result + margins + assumptions),
`constraints` (hard/advisory/layout/verification/integration), `evidence`,
`unknowns`, `assumptions`, `binding` levels, `content_hash`.

Determinism: the same inputs always produce the same bytes and hash; unit
spellings normalise to the same hash; a display-name change does not change it.
