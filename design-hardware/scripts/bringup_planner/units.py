"""Unit table and conversions.

Every value stored in the normalised model is in the canonical SI unit for its
quantity.  Inputs may be a bare number (interpreted as the canonical unit) or
an explicit ``{"value": ..., "unit": "..."}`` object.  Unknown units and
quantity/unit mismatches are hard errors: guessing a unit would silently change
a safety-relevant threshold.
"""
from __future__ import annotations

import math

CANONICAL_UNITS = {
    'voltage': 'V',
    'current': 'A',
    'resistance': 'ohm',
    'frequency': 'Hz',
    'time': 's',
    'temperature': 'degC',
    'power': 'W',
    'capacitance': 'F',
    'ratio': '1',
}

# unit -> (quantity, factor-to-canonical)
UNIT_TABLE = {
    'V': ('voltage', 1.0),
    'mV': ('voltage', 1e-3),
    'uV': ('voltage', 1e-6),
    'kV': ('voltage', 1e3),
    'A': ('current', 1.0),
    'mA': ('current', 1e-3),
    'uA': ('current', 1e-6),
    'nA': ('current', 1e-9),
    'ohm': ('resistance', 1.0),
    'Ohm': ('resistance', 1.0),
    '\u03a9': ('resistance', 1.0),
    'kohm': ('resistance', 1e3),
    'k\u03a9': ('resistance', 1e3),
    'Mohm': ('resistance', 1e6),
    'M\u03a9': ('resistance', 1e6),
    'mohm': ('resistance', 1e-3),
    'Hz': ('frequency', 1.0),
    'kHz': ('frequency', 1e3),
    'MHz': ('frequency', 1e6),
    'GHz': ('frequency', 1e9),
    's': ('time', 1.0),
    'ms': ('time', 1e-3),
    'us': ('time', 1e-6),
    '\u00b5s': ('time', 1e-6),
    '\u03bcs': ('time', 1e-6),
    'ns': ('time', 1e-9),
    'min': ('time', 60.0),
    'degC': ('temperature', 1.0),
    '\u00b0C': ('temperature', 1.0),
    'degF': ('temperature', None),  # affine, handled separately
    'W': ('power', 1.0),
    'mW': ('power', 1e-3),
    'F': ('capacitance', 1.0),
    'mF': ('capacitance', 1e-3),
    'uF': ('capacitance', 1e-6),
    'nF': ('capacitance', 1e-9),
    'pF': ('capacitance', 1e-12),
    '1': ('ratio', 1.0),
    '%': ('ratio', 0.01),
}

_UNIT_ALIASES = {
    'v': 'V',
    'mv': 'mV',
    'uv': 'uV',
    'kv': 'kV',
    'a': 'A',
    'ma': 'mA',
    'ua': 'uA',
    'na': 'nA',
    'OHM': 'ohm',
    'ohms': 'ohm',
    'k\u03a9': 'k\u03a9',
    'kOhm': 'kohm',
    'kohm': 'kohm',
    'MOhm': 'Mohm',
    'mOhm': 'mohm',
    'hz': 'Hz',
    'khz': 'kHz',
    'mhz': 'MHz',
    'sec': 's',
    'secs': 's',
    's': 's',
    'ms': 'ms',
    'us': 'us',
    'ns': 'ns',
    'degc': 'degC',
    'c': 'degC',
    'w': 'W',
    'mw': 'mW',
    'uf': 'uF',
    'nf': 'nF',
    'pf': 'pF',
    'mhz_': 'MHz',
}


class UnitError(ValueError):
    """Unknown unit or unit/quantity mismatch."""


def normalise_unit(unit):
    if not isinstance(unit, str) or not unit.strip():
        raise UnitError('unit must be a non-empty string')
    text = unit.strip()
    if text in UNIT_TABLE:
        return text
    if text in _UNIT_ALIASES:
        return _UNIT_ALIASES[text]
    stripped = text.rstrip('.')
    if stripped in UNIT_TABLE:
        return stripped
    lowered = stripped.lower()
    for candidate in UNIT_TABLE:
        if candidate.lower() == lowered:
            return candidate
    raise UnitError('unknown unit: %r' % unit)


def to_canonical(value, unit, quantity):
    """Convert ``value`` in ``unit`` to the canonical SI unit of ``quantity``."""
    if type(value) not in (int, float) or isinstance(value, bool) or not math.isfinite(value):
        raise UnitError('value must be a finite number')
    canonical = normalise_unit(unit)
    unit_quantity, factor = UNIT_TABLE[canonical]
    if unit_quantity != quantity:
        raise UnitError('unit %r is %s, expected %s' % (unit, unit_quantity, quantity))
    if factor is None:  # affine temperature unit
        if canonical != 'degF':
            raise UnitError('unsupported affine unit: %r' % unit)
        return (float(value) - 32.0) * 5.0 / 9.0
    converted = float(value) * factor
    if not math.isfinite(converted):
        raise UnitError('unit conversion overflow')
    return converted


def canonical_unit(quantity):
    return CANONICAL_UNITS[quantity]


def quantity_for_unit(unit):
    canonical = normalise_unit(unit)
    return UNIT_TABLE[canonical][0]


def format_quantity(quantity, value):
    """Human-readable value in canonical units (no excessive precision)."""
    unit = CANONICAL_UNITS.get(quantity, '')
    if isinstance(value, float):
        text = ('%.6g' % value)
    else:
        text = str(value)
    return ('%s %s' % (text, unit)).strip()
