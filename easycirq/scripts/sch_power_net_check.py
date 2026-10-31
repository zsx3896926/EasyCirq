#!/usr/bin/env python3
"""电源网络检查：声明的电源引脚是否真的接在一个电源网络上。

为什么需要这一项
----------------
2026-10-31 的一块板通过了全部 15 项 KPI（必查 11/11、可以下单），但它的
U1.8、R1.1、R2.1、C1.1 全都接在 **GND** —— 整块板没有电源，任何情况下都不工作。

15 项检查的都是"结构完整性"：
  - unconnected  每个脚都有网络            -> 通过
  - erc          没有未连接/输出冲突        -> 通过
  - decoupling   电容存在且两脚都有网络     -> 通过
  - netlist_diff 网表与图纸一致             -> 通过（图纸本身错）

**没有任何一项问过："这块板有电源吗？"**

本脚本只做这一件事。判据全部可从快照读出，不需要新数据源：

1. 找出 pinName 属于电源类（VCC/VDD/V+/VBUS/VIN/VBAT…）的引脚；
2. 若一个都没有 -> `n/a`（纯无源网络可能确实没有，不算问题）；
3. 若有 -> 它们必须满足：
   a. 每个都落在某个网络上（不能悬空）；
   b. 全部落在**同一个**网络上（不能一半接电源一半接地）；
   c. 该网络**不是地网络**（GND/AGND/PGND/EARTH…）；
   d. 该网络上至少有 2 个引脚（电源要分配出去，独脚电源没意义）。

退出码：0 = 通过，1 = 有问题，2 = 输入不可用。
输出：一个 JSON 对象。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

SCHEMA = "easycirq-power-net-check/v1"

POWER_PIN = re.compile(
    r"^(VCC|VDD|V\+|VBUS|VIN|VBAT|VEE|AVCC|AVDD|DVCC|DVDD|VSP|VSN|VM)$",
    re.IGNORECASE,
)
GROUND_NET = re.compile(r"^(GND|AGND|DGND|PGND|EARTH|VSS|0V)$", re.IGNORECASE)


def load_pins(path: Path) -> list[dict]:
    """Pull (designator, pinNumber, pinName, net) rows out of a sch list read."""
    data = json.loads(path.read_text(encoding="utf-8"))
    components = data.get("components")
    if not isinstance(components, list):
        result = data.get("result")
        components = (result or {}).get("components") if isinstance(result, dict) else None
    rows: list[dict] = []
    for component in components or []:
        if not isinstance(component, dict):
            continue
        ref = component.get("designator")
        pins = component.get("pins")
        if not isinstance(pins, list):
            continue
        for pin in pins:
            if not isinstance(pin, dict):
                continue
            rows.append({
                "ref": str(ref),
                "pin": str(pin.get("pinNumber") or pin.get("number") or ""),
                "name": str(pin.get("pinName") or pin.get("name") or ""),
                "net": str(pin.get("net") or ""),
            })
    return rows


def analyze(rows: list[dict], declared: list[str] | None = None) -> dict:
    declared = declared or []
    findings: list[dict] = []
    present_nets = {row["net"] for row in rows if row["net"]}

    # A declared supply net is a promise the board has to keep. This branch does
    # not depend on pin NAMES at all, so it works for symbols with generic pins -
    # the blind spot that made KPI 16 answer n/a on a board with no supply.
    if declared:
        for net in declared:
            if net not in present_nets:
                findings.append({
                    "code": "POWER_NET_DECLARED_MISSING",
                    "severity": "blocking",
                    "message": f"计划声明了电源网络 {net}，但图上不存在这个网络",
                    "where": f"plan.power_nets[{net}]",
                })
                continue
            members = [row for row in rows if row["net"] == net]
            if len(members) < 2:
                findings.append({
                    "code": "POWER_NET_UNDISTRIBUTED",
                    "severity": "warning",
                    "message": f"电源网络 {net} 只有 {len(members)} 个引脚，没有分配到任何地方",
                    "where": f"plan.power_nets[{net}]",
                })
        for net in declared:
            if GROUND_NET.match(net.strip()):
                findings.append({
                    "code": "POWER_ON_GROUND",
                    "severity": "blocking",
                    "message": f"计划把地网络 {net} 声明成了电源网络",
                    "where": f"plan.power_nets[{net}]",
                })
        status = "fail" if any(f["severity"] == "blocking" for f in findings) else "pass"
        return {
            "schema": SCHEMA,
            "status": status,
            "verdict": "review" if status == "fail" else "pass",
            "metrics": {"power_net_conflicts":
                        sum(1 for f in findings if f["severity"] == "blocking")},
            "source": "declared",
            "declaredNets": declared,
            "powerPins": [f"{r['ref']}.{r['pin']}({r['name']})->{r['net'] or '(floating)'}"
                          for r in rows if r["net"] in declared],
            "nets": sorted(declared),
            "findings": findings,
        }

    power_pins = [row for row in rows if POWER_PIN.match(row["name"].strip())]
    if not power_pins:
        return {
            "schema": SCHEMA,
            "status": "n/a",
            "reason": ("图里没有电源类引脚（纯无源或未标注），这一项不适用；"
                       "若要验证具体电源网络，请在计划的 power_nets 里声明"),
            "source": "pin-name",
            "powerPins": [],
            "nets": [],
            "findings": [],
        }

    nets = sorted({row["net"] for row in power_pins if row["net"]})
    floating = [row for row in power_pins if not row["net"]]
    for row in floating:
        findings.append({
            "code": "POWER_PIN_FLOATING",
            "severity": "blocking",
            "message": f"{row['ref']}.{row['pin']}({row['name']}) 没有接到任何网络",
            "where": f"{row['ref']}.{row['pin']}",
        })

    if len(nets) > 1:
        detail = "、".join(
            f"{net}({','.join(r['ref'] + '.' + r['pin'] for r in power_pins if r['net'] == net)})"
            for net in nets
        )
        findings.append({
            "code": "POWER_SPLIT",
            "severity": "blocking",
            "message": f"电源引脚被分到了 {len(nets)} 个不同网络：{detail}",
            "where": "pins[].net",
        })

    ground_nets = [net for net in nets if GROUND_NET.match(net.strip())]
    for net in ground_nets:
        pins = [f"{r['ref']}.{r['pin']}({r['name']})" for r in power_pins if r["net"] == net]
        findings.append({
            "code": "POWER_ON_GROUND",
            "severity": "blocking",
            "message": f"电源引脚接在了地网络 {net} 上：{'、'.join(pins)} —— 这块板没有电源",
            "where": "pins[].net",
        })

    if len(nets) == 1 and not ground_nets:
        net = nets[0]
        members = [r for r in rows if r["net"] == net]
        if len(members) < 2:
            findings.append({
                "code": "POWER_NET_UNDISTRIBUTED",
                "severity": "warning",
                "message": f"电源网络 {net} 只有 1 个引脚，没有分配到任何地方",
                "where": "pins[].net",
            })

    status = "fail" if any(f["severity"] == "blocking" for f in findings) else "pass"
    return {
        "schema": SCHEMA,
        "status": status,
        "verdict": "review" if status == "fail" else "pass",
        "metrics": {"power_net_conflicts": sum(1 for f in findings if f["severity"] == "blocking")},
        "source": "pin-name",
        "powerPins": [f"{r['ref']}.{r['pin']}({r['name']})->{r['net'] or '(floating)'}" for r in power_pins],
        "nets": nets,
        "findings": findings,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--list", required=True, help="sch list --include-pins output")
    ap.add_argument("--plan", default="",
                    help="pin-plan/v1 JSON that may declare power_nets; "
                         "declaring them beats guessing from pin names")
    ap.add_argument("--out")
    args = ap.parse_args(argv)

    path = Path(args.list)
    if not path.is_file():
        print(json.dumps({"schema": SCHEMA, "status": "unavailable",
                          "reason": f"no list read at {path}"}, ensure_ascii=False))
        return 2
    try:
        rows = load_pins(path)
    except (OSError, ValueError) as exc:
        print(json.dumps({"schema": SCHEMA, "status": "unavailable",
                          "reason": str(exc)}, ensure_ascii=False))
        return 2

    declared = []
    if args.plan:
        try:
            plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print(json.dumps({"schema": SCHEMA, "status": "unavailable",
                              "reason": f"plan unreadable: {exc}"}, ensure_ascii=False))
            return 2
        raw = plan.get("power_nets")
        if isinstance(raw, list):
            declared = [str(item).strip() for item in raw if str(item).strip()]

    result = analyze(rows, declared)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if result["status"] in ("pass", "n/a") else 1


if __name__ == "__main__":
    sys.exit(main())
