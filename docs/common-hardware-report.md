# 常用硬件能力扩展报告（2026-10-22）

> 分支：`feat/common-hardware-coverage`；基线 `origin/main` = `0fe5cf8`。
> 状态标记：`DONE` 已交付并有证据 / `PARTIAL` 部分完成 / `NOT RUN` 未执行 / `BLOCKED` 环境或资料阻断。

## 0. 结论

本轮把“用户说测温、称重、风扇、电池设备、加屏幕”这类日常需求，落成了 13 组常用硬件资料、102 个主题和 12 个组合应用；每个主题固定回答路线、必查参数、电路、算例、逐脚、PCB、程序、验证、误判与采购落地。内容以原厂数据手册为主来源，电气理论继续引用现有 60 张设计卡，不另建近似卡片。另修正了一批高影响的旧内容数值、边界与引用问题（见第 4 节与各组 `## 需要同步修正`；不是审计 78 条的全部）。

边界：没有 PCB、制造、样机、固件、热/EMC/安规实测；所有涉及标准与认证的地方只写“需取得并核对”，不声称通过。

## 1. 原有内容盘点与缺口

开工前先做了 13 份分组审计（[证据目录](evidence/common-hardware-2026-10-22/audit/)），按任务书 102 个主题逐条对照现有设计卡、范例、故障库、深潜、选型、计算与项目样本：

| 判定 | 数量 | 含义 |
|---|---:|---|
| adequate | 15 | 现有内容可直接引用，只补用户话术/采购/验证 |
| partial | 60 | 有基础，缺本主题的具体型号、算例或产品化内容 |
| missing | 27 | 没有本主题内容 |

动作分布：`new` 43、`supplement` 46、`reuse` 13。详细缺口、候选型号与旧内容问题见 [缺口分析](common-hardware-gap-analysis.md)。

审计同时发现 78 条旧内容问题：数值/逻辑错误 30 条、单型号外推/边界收窄 17 条、悬空或错向引用 25 条、索引/计数 6 条。本轮优先修正会影响画图/选型/烧板的条目。

## 2. 本轮新增或深化的高频硬件能力

新增 `design-hardware/references/common-hardware/`：

| 组 | 文件 | 主题 |
|---|---|---|
| A 温度/湿度/环境 | [a-environment.md](../design-hardware/references/common-hardware/a-environment.md) | A1 NTC、A2 数字温度、A3 RTD、A4 热电偶、A5 温湿度、A6 气压/高度、A7 气体/空气质量 |
| B 光/接近/距离/人体 | [b-optics.md](../design-hardware/references/common-hardware/b-optics.md) | B1 环境光、B2 光电二极管 TIA、B3 反射、B4 对射/槽型、B5 PIR、B6 ToF、B7 超声、B8 毫米波 |
| C 运动/位置/转速 | [c-motion.md](../design-hardware/references/common-hardware/c-motion.md) | C1 加速度、C2 IMU、C3 磁力计、C4 霍尔、C5 编码器、C6 转速、C7 限位/接近 |
| D 力/压力/液位/流量 | [d-force.md](../design-hardware/references/common-hardware/d-force.md) | D1 称重、D2 模拟压力、D3 数字压力、D4 液位、D5 土壤、D6 脉冲流量、D7 模拟量接口 |
| E 电压/电流/电能 | [e-measurement.md](../design-hardware/references/common-hardware/e-measurement.md) | E1 电压、E2 低侧、E3 高侧、E4 双向、E5 隔离、E6 电量、E7 多通道 |
| F 供电入口/保护 | [f-input-protection.md](../design-hardware/references/common-hardware/f-input-protection.md) | F1 USB、F2 USB-C 5V、F3 PD、F4 DC 座/端子、F5 反接、F6 过流、F7 过压、F8 浪涌/热插拔 |
| G 电源转换 | [g-power-conversion.md](../design-hardware/references/common-hardware/g-power-conversion.md) | G1 LDO、G2 Buck、G3 Boost、G4 Buck-Boost、G5 负压、G6 隔离、G7 负载开关、G8 多路 |
| H 电池/充电/低功耗 | [h-battery.md](../design-hardware/references/common-hardware/h-battery.md) | H1 一次电池、H2 充电、H3 电源路径、H4 保护、H5 多节、H6 共存、H7 低功耗、H8 低电量 |
| I 主控/最小系统 | [i-mcu.md](../design-hardware/references/common-hardware/i-mcu.md) | I1 低成本、I2 通用、I3 无线、I4 模拟主控、I5 时钟、I6 复位/看门狗、I7 下载、I8 存储 |
| J 总线/有线通信 | [j-buses.md](../design-hardware/references/common-hardware/j-buses.md) | J1 I²C、J2 SPI、J3 UART、J4 RS-232、J5 RS-485、J6 CAN、J7 USB、J8 以太网 |
| K 开关/继电器/电机 | [k-drive.md](../design-hardware/references/common-hardware/k-drive.md) | K1 低侧、K2 高侧、K3 继电器、K4 电磁阀、K5 直流电机、K6 步进、K7 风扇、K8 舵机、K9 加热器 |
| L 显示/声音/交互 | [l-hmi.md](../design-hardware/references/common-hardware/l-hmi.md) | L1 LED、L2 数码管/矩阵、L3 OLED/LCD、L4 TFT、L5 触摸、L6 按键、L7 旋钮、L8 蜂鸣器、L9 扬声器 |
| M 无线/时间/隔离 | [m-wireless-time.md](../design-hardware/references/common-hardware/m-wireless-time.md) | M1 Wi-Fi、M2 BLE、M3 Sub-GHz、M4 蜂窝、M5 GNSS、M6 RTC、M7 NFC/RFID、M8 数字隔离 |

每个主题固定 12 节：用户会怎么说、路线选择、必查参数、电路组成、参数与算例、原理图与逐脚、PCB、程序、验证、常见误判、采购与落地、来源与证据。组文件头部有“本组怎么用”的话术路由，末尾有来源表与需要同步修正的旧内容。

## 3. 每类具体型号与来源

每组至少一个具体型号达到 `E1`（本次打开原厂资料）。代表性锚点：

| 组 | 主要锚点型号 |
|---|---|
| A | Murata NCP15XH103F03RC、TI TMP117、Maxim DS18B20、Maxim MAX31855/31856、Sensirion SHT40、Bosch BMP390、Sensirion SGP41/SCD41 |
| B | TI OPT3001、Vishay VEML7700、Vishay BPW34 + TI OPA320、Vishay TCRT5000/TCST1103、Panasonic EKMC1601111、ST VL53L1X、MaxBotix MB1240、Hi-Link LD2410 / Infineon BGT60 |
| C | ST LIS2DH12、ST LSM6DS3TR-C、ST LIS3MDL、TI DRV5032/DRV5055、Bourns PEC11R、ams AS5600/AS5047P、Omron D2F |
| D | Avia HX711、TI ADS1232、NXP MPXV5010、Bosch BMP388、TE MS5837、JSN-SR04T、DFRobot SEN0308、YF S201、TI INA149 |
| E | TI INA181A2/INA240/INA228、TI AMC1300/AMC1306、TI BQ27441、TI ADS1115/ADS131M08 |
| F | TI TPD3S014、TI TUSB320LAI、ST STUSB4500、Same Sky PJ-002A、AOS AO3401A、TI TPS2595、Vishay SMBJ |
| G | TI TPS7A02、TPS54202H、TPS61023、TPS63802、TPS63710、SN6501、TPS22918、TPS2116 |
| H | Energizer E91/CR2032/L91、EVE ER14250、Microchip MCP73831、TI BQ24074/BQ25619、TI BQ2970、TI BQ76952、TPS2121 |
| I | WCH CH32V003F4P6、ST STM32F103C8T6、Espressif ESP32-C3-MINI-1、ST STM32G431、Abracon ABM8、TI TPS3823、WCH CH340C、Microchip AT24C256C |
| J | Sensirion SHT40、AT24C256C、Winbond W25Q128JV、CH340C、TI MAX3232、TI THVD1450、TI TCAN334、Microchip USB2514B、WIZnet W5500 / TI LAN8720A |
| K | Infineon IRLZ44N、TI TPS1H100-Q1、Omron G5LE-1、TI DRV110、TI DRV8871、TMC2209、Delta AFB0812HH、MG996R |
| L | Everlight/Kingbright LED、Titan TM1637、Maxim MAX7219、Solomon SSD1306/SH1106、ST ST7789V、FT6236/TTP223、Omron TS-1088、Bourns PEC11R、CUI CEM-1203、Maxim MAX98357A |
| M | Espressif ESP32-C3-MINI-1、Nordic nRF52840、Semtech SX1268、Quectel EG915N、u-blox MAX-M10S、Maxim DS3231、NXP PN532、TI ISO7721 |

来源登记在 [原始来源登记](../design-hardware/references/source-register.md) 的 `CHW-S001–S255` 段（本轮实际登记 200 条）；每条含文档号/版本、实际查阅范围、支持内容与“不能推广”。商品页、搜索摘要、二手转载不作为已核对正文；本地缓存路径与公开 URL 都在来源表中标明。

## 4. 修正的旧错误与同步范围

已修正的高影响条目（其余见各组 `## 需要同步修正` 与本轮 diff）：

- **RTD 误差**：ANA-10 把 400 Ω 当 850 °C 内、用全量程平均 0.362 Ω/°C 折算高温端，低估约 20%；改为局部 dR/dT，并明确 400 Ω 已约 880 °C。
- **高侧电流误差**：ANA-07 把 100 µV/1 mΩ 算成 10 mA（应为 100 mA），RSS/最坏误差被低估；已重算为 158.5 mA/1.59%（RSS）、315.5 mA/3.16%（最坏）。
- **分压 ADC 建立**：ANA-01/analog-adc 的工具按 3.3 V 阶跃算 0–10 V 分压节点（实际 2.5 V），1085.5 LSB 高估约 32%；用 `rc_settle_sim.py --vin 2.5` 重跑得 822.42 LSB。
- **桥式候选理由**：ANA-09 淘汰增益 200 的理由“5 V 摆幅接近轨”不成立；改为零点/噪声/CMRR/后级范围，并给 24 bit 直接采加 ENOB/噪声/陷波条件。
- **RS-485/CAN 24 V 端接功率**：IF-07/IF-08 把两端 120 Ω 当串联，1.2 W/只；实际两端并联，最坏 4.8 W/只、9.6 W 合计；按三种故障拓扑重写。
- **USB 低速上拉**：IF-09 “低全速设备在 D− 上接 1.5 kΩ”改为“低速设备 D−；全速设备 D+；全速/高速能力设备不得在 D− 放 1.5 kΩ”。
- **感性负载释放时间**：DRV-01/02/03 的 `L·ΔI/V` 线性式忽略 `I·R`，126 ms/21.4 ms 等严重偏大；改用 RL 解 `t=τ·ln(1+I0·R/V_rev)`，D01 约 12.2 ms、D03 仅二极管 3.62 ms（满足 5 ms，旧结论“淘汰”不成立）。
- **超级电容漏电**：PWR-14 把 2.5 µA 当整组漏电、10 s 掉 25 mV；改为按接法区分整组 5 µA，10 s 掉 50–100 µV。
- **LDO**：PWR-01 补 TPS7A02 `TJ(max)=125 °C`、VDO 95% 判据、反向电流 5% 只属该型号。
- **USB-C**：P12 把 0.9 A 与 CC 档并列；改为 USB 2.0 500 mA / USB 3.x 900 mA（端口电流）/ Type-C 1.5/3 A（CC 广告）。F09/P12 两套 CC 窗口加版本说明。
- **选型与索引**：selection 拆分“环境光/反射/对射/磁开关/磁力计/接近”；DM24/PL24 拆环境/光学/惯性；module-cards 蜂鸣器移到 HMI；W05 显示卡补 L 组入口；source-register 修正 PWR-S11/13/14、MCU-S06 列错位。
- **MCU 调试/复位**：MCU-07 补 STDC14 pin 1/2、13/14；MCU-03 迟滞 6 mV 限定 TPS3808G01；P01 的 Q1 不再用 `Vgs(th)` 证明导通。

未修正/仅记录的条目：需要标准正文、具体料号曲线或实物测试的项，保持 `待核实`，没有用竞品参数补齐。

## 5. 可直接用于 Agent 的路由与设计资料

- [常用硬件 README](../design-hardware/references/common-hardware/README.md)：按用户话术（测温/称重/风扇/电池/屏幕）路由到 13 组与 12 个应用。
- [SKILL.md](../design-hardware/SKILL.md)：按需读取表新增“常用硬件”入口；3.1 节说明与设计卡的分工。
- [module-cards.md](../design-hardware/references/module-cards.md)：主控/电源/接口/无线/模拟/驱动/HMI/隔离各节补常用硬件链接。
- [domains.md](../design-hardware/references/domains.md)：新增“日常常用硬件”领域行。
- 每组头部“本组怎么用”给出用户话术 → 先判断 → 路线 → 主题；组内主题再按 12 节展开。
- 盲测后修正的 routing：README 增加“ESP32/无线 + 2.4 寸彩屏 + 蜂鸣器”和“门窗开合/干簧/霍尔/纽扣电池”直达行；05 电子秤行改为 `D1 + ANA-09 + I1 + L3 + F2/G1`（E1/E7 仅可选）；08 RS-485 行拆成“无 4–20 mA（默认隔离）”和“带 4–20 mA（加 D7/E5）”；A2 补 DS18B20 ±0.5 °C 仅 −10…85 °C；03 应用增加 ESP32 + 2.4 寸 TFT 变体（≥1 A Buck）。

## 6. 组合应用成果

12 个组合应用在 [applications/](../design-hardware/references/common-hardware/applications/)：

温度过高报警、自动调速风扇、桌面温湿度显示、电池门窗提醒、简易电子秤、水箱液位提醒、设备电流监测、RS-485 采集节点、定时控制装置、土壤监测装置、小型数据记录器、电磁阀控制器。

每个给出：需求与验收、推荐路线及理由、器件资料需求、模块组成与连接、关键计算与未确定项、原理图组织、PCB 重点、程序与测试、采购与制造落地、完成级别。完成级别按“资料/离线/EDA/制造/样机/实测”如实标注；除 S1 温度报警外均为离线设计。

## 7. 工具、计算与真实工程验证

| 项 | 状态 | 证据 |
|---|---|---|
| 基线回归 | DONE | 改动前 148 tests OK |
| 新结构契约 | DONE | `tests/test_common_hardware.py`：13 组/102 主题/12 应用/12 标题/来源登记/无占位；全量 `260 tests OK` |
| 来源登记 | DONE | 200 条 `CHW-S`，`test_no_unregistered_source_ids` |
| C 号/库存纪律 | DONE | `test_no_obvious_fabricated_c_numbers` |
| 计算复核 | PARTIAL | ADC 建立用 `rc_settle_sim` 重跑；其余算例为手算/脚本复核，未逐一仿真 |
| 真实 EDA | DONE（连接级） | [S1-NTC-ALARM](evidence/common-hardware-2026-10-22/eda/README.md)：12 器件、网表、save、reopen match、DRC 2 warn |
| PCB/制造/样机 | NOT RUN | 无 Gerber/BOM/坐标/DFM/打样/SMT/实物 |
| 全在线 GUI | NOT RUN | CLI 会话恒半离线 |
| 独立资料审校 | NOT RUN | 未单独派审校员逐条复核；作者核对 + 集成人抽查 |
| 盲测路由 | DONE（6/6） | [blind/eval.md](evidence/common-hardware-2026-10-22/blind/eval.md)：B1–B6 路线均正确；暴露的 5 处 routing 不一致已修 |

## 8. 未解决问题及所缺条件

- **标准正文**：IEC 60751/60584、EN 50291、UL 2034、IEC 62368-1/60664-1、UN38.3 等未取得；涉及处只写“需取得并核对”，不声称认证。
- **实时商品信息**：C 号、价格、库存、MOQ、包装、SMT 可贴状态未核对；需按立创商城/嘉立创订单实时查询。
- **具体型号曲线**：部分 NTC R-T 表、保险丝 I²t、PTC 动作曲线、风扇 PQ、电池放电曲线只有手册图/摘要；需要逐型号取曲线或实测。
- **PCB/热/EMC/安规**：全部未做；S1 只是连接级原理图。
- **半离线 EDA**：不能写成全在线验收；需用户 GUI 会话复验。
- **盲测/审校**：若未完成，交付报告中明确标 `NOT RUN`，不把结构测试当内容正确。

## 9. 对新手提问次数和工程师复核便利性的影响

- 新手说“测水温/称重/风扇/电池/屏幕”时，README 的话术表直接给出先判断什么、推荐路线和要读的主题，不再从“温度传感器”五个字跳到某个模块；首轮只需问 1–2 个影响路线的问题（介质/温区/量程/安装/供电）。
- 工程师可按“路线表 → 必查参数 → 逐脚 → PCB → 程序 → 验证 → 误判”复核；每组末尾的来源表能定位到手册章节，不需要重新搜资料。
- 组合应用把跨组接口（传感器+主控+显示+电源+驱动）一次列清，减少“单模块正常、组合失败”的漏项。

## 10. 后续维护方式

1. 新增/替换型号时，同时更新组文件、`source-register.md`、`tests/test_common_hardware.py` 主题清单；不为凑数量拆近似文档。
2. 每季度抽查 `CHW-S` 来源的版本/生命周期；停产/换版时把旧结论标 `待核实`，不静默覆盖。
3. 有真实 EDA/PCB/样机证据时，在对应主题的“验证”节和 `docs/evidence/` 补链接；没有证据保持 `NOT RUN`。
4. 旧卡片被修正后，检查组文件中的引用与算例是否仍成立；冲突先写适用条件，不互相覆盖。
5. 新增组合应用时，先复用现有 12 个的模板与主题链接，避免另建同义文件。

---

**本轮完成等级：** 资料与离线设计 `DONE`；结构/来源/纪律测试 `DONE`（260 tests OK）；盲测 6/6 `DONE`；真实 EDA 连接级 `DONE`；独立资料审校 `NOT RUN`；PCB/制造/样机/全在线 `NOT RUN`。
