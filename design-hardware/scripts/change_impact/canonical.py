"""Canonicalisation, hashing and finite-number guards.

Two rules keep reports reproducible and honest:

* every number must be a finite JSON number (``bool`` is not a number, ``NaN``
  and ``inf`` are rejected) because a non-finite cost would silently break
  budget comparisons;
* a content hash covers canonical JSON with sorted keys and no whitespace, so
  reformatting an input does not change its identity but any semantic edit does.

No wall-clock value is ever produced here; the tool is deterministic and does
not pretend a fresh capture happened.
"""
from __future__ import annotations

import hashlib
import json
import math

from .errors import InputInvalid, issue


class _Unsupported:
    def __repr__(self):
        return '<unsupported>'


def is_finite_number(value):
    """True only for int/float (not bool) finite values."""
    return type(value) in (int, float) and math.isfinite(value)


def number(value, *, where, code='non_finite_number', allow_none=False):
    """Validated finite number, with a stable error code otherwise."""
    if value is None and allow_none:
        return None
    if type(value) is bool or not is_finite_number(value):
        raise InputInvalid(
            f'{where}: a finite number is required',
            code=code, where=where,
            issues=[issue(code, 'expected a finite JSON number (bool/NaN/inf '
                                'are not numbers)', where=where)])
    return value


def positive_number(value, *, where, code='non_positive_number', allow_zero=False):
    value = number(value, where=where, code=code)
    if value < 0 or (value == 0 and not allow_zero):
        raise InputInvalid(
            f'{where}: a {"non-negative" if allow_zero else "positive"} number is required',
            code=code, where=where)
    return value


def non_negative_int(value, *, where, code='invalid_integer'):
    if type(value) is not int or value < 0:
        raise InputInvalid(f'{where}: a non-negative integer is required',
                           code=code, where=where)
    return value


def text(value, *, where, allow_empty=False, code='invalid_text'):
    if not isinstance(value, str) or (not allow_empty and not value):
        raise InputInvalid(f'{where}: a non-empty string is required',
                           code=code, where=where)
    return value


def list_of(value, *, where, code='invalid_list'):
    if not isinstance(value, list):
        raise InputInvalid(f'{where}: a list is required', code=code, where=where)
    return value


def mapping(value, *, where, code='invalid_object'):
    if not isinstance(value, dict):
        raise InputInvalid(f'{where}: an object is required', code=code, where=where)
    return value


def canonical_value(value, *, where):
    """Return a JSON-normalised copy; reject non-finite and unsupported types.

    Sets are sorted tuples, tuples become lists, and dict keys must be strings.
    """
    if value is None or isinstance(value, (str, bool)):
        return value
    if is_finite_number(value):
        return int(value) if isinstance(value, int) else float(value)
    if isinstance(value, (list, tuple)):
        return [canonical_value(item, where=f'{where}[{index}]')
                for index, item in enumerate(value)]
    if isinstance(value, dict):
        result = {}
        for key in value:
            if not isinstance(key, str):
                raise InputInvalid(f'{where}: non-string object key',
                                   code='invalid_key', where=where)
            result[key] = canonical_value(value[key], where=f'{where}.{key}')
        return result
    raise InputInvalid(
        f'{where}: unsupported JSON value {type(value).__name__}',
        code='unsupported_value', where=where)


def canonical_json(value):
    """Canonical JSON text: sorted keys, compact separators, no NaN."""
    return json.dumps(canonical_value(value, where='value'),
                      sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False)


def sha256_text(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def sha256_bytes(value):
    return hashlib.sha256(value).hexdigest()


def sha256_value(value):
    """Stable hash of a JSON value, prefixed like the rest of the project."""
    return 'sha256:' + sha256_text(canonical_json(value))


def normalize_hash(value, *, where, code='invalid_hash'):
    """Accept ``sha256:<64 hex>`` or a bare 64-char digest."""
    text_value = text(value, where=where, code=code)
    digest = text_value[7:] if text_value.startswith('sha256:') else text_value
    if len(digest) != 64 or any(ch not in '0123456789abcdef' for ch in digest.lower()):
        raise InputInvalid(
            f'{where}: expected sha256:<64 hex> or a 64-char hex digest',
            code=code, where=where)
    return 'sha256:' + digest.lower()


def fingerprint(pairs):
    """Deterministic fingerprint of sorted ``(label, value)`` pairs.

    Used for evidence reuse: two revisions are semantically interchangeable for
    a covered attribute only when every covered pair hashes identically.
    """
    material = [[label, canonical_value(value, where=f'fingerprint.{label}')]
                for label, value in sorted(pairs, key=lambda item: str(item[0]))]
    return sha256_value(material)
