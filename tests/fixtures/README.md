# Retained real-data fixtures

These files are read-only evidence from actual EasyEDA pages.  They keep failure
shapes reproducible; they do not assert that the project passed acceptance.

## `photo-led-acceptance.json`

- Source project: `photo-led-5v-20261026`, page `cd008f919db36eba` (P1),
  EasyEDA Pro 4.1.78, easyeda-agent 1.15.0.
- Inputs: `easyeda sch list --include-bbox --include-pins --include-wires
  --include-page-primitives`, `schematic.visible_text.bboxes`,
  `easyeda sch sheet-geometry --from-svg` on the official PNG/SVG export, and
  `svg_text_bbox.py` over the same SVG (134 rendered texts).
- Built with `layout_from_easyeda.py --expect-rotation GND=0 --expect-rotation
  +5V=0 --min-text-wire-clearance 5`.
- Preserved failures: zone reading order 2,1,3,4; orphan `LED_CTRL` text;
  duplicate `Claude Code` in the title block; GND/+5V net flags at 90/180/270
  degrees; value/marker text within 5 raw of wires.
- The project was later edited by its owning session; this fixture captures the
  measured pre-fix state and must not be used as the project's current result.

## `photo-led-visible-text.json`

Historical `visible_text.bboxes` payload (API subset only: 65 measured, 2
unmeasured).  Used to test honest coverage gaps: pin names, wire names and
border text are absent and must not be reported as complete.
