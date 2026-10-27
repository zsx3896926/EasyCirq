# Integration proposal: abstract blocks → existing connectivity / intent models

Status: **proposal only**. This document does not modify any shared script, the
connector, the protocol, the EDA executor or task A's compose path. The Lead of
task A decides whether and how to adopt it.

## 1. What already exists (read-only survey, main `9a951ed`)

| Artefact | Shape | Owner |
|---|---|---|
| `netlist_check.py` input | `{components:[{ref, kind?, part?, physical_pins:[...], pins:{physical_pin: net}, nc:[...], fitted?}], power_nets:[], ground_nets:[], external_nets:[], net_rules:{net:{pullup,power_net}}}` | existing offline check |
| `pin_net_intent_check.py` intent | `{components:{REF:{pins:{pin_key: net}, pinMap:{semantic:physical}}}, nets:{net:[REF.pin_key]}}` | existing offline check |
| `design_engine` IR | `components[{id, kind, designator, pins[{id, number, native}], native, placement}]`, `nets[{id:"net:<name>", name, scope, role, native}]`, `connections[{component_id, pin_id, pin_number, net_id}]` | `design_engine/ir.py`, adapters |
| `pcb-intent.json` | `modules:[{id, template, target, roles:{role:{designator, pads:{semantic: physical}}}}]`, `constraints`, `power_nets` | PCB preflight / apply plan |
| `*.module-plan.json` | `zones:[{id, title, core, members:[designator], netPolicies}]` — designators only, no coordinates | schematic/PCB module layout |

Common denominator: **components are identified by ref/designator, connections
by (ref, physical pin) → net name, modules/roles by designator.** None of these
formats wants an abstract role; they all need a bound library part with real
pads. That is exactly the boundary this task stops at.

## 2. Mapping of a module result to the existing models

| Abstract block field | Existing field | Available now? |
|---|---|---|
| `components[].ref` (R1, D1, …) | `components[].ref` / `designator` | yes, but only after refs are made unique across blocks (`<INSTANCE>_<REF>`) |
| `components[].role`, `requirements` | pre-binding selection constraints; no destination field | keep in the handoff artefact |
| `components[].kind`, `value`, `tolerance`, `series`, `power_rating` | BOM/selection and `netlist_check` `kind` | yes |
| `components[].pins[].name` + `semantic` | `pins` key / `pinMap` semantic key | **semantic only**; must be mapped to a real physical pad after binding |
| `connectivity.connections[]` (`component`, `pin`, `net`) | `pins:{physical: net}` and `connections` | only after the semantic pin is bound to a physical pad |
| `connectivity.nets[].name` | net name (`net:<name>`, netlist `pins` values) | yes, after namespace decision (below) |
| `ports[]` | `external_nets`, `net_rules`, `power_nets`, `ground_nets` | yes, with declared voltage/current ranges attached as evidence |
| `status`, `content_hash`, `evidence[]` | no destination field | must travel in a sidecar; do not drop |
| module result as a whole | `intent.modules[]` `{id, template, roles}` | after binding, one block ≈ one module with `roles` per abstract role |

### 2.1 Proposed sidecar (not a replacement)

Keep the full module result as a sidecar file next to the project intent, e.g.
`docs/circuit-blocks/<instance>.json`, and let any converter read it. The result
already carries `status`, `content_hash`, `binding` levels and evidence, so a
converter can refuse to convert anything that is not `ready_abstract`.

### 2.2 Proposed converter contract (to be implemented by task A, not here)

```
abstract module result (ready_abstract, binding=unbound)
  + library binding facts (real MPN, pad map, footprint identity, pin electrical direction)
  → netlist_check components[] / design_engine IR connections / intent.modules roles
```

Hard requirements for that converter:

1. Refuse if `status != ready_abstract`, if `content_hash` is missing, or if a
   component has `binding != unbound` with no binding evidence.
2. Refuse if a required port of the abstract design has no declared external
   net binding.
3. Map every semantic pin to a physical pad **through a verified pad map**. A
   semantic pin without a pad map is blocked, never guessed by name similarity
   (the repo already enforces this for EP pads and pin maps).
4. Prefix refs per instance (`LED1_R1`) before merging into a project; refuse
   duplicate designators instead of renumbering silently.
5. Namespace abstract nets on merge (`<instance>:<net>` → chosen project net
   only when the user declares the mapping). Same-name nets must never merge
   implicitly; the repo's own layout rules already treat this as unsafe.
6. Keep `evidence[]`, `unknowns[]` and the four binding levels in an emission
   report; a converted netlist is not a verified board.

### 2.3 Worked example (LED instance → `netlist_check` shape)

Abstract result (abridged):

```json
{"components":[
  {"ref":"R1","kind":"resistor","value":{"value":560,"unit":"ohm"},
   "pins":[{"name":"1","semantic":"supply_side"},{"name":"2","semantic":"led_anode_side"}]},
  {"ref":"D1","kind":"led",
   "pins":[{"name":"A","semantic":"anode"},{"name":"K","semantic":"cathode"}]}],
 "connectivity":{"connections":[
   {"component":"R1","pin":"1","net":"status_led:VCC"},
   {"component":"R1","pin":"2","net":"status_led:LED_A"},
   {"component":"D1","pin":"A","net":"status_led:LED_A"},
   {"component":"D1","pin":"K","net":"status_led:SW_NODE"}],
  "nets":[{"id":"status_led:VCC","name":"VCC"},{"id":"status_led:LED_A","name":"LED_A"},
          {"id":"status_led:SW_NODE","name":"SW_NODE"}]},
 "ports":[{"id":"VCC","net":"status_led:VCC"},{"id":"SW","net":"status_led:SW_NODE"},
          {"id":"GND","net":"status_led:GND"}]}
```

After binding R1→0603 1 % 560 Ω (pads 1/2) and D1→a verified LED with pad map
`{anode: 2, cathode: 1}`, and declaring `VCC→+5V`, `SW_NODE→LED1_K`,
`GND→GND`, the converter may emit:

```json
{"components":[
  {"ref":"LED1_R1","kind":"resistor","physical_pins":["1","2"],
   "pins":{"1":"+5V","2":"LED1_K"}},
  {"ref":"LED1_D1","kind":"led","physical_pins":["1","2"],
   "pins":{"1":"LED1_K","2":"LED1_SW"}}],
 "power_nets":["+5V"],"ground_nets":["GND"],
 "external_nets":["+5V","GND","LED1_SW"],
 "net_rules":{"LED1_SW":{"power_net":"+5V"}}}
```

Note what changed: semantic `supply_side/led_anode_side` became physical `1/2`
**through the pad map**, and abstract net ids became declared project net names.
No step in this conversion is automatic in the current generator.

## 3. Gaps that must stay visible

- `intent.modules[].roles[].pads` needs physical pads; an abstract role list is
  not enough. The abstract result can seed `template`/role names, but `pads`
  must come from the bound library part.
- `*.module-plan.json` `members[]` are designators; abstract components are
  pre-binding, so a plan can only be produced after binding.
- `netlist_check` has no field for "abstract/unbound"; do not encode
  `MPN: null` as a fake part string — keep unbound modules out of the netlist
  until binding is real.
- Voltage/current port ranges have no machine field in the existing intent
  models except `power_nets[].current_a`; the proposal would carry them as
  `net_rules` evidence or a sidecar, not as invented constraints.

## 4. Requested minimal interface from TASK A

1. Accept a list of `ready_abstract` module results plus an explicit
   `port_map` (abstract `instance.PORT` → project net name) and an explicit
   component binding table (semantic pin → real pad).
2. Run the existing validators on the converted output (`netlist_check`,
   `pin_net_intent_check` with the project's declared intent) — those tools
   already catch missing/duplicate pins, NC conflicts and merged nets.
3. Record in the handoff that the conversion is a *derived* artefact: source
   `content_hash`, binding level reached, and `real_eda=NOT RUN` unless the EDA
   readback actually ran.

## 5. Non-goals

No change to `netlist_check.py`, `pin_net_intent_check.py`, `design_engine`,
`pcb-intent` schema, layout-module schema, connector, protocol or CI in this
task. No automatic library selection, no automatic net renaming, no claim that a
converted netlist is a verified board.
