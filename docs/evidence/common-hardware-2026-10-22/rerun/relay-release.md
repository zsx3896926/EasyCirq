# 12 V 继电器释放时间复核（仓库快照 4c9db61）

> 任务：12 V 继电器线圈 `R=400 Ω`、`L=0.5 H`，用 1N4148 仅续流，继电器机械释放时间 max 5 ms，系统要求 5 ms 内释放。求线圈电流到零时间、系统总释放时间，判断 5 ms 目标是否可达；再算二极管 + 24 V 稳压管的线圈时间与系统总时间。
>
> 复核对象：`C:\Users\jlc\work\hardware-design-skill`，固定提交 `4c9db61`（`fix(common-hardware): correct five audited engineering conclusions`）。本次没有修改仓库文件。
>
> 快照完整性说明：运行期间仓库 HEAD 因其他会话推进到 `662a7ab`（其间新增 `d97b6f3`、`662a7ab`）。已用 `git diff 4c9db61..HEAD` 核对：继电器相关文件（`d03-relay.md`、应用 09/06、E1、F14、`docs/common-hardware-report.md`、`docs/common-hardware-gap-analysis.md`）无差异；`k-drive.md` 仅风扇 tach 一行变化，继电器 K3 段落未变。因此本文引用的继电器内容与 `4c9db61` 一致。
>
> 写作期间工作树还出现了其他会话对继电器相关文件的**未提交修改**（`d03-relay.md`、`k-drive.md`、F14、`docs/common-hardware-report.md`、`docs/common-hardware-gap-analysis.md` 等，内容与本文建议方向一致，像是在同步同一批结论）。这些修改不是本次任务做的；本文的“残留不一致”判断以 `4c9db61` 快照为准，不评价未提交工作树。

## 0. 结论摘要

| 方案 | 线圈电流到零时间（恒压模型） | 系统总释放时间（按“线圈到零 + 机械 5 ms”相加） | 5 ms 目标 |
|---|---|---|---|
| 仅 1N4148 续流，`V_F=0.7 V` | `3.62 ms` | `8.62 ms`（约 8.6 ms） | 不可达；差 3.62 ms |
| 1N4148 + 24 V 稳压管，`V_rev=24.7 V` | `0.495 ms`（约 0.50 ms） | `5.495 ms`（约 5.5 ms） | 仍不可达；差 0.50 ms |

- **计算本身正确**：`τ=L/R=1.25 ms`，`I0=12 V/400 Ω=30 mA`，`t=τ·ln(1+I0·R/V_rev)`；仅二极管 `3.6228 ms`，二极管+24 V 稳压管 `0.4950 ms`。仓库 `k-drive.md`、`d03-relay.md`、应用 09 的 0.5 H/400 Ω 数值与此一致；应用 06 是 5 V/70 Ω 的另一组假设，采用同一口径但数值不同。
- **5 ms 不可达的结论正确，但理由要写准**：G5LE 数据手册的 `5 ms max` 是 **release/dropout time（线圈断电到 NC 触点闭合，23 °C，不含弹跳）**，不是纯机械时间。把 `3.62 ms` 与 `5 ms` 直接相加得到 `8.62 ms` 是**保守上限**，因为数据手册的 5 ms 已经包含测试电路中的一段线圈衰减，直接相加会重复计算未知的一部分。精确系统总时间需要知道数据手册的测试电路（是否带续流、驱动方式），该条件在 4 页 G5LE 手册中没有给出 → **待核实**。
- **无论采用哪种解释，5 ms 都不能作为“保证值”**：继电器自身的最大释放时间已经等于 5 ms，没有任何余量；任何续流/钳位网络只会让线圈衰减比无抑制更慢。要保证 5 ms 内释放，必须选 `release time max` 更小的继电器（按相加模型：仅二极管需 ≤1.38 ms；二极管+24 V 稳压管需 ≤4.50 ms），或把要求放宽到 ≥8.6 ms / ≥5.5 ms，或改用典型值/实测值验收（不能作为保证）。
- **历史原始回答保留情况**：旧答案“仅二极管 21.4 ms，淘汰”和“0.607 ms”仍保留在审计/缺口文档中；`docs/common-hardware-report.md:80` 仍有一句旧结论“3.62 ms（满足 5 ms）”，与 4c9db61 修正后的快照矛盾，属于**未同步的残留**（详见 §8.2）。

## 1. 实际读过的文件/小节

### 1.1 仓库文件（快照 4c9db61）

- `C:\Users\jlc\work\hardware-design-skill\design-hardware\references\common-hardware\k-drive.md`
  - K3 继电器 §必查参数（约 L220）：G5LE-1 动作 10 ms max、释放 5 ms max；
  - K3 §参数与算例（L228–232）：`L=0.5 H`、`R=400 Ω`、`I0=30 mA`、`V_F=0.7 V`，`τ=1.25 ms`，仅二极管 `3.62 ms`，二极管+24 V 稳压管 `0.50 ms`；
  - K3 §验证（L256）：“释放时间=线圈衰减+机械释放”；
  - K3 §来源与证据（L274、L814，CHW-S200）；
  - K3 §需要同步修正（L836–839，第 1–5 条与继电器相关项）。
- `C:\Users\jlc\work\hardware-design-skill\design-hardware\references\design-cards\drive\d03-relay.md`
  - §4 第 2 步（L109）：RL 解公式与 `V_rev` 定义；
  - §5 完整算例（L132–149）：给定条件、仅二极管、二极管+24 V 稳压管、`V_DS` 与稳压管功率；
  - §5 候选选择/结论（L165–174）；
  - §12 来源（L267–269，DRV-S04/DRV-S10）。
- `C:\Users\jlc\work\hardware-design-skill\design-hardware\references\engineering-deepdives\topics\e1-inductive-load-energy-path.md`
  - §2.2（L95–111）：`L·ΔI/V` 线性式为什么在仅二极管时严重高估，RL 解与“到 zero / 到 must-release”的区别；
  - §5.1（L260–271）：钳位方案表与“释放不是电流到零”；
  - §6.1（L299–351）：12 V/100 mA 构造算例的完整代入。
- `C:\Users\jlc\work\hardware-design-skill\design-hardware\references\failures\f14-relay-flyback.md`
  - L46：仍建议用 `Δt ≈ L × ΔI / V`（忽略线圈电阻）比较钳位方式（本次发现的残留不一致，见 §8.2）。
- `C:\Users\jlc\work\hardware-design-skill\design-hardware\references\common-hardware\applications\09-timer-control.md`
  - L81：同一 0.5 H/400 Ω 算例，`3.62 ms`、`0.50 ms`、加机械 5 ms 后 `8.6 ms`/`5.5 ms`。
- `C:\Users\jlc\work\hardware-design-skill\design-hardware\references\common-hardware\applications\06-water-level-alarm.md`
  - L100：5 V/70 Ω、`L=0.5 H` 的释放时间算例，同样采用“线圈衰减 + 机械 5 ms”口径。
- `C:\Users\jlc\work\hardware-design-skill\design-hardware\references\source-register.md`
  - L301：CHW-S200，Omron G5LE，Cat. No. K100-E1-08，4 页，注明“线圈电阻/must-operate 未在本 4 页摘要中给出”。
- `C:\Users\jlc\work\hardware-design-skill\design-hardware\references\common-hardware\README.md`
  - L11：证据等级定义（E1 本次核对原厂资料；E2 通用方法/具体值待核；E3 离线分析/推断）。
- `C:\Users\jlc\work\hardware-design-skill\docs\common-hardware-report.md`
  - L80：旧结论“D03 仅二极管 3.62 ms（满足 5 ms，旧结论‘淘汰’不成立）”（未同步，见 §8.2）。
- `C:\Users\jlc\work\hardware-design-skill\docs\common-hardware-gap-analysis.md`
  - L465–466：C13/C14，历史缺口记录“仅二极管 21.4 ms 错误；到零约 3.6 ms；按 must-release 重算”。
- `C:\Users\jlc\work\hardware-design-skill\docs\evidence\common-hardware-2026-10-22\audit\k-drive.md`
  - L164–165、L521–522：审计保留的原始错误（21.4 ms、0.607 ms）与 RL 修正说明。

### 1.2 原厂资料（本次下载并实际读取）

- **Omron G5LE PCB Power Relay datasheet**，Cat. No. K100-E1-08，0318(0207)(O)，4 页，URL `https://omronfs.omron.com/en_US/ecb/products/pdf/en-g5le.pdf`。
  - p.1：G5LE-1 有 5/12/24 VDC 线圈档；
  - p.2 Characteristics：`Operate time 10 ms max.`、`Release time 5 ms max.`（标准型）；注“initial values”；
  - p.2 注 1–3 只给接触电阻、绝缘电阻、失效率的测量条件，**没有给动作/释放时间的测试电路**。
- **Omron General Information**，Cat. No. JB301-E3-01 3/05（DigiKey 镜像 `https://media.digikey.com/pdf/Other%20Related%20Documents/Omron%20Other%20Doc/Relay%20Technical%20Pages.pdf`）。
  - PDF 第 7 页：`Dropout time` 定义：“The time that elapses between the moment a relay coil is de-energized until the NC contacts have closed, at an ambient temperature of 23°C. ... Bounce time is not included.” 同页给出通用示例“Dropout time 5 ms max. (mean value: approx. 2.3 ms)”（**这是通用示例，不是 G5LE 的保证值/典型值**）。
  - PDF 第 3 页：`Relays with a diode connected in parallel with the relay coil tend to experience increased release times.` 即“并二极管会增加释放时间”，与本次方向一致。
- **Vishay 1N4148 datasheet**，Rev. 1.6，07-Nov-2024，Document Number 81857，URL `https://www.vishay.com/docs/81857/1n4148.pdf`。
  - p.2 Electrical Characteristics：`Forward voltage, IF = 10 mA, VF max. 1 V`（Tamb=25 °C）；该表只给 10 mA 的 max，没有 30 mA 的保证值；
  - p.2 Fig.1 Typical Forward Voltage vs Junction Temperature：25 °C、`IF=10 mA` 典型约 0.72 V；`IF=100 mA` 约 0.84 V；`IF=1 mA` 约 0.62 V；
  - p.2 Fig.2 Typical Forward Current vs Forward Voltage：25 °C、30 mA 对应约 0.75–0.8 V（图读值，非表格保证值）。

## 2. 已知条件与数值分类

| 量 | 取值 | 分类 | 依据/说明 |
|---|---|---|---|
| `V_coil` | 12 V | 给定/额定 | 任务给定；G5LE-1 有 12 VDC 档（CHW-S200 p.1） |
| `R_coil` | 400 Ω | 给定/假设 | 任务给定；4 页 G5LE 手册没有线圈电阻表，`400 Ω` 不能从该手册核实 → **待核实** |
| `L` | 0.5 H | **假设值** | 仓库 `d03-relay.md:132` 明确写“算例假设”；不是 G5LE 数据手册保证值 → **待核实**（需实测） |
| `I0` | 30 mA | 推导值 | `I0=12 V/400 Ω=0.030 A`；假设线圈已达稳态、`R` 为 25 °C 附近的值 |
| `V_F`（1N4148） | 0.7 V | **典型假设** | Vishay 手册只保证 `10 mA` 时 `VF ≤1.0 V`；25 °C、10 mA 典型约 0.72 V；30 mA 图读约 0.75–0.8 V。`0.7 V` 是便于复算的典型假设，不是 30 mA 的保证值 |
| `V_Z`（稳压管） | 24 V | 给定/假设 | 任务给定“24 V 稳压管”；实际稳压值有容差、动态电阻，且随电流下降而下降 → **待核实** |
| `V_rev`（二极管+稳压管） | 24.7 V | 推导/假设 | `V_Z + V_F = 24 + 0.7`；恒压模型 |
| 继电器释放时间 | 5 ms max | **保证值（max）** | Omron G5LE p.2 `Release time 5 ms max.`；但它是 dropout time（线圈断电→NC 触点闭合），不是纯机械时间；测试电路未给 → 定义/条件**待核实** |
| 系统要求 | 5 ms | 给定 | 任务给定；本文按“线圈断电到触点释放”理解 |

## 3. 模型与公式

### 3.1 电路模型

低侧 N-MOS 关断后，线圈 `L` 与线圈电阻 `R` 串联，经续流二极管（或二极管+稳压管）形成闭合回路。取线圈电流正方向为关断前的方向，忽略二极管反向恢复、线圈寄生电容和开关管漏电，KVL 为：

```text
L·di/dt + R·i + V_rev = 0,   i(0) = I0
```

其中 `V_rev` 是钳位器件在线圈两端建立的反压（**不含**电源电压 `V_coil`）：

- 仅续流二极管：`V_rev ≈ V_F`；
- 二极管 + 稳压管串联：`V_rev ≈ V_Z + V_F`。

### 3.2 解与到零时间

```text
i(t) = (I0 + V_rev/R)·e^(−t/τ) − V_rev/R,   τ = L/R
```

令 `i(t)=0`：

```text
(I0 + V_rev/R)·e^(−t/τ) = V_rev/R
e^(t/τ) = 1 + I0·R/V_rev
t_off = τ·ln(1 + I0·R/V_rev)
```

### 3.3 模型边界（重要）

1. **“到零”是恒压模型的数学零点，不是物理上的硬零。** 真实二极管的 `V_F` 随电流减小而下降，接近零时 `V_rev→0`，电流按 `τ=L/R` 渐近衰减，严格说没有有限时间到达绝对零。`3.62 ms` 是“把 `V_F` 固定为 0.7 V”外推出来的零点；继电器实际在 **must-release 电流**（远大于零）就释放，时间比“到零”短。仓库 E1 §2.2 也明确说“释放不是电流到零”。
2. **系统总时间应优先用数据手册的 end-to-end release/dropout time。** Omron 的定义是“线圈断电→NC 触点闭合，23 °C，不含弹跳”，已经把测试电路中的线圈衰减包含在内。若再用“线圈到零 + 机械释放”相加，只有在 5 ms 被解释为“纯机械时间”时才严格成立；否则是保守上限。
3. 线圈 `R` 随温度上升：铜线圈升温后 `R` 增大、`I0` 减小、`τ=L/R` 减小；在 `I0·R ≈ V_coil` 近似不变时，`t_off` 会略减小。本文按 25 °C、`R=400 Ω` 计算；热态需按实际 `R(T)` 复算。

## 4. 计算一：仅 1N4148 续流

给定：`L=0.5 H`、`R=400 Ω`、`V_coil=12 V`、`V_F=0.7 V`。

### 4.1 稳态电流与时间常数

```text
I0 = V_coil / R = 12 V / 400 Ω = 0.030 A = 30 mA
τ = L / R = 0.5 H / 400 Ω = 1.25×10⁻³ s = 1.25 ms
I0·R = 0.030 A × 400 Ω = 12 V
```

### 4.2 线圈电流到零时间

```text
t_off = τ·ln(1 + I0·R/V_F)
      = 1.25 ms × ln(1 + 12 V / 0.7 V)
      = 1.25 ms × ln(18.142857)
      = 1.25 ms × 2.898276
      = 3.6228 ms
      ≈ 3.62 ms
```

### 4.3 系统总释放时间（按“线圈到零 + 机械 5 ms”）

```text
t_system = t_off + t_release,max
         = 3.62 ms + 5 ms
         = 8.62 ms
         ≈ 8.6 ms
```

- 对 5 ms 目标的余量：`5 − 8.62 = −3.62 ms`（不满足）。
- 即使只看线圈：`5 − 3.62 = 1.38 ms`，留给“机械释放”的预算只有 1.38 ms，小于 5 ms max。
- `V_DS,peak = V_coil + V_F = 12 + 0.7 = 12.7 V`；30 V 级 MOSFET 可覆盖（考虑 12 V +10% 与布线过冲仍建议留余量）。

## 5. 计算二：1N4148 + 24 V 稳压管

给定：`V_Z=24 V`、`V_F=0.7 V`，串联后 `V_rev = V_Z + V_F = 24.7 V`。

### 5.1 线圈电流到零时间

```text
t_off = τ·ln(1 + I0·R/V_rev)
      = 1.25 ms × ln(1 + 12 V / 24.7 V)
      = 1.25 ms × ln(1.485830)
      = 1.25 ms × 0.396025
      = 0.4950 ms
      ≈ 0.495 ms（约 0.50 ms）
```

### 5.2 系统总释放时间（按“线圈到零 + 机械 5 ms”）

```text
t_system = 0.495 ms + 5 ms = 5.495 ms ≈ 5.5 ms
```

- 对 5 ms 目标的余量：`5 − 5.495 = −0.495 ms`（不满足；差约 0.5 ms）。
- `V_DS,peak = 12 + 24.7 = 36.7 V`；30 V 级 MOSFET 余量不足，需 60 V 级并核对重复关断 SOA/雪崩。
- 稳压管峰值功率约 `24.7 V × 0.030 A = 0.741 W`；单次储能 `½LI0² = 0.5 × 0.5 H × (0.030 A)² = 0.225 mJ`。1 W 稳压管要查脉冲额定，不能只按连续 1 W 放行。

## 6. 5 ms 目标是否可达

### 6.1 按任务口径（5 ms 为纯机械释放时间）

- 仅二极管：`3.62 + 5 = 8.62 ms`，**不可达**，差 3.62 ms。
- 二极管+24 V 稳压管：`0.495 + 5 = 5.495 ms`，**仍不可达**，差约 0.50 ms。
- 要在该口径下满足 5 ms，继电器 `release time max` 必须满足 `t_release,max ≤ 5 − t_off`：
  - 仅二极管：`≤1.38 ms`（若按 `V_F=1.0 V` 的线圈时间 3.21 ms，则 `≤1.79 ms`）；
  - 二极管+24 V 稳压管：`≤4.50 ms`。
  G5LE 的 5 ms max 在两种方案下都不满足；稳压管方案只差 0.5 ms，换一颗 release max ≤4.5 ms 的继电器即可，但必须用该型号的保证值，不能用典型值。

### 6.2 按 Omron 数据手册口径（5 ms 为 end-to-end dropout time）

- `5 ms max` 已经是从线圈断电到 NC 触点闭合的最大值，包含测试电路中的线圈衰减；它不是“纯机械 5 ms”。
- 因此 `8.62 ms`/`5.50 ms` 是**保守上限**，不是数据手册意义下的精确总时间。精确值取决于数据手册的测试电路（是否带续流、驱动管类型、线圈电压/温度）；4 页 G5LE 手册没有给出该条件 → **待核实**。
- 若数据手册测试为“无抑制”（Omron 明确说并二极管会增加释放时间，通常额定值按无抑制测），则加续流后的最大释放时间 = `5 ms + (t_suppressed − t_unsuppressed)`。`t_unsuppressed` 未知但很小，所以实际值落在 `5 ms` 与 `8.62 ms`（仅二极管）/`5.50 ms`（稳压管）之间。由于 `t_suppressed > t_unsuppressed`，**最大释放时间严格大于 5 ms**；5 ms 不能作为保证值。
- 最有利的解释（若 5 ms 已包含与本次完全相同的续流网络）下，总时间就是 `5 ms max`，与目标相等、余量为 0；这仍然不构成“5 ms 内保证释放”，只是“最大恰好 5 ms”。而且 G5LE 手册没有声明该测试条件，不能采用这个最有利解释。
- 若系统要求的 5 ms 是从“线圈电流已经到零”之后才开始计时，则机械部分 `5 ms max` 恰好等于要求、余量为 0；但任务问的是“系统总释放时间”，通常从线圈断电算起，本文按后者理解。计时起点不同，结论需重算（见 §9 第 9 项）。

### 6.3 结论

**5 ms 目标不可达/不可保证。** 两种续流方案都无法在“G5LE release max 5 ms”的前提下保证 5 ms 内释放：仅二极管差 3.62 ms，二极管+24 V 稳压管差约 0.50 ms。要达到 5 ms，必须换更快的继电器、放宽系统要求，或把 5 ms 改为典型值/实测统计值（并在样机上用电流探头 + 触点/机械位置实测，不能用计算代替）。

## 7. 敏感性分析（全部为模型计算，不是保证值）

### 7.1 仅二极管：`V_F` 变化

| `V_F` | `t_off` | `t_system`（+5 ms） | 5 ms |
|---|---|---|---|
| 0.70 V（典型假设） | 3.62 ms | 8.62 ms | 不满足 |
| 0.75 V（30 mA 图读附近） | 3.54 ms | 8.54 ms | 不满足 |
| 0.80 V | 3.47 ms | 8.47 ms | 不满足 |
| 1.00 V（Vishay 10 mA max） | 3.21 ms | 8.21 ms | 不满足 |

结论：`V_F` 在 0.7–1.0 V 内变化只让线圈时间变 0.4 ms 左右，**不改变 5 ms 不可达的结论**。

### 7.2 仅二极管：`L` 与热态 `R` 变化

| 条件 | `t_off` | `t_system`（+5 ms） |
|---|---|---|
| `L=0.4 H` | 2.90 ms | 7.90 ms |
| `L=0.5 H`（假设） | 3.62 ms | 8.62 ms |
| `L=0.6 H` | 4.35 ms | 9.35 ms |
| `R=440 Ω`（热态，`I0R≈12 V`） | 3.29 ms | 8.29 ms |
| `R=480 Ω`（热态，`I0R≈12 V`） | 3.02 ms | 8.02 ms |

结论：`L` 是最敏感的未知量；即使 `L` 降到 0.4 H、`R` 升到 480 Ω，系统仍约 7.9–8.0 ms，远大于 5 ms。

### 7.3 二极管+24 V 稳压管：稳压值容差

| `V_Z`（`V_rev=V_Z+0.7`） | `t_off` | `t_system`（+5 ms） |
|---|---|---|
| 22.8 V（−5%） | 0.516 ms | 5.516 ms |
| 24.0 V（标称） | 0.495 ms | 5.495 ms |
| 25.2 V（+5%） | 0.476 ms | 5.476 ms |
| 30.0 V（示例） | 0.412 ms | 5.412 ms |

结论：稳压值在 ±5% 内只让总时间变约 0.04 ms；**5 ms 仍差约 0.4–0.5 ms**。

### 7.4 若按 must-release 电流判释放（假设值，仅作敏感性）

G5LE 的 must-release 电流/电压未在 4 页手册中给出 → **待核实**。下表把 must-release 设为 `I0` 的 10%/30%/50%，仅为说明“到 must-release 比到零早”，**不是 G5LE 的真实值**：

| must-release | 仅二极管 `t` / 系统 | 二极管+24 V 稳压管 `t` / 系统 |
|---|---|---|
| 50%·I0 | 0.80 ms / 5.80 ms | 0.223 ms / 5.223 ms |
| 30%·I0 | 1.35 ms / 6.35 ms | 0.325 ms / 5.325 ms |
| 10%·I0 | 2.37 ms / 7.37 ms | 0.436 ms / 5.436 ms |

结论：即使继电器在 10%·I0 就释放，按“到 must-release + 机械 5 ms”相加，两种方案仍 >5 ms（5.44–7.37 ms）。5 ms 的瓶颈始终是 5 ms max 本身。

## 8. 与仓库现有结论的一致性

### 8.1 一致的部分

- `k-drive.md` K3（L228–232）：`τ=1.25 ms`、仅二极管 `3.62 ms`、二极管+24 V 稳压管 `0.50 ms`，与本次独立计算一致；`3.62/0.50` 的算术正确。
- `d03-relay.md` §5（L143–148）：`3.62 ms`、`0.495 ms`、`8.6 ms`、`5.5 ms` 与本次一致；已把“线圈电流到零”和“系统释放”分开，纠正了旧版“3.62 ms 满足 5 ms”的错误。
- `applications/09-timer-control.md:81` 的 0.5 H/400 Ω 数值（`0.50`、`8.6`、`5.5`）与本次一致；`applications/06-water-level-alarm.md:100` 采用同一“线圈衰减 + 机械 5 ms”口径，但它是 5 V/70 Ω 的另一组假设（14.9 ms/20 ms），本次未复核其算术。
- `e1-inductive-load-energy-path.md` §2.2 的 RL 解、`L·ΔI/V` 适用边界与本次一致；§5.1 明确“释放不是电流到零”，是正确的限定。

### 8.2 发现的残留不一致（本次未修改仓库）

1. **`docs/common-hardware-report.md:80` 仍是旧结论**：  
   “D03 仅二极管 3.62 ms（满足 5 ms，旧结论‘淘汰’不成立）”。  
   这与 4c9db61 修正后的 `d03-relay.md`/`k-drive.md` 矛盾。按修正后的口径应写成：“3.62 ms 只是线圈电流到零；还要加继电器 release max 5 ms，系统约 8.6 ms，5 ms 不可保证。”这是**唯一一处直接数值/结论矛盾**的残留，建议后续同步（本次任务不改仓库）。
2. **`failures/f14-relay-flyback.md:46` 仍建议 `Δt ≈ L × ΔI / V`**：  
   该式忽略线圈电阻，仅适用于 `I·R ≪ V_clamp` 的稳压管/TVS 钳位；用在仅二极管上会把时间严重高估（仓库自己在 D01/K1 已改为 RL 解）。F14 虽注明“近似、不能替代手册”，但与“全库释放时间一律用 RL 解”的纪律不一致，建议改成 RL 解或明确限定“仅用于高钳位粗略比较”。
3. **`docs/common-hardware-gap-analysis.md:465`（C13）措辞**：  
   “‘仅二极管不满足 5 ms，淘汰’不成立”作为历史缺口记录可以保留，但容易被读成“仅二极管现在能满足 5 ms”。4c9db61 后的正确结论是：旧理由（21.4 ms）不成立，但仅二极管在加上 5 ms release 后仍不满足 5 ms；两种方案都不满足，区别只是差 3.62 ms 还是 0.50 ms。
4. **`d03-relay.md:132` 的“要求触点断开后 5 ms 内释放”措辞**：  
   字面上是“触点断开之后 5 ms 内释放”，与“线圈断电后 5 ms 内触点断开”相反/歧义。建议写成“线圈断电后 5 ms 内触点释放（NC 闭合）”。本次按后者理解。
5. **`docs/evidence/common-hardware-2026-10-22/audit/k-drive.md:164` 的“这个错误直接改变了候选取舍”**：  
   在 4c9db61 加上 5 ms release 后，仅二极管和稳压管都不满足 5 ms，“取舍”只在 ≥8.6 ms/≥5.5 ms 的场景成立；该句作为历史审计记录可以保留，但不应作为当前选型结论引用。

### 8.3 历史原始回答的保留

- 旧版 `d03-relay.md` 的“21.4 ms，淘汰”（`L×I/V` 线性式）已不在当前正文，但仍保留在 `docs/evidence/.../audit/k-drive.md:521` 和 `docs/common-hardware-gap-analysis.md:465` 的审计记录中；旧版“0.607 ms”同样保留在审计 L522。符合“保留历史原始回答”的要求。
- 旧版“3.62 ms 满足 5 ms”仍残留在 `docs/common-hardware-report.md:80`，这不是有意保留的历史记录，而是未同步的残留（见 8.2 第 1 条）。

## 9. 仍未核实事项（待核实 / NOT RUN）

1. **G5LE-1 12 VDC 线圈的 `R_coil` 与 must-release 电流/电压**：4 页 G5LE 手册（K100-E1-08）没有线圈电阻表、must-operate/must-release 表；`400 Ω` 是任务给定值，不能从该手册核实。→ **待核实**（需 G5LE 完整手册或实测）。
2. **`L=0.5 H`**：仓库明确写“算例假设”，不是 G5LE 数据手册值；线圈电感随衔铁位置/温度变化。→ **待核实**（需 LCR 表/电流波形实测）。
3. **G5LE `Release time 5 ms max` 的测试电路**：是否带续流二极管、驱动管类型、线圈电压/温度、触点负载；4 页手册只给“initial values”，未给测试条件。→ **待核实**。
4. **“5 ms”是纯机械时间还是 end-to-end dropout time**：Omron General Information 的定义是后者（线圈断电→NC 闭合，23 °C，不含弹跳）；任务文字称“机械释放时间”。两种解释下的系统总时间不同（8.62/5.50 ms 是相加模型的上限；若 5 ms 已含线圈衰减，则精确值更低但无法从现有资料算出）。→ **待核实**。
5. **1N4148 在 30 mA、实际温度下的 `V_F`**：Vishay 表格只保证 10 mA、25 °C 时 `VF ≤1.0 V`；30 mA 的 0.75–0.8 V 是 Fig.1/Fig.2 图读值，不是保证值；低温 `V_F` 更高、高温更低。→ **待核实**（可按实际批次/温度实测）。
6. **24 V 稳压管的实际 `V_Z`、容差、动态电阻、脉冲功率额定**：本文按理想 24.0 V + 0.7 V 恒压源计算；实际器件的钳位随电流下降，`t_off` 会比 0.495 ms 略长。→ **待核实**（需具体料号手册）。
7. **线圈热态 `R(T)`、电源容差（12 V ±?）、线圈是否长期加额定电压**：本文按 25 °C、12.0 V 计算；热态/低压会改变 `I0`、`τ` 和 must-release 余量。→ **待核实**。
8. **实际释放时间**：计算不能代替测量。需在样机上用电流探头测线圈电流、用差分探头/辅助触点测触点断开时刻，分别在仅二极管、二极管+24 V 稳压管、不同温度/电压下记录；通过标准是“线圈断电到触点释放的最大值 ≤ 系统要求”，并留够批次/温度余量。→ **NOT RUN**（本次没有实物）。
9. **“5 ms 系统要求”的计时起点**：是线圈断电、驱动信号撤销、还是触点开始动作？本文按“线圈断电到触点释放”理解；若起点不同，结论需重算。→ **待核实**（需系统时序定义）。

## 10. 参考来源（本次实际查阅）

### 10.1 仓库（快照 4c9db61）

- `design-hardware/references/common-hardware/k-drive.md`：K3 §必查参数 L220、§参数与算例 L228–232、§验证 L256、CHW-S200 L814、§需要同步修正 L836–839。
- `design-hardware/references/design-cards/drive/d03-relay.md`：§4 第 2 步 L109、§5 L132–149/L165–174、§12 L267–269。
- `design-hardware/references/engineering-deepdives/topics/e1-inductive-load-energy-path.md`：§2.2 L95–111、§5.1 L260–271、§6.1 L299–351。
- `design-hardware/references/failures/f14-relay-flyback.md`：L46。
- `design-hardware/references/common-hardware/applications/09-timer-control.md`：L81。
- `design-hardware/references/common-hardware/applications/06-water-level-alarm.md`：L100。
- `design-hardware/references/source-register.md`：CHW-S200 L301。
- `design-hardware/references/common-hardware/README.md`：L11（证据等级）。
- `docs/common-hardware-report.md`：L80。
- `docs/common-hardware-gap-analysis.md`：L465–466。
- `docs/evidence/common-hardware-2026-10-22/audit/k-drive.md`：L164–165、L521–522。

### 10.2 原厂资料

- Omron, **G5LE PCB Power Relay datasheet**, Cat. No. K100-E1-08, 0318(0207)(O), 4 pp. p.1 ordering/coil voltages; p.2 Characteristics (`Operate time 10 ms max.`, `Release time 5 ms max.`). URL: `https://omronfs.omron.com/en_US/ecb/products/pdf/en-g5le.pdf`（2026-10-22 下载）。
- Omron, **General Information**, Cat. No. JB301-E3-01 3/05. PDF p.7 `Dropout time` definition (coil de-energized → NC contacts closed, 23 °C, bounce excluded; generic example 5 ms max/mean approx. 2.3 ms); PDF p.3 note that a parallel diode tends to increase release time. Retrieved via DigiKey mirror: `https://media.digikey.com/pdf/Other%20Related%20Documents/Omron%20Other%20Doc/Relay%20Technical%20Pages.pdf`（2026-10-22 下载）。
- Vishay, **1N4148 Small Signal Fast Switching Diodes**, Rev. 1.6, 07-Nov-2024, Document Number 81857. p.2 Electrical Characteristics (`VF max. 1 V at IF = 10 mA`, Tamb = 25 °C), Fig.1/Fig.2 typical curves. URL: `https://www.vishay.com/docs/81857/1n4148.pdf`（2026-10-22 下载）。

> 说明：Omron 的通用 `5 ms max / mean approx. 2.3 ms` 是 General Information 中的示例，不是 G5LE 的典型值；本文没有把它当作 G5LE 的保证值或典型值使用。

---

**复核结论一句话：** 仅 1N4148 时线圈电流到零 `3.62 ms`，加 5 ms 释放得 `8.62 ms`；二极管+24 V 稳压管时 `0.495 ms`，加 5 ms 得 `5.495 ms`；两种方案都不能保证 5 ms 内释放。线圈算术与仓库 4c9db61 的修正值一致；但“5 ms”是 Omron 的 end-to-end dropout time，不是纯机械时间，因此 `8.62/5.50 ms` 应标为保守上限，精确值取决于未给出的数据手册测试电路，`待核实`。`docs/common-hardware-report.md:80` 仍有“3.62 ms 满足 5 ms”的旧结论，与当前快照矛盾，建议同步修正。
