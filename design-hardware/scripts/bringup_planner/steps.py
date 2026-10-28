"""Structured step construction shared by every capability generator.

A step is a *human* instruction.  The planner never executes it, never opens an
instrument and never presses reset.  Machine fields exist so a result evaluator
can check whether the recorded evidence is complete and consistent.
"""
from __future__ import annotations

from .util import is_number

GROUP_ORDER = {'I1': 0, 'I2': 1, 'I3': 2, 'I4': 3}

STATUS_READY = 'ready'
STATUS_BLOCKED = 'blocked'
STATUS_UNSUPPORTED = 'unsupported'
STATUS_ADVISORY = 'advisory'

STATUSES = (STATUS_READY, STATUS_BLOCKED, STATUS_UNSUPPORTED, STATUS_ADVISORY)

MEASURE_QUANTITIES = ('voltage', 'current', 'resistance', 'frequency', 'time',
                      'temperature', 'power', 'logic_level')
CRITERION_STATUSES = ('defined', 'undefined', 'needs_interpretation',
                      'qualitative')
EVIDENCE_KINDS = ('photo', 'video', 'meter_reading', 'scope_capture',
                  'supply_reading', 'serial_log', 'host_log', 'visual_check',
                  'inspection_note', 'datasheet_reference')


def prerequisite_step(step_id, reason=None):
    return {'kind': 'step', 'step_id': step_id, 'reason': reason}


def prerequisite_condition(text, source_ref=None):
    return {'kind': 'condition', 'text': text, 'source_ref': source_ref}


def stop_condition(code, description, *, threshold=None, quantity=None,
                   unit=None, source_ref=None, action=(
                       'stop the test, disconnect the supply and keep the '
                       'board de-energised')):
    item = {'code': code, 'description': description,
            'action': action, 'source_ref': source_ref}
    if threshold is not None:
        item['threshold'] = {'value': threshold, 'quantity': quantity,
                             'unit': unit}
    else:
        item['threshold'] = None
    return item


def equipment_item(equipment_id, capability, *, settings=None,
                   verified=True, detail=None):
    return {'equipment_id': equipment_id, 'capability': capability,
            'settings': settings or {}, 'verified': bool(verified),
            'detail': detail}


def evidence_item(kind, description, *, verifiable=True):
    return {'kind': kind, 'description': description,
            'verifiable': bool(verifiable), 'synthetic_forbidden': True}


def make_step(*, step_id, group, title, purpose, prerequisites=(),
              equipment=(), wiring=None, procedure=(), measurement=None,
              expected_behavior=None, stop_conditions=(), failure_branches=(),
              required_evidence=(), status=STATUS_READY, blocked_reason=None,
              missing_information=(), required=True, source_refs=(),
              notes=None, safety=None):
    if group not in GROUP_ORDER:
        raise ValueError('unknown group %r' % group)
    if status not in STATUSES:
        raise ValueError('unknown status %r' % status)
    if measurement is not None:
        quantity = measurement.get('quantity')
        if quantity not in MEASURE_QUANTITIES:
            raise ValueError('unknown measurement quantity %r' % quantity)
        criterion = measurement.get('criterion_status')
        if criterion not in CRITERION_STATUSES:
            raise ValueError('unknown criterion_status %r' % criterion)
        if measurement.get('range') is not None:
            lower = measurement['range'].get('min')
            upper = measurement['range'].get('max')
            for value in (lower, upper):
                if value is not None and not is_number(value):
                    raise ValueError('measurement range must be numeric')
            if lower is not None and upper is not None and lower > upper:
                raise ValueError('measurement range is inverted')
    return {
        'step_id': step_id,
        'group': group,
        'title': title,
        'purpose': purpose,
        'status': status,
        'blocked_reason': blocked_reason,
        'missing_information': list(missing_information),
        'required': bool(required),
        'execution': 'manual_only',
        'auto_execute': False,
        'prerequisites': list(prerequisites),
        'equipment': list(equipment),
        'wiring': wiring or {},
        'procedure': list(procedure),
        'measurement': measurement,
        'expected_behavior': expected_behavior,
        'stop_conditions': list(stop_conditions),
        'failure_branches': list(failure_branches),
        'required_evidence': list(required_evidence),
        'source_refs': list(source_refs),
        'safety': safety or ('manual operation by a competent person; the '
                             'planner never executes this step'),
        'notes': notes,
    }


def finalize_steps(steps, *, id_prefix=''):
    """Assign stable order, reject duplicate ids and empty procedures."""
    seen = set()
    ordered = []
    for index, step in enumerate(steps):
        step_id = step['step_id']
        if step_id in seen:
            raise ValueError('duplicate step_id %r' % step_id)
        seen.add(step_id)
        if step.get('status') == STATUS_READY and not step.get('procedure'):
            raise ValueError('ready step %r has no procedure' % step_id)
        step['sequence'] = index + 1
        ordered.append(step)
    return ordered


def step_ids(steps):
    return [step['step_id'] for step in steps]
