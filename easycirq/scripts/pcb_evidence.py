#!/usr/bin/env python3
"""Deterministic parsers/normalizers for PCB acceptance evidence.

``pcb_gate.py`` and ``pcb_case.py`` share these functions so a check cannot be
"passed" by one tool with a different interpretation than the other.  Nothing
here talks to EDA; all inputs are already captured JSON or a manifest.

Design rules:
  * missing, unreadable or contradictory evidence is ``blocked``/``incomplete``,
    never pass;
  * absent, explicitly unconnected, empty and measured are different states;
  * a warning is not an error, but every warning needs a disposition;
  * invalid field types produce a structured diagnostic instead of being
    silently coerced to zero;
  * net-path never covers copper pours; callers must say so in the report;
  * component/pin comparisons are exact for designator+pad number.  Combination
    pads need an explicit alias map; an unmapped pin is reported, not guessed.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re

from pcb_cli import load_json, sha256_file

SCH_PCB_SCHEMA = 'design-engine-pcb-sch-pcb-compare/v1'
WARN_DISPOSITION_SCHEMA = 'design-engine-pcb-warn-disposition/v1'
CHECK_SCHEMA = 'design-engine-pcb-check/v1'
DRC_SCHEMA = 'design-engine-pcb-drc/v1'
LINT_SCHEMA = 'design-engine-pcb-lint/v1'
NETPATH_SCHEMA = 'design-engine-pcb-netpath/v1'
PARSER_VERSION = 2

_LEVELS = {'ERROR', 'WARN', 'INFO'}
_LEVEL_ALIASES = {
    'ERROR': 'ERROR', 'ERR': 'ERROR', 'CRITICAL': 'ERROR', 'FATAL': 'ERROR',
    'SEVERE': 'ERROR',
    'WARN': 'WARN', 'WARNING': 'WARN', 'MINOR': 'WARN',
    'INFO': 'INFO', 'INFORMATION': 'INFO', 'NOTE': 'INFO', 'HINT': 'INFO',
}


_VOLATILE_KEYS = {
    'capturedAt', 'captured_at', 'generated_at', 'created_at', 'createdAt',
    'savedAt', 'completedAt', 'started_at', 'ended_at', 'produced_at',
    'mtime', 'storedAt', 'stdout', 'stderr', 'argv',
}


def semantic_sha256(value):
    """Hash the semantic content, excluding capture timestamps and paths.

    The raw file hash proves the exact bytes; this hash is for comparing two
    captures of the same design where timestamps or local paths differ.  It
    keeps array order (some arrays, such as wire point lists, are ordered) and
    does not merge values.
    """
    def clean(item):
        if isinstance(item, dict):
            result = {}
            for key, value in item.items():
                if key in _VOLATILE_KEYS:
                    continue
                # A file path is environment-specific; a geometric/net path
                # (a list or a non-path string) stays in the semantic hash.
                if key == 'path' and isinstance(value, str) and (
                        '/' in value or '\\' in value or
                        value.lower().endswith(('.json', '.png', '.svg',
                                                '.csv', '.epro2'))):
                    continue
                result[key] = clean(value)
            return result
        if isinstance(item, list):
            return [clean(value) for value in item]
        return item

    text = json.dumps(clean(value), ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False)
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _text(value):
    if value is None:
        return ''
    return str(value).strip()


def _net(value):
    value = _text(value)
    return value or None


def _as_envelope(value):
    if isinstance(value, dict) and isinstance(value.get('result'), dict):
        return value['result']
    return value if isinstance(value, dict) else {}


def _envelope_meta(value):
    """Return ``(payload, meta)`` and preserve a contradictory outer ``ok``.

    The CLI can print ``{"ok": false, "result": {...}}`` after a partial
    failure.  The result is still useful evidence, but it must not be treated
    as a successful measurement without saying so.
    """
    meta = {'envelope_ok': None, 'contradictory_envelope': False,
            'diagnostics': []}
    if not isinstance(value, dict):
        return {}, meta
    raw_ok = value.get('ok')
    if isinstance(raw_ok, bool):
        meta['envelope_ok'] = raw_ok
        if raw_ok is False:
            meta['contradictory_envelope'] = True
            meta['diagnostics'].append({
                'field': 'ok',
                'issue': 'payload reports ok=false even though measurement '
                         'fields may be present',
            })
    elif raw_ok is not None:
        meta['diagnostics'].append(
            _diagnostic('ok', 'boolean required', raw_ok))
    result = value.get('result')
    if isinstance(result, dict):
        if meta['envelope_ok'] is False:
            meta['contradictory_envelope'] = True
        return result, meta
    return value, meta


def _diagnostic(field, issue, value=None, expected=None):
    item = {'field': field, 'issue': issue}
    if value is not None:
        item['value'] = value
    if expected is not None:
        item['expected'] = expected
    return item


def _number(value):
    """Return ``(ok, float_value, diagnostic)`` for a finite JSON number."""
    if isinstance(value, bool):
        return False, None, _diagnostic('value', 'boolean is not a number', value)
    if not isinstance(value, (int, float)):
        return False, None, _diagnostic('value', 'finite number required', value)
    if not math.isfinite(float(value)):
        return False, None, _diagnostic('value', 'NaN/Infinity is not a number', value)
    return True, float(value), None


def _nonnegative_int(value):
    if isinstance(value, bool):
        return False, None, _diagnostic('value', 'boolean is not an integer', value)
    if isinstance(value, float):
        if not math.isfinite(value) or not value.is_integer():
            return False, None, _diagnostic('value', 'integer required', value)
        value = int(value)
    if not isinstance(value, int):
        return False, None, _diagnostic('value', 'integer required', value)
    if value < 0:
        return False, None, _diagnostic('value', 'nonnegative integer required', value)
    return True, value, None


def _normalized_level(finding):
    if not isinstance(finding, dict):
        return None
    raw = finding.get('level')
    if raw is None:
        raw = finding.get('severity')
    if raw is None:
        return None
    return _LEVEL_ALIASES.get(_text(raw).upper())


def _finding_type(finding):
    for key in ('type', 'code', 'rule', 'category'):
        value = _text(finding.get(key))
        if value:
            return value
    return 'unknown'


# ---------------------------------------------------------------------------
# schematic <-> PCB comparison
# ---------------------------------------------------------------------------


def _component_ref(component):
    return _text(component.get('ref') or component.get('designator') or
                 component.get('componentName'))


def _pin_number(pin):
    return _text(pin.get('number') or pin.get('pinNumber') or pin.get('name'))


def _pin_rec(pin, *, net=None, net_measured=True):
    return {
        'number': _pin_number(pin),
        'net': _net(net if net is not None else pin.get('net')),
        'net_measured': bool(net_measured),
        'nc': pin.get('nc') if isinstance(pin.get('nc'), bool) else None,
        'raw': pin,
    }


def _sch_components_detailed(sch):
    """Return ``(components, diagnostics, coverage)`` for supported SCH shapes.

    Duplicate designators, duplicate pin numbers and conflicting connection
    records are reported, not overwritten.  An envelope ``ok=false`` with a
    result object is preserved as a contradiction.
    """
    data, meta = _envelope_meta(sch)
    diagnostics = list(meta['diagnostics'])
    coverage = {'shape': 'unknown', 'raw_components': 0, 'usable_components': 0,
                'excluded_components': 0}
    components = data.get('components')
    if not isinstance(components, list):
        diagnostics.append(_diagnostic('components', 'list required',
                                       components))
        return {}, diagnostics, coverage

    connections = data.get('connections')
    nets = data.get('nets')
    per_pin = {}
    # ``sch read`` returns a ``nets`` summary (net -> pin list) without a
    # ``connections`` table.  In that shape the component pin records already
    # carry the net name; the summary must not be mistaken for a broken
    # connection table.
    if isinstance(connections, list):
        coverage['shape'] = 'components+connections+nets'
        net_names = {}
        if isinstance(nets, list):
            for index, item in enumerate(nets):
                if not isinstance(item, dict):
                    diagnostics.append(_diagnostic(
                        'nets[%d]' % index, 'object required', item))
                    continue
                net_id = item.get('id')
                name = _text(item.get('name'))
                if net_id is None:
                    diagnostics.append(_diagnostic(
                        'nets[%d]' % index, 'id required', item))
                    continue
                if not name:
                    diagnostics.append(_diagnostic(
                        'nets[%d].name' % index, 'net name is missing', item))
                net_names[net_id] = name or None
        elif nets is not None:
            diagnostics.append(_diagnostic('nets', 'list required', nets))

        if isinstance(connections, list):
            for index, connection in enumerate(connections):
                if not isinstance(connection, dict):
                    diagnostics.append(_diagnostic(
                        'connections[%d]' % index, 'object required',
                        connection))
                    continue
                component_id = connection.get('componentId')
                number = _text(connection.get('pinNumber'))
                net_id = connection.get('netId')
                if component_id is None or not number:
                    diagnostics.append(_diagnostic(
                        'connections[%d]' % index,
                        'componentId and pinNumber required', connection))
                    continue
                if net_id not in net_names:
                    diagnostics.append(_diagnostic(
                        'connections[%d].netId' % index,
                        'net id is absent from nets; net name is unknown',
                        net_id))
                    name = None
                    measured = False
                else:
                    name = net_names[net_id]
                    measured = name is not None
                key = (component_id, number)
                if key in per_pin and per_pin[key]['net'] != _net(name):
                    diagnostics.append(_diagnostic(
                        'connections[%d]' % index,
                        'conflicting connections for the same pin',
                        {'componentId': component_id, 'pinNumber': number}))
                per_pin[key] = {'net': _net(name), 'net_measured': measured,
                                'count': per_pin.get(key, {}).get('count', 0) + 1}
        elif connections is not None:
            diagnostics.append(_diagnostic('connections', 'list required',
                                           connections))

    by_ref = {}
    duplicate_refs = {}
    for index, component in enumerate(components):
        coverage['raw_components'] += 1
        if not isinstance(component, dict):
            diagnostics.append(_diagnostic('components[%d]' % index,
                                           'object required', component))
            continue
        ref = _component_ref(component)
        if not ref:
            diagnostics.append(_diagnostic(
                'components[%d]' % index,
                'ref/designator required; object is not comparable',
                component.get('id')))
            continue
        pins = {}
        pin_duplicates = []
        raw_pins = component.get('pins')
        if raw_pins is not None and not isinstance(raw_pins, list):
            diagnostics.append(_diagnostic(
                'components[%s].pins' % ref, 'list required', raw_pins))
            raw_pins = []
        for pin_index, pin in enumerate(raw_pins or []):
            if not isinstance(pin, dict):
                diagnostics.append(_diagnostic(
                    'components[%s].pins[%d]' % (ref, pin_index),
                    'object required', pin))
                continue
            number = _pin_number(pin)
            if not number:
                diagnostics.append(_diagnostic(
                    'components[%s].pins[%d]' % (ref, pin_index),
                    'pin number/name required', pin))
                continue
            if number in pins:
                pin_duplicates.append(number)
                diagnostics.append(_diagnostic(
                    'components[%s].pins[%s]' % (ref, number),
                    'duplicate pin number; the last value was not allowed to '
                    'replace the first', pin))
                continue
            pins[number] = _pin_rec(pin)
        # Connection rows are authoritative for pin nets in this shape.
        component_id = component.get('id')
        for (cid, number), record in per_pin.items():
            if cid != component_id:
                continue
            pin = pins.get(number)
            if pin is None:
                pin = {'number': number, 'net': None, 'net_measured': False,
                       'nc': None, 'raw': None}
                pins[number] = pin
            pin['net'] = record['net']
            pin['net_measured'] = record['net_measured']
        record = {
            'ref': ref,
            'id': component_id,
            'pins': pins,
            'pin_duplicates': sorted(set(pin_duplicates)),
            'raw': component,
        }
        if ref in by_ref:
            duplicate_refs.setdefault(ref, [by_ref[ref]['raw']]).append(component)
            diagnostics.append(_diagnostic(
                'components[%s]' % ref,
                'duplicate designator; the first record was kept and the '
                'duplicate is reported', component))
            continue
        by_ref[ref] = record
    coverage['usable_components'] = len(by_ref)
    coverage['duplicate_designators'] = sorted(duplicate_refs)
    coverage['duplicate_pins'] = {
        ref: item['pin_duplicates'] for ref, item in by_ref.items()
        if item['pin_duplicates']
    }
    return by_ref, diagnostics, coverage


def _pcb_components_detailed(dump):
    data, meta = _envelope_meta(dump)
    diagnostics = list(meta['diagnostics'])
    coverage = {'shape': 'components', 'raw_components': 0,
                'usable_components': 0}
    components = data.get('components')
    if not isinstance(components, list):
        diagnostics.append(_diagnostic('components', 'list required',
                                       components))
        return {}, diagnostics, coverage
    by_ref = {}
    duplicate_refs = {}
    for index, component in enumerate(components):
        coverage['raw_components'] += 1
        if not isinstance(component, dict):
            diagnostics.append(_diagnostic('components[%d]' % index,
                                           'object required', component))
            continue
        ref = _text(component.get('designator') or component.get('ref'))
        if not ref:
            diagnostics.append(_diagnostic(
                'components[%d]' % index,
                'designator required; object is not comparable',
                component.get('primitiveId')))
            continue
        pads = {}
        pad_duplicates = []
        raw_pads = component.get('pads')
        if raw_pads is not None and not isinstance(raw_pads, list):
            diagnostics.append(_diagnostic(
                'components[%s].pads' % ref, 'list required', raw_pads))
            raw_pads = []
        for pad_index, pad in enumerate(raw_pads or []):
            if not isinstance(pad, dict):
                diagnostics.append(_diagnostic(
                    'components[%s].pads[%d]' % (ref, pad_index),
                    'object required', pad))
                continue
            number = _text(pad.get('padNumber') or pad.get('number'))
            if not number:
                diagnostics.append(_diagnostic(
                    'components[%s].pads[%d]' % (ref, pad_index),
                    'padNumber/number required', pad))
                continue
            if number in pads:
                pad_duplicates.append(number)
                existing = pads[number]
                existing['pads'].append(pad)
                existing['nets'].add(_net(pad.get('net')))
                diagnostics.append(_diagnostic(
                    'components[%s].pads[%s]' % (ref, number),
                    'duplicate pad number (e.g. a thermal/array pad); every '
                    'pad net is retained and the comparison requires them to '
                    'agree', pad))
                continue
            pads[number] = {'number': number, 'net': _net(pad.get('net')),
                            'nets': {_net(pad.get('net'))},
                            'pads': [pad], 'raw': pad}
        for number, record in pads.items():
            nets = record['nets']
            if len(nets) == 1:
                record['net'] = next(iter(nets))
                record['ambiguous'] = False
            else:
                record['ambiguous'] = True
                record['net'] = sorted(nets, key=lambda value: (value is None,
                                                                value or ''))
        record = {
            'ref': ref,
            'pins': pads,
            'pad_duplicates': sorted(set(pad_duplicates)),
            'raw': component,
        }
        if ref in by_ref:
            duplicate_refs.setdefault(ref, [by_ref[ref]['raw']]).append(component)
            diagnostics.append(_diagnostic(
                'components[%s]' % ref,
                'duplicate designator; the first record was kept and the '
                'duplicate is reported', component))
            continue
        by_ref[ref] = record
    coverage['usable_components'] = len(by_ref)
    coverage['duplicate_designators'] = sorted(duplicate_refs)
    coverage['duplicate_pads'] = {
        ref: item['pad_duplicates'] for ref, item in by_ref.items()
        if item['pad_duplicates']
    }
    return by_ref, diagnostics, coverage


def _identity_fields(record, kind):
    raw = record.get('raw') or {}
    fields = {}
    for key in ('uniqueId', 'uniqueID'):
        value = _text(raw.get(key))
        if value:
            fields['uniqueId'] = value
            break
    component = raw.get('component')
    if isinstance(component, dict):
        value = _text(component.get('uuid'))
        if value:
            fields['componentUuid'] = value
    device = raw.get('device')
    if isinstance(device, dict):
        value = _text(device.get('uuid') or device.get('deviceUuid'))
        if value:
            fields['deviceUuid'] = value
        name = _text(device.get('name'))
        if name and not name.startswith('={') and not name.endswith('}'):
            fields['deviceName'] = name
    elif isinstance(device, str):
        value = _text(device)
        if value:
            fields['deviceName'] = value
    symbol = raw.get('symbol')
    if isinstance(symbol, dict):
        value = _text(symbol.get('uuid'))
        if value:
            fields['symbolUuid'] = value
    for key in ('footprint', 'Footprint'):
        value = raw.get(key)
        if isinstance(value, dict):
            value = value.get('name') or value.get('uuid')
        value = _text(value)
        if value:
            fields['footprint'] = value
            break
    properties = raw.get('otherProperty')
    if isinstance(properties, dict):
        value = _text(properties.get('Footprint'))
        if value:
            fields.setdefault('footprint', value)
        for key in ('Manufacturer Part', 'Supplier Part', 'LCSC Part Name',
                    'Value'):
            text_value = _text(properties.get(key))
            if text_value:
                fields['bom.' + key] = text_value
    if kind == 'pcb':
        for key in ('value', 'name'):
            value = _text(raw.get(key))
            if value and not value.startswith('={'):
                fields.setdefault('pcb.' + key, value)
    return fields


def _compare_identity(sch_map, pcb_map):
    checks, mismatches, not_checked = [], [], []
    for ref in sorted(set(sch_map) & set(pcb_map)):
        sch = _identity_fields(sch_map[ref], 'sch')
        pcb = _identity_fields(pcb_map[ref], 'pcb')
        comparable = sorted(set(sch) & set(pcb))
        if not comparable:
            not_checked.append({'designator': ref,
                                'reason': 'no identity field is present on both '
                                          'sides (uniqueId/device/footprint/BOM)'})
            continue
        for field in comparable:
            checks.append({'designator': ref, 'field': field,
                           'schematic': sch[field], 'pcb': pcb[field],
                           'status': 'match' if sch[field] == pcb[field]
                           else 'mismatch'})
            if sch[field] != pcb[field]:
                mismatches.append({
                    'designator': ref, 'kind': 'identity_mismatch',
                    'field': field, 'schematic': sch[field],
                    'pcb': pcb[field],
                })
    return checks, mismatches, not_checked


def _partition(entries, canonical=None):
    """Return ``(pin -> group frozenset, net -> members)`` for one side.

    ``canonical`` maps ``(ref, number)`` to one or more comparison keys.  For
    the PCB side it maps alias pad numbers back to the schematic pin so a
    combination pad is one member, not an artificial partition difference.
    """
    groups = {}
    for ref, record in entries.items():
        for number, pin in record['pins'].items():
            nets = pin.get('nets')
            if nets is None:
                nets = {pin.get('net')}
            targets = canonical(ref, number) if canonical else [number]
            for net in nets:
                if net is None:
                    continue
                for target in targets:
                    groups.setdefault(net, set()).add('%s.%s' % (ref, target))
    pin_group = {}
    for net, members in groups.items():
        frozen = frozenset(members)
        for member in members:
            pin_group[member] = frozen
    return pin_group, groups


def _alias_partition_keys(alias_map):
    """Return ``(pin_key, pad_key)`` canonical keys for alias partitions.

    A combination pad can be one-to-many (one schematic pin -> several pads)
    or many-to-one (several schematic pins -> one pad).  Both sides collapse
    to the same bracketed target set, so a legal alias never creates a fake
    partition difference.
    """
    pin_keys, pad_keys = {}, {}
    for ref, pins in (alias_map or {}).items():
        for pin, targets in (pins or {}).items():
            key = '[%s]' % ','.join(sorted(targets))
            pin_keys[(ref, pin)] = key
            for target in targets:
                pad_keys.setdefault((ref, target), set()).add(key)
    return pin_keys, {key: sorted(values)[0]
                      for key, values in pad_keys.items()}


def compare_sch_pcb(sch, dump, *, pin_aliases=None, ignore_designators=None):
    """Compare schematic pin nets with PCB pad nets.

    ``pin_aliases`` is ``{designator: {sch_pin: [pcb_pad, ...]}}`` for
    combination pads.  Without an alias, one schematic pin must match one PCB
    pad with the same number; an unmapped schematic pin is a mismatch kind
    ``unmapped_pin`` instead of being silently skipped.

    The result separates four things that were previously conflated:

    * component presence (missing/extra/duplicate designator);
    * pin presence (missing pad / extra pad / duplicate pin or pad);
    * electrical grouping (the net partition over pins) — this is the
      connectivity fact;
    * net names (a rename with an unchanged partition is reported separately
      and does not by itself fail the comparison).

    An empty side, a side with no usable pins, or an ignore list that removes
    every object is ``not_comparable``, never ``match``.
    """
    sch_map, sch_diagnostics, sch_coverage = _sch_components_detailed(sch)
    pcb_map, pcb_diagnostics, pcb_coverage = _pcb_components_detailed(dump)
    diagnostics = sch_diagnostics + pcb_diagnostics
    alias_map = {}
    if pin_aliases is not None:
        if not isinstance(pin_aliases, dict):
            diagnostics.append(_diagnostic('pin_aliases', 'object required',
                                           pin_aliases))
        else:
            for ref, pins in pin_aliases.items():
                if not isinstance(pins, dict):
                    diagnostics.append(_diagnostic(
                        'pin_aliases[%s]' % ref, 'object required', pins))
                    continue
                normalized = {}
                for pin, targets in pins.items():
                    if not isinstance(targets, list) or not targets or any(
                            not _text(target) for target in targets):
                        diagnostics.append(_diagnostic(
                            'pin_aliases[%s][%s]' % (ref, pin),
                            'nonempty list of pad numbers required', targets))
                        continue
                    normalized[_text(pin)] = [_text(target) for target in targets]
                alias_map[_text(ref)] = normalized

    raw_ignored = ignore_designators or []
    if not isinstance(raw_ignored, (list, tuple)) or any(
            not isinstance(item, str) for item in raw_ignored):
        diagnostics.append(_diagnostic('ignore_designators',
                                       'list of designator strings required',
                                       raw_ignored))
        raw_ignored = []
    ignored = sorted({_text(item) for item in raw_ignored if _text(item)})
    excluded_present = [ref for ref in ignored if ref in sch_map or ref in pcb_map]
    for ref in ignored:
        if ref not in sch_map and ref not in pcb_map:
            diagnostics.append(_diagnostic(
                'ignore_designators', 'designator is absent from both sides',
                ref))

    original_sch_refs = set(sch_map)
    original_pcb_refs = set(pcb_map)
    for ref in ignored:
        sch_map.pop(ref, None)
        pcb_map.pop(ref, None)
    all_excluded = (bool(ignored) and not sch_map and not pcb_map and
                    bool(original_sch_refs or original_pcb_refs))

    component_mismatches = []
    for ref in sorted(set(sch_map) - set(pcb_map)):
        component_mismatches.append({'designator': ref,
                                     'kind': 'missing_component',
                                     'message': 'schematic part has no PCB component'})
    for ref in sorted(set(pcb_map) - set(sch_map)):
        component_mismatches.append({'designator': ref,
                                     'kind': 'extra_component',
                                     'message': 'PCB component has no schematic part'})
    for ref in sorted(set(sch_coverage.get('duplicate_designators') or []) &
                      set(pcb_map)):
        component_mismatches.append({
            'designator': ref, 'kind': 'duplicate_sch_designator',
            'message': 'schematic contains more than one object with this '
                       'designator; identity is ambiguous'})
    for ref in sorted(set(pcb_coverage.get('duplicate_designators') or []) &
                      set(sch_map)):
        component_mismatches.append({
            'designator': ref, 'kind': 'duplicate_pcb_designator',
            'message': 'PCB contains more than one object with this '
                       'designator; identity is ambiguous'})
    for ref, record in sorted(sch_map.items()):
        if record.get('pin_duplicates'):
            component_mismatches.append({
                'designator': ref, 'kind': 'duplicate_pin',
                'pins': record['pin_duplicates'],
                'message': 'schematic has duplicate pin numbers; a single '
                           'pin-to-pad mapping cannot be proven'})

    rows = []
    for ref in sorted(set(sch_map) & set(pcb_map)):
        schematic = sch_map[ref]['pins']
        board = pcb_map[ref]['pins']
        ref_aliases = alias_map.get(ref) or {}
        used_pads = set()
        for pin in sorted(schematic):
            expected = schematic[pin].get('net')
            expected_measured = schematic[pin].get('net_measured', True)
            targets = ref_aliases.get(pin)
            if targets:
                used_pads.update(targets)
                target_states = []
                for target in targets:
                    if target not in board:
                        target_states.append({'pad': target, 'exists': False,
                                              'net': None, 'ambiguous': False})
                    else:
                        pad_record = board[target]
                        target_states.append({
                            'pad': target, 'exists': True,
                            'net': pad_record.get('net'),
                            'ambiguous': bool(pad_record.get('ambiguous')),
                        })
                missing_targets = [item['pad'] for item in target_states
                                   if not item['exists']]
                ambiguous_targets = [item['pad'] for item in target_states
                                     if item.get('ambiguous')]
                nets = {item['net'] for item in target_states
                        if item['exists'] and not item.get('ambiguous')}
                actual = None
                if not missing_targets and not ambiguous_targets:
                    actual = next(iter(nets)) if len(nets) == 1 else sorted(
                        nets, key=lambda value: (value is None, value or ''))
                row = {
                    'designator': ref, 'pin': pin,
                    'pcb_pads': list(targets),
                    'schematic_net': expected,
                    'pcb_net': actual,
                    'targets': target_states,
                }
                if not expected_measured:
                    row['status'] = 'mismatch'
                    row['kind'] = 'schematic_net_unknown'
                elif missing_targets:
                    row['status'] = 'mismatch'
                    row['kind'] = 'alias_target_missing'
                    row['missing_pads'] = missing_targets
                elif ambiguous_targets:
                    row['status'] = 'mismatch'
                    row['kind'] = 'ambiguous_alias_target_net'
                    row['ambiguous_pads'] = ambiguous_targets
                    row['note'] = (
                        'the target pad number has several pads with different '
                        'nets; a single-net comparison is not possible')
                elif expected is None and all(item['net'] is None
                                              for item in target_states):
                    row['status'] = 'match'
                    row['kind'] = 'unconnected'
                    row['note'] = ('both sides have no net; this is not an NC '
                                   'proof')
                elif all(item['exists'] and item['net'] == expected
                         for item in target_states):
                    row['status'] = 'match'
                else:
                    row['status'] = 'mismatch'
                    row['kind'] = ('net_missing_on_pcb'
                                   if expected is not None and
                                   all(item['net'] is None for item in target_states)
                                   else 'net_name_mismatch')
                rows.append(row)
                continue
            if pin not in board:
                rows.append({
                    'designator': ref, 'pin': pin, 'schematic_net': expected,
                    'pcb_net': None, 'status': 'mismatch',
                    'kind': 'missing_pad',
                    'message': 'schematic pin has no PCB pad with this number',
                })
                continue
            pad_record = board[pin]
            actual = pad_record.get('net')
            row = {'designator': ref, 'pin': pin, 'schematic_net': expected,
                   'pcb_net': actual}
            if pad_record.get('ambiguous'):
                row.update({
                    'status': 'mismatch',
                    'kind': 'ambiguous_pad_net',
                    'pcb_nets': pad_record.get('nets'),
                    'note': 'the pad number has several pads with different '
                            'nets; a single-net comparison is not possible',
                })
            elif not expected_measured:
                row.update({'status': 'mismatch',
                            'kind': 'schematic_net_unknown',
                            'message': 'schematic net name is unknown; absence '
                                       'is not a measured unconnected pin'})
            elif expected is None and actual is None:
                row.update({'status': 'match', 'kind': 'unconnected',
                            'note': 'both sides have no net; this is not an NC proof'})
            elif expected is None:
                row.update({'status': 'mismatch',
                            'kind': 'unexpected_pcb_net',
                            'message': 'schematic pin is unconnected but the PCB '
                                       'pad carries a net'})
            elif actual is None:
                row.update({'status': 'mismatch',
                            'kind': 'net_missing_on_pcb',
                            'message': 'PCB pad has no measured net'})
            elif expected == actual:
                row['status'] = 'match'
            else:
                row.update({'status': 'mismatch',
                            'kind': 'net_name_mismatch'})
            rows.append(row)
        for pin in sorted(set(board) - set(schematic) - used_pads):
            rows.append({
                'designator': ref, 'pin': pin, 'schematic_net': None,
                'pcb_net': board[pin].get('net'), 'status': 'mismatch',
                'kind': 'extra_pad',
                'message': 'PCB pad has no schematic pin with this number',
            })

    # Connectivity partition: compare grouping, then names separately.
    pin_keys, pad_keys = _alias_partition_keys(alias_map)

    def canonical_sch(ref, number):
        return [pin_keys.get((ref, number), number)]

    def canonical_pad(ref, number):
        return [pad_keys.get((ref, number), number)]

    sch_pin_group, sch_groups = _partition(sch_map, canonical_sch)
    pcb_pin_group, pcb_groups = _partition(pcb_map, canonical_pad)
    pcb_normalized = pcb_pin_group
    partition_same = set(sch_pin_group.values()) == set(pcb_normalized.values())
    if not partition_same:
        diagnostics.append(_diagnostic(
            'net_partition', 'pins are grouped into different nets on the two '
                             'sides', {
                                 'schematic': sorted(
                                     [sorted(group) for group in
                                      set(sch_pin_group.values())])[:20],
                                 'pcb': sorted(
                                     [sorted(group) for group in
                                      set(pcb_normalized.values())])[:20],
                             }))

    # A per-pin net-name difference with an unchanged net membership is a
    # rename, not a connectivity failure.  Report it and keep the overall
    # status distinct so a gate can decide how to treat it.
    name_changes = []
    for row in rows:
        if row.get('status') != 'mismatch' or row.get('kind') != 'net_name_mismatch':
            continue
        key = '%s.%s' % (row['designator'],
                         canonical_sch(row['designator'], row['pin'])[0])
        if sch_pin_group.get(key) and sch_pin_group.get(key) == pcb_normalized.get(key):
            row['status'] = 'match'
            row['kind'] = 'net_name_only'
            row['name_changed'] = True
            name_changes.append({
                'designator': row['designator'], 'pin': row['pin'],
                'schematic_net': row.get('schematic_net'),
                'pcb_net': row.get('pcb_net'),
                'pins': sorted(sch_pin_group[key]),
            })
    # The same rename can appear on several pins; collapse to one group report.
    collapsed = {}
    for item in name_changes:
        key = tuple(sorted(item['pins']))
        collapsed.setdefault(key, {
            'pins': item['pins'],
            'schematic_net': item['schematic_net'],
            'pcb_net': item['pcb_net'],
        })
    name_changes = sorted(collapsed.values(), key=lambda item: item['pins'])

    identity_checks, identity_mismatches, identity_not_checked = _compare_identity(
        sch_map, pcb_map)
    component_mismatches.extend(identity_mismatches)

    bad_rows = [row for row in rows if row.get('status') != 'match']
    mismatches = component_mismatches + bad_rows
    compared = len(set(sch_map) & set(pcb_map))
    coverage = {
        'schematic_components': len(sch_map),
        'pcb_components': len(pcb_map),
        'compared_components': compared,
        'excluded_designators': excluded_present,
        'ignored_designators_supplied': ignored,
        'pins': len(rows),
        'identity_fields_compared': len(identity_checks),
        'identity_fields_not_checked': len(identity_not_checked),
    }

    if all_excluded:
        status = 'not_comparable'
        reason = ('all %d object(s) were excluded by ignore_designators; this '
                  'is not a complete verification' % len(ignored))
    elif not sch_map or not pcb_map:
        status = 'not_comparable'
        reason = ('schematic side has no usable component'
                  if not sch_map else 'PCB side has no usable component')
    elif not sch_map.keys() & pcb_map.keys():
        status = 'not_comparable'
        reason = 'the two sides share no designator'
    elif compared == 0:
        status = 'not_comparable'
        reason = 'no component was compared'
    elif mismatches:
        status = 'mismatch'
        reason = None
    elif name_changes:
        status = 'match_with_renames'
        reason = None
    else:
        status = 'match'
        reason = None

    return {
        'schema': SCH_PCB_SCHEMA,
        'parser_version': PARSER_VERSION,
        'status': status,
        'reason': reason,
        'schematic_components': len(sch_map),
        'pcb_components': len(pcb_map),
        'pins': len(rows),
        'component_mismatches': component_mismatches,
        'mismatches': mismatches,
        'rows': rows,
        'name_changes': name_changes,
        'partition_match': partition_same,
        'identity': {
            'checks': identity_checks,
            'mismatches': identity_mismatches,
            'not_checked': identity_not_checked,
        },
        'excluded_designators': excluded_present,
        'ignore_designators': ignored,
        'coverage': coverage,
        'diagnostics': diagnostics,
        'sch_shape': sch_coverage.get('shape'),
        'not_checked': (
            [] if identity_checks else
            ['instance UUID / library identity / footprint / BOM: no field '
             'was present on both sides to compare']
        ),
        'note': 'designator+pad-number comparison; combination pads require '
                'pin_aliases; net renames with an unchanged partition are '
                'reported separately',
    }


# ---------------------------------------------------------------------------
# pcb check
# ---------------------------------------------------------------------------


def _summary_counts(summary, diagnostics, prefix='summary'):
    values = {}
    for key in ('errors', 'warnings', 'infos', 'total'):
        if key not in summary:
            continue
        ok, value, issue = _nonnegative_int(summary[key])
        if not ok:
            issue['field'] = '%s.%s' % (prefix, key)
            diagnostics.append(issue)
            continue
        values[key] = value
    return values


def parse_pcb_check(payload):
    """Normalize ``easycirq pcb check --json`` (envelope or result).

    Summary counters are cross-checked against itemized findings.  A summary
    of ``errors=0`` with an ERROR finding is not clean; it is an inconsistent
    receipt and fails closed.
    """
    data, envelope = _envelope_meta(payload)
    diagnostics = list(envelope['diagnostics'])
    raw_findings = data.get('findings')
    if raw_findings is not None and not isinstance(raw_findings, list):
        diagnostics.append(_diagnostic('findings', 'list required', raw_findings))
        raw_findings = None
    findings = [item for item in raw_findings or [] if isinstance(item, dict)]
    for index, item in enumerate(raw_findings or []):
        if not isinstance(item, dict):
            diagnostics.append(_diagnostic('findings[%d]' % index,
                                           'object required', item))
    summary = data.get('summary')
    if summary is not None and not isinstance(summary, dict):
        diagnostics.append(_diagnostic('summary', 'object required', summary))
        summary = {}
    summary = summary or {}

    levels = {'ERROR': [], 'WARN': [], 'INFO': [], 'UNKNOWN': []}
    level_conflicts = []
    for finding in findings:
        level = _normalized_level(finding)
        if level is None:
            levels['UNKNOWN'].append(finding)
            continue
        levels[level].append(finding)
        raw_level = finding.get('level')
        raw_severity = finding.get('severity')
        if raw_level is not None and raw_severity is not None:
            left = _LEVEL_ALIASES.get(_text(raw_level).upper())
            right = _LEVEL_ALIASES.get(_text(raw_severity).upper())
            if left and right and left != right:
                level_conflicts.append({
                    'type': _finding_type(finding),
                    'level': raw_level, 'severity': raw_severity,
                })

    counts = _summary_counts(summary, diagnostics)
    summary_keys_measured = ('errors' in counts and 'warnings' in counts)
    # An empty findings array with no summary is an absent receipt, not a
    # clean measurement.
    findings_measured = bool(findings) or (raw_findings is not None and
                                           bool(summary))
    measured = bool(summary_keys_measured or findings_measured)

    itemized = {key: len(levels[key]) for key in levels}
    errors = max(counts.get('errors', 0), itemized['ERROR'])
    warnings = max(counts.get('warnings', 0), itemized['WARN'])
    infos = max(counts.get('infos', 0), itemized['INFO'])
    total = max(counts.get('total', 0), len(findings), errors + warnings + infos)

    contradictions = []
    if summary_keys_measured:
        if counts.get('errors', 0) < itemized['ERROR']:
            contradictions.append(
                'summary.errors=%d is lower than %d itemized ERROR finding(s)'
                % (counts.get('errors', 0), itemized['ERROR']))
        if counts.get('warnings', 0) < itemized['WARN']:
            contradictions.append(
                'summary.warnings=%d is lower than %d itemized WARN finding(s)'
                % (counts.get('warnings', 0), itemized['WARN']))
        if 'total' in counts and counts['total'] < errors + warnings + infos:
            contradictions.append(
                'summary.total=%d is lower than errors+warnings+infos=%d'
                % (counts['total'], errors + warnings + infos))
        if 'total' in counts and counts['total'] > errors + warnings + infos:
            contradictions.append(
                'summary.total=%d is higher than errors+warnings+infos=%d; '
                'finding(s) are not itemised'
                % (counts['total'], errors + warnings + infos))
    if levels['UNKNOWN']:
        contradictions.append(
            '%d finding(s) have no recognised level/severity'
            % len(levels['UNKNOWN']))
    if level_conflicts:
        contradictions.append(
            '%d finding(s) have conflicting level and severity values'
            % len(level_conflicts))
    if diagnostics:
        contradictions.append(
            '%d invalid field(s) in the check receipt; values were not coerced '
            'to a clean result' % len(diagnostics))
    if envelope['contradictory_envelope']:
        contradictions.append('outer envelope ok=false with a result object')

    consistent = not contradictions
    passed = bool(measured and errors == 0 and consistent and
                  not envelope['contradictory_envelope'])
    return {
        'schema': CHECK_SCHEMA,
        'parser_version': PARSER_VERSION,
        'measured': measured,
        'trusted': not envelope['contradictory_envelope'],
        'passed': passed,
        'raw_passed': data.get('passed') if isinstance(data.get('passed'), bool)
        else None,
        'summary': summary,
        'counts': {
            'errors': errors, 'warnings': warnings, 'infos': infos,
            'total': total,
            'itemized_errors': itemized['ERROR'],
            'itemized_warnings': itemized['WARN'],
            'itemized_infos': itemized['INFO'],
            'unlevelled_findings': itemized['UNKNOWN'],
        },
        'errors': levels['ERROR'],
        'warnings': levels['WARN'],
        'infos': levels['INFO'],
        'unlevelled': levels['UNKNOWN'],
        'findings': findings,
        'level_conflicts': level_conflicts,
        'contradictions': contradictions,
        'consistent': consistent,
        'diagnostics': diagnostics,
        'note': 'pcb check passed=false may mean warnings only; gate on errors '
                'and dispositions, not on the boolean alone',
    }


# ---------------------------------------------------------------------------
# native DRC
# ---------------------------------------------------------------------------


def parse_drc(payload):
    """Normalize native ``easycirq pcb drc`` output.

    A bare ``{"passed": true}`` is not a measurement: the native receipt must
    carry a total or a violations list (or counts) before ``ok`` can be true.
    ``passed=true`` with a nonzero total, a nonempty violations list, a nonzero
    connection count or contradictory counters is not clean.
    """
    data, envelope = _envelope_meta(payload)
    diagnostics = list(envelope['diagnostics'])
    contradictions = []

    raw_passed = data.get('passed')
    passed_present = isinstance(raw_passed, bool)
    if raw_passed is not None and not passed_present:
        diagnostics.append(_diagnostic('passed', 'boolean required', raw_passed))
    passed = raw_passed if passed_present else False
    if envelope['contradictory_envelope']:
        contradictions.append('outer envelope ok=false with a result object')

    violations_value = data.get('violations')
    violations_present = isinstance(violations_value, list)
    if violations_value is not None and not violations_present:
        diagnostics.append(_diagnostic('violations', 'list required',
                                       violations_value))
        violations = []
    else:
        violations = violations_value or []
    if violations_present:
        for index, item in enumerate(violations):
            if not isinstance(item, (dict, str)):
                diagnostics.append(_diagnostic('violations[%d]' % index,
                                               'object or string required', item))

    total_present = 'total' in data
    total = None
    if total_present:
        ok, value, issue = _nonnegative_int(data.get('total'))
        if ok:
            total = value
        else:
            issue['field'] = 'total'
            diagnostics.append(issue)
    if total is None and violations_present:
        total = len(violations)

    counts_value = data.get('counts')
    counts_present = isinstance(counts_value, dict)
    if counts_value is not None and not counts_present:
        diagnostics.append(_diagnostic('counts', 'object required', counts_value))
    counts = counts_value if counts_present else {}
    normalized_counts = {}
    normalized_keys = {}
    for key, value in counts.items():
        ok, number, issue = _nonnegative_int(value)
        text_key = _text(key)
        if ok:
            normalized_counts[text_key] = number
            normalized_keys[text_key.lower().replace(' ', '').replace('_', '')] = number
        else:
            issue['field'] = 'counts.%s' % key
            diagnostics.append(issue)
    connection = (normalized_keys.get('connection', 0) or
                  normalized_keys.get('connectionerror', 0) or
                  normalized_keys.get('connectionerrors', 0) or 0)
    measured = bool(passed_present and
                    (total_present or violations_present or
                     bool(normalized_counts)))

    if total is not None:
        if total == 0 and violations:
            contradictions.append('total=0 but the violations list is not empty')
        if total < len(violations):
            contradictions.append(
                'total=%d is lower than %d listed violation(s)'
                % (total, len(violations)))
        if connection > total:
            contradictions.append(
                'counts.connection=%d exceeds total=%d' % (connection, total))
        counted = sum(normalized_counts.values())
        if counted > total:
            contradictions.append(
                'counts sum to %d but total=%d' % (counted, total))
    if passed and total not in (None, 0):
        contradictions.append('passed=true with total=%d' % total)
    if passed and violations:
        contradictions.append('passed=true with %d listed violation(s)'
                              % len(violations))
    if passed and connection:
        contradictions.append('passed=true with connection=%d' % connection)
    if diagnostics:
        contradictions.append(
            '%d invalid field(s) in the native DRC receipt; a missing or '
            'malformed total is not a clean result' % len(diagnostics))
    if envelope['contradictory_envelope']:
        contradictions.append('the outer envelope reports failure')

    consistent = not contradictions
    ok = bool(measured and passed and total == 0 and not violations and
              connection == 0 and consistent)
    return {
        'schema': DRC_SCHEMA,
        'parser_version': PARSER_VERSION,
        'measured': measured,
        'trusted': not envelope['contradictory_envelope'],
        'passed': passed,
        'passed_present': passed_present,
        'total': int(total or 0),
        'total_present': total_present,
        'counts': normalized_counts,
        'violations': violations,
        'connection_violations': connection,
        'contradictions': contradictions,
        'consistent': consistent,
        'diagnostics': diagnostics,
        'ok': ok,
        'note': 'native DRC must be run with the PCB foreground; total=0 is the '
                'only clean result',
    }


# ---------------------------------------------------------------------------
# layout lint
# ---------------------------------------------------------------------------


def parse_layout_lint(payload):
    """Normalize ``easycirq pcb layout-lint --json``.

    Fields must be finite numbers (booleans and numeric strings are not
    numbers).  Counts cannot be negative.  If a required field is invalid the
    report is not a measurement, rather than being coerced to zero.
    """
    data, envelope = _envelope_meta(payload)
    diagnostics = list(envelope['diagnostics'])
    report = data.get('report')
    if report is not None and not isinstance(report, dict):
        diagnostics.append(_diagnostic('report', 'object required', report))
    report = report if isinstance(report, dict) else data

    values = {}
    derived = {}
    summary_text = str(report.get('summary') or data.get('summary') or '')

    def summary_zero(label):
        return re.search(r'\b0\s+' + re.escape(label), summary_text,
                         re.IGNORECASE) is not None

    def number(*keys, nonnegative=False, required=False, label=None):
        for key in keys:
            if key not in report:
                continue
            raw = report.get(key)
            if raw is None:
                # Real EasyEDA layout-lint uses null for an empty detail
                # array (e.g. overlaps/outsideOutline/tightSpacing).  Accept
                # it only when the summary text corroborates a zero count;
                # otherwise it is an unmeasured field, not a silent zero.
                if label and summary_zero(label):
                    derived[key] = 'summary_zero'
                    return 0
                if required:
                    diagnostics.append(_diagnostic(
                        key, 'field is null and the summary does not confirm '
                             'a zero count', raw))
                return None
            if isinstance(raw, list):
                derived[key] = 'detail_array_length'
                return len(raw)
            ok, value, issue = _number(raw)
            if not ok:
                issue['field'] = key
                diagnostics.append(issue)
                return None
            if nonnegative and value < 0:
                diagnostics.append(_diagnostic(
                    key, 'nonnegative number required', raw))
                return None
            return value
        if required:
            diagnostics.append(_diagnostic(keys[0], 'field required'))
        return None

    values['score'] = number('score', required=True)
    values['crossings'] = number('crossingCount', 'crossings',
                                 nonnegative=True, required=True)
    values['components'] = number('componentCount', 'components', 'comps',
                                  nonnegative=True, required=True)
    values['overlap'] = number('overlap', 'overlaps', nonnegative=True,
                               label='overlap')
    values['off_board'] = number('offBoard', 'off_board', 'outsideOutline',
                                 nonnegative=True, label='off-board')
    values['short'] = number('short', 'shorts', nonnegative=True,
                             label='short')
    values['tight'] = number('tight', 'tightSpacing', nonnegative=True,
                             label='tight')
    values['silk_over_pad'] = number('silkOverPad', 'silk_over_pad',
                                     nonnegative=True, label='silk-over-pad')

    has_overlap = any(key in report for key in ('overlap', 'overlaps'))
    has_off_board = any(key in report for key in
                        ('offBoard', 'off_board', 'outsideOutline'))
    coverage_value = data.get('coverage', report.get('coverage'))
    coverage_complete = False
    if isinstance(coverage_value, dict):
        coverage_complete = coverage_value.get('complete') is True
    elif coverage_value is not None:
        diagnostics.append(_diagnostic('coverage', 'object required',
                                       coverage_value))
    incomplete_value = report.get('incomplete', data.get('incomplete'))
    incomplete = incomplete_value is True
    if incomplete_value is not None and not isinstance(incomplete_value, bool):
        diagnostics.append(_diagnostic('incomplete', 'boolean required',
                                       incomplete_value))
        incomplete = True

    measured = bool(values['score'] is not None and
                    values['crossings'] is not None and
                    values['components'] is not None and
                    has_overlap and has_off_board and
                    values['overlap'] is not None and
                    values['off_board'] is not None and
                    not envelope['contradictory_envelope'])
    return {
        'schema': LINT_SCHEMA,
        'parser_version': PARSER_VERSION,
        'measured': measured,
        'trusted': not envelope['contradictory_envelope'],
        'score': values['score'] if values['score'] is not None else 0,
        'crossings': values['crossings'] if values['crossings'] is not None else 0,
        'components': values['components'] if values['components'] is not None else 0,
        'overlap': values['overlap'] if values['overlap'] is not None else 0,
        'off_board': values['off_board'] if values['off_board'] is not None else 0,
        'short': values['short'] if values['short'] is not None else 0,
        'tight': values['tight'] if values['tight'] is not None else 0,
        'silk_over_pad': (values['silk_over_pad']
                          if values['silk_over_pad'] is not None else 0),
        'coverage_complete': coverage_complete,
        'incomplete': incomplete,
        'field_basis': derived,
        'raw': report,
        'diagnostics': diagnostics,
        'note': 'score/crossings are placement quality, not routing correctness',
    }


# ---------------------------------------------------------------------------
# net-path
# ---------------------------------------------------------------------------


def evaluate_netpath(rows, required):
    """Check every required pad-to-pad path is connected.

    ``required`` is a list of ``{net, from, to}``.  ``from``/``to`` use
    ``DESIGNATOR.PAD``.  A proof must be ``status=connected`` and
    ``path_kind=exact-centerline``; pours are not covered by this command.
    An empty requirement list is ``not_applicable``, not a pass.
    """
    rows = [row for row in rows or [] if isinstance(row, dict)]
    required = [item for item in required or [] if isinstance(item, dict)]
    results = []
    missing = []
    failed = []
    unmeasured = []
    invalid = []
    for index, item in enumerate(required):
        net = _text(item.get('net'))
        start = _text(item.get('from'))
        end = _text(item.get('to'))
        if not (net and start and end):
            entry = {'index': index, 'net': net, 'from': start, 'to': end,
                     'status': 'invalid'}
            results.append(entry)
            invalid.append(entry)
            continue
        candidates = [
            row for row in rows
            if _text(row.get('net')) == net and
            ((_text(row.get('from')) == start and _text(row.get('to')) == end) or
             (_text(row.get('from')) == end and _text(row.get('to')) == start))
        ]
        connected = [row for row in candidates
                     if _text(row.get('status')).lower() == 'connected' and
                     _text(row.get('path_kind')) == 'exact-centerline']
        unknown = [row for row in candidates
                   if _text(row.get('path_kind')) in ('', 'unknown', None)]
        entry = {'net': net, 'from': start, 'to': end,
                 'candidates': len(candidates), 'connected': len(connected)}
        if not candidates:
            entry['status'] = 'missing'
            missing.append(entry)
        elif unknown and not connected:
            entry['status'] = 'unmeasured'
            entry['reason'] = 'candidate path exists but path_kind is unknown'
            unmeasured.append(entry)
        elif not connected:
            entry['status'] = 'not_connected'
            failed.append(entry)
        elif len(connected) > 1:
            entry['status'] = 'ambiguous'
            failed.append(entry)
        else:
            entry['status'] = 'connected'
            entry['path'] = connected[0]
        results.append(entry)
    if not required:
        status = 'not_applicable'
    elif invalid or missing or failed or unmeasured:
        status = 'fail'
    else:
        status = 'pass'
    return {
        'schema': NETPATH_SCHEMA,
        'parser_version': PARSER_VERSION,
        'status': status,
        'required': len(required),
        'connected': sum(1 for item in results if item.get('status') == 'connected'),
        'rows': results,
        'missing': missing,
        'failed': failed,
        'unmeasured': unmeasured,
        'invalid': invalid,
        'note': 'net-path proves listed tracks/vias only; copper pours need DRC + '
                'poured-list evidence',
    }


def finding_key(finding):
    """Stable disposition key for one pcb-check finding."""
    kind = _finding_type(finding)
    # primitiveId is not stable across a document reload; keep the key on
    # durable designators/nets/pads so a disposition survives save/reload.
    objects = []
    for field in ('designators', 'designator', 'nets', 'net', 'pad', 'pads'):
        value = finding.get(field)
        if isinstance(value, str):
            objects.append(value)
        elif isinstance(value, list):
            objects.extend(_text(item) for item in value if _text(item))
    return kind + '|' + '|'.join(sorted(set(objects)))


def _disposition_key(entry):
    if entry.get('key'):
        return _text(entry.get('key'))
    return finding_key(entry)


def validate_warn_disposition(disposition, check_report, check_sha256=None,
                              levels=('ERROR', 'WARN', 'INFO')):
    """Require every finding in ``levels`` to be dispositioned.

    ``disposition`` schema ``design-engine-pcb-warn-disposition/v1``:
      {schema, source: {sha256, path?}, findings: [{type/designator/net/...,
       disposition: fixed|waived|accepted|not_applicable, reason,
       evidence: [paths], recheck_condition?}]}
    ``fixed`` means the finding is gone from the current report; if it is still
    present the disposition is stale and fails.
    """
    data = _as_envelope(disposition)
    problems = []
    if data.get('schema') != WARN_DISPOSITION_SCHEMA:
        problems.append('schema must be %s' % WARN_DISPOSITION_SCHEMA)
    source = data.get('source') if isinstance(data.get('source'), dict) else {}
    if check_sha256:
        if not source.get('sha256'):
            problems.append('source.sha256 is required to bind the disposition '
                            'to the check report')
        else:
            allowed = ({check_sha256} if isinstance(check_sha256, str)
                       else set(check_sha256))
            if source['sha256'] not in allowed:
                problems.append('source.sha256 does not match the check report')
    entries = data.get('findings') if isinstance(data.get('findings'), list) else []
    by_key = {}
    for entry in entries:
        if not isinstance(entry, dict):
            problems.append('disposition entry is not an object')
            continue
        key = _disposition_key(entry)
        if key in by_key:
            problems.append('duplicate disposition key: %s' % key)
        by_key[key] = entry

    wanted = {_text(level).upper() for level in levels}
    wanted = {level for level in wanted if level in _LEVELS}
    current = [item for item in check_report.get('findings') or []
               if isinstance(item, dict) and
               _normalized_level(item) in wanted]
    missing = []
    stale = []
    invalid = []
    for finding in current:
        key = finding_key(finding)
        entry = by_key.get(key)
        if entry is None:
            missing.append({'key': key, 'level': finding.get('level'),
                            'type': _finding_type(finding)})
            continue
        state = _text(entry.get('disposition')).lower()
        if state not in ('fixed', 'waived', 'accepted', 'not_applicable'):
            invalid.append({'key': key, 'reason': 'unknown disposition %r' % state})
            continue
        if state == 'fixed':
            stale.append({'key': key, 'reason': 'marked fixed but still present'})
        if not _text(entry.get('reason')):
            invalid.append({'key': key, 'reason': 'missing reason'})
    status = 'pass' if not missing and not stale and not invalid and not problems \
        else 'fail'
    return {
        'schema': 'design-engine-pcb-warn-disposition-check/v1',
        'status': status,
        'current_warn_errors': len(current),
        'dispositioned': len(by_key),
        'missing': missing,
        'stale': stale,
        'invalid': invalid,
        'problems': problems,
        'accepted_risks': [
            {'key': key, 'disposition': entry.get('disposition'),
             'reason': entry.get('reason')}
            for key, entry in by_key.items()
            if _text(entry.get('disposition')).lower() in
            ('waived', 'accepted', 'not_applicable')
        ],
    }


def artifact_hashes(manifest_or_dir):
    """Return {role: sha256} from a manifest or a case evidence dir."""
    if isinstance(manifest_or_dir, dict):
        artifacts = manifest_or_dir.get('artifacts') or []
    else:
        path = manifest_or_dir
        if os.path.isfile(path):
            artifacts = (load_json(path) or {}).get('artifacts') or []
        else:
            return {}
    hashes = {}
    for item in artifacts:
        if not isinstance(item, dict):
            continue
        role = item.get('role')
        if role and item.get('sha256'):
            hashes[role] = item['sha256']
    return hashes


def compare_artifact_baseline(current_hashes, baseline_hashes):
    """Compare role hashes; a missing or empty baseline is not a match."""
    if not baseline_hashes:
        return {'status': 'unmeasured',
                'reason': 'baseline has no role hashes',
                'changed': [], 'missing': [], 'extra_roles': []}
    changed = []
    missing = []
    for role, expected in sorted((baseline_hashes or {}).items()):
        actual = (current_hashes or {}).get(role)
        if actual is None:
            missing.append({'role': role, 'expected': expected})
        elif actual != expected:
            changed.append({'role': role, 'expected': expected, 'actual': actual})
    extra = sorted(set(current_hashes or {}) - set(baseline_hashes or {}))
    return {
        'status': 'match' if not changed and not missing else 'mismatch',
        'changed': changed,
        'missing': missing,
        'extra_roles': extra,
    }


def file_evidence(path, role):
    return {'role': role, 'path': path, 'sha256': sha256_file(path),
            'bytes': os.path.getsize(path)}
