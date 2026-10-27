# Issue candidates (cross-cutting, NOT fixed here)

These are observations from task K while reusing the existing geometry adapter
and checker.  They are recorded for the owner of those components; this branch
does **not** modify `sch_layout_check.py`, `layout_from_easyeda.py`,
`design_engine`, compose or any shared reference.  Each item has a reproduction
that stays inside the K planner's own fixtures/tests.

## 1. Checker skips wire checks for symbol-owned attribute text

**Component:** `design-hardware/scripts/sch_layout_check.py`, wire loop
(`for obj in symbols + texts: if obj.get('owner') in symbol_ids or kind in
marker_text: continue`).

**Effect:** a designator/value text whose `owner` is a symbol ID is never checked
for `wire_enters_bbox`/`text_wire_clearance`, even when the text visibly sits on
a wire.  A planner could move a value onto a wire and the checker would stay
silent.

**Reproduction (no EDA):**

```bash
cd design-hardware/scripts
python - <<'PY'
import json
from annotation_layout.schema import load_input
from annotation_layout.verify import verify_plan, checker_result
from annotation_layout.model import Rect
inp = load_input('../../tests/annotation_layout/fixtures/photo-led-v14/input.json')
# take the already-moved R3 value pose and push it onto the VREF stub y=760
planned = {a.id: a.current.bbox for a in inp.annotations}
planned['8bd5a6b179fa7148'] = Rect(290, 755, 311.107666015625, 765)
checker = checker_result(inp, planned)
print('checker blocking:', len((checker['after'] or {}).get('blocking_findings', [])))
print('independent hard:', [v['code'] for v in verify_plan(inp, planned)['independent']['after']
                            if v['severity'] == 'hard'])
PY
```

The checker reports no new blocking `wire_enters_bbox` for the moved attribute,
while K's independent recheck reports a hard `text_wire_intrusion`.  K therefore
records the checker limitation and uses the independent path as authority for
attribute-scope wire conflicts.  Suggested fix owner: checker/maintainer, with a
regression test that distinguishes "own pin/graphic text at the pin" from a
deliberately moved attribute.

## 2. Attribute rotation/alignment/font are missing from the retained read

**Component:** `layout_from_easyeda.py` / `easyeda sch list` retained fixture.

**Effect:** the frozen photo-led `layout.json` has `field=attribute` and
`owner` for all 38 attribute texts but no rotation, alignment or font size.
K deliberately treats these as unknown and generates translation-only
candidates (`rotation_source=unknown`, `font_source=unknown`); a rotated attribute
could be mis-measured by a consumer that assumes rotation 0.

**Reproduction:** `python -m annotation_layout validate` on the real fixture, then
inspect any annotation's `current.rotation_deg` (null) and
`current.font_size` (null).  `tests/annotation_layout/test_convert.py` asserts
the converter does not invent values.

Suggested fix owner: adapter/executor A.  Add a host read that exposes the actual
attribute pose (or a `designator-geometry`-style result bound to the snapshot)
and extend the adapter contract; do not silently default to 0.

## 3. Free-text move persistence is historical only and must be probed

**Component:** host/executor (A), not a code bug.

**Effect:** the project notes say free-text moves were not persistent.  K sets
`free_text_translate=unverified` in the real input and marks those changes with
`host_probe_required=true`; it will not claim execution.

**Action for A:** probe with a create/move + save + reopen + SVG/readback on a
page copy, record the result in `host.capabilities`, and feed it back.  If the
move does not persist, the correct K status is a partial/frozen conflict, not a
retry loop.

## 4. Duplicate hard findings for the same title-block area

**Component:** K's own conflict layer vs checker (observation, not a checker bug).

**Effect:** K reports both `overlaps_title_block` and `overlaps_keepout` when the
title block is also declared as a hard keep-out (the converter does this).  The
same physical overlap therefore appears twice in the before/after counts.  The
checker reports it once.  K retains both rather than de-duplicating so the
independent and checker payloads can be compared item by item; the acceptance
matrix documents this.

**Reproduction:** `tests/annotation_layout/fixtures/synthetic/title-block.json`
(before hard count is 2 for one physical overlap).  Suggested future change, if
desired: deduplicate by `(text, area)` in the planner with an explicit
`dedupe_reason`, or stop declaring the title block a second time as a keep-out.
Not changed here to avoid masking a real double-count.

## 5. No public "checker layout from annotation-layout/v1" bridge

**Component:** shared tooling.

**Effect:** K has to build the checker's input dictionary itself in `verify.py`.
It matches the current checker contract but duplicates the adapter's knowledge; a
checker field rename would silently desynchronise the bridge until tests fail.

**Reproduction:** `annotation_layout/verify.py::build_checker_layout` plus the
`test_real_plan_is_verified_by_independent_path_and_checker` test.  Suggested
owner: maintainer of the offline tooling could expose a small documented builder
or a schema version check.  K cannot modify `sch_layout_check.py` under its task
boundary, so this remains a proposal.

## 6. Net-label text/anchor separation needs an explicit host capability

**Component:** executor A + K input capability.

**Effect:** if the host cannot move net-label text independently of its
electrical anchor, a net-label overlay is not a safe pose plan.  K refuses to move
it unless `host.net_label_detach=supported` and reports
`net_label_anchor_not_separable`/`host_capability_unsupported` otherwise.

**Action for A:** probe this on a page copy (move text, read net/checker/export,
save+reopen) and provide the capability.  Until then, net-label conflicts remain
reported, never "fixed" by breaking the anchor.

## 7. Cross-task test discovery poisoning by `sys.path.insert(0, scripts)`

**Components:** `tests/change_impact/__init__.py`,
`tests/bringup_planner/test_*.py`, `tests/delivery_audit/support.py`,
`tests/mechanical_layout/test_*.py`, other task test bootstraps (and formerly
`tests/annotation_layout/__init__.py` here).

**Effect:** `python -m unittest discover -s tests` imports `tests/<name>` as a
top-level package.  Any test module that does
`sys.path.insert(0, "design-hardware/scripts")` while discovery is still running
changes resolution for every later package: a later `tests/<name>` whose name
also exists under `design-hardware/scripts` is imported from the implementation
instead, and discovery then cannot find `<name>.test_*` → import-time
`ModuleNotFoundError`.  On the PR #46 merge ref this produced 42 errors across
`change_impact` (9), `return_path_audit` (8), `circuit_blocks` (7),
`delivery_audit` (7), `skill_knowledge_audit` (6), `procurement_planner` (5).
Branch-only runs pass because fewer packages are present.

**Evidence / reproduction:** see
`docs/parallel-annotation-layout/handoff-current.md`, section "Merge-ref CI
failure investigation".  Key controls: removing this branch's insertion drops
42 → 33 errors and clears `change_impact`; changing only
`tests/change_impact/__init__.py` from `insert(0, …)` to `append(…)` in a
temporary merge worktree drops 33 → 5 (only `delivery_audit` from another
insertion).

**Suggested fix owner:** each test package (other tasks).  Load the
implementation with `importlib.util.spec_from_file_location` under a private
alias (as `change_impact` already does) and do not put the scripts directory
first on `sys.path`; when subprocess CLI tests need it, pass `PYTHONPATH` in the
child environment (as `tests/annotation_layout/helpers.py` does) instead of
mutating the parent.  This branch fixed only its own test bootstrap within its
allowed path; the merge-ref check stays red until the other owners do the same.
