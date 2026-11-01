#!/usr/bin/env python3
"""One question, one answer: where is this board, and what is the next step?

This is the customer-facing state machine. It reads the artefacts the other
tools already produce (a KPI report, a gate token, an optional reopen diff) and
prints one state plus one next action. It never calls EDA and never invents a
state: an input that is missing simply means the state was not reached.

States, in order:
  not_measured   no KPI report for this page
  blocked        KPI report says BLOCKED (fix the listed items first)
  review         KPI report says REVIEW (soft limits not met)
  ready_to_write KPI PASS and a live gate token exists
  gate_stale     KPI PASS but the token is missing/expired/foreign
  guard_missing  (informational) KPI PASS but no token path was given

Exit codes: 0 ready_to_write, 1 blocked/review, 2 not_measured or invalid.
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

SCHEMA = "easycirq-sch-status/v1"

# plain-language labels: the customer should never meet a KPI id
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


def _load(path):
    with open(path, "rb") as stream:
        raw = stream.read(8_000_001)
    if len(raw) >= 8_000_000:
        raise ValueError(f"{path}: input too large")
    return json.loads(raw.decode("utf-8-sig"))


def _gate_state(path):
    """(state, detail) for the gate token: live | stale | missing."""
    if not path:
        return "missing", "没有指定检查结果的路径"
    p = Path(path)
    if not p.is_file():
        return "missing", "还没确认可以写入"
    try:
        token = _load(p)
    except (OSError, ValueError) as exc:
        return "stale", f"读取上次的检查结果失败：{exc}"
    if not str(token.get("verdict", "")).upper() == "PASS" or not token.get("apply_allowed"):
        return "stale", "上次的检查结果不是 PASS"
    expires = token.get("expires_at")
    if expires:
        try:
            when = datetime.strptime(expires, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) > when:
                return "stale", f"上次的检查结果过期了（{expires}）"
        except ValueError:
            pass
    return "live", f"上次的检查结果有效到 {expires}"


def analyze(report=None, gate_path=None):
    if report is None:
        return {
            "schema": SCHEMA,
            "state": "not_measured",
            "headline": "这块板还没有做过离线检查",
            "next": "把你想做的板子说给 AI 听就行；画完并检查过之后，这里会告诉你还差什么",
            "blockers": [],
            "missing": [],
        }
    verdict = str(report.get("verdict", "")).upper()
    status_of = {str(r.get("id")): r.get("status") for r in report.get("kpis") or []}
    blockers, missing = [], []
    for item in report.get("blockers") or []:
        kpi = str(item.get("kpi"))
        entry = {"kpi": kpi, "plain": PLAIN.get(kpi, kpi), "reason": item.get("reason")}
        # "not measured yet" is not a defect: a customer who never supplied a
        # pin plan has not broken anything
        if status_of.get(kpi) in ("missing", "unknown"):
            missing.append(entry)
        else:
            blockers.append(entry)

    unmeasured = sum(1 for k in report.get("kpis") or []
                     if not k.get("advisory")
                     and k.get("status") in ("missing", "unknown"))
    apply_allowed = bool((report.get("stability") or {}).get("apply_allowed"))

    if verdict == "PASS" and unmeasured:
        state, headline = "incomplete", "还不能判断：有些检查还没做"
        nxt = "补齐下面这些检查需要的资料，再跑一轮"
    elif verdict == "PASS" and not apply_allowed:
        state, headline = "gate_stale", "检查通过，还差一轮确认"
        nxt = "连续两轮通过后才会获得许可；再跑一轮即可"
    elif verdict == "BLOCKED" and blockers:
        state, headline = "blocked", "暂时不能写入：还有必须修掉的问题"
        nxt = "按下面的清单逐条修，修完重新测量；修完之前不要画图"
    elif verdict == "BLOCKED":
        state, headline = "incomplete", "还不能判断：有些检查还没做"
        nxt = "补齐下面这些检查需要的输入，再跑一轮"
    elif verdict == "REVIEW":
        state, headline = "review", "可以写入，但有几项软指标没达标"
        nxt = "确认这些提醒项可接受后继续；否则先调整再测"
    else:
        gate_state, gate_detail = _gate_state(gate_path)
        if gate_state == "live":
            state, headline = "ready_to_write", "检查通过，可以写入图纸了"
            nxt = "执行写入；写完保存、关掉重开，确认东西都还在，再跑一次检查"
        else:
            state = "gate_stale"
            headline = "检查通过了，但上次的结果过期了"
            nxt = f"{gate_detail}；重新跑一轮检查即可重新签发"
    return {
        "schema": SCHEMA,
        "state": state,
        "headline": headline,
        "next": nxt,
        "verdict": verdict,
        "blockers": blockers,
        "missing": missing,
        "project": report.get("project"),
        "page": report.get("page"),
    }


def render(status):
    lines = [f"【{status['headline']}】"]
    if status.get("project"):
        lines.append(f"工程 {status['project']} / {status['page']}")
    if status["blockers"]:
        lines.append("必须修的问题：")
        for item in status["blockers"]:
            lines.append(f"  - {item['plain']}")
            if item.get("reason"):
                lines.append(f"    {item['reason']}")
    if status.get("missing"):
        lines.append("还没检查的项目（补上输入即可）：")
        for item in status["missing"]:
            lines.append(f"  - {item['plain']}")
    lines.append(f"下一步：{status['next']}")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="One-line board status and next step")
    ap.add_argument("--kpi-report", help="kpi-report.json from the offline pipeline")
    ap.add_argument("--gate", help="gate token path (default .easycirq/gate.json)")
    ap.add_argument("--json", action="store_true", help="print JSON")
    args = ap.parse_args(argv)

    report = None
    if args.kpi_report:
        try:
            report = _load(args.kpi_report)
        except (OSError, ValueError) as exc:
            print(f"sch_status: {exc}", file=sys.stderr)
            return 2
    gate = args.gate if args.gate is not None else ".easycirq/gate.json"
    status = analyze(report, gate)
    print(json.dumps(status, ensure_ascii=False, indent=2)
          if args.json else render(status))
    return {"ready_to_write": 0, "review": 1, "blocked": 1}.get(status["state"], 2)


if __name__ == "__main__":
    sys.exit(main())
