# 第六轮变更计划：把实战教训变成阶段门禁

- 任务书：`C:\Users\jlc\work\temp-alarm-20261024\docs\skill-optimization-task.md`（2026-10-24 更新版）
- 分支：`feat/design-gates-round6`（基于 `origin/main` `fe950d3`）
- 隔离 worktree：`C:\Users\jlc\work\hds-round6`
- 只改 Skill 文档/脚本/案例；不改嘉立创 EDA 工程 `test`；不画板、不导出 Gerber、不下单。

## 1. 设计原则

1. **门禁是证据门，不是审批门**：在已授权范围内自查、记录、继续；只在证据缺失或门禁失败时停住依赖链路。豁免必须带理由落盘。
2. **不另立阶段体系**：沿用 `SKILL.md` 的 S0–S5、四个可见检查点与五个状态词；G0–G6 是这些阶段的退出条件。
3. **状态文件统一为 `design-state.json`**（schema `design-state/v1`，snake_case）。早期草案的 `gates.json` / `design-gates/v1` / camelCase 不再识别；迁移说明只保留在 `design-gates.md` 的变更记录里。
4. **四结论词固定**：`PASS` / `PASS_WITH_WAIVER` / `BLOCKED` / `UNSUPPORTED`。`PASS_WITH_WAIVER` 不是 `PASS`；`UNSUPPORTED` 必须进 `not_checked`，不得默认通过。
5. **命令只写真实存在的**：以 easyeda-agent v1.14.0 的 `--help` 为准（证据：`docs/evidence/round6-2026-10-24/cli-help.txt`、`cli-subcommands.txt`）。Gerber/钻孔/CPL 无 CLI/typed action，标 `UNSUPPORTED` 能力。
6. **门禁可离线复核**：`gate_check.py` 只读证据目录与状态文件，不连 daemon、不写工程；缺证据 `BLOCKED`。
7. **不重复既有内容**：能在 `pcb.md`、`pcb-routing-details.md`、`lcsc-sourcing.md` 说清的，新文档只引用并补退出条件。

## 2. 新增文件

| 文件 | 作用 | 要点 |
|---|---|---|
| `references/design-gates.md` | G0–G6 门禁主文档 | 每门禁：目的、必需输入、真实 CLI、退出条件、证据、豁免、实战反例；与 `gate_check.py` 同名同键 |
| `references/pcb-routing-strategy.md` | 层数/电源地/布线计划 | 2 vs 4 层矩阵；一层一网或铺铜优先级；GND 双层铺铜+缝合；不在铺铜板上 `--route-power`；连接器逃逸；停止规则 |
| `references/tool-gotchas.md` | 工具陷阱表 | 现象→原因→正确动作→证据/边界；前台按动作区分；JSON/human 混行；`import-changes` 不删件；`bom-enrich` None |
| `assets/design-calc.md` | 设计前计算模板 | 阈值/回差、NTC 自热/最大电流、LED/蜂鸣器、二极管/LDO 压降、连接器载流；E2/E3 标注 |
| `assets/routing-plan.md` | 布线计划模板 | 层/通道/过孔/net class/顺序/停止条件/关键网证明 |
| `assets/docs/mechanical.md` 等 5 份 | 机械、温度传感器、丝印装配、制造包、验证 | 表格化记录 + 状态列 + 开放项；不填假值 |
| `scripts/gate_check.py` | 离线门禁复核 | 读 evidence + `design-state.json`；输出四结论；退出码 0/1/2；证据带 sha256/mtime/format |
| `scripts/bom_check.py` | parts.json 结构检查 | role/MPN/封装/装配/C 号/库存时间/备选；不访问网络 |
| `scripts/skill_selftest.py` | Skill 自检 | 必需文件、相对链接、门禁命名、案例回归、脚本编译 |
| `assets/design-state.example.json` | 状态模板 | 需求/功能冻结/原理图/布局/层叠/布线/制造/采购/假设/风险/未决 |
| `assets/parts.example.json`、`assets/pinmap.example.json` | 零件与引脚图示例 | 明确“示例，未核对”；引脚图含 NC 与电源行 |
| `cases/temp-alarm-2026-10-24/` | 回归案例 | 证据快照、预期、豁免、错误清单、测试计划 |
| `tests/test_gate_check.py`、`test_bom_check.py`、`test_pinmap.py` | 新增测试 | 合成夹具 + 真实案例；不依赖 EDA |
| `CHANGELOG.md`、`.version` | 版本 0.6.0 | 安装目录同步时一并核对 |

## 3. 修改文件

| 文件 | 改动 |
|---|---|
| `SKILL.md` | 新增 §3.2 阶段门禁入口、G0–G6 键名、硬规则、`gate_check.py` 用法；按需读取表补新文档；§6 补三个离线脚本边界 |
| `assets/design-brief.md` | 补尺寸/外壳/安装孔、装配方式、数量/预算、USB 角色、测试点、显示、固件、阈值交互、报警行为、环境/精度；尺寸示例改为 `pending`，不再把 `outline-fit` 结果当用户上限 |
| `references/agent-collaboration.md` | 逐针回读、超时/部分写入、DRC 3 轮停止规则、证据协议、G1 后变更影响 |
| `references/part-selection.md` | 先定手焊/SMT 再定封装；手焊默认 0603；C 号/库存/SMT 分类分开 |
| `references/lcsc-sourcing.md` | 先导出 `--enrich=false` 原始 BOM；enrich 失败不阻断；库存/SMT/MOQ 分列 |
| `references/pcb.md` | 连接器旁无源件 ≤5 mm、TVS/ESD 逃逸、slot 禁布、安装孔、丝印极性、测试点可达；指向 routing strategy |
| `references/schematic.md` | 直连 vs 同网标签风格先定；`peripheral-not-direct` 豁免记录；G2 退出条件 |
| `references/eda-execution.md` | 指向 tool-gotchas；补前台/超时/`--doc` 单点说明 |
| `references/beginner-journey.md` | 电位器标定、无显示限制、NTC 短路不报警、测试点、装配难度 |
| `docs/round6-change-plan.md` | 本文件，按新契约重写 |

## 4. 门禁模型

| 门禁 | 阻塞条件（摘要） | 主要证据 |
|---|---|---|
| G0 需求 | 12 个需求字段缺失/`pending`，或 blocking open item | `design-state.requirements` |
| G1 功能冻结 | 未冻结、必需件为空，或冻结后增删无 `change_impact` | `function_freeze`、`change-impact.md` |
| G2 原理图 | `sch drc` fatal/error>0、电气类 check>0，或网表/图签/看图/单脚网证据缺失 | `sch-drc`、`sch-check`、`netlist_diff`、`schematic_png` |
| G3 布局 | score<60、crossings>8、几何错误、无目标板框/安装孔/冻结 | `pcb_layout_lint`、`pcb_board`、`pcb_mount_holes` |
| G4 电源地 | 层数与板不符、策略未声明、GND 未双层铺、过孔 stale、规则未记录 | `pcb_pours`、`pcb_vias`、`pcb_board`、`pcb_check` |
| G5 布线 | `pcb drc` 未 `passed:true` 或有 Connection、关键网未证明、无保存重载、丝印压焊盘、DRC 平台期未停 | `pcb_drc`、`net_path`、`reopen_check`、`silk_align` |
| G6 制造 | Gerber/钻孔/CPL 缺、BOM 缺 C 号、工艺档案缺失、恢复演练未做、库存/SMT 未核、无测试计划 | 制造文件、`bom`、`project_export`、`sourcing` |

判定优先级：未豁免失败 → `BLOCKED`；无可判定路径 → `UNSUPPORTED`；有生效豁免 → `PASS_WITH_WAIVER`；全部通过 → `PASS`。

## 5. gate_check 接口

```text
python scripts/gate_check.py --project <name> --evidence-dir <dir>
  [--project-dir <dir>] [--design-state <file>] [--brief <md>]
  [--waiver GATE[:CHECK]:REASON ...] [--waiver-file <json>]
  [--file ROLE=PATH ...] [--min-layout-score 60] [--max-crossings 8]
  [--strict-advisory] [--json] [--out <report.json>] [--quiet]
```

- 退出码：0 无 `BLOCKED`/`UNSUPPORTED`；1 至少一个；2 参数/IO/schema 错误。
- 证据格式：JSON 优先；识别 `sch drc`/`sch check`/`pcb layout-lint` human 摘要并标 `format:"text"`；截断/损坏 → `BLOCKED`，不崩溃。
- 每个结论带 `path/sha256/mtime/format/candidates/selected_because`；`staleRisk` 非空只作警告，不作为权威证据。
- 缺检查项输出 `next_command`；未使用的豁免标 `unused`；CLI 不支持项进 `not_checked`。

## 6. 验收映射

1. 文档一致：`tests/test_skill.py` 链接检查 + `scripts/skill_selftest.py` 门禁命名检查。
2. `python -m unittest discover -s tests` 全绿（记录数量与退出码）。
3. 回归案例 dry-run：G0/G1/G3/G4/G5/G6 `BLOCKED`，G2 `PASS_WITH_WAIVER`；退出码 1。
4. 安装目录备份 + 逐文件哈希核对。
5. 提交并推送 `feat/design-gates-round6`，报告 SHA。

## 7. 非目标

- 不改 EDA 工程、不重画板、不导出 Gerber、不下单。
- 不新增 Skill 之外的执行器能力；不声称 CLI 有但实际没有的命令。
- 不把门禁写成逐项人工审批；不静默削弱既有规则。
