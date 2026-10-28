"""ECO change-impact analysis and incremental verification planning.

The package answers one question for a hardware ECO: *given an explicit set of
design changes, what is theoretically affected, which prior evidence may still
be relied on, and which verification remains necessary?*  It does not diff
geometry (the existing feedback/design-engine layers do that), it does not
write to a design, and it never claims that a board is correct.

Everything here is deterministic: the same input bytes and the same declared
model produce the same report bytes.  Unknown is a first-class value: an absent
dependency edge is not evidence of no impact, and an absent catalog entry is a
coverage gap rather than a pass.

Module map
----------
canonical   canonical JSON, hashing, finite-number checks
errors      machine-readable failure classes
model       versioned input contract and strict validation
classify    change intake, classification and declared-vs-observed diff
graph       dependency index, deterministic traversal, cycles and budgets
propagate   change-kind aware impact propagation rules (J2)
evidence    prior-evidence invalidation and reuse assessment (J3)
verify_plan bounded verification selection, gates and coverage gaps (J4)
compare     multi-candidate ECO comparison (J5)
report      report assembly and human-readable ECO handover (J6)
cli         ``python -m change_impact`` entry point
"""
from __future__ import annotations

TOOL_VERSION = '0.1.0'
IMPLEMENTATION = 'change-impact'

SCHEMA_MODEL = 'hds-change-impact-input/v1'
SCHEMA_ANALYSIS = 'hds-change-impact-analysis/v1'
SCHEMA_PLAN = 'hds-change-impact-plan/v1'
SCHEMA_VALIDATE = 'hds-change-impact-validation/v1'
SCHEMA_ERROR = 'hds-change-impact-error/v1'
SCHEMA_COMPARE_INPUT = 'hds-change-impact-compare-input/v1'
SCHEMA_COMPARE = 'hds-change-impact-compare/v1'
SCHEMA_EXPLAIN = 'hds-change-impact-explain/v1'

# Overall status.  There is deliberately no "design_pass": completing an
# analysis says nothing about whether the board is correct or the change was
# applied.
STATUS_PLANNED_WITH_SCOPE = 'planned_with_scope'
STATUS_INCOMPLETE = 'incomplete'
STATUS_INPUT_INVALID = 'input_invalid'
STATUS_NO_CHANGE = 'no_change'
STATUSES = (
    STATUS_PLANNED_WITH_SCOPE,
    STATUS_INCOMPLETE,
    STATUS_INPUT_INVALID,
    STATUS_NO_CHANGE,
)

# Object kinds (J2 model).  A model may use a subset; the declared scope says
# which ones are complete for this snapshot.
OBJECT_KINDS = (
    'component_instance',
    'pin',
    'net',
    'power_domain',
    'interface',
    'layout_region',
    'mechanical_anchor',
    'bom_line',
    'firmware_contract',
    'test',
    'artifact',
    'requirement',
    'document',
)

# Change classes produced by J1.  ``unknown_attribute`` is never folded into
# ``display_only``.
CHANGE_KINDS = (
    'display_only',
    'identity_rename',
    'parameter',
    'power_requirement',
    'component_identity',
    'footprint',
    'pin_mapping',
    'connectivity',
    'mechanical_pose',
    'board_outline',
    'layer_stack',
    'delivery_config',
    'firmware_contract',
    'test_criterion',
    'requirement',
    'document_metadata',
    'unknown_attribute',
)

# What a propagated path asserts about a target object.
IMPACT_KINDS = (
    'electrical_state',
    'power_integrity',
    'signal_integrity',
    'pin_compatibility',
    'footprint_compatibility',
    'layout_congestion',
    'mechanical_fit',
    'enclosure_interface',
    'assembly_fit',
    'bom_variant',
    'firmware_compatibility',
    'manufacturing_output',
    'test_criterion_change',
    'requirement_trace',
    'documentation_only',
    'unknown',
)

# Dependency semantics.  An edge only propagates when the change class is
# compatible with its semantic (see ``propagate.RULES``).
DEPENDENCY_SEMANTICS = (
    'power_supply',
    'signal_path',
    'pin_mapping',
    'footprint_binding',
    'mechanical_constraint',
    'enclosure_constraint',
    'artifact_source',
    'verification_coverage',
    'requirement_ref',
    'firmware_consumer',
    'test_reference',
    'document_reference',
)

DEPENDENCY_CERTAINTY = ('declared', 'observed', 'inferred', 'unknown')

CONFIDENCES = ('certain', 'possible', 'unknown')
CONFIDENCE_RANK = {'certain': 2, 'possible': 1, 'unknown': 0}

# Verification plan states.
PRIORITIES = ('required', 'conditional', 'optional', 'blocked')
CHECK_KINDS = ('offline', 'host', 'manual')

# Prior-evidence assessment states.  No state means "valid": reuse always
# carries the original capture binding plus an explicit assessment.
EVIDENCE_INVALIDATED = 'invalidated'
EVIDENCE_REUSABLE_BOUND = 'reusable_bound'
EVIDENCE_REUSABLE_ASSESSED = 'reusable_with_assessment'
EVIDENCE_NOT_APPLICABLE = 'not_applicable'
EVIDENCE_UNKNOWN = 'unknown'
EVIDENCE_STATES = (
    EVIDENCE_INVALIDATED,
    EVIDENCE_REUSABLE_BOUND,
    EVIDENCE_REUSABLE_ASSESSED,
    EVIDENCE_NOT_APPLICABLE,
    EVIDENCE_UNKNOWN,
)

# Why a propagation path stopped.  A stop is never proof of no impact unless
# the reason says so explicitly (``declared_boundary`` with a complete model).
STOP_REASONS = (
    'leaf_object',
    'semantic_mismatch',
    'display_only_boundary',
    'declared_boundary',
    'already_visited',
    'cycle_detected',
    'depth_budget',
    'path_budget',
    'deduplicated',
    'missing_edge_data',
)

# Failure classes for machine branching (mirrors the feedback layer style).
FAILURE_INVALID_INPUT = 'invalid_input'
FAILURE_PATH_CONFLICT = 'path_conflict'
FAILURE_BUDGET_EXHAUSTED = 'budget_exhausted'
FAILURE_UNRESOLVED_UNKNOWN = 'unresolved_unknown'
FAILURE_INTERNAL = 'internal_error'

# Explicitly not executed by this tool.  Anything outside offline analysis is
# only ever planned, never claimed as run.
NOT_RUN_ACTIONS = (
    'eda_read',
    'eda_write',
    'host_drc',
    'save_and_reopen',
    'official_plot',
    'physical_test',
    'manufacturing_order',
)
