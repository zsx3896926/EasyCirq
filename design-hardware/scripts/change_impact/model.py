"""Versioned input contract, strict validation and the normalized model.

The model is a *declared* object graph: nodes carry per-side attributes and
edges carry a semantic.  Validation is intentionally unforgiving about the
things that decide whether an answer is evidence or a guess:

* every ID is unique and namespaced by its object type;
* every dependency, change, constraint, coverage entry and evidence record
  points at an object that actually exists;
* ``before``/``after`` in a change must match the declared model values, so a
  hand-written claim cannot silently contradict the snapshot;
* non-finite numbers, ``bool`` costs, negative budgets and duplicate
  contradictory changes are rejected;
* a partial snapshot may not claim to be complete.

Absent information is stored as ``unknown``; it is never replaced by an empty
list or by "no impact".
"""
from __future__ import annotations

import json
from pathlib import Path

from . import (
    CHANGE_KINDS,
    CHECK_KINDS,
    DEPENDENCY_CERTAINTY,
    DEPENDENCY_SEMANTICS,
    OBJECT_KINDS,
    SCHEMA_MODEL,
    TOOL_VERSION,
)
from . import canonical as canon
from .errors import InputInvalid, issue

MISSING = object()
"""Sentinel for an attribute that is absent on one side of the snapshot."""

ID_PREFIX = {
    'component_instance': 'cmp',
    'pin': 'pin',
    'net': 'net',
    'power_domain': 'pwr',
    'interface': 'if',
    'layout_region': 'region',
    'mechanical_anchor': 'anchor',
    'bom_line': 'bom',
    'firmware_contract': 'fw',
    'test': 'test',
    'artifact': 'art',
    'requirement': 'req',
    'document': 'doc',
}

CONSTRAINT_KINDS = (
    'voltage_range',
    'current_limit',
    'io_level',
    'mechanical_clearance',
    'timing',
    'impedance',
    'critical_net',
    'thermal',
    'custom',
)

SNAPSHOT_SOURCES = (
    'normalized_model',
    'feedback_observation',
    'design_engine_ir',
    'snapshot_json',
    'simulated_synthetic',
)

CHANGE_TYPES = ('modify', 'add', 'remove')

# Attribute paths that are safe to treat as a *display* change.  Anything not
# matched here is classified as ``unknown_attribute``; it is never folded into
# ``display_only`` by default.
DISPLAY_PREFIXES = (
    'display.', 'annotation.', 'text_style.', 'label_offset.',
    'silk_text.', 'visual.', 'doc_note.',
)

# Attribute paths (or prefixes) that carry a well-defined meaning.
ATTRIBUTE_CLASSES = (
    ('identity', ('mpn', 'manufacturer', 'lcsc', 'device.uuid',
                  'instance_uuid', 'part_number', 'instance.identity')),
    ('footprint', ('footprint.', 'package.', 'symbol.')),
    ('power', ('power.', 'supply.', 'voltage', 'current', 'rail.',
               'voltage_range.', 'current_requirement.')),
    ('parameter', ('value', 'resistance', 'capacitance', 'inductance',
                   'tolerance', 'rating.', 'parameters.', 'derating.')),
    ('pin', ('pins.', 'pin.', 'pinout.', 'pin_function')),
    ('connectivity', ('net', 'nets', 'connectivity.', 'electrical.')),
    ('pose', ('placement.', 'position.', 'rotation', 'mirror', 'pose.')),
    ('layer', ('layer', 'layers.', 'stackup.')),
    ('outline', ('board.outline', 'outline', 'hole', 'holes',
                 'mounting_hole', 'board_frame', 'edge.')),
    ('delivery', ('dnp', 'bom.', 'assembly.', 'variant.', 'delivery.',
                  'fitted', 'population.')),
    ('firmware', ('firmware.', 'peripheral.', 'register.', 'clock.',
                  'io_contract.', 'io_voltage')),
    ('test', ('test.', 'limit.', 'threshold.', 'acceptance.', 'criterion')),
    ('requirement', ('requirement.', 'requirement_id', 'trace.')),
    ('document', ('document.', 'title_block.', 'revision', 'sheet.',
                  'designator', 'net_name', 'name')),
)

_KIND_BY_CLASS = {
    'identity': 'component_identity',
    'footprint': 'footprint',
    'power': 'power_requirement',
    'parameter': 'parameter',
    'pin': 'pin_mapping',
    'connectivity': 'connectivity',
    'pose': 'mechanical_pose',
    'layer': 'layer_stack',
    'outline': 'board_outline',
    'delivery': 'delivery_config',
    'firmware': 'firmware_contract',
    'test': 'test_criterion',
    'requirement': 'requirement',
    'document': 'document_metadata',
}

DEFAULT_BUDGET = {
    'max_depth': 8,
    'max_paths': 500,
    'max_cost': 1000.0,
    'max_checks': None,
}

MAX_INPUT_BYTES = 32 * 1024 * 1024


# ---------------------------------------------------------------------------
# small validators
# ---------------------------------------------------------------------------

def _text(value, where, *, allow_empty=False, code='invalid_text'):
    return canon.text(value, where=where, allow_empty=allow_empty, code=code)


def _mapping(value, where, code='invalid_object'):
    return canon.mapping(value, where=where, code=code)


def _list(value, where, code='invalid_list'):
    return canon.list_of(value, where=where, code=code)


def _optional_list(parent, key, where, code='invalid_list'):
    if key not in parent or parent[key] is None:
        return []
    return _list(parent[key], f'{where}.{key}', code=code)


def _reject_path_like(value, where):
    """Model content may not point outside the snapshot with a file path."""
    if not isinstance(value, str):
        return
    stripped = value.strip()
    if stripped.startswith(('/', '\\')) or (len(stripped) > 1 and stripped[1] == ':'):
        raise InputInvalid(f'{where}: absolute filesystem paths are not allowed '
                           f'in a model', code='path_traversal', where=where)
    for segment in stripped.replace('\\', '/').split('/'):
        if segment == '..':
            raise InputInvalid(f'{where}: path traversal is not allowed',
                               code='path_traversal', where=where)


def _walk_paths(value, where):
    """Reject path-like strings in any field whose name suggests a file."""
    if isinstance(value, dict):
        for key in sorted(value):
            child = f'{where}.{key}'
            if key in ('path', 'file', 'file_path', 'source_path',
                       'snapshot_path', 'artifact_path'):
                _reject_path_like(value[key], child)
            _walk_paths(value[key], child)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _walk_paths(item, f'{where}[{index}]')


def json_equal(first, second):
    """Numeric-aware deep equality (``5`` equals ``5.0``, ``True`` never does)."""
    if isinstance(first, bool) or isinstance(second, bool):
        return type(first) is type(second) and first == second
    if canon.is_finite_number(first) and canon.is_finite_number(second):
        return float(first) == float(second)
    if isinstance(first, dict) and isinstance(second, dict):
        if set(first) != set(second):
            return False
        return all(json_equal(first[key], second[key]) for key in first)
    if isinstance(first, list) and isinstance(second, list):
        return len(first) == len(second) and all(
            json_equal(a, b) for a, b in zip(first, second))
    return type(first) is type(second) and first == second


# ---------------------------------------------------------------------------
# attribute paths
# ---------------------------------------------------------------------------

def split_path(path):
    if not isinstance(path, str) or not path:
        raise InputInvalid('attribute path must be a non-empty string',
                           code='invalid_attribute_path', where='attribute')
    parts = path.split('.')
    for part in parts:
        if not part:
            raise InputInvalid(f'attribute path {path!r} contains an empty segment',
                               code='invalid_attribute_path', where='attribute')
    return parts


def lookup(attributes, path):
    """Return the value at ``path`` or :data:`MISSING`."""
    current = attributes
    for part in split_path(path):
        if not isinstance(current, dict) or part not in current:
            return MISSING
        current = current[part]
    return current


# ---------------------------------------------------------------------------
# loading
# ---------------------------------------------------------------------------

def load_json_file(path, *, where='input'):
    """Read strict UTF-8 JSON, rejecting duplicate keys and non-finite values."""
    file_path = Path(path)
    try:
        size = file_path.stat().st_size
    except OSError as exc:
        raise InputInvalid(f'{where}: cannot stat {file_path}: {exc}',
                           code='input_unreadable', where=where)
    if size > MAX_INPUT_BYTES:
        raise InputInvalid(f'{where}: input exceeds {MAX_INPUT_BYTES} bytes',
                           code='input_too_large', where=where)
    try:
        text = file_path.read_text(encoding='utf-8-sig')
    except OSError as exc:
        raise InputInvalid(f'{where}: cannot read {file_path}: {exc}',
                           code='input_unreadable', where=where)

    def _pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise InputInvalid(f'{where}: duplicate JSON key {key!r}',
                                   code='duplicate_json_key', where=where)
            result[key] = value
        return result

    def _constant(name):
        raise InputInvalid(f'{where}: non-finite number {name} is not allowed',
                           code='non_finite_number', where=where)

    try:
        value = json.loads(text, object_pairs_hook=_pairs,
                           parse_constant=_constant)
    except json.JSONDecodeError as exc:
        raise InputInvalid(f'{where}: invalid JSON at line {exc.lineno} '
                           f'column {exc.colno}', code='invalid_json', where=where)
    if not isinstance(value, dict):
        raise InputInvalid(f'{where}: the top-level JSON value must be an object',
                           code='invalid_json', where=where)
    return value


# ---------------------------------------------------------------------------
# snapshot
# ---------------------------------------------------------------------------

def _validate_snapshot(value, where, model_kinds):
    record = _mapping(value, where)
    result = {}
    for key in ('project', 'document', 'revision'):
        result[key] = _text(record.get(key), f'{where}.{key}')
    result['content_hash'] = canon.normalize_hash(
        record.get('content_hash'), where=f'{where}.content_hash')
    source = _text(record.get('source_type'), f'{where}.source_type')
    if source not in SNAPSHOT_SOURCES:
        raise InputInvalid(
            f'{where}.source_type: must be one of {", ".join(SNAPSHOT_SOURCES)}',
            code='invalid_snapshot_source', where=f'{where}.source_type')
    result['source_type'] = source
    scope = _list(record.get('snapshot_scope'), f'{where}.snapshot_scope')
    normalized_scope = []
    for index, kind in enumerate(scope):
        kind_where = f'{where}.snapshot_scope[{index}]'
        kind = _text(kind, kind_where)
        if kind not in OBJECT_KINDS and kind != 'dependencies':
            raise InputInvalid(f'{kind_where}: unknown snapshot scope {kind!r}',
                               code='unknown_object_kind', where=kind_where)
        if kind in normalized_scope:
            raise InputInvalid(f'{kind_where}: duplicate scope {kind!r}',
                               code='duplicate_scope', where=kind_where)
        normalized_scope.append(kind)
    result['snapshot_scope'] = sorted(normalized_scope)
    missing = _optional_list(record, 'missing_fields', where)
    result['missing_fields'] = sorted(_text(item, f'{where}.missing_fields[{i}]')
                                      for i, item in enumerate(missing))
    if 'complete' in record:
        if type(record['complete']) is not bool:
            raise InputInvalid(f'{where}.complete: a boolean is required',
                               code='invalid_boolean', where=f'{where}.complete')
        result['complete'] = record['complete']
    else:
        result['complete'] = False
    if result['complete'] and result['missing_fields']:
        raise InputInvalid(
            f'{where}: snapshot claims to be complete but lists missing fields '
            f'{result["missing_fields"]}',
            code='partial_snapshot_claimed_complete', where=where)
    if result['complete']:
        uncovered = [kind for kind in model_kinds if kind not in result['snapshot_scope']]
        if uncovered:
            raise InputInvalid(
                f'{where}: snapshot claims to be complete but scope omits object '
                f'kinds present in the model: {uncovered}',
                code='partial_snapshot_claimed_complete', where=where)
    result['notes'] = _text(record.get('notes'), f'{where}.notes',
                            allow_empty=True) if 'notes' in record else ''
    return result


# ---------------------------------------------------------------------------
# objects
# ---------------------------------------------------------------------------

def _validate_object(value, where):
    record = _mapping(value, where)
    identity = _text(record.get('id'), f'{where}.id')
    if ':' not in identity:
        raise InputInvalid(f'{where}.id: an object id must be <kind-prefix>:<name>',
                           code='untyped_object_id', where=f'{where}.id')
    prefix, _, name = identity.partition(':')
    if not name:
        raise InputInvalid(f'{where}.id: empty object name', code='untyped_object_id',
                           where=f'{where}.id')
    kind = _text(record.get('kind'), f'{where}.kind')
    if kind not in OBJECT_KINDS:
        raise InputInvalid(f'{where}.kind: must be one of {", ".join(OBJECT_KINDS)}',
                           code='unknown_object_kind', where=f'{where}.kind')
    expected = ID_PREFIX[kind]
    if prefix != expected:
        raise InputInvalid(
            f'{where}.id: {identity!r} is typed {prefix!r} but kind is {kind!r} '
            f'(expected prefix {expected!r})',
            code='object_type_conflict', where=f'{where}.id')
    attributes = _mapping(record.get('attributes', {}), f'{where}.attributes')
    baseline_attributes = None
    if 'baseline_attributes' in record:
        baseline_attributes = _mapping(record['baseline_attributes'],
                                       f'{where}.baseline_attributes')
        for key in sorted(baseline_attributes):
            if key in attributes and json_equal(baseline_attributes[key],
                                                attributes[key]):
                raise InputInvalid(
                    f'{where}.baseline_attributes.{key}: identical to attributes; '
                    f'only differing baseline values may be listed',
                    code='redundant_baseline_attribute',
                    where=f'{where}.baseline_attributes.{key}')
    present = record.get('present')
    present_record = {'baseline': True, 'candidate': True}
    if present is not None:
        present = _mapping(present, f'{where}.present')
        for side in ('baseline', 'candidate'):
            if side not in present:
                continue
            if type(present[side]) is not bool:
                raise InputInvalid(f'{where}.present.{side}: a boolean is required',
                                   code='invalid_boolean',
                                   where=f'{where}.present.{side}')
            present_record[side] = present[side]
        if not present_record['baseline'] and not present_record['candidate']:
            raise InputInvalid(f'{where}.present: an object cannot be absent on '
                               f'both sides', code='object_absent_everywhere',
                               where=f'{where}.present')
    _walk_paths(attributes, f'{where}.attributes')
    if baseline_attributes is not None:
        _walk_paths(baseline_attributes, f'{where}.baseline_attributes')
    simulated = record.get('simulated', False)
    if type(simulated) is not bool:
        raise InputInvalid(f'{where}.simulated: a boolean is required',
                           code='invalid_boolean', where=f'{where}.simulated')
    provenance = record.get('provenance', {})
    provenance = _mapping(provenance, f'{where}.provenance') if provenance else {}
    _walk_paths(provenance, f'{where}.provenance')
    label = record.get('display_name')
    if label is not None:
        label = _text(label, f'{where}.display_name')
    return {
        'id': identity,
        'kind': kind,
        'display_name': label,
        'attributes': canon.canonical_value(attributes, where=f'{where}.attributes'),
        'baseline_attributes': (canon.canonical_value(
            baseline_attributes, where=f'{where}.baseline_attributes')
            if baseline_attributes is not None else None),
        'present': present_record,
        'simulated': simulated,
        'provenance': canon.canonical_value(provenance, where=f'{where}.provenance'),
        'raw': record,
    }


def _attr(record, path, side):
    """Value of ``path`` on one side, using baseline overrides."""
    present = record['present'][side]
    if not present:
        return MISSING
    overrides = record['baseline_attributes'] if side == 'baseline' else None
    if side == 'baseline':
        parts = split_path(path)
        if overrides:
            if parts[0] in overrides:
                if len(parts) == 1:
                    return overrides[parts[0]]
                value = lookup(overrides[parts[0]], '.'.join(parts[1:]))
                if value is not MISSING:
                    return value
    return lookup(record['attributes'], path)


# ---------------------------------------------------------------------------
# dependencies
# ---------------------------------------------------------------------------

def _validate_dependency(value, where):
    record = _mapping(value, where)
    identity = _text(record.get('id'), f'{where}.id')
    if not identity.startswith('dep:'):
        raise InputInvalid(f'{where}.id: a dependency id must start with "dep:"',
                           code='invalid_dependency_id', where=f'{where}.id')
    result = {
        'id': identity,
        'from': _text(record.get('from'), f'{where}.from'),
        'to': _text(record.get('to'), f'{where}.to'),
    }
    semantic = _text(record.get('semantic'), f'{where}.semantic')
    if semantic not in DEPENDENCY_SEMANTICS:
        raise InputInvalid(
            f'{where}.semantic: must be one of {", ".join(DEPENDENCY_SEMANTICS)}',
            code='unknown_dependency_semantic', where=f'{where}.semantic')
    result['semantic'] = semantic
    direction = record.get('direction', 'forward')
    if direction not in ('forward', 'bidirectional'):
        raise InputInvalid(
            f'{where}.direction: must be "forward" or "bidirectional"',
            code='unknown_dependency_direction', where=f'{where}.direction')
    result['direction'] = direction
    conditions = _optional_list(record, 'conditions', where)
    result['conditions'] = sorted(
        _text(item, f'{where}.conditions[{index}]')
        for index, item in enumerate(conditions))
    certainty = record.get('certainty', 'declared')
    if certainty not in DEPENDENCY_CERTAINTY:
        raise InputInvalid(
            f'{where}.certainty: must be one of {", ".join(DEPENDENCY_CERTAINTY)}',
            code='unknown_certainty', where=f'{where}.certainty')
    result['certainty'] = certainty
    evidence = record.get('evidence')
    if evidence is not None:
        evidence = _mapping(evidence, f'{where}.evidence')
        _walk_paths(evidence, f'{where}.evidence')
        simulated = evidence.get('simulated', False)
        if type(simulated) is not bool:
            raise InputInvalid(f'{where}.evidence.simulated: a boolean is required',
                               code='invalid_boolean', where=f'{where}.evidence.simulated')
        evidence = canon.canonical_value(evidence, where=f'{where}.evidence')
    result['evidence'] = evidence
    result['note'] = record.get('note', '')
    return result


# ---------------------------------------------------------------------------
# changes
# ---------------------------------------------------------------------------

def classify_attribute(object_kind, path):
    """Map ``(kind, attribute path)`` to ``(change_kind, sub_label)``.

    Returns ``('unknown_attribute', None)`` for anything not explicitly
    understood; that is a deliberate, visible outcome, not a fallback to
    ``display_only``.
    """
    if path is None:
        return None, None
    lowered = str(path).lower()
    for prefix in DISPLAY_PREFIXES:
        if lowered.startswith(prefix):
            return 'display_only', 'drawing_text'
    for label, prefixes in ATTRIBUTE_CLASSES:
        for prefix in prefixes:
            if lowered == prefix or lowered.startswith(prefix + '.') or \
                    lowered.startswith(prefix) and prefix.endswith(('.', '_')):
                return _KIND_BY_CLASS[label], label
    return 'unknown_attribute', None


def _validate_change(value, where):
    record = _mapping(value, where)
    identity = _text(record.get('id'), f'{where}.id')
    if not identity.startswith('chg:'):
        raise InputInvalid(f'{where}.id: a change id must start with "chg:"',
                           code='invalid_change_id', where=f'{where}.id')
    result = {'id': identity}
    change_type = record.get('change_type', 'modify')
    if change_type not in CHANGE_TYPES:
        raise InputInvalid(f'{where}.change_type: must be one of '
                           f'{", ".join(CHANGE_TYPES)}',
                           code='invalid_change_type', where=f'{where}.change_type')
    result['change_type'] = change_type
    declared_kind = record.get('kind')
    if declared_kind is not None and declared_kind not in CHANGE_KINDS:
        raise InputInvalid(
            f'{where}.kind: unknown change kind {declared_kind!r}',
            code='unknown_change_kind', where=f'{where}.kind')
    result['declared_kind'] = declared_kind
    object_id = record.get('object')
    result['object'] = _text(object_id, f'{where}.object') if object_id else None
    attribute = record.get('attribute')
    if attribute is not None:
        attribute = _text(attribute, f'{where}.attribute')
        split_path(attribute)
    result['attribute'] = attribute
    if 'before' not in record:
        raise InputInvalid(f'{where}.before: an explicit value is required '
                           f'(use null for an added attribute)',
                           code='missing_before_value', where=f'{where}.before')
    if 'after' not in record:
        raise InputInvalid(f'{where}.after: an explicit value is required '
                           f'(use null for a removed attribute)',
                           code='missing_after_value', where=f'{where}.after')
    result['before'] = canon.canonical_value(record['before'], where=f'{where}.before')
    result['after'] = canon.canonical_value(record['after'], where=f'{where}.after')
    if change_type == 'modify' and json_equal(result['before'], result['after']):
        raise InputInvalid(f'{where}: a modify change with identical before/after '
                           f'is not a change', code='no_op_change', where=where)
    authorized = record.get('authorized')
    if authorized is None:
        result['authorized'] = False
        result['authorization_source'] = 'not_declared'
    else:
        if type(authorized) is not bool:
            raise InputInvalid(f'{where}.authorized: a boolean is required',
                               code='invalid_boolean', where=f'{where}.authorized')
        result['authorized'] = authorized
        result['authorization_source'] = 'declared'
    scope = record.get('authorized_scope')
    if scope is None:
        result['authorized_scope'] = None
    else:
        scope = _mapping(scope, f'{where}.authorized_scope')
        objects = _optional_list(scope, 'objects', f'{where}.authorized_scope')
        attributes = _optional_list(scope, 'attributes', f'{where}.authorized_scope')
        regions = _optional_list(scope, 'regions', f'{where}.authorized_scope')
        result['authorized_scope'] = {
            'objects': sorted(_text(item, f'{where}.authorized_scope.objects[{i}]')
                              for i, item in enumerate(objects)),
            'attributes': sorted(_text(item, f'{where}.authorized_scope.attributes[{i}]')
                                 for i, item in enumerate(attributes)),
            'regions': sorted(_text(item, f'{where}.authorized_scope.regions[{i}]')
                              for i, item in enumerate(regions)),
        }
    source = record.get('source')
    if source is None:
        result['source'] = {'type': 'declared'}
    else:
        source = _mapping(source, f'{where}.source')
        source_type = source.get('type', 'declared')
        if source_type not in ('declared', 'derived', 'observed'):
            raise InputInvalid(f'{where}.source.type: must be declared, derived '
                               f'or observed', code='invalid_change_source',
                               where=f'{where}.source.type')
        result['source'] = {'type': source_type,
                            'ref': _text(source.get('ref'), f'{where}.source.ref',
                                         allow_empty=True)
                            if 'ref' in source else ''}
    conditions = _optional_list(record, 'conditions', where)
    result['conditions'] = sorted(
        _text(item, f'{where}.conditions[{index}]')
        for index, item in enumerate(conditions))
    note = record.get('note', '')
    result['note'] = _text(note, f'{where}.note', allow_empty=True) if note else ''
    return result


# ---------------------------------------------------------------------------
# constraints, catalog, evidence
# ---------------------------------------------------------------------------

def _validate_constraint(value, where):
    record = _mapping(value, where)
    result = {
        'id': _text(record.get('id'), f'{where}.id'),
        'kind': _text(record.get('kind'), f'{where}.kind'),
        'object': _text(record.get('object'), f'{where}.object'),
        'value': canon.canonical_value(record.get('value'), where=f'{where}.value'),
        'source': _text(record.get('source'), f'{where}.source'),
    }
    if not result['id'].startswith('con:'):
        raise InputInvalid(f'{where}.id: a constraint id must start with "con:"',
                           code='invalid_constraint_id', where=f'{where}.id')
    if result['kind'] not in CONSTRAINT_KINDS:
        raise InputInvalid(
            f'{where}.kind: must be one of {", ".join(CONSTRAINT_KINDS)}',
            code='unknown_constraint_kind', where=f'{where}.kind')
    if 'attribute' in record and record['attribute'] is not None:
        result['attribute'] = _text(record['attribute'], f'{where}.attribute')
        split_path(result['attribute'])
    else:
        result['attribute'] = None
    hard = record.get('hard', False)
    if type(hard) is not bool:
        raise InputInvalid(f'{where}.hard: a boolean is required',
                           code='invalid_boolean', where=f'{where}.hard')
    result['hard'] = hard
    result['note'] = record.get('note', '')
    return result


def _validate_check(value, where):
    record = _mapping(value, where)
    result = {
        'id': _text(record.get('id'), f'{where}.id'),
        'title': _text(record.get('title'), f'{where}.title'),
        'kind': _text(record.get('kind'), f'{where}.kind'),
    }
    if not result['id'].startswith('chk:'):
        raise InputInvalid(f'{where}.id: a check id must start with "chk:"',
                           code='invalid_check_id', where=f'{where}.id')
    if result['kind'] not in CHECK_KINDS:
        raise InputInvalid(f'{where}.kind: must be one of {", ".join(CHECK_KINDS)}',
                           code='unknown_check_kind', where=f'{where}.kind')
    result['cost'] = canon.positive_number(record.get('cost'), where=f'{where}.cost',
                                           code='invalid_cost', allow_zero=True)
    mandatory = record.get('mandatory', False)
    if type(mandatory) is not bool:
        raise InputInvalid(f'{where}.mandatory: a boolean is required',
                           code='invalid_boolean', where=f'{where}.mandatory')
    result['mandatory'] = mandatory
    approval = record.get('approval', False)
    if type(approval) is not bool:
        raise InputInvalid(f'{where}.approval: a boolean is required',
                           code='invalid_boolean', where=f'{where}.approval')
    result['approval'] = approval
    result['module'] = _text(record.get('module', 'unknown'), f'{where}.module',
                             allow_empty=True)
    covers = _optional_list(record, 'covers', where)
    result['covers'] = []
    for index, item in enumerate(covers):
        item_where = f'{where}.covers[{index}]'
        item = _mapping(item, item_where)
        object_id = item.get('object')
        if object_id is not None:
            object_id = _text(object_id, f'{item_where}.object')
        impact = item.get('impact')
        if impact is not None:
            impact = _text(impact, f'{item_where}.impact')
            from . import IMPACT_KINDS
            if impact not in IMPACT_KINDS:
                raise InputInvalid(f'{item_where}.impact: unknown impact kind '
                                   f'{impact!r}', code='unknown_impact_kind',
                                   where=f'{item_where}.impact')
        attribute = item.get('attribute')
        if attribute is not None:
            attribute = _text(attribute, f'{item_where}.attribute')
        if object_id is None and impact is None:
            raise InputInvalid(f'{item_where}: a coverage entry needs an object '
                               f'or an impact kind',
                               code='empty_coverage_entry', where=item_where)
        result['covers'].append({'object': object_id, 'impact': impact,
                                 'attribute': attribute})
    requires = _optional_list(record, 'requires', where)
    result['requires'] = sorted(_text(item, f'{where}.requires[{i}]')
                                for i, item in enumerate(requires))
    inputs = _optional_list(record, 'requires_inputs', where)
    result['requires_inputs'] = sorted(
        _text(item, f'{where}.requires_inputs[{i}]')
        for i, item in enumerate(inputs))
    runnable = record.get('runnable_offline')
    if runnable is None:
        runnable = result['kind'] == 'offline'
    if type(runnable) is not bool:
        raise InputInvalid(f'{where}.runnable_offline: a boolean is required',
                           code='invalid_boolean', where=f'{where}.runnable_offline')
    result['runnable_offline'] = runnable
    result['note'] = record.get('note', '')
    return result


def _validate_evidence(value, where, checks):
    record = _mapping(value, where)
    result = {'id': _text(record.get('id'), f'{where}.id')}
    if not result['id'].startswith('ev:'):
        raise InputInvalid(f'{where}.id: an evidence id must start with "ev:"',
                           code='invalid_evidence_id', where=f'{where}.id')
    check = _text(record.get('check'), f'{where}.check')
    if check not in checks:
        raise InputInvalid(f'{where}.check: unknown check {check!r}',
                           code='evidence_unknown_check', where=f'{where}.check')
    result['check'] = check
    outcome = _text(record.get('result'), f'{where}.result')
    if outcome not in ('pass', 'fail', 'unknown'):
        raise InputInvalid(f'{where}.result: must be pass, fail or unknown',
                           code='invalid_evidence_result', where=f'{where}.result')
    result['result'] = outcome
    # Fields whose absence makes reuse unprovable are optional at the schema
    # level and become ``unknown`` during assessment, never silently valid.
    for key, normalizer, code in (
            ('tool_version', _text, 'invalid_tool_version'),
            ('revision', _text, 'invalid_revision')):
        if key in record and record[key] is not None:
            result[key] = normalizer(record[key], f'{where}.{key}')
        else:
            result[key] = None
    if 'content_hash' in record and record['content_hash'] is not None:
        result['content_hash'] = canon.normalize_hash(
            record['content_hash'], where=f'{where}.content_hash')
    else:
        result['content_hash'] = None
    coverage = record.get('coverage')
    if coverage is not None:
        coverage = _mapping(coverage, f'{where}.coverage')
        objects = _optional_list(coverage, 'objects', f'{where}.coverage')
        impacts = _optional_list(coverage, 'impacts', f'{where}.coverage')
        attributes = _optional_list(coverage, 'attributes', f'{where}.coverage')
        result['coverage'] = {
            'objects': sorted(_text(item, f'{where}.coverage.objects[{i}]')
                              for i, item in enumerate(objects)),
            'attributes': sorted(_text(item, f'{where}.coverage.attributes[{i}]')
                                 for i, item in enumerate(attributes)),
            'impacts': sorted(_text(item, f'{where}.coverage.impacts[{i}]')
                              for i, item in enumerate(impacts)),
        }
    else:
        result['coverage'] = None
    conditions = _optional_list(record, 'conditions', where)
    result['conditions'] = sorted(
        _text(item, f'{where}.conditions[{index}]')
        for index, item in enumerate(conditions))
    simulated = record.get('simulated', False)
    if type(simulated) is not bool:
        raise InputInvalid(f'{where}.simulated: a boolean is required',
                           code='invalid_boolean', where=f'{where}.simulated')
    result['simulated'] = simulated
    if 'captured_at' in record and record['captured_at'] is not None:
        result['captured_at'] = _text(record['captured_at'], f'{where}.captured_at')
    else:
        result['captured_at'] = None
    if 'valid_until' in record and record['valid_until'] is not None:
        result['valid_until'] = _text(record['valid_until'], f'{where}.valid_until')
    else:
        result['valid_until'] = None
    result['host'] = None
    if record.get('host') is not None:
        host = _mapping(record['host'], f'{where}.host')
        result['host'] = canon.canonical_value(host, where=f'{where}.host')
    if 'dependency_fingerprint' in record and record['dependency_fingerprint'] is not None:
        result['dependency_fingerprint'] = canon.normalize_hash(
            record['dependency_fingerprint'],
            where=f'{where}.dependency_fingerprint')
    else:
        result['dependency_fingerprint'] = None
    if 'scope_complete' in record:
        if type(record['scope_complete']) is not bool:
            raise InputInvalid(f'{where}.scope_complete: a boolean is required',
                               code='invalid_boolean', where=f'{where}.scope_complete')
        result['scope_complete'] = record['scope_complete']
    else:
        result['scope_complete'] = False
    result['note'] = record.get('note', '')
    return result


# ---------------------------------------------------------------------------
# model
# ---------------------------------------------------------------------------

class Model:
    """Normalized, validated input model with deterministic accessors."""

    def __init__(self, data, *, where='model'):
        self.data = data
        self.where = where
        self.schema = data['schema']
        self.project = {'name': data['project']['name'],
                        'id': data['project'].get('id')}
        self.objects = {}
        self.object_order = []
        self.dependencies = []
        self.changes = []
        self.observed_diff = []
        self.constraints = []
        self.checks = {}
        self.check_order = []
        self.evidence = []
        self.budget = dict(DEFAULT_BUDGET)
        self.model_scope = {}
        self.baseline = None
        self.candidate = None
        self.simulated = bool(data.get('simulated', False))
        self.analysis_time = data.get('analysis_time')
        self.undeclared_difference = False
        self.raw = data

    # -- accessors ---------------------------------------------------------
    def object(self, identity):
        return self.objects.get(identity)

    def require_object(self, identity, where):
        record = self.objects.get(identity)
        if record is None:
            raise InputInvalid(f'{where}: unknown object {identity!r}',
                               code='unknown_object_reference', where=where)
        return record

    def attribute(self, identity, path, side='candidate'):
        record = self.objects[identity]
        return _attr(record, path, side)

    def baseline_value(self, identity, path):
        return self.attribute(identity, path, 'baseline')

    def candidate_value(self, identity, path):
        return self.attribute(identity, path, 'candidate')

    def change(self, change_id):
        for record in self.changes:
            if record['id'] == change_id:
                return record
        return None

    def checks_covering(self):
        return list(self.check_order)

    def constraints_on(self, identity):
        return [item for item in self.constraints if item['object'] == identity]

    def evidence_for(self, check_id):
        return [item for item in self.evidence if item['check'] == check_id]

    def fingerprint(self):
        """Hash of the model content, excluding the declared changes.

        Ordering does not matter: objects and dependencies are sorted first, so
        a re-ordered input produces the same fingerprint.
        """
        material = {
            'project': self.project['name'],
            'baseline': self.baseline,
            'candidate': self.candidate,
            'objects': [self.objects[key] for key in sorted(self.objects)],
            'dependencies': sorted(self.dependencies,
                                   key=lambda item: item['id']),
        }
        return canon.sha256_value(material)


def validate_model(data, *, where='model'):
    """Validate ``data`` and return a :class:`Model`; never partially accepts."""
    _mapping(data, where)
    if data.get('schema') != SCHEMA_MODEL:
        raise InputInvalid(
            f'{where}.schema: expected {SCHEMA_MODEL!r}, got {data.get("schema")!r}',
            code='wrong_schema', where=f'{where}.schema')
    _walk_paths(data, where)
    model = Model(data, where=where)

    project = _mapping(data.get('project'), f'{where}.project')
    model.project = {
        'name': _text(project.get('name'), f'{where}.project.name'),
        'id': _text(project.get('id'), f'{where}.project.id', allow_empty=True)
        if project.get('id') is not None else None,
    }

    for side in ('baseline', 'candidate'):
        setattr(model, side, None)
    objects_raw = _list(data.get('objects'), f'{where}.objects')
    for index, raw in enumerate(objects_raw):
        record = _validate_object(raw, f'{where}.objects[{index}]')
        if record['id'] in model.objects:
            raise InputInvalid(
                f'{where}.objects[{index}].id: duplicate object {record["id"]!r}',
                code='duplicate_object_id', where=f'{where}.objects[{index}].id')
        model.objects[record['id']] = record
        model.object_order.append(record['id'])

    model_kinds = sorted({model.objects[key]['kind'] for key in model.object_order})
    for side in ('baseline', 'candidate'):
        value = data.get(side)
        if value is None:
            raise InputInvalid(f'{where}.{side}: a snapshot object is required',
                               code='missing_snapshot', where=f'{where}.{side}')
        setattr(model, side, _validate_snapshot(value, f'{where}.{side}', model_kinds))
    baseline, candidate = model.baseline, model.candidate
    if baseline['project'] != candidate['project']:
        raise InputInvalid(
            f'{where}: baseline.project {baseline["project"]!r} does not match '
            f'candidate.project {candidate["project"]!r}',
            code='project_mismatch', where=where)
    if baseline['document'] != candidate['document']:
        raise InputInvalid(
            f'{where}: baseline.document {baseline["document"]!r} does not match '
            f'candidate.document {candidate["document"]!r}',
            code='document_mismatch', where=where)
    if baseline['revision'] == candidate['revision'] and \
            baseline['content_hash'] != candidate['content_hash']:
        raise InputInvalid(
            f'{where}: the snapshots differ but share revision '
            f'{baseline["revision"]!r}; an ECO must move to a new revision',
            code='same_revision', where=where)

    dependencies_raw = _list(data.get('dependencies', []), f'{where}.dependencies')
    dependency_ids = set()
    for index, raw in enumerate(dependencies_raw):
        record = _validate_dependency(raw, f'{where}.dependencies[{index}]')
        if record['id'] in dependency_ids:
            raise InputInvalid(
                f'{where}.dependencies[{index}].id: duplicate dependency '
                f'{record["id"]!r}', code='duplicate_dependency_id',
                where=f'{where}.dependencies[{index}].id')
        dependency_ids.add(record['id'])
        for endpoint in ('from', 'to'):
            model.require_object(record[endpoint],
                                 f'{where}.dependencies[{index}].{endpoint}')
        model.dependencies.append(record)

    changes_raw = _list(data.get('changes', []), f'{where}.changes')
    change_ids = set()
    for index, raw in enumerate(changes_raw):
        if isinstance(raw, dict) and isinstance(raw.get('id'), str):
            if raw['id'] in change_ids:
                raise InputInvalid(
                    f'{where}.changes[{index}].id: duplicate change '
                    f'{raw["id"]!r}', code='duplicate_change_id',
                    where=f'{where}.changes[{index}].id')
            change_ids.add(raw['id'])
    observed_present = bool(data.get('observed_diff'))
    same_hash = baseline['content_hash'] == candidate['content_hash']
    if changes_raw and same_hash:
        raise InputInvalid(
            f'{where}: changes are declared but both snapshots carry the same '
            f'content hash; the declaration contradicts the snapshot',
            code='hash_conflict', where=where)
    if not changes_raw and observed_present and same_hash:
        raise InputInvalid(
            f'{where}: an observed diff is supplied but both snapshots carry the '
            f'same content hash', code='diff_hash_conflict', where=where)
    if not changes_raw and not observed_present:
        if not same_hash:
            # The snapshots differ but nobody declared what changed.  This is a
            # reported incomplete analysis, not a rejection: the tool can still
            # say "you declared nothing, so nothing can be propagated" and mark
            # the status incomplete rather than pretending the diff is empty.
            model.undeclared_difference = True
        else:
            scope_decl = data.get('model_scope')
            dependencies_complete = (isinstance(scope_decl, dict) and
                                     scope_decl.get('dependencies_complete') is True)
            if not (baseline['complete'] and candidate['complete'] and
                    model_kinds and dependencies_complete):
                raise InputInvalid(
                    f'{where}: both snapshots have the same content hash and '
                    f'declare no change, but the snapshot/model coverage is not '
                    f'declared complete; an empty comparison is not proof that '
                    f'nothing changed',
                    code='incomplete_no_change_proof', where=where)
    for index, raw in enumerate(changes_raw):
        where_change = f'{where}.changes[{index}]'
        record = _validate_change(raw, where_change)
        if record['object'] is None:
            raise InputInvalid(f'{where_change}.object: a change must name the '
                               f'object it applies to',
                               code='change_without_object', where=where_change)
        model.require_object(record['object'], f'{where_change}.object')
        model.changes.append(record)

    model.changes = _check_change_consistency(model, where)

    observed = data.get('observed_diff')
    if observed is not None:
        observed = _list(observed, f'{where}.observed_diff')
        model.observed_diff = _validate_observed_diff(observed, model, where)

    constraints_raw = _list(data.get('constraints', []), f'{where}.constraints')
    constraint_ids = set()
    for index, raw in enumerate(constraints_raw):
        record = _validate_constraint(raw, f'{where}.constraints[{index}]')
        if record['id'] in constraint_ids:
            raise InputInvalid(
                f'{where}.constraints[{index}].id: duplicate constraint '
                f'{record["id"]!r}', code='duplicate_constraint_id',
                where=f'{where}.constraints[{index}].id')
        constraint_ids.add(record['id'])
        model.require_object(record['object'],
                             f'{where}.constraints[{index}].object')
        model.constraints.append(record)

    catalog_raw = _list(data.get('verification_catalog', []),
                        f'{where}.verification_catalog')
    for index, raw in enumerate(catalog_raw):
        record = _validate_check(raw, f'{where}.verification_catalog[{index}]')
        if record['id'] in model.checks:
            raise InputInvalid(
                f'{where}.verification_catalog[{index}].id: duplicate check '
                f'{record["id"]!r}', code='duplicate_check_id',
                where=f'{where}.verification_catalog[{index}].id')
        model.checks[record['id']] = record
        model.check_order.append(record['id'])
    for check_id in model.check_order:
        check = model.checks[check_id]
        for index, target in enumerate(check['covers']):
            if target['object'] is not None:
                model.require_object(
                    target['object'],
                    f'check {check_id} covers[{index}].object')
        for index, required in enumerate(check['requires']):
            if required not in model.checks:
                raise InputInvalid(
                    f'check {check_id} requires unknown check {required!r}',
                    code='missing_check_dependency', where=f'check {check_id}')
        for index, required in enumerate(check['requires']):
            if required == check_id:
                raise InputInvalid(f'check {check_id} requires itself',
                                   code='check_self_dependency',
                                   where=f'check {check_id}')

    evidence_raw = _list(data.get('prior_evidence', []),
                         f'{where}.prior_evidence')
    for index, raw in enumerate(evidence_raw):
        record = _validate_evidence(raw, f'{where}.prior_evidence[{index}]',
                                    set(model.checks))
        if any(item['id'] == record['id'] for item in model.evidence):
            raise InputInvalid(
                f'{where}.prior_evidence[{index}].id: duplicate evidence '
                f'{record["id"]!r}', code='duplicate_evidence_id',
                where=f'{where}.prior_evidence[{index}].id')
        model.evidence.append(record)

    budget = data.get('budget', {})
    if budget is not None:
        budget = _mapping(budget, f'{where}.budget')
        for key in ('max_depth', 'max_paths'):
            if key in budget:
                model.budget[key] = canon.non_negative_int(
                    budget[key], where=f'{where}.budget.{key}',
                    code='invalid_budget')
                if model.budget[key] < 1:
                    raise InputInvalid(f'{where}.budget.{key}: must be >= 1',
                                       code='invalid_budget',
                                       where=f'{where}.budget.{key}')
        if 'max_cost' in budget:
            model.budget['max_cost'] = canon.positive_number(
                budget['max_cost'], where=f'{where}.budget.max_cost',
                code='invalid_budget', allow_zero=True)
        if 'max_checks' in budget and budget['max_checks'] is not None:
            model.budget['max_checks'] = canon.non_negative_int(
                budget['max_checks'], where=f'{where}.budget.max_checks',
                code='invalid_budget')
            if model.budget['max_checks'] < 1:
                raise InputInvalid(f'{where}.budget.max_checks: must be >= 1',
                                   code='invalid_budget',
                                   where=f'{where}.budget.max_checks')

    scope = data.get('model_scope')
    if scope is None:
        raise InputInvalid(f'{where}.model_scope: required; a model must declare '
                           f'what its graph covers', code='missing_model_scope',
                           where=f'{where}.model_scope')
    scope = _mapping(scope, f'{where}.model_scope')
    declared_kinds = _optional_list(scope, 'declared_kinds',
                                    f'{where}.model_scope')
    declared = sorted(_text(item, f'{where}.model_scope.declared_kinds[{i}]')
                      for i, item in enumerate(declared_kinds))
    for kind in declared:
        if kind not in OBJECT_KINDS:
            raise InputInvalid(
                f'{where}.model_scope.declared_kinds: unknown kind {kind!r}',
                code='unknown_object_kind', where=f'{where}.model_scope')
    unknown_objects = _optional_list(scope, 'unknown_objects',
                                     f'{where}.model_scope')
    unknown_objects = sorted(
        _text(item, f'{where}.model_scope.unknown_objects[{i}]')
        for i, item in enumerate(unknown_objects))
    for identity in unknown_objects:
        if identity in model.objects:
            raise InputInvalid(
                f'{where}.model_scope.unknown_objects: {identity!r} is also a '
                f'declared object', code='scope_contradiction',
                where=f'{where}.model_scope')
    complete_edges = scope.get('dependencies_complete', False)
    if type(complete_edges) is not bool:
        raise InputInvalid(
            f'{where}.model_scope.dependencies_complete: a boolean is required',
            code='invalid_boolean', where=f'{where}.model_scope.dependencies_complete')
    notes = scope.get('notes', '')
    model.model_scope = {
        'declared_kinds': declared,
        'unknown_objects': unknown_objects,
        'dependencies_complete': complete_edges,
        'notes': _text(notes, f'{where}.model_scope.notes', allow_empty=True)
        if notes else '',
    }

    if model.analysis_time is not None:
        model.analysis_time = _text(model.analysis_time, f'{where}.analysis_time')
    if not isinstance(model.simulated, bool):
        raise InputInvalid(f'{where}.simulated: a boolean is required',
                           code='invalid_boolean', where=f'{where}.simulated')
    return model


# ---------------------------------------------------------------------------
# change consistency
# ---------------------------------------------------------------------------

def _check_change_consistency(model, where):
    """Verify before/after against the model and reject contradictory changes."""
    ordered = sorted(model.changes, key=lambda item: (item['object'],
                                                      item['attribute'] or '',
                                                      item['id']))
    seen = {}
    for change in ordered:
        identity = change['object']
        record = model.object(identity)
        path = change['attribute']
        change_type = change['change_type']
        if change_type == 'modify':
            if not record['present']['baseline'] or not record['present']['candidate']:
                raise InputInvalid(
                    f'change {change["id"]}: modify requires the object to exist '
                    f'on both sides', code='before_after_mismatch',
                    where=f'change {change["id"]}')
            if path is None:
                raise InputInvalid(f'change {change["id"]}: modify requires an '
                                   f'attribute path (whole-object replacement is '
                                   f'a remove+add pair)',
                                   code='change_without_attribute',
                                   where=f'change {change["id"]}')
        before = model.baseline_value(identity, path) if path is not None else MISSING
        after = model.candidate_value(identity, path) if path is not None else MISSING
        if change_type == 'remove' and path is not None:
            if not json_equal(before, change['before']):
                raise InputInvalid(
                    f'change {change["id"]}: declared before={change["before"]!r} '
                    f'does not match the baseline model value '
                    f'{_show(before)}', code='before_after_mismatch',
                    where=f'change {change["id"]}')
        elif change_type == 'add' and path is not None:
            if not json_equal(after, change['after']):
                raise InputInvalid(
                    f'change {change["id"]}: declared after={change["after"]!r} '
                    f'does not match the candidate model value {_show(after)}',
                    code='before_after_mismatch', where=f'change {change["id"]}')
        elif path is not None:
            if not json_equal(before, change['before']):
                raise InputInvalid(
                    f'change {change["id"]}: declared before={change["before"]!r} '
                    f'does not match the baseline model value {_show(before)}',
                    code='before_after_mismatch', where=f'change {change["id"]}')
            if not json_equal(after, change['after']):
                raise InputInvalid(
                    f'change {change["id"]}: declared after={change["after"]!r} '
                    f'does not match the candidate model value {_show(after)}',
                    code='before_after_mismatch', where=f'change {change["id"]}')
        key = (identity, path, change['change_type'])
        if key in seen:
            raise InputInvalid(
                f'changes {seen[key]} and {change["id"]} both declare '
                f'{change_type} of {identity}.{path}', code='duplicate_change',
                where=f'change {change["id"]}')
        seen[key] = change['id']
        change['kind'], change['class_label'] = _resolve_change_kind(model, change)

    # Two changes must not rewrite the same attribute with different values.
    rewrites = {}
    for change in ordered:
        key = (change['object'], change['attribute'])
        if change['attribute'] is None:
            continue
        if key in rewrites and not json_equal(rewrites[key]['after'],
                                              change['after']):
            raise InputInvalid(
                f'changes {rewrites[key]["id"]} and {change["id"]} rewrite '
                f'{key[0]}.{key[1]} to different values',
                code='contradictory_changes', where=f'change {change["id"]}')
        rewrites[key] = change
    return ordered


def _resolve_change_kind(model, change):
    """Decide the effective change kind, honouring a declared kind only when it
    is compatible with the attribute class."""
    derived, label = classify_attribute(model.object(change['object'])['kind'],
                                        change['attribute'])
    declared = change['declared_kind']
    if declared is not None and derived is not None and declared != derived:
        # A declared class that disagrees with the attribute path is a contract
        # error rather than a silent override: the caller would otherwise be
        # able to hide a power change behind a display label.
        allowed = {
            ('power_requirement', 'parameter'),
            ('parameter', 'power_requirement'),
            # a pose edit explicitly claimed as a layer change is acceptable;
            # both classes drive pose/layer propagation rules.
            ('layer_stack', 'mechanical_pose'),
        }
        if (declared, derived) not in allowed:
            raise InputInvalid(
                f'change {change["id"]}: declared kind {declared!r} contradicts '
                f'the attribute class {derived!r} for '
                f'{change["object"]}.{change["attribute"]}',
                code='change_kind_mismatch', where=f'change {change["id"]}')
    kind = declared or derived or 'unknown_attribute'
    return kind, label


def _show(value):
    if value is MISSING:
        return '<absent>'
    return repr(value)


# ---------------------------------------------------------------------------
# observed diff (J1 declaration vs reality)
# ---------------------------------------------------------------------------

def _validate_observed_diff(entries, model, where):
    result = []
    for index, raw in enumerate(entries):
        item_where = f'{where}.observed_diff[{index}]'
        record = _mapping(raw, item_where)
        identity = _text(record.get('object'), f'{item_where}.object')
        model.require_object(identity, f'{item_where}.object')
        path = record.get('attribute')
        if path is not None:
            path = _text(path, f'{item_where}.attribute')
            split_path(path)
        if 'before' not in record or 'after' not in record:
            raise InputInvalid(f'{item_where}: before and after are required',
                               code='missing_before_value', where=item_where)
        before = canon.canonical_value(record['before'], where=f'{item_where}.before')
        after = canon.canonical_value(record['after'], where=f'{item_where}.after')
        if json_equal(before, after):
            raise InputInvalid(f'{item_where}: observed values are identical; a '
                               f'diff entry must describe a change',
                               code='no_op_change', where=item_where)
        source = record.get('source', 'observed')
        if source not in ('observed', 'derived'):
            raise InputInvalid(f'{item_where}.source: must be observed or derived',
                               code='invalid_diff_source', where=f'{item_where}.source')
        result.append({'object': identity, 'attribute': path,
                       'before': before, 'after': after, 'source': source})
    return sorted(result, key=lambda item: (item['object'],
                                            item['attribute'] or '',
                                            canon.canonical_json(item)))
