# EasyEDA batch capture and module reuse

This integration is offline and read-only. It adds runnable adapters rather than
installing or starting the upstream extensions. Run from the Skill directory.

## Batch-export logs

```bash
python scripts/ecosystem_capture.py --input export.json --out capture.json
python scripts/ecosystem_capture.py --input export.json --binding binding.json --out capture.json
```

Accepted input follows the upstream `checkProjectInternal` log:
`checkTime`, `projectInfo`, `checkResults[{checkType,status,details}]`, `summary`.
The adapter recognizes the pinned Chinese `checkType` values and exact list/count
keys, rejects duplicate sections and contradictory counts, distinguishes absent,
failed, measured-empty and measured-nonempty categories, and checks a sidecar
binding against the exact input bytes when using the CLI.

A binding sidecar is:

```json
{"source_sha256":"<SHA-256 of export.json bytes>","project_uuid":"p1","document_uuid":"pcb1","window_id":"w1"}
```

The sidecar is an independent assertion, not new host evidence. Unbound document
and window IDs stay unknown. The exporter can switch foreground documents; no
single atomic SCH/PCB snapshot is inferred. The report always has
`write_ready:false`, `before_dump:null`, `status:partial|invalid`.

`pcb` / `sch` preserve collected payloads. `feedback_sections.pcb` uses feedback
object/track/via/region keys for supplemental comparison. It is **not** an
`hds-observation/v1` and is not acceptable as a complete raw write baseline.
Absent data remains null. Component pose/lock values are not promoted to measured
facts because the upstream mapper supplies default-zero/default-false fallbacks.
Likewise, arc-read exceptions are swallowed upstream; arcs can never be certified
complete from an empty list. Full geometry/identity/availability must still be
captured by the existing live dump route before writing.

`collected` is a collection result, not an electrical verdict. A DRC section with
an actual raw array matching issues/count is retained as `reported_empty` or
`issues_present`; no native/quality PASS is fabricated. No freshness conclusion is
made. `staleness_assessed:false` is explicit.

## CBB catalog search

```bash
python scripts/ecosystem_reuse.py search --catalog catalog.json --query "LDO capacitor" --library-kind team
```

The catalog is the upstream export format `formatVersion:0.2`,
`generator:ai-reuse-block-placement`, with libraries and module metadata. Failed
libraries are isolated and reported, never counted as empty-success. Module UUIDs
are namespaced by library UUID. Duplicate library/module identities are refused.
Module metadata cannot override authoritative library/module identity fields.
Classification is validated as an array of strings, not a string to split into characters.
Search is deterministic keyword filtering over name/description/classification;
it is not a semantic circuit-matching or automatic placement success claim.

## Bound placement candidate for existing instances

```bash
python scripts/ecosystem_reuse.py plan --catalog catalog.json --source module-selection.json --target target-selection.json --request request.json --out reuse-plan.json
```

Source/target use the local explicit `hds-module-selection/v1` contract, not raw
CBB project files. A measured source includes project/document/module/library
identity, units (`sch_raw` or `mil`), origin, components with primitiveId,
uniqueId, designator, device/footprint/symbol UUIDs, pose, locked bool and measured
pin-number/net arrays; plus wires, labels and flags arrays with explicit complete
coverage. Each wire declares pin_refs with designator/pin. It is the caller's
responsibility to obtain and review the selection in the host; arrays and
coverage declarations do not independently prove the host extraction is complete.

Request binds canonical JSON SHA-256 of catalog/source/target, exact module and
library IDs, a bijective component_map, a bijective network_map and a placement
origin. Canonical hash: UTF-8 JSON, sorted keys, no extra whitespace, no NaN.
The CLI fixture request shows the complete structure at repository path
`tests/fixtures/ecosystem-capture-reuse/request.json`.

The planner refuses stale snapshots, unidentified or locked target instances,
missing wire/label/flag coverage, wires with external/mismatched pin endpoints,
different pin sets, network partitions, devices, symbols or footprints. It emits
only translations/rotations of explicitly mapped existing target instances,
including their exact identities to preserve. No new instance, network change,
CLI mutation, save or reload is emitted. Other target components are locked by
omission. Spatial preflight and native DRC remain NOT RUN; status `candidate`
is not write-ready. Feed a reviewed candidate through current scoped placement
planning, measured obstacles and the existing before-dump write gate.

## Provenance and licensing

Contract source reviews pinned on 2026-10-27:

- [eext-batch-data-export](https://github.com/easyeda/eext-batch-data-export/tree/16c0b33ca318abf162d21a287e5695ed1d8c1e73),
  commit `16c0b33ca318abf162d21a287e5695ed1d8c1e73`, Apache-2.0;
  `src/checkProject.ts`, `src/dataCollectors.ts` and LICENSE.
- [eext-ai-reuse-block-placement](https://github.com/easyeda/eext-ai-reuse-block-placement/tree/c24c7228b022c53e509788ef375e1bf81bd82966),
  commit `c24c7228b022c53e509788ef375e1bf81bd82966`, Apache-2.0;
  `src/catalog.ts`, `src/short-circuit-flags.ts`, README.md and LICENSE.

Independent Python implementations; no upstream executable or source copied.
The adopted ideas are exact export contracts, failure-isolated library namespaces,
selection snapshot invalidation and supporting-conductor/net-marker completeness.
The fixtures are synthetic contract examples, not real host exports. Unit tests
and CLI subprocess tests do not constitute EDA, visual, DRC or hardware acceptance.
