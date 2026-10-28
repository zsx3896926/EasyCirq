"""Currency-aware Decimal money helpers.

Settlement is always Decimal; binary floats never enter final amounts.  A
currency declares its ISO-4217-style minor unit so line totals can be rounded
once, explicitly.  Mixed currencies are reported separately unless a sourced,
fresh FX rate is supplied.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from .errors import InputError
from .util import parse_decimal, parse_enum

# Supported settlement currencies and their minor-unit precision.  An unknown
# code is rejected instead of silently treating it as a 2-decimal currency.
CURRENCIES = {
    "CNY": 2,
    "USD": 2,
    "EUR": 2,
    "HKD": 2,
    "GBP": 2,
    "SGD": 2,
    "TWD": 2,
    "JPY": 0,
}

TAX_BASES = ("incl", "excl", "unknown")
QUANTITY = Decimal("1")


def parse_currency(value, where, required=True):
    code = parse_enum(value, tuple(sorted(CURRENCIES)), where,
                      required=required)
    return code


def parse_amount(value, where, required=True, allow_zero=True):
    minimum = Decimal("0") if allow_zero else Decimal("0.0000001")
    return parse_decimal(value, where, minimum=minimum, required=required)


def parse_tax_basis(value, where, required=True):
    return parse_enum(value, TAX_BASES, where, required=required)


def quantize(amount, currency):
    exponent = Decimal(1).scaleb(-CURRENCIES[currency])
    return amount.quantize(exponent, rounding=ROUND_HALF_UP)


def format_amount(amount, currency):
    digits = CURRENCIES[currency]
    text = quantize(amount, currency)
    return format(text, ".%df" % digits)


def parse_fx_rate(value, where):
    return parse_decimal(value, where, minimum=Decimal("0.0000001"))


def require_same_currency(left, right, where, message):
    if left != right:
        raise InputError("currency_conflict", message, where)
