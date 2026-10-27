# Fixtures and expected behaviour

All files are committed, LF-normalized (`eol=lf` via this directory's
`.gitattributes`) and SHA-256-recorded in `MANIFEST.json`.  They are
**synthetic** except the frozen `photo-led-v14` copy; the real fixture is trimmed
from the official EasyEDA 4.1.78 SVG text measurement + `sch list` read and its
four source files keep their own SHA binding.

Regenerate after changing the builder/package:

```bash
PYTHONPATH=design-hardware/scripts python tests/annotation_layout/build_fixtures.py
```

## Synthetic cases (16)

CLI: `cd design-hardware/scripts && python -m annotation_layout plan ../../tests/annotation_layout/fixtures/synthetic/<name>.json`

| file | geometry | expected CLI result | why |
|---|---|---|---|
| `text-text.json` | two value texts overlap | `planned_clear`, 1 move, verified | K2 positive |
| `text-symbol.json` | value overlaps own symbol body | clear, 1 move | own-body overlap is hard beyond tolerance |
| `text-wire.json` | free text crossed by a wire | clear, 1 move | text-wire hard rule |
| `rotated.json` | declared 90° value overlaps fixed text | clear, 1 move, rotation/font unchanged | rotation is never changed |
| `chinese-purpose.json` | Chinese purpose text crossed by a wire, zone-clipped | clear, 1 move | CJK text, zone containment |
| `title-block.json` | free text inside title-block keep-out | clear, 1 move (120 raw allowed) | page/title escape |
| `zone-boundary.json` | free text overlaps fixed text, must stay in zone | clear, 1 move | zone constraint while fixing |
| `lock-frozen.json` | same as text-text, `A2` frozen by policy | clear by moving `A1`; `A2` never moves | local freeze |
| `no-candidates.json` | tiny zone leaves no legal grid move | `blocked`, 0 moves, `all_candidates_rejected` | no false fix |
| `estimated.json` | first value has `bbox_source=estimated` | `partial`, `candidate_needs_visual_review` | unknown geometry |
| `net-anchor.json` | net-label text crossed by own wire, detach unsupported | `blocked`, 0 moves, `host_capability_unsupported` | no broken anchor |
| `clean.json` | no conflict | `noop`, 0 changes, `planned_clear` | no meaningless write |
| `dense.json` | 6-value overlap chain | clear, 3 moves | batch density |
| `cluster-a.json` | two independent overlap clusters | clear, 2 moves; `--scope-cluster` freezes the other | local scope |
| `priority.json` | value vs free-text overlap, priority tie-break | clear, 1 move | deterministic ordering |
| `budget-exhausted.json` | chain with one-state budget | `partial`, `budget_exhausted` | bounded search, not infeasibility |

Additional committed cases: `counterexample.json` (greedy introduces a new
conflict; batch clears it), `MANIFEST.json` (hashes), `photo-led-v14/` (real
frozen input + its four sources), `holdout/`, `invalid/`.

## Holdouts (4, expectations authored, not back-filled)

`holdout/expectations.json` records acceptable statuses, max hard conflicts and
max moved annotations:

| case | design | expectation |
|---|---|---|
| `holdout-chain` | five-value chain in zone zC | clear, ≤4 moves |
| `holdout-rotated-cn` | rotated Chinese purpose text on a wire | clear, ≤1 move |
| `holdout-title-zone` | zone-clipped overlap + page-edge note | clear, ≤2 moves |
| `holdout-unsupported` | net-label detach unsupported | `blocked`/`partial`, 0 moves |

## Invalid inputs (6)

`invalid/{nan,duplicate-id,unknown-unit,bool-number,bad-bbox,unknown-key}.json`
must make each command exit 2 with `input_invalid`, never a PASS.  See
`test_cli_scenarios.py::test_04_to_09_invalid_inputs_exit_2_without_pass`.

## Protected fields

For every planned change the plan asserts content, net, font size, rotation,
alignment and owner are unchanged; component moves, wire edits, page changes,
font shrinking and hiding are forbidden.  The tests re-check these assertions;
`verify` independently recomputes the geometry and calls the existing checker.
