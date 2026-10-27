"""Declarative input schemas and strict normalisation.

A module declares ``INPUT_SCHEMA`` as a mapping of field name to field spec;
:func:`validate_inputs` turns the caller's JSON into a :class:`NormalizedInput`
holding exact Fractions, canonical units and typed accessors.  Three rules keep
the generators honest:

* unknown or misspelled fields are rejected (silently ignoring a constraint
  would produce a confidently wrong circuit);
* booleans, NaN and infinities never pass as numbers;
* a range must have both bounds, so a "typical" value cannot masquerade as a
  worst case.

Fields that describe *part facts* are declared optional and consumed by the
module, which then reports ``needs_device_facts`` naming exactly what is
missing.  Absence of an optional field is never silently replaced by a
plausible default.
"""
from __future__ import annotations

from fractions import Fraction

from .errors import InputInvalid
from .numeric import parse_number, to_json_number
from .ranges import Interval, parse_interval, parse_point
from .units import canonical_unit, quantity_json

_KINDS = ('quantity', 'range', 'enum', 'bool', 'integer', 'number', 'string',
          'object', 'array')


class NormalizedInput(object):
    """Typed view over validated inputs plus the normalised JSON echo."""

    def __init__(self, schema, values, provided):
        self._schema = schema
        self._values = values
        self._provided = set(provided)

    # -- presence -------------------------------------------------------
    def __contains__(self, name):
        return name in self._values

    def provided(self, name):
        return name in self._provided

    def missing(self, names):
        return [name for name in names if name not in self._provided]

    # -- typed accessors ------------------------------------------------
    def get(self, name, default=None):
        return self._values.get(name, default)

    def quantity(self, name):
        self._require_kind(name, 'quantity')
        return self._values[name]

    def interval(self, name):
        self._require_kind(name, 'range')
        return self._values[name]

    def enum(self, name):
        self._require_kind(name, 'enum')
        return self._values[name]

    def string(self, name):
        self._require_kind(name, 'string')
        return self._values[name]

    def boolean(self, name):
        self._require_kind(name, 'bool')
        return bool(self._values[name])

    def integer(self, name):
        self._require_kind(name, 'integer')
        return self._values[name]

    def number(self, name):
        self._require_kind(name, 'number')
        return self._values[name]

    def obj(self, name):
        self._require_kind(name, 'object')
        return self._values[name]

    def items(self, name):
        self._require_kind(name, 'array')
        return self._values[name]

    def _require_kind(self, name, kind):
        if name not in self._schema:
            raise KeyError(name)
        if self._schema[name]['kind'] != kind:
            raise TypeError('%s is a %s field, not %s'
                            % (name, self._schema[name]['kind'], kind))

    # -- echo -----------------------------------------------------------
    def as_json(self):
        """Normalised JSON echo (canonical units, no caller spelling)."""
        return _echo_object(self._schema, self._values)


def _echo_object(schema, values):
    return {name: _echo_field(schema.get(name, {}), value)
            for name, value in values.items()}


def _echo_field(spec, value):
    kind = spec.get('kind')
    if kind == 'quantity':
        return quantity_json(value, spec['family'])
    if kind == 'range':
        return value.as_json(spec['family'])
    if kind == 'number':
        return to_json_number(value)
    if kind == 'integer':
        return int(value)
    if kind == 'bool':
        return bool(value)
    if kind == 'object':
        if hasattr(value, 'as_json'):
            return value.as_json()
        nested = spec.get('fields', {})
        return _echo_object(nested, value) if isinstance(value, dict) else value
    if kind == 'array':
        item_spec = spec.get('items', {})
        return [_echo_field(item_spec, item) for item in value]
    return value


def validate_inputs(schema, raw, *, prefix=''):
    """Validate ``raw`` against ``schema`` and return a :class:`NormalizedInput`."""
    if not isinstance(raw, dict):
        raise InputInvalid('input must be a JSON object', field=prefix.rstrip('.') or 'input')
    unknown = sorted(set(raw) - set(schema))
    if unknown:
        raise InputInvalid('unknown field(s): %s (known: %s)'
                           % (', '.join(unknown), ', '.join(sorted(schema))),
                           field=prefix.rstrip('.') or 'input')
    values, provided = {}, set()
    for name, spec in schema.items():
        path = prefix + name
        if name in raw:
            values[name] = _parse_field(spec, raw[name], path)
            provided.add(name)
        elif 'default' in spec:
            values[name] = _parse_field(spec, spec['default'], path)
        elif spec.get('required'):
            raise InputInvalid('required field is missing', field=path)
    return NormalizedInput(schema, values, provided)


def _parse_field(spec, value, path):
    kind = spec.get('kind')
    if kind not in _KINDS:
        raise InputInvalid('schema error: unknown field kind %r' % (kind,), field=path)
    if kind == 'quantity':
        return parse_point(value, spec['family'], field=path,
                           nonnegative=spec.get('nonnegative', False),
                           positive=spec.get('positive', False))
    if kind == 'range':
        interval = parse_interval(value, spec['family'], field=path,
                                  nonnegative=spec.get('nonnegative', False),
                                  positive=spec.get('positive', False))
        if 'min_width' in spec and interval.width < parse_number(spec['min_width']):
            raise InputInvalid('range is narrower than %s' % spec['min_width'], field=path)
        return interval
    if kind == 'enum':
        if not isinstance(value, str):
            raise InputInvalid('expected one of: %s' % ', '.join(spec['values']), field=path)
        if value not in spec['values']:
            raise InputInvalid('%r is not one of: %s'
                              % (value, ', '.join(spec['values'])), field=path)
        return value
    if kind == 'bool':
        if not isinstance(value, bool):
            raise InputInvalid('expected true/false', field=path)
        return value
    if kind == 'integer':
        if isinstance(value, bool) or not isinstance(value, int):
            raise InputInvalid('expected an integer', field=path)
        _check_bounds(spec, Fraction(value), path)
        return value
    if kind == 'number':
        number = parse_number(value, field=path)
        _check_bounds(spec, number, path)
        return number
    if kind == 'string':
        if not isinstance(value, str) or not value.strip():
            raise InputInvalid('expected a non-empty string', field=path)
        if 'values' in spec and value not in spec['values']:
            raise InputInvalid('%r is not one of: %s' % (value, ', '.join(spec['values'])), field=path)
        return value
    if kind == 'object':
        nested_schema = spec.get('fields', {})
        nested = validate_inputs(nested_schema, value, prefix=path + '.')
        return nested
    if kind == 'array':
        if not isinstance(value, list):
            raise InputInvalid('expected a list', field=path)
        if not value:
            raise InputInvalid('list must not be empty', field=path)
        if 'min_items' in spec and len(value) < spec['min_items']:
            raise InputInvalid('at least %d items required' % spec['min_items'], field=path)
        item_spec = spec['items']
        return [_parse_field(item_spec, item, '%s[%d]' % (path, index))
                for index, item in enumerate(value)]
    raise InputInvalid('schema error: unhandled field kind %r' % (kind,), field=path)


def _check_bounds(spec, value, path):
    if 'min_value' in spec and value < parse_number(spec['min_value']):
        raise InputInvalid('must be >= %s' % spec['min_value'], field=path)
    if 'max_value' in spec and value > parse_number(spec['max_value']):
        raise InputInvalid('must be <= %s' % spec['max_value'], field=path)


def describe_schema(schema):
    """Human/JSON description used by ``python -m circuit_blocks describe``."""
    fields = []
    for name in schema:
        spec = schema[name]
        entry = {
            'name': name,
            'kind': spec['kind'],
            'required': bool(spec.get('required', False)),
            'doc': spec.get('doc', ''),
        }
        if 'family' in spec:
            entry['family'] = spec['family']
            entry['unit'] = canonical_unit(spec['family'])
        if 'values' in spec:
            entry['values'] = list(spec['values'])
        if 'default' in spec:
            if spec['kind'] in ('quantity', 'range', 'number'):
                entry['default'] = _default_echo(spec)
            else:
                entry['default'] = spec['default']
        if spec['kind'] == 'object':
            entry['fields'] = describe_schema(spec.get('fields', {}))
        if spec['kind'] == 'array':
            entry['items'] = describe_schema({'item': spec['items']})[0]
        if spec.get('nonnegative'):
            entry['nonnegative'] = True
        if spec.get('positive'):
            entry['positive'] = True
        fields.append(entry)
    return fields


def _default_echo(spec):
    try:
        value = _parse_field(spec, spec['default'], 'default')
    except InputInvalid:
        return spec['default']
    if spec['kind'] == 'quantity':
        return quantity_json(value, spec['family'])
    if spec['kind'] == 'range':
        return value.as_json(spec['family'])
    if spec['kind'] == 'number':
        return to_json_number(value)
    return value
