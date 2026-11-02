# 12V 温控风扇板 · 设计记录（未搭图）

> 状态：**参数已算准，电路还没画。** 这份文档只记录"该用什么值、为什么"，
> 不声称板子存在。要搭图时照这里的数走，搭完用 `sch_design_validity.py` 复核。
>
> 生成方式：`python tools/size_fan_controller.py`（每次改需求重跑一次）

## 客户原话

> 温度到 45°C 自动开 12V 风扇，降下来自动停；风扇 12V/200mA，别在边上疯狂启停。

## 算出来的参数

| 项 | 值 | 依据 |
|---|---|---|
| 阈值分压 R2 / R3 | 10k / **4.3k** | 扫 E24 档位取最接近 45°C 的一档，实得 **45.3°C** |
| 回差 R6 | **39k** | 从 ALARM 正反馈到 NTC_MID，实得回差 **2.97°C** |
| 栅极上拉 R5 | **100k** | MOSFET 栅极静态不取电流，100k 足够把栅压拉到 5V |
| 风扇驱动管 | **MOSFET（AO3400 类）** | 见下方"为什么不用三极管" |
| 续流二极管 D1 | 反并在风扇两端，≥500mA | 感性负载必须 |

## 为什么不用三极管（这一条差点选错）

客户说的 200mA 是**稳态**。直流风扇的**启动电流通常是稳态的 2–3 倍**：

```
按 3 倍估 → 启动瞬间 600mA
S8050 的 Ic 上限 700mA，稳态够用，启动时已贴近极限，而且大电流下 hFE 会掉
```

所以这颗负载该用 MOSFET：AO3400 这类 SOT-23 逻辑电平管额定 4A 以上，
`Vgs(th)` 约 1.05V，5V 栅压驱动充分，栅极还不取直流电流。

**如果一定用三极管**：R5 取 2.4k、串联 R4 取 10Ω → 基极 1.77mA → 可驱动 212mA。
稳态能过，启动裕量不足，属于"能跑但不稳"。

## 意图文件（搭图时直接用）

```json
{
  "schema": "easycirq-design-intent/v1",
  "name": "12V 温控风扇",
  "power_rail": "PWR5V",
  "load_rail": "PWR12V",
  "ground": "GND",
  "rails": { "PWR5V": 5.0, "PWR12V": 12.0 },
  "grounds": ["GND"],
  "threshold": {
    "comparator": "U1",
    "target_c": 45,
    "tolerance_c": 3,
    "vcc": 5.0,
    "sensor": { "kind": "ntc", "r25": 10000, "b": 3950 },
    "hysteresis_c": 3
  },
  "switches": [
    { "part": "Q1", "load": "FAN1", "load_ma": 200,
      "kind": "mosfet", "vgs_th": 1.05, "id_max_a": 4.0,
      "load_kind": "inductive", "load_rail": "PWR12V" }
  ]
}
```

## 尚未建模的部分（工具查不了，必须人判）

| 项 | 状态 |
|---|---|
| 续流二极管是否存在 / 方向对不对 | ✅ **已有判据**：`inductive_load` 查 `NO_FLYWHEEL_DIODE` 与 `FLYWHEEL_DIODE_REVERSED` |
| 双电源域接错（漏极接到 5V） | ✅ **已有判据**：`supply_domains` 查 `SWITCH_LOAD_ON_LOGIC_RAIL` |
| 两轨被 0Ω 短接 | ✅ **已有判据**：`RAIL_SHORTED` |
| 12V 与 5V 共地 | ✅ **已有判据**：`GROUNDS_DISCONNECTED`（只在 `grounds` 声明了多个地时才查） |
| 风扇启动电流的裕量 | ❌ 工具不猜倍率，用意图里声明的 `load_ma` |
| **器件额定电压是否够** | ❌ **要规格书**——"这颗管子 Vds 上限 30V，12V 打不穿"网表里没有。这一条只能人判 |

前四类已由 `sch_design_validity.py` 覆盖；最后两项明确写在检查器的 `note` 里，
不假装能判。

---

## 板子已画出（2026-11-02）

工程 `Fan-Controller-12V`，原理图页 `P1`，11 个器件、8 个网络，全部与设计一致：

```
PWR5V    R1.1 R2.1 R5.1 U1.8
PWR12V   D1.1 FAN1.1
GND      NTC1.2 Q1.2 R3.2 U1.4
NTC_MID  NTC1.1 R1.2 R6.2 U1.3
TH       R2.2 R3.1 U1.2
ALARM    R6.1 R7.2 U1.1
GATE     Q1.1 R5.2 R7.1
FAN_M    D1.2 FAN1.2 Q1.3
```

### 判据在全新板上抓到的东西

第一次跑，五类里 `inductive_load` 直接 **fail**：

```
! FLYWHEEL_DIODE_REVERSED: 续流二极管 D1 极性接反：
  阳极接 PWR12V、阴极接 FAN_M。
  应该反过来——阴极朝 PWR12V、阳极朝 FAN_M，
  否则它正向导通，一上电就把 PWR12V 短路
```

**判据是对的，线是我接错的。** 库里这颗 1N4148W 的引脚定义是
**pin2 = A（阳极）、pin1 = K（阴极）**，我按"1 阳 2 阴"的常见约定接反了。

`sch disconnect` 断开后按正确极性重接，五类全过：

```
threshold_sanity   pass   45.3°C（目标 45±3）
switch_drive       pass   栅极 5.0V » 1.05V，200mA « 4A
hysteresis         pass   反馈件 R6
inductive_load     pass   阴极朝 12V、阳极朝开关侧
supply_domains     pass
设计有效性：pass
```

**这是这次压力测试最重要的产出**：一块从零画的板子，
第一个让工具拦住的就是"会让电源短路"的那一处。

### 顺带记两个坑

**坑一：40 个内置块里没有模拟比较器这一类。**
`easycirq blocks ls` 有 power / comms / mcu / rf / usb / display / audio / storage /
button / sensing 十类，**没有"阈值比较 / 温控"**。所以"做个风扇控制器"这个需求，
块库给不了任何帮助，只能 11 个器件一个个手放。这是块库的真实缺口。

**坑二：我自己的成功判定又错了一次。**
`sch autoconnect` 输出的是人读文本（`✓ R1:1 → PWR5V [net_label] ...`），
我却按 `"ok": true` 去匹配，于是 26 次**全部成功**的连线被我报成 26 个失败。
读回网表才知道 8 个网络分毫不差。

**这已经是第三次同类错误**（前两次：数 bundle 里的 `[object Object]`、
按固定空格数断言状态列）。共同的病根是**用猜的格式去判成功**，而不是读回真实状态再判断。
