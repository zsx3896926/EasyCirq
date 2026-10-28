# 官方 lceda-pro CLI/MCP 四个 partial 工作流的关闭判定（S2）

- 生成：2026-10-28
- 依据：spike #75 的实测回执（`docs/parallel-a2-coverage/coverage-matrix.md` + `docs/evidence/a2-coverage-2026-10-28/`）与已实现的 workaround。
- 结论：W02/W06/W07 判 **covered-with-workaround**；**W03 判 partial + 已接受为可接受已知限制**（几何走官方 GUI / A `pcb dump` 兜底，2026-10-28 owner 确认）。

## 判定表

| ID | 工作流 | #75 判 partial 的原因 | 关闭判定 | 依据 / 残留 caveat |
|---|---|---|---|---|
| W02 | 原理图读 | `sch_Net.getAllNets()` 在该 fixture 返回空 | **covered-with-workaround** | 网表缺口由「导出 Protel 网表 + 解析」补齐，Skill 的 `netlist_diff.py` 已在做；残留：官方无 typed net read，靠网表文本解析 |
| W06 | 批处理/计划应用 | 无 typed batch/事务；超时状态未知 | **covered-with-workaround** | 官方实测「一个 JS 程序内做 10 次读 ≈ 10× 便宜」；残留：CLI 层无事务/idempotency，调用方自行写 journal + 读回校验 |
| W07 | 检查/DRC/DFM | DRC 有返回值形状不符文档；无 DFM | **covered**（DRC）/ DFM 移出官方范围 | 官方 `sch_Drc.check`/`pcb_Drc.check` 实测返回结构化数组（含 warning/error 树）；DFM 属 A 侧 `pcb check` 能力，不计入官方对等 |
| W03 | PCB 读 | 只读到 counts/layers，未 dump outline/copper 几何；单位/锚点未实测 | **partial（已接受限制，2026-10-28）** | 几何走官方 GUI / A `pcb dump` 兜底；不再阻塞 S2 门禁 |

## 为什么 W03 是唯一没关的

- W02/W06/W07 的“partial”本质是**语义缺口 + 已实现的 workaround**，判定即可关闭，不需要再跑新探针。
- W03 的“partial”是**几何完整性未证**：官方侧只验证了「能读到 counts/layers」，没有 dump 出 copper 线段/弧/填充/板框的完整几何，也没测单位与锚点约定。要把它从 partial 转 covered，必须跑一次真实的几何 dump 并写一个单位约定 unit test。

## W03 几何探针：已实跑，仍被「无 PCB 承载 fixture」卡住（更新 2026-10-28 晚）

- 官方 CLI 已实跑确认可用：`lceda-pro.exe`（4.1.78.34f5b8d9）`open --path <copy> --headless` → sessionId → `invoke --session <id> --code "<js>"` → `session close --destroy` 全链路通。
- 几何 API **存在且解析成功**（方法名正确、小写 `eda.pcb_*`）：`pcb_PrimitiveLine.getAll` / `pcb_PrimitiveArc.getAll` / `pcb_PrimitiveVia.getAll` / `pcb_PrimitiveFill.getAll` / `pcb_PrimitivePoured.getAll`；`dmt_EditorControl.openDocument` + `activateDocument` 的激活流程已从 #75 回执确认。
- 卡点：几何读必须**先激活 PCB 文档**；但本机可得的 fixture 都没有 PCB 文档——官方 `example-projects/示例工程_*.eprj2`（快速入门/彩色丝印/3D 外壳）实测 `dmt_Pcb.getAllPcbsInfo()` 与 `dmt_Board.getAllBoardsInfo()` 均返回空（**schematic-only，无 Board/PCB**）。
- 官方 CLI 也**接受 `.epro2`**（A 的 `project export` 格式）——`open --path <x>.epro2 --headless` 成功；但 A 导出的 `.epro2` 在 headless 会话里 PCB 文档树没有 materialize（`getAllPcbsInfo` 仍空），无法承载几何 dump。
- **结论**：W03 仍 partial，但已由 owner（2026-10-28）**判定为可接受已知限制**：几何读走官方 GUI / A `pcb dump` 兜底，不再阻塞 S2。几何 dump API 存在（`pcb_PrimitiveLine/Arc/Via/Fill/Poured.getAll`）+ 激活流程明确（`openDocument`+`activateDocument`），未来若要在 headless 会话完整 dump，仅需一个含 PCB 的原生 `.eprj2` fixture。

## 对 S2「0 空档」的净影响

- 官方侧：W02/W06/W07 已关闭判定（covered-with-workaround/covered），W03 判定为可接受限制（几何走官方 GUI）。
- A 侧（先前已定位）：W08 制造导出缺失、W11 无 MCP（架构事实，不计入对等）。
- 即：S2 门禁已于 2026-10-28 达成（0 空档，W03 为可接受限制），进入 S3。

## 边界 / NOT RUN

- 本轮已实跑官方 `open`/`invoke`/`session close` 全链路 + 几何 API 存在性验证；但未完成真实几何 dump（无 PCB 承载 fixture）。
- 未做：W03 完整几何 dump、真实工程端到端、制造导出实跑、硬件实测。
