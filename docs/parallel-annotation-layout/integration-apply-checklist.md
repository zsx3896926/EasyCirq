# Integration readiness 3 — apply / readback acceptance checklist

Status: **checklist for the executor task (A)**.  K never applies a plan, saves,
exports or reads connectivity.  This document defines the minimum evidence A must
collect before calling an apply successful, and when to abort/roll back.

## 0. Roles

| actor | owns |
|---|---|
| K (`annotation_layout`) | offline plan, independent geometric recheck, checker bridge, analysis overlays |
| A | host read/apply/save/reopen/export/connectivity, capability probe, acceptance evidence |
| user | approves a specific apply on a specific page copy; K/A evidence is not an approval |

A K plan is **never a write authorization**.  A stale plan or an unprobed
capability must stop the batch.

## 1. Plan acceptance gate (before any write)

Reject and re-plan unless all are true:

- [ ] `plan.status == "planned_clear"` and `plan.noop` is acceptable for the task;
- [ ] `plan.verification.status == "plan_verified"`;
- [ ] `plan.input.canonical_sha256` equals the adapter input hash for the current
      snapshot; `project.page_id` / `snapshot_sha256` match the live read;
- [ ] every `changes[].content_sha256`, owner and `before.bbox` can be re-read and
      matches; `protected` fields all say unchanged;
- [ ] `host.capabilities` in the plan matches the onsite capability record
      (`integration-host-probe.md`); every change with
      `host_probe_required=true` has a probed capability;
- [ ] the plan's `verification.checker.before` blocking findings match the current
      checker output (code + object IDs);
- [ ] no involved annotation has `bbox_source=estimated` or an unresolved
      `needs_geometry`/`unknown` state;
- [ ] analysis SVGs are treated as human inspection only
      (`analysis_not_official_export`), never as evidence.

If any item fails: stop, re-read, re-plan.  Do not hand-edit `plan.json` or move
objects manually "just this once".

## 2. Dry run on a disposable copy

Use a copy unless the user explicitly authorized the live page.  Apply one page
at a time, not a whole project.

For each change:

- [ ] target primitive ID and content match the plan (re-read immediately before
      the write);
- [ ] apply only the declared translation (`delta.dx`, `delta.dy`);
- [ ] do not change content, net, anchor, rotation, font, alignment, component,
      wire, page or instance identity;
- [ ] re-read the object; compare actual bbox/pose with `after.bbox` within the
      declared tolerance (record the tolerance, e.g. raw units);
- [ ] verify owner/zone/read-order membership did not change;
- [ ] verify no new object was created/destroyed and no ID drifted.

If any step fails: stop the batch, restore the copy, record the failing object and
the mismatch.  If it is a capability/persistence failure, mark that capability
`unsupported` for the next input.

## 3. Save, reopen, readback

- [ ] save the page/project;
- [ ] close/reopen the project or reload the page from disk;
- [ ] re-read the whole page with the same options as the baseline;
- [ ] confirm every applied pose persisted and remains within tolerance;
- [ ] confirm primitive IDs, content, net, owner, rotation/alignment/font are
      unchanged;
- [ ] compare counts with the baseline; no unexpected objects appeared/disappeared;
- [ ] export the official SVG/PNG; record SHA-256 and page identity; measure the
      rendered text positions for the changed annotations;
- [ ] visually inspect the official export for glyph/font issues that a bbox
      check cannot prove (human step; K did not see the rendering).

If a free-text move did not survive reopen, mark `free_text_translate=unsupported`
and do not claim the plan was applied.

## 4. Independent checker and electrical readback

- [ ] run the existing `sch_layout_check.py` on a fresh snapshot of the applied
      page; compare blocking findings with the planned after-state and with the
      plan's `verification.checker.after` (no new blocking conflict);
- [ ] run the host's own checker/lint, recording its exact scope;
- [ ] re-read connectivity/netlist and diff it against the baseline: same nets,
      same pin↔net intent, no new junction/short/open; K's
      `electrical_assertion` is structural only and is not this proof;
- [ ] confirm no net label/anchors were detached or renamed;
- [ ] if the host has a design-rule/score report, record change and scope (K makes
      no DRC or visual claim).

Any connectivity change or new blocking checker finding means the apply failed,
even if the text looks better.

## 5. Accept / reject / rollback

**Accept** only when §1–§4 are all recorded, the page identity is unchanged, and
the user accepts the result.  Record:

- plan input/plan hashes, capability record, before/after snapshot hashes;
- official export SHA and checker before/after;
- connectivity diff summary;
- any NOT RUN item.

**Reject/rollback** immediately and restore from the backup when:

- ID drift, content/net change, anchor separation or page identity change;
- a pose did not persist or exceeds tolerance;
- a new hard checker/connectivity issue appears;
- a capability was used that was not supported/unverified as declared.

After rollback, re-read and prove the restored page matches the pre-apply
snapshot; report the failure as evidence, not as a reason to weaken thresholds.

## 6. Evidence record template

Keep one directory per apply attempt:

```text
apply-<page_id>-<timestamp>/
  capability-record.json        # from integration-host-probe.md
  input-before.json             # adapter input + canonical hash
  plan.json / report.md / before.svg / after.svg
  snapshot-before.json          # sch list/sheet/checker/connectivity readback
  apply-log.json                # per change: id, before, after, tolerance, result
  snapshot-after.json
  export-before.svg             # official
  export-after.svg              # official
  connectivity-before.json
  connectivity-after.json
  acceptance.json               # checklist results, NOT RUN list, final decision
```

`acceptance.json` minimum:

```json
{
  "schema": "annotation-layout-apply-acceptance/v1",
  "page_id": "...",
  "plan_input_sha256": "...",
  "plan_sha256": "...",
  "capability_source": "...",
  "checks": {
    "plan_gate": "pass",
    "dry_run": "pass",
    "save_reopen": "pass",
    "checker": "pass",
    "connectivity": "pass",
    "official_export": "pass",
    "human_visual": "reviewed | NOT RUN"
  },
  "changes": [{"id": "...", "applied": true, "tolerance_raw": 0.5}],
  "not_run": ["..."],
  "decision": "accepted | rejected | rolled_back"
}
```

A pass here is host/apply evidence; it is not a substitute for the user's product
acceptance, and K's benchmark is not a whole-board speed claim.

## 7. Explicitly NOT RUN by K

- EDA apply/write, save/reopen, official export, DRC/score, connectivity readback;
- visual/raster inspection of the analysis SVGs;
- host capability probes;
- any claim about glyph rendering, netlist correctness or manufacturing readiness.

Those are A/user evidence and must be recorded separately.
