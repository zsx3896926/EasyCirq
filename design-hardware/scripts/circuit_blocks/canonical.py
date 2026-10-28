"""Canonical JSON and content hashing.

Two outputs built from the same configuration must be byte-identical, and a
content hash must change whenever any *topology-bearing* field changes (a net,
a component value, a port, a calculation result, a status).  Presentation-only
fields — instance id, display name, generation metadata — are excluded so that
renaming an instance does not look like a different circuit.
"""
from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from fractions import Fraction

from .errors import InputInvalid


def canonical_text(value):
    """Deterministic JSON text: sorted keys, no insignificant whitespace."""
    return json.dumps(_normalise(value), sort_keys=True, separators=(',', ':'),
                      ensure_ascii=True, allow_nan=False)


def sha256_text(text):
    return 'sha256:' + hashlib.sha256(text.encode('utf-8')).hexdigest()


def content_hash(payload):
    """sha256 over the canonical form of a payload dict."""
    return sha256_text(canonical_text(payload))


def _normalise(value):
    if isinstance(value, dict):
        result = {}
        for key in value:
            if not isinstance(key, str):
                raise InputInvalid('JSON object keys must be strings')
            result[key] = _normalise(value[key])
        return result
    if isinstance(value, (list, tuple)):
        return [_normalise(item) for item in value]
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, Fraction):
        return _normalise_float(value)
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise InputInvalid('non-finite number cannot be hashed')
        return _normalise_float(Fraction(value))
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value != value or value in (float('inf'), float('-inf')):
            raise InputInvalid('non-finite number cannot be hashed')
        return float(value)
    raise InputInvalid('cannot canonicalise value of type %s' % type(value).__name__)


def _normalise_float(fraction):
    from .numeric import to_json_number
    return to_json_number(fraction, 12)


def payload_of(result):
    """Return the hash-bearing subset of a module result, in a fixed order."""
    keys = ('schema', 'module_type', 'template_version', 'status', 'status_reasons',
            'inputs', 'units', 'components', 'ports', 'connectivity',
            'calculations', 'constraints', 'evidence', 'unknowns', 'binding')
    return {key: result[key] for key in keys if key in result}


def payload_of_design(design):
    """Hash-bearing projection of a composed design.

    Instance ``display_name`` and the embedded full block results are excluded:
    the instance content hashes already pin the actual block content, so renaming
    an instance does not change the design's topology hash.
    """
    keys = ('schema', 'design_name', 'status', 'status_reasons', 'components',
            'ports', 'nets', 'connections', 'unbound_ports', 'conflicts',
            'incomplete', 'partition', 'binding')
    payload = {key: design[key] for key in keys if key in design}
    payload['instances'] = [{'instance_id': instance.get('instance_id'),
                             'module_type': instance.get('module_type'),
                             'template_version': instance.get('template_version'),
                             'status': instance.get('status'),
                             'content_hash': instance.get('content_hash')}
                            for instance in design.get('instances') or []]
    return payload
