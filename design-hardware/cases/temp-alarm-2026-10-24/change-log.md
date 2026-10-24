# 实战错误清单与修复过程（temp-alarm，2026-10-24）

> 本文件是回归案例的事实底稿。只记录有证据或明确标为推断的内容；不把“时间顺序”写成“因果证明”。

## 1. 项目结果

- 原理图：26 个真实库器件，`sch drc` 0 违规，已保存。
- PCB：26 个器件，板框 3577.55 × 2176.76 mil（90.87 × 55.29 mm），GND 双层铺铜，多数网络已布线。
- 最终 `pcb drc`：18 条（16 Clearance + 2 Connection），`passed:false`，不可下单。
- 制造包：无 Gerber/钻孔/CPL；`.epro2` zip 完整但 `restoreVerified:false`；库存/SMT 未实时核对。

## 2. 错误与门禁

| # | 发生在 | 事实 | 证据 | 对应门禁 / R |
|---|---|---|---|---|
| 1 | 开工 | 没有 design-brief；尺寸上限、外壳/安装孔、装配方式、数量/预算、环境/精度未记录 | 项目工作目录无 `design-brief.md`；最终板框来自 `outline-fit --margin 100`，不是需求 | G0 / R1、R2、R5、R6、R7 |
| 2 | 方案 | 层数（2 vs 4）未在布线前决策；只有遇到布线瓶颈后才讨论 4 层 | 交接文档“需要你确认 4 层”出现在 DRC 18 之后 | G4 / R8 |
| 3 | 首次导入 PCB | 15:37 导入 28 件（含 J2、D2）；J2 在 15:45、D2 在 15:48 才删 | `pcb-import.log`、`pcb-list-after-j2.json` | G1 / R45 |
| 4 | 删 J2 后 | `pcb import-changes` 返回 `noChanges:true`、28→28；PCB 仍含 J2；`pcb-drc-5.json` 报 `PCB and schematic netlist does not match` | `pcb-import-after-j2-removal.log`、`pcb-list-after-j2.json`、`pcb-drc-5.json` | G1 / R24、R45 |
| 5 | 删件记录 | J2/D2 的手动 delete/track-delete/rip-up 只在会话记录里，evidence 目录没有删除回执；没有 change-impact | evidence 目录无对应输出 | G1 / R45 |
| 6 | 布局 | 15:38:01 `outline-fit --margin 100` 得到 90.87×55.29 mm；utilBefore 0、parts 28 | `pcb-outline-fit.json` | G3 / R26 |
| 7 | 布局 | 15:38:28 `pcb layout-lint` = score 48/100、13 crossings、28 comps、0 short/overlap/off-board/tight | `pcb-layout-lint-2.log` | G3 / R27、R28 |
| 8 | 布线 | 15:38:54 仍执行 `route-short --apply`（74 routes、26 vias）；布局未冻结 | 过程日志；R1/R2 15:50:47 才移动 | G3 / R28、R33 |
| 9 | 电源/地 | `power-pour` 创建 4 个铺铜（GND L1、GND L2、+5V L1、VREF L1）；创建回执 priority 1/1/2 且 `priorityVerified:false`；重载后 `pour-list` 读到 GND L1 priority=3 | `pcb-power-pour-apply.log`、`pcb-pour-list.json` | G4 / R29、R30 |
| 10 | 铺铜后 | 首次 DRC = 30（3 Clearance + 27 Connection）；**之前没有 DRC 基线，27 条断连与铺铜的因果只能写“时间顺序推断”** | `pcb-drc-3.json` | G4 / R29、R31 |
| 11 | 自动布线 | `route-short --route-power`：73 routes（GND 45、+5V 21、VREF 7；2 条 VREF 失败）、drawn 71、vias 14；GND 走线是 20 mil，不是“细线” | `pcb-route-power-apply.log` | G4 / R29、R32 |
| 12 | 铺铜板上布电源 | 随后 DRC 93 = 71 Clearance + 22 Connection；其中 net=GND 的 Clearance 68 条 | `pcb-drc-4.json`、`pcb-drc-full.json` | G4 / R29、R32 |
| 13 | 布局变更 | 布线已开始后，R1/R2 15:50:47 才从 `(1359.2,-1326.9)/(126.0,-410.5)` 移到 J1 旁 `(820,-1750)/(950,-1750)`；D1_N4 长度 2519.2→343.8 mil，D1_N3 1234.2→493.5 mil | 过程日志、`pcb-tracks-*` | G3 / R28、R33 |
| 14 | DRC 打地鼠 | 完整序列 93→50→31→28→23→31→28→22→16→18；**非单调**，最终 18 比上一轮 16 更差 | `pcb-drc-3`…`pcb-drc-11`、`pcb-drc-full.json` | G5 / R32 |
| 15 | 最终 DRC | 18 条 = 16 Clearance + 2 Connection；6 条在 J1 的 VBUS(D1_N1)/CC1(D1_N3)/CC2(D1_N4) 焊盘行 | `pcb-drc-11.json` | G5 / R31、R33 |
| 16 | 原理图检查 | 最终 `sch check` 10 findings：1 marker-overlap + 1 out-of-sheet + 2 designator-wire-overlap + 1 missing-partition + **5 peripheral-not-direct**（J1/C1/RV1/U1/Q1）；0 floating pin | `sch-check-final2.json` | G2 / R18、R23、R25 |
| 17 | 部分写入 | `block-apply` autoconnect 27 succeeded / 1 failed（J1:DN2）；首轮 autoconnect `ok:false, partial:true`，4 条失败；`--replace` 重试 52 succeeded | `block-usb-apply.json`、`autoconnect-apply.json` | G2 / R24 |
| 18 | 极性 | D5 曾反接：`page-d5-check.json` 中 `pin2 K = PWR_LED_A`、`pin1 A = ""`；修正后 `pin2 K = GND`、`pin1 A = PWR_LED_A` | `page-d5-check.json` | G2 / R13、R25 |
| 19 | 证据截断 | `Tee-Object ... | Select-Object -First 80` 产出 `pcb-drc-2.json` 2152 bytes（停在数组中间）；完整重跑为 238706 bytes | `pcb-drc-2.json` vs `pcb-drc-full.json` | G5 / R40 |
| 20 | 制造交付 | 无 Gerber/drill/CPL；BOM 21 行 26 件全部有 C 号（未核对库存/SMT）；`.epro2` 364,810 bytes、SHA-256 `6dcf4d87…800d9e`、`zipIntegrityVerified:true`、`restoreVerified:false`；有测试计划 | `BOM.csv`、`project-export-2.log`、`docs/test-plan.md` | G6 / R12、R35、R40、R43 |

## 3. 修复过程（实际做了什么，为什么没闭合）

1. **删可选件简化**：删 J2 测试排针和 D2 USB 数据 ESD。J2 在原理图和 PCB 都删了，但 `pcb import-changes` 不会自动删除 PCB 已放置件，返回 `noChanges:true`；J2 仍在 PCB 列表里。后续手动删除没有留下 evidence 回执，也没有 change-impact。→ G1 仍 `BLOCKED`。
2. **补 GND 焊盘连接、削 USB-C slot 间距错误**：这两类 DRC 消除了，但新的 Clearance/Connection 仍在。→ G5 仍 `BLOCKED`。
3. **铺铜后再布线**：先 `power-pour` 再 `route-short --route-power`，导致 GND 在铺铜板上被布成 20 mil 走线，DRC 从 30 升到 93。之后逐条挪线，序列 93→50→31→28→23→31→28→22→16→18，反复且最后回升。→ G4/G5 均未过。
4. **布局后移 R1/R2**：把 CC 电阻移到 J1 旁是正确方向，但发生在布线开始之后，已布线路由结论作废。→ G3 的“布局冻结”缺失。
5. **原理图整理**：填了图签、导出了 PNG、补了部分连接；剩余 10 条风格/结构警告没有清理，只记录为豁免候选。→ G2 只能 `PASS_WITH_WAIVER`，不能 `PASS`。

## 4. 如果重来，门禁会在哪里拦住

- **G0**：先问清尺寸上限、外壳/安装孔、装配方式（手焊/ SMT）、数量/预算、环境/精度；`outline-fit` 的结果不能反推需求。
- **G1**：冻结必需/可选件；J2/D2 若在冻结后删除，必须填 change-impact，并回读 PCB 列表证明已消失。
- **G2**：`sch drc` 0 之外，还要 `sch check` 电气类 0、网表 diff match、单引脚网审计、图签、实际看图；5 条 peripheral-not-direct 要么改直连，要么带理由豁免。
- **G3**：`layout-lint` 分数/交叉达标、目标板框、安装孔、连接器逃逸（CC/TVS/ESD ≤5 mm、避开 slot）、布局冻结后才布线。
- **G4**：先声明 2/4 层与电源/地策略，再铺铜；GND 双层铺铜 + 缝合；不在铺铜板上用 `--route-power` 布 GND 细线/走线；过孔 fresh readback。
- **G5**：`pcb drc` `passed:true` 且 0 Connection；关键网逐条 `net-path`；save→reload→readback；丝印整理；连续 3 轮改善 <30% 就停，重排/4 层/拆页/如实报告。
- **G6**：Gerber/钻孔/CPL 由 GUI 导出并登记；BOM 每行有 C 号；工艺档案；`.epro2` 恢复演练 `restoreVerified:true`；库存/SMT 核对时间；测试计划。

## 5. 边界

- 本案例只读证据，没有重新跑 EDA；所有“修复后”结论只到“证据显示”。
- 库存、价格、SMT 可贴状态不是 2026-10-24 的实时值，必须下单前重查。
- NTC 短路不报警是已知失效边界；NTC 开路会报警。
- 该板不是可制造状态；不要引用本案例的 DRC 数字宣称已修好。
