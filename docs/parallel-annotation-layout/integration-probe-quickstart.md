# Integration probe quickstart (for A)

Short execution version of [`integration-host-probe.md`](integration-host-probe.md).
Run it once on a **disposable copy** of the page, then return the capability
record and evidence.  K did not call EDA and none of this is executed by K.

## 0. Prepare (one page, one copy)

1. Copy the project/page; confirm no other writer is attached; export a project
   backup.
2. Record: host name + version, project name, page ID, page snapshot SHA-256.
3. Capture baseline evidence into `probe-before/`:
   - `sch list --include-bbox --include-pins --include-wires --include-page-primitives`
   - `sch sheet-geometry --from-svg`
   - official SVG/PNG export
   - `sch check` output and connectivity/netlist readback
4. Pick four objects and record their IDs/content/bbox/anchor:
   one designator, one value, one free text, one net-label text.
5. Safety: probe only on the copy; stop on any ID/content/net/anchor change.

## 1. Run the probes

| id | action | required readback | `supported` means |
|---|---|---|---|
| P0 | read twice; save + reopen with **no edits**; read again | IDs, counts, page hash, export identity | all reads agree |
| P1 | translate the designator and the value by **+5 raw x** (two separate probes) | immediate read, save + reopen, official SVG bbox | pose persisted; content/net/owner/rotation/font unchanged; IDs stable; record tolerance |
| P2 | translate the free text by **+5 raw y** | same as P1 | text persists after reopen and renders at the new place; historically this failed, so prove it |
| P3 | move **only** the net-label text by +5 raw x; leave its anchor | anchor position, net, `sch read`/checker, connectivity, export | anchor/net unchanged and text persists; otherwise `unsupported` |
| P5 | after each save/reopen, compare whole-page IDs and expected counts | before/after lists | no ID drift, no object added/lost |
| P6 | compare host/API bbox vs official-SVG text bbox for each probe object (and one pin name) | raw deltas | record the measurement source and deltas; do not guess a bbox |
| P7 | revert the copy and compare with the pre-probe snapshot | restored page ID/hash | rollback works |

Optional P4 (attribute rotation/alignment): only if A wants rotated poses later.
K's current contract plans **translation only**, so it must stay untouched.

Result rules:

- `supported`: persisted through save+reopen, export/readback agree, IDs/content/
  net/anchor stable, tolerance recorded.
- `unverified`: only an in-memory change was observed (e.g. no reopen possible).
- `unsupported`: not persistent, changed content/net/anchor/IDs, or host cannot
  express it.
- Never upgrade a result from historical notes or a single in-memory read.

## 2. Fill the capability record

Copy
[`integration-capability-record.example.json`](integration-capability-record.example.json)
and replace every value with the probe evidence.  Minimum:

```json
{
  "schema": "annotation-layout-host-probe/v1",
  "project": {"name": "...", "page_id": "...", "snapshot_sha256": "..."},
  "host": {"name": "EasyEDA Pro", "version": "..."},
  "probed_at": "...",
  "probes": [
    {"id": "P1-attribute-translate", "object_id": "...", "role": "value",
     "action": {"dx": 5, "dy": 0}, "before": {"bbox": []},
     "after_immediate": {"bbox": []}, "after_reopen": {"bbox": []},
     "ids_stable": true, "result": "supported", "tolerance_raw": 0.5,
     "notes": "..."}
  ],
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

Then feed the `capabilities` block into the K input:

```json
"host": {
  "capabilities": { "...": "..." },
  "capability_source": "onsite_probe_<date>_<page_id>",
  "execution": "not_executed"
}
```

`execution=not_executed` means K has not applied writes; it is not a probe
result.  Any object with `unsupported` remains fixed in K plans.

## 3. Validate the adapted input

```bash
cd design-hardware/scripts
python -m annotation_layout validate <input.json>
```

Expected: exit 0, `status=valid`, object counts match the frozen read, no stale
source/checker evidence, no guessed rotation/align/font/bbox.  If validation
fails, fix the adapter/evidence — do not relabel objects to pass.

## 4. Return this bundle to K

```text
probe-<page_id>-<date>/
  capability-record.json          (+ SHA-256)
  input.json                      (+ canonical_sha256)
  probe-before/                   baseline list/sheet/check/connectivity/export
  probe-after/                    after save+reopen/read/export/check/connectivity
  probe-log.md                    one short line per probe: pass/fail/tolerance
```

Return message should state:

- host/version, page ID, snapshot hash, probe date/time;
- per probe: result and failure reason (if any);
- `capability_source` string used in the input;
- absolute paths of the four evidence groups above;
- any `unsupported` object that K must keep fixed;
- explicit NOT RUN items (e.g. production apply, whole-board export, batch).

## 5. Stop conditions

Roll back the copy and report a failed probe if any of these occurs:

- primitive ID changes, object count changes, page identity changes;
- content, net, anchor, owner, rotation/alignment/font changes unexpectedly;
- the pose does not survive save + reopen;
- a new checker/connectivity issue appears;
- a capability was probed on a different page/version than the declared snapshot.

Do not probe the production page, do not edit content/net to "make it fit", and
do not weaken checker thresholds or tolerances after a failure.

