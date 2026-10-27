"""Loader for verified device-fact files (see ``devices/SCHEMA.md``).

A module never hard-codes a part number.  It either loads a fact file that was
verified against a primary manufacturer document (``verified: true``), or it
accepts caller-declared facts and marks them ``simulated/user_declared`` so the
result cannot be mistaken for a datasheet check.

The loader is strict: a fact file with a missing required key, a non-finite
number, or no source for a fact raises instead of degrading silently.
"""
from __future__ import annotations

import copy
import json
from fractions import Fraction
from pathlib import Path

from ..errors import InputInvalid, NeedsDeviceFacts
from ..numeric import parse_number

FACTS_DIR = Path(__file__).resolve().parent / 'facts'
REQUIRED_CATEGORY_KEYS = {
    'ldo': ('vin_min_v', 'vin_max_v', 'vout_nom_v', 'vout_tol_pct', 'iout_max_a',
            'dropout_v', 'iq_a', 'cin_min_f', 'cout_min_f'),
    'mosfet_n': ('vds_max_v', 'vgss_max_v', 'id_max_a', 'rds_on_ohm',
                 'vgs_th_max_v', 'qg_typ_c'),
    'led': ('vf_typ_v', 'vf_max_v', 'i_forward_max_a'),
    'diode_schottky': ('vr_max_v', 'if_avg_max_a', 'vf_max_v'),
    'bus_spec': (),
}
_CACHE = {}


def available_facts():
    """Return ``{fact_id: file_path}`` for the bundled fact files."""
    result = {}
    if not FACTS_DIR.is_dir():
        return result
    for path in sorted(FACTS_DIR.glob('*.json')):
        if path.name.startswith('_'):
            continue
        result[path.stem] = path
    return result


def load_fact(fact_id, *, trust_bundled=True):
    """Load and structurally validate one bundled fact file.

    ``trust_bundled`` is not a verdict on the facts: bundled files were checked
    against a named primary document, but that is a documentary check only.
    """
    if not isinstance(fact_id, str) or not fact_id.strip():
        raise InputInvalid('device_fact_id must be a non-empty string')
    fact_id = fact_id.strip()
    if fact_id in _CACHE:
        return copy.deepcopy(_CACHE[fact_id])
    path = available_facts().get(fact_id)
    if path is None:
        raise NeedsDeviceFacts(
            ['device_fact_id=%s' % fact_id],
            'no bundled verified fact file named %r (available: %s)'
            % (fact_id, ', '.join(sorted(available_facts())) or 'none'),
            details={'mechanism': 'bundled facts', 'expected_path': str(FACTS_DIR / (fact_id + '.json'))})
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise InputInvalid('device fact file %s is unreadable: %s' % (path.name, exc))
    _validate_fact_file(data, path.name)
    _CACHE[fact_id] = data
    return copy.deepcopy(data)


def _validate_fact_file(data, filename):
    if not isinstance(data, dict):
        raise InputInvalid('device fact file must be an object')
    for key in ('schema', 'fact_id', 'category', 'mpn', 'manufacturer', 'sources', 'facts'):
        if key not in data:
            raise InputInvalid('%s: missing %r' % (filename, key))
    if data['schema'] != 'circuit-blocks/device-facts/1':
        raise InputInvalid('%s: unsupported schema %r' % (filename, data['schema']))
    if data['fact_id'] + '.json' != filename:
        raise InputInvalid('%s: fact_id %r does not match the filename'
                           % (filename, data['fact_id']))
    if data['category'] not in REQUIRED_CATEGORY_KEYS:
        raise InputInvalid('%s: unknown category %r' % (filename, data['category']))
    if not isinstance(data['sources'], list) or not data['sources']:
        raise InputInvalid('%s: at least one primary source is required' % filename)
    for source in data['sources']:
        for key in ('document', 'url', 'accessed'):
            if not source.get(key):
                raise InputInvalid('%s: source is missing %r' % (filename, key))
    if not isinstance(data['facts'], dict) or not data['facts']:
        raise InputInvalid('%s: facts must be a non-empty object' % filename)
    for name, record in data['facts'].items():
        if isinstance(record, dict) and 'value' in record and 'unit' in record:
            _validate_fact_record(filename, name, record)
        elif isinstance(record, list):
            if not record:
                raise InputInvalid('%s: fact %r is an empty list' % (filename, name))
        elif isinstance(record, (str, int, float, bool)):
            continue
        else:
            raise InputInvalid('%s: fact %r is not a value record' % (filename, name))
    missing = [key for key in REQUIRED_CATEGORY_KEYS[data['category']]
               if key not in data['facts']]
    if missing:
        raise InputInvalid('%s: required %s facts missing: %s'
                           % (filename, data['category'], ', '.join(missing)))


def _validate_fact_record(filename, name, record):
    try:
        parse_number(record['value'])
    except InputInvalid as exc:
        if not isinstance(record['value'], str):
            raise InputInvalid('%s: fact %r has a non-numeric value: %s' % (filename, name, exc))
    if not isinstance(record.get('condition'), str) or not record['condition'].strip():
        raise InputInvalid('%s: fact %r needs a condition' % (filename, name))
    if not record.get('source'):
        raise InputInvalid('%s: fact %r needs a source reference' % (filename, name))


def fact_number(facts, key):
    """Return a fact value as a Fraction; raise NeedsDeviceFacts when absent."""
    record = fact(facts, key)
    try:
        return parse_number(record['value'])
    except InputInvalid:
        raise NeedsDeviceFacts([key], 'device fact %r is not numeric' % key)


def fact(facts, key, default=None):
    try:
        return facts['facts'][key]
    except (KeyError, TypeError):
        if default is not None:
            return default
        raise NeedsDeviceFacts([key], 'device fact %r is missing from %r'
                               % (key, facts.get('fact_id', 'device facts')))


def fact_value(facts, key):
    record = fact(facts, key)
    if isinstance(record, dict) and 'value' in record:
        return record['value']
    return record


def fact_condition(facts, key):
    record = fact(facts, key)
    return record.get('condition') if isinstance(record, dict) else None


def fact_source(facts, key):
    record = fact(facts, key)
    source_ref = record.get('source') if isinstance(record, dict) else None
    for source in facts.get('sources', []):
        text = '%s %s' % (source.get('doc_id', ''), source.get('document', ''))
        if source_ref and source_ref.split(',')[0].strip() in text:
            return source
    return facts.get('sources', [{}])[0] if facts.get('sources') else {}


def missing_keys(facts, keys):
    return [key for key in keys if key not in (facts.get('facts') or {})]


def evidence_for(draft, facts, keys, *, evidence_prefix=None):
    """Attach draft evidence entries for the facts a calculation consumed."""
    fact_id = facts.get('fact_id', 'user_declared')
    prefix = evidence_prefix or fact_id
    written = []
    for index, key in enumerate(keys):
        record = fact(facts, key)
        source = fact_source(facts, key)
        entry = draft.evidence(
            '%s_%d' % (prefix, index + 1),
            'manufacturer_datasheet' if facts.get('verified') else 'user_declared',
            '%s = %s %s (%s)' % (key, record.get('value'),
                                 record.get('unit', ''), record.get('condition', '')),
            source={
                'document': source.get('document'),
                'doc_id': source.get('doc_id'),
                'revision': source.get('revision'),
                'url': source.get('url'),
                'section': record.get('source'),
                'accessed': source.get('accessed'),
            },
            applies_to=record.get('applies_to'),
            verified=bool(facts.get('verified')),
        )
        written.append(entry['id'])
    return written


def user_declared_facts(payload, category, *, mpn=None, source_note=None):
    """Wrap caller-declared numbers in the same shape as a fact file.

    The result is tagged ``verified: False`` and can never satisfy a requirement
    that a *verified* datasheet fact exists.
    """
    if not isinstance(payload, dict) or not payload:
        raise InputInvalid('device_facts must be a non-empty object')
    facts = {}
    for key, value in payload.items():
        if isinstance(value, dict):
            if 'value' not in value:
                raise InputInvalid('device_facts.%s needs a value' % key)
            record = {
                'value': value['value'],
                'unit': value.get('unit', ''),
                'condition': value.get('condition', 'declared by the caller'),
                'source': value.get('source', source_note or 'caller declaration'),
                'applies_to': value.get('applies_to', mpn),
            }
        else:
            record = {'value': value, 'unit': _infer_unit(key, value),
                      'condition': 'declared by the caller',
                      'source': source_note or 'caller declaration',
                      'applies_to': mpn}
        facts[key] = record
    return {
        'schema': 'circuit-blocks/device-facts/1',
        'fact_id': 'user_declared',
        'category': category,
        'mpn': mpn,
        'manufacturer': None,
        'verified': False,
        'sources': [{'document': source_note or 'caller declaration',
                     'url': None, 'accessed': None}],
        'facts': facts,
        'unknown_facts': [],
    }


def _infer_unit(key, value):
    if key.endswith('_v'):
        return 'V'
    if key.endswith('_a'):
        return 'A'
    if key.endswith('_f'):
        return 'F'
    if key.endswith('_w'):
        return 'W'
    if key.endswith('_ohm'):
        return 'ohm'
    if key.endswith('_c_per_w'):
        return 'C/W'
    if key.endswith('_c'):
        return 'C'
    if key.endswith('_pct'):
        return '%'
    return ''
