# TPS61023 3.3 V→5 V/0.5 A：占空比、纹波、开关峰值与谷值限流复核

- 仓库：`C:\Users\jlc\work\EasyCirq`
- 固定快照：`4c9db61628e4a83f01acad1c53ea5c0665182325`
- 复核日期：2026-10-22
- 约束：只读仓库，未修改、未暂存、未提交任何仓库文件；计算只依据仓库现有内容和 TI 原厂手册。

## 0. 结论摘要

| 项目 | 按任务字面 `VIN=3.3 V` | 按仓库算例 `VIN(min)=3.135 V`（3.3 V±5%） |
|---|---:|---:|
| 占空比 `D` | **0.4060** | **0.4357** |
| 电感纹波 `ΔIL(P-P)` | **1.3398 A ≈ 1.340 A** | **1.3659 A ≈ 1.366 A** |
| 0.5 A 负载时开关峰值 `ISW(max)` | **1.5117 A ≈ 1.512 A** | **1.5690 A ≈ 1.569 A** |
| 限流允许的最大输出 `IOUT(LC)` | **2.0017 A ≈ 2.002 A** | **1.9090 A ≈ 1.909 A** |
| 相对 0.5 A 的余量 | **300.3%** | **281.8%** |
| 修复前旧式结果 | 0.9339 A（低估 53.3%） | 0.8407 A（低估 56.0%） |

**公式依据（要点）：**

- 占空比：TI TPS61023 数据手册 **SLVSF14B**（2019-09，Rev. August 2020）**Equation 2**：`D = 1 − VIN·η / VOUT`（p.9）。
- 电感纹波：同一手册 **Equation 3**（p.10）及 **Equation 6**（p.13）：`ΔIL(P-P) = VIN·D / (L·fSW)`。
- 电感平均电流：**Equation 5**（p.13）：`IL(DC) = VOUT·IOUT / (VIN·η)`。
- 电感/开关峰值：**Equation 7**（p.14）：`IL(P) = IL(DC) + ΔIL(P-P)/2`。
- **谷值限流**：**Equation 1**（p.9，§7.3.4）：`IOUT(LC) = (1 − D)·(ILIM + ΔIL(P-P)/2)`。手册明确 TPS61023 采用 valley current limit sensing scheme，检测发生在 off-time、通过同步整流管压降检测。
- **峰值限流**的对应式：TI **SLVA372D**（2009-11，Revised November 2022）**Equation 3**（p.3）：`IMAXOUT = (ILIM(min) − ΔIL/2)·(1 − D)`。
- 两者不能混用：谷值式加半纹波，峰值式减半纹波；两式都必须把半纹波放在 `(1−D)` 括号内。

**关键结论：** 旧式 `ILIM·(1−D) − ΔIL/2` 同时犯了两个错误：把 TPS61023 的谷值限流当成峰值限流（符号错），以及只把 `ILIM` 乘了 `(1−D)`、把 `ΔIL/2` 留在括号外（代数错）。在 3.135 V 算例中，旧式 0.841 A 比重算后的 1.909 A 低估 **56.0%**。

## 1. 快照与只读声明

- 开工时 `git rev-parse HEAD` 返回 `4c9db61628e4a83f01acad1c53ea5c0665182325`。
- 复核期间其他会话继续提交，HEAD 先后推进到 `d97b6f3`、`662a7ab`；但对本次涉及的 Boost 文件执行 `git diff 4c9db61 -- <file>` 为空，且 `git show 4c9db61:<file>` 的关键行与工作树一致。工作树文件是 CRLF，`git show` 输出是 LF，所以直接比 SHA256 会不同；按 Git 内容比较无差异。
- 本报告没有修改仓库。工作树中的 `design-hardware/assets/decisions/`、`design-hardware/references/decisions/`、`docs/evidence/common-hardware-2026-10-22/rerun/` 等未跟踪内容属于其他会话，未纳入本次复核。

## 2. 实际读过的文件/小节

| 文件 | 实际读过的部分 | 用途 |
|---|---|---|
| `design-hardware/references/design-cards/power/p03-boost.md` | 头部证据说明；§1 第 3 条；§2；§3；§4 第 1–5 步；§5 第 5 步；§12 | 仓库的 Boost 公式、12 V 算例与来源表 |
| `design-hardware/references/common-hardware/g-power-conversion.md` | G3 Boost 整节：结论、必查参数、参数与算例、常见误判、来源与证据 | 修正后的 1.909 A / 0.841 A 对照 |
| `design-hardware/references/calculations/power-thermal.md` | §3.3 Buck/Boost 功率级表；“芯片可输出”行；§4.3 快速判据 | 谷值/峰值公式对照与 Buck 判别 |
| `design-hardware/references/source-register.md` | PWR-S02、CHW-S123 登记行 | 文档号、版本、实际查阅范围 |
| `C:\Users\jlc\work\hds-common-scratch\ds-power\tps61023.pdf`（SLVSF14B） | p.1 Features；§6.3 Recommended Operating Conditions；§6.4 Thermal Information；§6.5 Electrical Characteristics；§7.3.3；§7.3.4（Equation 1–3）；§7.4.1；§8.2.2.2（Equation 5–7）；Table 8-2 | 全部原厂数值与式号 |
| `C:\Users\jlc\work\hds-common-scratch\tps61023-p9.png` | SLVSF14B p.9 页面图像 | 目视核对 Equation 1 与 Equation 2 的印刷形式 |
| `C:\Users\jlc\work\hds-common-scratch\rerun\slva372d.pdf` / `.txt`（SLVA372D） | 封面/目录；§2（Equation 1–4） | 峰值限流式与开关峰值式的独立原厂依据 |
| `C:\Users\jlc\work\hds-common-scratch\groups\g-power-conversion\03-boost.md` | “参数与算例”段（修复前底稿） | 保留历史原始回答，见 §8 |
| `docs/evidence/common-hardware-2026-10-22/audit/g-converters.md` | G3 Boost 审计段的摘读 | 确认 G3 主题的证据分工背景 |

未读：SLVSF14B §9–§12（布局、机械、封装图）；SLVA372D §3–§7 的逐条推导（只读了与本次问题直接相关的 §2 和式号）。

## 3. 给定值与数值性质

| 量 | 值 | 性质 | 依据/条件 |
|---|---:|---|---|
| `VIN` | 3.3 V | 任务给定（标称值） | 仓库算例按 3.3 V±5% 取 `VIN(min)=3.135 V` |
| `VOUT` | 5 V | 任务给定（设定值） | 在 TPS61023 的 2.2–5.5 V 输出范围内（§6.3） |
| `IOUT` | 0.5 A | 任务给定（负载要求） | 用于计算 0.5 A 工作点的峰值与余量 |
| `L` | 1 µH | 任务给定；**假设理想、无容差** | 在手册推荐的有效电感范围 0.37–2.9 µH 内（§6.3、§8.2.2.2）；Table 8-2 也列有 1 µH 推荐料 |
| `fSW` | 1 MHz | 任务给定；手册为**典型值** | §6.5 `fSW` 行：`VIN=3.6 V, VOUT=5.0 V, PWM` 时 typ 1.0 MHz；表中未给 min/max；§7.3.3 说明 `VIN>1.5 V` 时准恒定 1 MHz |
| `η` | 0.9 | **假设值** | §7.3.4 Equation 2 下文：“use 90% for most applications”；不是 3.3 V/0.5 A 实测曲线值 |
| `ILIM(min)` | 2.7 A | **保证最小值** | §6.5 `ILIM_SW` 行：`VIN=3.6 V, VOUT=5.0 V`，`TJ=−40…125°C`，min 2.7 A / typ 3.7 A；表中未给 max |
| `D`、`ΔIL`、`ISW`、`IOUT(LC)` | 见 §5/§6 | **计算值** | 由上表给定值按 §4 公式推出 |
| 工作模式 | CCM/PWM | **假设** | 0.5 A 时按 CCM 计算；实际轻载会进 PFM/DCM，见 §10 |

**特别说明：** `ILIM(min)=2.7 A` 的手册测试条件是 `VIN=3.6 V, VOUT=5.0 V`。任务用 3.3 V，严格说这是把 3.6 V 的保证值外推到 3.3 V；3.3 V 下的实际谷值限流未在读到的手册段落中给出，标为 **待核实**。本报告按任务给定的 2.7 A 计算，并把这一点保留在 §10。

## 4. 公式依据（手册/文档号与式号）

| 量 | 公式 | 原厂依据 |
|---|---|---|
| 占空比 | `D = 1 − VIN·η / VOUT` | TPS61023 SLVSF14B **Eq.2**（p.9，§7.3.4）；SLVA372D **Eq.1**（p.2，§2） |
| 电感纹波 | `ΔIL(P-P) = VIN·D / (L·fSW)` | SLVSF14B **Eq.3**（p.10，§7.3.4）与 **Eq.6**（p.13，§8.2.2.2）；SLVA372D **Eq.2**（p.2） |
| 电感平均电流 | `IL(DC) = VOUT·IOUT / (VIN·η)` | SLVSF14B **Eq.5**（p.13，§8.2.2.2）；在 CCM Boost 中输入平均电流等于电感平均电流 |
| 电感/开关峰值 | `IL(P) = IL(DC) + ΔIL(P-P)/2` | SLVSF14B **Eq.7**（p.14，§8.2.2.2） |
| 开关峰值（负载侧写法） | `ISW(max) = IOUT/(1−D) + ΔIL/2` | SLVA372D **Eq.4**（p.3，§2）；与 Eq.7 等价 |
| 谷值限流最大输出 | `IOUT(LC) = (1−D)·(ILIM + ΔIL(P-P)/2)` | SLVSF14B **Eq.1**（p.9，§7.3.4）；原文：“maximum continuous output current (IOUT(LC)), before entering current limit (CL) operation” |
| 峰值限流最大输出 | `IMAXOUT = (1−D)·(ILIM(min) − ΔIL/2)` | SLVA372D **Eq.3**（p.3，§2）；其代数形式对应“限流点为电感峰值” |

**式号与印刷形式的核对：** 已用 `tps61023-p9.png` 目视确认 p.9 的 Equation 1 为

```text
IOUT(CL) = (1 − D) × ( ILIM + ½ ΔIL(P-P) )
```

（手册正文写 `IOUT(LC)`，式(1)印刷为 `IOUT(CL)`，两者是同一个量；本报告正文统一用 `IOUT(LC)`。）

Equation 2 为

```text
D = 1 − (VIN × η) / VOUT
```

与文本提取一致。Eq.3/5/6/7 通过同一 PDF 的 `pdftotext` 文本读取；未逐页做图像核对，但式号、变量说明与量纲自洽。

## 5. 计算 A：按任务字面 `VIN = 3.3 V`

中间量不提前取整；最终按 4 位有效数字报告。

### 5.1 占空比

```text
D = 1 − VIN·η / VOUT
  = 1 − 3.3 × 0.9 / 5
  = 1 − 2.97 / 5
  = 1 − 0.594
  = 0.4060
```

即 **D = 40.60%**。`1 − D = 0.5940`。

### 5.2 电感纹波

```text
ΔIL(P-P) = VIN·D / (L·fSW)
         = 3.3 × 0.4060 / (1 × 10⁻⁶ H × 1 × 10⁶ Hz)
         = 1.3398 / 1
         = 1.3398 A
```

即 **ΔIL ≈ 1.340 A**。半纹波为 `ΔIL/2 = 0.6699 A`。

### 5.3 电感平均电流（0.5 A 工作点）

```text
IL(DC) = VOUT·IOUT / (VIN·η)
       = 5 × 0.5 / (3.3 × 0.9)
       = 2.5 / 2.97
       = 0.84175 A
```

也可写成 `IOUT/(1−D) = 0.5/0.5940 = 0.84175 A`，两者一致（这正是 Eq.2 与 Eq.5 的自洽性）。

### 5.4 0.5 A 工作点的谷值与 CCM 检查

```text
IL(valley) = IL(DC) − ΔIL/2
           = 0.84175 − 0.66990
           = 0.17185 A
```

谷值为正（0.172 A > 0），所以 **0.5 A 工作点按 CCM 计算是成立的**。但余量很薄：DCM 边界为

```text
IOUT(DCM boundary) = (1−D)·ΔIL/2
                   = 0.5940 × 0.6699
                   = 0.39792 A
```

0.5 A 只比 DCM 边界高约 0.102 A（26%）。如果电感是 −30% 容差（0.7 µH），纹波变为 `1.3398/0.7 = 1.914 A`，DCM 边界升到 `0.5940 × 0.957 = 0.5685 A`，0.5 A 工作点就会进入 DCM。见 §10。

### 5.5 0.5 A 工作点的开关峰值电流

开关在导通期承载电感电流，因此开关峰值等于电感峰值：

```text
ISW(max) = IL(DC) + ΔIL/2
         = 0.84175 + 0.66990
         = 1.51165 A
```

即 **ISW(max) ≈ 1.512 A**（在 `IOUT=0.5 A`、`VIN=3.3 V` 的工作点）。也可用 SLVA372D Eq.4：

```text
ISW(max) = IOUT/(1−D) + ΔIL/2
         = 0.5/0.5940 + 0.6699
         = 0.84175 + 0.66990
         = 1.51165 A
```

### 5.6 限流允许的最大输出电流（谷值式）

TPS61023 是谷值限流，使用 SLVSF14B Eq.1：

```text
IOUT(LC) = (1 − D) × (ILIM + ΔIL/2)
         = 0.5940 × (2.7 + 0.6699)
         = 0.5940 × 3.3699
         = 2.00172 A
```

即 **IOUT(LC) ≈ 2.002 A**。这是“进入限流之前”的最大连续输出电流，不是 2 A 的连续额定值。

**独立校核（功率平衡）：**

```text
IOUT(LC) = η·VIN·(ILIM + ΔIL/2) / VOUT
         = 0.9 × 3.3 × 3.3699 / 5
         = 2.00172 A
```

与 Eq.1 的结果完全相同。原因是 `1−D = η·VIN/VOUT`，两式在 CCM 下是同一能量平衡的两种写法。

### 5.7 限流边界处的开关峰值

在 `IOUT = IOUT(LC)` 时，电感平均电流为

```text
IL(DC,LC) = ILIM + ΔIL/2 = 2.7 + 0.6699 = 3.3699 A
```

谷值正好是 `ILIM = 2.7 A`，峰值为

```text
ISW(at limit) = ILIM + ΔIL = 2.7 + 1.3398 = 4.0398 A
```

即 **约 4.040 A**。这个值用于电感饱和/瞬态应力的上限评估，不是 0.5 A 工作点的峰值。

### 5.8 开关时间校核

```text
tON  = D/fSW      = 0.4060/1 MHz = 406.0 ns
tOFF = (1−D)/fSW  = 0.5940/1 MHz = 594.0 ns
```

对比 §6.5：`tON_min` max 130 ns、`tOFF_min` max 120 ns。406 ns 与 594 ns 都远大于最小值，**开关时间不构成限制**。

### 5.9 纹波比例与手册建议

```text
ΔIL / IL(DC) = 1.3398 / 0.84175 = 1.5917 = 159.2%
```

手册 §8.2.2.2（p.14）原文建议：“Normally, it is advisable to work with an inductor peak-to-peak current of less than 40% of the average inductor current for maximum output current.” 本算例的 159% 远高于 40%。1 µH 本身在推荐范围 0.37–2.9 µH 内，Table 8-2 也列有 1 µH 推荐料，但这说明**纹波很大、0.5 A 工作点离 DCM 边界很近**，不能把“1 µH 是推荐值”误解为“纹波一定合适”。见 §10。

## 6. 计算 B：按仓库算例 `VIN(min) = 3.135 V`（3.3 V±5%）

仓库 `g-power-conversion.md` 的算例条件是 `3.3 V±5%（3.135–3.465 V）→ 5 V/0.5 A`，因此用 `VIN(min)=3.135 V`。这一组用于和快照中的 1.909 A / 0.841 A 对照。

### 6.1 占空比

```text
D = 1 − 3.135 × 0.9 / 5
  = 1 − 2.8215 / 5
  = 1 − 0.5643
  = 0.4357
```

### 6.2 电感纹波

```text
ΔIL = 3.135 × 0.4357 / (1 × 10⁻⁶ × 1 × 10⁶)
    = 1.36592 A
```

半纹波 `ΔIL/2 = 0.68296 A`。

### 6.3 0.5 A 工作点

```text
IL(DC) = 0.5 / (1 − 0.4357) = 0.5 / 0.5643 = 0.88605 A
ISW(max) = 0.88605 + 0.68296 = 1.56901 A
IL(valley) = 0.88605 − 0.68296 = 0.20309 A > 0  → CCM
DCM boundary = 0.5643 × 0.68296 = 0.38539 A
```

即 **ISW(max) ≈ 1.569 A**，与快照 `g-power` 的 `0.886+0.683=1.569 A` 一致。

### 6.4 限流允许的最大输出电流（谷值式）

```text
IOUT(LC) = 0.5643 × (2.7 + 0.68296)
         = 0.5643 × 3.38296
         = 1.90900 A
```

即 **IOUT(LC) ≈ 1.909 A**，与快照 `g-power` 的 `0.5643×3.383 = 1.909 A` 一致。

功率平衡校核：

```text
0.9 × 3.135 × 3.38296 / 5 = 1.90900 A
```

完全相同。

### 6.5 限流边界处的开关峰值

```text
ISW(at limit) = 2.7 + 1.36592 = 4.06592 A ≈ 4.066 A
```

### 6.6 修复前旧式结果（同一 3.135 V 条件）

```text
旧式 = ILIM·(1−D) − ΔIL/2
     = 2.7 × 0.5643 − 0.68296
     = 1.52361 − 0.68296
     = 0.84065 A
```

即 **0.841 A**，与快照中作为反例保留的 `2.7×(1−0.4357)−0.683=0.841 A` 一致。

## 7. 谷值限流与峰值限流的区别

设电感电流为梯形波：谷值 `IL,v`、峰值 `IL,p`、纹波 `ΔIL = IL,p − IL,v`，平均值为

```text
IL,avg = (IL,v + IL,p)/2
```

Boost 在 CCM 下，输出只在关断区间 `(1−D)T` 接收电感电流，因此

```text
IOUT = (1 − D) · IL,avg
```

这个 `(1−D)` 因子是“电感平均电流 → 输出平均电流”的转换，任何限流公式都不能漏。

| 项目 | 谷值限流（TPS61023） | 峰值限流（SLVA372D Eq.3 的代数形式） |
|---|---|---|
| 检测位置/时刻 | 关断期，同步整流管压降，电感电流最低点 | 导通期，开关电流最高点 |
| 限流条件 | `IL,v = ILIM` | `IL,p = ILIM` |
| 限流点的电感平均 | `IL,avg = ILIM + ΔIL/2` | `IL,avg = ILIM − ΔIL/2` |
| 输出平均 | `IOUT(LC) = (1−D)(ILIM + ΔIL/2)` | `IMAXOUT = (1−D)(ILIM − ΔIL/2)` |
| 纹波增大时 | 按限流式算出的允许输出**增大**（但峰值、损耗、DCM 风险也增大） | 按限流式算出的允许输出**减小** |
| 手册依据 | SLVSF14B Eq.1，§7.3.4 明确 valley sensing | SLVA372D Eq.3；只适用于限流点为峰值的器件 |

**TPS61023 的归属：** SLVSF14B §7.3.4 原文明确：

> “The TPS61023 uses a valley current limit sensing scheme. Current limit detection occurs during the off-time by sensing of the voltage drop across the synchronous rectifier.”

§7.4.1 也说明电感电流降到误差放大器设定的 valley threshold 时开始下一个开关周期。因此 TPS61023 必须用 **加** 半纹波的 Eq.1，不能套 SLVA372D Eq.3 的 **减** 半纹波形式。

**一个容易混淆的点：** 谷值限流下，`ISW` 的峰值可以高于 `ILIM`。例如本算例在限流边界处谷值 2.7 A、峰值 4.04 A。不能因为“峰值 4.04 A > ILIM 2.7 A”就判定触发限流；限流判据是**谷值**，不是峰值。反过来，峰值限流器件在限流边界处谷值低于 `ILIM`。

## 8. 旧式 `ILIM·(1−D) − ΔIL/2` 为什么错

### 8.1 历史原始回答（保留，不修改）

修复前底稿 `C:\Users\jlc\work\hds-common-scratch\groups\g-power-conversion\03-boost.md` 的“参数与算例”原文：

```text
条件：3.3 V±5%（3.135–3.465 V）→5 V/0.5 A，L=1 µH，fS=1 MHz，η=0.9，ILIM(min)=2.7 A。

- D = 1 − 3.135×0.9/5 = 0.4357；IIN = 0.5/(1−0.4357) = 0.886 A。
- ΔIL = 3.135×0.4357/(1 MHz×1 µH) = 1.366 A；ISW(max)=0.886+0.683=1.569 A。
- IMAXOUT = 2.7×(1−0.4357) − 0.683 = 1.524−0.683 = 0.841 A，大于 0.5 A，余量 68%。
```

这段保留了原始错误结论：`0.841 A`、`余量 68%`。修复后的快照在 `g-power-conversion.md` 第 344 行把旧式明确标为反例：“把谷值限流当峰值并漏乘半纹波的 (1−D)，低估约 56%，不能再用。”

### 8.2 两个独立错误

正确谷值式（SLVSF14B Eq.1）：

```text
IOUT(LC) = (1−D)·ILIM + (1−D)·ΔIL/2
```

旧式：

```text
旧式 = (1−D)·ILIM − ΔIL/2
```

**错误 1：符号/限流类型错。** TPS61023 是谷值限流，限流时 `IL,avg = ILIM + ΔIL/2`；旧式却减去半纹波，等于把 `ILIM` 当成峰值。仅这一项就少算

```text
(1−D)·ΔIL/2 + (1−D)·ΔIL/2 = (1−D)·ΔIL
```

在 3.135 V 下为 `0.5643 × 1.36592 = 0.77079 A`。

**错误 2：半纹波没有乘 `(1−D)`。** 输出平均电流是 `(1−D)` 乘以整个电感平均电流；半纹波属于电感平均电流的一部分，必须一起乘 `(1−D)`。旧式把 `ΔIL/2` 留在括号外，相当于在输出侧直接减电感纹波，量纲上虽是 A，物理上不是输出平均电流。即使退一步按峰值限流，正确也应是

```text
(1−D)(ILIM − ΔIL/2) = (1−D)ILIM − (1−D)ΔIL/2
```

旧式多减了 `D·ΔIL/2`。在 3.135 V 下为 `0.4357 × 0.68296 = 0.29757 A`。

**总差：**

```text
正确 − 旧式 = (2−D)·ΔIL/2
             = (2 − 0.4357) × 0.68296
             = 1.5643 × 0.68296
             = 1.06835 A
0.84065 + 1.06835 = 1.90900 A
```

与 §6 的结果吻合。错误 1 贡献 0.77079 A，错误 2 贡献 0.29757 A，合计 1.06836 A。

### 8.3 数值后果

- 3.135 V：旧式 `0.8407 A` vs 正确 `1.9090 A`；旧式/正确 = **44.0%**，即低估 **56.0%**。
- 3.3 V：旧式 `0.9339 A` vs 正确 `2.0017 A`；旧式/正确 = **46.7%**，即低估 **53.3%**。
- 即使把 TPS61023 假设成峰值限流，正确的峰值式在 3.135 V 下为 `0.5643×(2.7−0.68296)=1.1382 A`；旧式 `0.8407 A` 仍比它低 **26.1%**。这说明旧式不只是“选了另一种限流定义”，而是代数上也错了。
- 错误方向是**悲观**：旧式会低估可输出电流，可能导致过度选型或错误淘汰本来够用的器件（例如仓库 p03 中 12 V/0.4 A 算例的 2.5 A 限流器件）。它不是“安全保守”，而是一个物理上不对的量。

## 9. 修改前后结果对照

| 项目 | 修复前（旧式，3.135 V） | 修复后（谷值式，3.135 V） | 修复后（字面 3.3 V） |
|---|---:|---:|---:|
| `D` | 0.4357 | 0.4357 | 0.4060 |
| `ΔIL(P-P)` | 1.366 A | 1.366 A | 1.340 A |
| `ISW(max)` @ `IOUT=0.5 A` | 1.569 A | 1.569 A | 1.512 A |
| `IOUT(LC)` | **0.841 A** | **1.909 A** | **2.002 A** |
| 相对 0.5 A 余量 | 68.1% | 281.8% | 300.3% |
| 结论 | 通过，但余量被严重低估 | 通过，余量 282% | 通过，余量 300% |

补充：

- 若误用 **typ 3.7 A** 代替 min 2.7 A：3.135 V 下 `0.5643×(3.7+0.68296)=2.473 A`，比 min 结果高 **29.6%**；3.3 V 下 `0.5940×(3.7+0.6699)=2.596 A`，高 **29.7%**。typ 只能用于初选，不能用于最坏样片保证。
- 旧式与正确值的差异不是“四舍五入”：3.135 V 差 1.068 A，远超任何舍入误差。

## 10. 结果边界与未核实事项

### 10.1 `IOUT(LC)` 是限流上限，不是连续输出额定

`2.002 A`（3.3 V）/ `1.909 A`（3.135 V）是“进入限流之前”的电流上限。实际连续输出还受热、输入源、电感饱和、DCM/PFM、最小占空比/关断时间等限制。按总损耗和 θJA 做的粗略热估算（仅作上限，未拆分芯片/电感损耗）：

- 0.5 A：`POUT=2.5 W`，`PIN=2.5/0.9=2.778 W`，总损耗 0.278 W；标准板 θJA 142.7 °C/W → ΔT≈39.6 °C；`TA=50 °C` 时 `TJ≈89.6 °C`。
- 1.0 A：总损耗 0.556 W → ΔT≈79.3 °C；`TA=50 °C` 时 `TJ≈129.3 °C`，已超过 125 °C（标准板）。
- 2.0 A：总损耗 1.111 W → ΔT≈158.6 °C；即使 `TA=25 °C` 也远超 125 °C。EVM 板 θJA 91.4 °C/W 也只能把 2 A 的 ΔT 降到约 101.5 °C，`TA=50 °C` 时仍约 151.5 °C。

因此：**不能把 2.002 A 当作“这颗芯片在 3.3 V→5 V 能连续出 2 A”的依据。** 热和输入源很可能远在限流之前成为瓶颈。实际连续电流需要按具体板、气流、环境温度和损耗拆分做热实测。

### 10.2 输入源

- 0.5 A 输出：输入功率 2.778 W，3.3 V 侧电流约 **0.842 A**。
- 限流边界 2.002 A 输出：输入功率 11.12 W，3.3 V 侧电流约 **3.37 A**。
如果 3.3 V 源不能提供这些电流，源会先塌陷/限流，芯片限流公式给出的上限没有实际意义。

### 10.3 电感容差、饱和与 DCM

- 任务给的是理想 1 µH。手册 §8.2.2.2 建议按 −30% 电感容差做最坏情况计算。
- `L=1 µH` 时 `ΔIL/IL(DC)=159%`，远高于手册 <40% 的建议；0.5 A 工作点谷值仅 0.172 A，DCM 边界 0.398 A。
- `L=0.7 µH`（−30%）时 `ΔIL=1.914 A`，DCM 边界 0.5685 A > 0.5 A，**0.5 A 工作点会进入 DCM**；虽然限流边界（平均 3.66 A、谷值 2.7 A）仍在 CCM，但 0.5 A 附近的模式/纹波/效率需要实测。
- `L=1.3 µH`（+30%）时 `ΔIL=1.031 A`，按 Eq.1 的 `IOUT(LC)=0.5940×(2.7+0.515)=1.910 A`；可见限流上限对电感容差也有几个百分点的敏感度。
- 限流边界处峰值约 4.04 A（3.3 V）/4.07 A（3.135 V）。电感饱和电流应按“变换器可能看到的最高峰值”（含启动/瞬态/限流）取，而不是只按 0.5 A 工作点的 1.512 A。Table 8-2 的 1 µH 推荐料（XEL4030-102ME、74438357010）饱和电流为 9.0/9.6 A，能覆盖 4.04 A；但实际选料未核对。

### 10.4 其他边界

- `5 V` 输出与 OVP min `5.5 V`（§6.5）之间只有 0.5 V 裕量；本次未分析反馈容差/OVP 误触发，标为 **待核实**。
- 0.5 A 时是否处于 PWM（而非 PFM）未由手册给出明确负载门限；本次按 PWM/CCM 计算，标为 **假设**。
- `tON=406 ns`、`tOFF=594 ns` 均大于手册最小值，开关时间不是限制；但这是按 `fSW=1 MHz` 典型值算的，fSW 的 min/max 未给出。

### 10.5 仍未核实清单

1. **TPS61023 在 `VIN=3.3 V` 下的实际谷值限流**：手册 min 2.7 A 的测试条件是 3.6 V/5 V；3.3 V 下是否仍为 2.7 A，未读到数据。
2. **`fSW` 的 min/max**：手册只给 typ 1.0 MHz；`ΔIL` 的最坏情况无法按 min fSW 复算。
3. **`η=0.9` 的真实性**：手册只建议“most applications use 90%”，3.3 V/0.5 A 的实际效率曲线未数字化读取。
4. **电感容差/饱和/DCR**：1 µH 理想值；−30% 时 0.5 A 工作点进 DCM；实际料号未选。
5. **热连续电流**：2.002 A 是限流上限，不是热额定；未做损耗拆分、板级 θJA、气流和温升实测。
6. **CCM/PWM 假设**：159% 纹波、DCM 边界 0.398 A；0.5 A 附近模式与稳定性未实测。
7. **输入源能力**：0.5 A 时 0.842 A、限流边界 3.37 A；源是否能提供未核实。
8. **限流边界峰值 4.04 A 的瞬态/启动行为**：电感饱和、软启动、负载阶跃未实测。
9. **OVP 裕量**：5 V 输出对 OVP min 5.5 V，反馈容差未分析。
10. **Eq.3/5/6/7 的页面图像核对**：仅 Eq.1/Eq.2 做了 p.9 图像目视核对；其余为同一 PDF 的文本提取。
11. **TPS63802 相关残留**：见 §11.3，本次未修正、未重算。

## 11. 仓库一致性检查与残留问题

### 11.1 已修正且一致的部分

在 `4c9db61` 快照中：

- `design-hardware/references/design-cards/power/p03-boost.md` §4 第 5 步、§5 第 5 步、§12 均已使用谷值式 `(1−D)(ILIM+ΔIL/2)`，并明确峰值式 `(1−D)(ILIM−ΔIL/2)` 不能混用。
- `design-hardware/references/common-hardware/g-power-conversion.md` G3 Boost 的结论、算例与“常见误判”均已改为 1.909 A，并把 0.841 A 标为旧式反例。
- `design-hardware/references/calculations/power-thermal.md` §3.3 的 Boost 行正确区分了谷值/峰值；Buck 行的 `IMAXOUT = ILIM(min) − ΔIL/2` 对 Buck 是正确的（Buck 的输出电流就是电感平均电流，没有 `(1−D)` 因子）。
- 全库搜索发现：`g-power-conversion.md` 第 344 行把旧式作为**反例**保留，这是正确的；但 `docs/evidence/common-hardware-2026-10-22/audit/g-converters.md` 第 123 行仍把 p03 的 Boost 限流写成旧式 `IMAXOUT=ILIM(min)(1−D)−ΔIL/2`，与当前 p03 的谷值式不一致。见 §11.3 第 1 条。

### 11.2 来源登记的追溯缺口

`source-register.md` 的 CHW-S123 行记录的“实际查阅范围”是“第 1–6 页；§5 引脚、§6.1–§6.5、§6.6 开关特性；未读 §8–§12”。但本次引用的 **Equation 1 在 p.9 §7.3.4**，Equation 5–7 在 p.13–14 §8.2.2.2，均不在该登记范围内。也就是说：**公式本身有原厂手册依据，但仓库的来源登记没有记录到 Eq.1 所在的 §7.3.4 页面。** 这是证据追溯的缺口，不是计算错误。建议（不在本任务修改仓库）把 `§7.3.4（p.9–10，Eq.1–3）` 和 `§8.2.2.2（p.13–14，Eq.5–7）` 补进 CHW-S123 的“实际查阅范围”。

### 11.3 发现的相关残留（未修改，供主流程处置）

1. **`docs/evidence/common-hardware-2026-10-22/audit/g-converters.md` 第 123 行**仍把 p03 的 Boost 限流描述为旧式：

   ```text
   IMAXOUT=ILIM(min)(1−D)−ΔIL/2
   ```

   当前 `p03-boost.md` §4/§5 已改为谷值式 `(1−D)(ILIM+ΔIL/2)`。这条记录出现在审计证据文件中，可能是修复前审计快照的历史描述；如果它被当作“现有内容索引”，就是过时的；如果它是历史证据，建议保留原文并明确标注“修复前/已被后续提交修正”，避免读者把它当成现行公式。本次未修改仓库，建议主流程决定处理方式。

2. **`g-power-conversion.md` TPS63802 Boost 峰值限流算例**（约第 466 行）：

   ```text
   IMAXOUT = 4 × 0.8182 − 0.249 = 3.02 A
   ```

   峰值限流的正确形式是 `(1−D)(ILIM − ΔIL/2)`：

   ```text
   0.8182 × (4 − 0.249) = 0.8182 × 3.751 = 3.069 A
   ```

   两者差约 1.7%。虽然结论“远大于 1 A”不变，但这是和本次旧式同类的代数错误（半纹波没有乘 `(1−D)`）。

   同一算例还有一个独立的不一致：它写 `D=(3.3−2.7)/3.3=0.1818`，但同一段又用 `η=0.9` 算 `IIN=1/(0.9×0.8182)=1.358 A`。若按 SLVSF14B/SLVA372D 的 `D=1−VIN·η/VOUT`，`D=1−2.7×0.9/3.3=0.2636`，`ΔIL` 会从 `0.497 A` 变为约 `0.721 A`，峰值从 `1.607 A` 变为约 `1.718 A`；再按峰值限流式 `(1−D)(ILIM−ΔIL/2)`，`IMAXOUT` 会从 `3.02 A` 降到约 `2.68 A`（`0.7364×(4−0.3606)=2.680 A`）。这属于 TPS63802 算例的独立问题，不在本次 TPS61023 复核范围，但建议主流程单独核对/修正；本次没有改仓库。

3. **`power-thermal.md` §4.3 的“芯片带载”快速判据**：

   ```text
   ILIM(min) − ΔIL/2 ≥ IOUT(max)
   ```

   这是 **Buck** 的判据（Buck 输出电流等于电感平均电流）。如果读者把它套到 Boost，会漏掉 `(1−D)` 和谷值/峰值符号。§3.3 的表已经正确区分，但 §4.3 的快速判据没有标明“仅 Buck”，建议在主流程中加限定或分拓扑列出。本次未修改。

### 11.4 快照完整性结论

- 本次引用的 Boost 文件内容与 `4c9db61` 一致（`git diff 4c9db61 -- <boost files>` 为空）。
- HEAD 在复核期间被其他会话推进，但不影响上述 Boost 文件的快照内容；报告中的数字均已按 `git show 4c9db61:<file>` 的关键行复核。
- 没有修改仓库文件；所有写入都在 `C:\Users\jlc\work\hds-common-scratch\rerun\` 下。

## 12. 来源与哈希

### 12.1 原厂文档

| 文档 | 版本/日期 | 本次实际使用的小节/式号 | 文件/哈希 |
|---|---|---|---|
| TI TPS61023 datasheet | **SLVSF14B**，2019-09，Rev. August 2020，28 页 | p.1 Features；§6.3（L/C 范围）；§6.4（θJA）；§6.5（ILIM_SW、fSW、tON/tOFF、VREF、OVP）；§7.3.3；§7.3.4（Eq.1–3，p.9–10）；§7.4.1；§8.2.2.2（Eq.5–7，p.13–14）；Table 8-2 | `C:\Users\jlc\work\hds-common-scratch\ds-power\tps61023.pdf`；SHA256 `c4e3f2db65f6b1e623ee089b59299c630e4f4be53e4381500cb370568d75080f` |
| TI SLVA372D《Basic Calculation of a Boost Converter's Power Stage》 | **SLVA372D**，2009-11，Revised November 2022，10 页 | §2（Eq.1–4，p.2–3）：D、ΔIL、峰值限流 `IMAXOUT`、开关峰值 `ISW(max)` | `C:\Users\jlc\work\hds-common-scratch\rerun\slva372d.pdf`；SHA256 `27f8a71623f240dfb3515c26107f201f7410ad3998461f921f6b392478465b36` |

原厂 URL（本次下载/核对）：

- TPS61023: `https://www.ti.com/lit/ds/symlink/tps61023.pdf`
- SLVA372D: `https://www.ti.com/lit/pdf/slva372`

### 12.2 仓库文件（快照 `4c9db61`）

- `C:\Users\jlc\work\EasyCirq\design-hardware\references\design-cards\power\p03-boost.md`
- `C:\Users\jlc\work\EasyCirq\design-hardware\references\common-hardware\g-power-conversion.md`
- `C:\Users\jlc\work\EasyCirq\design-hardware\references\calculations\power-thermal.md`
- `C:\Users\jlc\work\EasyCirq\design-hardware\references\source-register.md`
- `C:\Users\jlc\work\EasyCirq\docs\evidence\common-hardware-2026-10-22\audit\g-converters.md`

### 12.3 历史底稿与中间文件（scratch，非仓库）

- `C:\Users\jlc\work\hds-common-scratch\groups\g-power-conversion\03-boost.md`（修复前原始回答）
- `C:\Users\jlc\work\hds-common-scratch\ds-power\tps61023.txt`（SLVSF14B 文本提取）
- `C:\Users\jlc\work\hds-common-scratch\tps61023-p9.png`（p.9 图像）
- `C:\Users\jlc\work\hds-common-scratch\rerun\tps61023-layout.txt`（带布局的文本提取）
- `C:\Users\jlc\work\hds-common-scratch\rerun\slva372d.txt`（SLVA372D 文本提取）

---

**一句话总结：** 按 TPS61023 的谷值限流式 `IOUT(LC)=(1−D)(ILIM+ΔIL/2)`，字面 3.3 V 条件给出 `D=0.4060`、`ΔIL=1.340 A`、0.5 A 时开关峰值 `1.512 A`、限流上限 `2.002 A`；按仓库 3.3 V±5% 的 `VIN(min)=3.135 V` 给出 `D=0.4357`、`ΔIL=1.366 A`、峰值 `1.569 A`、限流上限 `1.909 A`。旧式 `ILIM(1−D)−ΔIL/2` 在 3.135 V 下只有 `0.841 A`，低估 56.0%，原因是符号（谷值当峰值）和代数（半纹波漏乘 `(1−D)`）两项错误。2.002 A/1.909 A 只是限流上限，不是连续输出额定；热、输入源、电感容差与 DCM 边界仍需实测/核实。
