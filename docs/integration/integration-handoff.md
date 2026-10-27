# Integration handoff (parallel A–K window, 2026-10-28)

This is the integration session's handoff. It does **not** replace each task's own
`docs/parallel-*/handoff-current.md`; those remain the owners' records. Authoritative
per-task details and review verdicts are in [task-ledger.md](task-ledger.md).

## 1. State of `main`

* Baseline before integration: `9a951ed` (all parallel branches were based on it).
* After eight reviewed merges: `9a4622e`.
* This integration-fix commit and the electrical-review fix PR are the only other
  main-side changes in this window. No tag, release, asset upload, installer
  replacement or client change was made.
* CI: every merge was made from a PR whose exact HEAD was green on the repository
  CI (`validate` 3.10 + 3.13, `updater` ubuntu/windows). The post-merge main run is
  reported at the end of the window.

## 2. Capability matrix

| capability | status | entry point | notes |
|---|---|---|---|
| electrical-intent review (B) | implemented, **not merged in this PR set** (fix branch open) | `python -m electrical_review` | blocked only by frozen-hash LF/CRLF portability |
| return-path / reference-plane audit (E) | merged, independent | `python -m return_path_audit` | 2-layer real replay; 4-layer NOT AVAILABLE |
| mechanical layout planning (G) | merged, independent | `python -m mechanical_layout` | 2.5D only; candidates `executable:false` |
| circuit-block generation (F) | merged, independent | `python -m circuit_blocks` | abstract only; no part/footprint binding |
| change impact / ECO planning (J) | merged, independent | `python -m change_impact` | generic verification catalogue, no module adapters |
| procurement / alternates (H) | merged, independent | `python -m procurement_planner` | no live marketplace/SMT data |
| bring-up / test planning (I) | merged, independent | `python -m bringup_planner` | PASS requires real hash-bound evidence |
| delivery package audit (C) | merged, independent | `python -m delivery_audit` | bounded format subset; unknown for unsupported features |
| Skill rule/reading audit (D) | merged, independent | `python -m skill_knowledge_audit` | read-only; candidate size limits |
| own EDA toolchain (A) | **BLOCKED / not merged** | draft PR #36 | conflicting, author says do not merge, real-host M2–M4 needs a manual connector import |
| annotation batch layout (K) | **not delivered** | none | no commits, no PR |

**No capability above is wired into the main design/bring-up workflow.** There is no
adapter from any producer to any consumer; see
[cross-module-contract.md](cross-module-contract.md) and the recorded gap probes.

## 3. Integration fixes applied on main (review of the merged code, not new features)

1. `tests/mechanical_layout` → `tests/mechanical_layout_tests` (+ `__init__.py`) and
   `tests/bringup_planner` → `tests/bringup_planner_tests` (+ `__init__.py`), so the
   official CI discovery actually runs 144 + 172 tests.
2. New test packages that inserted `design-hardware/scripts` at `sys.path[0]` now
   append it; C's test support loads its implementation package explicitly. This
   removes the cross-package `ModuleNotFoundError` chain produced when several
   parallel test packages coexist (integrated run went from 33 import errors to 0).
3. `benchmarks/delivery-audit/run_benchmarks.py`: recreate the empty `stale-output`
   input directory that git cannot store (case 27 now passes in a clean checkout).
4. `benchmarks/bringup-planner/.gitattributes`: pin LF so the frozen SHA-256 baseline
   reproduces on Windows and Linux; working-tree files renormalized.
5. `design-hardware/scripts/procurement_planner/README.md`: repository-only links no
   longer escape the installable Skill root (found by D's scanner).
6. Documentation path updates for the renamed test directories + a short integration
   note appended to G's and I's own handoffs (their historical statements remain,
   with the resolution recorded).

## 4. Minimal integration verification

* Frozen dataset: `fixtures/minimal-board/board.json` (synthetic, clearly labelled;
  identity / units / snapshot binding / change set / BOM / layout constraints /
  bring-up expectations / unknowns).
* Runner: `verify_integration.py` runs each merged module's real CLI offline on its
  own documented fixture (`native` checks) and deliberately feeds producer output to
  a different module's CLI (`gap` checks, expected rejection).
* Evidence: `evidence/integration-verification.json` (machine readable) — every run
  records exit code, observed status and the fact that EDA/network calls are 0.
* Result at generation time: 8/9 native checks OK (B not merged yet), 4/4 gap probes
  confirmed as missing adapters, 0 unexpected acceptances. This is **not** an
  end-to-end product chain and must not be reported as one.

## 5. Explicit NOT RUN / BLOCKED

* Real EDA Pro / daemon / connector: **not contacted** by this session (no window,
  no refresh, no connector install — the holder of the EDA window must run it).
* Host DRC, save/reopen, official plots, Gerber/CPL/drill export, manufacturing
  order, assembly, power-up, firmware flashing, measurement: **NOT RUN**.
* A's M2–M4 acceptance: **BLOCKED** on a manual EasyEDA extension import
  (documented in PR #36); its `updater (ubuntu-latest)` CI job fails.
* K: no code to review; only another session's untracked worktree. **NOT RUN.**
* Python 3.10 runtime on the integration machine: **not available locally**; the CI
  matrix runs 3.10 and 3.13 and both were green at merge time.
* Real four-layer board replay for E: **NOT AVAILABLE** (no real four-layer snapshot
  in the repository or on this machine).

## 6. Release blockers (do not tag/publish from this state)

1. B (electrical review) is not merged: its PR CI fails because frozen hashes were
   CRLF-based. The fix branch in this window must be reviewed and merged first.
2. A (own toolchain) is a draft, conflicting PR that rewrites core entry/install,
   protocol and runtime; it is **not** to be merged without an owner rebase, full
   review, green updater CI and real-host M2–M4 evidence.
3. K is absent.
4. No cross-module adapter exists, so the delivered toolchain is a set of
   independent offline CLIs, not an automated pipeline. Do not describe it as one.
5. No real-machine evidence exists for any of the new modules in this window.
6. Windows-only local verification (3.13); macOS untested; 3.10 only via CI.

## 7. Next steps (after this window)

1. Merge the B LF fix; re-run `docs/integration/verify_integration.py` so evidence
   covers all nine delivered modules.
2. Ask A's owner to rebase on current `main`, split the runtime/connector vendoring
   from the core-installer changes, fix the updater job and complete the manual
   connector import before requesting review.
3. Someone who owns the EDA window should run A's `tools/zhigou_acceptance.py` and
   record real M2–M4 evidence; this integration session intentionally did not.
4. If cross-module automation is wanted, build adapters in this order: F→B (needs
   port/fact mapping), J→module check selection (needs a command/rule id map), then
   G/K→A (needs A merged plus a plan adapter with re-audit).
5. Before a release: run the full CI matrix on the exact candidate, `tools/offline_suite.py`,
   `design-hardware/scripts/skill_selftest.py`, the distribution build and an install
   smoke test on a clean machine, and record the python 3.10 runtime result.
