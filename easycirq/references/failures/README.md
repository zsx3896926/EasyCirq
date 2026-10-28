# 故障与反例库

> 统一结构：现象 → 工况 → 原因假设 → 区分假设的检查 → 根因证据 → 修复 → 复验 → 适用边界。
> 证据等级：A 作者已证实根因；B 原厂/可复现资料支持；C 工程推断；D 未证实。不得把论坛回复写成定论。

| ID | 案例 | 证据 | 来源 | 文件 |
|---|---|---|---|---|
| F01 | ODrive 电流采样寄生电阻导致比例误差 | A | [P04, ANA-S06] | [f01-odrive-sense-parasitic.md](f01-odrive-sense-parasitic.md) |
| F02 | 两节 AA 经 LDO 维持 3.3V 失败 | C | [PWR-S03, PWR-S04] | [f02-two-aa-ldo.md](f02-two-aa-ldo.md) |
| F03 | ESP32 启动 strap 被外围拖偏 | B | [MCU-S04, MCU-S09, P04] | [f03-esp32-strap.md](f03-esp32-strap.md) |
| F04 | STM32 VCAP/特殊供电脚遗漏 | B | [MCU-S01, MCU-S02] | [f04-stm32-vcap.md](f04-stm32-vcap.md) |
| F05 | 晶体负载/ESR 不适配导致不起振 | B | [MCU-S02, MCU-S01, MCU-S04] | [f05-crystal-load-esr.md](f05-crystal-load-esr.md) |
| F06 | I2C 上拉过强/过弱 | B | [IF-S01, IF-S02] | [f06-i2c-pullup.md](f06-i2c-pullup.md) |
| F07 | RS-485 端接/偏置位置错误 | B | [IF-S03] | [f07-rs485-termination.md](f07-rs485-termination.md) |
| F08 | CAN 端接过多/共模问题 | B | [IF-S04] | [f08-can-termination.md](f08-can-termination.md) |
| F09 | USB-C CC 电阻缺失/错误 | B | [PWR-S16, PWR-S15, PWR-S17] | [f09-usbc-cc.md](f09-usbc-cc.md) |
| F10 | Buck 反馈/输入电容布局导致噪声 | B | [PWR-S01, G03] | [f10-buck-loop-layout.md](f10-buck-loop-layout.md) |
| F11 | MLCC 直流偏压导致有效容量不足 | B | [PWR-S01, PWR-S04] | [f11-mlcc-bias.md](f11-mlcc-bias.md) |
| F12 | 电感饱和导致过流/过热 | B | [PWR-S01, PWR-S09] | [f12-inductor-saturation.md](f12-inductor-saturation.md) |
| F13 | MOSFET SOA/热插拔浪涌失效 | B | [PWR-S11, DRV-S05] | [f13-mosfet-soa.md](f13-mosfet-soa.md) |
| F14 | 继电器线圈无续流/释放慢 | B | [DRV-S04, DRV-S09, DRV-S10] | [f14-relay-flyback.md](f14-relay-flyback.md) |
| F15 | FPC Pin-1/接触面反向 | C | [P07] | [f15-fpc-pin1.md](f15-fpc-pin1.md) |
| F16 | 铺铜后参考路径/连通性变化 | B | [T01, G05] | [f16-copper-pour-reference.md](f16-copper-pour-reference.md) |
| F17 | 差分等长但跨参考平面分割 | B | [G06, G05] | [f17-diff-split-reference.md](f17-diff-split-reference.md) |
| F18 | 天线净空/外壳导致失谐 | B | [RF-S01, RF-S02, RF-S04] | [f18-antenna-enclosure.md](f18-antenna-enclosure.md) |
| F19 | BOM/坐标/DNP 版本不一致 | B | [MFG-S03, MFG-S05, MFG-S06, MFG-S08, MFG-S16] | [f19-bom-cpl-dnp.md](f19-bom-cpl-dnp.md) |
| F20 | 商城有货但 SMT 不可贴 | B | [MFG-S02, MFG-S04, MFG-S10, MFG-S15] | [f20-lcsc-stock-vs-smt.md](f20-lcsc-stock-vs-smt.md) |
| F21 | 焊接完成但未烧录/未功能测试 | B | [MFG-S16] | [f21-soldered-not-tested.md](f21-soldered-not-tested.md) |
| F22 | ADC 建立时间/采样误差 | B | [ANA-S02, ANA-S03] | [f22-adc-settling.md](f22-adc-settling.md) |
| F23 | 下载器连接后异常供电（T_VCC 反灌/LDO 被抬压） | B/C | [MCU-S07, MCU-S01, D-S07] | [f23-debugger-backpower.md](f23-debugger-backpower.md) |
| F24 | 复位脚被外围拉错（推挽复位 IC/电容/漏电） | B/C | [MCU-S01, MCU-S06] | [f24-nrst-pulled-by-peripheral.md](f24-nrst-pulled-by-peripheral.md) |
| F25 | 无线发射导致系统复位（burst/源阻抗） | B | [RF-S03, MCU-S09] | [f25-radio-tx-resets-system.md](f25-radio-tx-resets-system.md) |
| F26 | 电机启动干扰模拟采集（地弹/耦合/混叠） | B | [ANA-S06, ANA-S14] | [f26-motor-start-corrupts-adc.md](f26-motor-start-corrupts-adc.md) |
| F27 | USB 接入后地环路或电源冲突 | B | [PWR-S06, IF-S11] | [f27-usb-ground-loop-source-conflict.md](f27-usb-ground-loop-source-conflict.md) |
| F28 | I²C 设备掉电后拖死总线 | B | [IF-S01 §3.1.16] | [f28-i2c-unpowered-device-lockup.md](f28-i2c-unpowered-device-lockup.md) |
| F29 | SPI 写正常、读不稳定 | B | [IF-S08, IF-S03] | [f29-spi-write-ok-read-unstable.md](f29-spi-write-ok-read-unstable.md) |
| F30 | GPIO 在上电阶段误触发负载 | B | [MCU-S01, MCU-S04] | [f30-gpio-power-on-glitch.md](f30-gpio-power-on-glitch.md) |
| F31 | 换料后典型工况正常、边界工况失败 | B | [selection/replacement-classes] | [f31-replacement-passes-typical-fails-corner.md](f31-replacement-passes-typical-fails-corner.md) |
| F32 | 外壳安装后无线或热性能下降 | B | [RF-S01, RF-S02, thermal] | [f32-enclosure-degrades-rf-and-thermal.md](f32-enclosure-degrades-rf-and-thermal.md) |
| F33 | 测量接法错误导致错误修板 | B | [ANA-S06, simulation-measurement §5] | [f33-measurement-caused-wrong-rework.md](f33-measurement-caused-wrong-rework.md) |

## 跨模块 12 类覆盖（本轮补齐）

| # | 用户点名的问题 | 本库对应 |
|---:|---|---|
| 1 | 下载器连接后异常供电 | F23；B1 专题 §2.9/§7.3 |
| 2 | MCU 复位或启动脚被外围拉错 | F24；F03（strap）；D1 专题 |
| 3 | 无线发射导致系统复位 | F25；B4 专题 |
| 4 | 电机启动干扰模拟采集 | F26；C2/C4 专题 |
| 5 | USB 接入后地环路或电源冲突 | F27；B1 专题 |
| 6 | I²C 设备掉电后拖死总线 | F28；D1 专题 §7 |
| 7 | SPI 写正常、读不稳定 | F29；D1/D3 专题 |
| 8 | GPIO 在上电阶段误触发负载 | F30；D1 专题 |
| 9 | 更换器件后典型工况正常、边界工况失败 | F31；selection/replacement-classes |
| 10 | 外壳安装后无线或热性能下降 | F32；F18（天线）；E3 专题 |
| 11 | 软件引脚配置与实际板版不一致 | F30、F31；D1 专题 §11 |
| 12 | 测量接法错误导致错误修板 | F33；C4 专题 |

复验未执行时，文件内写 `未执行`；不能把修复方案当成已验证。F23–F33 均为**构造案例**（除已在正文标注作者记录的部分），不是真实用户故障记录；根因证据按 B/C 分级，不能当实测。

## 器件专项案例的入库要求

按键内部常通组、具体型号/修订版引脚能力、合并焊盘映射、裸露焊盘功能、摇杆机械尺寸、多单元符号几何等器件级结论，必须先从原厂资料与真实库件核对，再按“适用条件（型号/修订/封装/工况）→ 证据级别（A/B/C/D）→ 结论 → 不适用场景”入库；先验证再沉淀，不把单次案例推广成通用规则。报告里先用同一格式标注，再决定是否新增案例；未取得原厂资料或现场证据的，保持 `D`/`未复现`，不得写成已吸收（见 [工程经验库](../design-experience.md) 与仓库内 `docs/toolchain-integration/field-lessons.md`）。
