# PR #26 integration closeout

Date: 2026-10-27 (Asia/Shanghai).

Integrated original 4549780 fixes with main 095b9e1 (including PRs #30, #31 and
#32). Retargeted PR #26 from the obsolete round11 branch to main. Both histories
are preserved; no force push is needed.

## Behavior checked

- Rejected check-like candidates block discovery rather than disappearing behind
  an older clean report (EVIDENCE_CANDIDATE_REJECTED).
- Path-only manifests cannot downgrade conflicting checks; matching hash-bound
  manifests or explicit --check are required.
- Placement reports cannot impersonate DFM checks. Semantic comparison avoids
  false ambiguity from JSON formatting. Regression PG4 remains not_run.
- Invalid/unhashable frame orders return validation errors, not exceptions.

## Verification

- Independent review: no concrete blocker; 84 focused tests passed (71 gate /
  provenance, 7 frame metadata, 6 move clearance).
- Full unittest discovery: 1659 tests OK (skipped=1), 107.183 seconds.
- Skill selftest: 5 PASS / 0 FAIL / 0 NOT RUN.
- Offline round11 benchmark: 9/9 pass, one run per case.
- Simulated feedback benchmark: 16/16 pass.
- Actual pcb_gate.py subprocess CLI on synthetic evidence: clean case exit 0;
  newer invalid check exit 1 / PG4 fail with EVIDENCE_CANDIDATE_REJECTED;
  explicit --check exit 0; regression profile exit 0 / PG4 not_run.
- Local evidence: C:/Users/jlc/work/pr26-targeted.log, pr26-full.log,
  pr26-offline-benchmark.json, pr26-feedback-benchmark.json, pr26-cli-evidence/.

Subprocess cases use synthetic offline evidence, not live DRC or hardware
acceptance. No EDA calls, client installation, or Release in this round.
Existing final-code live-write and strict-compose limitations remain unchanged;
see round12/report.md and round12-real-machine.md.
