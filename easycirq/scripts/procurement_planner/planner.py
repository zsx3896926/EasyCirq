"""Multi-strategy purchase planning with shared inventory pools and fees.

Three bounded, explainable candidates are produced (when requested):

* ``known_cost``               - cheapest known legal purchase, primary MPN only
* ``channel_split``            - channel preference and fewer orders first
* ``conservative_substitution``- primary MPN first, then only alternates graded
                                 ``exact_identity``/``evidence_supported_candidate``

The search is greedy and bounded by explicit policies; it never claims global
optimality.  Unknown inventory/price/fees are recorded as unknown and never
treated as zero in the "lowest known cost" comparison.
"""

from __future__ import annotations

from decimal import Decimal

from . import TOOL_VERSION
from . import alternates as alt_module
from . import channels
from .demand import expand_rows
from .errors import Findings
from .money import format_amount, quantize
from .pricing import (choose_purchase, effective_unit_price, orderable_qty,
                      price_for_qty)
from .pricing import price_for_qty as _price_for_qty
from .util import normalize_identity, normalize_supply_id

ZERO = Decimal("0")
STRATEGIES = ("known_cost", "channel_split", "conservative_substitution")
STRATEGY_LABELS = {
    "known_cost": "已知成本优先",
    "channel_split": "渠道/拆单减少",
    "conservative_substitution": "替代保守",
}


class PoolBook:
    """Shared inventory pools; one pool is deducted once across all lines."""

    def __init__(self, offers):
        self.groups = {}
        self.available = {}
        self.owners = {}
        for offer in offers:
            pool = self.pool_of(offer)
            self.groups.setdefault(pool, []).append(offer)
        for pool, group in self.groups.items():
            values = []
            for offer in group:
                if not offer.get("trusted"):
                    continue
                stock = offer["stock"]
                if stock["status"] in ("out_of_stock", "not_applicable"):
                    values.append(0)
                elif stock["status"] == "unknown" or stock["available"] is None:
                    values.append(None)
                else:
                    values.append(stock["available"])
            if not values:
                self.available[pool] = None
            elif any(value is None for value in values):
                self.available[pool] = None
            else:
                self.available[pool] = min(values)

    @staticmethod
    def pool_of(offer):
        explicit = offer["stock"]["pool_id"]
        if not explicit:
            return "offer:%s" % offer["offer_id"]
        # A pool is one physical stock of one item.  If a declared pool id is
        # reused for a different supply identity, keep the identities separate
        # (the model reports the conflict) instead of letting min() erase a
        # real quantity.
        identity = (normalize_supply_id(offer.get("product_id", ""))
                    or "%s|%s" % (normalize_identity(offer["mpn"]),
                                  normalize_identity(offer["footprint"])))
        return "%s|%s" % (explicit, identity)

    def available_for(self, offer):
        return self.available[self.pool_of(offer)]

    def consume(self, offer, qty):
        pool = self.pool_of(offer)
        current = self.available.get(pool)
        if current is None:
            return None
        if qty > current:
            return None
        self.available[pool] = current - qty
        return current


class StrategyPlanner:
    def __init__(self, prepared, strategy, gradings, gradings_by_alt):
        self.prepared = prepared
        self.strategy = strategy
        self.gradings = gradings
        self.gradings_by_alt = gradings_by_alt
        self.pools = PoolBook(prepared.offers)
        self.offers = prepared.offers
        self.demand = prepared.demand
        self.rows_by_id = {row["line_id"]: row for row in prepared.rows}
        self.findings = Findings()
        self.records = expand_rows(prepared.rows,
                                   prepared.project["board_quantity"],
                                   prepared.policies, prepared.demand,
                                   self.findings)
        self.records_by_id = {record["line_id"]: record
                              for record in self.records}
        self.lines = []
        self.orders = []
        self.total_orders = 0
        self.order_limit_hit = False
        self.search_steps = 0
        self.search_budget_exhausted = False
        self.comparison_currency = self._pick_comparison_currency()

    # -- cross-currency comparison --------------------------------------
    def _fx_lookup(self, source_currency, target_currency):
        if source_currency == target_currency:
            return Decimal("1"), None, "same"
        for fx in self.prepared.fx_rates:
            if fx["base"] == source_currency and fx["quote"] == target_currency:
                direction, rate = "direct", fx["rate"]
            elif fx["base"] == target_currency \
                    and fx["quote"] == source_currency:
                direction, rate = "inverse", fx["rate"]
            else:
                continue
            max_age = self.prepared.evaluation["max_age_hours"]
            if max_age is not None:
                from .util import ago_hours
                age = ago_hours(fx["captured_at"],
                                self.prepared.evaluation["as_of"])
                if Decimal(str(age)) > max_age:
                    continue
            if direction == "inverse":
                return (Decimal("1") / rate), fx, direction
            return rate, fx, direction
        return None, None, None

    def _pick_comparison_currency(self):
        currencies = {offer["currency"] for offer in self.offers}
        if not currencies:
            return None
        budget = self.demand.get("budget")
        if budget is not None:
            target = budget["currency"]
            if all(self._fx_lookup(code, target)[0] is not None
                   for code in currencies):
                return target
        if len(currencies) == 1:
            return next(iter(currencies))
        return None

    def _compare_unit_price(self, offer, unit_price):
        if self.comparison_currency is None:
            return None
        rate, _fx, _direction = self._fx_lookup(offer["currency"],
                                               self.comparison_currency)
        if rate is None:
            return None
        return unit_price * rate

    def _static_sort_key(self, offer):
        unit = effective_unit_price(offer, offer["price_tiers"][0]["unit_price"])
        rank = self._channel_rank(offer["channel"])
        if self.strategy == "known_cost":
            converted = self._compare_unit_price(offer, unit)
            if converted is not None:
                return (0, converted, rank, offer["offer_id"])
            # Mixed currencies without a usable FX rate are never ordered by
            # raw numeric unit price as if they were comparable.
            return (1, rank, offer["currency"], unit, offer["offer_id"])
        if self.strategy == "channel_split":
            return (rank, unit, offer["currency"], offer["offer_id"])
        # conservative: prefer known larger stock, then channel, then price.
        stock = self.pools.available_for(offer)
        stock_key = -stock if stock is not None else 0
        return (stock_key, rank, unit, offer["currency"], offer["offer_id"])

    # -- candidate selection ---------------------------------------------
    def _allowed_channels(self, row):
        if row["dnp"]:
            return []
        if row["assembly"] in ("tht", "hand"):
            return [channel for channel in self.demand["channels"]
                    if channel != "jlc_smt"]
        if self.demand["assembly_strategy"] == "hand_solder":
            return [channel for channel in self.demand["channels"]
                    if channel != "jlc_smt"]
        return list(self.demand["channels"])

    def _channel_rank(self, channel):
        preference = self.demand["channel_preference"]
        return preference.index(channel) if channel in preference \
            else len(preference)

    def _coverable_by_one(self, offer, remaining):
        available = self.pools.available_for(offer)
        if available is None:
            return False
        base = orderable_qty(min(remaining, available), offer["moq"],
                             offer["mpq"])
        return base > 0 and base <= available

    def _primary_candidates(self, row):
        matches = channels.matched_offers(row, self.offers)
        allowed = set(self._allowed_channels(row))
        eligible = []
        conflicts = []
        for match in matches:
            offer = match["offer"]
            if match["status"] == "conflict":
                conflicts.append({
                    "offer_id": offer["offer_id"],
                    "reason": match.get("reason"),
                    "warnings": match.get("warnings", []),
                })
                continue
            if match["status"] not in ("match", "match_with_warning"):
                continue
            if offer["channel"] not in allowed:
                conflicts.append({
                    "offer_id": offer["offer_id"],
                    "reason": "channel_not_allowed",
                    "warnings": ["渠道 %s 不在本需求允许渠道内"
                                 % offer["channel"]],
                })
                continue
            eligible.append({"offer": offer, "match": match})
        return matches, eligible, conflicts

    def _substitution_candidates(self, row, grading, allowed_grades):
        alternate = None
        for candidate in self.prepared.alternates:
            if candidate.get("alt_id") == grading.get("alt_id"):
                alternate = candidate
                break
        if alternate is None:
            return []
        if grading["status"] not in allowed_grades:
            return []
        if alternate.get("approval_scope") == "not_approved":
            return []
        candidate_part = alternate.get("candidate") or {}
        pseudo_row = {
            "mpn": candidate_part.get("mpn"),
            "manufacturer": candidate_part.get("manufacturer"),
            "footprint": candidate_part.get("footprint"),
            "supply_ids": {},
        }
        if not pseudo_row["mpn"] or not pseudo_row["footprint"]:
            return []
        matches = channels.matched_offers(pseudo_row, self.offers)
        allowed = set(self._allowed_channels(row))
        result = []
        for match in matches:
            offer = match["offer"]
            if match["status"] == "conflict":
                continue
            if match["status"] not in ("match", "match_with_warning"):
                continue
            if offer["channel"] not in allowed:
                continue
            if not offer.get("trusted"):
                continue
            if offer["stock"]["status"] in ("out_of_stock", "not_applicable"):
                continue
            result.append({"offer": offer, "grading": grading,
                           "alt_id": grading.get("alt_id"),
                           "match": match})
        return result

    # -- allocation -------------------------------------------------------
    def _lead_time(self, offer, order_qty):
        due = self.demand["due_date"]
        lead = offer["lead_time"]
        as_of = self.prepared.evaluation["as_of"]
        if due is None:
            return {"status": "not_evaluated_no_due_date",
                    "nature": lead["kind"], "days_min": lead["days_min"],
                    "days_max": lead["days_max"],
                    "note": "需求未给交期截止；不判按时交付"}
        if lead["kind"] == "unknown":
            return {"status": "unknown", "nature": "unknown",
                    "days_min": None, "days_max": None,
                    "note": "缺少交期性质/天数；不能判按时交付"}
        if lead["kind"] == "in_stock":
            if offer["snapshot"]["stale"]:
                return {"status": "unknown",
                        "nature": "in_stock_stale_snapshot",
                        "note": "现货快照已过期；不能判按时"}
            return {"status": "stock_snapshot_only", "nature": "in_stock",
                    "days_min": 0, "days_max": 0,
                    "note": "快照显示现货，不是供应商交期承诺，也未预留"}
        if lead["kind"] in ("estimated", "committed"):
            days = lead["days_max"] if lead["days_max"] is not None \
                else lead["days_min"]
            if days is None:
                return {"status": "unknown", "nature": lead["kind"],
                        "note": "缺 days；不能判按时"}
            from datetime import timedelta
            arrival = as_of + timedelta(days=days)
            late = arrival > due
            return {
                "status": "late" if late else "likely_on_time",
                "nature": lead["kind"],
                "days_min": lead["days_min"],
                "days_max": lead["days_max"],
                "estimated_arrival": arrival,
                "due_date": due,
                "note": ("按 %s 的 days_max 估算，非供应商承诺"
                         % lead["kind"]),
            }
        return {"status": "unknown", "nature": lead["kind"],
                "note": "交期性质不适用/未知"}

    def _allocate(self, record, candidates, unknown_reasons, trace,
                  max_orders, substitution=False):
        remaining = int(record["purchase_need"])
        orders = []
        if remaining <= 0:
            return orders, remaining
        ordered_candidates = sorted(candidates, key=lambda item: item["order_key"]) \
            if candidates and "order_key" in candidates[0] else list(candidates)
        attempts = 0
        max_steps = self.prepared.policies.get("search", {}).get(
            "max_search_steps", 10000)
        while remaining > 0 and len(orders) < max_orders:
            if self.search_steps >= max_steps:
                self.search_budget_exhausted = True
                unknown_reasons.append({
                    "code": "search_budget_exhausted",
                    "message": "确定性搜索步数预算 %d 已用尽；结果是有界候选，"
                               "不是全局最优，剩余数量按未知处理" % max_steps,
                })
                trace.append({
                    "attempt": attempts + 1,
                    "decision": "search_budget_exhausted",
                    "max_search_steps": max_steps,
                })
                break
            self.search_steps += 1
            total_limit = self.demand["split_policy"].get("max_orders_total")
            if total_limit is not None and self.total_orders >= total_limit:
                self.order_limit_hit = True
                trace.append({
                    "attempt": attempts + 1,
                    "decision": "max_orders_total_reached",
                    "limit": total_limit,
                })
                break
            pool_candidates = [item for item in ordered_candidates
                               if item["offer"]["offer_id"] not in
                               {order["offer_id"] for order in orders}]
            if not pool_candidates:
                break
            if self.strategy == "channel_split" and not substitution:
                # Prefer a single offer that covers the rest, then cheapest.
                pool_candidates.sort(
                    key=lambda item: (
                        not self._coverable_by_one(item["offer"], remaining),
                        item["order_key"]))
            else:
                pool_candidates.sort(key=lambda item: item["order_key"])
            item = pool_candidates[0]
            offer = item["offer"]
            attempts += 1
            available = self.pools.available_for(offer)
            if available is None:
                unknown_reasons.append({
                    "code": "stock_unknown",
                    "offer_id": offer["offer_id"],
                    "message": "该 offer 的库存/快照不能证明可用；未知库存"
                               "不视作无限",
                })
                ordered_candidates.remove(item)
                trace.append({"attempt": attempts, "offer_id": offer["offer_id"],
                              "decision": "unknown_stock"})
                continue
            if available <= 0:
                ordered_candidates.remove(item)
                trace.append({"attempt": attempts, "offer_id": offer["offer_id"],
                              "decision": "no_known_stock"})
                continue
            required_for_offer = min(remaining, available)
            allow_overbuy = self.strategy != "conservative_substitution"
            purchase = choose_purchase(
                offer, required_for_offer, self.demand["overbuy"],
                known_stock=available, allow_overbuy=allow_overbuy)
            if not purchase["feasible"] and \
                    purchase.get("reason") == "stock_below_minimum_order":
                # The MOQ rounding overshoots this offer's stock, but a
                # smaller MPQ-aligned batch may still be legal and useful.
                fallback = (available // offer["mpq"]) * offer["mpq"]
                if fallback >= offer["moq"] and fallback > 0:
                    purchase = choose_purchase(
                        offer, fallback, self.demand["overbuy"],
                        known_stock=available, allow_overbuy=False)
            if not purchase["feasible"]:
                ordered_candidates.remove(item)
                reason = purchase.get("reason")
                if reason == "price_unknown":
                    unknown_reasons.append({
                        "code": "price_unknown",
                        "offer_id": offer["offer_id"],
                        "message": "当前数量没有完整价格阶梯覆盖；不猜价格",
                    })
                trace.append({"attempt": attempts,
                              "offer_id": offer["offer_id"],
                              "decision": reason,
                              "base_qty": purchase.get("base_qty")})
                continue
            qty = int(purchase["chosen_qty"])
            if qty <= 0:
                ordered_candidates.remove(item)
                break
            stock_before = available
            actual = self.pools.consume(offer, qty)
            if actual is None:
                ordered_candidates.remove(item)
                trace.append({"attempt": attempts,
                              "offer_id": offer["offer_id"],
                              "decision": "pool_race_or_conflict"})
                continue
            pricing = _price_for_qty(offer, qty)
            order = {
                "line_id": record["line_id"],
                "offer_id": offer["offer_id"],
                "supplier": offer["supplier"],
                "channel": offer["channel"],
                "product_id": offer["product_id"],
                "mpn": offer["mpn"],
                "footprint": offer["footprint"],
                "currency": offer["currency"],
                "tax_basis": offer["tax_basis"],
                "qty": qty,
                "unit_price": (pricing[1].get("unit_price")
                               if pricing and pricing[1].get("basis")
                               == "total_tier" else None),
                "pricing": pricing[1] if pricing else None,
                "line_total": pricing[0] if pricing else None,
                "selection_reason": purchase["reason"],
                "base_qty": purchase["base_qty"],
                "candidates": purchase["candidates"],
                "overbuy_qty": max(0, qty - required_for_offer),
                "stock_pool": self.pools.pool_of(offer),
                "stock_before": stock_before,
                "stock_after": self.pools.available[self.pools.pool_of(offer)],
                "snapshot_id": offer["snapshot_id"],
                "snapshot_source": offer["snapshot"]["source"],
                "snapshot_truth": offer["snapshot"]["declared_truth"],
                "snapshot_captured_at": offer["snapshot"]["captured_at"],
                "simulated": bool(offer["snapshot"]["synthetic"]),
                "lead_time": self._lead_time(offer, qty),
                "substitution": substitution,
            }
            if substitution:
                order["alternate_id"] = item.get("alt_id")
                order["alternate_grade"] = item.get("grading", {}).get("status")
            orders.append(order)
            self.total_orders += 1
            remaining = max(0, remaining - qty)
            trace.append({
                "attempt": attempts,
                "offer_id": offer["offer_id"],
                "decision": "ordered",
                "qty": qty,
                "required_for_offer": required_for_offer,
                "selection_reason": purchase["reason"],
                "stock_before": stock_before,
                "stock_after": order["stock_after"],
                "candidates": purchase["candidates"],
            })
        return orders, remaining

    def _line_alternates(self, line_id):
        return [grading for grading in self.gradings
                if grading.get("line_id") == line_id]

    def _plan_line(self, record):
        row = self.rows_by_id[record["line_id"]]
        matches, eligible, conflicts = self._primary_candidates(row)
        trace = []
        warnings = []
        blockers = []
        unknown_reasons = []
        substitution_info = []
        orders = []
        remaining = int(record["purchase_need"])
        if not row["dnp"] and record["purchase_need"] > 0:
            candidates = []
            for item in eligible:
                offer = item["offer"]
                candidates.append({
                    "offer": offer,
                    "match": item["match"],
                    "order_key": self._static_sort_key(offer),
                })
                if not offer.get("trusted"):
                    unknown_reasons.append({
                        "code": "stale_or_untrusted_snapshot",
                        "offer_id": offer["offer_id"],
                        "message": "快照过期/渠道不符；价格与库存均不作为已知"
                                   "证据",
                    })
                elif self.pools.available_for(offer) is None:
                    unknown_reasons.append({
                        "code": "stock_unknown",
                        "offer_id": offer["offer_id"],
                        "message": "库存未知；不能算作已满足",
                    })
            if not eligible:
                unknown_reasons.append({
                    "code": "no_supply_evidence",
                    "offer_id": None,
                    "message": "没有匹配且渠道允许的 offer；缺少供应证据，"
                               "不等于已证明买不到",
                })
            max_orders = self.demand["split_policy"]["max_orders_per_line"] \
                if self.demand["split_policy"]["allow_multi_offer"] else 1
            if self.strategy == "conservative_substitution":
                max_orders = min(max_orders, 2)
            orders, remaining = self._allocate(
                record, candidates, unknown_reasons, trace, max_orders)
            split_limited = bool(
                remaining > 0 and candidates
                and len(orders) >= max_orders
                and not unknown_reasons)
            total_limit_hit = bool(remaining > 0 and self.order_limit_hit
                                   and not unknown_reasons)
            # Conservative substitution only for the still-uncovered part.
            if (remaining > 0 and self.strategy ==
                    "conservative_substitution"):
                allowed_grades = self.demand["substitution"]["allowed_grades"]
                sub_candidates = []
                for grading in self._line_alternates(row["line_id"]):
                    subs = self._substitution_candidates(
                        row, grading, allowed_grades)
                    substitution_info.append({
                        "alt_id": grading.get("alt_id"),
                        "candidate_mpn": grading.get("candidate_mpn"),
                        "grade": grading.get("status"),
                        "used": False,
                        "available_offers": [item["offer"]["offer_id"]
                                             for item in subs],
                    })
                    for item in subs:
                        sub_candidates.append({
                            "offer": item["offer"],
                            "match": item["match"],
                            "alt_id": item["alt_id"],
                            "grading": item["grading"],
                            "order_key": self._static_sort_key(item["offer"]),
                        })
                if sub_candidates:
                    sub_orders, remaining = self._allocate(
                        record, sub_candidates, unknown_reasons, trace,
                        max(1, max_orders - len(orders)), substitution=True)
                    for order in sub_orders:
                        used = [info for info in substitution_info
                                if info["alt_id"] == order.get("alternate_id")]
                        for info in used:
                            info["used"] = True
                    orders.extend(sub_orders)
                elif self._line_alternates(row["line_id"]) and remaining > 0:
                    unknown_reasons.append({
                        "code": "substitution_candidate_without_offer",
                        "message": "存在替代候选但没有匹配/可信 offer；替代"
                                   "可行性未知",
                    })
        elif row["dnp"]:
            warnings.append("DNP 行不采购")
        elif record["purchase_need"] == 0:
            warnings.append("需求已被自备/损耗覆盖，采购量为 0")

        ordered_qty = sum(order["qty"] for order in orders)
        purchase_need = int(record["purchase_need"])
        shortage = max(0, purchase_need - ordered_qty)
        overbuy = max(0, ordered_qty - purchase_need)
        remaining_after_assembly = max(0, ordered_qty
                                       - int(record["assembled_qty"]))
        known_shortage = bool(remaining and not unknown_reasons)
        line_status = "not_required"
        if row["dnp"] or purchase_need == 0:
            line_status = "not_required"
        elif ordered_qty >= purchase_need:
            line_status = "covered"
            if any(order["simulated"] for order in orders):
                line_status = "covered_with_unknowns"
            if any(order["snapshot_truth"] in ("user_provided_unverified",
                                               "manual_table_unverified")
                   for order in orders):
                line_status = "covered_with_unknowns"
            if self.demand["due_date"] is not None and any(
                    order["lead_time"]["status"] in ("unknown", "late")
                    for order in orders):
                line_status = "covered_with_unknowns"
        elif remaining and unknown_reasons:
            line_status = "partial_unknown"
        else:
            line_status = "uncovered_known"
            if total_limit_hit:
                blockers.append({
                    "code": "max_orders_total_reached",
                    "message": "全单拆单上限 %s 已到，仍有未满足数量；这是"
                               "策略限制，不是库存事实"
                               % self.demand["split_policy"].get(
                                   "max_orders_total"),
                    "qty": remaining,
                })
            elif split_limited:
                blockers.append({
                    "code": "split_limit_reached",
                    "message": "拆单上限 %d 已到，仍有未满足数量；这是策略"
                               "限制，不是库存事实" % max_orders,
                    "qty": remaining,
                })
            else:
                blockers.append({
                    "code": "known_shortage",
                    "message": "已知库存/价格无法覆盖 %d 个采购需求"
                               % remaining,
                    "qty": remaining,
                })
        if self._tht_blocked(row):
            line_status = "uncovered_known"
            blockers.append({
                "code": "tht_not_supported_by_smt",
                "message": "THT/手焊行不能由仅 SMT 渠道全自动贴装；需商城"
                           "购料手焊或自备",
            })
        if row["dnp"] and record["consigned_requested"]:
            warnings.append("DNP 行的自备数量不抵扣任何需求")
        if known_shortage and not blockers:
            blockers.append({"code": "known_shortage",
                             "message": "已知条件无法覆盖剩余数量",
                             "qty": remaining})
        cost_raw = ZERO
        cost_groups = {}
        for order in orders:
            if order["line_total"] is None:
                continue
            cost_raw += order["line_total"]
            key = (order["currency"], order["tax_basis"])
            cost_groups[key] = cost_groups.get(key, ZERO) + order["line_total"]
        known_cost = [
            {"currency": currency, "tax_basis": tax_basis,
             "amount": amount}
            for (currency, tax_basis), amount in sorted(cost_groups.items())
        ]
        lead_status = self._line_lead_status(orders)
        conclusions = {
            "mall": channels.mall_conclusion(matches),
            "smt": channels.smt_conclusion(row, self.demand, matches),
            "hand_solder": channels.hand_solder_conclusion(row, self.demand),
        }
        return {
            "line_id": row["line_id"],
            "mpn": row["mpn"],
            "manufacturer": row["manufacturer"],
            "footprint": row["footprint"],
            "package": row["package"],
            "assembly": row["assembly"],
            "dnp": row["dnp"],
            "demand": record,
            "status": line_status,
            "confidence": self._confidence(line_status, unknown_reasons),
            "orders": orders,
            "ordered_qty": ordered_qty,
            "purchase_need": purchase_need,
            "shortage_qty": shortage,
            "assembly_shortage_qty": max(0, int(record["assembled_qty"])
                                         - ordered_qty),
            "overbuy_qty": overbuy,
            "remaining_after_assembly_qty": remaining_after_assembly,
            "known_cost": known_cost,
            "known_cost_total_raw": cost_raw,
            "channel_conclusions": conclusions,
            "lead_time": lead_status,
            "eligible_offers": [
                {"offer_id": item["offer"]["offer_id"],
                 "channel": item["offer"]["channel"],
                 "trusted": bool(item["offer"].get("trusted")),
                 "stock": item["offer"]["stock"]["status"]}
                for item in eligible
            ],
            "identity_conflicts": conflicts,
            "unknown_reasons": unknown_reasons,
            "blockers": blockers,
            "warnings": warnings,
            "alternates": self._line_alternates(row["line_id"]),
            "substitution": substitution_info,
            "trace": trace,
        }

    def _tht_blocked(self, row):
        if row["assembly"] not in ("tht", "hand"):
            return False
        allowed = self._allowed_channels(row)
        return not allowed and "jlc_smt" in self.demand["channels"]

    def _line_lead_status(self, orders):
        if not orders:
            return {"status": "not_applicable", "note": "无订单"}
        if self.demand["due_date"] is None:
            return {"status": "not_evaluated_no_due_date",
                    "note": "需求未给交期截止；不判按时交付"}
        statuses = [order["lead_time"]["status"] for order in orders]
        if "late" in statuses:
            return {"status": "late", "note": "至少一个订单按交期估算晚于截止"}
        if any(status in ("unknown", "stock_snapshot_only")
               for status in statuses):
            return {"status": "unknown",
                    "note": "至少一个订单缺交期性质/天数或只有现货快照；"
                            "不能判按时交付"}
        return {"status": "likely_on_time", "note": "按声明 days_max 估算不晚于"
                                                   "截止；非承诺"}

    def _confidence(self, line_status, unknown_reasons):
        if line_status in ("not_required", "covered"):
            return "evidence"
        if line_status == "covered_with_unknowns":
            return "evidence_with_unknowns"
        if line_status == "partial_unknown":
            return "unknown"
        return "known_shortage"

    # -- fees / budget / status ------------------------------------------
    def _compute_fees(self, orders):
        groups = {}
        for order in orders:
            key = (order["channel"], order["currency"])
            group = groups.setdefault(key, {
                "channel": order["channel"],
                "currency": order["currency"],
                "orders": [],
                "subtotal": ZERO,
                "tax_bases": set(),
                "line_ids": set(),
                "offer_ids": set(),
            })
            group["orders"].append(order)
            if order["line_total"] is not None:
                group["subtotal"] += order["line_total"]
            group["tax_bases"].add(order["tax_basis"])
            group["offer_ids"].add(order["offer_id"])
        known = []
        unknown = []
        for fee in self.prepared.fees:
            channels_to_check = ([fee["channel"]] if fee["channel"] != "any"
                                 else sorted({key[0] for key in groups}))
            matched = False
            for channel in channels_to_check:
                group = groups.get((channel, fee["currency"]))
                if group is None:
                    continue
                matched = True
                if fee["unknown"]:
                    unknown.append({
                        "fee_id": fee["fee_id"], "kind": fee["kind"],
                        "channel": channel, "currency": fee["currency"],
                        "reason": "费用金额/费率未提供；不按 0 计",
                    })
                    continue
                if fee["basis"] == "percent_of_subtotal":
                    if fee["tax_basis"] is not None and \
                            group["tax_bases"] != {fee["tax_basis"]}:
                        unknown.append({
                            "fee_id": fee["fee_id"], "kind": fee["kind"],
                            "channel": channel, "currency": fee["currency"],
                            "reason": "费率口径与商品税口径不一致，无法确定",
                        })
                        continue
                    amount = fee["rate"] * group["subtotal"]
                else:
                    count = {
                        "per_order": 1,
                        "per_line": len({order["line_id"]
                                         for order in group["orders"]}),
                        "per_part": len(group["offer_ids"]),
                        "per_board": self.prepared.project["board_quantity"],
                    }[fee["basis"]]
                    amount = fee["amount"] * count
                waived = False
                if fee["waiver"] is not None and fee["basis"] == "per_order":
                    if group["subtotal"] >= fee["waiver"]["min_subtotal"]:
                        amount = ZERO
                        waived = True
                known.append({
                    "fee_id": fee["fee_id"], "kind": fee["kind"],
                    "channel": channel, "currency": fee["currency"],
                    "basis": fee["basis"], "amount": amount,
                    "source": fee["source"],
                    "captured_at": fee["captured_at"],
                    "waived": waived,
                    "note": fee["note"],
                })
            if not matched and fee["unknown"] and groups:
                # Declared unknown fee for a channel/currency that did not
                # participate: it cannot apply to this plan.
                pass
        # Undeclared fee categories are unknown, never zero.
        if groups:
            channels_used = sorted({group["channel"]
                                    for group in groups.values()})
            for channel in channels_used:
                declared_shipping = any(
                    item["channel"] in (channel, "any")
                    and item["kind"] == "shipping"
                    for item in self.prepared.fees)
                if not declared_shipping:
                    unknown.append({
                        "fee_id": None, "kind": "shipping",
                        "channel": channel, "currency": None,
                        "reason": "输入未声明该渠道运费/免运规则；未知，不按 0 计",
                    })
                if channel == "jlc_smt":
                    declared_smt = any(
                        item["kind"] in ("smt_extended_part_fee",
                                         "smt_board_fee")
                        and item["channel"] in (channel, "any")
                        for item in self.prepared.fees)
                    if not declared_smt:
                        unknown.append({
                            "fee_id": None, "kind": "smt_fee",
                            "channel": channel, "currency": None,
                            "reason": "输入未声明 SMT 扩展料费/板费；未知，"
                                      "不按 0 计",
                        })
            group_tax = set()
            for group in groups.values():
                group_tax |= group["tax_bases"]
            if "unknown" in group_tax:
                unknown.append({
                    "fee_id": None, "kind": "tax",
                    "channel": None, "currency": None,
                    "reason": "存在 tax_basis=unknown 的商品；税口径不明",
                })
            elif "excl" in group_tax:
                declared_tax = any(item["kind"] == "tax"
                                   for item in self.prepared.fees)
                if not declared_tax:
                    unknown.append({
                        "fee_id": None, "kind": "tax",
                        "channel": None, "currency": None,
                        "reason": "商品为税前价但未声明税率；未知，不按 0 计",
                    })
        known_totals = {}
        for item in known:
            key = item["currency"]
            known_totals[key] = known_totals.get(key, ZERO) + item["amount"]
        return {
            "known": known,
            "known_total_by_currency": known_totals,
            "unknown": unknown,
            "coverage": "declared_only",
            "note": "只计算输入声明的费用；未声明项列为未知，不按 0 计",
        }

    def _budget_analysis(self, fee_result, orders, unknown_items):
        budget = self.demand["budget"]
        goods = {}
        for order in orders:
            if order["line_total"] is None:
                continue
            goods[order["currency"]] = goods.get(order["currency"], ZERO) \
                + order["line_total"]
        known_total = dict(goods)
        for currency, amount in fee_result["known_total_by_currency"].items():
            known_total[currency] = known_total.get(currency, ZERO) + amount
        if budget is None:
            return {"status": "not_configured",
                    "known_total_by_currency": known_total,
                    "note": "需求未给预算；只报告已知金额与未知项"}
        budget_currency = budget["currency"]
        if not known_total:
            return {"status": "within_budget", "budget": budget,
                    "known_total_by_currency": known_total,
                    "note": "当前无可计金额"}
        try:
            converted, fx_used = self._convert_to(known_total,
                                                  budget_currency)
        except ValueError as exc:
            if budget_currency in known_total \
                    and known_total[budget_currency] > budget["amount"]:
                return {"status": "exceeded",
                        "budget": budget,
                        "known_total_by_currency": known_total,
                        "converted_total": None,
                        "note": "已有同币种已知金额超过预算；其余币种未换算"}
            return {"status": "undetermined_currency", "budget": budget,
                    "known_total_by_currency": known_total,
                    "converted_total": None,
                    "note": str(exc)}
        unknown_affects_budget = bool(
            [item for item in fee_result["unknown"]
             if item.get("currency") in (None, budget_currency)])
        unknown_affects_budget = unknown_affects_budget or bool(
            unknown_items.get("unknown_price_lines"))
        if converted > budget["amount"]:
            status = "exceeded"
            note = "已知合计 %s 超过预算 %s；未知项只会更高" % (
                format_amount(converted, budget_currency),
                format_amount(budget["amount"], budget_currency))
        elif unknown_affects_budget:
            status = "undetermined_unknowns"
            note = "已知合计未超预算，但存在未知费用/价格；不能声称在预算内"
        else:
            status = "within_budget"
            note = "按已知金额判断在预算内；不含未声明费用"
        line_costs = []
        for line in self.lines:
            for item in line["known_cost"]:
                line_costs.append({
                    "line_id": line["line_id"],
                    "currency": item["currency"],
                    "amount": item["amount"],
                })
        line_costs.sort(key=lambda item: (item["currency"],
                                          -float(item["amount"]),
                                          item["line_id"]))
        return {
            "status": status,
            "budget": budget,
            "known_total_by_currency": known_total,
            "converted_total": converted,
            "converted_currency": budget_currency,
            "fx_used": fx_used,
            "note": note,
            "lines_by_known_cost": line_costs,
        }

    def _convert_to(self, totals, target):
        from decimal import Decimal as D
        result = D("0")
        used = []
        for currency, amount in totals.items():
            if currency == target:
                result += amount
                continue
            rate = None
            direction = None
            for fx in self.prepared.fx_rates:
                if fx["base"] == currency and fx["quote"] == target:
                    rate, direction = fx["rate"], "direct"
                    source = fx
                    break
                if fx["base"] == target and fx["quote"] == currency:
                    rate, direction = fx["rate"], "inverse"
                    source = fx
                    break
            if rate is None:
                raise ValueError(
                    "缺少 %s/%s 汇率，无法合成总价；分币种报告" % (currency,
                                                                  target))
            max_age = self.prepared.evaluation["max_age_hours"]
            if max_age is not None:
                from .util import ago_hours
                age = ago_hours(source["captured_at"],
                                self.prepared.evaluation["as_of"])
                if D(str(age)) > max_age:
                    raise ValueError(
                        "汇率 %s/%s 已过期（%.1f h > %s h）"
                        % (source["base"], source["quote"], age, max_age))
            if direction == "direct":
                converted = amount * rate
            else:
                converted = amount / rate
            result += converted
            used.append({"base": source["base"], "quote": source["quote"],
                         "rate": str(rate), "direction": direction,
                         "source": source["source"],
                         "captured_at": source["captured_at"]})
        return result, used

    def _unknown_items(self):
        items = {
            "unknown_price_lines": [],
            "unknown_stock_lines": [],
            "stale_or_untrusted_lines": [],
            "no_offer_lines": [],
            "substitution_lines": [],
            "lead_time_unconfirmed_lines": [],
            "mixed_currency": False,
            "synthetic_snapshots": [],
            "unverified_snapshots": [],
        }
        for line in self.lines:
            reasons = line["unknown_reasons"]
            codes = {reason["code"] for reason in reasons}
            if "price_unknown" in codes or "substitution_candidate_without_offer" in codes:
                items["unknown_price_lines"].append(line["line_id"])
            if "stock_unknown" in codes:
                items["unknown_stock_lines"].append(line["line_id"])
            if "stale_or_untrusted_snapshot" in codes:
                items["stale_or_untrusted_lines"].append(line["line_id"])
            if "no_supply_evidence" in codes:
                items["no_offer_lines"].append(line["line_id"])
            if line["status"] == "partial_unknown" and line["substitution"]:
                items["substitution_lines"].append(line["line_id"])
            if line["lead_time"]["status"] == "unknown":
                items["lead_time_unconfirmed_lines"].append(line["line_id"])
            for order in line["orders"]:
                if order["simulated"]:
                    items["synthetic_snapshots"].append(order["snapshot_id"])
                elif order["snapshot_truth"] in ("user_provided_unverified",
                                                 "manual_table_unverified"):
                    items["unverified_snapshots"].append(order["snapshot_id"])
        items["synthetic_snapshots"] = sorted(set(items["synthetic_snapshots"]))
        items["unverified_snapshots"] = sorted(
            set(items["unverified_snapshots"]))
        currencies = {order["currency"] for line in self.lines
                      for order in line["orders"]}
        items["mixed_currency"] = len(currencies) > 1
        for key, value in items.items():
            if isinstance(value, list):
                items[key] = sorted(set(value), key=str)
        return items

    def plan(self):
        for record in self.records:
            self.lines.append(self._plan_line(record))
        orders = [order for line in self.lines for order in line["orders"]]
        fee_result = self._compute_fees(orders)
        unknown_items = self._unknown_items()
        budget = self._budget_analysis(fee_result, orders, unknown_items)
        blockers = []
        warnings = list(self.findings.sorted())
        if budget["status"] == "exceeded":
            blockers.append({
                "code": "budget_exceeded",
                "message": budget["note"],
            })
        for line in self.lines:
            for blocker in line["blockers"]:
                blockers.append({
                    "code": blocker["code"],
                    "line_id": line["line_id"],
                    "message": blocker["message"],
                })
        status = self._status(budget, unknown_items)
        counts = {
            "lines_total": len(self.lines),
            "not_required": sum(1 for line in self.lines
                                if line["status"] == "not_required"),
            "covered": sum(1 for line in self.lines
                           if line["status"] == "covered"),
            "covered_with_unknowns": sum(
                1 for line in self.lines
                if line["status"] == "covered_with_unknowns"),
            "partial_unknown": sum(1 for line in self.lines
                                   if line["status"] == "partial_unknown"),
            "uncovered_known": sum(1 for line in self.lines
                                   if line["status"] == "uncovered_known"),
            "orders": len(orders),
            "overbuy_qty": sum(line["overbuy_qty"] for line in self.lines),
            "shortage_qty": sum(line["shortage_qty"] for line in self.lines),
        }
        known_goods = {}
        for line in self.lines:
            for item in line["known_cost"]:
                key = (item["currency"], item["tax_basis"])
                known_goods[key] = known_goods.get(key, ZERO) \
                    + item["amount"]
        summary = {
            "strategy": self.strategy,
            "label": STRATEGY_LABELS[self.strategy],
            "status": status,
            "counts": counts,
            "known_goods_by_currency_tax_basis": [
                {"currency": currency, "tax_basis": tax_basis,
                 "amount": amount}
                for (currency, tax_basis), amount in sorted(
                    known_goods.items())
            ],
            "known_fee_total_by_currency": fee_result[
                "known_total_by_currency"],
            "budget_status": budget["status"],
            "unknown_fee_count": len(fee_result["unknown"]),
            "unknown_items": unknown_items,
            "blockers": blockers,
            "orders": len(orders),
        }
        return {
            "strategy": self.strategy,
            "label": STRATEGY_LABELS[self.strategy],
            "status": status,
            "lines": self.lines,
            "orders": orders,
            "fees": fee_result,
            "budget": budget,
            "blockers": blockers,
            "warnings": warnings,
            "unknowns": unknown_items,
            "counts": counts,
            "summary": summary,
            "bounded_search": {
                "method": "greedy_bounded",
                "global_optimum_claimed": False,
                "search_steps": self.search_steps,
                "max_search_steps": self.prepared.policies.get(
                    "search", {}).get("max_search_steps", 10000),
                "search_budget_exhausted": self.search_budget_exhausted,
                "split_limit": self.demand["split_policy"],
                "overbuy_policy": self.demand["overbuy"],
                "note": "逐行贪心、有界拆单与有界超购；用确定性步数预算代替"
                        "墙钟超时，避免基准漂移；不声称全局最优",
            },
        }

    def _status(self, budget, unknown_items):
        if budget["status"] == "exceeded":
            return "unsatisfied"
        if any(line["status"] == "uncovered_known" for line in self.lines):
            return "unsatisfied"
        if budget["status"] == "undetermined_currency":
            return "planned_with_unknowns"
        unknown = bool(
            unknown_items["unknown_price_lines"]
            or unknown_items["unknown_stock_lines"]
            or unknown_items["stale_or_untrusted_lines"]
            or unknown_items["no_offer_lines"]
            or unknown_items["substitution_lines"]
            or unknown_items["mixed_currency"]
            or unknown_items["synthetic_snapshots"]
            or unknown_items["unverified_snapshots"]
            or unknown_items["lead_time_unconfirmed_lines"])
        if any(line["status"] == "partial_unknown" for line in self.lines):
            unknown = True
        if any(line["status"] == "covered_with_unknowns" for line in self.lines):
            unknown = True
        return "planned_with_unknowns" if unknown \
            else "planned_with_evidence"


def plan_all(prepared, requested_strategies=None, gradings=None):
    gradings = gradings or []
    gradings_by_alt = {item["alt_id"]: item for item in gradings}
    if requested_strategies:
        names = [name for name in STRATEGIES
                 if name in requested_strategies]
    else:
        names = list(STRATEGIES)
    strategy_plans = []
    for name in names:
        planner = StrategyPlanner(prepared, name, gradings, gradings_by_alt)
        result = planner.plan()
        # Unknown fees are only known after fee computation; fold them into
        # the status without inventing a second pass.
        if result["fees"]["unknown"] and result["status"] \
                != "unsatisfied":
            result["status"] = "planned_with_unknowns"
            result["summary"]["status"] = "planned_with_unknowns"
        strategy_plans.append(result)
    preferred = _choose_preferred(strategy_plans)
    comparison = _compare(strategy_plans, preferred)
    return {
        "strategies": strategy_plans,
        "preferred": preferred,
        "comparison": comparison,
    }


def _choose_preferred(strategy_plans):
    if not strategy_plans:
        return None
    if len(strategy_plans) == 1:
        plan = strategy_plans[0]
        return {"strategy": plan["strategy"],
                "reason": "只请求了该策略"}
    evidence = [plan for plan in strategy_plans
                if plan["status"] == "planned_with_evidence"]
    if evidence:
        evidence.sort(key=lambda plan: (plan["counts"]["partial_unknown"],
                                        plan["counts"]["uncovered_known"],
                                        STRATEGIES.index(plan["strategy"])))
        return {"strategy": evidence[0]["strategy"],
                "reason": "该策略在已知证据下完整覆盖，未知项最少"}
    satisfiable = [plan for plan in strategy_plans
                   if plan["status"] != "unsatisfied"] or strategy_plans
    satisfiable.sort(key=lambda plan: (
        plan["counts"]["uncovered_known"],
        plan["counts"]["partial_unknown"],
        plan["counts"]["shortage_qty"],
        STRATEGIES.index(plan["strategy"])))
    chosen = satisfiable[0]
    return {
        "strategy": chosen["strategy"],
        "reason": "按覆盖行数/缺料数量排序的启发式选择；不是全局最优声明",
    }


def _known_total(plan):
    goods = {}
    for item in plan["summary"]["known_goods_by_currency_tax_basis"]:
        goods[item["currency"]] = goods.get(item["currency"], ZERO) \
            + item["amount"]
    fees = plan["summary"]["known_fee_total_by_currency"]
    for currency, amount in fees.items():
        goods[currency] = goods.get(currency, ZERO) + amount
    return goods


def _compare(strategy_plans, preferred):
    ranking = []
    indeterminate = False
    currencies = set()
    satisfiable = [plan for plan in strategy_plans
                   if plan["status"] != "unsatisfied"]
    for plan in satisfiable:
        if plan["fees"]["unknown"]:
            indeterminate = True
        for currency in _known_total(plan):
            currencies.add(currency)
    if satisfiable and len(currencies) == 1 and not indeterminate:
        currency = next(iter(currencies))
        for plan in satisfiable:
            ranking.append({
                "strategy": plan["strategy"],
                "known_total": _known_total(plan).get(currency, ZERO),
                "currency": currency,
            })
        ranking.sort(key=lambda item: (item["known_total"],
                                       STRATEGIES.index(item["strategy"])))
        reason = ("仅比较已知商品小计+已知费用；未知项未按 0 参与排序；"
                  "unsatisfied 策略不参与最低成本比较")
    elif not satisfiable:
        reason = ("所有策略均为 unsatisfied；没有可比较的满足方案，"
                  "不能把 0 成本当作最低成本")
    else:
        reason = ("无法确定完整成本排序：存在未知费用或混合币种/汇率；"
                  "仅可比较已知子集，不能宣称最低总成本")
    preferred_plan = None
    if preferred:
        for plan in strategy_plans:
            if plan["strategy"] == preferred["strategy"]:
                preferred_plan = plan
                break
    differences = []
    if preferred_plan is not None:
        for plan in strategy_plans:
            if plan is preferred_plan:
                continue
            differences.append({
                "strategy": plan["strategy"],
                "status_difference": "%s -> %s" % (plan["status"],
                                                   preferred_plan["status"]),
                "orders_difference": plan["counts"]["orders"]
                - preferred_plan["counts"]["orders"],
                "shortage_difference": plan["counts"]["shortage_qty"]
                - preferred_plan["counts"]["shortage_qty"],
                "unknown_fee_difference": len(plan["fees"]["unknown"])
                - len(preferred_plan["fees"]["unknown"]),
                "summary": _describe(plan),
            })
    return {
        "known_cost_ranking": ranking if ranking else None,
        "known_cost_ranking_reason": reason,
        "ranking_determinate": bool(ranking),
        "unknown_or_mixed_blocks_ranking": bool(indeterminate
                                                or len(currencies) > 1),
        "recommended_strategy": preferred["strategy"]
        if preferred and preferred_plan is not None
        and preferred_plan["status"] == "planned_with_evidence" else None,
        "recommended_strategy_note": (
            "只有完整已知证据的策略才给推荐；否则仅给候选与差异"),
        "differences": differences,
    }


def _describe(plan):
    counts = plan["counts"]
    return ("%s：覆盖 %d 行，部分未知 %d 行，已知缺料 %d 行，订单 %d 个，"
            "缺料数量 %d，未知费用 %d 项"
            % (STRATEGY_LABELS.get(plan["strategy"], plan["strategy"]),
               counts["covered"] + counts["covered_with_unknowns"],
               counts["partial_unknown"], counts["uncovered_known"],
               counts["orders"], counts["shortage_qty"],
               len(plan["fees"]["unknown"])))
