# Handoff — PCB round 9（2026-10-26）

## 仓库/分支

- 仓库：`hardware-design-skill`；worktree：`C:/Users/jlc/work/hds-pcb-round9`
- 分支：`feat/pcb-layout-round9`，已推送；PR **#21**（draft），**stacked on PR #20**（`feat/skill-v0.9-reviewed`）。合并前把 base 切到 main 或等 #20 合入。
- 提交：`79c2474` 约束/模板/候选/回读；`394f1db` 真实状态+handoff；`830f56d` fabrication 预检；`2061560` template CLI/THT flip；`34f5adb` 丝印 180 修复。

## 已完成（离线/可复现）

- `design_engine/pcb_workflow.py`：实测 dump 归一化、约束编译/冲突、9 个局部模板、三候选、逃线代理、IPC-2221 电源筛查、stale plan/primitiveId 拒绝、scoped diff、模块相对布局复用、预算化 joint loop、丝印/铺铜/过孔预检。
- `scripts/pcb_apply_plan.py`：校验 → 逐件 typed `pcb modify` → save/reload/fresh dump → scoped diff；默认 dry-run。
- `references/pcb-execution.md`、`assets/pcb-placement-templates.json`、SKILL 路由、v0.9.1。
- 测试：`python -m unittest discover -s tests` → **923 tests OK**（24 个 PCB 定向测试）；`skill_selftest` → **5 PASS**。
- 案例：`design-hardware/cases/photo-led-pcb-2026-10-26/`。

## 板 A 真实状态（已完成）

- 工程 `photo-led-pcb-20261026`（`e56848aaf64d49d7a465352291670aef`）/ PCB1 `99b8366b0bdc971f`；源 `photo-led-5v-20261026` 未改。
- 19 器件 / 47 焊盘；90×60mm 圆角板框；4×M3（inset 200，Ø126，垫圈 118）；J1 锁定、rotation 270 开口朝外。
- 信号：官方路由器 8/8 网 + 42 tracks/0 via；VREF 12 tracks/0 via；+5V/VIN 13 tracks/0 via；GND 双面铺铜 + `pour-rebuild`。
- **原生 DRC passed=true / total=0**；`pcb check` 6 WARN（powerNotPoured 2、widthUnderSpec 2、decapTooFar 2，均已解释）。
- 关键连接 14/14 `net-path` connected、exact-centerline、0 via；SCH-PCB 19/19、47/47 0 mismatch。
- save→reload→fresh dump `pcb-diff` **match**；19/19 `silk-align`，silk-over-pad/flipped/off-board 0；J1 旁 “5V IN”/“GND”。
- BOM 15 行/19 件，`sourcing` 身份完整性 pass；最终 `.epro2` 230,203 B SHA `d9ef9201…6491`；DRC-0 检查点 `6542f416…0400`。
- 顶/底 actual PNG 已实际查看；`pcb-final-top.png` / `pcb-final-bottom.png`。
- **制造包 BLOCKED**：typed CLI 无 Gerber/drill/CPL；BOM 已导出；未下单。
- 未做实物/热/EMC/光照实测。

## 板 B 状态（计划/资料核对，未创建）

- 方案：`mcu-i2c-s3-20261026`，ESP32-S3-WROOM-1-N8R8 + SHT40 + AMS1117-3.3 + USB-C 原生 USB，2 层 SMT。
- 已核对原厂资料：
  - WROOM-1 datasheet v1.8 Table 3-1：pin13 IO19=USB_D−、pin14 IO20=USB_D+、pin4 IO4、pin5 IO5、pin3 EN、pin27 IO0、pin1/40/41 GND、pin2 3V3；IO35-37 在 Octal PSRAM 模组不可用；模块 18×25.5mm，天线 keepout。
  - SHT4x datasheet v6.4 Figure 17/18：1 SDA/2 SCL/3 VDD/4 VSS；die pad 不与任何引脚相连；传感器下方除引脚焊盘外禁铜。**easyeda `-EP` 库封装把 EP 接 GND 与资料冲突，不能照抄**；需找无 EP 封装或 EP NC + 全层 no-copper 区。
  - AMS1117 固定 3.3V：pin1 GND/pin2 VOUT/pin3 VIN/pin4 散热片 VOUT；22µF 手册稳定性保证为固体钽，而 block 用陶瓷 → `LDO stability NOT VERIFIED`。
- 构建步骤与精确命令见 scratch `board-b-build.md` / `board-b-plan.md`（未提交仓库）；窗口空出后创建工程、block-apply、SHT40/22R、autoconnect、sch gate、import PCB、65×45mm 板框、2×M2.5、天线 keepout、布局/布线/DRC/保存重开。

## 未完成

1. 板 B 全部 EDA 创建与验证。
2. 板 A 三项局部改板（换封装/移接口/加器件）与跨工程模块复用；现有 `pcb-reuse-plan` 仅离线验证。
3. 制造资料 Gerber/drill/CPL（BLOCKED）；板厂 DFM、下单不做。
4. 实物/热/EMC。

## 窗口/并发

- 唯一 GUI 窗口 `5175351c…` 与 PR20 会话分时。板 A 最终保存后已让出 15 分钟给 jlc-06 修 photo-led 原理图；等其“空出”后继续板 B。**不要修改** `ne555-blinker-1hz-20261026`、`ams1117-3v3-20261026`、`photo-led-5v-20261026`。
- `pcb drc` 需 PCB 前台；后台/遮挡会超时，超时先切前台一次，不循环重试。
