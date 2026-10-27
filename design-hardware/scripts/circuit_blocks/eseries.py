"""Standard-value series (IEC 60063) and deterministic candidate selection.

Supported series: E6, E12, E24, E48, E96 for resistors; E3, E6, E12 for
capacitors (E3 = 10, 22, 47).  The tables below are the exact base values from
IEC 60063; a value is "standard" only if it equals ``base * 10^k`` exactly.

Candidate selection is deterministic: candidates are enumerated in ascending
numeric order, scored by the caller's hard-constraint filter and objective, and
ties break on the value itself.  No randomness, no dependence on dict order.
"""
from __future__ import annotations

from fractions import Fraction

from .errors import InputInvalid
from .numeric import parse_number

# Base values per series.  E3/E6/E12/E24 are given as two-digit integers
# (10..91) meaning 1.0..9.1; E48/E96 as three-digit integers (100..953)
# meaning 1.00..9.53.
_BASE = {
    'E3': [10, 22, 47],
    'E6': [10, 15, 22, 33, 47, 68],
    'E12': [10, 12, 15, 18, 22, 27, 33, 39, 47, 56, 68, 82],
    'E24': [10, 11, 12, 13, 15, 16, 18, 20, 22, 24, 27, 30, 33, 36, 39, 43,
            47, 51, 56, 62, 68, 75, 82, 91],
    'E48': [100, 105, 110, 115, 121, 127, 133, 140, 147, 154, 162, 169, 178,
            187, 196, 205, 215, 226, 237, 249, 261, 274, 287, 301, 316, 332,
            348, 365, 383, 402, 422, 442, 464, 487, 511, 536, 562, 590, 619,
            649, 681, 715, 750, 787, 825, 866, 909, 953],
    'E96': [100, 102, 105, 107, 110, 113, 115, 118, 121, 124, 127, 130, 133,
            137, 140, 143, 147, 150, 154, 158, 162, 165, 169, 174, 178, 182,
            187, 191, 196, 200, 205, 210, 215, 221, 226, 232, 237, 243, 249,
            255, 261, 267, 274, 280, 287, 294, 301, 309, 316, 324, 332, 340,
            348, 357, 365, 374, 383, 392, 402, 412, 422, 432, 442, 453, 464,
            475, 487, 499, 511, 523, 536, 549, 562, 576, 590, 604, 619, 634,
            649, 665, 681, 698, 715, 732, 750, 768, 787, 806, 825, 845, 866,
            887, 909, 931, 953],
}

#: Series nominally associated with resistor tolerances.  The generator never
#: enforces the pairing; it records whatever the caller declared.
RESISTOR_SERIES = ('E6', 'E12', 'E24', 'E48', 'E96')
CAPACITOR_SERIES = ('E3', 'E6', 'E12')

_SUPPORTED = tuple(sorted(_BASE))


def supported_series():
    return list(_SUPPORTED)


def _require_series(series):
    if series not in _BASE:
        raise InputInvalid('unsupported value series %r (supported: %s)'
                           % (series, ', '.join(_SUPPORTED)))


def base_values(series):
    """Return the exact base values of a series as Fractions (1.0 .. 9.53)."""
    _require_series(series)
    values = _BASE[series]
    divisor = 10 if len(str(values[0])) == 2 else 100
    return [Fraction(value, divisor) for value in values]


def values(series, min_value=None, max_value=None, decades=None):
    """Enumerate standard values of ``series`` in ascending order.

    ``min_value``/``max_value`` are Fractions or numbers; both bounds are
    inclusive.  ``decades`` optionally restricts the exponent range, e.g.
    ``range(-2, 7)``.  Values are exact Fractions.
    """
    _require_series(series)
    if decades is None:
        decades = range(-6, 7)
    low = parse_number(min_value) if min_value is not None else None
    high = parse_number(max_value) if max_value is not None else None
    result = []
    for base in base_values(series):
        for exponent in decades:
            value = base * (Fraction(10) ** exponent)
            if low is not None and value < low:
                continue
            if high is not None and value > high:
                continue
            result.append(value)
    return sorted(set(result))


def is_standard_value(value, series):
    """True only when ``value`` is exactly a member of ``series``."""
    _require_series(series)
    value = parse_number(value) if not isinstance(value, Fraction) else value
    if value <= 0:
        return False
    for base in base_values(series):
        if base == 0:
            continue
        ratio = value / base
        for exponent in range(-12, 13):
            if ratio == Fraction(10) ** exponent:
                return True
    return False


def classify(value, series):
    """Return a short standard-value label such as ``"4k7"`` or ``None``."""
    value = parse_number(value) if not isinstance(value, Fraction) else value
    if not is_standard_value(value, series):
        return None
    for unit_scale, suffix in ((Fraction(10) ** 6, 'M'), (Fraction(10) ** 3, 'k'),
                               (Fraction(1), 'R'), (Fraction(1, 1000), 'm')):
        scaled = value / unit_scale
        if Fraction(1) <= scaled < 1000 and scaled.denominator in (1, 2, 5, 10, 100):
            return _compact(scaled) + suffix
    return None


def _compact(value):
    """Format a Fraction 1..999 without trailing zeros (4.7 -> '4.7')."""
    text = str(value.numerator) if value.denominator == 1 else None
    if text is not None:
        return text
    scaled = value * 10
    while scaled.denominator != 1:
        scaled *= 10
    digits = str(scaled.numerator)
    if len(digits) <= 1:
        return '0.' + digits
    return digits[:-1] + '.' + digits[-1]


def choose(candidates, score, *, prefer_lower_on_tie=True):
    """Pick the best candidate deterministically.

    ``candidates`` is an iterable of comparable values (usually Fractions).
    ``score(value)`` returns a sortable key (lower is better) or ``None`` to
    reject the candidate.  Remaining ties break on the value itself, ascending
    when ``prefer_lower_on_tie`` else descending.
    """
    scored = []
    for value in candidates:
        key = score(value)
        if key is None:
            continue
        scored.append((key, value))
    if not scored:
        return None
    if prefer_lower_on_tie:
        scored.sort(key=lambda item: (item[0], item[1]))
    else:
        scored.sort(key=lambda item: (item[0], -item[1]))
    return scored[0][1]


def tolerance_bounds(nominal, tolerance_pct):
    """Return the exact ``[lo, hi]`` interval for a percent tolerance."""
    nominal = parse_number(nominal) if not isinstance(nominal, Fraction) else nominal
    span = nominal * parse_number(tolerance_pct) / 100
    if span < 0:
        raise InputInvalid('tolerance must not be negative')
    return nominal - span, nominal + span


def nearest(values_list, target):
    """Nearest candidate, ties resolved toward the lower value."""
    target = parse_number(target) if not isinstance(target, Fraction) else target
    best = None
    for value in values_list:
        distance = abs(value - target)
        if best is None or distance < best[0] or (distance == best[0] and value < best[1]):
            best = (distance, value)
    return None if best is None else best[1]
