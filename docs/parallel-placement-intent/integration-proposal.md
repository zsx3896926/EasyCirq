# 集成建议：接入 `design_engine` 模块计划/候选与 `easycirq_mcp` 工具层

本文件只给**建议**，不修改任何共享文件。任务 L 的交付是独立 CLI 包
（`easycirq/scripts/placement_intent/`）、测试、冻结基准与本目录文档；
`design_engine`、`pcb_apply_plan.py`、`easycirq_mcp`、`SKILL.md`、`references/*`
均**未修改**，由后续集成 PR 实施本文件的方案。

## 1. 与 `design_engine` 的关系：只做“意图前置校验”，不替代候选/门禁

### 1.1 定位

`placement_intent` 校验的是**放置意图本身是否自洽**（HMT 树 + CCG 相对约束 + unknown），
它不生成绝对坐标、不做硬合法性检查、不比较 HPWL、不写工程。因此它适合放在
`pcb-candidates` / `pcb-template-plan` / `pcb_apply_plan --module-plan` **之前**：

```text
模块计划 / 模板相对偏移 / 人工意图
        │  （映射，集成 PR 实现）
        ▼
placement_intent validate / plan     ← 本任务：只读、离线、0 EDA
        │  planned_with_scope / review_required / invalid_input / unknown
        ▼
design_engine pcb-candidates / pcb-template-plan   ← 既有：板内/重叠/固定/edge/keepout 硬过滤
        │  routing_verified=false（不变）
        ▼
pcb_apply_plan --module-plan → validate_placement → typed pcb modify → 回读
```

**约束**：`placement_intent` 的 `planned_with_scope` **不能**替代
`validate_placement` 的硬合法性（板内、同层重叠、固定/锁定、edge、keepout、spacing），
也不能替代 fresh dump 对照、preflight 或 DRC。它只证明“意图自洽”。

### 1.2 输入映射：module-plan / 模板 → `easycirq.placement-intent.input/v1`

| placement_intent 字段 | 来源 | 映射注意 |
|---|---|---|
| `project.project_id/revision` | `design-state.json` 的 `project.name/uuid` + 修订号；或调用方声明 | 只作身份/追溯，不参与几何 |
| `snapshot.captured_at/source_type/missing_fields` | 模块计划生成时间、`derived`/`manual`；无 hash 时 `content_sha256:null` + `missing_fields` 显式声明 | 缺失 → `incomplete`，不伪造 hash |
| `snapshot.content_sha256` | 源 dump/模块计划的 SHA-256（派生数据） | 与 `provenance.sources[].sha256` 含义不同，不可混用 |
| `units.length` | module-plan/模板用 mil → `"mil"`；dump 为 mm → `"mm"` | 读取时一次换算；不猜单位 |
| `board.width_mm/height_mm` | dump `outline.bbox` 的宽高 | 缺失则不填 → `board_unknown` |
| `board.fixed_positions_mm` | 既有 fixed/locked 器件与实测位姿 | 仅用于固定冲突报告，不参与求解 |
| `modules[].id` | `mod:<zone.id>`；根为 `mod:board` | 模块 id 与元件 id 同一命名空间，需加前缀避免撞名 |
| `modules[].parent/children` | 根 → zones（module-plan 无更深层级时可只做一层） | 单根；叶子才可列 components |
| `modules[].components` | `zones[].core` + `zones[].members` 的 designator → `instance_id` | 每个元件必须且只能属于一个叶子 |
| `modules[].confidence` | 无既有来源 → 不填（`null`） | 本任务不据此自动分层 |
| `modules[].size_mm` | zone/模块的实测 bbox 长宽（mil→mm） | 缺失 → `size_unknown`，不用模板猜 |
| `components[].instance_id` | 位号或宿主稳定 id；**必须跨重命名稳定** | PoC 可用 `cmp:<designator>`，真实集成需用宿主 primitive/unique id |
| `components[].designator` | 位号 | 只作显示，不要求唯一（重复记 warning） |
| `components[].size_mm` | 实测 bbox（mil→mm） | 缺失 → unknown，不按封装名猜 |
| `components[].fixed` | fixed/locked 标记 | 影响固定冲突报告 |
| `constraints[].from/to` | 模板 `core_role` → `relative[].role`；或 module-plan 的模块顺序/邻接意图 | 端点必须在 modules/components 中 |
| `constraints[].dx_mm/dy_mm` | 模板 `relative[].dx/dy`（mil）+ `frame` 语义 | 模板偏移在 core 帧；`frame: board` 的模板需先换算到 core 帧再表达为 CCG 边 |
| `constraints[].rotation_deg` | 模板 `relative[].rotation`（0/90/180/270） | 必须是两者 `allowed_rotations` 交集的元素 |
| `constraints[].weight` | 模板无权重 → 集成层显式给固定值（如 `1.0`）并记录映射规则 | 权重不参与合成，只作数据/报告；不得暗示已优化 |
| `constraints[].source` | 模板 id / module-plan 路径 / 文档引用 | `kind` 取 `guideline`/`derived`/`project_policy`；`derived` 需源 SHA-256 |
| `provenance.kind/sources/note` | `derived`（来自冻结工程数据）或 `manual`（人工声明） | `derived` 必须给源 SHA-256；不得冒充真实板 |
| `unknowns[]` | 已知缺口（缺 bbox/缺快照 hash/缺固定位姿） | 显式声明，工具绝不填补 |

**不 import `design_engine`**：映射代码应放在集成层，`placement_intent` 包保持
stdlib-only、零内部耦合；若需要模板字段，在任务目录/集成层复制必需字段，不建立
运行期依赖（任务书 §3 要求）。

### 1.3 状态映射（集成门禁语义）

| `plan.status` | exit | 建议门禁语义 |
|---|---|---|
| `planned_with_scope` | 0 | 意图自洽且几何自足；允许进入候选生成。**仍不是已放置**，`routing_verified=false` 不变 |
| `planned_constraints_only` | 1 | 意图自洽但缺尺寸/板框/帧；允许生成约束级候选，但不得声称重叠/包络结论，unknown 进入待办 |
| `review_required` | 1 | 兄弟重叠/固定冲突/模块超出声明尺寸：要求人工 disposition，**不得静默放行**，也不自动改模块计划 |
| `incomplete` | 3 | 无模块/无元件或快照绑定关键字段缺失：不可用于门禁，补数据后重跑 |
| `invalid_input` | 2 | 约束矛盾/树错误/非法数字：拒绝该意图，不得复用旧 PASS 报告 |
| 用法/IO 错误 | 4 | 工具/路径问题，不是结论 |

`validate` 只返回 `valid`(0) / `invalid_input`(2) / 用法·IO(4)，可用于“写候选文件前”
的轻量前置检查。

### 1.4 与 `routing_verified=false` / NOT RUN 的关系

- `placement_intent` 的 plan 输出固定携带 `placement_applied:false`、
  `routing_verified:false`、`physical_validation:"NOT RUN"`、`real_eda:"NOT RUN"`、
  `eda_calls:0`；这些字段必须**原样透传**到任何集成报告，不得被下游改写成 PASS。
- `planned_with_scope` 只等价于“意图自洽 + 几何自足”，**不等于** `hard_ok`、
  不等于可布通、不等于 DRC/制造通过。
- 集成后仍必须：fresh dump → `pcb-check-plan` 硬检查 → 候选/路由试验 → 保存回读。
- `sibling_overlap` 是**意图层**风险提示，不是 DRC 重叠结论；两者口径不同，报告应
  分别标注来源。

## 2. 与 `easycirq_mcp` 工具层的关系（建议新增 2 个离线工具）

`docs/easycirq-mcp/` 已合并且**本任务未修改**。建议由后续集成 PR 在
`easycirq/scripts/easycirq_mcp/` 中新增两个只读工具，复用既有 stdio JSON-RPC
协议与 `easycirq.mcp.offline-audit-tool-result/v1` 结果封装。

### 2.1 工具定义

| 工具 | 调用的 CLI | required | optional |
|---|---|---|---|
| `offline_placement_intent_validate` | `python -m placement_intent validate --input <path> --json` | `input_path` | `detail`、`timeout_s` |
| `offline_placement_intent_plan` | `python -m placement_intent plan --input <path> --anchor top-left --json` | `input_path` | `anchor`（v1 仅支持 `top-left`，其余值模块自身 exit 4）、`detail`、`timeout_s` |

语义：

- `command.module` = `placement_intent`；`command.argv` 记录实际参数；`cwd` =
  `easycirq/scripts`；
- `input_path` 解析规则与既有工具一致（相对仓库根）；输入只读，前后 SHA-256 对比；
- `anchor` 仅接受 v1 支持的 `top-left`（默认）；传其它合法枚举值会得到模块 exit 4，
  工具应把它映射为 `is_error:true` 的用法错误，而不是静默回退到 `top-left`；
- 模块报告 8 MB 以上拒绝（沿用 `report_too_large`）；`timeout_s` 默认 120；
- `detail="summary"` 时保留 `report_sha256`/`report_bytes` 与 `report_omitted:true`；
- 不启动 EDA/daemon/connector，不联网，不写工程。

### 2.2 `verdict_class` 映射（关键：plan 永远不是 pass）

既有 `easycirq_mcp` 的 `verdict_class` 映射针对审查模块（`pass_with_scope` 是唯一
`is_pass_with_scope=true` 的状态）。放置意图是**计划**，不是审查通过，因此**不能**
把 `planned_with_scope` 映射成 `pass_with_scope`。建议新增：

| 模块 status | 工具 | `verdict_class` | `is_pass_with_scope` |
|---|---|---|---|
| `valid` | validate | `valid_input` | false |
| `invalid` | validate | `invalid_input` | false |
| `planned_with_scope` | plan | `planned_with_scope` | **false** |
| `planned_constraints_only` | plan | `planned_constraints_only` | false |
| `review_required` | plan | `review_required` | false |
| `incomplete` | plan | `incomplete` | false |
| `invalid_input` | plan | `invalid_input` | false |
| 其他 | 两者 | `unknown_status` | false |

`is_pass_with_scope` 恒为 false，理由：`placement_applied:false`、
`routing_verified:false`，计划未被应用、布线未验证；若允许“pass”，正是任务书 §13
第 10 条警告的“假通过”。

### 2.3 结果字段映射

| 工具结果字段 | 来源 |
|---|---|
| `status` / `exit_code` | 模块报告 `status` / `exit_code` 原样 |
| `expected_exits` | validate `{0,2,4}`；plan `{0,1,2,3,4}` |
| `real_eda` / `eda_calls` | 报告原值（`"NOT RUN"`/`0`），`real_eda_source:"report"` |
| `placement_applied` / `routing_verified` / `physical_validation` | 报告原值（`false`/`false`/`"NOT RUN"`），固定在结果顶层 |
| `unknown_count` / `unknown_items` / `not_checked` / `limits` | 报告 `unknowns` / `not_checked` / `limits` 复制；unknown 最多 50 条并标 `unknown_items_truncated` |
| `scope_note` | 报告的 `scope_note`（plan）或 `null`（validate） |
| `summary` | plan：`counts`（modules/components/nodes_with_bbox/unknowns）与 `levels` 数；validate：`counts` 与 `checks` |
| `report_schema` | `easycirq.placement-intent.plan/v1` 或 `...validation/v1` |
| `not_proof` | 固定文案：未应用布局、未验证布线/DRC/SI/PI/EM/热/制造/上电 |

`is_error:true` 只用于工具失败（输入不存在、超时、模块异常退出、报告过大/不可解析）；
`invalid_input`/`review_required`/`incomplete` 都是**正常结构化结论**，不是协议错误。

### 2.4 建议的 MCP 调用示例（集成后）

```text
offline_placement_intent_validate {"input_path": "benchmarks/placement-intent/cases/valid-three-modules.json"}
offline_placement_intent_plan     {"input_path": "benchmarks/placement-intent/cases/valid-three-modules.json", "anchor": "top-left"}
offline_placement_intent_plan     {"input_path": "...", "detail": "full"}
```

## 3. 建议的调用点（由集成 PR 决定）

1. **生成候选之前**：模块计划/模板/人工意图映射成 intent 后先 `validate`；
   `invalid_input` 直接拒绝，不进入候选生成。
2. **候选比较之前**：对将要使用的模块计划跑 `plan`；`review_required` 项进入人工
   待办（例如兄弟包络重叠需要确认锚点/尺寸），不自动改计划。
3. **`pcb_apply_plan --module-plan` 之前**：把多份模块计划的相对意图合成一个 intent，
   校验“同一模块组的相对约束不矛盾”；这是现有 `merge_module_plans` 不覆盖的维度。
4. **不要**把它放在保存/回读/DRC 之后替代这些检查；它不是 DRC，也不读铜。

## 4. 建议的文档补丁（diff 片段，未修改真实文件）

`references/pcb-execution.md` 的“局部模板库/多候选”附近可补（措辞按仓库风格调整）：

```diff
+> **放置意图自洽 ≠ 已放置/可布通。** 模板相对偏移与 module-plan 只表达意图。
+> 在生成候选前，可先用 `easycirq/scripts/placement_intent`（离线，0 EDA）
+> 校验 HMT/CCG 是否自洽；其 `planned_with_scope` 只表示意图一致且几何自足，
+> 仍须 fresh dump、`pcb-check-plan` 硬检查与回读，且 `routing_verified=false`。
```

`SKILL.md` 暂不建议改动：本模块尚未接入主流程，接入时由集成 PR 一并更新调用说明与
边界（`NOT RUN` 口径与 `docs/easycirq-mcp/` 一致）。

## 5. 版本与兼容

- 输入/输出 schema 独立于 Skill 版本；本任务首期为 v1，不兼容变更需升版本号。
- `placement_intent` 只依赖 Python 标准库与 Python 3.10 语法；集成层负责字段映射，
  不把宿主协议复制进模块。
- 若上游 `design_engine` 的 module-plan/模板字段变化，优先在集成层转换，并保留
  `derived` 来源的 SHA-256 绑定。
