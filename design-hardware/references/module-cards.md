# 按功能组合的模块设计卡

本文件是“模块怎么组合”的入口，不是已验证拓扑或可直接套用的器件库。每类保留三条组合检查；具体的用途边界、必要输入、计算顺序、完整算例、选型、逐脚核对、原理图/PCB 要求和验证办法，按需读取 [设计卡库](design-cards/README.md)。

> 组合两个各自正常的模块仍可能失败：上拉并联、电压域、启动脚、供电状态、引脚复用、连接器视角和返回路径都要在组合后重新核对。跨模块检查见 [组合与接口契约](module-integration.md)。

## 1. 主控与可编程逻辑
- **构成：** 按完整型号区分模组、裸芯片、SOM；核对各电源/参考/内部稳压相关脚、去耦、启动配置、复位、时钟、下载、外部存储。
- **核算：** 核心/IO/无线动态电流、电源时序、GPIO/复用/启动状态、bank 电压及专用脚、可用调试与时钟资源。先分配受约束功能再普通 GPIO。
- **失效与 PCB：** 外设拖偏 strap、Flash/PSRAM 占脚、EPAD 连接、配置失败、去耦高频回路。不要把某个 STM32/ESP32 型号的 RC 与脚号推广到全家族。
- **深入：** [裸 MCU](design-cards/mcu/m01-bare-mcu.md)、[模组 MCU](design-cards/mcu/m02-module-mcu.md)、[复位](design-cards/mcu/m03-reset-supervisor.md)、[启动脚](design-cards/mcu/m04-boot-strap.md)、[晶体](design-cards/mcu/m05-crystal.md)、[外部时钟](design-cards/mcu/m06-external-clock.md)、[SWD/JTAG](design-cards/mcu/m07-swd-jtag.md)、[UART Bootloader](design-cards/mcu/m08-uart-bootloader.md)。
- **常用硬件：** [I 主控与最小系统](common-hardware/i-mcu.md)（低成本/通用/无线/模拟主控、看门狗、自动下载、EEPROM）。

## 2. 供电、充电与多源供电
- **构成：** 输入、适用保护、转换/分配/开关、使能/PG/采样、储能、负载。电池另查化学体系、串数、充电、保护、温度检测和电源路径。
- **核算：** 全输入范围下压差/效率/峰值/瞬态、热、有效电容、L/C 和开关应力、故障能量。
- **失效与 PCB：** 输入反灌、热插拔、掉电、短路、输出过冲；控制器真正高 di/dt 回路、反馈/Kelvin 路径和散热。不要用线性器件封装名称推断固定可耗散瓦数。
- **深入：** [LDO](design-cards/power/p01-ldo.md)、[Buck](design-cards/power/p02-buck.md)、[Boost](design-cards/power/p03-boost.md)、[Buck-Boost](design-cards/power/p04-buck-boost.md)、[多源供电](design-cards/power/p05-power-mux.md)、[线性充电](design-cards/power/p06-linear-charger.md)、[开关充电](design-cards/power/p07-switching-charger.md)、[电池保护](design-cards/power/p08-battery-protection.md)、[反接保护](design-cards/power/p09-reverse-polarity.md)、[热插拔](design-cards/power/p10-hot-swap.md)、[eFuse](design-cards/power/p11-efuse.md)、[USB-C Sink](design-cards/power/p12-usbc-sink.md)、[USB-C Source](design-cards/power/p13-usbc-source.md)、[掉电保持](design-cards/power/p14-supercap-backup.md)。
- **常用硬件：** [F 供电入口/保护](common-hardware/f-input-protection.md)、[G LDO/Buck/Boost/负压/隔离](common-hardware/g-power-conversion.md)、[H 电池/充电/低功耗](common-hardware/h-battery.md)。

## 3. 时钟、复位与调试
- **构成：** 实际需要的时钟源、匹配/去耦、复位/监控、启动配置和调试口。
- **核算：** 晶体负载/寄生、ESR 与驱动、启动、复位阈值/时序、噪声敏感性。CL 简式仅初选，不能用固定 18pF 通吃。
- **失效与 PCB：** 调试时反向供电、程序下载与正常启动互相牵制；晶振按具体 layout 指南控制环路和邻近干扰。
- **深入：** 见第 1 类的 MCU-03～MCU-08。

## 4. 有线接口
- **构成：** 控制器/PHY 或收发器、正确电源域、配置、连接器、适用端接/偏置/保护与参考地；接口名相同不保证物理层相同。
- **核算：** 方向、模式、地址、三态、电平、掉电状态、总线电容/端接/共模、时序和线缆。
- **失效与 PCB：** 同名不同物理层、重复端接、上拉并联、跨参考分割、连接器镜像、保护泄放绕远。
- **深入：** [I²C](design-cards/interfaces/i01-i2c.md)、[I²C 缓冲](design-cards/interfaces/i02-i2c-buffer.md)、[SPI](design-cards/interfaces/i03-spi.md)、[SPI 多从机](design-cards/interfaces/i04-spi-multi.md)、[UART](design-cards/interfaces/i05-uart.md)、[RS-232](design-cards/interfaces/i06-rs232.md)、[RS-485](design-cards/interfaces/i07-rs485.md)、[CAN](design-cards/interfaces/i08-can.md)、[USB Device](design-cards/interfaces/i09-usb-device.md)、[USB-C 数据](design-cards/interfaces/i10-usbc-data.md)、[Ethernet](design-cards/interfaces/i11-ethernet.md)、[电平转换](design-cards/interfaces/i12-level-shift.md)。
- **常用硬件：** [J 总线与外设](common-hardware/j-buses.md)（I²C/SPI/UART/RS-232/RS-485/CAN/USB/以太网的具体外设与模块）。

## 5. 无线、射频与定位
- **构成：** 模组或经验证的 RF 链、供电、控制/下载、SIM 或其他外围、天线/馈线/匹配/测试口。
- **核算：** 发射脉冲供电、频段/带宽、馈线和天线环境、参考 layout 差异；不固定某个模组的峰值电流/电容值。
- **失效与 PCB：** 天线净空按实际天线/模组逐层落实，考虑壳体/电池/紧固件；匹配网络值是调谐起点，认证不能自动代替整机认证。
- **深入：** [Wi-Fi/BLE](design-cards/wireless/w01-wifi-ble.md)、[天线](design-cards/wireless/w02-antenna.md)、[蜂窝](design-cards/wireless/w03-cellular.md)、[GNSS](design-cards/wireless/w04-gnss.md)。
- **常用硬件：** [M 无线/时间/隔离](common-hardware/m-wireless-time.md)（Wi-Fi/BLE/Sub-GHz/蜂窝/GNSS/RTC/NFC/数字隔离）。

## 6. 模拟采集与工业传感
- **构成：** 传感器/激励、保护、采样/放大/滤波、ADC/基准、参考回流；4-20mA 先辨两线/三线/四线、回路供电和共模。
- **核算：** 量程/过量程、compliance 余量、采样电阻功耗、精度/漂移/噪声、源阻抗/ADC 建立、输入共模/输出摆幅。
- **失效与 PCB：** 开路/误接/浪涌、保护漏电、参考动态负载、Kelvin 与敏感回流；温度传感器避开热源。
- **深入：** [分压](design-cards/analog/a01-divider.md)、[运放缓冲](design-cards/analog/a02-opamp-buffer.md)、[差分放大](design-cards/analog/a03-diff-amp.md)、[ADC 驱动](design-cards/analog/a04-adc-driver.md)、[基准](design-cards/analog/a05-vref.md)、[低侧采样](design-cards/analog/a06-low-side-sense.md)、[高侧采样](design-cards/analog/a07-high-side-sense.md)、[4-20mA](design-cards/analog/a08-4-20ma.md)、[桥式传感](design-cards/analog/a09-bridge.md)、[RTD/热敏](design-cards/analog/a10-rtd-thermistor.md)。
- **常用硬件：** [A 环境传感](common-hardware/a-environment.md)、[B 光学/测距](common-hardware/b-optics.md)、[C 运动/位置](common-hardware/c-motion.md)、[D 力/压力/液位/流量](common-hardware/d-force.md)、[E 电测](common-hardware/e-measurement.md)。

## 7. 电机、继电器与功率负载
- **构成：** 驱动/栅驱、功率级、实际需要的采样/限流/保护、负载连接、续流/钳位、控制默认态。
- **核算：** 启动/堵转/回生、MOSFET 实际 Vgs/温度下导通损耗、开关/SOA、驱动电荷、自举与占空比、死区、钳位能量/释放时间。
- **失效与 PCB：** 控制器复位时误动作、直通、缺相/短路、感性回灌；功率回路、栅极环路、散热、采样地。
- **深入：** [低侧开关](design-cards/drive/d01-low-side.md)、[高侧开关](design-cards/drive/d02-high-side.md)、[继电器](design-cards/drive/d03-relay.md)、[半桥](design-cards/drive/d04-half-bridge.md)、[H 桥](design-cards/drive/d05-h-bridge.md)、[步进](design-cards/drive/d06-stepper.md)、[LED 恒流](design-cards/drive/d07-led-cc.md)、[加热](design-cards/drive/d08-heater.md)。
- **常用硬件：** [K 开关/继电器/电机负载](common-hardware/k-drive.md)（电磁阀、直流电机、步进、风扇、舵机、加热器）。

## 8. 显示、音频与人机
- **构成：** 屏/背光或音频 Codec/功放/麦克风、实际接口、供电/偏置、控制、连接器；按键/LED 及适用驱动。
- **核算：** 面板时序/lane、FPC 视角、背光电流、音频负载/增益/噪声、LED 限流和热。
- **失效与 PCB：** 桥接输出误接地、电荷泵/升压遗漏、数字模拟耦合、对外线缆保护与装配可见标识。蜂鸣器须辨压电/电磁和有源/无源；有源只需电平/开关，无源需方波频率与占空比。
- **深入：** [显示与背光](design-cards/wireless/w05-display.md)、[Class-D](design-cards/wireless/w06-classd.md)。
- **常用硬件：** [L 显示/声音/按键](common-hardware/l-hmi.md)（LED、数码管、OLED/LCD、TFT、触摸、按键、旋钮、蜂鸣器、扬声器）。

## 9. 存储与高速链路
- **构成：** SPI/QSPI/OSPI Flash、EEPROM、SD/eMMC/DDR 等按所选控制器的工作模式；WP/HOLD/复位/电源与信号角色随模式核对。
- **核算：** 电压、启动、控制器时序、bank/复用、拓扑和时序/信号完整性预算；AC 耦合与终端按具体链路要求。
- **失效与 PCB：** 不把 SPI 模式的上下拉照搬到 QSPI，不把所有 SDIO/DDR 网机械等长；依据时序分组和叠层/过孔延迟设置约束。
- **深入：** [SPI Flash](design-cards/wireless/w07-spi-flash.md)、[microSD](design-cards/wireless/w08-microsd.md)。

## 10. 隔离、保护与测试
- **构成：** 明确隔离屏障两侧的信号、供电、地、屏蔽/机壳、跨屏障器件及可触及结构；保护按实际暴露/标准与功能选择。
- **核算：** 工作/瞬态电压、共模、绝缘要求、爬电/间隙、材料/污染/海拔、TVS 钳位电流条件与负载耐受、保护协调。
- **失效与 PCB：** 跨屏障铜/孔/测试夹具/紧固件破坏隔离、采样/调试误短接；预留可测点但不因此跨接隔离。
- **深入：** [热插拔](design-cards/power/p10-hot-swap.md)、[eFuse](design-cards/power/p11-efuse.md)、[RS-485](design-cards/interfaces/i07-rs485.md)、[CAN](design-cards/interfaces/i08-can.md)。
- **常用硬件：** [E5 隔离电流](common-hardware/e-measurement.md)、[G6 隔离 DC/DC](common-hardware/g-power-conversion.md)、[M8 数字隔离器](common-hardware/m-wireless-time.md)。

## 跨模块组合

组合后至少核对：输入/输出电压范围、逻辑门限与电流方向、上电/复位/下载/休眠/掉电状态、引脚复用与片选、连接器/FPC 视角、电源容量与反灌、参考地/隔离/屏蔽、模块内部已集成的外围、固件初始化与硬件版本、机械/热/天线/测试空间。至少 8 个“单模块正常、组合失败”的案例见 [组合与接口契约](module-integration.md)。
