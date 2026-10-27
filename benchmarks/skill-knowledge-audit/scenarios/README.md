# SKA dev scenarios (15 frozen task-intent cases)

Purpose
-------
`dev.json` is the frozen evaluation set for the deterministic task-intent reading
planner (contract §6). Each scenario supplies one `ska-intent/v1` and the
expected `must_include` / `must_exclude` / `may_include` / `required_unknown` /
`forbidden_plan_actions` / `required_approval_gates` for that intent. The set
checks navigation (which Skill documents a correct minimal plan selects, skips,
or flags), not model quality: no document text is executed and no engineering
claim is made. Frozen baseline: `git_sha` 9a951edc21481dc3ae91460acc11aa3e08a7be8a,
`catalog_version` 2026-10-27.1.

Derivation (no planner output copied)
-------------------------------------
- Read fully: `docs/parallel-skill-knowledge-audit/contract.md` (§6–§7),
  `design-hardware/SKILL.md` (esp. L96 checkpoints, L118, L132–L206 按需读取,
  L134 always rule, L30/L57/L77/L100, L199, L203), and the references actually
  involved: evidence, workflow, interaction, review, agent-collaboration,
  design-gates, schematic-authoring/-layout/-layout-engine, pcb, pcb-execution,
  pcb-placement-details, pcb-routing-strategy, pcb-routing-details,
  analog-rf-highspeed, easyeda-ecosystem, part-selection, lcsc-sourcing,
  jlc-handoff, jlc-production, manufacturing-details, offline-tools,
  offline-regression, connectivity, plus routing-plan and
  pcb-delivery-checklist. Line/table-row citations live in each rationale.
- Expectations were written from those rules before the planner was inspected;
  no planner output, plan.py behaviour, or benchmark result was copied into
  `dev.json`. When a document was plausible but not provable as required, it was
  put in `may_include` and the uncertainty stated in the rationale.
- Every path was verified as an existing worktree file (`Test-Path` + validator),
  and all must/may/exclude lists are disjoint per scenario.
- Lead-frozen conventions encoded here: always set = SKILL.md + workflow.md +
  evidence.md; design-gates.md required for schematic/PCB/layout/route/delivery
  types; approval-gate tokens are the frozen list and `required_approval_gates`
  must be a subset of `intent.user_decision_pending` (planner copies, never infers).

Coverage matrix
---------------
| id | task_type | protection / exercised expectation |
|---|---|---|
| dev-01 | schematic_new | vague sensor task → always set + schematic-authoring/layout/gates; `domain_unspecified`; no PCB/BOM docs |
| dev-02 | schematic_new | dense ESP32-S3/USB-C/LDO/I2C → adds digital.md; still excludes PCB/production/sourcing |
| dev-03 | schematic_edit | readability-only text reflow → layout-engine + layout; stale `already_read` (bad sha256) → `already_read_stale` |
| dev-04 | pcb_layout | constrained move after routing → pcb + pcb-execution + eda-execution + placement + gates; no schematic rewrite |
| dev-05 | pcb_layout | new 2-layer layout only → PCB execution/placement; routing docs deferred to `may_include` |
| dev-06 | four_layer_diff | 4-layer impedance/diff planning only → routing strategy/details + analog/high-speed + ecosystem; `write_eda` forbidden |
| dev-07 | bom_only | BOM/sourcing only, stage unspecified → part-selection + lcsc-sourcing; `stage_unspecified`; routing/thermal excluded |
| dev-08 | review_only | read-only electrical review → review + evidence; `write_eda`/EDA flow docs excluded, gates conditional |
| dev-09 | delivery_audit | G6/JLC package audit → gates + jlc-handoff + jlc-production + manufacturing-details + checklist; no engineering writes |
| dev-10 | offline_dev | connector/EDA unavailable → offline-tools + offline-regression + connectivity; `eda_unavailable`; no EDA docs |
| dev-11 | pcb_layout | user forbids EDA → offline PCB placement plan; `eda_unavailable`; `write_eda`/`read_eda`/`install` forbidden |
| dev-12 | full_product | autonomous whole-board authorization → gates + agent-collaboration + schematic authoring + PCB execution; `wait_user_approval` forbidden |
| dev-13 | pcb_route | "confirm layout before routing" → `before_route` in both `user_decision_pending` and `required_approval_gates` |
| dev-14 | schematic_new | `budget_chars` 2500 < required chars → required not trimmed, `budget_insufficient`, status incomplete |
| dev-15 | pcb_route | mid-task expansion to 4-layer diff routing → stale rules_version/scope → `cache_invalidated` + `scope_change` gate |

All 11 allowed task types are used except `knowledge_only`; the 15 coverage items
requested by the task brief are each represented exactly once.

Holdout separation protocol
---------------------------
- `holdout.json` was designed independently by teammate `scenario-holdout`, who
  did not read `dev.json` or this README; wording, task framing and rationales
  differ on purpose. This is a separated review of the same contract, **not a
  blind test**: both designers saw contract §6–§7 and the Skill text.
- The implementation must not branch on scenario ids or on dev-vs-holdout origin;
  scoring must be generic over intents. Holdout expectations are not edited to
  match planner output, and dev expectations are not edited to match holdout.
- This README, `dev.json` and the validator are dev-only artifacts; do not share
  them with the holdout designer before freeze, and do not copy holdout cases
  into dev. Any contamination or post-freeze edit must be recorded, not silently
  repaired.

Measurement definitions
-----------------------
Per scenario (`benchmark` in contract §7.2); `planned` = required ∪ conditional ∪ optional:
- `required_recall` = |planned ∩ must_include| / |must_include|.
- `missing_critical` = |must_include \ planned|; any value > 0 fails the scenario.
- `forbidden_selected` = |planned ∩ must_exclude|; any value > 0 fails.
- `required_unknown` / `unknown_expected_missing` = expected codes in
  `required_unknown` not reported in plan `unknown`; codes must come from §6.2.
- `forbidden_actions` = |execution_contract.actions ∩ forbidden_plan_actions|;
  any hit fails. Approval gates are checked as `required_approval_gates ⊆
  execution_contract.approval_gates`.
- `stable` = two consecutive runs produce the same plan digest (timestamps/hashes
  excluded).
- `selected_bytes` = summed bytes of planned files; compared against
  `baseline_all_markdown_bytes` = bytes of all reachable Markdown documents. The
  all-Markdown path is only a baseline strategy, not a record of what a user or
  earlier agent actually read; lower `selected_bytes` is not engineering speed.
- Secondary: `unrelated_bytes` (planned bytes outside must∪may), `budget_status`
  (`within|exceeds|incomplete`), `duration_ms`.

NOT RUN
-------
- Model behaviour: no claim that an LLM loads these documents, follows the rules,
  or improves hardware outcomes.
- EDA: no connector/daemon use, no reads, writes, DRC, save/reopen, or GUI
  evidence; offline-only and path-existence checks were run.
- Tokenizer: budget uses the contract's char-class heuristic, not a real
  tokenizer; token_estimate is not RUN.
- Real drawing/engineering speed and end-to-end task time: not measured; byte
  reduction of the reading plan is not a productivity or correctness result.
