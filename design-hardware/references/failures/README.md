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

复验未执行时，文件内写 `未执行`；不能把修复方案当成已验证。
