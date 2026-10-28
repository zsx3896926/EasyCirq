# Integration readiness 2 — snapshot to `annotation-layout/v1` adapter contract

Status: **contract for the executor task (A)**.  K reads this format; K does not
call EDA or build A's live adapter.  The frozen photo-led path
(`python -m annotation_layout convert`) only serves regression fixtures; real
work must be adapted from A's own snapshot.

Inputs accepted by K are versioned (`annotation-layout/v1`), strict, and
SHA-bound.  The authoritative field list and validation rules live in
`contract.md`; this document is the field-by-field mapping A must implement and
the failure modes it must not paper over.

## 1. Freeze evidence before adapting

For one page, capture and keep as files (SHA-256 each):

1. page identity: project name, page ID, page name, host version;
2. `sch list --include-bbox --include-pins --include-wires
   --include-page-primitives` (or the host's equivalent) — components, pins,
   wires, page primitives;
3. official SVG/PNG export of the page (the SVG is also the text-bbox source);
4. `sch sheet-geometry --from-svg` (page/inner box, title block);
5. checker output before planning;
6. connectivity/netlist readback before planning;
7. any host-specific attribute/designator geometry read.

Record the page snapshot hash and the read time.  Do not mix files from different
reads; K rejects stale source hashes (line-ending-normalized) and stale
junction/page evidence.

## 2. Object mapping

### 2.1 Page, units, coordinate system

| v1 field | source | rules |
|---|---|---|
| `units.name` | adapter constant | must be `schematic_raw`; never infer pixels/inches |
| `units.raw_per_mm` | project convention | e.g. photo-led: `10 raw = 0.1 inch = 2.54 mm` → `3.937007874015748`; must be positive |
| `coordinate_system` | measured convention | `y_axis=up`, `svg_y_axis=down`, nonempty declared transform; measured SVG text bbox is flipped **once** (photo-led adapter uses y negation) |
| `page.bbox` | sheet geometry | physical page rectangle |
| `page.usable_bbox` | sheet inner frame | drawing area; must be inside page bbox |
| `page.title_block` | official SVG vectors | actual title-block rectangle, not a guessed margin |
| `page.keepouts[]` | declared hard areas | title block and any project keep-outs; hard=true only for real barriers |
| `page.zones[]` | module/functional frames | id/name/bbox; membership used for free-text zone containment |

### 2.2 Components

- Use only real parts (`componentType=part`); include the sheet/title-block object
  only if it is a movable object (normally no).
- `id` = stable primitive ID.
- `bbox` = the host-read symbol body rectangle (real bounding box).  Do not
  synthesize a body from the symbol name, pin count or a text heuristic.
- `designator` = actual reference designator; if missing, leave null and expect
  K to refuse owning designator/value text to that component.
- `zone_id` = functional zone containing the component (or null).  Do not invent a
  zone membership.

### 2.3 Texts (this is the critical classification)

Every visible text must be either a fixed text or a movable annotation; the two
lists must not overlap.  Classification:

| v1 | host evidence | movable? |
|---|---|---|
| `designator` | attribute text owned by a component whose content equals that component's designator | only if host `attribute_translate=supported`/`unverified` |
| `value` | attribute text owned by a component whose content differs from the designator | same |
| `free_text` / purpose | page-level text primitive (not linked to a net/symbol) | only with probed `free_text_translate`; historical default `unverified` |
| `net_label` / `wire_name` | text linked to a wire/label anchor; has `net` and `anchor_id`, `anchored=true` | only if host `net_label_detach=supported`; otherwise fixed |
| `netflag` | text belongs to a global net flag symbol | fixed |
| `pin_name`, `pin_number` | symbol-internal pin text | fixed |
| `zone_title` | title of a module frame | fixed |
| `title_block`, `border` | title-block/border text | fixed |
| `unknown` | cannot prove ownership/kind | fixed, and K may report `owner_unknown`/incomplete coverage |

Field requirements:

- `id` stable and unique; `bbox` measured if possible (`bbox_source=measured_svg`
  from the official SVG; `measured_api` only if the host exposes an equivalent
  measured rectangle; otherwise `estimated` and K cannot claim `plan_verified`).
- `content` exactly the rendered string; `content_sha256` is derived by K.
- `owner` for designator/value must be the owning component; free text may be
  owned by a zone/page; net labels use `anchor_id` + `net`.
- `current.rotation_deg`, `align`, `font_size`: only fill when actually exposed.
  Use `null` + `rotation_source/align/font_source=unknown` otherwise.  **Never
  default rotation/alignment/font to 0.**
- `capability.translate`: `supported`/`unverified`/`unsupported` per probe and
  role; `rotate`, `resize`, `content_change`, `net_change` remain
  `fixed`/`forbidden`.
- `constraints`: declared per annotation (zone containment, allowed directions,
  max displacement, grid, owner distance, priority).  These are planning policy;
  do not silently use values not declared in the input.

Costs of wrong classification:

- a movable net label without anchor separation breaks connectivity (forbidden);
- a guessed owner lets K move an unrelated text;
- a guessed rotation makes the bbox/pose wrong;
- a guessed bbox turns a visual fix into a false `plan_verified`.

### 2.4 Wires

- Each wire object: stable `id`, ordered `points`, optional `net`, optional
  `primitive_id`.
- `rawEncoding=flat-segments` must be decoded as **independent segments**; never
  feed the flat list as a polyline (the existing adapter has a dedicated
  `flat_segments()` for this).  K judges every segment independently.
- Zero-length/degenerate wires: preserve the IR only if the host uses them for
  connections; exclude them from drawable geometry as the existing adapter does.
- Do not merge, rename, re-route or reorder wires to make a plan look clean.

## 3. Checker context passthrough

K's `verify` rebuilds the existing checker input and calls
`sch_layout_check.analyze` unchanged.  A must supply, where available:

```json
"checker_context": {
  "policy": { ... from the adapter/project policy ... },
  "title_block_owned": [ ... ],
  "label_anchors": [ ... ],
  "net_flags": [ ... ],
  "attachment_points": [ ... ],
  "module_frames": [ ... ],
  "no_junction_crossings": [ ... ],
  "junction_evidence": { "source": "...", "page_id": "...", "snapshot_sha256": "..." },
  "coverage": { ... },
  "expected_counts": { "components": 19, "texts": 136, "wires": 98 },
  "page_id": "...",
  "snapshot_sha256": "..."
}
```

Rules:

- `junction_evidence` must match the page ID and snapshot hash; stale evidence is
  rejected.
- `expected_counts` must equal the actual object counts; a mismatch is a
  discovery failure, not a warning to ignore.
- If the checker cannot be run, say so; K will record checker availability rather
  than assume pass.
- `coverage` should state complete/partial/absent for components, texts, wires,
  attachments, label anchors, module frames, title block.  Partial coverage means
  no visual/complete claim.

## 4. Host capabilities and uncertainty

```json
"host": {
  "capabilities": {
    "attribute_translate": "supported|unverified|unsupported",
    "free_text_translate": "supported|unverified|unsupported",
    "net_label_detach": "supported|unverified|unsupported",
    "attribute_rotate": "supported|unverified|unsupported"
  },
  "capability_source": "onsite_probe_<date>_<page_id>",
  "execution": "not_executed"
}
```

- Fill from `integration-host-probe.md` records; never from historical notes.
- `execution=not_executed` means K did not execute writes; it is not a probe
  result.
- `uncertainty`: state whether bboxes are measured, font metrics known, symbol
  outlines approximate; notes must include the actual limitations.
- If free text cannot be measured, mark it `estimated` and expect
  `candidate_needs_visual_review`; do not fabricate geometry.

## 5. Provenance and hashing

- `project.snapshot_sha256` = the page snapshot hash used for all reads.
- `source.files[]` = the evidence files consumed, with SHA-256 over
  LF-normalized bytes (K normalizes line endings so Windows CRLF and Linux LF
  checkouts agree).
- K's canonical input hash binds the whole document (`input.canonical_sha256`);
  the plan records it and `verify` rejects a plan whose input hash no longer
  matches.

## 6. Validation gate before planning

A produces `input.json` and runs:

```bash
cd design-hardware/scripts
python -m annotation_layout validate <input.json>
```

Accept only if:

- exit code 0 and `status=valid`;
- component/text/wire counts match the frozen read and `coverage` is complete for
  the objects K must judge;
- no source hash/checker evidence is stale;
- movable annotations are exactly the objects with probed capability, not more;
- no guessed rotation/align/font/owner/bbox remains unflagged.

If validation fails, fix the adapter/evidence; do not re-label objects to make
it pass.

## 7. Common adapter mistakes (all rejected or downgraded by K)

- treating the flat-segments wire list as a polyline;
- moving a net label without anchor separation;
- assigning a value text to the wrong component or guessing its owner;
- estimating a bbox but marking it `measured_svg`;
- setting unknown rotation/alignment/font to 0;
- using the page outer box as the usable inner frame;
- mixing SVG y-sign conventions, or flipping a bbox twice;
- leaving out subtle texts (pin names, net flags) so a planned move lands on
  them;
- stale page/hash evidence or a junction report from another save;
- modifying content/net to clear a conflict (K forbids it; A must not do it
  either).

## 8. Outputs A should keep with the snapshot

- `input.json` and its canonical SHA;
- the source evidence files and their SHA-256 list;
- `plan.json` + report + analysis SVGs from K (`analysis_not_official_export`);
- capability record from `integration-host-probe.md`;
- checker before/after findings from the unchanged checker.

These form the audit trail for any later apply decision.
