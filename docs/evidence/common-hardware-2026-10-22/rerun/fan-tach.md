# 风扇 TACH 接口复核（固定快照 4c9db61）

- 仓库：`C:\Users\jlc\work\hardware-design-skill`
- 固定快照：`4c9db61628e4a83f01acad1c53ea5c0665182325`（`4c9db61`）
- 复核日期：2026-10-22
- 任务：3.3 V MCU 读取 Intel 4 线风扇 TACH，上拉到 3.3 V 还是 12 V；5.25 V 限制指什么；给出符合规范的接口电路与依据。
- 证据级别：E1（Intel 原厂规范正文逐节核对；CH32V003 数据手册 Table 3-16 核对）；E2（具体风扇的 TACH VOL/漏电/最小灌电流、12 V 轨容差、线束/ESD，待按型号与实物核对）。**无实物、无 EDA、无台架实测（NOT RUN）**。

> 说明：复核期间工作树正被其他会话并发修改（`02-fan-control.md`、`c-motion.md`、`k-drive.md`、`source-register.md` 出现未提交改动）。本文所有仓库行号与原文均用 `git show 4c9db61:<path>` 读取固定快照，不采用工作树内容；本文也不修改仓库文件。

---

## 1. 实际读过的文件/小节

### 1.1 仓库文件（固定快照 4c9db61）

| 文件 | 实际读过的小节/行 | 用途 |
|---|---|---|
| `design-hardware/references/common-hardware/applications/02-fan-control.md` | 第 4 节模块组成（L52–60）、第 6 节原理图组织（L84–90）、第 5 节算例（TACH 换算、PWM 分辨率） | 组合应用 02 的 TACH/PWM 接法与算例 |
| `design-hardware/references/common-hardware/c-motion.md` | `## C6 转速检测`（L632–732），含结论先行 L634、必查参数 L655–660、电路组成 L662–666、参数算例 L668–682、原理图逐脚 L684–690、常见误判 L714–720、来源 L728–731、来源表 L855 | 通用测速主题的 TACH 结论 |
| `design-hardware/references/common-hardware/k-drive.md` | `## K7 风扇`（L534–625），含必查参数 L556、电路组成 L558–562、tach 算例 L566–568、原理图逐脚 L576–578、来源 L625、来源表 L811 | 驱动组的风扇接口与来源 |
| `design-hardware/references/common-hardware/i-mcu.md` | I1 低成本基础控制（L60–75、L100–125）、来源表 CHW-S161（L884） | CH32V003 的资源/引脚；未给 VIH/VIL |
| `design-hardware/references/source-register.md` | L188（CHW-S056）、L298（CHW-S197） | Intel 4 线风扇规范的登记条目与 URL |
| `docs/evidence/common-hardware-2026-10-22/blind/B3.md` | L1–55、L85–115、L195–235 | 历史盲测原始回答（保留，不改） |
| `docs/evidence/common-hardware-2026-10-22/blind/eval.md` | L19、L46–50 | 盲测评分与“PWM 脚内部上拉到 5.25 V”记录 |
| `docs/evidence/common-hardware-2026-10-22/audit/c-motion.md` | L255–296、L354 | C6 审计：此前缺上拉电源/串阻/默认态 |
| `docs/evidence/common-hardware-2026-10-22/audit/k-drive.md` | L363–376、L512–544 | K7 审计：此前缺 tach 上拉/分压/ESD |
| `docs/common-hardware-gap-analysis.md` | L113、L124、L349 | C6/DRV-10 的缺口盘点 |
| `docs/common-hardware-report.md` | 全库检索“TACH/转速/风扇”时命中的报告段落 | 确认是否有其他 TACH 结论 |

### 1.2 原厂资料（实际打开并抽取正文）

| 文档 | 实际查阅范围 | 版本/日期 |
|---|---|---|
| Intel《4-Wire Pulse Width Modulation (PWM) Controlled Fans Specification》 | §2.1.1、§2.1.2、§2.1.3、§2.1.4、§2.3.1、§2.4、§3.1、§3.3、§4.1.6 Table 1；封面/目录/修订记录 | Rev 1.3，September 2005 |
| WCH《CH32V003 Datasheet》 | Table 3-16 General-purpose I/O static characteristics；3.3.9/3.3.10 节；封面版本 V1.3 | V1.3 |

Intel 官方 URL（仓库 CHW-S056 登记）在本次复核时返回 HTTP 403；实际抽取用的是仓库 CHW-S197 登记的镜像 `https://glkinst.com/cables/cable_pics/4_Wire_PWM_Spec.pdf`（PDF 35 页，封面同样为 Rev 1.3 / September 2005，正文页脚页码与 §2.1.3/§2.1.4/§2.3.1/§2.4/§4.1.6 完全对应）。这是一处**来源可达性差异**，不是版本差异；引用时以 Rev 1.3 的节号为准。

CH32V003 数据手册从第三方镜像取得（`https://akizukidenshi.com/goodsaffix/CH32V003.pdf`，33 页，封面 V1.3，页脚 V1.3）。仓库 CHW-S161 登记的是 WCH 官方下载页；官方页面是 JS 动态页，本次未能直接取得 PDF。表格数值与版本号已核对，但仍应把“官方直链未取”列为待核实项（见 §8）。

---

## 2. 问题与短结论

### 2.1 TACH 上拉到 3.3 V 还是 12 V？

**按 Intel 4 线风扇规范：上拉到 12 V，最大 12.6 V；3.3 V MCU 不能直接接，必须分压/电平转换到 ≤3.3 V。**

依据是 Intel Rev 1.3 §2.1.3 的原文：

> “Fan shall provide tachometer output signal with the following characteristics:
> • Two pulses per revolution
> • Open-collector or open-drain type output
> • **Motherboard will have a pull up to 12V, maximum 12.6V**”

三个要点：

1. TACH 是**风扇侧开集电极/开漏输出**；上拉电阻在**主板侧**，不在风扇内部。
2. 规范给主板侧的测试条件是 **12 V（最大 12.6 V）**，不是 3.3 V。
3. 风扇输出管只负责拉低；12.6 V 是它关断时必须承受的电压。3.3 V 上拉不会给风扇过压，但它**不是规范的测试条件**，风扇厂商未在该条件下保证 VOL/漏电/边沿。

**3.3 V 上拉能不能用？** 电气上通常能工作（开漏输出只拉低，3.3 V 上拉的高电平就是 3.3 V），很多风扇实测也能读；但这是**规范外用法**，不能据此宣称“符合 Intel 4 线规范”。若要用，必须按具体风扇型号实测高/低电平、边沿、漏电和最小灌电流，并在设计文件中注明“非 Intel 测试条件”。如果产品要写“符合 Intel 4-wire 规范”，就应按 12 V 上拉（最大 12.6 V）+ 分压/电平转换来做。

### 2.2 “TACH 的 5.25 V 限制”指什么？

**5.25 V 不是 TACH 的限制；它是 PWM 控制输入（pin 4）的限制，以及主板硬件监控器 PWM 输出的最大电压能力。** Intel Rev 1.3 中 5.25 V 只出现在 §2.1.4 和 §2.3.1：

§2.1.4 “PWM Control Input Signal”原文：

> “The following requirements are measured at the PWM (control) pin of the fan cable connector see Figure 7 and Table 1:
> PWM Frequency: Target frequency 25 kHz, acceptable operational range 21 kHz to 28 kHz
> Maximum voltage for logic low: VIL = 0.8 V
> Absolute maximum current sourced: Imax = 5 mA (short circuit current)
> **Absolute maximum voltage level: VMax = 5.25 V (open circuit voltage)**
> **This signal must be pulled up to a maximum of 5.25V within the fan.**”

§2.3.1 “Hardware Monitor Device — PWM Output Signal”原文：

> “The Hardware Monitor Devise is required to provide an open-drain or open-collector type output for the PWM signal on pin 4 ... with the following properties:
> Frequency: 25kHz nominal, 21-28kHz is acceptable
> Current sink capability: 5mA required, 8mA recommended
> **Maximum voltage capability: 5.25V**
> Maximum VOL: 0.8V
> Signal is not inverted, 100% PWM results in Max fan speed”

因此：

- 5.25 V 是 **PWM 脚的开路电压上限**：风扇内部把 PWM 输入上拉到不高于 5.25 V；主板侧不能外加 pull-up/pull-down（§2.4 第 1 条），否则会改变占空比—转速关系，甚至到不了全速。
- 5.25 V 也是**主板 PWM 驱动器**必须能承受的电压上限（硬件监控器用开漏/开集电极，灌 5 mA，建议 8 mA，VOL ≤0.8 V）。
- **TACH（pin 3）在 §2.1.3 中没有 5.25 V 条目**；TACH 只有“2 脉冲/转、开集电极/开漏、主板侧 12 V 上拉最大 12.6 V”三条。把 5.25 V 当成 TACH 上限，是把 pin 4 的条目套到了 pin 3 上。
- 若某个具体风扇手册另外写“TACH 最大 5.25 V”，那是该型号的附加限制，不是 Intel 4-wire 规范的通用结论；应按该风扇手册处理，并标 `待核实`。

### 2.3 一句话结论

**TACH 按规范上拉到 12 V（最大 12.6 V），再用 10 kΩ/3.3 kΩ（1%）分压到约 3.13 V（12.6 V 时）后进 3.3 V MCU；5.25 V 是 PWM 脚的限制，不是 TACH 的限制。3.3 V 上拉只能作为经具体风扇验证的规范外简化，不能宣称 Intel 合规。**

---

## 3. 修改前 / 修改后（本项）

### 3.1 修改前：历史原始回答（保留，不改）

在 `4c9db61` 之前的历史版本与盲测原始回答中，结论是：

- `4c9db61^` 的 `c-motion.md` C6 结论先行：
  > “4 线风扇 TACH 是 2 脉冲/转、开漏输出，**上拉到 3.3 V 即可，不要照搬主板的 12 V 上拉**。”
- `4c9db61^` 的 `02-fan-control.md` 模块图：
  > “`FAN pin3 TACH ── 4.7 kΩ 上拉到 3.3 V ── 100 Ω ── MCU 输入捕获`”
- `docs/evidence/common-hardware-2026-10-22/blind/B3.md` L35（历史盲测回答，仍保留在快照中）：
  > “`FAN pin3 TACH ── 4.7 kΩ 上拉到 3.3 V ── 100 Ω ── MCU 输入捕获`”

这段历史回答的**合理部分**是：开漏输出确实可以用 3.3 V 上拉，电气上通常能工作。**问题**是它把“能用”当成了“规范做法”，没有区分“Intel 规范的 12 V 测试条件”和“规范外的 3.3 V 简化”，也没有给出 12 V 上拉时的分压边界。历史回答按用户要求保留，不作为当前推荐。

### 3.2 快照 4c9db61：已改成 12 V 上拉，但分压值仍有边界错误

`4c9db61` 的提交说明已经明确：

> “Fan tach: Intel 4-wire spec expects a 12 V (max 12.6 V) motherboard-side pull-up, not 3.3 V; 3.3 V MCUs need a divider/level shift and must not connect 12 V directly. **The 5.25 V limit is the PWM input, not tach.**”

快照中的对应文字：

- `02-fan-control.md` L56：
  > “`FAN pin3 TACH ── 12 V 上拉 10 kΩ ── 分压 3.6 kΩ 到地（3.18 V）── 100 Ω ── MCU 输入捕获`”
- `02-fan-control.md` L60：
  > “TACH 是开集电极/开漏；Intel §2.1.3 的**主板侧上拉是 12 V（最大 12.6 V）**，3.3 V MCU 要 12 V 上拉 + 分压/电平转换（10 kΩ/3.6 kΩ → 3.18 V），不要把 12 V 直接进 GPIO。3.3 V 上拉不是规范测试条件，需按具体风扇实测。”
- `02-fan-control.md` L88：
  > “pin3 经 **12 V 上拉 10 kΩ + 3.6 kΩ 分压到 3.18 V**、100 Ω 串阻进捕获脚……”
- `c-motion.md` L634：
  > “3.3 V MCU 要用 12 V 上拉 + 分压/电平转换（如 10 kΩ/3.6 kΩ → 3.18 V）……”
- `c-motion.md` L664：
  > “3.3 V MCU 用 12 V 上拉 + 分压（10 kΩ/3.6 kΩ → 3.18 V）或 5 V 耐压缓冲，串 100 Ω，必要时 1 nF 到地……”
- `k-drive.md` L568：
  > “需 12 V 上拉 + 分压（例如 `12 V × 3.6 kΩ/(10 kΩ+3.6 kΩ) = 3.18 V`）或 5 V 耐压缓冲/比较器。”
- `k-drive.md` L556（5.25 V 的正确归属）：
  > “**PWM 输入最高 5.25 V**（这个 5.25 V 是 PWM 脚，不是 tach 脚）。”

**快照做对的部分：**

1. 明确了 TACH 是开集电极/开漏，主板侧上拉按 Intel §2.1.3 是 12 V（最大 12.6 V）。
2. 明确了 3.3 V 上拉不是规范测试条件，需按具体风扇实测。
3. `k-drive.md` L556 明确写了 5.25 V 是 PWM 脚，不是 tach 脚；`c-motion.md` L665 也把 5.25 V 放在 PWM 条目下。

**快照仍存在的问题（本项要修的核心）：**

- 所有“3.18 V”都是按 **12.0 V** 算的：`12.0 × 3.6/(10+3.6) = 3.1765 V`。
- 但 Intel §2.1.1 的 12 V 轨是 **12 V ±5%**，最大 **12.6 V**；按 12.6 V 算：`12.6 × 3.6/(10+3.6) = 3.3353 V`，**超过 3.3 V 电源轨**。以 CH32V003 为例，标准 I/O 脚的绝对最大是 VDD+0.3 V = 3.6 V，3.335 V 虽仍低于绝对最大，但已超出推荐工作条件；如果 3.3 V 轨本身偏低（例如 Buck 的 3.21 V 下限），过压幅度增大，可能引起输入 ESD 二极管漏电/灌流。**不能把“绝对最大”当设计目标**；设计边界应是“高电平 ≤ VDD”。
- 因此快照的“3.18 V”只证明了 12.0 V 标称点，没有证明 **12.6 V 最坏点**；`10 kΩ/3.6 kΩ` 的组合不满足“输入高电平不超过 3.3 V 轨”的边界。
- `02-fan-control.md` L88 的“10 kΩ×1 nF 的上升时间约 10 µs，25 kHz 以下无问题”把 **TACH** 和 **PWM 的 25 kHz** 混在一起：25 kHz 是 PWM 频率；TACH 频率由转速决定（2 脉冲/转，3000 rpm 只有 100 Hz）。TACH 的 RC 应按实际最高转速核算，不能拿 25 kHz 当 TACH 频率。

### 3.3 本次复核结论（修改后）

**拓扑不变（12 V 上拉 + 分压），分压值改为 `10 kΩ/3.3 kΩ`（1%），并把“3.18 V”改成“3.13 V @12.6 V / 2.98 V @12 V”。**

- `12.6 × 3.3/(10+3.3) = 3.1263 V`（最坏 12.6 V 时）
- `12.0 × 3.3/(10+3.3) = 2.9774 V`（标称 12 V 时）
- `11.4 × 3.3/(10+3.3) = 2.8286 V`（最低 11.4 V 时）

`3.3 kΩ` 在 12.6 V 时给出 3.126 V，低于 3.3 V 标称轨；`3.6 kΩ` 给出 3.335 V，超过 3.3 V 标称轨。**这就是“风扇测速输入边界”的实质：不是“要不要 12 V 上拉”，而是“12.6 V 最坏点上分压后的高电平必须≤MCU 的 VDD 上限”。**

> 交叉核对：快照之后的同分支提交 `d97b6f3`（`fix(common-hardware): keep fan tach divider inside 12.6 V boundary`）也把 `10k/3.6k` 改成了 `10k/3.3k`，提交说明写“Use 10k/3.3k instead of 10k/3.6k so the divider output stays at 3.13 V at the Intel maximum 12.6 V pull-up (12 V gives 2.98 V), leaving margin for a 3.3 V input.” 该提交**不属于固定快照 4c9db61**，只作为独立交叉核对，不作为快照依据。

**5.25 V 的归属在快照中基本正确，不需要“改结论”，只需要把容易被误读的表格拆开：**

- `k-drive.md` L556 已经明确“这个 5.25 V 是 PWM 脚，不是 tach 脚”，这是正确表述，应保留。
- `c-motion.md` L659 的表格行把“TACH 上拉 12 V max 12.6 V”“MCU 侧 3.3 V”“PWM 25 kHz、VIL 0.8 V、Vmax 5.25 V”放在同一格。内容没有错，但行名是“上拉/PWM 电平”，读者可能把 5.25 V 误读成 TACH 的上限。建议同步时拆成两行：一行“TACH 上拉（12 V max 12.6 V）”，一行“PWM 电平（25 kHz、VIL 0.8 V、Vmax 5.25 V）”。
- `02-fan-control.md` L60 的“风扇内部已把 PWM 脚上拉到不高于 5.25 V”是正确的；它紧接在 TACH 句之前，读者也可能误读。建议在“5.25 V”后加“（PWM 脚，pin 4）”，并把 TACH 句单独成段。

**3.3 V 上拉的定位（修改后）：**

- 不作为默认推荐；只作为“具体风扇手册允许 + 实测通过”的规范外简化。
- 如果使用，建议 `4.7 kΩ–10 kΩ` 上拉到 3.3 V，串 100 Ω；但要注意 3.3 V/10 kΩ 的灌电流只有 0.33 mA，3.3 V/4.7 kΩ 只有 0.70 mA。若风扇 TACH 输出要求最小灌电流（常见 1 mA 级，**具体型号待核实**），3.3 V 上拉可能不足以可靠拉低；12 V/10 kΩ 提供 1.26 mA，更接近规范测试条件。
- 3.3 V 上拉的高电平是 3.3 V（或 VDD），低电平是风扇的 VOL；分压方案的低电平是 `VOL × 3.3/13.3`，反而更低、抗 VOL 偏差更好。这是 12 V+分压的另一个实际优点。

---

## 4. 原厂依据逐条

### 4.1 Intel 4-Wire PWM Fan Specification Rev 1.3（2005-09）

| 节 | 原文要点 | 对本问题的意义 |
|---|---|---|
| §2.1.1 Fan Input Voltage | “Fan operating voltage shall be within the range 12 V ±5% V.” | 12 V 轨最坏 12.6 V；分压必须按 12.6 V 算，不能按 12.0 V 算。 |
| §2.1.2 Current | 稳态 ≤1.5 A（12.6 V、自由风）；启动尖峰可 >1.0 A，最高 2.2 A，持续 ≤1.0 s。 | 与 TACH 电平无关；但说明 12 V 轨有启动跌落/地弹，TACH 地要单独回 MCU。 |
| §2.1.3 Tachometer Output Signal | 2 脉冲/转；开集电极或开漏；**主板侧上拉到 12 V，最大 12.6 V**。 | TACH 的唯一电压边界；没有 5.25 V。 |
| §2.1.4 PWM Control Input Signal | 25 kHz（21–28 kHz）；VIL=0.8 V；Imax=5 mA（短路）；**VMax=5.25 V（开路电压）**；风扇内部上拉到 ≤5.25 V；新设计鼓励 3.3 V 上拉。 | 5.25 V 属于 PWM 脚（pin 4），不属于 TACH。 |
| §2.3.1 Hardware Monitor PWM Output | 开漏/开集电极；25 kHz；灌 5 mA（建议 8 mA）；**最大电压能力 5.25 V**；VOL ≤0.8 V；100% = 全速。 | 主板 PWM 驱动器要能承受 5.25 V；3.3 V 非 5 V 容忍脚不能直连。 |
| §2.4 Motherboard Considerations | PWM 走线**不得**加上拉/下拉；上拉在风扇轮毂内；外加会改变占空比—转速关系，甚至到不了全速；多风扇用开漏缓冲。 | 只针对 PWM；TACH 相反，必须由主板加上拉。不要把两条规则混用。 |
| §3.1 Maximum Fan Speed | 最大转速由风扇厂商规定，对应 100% 占空比。 | 规范不限制 TACH 最高频率；TACH 频率按具体风扇 RPM 算。 |
| §3.3 Fan Speed Response | 无控制信号时风扇全速。 | PWM 默认态/断线方向是“全速”，不是停转；低边 FET 栅极下拉是失效安全。 |
| §4.1.6 Table 1 | pin 1 GND（黑）、pin 2 12 V（黄）、pin 3 Sense（绿）、pin 4 Control（蓝）。 | 确认 TACH 是 pin 3、PWM 是 pin 4；不要把 5.25 V 套到 pin 3。 |

### 4.2 CH32V003 Datasheet V1.3 — Table 3-16

| 参数 | 公式/条件 | VDD=3.3 V 时 | 说明 |
|---|---|---|---|
| VIH（标准 I/O） | min `0.22×(VDD−2.7)+1.55 V`，max `VDD+0.3 V` | min **1.682 V**，max 3.6 V | 3.13 V 分压高电平有 >1.4 V 余量 |
| VIH（FT I/O） | 同上，max 5.5 V | min 1.682 V，max 5.5 V | PWM 若用 FT 脚，5.25 V 在 5.5 V 以内（余量仅 0.25 V） |
| VIL（标准/FT） | max `0.19×(VDD−2.7)+0.65 V`，min −0.3 V | max **0.764 V** | 分压低电平 0.099 V（VOL=0.4 V）有 >0.6 V 余量 |
| Vhys | 150 mV typ | — | 施密特输入，抗噪声 |
| CI/O | 5 pF typ | — | 与外部 1 nF 相比可忽略 |

> 注意：Table 3-16 的 VIH/VIL 是 **GPIO 静态特性**；TACH 应接到普通 GPIO/定时器输入捕获脚，不要接到 NRST、SWIO 等专用脚。具体引脚分配待原理图阶段核对。

---

## 5. 计算过程（单位齐全）

### 5.1 分压高电平

电路：`+12V ── R1 ── TACH 节点 ── R2 ── GND`，TACH 节点经 `R3=100 Ω` 进 MCU。

公式：

```text
V_high = V_12V × R2 / (R1 + R2)
```

| R1 | R2 | 11.4 V | 12.0 V | 12.6 V | 结论 |
|---:|---:|---:|---:|---:|---|
| 10 kΩ | 3.6 kΩ | 3.0176 V | 3.1765 V | **3.3353 V** | 12.6 V 超过 3.3 V 轨，不合格 |
| 10 kΩ | 3.3 kΩ | 2.8286 V | 2.9774 V | **3.1263 V** | 合格（3.3 V 标称轨） |
| 10 kΩ | 3.0 kΩ | 2.6308 V | 2.7692 V | **2.9077 V** | 更保守；适合 3.3 V 轨下限较低或 5% 电阻 |

**结论：** 快照的 10 kΩ/3.6 kΩ 只在 12.0 V 标称点得到 3.18 V；在规范允许的 12.6 V 最坏点得到 3.335 V，超过 3.3 V。**必须改为 10 kΩ/3.3 kΩ（1%）**，或改用 10 kΩ/3.0 kΩ 留更多裕量。

### 5.2 电阻公差

以 10 kΩ/3.3 kΩ、12.6 V 为例，取最坏组合 `R1_min = 10 kΩ×(1−tol)`、`R2_max = 3.3 kΩ×(1+tol)`：

```text
V_high(max) = 12.6 × R2_max / (R1_min + R2_max)
```

| 电阻公差 | R1_min | R2_max | V_high(max) @12.6 V | 判断 |
|---:|---:|---:|---:|---|
| 1% | 9.90 kΩ | 3.333 kΩ | **3.1736 V** | 低于 3.3 V；若 VDD 下限 ≥3.21 V（本仓库 Buck 算例 3.21–3.38 V），余量约 36 mV |
| 5% | 9.50 kΩ | 3.465 kΩ | **3.3675 V** | 超过 3.3 V，不合格 |

**结论：** 必须用 **1% 电阻**；5% 电阻不能用于这个分压。若 3.3 V 轨下限低于 3.21 V，建议改用 10 kΩ/3.0 kΩ（1% 最坏约 2.967 V）或在 MCU 端加 3.3 V 钳位。

### 5.3 低电平

风扇 TACH 拉低到 `VOL` 时，分压节点：

```text
V_low = VOL × R2 / (R1 + R2)
```

以 R1=10 kΩ、R2=3.3 kΩ：

| VOL（假设值） | V_low | 对比 CH32V003 VIL(max)=0.764 V |
|---:|---:|---|
| 0.0 V | 0.000 V | 远低于 |
| 0.4 V（常见开集电极饱和假设） | **0.0992 V** | 余量 0.665 V |
| 0.8 V（Intel PWM 的 VOL 上限，不是 TACH 规范值） | **0.1985 V** | 余量 0.566 V |

**注意：** Intel §2.1.3 **没有给 TACH 的 VOL 保证值**；0.4 V/0.8 V 是**假设值**，不是 TACH 规范值。0.8 V 是 §2.3.1 的 PWM VOL 上限，借来做最坏估计。具体风扇的 TACH VOL 必须查该型号手册或实测。

### 5.4 电流与功耗

以 R1=10 kΩ、R2=3.3 kΩ、12.6 V 为例：

**高电平（风扇输出关断）：**

```text
I_div = 12.6 V / (10 kΩ + 3.3 kΩ) = 0.947 mA
P_R1 = (12.6 − 3.1263)² / 10 kΩ = 8.98 mW
P_R2 = 3.1263² / 3.3 kΩ = 2.96 mW
```

**低电平（风扇输出拉低，取 VOL=0.4 V）：**

```text
I_R1 = (12.6 − 0.4) / 10 kΩ = 1.220 mA
I_R2 = 0.4 / 3.3 kΩ = 0.121 mA
I_sink(fan) = 1.220 + 0.121 = 1.341 mA
P_R1 = (12.6 − 0.4)² / 10 kΩ = 14.88 mW
P_R2 = 0.4² / 3.3 kΩ = 0.048 mW
```

**结论：** 0402/0603 的 1% 电阻（通常 ≥50 mW）足够；风扇 TACH 只需灌 1.34 mA，远低于常见开集电极输出能力。**但 Intel 规范没有给 TACH 最大灌电流**；若具体风扇手册给了更小的上限，按手册核算。10 kΩ 是设计值，不是规范值；4.7 kΩ–10 kΩ 都可用，代价是功耗和灌电流不同。

### 5.5 上升时间与 TACH 频率

分压节点的戴维南电阻（风扇关断、R3 后）：

```text
R_th = R1 ∥ R2 = 10 kΩ × 3.3 kΩ / (10 kΩ + 3.3 kΩ) = 2.481 kΩ
R_total = R_th + R3 = 2.481 kΩ + 0.100 kΩ = 2.581 kΩ
τ = R_total × C = 2.581 kΩ × 1 nF = 2.581 µs
t_10–90% = 2.2 × τ = 5.68 µs
```

若用 3.3 V 上拉、10 kΩ、1 nF：

```text
τ = 10 kΩ × 1 nF = 10 µs
t_10–90% = 2.2 × τ = 22 µs
```

**TACH 频率（2 脉冲/转）：**

```text
f_TACH = RPM × 2 / 60
T = 1 / f_TACH
```

| RPM | f_TACH | 周期 T | 5.68 µs 占周期 |
|---:|---:|---:|---:|
| 600 | 20.00 Hz | 50.000 ms | 0.011% |
| 1400 | 46.67 Hz | 21.429 ms | 0.027% |
| 2200 | 73.33 Hz | 13.636 ms | 0.042% |
| 3000 | 100.00 Hz | 10.000 ms | 0.057% |
| 30000 | 1000.00 Hz | 1.000 ms | 0.568% |

**结论：** 1 nF + 10 kΩ/3.3 kΩ 的 5.68 µs 上升时间对 TACH 的 20 Hz–1 kHz 范围完全够；即使 30 000 rpm（1 kHz）也只占 0.57%。**不要把 PWM 的 25 kHz 当成 TACH 频率**；TACH 由 RPM 决定。如果线束很长、噪声大，1 nF 可保留；如果 TACH 频率更高或上升沿要求更严，减小 C 或降低 R1/R2。

### 5.6 数值性质（保证值 / 典型值 / 假设值）

| 数值 | 性质 | 来源/说明 |
|---|---|---|
| 12 V ±5%（11.4–12.6 V） | **规范保证值** | Intel §2.1.1 |
| 主板侧 TACH 上拉 12 V，最大 12.6 V | **规范保证值/条件** | Intel §2.1.3 |
| TACH 2 脉冲/转、开集电极/开漏 | **规范保证值** | Intel §2.1.3 |
| §2.1.3 没有 5.25 V 条目（TACH 的电压边界只有 12.6 V 上拉） | **规范条文事实** | Intel §2.1.3 只有三条：2 脉冲/转、开集电极/开漏、主板侧 12 V 上拉 max 12.6 V；5.25 V 只在 §2.1.4/§2.3.1 |
| PWM VMax 5.25 V（开路电压）、内部上拉 ≤5.25 V | **规范保证值/上限** | Intel §2.1.4 |
| PWM 25 kHz（21–28 kHz）、VIL 0.8 V、Imax 5 mA | **规范保证值** | Intel §2.1.4 |
| 硬件监控器 PWM 输出 5.25 V / 5 mA（8 mA 建议）/ VOL 0.8 V | **规范保证值** | Intel §2.3.1 |
| CH32V003 VIH/VIL 公式、VIH max、VIL min、Vhys、CI/O | **数据手册保证/典型值** | Table 3-16；Vhys/CI/O 为 typ |
| 风扇 TACH 的 VOL | **假设值（待核实）** | Intel §2.1.3 未给；本文用 0.4 V 作常见饱和假设、0.8 V 作最坏借用值（0.8 V 是 §2.3.1 PWM 的 VOL 上限，不是 TACH 规范值） |
| 风扇 TACH 最小灌电流 1 mA 级 | **假设值（待核实）** | 常见开集电极/霍尔输出的经验量级；具体型号手册才有效 |
| 3.3 V 轨 3.21–3.38 V | **仓库算例值（非实测）** | `02-fan-control.md` L74 的 TPS54202H 反馈容差算例；实际批次/负载瞬态待核 |
| 电阻 1% | **设计选择** | 5% 最坏 3.3675 V > 3.3 V，不满足；必须 1% |
| 12 V/10 kΩ 的 1.26 mA、含 R2 的 1.34 mA | **计算值** | 由规范电压与设计阻值算出，不是风扇保证值 |

### 5.7 MCU 阈值余量

以 CH32V003 VDD=3.3 V、R1=10 kΩ、R2=3.3 kΩ：

```text
V_high(min, 11.4 V) = 2.8286 V
VIH(min) = 0.22×(3.3−2.7)+1.55 = 1.682 V
余量 = 2.8286 − 1.682 = 1.147 V

V_low(max, VOL=0.8 V) = 0.1985 V
VIL(max) = 0.19×(3.3−2.7)+0.65 = 0.764 V
余量 = 0.764 − 0.1985 = 0.566 V
```

**结论：** 高/低电平余量都很大；分压方案对 MCU 阈值不敏感，主要约束是“高电平不要超过 VDD”和“电阻公差”。

---

## 6. 推荐接口电路

### 6.1 方案 A（推荐，按 Intel 规范）：12 V 上拉 + 分压

```text
                         +12 V (11.4–12.6 V)
                           │
                        R1 10 kΩ 1%
                           │
FAN pin3 (TACH) ───────────┤  TACH 节点
  (open collector/drain)   │
                        R2 3.3 kΩ 1%
                           │
                          GND

TACH 节点 ── R3 100 Ω ──┬── MCU 输入捕获
                        │
                     C1 1 nF (可选)
                        │
                       GND

连接器侧：ESD/TVS（VWM ≥ 13 V，建议 15 V 档，低电容；不要用 5 V TVS 直接钳 12 V 节点）
```

**取值与依据：**

| 元件 | 值 | 依据/说明 |
|---|---|---|
| R1 | 10 kΩ 1% | 主板侧 TACH 上拉到 12 V（Intel §2.1.3）；10 kΩ 是设计值，规范未规定阻值；12.6 V、VOL=0 V 时 R1 电流 1.26 mA；含 R2 时 VOL=0.4 V 总灌电流 1.34 mA |
| R2 | 3.3 kΩ 1% | 分压使 `12.6 V → 3.126 V`，低于 3.3 V；1% 最坏 3.174 V |
| R3 | 100 Ω | 串阻，限流/隔离 MCU 输入电容；与 C1 形成 RC |
| C1 | 1 nF（可选） | 与 `R1∥R2 + R3 = 2.581 kΩ` 形成 `τ=2.58 µs`、`t10–90%=5.68 µs`；TACH ≤1 kHz 时足够 |
| TVS/ESD | 连接器侧，VWM ≥13 V（建议 15 V 档） | 保护 12 V 节点；具体钳位/电容按 EMC 与线长核对 |

**设计检查清单：**

1. `V_high(12.6 V) ≤ VDD(min)`：3.126 V ≤ 3.3 V（标称）；1% 最坏 3.174 V，若 VDD 下限 3.21 V，余量 36 mV。
2. `V_high(11.4 V) ≥ VIH(min)`：2.829 V ≥ 1.682 V（CH32V003）。
3. `V_low(VOL=0.8 V) ≤ VIL(max)`：0.199 V ≤ 0.764 V。
4. 风扇 TACH 灌电流：1.34 mA（VOL=0.4 V），低于常见开集电极能力；具体型号待核。
5. 电阻功率：R1 最坏 14.9 mW、R2 3.0 mW；0402/0603 ≥50 mW 足够。
6. 12 V 节点不要直接进 MCU；分压比按 12.6 V 算，不按 12.0 V 算。

### 6.2 方案 B（规范外简化）：3.3 V 上拉

```text
                         +3.3 V
                           │
                        R1 4.7–10 kΩ 1%
                           │
FAN pin3 (TACH) ───────────┼── R3 100 Ω ── MCU 输入捕获
  (open collector/drain)   │
                           C1 1 nF (可选)
                           │
                          GND
```

**适用条件：**

- 具体风扇手册明确允许 3.3 V 上拉，或至少没有规定最小上拉电压；并且
- 实测高/低电平、边沿、漏电、丢脉冲都满足；并且
- 设计文件明确写“非 Intel 测试条件，按风扇型号验证”，不宣称 Intel 合规。

**注意：**

- 3.3 V/10 kΩ 的灌电流只有 0.33 mA；3.3 V/4.7 kΩ 只有 0.70 mA。若风扇 TACH 输出要求最小灌电流（常见 1 mA 级，具体待核），可能不足以可靠拉低。12 V/10 kΩ 的 1.26 mA 更接近规范条件。
- 3.3 V 上拉的上升时间：10 kΩ×1 nF → τ=10 µs、t10–90%=22 µs；TACH 20 Hz–1 kHz 仍够，但比方案 A 慢。
- 3.3 V 上拉的低电平就是风扇 VOL；方案 A 把 VOL 再衰减到 0.248 倍，低电平余量更好。

### 6.3 方案 C（替代电平转换）：N-FET

```text
                         +12 V
                           │
                        R1 10 kΩ
                           │
FAN pin3 (TACH) ─────── drain
                        BSS138 / 2N7002
                  gate ── +3.3 V
                  source ──┬── R2 10 kΩ ── +3.3 V
                           └── R3 100 Ω ── MCU 输入捕获
```

**原理：** 风扇拉低时，FET 的体二极管/沟道把 source 拉低；风扇关断时，FET 关断，source 被 R2 拉到 3.3 V。风扇侧仍然看到 12 V 上拉（满足 §2.1.3 的测试条件），MCU 侧是高电平 3.3 V。

**注意：**

- BSS138 的 VDS 50 V、2N7002 60 V，均能承受 12.6 V；gate 3.3 V 时 Rds(on) 足够（TACH 只有 mA 级）。
- 需要确认 FET 的 gate 阈值/体二极管方向；不同型号的 pinout 不同。
- 比方案 A 多一颗 FET 和一颗 3.3 V 上拉；优点是高电平时没有 12 V 分压电流，低电平由 FET 主动拉低。
- 若使用 74LVC1G07 等开漏缓冲，输入仍要先分压到 ≤5.5 V；它不能直接承受 12 V。不要把它当 12 V 电平转换器。

### 6.4 PWM 脚（pin 4）的 5.25 V 接口

```text
FAN pin4 (PWM, internal pull-up ≤5.25 V)
        │
        ├── drain of BSS138 / 2N7002
        │
gate ─── MCU GPIO (3.3 V) ── 100 kΩ pull-down to GND
source ─ GND
```

或：

```text
MCU GPIO ── 74LVC1G07 (VCC=3.3 V, open-drain output) ── FAN pin4
```

**规则：**

- 主板侧**不得**在 PWM 线上加 pull-up/pull-down（Intel §2.4 第 1 条）；上拉在风扇内部。
- 3.3 V 非 5 V 容忍 GPIO 不能直接接 PWM：风扇内部上拉最高 5.25 V，关断时引脚可能看到 5.25 V。
- 用 5 V 耐压开漏缓冲（74LVC1G07 类；具体输出 abs max 按该器件手册核对，仓库 02-fan-control 以它为候选）或低边 N-FET（BSS138/2N7002，VDS 50/60 V）；FET 的 gate 加 100 kΩ 下拉，默认关断 → PWM 高 → 风扇全速（失效安全）。
- 若 MCU 引脚本身是 5 V 容忍且可配置开漏（CH32V003 的 PC1/PC2/PC5/PC6 为 FT），可以直接开漏接；但 5.25 V 与 5.5 V 的余量只有 0.25 V，建议仍按具体引脚 abs max 核对。
- 3.3 V 推挽直接接：高电平 3.3 V 在 5.25 V 绝对最大以内，但会与风扇内部上拉“对拉”，可能改变占空比/增加灌电流；规范推荐开漏，不推荐推挽。

---

## 7. 全库一致性检查（快照 4c9db61）

### 7.1 相关结论清单

| 位置 | 快照原文/结论 | 判定 | 同步建议 |
|---|---|---|---|
| `02-fan-control.md` L56 | 12 V 上拉 10 kΩ + 3.6 kΩ 分压到 3.18 V | **部分错**：3.18 V 只是 12.0 V 标称；12.6 V 时 3.335 V > 3.3 V | 改 `3.3 kΩ`，写 `3.13 V @12.6 V（2.98 V @12 V）` |
| `02-fan-control.md` L60 | 12 V 上拉 + 10 kΩ/3.6 kΩ → 3.18 V；3.3 V 上拉不是规范测试条件 | **部分错**：拓扑对，分压值错 | 同上；并把“5.25 V”明确为“PWM 脚，pin 4” |
| `02-fan-control.md` L88 | 12 V 上拉 10 kΩ + 3.6 kΩ 分压到 3.18 V；1 nF 上升时间约 10 µs，25 kHz 以下无问题 | **部分错**：分压值错；25 kHz 是 PWM，不是 TACH | 改 3.3 kΩ；把 RC 说明改成“TACH 频率按 RPM 算，3000 rpm=100 Hz；5.7 µs 足够” |
| `c-motion.md` L634 | 12 V 上拉 + 10 kΩ/3.6 kΩ → 3.18 V；3.3 V 上拉需实测 | **部分错**：分压值错 | 改 3.3 kΩ / 3.13 V @12.6 V |
| `c-motion.md` L659 | 同一行写“TACH 上拉 12 V max 12.6 V；PWM Vmax 5.25 V” | **内容对，易误读** | 拆成 TACH 行与 PWM 行 |
| `c-motion.md` L664 | 12 V 上拉 + 10 kΩ/3.6 kΩ → 3.18 V；3.3 V 上拉需实测 | **部分错**：分压值错 | 改 3.3 kΩ / 3.13 V @12.6 V |
| `c-motion.md` L688 | 12 V 上拉（max 12.6 V）+ 分压到 3.3 V；2 脉冲/转、开漏 | **对**（未给具体比值） | 可保留；补“3.13 V @12.6 V” |
| `c-motion.md` L717 | 规范上拉 12 V max 12.6 V；3.3 V 上拉不是规范测试条件 | **对** | 保留 |
| `k-drive.md` L556 | TACH 12 V max 12.6 V；PWM 最高 5.25 V（明确“不是 tach 脚”） | **对** | 保留；这是全库最清楚的 5.25 V 归属表述 |
| `k-drive.md` L568 | 12 V 上拉 + `12 V × 3.6/(10+3.6)=3.18 V` | **部分错**：只算 12.0 V；12.6 V 时 3.335 V | 改 `12.6 × 3.3/(10+3.3)=3.13 V`（12 V 时 2.98 V） |
| `k-drive.md` L578 | PWM 开漏或 3.3 V 推挽（高电平 ≤5.25 V）；tach 上拉/分压后进捕获 | **基本对**；推挽不是规范推荐 | 建议改为“开漏优先；推挽仅在确认风扇 VIH 与内部上拉后使用” |
| `source-register.md` L188 / L298 | CHW-S056 / CHW-S197 登记 TACH 2 脉冲/转、开漏、12 V 上拉；PWM Vmax 5.25 V | **对** | 保留；可在“支持内容”里加“5.25 V 仅 PWM，不是 TACH” |
| `docs/evidence/.../blind/B3.md` L35 | 4.7 kΩ 上拉到 3.3 V | **历史原始回答，保留** | 不改；在报告/索引中注明“历史回答，已被 12 V+分压结论取代” |
| `docs/evidence/.../blind/eval.md` L50 | “PWM 脚内部上拉到 5.25 V 不可再加 pull-up” | **对** | 保留 |
| `i-mcu.md` L884（CHW-S161） | CH32V003 V1.3，VDD 2.7–5.5 V，FT 脚 PC1/PC2/PC5/PC6 | **对**；未给 VIH/VIL | 可在 TACH/PWM 接口处补 Table 3-16 的 VIH/VIL 引用 |

### 7.2 同步修改建议（不改仓库，仅列出）

1. **数值替换**：所有 `10 kΩ/3.6 kΩ → 3.18 V` 改为 `10 kΩ/3.3 kΩ → 3.13 V @12.6 V（2.98 V @12 V）`；明确“按 12.6 V 最坏点算，不按 12.0 V 算”。
2. **补一句边界**：`V_high(12.6 V) ≤ VDD(min)`；若 VDD 下限低于 3.21 V，改用 10 kΩ/3.0 kΩ 或加 3.3 V 钳位；电阻用 1%。
3. **拆 c-motion L659 表格行**：TACH 上拉一行、PWM 电平一行，避免 5.25 V 被误读为 TACH 上限。
4. **修正 02-fan-control L88 的 RC 说明**：25 kHz 是 PWM，不是 TACH；TACH 频率按 `RPM×2/60` 算；1 nF 在 3000 rpm/100 Hz 下 5.7 µs 上升时间足够。
5. **保留 k-drive L556 的“5.25 V 是 PWM 脚，不是 tach 脚”**，并建议在 c-motion、02-fan-control 也加同样的括号说明。
6. **保留历史 B3.md 原文**，不要用新结论覆盖历史证据；在报告索引里加“历史回答（3.3 V 上拉）→ 现行结论（12 V 上拉+分压）”的链接。
7. **来源登记**：CHW-S056/S197 的“支持内容”已写 Vmax 5.25 V，建议补“仅 §2.1.4 PWM；§2.1.3 TACH 无 5.25 V 限制”，避免后续搜索时再次张冠李戴。

> 本次任务明确“不要修改仓库文件”，以上只是同步建议；实际修改应由主 agent 在快照之后统一提交。

---

## 8. 仍未核实 / NOT RUN

以下项目**没有**本次复核中核实，不能当成保证值：

1. **具体风扇型号的 TACH 电气参数**：Noctua NF-A8 PWM、Delta AFB0812HH 的 TACH VOL、漏电、最大灌电流、最小灌电流、每转脉冲数、输出管耐压。仓库只登记了 Intel 通用规范；`k-drive.md` L820 明确说 Delta AFB0812HH 的电气表是图片、未取得数值。**待按原厂 PDF/实测**。
2. **3.3 V 上拉是否被具体风扇允许**：Intel 规范只给 12 V 测试条件；3.3 V 下的 VOL/边沿/漏电/最小灌电流没有规范保证。**必须按型号实测**。
3. **风扇 TACH 的 VOL 规范值**：Intel §2.1.3 没有给；本文 0.4 V/0.8 V 是**假设值**（0.8 V 是 §2.3.1 PWM 的 VOL 上限，借用作最坏估计）。**待风扇手册**。
4. **12 V 轨的实际最坏值**：本文按 Intel §2.1.1 的 12 V ±5% = 12.6 V；若系统 12 V 适配器空载/瞬态更高，或走线/保险后有跌落，需按实际电源规格重算。**待电源规格与实测**。
5. **3.3 V 轨的实际下限**：本文引用仓库 Buck 算例 3.21–3.38 V；实际 TPS54202H 批次、反馈电阻公差、负载瞬态会改变下限。若 VDD 下限低于 3.21 V，10 kΩ/3.3 kΩ 的 1% 最坏 3.174 V 可能超过 VDD；需改 3.0 kΩ 或加钳位。**待 Buck 实测/最坏分析**。
6. **TVS/ESD 具体型号与钳位**：本文只给“VWM ≥12.6 V、低电容”的原则；具体 TVS 的 VWM/VBR/VC/电容、连接器位置、线长未选型。**待 EMC/ESD 设计**。
7. **MCU 具体引脚与输入捕获配置**：CH32V003 的定时器通道、重映射、输入滤波、中断延迟未逐脚核对；本文只按 Table 3-16 的 GPIO 阈值算余量。**待原理图/固件**。
8. **CH32V003 数据手册官方直链**：本次用 V1.3 镜像（akizuki）核对 Table 3-16；WCH 官方页面是 JS 动态页，未直接取得 PDF。**待从 WCH 官方下载核对版本/表格**。
9. **长线/EMC/地弹**：TACH 与 12 V 风扇线并行走线、启动 2.2 A 在地线上的压降、屏蔽/双绞、滤波电容对边沿的影响，均未实测。**NOT RUN**。
10. **实物/台架**：没有风扇、没有示波器、没有光学转速计；TACH 波形、VOL、上升时间、丢脉冲、堵转行为均未测。**NOT RUN**。
11. **EDA/PCB/固件/样机**：没有原理图、PCB、DRC、BOM、固件、样机、温箱/噪声/EMC/安规测试。**NOT RUN**。
12. **“符合 Intel 规范”的整机结论**：本文只核对接口电平；整机是否符合 Intel 4-wire 规范，还取决于风扇型号、PWM 频率/占空比、连接器、线材、启动电流等，不能由本文单独宣称。

---

## 9. 证据与参考

### 9.1 原厂/规范

1. Intel Corporation, *4-Wire Pulse Width Modulation (PWM) Controlled Fans Specification*, Revision 1.3, September 2005.
   - §2.1.1 Fan Input Voltage（12 V ±5%）
   - §2.1.2 Current（稳态 ≤1.5 A；启动 ≤2.2 A/1 s）
   - §2.1.3 Tachometer Output Signal（2 脉冲/转；开集电极/开漏；主板侧 12 V 上拉，最大 12.6 V）
   - §2.1.4 PWM Control Input Signal（25 kHz/21–28 kHz；VIL 0.8 V；Imax 5 mA；VMax 5.25 V 开路电压；风扇内部上拉 ≤5.25 V）
   - §2.3.1 Hardware Monitor Device PWM Output Signal（开漏/开集电极；5 mA/8 mA；最大电压能力 5.25 V；VOL 0.8 V）
   - §2.4 Considerations for Motherboard Designers（PWM 不得外加 pull-up/pull-down）
   - §3.1/§3.3（最大转速由厂商定；无信号=全速）
   - §4.1.6 Table 1（pin 1 GND 黑、pin 2 12 V 黄、pin 3 Sense 绿、pin 4 Control 蓝）
   - 仓库登记：`source-register.md` L188（CHW-S056，Intel 官方 URL）、L298（CHW-S197，镜像 URL）
2. WCH, *CH32V003 Datasheet*, V1.3.
   - §3.3.9 I/O port characteristics, Table 3-16 General-purpose I/O static characteristics：
     - VIH（标准/FT）min `0.22×(VDD−2.7)+1.55 V`；标准 max `VDD+0.3 V`，FT max `5.5 V`
     - VIL（标准/FT）max `0.19×(VDD−2.7)+0.65 V`；min −0.3 V
     - Vhys 150 mV typ；CI/O 5 pF typ
   - VDD=3.3 V 时：VIH(min)=1.682 V，VIL(max)=0.764 V。
   - 仓库登记：`i-mcu.md` L884（CHW-S161）

### 9.2 仓库内证据

- `design-hardware/references/common-hardware/applications/02-fan-control.md`（快照 L52–60、L84–90）
- `design-hardware/references/common-hardware/c-motion.md`（快照 L632–732、L855）
- `design-hardware/references/common-hardware/k-drive.md`（快照 L534–625、L811、L820）
- `design-hardware/references/source-register.md`（快照 L188、L298）
- `design-hardware/references/common-hardware/i-mcu.md`（快照 L60–75、L100–125、L884）
- `docs/evidence/common-hardware-2026-10-22/blind/B3.md`（历史原始回答 L35、L204、L228、L237–239）
- `docs/evidence/common-hardware-2026-10-22/blind/eval.md`（L19、L46–50）
- `docs/evidence/common-hardware-2026-10-22/audit/c-motion.md`（L255–296、L354）
- `docs/evidence/common-hardware-2026-10-22/audit/k-drive.md`（L363–376、L512–544）
- `docs/common-hardware-gap-analysis.md`（L113、L124、L349）
- `docs/common-hardware-report.md`

### 9.3 提交

- 固定快照：`4c9db61628e4a83f01acad1c53ea5c0665182325`（`4c9db61`）
- 历史修正提交：`4c9db61`（提交说明明确 “The 5.25 V limit is the PWM input, not tach”）
- 快照之后的交叉核对提交：`d97b6f3`（`fix(common-hardware): keep fan tach divider inside 12.6 V boundary`），**不属于固定快照 4c9db61**，只作独立交叉核对。

---

## 10. 总结

1. **TACH 上拉电压**：按 Intel Rev 1.3 §2.1.3，主板侧上拉是 **12 V，最大 12.6 V**；3.3 V MCU 必须用 12 V 上拉 + 分压/电平转换，不能把 12 V 直接进 GPIO。
2. **5.25 V**：不是 TACH 的限制；它是 **PWM 控制输入（pin 4）** 的 VMax（开路电压）和主板硬件监控器 PWM 输出的最大电压能力（§2.1.4、§2.3.1）。TACH（pin 3）没有 5.25 V 条目。
3. **快照的边界错误**：`10 kΩ/3.6 kΩ` 在 12.0 V 时是 3.18 V，但在规范的 12.6 V 最坏点是 **3.335 V**，超过 3.3 V；应改为 **10 kΩ/3.3 kΩ 1%**（3.126 V @12.6 V、2.977 V @12 V），或 10 kΩ/3.0 kΩ 留更多裕量。
4. **推荐电路**：`TACH ── R1 10 kΩ 1% ── +12 V`；`TACH ── R2 3.3 kΩ 1% ── GND`；`TACH ── R3 100 Ω ── MCU 捕获`；可选 `C1 1 nF` 到地；连接器侧 TVS/ESD（VWM ≥12.6 V）。PWM 用开漏缓冲/低边 FET，主板侧不加 pull-up/down。
5. **3.3 V 上拉**：只能作为具体风扇手册允许且实测通过的规范外简化；不能宣称 Intel 合规，且要注意 3.3 V/10 kΩ 只有 0.33 mA 灌电流。
6. **未核实**：具体风扇的 TACH VOL/漏电/最小灌电流/PPR、12 V 与 3.3 V 轨实际最坏值、TVS 选型、MCU 逐脚、长线/EMC、实物台架、EDA/PCB/固件/样机。以上均为 `待核实` 或 `NOT RUN`。
