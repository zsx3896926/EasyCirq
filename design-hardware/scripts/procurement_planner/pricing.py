"""Legal order quantities and tier pricing.

Order-policy contract (explicit, not a hidden max()):

    orderable(need) = 0                                     if need <= 0
                    = ceil(max(need, MOQ) / MPQ) * MPQ       otherwise

Overbuy is bounded by BOTH ``max_extra_qty`` and ``floor(orderable * ratio)``;
a higher price break is only considered inside that bound, and only for the
``total_tier`` price mode.  ``progressive`` (segmented marginal) pricing is
supported separately; unknown price coverage is returned as ``None`` rather
than guessed.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, localcontext

from .money import quantize

ZERO = Decimal("0")


def _dividend(num, den):
    with localcontext() as ctx:
        ctx.prec = 34
        return Decimal(num) / Decimal(den)


def effective_unit_price(offer, unit_price):
    unit = offer["price_unit"]
    if unit["kind"] == "per_pack":
        return _dividend(unit_price, unit["pack_qty"])
    return unit_price


def orderable_qty(need, moq, mpq):
    if need is None or need <= 0:
        return 0
    target = max(int(need), int(moq))
    return int(-(-target // int(mpq)) * int(mpq))


def _tier_bounds(tiers, qty):
    """Yield (units, tier) for a progressive price at ``qty``; None if gap."""

    covered = 0
    result = []
    for index, tier in enumerate(tiers):
        start = tier["min_qty"]
        if index + 1 < len(tiers):
            natural_end = tiers[index + 1]["min_qty"] - 1
        else:
            natural_end = None
        end = natural_end
        if tier["max_qty"] is not None:
            end = tier["max_qty"] if end is None else min(end,
                                                          tier["max_qty"])
        if qty < start:
            break
        block_end = qty if end is None else min(qty, end)
        units = block_end - start + 1
        if units > 0:
            result.append((units, tier))
            covered += units
        if end is not None and qty > end:
            # A gap after an explicit max_qty means part of the quantity is
            # not priced by this tier list.
            if index + 1 < len(tiers) and tiers[index + 1]["min_qty"] > end + 1:
                return None
    if covered != qty:
        return None
    return result


def price_for_qty(offer, qty):
    """Return (total Decimal, per-unit-basis description) or None."""

    if qty <= 0:
        return ZERO, {"basis": "zero"}
    tiers = offer["price_tiers"]
    if offer["price_mode"] == "total_tier":
        applicable = None
        for index, tier in enumerate(tiers):
            upper = tier["max_qty"]
            if upper is None and index + 1 < len(tiers):
                upper = tiers[index + 1]["min_qty"] - 1
            if qty >= tier["min_qty"] and (upper is None or qty <= upper):
                applicable = tier
                break
        if applicable is None:
            return None
        unit = effective_unit_price(offer, applicable["unit_price"])
        return unit * qty, {
            "basis": "total_tier",
            "tier_min_qty": applicable["min_qty"],
            "tier_max_qty": applicable["max_qty"],
            "unit_price": unit,
        }
    blocks = _tier_bounds(tiers, qty)
    if blocks is None:
        return None
    total = ZERO
    detail = []
    for units, tier in blocks:
        unit = effective_unit_price(offer, tier["unit_price"])
        total += unit * units
        detail.append({"units": units, "unit_price": unit,
                       "tier_min_qty": tier["min_qty"]})
    return total, {"basis": "progressive", "segments": detail}


def line_total(offer, qty):
    priced = price_for_qty(offer, qty)
    if priced is None:
        return None
    return priced[0]


def quantized_line_total(offer, qty):
    total = line_total(offer, qty)
    if total is None:
        return None
    return quantize(total, offer["currency"])


def overbuy_cap(base_qty, policy):
    if base_qty <= 0:
        return 0
    ratio_extra = int((Decimal(base_qty)
                       * policy["max_extra_ratio"]).to_integral_value(
                           rounding=ROUND_FLOOR))
    allowed = min(int(policy["max_extra_qty"]), ratio_extra)
    return max(0, allowed)


def quantity_candidates(offer, required_qty, overbuy):
    """Return sorted unique legal order quantities with a bounded overbuy."""

    base = orderable_qty(required_qty, offer["moq"], offer["mpq"])
    if base <= 0:
        return []
    candidates = {base}
    if not overbuy.get("allow_price_break_extra", True):
        return sorted(candidates)
    if offer["price_mode"] != "total_tier":
        return sorted(candidates)
    allowed_extra = overbuy_cap(base, overbuy)
    if allowed_extra <= 0:
        return sorted(candidates)
    max_qty = base + (allowed_extra // offer["mpq"]) * offer["mpq"]
    for tier in offer["price_tiers"]:
        candidate = orderable_qty(tier["min_qty"], offer["moq"],
                                  offer["mpq"])
        if base < candidate <= max_qty:
            candidates.add(candidate)
    return sorted(candidates)


def choose_purchase(offer, required_qty, overbuy, known_stock=None,
                    allow_overbuy=True):
    """Choose the legal quantity with the lowest known total cost.

    ``known_stock`` is a known available quantity or None when unknown.  Unknown
    stock permits only the minimal legal quantity; it never opens the overbuy
    search because availability is not established.
    """

    base = orderable_qty(required_qty, offer["moq"], offer["mpq"])
    if base <= 0:
        return {"feasible": True, "chosen_qty": 0, "base_qty": 0,
                "chosen_total": ZERO, "base_total": ZERO,
                "unit_price": None, "reason": "zero_need",
                "candidates": [], "unpriced": []}
    if known_stock is not None and base > known_stock:
        return {"feasible": False, "reason": "stock_below_minimum_order",
                "base_qty": base, "chosen_qty": 0, "known_stock": known_stock,
                "candidates": []}
    if known_stock is None or not allow_overbuy:
        candidates = [base]
    else:
        candidates = quantity_candidates(offer, required_qty, overbuy)
    priced = []
    unpriced = []
    for qty in candidates:
        if known_stock is not None and qty > known_stock:
            continue
        total = line_total(offer, qty)
        if total is None:
            unpriced.append(qty)
            continue
        priced.append((qty, total))
    if not priced:
        return {"feasible": False, "reason": "price_unknown",
                "base_qty": base, "chosen_qty": 0,
                "candidates": [], "unpriced": unpriced}
    priced.sort(key=lambda item: (item[1], item[0]))
    chosen_qty, chosen_total = priced[0]
    base_total = line_total(offer, base)
    if chosen_qty > base and base_total is not None \
            and chosen_total < base_total:
        reason = "higher_tier_lower_total"
    elif chosen_qty > required_qty and chosen_qty > base:
        reason = "overbuy_cap_or_policy"
    elif chosen_qty > base:
        reason = "order_policy_minimum"
    else:
        reason = "base_quantity"
    unit_price = effective_unit_price(
        offer, offer["price_tiers"][-1]["unit_price"])
    return {
        "feasible": True,
        "base_qty": base,
        "chosen_qty": chosen_qty,
        "base_total": base_total,
        "chosen_total": chosen_total,
        "unit_price": unit_price,
        "reason": reason,
        "candidates": [
            {"qty": qty, "total": total,
             "selected": qty == chosen_qty}
            for qty, total in sorted(priced, key=lambda item: item[0])
        ],
        "unpriced": unpriced,
    }
