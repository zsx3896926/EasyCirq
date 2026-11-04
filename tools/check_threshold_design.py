"""这块板的阈值到底设得对不对——从图纸读真实阻值，纯计算，不需要实物。

2026-11-01 第一版发现阈值设错（R2 = R3 = 10k → TH = 2.500V = 25°C 时的 NTC_MID，
于是动作温度是 25°C 而不是 60°C）。R3 已改为 2.4k，本脚本现在从**图纸**读值再算，
不写死任何阻值——否则改完板再跑一次，脚本还会用旧数字骗人。

用法：
    python tools/check_threshold_design.py
    python tools/check_threshold_design.py --suggest
退出码：0 = 动作温度在目标 ±5°C 内；1 = 不在；3 = 读不到图纸。
"""
import argparse
import json
import math
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
PAGE = "9d9dd9e46f53880e"
PROJECT = "KPI-S5-Verify"

VCC = 5.0
T_LOW = 25.0
T_TARGET = 60.0
B_VALUES = (3435, 3950)


def read_schematic():
    proc = subprocess.run(["easycirq", "--project", PROJECT, "sch", "list",
                           "--page", PAGE, "--include-pins"],
                          cwd=str(ROOT), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    raw = proc.stdout
    start = raw.find("{")
    if start < 0:
        print("读不到图纸：" + (proc.stderr or raw)[:300])
        raise SystemExit(3)
    data = json.loads(raw[start:])
    return data.get("result") or data


def parse_ohms(text):
    """'10kΩ' / '2.4kΩ' / '4.7R' -> float ohms."""
    if not text:
        return None
    match = re.search(r"([\d.]+)\s*([kKmMrR]?)", str(text))
    if not match:
        return None
    value = float(match.group(1))
    unit = match.group(2).lower()
    if unit == "k":
        return value * 1000.0
    if unit == "m":
        return value * 1_000_000.0
    return value


def resistances(root):
    found = {}
    for comp in root.get("components") or []:
        if comp.get("componentType") != "part":
            continue
        props = comp.get("otherProperty") or {}
        ohms = parse_ohms(props.get("Value"))
        if ohms:
            found[comp.get("designator")] = ohms
    return found


def net_members(root):
    nets = {}
    for comp in root.get("components") or []:
        for pin in comp.get("pins") or []:
            net = pin.get("net") or ""
            if net:
                nets.setdefault(net, []).append(comp.get("designator"))
    return nets


def ntc_r(temp_c, b):
    return 10_000.0 * math.exp(b * (1.0 / (temp_c + 273.15) - 1.0 / (T_LOW + 273.15)))


def ntc_mid(temp_c, b, r_pull):
    r = ntc_r(temp_c, b)
    return VCC * r / (r_pull + r)


def trip_point(th, b, r_pull):
    lo, hi = 0.0, 120.0
    for _ in range(90):
        mid = (lo + hi) / 2
        if ntc_mid(mid, b, r_pull) > th:
            lo = mid
        else:
            hi = mid
    return lo


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--suggest", action="store_true")
    args = parser.parse_args()

    root = read_schematic()
    ohms = resistances(root)
    nets = net_members(root)

    print("图纸里的阻值：", {k: f"{v/1000:g}k" for k, v in sorted(ohms.items())})
    print("TH 网络成员：", sorted(set(nets.get("TH", []))))
    print("NTC_MID 网络成员：", sorted(set(nets.get("NTC_MID", []))))
    print()

    # 分压结构：TH = VCC * R3 / (R2 + R3)，NTC_MID = VCC * NTC / (R1 + NTC)
    th_members = sorted(set(nets.get("TH", [])))
    mid_members = sorted(set(nets.get("NTC_MID", [])))
    r_top = next((ohms[d] for d in th_members if d in ohms), None)
    others = [d for d in th_members if d in ohms and ohms[d] != r_top]
    r_bot = others[0] if others else None

    if r_top is None or r_bot is None:
        print("算不出：TH 分压电阻读不全")
        raise SystemExit(3)

    # 判断哪颗接 GND：R2 -> PWR5V，R3 -> GND
    gnd = set(nets.get("GND", []))
    pwr = set(nets.get("PWR5V", []))
    r_pull = next((ohms[d] for d in mid_members if d in pwr), None)
    if r_pull is None:
        print("算不出：NTC_MID 的上拉电阻读不全")
        raise SystemExit(3)

    if any(d in gnd for d in th_members) and others:
        r_lo = next(ohms[d] for d in th_members if d in gnd and d in ohms)
        r_hi = next((ohms[d] for d in th_members if d in pwr and d in ohms), r_top)
    else:
        r_hi, r_lo = r_top, r_bot

    th = VCC * r_lo / (r_hi + r_lo)
    print(f"上拉 R1 = {r_pull/1000:g}k（NTC_MID 到 5V）")
    print(f"阈值分压：上 {r_hi/1000:g}k / 下 {r_lo/1000:g}k  →  TH = {th:.3f} V")
    print()

    bad = []
    for b in B_VALUES:
        v25, v60 = ntc_mid(T_LOW, b, r_pull), ntc_mid(T_TARGET, b, r_pull)
        actual = trip_point(th, b, r_pull)
        ok = abs(actual - T_TARGET) <= 5
        print(f"B = {b}")
        print(f"  25°C NTC_MID {v25:.3f} V   60°C NTC_MID {v60:.3f} V")
        print(f"  实际翻转 ≈ {actual:.1f}°C   目标 {T_TARGET:.0f}±5°C   "
              f"{'OK' if ok else 'WRONG'}")
        print()
        if not ok:
            bad.append((b, actual))

    if args.suggest:
        print("若要保持 R2 不变、只改 R3，则：")
        for cand in (1800, 2200, 2400, 2700, 3000, 3300):
            th_c = VCC * cand / (r_hi + cand)
            print(f"  R3 = {cand/1000:.1f}k → TH = {th_c:.3f} V → 翻转 ≈ "
                  f"{trip_point(th_c, 3950, r_pull):.1f}°C")

    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
