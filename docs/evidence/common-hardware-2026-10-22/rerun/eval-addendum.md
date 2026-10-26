# 盲测评分更正：B2 的 HX711 5 V AVDD 分支

> 原始记录：`../blind/eval.md` 第 18、39、98、126 行与 `../blind/B2.md` 第 253、255 行。原始文件未修改，本页只追加更正。

## 1. 原评分

`../blind/eval.md` 给 B2：

| 路线 | 证据 | 计算 | 误判 | 诚实 | 总分 |
|---:|---:|---:|---:|---:|---:|
| 4 | 4 | 4 | 5 | 5 | 4 |

扣分理由（原文）：“5 V AVDD 分支违反 HX711 的 VSUP−100 mV 约束”；并在第 126 行写“B2 的 AVDD=5 V 分支不成立”。

## 2. 更正依据

HX711 数据手册 p.4 “Power Supply Options”原文分两段：

> “**When using internal analog supply regulator**, the dropout voltage of the regulator depends on the external transistor used. The output voltage is equal to VAVDD=VBG*(R1+R2)/R1 (Fig. 1). **This voltage should be designed with a minimum of 100mV below VSUP voltage.**”
>
> “**If the on-chip analog supply regulator is not used**, the VSUP pin should be connected to either AVDD or DVDD, depending on which voltage is higher. Pin VFB should be connected to Ground and pin BASE becomes NC. The external 0.1uF bypass capacitor shown on Fig. 1 at the VBG output pin is then not needed.”

100 mV 要求只在**内部稳压模式**成立。B2 的 HX711 引脚表明确写：

- `BASE` = NC（不用内部稳压）
- `VFB` = AGND（不用内部稳压）

即 B2 的 5 V AVDD 方案是**旁路模式**：`VSUP=AVDD=5 V`、`VFB=GND`、`BASE=NC`，符合 p.4 的旁路接法；5 V 也在 AVDD/VSUP 2.6–5.5 V 工作范围内（p.3 Table 2）。因此原件“违反 100 mV 约束”的扣分依据不成立。

## 3. 更正后的评分

| 路线 | 证据 | 计算 | 误判 | 诚实 | 总分 |
|---:|---:|---:|---:|---:|---:|
| 5 | 5 | 5 | 5 | 5 | 5 |

说明：

- 路线：HX711 + 四线桥 + CH32V003 + SSD1306 + USB-C，正确；5 V 旁路分支是合法路线。
- 证据：D1/ANA-09/I1/L3/F1/F2/G1 等文件真实；B2 的引脚表给出了 `BASE=NC`、`VFB=AGND`。
- 计算：满量程/增益/码值/噪声/误差/热均可复算；5 V 分支的 10 mV FS 与 ±19.53 mV FS 正确。
- 误判/诚实：完整；明确 05 当时缺失并拒绝假装读过，这一点是加分项。
- 残余边界（不扣分，但需保留）：B2 说“D1 没有给出 AVDD/VSUP 绝对最大值”在当时是事实；D1 现在已补 AVDD 2.6–5.5 V、VSUP 2.7–5.5 V 与两种模式。B2 没有展开“桥必须允许 5 V 激励”“USB 5.25 V 瞬态”，这两点在 `d-force.md`/`05-electronic-scale.md` 的“模块/边界”段落中保留为待核。

## 4. 对报告/路由的同步

- `docs/common-hardware-gap-analysis.md` 的 P0-3 原建议“HX711 约束：`AVDD ≤ VSUP−100 mV`”应改为“**内部稳压模式**下 `AVDD ≤ VSUP−100 mV`；旁路模式 `VSUP=AVDD` 合法”。正文 `d-force.md`/`05-electronic-scale.md` 已按此改写。
- 原始 `../blind/eval.md` 的 B2 行、§4 与 P0-3 保留为历史记录，不覆盖；引用 B2 评分时以本页为准。

## 5. 仍未核实

- 具体 HX711 模块的 `AVDD`/`VSUP` 是否短接、`E+` 是否来自 AVDD；模块丝印/跳线可能不同。
- 5 kg 传感器是否允许 5 V 激励；B2 用 2 mV/V、350 Ω 的假设，实际 5 kg 档可能是 1 mV/V。
- HX711 手册没有绝对最大额定值；USB 5.25 V 上限与插拔瞬态、TVS 钳位后的电压仍需外部钳位与实测。
- 旁路模式下 5 V 桥自热、共模与噪声；未做样机/实测。
