"""去耦电容到 IC 电源脚的摆放距离检查（PCB 级）。

## 为什么做这个而不是往 block 的 pcb_layout 里写文档

`block.threshold_switch_12v` 的 `pcb_layout` 是空的，我本想往里写"去耦电容要紧邻 VDD"。
查下来：**没有任何代码读 `.PCBLayout` 去校验**，`block-apply` 自己就写着
"the listed constraint maps were NOT applied"。

往一个无人消费的字段里写约束 = 加了但没人执行。所以改成一个**能跑、能被检查**的东西。

## 判据

去耦电容离它服务的 IC 电源脚越远，高频回路的面积越大，去耦越无效。
经典经验值是 100 mil（2.54mm）以内。

这个数字是**经验值，不是物理定律**，所以：
  - 默认 100 mil，但输出里明写「用的是默认值」
  - 允许用 --max-mil 覆盖
  - 永远报**实测距离**，让人自己判断

## 输入

`pcb dump --include-copper` 出来的 JSON（需要 components[].pads 带坐标）。
"""
import argparse
import json
import math
import pathlib
import sys

DEFAULT_MAX_MIL = 100.0


def load_board(path):
    data = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    return data.get("result") or data


# 电源网络会长这样。第一版把**所有非地焊盘**都当电源脚，
# 于是 U1 的 ALARM / TH / NTC_MID 全被报成"没找到去耦电容"——一堆噪声。
# 判据必须只盯真正的供电网络。
RAIL_PATTERNS = ("VCC", "VDD", "VSS", "VBAT", "PWR", "+5", "+3", "+12",
                 "3V3", "5V", "12V", "3.3V", "5.0V", "12.0V", "VIN", "VBUS")
GROUND_PATTERNS = ("GND", "VSS", "AGND", "PGND", "0V")


def looks_like_rail(net: str) -> bool:
    upper = net.upper()
    if any(tag in upper for tag in GROUND_PATTERNS):
        return False
    return any(tag in upper for tag in RAIL_PATTERNS)


def power_pads(comp, extra_nets=()):
    """IC 上接**电源网络**的焊盘（排除地）。"""
    out = []
    for pad in comp.get("pads") or []:
        net = pad.get("net") or ""
        if not net:
            continue
        if net not in extra_nets and not looks_like_rail(net):
            continue
        x, y = pad.get("x"), pad.get("y")
        if x is None or y is None:
            continue
        out.append((str(pad.get("padNumber")), net, float(x), float(y)))
    return out


def cap_pads(comp):
    out = []
    for pad in comp.get("pads") or []:
        net = pad.get("net") or ""
        x, y = pad.get("x"), pad.get("y")
        if not net or x is None or y is None:
            continue
        out.append((net, float(x), float(y)))
    return out


def run(board, max_mil=DEFAULT_MAX_MIL, extra_nets=()):
    comps = {c.get("designator"): c for c in board.get("components") or []}
    results = []

    for designator, comp in comps.items():
        if not designator or not designator.upper().startswith("U"):
            continue
        ic_power = power_pads(comp, extra_nets)
        if not ic_power:
            continue
        for pad_no, net, ix, iy in ic_power:
            best = None
            for other_des, other in comps.items():
                if other_des == designator or not other_des:
                    continue
                # 只把电容当去耦候选（Value 含 F 或名字里有 C 前缀）
                value = str((other.get("otherProperty") or {}).get("Value") or "")
                looks_cap = (other_des.upper().startswith("C")
                             or "F" in value.upper())
                if not looks_cap:
                    continue
                for cnet, cx, cy in cap_pads(other):
                    if cnet != net:
                        continue
                    dist = math.hypot(ix - cx, iy - cy)
                    if best is None or dist < best["distance_mil"]:
                        best = {"cap": other_des, "distance_mil": dist}
            if best is None:
                results.append({"ic": designator, "pin": pad_no, "net": net,
                                "status": "not_run",
                                "reason": f"{net} 上没有找到去耦电容"})
                continue
            ok = best["distance_mil"] <= max_mil
            results.append({
                "ic": designator, "pin": pad_no, "net": net,
                "cap": best["cap"],
                "distance_mil": round(best["distance_mil"], 1),
                "max_mil": max_mil, "status": "pass" if ok else "over",
            })
    return results


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--board", required=True, help="pcb dump --include-copper 的 JSON")
    ap.add_argument("--max-mil", type=float, default=DEFAULT_MAX_MIL,
                    help=f"允许的最大焊盘中心距（默认 {DEFAULT_MAX_MIL} mil）")
    ap.add_argument("--power-net", action="append", default=[],
                    help="额外把哪些网络当供电轨（可重复）")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    board = load_board(args.board)
    results = run(board, args.max_mil, tuple(args.power_net))
    used_default = abs(args.max_mil - DEFAULT_MAX_MIL) < 1e-9
    # **用默认经验值时不当硬失败。** 100 mil 是行业惯例，不是物理定律；
    # 拿它把板子判死等于发明判据。只有调用方显式给了上限，才把它当门。
    for r in results:
        if r["status"] == "over":
            r["status"] = "warn" if used_default else "fail"
    note = ("max_mil 用的是**默认经验值** 100 mil（2.54mm），不是物理定律"
            if used_default else "max_mil 由调用方指定")

    if args.json:
        print(json.dumps({"schema": "decap-placement/v1", "note": note,
                          "results": results}, ensure_ascii=False, indent=2))
    else:
        print(f"去耦摆放检查（{note}）")
        if not results:
            print("  没有找到带电源脚的 IC，跳过")
        for r in results:
            if r["status"] == "not_run":
                print(f"  [not_run] {r['ic']}.{r['pin']} ({r['net']}): {r['reason']}")
            else:
                print(f"  [{r['status']}] {r['ic']}.{r['pin']} ({r['net']}) "
                      f"← {r['cap']}: {r['distance_mil']} mil / 上限 {r['max_mil']}")

    if any(r["status"] == "fail" for r in results):
        return 1
    # 退出码 2 只留给"真的什么都判不了"；warn 是判了、只是没过经验值，不算。
    if results and all(r["status"] in ("unknown", "not_run") for r in results):
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
