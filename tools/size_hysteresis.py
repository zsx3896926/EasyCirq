"""算回差电阻 R6：从 ALARM 正反馈到 NTC_MID，要 3°C 回差。

电路（修好缺陷七之后）：
  NTC_MID 节点：R1 = 10k 上拉到 5V，NTC 到 GND，比较器 IN+
  TH   节点：R2/R3 = 10k/2.4k 分压，比较器 IN-
  ALARM = OUT（LM393 开集）

加 R6 从 ALARM 到 NTC_MID 之后：
  OUT 高阻（未触发）→ R6 不参与 → 动作点由 TH 决定
  OUT 拉低（已触发）→ R6 把 NTC_MID 往下拉 → 需要更低的温度才恢复 → 产生回差

注意方向：开集输出拉低时才有反馈，所以这是"触发后更难退出"，
正是回差该有的方向。
"""
import math
import sys

VCC = 5.0
R1 = 10_000.0        # NTC_MID 上拉
R2 = 10_000.0
R3 = 2_400.0         # 阈值分压下臂
R25 = 10_000.0
B = 3950


def ntc_r(t):
    return R25 * math.exp(B * (1.0 / (t + 273.15) - 1.0 / 298.15))


def v_mid(t, r6=None):
    """NTC_MID 电压。r6=None 表示输出高阻。"""
    rn = ntc_r(t)
    if r6 is None:
        return VCC * rn / (R1 + rn)
    # 输出拉到 0V：R6 与 NTC 并联到地
    down = rn * r6 / (rn + r6)
    return VCC * down / (R1 + down)


TH = VCC * R3 / (R2 + R3)


def trip(r6=None):
    """传感器电压随温度单调下降，不管有没有反馈。

    找 v_mid(T) == TH 的那个 T：
      r6=None 时是"触发点"（输出还高阻）
      给 r6 时会得到一个更低的温度，那就是"释放点"（输出已经拉低，被 R6 往下拽）
    早先给这个函数加过一个 rising 开关，想"反向搜索"——那是错的，
    电压对温度单调，反向搜索只会得到区间端点。"""
    lo, hi = -40.0, 150.0
    for _ in range(90):
        mid = (lo + hi) / 2
        if v_mid(mid, r6) > TH:
            lo = mid
        else:
            hi = mid
    return lo


def main():
    print(f"阈值 TH = {TH:.4f} V")
    t_on = trip(None)          # 输出高阻：触发温度
    print(f"未加回差时动作温度 = {t_on:.2f}°C")

    print()
    print(f"{'R6':>10} {'释放温度':>10} {'回差':>8}  结论")
    best = None
    for r6 in (1e6, 470e3, 330e3, 220e3, 150e3, 100e3, 68e3, 47e3, 33e3, 22e3, 15e3):
        t_off = trip(r6)
        hysteresis = t_on - t_off
        verdict = ""
        if 2.5 <= hysteresis <= 3.5:
            verdict = "≈3°C，可用"
            if best is None:
                best = r6
        elif hysteresis < 2.5:
            verdict = "回差偏小"
        else:
            verdict = "回差偏大"
        print(f"{r6/1000:>9.0f}k {t_off:>10.2f}°C {hysteresis:>7.2f}°C  {verdict}")

    if best:
        t_off = trip(best)
        print()
        print(f"推荐 R6 = {best/1000:.0f}kΩ")
        print(f"  触发 {t_on:.1f}°C → 释放 {t_off:.1f}°C，回差 {t_on - t_off:.2f}°C")
        i_leak = (VCC - 0.0) / best
        print(f"  触发时经 R6 的电流约 {i_leak*1000:.3f} mA（LM393 灌电流能力 6mA，够）")
        return 0
    print()
    print("上面没有一组落在 3°C ± 0.5 内，需要改 R1 或换反馈位置")
    return 1


if __name__ == "__main__":
    sys.exit(main())
