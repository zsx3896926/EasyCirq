# D 力、重量、压力、液位与流量 盘点

> 审计对象：`C:\Users\jlc\work\hardware-design-skill` 的硬件设计知识库。
> 审计范围：D1–D7。只读审计，未修改仓库任何文件。
> 判定口径：`adequate`＝已足够、可直接引用；`partial`＝有基础但缺本主题具体内容；`missing`＝没有。
> 缺口按任务书 11 问标注：用户话术、路线选择、必查参数、电路组成、参数确定、原理图、PCB、程序、验证、常见误判、采购落地。

---

## D1 称重与应变桥

### 现有内容

| 文件 | 行号/章节 | 实际内容 |
|---|---|---|
| `design-hardware/references/design-cards/analog/a09-bridge.md` | 1–248（§1 37–50；§2 52–69；§3 71–83；§4 85–113；§5 115–161；§6–§11 163–238；§12 240–248） | 桥式传感器专用卡：灵敏度/桥阻/激励、四线/六线、比率测量、INA 增益/共模/CMRR、误差预算、算例、逐脚、原理图、PCB、异常、验证、来源 |
| `design-hardware/references/design-cards/analog/a03-diff-amp.md` | 1–346 | 四电阻差分放大、CMRR 与电阻匹配；桥式输出可作为其输入 |
| `design-hardware/references/design-cards/analog/a04-adc-driver.md` | 1–331 | SAR ADC 驱动、源阻抗/采样建立、基准动态负载 |
| `design-hardware/references/design-cards/analog/a05-vref.md` | 1–342 | 电压基准六项误差、比率测量能消掉什么 |
| `design-hardware/references/design-cards/analog/a01-divider.md` | 41、179 | 激励/基准分压与 0–10 V 分压通用算例 |
| `design-hardware/references/engineering-deepdives/topics/c1-sensor-to-adc-error-chain.md` | 1–641（桥式对象见 28 行） | 传感器→激励→放大→RC→ADC→基准的完整误差链、校准边界 |
| `design-hardware/references/design-cards/README.md` | 65–77 | 模拟与传感 10 张卡索引，含 ANA-09 |
| `design-hardware/references/module-cards.md` | 37–41 | “模拟采集与工业传感”组合入口 |
| `design-hardware/references/domain-design-details.md` | 40–45（DM21–DM24） | 传感器/精密仪器易漏项，DM22 明确桥式激励/引线/自热 |
| `design-hardware/references/selection/modules-connectors.md` | 153–171 | 传感器选型表含“桥式”一行：灵敏度/桥阻/励磁/四六线/失调/非线性 |
| `design-hardware/references/failures/f26-motor-start-corrupts-adc.md` | 25–46、107、154 | 同板电机干扰模拟采集的构造案例，涉及压力/力类模拟前端的地回流、耦合、混叠 |

### 判定

`partial`

### 已覆盖

ANA-09 已把桥式传感器从灵敏度/桥阻/激励到 INA 增益、共模/CMRR、四/六线、比率测量、误差预算、PCB 与验证的模拟前端方法写完整；ANA-03/04/05 与 C1 补齐差放、ADC 驱动、基准和误差链。

### 缺口

- `[用户话术]` 没有“电子秤/厨房秤/地磅/料斗秤/几公斤/克”等生活化入口，也没有把“静态称重”和“动态力/振动/疲劳”分开的问法。
- `[路线选择]` 没有 HX711/HX710/ADS1232/NAU7802/CS1237 一体化称重 ADC、INA+SAR/ΔΣ、数字称重模块三条路线的取舍；没有模块 vs 裸芯片、单点式 vs S 型 vs 悬臂梁、四线 vs 六线的选择表。
- `[必查参数]` ANA-09 已有灵敏度/桥阻/激励/零点/非线性/迟滞/蠕变/温漂/引线/INA/ADC；缺额定容量 vs 安全过载/极限过载、偏载、重复性、零点温漂 vs 灵敏度温漂、IP/电缆/线色/屏蔽、校准砝码等级。
- `[电路组成]` ANA-09 给桥+INA+RC+ADC；缺一体化 ADC 的内部 PGA/振荡器/稳压、激励开关、RATE/通道 A/B、连接器入口 ESD/EMI、屏蔽接地、连接器处 Kelvin、比率激励到 VREF。
- `[参数确定]` 缺一体化 ADC 的 PGA×数据率×噪声折中（10/80 SPS）、50/60 Hz 陷波、加载后建立时间、去皮/两点校准、温补；ANA-09 只覆盖 INA 增益/CMRR/引线。
- `[原理图]` ANA-09 §8 有模块化画法和 4/6 线命名；缺称重连接器脚序/线色、屏蔽/屏蔽夹、激励极性、六线 DNP 选项、测试点、护环。
- `[PCB]` ANA-09 §9 有对称/热梯度/回流；缺称重传感器连接器靠板边与应变释放、连接器处 Kelvin、激励走线电阻、热电势对称、高阻输入护环、与秤体机械隔离。
- `[程序]` 全库没有称重固件：HX711 时序/ADS1232 SPI 读、去皮、两点校准、滤波/平均、漂移补偿、过载判定、单位换算。
- `[验证]` ANA-09 §11 有砝码/压力源/桥模拟器/温度；缺重复性、偏载、蠕变/回零、迟滞、长期漂移、IP/凝露、校准证书与不确定度。
- `[常见误判]` 缺“读数漂移=传感器坏”“HX711 10 Hz 够用”“四线当六线”“激励直接用 USB 5 V”“秤盘装配应力当零点”“软件去皮掩盖漂移”“按传感器额定而不是系统过载选量程”。
- `[采购落地]` 缺称重传感器/HX711 模块的检索词、完整 MPN/量程/精度/线色/连接器映射、校准砝码与工装采购。

### 动作

`supplement`：以 ANA-09 为主引用，不重写桥式前端公式；新增“称重产品化”补充卡，覆盖路线、机械/安装、固件校准、验证与采购。

### 候选型号

- `HX711`（模块/低成本路线首选；24-bit，10/80 Hz；需核对 AVDD/内部稳压、RATE、通道 A/B 与外围一致性）
- `ADS1232`（原厂资料完整的设计路线首选；24-bit、PGA 1–128、10/80 SPS）
- `NAU7802`（I2C、24-bit、PGA，适合小板与多传感器）
- `CS1237`（低成本 2 线、国产常见；资料完整度与长期供货需核对）

### 备注

ANA-09 是 E2 卡，明确写明未读 ANA-S09 第 5.2 节以后、未给出 INA 具体选型/噪声/动态桥；新卡不要重复其公式。现有 §5 对“增益 200”的淘汰理由有误，见“需要同步修正”。

---

## D2 模拟压力传感器

### 现有内容

| 文件 | 行号/章节 | 实际内容 |
|---|---|---|
| `design-hardware/references/failures/f26-motor-start-corrupts-adc.md` | 25–46、154 | 构造案例：3.3 V 比率型压力传感器（0.5–2.5 V、假设 40 mV/kPa）与 12 位 ADC 同板，电机启动造成地弹/耦合/混叠 |
| `design-hardware/references/design-cards/analog/a01-divider.md` | 41、179 | 0–10 V/传感器输出分压进 ADC 的通用方法 |
| `design-hardware/references/design-cards/analog/a02-opamp-buffer.md` | 1–342 | 缓冲/同相放大、共模/摆幅/容性负载 |
| `design-hardware/references/design-cards/analog/a04-adc-driver.md` | 1–331 | 源阻抗、采样建立、RC |
| `design-hardware/references/design-cards/analog/a05-vref.md` | 1–342 | 基准误差与比率测量 |
| `design-hardware/references/engineering-deepdives/topics/c1-sensor-to-adc-error-chain.md` | 28、1–641 | 缓变单端/差分信号的误差链，适用于压力传感器 |
| `design-hardware/references/module-cards.md` | 37–41 | 模拟采集组合入口 |
| `design-hardware/references/domain-design-details.md` | 40–45 | DM21/DM24 通用传感器建链与环境布置 |
| `design-hardware/references/selection/modules-connectors.md` | 153–171 | 传感器选型表（无压力行） |

### 判定

`partial`

### 已覆盖

只有通用模拟采集链（分压/缓冲/ADC 驱动/基准/误差链）和 F26 中一个 3.3 V 比率型压力传感器受电机干扰的构造案例；没有压力传感器专用的量程、过压、介质、端口与校准设计卡。

### 缺口

- `[用户话术]` 没有“水压/气压/胎压/血压/液位压力/差压”等问法，也没有先区分表压/绝压/差压/密封压。
- `[路线选择]` 没有比率型模拟输出、4–20 mA 压力变送器、数字 I2C 压力传感器、桥式压力芯体四条路线的取舍；没有模块 vs 裸传感器、带胶/带孔/带螺纹端口的选择。
- `[必查参数]` 缺压力量程（kPa/bar）、proof/burst 压力、综合误差 TEB、零点/满量程校准、温补、介质兼容（空气/水/油）、端口/O 圈、供电比率、输出跨度、响应时间、长期稳定性、IP。
- `[电路组成]` 通用分压/缓冲/ADC 之外，缺“传感器供电与 ADC VREF 同源”的比率接法、24 V 误接保护、RC/EMI 滤波、反接/过压钳位、电缆屏蔽、3 线/4 线定义。
- `[参数确定]` 缺传递函数缩放（如 `Vout = Vs × (0.1P + 0.5)` 一类）、零点/满量程压力校准、比率误差抵消、ADC 分辨率换算到压力分辨率、过压余量。
- `[原理图]` 没有压力端口/通气孔/介质隔离/屏蔽/激励与信号命名的专用画法，也没有入口保护与 DNP 选项。
- `[PCB]` 没有压力端口位置、应力隔离、热梯度、凝露、介质路径、O 圈、安装扭矩的布局要求。
- `[程序]` 没有零点/满量程校准、温补、滤波、单位换算、开路/短路/超量程/burst 判定。
- `[验证]` 没有压力源/校准器、泄漏测试、过压测试、温度循环、介质兼容性测试。
- `[常见误判]` 缺“5 V 传感器输出直连 3.3 V ADC”“表压当绝压”“burst 压力当量程”“忽略端口方向/安装应力”“DMM 平均漏掉脉动”“零点漂移就换传感器”。
- `[采购落地]` 缺压力传感器检索词、端口/螺纹/O 圈套件、校准压力源与工装。

### 动作

`new`：新写模拟压力传感器卡，电学部分引用 ANA-01/02/04/05/C1，压力专用内容独立成卡。

### 候选型号

- `NXP MPXV5010DP`（首选：0–10 kPa 差压、0.2–4.7 V、5 V 供电、双端口，资料完整）
- `NXP MPX5700AP`（0–700 kPa 绝压、0.2–4.7 V，资料完整）
- `NXP MPXV7002DP`（±2 kPa 差压、0.5–4.5 V，常见）
- `Honeywell HSC 系列`（模拟/I2C 可选，量程与封装多，需按后缀核对）

### 备注

F26 是构造案例（B/C 证据），只能说明压力传感器会被电机干扰，不能当压力传感器设计依据；ANA-09 只覆盖桥式压力芯体，不覆盖常见的 3 线比率型压力传感器。

---

## D3 数字压力传感器

### 现有内容

| 文件 | 行号/章节 | 实际内容 |
|---|---|---|
| `design-hardware/references/design-cards/interfaces/i01-i2c.md` | 1–301 | I2C 总线、上拉、总线电容、地址冲突 |
| `design-hardware/references/design-cards/interfaces/i03-spi.md` | 1–241 | SPI 模式/片选/时序 |
| `design-hardware/references/design-cards/interfaces/i12-level-shift.md` | 1–302 | 电平转换选型 |
| `design-hardware/references/examples/x05-i2c.md` | 1–207 | I2C 温湿度传感器接口范例：上拉、总线电容、ESD、地址 strap |
| `design-hardware/references/projects/p01-low-power-wireless-sensor.md` | 37、87、292、302 | I2C 传感器选型/布置/待机电流的项目级示例 |
| `design-hardware/references/selection/modules-connectors.md` | 153–171、182–196 | 环境传感器安装/精度陷阱；商城关键词仅 BME280 |
| `design-hardware/references/design-experience.md` | 44 | G08 Bosch BME280 贴装/清洗/气路处理 |
| `design-hardware/references/engineering-deepdives/topics/d1-interface-combination-constraints.md` | 141、274、277 | BMP280 `CSB/SDO` 接 3.3 V 固定 I2C；BMP388 `CSB`/`SDO` 设计观察（待按型号核对） |
| `design-hardware/references/engineering-deepdives/topics/b2-sleep-current-budget.md` | 125、186、467 | BMP280 等传感器 standby 电流未逐个核对 |
| `design-hardware/references/engineering-deepdives/casebook/low-power-wireless-battery.md` | 22、55、59、135、165 | Crazyflie/Feather 设计中的 BMP388/BMP280 实例、I2C 地址 0x77 |
| `design-hardware/references/domain-design-details.md` | 45（DM24） | 气压/环境传感器按物理测量条件布置 |

### 判定

`partial`

### 已覆盖

I2C/SPI 接口卡、x05 I2C 传感器范例、BMP280/BMP388 的 `CSB/SDO` 接法记录、BME280 安装处理与 standby 电流讨论；没有数字压力传感器的选型、量程、补偿、气路/液体介质与固件设计内容。

### 缺口

- `[用户话术]` 没有“气压/海拔/水深/差压/胎压”等问法，也没有先区分绝压/表压/差压、空气介质/液体介质。
- `[路线选择]` 没有 BMP280/BMP388/MS5837/SDP810 等候选的取舍；没有 I2C vs SPI、通气孔 vs 密封、空气专用 vs 防水/耐压的选择表。
- `[必查参数]` 缺压力量程、绝对精度、相对精度、分辨率、噪声、转换时间/ODR、供电/IO 电平、I2C 地址、介质、通气孔、凝露、长期漂移、回流焊敏感度。
- `[电路组成]` 通用 I2C/SPI 之外，缺去耦、地址 strap、`CSB/SDO` 配置、电平转换、ESD、通气路径、滤波、负载开关/断电重启。
- `[参数确定]` 缺过采样×IIR×转换时间×功耗的折中、FIFO/data-ready、补偿系数、气压→海拔/水压→水深换算。
- `[原理图]` 缺逐脚 strap 表、地址、`CSB/SDO`、通气孔、去耦、测试点的专用表达。
- `[PCB]` 缺通气孔/开窗、禁止涂覆、热隔离、远离热源、凝露、介质接触、机械应力的布局要求。
- `[程序]` 没有 I2C/SPI 初始化与读取序列、补偿算法、过采样配置、data-ready 中断、CRC、传感器卡死检测。
- `[验证]` 没有压力舱/参考气压计、海拔/水柱、温湿度、泄漏/凝露、长期漂移验证。
- `[常见误判]` 缺“BMP280 用于水下”“绝压当水深不扣大气压”“0x76/0x77 地址混淆”“CSB 悬空”“过采样拉满总是更好”“涂覆堵住通气孔”。
- `[采购落地]` 缺数字压力传感器检索词、模块 vs 裸芯片、带通气孔封装、防水膜/保护罩。

### 动作

`new`：新写数字压力传感器卡，接口部分引用 IF-01/IF-03/IF-12 与 x05。

### 候选型号

- `Bosch BMP388`（首选·气压/高度：300–1250 hPa、I2C/SPI、资料完整）
- `TE MS5837-30BA`（首选·液位/水深：0–30 bar、I2C、防水封装，资料完整）
- `Bosch BMP280`（常见、便宜、资料完整；不适合液体/高湿凝露）
- `Sensirion SDP810`（差压/流量：I2C、0–500 Pa 级，资料完整）

### 备注

BMP280/BMP388 只在开源设计观察中出现（`CSB/SDO`、待机电流），未按数据手册逐项核对；BMP280 不适合液体/高湿凝露，水深需 MS5837 类；G08 是 BME280 的贴装/清洗指南，不能当压力传感器通用规范。

---

## D4 液位检测

### 现有内容

> 本主题没有液位专用文件；下表是相邻可复用内容，不能当作已覆盖液位设计。

| 文件 | 行号/章节 | 实际内容 |
|---|---|---|
| `design-hardware/references/domains.md` | 11 | 工业 PLC/传感器/仪表：24 V、4–20 mA/0–10 V、隔离/浪涌 |
| `design-hardware/references/module-cards.md` | 37–41 | 模拟采集与工业传感组合入口 |
| `design-hardware/references/domain-design-details.md` | 40–45 | DM21–DM24 通用传感器/环境布置 |
| `design-hardware/references/enclosure-integration.md` | 25 | 密封、通风、防凝露；电容式土壤探头涂层/腐蚀/校准（不是液位） |
| `design-hardware/references/design-cards/analog/a08-4-20ma.md` | 1–256 | 4–20 mA 两/三/四线、compliance、隔离/保护；可用于投入式液位变送器 |
| `design-hardware/references/design-cards/analog/a01-divider.md` | 41、179 | 0–10 V 液位变送器进 ADC 的通用分压 |
| `design-hardware/references/product-example.md` | 12–25 | 花盆缺水提醒（土壤，不是液位；仅产品级参考） |

### 判定

`missing`

### 已覆盖

只有工业 4–20 mA/0–10 V 与模拟采集的通用入口，以及外壳密封/凝露的通用提醒；没有任何液位检测路线、安装、校准或泵控内容。

### 缺口

- `[用户话术]` 没有“水箱/水塔/污水/油位/料位/满溢/缺水”等问法，也没有先区分点式（有/无）与连续量（多少）。
- `[路线选择]` 没有浮球/干簧、电容、超声、静压/投入式、电导、雷达、光电的路线比较；没有接触 vs 非接触、罐体材质/壁厚、泡沫/蒸汽/凝露的适用性判断。
- `[必查参数]` 缺量程、盲区/死区、分辨率、精度、重复性、响应时间、介质兼容、压力/温度、IP、安装方式、泡沫/凝露/蒸汽、供电与功耗。
- `[电路组成]` 缺浮球开关去抖/上拉、电容式激励、超声 trigger/echo 电平转换、投入式 4–20 mA 的隔离/保护与共用电源。
- `[参数确定]` 缺罐体几何→体积换算、死区、泵控滞回、最低/最高液位、电缆长度、静压量程（液柱高度×密度）。
- `[原理图]` 没有液位传感器接口的专用画法：屏蔽、接地、隔离、泵继电器联锁、故障安全默认态。
- `[PCB]` 没有传感器安装位置、电缆入口、凝露排水、隔离、浪涌保护、泵/继电器噪声的布局要求。
- `[程序]` 没有泵控状态机、滞回、满溢/干转保护、去抖、累计量、现场校准。
- `[验证]` 没有“注水到已知液位”的校准、满溢/干转试验、泡沫/蒸汽试验、长期结垢/腐蚀验证。
- `[常见误判]` 缺“超声在泡沫/蒸汽中可用”“浮球开关不消抖”“电容式不受壁厚影响”“静压测的是液柱不是体积”“泵继电器不加续流”。
- `[采购落地]` 缺液位传感器检索词、浮球/电容/超声模块、投入式变送器、安装法兰/支架。

### 动作

`new`：新写液位检测卡；4–20 mA 电气部分引用 ANA-08，数字压力式水深引用 D3。

### 候选型号

- `JSN-SR04T`（首选·非接触超声：防水探头、20–600 cm、5 V trigger/echo，常见；资料版本需核对）
- `XKC-Y25-V`（非接触电容：5–24 V、NPN/PNP 输出，适合塑料/玻璃罐外贴）
- `不锈钢浮球开关`（机械点式、成本低、可靠性好；需消抖与安装位置）
- `TE MS5837-30BA`（投入式压力/水深，0–30 bar、I2C；与 D3 共用）

### 备注

本主题在库内没有现有内容；`enclosure-integration.md:25` 的密封/凝露条目是通用外壳内容，不是液位设计。超声的死区、泡沫、蒸汽、温度补偿必须写入卡片，不能只写“装一个超声模块”。

---

## D5 土壤与介质湿度

### 现有内容

| 文件 | 行号/章节 | 实际内容 |
|---|---|---|
| `design-hardware/references/product-example.md` | 12–25 | 花盆缺水提醒：探头类型/供电/模拟输出/源阻抗/ADC/校准；拔出探头只测输入异常，不代替真实土壤校准 |
| `design-hardware/references/product-acceptance.md` | 18–22 | 土壤干燥提醒的验收项：识别传感器、实际土壤/条件校准、通知、异常恢复 |
| `design-hardware/references/enclosure-integration.md` | 25 | 电容式土壤探头需验证涂层、吸水、长期腐蚀与土质校准，不能承诺不腐蚀 |
| `design-hardware/references/starter-patterns.md` | 20 | 原型跑通不等于电池续航、土壤检测或密封已验证 |
| `design-hardware/references/project-coherence.md` | 33 | 拔出/开路传感器只测故障/阈值链，不证明真实土壤缺水检测 |
| `design-hardware/references/beginner-journey.md` | 12 | 土壤检测新手话术：先只监测、不自动浇水 |
| `design-hardware/references/task-scenarios.md` | 8（S01） | 花盆缺水手机提醒的场景与禁止宣称 |
| `design-hardware/references/design-cards/analog/a01-divider.md` | 41、179 | 模拟探头输出分压进 ADC 的通用方法 |
| `design-hardware/references/design-cards/analog/a04-adc-driver.md` | 1–331 | 高阻/慢变信号的 ADC 驱动与采样建立 |
| `design-hardware/references/design-cards/analog/a08-4-20ma.md` | 1–256 | 工业 4–20 mA 土壤水分变送器的接收接口 |
| `design-hardware/references/domain-design-details.md` | 45（DM24） | 环境传感器按物理测量条件布置 |

### 判定

`partial`

### 已覆盖

S01 花盆缺水提醒、product-example/product-acceptance、enclosure-integration、project-coherence 给出了土壤探头的产品级注意事项（模拟输出/ADC/校准、涂层/腐蚀、不能拔探头代替真实土壤校准）；但没有电路、探头激励与标定方法。

### 缺口

- `[用户话术]` 没有“花盆/大棚/土壤墒情/灌溉/盐碱/基质”等问法，也没有区分土壤体积含水率、基质湿度、水位/水势。
- `[路线选择]` 没有电阻式、电容式、TDR/FDR、张力计/水势的路线比较；没有接触 vs 非接触、模拟 vs 数字 vs 4–20 mA 的选择表。
- `[必查参数]` 缺体积含水率范围、精度、盐分/EC、温度补偿、探头长度、响应时间、耐腐蚀、IP、电缆、功耗。
- `[电路组成]` 缺电阻式探头的交流激励（避免极化/电解）、电容式振荡/ADC、4–20 mA 变送器、隔离/保护。
- `[参数确定]` 缺实际土壤中的干/湿两点或多点标定、土质专用系数、温度/盐分修正、阈值/滞回、占空比供电。
- `[原理图]` 没有土壤探头接口的专用画法：交流激励、屏蔽、护环、隔离、探头身份/校准电阻。
- `[PCB]` 没有探头连接器/灌封、腐蚀、电缆电容、水汽侵入、埋设深度的布局与结构要求。
- `[程序]` 没有标定系数、滤波、温度补偿、灌溉控制滞回、探头健康/断线检测。
- `[验证]` 没有烘干称重法/标准仪器对比、不同土质矩阵、长期埋设、腐蚀试验、灌溉响应试验。
- `[常见误判]` 缺“电阻式直流激励导致电解”“电容式读数受盐分影响”“拔探头等于土壤校准”“一套系数通吃所有土”“涂层堵住水分交换”。
- `[采购落地]` 缺土壤探头检索词、防水连接器、灌封胶、参考仪器/标准土样。

### 动作

`new`：新写土壤与介质湿度卡；产品级验收引用 S01/product-acceptance，电学部分引用 ANA-01/04、D7。

### 候选型号

- `DFRobot SEN0308`（首选·防水电容式、3.3–5.5 V 模拟输出，常见、wiki 完整）
- `DFRobot SEN0193`（低成本电容式、3.3–5.5 V 模拟输出，适合原型）
- `Vegetronix VH400`（电容式、0–3 V 模拟、资料完整，价格较高）
- `METER EC-5 / Teros 10`（科研级、资料完整、价格高；适合作为标定参照）

### 备注

现有内容只到产品级注意事项（S01 花盆提醒），没有探头电路、激励、标定系数；“拔出探头不等于真实土壤校准”的结论正确，应保留并延伸到土壤类型/盐分/温度。`enclosure-integration.md:25` 的“电容式土壤探头也需验证涂层、吸水、长期腐蚀”是设计约束，不是电路方案。

---

## D6 脉冲流量计

### 现有内容

> 本主题没有脉冲流量计专用文件；下表是相邻可复用内容，不能当作已覆盖流量计数设计。

| 文件 | 行号/章节 | 实际内容 |
|---|---|---|
| `design-hardware/references/design-cards/analog/a08-4-20ma.md` | 1–256 | 若用 4–20 mA 流量变送器，可复用其接收接口；不是脉冲流量计 |
| `design-hardware/references/design-cards/analog/a01-divider.md` | 41、179 | 若用模拟流量传感器，可复用分压；不是脉冲 |
| `design-hardware/references/design-cards/interfaces/i12-level-shift.md` | 1–302 | 5 V 开集/推挽输出到 3.3 V 的电平转换 |
| `design-hardware/references/module-integration.md` | 111–155 | 逻辑门限、上拉/下拉所有权、电流方向（通用） |
| `design-hardware/references/digital.md` | 5–26 | MCU 引脚复用/电平/接口（通用；没有定时器/输入捕获） |
| `design-hardware/references/failures/f26-motor-start-corrupts-adc.md` | 25–46 | 泵/电机噪声耦合的构造案例（模拟采集，不是脉冲计数） |

### 判定

`missing`

### 已覆盖

全库没有脉冲流量计内容；只有通用电平/接口、4–20 mA/模拟采集和连接器知识可间接复用。

### 缺口

- `[用户话术]` 没有“水表/流量/升每分钟/累计用量/灌溉流量”等问法，也没有区分瞬时流量与累计总量。
- `[路线选择]` 没有涡轮/霍尔、桨轮、超声、电磁、差压的路线比较；没有脉冲 vs 4–20 mA vs 模拟量的选择表。
- `[必查参数]` 缺流量范围、K 系数/每升脉冲数、最小/最大流量、脉冲宽度、输出类型（开集/推挽）、供电、压降、介质、温度、精度、重复性。
- `[电路组成]` 缺上拉/电平转换、RC 滤波、施密特整形、ESD/保护、屏蔽电缆、地参考。
- `[参数确定]` 缺 K 系数标定、累计量换算、最大流量下的脉冲宽度、采样/更新率、去抖、计数器溢出。
- `[原理图]` 没有脉冲输入的专用画法：上拉到 3.3 V/5 V、串阻、钳位、屏蔽、地。
- `[PCB]` 没有连接器/电缆屏蔽、地、隔离、泵/继电器噪声的布局要求。
- `[程序]` 没有输入捕获/中断、去抖、累计、瞬时流量计算、反向流检测、传感器故障检测。
- `[验证]` 没有标准流量台/称重法、低/高流量、气泡、回流、长期漂移验证。
- `[常见误判]` 缺“每升脉冲数固定”“5 V 开集可直接进 3.3 V”“软件轮询计数”“忽略最小流量”“安装方向无关”。
- `[采购落地]` 缺流量传感器检索词、管接头/螺纹、标定与流量台。

### 动作

`new`：新写脉冲流量计卡；工业 4–20 mA 流量变送器部分引用 D7/ANA-08，电平部分引用 IF-12。

### 候选型号

- `YF-S201`（首选·常见霍尔涡轮：1–30 L/min、5 V、约数百 pulses/L；资料版本需核对）
- `YF-S401`（1–5 L/min 小流量，常见）
- `Seeed SEN0217`（G1/2 水流量传感器、1–30 L/min、5 V，wiki 较完整）
- `FS400A`（1–60 L/min 级霍尔流量计，常见；量程/脉冲常数按具体批次核对）

### 备注

本主题在库内没有现有内容；YF-S201 等的“每升脉冲数”不是固定值，必须按实际传感器/批次标定；5 V 开集输出不能直连 3.3 V MCU，需上拉/分压/电平转换与保护。

---

## D7 模拟量流量与液位接口

### 现有内容

| 文件 | 行号/章节 | 实际内容 |
|---|---|---|
| `design-hardware/references/design-cards/analog/a08-4-20ma.md` | 1–256（§1 37–50；§2 52–69；§3 71–96；§4 98–121；§5 123–173；§6–§12 175–256） | 4–20 mA 两/三/四线、compliance、采样电阻、功耗、隔离、保护、误差预算、逐脚、原理图、PCB、异常、验证 |
| `design-hardware/references/examples/x10-4-20ma.md` | 1–218 | 4–20 mA 两线制接收局部范例：回路、保护、Kelvin、地关系、布局 |
| `design-hardware/references/projects/p02-industrial-rs485-analog.md` | 1–503（§1 37–52；§2 66–90；§4.3 169；§11 477） | 工业 RS485/4–20 mA 采集节点：两路 100 Ω 分流、2.5 V 基准、误差预算、连接基线、首板计划 |
| `design-hardware/references/calculations/analog-adc.md` | 192–233、508–553 | 0–10 V 分压进 3.3 V/12 位 ADC 的三种阻抗方案；4 路 0–10 V 采集前端项目样本 |
| `design-hardware/references/simulation-measurement.md` | 556–610 | 24 V + 4 路 0–10 V + RS-485 的离线规划样本与测量计划 |
| `design-hardware/references/design-cards/analog/a01-divider.md` | 41、179 | 0–10 V 分压通用方法 |
| `design-hardware/references/design-cards/analog/a03-diff-amp.md` | 1–346 | 高共模/差分接收 |
| `design-hardware/references/design-cards/analog/a04-adc-driver.md` | 1–331 | 采样建立与 RC |
| `design-hardware/references/design-cards/analog/a05-vref.md` | 1–342 | 基准误差与比率测量 |
| `design-hardware/references/domains.md` | 11 | 工业 24 V、4–20 mA/0–10 V、隔离/浪涌 |
| `design-hardware/references/task-scenarios.md` | 16（S09）、25（S18） | 改 4–20 mA 输入、工业 RS485/4–20 mA 采集节点场景 |
| `design-hardware/references/module-cards.md` | 38 | 4–20 mA 先辨两线/三线/四线、回路供电和共模 |

### 判定

`partial`

### 已覆盖

ANA-08 完整覆盖 4–20 mA 两/三/四线、compliance、采样电阻、隔离/保护与误差预算；ANA-01/calculations §5.1/§10 覆盖 0–10 V 分压进 ADC；P02/x10 给出工业采集节点与局部范例；但没有 0–10 V 专用卡、流量平方律/液位标定/NAMUR 等过程量语义。

### 缺口

- `[用户话术]` 没有“接压力变送器/液位计/流量计/4–20 mA/0–10 V”等问法，也没有先问两线/三线/四线、回路供电还是自供电。
- `[路线选择]` 没有 4–20 mA vs 0–10 V vs 0–5 V vs 数字总线的取舍；没有隔离 vs 非隔离、环路供电 vs 自供电、250 Ω 转 1–5 V vs 直接电流输入的选择表。
- `[必查参数]` ANA-08 已有回路类型/电源/compliance/最大电流/线阻/保护/采样电阻/共模/隔离/ADC；缺 0–10 V 输入阻抗、过压、反接、24 V 误接、NAMUR NE43、HART、阻尼、变送器精度/长期漂移。
- `[电路组成]` ANA-08 给 4–20 mA 接收器；缺 0–10 V 输入分压/保护/缓冲、三线制 0–10 V 传感器、隔离前端、共模/地关系。
- `[参数确定]` 缺 0–10 V 分压/输入阻抗/保护、差压流量平方律线性化、液位 4 mA/20 mA 标定、阻尼、故障电流阈值。
- `[原理图]` 缺 0–10 V 输入的专用画法、24 V 误接保护、隔离边界、屏蔽/接地。
- `[PCB]` ANA-08 有 4–20 mA 布局；缺 0–10 V 输入保护位置、长线、浪涌、爬电/间隙。
- `[程序]` 缺缩放/线性化（差压流量平方律）、阻尼/滤波、NAMUR 故障判定、累计、校准。
- `[验证]` 缺 4/20 mA 信号源校准、0–10 V 源、过压/反接、隔离耐压、长线、浪涌测试。
- `[常见误判]` 缺“4–20 mA 当普通电压输入”“0–10 V 直连 3.3 V ADC”“24 V 误接”“流量一定与电流线性”“液位 4 mA=0 但变送器可能反向”。
- `[采购落地]` 缺变送器检索词、采样电阻/隔离接收器/保护件、校准信号源。

### 动作

`supplement`：4–20 mA 电气部分继续以 ANA-08 为主；新增 D7 补充卡，重点写 0–10 V 输入保护、流量/液位过程量语义、NAMUR/HART、程序缩放与采购。

### 候选型号

- `TI RCV420`（首选·4–20 mA 接收：内置 4–20 mA→0–5 V、伪地；资料为 1992 年应用公告，需核对现代替代）
- `TI INA149`（首选·0–10 V/高共模差分：高共模范围、增益 1，资料完整）
- `TI AMC1311`（隔离放大器，用于隔离 0–10 V/4–20 mA 前端；资料完整）
- `ADI AD629`（高共模差分放大器，0–10 V 差分接收备选；资料完整）

### 备注

ANA-08 的 RCV420/ISO122 例子来自 1992 年应用公告，只能作历史/拓扑参考；P02 用 100 Ω+2.5 V 基准，ANA-08 算例用 200 Ω+5 V ADC，二者不能混用；0 mA 断线判据要结合两线/三线/四线变送器类型，不能一概而论。

---

## 复用关系

- **D1 → ANA-09（主复用）**：桥式前端、四/六线、比率测量、误差预算直接引用；ANA-03（差放）、ANA-04（ADC 驱动）、ANA-05（基准）、C1（误差链）、DM22、SC33/SC36、PL21、RT21 同步引用。
- **D2 → ANA-01/ANA-02/ANA-04/ANA-05、C1、F26、DM21/DM24**：通用模拟链复用；桥式压力芯体可再引 ANA-09。
- **D3 → IF-01（I²C）、IF-03（SPI）、IF-12（电平）、x05（I²C 传感器范例）、P01（I²C 传感器集成）、G08（BME280 安装）、DM24、PL24**。
- **D4 → D3（MS5837 类数字压力/水深）、D7（4–20 mA 投入式液位变送器）、enclosure-integration（密封/凝露）、DM24、SC37/SC38**。
- **D5 → S01/product-example/product-acceptance（产品级土壤提醒）、ANA-01/ANA-04（模拟探头）、D7（4–20 mA 土壤变送器）、enclosure-integration（涂层/腐蚀）、DM24、PL24**。
- **D6 → D7（4–20 mA 流量变送器）、IF-12（5 V→3.3 V）、module-integration §4（逻辑门限/电流方向）、F26（泵/电机噪声）、DM19/DM26（涉及泵控/工业 IO 时）**。
- **D7 → ANA-08（4–20 mA 主复用）、ANA-01/ANA-03/ANA-04/ANA-05、x10、P02、calculations/analog-adc §5.1/§10、simulation-measurement §10.1、S09/S18、DM22、SC37/SC38、PL15/PL21、RT08/RT10**。
- **跨组**：工业接口组（IF-07 RS-485、P02）、低功耗组（B2 休眠电流、P01）、结构与防护组（enclosure-integration、DM23/DM24）、故障组（F26/F33）。

## 需要同步修正

- `[错误]` `design-cards/analog/a09-bridge.md:151`：淘汰 INA 增益 200 的理由写成“5 V 供电下摆幅接近轨”，但 2 V 输出在 5 V 供电下并不接近轨；且增益不改变输入共模，“共模余量变小”也不成立。建议改为：零点/失调余量、噪声、CMRR 与后级摆幅余量不足。
- `[错误]` `design-cards/analog/a09-bridge.md:130`：“若用 24 bit ADC 直接采，Code≈33,554，也可行”过于乐观：33,554 码只相当于约 15 bit，且未计 ADC 有效位数/噪声/50–60 Hz 陷波/桥自热。建议加条件：有效位数、噪声、漂移与陷波满足预算时才可行。
- `[同步]` `design-cards/analog/a08-4-20ma.md:96`：RCV420 的“对地 10…5 V”输出与 0–5 V ADC 并列出现，容易被读成可直连；应明确 10–5 V 需再电平移位/差分接收，不能直接进 0–5 V ADC。
- `[同步]` `design-cards/analog/a08-4-20ma.md` §1/§10：0 mA 断线判据要与两线/三线/四线变送器类型绑定；0 mA 既可能是断线，也可能是三线制零输出或设备断电。现有文字已提示“输出不明确”，但算例/表格容易让人直接按 0 mA 判故障。
- `[同步]` 索引/计数：`design-cards/README.md:3`（60 张、E1 42/E2 18）、`SKILL.md:155/158`（60 张）、`docs/expansion-report.md:7`（60 张）在新增 D 组卡片后需更新；`module-cards.md:37-41`、`SKILL.md:139` 需加传感器卡入口。
- `[同步]` `domain-design-details.md:43-45`：DM22 只列桥式/RTD/热电偶/4–20 mA，DM24 只列温湿度/气压/气体/光学/惯性；缺压力介质/液位/流量/土壤的专用检查项。建议新增 DM49–DM52 或扩写 DM22/DM24。
- `[同步]` `selection/modules-connectors.md:153-171`：传感器表只有 NTC/RTD/桥式/电流/环境/磁光，缺压力/液位/流量/土壤行；`182-196` 的商城关键词只有 BME280，需补称重/压力/液位/流量/土壤检索词。
- `[同步]` `source-register.md:10-23`：ANA-S01–S14 没有 HX711/ADS1232/NAU7802、MPX/MS5837/BMP388、YF-S201、土壤探头等来源；新增卡片必须登记来源 ID、版本、查阅范围与不能推广部分。
- `[同步]` `task-scenarios.md`：只有 S01（土壤）与 S09/S18（4–20 mA），缺称重/压力/液位/脉冲流量场景；新增卡片后应在 `assets/scenarios.json` 与 `task-scenarios.md` 同步加场景/反例。
- `[同步]` `examples/README.md:6-19` 与 `projects/README.md:5-10`：没有称重/压力/液位/流量范例；若要补局部范例，需同步计数与索引（当前 12 个范例、4 个项目样本）。

## 文件组织建议

推荐**拆分**，不写一个巨型组文件。新建 `design-hardware/references/design-cards/sensors/`：

| 建议文件 | 内容 | 约行数 |
|---|---|---:|
| `README.md` | 组索引、路线表、与 ANA-08/ANA-09 的分工、检查 ID 映射 | 60 |
| `s01-weighing-load-cell.md` | D1 补充卡：现有内容指回 ANA-09；新增用户话术/路线、机械与安装、程序、验证、采购、常见误判 | 180 |
| `s02-pressure-analog.md` | D2 新卡：12 节，重点量程/过压/介质、比率与校准、原理图/PCB、程序/验证、采购 | 240 |
| `s03-pressure-digital.md` | D3 新卡：I2C/SPI 与地址、量程/气路/介质、ODR/过采样/补偿、程序/验证、采购 | 220 |
| `s04-liquid-level.md` | D4 新卡：路线比较、死区/泡沫/泵控、安装/校准、程序/验证、采购 | 240 |
| `s05-soil-moisture.md` | D5 新卡：探头类型/AC 激励、土壤标定/盐分/温度、封装/腐蚀、程序/验证、采购 | 220 |
| `s06-pulse-flow.md` | D6 新卡：脉冲/OC/电平、K 系数/累计、输入捕获/去抖、验证/采购 | 220 |
| `s07-analog-process-interface.md` | D7 补充卡：4–20 mA 指回 ANA-08；0–10 V 保护/输入阻抗、流量平方律/液位标定、NAMUR/HART、程序/验证/采购 | 200 |

合计约 1580 行。若坚持单文件，可用 `design-cards/sensors/d-force-pressure-level-flow.md` 约 1000–1200 行，7 章各 140–170 行；但按 `SKILL.md` “先读 1–2 张卡”的原则，拆分更利于按需加载，也避免 D1/D7 与 ANA-09/ANA-08 重复。

每张卡建议沿用现有 12 节模板，并把任务书 11 问映射为：§1 用途/边界（含用户话术）、§2 路线选择、§3 必查参数、§4 电路组成、§5 参数确定/算例、§6 器件选择、§7 原理图、§8 PCB、§9 程序、§10 验证、§11 常见误判、§12 采购与来源。D1/D7 作为“补充卡”可压缩为 8–10 节，明确写“电气计算见 ANA-09/ANA-08”。
