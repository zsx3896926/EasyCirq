"""Channel semantics: LCSC mall purchase vs JLC SMT placement.

Mall stock never implies SMT attachability and a C-number never implies either.
Every SMT conclusion below is derived only from an offer's independent ``smt``
fields (attachability + evidence) on the ``jlc_smt`` channel.  THT/hand rows
are not pretended to be fully automatic SMT work.
"""

from __future__ import annotations

import re

from .util import normalize_identity, normalize_supply_id

TINY_PACKAGE_RE = re.compile(r"(?:^|[^0-9])(0201|0402|1005)(?:[^0-9]|$)")


def match_offer(row, offer):
    """Classify how an offer relates to a BOM row identity."""

    row_mpn = normalize_identity(row["mpn"])
    offer_mpn = normalize_identity(offer["mpn"])
    row_fp = normalize_identity(row["footprint"])
    offer_fp = normalize_identity(offer["footprint"])
    row_lcsc = normalize_supply_id(row.get("supply_ids", {}).get("lcsc", ""))
    offer_pid = normalize_supply_id(offer.get("product_id", ""))
    warnings = []
    if row_lcsc and offer_pid == row_lcsc:
        if offer_mpn != row_mpn:
            return {"status": "conflict", "offer": offer,
                    "reason": "supply_id_mpn_conflict",
                    "warnings": ["C 号相同但 MPN 不同，供应身份冲突"]}
        if offer_fp != row_fp:
            return {"status": "conflict", "offer": offer,
                    "reason": "supply_id_footprint_conflict",
                    "warnings": ["C 号相同但封装不同，供应身份冲突"]}
        if row.get("manufacturer") and offer.get("manufacturer") and \
                normalize_identity(row["manufacturer"]) != normalize_identity(
                    offer["manufacturer"]):
            return {"status": "conflict", "offer": offer,
                    "reason": "supply_id_manufacturer_conflict",
                    "warnings": ["C 号相同但制造商不同，供应身份冲突"]}
        return {"status": "match", "offer": offer, "reason": "supply_id",
                "warnings": warnings}
    if offer_mpn != row_mpn or offer_fp != row_fp:
        return {"status": "no_match", "offer": offer, "reason": "identity",
                "warnings": warnings}
    if row.get("manufacturer") and offer.get("manufacturer") and \
            normalize_identity(row["manufacturer"]) != normalize_identity(
                offer["manufacturer"]):
        return {"status": "conflict", "offer": offer,
                "reason": "manufacturer_conflict",
                "warnings": ["MPN+封装相同但制造商不同，不能直接当同一器件"]}
    if not row.get("manufacturer") or not offer.get("manufacturer"):
        warnings.append("制造商缺失；MPN+封装匹配保留为待核")
    if row_lcsc and offer_pid and row_lcsc != offer_pid:
        warnings.append("BOM C 号 %s 与 offer 产品 ID %s 不同；"
                        "按 MPN+封装匹配但需核对是否同一商品"
                        % (row_lcsc, offer_pid))
    return {"status": "match", "offer": offer, "reason": "mpn_footprint",
            "warnings": warnings}


def matched_offers(row, offers):
    result = []
    for offer in offers:
        result.append(match_offer(row, offer))
    return result


def smt_conclusion(row, demand, matches):
    """Return an SMT conclusion that never borrows mall stock as evidence."""

    requested = ("jlc_smt" in demand["channels"]
                 and row["assembly"] == "smt"
                 and demand["assembly_strategy"] != "hand_solder")
    if row["assembly"] in ("tht", "hand"):
        return {
            "status": "not_applicable_tht" if "jlc_smt" in demand["channels"]
            else "not_requested",
            "reason": "THT/手焊行不走全自动 SMT 贴装；单列手焊/自备路线",
            "evidence": None,
        }
    if not requested:
        return {"status": "not_requested", "reason": "需求未选择 SMT 渠道",
                "evidence": None}
    smt_matches = [item for item in matches
                   if item["status"] in ("match", "match_with_warning")
                   and item["offer"]["channel"] == "jlc_smt"]
    if not smt_matches:
        return {"status": "no_smt_offer",
                "reason": "没有 jlc_smt 渠道的匹配 offer；商城库存不能推断"
                          "SMT 可贴", "evidence": None}
    states = []
    for item in smt_matches:
        offer = item["offer"]
        smt = offer.get("smt") or {}
        attach = smt.get("attachability", "unknown")
        states.append({
            "offer_id": offer["offer_id"],
            "attachability": attach,
            "evidence_ok": bool(smt.get("evidence_ok")),
            "evidence": smt.get("evidence"),
            "min_placement_qty": smt.get("min_placement_qty"),
            "feed_type": smt.get("feed_type"),
            "fee_ref": smt.get("fee_ref"),
        })
    with_evidence = [state for state in states
                     if state["attachability"] in ("basic", "extended")
                     and state["evidence_ok"]]
    if with_evidence:
        return {"status": "candidate_with_evidence",
                "reason": "仅表示有独立来源的 SMT 基础/扩展库候选；"
                          "不是当日订单确认",
                "evidence": with_evidence[0]["evidence"],
                "states": states}
    consigned = [state for state in states
                 if state["attachability"] == "consigned"]
    if consigned:
        return {"status": "consigned_only",
                "reason": "仅 consigned/自备料路径；需确认工厂接受与入库",
                "evidence": consigned[0]["evidence"], "states": states}
    if any(state["attachability"] in ("basic", "extended")
           for state in states):
        return {"status": "claim_without_evidence",
                "reason": "声明可贴但无独立来源；只能标待核",
                "evidence": None, "states": states}
    return {"status": "smt_status_unknown",
            "reason": "SMT 字段缺失/未知；不得由商城库存或 C 号推断",
            "evidence": None, "states": states}


def hand_solder_conclusion(row, demand):
    if row["assembly"] in ("dnp",):
        return {"status": "not_required", "reason": "DNP 不装配"}
    allowed = demand["hand_solder_allowed"] or demo_hand_strategy(demand)
    if not allowed:
        return {"status": "not_allowed_by_policy",
                "reason": "需求未允许手焊/自备履约；不把 SMT 全自动当完成"}
    package_text = " ".join((str(row.get("package") or ""),
                             str(row.get("footprint") or ""))).upper()
    match = TINY_PACKAGE_RE.search(package_text)
    if match:
        code = match.group(1)
        if code == "0201":
            return {"status": "not_recommended",
                    "reason": "0201 封装无法可靠手焊；需改 SMT 或换封装"}
        return {"status": "allowed_with_difficulty",
                "reason": "0402/1005 手焊难度高；须记录返修能力与验收标准"}
    return {"status": "allowed_by_policy",
            "reason": "允许手焊/自备履约；该路线不是 SMT 全自动贴装"}


def demo_hand_strategy(demand):
    return demand.get("assembly_strategy") == "hand_solder"


def mall_conclusion(matches):
    mall = [item for item in matches
            if item["status"] in ("match", "match_with_warning")
            and item["offer"]["channel"] == "lcsc_mall"]
    if not mall:
        return {"status": "no_mall_offer",
                "reason": "没有匹配的商城 offer；需补商城快照"}
    trusted = [item for item in mall if item["offer"].get("trusted")]
    if not trusted:
        return {"status": "stale_or_untrusted_snapshot",
                "reason": "商城 offer 的快照已过期/渠道不符；不能当当前可买"}
    unknown_stock = [item for item in trusted
                     if item["offer"]["stock"]["available"] is None]
    known_stock = [item for item in trusted
                   if item["offer"]["stock"]["available"] is not None]
    if known_stock:
        return {"status": "purchasable_with_snapshot_evidence",
                "reason": "有来源快照与已知库存；不是实时可买/未锁库",
                "offers": [item["offer"]["offer_id"] for item in trusted]}
    if unknown_stock:
        return {"status": "listed_stock_unknown",
                "reason": "有商品/价格记录但库存未知；未知库存不视作有货",
                "offers": [item["offer"]["offer_id"] for item in trusted]}
    return {"status": "no_known_stock", "reason": "商城 offer 无已知可用库存",
            "offers": [item["offer"]["offer_id"] for item in trusted]}
