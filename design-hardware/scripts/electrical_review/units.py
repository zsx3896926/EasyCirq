"""Unit parsing and normalisation.  Unknown units are invalid input."""
import math


VOLTAGE = {
    "v": 1.0, "volt": 1.0, "volts": 1.0,
    "mv": 1e-3,
}
LENGTH = {
    "mm": 1.0, "millimeter": 1.0, "millimetre": 1.0,
    "mil": 0.0254, "mils": 0.0254, "thou": 0.0254,
    "in": 25.4, "inch": 25.4, "inches": 25.4,
}
CAPACITANCE = {
    "f": 1.0, "farad": 1.0,
    "mf": 1e-3, "uf": 1e-6, "\u00b5f": 1e-6, "\u03bcf": 1e-6,
    "nf": 1e-9, "pf": 1e-12,
}
RESISTANCE = {
    "ohm": 1.0, "\u03a9": 1.0, "ohms": 1.0,
    "kohm": 1e3, "k\u03a9": 1e3, "mohm": 1e6, "m\u03a9": 1e6,
}


def finite_number(value, name):
    """Reject bool/str/NaN/inf.  bool is not a number for this contract."""
    if type(value) not in (int, float):
        raise ValueError(name + ": finite number required")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(name + ": finite number required")
    return number


def unit_factor(table, unit, name, default=None):
    if unit is None and default is not None:
        return table[default]
    if not isinstance(unit, str):
        raise ValueError(name + ": unit string required")
    key = unit.strip().casefold()
    if key not in table:
        raise ValueError(name + ": unsupported unit " + repr(unit))
    return table[key]


def voltage(value, unit, name):
    return finite_number(value, name) * unit_factor(VOLTAGE, unit, name)


def length(value, unit, name):
    return finite_number(value, name) * unit_factor(LENGTH, unit, name)


def capacitance(value, unit, name):
    return finite_number(value, name) * unit_factor(CAPACITANCE, unit, name)


def resistance(value, unit, name):
    return finite_number(value, name) * unit_factor(RESISTANCE, unit, name)


def display(number, unit, digits=6):
    """Stable human-readable value without scientific noise for common cases."""
    if number is None:
        return None
    rounded = round(float(number), digits)
    if rounded == int(rounded):
        rounded = int(rounded)
    return str(rounded) + (" " + unit if unit else "")
