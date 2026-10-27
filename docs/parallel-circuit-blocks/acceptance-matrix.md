# Acceptance matrix

Status vocabulary: **DONE** (implemented and exercised by a real run),
**PARTIAL** (implemented with a named gap), **NOT RUN** (deliberately not
executed; must not be read as a pass).

Baseline: main `9a951edc21481dc3ae91460acc11aa3e08a7be8a`, branch
`feat/parallel-circuit-blocks`, isolated worktree.

## 1. Isolation and scope

| Requirement | Evidence | Status |
|---|---|---|
| only `design-hardware/scripts/circuit_blocks/`, `tests/circuit_blocks/`, `benchmarks/circuit-blocks/`, `docs/parallel-circuit-blocks/` touched | `git diff --stat main...HEAD` in `report.md`; final diff-scope check | DONE |
| no edit to SKILL.md, references, README/CHANGELOG/version, main handoff, runtime/connector/protocol, distribution, CI, top-level deps, feedback, compose, design_engine, ecosystem, other parallel dirs | same diff check | DONE |
| independent worktree, branch, recorded base SHA | `git worktree list`; base SHA above | DONE |
| no EDA call (not even read-only), old CLI, connector, window switch, global config, process kill | no such command was issued; tool transcripts | DONE |
| network only for primary-source verification; no marketplace/stock/API, no upload, no purchase | `source-register.md` (manufacturer PDFs only) | DONE |
| no merge, no release, no install of user clients; push + independent PR only | `report.md` PR link; no tag/release/install step | DONE |

## 2. Baseline investigation (M0)

| Requirement | Evidence | Status |
|---|---|---|
| current main/version/repo layout verified on site | main `9a951ed`, source version 1.0.1, layout surveyed | DONE |
| existing connectivity/intent/module data structures read before inventing format | `integration-proposal.md` §1 quotes `netlist_check`, `pin_net_intent_check`, `design_engine` IR, `pcb-intent` modules, module-plan | DONE |
| no parallel/incompatible netlist invented; mapping proposed instead of editing shared scripts | `integration-proposal.md` | DONE |
| common bug recorded with a reproduction, not fixed outside scope | two core defects were in this task's own new code (fixed); no pre-existing shared-script bug was found and changed | DONE |

## 3. Technical method and sources

| Requirement | Evidence | Status |
|---|---|---|
| input schema, applicability, required facts, formulas, tolerance model, network contract, failure/unknown semantics, sources per module | `module-catalog.md`, `describe` output, module docstrings | DONE |
| primary sources only; URL, revision, page/section, applicable part, condition | `source-register.md` + `devices/facts/*.json` (`facts.*.source`, `.condition`, `.applies_to`) | DONE |
| no copied unknown internet module; no pin assumption by generic name | abstract semantic pins only; no physical pin claimed (`contract.md` §3, `validate` rejects unbound port/pin claims) | DONE |
| licences: no unclear-licence image or whole manual packaged | only numeric facts + citation metadata; no PDF/image committed | DONE |

## 4. CLI and module outputs

| Requirement | Evidence | Status |
|---|---|---|
| `python -m circuit_blocks` with list/describe/generate/validate/compose | `cli.py`; 54 benchmark cases call it | DONE |
| output contains schema/module_type/template_version/instance_id/normalised units/content hash | every result; `contract.md` §3 | DONE |
| components: abstract role, nominal/tolerance/power/voltage, polarity, pin semantics, candidate standard values; unbound MPN/library | `Draft.component`; `validate` requires `binding: unbound` | DONE |
| ports: direction, power/analog/digital/ground role, legal level/current | every module's `ports[]` | DONE |
| connectivity: nets, endpoints, external ports, explicit NC/unknown | `connectivity` + `no_connect` state; NC path covered in `test_button_input`/validation tests | DONE |
| calculations: formula, inputs, derived range, margin, recomputed value, preconditions, unmodelled factors | `calculations[]` in every result | DONE |
| constraints: hard vs advisory vs layout vs verification | `constraints[].kind` | DONE |
| evidence: manufacturer fact / user declaration / derivation / assumption; missing never disguised | `evidence[].kind`, `verified`, `unknowns[]` | DONE |
| statuses `ready_abstract` / `needs_device_facts` / `unsupported` / `input_invalid`; no `hardware_pass` | `result.py STATUSES`, `validate.py`; grep confirms no `hardware_pass` | DONE |
| optional analysis SVG marked as not an EDA schematic | `svg.py` disclaimer; `--svg` on generate/compose | DONE |
| drawing never the only connection source | connectivity is authoritative; SVG is a projection | DONE |

## 5. Modules F1–F6

| Module | Normal | No solution | Missing facts | Tolerance boundary | Status |
|---|---|---|---|---|---|
| F1 LED | `test_led_indicator` normal set | conflicting current window → unsupported | point Vf / missing LED Imax / missing switch facts | 32.000 mA accepted, 31.999 mA rejected | DONE |
| F2 button | pull-up + RC, pull-down | contact-current-limited window empty → unsupported | missing V_IH/V_IL → needs facts | level at threshold tolerance; RC crossing times | DONE |
| F3 open drain | custom + I2C fast | empty interval with both bounds | missing V_OL/I_OL or C_bus | rise-time endpoint accepted, one step beyond rejected | DONE |
| F4 ADC | 1–5 V → 0–3.3 V | 10 Ω source-impedance limit → unsupported | missing ADC leakage → needs facts | worst-case tap exactly at ADC max accepted | DONE |
| F5 NMOS | verified AO3400A + DC variant | ID/dissipation/Tj violation | no fact source → needs facts | ID 5.7 A legal, 5.71 A rejected | DONE |
| F6 LDO | verified TLV75533P + caller facts | headroom/Tj/variant/envelope violations | missing fact keys, θJA/board condition | headroom 3.5645 V legal, 3.5644 V rejected | DONE |

Module-specific review claims: `calculation-review.md`. Device facts:
`source-register.md` (LDO, MOSFET, LED, Schottky diode, I2C bus spec = 4 device
categories + 1 standard).

## 6. Standard values, search and uncertainty

| Requirement | Evidence | Status |
|---|---|---|
| versioned E12/E24 (plus E6/E48/E96) and configurable range | `eseries.py` (IEC 60063 tables), `allowed_values`/`value_range` inputs | DONE |
| deterministic selection, recorded basis | objective enum + ascending tie-break; `candidates[]` in components | DONE |
| intervals cover supply/component/device ranges; correlation assumptions written down | `ranges.py`; `assumptions[]` in results | DONE |
| boundary not flipped by rounding | exact `Fraction` arithmetic; boundary cases above | DONE |
| invalid units/bool/NaN/inf/negative/inverted range/missing facts/empty candidates/duplicate endpoint/unknown module strictly handled | input tests per module + `validate`; benchmark `input_invalid` cases | DONE |
| missing information never silently defaulted to `ready_abstract` | `needs_device_facts`/unknown tests | DONE |

## 7. Composition

| Requirement | Evidence | Status |
|---|---|---|
| compose multiple modules into an abstract design with stable namespaces, instance identity, external port binds, net partitions | `compose.py`; `test_compose.py`; 13 compose benchmark cases | DONE |
| prevent internal net-name collision, duplicate designators, ground/power mis-merge, unbound required port, input conflict, illegal voltage-domain connection | explicit merge only; `ground_power_merge`, `output_contention`, `voltage_domain_conflict`, `unbound_ports` | DONE |
| same name never auto-merges; explicit port_map/connection only | `test_same_net_name_does_not_merge_implicitly` | DONE |
| re-verify level/current contracts after composition | design-net voltage intersection + current capability/demand contract | DONE |
| proven conflict refuses; unprovable reports `incomplete` | compose status tests + benchmark cases | DONE |
| deterministic re-run; display rename does not change topology; two instances never share identity | `test_design_is_deterministic`, `test_display_name_does_not_change_the_topology_hash`, namespaced refs/nets | DONE |
| intentional common vs isolated ground handled explicitly | `design_ports[].isolation`; holdout `compose_grounds_split` | DONE |

## 8. Tests, benchmarks and holdouts

| Requirement | Evidence | Status |
|---|---|---|
| per module: normal, no-solution, missing-facts, tolerance boundary | 212 unit tests (25/36/36/26/37/33 + 19 compose) | DONE |
| expected values independently derived | formula comments; `calculation-review.md` | DONE |
| ≥24 real CLI scenarios incl. six modules and compose positive/negative | **54** frozen CLI cases (43 `cases/` + 11 `holdout/`), 101 CLI invocations | DONE |
| frozen input SHA, expected standard value/interval/status/endpoints; post-generate `validate` consistency | every `case.json` has `input_sha256` + expectations; runner validates and recomputes | DONE |
| tampered net / resistor value must be detected | runner tamper checks: hash detection and recompute detection for net and value | DONE |
| ≥4 distinct holdout inputs, no fixture name in implementation | 11 holdouts under `benchmarks/circuit-blocks/holdout/`; grep shows no fixture name in `circuit_blocks/` | DONE |
| transformations: unit conversion, candidate ordering, JSON order, consistent rename; tightening must not improve feasibility | per-case variants (`unit_respelling`, `tighten_*`); deterministic ordering; rename tests | DONE |
| threshold/power extremes, tolerance endpoints, namespace collisions | benchmark cases + compose tests | DONE |
| ≥3 device fact categories with exact MPN and primary sources, incl. LDO + MOSFET | 4 categories: TLV75533PDBVR, AO3400A, APT1608SURCK, BAT54 + UM10204 bus standard | DONE |
| other modules may use clearly artificial fixtures marked simulated | LED/button/ADC/NMOS caller facts tagged `user_declared`/`verified: false` | DONE |
| benchmark records correctness/coverage/timing and `real_eda=NOT RUN`; no speed-up claim | `benchmarks/circuit-blocks/results.json` | DONE |

## 9. Integration and deliverable documents

| Requirement | Evidence | Status |
|---|---|---|
| minimal abstract module → existing connectivity/intent mapping + example for task A, without editing shared paths | `integration-proposal.md` | DONE |
| library binding must validate real pin/package/identity before use | `contract.md` §3/§9, `integration-proposal.md` §2.2 | DONE |
| required docs: contract, module-catalog, source-register, calculation-review, acceptance-matrix, report, integration-proposal, handoff | all eight present in `docs/parallel-circuit-blocks/` | DONE |
| quick start: 5 V two-button two-LED abstract design without EDA | `quickstart.md` + `benchmarks/circuit-blocks/examples/dual_button_dual_led.design.json` | DONE |
| report separates math / manufacturer facts / topology contract / part binding / host / physical; later ones NOT RUN | `report.md` verification-level table | DONE |
| generated result is not a hardware sign-off | `contract.md`, report, README-level wording | DONE |

## 10. Execution order and closing

| Requirement | Evidence | Status |
|---|---|---|
| M0–M4 execution with real code and verification | git history, benchmark, tests | DONE |
| diff contains only allowed paths; committed, pushed, independent PR opened | `report.md`; PR link | DONE |
| no merge, no release, no user-client installation | PR left open; no release/tag/install | DONE |
| no expansion into an auto-selection platform or generic SPICE solver | six modules + compose only; no SPICE/netlist simulator | DONE |

## Verification levels (never collapsed)

| Level | Status |
|---|---|
| mathematical calculation | **reviewed offline** (exact arithmetic, hand re-derivation) |
| manufacturer document facts | **verified for 4 parts + 1 bus standard**, citations in `source-register.md` |
| topology/connection contract | **reviewed offline** (structural validation + compose checks) |
| device/part binding | **NOT RUN** — no MPN is bound to a component, no stock/package identity check |
| library/footprint binding | **NOT RUN** |
| host schematic/PCB validation | **NOT RUN** — no EDA was called, not even read-only |
| physical measurement | **NOT RUN** |
| `real_eda` | **NOT RUN** |

## Known gaps / limits (not acceptance failures, but must not be over-read)

- Self-review only; no independent blind reviewer was available.
- ADC accuracy, LED temperature drift inside the declared range, switching loss,
  dynamic thermal behaviour, EMC/ESD and tolerance Monte-Carlo are not modelled;
  each is listed as an `unknown`/`not_modelled` in the corresponding result.
- No device-fact file exists for the LED in the examples; it is an abstract role
  with caller-declared ranges (`verified: false`).
- Compose proves only the declared boundary contracts; it does not simulate,
  place or route.
