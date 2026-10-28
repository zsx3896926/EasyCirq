#!/usr/bin/env python3
"""Single resolver and JSON parsing helpers for the Zhigou execution layer.

The skill drives exactly one executor: the ``zhigou`` CLI that ships with this
repository (``runtime/``, installed through ``distribution/``).  Everything
else in ``scripts/`` that shells out resolves the binary through
:func:`resolve_bin`, so a test seam or an installation layout never has to be
hard-coded twice.

Contract (verified against ``zhigou`` 0.2.0-dev, 2026-10-27):

* ``zhigou doctor`` emits ``zhigou-doctor/v1`` JSON on stdout and a human
  summary on stderr; a non-zero exit means the doctor itself failed, not that
  the toolchain is unusable.  ``verdict`` is ``ok`` / ``degraded`` / ``blocked``.
* ``zhigou capabilities`` emits ``zhigou-capabilities/v1`` JSON with one row per
  capability: ``supported`` / ``unsupported`` / ``unknown`` **plus a reason**.
  A capability is never inferred from the EDA version.

The parse helpers below normalise that JSON into the small facts the skill is
allowed to rely on.  They raise ``ValueError`` on a foreign or truncated
schema instead of guessing: a missing field must stay "unknown", never "ok".
"""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone

import offline_guard

DEFAULT_BIN = 'zhigou'
DEFAULT_TIMEOUT_SEC = 60.0
DOCTOR_SCHEMA = 'zhigou-doctor/v1'
CAPABILITIES_SCHEMA = 'zhigou-capabilities/v1'


class ZhigouError(ValueError):
    """The CLI output did not satisfy the documented contract."""


def resolve_bin(explicit=None):
    """Return the CLI to execute: explicit argument -> ``ZHIGOU_BIN`` -> PATH."""
    if explicit:
        return str(explicit)
    return os.environ.get('ZHIGOU_BIN', '').strip() or DEFAULT_BIN


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def run(args, *, zhigou=None, timeout=DEFAULT_TIMEOUT_SEC, cwd=None, env=None):
    """Run one ``zhigou`` command and return a JSON-friendly record.

    Never raises for a missing executable, a timeout or non-JSON output: a
    caller that reports a capability needs the failure itself, not an
    exception.  The offline guard still refuses a real binary during tests.
    """
    argv = [resolve_bin(zhigou)] + [str(item) for item in args]
    offline_guard.check_executable(argv, context='zhigou_cli.run')
    started = utc_now()
    stdout = stderr = ''
    code = None
    error = None
    try:
        proc = subprocess.run(
            argv, capture_output=True, text=True, encoding='utf-8',
            errors='replace', timeout=timeout, cwd=cwd, env=env,
        )
        code = proc.returncode
        stdout = proc.stdout or ''
        stderr = proc.stderr or ''
    except subprocess.TimeoutExpired as exc:
        code = 124
        stdout = _as_text(exc.stdout)
        stderr = _as_text(exc.stderr)
        error = 'timeout after %ss' % timeout
    except FileNotFoundError as exc:
        code = 127
        error = 'executable not found: %s' % exc
    except OSError as exc:
        code = 126
        error = 'could not execute: %s' % exc
    return {
        'argv': argv,
        'exit': code,
        'error': error,
        'stdout': stdout,
        'stderr': stderr,
        'payload': parse_json_payload(stdout),
        'started_at': started,
        'ended_at': utc_now(),
    }


def _as_text(value):
    if value is None:
        return ''
    if isinstance(value, bytes):
        return value.decode('utf-8', 'replace')
    return str(value)


def parse_json_payload(text):
    """Return the first JSON object printed on stdout, or ``None``."""
    text = (text or '').strip()
    if not text:
        return None
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        pass
    # Tolerate a leading notice line before the JSON document.
    for index, char in enumerate(text):
        if char != '{':
            continue
        try:
            value, _ = json.JSONDecoder().raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None


def _check_schema(payload, schema):
    if not isinstance(payload, dict):
        raise ZhigouError('expected a JSON object')
    found = payload.get('schema')
    if found != schema:
        raise ZhigouError('unexpected schema %r (expected %r)' % (found, schema))
    return payload


def _as_dict(value):
    return value if isinstance(value, dict) else {}


def _as_list(value):
    return value if isinstance(value, list) else []


def _check_rows(payload):
    rows = []
    for item in _as_list(payload.get('checks')):
        if not isinstance(item, dict):
            continue
        rows.append({
            'name': str(item.get('name') or ''),
            'status': str(item.get('status') or 'unknown'),
            'detail': str(item.get('detail') or ''),
            'fix': str(item.get('fix') or ''),
        })
    return rows


def parse_doctor(payload):
    """Normalise a ``zhigou-doctor/v1`` document.

    ``ready`` is true only when the doctor's own verdict is ``ok`` *and* the
    daemon is running *and* a connector is connected *and* the protocol is
    reported.  Anything else is a blocker with a reason; a degraded verdict is
    never rounded up to ready.
    """
    _check_schema(payload, DOCTOR_SCHEMA)
    runtime = _as_dict(payload.get('runtime'))
    skill = _as_dict(payload.get('skill'))
    daemon = _as_dict(payload.get('daemon'))
    connector = _as_dict(payload.get('connector'))
    protocol = _as_dict(payload.get('protocol'))
    legacy = _as_dict(payload.get('legacy'))
    checks = _check_rows(payload)
    verdict = str(payload.get('verdict') or 'unknown')

    blockers = []
    if verdict != 'ok':
        blockers.append('doctor verdict is %r' % verdict)
    if not runtime.get('onDisk'):
        blockers.append('runtime binary is not on disk (%s)' % (
            runtime.get('executable') or 'path unknown'))
    if daemon.get('status') != 'running':
        blockers.append('daemon is %r' % (daemon.get('status') or 'unknown'))
    if connector.get('status') != 'connected':
        blockers.append('connector is %r' % (connector.get('status') or 'unknown'))
    if not protocol.get('service'):
        blockers.append('protocol service name is missing')
    for row in checks:
        if row['status'] in ('fail', 'blocked'):
            blockers.append('check %r: %s' % (row['name'], row['detail'] or 'failed'))

    ready = not blockers
    return {
        'schema': DOCTOR_SCHEMA,
        'generated_at': payload.get('generatedAt'),
        'verdict': verdict,
        'ready': ready,
        'runtime': runtime,
        'skill': {
            'name': skill.get('name'),
            'status': skill.get('status'),
            'installed': [item for item in _as_list(skill.get('installed'))
                          if isinstance(item, dict)],
        },
        'daemon': daemon,
        'connector': connector,
        'protocol': protocol,
        'checks': checks,
        'failed_checks': [row for row in checks
                          if row['status'] in ('fail', 'blocked')],
        'next_steps': [str(item) for item in _as_list(payload.get('nextSteps'))],
        'legacy': {
            'detected': bool(legacy.get('detected')),
            'service': legacy.get('service'),
            'used': bool(legacy.get('used')),
        },
        'blockers': blockers,
    }


def parse_capabilities(payload):
    """Normalise a ``zhigou-capabilities/v1`` document.

    Returns one indexed row per capability plus explicit ``supported`` /
    ``unsupported`` / ``unknown`` lists.  The reason travels with the item so a
    caller cannot report a capability without saying why.
    """
    _check_schema(payload, CAPABILITIES_SCHEMA)
    items = {}
    for item in _as_list(payload.get('items')):
        if not isinstance(item, dict):
            continue
        cap_id = item.get('id')
        if not isinstance(cap_id, str) or not cap_id:
            continue
        status = str(item.get('status') or 'unknown')
        if status not in ('supported', 'unsupported', 'unknown'):
            status = 'unknown'
        items[cap_id] = {
            'id': cap_id,
            'status': status,
            'reason': str(item.get('reason') or ''),
            'mode': item.get('mode'),
            'returns_result': bool(item.get('returnsResult')),
            'readback': bool(item.get('readback')),
            'whole_board_impact': bool(item.get('wholeBoardImpact')),
            'action_count': item.get('actionCount'),
            'sample_actions': [str(value) for value in _as_list(item.get('sampleActions'))],
            'caveats': [str(value) for value in _as_list(item.get('caveats'))],
        }
    summary = _as_dict(payload.get('summary'))
    connector = _as_dict(payload.get('connector'))
    by_status = {'supported': [], 'unsupported': [], 'unknown': []}
    for row in items.values():
        by_status[row['status']].append(row)
    return {
        'schema': CAPABILITIES_SCHEMA,
        'generated_at': payload.get('generatedAt'),
        'protocol': _as_dict(payload.get('protocol')),
        'connector': {
            'status': connector.get('status'),
            'count': connector.get('count'),
            'reported': [str(value) for value in _as_list(connector.get('reported'))],
        },
        'summary': {
            'supported': _count(summary.get('supported'), by_status['supported']),
            'unsupported': _count(summary.get('unsupported'), by_status['unsupported']),
            'unknown': _count(summary.get('unknown'), by_status['unknown']),
        },
        'items': items,
        'supported': [row['id'] for row in by_status['supported']],
        'unsupported': [{'id': row['id'], 'reason': row['reason']}
                        for row in by_status['unsupported']],
        'unknown': [{'id': row['id'], 'reason': row['reason']}
                    for row in by_status['unknown']],
        'notes': [str(value) for value in _as_list(payload.get('notes'))],
        'connected': connector.get('status') == 'connected',
    }


def _count(reported, rows):
    if isinstance(reported, int) and not isinstance(reported, bool):
        return reported
    return len(rows)


def capability_state(report, capability_id):
    """Return ``supported``/``unsupported``/``unknown``/``missing`` for one id."""
    row = (report.get('items') or {}).get(capability_id)
    return row['status'] if row else 'missing'


def doctor(*, zhigou=None, timeout=DEFAULT_TIMEOUT_SEC, env=None, cwd=None):
    """Run ``zhigou doctor`` and return ``{record, ok, report, error}``."""
    record = run(['doctor'], zhigou=zhigou, timeout=timeout, env=env, cwd=cwd)
    return _load(record, parse_doctor)


def capabilities(*, zhigou=None, timeout=DEFAULT_TIMEOUT_SEC, env=None, cwd=None):
    """Run ``zhigou capabilities`` and return ``{record, ok, report, error}``."""
    record = run(['capabilities'], zhigou=zhigou, timeout=timeout, env=env, cwd=cwd)
    return _load(record, parse_capabilities)


def _load(record, parser):
    result = {'record': record, 'ok': False, 'report': None, 'error': None}
    if record.get('exit') != 0:
        result['error'] = ('zhigou %s exited %s: %s' % (
            record['argv'][1] if len(record['argv']) > 1 else '',
            record.get('exit'), (record.get('error') or record.get('stderr') or '')[:400]))
        return result
    payload = record.get('payload')
    if payload is None:
        result['error'] = 'zhigou %s did not emit a JSON object' % (
            record['argv'][1] if len(record['argv']) > 1 else '')
        return result
    try:
        result['report'] = parser(payload)
    except ZhigouError as exc:
        result['error'] = 'zhigou %s contract mismatch: %s' % (
            record['argv'][1] if len(record['argv']) > 1 else '', exc)
        return result
    result['ok'] = True
    return result


def preflight(*, zhigou=None, timeout=DEFAULT_TIMEOUT_SEC, env=None, cwd=None):
    """The skill's single preflight: doctor + capabilities.

    Returns a dict whose ``ready`` means "the documented contract reports a
    connected toolchain"; it never means "the project is writable" or "the
    design is correct".  Callers must keep those as separate claims.
    """
    diagnosis = doctor(zhigou=zhigou, timeout=timeout, env=env, cwd=cwd)
    negotiation = capabilities(zhigou=zhigou, timeout=timeout, env=env, cwd=cwd)
    blockers = []
    if not diagnosis['ok']:
        blockers.append(diagnosis['error'])
    elif not diagnosis['report']['ready']:
        blockers.extend(diagnosis['report']['blockers'])
    if not negotiation['ok']:
        blockers.append(negotiation['error'])
    return {
        'schema': 'design-hardware-preflight/v1',
        'generated_at': utc_now(),
        'ready': not blockers,
        'blockers': [item for item in blockers if item],
        'doctor': diagnosis['report'],
        'capabilities': negotiation['report'],
        'doctor_ok': diagnosis['ok'],
        'capabilities_ok': negotiation['ok'],
        'not_proven': [
            'project writability',
            'readback/persistence of a write',
            'electrical correctness or manufacturing readiness',
        ],
    }


def render_preflight(report):
    """Human summary used by ``--summary`` callers."""
    lines = ['preflight: %s' % ('ready' if report['ready'] else 'blocked')]
    diagnosis = report.get('doctor') or {}
    negotiation = report.get('capabilities') or {}
    if diagnosis:
        lines.append('- doctor verdict: %s' % diagnosis.get('verdict'))
        daemon = diagnosis.get('daemon') or {}
        connector = diagnosis.get('connector') or {}
        lines.append('- daemon: %s' % (daemon.get('status') or 'unknown'))
        lines.append('- connector: %s' % (connector.get('status') or 'unknown'))
    if negotiation:
        summary = negotiation.get('summary') or {}
        lines.append('- capabilities: supported=%s unsupported=%s unknown=%s' % (
            summary.get('supported'), summary.get('unsupported'),
            summary.get('unknown')))
    for blocker in report.get('blockers') or []:
        lines.append('- blocker: %s' % blocker)
    for step in report.get('not_proven') or []:
        lines.append('- NOT proven: %s' % step)
    return '\n'.join(lines)
