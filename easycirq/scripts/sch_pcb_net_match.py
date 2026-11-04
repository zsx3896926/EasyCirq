#!/usr/bin/env python3
"""原理图 ↔ PCB 网表一致性：图上接了哪里，板上是不是也接了那里。

为什么需要
----------
原理图和 PCB 是两份独立的产物。改完原理图（比如把四个电源脚从 GND 改到 PWR5V、
加一颗三极管），如果 PCB 没有重新导入网表，**两张图会静静地各说各话**：

- 原理图检查（15/16 项 KPI）只看原理图，全部通过；
- PCB DRC 只看板内几何与连通，也可能全部通过；
- 而板上的铜箔连的是**旧网表**。

本案就是先改原理图、再 import-changes 才一致的。若跳过那一步，没有任何一项检查会响。

判据
----
对每个器件、每个引脚：原理图里的网络名 必须 等于 PCB 焊盘上的网络名。
  - 两侧都没有网络 -> 一致（都悬空）
  - 一侧有、一侧没有 -> 不一致
  - 名字不同 -> 不一致（注意方向：原理图 VCC、板上 GND 也算不一致）

未在 PCB 上出现的器件、未在原理图上出现的器件也要报出来——那说明两边根本不是
同一块板。

输入：`sch list --include-pins` 与 `pcb dump` 各一份 JSON。
退出码：0 一致，1 有差异，2 输入不可用。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

SCHEMA = "easycirq-netlist-pcb-match/v1"


def _components(payload) -> list[dict]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("components",):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    result = payload.get("result")
    if isinstance(result, dict):
        return _components(result)
    return []


def schematic_nets(payload) -> dict[tuple[str, str], str]:
    """(designator, pin) -> net, from a sch list --include-pins read."""
    nets: dict[tuple[str, str], str] = {}
    for component in _components(payload):
        ref = str(component.get("designator") or "").strip()
        if not ref:
            # Graphics, text and other non-part primitives carry no designator.
            # Counting them as "a part missing on the board" is a false positive.
            continue
        for pin in component.get("pins") or []:
            if not isinstance(pin, dict):
                continue
            number = pin.get("pinNumber")
            if number is None:
                number = pin.get("number")
            if number is None:
                continue
            nets[(ref, str(number).strip())] = str(pin.get("net") or "").strip()
    return nets


def pcb_nets(payload) -> dict[tuple[str, str], str]:
    """(designator, pad) -> net, from a pcb dump read.

    Pad numbers may be absent; when they are, fall back to the pad's index so the
    comparison still lines up per designator instead of silently dropping pads.
    """
    nets: dict[tuple[str, str], str] = {}
    for component in _components(payload):
        ref = str(component.get("designator") or "").strip()
        if not ref:
            continue
        pads = component.get("pads") or []
        for index, pad in enumerate(pads):
            if not isinstance(pad, dict):
                continue
            number = pad.get("padNumber")
            if number in (None, ""):
                number = pad.get("number")
            if number in (None, ""):
                number = str(index)
            nets[(ref, str(number).strip())] = str(pad.get("net") or "").strip()
    return nets


def compare(sch: dict, board: dict) -> dict:
    findings: list[dict] = []

    sch_refs = {ref for ref, _ in sch}
    board_refs = {ref for ref, _ in board}
    for ref in sorted(sch_refs - board_refs):
        findings.append({
            "code": "PART_MISSING_ON_BOARD",
            "severity": "blocking",
            "message": f"{ref} 在原理图里有，板上没有",
            "where": ref,
        })
    for ref in sorted(board_refs - sch_refs):
        findings.append({
            "code": "PART_MISSING_IN_SCHEMATIC",
            "severity": "blocking",
            "message": f"{ref} 在板上，原理图里没有",
            "where": ref,
        })

    # Compare per designator, so pin-number vs pad-number mismatches do not turn
    # every pin into a false difference on symbols that do not expose pad numbers.
    for ref in sorted(sch_refs & board_refs):
        sch_pins = {pin: net for (r, pin), net in sch.items() if r == ref}
        board_pads = {pad: net for (r, pad), net in board.items() if r == ref}
        if len(sch_pins) != len(board_pads):
            findings.append({
                "code": "PIN_COUNT_MISMATCH",
                "severity": "blocking",
                "message": f"{ref}：原理图 {len(sch_pins)} 个引脚，板上 {len(board_pads)} 个焊盘",
                "where": ref,
            })
            continue
        if set(sch_pins) != set(board_pads):
            # Numbers differ (e.g. pads unnamed) - fall back to comparing the
            # multiset of nets, which still catches a stale netlist.
            if sorted(sch_pins.values()) != sorted(board_pads.values()):
                findings.append({
                    "code": "NET_SET_MISMATCH",
                    "severity": "blocking",
                    "message": f"{ref}：两侧引脚编号不同，且网络集合也不同"
                               f"（图 {sorted(sch_pins.values())} / 板 {sorted(board_pads.values())}）",
                    "where": ref,
                })
            continue
        for pin in sorted(sch_pins):
            if sch_pins[pin] != board_pads[pin]:
                findings.append({
                    "code": "PIN_NET_MISMATCH",
                    "severity": "blocking",
                    "message": f"{ref}.{pin}：原理图 {sch_pins[pin] or '(悬空)'} ≠ 板上 {board_pads[pin] or '(悬空)'}",
                    "where": f"{ref}.{pin}",
                })

    status = "fail" if findings else "pass"
    return {
        "schema": SCHEMA,
        "status": status,
        "verdict": "review" if status == "fail" else "pass",
        "metrics": {"schematic_pcb_diff": len(findings)},
        "partsOnSchematic": len(sch_refs),
        "partsOnBoard": len(board_refs),
        "findings": findings,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--schematic", required=True, help="sch list --include-pins output")
    ap.add_argument("--pcb", required=True, help="pcb dump output")
    ap.add_argument("--out")
    args = ap.parse_args(argv)

    reads = {}
    for label, path in (("schematic", args.schematic), ("pcb", args.pcb)):
        target = Path(path)
        if not target.is_file():
            print(json.dumps({"schema": SCHEMA, "status": "unavailable",
                              "reason": f"no {label} read at {target}"}, ensure_ascii=False))
            return 2
        try:
            reads[label] = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print(json.dumps({"schema": SCHEMA, "status": "unavailable",
                              "reason": f"{label}: {exc}"}, ensure_ascii=False))
            return 2

    result = compare(schematic_nets(reads["schematic"]), pcb_nets(reads["pcb"]))
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
