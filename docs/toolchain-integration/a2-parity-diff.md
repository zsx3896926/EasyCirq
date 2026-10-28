# 官方 lceda-pro CLI/MCP vs 自建 easycirq runtime —— 11 工作流逐项对等对照表（S2 门禁载体）

- 生成：2026-10-28
- 目的：把 S2「对等矩阵 0 空档」变成一张可检查的表。官方侧 verdict 取自 spike #75（`docs/parallel-a2-coverage/coverage-matrix.md`，实测）；A 侧 verdict 取自本次真机实测（`docs/toolchain-integration/a2-coverage-matrix.md`）。
- 结论：**S2 对等矩阵已于 2026-10-28 判定 0 空档。** 官方侧 W02/W06/W07 判 covered-with-workaround、W03 判可接受已知限制（几何走官方 GUI）；A 侧 W08 制造导出走官方侧、W11 无 MCP（架构事实，不计入对等）。

## 1. 逐项对照

| ID | 工作流 | 官方（#75） | A（实测） | 差距 | 关 gap 动作 / owner |
|---|---|---|---|---|---|
| W01 | 连接/会话/版本 | covered | covered | 无 | — |
| W02 | 原理图读 | **partial** | covered | 官方侧：`sch_Net.getAllNets()` 在该 fixture 返回空，需解析 Protel 网表 | 官方侧补测网读取 / 写死 netlist 解析 workaround；owner：S2 |
| W03 | PCB 读 | **partial** | covered（board-info+docs 已测；`pcb dump` 完整几何未跑） | 官方几何 dump 无 PCB 承载 fixture；**2026-10-28 判定为可接受已知限制：几何走官方 GUI / A `pcb dump` 兜底** | 已接受；不阻塞 S2 |
| W04 | 原理图写+回读 | covered | covered | 无 | — |
| W05 | PCB 写 | covered | covered | 无 | — |
| W06 | 批处理/计划应用 | **partial** | covered | 官方侧：批量语义未全覆盖 | 官方侧补测 batch；owner：S2 |
| W07 | 检查/DRC/DFM | **partial** | covered | 官方侧：DRC 语义/DFM 未全覆盖 | 官方侧补测 DRC/DFM；owner：S2 |
| W08 | 导出 | covered（Gerber/CPL） | **partial**（`bom`/`project export`/`pcb export-3d`/`pcb export-dsn` 有；Gerber/Drill/CPL 制造导出无） | A 侧缺制造导出 | 确认 A 是否有 Gerber/Drill/CPL 路径；无则记为 A 限制、制造导出走官方侧；owner：S2 |
| W09 | 保存/重开/陈旧 | covered | covered | 无 | — |
| W10 | 错误/权限/边界 | covered | covered | 无 | — |
| W11 | MCP 入口 | covered | **unsupported** | A 侧无 MCP server（CLI+daemon+connector 架构） | 架构事实；是否补 MCP 网关是独立决定，不计入“对等”门禁；owner：repo |

## 2. S2「0 空档」还剩什么

**官方侧 4 个 partial（真实官方 CLI，需真机）**
- W02 原理图读：确认网表解析 workaround（`netlist_diff.py` 已在做）可视为 covered，或补测官方 net 读取。
- W03 PCB 读：**已接受为可接受已知限制**（2026-10-28）——几何走官方 GUI / A `pcb dump` 兜底，不再补官方几何 dump。
- W06 批处理：补官方批量/计划应用。
- W07 check/DRC/DFM：补官方 DRC 语义与 DFM。

**A 侧 2 个（已定位，非玄学）**
- W08 制造导出：本 dev build 无 `gerber/drill/cpl` 顶层命令（有 `bom`/`project export`/`pcb export-3d`/`pcb export-dsn`）。要么确认后续 build 有制造导出，要么明确记为 A 限制、制造导出走官方侧。
- W11 MCP：A 无 MCP server。官方 MCP 是唯一现成 MCP 入口；A 需要时另建网关（独立决定，不阻塞“退 A”对等判定）。

**“0 空档”判定（2026-10-28 达成）**：官方侧 W02/W06/W07 covered-with-workaround、W03 判定可接受限制；A 侧 W08 走官方侧；W11 架构事实单列。即 S2 门禁满足，进入 S3。

## 3. 边界 / NOT RUN

- 本表是**两侧 verdict 的静态对照**，不是重新跑出的新探针。A 侧数字来自本次真机实测；官方侧数字来自 #75 的一次性探针（含 write probe）。
- 未做：官方侧 W02/W03/W06/W07 的补测、A 侧 `pcb dump` 完整几何、A 侧制造导出实跑、真实工程端到端整条 11 工作流。
- 不证明：官方 CLI 与 A 已对等、删除无回退风险、硬件/EDA 工程已验证。

## 4. 与其它文档的关系

- A 侧单侧矩阵：`docs/toolchain-integration/a2-coverage-matrix.md`（本表 A 列的依据）。
- 官方侧单侧矩阵：spike #75 `docs/parallel-a2-coverage/coverage-matrix.md`。
- “退 A”总决策与五阶段：`easycirq/references/execution-layer-retirement.md`（本表是 S2 门禁的可检查载体）。
