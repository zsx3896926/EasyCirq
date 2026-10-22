# 可复用电路设计卡库

> 60 张按任务读取的设计卡。每张包含用途/边界、必要输入、拓扑、参数步骤、完整算例、选型、逐脚核对、原理图表达、PCB 要求、异常状态、验证办法和来源。
> 卡片不是已验证的器件库：具体阻容、脚号、层数和线宽只在所写条件下成立；换芯片/换板必须重新核对。
> 证据等级 `E1` 本次已核对原厂资料；`E2` 通用方法，具体值仍须按型号手册核对；`E3` 仅有离线分析/推断，不得当保证值。

共 60 张；证据分布：E1 42，E2 18。

## 目录

- 按领域索引
- 使用顺序

## 按领域索引

### 电源、充电与保护（14 张）

| ID | 卡片 | 证据 | 关联检查 | 文件 |
|---|---|---|---|---|
| PWR-01 | LDO 线性稳压 | E1 | SC12, SC14, SC18, PL16, RT01 | [p01-ldo.md](power/p01-ldo.md) |
| PWR-02 | Buck 降压变换器 | E1 | SC13, PL09, PL10, PL11, PL12, RT01, RT04 | [p02-buck.md](power/p02-buck.md) |
| PWR-03 | Boost 升压变换器 | E1 | SC13, PL09, PL10, PL11, RT01, RT04 | [p03-boost.md](power/p03-boost.md) |
| PWR-04 | Buck-Boost / SEPIC / 四开关 | E1 | SC09, SC13, PL09, PL10, RT01 | [p04-buck-boost.md](power/p04-buck-boost.md) |
| PWR-05 | 多源供电与电源路径 | E2 | SC10, SC11, SC14, SC17, PL15, RT06 | [p05-power-mux.md](power/p05-power-mux.md) |
| PWR-06 | 单节锂电线性充电 | E1 | SC17, SC18, PL16, MF16 | [p06-linear-charger.md](power/p06-linear-charger.md) |
| PWR-07 | 开关充电与 Power Path | E2 | SC09, SC17, PL09, PL16 | [p07-switching-charger.md](power/p07-switching-charger.md) |
| PWR-08 | 1S 电池保护与 BMS | E2 | SC17, SC18, PL16, DM13 | [p08-battery-protection.md](power/p08-battery-protection.md) |
| PWR-09 | 反接保护 | E1 | SC16, PL15, RT01 | [p09-reverse-polarity.md](power/p09-reverse-polarity.md) |
| PWR-10 | 热插拔与浪涌限制 | E1 | SC16, SC15, PL15, RT01 | [p10-hot-swap.md](power/p10-hot-swap.md) |
| PWR-11 | 保险丝 / eFuse / 限流 | E2 | SC15, PL15, RT01 | [p11-efuse.md](power/p11-efuse.md) |
| PWR-12 | USB-C 5V Sink | E1 | SC30, SC31, PL15, DM29 | [p12-usbc-sink.md](power/p12-usbc-sink.md) |
| PWR-13 | USB-C 5V Source / OTG | E2 | SC30, SC10, PL15, DM29 | [p13-usbc-source.md](power/p13-usbc-source.md) |
| PWR-14 | 超级电容 / RTC 备份 / 掉电保持 | E2 | SC09, SC11, SC18, RT06 | [p14-supercap-backup.md](power/p14-supercap-backup.md) |

### 主控、时钟与调试（8 张）

| ID | 卡片 | 证据 | 关联检查 | 文件 |
|---|---|---|---|---|
| MCU-01 | 裸 MCU 最小系统（STM32 类） | E1 | SC19, SC22, SC23, SC24, SC25, PL17, PL18 | [m01-bare-mcu.md](mcu/m01-bare-mcu.md) |
| MCU-02 | 模组最小系统（ESP32 类） | E1 | SC19, SC20, SC24, PL17, PL26 | [m02-module-mcu.md](mcu/m02-module-mcu.md) |
| MCU-03 | 复位与电源监控 | E1 | SC22, SC14, PL17 | [m03-reset-supervisor.md](mcu/m03-reset-supervisor.md) |
| MCU-04 | 启动与配置脚 | E1 | SC20, SC21, SC25 | [m04-boot-strap.md](mcu/m04-boot-strap.md) |
| MCU-05 | 晶体振荡器 | E1 | SC23, PL19, RT24 | [m05-crystal.md](mcu/m05-crystal.md) |
| MCU-06 | 外部时钟 / 振荡器输入 | E2 | SC23, PL19, RT24 | [m06-external-clock.md](mcu/m06-external-clock.md) |
| MCU-07 | SWD / JTAG 调试与救援 | E1 | SC24, SC25, SC40 | [m07-swd-jtag.md](mcu/m07-swd-jtag.md) |
| MCU-08 | UART Bootloader / ISP | E1 | SC24, SC29, SC20 | [m08-uart-bootloader.md](mcu/m08-uart-bootloader.md) |

### 有线接口（12 张）

| ID | 卡片 | 证据 | 关联检查 | 文件 |
|---|---|---|---|---|
| IF-01 | I²C 总线 | E1 | SC27, SC26, PL15, RT19 | [i01-i2c.md](interfaces/i01-i2c.md) |
| IF-02 | I²C 缓冲 / 中继 / 电平转换 | E2 | SC27, SC26, RT19 | [i02-i2c-buffer.md](interfaces/i02-i2c-buffer.md) |
| IF-03 | SPI 点对点 | E1 | SC28, SC26, RT11, RT20 | [i03-spi.md](interfaces/i03-spi.md) |
| IF-04 | SPI 多从机 / 片选 | E2 | SC28, SC25, PL29 | [i04-spi-multi.md](interfaces/i04-spi-multi.md) |
| IF-05 | UART TTL | E2 | SC29, SC26, SC40 | [i05-uart.md](interfaces/i05-uart.md) |
| IF-06 | RS-232 | E1 | SC29, SC15, PL15, DM27 | [i06-rs232.md](interfaces/i06-rs232.md) |
| IF-07 | RS-485 | E1 | SC32, SC15, SC38, PL15, RT18 | [i07-rs485.md](interfaces/i07-rs485.md) |
| IF-08 | CAN | E1 | SC32, SC15, SC38, PL15 | [i08-can.md](interfaces/i08-can.md) |
| IF-09 | USB 2.0 Full-Speed Device | E1 | SC31, SC30, PL15, RT11, RT12 | [i09-usb-device.md](interfaces/i09-usb-device.md) |
| IF-10 | USB-C 数据与 CC | E1 | SC30, SC31, SC40, DM29 | [i10-usbc-data.md](interfaces/i10-usbc-data.md) |
| IF-11 | 10/100 Ethernet PHY | E2 | SC32, PL28, RT11, RT12, DM28 | [i11-ethernet.md](interfaces/i11-ethernet.md) |
| IF-12 | 电平转换选型 | E1 | SC26, SC27, PL15 | [i12-level-shift.md](interfaces/i12-level-shift.md) |

### 模拟与传感（10 张）

| ID | 卡片 | 证据 | 关联检查 | 文件 |
|---|---|---|---|---|
| ANA-01 | 电阻分压采样 | E1 | SC34, SC37, PL21, RT21 | [a01-divider.md](analog/a01-divider.md) |
| ANA-02 | 运放缓冲 / 同相放大 | E1 | SC33, PL22, RT22 | [a02-opamp-buffer.md](analog/a02-opamp-buffer.md) |
| ANA-03 | 差分放大 | E1 | SC33, SC36, PL21, RT21 | [a03-diff-amp.md](analog/a03-diff-amp.md) |
| ANA-04 | SAR ADC 驱动 | E1 | SC34, SC35, PL23, RT21 | [a04-adc-driver.md](analog/a04-adc-driver.md) |
| ANA-05 | 电压基准 | E1 | SC35, PL23, RT23 | [a05-vref.md](analog/a05-vref.md) |
| ANA-06 | 低侧电流采样 | E1 | SC36, PL14, RT07 | [a06-low-side-sense.md](analog/a06-low-side-sense.md) |
| ANA-07 | 高侧电流采样 | E2 | SC36, SC33, PL14, RT07 | [a07-high-side-sense.md](analog/a07-high-side-sense.md) |
| ANA-08 | 4–20 mA 输入 | E2 | SC37, SC38, PL21, DM22 | [a08-4-20ma.md](analog/a08-4-20ma.md) |
| ANA-09 | 桥式传感器前端 | E2 | SC33, SC36, PL21, DM22 | [a09-bridge.md](analog/a09-bridge.md) |
| ANA-10 | RTD / 热敏电阻测量 | E2 | SC33, SC36, PL24, DM22 | [a10-rtd-thermistor.md](analog/a10-rtd-thermistor.md) |

### 驱动与执行（8 张）

| ID | 卡片 | 证据 | 关联检查 | 文件 |
|---|---|---|---|---|
| DRV-01 | 低侧开关 | E1 | SC21, SC39, PL13, RT09 | [d01-low-side.md](drive/d01-low-side.md) |
| DRV-02 | 高侧开关 | E1 | SC21, SC39, PL13, RT09 | [d02-high-side.md](drive/d02-high-side.md) |
| DRV-03 | 继电器驱动 | E1 | SC21, SC39, PL16, DM20 | [d03-relay.md](drive/d03-relay.md) |
| DRV-04 | 半桥 | E1 | SC21, SC39, PL11, PL13, RT09 | [d04-half-bridge.md](drive/d04-half-bridge.md) |
| DRV-05 | H 桥 / 有刷电机 | E1 | SC21, SC39, PL13, PL14, RT09 | [d05-h-bridge.md](drive/d05-h-bridge.md) |
| DRV-06 | 步进电机驱动 | E2 | SC21, SC39, PL13, PL16 | [d06-stepper.md](drive/d06-stepper.md) |
| DRV-07 | LED 恒流驱动 | E1 | SC21, SC39, PL16, DM41 | [d07-led-cc.md](drive/d07-led-cc.md) |
| DRV-08 | 加热器控制 | E1 | SC21, SC39, PL16, DM44 | [d08-heater.md](drive/d08-heater.md) |

### 无线、显示、音频与存储（8 张）

> 显示/音频卡位于 `wireless/` 是历史归类；HMI 的用户话术、选屏/触摸/按键/蜂鸣器内容见 [常用硬件 L 组](../common-hardware/l-hmi.md)。

| ID | 卡片 | 证据 | 关联检查 | 文件 |
|---|---|---|---|---|
| RF-01 | Wi-Fi / BLE 模组 | E1 | SC09, SC20, PL26, PL27, DM33 | [w01-wifi-ble.md](wireless/w01-wifi-ble.md) |
| RF-02 | 天线接口与匹配 | E1 | PL26, PL27, RT25, RT26 | [w02-antenna.md](wireless/w02-antenna.md) |
| RF-03 | 蜂窝模组电源 | E2 | SC09, SC16, PL26, DM33 | [w03-cellular.md](wireless/w03-cellular.md) |
| RF-04 | GNSS 模组 | E2 | SC37, PL26, PL27, DM35 | [w04-gnss.md](wireless/w04-gnss.md) |
| RF-05 | SPI TFT 显示与背光 | E1 | SC40, PL07, PL16, DM39 | [w05-display.md](wireless/w05-display.md) |
| RF-06 | Class-D 音频功放 | E1 | SC39, PL16, RT22, DM38 | [w06-classd.md](wireless/w06-classd.md) |
| RF-07 | SPI NOR Flash | E1 | SC25, SC28, PL20, DM31 | [w07-spi-flash.md](wireless/w07-spi-flash.md) |
| RF-08 | microSD 接口 | E1 | SC25, SC28, SC40, DM31 | [w08-microsd.md](wireless/w08-microsd.md) |

## 使用顺序

1. 先读任务对应的 1-2 张卡，不要全量加载。
2. 用第 2 节列必要输入；缺失的阻断项先补，非阻断项可写带条件的假设。
3. 按第 4 节顺序计算，用第 5 节算例对照量级；具体器件值回到手册核对。
4. 原理图/PCB 阶段引用第 7-9 节和现有 SC/PL/RT/MF 检查 ID。
5. 第 11 节只写实际做过的工具检查/仿真/测量；未执行标 `未执行`。
