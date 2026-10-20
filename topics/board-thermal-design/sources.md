# 来源与核对记录

> 核对日期：2026-10-20。只记录实际打开并读到正文/摘要的来源；搜索摘要、二手转载、Scribd/ResearchGate 镜像不作为结论依据。
>
> 证据分级：
> - **S1**：已读原厂正文，关键结论可定位到页码/章节。
> - **S2**：已读部分正文或官方摘要；只使用已读部分。
> - **S3**：仅入口/未取得正文；不用于本专题结论，列在“未取得/未使用”中。
>
> 许可：以下均为原厂公开技术文档，本专题只做转述和短引用，不复制图表/全文，不随仓库再分发 PDF。具体使用受各厂商版权/使用条款约束。

## S01 TI SPRA953D：Semiconductor and IC Package Thermal Metrics

- **发布者/作者：** Texas Instruments，Darvin Edwards / Hiep Nguyen
- **URL：** https://www.ti.com/lit/an/spra953c/spra953c.pdf
- **版本/日期：** SPRA953D，2003-12 初版，2024-03 修订；15 页。注意 URL 路径写作 `spra953c`，实际提供/阅读的是 Revision D。
- **实际查阅范围：** 第 1–13 页（正文、Table 1-1/1-2、Table 3-1、Figure 4-1、第 7 节定义）；第 14–15 页为修订历史/声明，未逐句使用。
- **关键内容（转述）：**
  - RθJA 是在特定测试板上测得的封装比较指标，不是封装常数；静止空气 JEDEC 测量中 70%–95% 的功率从测试板散出（第 2 页）。
  - 1s 与 2s2p 测试板可造成最多 50% 的 RθJA 差异；芯片/焊盘尺寸可使 CSP 的 RθJA 变化近 8 倍（第 2–3 页）。
  - Table 1-1 影响强度：PCB design 100%、chip/pad size 50%、internal package geometry 35%、altitude 18%、ambient temperature 7%、power dissipation 3%（第 2 页）。
  - 海拔 8000 ft 约热 20%；Table 1-2 倍率：3000 ft 1.1、5000 ft 1.14、7000 ft 1.17、8350 ft 1.2（第 5 页）。
  - 环境 0–100°C 时 RθJA 可改善约 10%–20%；很低功耗时 RθJA 可能比额定功率时高 2–3 倍（第 5 页）。
  - 只有已知系统 `RθJA(effective)` 时，才可用 Eq.2 估算 Tj（第 5 页）。
  - RθJC 是为加散热器设计的；用“测得壳温 + RθJC”反推塑料封装 Tj（Eq.4）是传统但无效的用法，因为 60%–95% 的热从 PCB 走（第 6–7 页）。
  - 加散热器时用 Eq.5 `Tj=Ta+P·(RθJC+RθCS+RθSA)`；已知系统 RθJA 时 Eq.6 更准（第 7 页）。
  - ΨJT 不是真热阻；`Tj≈Tc+ΨJT·P`；塑料封装典型 0.5–2°C/W，RθJC 典型 4–15°C/W；ΨJT 随板/气流变化；加散热器时不要用 ΨJT（第 8–10 页）。
  - ΨJT 测量：≤36 AWG 热电偶，珠径 ≤2×2 mm，沿对角线走线并在 PCB 上贴 25 mm 以上；粗线可使温差低估 50% 以上，误差 5%–50%（第 9 页）。
  - ΨJB：`Tj≈Tboard+ΨJB·P`；PCB 散掉 75%–95% 的热；RθJB 的单节点/等温板假设本身有误（第 10–11 页）。
  - 三电阻近似：RθJC、RθJB、Rθa（顶部对流/辐射）（第 10 页）。
  - Ambient 定义因 NEBS/AEC/JEDEC 而异；区分 absolute maximum Tj、recommended operating Tj、maximum case temperature（第 12 页）。
- **适用条件：** 指标定义、测试板影响、测量方法；对任何封装/板级 Tj 估算都适用。
- **不能推广的部分：** 文中具体百分比是 TI 测试/建模条件；不能把某个封装的 RθJA 数值套到同封装其他芯片。
- **支撑 topic.md：** 第 2 节全部、第 8.1/8.2 节、第 6.5 节。

## S02 TI SLMA002H：PowerPAD™ Thermally Enhanced Package

- **发布者：** Texas Instruments
- **URL：** https://www.ti.com/lit/pdf/slma002
- **版本/日期：** SLMA002H，1997-11 初版，2018-07 修订；31 页。
- **实际查阅范围：** 第 1–31 页；重点第 2–14 页（热焊盘、热过孔、钢网、装配）、Appendix A（第 17–23 页）。
- **关键内容（转述）：**
  - 裸露焊盘必须焊到 PCB 热焊盘；PowerPAD 不是设计成不焊接使用的（第 3 页）。
  - Table 1 典型功率处理示例：SSOP-20 标准封装 0.75 W、PowerPAD 3.25 W；TSSOP-24 标准 0.55 W、PowerPAD 2.32 W；假设 Tj=150°C、Ta=80°C，是计算示例（第 3 页）。
  - 热过孔把热焊盘连到内层/反面铜；小 die 通常 5–9 个 0.33 mm 孔对多数应用足够；大 die 可更多；继续加孔收益递减（第 8 页）。
  - 0.33 mm（13 mil）孔、1 oz 铜；孔壁铜截面约为热焊盘面积的 1%（第 8 页）。
  - 钻孔 ≤0.33 mm 可减少焊料被吸走；未塞孔时元件面用阻焊盖住（孔径 +0.1 mm 以上）；从反面盖孔会增加空洞（第 9 页）。
  - 热过孔不要用 thermal relief/车轮连接；要连续铜环连到平面（第 10 页）。
  - 建议最小焊接面积 50% 的封装热焊盘面积；标准工艺通常 >80%；X-ray 检查空洞（第 12 页）。
  - 焊料覆盖/standoff 会影响 θJA（Figure 12/13）（第 12 页）。
  - TQFP 的最大铜 land 尺寸为封装体尺寸减 2.0 mm（第 5 页）。
  - 模型结果：焊到 TI 推荐板的 PowerPAD 比 low-k 板上的标准封装低 73%，比同一块板上的标准封装平均低 44%；这是热模型结果，不是实物测量（第 23 页）。
- **适用条件：** TI PowerPAD 封装；其他厂商的 EPAD/QFN 需查各自指南。
- **不能推广的部分：** “5–9 个孔”是 TI 对小 die 的建议，不是所有封装的通用数量；孔径/镀层/塞孔按具体板厂和器件；Table 1 的瓦数是计算示例。
- **支撑 topic.md：** 第 6.1/6.2/6.4 节。

## S03 TI SLOA120：PowerPAD™ Layout Guidelines

- **发布者：** Texas Instruments，Yang Boon Quek
- **URL：** https://www.ti.com/lit/pdf/sloa120
- **版本/日期：** SLOA120，2006-05；7 页。
- **实际查阅范围：** 第 1–7 页（布局图与文字；部分图为图形，文字提取有限）。
- **关键内容（转述）：**
  - 热焊盘、热过孔、顶层铜面积、阻焊定义焊盘、连续连接（非 web/spoke）是布局要点（第 2–7 页）。
  - 推荐过孔直径 0.3 mm 或更小、间距 1 mm；具体 datasheet 优先（第 3 页）。
  - 0.127 mm 钢网时，X-ray 验证至少 50% 热焊盘面积已焊接；热焊盘开孔不要 cross-hatch；推荐 type 3 或更细焊膏（第 4–6 页）。
  - 底层铜平面外露对热性能影响很小（第 2 页）。
  - 过孔可堵塞以防焊料流失，但会增加成本；不是必需（第 3 页）。
- **适用条件：** PowerPAD 布局；与 S02 配合。
- **不能推广的部分：** 图形中的具体尺寸是示例；按器件 datasheet；过孔间距 1 mm 与 SLMA002H 的 1.5 mm 建模板语境不同。
- **支撑 topic.md：** 第 6.1/6.2/6.4 节。

## S04 ADI MT-093：Thermal Design Basics

- **发布者：** Analog Devices
- **URL：** https://www.analog.com/media/en/training-seminars/tutorials/MT-093.pdf
- **版本/日期：** MT-093，Copyright 2009；13 页。
- **实际查阅范围：** 第 1–13 页。
- **关键内容（转述）：**
  - AD8017AR：25°C 时 1.3 W，条件是两层 PCB、约 4 in²（~2500 mm²）2 oz 铜；塑料封装 Tj 约 150°C，长期 >175°C 可失效（第 1 页）。
  - AD8016 PSOP3 + 10 in² 1 oz 铜：70°C 环境可耗散 3 W，θJA=18°C/W（Tjmax=125°C）（第 5 页）。
  - 设计建议：尽可能大铜面积、多层+多过孔、2 oz 以上铜、通风、垂直放置、必要时强制风冷、散热走线不盖阻焊、降低供电电压（第 6 页）。
  - 小封装 AD8057/58：SOT-23-5 240°C/W、8-pin µSOIC 200°C/W、SOIC 160°C/W（仅这些器件/封装，不可推广）（第 7 页）。
  - 裸露焊盘焊接与否：AD9430 25 vs 32°C/W；AD6645 23 vs 30°C/W；200 LFPM 时 17°C/W（第 10–12 页）。
  - 数据转换器功耗随采样率/输出负载变化；AD9245 380 mW、AD9430 1.5 W、AD6645 1.75 W 等例子（第 8–12 页）。
- **适用条件：** 运放/数据转换器的板级热设计；铜面积/过孔/气流建议。
- **不能推广的部分：** 具体 θJA/功率是 ADI 器件在所述板条件下的值；不能当通用封装规则。
- **支撑 topic.md：** 第 2.2/2.3 节、第 3.6 节、第 6.3 节、第 7.3 节。

## S05 TI SLVAE85A：An Empirical Analysis of the Impact of Board Layout on LDO Thermal Performance

- **发布者：** Texas Instruments
- **URL：** https://www.ti.com/lit/an/slvae85/slvae85.pdf
- **版本/日期：** SLVAE85A，2019-02 初版，2025-09 修订；30 页（含附录布局图/数据表）。修订记录称技术内容未变。
- **实际查阅范围：** 第 1–30 页；重点第 2–12 页（布局、测试方法、结果、结论）。
- **关键内容（转述）：**
  - 4 层、9 in²（3 in × 3 in）测试板；外层 2 oz、内层 1 oz；五种铜面积/过孔布局（第 2–3 页）。
  - TPS745 WSON 实测 θJA：datasheet 80.3、1S0P 169.2、内部断开 83.1、JEDEC High-K 近似 61.3、热增强 46.8、热饱和 43.2°C/W；相对 1S0P 降低 74.4%，相对 datasheet 降低 46.2%（第 8、10 页）。
  - TPS7B82-Q1 TO-252：38.8/91.2/46.1/31.9/26.8/26.3°C/W；相对 1S0P 降低 71.2%，相对 datasheet 降低 32.3%（第 9–10 页）。
  - TLV755P SOT-23：231/227/156/155/108/104°C/W；相对 1S0P 降低 54.3%，相对 datasheet 降低 54.9%（第 9–10 页）。
  - “内部断开”布局仅 0.07 in² 连接铜，却把 WSON/TO-252 的 θJA 降低近 50%；内层铜即使不直接连接也有帮助（第 8 页）。
  - 热优化布局相对 datasheet JEDEC 值可降低 θJA 32%–55%；相对最差 1S0P 布局可小至 1/4（第 10–12 页）。
  - 铜面积收益饱和：热增强布局约一半铜面积即可达到饱和布局 8% 以内的 θJA；过孔收益也饱和（第 11–12 页）。
  - 热焊盘封装从过孔/铜面积获益更大；SOT-23 无热焊盘，更依赖顶层/底层铜（第 9–12 页）。
  - 文档中的热过孔尺寸文字出现“20 millimeter / 10-mm”字样，与常见 mil 单位不符，本专题不引用该具体尺寸；以 JESD51-9 和实际板厂为准（第 2 页，待核）。
  - 注意：三个例子里实测 High-K 近似值都低于 datasheet 值，作者没有解释差异；“datasheet 保守”只是观察，不是通用保证（第 8–10 页）。
- **方法/精度：** θJA 由“热关断阈值–功耗斜率”间接得到，不是直接结温测量；作者明确说精度受烤箱 ±2°C、环境温度/功耗漂移、Vout 随温度下降导致功耗增加的限制（第 7 页）。这些值适合看相对趋势，不应当作精确绝对热阻。
- **适用条件：** LDO/小封装 SMD 的板布局；具体测试板/器件。
- **不能推广的部分：** 百分比是这三种封装/测试板的结果；不能保证所有封装都降低 32%–55%。
- **支撑 topic.md：** 第 2.2 节、第 4.1 节、第 6.2/6.3 节、附录 A。

## S06 TI SNVA753：LDOs Thermal Performance in Small SMD Packages

- **发布者：** Texas Instruments
- **URL：** https://www.ti.com/lit/snva753
- **版本/日期：** SNVA753，2016-04；约 30 页。
- **实际查阅范围：** 第 1–15 页（热指标、封装比较、脉冲负载、FAQ）；第 17–30 页附录布局图仅浏览。
- **关键内容（转述）：**
  - RθJA 是标准化测试环境下的封装比较基线，不是实际板值（第 4–5 页）。
  - 封装比较（数据手册值；测试板未在文中注明）：LP5907 DSBGA 206.1、SOT-23 193.4、X2SON 216.1°C/W（第 11 页 Table 2）；LP5910 DSBGA 202.8（第 9 页 Figure 8）、WSON 79.2°C/W（第 11 页 Table 2）。
  - Table 2 的“measured temperature at PD=375 mW”是壳顶温度，不是结温；不能把两列直接换算（第 11 页）。
  - 脉冲负载：低频脉冲的峰值壳温较低；频率升高后壳温上升更快；结果依赖封装/板的热容和热阻（第 12–13 页）。
  - 裸露焊盘/铜面积/过孔的建议与 S02/S05 一致（第 14 页起）。
  - 无热像仪/热电偶时，可逐步增大功耗直到热关断，用 `RθJA=(Tj−Ta)/PD` 估算应用板热阻（第 15 页）。
- **适用条件：** 小封装 LDO 的热性能比较；脉冲负载定性趋势。
- **不能推广的部分：** 具体 θJA 是特定器件/测试板；不能套到其他 LDO。
- **支撑 topic.md：** 第 2.1 节、第 5.3 节（脉冲定性）；第 8.5 节提到热关断法但标为待验证，具体以 S06 第 15 页和器件手册为准。

## S07 TI SSZT950：LDO Basics: Thermals – How Hot is Your Application?

- **发布者：** Texas Instruments
- **URL：** https://www.ti.com/document-viewer/lit/html/SSZT950
- **版本/日期：** 2017-09 文章，PDF 渲染版 2023-08；6 页。
- **实际查阅范围：** 第 1–6 页（公式为图片，已核对）。
- **关键内容（转述）：**
  - TPS732 的 SOT-23（2.9×1.6 mm）RθJA=205.9°C/W，SOT-223（6.5×3.5 mm）53.1°C/W；这是该器件两个封装的数据手册值（第 1 页）。
  - LDO 推荐工作结温 −40–125°C；这是作者对 LDO 的概括，具体器件查 datasheet（第 1 页）。
  - `Tj=Ta+RθJA·PD`，`PD=(Vin−Vout)·Iout+Vin·Iq`（第 2 页）。
  - 算例：5.5 V→3 V、250 mA、Iq=0.95 mA，PD=0.63 W；SOT-23 得 Tj≈154.72°C，SOT-223 得 58.45°C；未考虑板布局差异（第 2 页）。
  - 热关断典型 160°C，降到约 140°C 恢复；这是 TPS732 的典型值，不是通用阈值（第 2 页）。
  - 增大输入/输出/地平面铜面积会降低 RθJA；多层板建议用一整层地平面（第 2–3 页）。
  - 可在输入串联电阻分担功耗：`Rmax=(Vin−Vout−Vdropout)/(Iout+Iq)`，`PD(Rmax)=(Iout+Iq)²·Rmax`；但会降低 PSRR/瞬态余量，文中未展开（第 3–4 页）。
- **适用条件：** LDO 热基础/示例；TPS732 的具体值。
- **不能推广的部分：** 205.9/53.1°C/W、160/140°C、−40–125°C 都是 TPS732/该文的条件。
- **支撑 topic.md：** 第 3.1 节、第 4.1 节。

## S08 TI SLUAAT8：Using MOSFET Transient Thermal Impedance Curves In Your Design

- **发布者：** Texas Instruments，John Wallace
- **URL：** https://www.ti.com/lit/pdf/sluaat8
- **版本/日期：** SLUAAT8，2023-12；7 页。
- **实际查阅范围：** 第 1–5 页。
- **关键内容（转述）：**
  - ZθJC 曲线在 1.5 in × 1.5 in FR4、1 in² 2 oz Cu 焊盘上测量，按静态 RθJC 归一化（第 2 页）。
  - `ΔTj = P · ZθJC · RθJC`；按脉冲宽度和占空比取归一化值（第 2 页）。
  - 例：CSD17579Q5A 在 2 ms、约 11% 占空比下 Z≈0.52（第 3 页）。
  - 例：CSD19532Q5B RθJC=0.8°C/W、Rds(on) max 4.9 mΩ×2.1=10.3 mΩ；1 ms 单脉冲 Z≈0.17，1 ms/50% Z≈0.56；Tc=110°C 时峰值电流显著低于 Tc=25°C（第 4 页）。
  - 假设 Tc 可恒定在 25°C 需要无限热沉；实际应按最高 PCB 温度（例 110°C）（第 4 页）。
  - 重复脉冲可靠性降额常用 10–25°C（第 5 页）。
- **适用条件：** MOSFET 单脉冲/重复脉冲的 ZθJC 用法；具体器件曲线。
- **不能推广的部分：** 具体 Z 值/电流是 CSD 器件的例子；不能套到其他 MOSFET。
- **支撑 topic.md：** 第 2.1/2.5 节、第 5.2/5.4/5.5 节。

## S09 ST DM00241971（AN4783）：Thermal effects and junction temperature evaluation of Power MOSFETs

- **发布者：** STMicroelectronics
- **URL：** https://www.st.com/resource/en/application_note/dm00241971-thermal-effects-and-junction-temperature-evaluation-of-power-mosfets-stmicroelectronics.pdf
- **版本/日期：** DocID028570 Rev 1；41 页。
- **实际查阅范围：** 第 5–8 页（Rth/Zth、热因子）、第 19–28 页（损耗）；其余页未逐句使用。
- **关键内容（转述）：**
  - 热域与电域类比：`ΔT=P·Rθ`；层热阻 `R=L/(k·A)`；热容 `C=ρ·cp·V`（第 5–6 页）。
  - 极短脉冲（<1 ms 量级）热量主要留在 die；更长脉冲进入封装/PCB，需用包含外部路径的 Zth/模型（第 7–8 页）。
  - 总损耗 `Ptot=Pcond+Psw+PCoss+Pdriving+Pdiode`（第 19 页）。
  - 导通损耗 `Pcond=I²RMS·Rds(on)(T)`；阻性/感性/CCM/DCM 的电流波形不同（第 20–23 页）。
  - 开关损耗：阻性负载 `1/6·Vds·Id·tr/T`、`1/6·...·tf/T`；感性负载开通可能很小、关断 `1/2·Vdsmax·Idpeak·tf/T`（第 24–25 页）。
  - 公式法不能预测真实参数；正确做法是测 Eon/Eoff，`Psw=Eon·fsw`、`Poff=Eoff·fsw`；二极管 `Pdiode=Qrr·Vds·fsw`（第 25–28 页）。
- **适用条件：** MOSFET 损耗分项和 Zth 概念；具体拓扑/器件需手册。
- **不能推广的部分：** 公式依赖负载/波形/测试条件；不能把某器件的 tr/tf 或系数套到其他器件。
- **支撑 topic.md：** 第 3.2/3.3 节、第 5.3 节。

## S10 Cree LED CLD-AP5：Thermal Management of XLamp LEDs

- **发布者：** Cree LED
- **URL：** https://assets.cree-led.com/a/da/x/XLamp-Thermal-Management.pdf
- **版本/日期：** CLD-AP5 Rev 5；© 2004–2023；19 页。
- **实际查阅范围：** 第 1–10 页；其余页未逐句使用。
- **关键内容（转述）：**
  - XLamp 最大工作 Tj 通常 150°C；超过可永久/灾难性损坏（第 2 页）。
  - 高温使光输出下降（可恢复）、色偏、Vf 下降、寿命缩短（第 1–3 页）。
  - 热功率估算 `Pt=0.75·Vf·If`：该文估计蓝/白 XLamp 实际约 50%–60% 输入功率变热，75% 是**保守假设**；不是所有 LED 的通用效率（第 4 页）。
  - 自然对流 h 约 5–20 W/m²K；强制风冷空气可到 100 W/m²K，水可到 10,000；自然对流粗算可用 10 W/m²K（第 5 页）。
  - 热网络：junction → solder point (TSP) → PCB → TIM → heatsink → ambient；`ΘJ-SP` 从 datasheet；`Tj=TSP+Θth·Ptotal`（第 6–9 页）。
  - 电流降额曲线按系统 ΘJ-A = 10/15/20/25°C/W 给出（第 8 页）。
  - 热堆叠：减少材料界面、用 TIM 填空气隙、金属芯或 FR4（第 9 页）。
- **适用条件：** Cree XLamp LED；具体型号的 Rth/Tj 限值查 datasheet。
- **不能推广的部分：** 0.75 热功率比例、150°C、h 范围都是该应用笔记/XLamp 的条件；其他 LED/封装不同。
- **支撑 topic.md：** 第 3.5 节、第 7.2 节、附录 A。

## S11 Cree LED：Optimizing PCB Thermal Performance for XLamp LEDs

- **发布者：** Cree LED
- **URL：** https://downloads.cree-led.com/files/da/x/XLamp-PCB-Thermal.pdf
- **版本/日期：** Cree CLD-AP37 Rev 4A；© 2010–2025；21 页。
- **实际查阅范围：** 第 1–6 页（FR-4/MCPCB、热过孔）；其余页未逐句使用。
- **关键内容（转述）：**
  - FR-4 星形板 1.6 mm、约 270 mm²：厚向热阻约 30°C/W（70 µm 顶层铜/1588 µm FR-4 k=0.2/70 µm 底层铜）；热源很小时可超过 700°C/W（第 3 页）。
  - 单层 MCPCB 同尺寸约 0.2°C/W；小热源约 5.3°C/W；限制因素是介质（第 4 页）。
  - 单孔公式 `θ=l/(k·A)`；0.6 mm 填充焊料孔单孔约 96.8°C/W；N 孔并联 `θ=l/(N·k·A)`；只适用于热源正对过孔，否则扩散热阻增加（第 5–6 页）。
  - 通孔与介质可按并联处理；开口孔与填充孔的面积公式不同（第 6 页）。
- **适用条件：** LED PCB 热过孔/FR-4/MCPCB；具体叠层/孔径。
- **不能推广的部分：** 具体热阻是 Cree 的板/热源条件；不能当所有 FR-4/MCPCB 的通用值。
- **支撑 topic.md：** 第 6.2/6.3 节。

## S12 ams OSRAM AN049：Package-related thermal resistance of LEDs

- **发布者：** ams-OSRAM AG
- **URL：** https://look.ams-osram.com/m/2b5062d58e23258f/original/Package-related-thermal-resistance-of-LEDs.pdf
- **版本/日期：** AN049，2022-07-22；12 页。
- **实际查阅范围：** 第 1–8 页；其余页未逐句使用。
- **关键内容（转述）：**
  - `Rth=ΔT/Q`；LED 有“电学热阻” `Rth_elec=ΔT/Pel` 和“真实热阻” `Rth_real=ΔT/(Pel−Popt)` 两种定义；2012 年后引入真实热阻，典型光效 25%–50%（第 4–5 页）。
  - Rth_JS 用热瞬态 TSP 法测：标定 Vf–T 的 TK，加热到平衡，切换小测量电流测 Vf，得到 Zth(t)；用两种 PCB 材料测到曲线分离点，`Rth_JS=Zth(ts)`（第 5–7 页）。
  - 测量“far from trivial”；前几十微秒因时间分辨率无法测，需要 offset correction（第 7 页）。
  - datasheet 视器件而定，给 typ/max real Rth_JS、typ/max electrical Rth_JS（max=typ+6σ）和典型光效中的一部分或全部（第 8 页）。
  - 参考点：多数 SMT LED 是 solder point；金属芯/胶装器件可能是 board temperature（第 4 页）。
- **适用条件：** LED 的 Rth_JS 定义/测量/数据手册值；具体型号。
- **不能推广的部分：** 具体 Rth 值/光效是 OSRAM 器件；测量方法需要专用标定。
- **支撑 topic.md：** 第 3.5 节、第 8.3 节、附录 A。

## S13 Vishay 30380：Thermal Management for Surface-Mount Devices

- **发布者：** Vishay Dale，Bryan Yarborough
- **URL：** https://www.vishay.com/docs/30380/terminalderating.pdf
- **版本/日期：** Document 30380，Revision 19-Mar-2018；4 页。
- **实际查阅范围：** 第 1–4 页。
- **关键内容（转述）：**
  - 环境降额曲线源于军用标准（如 MIL-PRF-39009/39017）；通孔轴向电阻约 80%–90% 的热经空气对流，SMD 可有多达 90% 的热经 PCB 传导；不能把通孔曲线直接套到 SMD（第 1–2 页）。
  - 端子降额要求用户保证 PCB 上的端子温度不超过规定值（第 2 页）。
  - `Rth=(T_hotspot−T_terminal)/P`；例 WSLF2512 0.5 mΩ 为 6.7°C/W（特定型号/阻值）（第 2 页）。
  - 热阻测量：不同功率下用热像仪测最热点/端子，板水平放在 25°C 静止空气、自然对流（第 3 页）。
  - Power Metal Strip 的 Rth 随阻值/合金/厚度/修调变化；厚膜/箔电阻同封装通常一个 Rth（第 4 页）。
- **适用条件：** SMD 电流检测/功率电阻的热降额；具体系列。
- **不能推广的部分：** 6.7°C/W 是 WSLF2512 0.5 mΩ 的值；不能套到其他电阻。
- **支撑 topic.md：** 第 3.4 节。

## S14 Vishay 28771：Basics of Linear Fixed Resistors

- **发布者：** Vishay Beyschlag
- **URL：** https://www.vishay.com/docs/28771/basics.pdf
- **版本/日期：** Document 28771，Revision 11-Nov-2008；8 页。
- **实际查阅范围：** 第 1–8 页。
- **关键内容（转述）：**
  - 额定耗散定义为额定环境温度（通常 +70°C）下的最大耗散；高于该温度按降额曲线降低功率；典型曲线到 +70°C 为 100%，到 +125°C 线性降到 0%（第 4 页，Fig.9）。
  - 脉冲稳定性：短脉冲可高于额定负载；需同时满足平均负载不超过该环境温度下的额定负载、脉冲负载不超过给定脉宽的允许值、峰值电压低于允许值（第 4 页）。
  - 标准试验脉冲：IEC 60115-1 4.27 的 1.2/50 µs（5 个，间隔 ≥12 s）和 10/700 µs（10 个，间隔 ≥60 s）；判据是脉冲后的阻值变化（第 4 页）。
  - 热阻是装配相关量；目录值来自标准化试验装配，实际温升用 `Δϑ=P·Rth`，Rth 取实际装配条件（第 4 页）。
  - 不同技术最高工作温度示例：碳膜/金属膜/厚膜 +155°C，金属箔/碳合成 +150°C，线绕 +400°C，Power Metal Strip +275°C（第 5 页）。
- **适用条件：** 通用薄膜/厚膜电阻的降额/脉冲概念；具体产品 datasheet 优先。
- **不能推广的部分：** +70°C/+125°C 是典型曲线；不同产品可能不同。
- **支撑 topic.md：** 第 3.4 节。

## S15 Vishay 28870：Pulse Load on SMD Resistors: At the Limit

- **发布者：** Vishay Beyschlag，Joachim von der Ohe
- **URL：** https://www.vishay.com/docs/28870/pulseloadsmdlimit.pdf
- **版本/日期：** Document 28870，Revision 15-Aug-2013；3 页。
- **实际查阅范围：** 第 1–3 页。
- **关键内容（转述）：**
  - 连续脉冲串的负载能力远低于单脉冲；单脉冲和连续脉冲要分开评估（第 1 页）。
  - 连续脉冲三个条件：A 平均功率不超过 P70；B 峰值功率随脉宽的允许值查 datasheet/CECC 详细规范；C 峰值电压不超过允许值（第 1–2 页）。
  - 标准单脉冲试验：1.2/50 µs（5 个，间隔 ≥12 s）或 10/700 µs（10 个，间隔 ≥60 s）；判据是阻值变化（第 3 页）。
  - 技术比较（1 kΩ、同体尺寸、电容放电 τ=16 ms）：厚膜片式最低，薄膜片式优于厚膜，薄膜 MELF 最优；这是特定样品/条件的比较（第 3 页）。3 ms 矩形脉冲是 S17 的测试条件，不是本文的条件。
- **适用条件：** SMD 薄膜/厚膜片式电阻的脉冲选型；具体 datasheet 脉冲图。
- **不能推广的部分：** P70 约 50 mW–1 W 是该文范围；结论不能外推到所有阻值。
- **支撑 topic.md：** 第 3.4 节。

## S16 Vishay 50512：SMD Resistor Thermal Analysis

- **发布者：** Vishay Barry
- **URL：** https://www.vishay.com/docs/50512/smd_resistor_thermal_analysis.pdf
- **版本/日期：** Document 50512，Revision 16-Jul-2026；2 页。
- **实际查阅范围：** 第 1–2 页。
- **关键内容（转述）：**
  - 只考虑传导、忽略对流/辐射时，膜温由各层热阻串联决定：`θtot=θsub+θmet+θsold+θPCB+θpre`；PCB 热阻通常比热沉高一个数量级（第 1 页）。
  - 算例：`θres=1.2+0.2=1.4°C/W`；膜温上限 250°C、焊点 100°C → 元件侧 107.1 W；板侧 35°C、`θPCB+θpre+θsold=2.3°C/W` → 15.2 W；整个组件取较小值 15 W（第 2 页）。
  - 方法：以焊点为界拆成两段，各自用允许温差/热阻算最大功率，取小值（第 2 页）。
- **适用条件：** SMD 电阻的单路径传导热分析；焊点温度已知/可控。
- **不能推广的部分：** 算例的 1.2/0.2/2/0.2/0.1°C/W、250/100/65°C 都是假设值，不是产品参数。
- **支撑 topic.md：** 第 3.4 节。

## S17 Vishay MS9702509-2401：12 Things to Know About Resistors in Pulse Load Applications

- **发布者：** Vishay
- **URL：** https://www.vishay.com/docs/48516/_ms9702509-2401-vishaychecklistpulseload.pdf
- **版本/日期：** MS9702509-2401，© 2024；4 页。
- **实际查阅范围：** 第 1–4 页。
- **关键内容（转述）：**
  - 电阻可承受高于额定耗散 P70 的脉冲，但是否安全取决于脉冲数量/间隔、形状、持续时间；短脉冲热量留在膜内但时间短，长脉冲散热已开始，限值不同（第 1 页）。
  - 单脉冲与连续脉冲判据不同：单脉冲平均功率趋近 0；连续脉冲要求 0 < 平均功率 ≤ P70，同时峰值功率/电压不超过规定值（第 1 页）。
  - 脉冲图通常定义在室温；高温或叠加连续功率需额外降额；读图要确认覆盖整个阻值范围并注明允许阻值变化（第 2 页）。
  - 工艺比较：厚膜片式有限，薄膜片式优秀，薄膜 MELF 最高，线绕可承受极高脉冲能量；这些是示例/典型值（第 3–4 页）。
- **适用条件：** 电阻脉冲负载检查清单；具体 datasheet 曲线。
- **不能推广的部分：** 清单以判据/图表为主；具体数值（如 60 kJ、1000×/3 ms、G207 17 W→17 kW、1000 kg/70 km/h）仅作为示例，不能外推。
- **支撑 topic.md：** 第 3.4 节。

## S18 TI AN-1520 / SNVA183B：A Guide to Board Layout for Best Thermal Resistance for Exposed Packages

- **发布者：** Texas Instruments（原 National Semiconductor）
- **URL：** https://www.ti.com/lit/an/snva183b/snva183b.pdf
- **版本/日期：** SNVA183B，2006-09 初版，2013-04 修订；15 页。
- **实际查阅范围：** 第 1–15 页。
- **关键内容（转述）：**
  - 9 in²、4 层 2/1/1/2 oz 测试板、LM2652 28-lead e-TSSOP、2 W：θJA Ideal 25.5、Real#1 27.7、Real#2 26.3、Real#3 25.0、Modified JEDEC 30.3°C/W；旧 2 层板 43.4°C/W（1.5 W）（第 6 页 Table 2）。
  - 没有顶/底 GND 平面的 Modified JEDEC 板比 Real#3 高约 21%（30.3 vs 25.0）（第 6–7 页）。
  - 顶/底铜面积降到约 50%，θJA 只增加 3.1%（25.5→26.3）（第 6–7 页）。
  - 阻焊覆盖降低 θJA 4.9%（26.3→25.0），作者归因于辐射（第 6–7 页）。
  - Dog-bone 区域加大并增加过孔带来约 5% 改善；但 FEA 单独把 **dog-bone 区域**过孔从 0 增到 24 个只降低 0.5%。“5% 主要来自铜面积”是对第 7、12 页结果的解读，不是原文单句归因。
  - 焊料覆盖从 100% 降到 50/20/10/5%，θJA 增加约 4/13/19/34%；10% 是临界点；>50% 时变化 <5%（第 12 页）。
  - 0.33 mm 相对 0.2 mm 热过孔：小热焊盘（≤4 孔）θJA 改善 15%–25%（即 0.2 mm 会使 θJA 增加 15%–25%）；大热焊盘（≥9 孔）影响一般 <10%（第 13 页）。
  - 设计建议：至少 4 层、3×3 in、2/1/1/2 oz；热过孔连接 DAP、内层 GND、底层 GND；尽量 0.33 mm；过孔受限时放 DAP 周边（第 13 页）。
- **适用条件：** 带 exposed DAP 的 e-TSSOP/e-QFP/LLP 等封装；特定测试板。
- **不能推广的部分：** 单一封装实测 + LLP FEA；9 in²/4 层/2-1-1-2 oz 条件；不能直接推广到现代高密度板/不同外壳/强制风冷。
- **支撑 topic.md：** 第 6.2/6.3/6.4 节、附录 A。

## S19 Infineon AN-2021-02：Thermal measurement for D2PAK on PCB

- **发布者：** Infineon Technologies AG
- **URL：** https://www.infineon.com/assets/row/public/documents/24/42/infineon-an-2021-02-thermal-measurement-for-d2pak-on-pcb-applicationnotes-en.pdf
- **版本/日期：** V2.0，2021-05-03（V1.0 2021-02-19；V1.1 2021-04-20）；25 页。
- **实际查阅范围：** 第 1–25 页。
- **关键内容（转述）：**
  - 测试矩阵：2L/4L × 1 oz/2 oz；TO-263（D2PAK）1700 V CoolSiC MOSFET；过孔间距 1.3 mm；总漏极铜面积 67.45/112.52/163.94/229.35/309.92 mm²（1S/1.67S/2.43S/3.4S/4.6S）；内过孔 0.3/0.4/0.5 mm（第 8–9 页）。
  - 0.3 A：2L1OZ 从 8×4 的 46.84°C 降到 16×8 的 29.37°C；4L2OZ 从 37.23°C 降到 28.56°C；小阵列时 4L2OZ 比 2L1OZ 低约 10°C，大阵列时四种板几乎相同（第 11 页 Table 7）。
  - 结论：总漏极铜 <3S（202.35 mm²）时，加层/加铜厚显著改善，且加层比加铜厚更有效；>3S 后影响减弱（第 12 页）。
  - 0.4 mm 内过孔在该测试矩阵中通常比 0.3/0.5 mm 温升更低（第 16–18 页）。
  - 去掉 D2PAK 周围铜上的阻焊，Rthja 降低约 4°C/W（第 14–15 页）。
  - 散热器只在总漏极铜 <2.7S（182.12 mm²）时才值得考虑；>该面积时加铜更有效（第 19–21 页）。
- **适用条件：** TO-263/1700 V CoolSiC、0.1–0.5 A、自然对流、特定板；不是通用规则。
- **不能推广的部分：** 3S/2.7S 阈值、0.4 mm 最优直径都是该测试矩阵的经验值；不能套到 QFN/其他封装/更高功率。
- **支撑 topic.md：** 第 6.2/6.3 节、附录 A。

## S20 Nexperia AN11261：RC Thermal Models

- **发布者：** Nexperia B.V.（原 NXP；Rev 2.0 2014-05-19）
- **URL：** https://assets.nexperia.com/documents/application-note/AN11261.pdf（本次通过 Wayback 捕获读取；直链 403）
- **版本/日期：** Rev 5.0，2021-03-18；19 页。
- **实际查阅范围：** 第 1–19 页。
- **关键内容（转述）：**
  - Zth 由阶跃功率脉冲测量；脉冲 >~1 s 即稳态，Zth 平台值就是 Rth；热惯性使短脉冲可承受更大功率；重复脉冲曲线给出 RMS 温升（第 2 页）。
  - `ΔTj=P·Zth(t)`（方波脉冲）；恒定功率 `ΔTj=P·Rth`（第 3 页）。
  - Foster 模型是 Zth 曲线的半经验拟合，R/C 不对应物理位置，不能由材料常数计算，不能拆分或直接接散热器网络（第 4 页）。
  - Cauer 模型节点有物理意义，可外接 PCB/散热器网络；外部网络末端接环境源（第 5–6 页）。
  - 模型局限：Rth 随温度变化；Tmb 被假设等温；脉冲 >1 s 时必须把器件、PCB、散热器和附近材料一起建模（第 13 页）。
- **适用条件：** 热模型语义/使用；不是 PCB 布局指南。
- **不能推广的部分：** 具体 BUK7S1R0-40H 的 Rth/Zth 是示例；Foster/Cauer 不能混用。
- **支撑 topic.md：** 第 5.3/5.4 节。

## S21 Vishay 34256：Using IHLP's in Automotive Applications — PCB Trace Size Concerns

- **发布者：** Vishay Dale
- **URL：** https://www.vishay.com/docs/34256/ihlpaapp.pdf
- **版本/日期：** Document 34256，Revision 14-Aug-2008；5 页。
- **实际查阅范围：** 第 1–5 页；载流温升章节第 3–4 页、Table 1 第 4 页。
- **关键内容（转述）：**
  - 历史标准（NBS 1956、MIL-STD-275、IPC-2221）未能一致预测 PCB 走线温升；该文早于 IPC-2152，未评价 IPC-2152（第 3 页）。
  - 外部走线经验式 `I=3.188·ΔT^0.45·W^0.79·Th^0.53`；ΔT 用 °C，W/Th 用 mm。原文明确条件：外部走线、ΔT 30–70°C、W 0.25–5.0 mm、Th 0.0175/0.035/0.07 mm；“单根孤立、自然对流”是此类经验式通常隐含的假设，原文未写明，需按原标准核对（第 4 页）。
  - Table 1 给出示例：1.0 mm×0.035 mm 在 30/40/50/60/70°C 温升下 2.5/2.8/3.1/3.4/3.6 A；2.0 mm×0.035 mm 在 40°C 下 4.9 A；5.0 mm×0.07 mm 在 70°C 下 18.8 A（第 4 页）。
  - 内层走线按外部走线最大电流的 50% 降额（第 4 页）。
- **适用条件：** 一阶走线选型；不是 IPC-2152/安全标准。
- **不能推广的部分：** 不含平面、过孔、气流、外壳、邻近热源；不能外推到表范围外。
- **支撑 topic.md：** 第 6.3 节、附录 A。

## S22 nVent HOFFMAN Spec-00488 Rev F：Heat Dissipation in Sealed Electrical Enclosures

- **发布者：** nVent HOFFMAN
- **URL：** https://www.nvent.com/sites/default/files/acquiadam_assets/2021-02/Spec-00488.pdf
- **版本/日期：** Spec-00488 Rev F；未标日期；6 页。
- **实际查阅范围：** 第 1–6 页。
- **关键内容（转述）：**
  - 适用于有垫圈、无通风的电气外壳；未涂装铝/不锈钢因辐射换热较差，温升更高；非金属外壳与涂装金属外壳的换热特性相近（第 1 页）。
  - 表面积按六个面计算：`A=2[(A×B)+(A×C)+(B×C)]/144`（英寸→ft²）；靠墙等不能换热的表面要扣除；不能用体积代替表面积（第 1 页）。
  - 示例：48×36×16 in 涂装钢壳、300 W，表面积 42 ft²，功率密度 7.1 W/ft²，由图读得温升约 30°F（16.7°C）（第 1 页）。
  - 建议保留 25% 安全裕量；内部循环风扇最多改善约 10%；图表是平均温升，局部热点可能更高（第 1–2 页）。
  - 海拔升高使空气密度下降，应增加通过外壳的空气流量（第 5 页）。
  - 进风口宜在侧面靠近底部，出风口在对侧靠近顶部；出风口面积至少等于进风口（第 5 页）。
- **适用条件：** 大型密封电气柜；不是小型 PCB 密封盒。
- **不能推广的部分：** 图表读数近似；25%/10% 是建议/经验；未给 k 数值。
- **支撑 topic.md：** 第 7.2/7.3 节、附录 A。

## S23 nVent HOFFMAN：Calculating Heat Dissipation in nVent HOFFMAN Enclosures（White Paper）

- **发布者：** nVent HOFFMAN
- **URL：** https://www.nvent.com/sites/default/files/acquiadam_assets/2022-01/Heat%20dissipation_nVent_HOFFMAN_ENG.pdf
- **版本/日期：** 未标日期；hosted 2022-01；16 页。
- **实际查阅范围：** 第 1–12 页；后续表格未逐页读。
- **关键内容（转述）：**
  - 封闭外壳关系：`(Ti−Tu)=Qv/(k·A)`、`Qs=k·A·ΔT`、`Qe=Qv−Qs`、所需风量 `V=3.1·Qv/ΔT`（m³/h，Qv W，ΔT K）（第 3 页）。
  - 10 K 温升使元件寿命减半、失效率翻倍（相对于最大允许工作温度）（第 3 页）。
  - 推荐外壳内部平均温度 +35°C 作为常规值（第 4 页）。
  - 表面积按安装方式用 IEC 60890 公式：独立安装 `A=1.8H(W+D)+1.4WD`；壁挂 `A=1.4W(H+D)+1.8HD`；柜列首/末、柜列内、带顶盖等各有不同（第 5 页）。
  - 表值是特定 nVent 外壳在 ΔT=20 K 下的散热功率，不能跨产品套用（第 6–12 页）。
- **适用条件：** 电气柜；不是小型 PCB 盒。
- **不能推广的部分：** k 未给；表值是特定型号；+35°C/10 K 是经验/常规值。
- **支撑 topic.md：** 第 7.2 节、附录 A。

## S24 FLIR：Infrared Camera Accuracy and Uncertainty in Plain Language

- **发布者：** Teledyne FLIR
- **URL：** https://www.flir.com/discover/rd-science/infrared-camera-accuracy-and-uncertainty-in-plain-language/
- **版本/日期：** 未标日期；访问 2026-10-20。
- **实际查阅范围：** 全文网页。
- **关键内容（转述）：**
  - 典型相机精度 ±2°C 或读数的 2%，各误差项按 RSS 合成（Accuracy section）。
  - 不确定度来源：发射率、反射环境温度、透射率、大气温度、相机响应、黑体校准；短距离实验室误差较小，长距离大气吸收增加；环境补偿不良可增加 10°C 以上（Uncertainty section）。
  - 目标应至少占 10×10 像素；小于一个像素时背景辐射主导（Spot size section）。
- **适用条件：** 红外测温的通用误差认知；具体型号查 datasheet/校准证书。
- **不能推广的部分：** ±2°C/2% 是典型规格，不是校准保证；文章未给型号/条件。
- **支撑 topic.md：** 第 8.2 节、附录 A。

## S25 Advanced Energy：Low Voltage Power Supplies and Convection Cooling

- **发布者：** Advanced Energy
- **URL：** https://www.advancedenergy.com/getmedia/bbd7608a-aa71-4888-a3f4-bc7dbba559bf/en-lv-convection-cooling-application-note.pdf
- **版本/日期：** ©2020；文档 ENG-Glass-Gob-265-01 9.20；5 页。
- **实际查阅范围：** 第 1–5 页。
- **关键内容（转述）：**
  - 自然对流安装方向：底板朝下或侧壁安装通常较好，侧壁因烟囱效应最佳；倒装应避免（第 2 页）。
  - 密封盒内放置电源可能导致热失控；必须提供让冷空气进入的通风；电源自身功耗对外壳温度影响很大（第 3 页）。
  - 自然对流无风扇，风扇常是首先失效的部件（第 2 页）。
  - 通过测试获取热数据是验证设计的最佳方式（第 4 页）。
- **适用条件：** 电源产品的自然对流安装；不是 PCB 板级通用规则。
- **不能推广的部分：** 定性建议，无公式/数值表；具体产品查安装手册。
- **支撑 topic.md：** 第 7.1/7.3 节。

## S26 JEDEC JESD51 系列（摘要）

- **发布者：** JEDEC Solid State Technology Association（JC-15/JC-15.1）
- **URL/版本：**
  - JESD51-1《Integrated Circuit Thermal Measurement Method – Electrical Test Method》, 1995-12：https://www.jedec.org/standards-documents/docs/jesd-51-1
  - JESD51-2A《Integrated Circuits Thermal Test Method Environmental Conditions – Natural Convection (Still Air)》, 2007-01：https://www.jedec.org/standards-documents/docs/jesd-51-2a
  - JESD51-3《Low Effective Thermal Conductivity Test Board for Leaded Surface Mount Packages》, 1996-08，2026-02 重申：https://www.jedec.org/standards-documents/docs/jesd-51-3
  - JESD51-7《High Effective Thermal Conductivity Test Board for Leaded Surface Mount Packages》, 1999-02，2026-02 重申：https://www.jedec.org/standards-documents/docs/jesd-51-7
  - JESD51-14《Transient Dual Interface Test Method for the Measurement of the Thermal Resistance Junction-to-Case…》, 2010-11：https://www.jedec.org/standards-documents/docs/jesd51-14-0/
- **实际查阅范围：** 仅官方页面摘要；全文需 JEDEC 账号/登录，未读正文。
- **关键内容（转述）：**
  - JESD51-1 定义单器件电学热测试方法（ETM），用于同封装/不同封装器件的热特性比较。
  - JESD51-2A 规定自然对流（静止空气）下 θJA 测量的环境条件，以保证准确性与可重复性；测试板由 JESD51-3/-7 等另行规定。
  - JESD51-3 定义单层、引线式表面贴装封装的热测试板（low effective thermal conductivity）。
  - JESD51-7 定义高有效导热率测试板，目标是不同实验室间典型差异 ≤10%。
  - JESD51-14 定义 Transient Dual Interface Measurement（TDIM），用于单一热流路径器件的 RθJC。
- **适用条件：** 理解 RθJA/RθJC 测试标准的范围；不能从摘要推断具体试验箱尺寸、风速、板朝向、稳态判据。
- **不能推广的部分：** 摘要不是正文；本专题不引用摘要里没有的数值/条款。
- **支撑 topic.md：** 第 2.1 节、第 8.4 节。

## S27 Infineon AN2015-10：Transient Thermal Measurements and Thermal Equivalent Circuit Models

- **发布者：** Infineon Technologies AG
- **URL：** https://www.infineon.com/dgdl/Infineon-Thermal_equivalent_circuit_models-ApplicationNotes-v01_02-EN.pdf?fileId=db3a30431a5c32f2011aa65358394dd2
- **版本/日期：** V1.2，2020-04-14（Rev 1.0 2015-12-08；Rev 1.1 2018-10-16）；11 页；替代 AN2008-03。
- **实际查阅范围：** 第 1–11 页。
- **关键内容（转述）：**
  - Rth 取 t=0 时两点温差除以 PL；Zth 取降温曲线镜像/平移后各时刻温差除以 PL（第 3 页）。
  - 结温由小测量电流下的饱和/正向压降反推，需先标定 Tj=f(VCE/VF @ Iref)（第 3–4 页）。
  - Cauer（连分式/T 型）反映物理层叠，节点可访问各层温度；但热扩散建模困难（第 6 页）。
  - Foster（部分分式/Pi）RC 不再对应层序，节点无物理意义；因可从实测曲线提取且便于解析计算，数据手册采用（第 6 页）。
  - Foster→Cauer 变换不唯一，变换后元件/节点失去物理意义（第 8–9 页）。
  - 数据手册 Foster 模型在特定散热器条件下测得；风冷/水冷会影响模块内部热扩散；无法把模块模型和散热器模型无误差串联；精确系统模型需实测整条路径 Zth(j-a)（第 9 页）。
  - 散热器时间常数（风冷约 10 s 到数百 s）远大于 IGBT 本身（约 1 s）；水冷/极快水冷需实测整体 Zth（第 9 页）。
- **适用条件：** IGBT 模块的热模型语义；方法可借鉴，时间常数/量级不能移植到 SMD MOSFET。
- **不能推广的部分：** 文档对象是 IGBT 模块，不是 PCB 板级；不含具体器件 Zth 系数/数值算例；V1.2 与任务书写的 2018-10-16（Rev 1.1）不同，引用需写版本。
- **支撑 topic.md：** 第 5.4 节（模型语义/串联限制）。

## 未取得/未使用

- **IPC-2152 / IPC-2221**：付费标准，未取得正文；本专题不引用其具体曲线/数值。Vishay 34256 只评价了 NBS/MIL-STD-275/IPC-2221，且早于 IPC-2152，不能替 IPC-2152。
- **JEDEC 全文**：仅官方摘要；不要把摘要转述当标准条款。
- **具体器件 datasheet**：本专题不绑定某一型号；实际设计必须查所选器件的当前 datasheet/勘误。
- **TI SLVAE85 中“20 millimeter / 10-mm”热过孔文字**：与常见 mil 单位不符，疑为笔误/提取错误；本专题不引用该尺寸。
- **TI SNVA753 Table 2 的“measured temperature”**：确认为壳顶温度，不是 Tj；本专题只用其封装比较趋势，不把它当 Tj。
- **Cree/OSRAM/Vishay 的具体图表**：只转述数值/趋势，不复制图表；需要原图时查原 PDF。

## 许可与再分发

- 以上来源均为原厂公开技术文档；本专题只做转述、短引用和页码定位，**不复制图表、不打包 PDF、不再分发全文**。
- 仓库的 MIT 许可适用于本专题原创的文字、SVG 和一阶计算脚本；不覆盖第三方文档/商标。
- 引用厂商文档时保留厂商名、文档号、版本/日期和 URL；不要把厂商的应用笔记内容改写成“本仓库的保证”。
- TI、ADI、Infineon、ST、Nexperia、Cree、ams-OSRAM、Vishay、nVent、FLIR、Advanced Energy、JEDEC 的文档均受各自版权/使用条款约束；本专题不声称获得再分发许可。
