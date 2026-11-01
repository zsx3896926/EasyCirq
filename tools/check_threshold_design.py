"""这块板的阈值设计对不对——纯计算，不需要实物。

2026-11-01 第一次算，**发现阈值设错了**：

  NTC 在 25°C 是 10k，R1 也是 10k  →  NTC_MID = 5 × 10k/(10k+10k) = 2.500 V
  TH 由 R2/R3 分压，两个都是 10k   →  TH     = 5 × 10k/(10k+10k) = 2.500 V

**两个值在 25°C 完全相等。** 温度只要高一点点，NTC 阻值下降、NTC_MID 低于 TH，
比较器就翻转——**这块板的动作温度是 25°C，不是 60°C**。

目标写的是"超温就响"，示例验收数据写的是"58℃ 响，55℃ 停"。
所以这是设计缺陷，不是设计意图。

而 18 项门禁、DRC、网表检查**都看不出这个**——它们验的是连接与结构，
不是"这个阻值选得对不对"。

用法：
    python tools/check_threshold_design.py
    python tools/check_threshold_design.py --suggest
"""
import argparse
import json
import math
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
SNAP = ROOT / "deliverables" / "alarm" / "design" / "snapshot" / "list.json"

VCC = 5.0
R_FIXED = 10_000.0
R_NTC_25 = 10_000.0
B_VALUES = (3435, 3950)
T_LOW = 25.0
T_TARGET = 60.0


def ntc_r(temp_c: float, b: float) -> float:
    t = temp_c + 273.15
    t25 = T_LOW + 273.15
    return R_NTC_25 * math.exp(b * (1.0 / t - 1.0 / t25))


def ntc_mid(temp_c: float, b: float) -> float:
    r = ntc_r(temp_c, b)
    return VCC * r / (R_FIXED + r)


def netlist():
    nets = {}
    if SNAP.is_file():
        payload = json.loads(SNAP.read_text(encoding="utf-8"))
        root = payload.get("result") or payload
        for comp in root.get("components") or []:
            for pin in comp.get("pins") or []:
                net = pin.get("net") or ""
                if net:
                    nets.setdefault(net, []).append(f"{comp.get('designator')}.{pin.get('pinNumber')}")
    return nets


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--suggest", action="store_true")
    args = parser.parse_args()

    nets = netlist()
    print("网表（判断分压结构的依据）：")
    for net in ("PWR5V", "GND", "NTC_MID", "TH", "ALARM", "BASE", "BUZ_SW"):
        print(f"  {net:9} {' '.join(sorted(nets.get(net, [])))}")
    print()

    th = VCC * R_FIXED / (R_FIXED + R_FIXED)
    print(f"当前：R2 = R3 = 10k  →  TH = {th:.3f} V")
    print()

    worst = None
    for b in B_VALUES:
        v25, v60 = ntc_mid(T_LOW, b), ntc_mid(T_TARGET, b)
        print(f"B = {b}")
        print(f"  25°C  NTC {ntc_r(T_LOW, b)/1000:6.2f}k  NTC_MID {v25:.3f} V")
        print(f"  60°C  NTC {ntc_r(T_TARGET, b)/1000:6.2f}k  NTC_MID {v60:.3f} V")
        # find where NTC_MID crosses TH
        lo, hi = 0.0, 100.0
        for _ in range(80):
            mid = (lo + hi) / 2
            if ntc_mid(mid, b) > th:
                lo = mid
            else:
                hi = mid
        print(f"  实际翻转温度 ≈ {lo:.1f}°C   （目标 {T_TARGET:.0f}°C）")
        ok = abs(lo - T_TARGET) <= 5
        print(f"  判定：{'OK' if ok else 'WRONG'}")
        print()
        if not ok:
            worst = (b, lo)

    if args.suggest:
        print("若要 60°C 翻转，TH 需要落在下面这个区间内：")
        for b in B_VALUES:
            v25, v60 = ntc_mid(T_LOW, b), ntc_mid(T_TARGET, b)
            print(f"  B = {b}:  {v60:.3f} V  <  TH  <  {v25:.3f} V")
        # pick a TH near the geometric middle of the range for B=3950
        v60, v25 = ntc_mid(T_TARGET, 3950), ntc_mid(T_LOW, 3950)
        want = (v60 + v25) / 2
        print()
        print(f"取 TH = {want:.2f} V（B=3950 时约 {T_TARGET:.0f}°C 附近的中间值）")
        # TH = 5 * R3/(R2+R3); keep R2 = 10k
        r3 = want * R_FIXED / (VCC - want)
        print(f"  保持 R2 = 10k，则 R3 ≈ {r3:.0f} Ω（最接近的 E24: 4.3k 或 4.7k）")
        for cand in (4300, 4700, 3300, 5100):
            th_c = VCC * cand / (R_FIXED + cand)
            lo, hi = 0.0, 100.0
            for _ in range(80):
                mid = (lo + hi) / 2
                if ntc_mid(mid, 3950) > th_c:
                    lo = mid
                else:
                    hi = mid
            print(f"  R3 = {cand/1000:.1f}k → TH = {th_c:.2f} V → 翻转 ≈ {lo:.1f}°C")

    return 1 if worst else 0


if __name__ == "__main__":
    raise SystemExit(main())
