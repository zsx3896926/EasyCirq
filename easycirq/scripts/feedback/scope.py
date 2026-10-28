"""Modification contract, writable/check scope, diff, invariants and recovery.

This is work package D of the closed-loop feedback layer.  The frozen data
contracts live in :mod:`schemas`; this module adds the operational rules the
schemas deliberately leave open:

* a modification contract is built from a measured observation and keeps the
  exact baseline hash, target project/document UUIDs, a writable scope, the
  allowed actions and the invariants that must hold afterwards;
* ``validate_plan`` is a pure pre-write check: it refuses an action outside
  ``allowed_actions``, an object/net/region outside ``scope.writable``, a
  locked object, a missing/stale/unknown baseline, a document identity change
  and duplicate operations.  Nothing is sent to EDA and nothing is written;
* ``preview`` compiles the same steps a write would send, annotates each step
  with its scope decision and always reports ``writes_sent: 0``;
* a PCB write is delegated to :mod:`pcb_apply_plan` (playbook compiler, one
  ``easycirq apply``, journal) - this module does not reimplement that
  compiler.  A schematic write compiles typed ``schematic.text.move`` /
  ``schematic.component.modify`` calls, verifies the response context and
  reads the result back;
* ``apply_scoped`` records five separate facts.  ``call_ok``,
  ``write_confirmed``, ``save_confirmed``, ``reopen_confirmed`` and
  ``quality_passed`` never collapse into one "success"; a missing readback is
  ``None`` (NOT RUN), never ``True``;
* ``diff_observations`` compares PCB and schematic observations semantically.
  Primitive IDs churn across a reload, rotations 0/360 and -90/270 are
  equivalent, and an unreadable category is reported as ``unknown`` rather
  than treated as empty;
* ``recover`` parses the journal, maps every operation to a content-stable
  ``operation_key`` and compares it with a current observation.  A re-run may
  skip already-applied operations; non-idempotent creations (track/via/pour)
  with an unconfirmed send are flagged as duplicate risk and are not declared
  safe to retry.

Contract gaps reported instead of worked around (schemas.py is frozen):

* ``SCHEMA_MODIFICATION`` has no field for the observation snapshot or for
  the tolerance used by the diff.  The snapshot is stored under
  ``contract.baseline.facts`` (extra keys are not rejected) and the tolerance
  under ``contract.scope.tolerance``;
* there is no frozen schema for plan validation, baseline checks or
  invariant results.  This module exposes ``hds-plan-validation/v1``,
  ``hds-baseline-check/v1`` and ``hds-invariants/v1`` locally and says so in
  every payload;
* ``SCHEMA_DIFF`` does not prescribe a change shape.  This module returns a
  stable ``changes[]`` list plus per-category summaries.

Tests use a fake runner only.  No function resolves ``easycirq`` from PATH:
``apply_scoped`` refuses a write when neither ``runner`` nor an explicit
``easycirq`` path is supplied.
"""
from __future__ import annotations

import copy
import json
import math
import os
import re
import shutil
import sys
import tempfile
import types

try:  # package import
    from . import schemas
except ImportError:  # pragma: no cover - flat import by offline tools
    import os as _os
    import sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
    import schemas

SCHEMA_PLAN_VALIDATION = 'hds-plan-validation/v1'
SCHEMA_BASELINE_CHECK = 'hds-baseline-check/v1'
SCHEMA_INVARIANTS = 'hds-invariants/v1'
PLAYBOOK_SCHEMA = 'design-engine-pcb-playbook/v1'

POSITION_TOLERANCE = 0.01
ANGLE_TOLERANCE = 1e-6

PCB_OP_KINDS = ('place', 'track', 'via', 'pour')
SCH_OP_KINDS = ('move_text', 'move_component', 'rotate_component')
COPPER_OP_KINDS = ('track', 'via', 'pour')
NON_IDEMPOTENT_KINDS = ('track', 'via', 'pour')

KIND_ACTION = {
    'place': schemas.ACTION_MOVE_COMPONENT,
    'track': schemas.ACTION_TRACK,
    'via': schemas.ACTION_VIA,
    'pour': schemas.ACTION_POUR,
    'move_text': schemas.ACTION_MOVE_TEXT,
    'move_component': schemas.ACTION_MOVE_COMPONENT,
    'rotate_component': schemas.ACTION_ROTATE_COMPONENT,
}

IDENTITY_PATCH_KEYS = frozenset((
    'designator', 'uniqueId', 'unique_id', 'device', 'footprint',
    'replace', 'delete', 'remove', 'create', 'id',
))
IDENTITY_OP_KINDS = frozenset((
    'add_component', 'create_component', 'delete_component', 'replace_component',
    'create_document', 'delete_document', 'replace_document', 'create', 'delete',
    'replace',
))
VOLATILE_KEYS = frozenset((
    'primitiveId', 'primitive_id', 'id', 'native', 'locked', 'geometryAvailable',
    'resultSha256', 'responseCreatedAt', 'startedAt', 'completedAt',
))


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------

def _is_number(value):
    return type(value) in (int, float) and math.isfinite(float(value))


def _number(value):
    return float(value) if _is_number(value) else None


def _int_or_none(value):
    if _is_number(value) and int(value) == float(value):
        return int(value)
    return None


def _text(value):
    return '' if value is None else str(value).strip()


def _first(mapping, *keys):
    if not isinstance(mapping, dict):
        return None
    for key in keys:
        if key in mapping:
            return mapping[key]
    return None


def _has(mapping, key):
    return isinstance(mapping, dict) and key in mapping


def _angle_norm(value):
    number = _number(value)
    if number is None:
        return None
    result = number % 360.0
    if abs(result - 360.0) <= 1e-9:
        result = 0.0
    return result


def _same_angle(first, second, tolerance):
    left, right = _angle_norm(first), _angle_norm(second)
    if left is None or right is None:
        return left is None and right is None
    delta = ((left - right + 180.0) % 360.0) - 180.0
    return abs(delta) <= tolerance


def _same_number(first, second, tolerance):
    left, right = _number(first), _number(second)
    if left is None or right is None:
        return left is None and right is None
    return abs(left - right) <= tolerance


def _json_value(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False, default=str)


def _canonical(value, tolerance, *, ignore=VOLATILE_KEYS):
    """Return a JSON-stable value with geometry rounded to a tolerance."""
    if isinstance(value, dict):
        return {key: _canonical(item, tolerance, ignore=ignore)
                for key, item in sorted(value.items())
                if key not in ignore}
    if isinstance(value, (list, tuple)):
        return [_canonical(item, tolerance, ignore=ignore) for item in value]
    if _is_number(value):
        decimals = _decimals(tolerance)
        return round(float(value), decimals)
    return value


def _decimals(tolerance):
    tolerance = abs(float(tolerance)) if _is_number(tolerance) else 0.01
    if tolerance <= 0:
        return 9
    return min(9, max(0, int(math.ceil(-math.log10(tolerance))) + 1))


def _bbox(value):
    if isinstance(value, dict):
        values = [_number(value.get(key)) for key in
                  ('minX', 'minY', 'maxX', 'maxY')]
        if all(item is not None for item in values):
            return [float(item) for item in values]
        return None
    if isinstance(value, (list, tuple)) and len(value) == 4:
        values = [_number(item) for item in value]
        if all(item is not None for item in values):
            return [float(item) for item in values]
    return None


def _bbox_dict(value):
    box = _bbox(value)
    if box is None:
        return None
    return {'minX': box[0], 'minY': box[1], 'maxX': box[2], 'maxY': box[3]}


def _bbox_of_points(points):
    values = [_point(item) for item in points or []]
    values = [item for item in values if item is not None]
    if not values:
        return None
    return [min(item[0] for item in values), min(item[1] for item in values),
            max(item[0] for item in values), max(item[1] for item in values)]


def _bbox_union(first, second):
    if first is None:
        return second
    if second is None:
        return first
    return [min(first[0], second[0]), min(first[1], second[1]),
            max(first[2], second[2]), max(first[3], second[3])]


def _point(value):
    if isinstance(value, dict):
        x, y = _number(value.get('x')), _number(value.get('y'))
        if x is not None and y is not None:
            return (x, y)
        return None
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        x, y = _number(value[0]), _number(value[1])
        if x is not None and y is not None:
            return (x, y)
    return None


def _points(value):
    if not isinstance(value, list):
        return None
    result = [_point(item) for item in value]
    if any(item is None for item in result):
        return None
    return result


def _point_in_bbox(point, box, tolerance=0.0):
    if point is None or box is None:
        return False
    return (box[0] - tolerance <= point[0] <= box[2] + tolerance and
            box[1] - tolerance <= point[1] <= box[3] + tolerance)


def _bbox_intersects(first, second, tolerance=0.0):
    if first is None or second is None:
        return False
    return not (first[2] < second[0] - tolerance or
                second[2] < first[0] - tolerance or
                first[3] < second[1] - tolerance or
                second[3] < first[1] - tolerance)


def _points_inside_region(points, region, tolerance):
    return bool(points) and all(_point_in_bbox(point, region, tolerance)
                                for point in points)


# ---------------------------------------------------------------------------
# scope / target / baseline normalisation
# ---------------------------------------------------------------------------

def _normalize_tolerance(value, base=None):
    result = dict(base or {'position': POSITION_TOLERANCE,
                           'angle': ANGLE_TOLERANCE})
    if value is None:
        return result
    if _is_number(value):
        result['position'] = float(value)
        return result
    if not isinstance(value, dict):
        raise schemas.ContractError('tolerance must be a number or an object')
    for key in ('position', 'geometry', 'outline', 'distance', 'position_mil'):
        if key in value:
            number = _number(value[key])
            if number is None or number < 0:
                raise schemas.ContractError('tolerance.%s must be a '
                                            'nonnegative number' % key)
            result['position'] = float(number)
    for key in ('angle', 'rotation'):
        if key in value:
            number = _number(value[key])
            if number is None or number < 0:
                raise schemas.ContractError('tolerance.%s must be a '
                                            'nonnegative number' % key)
            result['angle'] = float(number)
    if 'tolerance' in value and _is_number(value['tolerance']):
        result['position'] = float(value['tolerance'])
    return result


def _normalize_region(value):
    if isinstance(value, dict):
        box = _bbox(value.get('bbox') or value.get('region') or value)
        if box is not None:
            return box
        x, y = _number(value.get('x')), _number(value.get('y'))
        width, height = _number(value.get('width')), _number(value.get('height'))
        if None not in (x, y, width, height):
            return [x, y, x + width, y + height]
        return None
    return _bbox(value)


def _object_names(value):
    result = []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return result
    for item in value:
        if isinstance(item, str) and item.strip():
            result.append(item.strip())
        elif isinstance(item, dict):
            for key in ('designator', 'id', 'primitiveId', 'primitive_id',
                        'object', 'name'):
                text = _text(item.get(key))
                if text:
                    result.append(text)
                    break
    return result


def _region_values(value):
    if value is None:
        return []
    if isinstance(value, dict):
        value = [value]
    if not isinstance(value, list):
        return []
    if len(value) == 4 and all(_is_number(item) for item in value):
        value = [value]
    result = []
    for item in value:
        region = _normalize_region(item)
        if region is None:
            raise schemas.ContractError('scope region must be '
                                        '[minX,minY,maxX,maxY]')
        result.append(region)
    return result


def _normalize_scope_part(value, *, tolerance=None):
    if not isinstance(value, dict):
        raise schemas.ContractError('scope must be an object')
    objects = []
    for key in ('objects', 'designators', 'primitive_ids', 'primitiveIds',
                'parts', 'items'):
        objects.extend(_object_names(value.get(key)))
    nets = []
    for key in ('nets', 'network', 'net_names'):
        raw = value.get(key)
        if isinstance(raw, str):
            raw = [raw]
        if isinstance(raw, list):
            nets.extend(_text(item) for item in raw if _text(item))
    regions = []
    for key in ('regions', 'areas', 'boxes'):
        regions.extend(_region_values(value.get(key)))
    if value.get('bbox') is not None:
        regions.extend(_region_values(value.get('bbox')))
    if value.get('region') is not None:
        regions.extend(_region_values(value.get('region')))
    return {
        'objects': list(dict.fromkeys(objects)),
        'nets': list(dict.fromkeys(nets)),
        'regions': [list(item) for item in regions],
    }


def normalize_scope(scope, *, tolerance=None):
    """Return the canonical ``{writable, checkable, tolerance}`` object."""
    if scope is None:
        raise schemas.ContractError('scope is required')
    if isinstance(scope, str):
        scope = {'objects': [scope]}
    elif isinstance(scope, list):
        scope = {'objects': scope}
    if not isinstance(scope, dict):
        raise schemas.ContractError('scope must be an object, list or string')
    if 'writable' in scope:
        writable = _normalize_scope_part(scope.get('writable') or {})
        checkable_raw = scope.get('checkable')
        checkable = (_normalize_scope_part(checkable_raw)
                     if isinstance(checkable_raw, dict) else None)
        tol = _normalize_tolerance(scope.get('tolerance'), tolerance)
    else:
        writable = _normalize_scope_part(scope)
        checkable = None
        tol = _normalize_tolerance(scope.get('tolerance'), tolerance)
    result = {
        'writable': writable,
        'tolerance': tol,
    }
    if checkable is not None:
        result['checkable'] = checkable
    return result


def _scope_selectors(scope):
    if not isinstance(scope, dict):
        return set(), set(), []
    writable = scope.get('writable') if 'writable' in scope else scope
    objects = set(_object_names((writable or {}).get('objects')))
    nets = set(_text(item) for item in (writable or {}).get('nets') or []
               if _text(item))
    regions = _region_values((writable or {}).get('regions'))
    return objects, nets, regions


def _normalize_documents(value, observation=None):
    by_uuid = {}
    for document in (observation or {}).get('documents') or []:
        if isinstance(document, dict):
            uuid = _text(document.get('uuid'))
            if uuid:
                by_uuid[uuid] = document
    if isinstance(value, str):
        value = [value]
    if isinstance(value, dict):
        value = [value]
    documents = []
    for item in value or []:
        if isinstance(item, str):
            text = item.strip()
            if not text:
                continue
            known = by_uuid.get(text) or {}
            documents.append({'uuid': text,
                              'type': known.get('type'),
                              'name': known.get('name')})
        elif isinstance(item, dict):
            uuid = _text(_first(item, 'uuid', 'document_uuid', 'documentUuid',
                                'id'))
            if not uuid:
                continue
            known = by_uuid.get(uuid) or {}
            documents.append({
                'uuid': uuid,
                'type': item.get('type') or item.get('documentType') or
                        known.get('type'),
                'name': item.get('name') or known.get('name'),
            })
    seen = set()
    result = []
    for document in documents:
        if document['uuid'] in seen:
            continue
        seen.add(document['uuid'])
        result.append(document)
    return result


def _normalize_target(target, observation=None):
    window_id = None
    if target is None:
        observation = observation or {}
        project = observation.get('project') or {}
        project_uuid = _text(_first(project, 'uuid', 'project_uuid',
                                    'projectUuid'))
        documents = _normalize_documents(observation.get('documents') or [],
                                         observation)
    elif isinstance(target, str):
        project_uuid = target.strip()
        documents = _normalize_documents(observation.get('documents') or [],
                                         observation)
    elif isinstance(target, dict):
        project = target.get('project')
        window_id = _text(_first(target, 'window_id', 'windowId'))
        project_uuid = _text(_first(target, 'project_uuid', 'projectUuid',
                                    'uuid'))
        if not project_uuid and isinstance(project, str):
            project_uuid = project.strip()
        if not project_uuid and isinstance(project, dict):
            project_uuid = _text(_first(project, 'uuid', 'project_uuid',
                                        'projectUuid'))
        documents = target.get('documents') or target.get('docs')
        if documents is None and target.get('document_uuid'):
            documents = [{'uuid': target.get('document_uuid'),
                          'type': target.get('document_type'),
                          'name': target.get('document_name')}]
        documents = _normalize_documents(documents or [], observation)
        if not project_uuid:
            observed = (observation or {}).get('project') or {}
            project_uuid = _text(_first(observed, 'uuid', 'project_uuid',
                                        'projectUuid'))
    else:
        raise schemas.ContractError('target must be an object, string or None')
    if not project_uuid:
        raise schemas.ContractError('contract.target.project_uuid is required')
    if not documents:
        raise schemas.ContractError('contract.target.documents must not be empty')
    if not window_id and isinstance(observation, dict):
        # A contract built from an observation inherits the window that
        # observation was captured from; otherwise the plan->apply flow would
        # silently forget which host window the baseline belongs to.
        window_id = _text(_first(observation.get('host') or {},
                                 'window_id', 'windowId'))
    normalized = {'project_uuid': project_uuid, 'documents': documents}
    if window_id:
        normalized['window_id'] = window_id
    return normalized


def _document_kind(document):
    text = _text((document or {}).get('type') if isinstance(document, dict)
                 else document).lower()
    if 'pcb' in text:
        return 'pcb'
    if 'sch' in text:
        return 'schematic'
    return None


def _observation_revision(observation):
    observation = observation or {}
    if not isinstance(observation, dict):
        return None, {}, None
    revision = observation.get('revision') or {}
    hash_value = (_text(revision.get('semantic_sha256')) or
                  _text(revision.get('semanticSha256')))
    per_document = revision.get('per_document') or {}
    captured = revision.get('captured_at') or observation.get('generated_at')
    if not hash_value:
        pcb = observation.get('pcb') if isinstance(observation.get('pcb'),
                                                   dict) else {}
        hash_value = (_text(pcb.get('semanticSha256')) or
                      _text(pcb.get('semantic_sha256')))
    if not hash_value:
        semantic = observation.get('semanticSha256')
        hash_value = _text(semantic)
    return hash_value or None, per_document, captured


def _baseline_unknown_reason(observation):
    for entry in (observation or {}).get('unknown') or []:
        field = _text((entry or {}).get('field'))
        if field.startswith('revision'):
            return _text(entry.get('reason')) or 'revision is unknown'
    return 'observation has no revision.semantic_sha256'


def _build_baseline(observation, target):
    hash_value, per_document, captured = _observation_revision(observation)
    facts = _compact_observation(observation) if observation else None
    baseline = {
        'semantic_sha256': hash_value,
        'per_document': per_document,
        'captured_at': captured,
        'target': target,
        'observation_digest': (schemas.stable_hash(facts) if facts else None),
        'facts': facts,
    }
    if not hash_value:
        baseline['unknown_reason'] = _baseline_unknown_reason(observation)
    return baseline


def _compact_observation(observation):
    """Return the compact baseline view stored with a modification contract."""
    if not isinstance(observation, dict):
        return None
    _hash, _per_document, captured = _observation_revision(observation)
    pcb = _obs_pcb(observation)
    schematic = _obs_sch(observation)
    facts = {
        'schema': 'hds-observation-facts/v1',
        'generated_at': observation.get('generated_at') or captured,
        'project': copy.deepcopy(observation.get('project') or {}),
        'documents': copy.deepcopy(observation.get('documents') or []),
        'revision': copy.deepcopy(observation.get('revision') or {}),
        'unknown': copy.deepcopy(observation.get('unknown') or []),
    }
    if pcb is not None:
        components, availability = _pcb_component_map(pcb)
        facts['pcb'] = {
            'document_uuid': _text(_first(pcb, 'document_uuid',
                                          'documentUuid')),
            'semantic_sha256': _text(_first(pcb, 'semanticSha256',
                                            'semantic_sha256')),
            'components': [
                {key: copy.deepcopy(value) for key, value in item.items()
                 if key != 'native'}
                for item in (components or {}).values()],
            'components_availability': availability,
            'outline': copy.deepcopy(pcb.get('outline') or {}),
            'copper': copy.deepcopy(pcb.get('copper') or {}),
            'copperLayers': pcb.get('copperLayers'),
            'rules': copy.deepcopy(pcb.get('rules') or {}),
            'holes': copy.deepcopy(pcb.get('holes')),
            'keepouts': copy.deepcopy(pcb.get('keepouts')),
            'cutouts': copy.deepcopy(pcb.get('cutouts')),
            'routedLines': copy.deepcopy(pcb.get('routedLines')),
            'routed': copy.deepcopy(pcb.get('routed')),
            'unrouted': copy.deepcopy(pcb.get('unrouted')),
            'drc': copy.deepcopy(_pcb_drc(observation)),
            'availability': copy.deepcopy(pcb.get('availability') or {}),
        }
    if schematic is not None:
        facts['schematic'] = {
            'document_uuid': _text(_first(schematic, 'document_uuid',
                                          'documentUuid')),
            'components': copy.deepcopy(schematic.get('components') or []),
            'nets': copy.deepcopy(schematic.get('nets') or []),
            'texts': copy.deepcopy(schematic.get('texts')),
            'availability': copy.deepcopy(schematic.get('availability') or {}),
        }
    return facts


# ---------------------------------------------------------------------------
# observation views
# ---------------------------------------------------------------------------

def _looks_like_pcb_dump(value):
    if not isinstance(value, dict):
        return False
    if 'components' not in value:
        return False
    return any(key in value for key in ('outline', 'copper', 'copperLayers',
                                        'semanticSha256', 'capture',
                                        'rules', 'availability'))


def _looks_like_schematic(value):
    if not isinstance(value, dict):
        return False
    if 'components' not in value and 'nets' not in value:
        return False
    return any(key in value for key in ('nets', 'netlistAvailable', 'texts',
                                        'pins', 'floatingPins',
                                        'componentCount'))


def _as_observation(value):
    if not isinstance(value, dict):
        return value
    if value.get('schema') == schemas.SCHEMA_OBSERVATION:
        return value
    if any(key in value for key in ('pcb', 'schematic')):
        return value
    if _looks_like_pcb_dump(value):
        return {'pcb': value,
                'revision': {'semantic_sha256':
                             _text(value.get('semanticSha256')) or None},
                'generated_at': value.get('capturedAt'),
                'unknown': []}
    if _looks_like_schematic(value):
        return {'schematic': value, 'revision': {'semantic_sha256': None},
                'generated_at': None, 'unknown': []}
    return value


def _obs_pcb(observation):
    if not isinstance(observation, dict):
        return None
    pcb = observation.get('pcb')
    if isinstance(pcb, dict):
        return pcb
    if _looks_like_pcb_dump(observation):
        return observation
    return None


def _obs_sch(observation):
    if not isinstance(observation, dict):
        return None
    schematic = observation.get('schematic')
    if isinstance(schematic, dict):
        return schematic
    if _looks_like_schematic(observation):
        return observation
    return None


def _availability(value):
    text = _text(value).lower()
    if text in ('available', 'complete', 'ok', 'measured', 'true'):
        return 'available'
    if text in ('partial', 'incomplete'):
        return 'partial'
    if text in ('unavailable', 'absent', 'failed', 'error', 'false'):
        return 'unavailable'
    return 'unknown'


def _pcb_component_map(pcb):
    """Return ``(by designator, availability)`` for a PCB section."""
    if not isinstance(pcb, dict):
        return None, 'unavailable'
    availability = _availability(
        (pcb.get('availability') or {}).get('components') or
        pcb.get('componentsAvailability') or
        (pcb.get('coverage') or {}).get('components'))
    raw = pcb.get('components')
    if raw is None:
        return None, ('unavailable' if availability == 'unknown'
                      else availability)
    if not isinstance(raw, list):
        return None, 'unavailable'
    result = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        designator = _text(_first(item, 'designator', 'ref', 'reference'))
        if not designator:
            continue
        native = item.get('native') if isinstance(item.get('native'), dict) \
            else {}
        primitive_id = _text(_first(item, 'primitive_id', 'primitiveId') or
                             _first(native, 'primitiveId', 'primitive_id'))
        pads = []
        raw_pads = item.get('pads')
        if isinstance(raw_pads, list):
            for pad in raw_pads:
                if not isinstance(pad, dict):
                    continue
                pads.append({
                    'number': _text(_first(pad, 'number', 'padNumber',
                                           'pad_number')),
                    'net': _text(pad.get('net')) or None,
                    'primitive_id': _text(_first(pad, 'primitive_id',
                                                 'primitiveId')),
                    'x': _number(pad.get('x')),
                    'y': _number(pad.get('y')),
                })
        locked = _first(item, 'locked', 'primitiveLock', 'lock')
        if locked is None:
            locked = _first(native, 'locked', 'primitiveLock', 'lock')
        result[designator] = {
            'designator': designator,
            'primitive_id': primitive_id or None,
            'unique_id': _text(_first(item, 'unique_id', 'uniqueId') or
                               _first(native, 'uniqueId', 'unique_id')) or None,
            'device': _first(item, 'device') or _first(native, 'device'),
            'name': _first(item, 'name') or _first(native, 'name'),
            'layer': _int_or_none(item.get('layer')),
            'x': _number(item.get('x')),
            'y': _number(item.get('y')),
            'rotation': _number(item.get('rotation')),
            'locked': locked if isinstance(locked, bool) else None,
            'bbox': _bbox(item.get('bbox')),
            'pads': pads,
            'pads_readable': isinstance(raw_pads, list),
            'native': native or item,
        }
    return result, availability


def _sch_component_map(schematic):
    if not isinstance(schematic, dict):
        return None, 'unavailable'
    availability = _availability(
        (schematic.get('availability') or {}).get('components') or
        schematic.get('componentsAvailability'))
    raw = schematic.get('components')
    if raw is None:
        return None, ('unavailable' if availability == 'unknown'
                      else availability)
    if not isinstance(raw, list):
        return None, 'unavailable'
    result = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        designator = _text(_first(item, 'designator', 'ref', 'reference'))
        if not designator:
            continue
        pins = []
        pins_readable = isinstance(item.get('pins'), list)
        for pin in item.get('pins') or []:
            if not isinstance(pin, dict):
                continue
            pins.append({
                'number': _text(_first(pin, 'number', 'name', 'pin')),
                'name': _text(pin.get('name')),
                'net': _text(pin.get('net')) or None,
            })
        locked = _first(item, 'locked', 'primitiveLock', 'lock')
        result[designator] = {
            'designator': designator,
            'primitive_id': _text(_first(item, 'primitive_id', 'primitiveId',
                                         'id')) or None,
            'unique_id': _text(_first(item, 'unique_id', 'uniqueId')) or None,
            'device': _first(item, 'device', 'footprint'),
            'name': _first(item, 'name', 'value'),
            'footprint': _first(item, 'footprint'),
            'supplier_id': _text(_first(item, 'supplierId', 'supplier_id')) or
                            None,
            'x': _number(item.get('x')),
            'y': _number(item.get('y')),
            'rotation': _number(item.get('rotation')),
            'locked': locked if isinstance(locked, bool) else None,
            'pins': pins,
            'pins_readable': pins_readable,
            'attributes': copy.deepcopy(item.get('attributes') or {}),
        }
    return result, availability


def _pcb_outline(pcb):
    if not isinstance(pcb, dict):
        return None, None
    outline = pcb.get('outline') if isinstance(pcb.get('outline'), dict) else {}
    if 'points' not in outline:
        return None, None
    points = _points(outline.get('points'))
    if points is None:
        return None, None
    box = _bbox(outline.get('bbox')) or _bbox_of_points(points)
    return points, box


def _pcb_copper(pcb, key):
    if not isinstance(pcb, dict):
        return None
    copper = pcb.get('copper') if isinstance(pcb.get('copper'), dict) else None
    if copper is not None:
        values = copper.get(key)
        if not isinstance(values, list):
            return None
        # The raw dump names the line collection ``routing`` in its
        # availability map; reading ``lines`` here silently treated an
        # explicit "routing unavailable" as an empty measured collection.
        raw_availability_key = {
            'lines': 'routing', 'vias': 'vias', 'pours': 'pours',
            'regions': 'regions', 'fills': 'fills', 'poured': 'poured',
        }.get(key, key)
        availability = _availability(
            (copper.get('availability') or {}).get(raw_availability_key))
        if availability != 'available':
            return None
        return values
    # ``observe`` emits a normalized board where copper collections live at
    # the top level (tracks/vias/pours/...) with availability under
    # availability.categories.  Read that shape too; otherwise every real
    # readback reports all copper as unknown.
    source, availability_key = {
        'lines': ('tracks', 'routing'),
        'vias': ('vias', 'vias'),
        'pours': ('pours', 'pours'),
        'regions': ('regions', 'regions'),
        'fills': ('fills', 'fills'),
        'poured': ('poured', 'poured'),
    }.get(key, (key, key))
    values = pcb.get(source)
    if not isinstance(values, list):
        return None
    availability = _availability(
        ((pcb.get('availability') or {}).get('categories') or {}).get(
            availability_key))
    if availability != 'available':
        return None
    return values


def _pcb_rules(pcb):
    if not isinstance(pcb, dict) or 'rules' not in pcb:
        return None
    return copy.deepcopy(pcb.get('rules') or {})


def _pcb_copper_layers(pcb):
    if not isinstance(pcb, dict) or 'copperLayers' not in pcb:
        return None
    return pcb.get('copperLayers')


def _pcb_collection(pcb, *keys):
    for key in keys:
        if isinstance(pcb, dict) and key in pcb:
            return copy.deepcopy(pcb.get(key))
        copper = (pcb or {}).get('copper') if isinstance(pcb, dict) else None
        if isinstance(copper, dict) and key in copper:
            return copy.deepcopy(copper.get(key))
    return None


def _pcb_drc(observation):
    observation = observation or {}
    if not isinstance(observation, dict):
        return None
    for holder in (observation, observation.get('pcb'),
                   observation.get('drc')):
        if isinstance(holder, dict):
            for key in ('drc', 'drcResult', 'drc_result'):
                if isinstance(holder.get(key), dict):
                    return copy.deepcopy(holder[key])
            if holder.get('errors') is not None and 'passed' in holder:
                return copy.deepcopy(holder)
    return None


def _pcb_routed_state(observation):
    pcb = _obs_pcb(observation) or {}
    required = set()
    components, _availability_components = _pcb_component_map(pcb)
    for component in (components or {}).values():
        for pad in component.get('pads') or []:
            if pad.get('net'):
                required.add(str(pad['net']))
    for item in pcb.get('nets') or []:
        if isinstance(item, str):
            required.add(item)
        elif isinstance(item, dict) and item.get('name'):
            required.add(str(item['name']))
    routed = set()
    explicit = False
    for key in ('routedNets', 'routed_nets'):
        value = pcb.get(key)
        if isinstance(value, list):
            explicit = True
            for item in value:
                net = item if isinstance(item, str) else _first(item, 'net',
                                                                'name')
                if _text(net):
                    routed.add(_text(net))
    routed_lines = pcb.get('routedLines')
    if isinstance(routed_lines, list):
        explicit = True
        for item in routed_lines:
            net = item if isinstance(item, str) else _first(item, 'net', 'name')
            if _text(net):
                routed.add(_text(net))
    copper_routed = set()
    copper_readable = False
    for key in ('lines', 'vias', 'pours'):
        values = _pcb_copper(pcb, key)
        if values is None:
            continue
        copper_readable = True
        for item in values:
            if isinstance(item, dict) and _text(item.get('net')):
                copper_routed.add(_text(item.get('net')))
    if copper_readable:
        routed.update(copper_routed)
    elif not explicit:
        return {'status': 'unknown', 'routed': [], 'unrouted': None,
                'per_net': {}, 'required': sorted(required),
                'reason': 'routed state is not measurable'}
    unrouted = sorted(required - routed) if required else None
    status = 'available' if required or explicit else 'partial'
    per_net = {}
    for net in sorted(required | routed):
        if net in routed:
            per_net[net] = 'routed'
        elif required and net in required:
            per_net[net] = 'unrouted'
        else:
            per_net[net] = 'unknown'
    return {'status': status, 'routed': sorted(routed), 'unrouted': unrouted,
            'per_net': per_net, 'required': sorted(required),
            'source': ('explicit' if explicit else
                       ('copper' if copper_readable else 'unknown'))}


# ---------------------------------------------------------------------------
# plan normalisation
# ---------------------------------------------------------------------------

def _plan_observation(plan):
    if not isinstance(plan, dict):
        return None
    for key in ('observation', 'before', 'baseline_observation',
                'fresh_observation'):
        value = plan.get(key)
        if isinstance(value, dict) and any(item in value for item in
                                           ('pcb', 'schematic', 'schema',
                                            'components', 'revision')):
            return _as_observation(value)
    baseline = plan.get('baseline')
    if isinstance(baseline, dict):
        for key in ('observation', 'facts'):
            value = baseline.get(key)
            if isinstance(value, dict):
                return _as_observation(value)
    return None


def _plan_simulated(plan):
    """True when the plan or its observation came from a simulated host."""
    if not isinstance(plan, dict):
        return False
    if plan.get('simulated') is True:
        return True
    observation = _plan_observation(plan)
    return bool(isinstance(observation, dict) and
                observation.get('simulated'))


def _plan_shape(plan):
    if isinstance(plan, list):
        return 'legacy'
    if not isinstance(plan, dict):
        return 'invalid'
    if 'ops' in plan and 'placements' in plan:
        return 'invalid'
    if 'ops' in plan:
        schema = plan.get('schema')
        if schema not in (None, PLAYBOOK_SCHEMA):
            return 'invalid'
        return 'playbook'
    if 'placements' in plan:
        return 'legacy'
    return 'invalid'


def _plan_flags(plan, kind):
    plan = plan if isinstance(plan, dict) else {}
    flags = {'save': plan.get('save'), 'reload': plan.get('reload'),
             'no_reload': bool(plan.get('no_reload'))}
    if kind == 'pcb':
        if flags['save'] is False:
            return None, 'a pcb_apply_plan playbook always saves; save=false ' \
                         'is not supported'
        save = True if flags['save'] is None else bool(flags['save'])
        reload = (not flags['no_reload']) if flags['reload'] is None \
            else bool(flags['reload'])
    else:
        save = bool(flags['save']) if flags['save'] is not None else False
        reload = bool(flags['reload']) if flags['reload'] is not None else False
        if reload:
            return None, 'schematic reload is not implemented by this ' \
                         'adapter; record the reopen evidence separately'
    return {'save': save, 'reload': reload}, None


def _normalize_plan_ops(plan):
    """Return ``(kind, ops, flags, error)`` without touching a board."""
    shape = _plan_shape(plan)
    if shape == 'invalid':
        return None, [], {}, 'plan must be a playbook {"ops":[...]} or a ' \
                             'legacy {"placements":[...]} object'
    raw_ops = plan if shape == 'legacy' else plan.get('ops')
    if shape == 'legacy':
        raw_ops = plan if isinstance(plan, list) else plan.get('placements')
    if not isinstance(raw_ops, list) or not raw_ops:
        return None, [], {}, 'plan.ops must be a non-empty list'
    ops = []
    flags_from_ops = {}
    for raw_index, raw in enumerate(raw_ops):
        if not isinstance(raw, dict):
            return None, [], {}, 'ops[%d] must be an object' % raw_index
        if shape == 'legacy':
            raw = dict(raw, op='place')
        name = _text(_first(raw, 'op', 'action', 'kind')).lower()
        if name in ('save', 'reload'):
            flags_from_ops[name] = True
            continue
        if name not in PCB_OP_KINDS + SCH_OP_KINDS:
            return None, [], {}, 'unsupported operation %r at ops[%d]' % (
                name, raw_index)
        op = {'index': len(ops), 'raw_index': raw_index, 'op': name,
              'raw': raw}
        if name == 'place':
            designator = _text(_first(raw, 'designator', 'ref'))
            to = raw.get('to') if isinstance(raw.get('to'), dict) else {
                key: raw.get(key) for key in ('x', 'y', 'rotation', 'layer')
                if key in raw
            }
            op['designator'] = designator or None
            op['primitive_id'] = _text(_first(raw, 'primitive_id',
                                              'primitiveId')) or None
            op['to'] = {
                'x': _number(to.get('x')),
                'y': _number(to.get('y')),
                'rotation': (_number(to.get('rotation'))
                             if 'rotation' in to else None),
                'layer': (_int_or_none(to.get('layer'))
                          if 'layer' in to else None),
            }
            if not designator:
                return None, [], {}, 'place op needs a designator'
            if op['to']['x'] is None or op['to']['y'] is None:
                return None, [], {}, 'place %s needs numeric to.x/to.y' % (
                    designator,)
        elif name in ('track', 'pour'):
            op['net'] = _text(raw.get('net')) or None
            op['layer'] = _int_or_none(raw.get('layer'))
            op['points'] = _points(raw.get('points'))
            if name == 'track':
                op['width_mil'] = _number(raw.get('width_mil'))
            else:
                op['fill'] = _text(raw.get('fill')) or 'solid'
            if op['points'] is None:
                return None, [], {}, '%s op needs a list of [x,y] points' % name
        elif name == 'via':
            op['net'] = _text(raw.get('net')) or None
            op['x'] = _number(raw.get('x'))
            op['y'] = _number(raw.get('y'))
            op['hole_mil'] = _number(raw.get('hole_mil'))
            op['diameter_mil'] = _number(raw.get('diameter_mil'))
            if op['x'] is None or op['y'] is None:
                return None, [], {}, 'via op needs numeric x/y'
        elif name == 'move_text':
            op['primitive_id'] = _text(_first(raw, 'primitive_id',
                                              'primitiveId', 'id')) or None
            op['x'] = _number(raw.get('x'))
            op['y'] = _number(raw.get('y'))
            op['content'] = _text(_first(raw, 'content', 'text'))
            if not op['primitive_id']:
                return None, [], {}, 'move_text op needs a primitiveId'
            if op['x'] is None or op['y'] is None:
                return None, [], {}, 'move_text op needs numeric x/y'
        else:  # move_component / rotate_component
            op['designator'] = _text(_first(raw, 'designator', 'ref')) or None
            op['primitive_id'] = _text(_first(raw, 'primitive_id',
                                              'primitiveId', 'id')) or None
            patch = raw.get('patch') if isinstance(raw.get('patch'), dict) else {
                key: raw.get(key) for key in ('x', 'y', 'rotation', 'layer')
                if key in raw
            }
            op['patch'] = copy.deepcopy(patch or {})
            if not op['designator'] and not op['primitive_id']:
                return None, [], {}, '%s op needs a designator or primitiveId' \
                                     % name
            if not op['patch']:
                return None, [], {}, '%s op needs a patch' % name
        ops.append(op)
    values = {op['op'] for op in ops}
    pcb_kinds = values & set(PCB_OP_KINDS)
    sch_kinds = values & set(SCH_OP_KINDS)
    if pcb_kinds and sch_kinds:
        return None, [], {}, 'a plan may not mix schematic and PCB operations'
    if not pcb_kinds and not sch_kinds:
        return None, [], {}, 'plan contains no writable operation'
    kind = 'pcb' if pcb_kinds else 'schematic'
    if kind == 'schematic' and shape == 'legacy':
        return None, [], {}, 'legacy placements are PCB-only'
    flags, error = _plan_flags(plan, kind)
    if error:
        return None, [], {}, error
    for key in flags_from_ops:
        flags[key] = True
    return kind, ops, flags, None


def _plan_base(plan, *, before=None):
    values = []
    if isinstance(plan, dict):
        base = plan.get('base')
        if isinstance(base, str) and base.strip():
            values.append(base.strip())
        elif isinstance(base, dict):
            for key in ('semantic_sha256', 'semanticSha256', 'sha256',
                        'base_semantic_sha256', 'baseSha256'):
                if _text(base.get(key)):
                    values.append(_text(base.get(key)))
                    break
        for key in ('base_semantic_sha256', 'base_sha256', 'baseSemanticSha256'):
            if _text(plan.get(key)):
                values.append(_text(plan.get(key)))
    observation = _plan_observation(plan)
    observation_hash = _observation_revision(observation)[0] if observation \
        else None
    if observation_hash:
        values.append(observation_hash)
    before_hash = _observation_revision(before)[0] if before else None
    if not values and before_hash:
        values.append(before_hash)
    unique = list(dict.fromkeys(item for item in values if item))
    return unique, observation, observation_hash, before_hash


def _plan_document(plan):
    if not isinstance(plan, dict):
        return None
    document = plan.get('document') or plan.get('doc')
    if isinstance(document, dict):
        return document
    if isinstance(document, str):
        return {'uuid': document, 'name': document}
    return None


def _pick_document(contract, kind, plan):
    target = contract.get('target') or {}
    documents = target.get('documents') or []
    declared = _plan_document(plan)
    if declared:
        declared_uuid = _text(_first(declared, 'uuid', 'document_uuid',
                                     'documentUuid', 'id'))
        declared_name = _text(declared.get('name'))
        for document in documents:
            if declared_uuid and declared_uuid in (
                    _text(document.get('uuid')),
                    _text(document.get('name'))):
                return document, None
            if declared_name and declared_name in (
                    _text(document.get('uuid')),
                    _text(document.get('name'))):
                return document, None
        if declared_uuid or declared_name:
            return None, 'plan targets a document outside contract.target'
        declared_type = _document_kind(declared)
        if declared_type and declared_type != kind:
            return None, 'plan document type %r does not match %s operations' \
                         % (declared_type, kind)
    for document in documents:
        if _document_kind(document) == kind:
            return document, None
    if len(documents) == 1:
        return documents[0], None
    return None, 'contract.target has no %s document' % kind


def _plan_project_refusal(contract, plan):
    if not isinstance(plan, dict):
        return None
    target = contract.get('target') or {}
    expected = {_text(target.get('project_uuid'))}
    facts = (contract.get('baseline') or {}).get('facts') or {}
    baseline_name = _text(((facts.get('project') or {}).get('name')))
    if baseline_name:
        expected.add(baseline_name)
    observation = _plan_observation(plan)
    if observation:
        project = observation.get('project') or {}
        if _text(_first(project, 'uuid', 'project_uuid', 'projectUuid')):
            expected.add(_text(_first(project, 'uuid', 'project_uuid',
                                      'projectUuid')))
        if _text(project.get('name')):
            expected.add(_text(project.get('name')))
    declared = plan.get('project') or plan.get('project_uuid') or \
        plan.get('projectUuid')
    if isinstance(declared, dict):
        declared = _first(declared, 'uuid', 'project_uuid', 'projectUuid',
                          'name')
    declared = _text(declared)
    if declared and declared not in expected:
        return 'plan targets project %r, contract targets %r' % (
            declared, sorted(expected))
    return None


# ---------------------------------------------------------------------------
# operation keys and presence
# ---------------------------------------------------------------------------

def _operation_canonical(op):
    kind = _text(_first(op, 'op', 'action', 'kind')).lower()
    if kind == 'place':
        to = op.get('to') if isinstance(op.get('to'), dict) else op
        return {'op': 'place', 'designator': _text(op.get('designator')),
                'to': {
                    'x': _number(to.get('x')),
                    'y': _number(to.get('y')),
                    'rotation': (_angle_norm(to.get('rotation'))
                                 if to.get('rotation') is not None else None),
                    'layer': _int_or_none(to.get('layer')),
                }}
    if kind == 'track':
        return {'op': 'track', 'net': _text(op.get('net')),
                'layer': _int_or_none(op.get('layer')),
                'width_mil': _number(op.get('width_mil')),
                'points': [list(point) for point in _points(op.get('points')) or
                           []]}
    if kind == 'via':
        return {'op': 'via', 'net': _text(op.get('net')),
                'x': _number(op.get('x')), 'y': _number(op.get('y')),
                'hole_mil': _number(op.get('hole_mil')),
                'diameter_mil': _number(op.get('diameter_mil'))}
    if kind == 'pour':
        return {'op': 'pour', 'net': _text(op.get('net')),
                'layer': _int_or_none(op.get('layer')),
                'fill': _text(op.get('fill')) or 'solid',
                'points': [list(point) for point in _points(op.get('points')) or
                           []]}
    if kind == 'move_text':
        return {'op': 'move_text',
                'primitive_id': _text(_first(op, 'primitive_id', 'primitiveId',
                                             'id')),
                'content': _text(op.get('content')),
                'x': _number(op.get('x')), 'y': _number(op.get('y'))}
    if kind in ('move_component', 'rotate_component'):
        patch = op.get('patch') if isinstance(op.get('patch'), dict) else {}
        normalized = {}
        for key in ('x', 'y'):
            if key in patch and _number(patch.get(key)) is not None:
                normalized[key] = _number(patch.get(key))
        if 'rotation' in patch and _number(patch.get('rotation')) is not None:
            normalized['rotation'] = _angle_norm(patch.get('rotation'))
        if 'layer' in patch and _int_or_none(patch.get('layer')) is not None:
            normalized['layer'] = _int_or_none(patch.get('layer'))
        for key in sorted(patch):
            if key not in ('x', 'y', 'rotation', 'layer'):
                normalized[key] = _canonical(patch[key], POSITION_TOLERANCE)
        return {'op': kind,
                'designator': _text(op.get('designator')),
                'primitive_id': _text(_first(op, 'primitive_id', 'primitiveId',
                                             'id')),
                'patch': normalized}
    if kind in ('save', 'reload'):
        return {'op': kind}
    raise schemas.ContractError('cannot build an operation key for %r' % (kind,))


def operation_key(op):
    """Return a content-stable key for duplicate prevention and recovery.

    Volatile fields (measured primitiveId on a place op, reason text, source
    pose) are excluded so a save/reload that churns IDs does not make the same
    operation look new.
    """
    canonical = _operation_canonical(op)
    digest = schemas.sha256_text(_json_value(canonical))[:16]
    return '%s:%s' % (canonical['op'], digest)


def _component_for_op(op, components):
    if not components:
        return None
    designator = _text(op.get('designator'))
    primitive_id = _text(_first(op, 'primitive_id', 'primitiveId', 'id'))
    if designator and designator in components:
        return components[designator]
    for component in components.values():
        if primitive_id and component.get('primitive_id') == primitive_id:
            return component
    return None


def _op_present(op, observation):
    """Return True/False/None when an operation is already on the board."""
    kind = _text(_first(op, 'op', 'action', 'kind')).lower()
    observation = _as_observation(observation)
    tolerance = POSITION_TOLERANCE
    angle_tolerance = ANGLE_TOLERANCE
    if kind in ('place', 'move_component', 'rotate_component'):
        pcb = _obs_pcb(observation)
        schematic = _obs_sch(observation)
        components = None
        if kind == 'place' or pcb is not None:
            components, _availability_value = _pcb_component_map(pcb)
        if components is None and schematic is not None:
            components, _availability_value = _sch_component_map(schematic)
        if components is None:
            return None
        component = _component_for_op(op, components)
        if component is None:
            return False
        if kind == 'place':
            to = op.get('to') if isinstance(op.get('to'), dict) else {}
        else:
            to = op.get('patch') if isinstance(op.get('patch'), dict) else {}
        x = _number(to.get('x'))
        y = _number(to.get('y'))
        if x is not None and not _same_number(component.get('x'), x, tolerance):
            return False
        if y is not None and not _same_number(component.get('y'), y, tolerance):
            return False
        if 'rotation' in to and to.get('rotation') is not None:
            if not _same_angle(component.get('rotation'), to.get('rotation'),
                               angle_tolerance):
                return False
        if 'layer' in to and to.get('layer') is not None:
            if _int_or_none(component.get('layer')) != _int_or_none(
                    to.get('layer')):
                return False
        return True
    if kind == 'move_text':
        schematic = _obs_sch(observation)
        texts = _sch_texts(schematic)
        if texts is None:
            return None
        primitive_id = _text(_first(op, 'primitive_id', 'primitiveId', 'id'))
        x, y = _number(op.get('x')), _number(op.get('y'))
        for text in texts:
            if primitive_id and text.get('primitive_id') == primitive_id:
                return (_same_number(text.get('x'), x, tolerance) and
                        _same_number(text.get('y'), y, tolerance))
        return False
    if kind in COPPER_OP_KINDS:
        pcb = _obs_pcb(observation)
        if pcb is None:
            return None
        key = {'track': 'lines', 'via': 'vias', 'pour': 'pours'}[kind]
        values = _pcb_copper(pcb, key)
        if values is None:
            return None
        for item in values:
            if not isinstance(item, dict):
                continue
            if _copper_matches_op(kind, op, item,
                                  {'position': tolerance,
                                   'angle': angle_tolerance}):
                return True
        return False
    return None


def _copper_matches_op(kind, op, item, tolerance):
    if _text(op.get('net')) != _text(item.get('net')):
        return False
    position = tolerance['position']
    if kind == 'via':
        return (_same_number(op.get('x'), item.get('x'), position) and
                _same_number(op.get('y'), item.get('y'), position) and
                _same_number(op.get('hole_mil'), item.get('holeDiameter'),
                             position) and
                _same_number(op.get('diameter_mil'), item.get('diameter'),
                             position))
    if _int_or_none(op.get('layer')) != _int_or_none(item.get('layer')):
        return False
    if kind == 'track':
        first = _points(op.get('points'))
        second = _points([(item.get('startX'), item.get('startY')),
                          (item.get('endX'), item.get('endY'))])
        if first is None or second is None:
            return False
        if not _same_number(op.get('width_mil'), item.get('lineWidth'),
                            position):
            return False
        forward = all(_same_number(a[0], b[0], position) and
                      _same_number(a[1], b[1], position)
                      for a, b in zip(first, second))
        backward = all(_same_number(a[0], b[0], position) and
                       _same_number(a[1], b[1], position)
                       for a, b in zip(first, list(reversed(second))))
        return forward or backward
    # pour
    first = op.get('points')
    second = item.get('source') if item.get('source') is not None else \
        item.get('points')
    if first is None or second is None:
        return _text(op.get('fill') or 'solid') == _text(
            _first(item, 'fillMethod', 'fill') or 'solid')
    if _text(op.get('fill') or 'solid') != _text(
            _first(item, 'fillMethod', 'fill') or 'solid'):
        return False
    return _json_value(_canonical(first, position)) == \
        _json_value(_canonical(second, position))


# ---------------------------------------------------------------------------
# scope decisions
# ---------------------------------------------------------------------------

def _op_points(op):
    kind = op.get('op')
    if kind == 'place':
        to = op.get('to') or {}
        point = _point((to.get('x'), to.get('y')))
        return [point] if point else []
    if kind in ('track', 'pour'):
        return _points(op.get('points')) or []
    if kind == 'via':
        point = _point((op.get('x'), op.get('y')))
        return [point] if point else []
    if kind in ('move_text', 'move_component', 'rotate_component'):
        patch = op.get('patch') if isinstance(op.get('patch'), dict) else op
        x = patch.get('x') if kind != 'move_text' else op.get('x')
        y = patch.get('y') if kind != 'move_text' else op.get('y')
        point = _point((x, y))
        return [point] if point else []
    return []


def _op_object(op):
    kind = op.get('op')
    if kind in ('place', 'move_component', 'rotate_component'):
        return _text(_first(op, 'designator', 'primitive_id', 'primitiveId',
                            'id'))
    if kind == 'move_text':
        return _text(_first(op, 'primitive_id', 'primitiveId', 'id'))
    return ''


def _scope_decision(scope, op):
    objects, nets, regions = _scope_selectors(scope)
    tolerance = _normalize_tolerance(scope.get('tolerance')
                                     if isinstance(scope, dict) else None)
    object_id = _op_object(op)
    if object_id and object_id in objects:
        return {'decision': 'in_scope', 'basis': 'object:%s' % object_id}
    primitive_id = _text(_first(op, 'primitive_id', 'primitiveId'))
    if primitive_id and primitive_id in objects:
        return {'decision': 'in_scope', 'basis': 'object:%s' % primitive_id}
    net = _text(op.get('net'))
    if net and net in nets:
        return {'decision': 'in_scope', 'basis': 'net:%s' % net}
    points = _op_points(op)
    for index, region in enumerate(regions):
        if _points_inside_region(points, region, tolerance['position']):
            return {'decision': 'in_scope', 'basis': 'region:%d' % index}
    return {'decision': 'out_of_scope', 'basis': None}


def _locked_target(op, observation):
    kind = op.get('op')
    pcb_components = _pcb_component_map(_obs_pcb(observation))[0]
    sch_components = _sch_component_map(_obs_sch(observation))[0]
    candidates = []
    designator = _text(op.get('designator'))
    primitive_id = _text(_first(op, 'primitive_id', 'primitiveId'))
    if designator and pcb_components and designator in pcb_components:
        candidates.append(pcb_components[designator])
    if designator and sch_components and designator in sch_components:
        candidates.append(sch_components[designator])
    for component in (pcb_components or {}).values():
        if primitive_id and component.get('primitive_id') == primitive_id:
            candidates.append(component)
    for component in (sch_components or {}).values():
        if primitive_id and component.get('primitive_id') == primitive_id:
            candidates.append(component)
    if kind == 'move_text':
        texts = _sch_texts(_obs_sch(observation))
        if texts is None:
            return None
        for text in texts:
            if primitive_id and text.get('primitive_id') == primitive_id:
                return bool(text.get('locked')) if text.get('locked') is not \
                    None else None
        return False
    if not candidates:
        return False if (pcb_components is not None or
                         sch_components is not None) else None
    known = [component.get('locked') for component in candidates
             if component.get('locked') is not None]
    return True if any(known) else (False if known else None)


# ---------------------------------------------------------------------------
# compilation
# ---------------------------------------------------------------------------

def _pcb_modules():
    scripts = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    import pcb_apply_plan  # noqa: PLC0415
    import pcb_cli  # noqa: PLC0415
    return pcb_apply_plan, pcb_cli


def _track_for_dump(item):
    start = item.get('start') or {}
    end = item.get('end') or {}
    return {
        'primitiveId': item.get('primitive_id'),
        'net': item.get('net'), 'layer': item.get('layer'),
        'lineWidth': item.get('width', item.get('lineWidth')),
        'startX': start.get('x', item.get('startX')),
        'startY': start.get('y', item.get('startY')),
        'endX': end.get('x', item.get('endX')),
        'endY': end.get('y', item.get('endY')),
    }


def _via_for_dump(item):
    return {
        'primitiveId': item.get('primitive_id'), 'net': item.get('net'),
        'x': item.get('x'), 'y': item.get('y'),
        'diameter': item.get('diameter'),
        'holeDiameter': item.get('hole_diameter', item.get('holeDiameter')),
    }


def _pour_for_dump(item):
    return {
        'primitiveId': item.get('primitive_id'), 'net': item.get('net'),
        'layer': item.get('layer'),
        'fillMethod': item.get('fill_method', item.get('fillMethod')),
        'points': copy.deepcopy(item.get('points')),
    }


def _pcb_dump_from_view(observation):
    pcb = _obs_pcb(observation)
    if not isinstance(pcb, dict):
        return None
    components, _availability_value = _pcb_component_map(pcb)
    if components is None:
        return None
    raw_components = []
    for component in components.values():
        native = component.get('native') or {}
        if isinstance(native, dict) and 'primitiveId' in native and 'x' in native:
            native = copy.deepcopy(native)
            native.setdefault('primitive_id', native.get('primitiveId'))
            raw_components.append(native)
            continue
        pads = []
        for pad in component.get('pads') or []:
            pads.append({
                'padNumber': pad.get('number'),
                'net': pad.get('net'),
                'primitiveId': pad.get('primitive_id'),
                'x': pad.get('x'), 'y': pad.get('y'),
            })
        raw_components.append({
            'primitiveId': component.get('primitive_id'),
            'primitive_id': component.get('primitive_id'),
            'uniqueId': component.get('unique_id'),
            'designator': component.get('designator'),
            'name': component.get('name'),
            'device': component.get('device'),
            'layer': component.get('layer'),
            'x': component.get('x'), 'y': component.get('y'),
            'rotation': component.get('rotation'),
            'bbox': _bbox_dict(component.get('bbox')),
            'pads': pads,
        })
    outline = pcb.get('outline') if isinstance(pcb.get('outline'), dict) else {}
    points = _points(outline.get('points'))
    if points is not None:
        points = [list(point) for point in points]
    coast = pcb.get('copper') if isinstance(pcb.get('copper'), dict) else {}
    if not coast:
        coast = {
            'lines': [_track_for_dump(item) for item in pcb.get('tracks') or []
                      if isinstance(item, dict)],
            'vias': [_via_for_dump(item) for item in pcb.get('vias') or []
                     if isinstance(item, dict)],
            'pours': [_pour_for_dump(item) for item in pcb.get('pours') or []
                      if isinstance(item, dict)],
            'regions': copy.deepcopy(pcb.get('regions') or []),
            'fills': copy.deepcopy(pcb.get('fills') or []),
        }
    dump = {
        'components': raw_components,
        'outline': {'points': points or [],
                    'bbox': _bbox_dict(outline.get('bbox')) or
                            _bbox_dict(_bbox_of_points(points)),
                    'format': outline.get('format'),
                    'source': outline.get('source')},
        'copper': copy.deepcopy(coast),
        'copperLayers': pcb.get('copperLayers'),
        'rules': copy.deepcopy(pcb.get('rules') or {}),
        'capture': {
            'projectUuid': _text(((observation or {}).get('project') or
                                  {}).get('uuid')),
            'projectName': _text(((observation or {}).get('project') or
                                  {}).get('name')),
            'documentUuid': _text(_first(pcb, 'document_uuid',
                                         'documentUuid')),
            'documentType': 'pcb',
        },
        'semanticSha256': _text(_first(pcb, 'semanticSha256',
                                       'semantic_sha256')) or
                          _observation_revision(observation)[0],
        'availability': copy.deepcopy(pcb.get('availability') or {}),
        'routedLines': copy.deepcopy(pcb.get('routedLines')),
    }
    for key in ('holes', 'keepouts', 'cutouts'):
        if key in pcb:
            dump[key] = copy.deepcopy(pcb.get(key))
    return dump


_DUMP_COPPER_KEYS = ('lines', 'vias', 'pours', 'regions', 'fills', 'poured',
                     'arcs')
_DUMP_COPPER_AVAILABILITY = ('routing', 'vias', 'pours', 'poured',
                             'regions', 'fills')
_DUMP_TOP_AVAILABILITY = ('components', 'copper', 'outline', 'routedLines',
                          'rules')
_AVAILABLE_TOKENS = ('available', 'complete', 'ok', True)


def _raw_before_dump(plan):
    """Return the caller-supplied raw PCB dump, never a reconstruction."""
    if not isinstance(plan, dict):
        return None
    value = plan.get('before_dump')
    if not isinstance(value, dict):
        return None
    if not isinstance(value.get('components'), list):
        return None
    return value


def _dump_availability_problem(value, required, label):
    if not isinstance(value, dict):
        return ('%s is missing; a normalized observation rebuilt from '
                'pcb.tracks/vias/pours is not a raw dump' % label)
    missing = [key for key in required if key not in value]
    if missing:
        return '%s does not cover: %s' % (label, ', '.join(missing))
    incomplete = sorted(key for key, item in value.items()
                        if item not in _AVAILABLE_TOKENS)
    if incomplete:
        return '%s is incomplete for: %s' % (label, ', '.join(incomplete))
    return None


def _dump_copper_problem(dump):
    copper = dump.get('copper')
    if not isinstance(copper, dict):
        return 'before_dump has no copper section'
    for key in _DUMP_COPPER_KEYS:
        if not isinstance(copper.get(key), list):
            return 'before_dump.copper.%s is missing' % key
    problem = _dump_availability_problem(
        copper.get('availability'), _DUMP_COPPER_AVAILABILITY,
        'before_dump.copper.availability')
    if problem:
        return problem
    if copper.get('arcsAvailable') not in _AVAILABLE_TOKENS:
        return ('before_dump.copper.arcsAvailable is not available; the '
                'copper capture is incomplete')
    if not isinstance(dump.get('capturedAt'), str) or \
            not dump.get('capturedAt').strip():
        return ('before_dump.capturedAt is missing; the dump carries no '
                'capture timestamp')
    if dump.get('componentsAvailability') not in _AVAILABLE_TOKENS:
        return ('before_dump.componentsAvailability is not available; the '
                'component capture is incomplete')
    routed_lines = dump.get('routedLines')
    if isinstance(routed_lines, bool) or not isinstance(routed_lines, int) or \
            routed_lines < 0:
        return ('before_dump.routedLines is missing; the raw dump must carry '
                'the routed-line count')
    problem = _dump_availability_problem(
        dump.get('availability'), _DUMP_TOP_AVAILABILITY,
        'before_dump.availability')
    if problem:
        return problem
    return None


def _dump_component_problem(dump, pcb):
    raw = {}
    for item in dump.get('components') or []:
        if not isinstance(item, dict):
            continue
        designator = _text(item.get('designator'))
        if designator:
            raw[designator] = item
    components, _availability = _pcb_component_map(pcb)
    observed = {str(key): value
                for key, value in (components or {}).items()}
    if not observed:
        return 'the fresh observation has no measurable components'
    if set(raw) != set(observed):
        missing = sorted(set(observed) - set(raw))
        extra = sorted(set(raw) - set(observed))
        return ('before_dump components do not match the observation '
                '(missing=%s extra=%s)' % (missing[:8], extra[:8]))
    for designator in sorted(observed):
        left = raw[designator]
        right = observed[designator]
        left_id = _text(_first(left, 'primitiveId', 'primitive_id'))
        right_id = _text(right.get('primitive_id'))
        if left_id and right_id and left_id != right_id:
            return ('component %s primitive_id changed between the raw dump '
                    'and the fresh observation' % designator)
        for key in ('x', 'y', 'rotation'):
            left_value = _number(left.get(key))
            right_value = _number(right.get(key))
            if left_value is None or right_value is None:
                continue
            if abs(left_value - right_value) > 1e-6:
                return ('component %s %s changed between the raw dump and the '
                        'fresh observation' % (designator, key))
    return None


def _document_uuid(document):
    if isinstance(document, str):
        return _text(document)
    if isinstance(document, dict):
        return _text(_first(document, 'uuid', 'document_uuid', 'documentUuid',
                            'id'))
    return None


def _before_dump_refusals(contract, plan, observation, document=None,
                          window=None):
    """Refuse a PCB plan whose raw before_dump is missing, incomplete or not
    bound to the fresh observation and the document/window the write will use.

    ``document`` is the value ``_pick_document`` resolved for the write;
    ``window`` is the runtime ``--window`` override.  Both are checked against
    the observation and the raw dump before any CLI call is made.
    """
    kind, _ops, _flags, _error = _normalize_plan_ops(plan)
    if kind != 'pcb':
        return []
    dump = plan.get('before_dump') if isinstance(plan, dict) else None
    if not isinstance(dump, dict):
        return [_refusal(
            schemas.FAILURE_PRECONDITION_REFUSED, 'missing_before_dump',
            'a PCB write requires plan.before_dump carrying the raw pcb dump '
            'captured before planning; a normalized observation is not a '
            'substitute')]
    if not isinstance(dump.get('components'), list):
        return [_refusal(
            schemas.FAILURE_PRECONDITION_REFUSED, 'invalid_before_dump',
            'plan.before_dump.components must be the raw list captured by '
            'pcb dump')]
    refusals = []
    problem = _dump_copper_problem(dump)
    if problem:
        refusals.append(_refusal(
            schemas.FAILURE_PRECONDITION_REFUSED, 'incomplete_before_dump',
            'the raw before_dump is not a complete measurement: %s' % problem))

    capture = dump.get('capture') if isinstance(dump.get('capture'),
                                                dict) else {}
    observation = observation if isinstance(observation, dict) else {}
    pcb = _obs_pcb(observation)
    project = observation.get('project') if isinstance(
        observation.get('project'), dict) else {}
    target = contract.get('target') or {}
    expected_project = _text(target.get('project_uuid')) or \
        _text(project.get('uuid'))
    observed_project = _text(_first(project, 'uuid', 'projectUuid'))
    observed_document = _text(_first(pcb, 'document_uuid', 'documentUuid'))
    # Bind the dump to the document the write will actually address, not to
    # whichever alias happens to be in the plan.  ``_pick_document`` resolves
    # plan['document']/plan['doc'] the same way the apply path does.
    write_document = _document_uuid(document) or \
        _document_uuid(_plan_document(plan))
    expected_document = write_document or observed_document
    dump_project = _text(_first(capture, 'projectUuid', 'project_uuid'))
    dump_project_name = _text(_first(capture, 'projectName', 'project_name'))
    dump_document = _text(_first(capture, 'documentUuid', 'document_uuid'))
    # Real ``pcb dump`` output does not always carry a top-level ``project``;
    # when it does, accept either the bare uuid or an object.  The capture is
    # the authoritative provenance either way.
    raw_project_value = dump.get('project')
    raw_project_name = ''
    if isinstance(raw_project_value, dict):
        raw_project = _text(_first(raw_project_value, 'uuid', 'project_uuid',
                                   'projectUuid'))
        raw_project_name = _text(raw_project_value.get('name'))
    else:
        raw_project = _text(raw_project_value)

    if not observed_project:
        refusals.append(_refusal(
            schemas.FAILURE_PRECONDITION_REFUSED, 'unbound_before_dump',
            'the fresh observation does not identify its project; the dump '
            'cannot be bound to a live project'))
    if not observed_document:
        refusals.append(_refusal(
            schemas.FAILURE_PRECONDITION_REFUSED, 'unbound_before_dump',
            'the fresh observation does not identify its PCB document; the '
            'dump cannot be bound to a live document'))
    if expected_project and dump_project and dump_project != expected_project:
        refusals.append(_refusal(
            schemas.FAILURE_TARGET_MISMATCH, 'before_dump_target_mismatch',
            'before_dump was captured from project %s, the contract targets %s'
            % (dump_project, expected_project),
            expected=expected_project, actual=dump_project))
    if observed_project and dump_project and \
            dump_project != observed_project:
        refusals.append(_refusal(
            schemas.FAILURE_TARGET_MISMATCH, 'before_dump_target_mismatch',
            'before_dump belongs to project %s but the fresh observation is '
            'project %s' % (dump_project, observed_project),
            expected=observed_project, actual=dump_project))
    if raw_project and dump_project and raw_project != dump_project:
        refusals.append(_refusal(
            schemas.FAILURE_INVALID_INPUT, 'invalid_before_dump',
            'before_dump.project %s disagrees with capture.projectUuid %s'
            % (raw_project, dump_project),
            expected=dump_project, actual=raw_project))
    if not raw_project and raw_project_name and dump_project_name and \
            raw_project_name != dump_project_name:
        refusals.append(_refusal(
            schemas.FAILURE_INVALID_INPUT, 'invalid_before_dump',
            'before_dump.project %s disagrees with capture.projectName %s'
            % (raw_project_name, dump_project_name),
            expected=dump_project_name, actual=raw_project_name))
    if write_document and observed_document and \
            write_document != observed_document:
        refusals.append(_refusal(
            schemas.FAILURE_TARGET_MISMATCH, 'before_dump_target_mismatch',
            'the plan resolves to write document %s but the fresh observation '
            'is document %s' % (write_document, observed_document),
            expected=observed_document, actual=write_document))
    if expected_document and dump_document and \
            dump_document != expected_document:
        refusals.append(_refusal(
            schemas.FAILURE_TARGET_MISMATCH, 'before_dump_target_mismatch',
            'before_dump was captured from document %s, the write targets %s'
            % (dump_document, expected_document),
            expected=expected_document, actual=dump_document))
    if not dump_project or not dump_document:
        refusals.append(_refusal(
            schemas.FAILURE_PRECONDITION_REFUSED, 'unbound_before_dump',
            'before_dump.capture does not identify both its project and '
            'document; the dump cannot be bound to the target'))

    target_window = _text(target.get('window_id'))
    observed_window = _text(_first(
        observation.get('host') or {}, 'window_id', 'windowId'))
    dump_window = _text(_first(capture, 'windowId', 'window_id'))
    runtime_window = _text(window)
    expected_window = target_window or observed_window
    if not observed_window:
        refusals.append(_refusal(
            schemas.FAILURE_PRECONDITION_REFUSED, 'unbound_before_dump',
            'the fresh observation does not identify its window; a PCB write '
            'cannot be bound to a live host window'))
    if target_window and observed_window and target_window != observed_window:
        refusals.append(_refusal(
            schemas.FAILURE_TARGET_MISMATCH, 'before_dump_target_mismatch',
            'the observation was captured from window %s, the contract targets '
            'window %s' % (observed_window, target_window),
            expected=target_window, actual=observed_window))
    if expected_window and not dump_window:
        refusals.append(_refusal(
            schemas.FAILURE_PRECONDITION_REFUSED, 'unbound_before_dump',
            'before_dump.capture does not identify its window; the dump '
            'cannot be bound to the target window'))
    elif expected_window and dump_window != expected_window:
        refusals.append(_refusal(
            schemas.FAILURE_TARGET_MISMATCH, 'before_dump_target_mismatch',
            'before_dump was captured from window %s, the write targets '
            'window %s' % (dump_window, expected_window),
            expected=expected_window, actual=dump_window))
    if runtime_window and runtime_window != expected_window:
        refusals.append(_refusal(
            schemas.FAILURE_TARGET_MISMATCH, 'before_dump_target_mismatch',
            'the runtime --window %s does not match the observed/target window '
            '%s' % (runtime_window, expected_window),
            expected=expected_window, actual=runtime_window))

    dump_hash = _text(_first(dump, 'semanticSha256', 'semantic_sha256'))
    observed_hash = _text(_first(pcb, 'semanticSha256', 'semantic_sha256'))
    if not dump_hash or not observed_hash:
        refusals.append(_refusal(
            schemas.FAILURE_PRECONDITION_REFUSED, 'unbound_before_dump',
            'before_dump or the fresh observation carries no PCB '
            'semanticSha256; content binding cannot be verified'))
    elif dump_hash != observed_hash:
        refusals.append(_refusal(
            schemas.FAILURE_STALE_BASELINE, 'before_dump_stale',
            'before_dump hash %s does not match the fresh observation hash %s'
            % (dump_hash, observed_hash),
            expected=observed_hash, actual=dump_hash))

    if not isinstance(pcb, dict):
        refusals.append(_refusal(
            schemas.FAILURE_PRECONDITION_REFUSED, 'missing_observation',
            'the fresh observation carries no PCB section; before_dump cannot '
            'be bound to the live board'))
    else:
        component_problem = _dump_component_problem(dump, pcb)
        if component_problem:
            refusals.append(_refusal(
                schemas.FAILURE_STALE_BASELINE, 'before_dump_stale',
                component_problem))
    return refusals


def _plan_ops_for_compile(plan, kind, ops):
    """Build the plan object pcb_apply_plan expects for the chosen ops.

    Legacy ``placements`` are converted into playbook ``place`` operations so
    the one compiler path is used for both dialects.
    """
    if isinstance(plan, list) or (isinstance(plan, dict) and
                                  'placements' in plan and 'ops' not in plan):
        if kind != 'pcb':
            return None
        placements = plan if isinstance(plan, list) else plan.get('placements')
        raw_ops = []
        for op in ops:
            placement = copy.deepcopy(placements[op['raw_index']])
            item = {'op': 'place',
                    'designator': placement.get('designator'),
                    'to': {key: placement.get(key)
                           for key in ('x', 'y', 'rotation', 'layer')
                           if key in placement}}
            if placement.get('reason'):
                item['reason'] = placement['reason']
            raw_ops.append(item)
        result = {key: copy.deepcopy(value) for key, value in
                  (plan.items() if isinstance(plan, dict) else [])}
        result.pop('placements', None)
        result.setdefault('schema', PLAYBOOK_SCHEMA)
        result['ops'] = raw_ops
        return result
    result = copy.deepcopy(plan)
    if kind == 'pcb':
        if 'ops' in result:
            result['ops'] = [copy.deepcopy(plan['ops'][op['raw_index']])
                             for op in ops]
        else:
            result['placements'] = [
                copy.deepcopy(plan['placements'][op['raw_index']])
                for op in ops]
    else:
        result['ops'] = [copy.deepcopy(plan['ops'][op['raw_index']])
                         for op in ops]
    return result


def _fill_place_primitive_ids(plan_copy, board):
    """Fill an omitted place ``primitive_id`` from the measured board.

    pcb_apply_plan expects the plan to name the mutation handle.  A scoped
    plan generated by this layer may omit it because the contract baseline
    already identified the designator; filling it here does not bypass the
    stale-ID check when the plan does declare one.
    """
    if not isinstance(plan_copy, dict) or not isinstance(board, dict):
        return plan_copy
    components = {str(item.get('designator')): item
                  for item in board.get('components') or []
                  if isinstance(item, dict) and item.get('designator')}
    for op in plan_copy.get('ops') or []:
        if not isinstance(op, dict) or op.get('op') != 'place':
            continue
        if op.get('primitive_id') or op.get('primitiveId'):
            continue
        component = components.get(str(op.get('designator')))
        if component is None:
            continue
        primitive_id = component.get('primitiveId') or \
            component.get('primitive_id')
        if primitive_id:
            op['primitive_id'] = primitive_id
    return plan_copy


def _compile_pcb(plan, kind, ops, observation, *, timeout=120,
                 doc=None, project=None):
    pcb_apply_plan, _pcb_cli = _pcb_modules()
    board = _raw_before_dump(plan)
    if board is None:
        return {'steps': [], 'step_scope': [], 'records': [],
                'refusals': [{'failure_class':
                              schemas.FAILURE_PRECONDITION_REFUSED,
                              'reason': 'missing_before_dump',
                              'message': 'a raw plan.before_dump is required '
                                         'to compile PCB operations; a '
                                         'normalized observation is not a '
                                         'substitute'}],
                'normalized_ops': [], 'noops': []}
    plan_for_compile = _plan_ops_for_compile(plan, kind, ops)
    plan_for_compile = _fill_place_primitive_ids(plan_for_compile, board)
    try:
        board_view = pcb_apply_plan.normalize_board(board)
        if isinstance(plan_for_compile, list) or 'placements' in plan_for_compile:
            normalized, placements, refused, noops = \
                pcb_apply_plan._legacy_placement_ops(plan_for_compile,
                                                     board_view)
        else:
            normalized, placements, refused, _primitive_ids, noops = \
                pcb_apply_plan._normalize_playbook_ops(plan_for_compile,
                                                       board_view)
    except pcb_apply_plan.PlanInputError as exc:
        return {'steps': [], 'step_scope': [], 'records': [],
                'refusals': [{'failure_class': schemas.FAILURE_INVALID_INPUT,
                              'reason': 'invalid_plan', 'message': str(exc)}],
                'normalized_ops': [], 'noops': []}
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        return {'steps': [], 'step_scope': [], 'records': [],
                'refusals': [{'failure_class': schemas.FAILURE_INVALID_INPUT,
                              'reason': 'invalid_plan', 'message': str(exc)}],
                'normalized_ops': [], 'noops': []}
    refusals = []
    for item in refused:
        item_kind = _text(item.get('kind'))
        failure_class = schemas.FAILURE_PRECONDITION_REFUSED
        if item_kind in ('stale_from_pose', 'stale_plan_object'):
            failure_class = schemas.FAILURE_STALE_BASELINE
        refusals.append({
            'failure_class': failure_class,
            'reason': item_kind or 'plan_refused',
            'message': _text(item.get('message')) or 'plan refused by the '
                                                     'PCB compiler',
            'detail': item,
        })
    if refusals:
        return {'steps': [], 'step_scope': [], 'records': [],
                'refusals': refusals, 'normalized_ops': normalized,
                'noops': noops}
    documents = (observation or {}).get('documents') or []
    doc_name = _text(doc) or (_text(documents[0].get('name'))
                              if documents else 'PCB1')
    project_name = _text(project) or _text(
        ((observation or {}).get('project') or {}).get('name')) or 'project'
    args = types.SimpleNamespace(
        plan='<in-memory>', project=project_name, doc=doc_name,
        out_dump=os.path.join(tempfile.gettempdir(), 'hds-scope-preview.json'),
        no_reload=not bool((_current_flags(plan) or {}).get('reload', True)))
    compile_scope = {'designators': [], 'nets': []}
    try:
        playbook, summary, records = pcb_apply_plan.compile_playbook(
            normalized, compile_scope, args, max(1, int(timeout)))
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        return {'steps': [], 'step_scope': [], 'records': [],
                'refusals': [{'failure_class': schemas.FAILURE_INVALID_INPUT,
                              'reason': 'invalid_plan', 'message': str(exc)}],
                'normalized_ops': normalized, 'noops': noops}
    step_scope = []
    by_step = {}
    for record in records:
        for step_id in record.get('steps') or []:
            by_step[step_id] = record.get('index')
    for step in summary:
        index = by_step.get(step.get('id'))
        if index is not None and index < len(ops):
            op = ops[index]
            decision = _scope_decision({}, op)  # scope is supplied by caller
            basis = 'operation'
        else:
            decision = {'decision': 'in_scope', 'basis': 'read_only_or_control'}
        step_scope.append({'step_id': step.get('id'),
                           'decision': decision['decision'],
                           'basis': basis,
                           'op_index': index})
    return {'steps': summary, 'step_scope': step_scope, 'records': records,
            'refusals': [], 'normalized_ops': normalized,
            'noops': noops, 'playbook': playbook}


def _current_flags(plan):
    kind, _ops, flags, error = _normalize_plan_ops(plan)
    return flags if not error else None


def _compile_schematic(plan, ops, flags):
    steps = []
    step_scope = []
    for op in ops:
        index = op['index']
        if op['op'] == 'move_text':
            step = {
                'id': 'move_text-%d' % index,
                'action': 'schematic.text.move',
                'payload': {'moves': [{'primitiveId': op['primitive_id'],
                                       'x': op['x'], 'y': op['y']}]},
                'assert': {'$.verified': 'true'},
            }
        else:
            patch = copy.deepcopy(op.get('patch') or {})
            step = {
                'id': 'move_component-%d' % index,
                'action': 'schematic.component.modify',
                'payload': {'id': op.get('primitive_id'), 'patch': patch},
                'assert': {'$.verified': 'true'},
            }
        steps.append(step)
        step_scope.append({'step_id': step['id'], 'decision': 'pending',
                           'basis': 'operation', 'op_index': index})
    if (flags or {}).get('save'):
        steps.append({'id': 'save', 'action': 'schematic.save',
                      'payload': {}, 'assert': {'$.saved': 'true'}})
        step_scope.append({'step_id': 'save', 'decision': 'in_scope',
                           'basis': 'action_allowed', 'op_index': None})
    if (flags or {}).get('reload'):
        steps.append({'id': 'reload', 'action': 'sch.reload', 'payload': {},
                      'assert': {}})
        step_scope.append({'step_id': 'reload', 'decision': 'in_scope',
                           'basis': 'action_allowed', 'op_index': None})
    return {'steps': steps, 'step_scope': step_scope, 'records': [],
            'refusals': [], 'normalized_ops': [], 'noops': []}


# ---------------------------------------------------------------------------
# plan validation
# ---------------------------------------------------------------------------

def _refusal(failure_class, reason, message, **detail):
    item = {'failure_class': failure_class, 'reason': reason,
            'message': message}
    if detail:
        item['detail'] = detail
    return item


def _action_refusal(op, allowed):
    kind = op['op']
    action = KIND_ACTION.get(kind)
    if kind == 'place':
        if schemas.ACTION_MOVE_COMPONENT not in allowed:
            return _refusal(schemas.FAILURE_OUT_OF_SCOPE,
                            'action_not_allowed',
                            'action move_component is not in allowed_actions',
                            action='move_component', op_index=op['index'])
    elif kind in ('move_component', 'rotate_component'):
        if schemas.ACTION_MOVE_COMPONENT not in allowed and \
                schemas.ACTION_ROTATE_COMPONENT not in allowed:
            return _refusal(schemas.FAILURE_OUT_OF_SCOPE,
                            'action_not_allowed',
                            'component modification is not in allowed_actions',
                            action='move_component', op_index=op['index'])
    elif action not in allowed:
        return _refusal(schemas.FAILURE_OUT_OF_SCOPE, 'action_not_allowed',
                        'action %s is not in allowed_actions' % action,
                        action=action, op_index=op['index'])
    return None


def _identity_refusal(plan, ops, kind):
    if isinstance(plan, dict):
        for key in ('identity_change', 'replace_document', 'create_document',
                    'delete_document', 'new_document'):
            if plan.get(key) is True:
                return _refusal(schemas.FAILURE_PRECONDITION_REFUSED,
                                'identity_change',
                                'plan would change document identity (%s)' % key,
                                field=key)
    for op in ops:
        if op['op'] in IDENTITY_OP_KINDS:
            return _refusal(schemas.FAILURE_PRECONDITION_REFUSED,
                            'identity_change',
                            'operation %r changes document identity' % op['op'],
                            op_index=op['index'])
        if op['op'] == 'place':
            to = op.get('to') or {}
            if to.get('designator') and \
                    _text(to.get('designator')) != op.get('designator'):
                return _refusal(schemas.FAILURE_PRECONDITION_REFUSED,
                                'identity_change',
                                'place op would rename the component',
                                op_index=op['index'])
        if op['op'] in ('move_component', 'rotate_component'):
            for key in (op.get('patch') or {}):
                if key in IDENTITY_PATCH_KEYS:
                    return _refusal(schemas.FAILURE_PRECONDITION_REFUSED,
                                    'identity_change',
                                    'component patch key %r changes identity'
                                    % key, op_index=op['index'])
    return None


def _baseline_refusals(contract, plan, before=None):
    refusals = []
    expected = _text((contract.get('baseline') or {}).get('semantic_sha256'))
    if not expected:
        refusals.append(_refusal(
            schemas.FAILURE_PRECONDITION_REFUSED, 'unknown_baseline',
            'contract baseline has no semantic_sha256'))
    plan_hashes, observation, observation_hash, before_hash = \
        _plan_base(plan, before=before)
    if observation is not None and not observation_hash and not expected:
        refusals.append(_refusal(
            schemas.FAILURE_PRECONDITION_REFUSED, 'unknown_baseline',
            'plan observation has no revision.semantic_sha256'))
    if before is not None and not before_hash and expected:
        refusals.append(_refusal(
            schemas.FAILURE_PRECONDITION_REFUSED, 'unknown_baseline',
            'fresh observation has no revision.semantic_sha256'))
    if not plan_hashes and not before_hash:
        refusals.append(_refusal(
            schemas.FAILURE_PRECONDITION_REFUSED, 'missing_baseline',
            'plan does not declare a baseline (base.semantic_sha256 or an '
            'observation)'))
    if expected:
        for candidate in plan_hashes:
            if candidate != expected:
                refusals.append(_refusal(
                    schemas.FAILURE_STALE_BASELINE, 'stale_baseline',
                    'plan baseline %s does not match contract baseline %s'
                    % (candidate, expected),
                    expected=expected, actual=candidate))
        if before_hash and before_hash != expected:
            refusals.append(_refusal(
                schemas.FAILURE_STALE_BASELINE, 'stale_baseline',
                'fresh observation baseline %s does not match contract '
                'baseline %s' % (before_hash, expected),
                expected=expected, actual=before_hash))
        if observation is not None:
            per_document = (observation.get('revision') or {}).get(
                'per_document') or {}
            expected_per_document = (contract.get('baseline') or {}).get(
                'per_document') or {}
            for uuid, digest in sorted(expected_per_document.items()):
                if uuid in per_document and per_document[uuid] != digest:
                    refusals.append(_refusal(
                        schemas.FAILURE_STALE_BASELINE, 'stale_baseline',
                        'document %s changed since the contract baseline'
                        % uuid, document_uuid=uuid, expected=digest,
                        actual=per_document[uuid]))
    return refusals


def _observation_target_refusal(contract, observation):
    if not isinstance(observation, dict):
        return None
    target = contract.get('target') or {}
    expected_project = _text(target.get('project_uuid'))
    project = observation.get('project') or {}
    observed_project = _text(_first(project, 'uuid', 'project_uuid',
                                    'projectUuid'))
    if expected_project and observed_project and \
            observed_project != expected_project:
        return _refusal(schemas.FAILURE_TARGET_MISMATCH, 'target_mismatch',
                        'observation belongs to project %r, contract targets %r'
                        % (observed_project, expected_project),
                        expected=expected_project, actual=observed_project)
    expected_docs = {_text(document.get('uuid')) for document in
                     target.get('documents') or [] if _text(document.get('uuid'))}
    if expected_docs:
        observed_docs = {_text(document.get('uuid')) for document in
                         observation.get('documents') or []
                         if isinstance(document, dict) and
                         _text(document.get('uuid'))}
        if observed_docs and not (observed_docs & expected_docs):
            return _refusal(schemas.FAILURE_TARGET_MISMATCH,
                            'target_mismatch',
                            'observation documents do not overlap the contract '
                            'target documents', expected=sorted(expected_docs),
                            actual=sorted(observed_docs))
    for key in ('pcb', 'schematic'):
        section = observation.get(key)
        if not isinstance(section, dict):
            continue
        document_uuid = _text(_first(section, 'document_uuid', 'documentUuid'))
        if document_uuid and expected_docs and document_uuid not in expected_docs:
            return _refusal(schemas.FAILURE_TARGET_MISMATCH,
                            'target_mismatch',
                            '%s section belongs to document %s outside the '
                            'contract target' % (key, document_uuid),
                            expected=sorted(expected_docs),
                            actual=document_uuid)
    return None


def _validate_plan_internal(contract, plan, *, before=None):
    refusals = []
    unknown = []
    notes = []
    try:
        schemas.validate_modification(contract)
    except (schemas.ContractError, TypeError, AttributeError) as exc:
        return {
            'schema': SCHEMA_PLAN_VALIDATION, 'ok': False,
            'failure_class': schemas.FAILURE_INVALID_INPUT,
            'contract_id': None, 'plan_kind': None, 'document': None,
            'actions': [], 'steps': [], 'step_scope': [], 'skipped': [],
            'baseline': None, 'target': None, 'scope': None,
            'refusals': [_refusal(schemas.FAILURE_INVALID_INPUT,
                                  'invalid_contract', str(exc))],
            'unknown': [], 'notes': [],
        }
    kind, ops, flags, error = _normalize_plan_ops(plan)
    if error:
        return {
            'schema': SCHEMA_PLAN_VALIDATION, 'ok': False,
            'failure_class': schemas.FAILURE_INVALID_INPUT,
            'contract_id': contract.get('id'), 'plan_kind': kind,
            'document': None, 'actions': [], 'steps': [], 'step_scope': [],
            'skipped': [], 'baseline': None, 'target': None,
            'scope': contract.get('scope'),
            'refusals': [_refusal(schemas.FAILURE_INVALID_INPUT,
                                  'invalid_plan', error)],
            'unknown': [], 'notes': [],
        }
    document, document_error = _pick_document(contract, kind, plan)
    if document_error:
        refusals.append(_refusal(schemas.FAILURE_TARGET_MISMATCH,
                                 'target_mismatch', document_error,
                                 plan_kind=kind))
    project_error = _plan_project_refusal(contract, plan)
    if project_error:
        refusals.append(_refusal(schemas.FAILURE_TARGET_MISMATCH,
                                 'target_mismatch', project_error))
    scope = normalize_scope(contract.get('scope'))
    allowed = set(contract.get('allowed_actions') or [])
    if flags.get('save') and schemas.ACTION_SAVE not in allowed:
        refusals.append(_refusal(schemas.FAILURE_OUT_OF_SCOPE,
                                 'action_not_allowed',
                                 'plan saves but save is not in allowed_actions',
                                 action=schemas.ACTION_SAVE))
    if flags.get('reload') and schemas.ACTION_RELOAD not in allowed:
        refusals.append(_refusal(schemas.FAILURE_OUT_OF_SCOPE,
                                 'action_not_allowed',
                                 'plan reloads but reload is not in '
                                 'allowed_actions', action=schemas.ACTION_RELOAD))
    identities = [operation_key(op) for op in ops]
    duplicates = {key for key in identities if identities.count(key) > 1}
    if duplicates:
        refusals.append(_refusal(
            schemas.FAILURE_INVALID_INPUT, 'duplicate_operation',
            'plan contains duplicate operations; a re-run would create '
            'duplicate tracks/vias/text', operation_keys=sorted(duplicates)))
    for op in ops:
        refusal = _action_refusal(op, allowed)
        if refusal:
            refusals.append(refusal)
    identity = _identity_refusal(plan, ops, kind)
    if identity:
        refusals.append(identity)
    fresh_observation = before if before is not None else \
        _plan_observation(plan)
    observation = fresh_observation or \
        (contract.get('baseline') or {}).get('facts')
    observation = _as_observation(observation) if observation else None
    fresh_observation = _as_observation(fresh_observation) \
        if fresh_observation else None
    if observation is not None:
        target_refusal = _observation_target_refusal(contract, observation)
        if target_refusal:
            refusals.append(target_refusal)
    refusals.extend(_baseline_refusals(contract, plan, before=before))
    if kind == 'pcb' and fresh_observation is not None:
        # Bind the raw dump to a plan-carried fresh observation only.  The
        # contract baseline is not fresh, and using it here would turn a
        # missing live baseline into an unrelated precondition error.
        refusals.extend(_before_dump_refusals(contract, plan,
                                              fresh_observation,
                                              document=document))
    actions = []
    for op in ops:
        decision = _scope_decision(scope, op)
        if decision['decision'] != 'in_scope':
            refusals.append(_refusal(
                schemas.FAILURE_OUT_OF_SCOPE, 'out_of_scope',
                'operation %d (%s) is outside scope.writable' %
                (op['index'], op['op']),
                op_index=op['index'], operation=op['op'],
                object=_op_object(op) or None, net=op.get('net')))
        locked = _locked_target(op, observation) if observation else None
        if locked is True:
            refusals.append(_refusal(
                schemas.FAILURE_PRECONDITION_REFUSED, 'locked_object',
                'operation %d targets a locked object' % op['index'],
                op_index=op['index'], object=_op_object(op) or None))
        elif locked is None:
            unknown.append({'field': 'locked[%d]' % op['index'],
                            'reason': 'lock state is not measurable'})
        present = _op_present(op, observation) if observation else None
        actions.append({
            'index': op['index'], 'raw_index': op['raw_index'],
            'op': op['op'], 'action': KIND_ACTION.get(op['op']),
            'operation_key': operation_key(op),
            'object': _op_object(op) or None,
            'designator': op.get('designator'),
            'net': op.get('net'),
            'scope': decision,
            'already_applied': present,
            'document_uuid': (document or {}).get('uuid'),
        })
    compiled = None
    if not refusals:
        if kind == 'pcb':
            compiled = _compile_pcb(
                plan, kind, ops, observation,
                timeout=120,
                doc=(document or {}).get('name') or
                    (document or {}).get('uuid'),
                project=((observation or {}).get('project') or {}).get('name'))
        else:
            compiled = _compile_schematic(plan, ops, flags)
        if compiled and compiled.get('refusals'):
            refusals.extend(compiled['refusals'])
            compiled = None
    steps = (compiled or {}).get('steps') or []
    step_scope = (compiled or {}).get('step_scope') or []
    if steps and kind == 'pcb':
        by_step = {}
        for record in (compiled or {}).get('records') or []:
            for step_id in record.get('steps') or []:
                by_step[step_id] = record.get('index')
        for entry in step_scope:
            index = entry.get('op_index')
            if index is not None and index < len(actions):
                entry['decision'] = actions[index]['scope']['decision']
                entry['basis'] = actions[index]['scope']['basis']
    elif steps and kind == 'schematic':
        by_index = {action['index']: action for action in actions}
        for entry in step_scope:
            index = entry.get('op_index')
            if index is not None and index in by_index:
                entry['decision'] = by_index[index]['scope']['decision']
                entry['basis'] = by_index[index]['scope']['basis']
    skipped = [action for action in actions
               if action.get('already_applied') is True]
    baseline_info = {
        'expected': (contract.get('baseline') or {}).get('semantic_sha256'),
        'plan': _plan_base(plan, before=before)[0],
    }
    if observation is not None:
        baseline_info['observed'] = _observation_revision(observation)[0]
    result = {
        'schema': SCHEMA_PLAN_VALIDATION,
        'ok': not refusals,
        'failure_class': (refusals[0]['failure_class'] if refusals else None),
        'contract_id': contract.get('id'),
        'plan_kind': kind,
        'document': document,
        'flags': flags,
        'actions': actions,
        'steps': steps,
        'step_scope': step_scope,
        'skipped': skipped,
        'baseline': baseline_info,
        'target': contract.get('target'),
        'scope': scope,
        'refusals': refusals,
        'unknown': unknown,
        'notes': notes,
        'writes_sent': 0,
    }
    if compiled:
        result['noops'] = compiled.get('noops') or []
        result['compiled_operations'] = compiled.get('normalized_ops') or []
    return result


def validate_plan(contract, plan):
    """Validate ``plan`` against ``contract`` without any side effect."""
    return _validate_plan_internal(contract, plan)


# ---------------------------------------------------------------------------
# preview
# ---------------------------------------------------------------------------

def _annotate_steps(steps, step_scope):
    """Copy compiled steps and attach their scope decision inline."""
    by_step = {entry.get('step_id'): entry for entry in step_scope or []}
    result = []
    for step in steps or []:
        entry = by_step.get(step.get('id')) or {}
        item = copy.deepcopy(step)
        item['scope'] = {'decision': entry.get('decision', 'unknown'),
                         'basis': entry.get('basis')}
        result.append(item)
    return result


def preview(contract, plan, *, before=None):
    """Return the compiled steps and scope decisions; never writes."""
    validation = _validate_plan_internal(contract, plan, before=before)
    step_scope = validation.get('step_scope') or []
    payload = {
        'schema': schemas.SCHEMA_PREVIEW,
        'ok': validation.get('ok', False),
        'tool_version': schemas.TOOL_VERSION,
        'generated_at': schemas.now_utc(),
        'contract_id': validation.get('contract_id'),
        'plan_kind': validation.get('plan_kind'),
        'document': validation.get('document'),
        'write_authorized': not bool(contract.get('preview_only')),
        'simulated': _plan_simulated(plan),
        'writes_sent': 0,
        'steps': _annotate_steps(validation.get('steps') or [], step_scope),
        'step_scope': step_scope,
        'scope_decisions': step_scope,
        'actions': validation.get('actions') or [],
        'skipped': validation.get('skipped') or [],
        'baseline': validation.get('baseline'),
        'scope': validation.get('scope'),
        'refusals': validation.get('refusals') or [],
        'unknown': validation.get('unknown') or [],
        'notes': ['preview only: no CLI call and no file write were made'],
    }
    if not payload['ok']:
        payload['failure_class'] = validation.get('failure_class')
    return payload


# ---------------------------------------------------------------------------
# baseline check
# ---------------------------------------------------------------------------

def _baseline_payload(status, *, ok=False, failure_class=None, reasons=None,
                      expected=None, current=None, target=None):
    payload = {
        'schema': SCHEMA_BASELINE_CHECK,
        'ok': ok,
        'status': status,
        'generated_at': schemas.now_utc(),
        'expected': expected,
        'current': current,
        'target': target,
        'reasons': reasons or [],
    }
    if failure_class:
        payload['failure_class'] = failure_class
    return payload


def check_baseline(contract, current_observation):
    """Compare the contract baseline with a freshly measured observation."""
    try:
        schemas.validate_modification(contract)
    except (schemas.ContractError, TypeError, AttributeError) as exc:
        return _baseline_payload('unknown', failure_class=(
            schemas.FAILURE_INVALID_INPUT), reasons=[str(exc)])
    current = _as_observation(current_observation)
    if not isinstance(current, dict):
        return _baseline_payload(
            'unknown', failure_class=schemas.FAILURE_INVALID_INPUT,
            reasons=['current observation must be an object'])
    expected = contract.get('baseline') or {}
    expected_hash = _text(expected.get('semantic_sha256'))
    current_hash, current_per_document, _captured = \
        _observation_revision(current)
    target_refusal = _observation_target_refusal(contract, current)
    if target_refusal:
        return _baseline_payload(
            'target_mismatch', failure_class=(
                schemas.FAILURE_TARGET_MISMATCH),
            reasons=[target_refusal['message']],
            expected=expected_hash, current=current_hash,
            target=contract.get('target'))
    if not expected_hash:
        return _baseline_payload(
            'unknown', failure_class=schemas.FAILURE_PRECONDITION_REFUSED,
            reasons=['contract baseline has no semantic_sha256'],
            expected=None, current=current_hash,
            target=contract.get('target'))
    if not current_hash:
        return _baseline_payload(
            'unknown', failure_class=schemas.FAILURE_PRECONDITION_REFUSED,
            reasons=['current observation has no revision.semantic_sha256'],
            expected=expected_hash, current=None,
            target=contract.get('target'))
    reasons = []
    if current_hash != expected_hash:
        reasons.append('current baseline %s does not match contract baseline '
                       '%s' % (current_hash, expected_hash))
    expected_per_document = expected.get('per_document') or {}
    for uuid, digest in sorted(expected_per_document.items()):
        if uuid in current_per_document and current_per_document[uuid] != digest:
            reasons.append('document %s changed since the contract baseline'
                           % uuid)
    if reasons:
        return _baseline_payload(
            'stale', failure_class=schemas.FAILURE_STALE_BASELINE,
            reasons=reasons, expected=expected_hash, current=current_hash,
            target=contract.get('target'))
    return _baseline_payload(
        'current', ok=True, expected=expected_hash, current=current_hash,
        reasons=['baseline matches'], target=contract.get('target'))


# ---------------------------------------------------------------------------
# diff
# ---------------------------------------------------------------------------

def _new_change(category, kind, **fields):
    change = {'category': category, 'kind': kind}
    change.update({key: value for key, value in fields.items()
                   if value is not None})
    return change


def _change_bbox(change):
    box = _bbox(change.get('bbox'))
    if box is not None:
        return box
    return _bbox_of_points(change.get('points') or [])


def _classify_change(change, objects, nets, regions, tolerance):
    if not objects and not nets and not regions:
        change['in_scope'] = True
        change['scope_basis'] = 'no_scope'
        return change
    object_id = _text(change.get('object') or change.get('designator'))
    if object_id and object_id in objects:
        change['in_scope'] = True
        change['scope_basis'] = 'object:%s' % object_id
        return change
    primitive_id = _text(change.get('primitive_id'))
    if primitive_id and primitive_id in objects:
        change['in_scope'] = True
        change['scope_basis'] = 'object:%s' % primitive_id
        return change
    # A through-hole change belongs to the component that owns the hole.  A
    # moved THT part moves its holes too; counting those as unrelated would
    # make every THT placement fail the outside-scope gate.  Only attribute
    # when every changed hole names an in-scope owner, and never when a
    # changed hole has no owner at all.
    owners = {_text(item) for item in change.get('designators') or []}
    owners.discard(None)
    if owners and not change.get('unattributed') and owners <= objects:
        change['in_scope'] = True
        change['scope_basis'] = 'hole-owner:%s' % ','.join(sorted(owners))
        return change
    net = _text(change.get('net'))
    if net and net in nets:
        change['in_scope'] = True
        change['scope_basis'] = 'net:%s' % net
        return change
    for net in change.get('nets') or []:
        if _text(net) in nets:
            change['in_scope'] = True
            change['scope_basis'] = 'net:%s' % _text(net)
            return change
    box = _change_bbox(change)
    for index, region in enumerate(regions):
        if box is not None and _bbox_intersects(box, region,
                                               tolerance['position']):
            change['in_scope'] = True
            change['scope_basis'] = 'region:%d' % index
            return change
    change['in_scope'] = False
    change['scope_basis'] = None
    return change


def _add_unknown(unknown, field, reason):
    item = {'field': field, 'reason': reason}
    if item not in unknown:
        unknown.append(item)


def _pad_net_map(component):
    if component is None or not component.get('pads_readable'):
        return None
    return {str(pad.get('number')): pad.get('net')
            for pad in component.get('pads') or []}


def _diff_pcb(pcb_before, pcb_after, tolerance, changes, unknown):
    pcb_before = pcb_before or {}
    pcb_after = pcb_after or {}
    result = {}
    before_map, before_avail = _pcb_component_map(pcb_before)
    after_map, after_avail = _pcb_component_map(pcb_after)
    component = {'status': 'available', 'added': [], 'removed': [],
                 'identity_changed': [], 'pose_changed': [],
                 'layer_changed': [], 'locked_changed': [],
                 'pad_net_changed': [], 'all': []}
    if before_map is None or after_map is None or \
            before_avail == 'unavailable' or after_avail == 'unavailable':
        component['status'] = 'unknown'
        _add_unknown(unknown, 'pcb.components',
                     'component list is not readable on both sides')
    else:
        if before_avail == 'partial' or after_avail == 'partial':
            _add_unknown(unknown, 'pcb.components',
                         'component list is partial')
        for designator in sorted(set(before_map) | set(after_map)):
            first = before_map.get(designator)
            second = after_map.get(designator)
            box = _bbox_union(first.get('bbox') if first else None,
                              second.get('bbox') if second else None)
            if first is None or second is None:
                change = _new_change(
                    'pcb.component', 'added' if first is None else 'removed',
                    designator=designator, object=designator, bbox=box,
                    locked=(second or first or {}).get('locked'))
                component['added' if first is None else 'removed'].append(
                    change)
                component['all'].append(change)
                if first is not None and first.get('locked') is True:
                    locked_change = dict(change, kind='locked_removed')
                    component['locked_changed'].append(locked_change)
                    component['all'].append(locked_change)
                continue
            identity = {
                'unique_id': first.get('unique_id'),
                'device': _json_value(first.get('device')),
            }
            identity_after = {
                'unique_id': second.get('unique_id'),
                'device': _json_value(second.get('device')),
            }
            if identity != identity_after:
                change = _new_change(
                    'pcb.component', 'identity_changed', designator=designator,
                    object=designator, bbox=box, before=identity,
                    after=identity_after)
                component['identity_changed'].append(change)
                component['all'].append(change)
            pose_before = {'x': first.get('x'), 'y': first.get('y'),
                           'rotation': first.get('rotation')}
            pose_after = {'x': second.get('x'), 'y': second.get('y'),
                          'rotation': second.get('rotation')}
            pose_known = all(value is not None for value in
                             (pose_before['x'], pose_before['y'],
                              pose_after['x'], pose_after['y']))
            if not pose_known:
                _add_unknown(unknown, 'pcb.components[%s].pose' % designator,
                             'x/y pose is not measured on both sides')
            rotation_known = (pose_before['rotation'] is not None and
                              pose_after['rotation'] is not None)
            pose_changed = (pose_known and (
                not _same_number(pose_before['x'], pose_after['x'],
                                 tolerance['position']) or
                not _same_number(pose_before['y'], pose_after['y'],
                                 tolerance['position'])))
            if rotation_known and not _same_angle(
                    pose_before['rotation'], pose_after['rotation'],
                    tolerance['angle']):
                pose_changed = True
            if pose_changed:
                change = _new_change(
                    'pcb.component', 'pose_changed', designator=designator,
                    object=designator, bbox=box, before=pose_before,
                    after=pose_after)
                component['pose_changed'].append(change)
                component['all'].append(change)
            if first.get('layer') is not None and \
                    second.get('layer') is not None and \
                    _int_or_none(first.get('layer')) != \
                    _int_or_none(second.get('layer')):
                change = _new_change(
                    'pcb.component', 'layer_changed', designator=designator,
                    object=designator, bbox=box,
                    before=first.get('layer'), after=second.get('layer'))
                component['layer_changed'].append(change)
                component['all'].append(change)
            if first.get('locked') is not None and \
                    second.get('locked') is not None and \
                    bool(first.get('locked')) != bool(second.get('locked')):
                change = _new_change(
                    'pcb.component', 'locked_changed', designator=designator,
                    object=designator, bbox=box,
                    before=bool(first.get('locked')),
                    after=bool(second.get('locked')))
                component['locked_changed'].append(change)
                component['all'].append(change)
            elif first.get('locked') is None or \
                    second.get('locked') is None:
                _add_unknown(unknown, 'pcb.components[%s].locked' % designator,
                             'lock state is not measured on both sides')
            if first.get('locked') is True and \
                    (pose_changed or
                     first.get('layer') != second.get('layer')):
                locked_change = _new_change(
                    'pcb.component', 'locked_object_changed',
                    designator=designator, object=designator, bbox=box)
                component['locked_changed'].append(locked_change)
                component['all'].append(locked_change)
            before_pads = _pad_net_map(first)
            after_pads = _pad_net_map(second)
            if before_pads is None or after_pads is None:
                _add_unknown(unknown, 'pcb.components[%s].pads' % designator,
                             'pad/net map is not measured on both sides')
            elif before_pads != after_pads:
                changed = sorted(set(before_pads) | set(after_pads))
                net_changes = []
                for pad in changed:
                    if before_pads.get(pad) != after_pads.get(pad):
                        net_changes.append({'pad': pad,
                                            'before': before_pads.get(pad),
                                            'after': after_pads.get(pad)})
                change = _new_change(
                    'pcb.component', 'pad_net_changed', designator=designator,
                    object=designator, bbox=box, pads=net_changes,
                    net=(net_changes[0]['before'] if len(net_changes) == 1
                         else None),
                    nets=sorted({_text(item['before']) for item in net_changes
                                 if item['before']} |
                                {_text(item['after']) for item in net_changes
                                 if item['after']}))
                component['pad_net_changed'].append(change)
                component['all'].append(change)
    result['components'] = component
    changes.extend(component['all'])

    outline_before, outline_bbox_before = _pcb_outline(pcb_before)
    outline_after, outline_bbox_after = _pcb_outline(pcb_after)
    outline = {'status': 'available', 'changed': False, 'change': None}
    if outline_before is None or outline_after is None:
        outline['status'] = 'unknown'
        _add_unknown(unknown, 'pcb.outline',
                     'outline points are not measured on both sides')
    else:
        outline_change = None
        if len(outline_before) != len(outline_after):
            outline_change = _new_change(
                'pcb.outline', 'outline_changed',
                before=len(outline_before), after=len(outline_after),
                bbox=_bbox_union(outline_bbox_before, outline_bbox_after))
        else:
            maximum = 0.0
            for first_point, second_point in zip(outline_before,
                                                 outline_after):
                distance = math.hypot(first_point[0] - second_point[0],
                                      first_point[1] - second_point[1])
                maximum = max(maximum, distance)
            if maximum > tolerance['position']:
                outline_change = _new_change(
                    'pcb.outline', 'outline_changed', max_deviation=maximum,
                    points=len(outline_before),
                    bbox=_bbox_union(outline_bbox_before, outline_bbox_after))
        if outline_change:
            outline['changed'] = True
            outline['change'] = outline_change
            changes.append(outline_change)
    result['outline'] = outline

    copper_before = pcb_before.get('copper') if isinstance(
        pcb_before.get('copper'), dict) else {}
    copper_after = pcb_after.get('copper') if isinstance(
        pcb_after.get('copper'), dict) else {}
    for key, category in (('lines', 'track'), ('vias', 'via'),
                          ('pours', 'pour')):
        values_before = _pcb_copper(pcb_before, key)
        values_after = _pcb_copper(pcb_after, key)
        section = {'status': 'available', 'added': [], 'removed': [],
                   'changed': [], 'all': [], 'id_churn': 0}
        if values_before is None or values_after is None:
            section['status'] = 'unknown'
            _add_unknown(unknown, 'pcb.copper.%s' % key,
                         '%s are not measured on both sides' % key)
            result[category + 's' if category != 'via'
                   else 'vias'] = section
            continue
        before_items = [item for item in values_before if isinstance(item, dict)]
        after_items = [item for item in values_after if isinstance(item, dict)]
        matched_after = set()
        for item in before_items:
            twin = _match_copper(category, item, after_items, matched_after,
                                 tolerance)
            if twin is None:
                change = _new_change(
                    'pcb.copper.%s' % category, category + '_removed',
                    net=_text(item.get('net')) or None,
                    primitive_id=_text(item.get('primitiveId')) or None,
                    bbox=_copper_bbox(category, item))
                section['removed'].append(change)
                section['all'].append(change)
                continue
            index, difference = twin
            matched_after.add(index)
            other = after_items[index]
            if _text(item.get('primitiveId')) != _text(
                    other.get('primitiveId')):
                section['id_churn'] += 1
            if difference:
                change = _new_change(
                    'pcb.copper.%s' % category, category + '_changed',
                    net=_text(item.get('net')) or None,
                    primitive_id=_text(item.get('primitiveId')) or None,
                    bbox=_copper_bbox(category, item),
                    difference=difference)
                section['changed'].append(change)
                section['all'].append(change)
        for index, item in enumerate(after_items):
            if index in matched_after:
                continue
            change = _new_change(
                'pcb.copper.%s' % category, category + '_added',
                net=_text(item.get('net')) or None,
                primitive_id=_text(item.get('primitiveId')) or None,
                bbox=_copper_bbox(category, item))
            section['added'].append(change)
            section['all'].append(change)
        changes.extend(section['all'])
        result[category + 's' if category != 'via' else 'vias'] = section

    for key, category in (('regions', 'region'), ('fills', 'fill'),
                          ('poured', 'poured')):
        values_before = _pcb_copper(pcb_before, key)
        values_after = _pcb_copper(pcb_after, key)
        section = {'status': 'available', 'changed': False, 'change': None}
        if values_before is None or values_after is None:
            section['status'] = 'unknown'
            _add_unknown(unknown, 'pcb.copper.%s' % key,
                         '%s are not measured on both sides' % key)
        else:
            change = _compare_geometry_collection(
                'pcb.copper.%s' % key, category, values_before, values_after,
                tolerance)
            if change:
                section['changed'] = True
                section['change'] = change
                changes.append(change)
        result[category] = section

    for key, category in (('holes', 'hole'), ('keepouts', 'keepout')):
        values_before = _pcb_collection(pcb_before, key)
        values_after = _pcb_collection(pcb_after, key)
        section = {'status': 'available', 'changed': False, 'change': None}
        if values_before is None or values_after is None:
            section['status'] = 'unknown'
            _add_unknown(unknown, 'pcb.%s' % key,
                         '%s are not measured on both sides' % key)
        else:
            change = _compare_geometry_collection(
                'pcb.%s' % key, category, values_before, values_after,
                tolerance)
            if change:
                if key == 'holes':
                    owners, unattributed = _changed_hole_designators(
                        values_before, values_after, tolerance)
                    if owners:
                        change['designators'] = owners
                    if unattributed:
                        change['unattributed'] = True
                section['changed'] = True
                section['change'] = change
                changes.append(change)
        result[key] = section

    rules_before = _pcb_rules(pcb_before)
    rules_after = _pcb_rules(pcb_after)
    rules = {'status': 'available', 'changed': False, 'change': None}
    if rules_before is None or rules_after is None:
        rules['status'] = 'unknown'
        _add_unknown(unknown, 'pcb.rules', 'rules are not measured on both '
                                            'sides')
    elif rules_before != rules_after:
        change = _new_change(
            'pcb.rules', 'rules_changed',
            before=sorted(rules_before), after=sorted(rules_after),
            changed_keys=sorted(key for key in set(rules_before) |
                                set(rules_after)
                                if rules_before.get(key) !=
                                rules_after.get(key)))
        rules['changed'] = True
        rules['change'] = change
        changes.append(change)
    result['rules'] = rules

    layers_before = _pcb_copper_layers(pcb_before)
    layers_after = _pcb_copper_layers(pcb_after)
    layers = {'status': 'available', 'changed': False, 'change': None}
    if layers_before is None or layers_after is None:
        layers['status'] = 'unknown'
        _add_unknown(unknown, 'pcb.copperLayers',
                     'copper layer count is not measured on both sides')
    elif layers_before != layers_after:
        change = _new_change('pcb.copper_layers', 'copper_layers_changed',
                             before=layers_before, after=layers_after)
        layers['changed'] = True
        layers['change'] = change
        changes.append(change)
    result['copper_layers'] = layers

    routed_before = _pcb_routed_state({'pcb': pcb_before})
    routed_after = _pcb_routed_state({'pcb': pcb_after})
    routed = {'status': 'available', 'changes': [], 'all': [],
              'before': routed_before, 'after': routed_after}
    if routed_before['status'] == 'unknown' or \
            routed_after['status'] == 'unknown':
        routed['status'] = 'unknown'
        _add_unknown(unknown, 'pcb.routed',
                     'routed/unrouted state is not measurable')
    else:
        # Nets that appear on only one side are a component/pad change; do not
        # double-report them as a routing regression.
        nets = set(routed_before.get('per_net') or {}) & \
            set(routed_after.get('per_net') or {})
        for net in sorted(nets):
            first = (routed_before.get('per_net') or {}).get(net, 'unknown')
            second = (routed_after.get('per_net') or {}).get(net, 'unknown')
            if first != second:
                change = _new_change('pcb.routed', 'routed_changed', net=net,
                                     before=first, after=second)
                routed['changes'].append(change)
                routed['all'].append(change)
        if routed_before['status'] == 'partial' or \
                routed_after['status'] == 'partial':
            routed['status'] = 'partial'
        changes.extend(routed['all'])
    result['routed'] = routed

    drc_before = _pcb_drc({'pcb': pcb_before})
    drc_after = _pcb_drc({'pcb': pcb_after})
    if drc_before is not None or drc_after is not None:
        counts_before = _drc_counts(drc_before)
        counts_after = _drc_counts(drc_after)
        result['drc'] = {'status': 'available' if drc_after is not None
                         else 'unknown',
                         'before': counts_before, 'after': counts_after}
    else:
        result['drc'] = {'status': 'unknown', 'reason': 'DRC was not measured'}
    return result


def _track_points(item):
    points = _points([(item.get('startX'), item.get('startY')),
                      (item.get('endX'), item.get('endY'))])
    if points is not None:
        return points
    start = item.get('start') if isinstance(item.get('start'), dict) else {}
    end = item.get('end') if isinstance(item.get('end'), dict) else {}
    return _points([(start.get('x'), start.get('y')),
                    (end.get('x'), end.get('y'))])


def _copper_bbox(kind, item):
    if kind == 'track':
        points = _track_points(item)
        return _bbox_of_points(points) if points is not None else None
    if kind == 'via':
        point = _point((item.get('x'), item.get('y')))
        if point is None:
            return None
        radius = (_number(item.get('diameter')) or 0) / 2.0
        return [point[0] - radius, point[1] - radius,
                point[0] + radius, point[1] + radius]
    return _bbox(item.get('bbox')) or _bbox_of_points(item.get('points') or [])


def _tracks_match(first, second, tolerance):
    if _text(first.get('net')) != _text(second.get('net')):
        return False
    if _int_or_none(first.get('layer')) != _int_or_none(second.get('layer')):
        return False
    first_points = _track_points(first)
    second_points = _track_points(second)
    if first_points is None or second_points is None:
        return False
    forward = all(_same_number(a[0], b[0], tolerance['position']) and
                  _same_number(a[1], b[1], tolerance['position'])
                  for a, b in zip(first_points, second_points))
    backward = all(_same_number(a[0], b[0], tolerance['position']) and
                   _same_number(a[1], b[1], tolerance['position'])
                   for a, b in zip(first_points, list(reversed(second_points))))
    return forward or backward


def _vias_match(first, second, tolerance):
    return (_text(first.get('net')) == _text(second.get('net')) and
            _same_number(first.get('x'), second.get('x'),
                         tolerance['position']) and
            _same_number(first.get('y'), second.get('y'),
                         tolerance['position']))


def _pours_match(first, second, tolerance):
    return (_text(first.get('net')) == _text(second.get('net')) and
            _int_or_none(first.get('layer')) ==
            _int_or_none(second.get('layer')) and
            _text(_first(first, 'fillMethod', 'fill', 'fill_method')) ==
            _text(_first(second, 'fillMethod', 'fill', 'fill_method')))


def _match_copper(kind, item, after_items, matched, tolerance):
    matcher = {'track': _tracks_match, 'via': _vias_match,
               'pour': _pours_match}[kind]
    for index, candidate in enumerate(after_items):
        if index in matched:
            continue
        if not matcher(item, candidate, tolerance):
            continue
        difference = []
        if kind == 'track':
            if not _same_number(_first(item, 'lineWidth', 'width'),
                                _first(candidate, 'lineWidth', 'width'),
                                tolerance['position']):
                difference.append('width')
        elif kind == 'via':
            for field in ('diameter', 'holeDiameter', 'hole_diameter'):
                if not _same_number(item.get(field), candidate.get(field),
                                    tolerance['position']):
                    difference.append(field)
        else:
            for label, keys in (
                    ('priority', ('priority',)),
                    ('pour_name', ('pour_name', 'pourName', 'name')),
                    ('locked', ('locked',))):
                if _json_value(_first(item, *keys)) != \
                        _json_value(_first(candidate, *keys)):
                    difference.append(label)
            if not _same_number(_first(item, 'line_width', 'lineWidth'),
                                _first(candidate, 'line_width', 'lineWidth'),
                                tolerance['position']):
                difference.append('line_width')
            first_hash = _text(item.get('geometry_sha256'))
            second_hash = _text(candidate.get('geometry_sha256'))
            if first_hash or second_hash:
                if first_hash != second_hash:
                    difference.append('geometry')
            else:
                first_source = item.get('source') if item.get('source') is \
                    not None else item.get('points')
                second_source = candidate.get('source') if candidate.get(
                    'source') is not None else candidate.get('points')
                if first_source is None or second_source is None:
                    if first_source is not second_source:
                        difference.append('geometry_unknown')
                elif _json_value(_canonical(first_source,
                                            tolerance['position'])) != \
                        _json_value(_canonical(second_source,
                                               tolerance['position'])):
                    difference.append('geometry')
        return index, difference
    return None


def _compare_geometry_collection(category, label, before, after, tolerance):
    before_signatures = sorted(
        _json_value(_canonical(item, tolerance['position']))
        for item in before if isinstance(item, dict))
    after_signatures = sorted(
        _json_value(_canonical(item, tolerance['position']))
        for item in after if isinstance(item, dict))
    if before_signatures == after_signatures:
        return None
    return _new_change(category, label + '_changed',
                       before=len(before_signatures),
                       after=len(after_signatures),
                       added=max(0, len(after_signatures) -
                                 len(before_signatures)),
                       removed=max(0, len(before_signatures) -
                                   len(after_signatures)))


def _hole_identity(hole):
    primitive_id = _text(hole.get('primitive_id'))
    if primitive_id:
        return 'primitive:%s' % primitive_id
    designator = _text(hole.get('designator'))
    pad = _text(hole.get('pad'))
    if designator and pad:
        return 'pad:%s:%s' % (designator, pad)
    return None


def _changed_hole_designators(before, after, tolerance):
    """Return owners of changed holes plus an unattributed flag.

    Holes are paired by primitive id first, then by (designator, pad).  Holes
    with no stable identity are paired by exact signature; leftovers count as
    changes.  A change is attributable only when the hole names a designator —
    otherwise the caller must keep it outside scope.
    """
    position = tolerance['position']
    before_items = [item for item in before if isinstance(item, dict)]
    after_items = [item for item in after if isinstance(item, dict)]

    def signature(item):
        return _json_value(_canonical(item, position))

    buckets = {}
    for item in after_items:
        key = _hole_identity(item)
        if key is not None:
            buckets.setdefault(key, []).append(item)

    owners = set()
    unattributed = False
    unmatched_before = []
    for item in before_items:
        key = _hole_identity(item)
        designator = _text(item.get('designator'))
        if key is not None and buckets.get(key):
            candidate = buckets[key].pop(0)
            if signature(item) != signature(candidate):
                after_owner = _text(candidate.get('designator'))
                if not designator or not after_owner:
                    unattributed = True
                else:
                    # A hole whose owner changed from D1 to D2 touches both
                    # components; recording only the before owner would let
                    # an out-of-scope D2 change pass as a D1 change.
                    owners.add(designator)
                    owners.add(after_owner)
        elif key is not None:
            # Removed hole: its identity still names the owner.
            if designator:
                owners.add(designator)
            else:
                unattributed = True
        else:
            unmatched_before.append(item)

    # After-side holes without any identity never entered a bucket, but they
    # are still changes (typically a newly added unowned hole) and must be
    # counted as unattributed rather than silently ignored.
    unmatched_after = [item for item in after_items
                       if _hole_identity(item) is None]
    unmatched_after.extend(item for values in buckets.values()
                           for item in values)
    if unmatched_before or unmatched_after:
        after_signatures = {}
        for item in unmatched_after:
            after_signatures.setdefault(signature(item), []).append(item)
        for item in unmatched_before:
            pool = after_signatures.get(signature(item))
            if pool:
                pool.pop(0)
                continue
            designator = _text(item.get('designator'))
            if designator:
                owners.add(designator)
            else:
                unattributed = True
        for values in after_signatures.values():
            for item in values:
                designator = _text(item.get('designator'))
                if designator:
                    owners.add(designator)
                else:
                    unattributed = True

    owners.discard(None)
    owners.discard('')
    return sorted(owners), unattributed


def _drc_counts(drc):
    if not isinstance(drc, dict):
        return None
    errors = drc.get('errors')
    if isinstance(errors, list):
        errors = len(errors)
    elif not isinstance(errors, int):
        errors = None
    warnings = drc.get('warnings')
    if isinstance(warnings, list):
        warnings = len(warnings)
    elif not isinstance(warnings, int):
        warnings = None
    if errors is None:
        for key in ('errorCount', 'errors_count', 'total'):
            if isinstance(drc.get(key), int):
                errors = drc[key]
                break
    return {'errors': errors, 'warnings': warnings,
            'passed': drc.get('passed') if isinstance(drc.get('passed'), bool)
            else None}


def _sch_endpoints(schematic):
    if not isinstance(schematic, dict):
        return None, None, 'schematic section is absent'
    components, availability = _sch_component_map(schematic)
    nets = schematic.get('nets')
    if components is None and not isinstance(nets, list):
        return None, None, 'schematic components and nets are absent'
    endpoints = {}
    pins_readable = False
    for component in (components or {}).values():
        if component.get('pins_readable'):
            pins_readable = True
        for pin in component.get('pins') or []:
            if pin.get('net'):
                endpoints['%s.%s' % (component['designator'],
                                     pin.get('number') or pin.get('name'))] = \
                    pin['net']
    if isinstance(nets, list):
        pins_readable = True
        for item in nets:
            if not isinstance(item, dict):
                continue
            net = _text(item.get('net') or item.get('name'))
            if not net:
                continue
            members = item.get('pins') or item.get('members') or []
            for member in members:
                endpoints[_text(member)] = net
    if not pins_readable:
        return None, None, 'schematic pin nets are not measured and no net ' \
                           'list is present'
    return endpoints, {'availability': availability,
                       'pins_readable': pins_readable}, None


def _sch_texts(schematic):
    if not isinstance(schematic, dict):
        return None
    values = schematic.get('texts')
    if values is None:
        values = schematic.get('textPrimitives') or \
            schematic.get('text_primitives')
    if values is None:
        return None
    if not isinstance(values, list):
        return None
    result = []
    for index, item in enumerate(values):
        if not isinstance(item, dict):
            continue
        result.append({
            'primitive_id': _text(_first(item, 'primitive_id', 'primitiveId',
                                         'id')) or 'text-%d' % index,
            'content': _text(item.get('content') or item.get('text')),
            'x': _number(item.get('x')), 'y': _number(item.get('y')),
            'rotation': _number(item.get('rotation')),
            'font_size': _number(_first(item, 'fontSize', 'font_size')),
            'locked': item.get('locked') if isinstance(item.get('locked'),
                                                       bool) else None,
        })
    return result


def _diff_schematic(sch_before, sch_after, tolerance, changes, unknown):
    result = {}
    components_before, availability_before = _sch_component_map(sch_before)
    components_after, availability_after = _sch_component_map(sch_after)
    component = {'status': 'available', 'added': [], 'removed': [],
                 'identity_changed': [], 'pose_changed': [],
                 'attribute_changed': [], 'all': []}
    if components_before is None or components_after is None or \
            availability_before == 'unavailable' or \
            availability_after == 'unavailable':
        component['status'] = 'unknown'
        _add_unknown(unknown, 'schematic.components',
                     'schematic components are not readable on both sides')
    else:
        for designator in sorted(set(components_before) |
                                 set(components_after)):
            first = components_before.get(designator)
            second = components_after.get(designator)
            if first is None or second is None:
                change = _new_change(
                    'schematic.component',
                    'added' if first is None else 'removed',
                    designator=designator, object=designator)
                component['added' if first is None else 'removed'].append(
                    change)
                component['all'].append(change)
                continue
            identity_before = {'unique_id': first.get('unique_id'),
                               'device': _json_value(first.get('device'))}
            identity_after = {'unique_id': second.get('unique_id'),
                              'device': _json_value(second.get('device'))}
            if identity_before != identity_after:
                change = _new_change(
                    'schematic.component', 'identity_changed',
                    designator=designator, object=designator,
                    before=identity_before, after=identity_after)
                component['identity_changed'].append(change)
                component['all'].append(change)
            x_known = first.get('x') is not None and second.get('x') is not None
            y_known = first.get('y') is not None and second.get('y') is not None
            if x_known and y_known and (
                    not _same_number(first.get('x'), second.get('x'),
                                     tolerance['position']) or
                    not _same_number(first.get('y'), second.get('y'),
                                     tolerance['position'])):
                change = _new_change(
                    'schematic.component', 'pose_changed',
                    designator=designator, object=designator,
                    before={'x': first.get('x'), 'y': first.get('y'),
                            'rotation': first.get('rotation')},
                    after={'x': second.get('x'), 'y': second.get('y'),
                           'rotation': second.get('rotation')})
                component['pose_changed'].append(change)
                component['all'].append(change)
            elif first.get('rotation') is not None and \
                    second.get('rotation') is not None and \
                    not _same_angle(first.get('rotation'),
                                    second.get('rotation'),
                                    tolerance['angle']):
                change = _new_change(
                    'schematic.component', 'pose_changed',
                    designator=designator, object=designator,
                    before={'x': first.get('x'), 'y': first.get('y'),
                            'rotation': first.get('rotation')},
                    after={'x': second.get('x'), 'y': second.get('y'),
                           'rotation': second.get('rotation')})
                component['pose_changed'].append(change)
                component['all'].append(change)
            attributes_before = {
                'name': _json_value(first.get('name')),
                'footprint': _json_value(first.get('footprint')),
                'supplier_id': first.get('supplier_id'),
            }
            attributes_after = {
                'name': _json_value(second.get('name')),
                'footprint': _json_value(second.get('footprint')),
                'supplier_id': second.get('supplier_id'),
            }
            if attributes_before != attributes_after:
                change = _new_change(
                    'schematic.component', 'attribute_changed',
                    designator=designator, object=designator,
                    before=attributes_before, after=attributes_after)
                component['attribute_changed'].append(change)
                component['all'].append(change)
    result['components'] = component
    changes.extend(component['all'])

    endpoints_before, readable_before, reason_before = \
        _sch_endpoints(sch_before)
    endpoints_after, readable_after, reason_after = _sch_endpoints(sch_after)
    nets = {'status': 'available', 'added': [], 'removed': [], 'changed': [],
            'all': []}
    if endpoints_before is None or endpoints_after is None:
        nets['status'] = 'unknown'
        _add_unknown(unknown, 'schematic.nets',
                     reason_before or reason_after or
                     'schematic connectivity is not measurable')
    else:
        for key in sorted(set(endpoints_before) | set(endpoints_after)):
            first = endpoints_before.get(key)
            second = endpoints_after.get(key)
            if first == second:
                continue
            designator = key.split('.', 1)[0]
            if first is None:
                kind = 'endpoint_added'
            elif second is None:
                kind = 'endpoint_removed'
            else:
                kind = 'endpoint_net_changed'
            change = _new_change(
                'schematic.net', kind, designator=designator, object=key,
                net=(first or second), nets=sorted({_text(first), _text(second)}
                                                    - {''}),
                before=first, after=second)
            nets['added' if kind == 'endpoint_added' else
                 ('removed' if kind == 'endpoint_removed' else 'changed')].append(
                change)
            nets['all'].append(change)
    result['nets'] = nets
    changes.extend(nets['all'])

    texts_before = _sch_texts(sch_before)
    texts_after = _sch_texts(sch_after)
    texts = {'status': 'available', 'added': [], 'removed': [], 'changed': [],
             'all': []}
    if texts_before is None or texts_after is None:
        texts['status'] = 'unknown'
        _add_unknown(unknown, 'schematic.texts',
                     'schematic text primitives are not measured on both '
                     'sides')
    else:
        before_map = {item['primitive_id']: item for item in texts_before}
        after_map = {item['primitive_id']: item for item in texts_after}
        for key in sorted(set(before_map) | set(after_map)):
            first = before_map.get(key)
            second = after_map.get(key)
            if first is None or second is None:
                change = _new_change(
                    'schematic.text', 'added' if first is None else 'removed',
                    object=key, primitive_id=key,
                    content=(second or first).get('content'))
                texts['added' if first is None else 'removed'].append(change)
                texts['all'].append(change)
                continue
            difference = {}
            if first.get('content') != second.get('content'):
                difference['content'] = [first.get('content'),
                                         second.get('content')]
            if first.get('x') is not None and second.get('x') is not None and \
                    (not _same_number(first.get('x'), second.get('x'),
                                      tolerance['position']) or
                     not _same_number(first.get('y'), second.get('y'),
                                      tolerance['position'])):
                difference['position'] = [
                    {'x': first.get('x'), 'y': first.get('y')},
                    {'x': second.get('x'), 'y': second.get('y')},
                ]
            if first.get('rotation') is not None and \
                    second.get('rotation') is not None and \
                    not _same_angle(first.get('rotation'),
                                    second.get('rotation'),
                                    tolerance['angle']):
                difference['rotation'] = [first.get('rotation'),
                                          second.get('rotation')]
            if first.get('font_size') != second.get('font_size'):
                difference['font_size'] = [first.get('font_size'),
                                           second.get('font_size')]
            if difference:
                change = _new_change(
                    'schematic.text', 'text_changed', object=key,
                    primitive_id=key, difference=difference,
                    content=second.get('content'))
                texts['changed'].append(change)
                texts['all'].append(change)
    result['texts'] = texts
    changes.extend(texts['all'])
    return result


def diff_observations(before, after, *, scope=None, tolerance=None):
    """Compare two observations semantically and classify every change.

    The result never treats an unreadable category as empty: a missing or
    explicitly unavailable category is reported in ``unknown[]`` and makes
    the status ``unknown`` when nothing else changed.
    """
    before = _as_observation(before)
    after = _as_observation(after)
    if not isinstance(before, dict) or not isinstance(after, dict):
        return {
            'schema': schemas.SCHEMA_DIFF, 'status': 'unknown',
            'changes': [], 'inside_scope': [], 'outside_scope': [],
            'unknown': [{'field': 'observation',
                         'reason': 'both sides must be observation objects'}],
            'counts': {'total': 0, 'inside_scope': 0, 'outside_scope': 0},
            'note': 'unreadable observation; no empty-list comparison was made',
            'simulated': bool(
                (before.get('simulated') if isinstance(before, dict) else False)
                or (after.get('simulated') if isinstance(after, dict) else False)),
        }
    try:
        normalized_scope = normalize_scope(scope) if scope is not None else \
            {'writable': {'objects': [], 'nets': [], 'regions': []},
             'tolerance': _normalize_tolerance(None)}
        tol = _normalize_tolerance(tolerance,
                                   normalized_scope.get('tolerance'))
    except schemas.ContractError as exc:
        return {
            'schema': schemas.SCHEMA_DIFF, 'status': 'unknown',
            'changes': [], 'inside_scope': [], 'outside_scope': [],
            'unknown': [{'field': 'scope', 'reason': str(exc)}],
            'counts': {'total': 0, 'inside_scope': 0, 'outside_scope': 0},
            'note': 'unreadable scope; no change was classified',
            'simulated': bool(before.get('simulated') or
                              after.get('simulated')),
        }
    objects, nets_set, regions = _scope_selectors(normalized_scope)
    changes = []
    unknown = []
    pcb_before, pcb_after = _obs_pcb(before), _obs_pcb(after)
    sch_before, sch_after = _obs_sch(before), _obs_sch(after)
    pcb_section = None
    sch_section = None
    if pcb_before is None or pcb_after is None:
        _add_unknown(unknown, 'pcb',
                     'PCB section is absent on at least one side')
    else:
        pcb_section = _diff_pcb(pcb_before, pcb_after, tol, changes, unknown)
    if sch_before is None or sch_after is None:
        _add_unknown(unknown, 'schematic',
                     'schematic section is absent on at least one side')
    else:
        sch_section = _diff_schematic(sch_before, sch_after, tol, changes,
                                      unknown)
    classified = []
    for change in changes:
        classified.append(_classify_change(change, objects, nets_set, regions,
                                           tol))
    inside = [change for change in classified if change.get('in_scope')]
    outside = [change for change in classified if not change.get('in_scope')]
    if outside:
        status = 'mismatch'
    elif classified:
        status = 'changed'
    elif unknown:
        status = 'unknown'
    else:
        status = 'match'
    before_hash, _per_document, _captured = _observation_revision(before)
    after_hash, _per_document_after, _captured_after = \
        _observation_revision(after)
    payload = {
        'schema': schemas.SCHEMA_DIFF,
        'status': status,
        'before': {'semantic_sha256': before_hash,
                   'generated_at': before.get('generated_at')},
        'after': {'semantic_sha256': after_hash,
                  'generated_at': after.get('generated_at')},
        'tolerance': tol,
        'scope': normalized_scope,
        'changes': classified,
        'inside_scope': inside,
        'outside_scope': outside,
        'unknown': unknown,
        'counts': {
            'total': len(classified),
            'inside_scope': len(inside),
            'outside_scope': len(outside),
            'unknown': len(unknown),
        },
        'note': 'primitiveId churn is not a change; rotations 0/360 and '
                '-90/270 are equivalent; unreadable categories are unknown, '
                'never empty',
        'simulated': bool(before.get('simulated') or after.get('simulated')),
    }
    if pcb_section is not None:
        payload['pcb'] = pcb_section
        # Flat aliases keep the common categories easy to consume without
        # walking the section tree.
        for key in ('components', 'outline', 'tracks', 'vias', 'pours',
                    'fills', 'regions', 'poured', 'holes', 'keepouts',
                    'rules', 'copper_layers', 'routed', 'drc'):
            if key in pcb_section:
                payload[key] = pcb_section[key]
        if 'copper_layers' in pcb_section:
            payload['copperLayers'] = pcb_section['copper_layers']
    if sch_section is not None:
        payload['schematic'] = sch_section
    return payload


# ---------------------------------------------------------------------------
# invariants
# ---------------------------------------------------------------------------

def _invariant_result(identifier, kind, status, reasons, **detail):
    result = {'id': identifier, 'kind': kind, 'status': status,
              'reasons': reasons}
    if detail:
        result['detail'] = detail
    return result


def _diff_unknown(diff, prefix):
    values = []
    for item in (diff or {}).get('unknown') or []:
        field = _text((item or {}).get('field'))
        if field == prefix or field.startswith(prefix + '.') or \
                field.startswith(prefix + '['):
            values.append(item)
    return values


def _changes_for(diff, path):
    value = diff or {}
    for key in path:
        value = (value or {}).get(key) if isinstance(value, dict) else None
    return value if isinstance(value, list) else []


def _check_invariant(invariant, diff, after):
    identifier = _text(invariant.get('id')) or 'invariant'
    kind = _text(invariant.get('kind'))
    params = invariant.get('params') or {}
    diff = diff or {}
    if kind == schemas.INVARIANT_SCH_CONNECTIVITY:
        section = (diff.get('schematic') or {}).get('nets')
        if not section or section.get('status') != 'available':
            return _invariant_result(
                identifier, kind, 'unknown',
                ['schematic net endpoint sets are not readable'])
        changes_section = section.get('all') or []
        if changes_section:
            return _invariant_result(
                identifier, kind, 'fail',
                ['schematic connectivity changed: %d endpoint change(s)' %
                 len(changes_section)], changes=changes_section)
        return _invariant_result(identifier, kind, 'pass',
                                 ['schematic net endpoint sets unchanged'])
    if kind == schemas.INVARIANT_SCH_IDENTITY:
        section = (diff.get('schematic') or {}).get('components')
        if not section or section.get('status') != 'available':
            return _invariant_result(
                identifier, kind, 'unknown',
                ['schematic component identity is not readable'])
        changes_section = ((section.get('added') or []) +
                           (section.get('removed') or []) +
                           (section.get('identity_changed') or []))
        if changes_section:
            return _invariant_result(
                identifier, kind, 'fail',
                ['schematic component identity changed: %d change(s)' %
                 len(changes_section)], changes=changes_section)
        return _invariant_result(identifier, kind, 'pass',
                                 ['schematic component identity unchanged'])
    if kind == schemas.INVARIANT_PCB_PAD_NET:
        section = (diff.get('pcb') or {}).get('components') or {}
        unknown_pads = [item for item in _diff_unknown(diff, 'pcb.components')
                        if '.pads' in _text(item.get('field'))]
        if not section or section.get('status') != 'available' or unknown_pads:
            return _invariant_result(
                identifier, kind, 'unknown',
                ['PCB pad/net map is not readable for every component'])
        changes_section = section.get('pad_net_changed') or []
        if changes_section:
            return _invariant_result(
                identifier, kind, 'fail',
                ['PCB pad net assignments changed: %d component(s)' %
                 len(changes_section)], changes=changes_section)
        return _invariant_result(identifier, kind, 'pass',
                                 ['PCB pad net assignments unchanged'])
    if kind == schemas.INVARIANT_PCB_OUTLINE:
        section = (diff.get('pcb') or {}).get('outline')
        if not section or section.get('status') != 'available':
            return _invariant_result(identifier, kind, 'unknown',
                                     ['PCB outline is not readable'])
        if section.get('changed'):
            return _invariant_result(identifier, kind, 'fail',
                                     ['PCB outline changed'],
                                     changes=[section.get('change')])
        return _invariant_result(identifier, kind, 'pass',
                                 ['PCB outline unchanged'])
    if kind == schemas.INVARIANT_PCB_LOCKED:
        section = (diff.get('pcb') or {}).get('components')
        unknown_locked = [item for item in _diff_unknown(diff, 'pcb.components')
                          if '.locked' in _text(item.get('field'))]
        if not section or section.get('status') != 'available' or \
                unknown_locked:
            return _invariant_result(identifier, kind, 'unknown',
                                     ['PCB lock state is not readable'])
        changes_section = section.get('locked_changed') or []
        if changes_section:
            return _invariant_result(
                identifier, kind, 'fail',
                ['a locked object changed: %s' % ', '.join(sorted(
                    _text(item.get('designator')) for item in changes_section))],
                changes=changes_section)
        return _invariant_result(identifier, kind, 'pass',
                                 ['locked objects unchanged'])
    if kind == schemas.INVARIANT_PCB_UNRELATED:
        outside = diff.get('outside_scope') or []
        if outside:
            return _invariant_result(
                identifier, kind, 'fail',
                ['%d change(s) outside scope.writable' % len(outside)],
                changes=outside)
        unknown_pcb = _diff_unknown(diff, 'pcb')
        if unknown_pcb:
            return _invariant_result(
                identifier, kind, 'unknown',
                ['PCB categories are unreadable; unrelated changes cannot be '
                 'excluded'], unknown=unknown_pcb)
        return _invariant_result(identifier, kind, 'pass',
                                 ['no change outside scope.writable'])
    if kind == schemas.INVARIANT_PCB_ROUTED:
        section = (diff.get('pcb') or {}).get('routed')
        if not section or section.get('status') not in ('available', 'partial'):
            return _invariant_result(identifier, kind, 'unknown',
                                     ['routed/unrouted state is not readable'])
        regressions = []
        unknown_nets = []
        for change in section.get('changes') or []:
            before = _text(change.get('before'))
            after = _text(change.get('after'))
            if 'unknown' in (before, after):
                unknown_nets.append(change)
            elif before == 'routed' and after != 'routed':
                regressions.append(change)
        if regressions:
            return _invariant_result(
                identifier, kind, 'fail',
                ['routed net(s) became unrouted: %s' % ', '.join(
                    _text(item.get('net')) for item in regressions)],
                changes=regressions)
        if unknown_nets or section.get('status') == 'partial':
            return _invariant_result(
                identifier, kind, 'unknown',
                ['routed state is partial or unknown for some nets'],
                unknown=unknown_nets)
        return _invariant_result(identifier, kind, 'pass',
                                 ['no routed net regressed'])
    if kind == schemas.INVARIANT_DRC:
        drc = _pcb_drc(after) if after is not None else None
        if drc is None:
            drc = (diff.get('pcb') or {}).get('drc')
        if isinstance(drc, dict) and isinstance(drc.get('after'), dict):
            # A diff carries DRC counts, not the raw DRC result.
            drc = {'errors': drc['after'].get('errors'),
                   'warnings': drc['after'].get('warnings'),
                   'passed': drc['after'].get('passed')}
        if not isinstance(drc, dict):
            return _invariant_result(identifier, kind, 'unknown',
                                     ['DRC was not measured'])
        counts = _drc_counts(drc)
        if counts is None or (counts.get('errors') is None and
                              counts.get('passed') is None):
            return _invariant_result(identifier, kind, 'unknown',
                                     ['DRC result is unreadable'])
        max_errors = params.get('max_errors', 0)
        if not isinstance(max_errors, int) or max_errors < 0:
            max_errors = 0
        errors = counts.get('errors')
        if counts.get('passed') is False:
            return _invariant_result(identifier, kind, 'fail',
                                     ['DRC did not pass'], drc=counts)
        if errors is not None and errors > max_errors:
            return _invariant_result(
                identifier, kind, 'fail',
                ['DRC errors %d exceed max_errors %d' % (errors, max_errors)],
                drc=counts)
        if errors is None and counts.get('passed') is not True:
            return _invariant_result(identifier, kind, 'unknown',
                                     ['DRC has no error count or pass flag'])
        return _invariant_result(identifier, kind, 'pass',
                                 ['DRC passed with %s error(s)' %
                                  (errors if errors is not None else '0')],
                                 drc=counts)
    if kind == schemas.INVARIANT_KEEPOUT:
        section = (diff.get('pcb') or {}).get('keepouts')
        if not section or section.get('status') != 'available':
            return _invariant_result(identifier, kind, 'unknown',
                                     ['keepouts are not readable'])
        if section.get('changed'):
            return _invariant_result(identifier, kind, 'fail',
                                     ['keepouts changed'],
                                     changes=[section.get('change')])
        return _invariant_result(identifier, kind, 'pass',
                                 ['keepouts unchanged'])
    if kind == schemas.INVARIANT_HOLES:
        section = (diff.get('pcb') or {}).get('holes')
        if not section or section.get('status') != 'available':
            return _invariant_result(identifier, kind, 'unknown',
                                     ['holes are not readable'])
        if section.get('changed'):
            return _invariant_result(identifier, kind, 'fail',
                                     ['holes changed'],
                                     changes=[section.get('change')])
        return _invariant_result(identifier, kind, 'pass',
                                 ['holes unchanged'])
    return _invariant_result(identifier, kind, 'unknown',
                             ['invariant kind is not supported'])


def check_invariants(contract, diff, after=None):
    """Evaluate every contract invariant.  Unknown is never treated as pass."""
    try:
        schemas.validate_modification(contract)
    except (schemas.ContractError, TypeError, AttributeError) as exc:
        return {
            'schema': SCHEMA_INVARIANTS, 'ok': False, 'status': 'unknown',
            'contract_id': None, 'results': [],
            'counts': {'pass': 0, 'fail': 0, 'unknown': 0},
            'unknown': ['invalid_contract'],
            'reasons': [str(exc)],
        }
    results = []
    for invariant in contract.get('invariants') or []:
        results.append(_check_invariant(invariant, diff, after))
    counts = {'pass': 0, 'fail': 0, 'unknown': 0}
    for result in results:
        counts[result['status']] = counts.get(result['status'], 0) + 1
    if counts['fail']:
        status = 'fail'
    elif counts['unknown']:
        status = 'unknown'
    else:
        status = 'pass'
    return {
        'schema': SCHEMA_INVARIANTS,
        'ok': status == 'pass',
        'status': status,
        'contract_id': contract.get('id'),
        'generated_at': schemas.now_utc(),
        'results': results,
        'counts': counts,
        'unknown': [result['id'] for result in results
                    if result['status'] == 'unknown'],
        'note': 'unknown is not pass; a single fail dominates the result',
    }


_ACCEPTANCE_PREDICATE = re.compile(
    r'^(?:count\s*)?(==|!=|>=|<=|>|<)\s*(.+)$', re.IGNORECASE)


def _acceptance_actual(metric, diff, evaluation, invariants):
    name = str(metric or '').strip().lower()
    diff = diff if isinstance(diff, dict) else {}
    if name.startswith('diff.') and diff.get('status') == 'unknown':
        # A diff that could not measure a category still carries zero counters
        # and empty lists.  Those zeros are "not measured", never evidence
        # that no out-of-scope change happened.
        return None
    counts = diff.get('counts') if isinstance(diff.get('counts'), dict) else {}
    def measured(key, list_key):
        if key in counts:
            return counts[key]
        # An absent counter with no list either means "not measured", never 0:
        # an empty diff payload must not satisfy ``outside_scope == 0``.
        if isinstance(diff.get(list_key), list):
            return len(diff[list_key])
        return None

    if name in ('diff.outside_scope', 'outside_scope',
                'diff.outside_scope.count'):
        return measured('outside_scope', 'outside_scope')
    if name in ('diff.inside_scope', 'inside_scope'):
        return measured('inside_scope', 'inside_scope')
    if name in ('diff.changes', 'diff.count', 'diff.counts.total'):
        return measured('total', 'changes')
    if name in ('invariants.status', 'invariants.verdict'):
        return invariants.get('status') if isinstance(invariants, dict) \
            else None
    if name in ('evaluation.verdict', 'quality.verdict'):
        return (evaluation or {}).get('verdict')
    return None


def _acceptance_status(actual, predicate):
    text = _text(predicate)
    if text is None:
        return 'unknown', 'predicate is empty'
    match = _ACCEPTANCE_PREDICATE.match(text.strip())
    if not match:
        return 'unknown', 'predicate %r is not understood' % text
    operator, raw_expected = match.group(1), match.group(2).strip()
    if actual is None:
        return 'unknown', 'metric %r was not measured' % (raw_expected,)

    def coerce(value):
        if isinstance(value, bool):
            return value
        number = _number(value)
        if number is not None:
            return number
        if isinstance(value, str):
            # A predicate literal such as ``0`` is numeric, not a status
            # token; comparing it as text would make ``str(0.0) == '0'`` fail.
            try:
                return float(value.strip())
            except ValueError:
                return value.strip().lower()
        return value

    left, right = coerce(actual), coerce(raw_expected)
    try:
        if isinstance(left, str) or isinstance(right, str):
            if operator not in ('==', '!='):
                return 'unknown', 'status values only support == and !='
            equal = str(left) == str(right)
            passed = equal if operator == '==' else not equal
        else:
            passed = {
                '==': left == right, '!=': left != right,
                '>=': left >= right, '<=': left <= right,
                '>': left > right, '<': left < right,
            }[operator]
    except TypeError:
        return 'unknown', 'metric and predicate are not comparable'
    return ('pass' if passed else 'fail',
            '%s %s %s' % (actual, operator, raw_expected))


def evaluate_acceptance(contract, diff, evaluation=None, invariants=None):
    """Evaluate every declared acceptance predicate.

    ``target_met`` is true only when every predicate passes; an unmeasured
    metric is ``unknown`` and never counts as meeting the goal.
    """
    if not isinstance(invariants, dict):
        invariants = (diff or {}).get('invariants') \
            if isinstance(diff, dict) else None
        if not isinstance(invariants, dict):
            invariants = {}
    results = []
    for item in contract.get('acceptance') or []:
        if not isinstance(item, dict):
            continue
        actual = _acceptance_actual(item.get('metric'), diff, evaluation,
                                    invariants)
        status, detail = _acceptance_status(actual, item.get('predicate'))
        results.append({
            'id': item.get('id'),
            'metric': item.get('metric'),
            'predicate': item.get('predicate'),
            'actual': actual,
            'status': status,
            'detail': detail,
        })
    failed = [item for item in results if item['status'] == 'fail']
    unknown = [item for item in results if item['status'] == 'unknown']
    if failed:
        status = 'fail'
    elif unknown or not results:
        status = 'unknown'
    else:
        status = 'pass'
    return {
        'schema': 'hds-acceptance/v1',
        'status': status,
        'target_met': True if status == 'pass' else (
            False if status == 'fail' else None),
        'results': results,
        'failed': [item['id'] for item in failed],
        'unknown': [item['id'] for item in unknown],
        'note': 'only a fully measured pass meets the declared target',
    }


# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------

def _apply_base(contract, plan, *, write_requested, status, validation=None):
    return {
        'schema': schemas.SCHEMA_APPLY,
        'ok': status in ('verified', 'no_op', 'preview'),
        'status': status,
        'tool_version': schemas.TOOL_VERSION,
        'generated_at': schemas.now_utc(),
        'contract_id': contract.get('id'),
        'write_requested': bool(write_requested),
        'simulated': _plan_simulated(plan),
        'writes_sent': 0,
        'call_ok': None,
        'write_confirmed': None,
        'save_confirmed': None,
        'reopen_confirmed': None,
        'quality_passed': None,
        'baseline': None,
        'validation': validation,
        'steps': _annotate_steps((validation or {}).get('steps') or [],
                                 (validation or {}).get('step_scope') or []),
        'step_scope': (validation or {}).get('step_scope') or [],
        'scope_decisions': (validation or {}).get('step_scope') or [],
        'skipped': (validation or {}).get('skipped') or [],
        'journal': None,
        'readback': None,
        'diff': None,
        'invariants': None,
        'failure': None,
        'unknown': (validation or {}).get('unknown') or [],
        'notes': [],
    }


def _apply_refused(contract, plan, validation, failure_class, reason,
                   message, **detail):
    payload = _apply_base(contract, plan, write_requested=True,
                          status='refused', validation=validation)
    payload['ok'] = False
    payload['failure'] = {'failure_class': failure_class, 'reason': reason,
                          'message': message}
    if detail:
        payload['failure']['detail'] = detail
    payload['notes'].append('refused before any CLI call; writes_sent=0')
    return payload


def _preview_apply(contract, plan, *, write_requested):
    validation = _validate_plan_internal(contract, plan)
    payload = _apply_base(contract, plan, write_requested=write_requested,
                          status='preview', validation=validation)
    payload['ok'] = bool(validation.get('ok'))
    payload['failure_class'] = validation.get('failure_class')
    payload['write_authorized'] = not bool(contract.get('preview_only'))
    payload['notes'].append('preview only: no CLI call and no file write were '
                            'made')
    payload['refusals'] = validation.get('refusals') or []
    return payload


def _run_cli(runner, args, *, easycirq, timeout):
    try:
        if runner is not None:
            return runner(args, easycirq=easycirq, timeout=timeout)
        _pcb_apply_plan, pcb_cli = _pcb_modules()
        return pcb_cli.run(args, easycirq=easycirq, timeout=timeout)
    except Exception as exc:  # fake runners must not hide a crash as success
        return {'argv': args, 'exit': None, 'ok': False, 'error': str(exc),
                'stdout': '', 'stderr': '', 'payload': None,
                'started_at': None, 'ended_at': None}


def _record_ok(record):
    if not isinstance(record, dict):
        return False
    payload = record.get('payload')
    return (record.get('exit') == 0 and isinstance(payload, dict) and
            payload.get('ok') is not False)


def _payload_context(payload):
    if not isinstance(payload, dict):
        return {}
    context = payload.get('context')
    if isinstance(context, dict) and context:
        return context
    result = payload.get('result')
    if isinstance(result, dict) and isinstance(result.get('context'), dict):
        return result['context']
    mutation = payload.get('mutationContext')
    return mutation if isinstance(mutation, dict) else {}


def _context_status(contract, document, payload):
    context = _payload_context(payload)
    if not context:
        return 'unknown', 'response has no context; the target cannot be '
    expected_project = _text((contract.get('target') or {}).get(
        'project_uuid'))
    expected_document = _text((document or {}).get('uuid'))
    project = _text(context.get('projectUuid') or
                    context.get('project_uuid'))
    document_uuid = _text(context.get('documentUuid') or
                          context.get('document_uuid'))
    if expected_project and project and project != expected_project:
        return 'mismatch', 'response project %s != target %s' % (
            project, expected_project)
    if expected_document and document_uuid and \
            document_uuid != expected_document:
        return 'mismatch', 'response document %s != target %s' % (
            document_uuid, expected_document)
    if not project and not document_uuid:
        return 'unknown', 'response context lacks project/document UUIDs'
    return 'ok', 'response context matches the contract target'


def _result_value(payload, key):
    if not isinstance(payload, dict):
        return None
    result = payload.get('result')
    if isinstance(result, dict) and key in result:
        return result[key]
    return payload.get(key)


def _verified_payload(payload, action):
    if not isinstance(payload, dict) or payload.get('ok') is False:
        return False, 'the CLI envelope is not ok'
    if action.startswith('schematic.') and action.endswith('.save'):
        saved = _result_value(payload, 'saved')
        return (saved is True, 'save receipt is missing' if saved is not True
                else 'saved')
    verified = _result_value(payload, 'verified')
    partial = _result_value(payload, 'partial')
    not_applied = _result_value(payload, 'notApplied')
    not_moved = _result_value(payload, 'notMoved')
    if verified is not True:
        return False, 'response does not assert verified=true'
    if partial is True:
        return False, 'response reports partial application'
    if not_applied:
        return False, 'response reports notApplied entries'
    if not_moved:
        return False, 'response reports notMoved entries'
    return True, 'verified'


def _append_journal(path, entries):
    if not path:
        return
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, 'a', encoding='utf-8', newline='\n') as handle:
        for entry in entries:
            handle.write(json.dumps(entry, ensure_ascii=False,
                                    allow_nan=False) + '\n')


def _read_journal_file(path):
    try:
        with open(path, 'r', encoding='utf-8-sig') as handle:
            lines = handle.read().splitlines()
    except OSError:
        return None
    entries = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            entries.append(value)
    return entries


def _schematic_step_id(op, index):
    if op['op'] == 'move_text':
        return 'move_text-%d' % index
    return 'move_component-%d' % index


def _schematic_payload(op):
    if op['op'] == 'move_text':
        return {'moves': [{'primitiveId': op['primitive_id'],
                           'x': op['x'], 'y': op['y']}]}
    return {'id': op.get('primitive_id'), 'patch': copy.deepcopy(
        op.get('patch') or {})}


def _schematic_readback(runner, easycirq, timeout, window, contract, document,
                        project, ops):
    text_ops = [op for op in ops if op['op'] == 'move_text']
    component_ops = [op for op in ops if op['op'] != 'move_text']
    calls = []
    texts = None
    components = None
    issues = []
    if text_ops:
        args = ['call', 'schematic.text.list', '--payload', '{}']
        args = _with_target(args, project, _document_ref(document), window)
        record = _run_cli(runner, args, easycirq=easycirq, timeout=timeout)
        context, reason = _context_status(
            contract, document, record.get('payload'))
        calls.append({'action': 'schematic.text.list',
                      'exit': record.get('exit'), 'ok': _record_ok(record),
                      'context': context, 'reason': reason})
        if context == 'mismatch':
            issues.append(reason)
        payload = record.get('payload')
        if _record_ok(record):
            result = payload.get('result') or {}
            texts = _sch_texts({'texts': result.get('texts')}) if \
                isinstance(result.get('texts'), list) else None
        if texts is None:
            issues.append('schematic text readback is unavailable')
    if component_ops:
        args = ['call', 'schematic.components.list', '--payload',
                json.dumps({'includePins': True})]
        args = _with_target(args, project, _document_ref(document), window)
        record = _run_cli(runner, args, easycirq=easycirq, timeout=timeout)
        context, reason = _context_status(
            contract, document, record.get('payload'))
        calls.append({'action': 'schematic.components.list',
                      'exit': record.get('exit'), 'ok': _record_ok(record),
                      'context': context, 'reason': reason})
        if context == 'mismatch':
            issues.append(reason)
        payload = record.get('payload')
        if _record_ok(record):
            result = payload.get('result') or {}
            raw = result.get('components')
            if isinstance(raw, list):
                components = copy.deepcopy(raw)
        if components is None:
            issues.append('schematic component readback is unavailable')
    return {'calls': calls, 'texts': texts, 'components': components,
            'issues': issues}


def _document_ref(document):
    """Turn a resolved document object into a --doc value."""
    if isinstance(document, dict):
        return _text(document.get('uuid')) or _text(document.get('name')) or None
    return _text(document) or None


def _with_target(args, project, document, window):
    args = list(args)
    if project:
        args.extend(['--project', project])
    if document:
        args.extend(['--doc', document])
    if window:
        args.extend(['--window', window])
    return args


def _readback_verified(ops, readback):
    if not readback:
        return None
    tolerance = POSITION_TOLERANCE
    for op in ops:
        if op['op'] == 'move_text':
            texts = readback.get('texts')
            if texts is None:
                return None
            match = next((text for text in texts if text.get('primitive_id') ==
                          op.get('primitive_id')), None)
            if match is None:
                return False
            if match.get('x') is None or match.get('y') is None:
                return None
            if not (_same_number(match.get('x'), op.get('x'), tolerance) and
                    _same_number(match.get('y'), op.get('y'), tolerance)):
                return False
        else:
            components = readback.get('components')
            if components is None:
                return None
            designator = _text(op.get('designator'))
            primitive_id = _text(op.get('primitive_id'))
            match = None
            for item in components:
                if not isinstance(item, dict):
                    continue
                if (designator and _text(item.get('designator')) ==
                        designator) or \
                        (primitive_id and _text(_first(item, 'primitiveId',
                                                       'primitive_id')) ==
                         primitive_id):
                    match = item
                    break
            if match is None:
                return False
            for key in ('x', 'y'):
                if key in (op.get('patch') or {}):
                    if match.get(key) is None:
                        return None
                    if not _same_number(match.get(key),
                                        op['patch'][key], tolerance):
                        return False
            if 'rotation' in (op.get('patch') or {}):
                if match.get('rotation') is None:
                    return None
                if not _same_angle(match.get('rotation'),
                                   op['patch']['rotation'], ANGLE_TOLERANCE):
                    return False
            if 'layer' in (op.get('patch') or {}):
                if _int_or_none(match.get('layer')) != _int_or_none(
                        op['patch']['layer']):
                    return False
    if readback.get('issues'):
        return None
    return True


def _schematic_after(fresh, ops, readback):
    after = copy.deepcopy(fresh)
    schematic = copy.deepcopy(after.get('schematic') or {})
    if readback.get('texts') is not None:
        existing = {item.get('primitive_id'): item for item in
                    schematic.get('texts') or [] if isinstance(item, dict)}
        for text in readback['texts']:
            pid = text.get('primitive_id')
            entry = dict(existing.get(pid) or {})
            entry['primitiveId'] = pid
            for source, target in (('content', 'content'), ('x', 'x'),
                                   ('y', 'y'), ('rotation', 'rotation'),
                                   ('font_size', 'fontSize')):
                if text.get(source) is not None:
                    entry[target] = text.get(source)
            existing[pid] = entry
        schematic['texts'] = list(existing.values())
    if readback.get('components') is not None:
        raw = schematic.get('components')
        if isinstance(raw, list):
            by_designator = {_text(item.get('designator')): item
                             for item in raw if isinstance(item, dict)}
            for item in readback['components']:
                if not isinstance(item, dict):
                    continue
                designator = _text(item.get('designator'))
                if designator in by_designator:
                    by_designator[designator].update({
                        'x': item.get('x'), 'y': item.get('y'),
                        'rotation': item.get('rotation'),
                        'layer': item.get('layer'),
                    })
            schematic['components'] = list(by_designator.values())
    after['schematic'] = schematic
    return after


def _apply_schematic(contract, plan, validation, fresh, document, *,
                     runner, easycirq, window, journal_path, timeout):
    included = [action for action in validation['actions']
                if action.get('already_applied') is not True]
    if not included:
        payload = _apply_base(contract, plan, write_requested=True,
                              status='no_op', validation=validation)
        payload['ok'] = True
        payload['unknown'] = list(payload.get('unknown') or []) + [
            {'field': 'write', 'reason': 'all operations were already present'}]
        payload['notes'].append('no write needed: every operation is already '
                                'present in the fresh observation')
        return payload
    # Normalised ops are stable by index; collect them once.
    _kind, all_ops, flags, _error = _normalize_plan_ops(plan)
    ops = [op for op in all_ops
           if op['index'] in {action['index'] for action in included}]
    project = _text(((fresh or {}).get('project') or {}).get('name')) or \
        _text((contract.get('target') or {}).get('project_uuid'))
    document_uuid = _text((document or {}).get('uuid'))
    document_name = _text((document or {}).get('name')) or document_uuid
    entries = []
    calls = []
    target_failure = None
    context_unknown = False
    seen_step_ids = []
    for op in ops:
        action = _schematic_payload(op)
        step_id = _schematic_step_id(op, op['index'])
        seen_step_ids.append(step_id)
        args = ['call', ('schematic.text.move' if op['op'] == 'move_text'
                         else 'schematic.component.modify'),
                '--payload', json.dumps(action, ensure_ascii=False,
                                        separators=(',', ':'))]
        args = _with_target(args, project, document_name, window)
        record = _run_cli(runner, args, easycirq=easycirq, timeout=timeout)
        payload = record.get('payload')
        context, context_reason = _context_status(contract, document, payload)
        ok, verify_reason = _verified_payload(
            payload, 'schematic.text.move' if op['op'] == 'move_text'
            else 'schematic.component.modify')
        calls.append({'step_id': step_id, 'op': op['op'],
                      'action': args[1], 'exit': record.get('exit'),
                      'ok': _record_ok(record), 'verified': ok,
                      'context': context, 'reason': verify_reason})
        status = ('ok' if (_record_ok(record) and ok and context != 'mismatch')
                  else ('unknown' if record.get('exit') is None else 'failed'))
        entries.append({'journalVersion': 1, 'contractId': contract.get('id'),
                        'id': step_id,
                        'opKey': operation_key(op),
                        'status': status,
                        'action': args[1],
                        'exit': record.get('exit')})
        if context == 'mismatch' and target_failure is None:
            target_failure = context_reason
        if context == 'unknown':
            context_unknown = True
            entries[-1]['context'] = 'unknown'
    if journal_path:
        _append_journal(journal_path, entries)
    readback = _schematic_readback(
        runner, easycirq, timeout, window, contract, document, project, ops)
    write_confirmed = _readback_verified(ops, readback)
    if context_unknown and write_confirmed is True:
        # A verified readback without a response context cannot prove which
        # document was edited; keep the fact unknown instead of verified.
        write_confirmed = None
        readback.setdefault('issues', []).append(
            'response context is missing; target identity is unproven')
    save_confirmed = None
    save_record = None
    if flags.get('save'):
        args = ['call', 'schematic.save', '--payload', '{}']
        args = _with_target(args, project, document_name, window)
        save_record = _run_cli(runner, args, easycirq=easycirq, timeout=timeout)
        saved, _reason = _verified_payload(save_record.get('payload'),
                                           'schematic.save')
        save_confirmed = True if saved and _record_ok(save_record) else (
            False if save_record.get('exit') is not None else None)
    after = _schematic_after(fresh, ops, readback)
    diff = diff_observations(fresh, after, scope=contract.get('scope'),
                             tolerance=(contract.get('scope') or {}).get(
                                 'tolerance'))
    invariants = check_invariants(contract, diff, after=after)
    payload = _apply_base(contract, plan, write_requested=True,
                          status='verified', validation=validation)
    payload['writes_sent'] = len(calls)
    payload['call_ok'] = all(call.get('ok') for call in calls) if calls \
        else None
    payload['write_confirmed'] = write_confirmed
    payload['save_confirmed'] = save_confirmed
    payload['reopen_confirmed'] = None
    payload['quality_passed'] = None
    payload['calls'] = calls
    payload['readback'] = readback
    payload['diff'] = diff
    payload['invariants'] = invariants
    payload['journal'] = {'path': journal_path,
                          'entries': entries,
                          'status': 'written' if journal_path else 'inline'}
    payload['baseline'] = {
        'expected': (contract.get('baseline') or {}).get('semantic_sha256'),
        'observed': _observation_revision(fresh)[0],
    }
    if target_failure:
        payload['status'] = 'target_mismatch'
        payload['ok'] = False
        payload['write_confirmed'] = False
        payload['failure'] = {
            'failure_class': schemas.FAILURE_TARGET_MISMATCH,
            'reason': 'target_mismatch',
            'message': target_failure,
        }
    elif write_confirmed is False or \
            (invariants and invariants.get('status') == 'fail'):
        payload['status'] = 'mismatch'
        payload['ok'] = False
        payload['failure'] = {
            'failure_class': schemas.FAILURE_VERIFICATION_FAILED,
            'reason': 'readback_mismatch',
            'message': 'the readback does not match the intended edit',
        }
    elif write_confirmed is None:
        payload['status'] = 'unknown'
        payload['ok'] = False
        payload['failure'] = {
            'failure_class': schemas.FAILURE_UNKNOWN_EXECUTION_STATE,
            'reason': 'readback_missing',
            'message': 'the write was sent but no readback proves it landed',
        }
    else:
        payload['ok'] = (save_confirmed is not False)
    if payload['write_confirmed'] is None:
        payload['unknown'].append({'field': 'write_confirmed',
                                   'reason': 'readback is missing or unreadable'})
    if payload['save_confirmed'] is None:
        payload['unknown'].append({'field': 'save_confirmed',
                                   'reason': 'save receipt was not observed'})
    if payload['reopen_confirmed'] is None:
        payload['unknown'].append({'field': 'reopen_confirmed',
                                   'reason': 'no reopen/readback was performed'})
    if payload['quality_passed'] is None:
        payload['unknown'].append({'field': 'quality_passed',
                                   'reason': 'no quality evaluation was run'})
    return payload


def _apply_pcb(contract, plan, validation, fresh, document, *,
               runner, easycirq, window, journal_path, timeout):
    pcb_apply_plan, pcb_cli = _pcb_modules()
    included = [action for action in validation['actions']
                if action.get('already_applied') is not True]
    if not included:
        payload = _apply_base(contract, plan, write_requested=True,
                              status='no_op', validation=validation)
        payload['ok'] = True
        payload['unknown'] = list(payload.get('unknown') or []) + [
            {'field': 'write', 'reason': 'all operations were already present'}]
        payload['notes'].append('no write needed: every operation is already '
                                'present in the fresh observation')
        return payload
    _kind, all_ops, flags, _error = _normalize_plan_ops(plan)
    included_indices = {action['index'] for action in included}
    plan_ops = [op for op in all_ops if op['index'] in included_indices]
    plan_copy = _plan_ops_for_compile(plan, 'pcb', plan_ops)
    before_dump = _raw_before_dump(plan)
    if before_dump is None:
        return _apply_refused(
            contract, plan, validation,
            schemas.FAILURE_PRECONDITION_REFUSED, 'missing_before_dump',
            'a PCB write requires the raw plan.before_dump; refusing before '
            'any CLI call')
    binding = _before_dump_refusals(contract, plan, fresh,
                                    document=document, window=window)
    if binding:
        first = binding[0]
        return _apply_refused(
            contract, plan, validation,
            first.get('failure_class') or
            schemas.FAILURE_PRECONDITION_REFUSED,
            first.get('reason') or 'before_dump_invalid',
            first.get('message') or
            'before_dump is not bound to the live board',
            refusals=binding)
    plan_copy = _fill_place_primitive_ids(plan_copy, before_dump)
    # The contract baseline is the observation revision (SCH+PCB).  The PCB
    # adapter compares against the dump's own semantic hash, so pass that hash
    # to it instead of the composite revision.
    if isinstance(plan_copy, dict) and isinstance(plan_copy.get('base'),
                                                  dict):
        board_hash = before_dump.get('semanticSha256') or \
            before_dump.get('semantic_sha256')
        if board_hash:
            plan_copy = copy.deepcopy(plan_copy)
            plan_copy['base'] = dict(plan_copy['base'])
            plan_copy['base']['semantic_sha256'] = board_hash
    target = contract.get('target') or {}
    project = _text(target.get('project_uuid')) or \
        _text(((fresh or {}).get('project') or {}).get('name'))
    document_ref = _document_ref(document)
    capture = before_dump.get('capture') if isinstance(
        before_dump.get('capture'), dict) else {}
    window_ref = (_text(window) or _text(target.get('window_id')) or
                  _text(_first(capture, 'windowId', 'window_id')) or
                  _text(_first((fresh or {}).get('host') or {},
                               'window_id', 'windowId')))
    journal_is_user = journal_path is not None
    temp_dir = tempfile.mkdtemp(prefix='hds-scope-apply-')
    if journal_path is None:
        journal_path = os.path.join(temp_dir, 'apply.jsonl')
    else:
        parent = os.path.dirname(os.path.abspath(journal_path))
        if parent:
            os.makedirs(parent, exist_ok=True)
    report_path = os.path.join(temp_dir, 'scope-report.json')
    playbook_path = os.path.join(temp_dir, 'scope-playbook.json')
    out_dump = os.path.join(temp_dir, 'scope-after.json')
    dump_path = os.path.join(temp_dir, 'scope-before.json')
    plan_path = os.path.join(temp_dir, 'scope-plan.json')
    operation_map = []
    filtered = []
    for position, op in enumerate(plan_ops):
        step_ids = _op_step_ids(op, position)
        operation_map.append({'index': position,
                              'original_index': op['index'],
                              'key': operation_key(op),
                              'step_ids': step_ids})
        filtered.append(op)
    try:
        _append_journal(journal_path, [{
            'journalVersion': 1,
            'contractId': contract.get('id'),
            'kind': 'scoped-pcb',
            'startedAt': schemas.now_utc(),
            'operationMap': operation_map,
            'playbookSha256': None,
        }])
        _write_json(dump_path, before_dump)
        _write_json(plan_path, plan_copy)
        argv = ['--dump', dump_path,
                '--plan', plan_path,
                '--project', project or 'project',
                '--doc', document_ref or 'PCB1',
                '--out-dump', out_dump,
                '--report', report_path,
                '--playbook-out', playbook_path,
                '--journal', journal_path,
                '--timeout', str(timeout),
                '--apply']
        if window_ref:
            argv.extend(['--window', window_ref])
        plan_options = plan_copy if isinstance(plan_copy, dict) else {}
        if plan_options.get('partial', True) is not False:
            argv.append('--partial')
        if plan_options.get('yes') is True:
            argv.append('--yes')
        if easycirq:
            argv.extend(['--easycirq', easycirq])
        if runner is not None:
            original = pcb_cli.run
            pcb_cli.run = runner
            try:
                exit_code = pcb_apply_plan.main(argv)
            finally:
                pcb_cli.run = original
        else:
            exit_code = pcb_apply_plan.main(argv)
        report = None
        try:
            with open(report_path, 'r', encoding='utf-8-sig') as handle:
                report = json.load(handle)
        except (OSError, ValueError):
            report = None
        after_dump = None
        try:
            with open(out_dump, 'r', encoding='utf-8-sig') as handle:
                after_dump = json.load(handle)
        except (OSError, ValueError):
            after_dump = None
        after = None
        target_failure = None
        after_hash_missing = False
        normalization_failed = False
        if isinstance(after_dump, dict):
            after = copy.deepcopy(fresh)
            # ``out-dump`` is a raw ``pcb dump``; normalize it to the same
            # shape as ``observe`` output before diffing.  Comparing a raw
            # dump with a normalized observation reports every copper item as
            # removed+added and hides real changes.
            try:
                try:  # package import (feedback.scope)
                    from . import observe as observe_module
                except ImportError:  # pragma: no cover - flat import
                    import observe as observe_module
                after['pcb'] = observe_module.normalize_pcb_dump(after_dump)
            except Exception:
                normalization_failed = True
                after['pcb'] = after_dump
            after_hash = _text(after_dump.get('semanticSha256')) or \
                _text(after_dump.get('semantic_sha256'))
            revision = dict(after.get('revision') or {})
            # Never fall back to the before hash: a missing after hash is
            # "not measured", not evidence that the board did not change.
            revision['semantic_sha256'] = after_hash
            revision['per_document'] = {}
            after['revision'] = revision
            capture = after_dump.get('capture') if isinstance(
                after_dump.get('capture'), dict) else {}
            expected_project = _text((contract.get('target') or {}).get(
                'project_uuid')) or _text(_first(
                    (fresh or {}).get('project') or {}, 'uuid',
                    'project_uuid', 'projectUuid'))
            expected_document = _document_uuid(document) or _text(_first(
                _obs_pcb(fresh) or {}, 'document_uuid', 'documentUuid'))
            expected_window = (
                _text((contract.get('target') or {}).get('window_id')) or
                _text(_first((fresh or {}).get('host') or {}, 'window_id',
                             'windowId')))
            bindings = (
                ('projectUuid', expected_project, 'project'),
                ('documentUuid', expected_document, 'document'),
                ('windowId', expected_window, 'window'),
            )
            for field, expected, label in bindings:
                actual = _text(capture.get(field))
                if not actual:
                    target_failure = (
                        'out-dump capture does not identify its %s; the '
                        'readback cannot be bound to the write target' % label)
                    break
                if expected and actual != expected:
                    target_failure = 'out-dump %s %s != target %s' % (
                        label, actual, expected)
                    break
            if not after_hash:
                after_hash_missing = True
        diff = (diff_observations(fresh, after, scope=contract.get('scope'),
                                  tolerance=(contract.get('scope') or {}).get(
                                      'tolerance'))
                if after is not None and not normalization_failed else None)
        invariants = (check_invariants(contract, diff, after=after)
                      if diff is not None else None)
        entries = _read_journal_file(journal_path) or []
        payload = _apply_base(contract, plan, write_requested=True,
                              status='unknown', validation=validation)
        if normalization_failed:
            payload['notes'].append(
                'the after dump could not be normalized; diff and invariants '
                'were not computed')
        payload['writes_sent'] = (1 if isinstance(report, dict) and
                                  report.get('apply') else 0)
        payload['exit_code'] = exit_code
        payload['journal'] = {
            'path': journal_path if journal_is_user else None,
            'entries': entries,
            'status': ('read' if entries else 'missing'),
        }
        payload['report'] = report
        payload['diff'] = diff
        payload['invariants'] = invariants
        payload['after_observation'] = after
        payload['baseline'] = {
            'expected': (contract.get('baseline') or {}).get(
                'semantic_sha256'),
            'observed': _observation_revision(fresh)[0],
            'after': _observation_revision(after)[0] if after else None,
        }
        apply_info = (report or {}).get('apply') if isinstance(report, dict) \
            else None
        payload['call_ok'] = (apply_info.get('exit') == 0
                              if isinstance(apply_info, dict) else None)
        if isinstance(report, dict):
            journal_status = _text((report.get('journal') or {}).get('status'))
            save_status = _text((report.get('save') or {}).get('status'))
            reload_status = _text((report.get('reload') or {}).get('status'))
            dump_status = _text(((report.get('dump') or {}).get('after') or
                                 {}).get('status'))
        else:
            journal_status = save_status = reload_status = dump_status = ''
        if save_status.startswith('ok'):
            payload['save_confirmed'] = True
        elif save_status:
            payload['save_confirmed'] = False
        if reload_status.startswith('ok'):
            payload['reopen_confirmed'] = True if dump_status == 'ok' else None
        elif reload_status in ('failed', 'error'):
            payload['reopen_confirmed'] = False
        presence = [_op_present(action_op, after) for action_op in plan_ops] \
            if after is not None else [None]
        if after is None:
            payload['write_confirmed'] = None
        elif any(item is False for item in presence):
            payload['write_confirmed'] = False
        elif journal_status and journal_status != 'pass' and \
                isinstance(report, dict) and \
                (report.get('journal') or {}).get('failed'):
            payload['write_confirmed'] = False
        elif any(item is None for item in presence):
            payload['write_confirmed'] = None
        else:
            payload['write_confirmed'] = True
        if isinstance(report, dict):
            report_status = _text(report.get('status'))
            if report_status in ('verified', 'verified_geometry'):
                payload['status'] = 'verified'
                payload['ok'] = True
            elif report_status == 'no_op':
                payload['status'] = 'no_op'
                payload['ok'] = True
            elif report_status == 'unverified':
                payload['status'] = 'unverified'
                payload['ok'] = False
            elif report_status == 'mismatch':
                payload['status'] = 'mismatch'
                payload['ok'] = False
            elif report_status in ('refused', 'invalid_input'):
                payload['status'] = 'refused'
                payload['ok'] = False
            else:
                payload['status'] = 'unknown'
                payload['ok'] = False
            if report.get('failure'):
                payload['failure'] = {
                    'failure_class': schemas.FAILURE_VERIFICATION_FAILED,
                    'reason': _text(report['failure'].get('stage')) or
                              'pcb_apply_failed',
                    'message': _text(report['failure'].get('message')),
                    'detail': report['failure'],
                }
        else:
            payload['status'] = 'unknown'
            payload['ok'] = False
            payload['failure'] = {
                'failure_class': schemas.FAILURE_UNKNOWN_EXECUTION_STATE,
                'reason': 'missing_report',
                'message': 'pcb_apply_plan did not produce a report',
            }
        if normalization_failed and payload.get('status') in ('verified',
                                                              'no_op'):
            # The executor may report its own save/reload success, but without
            # a normalized after-dump this layer cannot verify scope or
            # invariants.  Keep the execution facts, drop the misleading
            # "verified" status, and mark write confirmation unmeasured.
            payload['status'] = 'unknown'
            payload['ok'] = False
            payload['write_confirmed'] = None
            payload['failure'] = {
                'failure_class': schemas.FAILURE_VERIFICATION_FAILED,
                'reason': 'after_dump_unreadable',
                'message': ('the after dump could not be normalized; scope '
                            'changes and invariants were not verified'),
            }
        if after_hash_missing and payload.get('status') in ('verified',
                                                            'no_op'):
            payload['status'] = 'unknown'
            payload['ok'] = False
            payload['write_confirmed'] = None
            payload['failure'] = {
                'failure_class': schemas.FAILURE_VERIFICATION_FAILED,
                'reason': 'after_hash_missing',
                'message': ('the after dump carries no semanticSha256; the '
                            'readback content was not measured'),
            }
        if invariants and invariants.get('status') == 'fail':
            payload['status'] = 'mismatch'
            payload['ok'] = False
            if not payload.get('failure'):
                payload['failure'] = {
                    'failure_class': schemas.FAILURE_VERIFICATION_FAILED,
                    'reason': 'invariant_failed',
                    'message': 'an invariant failed after the write',
                }
        if target_failure:
            payload['status'] = 'target_mismatch'
            payload['ok'] = False
            payload['write_confirmed'] = False
            payload['failure'] = {
                'failure_class': schemas.FAILURE_TARGET_MISMATCH,
                'reason': 'target_mismatch',
                'message': target_failure,
            }
        for field, reason in (
                ('write_confirmed', 'readback is missing or unreadable'),
                ('save_confirmed', 'save receipt was not observed'),
                ('reopen_confirmed', 'reopen persistence was not observed'),
                ('quality_passed', 'no quality evaluation was run')):
            if payload.get(field) is None:
                payload['unknown'].append({'field': field, 'reason': reason})
        return payload
    finally:
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)


def _op_step_ids(op, index):
    kind = op.get('op')
    if kind == 'place':
        return ['place-%s' % _text(op.get('designator'))]
    if kind == 'track':
        points = _points(op.get('points')) or []
        return ['track-%d-%d' % (index, segment + 1)
                for segment in range(max(0, len(points) - 1))]
    if kind in ('via', 'pour'):
        return ['%s-%d' % (kind, index)]
    if kind == 'move_text':
        return ['move_text-%d' % index]
    if kind in ('move_component', 'rotate_component'):
        return ['move_component-%d' % index]
    return []


def _write_json(path, value):
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='\n') as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write('\n')


def apply_scoped(contract, plan, *, runner=None, easycirq=None, window=None,
                 write=False, journal_path=None, timeout=120):
    """Preview or apply a scoped plan, keeping five facts separate.

    ``write=False`` is always a preview: no CLI call, no file write.
    ``write=True`` refuses a ``preview_only`` contract, re-checks the live
    baseline carried by the plan and refuses on any mismatch.  A missing
    readback is recorded as ``None`` (NOT RUN), never as verified.
    """
    if not write:
        return _preview_apply(contract, plan, write_requested=False)
    if contract.get('preview_only') is True:
        validation = _validate_plan_internal(contract, plan)
        return _apply_refused(
            contract, plan, validation,
            schemas.FAILURE_PRECONDITION_REFUSED, 'preview_only',
            'contract.preview_only is true: writes are not allowed')
    fresh = _plan_observation(plan)
    validation = _validate_plan_internal(contract, plan, before=fresh)
    if not validation.get('ok'):
        return _apply_refused(
            contract, plan, validation,
            validation.get('failure_class') or
            schemas.FAILURE_PRECONDITION_REFUSED,
            'plan_invalid',
            'the plan was refused before any write; see refusals',
            refusals=validation.get('refusals') or [])
    if fresh is None:
        return _apply_refused(
            contract, plan, validation, schemas.FAILURE_STALE_BASELINE,
            'missing_fresh_observation',
            'apply_scoped needs a fresh observation in the plan '
            '(plan.observation or plan.before) to re-check the live baseline')
    baseline = check_baseline(contract, fresh)
    if not baseline.get('ok'):
        return _apply_refused(
            contract, plan, validation,
            baseline.get('failure_class') or schemas.FAILURE_STALE_BASELINE,
            baseline.get('status') or 'stale_baseline',
            'the live baseline does not match the contract: %s' %
            '; '.join(baseline.get('reasons') or []),
            baseline=baseline)
    if runner is None and easycirq is None:
        return _apply_refused(
            contract, plan, validation, schemas.FAILURE_HOST_UNAVAILABLE,
            'host_unavailable',
            'no runner or explicit easycirq path was supplied; refusing to '
            'resolve easycirq from PATH')
    document = validation.get('document')
    kind = validation.get('plan_kind')
    if kind == 'pcb':
        return _apply_pcb(contract, plan, validation, fresh, document,
                          runner=runner, easycirq=easycirq, window=window,
                          journal_path=journal_path, timeout=timeout)
    return _apply_schematic(contract, plan, validation, fresh, document,
                            runner=runner, easycirq=easycirq, window=window,
                            journal_path=journal_path, timeout=timeout)


# ---------------------------------------------------------------------------
# recovery
# ---------------------------------------------------------------------------

def _journal_entries(journal):
    if isinstance(journal, list):
        return [item for item in journal if isinstance(item, dict)], None, []
    if isinstance(journal, str):
        entries = _read_journal_file(journal)
        if entries is None:
            return [], journal, ['journal file is missing or unreadable']
        return entries, journal, []
    if isinstance(journal, dict):
        for key in ('entries', 'journal', 'lines'):
            value = journal.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)], \
                    journal.get('path'), []
        if isinstance(journal.get('steps'), list):
            entries = []
            header = journal.get('header') or {}
            if header:
                entries.append(dict(header))
            entries.extend(item for item in journal['steps']
                           if isinstance(item, dict))
            return entries, journal.get('path'), []
    return [], None, ['journal must be a path, a list or an object with entries']


def _journal_status(entry):
    status = _text(entry.get('status')).lower()
    if status.startswith('ok') or status == 'applied':
        return 'confirmed'
    if status in ('failed', 'error', 'fail'):
        return 'failed'
    if status in ('sent', 'unknown', 'in_progress'):
        return 'unknown'
    if status in ('planned', 'pending', 'not_sent'):
        return 'pending'
    return 'unknown'


def _journal_kind(entries):
    for entry in entries:
        if 'playbookSha256' in entry:
            return 'pcb-apply'
        if entry.get('kind') == 'scoped-pcb' or 'operationMap' in entry:
            return 'scoped-pcb'
        if entry.get('journalVersion') and entry.get('opKey'):
            return 'scoped'
    return 'unknown'


def _operation_map(entries):
    for entry in reversed(entries):
        if isinstance(entry.get('operationMap'), list):
            return entry['operationMap']
    return None


def _entry_for_op(op_key, step_ids, entries):
    matches = []
    for entry in entries:
        if entry.get('opKey') and entry.get('opKey') == op_key:
            matches.append(entry)
            continue
        entry_id = _text(entry.get('id'))
        if entry_id and entry_id in step_ids:
            matches.append(entry)
    return matches


def _merge_journal_status(matches):
    if not matches:
        return None, []
    states = [_journal_status(entry) for entry in matches]
    if 'confirmed' in states:
        return 'confirmed', matches
    if 'failed' in states:
        return 'failed', matches
    if 'unknown' in states:
        return 'unknown', matches
    if 'pending' in states:
        return 'pending', matches
    return 'unknown', matches


def recover(contract, journal, current_observation=None, plan=None):
    """Map journal entries to operations and decide what is safe to retry."""
    entries, path, problems = _journal_entries(journal)
    kind = _journal_kind(entries)
    operation_map = _operation_map(entries)
    if operation_map:
        map_by_index = {}
        for item in operation_map:
            if not isinstance(item, dict):
                continue
            original = item.get('original_index', item.get('index'))
            if isinstance(original, int):
                map_by_index[original] = item
    else:
        map_by_index = {}
    observation = _as_observation(current_observation) \
        if current_observation is not None else None
    operations = []
    applied, pending, unknown, duplicate_risk = [], [], [], []
    if plan is not None:
        plan_kind, ops, _flags, error = _normalize_plan_ops(plan)
        if error:
            return {
                'schema': schemas.SCHEMA_RECOVERY, 'ok': False,
                'status': 'blocked', 'contract_id': contract.get('id'),
                'journal': {'path': path, 'entries': len(entries),
                            'kind': kind, 'problems': [error]},
                'operations': [], 'applied': [], 'pending': [], 'unknown': [],
                'duplicate_risk': [], 'safe_to_retry': False,
                'notes': ['plan cannot be interpreted; recovery is blocked'],
            }
    else:
        ops = []
        for index, entry in enumerate(entries):
            entry_id = _text(entry.get('id'))
            if not entry_id or entry_id in ('save', 'reload', 'dump'):
                continue
            name = entry_id.split('-', 1)[0]
            if name not in PCB_OP_KINDS + ('move_text', 'move_component'):
                continue
            ops.append({'index': index, 'op': name,
                        'raw_index': index, '_journal_key':
                        _text(entry.get('opKey')) or 'journal:%s' % entry_id,
                        '_journal_id': entry_id})
    for op in ops:
        key = op.get('_journal_key') or operation_key(op)
        mapped = map_by_index.get(op['index']) if op.get('_journal_key') \
            is None else None
        if mapped:
            key = _text(mapped.get('key')) or key
        step_ids = _op_step_ids(op, op['index'])
        if mapped and mapped.get('step_ids'):
            step_ids = [str(item) for item in mapped['step_ids']]
        if op.get('_journal_id'):
            matches = [entry for entry in entries
                       if _text(entry.get('id')) == op['_journal_id']]
        else:
            matches = _entry_for_op(key, step_ids, entries)
        journal_status, matched = _merge_journal_status(matches)
        present = _op_present(op, observation) if observation is not None \
            else None
        confirmed_count = sum(1 for entry in matched
                              if _journal_status(entry) == 'confirmed')
        duplicate = confirmed_count > 1
        if journal_status == 'confirmed' and present is False:
            state = 'unknown'
            reason = 'journal says confirmed but the readback does not show it'
        elif journal_status == 'confirmed':
            state = 'applied'
            reason = 'journal confirms the write'
        elif journal_status == 'failed' and present is True:
            state = 'applied'
            reason = 'journal says failed but the readback shows the write'
        elif journal_status == 'failed':
            state = 'pending'
            reason = 'journal says failed and the readback does not show it'
        elif journal_status in ('unknown',) and present is True:
            state = 'applied'
            reason = 'readback shows the write despite an unconfirmed journal'
        elif journal_status in ('unknown',):
            state = 'unknown'
            reason = 'the write was sent but neither the journal nor the ' \
                     'readback confirms it'
        elif present is True:
            state = 'applied'
            reason = 'readback shows the write; the journal has no entry'
        elif present is False:
            state = 'pending'
            reason = 'neither the journal nor the readback shows the write'
        else:
            state = 'unknown'
            reason = 'the operation state is not measurable'
        non_idempotent = op.get('op') in NON_IDEMPOTENT_KINDS
        risk = duplicate or (state == 'unknown' and non_idempotent)
        safe = (state == 'pending') or (state == 'unknown' and
                                        not non_idempotent)
        entry = {
            'index': op['index'],
            'operation_key': key,
            'op': op.get('op'),
            'designator': op.get('designator'),
            'net': op.get('net'),
            'journal_status': journal_status,
            'observation': ('present' if present is True else
                            ('absent' if present is False else 'unknown')),
            'state': state,
            'reason': reason,
            'duplicate_risk': risk,
            'safe_to_retry': safe,
            'journal_entries': [{'id': item.get('id'),
                                 'status': item.get('status')}
                                for item in matched],
        }
        operations.append(entry)
        if state == 'applied':
            applied.append(key)
        elif state == 'pending':
            pending.append(key)
        else:
            unknown.append(key)
        if risk:
            duplicate_risk.append(key)
    if not operations:
        safe_to_retry = False if problems else False
        status = 'blocked' if problems or not entries else 'unknown'
    elif unknown or duplicate_risk:
        safe_to_retry = False
        status = 'unknown'
    elif pending:
        safe_to_retry = True
        status = 'resumable'
    else:
        safe_to_retry = True
        status = 'complete'
    if problems:
        status = 'blocked' if not applied else status
        safe_to_retry = False
    notes = []
    if kind == 'pcb-apply':
        notes.append('pcb_apply_plan journal: only statuses starting with ok '
                     'are confirmed')
    if unknown:
        notes.append('%d operation(s) have unknown execution state; do not '
                     'retry non-idempotent creates' % len(unknown))
    if pending:
        notes.append('%d operation(s) can be retried' % len(pending))
    if applied:
        notes.append('%d operation(s) are already applied and must be skipped'
                     % len(applied))
    return {
        'schema': schemas.SCHEMA_RECOVERY,
        'ok': status in ('complete', 'resumable'),
        'status': status,
        'contract_id': contract.get('id') if isinstance(contract, dict)
        else None,
        'generated_at': schemas.now_utc(),
        'journal': {'path': path, 'entries': len(entries), 'kind': kind,
                    'problems': problems},
        'operations': operations,
        'applied': applied,
        'pending': pending,
        'unknown': unknown,
        'duplicate_risk': duplicate_risk,
        'safe_to_retry': safe_to_retry,
        'notes': notes,
    }


# ---------------------------------------------------------------------------
# contract construction
# ---------------------------------------------------------------------------

def _default_invariants(target):
    kinds = []
    for document in (target or {}).get('documents') or []:
        kind = _document_kind(document)
        if kind == 'pcb':
            for name in (schemas.INVARIANT_PCB_PAD_NET,
                         schemas.INVARIANT_PCB_OUTLINE,
                         schemas.INVARIANT_PCB_LOCKED,
                         schemas.INVARIANT_PCB_UNRELATED):
                if name not in kinds:
                    kinds.append(name)
        elif kind == 'schematic':
            for name in (schemas.INVARIANT_SCH_CONNECTIVITY,
                         schemas.INVARIANT_SCH_IDENTITY):
                if name not in kinds:
                    kinds.append(name)
    return kinds


def _normalize_invariants(value, target):
    if value is None:
        kinds = _default_invariants(target)
        if not kinds:
            raise schemas.ContractError(
                'cannot derive invariants: contract target document types are '
                'unknown; pass invariants explicitly')
        return [{'id': 'inv-%d' % (index + 1), 'kind': kind, 'params': {}}
                for index, kind in enumerate(kinds)]
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list) or not value:
        raise schemas.ContractError('invariants must be a non-empty list')
    result = []
    for index, item in enumerate(value):
        if isinstance(item, str):
            result.append({'id': 'inv-%d' % (index + 1), 'kind': item,
                           'params': {}})
        elif isinstance(item, dict):
            entry = copy.deepcopy(item)
            entry.setdefault('id', 'inv-%d' % (index + 1))
            if not _text(entry.get('kind')):
                raise schemas.ContractError(
                    'invariants[%d].kind is required' % index)
            entry.setdefault('params', {})
            result.append(entry)
        else:
            raise schemas.ContractError(
                'invariants[%d] must be a string or object' % index)
    return result


def _normalize_acceptance(value):
    if value is None:
        return [
            {'id': 'no-outside-changes', 'metric': 'diff.outside_scope',
             'predicate': 'count == 0'},
            {'id': 'invariants-pass', 'metric': 'invariants.status',
             'predicate': '== pass'},
        ]
    if not isinstance(value, list) or not value:
        raise schemas.ContractError('acceptance must be a non-empty list')
    result = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise schemas.ContractError(
                'acceptance[%d] must be an object' % index)
        entry = copy.deepcopy(item)
        entry.setdefault('id', 'accept-%d' % (index + 1))
        if not _text(entry.get('metric')) or not _text(entry.get('predicate')):
            raise schemas.ContractError(
                'acceptance[%d] needs metric and predicate' % index)
        result.append(entry)
    return result


def _default_recovery():
    return {
        'required': True,
        'strategy': 'journal_resume',
        'idempotent_operations': ['place', 'move_component', 'move_text',
                                  'rotate_component'],
        'non_idempotent_operations': list(NON_IDEMPOTENT_KINDS),
        'atomic_rollback': False,
        'requires_fresh_readback': True,
        'note': 'the host does not provide an atomic transaction; recovery '
                'uses the journal, content-stable operation keys and a fresh '
                'readback',
    }


def build_contract(*, contract_id, goal, target, observation, scope,
                   allowed_actions, invariants=None, acceptance=None,
                   recovery=None, preview_only=True):
    """Build a schema-valid ``hds-modification/v1`` contract.

    The observation supplies the baseline hash, target project/documents and a
    compact baseline snapshot used by ``validate_plan`` even when the caller
    does not pass a fresh observation.  A contract built without a baseline
    hash is valid data but every plan validation refuses it.
    """
    if not isinstance(contract_id, str) or not contract_id.strip():
        raise schemas.ContractError('contract_id must be a non-empty string')
    if not isinstance(goal, str) or not goal.strip():
        raise schemas.ContractError('goal must be a non-empty string')
    observation = _as_observation(observation) if observation else None
    if observation is not None and isinstance(observation, dict) and \
            observation.get('schema') == schemas.SCHEMA_OBSERVATION:
        schemas.validate_observation(observation)
    normalized_target = _normalize_target(target, observation)
    normalized_scope = normalize_scope(scope)
    writable = normalized_scope.get('writable') or {}
    if not any(writable.get(key) for key in ('objects', 'regions', 'nets')):
        raise schemas.ContractError('contract.scope.writable must name '
                                    'objects, regions or nets')
    if isinstance(allowed_actions, str):
        allowed_actions = [allowed_actions]
    if not isinstance(allowed_actions, list) or not allowed_actions:
        raise schemas.ContractError('allowed_actions must be a non-empty list')
    for action in allowed_actions:
        if action not in schemas.ALLOWED_ACTIONS:
            raise schemas.ContractError(
                'allowed_actions: unknown action %r' % (action,))
    normalized_invariants = _normalize_invariants(invariants,
                                                  normalized_target)
    normalized_acceptance = _normalize_acceptance(acceptance)
    normalized_recovery = copy.deepcopy(recovery) if recovery is not None \
        else _default_recovery()
    if not isinstance(normalized_recovery, dict):
        raise schemas.ContractError('recovery must be an object')
    baseline = _build_baseline(observation, normalized_target)
    contract = schemas.new_modification(
        contract_id=contract_id,
        goal=goal,
        target=normalized_target,
        baseline=baseline,
        scope=normalized_scope,
        allowed_actions=list(dict.fromkeys(allowed_actions)),
        invariants=normalized_invariants,
        acceptance=normalized_acceptance,
        recovery=normalized_recovery,
        preview_only=bool(preview_only),
    )
    return schemas.validate_modification(contract)


