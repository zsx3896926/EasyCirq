#!/usr/bin/env python3
"""Deterministic parsers/normalizers for PCB acceptance evidence.

``pcb_gate.py`` and ``pcb_case.py`` share these functions so a check cannot be
"passed" by one tool with a different interpretation than the other.  Nothing
here talks to EDA; all inputs are already captured JSON or a manifest.

Design rules:
  * missing or unreadable evidence is ``blocked``/``incomplete``, never pass;
  * a warning is not an error, but every warning needs a disposition;
  * net-path never covers copper pours; callers must say so in the report;
  * component/pin comparisons are exact for designator+pad number.  Combination
    pads need an explicit alias map; an unmapped pin is reported, not guessed.
"""
from __future__ import annotations

import os

from pcb_cli import load_json, sha256_file

SCH_PCB_SCHEMA = 'design-engine-pcb-sch-pcb-compare/v1'
WARN_DISPOSITION_SCHEMA = 'design-engine-pcb-warn-disposition/v1'
CHECK_SCHEMA = 'design-engine-pcb-check/v1'
DRC_SCHEMA = 'design-engine-pcb-drc/v1'
LINT_SCHEMA = 'design-engine-pcb-lint/v1'
NETPATH_SCHEMA = 'design-engine-pcb-netpath/v1'


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


def _sch_components(sch):
    """Return {ref: {pin: net}} for the two supported schematic shapes."""
    sch = _as_envelope(sch)
    components = sch.get('components')
    if not isinstance(components, list):
        return {}
    if sch.get('connections') is not None and sch.get('nets') is not None:
        nets = {item.get('id'): item.get('name')
                for item in sch.get('nets') or [] if isinstance(item, dict)}
        per_pin = {}
        for connection in sch.get('connections') or []:
            if not isinstance(connection, dict):
                continue
            per_pin[(connection.get('componentId'),
                     _text(connection.get('pinNumber')))] = _net(
                         nets.get(connection.get('netId')))
        mapping = {}
        for component in components:
            if not isinstance(component, dict):
                continue
            ref = _text(component.get('ref') or component.get('designator'))
            if not ref:
                continue
            pins = {}
            for pin in component.get('pins') or []:
                if not isinstance(pin, dict):
                    continue
                number = _text(pin.get('number') or pin.get('name'))
                if number:
                    pins[number] = _net(pin.get('net'))
            for (component_id, number), net in per_pin.items():
                if component_id == component.get('id'):
                    pins[number] = net
            mapping[ref] = pins
        return mapping
    mapping = {}
    for component in components:
        if not isinstance(component, dict):
            continue
        ref = _text(component.get('designator') or component.get('ref'))
        if not ref:
            continue
        pins = {}
        for pin in component.get('pins') or []:
            if not isinstance(pin, dict):
                continue
            number = _text(pin.get('number') or pin.get('name'))
            if number:
                pins[number] = _net(pin.get('net'))
        mapping[ref] = pins
    return mapping


def _pcb_components(dump):
    dump = _as_envelope(dump)
    mapping = {}
    for component in dump.get('components') or []:
        if not isinstance(component, dict):
            continue
        ref = _text(component.get('designator'))
        if not ref:
            continue
        pads = {}
        for pad in component.get('pads') or []:
            if not isinstance(pad, dict):
                continue
            number = _text(pad.get('padNumber') or pad.get('number'))
            if not number:
                continue
            pads[number] = _net(pad.get('net'))
        mapping[ref] = pads
    return mapping


def compare_sch_pcb(sch, dump, *, pin_aliases=None, ignore_designators=None):
    """Compare schematic pin nets with PCB pad nets.

    ``pin_aliases`` is ``{designator: {sch_pin: [pcb_pad, ...]}}`` for
    combination pads.  Without an alias, one schematic pin must match one PCB
    pad with the same number; an unmapped schematic pin is a mismatch kind
    ``unmapped_pin`` instead of being silently skipped.
    """
    sch_map = _sch_components(sch)
    pcb_map = _pcb_components(dump)
    aliases = pin_aliases or {}
    ignored = set(ignore_designators or [])
    for ref in ignored:
        sch_map.pop(ref, None)
        pcb_map.pop(ref, None)

    component_mismatches = []
    for ref in sorted(set(sch_map) - set(pcb_map)):
        component_mismatches.append({'designator': ref, 'kind': 'missing_component'})
    for ref in sorted(set(pcb_map) - set(sch_map)):
        component_mismatches.append({'designator': ref, 'kind': 'extra_component'})

    rows = []
    for ref in sorted(set(sch_map) & set(pcb_map)):
        schematic = sch_map[ref]
        board = pcb_map[ref]
        ref_aliases = aliases.get(ref) or {}
        used_pads = set()
        for pin in sorted(schematic):
            expected = schematic.get(pin)
            targets = ref_aliases.get(pin)
            if targets:
                used_pads.update(targets)
                actual_nets = {_net(board.get(target)) for target in targets}
                actual = next(iter(actual_nets)) if len(actual_nets) == 1 else tuple(
                    sorted('' if value is None else value for value in actual_nets))
                status = 'match' if all(
                    (_net(board.get(target)) or None) == expected for target in targets
                ) else 'mismatch'
                rows.append({
                    'designator': ref, 'pin': pin, 'pcb_pads': list(targets),
                    'schematic_net': expected,
                    'pcb_net': actual if isinstance(actual, str) else list(actual),
                    'status': status,
                })
                continue
            if pin not in board:
                rows.append({
                    'designator': ref, 'pin': pin, 'schematic_net': expected,
                    'pcb_net': None, 'status': 'mismatch', 'kind': 'missing_pad',
                })
                continue
            actual = board.get(pin)
            rows.append({
                'designator': ref, 'pin': pin, 'schematic_net': expected,
                'pcb_net': actual,
                'status': 'match' if expected == actual else 'mismatch',
            })
        for pin in sorted(set(board) - set(schematic) - used_pads):
            rows.append({
                'designator': ref, 'pin': pin, 'schematic_net': None,
                'pcb_net': board.get(pin), 'status': 'mismatch',
                'kind': 'extra_pad',
            })
    mismatches = component_mismatches + [
        row for row in rows if row.get('status') != 'match'
    ]
    return {
        'schema': SCH_PCB_SCHEMA,
        'status': 'match' if not mismatches else 'mismatch',
        'schematic_components': len(sch_map),
        'pcb_components': len(pcb_map),
        'pins': len(rows),
        'component_mismatches': component_mismatches,
        'mismatches': mismatches,
        'rows': rows,
        'note': 'designator+pad-number comparison; combination pads require pin_aliases',
    }


def _level_counts(findings):
    counts = {'ERROR': 0, 'WARN': 0, 'INFO': 0}
    for finding in findings:
        level = _text(finding.get('level') or finding.get('severity')).upper()
        if level in counts:
            counts[level] += 1
    return counts


def parse_pcb_check(payload):
    """Normalize ``easyeda pcb check --json`` (envelope or result)."""
    data = _as_envelope(payload)
    findings = [item for item in data.get('findings') or [] if isinstance(item, dict)]
    summary = data.get('summary') if isinstance(data.get('summary'), dict) else {}
    levels = _level_counts(findings)
    summary_measured = ('errors' in summary and 'warnings' in summary)
    findings_measured = bool(data.get('findings'))
    measured = summary_measured or findings_measured
    errors = int(summary.get('errors', levels['ERROR']) or 0)
    warnings = int(summary.get('warnings', levels['WARN']) or 0)
    infos = int(summary.get('infos', levels['INFO']) or 0)
    total = int(summary.get('total', len(findings)) or 0)
    return {
        'schema': CHECK_SCHEMA,
        'measured': measured,
        'passed': measured and errors == 0,
        'summary': summary,
        'counts': {
            'errors': errors, 'warnings': warnings, 'infos': infos,
            'total': total,
        },
        'errors': [f for f in findings
                   if _text(f.get('level')).upper() == 'ERROR'],
        'warnings': [f for f in findings
                     if _text(f.get('level')).upper() == 'WARN'],
        'infos': [f for f in findings
                  if _text(f.get('level')).upper() == 'INFO'],
        'findings': findings,
        'note': 'pcb check passed=false may mean warnings only; gate on errors and '
                'dispositions, not on the boolean alone',
    }


def parse_drc(payload):
    """Normalize native ``easyeda pcb drc`` output.

    A bare ``{"passed": true}`` is not a measurement: the native receipt must
    carry a total or a violations list (or counts) before ``ok`` can be true.
    """
    data = _as_envelope(payload)
    counts = data.get('counts') if isinstance(data.get('counts'), dict) else {}
    violations = data.get('violations') if isinstance(data.get('violations'), list) else []
    total_present = isinstance(data.get('total'), int) and not isinstance(data.get('total'), bool)
    measured = (isinstance(data.get('passed'), bool) and
                (total_present or isinstance(data.get('violations'), list) or
                 isinstance(data.get('counts'), dict)))
    total = data.get('total')
    if total is None:
        total = len(violations)
    connection = int(counts.get('connection', 0) or 0)
    return {
        'schema': DRC_SCHEMA,
        'measured': measured,
        'passed': data.get('passed') is True,
        'total': int(total or 0),
        'counts': counts,
        'violations': violations,
        'connection_violations': connection,
        'ok': bool(measured and data.get('passed') is True and
                   int(total or 0) == 0 and connection == 0),
        'note': 'native DRC must be run with the PCB foreground; total=0 is the '
                'only clean result',
    }


def parse_layout_lint(payload):
    """Normalize ``easyeda pcb layout-lint --json``."""
    data = _as_envelope(payload)
    report = data.get('report') if isinstance(data.get('report'), dict) else data
    def number(*keys, default=0):
        for key in keys:
            value = report.get(key)
            if isinstance(value, (int, float)):
                return value
        return default
    measured = (number('score', default=None) is not None and
                number('crossingCount', 'crossings', default=None) is not None and
                number('componentCount', 'components', 'comps', default=None) is not None and
                any(key in report for key in ('overlap', 'overlaps')) and
                any(key in report for key in ('offBoard', 'off_board', 'outsideOutline')))
    return {
        'schema': LINT_SCHEMA,
        'measured': measured,
        'score': number('score'),
        'crossings': number('crossingCount', 'crossings'),
        'components': number('componentCount', 'components', 'comps'),
        'overlap': number('overlap', 'overlaps'),
        'off_board': number('offBoard', 'off_board', 'outsideOutline'),
        'short': number('short', 'shorts'),
        'tight': number('tight', 'tightSpacing'),
        'silk_over_pad': number('silkOverPad', 'silk_over_pad'),
        'coverage_complete': bool((report.get('coverage') or {}).get('complete', False)),
        'incomplete': bool(report.get('incomplete', False)),
        'raw': report,
        'note': 'score/crossings are placement quality, not routing correctness',
    }


def evaluate_netpath(rows, required):
    """Check every required pad-to-pad path is connected.

    ``required`` is a list of ``{net, from, to}``.  ``from``/``to`` use
    ``DESIGNATOR.PAD``.  A proof must be ``status=connected`` and
    ``path_kind=exact-centerline``; pours are not covered by this command.
    """
    rows = [row for row in rows or [] if isinstance(row, dict)]
    required = [item for item in required or [] if isinstance(item, dict)]
    results = []
    missing = []
    failed = []
    for item in required:
        net = _text(item.get('net'))
        start = _text(item.get('from'))
        end = _text(item.get('to'))
        candidates = [
            row for row in rows
            if _text(row.get('net')) == net and
            ((_text(row.get('from')) == start and _text(row.get('to')) == end) or
             (_text(row.get('from')) == end and _text(row.get('to')) == start))
        ]
        connected = [row for row in candidates
                     if _text(row.get('status')).lower() == 'connected' and
                     _text(row.get('path_kind')) == 'exact-centerline']
        entry = {'net': net, 'from': start, 'to': end,
                 'candidates': len(candidates), 'connected': len(connected)}
        if not candidates:
            entry['status'] = 'missing'
            missing.append(entry)
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
    return {
        'schema': NETPATH_SCHEMA,
        'status': 'pass' if not missing and not failed else 'fail',
        'required': len(required),
        'connected': sum(1 for item in results if item.get('status') == 'connected'),
        'rows': results,
        'missing': missing,
        'failed': failed,
        'note': 'net-path proves listed tracks/vias only; copper pours need DRC + '
                'poured-list evidence',
    }


def finding_key(finding):
    """Stable disposition key for one pcb-check finding."""
    kind = _text(finding.get('type') or finding.get('code') or
                  finding.get('rule') or 'unknown')
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


def validate_warn_disposition(disposition, check_report, check_sha256=None):
    """Require every ERROR/WARN in a check report to be dispositioned.

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
        elif source['sha256'] != check_sha256:
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

    current = [item for item in check_report.get('findings') or []
               if _text(item.get('level')).upper() in ('ERROR', 'WARN')]
    missing = []
    stale = []
    invalid = []
    for finding in current:
        key = finding_key(finding)
        entry = by_key.get(key)
        if entry is None:
            missing.append({'key': key, 'level': finding.get('level'),
                            'type': finding.get('type')})
            continue
        state = _text(entry.get('disposition')).lower()
        if state not in ('fixed', 'waived', 'accepted', 'not_applicable'):
            invalid.append({'key': key, 'reason': 'unknown disposition %r' % state})
            continue
        if state == 'fixed':
            stale.append({'key': key, 'reason': 'marked fixed but still present'})
        if not _text(entry.get('reason')):
            invalid.append({'key': key, 'reason': 'missing reason'})
    for key, entry in by_key.items():
        state = _text(entry.get('disposition')).lower()
        if state == 'fixed' and key not in {finding_key(f) for f in current}:
            continue
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
            if _text(entry.get('disposition')).lower() in ('waived', 'accepted')
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
    """Compare role hashes; a missing baseline role fails the comparison."""
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
