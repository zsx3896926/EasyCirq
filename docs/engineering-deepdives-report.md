# 工程深潜与开源案例研究：交付报告（2026-10-22）

> **合并复核补记：** 本文是原分支交付记录。后续复核发现并修正公式、故障排查、参考答案和试验输入提示问题，当前结论及验证范围以[PR #3集成复核](pr3-integration-review.md)与修订正文为准。196/200、197/200为带题型提示及旧答案下的历史评分，不能作为盲判或Skill效果证据。


> 分支：`feat/engineering-deepdives`（从 `origin/main` `68331c4` 创建）。
> 范围：只新增研究内容、故障案例、审图练习与索引；不修改 EDA 执行流程、原理图检查器、计算器核心、嘉立创生产规则主文件、公共测试框架。
> 完成级别：资料阅读 + 文件核对 + 独立计算 + 内容层答案文件隔离试答试验；**没有** EDA 绘图/回读、PCB、制造、样机、热/EMC/安规实测。

## 1. 实际研究了什么

### 1.1 开源硬件项目（25 个）

| 领域 | 项目 |
|---|---|
| MCU/开发板 | Arduino UNO R3、SparkFun ESP32 Thing Plus、iCEBreaker、TinyFPGA BX、OLinuXino A20 Lime、BeagleBone Black |
| 低功耗无线/电池 | Crazyflie 2.1、Crazyflie 2.1 Brushless、Adafruit Feather nRF52840 Sense、LibreSolar BMS C1、LibreSolar MPPT 2420 HC |
| 电机/功率/工业 | ODrive v3、VESC BLDC_4、Smoothieboard、Pixhawk FMUv2、ULX3S |
| 音频/精密模拟 | Mutable Braids、Clouds、Edges、EEZ BB3 AUX-PS |
| 高速/RF/FPGA | HackRF One、Glasgow revB、Fomu |
| HMI/连接器/热 | Keyboardio Model01、MNT Reform 2 |

每个项目记录了：仓库/提交、许可证、实际读取的文件/页/位号/网络、1 个电路决定、1 个 PCB 决定（或“资料不足”）、1 个调试/制造/可维护性考虑、版本迭代证据、迁移条件、不应照搬、开放问题。**没有**把 star 数或成品照当正确性依据；作者修订（如 ODrive CHANGELOG）与社区推测、本文推断分开标注。

### 1.2 原厂/规范来源

新增 `D-S01`–`D-S08`：

- TPS212x 优先级 power mux（SLVSEA3F）
- BQ27441-G1 电量计（SLUSBH1C）
- SBOA583 运放输入/输出摆幅
- OPA333（SBOS351E）
- OPA340（SBOS073C）
- FCC KDB 996369 D04 模块集成指南
- LP2985（SLVS522S）
- NXP UM10204 §3.1.16 Bus clear

既有 `PWR/ANA/MCU/IF/DRV/RF/MFG/G/P` 来源继续按 `source-register.md` / `design-experience.md` 引用，未重复登记。nRF52840 PS、Pinecil 原理图、FCC 官方 PDF 因 403/503/403 未取得正文，相关结论保持 `待补` 或用可读镜像并注明。

## 2. 新增、深化与纠正

### 2.1 新增

- `design-hardware/references/engineering-deepdives/`：
  - `README.md`：按症状/器件/阶段导航；与设计卡、故障库、组合契约、测量、热专题的分工。
  - `sources.md`：D-S 来源 + 25 个 OSHW 项目/许可/提交/查阅范围台账。
  - `action-map.md`：24 条“触发→读取→动作→预期证据→失败后继续”。
  - `topics/`：16 篇专题（B1–B4、C1–C4、D1–D4、E1–E4）。
  - `casebook/`：6 组案例 + 索引，共 25 个项目。
  - `exercises/`：20 题、8 对成对案例、参考答案、2 名 Agent 答案文件隔离试答记录与评分。
- `references/failures/`：F23–F33，共 11 个跨模块故障案例；`failures/README.md` 增加 12 类覆盖表。
- `SKILL.md`：增加 1 行导航（工程深潜/审图练习）；故障案例数量 22→33。
- `source-register.md`：新增 D-S01–D-S08 登记段。
- `design-experience.md`：注明 F23–F33 新增，共 33 个。

### 2.2 深化

- 电源路径：把“反接保护≠反向电流阻断”落到 `2^n` 组合、体二极管/输出电容反灌、TPS2121 的 5 µs/100 µs 条件、DPPM/supplement 状态机。
- 低功耗：把“MCU 睡眠电流”拆成电池侧常开分支；Feather Sense 的 2×100 kΩ 分压 18.5 µA 是算例主导项。
- 充电/电量：区分充电器、保护器、power path、电量计；给出 500 mA 输入/300 mA 系统/200 mA 充电的 13.1 h 算例与“500 mA 系统不充电/超过进入 supplement”的边界。
- 模拟：误差链区分可校准/随机/温漂/非线性；RSS 的适用条件；运放共模/摆幅/容性负载/输入保护；测量假象。
- 接口/时钟/板外/无线：组合失败、CL/负阻、共模/终端、模组认证 vs 整机合规。
- 功率/热/连接：感性负载能量、栅极驱动/米勒、机械环境热路径、连接器整链路。

### 2.3 纠正（独立审计后发现并已修）

| 位置 | 原问题 | 修正 |
|---|---|---|
| B1 ODrive 母线分压 | R6 写成 100 kΩ，分压比 1/101、81 mV/LSB | R6=10 kΩ，1/11；24 V→2.18 V（约 2708 码），48 V 超 3.3 V 满量程；8.86 mV/LSB |
| B1 supplement | 系统 1 A 时写“电池补 0.16 A” | 明确 5 V 侧 1 A→补 0.5 A；3.3 V 侧 1 A 折算才约 0.16 A |
| B1 MNT 作者注 | “Zo…”编码显示不全 | 作者注为 “Inrush Current Limiter by Zoé” |
| B1/B2 T_VCC | 1.65–3.3 V 写成所有 STLINK 通用 | 限定为 UM2448 §11.5 的 B-STLINK-VOLT 适配板范围 |
| B2 典型值 | 3 nA/100 nA/7 µA 未给 max | 3 nA typ/10 nA max；0.1 µA typ；7 µA typ/9.5 µA max |
| B3 线性热 | `(VIN−VBAT)×ICHG` 与 PWR-06 口径冲突 | 完整线性power-path损耗应合并输入到SYS及SYS到BAT两段，见修订正文；原“上界”式漏项 |
| B3 存储预算 | 20 µA 未标 typ-only | 标 typ-only 下限，补 2×/3× 敏感性（6 个月 175/263 mAh） |
| C1 建立算例 | 100 k/100 k 分压用 100 kΩ 算 τ，1507 LSB | 用 R_th=50 kΩ：τ=0.5 µs、13.5%、554 LSB；`calculate.py` 重跑核对 |
| C1 “实测” | 把解析计算写成“实测 1507 LSB” | 改为“计算 554 LSB（非实测）” |
| C2 CMRR | “两者取更差” | 按式 8 并联合成，低于任一项；相等时再低 3 dB |
| C2 VESC 分流 | 只写 pad 3 | 改 pad 3/4 成对 sense；四端分流 |
| C3 θJA | 直接乘 JEDEC θJA 判实际 Tj | 标为封装比较/一阶筛查，实际用 ΨJB/板温/实测 |
| D1 断电钳位 | “上拉越大，灌流越大”因果反了 | 上拉电阻越小，灌流越大；正确做法是 Ioff/负载开关/串阻/缓冲 |
| D2 晶体 CL | 把 CL=8 pF 说成 AN2867 原例 | CL=8 是本稿任务条件；AN2867 原例 CL=10 pF、gmcrit≈0.23 mA/V、margin≈107 |
| D3 采样点 | 85% 说成超过 75–87.5% | 85% 落在上沿，余量不足；需按支线 ≤0.3 m 重算 |
| D3 适配线 | 把两种错接后果合并 | 1 对 1 与“电源脚接 pin1”分开写 |
| D4 Crazyflie RF | ANT_A/ANT_B 路径把 L3/L4 混入 | ANT_A→U12→C36→（L2→Y1，L3 对地）；ANT_B→U13→J12；L4 在 U8 IND 对地 |
| E1 动能 | J=1e−3 算出 125 mJ（应为 125 J） | 改 J=1e−6（小型转子假设），125 mJ 自洽；电容 53.4 V 结论不变 |
| E1 母线电容 | 31.7 mJ 总储能与 480 mJ 直接比“15 倍” | 可用裕量 105.8 mJ（到 50 V），480/105.8≈4.5 倍 |
| E1/E2 VESC 39 kΩ | 把 R30/R36/R46 当相分压 | R30/R36/R46 是栅-源下拉；R23/R26/R32 才是相分压 |
| E1 Pixhawk 分压 | 漏 R919，按 1/2 算 | R922/R918/R919 三颗 10 k，VDD_SERVO_SENS≈VDD_SERVO/3 |
| E1 Smoothieboard R83 | 说成栅-源下拉 | R83 在 R82 驱动器一侧；Q5 的 R86 才是栅-源下拉 |
| E2 DRV8871 TSD | 写 175 °C | 150–175 °C（min/max） |
| E3 ODrive R35 | 写 10 kΩ | R35=3.3 kΩ；三组 R12/R13、R31/R35、R49/R50 |
| E3 TSP | 把 S12 扩展到二极管/MOSFET | S12 只支持 LED Vf；其余标 `[推断]` |
| 案例库 ODrive | NT8/NT9 说成 GND–PGND 分割 | 是 Kelvin net-tie；单点位置未确认 |
| 案例库 VESC | 符号名/Value 说反 | 符号是 MCP2551 rescue，Value/BOM 是 SN65HVD232 |
| 案例库 Feather | 天线净空 5.2 mm | 统一 5.7 mm（5.715 mm） |
| 案例库 Brushless | C102 22 n、称“无文本层” | C102 22 µF；有部分文本层，已交叉核对 |
| 案例库 BBB | “过 FCC/CE” | 作者注记“to pass”，未验证是否通过 |
| 索引 | ESP32/Feather/Glasgow 写成 USB-C；Arduino 许可缺失；Pixhawk 双 IMU | 改 micro-USB/Micro-B；CC BY-SA 4.0；双 IMU 位共用总线 |

## 3. 最有价值的十项工程发现

1. **RPP ≠ RCB，且 mux 的“快速切换”有前提。** P-MOS 反接保护挡不住输入掉电时的反向电流；TPS2121 的 5 µs 只在 `CP2 ≥ VREF` 时成立，默认是 100 µs；100 µF/5 V 的 holdup 只有 1.25 mJ，不能靠它扛住源切换。
2. **板级睡眠电流是常开分支之和。** Feather Sense 的 2×100 kΩ 电池分压单独 18.5 µA @3.7 V，占 32 µA 算例的 57.8%；MCU 2 µA 只占 6.25%。10 条 100 kΩ 上拉就是 330 µA，年耗 2.89 Ah。
3. **“插 USB 就能充电”是状态机。** 500 mA 输入、300 mA 系统、200 mA 充电，1S 2000 mAh 约 13.1 h；系统 400 mA→24.05 h；系统 500 mA→不充电；超过→supplement。充电器、保护器、power path、电量计不能互相替代。
4. **ADC 误差链先看主导项，不要先 RSS。** 1 µA 漏电 × 50 kΩ 戴维南 = 50 mV = 62 LSB；50 kΩ/10 pF/1 µs 建立误差 13.5% = 554 LSB。RSS用于不相关随机标准不确定度；存在主导项不使方差合成失效，保证上限不能直接RSS；温漂/保证值/非线性要 worst-case。
5. **运放“直流增益对”远远不够。** OPA340 输出摆幅在 100 kΩ 时 1 mV、2 kΩ 时 40 mV（典型），全温更差；OPA333 输入保护正文写 10 mA、绝对最大表却写 ±1 mA；输入先于 V+ 上电会经钳位二极管灌流。
6. **测量接法能制造 10 倍假象。** 10 cm 地线约 100 nH，1 A/10 ns 的 `L·di/dt` 就是 10 V；500 µΩ 分流上 2.46 mΩ 共享铜会把读数变成 5.92 倍（误差 +492%）；换短地弹簧/差分探头后 500 mV 纹波可能只有 30 mV。
7. **I²C 的 400 pF 不是“随便 4.7 k”就能过。** 4.7 kΩ/150 pF 在 400 kHz 下 `tr≈597 ns > 300 ns`；400 pF 时 `Rp(max)=885 Ω` 与 `Rp(min)=967 Ω` 区间为空，3 mA IOL 下没有合法上拉，必须降 Cb/分段/缓冲。
8. **晶体的“看起来缺电容”经常是误读。** Crazyflie 的 C1 100 nF 接 `STM_NRST`、R3 10 k 接 `STM_BOOT0`，不是 X1 负载电容；X1 无外接负载电容，需 BOM 确认是否为内置电容谐振器。AN2867 的 CL=10 pF 原例与任务 CL=8 pF 不能混。
9. **感性负载与栅极驱动要分开算“能量”和“应力”。** 100 mH/100 mA 储能 0.5 mJ；1 kΩ 钳位峰值 100 V、τ=100 µs；续流二极管把释放时间拉到 L/R≈0.83 ms，触点和 FET 的取舍不同。Qgd=10 nC、10 V/ns、30 V 的米勒电流约 3.33 A，10 Ω 栅阻上理论 33 V，足以误导通。
10. **真实开源设计的价值在“作者为什么改”和“不能照搬的边界”。** ODrive 3.4/3.5 的 Kelvin net-tie、VESC 两相 1 mΩ 四端分流、MNT LTC4020 的 29.04 V/8、Keyboardio 一根 RJ45 同时传差分 I²C 与受控电源、HackRF 的 TX/RX/bypass 三路开关——这些比“成品照”更能训练判断。

## 4. 哪些发现改变了已有建议

- **PWR-05 / B1**：TPS2121 的 5 µs 不是默认值；必须写 `CP2≥VREF` 条件，否则按 100 µs 算输出跌落。
- **D1 / F06**：400 pF 不是“在范围内就安全”；400 kHz + 3 mA IOL 下 Rp 区间可能为空，必须分段/缓冲。
- **C1 / ANA-01**：分压的建立时间用 `R_th=R1∥R2`，不是单颗 100 kΩ；原 1507 LSB 算例改用 50 kΩ 后是 554 LSB。
- **E1/E2 / VESC 案例**：R30/R36/R46 是栅-源下拉，不是相分压；相分压是 R23/R26/R32。
- **E3 / ODrive 案例**：R35 是 3.3 kΩ，不是 10 kΩ；三组 TEMP 分压是 10 k/3.3 k。
- **案例库 ODrive**：NT8/NT9 是 Kelvin net-tie，不是 GND–PGND 分割；单点位置未确认。
- **案例库 Feather**：天线净空是 5.7 mm，不是 5.2 mm；USB 是 micro-USB，不是 USB-C。
- **审图练习**：E01/E04/E07/E10/E13/E16–E18 的题型与答案口径已按答案文件隔离试答试验修正；原题面有 8 处类型歧义。

## 5. 独立计算、仿真与行为试验

- **独立复算**：B1 二极管/理想二极管损耗、反灌能量、比较器门限/迟滞；B2 年耗/分压/上拉；B3 充电时间/线性热/分流；B4 负载阶跃/源阻抗/热插拔能量；C1 LSB/漏电/建立/RSS vs worst-case；D1 并联上拉/上升时间/Rp 区间；E1 储能/钳位/释放时间；E2 栅极电荷/米勒/导通损耗；E4 接触电阻/铜箔电阻。
- **可执行计算**：用仓库 `calculate.py adc_settle` 以 `r_source_ohm=50000` 重跑，得到 `tau=5.0006e-7 s`、`error=0.13537`、`554.47 LSB`、`max_total_resistance_for_0p5LSB=11096.54 Ω`、`board_verified:false`；文中保留该 JSON 并标“非实测”。
- **内容层答案文件隔离试答**：2 名独立 Agent 只读 20 题、不看答案；评分 196/200 与 197/200；评分员列出 8 处题面/答案歧义，已修 6 处（E01/E04/E07/E10/E13/E16–E18 的口径），并保存原始 `student-a.json`、`student-b.json`、`grade.json`、`responses.md`、`evaluation.md`。
- **独立审计**：4 名审计员按 B/C/D/E 抽查 16 篇专题的数值、页码、位号和跨文件冲突；上述“纠正”表来自该轮审计。

## 6. 仍是条件推断或待实测

- 全部专题**没有** EDA 回读、PCB、SPICE、热仿真、EMC/安规、制造或样机实测；文中 `未执行` 保持原样。
- nRF52840 睡眠电流、Pinecil、FCC 官方 PDF 未取得；连接器原厂手册未读，E4 的所有额定值标 `待查`。
- LTC4020、BQ76952、MCP73831、RT9080、DRV8302、IRFS7530 等器件手册未逐页核对；相关结论按原厂判据/设计文件/推断分级。
- 开源项目的 PCB 结论多处为“资料不足”（Crazyflie、BeagleBone、Keyboardio、ODrive 无 PCB 源文件）；不能把原理图观察当布局验证。
- F23–F33 均为构造案例（除正文标注的作者记录），不是真实用户故障；根因排序是 C 级推断。
- 审图试验只有 2 名 Agent、20 题，不是能力认证；题面/答案仍有口径风险。

## 7. 与另一条开发任务的协调

- **只改了 `SKILL.md` 两处**：新增 1 行“工程深潜/审图练习”导航；故障案例数量 22→33。另一条任务若也改这两处，合并时保留双方行、数量取 33。
- **未改** `references/eda-execution.md`、`assets/eda/`、`scripts/eda_exec.py`、`scripts/sch_layout_check.py`、`scripts/calculate.py`、`jlc-*-rules.md`、`tests/` 框架；只新增了内容文件。
- **新增故障 F23–F33** 引用 `D-S07`；`source-register.md` 已加 D-S 登记段，避免与既有 `PWR/ANA/...` 编号混用。
- **执行流程若要在运行时引用深潜内容**：建议只链接 `engineering-deepdives/README.md` 的导航，不要全量加载 16 篇；按症状选 1 篇 + 1 个案例 + 1 张设计卡。
- **潜在冲突**：另一条任务若修改 `failures/README.md` 的表格，保留 F23–F33 行和“跨模块 12 类覆盖”表；若修改 `SKILL.md` 的 190 条检查/数量段，保留 33 个故障案例的口径。

## 8. 验证记录

| 项目 | 命令/方法 | 结果 |
|---|---|---|
| 仓库测试 | `python -m unittest discover -s tests` | 108 tests OK |
| Markdown 相对链接 | 自写检查器遍历 `engineering-deepdives/` + F23–F33 | 67 files，0 broken |
| 专题结构 | 检查 `## 0`–`## 10` | 16/16 齐全 |
| 案例编号 | OSHW 标题 vs `sources.md` | 25/25 一致 |
| 故障编号 | F23–F33 vs `failures/README.md` | 33/33 一致 |
| 算例复核 | `calculate.py adc_settle` 50 kΩ | 554.47 LSB，`board_verified:false` |
| 答案文件隔离试答试验 | 2 学生 + 1 评分员 | 196/200、197/200；8 处歧义，已修 6 处 |

**未执行**：真实 EDA 绘图/回读、DRC/ERC、SPICE、热/EMC/SI、制造、样机、安规。任何“通过/满足”只指文档/公式/文件核对，不是实物验证。

## 9. 提交与 PR

- 分支：`feat/engineering-deepdives`
- 提交：`4dace97372a419b5fe1a9fa1a96f2a5d02560a3b`（本报告随该提交；后续仅文档更新会追加提交）
- PR：https://github.com/zsx3896926/hardware-design-skill/pull/3
- CI：`validate` 通过（108 个 unittest，2 次检查均 pass）
