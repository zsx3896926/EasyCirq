# Parameterized standard circuit blocks — contract v1

Status: implementation contract for `design-hardware/scripts/circuit_blocks/`.
Scope: offline generation of abstract circuits (math + connectivity), **not** an
EDA executor, not a part-selection service, not a production schematic.

## 1. What a block is

A block is a deterministic function

```
raw inputs (JSON object)  ->  module result (JSON object, self-validated)
```

It computes parameter values, selects standard component values, states the
applicability domain, and emits an abstract net/endpoint/component-role
contract. It never binds an MPN, a library footprint, a host schematic or a
physical board; those levels stay `NOT RUN`.

## 2. Statuses and process exit codes

| status | meaning | exit |
|---|---|---|
| `ready_abstract` | mathematics and connectivity contract hold for declared inputs/facts | 0 |
| `needs_device_facts` | circuit maths needs part facts that were not supplied; `unknowns` names them | 3 |
| `unsupported` | well-formed input outside applicability, or hard constraints have no feasible solution | 4 |
| `input_invalid` | malformed/contradictory input (unknown field, bad unit, NaN/bool, inverted range, missing structural field) | 2 |
| `incomplete` | compose-only: can prove neither compatibility nor conflict | 5 |

`ready_abstract` **must not** carry status reasons. Non-ready results must carry
at least one. `hardware_pass` is never a status. Validation failure of the tool's
own output is exit 1 (internal bug), not a result status.

## 3. Result schema (`circuit-blocks/module-result/1`)

Required top-level keys, in this order:

```
schema, module_type, template_version, instance_id, display_name, status,
status_reasons, inputs, units, components, ports, connectivity, calculations,
constraints, evidence, unknowns, assumptions, binding, tool, notes, content_hash
```

- `inputs`: normalised echo of caller input. Quantities `{"value","unit"}`,
  ranges `{"min","max","unit"}`, canonical units only. Two callers writing
  `"4k7"`, `"4.7k"` or `{"value":4700,"unit":"ohm"}` must produce the same echo
  and the same `content_hash`.
- `units`: `{family: canonical-unit}` actually used by the module schema.
- `components[]`: `ref, role, kind, value, tolerance, series, power_rating,
  voltage_rating, polarity, pins[{name, semantic}], candidates[], mpn,
  library_id, binding, requirements, notes`.
  `value` is a requirement for part selection; it is not a bound part.
  `mpn`/`library_id` stay `null` and `binding` stays `"unbound"`.
- `ports[]`: `id, direction(input|output|bidirectional|passive), role(power|
  ground|analog|digital|open_drain|switch|reference), net, voltage, current,
  logic, description, notes`. A port is the module boundary; it must declare
  its legal voltage (and current where relevant) range.
- `connectivity`: `{"nets":[{id,name,role,scope,voltage_domain,notes}],
  "connections":[{component,pin,pin_semantic,net,state}]}`.
  `state` is `connected` or `no_connect` (with `reason`). Net ids are namespaced
  `"<instance_id>:<LOCAL_NAME>"`; local names are simple identifiers. Physical
  pin numbers are **not** claimed: `pins`/`pin_semantic` are semantic roles.
- `calculations[]`: `id, title, method, formula, inputs, result, unit, limit,
  margin, assumptions[], not_modelled[]`. Every hard decision must have a
  calculation that a reviewer can recompute by hand.
- `constraints[]`: `id, kind(hard|advisory|layout|verification|integration),
  statement, applies_to, source, rationale`. Only `hard` blocks readiness.
- `evidence[]`: `id, kind(manufacturer_datasheet|standard|application_note|
  user_declared|derivation|assumption|tool_output), statement, source,
  applies_to, verified`. `verified=true` requires a primary manufacturer or
  standards source.
- `unknowns[]`: `id, statement, impact, how_to_resolve`.
- `assumptions[]`: `statement, impact`.
- `binding`: fixed map. `math_and_connection_contract` may be `pass`,
  `device_fact_verification` is `partial` when facts are user-declared, and
  `part_binding`, `library_binding`, `host_validation`, `physical_validation`,
  `real_eda` are `NOT RUN`.
- `content_hash`: `sha256:` over the canonical JSON of everything except
  `instance_id`, `display_name`, `notes`, `tool`, `symbols`, `content_hash`.
  Renaming an instance must not change it; changing a net/ref/value/status
  must.

## 4. Input conventions

- Numbers: JSON number or numeric string. Booleans are never numbers. NaN,
  infinities, empty strings and magnitudes > 1e15 are rejected.
- Quantities: number (canonical unit), string with SI suffix (`"4.7k"`,
  `"100nF"`, `"2.5V"`, `"1m"`, `"4k7"`), or `{"value","unit"}` object.
- Ranges: `{"min","max"}` (both required, closed interval) or
  `{"nominal","tolerance_pct"}`. Point ranges are legal input but a module may
  reject them with `needs_device_facts` when a real spread is required.
- Percent: number (meaning %), `"5%"`, or `{"value":5,"unit":"%"}`.
- Unknown fields are rejected with the field path. Optional part facts that are
  absent must not be silently defaulted; report `needs_device_facts`.
- Every module declares `INPUT_SCHEMA`; the CLI `describe` prints it.

## 5. Core API (read the code, do not re-implement)

| module | purpose |
|---|---|
| `errors.py` | `InputInvalid`, `Unsupported`, `NeedsDeviceFacts`, `NoFeasibleSolution`, `CompositionConflict` |
| `numeric.py` | `parse_number`, `to_json_number`, `format_number` — exact `Fraction` arithmetic |
| `units.py` | `parse_quantity`, `quantity_json`, `canonical_unit` |
| `ranges.py` | `Interval` (closed, exact), `parse_interval`, `parse_percent` |
| `eseries.py` | `values(series,min,max)`, `is_standard_value`, `choose`, `nearest`, E6/E12/E24/E48/E96 |
| `schema.py` | declarative `INPUT_SCHEMA`, `validate_inputs` |
| `result.py` | `Draft`: `component`, `net`, `port`, `connect`, `no_connect`, `calculation`, `constraint`, `evidence`, `unknown`, `assumption`, `finish` |
| `validate.py` | `validate_module_result`, `recompute_module` |
| `devices/` | `load_fact(fact_id)`, `evidence_for(draft, facts, keys)`, `user_declared_facts(...)` |

Rules:

1. All numeric *decisions* use `Fraction`/`Interval`. Floats only appear in the
   JSON output (`to_json_number`).
2. Never reach into `Draft` private attributes (`_nets`, `_connections`, …).
   If a helper is missing, ask the Lead — do not invent a parallel result path.
3. Sort candidates deterministically; ties break on numeric value ascending.
4. A module with no feasible solution must raise `NoFeasibleSolution` (mapped
   to `unsupported`) and must not relax a hard constraint to find a value.
5. Missing facts raise `NeedsDeviceFacts([...])` naming the missing keys; the
   base class turns them into `unknowns`.

## 6. Block class shape

```python
class MyBlock(Block):
    MODULE_TYPE = 'snake_case_id'
    TEMPLATE_VERSION = '1.0.0'
    TITLE = '...'
    SUMMARY = '...'
    TOPOLOGY = '...'
    APPLICABILITY = (...)          # what the maths actually covers
    NON_APPLICABILITY = (...)      # what it refuses
    REQUIRED_DEVICE_FACTS = (...)
    SOURCES = ({'document': '...', 'why': '...'}, ...)
    INPUT_SCHEMA = {...}
    EXAMPLE_INPUT = {...}          # must generate ready_abstract with documented defaults

    def compute(self, draft, inputs):
        ...
        return 'ready_abstract', [], notes      # or (status, reasons[, notes])
```

`compute` may raise the error classes; the base class converts them and always
self-validates the result.

## 7. Per-module deliverables

For each block `X`:

1. `design-hardware/scripts/circuit_blocks/blocks/<x>.py`
2. `tests/circuit_blocks/test_<x>.py` — at least these cases:
   - normal generation: status, selected standard value, net/endpoint contract,
     recomputed worst case, power/current margins;
   - no feasible solution: conflicting hard constraints → `unsupported` plus the
     bound that fails;
   - missing device facts → `needs_device_facts` naming them;
   - tolerance boundary: worst case exactly on the limit is *legal*; one smallest
     step past it is rejected (and the decision must not flip due to float
     rounding);
   - determinism: same inputs twice → identical `content_hash`;
     unit-spelling variant (`"4.7k"` vs `4700`) → identical hash.
3. Expected numbers are derived in the test by hand/independent formula (write
   the formula in a comment above the assertion). Never copy the generator's
   output into the test as the expected value.

## 8. Module requirements (condensed)

- **F1 LED** (`led_indicator`): supply/Vf/current ranges, resistor series +
  tolerance; worst-case I_min/I_max, resistor power + derating; topology
  high-side supply / low-side switch / always-on ports; point-only Vf rejected;
  GPIO direct drive only with declared drive facts.
- **F2 button** (`button_input`): supply/logic-threshold/pull-up/tolerance and
  target time constant; pull-up/down variants, optional RC; compute threshold
  crossing time from declared thresholds — never equate RC product with a
  guaranteed debounce time; mechanical bounce, slow edges, Schmitt and software
  debounce are separate preconditions; abstract two-terminal contact, no
  physical 4-pin pin numbers without a verified internal-connection fact.
- **F3 open drain** (`open_drain_pullup`): pull-up rail range, VOL/IOL limits,
  bus capacitance, allowed rise time, static-current budget, tolerance; legal
  pull-up interval then a standard value, recomputed; state the rise-time
  definition and first-order RC assumption; per-interface coefficient (I2C mode
  from the bus spec, not one factor for everything); unknown C_bus or sink
  capability never yields a "bus frequency guaranteed" claim.
- **F4 divider** (`adc_divider`): measured-voltage range, ADC input range,
  resistor values/tolerance, input leakage, source impedance/sample constraint;
  standard values, worst-case output, power, Thevenin source impedance; unknown
  ADC sample time/capacitance → sampling settling explicitly unverified;
  protection (negative/overvoltage/reverse feed) is a separate constraint;
  optional RC only with its bandwidth change stated; a buffer requirement emits
  a gap instead of an op-amp pick.
- **F5 low-side NMOS** (`low_side_nmos`): load voltage/current/inrush, drive
  level, frequency range, inductive load flag, sourced MOSFET facts; RDS(on) at
  the actual VGS (never VGS(th)), conduction loss where valid, unknown switching
  loss/thermal when data is insufficient; inductive loads → freewheel device
  voltage/current/pulse conditions and clamp behaviour; lower-bound-only specs
  become selection constraints, not invented part numbers.
- **F6 LDO** (`ldo_supply`): Vin/Vout/load/ambient + exact device facts
  (dropout, capacitor/ESR stability, minimum load, operating area, thermal
  model); headroom check, dissipation and conditional temperature estimate,
  decoupling/feedback only for the variant the facts describe; missing facts →
  `needs_device_facts`; θJA results are estimates under the datasheet's board
  condition, never a board temperature guarantee; reverse current, enable pin
  and out-of-range operation are explicit constraints.

## 9. Verified device facts

`design-hardware/scripts/circuit_blocks/devices/SCHEMA.md` is normative.
Modules that consume exact-part data accept either a bundled `device_fact_id`
or caller-declared facts (`devices.user_declared_facts`) which are tagged
`verified: false`. Never invent an MPN. Facts that are not in a primary
manufacturer document go to `unknowns`, not `evidence`.

## 10. Compose (Lead-owned)

`compose` consumes `{"design_name", "blocks":[{instance, module_type, display_name,
inputs}], "connections":[...], "design_ports":[...]}`. Modules must expose
explicit ports with declared electrical roles/ranges so compose can (a) refuse
proven conflicts, (b) report `incomplete` when compatibility is unprovable, and
(c) never merge nets just because two labels match.

## 11. Running

```powershell
$env:PYTHONPATH = "design-hardware/scripts"
python -m circuit_blocks list
python -m circuit_blocks describe <module_type>
python -m circuit_blocks generate <module_type> --example
python -m unittest discover -s tests -p "test_*.py"
```

Python 3.10 and 3.13 must both work; standard library only.

## 12. Ownership

Only the Lead edits: `core` modules (`numeric`, `units`, `ranges`, `eseries`,
`schema`, `result`, `canonical`, `validate`, `cli`, `compose`, `svg`, `devices/`),
`contract.md`, `module-catalog.md`, `report.md`, `handoff-current.md`, and the
git/PR state. Block owners edit only their block file, their test file, and
their own benchmark fixtures. Never edit another owner's file; message the Lead
instead.
