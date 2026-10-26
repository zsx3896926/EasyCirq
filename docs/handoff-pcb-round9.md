# Handoff — PCB round 9（2026-10-26）

## 仓库/分支

- 仓库：`hardware-design-skill`；worktree：`C:/Users/jlc/work/hds-pcb-round9`
- 分支：`feat/pcb-layout-round9`，已推送；PR **#21**（draft）
- **stacked on PR #20**（`feat/skill-v0.9-reviewed`，v0.9.0）；本 PR 只含 PCB 工作包，合并前先把 base 切到 main 或等 #20 合入。
- 本轮代码提交：`79c2474 feat(pcb): add measured constraints, local templates and readback workflow`

## 已完成（离线/可复现）

- `design_engine/pcb_workflow.py`：实测 dump 归一化、约束编译/冲突、9 个局部模板、三候选、逃线代理、IPC-2221 电源筛查、stale plan/primitiveId 拒绝、scoped diff、模块相对布局复用、预算化 joint loop。
- `scripts/pcb_apply_plan.py`：校验 → 逐件 typed `pcb modify` → save/reload/fresh dump → scoped diff；默认 dry-run。
- `references/pcb-execution.md`、`assets/pcb-placement-templates.json`、SKILL 路由、v0.9.1。
- 真实板 A 案例证据：`design-hardware/cases/photo-led-pcb-2026-10-26/`（19 件 dump、intent、constraints、plan、candidates、escapes、power、module contract、design-state）。
- 测试：`python -m unittest discover -s tests` → **923 tests OK**；`skill_selftest` → **5 PASS**。

## EDA 当前真实状态

- 工程 `photo-led-pcb-20261026`（UUID `e56848aaf64d49d7a465352291670aef`），PCB1 `99b8366b0bdc971f`；源工程 `photo-led-5v-20261026` 未改。
- 19 器件 / 47 焊盘已导入；90×60mm 圆角板框；4×M3 安装孔（inset 200，Ø126，垫圈 keepout 118）。
- 19 器件已按提案落位并通过离线检查；`layout-lint` 80/moderate，0 overlap/off-board/short，5 crossings。
- J1 已从 rotation 90 改 270，`connector-opening-inward`/`connector-mating-blocked` 清零。
- VREF_2V5 官方路由器已布：12 tracks / 0 vias；`net-path U2.3→R1.1` connected（底层 10 mil）。
- 当前窗口 `5175351c…` 被 PR20 会话（jlc-06/jlc-61）占用到约 21:30；我方已保存并让出，恢复后先确认 `doc ls`/save/reload。
- 证据快照：`photo-led-board-placed2.json`（布局后、VREF 前）；checkpoint `photo-led-placed-checkpoint.epro2`（SHA `dbe3fdd9…c018`）。

## 未完成 / 下一步

1. 板 A：剩余信号（LDR_SIG/VTH/VTH_ADJ/LED_CTRL/Q1_B/LED_A/LED_K/U1B_TIE）官方布线 → 铺铜（power-pour）→ 关键网 net-path → DRC/check → 丝印 → save/reload/fresh dump + diff → 顶/底图。
2. 板 B：按 `board-b-plan.md` / `board-b-build.md` 创建 `mcu-i2c-s3-20261026`（ESP32-S3-WROOM-1-N8R8 + SHT40，USB-C 原生 USB，2 层 SMT）；先干跑 block-apply，再写入/检查。
3. 局部改板/复用/基线/制造资料按任务书后续补齐；未导出 Gerber/drill/CPL 记 `BLOCKED`。
4. 证据归档与 handoff 更新。

## 已知限制/风险

- `near_pin` 是 pad 中心距；逃线是代理；铺铜连通/阻抗/EMC/热/实物未证明。
- 板 A C2 去耦 150 mil，CLI 规则阈值 100 mil；DIP-8/12mm 本体在不重叠条件下已最近，保留 WARN 并解释。
- 板 B SHT40 原厂 4 脚 vs 库 DFN-4-EP（EP 接 GND）需装配前核对；WROOM 天线端方向需按 footprint/3D 确认。
- EasyEDA 唯一 GUI 窗口需与 PR20 会话分时；写入前确认没有他人未保存工程。
- `pcb drc` 需要 PCB 前台；后台/遮挡会超时，超时先切前台一次，不循环重试。
