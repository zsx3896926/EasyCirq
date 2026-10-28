# Cross-module contract (integration view)

Status: **draft integration contract, no adapters implemented yet**

This file fixes the *minimum common semantics* that the parallel tools must share
before any of them can be chained automatically. It is an integration document,
not a module contract: every module keeps its own versioned schema and stays the
owner of its own semantics.

## 1. Why this file exists

The nine parallel deliveries (A–K) each ship a working offline CLI with its own
versioned JSON schema. They were reviewed and merged independently into `main`.
**No producer→consumer adapter exists in the code**: every module's
`docs/parallel-*/integration-proposal.md` says the adapter is future work, and
the integration probes in `verify_integration.py` show the consumer rejecting the
producer's native output (see `evidence/integration-verification.json`).

So the current truthful state is:

| capability | state |
|---|---|
| each module runs on its own native input | **implemented and verified** |
| F → B (generated circuit → electrical review) | **GAP: no adapter** |
| J → re-check selection (change impact → B/C/E/F/I checks) | **GAP: J plans generic verification items, no module adapters** |
| G/K → A (layout/pose plan → PCB plan adapter) | **GAP: A is unmerged draft; no schema mapping** |
| C audits an existing delivery package | **implemented (native)** |
| H / I generate procurement / bring-up plans | **implemented (native)** |
| one shared snapshot identity across modules | **GAP: each module has its own snapshot/revision fields** |

## 2. Minimal common semantics (normative for future adapters)

An adapter may not invent these; it must map them explicitly and preserve
unknowns.

### 2.1 Identity

* `project_id` — stable project identity, independent of display name/path.
* `document_id` — `schematic|pcb|<other>` + project + revision; never a file path.
* `revision` — design revision string; changing contents without a revision
  change is a contract violation.
* `instance_id` — stable per-component identity (`cmp:U1` style); designator is a
  display attribute that may be renamed.
* Consumer rule: two documents are the same object only if identity fields match;
  a hash match alone is not an identity.

### 2.2 Units

* SI base with explicit unit strings at every numeric leaf (`{"value": 10, "unit":
  "kohm"}` style), or documented canonical units for the whole document.
* No bare magic numbers: a module that cannot determine the unit must emit
  `unknown`, not a default.
* Length: mm for mechanical/layout, mil must be converted explicitly and recorded.

### 2.3 Snapshot binding

* Every report binds to `(document_id, revision, content_sha256)` of the input it
  actually read.
* A stale or missing hash is `unknown`/`incomplete`, never `pass`.
* A synthetic fixture hash (like the zero hash in
  `fixtures/minimal-board/board.json`) must be rejected by any module that
  requires real binding.

### 2.4 Provenance

* Every fact/number has `source` (id, document, revision, page/table, URL) or is
  explicitly `synthetic`/`unknown`.
* Real EDA reads, host DRC, save/reopen, physical measurements and manufacturing
  are separate provenance levels; none may be inferred from a lower level.

### 2.5 Unknown

* `unknown` is a first-class state and must survive the chain. It may not be
  collapsed to `pass` by an adapter, a default, or an empty list.
* `unknown` must be itemised (which object/field/why) so the next module can
  decide.

### 2.6 Plan vs execution

* A plan is not an execution permit: candidates are `executable:false` until a
  writer applies and re-reads them.
* Offline tools never write EDA state, never call the connector and never claim
  hardware results.

### 2.7 Offline vs real machine

Every report needs explicit markers (`real_eda: NOT RUN|...`, `simulated: true`,
`physical_test: NOT RUN`) and a `not_checked`/`not_covered` list.

## 3. Field mapping per module (what exists)

| module | schema / status | identity | units | snapshot binding | unknown | plan vs execution |
|---|---|---|---|---|---|---|
| B `electrical_review` | `easycirq.electrical-review.input/v1`, `.report/v1` | `project`, component `instance_id`, ref | per-field `unit` | `input.sha256` + `semantic_sha256` | `review_required`/`incomplete` statuses, per-rule unknown | report only; no write |
| E `return_path_audit` | `return-path-audit-report/v1` | layer/via/net ids | `units.mil|mm` declared | `input_sha256` in report | unknown for arcs/unsupported geometry; `recovered_return_path` always false | report + analysis SVG only |
| G `mechanical_layout` | own `report`/`plan` JSON | object ids, datums | mm canonical, mil conversion | source snapshot fields | `review` status, missing geometry → unknown | `only_planned`, `executable:false` |
| F `circuit_blocks` | `easycirq.circuit-blocks.*` abstract result | module instance id, ports | SI strings | no snapshot (abstract) | `unknown_ids`, `ready_abstract` ≠ bound | abstract design only |
| J `change_impact` | `hds-change-impact-*/v1` | typed object ids (`cmp:`, `net:`) | per-change units | `baseline`/`candidate` content_hash + revision | `incomplete`, `possible`, unknown_objects | verification plan only |
| H `procurement_planner` | `procurement-input/v1` | MPN/designator identity | money as strings + currency | `evaluation.as_of`, snapshot kind | `planned_with_unknowns`, unknown stock/price | order plan only, not an order |
| I `bringup_planner` | `bringup-plan-input/v1`, `bringup-plan/v1` | plan/input/revision/tool_version binding | units per measurement | raw+semantic sha, revision | `INCOMPLETE`, `SYNTHETIC_ONLY` | human-executable steps; PASS only for real evidence |
| C `delivery_audit` | `delivery-audit/v1`, `delivery-manifest/v1` | package + layer identity | Gerber/drill units parsed | `content_manifest.sha256` | unsupported feature → unknown; `incomplete` | read-only audit |
| D `skill_knowledge_audit` | `scan`/`rules`/`plan` JSON | file/anchor identity | n/a | file SHA-256 + catalogue version | budget gaps surfaced | plan only; never edits docs |

## 4. Gaps an adapter author must close (not "unify the modules")

1. **F → B**: B needs components/pins/connectivity/evidence/facts with units and
   evidence ids; F emits abstract ports/endpoints and no electrical evidence.
   Required: explicit `port_map` + fact/evidence ids + unit mapping; unknown stays
   unknown.
2. **J → B/C/E/F/I**: J's `verification_catalog` items are generic. A mapping
   table from J item ids to module commands (and rule ids) is required; until
   then J's plan is *selection advice*, not an automated re-check.
3. **G → A**: G emits a mechanical candidate plan (`executable:false`); A's PCB
   plan/adapter is not merged (PR #36 draft, conflicting) and has no mechanical
   schema. Need a plan-adapter owned by A with re-audit after apply.
4. **K → A**: K (annotation layout) now exists and emits `only_planned` annotation
   poses plus an independent recheck. A must re-read the host before applying; there
   is no K→A adapter and A is still an unmerged draft, so nothing applies a K plan
   automatically.
5. **C/H/I inputs**: each takes a hand-authored native document; no common
   exporter exists. A delivery manifest (C) does not feed H/I automatically.
6. **Identity drift**: B/E/J use different snapshot/revision field names for the
   same concept. Adapters must map explicitly; no shared "assume same revision".

## 5. Verification rule

`verify_integration.py` only reports:
* `native` checks — the module ran on its own documented fixture;
* `gap` checks — a producer output was deliberately fed to a consumer and was
  rejected (recorded exit code/status), or the consumer/producer is absent.

An integration claim is only allowed when an adapter exists in the repository and
a runnable check exercises it end to end. Hand-editing a JSON between modules is
not an adapter and must not be reported as an automated chain.
