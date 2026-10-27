# Quick start: generate the 5 V dual-button / dual-LED abstract design

No EDA, no connector, no marketplace. This produces a mathematical +
connectivity contract, not a schematic.

## 0. Setup

```powershell
cd <repo>
$env:PYTHONPATH = "design-hardware/scripts"   # or: cd design-hardware/scripts
```

Python 3.10+ with the standard library only.

## 1. See what exists

```powershell
python -m circuit_blocks list
python -m circuit_blocks describe led_indicator
python -m circuit_blocks facts list
```

`list` prints the six module types with their template versions; `describe`
prints every input field, its unit, whether it is required and the documented
example input; `facts list` prints the bundled device-fact files and their exact
MPNs.

## 2. Generate one block

```powershell
python -m circuit_blocks generate led_indicator --example --out led.json --summary
```

Read `led.json` (or pipe it): the interesting parts are

- `status`: `ready_abstract` means the maths and the connection contract hold
  for the declared inputs and facts;
- `components`: R1 is a selected E24/E96 value with tolerance and a power-rating
  requirement; D1 is an abstract LED role with a Vf range requirement; both are
  `binding: unbound`, `mpn: null`;
- `calculations`: the resistance window, the worst-case current at both supply
  extremes and the resistor dissipation, with formulas and assumptions;
- `connectivity`: nets with namespaced ids and endpoint → net bindings;
- `ports`: VCC / GND / SW with legal voltage/current ranges;
- `binding`: part/library/host/physical/EDA levels stay `NOT RUN`.

## 3. Compose the documented design

The frozen example is
[`benchmarks/circuit-blocks/examples/dual_button_dual_led.design.json`](../../benchmarks/circuit-blocks/examples/dual_button_dual_led.design.json):

```powershell
python -m circuit_blocks compose ^
  --input benchmarks/circuit-blocks/examples/dual_button_dual_led.design.json ^
  --out dual_button_dual_led.out.json
```

It composes four instances:

| instance | module | result |
|---|---|---|
| `btn1` | `button_input` | 10 kΩ pull-up + 100 nF RC, 1 ms nominal time constant, `OUT` port |
| `btn2` | `button_input` | same, independent instance |
| `led1` | `led_indicator` | 560 Ω E24, external low-side switch port |
| `led2` | `led_indicator` | 560 Ω E24, external low-side switch port |

and declares ten design ports: `VIN`, `GND`, `BTN1_A/B`, `BTN2_A/B`,
`BTN1_OUT`, `BTN2_OUT`, `LED1_DRIVE`, `LED2_DRIVE`. The output is
`ready_abstract`: every block port is bound to exactly one explicit design net,
no net is merged by spelling, and the design-level voltage/current contracts are
proven for the declared ranges.

You only fill in what the modules need (about 30 lines of JSON per block, most of
it copied from the example); you never fill in EDA UUIDs, packages or a pin map.

## 4. Look before you trust

```powershell
python -m circuit_blocks validate dual_button_dual_led.out.json --design
```

This re-checks structure, the content hash, ref uniqueness and namespace
isolation. Add `--svg out.svg` to any `generate`/`compose` command to get an
analysis-only drawing (explicitly labelled as not an EDA schematic).

Tamper test: change one component value or one net in the JSON and re-run
`validate` — it must fail (`content_hash_mismatch`). If you edit the hash too,
`validate --recompute` re-runs the module from its echoed inputs and detects the
change as well.

## 5. What you may and may not do next

May: hand the design to the selection/EDA execution layer with the explicit
requirement to bind real parts, verify pad maps and re-check the boundary
conditions; use the calculation values as the starting point for a datasheet
review.

May not: treat the abstract design as a schematic, a BOM, a manufacturable
board, or a hardware sign-off. Every device fact in the examples is either
user-declared (tagged `verified: false`) or a verified document fact; none is a
library/stock/physical verification.

## 6. Reproduce the benchmark

```powershell
python benchmarks/circuit-blocks/run_benchmarks.py --json
```

It runs the frozen CLI cases (including holdouts) and reports correctness,
coverage, timing and `real_eda=NOT RUN`.
