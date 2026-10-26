# 真实案例（计划/资料核对）：MCU + I²C 传感器小板（2026-10-26）

> 状态：**尚未在 EDA 创建工程**。本文件只记录已核对的方案、原厂资料和待执行步骤；不得写成已画/已验收。窗口空出后创建 `mcu-i2c-s3-20261026` 并补真实证据。

## 1. 目标

- 低速、低压、小规模、双层：3.3V；I²C 100/400kHz；ESP32-S3 原生 USB 下载；SMT。
- 与板 A 不同：板 A 为 THT/混装、5V 直接输入、左侧螺钉端子；板 B 为 SMT、USB-C 右侧供电+下载、2×M2.5 安装孔。
- 不做：RF 匹配/天线设计（用模组内置天线 + keepout）、高速阻抗签核、外壳、固件、实物测试。

## 2. 方案

| 功能 | 方案 | 身份/依据 |
|---|---|---|
| MCU | ESP32-S3-WROOM-1-N8R8（内置 flash/PSRAM/晶振/PCB 天线） | Espressif datasheet v1.8；easyeda block `esp32s3_wroom1_module`；LCSC C9900163599 |
| 下载 | 原生 USB-Serial/JTAG：IO19=D−、IO20=D+，经 22R 到 USB-C | datasheet Table 3-1；block notes |
| 供电 | USB-C 5V（CC 5.1k + ESD）→ AMS1117-3.3 | AMS1117 datasheet；block `ams1117_ldo_3v3` |
| I²C 传感器 | SHT40-CD1B-R3（DFN-4 1.5×1.5mm，1.08–3.6V，地址 0x44） | Sensirion SHT4x datasheet v6.4 Figure 17/18；LCSC C7461852 |
| 上拉 | 2×2.2k 0402 到 +3V3 | 总线电容/上升时间核算；只保留一组 |
| 去耦 | 模组 100nF×3 + 10µF；SHT40 100nF | 模组 block + 传感器布置要求 |
| 按键 | BOOT(IO0)/RESET(EN) 轻触 SMD | block `tactile_boot_reset` |

## 3. 已核对的原厂引脚

ESP32-S3-WROOM-1 datasheet v1.8 Table 3-1（41 脚）：
- 1 GND、2 3V3、3 EN（不得悬空）、4 IO4、5 IO5、13 IO19/USB_D−、14 IO20/USB_D+、27 IO0、36 RXD0、37 TXD0、40 GND、41 EPAD/GND。
- 模块 18±0.2 × 25.5±0.2 mm；1.27mm 引脚间距；Figure 3-1 标天线 Keepout Zone。
- IO35/36/37 在 Octal PSRAM 模组被 PSRAM 占用；本设计不用。
- GPIO47/48 在 R16V 为 1.8V；本设计不用；I²C 用 IO4/IO5。

SHT4x datasheet v6.4 Figure 17/18：
- 1 SDA、2 SCL、3 VDD、4 VSS；die pad 不与任何引脚相连；Figure 17 明确“传感器下方除引脚焊盘外不得有铜”。

## 4. 必须处理的两个资料冲突（不能照抄库/block）

1. **SHT40 EP**：easyeda `co2-temperature-humidity.topology.json` 用 `DFN-4_L1.5-W1.5-P0.80-TL-EP` 并把 EP 接 GND；原厂说 die pad 不与引脚相连、传感器下方禁铜。板 B 处理：优先找无 EP 封装；若只有 `-EP`，EP 标 NC，传感器本体投影区全层 no-copper/no-pours，实际看图确认；无法满足则换有明确无 EP 封装的传感器或不宣称完成。
2. **AMS1117 输出电容**：block 用 22µF 0805 陶瓷；datasheet 的稳定性保证是 22µF 固体钽。板 B 保留 block 时明确 `LDO output stability NOT VERIFIED`；生产候选需换钽或做负载瞬态/振荡实测。

## 5. 待执行步骤（窗口空出后）

1. `project create --name mcu-i2c-s3-20261026 --open` → `board new --project <uuid> --name MCU_I2C`。
2. 先放 SHT40/100nF/2×2.2k/2×22R（高位号避免冲突），再 block-apply：
   - `usbc_dual_orientation_data`：VBUS=VBUS_5V、GND=GND、USB_DP=USB_DP_CONN、USB_DM=USB_DM_CONN。
   - `ams1117_ldo_3v3`：VIN_5V=VBUS_5V、3V3=+3V3、GND=GND。
   - `esp32s3_wroom1_module`：3V3=+3V3、GND=GND、EN=EN、IO0=BOOT、U0TXD=MCU_TX、U0RXD=MCU_RX。
   - `tactile_boot_reset`：IO0=BOOT、EN=EN、GND=GND。
3. autoconnect：SHT40 1/2/3/4 到 I2C_SDA/I2C_SCL/+3V3/GND，EP 5 标 NC；上拉/滤波；22R 串在 USB_DP_CONN↔USB_DP_MCU、USB_DM_CONN↔USB_DM_MCU；U pin14/13 到 USB_DP_MCU/USB_DM_MCU，pin4/5 到 I2C_SDA/SCL。
4. `sch check/gate/drc`、导图、save/reload、`sch read` 逐脚对账。
5. PCB：`import-changes`，65×45mm 圆角板框、2×M2.5（Ø2.7mm，inset 150）、USB-C 右板边、模组天线朝上板边 + 全层 keepout、SHT40 左/上板边且下方禁铜；`ldo-caps`/`i2c-sensor`/`module-decap` 模板 + 约束；布线 USB 对、I²C、电源；GND 双面铺铜。
6. DRC/check、关键 net-path、save/reload diff、顶/底图、BOM；制造包同样受 Gerber/CPL CLI 能力限制。

## 6. 资料入口

- ESP32-S3-WROOM-1 datasheet v1.8：https://documentation.espressif.com/esp32-s3-wroom-1_wroom-1u_datasheet_en.pdf
- ESP32-S3 Hardware Design Guidelines：https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32s3/pcb-layout-design.html
- SHT4x datasheet v6.4：https://sensirion.com/media/documents/33FD6951/6555C40E/Sensirion_Datasheet_SHT4x.pdf
- AMS1117 datasheet：LCSC C6186（见 `block.ams1117_ldo_3v3.source`）

## 7. 当前限制

- 未创建工程、未画原理图/PCB；本文件不能作为交付证据。
- 天线 keepout 的具体方向/尺寸需按实际 footprint 与 datasheet Figure 3-1 再次确认。
- LDO 热耗 (5−3.3)×0.5=0.85W 需按实际铜面积/环境温度核算；DRC 通过不等于热设计通过。
