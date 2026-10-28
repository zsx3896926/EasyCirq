# eev3 最终验收证据（DRC + BOM）

> 工程：`zhigou-dual-button-led-eev3-20261028`（uuid `b45c9648853446a08f2bf374fa85ee0d`）
> 基线：从 `zhigou-board.epro2` 重导（原工程与 eev2 副本已损坏，不再使用）
> 采集时间：2026-10-28 13:12（只读收集，未修改工程）

## 1. PCB DRC

- 命令：`zhigou pcb drc`（`pcb.drc.check`）
- 结果：**passed = true，0 violations**（原始回执 `evidence/eev3/pcb-drc.json`）
- 前提：全部 47 条旧走线删除后由官方路由器 `pcb.route.auto` 全板重布，`pcb.pour.rebuild` 重建两层 GND 铺铜，
  `pcb save → doc reload` 后读取。

## 2. BOM（可下单）

来源 `evidence/eev3/BOM-v3.csv`（`bom export --type csv --enrich=false`）：

| 位号 | C 号 | 型号 | 厂家 | 封装 |
|---|---|---|---|---|
| C1 | C125205 | CT41G-0603-2X1-50V-0.1uF-K(N) | TORCH(火炬) | C0603 |
| D1,D2 | C51933311 | GL0805YG01 | Guiguang light(桂光光电) | LED0805-RD |
| F1 | C845159 | S1206-SD-1.5A | SART(萨特) | F1206 |
| J1 | C124375 | B-2100S02P-A110 | Ckmtw(灿科盟) | HDR-TH_2P-P2.54-V-M-1 |
| R1,R2 | C112291 | RC0402FR-07220RL | YAGEO(国巨) | R0402 |
| SW1,SW2 | C49296724 | TS-1101-C-R | XKB Connection(中国星坤) | SW-SMD_L6.0-W3.6-LS8.0 |

## 3. 视觉证据

- PCB 顶面图：`evidence/eev3/pcb-top.png`（快照时间 2026-10-28 13:12）
- 原理图：`evidence/eev3/schematic.png`（2026-10-28 13:11 导出）

## 4. 能作为投产基线吗？

**结论：可以作为"工程/PCB 候选基线"，但不能直接作为"投产基线"。**

已具备：
- PCB 原生 DRC 0 违规；
- 6 行 BOM 全部有可订货 C 号/型号/厂家（库存已核）；
- J1 已按确认方案换为 TH 封装，网络与封装一致。

还缺（投产前必须补）：
1. **制造文件**：eec3 工程尚未导出 Gerber/钻孔/CPL（工具侧已有 `pcb.manufacture.*` 能力，
   可只读导出、不改工程）；
2. **DFM/工艺复核**：layout-lint、DFM 规则、板厂工艺档案核对；
3. **人工走线复核**：全板重布由官方路由器生成，电气正确，但需人工确认走线走向/电源路径/丝印观感；
4. **实物验证**：打样后的上电、通断、限流、边界测试（V2–V11，全部 NOT RUN）。

一句话：**"电气/工程上可以当基线，投产还差制造文件 + DFM + 人工复核 + 实物验证"。**

## 5. 制造文件（2026-10-28 13:13 只读导出）

| 文件 | 大小 | 内容 |
|---|---|---|
| `evidence/eev3/manufacturing/eev3-gerber.zip` | 19483 B | 12 个条目：Gerber_TopLayer.GTL, Gerber_BottomLayer.GBL, Gerber_TopSilkscreenLayer.GTO, Gerber_BottomSilkscreenLayer.GBO, Gerber_TopSolderMaskLayer.GTS, Gerber_BottomSolderMaskLayer.GBS, Gerber_TopPasteMaskLayer.GTP, Gerber_BoardOutlineLayer.GKO, Gerber_DocumentLayer.GDL, Gerber_DrillDrawingLayer.GDD |
| 其中钻孔 | — | **Gerber_DrillDrawingLayer.GDD, Drill_PTH_Through.DRL**（J1 换 TH 后 PTH 钻孔文件正常产出） |
| `evidence/eev3/manufacturing/eev3-cpl.csv` | 3406 B | 9 行，表头 18 列（Designator…Rotation/SMD/Type） |
| `manufacturing-summary.json` | — | 上述产物的层清单/行数/编码记录 |

导出方式：`pcb.manufacture.gerber`（drill=true、drillTable=true）+ `pcb.manufacture.cpl`（csv/mm），
均为**只读产物导出，未修改工程**。

## 6. 更新后的投产结论

制造文件补齐后，投产前剩余：

1. **DFM/工艺复核**：layout-lint + DFM 规则 + 板厂工艺档案核对（仍需人工/工具复核）；
2. **人工走线复核**：全板重布结果建议看一眼（电气正确，走向/观感可优化）；
3. **实物验证**：打样后的上电、通断、限流、边界测试（V2–V11，全部 NOT RUN）；
4. 钻孔文件已随 Gerber 产出（PTH），若需单独钻孔文件可从 zip 内取 `Drill_PTH_Through.DRL`。

## 7. DFM / layout-lint 复核（2026-10-28 13:15，只读）

### layout-lint

- **score 76 / 100（moderate）**，覆盖完整：9 器件、
  minGap 5.98 mil、overlaps None、outsideOutline [{'type': 'outside-outline', 'a': 'J1'}]、
  tightSpacing None、crossings 1
- crossing：[{"netA": "LED1_A", "netB": "LED1_K", "x": 30.21, "y": 277}]

### PCB DFM（`pcb check`）

`passed = false`（无 error，全部为 WARN）：

| 类型 | 级别 | 说明 |
|---|---|---|
| silk-off-board | WARN | silkscreen text 'J1' extends outside the board outline (text -1293..-1257 × -593..-548 mil, board -1288..585 × |
| power-not-poured | WARN | power net +5V (4 pads) has no copper pour/plane — power should be poured, not carried by thin tracks: `pcb pou |
| width-under-spec | WARN | power net +5V: 5 track(s) below the power-trunk spec width 15.7 mil (thinnest 10 mil) — widen for current capa |
| width-under-spec | WARN | power net GND: 5 track(s) below the gnd spec width 19.7 mil (thinnest 10 mil) — widen for current capacity (ro |

### 结论与修复建议

- DFM **没有 error**；三条 WARN 属可接受但应处理：
  1. **J1 丝印越界**（TH J1 在板外，位号文字跑到板框外）→ 用 `pcb silk-set --ids … --x/--y` 移回板内；
  2. **+5V 未铺铜**（4 pads）→ 设计选择（9–14 mA 走线可承载），若要按 DFM 建议可加 +5V 铺铜；
  3. **2 条线宽低于推荐** → 加宽或确认电流/工艺可接受。
- layout-lint 76 分、1 处 crossing（LED1_A × LED1_K）是自动布线结果，人工复核时可优化。
- 此复核为只读，未修改工程。

### 补充：最小间距 5.98 mil（略低于 6 mil 常规工艺）

layout-lint 报告 `minGapMil = 5.98`，低于多数板厂 6 mil 的最小间距标准（差 0.02 mil）。
这来自全板自动布线，属于**制造前必须处理**的一项：人工微调该处走线，或在板厂确认
5.98 mil 可接受的工艺档位后放行。另外 `outsideOutline` 报告 J1 在板框外（TH 排针逃逸，
设计使然），其位号丝印同时越界（DFM `silkOffBoard`）。

## 8. DFM 修复尝试与最终基线（2026-10-28 13:16–13:20）

- 备份：`.zhigou/artifacts/eev3-before-dfm-fix.epro2`（49,207 B，导出成功）。
- 尝试：J1 位号丝印移回板内（成功）；删除 +5V/GND 走线后用 `route-short --route-power
  --width-power 20` 重布（DRC 仍 0），但引入 `widthMismatches` 4 与 `viaInPad` 1，minGap 仍 5.98。
- **已回退**：从备份恢复为 `zhigou-dual-button-led-eev3-final`（uuid `f178aba5…`），
  `pcb drc` = **passed，0 违规**。
- 最终基线保留原 eev3 状态（DRC 0 + 4 条 DFM WARN）；线宽/过孔/间距修复需人工在 GUI 完成
  （自动重布会在焊盘上放孔并把线宽混接）。
- 证据：`evidence/eev3/final-baseline.json`、`dfm-fix-attempt.json`。

## 9. 丝印修复（只动丝印，不碰走线）与制造文件重导（2026-10-28 13:19）

- 只执行 `pcb silk-set --ids 68c1979920df5098e9 --x -1250 --y -380` 把 J1 位号文字移回板内，
  未改动任何走线；`pcb save → doc reload` 后 **DRC = passed，0 违规**。
- DFM 复验：`silkOffBoard` 已消失；剩 3 条 WARN：`powerNotPoured`（+5V）、`widthUnderSpec` ×2
  （+5V/GND 各 5 条 10 mil 细线）。layout-lint 仍 76（minGap 5.98、1 crossing）。
- 制造文件按修复后状态**重新导出**并覆盖证据包：Gerber 12 条目（含 `GDD` + `Drill_PTH_Through.DRL`）、
  CPL 9 行；摘要见 `manufacturing/manufacturing-summary.json`。

## 10. 生产档案（按 skill 模板）

- 已按 `design-hardware/assets/manufacturing-profile.md` 建立 eev3-final 生产档案：
  `evidence/eev3/manufacturing-profile.md`。
- 关键记录：2 层 / 1 oz / 1.6 mm / 47.84×20.36 mm、2 个 PTH 孔（J1）、0 过孔、HASL/绿油；
  `pcb drc` 0 违规（规则 10 mil）；layout-lint 76（minGap **5.98 mil**、1 crossing）；
  DFM 3 WARN（+5V 未铺铜、2 组 10 mil 电源线）。
- **5.98 mil 已按"推荐值边界"记录**（D1 周边 `LED1_A × LED1_K`）：不违反本工程 DRC，
  但低于嘉立创 6 mil 推荐值 → 待人工微调或向板厂确认，**不私自豁免**。
- 制造文件 / BOM / 库存与本档案一致；实物测试仍 `NOT RUN`。
