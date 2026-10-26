# M 无线、时间与常用功能模块 盘点

> 审计对象：`C:\Users\jlc\work\hardware-design-skill`，HEAD `0fe5cf8`，2026-10-22。
> 判定口径：`adequate` 已足够可直接引用；`partial` 有基础但缺本主题具体内容；`missing` 没有。
> 动作口径：`reuse` 引用 + 极短补充；`supplement` 在现有卡上补缺口；`new` 新写。
> 对照 11 问：用户话术、路线选择、必查参数、电路组成、参数确定、原理图、PCB、程序、验证、常见误判、采购落地。

| 主题 | 判定 | 动作 | 结论一句话 |
|---|---|---|---|
| M1 Wi-Fi | partial | supplement | 模组供电/EN/strap/天线很扎实，缺路线选择、Wi-Fi 规格参数、配网程序与采购。 |
| M2 BLE | partial | supplement | 共享 RF-01 的模组硬件，缺 BLE 专有的低功耗、晶振/巴伦、协议与测试。 |
| M3 Sub-GHz | missing | new | 全库只有“Sub-GHz 另查天线指南”的边界声明，无任何电路/选型/参数内容。 |
| M4 蜂窝 | partial | supplement | RF-03 只覆盖 EG915N 的 2G 突发供电；缺 LTE/NB-IoT 路线、SIM/eSIM、接口、认证。 |
| M5 GNSS | partial | supplement | RF-04 覆盖天线/偏置/NF/屏蔽；缺模组选型、接口/PPS/备份、TTFF 与共存。 |
| M6 RTC | partial | new | PWR-14 只算备份能量，MCU-05/D2 只算 32.768 kHz 晶体；无 RTC 芯片级设计卡。 |
| M7 身份与标签读取 | missing | new | 全库无 NFC/RFID/读卡/条码内容。 |
| M8 隔离与数字隔离器 | partial | new | 有隔离边界检查与零散隔离收发器提示，但无隔离器选型/参数/隔离电源卡。 |

---

## M1 Wi-Fi

### 现有内容

- `design-hardware/references/design-cards/wireless/w01-wifi-ble.md:1-202`：RF-01 全卡；§1–§12，重点是 §2 必要输入（51-64）、§4 参数步骤（80-99）、§5 算例（100-117）、§7 逐脚（134-148）、§9 PCB（155-168）、§11 验证（183-190）。
- `design-hardware/references/design-cards/wireless/w02-antenna.md:1-194`：RF-02 全卡；50 Ω 馈线、CLC 匹配、净空、测试口；§4（76-94）、§5（95-111）、§9（147-161）。
- `design-hardware/references/engineering-deepdives/topics/d4-wireless-integration.md:1-717`：D4 整机集成；集成边界（75-106）、认证（110-126）、净空几何（128-176）、burst 电源（178-195、401-437）、PCB 审查（252-318）、失败链（487-632）。
- `design-hardware/references/module-cards.md:31-35`：第 5 类“无线、射频与定位”的三条组合检查。
- `design-hardware/references/domain-design-details.md:61-66`：DM33–DM36（集成边界、净空、弱信号接收、匹配/测试口）。
- `design-hardware/references/module-integration.md:291-303`（§9 参考地/隔离/屏蔽/回流）、`376-389`（§12 机械/热/天线/测试空间）。
- 故障：`failures/f18-antenna-enclosure.md:1-86`（装壳失谐）、`failures/f25-radio-tx-resets-system.md:1-194`（发射复位）、`failures/f03-esp32-strap.md:1-98`（strap 被拖偏）、`failures/f32-enclosure-degrades-rf-and-thermal.md:1-265`（装壳 RF/热）。
- 范例：`examples/x12-antenna.md:1-215`（Wi-Fi 模组与天线局部布局草案）。
- 项目：`projects/p04-usb-mcu-board.md:40-51,126,156,171-179`（ESP-01S 最小板，C503582）；`projects/p01-low-power-wireless-sensor.md:1-491` 是 BLE 项目，可借其验收写法。
- 测量：`simulation-measurement.md:80,131-137,248,263-264,294,359-364`（S11/S21/OTA/净空）。
- 选型：`selection/modules-connectors.md:56-80`（模组供电/EN/strap 与 ESP32-S3 条件）。
- 来源：`source-register.md:91-92`（RF-S01/S02），`93-94`（RF-S03/S04）。

### 判定

`partial`

### 已覆盖

已把“ESP32 类 Wi-Fi 模组上板”的 3.3 V 峰值/储能、EN RC、strap、天线净空、CLC 初值、VNA/OTA 验证和装壳失谐、发射复位、FCC host 责任讲透，硬件设计可直接引用 RF-01/RF-02/D4。

### 缺口

- **用户话术**：没有“距离/穿墙/并发设备数/是否电池/是否要视频/目标市场认证”的提问模板；现有卡从“已选模组”开始。
- **路线选择**：没有 Wi-Fi vs BLE vs Sub-GHz vs 有线的决策树；没有 2.4 GHz vs 5 GHz、Wi-Fi 4/5/6、模组 vs 裸芯片、ESP32-C3/C6/S3/RTL8720 的取舍。
- **必查参数**：只覆盖供电/EN/strap/天线；缺 TX 功率、EVM、接收灵敏度、带宽/吞吐、MIMO、regulatory domain、共存（Wi-Fi+BLE）等系统参数。
- **电路组成**：没有裸芯片方案的 RF 前端（PA/LNA/开关）、外部 Flash/PSRAM、USB/UART 电平与复位监控；模组方案也没有“主机侧接口边界”的完整清单。
- **程序**：`firmware-bringup.md` 只有通用烧录/联调；缺 SoftAP/BLE 配网、凭据保存、重连退避、country code、MAC、OTA 分区。
- **验证**：VNA/OTA 有，但缺吞吐/iPerf、重连/漫游、Wi-Fi+BLE 共存、法规预扫的通过判据。
- **采购落地**：`lcsc-sourcing.md` 没有任何无线模组/天线条目；缺模组完整后缀、天线形式、C 号/库存/SMT 可贴状态的核对流程。

### 动作

`supplement`：保留 RF-01/RF-02/D4 为深内容；在 RF-01 前加“路线选择/用户话术”一节，在文末加“配网程序接口”和“采购核对”两节；不重写现有 12 节。

### 候选型号

- `ESP32-C3-MINI-1`（首选；现有 RF-01/MCU-S09 已核对，模组天线/Flash/晶振集成，适合作为基线）。
- `ESP32-S3-MINI-1`（IO/算力更大，供电与 strap 条件需按 S3 重查）。
- `ESP32-C6-MINI-1`（Wi-Fi 6 + BLE 5 + 802.15.4，适合新设计，需补当前 datasheet）。
- `RTL8720DN` 模组（双频 Wi-Fi + BLE，成本路线，原厂资料与 SDK 需另核）。

均不写 C 号/库存；采购时按完整后缀在立创商城核对。

### 备注

- `w02-antenna.md:90` 与 `d4:470`、`simulation-measurement.md:80/294/359/668` 重复出现 ESP32-S3 的“35+j0”S11 目标；w02 自己已注明来源笔记定义不完整，疑似应为“S11 ≤ −35 dB”。这是全库同步问题，不是 M1 新写内容能解决的。
- RF-01 的数值全部限定在 ESP32-C3/S3 条件，写法正确；不要把这些值升级成“Wi-Fi 通用值”。
- D4 明确“模组认证不等于整机认证”，M1 应直接引用，不要另写一套认证结论。

---

## M2 BLE

### 现有内容

- `design-hardware/references/design-cards/wireless/w01-wifi-ble.md:1-202`：标题含 BLE，但正文以 ESP32 Wi-Fi 模组为主；BLE 只出现在峰值电流表（340 mA @20 dBm，§4 器件实例）和天线/供电通用步骤。
- `design-hardware/references/design-cards/wireless/w02-antenna.md:1-194`：2.4 GHz 天线/匹配通用，BLE 可直接复用。
- `design-hardware/references/design-cards/mcu/m02-module-mcu.md:76,133-134,193,215,229`：ESP32-C3 可选 32.768 kHz RTC 晶体（ESR ≤70 kΩ、偏置 5–10 MΩ），模组符号按域分组。
- `design-hardware/references/projects/p01-low-power-wireless-sensor.md:1-491`：BLE 温湿度传感器完整离线样本；用户原话（35-53）、方案取舍（66-76）、BLE 模组选型（84）、睡眠/续航（397-401）、验收（403-449）。
- `design-hardware/references/module-cards.md:31-35`、`domain-design-details.md:61-66`：无线组合与集成边界通用检查。
- `design-hardware/references/simulation-measurement.md:359-364`：RF S11/OTA/净空测量。
- 故障：`f25-radio-tx-resets-system.md:1-194` 是 Wi-Fi 案例，但 burst 电源方法与 BLE 发射共用；`f18-antenna-enclosure.md:1-86` 适用于 2.4 GHz BLE。

### 判定

`partial`

### 已覆盖

BLE 的 2.4 GHz 天线/净空、模组供电/EN/strap、32.768 kHz RTC 晶体和低功耗项目样本已有；P01 给出了“BLE 广播 + 5 min 上报 + 1 年续航”的验收写法。

### 缺口

- **用户话术/路线**：没有 BLE vs 2.4 GHz 私有协议 vs Wi-Fi 的选择；没有 BLE 4.2/5.0/5.1/5.2/5.3/5.4 的功能取舍（2M PHY、Coded PHY、AoA/AoD、Isochronous）。
- **必查参数**：缺 BLE 芯片/模组的 TX 功率、接收灵敏度、峰值/平均电流、连接间隔、广播间隔、天线增益、协议栈 Flash/RAM 预算。
- **电路组成**：没有 BLE SoC 的 32 MHz/32.768 kHz 双晶振、巴伦/滤波、DC-DC、射频前端、天线匹配的完整链路；RF-01 只给 ESP32 模组形态。
- **参数确定**：没有“广播/连接占空比 → 平均电流 → 纽扣电池寿命”的 BLE 专有算例；P01 是项目级预算，不是通用方法。
- **程序**：缺 GATT 服务/特征、广播包、连接参数、配对/绑定、MTU、DFU/OTA、配网（手机 App）与白名单。
- **验证**：缺 BLE DTM/直接测试模式、PER/RSSI vs 距离、连接稳定性、Wi-Fi/BLE 共存、纽扣电池实测。
- **采购落地**：缺 nRF52/CH58x/DA14531 等 BLE 专有模组的选型与天线/C 号核对。

### 动作

`supplement`：在 RF-01 增加“BLE 专项”一节（约 40 行），并新增一个 BLE 低功耗算例；或单独写 `w09-ble.md` 但必须只写 BLE 专有内容，避免复制 RF-01。

### 候选型号

- `ESP32-C3-MINI-1`（首选；现有资料最全，BLE 5.0，适合与 Wi-Fi 共存的低成本产品）。
- `nRF52840`（BLE 5.0、USB、Thread/Zigbee，协议栈资料完整，适合 BLE 专有产品）。
- `CH582M`（国产 BLE，成本低，常见；原厂资料/SDK 需按当前版本核对）。
- `DA14531`（超低功耗 BLE，适合纽扣电池；开发板/模组生态需确认）。

### 备注

- RF-01 标题是“Wi-Fi / BLE 模组”，但 BLE 内容只占很小比例；不要把 RF-01 当成 BLE 设计卡直接引用全部结论。
- P01 的 BLE 续航是模型值（421 天），明确标“未实测”；新内容不要把它当保证值。
- BLE 的 2.4 GHz 天线规则可复用 RF-02，但 BLE 的 2M/Coded PHY 对天线带宽/灵敏度要求不同，需另查芯片手册。

---

## M3 Sub-GHz 无线

### 现有内容

- `design-hardware/references/engineering-deepdives/topics/d4-wireless-integration.md:705`：只在“部分适用”一句提到“GNSS/蜂窝/Sub-GHz 的净空/电源/认证思路可参考”，明确不是覆盖。
- `design-hardware/references/failures/f18-antenna-enclosure.md:82`：适用边界一句“蜂窝、Sub-GHz、UWB 等需要各自天线指南”。
- `design-hardware/references/module-cards.md:31-35`：无线类组合检查只列 Wi-Fi/BLE/蜂窝/GNSS，没有 Sub-GHz。
- 其余全库检索无 LoRa/SX126x/CC1101/CMT2300/433/470/868/915 的电路、选型或参数内容。

### 判定

`missing`

### 已覆盖

没有实质覆盖；只有两处“Sub-GHz 不在本文范围、需另查天线指南”的边界声明。

### 缺口

- **用户话术**：没有“距离/穿墙/节点数/电池/频段/天线形式/是否要自组网”的提问模板。
- **路线选择**：没有 433/470/868/915 MHz 的法规与频段选择；没有 LoRa vs FSK/OOK vs 私有协议、模组 vs 芯片、点对点 vs 星型/中继的取舍。
- **必查参数**：缺灵敏度、TX 功率、链路预算、晶体精度/频偏、PA 电流、T/R 开关、天线增益/效率、阻塞/邻道、占空比限制。
- **电路组成**：缺匹配网络/巴伦、PA/LNA、T/R 开关、晶体、去耦、天线与馈线的完整链路。
- **参数确定**：缺 Friis/链路预算、灵敏度与距离、天线 S11、晶体 ppm、平均电流/占空比的算例。
- **原理图/PCB**：缺 RF 走线、天线净空、地平面、屏蔽、晶振布局、PA 回流的具体检查。
- **程序**：缺扩频因子/带宽/编码率、包格式、CAD、RSSI/SNR、占空比与法规限制、点对点/星型协议。
- **验证**：缺传导功率/灵敏度、PER vs 距离、天线 S11、法规占空比/杂散测试。
- **采购落地**：缺 LoRa/FSK 模组、天线、晶体的选型与 C 号核对。

### 动作

`new`：新写 `w09-subghz.md`（12 节设计卡），复用 RF-02 天线方法、PWR-01/PWR-02 电源、MCU-02 模组最小系统、MCU-05 晶体、F18/F32 净空与装壳失效。

### 候选型号

- `SX1268IMLTRT`（首选；410–810 MHz，覆盖中国 433/470 MHz LoRa，Semtech 资料完整）。
- `SX1262IMLTRT`（150–960 MHz，适合 868/915 MHz；与 SX1268 同系列，寄存器/驱动可复用）。
- `CC1101RGPR`（300–928 MHz FSK/OOK，TI 资料成熟，适合低速低功耗私有协议）。
- `CMT2300A`（国产 Sub-GHz 收发器，成本低、常见；原厂资料/驱动需按当前版本核对）。

模块路线可看 `RFM95W`（SX1276 内核）等，但必须按模块厂 datasheet 核对频段/认证。

### 备注

- 这是本组最大的空白；现有任何“无线”结论都不能直接套到 Sub-GHz。
- 频段/占空比/发射功率必须按目标市场法规（SRRC/CE/FCC）核对，不要写“433 随便用”。
- LoRa 的链路预算与 Wi-Fi/BLE 不同，不能用 2.4 GHz 的 λ/10 净空规则代替 Sub-GHz 天线规则。

---

## M4 蜂窝通信

### 现有内容

- `design-hardware/references/design-cards/wireless/w03-cellular.md:1-197`：RF-03 全卡；§1 范围（37-49）、§2 输入（51-65）、§4 参数（82-103）、§5 算例（105-122）、§7 逐脚（138-148）、§9 PCB（156-168）、§11 验证（182-189）。
- `design-hardware/references/module-cards.md:31-35`：无线类组合检查。
- `design-hardware/references/module-integration.md:250-267`（§8 合并负载/同时性）、`442-449`（C06 蜂窝与 3.3 V 逻辑共用轨）。
- `design-hardware/references/domain-design-details.md:61-66`：DM33–DM35。
- `design-hardware/references/selection/modules-connectors.md:69`：EG915N 脉冲供电摘要。
- `design-hardware/references/engineering-deepdives/topics/d4-wireless-integration.md:187,554`：把 EG915N 2G burst 作为量级参照。
- `design-hardware/references/simulation-measurement.md:135`：蜂窝 burst 电压跌落测量判据。

### 判定

`partial`

### 已覆盖

已覆盖 EG915N 的 VBAT 3.4/3.8/4.5 V、2G 突发 2.0/2.5 A、400 mV 跌落、100 µF 低 ESR、VBAT_RF/BB 分域、1/2 mm 走线、TVS、PWRKEY ≥500 ms，以及“3.3 V 轨不能直接供 3.8 V 蜂窝模组”的组合失败。

### 缺口

- **用户话术/路线**：没有 2G vs LTE Cat 1/Cat 1bis/Cat M/NB-IoT 的选择；没有地区频段、运营商、2G/3G 退网、资费/流量、天线形式的提问模板。
- **必查参数**：只有 2G 突发值；缺 LTE-only 的峰值/平均电流、发射功率等级、频段、灵敏度、RRC 状态功耗、PSM/eDRX。
- **电路组成**：缺 SIM/eSIM（MFF2）电路、SIM ESD/检测/热插拔、USB/UART/PCIe 接口、STATUS/RESET/WAKEUP、天线与共存。
- **参数确定**：缺平均电流/电池寿命、LTE 突发能量、热耗、SIM 电源限流、天线隔离的算例。
- **程序**：缺 AT 命令/USB 拨号、PDP/APN、网络注册、MQTT/HTTPS、断网重连、SIM 热插拔处理。
- **验证**：缺 LTE 频段/功率/灵敏度、运营商入网、CE/FCC/SRRC/PTCRB、SIM/eSIM 兼容、GNSS/Wi-Fi 共存。
- **采购落地**：缺模组完整型号/地区后缀、SIM/eSIM、天线、C 号/库存/SMT 状态核对。

### 动作

`supplement`：保留 RF-03 的电源深内容；新增“蜂窝制式/模组路线”“SIM/eSIM 与接口”“认证与采购”三节（约 80–100 行），并把 2G 数据明确标为“仅 EG915N 2G 条件”。

### 候选型号

- `Quectel EG915N`（首选；现有 RF-03 已读其电源章节，LTE Cat 1bis + 2G fallback，资料完整；需补 LTE-only 电流）。
- `Quectel EC200U-CN`（LTE Cat 1，国内常见，硬件设计资料完整；适合作为 Cat 1 基线）。
- `SIMCom A7670C`（LTE Cat 1，常见，资料完整；注意地区频段/后缀）。
- `Quectel BG95-M3`（LTE Cat M1/NB-IoT/EGPRS，低功耗；适合电池类，需核对运营商支持）。

### 备注

- RF-03 是 E2，且唯一算例是 EG915N 的 2G 突发；2026 年 LTE-only/NB-IoT 项目不能把 2G 值当默认，必须补 LTE-only 数据。
- `w03:112` 已指出“100 µF + ESR ≤0.7 Ω”与 400 mV 跌落存在张力；这是待原厂确认项，不是已解决结论。
- `module-cards.md:33` “不固定某个模组的峰值电容”疑为“峰值电流/电容”笔误；见“需要同步修正”。

---

## M5 GNSS

### 现有内容

- `design-hardware/references/design-cards/wireless/w04-gnss.md:1-194`：RF-04 全卡；§1 范围（37-49）、§2 输入（51-64）、§4 参数（78-98）、§5 Friis 算例（100-116）、§7 逐脚（135-145）、§9 PCB（153-165）、§11 验证（179-186）。
- `design-hardware/references/design-cards/wireless/w02-antenna.md:93`：u-blox 芯片天线 keep-out 5 mm 旁证。
- `design-hardware/references/module-cards.md:31-35`、`domain-design-details.md:61-66`（DM35）。
- `design-hardware/references/module-integration.md:376-389`（§12 天线净空/芯片天线 keep-out）。
- `design-hardware/references/selection/modules-connectors.md:71`：GNSS 有源天线摘要。
- `design-hardware/references/simulation-measurement.md:134,362,364`：C/N0、GNSS 测量与净空。
- `design-hardware/references/failures/f18-antenna-enclosure.md:82`、`f32-enclosure-degrades-rf-and-thermal.md:255`：GNSS 仅在适用边界中出现。

### 判定

`partial`

### 已覆盖

已覆盖有源/无源天线选择、馈线 >10 cm 用有源、LNA NF/增益/Friis 噪声预算、26 dB 输入上限、偏置网络、芯片天线 5 mm keep-out、屏蔽/穿心滤波、C/N0 与冷/温/热启动验证。

### 缺口

- **用户话术/路线**：没有 GNSS vs 蜂窝/Wi-Fi 定位、单频 vs 多频/多系统、普通定位 vs RTK、天线内置 vs 外置的提问模板。
- **必查参数**：缺模组选型参数（通道数、更新率、TTFF、功耗、备份域、PPS、接口）；RF-04 只有天线/NF。
- **电路组成**：缺模组本体、UART/I²C/SPI 接口、PPS、复位、备份电池/超级电容、天线检测/偏置保护、ESD 的完整链路。
- **参数确定**：缺 TTFF/首次定位时间、PPS 精度、备份电流/寿命、天线增益/电缆损耗/灵敏度链路预算的模组级算例。
- **程序**：缺 NMEA/UBX 解析、冷/温/热启动策略、AGPS/星历、PPS 校时、失锁重连。
- **验证**：缺冷启动/温启动/热启动 TTFF、定位精度/圆概率误差、PPS 抖动、蜂窝/Wi-Fi 共存、装壳后 C/N0。
- **采购落地**：缺 u-blox/Quectel/Unicore 模组、天线、备份电池的选型与 C 号核对。

### 动作

`supplement`：保留 RF-04 的天线/NF 深内容；新增“模组选型/接口/PPS/备份/认证采购”两节（约 60–80 行）。

### 候选型号

- `u-blox MAX-M10S`（首选；资料完整、低功耗、多系统，适合作为基线）。
- `u-blox NEO-M8N`（经典、资料完整，尺寸/功耗较大）。
- `Quectel L76K`（国内常见、成本低，资料完整；需核对地区/接口）。
- `ATGM336H`（中科微，低价常见；原厂资料与一致性需更谨慎核对）。

### 备注

- RF-04 是 E2，来源 u-blox UBX-15030289 R03（2019）；方法仍可用，但具体模块/天线参数必须按当前 datasheet 重查。
- RF-04 把“备份电源/RTC”只作为逐脚表一行（§7），没有展开；这是 M6 的交叉缺口。
- u-blox 的 C/N0 44 dBHz、5 mm keep-out、屏蔽 30–40 dB 都是条件值，不能当所有 GNSS 模组的验收门限。

---

## M6 RTC

### 现有内容

- `design-hardware/references/design-cards/power/p14-supercap-backup.md:1-242`：PWR-14；§1 范围（37-51）、§4 步骤 9“RTC 备份单独算”（111-112）、§5 RTC 子算例（142-144）、§6 纽扣电池行（174）、§10 异常状态（210-221）。
- `design-hardware/references/design-cards/mcu/m01-bare-mcu.md:61-63,78,100,168,198,207,213,218,249`：VBAT 备份域、OSC32_IN/OUT、LSE CL ≤7 pF、VBAT 不用电池时接 VDD + 100 nF。
- `design-hardware/references/design-cards/mcu/m02-module-mcu.md:76,133-134,193,215,229`：ESP32-C3 可选 32.768 kHz RTC 晶体（ESR ≤70 kΩ、偏置 5–10 MΩ），RTC 电源脚 0.1 µF。
- `design-hardware/references/design-cards/mcu/m05-crystal.md:41,122-123,161,187,200,234`：32.768 kHz 启动 1–5 s、CL=7 pF/Cs=2 pF → 10 pF、RTC 晶体 ESR/CL 选择。
- `design-hardware/references/engineering-deepdives/topics/d2-clock-system-checklist.md:37-40,53-60,99,166,231-237`：RTC/LSE 的 ppm 预算、启动时间、温度曲线、探头负载、OSC32 复用冲突。
- `examples/x04-crystal.md:109`、`examples/x03-mcu-min.md:181`：LSE 与 RTC/GPIO 互斥、VBAT 悬空导致备份域异常。
- `design-hardware/references/calculations/energy-battery.md` 与 `engineering-deepdives/topics/b2-sleep-current-budget.md`：电池/睡眠预算方法，可用于 RTC 备份电流，但没有 RTC 专项。

### 判定

`partial`

### 已覆盖

已覆盖 RTC 备份能量公式（超级电容/纽扣电池）、32.768 kHz 晶体 CL/ESR/启动时间/ppm 预算、MCU VBAT 备份域接法，以及“µA 级月级备份用纽扣电池更划算”的结论。

### 缺口

- **用户话术/路线**：没有“需要多准（ppm）/断电多久/是否要闹钟/是否要校准/成本”的提问模板；没有 MCU 内部 RTC vs 外部 RTC 芯片 vs GNSS/NTP 授时的选择。
- **必查参数**：缺 RTC 芯片的精度（ppm over temperature）、工作/备份电流、I²C/SPI 地址、闹钟/中断、SRAM、复位/去抖、写保护。
- **电路组成**：缺外部 RTC 芯片 + 32.768 kHz 晶体 + 备份电池/超级电容 + 二极管/ORing + I²C 上拉的完整链路；PWR-14 只讲能量，不讲 RTC 芯片。
- **参数确定**：缺“ppm → 每天/每年秒差”、温度补偿、电池寿命（CR2032 容量/自放电/负载）、备份切换压降的算例。
- **原理图/PCB**：缺 RTC 晶体 guard ring/keepout、远离热源/开关节点、电池座极性/防反、I²C 地址冲突的具体检查。
- **程序**：缺 BCD/Unix 时间转换、闰年、闹钟、校准寄存器、掉电检测、首次上电默认时间。
- **验证**：缺 ppm 测量（频率计/日差）、温度循环、备份切换/保持、电池寿命、I²C 读写/闹钟中断测试。
- **采购落地**：缺 DS3231/PCF8563/RV-3028 等 RTC 芯片、CR2032/CR1220、晶体的选型与 C 号核对。

### 动作

`new`：新写 `m09-rtc.md`（12 节设计卡）；PWR-14 只作为“备份能量”引用，MCU-05/D2 只作为“32.768 kHz 晶体/ppm”引用，不复制。

### 候选型号

- `DS3231SN`（首选；内置 TCXO，精度高，I²C，资料完整；成本/尺寸较大）。
- `PCF8563T`（低成本 I²C RTC，需外部 32.768 kHz 晶体；精度取决于晶体）。
- `RV-3028-C7`（超低功耗、±1 ppm 级，适合纽扣电池长期备份；资料完整）。
- `MCP7940N`（I²C RTC，带 SRAM/唯一 ID，Microchip 资料完整）。

### 备注

- **现有错误**：`p14-supercap-backup.md:159` 写“均衡电阻 2.5 µA 在 10 s 内只掉 25 mV”，但同文件 `:136` 的正确计算是 `25 µC / 1 F = 25 µV`；结论段大了 1000 倍，应改为 25 µV。
- PWR-14 是 E2，RTC 子算例只按恒流 2 µA 估算，没有 RTC 芯片的典型/最大备份电流、电池自放电、切换压降；新卡必须按具体器件重算。
- 不要把“32.768 kHz 晶体”当成 RTC 芯片；MCU 内部 RTC 与外部 RTC 的精度/功耗/校准方法不同。

---

## M7 身份与标签读取

### 现有内容

- 无。全库检索 `NFC`、`RFID`、`13.56`、`MIFARE`、`NTAG`、`ISO14443`、`ISO15693`、`读卡`、`电子标签`、`UHF`、`二维码`、`条码`、`磁条` 均无实质内容。
- 可复用的相邻内容：`design-cards/interfaces/i01-i2c.md`、`i03-spi.md`（读卡器接口）、`w02-antenna.md`（13.56 MHz 天线匹配方法可借部分思路）、`schematic-details.md:52`（SC37 输入异常/保护）、`failures/f18`（天线净空）。

### 判定

`missing`

### 已覆盖

没有覆盖；既没有 NFC/RFID 读卡，也没有 125 kHz LF、UHF RFID、条码/二维码、磁条或 iButton 的内容。

### 缺口

- **用户话术**：没有“读什么标签/距离/是否写卡/是否手机 NFC/是否金属环境/是否要身份级安全”的提问模板。
- **路线选择**：没有 13.56 MHz NFC vs 125 kHz LF vs UHF RFID vs 条码/二维码 vs 磁条的选择；没有读卡器 IC vs 模块 vs 手机 NFC 的取舍。
- **必查参数**：缺读卡器 TX 功率、接收灵敏度、天线 Q/尺寸/失谐、场强、标签类型/容量/安全等级、读距。
- **电路组成**：缺 EMC 滤波、匹配网络、天线线圈、晶振、接收前端、ESD/保护、电源去耦的完整链路。
- **参数确定**：缺天线线圈电感/电容/Q、谐振频率、读距/场强、标签负载调制、功耗的算例。
- **原理图/PCB**：缺线圈 keep-out、地平面/金属影响、天线调谐、ESD、屏蔽与外壳的具体检查。
- **程序**：缺 ISO14443A/B、ISO15693、NDEF、防冲突、密钥/认证、MIFARE Classic 安全边界。
- **验证**：缺读距/标签兼容性、失谐/金属环境、EMI/EMC、写卡寿命、身份级安全评估。
- **采购落地**：缺 PN532/MFRC522/ST25R3916/FM17550、NTAG/IC 卡、天线厂家的选型与 C 号核对。

### 动作

`new`：新写 `i13-nfc-rfid.md`（12 节设计卡）；先锁定 13.56 MHz NFC 读卡，再在“适用范围”里明确 125 kHz/UHF/条码是否另开卡。

### 候选型号

- `PN5321A3HN`（首选；13.56 MHz 多协议读卡器，I²C/SPI/UART，NXP 资料完整，生态成熟）。
- `MFRC522`（低成本 13.56 MHz 读卡器，SPI，资料多但较老；新设计注意生命周期）。
- `ST25R3916-AQWT`（高性能 NFC 读卡器，适合多协议/长距离；资料完整）。
- `FM17550`（国产 13.56 MHz 读卡器，成本低、国内常见；资料/驱动需按原厂核对）。

标签侧可列 `NTAG213/215/216`（ISO14443A-3，NDEF）作为首选标签族；不要写具体 C 号。

### 备注

- MIFARE Classic 的加密已被公开破解，不能当身份级安全方案；新设计优先 NTAG/ISO14443A-3/4 或 DESFire，并在卡内做真正的密钥/证书体系。
- 13.56 MHz 天线是线圈近场，不是 2.4 GHz 的 50 Ω 馈线；RF-02 的 CLC/λg 方法只能借“匹配/净空”思路，不能照抄。
- 金属外壳/电池会显著降低读距；必须把“装壳后读距”列入验收，不能只测裸板。

---

## M8 隔离与数字隔离器

### 现有内容

- `design-hardware/references/module-cards.md:61-65`：第 10 类“隔离、保护与测试”的构成/核算/失效三条组合检查。
- `design-hardware/references/module-integration.md:291-303`：§9 参考地/隔离/屏蔽/回流；隔离屏障行、RS-485/以太网隔离边界。
- `design-hardware/references/domain-design-details.md:82-87`：DM45/DM46（市电/高压/绝缘体系、爬电/间隙、隔离器/变压器）。
- `design-hardware/references/schematic-details.md:53`（SC38 隔离边界）、`pcb-routing-details.md:16`（RT10 隔离全层检查）。
- `design-hardware/references/design-cards/interfaces/i07-rs485.md:53,108,225,242,259`：RS-485 隔离器 + 隔离 DC/DC、传播延时。
- `design-hardware/references/design-cards/interfaces/i08-can.md:54,109,111,147-149,217,234,249,253,277,301`：CAN 隔离延时预算、隔离型收发器、隔离侧地/测试点。
- `design-hardware/references/design-cards/interfaces/i05-uart.md:56,141,218,253`：UART 跨隔离边界、隔离器方向/默认态/耐压、隔离侧地。
- `design-hardware/references/design-cards/interfaces/i12-level-shift.md:51`：电平转换不是隔离。
- `design-hardware/references/design-cards/analog/a07-high-side-sense.md:46,88,113,178,196`：隔离放大器/调制器、隔离侧供电、爬电/间隙。
- `design-hardware/references/design-cards/analog/a08-4-20ma.md:117,156,182,200,207,214,216,232,238`：隔离 4–20 mA 接收器、ISO122 示例、隔离侧供电。
- `design-hardware/references/design-cards/drive/d03-relay.md:51,70,127,159,190,204`：继电器线圈-触点隔离、爬电/间隙。
- `design-hardware/references/engineering-deepdives/topics/c2-grounding-shielding-common-mode.md:47,74,347,363,380,399,406,639,746`：隔离屏障、屏障电容、隔离电源、爬电/间隙。
- `design-hardware/references/calculations/interconnect.md:140`：按间距/爬电/阻焊/标准查走线电压。
- `design-hardware/references/projects/p02-industrial-rs485-analog.md:332,364-365,460`：V2 隔离变体（数字隔离器 + 隔离 DC/DC）未设计。
- `design-hardware/references/examples/x06-rs485.md:110,121`、`x07-can.md:107,159`：隔离边界/隔离延时局部范例。

### 判定

`partial`

### 已覆盖

已把“隔离是整块边界，不只是器件”的原则讲清：SC38/RT10 要求列全跨屏障的铜、孔、测试点、紧固件；RS-485/CAN/UART/4–20 mA/继电器都提示了“隔离器 + 隔离 DC/DC”和传播延时；DM45/46 明确爬电/间隙按标准，不给统一毫米值。

### 缺口

- **用户话术/路线**：没有“是否需要安规隔离/加强绝缘/功能隔离、隔离电压、两侧地电位差、信号速率/方向”的提问模板；没有数字隔离器 vs 光耦 vs 电容/磁耦 vs 隔离收发器/隔离放大器的选择。
- **必查参数**：缺隔离额定（Vrms/Vpeak）、工作电压、瞬态耐受、CMTI、传播延时/脉宽失真/通道间偏斜、默认态/失效态、通道数/方向、两侧电源范围、功耗。
- **电路组成**：缺隔离器 + 隔离 DC-DC（SN6505+变压器/B0505S 模块/ADuM5000）+ 两侧去耦 + ESD/保护 + 默认态拉电阻的完整链路。
- **参数确定**：缺“爬电/间隙按工作电压/污染等级/材料组/海拔”、隔离器延时 vs 比特率、隔离电源功率/效率/纹波的算例。
- **原理图/PCB**：缺隔离屏障下方无铜/无过孔、爬电/间隙、开槽、测试点/调试器不跨屏障、机壳/屏蔽连接的具体检查。
- **程序**：缺默认态/失效态、方向切换、上电顺序、隔离侧未上电时的 I/O 行为、CRC/超时。
- **验证**：缺隔离耐压/绝缘电阻、CMTI、传播延时/偏斜、EMC、长期老化；不能只做“上电能通信”。
- **采购落地**：缺 ISO7721/ADuM1201/Si8621/π122M、隔离 DC-DC、隔离收发器的选型与 C 号核对。

### 动作

`new`：新写 `i14-digital-isolator.md`（12 节设计卡）；SC38/RT10/DM45/46 作为检查入口，I07/I08/A07/A08/D03 作为应用案例，不重复。

### 候选型号

- `ISO7721DR`（首选；TI 双通道 1/1 数字隔离器，5 kVrms，100 Mbps，资料完整）。
- `ADuM1201ARZ`（ADI 双通道 1/1，2.5 kVrms，成熟）。
- `Si8621BB-B-IS`（Silicon Labs 双通道 1/1，2.5 kVrms，150 Mbps）。
- `π122M31`（2Pai Semi 双通道 1/1，3 kVrms，国内常见、成本低；资料需按原厂核对）。

隔离电源可列 `SN6505B` + 变压器、`B0505S-1W` 模块、`ADuM5000` 作为候选，但必须按隔离等级/功率/纹波另选。

### 备注

- 多张现有卡明确写“隔离不在本卡范围”（i07/i08/i05/i12/a07/a08/d03/d04/d08），所以新卡有明确入口，不会与现有内容冲突；但必须在这些卡里加“见 I14”的反向链接。
- 不要给统一爬电/间隙毫米值；必须按 IEC 60664/61010/62368 等适用标准、污染等级、材料组、海拔、工作/瞬态电压查证。
- 数字隔离器不是电平转换器，也不是隔离电源；只加一颗隔离器而不加隔离侧供电，是最常见的“假隔离”。

---

## 复用关系

- **M1/M2**：复用 RF-01（模组供电/EN/strap）、RF-02（2.4 GHz 天线/匹配）、D4（整机/认证/净空）、F18/F25/F03/F32（装壳/发射复位/strap）、X12（布局范例）、P01/P04（BLE/ESP-01S 项目）；电源复用 PWR-01/PWR-02/PWR-05，主控复用 MCU-02。
- **M3**：复用 RF-02 的天线/匹配方法、PWR-01/PWR-02 电源、MCU-02 模组最小系统、MCU-05 晶体、F18/F32 净空/装壳失效；不要复用 2.4 GHz 的 λ/10 与 15 mm 结论。
- **M4**：复用 RF-03（电源）、PWR-01/PWR-02/PWR-05/PWR-10、RF-02（天线）、module-integration C06（3.3 V 轨不能供 3.8 V 蜂窝）、selection/modules-connectors §2.2（EG915N 摘要）。
- **M5**：复用 RF-04（天线/NF/屏蔽）、RF-02（keep-out/馈线）、PWR-01（低噪声 LDO）、MCU-05/D2（RTC/时钟）、D4（整机/认证）、F18（装壳）、simulation-measurement §5/§6（C/N0/VNA/OTA）。
- **M6**：复用 PWR-14（备份能量）、MCU-05（32.768 kHz 晶体）、MCU-01（VBAT 备份域）、D2 §3.4（LSE/ppm/启动）、B2（睡眠电流）、IF-01（I²C RTC）。
- **M7**：复用 IF-01/IF-03（I²C/SPI 读卡器接口）、RF-02（13.56 MHz 天线匹配思路）、SC15/SC37（ESD/输入保护）、PL26/PL27/RT25/RT26（天线净空/馈线）；与 M8 无强耦合。
- **M8**：复用 SC38/RT10（隔离边界）、DM45/DM46（安规/爬电）、module-integration §9（地/隔离/回流）、C2（接地/屏蔽/共模）、I07/I08（隔离收发器）、A07/A08（隔离放大/4–20 mA）、D03（继电器）、P02 V2（隔离变体）。
- **跨组**：M4/M5 与 M1 在“蜂窝/Wi-Fi/GNSS 共存、天线隔离、同时发射”上交叉；M6 与 B 组（低功耗/电池）在备份电流/寿命上交叉；M8 与 E 组（工业接口/电源）在隔离 DC-DC/隔离 RS-485/CAN 上交叉；M7 与“人机/结构”组在金属外壳/读距上交叉。

## 需要同步修正

1. **PWR-14 结论段单位错误（确定）**：`design-hardware/references/design-cards/power/p14-supercap-backup.md:159` 写“2.5 µA 在 10 s 内只掉 25 mV”，同文件 `:136` 的正确计算是 `25 µC / 1 F = 25 µV`。应改为 25 µV；否则 RTC/备份漏电结论被放大 1000 倍。
2. **“35+j0”S11 目标重复传播（需回读原页）**：`w02-antenna.md:90` 已注明来源笔记对“35+j0”的单位/定义记录不完整；`d4-wireless-integration.md:470`、`simulation-measurement.md:80,294,359,668` 仍把它当 ESP32-S3 的 S11 目标。疑似应为“S11 ≤ −35 dB”，必须回读 Espressif RF Tuning 原页后统一；在未确认前，所有文档都应写成“按模组/芯片要求，不能用 35+j0 当门限”。
3. **EG915N 2G 数据的适用范围（过时/边界风险）**：`w03-cellular.md:1-197`、`module-integration.md:442-449`、`d4:187,554` 把 EG915N 的 2G 突发值作为蜂窝默认量级。2026 年 LTE-only/NB-IoT 项目不能套用；应补 LTE-only 峰值/平均电流，并标注“2G/3G 退网按地区/运营商核实”。这不是数值错误，而是默认工作条件过时。
4. **module-cards 第 5 类措辞（编辑修正）**：`module-cards.md:33` “不固定某个模组的峰值电容”疑为“峰值电流/电容”笔误；建议改为“不固定某个模组的峰值电流/电容值”。
5. **不要继续复制“模组认证=整机认证”的旧思路**：D4 已纠正（KDB D04 host 责任）；M1/M4/M5 新内容应统一引用 D4，不要另写“有 FCC ID 就能卖”。
6. **隔离相关卡片的反向链接缺失**：I07/I08/I05/I12/A07/A08/D03/D04/D08 都写“隔离不在本卡范围”，但没有指向一张统一隔离卡；新增 I14 后应在这些卡的“不能使用条件/关联”中各加一行反向链接，避免读者以为全库没有隔离内容。
7. **M7 不存在旧结论可修正**：全库无 NFC/RFID 内容，新增时不要引用“MIFARE Classic 可做身份卡”的旧方案；MIFARE Classic 加密已公开破解，只能做低安全门禁/消费，不应做身份级。

## 文件组织建议

建议“**薄组文件 + 按能力拆分的设计卡**”，不要把 8 个主题塞进一个 800 行大文件：

1. `design-hardware/references/wireless-time-functions.md`（新建，约 120–150 行）
   - §0 用户话术与路线选择（M1–M8 共用决策树，约 45 行）
   - §1 主题地图与卡片索引（约 20 行）
   - §2 跨主题参数/采购/认证总表（约 35 行）
   - §3 验证与常见误判总表（约 25 行）
   - §4 来源与边界（约 15 行）

2. `design-hardware/references/design-cards/wireless/w01-wifi-ble.md`（现有，补约 80–100 行）
   - 新增 §0 路线选择/用户话术（约 30 行）
   - 新增 §13 BLE 专项（约 40 行）
   - 新增 §14 配网/采购/认证接口（约 25 行）
   - 现有 §1–§12 不改，只加交叉链接。

3. `design-hardware/references/design-cards/wireless/w03-cellular.md`（现有，补约 80–100 行）
   - 新增 §13 蜂窝制式/模组路线（约 30 行）
   - 新增 §14 SIM/eSIM 与接口（约 40 行）
   - 新增 §15 认证/采购/产测（约 25 行）

4. `design-hardware/references/design-cards/wireless/w04-gnss.md`（现有，补约 60–80 行）
   - 新增 §13 模组选型/接口/PPS/备份（约 50 行）
   - 新增 §14 认证/采购（约 20 行）

5. `design-hardware/references/design-cards/wireless/w09-subghz.md`（新建，约 180–220 行，12 节）
   - §1 范围/边界、§2 必要输入、§3 拓扑、§4 参数步骤、§5 链路预算算例、§6 选型、§7 逐脚、§8 原理图、§9 PCB、§10 异常、§11 验证、§12 来源；每节约 12–20 行。

6. `design-hardware/references/design-cards/mcu/m09-rtc.md`（新建，约 160–200 行，12 节）
   - 重点：RTC 芯片 vs MCU 内部 RTC、ppm 预算、备份电池/超级电容、I²C/SPI、闹钟/中断、晶体布局、时间同步；每节约 12–18 行。

7. `design-hardware/references/design-cards/interfaces/i13-nfc-rfid.md`（新建，约 180–220 行，12 节）
   - 重点：13.56 MHz NFC 读卡器、天线线圈/匹配、标签类型、协议/安全、读距/金属环境、ESD；每节约 15–20 行。

8. `design-hardware/references/design-cards/interfaces/i14-digital-isolator.md`（新建，约 180–220 行，12 节）
   - 重点：隔离器 vs 光耦、隔离额定/CMTI/延时/默认态、隔离 DC-DC、爬电/间隙、屏障布局、耐压测试；每节约 15–20 行。

9. 索引更新：
   - `design-cards/README.md` 的“无线、显示、音频与存储”表加 W09；
   - 新增/调整“主控、时钟与调试”表加 M09；在“有线接口”表加 I13/I14（或新增“隔离与身份”小节）；
   - `module-cards.md` §5 加 Sub-GHz 链接，§10 加 I14 链接；
   - `SKILL.md` 按需读取表的“具体电源/主控/接口/模拟/驱动/无线电路”行已覆盖设计卡库，无需新增顶层行，但可在“领域易漏项”行旁注明新卡。
