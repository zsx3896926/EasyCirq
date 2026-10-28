# annotation-layout contract (v1)

Status: **implementation contract** for the offline annotation-pose planner.
This document is the source of truth for the input schema, the CLI, the status
vocabulary and the internal module interfaces. It does not claim any host
(EasyEDA) execution.

- task: 智构 parallel task K — batch annotation avoidance / local relayout planner
- branch: `feat/parallel-annotation-layout`
- base main SHA: `9a951edc21481dc3ae91460acc11aa3e08a7be8a` (2026-10-27)
- package: `easycirq/scripts/annotation_layout/` (standalone, no deps)
- delivered paths: `easycirq/scripts/annotation_layout/`,
  `tests/annotation_layout/`, `benchmarks/annotation-layout/`,
  `docs/parallel-annotation-layout/`

No EDA call, no network, no host window/state change. Inputs are read-only
files; every output goes outside the input (`--out`, `--out-dir`).

## 1. Scope

Movable annotation roles (only when the input declares the capability):

| role | meaning | default capability |
|---|---|---|
| `designator` | reference designator text (R3, U1) | `supported` (historical host support; not probed here) |
| `value` | value/part-number text (10kΩ, LM358P) | `supported` (historical host support; not probed here) |
| `free_text` | ordinary note / purpose text | `unverified` (historical free-text moves were not persistent) |
| `purpose_text` | alias of `free_text` kept for reports | `unverified` |
| `net_label` / `wire_name` | net-name text with an electrical anchor | `unsupported` for text↔anchor separation unless explicitly declared supported |

Fixed by default: net-label electrical anchors, netflag symbols, symbol bodies,
pin names/numbers, symbol graphic text, wires, junctions, zone frames, title
block, border text, other pages, instance identity, all `not_movable` fields.

Forbidden ways to clear a conflict (never proposed, never counted as a fix):
font shrink, hiding/deleting text, changing content/value/net, floating pins, a
new page, moving components, crossing another functional zone, changing checker
thresholds.

Out of scope for phase 1: arbitrary font rendering, whole-page component
placement, wire rerouting, image OCR, visual model services, host write scripts.

## 2. Input document

`annotation-layout/v1` JSON object. UTF-8. Unknown keys are **rejected** (strict)
so a typo cannot silently weaken the constraints.

```json
{
  "schema": "annotation-layout/v1",
  "project": {
    "name": "photo-led-5v-20261026",
    "page_id": "cd008f919db36eba",
    "page_name": "P1",
    "snapshot_sha256": "6bcf...8184"
  },
  "source": {
    "kind": "frozen_fixture",
    "adapter": "annotation_layout.convert/photo-led-v14",
    "source_commit": "9a951edc21481dc3ae91460acc11aa3e08a7be8a",
    "created": "2026-10-27",
    "notes": "trimmed official EasyEDA 4.1.78 SVG text measurement + sch list",
    "files": [{"path": "tests/fixtures/photo-led-v14/layout.json", "sha256": "..."}]
  },
  "units": {
    "name": "schematic_raw",
    "raw_per_mm": 3.937007874015748,
    "description": "schematic raw units; 10 raw = 0.1 inch = 2.54 mm"
  },
  "coordinate_system": {
    "name": "easyeda-schematic-raw-y-up",
    "y_axis": "up",
    "svg_y_axis": "down",
    "transform": "source measured SVG text bbox flips once by negating y (rendered svg_y = -raw_y); analysis overlays use screen_y = page_height - raw_y"
  },
  "page": {
    "bbox": [0, 0, 1170, 825],
    "usable_bbox": [10, 10, 1160, 815],
    "title_block": {"id": "titleBlock", "bbox": [460, 10, 1160, 190], "hard": true},
    "keepouts": [{"id": "titleBlock", "bbox": [460, 10, 1160, 190], "hard": true, "reason": "title block"}],
    "zones": [{"id": "zone-1", "name": "1 light sensor", "bbox": [30, 40, 455, 260], "hard": false, "source": "module_frame"}]
  },
  "components": [{"id": "417202d804679ca0", "bbox": [289.5, 154.5, 370.5, 205.5], "designator": "U1", "zone_id": "zone-1"}],
  "wires": [{"id": "1fa3e4d8816a3e4a", "points": [[145, 750], [145, 760], [320, 760]], "net": "", "primitive_id": "1fa3e4d8816a3e4a"}],
  "fixed_texts": [
    {"id": "c332e360692d0efa", "bbox": [580, 715, 589.25, 725], "kind": "pin_name", "content": "J1", "owner_id": "9f05264307912dc7", "measurement": "bbox"}
  ],
  "movable_annotations": [
    {
      "id": "8bd5a6b179fa7148",
      "role": "value",
      "content": "10kΩ",
      "kind": "attribute",
      "field": "attribute",
      "current": {
        "bbox": [290, 348, 311.107666015625, 358],
        "anchor": null,
        "anchor_source": "unknown",
        "align": "unknown",
        "rotation_deg": null,
        "rotation_source": "unknown",
        "font_size": null,
        "font_source": "unknown"
      },
      "bbox_source": "measured_svg",
      "owner": {"kind": "component", "id": "4c3b66d17e7f4875", "requirement": "keep_near"},
      "net": null,
      "anchor_id": null,
      "capability": {
        "translate": "supported",
        "rotate": "fixed",
        "resize": "forbidden",
        "content_change": "forbidden",
        "net_change": "forbidden",
        "source": "historical_docs_not_probed"
      },
      "constraints": {
        "zone_id": "zone-3",
        "keep_in_zone": false,
        "allowed_directions": ["left", "right", "up", "down"],
        "max_displacement": 80,
        "grid": 5,
        "owner_max_distance": 250,
        "priority": 0
      }
    }
  ],
  "constraints": {
    "grid": 5,
    "min_text_text_gap": 2,
    "min_text_symbol_gap": 2,
    "min_text_wire_gap": 0,
    "min_text_wire_clearance": 5,
    "self_text_contact_tolerance": 1,
    "label_own_wire_edge_tolerance": 1,
    "max_candidates_per_annotation": 32,
    "max_total_candidates": 800,
    "max_search_states": 20000,
    "max_local_search_steps": 2000,
    "max_displacement": 80,
    "owner_max_distance": 250,
    "forbid_font_change": true,
    "forbid_content_change": true,
    "forbid_net_change": true,
    "forbid_component_move": true,
    "freeze_ids": [],
    "scope": "all",
    "scope_cluster_ids": []
  },
  "host": {
    "capabilities": {
      "attribute_translate": "supported",
      "free_text_translate": "unverified",
      "net_label_detach": "unsupported",
      "attribute_rotate": "unsupported"
    },
    "capability_source": "historical_docs_requires_onsite_probe",
    "execution": "not_executed"
  },
  "uncertainty": {
    "bbox_measured": true,
    "font_metrics_known": false,
    "symbol_outline_approximate": true,
    "notes": ["text bboxes measured from the official SVG; symbol bodies are bbox approximations"]
  },
  "checker_context": {
    "policy": {},
    "title_block_owned": [],
    "label_anchors": [],
    "net_flags": [],
    "attachment_points": [],
    "no_junction_crossings": [],
    "junction_evidence": null,
    "coverage": {},
    "expected_counts": {"components": 19, "texts": 136, "wires": 98}
  }
}
```

### 2.1 Validation rules (all violations are input_invalid / exit 2)

- `schema` exactly `annotation-layout/v1`; `project.snapshot_sha256` 64 hex chars;
  `units.name` known (`schematic_raw`), `raw_per_mm` finite > 0;
  `coordinate_system.y_axis` is `up` and `transform` non-empty (never inferred).
- No `NaN`/`Infinity`; `bool` is never accepted as a number; bbox has positive
  ordered extent; rotation finite; displacement/grid/caps finite and >= 0.
- All object IDs (components, wires, fixed texts, annotations, zones, keepouts,
  anchors) globally unique and non-empty; owners/zone/anchor references resolve.
- `fixed_texts` and `movable_annotations` are disjoint; a text ID appears once.
- capability enum: `supported | unverified | unsupported`; `rotate`/`resize`/
  content/net change are `fixed|forbidden` (a plan may never change them).
- `content` non-empty; `content_sha256` is derived, never trusted from input.
- `source.files[].sha256` 64 hex; when paths are relative they are resolved from
  the input file's directory, and a mismatch with the recorded hash is a stale
  input error. `checker_context.junction_evidence`, when present, must bind the
  same page ID + snapshot SHA as `project` (otherwise stale evidence).
- `freeze_ids` refer to existing annotations; `scope_cluster_ids` refer to
  annotation IDs when `scope=cluster`.
- `constraints.scope` in `all | cluster`; unknown value invalid.
- `title_block`/keepout/zones must be inside `page.bbox`.

The canonical input hash is `sha256(canonical_json(input))` with sorted keys,
UTF-8, `ensure_ascii=False`, no whitespace. `plan.input_sha256` binds it.

## 3. Coordinates and geometry policy

- Raw schematic units are y-up. The official SVG is y-down. The only allowed
  conversion is the declared affine `svg_y = page_height - raw_y`; no second
  transform of a bbox, no per-object refit.
- Measured bbox is authoritative for text extents (`measurement=bbox`). If only
  an estimated bbox exists (`measurement=estimated`/`bbox_source=estimated`),
  any conflict involving it is `unknown` until a measured bbox is supplied.
- `flat-segments` wire encodings are already split into independent segments;
  a list of points is treated as an ordered polyline only when the adapter says
  so. The planner evaluates every segment independently.
- Symbol bodies are bbox approximations: a bbox may cover legal whitespace or
  outgoing pin area. The planner stays conservative (never relaxes a checker
  rule); an annotation that only clears because of a symbol-bbox approximation
  is reported with `uncertainty=symbol_outline_approximate`.
- A text's own net-label wire may touch the text bbox only at its edge within
  `label_own_wire_edge_tolerance`; interior intrusion is still hard. Ownership
  never exempts a whole wire.
- All coordinates are judged exactly as supplied; grid snapping only ever
  produces candidate positions, never silently rounds the current pose.

## 4. Candidate contract (K1)

A candidate is one rigid translation of the measured bbox:
`pose = {dx, dy}` in raw units, `bbox_after = bbox_before + (dx, dy)`.
Rotation, font size, alignment, content and net are preserved; a candidate that
would need them changed is never generated. The displacement is on-grid and
limited by `constraints.max_displacement`/`constraints.grid`.

Ordering is deterministic: role order, then smaller displacement, then axis
order (right, left, up, down), then candidate index. Each candidate carries
`rank`, `displacement`, `bbox`, `rationale` (why this position is eligible) and
`capability` (host may need a probe). Candidate generation is bounded by
`max_candidates_per_annotation` and `max_total_candidates`; truncation is
recorded, never silent.

Role-specific rules:
- designator/value: keep owner association (`owner_max_distance`), prefer
  right/left/above/below near the original position, avoid the owner body,
  stay on the page, respect `keep_in_zone` and keepouts;
- free_text/purpose_text: stay in the declared zone unless explicitly allowed,
  keep away from all symbols/wires/text, keep readable at the fixed font;
- net_label/wire_name: only when `capability.translate=supported` **and** the
  host explicitly supports text/anchor separation; otherwise fixed/unsupported;
- fixed roles never produce candidates.

Candidates are generated from the measured bbox only; no font engine is used.

## 5. Solver contract (K2–K4)

1. **Hard conflict filter first:** text-text, text-symbol, text-wire,
   page/keepout/title/zone out-of-bounds, owner too far, undecidable ownership.
   Soft/readability findings never drive hard acceptance.
2. **Conflict graph:** movable annotations are nodes; an edge exists when two
   candidates' bboxes can interact. Connected components are solved as small
   independent clusters; annotations outside the selected cluster are frozen.
3. **Search:** deterministic bounded greedy initialization, then bounded local
   search/backtracking within a cluster. Every accepted state is validated as a
   whole; the solver never optimizes candidates independently and leaves a new
   conflict behind. Cost lexicographic: hard violations, unknown conflicts,
   moved annotations, total displacement, displacement of unrelated annotations,
   soft readability. `max_search_states`/`max_local_search_steps` are hard
   budgets; wall time is measured but never used to decide.
4. **Stability:** same input -> byte-identical plan. Re-planning an accepted
   plan is a no-op (fixpoint) unless the input changed. A no-op plan has zero
   changes and is `planned_clear` with `noop=true`.
5. **Failure taxonomy (per annotation / plan):** `no_candidates`,
   `all_candidates_rejected`, `budget_exhausted`, `geometry_uncertain`,
   `host_capability_unsupported`, `net_label_anchor_not_separable`. A search
   failure is never reported as mathematical infeasibility. With remaining hard
   conflicts the status is `partial`/`blocked`, never `plan_verified`.
6. **Minimal gap / next action:** each failure carries the blocking objects, the
   missing evidence (e.g. measured bbox) and a concrete suggestion (allow a
   larger zone, probe host capability, supply measured bbox) — never "shrink the
   font" or "change the net".

## 6. Verification contract (K5)

`verify` reconstructs all geometry from the input + plan changes (never from
solver internals), then:

1. runs an **independent brute-force recheck** of every applicable planner
   constraint (no spatial index, no incremental cache), and
2. when available, builds the existing checker's layout dictionary and calls
   `sch_layout_check.analyze()` unchanged (no threshold edits, no ignore list),
   keeping the original before and after findings.

Verification output keeps, for each finding, `before_present`, `after_present`,
`cause` (`resolved`, `pre_existing`, `introduced`, `out_of_scope`) and the
checker's own finding payload. `plan_verified` requires: no introduced hard
finding, no remaining hard finding attributable to movable annotations in scope,
independent recheck clean, checker ran (or is explicitly unavailable), and no
`estimated` geometry involved. Otherwise the plan is `partial`/`blocked`/
`candidate_needs_visual_review`. The checker's known exemptions (e.g. a symbol's
own attribute text skipped from wire checks) are recorded as limitations with
the independent recheck as extra evidence; thresholds are never changed.

Electrically, a plan only asserts the structural claim "this plan contains no
electrical change": same net names, anchors, wires, components, instance IDs,
content hashes. Real host readback, save/reopen, official export and connectivity
re-read are **NOT RUN**.

## 7. CLI contract

Invocation (one of):
- `cd easycirq/scripts && python -m annotation_layout ...`
- `PYTHONPATH=easycirq/scripts python -m annotation_layout ...`

Commands:

| command | purpose | exit 0 | exit 1 | exit 2 |
|---|---|---|---|---|
| `validate INPUT` | schema/geometry validation, counts, coverage | valid | — | invalid |
| `plan INPUT [--out PLAN] [--out-dir DIR]` | solve, write plan/report/SVG | `planned_clear` | `partial`/`blocked`/`needs_geometry` | invalid |
| `verify INPUT --plan PLAN [--out FILE] [--out-dir DIR]` | independent recheck of a plan | `plan_verified` | not verified | invalid/stale |
| `benchmark [--suite DIR] [--repeat N] [--out DIR]` | baseline vs improved, actual CLI-equivalent entry | ok | — | invalid |
| `convert --layout FILE [--list FILE] [--rendered FILE] [--sheet FILE] --out FILE` | frozen fixture -> v1 input | ok | — | invalid |
| `probe-check RECORD [--out HOST_BLOCK]` | validate an onsite host-probe capability record and derive the input `host` block (read-only, no host execution) | valid record | — | invalid record/IO |
| `probe-bind INPUT --record RECORD --out INPUT` | bind a valid capability record into a page/snapshot-matching v1 input (read-only apart from the output file) | ok | — | invalid record/mismatch/IO |
| `version` | tool/schema version JSON | ok | — | — |

Rules:
- stdout is **one pure JSON document**; diagnostics go to stderr; UTF-8 always
  (explicit encodings, `ensure_ascii=False`), deterministic ordering.
- `--out`/`--out-dir` writes are atomic (temp file + `os.replace`); a failed run
  never leaves a stale PASS file.
- Inputs are only opened for reading. Output paths must not equal an input path.
- No source file/URL contained in the input is executed or fetched.
- Every plan/report carries `schema`, `tool_version`, `input_sha256`, geometry
  accuracy/coordinate convention, candidate/search budgets, hard/unknown/moved
  counts, changed/unrelated/fixed violations, checker result and host NOT RUN.

Status vocabulary: `planned_clear`, `partial`, `blocked`, `needs_geometry`,
`input_invalid`; plan verification adds `plan_verified`,
`candidate_needs_visual_review`, `plan_not_verified`, `plan_rejected`.

## 8. Outputs

`plan --out-dir DIR` writes:
- `plan.json` — machine plan: status, changes (`id`, role, before/after pose and
  bbox, displacement, rationale, protected fields asserted unchanged), metrics,
  budgets, verification summary, host execution `not_executed`;
- `report.md` — short human report (status, counts, changes, verification,
  limitations/NOT RUN);
- `before.svg` / `after.svg` — analysis overlays, explicitly marked
  `analysis_not_official_export`, generated from geometry and checked for basic
  XML/rendering validity (no claim of visual acceptance).

## 9. Determinism and budgets

- JSON output uses sorted keys; arrays are ordered by stable IDs; no wall-clock
  values inside the plan hash.
- Search budgets are counts (candidates, checks, states, steps), never time.
- Same input + same tool version + same arguments => byte-identical plan.
- Timings appear only in benchmark reports with environment, seed, repeat count
  and median/range, and are never mixed into the plan decision.

## 10. Internal module map (contributor interface)

| module | owner | responsibility |
|---|---|---|
| `model.py` | lead | frozen dataclasses (`Rect`, `Input`, `Annotation`, `Candidate`, `Violation`, `Plan`), counters |
| `geometry.py` | lead | rect/segment math, y-up checks, grid, spatial index |
| `schema.py` | lead | parse + strict validation + canonical hash + status codes |
| `conflicts.py` | lead | fixed-geometry conflict checks and per-pair evaluation |
| `candidates.py` | solver-dev | K1 bounded candidate generation |
| `solver.py` | solver-dev | K2–K4 cluster search, local freeze, budgets, stability |
| `baseline.py` | solver-dev | per-annotation greedy + full recheck baseline for benchmarks |
| `planner.py` | lead | orchestration: input -> candidates -> solver -> plan -> verify |
| `verify.py` | verify-dev | independent brute-force verification + checker bridge |
| `svg_analysis.py` | verify-dev | before/after analysis SVGs |
| `report.py` | lead | JSON/Markdown report assembly |
| `convert.py` | fixtures-bench | frozen photo-led fixture -> v1 input |
| `benchmark.py` | fixtures-bench | same-domain baseline vs improved measurement |
| `cli.py` / `__main__.py` | lead | CLI dispatch, IO, exit codes |
| `probe_record.py` | lead | validate `annotation-layout-host-probe/v1` records and map them to the input host block |

Public functions other modules may rely on:

```python
# model.py
Rect(x0, y0, x1, y1)  # .width .height .center .translated(dx,dy) .inflated(g) .intersects(other)
                      # .contains_rect(other) .contains_point(p) .as_list()
Candidate(annotation_id, dx, dy, bbox, rank, rationale, capability)
Violation(code, severity, objects, detail, scope, annotation_ids)
SearchStats(candidates_generated, collision_checks, states, iterations, clusters,
            local_steps, budget_exhausted, budget_kind)

# geometry.py
segments_cross(a, b, c, d) -> bool            # proper crossing only
segment_enters_rect(a, b, rect) -> bool       # open-rectangle clipping
rect_segment_distance(rect, a, b) -> float
segment_distance(a, b, c, d) -> float
collinear_overlap(a, b, c, d) -> bool
SpatialIndex(cell_size)  # .add_rect(key, rect) .query_rect(rect) .add_segment(key,a,b)
                         # .query_segment(a,b) .query_rect_segment(rect)

# schema.py
load_input(path) -> Input                      # raises InputError(reasons)
canonical_json(obj) -> str
canonical_sha256(obj) -> str
validate_input(obj) -> Input

# conflicts.py
static_violations(inp, ann, cand, counter=None) -> list[Violation]
pair_violations(inp, a, ca, b, cb, counter=None) -> list[Violation]
evaluate_assignment(inp, assignment) -> list[Violation]
hard_violations(violations) -> list[Violation]
cluster_annotations(inp, assignment) -> list[list[str]]   # deterministic connected components
```

All modules are pure functions over the frozen model; no global mutable state
except explicit `SearchStats`/counter objects passed by the caller.

## 11. Implementation decisions recorded after the first vertical slice

These are decisions the implementation makes explicit; they do not change the
sections above.

1. **Status vocabulary** is `planned_clear | partial | blocked | needs_geometry |
   input_invalid`.  `blocked` is used when the remaining conflict cannot be
   fixed under the declared scope/capabilities (no candidate, unsupported host
   capability, frozen by scope) and `partial` when some conflicts were resolved
   but others remain.  `plan_verified` is a verification sub-status, never a
   host acceptance or a replacement for `gate_pass`.
2. **Scope in verification.**  A plan carries `scope.scope_ids` and
   `scope.frozen_ids`.  Remaining hard findings whose annotation IDs lie outside
   that scope (frozen or unsupported annotations) are classified `out_of_scope`
   and do not make a scope-clean plan `plan_rejected`; they still keep the
   overall plan `partial`/`blocked`.  Introduced conflicts in scope always fail.
3. **Checker limitations are recorded, not hidden.**  The current checker skips
   wire checks for texts whose `owner` is a symbol ID.  The independent
   brute-force recheck in `verify.py` covers those, and the checker's own
   before/after payload is retained unchanged.  See
   `issue-candidates.md` item 1.
4. **Real fixture numbers.**  The frozen photo-led v14 input has 19 components,
   98 wires, 94 fixed texts and 42 movable annotations; it starts with 3
   blocking checker conflicts and plans 2 translations totalling 10 raw.  Its
   converter uses `max_total_candidates=2000` so all 42 annotations keep a
   non-starved domain; the global cap is still a hard input bound.
5. **Verification of estimated geometry.**  If any annotation that moves has
   `bbox_source=estimated`, verification returns
   `candidate_needs_visual_review` even when the after-findings are empty.  A
   search result is never called mathematically infeasible: it is
   `budget_exhausted`, `all_candidates_rejected`, `geometry_uncertain` or
   `host_capability_unsupported`.
6. **Analysis SVG coordinates.**  Source measurement flips SVG text bboxes once
   by negating raw y; the overlay is a separate drawing space using
   `screen_y = page_height - raw_y`.  The two transforms are documented and must
   never be applied together to the same value.
7. **Benchmark honesty.**  A speedup is claimed only when the improved run ends
   with zero hard conflicts, moves no more annotations than the baseline,
   introduces no conflict and passes the independent recheck.  The synthetic
   `counterexample` is faster but moves more objects, so no speedup is claimed
   for it.  Only offline solver work is measured; EDA render/save/reopen/
   readback/whole-board time are **NOT RUN**.


