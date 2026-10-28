"""Engineering units with one canonical base unit per physical family.

Inputs may be written as a bare number (meaning the family's canonical unit),
a string with an SI suffix (``"4.7k"``, ``"100nF"``, ``"2.5V"``, ``"4k7"``) or
an explicit ``{"value": ..., "unit": ...}`` object.  All three normalise to an
exact Fraction in the canonical unit; the canonical unit is echoed back in the
result so a caller never has to guess what a number meant.

Deliberately *not* supported: unitless mixing, imperial units, and offset
conversions such as degC -> K (a temperature *range* is not a temperature
*value*, and this package never needs the latter).
"""
from __future__ import annotations

import re
from fractions import Fraction

from .errors import InputInvalid
from .numeric import parse_number

# prefix -> power of ten
_PREFIXES = {
    'p': Fraction(1, 10 ** 12),
    'n': Fraction(1, 10 ** 9),
    'u': Fraction(1, 10 ** 6),
    'm': Fraction(1, 10 ** 3),
    'k': Fraction(10 ** 3),
    'K': Fraction(10 ** 3),
    'M': Fraction(10 ** 6),
    'G': Fraction(10 ** 9),
}

_UNIT_ALIASES = {
    'ohm': 'ohm', 'ohms': 'ohm', 'Ohm': 'ohm', 'OHM': 'ohm', 'R': 'ohm',
    'Ω': 'ohm', 'Ω'.encode('utf-8').decode('utf-8'): 'ohm', '\u03a9': 'ohm',
    'farad': 'F', 'Farad': 'F', 'f': 'F',
    'volt': 'V', 'Volt': 'V', 'v': 'V',
    'amp': 'A', 'Ampere': 'A', 'ampere': 'A', 'a': 'A',
    'sec': 's', 'second': 's', 'seconds': 's',
    'hertz': 'Hz',
    'watt': 'W', 'Watt': 'W',
    'celsius': 'degC', 'degC': 'degC', 'C': 'degC', '°C': 'degC', '\u2103': 'degC',
    'pct': '%', 'percent': '%',
    'henry': 'H', 'Henry': 'H', 'henries': 'H',
    'coulomb': 'coulomb', 'Coulomb': 'coulomb',
}

_FAMILIES = {
    'voltage': {'unit': 'V', 'units': {'V': 1, 'mV': Fraction(1, 1000), 'uV': Fraction(1, 10 ** 6), 'kV': 1000}},
    'current': {'unit': 'A', 'units': {'A': 1, 'mA': Fraction(1, 1000), 'uA': Fraction(1, 10 ** 6),
                                       'nA': Fraction(1, 10 ** 9), 'pA': Fraction(1, 10 ** 12)}},
    'resistance': {'unit': 'ohm', 'units': {'ohm': 1, 'kohm': 1000, 'Mohm': 10 ** 6,
                                            'mohm': Fraction(1, 1000), 'Gohm': 10 ** 9}},
    'capacitance': {'unit': 'F', 'units': {'F': 1, 'mF': Fraction(1, 1000), 'uF': Fraction(1, 10 ** 6),
                                           'nF': Fraction(1, 10 ** 9), 'pF': Fraction(1, 10 ** 12)}},
    'inductance': {'unit': 'H', 'units': {'H': 1, 'mH': Fraction(1, 1000), 'uH': Fraction(1, 10 ** 6),
                                          'nH': Fraction(1, 10 ** 9)}},
    'time': {'unit': 's', 'units': {'s': 1, 'ms': Fraction(1, 1000), 'us': Fraction(1, 10 ** 6),
                                    'ns': Fraction(1, 10 ** 9), 'ps': Fraction(1, 10 ** 12)}},
    'frequency': {'unit': 'Hz', 'units': {'Hz': 1, 'kHz': 1000, 'MHz': 10 ** 6, 'GHz': 10 ** 9}},
    'power': {'unit': 'W', 'units': {'W': 1, 'mW': Fraction(1, 1000), 'uW': Fraction(1, 10 ** 6)}},
    'charge': {'unit': 'coulomb', 'units': {'coulomb': 1, 'mC': Fraction(1, 1000),
                                            'uC': Fraction(1, 10 ** 6), 'nC': Fraction(1, 10 ** 9)}},
    'temperature': {'unit': 'degC', 'units': {'degC': 1}},
    'percent': {'unit': '%', 'units': {'%': 1}},
    'ratio': {'unit': '1', 'units': {'1': 1}},
}

#: Families whose bare prefix token is accepted as a unit (``100n`` -> 100 nF).
_PREFIX_STYLES = {'capacitance': 'F', 'resistance': 'ohm'}

_NUMBER_RE = re.compile(r'^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$')
_SUFFIX_RE = re.compile(
    r'^([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*'
    r'([A-Za-z\u00b5\u03bc\u03a9\u00b0\u2103%]+)?$')
_INFIX_RE = re.compile(r'^(\d+)([pnu\u00b5\u03bcmkKM])(\d+)$')


def canonical_unit(family):
    """Return the canonical base unit of a family (raises on unknown family)."""
    if family not in _FAMILIES:
        raise InputInvalid('unknown unit family %r' % (family,))
    return _FAMILIES[family]['unit']


def known_families():
    return sorted(_FAMILIES)


def _normalise_unit_token(token):
    token = token.replace('\u00b5', 'u').replace('\u03bc', 'u')  # micro sign / greek mu
    return _UNIT_ALIASES.get(token, token)


def unit_factor(family, token):
    """Return the Fraction factor converting ``token`` to the family base unit."""
    if family not in _FAMILIES:
        raise InputInvalid('unknown unit family %r' % (family,))
    normalised = _normalise_unit_token(token)
    units = _FAMILIES[family]['units']
    if normalised in units:
        return Fraction(units[normalised])
    # Split "mV" -> ("m", "V") etc.  Longest base symbol first ("ohm" before "m").
    for base in sorted(units, key=len, reverse=True):
        if normalised.endswith(base) and len(normalised) > len(base):
            prefix = normalised[:-len(base)]
            if prefix in _PREFIXES:
                return Fraction(units[base]) * _PREFIXES[prefix]
    style = _PREFIX_STYLES.get(family)
    if style and normalised in _PREFIXES:
        return Fraction(_PREFIXES[normalised])
    raise InputInvalid('unit %r is not valid for %s (allowed: %s)'
                       % (token, family, ', '.join(sorted(units))))


def parse_quantity(value, family, field='value'):
    """Parse a quantity into an exact Fraction expressed in the canonical unit."""
    base = canonical_unit(family)
    if isinstance(value, dict):
        if 'value' not in value or 'unit' not in value:
            raise InputInvalid('quantity object needs "value" and "unit"', field=field)
        amount = parse_number(value['value'], field=field + '.value')
        unit = value['unit']
        if not isinstance(unit, str) or not unit.strip():
            raise InputInvalid('unit must be a non-empty string', field=field + '.unit')
        return amount * unit_factor(family, unit.strip())
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise InputInvalid('empty quantity string', field=field)
        match = _INFIX_RE.match(text)
        if match and family == 'resistance':
            whole, prefix, decimal = match.groups()
            return Fraction(int(whole) * 10 + int(decimal)) * _PREFIXES[prefix]
        match = _SUFFIX_RE.match(text)
        if not match:
            raise InputInvalid('cannot parse quantity %r' % (value,), field=field)
        number_text, token = match.groups()
        amount = parse_number(number_text, field=field)
        if token is None:
            return amount
        return amount * unit_factor(family, token)
    return parse_number(value, field=field)


def quantity_json(value, family, digits=12):
    """Encode a Fraction as ``{"value": ..., "unit": "<canonical>"}``."""
    from .numeric import to_json_number
    return {'value': to_json_number(value, digits), 'unit': canonical_unit(family)}


def display(value, family, digits=6):
    """Render ``"4700 ohm"``-style text for reports and messages."""
    from .numeric import format_number
    return '%s %s' % (format_number(value, digits), canonical_unit(family))
