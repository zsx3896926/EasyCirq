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

## 板 B 真实状态（已完成）

- 工程 `mcu-i2c-s3-20261026`（`b4327168b80347f492b53baf9f04bd20`）/ Board2 / PCB2 `40b81985cfb4a5ed`；三页原理图 P1/P2/P3。
- 23 器件 / 15 网络 / 104 物理脚；SCH-PCB 23/23、104/104 0 mismatch。
- 板框 65.79×45 mm，2×M2.5；USB-C 右板边 rotation 180，开口/插拔通道 0；WROOM rotation 180，天线端贴下板边；SHT40 左上。
- 布局 lint 68/moderate，0 overlap/off-board/short；官方路由器首轮 12/14（MCU_TX/RX 单引脚），后续 +3V3/GND 重布；GND 双面铺铜。
- **原生 DRC passed=true / total=0**；15/15 关键 net-path connected；save/reload diff **match**。
- 丝印 over-pad/off-board/flipped 0；BOM 15 行/23 件，`sourcing` 身份完整性 pass。
- 最终归档 132,270 B SHA `312f3cd4…cc1`；图 `pcb-final-top.png`/`pcb-final-bottom.png`。
- 剩余 WARN：天线 keepout CLI 口径 1、+3V3 未铺铜 1、GND 10 mil 1、decap 5、parallel 4、acute 1、fiducial INFO；SHT40 EP 库焊盘/原厂“下方无铜”未完全一致；AMS1117 陶瓷输出稳定性 NOT VERIFIED；USB 未做 SI 签核。
- **制造包 BLOCKED**：typed CLI 无 Gerber/drill/CPL；BOM 已导出。

## 局部改板（WP11，已完成一项）

- 独立副本 `mcu-i2c-s3-edit-20261026`（`283b0ccaaa9c404d87056886a29c2562`），从 `boardB-final.epro2` 导入。
- 增加 C99 100nF +3V3/GND 去耦；只重布 `+3V3`/`GND`；DRC 0；scoped diff：identity +1(C99)、geometry 0、copper 135（均在受影响网络）、**unrelated 0**；save/reload match。
- 最终 `edit-add-decap-final.epro2` 135,173 B SHA `f65654cb…e025`。
- 换封装/移动接口两项 **NOT RUN**；跨工程铜复用未支持（`pcb-reuse-plan` 仅离线验证）。

## 未完成

1. 板 A/B 换封装/移动接口两项局部改板；跨工程模块铜复用未支持。
2. 制造资料 Gerber/drill/CPL（BLOCKED）；板厂 DFM、下单不做。
3. 实物/热/EMC/固件；WP14 四板矩阵中的 C/D 未做。
4. WP15 受控基线仅记录了两板事实，未做同条件原流程/新流程完整对照。

## 窗口/并发

- 唯一 GUI 窗口 `5175351c…` 与 PR20 会话分时。板 A 最终保存后已让出 15 分钟给 jlc-06 修 photo-led 原理图；等其“空出”后继续板 B。**不要修改** `ne555-blinker-1hz-20261026`、`ams1117-3v3-20261026`、`photo-led-5v-20261026`。
- `pcb drc` 需 PCB 前台；后台/遮挡会超时，超时先切前台一次，不循环重试。
