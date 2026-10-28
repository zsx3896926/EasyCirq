#!/usr/bin/env python3
"""Offline PCB preflight over a measured dump, intent and placement plan.

The preflight answers one question before any write: *is this board + intent +
plan combination measured well enough to apply, and what is left unverified?*
It never talks to EDA.  Every input is a retained JSON artifact:

* ``pcb dump`` (``--dump``, required) - the common geometry source;
* ``sch read``/``sch connectivity`` (``--schematic``) - pin counts per part;
* ``pcb-intent.json`` (``--intent``) - constraints, EP/connector/RF/sensor
  declarations and power nets;
* ``pcb-constraints`` output (``--constraints``) - compiled constraints; when
  omitted they are compiled from ``--intent`` with the same core function;
* a placement plan (``--plan``) - ``{"placements": [...]}"`` with optional
  ``base_semantic_sha256`` and ``primitive_ids``;
* ``component_identity_check.py`` output (``--identity``).

Report schema ``design-engine-pcb-preflight/v1``.  Exit codes:

* ``ready`` -> 0
* ``review`` -> 1  (only advisory items failed / are unmeasured)
* ``blocked`` / ``incomplete`` / invalid input -> 2

Design rules (from the round10 interface contract):

* hard checks that are ``unmeasured`` block; they are never downgraded;
* a missing optional intent section is ``unmeasured``/advisory, never a pass;
* a stale ``base_semantic_sha256`` or a stale/duplicate ``primitiveId`` is a
  hard blocking failure;
* preferred constraint failures are advisory (the core emits
  ``severity=preferred``); they cause ``review``, never ``blocked``;
* decap/feedback ``near_pin`` rows must resolve both pads in the dump and the
  two pad nets must be equal;
* EP pads, antenna keepouts and sensor copper voids are checked only from
  explicit intent data - a pad whose number/name merely looks like ``EP`` or
  ``9`` is never guessed;
* pad-centre distances are measurements, not copper-path proofs.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pcb_cli import load_json, write_json  # noqa: E402
from design_engine.pcb_workflow import (  # noqa: E402
    apply_placements,
    audit_fabrication,
    audit_power,
    bind_template,
    compile_constraints,
    load_templates,
    normalize_board,
    validate_placement,
)

SCHEMA = 'design-engine-pcb-preflight/v1'
EXIT_CODES = {'ready': 0, 'review': 1, 'blocked': 2, 'incomplete': 2}

HARD = 'hard'
ADVISORY = 'advisory'
PASS = 'pass'
FAIL = 'fail'
UNMEASURED = 'unmeasured'
SKIPPED = 'skipped'

ALLOWED_CONFLICT_KINDS = {'edge_fixed_requires_pose_check'}
EDGES = {'left', 'right', 'top', 'bottom'}
NEAR_PIN_ROLES = {'decap', 'feedback'}


class InvalidInput(Exception):
    """The supplied artifact cannot be interpreted; the CLI exits 2."""


# ---------------------------------------------------------------------------
# Small value helpers


def _finite(value):
    return type(value) in (int, float) and math.isfinite(float(value))


def _text(value):
    if value is None:
        return ''
    return str(value).strip()


def _envelope(value):
    """Unwrap ``{"result": {...}}`` from retained CLI output."""
    if isinstance(value, dict) and isinstance(value.get('result'), dict):
        return value['result']
    return value


def _casefold(value):
    return _text(value).casefold()


def _load_object(path, label):
    try:
        value = load_json(path)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise InvalidInput('%s: cannot read %s: %s' % (label, path, exc)) from exc
    if not isinstance(value, dict):
        raise InvalidInput('%s: JSON object required in %s' % (label, path))
    return value


def _load_plan(path):
    try:
        value = load_json(path)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise InvalidInput('plan: cannot read %s: %s' % (path, exc)) from exc
    if isinstance(value, list):
        return {'placements': value}
    if not isinstance(value, dict):
        raise InvalidInput('plan: JSON object or placement list required in %s' % path)
    if isinstance(value.get('ops'), list):
        raise InvalidInput(
            'plan: an apply playbook (ops) is not a placement plan; '
            'pass {"placements": [...]}')
    return value


def _component_map(board):
    result = {}
    for component in board.get('components') or []:
        designator = _text(component.get('designator'))
        if designator:
            result[designator] = component
    return result


def _pad_index(component):
    result = {}
    for pad in (component or {}).get('pads') or []:
        number = pad.get('number') if pad.get('number') is not None else pad.get('padNumber')
        if number is not None:
            result[_text(number)] = pad
    return result


def _total_pads(board):
    return sum(len(component.get('pads') or [])
               for component in board.get('components') or [])


def _semantic_hash(board, dump):
    return ((board.get('source') or {}).get('semantic_sha256') or
            dump.get('semanticSha256'))


def _rotation_matches(actual, expected):
    try:
        actual = float(actual or 0.0) % 360.0
        expected = float(expected) % 360.0
    except (TypeError, ValueError):
        return False
    return min(abs(actual - expected), abs(actual - expected + 360.0),
               abs(actual - expected - 360.0)) <= 1e-6


def _box_edge_distance(box, edge, outline=None):
    """Distance from a component bbox to a board edge, in mil.

    The measured outline is the reference: the board origin is not guaranteed to
    be (0, 0), so ``box[2]`` is not the distance to a right edge.
    """
    if outline:
        if edge == 'left':
            return box[0] - outline[0]
        if edge == 'right':
            return outline[2] - box[2]
        if edge == 'bottom':
            return box[1] - outline[1]
        if edge == 'top':
            return outline[3] - box[3]
    if edge == 'left':
        return box[0]
    if edge == 'right':
        return box[2]
    if edge == 'bottom':
        return box[1]
    if edge == 'top':
        return box[3]
    raise ValueError('unknown edge %r' % edge)


def _contains_box(outer, inner, tolerance=0.0):
    return (inner[0] >= outer[0] - tolerance and
            inner[2] <= outer[2] + tolerance and
            inner[1] >= outer[1] - tolerance and
            inner[3] <= outer[3] + tolerance)


def _point_in_box(point, box):
    return box[0] <= point[0] <= box[2] and box[1] <= point[1] <= box[3]


def _segment_intersects_box(start, end, box):
    """Liang-Barsky clipping; True when the segment touches the box."""
    dx, dy = end[0] - start[0], end[1] - start[1]
    p = [-dx, dx, -dy, dy]
    q = [start[0] - box[0], box[2] - start[0],
         start[1] - box[1], box[3] - start[1]]
    u1, u2 = 0.0, 1.0
    for pi, qi in zip(p, q):
        if abs(pi) < 1e-12:
            if qi < 0:
                return False
            continue
        t = qi / pi
        if pi < 0:
            u1 = max(u1, t)
        else:
            u2 = min(u2, t)
        if u1 > u2:
            return False
    return True


def _box_from_value(value):
    """Accept ``[x0,y0,x1,y1]`` or ``{minX,minY,maxX,maxY}``."""
    if isinstance(value, dict):
        try:
            value = [value['minX'], value['minY'], value['maxX'], value['maxY']]
        except (KeyError, TypeError):
            return None
    if not isinstance(value, list) or len(value) != 4:
        return None
    if not all(_finite(item) for item in value):
        return None
    box = [float(item) for item in value]
    if box[0] > box[2] or box[1] > box[3]:
        return None
    return box


# ---------------------------------------------------------------------------
# Report assembly


def _new_report(board, dump, plan, plan_supplied):
    source = board.get('source') or {}
    capture = dump.get('capture') or {}
    copper = board.get('copper') or {}
    dump_project = dump.get('project') if isinstance(dump.get('project'), str) else None
    summary = {
        'source': {
            'project_uuid': source.get('project_uuid'),
            'project_name': source.get('project_name'),
            'document_uuid': source.get('document_uuid'),
            'captured_at': source.get('captured_at'),
            'semantic_sha256': source.get('semantic_sha256'),
        },
        'project': (source.get('project_name') or capture.get('projectName') or
                    dump_project),
        'document_uuid': source.get('document_uuid') or capture.get('documentUuid'),
        'document_type': capture.get('documentType'),
        'captured_at': source.get('captured_at') or dump.get('capturedAt'),
        'units': board.get('units'),
        'coverage': board.get('coverage') or {},
        'component_count': len(board.get('components') or []),
        'pad_count': _total_pads(board),
        'outline_bbox': (board.get('outline') or {}).get('bbox'),
        'copper_layers': (board.get('layers') or {}).get('copper_count'),
        'silk_count': len(board.get('silk') or []),
        'copper_counts': {
            'lines': len(copper.get('lines') or []),
            'vias': len(copper.get('vias') or []),
            'pours': len(copper.get('pours') or []),
        },
        'plan': {
            'supplied': bool(plan_supplied),
            'placements': len((plan or {}).get('placements') or []),
            'base_semantic_sha256': (plan or {}).get('base_semantic_sha256'),
        },
    }
    return {
        'schema': SCHEMA,
        'status': 'ready',
        'checks': [],
        'counts': {'pass': 0, 'fail': 0, 'unmeasured': 0,
                   'hard_fail': 0, 'hard_unmeasured': 0},
        'board': summary,
        'notes': [
            'offline preflight: no zhigou command is executed',
            'hard check fail/unmeasured blocks; advisory items only cause review',
            'preferred constraints are advisory by contract and never block',
            'near_pin distances are pad-centre measurements, not copper-path proofs',
        ],
        'not_checked': [],
    }


def _add(report, check_id, status, severity, message, source, objects=None):
    report['checks'].append({
        'id': check_id,
        'status': status,
        'severity': severity,
        'objects': objects or {},
        'message': message,
        'source': source,
    })


def _finish(report):
    counts = {'pass': 0, 'fail': 0, 'unmeasured': 0,
              'hard_fail': 0, 'hard_unmeasured': 0}
    for check in report['checks']:
        status = check['status']
        if status in counts:
            counts[status] += 1
        if check['severity'] == HARD and status == FAIL:
            counts['hard_fail'] += 1
        if check['severity'] == HARD and status == UNMEASURED:
            counts['hard_unmeasured'] += 1
        if status in (UNMEASURED, SKIPPED):
            report['not_checked'].append({
                'check': check['id'],
                'reason': check['message'],
            })
    report['counts'] = counts
    report['not_checked'].extend([
        {'check': 'global', 'reason': 'native DRC / pcb check were not run '
                                      '(pcb_gate owns those stages)'},
        {'check': 'global', 'reason': 'copper-path connectivity through pours '
                                      'is not proven by geometry alone'},
        {'check': 'global', 'reason': 'impedance/EMC/thermal and manufacturing '
                                      'files are out of preflight scope'},
        {'check': 'global', 'reason': 'live-vs-dump freshness is not observable '
                                      'in an offline preflight'},
    ])

    coverage_broken = any(
        check['id'] in ('dump.components_coverage', 'dump.outline_coverage') and
        check['status'] != PASS
        for check in report['checks'])
    advisory_issue = any(
        check['severity'] == ADVISORY and check['status'] in (FAIL, UNMEASURED)
        for check in report['checks'])
    if coverage_broken:
        report['status'] = 'incomplete'
    elif counts['hard_fail'] or counts['hard_unmeasured']:
        report['status'] = 'blocked'
    elif advisory_issue:
        report['status'] = 'review'
    else:
        report['status'] = 'ready'
    return report


# ---------------------------------------------------------------------------
# Input normalization / structural validation


def _validate_plan_shape(plan):
    placements = plan.get('placements')
    if not isinstance(placements, list):
        raise InvalidInput('plan.placements: list required')
    base = plan.get('base_semantic_sha256')
    if base is not None and not isinstance(base, str):
        raise InvalidInput('plan.base_semantic_sha256: string required')
    primitive_ids = plan.get('primitive_ids')
    if primitive_ids is not None and not isinstance(primitive_ids, dict):
        raise InvalidInput('plan.primitive_ids: object required')
    for index, item in enumerate(placements):
        if not isinstance(item, dict):
            raise InvalidInput('plan.placements[%d]: object required' % index)
        if not _text(item.get('designator')):
            raise InvalidInput('plan.placements[%d].designator: required' % index)
        for field in ('x', 'y'):
            if not _finite(item.get(field)):
                raise InvalidInput('plan.placements[%d].%s: finite number required'
                                   % (index, field))
        if item.get('rotation') is not None and not _finite(item.get('rotation')):
            raise InvalidInput('plan.placements[%d].rotation: finite number required'
                               % index)
        if item.get('layer') is not None and type(item.get('layer')) is not int:
            raise InvalidInput('plan.placements[%d].layer: integer required' % index)
        for key in ('primitive_id', 'primitiveId'):
            if item.get(key) is not None and not isinstance(item.get(key), str):
                raise InvalidInput('plan.placements[%d].%s: string required'
                                   % (index, key))


def _validate_intent_shape(intent):
    if intent is None:
        return
    for key in ('constraints', 'components', 'modules', 'connectors', 'rf',
                'sensors', 'power_nets', 'keepouts'):
        value = intent.get(key)
        if value is not None and not isinstance(value, list):
            raise InvalidInput('intent.%s: list required' % key)
    for index, item in enumerate(intent.get('constraints') or []):
        if not isinstance(item, dict):
            raise InvalidInput('intent.constraints[%d]: object required' % index)


def _validate_constraints_shape(constraints):
    if constraints is None:
        return
    items = constraints.get('constraints')
    if items is not None and not isinstance(items, list):
        raise InvalidInput('constraints.constraints: list required')
    if constraints.get('status') is not None and not isinstance(
            constraints.get('status'), str):
        raise InvalidInput('constraints.status: string required')


def _validate_identity_shape(identity):
    if identity is None:
        return
    if not isinstance(identity.get('status'), str) or not identity.get('status'):
        raise InvalidInput('identity.status: string required '
                           '(component_identity_check.py output)')


def _validate_schematic_shape(schematic):
    if schematic is None:
        return
    if not isinstance(schematic.get('components'), list):
        raise InvalidInput('schematic.components: list required')


# ---------------------------------------------------------------------------
# Hard checks


def _coverage_checks(report, board):
    coverage = board.get('coverage') or {}
    components = coverage.get('components')
    if components == 'complete':
        _add(report, 'dump.components_coverage', PASS, HARD,
             'component inventory is measured as complete', 'dump',
             {'coverage': components,
              'components': len(board.get('components') or [])})
    else:
        _add(report, 'dump.components_coverage', UNMEASURED, HARD,
             'component inventory is %r; a complete pcb dump is required'
             % (components,), 'dump',
             {'coverage': components,
              'components': len(board.get('components') or [])})

    outline = board.get('outline') or {}
    if coverage.get('outline') == 'complete' and outline.get('bbox'):
        _add(report, 'dump.outline_coverage', PASS, HARD,
             'board outline is measured', 'dump',
             {'coverage': coverage.get('outline'),
              'bbox': outline.get('bbox')})
    else:
        _add(report, 'dump.outline_coverage', UNMEASURED, HARD,
             'board outline is not measured; no containment/edge check is possible',
             'dump', {'coverage': coverage.get('outline'),
                      'bbox': outline.get('bbox')})


def _project_candidates(dump):
    values = []

    def add(value):
        if isinstance(value, dict):
            for key in ('name', 'projectName', 'uuid', 'projectUuid'):
                add(value.get(key))
        elif value is not None and _text(value):
            values.append(_text(value))

    add(dump.get('project'))
    capture = dump.get('capture') or {}
    add(capture.get('projectName'))
    add(capture.get('projectUuid'))
    return values


def _document_candidates(dump):
    """Return ``(identifiers, types)``; a type alone is not a name proof."""
    identifiers, types = [], []

    def add(value, target):
        if isinstance(value, dict):
            for key in ('uuid', 'name', 'documentUuid', 'documentName'):
                add(value.get(key), target)
        elif value is not None and _text(value):
            target.append(_text(value))

    capture = dump.get('capture') or {}
    for key in ('documentUuid', 'documentName', 'docName', 'document', 'tabId'):
        add(capture.get(key), identifiers)
    for key in ('document', 'doc', 'documentName', 'documentUuid'):
        add(dump.get(key), identifiers)
    add(capture.get('documentType'), types)
    add(dump.get('documentType'), types)
    for values in (identifiers, types):
        unique = []
        for value in values:
            if _casefold(value) not in {_casefold(item) for item in unique}:
                unique.append(value)
        values[:] = unique
    return identifiers, types


def _identity_check(report, expected, dump, check_id):
    if expected is None:
        return
    if check_id == 'dump.project_identity':
        candidates = _project_candidates(dump)
        if not candidates:
            _add(report, check_id, UNMEASURED, HARD,
                 'dump carries no project identity; the supplied project cannot '
                 'be verified', 'dump',
                 {'expected': expected, 'measured': []})
            return
        if _casefold(expected) in {_casefold(item) for item in candidates}:
            _add(report, check_id, PASS, HARD,
                 'project matches the measured dump identity', 'dump',
                 {'expected': expected, 'measured': candidates})
        else:
            _add(report, check_id, FAIL, HARD,
                 'project does not match the measured dump identity', 'dump',
                 {'expected': expected, 'measured': candidates})
        return
    identifiers, types = _document_candidates(dump)
    if _casefold(expected) in {_casefold(item) for item in identifiers}:
        _add(report, check_id, PASS, HARD,
             'document matches the measured dump identity', 'dump',
             {'expected': expected, 'measured': identifiers})
    elif _casefold(expected) in {_casefold(item) for item in types}:
        _add(report, check_id, PASS, HARD,
             'document type matches the measured dump; the match is type-level '
             'only', 'dump',
             {'expected': expected, 'measured': identifiers,
              'document_type': types})
    elif identifiers:
        _add(report, check_id, FAIL, HARD,
             'document does not match the measured dump identity', 'dump',
             {'expected': expected, 'measured': identifiers})
    elif types:
        _add(report, check_id, UNMEASURED, HARD,
             'dump only carries document type %r; the supplied document %r cannot '
             'be verified' % (types, expected), 'dump',
             {'expected': expected, 'measured': [], 'document_type': types})
    else:
        _add(report, check_id, UNMEASURED, HARD,
             'dump carries no document identity; the supplied document cannot be '
             'verified', 'dump', {'expected': expected, 'measured': []})


def _constraints_for(intent, constraints_input, board):
    if constraints_input is not None:
        return constraints_input, 'constraints'
    if intent is not None:
        try:
            return compile_constraints(intent, board), 'intent.constraints'
        except (ValueError, TypeError, KeyError) as exc:
            raise InvalidInput('intent.constraints: %s' % exc) from exc
    return None, None


def _constraints_check(report, constraint_set, source):
    if constraint_set is None:
        _add(report, 'constraints.compiled', UNMEASURED, HARD,
             'no --constraints file and no --intent were supplied; constraints '
             'cannot be compiled', 'constraints')
        return
    status = _text(constraint_set.get('status'))
    conflicts = [item for item in constraint_set.get('conflicts') or []
                 if isinstance(item, dict)]
    kinds = [_text(item.get('kind')) for item in conflicts]
    blocking = sorted({kind for kind in kinds if kind not in ALLOWED_CONFLICT_KINDS})
    counts = constraint_set.get('counts') if isinstance(
        constraint_set.get('counts'), dict) else {}
    unknown = constraint_set.get('unknown') or []
    objects = {'status': status, 'conflict_kinds': kinds,
               'blocking_conflicts': blocking,
               'unknown': unknown[:20], 'counts': counts}
    if status != 'compiled' or blocking:
        _add(report, 'constraints.compiled', FAIL, HARD,
             'constraints are not compiled cleanly (status=%r, blocking conflicts=%s)'
             % (status, blocking or 'none'), source, objects)
    else:
        _add(report, 'constraints.compiled', PASS, HARD,
             'constraints compiled; only benign pose-check notes are present'
             if kinds else 'constraints compiled without conflicts',
             source, objects)


def _plan_inputs(plan, board):
    """Return (validate_plan, placements, designators)."""
    if plan is not None:
        placements = plan.get('placements') or []
        designators = [_text(item.get('designator')) for item in placements]
        return plan, placements, designators
    placements = []
    for component in board.get('components') or []:
        if not _finite(component.get('x')) or not _finite(component.get('y')):
            continue
        placements.append({
            'designator': component.get('designator'),
            'x': component.get('x'),
            'y': component.get('y'),
            'rotation': component.get('rotation') or 0,
            'layer': component.get('layer') if component.get('layer') is not None else 1,
        })
    designators = [_text(item.get('designator')) for item in placements]
    return {'placements': placements}, placements, designators


def _placement_check(report, board, validate_plan, placements, designators,
                     component_index, constraint_set, partial, plan_supplied):
    duplicates = sorted({value for value in designators
                         if designators.count(value) > 1})
    unknown = sorted({value for value in designators
                      if value and value not in component_index})
    usable = not duplicates and not unknown and (bool(placements) or not plan_supplied)
    if plan_supplied and not placements:
        usable = True  # an empty explicit plan is legal: it proposes no move.

    if not usable:
        reason = []
        if duplicates:
            reason.append('duplicate designators %s' % duplicates)
        if unknown:
            reason.append('unmeasured designators %s' % unknown)
        _add(report, 'placement.hard', UNMEASURED, HARD,
             'placement plan is not applicable: ' + '; '.join(reason),
             'plan' if plan_supplied else 'dump',
             {'duplicates': duplicates, 'unknown': unknown})
        return None
    try:
        check = validate_placement(board, validate_plan, constraint_set,
                                   partial=partial)
    except (ValueError, TypeError, KeyError) as exc:
        _add(report, 'placement.hard', UNMEASURED, HARD,
             'placement cannot be validated: %s' % exc,
             'plan' if plan_supplied else 'dump', {})
        return None
    counts = check.get('counts') or {}
    hard_ok = bool(check.get('hard_ok'))
    failed = [finding for finding in check.get('findings') or []
              if _text(finding.get('severity')) == HARD]
    hard_rows = [row for row in check.get('constraints') or []
                 if _text(row.get('severity')) == HARD and
                 _text(row.get('status')) in (FAIL, UNMEASURED)]
    if hard_ok and not counts.get('hard_failed') and not counts.get('hard_unmeasured'):
        _add(report, 'placement.hard', PASS, HARD,
             'placement satisfies every hard constraint and measured geometry check',
             'plan' if plan_supplied else 'dump',
             {'counts': counts,
              'hard_finding_codes': sorted({_text(item.get('code'))
                                            for item in failed})})
    else:
        _add(report, 'placement.hard', FAIL, HARD,
             'placement fails a hard constraint or a hard item is unmeasured',
             'plan' if plan_supplied else 'dump',
             {'counts': counts,
              'hard_finding_codes': sorted({_text(item.get('code'))
                                            for item in failed}),
              'hard_rows': [{'constraint_id': row.get('constraint_id'),
                             'status': row.get('status'),
                             'type': row.get('type')} for row in hard_rows]})
    return check


def _plan_base_hash_check(report, plan, dump, board):
    if plan is None:
        _add(report, 'plan.base_hash', SKIPPED, HARD,
             'no --plan supplied; the measured poses are used and no base hash '
             'assertion exists', 'plan')
        return
    base = plan.get('base_semantic_sha256')
    if not base:
        _add(report, 'plan.base_hash', SKIPPED, HARD,
             'plan declares no base_semantic_sha256; its freshness is not asserted',
             'plan')
        return
    current = _semantic_hash(board, dump)
    objects = {'plan': base, 'dump': current}
    if not current:
        _add(report, 'plan.base_hash', UNMEASURED, HARD,
             'dump has no semanticSha256; the plan base hash cannot be compared',
             'dump', objects)
    elif base != current:
        _add(report, 'plan.base_hash', FAIL, HARD,
             'plan was generated from a different board capture (stale base hash)',
             'plan', objects)
    else:
        _add(report, 'plan.base_hash', PASS, HARD,
             'plan base hash matches the measured dump', 'plan', objects)


def _primitive_id_check(report, plan, board, designators, plan_supplied):
    component_index = _component_map(board)
    coverage = (board.get('coverage') or {}).get('components')
    dump_ids = [_text(component.get('primitive_id'))
                for component in board.get('components') or []]
    dump_duplicates = sorted({value for value in dump_ids
                              if value and dump_ids.count(value) > 1})
    missing_measured = sorted({designator for designator, component
                               in component_index.items()
                               if not _text(component.get('primitive_id'))})

    if not plan_supplied:
        objects = {'declared': len(dump_ids), 'duplicates': dump_duplicates,
                   'missing': missing_measured}
        if dump_duplicates:
            _add(report, 'plan.primitive_ids', FAIL, HARD,
                 'the dump contains duplicate component primitiveIds',
                 'dump', objects)
        elif coverage != 'complete' or missing_measured:
            _add(report, 'plan.primitive_ids', UNMEASURED, HARD,
                 'component primitiveIds are not all measured; write identity is '
                 'not proven', 'dump', objects)
        else:
            _add(report, 'plan.primitive_ids', PASS, HARD,
                 'every measured component has a unique primitiveId', 'dump',
                 objects)
        return

    declarations = {}
    declaration_conflicts = []

    def declare(designator, primitive_id, where):
        designator = _text(designator)
        primitive_id = _text(primitive_id)
        if not designator or not primitive_id:
            return
        previous = declarations.get(designator)
        if previous and previous[0] != primitive_id:
            declaration_conflicts.append({
                'designator': designator, 'first': previous[0],
                'second': primitive_id, 'source': where,
            })
            return
        declarations[designator] = (primitive_id, where)

    for item in plan.get('placements') or []:
        declare(item.get('designator'),
                item.get('primitive_id') or item.get('primitiveId'),
                'placements')
    for designator, primitive_id in (plan.get('primitive_ids') or {}).items():
        declare(designator, primitive_id, 'primitive_ids')

    resolved, stale, missing = {}, [], []
    for designator in sorted(set(designators) | set(declarations)):
        component = component_index.get(designator)
        declared = declarations.get(designator)
        if component is None:
            stale.append({'designator': designator,
                          'expected': declared[0] if declared else None,
                          'actual': None, 'reason': 'designator not measured'})
            continue
        actual = _text(component.get('primitive_id'))
        if declared is None:
            # Old {placements} plans do not assert IDs; the apply path resolves
            # them from the fresh dump, so preflight verifies that resolution.
            if actual:
                resolved[designator] = {'primitive_id': actual, 'source': 'dump'}
            else:
                missing.append(designator)
            continue
        expected = declared[0]
        if not actual:
            missing.append(designator)
        elif actual != expected:
            stale.append({'designator': designator, 'expected': expected,
                          'actual': actual, 'reason': 'stale primitiveId'})
        else:
            resolved[designator] = {'primitive_id': actual,
                                    'source': declared[1]}
    claims = {}
    for designator, info in resolved.items():
        claims.setdefault(info['primitive_id'], []).append(designator)
    duplicated = {primitive_id: values for primitive_id, values in claims.items()
                  if len(values) > 1}
    from_dump = sorted(set(resolved) - set(declarations))
    objects = {'declared': len(declarations), 'resolved': len(resolved),
               'resolved_from_dump': from_dump, 'stale': stale,
               'missing': missing, 'duplicate_claims': duplicated,
               'declaration_conflicts': declaration_conflicts,
               'duplicate_dump_ids': dump_duplicates}
    if stale or duplicated or dump_duplicates or declaration_conflicts:
        _add(report, 'plan.primitive_ids', FAIL, HARD,
             'a placement/plan primitiveId is stale or not unique; the plan must '
             'be replanned from a fresh dump', 'plan', objects)
    elif coverage != 'complete' or missing or not resolved:
        _add(report, 'plan.primitive_ids', UNMEASURED, HARD,
             'a placement has no resolved, unique measured primitiveId', 'plan',
             objects)
    else:
        _add(report, 'plan.primitive_ids', PASS, HARD,
             'every placement resolves to a unique measured primitiveId'
             + (' (undeclared ids resolved from the dump)' if from_dump else ''),
             'plan', objects)


def _designators_check(report, board, designators, component_index, plan_supplied):
    coverage = (board.get('coverage') or {}).get('components')
    duplicates = sorted({value for value in designators
                         if designators.count(value) > 1})
    unknown = sorted({value for value in designators
                      if value and value not in component_index})
    objects = {'placements': len(designators), 'duplicates': duplicates,
               'unknown': unknown}
    if coverage != 'complete':
        _add(report, 'plan.designators_measured', UNMEASURED, HARD,
             'component coverage is incomplete; plan designators cannot be proven '
             'measured', 'plan' if plan_supplied else 'dump', objects)
    elif duplicates:
        _add(report, 'plan.designators_measured', FAIL, HARD,
             'the plan lists the same designator more than once', 'plan', objects)
    elif unknown:
        _add(report, 'plan.designators_measured', FAIL, HARD,
             'the plan references designators that are not measured on the board',
             'plan', objects)
    elif not designators:
        _add(report, 'plan.designators_measured', UNMEASURED, HARD,
             'the plan contains no placement to preflight',
             'plan' if plan_supplied else 'dump', objects)
    else:
        _add(report, 'plan.designators_measured', PASS, HARD,
             'every plan designator is measured on the board',
             'plan' if plan_supplied else 'dump', objects)


# ---------------------------------------------------------------------------
# Advisory checks


def _geometry_check(report, board):
    components = board.get('components') or []
    missing_bbox, missing_pads, duplicate_pads = [], [], []
    for component in components:
        designator = _text(component.get('designator'))
        box = component.get('bbox')
        if not (isinstance(box, list) and len(box) == 4 and all(_finite(v) for v in box)):
            missing_bbox.append(designator)
        seen = set()
        for pad in component.get('pads') or []:
            number = _text(pad.get('number'))
            if number in seen:
                duplicate_pads.append('%s.%s' % (designator, number))
            seen.add(number)
            if not _finite(pad.get('x')) or not _finite(pad.get('y')):
                missing_pads.append('%s.%s' % (designator, number))
    coverage = (board.get('coverage') or {}).get('components')
    objects = {'components': len(components), 'missing_bbox': missing_bbox,
               'missing_pad_centres': missing_pads,
               'duplicate_pad_numbers': duplicate_pads,
               'coverage': coverage}
    if not components:
        _add(report, 'dump.component_geometry', UNMEASURED, ADVISORY,
             'the dump has no component geometry to measure', 'dump', objects)
    elif missing_bbox or missing_pads:
        _add(report, 'dump.component_geometry', FAIL, ADVISORY,
             'some components/pads have no measured bbox or pad centre', 'dump',
             objects)
    elif duplicate_pads:
        _add(report, 'dump.component_geometry', UNMEASURED, ADVISORY,
             'duplicate pad numbers exist; pad-count comparison is ambiguous',
             'dump', objects)
    else:
        _add(report, 'dump.component_geometry', PASS, ADVISORY,
             'every component bbox and pad centre is measured', 'dump', objects)


def _schematic_pins(schematic):
    data = _envelope(schematic)
    components = data.get('components') or []
    result = {}
    id_to_ref = {}
    for component in components:
        if not isinstance(component, dict):
            continue
        ref = _text(component.get('designator') or component.get('ref'))
        if not ref:
            continue
        id_to_ref[component.get('id')] = ref
        pins = result.setdefault(ref, set())
        for pin in component.get('pins') or []:
            if not isinstance(pin, dict):
                continue
            number = pin.get('number', pin.get('pinNumber', pin.get('name')))
            if number is not None and _text(number):
                pins.add(_text(number))
    for connection in data.get('connections') or []:
        if not isinstance(connection, dict):
            continue
        ref = id_to_ref.get(connection.get('componentId')) or \
            _text(connection.get('designator'))
        number = connection.get('pinNumber', connection.get('pin'))
        if ref and number is not None and _text(number):
            result.setdefault(ref, set()).add(_text(number))
    return result


def _schematic_check(report, schematic, board):
    if schematic is None:
        _add(report, 'schematic.pad_counts', SKIPPED, ADVISORY,
             'no --schematic supplied; pad counts are not cross-checked', 'schematic')
        return
    pins = _schematic_pins(schematic)
    mismatches, unmatched = [], []
    for component in board.get('components') or []:
        designator = _text(component.get('designator'))
        pads = {_text(pad.get('number')) for pad in component.get('pads') or []
                if _text(pad.get('number'))}
        if designator not in pins:
            unmatched.append(designator)
            continue
        if len(pins[designator]) != len(pads):
            mismatches.append({'designator': designator,
                               'pcb_pads': len(pads),
                               'schematic_pins': len(pins[designator]),
                               'pcb_pad_numbers': sorted(pads),
                               'schematic_pin_numbers': sorted(pins[designator])})
    objects = {'mismatches': mismatches, 'unmatched_pcb_designators': unmatched,
               'schematic_designators': sorted(pins)}
    if mismatches:
        _add(report, 'schematic.pad_counts', FAIL, ADVISORY,
             'PCB pad count differs from the schematic pin count', 'schematic',
             objects)
    elif unmatched:
        _add(report, 'schematic.pad_counts', UNMEASURED, ADVISORY,
             'some PCB designators have no schematic counterpart; counts are not '
             'complete', 'schematic', objects)
    elif not pins:
        _add(report, 'schematic.pad_counts', UNMEASURED, ADVISORY,
             'the schematic read contains no components', 'schematic', objects)
    else:
        _add(report, 'schematic.pad_counts', PASS, ADVISORY,
             'PCB pad counts match the schematic pin counts', 'schematic', objects)


def _pad_identifiers(value):
    """Explicit EP pad identifiers only; never inferred from a number/name."""
    if isinstance(value, (str, int)) and not isinstance(value, bool):
        text = _text(value)
        return [text] if text else []
    if isinstance(value, list):
        return [_text(item) for item in value
                if isinstance(item, (str, int)) and _text(item)]
    return []


def _ep_check(report, intent, board):
    if intent is None:
        _add(report, 'intent.ep', UNMEASURED, ADVISORY,
             'no --intent supplied; no explicit exposed-pad declaration exists',
             'intent')
        return
    declarations = [item for item in intent.get('components') or []
                    if isinstance(item, dict) and 'ep' in item]
    if not declarations:
        _add(report, 'intent.ep', UNMEASURED, ADVISORY,
             'intent.components[].ep is not declared; EP pads are not guessed',
             'intent')
        return
    components = _component_map(board)
    failed, unmeasured, passed = [], [], []
    for item in declarations:
        designator = _text(item.get('designator'))
        flag = item.get('ep')
        if flag is False:
            passed.append({'designator': designator, 'ep': False})
            continue
        if not flag:
            continue
        component = components.get(designator)
        if component is None:
            failed.append({'designator': designator,
                           'reason': 'declared component is not measured'})
            continue
        expected = _pad_identifiers(flag) + _pad_identifiers(item.get('ep_pads')) + \
            _pad_identifiers(item.get('ep_pad'))
        expected = [value for index, value in enumerate(expected)
                    if value and value not in expected[:index]]
        if not expected:
            unmeasured.append({'designator': designator,
                               'reason': 'ep=true without an explicit ep_pad/ep_pads'})
            continue
        pads = _pad_index(component)
        missing = [number for number in expected if number not in pads]
        if missing:
            failed.append({'designator': designator, 'missing_pads': missing,
                           'declared_pads': expected,
                           'measured_pads': sorted(pads)})
        else:
            passed.append({'designator': designator, 'pads': expected})
    objects = {'passed': passed, 'failed': failed, 'unmeasured': unmeasured}
    if failed:
        _add(report, 'intent.ep', FAIL, ADVISORY,
             'a declared exposed/thermal pad is absent from the measured dump',
             'intent', objects)
    elif unmeasured:
        _add(report, 'intent.ep', UNMEASURED, ADVISORY,
             'an EP declaration has no explicit pad identifier; it is not guessed',
             'intent', objects)
    else:
        _add(report, 'intent.ep', PASS, ADVISORY,
             'every declared exposed/thermal pad exists in the measured dump',
             'intent', objects)


def _constraint_rows_by_type(placement_check, types):
    rows = []
    for row in (placement_check or {}).get('constraints') or []:
        if _text(row.get('type')) in types:
            rows.append(row)
    return rows


def _placement_constraints_check(report, placement_check, constraint_set):
    if constraint_set is None:
        _add(report, 'placement.constraints', UNMEASURED, ADVISORY,
             'no compiled constraints exist; fixed/edge/near_pin/keepout were not '
             'evaluated', 'constraints')
        return
    rows = _constraint_rows_by_type(placement_check,
                                    {'fixed', 'edge', 'near_pin', 'keepout'})
    if not rows:
        _add(report, 'placement.constraints', UNMEASURED, ADVISORY,
             'no fixed/edge/near_pin/keepout constraint rows were evaluated',
             'constraints')
        return
    failed = [row for row in rows if _text(row.get('status')) == FAIL]
    unmeasured = [row for row in rows if _text(row.get('status')) == UNMEASURED]
    objects = {
        'rows': len(rows),
        'failed': [{'constraint_id': row.get('constraint_id'),
                    'type': row.get('type'),
                    'severity': row.get('severity')} for row in failed],
        'unmeasured': [{'constraint_id': row.get('constraint_id'),
                        'type': row.get('type'),
                        'severity': row.get('severity')} for row in unmeasured],
    }
    if failed:
        _add(report, 'placement.constraints', FAIL, ADVISORY,
             'a fixed/edge/near_pin/keepout constraint failed', 'constraints',
             objects)
    elif unmeasured:
        _add(report, 'placement.constraints', UNMEASURED, ADVISORY,
             'a fixed/edge/near_pin/keepout constraint is unmeasured',
             'constraints', objects)
    else:
        _add(report, 'placement.constraints', PASS, ADVISORY,
             'fixed/edge/near_pin/keepout constraints all pass', 'constraints',
             objects)


def _preferred_check(report, placement_check, constraint_set):
    preferred = [item for item in (constraint_set or {}).get('constraints') or []
                 if _text(item.get('severity')) == 'preferred']
    if constraint_set is None or not preferred:
        _add(report, 'placement.preferred', SKIPPED, ADVISORY,
             'no preferred constraints are declared', 'constraints')
        return
    if placement_check is None:
        _add(report, 'placement.preferred', UNMEASURED, ADVISORY,
             'placement validation did not run; preferred constraints cannot be '
             'evaluated', 'constraints')
        return
    preferred_ids = {_text(item.get('id')) for item in preferred}
    findings = [finding for finding in (placement_check or {}).get('findings') or []
                if _text(finding.get('severity')) == 'preferred']
    rows = [row for row in (placement_check or {}).get('constraints') or []
            if _text(row.get('severity')) == 'preferred' and
            _text(row.get('status')) in (FAIL, UNMEASURED)]
    objects = {
        'preferred_constraints': sorted(preferred_ids),
        'finding_codes': sorted({_text(item.get('code')) for item in findings}),
        'rows': [{'constraint_id': row.get('constraint_id'),
                  'status': row.get('status'),
                  'type': row.get('type')} for row in rows],
    }
    if findings or rows:
        _add(report, 'placement.preferred', FAIL, ADVISORY,
             'a preferred constraint is not satisfied; this is advisory and never '
             'blocks', 'constraints', objects)
    else:
        _add(report, 'placement.preferred', PASS, ADVISORY,
             'all declared preferred constraints are satisfied', 'constraints',
             objects)


def _near_pin_check(report, constraint_set, board):
    constraints = [item for item in (constraint_set or {}).get('constraints') or []
                   if item.get('type') == 'near_pin' and
                   _text(item.get('role')) in NEAR_PIN_ROLES]
    if not constraints:
        _add(report, 'near_pin.decap_feedback', UNMEASURED, ADVISORY,
             'no near_pin constraint with role decap/feedback is declared',
             'constraints')
        return
    components = _component_map(board)
    rows = []
    failures = []
    for item in constraints:
        constraint_id = _text(item.get('id'))
        part = _text(item.get('part'))
        owner = _text(item.get('owner'))
        part_pad_number = _text(item.get('pad'))
        owner_pad_number = _text(item.get('owner_pad'))
        part_component = components.get(part)
        owner_component = components.get(owner)
        part_pad = _pad_index(part_component).get(part_pad_number) \
            if part_component else None
        owner_pad = _pad_index(owner_component).get(owner_pad_number) \
            if owner_component else None
        row = {'constraint_id': constraint_id,
               'part': '%s.%s' % (part, part_pad_number),
               'owner': '%s.%s' % (owner, owner_pad_number),
               'role': _text(item.get('role'))}
        reasons = []
        if part_component is None:
            reasons.append('part designator is not measured')
        elif part_pad is None:
            reasons.append('part pad is absent from the dump')
        if owner_component is None:
            reasons.append('owner designator is not measured')
        elif owner_pad is None:
            reasons.append('owner pad is absent from the dump')
        if part_pad is not None and owner_pad is not None:
            part_net = part_pad.get('net') or None
            owner_net = owner_pad.get('net') or None
            row['part_net'] = part_net
            row['owner_net'] = owner_net
            if not part_net or not owner_net:
                reasons.append('a pad has no measured net')
            elif part_net != owner_net:
                reasons.append('pad nets differ')
        row['status'] = 'fail' if reasons else 'pass'
        if reasons:
            row['reasons'] = reasons
            failures.append(row)
        rows.append(row)
    objects = {'rows': rows,
               'note': 'pad-centre relation only; copper path is not proven here'}
    if failures:
        _add(report, 'near_pin.decap_feedback', FAIL, ADVISORY,
             'a decap/feedback near_pin relation cannot be resolved with equal '
             'pad nets on the measured dump', 'constraints', objects)
    else:
        _add(report, 'near_pin.decap_feedback', PASS, ADVISORY,
             'every decap/feedback near_pin pair has both pads measured on the '
             'same net', 'constraints', objects)


def _region_from_value(value):
    """Return ``(rect, circle)`` for an explicit keepout declaration."""
    if isinstance(value, list):
        box = _box_from_value(value)
        return (box, None) if box else (None, None)
    if not isinstance(value, dict):
        return None, None
    for key in ('rect', 'bbox', 'region'):
        if key in value:
            box = _box_from_value(value[key])
            if box:
                return box, None
    center = value.get('center')
    radius = value.get('radius')
    if (isinstance(center, list) and len(center) == 2 and
            all(_finite(item) for item in center) and _finite(radius) and radius > 0):
        return [float(center[0]) - float(radius), float(center[1]) - float(radius),
                float(center[0]) + float(radius), float(center[1]) + float(radius)], \
            (float(center[0]), float(center[1]), float(radius))
    return None, None


def _point_in_region(point, rect, circle):
    if circle:
        return math.hypot(point[0] - circle[0], point[1] - circle[1]) <= circle[2]
    return _point_in_box(point, rect)


def _copper_hits(region_rect, region_circle, board, *, exclude_designator=None,
                 layers=None, include_lines=True):
    """Measured copper pads/vias/lines that touch the declared region."""
    hits = []
    for component in board.get('components') or []:
        designator = _text(component.get('designator'))
        if exclude_designator and designator == exclude_designator:
            continue
        for pad in component.get('pads') or []:
            if layers and pad.get('layer') not in layers and pad.get('layer') != 12:
                continue
            if _finite(pad.get('x')) and _finite(pad.get('y')) and \
                    _point_in_region((pad.get('x'), pad.get('y')),
                                     region_rect, region_circle):
                hits.append({'kind': 'pad',
                             'object': '%s.%s' % (designator, pad.get('number')),
                             'net': pad.get('net')})
    copper = board.get('copper') or {}
    for via in copper.get('vias') or []:
        if _finite(via.get('x')) and _finite(via.get('y')) and \
                _point_in_region((via.get('x'), via.get('y')),
                                 region_rect, region_circle):
            hits.append({'kind': 'via', 'object': _text(via.get('primitiveId')),
                         'net': via.get('net')})
    if include_lines:
        for line in copper.get('lines') or []:
            if layers and line.get('layer') not in layers and \
                    line.get('layer') != 12:
                continue
            points = [line.get('startX'), line.get('startY'),
                      line.get('endX'), line.get('endY')]
            if not all(_finite(item) for item in points):
                continue
            if _segment_intersects_box((points[0], points[1]),
                                       (points[2], points[3]), region_rect):
                hits.append({'kind': 'track',
                             'object': _text(line.get('primitiveId')),
                             'net': line.get('net')})
    return hits


def _pour_caveat(board, layers):
    copper = board.get('copper') or {}
    for pour in copper.get('pours') or []:
        if layers and pour.get('layer') not in layers:
            continue
        return ('pour boundary %s on layer %s has no fill geometry in the dump; '
                'copper under the declared region cannot be proven absent'
                % (_text(pour.get('primitiveId')), pour.get('layer')))
    return None


def _connectors_check(report, intent, board):
    if intent is None:
        _add(report, 'intent.connectors', UNMEASURED, ADVISORY,
             'no --intent supplied; connector opening declarations are absent',
             'intent')
        return
    entries = intent.get('connectors')
    if entries is None:
        _add(report, 'intent.connectors', UNMEASURED, ADVISORY,
             'intent.connectors is not declared; openings are not guessed',
             'intent')
        return
    if not entries:
        _add(report, 'intent.connectors', PASS, ADVISORY,
             'intent declares no connectors', 'intent', {'declared': 0})
        return
    components = _component_map(board)
    outline = (board.get('outline') or {}).get('bbox')
    failures, unmeasured, passed = [], [], []
    for entry in entries:
        if not isinstance(entry, dict):
            failures.append({'reason': 'connector entry is not an object'})
            continue
        designator = _text(entry.get('designator'))
        opening = entry.get('opening')
        if not designator:
            failures.append({'reason': 'connector entry has no designator'})
            continue
        component = components.get(designator)
        if component is None:
            failures.append({'designator': designator,
                             'reason': 'designator is not measured'})
            continue
        if opening is False:
            passed.append({'designator': designator, 'opening': False})
            continue
        if not isinstance(opening, dict):
            unmeasured.append({'designator': designator,
                               'reason': 'opening has no measurable declaration'})
            continue
        box = component.get('bbox')
        checks, problems = [], []
        edge = opening.get('edge')
        limit = opening.get('max_inset_mil', opening.get('max_inset'))
        if edge is not None:
            edge = _text(edge)
            if edge not in EDGES:
                problems.append('unsupported edge %r' % edge)
            elif not (isinstance(box, list) and len(box) == 4):
                problems.append('component bbox is not measured')
            elif not _finite(limit):
                problems.append('edge declared without a finite max_inset_mil')
            else:
                distance = _box_edge_distance(box, edge, outline)
                checks.append({'condition': 'edge', 'edge': edge,
                               'distance_mil': distance,
                               'max_inset_mil': float(limit),
                               'status': PASS if distance <= float(limit) else FAIL})
        if 'facing_rotation' in opening:
            expected = opening.get('facing_rotation')
            if not _finite(expected):
                problems.append('facing_rotation is not finite')
            else:
                ok = _rotation_matches(component.get('rotation'), expected)
                checks.append({'condition': 'facing_rotation',
                               'actual': component.get('rotation'),
                               'expected': float(expected),
                               'status': PASS if ok else FAIL})
        failed_checks = [item for item in checks if item['status'] == FAIL]
        if problems or failed_checks:
            failures.append({'designator': designator, 'checks': checks,
                             'problems': problems})
        elif not checks:
            unmeasured.append({'designator': designator,
                               'reason': 'opening is declared without edge/'
                                         'facing_rotation evidence'})
        else:
            passed.append({'designator': designator, 'checks': checks})
    objects = {'passed': passed, 'failed': failures, 'unmeasured': unmeasured}
    if failures:
        _add(report, 'intent.connectors', FAIL, ADVISORY,
             'a connector opening declaration is not satisfied by the measured '
             'geometry', 'intent', objects)
    elif unmeasured:
        _add(report, 'intent.connectors', UNMEASURED, ADVISORY,
             'a connector opening declaration has no measurable condition',
             'intent', objects)
    else:
        _add(report, 'intent.connectors', PASS, ADVISORY,
             'declared connector openings match the measured geometry',
             'intent', objects)


def _rf_check(report, intent, board, copper_complete):
    if intent is None:
        _add(report, 'intent.rf', UNMEASURED, ADVISORY,
             'no --intent supplied; antenna keepouts are absent', 'intent')
        return
    entries = intent.get('rf')
    if entries is None:
        _add(report, 'intent.rf', UNMEASURED, ADVISORY,
             'intent.rf is not declared; antenna keepouts are not guessed',
             'intent')
        return
    if not entries:
        _add(report, 'intent.rf', PASS, ADVISORY,
             'intent declares no RF modules', 'intent', {'declared': 0})
        return
    components = _component_map(board)
    outline = (board.get('outline') or {}).get('bbox')
    failures, unmeasured, passed = [], [], []
    for entry in entries:
        if not isinstance(entry, dict):
            failures.append({'reason': 'rf entry is not an object'})
            continue
        designator = _text(entry.get('designator'))
        keepout = entry.get('antenna_keepout')
        if not designator:
            failures.append({'reason': 'rf entry has no designator'})
            continue
        if designator not in components:
            failures.append({'designator': designator,
                             'reason': 'designator is not measured'})
            continue
        rect, circle = _region_from_value(keepout)
        if rect is None:
            unmeasured.append({'designator': designator,
                               'reason': 'antenna_keepout has no explicit '
                                         'rect/bbox/center+radius'})
            continue
        if not outline:
            unmeasured.append({'designator': designator,
                               'reason': 'board outline is not measured'})
            continue
        if not _contains_box(outline, rect):
            failures.append({'designator': designator,
                             'reason': 'antenna keepout extends outside the board',
                             'region': rect, 'outline': outline})
            continue
        if not copper_complete:
            unmeasured.append({'designator': designator,
                               'reason': 'copper coverage is incomplete'})
            continue
        hits = _copper_hits(rect, circle, board, exclude_designator=designator)
        caveat = _pour_caveat(board, None)
        if hits:
            failures.append({'designator': designator,
                             'reason': 'copper intersects the antenna keepout',
                             'hits': hits, 'region': rect})
        elif caveat:
            unmeasured.append({'designator': designator, 'reason': caveat})
        else:
            passed.append({'designator': designator, 'region': rect})
    objects = {'passed': passed, 'failed': failures, 'unmeasured': unmeasured}
    if failures:
        _add(report, 'intent.rf', FAIL, ADVISORY,
             'a declared antenna keepout is violated by measured geometry',
             'intent', objects)
    elif unmeasured:
        _add(report, 'intent.rf', UNMEASURED, ADVISORY,
             'an antenna keepout is not fully measurable from the dump',
             'intent', objects)
    else:
        _add(report, 'intent.rf', PASS, ADVISORY,
             'declared antenna keepouts contain no measured copper', 'intent',
             objects)


def _sensors_check(report, intent, board, copper_complete):
    if intent is None:
        _add(report, 'intent.sensors', UNMEASURED, ADVISORY,
             'no --intent supplied; sensor copper voids are absent', 'intent')
        return
    entries = intent.get('sensors')
    if entries is None:
        _add(report, 'intent.sensors', UNMEASURED, ADVISORY,
             'intent.sensors is not declared; no-copper-under is not guessed',
             'intent')
        return
    if not entries:
        _add(report, 'intent.sensors', PASS, ADVISORY,
             'intent declares no sensors', 'intent', {'declared': 0})
        return
    components = _component_map(board)
    failures, unmeasured, passed = [], [], []
    for entry in entries:
        if not isinstance(entry, dict):
            failures.append({'reason': 'sensor entry is not an object'})
            continue
        designator = _text(entry.get('designator'))
        spec = entry.get('no_copper_under')
        if not designator:
            failures.append({'reason': 'sensor entry has no designator'})
            continue
        component = components.get(designator)
        if component is None:
            failures.append({'designator': designator,
                             'reason': 'designator is not measured'})
            continue
        if spec is False:
            passed.append({'designator': designator, 'no_copper_under': False})
            continue
        box = component.get('bbox')
        if not (isinstance(box, list) and len(box) == 4):
            unmeasured.append({'designator': designator,
                               'reason': 'component bbox is not measured'})
            continue
        margin = 0.0
        layers = None
        if isinstance(spec, dict):
            if 'layer' in spec:
                try:
                    layers = [int(spec['layer'])]
                except (TypeError, ValueError):
                    failures.append({'designator': designator,
                                     'reason': 'no_copper_under.layer is not an '
                                               'integer'})
                    continue
            if 'margin_mil' in spec:
                if not _finite(spec['margin_mil']) or spec['margin_mil'] < 0:
                    failures.append({'designator': designator,
                                     'reason': 'no_copper_under.margin_mil must be '
                                               'a nonnegative number'})
                    continue
                margin = float(spec['margin_mil'])
        elif spec is not True:
            unmeasured.append({'designator': designator,
                               'reason': 'no_copper_under has no explicit '
                                         'layer/margin declaration'})
            continue
        if not copper_complete:
            unmeasured.append({'designator': designator,
                               'reason': 'copper coverage is incomplete'})
            continue
        region = [box[0] - margin, box[1] - margin,
                  box[2] + margin, box[3] + margin]
        hits = _copper_hits(region, None, board, exclude_designator=designator,
                            layers=layers)
        caveat = _pour_caveat(board, layers)
        if hits:
            failures.append({'designator': designator,
                             'reason': 'measured copper lies under the sensor',
                             'hits': hits, 'region': region,
                             'layers': layers or [1, 2]})
        elif caveat:
            unmeasured.append({'designator': designator, 'reason': caveat})
        else:
            passed.append({'designator': designator, 'region': region,
                           'layers': layers or [1, 2]})
    objects = {'passed': passed, 'failed': failures, 'unmeasured': unmeasured}
    if failures:
        _add(report, 'intent.sensors', FAIL, ADVISORY,
             'measured copper lies under a declared sensor', 'intent', objects)
    elif unmeasured:
        _add(report, 'intent.sensors', UNMEASURED, ADVISORY,
             'a sensor copper void is not fully measurable from the dump',
             'intent', objects)
    else:
        _add(report, 'intent.sensors', PASS, ADVISORY,
             'no measured copper lies under the declared sensors', 'intent',
             objects)


def _fabrication_check(report, board, moved_component_ids=None):
    coverage = board.get('coverage') or {}
    silk_ok = coverage.get('silk') == 'complete'
    copper_ok = coverage.get('copper') == 'complete'
    if not silk_ok or not copper_ok:
        _add(report, 'fabrication.audit', UNMEASURED, ADVISORY,
             'silk/copper coverage is incomplete; the fabrication audit cannot be '
             'complete', 'dump',
             {'silk_coverage': coverage.get('silk'),
              'copper_coverage': coverage.get('copper')})
        return
    try:
        audit = audit_fabrication(board)
    except (ValueError, TypeError, KeyError) as exc:
        raise InvalidInput('dump: fabrication audit failed: %s' % exc) from exc
    findings = audit.get('findings') or []
    skipped = []
    moved = {str(value) for value in (moved_component_ids or []) if value}
    if moved:
        # The dump's silk rows still sit at the PRE-move pose.  A planned move
        # cannot prove the post-write silk position without a fresh dump, so
        # those silk findings are not evidence against the candidate — they are
        # reported as skipped, not silently passed.
        moved_silk_ids = {
            str(item.get('ID')) for item in board.get('silk') or []
            if str(item.get('CompID')) in moved
        }
        kept = []
        for item in findings:
            objects = {str(value) for value in item.get('objects') or []}
            if objects & moved_silk_ids:
                skipped.append('moved-part silk: %s' % item.get('code'))
                continue
            kept.append(item)
        findings = kept
    hard = [item for item in findings if _text(item.get('severity')) == HARD]
    preferred = [item for item in findings
                 if _text(item.get('severity')) != HARD]
    objects = {
        'status': audit.get('status'),
        'counts': audit.get('counts'),
        'hard_findings': [{'code': item.get('code'),
                           'objects': item.get('objects')} for item in hard],
        'preferred_findings': [{'code': item.get('code'),
                                'objects': item.get('objects')}
                               for item in preferred],
    }
    if hard:
        _add(report, 'fabrication.audit', FAIL, ADVISORY,
             'fabrication audit found hard silk/pour/via issues', 'dump', objects)
    elif preferred:
        _add(report, 'fabrication.audit', FAIL, ADVISORY,
             'fabrication audit found advisory-only issues; this causes review, '
             'not a block', 'dump', objects)
    else:
        _add(report, 'fabrication.audit', PASS, ADVISORY,
             'no measured silk/pour/via fabrication issue was found', 'dump',
             objects)
    if skipped:
        objects['skipped_for_moved_parts'] = sorted(set(skipped))
        report['not_checked'].append(
            'post-move silk for %d component(s) requires a fresh dump'
            % len(moved))
    report['notes'].append(
        'fabrication audit covers only measured silk bboxes, pour fills and via '
        'rows; it is not manufacturing approval')


def _power_check(report, intent, board):
    if intent is None:
        _add(report, 'power.audit', UNMEASURED, ADVISORY,
             'no --intent supplied; power nets/currents are not declared',
             'intent')
        return
    power_nets = intent.get('power_nets')
    if power_nets is None:
        _add(report, 'power.audit', UNMEASURED, ADVISORY,
             'intent.power_nets is not declared; no power width or pour claim is '
             'checked', 'intent')
        return
    if (board.get('coverage') or {}).get('copper') != 'complete':
        _add(report, 'power.audit', UNMEASURED, ADVISORY,
             'copper coverage is incomplete; power widths and pours cannot be '
             'measured', 'dump')
        return
    try:
        audit = audit_power(board, intent)
    except (ValueError, TypeError, KeyError) as exc:
        raise InvalidInput('intent.power_nets: %s' % exc) from exc
    failed = audit.get('failed') or []
    unmeasured = audit.get('unmeasured') or []
    objects = {'status': audit.get('status'),
               'failed': [{'net': item.get('net'), 'reason': item.get('reason')}
                          for item in failed],
               'unmeasured': [{'net': item.get('net'),
                               'reason': item.get('reason')}
                              for item in unmeasured],
               'nets': [{'net': item.get('net'), 'status': item.get('status')}
                        for item in audit.get('nets') or []]}
    if audit.get('status') != PASS:
        _add(report, 'power.audit', FAIL, ADVISORY,
             'power audit is not pass (status=%r); this causes review'
             % audit.get('status'), 'intent', objects)
    else:
        _add(report, 'power.audit', PASS, ADVISORY,
             'declared power widths/pours pass the IPC-2221 screening check',
             'intent', objects)


def _modules_check(report, intent, board):
    if intent is None or intent.get('modules') is None:
        _add(report, 'intent.modules', SKIPPED, ADVISORY,
             'no intent.modules section; no template binding was declared',
             'intent')
        return
    modules = intent.get('modules')
    if not modules:
        _add(report, 'intent.modules', PASS, ADVISORY,
             'intent declares no module templates', 'intent', {'declared': 0})
        return
    try:
        templates = load_templates()
    except (OSError, ValueError, TypeError) as exc:
        _add(report, 'intent.modules', UNMEASURED, ADVISORY,
             'placement templates could not be loaded: %s' % exc, 'intent')
        return
    by_id = {template.get('id'): template
             for template in templates.get('templates') or []
             if isinstance(template, dict)}
    rejected, bound = [], []
    for module in modules:
        if not isinstance(module, dict):
            rejected.append({'module': None, 'reasons': ['module is not an object']})
            continue
        module_id = _text(module.get('id')) or '<unnamed>'
        template_id = _text(module.get('template'))
        template = by_id.get(template_id)
        if template is None:
            rejected.append({'module': module_id, 'template': template_id,
                             'reasons': ['unknown template %r' % template_id]})
            continue
        try:
            result = bind_template(template, module.get('roles') or {}, board)
        except (ValueError, TypeError, KeyError) as exc:
            raise InvalidInput('intent.modules[%s]: %s' % (module_id, exc)) from exc
        entry = {'module': module_id, 'template': template_id,
                 'status': result.get('status'),
                 'reasons': result.get('reasons') or []}
        if result.get('status') == 'bound':
            bound.append(entry)
        else:
            rejected.append(entry)
    objects = {'bound': bound, 'rejected': rejected}
    if rejected:
        _add(report, 'intent.modules', FAIL, ADVISORY,
             'a declared module template binding is rejected (conditions or pin '
             'nets do not match the measured board)', 'intent', objects)
    else:
        _add(report, 'intent.modules', PASS, ADVISORY,
             'every declared module template binds to measured parts and nets',
             'intent', objects)


def _identity_file_check(report, identity):
    if identity is None:
        _add(report, 'identity.check', UNMEASURED, ADVISORY,
             'no --identity supplied; component identity is not verified',
             'identity')
        return
    data = _envelope(identity)
    status = _text(data.get('status'))
    counts = data.get('counts') if isinstance(data.get('counts'), dict) else {}
    blocking = data.get('blocking_findings') or []
    objects = {'status': status, 'counts': counts,
               'blocking_codes': sorted({_text(item.get('code'))
                                         for item in blocking
                                         if isinstance(item, dict)})}
    if status == 'pass':
        _add(report, 'identity.check', PASS, ADVISORY,
             'component identity check passed', 'identity', objects)
    else:
        _add(report, 'identity.check', FAIL, ADVISORY,
             'component identity status is %r (a full PCB-bound pass is required)'
             % status, 'identity', objects)


# ---------------------------------------------------------------------------
# Top-level preflight


def _validate_all(intent, constraints_input, schematic, identity, plan):
    _validate_intent_shape(intent)
    _validate_constraints_shape(constraints_input)
    _validate_schematic_shape(schematic)
    _validate_identity_shape(identity)
    if plan is not None:
        _validate_plan_shape(plan)


def preflight(args):
    """Build the preflight report for parsed CLI ``args``."""
    dump = _load_object(args.dump, 'dump')
    intent = _load_object(args.intent, 'intent') if args.intent else None
    constraints_input = _load_object(args.constraints, 'constraints') \
        if args.constraints else None
    schematic = _envelope(_load_object(args.schematic, 'schematic')) \
        if args.schematic else None
    identity = _envelope(_load_object(args.identity, 'identity')) \
        if args.identity else None
    plan = _load_plan(args.plan) if args.plan else None
    _validate_all(intent, constraints_input, schematic, identity, plan)

    try:
        board = normalize_board(dump)
    except (ValueError, TypeError, KeyError) as exc:
        raise InvalidInput('dump: %s' % exc) from exc

    plan_supplied = plan is not None
    report = _new_report(board, dump, plan, plan_supplied)
    if not plan_supplied:
        report['notes'].append('no --plan supplied: measured component poses are '
                               'validated as the placement')
    if identity is not None:
        report['notes'].append('identity evidence: component_identity_check.py '
                               'output')

    _coverage_checks(report, board)
    _identity_check(report, args.project, dump, 'dump.project_identity')
    _identity_check(report, args.doc, dump, 'dump.document_identity')

    constraint_set, constraints_source = _constraints_for(
        intent, constraints_input, board)
    _constraints_check(report, constraint_set, constraints_source)

    validate_plan, placements, designators = _plan_inputs(plan, board)
    component_index = _component_map(board)
    placement_check = _placement_check(
        report, board, validate_plan, placements, designators, component_index,
        constraint_set, bool(args.partial), plan_supplied)
    _plan_base_hash_check(report, plan, dump, board)
    _primitive_id_check(report, plan, board, designators, plan_supplied)
    _designators_check(report, board, designators, component_index, plan_supplied)

    # A plan is the board we are about to write.  Fabrication, keepout, connector
    # and near-pin checks must see the candidate poses, not the pre-import pose
    # of a newly added part (which legitimately sits outside the board until the
    # placement batch runs).
    try:
        audit_board = apply_placements(board, placements) if placements else board
    except (ValueError, TypeError, KeyError) as exc:
        _add(report, 'plan.candidate_board', UNMEASURED, HARD,
             'cannot build the candidate board from the plan: %s' % exc, 'plan')
        audit_board = board
    moved_component_ids = []
    for item in placements:
        component = component_index.get(_text(item.get('designator')))
        if component is None:
            continue
        try:
            target = (float(item.get('x')), float(item.get('y')),
                      float(item.get('rotation', component.get('rotation')) or 0) % 360,
                      int(item.get('layer', component.get('layer'))))
            measured = (float(component.get('x')), float(component.get('y')),
                        float(component.get('rotation') or 0) % 360,
                        int(component.get('layer')))
        except (TypeError, ValueError):
            moved_component_ids.append(component.get('primitive_id'))
            continue
        if target != measured:
            moved_component_ids.append(component.get('primitive_id'))

    _geometry_check(report, audit_board)
    _schematic_check(report, schematic, audit_board)
    _ep_check(report, intent, audit_board)
    _placement_constraints_check(report, placement_check, constraint_set)
    _preferred_check(report, placement_check, constraint_set)
    _near_pin_check(report, constraint_set, audit_board)
    _connectors_check(report, intent, audit_board)
    copper_complete = (audit_board.get('coverage') or {}).get('copper') == 'complete'
    _rf_check(report, intent, audit_board, copper_complete)
    _sensors_check(report, intent, audit_board, copper_complete)
    _fabrication_check(report, audit_board, moved_component_ids)
    _power_check(report, intent, audit_board)
    _modules_check(report, intent, audit_board)
    _identity_file_check(report, identity)
    return _finish(report)


def _invalid_report(message):
    return {
        'schema': SCHEMA,
        'status': 'invalid_input',
        'checks': [],
        'counts': {'pass': 0, 'fail': 0, 'unmeasured': 0,
                   'hard_fail': 0, 'hard_unmeasured': 0},
        'board': {},
        'notes': [message],
        'not_checked': [],
        'error': message,
    }


def _render_human(report):
    lines = ['pcb preflight: %s' % report['status']]
    counts = report['counts']
    lines.append('checks: %d pass, %d fail, %d unmeasured, %d hard fail, '
                 '%d hard unmeasured' % (
                     counts['pass'], counts['fail'], counts['unmeasured'],
                     counts['hard_fail'], counts['hard_unmeasured']))
    for check in report['checks']:
        if check['status'] == PASS:
            continue
        lines.append('  [%s/%s] %s: %s' % (
            check['status'], check['severity'], check['id'], check['message']))
    return '\n'.join(lines)


def _emit(report, args):
    if args.out:
        write_json(args.out, report)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    else:
        print(_render_human(report))


def _emit_or_fail(report, args):
    """Emit the report; a write/encoding failure becomes invalid_input."""
    try:
        _emit(report, args)
        return True
    except (OSError, TypeError, ValueError) as exc:
        fallback = _invalid_report('cannot emit report: %s' % exc)
        print(json.dumps(fallback, ensure_ascii=False, allow_nan=False))
        return False


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Offline PCB preflight over a measured dump',
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--dump', required=True,
                        help='measured pcb dump JSON (required)')
    parser.add_argument('--schematic',
                        help='sch read/connectivity JSON for pad-count comparison')
    parser.add_argument('--intent', help='pcb-intent JSON')
    parser.add_argument('--constraints',
                        help='compiled pcb-constraints JSON (else compiled from intent)')
    parser.add_argument('--plan',
                        help='placement plan JSON ({"placements": [...]})')
    parser.add_argument('--identity',
                        help='component_identity_check.py output JSON')
    parser.add_argument('--project', help='expected project name/uuid')
    parser.add_argument('--doc', help='expected document name/uuid/type')
    parser.add_argument('--partial', action='store_true',
                        help='validate only the designators listed in the plan')
    parser.add_argument('--out', help='write the preflight report JSON here')
    parser.add_argument('--json', action='store_true',
                        help='print the report JSON instead of a summary')
    args = parser.parse_args(argv)
    try:
        report = preflight(args)
    except InvalidInput as exc:
        report = _invalid_report(str(exc))
        if not _emit_or_fail(report, args):
            return 2
        return 2
    except (ValueError, TypeError, KeyError, AttributeError, IndexError) as exc:
        # A malformed input must be invalid_input/2, never a traceback.
        report = _invalid_report('%s: %s' % (type(exc).__name__, exc))
        if not _emit_or_fail(report, args):
            return 2
        return 2
    if not _emit_or_fail(report, args):
        return 2
    return EXIT_CODES.get(report['status'], 2)


if __name__ == '__main__':
    sys.exit(main())
