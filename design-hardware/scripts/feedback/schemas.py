"""Versioned contracts for the closed-loop feedback layer.

Every tool in this package reads and writes JSON that names its own schema.
The validators are deliberately strict about the fields that decide whether a
statement is evidence or a guess:

* an observation must identify the exact window/project/document it came from;
* an unknown value is stored as an explicit ``unknown`` entry, never as zero,
  empty list or "pass";
* a modification contract must have a baseline, a writable scope and at least
  one invariant before a write is allowed;
* an evaluation has no total score and cannot turn a hard failure into a pass;
* a case must record which verification level was actually executed.

These modules do not call EDA.  They only describe and validate data.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

SCHEMA_CAPABILITIES = 'hds-capabilities/v1'
SCHEMA_OBSERVATION = 'hds-observation/v1'
SCHEMA_INTENT = 'hds-intent/v1'
SCHEMA_ISSUE = 'hds-issue/v1'
SCHEMA_MODIFICATION = 'hds-modification/v1'
SCHEMA_PREVIEW = 'hds-preview/v1'
SCHEMA_APPLY = 'hds-apply/v1'
SCHEMA_DIFF = 'hds-diff/v1'
SCHEMA_LOOP = 'hds-feedback-loop/v1'
SCHEMA_EVALUATION = 'hds-quality-eval/v1'
SCHEMA_CANDIDATE_COMPARISON = 'hds-candidate-compare/v1'
SCHEMA_CASE = 'hds-case/v1'
SCHEMA_CASE_INDEX = 'hds-case-index/v1'
SCHEMA_CASE_QUERY = 'hds-case-query/v1'
SCHEMA_RECOVERY = 'hds-recovery/v1'
SCHEMA_ERROR = 'hds-error/v1'

TOOL_VERSION = '1.0.0'

# Failure classes are the only allowed machine-readable reasons.  A caller
# must branch on ``failure_class`` instead of matching English text.
FAILURE_INVALID_INPUT = 'invalid_input'
FAILURE_PRECONDITION_REFUSED = 'precondition_refused'
FAILURE_STALE_BASELINE = 'stale_baseline'
FAILURE_TARGET_MISMATCH = 'target_mismatch'
FAILURE_OUT_OF_SCOPE = 'out_of_scope'
FAILURE_HOST_UNAVAILABLE = 'host_unavailable'
FAILURE_ADAPTER_ERROR = 'adapter_error'
FAILURE_TIMEOUT = 'timeout'
FAILURE_PARTIAL_WRITE = 'partial_write'
FAILURE_VERIFICATION_FAILED = 'verification_failed'
FAILURE_UNKNOWN_EXECUTION_STATE = 'unknown_execution_state'
FAILURE_NOT_RUN = 'not_run'
FAILURE_BLOCKED = 'blocked'

FAILURE_CLASSES = (
    FAILURE_INVALID_INPUT,
    FAILURE_PRECONDITION_REFUSED,
    FAILURE_STALE_BASELINE,
    FAILURE_TARGET_MISMATCH,
    FAILURE_OUT_OF_SCOPE,
    FAILURE_HOST_UNAVAILABLE,
    FAILURE_ADAPTER_ERROR,
    FAILURE_TIMEOUT,
    FAILURE_PARTIAL_WRITE,
    FAILURE_VERIFICATION_FAILED,
    FAILURE_UNKNOWN_EXECUTION_STATE,
    FAILURE_NOT_RUN,
    FAILURE_BLOCKED,
)

# Loop stages.  The names are part of the contract; aliases are not accepted.
STAGE_OBSERVE = 'observe'
STAGE_PLAN = 'plan'
STAGE_PREPARE = 'prepare'
STAGE_APPLY = 'apply'
STAGE_READBACK = 'readback'
STAGE_VERIFY = 'verify'
STAGE_REPAIR = 'repair'
STAGE_DONE = 'done'
STAGE_FAILED = 'failed'
STAGE_BLOCKED = 'blocked'
STAGES = (
    STAGE_OBSERVE, STAGE_PLAN, STAGE_PREPARE, STAGE_APPLY,
    STAGE_READBACK, STAGE_VERIFY, STAGE_REPAIR,
    STAGE_DONE, STAGE_FAILED, STAGE_BLOCKED,
)
TRANSITIONS = {
    STAGE_OBSERVE: (STAGE_PLAN, STAGE_BLOCKED, STAGE_FAILED),
    STAGE_PLAN: (STAGE_PREPARE, STAGE_OBSERVE, STAGE_BLOCKED),
    STAGE_PREPARE: (STAGE_APPLY, STAGE_PLAN, STAGE_BLOCKED),
    STAGE_APPLY: (STAGE_READBACK, STAGE_FAILED, STAGE_BLOCKED),
    STAGE_READBACK: (STAGE_VERIFY, STAGE_APPLY, STAGE_FAILED),
    STAGE_VERIFY: (STAGE_REPAIR, STAGE_DONE, STAGE_FAILED),
    STAGE_REPAIR: (STAGE_PLAN, STAGE_VERIFY, STAGE_FAILED),
    STAGE_DONE: (),
    STAGE_FAILED: (),
    STAGE_BLOCKED: (),
}

STOP_TARGET_CHANGED = 'target_changed'
STOP_PRECONDITION_INVALID = 'precondition_invalid'
STOP_OUT_OF_SCOPE = 'out_of_scope'
STOP_INVARIANT_BROKEN = 'invariant_broken'
STOP_CRITICAL_ERROR_ADDED = 'critical_error_added'
STOP_UNKNOWN_EXECUTION_STATE = 'unknown_execution_state'
STOP_BUDGET_EXHAUSTED = 'budget_exhausted'
STOP_NO_IMPROVEMENT = 'no_improvement'
STOP_USER_STOP = 'user_stop'
STOP_COMPLETED = 'completed'
# Terminal stages double as stop reasons so a caller does not need a second
# vocabulary when a loop ends in failure or blockage.
STOP_FAILED = STAGE_FAILED
STOP_BLOCKED = STAGE_BLOCKED
STOP_REASONS = (
    STOP_TARGET_CHANGED, STOP_PRECONDITION_INVALID, STOP_OUT_OF_SCOPE,
    STOP_INVARIANT_BROKEN, STOP_CRITICAL_ERROR_ADDED,
    STOP_UNKNOWN_EXECUTION_STATE, STOP_BUDGET_EXHAUSTED,
    STOP_NO_IMPROVEMENT, STOP_USER_STOP, STOP_COMPLETED,
    STOP_FAILED, STOP_BLOCKED,
)

ACTION_MOVE_COMPONENT = 'move_component'
ACTION_ROTATE_COMPONENT = 'rotate_component'
ACTION_MOVE_TEXT = 'move_text'
ACTION_MOVE_GROUP = 'move_group'
ACTION_TRACK = 'track'
ACTION_VIA = 'via'
ACTION_POUR = 'pour'
ACTION_RIP_UP = 'rip_up'
ACTION_SAVE = 'save'
ACTION_RELOAD = 'reload'
ACTION_REBUILD_POUR = 'rebuild_pour'
ALLOWED_ACTIONS = (
    ACTION_MOVE_COMPONENT, ACTION_ROTATE_COMPONENT, ACTION_MOVE_TEXT,
    ACTION_MOVE_GROUP, ACTION_TRACK, ACTION_VIA, ACTION_POUR,
    ACTION_RIP_UP, ACTION_SAVE, ACTION_RELOAD, ACTION_REBUILD_POUR,
)

INVARIANT_SCH_CONNECTIVITY = 'sch_connectivity'
INVARIANT_SCH_IDENTITY = 'sch_identity'
INVARIANT_PCB_PAD_NET = 'pcb_pad_net'
INVARIANT_PCB_OUTLINE = 'pcb_outline'
INVARIANT_PCB_LOCKED = 'pcb_locked'
INVARIANT_PCB_UNRELATED = 'pcb_unrelated'
INVARIANT_PCB_ROUTED = 'pcb_routed'
INVARIANT_DRC = 'drc'
INVARIANT_KEEPOUT = 'keepout'
INVARIANT_HOLES = 'holes'
INVARIANT_KINDS = (
    INVARIANT_SCH_CONNECTIVITY, INVARIANT_SCH_IDENTITY,
    INVARIANT_PCB_PAD_NET, INVARIANT_PCB_OUTLINE, INVARIANT_PCB_LOCKED,
    INVARIANT_PCB_UNRELATED, INVARIANT_PCB_ROUTED, INVARIANT_DRC,
    INVARIANT_KEEPOUT, INVARIANT_HOLES,
)

SEVERITY_BLOCKING = 'blocking'
SEVERITY_MAJOR = 'major'
SEVERITY_MINOR = 'minor'
SEVERITY_INFO = 'info'
SEVERITY_UNKNOWN = 'unknown'
SEVERITIES = (SEVERITY_BLOCKING, SEVERITY_MAJOR, SEVERITY_MINOR,
              SEVERITY_INFO, SEVERITY_UNKNOWN)

VERIFICATION_STRUCTURAL = 'structural'
VERIFICATION_HOST_READBACK = 'host_readback'
VERIFICATION_ERC_DRC = 'erc_drc'
VERIFICATION_SIMULATION = 'simulation'
VERIFICATION_MANUFACTURING = 'manufacturing'
VERIFICATION_PHYSICAL = 'physical'
VERIFICATION_LEVELS = (
    VERIFICATION_STRUCTURAL, VERIFICATION_HOST_READBACK,
    VERIFICATION_ERC_DRC, VERIFICATION_SIMULATION,
    VERIFICATION_MANUFACTURING, VERIFICATION_PHYSICAL,
)

STATUS_PASS = 'pass'
STATUS_FAIL = 'fail'
STATUS_WARN = 'warn'
STATUS_UNKNOWN = 'unknown'
STATUS_NOT_RUN = 'not_run'
STATUS_BLOCKED = 'blocked'

LAYER_HARD = 'hard'
LAYER_ENGINEERING = 'engineering'
LAYER_READABILITY = 'readability'
LAYERS = (LAYER_HARD, LAYER_ENGINEERING, LAYER_READABILITY)

# Observation unit semantics.  These are recorded rather than assumed so a
# consumer never silently compares raw 0.01-inch values with mil values.
UNIT_DEFAULTS = {
    'schematic_coordinate': '0.01inch',
    'schematic_y_axis': 'up',
    'pcb_coordinate': 'mil',
    'pcb_y_axis': 'up',
    'rotation': 'deg',
    'rotation_direction': 'counterclockwise',
    'mirror': 'host-native',
    'layer_ids': {'top': 1, 'bottom': 2, 'inner1': 15},
}


class ContractError(ValueError):
    """A payload does not satisfy its declared schema."""


class FeedbackError(RuntimeError):
    """A tool failure with a machine-readable class.

    Callers branch on ``failure_class``; the message is for humans.  ``detail``
    stays JSON-serialisable so it can be embedded in a report unchanged.
    """

    def __init__(self, failure_class, message, **detail):
        if failure_class not in FAILURE_CLASSES:
            raise ContractError('unknown failure class: %r' % (failure_class,))
        super().__init__(message)
        self.failure_class = failure_class
        self.message = message
        self.detail = detail

    def as_payload(self):
        return error(self.failure_class, self.message, **self.detail)


def now_utc():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def sha256_text(text):
    return hashlib.sha256((text or '').encode('utf-8', 'replace')).hexdigest()


def stable_hash(value):
    """Hash a JSON value with sorted keys and no floating-point noise."""
    text = json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False)
    return sha256_text(text)


def error(failure_class, message, **detail):
    if failure_class not in FAILURE_CLASSES:
        raise ContractError('unknown failure class: %r' % (failure_class,))
    payload = {
        'schema': SCHEMA_ERROR,
        'ok': False,
        'failure_class': failure_class,
        'message': message,
    }
    if detail:
        payload['detail'] = detail
    return payload


def _require(mapping, key, where='payload'):
    if not isinstance(mapping, dict):
        raise ContractError('%s must be an object' % where)
    if key not in mapping:
        raise ContractError('%s.%s is required' % (where, key))
    return mapping[key]


def _require_text(mapping, key, where='payload'):
    value = _require(mapping, key, where)
    if not isinstance(value, str) or not value.strip():
        raise ContractError('%s.%s must be a non-empty string' % (where, key))
    return value


def _require_list(mapping, key, where='payload'):
    value = _require(mapping, key, where)
    if not isinstance(value, list):
        raise ContractError('%s.%s must be a list' % (where, key))
    return value


def _check_schema(value, schema, where='payload'):
    if not isinstance(value, dict) or value.get('schema') != schema:
        raise ContractError('%s.schema must be %s' % (where, schema))
    return value


# ---------------------------------------------------------------------------
# capabilities
# ---------------------------------------------------------------------------

def new_capabilities(host=None, adapter=None, items=None):
    return {
        'schema': SCHEMA_CAPABILITIES,
        'generated_at': now_utc(),
        'tool_version': TOOL_VERSION,
        'host': host or {},
        'adapter': adapter or {},
        'items': items or [],
        'summary': {},
    }


def validate_capabilities(value):
    _check_schema(value, SCHEMA_CAPABILITIES, 'capabilities')
    _require_list(value, 'items', 'capabilities')
    seen = set()
    counts = {'available': 0, 'unavailable': 0, 'unknown': 0}
    for index, item in enumerate(value['items']):
        where = 'capabilities.items[%d]' % index
        ident = _require_text(item, 'id', where)
        if ident in seen:
            raise ContractError('%s.id duplicates %r' % (where, ident))
        seen.add(ident)
        status = _require_text(item, 'status', where)
        if status not in counts:
            raise ContractError('%s.status must be available/unavailable/unknown'
                                % where)
        counts[status] += 1
        if status == 'available' and not item.get('evidence'):
            raise ContractError('%s: available capability needs evidence' % where)
        if status == 'unknown' and not item.get('reason'):
            raise ContractError('%s: unknown capability needs a reason' % where)
    value['summary'] = counts
    return value


# ---------------------------------------------------------------------------
# observation
# ---------------------------------------------------------------------------

def new_observation(*, host, adapter, project, documents, units=None,
                    schematic=None, pcb=None, evidence=None,
                    degradations=None, unknown=None):
    observation = {
        'schema': SCHEMA_OBSERVATION,
        'generated_at': now_utc(),
        'tool_version': TOOL_VERSION,
        'host': host,
        'adapter': adapter,
        'project': project,
        'documents': documents,
        'units': units or dict(UNIT_DEFAULTS),
        'schematic': schematic,
        'pcb': pcb,
        'revision': {'semantic_sha256': None, 'per_document': {},
                     'captured_at': None},
        'evidence': evidence or [],
        'degradations': degradations or [],
        'unknown': unknown or [],
    }
    return observation


def validate_observation(value):
    _check_schema(value, SCHEMA_OBSERVATION, 'observation')
    _require_text(value, 'generated_at', 'observation')
    host = _require(value, 'host', 'observation')
    _require_text(host, 'window_id', 'observation.host')
    adapter = _require(value, 'adapter', 'observation')
    if not isinstance(adapter, dict) or not adapter:
        raise ContractError('observation.adapter must be a non-empty object')
    project = _require(value, 'project', 'observation')
    _require_text(project, 'uuid', 'observation.project')
    _require_text(project, 'name', 'observation.project')
    documents = _require_list(value, 'documents', 'observation')
    if not documents:
        raise ContractError('observation.documents must not be empty')
    uuids = set()
    for index, document in enumerate(documents):
        where = 'observation.documents[%d]' % index
        uuid = _require_text(document, 'uuid', where)
        _require_text(document, 'type', where)
        if uuid in uuids:
            raise ContractError('%s.uuid duplicates %r' % (where, uuid))
        uuids.add(uuid)
    units = _require(value, 'units', 'observation')
    for key in ('schematic_coordinate', 'pcb_coordinate', 'pcb_y_axis'):
        _require_text(units, key, 'observation.units')
    revision = _require(value, 'revision', 'observation')
    if revision.get('semantic_sha256') is None:
        unknown = value.get('unknown') or []
        if not any(str(entry.get('field', '')).startswith('revision')
                   for entry in unknown):
            raise ContractError('observation.revision without a hash must be '
                                'listed in unknown[]')
    for section in ('schematic', 'pcb'):
        data = value.get(section)
        if data is None:
            continue
        if not isinstance(data, dict):
            raise ContractError('observation.%s must be an object' % section)
        _require_text(data, 'document_uuid', 'observation.%s' % section)
    _require_list(value, 'evidence', 'observation')
    _require_list(value, 'degradations', 'observation')
    _require_list(value, 'unknown', 'observation')
    return value


# ---------------------------------------------------------------------------
# design intent
# ---------------------------------------------------------------------------

def new_intent(*, target, zones=None, flows=None, fixed=None,
               current_paths=None, sensitive_nodes=None,
               reference_limits=None, unknowns=None, basis=None):
    return {
        'schema': SCHEMA_INTENT,
        'generated_at': now_utc(),
        'target': target,
        'zones': zones or [],
        'flows': flows or [],
        'fixed': fixed or [],
        'current_paths': current_paths or [],
        'sensitive_nodes': sensitive_nodes or [],
        'reference_limits': reference_limits or [],
        'unknowns': unknowns or [],
        'basis': basis or [],
    }


def validate_intent(value):
    _check_schema(value, SCHEMA_INTENT, 'intent')
    _require(value, 'target', 'intent')
    for key in ('zones', 'flows', 'fixed', 'current_paths',
                'sensitive_nodes', 'reference_limits', 'unknowns', 'basis'):
        _require_list(value, key, 'intent')
    for index, zone in enumerate(value['zones']):
        where = 'intent.zones[%d]' % index
        _require_text(zone, 'id', where)
        if not zone.get('parts') and not zone.get('basis'):
            raise ContractError('%s needs parts or a stated basis' % where)
    for index, unknown in enumerate(value['unknowns']):
        where = 'intent.unknowns[%d]' % index
        _require_text(unknown, 'field', where)
        _require_text(unknown, 'reason', where)
    return value


# ---------------------------------------------------------------------------
# issue
# ---------------------------------------------------------------------------

def new_issue(*, issue_id, target, description, basis, severity,
              evidence=None, action=None, improvement=None, status='open'):
    return {
        'schema': SCHEMA_ISSUE,
        'generated_at': now_utc(),
        'id': issue_id,
        'target': target,
        'description': description,
        'basis': basis,
        'severity': severity,
        'evidence': evidence or [],
        'action': action or {},
        'improvement': improvement or {},
        'status': status,
    }


def validate_issue(value):
    _check_schema(value, SCHEMA_ISSUE, 'issue')
    _require_text(value, 'id', 'issue')
    _require(value, 'target', 'issue')
    _require_text(value, 'description', 'issue')
    basis = _require(value, 'basis', 'issue')
    if not isinstance(basis, dict):
        raise ContractError('issue.basis must be an object')
    if basis.get('deterministic') is not True:
        # A heuristic alone may still be recorded, but it cannot be blocking.
        if value.get('severity') == SEVERITY_BLOCKING:
            raise ContractError('issue: a blocking issue needs a deterministic '
                                'basis')
        if not basis.get('heuristic'):
            raise ContractError('issue.basis must state deterministic or '
                                'heuristic')
    severity = _require_text(value, 'severity', 'issue')
    if severity not in SEVERITIES:
        raise ContractError('issue.severity must be one of %s' % (SEVERITIES,))
    if not value.get('evidence'):
        raise ContractError('issue.evidence must not be empty')
    improvement = value.get('improvement') or {}
    if improvement and not improvement.get('predicate'):
        raise ContractError('issue.improvement needs a predicate')
    return value


# ---------------------------------------------------------------------------
# modification contract
# ---------------------------------------------------------------------------

def new_modification(*, contract_id, goal, target, baseline, scope,
                     allowed_actions, invariants, acceptance,
                     recovery=None, stop_conditions=None,
                     preview_only=True):
    return {
        'schema': SCHEMA_MODIFICATION,
        'generated_at': now_utc(),
        'tool_version': TOOL_VERSION,
        'id': contract_id,
        'goal': goal,
        'target': target,
        'baseline': baseline,
        'scope': scope,
        'allowed_actions': allowed_actions,
        'invariants': invariants,
        'acceptance': acceptance,
        'recovery': recovery or {},
        'stop_conditions': stop_conditions or list(STOP_REASONS),
        'preview_only': bool(preview_only),
    }


def validate_modification(value):
    _check_schema(value, SCHEMA_MODIFICATION, 'contract')
    _require_text(value, 'id', 'contract')
    _require_text(value, 'goal', 'contract')
    target = _require(value, 'target', 'contract')
    _require_text(target, 'project_uuid', 'contract.target')
    _require_list(target, 'documents', 'contract.target')
    if not target['documents']:
        raise ContractError('contract.target.documents must not be empty')
    baseline = _require(value, 'baseline', 'contract')
    if not baseline.get('semantic_sha256') and not baseline.get('unknown_reason'):
        raise ContractError('contract.baseline needs semantic_sha256 or an '
                            'unknown_reason')
    scope = _require(value, 'scope', 'contract')
    writable = _require(scope, 'writable', 'contract.scope')
    if not isinstance(writable, dict):
        raise ContractError('contract.scope.writable must be an object')
    if not any(writable.get(key) for key in ('objects', 'regions', 'nets')):
        raise ContractError('contract.scope.writable must name objects, regions '
                            'or nets')
    checkable = scope.get('checkable')
    if checkable is not None and not isinstance(checkable, dict):
        raise ContractError('contract.scope.checkable must be an object')
    actions = _require_list(value, 'allowed_actions', 'contract')
    if not actions:
        raise ContractError('contract.allowed_actions must not be empty')
    for action in actions:
        if action not in ALLOWED_ACTIONS:
            raise ContractError('contract.allowed_actions: unknown action %r'
                                % (action,))
    invariants = _require_list(value, 'invariants', 'contract')
    if not invariants:
        raise ContractError('contract.invariants must not be empty')
    for index, invariant in enumerate(invariants):
        where = 'contract.invariants[%d]' % index
        _require_text(invariant, 'id', where)
        kind = _require_text(invariant, 'kind', where)
        if kind not in INVARIANT_KINDS:
            raise ContractError('%s.kind %r is not supported' % (where, kind))
    acceptance = _require_list(value, 'acceptance', 'contract')
    if not acceptance:
        raise ContractError('contract.acceptance must not be empty')
    for index, item in enumerate(acceptance):
        where = 'contract.acceptance[%d]' % index
        _require_text(item, 'id', where)
        _require_text(item, 'metric', where)
        _require_text(item, 'predicate', where)
    stop = _require_list(value, 'stop_conditions', 'contract')
    for reason in stop:
        if reason not in STOP_REASONS:
            raise ContractError('contract.stop_conditions: unknown reason %r'
                                % (reason,))
    if value.get('preview_only') not in (True, False):
        raise ContractError('contract.preview_only must be a boolean')
    return value


def assert_writable(contract):
    """Refuse a write unless the contract was explicitly cleared for writes."""
    validate_modification(contract)
    if contract.get('preview_only') is True:
        raise ContractError('contract is preview_only: writes are not allowed')


# ---------------------------------------------------------------------------
# loop state
# ---------------------------------------------------------------------------

def new_loop(*, loop_id, goal, target, budgets=None):
    return {
        'schema': SCHEMA_LOOP,
        'loop_id': loop_id,
        'created_at': now_utc(),
        'updated_at': now_utc(),
        'goal': goal,
        'target': target,
        'stage': STAGE_OBSERVE,
        'history': [{'stage': STAGE_OBSERVE, 'at': now_utc()}],
        'budgets': budgets or {
            'max_rounds': 4,
            'max_no_improvement': 2,
            'timeout_sec': 600,
            'max_calls': 200,
            'calls_used': 0,
        },
        'rounds': [],
        'issues': [],
        'stop': None,
        'result': None,
        'recovery': None,
    }


def transition_loop(state, stage):
    validate_loop(state)
    current = state['stage']
    if stage not in TRANSITIONS.get(current, ()):
        raise ContractError('illegal transition %s -> %s' % (current, stage))
    state['stage'] = stage
    state['updated_at'] = now_utc()
    state['history'].append({'stage': stage, 'at': state['updated_at']})
    return state


def validate_loop(state):
    _check_schema(state, SCHEMA_LOOP, 'loop')
    _require_text(state, 'loop_id', 'loop')
    _require_text(state, 'goal', 'loop')
    stage = _require_text(state, 'stage', 'loop')
    if stage not in STAGES:
        raise ContractError('loop.stage must be one of %s' % (STAGES,))
    budgets = _require(state, 'budgets', 'loop')
    for key in ('max_rounds', 'max_no_improvement', 'timeout_sec', 'max_calls'):
        if not isinstance(budgets.get(key), int) or budgets[key] < 0:
            raise ContractError('loop.budgets.%s must be a nonnegative integer'
                                % key)
    if not isinstance(state.get('rounds'), list):
        raise ContractError('loop.rounds must be a list')
    for index, round_ in enumerate(state['rounds']):
        where = 'loop.rounds[%d]' % index
        for key in ('n', 'stage', 'started_at'):
            _require(round_, key, where)
        if round_.get('stage') not in STAGES:
            raise ContractError('%s.stage is invalid' % where)
    return state


# ---------------------------------------------------------------------------
# evaluation / candidate comparison
# ---------------------------------------------------------------------------

def new_evaluation(*, target, layers, confirmed_issues=None,
                   conditional_risks=None, suggestions=None, unknown=None):
    return {
        'schema': SCHEMA_EVALUATION,
        'generated_at': now_utc(),
        'tool_version': TOOL_VERSION,
        'target': target,
        'layers': layers,
        'confirmed_issues': confirmed_issues or [],
        'conditional_risks': conditional_risks or [],
        'suggestions': suggestions or [],
        'unknown': unknown or [],
        'drc_zero_but_quality_issues': False,
        'verdict': STATUS_UNKNOWN,
        'total_score': None,
        'note': 'no total score: a hard failure is never offset by other layers',
    }


def validate_evaluation(value):
    _check_schema(value, SCHEMA_EVALUATION, 'evaluation')
    layers = _require(value, 'layers', 'evaluation')
    for name in LAYERS:
        layer = _require(layers, name, 'evaluation.layers')
        status = _require_text(layer, 'status', 'evaluation.layers.%s' % name)
        if status not in (STATUS_PASS, STATUS_FAIL, STATUS_WARN, STATUS_UNKNOWN,
                          STATUS_NOT_RUN):
            raise ContractError('evaluation.layers.%s.status invalid' % name)
        if not isinstance(layer.get('findings'), list):
            raise ContractError('evaluation.layers.%s.findings must be a list'
                                % name)
    hard = layers['hard']['status']
    if hard == STATUS_FAIL and value.get('verdict') != STATUS_FAIL:
        raise ContractError('evaluation: a hard failure cannot have verdict %r'
                            % (value.get('verdict'),))
    if value.get('total_score') is not None:
        raise ContractError('evaluation must not expose a total score')
    for key in ('confirmed_issues', 'conditional_risks', 'suggestions',
                'unknown'):
        _require_list(value, key, 'evaluation')
    return value


def new_candidate_comparison(*, target, candidates, selected=None,
                             rejected=None):
    return {
        'schema': SCHEMA_CANDIDATE_COMPARISON,
        'generated_at': now_utc(),
        'target': target,
        'candidates': candidates,
        'selected': selected,
        'rejected': rejected or [],
        'basis': 'hard constraints first; key metrics only where comparable',
    }


def validate_candidate_comparison(value):
    _check_schema(value, SCHEMA_CANDIDATE_COMPARISON, 'comparison')
    _require_list(value, 'candidates', 'comparison')
    if not value['candidates']:
        raise ContractError('comparison.candidates must not be empty')
    for index, candidate in enumerate(value['candidates']):
        where = 'comparison.candidates[%d]' % index
        _require_text(candidate, 'id', where)
        hard = _require(candidate, 'hard', where)
        if hard.get('status') not in (STATUS_PASS, STATUS_FAIL, STATUS_UNKNOWN):
            raise ContractError('%s.hard.status invalid' % where)
        if hard.get('status') == STATUS_FAIL and value.get('selected') == \
                candidate.get('id'):
            raise ContractError('%s: a hard-failing candidate cannot be '
                                'selected' % where)
    return value


# ---------------------------------------------------------------------------
# cases
# ---------------------------------------------------------------------------

CASE_REQUIRED_FIELDS = (
    'id', 'version', 'goal', 'applies_when', 'does_not_apply_when',
    'inputs', 'provenance', 'tool_versions', 'original_problem', 'method',
    'before_after', 'check_method', 'evidence', 'verification_levels',
    'limits', 'failed_attempts', 'invalidation_conditions', 'source_tier',
)


def new_case(**fields):
    payload = {
        'schema': SCHEMA_CASE,
        'created_at': now_utc(),
        'tool_version': TOOL_VERSION,
    }
    payload.update(fields)
    return payload


def validate_case(value):
    _check_schema(value, SCHEMA_CASE, 'case')
    for field in CASE_REQUIRED_FIELDS:
        _require(value, field, 'case')
    if value['source_tier'] not in ('project-local', 'reusable', 'candidate-rule'):
        raise ContractError('case.source_tier invalid')
    levels = value['verification_levels']
    if not isinstance(levels, dict):
        raise ContractError('case.verification_levels must be an object')
    for level in VERIFICATION_LEVELS:
        entry = levels.get(level)
        if entry is None:
            continue
        if not isinstance(entry, dict):
            raise ContractError('case.verification_levels.%s must be an object'
                                % level)
        status = entry.get('status')
        if status not in (STATUS_PASS, STATUS_FAIL, STATUS_NOT_RUN,
                          STATUS_UNKNOWN):
            raise ContractError('case.verification_levels.%s.status invalid'
                                % level)
        if status == STATUS_PASS and not entry.get('evidence'):
            raise ContractError('case.verification_levels.%s: a pass needs '
                                'evidence' % level)
    if not value['verification_levels']:
        raise ContractError('case.verification_levels must not be empty')
    return value


def new_case_query(**filters):
    payload = {
        'schema': SCHEMA_CASE_QUERY,
        'generated_at': now_utc(),
        'filters': filters,
    }
    return payload


def validate_case_query(value):
    _check_schema(value, SCHEMA_CASE_QUERY, 'query')
    filters = _require(value, 'filters', 'query')
    if not isinstance(filters, dict):
        raise ContractError('query.filters must be an object')
    return value


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------

def ok_payload(schema, **fields):
    payload = {'schema': schema, 'ok': True, 'tool_version': TOOL_VERSION,
               'generated_at': now_utc()}
    payload.update(fields)
    return payload
