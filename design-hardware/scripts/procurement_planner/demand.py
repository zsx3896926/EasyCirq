"""BOM demand expansion: designators -> assembly demand -> purchase need.

The chain is explicit and reported step by step:

    qty_per_board * board_quantity
      -> assembled_qty
      -> + spare (ratio ceil, fixed, minimum in the declared order)
      -> target_qty
      -> - consigned/self-supplied qty (same identity, qualified only)
      -> purchase_need
      -> MOQ/MPQ-rounded orderable qty (in planner)

DNP rows are excluded from procurement but kept in the report.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_CEILING

ZERO = Decimal("0")


def expand_rows(rows, board_quantity, policies, demand, findings=None):
    """Return demand records for every BOM row (DNP included)."""

    records = []
    attrition = policies["attrition"]
    ratio = attrition["ratio"]
    fixed = int(attrition["fixed"])
    minimum = int(attrition["minimum"])
    self_allowed = bool(demand.get("self_supply_allowed"))
    consigned_blocked = 0
    for row in rows:
        line_id = row["line_id"]
        per_board = int(row["qty_per_board"])
        if row["dnp"]:
            # DNP is not part of the default procurement demand; keep the
            # BOM quantity in the report but do not add spare/consigned or
            # purchase anything for it.
            assembled = 0
        else:
            assembled = per_board * int(board_quantity)
        ratio_spare = 0
        if ratio > 0 and assembled > 0:
            ratio_spare = int((Decimal(assembled) * ratio)
                              .to_integral_value(rounding=ROUND_CEILING))
        fixed_spare = fixed
        minimum_spare = minimum
        spare_after_fixed = ratio_spare + fixed_spare
        spare_total = max(spare_after_fixed, minimum_spare)
        target = assembled + spare_total
        consigned_requested = int(row.get("consigned_qty", 0))
        qualified = bool(row.get("consigned_qualified", True))
        consigned_applied = 0
        consigned_note = None
        if row["dnp"] or assembled == 0:
            consigned_applied = 0
            if consigned_requested:
                consigned_note = "dnp_or_zero_demand_no_offset"
        elif consigned_requested and not qualified:
            consigned_note = "consigned_not_qualified_no_offset"
            if findings is not None:
                findings.warning(
                    "consigned_not_qualified", "bom.rows[%s]" % line_id,
                    "自备料标记为不合格，不抵扣需求")
        elif consigned_requested and not self_allowed:
            consigned_note = "self_supply_policy_disallows_offset"
            if findings is not None:
                findings.warning(
                    "consigned_ignored_by_policy", "bom.rows[%s]" % line_id,
                    "存在自备数量但 demand.self_supply_allowed=false；"
                    "不抵扣采购需求")
        elif consigned_requested:
            consigned_applied = min(consigned_requested, target)
            consigned_blocked = max(0, consigned_requested
                                    - consigned_applied)
            if consigned_blocked:
                if findings is not None:
                    findings.warning(
                        "consigned_exceeds_need", "bom.rows[%s]" % line_id,
                        "自备数量 %d 超过含备损需求 %d；只抵扣需求，剩余 %d"
                        " 不产生采购" % (consigned_requested, target,
                                        consigned_blocked))
        purchase_need = max(0, target - consigned_applied)
        records.append({
            "line_id": line_id,
            "mpn": row["mpn"],
            "manufacturer": row["manufacturer"],
            "footprint": row["footprint"],
            "package": row["package"],
            "supply_ids": dict(row["supply_ids"]),
            "assembly": row["assembly"],
            "dnp": bool(row["dnp"]),
            "excluded": ("dnp" if row["dnp"] else
                         ("zero_board_quantity" if assembled == 0 else None)),
            "designators": list(row["designators"]),
            "qty_per_board": per_board,
            "board_quantity": int(board_quantity),
            "assembled_qty": assembled,
            "attrition": {
                "ratio": str(ratio),
                "ratio_spare": ratio_spare,
                "fixed_spare": fixed_spare,
                "minimum_spare": minimum_spare,
                "spare_after_fixed": spare_after_fixed,
                "spare_total": spare_total,
                "order": list(attrition["order"]),
            },
            "target_qty": target,
            "consigned_requested": consigned_requested,
            "consigned_qualified": qualified,
            "consigned_applied": consigned_applied,
            "consigned_note": consigned_note,
            "purchase_need": purchase_need,
        })
    return records
