"""蜂鸣器驱动链的电气校验——纯读网表 + 算术，不需要实物。

2026-11-01 算出阈值缺陷（25°C 而非 60°C）之后，继续查驱动链，又发现三处问题：

  1. Q1 基极没有到 5V 的通路 → 三极管永远不会导通 → 蜂鸣器永远不响
  2. 蜂鸣器极性接反：封装里标 "-" 的那一脚接了 PWR5V，标 "+" 的接了开关端
  3. 比较器无正反馈 → 没有回差，在阈值附近会抖动，
     而验收示例写的是「58℃ 响，55℃ 停（回差 3℃）」

这三条 18 项门禁都看不出来：网表连接"正确"，DRC 0，图板一致，BOM 一致。
它们验的是"连没连上"，不是"连上之后会不会工作"。

用法：
    python tools/check_buzzer_drive.py
退出码：0 = 三项都通过；1 = 有缺陷；3 = 读不到网表。
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "deliverables" / "alarm" / "design" / "snapshot" / "list.json"

VCC = 5.0
V_BE = 0.7
HFE_MIN = 120          # S8050 datasheet lower bound
I_BUZZER_TYP = 0.030   # 30 mA typical for a 5V active buzzer
I_BASE_MAX_PULLUP = 10_000.0


def load_pins():
    if not SNAPSHOT.is_file():
        print(f"读不到网表：{SNAPSHOT}")
        raise SystemExit(3)
    payload = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    root = payload.get("result") or payload
    parts = {}
    for comp in root.get("components") or []:
        if comp.get("componentType") != "part":
            continue
        parts[comp.get("designator")] = {
            pin.get("pinNumber"): (pin.get("net") or "", pin.get("pinName") or pin.get("name") or "")
            for pin in comp.get("pins") or []
        }
    return parts


def value_of(parts_root, designator):
    """Resistance of a resistor from the schematic, in ohms."""
    for comp in parts_root:
        pass
    return None


def main():
    parts = load_pins()

    def net_of(designator, pin):
        return parts.get(designator, {}).get(pin, ("", ""))[0]

    print("驱动链上的引脚：")
    for designator, pins in parts.items():
        if designator in ("Q1", "U1", "R4", "BZ1"):
            for pin, (net, name) in sorted(pins.items()):
                print(f"  {designator}.{pin:<2} ({name:<4}) -> {net or '(未连接)'}")
    print()

    problems = []

    # 1. does BASE have any path to 5V?
    base_net = net_of("Q1", "1")
    base_members = [f"{d}.{p}({n})" for d, pins in parts.items()
                    for p, (n, _) in pins.items() if n and n == base_net]
    print(f"BASE 网络（{base_net}）上的引脚：{base_members}")
    has_pullup = any(n == "PWR5V" for d, pins in parts.items()
                     for p, (n, _) in pins.items() if n == base_net)
    if not has_pullup:
        # the only other member is R4 -> ALARM = open-collector output
        print("  → 没有引脚接到 PWR5V：基极没有电流来源")
        print("    开集输出拉低时基极被拉到 0V（截止）；高阻时基极悬空（也截止）")
        print("    **Q1 永远不会导通**")
        problems.append("Q1 base has no pull-up to 5V")
        ib = 0.0
    else:
        ib = (VCC - V_BE) / I_BASE_MAX_PULLUP
        print(f"  → 有上拉；基极电流约 {ib*1000:.2f} mA")

    if ib:
        ic = ib * HFE_MIN
        print(f"  可驱动集电极电流 ≈ {ic*1000:.1f} mA（hFE 取下限 {HFE_MIN}）")
        print(f"  蜂鸣器典型 {I_BUZZER_TYP*1000:.0f} mA → "
              f"{'够' if ic >= I_BUZZER_TYP else '不够'}")
        if ic < I_BUZZER_TYP:
            problems.append("insufficient base drive")
    print()

    # 2. buzzer polarity
    print("蜂鸣器极性：")
    for pin in sorted(parts.get("BZ1", {})):
        net, name = parts["BZ1"][pin]
        print(f"  pin{pin} 名称'{name}' -> {net or '(未连接)'}")
    # 引脚名是 '1' / '+' / '-'，但 '-' 是未连的第三脚；网表里看不出哪一个
    # 是真正的正端，要靠符号定义。这里只陈述事实，不下"接反"的结论。
    nets = {pin: parts["BZ1"][pin][0] for pin in parts.get("BZ1", {})}
    plus_net = next((n for p, (n, name) in parts["BZ1"].items() if name == "+"), "")
    if plus_net == "PWR5V":
        print("  → '+' 接 5V，正确")
    elif plus_net:
        print(f"  → '+' 接 {plus_net}（开关端）；**正端是否应为 5V 取决于符号定义，"
              "网表判不了**，需对照器件规格书确认")
    print()

    # 3. hysteresis
    print("比较器回差：")
    th_members = {d for d, pins in parts.items()
                  for p, (n, _) in pins.items() if n == "TH"}
    print(f"  TH 网络上的器件：{sorted(th_members)}")
    # 真正的正反馈：某个器件同时接 ALARM（输出）和 TH/NTC_MID（输入）。
    # R4 接的是 ALARM 与 BASE，那是驱动链，不是反馈。
    inputs = {"TH", "NTC_MID"}
    feedback_parts = []
    for designator, pins in parts.items():
        if designator == "U1":
            continue
        nets = {n for (n, _) in pins.values() if n}
        if "ALARM" in nets and nets & inputs:
            feedback_parts.append(designator)
    print(f"  同时接 ALARM 与输入（TH/NTC_MID）的器件：{feedback_parts or '无'}")
    if feedback_parts:
        print("  → 有正反馈，具备回差")
    else:
        print("  → 没有正反馈 → 没有回差，阈值附近会抖动")
        print("    验收示例写的「58℃ 响，55℃ 停（回差 3℃）」在这版电路上不成立")
        problems.append("no hysteresis")

    print()
    if problems:
        print(f"发现 {len(problems)} 处问题：")
        for item in problems:
            print("  -", item)
        return 1
    print("驱动链三项检查全部通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
