# Verified device facts — file format (v1)

Circuit-block generators never invent part numbers, pinouts or ratings.  A
module may consume a *verified device fact file* only when the file names an
exact manufacturer part number (MPN), a primary manufacturer document, and the
condition under which each number applies.

These files prove **document facts only**.  They do not prove that the part is
in stock, that a PCB library footprint exists, that a pin map matches a
physical package, or that the circuit was built and measured.  `generate`
reports those levels separately and never upgrades them.

## Directory layout

```
design-hardware/scripts/circuit_blocks/devices/
  SCHEMA.md
  facts/
    ldo_tlv75533p.json
    mosfet_ao3400a.json
    ...
```

## File format

```json
{
  "schema": "circuit-blocks/device-facts/1",
  "fact_id": "ldo_tlv75533p",
  "category": "ldo",
  "mpn": "TLV75533PDBVR",
  "manufacturer": "Texas Instruments",
  "verified_on": "2026-10-27",
  "conditions": "TA = 25 C, VIN = VOUT(nom) + 1 V, unless a fact states its own condition",
  "sources": [
    {
      "document": "TLV755P 500-mA, Low-IQ, Low-Dropout Regulator datasheet",
      "doc_id": "SBVS260",
      "revision": "B",
      "url": "https://www.ti.com/lit/ds/symlink/tlv755p.pdf",
      "accessed": "2026-10-27",
      "sections": ["6.5 Electrical Characteristics", "7.3 Feature Description"]
    }
  ],
  "facts": {
    "vin_min_v":  {"value": 2.5, "unit": "V", "applies_to": "TLV75533P", "condition": "recommended operating range", "source": "SBVS260 rev B, 6.3"},
    "theta_ja_c_per_w": {"value": 190, "unit": "C/W", "applies_to": "DBV (SOT-23-5)", "condition": "JEDEC 2x2 board, still air", "source": "SBVS260 rev B, 6.4"}
  },
  "unknown_facts": ["short-circuit recovery time not stated for this exact orderable part"],
  "notes": "Fact file verified against the PDF revision above; values that the datasheet gives only as typical are recorded with condition='typical'."
}
```

Rules:

1. `fact_id` is the stable key modules reference (`"device_fact_id": "ldo_tlv75533p"`).
2. Every leaf fact is `{value, unit, applies_to, condition, source}`.  A fact
   that the datasheet does not state belongs in `unknown_facts`, never guessed.
3. `value` is a number, a string for text facts, or a list for tabulated
   families (for example RDS(on) at several VGS points).  Units are SI symbols
   (`V`, `A`, `ohm`, `F`, `s`, `W`, `C/W`, `C`, `Hz`, `C`).
4. `applies_to` names the exact orderable variant and package when facts differ
   between packages.  A fact without a variant when variants differ is invalid.
5. `source` points into `sources[].doc_id` + section; it is not a URL by itself.
6. Filenames are lower-case `category_mpn.json`; `fact_id` matches the filename
   stem.
7. Min/max pairs use suffixed keys (`vin_min_v`, `vin_max_v`).  A one-sided
   limit is legal; a missing limit is `unknown`.

## Categories and required keys

`ldo` — `vin_min_v`, `vin_max_v`, `vout_nom_v`, `vout_tol_pct`, `iout_max_a`,
`dropout_v` (with condition naming the load current), `iq_a`, `cin_min_f`,
`cout_min_f`, `esr_min_ohm` and `esr_max_ohm` when the datasheet states a
stability range, `min_load_a` when a minimum load is required, plus thermal
facts (`theta_ja_c_per_w` with board condition, `tj_max_c`).  If the device has
an enable pin or a reverse-current path, record `enable_pin` /
`reverse_current_allowed`.

`mosfet_n` — `vds_max_v`, `vgss_max_v`, `id_max_a`, `pd_max_w`, `rds_on_ohm`
(list of `{vgs_v, max_ohm, condition}`), `vgs_th_min_v`, `vgs_th_max_v`,
`qg_typ_c` (condition: VGS, VDS), `ciss_typ_f`, `theta_ja_c_per_w` with board
condition, `tj_max_c`, `body_diode` (text: yes/no and VSD condition), plus
`soa` text when the datasheet gives one.

`led` — `vf_typ_v` / `vf_min_v` / `vf_max_v` at a stated test current,
`i_forward_max_a`, `i_forward_abs_max_a` (pulse vs continuous must be
distinguished), `power_dissipation_max_w`, `temperature_coefficient`, package
and colour.

`diode_schottky` — `vr_max_v`, `if_avg_max_a`, `ifsm_max_a`, `vf_max_v` at a
stated current, `trr` (or `majority_carrier: true`), `ct_typ_f`, thermal facts.

`bus_spec` — for protocol limits (for example I2C bus timing); a primary
standards document rather than a part.  Keys are the quantities the module
actually consumes (`rise_time_max_s` with mode/condition, `bus_cap_max_f`,
`vol_max_v` at a stated sink current).
