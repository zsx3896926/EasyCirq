"""Report builders: machine JSON, Markdown and procurement CSV.

Every report carries a NOT_ORDER / NOT_LIVE_QUOTE watermark and records
``real_eda=NOT RUN`` and ``live_supply_query=NOT RUN``.  CSV export is
spreadsheet formula-injection guarded; internal MPN values are never changed.
"""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from decimal import Decimal

from . import (ALTERNATES_SCHEMA, DEMAND_SCHEMA, EXPLAIN_SCHEMA,
               NOT_CHECKED, PLAN_SCHEMA, TOOL_VERSION, VALIDATION_SCHEMA)
from .demand import expand_rows
from .money import format_amount, quantize
from .util import format_utc, csv_safe_cell

MONEY_KEYS = {"amount", "line_total", "known_total", "converted_total",
              "total", "subtotal", "known_cost_total"}
WATERMARK = ("NOT_ORDER | NOT_LIVE_QUOTE | OFFLINE PLAN — 本报告不构成订单、"
             "不构成实时报价，也未预留库存。")


def decimal_str(value):
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    if text in ("", "-0"):
        return "0"
    return text


def serialize(value, currency=None, key=None):
    if isinstance(value, Decimal):
        if currency and key in MONEY_KEYS:
            return format_amount(quantize(value, currency), currency)
        return decimal_str(value)
    if isinstance(value, datetime):
        return format_utc(value)
    if isinstance(value, dict):
        from .money import CURRENCIES
        local_currency = None
        for name in ("currency", "converted_currency", "order_currency"):
            candidate = value.get(name)
            if isinstance(candidate, str) and candidate in CURRENCIES:
                local_currency = candidate
                break
        result = {}
        for name, item in value.items():
            if name in ("known_total_by_currency",
                        "known_fee_total_by_currency") \
                    and isinstance(item, dict):
                result[name] = {
                    code: format_amount(quantize(amount, code), code)
                    for code, amount in item.items()
                }
            else:
                result[name] = serialize(item,
                                         currency=local_currency or currency,
                                         key=name)
        return result
    if isinstance(value, (list, tuple)):
        return [serialize(item, currency=currency, key=key) for item in value]
    if isinstance(value, set):
        return sorted(serialize(item, currency=currency, key=key)
                      for item in value)
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return value


def _input_block(prepared):
    doc = prepared.raw or {}
    return {
        "schema": doc.get("schema"),
        "sha256": prepared.input_sha256,
        "path": getattr(prepared, "source_label", None),
        "bom_csv": prepared.csv,
    }


def _project_block(prepared):
    return {
        "name": prepared.project.get("name"),
        "bom_revision": prepared.project.get("bom_revision"),
        "bom_source_sha256_declared": prepared.project.get(
            "bom_source_sha256"),
        "bom_source_sha256_computed": getattr(prepared,
                                             "bom_computed_sha256", None),
        "board_quantity": prepared.project.get("board_quantity"),
    }


def _evaluation_block(prepared):
    return {
        "as_of": prepared.evaluation.get("as_of"),
        "as_of_source": prepared.evaluation.get("as_of_source"),
        "max_age_hours": prepared.evaluation.get("max_age_hours"),
        "replay_note": "所有时效判断都以声明的评估时刻重放；导入/文件修改"
                       "时间不会让旧快照变新",
    }


def _supply_block(prepared):
    snapshots = []
    for snapshot in sorted(prepared.snapshots.values(),
                           key=lambda item: item["snapshot_id"]):
        snapshots.append({
            "snapshot_id": snapshot["snapshot_id"],
            "source": snapshot["source"],
            "declared_truth": snapshot["declared_truth"],
            "captured_at": snapshot["captured_at"],
            "valid_until": snapshot["valid_until"],
            "channel": snapshot["channel"],
            "age_hours": snapshot["age_hours"],
            "stale": snapshot["stale"],
            "stale_reasons": snapshot["stale_reasons"],
            "live_supply_query": snapshot["live_supply_query"],
            "sha256": snapshot["sha256"],
        })
    return {
        "snapshots": snapshots,
        "live_supply_query": "NOT RUN",
        "note": "快照来源与捕获时间来自输入声明；本工具不执行商城/API 查询，"
                "不把模拟数据标成实时可买",
    }


def _counts(prepared):
    designators = sum(len(row["designators"]) for row in prepared.rows)
    return {
        "rows": len(prepared.rows),
        "designators": designators,
        "dnp_rows": sum(1 for row in prepared.rows if row["dnp"]),
        "offers": len(prepared.offers),
        "snapshots": len(prepared.snapshots),
        "findings_blocking": prepared.findings.blocking_count,
        "findings_warning": prepared.findings.warning_count,
    }


def build_validation_report(prepared, strict=False):
    findings = prepared.findings.sorted()
    if strict:
        for finding in findings:
            if finding["level"] == "warning":
                finding["level"] = "blocking"
                finding["promoted"] = True
    blocking = sum(1 for finding in findings if finding["level"] == "blocking")
    return serialize({
        "schema": VALIDATION_SCHEMA,
        "tool_version": TOOL_VERSION,
        "status": "input_invalid" if blocking else "valid",
        "input": _input_block(prepared),
        "project": _project_block(prepared),
        "evaluation": _evaluation_block(prepared),
        "counts": _counts(prepared),
        "bom": {
            "rows": len(prepared.rows),
            "designators": sum(len(row["designators"])
                               for row in prepared.rows),
            "dnp_rows": sum(1 for row in prepared.rows if row["dnp"]),
            "identity_conflicts": [
                finding for finding in findings
                if "conflict" in finding["code"]
            ],
        },
        "findings": findings,
        "strict": strict,
        "limits": _limits(prepared, simulated=False),
        "not_checked": list(NOT_CHECKED),
    })


def build_demand_report(prepared):
    findings = prepared.findings.sorted()
    blocking = prepared.findings.blocking_count
    records = []
    if not blocking:
        records = expand_rows(prepared.rows,
                              prepared.project["board_quantity"],
                              prepared.policies, prepared.demand,
                              prepared.findings)
    return serialize({
        "schema": DEMAND_SCHEMA,
        "tool_version": TOOL_VERSION,
        "status": "input_invalid" if blocking else "valid",
        "input": _input_block(prepared),
        "project": _project_block(prepared),
        "evaluation": _evaluation_block(prepared),
        "policies": {
            "attrition": prepared.policies.get("attrition"),
            "order_policy": prepared.policies.get("order_policy"),
            "overbuy": prepared.policies.get("overbuy"),
            "substitution": prepared.demand.get("substitution"),
            "split_policy": prepared.demand.get("split_policy"),
            "assembly_strategy": prepared.demand.get("assembly_strategy"),
            "channels": prepared.demand.get("channels"),
            "hand_solder_allowed": prepared.demand.get(
                "hand_solder_allowed"),
            "self_supply_allowed": prepared.demand.get(
                "self_supply_allowed"),
            "due_date": prepared.demand.get("due_date"),
            "budget": prepared.demand.get("budget"),
        },
        "demand": records,
        "findings": findings,
        "counts": {
            "rows": len(records),
            "assembled_qty": sum(record["assembled_qty"]
                                 for record in records),
            "spare_qty": sum(record["attrition"]["spare_total"]
                             for record in records),
            "target_qty": sum(record["target_qty"] for record in records),
            "consigned_applied": sum(record["consigned_applied"]
                                     for record in records),
            "purchase_need": sum(record["purchase_need"]
                                 for record in records),
        },
        "limits": _limits(prepared, simulated=False),
        "not_checked": list(NOT_CHECKED),
    })


def _strategy_summary(plan):
    return {
        "strategy": plan["strategy"],
        "label": plan["label"],
        "status": plan["status"],
        "counts": plan["counts"],
        "known_goods_by_currency_tax_basis": plan["summary"][
            "known_goods_by_currency_tax_basis"],
        "known_fee_total_by_currency": plan["summary"][
            "known_fee_total_by_currency"],
        "unknown_fee_count": len(plan["fees"]["unknown"]),
        "budget_status": plan["budget"]["status"],
        "blockers": plan["blockers"],
        "unknowns": plan["unknowns"],
        "bounded_search": plan["bounded_search"],
        "line_statuses": [
            {
                "line_id": line["line_id"],
                "status": line["status"],
                "purchase_need": line["purchase_need"],
                "ordered_qty": line["ordered_qty"],
                "shortage_qty": line["shortage_qty"],
                "overbuy_qty": line["overbuy_qty"],
            }
            for line in plan["lines"]
        ],
    }


def build_plan_report(prepared, planned, gradings):
    strategies = planned["strategies"]
    preferred_name = planned["preferred"]["strategy"] if planned["preferred"] \
        else strategies[0]["strategy"]
    preferred = next(plan for plan in strategies
                     if plan["strategy"] == preferred_name)
    all_warnings = prepared.findings.sorted()
    for plan in strategies:
        for warning in plan["warnings"]:
            if warning.get("level") == "warning":
                all_warnings.append(warning)
    selected_orders = preferred["orders"]
    simulated_ids = sorted({order["snapshot_id"] for order in selected_orders
                            if order["simulated"]})
    currencies = sorted({order["currency"] for order in selected_orders})
    fx_used = preferred["budget"].get("fx_used", [])
    alternatives = []
    for grading in gradings:
        alternatives.append(grading)
    report = {
        "schema": PLAN_SCHEMA,
        "tool_version": TOOL_VERSION,
        "status": preferred["status"],
        "input": _input_block(prepared),
        "project": _project_block(prepared),
        "evaluation": _evaluation_block(prepared),
        "supply": _supply_block(prepared),
        "currency": {
            "reporting": "per_currency_per_tax_basis",
            "order_currencies": currencies,
            "tax_bases": sorted({order["tax_basis"]
                                 for order in selected_orders}),
            "fx_used": fx_used,
            "note": "不同币种不合成假总价；无来源/过期汇率时分币种报告",
        },
        "demand": [line["demand"] for line in preferred["lines"]],
        "preferred_strategy": preferred_name,
        "preferred_reason": planned["preferred"]["reason"]
        if planned["preferred"] else None,
        "strategies": [_strategy_summary(plan) for plan in strategies],
        "comparison": planned["comparison"],
        "plan": {
            "strategy": preferred_name,
            "lines": preferred["lines"],
            "orders": preferred["orders"],
            "fees": preferred["fees"],
            "budget": preferred["budget"],
            "counts": preferred["counts"],
            "bounded_search": preferred["bounded_search"],
            "blockers": preferred["blockers"],
            "unknowns": preferred["unknowns"],
        },
        "alternates": alternatives,
        "blockers": preferred["blockers"],
        "warnings": all_warnings,
        "unknowns": preferred["unknowns"],
        "limits": _limits(prepared,
                          simulated=bool(simulated_ids),
                          simulated_ids=simulated_ids),
        "not_checked": list(NOT_CHECKED),
        "report_notes": [
            "status 只使用 planned_with_evidence/planned_with_unknowns/"
            "unsatisfied/input_invalid；不使用 order_ready 或 "
            "procurement_verified",
            "未知费用/价格/库存不按 0 参与最低总成本排序",
            "多策略结果是有界贪心候选，不声称全局最优",
        ],
    }
    return serialize(report)


def _limits(prepared, simulated, simulated_ids=None):
    return {
        "not_order": True,
        "not_live_quote": True,
        "live_supply_query": "NOT RUN",
        "real_eda": "NOT RUN",
        "eda_calls": "NOT RUN",
        "network_access": "NOT RUN",
        "simulated_data": bool(simulated),
        "simulated_snapshot_ids": simulated_ids or [],
        "watermark": WATERMARK,
        "note": "不登录、不抓取商城、不下单、不锁库存、不调用 EDA；"
                "输出不改写输入 BOM 或任何设计文件",
    }


def build_alternates_report(prepared, gradings, findings):
    statuses = {}
    for grading in gradings:
        statuses[grading["status"]] = statuses.get(grading["status"], 0) + 1
    blocking = findings.blocking_count
    return serialize({
        "schema": ALTERNATES_SCHEMA,
        "tool_version": TOOL_VERSION,
        "status": "input_invalid" if blocking else "valid",
        "input": _input_block(prepared),
        "project": _project_block(prepared),
        "evaluation": _evaluation_block(prepared),
        "substitution_policy": prepared.demand["substitution"],
        "summary": {
            "candidates": len(gradings),
            "by_status": statuses,
            "never_a_bom_change": True,
        },
        "gradings": gradings,
        "findings": findings.sorted(),
        "limits": _limits(prepared, simulated=False),
        "not_checked": list(NOT_CHECKED),
    })


def build_explain_report(prepared, planned, line_ids=None):
    strategies = planned["strategies"]
    preferred_name = planned["preferred"]["strategy"] if planned["preferred"] \
        else strategies[0]["strategy"]
    preferred = next(plan for plan in strategies
                     if plan["strategy"] == preferred_name)
    selected = preferred["lines"]
    if line_ids:
        wanted = set(line_ids)
        selected = [line for line in selected if line["line_id"] in wanted]
        if not selected:
            from .errors import InputError
            raise InputError("unknown_line_id",
                             "指定的 line_id 不存在：%s"
                             % ", ".join(sorted(wanted)))
    explanations = []
    for line in selected:
        explanations.append({
            "line_id": line["line_id"],
            "mpn": line["mpn"],
            "assembly": line["assembly"],
            "demand_chain": {
                "qty_per_board": line["demand"]["qty_per_board"],
                "board_quantity": line["demand"]["board_quantity"],
                "assembled_qty": line["demand"]["assembled_qty"],
                "attrition": line["demand"]["attrition"],
                "target_qty": line["demand"]["target_qty"],
                "consigned_applied": line["demand"]["consigned_applied"],
                "purchase_need": line["demand"]["purchase_need"],
            },
            "order_policy": {
                "mode": prepared.policies["order_policy"],
                "formula": "0 if need<=0 else ceil(max(need,MOQ)/MPQ)*MPQ",
                "overbuy_policy": prepared.demand["overbuy"],
                "overbuy_qty": line["overbuy_qty"],
            },
            "offers_considered": line["trace"],
            "selected_orders": line["orders"],
            "eligible_offers": line["eligible_offers"],
            "identity_conflicts": line["identity_conflicts"],
            "channel_conclusions": line["channel_conclusions"],
            "lead_time": line["lead_time"],
            "known_cost": line["known_cost"],
            "status": line["status"],
            "blockers": line["blockers"],
            "unknown_reasons": line["unknown_reasons"],
            "alternates": line["alternates"],
        })
    return serialize({
        "schema": EXPLAIN_SCHEMA,
        "tool_version": TOOL_VERSION,
        "status": preferred["status"],
        "input": _input_block(prepared),
        "project": _project_block(prepared),
        "evaluation": _evaluation_block(prepared),
        "strategy": preferred_name,
        "explanations": explanations,
        "limits": _limits(
            prepared,
            simulated=any(order["simulated"] for line in selected
                          for order in line["orders"])),
        "not_checked": list(NOT_CHECKED),
    })


def render_markdown(report, procurement_csv_name=None):
    lines = []
    lines.append("# 采购/缺料/替代规划报告（离线，非订单）")
    lines.append("")
    lines.append("> **%s**" % WATERMARK)
    lines.append("")
    lines.append("- schema: `%s` / tool `%s`"
                 % (report.get("schema"), report.get("tool_version")))
    lines.append("- status: **%s**" % report.get("status"))
    evaluation = report.get("evaluation", {})
    lines.append("- 评估时刻（重放）：`%s`（source=%s）"
                 % (evaluation.get("as_of"),
                    evaluation.get("as_of_source")))
    lines.append("- 输入 SHA256: `%s`" % report.get("input", {}).get("sha256"))
    project = report.get("project", {})
    lines.append("- BOM revision: `%s`；板数量: %s；BOM 源哈希: `%s`"
                 % (project.get("bom_revision"),
                    project.get("board_quantity"),
                    project.get("bom_source_sha256_computed")))
    lines.append("")
    lines.append("## 策略比较")
    lines.append("")
    comparison = report.get("comparison", {})
    lines.append("| 策略 | status | 覆盖 | 部分未知 | 已知缺料 | 订单 | 缺料数量 | 未知费用 |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for strategy in report.get("strategies", []):
        counts = strategy.get("counts", {})
        lines.append("| %s | %s | %s | %s | %s | %s | %s | %s |"
                     % (strategy.get("label") or strategy.get("strategy"),
                        strategy.get("status"),
                        counts.get("covered", 0)
                        + counts.get("covered_with_unknowns", 0),
                        counts.get("partial_unknown", 0),
                        counts.get("uncovered_known", 0),
                        counts.get("orders", 0),
                        counts.get("shortage_qty", 0),
                        strategy.get("unknown_fee_count", 0)))
    lines.append("")
    if comparison.get("known_cost_ranking"):
        lines.append("已知成本排序（仅已知子集）：")
        for row in comparison["known_cost_ranking"]:
            lines.append("- %s: %s %s" % (row["strategy"],
                                          row["known_total"],
                                          row["currency"]))
    lines.append("- %s" % comparison.get("known_cost_ranking_reason"))
    lines.append("")
    plan = report.get("plan", {})
    lines.append("## 需求展开（selected strategy: `%s`）"
                 % report.get("preferred_strategy"))
    lines.append("")
    lines.append("| line | MPN | 装配 | 每板 | 板数 | 装配量 | 备损 | 自备抵扣 | 采购需求 | 已购 | 缺料 |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for line in plan.get("lines", []):
        demand = line.get("demand", {})
        lines.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |"
                     % (line.get("line_id"), line.get("mpn"),
                        line.get("assembly"), demand.get("qty_per_board"),
                        demand.get("board_quantity"),
                        demand.get("assembled_qty"),
                        demand.get("attrition", {}).get("spare_total"),
                        demand.get("consigned_applied"),
                        demand.get("purchase_need"),
                        line.get("ordered_qty"), line.get("shortage_qty")))
    lines.append("")
    lines.append("## 渠道与替代结论")
    lines.append("")
    for line in plan.get("lines", []):
        conclusions = line.get("channel_conclusions", {})
        lines.append("- `%s` %s：mall=%s；SMT=%s；手焊=%s；status=%s"
                     % (line.get("line_id"), line.get("mpn"),
                        conclusions.get("mall", {}).get("status"),
                        conclusions.get("smt", {}).get("status"),
                        conclusions.get("hand_solder", {}).get("status"),
                        line.get("status")))
        if line.get("shortage_qty"):
            lines.append("  - 缺料 %s；未知原因：%s"
                         % (line["shortage_qty"],
                            ", ".join(reason.get("code", "")
                                      for reason in line.get(
                                          "unknown_reasons", []))))
    lines.append("")
    lines.append("## 费用与未知项")
    lines.append("")
    lines.append("- 已知费用：")
    for fee in plan.get("fees", {}).get("known", []):
        lines.append("  - %s %s %s（%s）"
                     % (fee.get("kind"), fee.get("amount"),
                        fee.get("currency"), fee.get("fee_id")))
    if not plan.get("fees", {}).get("known"):
        lines.append("  - 无已声明费用")
    lines.append("- 未知费用（不按 0 计）：")
    for fee in plan.get("fees", {}).get("unknown", []):
        lines.append("  - %s %s：%s"
                     % (fee.get("kind"), fee.get("channel"),
                        fee.get("reason")))
    if not plan.get("fees", {}).get("unknown"):
        lines.append("  - 无")
    budget = plan.get("budget", {})
    lines.append("- 预算：%s（%s）" % (budget.get("status"),
                                      budget.get("note")))
    lines.append("")
    lines.append("## 阻塞与限制")
    lines.append("")
    for blocker in report.get("blockers", []):
        lines.append("- **%s** %s：%s"
                     % (blocker.get("code"), blocker.get("line_id") or "",
                        blocker.get("message")))
    if not report.get("blockers"):
        lines.append("- 无 known blocker；未知项见上。")
    for item in report.get("limits", {}).get("watermark", []):
        pass
    lines.append("- real_eda=NOT RUN；live_supply_query=NOT RUN；"
                 "不登录、不下单、不锁库存。")
    lines.append("")
    lines.append("## 未核对项")
    lines.append("")
    for item in report.get("not_checked", []):
        lines.append("- %s" % item)
    lines.append("")
    return "\n".join(lines)


def render_procurement_csv(report):
    buffer = io.StringIO(newline="")
    buffer.write("# not_order;not_live_quote;offline_plan;"
                 "real_eda=NOT_RUN;live_supply_query=NOT_RUN\n")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["line_id", "mpn", "manufacturer", "footprint", "channel",
                     "supplier", "product_id", "qty", "currency", "tax_basis",
                     "unit_price", "line_total", "offer_id", "snapshot_id",
                     "status", "note"])
    plan = report.get("plan", {})
    for line in plan.get("lines", []):
        for order in line.get("orders", []):
            writer.writerow([csv_safe_cell(value) for value in (
                line.get("line_id"), line.get("mpn"),
                line.get("manufacturer"), line.get("footprint"),
                order.get("channel"), order.get("supplier"),
                order.get("product_id"), order.get("qty"),
                order.get("currency"), order.get("tax_basis"),
                order.get("unit_price"), order.get("line_total"),
                order.get("offer_id"), order.get("snapshot_id"),
                line.get("status"),
                "NOT_ORDER; NOT_LIVE_QUOTE; snapshot evidence only",
            )])
    return buffer.getvalue()


def dumps_report(report, pretty=False):
    if pretty:
        return json.dumps(report, ensure_ascii=False, sort_keys=True,
                          indent=2) + "\n"
    return json.dumps(report, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))
