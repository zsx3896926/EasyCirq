# Report: parameterized standard circuit blocks (parallel task F)

Branch `feat/parallel-circuit-blocks`, base main `9a951edc21481dc3ae91460acc11aa3e08a7be8a`
(source version 1.0.1). Worktree isolated from the other parallel tasks. One
independent PR; nothing merged, released or installed.

## What was built

An offline generator that turns declared electrical constraints into a
**mathematical + connectivity contract** for six recurring circuits, plus a
composer that combines instances into an abstract design with explicit net
merges and conflict checks.

| Piece | Path |
|---|---|
| generator package (`python -m circuit_blocks`) | `design-hardware/scripts/circuit_blocks/` |
| six modules | `blocks/led_indicator.py`, `button_input.py`, `open_drain_pullup.py`, `adc_divider.py`, `low_side_nmos.py`, `ldo_supply.py` |
| core (exact arithmetic, units, intervals, E-series, schema, result envelope, validation, compose, SVG) | `numeric.py`, `units.py`, `ranges.py`, `eseries.py`, `schema.py`, `result.py`, `canvas`-free `compose.py`, `validate.py`, `svg.py`, `cli.py` |
| verified device facts | `devices/facts/*.json` + `devices/SCHEMA.md` |
| tests | `tests/circuit_blocks/` (7 files) |
| frozen CLI benchmark | `benchmarks/circuit-blocks/` (54 cases, runner, examples, results.json) |
| documents | `docs/parallel-circuit-blocks/` |

Each result contains: normalised inputs with canonical units, abstract
components with selected standard values, ports with legal voltage/current
ranges, namespaced nets and endpoint→net connections (explicit `no_connect`
where applicable), calculations with formulas/margins/assumptions,
hard/advisory/layout/verification constraints, evidence with primary-source
citations or explicit `user_declared`, unknowns, and a content hash.

Statuses: `ready_abstract`, `needs_device_facts`, `unsupported`,
`input_invalid` (compose adds `incomplete`). A design can never be reported as
`hardware_pass`; no such field exists.

## Verification actually executed

| Check | Result |
|---|---|
| circuit-block unit tests (`tests/circuit_blocks`: 7 files) | **210 tests, OK** (LED 23, button 36, open-drain 36, ADC 26, NMOS 37, LDO 33, compose 19) |
| full repository test suite (`python -m unittest discover -s tests`) | **1988 tests, OK** — the new tests are discovered with the repo's own CI command and nothing existing regressed |
| frozen CLI benchmark (`benchmarks/circuit-blocks/run_benchmarks.py`) | **54/54 cases passed** (43 `cases/` + 11 `holdout/`), 101 CLI invocations, `real_eda=NOT RUN` |
| per-case checks | exit code, status, frozen input SHA-256, component values/series/tolerance/binding, ports, nets, endpoint→net, calculation values (1e-9 rel.), `validate --recompute` match, tampered net and tampered component value rejected both with the original hash and with a re-computed hash |
| determinism | same inputs → identical bytes/hash; unit respelling → same hash; display rename → same topology hash |
| result self-validation | every `generate` runs `validate_module_result` on its own output; a generator bug raises instead of emitting a plausible result |
| timing | median 223 ms, p95 293 ms per CLI invocation (Python 3.13, Windows, cold subprocess each call). This is **generation** time, not board-design speed; no speed-up is claimed. |

Verified device facts (primary manufacturer/standards documents; details in
`source-register.md`):

| fact_id | category | exact MPN | document |
|---|---|---|---|
| `ldo_tlv75533p` | LDO | TLV75533PDBVR (SOT-23-5) | TI SBVS320D (rev. Sept 2024) |
| `mosfet_ao3400a` | N-MOSFET | AO3400A (SOT-23) | AOS Rev 3.1 (Jul 2023) |
| `led_apt1608surck` | LED | APT1608SURCK | Kingbright DSAD0926 V.22A (2023-04-08) |
| `diode_bat54` | Schottky | BAT54 (SOT-23) | onsemi BAT54/D Rev. 3 |
| `bus_i2c_um10204` | bus standard | — | NXP UM10204 Rev. 7.0 (2021-10-01) |

`APT1608SURCK` and `BAT54` are bundled fact files proving document-verification
of the format; the example modules use the LDO and MOSFET fact files or
clearly-labelled caller-declared facts. No LED/diode MPN is bound by any module.

## Verification levels (kept separate on purpose)

| Level | Status |
|---|---|
| mathematics / calculations | reviewed offline with independent re-derivation (`calculation-review.md`) |
| manufacturer document facts | verified for the five documents above; every fact carries condition + section |
| topology / connection contract | reviewed offline; compose re-checks voltage/class/current contracts |
| device / part binding | **NOT RUN** — no MPN is bound to a component; no stock/package identity check |
| library / footprint binding | **NOT RUN** |
| host schematic/PCB validation | **NOT RUN** — no EDA tool was called, not even read-only |
| physical measurement | **NOT RUN** |
| `real_eda` | **NOT RUN** |

Consequences: a `ready_abstract` result is *not* a schematic, BOM, manufacturable
board or hardware sign-off. The abstract semantic pins are not physical pad
numbers; a later binding layer must map them through a verified pad map.

## Composition

`compose` merges only what the caller explicitly declares (`connections`,
design-port `members`, `optional_unbound`). It refuses proven conflicts
(`ground_power_merge`, `voltage_domain_conflict`, `output_contention`,
`current_contract_conflict`) and reports `incomplete` when compatibility cannot
be proven (unbound ports, unknown current capability, a block that needs facts).
Two `ready_abstract` blocks never add up to a "ready board" automatically.

Documented quick start (5 V, two buttons + two LEDs) composes to
`ready_abstract` with ten design ports and ten namespaced components; a second
example adds an LDO with explicit EN tying and a declared 5 V current boundary.

## Defects found and fixed during the work

- pull-down button exposed both contact terminals on VCC (fixed in the block,
  regression test + benchmark case added);
- `devices.evidence_for` crashed on tabulated facts (now summarised);
- compose mishandled blocks that failed before producing a port table (now
  reported as `unsupported`/`incomplete` instead of `input_invalid`);
- compose treated an inbound design-port current as demand (now a boundary
  rating/capability).

See `calculation-review.md` for the arithmetic review and `acceptance-matrix.md`
for the requirement-by-requirement evidence table.

## Explicit non-goals (not done, by design)

No EDA, connector, protocol or old-CLI interaction. No marketplace/stock/pricing
API. No automatic part selection, no library/footprint creation, no SPICE or
thermal simulation, no PCB placement/routing. No change to SKILL.md, existing
references, README/CHANGELOG/version, main handoff, CI, distribution, feedback,
compose/executor or any other parallel-task directory. Shared-code integration is
a **proposal** in `integration-proposal.md`, not an edit.

## Reproduce

```powershell
cd <worktree>
$env:PYTHONPATH = "design-hardware/scripts"
python -m circuit_blocks list
python -m circuit_blocks generate led_indicator --example --summary
python -m circuit_blocks compose --input benchmarks/circuit-blocks/examples/dual_button_dual_led.design.json
python -m unittest discover -s tests/circuit_blocks -p "test_*.py"
python benchmarks/circuit-blocks/run_benchmarks.py --json
```

## Git / PR

- branch: `feat/parallel-circuit-blocks` (worktree separate from the other
  parallel tasks; only the four allowed path groups are modified)
- commits: see `git log main..HEAD`
- PR: opened against `main`, not merged, no release, no install
