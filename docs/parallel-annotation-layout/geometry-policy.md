# Geometry policy

Status: implementation policy for `annotation-layout/v1`.  All numbers below are
read from the input; none is a hidden default that silently overrides a project
choice.  The existing checker `easycirq/scripts/sch_layout_check.py` is
never modified, and no threshold is changed to make a plan green.

## 1. Coordinate conventions

- Raw schematic coordinates are **y-up**, exactly as supplied.  The planner never
  converts to pixels/inches and never infers a scale; `units.name` must be
  `schematic_raw` and `units.raw_per_mm` must be a positive finite number.
- The frozen photo-led v14 adapter measures official EasyEDA SVG text bboxes in
  a y-down space whose values are the negation of raw y
  (`rendered_bbox_to_raw()` flips once).  The v1 input records both facts:
  `coordinate_system.y_axis=up` and a non-empty declared transform.  No second
  flip is ever applied to a stored bbox.
- Analysis overlays use their own single display transform
  `screen_y = page_height - raw_y`; this is why the SVG looks upright while the
  stored geometry stays raw y-up.  That transform is applied exactly once in
  `svg_analysis.py` and is labelled analysis-only.
- `flat-segments` encodings are independent wire segments.  An ordered point
  list is judged segment-by-segment; a flat list is never treated as a polyline
  and no diagonal is invented between independent segments.

## 2. Bboxes and uncertainty

| source | meaning | planner behaviour |
|---|---|---|
| `measured_svg` | measured from the official SVG text rendering | usable for a verified plan |
| `measured_api` | measured from a host geometry read | usable if the adapter says so |
| `declared` | supplied by the user/adapter as a declared box | usable for planning, flagged as declared |
| `estimated` | font-metric estimate, no measured glyph extent | a move that relies on it can never be `plan_verified`; result is `candidate_needs_visual_review` |

The real photo-led fixture has `measured_svg` for every text and
`font_metrics_known=false`: the bbox is evidence, but the planner does not claim
glyph-level correctness for untested fonts.  Symbol bodies are conservative
rectangles, not shape-accurate outlines; a bbox may cover legal whitespace or an
outgoing pin area.  The planner stays conservative and never weakens a checker
rule because of the approximation; candidates that only clear because of symbol
-bbox slack retain the uncertainty note.

## 3. Hard vs soft findings

Hard (block plan verification while attributable to a movable annotation):

- page and usable-area escape, title-block / declared keep-out overlap;
- `text_text_overlap` (positive intersection);
- `text_symbol_overlap` (positive intersection, except the documented own-symbol
  edge tolerance);
- `text_wire_intrusion` (a segment passes through the open interior of the text
  bbox);
- owner-association failures (`owner_too_far`, unknown owner) and zone escape
  when the annotation is declared to stay in its zone.

Soft / informational only (reported, never used to claim a hard fix):

- near-miss clearances (`text_text_clearance`, `text_symbol_clearance`,
  `text_wire_clearance`);
- own-symbol edge contact within `self_text_contact_tolerance`;
- own-wire edge contact within `label_own_wire_edge_tolerance`.

## 4. Ownership rules (mirroring the existing checker, conservatively)

- A net label's **own** anchored wire may touch only the outer edge margin.  The
  bbox is shrunk by `label_own_wire_edge_tolerance`; a segment entering that
  inner box is still a hard `text_wire_intrusion` (with `own_wire=true`).  No
  wire is ever exempted wholesale.
- A symbol's own attribute/pin text may touch the symbol body by at most
  `self_text_contact_tolerance`; deeper overlap is hard.  Ownership is never a
  free pass for a designator/value that visibly sits inside the body.
- A text with no declared owner cannot be guessed and moved: designator/value
  without a component owner is `owner_unknown`; a plan does not invent identity.
- `net_label`/`wire_name` text is fixed unless the input declares
  `capability.translate=supported` **and** host `net_label_detach=supported`.
  Otherwise the conflict is reported as `host_capability_unsupported` /
  `net_label_anchor_not_separable`, not "fixed" with a misleading move.
- Wires, pins, junctions, components, zone frames, the title block, border text
  and instance identity are never moved or rewritten.

## 5. Zone, page and title-block policy

- `page.bbox` is the physical page; `page.usable_bbox` is the drawing area used
  for candidate containment.  A candidate outside the usable area is discarded
  before scoring.
- `page.title_block` and every `hard` keep-out reject candidates that intersect
  them.  Declared functional zones can be `hard=false`; when an annotation has
  `keep_in_zone=true`, its candidate must stay inside that zone bbox.  Zones are
  never redrawn and components never cross zones.
- A title-block overlap is reported once per containing object; the checker may
  additionally report the same area as a keep-out.  This duplication is retained
  rather than silently de-duplicated, so the checker and independent reports can
  be compared item by item.

## 6. What the geometry layer refuses to do

- no font shrinking, hiding, deleting, rewording or net renaming;
- no component movement, pin floating, wire rerouting or page creation;
- no image/OCR or visual-model judgement;
- no "threshold tuning" or ignore list to make a conflict disappear;
- no treating a model coordinate as measured geometry without the `bbox_source`
  provenance;
- no second y-flip, no per-object refit, no silent grid snapping of the current
  pose (only candidate poses are generated on the grid).
