# Integration readiness 1 — host capability probe plan

Status: **instructions for the executor task (A)**, produced by the offline
annotation-layout task K.  K has **not** called EDA and has **not** executed any
of these probes.  Nothing in this document is evidence that a host capability
works; it is the minimum probe plan A must run before applying a planned pose.
Short execution version for A: [`integration-probe-quickstart.md`](integration-probe-quickstart.md).  See `integration-proposal.md` for the boundary and consumer contract.

## 1. Purpose

K's planner can only move annotation text when the input declares both the
per-object capability **and** the host capability.  The plan currently ships with
historical/offline declarations:

```json
{
  "attribute_translate": "supported",
  "free_text_translate": "unverified",
  "net_label_detach": "unsupported",
  "attribute_rotate": "unsupported",
  "capability_source": "historical_docs_requires_onsite_probe"
}
```

These are **not** probe results.  A must replace them with onsite evidence on a
disposable copy before batch-applying anything.  A free-text move that looks
successful in memory but disappears after save/reopen is `unsupported`, not
`unverified` or `supported`.

## 2. Preconditions and safety

| item | requirement |
|---|---|
| target | a **disposable copy** of the project; never probe the production page |
| writer exclusivity | no other session writing the same project copy; check the audit/lease state first |
| baseline evidence | save page id, snapshot SHA-256, host name/version, checker output, official SVG/PNG, `sch list` readback, connectivity readback |
| backup | project export (e.g. `.epro2`) outside the EDA working tree before any write |
| grid | use the declared drawing grid (for photo-led: 5 raw); record the exact offset values used |
| abort | any ID change, content/net change, unexpected object count, stale page/hash, or save failure → stop, restore the copy, report the probe as failed |
| no claim | a successful in-memory move is **not** persistence evidence; only save + reopen + readback + export count |

All probe writes happen on the copy.  K remains read-only and is not involved in
the host operation.

## 3. Probe matrix

Run at least P0–P4 and P7.  P5/P6 are required if the plan will move more than a
few texts.  Record every probe in the capability record (§5).

### P0 — readback stability (no edit)

1. Read the page twice with the same options; compare page ID, snapshot SHA,
   component/text/wire counts and primitive IDs.
2. Save (no edits), reopen, read again; compare the same set.
3. Export SVG/PNG; record SHA-256 and page identity.

Pass: all reads agree; IDs and counts stable; export page matches.  Failure means
no later probe can be trusted.

### P1 — attribute translation (designator and value)

1. Pick one designator and one value whose current bbox/anchor/rotation are
   actually exposed by the host read.
2. Record `before`: primitive ID, content, owner, anchor, bbox, rotation, font.
3. Translate by one or two on-grid offsets (e.g. +5 raw x, then −5 raw y).
4. Immediately re-read the object (in-memory state).
5. Save, reopen, re-read; export the official SVG and measure the text bbox.
6. Compare `after_reopen` with the intended pose and with the exported glyph bbox.

`supported` only if: pose changed by the requested offset, content/net/owner and
rotation/font are unchanged, the pose survives save/reopen, the exported text
renders at the new place, and primitive IDs are stable.  Record the observed
position tolerance in raw units.  If any condition fails, record
`unsupported`/`unverified` and the failure reason.

### P2 — free-text translation (historically unreliable)

Same cycle as P1 with a free text (not a net label, not a symbol attribute):

- create or choose an existing free text, record content/owner (zone/page),
  anchor/align/rotation/font if exposed;
- translate it, read back in memory;
- **save + reopen + read**, export SVG, compare glyph position;
- additionally check the text still exists as the same object and is not
  re-created with a new ID.

Historical project notes say free-text moves were not persistent.  That is a
warning, not a result.  A must probe it on the current host version and record
`free_text_translate` as `supported`, `unverified` (in-memory only) or
`unsupported` (lost on reopen), with the exact failure.

### P3 — net-label text vs electrical anchor separation

1. Pick a net-label text with its anchor and net.
2. Read the connection/checker/export evidence for that net.
3. Move **only the text**, if the host exposes text position separately from the
   anchor; keep the anchor at its original point.
4. Read back: anchor position, net name, `sch read`/checker result, exported SVG.
5. Save + reopen + read + export again.

`supported` only if the anchor/net connection is provably unchanged and the text
pose persists.  If the host moves the anchor with the text, changes the net, or
loses the connection, record `unsupported`; K will then never propose moving that
net-label text.  Do not "fix" a break by re-attaching the anchor.

### P4 — attribute rotation/alignment/font (optional, only if future poses need it)

K's first phase plans **translation only**, so this probe is optional.  If A
later wants rotated/realigned poses, probe rotation and alignment with the same
save/reopen/export cycle and record `attribute_rotate` / `attribute_align`.
K currently requires rotation/align/font to remain untouched; do not claim a
rotated pose as supported under the existing plan contract.

### P5 — identity and property stability

For each probe object and for the whole page:

- primitive IDs, designator, content, owner, net, anchors before/after
  save/reopen;
- object counts (components/texts/wires) vs the declared `expected_counts`;
- title-block/page identity unchanged.

Any drift → `ids_stable=false`; reject batch application for that page and
re-plan.

### P6 — text bbox measurement fidelity

Compare the host/API bbox with the official-SVG measured bbox for a sample of
texts (at least designator, value, free text, net label, pin name/number).
Record:

- source (`measured_svg` / `measured_api` / `estimated`),
- deltas in raw units and whether they exceed the planner's declared tolerances,
- whether the host exposes rotation/alignment/font at all.

K only treats measured bboxes as evidence; if A cannot measure the rendered text
bbox, the input must use `bbox_source=estimated` and K will return
`candidate_needs_visual_review` rather than `plan_verified`.

### P7 — revert / rollback

Confirm on the copy that the applied probes can be undone (undo history, project
restore, or copy replacement) and that the restored page matches the pre-probe
evidence.  Record the method and the restored snapshot SHA.

## 4. Result vocabulary

| result | meaning |
|---|---|
| `supported` | requested pose persisted through save+reopen, readback/export agree, IDs/content/net stable, tolerance recorded |
| `unverified` | change observed in memory but persistence/export could not be proven (e.g. no reopen available) |
| `unsupported` | not persistent, changes content/net/anchor/IDs, or the host cannot express the change |

Never upgrade `unsupported`/`unverified` to `supported` based on historical notes,
another version, or a single in-memory read.

## 5. Capability record format

A should keep one record per page/version and feed the `capabilities` block into
K's input `host` object.  Example:
`integration-capability-record.example.json`.  Minimum fields:

```json
{
  "schema": "annotation-layout-host-probe/v1",
  "project": {"name": "...", "page_id": "...", "snapshot_sha256": "..."},
  "host": {"name": "EasyEDA Pro", "version": "..."},
  "probed_at": "2026-10-28T...",
  "operator": "...",
  "probes": [
    {
      "id": "P1-attribute-translate",
      "object_id": "...",
      "role": "value",
      "action": {"dx": 5, "dy": 0},
      "before": {"bbox": [0, 0, 0, 0], "anchor": [0, 0], "content_sha256": "..."},
      "after_immediate": {"bbox": [0, 0, 0, 0]},
      "after_reopen": {"bbox": [0, 0, 0, 0]},
      "export_svg_sha256": "...",
      "ids_stable": true,
      "result": "supported",
      "tolerance_raw": 0.5,
      "notes": "..."
    }
  ],
  "capabilities": {
    "attribute_translate": "supported",
    "free_text_translate": "unsupported",
    "net_label_detach": "unsupported",
    "attribute_rotate": "unverified"
  },
  "capability_source": "onsite_probe_2026-10-28_<page_id>",
  "not_run": ["batch apply", "whole-board export", "connectivity regression on production"]
}
```

K's input mapping:

```json
"host": {
  "capabilities": { "...": "supported | unverified | unsupported" },
  "capability_source": "onsite_probe_<date>_<page_id>",
  "execution": "not_executed"
}
```

`execution=not_executed` means K has not executed host writes; it does not
describe the probe.  The probe record is separate evidence and must be stored
beside the page snapshot.

## 6. Deliverables back to K

1. the capability record above, with the probe commands/tool actions recorded;
2. the before/after snapshot files and their SHA-256 values;
3. official SVG/PNG and checker/connectivity outputs at each stage;
4. any object whose capability is `unsupported`/`unverified`, so K can keep it
   fixed and report `host_capability_unsupported` instead of silently moving it.

Until these exist, K plans remain `only_planned`; no batch apply is authorized.


