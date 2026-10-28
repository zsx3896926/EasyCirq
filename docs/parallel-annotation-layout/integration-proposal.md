# Integration proposal for the executor task (A)

Status: proposal from parallel task K (offline annotation layout planner).  It is
**not** a request to modify the executor, connector, compose pipeline or
`design_engine`.  K does not call EDA, does not write host files and does not
authorize any write.  This document tells A how it can consume a K plan safely
and what it must probe on the real host before trusting it.

## 1. Boundary

- K deliverable: `easycirq/scripts/annotation_layout/` plus
  `tests/annotation_layout/`, `benchmarks/annotation-layout/`,
  `docs/parallel-annotation-layout/`.  No changes to `SKILL.md`, existing
  references, runtime/connector/protocol, compose, `design_engine`,
  `layout_from_easyeda`, `sch_layout_check`, CI, dependencies or other tasks.
- K produces **pose plans** (`only_planned`, host execution `not_executed`).
  A remains the only component allowed to apply, save/reopen and verify on the
  host.
- A must re-read the target page and its capabilities at apply time.  A K plan is
  never a write authorization, and a stale plan must be rejected.

## 2. What K needs from A's snapshot (input extraction)

K's input is a versioned JSON (`annotation-layout/v1`); its contract is
`docs/parallel-annotation-layout/contract.md`.  A can either:

1. **Reuse the frozen fixture path** for regression only:
   `python -m annotation_layout convert --layout … --list … --rendered … --sheet …`
   (the photo-led shim; deterministic and SHA-bound), or
2. **Produce v1 directly** from its live snapshot (preferred for real work).  The
   following host reads are enough; no new EDA query type is required beyond what
   `easyeda sch list --include-bbox --include-pins --include-wires
   --include-page-primitives`, `sch sheet-geometry --from-svg`, and the SVG text
   measurement already provide:
   - page bbox, inner/usable bbox and title-block keep-out from `sheet-geometry`;
   - component bodies as conservative rectangles (real bbox, not symbol-name
     guesses), with designator and zone/read-order membership;
   - each text's measured bbox from the rendered SVG (`bbox_source=measured_svg`)
     and its kind/owner/content/anchor/rotation where the host actually exposes
     them; mark unknown rotation/alignment/font as unknown, never assume 0;
   - wires as independent segments (`flat-segments` split), with net/primitive
     IDs; net labels with `anchor_id` and `anchored`;
   - page zones/frames with member IDs, title block, and the raw y-up convention.
3. K's schema requires a `project.snapshot_sha256`, page ID and source file
   SHA-256s.  A should bind these to the exact readback it used; K rejects stale
   provenance.

If A supplies only a subset of texts, K reports incomplete coverage and cannot
claim visual completeness.  Do not replace missing bboxes with guesses just to
get a `planned_clear`.

## 3. Capability probe A must run on the host (do not assume history)

Historically, free-text moves were **not persistent** in this project, and
net-label text could not always be separated from its electrical anchor.  Those
are historical notes, not a guarantee.  A should probe each capability on a copy
of the target page and record the result:

| capability | probe | expected record |
|---|---|---|
| attribute (designator/value) translation | move one attribute by a small pose, `sch list` / `designator-geometry` readback, save + reopen, read again | `attribute_translate: supported/unverified/unsupported`, plus tolerance |
| attribute rotation/alignment | if K plans only translation, rotation can stay fixed; probe only if A wants rotated poses | `attribute_rotate`, `attribute_align` |
| free-text translation | create/move a free text, save + reopen, exported SVG readback | `free_text_translate`; **must not be assumed** from historical docs |
| net-label text vs anchor separation | move net-label text, check anchor/net stays attached (`sch read`/checker/export) | `net_label_detach`; if unsupported, K keeps net-label text fixed |
| UUID/ID stability across save/reopen | compare primitive IDs before/after | reject the plan if IDs drift |

Until probed, set the corresponding `host.capabilities` value to `unverified`
(the real photo-led fixture uses `attribute_translate=supported` from historical
notes, `free_text_translate=unverified`, `net_label_detach=unsupported`, all with
`capability_source=historical_docs_requires_onsite_probe`).  K will then:

- mark changes relying on unverified capability with `host_probe_required=true`;
- never move net labels when `net_label_detach` is not `supported`;
- report a remaining net-label conflict as `net_label_anchor_not_separable`
  rather than proposing a broken-anchor move.

## 4. Plan fields A should honour

A plan (`annotation_layout plan INPUT --out PLAN`) contains:

- `input.canonical_sha256`, `input.project.page_id/snapshot_sha256`,
  `input.source.files[]` — the exact baseline;
- `status` (`planned_clear` / `partial` / `blocked` / `needs_geometry`) and
  `noop`; **`plan_verified` is a verification result, not host acceptance**;
- `changes[]`: `id`, `role`, `content`, `content_sha256`, `owner`,
  `capability`, `host_probe_required`, `before.bbox/anchor`, `after.bbox/anchor`,
  `delta {dx,dy}`, `protected` (content/net/font/rotation/alignment/owner
  unchanged; component/wire edits forbidden);
- `verification`: independent recheck + the existing checker's before/after
  findings, `plan_verified` only when no introduced/remaining movable hard
  conflict and no estimated bbox was relied upon;
- `metrics`, `search` budgets, `status_detail.failures` with blocking IDs and
  minimal-gap suggestions;
- `host_execution: not_executed`, limitations, and analysis SVG artifact paths
  (`analysis_not_official_export`, not an official export).

A must reject a plan when: `status` is not `planned_clear`; `input` does not match
the current page/snapshot; any change's `content_sha256`, owner or protected
fields cannot be re-checked; `host_probe_required` is true for a capability that
was not probed; `verification.status` is not `plan_verified`; or the plan is
older than the target snapshot.

## 5. Pre-write baseline checks (A side)

Before applying any change:

1. re-read the page (same read options) and compare `page_id`, snapshot hash and
   the primitive IDs/content/owners of every changed annotation;
2. run the existing `sch_layout_check.py` on the current snapshot and compare
   its blocking findings with the plan's `verification.checker.before`
   (kind/objects); a mismatch means the snapshot moved — re-plan;
3. confirm the host capability record matches the plan's `host` block; if a
   change needs an unprobed capability, probe it or drop that change;
4. confirm `analysis_not_official_export` SVGs are being used only for human
   inspection, never as evidence.

## 6. Batch apply and post-write verification (A side)

- Apply only the listed translations to the listed annotation IDs; do not change
  content, net, anchor, rotation, font, components, wires or pages.
- After each batch (or one controlled page at a time): read back the actual
  attribute/free-text poses and compare with `after.bbox` within a declared
  tolerance; stop on any mismatch or ID drift.
- Save, reopen, and re-read; run the host checker and export the official
  image; re-run the existing offline checker on a fresh snapshot.
- Verify connectivity is unchanged (same netlist/pin-net intent, no new
  junctions/shorts) and that the export matches the page identity.  K's
  `electrical_assertion` is only a structural statement; real net readback is
  A's job.
- If a free-text move did not persist, record the capability as unsupported and
  feed that back into the next K input; do not claim the plan was applied.

## 7. Suggested interface shape (no shared code changes)

- A builds `annotation-layout/v1` from its own snapshot adapter and calls K as a
  subprocess:
  `PYTHONPATH=easycirq/scripts python -m annotation_layout plan INPUT --out out/plan.json`;
- A treats `out/plan.json` as a proposal file; it may persist it beside the
  page evidence with the same SHA binding;
- A returns to K a capability/probe record and, optionally, a post-apply
  snapshot so K can re-verify; K's `verify INPUT --plan PLAN` is read-only.
- Versioning: K's `schema` is `annotation-layout/v1`; a future incompatible
  change bumps the schema and must be coordinated.  A should ignore unknown
  optional fields rather than guessing semantics.

## 8. Non-guarantees

K does **not** guarantee: persistence of any host write, free-text or net-label
movement, attribute rotation/alignment, glyph-level rendering, visual
acceptance, electrical correctness, or a whole-board speedup.  K's benchmark is
offline solver work only.  A's own apply/save/reopen/export/connectivity evidence
is still required before any delivery claim.

## 9. Readiness package (probe → adapter → apply acceptance)

The companion documents make the readiness path executable by A without changing
K or its allowed paths:

- [`integration-probe-quickstart.md`](integration-probe-quickstart.md) — short, executable version of the probe plan for A;\n- [`integration-host-probe.md`](integration-host-probe.md) — disposable-copy
  probe plan for attribute/free-text/net-label movement, save/reopen, export,
  ID stability and the capability-record format;
- [`integration-adapter-contract.md`](integration-adapter-contract.md) —
  field-by-field snapshot → `annotation-layout/v1` mapping, text classification,
  flat-segment handling, checker context, hashing and validation gate;
- [`integration-apply-checklist.md`](integration-apply-checklist.md) — plan
  acceptance gate, dry run on a copy, save/reopen/export/checker/connectivity
  evidence, accept/reject/rollback and evidence record;
- [`integration-capability-record.example.json`](integration-capability-record.example.json)
  — format example only (not probe evidence).

A should complete the probe record before applying anything; K continues to
produce `only_planned` proposals and never treats a plan as a write
authorization.

