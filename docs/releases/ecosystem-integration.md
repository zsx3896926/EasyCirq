# v1.0 EasyEDA ecosystem integration

The user expanded the v1.0 release scope before publication. PR #33 remains a
release candidate, not a published version. Eight pinned upstream sources are
recorded in design-hardware/assets/ecosystem/registry.json.

## Delivered integrations

| Upstream | Delivered behavior | Deliberately separate evidence |
|---|---|---|
| quick-equal-length | Ordered path/differential geometry audit; bounded 45-degree tuning candidate | Full push routing, impedance, return path, native DRC and write-back NOT RUN |
| design-rule-generator | Explicit net/width/gap/mate consistency and preview | No RBF model or production impedance approval |
| batch-data-export | Actual collector JSON contract, availability/identity/summary validation, supplemental feedback fields | No fabricated writable before_dump; no atomic multi-document claim |
| ai-reuse-block-placement | Real catalog contract, search and hash-bound existing-instance reuse plan | No automatic library writes or placement; native checks separate |
| format-skill | Six unchanged MIT schemas with provenance; document-aware conservative validation | Unsupported schema constraints => incomplete, not full Ajv validation |
| viewer | Safe archive/record inspection and local read-only viewer protocol adapter | Renderer not bundled; actual browser rendering NOT RUN |
| client-cli | Runtime-help discovery plan, source-of-truth discipline | No automatic invoke/session/exports; runtime execution remains existing adapter responsibility |
| api-skill | Local docs/SDK index and content-bound lookup | No automatic bridge or port scan; signatures must match installed runtime |

The new scripts are integrated via scripts/ecosystem.py and routed from SKILL.md.
The installer lifecycle also invokes tools/ecosystem_smoke.py against the
actually installed archive contents, not only the source checkout.

## Verification

- 123 focused ecosystem tests passed; full guarded offline suite 1782 OK
  (skipped=1), zero failures/errors, zero blocked real-EDA attempts.
- Import sweep: 100 modules, zero blocked/error/system_exit.
- Skill selftest: 5 PASS; existing benchmarks 9/9 and 16/16 pass.
- Unified subprocess entry: 12/12 synthetic offline scenarios passed.
- Actual API Skill documentation snapshot indexed/queried outside the repository;
  query hits have source byte hashes and line numbers. Version is caller-declared.
- File adapter developer replay inspected an existing frozen dual-button archive
  without changing bytes; structural checks are not a restore/import exercise.
- Detailed machine summary: ecosystem-acceptance.json.

## Review findings fixed

Independent cross-review reproduced and fixed adjacent backtracking counted as
extra copper length; contradictory two-sided differential rules; catalog identity
field overwrite and invalid classifications; unsupported schema constraints hidden
by empty arrays; empty document identities; malformed project metadata; preview
output clobbering its adapter; documentation TOCTOU/hash mismatch and non-object
index error handling. Negative tests remain in the suite.

The first guarded run also exposed a pure Node test's inline protocol string
being conservatively rejected as an EDA command, plus the sandbox's excessive
Windows temporary path depth. The Node test now runs the same assertions from a
file; the guard is unchanged. Accepted local suite used an explicit short temp
root C:/Users/jlc/work/hds-test-temp; no test or guard was disabled.

## Artifacts and limits

Local evidence: C:/Users/jlc/work/v1-ecosystem-*-accepted.*,
v1-ecosystem-suite-accepted.json, v1-ecosystem-smoke.json,
v1-ecosystem-api-index.json and v1-ecosystem-api-query.json.
Clean package/lifecycle output is v1-ecosystem-package-lifecycle.json after build.
All new host operations remain NOT RUN; existing feedback final-code live-write
and compose strict-gate limitations are unchanged. No installed user client,
shared EDA window, external executor, manufacturing order or Release was modified.

Apache-2.0 applies to our own content; copied schemas retain original MIT text.
Upstream source or algorithms are not relabeled as our production-verified engine.
