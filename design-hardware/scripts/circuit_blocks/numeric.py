"""Strict numeric handling with exact rational arithmetic.

Every engineering decision in this package is made on :class:`fractions.Fraction`
values so that a tolerance endpoint equal to a limit is decided exactly, never
by binary floating-point luck.  Floats appear only at the JSON boundary, after
the decision, and booleans are never accepted as numbers (``True == 1`` in
Python, which would silently turn a typo into a value).
"""
from __future__ import annotations

import math
from decimal import Decimal, InvalidOperation, localcontext
from fractions import Fraction

from .errors import InputInvalid

#: Hard ceiling on magnitudes we are willing to reason about.  A value beyond
#: this is a unit/typo error for a real hardware constraint, not data.
MAX_MAGNITUDE = Fraction(10) ** 15


def is_number(value):
    """Return True for int/float/Decimal/Fraction but never for bool."""
    return isinstance(value, (int, float, Decimal, Fraction)) and not isinstance(value, bool)


def parse_number(value, field='value'):
    """Parse a real number into a Fraction.

    Accepts int, float, Decimal, Fraction and a numeric string (including
    scientific notation).  Rejects booleans, NaN, infinities, non-numeric
    strings and absurd magnitudes.
    """
    if isinstance(value, bool):
        raise InputInvalid('boolean is not a number', field=field)
    if isinstance(value, int):
        result = Fraction(value)
    elif isinstance(value, Fraction):
        result = value
    elif isinstance(value, Decimal):
        if not value.is_finite():
            raise InputInvalid('non-finite number is not allowed', field=field)
        result = Fraction(value)
    elif isinstance(value, float):
        if not math.isfinite(value):
            raise InputInvalid('NaN/inf is not a number', field=field)
        # repr() is the shortest decimal that round-trips, so 0.1 means the
        # decimal 0.1 a user typed, not the nearest binary double.
        result = Fraction(Decimal(repr(value)))
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            raise InputInvalid('empty numeric string', field=field)
        try:
            parsed = Decimal(text)
        except InvalidOperation:
            raise InputInvalid('not a number: %r' % (value,), field=field)
        if not parsed.is_finite():
            raise InputInvalid('non-finite number is not allowed', field=field)
        result = Fraction(parsed)
    else:
        raise InputInvalid('expected a number, got %s' % type(value).__name__, field=field)
    if abs(result) > MAX_MAGNITUDE:
        raise InputInvalid('number is out of the supported range: %r' % (value,), field=field)
    return result


def to_float(value, digits=12):
    """Render a Fraction as a JSON float rounded to ``digits`` significant digits."""
    value = value if isinstance(value, Fraction) else Fraction(value)
    if value.denominator == 1:
        integer = value.numerator
        if abs(integer) <= 2 ** 53:
            return float(integer)
        with localcontext() as ctx:
            ctx.prec = digits
            return float(Decimal(integer))
    with localcontext() as ctx:
        ctx.prec = digits
        result = Decimal(value.numerator) / Decimal(value.denominator)
    return float(result)


def to_json_number(value, digits=12):
    """JSON-safe int/float rendering; integral values stay ints."""
    value = value if isinstance(value, Fraction) else Fraction(value)
    if value.denominator == 1 and abs(value.numerator) <= 2 ** 53:
        return value.numerator
    return to_float(value, digits)


def format_number(value, digits=6):
    """Human-readable decimal string with trailing zeros trimmed."""
    value = value if isinstance(value, Fraction) else Fraction(value)
    with localcontext() as ctx:
        ctx.prec = digits
        decimal_value = Decimal(value.numerator) / Decimal(value.denominator)
    text = format(decimal_value.normalize(), 'f')
    if '.' in text:
        text = text.rstrip('0').rstrip('.')
    return text or '0'


def quantize(value, quantum):
    """Round a Fraction to the nearest multiple of ``quantum`` (half up)."""
    value, quantum = Fraction(value), Fraction(quantum)
    if quantum <= 0:
        raise InputInvalid('quantum must be positive')
    ratio = value / quantum
    floor = ratio.numerator // ratio.denominator
    remainder = ratio - floor
    if remainder >= Fraction(1, 2):
        floor += 1
    return quantum * floor


def require_nonnegative(value, field):
    if value < 0:
        raise InputInvalid('must not be negative', field=field)
    return value


def require_positive(value, field):
    if value <= 0:
        raise InputInvalid('must be greater than zero', field=field)
    return value


def require_positive_int(value, field):
    if isinstance(value, bool) or not isinstance(value, int):
        raise InputInvalid('expected an integer', field=field)
    if value <= 0:
        raise InputInvalid('expected a positive integer', field=field)
    return value


def fraction_from_pairs(numerator, denominator=1):
    """Small helper for readable unit tables."""
    return Fraction(numerator, denominator)
