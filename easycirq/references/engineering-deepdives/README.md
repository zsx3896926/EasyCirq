# 工程深潜：真实设计、失效机制与审图训练

## 内容导航

- [1. 和现有内容的分工](#1-和现有内容的分工)
- [2. 按症状找](#2-按症状找)
- [3. 按设计阶段找](#3-按设计阶段找)
- [4. 按器件/领域找](#4-按器件领域找)
- [5. 证据怎么读](#5-证据怎么读)
- [6. 文件地图](#6-文件地图)
- [7. Agent 使用规则](#7-agent-使用规则)
- [8. 不覆盖什么](#8-不覆盖什么)


> 这组内容回答三个问题：**工程师为什么这样设计、真实设计为什么失败、Agent 怎样把这些经验落到具体原理图和 PCB。**
>
> 它不是设计卡的替代品，也不是“更多规则”。设计卡给拓扑与参数步骤；这里给**真实开源设计的位号/网络/页码证据、跨模块失效链、设计取舍和可训练的审图题**。

## 1. 和现有内容的分工

| 已有内容 | 负责 | 本目录补什么 |
|---|---|---|
| [设计卡库](../design-cards/README.md) | 拓扑、参数步骤、算例、逐脚/PCB 要求 | 为什么选这个拓扑、真实设计怎么落地、哪里容易误判 |
| [故障与反例库](../failures/README.md) | 单点故障的现象→假设→检查→修复 | 跨模块组合失效、测量误判、版本/替代料边界（F23–F33） |
| [组合与接口契约](../module-integration.md) | 接口契约、6 个组合案例 | 8+ 个“单模块正常、组合失败”的机制与区分检查（D1） |
| [仿真与测量](../simulation-measurement.md) | 仿真/测量总则 | 测量接法制造的假象、示波器/探头/分流器的具体算例（C4） |
| [板级热专题](../thermal/topic.md) | Rθ、结温、PCB/外壳热路径 | 机械/环境如何改变热路径、外壳装配后的交叉验证（E3） |

**不要全量加载。** 先按症状/器件/阶段选 1 篇专题，再按需读 1 个案例和 1 张设计卡。

## 2. 按症状找

| 你看到的现象 | 先读 | 再查 |
|---|---|---|
| 插上 USB/适配器/调试器后复位、发热、反向供电 | [B1 多路供电与电源切换](topics/b1-power-path-and-source-switching.md) | F23、F27、PWR-05/09/10 |
| 电池设备待机远超标称、续航对不上 | [B2 低功耗整机与睡眠电流](topics/b2-sleep-current-budget.md) | PWR-01、MCU-02、任务场景 S04/S34 |
| 充电慢、充电时系统掉电、电量跳变 | [B3 充电、系统负载与电量判断](topics/b3-charger-load-and-gauge.md) | PWR-06/07/08、F09 |
| 无线发射/电机启动时系统复位或音频爆音 | [B4 电源动态与负载瞬态](topics/b4-power-dynamics.md) | F25、F26、RF-03 |
| 传感器读数有偏、跳、温漂、校准后仍不够 | [C1 从传感器到 ADC 的误差链](topics/c1-sensor-to-adc-error-chain.md) | ANA-01/03/04/05、F01/F22 |
| 模拟量被数字/功率噪声污染，地怎么接都别扭 | [C2 接地、屏蔽与共模](topics/c2-grounding-shielding-common-mode.md) | F16/F17、MT-031 |
| 运放直流增益对，但输出饱和/振铃/上电异常 | [C3 运放容易被漏查的工作条件](topics/c3-opamp-hidden-conditions.md) | ANA-02/03/04、SBOA583 |
| 示波器看到“明显振铃/纹波”，改板后却没改善 | [C4 测量方法本身造成的错误](topics/c4-measurement-artifacts.md) | F33、仿真与测量 §5 |
| 单个模块都正常，接在一起就 NACK/冲突/读错 | [D1 接口组合后的隐藏约束](topics/d1-interface-combination-constraints.md) | F06/F28/F29、module-integration §13 |
| 晶体不起振/偶发不起振/频偏/抖动 | [D2 时钟系统完整检查](topics/d2-clock-system-checklist.md) | MCU-05/06、F05 |
| 板内正常，接长线/外设/热插拔就坏 | [D3 连接器与板外通信](topics/d3-off-board-interfaces.md) | IF-06/07/08/11、F07/F08 |
| 模组能用，装壳后距离/灵敏度下降 | [D4 无线性能与整机环境](topics/d4-wireless-integration.md) | F18、RF-01/02/04、KDB 996369 D04 |
| 继电器/电磁阀/电机关断时炸管、触点烧 | [E1 感性负载与能量去向](topics/e1-inductive-load-energy-path.md) | DRV-03/05、F14 |
| MOSFET 发热/误导通/低栅压不够 | [E2 MOS 栅极驱动与异常状态](topics/e2-gate-drive-and-false-turn-on.md) | DRV-01/02/04/05、F13 |
| 板在壳里过热、降额后仍不够 | [E3 热设计与机械环境](topics/e3-thermal-mechanical-environment.md) | thermal/topic、thermal/cases |
| 连接器/端子/焊点发热、长期接触不良 | [E4 连接与长期可靠性](topics/e4-connector-long-term-reliability.md) | MF-xx、VESC/MNT/Smoothieboard 案例 |

## 3. 按设计阶段找

| 阶段 | 先做什么 | 读什么 |
|---|---|---|
| 方案/架构 | 画电源树、接口契约、状态表 | B1、B3、D1、D3 |
| 选型 | 核对完整型号、条件、边界 | 设计卡 + 对应专题的“必须先知道的条件” |
| 原理图 | 逐脚/逐网络/状态表 | 专题 §3 + 设计卡逐脚 + F23–F33 |
| PCB | 回路、参考平面、热路径、连接器 | 专题 §4 + pcb-placement/routing-details |
| 评审 | 先问“结论类型”，再给证据 | [审图练习](exercises/README.md)、[预布局审题练习](exercises-pcb/README.md) |
| 调试 | 先区分测量假象 vs 真实故障 | C4、F33、simulation-measurement §5 |
| 改板/替代 | 只改一个条件，重算边界 | F31、selection/replacement-classes |

## 4. 按器件/领域找

| 领域 | 专题 | 开源案例 |
|---|---|---|
| MCU/开发板 | B2、D1、D2 | [MCU 与开发板](casebook/mcu-dev-boards.md) |
| 低功耗无线/电池 | B2、B3、B4、D4 | [低功耗无线/电池](casebook/low-power-wireless-battery.md) |
| 电机/功率/工业 | B4、E1、E2、E3 | [电机/功率/工业](casebook/motor-power-industrial.md) |
| 音频/精密模拟 | C1、C2、C3 | [音频/模拟/精密](casebook/audio-analog-precision.md) |
| 高速/RF/FPGA | C2、D2、D3、D4 | [高速/RF/FPGA](casebook/high-speed-rf-fpga.md) |
| HMI/连接器/热 | E3、E4 | [HMI/连接器/热](casebook/hmi-connectors-thermal.md) |

## 5. 证据怎么读

- `A`：作者/维护者明确记录（CHANGELOG、commit、issue、设计注记）或可复现实测。
- `B`：原厂手册/应用笔记/规范支持机理，但本板未实测。
- `C`：工程推断，需后续验证。
- `D`：未证实线索，只作线索。
- `[构造]`：写明假设的构造案例/算例，不是实测。
- `[未执行]`：没有做的仿真/测量。
- `[待核]`：缺型号资料，待按实际型号核对。

具体数值只在所写型号、条件、温度、版本内成立；典型值不是保证值；开源项目不是正确性权威。

## 6. 文件地图

```
engineering-deepdives/
├── README.md                  # 本页
├── sources.md                 # D-S 来源 + OSHW 项目/许可台账
├── action-map.md              # 24 条“触发→读取→动作→证据→失败后继续”
├── topics/                    # 16 篇专题
│   ├── b1 ... e4
├── casebook/                  # 25 个开源项目，按领域分组
│   ├── index.md
│   ├── mcu-dev-boards.md
│   ├── low-power-wireless-battery.md
│   ├── motor-power-industrial.md
│   ├── audio-analog-precision.md
│   ├── high-speed-rf-fpga.md
│   └── hmi-connectors-thermal.md
├── exercises/
│   ├── README.md
│   ├── exercises.md           # 20 题
│   ├── paired-cases.md        # 8 对
│   ├── answers.md             # 参考答案
│   └── blind-prompts.md       # 无题型提示的独立输入（尚未运行）
└── exercises-pcb/             # PCB 预布局审题练习（同结构，绑定离线案例集）
```

## 7. Agent 使用规则

1. 先读对应专题的 §0–§2，确认“是否需要做、缺什么条件、机制是什么”。
2. 再把 §3/§4 的检查项落到当前工程的**位号、网络、状态**；不要只说“检查一下”。
3. 用 §6 的计算/测量方法给出**可观察证据**；没有证据就写 `待确认`。
4. 失败时按 §7 的排查顺序，先区分“测量假象/条件不足/真实缺陷”，再改板。
5. 交付时写清：结论类型（可确认/条件/待补）、依据、还缺什么、下一步。

## 8. 不覆盖什么

- 不覆盖所有硬件行业、所有协议、所有认证；不声称已量产验证。
- 不替代具体型号手册、勘误、项目安全/可靠性标准、板厂规则。
- 没有实际 EDA 回读、仿真、制造、样机/EMC/安规测试的内容，保持 `未执行`。
- 开源项目的许可未明确时，只做阅读分析，不复制图纸/文件。

历史试答原始记录单独保存在[仓库证据目录](https://github.com/zsx3896926/EasyCirq/blob/main/docs/evidence/deepdives-2026-10-22/README.md)，不随Skill运行资料分发；其题型提示泄漏与旧评分限制见记录说明。
