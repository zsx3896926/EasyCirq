"""I4: declared load / interface / analog-input test templates.

Implemented by the I4 capability owner.

Required semantics:

* low-side loads: only with a declared load (removable load / datasheet
  current), never "short the output" or "apply full scale for a long time" by
  default; the step separates design target from the device operating limit;
* I2C/SPI/UART/USB: declared logic levels, pull-ups, firmware and host-based
  prerequisites; no bus contention / no unknown load unless declared;
* analog inputs: only with a declared source and range; reading a value does
  not prove range or accuracy;
* bridge-tied / non-ground-referenced outputs: single-ended earth-grounded
  scope measurement is forbidden and explicitly stated; if no differential
  probe/method is declared, the related steps are BLOCKED;
* standards: distinguish ``design_target`` from
  ``device_operating_requirement``; datasheet typical values are marked
  typical and never treated as guaranteed limits.

The planner never energises an output, never connects a load and never probes
a board: every generated step is a manual instruction for a competent person.
"""
from __future__ import annotations

import re

from . import steps

_BUS_TYPES = ('i2c', 'spi', 'uart', 'usb')
_LOAD_TYPES = ('button', 'led', 'load_output')
_NON_GROUND_REFERENCED = ('bridge_tied_load', 'differential',
                          'floating_unknown')

# A declared numeric source range in the free-text interface notes, e.g.
# "signal range 0.20..2.80 V".  Only the declared notes are read; no value is
# invented when the range is absent.
_RANGE_RE = re.compile(
    r'range\s*:?\s*([0-9]+(?:\.[0-9]+)?)\s*'
    r'(?:\.\.|\u2026|\u2014|\u2013|\bto\b|-)\s*'
    r'([0-9]+(?:\.[0-9]+)?)\s*(mV|V)\b',
    re.IGNORECASE)

_HOST_PREMISE = {
    'usb': 'a declared USB host port (and OS/driver) is required; USB data '
           'lines are differential and must not be probed single-ended with '
           'an earth-referenced scope',
    'uart': 'a host UART adapter matched to the declared logic level '
            '(TTL vs RS-232) and a terminal at the declared baud/format',
    'i2c': 'a host I2C adapter compatible with the declared logic level and '
           'pull-ups, with no second master on the bus',
    'spi': 'a host SPI adapter matched to the declared logic level, CS/idle '
           'setup and the declared number of devices',
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
        return True
    return bool(scope['energize_allowed'])


def _gated(ctx, missing, reason=None):
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


def _signal_nets(interface):
    nets = []
    for pin in interface.get('pins') or []:
        net = pin.get('net')
        if net and pin.get('role') in (None, 'signal', 'power'):
            nets.append(net)
    return sorted(set(nets))


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
    """Existing I1/I2 steps that must complete before a powered test."""
    items = [
        _step_prereq(ctx, 'I1-OFF-001',
                     'board de-energised state verified by I1 before any '
                     'powered test'),
        _step_prereq(ctx, 'I1-OFF-DISCHARGE',
                     'bulk capacitance discharged and verified before the '
                     'powered test'),
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


def _differential_capability(ctx):
    """Return a scope declaring a differential or isolated measurement method."""
    for scope in ctx.oscilloscopes():
        probe = scope.get('probe') or {}
        probe_type = (probe.get('type') or '').lower()
        if scope.get('grounding') in ('differential', 'isolated') or \
                'diff' in probe_type:
            if not probe:
                continue
            return scope
    return None


def _differential_gap(ctx):
    _equipment_gap_once(
        ctx, 'DIFFERENTIAL_PROBE_NOT_DECLARED', 'oscilloscopes',
        'differential_or_isolated_measurement',
        'no declared differential probe or isolated channel can measure the '
        'non-ground-referenced output; an earth-referenced single-ended probe '
        'must never be connected to either output node')


def _basis(notes):
    return (
        'design_target and device_operating_requirement are kept separate: '
        'declared interface notes = %r (design intent, not a guaranteed '
        'device limit); device_operating_requirement = only declared '
        'min/max values, if any. Typical datasheet values are not guaranteed '
        'limits and are never used as thresholds.' % (notes or 'not declared'))


def _parse_voltage_range(notes):
    match = _RANGE_RE.search(notes or '')
    if not match:
        return None, None
    low = float(match.group(1))
    high = float(match.group(2))
    unit = match.group(3).lower()
    if unit == 'mv':
        low, high = low / 1000.0, high / 1000.0
    if low > high:
        return None, None
    return low, high


# ---------------------------------------------------------------------------
# I4 generation


def build(ctx):
    """Generate I4 steps into ``ctx``."""
    for interface in ctx.interfaces:
        interface_type = interface['type']
        output_type = interface.get('output_type')
        if interface_type in _LOAD_TYPES:
            _load(ctx, interface)
        if interface_type in _BUS_TYPES:
            _bus(ctx, interface)
        if interface_type == 'analog_input':
            _analog(ctx, interface)
        if interface_type == 'bridge_output' or \
                output_type in _NON_GROUND_REFERENCED or \
                (interface_type == 'analog_output' and output_type is None):
            _bridge(ctx, interface)
    return None


# ---------------------------------------------------------------------------
# declared loads: load_output / led / button


def _load(ctx, interface):
    step_id = 'I4-LOAD-%s' % interface['id']
    interface_type = interface['type']
    output_type = interface.get('output_type')
    notes = (interface.get('notes') or '').strip()
    logic_level = interface.get('logic_level_v')

    if interface_type in ('led', 'load_output'):
        if not notes:
            detail = ('interface %r (%s) declares no load/device constraint '
                      '(notes); no load step is generated because an unknown '
                      'dummy load must never be used'
                      % (interface['id'], interface_type))
            ctx.add_gap('LOAD_DECLARATION_MISSING', step_id, detail,
                        needed=['declared load (component/current/voltage), '
                                'design target and device operating limit'],
                        severity='blocking')
            ctx.add_unknown('LOAD_DECLARATION_MISSING', step_id, detail,
                            needed=['declared load and its device operating '
                                    'limit'], blocks=[step_id])
            return
        if output_type in _NON_GROUND_REFERENCED:
            detail = ('interface %r declares output_type=%r: the load and '
                      'its measurement are not ground referenced, so this '
                      'single-ended load step is not generated; the '
                      'differential step I4-BRIDGE-%s applies'
                      % (interface['id'], output_type, interface['id']))
            ctx.add_unknown('LOAD_TOPOLOGY_REQUIRES_DIFFERENTIAL', step_id,
                            detail, needed=['declared differential/floating '
                                            'load and a differential method'],
                            blocks=[step_id])
            return

    missing = []
    if interface_type == 'button':
        if not notes and logic_level is None:
            detail = ('interface %r (button) declares neither notes (pull-up '
                      'and active level) nor logic_level_v; no button step is '
                      'generated' % interface['id'])
            ctx.add_gap('BUTTON_DECLARATION_MISSING', step_id, detail,
                        needed=['declared pull-up/pull-down and active '
                                'level'], severity='blocking')
            ctx.add_unknown('BUTTON_DECLARATION_MISSING', step_id, detail,
                            needed=['declared pull-up/pull-down and active '
                                    'level'], blocks=[step_id])
            return
        if not notes:
            missing.append('declared pull-up/pull-down value and active level '
                           'in interface notes')
        if logic_level is None:
            missing.append('declared logic_level_v for the button input')
    elif interface_type == 'load_output' and output_type is None:
        missing.append('declared output_type (return/reference topology) '
                       'before the load node may be measured')
        detail = ('interface %r does not declare output_type; the '
                  'return/reference topology of the output is unknown and '
                  'must not be assumed safe' % interface['id'])
        ctx.add_unknown('OUTPUT_REFERENCE_UNKNOWN', step_id, detail,
                        needed=['declared output_type and return/reference '
                                'topology'], blocks=[step_id])

    status, reason, missing = _gated(ctx, missing)
    output_net = _signal_nets(interface)
    output_net = output_net[0] if output_net else None
    point = _testpoint_for(ctx, output_net) if output_net else None

    if interface_type == 'button':
        quantity = 'logic_level'
        title = 'Verify declared button input %s' % interface['id']
        purpose = ('Check the declared button pull-up/active level without '
                   'shorting the pins or injecting an unknown level.')
        criterion = 'qualitative'
    elif interface_type == 'led':
        quantity = 'voltage'
        title = 'Activate declared LED load %s' % interface['id']
        purpose = ('Activate the declared LED load only as declared and keep '
                   'the design target separate from the device limit.')
        criterion = 'undefined'
    else:
        quantity = 'voltage'
        title = 'Activate declared low-side load %s' % interface['id']
        purpose = ('Activate the declared load only with the declared load '
                   'connected, never as a short or at full scale by default.')
        criterion = 'undefined'

    if status == steps.STATUS_READY:
        procedure = []
        if interface_type in ('led', 'load_output'):
            procedure.append(
                'Confirm the declared load is present exactly as declared: %s. '
                'Do not fit an unknown/improvised dummy load and do not short '
                'the output to ground or to the supply rail.' % notes)
            procedure.append(
                'Do not leave the output at full scale / full load for a long '
                'time by default: the declared design target is a design '
                'intent, not the device guaranteed operating limit.')
        if interface_type == 'button':
            procedure.append(
                'Confirm the declared pull-up/pull-down and active level: %s; '
                'do not short the button pins or inject a level from an '
                'unknown source.' % (notes or 'not declared'))
            procedure.append(
                'Verify the idle level (%s V nominal from logic_level_v) and '
                'the pressed level separately; activate the button only '
                'through its declared switch.'
                % (_num(logic_level) if logic_level is not None else
                   'not declared'))
        if interface_type == 'led':
            procedure.append(
                'Observe the LED and, if a declared testpoint exists, measure '
                'its anode voltage; brightness/colour is a qualitative '
                'observation, not a current or accuracy measurement.')
        elif interface_type == 'load_output':
            procedure.append(
                'Measure the declared load-node voltage at the declared '
                'testpoint with the DMM relative to the declared ground; do '
                'not infer the load current from a full-scale assumption.')
        procedure.append(
            'Record the declared load, the design target and the observed '
            'behaviour. Device operating requirement: use only declared '
            'min/max values; typical datasheet values are not guaranteed '
            'limits.')
        measurement = None
        if point is not None:
            measurement = {
                'quantity': quantity,
                'point': point['id'],
                'reference': point.get('reference_net'),
                'range': None,
                'criterion_status': criterion,
                'basis': _basis(notes),
                'source_refs': [],
            }
        equipment = []
        dmm = _dmm_for(ctx, _rail_bound(ctx))
        if measurement is not None and dmm is not None:
            equipment.append(steps.equipment_item(
                dmm['id'], 'dc_voltage_measurement',
                settings={'mode': 'dc_voltage',
                          'range_max_v': dmm['dc_voltage_max_v']},
                verified=dmm.get('dc_voltage_resolution_v') is not None,
                detail='declared load-node voltage observation'))
        expected = ('the output/input behaves as declared for the declared '
                    'load; no numeric PASS is defined without a declared '
                    'device operating limit')
        evidence = [steps.evidence_item(
            'visual_check',
            'visual observation of %r (LED state / button state / load '
            'behaviour), with timestamp' % interface['id'])]
        if measurement is not None:
            evidence.append(steps.evidence_item(
                'meter_reading',
                'DMM reading at %s referenced to %s'
                % (point['id'], point.get('reference_net'))))
    else:
        procedure = [
            'Do not activate or load this output until the missing '
            'information is declared: %s.' % '; '.join(missing),
            'Do not short the output, do not apply full scale for a long time '
            'and do not use an unknown dummy load under any circumstances.',
        ]
        measurement = None
        equipment = []
        expected = ('no load test is valid without a declared load and '
                    'declared device operating limit')
        evidence = [steps.evidence_item(
            'visual_check',
            'visual observation of the declared load (not obtainable yet)',
            verifiable=False)]

    prerequisites = [
        steps.prerequisite_condition(
            'the output/input is enabled by the declared firmware mode; '
            'the rail and MCU checks are recorded'),
        steps.prerequisite_condition(
            'the declared load/device constraint is respected exactly; '
            'no unknown load is attached'),
    ]
    prerequisites.extend(_interface_prerequisites(ctx, interface))
    ctx.add_step(steps.make_step(
        step_id=step_id, group='I4',
        title=title,
        purpose=purpose,
        prerequisites=prerequisites,
        equipment=equipment,
        wiring={'measure_at': point['id'] if point else
                (output_net or 'not declared'),
                'reference': point.get('reference_net') if point else
                'declared ground',
                'probe': 'DMM test leads' if measurement else None,
                'notes': 'never short the output; never apply an unknown or '
                         'full-scale load by default'},
        procedure=procedure,
        measurement=measurement,
        expected_behavior=expected,
        required_evidence=evidence,
        status=status, blocked_reason=reason,
        missing_information=missing,
        source_refs=['interfaces[%s]' % interface['id']],
        notes='design_target vs device_operating_requirement are separated; '
              'no short, no unknown dummy load, no default full-scale '
              'long-duration loading',
    ))


def _dmm_for(ctx, required_v):
    candidates = [meter for meter in ctx.multimeters()
                  if meter.get('dc_voltage_max_v') is not None
                  and meter['dc_voltage_max_v'] >= required_v]
    return candidates[0] if candidates else None


def _rail_bound(ctx):
    """Highest declared rail absolute maximum (bounds an on-board node voltage)."""
    values = [domain['absolute_max_v'] for domain in ctx.domains
              if domain.get('absolute_max_v') is not None]
    return max(values) if values else 0.0


# ---------------------------------------------------------------------------
# I2C / SPI / UART / USB bus templates


def _bus_missing(interface):
    typ = interface['type']
    notes = (interface.get('notes') or '').strip()
    low = notes.lower()
    missing = []
    if interface.get('logic_level_v') is None:
        missing.append('declared logic_level_v (the bus and host adapter must '
                       'share it)')
    if not interface.get('firmware_prerequisite'):
        missing.append('declared firmware_prerequisite (image/version and '
                       'flash state)')
    if typ == 'i2c':
        if not notes:
            missing.append('declared bus premise in interface notes '
                           '(pull-up value, number of devices/masters)')
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


def _bus(ctx, interface):
    step_id = 'I4-BUS-%s' % interface['id']
    typ = interface['type']
    notes = (interface.get('notes') or '').strip()
    logic_level = interface.get('logic_level_v')
    firmware = (interface.get('firmware_prerequisite') or '').strip()
    missing = _bus_missing(interface)
    status, reason, missing = _gated(ctx, missing)
    firmware_flashing_forbidden = 'firmware_flashing' in (
        ctx.policy.get('forbidden_operations') or [])
    host = _HOST_PREMISE.get(typ, 'a host matched to the declared interface')

    prerequisites = [
        steps.prerequisite_condition(
            ('declared firmware prerequisite: %s' % firmware) if firmware
            else
            'firmware prerequisite is NOT declared: record the exact image, '
            'version and flash state before interpreting the bus',
            source_ref=('interfaces[%s].firmware_prerequisite'
                        % interface['id']) if firmware else None),
        steps.prerequisite_condition(
            ('declared host/bus premise (interface notes): %s' % notes)
            if notes else 'host prerequisite: %s' % host,
            source_ref=('interfaces[%s].notes' % interface['id'])
            if notes else None),
    ]
    if interface.get('backfeed_risk'):
        prerequisites.append(steps.prerequisite_condition(
            'declared backfeed risk: keep the host/external-supply path '
            'isolated or confirmed reverse-blocked before connecting'))
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
            'Confirm only the declared devices are on the bus: %s. Do not '
            'attach unknown modules or adapters; bus contention and unknown '
            'loads are not safe by default.'
            % (notes or 'only the declared single host and device'),
            'Confirm the declared %s V logic level and that the host adapter '
            'I/O matches it; never drive a %s V bus with a 5 V adapter.'
            % (_num(logic_level), _num(logic_level)),
        ]
        if typ == 'i2c':
            procedure.append(
                'Confirm the declared pull-ups (SDA/SCL) are fitted and that '
                'no second master or unpowered device pulls the bus down.')
        elif typ == 'spi':
            procedure.append(
                'Confirm the declared CS idle state, the number of devices and '
                'the declared termination; an undriven CS or extra device can '
                'contend on MISO.')
        elif typ == 'uart':
            procedure.append(
                'Confirm the host adapter electrical type (TTL vs RS-232) and '
                'never connect an RS-232-level adapter to TTL pins.')
        else:  # usb
            procedure.append(
                'USB D+/D- are differential: do not probe them single-ended '
                'with an earth-referenced scope; any signal-integrity '
                'measurement needs a declared differential method.')
        procedure.append(
            'Firmware prerequisite: %s. Until that firmware is flashed, the '
            'only expected result is NO business communication (no '
            'enumeration, no transaction/ACK, no serial traffic). That '
            'absence is not a failure and must be recorded as not applicable '
            'yet.' % (firmware or 'not declared'))
        procedure.append(
            'Host prerequisite: %s. Record adapter model, settings and the '
            'host log with timestamps.' % (notes or host))
        procedure.append(
            'A numeric value returned through the bus (e.g. ADC counts) does '
            'not prove range or accuracy; that is the analog-input step, not '
            'a bus PASS.')
        expected = ('before the declared firmware is flashed: no business '
                    'communication is expected and is not a failure; after an '
                    'authorized flashing, record the observed enumeration/'
                    'ACK/log')
    else:
        procedure = [
            'Do not connect the host adapter and do not claim any bus '
            'behaviour until the missing declared information is available: '
            '%s.' % '; '.join(missing),
            'Bus contention and unknown loads are not safe by default; no '
            'probable-enumeration statement may be recorded.',
        ]
        expected = ('no bus claim is valid while the level/pull-up/firmware/'
                    'host premise is missing')

    measurement = None
    equipment = []
    if typ != 'usb':
        for net in _signal_nets(interface):
            point = _testpoint_for(ctx, net)
            if point is not None:
                measurement = {
                    'quantity': 'logic_level',
                    'point': point['id'],
                    'reference': point.get('reference_net'),
                    'range': None,
                    'criterion_status': 'qualitative',
                    'basis': 'idle logic-level observation only; the declared '
                             'logic level is %s V and no bus timing/level '
                             'mask is declared' % _num(logic_level),
                    'source_refs': [],
                }
                break
    dmm = _dmm_for(ctx, _rail_bound(ctx))
    if dmm is not None:
        equipment.append(steps.equipment_item(
            dmm['id'], 'dc_voltage_measurement',
            settings={'mode': 'dc_voltage',
                      'range_max_v': dmm['dc_voltage_max_v']},
            verified=True,
            detail='idle logic-level observation only; not a protocol test'))

    if status == steps.STATUS_READY:
        if typ == 'usb':
            evidence = [steps.evidence_item(
                'host_log',
                'host USB enumeration log: device present/absent, VID/PID and '
                'descriptors, with timestamp')]
        else:
            evidence = [
                steps.evidence_item(
                    'host_log',
                    'host-side transaction/terminal log for %r, with adapter '
                    'settings and timestamp' % interface['id']),
                steps.evidence_item(
                    'serial_log',
                    'firmware serial log for %r (if the firmware is flashed)'
                    % interface['id']),
            ]
    else:
        evidence = [steps.evidence_item(
            'host_log', 'host-side bus log (not obtainable yet)',
            verifiable=False)]

    ctx.add_step(steps.make_step(
        step_id=step_id, group='I4',
        title='Check declared %s bus %s' % (typ.upper(), interface['id']),
        purpose='Verify the declared logic level, pull-up/termination and '
                'firmware/host prerequisites before drawing any bus '
                'conclusion.',
        prerequisites=prerequisites,
        equipment=equipment,
        wiring={'measure_at': 'declared bus pins',
                'reference': 'circuit ground',
                'probe': None,
                'notes': 'never probe a differential bus single-ended with an '
                         'earth-referenced scope'},
        procedure=procedure,
        measurement=measurement,
        expected_behavior=expected,
        required_evidence=evidence,
        status=status, blocked_reason=reason,
        missing_information=missing,
        source_refs=['interfaces[%s]' % interface['id']],
        notes='logic levels, pull-ups/termination, firmware and host premise '
              'are explicit; bus contention / unknown loads are not assumed '
              'safe; typical values are never used as thresholds',
    ))


# ---------------------------------------------------------------------------
# analog inputs


def _analog(ctx, interface, *, kind='input'):
    """Analog input reading, or a declared single-ended analog output."""
    is_output = kind == 'output'
    step_id = 'I4-ANALOG-%s' % interface['id']
    notes = (interface.get('notes') or '').strip()
    nets = _signal_nets(interface)
    net = nets[0] if nets else None
    point = _testpoint_for(ctx, net) if net else None
    low, high = _parse_voltage_range(notes)
    missing = []
    if not notes:
        missing.append('declared analog output target range in interface '
                       'notes' if is_output else
                       'declared analog source and range in interface notes')
    elif low is None or high is None:
        missing.append('declared numeric output target range (for example '
                       '"range 0.50..2.50 V") in interface notes'
                       if is_output else
                       'declared numeric source range (for example '
                       '"range 0.20..2.80 V") in interface notes')
    if net is None:
        missing.append('declared analog signal pin/net')
    if point is None:
        missing.append('declared testpoint on analog net %r' % net)

    status, reason, missing = _gated(ctx, missing)
    if status == steps.STATUS_READY:
        if is_output:
            procedure = [
                'Drive the output only to the declared target/range: %s. '
                'Never request full scale or the supply rail by default; only '
                'the declared output range may be applied.' % notes,
                'Measure testpoint %s (net %s) against %s with the DMM and '
                'record the firmware output setting/scale with the reading.'
                % (point['id'], net, point.get('reference_net')),
                'A reading inside the declared range is not proof of accuracy '
                'or linearity: the output setting and calibration state must '
                'be declared, and a single reading is a trend observation.',
                'Do not load the output beyond the declared load, and do not '
                'hold full scale for a long time: the declared target is a '
                'design target, not a device guaranteed operating limit.',
            ]
            measurement = {
                'quantity': 'voltage',
                'point': point['id'],
                'reference': point.get('reference_net'),
                'range': {'min': low, 'max': high, 'unit': 'V'},
                'criterion_status': 'needs_interpretation',
                'basis': _basis(notes) + ' The declared numeric range is the '
                         'output design target (%s V to %s V), not a verified '
                         'accuracy/linearity limit.'
                         % (_num(low), _num(high)),
                'source_refs': [],
            }
            expected = ('the output drives only the declared target range; '
                        'the reading is recorded, not treated as an accuracy '
                        'PASS')
            evidence = [
                steps.evidence_item(
                    'meter_reading',
                    'DMM reading at %s referenced to %s with the firmware '
                    'output setting recorded'
                    % (point['id'], point.get('reference_net'))),
                steps.evidence_item(
                    'serial_log',
                    'firmware log of the output setting/range and calibration '
                    'state, with timestamp'),
            ]
        else:
            procedure = [
                'Inspect/apply only the declared source and range: %s. Never '
                'drive or sweep the input to the supply rail or full scale by '
                'default; only the declared source range may be applied.'
                % notes,
                'Measure testpoint %s (net %s) against %s with the DMM and '
                'record the reading together with the ADC raw value and the '
                'declared attenuation/gain settings.'
                % (point['id'], net, point.get('reference_net')),
                'A numeric ADC value inside the declared range is not proof of '
                'range or accuracy: the ADC attenuation, reference and '
                'calibration must be declared. Uncalibrated readings are trend '
                'observations only.',
                'Do not treat a single reading at one temperature as proof of '
                'full-temperature accuracy or long-term drift.',
            ]
            measurement = {
                'quantity': 'voltage',
                'point': point['id'],
                'reference': point.get('reference_net'),
                'range': {'min': low, 'max': high, 'unit': 'V'},
                'criterion_status': 'needs_interpretation',
                'basis': 'the range is the declared source range from the '
                         'interface notes (%s V to %s V), not a verified ADC '
                         'accuracy limit; reading a value does not prove range '
                         'or accuracy' % (_num(low), _num(high)),
                'source_refs': [],
            }
            expected = ('the analog reading stays within the declared source '
                        'range; the reading is not a calibrated-accuracy proof')
            evidence = [
                steps.evidence_item(
                    'meter_reading',
                    'DMM reading at %s referenced to %s'
                    % (point['id'], point.get('reference_net'))),
                steps.evidence_item(
                    'serial_log',
                    'firmware log of the ADC raw value, attenuation/gain and '
                    'calibration state, with timestamp'),
            ]
        equipment = []
        dmm = _dmm_for(ctx, high)
        if dmm is not None:
            equipment.append(steps.equipment_item(
                dmm['id'], 'dc_voltage_measurement',
                settings={'mode': 'dc_voltage',
                          'range_max_v': dmm['dc_voltage_max_v']},
                verified=True,
                detail='reference reading of the declared analog node'))
        expected = ('the analog reading stays within the declared source '
                    'range; the reading is not a calibrated-accuracy proof')
        evidence = [
            steps.evidence_item(
                'meter_reading',
                'DMM reading at %s referenced to %s'
                % (point['id'], point.get('reference_net'))),
            steps.evidence_item(
                'serial_log',
                'firmware log of the ADC raw value, attenuation/gain and '
                'calibration state, with timestamp'),
        ]
    else:
        procedure = [
            'Do not apply any input and do not assume full scale or the '
            'supply rail is a valid test point until the missing declaration '
            'is available: %s.' % '; '.join(missing),
            'No analog reading may be recorded as a range/accuracy PASS.',
        ]
        measurement = None
        equipment = []
        expected = ('no analog test is valid without a declared source, '
                    'declared range and a declared testpoint')
        evidence = [steps.evidence_item(
            'meter_reading', 'DMM reading of the declared analog node (not '
            'obtainable yet)', verifiable=False)]

    prerequisites = [
        steps.prerequisite_condition(
            'the declared analog source is present and within the '
            'declared source range; nothing is driven to full scale'),
        steps.prerequisite_condition(
            'the firmware ADC attenuation/reference/calibration state is '
            'recorded before interpreting values'),
    ]
    prerequisites.extend(_interface_prerequisites(ctx, interface))
    ctx.add_step(steps.make_step(
        step_id=step_id, group='I4',
        title='Check declared analog input %s' % interface['id'],
        purpose='Test only the declared analog source and range; keep the '
                'reading separate from range/accuracy verification.',
        prerequisites=prerequisites,
        equipment=equipment,
        wiring={'measure_at': point['id'] if point else 'not declared',
                'reference': point.get('reference_net') if point else
                'declared ground',
                'probe': 'DMM test leads' if measurement else None,
                'notes': 'only the declared source/range may be applied; no '
                         'default full-scale input'},
        procedure=procedure,
        measurement=measurement,
        expected_behavior=expected,
        required_evidence=evidence,
        status=status, blocked_reason=reason,
        missing_information=missing,
        source_refs=['interfaces[%s]' % interface['id']],
        notes='reading a value is not proof of range or accuracy; the '
              'declared range is the source range, not a calibrated limit',
    ))


# ---------------------------------------------------------------------------
# bridge-tied / non-ground-referenced outputs


def _bridge(ctx, interface):
    step_id = 'I4-BRIDGE-%s' % interface['id']
    interface_type = interface['type']
    output_type = interface.get('output_type')
    notes = (interface.get('notes') or '').strip()
    nets = _signal_nets(interface)
    scope = _differential_capability(ctx)
    missing = []
    unknown = None

    if output_type == 'single_ended_ground_referenced' and \
            interface_type == 'bridge_output':
        missing.append('contradictory declaration: bridge_output with '
                       'output_type=single_ended_ground_referenced')
        unknown = ('OUTPUT_TOPOLOGY_CONTRADICTION',
                   'interface %r is declared bridge_output but output_type is '
                   'single_ended_ground_referenced; the actual reference '
                   'topology is contradictory' % interface['id'])
    elif output_type is None:
        missing.append('declared output_type (the output reference topology '
                       'is unknown)')
        unknown = ('OUTPUT_REFERENCE_UNKNOWN',
                   'interface %r of type %r does not declare output_type; a '
                   'single-ended earth-grounded measurement must not be '
                   'assumed safe' % (interface['id'], interface_type))
    elif output_type == 'floating_unknown':
        missing.append('declared output reference/common-mode range for the '
                       'floating output')
        unknown = ('FLOATING_OUTPUT_REFERENCE_UNKNOWN',
                   'interface %r declares output_type=floating_unknown; the '
                   'common-mode/reference voltage is unknown even for a '
                   'differential probe' % interface['id'])
    elif output_type in ('bridge_tied_load', 'differential'):
        if len(nets) < 2:
            missing.append('two declared output nodes (P and N) for the '
                           'differential measurement')
    else:
        missing.append('declared output_type (recognised: '
                       'bridge_tied_load / differential / '
                       'single_ended_ground_referenced / floating_unknown)')
        unknown = ('OUTPUT_REFERENCE_UNKNOWN',
                   'interface %r declares an unrecognised output topology'
                   % interface['id'])

    if output_type != 'single_ended_ground_referenced' or \
            interface_type != 'bridge_output':
        if scope is None:
            detail = ('a single-ended earth-grounded oscilloscope probe must '
                      'never be connected to either output node of %r: the '
                      'ground clip is bonded to earth and would short the '
                      'output; a differential probe or isolated channel with '
                      'declared ratings is required' % interface['id'])
            missing.append('declared differential probe or isolated channel '
                           '(single-ended earth-grounded measurement is '
                           'forbidden on this output)')
            _differential_gap(ctx)

    if unknown is not None:
        code, detail = unknown
        ctx.add_unknown(code, step_id, detail,
                        needed=['declared output_type and return/reference '
                                'topology'],
                        blocks=[step_id])

    status, reason, missing = _gated(ctx, missing)
    pair = (' and '.join(nets[:2]) if len(nets) >= 2
            else 'the declared output nodes')

    prerequisites = [
        steps.prerequisite_condition(
            'the declared load is connected between the two output nodes only; '
            'neither output node is grounded'),
        steps.prerequisite_condition(
            'a declared differential probe or isolated channel covers the '
            'output common-mode voltage; a single-ended earth-referenced '
            'ground clip may never be connected to either output node'),
        steps.prerequisite_condition(
            ('declared output premise (interface notes): %s' % notes)
            if notes else
            'no declared output amplitude/load premise: the measurement is '
            'an observation, not a numeric limit'),
    ]
    prerequisites.extend(_interface_prerequisites(ctx, interface))

    if status == steps.STATUS_READY:
        probe = (scope.get('probe') or {})
        procedure = [
            'Connect the declared differential probe across %s; do not '
            'connect an earth-referenced ground clip to either output node or '
            'to any load terminal.' % pair,
            'Verify the probe/scope common-mode voltage rating covers the '
            'declared output common-mode voltage (bound it by the highest '
            'declared rail absolute maximum) before connecting; stop if the '
            'rating is insufficient.',
            'Keep the declared load between the two output nodes only '
            '(%s); never ground one terminal of a bridge-tied load.'
            % (notes or 'floating load as declared'),
            'Do not run the output at full scale for a long time unless the '
            'device operating requirement is declared; record the '
            'differential capture with probe ratio and timebase.',
            'A differential capture is not a device-limit PASS: no numeric '
            'output limit is declared, so record it as an observation.',
        ]
        equipment = [steps.equipment_item(
            scope['id'], 'differential_voltage_measurement',
            settings={'probe': probe.get('type'),
                      'probe_bandwidth_mhz': probe.get('bandwidth_mhz'),
                      'grounding': scope.get('grounding'),
                      'mode': 'differential'},
            verified=True,
            detail='declared differential/isolated method, no earth ground '
                   'clip on the output nodes')]
        measurement = {
            'quantity': 'voltage',
            'point': '%s - %s (differential)' % (nets[0], nets[1]),
            'reference': 'differential across %s/%s; not earth ground'
                         % (nets[0], nets[1]),
            'range': None,
            'criterion_status': 'undefined',
            'basis': _basis(notes),
            'source_refs': [],
        }
        expected = ('the differential output capture is recorded; no numeric '
                    'PASS/FAIL exists without a declared output limit')
        evidence = [steps.evidence_item(
            'scope_capture',
            'differential capture across %s with probe ratio, bandwidth and '
            'timebase, no earth ground clip on either node' % pair)]
    else:
        procedure = [
            'Do NOT connect an earth-referenced oscilloscope ground clip to '
            '%s or to any non-ground node: the clip is bonded to protective '
            'earth and would short the non-ground-referenced output.'
            % pair,
            'Do NOT measure either output single-ended against earth ground; '
            'a differential probe or isolated channel is mandatory for this '
            'output.',
            'This step remains BLOCKED until a differential measurement '
            'method with declared ratings and a declared output topology is '
            'available: %s.' % '; '.join(missing),
        ]
        equipment = []
        measurement = None
        expected = ('no safe measurement exists with the declared equipment; '
                    'do not improvise a single-ended earth-grounded '
                    'connection')
        evidence = [steps.evidence_item(
            'scope_capture',
            'differential capture across %s (not obtainable yet)' % pair,
            verifiable=False)]

    ctx.add_step(steps.make_step(
        step_id=step_id, group='I4',
        title='Measure non-ground-referenced output %s differentially'
              % interface['id'],
        purpose='Forbid single-ended earth-grounded measurement of a '
                'bridge-tied/floating output and require a declared '
                'differential method.',
        prerequisites=prerequisites,
        equipment=equipment,
        wiring={'measure_at': pair + ' (differential pair)',
                'reference': 'differential; never earth ground',
                'probe': 'differential probe' if scope else
                         'not declared (differential required)',
                'notes': 'earth-referenced ground clip may never touch either '
                         'output node'},
        procedure=procedure,
        measurement=measurement,
        expected_behavior=expected,
        required_evidence=evidence,
        status=status, blocked_reason=reason,
        missing_information=missing,
        source_refs=['interfaces[%s]' % interface['id']],
        notes='single-ended earth-grounded probe is forbidden; differential '
              'method required; BTL/load terminals are never grounded',
    ))
