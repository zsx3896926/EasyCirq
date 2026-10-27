"""I3: rail, clock, reset and basic-communication measurement methods.

Implemented by the I3 capability owner.

Required semantics:

* voltage measurement per rail uses a declared testpoint and ground reference;
  the accepted range comes from the declared operating range and the
  measurement basis, never from the absolute maximum;
* ripple/transient and clock/reset waveform steps require a declared
  oscilloscope bandwidth, probe divider/bandwidth/loading and grounding
  method; missing capability -> BLOCKED, never a claim that the waveform was
  measured;
* an earth-referenced scope ground clip may only connect to circuit ground;
  non-ground-referenced nodes require a differential method;
* ADC readings do not prove range/accuracy; a single voltage reading does not
  prove ripple or EMC;
* USB enumeration / UART logs / debug connection require firmware and host
  prerequisites; before flashing the only expected result is "no business
  communication", not a failure.

The planner only emits manual instructions: it never connects an instrument,
never powers a board and never flashes firmware.
"""
from __future__ import annotations

import re

from . import steps

_COMM_TYPES = ('debug', 'i2c', 'spi', 'uart', 'usb')

# Clock / reset / boot-strap nets are recognised from the *declared structured
# net names* only (interface pins and testpoints).  Free-text task descriptions
# are never used to decide that a signal exists.
_CLOCK_TOKENS = frozenset((
    'CLK', 'CLOCK', 'SWCLK', 'SWDCLK', 'TCK', 'MCO', 'XTAL', 'XTALIN',
    'XTALOUT', 'OSC', 'OSCIN', 'OSCOUT', 'OSCCLK',
))
_RESET_TOKENS = frozenset((
    'RST', 'NRST', 'RESET', 'NRESET', 'SRST', 'POR', 'BOR',
))
_BOOT_TOKENS = frozenset((
    'BOOT', 'BOOT0', 'BOOT1', 'STRAP', 'STRAPPING', 'STRAPMODE',
    'MODE0', 'MODE1', 'MODESEL',
))

_HOST_PREMISE = {
    'usb': 'a host with a USB 2.0 port and the declared OS/driver; record the '
           'host, port and whether any device is enumerated',
    'uart': 'a host UART adapter that matches the declared logic level '
            '(TTL vs RS-232) and a terminal at the declared baud/format',
    'i2c': 'a host I2C adapter compatible with the declared logic level and the '
           'declared pull-ups; no second master on the bus',
    'spi': 'a host SPI adapter matched to the declared logic level and CS/idle '
           'setup; no other device on the bus',
    'debug': 'a host debug probe matched to the declared debug interface and '
             'target connector',
}


# ---------------------------------------------------------------------------
# small shared helpers (duplicated per capability module: core files are owned
# by other tasks and must not be edited here)


def _num(value):
    if isinstance(value, float):
        return '%.6g' % value
    return str(value)


def _powered(ctx):
    scope = ctx.scope or {}
    if 'energize_allowed' not in scope:
        # The gate was not assessed by this caller; plan.py always sets it.
        return True
    return bool(scope['energize_allowed'])


def _gated(ctx, missing, reason=None):
    """Return ``(status, blocked_reason, missing_information)``."""
    missing = [item for item in missing if item]
    if not _powered(ctx):
        missing.append('scope gate: energize_allowed=false (scope status %r)'
                       % ((ctx.scope or {}).get('status')))
    if not missing:
        return steps.STATUS_READY, None, []
    if reason is None:
        reason = ('blocked until the declared information/capability is '
                  'available: ' + '; '.join(missing))
    return steps.STATUS_BLOCKED, reason, missing


def _equipment_gap_once(ctx, code, equipment, capability, detail):
    for item in ctx.equipment_gaps:
        key = (item.get('code'), item.get('equipment'), item.get('capability'))
        if key == (code, equipment, capability):
            return item
    return ctx.add_equipment_gap(code, equipment, capability, detail)


def _testpoint_for(ctx, net):
    points = ctx.testpoints_for(net)
    for point in points:
        if point.get('reachability_verified'):
            return point
    return points[0] if points else None


def _tokens(net):
    return [token for token in re.split(r'[^A-Za-z0-9]+', (net or '').upper())
            if token]


def _matches(net, tokens):
    for token in _tokens(net):
        if token in tokens:
            return True
        if token.startswith('XTAL') or token.startswith('OSC'):
            return True
    return False


def _special_nets(interface):
    clock = []
    reset = []
    boot = []
    for pin in interface.get('pins') or []:
        net = pin.get('net')
        if not net or pin.get('role') in ('ground', 'power', 'nc'):
            continue
        if _matches(net, _CLOCK_TOKENS):
            clock.append(net)
        if _matches(net, _RESET_TOKENS):
            reset.append(net)
        elif _matches(net, _BOOT_TOKENS):
            boot.append(net)
    return sorted(set(clock)), sorted(set(reset)), sorted(set(boot))


# ---------------------------------------------------------------------------
# hard step dependencies (I1/I2) -- added only when the owning generator has
# already produced the step, so a capability can also be generated stand-alone


def _sanitize(value):
    text = ''.join(character if character.isalnum()
                   or character in '_.:-' else '-'
                   for character in str(value))
    return text.strip('-') or 'X'


def _step_exists(ctx, step_id):
    return any(step.get('step_id') == step_id for step in ctx.steps)


def _find_step_prefix(ctx, prefix):
    """Return the first existing step id equal to ``prefix`` or suffixed."""
    for step in ctx.steps:
        step_id = step.get('step_id') or ''
        if step_id == prefix or step_id.startswith(prefix + '-'):
            return step_id
    return None


def _step_prereq(ctx, step_id, reason):
    if not step_id or not _step_exists(ctx, step_id):
        return None
    return steps.prerequisite_step(step_id, reason)


def _dedupe_prerequisites(items):
    result = []
    seen = set()
    for item in items:
        if not item:
            continue
        if item.get('kind') == 'step':
            key = ('step', item.get('step_id'))
        else:
            key = ('condition', item.get('text'))
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _interface_domain(ctx, interface):
    """Resolve the declared supply domain for an interface, or ``None``.

    The domain is resolved structurally from a declared power pin net;
    otherwise the declared ``logic_level_v`` is matched against a single
    declared rail nominal voltage.  Ambiguous or absent declarations are not
    guessed.
    """
    for pin in interface.get('pins') or []:
        if pin.get('role') != 'power' or not pin.get('net'):
            continue
        domain = ctx.domain_for_net(pin['net'])
        if domain is not None:
            return domain
    logic_level = interface.get('logic_level_v')
    if logic_level is not None:
        tolerance = max(0.05, logic_level * 0.02)
        matches = [domain for domain in ctx.domains
                   if domain.get('nominal_v') is not None
                   and abs(domain['nominal_v'] - logic_level) <= tolerance]
        if len(matches) == 1:
            return matches[0]
    if len(ctx.domains) == 1:
        return ctx.domains[0]
    return None


def _supply_prerequisites(ctx, domain, *, include_firmware=False):
    """Existing I1/I2 steps that must complete before a powered measurement."""
    items = [
        _step_prereq(ctx, 'I1-OFF-001',
                     'board de-energised state verified by I1 before any '
                     'powered measurement'),
        _step_prereq(ctx, 'I1-OFF-DISCHARGE',
                     'bulk capacitance discharged and verified before the '
                     'powered measurement'),
    ]
    if include_firmware:
        items.append(_step_prereq(
            ctx, 'I2-FW-001',
            'firmware/debugger state recorded by I2 before interpreting '
            'interface behaviour'))
    if domain is not None:
        items.append(_step_prereq(
            ctx, 'I2-SEQ-%s' % domain['id'],
            'declared first power-up of supply domain %r completed'
            % domain['id']))
        items.append(_step_prereq(
            ctx, 'I2-LOAD-%s' % domain['id'],
            'declared removable-load isolation for domain %r completed'
            % domain['id']))
        for path in ctx.assemblies.get('external_supply_paths') or []:
            if path.get('net') != domain.get('net'):
                continue
            if not (path.get('can_backfeed')
                    or path.get('disconnect_required_for_deenergized_tests')):
                continue
            base = 'I2-EXT-%s' % _sanitize(path.get('id'))
            items.append(_step_prereq(
                ctx, _find_step_prefix(ctx, base),
                'declared external supply/backfeed path %r is isolated before '
                'energising %r' % (path.get('id'), domain['id'])))
    return _dedupe_prerequisites(items)


def _interface_prerequisites(ctx, interface, *, include_firmware=False):
    """Supply-domain dependencies plus declared removable-load/backfeed steps."""
    domain = _interface_domain(ctx, interface)
    items = _supply_prerequisites(ctx, domain,
                                 include_firmware=include_firmware)
    designator = interface.get('id')
    for load in ctx.assemblies.get('removable_loads') or []:
        if load.get('designator') != designator:
            continue
        sanitized = _sanitize(designator)
        items.append(_step_prereq(
            ctx, 'I2-LOAD-ASM-%s' % sanitized,
            'declared removable load %r isolated before the test'
            % designator))
        items.append(_step_prereq(
            ctx, 'I2-CONNECT-ASM-%s' % sanitized,
            'declared removable load %r connected by the I2 assembly step '
            'before the test' % designator))
    if interface.get('backfeed_risk'):
        base = 'I2-EXT-%s' % _sanitize(designator)
        items.append(_step_prereq(
            ctx, _find_step_prefix(ctx, base),
            'declared backfeed path of interface %r isolated before '
            'connecting it' % designator))
    return _dedupe_prerequisites(items)


# ---------------------------------------------------------------------------
# instrument capability checks


def _scope_issue(scope, required_v):
    """Return a gap tuple when ``scope`` cannot support the measurement."""
    grounding = scope.get('grounding')
    if grounding not in ('earth_referenced', 'differential', 'isolated'):
        return (
            'SCOPE_GROUNDING_NOT_DECLARED', scope['id'], 'grounding method',
            'oscilloscope %r does not declare a usable grounding method; the '
            'safe ground-clip connection cannot be verified' % scope['id'])
    probe = scope.get('probe')
    if not probe:
        return (
            'PROBE_NOT_DECLARED', scope['id'],
            'probe divider/bandwidth/loading',
            'oscilloscope %r declares no probe: probe divider ratio, '
            'bandwidth and loading cannot be verified' % scope['id'])
    if probe.get('capacitance_pf') is None:
        return (
            'PROBE_LOADING_NOT_DECLARED', scope['id'],
            'probe loading capacitance',
            'probe %r on %r does not declare its loading capacitance; the '
            'capacitive loading on the measured node cannot be verified'
            % (probe.get('type'), scope['id']))
    if probe.get('max_voltage_v') is None:
        return (
            'PROBE_VOLTAGE_RATING_NOT_DECLARED', scope['id'],
            'probe voltage rating',
            'probe on %r does not declare a maximum voltage rating; safe '
            'connection to this node cannot be verified' % scope['id'])
    if required_v and probe['max_voltage_v'] < required_v:
        return (
            'PROBE_VOLTAGE_RATING_INSUFFICIENT', scope['id'],
            'probe voltage rating',
            'declared probe rating %s V is below the required %s V for this '
            'measurement' % (_num(probe['max_voltage_v']), _num(required_v)))
    max_input = scope.get('max_input_voltage_v')
    if required_v and max_input is not None and max_input < required_v:
        return (
            'SCOPE_INPUT_RATING_INSUFFICIENT', scope['id'],
            'oscilloscope input rating',
            'declared oscilloscope input rating %s V is below the required '
            '%s V' % (_num(max_input), _num(required_v)))
    return None


def _waveform_capability(ctx, required_v):
    """Return ``(scope, issue)``; ``issue`` is a gap tuple when unusable.

    A waveform step may only be executable when the oscilloscope bandwidth, the
    probe divider/bandwidth/loading and the grounding method are declared and
    the ratings cover the measured voltage.  The first adequately declared
    scope is selected; otherwise the first finding is reported.
    """
    scopes = ctx.oscilloscopes()
    if not scopes:
        return None, (
            'OSCILLOSCOPE_NOT_DECLARED', 'oscilloscopes',
            'declared bandwidth/probe/grounding',
            'no oscilloscope is declared in equipment.oscilloscopes, so no '
            'bandwidth-correct waveform measurement can be completed')
    fallback = None
    for scope in scopes:
        issue = _scope_issue(scope, required_v)
        if issue is None:
            return scope, None
        if fallback is None:
            fallback = issue
    return None, fallback


def _scope_settings(scope):
    probe = scope['probe']
    effective = min(scope['bandwidth_mhz'], probe['bandwidth_mhz'])
    return {
        'coupling': 'DC',
        'bandwidth_limit_20mhz': 'off',
        'bandwidth_mhz': scope['bandwidth_mhz'],
        'probe': probe.get('type'),
        'probe_bandwidth_mhz': probe.get('bandwidth_mhz'),
        'probe_capacitance_pf': probe.get('capacitance_pf'),
        'grounding': scope.get('grounding'),
        'effective_bandwidth_mhz': effective,
    }


def _dmm_for(ctx, required_v):
    candidates = [meter for meter in ctx.multimeters()
                  if meter.get('dc_voltage_max_v') is not None
                  and meter['dc_voltage_max_v'] >= required_v]
    return candidates[0] if candidates else None


def _blocked_waveform_procedure(missing):
    return [
        'Do not connect any probe and do not claim that this waveform was '
        'measured: the missing capability/information is %s.'
        % '; '.join(missing),
        'Never connect an earth-referenced oscilloscope ground clip to a '
        'non-ground node; the clip may only go to the declared circuit ground.',
    ]


# ---------------------------------------------------------------------------
# I3 generation


def build(ctx):
    """Generate I3 steps into ``ctx``."""
    for domain in ctx.domains:
        _rail_voltage(ctx, domain)
        _ripple(ctx, domain)
    for interface in ctx.interfaces:
        clock_nets, reset_nets, boot_nets = _special_nets(interface)
        if clock_nets:
            _clock(ctx, interface, clock_nets)
        if reset_nets or boot_nets:
            _reset(ctx, interface, reset_nets, boot_nets)
        if interface['type'] in _COMM_TYPES:
            _comm(ctx, interface)
    return None


def _rail_voltage(ctx, domain):
    step_id = 'I3-V-%s' % domain['id']
    net = domain['net']
    ground = domain['ground_net']
    point = _testpoint_for(ctx, net)
    missing = []
    if point is None:
        missing.append('declared testpoint on rail net %r' % net)
        ctx.add_gap(
            'TESTPOINT_MISSING', step_id,
            'no declared testpoint on rail net %r: the voltage measurement '
            'point is not defined' % net,
            needed=['a declared testpoint (id, net=%r, reference_net=%r, '
                    'reachable contact)' % (net, ground)],
            severity='blocking')
    elif point.get('reference_net') != ground:
        missing.append('testpoint %r reference_net=%r does not match the '
                       'declared domain ground_net=%r'
                       % (point['id'], point.get('reference_net'), ground))
        ctx.add_gap(
            'TESTPOINT_REFERENCE_MISMATCH', step_id,
            'testpoint %r on rail %r references %r, not the declared ground '
            '%r' % (point['id'], net, point.get('reference_net'), ground),
            needed=['a testpoint with an explicit reference to the declared '
                    'ground net'],
            severity='blocking')

    absolute_max = domain['absolute_max_v']
    dmm = _dmm_for(ctx, absolute_max)
    if dmm is None:
        detail = ('no declared multimeter with dc_voltage_max_v >= %s V can '
                  'measure rail %r including its absolute-maximum stop '
                  'threshold' % (_num(absolute_max), net))
        missing.append(detail)
        _equipment_gap_once(ctx, 'DMM_DC_VOLTAGE_RANGE_NOT_DECLARED',
                            'multimeters', 'dc_voltage_measurement', detail)

    status, reason, missing = _gated(ctx, missing)
    low = domain['operating_min_v']
    high = domain['operating_max_v']
    ground_ref = point.get('reference_net') if point else ground
    basis = (
        'acceptance range is the declared operating range '
        'power_domains[%s].operating_min_v=%s V to operating_max_v=%s V '
        '(declared design intent, source: %r); absolute_max_v=%s V is a '
        'stress/stop boundary and is NOT used as the acceptance limit'
        % (domain['id'], _num(low), _num(high), domain.get('source'),
           _num(absolute_max)))

    prerequisites = [
        steps.prerequisite_condition(
            'the rail is energised by the declared I2 power-up step with the '
            'declared current limit; the de-energised I1 checks are complete'),
    ]
    prerequisites.extend(_supply_prerequisites(ctx, domain))
    if status == steps.STATUS_READY:
        procedure = [
            'Set %s to DC voltage mode; confirm its range covers %s V and '
            'record the range and resolution.' % (dmm['id'],
                                                  _num(absolute_max)),
            'Touch the probe tip to testpoint %s (net %s) and the common lead '
            'to %s (%s); ensure the common lead is only on the declared '
            'ground.' % (point['id'], net, ground_ref, ground),
            'Read the value after it settles; record the instrument model, '
            'range, testpoint and reference in the evidence.',
            'A reading inside the acceptance range proves only the DC voltage. '
            'It does not prove ripple, noise, transient droop or EMC '
            'compliance; ripple/transient is the separate I3-RIPPLE-%s step '
            'and may itself be blocked.' % domain['id'],
        ]
        equipment = [steps.equipment_item(
            dmm['id'], 'dc_voltage_measurement',
            settings={'mode': 'dc_voltage',
                      'range_max_v': dmm['dc_voltage_max_v'],
                      'resolution_v': dmm.get('dc_voltage_resolution_v')},
            verified=dmm.get('dc_voltage_resolution_v') is not None,
            detail='measure the DC rail voltage at the declared testpoint')]
        measurement = {
            'quantity': 'voltage',
            'point': point['id'],
            'reference': ground_ref,
            'range': {'min': low, 'max': high, 'unit': 'V'},
            'criterion_status': 'defined',
            'basis': basis,
            'source_refs': [],
        }
        expected = ('the DC voltage at %s referenced to %s stays between %s V '
                    'and %s V' % (point['id'], ground_ref, _num(low),
                                  _num(high)))
        required_evidence = [
            steps.evidence_item(
                'meter_reading',
                'DMM DC voltage at %s (%s) referenced to %s, with instrument '
                'model/serial, range and timestamp' % (point['id'], net,
                                                       ground_ref)),
        ]
    else:
        procedure = [
            'Do not perform this voltage measurement until the missing '
            'information/capability is declared: %s.' % '; '.join(missing),
            'No voltage PASS/FAIL may be recorded from a different testpoint '
            'or reference.',
        ]
        equipment = []
        measurement = None
        expected = ('no valid DC voltage criterion exists until the declared '
                    'testpoint/reference/instrument is available')
        required_evidence = [
            steps.evidence_item(
                'meter_reading',
                'DMM DC voltage at the declared testpoint referenced to the '
                'declared ground (not obtainable yet)',
                verifiable=False),
        ]

    step = steps.make_step(
        step_id=step_id, group='I3',
        title='Measure DC voltage of rail %s (%s)' % (domain['id'], net),
        purpose='Verify the declared DC operating range of rail %r at a '
                'declared testpoint, without treating the absolute maximum as '
                'the acceptance limit.' % net,
        prerequisites=prerequisites,
        equipment=equipment,
        wiring={'measure_at': point['id'] if point else 'not declared',
                'reference': ground_ref,
                'probe': 'DMM test leads',
                'notes': 'DC voltage only; a DC reading is not ripple or '
                         'transient evidence'},
        procedure=procedure,
        measurement=measurement,
        expected_behavior=expected,
        stop_conditions=[
            steps.stop_condition(
                'OVERVOLTAGE_ABSOLUTE_MAX',
                'rail %r exceeds the declared absolute maximum %s V'
                % (net, _num(absolute_max)),
                threshold=absolute_max, quantity='voltage', unit='V',
                source_ref='power_domains[%s].absolute_max_v' % domain['id']),
            steps.stop_condition(
                'REVERSED_POLARITY',
                'the measured voltage is negative or the supply polarity is '
                'reversed'),
        ],
        required_evidence=required_evidence,
        status=status, blocked_reason=reason,
        missing_information=missing,
        source_refs=['power_domains[%s]' % domain['id']],
        notes='absolute_max_v is a stress boundary, never the working target; '
              'DC voltage inside the range does not prove ripple/transient '
              'quality',
    )
    ctx.add_step(step)


def _ripple(ctx, domain):
    step_id = 'I3-RIPPLE-%s' % domain['id']
    net = domain['net']
    ground = domain['ground_net']
    absolute_max = domain['absolute_max_v']
    point = _testpoint_for(ctx, net)
    missing = []
    if point is None:
        missing.append('declared testpoint on rail net %r' % net)
        ctx.add_gap(
            'TESTPOINT_MISSING', step_id,
            'no declared testpoint on rail net %r for the ripple/transient '
            'measurement' % net,
            needed=['a declared testpoint on %r with an explicit reference to '
                    '%r' % (net, ground)],
            severity='blocking')
    elif point.get('reference_net') != ground:
        missing.append('testpoint %r reference_net=%r does not match the '
                       'declared ground_net=%r'
                       % (point['id'], point.get('reference_net'), ground))

    scope, issue = _waveform_capability(ctx, absolute_max)
    if issue is not None:
        missing.append(issue[3])
        _equipment_gap_once(ctx, *issue)

    status, reason, missing = _gated(ctx, missing)
    prerequisites = [
        steps.prerequisite_condition(
            'the rail voltage step I3-V-%s is recorded; the board is '
            'energised under the declared I2 conditions' % domain['id']),
        steps.prerequisite_condition(
            'the oscilloscope ground clip may only be connected to the '
            'declared circuit ground %r; it must never be connected to a '
            'non-ground node' % ground),
    ]
    prerequisites.extend(_supply_prerequisites(ctx, domain))
    if status == steps.STATUS_READY:
        settings = _scope_settings(scope)
        procedure = [
            'Set %s to DC coupling, 20 MHz bandwidth limit off unless a '
            'declared limit applies; record the effective bandwidth = '
            'min(%s MHz scope, %s MHz probe) = %s MHz.'
            % (scope['id'], _num(scope['bandwidth_mhz']),
               _num(scope['probe']['bandwidth_mhz']),
               _num(settings['effective_bandwidth_mhz'])),
            'Use the declared probe (%s, %s pF) with a short ground lead '
            'connected only to %r. The probe loading is part of the '
            'measurement; record it.'
            % (scope['probe'].get('type'),
               _num(scope['probe'].get('capacitance_pf')), ground),
            'Measure the rail AC ripple at testpoint %s (%s) referenced to '
            '%s with a DC-coupled vertical scale that keeps the rail on '
            'screen; record Vpp and, if used, Vrms separately.'
            % (point['id'], net, ground),
            'Capture the power-up transient with a single-shot trigger and '
            'record the trigger level/timebase. Do not use averaging for a '
            'single event.',
            'Report p-p and RMS as different quantities with their '
            'assumptions; do not convert one into the other without stating '
            'the assumption.',
            'A DC voltage inside the operating range does not prove ripple, '
            'noise, transient droop or EMC compliance; no numeric ripple '
            'limit is declared in this input, so record the capture as '
            'observation, not as a numeric PASS.',
        ]
        equipment = [steps.equipment_item(
            scope['id'], 'ripple_and_transient_measurement',
            settings=settings,
            verified=True,
            detail='declared bandwidth, probe loading and grounding verified')]
        measurement = {
            'quantity': 'voltage',
            'point': point['id'],
            'reference': point.get('reference_net'),
            'range': None,
            'criterion_status': 'undefined',
            'basis': 'no numeric ripple/noise/transient limit is declared in '
                     'the input; the capture is an observation, not a PASS '
                     'criterion. Any numeric limit would need a declared '
                     'bandwidth, coupling, probe ratio and measurement point.',
            'source_refs': [],
        }
        expected = ('the rail is present and stable; record the ripple/'
                    'transient capture, but no numeric pass/fail exists '
                    'without a declared limit')
        required_evidence = [
            steps.evidence_item(
                'scope_capture',
                'scope capture of %s at %s referenced to %s, with bandwidth, '
                'coupling, probe ratio, timebase and trigger recorded'
                % (net, point['id'], point.get('reference_net'))),
        ]
    else:
        procedure = _blocked_waveform_procedure(missing)
        equipment = []
        measurement = None
        expected = ('no waveform measurement may be recorded: the declared '
                    'capability is insufficient, so any "ripple looks fine" '
                    'statement would be invalid')
        required_evidence = [
            steps.evidence_item(
                'scope_capture',
                'valid ripple/transient capture (not obtainable with the '
                'declared capability)', verifiable=False),
        ]

    ctx.add_step(steps.make_step(
        step_id=step_id, group='I3',
        title='Capture ripple and power-up transient of rail %s' % net,
        purpose='Check whether a bandwidth-correct ripple/transient '
                'measurement is possible, and record it separately from the '
                'DC voltage criterion.',
        prerequisites=prerequisites,
        equipment=equipment,
        wiring={'measure_at': point['id'] if point else 'not declared',
                'reference': ground,
                'probe': '%s probe' % (scope['probe'].get('type')
                                       if scope else 'not declared'),
                'notes': 'the scope ground clip may only contact the declared '
                         'circuit ground'},
        procedure=procedure,
        measurement=measurement,
        expected_behavior=expected,
        stop_conditions=[
            steps.stop_condition(
                'OVERVOLTAGE_ABSOLUTE_MAX',
                'the rail exceeds the declared absolute maximum %s V'
                % _num(absolute_max),
                threshold=absolute_max, quantity='voltage', unit='V',
                source_ref='power_domains[%s].absolute_max_v' % domain['id']),
        ],
        required_evidence=required_evidence,
        status=status, blocked_reason=reason,
        missing_information=missing,
        source_refs=['power_domains[%s]' % domain['id']],
        notes='a DC voltage reading is not ripple/transient evidence; '
              'missing bandwidth/probe/grounding capability keeps this step '
              'BLOCKED',
    ))


def _clock(ctx, interface, clock_nets):
    step_id = 'I3-CLK-%s' % interface['id']
    missing = []
    points = {}
    for net in clock_nets:
        point = _testpoint_for(ctx, net)
        if point is None:
            missing.append('declared testpoint on clock net %r' % net)
            ctx.add_gap(
                'TESTPOINT_MISSING', step_id,
                'clock signal %r is declared on interface %r but no testpoint '
                'is declared on that net' % (net, interface['id']),
                needed=['a reachable testpoint on net %r' % net],
                severity='blocking')
        else:
            points[net] = point
    logic_level = interface.get('logic_level_v')
    scope, issue = _waveform_capability(
        ctx, logic_level if logic_level is not None else 0.0)
    if issue is not None:
        missing.append(issue[3])
        _equipment_gap_once(ctx, *issue)
    if logic_level is None:
        missing.append('declared logic_level_v for the clock interface')

    status, reason, missing = _gated(ctx, missing)
    notes = (interface.get('notes') or '').strip()
    prerequisites = [
        steps.prerequisite_condition(
            'the declared ground reference: the scope ground clip may only be '
            'connected to the circuit ground, never to the clock, reset or '
            'boot-strap net'),
        steps.prerequisite_condition(
            ('declared clock mode/timing premise (interface notes): %s'
             % notes) if notes else
            'no declared clock frequency/timing or mode premise: confirm the '
            'required mode and an official limit before judging the waveform; '
            'an absent waveform must stay unknown, not a failure',
            source_ref=('interfaces[%s].notes' % interface['id'])
            if notes else None),
    ]
    prerequisites.extend(_interface_prerequisites(ctx, interface))
    if status == steps.STATUS_READY:
        settings = _scope_settings(scope)
        procedure = [
            'Set %s to DC coupling, 20 MHz bandwidth limit off unless a '
            'declared limit applies; record the effective bandwidth = '
            'min(%s MHz scope, %s MHz probe) = %s MHz.'
            % (scope['id'], _num(scope['bandwidth_mhz']),
               _num(scope['probe']['bandwidth_mhz']),
               _num(settings['effective_bandwidth_mhz'])),
            'Use the declared probe (%s, %s pF) and connect its ground clip '
            'only to the circuit ground. The declared probe capacitance loads '
            'the clock node and can slow the edges or stop the oscillator; '
            'the loaded waveform is not the unloaded waveform.'
            % (scope['probe'].get('type'),
               _num(scope['probe'].get('capacitance_pf'))),
        ]
        for net in sorted(points):
            procedure.append(
                'Probe testpoint %s (net %s) referenced to %s and record the '
                'frequency and amplitude as observations.'
                % (points[net]['id'], net, points[net].get('reference_net')))
        procedure.append(
            'Timing/mode premise: %s. No official clock frequency/timing '
            'limit is declared in device_facts, so no numeric PASS/FAIL is '
            'defined for this step.' % (notes or 'not declared'))
        equipment = [steps.equipment_item(
            scope['id'], 'clock_waveform_observation',
            settings=settings, verified=True,
            detail='declared bandwidth, probe loading and grounding verified')]
        first_net = sorted(points)[0]
        measurement = {
            'quantity': 'frequency',
            'point': points[first_net]['id'],
            'reference': points[first_net].get('reference_net'),
            'range': None,
            'criterion_status': 'undefined',
            'basis': 'no official clock frequency/timing limit is declared in '
                     'device_facts; the waveform is recorded as an '
                     'observation only',
            'source_refs': [],
        }
        expected = ('the clock observation is recorded; absence may be caused '
                    'by reset state, boot mode or probe loading and must be '
                    'recorded as unknown, not as a clock failure')
    else:
        procedure = _blocked_waveform_procedure(missing) + [
            'The declared clock net(s) %s remain unverified until the missing '
            'capability is available.' % ', '.join(clock_nets),
        ]
        equipment = []
        measurement = None
        expected = ('no waveform may be claimed: missing bandwidth/probe '
                    'information invalidates any clock judgement')

    ctx.add_step(steps.make_step(
        step_id=step_id, group='I3',
        title='Observe declared clock signal(s) on interface %s'
              % interface['id'],
        purpose='Record the declared clock signal only when a bandwidth- and '
                'loading-correct scope method is declared; never claim a '
                'clock measurement with missing probe/bandwidth information.',
        prerequisites=prerequisites,
        equipment=equipment,
        wiring={'measure_at': ', '.join(
                    points[net]['id'] for net in sorted(points))
                if points else 'not declared',
                'reference': 'circuit ground',
                'probe': '%s probe' % (scope['probe'].get('type')
                                       if scope else 'not declared'),
                'notes': 'probe capacitance loads high-impedance clock nodes; '
                         'ground clip only on circuit ground'},
        procedure=procedure,
        measurement=measurement,
        expected_behavior=expected,
        required_evidence=[
            steps.evidence_item(
                'scope_capture',
                'clock observation at %s with probe ratio/capacitance, '
                'bandwidth, coupling and timebase recorded'
                % ', '.join('%s (%s)' % (points[net]['id'], net)
                            for net in sorted(points))
                if points else 'clock observation (not obtainable)',
                verifiable=status == steps.STATUS_READY),
        ],
        status=status, blocked_reason=reason,
        missing_information=missing,
        source_refs=['interfaces[%s]' % interface['id']],
        notes='only generated for clock signals declared on interface pins '
              'and located at a declared testpoint; timing limits must come '
              'from official values, not from experience',
    ))


def _reset(ctx, interface, reset_nets, boot_nets):
    step_id = 'I3-RST-%s' % interface['id']
    nets = sorted(set(reset_nets) | set(boot_nets))
    missing = []
    points = {}
    for net in nets:
        point = _testpoint_for(ctx, net)
        if point is None:
            missing.append('declared testpoint on reset/boot net %r' % net)
            ctx.add_gap(
                'TESTPOINT_MISSING', step_id,
                'declared reset/boot-strap net %r on interface %r has no '
                'testpoint' % (net, interface['id']),
                needed=['a reachable testpoint on net %r' % net],
                severity='blocking')
        else:
            points[net] = point
    logic_level = interface.get('logic_level_v')
    scope, issue = _waveform_capability(
        ctx, logic_level if logic_level is not None else 0.0)
    if issue is not None:
        missing.append(issue[3])
        _equipment_gap_once(ctx, *issue)

    status, reason, missing = _gated(ctx, missing)
    notes = (interface.get('notes') or '').strip()
    prerequisites = [
        steps.prerequisite_condition(
            'the declared ground reference: the scope ground clip may only be '
            'connected to the circuit ground'),
        steps.prerequisite_condition(
            ('declared reset/boot mode premise (interface notes): %s' % notes)
            if notes else
            'no declared reset/boot mode premise: confirm which boot-strap '
            'combination the design expects before interpreting levels',
            source_ref=('interfaces[%s].notes' % interface['id'])
            if notes else None),
    ]
    prerequisites.extend(_interface_prerequisites(ctx, interface))
    if status == steps.STATUS_READY:
        settings = _scope_settings(scope)
        procedure = [
            'Set %s to DC coupling and record the effective bandwidth = %s '
            'MHz; the probe ground clip may only contact the circuit ground.'
            % (scope['id'], _num(settings['effective_bandwidth_mhz'])),
            'The declared probe (%s, %s pF) loads the reset/boot nodes: it '
            'can change the reset RC time constant or the level sampled at '
            'boot. Record the probe type and capacitance.'
            % (scope['probe'].get('type'),
               _num(scope['probe'].get('capacitance_pf'))),
            'Check all declared reset/boot-strap nets together: %s. A '
            'boot-mode conclusion from a single pin is incomplete.'
            % ', '.join('%s (%s)' % (points[net]['id'], net)
                        for net in sorted(points)),
            'Record the reset pulse width and boot-strap levels as '
            'observations. No official reset/timing/strap-hold limit is '
            'declared in device_facts, so no numeric PASS/FAIL is defined; '
            'official values may only be used when they are declared.',
        ]
        equipment = [steps.equipment_item(
            scope['id'], 'reset_time_measurement', settings=settings,
            verified=True,
            detail='declared bandwidth, probe loading and grounding verified')]
        first_net = sorted(points)[0]
        measurement = {
            'quantity': 'time',
            'point': points[first_net]['id'],
            'reference': points[first_net].get('reference_net'),
            'range': None,
            'criterion_status': 'undefined',
            'basis': 'no official reset timing / boot-strap hold limit is '
                     'declared in device_facts; the waveform is an '
                     'observation only',
            'source_refs': [],
        }
        expected = ('the reset/boot observation is recorded; an absent or '
                    'unexpected pulse must stay unknown until an official '
                    'timing/mode value is declared')
    else:
        procedure = _blocked_waveform_procedure(missing) + [
            'Reset/boot levels on %s stay unverified until the missing '
            'capability is available.' % ', '.join(nets),
        ]
        equipment = []
        measurement = None
        expected = ('no reset/timing claim may be recorded from an '
                    'unverified probe/bandwidth setup')

    ctx.add_step(steps.make_step(
        step_id=step_id, group='I3',
        title='Verify declared reset/boot-strap signals on interface %s'
              % interface['id'],
        purpose='Record declared reset and boot-strap signals only with a '
                'declared probe/bandwidth method, and keep the boot-mode '
                'precondition explicit.',
        prerequisites=prerequisites,
        equipment=equipment,
        wiring={'measure_at': ', '.join(
                    points[net]['id'] for net in sorted(points))
                if points else 'not declared',
                'reference': 'circuit ground',
                'probe': '%s probe' % (scope['probe'].get('type')
                                       if scope else 'not declared'),
                'notes': 'probe loading changes reset/boot timing'},
        procedure=procedure,
        measurement=measurement,
        expected_behavior=expected,
        required_evidence=[
            steps.evidence_item(
                'scope_capture',
                'reset/boot capture at %s with probe ratio/capacitance and '
                'timebase recorded' % ', '.join(nets),
                verifiable=status == steps.STATUS_READY),
        ],
        status=status, blocked_reason=reason,
        missing_information=missing,
        source_refs=['interfaces[%s]' % interface['id']],
        notes='only generated for reset/boot signals that the interface '
              'declares and that have a declared testpoint; timing limits '
              'come from official values only',
    ))


def _comm_missing(interface):
    typ = interface['type']
    notes = (interface.get('notes') or '').strip()
    low = notes.lower()
    missing = []
    if interface.get('logic_level_v') is None:
        missing.append('declared logic_level_v (the host adapter level must '
                       'match it)')
    if not interface.get('firmware_prerequisite'):
        missing.append('declared firmware_prerequisite (image/version and '
                       'flash state)')
    if typ == 'i2c':
        if not notes:
            missing.append('declared bus premise in interface notes (pull-up '
                           'value, number of devices/masters)')
        elif 'pull' not in low and '\u4e0a\u62c9' not in notes:
            missing.append('declared pull-up value(s) for SDA/SCL')
    elif typ == 'spi':
        if not notes:
            missing.append('declared bus premise in interface notes '
                           '(single master, CS idle state, termination, '
                           'number of devices)')
        elif not any(word in low for word in ('termination', 'master',
                                             'idle', 'cs')):
            missing.append('declared CS idle state / termination / number of '
                           'devices')
    elif typ == 'uart':
        if not notes:
            missing.append('declared host-adapter premise in interface notes '
                           '(TTL vs RS-232, baud/format)')
        elif not any(word in low for word in ('ttl', 'rs-232', 'rs232',
                                             'adapter', 'logic')):
            missing.append('declared host-adapter electrical type '
                           '(TTL vs RS-232)')
    return missing


def _comm(ctx, interface):
    step_id = 'I3-COMM-%s' % interface['id']
    typ = interface['type']
    missing = _comm_missing(interface)
    status, reason, missing = _gated(ctx, missing)

    firmware = (interface.get('firmware_prerequisite') or '').strip()
    notes = (interface.get('notes') or '').strip()
    firmware_flashing_forbidden = 'firmware_flashing' in (
        ctx.policy.get('forbidden_operations') or [])
    host = _HOST_PREMISE.get(typ, 'a host matched to the declared interface')

    prerequisites = [
        steps.prerequisite_condition(
            ('declared firmware prerequisite: %s' % firmware) if firmware
            else
            'firmware prerequisite is NOT declared: record the exact image, '
            'version and flash state before interpreting any host log',
            source_ref=('interfaces[%s].firmware_prerequisite'
                        % interface['id']) if firmware else None),
        steps.prerequisite_condition(
            ('declared host premise (interface notes): %s' % notes) if notes
            else 'host prerequisite: %s' % host,
            source_ref=('interfaces[%s].notes' % interface['id'])
            if notes else None),
    ]
    if interface.get('backfeed_risk'):
        prerequisites.append(steps.prerequisite_condition(
            'declared backfeed risk on this interface: isolate the external '
            'supply/host path before connecting or powering the board'))
    if firmware_flashing_forbidden:
        prerequisites.append(steps.prerequisite_condition(
            'user_policy.forbidden_operations contains firmware_flashing: '
            'this plan may not flash firmware, so only the pre-firmware '
            'baseline can be recorded'))
    prerequisites = _dedupe_prerequisites(
        prerequisites + _interface_prerequisites(ctx, interface,
                                                 include_firmware=True))

    if status == steps.STATUS_READY:
        procedure = [
            'Connect only the declared devices/adapters for interface %r; '
            'unknown modules, a second master or an unknown load are not safe '
            'by default and must be disconnected first.'
            % interface['id'],
            'Confirm the declared %s V logic level and that the host adapter '
            'I/O is matched to it; never drive a %s V bus with a 5 V adapter.'
            % (_num(interface.get('logic_level_v')),
               _num(interface.get('logic_level_v'))),
            'Firmware prerequisite: %s. Until that firmware is flashed, the '
            'only expected result is NO business communication (no '
            'enumeration, no serial traffic, no ACK). That absence is not a '
            'failure and must be recorded as not applicable yet.'
            % (firmware or 'not declared'),
            'Host prerequisite: %s. Record adapter model, settings and the '
            'host log/serial log.' % (notes or host),
            'A numeric value reported by the firmware (for example ADC '
            'counts) is not proof of range or accuracy; that belongs to the '
            'analog-input measurement and must not be recorded as a '
            'measurement PASS here.',
        ]
        measurement = None
        expected = ('before the declared firmware is flashed: no business '
                    'communication is expected (no enumeration/serial traffic/'
                    'ACK) and that is not a failure; after an authorized '
                    'flashing, record the observed enumeration/log')
    else:
        procedure = [
            'Do not connect the host adapter and do not claim any interface '
            'behaviour until the missing declared information is available: '
            '%s.' % '; '.join(missing),
            'Bus conflicts and unknown loads are not safe by default; no '
            '"it probably enumerates" statement may be recorded.',
        ]
        measurement = None
        expected = ('no communication claim is valid while the declared '
                    'level/topology/firmware premise is missing')

    equipment = []
    dmm = _dmm_for(ctx, float(interface.get('logic_level_v') or 0.0))
    if dmm is not None:
        equipment.append(steps.equipment_item(
            dmm['id'], 'dc_voltage_measurement',
            settings={'mode': 'dc_voltage',
                      'range_max_v': dmm['dc_voltage_max_v']},
            verified=dmm.get('dc_voltage_resolution_v') is not None,
            detail='idle logic-level observation only; not a protocol test'))

    if typ == 'usb':
        evidence = [steps.evidence_item(
            'host_log',
            'host USB enumeration log: device present/absent, VID/PID and '
            'descriptors, with timestamp',
            verifiable=status == steps.STATUS_READY)]
    else:
        evidence = [steps.evidence_item(
            'serial_log',
            'serial/host log for %r: adapter, settings and timestamp'
            % interface['id'], verifiable=status == steps.STATUS_READY),
            steps.evidence_item(
                'host_log',
                'host-side transaction/terminal log for %r'
                % interface['id'], verifiable=status == steps.STATUS_READY)]

    ctx.add_step(steps.make_step(
        step_id=step_id, group='I3',
        title='Debug/enumerate declared interface %s (%s)'
              % (interface['id'], typ),
        purpose='Establish the host/firmware premise and record the '
                'pre-firmware "no business communication" baseline without '
                'treating it as a failure.',
        prerequisites=prerequisites,
        equipment=equipment,
        wiring={'measure_at': 'declared interface pins',
                'reference': 'circuit ground',
                'probe': None,
                'notes': 'do not probe bus data lines single-ended with an '
                         'earth-referenced scope'},
        procedure=procedure,
        measurement=measurement,
        expected_behavior=expected,
        required_evidence=evidence,
        status=status, blocked_reason=reason,
        missing_information=missing,
        source_refs=['interfaces[%s]' % interface['id']],
        notes='firmware and host prerequisites are written explicitly; a '
              'missing firmware means "no business communication expected", '
              'not a failure',
    ))
