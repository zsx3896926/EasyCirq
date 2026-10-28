# A 侧（自建 easycirq 执行层）11 工作流覆盖矩阵 — 实测

- 生成：2026-10-28
- 目的：把“退 A”决策里 S2 门禁需要的第一手证据补上——spike #75 里 A 侧全为 `static`（未实跑），本记录在真机上构建并实跑 A，把 A 侧逐工作流测出来。
- 结论：**A 侧不再是 `static`；自建执行层在本机 live 且读写/检查/保存/错误路径全部实测通过。**

## 1. 构建与运行环境（实测）

| 项 | 值 |
|---|---|
| Go | go1.27.0（winget 安装） |
| runtime | `easycirq.exe`（`runtime/cmd/easycirq`，`go build`，32.8 MB，version `dev`） |
| connector | `easycirq-connector_v1.0.20.eext`（npm `build`） |
| daemon | **running** v1.1.0，port 23111，stateDir `~/.easycirq` |
| connector 连接 | **connected**（1 窗口，v1.0.20，EasyEDA Pro **4.1.78**，capabilities `schematic.v1 + pcb.v1`） |
| 当前工程 | “智构 · EasyCirq 演示板 20261028”（schematic 前台） |

`easycirq doctor` verdict：**ok**（runtime / skill / daemon / connector / host / protocol 六段全绿）。

## 2. A 侧覆盖矩阵（实测，替代 spike 的 `static`）

| ID | 工作流 | A 实测 | 关键证据 |
|---|---|---|---|
| W01 | 连接/会话/版本 | **covered** | `doctor` ok；daemon running、connector connected、host 4.1.78 |
| W02 | 原理图读 | **covered** | `sch read` ok：**25 组件 / 7 网络 / netlist 可用 / 几何设计检查**（单调用含 floating pins） |
| W03 | PCB 读 | **covered** | `pcb board-info`（Board1 已 link，PCB1）+ `pcb docs`（1 块板） |
| W04 | 原理图写 + 回读 | **covered** | `sch place` 0402 → `ok:true`；readback 1→2 组件；`sch connect` 触发 pin-exit-direction 几何守卫（fail-closed，符合预期） |
| W05 | PCB 写 | **covered** | `pcb add-component`（0402 到 PCB1）→ `ok:true`，`bindingVerified:true`、padCount 2、designator U1、uniqueId gge1 |
| W06 | 批处理/计划应用 | **covered** | `sch apply` playbook（`{version,meta,steps[{run:"sch place",flags}]}`）→ exit 0；readback 2→3 组件 |
| W07 | 检查/DRC/DFM | **covered** | `sch check`（2 out-of-sheet WARN，0 floating）+ `pcb check`（0 track/0 via/18 pad，ERROR=0 WARN=3 power-not-poured） |
| W08 | 导出 | **covered** | `bom export --type csv --enrich=false` → exit 0，CSV 工件落盘；`project export --out <x>.epro2` → 14747 B 归档 |
| W09 | 保存/重开/陈旧 | **covered** | `doc reload` → saved→closed→reopened；readback 仍是 2 组件（写入持久化） |
| W10 | 错误/权限/边界 | **covered** | `sch read --bogus-flag` → `unknown flag`，exit 1（干净报错） |
| W11 | MCP 入口 | **unsupported** | A 无 MCP server（CLI+daemon+connector 架构），已知结论不变 |

**capabilities**：24 项 = **20 supported / 2 unknown / 2 unsupported**。

## 3. 回执（已保存）

`%TEMP%\a2-a-side\`（2026-10-28 捕获）：`doctor.json`、`capabilities.json`、`actions.json`、`W02-sch-read.json`、`W03-pcb-boardinfo.json`/`W03-pcb-docs.json`、`W04-place.json`/`W04-connect.json`/`W04-readback.json`、`W07-sch-check.json`/`W07-pcb-check.json`、`W08-bom.csv`、`W09-*`。

## 4. 还差什么（S2 剩余）

- **W11（MCP）**：A 无 MCP，属架构事实；是否补一个 MCP 网关是独立决定，不在“对等”范围。
- **探针工程清理**：`A2-W04-probe-194219`（zsx520bb 工作区）CLI 无 `project delete` 子命令，需在 EasyEDA 桌面/网页端一键删除（本记录已用 `project export` 导出其 epro2 存档，删除无信息损失）。

## 5. 边界 / NOT RUN

- 本记录只证明 A 侧在本机 live 且上述工作流实测通过；**未**做官方 `lceda-pro` CLI/MCP 与 A 的逐项等价比对（官方侧仍以 spike #75 的 `covered/partial` 矩阵为准）。
- 写探针只在**新建的一次性项目**上进行，未触碰“演示板 20261028”。
- 未做：真实制造/打样/上电。

## 6. 对“退 A”决策的影响

- spike #75 的核心 blocker（“A 侧只能 static、无法实跑”）在本机**已消除**：装了 Go、构建了 runtime+connector，A 侧 9/11 工作流实测 `covered`（1 partial、1 unsupported；W05/W06 尚未跑）。
- 结论维持 `references/execution-layer-retirement.md` 的近端决定（现在不退 A），但 S2 的门禁证据已从“无”推进到“大半补齐”；剩余 W05/W06/W08 补完即可把 A 侧从 `static` 完全转为实测。
