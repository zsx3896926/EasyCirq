---
id: R4-CASE-D01
project: R4-P3
family: P02
parent: P02
facts_source: design-hardware/references/projects/p02-industrial-rs485-analog.md
packages: [D]
title: 两路 4–20 mA 采集的容差预算与角点决策
evidence: E3
execution: OFFLINE_PLANNING
hardware_execution: NOT RUN
last_reviewed: 2026-10-22
sources: [ANA-S01, ANA-S02, ANA-S03, ANA-S13]
record_types: [refuted-assumption]
---
# 两路 4–20 mA 采集的容差预算与角点决策
> 完成级别：纸面预算与离线重算。R4-P3 的器件未定型，未做 EDA 回读、SPICE、台架或温循；本案例只把 P02 的既有预算扩展为跨电路角点决策，不新增器件参数。
## 1. 触发与用户任务
R4-P3 要在 -20/25/60 °C 做两路 4–20 mA 采集，25 °C 目标 ±0.5% FS、全温区 ±1% FS（`design-hardware/references/projects/p02-industrial-rs485-analog.md:41-43`）。两个通道共用 2.5 V 基准和 ADC，存在 MUX 切换与 25 °C 两点校准；触发 D2 跨电路预算。
## 2. 产品与真实材料
- 仓库事实：100 Ω 低侧分流、0.1% 增益、1 mV Vos、2.5 V/0.1% 基准、12 位 ADC、10 µs 采样、8 次平均、两点 4/20 mA 校准（`design-hardware/references/projects/p02-industrial-rs485-analog.md:169-190`、`:405-416`）；0.05% 分流与 ≤25 ppm/°C 是 P02 方案 B 的计算假设，不是已核对器件值。
- 假设需求：全温区 -20/25/60 °C，不是实测温度场；本轮未重开原厂正文，ANA-S01/S02/S03/S13 沿用 `source-register.md` 登记范围；所有数值 E3，器件 MPN、C 号、价格、库存均待查。
## 3. 初始决定（错在哪）
1. 把 P02 的 0.159% RSS 当保证值。错在 RSS 只适用于独立随机项；共用基准与同一温度场的 tempco 是相关项。
2. 只算 25 °C 初始误差。错在分流/基准温漂、MUX 串扰、校准残差与 INL 在 25 °C 校准后仍留。
3. 认为“加缓冲 + 校准”就能覆盖全温区。错在校准只消当前温度的 offset/gain，不消温漂、建立、串扰、INL 与长期漂移。
4. 把 P02 的 3905 LSB 与 0.524 LSB 直接当二阶结果。重算见 `design-hardware/assets/decisions/adc-settle.r4p3.recompute.json`：两者都是一阶筛查值。
## 4. 判定依据（path:start-end）
- `design-hardware/references/projects/p02-industrial-rs485-analog.md:169-190`：既有 4.3 误差预算、RSS 24.7 µA（0.123%）、最坏 43.1 µA（0.215%）、加 0.1% 基准后 RSS 0.159%。
- `design-hardware/references/projects/p02-industrial-rs485-analog.md:190-207`：4.4 ADC 建立表与 3905/0.524 LSB。
- `design-hardware/references/projects/p02-industrial-rs485-analog.md:122-124`：Vos、分流、基准的选型要求与“0.1% 只代表 25 °C 初始”。
- `design-hardware/references/projects/p02-industrial-rs485-analog.md:405-416`：ADC1 3 通道、10 µs/8 次平均、两点校准与 Flash CRC。
- `design-hardware/references/engineering-deepdives/topics/c1-sensor-to-adc-error-chain.md:144-177`：RSS 与 worst、相关项处理规则；同文件 `:179-191`：校准能消/不能消的边界。
- `design-hardware/assets/decisions/adc-settle.r4p3.recompute.json`：两节点重算 direct 3740.2475 LSB、buffered 1 nF 2.27e-36 LSB、buffered 470 pF 10 µs 4.26e-80 LSB。
## 5. 修正后的决定、代价与三行用户可见摘要
修正决定（使用模板 `design-hardware/assets/decisions/tolerance-budget.template.md` 的 §2 字段、§3 角点、§5 判定与 §6 动作）：保留 P02 的 100 Ω + 缓冲 + 470 pF + 10 µs 网络；把共用基准、MUX 串扰、校准残差、温度场相关组列为独立项；25 °C 未校准与全温区只给 conditional，post-cal 给 conditional/cannot_conclude。
| id | term | min | typ | max | unit | condition | temp_range | evidence_grade | class | correlated_group | calibration_state | source | worst | RSS | dominant_rank | decision |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SHUNT_INIT | 分流初始公差 | -10 | 0 | +10 | µA | 20 mA FS；25 °C | 25 °C | E3 | gain | gain_initial | initial | P02:169-190 | 10 | 10 | 3（并列） | conditional |
| GAIN_INIT | 增益网络初始公差 | -20 | 0 | +20 | µA | 20 mA FS；25 °C | 25 °C | E3 | gain | gain_initial | initial | P02:169-190 | 20 | 20 | 1（并列） | conditional |
| VREF_INIT | 2.5 V 基准初始 0.1% | -20 | 0 | +20 | µA | 20 mA FS；25 °C | 25 °C | E3 | gain | vref_common | initial | P02:82-82；P02:169-190 | 20 | n/a（相关） | 1（并列） | conditional |
| VOS_INIT | 缓冲 Vos 1 mV / 100 Ω | -10 | 0 | +10 | µA | 25 °C | 25 °C | E3 | offset | offset_initial | initial | P02:169-190 | 10 | 10 | 3（并列） | conditional |
| QUANT | 12 位量化 ±0.5 LSB | -0.5 | 0 | +0.5 | LSB | 2.5 V/12 位 | 25 °C | E3 | quantization | independent | not-calibratable | P02:190-201 | 0.5 | 0.5 | 5 | conditional |
| VREF_TEMP | 基准 25 ppm/°C × 45 K（25→-20 最坏） | -22.5 | 0 | +22.5 | µA | ΔT=45 K | -20..60 °C | E3 | drift | temp_field | post-cal | P02:122-124 | 22.5 | n/a（相关） | 2（全温） | conditional |
| SHUNT_TEMP | 分流 25 ppm/°C × 45 K（25→-20 最坏） | -22.5 | 0 | +22.5 | µA | ΔT=45 K | -20..60 °C | E3 | drift | temp_field | post-cal | P02:122-124 | 22.5 | n/a（相关） | 2（全温） | conditional |
| TEMP_FIELD | 温度场相关组（6+7，同向最坏） | -45 | 0 | +45 | µA | ΔT=45 K | -20..60 °C | E3 | correlated | temp_field | post-cal | P02:122-124 | 45 | n/a（相关） | 1（全温；含于 CAL_RESIDUAL） | conditional |
| MUX_CROSSTALK | 两通道/MUX 串扰 | 待查 | 待查 | 待查 | µA | 前通道 20→0 mA 切换 | -20..60 °C | E3 | dynamic | mux_sequence | not-calibratable | P02:205-205 | 待查 | n/a | 待查 | cannot_conclude |
| CAL_RESIDUAL | 两点 4/20 mA 校准后残差 | 待查 | 待查 | ≥45（下限；其余待查） | µA | 校准后；全温 | -20..60 °C | E3 | residual | calibration | post-cal | P02:405-416；C1:179-191 | ≥45 | n/a | 1（post-cal 汇总） | conditional |
| SETTLE_470P | 100 Ω+470 pF；10 µs 建立 | ≈0 | ≈0 | ≈0（<1e-6 LSB；模型四舍五入） | LSB | 两节点模型；25 °C | 25 °C | E3 | dynamic | settling | not-calibratable | JSON:buffered-470pF-10us | ≈0 | n/a | n/a | conditional |
| SETTLE_UNBUFFERED | 1 kΩ+100 nF 直接采样；10 µs | 0 | 0 | 3740.2475 | LSB | 两节点模型；25 °C | 25 °C | E3 | dynamic | settling | not-calibratable | JSON:direct-unbuffered | 3740.2475 | n/a | 1（替代方案） | fail |
| INL_LONGTERM | ADC INL + 长期漂移 | 待查 | 待查 | 待查 | LSB | 全码/寿命 | -20..60 °C | E3 | nonlinear | adc_nonlinear+aging | not-calibratable | 待查；周期校准见动作表 | 待查 | n/a | 分解项（含于 CAL_RESIDUAL） | cannot_conclude |
> 源列缩写：`P02`=`design-hardware/references/projects/p02-industrial-rs485-analog.md`；`C1`=`design-hardware/references/engineering-deepdives/topics/c1-sensor-to-adc-error-chain.md`；`JSON`=`design-hardware/assets/decisions/adc-settle.r4p3.recompute.json`；`:N-M` 均指对应文件的 path:start-end。
> 行 6/7 是 TEMP_FIELD 的组内分解；post-cal 汇总只取 CAL_RESIDUAL，不得再加 TEMP_FIELD/INL/噪声（CAL_RESIDUAL = TEMP_FIELD + INL + 噪声 + 校准源不确定度，后三项待查）。conditional 统一落地：owner=硬件负责人（R4-P3）；到期日=首板 bring-up 前；条件=补齐 MUX 串扰、INL/噪声、校准源不确定度与增益网络温漂并复核本表；未满足前保持 conditional，不得写 guaranteed_pass；无 owner/到期日的 MUX_CROSSTALK 与 INL_LONGTERM 已判 cannot_conclude。
- 汇总（1 LSB=6.1035 µA；LSB 行先折算再与 µA 行合成；除注明外均为 20 mA 满量程）：25 °C 未校准 known worst = 10+20+20+10+3.05 = 63.05 µA（0.315% FS）；P02 原表不含基准为 43.1 µA；全温未校准 worst = 63.05+45 = 108.05 µA（0.540% FS），对 R3 的 1% 只剩 0.460% 给未知项；增益网络温漂未计。
- P02 原口径 RSS = sqrt(10²+20²+20²+10²+3.05²) = 31.77 µA（0.159%）；D01 把基准当共同系统项，mixed bound = 20+sqrt(10²+20²+10²+3.05²) = 44.68 µA（0.223%）。
- post-cal：25 °C 只剩 QUANT 3.05 µA + SETTLE≈0 + INL/噪声/校准源不确定度（待查）→ cannot_conclude；全温只加 CAL_RESIDUAL（≥45 µA，0.225% FS，仅温漂下限）+ QUANT 3.05 µA + 未知项 → conditional。
角点组合（gain 与 tempco 类按读数缩放，4 mA 取 0.2；Vos 与量化不缩放；不把不同时发生的 max 硬乘）：
| 组合 ID | 温度 | 输入 | 供电/基准 | 通道状态 | 同时取极值的项 | 结论 |
|---|---|---|---|---|---|---|
| CORNER-01 | 25 °C | 4 mA | Vref min | 两通道同值 | 0.2×(SHUNT 10+GAIN 20+VREF 20)=10 µA、Vos 10 µA、量化 3.05 µA | 23.05 µA（0.115% FS） |
| CORNER-02 | 25 °C | 20 mA | Vref min | CH1 满量程、CH2 零 | SHUNT 10+GAIN 20+VREF 20、Vos 10、量化 3.05 | 63.05 µA（0.315% FS） |
| CORNER-03 | -20 °C | 4 mA | Vref min（-20 °C） | 两通道同值 | 0.2×(SHUNT+GAIN+VREF)=10 µA、0.2×TEMP_FIELD=9 µA、Vos 10、量化 3.05 | 32.05 µA（0.160% FS） |
| CORNER-04 | -20 °C | 20 mA | Vref min（-20 °C） | CH1 满量程、CH2 零 | TEMP_FIELD 45 µA + 初始 63.05 µA | 108.05 µA（0.540% FS，最坏） |
60 °C/20 mA：TEMP_FIELD=2×20 mA×25 ppm/°C×35 K=35 µA，总 98.05 µA（0.490% FS，自热待查）；MUX 20→0 mA 角点值待查，单列 cannot_conclude；未缓冲替代方案见 SETTLE_UNBUFFERED 行，不参与本表合成。
主导项动作（rank 1 映射；边界见模板 §6）：
| 主导项 | 动作 | 代价 | owner |
|---|---|---|---|
| VREF_INIT / GAIN_INIT（25 °C） | 两点 4/20 mA 校准；不足时外基准或比率测量 | 校准工位与存储；外基准成本、长期漂移 | 硬件负责人 |
| TEMP_FIELD（全温） | 多点温度校准；降 tempco（0.05% 分流、≤25 ppm/°C 基准） | 温箱与校准点数；BOM 成本 | 硬件负责人 |
| CAL_RESIDUAL（post-cal） | 提高校准源不确定度；多点温度校准 | 工位时间、存储；校准源成本 | 硬件负责人 |
| MUX_CROSSTALK / INL_LONGTERM | 每通道缓冲或占位通道；换更高位数 ADC 或定期校准 | 通道数、采样率、面积；位数/成本 | 硬件负责人 |
- 决定：保留 100 Ω + 缓冲 + 470 pF + 10 µs；把共用基准、MUX 串扰、校准残差、温度场相关组单列；只给 conditional/cannot_conclude，不给 guaranteed_pass。
- 代价：必须补 MUX/INL/噪声、校准源不确定度与增益网络温漂的台架数据；不能再用 P02 的 0.159% RSS 或 0.524 LSB 当保证。
- 下一个检查或待查：ADC 实际 Csh/Rsw、MUX 通道序列、校准源不确定度、增益网络温漂、自热；全部待查。
## 6. 记录类型与 typed block
### refuted-assumption
- 原假设与依据：0.524 LSB 证明 1 nF 缓冲“刚好不通过”、3905 LSB 是无缓冲的精确结果；依据 `design-hardware/references/projects/p02-industrial-rs485-analog.md:190-201`、`:73-73`、`:498-498`。
- 反证（`design-hardware/assets/decisions/adc-settle.r4p3.recompute.json`）：direct 一阶 3905.53 LSB、两节点 3740.25 LSB（差 -165.29 LSB，-4.23%）；buffered 1 nF 一阶 0.5239 LSB、两节点 2.27e-36 LSB。
- 影响与状态：保留 470 pF 作为保守选择，删除“1 nF 刚好不通过”的决策依据；无缓冲结论仍为 fail，引用值改为 3740 LSB；状态：corrected，1 nF 与 470 pF 的最终取舍仍需台架复验。
## 7. 验证与证据状态
- 已执行：P02 既有预算复算；两节点闭式重算（独立公式与 RK4 交叉核对）；结构/字段/哈希检查。均为 E3，`board_verified:false`。
- NOT RUN 与不能证明：SPICE、台架阶跃、MUX 切换、温循、校准、批量均未执行；不能证明实际 ADC 建立、串扰、INL/噪声、基准动态负载、校准源不确定度、增益网络温漂与整机精度。
## 8. 未知、停止与重评
- 未知：ADC/MUX/运放/基准型号、实际 Csh/Rsw、INL/噪声、校准源不确定度、增益网络温漂、MUX 串扰、自热，均待查。
- 停止与重评触发：未取得 ADC/MUX 数据或校准源不确定度前，不得把 25 °C post-cal 或全温区写成 guaranteed_pass，未做台架前不得写“建立已验证”；器件定型、通道数/采样率、温区/精度承诺、校准方案、PCB 布局或 P02 基线变化时重评。
## 9. 与现有资产分工
- 预算方法见 `design-hardware/references/decisions/d01-tolerance-and-worst-case.md`；本文只做 R4-P3 案例。
- 既有预算见 `design-hardware/references/projects/p02-industrial-rs485-analog.md:169-190`；本文不重抄，只补相关组与角点。
- 误差分类与校准边界见 `design-hardware/references/engineering-deepdives/topics/c1-sensor-to-adc-error-chain.md:99-118`、`:179-191`；本文不重复。
