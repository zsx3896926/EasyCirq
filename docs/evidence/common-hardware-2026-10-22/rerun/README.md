# 五项工程结论修复复核（2026-10-22）

> 本目录只做修复与复核，不扩大内容、不合并 PR #5。历史盲测原始回答仍保存在 `../blind/B1.md`–`B6.md` 和 `../blind/eval.md`，未覆盖。
> S1-NTC-ALARM 仍保持“连接级证据”，本复核没有把它升级为功能验证。

## 0. 快照与结论

| 项 | 值 |
|---|---|
| 修复前快照 | `e5094e4`（PR #5 当时 HEAD） |
| 主修复快照 | `4c9db61`（Boost/HX711/DS18B20/TACH/RL 五项结论） |
| 补充修复 | `d97b6f3`（TACH 分压 10k/3.3k）、`662a7ab`（HX711 5V 旁路限定）、`e0710c7`（DS18B20 位数时间/继电器 release 语义/残留同步）、`7c1b886`（TPS63802 Boost 区 D/峰值限流与 TPS61023 纹波/ILIM 条件注记） |
| 复核快照 | 5 个 Agent 均在 `4c9db61` 上运行，回答见本目录；复核发现的问题已应用到 `d97b6f3`/`662a7ab`/`e0710c7` |
| 最终测试 | 在 `7c1b886` 上 `260 tests OK` |
| 未做 | PCB、制造、样机、实测、全在线 GUI、独立资料审校逐条复核 |

**复核结论：** 五项结论均已在正文修正；复核 Agent 另外发现多处残留（DS18B20 9 位时间、TACH 12.6 V 分压、继电器“机械时间”语义、报告/F14/C13 旧结论、TPS63802 Boost 区 D/峰值限流），均已同步。S1 未升级。

## 1. 修改前后对照

### 1.1 Boost 限流公式

| | 修改前 | 修改后 |
|---|---|---|
| 公式 | `IMAXOUT = ILIM(min)·(1−D) − ΔIL/2` | 谷值限流 `IMAXOUT = (1−D)·(ILIM(min)+ΔIL/2)`；峰值限流 `(1−D)·(ILIM(min)−ΔIL/2)` |
| PWR-03 3.0 A 例 | 0.463 A | 0.711 A |
| PWR-03 2.5 A 例 | 0.352 A，判“淘汰” | 0.600 A，**仍可通过** |
| G3 TPS61023 2.7 A 例 | 0.841 A | 1.909 A（旧式低估 56%） |
| 结论 | “3.7 A 开关只剩不到 1 A” | 3.3→5 V 时 2.7 A min 约 1.91 A；实际还受热/输入源/占空比限制 |
| G4 TPS63802 Boost 区 | 理想 D=0.1818、ΔIL=0.497 A、IMAXOUT=3.02 A | 含 η 的 D=0.2636、ΔIL=0.721 A、峰值限流 `IMAXOUT=2.68 A` |

**独立依据：** TI TPS61023 `SLVSF14B` p.9 §7.3.4 **Equation 1**：`IOUT(LC) = (1−D)·(ILIM + 1/2·ΔIL(P-P))`；TI `SLVA372D` p.3 **Equation 3** 为峰值限流式 `(1−D)(ILIM−ΔIL/2)`。复核报告：[boost-limit.md](boost-limit.md)。独立算术：[calc.py](calc.py)。

**仍未核实：** `ILIM(min)=2.7 A` 的手册条件是 `VIN=3.6 V`，3.3 V 下未给；1.9 A 输出时的热/电感/输入源能力；DCM/PFM 与环路；其他 Boost 型号。

### 1.2 HX711 供电模式与盲测评分

| | 修改前 | 修改后 |
|---|---|---|
| 供电模式 | D1 只写内部稳压 + 100 mV 规则 | D1 明确两种：内部稳压（AVDD 2.6–5.5 V，≥100 mV 低于 VSUP）与旁路（VSUP=AVDD/DVDD、VFB=GND、BASE=NC，100 mV 不适用） |
| 5 V AVDD | 被当作违反 100 mV | 旁路模式下合法（VSUP=AVDD=5 V，桥/ADC 按 5 V 重算） |
| B2 评分 | `eval.md` 给 4/5，理由“5 V AVDD 违反 VSUP−100 mV” | 扣分撤销；B2 的引脚表已写 `BASE=NC`、`VFB=AGND`，属于旁路模式；修正为 5/5（见 [eval-addendum.md](eval-addendum.md)） |

**独立依据：** HX711 手册 p.4 “Power Supply Options”：100 mV 要求写在“When using internal analog supply regulator”段；下一段“If the on-chip analog supply regulator is not used”给出旁路接法，未再提 100 mV。AVDD/VSUP 工作范围 2.6–5.5 V（p.3 Table 2）。复核报告：[hx711-supply.md](hx711-supply.md)。

**仍未核实：** 具体模块的 AVDD/VSUP 是否短接、E+ 来源、桥的 5 V 激励上限、手册没有绝对最大额定值、USB 插拔瞬态。

### 1.3 DS18B20 多点转换调度

| | 修改前 | 修改后 |
|---|---|---|
| 多点 | “按个数 × 750 ms 排时间” | `Skip ROM (0xCC)` + `Convert T (0x44)` 广播，所有探头同时转换，总转换 **750 ms 一次** |
| 9 位时间 | 187.5 ms（错） | **93.75 ms**；10 位 187.5、11 位 375、12 位 750 |
| 读回 | 未拆开 | 逐器件 `Match ROM (0x55)` + `Read Scratchpad (0xBE)` 9 字节；8 个标准速约 81.9 ms |
| 一轮 | 隐含 6 s | 广播 750 ms + 读回约 82 ms ≈ **0.834 s** |

**独立依据：** DS18B20 `19-7487 Rev 6` p.3 AC 表与 p.9 Table 2（9/10/11/12 位 = 93.75/187.5/375/750 ms max）、p.10–12 命令集（Skip ROM + Convert T 同时转换；Skip ROM + Read Scratchpad 多器件会冲突）、p.15–16 时隙（60 µs + 1 µs）。复核报告：[ds18b20-multipoint.md](ds18b20-multipoint.md)、独立脚本：[ds18b20_calc.py](ds18b20_calc.py)。

**仍未核实：** 实际总线电容/拓扑、长线与支线、寄生供电、逐器件读取的实际时间、转换与读回流水线是否被手册保证。

### 1.4 风扇测速输入边界

| | 修改前 | 修改后 |
|---|---|---|
| TACH 上拉 | “上拉到 3.3 V 即可，不要照搬 12 V” | Intel §2.1.3：主板侧上拉 **12 V，最大 12.6 V**；3.3 V 上拉不是规范测试条件 |
| 3.3 V MCU | 直接上拉 3.3 V | 12 V 上拉 + 分压/电平转换；推荐 10 kΩ/3.3 kΩ → 3.13 V @12.6 V（2.98 V @12 V） |
| 5.25 V | 易被读成 TACH 上限 | 明确是 **PWM 输入**（pin 4）的 `Vmax`，不是 TACH |
| 分压边界 | 3.6 kΩ → 3.18 V @12 V，12.6 V 时 3.335 V 超 3.3 V | 3.3 kΩ → 3.13 V @12.6 V，留出 3.3 V 轨余量 |

**独立依据：** Intel 4-Wire PWM Fan Specification Rev 1.3 §2.1.1（12 V ±5%）、§2.1.3（TACH 开集、主板侧 12 V max 12.6 V）、§2.1.4（PWM 25 kHz、VIL 0.8 V、Imax 5 mA、Vmax 5.25 V）。复核报告：[fan-tach.md](fan-tach.md)。独立算术：[calc.py](calc.py)。

**仍未核实：** 具体风扇 TACH 的 VOL/漏电/最小灌电流、12 V 轨瞬态、长线/ESD、3.3 V 上拉的非规范用法是否在该型号上可用。

### 1.5 继电器 RL 释放时间

| | 修改前 | 修改后 |
|---|---|---|
| 公式 | `Δt ≈ L·ΔI/V`（线性） | `t = τ·ln(1+I0·R/V_rev)`，`τ=L/R` |
| D03 仅二极管 | 21.4 ms，判“淘汰” | 线圈 3.62 ms 到零 |
| D03 二极管+24 V 稳压管 | 0.607 ms | 线圈 0.495 ms |
| 系统判据 | “3.62 ms 满足 5 ms” | G5LE-1 release/dropout max **5 ms** 是线圈断电到 NC 闭合的端到端时间；5 ms 目标不可达；`3.62+5=8.62 ms`、`0.495+5=5.50 ms` 只能当**保守上限** |
| 残留 | F14 仍用 `L·ΔI/V`；报告仍写“3.62 ms 满足 5 ms”；C13 措辞易误读 | F14 改 RL 解；报告改为“5 ms 不可达”；C13 明确“旧理由错、结论不反转” |

**独立依据：** RL 解；Omron G5LE `K100-E1-08` p.2 `Release time 5 ms max`；Omron General Information `JB301-E3-01` p.7 定义 `Dropout time` 为“线圈断电到 NC 闭合，23 °C，不含弹跳”；1N4148 `VF` 0.7 V 是典型假设（Vishay 只保证 10 mA 时 ≤1.0 V）。复核报告：[relay-release.md](relay-release.md)。独立算术：[calc.py](calc.py)。

**仍未核实：** G5LE 12 V 线圈 `R_coil`/must-release、`L=0.5 H`、5 ms 的测试电路（是否带续流）、1N4148 在 30 mA 实际温度下的 `VF`、稳压管容差/动态电阻、实际释放时间（NOT RUN）。

## 2. 复核任务与回答

| 任务 | 回答 | 快照 | 关键结果 |
|---|---|---|---|
| Boost 限流 | [boost-limit.md](boost-limit.md) | `4c9db61` | 谷值式 1.909 A；旧式 0.841 A 低估 56% |
| HX711 供电 | [hx711-supply.md](hx711-supply.md) | `4c9db61` | 旁路模式允许 5 V AVDD；B2 扣分撤销 |
| DS18B20 多点 | [ds18b20-multipoint.md](ds18b20-multipoint.md) | `4c9db61` | 广播 750 ms + 读回 81.9 ms ≈ 0.834 s；9 位是 93.75 ms |
| 风扇 TACH | [fan-tach.md](fan-tach.md) | `4c9db61` | 12 V max 12.6 V；10k/3.3k → 3.13 V；5.25 V 是 PWM |
| 继电器释放 | [relay-release.md](relay-release.md) | `4c9db61` | 3.62/0.495 ms 线圈；5 ms 不可达；8.62/5.50 ms 为保守上限 |

> 复核 Agent 只读仓库；没有修改仓库文件。它们的回答写在 `hds-common-scratch/rerun/`，本目录是复制件。

## 3. 盲测评分更正（保留原始记录）

原始 `../blind/eval.md` 的 B2 评分把“AVDD=5 V、VSUP=5 V”判为违反 100 mV 约束，给 4/5。复核确认：

- 100 mV 约束只在**内部稳压模式**成立；B2 的引脚表明确写 `BASE=NC`、`VFB=AGND`，属于**旁路模式**。
- HX711 p.4 允许旁路模式 `VSUP=AVDD=5 V`；5 V 在 AVDD/VSUP 2.6–5.5 V 工作范围内。
- 因此 B2 的供电分支**不违规**；原扣分撤销。修正评分见 [eval-addendum.md](eval-addendum.md)。
- 原始 `eval.md` 与 B2 回答**未修改**，作为历史记录保留；本目录只追加更正。

## 4. 仍未核实（汇总）

- Boost：`ILIM(min)` 在 3.3 V 下的保证值、1.9 A 输出的热/电感/输入源、DCM/PFM/环路。
- HX711：模块 AVDD/VSUP 实际接法、桥的 5 V 额定、手册无绝对最大额定值、USB 瞬态。
- DS18B20：实际总线电容/拓扑、寄生供电、转换与读回流水线、逐器件读取时间。
- TACH：具体风扇的 VOL/漏电/灌电流、12 V 轨瞬态、长线/ESD、3.3 V 上拉的非规范用法。
- 继电器：G5LE 线圈 `R/L`/must-release、5 ms 测试电路、1N4148 `VF`、稳压管容差、实际释放时间。
- 全部五项：没有样机/实测；`calc.py` 与复核回答是离线算术，不是功能验证。
- S1-NTC-ALARM：仍为连接级证据（12 器件/网表/save/reopen/DRC 2 warn），未升级为功能验证。

## 5. 文件

| 文件 | 内容 |
|---|---|
| [calc.py](calc.py) | 五项独立算术（无仓库导入） |
| [ds18b20_calc.py](ds18b20_calc.py) | DS18B20 8 器件时序独立脚本（复核 Agent 版） |
| [boost-limit.md](boost-limit.md) | Boost 复核回答 |
| [hx711-supply.md](hx711-supply.md) | HX711 复核回答 |
| [ds18b20-multipoint.md](ds18b20-multipoint.md) | DS18B20 复核回答 |
| [fan-tach.md](fan-tach.md) | 风扇 TACH 复核回答 |
| [relay-release.md](relay-release.md) | 继电器释放复核回答 |
| [eval-addendum.md](eval-addendum.md) | B2 评分更正（原始 eval 保留） |
