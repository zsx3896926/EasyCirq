"""Shared strict I/O helpers: JSON loading, hashing, atomic writes, diagnostics.

All numbers in generated artifacts are finite (``allow_nan=False``); duplicate
JSON keys, NaN/Infinity constants and ``true``/``false`` where a number is
required are rejected instead of being silently coerced.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

MAX_INPUT_BYTES = 4 * 1024 * 1024

ID_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$')
HEX64_RE = re.compile(r'^[0-9a-fA-F]{64}$')


class PlannerError(Exception):
    """Base error carrying a stable machine-readable code."""

    def __init__(self, message, *, code='ERROR', path=None):
        super().__init__(message)
        self.code = code
        self.path = path
        self.message = message

    def as_dict(self):
        return {'code': self.code, 'path': self.path, 'message': self.message}


class InputInvalid(PlannerError):
    """The input document is structurally or semantically invalid."""

    def __init__(self, diagnostics):
        super().__init__('input validation failed', code='E_INPUT_INVALID')
        self.diagnostics = list(diagnostics)

    def errors(self):
        return [item for item in self.diagnostics if item.get('severity') == 'error']


class UnitConflict(PlannerError):
    pass


def diagnostic(code, path, message, severity='error'):
    return {'code': code, 'path': path, 'message': message,
            'severity': severity}


class Diagnostics:
    """Ordered diagnostic collector used by schema/normalisation code."""

    def __init__(self):
        self.items = []

    def error(self, code, path, message):
        self.items.append(diagnostic(code, path, message, 'error'))

    def warning(self, code, path, message):
        self.items.append(diagnostic(code, path, message, 'warning'))

    def info(self, code, path, message):
        self.items.append(diagnostic(code, path, message, 'info'))

    @property
    def errors(self):
        return [item for item in self.items if item['severity'] == 'error']

    @property
    def warnings(self):
        return [item for item in self.items if item['severity'] == 'warning']

    def raise_if_errors(self):
        if self.errors:
            raise InputInvalid(self.items)

    def summary(self):
        counts = {'error': 0, 'warning': 0, 'info': 0}
        for item in self.items:
            counts[item['severity']] = counts.get(item['severity'], 0) + 1
        return counts


def _reject_duplicate_keys(pairs):
    data = {}
    for key, value in pairs:
        if key in data:
            raise ValueError('duplicate JSON key: %r' % key)
        data[key] = value
    return data


def read_json(path, *, max_bytes=MAX_INPUT_BYTES):
    """Read strict JSON from ``path`` (UTF-8 with optional BOM)."""
    try:
        raw = Path(path).read_bytes()
    except OSError as exc:
        raise PlannerError('cannot read %s: %s' % (path, exc), code='E_IO',
                           path=str(path))
    if len(raw) > max_bytes:
        raise PlannerError('input exceeds %d bytes' % max_bytes,
                           code='E_TOO_LARGE', path=str(path))

    def _no_constant(token):
        raise ValueError('non-finite JSON constant: %s' % token)

    try:
        return json.loads(raw.decode('utf-8-sig'),
                          object_pairs_hook=_reject_duplicate_keys,
                          parse_constant=_no_constant)
    except UnicodeDecodeError as exc:
        raise PlannerError('input is not valid UTF-8: %s' % exc,
                           code='E_ENCODING', path=str(path))
    except (ValueError, json.JSONDecodeError) as exc:
        raise PlannerError('invalid JSON: %s' % exc, code='E_JSON',
                           path=str(path))


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    return sha256_bytes(Path(path).read_bytes())


def canonical_text(obj):
    """Canonical JSON text for semantic hashing (sorted keys, no spaces).

    Free-text ``notes`` fields are documentation only: they never change a
    criterion, so they are excluded from the semantic hash.  Every structured
    value (ids, ranges, units, sources) still contributes.
    """
    return json.dumps(_canonicalise(_strip_free_text(obj)), sort_keys=True,
                      ensure_ascii=False, separators=(',', ':'),
                      allow_nan=False)


def _strip_free_text(value):
    if isinstance(value, dict):
        return {str(key): _strip_free_text(item)
                for key, item in value.items() if key != 'notes'}
    if isinstance(value, (list, tuple)):
        return [_strip_free_text(item) for item in value]
    return value


def semantic_sha256(obj):
    return sha256_bytes(canonical_text(obj).encode('utf-8'))


def _canonicalise(value):
    if isinstance(value, dict):
        return {str(key): _canonicalise(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonicalise(item) for item in value]
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError('non-finite number in semantic hash input')
        rounded = float('%.12g' % value)
        return 0.0 if rounded == 0 else rounded
    return value


def utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso_now():
    return utc_now().isoformat().replace('+00:00', 'Z')


def parse_timestamp(value, name='timestamp'):
    """Parse a timezone-aware ISO-8601 timestamp; naive times are rejected."""
    if not isinstance(value, str) or not value.strip():
        raise PlannerError('%s must be an ISO-8601 string' % name,
                           code='E_TIMESTAMP')
    text = value.strip()
    if text.endswith('Z'):
        text = text[:-1] + '+00:00'
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        raise PlannerError('%s is not a valid ISO-8601 timestamp: %r'
                           % (name, value), code='E_TIMESTAMP')
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PlannerError('%s must include a timezone offset' % name,
                           code='E_TIMESTAMP')
    return parsed


def check_not_future(value, name='timestamp', *, now=None):
    parsed = parse_timestamp(value, name)
    reference = now or utc_now()
    if parsed.astimezone(timezone.utc) > reference.astimezone(timezone.utc):
        raise PlannerError('%s is in the future: %s' % (name, value),
                           code='E_FUTURE_TIMESTAMP')
    return parsed


def check_attachment_path(value, name='path'):
    """Validate a relative attachment/evidence path (no traversal, no drive)."""
    if not isinstance(value, str) or not value.strip():
        raise PlannerError('%s must be a non-empty string' % name,
                           code='E_BAD_PATH')
    text = value.strip().replace('\\', '/')
    if len(text) > 300:
        raise PlannerError('%s is too long' % name, code='E_BAD_PATH')
    if text.startswith('/') or re.match(r'^[A-Za-z]:', text):
        raise PlannerError('%s must be relative, got %r' % (name, value),
                           code='E_PATH_ESCAPE')
    if '://' in text:
        raise PlannerError('%s must be a local relative path' % name,
                           code='E_BAD_PATH')
    parts = [part for part in text.split('/') if part not in ('', '.')]
    if not parts or any(part == '..' for part in parts):
        raise PlannerError('%s escapes the working directory: %r' % (name, value),
                           code='E_PATH_ESCAPE')
    if any(part.startswith('.') for part in parts):
        raise PlannerError('%s must not use hidden paths' % name,
                           code='E_BAD_PATH')
    return '/'.join(parts)


def resolve_within(root, relative):
    """Resolve ``relative`` under ``root`` and prove it cannot escape."""
    root = Path(root).resolve()
    target = (root / relative).resolve()
    if target != root and root not in target.parents:
        raise PlannerError('path escapes evidence root: %r' % relative,
                           code='E_PATH_ESCAPE')
    return target


def atomic_write_text(path, text):
    """Write UTF-8 text atomically (same directory temp file + os.replace)."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=str(target.parent),
                                prefix='.%s.' % target.name)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, str(target))
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def atomic_write_json(path, data):
    text = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    atomic_write_text(path, text)


def atomic_write_csv(path, rows):
    import csv
    import io

    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator='\n')
    for row in rows:
        writer.writerow(row)
    atomic_write_text(path, buffer.getvalue())


def is_number(value):
    return type(value) in (int, float) and math.isfinite(value)


def clamp_text(value, limit=400):
    text = str(value)
    return text if len(text) <= limit else text[:limit] + '...'
