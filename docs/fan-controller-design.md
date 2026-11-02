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
