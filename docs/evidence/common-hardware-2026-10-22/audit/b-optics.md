# B 光、接近、距离与人体检测 盘点

> 审计对象：`C:\Users\jlc\work\EasyCirq`（HEAD `0fe5cf8`）。
> 方法：按 `SKILL.md` 按需读取表定位，再用 Grep 抽查 `design-cards/`、`selection/`、`engineering-deepdives/`、`pcb-placement-details.md`、`domain-design-details.md`、`enclosure-integration.md` 等；只读相关段落，未全量加载大文件。
> 判定口径：只针对本组 8 个主题的“11 问 + 来源”是否够用，不代表仓库其他领域质量。行号为当前工作区 1 起始行号；路径相对仓库根。
> 结论先行：**B 组是明显的空白组。** 60 张设计卡中没有任何光学/接近/测距/人体检测卡；现有内容只有通用模拟采集链（ANA-01/02/04）、运放高源阻抗的一行提示（C3）、选型表里一行“磁/光/proximity”，以及 Feather Sense 案例中 APDS-9960 的 BOM/网表观察。B1/B2 可“复用+补”，B3–B8 需要新写。

---

## B1 环境光检测

**现有内容**
- `design-hardware/references/design-cards/analog/a01-divider.md` L11–271（整卡）：电阻分压采样的拓扑、参数步骤、误差预算与算例；LDR 分压可直接借用其“分压比 → 源阻抗 → 采集时间 → 误差预算”的顺序，但它假设源是电压源、阻值公差已知。
- `design-hardware/references/design-cards/analog/a02-opamp-buffer.md` §3–§5（L74–265）：需要高阻缓冲时的运放选择、噪声/带宽/稳定性。
- `design-hardware/references/design-cards/analog/a04-adc-driver.md` §3–§5（L77–248）：ADC 建立时间、RC 驱动、基准脚。
- `design-hardware/references/calculations/analog-adc.md` §3.3（L95–108）、§5.3（L270–305）：运放增益/带宽/噪声/容性负载；可用于 ALS 模拟前端或 LDR 缓冲。
- `design-hardware/references/selection/modules-connectors.md` §5 L153–169（关键行 L162）：一行“磁/光/proximity | 感应距离、目标材料、污染、环境光 | 只看检测距离 | 现场条件留裕量”。
- `design-hardware/references/schematic-details.md` L48–52（SC33/SC34/SC37）：运放真实范围、ADC 驱动、输入异常；可作检查项。
- `design-hardware/references/pcb-placement-details.md` L13（PL07）、L33（PL21）、L36（PL24）：传感器孔/模拟链/环境传感器位置；没有光窗/遮光的具体判据。

**判定：partial**

**已覆盖：** 只有通用“分压/缓冲/ADC”采集链和一行传感器选型判据；没有任何照度（lux）、LDR、光电二极管或数字 ALS 的具体内容，也没有人眼匹配/红外抑制/窗口污染的设计判据。

**缺口（对照 11 问）**
- 用户话术：缺“天黑了开灯 / 屏幕自动调亮 / 记录光照度 / 检测是否被遮挡 / 太阳能板朝向”的生活化分流；未区分“相对明暗阈值”与“绝对 lux 测量”。
- 路线选择：缺 LDR 分压（便宜、慢、离散大）→ 光电二极管+跨阻（线性好、需前端）→ 数字 ALS（BH1750/OPT3001/VEML7700，出厂校准、I²C）→ 光敏三极管/光伏模式的判据与代价。
- 必查参数：缺量程（lux）、分辨率、暗电流/暗阻、温度系数、视角、红外抑制/人眼匹配（CIE photopic）、长期老化/窗口污染、响应时间、供电/接口。
- 电路组成：缺 LDR 分压+RC 的具体拓扑、数字 ALS 的去耦/上拉/INT/ADDR 接法；未说明模块自带稳压/电平转换时不能重复添加。
- 参数确定：缺 LDR 的 R_top 选择（亮/暗阻、ADC 量程、自热）、lux 与 ADC 码的换算/标定、对数或分段线性化、采样平均时间。
- 原理图：缺数字 ALS 的逐脚（VDD/GND/SDA/SCL/ADDR/INT）、LDR 极性/封装、模拟输出的缓冲/保护。
- PCB：缺光窗开孔/透光材料、遮光墙、发射-接收隔离（若带 IR）、窗口与传感器间距、表面污染/凝露。
- 程序：缺 ALS 初始化、量程/积分时间切换、中断阈值与迟滞、lux 计算、去抖/平均、低功耗周期采样。
- 验证：缺照度计对比、暗箱/日光/白炽/LED 频闪、不同色温、温度/老化、窗口污染后的复测。
- 常见误判：缺“读数正常但人眼感觉不对”（硅响应不等于人眼）、“白天饱和/夜晚分辨率不足”、“窗口黄变/污染当传感器坏”、“PWM 光源频闪被当成随机噪声”。
- 采购：缺关键词/封装/模块 vs 芯片、量程与接口核对、C 号核对流程。

**动作：supplement**（复用 ANA-01/ANA-02/ANA-04 + C1 误差链；只补“环境光”这一层的路线、光学窗口、lux 标定与数字 ALS 接法）

**候选型号**
- 首选 BH1750FVI（Rohm，I²C 16-bit ALS，1–65535 lx 量级；供电/量程/封装按手册核对，模块极常见）
- OPT3001（TI，I²C ALS，0.01–83k lx 量级，原厂手册与应用笔记完整）
- VEML7700（Vishay，I²C，高动态范围，原厂手册完整）
- GL5528（通用 LDR，便宜、无原厂数据手册；只能作 E3 候选，亮/暗阻与批次差异必须实拍标定）

**备注：** `a01-divider.md` §4.5 的误差预算按“已知阻值公差”的电压源分压计算；LDR 的亮/暗阻可跨几个数量级，且批次/温度/老化漂移大，不能直接套该预算。`selection/modules-connectors.md` L162 把光敏/接近/磁合并成一行，写作时必须拆开并回链 B1/B3/B4。

---

## B2 光电二极管前端

**现有内容**
- `design-hardware/references/engineering-deepdives/topics/c3-opamp-hidden-conditions.md` L44（表行）、§2.5 L153–166、§6.4 L354–372：把光电二极管列为“源阻抗 >100 kΩ”场景，提醒查 Ib/Ios、输入电容与低频噪声；只有一行/一段，不是前端设计。
- `design-hardware/references/design-cards/analog/a02-opamp-buffer.md` §3–§5（L74–265）：同相放大/缓冲、噪声增益、闭环带宽、容性负载稳定性；不含跨阻（TIA）拓扑。
- `design-hardware/references/design-cards/analog/a04-adc-driver.md` §3–§5（L77–248）：ADC 驱动/建立；TIA 输出到 ADC 时复用。
- `design-hardware/references/design-cards/analog/a05-vref.md`（整卡）：若用单电源偏置/基准，复用其基准误差与回流要求。
- `design-hardware/references/calculations/analog-adc.md` §3.3（L95–108）、§5.3（L270–305）：运放增益/带宽/噪声/稳定性；TIA 的环路稳定性需另加 Cd/Cf 分析。
- `design-hardware/references/engineering-deepdives/topics/c1-sensor-to-adc-error-chain.md`（整篇）：直流误差分类/合成/校准；可作 TIA 后级误差链。
- `design-hardware/references/pcb-placement-details.md` L33（PL21）：模拟信号链顺序；没有高阻节点漏电/guard 的具体条目。

**判定：partial**

**已覆盖：** 有运放误差/稳定性/ADC 驱动的通用方法，并在 C3 中明确提到光电二极管属于高源阻抗场景需要查 Ib/Ios；没有跨阻拓扑、结电容、反馈电容、光电流标定或光学窗口的任何内容。

**缺口（对照 11 问）**
- 用户话术：缺“测光/测激光/测浊度/红外接收/心跳/颜色”的入口；未区分光伏模式（零偏、低暗电流、低噪声）与光导模式（反偏、高速、高暗电流），也未问波长/光功率/带宽。
- 路线选择：缺 光伏 vs 光导 vs 集成 TIA/数字光传感器 的判据；缺“电阻负载取电压”与“跨阻取电流”的取舍；缺单端/差分、AC 耦合/调制解调的选择。
- 必查参数：缺响应度（A/W）、暗电流、结电容 Cd、shunt resistance、波长范围/峰值、有效面积、NEP/噪声、线性上限、温度系数、视角/滤光片。
- 电路组成：缺 TIA 拓扑（运放 + 反馈 Rf/Cf + 偏置/虚拟地 + 输出 RC）、光导偏置/AC 耦合、输入保护/限流。
- 参数确定：缺 `Vout = Iph × Rf`、`Cf` 与 `Cd`/GBW 的相位裕度、`f_p = 1/(2πRfCf)`、带宽/噪声/暗电流的权衡、单电源偏置与输出摆幅。
- 原理图：缺阳极/阴极/偏置/反馈/guard 的逐脚画法；缺光电二极管符号、极性、屏蔽/guard ring。
- PCB：缺高阻节点漏电/污染/助焊剂残留、guard ring/保护环、光电二极管下方开窗/遮光、TIA 输入走线最短、反馈电阻附近清洁度。
- 程序：缺 ADC 采样/平均、暗电流扣除、调制解调（lock-in）/带通、过曝/饱和检测。
- 验证：缺暗电流、响应度、线性、带宽、温度、长期漂移测试；缺已知光源/功率计的标定。
- 常见误判：缺“GBW 够但 TIA 振荡”（Cd 引起）、“暗电流当信号”、“反馈电阻漏电/污染”、“用电压反馈运放忽略输入电容”、“单电源下光电流方向接反”。
- 采购：缺光电二极管型号/封装/窗口/滤光片、运放 Ib/GBW/噪声的配对选择。

**动作：supplement**（复用 C3/ANA-02/ANA-04/ANA-05 与 C1；新增 TIA 拓扑、Cd/Cf 稳定性、guard/漏电与光电流标定）

**候选型号**
- 首选 BPW34（ams-OSRAM，硅 PIN 光电二极管，可见–近红外，通孔/贴片版本按后缀核对；原厂手册完整、常见）
- TEMD6200FX01（Vishay，贴片环境光光电二极管，人眼响应滤光；原厂手册完整）
- Hamamatsu S1223-01（高灵敏度 Si PIN，原厂资料完整但采购渠道较窄）
- OPA320 / OPA333（TI，TIA 运放候选：OPA320 带宽高、OPA333 零漂移低 Ib；具体 Ib/GBW/噪声按手册核对）

**备注：** `c3-opamp-hidden-conditions.md` L44/§2.5 的“源阻抗 >100 kΩ → 查 Ib/Ios”是电压源判据；TIA 的反相输入是虚地，直流误差主要是 `Ib × Rf`（及 `Ios × Rf`），稳定性由光电二极管结电容 Cd 与反馈电容 Cf/GBW 决定。写 B2 时必须明确这一区分，不能照抄 C3 的结论。

---

## B3 反射式光电检测

**现有内容**
- `design-hardware/references/selection/modules-connectors.md` §5 L162：仅一行“磁/光/proximity”选型判据（感应距离、目标材料、污染、环境光）。
- `design-hardware/references/design-cards/drive/d01-low-side.md` §3–§5（L72–179）：低侧开关，可用于 IR 发射管的通断/调制驱动。
- `design-hardware/references/design-cards/drive/d07-led-cc.md` §3–§5（L76–181）：连续 LED 恒流/限流；不是脉冲 IR 驱动卡，PWM 延迟与峰值电流另有条件。
- `design-hardware/references/design-cards/analog/a04-adc-driver.md` §3–§5（L77–248）：若接收侧用 ADC 读光电流/电压，复用其建立与驱动。
- `design-hardware/references/pcb-placement-details.md` L13（PL07）、L33（PL21）：传感器开孔与模拟链位置；没有发射-接收遮光/串扰条目。

**判定：missing**

**已覆盖：** 只有通用 LED/低侧开关驱动和一行选型判据；没有反射式光电的发射-接收配对、调制、串扰、阈值或目标反射率设计。

**缺口（对照 11 问）**
- 用户话术：缺“手靠近就亮 / 检测黑色物体 / 计数 / 避障 / 液位 / 纸张有无”的入口；未区分反射式、对射式、槽型，也未问目标颜色/表面/距离/环境光/污染。
- 路线选择：缺 反射式光电（TCRT5000/GP2S700/QRE1113）vs 对射/槽型 vs ToF/超声 的判据；缺直流驱动 vs 调制+同步解调的取舍；缺模拟阈值 vs ADC/比较器的选择。
- 必查参数：缺发射波长/正向电流/峰值电流、接收光电流/暗电流、CTR（电流传输比）、检测距离、目标反射率、环境光抑制、发射-接收串扰、响应时间。
- 电路组成：缺 “IR LED + 限流/驱动 + 光电晶体管 + 上拉/比较器/ADC” 的完整拓扑；缺调制驱动/同步解调、环境光抵消。
- 参数确定：缺 R_LED（Vf/I）、接收侧 R_C/阈值、对比度/SNR、调制频率/占空比、峰值电流与平均电流的热换算。
- 原理图：缺 LED A/K、光电晶体管 C/E 的逐脚；缺比较器迟滞、输出上拉/开集。
- PCB：缺发射-接收遮光墙/开槽、窗口/污染、串扰布局、透镜/孔径；缺发射管与接收管的光学轴线。
- 程序：缺 38 kHz 调制/同步采样、自适应阈值、去抖/计数、环境光基线跟踪、LED 老化补偿。
- 验证：缺不同颜色/距离/环境光/污染条件下的对比测试；缺 LED 光衰/接收管饱和/长期稳定性。
- 常见误判：缺“黑色物体检测不到是反射率低，不是传感器坏”、“太阳光/环境光导致误触发”、“发射管老化后距离下降”、“接收管饱和/上拉不当”、“直流驱动被环境光淹没”。
- 采购：缺型号/封装/配对管/窗口/透镜、模块 vs 分立器件。

**动作：new**（发射驱动可引用 DRV-01/DRV-07，接收可引用 ANA-04；本主题补反射式特有的光学、调制与阈值）

**候选型号**
- 首选 TCRT5000（Vishay，反射式光电传感器，红外发射+光电晶体管，通孔；原厂手册完整、极常见）
- GP2S700HCP（Sharp，贴片反射式光电传感器，原厂手册完整）
- QRE1113（onsemi，贴片反射式物体传感器，常用于循迹/计数）
- 备选 Kingbright KTIR0711S（反射式，具体封装/距离按手册核对）

**备注：** `d07-led-cc.md` 是连续恒流/照明取向，正文明确不覆盖高频 PWM 的延迟/压摆；脉冲 IR 发射需另算峰值电流、占空比、结温与平均电流，不能直接套 d07 的连续电流算例。

---

## B4 对射与槽型检测

**现有内容**
- `design-hardware/references/selection/modules-connectors.md` §5 L162：仅一行“磁/光/proximity”选型判据。
- `design-hardware/references/design-cards/drive/d01-low-side.md` §3–§5（L72–179）：可用于发射管驱动。
- `design-hardware/references/design-cards/drive/d07-led-cc.md` §3–§5（L76–181）：连续 LED 驱动，不是脉冲/高速光断续器驱动。
- `design-hardware/references/design-cards/mcu/m01-bare-mcu.md`、`m04-boot-strap.md`（整卡）：GPIO/定时器/中断资源与启动脚复用；接收输出接 MCU 时复用。
- `design-hardware/references/module-integration.md` §5（L156–185）：上电/复位/休眠/掉电状态表；光断续器输出在复位态的电平要进表。

**判定：missing**

**已覆盖：** 仅有一行“光/proximity”选型判据；没有对射/槽型的槽宽、孔径、遮光片、响应时间、输出整形或计数程序。

**缺口（对照 11 问）**
- 用户话术：缺“门开关 / 限位 / 计数 / 断料 / 转速 / 电梯平层”的入口；未区分对射（分离发射/接收）与槽型（U 型一体），也未问物体尺寸/速度/间隙/污染。
- 路线选择：缺 槽型光电 vs 对射 vs 机械微动 vs 霍尔 vs 反射式 的判据；缺遮光片/孔径/透镜的选择；缺开集输出 vs 推挽输出的接口选择。
- 必查参数：缺槽宽/缝隙、孔径、发射波长、接收光电流、CTR、响应时间/上升下降、暗电流、环境光、安装公差、重复精度。
- 电路组成：缺 发射限流 + 接收上拉/比较器 + 输出整形（施密特/迟滞）的拓扑；缺开集/推挽、常开/常闭、NPN/PNP 输出选择。
- 参数确定：缺 R_LED、R_C、阈值/迟滞、响应时间与计数频率的关系、遮光片最小宽度。
- 原理图：缺逐脚/极性、输出上拉/滤波、反相/同相逻辑；缺与 MCU 电平的匹配。
- PCB：缺槽型器件跨板/开槽、发射-接收对准、遮光结构、连接器/线束；缺灰尘/油污的可维护性。
- 程序：缺边沿计数/去抖/转速计算/中断、方向判断（双通道）、断料/堵转检测。
- 验证：缺遮光片厚度/间隙/污染/温度测试；缺最小可检测物、最高计数频率、输出波形。
- 常见误判：缺“开集输出没上拉”、“遮光片太薄/太厚/半透明”、“灰尘/油污导致误判”、“对射距离与透镜/孔径有关”、“槽型装反/发射接收错位”。
- 采购：缺槽宽/缝隙/封装/连接器、模块 vs 分立、防护等级。

**动作：new**（发射驱动可引用 DRV-01/DRV-07；MCU 侧引用 M01/M04；本主题补槽型/对射的机械、光学与计数）

**候选型号**
- 首选 TCST1103（Vishay，透射式光传感器，槽型，光电晶体管输出；原厂手册完整、常见）
- Omron EE-SX1041（光电微传感器，5 mm 槽型，3D 打印机限位常用）
- Sharp GP1S094HCZ0F（贴片光断续器，紧凑槽型）
- Everlight ITR9608（DIP 槽型光断续器，常见、便宜；具体槽宽/电流按手册核对）

**备注：** 无专属现有内容；与 B3 共用发射驱动/接收整形，但槽型/对射的机械对准、遮光片和响应时间是独立判据，不能合并成一节。

---

## B5 PIR 人体检测

**现有内容**
- `design-hardware/references/pcb-placement-details.md` L13（PL07 人机位置：传感器孔/外壳开口）、L36（PL24 环境传感器：气孔/气流/热传导/凝露）；都是通用条目，不是 PIR。
- `design-hardware/references/enclosure-integration.md` L13：天线/传感器行提到“气路/声孔/光窗”；可作 PIR 菲涅尔窗口的入口，但没有透红外材料/透镜固定判据。
- `design-hardware/references/domain-design-details.md` L45（DM24）：温湿度/气压/气体/光学/惯性传感器“按物理测量条件布置”；只有一句。
- `design-hardware/references/manufacturing-details.md` L25（MF14）、L27（MF16）：涂层/清洗避开传感器孔；可扩展到菲涅尔窗口。
- `design-hardware/references/design-cards/power/p01-ldo.md`（整卡）：PIR 模块/芯片的 3.3 V 供电与静态电流；复用。
- `design-hardware/references/design-cards/mcu/m02-module-mcu.md`（整卡）：MCU 唤醒/低功耗；PIR 输出作唤醒源时复用。

**判定：missing**

**已覆盖：** 只有通用的传感器开孔/外壳窗口/远离热源检查；没有 PIR 的热释电原理、菲涅尔透镜、运动检测、延时/重触发或误报判据。

**缺口（对照 11 问）**
- 用户话术：缺“有人经过就亮 / 人在房间保持 / 电池供电多年 / 防盗报警”的入口；未区分运动检测（PIR）与存在检测（mmWave），也未问覆盖范围/安装高度/延时/光照联动。
- 路线选择：缺 裸热释电+菲涅尔+运放/比较器 vs 集成 PIR 模块（HC-SR501/AM312）vs Panasonic PaPIRs vs mmWave 的判据；缺电池 vs 常电、模拟 vs 数字输出。
- 必查参数：缺探测距离/视场角（FOV）、光谱 8–14 µm、供电/电流、输出类型/极性、延时/重触发、预热时间、工作温度、菲涅尔透镜焦距/覆盖。
- 电路组成：缺 热释电传感器（双元/三元）+ 前置放大/比较器 + 菲涅尔 + 稳压/去耦；模块版缺外围与去重说明。
- 参数确定：缺前置增益/带宽（约 0.1–10 Hz）、阈值/延时、电源噪声、透镜与探测距离的关系。
- 原理图：缺 VDD/GND/OUT/REL 逐脚、上拉/开集、模拟输出的偏置/滤波。
- PCB：缺传感器开窗/菲涅尔固定/远离热源/避免气流直吹/遮光；缺与无线天线的位置关系。
- 程序：缺中断/去抖/延时/重触发/光照门控/低功耗唤醒、误报过滤。
- 验证：缺人体移动/静止/环境温度接近体温/阳光/空调/热源/宠物 的误触发与漏检测试；缺预热时间与覆盖角实测。
- 常见误判：缺“PIR 只测运动，人静止会漏”（需要 mmWave 或保持逻辑）、“热源/空调/阳光误触发”、“透镜装反/被遮挡”、“预热时间不够”、“灵敏度调太高导致误报”。
- 采购：缺模块 vs 裸传感器/透镜、探测距离/FOV/供电/输出类型、C 号核对。

**动作：new**（供电复用 PWR-01，唤醒复用 MCU-02，外壳窗口复用 enclosure-integration；本主题补 PIR 特有的光学、前端与误报）

**候选型号**
- 首选 EKMC1601111（Panasonic PaPIRs，3.3 V 数字输出，低电流；具体后缀/透镜/电流按手册核对，原厂资料完整）
- EKMB1201111（Panasonic PaPIRs，1 µA 级电池型；适合低功耗，具体型号按手册核对）
- HC-SR501（模块，BISS0001，4.5–20 V，便宜、极常见；无原厂完整数据手册，只能 E3）
- AM312（微型 PIR 模块，3.3 V 兼容，便宜；模块资料为主）

**备注：** `pcb-placement-details.md` L36（PL24）是“环境传感器”气孔/气流条目；PIR 需要的是红外光窗/菲涅尔且要避免气流直吹，直接套 PL24 会做错。B5 与 B8 都常被用户叫“人体感应”，必须在路线选择里明确 PIR=运动、mmWave=可做静止/存在。

---

## B6 ToF 测距

**现有内容**
- 无 ToF/VL53/激光测距内容。可复用的相邻内容：
  - `design-hardware/references/design-cards/interfaces/i01-i2c.md`（整卡）：I²C 上拉、总线电容、地址、时序。
  - `design-hardware/references/design-cards/interfaces/i12-level-shift.md`（整卡）：2.8 V/3.3 V 电平转换；ToF 模块常见 2.8 V I/O。
  - `design-hardware/references/design-cards/power/p01-ldo.md`、`p02-buck.md`（整卡）：2.8 V/3.3 V 供电与去耦。
  - `design-hardware/references/module-integration.md` §6（L186–215）：地址/片选/复用；多颗 ToF 的 XSHUT 地址分配要进资源表。
  - `design-hardware/references/pcb-placement-details.md` L13/L33/L36：传感器开孔/模拟链/环境传感器；没有光学盖板/串扰条目。
  - `design-hardware/references/enclosure-integration.md` L13：光窗；可作盖板/窗口入口。

**判定：missing**

**已覆盖：** 无。只有 I²C/电平转换/电源/模块地址等通用基础，没有任何 ToF 的路线、量程条件、盖板、校准或眼安全内容。

**缺口（对照 11 问）**
- 用户话术：缺“测距离 / 防撞 / 液位 / 人数统计 / 自动对焦”的入口；未区分单点 ToF、多区/成像 ToF、三角测距，也未问量程/精度/目标反射率/环境光/FOV。
- 路线选择：缺 单点 ToF（VL53L0X/L1X）vs 多区（VL53L5CX）vs 超声（B7）vs 毫米波（B8）vs 三角/激光 的判据；缺盖板/窗口/保护膜的影响。
- 必查参数：缺量程（依赖目标反射率/环境光）、精度/重复性、FoV、波长 940 nm、Class 1 眼安全、供电（2.8 V/3.3 V）、I²C 电平、XSHUT/GPIO、帧率/功耗。
- 电路组成：缺 模块/芯片 + 去耦 + 电平转换 + XSHUT 地址分配 + 窗口/盖板 的拓扑；缺多传感器同步/防串扰。
- 参数确定：缺供电/去耦、I²C 上拉、XSHUT 上拉/下拉、地址分配顺序、timing budget/量程模式、盖板折射/串扰补偿。
- 原理图：缺 AVDD/AVSS/VDD/GND/SDA/SCL/XSHUT/GPIO1 的逐脚；缺 2.8 V LDO/电平转换/上拉归属。
- PCB：缺发射/接收窗口开孔、盖板与传感器间距、串扰/内部反射、遮光、散热；缺盖板材料/镀膜。
- 程序：缺 ST API 初始化/测距/中断、多传感器 XSHUT 顺序、offset/crosstalk/SPAD 校准、量程/时序模式切换。
- 验证：缺不同目标（白/黑/镜面）/距离/环境光/盖板 的误差与重复性；缺 Class 1 眼安全声明核对；缺长期漂移。
- 常见误判：缺“标称 4 m 但黑目标/强光下大幅缩短”、“盖板/保护膜导致串扰/测近”、“I²C 电平不匹配”、“多传感器 XSHUT 顺序错”、“把单点当多区”。
- 采购：缺模块 vs 芯片、盖板/窗口、量程版本、C 号核对。

**动作：new**（I²C/电平/电源复用 IF-01/IF-12/PWR-01；本主题补 ToF 的光学窗口、量程条件、校准与眼安全）

**候选型号**
- 首选 VL53L1X（ST，单点 ToF，约 4 m 级，I²C，940 nm Class 1；原厂手册+API 完整、常见）
- VL53L0X（ST，单点 ToF，约 2 m 级，便宜、模块极常见）
- VL53L5CX（ST，多区 4×4/8×8 ToF，适合人数/区域检测；手册/API 完整）
- TMF8801（ams，单点 ToF，小尺寸、近距离；原厂手册完整）

**备注：** 无专属现有内容；ToF 常被用户说成“激光测距”，但单点/多区、量程条件、盖板/窗口和 Class 1 眼安全都不同，不能与 B7/B8 的量程直接互换。

---

## B7 超声测距

**现有内容**
- 无超声/换能器/回波内容。可复用的相邻内容：
  - `design-hardware/references/design-cards/mcu/m01-bare-mcu.md`（整卡）：定时器/GPIO/中断；回波计时复用。
  - `design-hardware/references/design-cards/interfaces/i12-level-shift.md`（整卡）：5 V ECHO → 3.3 V MCU 的电平转换/分压。
  - `design-hardware/references/design-cards/drive/d01-low-side.md`（整卡）：若用分立换能器驱动，低侧开关可作驱动级参考。
  - `design-hardware/references/design-cards/power/p01-ldo.md`、`p02-buck.md`（整卡）：5 V/3.3 V 供电。
  - `design-hardware/references/enclosure-integration.md` L13：声孔/结构；可作换能器开孔入口。
  - `design-hardware/references/pcb-placement-details.md` L13：传感器孔/外壳开口；没有声学隔离/减振条目。

**判定：missing**

**已覆盖：** 无。只有 MCU 定时器/电平转换/电源/结构开孔等通用基础，没有任何超声换能器、驱动、回波、温度补偿或盲区内容。

**缺口（对照 11 问）**
- 用户话术：缺“测水位 / 避障 / 停车 / 料位 / 人体接近”的入口；未区分空气超声与水声/固体超声，也未问量程/盲区/目标表面/温度/风/泡沫。
- 路线选择：缺 成品模块（HC-SR04/JSN-SR04T/MaxBotix）vs 裸换能器+驱动 的判据；缺防水/长距离/模拟 vs 数字接口的选择。
- 必查参数：缺频率 40 kHz、量程/盲区、波束角、精度、供电、接口（Trig/Echo/UART/I²C/模拟）、温度补偿、防护等级、最小目标尺寸。
- 电路组成：缺 换能器驱动（变压器/半桥/专用 IC）+ 接收放大/比较 + MCU 计时；模块版缺外围与去重。
- 参数确定：缺声速温度补偿 `c ≈ 331 + 0.6T`、往返时间、盲区、脉冲数/驱动电压、接收增益/阈值。
- 原理图：缺 VCC/Trig/Echo/GND 逐脚、5 V→3.3 V 电平转换、去耦；缺换能器极性/匹配。
- PCB：缺换能器开孔/声学隔离/减振、发射-接收串扰、壳体共鸣/密封；缺防水结构。
- 程序：缺触发脉宽、回波计时/超时、温度补偿、滤波/中值、多传感器轮流触发。
- 验证：缺不同目标（软/吸声/倾斜）/距离/温度/风/泡沫 的测试；缺盲区/最小距离/波束角实测。
- 常见误判：缺“ECHO 5 V 直连 3.3 V MCU”、“标称量程对软/吸声目标不成立”、“温度/风影响声速”、“多传感器互相干扰”、“把回波当距离而不除 2”。
- 采购：缺模块/换能器/防水型号、接口/量程/防护等级、C 号核对。

**动作：new**（MCU/电平/电源/结构复用 M01/IF-12/PWR-01/enclosure；本主题补超声换能器、驱动、回波与温度补偿）

**候选型号**
- 首选 MaxBotix MB1240（LV-MaxSonar-EZ4，约 0.2–7.65 m，3.3–5 V，模拟/脉宽/RS232 输出；原厂手册完整、可靠）
- DFRobot A02YYUW（防水超声模块，UART，约 3–450 cm；原厂资料完整，适合液位/户外）
- HC-SR04（模块，5 V，约 2–400 cm，Trig/Echo；极常见但无原厂数据手册，只能 E3）
- Murata MA40S4S（40 kHz 裸换能器，需自建驱动/接收；原厂手册完整，适合讲清原理）

**备注：** 无专属现有内容；HC-SR04 只有卖家页/社区资料，没有原厂数据手册，参数必须标 E3，不能把卖家标称当保证值。MaxBotix 有完整手册，可作 E1 首选。

---

## B8 毫米波存在感知

**现有内容**
- 无毫米波/雷达/存在感知内容。可复用的相邻内容：
  - `design-hardware/references/design-cards/wireless/w01-wifi-ble.md`、`w02-antenna.md`（整卡）：模组供电/天线净空/整机 RF 环境；裸芯片雷达的天线/净空可参考其方法，但不能照搬 2.4 GHz 数值。
  - `design-hardware/references/design-cards/interfaces/i05-uart.md`（整卡）：UART 电平/交叉/波特率；LD2410 等模块常用 UART。
  - `design-hardware/references/design-cards/power/p01-ldo.md`、`p02-buck.md`（整卡）：模块供电/纹波/去耦。
  - `design-hardware/references/module-integration.md` §5（L156–185）、§6（L186–215）：状态表/地址/复用；模块 EN/复位/上报要进表。
  - `design-hardware/references/enclosure-integration.md` L13：天线/传感器净空与外壳；毫米波模块的天线净空/壳体材料要复用。
  - `design-hardware/references/engineering-deepdives/topics/d4-wireless-integration.md`（整篇）：整机 RF 环境/外壳/人体距离；方法可参考，频段/法规需另查。
  - `design-hardware/references/pcb-placement-details.md` L13、L36：传感器开孔/环境传感器；没有雷达天线净空/壳体条目。

**判定：missing**

**已覆盖：** 无。只有 UART/电源/无线天线净空/模块状态等通用基础，没有任何毫米波的频段、调制、探测距离、安装角度、法规或误报内容。

**缺口（对照 11 问）**
- 用户话术：缺“人在就保持 / 呼吸检测 / 跌倒 / 人数统计 / 存在感应灯”的入口；未区分运动、存在、生命体征，也未问安装高度/角度/覆盖/误报容忍/供电。
- 路线选择：缺 24 GHz 模块（LD2410）vs 60 GHz（BGT60LTR11AIP/A121/IWR6843）vs PIR+保持逻辑 的判据；缺频段法规/天线/穿透/成本；缺模块 vs 裸芯片。
- 必查参数：缺频段、调制（CW/FMCW/脉冲）、探测距离/角度、功耗、接口（UART/SPI/GPIO）、供电、认证/法规、天线形式/净空。
- 电路组成：缺 模块 + 稳压/滤波 + UART 电平 + 使能/复位 的拓扑；裸芯片需 RF 前端/天线/晶振，超出本组。
- 参数确定：缺供电纹波/去耦、UART 电平、天线净空、安装角度/高度、检测门限/灵敏度、上报周期。
- 原理图：缺 VCC/GND/TX/RX/EN/GPIO 逐脚、电平转换/上拉；缺模块与 MCU 的 UART 交叉。
- PCB：缺天线净空/壳体材料/金属遮挡、电源噪声/晶振干扰、模块下方地/开窗；缺与 Wi-Fi/蓝牙天线的共存。
- 程序：缺协议解析/存在/运动/距离门限/上报周期/低功耗、误报过滤、固件升级。
- 验证：缺静止/微动/呼吸/多人/不同姿态/窗帘/风扇/金属反射 的误报与漏检测试；缺法规/射频功率/认证核对。
- 常见误判：缺“毫米波能测静止但会被风扇/窗帘/金属反射干扰”、“24/60 GHz 法规/穿透不同”、“模块天线被金属/水汽遮挡”、“把 motion 当 presence”、“把模块标称距离当全场景保证”。
- 采购：缺模块/频段/认证/天线、C 号核对；缺“模块有售 ≠ 目标市场允许”。

**动作：new**（UART/电源/天线净空/整机 RF 复用 IF-05/PWR-01/RF-01/02/D4；本主题只写模块路线与安装/验证，裸芯片 RF 另请评审）

**候选型号**
- 首选 LD2410C（Hi-Link，24 GHz 人体存在雷达模块，UART，极常见、便宜；模块资料为主，关键结论按模块手册/实测）
- BGT60LTR11AIP（Infineon，60 GHz 自主雷达，集成天线，原厂手册/应用笔记完整；适合要求原厂资料的路线）
- IWR6843（TI，60–64 GHz mmWave，适合多区/人数/高级算法；需 RF 设计/评估板）
- A121（Acconeer，60 GHz 脉冲相干雷达，低功耗；原厂资料完整）

**备注：** 无专属现有内容；毫米波属于 RF 设计，本组只能覆盖模块选型/接口/安装/验证，裸芯片天线与法规认证必须另请 RF 评审。B8 与 B5 的“人体感应”话术重叠，必须在组头做 PIR vs mmWave 对照表。

---

## 复用关系

- **B1** → ANA-01（LDR 分压）、ANA-02（缓冲）、ANA-04（ADC 驱动）、C1 误差链、`calculations/analog-adc.md` §3.3/§5.3、SC33/SC34/SC37、PL21；数字 ALS 另用 IF-01（I²C 上拉/地址/总线电容）。
- **B2** → C3 §2.5/§6.4（Ib/Ios）、ANA-02（运放）、ANA-04（ADC 驱动）、ANA-05（基准/偏置）、C1（误差链）、`calculations/analog-adc.md` §3.3/§5.3；高阻漏电/guard 另用 DM23、PL21。
- **B3** → DRV-01（发射管低侧驱动）、DRV-07（连续 LED 恒流，仅作对照）、ANA-04（接收 ADC）、C1、SC21/SC37、PL07/PL21；接收比较器/迟滞参考 ANA-02。
- **B4** → DRV-01（发射驱动）、DRV-07（连续 LED，仅作对照）、MCU-01/MCU-04（定时器/GPIO/启动脚）、`module-integration.md` §5（复位/休眠状态）、PL07。
- **B5** → PWR-01（3.3 V 供电/静态电流）、MCU-02（唤醒/低功耗）、DRV-01（若驱动继电器/负载）、`module-integration.md` §5、`enclosure-integration.md`（菲涅尔光窗）、PL07/PL24、MF14/MF16。
- **B6** → IF-01（I²C）、IF-12（2.8 V/3.3 V 电平）、PWR-01/PWR-02（2.8 V/3.3 V）、MCU-01/02、`module-integration.md` §6（地址/XSHUT）、PL21/PL24、SC27/SC34。
- **B7** → IF-12（5 V ECHO→3.3 V）、MCU-01（定时器/中断）、DRV-01（分立换能器驱动参考）、PWR-01/PWR-02、`enclosure-integration.md`（声孔/结构）、PL07。
- **B8** → RF-01/RF-02（模组/天线净空）、IF-05（UART）、PWR-01/PWR-02（供电/纹波）、`module-integration.md` §5/§6、`enclosure-integration.md`（天线净空/壳体）、D4 专题（整机 RF）、PL26/PL27。
- **跨组**：B1/B2 属于“模拟采集/精密前端”组，与称重/桥式（ANA-09/ANA-04）、RTD/热敏（ANA-10）共享误差链与 ADC 驱动，但源特性不同（光电流源 vs 电阻桥/电压源），不能互套。B3/B4 与“LED/驱动”组共享 DRV-01/DRV-07，但脉冲 IR 的峰值电流/占空比/热是新增条件。B6/B7/B8 与“无线/RF”“MCU/接口”组共享 UART/天线净空/整机 RF；B6/B7/B8 之间应共用一张“距离/存在路线选择表”（精度、量程、目标、环境光/风/遮挡、成本）。

## 需要同步修正

1. `design-hardware/references/engineering-deepdives/topics/c3-opamp-hidden-conditions.md` L44、§2.5 L153–166：把光电二极管与 pH/高阻分压一起归入“源阻抗 >100 kΩ → 查 Ib/Ios”的电压源判据。跨阻接法反相输入是虚地，直流误差主要是 `Ib × Rf`，稳定性由光电二极管结电容 Cd 与反馈电容 Cf/GBW 决定。建议在 B2 明确区分，并在 c3 该行加“跨阻接法不适用本条”的注。
2. `design-hardware/references/selection/modules-connectors.md` L162：一行“磁/光/proximity”把环境光、反射式、对射/槽型、磁接近混在一起，判据只有“感应距离/目标材料/污染/环境光”。建议拆成环境光、反射式、对射/槽型三行，并补发射管老化、接收饱和、串扰、窗口污染。
3. `design-hardware/references/selection/modules-connectors.md` L182–196：立创商城检索关键词表只有 BME280 一个传感器例子，没有 BH1750/OPT3001、TCRT5000、TCST1103、HC-SR501、VL53L1X、HC-SR04、LD2410 等常用光学/测距关键词。建议补行或统一指向 B 组。
4. `design-hardware/references/pcb-placement-details.md` L36（PL24）：“环境传感器”只写气孔/气流/热传导/凝露，未覆盖光窗、遮光墙、发射-接收串扰、盖板间距、菲涅尔透镜；PIR 还应避免气流直吹。建议拆成“温湿压/气体”与“光学/热释电”两条。
5. `design-hardware/references/domain-design-details.md` L45（DM24）：把温湿度/气压/气体/光学/惯性传感器合并为一条“按物理测量条件布置”，对光学窗口/PIR 透镜/ToF 盖板没有可执行判据。建议新增 DM24a（光学窗口/遮光/串扰）或把光学单列。
6. `design-hardware/references/manufacturing-details.md` L25/L27（MF14/MF16）：只写“防护涂层避开传感器孔”，未写光学窗口的透光率/清洁/划伤/镀膜和光学模块的 MSL/回流限制。建议在 B 组采购/制造段落补，并回链 MF14/MF16。
7. `design-hardware/references/engineering-deepdives/topics/b2-sleep-current-budget.md` L125/L186/L467：APDS-9960 被列为常开传感器且 standby `[待核]`；B1/B3 写作时应补该器件的待机/测量条件（按手册），否则这条旧结论会一直悬空。
8. `design-hardware/references/design-cards/README.md` L65 与 `design-hardware/SKILL.md` §3.1：现有计数为 60 张卡、模拟与传感 10 张（ANA-01..10）、12 组范例、33 个故障、35 个场景；B 组新增卡片/主题后这些计数和索引必须同步，否则路由表与实际内容不一致。

## 文件组织建议

**结论：本组用一个组文件，不拆分。** 按 `C:\Users\jlc\work\hds-common-scratch\authoring-guide.md`：每组一个 `design-hardware/references/common-hardware/<group>.md`，由 `scratch/groups/<group>/` 下的分文件拼装。B1–B8 共享“光学窗口/发射-接收/距离路线”的跨主题判据，拆开会产生重复跳转；单文件约 800–950 行，与现有 `module-integration.md`（846 行）相当。

| 建议文件（scratch） | 内容 | 建议行数 |
|---|---|---:|
| `00-intro.md` | `## 0. 本组怎么用`：用户话术 → 先判断“环境光/反射/对射/运动/距离/存在” → 路线表 → 读哪节；附 PIR vs mmWave、反射 vs 对射 vs ToF/超声 两张对照表 | 35–50 |
| `01-b1-ambient-light.md` | B1 环境光检测（复用 ANA-01/02/04，补 lux/窗口/ALS） | 70–90 |
| `02-b2-photodiode-frontend.md` | B2 光电二极管前端（复用 C3/ANA-02/04，新增 TIA/Cd-Cf/guard） | 90–110 |
| `03-b3-reflective.md` | B3 反射式光电（新写，含发射-接收/调制/阈值） | 80–100 |
| `04-b4-through-beam-slot.md` | B4 对射与槽型（新写，含槽宽/遮光片/计数） | 70–90 |
| `05-b5-pir.md` | B5 PIR（新写，含菲涅尔/前端/误报） | 80–100 |
| `06-b6-tof.md` | B6 ToF（新写，含量程条件/盖板/校准/眼安全） | 90–110 |
| `07-b7-ultrasonic.md` | B7 超声（新写，含换能器/驱动/温度补偿） | 80–100 |
| `08-b8-mmwave.md` | B8 毫米波（新写，模块路线/安装/法规边界） | 90–110 |
| `99-sources.md` | `## 本组来源`：CHW-S 编号、文档号/版本、实读章节、支持结论、不能推广部分、URL（建议预留 14–20 条） | 25–40 |
| `99-fixes.md` | `## 需要同步修正`（本文件“需要同步修正”1–8） | 15–25 |

合计约 **800–950 行**。每节严格按 12 个三级标题（用户会怎么说 / 路线选择 / 必查参数 / 电路组成 / 参数与算例 / 原理图与逐脚 / PCB / 程序 / 验证 / 常见误判 / 采购与落地 / 来源与证据），复用型主题也不省略标题，正文用“见 [XXX] §N”压缩。

**拆分条件（仅在触发时）：** 若 B2 或 B6 单节超过 110 行、总文件超过 1100 行，再拆为 `b-optics-light.md`（B1–B4）与 `b-optics-distance.md`（B5–B8）；但两半都会引用光学窗口/发射-接收/距离路线表，拆分会造成重复或跨文件跳转，默认不做。

**来源建议：** 每个主题至少核一颗原厂手册到 E1（B1 BH1750FVI/OPT3001；B2 BPW34+OPA320/OPA333；B3 TCRT5000；B4 TCST1103；B5 EKMC1601111；B6 VL53L1X；B7 MB1240；B8 BGT60LTR11AIP），模块类（HC-SR501/HC-SR04/LD2410）只作 E3/E2，并在 `99-sources.md` 写清“实读章节”和“不能推广的部分”。
