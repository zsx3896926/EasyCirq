# Verified device / bus facts — source register

Status: **documentary verification only**. Every number in
`design-hardware/scripts/circuit_blocks/devices/facts/*.json` was read from a
primary manufacturer document or from the standards-body document (NXP UM10204),
opened directly on **2026-10-27 (Asia/Shanghai)**. Nothing here proves stock,
footprint/library correctness, pin-map correctness, board behaviour or measured
performance; `generate` reports those levels separately and never upgrades them.

This register is the human-readable companion to the JSON files. Each JSON leaf
fact carries `applies_to`, `condition` and a `source` of the form
`"<doc_id>, <section> (printed p. N)"`.

## 1. How the numbers were verified

1. The PDF behind each URL below was downloaded directly (manufacturer CDN, no
   mirror / no aggregator / no marketplace), then its text layer was extracted
   locally with PyMuPDF.
2. Where the text layer was scrambled or ambiguous, the PDF page was rendered to
   an image and the table was read visually — this was required for the
   AO3400A RDS(ON) table (the text layer prints `mW` where the page prints
   `mΩ`) and for the TLV755P `I_GND` row (column alignment).
3. Every value in the JSON was then re-read against the rendered/parsed page
   during a second pass, and each file was loaded through the repository's own
   strict loader (`circuit_blocks.devices.load_fact`) so that the required keys,
   units, conditions and source references are structurally valid.
4. No web-search engine was used (the search endpoint was unavailable during
   this task). No Wikipedia, blog, forum, distributor or marketplace value was
   used. No AI-summarised number was copied.

Cross-checks used:

- AO3400A: the electrical table values were cross-checked against the
  Product Summary on printed p. 1 (`RDS(ON)` `< 26.5 / 32 / 48 mΩ` at
  VGS = 10 / 4.5 / 2.5 V), which independently confirms the mΩ reading.
- TLV755P: `I_Q` typical 25 µA cross-checked against the front-page feature
  "Low I_Q: 25 µA (typical)"; the exact orderable `TLV75533PDBVR` was confirmed
  in the Package Option Addendum (SOT-23 DBV, 5 pins, 3000-piece reel).
- UM10204: the pull-up equations in Section 7.1 were cross-checked against the
  worked example on printed p. 51 (`Rp(min) = (5.5 V − 0.4 V)/3 mA = 1.7 kΩ`).

## 2. Sources (primary documents actually opened)

| id | manufacturer | exact document title | document number / id | revision · date | URL opened | accessed (Asia/Shanghai) | pages / sections used |
|---|---|---|---|---|---|---|---|
| S1 | Texas Instruments | *TLV755P 500-mA, Low-IQ, Small-Size, Low-Dropout Regulator datasheet* | SBVS320 | **SBVS320D** · November 2017, revised September 2024 | <https://www.ti.com/lit/ds/symlink/tlv755p.pdf> | 2026-10-27 | 5.1 (p. 4), 5.3 (p. 4), 5.4 (p. 5), 5.5 (p. 5–6), 6.3.2 (p. 12–13), 6.4.3 (p. 14), 7.1.1 (p. 15), 7.1.4 (p. 17–18), 8.1.1 (p. 23), Package Option Addendum (PDF p. 28) |
| S2 | Alpha & Omega Semiconductor (AOS) | *AO3400A 30V N-Channel MOSFET datasheet* | AO3400A | **Rev 3.1** · July 2023 | <https://www.aosmd.com/pdfs/datasheet/AO3400A.pdf> | 2026-10-27 | Absolute Maximum Ratings + Thermal Characteristics (p. 1), Electrical Characteristics + Notes A–F (p. 2), Figure 9 SOA / Figure 11 transient thermal (p. 4) |
| S3 | Kingbright | *APT1608SURCK 1.6 x 0.8 mm SMD Chip LED Lamp datasheet* | Spec No. DSAD0926 / 1203001764 | **V.22A** · 2023-04-08 | <https://www.kingbrightusa.com/images/catalog/SPEC/APT1608SURCK.pdf> | 2026-10-27 | Selection Guide/Features (p. 1), Absolute Maximum Ratings + Electrical/Optical Characteristics + Rθ notes (p. 2), Forward Current Derating Curve (p. 3) |
| S4 | onsemi | *BAT54 / BAT54A / BAT54C / BAT54S Schottky Diodes datasheet* | Publication Order Number BAT54/D | **Rev. 3** · September 2017 | <https://www.onsemi.com/download/data-sheet/pdf/bat54-d.pdf> | 2026-10-27 | Ordering Information + Absolute Maximum Ratings (p. 1), Thermal Characteristics + Electrical Characteristics (p. 2) |
| S5 | NXP Semiconductors | *UM10204 I2C-bus specification and user manual* | UM10204 | **Rev. 7.0** · 1 October 2021 | <https://www.nxp.com/docs/en/user-guide/UM10204.pdf> | 2026-10-27 | Table 10 (p. 43), Table 11 (p. 43–44), Figure 38 (p. 45), Section 6.1 (p. 43), Section 7.1 + eq. 1/2 (p. 50), worked example (p. 51) |

Access-path notes (not fact failures): `https://www.kingbright.com/attachments/file/pdfs/APT1608SURCK.pdf`
returned HTTP 404 on the access date, so the spec PDF published on Kingbright USA
(the manufacturer's US site; the PDF footer is a Kingbright copyright block) was
used. `https://www.onsemi.com/pdf/datasheet/bat54-d.pdf` returned HTTP 403 and
`https://www.onsemi.com/pub/Collateral/BAT54-D.PDF` returned HTTP 403, so the
`download/data-sheet` path was used. `https://www.nxp.com/docs/en/user-guide/UM10204.pdf`
returned 404 on the first request and 200 on retry; the file served is Rev. 7.0.

## 3. Fact files

| fact_id | category | exact orderable MPN | package | status | file |
|---|---|---|---|---|---|
| `ldo_tlv75533p` | `ldo` | **TLV75533PDBVR** (3.3 V fixed) | SOT-23-5 (TI DBV, 5 pins), 3000-piece reel | verified — primary datasheet S1 | `devices/facts/ldo_tlv75533p.json` |
| `mosfet_ao3400a` | `mosfet_n` | **AO3400A** | SOT-23 (3-lead) | verified — primary datasheet S2 | `devices/facts/mosfet_ao3400a.json` |
| `led_apt1608surck` | `led` | **APT1608SURCK** (Hyper Red) | 1.6 × 0.8 mm SMD, 0.75 mm (1608/0603 class) | verified — primary datasheet S3 | `devices/facts/led_apt1608surck.json` |
| `diode_bat54` | `diode_schottky` | **BAT54** (single diode; A/C/S variants share ratings) | SOT-23 (3-lead), top mark L4P | verified — primary datasheet S4 | `devices/facts/diode_bat54.json` |
| `bus_i2c_um10204` | `bus_spec` | N/A — protocol specification (UM10204) | — | verified — standards body document S5 | `devices/facts/bus_i2c_um10204.json` |

All five files carry `"verified": true`, and every fact record carries a
`source` whose first token is the `doc_id` of the source above, so the loader's
`fact_source()` resolves each record to the correct document.

## 4. What each file contains (fact groups → page)

### `ldo_tlv75533p` (S1, SBVS320D)

- Recommended operating range and absolute maximums — 5.3 / 5.1, p. 4.
  `VIN` 1.45–5.5 V, `VOUT` nominal 3.3 V (code `33`), `IOUT` 0–500 mA.
- Output accuracy — 5.5, p. 5. ±1.5 % max over TJ = −40…+125 °C (DBV,
  `VOUT ≥ 1 V`); ±1.0 % over TJ = −40…+85 °C.
- Dropout — 5.5 `V_DO`, p. 6. For the bin `3.3 V ≤ VOUT < 5.0 V` (which contains
  3.3 V) at `IOUT = 500 mA`: 150 mV typ / 215 mV max over −40…+85 °C,
  238 mV max over −40…+125 °C.
- Quiescent current — 5.5 `I_GND`, p. 5. At TJ = 25 °C, `IOUT = 0`: 14 µA min /
  25 µA typ / 31 µA max; 33 µA max over −40…+85 °C, 40 µA max over −40…+125 °C.
- Capacitors and stability — 5.3 p. 4 + 7.1.1 p. 15 + pin note p. 3.
  `C_IN ≥ 1 µF`; `1 µF ≤ C_OUT ≤ 200 µF` recommended; stability requires
  **≥ 0.47 µF effective** after DC-bias derating, X5R/X7R. No ESR window stated.
- Minimum load — 0 A (range starts at 0 mA; `I_GND` specified at 0 mA).
- Thermal — 5.4, p. 5. DBV: **RθJA = 231.1 °C/W** (JEDEC 2s2p, no vias to
  internal plane/bottom layer) and 100.8 °C/W (LP087A EVM); ψJB = 63.8 °C/W.
  TJ max = 125 °C recommended / 150 °C absolute.
- Enable — 5.5 p. 6 + 6.3.2 pp. 12–13 + 6.4.3 p. 14. Active high, VIH ≥ 1 V,
  VIL ≤ 0.3 V, I_EN 10 nA typ, output actively discharged through 120 Ω when
  disabled; tie EN to IN if unused; EN must stay below 10 kHz if driven above VIN.
- Reverse current — 5.1 note 2 p. 4 + 7.1.4 pp. 17–18. Not permitted:
  `VOUT ≤ VIN + 0.3 V` (absolute max); reverse current flows through the pass
  transistor body diode; external protection (Schottky) required if expected.

### `mosfet_ao3400a` (S2, Rev 3.1)

- Absolute maximums and thermal — p. 1. VDS 30 V, VGS ±12 V, ID 5.7 A
  (TA = 25 °C) / 4.7 A (TA = 70 °C), IDM 30 A, PD 1.4 W / 0.9 W,
  TJ −55…+150 °C. **RθJA 125 °C/W max steady-state** and 90 °C/W max for
  `t ≤ 10 s`, both on 1 in² FR-4 / 2 oz Cu / still air; θJL 80 °C/W max.
- RDS(ON) — p. 2, four specified points only: 10 V/5.7 A → 26.5 mΩ max
  (38 mΩ max at TJ = 125 °C); 4.5 V/5 A → 32 mΩ max; 2.5 V/3 A → 48 mΩ max.
  No other VGS points are guaranteed.
- VGS(th) — p. 2. 0.65 V min / 1.05 V typ / 1.45 V max at
  `VDS = VGS, ID = 250 µA`. Recorded explicitly as a threshold, **not** proof of
  full enhancement: the on-state proof is RDS(ON) at the applied VGS.
- Charge/capacitance — p. 2. Qg 6 nC typ / 7 nC max at VGS = 4.5 V,
  VDS = 15 V, ID = 5.7 A; Ciss 630 pF, Coss 75 pF, Crss 50 pF at VGS = 0,
  VDS = 15 V, 1 MHz.
- Body diode and SOA — p. 2 + Figure 9 p. 4. VSD 0.7 V typ / 1.0 V max at
  IS = 1 A; IS max 2 A; trr 8.5 ns typ, Qrr 2.6 nC typ; Figure 9 single-pulse
  forward-bias SOA at TA = 25 °C / TJ(max) = 150 °C. No UIS/EAS rating.

### `led_apt1608surck` (S3, DSAD0926 V.22A)

- VF — p. 2. 1.95 V typ / 2.5 V max at IF = 20 mA (plus the stated ±0.1 V
  tolerance). **No minimum VF is published** (`vf_min_v` is not recorded).
- Currents/power — p. 2. DC forward current 30 mA absolute max; peak forward
  current 185 mA only at 1/10 duty / 0.1 ms; PD 75 mW.
- Thermal — p. 2 + derating curve p. 3. TJ max 115 °C, operating −40…+85 °C,
  RθJA 480 °C/W and RθJS 310 °C/W both on FR-4 with ≥ 16 mm² pad per pad.
- Colour/optics — pp. 1–2. Hyper Red AlGaInP/GaAs, λpeak 645 nm, λdom 630 nm,
  Iv 120 mcd min / 230 mcd typ at 20 mA, 2θ½ = 120°, VF temperature coefficient
  −1.9 mV/°C.

### `diode_bat54` (S4, BAT54/D Rev. 3)

- Absolute maximums — p. 1. VRRM 30 V, IF(AV) 200 mA, IFSM 600 mA (1 s pulse),
  TJ −55…+150 °C; SOT-23 3L, top mark L4P.
- Thermal — p. 2. PD 290 mW, RθJA 430 °C/W (no board condition stated).
- Forward voltage — p. 2. 0.24 / 0.32 / 0.40 / 0.50 / 0.80 V max at
  0.1 / 1 / 10 / 30 / 100 mA; leakage 2 µA max at VR = 25 V.
- Recovery/capacitance — p. 2. trr 5 ns max (not typical); CT 10 pF max at
  VR = 1 V, 1 MHz (not typical); majority-carrier Schottky, no Qrr.

### `bus_i2c_um10204` (S5, UM10204 Rev. 7.0)

- Table 10 (I/O stages, p. 43): VIL ≤ 0.3 VDD, VIH ≥ 0.7 VDD, Vhys 0.05 VDD
  (Fm/Fm+), VOL1 ≤ 0.4 V at IOL = 3 mA (VDD > 2 V), VOL2 ≤ 0.2 VDD at 2 mA
  (VDD ≤ 2 V), IOL 3 mA (Sm/Fm at VOL 0.4 V) / 6 mA (Fm at VOL 0.6 V) /
  20 mA (Fm+ at VOL 0.4 V), tof 250 ns (Sm/Fm) / 120 ns (Fm+), tSP 50 ns,
  Ci 10 pF.
- Table 11 (bus lines, pp. 43–44): fSCL max 100 / 400 / 1000 kHz;
  **tr max 1000 ns (Sm) / 300 ns (Fm, min 20 ns) / 120 ns (Fm+)**;
  tf max 300 / 300 / 120 ns with min 20 × (VDD/5.5 V) for Fm/Fm+;
  **Cb max 400 pF (Sm, Fm) / 550 pF (Fm+)**; noise margins VnL 0.1 VDD,
  VnH 0.2 VDD.
- Pull-up sizing (Section 7.1, p. 50): `Rp(max) = tr / (0.8473 × Cb)`,
  `Rp(min) = (VDD − VOL(max)) / IOL`; worked example p. 51 gives 1.7 kΩ for
  VDD = 5.5 V worst case, VOL = 0.4 V, IOL = 3 mA.
- Scope limit recorded in the file: these limits are for Sm/Fm/Fm+ only —
  Hs-mode (Table 12) and UFm are **not** covered.

## 5. Facts that could NOT be verified (`unknown`)

No required category is unverified: all five fact files are backed by a primary
document. The following individual values are genuinely absent from the
documents and are therefore listed in each file's `unknown_facts` instead of
being filled in:

| fact_id | key / item | why it is unknown |
|---|---|---|
| `ldo_tlv75533p` | `esr_min_ohm`, `esr_max_ohm` | SBVS320D gives no ESR stability window; it only requires a ≥ 0.47 µF effective X5R/X7R ceramic. No numeric ESR min/max may be invented. |
| `ldo_tlv75533p` | start-up time maximum | only 550 µs typical is published; no max |
| `ldo_tlv75533p` | reverse-current magnitude limit | only `VOUT ≤ VIN + 0.3 V` abs max + "use external protection" |
| `ldo_tlv75533p` | load-transient deviation (min/max) | only typical characteristic curves |
| `mosfet_ao3400a` | RDS(ON) at 4.5 V / 2.5 V for TJ = 125 °C | only the 10 V row has a hot maximum (38 mΩ) |
| `mosfet_ao3400a` | RDS(ON) below VGS = 2.5 V | not characterised; transfer curve is typical only |
| `mosfet_ao3400a` | UIS / EAS avalanche rating | not in the datasheet |
| `mosfet_ao3400a` | switching loss / Qg at 2.5 V or 10 V drive | Qg specified only at VGS = 4.5 V |
| `mosfet_ao3400a` | RθJA on a user PCB | only the JEDEC/reference 1 in² 2 oz board condition |
| `led_apt1608surck` | `vf_min_v` | Kingbright publishes typ 1.95 V / max 2.5 V only; no minimum. A Vf lower bound must be a caller-declared range. |
| `led_apt1608surck` | numeric ambient-derating table | only a printed graph (p. 3) |
| `led_apt1608surck` | PWM/switching behaviour, capacitance test condition | not characterised |
| `led_apt1608surck` | LM-80 / lumen maintenance | not in this datasheet |
| `diode_bat54` | `ct_typ_f`, `trr_typ_s` | datasheet publishes maxima only (10 pF, 5 ns) |
| `diode_bat54` | hot reverse leakage | only 25 °C max + typical curves |
| `diode_bat54` | RθJA board condition / transient thermal impedance | not stated |
| `bus_i2c_um10204` | Hs-mode / UFm limits | out of scope of Tables 10–11 (Hs-mode is Table 12) |
| `bus_i2c_um10204` | "guaranteed bus frequency" | requires the slowest device's tLOW/tHIGH; not a single spec number |
| `bus_i2c_um10204` | Cb limit above which a bus cannot work | only the 400/550 pF specified limits; Section 7.2 gives mitigation techniques, not a limit |
| `bus_i2c_um10204` | pull-up resistor tolerance/ESR | not part of UM10204 |

## 6. Revision conflicts and caveats

1. **SCHEMA.md example vs. the real TLV755P document.** `devices/SCHEMA.md`
   shows an illustrative example with doc id `SBVS260` / revision `B`. The
   document actually served by TI for TLV755P on 2026-10-27 is **SBVS320D**
   (November 2017, revised September 2024). The SCHEMA example is illustrative
   only; the fact file cites SBVS320D and `SCHEMA.md` should not be treated as a
   source. The MPN in the SCHEMA example (`TLV75533PDBVR`) does exist and was
   confirmed in SBVS320D's Package Option Addendum.
2. **TLV755P output capacitor: two different minimums.** 5.3 Recommended
   Operating Conditions says `C_OUT ≥ 1 µF`; 7.1.1 says the device "requires an
   output capacitance of 0.47 µF or larger for stability" and the pin note says
   the *effective* capacitance (after DC-bias derating) must exceed 0.47 µF.
   Both are recorded (`cout_min_f = 1 µF`, `cout_stability_min_f = 0.47 µF`).
   A generator must state which one it used; a 0.47 µF *nominal* capacitor is
   not automatically 0.47 µF effective.
3. **AO3400A thermal: two different RθJA values.** The datasheet gives
   70/90 °C/W for `t ≤ 10 s` and 100/125 °C/W steady-state (JEDEC 1 in² FR-4
   2 oz Cu, still air). The PD rating 1.4 W is derived from the **≤ 10 s**
   value (note B), so a DC thermal calculation must use 125 °C/W, not 90 °C/W.
   Both values are recorded with their conditions.
4. **AO3400A text layer vs. printed page.** The PDF text layer prints `mW` /
   `mW` where the page prints `mΩ` (and `mA` where the page prints `µA` in
   `IDSS`). Values in the fact file were read from the rendered page and
   cross-checked against the p. 1 Product Summary; a text-only extraction would
   be wrong by 1000×.
5. **onsemi BAT54 revision.** The PDF served at the onsemi URL prints
   "September-2017, Rev. 3" and no superseded marker. That is the revision
   recorded; if onsemi publishes a newer file the facts must be re-verified
   rather than assumed unchanged.
6. **I2C revision.** UM10204 **Rev. 7.0 (1 October 2021)** is the current release
   in the document's own revision history (it is the seventh release; it
   replaced master/slave with controller/target and updated Table 5). The
   Table 10/Table 11 limits recorded here are as printed in Rev. 7.0; older
   "Rev. 6 (2014)" citations found elsewhere must not be mixed with these page
   numbers, because table numbering/section numbers in Rev. 7.0 are the ones
   cited.
7. **Bus-spec alias keys.** `rise_time_max_s`, `bus_cap_max_f` and `vol_max_v`
   are convenience aliases for the Fast-mode / Sm-Fm values, and their
   `condition` strings say so. The per-mode keys
   (`rise_time_max_s_standard|fast|fast_plus`,
   `bus_cap_max_f_standard|fast|fast_plus`) are the normative ones; a pull-up
   module must select by interface mode instead of using one coefficient.

## 7. Reproduce

```
# 1. fetch the five PDFs (direct manufacturer URLs, see table above)
# 2. extract the text layer locally (PyMuPDF) and render the table pages to images
#    where the text layer scrambles columns; read the pages cited in the table above
# 3. run the repository loader:
$env:PYTHONPATH = "design-hardware/scripts"
python -c "from circuit_blocks.devices import load_fact; print(len(load_fact('ldo_tlv75533p')['facts']))"
```

Fact index: `devices/facts/_fact_index.json` (underscore prefix so the loader's
`available_facts()` — which only lists real device-fact files — does not treat
the index as a device fact file).
