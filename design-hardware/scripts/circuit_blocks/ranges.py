"""Bounded intervals, tolerance models and exact interval arithmetic.

Every declared range is a closed interval of Fractions: ``[lo, hi]``.  A point
value is the degenerate interval ``[x, x]``.  Ranges are never re-opened by
rounding, so a worst case that lands exactly on a limit is decided on the
limit, and an inverted interval is an input error rather than a negative width.

Tolerance models
----------------
``{"nominal": 4700, "tolerance_pct": 5}``  -> [4465, 4935]
``{"min": 4.5, "max": 5.5}``               -> [4.5, 5.5]
``4700`` / ``"4.7k"``                      -> [4700, 4700]

Correlation is *not* modelled: applying interval arithmetic to two toleranced
values assumes they can move independently and adversarially.  That is the
conservative assumption for worst-case checks and every module records it in
``assumptions`` so a reviewer can see where independence was assumed.
"""
from __future__ import annotations

from fractions import Fraction

from .errors import InputInvalid
from .numeric import (parse_number, require_nonnegative, require_positive,
                      to_json_number)
from .units import canonical_unit, parse_quantity


class Interval(object):
    """Closed interval ``[lo, hi]`` over Fractions."""

    __slots__ = ('lo', 'hi')

    def __init__(self, lo, hi=None):
        lo = lo if isinstance(lo, Fraction) else Fraction(lo)
        hi = lo if hi is None else (hi if isinstance(hi, Fraction) else Fraction(hi))
        if lo > hi:
            raise InputInvalid('inverted interval: min %s > max %s' % (lo, hi))
        self.lo = lo
        self.hi = hi

    # -- constructors ---------------------------------------------------
    @classmethod
    def point(cls, value):
        return cls(value, value)

    @classmethod
    def centred(cls, nominal, tolerance_pct):
        """Symmetric percent tolerance about ``nominal`` (exact)."""
        nominal = Fraction(nominal)
        span = nominal * Fraction(tolerance_pct) / 100
        return cls(nominal - span, nominal + span)

    # -- queries --------------------------------------------------------
    @property
    def nominal(self):
        return (self.lo + self.hi) / 2

    @property
    def width(self):
        return self.hi - self.lo

    @property
    def is_point(self):
        return self.lo == self.hi

    def contains(self, value):
        value = value if isinstance(value, Fraction) else Fraction(value)
        return self.lo <= value <= self.hi

    def clamp(self, value):
        value = value if isinstance(value, Fraction) else Fraction(value)
        return min(max(value, self.lo), self.hi)

    def relative_width(self):
        if self.hi == 0:
            return Fraction(0)
        return self.width / self.hi

    # -- arithmetic (conservative, independence assumed) ----------------
    def __add__(self, other):
        other = _coerce(other)
        return Interval(self.lo + other.lo, self.hi + other.hi)

    __radd__ = __add__

    def __sub__(self, other):
        other = _coerce(other)
        return Interval(self.lo - other.hi, self.hi - other.lo)

    def __rsub__(self, other):
        return _coerce(other).__sub__(self)

    def __mul__(self, other):
        other = _coerce(other)
        products = [self.lo * other.lo, self.lo * other.hi,
                    self.hi * other.lo, self.hi * other.hi]
        return Interval(min(products), max(products))

    __rmul__ = __mul__

    def __truediv__(self, other):
        other = _coerce(other)
        if other.contains(0):
            raise InputInvalid('division by an interval containing zero')
        quotients = [self.lo / other.lo, self.lo / other.hi,
                     self.hi / other.lo, self.hi / other.hi]
        return Interval(min(quotients), max(quotients))

    def __neg__(self):
        return Interval(-self.hi, -self.lo)

    def scale(self, factor):
        return self * Interval.point(factor)

    def intersect(self, other):
        other = _coerce(other)
        lo, hi = max(self.lo, other.lo), min(self.hi, other.hi)
        return None if lo > hi else Interval(lo, hi)

    def overlaps(self, other):
        other = _coerce(other)
        return self.lo <= other.hi and other.lo <= self.hi

    def covers(self, other):
        other = _coerce(other)
        return self.lo <= other.lo and other.hi <= self.hi

    def __repr__(self):
        return 'Interval(%s, %s)' % (self.lo, self.hi)

    def as_json(self, family, digits=12):
        return {'min': to_json_number(self.lo, digits),
                'max': to_json_number(self.hi, digits),
                'unit': canonical_unit(family)}


def _coerce(value):
    if isinstance(value, Interval):
        return value
    return Interval.point(value)


def parse_percent(value, field='tolerance_pct'):
    """Parse a percent quantity: ``5``, ``"5%"`` or ``{"value": 5, "unit": "%"}``."""
    from .units import parse_quantity as _pq
    if isinstance(value, str) and not value.strip().endswith('%'):
        text = value.strip()
        if text and not text.replace('.', '').replace('-', '').isdigit():
            return _pq(value, 'percent', field=field)
        value = text + '%'
    return _pq(value, 'percent', field=field)


def parse_interval(value, family, field='value', *, nonnegative=False,
                   allow_zero=True, positive=False):
    """Parse a closed interval in ``family`` units (exact base-unit Fractions)."""
    if isinstance(value, dict):
        keys = set(value)
        if 'nominal' in keys and ('tolerance_pct' in keys or 'tolerance' in keys):
            nominal = parse_quantity(value['nominal'], family, field=field + '.nominal')
            tolerance = value.get('tolerance_pct', value.get('tolerance'))
            interval = Interval.centred(nominal, parse_percent(tolerance, field + '.tolerance'))
        elif 'nominal' in keys and 'tolerance_value' in keys:
            nominal = parse_quantity(value['nominal'], family, field=field + '.nominal')
            span = abs(parse_quantity(value['tolerance_value'], family,
                                       field=field + '.tolerance_value'))
            interval = Interval(nominal - span, nominal + span)
        elif 'min' in keys or 'max' in keys:
            if 'min' not in keys or 'max' not in keys:
                raise InputInvalid('range needs both "min" and "max"', field=field)
            interval = Interval(parse_quantity(value['min'], family, field=field + '.min'),
                                parse_quantity(value['max'], family, field=field + '.max'))
        elif 'value' in keys and 'unit' in keys:
            point = parse_quantity(value, family, field=field)
            interval = Interval.point(point)
        elif 'value' in keys:
            point = parse_quantity(value['value'], family, field=field + '.value')
            interval = Interval.point(point)
        else:
            raise InputInvalid('unrecognised interval object (keys: %s)'
                               % ', '.join(sorted(keys)), field=field)
    else:
        point = parse_quantity(value, family, field=field)
        interval = Interval.point(point)
    if nonnegative and interval.lo < 0:
        raise InputInvalid('must not be negative', field=field)
    if positive and interval.lo <= 0:
        raise InputInvalid('must be greater than zero', field=field)
    if not allow_zero and interval.lo == 0:
        raise InputInvalid('must not be zero', field=field)
    return interval


def parse_point(value, family, field='value', *, nonnegative=False, positive=False):
    """Parse a single quantity (not a range); reject range objects."""
    if isinstance(value, dict) and ({'min', 'max', 'nominal'} & set(value)):
        raise InputInvalid('expected a single value, not a range', field=field)
    point = parse_quantity(value, family, field=field)
    if nonnegative:
        point = require_nonnegative(point, field)
    if positive:
        point = require_positive(point, field)
    return point


def interval_json(interval, family, digits=12):
    return interval.as_json(family, digits)


def midpoint_json(interval, family, digits=12):
    return {'value': to_json_number(interval.nominal, digits), 'unit': canonical_unit(family)}


def ratio_of(interval, reference):
    """Return the interval of ``interval / reference`` (both Fractions)."""
    reference = reference if isinstance(reference, Fraction) else Fraction(reference)
    if reference == 0:
        raise InputInvalid('reference must not be zero')
    return interval.scale(Fraction(1) / reference)


def worst_case_product(*intervals):
    """Conservative product of two or more intervals."""
    result = _coerce(intervals[0])
    for item in intervals[1:]:
        result = result * _coerce(item)
    return result
