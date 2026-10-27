# Handoff — parameterized standard circuit blocks (task F)

## State

- Worktree/branch: `feat/parallel-circuit-blocks`, base main `9a951ed`
  (source version 1.0.1). One independent PR; **not merged, not released, not
  installed**.
- Six modules work end-to-end (`list` → `describe` → `generate` → `validate`,
  plus `compose`): `led_indicator`, `button_input`, `open_drain_pullup`,
  `adc_divider`, `low_side_nmos`, `ldo_supply`.
- 210 circuit-block tests pass; the full repository suite (1988 tests) passes
  with the repo's own `python -m unittest discover -s tests`.
- Frozen CLI benchmark: 54/54 (43 cases + 11 holdouts, 101 CLI calls,
  `real_eda=NOT RUN`).
- Four document-verified device categories + the I2C bus standard are bundled;
  no EDA, connector, marketplace or physical work was performed.

## Read first

1. `docs/parallel-circuit-blocks/contract.md` — normative interface.
2. `docs/parallel-circuit-blocks/quickstart.md` — 5 V dual-button/dual-LED
   design in a few commands.
3. `docs/parallel-circuit-blocks/module-catalog.md` — per-module inputs,
   formulas, refusals, ports.
4. `docs/parallel-circuit-blocks/report.md` — verification levels and limits.
5. `docs/parallel-circuit-blocks/source-register.md` — every device fact and
   its primary source.
6. `docs/parallel-circuit-blocks/integration-proposal.md` — how task A can map
   an abstract result to the existing connectivity/intent models **without**
   this task editing them.

## Try it

```powershell
$env:PYTHONPATH = "design-hardware/scripts"
python -m circuit_blocks list
python -m circuit_blocks describe adc_divider
python -m circuit_blocks generate low_side_nmos --example --summary
python -m circuit_blocks compose --input benchmarks/circuit-blocks/examples/dual_button_dual_led.design.json --out design.json
python -m circuit_blocks validate design.json --design
python benchmarks/circuit-blocks/run_benchmarks.py
```

## What is proven / not proven

Proven offline: the arithmetic (exact rational intervals, hand re-derivation),
the E-series selection, the endpoint/net/port contract, compose merge rules and
conflict detection, determinism and tamper detection.

Not proven / `NOT RUN`: part binding, library/footprint binding, host EDA
readback, physical measurement, ADC accuracy, switching loss, dynamic thermal
behaviour, EMC/ESD, Monte-Carlo tolerance. `ready_abstract` means "maths and
connection contract hold for the declared inputs/facts", nothing more.

## Next steps (outside this task)

1. Task A: implement the proposed converter (abstract result + explicit
   `port_map` + verified pad map → `netlist_check` / `design_engine` /
   `intent.modules`). Requirements in `integration-proposal.md` §2.2.
2. A part-selection layer: bind real orderable parts, verify pin/package
   identity, then flip `binding.part_binding`/`library_binding` from `NOT RUN`.
3. Optional: add more verified fact files (LED, Schottky, connectors) and more
   blocks (buzzer, MOSFET gate drive variants) using the same `Block` pattern —
   auto-discovery means no registry edit is needed.
4. Optional: move the frozen benchmark into CI as a non-EDA regression; it is
   standard-library only.

## Guardrails

- Do not treat any generated result as a schematic or a hardware sign-off.
- Do not copy `components[].value` into a BOM without the datasheet/tolerance
  check the constraints require.
- Do not merge abstract nets by name; only explicit `port_map`/connections.
- Keep the `binding` levels honest: a verified document fact is not a bound part.
