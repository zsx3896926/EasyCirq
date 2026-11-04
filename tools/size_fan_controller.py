"""12V 温控风扇板的设计参数计算。

需求（客户原话）：温度到 45°C 自动开 12V 风扇，降下来自动停；风扇 12V/200mA，
别在边上疯狂启停。

这个脚本不写板子，只负责把参数算准：
  · 阈值分压：45°C 时 NTC 分压中点是多少，R3 该取多大
  · 回差电阻：要 3°C 回差，R6 该取多大
  · 驱动：200mA 负载要多少基极电流，上拉和串联电阻各取多大

算错的后果和报警板那三个缺陷一样——门禁全绿而板子不工作。所以先把数算出来，
再照着搭图，最后用 sch_design_validity 复核。两边必须一致。
"""
import math
import sys

VCC = 5.0            # 逻辑侧
V_FAN = 12.0         # 负载侧
R25 = 10_000.0
B = 3950
T_ON = 45.0          # 客户要的动作温度
HYSTERESIS_C = 3.0   # 客户要的回差
I_LOAD = 0.200       # 风扇 200mA
HFE_MIN = 120        # S8050 下限
V_BE_SAT = 0.75
V_BE_ON = 0.65

E24 = [1.0, 1.1, 1.2, 1.3, 1.5, 1.6, 1.8, 2.0, 2.2, 2.4, 2.7, 3.0,
       3.3, 3.6, 3.9, 4.3, 4.7, 5.1, 5.6, 6.2, 6.8, 7.5, 8.2, 9.1]


def ntc_r(t):
    return R25 * math.exp(B * (1.0 / (t + 273.15) - 1.0 / 298.15))


def ntc_mid(t, r_pull):
    r = ntc_r(t)
    return VCC * r / (r_pull + r)


def v_mid_with_feedback(t, r_pull, r6):
    """输出已拉低（0V）时，R6 把中点往下拽。"""
    r = ntc_r(t)
    down = r * r6 / (r + r6)
    return VCC * down / (r_pull + down)


def crossing(th, r_pull, r6=None):
    lo, hi = -40.0, 150.0
    for _ in range(90):
        mid = (lo + hi) / 2
        v = ntc_mid(mid, r_pull) if r6 is None else v_mid_with_feedback(mid, r_pull, r6)
        if v > th:
            lo = mid
        else:
            hi = mid
    return lo


def nearest_e24(value):
    best = None
    for decade in (1e2, 1e3, 1e4, 1e5):
        for base in E24:
            candidate = base * decade
            if best is None or abs(candidate - value) < abs(best - value):
                best = candidate
    return best


def main():
    r_pull = 10_000.0            # R1：NTC_MID 上拉

    v_at_on = ntc_mid(T_ON, r_pull)
    print(f"NTC 在 {T_ON:.0f}°C 时 = {ntc_r(T_ON)/1000:.3f}k")
    print(f"此时 NTC_MID = {v_at_on:.4f} V")
    print(f"→ 阈值 TH 必须略低于这个值才能在该温度翻转")
    print()

    # 直接解：扫 R3 的 E24 档位，取让动作温度最接近目标的那一档。
    # 早先按"中点的 93%"取，R3=3.9k 落到 47.8°C，偏了 2.8°C——
    # 比例系数是拍脑袋的，扫档位才是有依据的做法。
    best_r3 = None
    for decade in (1e2, 1e3):
        for base in E24:
            candidate = base * decade
            th_c = VCC * candidate / (10_000.0 + candidate)
            trip_c = crossing(th_c, r_pull)
            score = abs(trip_c - T_ON)
            if best_r3 is None or score < best_r3[0]:
                best_r3 = (score, candidate, th_c, trip_c)
    _, r3, th, trip = best_r3
    r3_exact = r3
    print(f"阈值分压：R2 = 10k，R3 ≈ {r3_exact:.0f}Ω → 取 E24 的 {r3/1000:g}k")
    print(f"TH = {th:.4f} V  →  动作温度 {trip:.2f}°C（目标 {T_ON:.0f}±2）")
    ok_th = abs(trip - T_ON) <= 2.0
    print(f"  判定：{'OK' if ok_th else '需要调整'}")
    print()

    # 回差：找让释放温度 = trip - 3°C 的 R6
    target_release = trip - HYSTERESIS_C
    print(f"回差目标：释放温度 {target_release:.2f}°C（{trip:.1f} − {HYSTERESIS_C:.0f}）")
    candidates = []
    for k in E24 + [1.0, 2.2, 3.3, 4.7]:
        for decade in (1e3, 1e4, 1e5):
            r6 = k * decade
            release = crossing(th, r_pull, r6)
            candidates.append((abs(release - target_release), r6, release))
    candidates.sort()
    best = candidates[0]
    r6 = best[1]
    print(f"R6 = {r6/1000:g}k → 释放温度 {best[2]:.2f}°C，"
          f"回差 {trip - best[2]:.2f}°C")
    print(f"  次优：{[f'{c[1]/1000:g}k→{c[2]:.1f}°C' for c in candidates[1:4]]}")
    print()

    # 驱动：200mA 负载
    need_ib = I_LOAD / HFE_MIN
    print(f"驱动：负载 {I_LOAD*1000:.0f}mA，hFE 下限 {HFE_MIN} → 需要基极 {need_ib*1000:.2f}mA")
    r_pullup_exact = (VCC - V_BE_SAT) / need_ib
    r_pullup = nearest_e24(r_pullup_exact)
    ib = (VCC - V_BE_SAT) / r_pullup
    ic = ib * HFE_MIN
    print(f"  基极上拉 R5 ≈ {r_pullup_exact:.0f}Ω → 取 E24 的 {r_pullup/1000:g}k")
    print(f"  基极电流 {ib*1000:.2f}mA → 可驱动 {ic*1000:.0f}mA"
          f"（需要 {I_LOAD*1000:.0f}mA）{'OK' if ic >= I_LOAD else '不够'}")
    # 串联电阻：关断时基极必须被压到 V_BE_ON 以下
    # 串联电阻要小到能把基极压到 V_BE_ON 以下，且留 30mV 余量。
    # 判据是 r4/(r5+r4)*VCC < V_BE_ON - margin，不是"上拉的某个百分比"。
    margin = 0.05
    r_series = None
    v_off = None
    for decade in (1e1, 1e2, 1e3):
        for base in E24:
            candidate = base * decade
            v = VCC * candidate / (r_pullup + candidate)
            if v < V_BE_ON - margin:
                r_series, v_off = candidate, v
                break
        if r_series is not None:
            break
    print(f"  串联 R4 = {r_series:.0f}Ω → 关断时基极 {v_off:.3f}V"
          f"（必须 < {V_BE_ON}V − {margin}V 余量）"
          f"{'OK' if v_off < V_BE_ON - margin else '关不断'}")
    print()

    # ── 风扇启动电流：直流风扇启动电流通常是稳态的 2~3 倍。
    # 客户说的 200mA 是稳态，按它选管子会在启动瞬间顶到额定值。
    surge = I_LOAD * 3
    print("=== 启动电流（客户没说，但必须算）===")
    print(f"  直流风扇启动电流约为稳态的 2~3 倍 → 按 3 倍估 {surge*1000:.0f}mA")
    print(f"  S8050 的 Ic 上限 700mA，稳态 200mA 没问题，"
          f"启动 {surge*1000:.0f}mA 时已接近极限，且 hFE 在大电流下会掉")
    print(f"  MOSFET（AO3400 这类 SOT-23 逻辑电平管）额定 4A 以上，"
          f"Vgs(th) 约 1.05V，5V 栅压驱动充分")
    print("  → **这颗负载应该用 MOSFET，不是三极管**")
    print()

    print("=== 12V 侧 ===")
    print(f"风扇 {V_FAN:.0f}V/{I_LOAD*1000:.0f}mA 接在 12V 与 Q1 集电极之间")
    print("续流二极管 D1 反并在风扇两端（阴极接 +12V），漏电流选 ≥500mA 的肖特基或 1N4148")
    print(f"  → 断开瞬间线圈电流 {I_LOAD*1000:.0f}mA 经 D1 续流，集电极承受的尖峰被钳在 "
          f"{V_FAN:.0f}+0.4V 左右")
    print()
    print("=== 结论 ===")
    problems = []
    if not ok_th:
        problems.append("阈值")
    if ic < I_LOAD:
        problems.append("驱动")
    if v_off >= V_BE_ON:
        problems.append("关断")
    if problems:
        print("需要调整:", ", ".join(problems))
        return 1
    print("参数全部自洽，可以照此搭图。")
    print(f"  阈值：R2=10k R3={r3/1000:g}k  → {trip:.1f}°C")
    print(f"  回差：R6={r6/1000:g}k          → {trip - best[2]:.1f}°C")
    print(f"  驱动（若用 BJT）：R5={r_pullup/1000:g}k R4={r_series:.0f}Ω → {ic*1000:.0f}mA")
    print(f"  驱动（推荐 MOSFET）：栅极 100k 上拉到 5V，静态不取电流，"
          f"栅源电压 5V » Vgs(th) 1.05V")
    return 0


if __name__ == "__main__":
    sys.exit(main())
