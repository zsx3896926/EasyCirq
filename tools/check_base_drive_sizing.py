"""验证「加基极上拉」的正确取值——只加 R5 是不够的。

背景（2026-11-01）：
  BASE = {R4.1, Q1.1}，R4.2 -> ALARM = U1.1（LM393 开集输出）
  没有上拉时 Q1 永远截止，蜂鸣器不响。

但**只加一颗 R5 从 BASE 到 5V，而 R4 仍是 10k** 会走到反面：
  OUT1 拉低（0V）时，BASE = 5 × R4 / (R5 + R4)
  以 R5 = R4 = 10k 算，BASE ≈ 2.5V —— 远高于 VBE(on)，
  三极管会一直导通，蜂鸣器**一直响**。

所以 R4 必须同时改小，让 OUT1 拉低时能把基极压到 VBE(on) 以下。
"""
import sys

VCC = 5.0
V_BE_ON = 0.65      # 硅管开始导通的门槛，保守取值
V_BE_SAT = 0.75     # 饱和时基极电压
HFE_MIN = 120
I_LOAD = 0.030      # 典型 5V 有源蜂鸣器 30 mA

PULLUPS = (10_000, 22_000, 4_700)
SERIES = (10_000, 4_700, 2_200, 1_000, 470, 220)


def off_voltage(r_up, r_series):
    """OUT1 拉低到 0V 时，基极被分到多少伏。"""
    return VCC * r_series / (r_up + r_series)


def on_current(r_up, r_series):
    """OUT1 高阻时进入基极的电流。R4 串联到高阻端，不参与分流。"""
    return (VCC - V_BE_SAT) / (r_up + 0.0)


def main():
    print(f"判据：OUT1 拉低时基极必须 < {V_BE_ON} V（确保关断）")
    print(f"      OUT1 高阻时基极电流 × hFE({HFE_MIN}) 必须 > {I_LOAD*1000:.0f} mA\n")

    print(f"{'R5(上拉)':>10} {'R4(串联)':>10} {'关断电压':>10} {'基极电流':>10} "
          f"{'可驱动 Ic':>10}  {'结论'}")
    good = []
    for r_up in PULLUPS:
        for r_series in SERIES:
            v_off = off_voltage(r_up, r_series)
            i_b = on_current(r_up, r_series)
            ic = i_b * HFE_MIN
            ok_off = v_off < V_BE_ON
            ok_on = ic >= I_LOAD
            verdict = "OK" if (ok_off and ok_on) else (
                "关不断" if not ok_off else "驱动不足")
            if ok_off and ok_on:
                good.append((r_up, r_series, v_off, i_b, ic))
            print(f"{r_up/1000:>9.1f}k {r_series/1000:>9.1f}k "
                  f"{v_off:>9.3f}V {i_b*1000:>9.2f}mA {ic*1000:>9.1f}mA  {verdict}")

    print()
    if not good:
        print("没有一组取值同时满足——需要换驱动方式（如改用 MOS 管或加一级）")
        return 1
    print("可用组合（按基极电流从大到小）：")
    for r_up, r_series, v_off, i_b, ic in sorted(good, key=lambda x: -x[3]):
        print(f"  R5 = {r_up/1000:.0f}k（上拉到 5V）, R4 = {r_series/1000:g}k（串联）"
              f"  → 关断时基极 {v_off:.2f}V，导通时 {i_b*1000:.2f}mA，"
              f"Ic 上限 {ic*1000:.0f}mA")
    print()
    print("推荐：R5 = 10k（上拉）, R4 = 1k（串联）")
    print("  关断时基极 5×1k/11k = 0.45 V < 0.65 V ✓")
    print("  导通时基极电流 (5−0.75)/10k = 0.425 mA，Ic ≈ 51 mA ✓")
    print("  代价：R4 由 10k 改为 1k，需要换料并重新布局")
    return 0


if __name__ == "__main__":
    sys.exit(main())
