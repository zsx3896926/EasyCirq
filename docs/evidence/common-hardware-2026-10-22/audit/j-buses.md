# J 数字总线与常见有线通信 盘点

> 审计对象：`C:\Users\jlc\work\hardware-design-skill`（当前工作区）。
> 方法：按 `design-hardware/SKILL.md` 的按需读取表定位，再以 Grep 抽查；只读相关段落，未全量加载大文件。
> 口径：判定只针对“常用硬件能力”任务书的 11 问（用户话术、路线选择、必查参数、电路组成、参数确定、原理图、PCB、程序、验证、常见误判、采购落地）是否够用，不代表仓库其他领域质量。
> 路径相对仓库根；行号为当前文件的 1 起始行号。只读审计，未修改任何仓库文件。

---

## J1 I²C 外设

**现有内容**
- `design-hardware/references/design-cards/interfaces/i01-i2c.md` L1–301（整卡）：L39–58 适用范围；L60–77 必要输入；L105–151 上拉区间/`Cb`/漏电/串阻/地址与并联；L153–220 400 kbit/s、5 器件算例；L222–233 选型表；L235–247 逐脚；L249–255 原理图表达；L257–270 PCB；L272–283 异常状态；L285–292 验证；L294–301 来源。
- `design-hardware/references/design-cards/interfaces/i02-i2c-buffer.md` L1–292：L103–149 分段/静态偏移/EN 时序；L150–210 TCA9517 算例；L211–223 选型。
- `design-hardware/references/design-cards/interfaces/i12-level-shift.md` L1–302：L117–164 电平转换判据；L217–230 选型。
- `design-hardware/references/examples/x05-i2c.md` L1–207：15 cm 排线接温湿度传感器；L137–150 常见错误；L152–186 改善与复验。
- `design-hardware/references/failures/f06-i2c-pullup.md` L1–96（上拉过强/过弱）；`failures/f28-i2c-unpowered-device-lockup.md` L1–258（掉电从机拖死总线/9 clock 恢复）。
- `design-hardware/references/engineering-deepdives/topics/d1-interface-combination-constraints.md` L86–189（§2.1–2.8：上拉所有权、`Cb`、ESD 钳位、模式脚、地址 7/8 位、9 clock）；L219–280（§3.2–3.5：I²C 逐网络检查、状态表、地址表）；L300–313（§4.3 `Cb` 预算）；L380–535（§6 算例）；L536–681（§7 故障链）。
- `design-hardware/references/selection/modules-connectors.md` L153–169（§5 传感器选型：精度/漂移/位置/气路）；L182–196（商城检索关键词）。
- `design-hardware/references/projects/p01-low-power-wireless-sensor.md` L87（I²C 温湿度传感器必要条件）；L191–204（I²C 上拉计算）。
- `design-hardware/references/schematic-details.md` L39（SC27）；`module-integration.md` L139–155（上拉/下拉所有权）、L208–215（地址与片选规则）、L397–405（C01 并联上拉）、L478–486（C10 地址冲突）；`calculations/interconnect.md` L122–130（I²C 集总模型）；`simulation-measurement.md` L346（I²C 测量）。

**判定：partial**

**已覆盖：** 一条 I²C 总线的电气设计已经足够直接引用：上拉区间、`Cb`/`tr`、最弱 `IOL`、漏电、串阻代价、地址 7/8 位、并联上拉、缓冲分段、掉电钳位与总线恢复，并有一个 15 cm 排线接传感器的完整范例和两个故障案例。

**缺口（对照 11 问）**
- 用户话术：缺“接个温湿度/EEPROM/IO 扩展/OLED/RTC/多路 ADC/多个相同传感器”到 I²C 外设类别的分流；现有 S03 只覆盖“手机看温湿度”一个应用，P01 的传感器仍是“待选”。
- 路线选择：缺 I²C 外设 vs SPI 外设 vs 模拟传感器+ADC 的判据；缺 EEPROM vs SPI Flash、IO 扩展 vs 移位寄存器、专用传感器 vs 通用 ADC 的取舍。
- 必查参数：缺各类外设自己的关键参数：传感器量程/精度/漂移/响应时间/预热；EEPROM  endurance/retention/页大小/写周期；IO 扩展驱动/中断/上电默认；RTC 备电/精度；I²C ADC 分辨率/速率/基准。
- 电路组成：缺外设支持电路：去耦、地址 strap、WP、INT/ALERT、RESET、EEPROM 写保护、IO 扩展中断上拉、OLED 电荷泵电容。
- 参数确定：缺多器件地址预算与上电扫描表、repeated start/clock stretching 的时序、EEPROM 写等待、传感器转换时间与轮询周期。
- 原理图：缺逐脚表（地址脚、WP、INT、EN、NC）与“同一总线 6–10 个器件”的地址分配示例；现有地址表在 D1 只覆盖 Feather/Crazyflie 两个真实板。
- PCB：只有通用 I²C 布线；缺每个外设的去耦/地址 strap/ESD 相对位置，以及多器件分支的 `Cb` 分配。
- 程序：只有总线恢复思路（F28）和地址 7/8 位；缺探测/读写寄存器/repeated start/clock stretching/CRC、EEPROM 磨损均衡、传感器转换等待。
- 验证：缺外设级验证（传感器与参考表比对、EEPROM 写-读-保持、IO 扩展中断、地址扫描），现有验证集中在总线电气。
- 常见误判：已有“模块自带上拉”“并联上拉”“地址写法”“掉电钳位”；仍缺“固定地址模块无法改地址”“EEPROM WP 悬空导致写保护”“OLED 模块自带电荷泵/稳压”“同一型号不同后缀地址不同”。
- 采购落地：缺具体型号、封装、地址选项、温度等级与模块/裸芯片区分；i01 L301 明写“任何具体 I²C 器件未核对”。

**动作：supplement**（复用 IF-01/IF-02/IF-12、x05、F06/F28、D1；本主题只补“外设类别选择 + 地址/支持电路 + 驱动/验证”，不重抄上拉公式）

**候选型号**
- **首选：SHT40（Sensirion，I²C 温湿度，DFN-4）**：手册完整、常见、地址/CRC/转换时间都有明确条款，适合做“传感器类外设”样板。
- AT24C02C / AT24C256C（Microchip，I²C EEPROM，SOIC-8/TSSOP-8）：页大小、写周期、 endurance 明确，适合做“存储类外设”样板。
- TCA9555（TI，16 位 I²C IO 扩展，INT）：寄存器/中断/上电默认完整，适合做“IO 扩展类”样板。
- ADS1115（TI，16 位 I²C ADC，ALERT/RDY）：适合做“I²C ADC + 基准/输入”边界；若只做数字传感器可不选。
- 具体后缀、封装、地址选项与库存均待按原厂手册/商城核对，不写 C 号。

**备注：** i01 的结论明确限定 Standard/Fast/Fast-mode Plus，且 L301 声明未核对任何具体 I²C 器件；x05 是通用温湿度示例，不是某一型号的实测。P01 的 I²C 传感器仍“待选”，说明“外设型号/地址/精度”正是缺口。未发现 i01/i02/x05 的电气错误。

---

## J2 SPI 外设

**现有内容**
- `design-hardware/references/design-cards/interfaces/i03-spi.md` L1–241：L39–58 适用范围；L60–75 必要输入；L115–152 CPOL/CPHA、帧格式、时序预算、`CS`/三态、电平、电短/电长、串阻；L154–164 25 MHz 读方向反例；L166–177 选型；L179–190 逐脚；L201–212 PCB；L226–233 验证。
- `design-hardware/references/design-cards/interfaces/i04-spi-multi.md` L1–279：L39–58 适用范围；L108–143 拓扑/`MISO` 争用死区/`CS` 默认态/混合电压；L145–201 4 从机算例；L203–214 选型。
- `design-hardware/references/design-cards/interfaces/i12-level-shift.md` L1–302（SPI 单向转换边界）。
- `design-hardware/references/failures/f29-spi-write-ok-read-unstable.md` L1–247（SPI NOR 写正常读不稳定：MISO 采样窗/CS 释放/20 MHz 排线）。
- `design-hardware/references/design-cards/wireless/w05-display.md` L1–208（SPI TFT/背光）；`w07-spi-flash.md` L1–198（W25Q128JV/QSPI/WP/HOLD/QE）；`w08-microsd.md` L1–203（SDIO/SPI、CMD/DAT 上拉、卡检测）。
- `design-hardware/references/selection/modules-connectors.md` L129（microSD 卡座）、L153–169（传感器）、L182–196（检索关键词）。
- `design-hardware/references/schematic-details.md` L40（SC28）；`module-integration.md` L208–215（片选/地址）、L338–375（固件初始化/驱动支持）；`simulation-measurement.md` L347（SPI 测量）。

**判定：partial**

**已覆盖：** SPI 点对点与多从机的电气/时序已经足够直接引用：四种模式、整帧 `CS`、`MISO` 三态与死区、混合电压、电短/电长与串阻代价；并已有 SPI NOR、microSD、SPI TFT 三张器件级卡片和一个“写正常读不稳定”的故障案例。

**缺口（对照 11 问）**
- 用户话术：缺“接 Flash/屏幕/SD 卡/SPI ADC/SPI 传感器/无线模块/多路从机”到路线的生活化分流；S 场景没有 SPI 入口。
- 路线选择：缺 SPI vs I²C vs QSPI/OSPI vs SDIO 的判据；缺“内部 Flash 够不够”“SPI NOR vs microSD vs eMMC”“SPI TFT vs RGB/MIPI”“SPI ADC vs 内部 ADC”的取舍。
- 必查参数：缺外设级参数：Flash endurance/retention/QE/块大小；SD 卡 class/UHS/供电；显示控制器 RAM/接口/背光；ADC 分辨率/速率/基准/输入范围；传感器 FIFO/DRDY。
- 电路组成：缺 Flash 的 WP/HOLD/RESET、SD 卡电源开关/CD/ESD、显示的 RESET/背光/ tearing、ADC 基准/输入缓冲、传感器 DRDY/INT。
- 参数确定：缺吞吐预算（命令开销、DMA、FIFO）、多从机调度与片选译码延时、QSPI/dual/quad 模式下的引脚复用与 `QE`。
- 原理图：缺逐器件引脚表（WP/HOLD/QE、SD CD/CMD 上拉、显示 IM/CS/DC/RST、ADC REFIN/DRDY）；现有 w05/w07/w08 各自有表，但没有“一条 SPI 挂多类外设”的组合表。
- PCB：只有通用 SPI 布线；缺 SD 卡座、显示 FPC、Flash 的专属摆放与 keep-out。
- 程序：缺驱动流程（模式配置、DMA、命令/dummy 周期、擦写轮询、SD 初始化、显示初始化）；F29 只给排查，不给驱动代码。
- 验证：缺外设级验证（Flash 擦-写-读回、SD 热插拔、显示 tearing、ADC 噪声/线性），现有验证偏向时序与眼图。
- 常见误判：已有模式/CS/MISO/混合电压；仍缺“Flash WP/HOLD 悬空”“SD 卡只支持 3.3 V”“显示模块自带稳压/电平转换”“QSPI 需要 QE”“多从机共用 MISO 但某从机无三态”。
- 采购落地：缺具体型号/封装/endurance/温度等级；w07/w08 只覆盖两类，未覆盖 SPI ADC/传感器。

**动作：supplement**（复用 IF-03/IF-04、F29、RF-05/07/08；本主题补“外设类别选择 + 逐器件支持电路 + 驱动/验证”，不重抄 SPI 时序公式）

**候选型号**
- **首选：W25Q128JV（Winbond，SPI/QSPI NOR，SOIC-8）**：已有 E1 卡（RF-07），手册条款完整，适合做“存储类”样板。
- MCP3008（Microchip，8 通道 10 位 SPI ADC，DIP/SOIC）：手册完整、常见，适合做“SPI ADC”样板。
- ADS1118（TI，16 位 SPI ADC，内部基准/温度传感器）：适合做“高分辨率 SPI ADC + 基准”边界。
- ST7789V（Sitronix，SPI TFT 控制器；模组厂多）：已有 RF-05 以该系列为实例，适合做“显示类”样板；具体模组/玻璃/背光待按模组手册核对。
- 具体后缀、封装、QE 默认值、库存待按原厂手册/商城核对，不写 C 号。

**备注：** i03 在 L110、L128、L146、L158 出现“加粗结论句替代公式”的编辑痕迹：§4 第 3 步“时序预算”和第 7 步“串阻上限”现在只有文字判据，没有可直接代入的不等式；§5 算例也只有结论，缺少完整代入。这不是电气错误，但会让读者无法复算。建议在新增 J2 时引用 i03 的结论，同时把缺失的公式补回 i03（见“需要同步修正”）。w07/w08/w05 都是器件级 E1/E2 卡，不能替代“SPI 外设选型”主题。

---

## J3 UART 与串口模块

**现有内容**
- `design-hardware/references/design-cards/interfaces/i05-uart.md` L1–287：L39–58 适用范围；L60–75 必要输入；L104–143 角色/电平/空闲态/波特率误差/串阻/流控缺口/隔离缺口；L145–206 8 MHz/115200 分频反例；L208–218 选型；L222–233 逐脚；L244–254 PCB；L268–275 验证。
- `design-hardware/references/design-cards/mcu/m08-uart-bootloader.md` L1–244：L94–126 ISP 输入/BOOT0；L127–166 STM32F4 算例；L167–179 选型；L180–192 逐脚；L226–234 验证。
- `design-hardware/references/engineering-deepdives/topics/d3-off-board-interfaces.md` L343–354（§3.6 UART TTL 与 RS-232 分开看）。
- `design-hardware/references/projects/p04-usb-mcu-board.md` L139–146（外部 3.3 V USB-TTL 下载，无 USB-UART 桥片）；L147–159（UART 下载测试）。
- `design-hardware/references/projects/p02-industrial-rs485-analog.md` L405–421（USART1 + TIM、Modbus RTU、DE 时序）。
- `design-hardware/references/schematic-details.md` L41（SC29）；`module-integration.md` L338–375（引脚复用/初始化顺序/驱动支持）；`simulation-measurement.md` L348（UART 测量）。
- `design-hardware/references/selection/modules-connectors.md` L182–196（商城检索关键词；没有 USB-UART 桥/串口模块的具体条目）。

**判定：partial**

**已覆盖：** UART TTL 本身已经足够直接引用：TX/RX 交叉、空闲高、电平判据、波特率误差预算、RX 上拉、串阻代价、未用引脚处理；并有 UART bootloader 卡、一个真实 USB-C/ESP8266 板的 UART 下载口，以及 P02 的 Modbus RTU/DE 时序示例。

**缺口（对照 11 问）**
- 用户话术：缺“USB 转串口/蓝牙串口/串口屏/AT 模块/调试口/老设备串口”到路线的分流；S08 只覆盖“收到焊好的板不会烧录”。
- 路线选择：缺 UART TTL vs USB-UART 桥 vs RS-232 vs RS-485 vs 无线串口模组 的判据；缺“原生 USB vs 桥片”“桥片 vs 成品模块”“透传 vs AT 指令”的取舍。
- 必查参数：缺 USB-UART 桥的关键参数（驱动支持、VIO、suspend、DTR/RTS、电流、ESD）；缺串口模组的关键参数（波特率、AT 固件版本、睡眠/峰值电流、天线、认证）。
- 电路组成：缺 USB-UART 桥支持电路（VBUS 检测、3.3 V LDO、ESD、DTR/RTS 自动复位、TX/RX 分压）；缺 AT 模组的电源/EN/RESET/BOOT 电路。
- 参数确定：缺 DTR/RTS 自动下载复位时序、流控预算、模组峰值电流与 bulk 电容；i05 明确把 RTS/CTS/隔离/热插拔标为缺口。
- 原理图：缺桥片/模组逐脚表与 4-pin/6-pin 串口排针的板端/线端视角；p04 只有排针，没有桥片。
- PCB：缺 USB 差分对布线（桥片侧）、模组天线 keep-out/摆放、ESD 位置。
- 程序：缺 AT 指令状态机、环形缓冲、波特率切换、固件升级；P02 只有 Modbus RTU，不能覆盖通用串口模块。
- 验证：缺回环/波特率扫描/误码率、USB 枚举、AT 模组入网/透传、热插拔；i05 §11 只有 UART 电气测量。
- 常见误判：已有 TX/RX 交叉、电平、RX 悬空、波特率；仍缺“USB-UART 模块是 5 V TTL 还是 3.3 V”“DTR/RTS 自动复位接反”“AT 模组峰值电流导致复位”“模组自带稳压反灌”“串口屏/模组可能自带电平转换”。
- 采购落地：缺 CH340/CP2102N/FT232 等桥片与 ESP-AT/HC-05 等模组的型号、封装、驱动与供货边界。

**动作：supplement**（复用 IF-05、MCU-08、D3 §3.6、P04/P02；本主题补“USB-UART 桥 + 无线串口模组 + 自动下载/AT 程序/验证”，不重抄 UART 位时间公式）

**候选型号**
- **首选：CH340C（WCH，USB-UART，SOP-16）**：国内常见、内置晶振、3.3 V/5 V 可选、资料可得；注意驱动/封装后缀与 VIO 接法。
- CP2102N（Silicon Labs，USB-UART，QFN-24/QFN-20）：原厂文档完整，DTR/RTS、VIO、suspend 行为清楚，适合做“可核对”样板。
- FT232RL（FTDI，USB-UART，SSOP-28）：文档最完整、生态成熟，适合做对照；成本/封装较大。
- ESP32-C3-MINI-1（Espressif，Wi-Fi/BLE 模组，可跑 ESP-AT）：适合做“无线串口/AT 模组”样板；模组供电/天线/固件版本需按 Espressif 文档核对。
- 具体后缀、封装、驱动版本、库存待按原厂手册/商城核对，不写 C 号。

**备注：** i05 明确标为 E2，并在 L136–143 把 RTS/CTS、隔离、热插拔列为缺口；这是正确的边界，不应在 J3 里被“补成保证值”。P04 明确“本页没有 USB-UART 桥片”，说明桥片/模块是真实缺口。未发现 i05/m08 的电气错误，但 i05 的“CMOS 0.7/0.3×VCC”只是估算，必须按具体 MCU 手册核对。

---

## J4 RS-232

**现有内容**
- `design-hardware/references/design-cards/interfaces/i06-rs232.md` L1–284：L39–58 适用范围；L60–74 必要输入；L107–148 电荷泵电容/驱动负载/速率；L150–205 MAX3232 算例；L206–218 选型；L220–232 逐脚；L243–254 PCB；L256–267 异常；L269–276 验证。
- `design-hardware/references/engineering-deepdives/topics/d3-off-board-interfaces.md` L299–314（§3.3 RS-232 原理图检查：电荷泵电容、V+/V−、250 kbit/s、DB9 针序待查、器件 ESD≠系统 ESD）；L485（五种接口边界表）；L831–861（§7.5 RS-232 热插拔后无输出排查链）。
- `design-hardware/references/selection/modules-connectors.md` L95–104（§3.2 RS-232 选型表）。
- `design-hardware/references/module-integration.md` L90（MAX3232 的 TTL 侧 5 V 输出能否被 3.3 V MCU 接受）。
- `design-hardware/references/schematic-details.md` L41（SC29）、L44（SC32）；`simulation-measurement.md` 没有 RS-232 专列（只有 RS-485/CAN/USB/Ethernet）。

**判定：partial**

**已覆盖：** 单颗 MAX3232 的电气设计已经足够直接引用：3–5.5 V 单电源、4 个电荷泵电容按供电分档、±5 V 摆幅、250 kbit/s、器件级 ±15 kV HBM、V+/V− 与 TTL 侧交叉；D3 还给了板外 RS-232 的检查项和热插拔排查链。

**缺口（对照 11 问）**
- 用户话术：缺“老设备/PLC/仪器/DB9 调试口/串口屏”到 RS-232 的分流；S 场景没有 RS-232 入口。
- 路线选择：缺 RS-232 vs RS-485 vs USB-UART 的判据；缺 3 线 TX/RX/GND vs 全握手（RTS/CTS/DTR/DSR/DCD/RI）；缺非隔离 vs 隔离。
- 必查参数：缺 DB9 针序/DTE-DCE、null modem 交叉、电缆长度/电容、接收器 ±3 V 门限、摆率、隔离等级、系统级 ESD/浪涌。
- 电路组成：缺 DB9/端子连接器、共模扼流/TVS、隔离型 RS-232（隔离电源+数字隔离）、V+/V− 储能与保护。
- 参数确定：缺最大电缆长度 vs 波特率、容性负载、3 kΩ 驱动负载、Icc/电荷泵建立时间、隔离延时。
- 原理图：缺 DB9 9-pin 映射、DTE/DCE 角色、屏蔽/保护地、null modem 画法；i06 L239 与 D3 L313 都写“针序待查”。
- PCB：缺连接器/保护/隔离屏障/机壳地的具体摆放；i06 只有通用泵电容与 TVS 位置。
- 程序：缺波特率/帧格式/流控/回显；RS-232 本身无协议，但“与老设备对接”需要帧格式与握手约定。
- 验证：缺 null modem 回环、±5 V 波形、长线/高容负载、系统级 ESD/浪涌、隔离耐压；i06 §11 只给 MAX3232 电气验证。
- 常见误判：已有“器件 ESD≠系统 ESD”“电荷泵电容按供电分档”“250 kbit/s 是器件上限”；仍缺“DB9 pin2/3 交换”“RS-232 不是 TTL”“RS-485 电平直接进 RS-232 接收器会损坏”“DB9 公母/DTE-DCE 视角”。
- 采购落地：只有 MAX3232 一个实例；缺 SP3232E/MAX3243/隔离型等替代与封装/温度等级。

**动作：supplement**（复用 IF-06、D3 §3.3、selection §3.2；本主题补“DB9/DTE-DCE/null modem + 隔离/系统 ESD + 替代型号 + 验证”，不重抄 MAX3232 电容表）

**候选型号**
- **首选：MAX3232（TI，3–5.5 V 双电荷泵，SOIC-16/TSSOP-16）**：已有 E1 卡，资料完整、常见、易采购。
- SP3232E（MaxLinear，3.3 V RS-232 收发器）：与 MAX3232 引脚兼容的常见替代，需核对 ESD/摆率/电容分档。
- MAX3243（TI，3 驱动/5 接收，完整握手）：适合做“全握手 DB9”样板。
- ADM3251E（Analog Devices，隔离型 RS-232，集成隔离电源）：适合做“隔离 RS-232”边界；隔离等级/爬电/认证需另核。
- 具体后缀、封装、库存待按原厂手册/商城核对，不写 C 号。

**备注：** i06 L20 与 §12 已明确“连接器针序、系统级 IEC 61000-4-2、隔离型 RS-232、长线/高容负载”未核对；D3 L313 也写 DB9 针序待查。这是本主题最大的真实缺口，不应在 J4 里用“常见 DB9 定义”直接填死。未发现 i06 的电气错误；i06 的 250 kbit/s 已注明是器件上限而非标准上限。

---

## J5 RS-485

**现有内容**
- `design-hardware/references/design-cards/interfaces/i07-rs485.md` L1–323：L39–56 适用范围；L58–75 必要输入；L112–162 端接/偏置/共模/保护/DE 时序；L164–235 16 节点/200 m/115.2 kbit/s 算例；L237–249 选型；L251–264 逐脚；L276–290 PCB；L292–305 异常；L307–314 验证。
- `design-hardware/references/examples/x06-rs485.md` L1–205：100 m/8 节点/115.2 kbit/s；L133–147 常见错误；L149–186 改善/复验。
- `design-hardware/references/failures/f07-rs485-termination.md` L1–98（端接/偏置位置错误）。
- `design-hardware/references/engineering-deepdives/topics/d3-off-board-interfaces.md` L287–298（§3.2 RS-485 检查表）；L600–618（§6.2 100 m/2 V 地差算例）；L734–766（§7.2 长线偶发误码排查链）。
- `design-hardware/references/projects/p02-industrial-rs485-analog.md` L247–263（§4.8 端接/偏置算例）；L405–421（§8 Modbus RTU/DE 时序/寄存器草案）；L422–442（§9 B11–B13 总线测试计划）。
- `design-hardware/references/selection/modules-connectors.md` L84–94（§3.1 RS-485/RS-422/CAN 条件）；`schematic-details.md` L44（SC32）；`simulation-measurement.md` L349（RS-485 测量）。
- `design-hardware/references/module-integration.md` L139–155（上拉/下拉所有权）、L682–758（双板环境监测节点项目样本，含 RS-485 连接表）。

**判定：partial**

**已覆盖：** RS-485 物理层已经足够直接引用：A/B 极性、两端端接、失效保护偏置、共模/隔离、TVS/PTC/串阻、DE/RE 默认态、速率×长度、支线/节点间距；并有完整算例、故障案例和 P02 的 Modbus RTU 工程（含 DE 时序与 B11–B13 测试计划）。

**缺口（对照 11 问）**
- 用户话术：已有 S18/P02 的“工业 RS485/4–20 mA 采集节点”；仍缺“USB 转 485/485 模块/多机总线/Modbus 网关/长线现场”的产品化分流。
- 路线选择：缺收发器选型树（5 V vs 3.3 V、半双工 vs 全双工、非隔离 vs 隔离、内部 fail-safe vs 外部偏置、1/8 U.L.、限摆率、ESD 等级）；缺 RS-485 vs RS-422 vs CAN 的边界（i07 L54 只有一句“不能互代”）。
- 必查参数：缺具体收发器参数：`VOD@RL`、fail-safe 门限、`t_en/t_dis`、共模、ESD、U.L.、隔离等级；缺电缆/连接器参数表。
- 电路组成：缺隔离型方案（数字隔离器+隔离 DC/DC+隔离收发器）、TVS/PTC/共模扼流的具体配合、AC 端接/总线供电变体。
- 参数确定：缺 DE 提前/释放时间与 UART 停止位/中断延迟的预算；缺分数 U.L. 下的偏置重算；缺 TVS 钳位能量与浪涌协调。
- 原理图：缺 MAX485/SP3485/ADM2483 等逐脚表与隔离屏障画法；i07 明确“本卡不写脚号”。
- PCB：已有差分/端接/TVS/隔离/屏蔽的通用要求；缺具体隔离间距、TVS 回路、端子针序的实例。
- 程序：P02 有 Modbus RTU 配置/DE 时序/寄存器草案，但缺通用驱动状态机、CRC、冲突/重试、广播/异常码。
- 验证：P02 有 B11–B13，但全部“未执行”；缺眼图/共模/浪涌/EMC/长期现场。
- 常见误判：已有“每节点都装 120 Ω”“偏置装两处”“A/B 反接”“DE 悬空”“TVS 只看 ESD 等级”；仍缺“5 V 收发器 RO 直接进 3.3 V MCU”“32 U.L. 不是节点数”“内部 fail-safe 与外部偏置叠加”“隔离收发器没有隔离电源”“120 Ω 用在 100 Ω 电缆”。
- 采购落地：缺具体收发器型号/封装/温度等级/隔离等级；selection 只有“MAX485 5V / SP3485 3.3V”两个检索词。

**动作：supplement**（复用 IF-07、x06、F07、D3 §3.2/§6.2、P02；本主题补“收发器选型树 + 隔离/保护变体 + Modbus 驱动/验证 + 采购型号”，不重抄端接/偏置公式）

**候选型号**
- **首选：THVD1450（TI，3.3 V 半双工 RS-485，±18 kV IEC ESD，SOIC-8）**：手册完整、共模/ESD/限摆率条款清楚，适合做“现代 3.3 V 收发器”样板。
- SP3485（MaxLinear，3.3 V 半双工，SOIC-8）：国内常见、便宜，适合做“低成本 3.3 V”对照；需核对 ESD/共模/失效保护。
- MAX485（Analog Devices/Maxim，5 V 半双工，SOIC-8）：经典 5 V 器件，适合做“5 V→3.3 V 电平”反面样板。
- ADM2483（Analog Devices，隔离型 RS-485，集成隔离电源）：适合做“隔离/高共模”边界；隔离等级/爬电/认证需另核。
- 具体后缀、封装、库存待按原厂手册/商城核对，不写 C 号。

**备注：** **发现一处需修正的电气错误**：i07 L208–212 把“24 V 直接加在 A/B 两端”的故障算成“两只 120 Ω 串联，0.1 A，每只 1.2 W，合计 2.4 W”。实际两端各一只 120 Ω 端接在 A/B 之间是**并联**（电缆把两端 A 与 A、B 与 B 连在一起），每只都承受约 24 V，每只 4.8 W、合计 9.6 W；只有“把总线回路断开、两只端接形成唯一串联路径”才是 1.2 W/只。该卡 L231 的结论“1/4 W 不满足”仍成立，但单只功率被低估 4 倍，必须按 x06 L145/L165、D3 L560、F08 L77 的口径统一。另：`selection/modules-connectors.md` L88 的“最多 32 单位负载”应加“32 U.L. 是标准单位负载预算，不是节点数；1/8 U.L. 器件可更多节点”的限定（i07 L50 已有正确说法）。

---

## J6 CAN

**现有内容**
- `design-hardware/references/design-cards/interfaces/i08-can.md` L1–316：L37–56 适用范围；L58–76 必要输入；L113–159 端接/分裂端接/支线/节点间距/共模/隔离延时/保护；L161–227 10 节点/100 m/500 kbit/s 算例；L229–242 选型；L243–257 逐脚；L267–283 PCB；L284–298 异常；L299–307 验证。
- `design-hardware/references/examples/x07-can.md` L1–199：20 m/6 节点/500 kbit/s；L126–140 常见错误；L142–178 改善/复验。
- `design-hardware/references/failures/f08-can-termination.md` L1–100（端接过多/共模问题）。
- `design-hardware/references/engineering-deepdives/topics/d3-off-board-interfaces.md` L271–285（§3.1 CAN 检查表）；L533–598（§6.1 三节点 CAN 算例）；L700–733（§7.1 CAN 台架正常、三板连接失败排查链）；L106–113（VESC/LibreSolar/Pixhawk/BeagleBone 接口清单）。
- `design-hardware/references/engineering-deepdives/casebook/low-power-wireless-battery.md` L212（SN65HVD230/SN65HVD75 共用差分对）、L258（TCAN334 非隔离）；`casebook/motor-power-industrial.md` L81（MCP2551 符号/SN65HVD232 值域不一致，R402 接在 NC 脚）。
- `design-hardware/references/selection/modules-connectors.md` L84–94（§3.1 CAN 条件）；`schematic-details.md` L44（SC32）；`simulation-measurement.md` L350（CAN 测量）；`task-scenarios.md` S22（“增加一路 CAN”）。

**判定：partial**

**已覆盖：** 高速 CAN 物理层已经足够直接引用：两端 120 Ω/分裂端接、支线临界长度、节点间距、共模/屏蔽、隔离延时预算、端接故障功率；并有完整算例、故障案例，以及 VESC/LibreSolar/Pixhawk 三块真实板的位号级证据（含“符号库 MCP2551、值域 SN65HVD232、R402 接 NC 脚”这种高价值教训）。

**缺口（对照 11 问）**
- 用户话术：S22 已覆盖“增加一路 CAN”；仍缺“汽车/电机/BMS/CANopen/CAN FD/隔离 CAN/总线供电”的分流。
- 路线选择：缺高速 CAN vs CAN FD vs 容错 CAN vs 隔离 CAN 的判据；缺“MCU 内置 CAN 控制器 vs SPI CAN 控制器（MCP2515/MCP2518FD）”“5 V 收发器 vs 3.3 V VIO 收发器”“非隔离 vs 隔离”的取舍。
- 必查参数：缺收发器关键参数：环路延时、对称性、`VIO`、STB/EN、ESD、共模、SIC；缺 MCU CAN 控制器的位定时/晶振 ppm/采样点。
- 电路组成：缺 VIO 供电、STB/EN 默认态、分裂端接中点、共模扼流、TVS、隔离电源；缺总线供电（LibreSolar 10–32 V/600 mA）的完整契约。
- 参数确定：缺位定时（prop segment/phase segment/SJW/采样点）、振荡器容差、环路延时预算、CAN FD 数据段时限。
- 原理图：缺 TJA1050/SN65HVD230/TCAN334 等逐脚表与 MCU CAN TX/RX 复用；i08 明确“本卡不写脚号”。
- PCB：已有端接/支线/共模/隔离通用要求；缺隔离屏障、连接器针序、总线供电的实例化。
- 程序：缺 CAN 控制器初始化、位定时、滤波器、TX/RX 队列、错误计数/bus-off 恢复、CANopen；现有 casebook 只有硬件证据。
- 验证：缺 CAN 分析仪/错误计数/眼图/EMC/bus-off 恢复；i08 §11 只有电气测量。
- 常见误判：已有“每节点 120 Ω”“支线过长”“CANH/CANL 反接”“STB 悬空”“TVS 电容”；仍缺“5 V 收发器 RXD 进 3.3 V MCU”“CAN FD 需要不同收发器/对称性”“MCP2515 是 SPI 控制器不是收发器”“符号库名不等于装配料号”（VESC 已给实例）。
- 采购落地：缺具体收发器型号/封装/温度等级/隔离等级；selection 只有“TJA1050”一个检索词。

**动作：supplement**（复用 IF-08、x07、F08、D3 §3.1/§6.1、casebook 真实板证据；本主题补“收发器/控制器选型树 + 位定时/固件 + CAN FD 边界 + 采购型号”，不重抄端接/支线公式）

**候选型号**
- **首选：TCAN334（TI，3.3 V 高速 CAN，SOIC-8/SOT-23-8）**：手册完整、3.3 V 单电源、STB/共模/ESD 条款清楚；LibreSolar 真实板已用。
- SN65HVD230（TI，3.3 V 高速 CAN，SOIC-8）：常见、便宜，带 Rs 斜率控制；VESC/Pixhawk 生态常见。
- TJA1051T/3（NXP，5 V 收发器带 3.3 V VIO，SOIC-8）：适合做“5 V 总线 + 3.3 V 逻辑”样板。
- ISO1042（TI，隔离型 CAN FD 收发器，SOIC-16）：适合做“隔离/CAN FD”边界；隔离电源/等级需另核。
- 具体后缀、封装、库存待按原厂手册/商城核对，不写 C 号。

**备注：** i08 L50 与 §12 明确把 CAN FD/ISO 11898-2:2016/SIC 收发器排除在外；J6 必须显式写“CAN FD 另立主题或标为超出本组范围”，不能把 i08 的 2008 年 SLLA270 数值套到 CAN FD。i08 L182/L221 的“100 m/500 kbit/s 在最坏延时下往返占 82.5%、建议降到 250 kbit/s”是**特定最坏假设**下的结论，不是“100 m/500 k 永远不成立”的通用规则；新增内容应保留条件、不要复制成绝对判据。D3/casebook 的开源板证据是“有人这样设计”，不是保证值。

---

## J7 USB 数据接口

**现有内容**
- `design-hardware/references/design-cards/interfaces/i09-usb-device.md` L1–301：L37–55 适用范围；L57–73 必要输入；L108–149 上拉/串阻/VBUS/短接/时钟；L151–213 1.5 kΩ/27 Ω/短接功率算例；L215–227 选型；L229–242 逐脚；L254–267 PCB；L269–282 异常；L284–292 验证。
- `design-hardware/references/design-cards/interfaces/i10-usbc-data.md` L1–293：L37–55 适用范围；L57–73 必要输入；L111–152 角色/CC/去抖/SBU/IR Drop；L154–205 Sink 算例；L207–219 选型；L221–235 逐脚；L246–260 PCB；L261–276 异常；L277–285 验证。
- `design-hardware/references/examples/x08-usbc.md` L1–214：USB-C Sink、CC 下拉、VBUS、数据保护；L137–151 常见错误；L153–193 改善/复验。
- `design-hardware/references/failures/f09-usbc-cc.md` L1–114（CC 电阻缺失/错误）；`failures/f27-usb-ground-loop-source-conflict.md` L1–212（USB 与外部 5 V 同时接入：地环/ORing 反灌/屏蔽环流）。
- `design-hardware/references/projects/p04-usb-mcu-board.md` L97–119（USB-C/CC 原理图连接基线）；L139–146（固件/启动）；L147–159（首板测试）。
- `design-hardware/references/engineering-deepdives/topics/d3-off-board-interfaces.md` L241–250（§2.8 USB VBUS/上拉契约）；L316–327（§3.4 USB 2.0 FS 检查表）；L800–830（§7.4 USB 加 TVS 后不枚举排查链）。
- `design-hardware/references/selection/modules-connectors.md` L95–104（§3.2 USB/USB-C 条件）；`schematic-details.md` L42–43（SC30/SC31）；`simulation-measurement.md` L351（USB FS 测量）；`module-integration.md` L469–477（C09 两个 USB-C Sink CC 并联）。

**判定：partial**

**已覆盖：** USB 2.0 Full-Speed 设备侧与 USB-C Sink 的电气设计已经足够直接引用：1.5 kΩ 上拉/VBUS 控制、串联终端 28–44 Ω、短接耐受、ESD、CC1/CC2/Rd/Rp、正反插、IR Drop、去抖；并有完整 Sink 算例、CC 故障、USB 地环/反灌故障和一个真实 USB-C 小板。

**缺口（对照 11 问）**
- 用户话术：S02/S20 覆盖“USB-C 供电小板”；仍缺“USB 数据/枚举/USB hub/USB 转串口/USB host/OTG/键盘鼠标”的分流。
- 路线选择：缺 device vs host vs OTG vs hub 的判据；缺 FS vs HS、原生 USB vs USB-UART 桥、Type-C vs micro-B、直连 vs hub 的取舍。
- 必查参数：缺 hub 关键参数（端口数、每端口电流、BC1.2、ESD、时钟、strap）；缺 host 端口电源开关/过流；缺 USB ESD 阵列的电容/钳位/漏电选型表；缺连接器 16/24-pin 映射。
- 电路组成：缺 hub 支持电路（晶振、复位、strap、端口电源开关、ESD）、host 端口电源/过流、USB-C SS lane 映射（i10 只覆盖 CC/SBU/D+/D−）、USB-UART 桥。
- 参数确定：缺 hub 端口功率预算、VBUS 跌落、HS 眼图/阻抗、ESD 电容对眼图的影响；i09/i10 只覆盖 FS/CC。
- 原理图：缺 Type-C 16/24-pin、micro-B、A 口的逐脚表；i10 L54 明确“具体 Rp/Rd 阻值本卡不写”，x08/PWR-12 才给出 5.1 kΩ。
- PCB：已有 FS 差分/ESD/VBUS 通用要求；缺 HS 布线、hub 晶振/端口摆位、连接器屏蔽/固定脚。
- 程序：缺枚举/描述符、hub 配置、USB-UART 驱动、DFU/OTA；P04 只有 ESP8266 启动条件。
- 验证：缺 USB-IF/USB 2.0 一致性、枚举矩阵、host/hub 互操作、ESD/浪涌；现有验证只到 FS 电气与 CC 电压。
- 常见误判：已有“Type-C 外形≠PD”“CC1/CC2 不能短”“VBUS 反灌”“ESD 漏电影响 CC”；仍缺“USB-UART 不是原生 USB”“hub 需要每端口电源开关/过流”“HS 需要 90 Ω 与 45 Ω 端接”“两个 Sink 的 Rd 并联”“Type-C 16-pin 省略 SS 不等于省略 CC”。
- 采购落地：缺 hub/ESD/USB-UART/连接器型号；selection 只有“USB-C sink 5.1 kΩ”一条。

**动作：supplement**（复用 IF-09/IF-10、PWR-12/PWR-13、x08、F09/F27、P04、D3 §3.4；本主题补“hub/host/USB-UART 路线 + 连接器/ESD 选型 + 枚举/一致性验证”，不重抄 FS/CC 公式）

**候选型号**
- **首选：USB2514B（Microchip，4 端口 USB 2.0 Hub，QFN-36）**：手册完整、端口电源/strap/晶振条款清楚，适合做“hub”样板。
- TUSB4041（TI，4 端口 USB 2.0 Hub，QFN）：与 USB2514B 对照；BC1.2/端口电源配置需按手册核对。
- USB2422（Microchip，2 端口 USB 2.0 Hub，QFN-24）：小项目够用，适合做“2 端口”边界。
- USBLC6-2SC6（ST，USB 2.0 ESD 保护，SOT-23-6）：常见、低电容，适合做“USB ESD”样板；需核对 standoff/钳位/电容。
- 具体后缀、封装、库存待按原厂手册/商城核对，不写 C 号。

**备注：** **发现一处需修正的文字/语义错误**：i09 L98 写“全速设备在 D+ 上接 1.5 kΩ 上拉，低全速设备在 D− 上接”，应为“**低速（Low-Speed）设备**在 D− 上接”；L234 的“D− 不得放 1.5 kΩ 上拉（HS-capable 设备）”也应改为“全速/高速能力设备不得在 D− 放 1.5 kΩ；低速设备必须在 D− 放 1.5 kΩ”，否则低速设备会被画错。另：i10 L54 声明“具体 Rp/Rd 阻值本卡不写”，但 x08 L32/PWR-12 已从 ST AN5225/TUSB320 给出 5.1 kΩ/56 kΩ/22 kΩ/10 kΩ；J7 应引用 x08/PWR-12 并注明来源，不要把 i10 的“未提取”误读成“没有可用值”。

---

## J8 以太网

**现有内容**
- `design-hardware/references/design-cards/interfaces/i11-ethernet.md` L1–303：L39–57 适用范围（仅 10/100、单一 DP83822 实例）；L59–76 必要输入；L113–155 MDI/磁性/中心抽头/`RBIAS`/strap/时钟/ESD/屏蔽；L157–213 DP83822 算例；L215–228 选型；L230–243 逐脚；L255–270 PCB；L272–285 异常；L287–294 验证。
- `design-hardware/references/engineering-deepdives/topics/d3-off-board-interfaces.md` L252–260（§2.9 以太网磁性中心抽头/屏蔽）；L328–341（§3.5 10/100 以太网检查表，含 BeagleBone LAN8710A 实例）；L767–799（§7.3 以太网装壳后掉链路排查链）。
- `design-hardware/references/selection/modules-connectors.md` L95–104（§3.2 Ethernet PHY 条件）；`calculations/interconnect.md` L122–130（§3.6 以太网 MDI/阻抗/MII）；`simulation-measurement.md` L352（以太网测量）。
- `design-hardware/references/domain-design-details.md` L52（DM28）；`module-integration.md` L315–337（已集成外围去重，含 PHY/磁性边界）。
- `design-hardware/references/engineering-deepdives/casebook/` 未单独设以太网章节；BeagleBone 证据集中在 D3 L113/L407–411。

**判定：partial**

**已覆盖：** 10/100 PHY 的板级物理层已经足够直接引用：MDI 长度/对内匹配/100 Ω、磁性器件挖空、中心抽头与 `AVD` 同电位、`RBIAS`、strap、25 MHz 时钟、ESD 放 PHY 侧、屏蔽/大地 20 mil+RC 单点；并有 DP83822 的完整算例和 BeagleBone LAN8710A 的真实板证据。

**缺口（对照 11 问）**
- 用户话术：缺“网口/联网/远程/以太网模块/PoE/工业网关”的分流；S03 只走 Wi-Fi，没有有线以太网入口。
- 路线选择：缺 PHY+MAC（RMII/MII）vs MAC+PHY+TCP/IP 模块（W5500）vs SPI 以太网 vs Wi-Fi 的判据；缺 10/100 vs 1G、非 PoE vs PoE 的取舍。
- 必查参数：缺 PHY/MAC 关键参数（RMII/MII/SPI 接口、地址/strap、时钟、LED、中断）；缺变压器匝比/隔离/中心抽头电流、RJ45 内置磁性、PoE class。
- 电路组成：缺 MAC+PHY 模块支持电路（SPI/复位/时钟/RJ45 内置磁性）、变压器中心抽头供电、Bob Smith 端接、PoE 前端（检测/分级/隔离 DC/DC）。
- 参数确定：缺链路预算、RMII 25 MHz/50 MHz 时钟 ppm、变压器中心抽头电流、PoE 功率/隔离。
- 原理图：缺 W5500/LAN8720A 逐脚表与 RJ45 针序/磁性画法；i11 只给 DP83822 的 pin 16 `RBIAS` 实例。
- PCB：已有 MDI 通用要求；缺内置磁性 RJ45 的摆放、Bob Smith、PoE 隔离/爬电、1G 布线。
- 程序：缺 TCP/IP 协议栈、PHY 初始化/strap 读取、link/LED、DHCP/DNS、W5500/lwIP 驱动；现有内容没有协议层。
- 验证：缺 ping/吞吐/link-up、电缆测试、EMC/浪涌、PoE 互操作；i11 §11 只有 PHY 电气与 MDI。
- 常见误判：已有“中心抽头不是随便接 3.3 V”“RBIAS 不能 5.1 kΩ 替 4.87 kΩ”“ESD 放 PHY 侧”“RJ45 内置磁性 vs 分立”；仍缺“W5500 是 MAC+PHY+TCP/IP 不是裸 PHY”“RMII 需要 50 MHz/25 MHz 时钟”“PoE 需要变压器中心抽头电流/隔离”“1G 不能套 100M 的 50 mil”“RJ45 内置磁性却按分立挖空”。
- 采购落地：只有 DP83822 一个实例；缺 W5500/LAN8720A/KSZ8081/变压器/RJ45 的型号与封装。

**动作：supplement**（复用 IF-11、D3 §3.5、calculations/interconnect §3.6；本主题补“PHY vs MAC+PHY 模块路线 + W5500/LAN8720 逐脚 + PoE/Bob Smith 边界 + 协议/验证 + 采购型号”，不重抄 DP83822 的 `RBIAS`/中心抽头数值）

**候选型号**
- **首选：W5500（WIZnet，SPI 转 10/100 以太网，MAC+PHY+TCP/IP，LQFP-48）**：国内极常见、手册完整、SPI 接口对 MCU 友好，适合做“无 MAC 的 MCU 加网口”样板。
- LAN8720A（Microchip，10/100 PHY，RMII，QFN-24）：BeagleBone 已用同系列 LAN8710A，资料完整，适合做“RMII PHY”样板。
- DP83822（TI，10/100 PHY，RMII，QFN-32）：已有 E1 卡，适合做“PHY 逐脚/strap/中心抽头”对照。
- KSZ8081（Microchip，10/100 PHY，RMII，QFN-24）：常见替代，需核对 strap/中心抽头/时钟。
- 具体后缀、封装、变压器/RJ45 型号、库存待按原厂手册/商城核对，不写 C 号。

**备注：** i11 整体 E2，且 L22/L57 明确“DP83822 的 `RBIAS=4.87 kΩ`、中心抽头 3.15–3.45 V/1.71–1.89 V、strap 2.2 kΩ 只适用于该型号”；新增 J8 不得把这些值写成通用值。D3 L113 的 BeagleBone 证据是“TCT_RCT 经 R137 0 Ω 接 VDD_PHYA、C141 22 nF、R136 0.1 Ω 接 ESD_RING”，可作为“中心抽头/屏蔽实例”，但不是所有 PHY 的通用做法。未发现 i11 的电气错误。

---

## 复用关系

- **J1 → 现有卡**：IF-01/IF-02/IF-12、x05、F06/F28、D1 §2–§7、SC27、module-integration §4.3/§6.3。J1 只补“外设类别/地址/支持电路/驱动”，上拉公式与 `Cb` 预算全部引用 IF-01，不重写。
- **J1 → 其他组**：I²C 温湿度/压力传感器的量程、精度、气路复用 ANA-10（RTD/热敏）与 selection §5；若用 I²C ADC，采样/基准复用 ANA-04/ANA-05；I²C OLED 的显示驱动复用 L 组显示主题，J1 只写地址/上拉/电荷泵边界。
- **J2 → 现有卡**：IF-03/IF-04、F29、RF-05（SPI TFT）、RF-07（SPI NOR）、RF-08（microSD）、SC28。J2 只补“外设类别/多器件组合/驱动”，SPI 模式/时序公式引用 IF-03/IF-04。
- **J2 → 其他组**：SPI ADC 复用 ANA-04 的采样/基准；SPI 显示的背光/亮度复用 L 组；SPI Flash 的 QSPI 启动复用 MCU-04/MCU-08 的 strap/启动内容。
- **J3 → 现有卡**：IF-05、MCU-08、D3 §3.6、P04/P02、SC29。J3 只补“USB-UART 桥/无线串口模组/AT 程序”，UART 位时间/电平判据引用 IF-05。
- **J3 → 其他组**：USB-UART 桥的 USB 侧复用 J7 的 USB 设备/ESD 内容；无线串口模组复用 RF-01（Wi-Fi/BLE）的模组供电/天线/认证；RS-232/RS-485 成品模块分别引用 J4/J5。
- **J4 → 现有卡**：IF-06、D3 §3.3、selection §3.2、SC29/SC32。J4 只补“DB9/DTE-DCE/null modem/隔离/系统 ESD”，MAX3232 电容表引用 IF-06。
- **J4 → 其他组**：隔离/保护复用 SC15/SC38 与 E 组连接器/隔离内容；RS-232 电平转换若用分立方案，复用 IF-12 的电平判据。
- **J5 → 现有卡**：IF-07、x06、F07、D3 §3.2/§6.2、P02、SC32。J5 只补“收发器选型/隔离/Modbus 驱动/采购”，端接/偏置公式引用 IF-07。
- **J5 → 其他组**：4–20 mA 采集复用 ANA-08 与 P02 §4；隔离电源/数字隔离复用电源组与 SC38；电机/变频器现场的 RS-485 复用 E 组接地/屏蔽。
- **J6 → 现有卡**：IF-08、x07、F08、D3 §3.1/§6.1、SC32。J6 只补“收发器/控制器选型/位定时/固件/CAN FD 边界”，端接/支线公式引用 IF-08。
- **J6 → 其他组**：电机驱动板上的 CAN 复用 DRV 组/P03；BMS/电池设备的 CAN 复用 B 组电源/电池内容；隔离 CAN 复用 SC38 与 E 组隔离。
- **J7 → 现有卡**：IF-09/IF-10、PWR-12/PWR-13、x08、F09/F27、P04、SC30/SC31。J7 只补“hub/host/USB-UART/连接器/一致性”，FS/CC 公式引用 IF-09/IF-10。
- **J7 → 其他组**：USB 端口电源/限流复用 PWR-05/PWR-11；USB-C 受电/供电复用 PWR-12/PWR-13；USB 地环/屏蔽复用 C2 与 E 组。
- **J8 → 现有卡**：IF-11、D3 §3.5、calculations/interconnect §3.6、DM28。J8 只补“W5500/LAN8720 路线/PoE/Bob Smith/协议”，DP83822 的 `RBIAS`/中心抽头引用 IF-11。
- **J8 → 其他组**：W5500 的 SPI 侧复用 J2 的 SPI 总线/片选；PoE 复用电源组与 E4 连接器可靠性；RJ45/变压器机械/隔离复用 E 组。
- **全组共用**：SC25–SC32、module-integration §4/§6/§7/§11、simulation-measurement §6.3、lcsc-sourcing、part-selection；不重复写“网表连通≠电气正确”“DNP≠NC”等总则。

---

## 需要同步修正

1. **`design-hardware/references/design-cards/interfaces/i07-rs485.md` L208–212、L231（电气错误，MAJOR）**
   - 原结论：“24 V 直接加在 A/B 两端，端接两只 120 Ω 串联承受 24 V；I=0.1 A；每只 1.2 W，合计 2.4 W。”
   - 问题：两端各一只 120 Ω 端接在 A/B 之间是并联，不是串联；每只都承受约 24 V，每只 4.8 W、合计 9.6 W。只有“总线回路被断开、两只端接构成唯一串联路径”才是 1.2 W/只。
   - 建议改法：把故障模型拆成三种并写明条件：(a) 24 V 加在 A/B 且两端端接 → 并联，每只 4.8 W、合计 9.6 W；(b) 只有一只端接 → 4.8 W；(c) 回路断开、两只端接串联 → 每只 1.2 W、合计 2.4 W。功率选型按 (a) 的最坏情况，除非设计能证明故障模型不是 (a)。与 x06 L145/L165、D3 L560、F08 L77 统一。
2. **`design-hardware/references/engineering-deepdives/topics/d3-off-board-interfaces.md` L129 与 L527/L618（内部不一致，MAJOR）**
   - L129 仍写“RS-485 共模 −7…+12 V；同样是 2 V，负方向还剩 5 V”，这是把地差直接当共模、直接扣规范负端。
   - L527/L618 已明确“地差不是共模本身；按 `VCM_TX + GND_TX − GND_RX` 的完整包络计算，不能由地差直接扣接收范围负端”。
   - 建议改法：把 L129 改成“仅作数量级对比；实际按 §6.2 的发送共模+地差包络计算”，并删除“还剩 5 V”的确定性表述；否则读者会拿 2 V 地差直接判“RS-485 一定够”。
3. **`design-hardware/references/design-cards/interfaces/i09-usb-device.md` L98、L234（文字/语义错误，MAJOR）**
   - L98 “全速设备在 D+ 上接 1.5 kΩ 上拉，低全速设备在 D− 上接”应为“全速设备在 D+ 上接 1.5 kΩ 上拉，**低速（Low-Speed）设备**在 D− 上接”。
   - L234 “D− 不得放 1.5 kΩ 上拉（HS-capable 设备）”应改为“全速/高速能力设备不得在 D− 放 1.5 kΩ；**低速设备必须在 D− 放 1.5 kΩ**”。否则低速设备会被画错。
4. **`design-hardware/references/design-cards/interfaces/i03-spi.md` L110、L128、L146、L158（编辑回退/可复算性，MINOR–MAJOR）**
   - §4 第 3 步标题是“时序预算（核心）”，但只剩文字判据，没有可代入的不等式；第 7 步标题是“串阻上限公式”，但公式被一段“串阻上限仅可从……”替代；§5 算例也缺完整代入。
   - 建议改法：至少恢复读方向 `T/2 ≥ tCLK_forward + tCO_slave(max) + tMISO_return + tSU_master + jitter/skew`、写方向相对偏斜、保持 `tH` 用 `tCO(min)`、串阻 `1.2·Rs·C_L ≤ 剩余建立余量` 这四条可复算关系，并保留“数值必须按实际手册替换”的限定。
5. **`design-hardware/references/selection/modules-connectors.md` L88（旧建议/易误读，MINOR）**
   - 原句“RS-485 | 最多 32 单位负载”容易被读成“最多 32 个节点”。建议改为“32 U.L. 是标准单位负载预算，不是节点数；1/8、1/4 U.L. 收发器可挂更多节点，偏置/电容/失效保护须按型号重算”。i07 L50 已有正确说法，应同步到 selection。
6. **`design-hardware/references/design-cards/interfaces/i10-usbc-data.md` L54 与 `examples/x08-usbc.md` L32、`design-cards/power/p12-usbc-sink.md`（跨卡口径，MINOR）**
   - i10 写“具体 `Rp`/`Rd` 阻值本次未能从规范文本层提取，本卡不写”；x08/PWR-12 已从 ST AN5225/TUSB320 给出 5.1 kΩ、56 kΩ/22 kΩ/10 kΩ。两者不是矛盾，但读者会以为“没有可用值”。
   - 建议改法：i10 增加一句“5.1 kΩ 等具体值见 PWR-12/x08，来源为 ST AN5225 Table 6/TUSB320，不是从 Type-C 规范文本层提取；使用前仍按规范图表/CC 控制器手册核对”。
7. **`design-hardware/references/design-cards/interfaces/i08-can.md` L182、L221（结论条件需保留，MINOR）**
   - “100 m/500 kbit/s 在最坏收发器/控制器延时下往返占 82.5%，建议降到 250 kbit/s”是特定最坏假设下的结论，不是“100 m/500 k 永远不成立”。建议在 L182/L221 明确“若实际收发器/控制器延时和采样点更优，须用实际值重算；不要把这句当成通用降速规则”。
8. **`design-hardware/references/design-cards/interfaces/i06-rs232.md` L20/L282 与 D3 L313（缺口标注需保持，MINOR）**
   - 两张卡都已写“DB9 针序、系统级 IEC 61000-4-2、隔离型 RS-232、长线/高容负载未核对”。新增 J4 时不要用“常见 DB9 2/3/5”直接填死；应把针序列为阻断项，按对端手册/连接器图纸核对。
9. **`design-hardware/references/design-cards/interfaces/i11-ethernet.md` L22/L57/L222（单型号外推风险，MINOR）**
   - 卡内已声明 DP83822 的 `RBIAS=4.87 kΩ`、中心抽头 3.15–3.45 V/1.71–1.89 V、strap 2.2 kΩ 只适用该型号；但 selection §3.2 L103 仍把 `RBIAS=4.87 kΩ±1%` 与“中心抽头与 AVD 同电位”写成 Ethernet PHY 的通用条件。建议在 selection 该行加“DP83822 实例，换 PHY 必须重查”。
10. **根 `README.md`、`design-hardware/SKILL.md` 的按需读取表与测试契约（结构性，MINOR）**
    - 当前没有 `common-hardware/` 目录，也没有 J 组路由；新增组文件后需同步 `README.md`/`SKILL.md` 的路由与 `tests/test_common_hardware.py` 的 13 组契约，否则机械检查会漏。

---

## 文件组织建议

**建议一个组文件，不按主题拆成 8 个 references 文件。**

- 主文件：`design-hardware/references/common-hardware/j-buses.md`，约 **1200–1350 行**。
- 结构按 authoring-guide 的 12 个三级标题，每个主题前加 1–3 行“结论先行”和一行证据标签；已有设计卡用链接引用，不复制整段理论。
- 建议行数分配：
  - `## 0. 本组怎么用`：30–40 行（用户话术 → 先判断什么 → 推荐路线 → 读哪个主题；含“先区分 TTL/RS-232/RS-485/CAN/USB/以太网，不要被‘串口/总线’名字骗”）。
  - `## J1 I²C 外设`：140–160 行（复用 IF-01/IF-02/x05/F06/F28；新增外设类别表、地址预算、EEPROM/IO 扩展/传感器支持电路、驱动/验证）。
  - `## J2 SPI 外设`：130–150 行（复用 IF-03/IF-04/RF-05/07/08/F29；新增外设类别表、多器件组合、Flash/SD/显示/ADC 支持电路、驱动/验证）。
  - `## J3 UART 与串口模块`：150–170 行（复用 IF-05/MCU-08/D3 §3.6；新增 USB-UART 桥、无线串口模组、DTR/RTS 自动下载、AT 程序、验证/采购）。
  - `## J4 RS-232`：100–120 行（复用 IF-06/D3 §3.3；新增 DB9/DTE-DCE/null modem、隔离/系统 ESD、替代型号、验证）。
  - `## J5 RS-485`：150–170 行（复用 IF-07/x06/F07/D3/P02；新增收发器选型树、隔离/保护变体、Modbus 驱动、验证/采购）。
  - `## J6 CAN`：140–160 行（复用 IF-08/x07/F08/D3/casebook；新增收发器/控制器选型、位定时/固件、CAN FD 边界、验证/采购）。
  - `## J7 USB 数据接口`：160–180 行（复用 IF-09/IF-10/PWR-12/13/x08/F09/F27；新增 hub/host/USB-UART、连接器/ESD、枚举/一致性、采购）。
  - `## J8 以太网`：150–170 行（复用 IF-11/D3 §3.5/interconnect；新增 W5500/LAN8720 路线、PoE/Bob Smith、协议/验证、采购）。
  - `## 本组来源`：50–60 行（CHW-S 编号、文档号/版本、实际读到的章节、支持的结论、不能推广的部分、URL）。
- 作者阶段可按 authoring-guide 拆成 `scratch/groups/j/00-intro.md`、`j1-i2c.md` … `j8-ethernet.md`、`99-sources.md`、`99-fixes.md`，集成时按顺序拼接；**最终 references 只保留一个 `j-buses.md`**，避免 README 路由、测试契约和“13 组”结构复杂化。
- 若单文件超过约 1500 行或审阅困难，次选是拆成 `j-buses-a.md`（J1–J4）与 `j-buses-b.md`（J5–J8），但需要同步修改测试/路由；默认不这样拆。

---

## 审计边界

- 本次只做审计，未修改任何仓库文件。
- 所有“候选型号”只用于建议深入核对，不代表已验证库存、价格、C 号、封装或 SMT 可贴状态。
- 现有卡片的证据等级（E1/E2）沿用卡内声明；本审计不把 E2 内容升级为 E1。
- 未执行任何 EDA、仿真、样机或实测；所有“验证”建议均需在真实工程中另行执行。
