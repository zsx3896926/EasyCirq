"""First-release scope gate.

The gate is decided from declared inputs (supply class, declared operations,
declared voltage envelope and user policy), never from a project name or a
keyword in free text.  When the envelope cannot be verified, the planner asks
for information instead of emitting generic energise steps.
"""
from __future__ import annotations

from . import (SUPPORTED_MAX_ABSOLUTE_DC_V, SUPPORTED_MAX_OPERATING_DC_V,
               SUPPORTED_OPERATIONS, UNSUPPORTED_SUPPLY_CLASSES)

_DIGITAL_TYPES = ('usb', 'uart', 'i2c', 'spi', 'gpio', 'debug')
_LOAD_TYPES = ('load_output', 'led', 'button')


def required_operations(model):
    operations = {'visual_inspection', 'deenergized_continuity'}
    if model['power_domains']:
        operations.add('powered_dc_measurement')
    for interface in model['interfaces']:
        kind = interface.get('type')
        if kind in _DIGITAL_TYPES:
            operations.add('digital_interface')
        if kind == 'analog_input':
            operations.add('analog_measurement')
        if kind == 'analog_output':
            operations.add('analog_measurement')
        if kind in _LOAD_TYPES:
            operations.add('low_side_load')
        if kind == 'bridge_output':
            operations.add('analog_measurement')
    return sorted(operations)


def assess_scope(model):
    required = required_operations(model)
    declared = set(model['project']['scope']['operations'])
    authorized = set(model['user_policy']['allowed_operations'])
    forbidden = set(model['user_policy']['forbidden_operations'])
    reasons = []

    def add(code, detail, severity='blocking'):
        reasons.append({'code': code, 'detail': detail, 'severity': severity})

    supply_class = model['project']['scope']['supply_class']
    unsupported = False
    specialist = False
    if model['user_policy']['mode'] != 'plan_only':
        add('MODE_NOT_PLAN_ONLY',
            'user_policy.mode=%r; this tool only produces reviewed plans and '
            'never executes them' % model['user_policy']['mode'])
        unsupported = True
    if supply_class in UNSUPPORTED_SUPPLY_CLASSES:
        add('SUPPLY_CLASS_OUT_OF_SCOPE',
            'declared supply class %r needs a specialist workflow; this '
            'release only supports dc_low_voltage' % supply_class)
        unsupported = True
        specialist = supply_class in ('mains_ac', 'high_voltage_dc',
                                      'battery_charging')
    elif supply_class != 'dc_low_voltage':
        add('SUPPLY_CLASS_UNKNOWN', 'unrecognised supply class %r'
            % supply_class)
        unsupported = True

    max_operating = 0.0
    max_absolute = 0.0
    for domain in model['power_domains']:
        if domain['operating_max_v'] is not None:
            max_operating = max(max_operating, domain['operating_max_v'])
        if domain['absolute_max_v'] is not None:
            max_absolute = max(max_absolute, domain['absolute_max_v'])
        if domain['operating_max_v'] is not None and \
                domain['operating_max_v'] > SUPPORTED_MAX_OPERATING_DC_V:
            add('VOLTAGE_ENVELOPE_OUT_OF_SCOPE',
                'rail %r operating_max_v=%.6g V exceeds the supported '
                'low-voltage envelope (%.6g V)'
                % (domain['net'], domain['operating_max_v'],
                   SUPPORTED_MAX_OPERATING_DC_V))
            unsupported = True
        if domain['absolute_max_v'] is not None and \
                domain['absolute_max_v'] > SUPPORTED_MAX_ABSOLUTE_DC_V:
            add('ABSOLUTE_MAX_OUT_OF_SCOPE',
                'rail %r absolute_max_v=%.6g V exceeds the first-release '
                'absolute envelope (%.6g V); confirm the safe boundary with a '
                'specialist' % (domain['net'], domain['absolute_max_v'],
                                SUPPORTED_MAX_ABSOLUTE_DC_V))
            specialist = True

    missing = [op for op in required if op not in declared]
    if missing:
        add('OPERATIONS_NOT_DECLARED',
            'required operations not declared in project.scope.operations: %s'
            % ', '.join(missing))
        unsupported = unsupported or specialist
    unauthorized = [op for op in required if op not in authorized]
    if unauthorized:
        add('OPERATIONS_NOT_AUTHORIZED',
            'required operations not authorized by user_policy.'
            'allowed_operations: %s' % ', '.join(unauthorized))
    forbidden_required = [op for op in required if op in forbidden]
    if forbidden_required:
        add('OPERATIONS_FORBIDDEN',
            'required operations are forbidden by user_policy: %s'
            % ', '.join(forbidden_required))
        unsupported = True
    extra = [op for op in sorted(declared) if op not in SUPPORTED_OPERATIONS]
    if extra:
        add('OPERATIONS_EXTRA_UNSUPPORTED',
            'declared operations outside the first-release tool scope: %s'
            % ', '.join(extra), 'advisory')

    if max_operating > 0:
        ceiling = model['user_policy']['max_input_voltage_v']
        if ceiling is not None and max_operating > ceiling:
            add('POLICY_VOLTAGE_CEILING_LOW',
                'user_policy.max_input_voltage_v=%.6g V is below the highest '
                'rail operating voltage %.6g V; the user has not authorized '
                'energising at the declared rail voltage'
                % (ceiling, max_operating))
    if unsupported:
        status = 'needs_specialist' if specialist else 'unsupported'
    elif any(item['severity'] == 'blocking' for item in reasons):
        status = 'needs_information'
    else:
        status = 'supported'
    return {
        'status': status,
        'supply_class': supply_class,
        'energize_allowed': status == 'supported',
        'reasons': reasons,
        'required_operations': required,
        'declared_operations': sorted(declared),
        'authorized_operations': sorted(authorized),
        'voltage_envelope': {
            'max_operating_v': max_operating,
            'max_absolute_v': max_absolute,
            'supported_max_operating_v': SUPPORTED_MAX_OPERATING_DC_V,
            'supported_max_absolute_v': SUPPORTED_MAX_ABSOLUTE_DC_V,
        },
        'excluded': [item['detail'] for item in reasons
                     if item['severity'] == 'blocking'],
    }
