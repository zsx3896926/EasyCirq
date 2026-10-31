#!/usr/bin/env python3
"""The one page a customer reads: can this board be ordered, and what is left?

Answer in three lines, then the detail:

    ❌ 还不能打样
    还差 1 个必须修的问题
    下一步：把它连到该连的地方，或显式标成不接

It reads a KPI report (and optionally a gate token) and never re-measures
anything. "可以打样" is only claimed when the report says PASS and, if a gate
path was given, the token is live -- otherwise the card says what is missing.

Exit codes: 0 ready, 1 not ready, 2 invalid input.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

SCHEMA = "easycirq-sch-delivery-card/v1"

PLAIN = {
    "unconnected": "有引脚或网络没有接上",
    "cross_zone": "有一根线跨过了不该跨的区域",
    "overlaps": "图上有东西叠在一起",
    "net_text": "图上有一行字没有归属",
    "bus": "总线或差分对少了一根",
    "wire_length": "有一根线太长，读图困难",
    "readability": "整页几乎全靠标签连接（提醒项）",
    "zone_balance": "各分区里的器件数量不均",
    "erc": "电气规则有冲突",
    "pin_mux": "引脚复用冲突",
    "decoupling": "电源脚没有配电容",
    "naming": "网络名重复或还是默认名",
    "bom_map": "元件缺封装、型号或立创编号",
    "netlist_diff": "改动前后连接对不上",
    "readback": "保存重开后和保存前对不上",
}

ADVICE = {
    "unconnected": "把它连到该连的地方，或显式标成不接（NC）",
    "cross_zone": "在两端改用网络标签，不要拉长线跨区",
    "overlaps": "挪开叠在一起的器件或文字",
    "net_text": "给这行字找回归属，或删掉它",
    "bus": "补齐总线/差分对缺的那一根",
    "wire_length": "拆成短线 + 标签",
    "readability": "局部电路尽量用导线直接连",
    "zone_balance": "把器件在各分区之间挪匀",
    "erc": "按 DRC 提示逐条改（输出冲突/多驱动等）",
    "pin_mux": "换一个引脚，或声明该复用是有意的",
    "decoupling": "给电源脚补一颗去耦电容",
    "naming": "改成有意义的名字",
    "bom_map": "补上封装/型号/立创编号",
    "netlist_diff": "确认这次改动是不是真的等价",
    "readback": "保存、重开、回读，确认对象都还在",
}


def _load(path):
    with open(path, "rb") as stream:
        raw = stream.read(8_000_001)
    if len(raw) >= 8_000_000:
        raise ValueError(f"{path}: input too large")
    return json.loads(raw.decode("utf-8-sig"))


def _gate_live(path):
    if not path or not Path(path).is_file():
        return False, "没有通行证"
    try:
        token = _load(path)
    except (OSError, ValueError):
        return False, "通行证读不出来"
    if str(token.get("verdict", "")).upper() != "PASS" or not token.get("apply_allowed"):
        return False, "通行证不是 PASS"
    expires = token.get("expires_at")
    if expires:
        try:
            when = datetime.strptime(expires, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) > when:
                return False, f"通行证已过期（{expires}）"
        except ValueError:
            pass
    return True, "通行证有效"


def analyze(report, gate_path=None, pcb=None):
    kpis = report.get("kpis") or []
    counts = {"pass": 0, "fail": 0, "missing": 0, "na": 0, "advisory": 0}
    for row in kpis:
        if row.get("advisory"):
            counts["advisory"] += 1
            continue
        status = row.get("status")
        if status in counts:
            counts[status] += 1

    verdict = str(report.get("verdict", "")).upper()
    status_of = {str(r.get("id")): r.get("status") for r in kpis}
    blockers, missing = [], []
    for item in report.get("blockers") or []:
        kpi = str(item.get("kpi"))
        entry = {"kpi": kpi, "plain": PLAIN.get(kpi, kpi),
                 "advice": ADVICE.get(kpi, "按检查结果修正"),
                 "reason": item.get("reason")}
        if status_of.get(kpi) in ("missing", "unknown"):
            missing.append(entry)
        else:
            blockers.append(entry)

    gate_ok, gate_detail = (True, "") if gate_path is None else _gate_live(gate_path)

    unmeasured = sum(1 for k in kpis
                     if not k.get("advisory")
                     and k.get("status") in ("missing", "unknown"))
    if verdict == "PASS" and unmeasured:
        state, headline = "incomplete", "⏳ 还不能判断：有些检查还没做"
        next_step = "补齐下面这些检查需要的资料，再跑一轮"
    elif verdict == "PASS" and gate_ok:
        # The KPI report only covers the schematic. Say so unless the caller
        # also supplied the PCB half, otherwise the card reads as a whole-board
        # verdict it cannot support.
        if pcb is None:
            state, headline = "ready", "✅ 原理图可以打样（PCB 未检查）"
            next_step = "原理图这一关过了；带上 PCB 检查结果才是整板结论"
        elif pcb.get("passed") and int(pcb.get("violations") or 0) == 0:
            state, headline = "ready", "✅ 可以下单（原理图与 PCB 都通过）"
            next_step = "导出制造文件；打样回来后做验收"
        else:
            reason = pcb.get("reason") or ""
            state, headline = "blocked", "❌ PCB 还没过检查，不能下单"
            next_step = ("按 PCB 检查报告逐条修（间距 / 连通），修完重新检查"
                         + (f"；首要问题：{reason}" if reason else ""))
    elif verdict == "PASS" and not gate_ok:
        state, headline = "gate_stale", "⚠️ 检查通过，但需要重新确认"
        next_step = f"{gate_detail}；重新跑一次检查即可"
    elif verdict == "REVIEW":
        state, headline = "review", "⚠️ 可以打样，但有需要留意的项"
        next_step = "确认下面这些提醒可接受，再导出制造文件"
    elif blockers:
        state, headline = "blocked", "❌ 还不能打样"
        next_step = "按下面的建议逐条修，修完重新测量"
    else:
        state, headline = "incomplete", "⏳ 还不能判断：有些检查还没做"
        next_step = "补齐下面这些检查需要的资料，再跑一轮"

    return {
        "schema": SCHEMA,
        "state": state,
        "headline": headline,
        "next": next_step,
        "counts": counts,
        "blockers": blockers,
        "missing": missing,
        "pcb": pcb,
        "project": report.get("project"),
        "page": report.get("page"),
    }


def render(card):
    lines = [card["headline"], ""]
    pcb = card.get("pcb")
    if pcb is not None:
        if pcb.get("passed") and int(pcb.get("violations") or 0) == 0:
            lines += ["PCB 检查：通过（0 项）", ""]
        else:
            reason = pcb.get("reason") or ""
            lines += [("PCB 检查：未通过" + (" · " + reason if reason else "")), ""]
    c = card["counts"]
    if card["blockers"]:
        lines.append("必须修的问题：")
        for item in card["blockers"]:
            lines.append(f"  · {item['plain']}")
            lines.append(f"    → {item['advice']}")
        lines.append("")
    if card.get("missing"):
        lines.append("还没检查的项目（补上资料即可）：")
        for item in card["missing"]:
            lines.append(f"  · {item['plain']}")
        lines.append("")
    lines.append(
        f"检查结果：必查 {c['pass']}/{c['pass'] + c['fail'] + c['missing']} 通过"
        f" · 缺证据 {c['missing']} · 不适用 {c['na']} · 提醒 {c['advisory']}")
    lines.append(f"下一步：{card['next']}")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Customer delivery card: can it be ordered?")
    ap.add_argument("--kpi-report", required=True)
    ap.add_argument("--pcb-drc", default="",
                    help="pcb drc --json output; without it the card only covers the schematic")
    ap.add_argument("--gate", help="gate token path (omit to ignore the gate)")
    ap.add_argument("--json", action="store_true", help="print JSON")
    args = ap.parse_args(argv)

    try:
        report = _load(args.kpi_report)
    except (OSError, ValueError) as exc:
        print(f"sch_delivery_card: {exc}", file=sys.stderr)
        return 2
    pcb = None
    if args.pcb_drc:
        try:
            raw = json.loads(Path(args.pcb_drc).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print(f"PCB 检查结果读不出来：{exc}", file=sys.stderr)
            return 2
        violations = raw.get("violations") or []
        passed = raw.get("passed")
        pcb = {
            "checked": True,
            "passed": bool(passed) if passed is not None else not violations,
            "violations": len(violations),
            "reason": (violations[0].get("message") if violations else ""),
        }
    card = analyze(report, args.gate, pcb)
    print(json.dumps(card, ensure_ascii=False, indent=2)
          if args.json else render(card))
    return 0 if card["state"] == "ready" else 1


if __name__ == "__main__":
    sys.exit(main())
