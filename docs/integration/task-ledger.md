# Parallel-task integration ledger

Integration window: 2026-10-28 (Asia/Shanghai). Integrator: main integration session
(no shared chat with the parallel sessions; coordination is via branches, PRs and
each task's own handoff under `docs/parallel-*/`).

Base of every parallel branch: `main @ 9a951edc21481dc3ae91460acc11aa3e08a7be8a`
("test: make Chinese fixture portable across Windows locales"). Every branch is
purely additive (0 modified/deleted files outside its own trees), verified with
`git diff --name-status origin/main...origin/<branch>`.

## 1. Ledger

| task | branch | PR | reviewed HEAD | scope (files / lines) | implementation | tests discovered by CI | evidence run by integrator | review |
|---|---|---|---|---|---|---|---|---|
| A own CLI/daemon/connector/protocol/install | `feat/integrated-eda-toolchain` | #36 (draft) | `0aff47c` | 1703 files, +559787/−1548, 104 modified core files | runtime rebrand + connector + protocol + installer + doctor/capabilities; M2–M4 blocked by a manual EDA extension import | CI validate 3.10/3.13 SUCCESS; updater (ubuntu) FAILURE, updater (windows) CANCELLED | not merged; `gh pr view` mergeable=CONFLICTING; author states "不合并、不发布，等用户确认"; no EDA/host run by integrator | **BLOCKED** |
| B offline electrical-intent review | `feat/parallel-electrical-review` | #38 | `f473f0d` | 70 files, +12006 | working CLI + 6 rule groups + 31 frozen CLI cases | 50 tests discovered (Windows pass) | module tests 50 OK on Windows; benchmark 31/31 on Windows; **CI validate 3.10/3.13 FAILURE** (frozen `input_sha256` computed over CRLF bytes, Linux checkout is LF) | **修复后复审 → merged via #48** (`f473f0d` reviewed, LF fix at `99ba5ed`; PR #38 closed as superseded) |
| C manufacturing delivery audit | `feat/parallel-delivery-audit` | #40 | `ea565b7` | 258 files, +44612 | working CLI (inspect/manifest/audit), bounded Gerber/drill/BOM/CPL subset, 28 frozen cases | 303 tests (1 skip) | 303 OK; benchmark 28/28 after integration fix; Apache-2.0 real sample attributed | **可合并 → merged** |
| D Skill rule consistency / minimal reading path | `feat/parallel-skill-knowledge-audit` | #45 | `3c3f611` | 60 files, +131654 | read-only scan/rules/plan/benchmark CLI, 20 scenarios, frozen real baseline | 53 tests (1 skip) | 53 OK; benchmark 20/20; scan 312 files / 0 errors on integrated main after H README fix; 16 documented anchor warnings | **可合并 → merged** |
| E high-speed reference plane / return path | `feat/parallel-return-path-audit` | #37 | `b4cfa7b` | 134 files, +38112 | working CLI, 45 frozen scenes, 2-layer real replay derived from repo case; 4-layer replay NOT AVAILABLE | 112 tests | 112 OK; benchmark 45/45; derived real replay runs offline; `recovered_return_path` never true | **可合并 → merged** |
| F parameterized standard circuit blocks | `feat/parallel-circuit-blocks` | #44 | `de88fcc` (code at `b832c94`) | 107 files, +25617 | 6 block modules + compose, exact interval math, 54 frozen cases | 212 tests | 212 OK; benchmark 54/54 (43 + 11 holdout); binding levels explicit NOT RUN | **可合并 → merged** |
| G mechanical layout / interface constraints | `feat/parallel-mechanical-layout` | #42 | `317876c` | 119 files, +23349 | working CLI (validate/audit/plan/explain), G1–G5 rules, 2.5D, SVG analysis overlays, 34+4 frozen cases | **0 discovered at review time** (test dir not a package + same-name import) | 144 OK when explicitly invoked; benchmark 34/34 + holdout 4/4; plan candidates `executable:false`; missing geometry → review | **可合并（含发现性修复）→ merged** |
| H BOM procurement / alternates | `feat/parallel-procurement-planner` | #41 | `4df463f` | 47 files, +11506 | working CLI (validate/demand/plan/alternates/explain), Decimal money, channel split, 6 frozen cases | 78 tests | 78 OK; benchmark 6/6; unknown stock/price never treated as 0 | **可合并 → merged** |
| I first-board power-up/test/fault plan | `feat/parallel-bringup-planner` | #39 | `b407d72` | 175 files, +44762 | working CLI (validate/plan/explain/evaluate), I1–I6, 41 frozen checks | **0 discovered at review time** (same discovery defect) | 172 OK when explicitly invoked; benchmark 41/41 after LF fix; PASS requires hash-bound real evidence, synthetic → SYNTHETIC_ONLY | **可合并（含发现性与 LF 修复）→ merged** |
| J ECO change impact / incremental verification | `feat/parallel-change-impact` | #43 | `2eec288` | 136 files, +26110 | working CLI (validate/analyze/plan/compare/explain), 50 frozen cases | 231 tests | 231 OK; benchmark 50/50; unknown/incomplete preserved, no `design_pass` | **可合并 → merged** |
| K schematic annotation batch avoidance / local layout | `feat/parallel-annotation-layout` | #46 | `3cc7e1e` (code reviewed at `d2e539f`; `3cc7e1e` is docs-only) | 97 files, +46369, additive only | working CLI (validate/plan/verify/benchmark/convert/version); 86 tests; 5 benchmark cases (1 real frozen + 4 synthetic) with explicit quality gate | 86 tests discovered by the official entry | 86 OK targeted; merged with current main locally → full suite 3230 tests OK; benchmark honest per-case table (counterexample not claimed as speedup); render/save/reopen/readback NOT RUN | **可合并（含跨任务 sys.path 风险记录）→ merged** |

### Merged to main (in order)

| order | PR | merge commit | reviewed head |
|---|---|---|---|
| 1 | #37 E | `4316729` | `b4cfa7b` |
| 2 | #40 C | `f7a04b6` | `ea565b7` |
| 3 | #41 H | `2af8fcb` | `4df463f` |
| 4 | #43 J | `259d438` | `2eec288` |
| 5 | #44 F | `9778dcd` | `de88fcc` |
| 6 | #45 D | `7990cec` | `3c3f611` |
| 7 | #42 G | `ecb4c8a` | `317876c` |
| 8 | #39 I | `9a4622e` | `b407d72` |
| 9 | #47 integration fixes (discovery/portability) | `6a5c4f7` | `a575748` |
| 10 | #48 B (LF frozen-hash fix) | `3f21897` | `99ba5ed` (reviewed task B at `f473f0d`) |
| 11 | #52 B follow-up (pad-nets / switch bypass) | `acbcc18` | `0c3136d` |
| 12 | #51 G docs reconciliation | `b3ce6fd` | `52fdb11` |
| 13 | #53 D merged-main verification docs | `49a9f80` | `b1d4b07` |
| 14 | #54 doc test-path correction | `6f588f4` | `df116be` |
| 15 | #46 K (annotation layout planner) | `dd69452` | `3cc7e1e` (code at `d2e539f`) |

`main` after the eight module merges: `9a4622e`. Integration fixes #47 → `6a5c4f7`; task B #48 → `3f21897`; later in the same window the repository owner merged #49 (J handoff docs) → `1f3abee`, task-B follow-up #52 → `acbcc18`, and docs PRs #51 → `b3ce6fd`, #53 → `49a9f80`, #54 → `6f588f4`; task K #46 → `dd69452`. The final `main` HEAD and CI status after the last evidence-refresh PR are recorded in the final handoff.

## 2. Cross-cutting defects found by integration review

1. **Test discovery false green (G, I).** `tests/mechanical_layout/` and
   `tests/bringup_planner/` had no package marker, so `python -m unittest discover
   -s tests` (the CI command) never imported them. Their PRs were CI-green with
   **0** of their own tests run. Fixed by renaming to `*_tests` packages.
2. **Cross-package import shadowing (all modules, latent).** `unittest discover -s
   tests` imports each subdirectory as a top-level package. Several new test
   packages inserted `easycirq/scripts` at `sys.path[0]`; after the first
   one ran, later test packages resolved to the *implementation* package and
   failed to import (33 `ModuleNotFoundError`s in the first integrated run).
   Fixed by moving those insertions to the end of `sys.path` and by loading the C
   implementation package explicitly instead of relying on path order.
3. **Frozen-hash platform drift.** B froze SHA-256 values over CRLF working-tree
   bytes (fails on Linux CI); I froze them over LF bytes (failed on a normal
   Windows checkout). Fixed with per-tree `.gitattributes` (`text eol=lf`) and, for
   B, regenerated hashes in the fix branch.
4. **Benchmark depends on an uncommitted empty directory.** C's `stale-output`
   benchmark case needs `fixtures/27-stale-output-replacement/input/`, which git
   cannot store; a clean checkout crashed in `shutil.copy2`. Fixed in the driver.
5. **Repository-only links inside the installable Skill.** H's
   `easycirq/scripts/procurement_planner/README.md` linked `../../../docs/...`;
   D's scanner correctly flagged the escaping targets. Links degraded to code spans.
6. **No cross-module adapters.** Verified: producer → consumer probes are rejected
   (see `evidence/integration-verification.json`). Each module's own
   `integration-proposal.md` already says the adapter is future work.

## 3. What is independently usable vs integrated

* **Independently usable (merged, CLI + tests + frozen benchmark):** B, C, D, E, F,
  G, H, I, J, K. Each is a standalone `python -m <module>` CLI under
  `easycirq/scripts/`, offline, stdlib-only.
* **Not wired into any main workflow:** none of them is referenced from
  `SKILL.md`/references and no producer→consumer adapter exists. Their integration
  proposals are plans, not code.
* **Blocked / not merged:** A (#36 draft, conflicting). All of B–K are merged;
  PR #38 is closed as superseded.

## 4. Verification records

* Full repository suite on the integration branch (8 merged modules, before B):
  `python -m unittest discover -s tests` → **3089 tests, OK (skipped=2)**, ~236 s,
  Windows 11 / Python 3.13.15.
* Frozen benchmarks re-run by the integrator (all offline, `real_eda` NOT RUN):
  C 28/28, D 20/20, E 45/45, F 54/54, G 34/34 (+ holdout 4/4), H 6/6, I 41/41,
  J 50/50.
* D's own read-only scanner on integrated `main`: 312 files, 0 errors, 16
  documented anchor warnings (used as an integration gate).
* `docs/integration/verify_integration.py` → `evidence/integration-verification.json`:
  8/9 native checks OK (B absent at generation time), 4/4 gap probes confirmed,
  0 unexpected acceptances.
* Final candidate before task K, `main @ 3f21897` (nine modules): 3139 tests OK.
  With task K merged locally on current main: **3230 tests, OK (skipped=2)**, ~308 s;
  CI on `3f21897`, `6f588f4` and `dd69452` push runs: both workflows SUCCESS.
* Task B benchmark after the LF fix: 31/31 (`real_eda=NOT RUN`, `eda_calls=0`).
* `easycirq/scripts/skill_selftest.py`: 5 PASS / 0 FAIL (repository and
  installed copy).
* Packaging: `python distribution/build_release.py` → `easycirq-1.0.1.zip`,
  `easycirq-installer-1.0.1.zip`, `SHA256SUMS`, `release.json` (696 files,
  version 1.0.1). No publish/tag.
* Maintainer offline runner `tools/offline_suite.py` (after integration fix): 3230
  tests, 0 failures, 0 errors, 2 skipped, `status: pass`, offline guard installed;
  before the fix it reported 57 discovery errors on integrated `main` while CI was
  green.
* Install smoke: installer extracted into a temporary fake client skills directory;
  installed copy self-test 5 PASS; `doctor_env.py --summary` runs read-only and
  correctly reports incomplete with no active client. No real client directory or
  installed skill was modified.
* **NOT RUN:** any real EDA/daemon/connector interaction, host DRC, save/reopen,
  official plots, manufacturing order, physical measurement, power-up, firmware
  flashing, Python 3.10 runtime (local machine has only 3.13; CI matrix covers 3.10).
