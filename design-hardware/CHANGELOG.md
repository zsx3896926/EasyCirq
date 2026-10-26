# 变更记录

## 0.8.0 — 2026-10-26

- 新增独立 Windows 管理入口和 Python 更新器：安装、检查稳定版、升级、修复、回退、中断恢复。
- 托管安装记录逐文件哈希；整包校验、暂存验证、备份切换、并发锁；拒绝隐式覆盖本地修改。
- 识别 Claude / Codex / WorkBuddy 默认安装路径及 Codex 旧目录重复安装。
- 新增版本化发布包构建、Windows/Linux CI 和正式 Release 资产附加工作流。
- 不创建常驻进程、不自动升级 EDA 或下单；线上更新需维护者发布带资产的稳定 Release 后开通。


## 0.7.0 — 2026-10-26

第七轮整合：把 round7 排版引擎、确定性 design engine 与 round6 G0–G6 门禁合并为单一版本。

### 新增/合并

- **G0–G6 阶段门禁**（round6）：`references/design-gates.md`、`assets/design-state.example.json`、`scripts/gate_check.py`、temp-alarm 回归案例、BOM/pinmap 检查与 5 份 docs 模板。
- **原理图排版引擎**（PR #11）：真实几何 → 功能模块 → `layout-plan` → 合页 → 独立质量检查；整页 compose 仍受 D4/KT-0805R off-grid 限制，未证明一键 apply。
- **确定性 design engine**（PR #12）：离线 IR、几何/身份审计、标签规划、PCB/制造检查；真机仅验证 9 个 Name/Designator 属性移动。
- **doctor_env 双路线诊断**：`lceda-pro` 与 `easyeda-agent` 分开报告；任一绿色不再代表另一条路线就绪；新增 easyeda health 解析与回归测试，识别 `found`（内层 daemon `ok`）为已连接。
- README、readme-technical、handoff 同步测试数字、F1 rev3 21 器件与验证日期。

### 边界

- 整页排版 apply、原生 netlist diff、Gerber/CPL/BOM 导出、下单/SMT、固件烧录、实物/热/EMC、全在线 GUI 仍未完成。
- 本次整合只做版本/文档/诊断收口，不代表上述未完成项已通过。

## 0.6.0 — 2026-10-24

第六轮：把「室内温度报警小板」实战复盘中的门禁缺口，落成可离线复核的规则、模板与回归案例。

### 新增

- **G0–G6 阶段门禁**：[references/design-gates.md](references/design-gates.md)。每个门禁写目的、必需输入、当前 easyeda-agent v1.14.0 真实命令、退出条件、证据文件、豁免规则与实战反例。
- **项目状态载体**：`assets/design-state.example.json`（schema `design-state/v1`），集中记录需求、功能冻结、原理图/布局/布线/制造状态、豁免、假设与风险；`scripts/gate_check.py` 只读证据目录，输出 `PASS / PASS_WITH_WAIVER / BLOCKED / UNSUPPORTED`，退出码 0/1/2。
- **布线与工具约束**：[references/pcb-routing-strategy.md](references/pcb-routing-strategy.md)（2 层 vs 4 层、电源/地策略、布线计划、连接器逃逸）、[references/tool-gotchas.md](references/tool-gotchas.md)（前台要求、铺铜优先级、`route-short --route-power`、`bom enrich`、`pcb import-changes`、JSON/human 混行等）。
- **模板**：`assets/design-brief.md` 扩充尺寸/装配/预算/接口/测试点/阈值交互；新增 `assets/routing-plan.md`、`assets/design-calc.md`、`assets/docs/` 下的机械、热设计、丝印装配、制造包、验证模板，以及 `assets/parts.example.json`、`assets/pinmap.example.json`。
- **离线检查脚本**：`scripts/bom_check.py`、扩展 `scripts/pin_plan_check.py`（可选 `pinmap`）、`scripts/skill_selftest.py`。
- **回归案例**：[cases/temp-alarm-2026-10-24/README.md](cases/temp-alarm-2026-10-24/README.md)。dry-run 预期 G0/G1/G3/G4/G5/G6 为 `BLOCKED`，G2 为 `PASS_WITH_WAIVER`。

### 修改

- `SKILL.md`：新增阶段门禁入口与硬规则（G2 未过不进 PCB、G3 未过不布线、G5 未过不谈制造、G6 未过不说可打样/可量产）。
- `references/agent-collaboration.md`、`part-selection.md`、`lcsc-sourcing.md`、`pcb.md`、`schematic.md`、`eda-execution.md`、`beginner-journey.md`：补逐针回读、停止规则、选型/库存/SMT 核对、工具陷阱和新手标定说明。

### 边界

- 本轮只做离线文档、脚本和证据 dry-run：未运行 EDA、未重画板、未导出 Gerber、未下单。
- `gate_check.py` 只读证据；当前 CLI 不支持的检查项标 `UNSUPPORTED` 或要求人工证据，不默认 `PASS`。
- 回归案例的预期结果来自真实项目证据，不代表该板已可制造或已实测。
