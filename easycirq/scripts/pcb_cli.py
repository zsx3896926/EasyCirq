#!/usr/bin/env python3
"""Shared process/JSON helpers for the PCB evidence tools.

This module never writes to an EDA project by itself.  It only runs the
``easyeda`` CLI (or a fake passed by a test), captures stdout/stderr, parses a
JSON payload when one is present, and records enough provenance for a case
manifest.  Every PCB tool accepts ``--easyeda`` so tests never fall back to a
real installed CLI through PATH.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone

import offline_guard

DEFAULT_TIMEOUT_SEC = 120.0


def easyeda_executable(explicit=None):
    """Return the CLI path/name.  ``EASYEDA_CLI`` is an explicit test seam."""
    return explicit or os.environ.get('EASYEDA_CLI') or 'easyeda'


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_text(text):
    return sha256_bytes((text or '').encode('utf-8', 'replace'))


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path):
    with open(path, encoding='utf-8-sig') as handle:
        return json.load(handle)


def write_json(path, value):
    """Atomically replace a JSON file so a reader never sees half a report."""
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    text = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)
    fd, temp = tempfile.mkstemp(prefix='.hds-json-', dir=parent or '.')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as handle:
            handle.write(text)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def write_text(path, text):
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='\n') as handle:
        handle.write(text if text is not None else '')


def run(args, *, easyeda=None, timeout=DEFAULT_TIMEOUT_SEC, cwd=None,
        env=None):
    """Run one CLI command and return a JSON-friendly record.

    Never raises for a missing executable, a timeout or non-JSON output: a
    caller deciding pass/fail needs the failure itself, not an exception.
    """
    argv = [easyeda_executable(easyeda)] + [str(item) for item in args]
    offline_guard.check_executable(argv, context='pcb_cli.run')
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
    payload = _parse_payload(stdout)
    ok = bool(code == 0 and isinstance(payload, dict) and
              payload.get('ok') is not False)
    return {
        'argv': argv,
        'exit': code,
        'ok': ok,
        'error': error,
        'stdout': stdout,
        'stderr': stderr,
        'payload': payload,
        'started_at': started,
        'ended_at': utc_now(),
    }


def _as_text(value):
    if value is None:
        return ''
    if isinstance(value, bytes):
        return value.decode('utf-8', 'replace')
    return str(value)


def _parse_payload(text):
    text = (text or '').strip()
    if not text:
        return None
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def result(payload):
    """Return the ``result`` mapping of a CLI payload (or an empty dict)."""
    if isinstance(payload, dict) and isinstance(payload.get('result'), dict):
        return payload['result']
    return {}


def payload_ok(record):
    """True when the command exited 0 and its JSON envelope says ok."""
    payload = record.get('payload')
    return bool(record.get('exit') == 0 and isinstance(payload, dict) and
                payload.get('ok') is not False)


def exit_ok(record):
    """True for a zero exit; human-readable commands emit no JSON envelope.

    ``doc switch`` and ``pcb dump --out`` print a human line, not JSON.  A
    caller that only needs the command's success should use this, while a
    caller that consumes structured result fields keeps ``payload_ok``.
    """
    if record.get('exit') != 0:
        return False
    payload = record.get('payload')
    return not (isinstance(payload, dict) and payload.get('ok') is False)


def command_record(record, *, stdout_path=None, stderr_path=None):
    """Compact provenance for a manifest: hashes and paths, never raw text."""
    result_payload = result(record.get('payload'))
    item = {
        'argv': record.get('argv') or [],
        'exit': record.get('exit'),
        'ok': exit_ok(record),
        'started_at': record.get('started_at'),
        'ended_at': record.get('ended_at'),
        'stdout_sha256': sha256_text(record.get('stdout') or ''),
        'stderr_sha256': sha256_text(record.get('stderr') or ''),
    }
    if record.get('error'):
        item['error'] = record['error']
    if result_payload:
        item['result_keys'] = sorted(result_payload)
    if stdout_path:
        item['stdout_path'] = stdout_path
        write_text(stdout_path, record.get('stdout') or '')
    if stderr_path:
        item['stderr_path'] = stderr_path
        write_text(stderr_path, record.get('stderr') or '')
    return item


def file_record(path, *, role=None, stage=None):
    """Artifact identity used by manifests and case verification."""
    item = {
        'path': path,
        'sha256': sha256_file(path),
        'bytes': os.path.getsize(path),
    }
    if role:
        item['role'] = role
    if stage:
        item['stage'] = stage
    return item


def check_payload(record, expect_result=True):
    """Raise ValueError for a failed envelope; return the result mapping.

    Tools that must fail closed on an unreadable check use this.  Tools that
    aggregate evidence should inspect ``record`` instead.
    """
    if not payload_ok(record):
        raise ValueError('CLI failed: exit=%s error=%s stderr=%s' % (
            record.get('exit'), record.get('error'),
            (record.get('stderr') or '')[:400]))
    value = result(record.get('payload'))
    if expect_result and not value:
        raise ValueError('CLI returned no result object')
    return value
