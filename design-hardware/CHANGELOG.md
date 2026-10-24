# 变更记录

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

- `SKILL.md`：新增阶段门禁入口与硬规则（G2 未过不进 PCB、G3 未过不布线、G5/G6 未过不谈制造）。
- `references/agent-collaboration.md`、`part-selection.md`、`lcsc-sourcing.md`、`pcb.md`、`schematic.md`、`eda-execution.md`、`beginner-journey.md`：补逐针回读、停止规则、选型/库存/SMT 核对、工具陷阱和新手标定说明。

### 边界

- 本轮只做离线文档、脚本和证据 dry-run：未运行 EDA、未重画板、未导出 Gerber、未下单。
- `gate_check.py` 只读证据；当前 CLI 不支持的检查项标 `UNSUPPORTED` 或要求人工证据，不默认 `PASS`。
- 回归案例的预期结果来自真实项目证据，不代表该板已可制造或已实测。
