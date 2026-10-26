# HX711 供电模式复核：5 V VSUP + AVDD=5 V 桥激励

> 复核对象：`C:\Users\jlc\work\hardware-design-skill`，固定提交 `4c9db61`（完整 SHA：`4c9db61628e4a83f01acad1c53ea5c0665182325`）。
> 复核日期：2026-10-22。
> 证据级别：原厂手册 + 仓库文本 + 独立计算；未做样机、未实测，相关验证项标 `NOT RUN`。
> 范围说明：只复核 HX711 供电模式与盲测 B2 的评分依据；不扩大内容、不合并 PR #5、不修改仓库文件。S1 仍保持“连接级证据”，未升级为功能验证。

## 0. 结论（先给答案）

1. **允许，但仅限旁路模式**：HX711 可以用 5 V VSUP、把 AVDD 直接接 5 V 给桥激励，前提是**不使用片内模拟稳压器**，按手册 p.4 “Power Supply Options” 的旁路接法：`VSUP` 接 `AVDD` 或 `DVDD` 中较高者，`VFB` 接 GND，`BASE` 为 NC，`VBG` 的 0.1 µF 不需要。5 V 在 AVDD/VSUP 的 2.6–5.5 V 工作范围内（p.3 Table 2；VSUP 引脚说明 p.2 写 2.7–5.5 V）。
2. **旁路模式逐脚**：`VSUP=AVDD=5 V`；`BASE=NC`；`VFB=AGND`；`VBG` 的 0.1 µF 不装；`AVDD=5 V` 接桥 `E+`；`AGND` 接桥 `E−`；`DVDD` 接 MCU 电源（必须与 MCU 同域，通常 3.3 V）；`XI=GND` 用内部振荡器；`RATE=GND` 选 10 SPS、`RATE=DVDD` 选 80 SPS；`PD_SCK`/`DOUT` 接 MCU；`XO=NC`；`INB±` 未用（手册未规定接法，见 §8）。
3. **如果仍用片内稳压器，则不允许 AVDD 直接接 5 V**：p.4 要求 `VAVDD` 至少比 `VSUP` 低 100 mV。5 V 标称下 `AVDD ≤ 4.9 V`；按 USB 5 V±5% 的最低值 4.75 V 算，`AVDD ≤ 4.65 V`。此时 AVDD 由 `VAVDD = VBG×(R1+R2)/R1` 设定，`VBG` typ 1.25 V，外部 PNP（Fig.1 典型 S8550）+ R1/R2。5 V→3.3 V 或 5 V→4.3 V 都可，但外部调整管的实际压降/功耗必须核算。
4. **评分依据错误**：`docs/evidence/common-hardware-2026-10-22/blind/eval.md` 的 B2 评分把“AVDD 直接接 5 V、VSUP=5 V”判为违反 100 mV 约束。该约束只在“使用片内稳压器”的段落里有条件成立；B2 的 5 V 分支在引脚表里明确 `BASE=NC`、`VFB=AGND`，属于旁路模式，因此**不违反**。该扣分应撤销；P0-3 的通用写法 `AVDD ≤ VSUP−100 mV` 应改为“内部稳压模式专用”。

## 1. 实际读过的文件/小节

| 文件/资料 | 版本/快照 | 实际读过的小节 | 用途 |
|---|---|---|---|
| `design-hardware/references/common-hardware/d-force.md` | `4c9db61` | §D1（44–166 行），重点 77–83、91–101、105、162 | HX711 两种供电模式、逐脚、算例、来源 |
| `design-hardware/references/common-hardware/applications/05-electronic-scale.md` | `4c9db61` | 3、27、41–44、63–80、90–105、111–113 行 | 电子秤应用、内部稳压选择、功耗算例 |
| `design-hardware/references/common-hardware/f-input-protection.md` | `4c9db61` | 205 行 | USB VBUS 4.75–5.25 V（5 V±5%） |
| `design-hardware/references/source-register.md` | `4c9db61` | 190 行 | CHW-S061 HX711 来源登记 |
| `docs/evidence/common-hardware-2026-10-22/blind/eval.md` | `4c9db61` | 15–18、35–42、94–98、119–126 行 | B2 评分与“应修”条目 |
| `C:\Users\jlc\work\hds-common-scratch\sources\d-force\hx711.pdf` | Avia HX711，9 页，版本未标；SHA-256 `6050e88a5e938ff9ac3292bfbc9fea2afa0ca73d1a649d5398ae8de5ab7c017e`；PDF 元数据 creation date 2009-06-26 | p.1–5：p.1 描述/Fig.1；p.2 Table 1；p.3 Table 2；p.4 Power Supply Options；p.5 Reset and Power-Down | 原厂手册依据 |
| `C:\Users\jlc\work\hds-common-scratch\sources\d-force\lcae.pdf` | Omega LCAE F-80/F-81，版本未标；SHA-256 `a2af4831db18ee43a78a83a2767580b7e1c9ab7faa097f0c23cfc1b754db2bb8` | p.1 Specifications | 2 mV/V、350 Ω、10 V（15 V max）例子 |
| `https://cdn.sparkfun.com/datasheets/Sensors/ForceFlex/hx711_english.pdf` | 与本地 `hx711.pdf` 逐字节一致（SHA-256 相同） | p.1–5 同上 | 独立镜像核对 |

说明：

- 仓库工作树在复核期间从 `4c9db61` 继续移动到 `d97b6f3`、`662a7ab`（另一会话的提交）。本报告所有仓库引用都用 `git show 4c9db61:<path>` 固定，不引用后续提交。
- 本地 HX711 PDF 与 SparkFun 镜像的 SHA-256 完全相同（`6050e88a…`），说明本地缓存不是二次编辑版；但手册本身没有印版本号/日期，见 §8。
- 本次没有使用训练记忆中的“大概值”；所有数值来自上述手册页/表或仓库行，计算值在 §5、§7 标明。

## 2. 问题 1：5 V VSUP + AVDD 直接接 5 V 给桥激励，是否允许？

### 2.1 手册原文（p.4 “Power Supply Options”）

> “When using internal analog supply regulator, the dropout voltage of the regulator depends on the external transistor used. The output voltage is equal to VAVDD=VBG*(R1+R2)/ R1 (Fig. 1). This voltage should be designed with a minimum of 100mV below VSUP voltage.”
>
> “If the on-chip analog supply regulator is not used, the VSUP pin should be connected to either AVDD or DVDD, depending on which voltage is higher. Pin VFB should be connected to Ground and pin BASE becomes NC. The external 0.1uF bypass capacitor shown on Fig. 1 at the VBG output pin is then not needed.”

关键在条件句：100 mV 要求写在“**When using internal analog supply regulator**”这一段里；下一段“**If the on-chip analog supply regulator is not used**”给出的是另一套引脚接法，没有再提 100 mV。因此：

- **旁路模式**（片内稳压器不用）：`VSUP` 接 `AVDD` 或 `DVDD` 中较高者，`AVDD` 可由外部 5 V 直接供电；5 V 系统 `VSUP=AVDD=5 V` 是手册明确允许的。
- **内部稳压模式**：`AVDD` 是片内稳压器的输出，必须比 `VSUP` 低至少 100 mV；5 V VSUP 下不能把 `AVDD` 接 5 V。

### 2.2 电压范围核对

| 项目 | 数值 | 依据 | 判定 |
|---|---:|---|---|
| AVDD、VSUP 工作范围（Table 2） | 2.6–5.5 V | p.3 Table 2 “Power supply voltage: AVDD, VSUP 2.6 … 5.5 V” | 5 V 在范围内 |
| VSUP 引脚说明 | 2.7–5.5 V | p.2 Table 1 “Regulator supply: 2.7 ~ 5.5V” | 5 V 在范围内；与 Table 2 的 2.6 V 下限有 0.1 V 不一致，按更严格的 2.7 V 用 |
| USB VBUS | 4.75–5.25 V | 仓库 `f-input-protection.md:205` “VBUS：source 4.75–5.25 V（5 V ±5%）” | 5.25 V < 5.5 V，工作范围内余量 0.25 V |
| 传感器激励上限 | 按具体型号 | 仓库 `d-force.md:70` 的 LCAE 例：10 V 推荐、15 V max；LCAE p.1 同 | LCAE 例的 15 V max 允许 5 V；10 V 是推荐值，5 V 属降额使用；通用 5 kg 传感器必须查规格，不能假设 |

注意：手册只给“工作范围”，**没有给绝对最大额定值（Absolute Maximum Ratings）**。5.25 V 在 2.6/2.7–5.5 V 工作范围内，但插拔瞬态、ESD、TVS 钳位后的电压是否超过器件耐压，手册没有数字，必须外部钳位并实测（§8）。

### 2.3 桥中点共模核对

HX711 的共模输入范围（p.3 Table 2）：

`V_CM(min) = AGND + 1.2 V`，`V_CM(max) = AVDD − 1.3 V`。

5 V 旁路、桥上下臂对称时：

`V_CM = AVDD/2 = 5.00/2 = 2.50 V`。

范围：`1.20 V … 3.70 V`。

余量：向下 `2.50 − 1.20 = 1.30 V`；向上 `3.70 − 2.50 = 1.20 V`。

3.3 V 内部稳压时：`V_CM = 1.65 V`；范围 `1.20 … 2.00 V`；余量向下 `0.45 V`、向上 `0.35 V`。所以 5 V AVDD 的共模余量反而更大，不是“5 V 一定更危险”。真正要重算的是传感器自热、输入满量程和 5 V 轨噪声。

### 2.4 满量程、码值与噪声核对

以 5 kg、2 mV/V、350 Ω 桥为例（传感器参数是假设值，必须按实际型号核对；LCAE 10 kg 例是 2 mV/V、350 Ω，但 LCAE 的 <6 kgf 档是 1 mV/V，5 kg 不是 LCAE 标准档，见 §8）：

- 满量程输出：`V_FS = S × AVDD = 2 mV/V × 5 V = 10.00 mV`。
- 增益 128 的输入满量程：`±0.5 × AVDD / GAIN = ±0.5 × 5 / 128 = ±19.53125 mV`（手册 p.1/p.4 把它圆整写成 ±20 mV）。
- 利用率：`10.00 / 19.53125 = 51.20%`。
- 正半轴码值：`0.5120 × 2^23 = 0.5120 × 8,388,608 = 4,294,967` 码。
- 每克码值：`4,294,967 / 5,000 g = 858.99 码/g`，即 `1.164 mg/码`。
- 噪声：增益 128、10 SPS 的输入噪声 typ 50 nV rms（p.3 Table 2）。5 kg 处灵敏度 `10 mV / 5 kg = 2.00 µV/g`；折合 `50 nV / 2.00 µV/g = 0.0250 g rms`；8 次平均 `0.0250 / √8 = 0.00884 g rms`。50 nV 是 typ，不是 max。

对比 3.3 V 和 4.3 V（同一 2 mV/V、5 kg 桥）：

| AVDD | V_FS | 增益 128 FS | 利用率 | 码值 | 噪声（10 SPS，typ） | 8 次平均 |
|---:|---:|---:|---:|---:|---:|---:|
| 3.3 V | 6.60 mV | ±12.890625 mV | 51.20% | 4,294,967 | 0.0379 g rms | 0.0134 g rms |
| 4.3 V | 8.60 mV | ±16.796875 mV | 51.20% | 4,294,967 | 0.0291 g rms | 0.0103 g rms |
| 5.0 V | 10.00 mV | ±19.53125 mV | 51.20% | 4,294,967 | 0.0250 g rms | 0.00884 g rms |

结论：因为桥激励和 ADC 参考同为 AVDD（由满量程公式 `±0.5(AVDD/GAIN)` 和“没有独立 VREF 引脚”推得，见 §8），**比率测量下码值比例不随 AVDD 改变**；5 V 的好处是绝对信号更大、折合到克的输入噪声更小（0.025 g vs 0.038 g，改善 1.515 倍），代价是桥自热更大（见 §5.5）。

### 2.5 5 V 旁路的系统代价

- 桥电流：`I_EXC = 5 / 350 = 14.2857 mA`；桥功耗 `P = 5² / 350 = 71.4286 mW`。
- 3.3 V 时：`I_EXC = 9.4286 mA`；`P = 31.1143 mW`。5 V 的桥功耗是 3.3 V 的 `71.4286 / 31.1143 = 2.296` 倍。
- HX711 自身：模拟 `1400 µA` typ + 数字 `100 µA` typ = `1.5 mA` typ（p.3 Table 2）；5 V 时约 `7.5 mW`。
- 5 V 总电流（旁路，不含 MCU/显示）：`14.2857 + 1.5 = 15.7857 mA` typ；3.3 V 时 `9.4286 + 1.5 = 10.9286 mA` typ。
- 传感器必须能承受 5.25 V（USB 上限）而不是只承受 5.0 V；LCAE 例 15 V max 可以，通用 5 kg 传感器必须查。
- 5 V 轨的纹波会同时加到桥激励和 ADC 参考；比率测量能抵消一阶共模，但桥自热、传感器漂移和 5 V 轨的瞬时跌落不会自动抵消，必须实测（`NOT RUN`）。

**问题 1 结论：允许，条件是旁路模式 + 传感器激励上限 ≥5.25 V + 共模/满量程/自热复核；不是“任何 5 V 模块都能直接接”。**

## 3. 问题 2：旁路模式的逐脚接法

### 3.1 逐脚表

| 脚 | 名称 | 旁路模式接法 | 依据/说明 |
|---:|---|---|---|
| 1 | VSUP | 接 5 V（与 AVDD 同节点） | p.4：VSUP 接 AVDD 或 DVDD 中较高者；本设计 AVDD=5 V > DVDD=3.3 V，故接 AVDD |
| 2 | BASE | NC | p.4：BASE becomes NC；p.2：NC when not used |
| 3 | AVDD | 5 V；接桥 `E+`；10 µF + 0.1 µF 到 AGND | p.4：外部电源直接供 AVDD；Fig.1 画 10 µF；0.1 µF 为良好实践，手册未逐值规定 |
| 4 | VFB | 接 AGND | p.4：VFB 接 Ground；p.2：connect to AGND when not used |
| 5 | AGND | 模拟地星点；桥 `E−` 回此点 | p.2；Fig.1 |
| 6 | VBG | 0.1 µF 不装；手册只说不装该电容，未规定引脚其他接法 | p.4：旁路时 VBG 的 0.1 µF 不需要；手册没有要求把 VBG 接地 |
| 7 | INA− | 桥 `S−`（经对称 RC） | p.2；Fig.1 |
| 8 | INA+ | 桥 `S+`（经对称 RC） | p.2；Fig.1 |
| 9 | INB− | 未用；手册未规定，建议接已知电位（如 AGND），待核实 | p.2 只给功能名；手册没有“未用输入接法”的明文 |
| 10 | INB+ | 同上 | 同上 |
| 11 | PD_SCK | MCU GPIO；25/26/27 个脉冲选 A/128、B/32、A/64 | p.2；p.4 Table 3 |
| 12 | DOUT | MCU GPIO | p.2 |
| 13 | XO | NC | p.2：NC when not used |
| 14 | XI | 接 GND，启用内部振荡器 | p.2；p.4 “By connecting pin XI to Ground, the on-chip oscillator is activated” |
| 15 | RATE | GND=10 SPS；DVDD=80 SPS | p.2；p.4 |
| 16 | DVDD | MCU 电源（3.3 V 或 5 V，必须与 MCU 同域） | p.4：DVDD should be the same power supply as the MCU power supply |

### 3.2 接线示意

```text
USB-C 5 V ──┬── VSUP(1) ── AVDD(3) ── E+ ── 桥
            │        │
            │       10 µF + 0.1 µF
            │        │
            │       AGND(5) ── E− ── 桥
            │
            └── TPS7A02 3.3 V ── DVDD(16) / MCU / OLED

桥 S+ ── 对称 RC ── INA+(8)
桥 S− ── 对称 RC ── INA−(7)
PD_SCK(11) / DOUT(12) ── MCU
XI(14) ── GND；XO(13) ── NC；RATE(15) ── GND 或 DVDD
BASE(2) ── NC；VFB(4) ── AGND；VBG(6) ── 不装 0.1 µF
```

注意：不要把 `AVDD=5 V` 和 `VSUP=5 V` 画成经过 S8550/R1/R2 的内部稳压拓扑；旁路模式必须把 `BASE` 断开、`VFB` 接地。如果保留调整管和反馈分压，片内误差放大器仍可能驱动 `BASE`，状态不受手册保证（这是按 p.4 接法推断的，手册没有展开说明）。

### 3.3 DVDD 逻辑域

- p.4 明确 `DVDD` 应与 MCU 同电源。3.3 V MCU → `DVDD=3.3 V`；5 V MCU → `DVDD=5 V`。
- 不要用 3.3 V MCU 配 5 V DVDD 而不核对 VIH/DOUT 高电平：手册没有给 VIH/VIL 数字，只给“DVDD 与 MCU 同电源”的设计要求。DOUT 高电平接近 DVDD（推断）；5 V DVDD 的 DOUT 会到 5 V，3.3 V 非 5 V 容忍脚不能直连。
- 反过来，3.3 V DVDD 时，3.3 V MCU 驱动 PD_SCK 是同域，最简单。

## 4. 问题 3：改用内部稳压，5 V VSUP 下 AVDD 有什么约束？

### 4.1 公式与硬约束

手册 p.4：

`VAVDD = VBG × (R1 + R2) / R1`

其中 `VBG` 的 typ 值为 `1.25 V`（p.3 Table 2 “Reference bypass (VBG) 1.25 V”，只有 TYP，没有 MIN/MAX）。

内部稳压模式下必须同时满足：

1. **100 mV 余量**：`VAVDD ≤ VSUP − 0.100 V`（p.4）。
2. **AVDD 工作范围**：`2.6 V ≤ VAVDD ≤ 5.5 V`（p.3 Table 2；p.2 AVDD 引脚说明 2.6–5.5 V）。
3. **VSUP 工作范围**：`2.7 V ≤ VSUP ≤ 5.5 V`（p.2 Table 1；Table 2 写 2.6 V，取更严格的 2.7 V）。
4. **外部调整管**：PNP（Fig.1 典型 S8550）的发射极接 VSUP、集电极接 AVDD、基极接 BASE；它必须在 `I_EXC + I_AVDD + I_R1R2` 下提供小于 `VSUP − VAVDD` 的压降。手册只说“dropout depends on the external transistor”，**没有给最大压降/热阻**。

### 4.2 5 V VSUP 下的 AVDD 窗口

按 `VAVDD ≤ VSUP − 0.1 V`：

| VSUP 条件 | VSUP | AVDD 允许上限（100 mV 规则） | AVDD 允许下限 | 说明 |
|---|---:|---:|---:|---|
| 标称 5.00 V | 5.00 V | 4.90 V | 2.60 V | 只按标称算 |
| USB 最低 4.75 V | 4.75 V | 4.65 V | 2.60 V | 全输入范围保持 100 mV 的稳健上限 |
| USB 最高 5.25 V | 5.25 V | 5.15 V | 2.60 V | 最高轨不是限制项；最低轨才是 |
| 3×AAA 标称 4.50 V | 4.50 V | 4.40 V | 2.60 V | 备选电池 |
| 3×AAA 截止 3.50 V | 3.50 V | 3.40 V | 2.60 V | 3.3 V 设定只剩 0.19 V 余量，见 §5.8 |

因此，**5 V VSUP、内部稳压、AVDD 直接接 5 V 不成立**：5.00 V 时上限 4.90 V，4.75 V 时上限 4.65 V，5 V 都超了。5 V→4.3 V 和 5 V→3.3 V 都满足 100 mV；5 V→4.3 V 在 USB 最低 4.75 V 时余量 0.45 V，5 V→3.3 V 余量 1.44 V。

### 4.3 R1/R2 设定示例

| 目标 AVDD | (R1+R2)/R1 | R2/R1 | R1 | R2 | 实际 VAVDD（VBG=1.25 V typ） | 分压电流 |
|---:|---:|---:|---:|---:|---:|---:|
| 3.300 V | 2.640 | 1.640 | 20.0 kΩ | 32.8 kΩ | 3.300 V | 62.5 µA |
| 3.3125 V（仓库 20k/33k 例） | 2.650 | 1.650 | 20.0 kΩ | 33.0 kΩ | 3.3125 V | 62.5 µA |
| 4.300 V | 3.440 | 2.440 | 20.0 kΩ | 48.8 kΩ | 4.300 V | 62.5 µA |

分压电流：`I_R1R2 = VBG / R1 = 1.25 / 20 kΩ = 62.5 µA`（因为 VFB 被调节到 VBG）。这个电流从 AVDD 经 R2+R1 到 AGND，必须计入调整管电流。

**注意 Fig.1 的 R1/R2 位置与公式的表面矛盾**：p.4 公式是 `VAVDD = VBG×(R1+R2)/R1`，这意味着 R1 是 VFB 到 AGND 的下臂、R2 是 VAVDD 到 VFB 的上臂；但 Fig.1 中 R2 画在 VFB 左侧（朝一个向左的三角符号）、R1 画在 VFB 右侧（接 VAVDD），看起来 R1 是上臂、R2 是下臂。两者至少有一处标注不一致。设计时以 p.4 公式为准，按“R1 下臂、R2 上臂”选值，并在样机上实测 AVDD；不要把 Fig.1 的左右位置当作引脚级依据（§8）。

### 4.4 内部稳压模式逐脚表

| 脚 | 名称 | 内部稳压模式接法 | 依据/说明 |
|---:|---|---|---|
| 1 | VSUP | 5 V | p.4；p.2 2.7–5.5 V |
| 2 | BASE | 接外部 PNP 基极 | p.2 “Regulator control output”；Fig.1 |
| 3 | AVDD | 稳压器输出；接桥 `E+`；10 µF 到 AGND | p.4 公式；Fig.1 |
| 4 | VFB | 接 R1/R2 分压中点 | p.2 “Regulator control input”；p.4 公式 |
| 5 | AGND | 模拟地 | p.2 |
| 6 | VBG | 0.1 µF 到 AGND | p.1/p.4 Fig.1；p.3 VBG typ 1.25 V |
| 7 | INA− | 桥 `S−` | p.2 |
| 8 | INA+ | 桥 `S+` | p.2 |
| 9 | INB− | 未用；建议接已知电位，待核实 | p.2 无未用接法明文 |
| 10 | INB+ | 同上 | 同上 |
| 11 | PD_SCK | MCU GPIO | p.2 |
| 12 | DOUT | MCU GPIO | p.2 |
| 13 | XO | NC | p.2 |
| 14 | XI | GND（内部振荡器） | p.2；p.4 |
| 15 | RATE | GND=10 SPS；DVDD=80 SPS | p.2；p.4 |
| 16 | DVDD | MCU 电源 | p.4 |

外部 PNP 接法（Fig.1）：发射极接 VSUP，集电极接 AVDD，基极接 BASE。R1 从 VFB 到 AGND，R2 从 VFB 到 AVDD（按 p.4 公式的定义；Fig.1 标注见 §4.3 的注意）。VBG 用 0.1 µF 旁路到 AGND。

### 4.5 内部稳压模式的掉电行为

p.5 “Reset and Power-Down”：

> “When internal regulator is used for HX711 and the external transducer, both HX711 and the transducer will be powered down.”

即内部稳压模式下，`PD_SCK` 高 >60 µs 会把 HX711 和桥一起掉电。旁路模式下，桥接在外部 5 V 上，HX711 掉电不能切断桥激励；如果电池供电需要桥掉电，必须外加负载开关（这是按拓扑推断，手册只明说了内部稳压模式，见 §8）。

## 5. 计算过程（逐步、带单位）

### 5.1 电压范围

- 标称：`VSUP = 5.00 V`，`AVDD = 5.00 V`。
- USB 5 V±5%：`4.75 V ≤ VBUS ≤ 5.25 V`（仓库 `f-input-protection.md:205`）。
- HX711 工作范围：`AVDD, VSUP = 2.6 … 5.5 V`（p.3 Table 2）；VSUP 引脚说明 `2.7 … 5.5 V`（p.2 Table 1）。
- 最高余量：`5.50 − 5.25 = 0.25 V`。
- 结论：5 V 标称和 USB 极限都在工作范围内；绝对最大额定值未给，见 §8。

### 5.2 旁路模式的 100 mV 规则

- 旁路模式：`VSUP = max(AVDD, DVDD) = max(5.00, 3.30) = 5.00 V`。
- `VSUP − AVDD = 5.00 − 5.00 = 0.00 V`。
- 100 mV 规则只适用于“使用片内稳压器”的段落（p.4），旁路段落没有这个要求；所以 0.00 V 不是违规。
- 如果误用内部稳压模式：`5.00 − 5.00 = 0.00 V < 0.100 V`，违规；这正是不能把两种模式混为一谈的原因。

### 5.3 共模

- 5 V：`V_CM = 5.00 / 2 = 2.50 V`；范围 `AGND+1.20` 到 `AVDD−1.30` = `1.20 … 3.70 V`；向下余量 `1.30 V`，向上余量 `1.20 V`。
- 3.3 V：`V_CM = 3.30 / 2 = 1.65 V`；范围 `1.20 … 2.00 V`；向下余量 `0.45 V`，向上余量 `0.35 V`。
- 4.3 V：`V_CM = 2.15 V`；范围 `1.20 … 3.00 V`；向下余量 `0.95 V`，向上余量 `0.85 V`。
- 结论：5 V 的共模余量最大；3.3 V 的上侧余量只有 0.35 V，桥/走线不对称时要留神。

### 5.4 满量程、码值、分辨率

以 5 kg、2 mV/V 为例：

- `V_FS = 2 mV/V × 5.00 V = 10.00 mV`。
- 增益 128：`FS = ±0.5 × 5.00 / 128 = ±19.53125 mV`；利用率 `10.00 / 19.53125 = 0.5120 = 51.20%`。
- 正半轴码值：`0.5120 × 2^23 = 0.5120 × 8,388,608 = 4,294,967` 码。
- 每克码值：`4,294,967 / 5,000 = 858.99 码/g`；每码 `5,000 / 4,294,967 = 1.164 mg/码`。
- 增益 64：`FS = ±39.0625 mV`；利用率 `25.60%`；码值 `2,147,484`；`2.328 mg/码`。
- 增益 32（B 通道）：`FS = ±78.125 mV`；利用率 `12.80%`；码值 `1,073,742`；`4.657 mg/码`。
- 手册 p.1/p.4 把 5 V 下的 128/64/32 增益圆整写成 `±20 mV / ±40 mV / ±80 mV`；精确公式给的是 `±19.53125 / ±39.0625 / ±78.125 mV`，本报告用精确值。

3.3 V 和 4.3 V 的同一 2 mV/V、5 kg 桥：

- 3.3 V：`V_FS = 6.60 mV`；`FS = ±12.890625 mV`；利用率 `51.20%`；码值 `4,294,967`；`1.164 mg/码`。
- 4.3 V：`V_FS = 8.60 mV`；`FS = ±16.796875 mV`；利用率 `51.20%`；码值 `4,294,967`；`1.164 mg/码`。
- 结论：比率测量下，AVDD 从 3.3 V 变到 5 V，码值比例不变；变化的是绝对信号、噪声折合到克、桥自热和共模余量。

### 5.5 桥电流、功耗、自热比较

- 5 V：`I_EXC = 5.00 / 350 = 14.2857 mA`；`P = 5.00² / 350 = 71.4286 mW`；每臂约 `17.86 mW`。
- 4.3 V：`I_EXC = 4.30 / 350 = 12.2857 mA`；`P = 4.30² / 350 = 52.8286 mW`。
- 3.3 V：`I_EXC = 3.30 / 350 = 9.4286 mA`；`P = 3.30² / 350 = 31.1143 mW`。
- 5 V / 3.3 V 功耗比：`71.4286 / 31.1143 = 2.296`。
- 5 V / 4.3 V 功耗比：`71.4286 / 52.8286 = 1.352`。
- 传感器允许的激励上限和自热必须按具体型号核对；LCAE 例的 10 V 推荐/15 V max 说明 5 V 对它是降额使用，但不能推广到所有 5 kg 传感器。

### 5.6 噪声折合到克

- 5 V：灵敏度 `10.00 mV / 5 kg = 2.00 µV/g`；`50 nV / 2.00 µV/g = 0.0250 g rms`；8 次平均 `0.00884 g rms`。
- 4.3 V：灵敏度 `8.60 mV / 5 kg = 1.72 µV/g`；`50 nV / 1.72 µV/g = 0.0291 g rms`；8 次平均 `0.0103 g rms`。
- 3.3 V：灵敏度 `6.60 mV / 5 kg = 1.32 µV/g`；`50 nV / 1.32 µV/g = 0.0379 g rms`；8 次平均 `0.0134 g rms`。
- 50 nV 是 p.3 Table 2 的 TYP，不是 MAX；不能拿它保证 0.1 g 或 1 g 准确度。

### 5.7 内部稳压的调整管功耗

调整管电流不是只有桥电流，还包括 HX711 模拟电流 `I_AVDD = 1.4 mA` typ（p.3 Table 2 “Analog supply current (including regulator) 1400 µA”）和分压电流 `I_R1R2 = 62.5 µA`（§4.3）。下面把 1.4 mA 全部计入调整管电流是保守算法；手册没有拆分“稳压器自身静态电流”和“AVDD 负载电流”：

`I_pass = I_EXC + I_AVDD + I_R1R2`

`P_PNP = (VSUP − VAVDD) × I_pass`

以仓库 05 的 20 kΩ/33 kΩ → `VAVDD = 3.3125 V` 为例：

- `I_EXC = 3.3125 / 350 = 9.4643 mA`。
- `I_pass = 9.4643 + 1.4000 + 0.0625 = 10.9268 mA`。
- 5.00 V：`P_PNP = (5.00 − 3.3125) × 10.9268 mA = 1.6875 V × 10.9268 mA = 18.439 mW`。
- 4.75 V：`P_PNP = 1.4375 × 10.9268 = 15.707 mW`。
- 5.25 V：`P_PNP = 1.9375 × 10.9268 = 21.171 mW`。
- 3.50 V（3×AAA 截止）：`P_PNP = 0.1875 × 10.9268 = 2.049 mW`，但压差只有 0.1875 V，见 §5.8。

以 20 kΩ/48.8 kΩ → `VAVDD = 4.300 V` 为例：

- `I_EXC = 4.300 / 350 = 12.2857 mA`。
- `I_pass = 12.2857 + 1.4000 + 0.0625 = 13.7482 mA`。
- 5.00 V：`P_PNP = (5.00 − 4.30) × 13.7482 = 0.70 × 13.7482 = 9.624 mW`。
- 4.75 V：`P_PNP = 0.45 × 13.7482 = 6.187 mW`。
- 5.25 V：`P_PNP = 0.95 × 13.7482 = 13.061 mW`。

**仓库 05 第 105 行的公式 `(VSUP−AVDD)×I_EXC` 少算了 `I_AVDD + I_R1R2`**：以 3.3125 V/5 V 为例，按 I_EXC 算 `1.6875 × 9.4643 = 15.97 mW`，按完整电流算 `18.44 mW`，低估约 13.4%。功率绝对值不大，但公式应改完整。

### 5.8 3×AAA 备选的截止电压

仓库 05 的备选是 3×AAA，标称 4.5 V，截止 3.5 V（05 第 20/99 行）。用 20 kΩ/33 kΩ、`VAVDD=3.3125 V`：

- 标称 4.5 V：`VSUP − VAVDD = 4.50 − 3.3125 = 1.1875 V`，满足 100 mV。
- 截止 3.5 V：`VSUP − VAVDD = 3.50 − 3.3125 = 0.1875 V`，仍大于 0.100 V，但只剩 87.5 mV 的额外余量。
- 调整管必须在 `I_pass = 10.9268 mA` 下把压降做到小于 0.1875 V；手册没有给 S8550 的 Vce(sat) 曲线，`待核实`。如果实际管子需要 0.2–0.3 V，3.5 V 截止前就会失去稳压，3×AAA 备选的可用容量会缩水。
- 05 第 105 行写“1.2 V（AAA）”是用 4.5 V 标称算的，不是最低电压；应补“按 3.5 V 截止复核，实际只有 0.19 V”。

### 5.9 5 V 直供的 HX711 自身功耗

- 模拟：`5.00 V × 1.400 mA = 7.000 mW` typ。
- 数字：`3.30 V × 0.100 mA = 0.330 mW` typ。
- 合计：约 `7.33 mW` typ；SOP-16 的 θJA 手册未给，不能据此算结温，`待核实`。
- 桥 71.43 mW + HX711 7.33 mW ≈ 78.76 mW（不含 MCU/显示）；比 3.3 V 方案的 31.11 + 4.95 ≈ 36.06 mW 高约 2.18 倍。

## 6. 修改前后结果（保留 4c9db61 原文）

> 本节只列修正建议，不修改仓库文件；原文逐字保留，便于对照。

### 6.1 `d-force.md`

| 位置 | 4c9db61 原文 | 问题 | 建议修正 |
|---|---|---|---|
| 第 79 行 | “**内部稳压（默认）**：`VSUP` 2.7–5.5 V、`AVDD` 2.6–5.5 V …” | 手册没有说内部稳压是“默认”；Fig.1 只是典型应用，模式由外部引脚决定 | 改为“**内部稳压（Fig.1 典型应用）**”；并注明“AVDD 的 2.6–5.5 V 是器件工作范围，内部稳压模式下还必须满足 AVDD ≤ VSUP−0.1 V” |
| 第 80 行 | “此时 `AVDD=VSUP`（或 DVDD）” | 如果 VSUP 接 DVDD（DVDD 较高），AVDD 并不等于 DVDD；正确关系是 VSUP 接 AVDD 或 DVDD 中较高者 | 改为“此时 VSUP 接 AVDD 或 DVDD 中较高者；若 VSUP 接 AVDD，则 AVDD=VSUP；若 VSUP 接 DVDD，则 VSUP=DVDD，AVDD 仍是独立轨” |
| 第 80 行 | “5 V 系统可 `VSUP=AVDD=5 V`，但桥/ADC 共模、自热和输入范围要按 5 V 重算” | 结论正确；缺“传感器激励上限 ≥5.25 V”和“DVDD 与 MCU 同域”两个条件 | 保留，补两句条件；并把“共模”具体化为 `1.2–3.7 V`、`V_CM=2.5 V` |
| 第 81 行 | “不要看到‘AVDD=5 V’就判违规——只有内部稳压模式才要求 100 mV 余量” | 正确，且与 p.4 一致；这是仓库里最准确的表述 | 保留；建议在句末加“(p.4 Power Supply Options)”以便审计引用 |

### 6.2 `05-electronic-scale.md`

| 位置 | 4c9db61 原文 | 问题 | 建议修正 |
|---|---|---|---|
| 第 77 行 | “比率测量时它同时是 ADC 参考，不能用外部 5 V 单独激励” | 过度一般化：本设计是内部稳压 3.3 V，不能用外部 5 V 单独激励；但旁路模式允许 `VSUP=AVDD=5 V` | 改为“本设计内部稳压模式下不能用外部 5 V 单独激励；若改旁路模式（VSUP=AVDD=5 V、VFB=GND、BASE=NC），允许外部 5 V 激励” |
| 第 105 行 | “外部调整管要承受 `(VSUP−AVDD)×I_EXC` 的功耗” | 少算 HX711 模拟电流 1.4 mA 和分压电流 62.5 µA | 改为 `(VSUP−AVDD)×(I_EXC+I_AVDD+I_R1R2)`；3.3125 V/5 V 例为 18.44 mW，不是 15.97 mW |
| 第 105 行 | “`VSUP−AVDD=1.7 V`（USB）或 `1.2 V`（AAA），满足 ≥100 mV” | 1.2 V 是 4.5 V 标称；3×AAA 截止 3.5 V 时只有 0.1875 V | 补“按 3.5 V 截止复核：0.1875 V；调整管实际压降必须小于此值，待核实” |
| 第 63 行 | 框图 “USB-C 5 V ── HX711 VSUP(1) ── AVDD(3)=3.3 V ── EXC+ ── 桥” | 画成 VSUP 与 AVDD 直连，容易被读成旁路；本设计是内部稳压，中间应有 S8550/R1/R2 | 改画为 `USB 5V ── VSUP(1) ── [S8550 + R1/R2] ── AVDD(3)=3.3V ── E+`；或明确标注“内部稳压，S8550/R1/R2 未画出” |
| 第 27/42 行 | “HX711 `VSUP=5 V`、`AVDD=DVDD=3.3 V`” | 数值本身对（内部稳压），但没有在句内点明是稳压器输出，容易与“AVDD 直接接 3.3 V”混淆 | 补“AVDD 为内部稳压输出，不是直接短接 3.3 V；DVDD 是 LDO 的 3.3 V，二者同值不同网络” |

### 6.3 `blind/eval.md` 评分依据

| 位置 | 4c9db61 原文 | 问题 | 建议修正 |
|---|---|---|---|
| 第 18 行 | “5 V AVDD 分支违反 HX711 的 VSUP−100 mV 约束” | 把内部稳压模式的约束套到旁路模式；B2 的 5 V 分支是 `BASE=NC`、`VFB=AGND` 的旁路接法 | 改为“5 V AVDD 分支在旁路模式下允许；100 mV 约束只适用于内部稳压模式。应检查共模、传感器激励上限、DVDD 逻辑，而不是用 100 mV 规则扣分” |
| 第 39 行 | “它把 `AVDD` 直接接 5 V、`VSUP=5 V` 当作可用分支，实际上不成立” | 同上；且引用的 `d-force.md:77` 是标题行，100 mV 规则实际在第 79 行、旁路例外在第 80 行 | 改为“B2 的 5 V 分支按 p.4 旁路接法成立；第 77 行只是标题，规则在第 79 行，旁路例外在第 80 行” |
| 第 40 行 | “5 V AVDD 分支是唯一硬错误” | 不是硬错误；旁路模式允许 | 改为“5 V AVDD 分支本身不是硬错误；B2 的不足是没给出 5 V 共模数字、没确认传感器 5.25 V 激励上限、旁路表里多列了 VBG 0.1 µF” |
| 第 98 行 | “把 B2 暴露的 HX711 约束写进 05/D1：`AVDD ≤ VSUP−100 mV`，推荐 AVDD=3.3 V” | 写成通用约束，遗漏“仅内部稳压模式”；3.3 V 是推荐值，不是唯一合法值 | 改为“内部稳压模式：`AVDD ≤ VSUP−100 mV`；旁路模式不适用。05 选 3.3 V 是保守推荐，5 V 旁路也是合法分支” |
| 第 122 行 | “确认它不再走 5 V AVDD 分支” | 把合法分支当成要避免的错误 | 改为“确认它明确写出 5 V 分支的旁路模式条件（VSUP=AVDD=5 V、VFB=GND、BASE=NC），并核对共模/传感器激励上限/DVDD；不是要求它避免该分支” |
| 第 126 行 | “B2 HX711 AVDD=5 V 分支不成立：`d-force.md:77` 明确 …” | 同第 39 行；规则行号与适用范围都不准确 | 改为“该判断不成立；`d-force.md:79` 的 100 mV 规则在‘内部稳压’段内，第 80 行旁路段明确说 100 mV 不适用” |

**评分影响**：如果只按“5 V AVDD 分支”这一条扣分，B2 的证据/计算项不应因这一条被扣分；该分支是手册允许的旁路模式。是否给满分还要看 B2 的其他检查（5 V 共模数字、传感器 5.25 V 激励上限、未用 INB±、VBG 电容、DVDD 逻辑），这些是小瑕疵/待核实项，不是硬错误。本报告不重新给 B2 总分，只纠正评分依据；重新评分应由评测流程按完整 rubric 决定。

### 6.4 其他文件的搜索结果

- `source-register.md:190`（CHW-S061）：只登记“手册 9 页（版本未标）… 模块板未核对；不能把 typ 噪声当保证值”，没有供电模式结论，**无需改**。
- `docs/common-hardware-gap-analysis.md`：只在 D1 选型表提到 HX711，没有 5 V/100 mV 结论，**无需改**。
- `docs/common-hardware-report.md`：只列 HX711 型号，没有供电模式结论，**无需改**。
- `docs/evidence/common-hardware-2026-10-22/audit/d-force.md`：是写卡前的缺口审计，没有 5 V/100 mV 结论，**无需改**。
- `docs/evidence/common-hardware-2026-10-22/blind/B2.md`：B2 原文的 5 V 分支引脚表（约 250–269 行）明确 `BASE=NC`、`VFB=AGND`，是旁路模式；B2 的结论本身基本正确，**不应按“违反 100 mV”扣分**。B2 的 VBG 100 nF 在旁路模式是多余但手册未禁止；B2 说“D1 没有给出绝对最大值”是对的（D1 给的是 100 mV 关系，不是绝对最大值）。

## 7. 独立计算依据（数值 → 来源/公式 → 类型）

| 数值/结论 | 数值 | 来源/公式 | 类型 |
|---|---:|---|---|
| VSUP 工作范围 | 2.7–5.5 V | p.2 Table 1 | 手册工作范围（引脚说明） |
| AVDD 工作范围 | 2.6–5.5 V | p.2 Table 1；p.3 Table 2 | 手册工作范围 |
| VSUP/AVDD Table 2 范围 | 2.6–5.5 V | p.3 Table 2 | 手册工作范围（与 p.2 的 2.7 V 有 0.1 V 不一致） |
| DVDD 工作范围 | 2.6–5.5 V | p.2 Table 1；p.3 Table 2 | 手册工作范围 |
| 内部稳压 100 mV 规则 | `VAVDD ≤ VSUP − 0.100 V` | p.4 “Power Supply Options” | 手册设计要求（条件：使用片内稳压器） |
| 旁路模式引脚 | VSUP→AVDD/DVDD 较高者；VFB→GND；BASE→NC；VBG 0.1 µF 不需要 | p.4 同段 | 手册明确要求 |
| VBG | 1.25 V typ | p.3 Table 2 | 典型值（无 MIN/MAX） |
| 满量程输入 | `±0.5 × AVDD / GAIN` | p.3 Table 2；p.1/p.4 圆整为 ±20/±40/±80 mV @5 V | 手册公式/名义值 |
| 共模输入 | `AGND+1.2 V … AVDD−1.3 V` | p.3 Table 2 | 手册极限（无测试条件） |
| 输入噪声 | 50 nV rms typ（Gain=128，RATE=0） | p.3 Table 2 | 典型值（不是 max） |
| 模拟电源电流 | 1400 µA typ（含稳压器） | p.3 Table 2 | 典型值 |
| 数字电源电流 | 100 µA typ | p.3 Table 2 | 典型值 |
| 掉电电流 | 模拟 0.3 µA typ + 数字 0.2 µA typ | p.3 Table 2 | 典型值 |
| 内部稳压掉电行为 | HX711 和传感器一起掉电 | p.5 | 手册明确（条件：内部稳压） |
| USB VBUS | 4.75–5.25 V | 仓库 `f-input-protection.md:205` | 仓库引用（USB 5 V±5%） |
| LCAE 灵敏度/桥阻/激励 | 2 mV/V ±10%；350 Ω；10 V 推荐，15 V max | 仓库 `d-force.md:70`；LCAE p.1 | 具体型号示例（不能推广） |
| 5 V 桥电流 | 14.2857 mA | `5.00 / 350` | 计算（假设 350 Ω） |
| 5 V 桥功耗 | 71.4286 mW | `5.00² / 350` | 计算（假设 350 Ω） |
| 3.3 V 桥功耗 | 31.1143 mW | `3.30² / 350` | 计算（假设 350 Ω） |
| 5 V 满量程输出 | 10.00 mV | `2 mV/V × 5.00 V` | 计算（假设 2 mV/V、5 kg） |
| 增益 128 FS @5 V | ±19.53125 mV | `0.5 × 5.00 / 128` | 计算（手册公式） |
| 增益 128 利用率 | 51.20% | `10.00 / 19.53125` | 计算 |
| 正半轴码值 | 4,294,967 | `0.5120 × 2^23` | 计算 |
| 每克码值 | 858.99 码/g；1.164 mg/码 | `4,294,967 / 5,000` | 计算 |
| 5 V 噪声折合 | 0.0250 g rms；8 次平均 0.00884 g rms | `50 nV / 2.00 µV/g`；`/√8` | 计算（噪声为 typ） |
| 5 V 共模 | 2.50 V；范围 1.20–3.70 V；余量 1.30/1.20 V | `AVDD/2`；Table 2 | 计算 + 手册极限 |
| 3.3 V 共模 | 1.65 V；范围 1.20–2.00 V；余量 0.45/0.35 V | 同上 | 计算 + 手册极限 |
| 20k/33k AVDD | 3.3125 V | `1.25 × (20+33)/20` | 计算（VBG typ） |
| 20k/48.8k AVDD | 4.300 V | `1.25 × (20+48.8)/20` | 计算（VBG typ） |
| 分压电流 | 62.5 µA | `1.25 / 20 kΩ` | 计算 |
| 3.3125 V/5 V 调整管功耗 | 18.439 mW | `(5.00−3.3125) × 10.9268 mA` | 计算（含 I_AVDD + I_div） |
| 4.3 V/5 V 调整管功耗 | 9.624 mW | `(5.00−4.30) × 13.7482 mA` | 计算（含 I_AVDD + I_div） |
| 3×AAA 3.5 V 余量 | 0.1875 V | `3.50−3.3125` | 计算（仓库 05 的 3.5 V 截止） |

## 8. 仍未核实事项

以下全部标 `待核实` 或 `NOT RUN`，不能当成已保证：

1. **手册版本/日期**：PDF 没有印 revision/date；元数据 creation date 2009-06-26，source register CHW-S061 也写“版本未标”。本报告的结论绑定这份 9 页 PDF；如果 Avia 后续改版，需重核 p.4。`待核实`
2. **绝对最大额定值**：手册只给 2.6/2.7–5.5 V 工作范围，没有 Absolute Maximum Ratings。5.25 V USB 上限在工作范围内，但插拔瞬态/ESD/TVS 钳位后的电压是否超器件耐压，没有数字。`待核实`；外部钳位与实测 `NOT RUN`
3. **VBG 的 MIN/MAX**：Table 2 只有 typ 1.25 V。AVDD 设定值的批次/温度公差无法从手册保证；R1/R2 公差也未计。`待核实`；样机实测 AVDD `NOT RUN`
4. **Fig.1 的 R1/R2 位置**：p.4 公式与 Fig.1 的左右标注看起来不一致（§4.3）。按公式设计，物理分压拓扑需对照原厂参考板/实测确认。`待核实`
5. **外部 PNP 的实际压降/热**：手册只说 dropout 取决于外部管子，没有给 S8550 的 Vce(sat) 曲线、最大电流、热阻。5 V→4.3 V 在 USB 最低 4.75 V 时只有 0.45 V 余量；3×AAA 3.5 V 时只有 0.1875 V 余量。`待核实`；调整管温升/压降实测 `NOT RUN`
6. **未用 INB± 的接法**：p.2 只给功能名，没有“未用输入接已知电位/接地”的明文。仓库 `05-electronic-scale.md:86` 说“B 通道不用时按手册接已知电位，不能悬空”，但手册没有这句话；这是仓库建议，不是手册要求。`待核实`
7. **旁路模式 VBG 引脚**：p.4 说 0.1 µF “not needed”，但没有说该引脚必须悬空、接地还是可接其他电容。按“不装”处理；是否需要其他处理 `待核实`
8. **AVDD 是否就是 ADC 参考**：由满量程公式 `±0.5(AVDD/GAIN)` 和“没有独立 VREF 引脚”推得，手册没有一句“AVDD is the reference”。比率测量的结论建立在这个推导上；`待核实`
9. **旁路模式的桥掉电行为**：p.5 只明说“内部稳压模式下 HX711 和传感器一起掉电”。旁路模式下桥接外部 5 V，HX711 掉电不能切断桥；这是按拓扑推断，手册没有明说。需要桥掉电时加负载开关；`待核实`
10. **传感器激励上限/5 kg 灵敏度**：5 kg、2 mV/V 是 05 的假设；LCAE p.1 写“2 mV/V ±10%（<6 kgf 为 1 mV/V ±10%）”，所以 LCAE 的 <6 kgf 档（如 3 kg）是 1 mV/V；5 kg 不是 LCAE 标准档，不能直接套 2 mV/V。具体 MPN 的激励上限、桥阻、灵敏度公差、自热系数都要查。`待核实`
11. **模块板实际拓扑**：模块的 AVDD 实际值、`E+` 是否来自 AVDD、DVDD 电压、R1/R2/调整管/屏蔽是否已装，必须按模块原理图/实测核对；不能看到“5 V 模块”就假设 AVDD=4.3 V。`待核实`
12. **HX711 的 VIH/VIL**：手册没有给数字输入阈值，只要求 DVDD 与 MCU 同电源。3.3 V MCU + 5 V DVDD 的组合不能靠“大概能行”判断。`待核实`
13. **5 V 轨噪声/纹波与比率测量**：5 V 同时供桥和 AVDD，比率测量能抵消一阶共模，但桥自热、传感器漂移、5 V 瞬态跌落不会自动抵消。`NOT RUN`
14. **长期可靠性/EMC/ESD**：5 V 激励下的长期漂移、蠕变、EMC、ESD、插拔浪涌均未测。`NOT RUN`
15. **B2 重新评分**：本报告只纠正“5 V 分支违反 100 mV”这一评分依据；B2 的最终分数应由完整 rubric 重新评，不能从本报告直接推出“B2 应得 5 分”。`待核实`

## 9. 可追溯性与范围声明

- 固定快照：`git rev-parse 4c9db61` → `4c9db61628e4a83f01acad1c53ea5c0665182325`；提交说明 `fix(common-hardware): correct five audited engineering conclusions`（2026-10-22 20:32:34 +0800）。
- 复核开始时 `git status` 只有其他会话的未跟踪 `decisions/` 文件；复核过程中工作树继续移动到 `d97b6f3`、`662a7ab`。本报告所有仓库引用均用 `git show 4c9db61:<path>` 固定，不引用后续提交。
- HX711 手册：本地 `C:\Users\jlc\work\hds-common-scratch\sources\d-force\hx711.pdf`，9 页，SHA-256 `6050e88a5e938ff9ac3292bfbc9fea2afa0ca73d1a649d5398ae8de5ab7c017e`；与 `https://cdn.sparkfun.com/datasheets/Sensors/ForceFlex/hx711_english.pdf` 的 SHA-256 完全相同。
- LCAE 手册：本地 `C:\Users\jlc\work\hds-common-scratch\sources\d-force\lcae.pdf`，SHA-256 `a2af4831db18ee43a78a83a2767580b7e1c9ab7faa097f0c23cfc1b754db2bb8`；只读 p.1 规格，未读尺寸/安装页。
- 本报告没有修改仓库文件；只写了本文件与 HX711 页面截图（`rerun\hx711-pages\`）。S1 的证据级别保持“连接级”，本报告没有把它升级为功能验证。
