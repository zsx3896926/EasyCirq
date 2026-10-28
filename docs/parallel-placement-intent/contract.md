# 放置意图（HMT + CCG）离线 PoC：输入/输出契约 v1

本模块只读取一个 JSON 文件，离线校验“分层模块树（HMT）+ 相对约束图（CCG）”是否
自洽，并在输入自足时导出**仅计划**的分层相对布局。它**不写工程、不调用 EDA/daemon/
connector、不联网、不训练/推理任何模型**。

- 输入 schema：`easycirq.placement-intent.input/v1`
- 校验输出 schema：`easycirq.placement-intent.validation/v1`
- 计划输出 schema：`easycirq.placement-intent.plan/v1`
- 解释输出 schema：`easycirq.placement-intent.explain/v1`
- 错误输出 schema（仅用法/IO 错误）：`easycirq.placement-intent.error/v1`
- 工具：`placement_intent 0.1.0`，Python ≥ 3.10，仅标准库
- 入口：`cd easycirq/scripts && PYTHONPATH=. python -m placement_intent ...`

> **命名说明**：本契约沿用任务书的字段结构；仓库 PR #99 统一品牌为「智构 / EasyCirq」后，
> 目录 `design-hardware/` 重构为 `easycirq/`，schema 命名空间 `easycirq.*` 统一为
> `easycirq.*`（与仓库其它模块一致）。任务书原文写作 `easycirq.placement-intent.*`。

本文件是规范。测试与冻结基准只依赖本文件描述的 CLI 行为与 JSON 字段，不导入实现。

## 1. 命令、输出与退出码

```bash
cd easycirq/scripts
PYTHONPATH=. python -m placement_intent validate --input IN.json [--out VALIDATION.json] [--json]
PYTHONPATH=. python -m placement_intent plan     --input IN.json [--out PLAN.json] [--anchor top-left] [--json]
PYTHONPATH=. python -m placement_intent explain  --input IN.json [--constraint ID | --module ID] [--anchor top-left] [--json]
PYTHONPATH=. python -m placement_intent --version
```

- `--input` 必填（`validate`/`plan`/`explain`）；`--out` 仅 `validate`/`plan`。
- `--anchor`：v1 **只支持 `top-left`**（默认，也是唯一支持值）。其余取值
  （`top-right`/`bottom-left`/`bottom-right`/`center`）→ exit 4（用法错误），
  不会静默按 top-left 处理。原因与语义见 §4.2。`validate` 不涉及几何，接受但忽略
  `--anchor`。
- `--json` 可加在所有子命令上；本 PoC 三个子命令的 stdout **始终**是一个 JSON，
  `--json` 是显式声明（兼容客户端），不改变输出。
- stdout 只放一个 JSON 对象（结尾换行）；诊断信息只写 stderr。
- `--out` 使用“同目录临时文件 + `os.replace`”原子写；失败不会留下半截文件。
  `--out` 与 `--input` 解析到同一文件时拒绝（exit 4）。若目标已存在旧结果，
  本次运行的报告会整体覆盖它（包括 `invalid_input`/`incomplete` 报告），不会残留旧 PASS。
  带 `--out` 时 stdout 输出一个**摘要对象**（`schema` 仍为对应输出 schema、`status`、
  `exit_code`、`out`、`counts`、`findings[{code,severity,subject}]`、
  `unknowns[{code,subject,impact}]`），完整报告只写文件；不带 `--out` 时 stdout 即完整报告。
  两种情况下 stdout 都恰是一个 JSON 对象。
- 输入永远只读：`validate`/`plan`/`explain` 均不修改输入文件（测试用前后 SHA-256 对比）。
- 输出确定性：同一输入、同一参数、同一路径两次运行 stdout 字节一致；输出中不含
  运行时间/时间戳，`snapshot.captured_at` 原样来自输入。

| 退出码 | 场景 |
|---|---|
| 0 | `validate`：输入结构/语义合法（允许 warning/unknown）。`plan`：`planned_with_scope`。`explain`：成功解释。 |
| 1 | `plan`：`planned_constraints_only`（信息不足以给出完整 bbox 计划）或 `review_required`（有需人工处置的风险）。 |
| 2 | `invalid_input`：结构/语义非法（重复 JSON 键、NaN/Inf/伪数字、树错误、矛盾约束、非恒等环等），或 `explain` 的目标 ID 不存在。 |
| 3 | `incomplete`：信息不足以规划（无模块/无元件、快照绑定关键字段缺失）。 |
| 4 | 用法/IO 错误：文件不存在、参数错误、`--out` 等于输入、输出不可写。 |

`validate` 只输出 exit 0 或 2（输入文件层面的 4 除外）；`planned_*`/`review_required`/
`incomplete` 只由 `plan` 产生。任何 `unknown`/`review_required`/`incomplete` **不会**
被 `plan` 提升为 `planned_with_scope`。

## 2. 输入结构 `easycirq.placement-intent.input/v1`

顶层对象，`additionalProperties:false`。严格解析：UTF-8（允许 BOM），拒绝重复键、
`NaN`/`Infinity`、非对象根、结尾多余内容。

| 字段 | 必填 | 类型/约束 | 说明 |
|---|---|---|---|
| `schema` | 是 | 常量 `easycirq.placement-intent.input/v1` | |
| `project` | 是 | 对象，见 §2.1 | 身份稳定；位号可变 |
| `snapshot` | 是 | 对象，见 §2.2 | 上游快照绑定 |
| `units` | 是 | 对象，见 §2.3 | 长度单位 |
| `board` | 否 | 对象，见 §2.4 | 缺失 = unknown |
| `modules` | 是 | 数组，见 §2.5 | HMT 节点 |
| `components` | 是 | 数组，见 §2.6 | 元件 |
| `constraints` | 是 | 数组，见 §2.7 | CCG 边，可为空 |
| `policy` | 否 | 对象，见 §2.8 | |
| `provenance` | 是 | 对象，见 §2.9 | 来源 |
| `unknowns` | 否 | 数组，见 §2.10 | 显式未知项 |

全局规则：

- 所有 `id`（`instance_id`、模块 `id`、约束 `id`、显式未知项 `id`）合法值 = 非空字符串。
  模块 id 与元件 `instance_id` 共用**同一命名空间**（CCG/固定位置按 id 引用任何节点），
  跨类型重复 = `node_id_duplicate` 非法。
- 数字字段只接受 JSON number（int/float），**拒绝** bool、数字字符串、`NaN`/`Infinity`。
  长度/权重必须有限；见各字段的取值约束。
- 未知额外字段一律 `unknown_property` 非法（顶层与所有子对象 `additionalProperties:false`）。
- 字符串枚举严格小写、逐字符匹配；空字符串一律非法。

### 2.1 `project`

| 字段 | 必填 | 约束 |
|---|---|---|
| `project_id` | 是 | 非空字符串 |
| `revision` | 是 | 非空字符串 |
| `document_id` | 否 | 非空字符串 |

### 2.2 `snapshot`

| 字段 | 必填 | 约束 |
|---|---|---|
| `schema` | 否 | 非空字符串（上游快照 schema，仅记录） |
| `captured_at` | 是 | 非空字符串（ISO 8601 风格时间；不重新解释/不取当前时间） |
| `content_sha256` | 是 | 64 位小写十六进制字符串，或 `null` |
| `source_type` | 是 | `host_export` / `manual_declaration` / `synthetic_fixture` / `derived` |
| `missing_fields` | 是 | 字符串数组，元素非空、无重复；数组可为空 |

- `content_sha256` 为 `null` 时，`"content_sha256"` **必须**出现在 `missing_fields` 中，
  否则 `snapshot_missing_not_declared` 非法。
- `content_sha256` 为 `null`（已声明缺失）→ unknown `snapshot_content_hash_missing`
  （`impact=incomplete`）→ `plan` 为 `incomplete`。工具不计算、不伪造该哈希。
- `content_sha256` 是**声明值**：工具不重新读取宿主快照，只在报告里记录。

### 2.3 `units`

| 字段 | 必填 | 约束 |
|---|---|---|
| `length` | 是 | `"mm"` 或 `"mil"` |

- 这是输入中**所有**“长度字段”的单位。字段名带 `_mm` 后缀只是“长度字段”的标记：
  `units.length="mil"` 时，`dx_mm`/`size_mm.w`/`width_mm` 等都按 mil 读入，
  内部统一换算成 mm（`1 mil = 0.0254 mm`）。
- 报告写 `units.input_length` 与换算后的 `units.normalized_length="mm"`、
  `units.scale_to_mm`。未声明 `units` 或 `units.length` 不在白名单 → 非法（不按 mm 猜）。

### 2.4 `board`（可选）

| 字段 | 必填 | 约束 |
|---|---|---|
| `width_mm` | 否 | 长度 > 0 |
| `height_mm` | 否 | 长度 > 0 |
| `outline_polygon_mm` | 否 | 至少 3 个 `[x, y]` 点；每个都是长度；不要求凸或闭合 |
| `fixed_positions_mm` | 否 | 数组，见下 |

`fixed_positions_mm` 元素：`{"id": <模块 id 或元件 instance_id>, "x_mm": 长度, "y_mm": 长度,
"rotation_deg": 0|90|180|270}`；`rotation_deg` 可选（缺省视为未知旋转）。同一 `id` 重复
出现且值不一致 = `fixed_position_duplicate` 非法；值一致 = 去重（info）。

- “板框已知” = (`width_mm` 与 `height_mm` 同时存在) 或 (`outline_polygon_mm` 存在且点数 ≥3)。
  否则 unknown `board_unknown`（`impact=constraints_only`）。
- 板框只影响 `plan` 状态标注；本模块**不**输出绝对板坐标，也不把节点投影到板框上。

### 2.5 HMT 节点（`modules[]`）

| 字段 | 必填 | 约束 |
|---|---|---|
| `id` | 是 | 非空字符串，全局唯一 |
| `name` | 否 | 非空字符串 |
| `parent` | 是 | 字符串或 `null`（根） |
| `children` | 是 | 模块 id 字符串数组；元素唯一 |
| `components` | 是 | 元件 `instance_id` 字符串数组；元素唯一 |
| `confidence` | 否 | number，`0 <= c <= 1`（不据此自动分层） |
| `size_mm` | 否 | `{"w": 长度>0, "h": 长度>0}`，`additionalProperties:false` |
| `allowed_rotations` | 否 | 子集 `{0,90,180,270}`，非空、无重复 |
| `fixed` | 否 | bool，缺省 `false` |
| `source` | 否 | `{"kind": "user"|"guideline"|"derived", "ref": 可选非空字符串}`，额外字段非法 |

树规则（全部硬错误）：

1. 恰好一个 `parent=null` 的根；多于一个 → `tree_multiple_roots`；没有 → `tree_no_root`。
2. `id` 唯一；`parent` 必须指向存在的模块（`tree_parent_unknown`）。
3. 父子双向一致：节点 `parent=P` ⇔ `P.children` 含该节点 id；不一致 →
   `tree_parent_mismatch`。`children` 中出现不存在/非模块 id → `tree_child_unknown`。
4. 无环（从根 DFS 可达全部节点；否则 `tree_cycle` / `tree_unreachable`）。
5. 深度（根 = 0）不得超过 `policy.max_depth`（默认 6）；超限 → `tree_depth_exceeded`。
6. 叶子（`children == []`）才可列 `components`；非叶子 `components` 非空 →
   `non_leaf_components`。叶子 `components == []` 允许，但记 warning `empty_leaf`。
7. 每个元件必须且只能出现在一个叶子中：未归属 → `component_unassigned`；
   多处归属 → `component_duplicate_membership`；引用不存在的元件 → `unknown_component_reference`。
8. `allowed_rotations` 缺省取 `policy.default_allowed_rotations`（默认 `[0,90,180,270]`）。

### 2.6 元件（`components[]`）

| 字段 | 必填 | 约束 |
|---|---|---|
| `instance_id` | 是 | 非空字符串，全局唯一且稳定（位号变了也不变） |
| `designator` | 是 | 非空字符串（只作显示；不要求全局唯一，但重复记 warning `designator_duplicate`） |
| `kind` | 否 | 非空字符串（如 `ldo`/`capacitor`；自由文本，不据此推断尺寸） |
| `mpn` | 否 | 非空字符串或 `null` |
| `package` | 否 | 非空字符串或 `null` |
| `size_mm` | 否 | `{"w": >0, "h": >0}`；缺失 = 几何 unknown，不得用封装名猜 |
| `fixed` | 否 | bool，缺省 `false` |
| `allowed_rotations` | 否 | 同模块；缺省取 policy 默认 |
| `source` | 否 | `{"kind": "user"|"guideline"|"derived", "ref": 可选}` |
| `position_mm` | 否 | `{"x_mm": 长度, "y_mm": 长度, "rotation_deg"?: 0|90|180|270}`；只用于 `fixed` 冲突报告 |

`position_mm` 出现在 `fixed=false` 元件上不非法，但会记 warning `position_ignored_non_fixed`
且不参与任何几何计算。`position_mm` 与 `board.fixed_positions_mm` 同时给出同一元件且
不一致 → `fixed_position_duplicate` 非法（一致则去重）。

### 2.7 CCG 边（`constraints[]`）

| 字段 | 必填 | 约束 |
|---|---|---|
| `id` | 是 | 非空字符串，全局唯一 |
| `from` | 是 | 模块 id 或元件 `instance_id` |
| `to` | 是 | 同上 |
| `dx_mm` | 是 | 有限数字（见 §4.3） |
| `dy_mm` | 是 | 有限数字 |
| `rotation_deg` | 是 | 必须是 `0`/`90`/`180`/`270` 之一（见 §4.4） |
| `weight` | 是 | 有限数字且 `> 0` |
| `source` | 否 | `{"kind": "user"|"guideline"|"derived"|"datasheet"|"project_policy"|"synthetic", "ref": 可选非空字符串}` |
| `note` | 否 | 非空字符串 |

`constraints` 可以为空数组，表示“只有模块树、没有相对约束”。

### 2.8 `policy`（可选）

| 字段 | 必填 | 约束 | 默认 |
|---|---|---|---|
| `max_depth` | 否 | 整数 `1..12` | 6 |
| `default_allowed_rotations` | 否 | `{0,90,180,270}` 的非空真子集/全集，无重复 | `[0,90,180,270]` |
| `position_tolerance_mm` | 否 | 有限数字 `>= 0` | `1e-6` |
| `weight_epsilon` | 否 | 有限数字 `> 0` | `1e-9` |

旋转比较的固定容差为 `1e-6` 度（不可配置）；平移比较使用 `position_tolerance_mm`（均为
换算后的 mm）。`weight` 比较使用 `weight_epsilon`。

### 2.9 `provenance`（必填）

| 字段 | 必填 | 约束 |
|---|---|---|
| `kind` | 是 | `synthetic` / `derived` / `manual` |
| `sources` | 是 | 数组，元素 `{"ref": 非空字符串, "sha256": 64 位小写十六进制, "note"?: 非空字符串}` |
| `note` | 是 | 非空字符串（说明这是什么数据、不是什么） |

- `kind="derived"`：`sources` 必须非空，且每个 source 都有 `sha256`；否则
  `provenance_source_missing` 非法。
- `kind="synthetic"`/`"manual"`：`sources` 可为空；但 `derived` 语义不得用于冒充真实工程。
- 真实工程派生数据的 `sha256` 指被派生源文件的 SHA-256（写入 `sources[].sha256`），
  报告另记本次输入文件的 SHA-256；两者含义不同，不可混用。

### 2.10 `unknowns[]`（可选）

元素 `{"id": 非空且唯一, "field": 非空字符串, "reason": 非空字符串}`，额外字段非法。
这些是调用方**主动声明**的未知项；工具会原样搬进输出（`origin="input"`,
`impact="constraints_only"`），绝不因为“其它数据齐全”而吞掉。

## 3. 严格解析与非法输入

- 重复 JSON 键 → `json_duplicate_key`；语法错误/非对象根/尾随内容 → `json_invalid`。
- `NaN`/`Infinity`/`-Infinity` 字面量 → `json_invalid`。
- bool 伪装数字（`true` 当 1）、数字字符串（`"1.5"`）、`null` 当 0 → `number_invalid`。
- 字段缺失 → `missing_required`；类型错 → `type_mismatch`；枚举外 → `enum_invalid`；
  空字符串 → `empty_string`；额外字段 → `unknown_property`。
- 越界（`weight <= 0`、`size <= 0`、`confidence` 越界、`max_depth` 越界、
  `position_tolerance_mm < 0`）→ `number_out_of_range`。
- 一个输入可以同时有多条 finding；`findings` 全部输出，`status=invalid_input`，
  exit 2。错误不会被“第一条”截断。
- 重复 id 的 finding code：同一集合/同一命名空间内重复（模块 id 重复、元件
  `instance_id` 重复、约束 `id` 重复、显式 unknown `id` 重复、数组元素重复）→
  `duplicate_id`；模块 id 与元件 `instance_id` 互撞（跨类型共用命名空间）→
  `node_id_duplicate`。两者都是硬错误。
- 合法规避：`components[].position_mm` 与 `board.fixed_positions_mm` 对同一节点给出
  完全相同的值 → 记 info `fixed_position_duplicate` 并去重；不同值 → 硬错误。

## 4. CCG 几何语义（必须精确实现）

### 4.1 坐标系与锚点

- 每个节点（模块或元件）有一个**放置帧**：帧原点 = 该节点的“锚点”，旋转 = 该节点的
  绝对旋转（相对根）。
- v1 **固定 `anchor = "top-left"`**：`dx_mm/dy_mm` 指向 `to` 的锚点，即元件声明尺寸框
  的左上角、模块放置帧的原点（由父级约束链确定）。`--anchor` 的其它取值直接拒绝
  （exit 4），不会静默改语义。
- `dx_mm/dy_mm` 是**轴对齐偏移向量**；该向量表达在合成到该边时 `from` 所在的坐标系中
  （对同一父模块下的兄弟节点，就是父模块坐标系；跨模块边按路径累积旋转合成）。若
  `from` 已旋转，则偏移随其旋转。
- 模块的帧原点由约束链决定，**不等于**其推导包络的左上角：包络可以落在原点的负方向
  （`bbox_mm` 的 x/y 可为负）。工具**不做**“把 bbox 平移到 (0,0)”的归一化，因此同一
  计划中不同节点的 bbox 都在各自帧里表达，可直接用于相对布局复核。

### 4.2 旋转

- `rotation_deg` 是 `to` 相对 `from` 的相对旋转，逆时针为正，统一 `mod 360`。
- 取值必须落在二者 `allowed_rotations` 的**交集**内（模块取自身声明或 policy 默认；
  元件同理）；否则 `constraint_rotation_not_allowed` 非法。
- 路径累积旋转：`r_to = (r_from + rotation_deg) mod 360`。
- 任何节点的最终累积旋转必须在其 `allowed_rotations` 内，否则
  `constraint_rotation_not_allowed` 非法（错误主体是该节点）。
- 比较用 `1e-6` 度容差；内部把 `-0.0` 规范成 `0.0`。

### 4.3 数值

- `dx_mm`/`dy_mm`/`weight` 必须是有限 number；`dx/dy` 无范围限制（可为负）；
  `weight > 0`。`from == to` → `constraint_self_loop`。端点不存在 →
  `constraint_endpoint_unknown`。

### 4.4 路径合成（规范公式）

以根为起点，沿一条边 `from -> to` 有：

```text
p_to = p_from + R(r_from) · (dx, dy)
r_to = (r_from + rotation_deg) mod 360
R(a) = [[cos a, -sin a], [sin a, cos a]]
```

`p_root = (0, 0)`、`r_root = 0`。反向沿同一条边（`to -> from`）为：

```text
r_from = (r_to - rotation_deg) mod 360
p_from = p_to - R(r_from) · (dx, dy)
```

- 对每个 CCG 连通分量，选该分量中 **id 字典序最小** 的节点为过程锚点，用 BFS/生成树
  给分量内所有节点赋相对位姿；含根的分量即得到根相对位姿（根固定 `(0,0,0)`）。
- 多路径一致性：任意两节点若存在多条路径，合成位姿必须在 `position_tolerance_mm`
  与 `1e-6` 度内一致，否则 `constraint_path_mismatch` 非法。
- 环：沿环一周的合成必须是恒等（平移长度 `<= position_tolerance_mm` 且旋转
  `mod 360` 在 `1e-6` 度内为 0）→ 记 info `constraint_cycle_identity`；否则
  `constraint_cycle_nonidentity` 非法。
- 重复边：同一 `(from, to)` 且 `dx/dy`（按容差）、`rotation_deg`、`weight`（按
  `weight_epsilon`）都相同 → 去重，保留输入顺序第一条，其余 id 进 `aliases`，
  记 info `constraint_duplicate_deduped`；任一字段不同 → `constraint_duplicate_conflict`
  非法（不做最小二乘、不择一）。
- 无路径：与根不在同一 CCG 连通分量的节点，其位置/旋转**保持 unknown**
  （`no_constraint`），不推断、不猜原点。

### 4.5 固定节点与冲突（`review_required`，不是 invalid）

- `fixed:true` 的节点表示不可移动；只用于冲突报告，不参与求解。
- 声明位置来源：`board.fixed_positions_mm` 与 `components[].position_mm`（模块只能用前者）。
- 冲突判定（全部基于**相对**信息，不使用绝对板坐标）：
  1. **旋转冲突**：固定节点已声明 `rotation_deg`，且其 CCG 合成旋转（相对根）与声明值
     在 `1e-6` 度内不一致 → finding `fixed_conflict`（severity `review`）。
  2. **相对距离冲突**：两个固定节点 A、B 都声明了位置，且 A、B 在同一 CCG 连通分量内
     能算出相对位移；若 `|declared_B - declared_A|` 与合成距离之差超过
     `position_tolerance_mm` → `fixed_conflict`。
  3. 固定节点有声明位置但没有任何约束边：不产生冲突（无可证明的移动要求）。
  4. 固定节点出现在约束中但未声明位置：不能证明冲突 → warning `fixed_position_unknown`
     （不改变状态）。
- `fixed_conflict` 令 `plan` 状态为 `review_required`，`validate` 仍 exit 0（输入合法）。

## 5. unknown 传播

unknown 条目统一形状（输出字段固定）：

```json
{
  "id": "unk:size_unknown:cmp:U1",
  "code": "size_unknown",
  "subject": "cmp:U1",
  "field": "size_mm",
  "reason": "component size_mm is missing; bbox not inferred",
  "impact": "constraints_only",
  "origin": "derived"
}
```

`impact` 取值 `none`（只记录）、`constraints_only`（最多 `planned_constraints_only`）、
`incomplete`（`incomplete`）。`origin` 取值 `input`/`derived`。id 稳定可复现：
`unk:<code>:<subject or "global">`（同一 id 冲突时追加 `:2`、`:3`…）。输入 `unknowns[]`
搬运后的条目为 `unk:declared:<declared_id>`、`subject=<declared_id>`、`field`/`reason`
原样保留，并额外回显 `declared_id`。

派生 unknown：

| code | 触发 | impact |
|---|---|---|
| `design_empty` | `modules` 为空或 `components` 为空 | incomplete |
| `snapshot_content_hash_missing` | `snapshot.content_sha256=null` 且已在 `missing_fields` 声明 | incomplete |
| `board_unknown` | 板框不足（见 §2.4） | constraints_only |
| `no_constraint` | 节点与根不在同一 CCG 连通分量，位置/旋转不推断（`subject`=节点 id） | constraints_only |
| `frame_unknown` | 节点与根连通、但其树父不在根分量，父相对帧不可知（`subject`=节点 id） | constraints_only |
| `constraints_empty` | `constraints` 为空数组 | constraints_only |
| `size_unknown` | 已知帧下 bbox 无法推导（`subject`=该节点 id） | constraints_only |
| `overlap_not_checked` | 某父模块的兄弟重叠因缺 bbox/帧未检查（`subject`=null） | none |
| `declared_unknown` | 输入 `unknowns[]` 原样搬运（`origin=input`） | constraints_only |

- 每个受影响的节点各自产生条目：缺一个元件尺寸不会让同层其它已知尺寸模块失去 bbox，
  但会让它的所有祖先模块 bbox 为 `null` 并各自 `size_unknown`。
- unknown 不参与“补齐”，不会因为其它模块齐全而被丢弃；也不会被降级成 warning。

## 6. `validate` 输出 `easycirq.placement-intent.validation/v1`

```json
{
  "schema": "easycirq.placement-intent.validation/v1",
  "tool": {"name": "placement_intent", "version": "0.1.0", "min_python": "3.10",
           "deterministic": true},
  "status": "valid",
  "valid": true,
  "exit_code": 0,
  "project": {"project_id": "demo-3mod", "revision": "r1", "document_id": null},
  "units": {"input_length": "mm", "normalized_length": "mm", "scale_to_mm": 1.0},
  "input": {"path": ".../valid-three-modules.json", "sha256": "<64hex>",
            "bytes": 1234, "schema": "easycirq.placement-intent.input/v1"},
  "counts": {"modules": 5, "components": 8, "constraints_input": 8,
             "constraints_normalized": 8, "tree_depth": 2, "errors": 0,
             "reviews": 0, "warnings": 0, "info": 0, "unknowns": 0},
  "checks": {"json": "passed", "structure": "passed", "identity": "passed",
             "tree": "passed", "constraints": "passed",
             "fixed_positions": "not_checked"},
  "findings": [],
  "unknowns": [],
  "not_checked": ["board placement / absolute board coordinates",
                  "host DRC and electrical rules",
                  "routing and copper connectivity", "SI/PI/EM/thermal",
                  "manufacturing, assembly and physical test"],
  "limits": ["relative plan only; nothing is applied",
             "unknowns are reported, never filled with defaults"],
  "real_eda": "NOT RUN",
  "eda_calls": 0
}
```

- `status` 只有 `valid` / `invalid`；`checks` 值 `passed` / `failed` / `not_checked`。
- 非法输入时 `valid=false`、`exit_code=2`、`checks` 中对应项 `failed`，`project`/`units`
  在可解析时仍尽量回填，不可解析时为 `null`（`input.path` 与 `sha256` 始终记录）。
- `findings[]` 形状：`{"code","severity","status","subject","path","explanation","suggestion","details"}`：
  - `severity` ∈ `error` / `review` / `warning` / `info`；
  - `status`：`error`→`invalid_input`，`review`→`review_required`，其余→`ok`；
  - `subject`：节点/边 id 或 `null`；`path`：`modules[0].size_mm.w` 形式的输入内位置或 `null`；
    `details`：对象（可为 `{}`）。数组按 `(severity, code, subject, path)` 稳定排序。

## 7. `plan` 输出 `easycirq.placement-intent.plan/v1` 与状态

### 7.1 状态判定（优先级从高到低）

```text
invalid_input          exit 2   任一 severity=error 的 finding
incomplete             exit 3   modules/components 为空，或任一 impact=incomplete 的 unknown
review_required        exit 1   任一 severity=review 的 finding（fixed_conflict / sibling_overlap /
                                module_size_exceeded 等）
planned_constraints_only exit 1 任一 impact=constraints_only 的 unknown（缺尺寸/缺帧/缺板框/无约束）
planned_with_scope     exit 0   以上都没有
```

- `planned_with_scope`：输入合法、约束一致、所有节点帧已知、所有 bbox 可推导、板框已知。
  仍明确是**计划**（`placement_applied:false`）。
- `planned_constraints_only`：约束一致但信息不足；`levels` 与 `normalized_constraints` 仍输出，
  `bbox_mm` 不可推导处一律 `null`（**绝不填默认尺寸/默认位置**）。
- `review_required`：有可解释风险（固定冲突、兄弟重叠、模块包络超出声明尺寸、来源不足）。
- `incomplete`：连相对约束/层级都无从谈起。
- 任何状态下 `placement_applied:false`、`routing_verified:false`、`physical_validation:"NOT RUN"`、
  `real_eda:"NOT RUN"`、`eda_calls:0` 都保留。

### 7.2 输出结构

```json
{
  "schema": "easycirq.placement-intent.plan/v1",
  "tool": {"name": "placement_intent", "version": "0.1.0", "min_python": "3.10"},
  "status": "planned_with_scope",
  "exit_code": 0,
  "project": {"project_id": "demo-3mod", "revision": "r1", "document_id": null},
  "units": {"input_length": "mm", "normalized_length": "mm", "scale_to_mm": 1.0},
  "anchor": "top-left",
  "rotation_convention": "counter_clockwise",
  "bbox_approx": "axis_aligned_rotated_rects",
  "levels": [
    {"depth": 0, "nodes": [<node>]},
    {"depth": 1, "nodes": [<node>]},
    {"depth": 2, "nodes": [<node>]}
  ],
  "normalized_constraints": [
    {"id": "ccg:1", "from": "mod:board", "to": "mod:power",
     "from_kind": "module", "to_kind": "module",
     "dx_mm": 5.0, "dy_mm": 5.0, "rotation_deg": 0, "weight": 0.9,
     "source": {"kind": "guideline", "ref": "doc:power-layout#L12"},
     "note": null, "aliases": []}
  ],
  "findings": [],
  "unknowns": [],
  "counts": {"modules": 5, "components": 8, "constraints_input": 8,
             "constraints_normalized": 8, "nodes_with_bbox": 13,
             "nodes_without_bbox": 0, "errors": 0, "reviews": 0,
             "warnings": 0, "info": 0, "unknowns": 0},
  "not_checked": ["absolute board coordinates were not computed",
                  "placement was not applied to any project",
                  "routing/connectivity not verified",
                  "host DRC not run", "SI/PI/EM/thermal not evaluated",
                  "manufacturing/assembly/physical test not performed"],
  "limits": ["axis-aligned bounding boxes of rotated rectangles",
             "relative frames only; the plan is not a final placement",
             "constraints are reported, never optimized or resolved"],
  "scope_note": "Module-relative placement intent plan. Not board coordinates; nothing was applied.",
  "provenance": {"kind": "synthetic", "sources": [], "note": "...",
                 "input": {"path": "...", "sha256": "<64hex>", "bytes": 1234},
                 "snapshot": {"captured_at": "...", "source_type": "synthetic_fixture",
                              "content_sha256": "<64hex>", "missing_fields": []},
                 "units": {"input_length": "mm", "normalized_length": "mm",
                           "scale_to_mm": 1.0},
                 "tool": {"name": "placement_intent", "version": "0.1.0"}},
  "placement_applied": false,
  "routing_verified": false,
  "physical_validation": "NOT RUN",
  "real_eda": "NOT RUN",
  "eda_calls": 0
}
```

`<node>` 字段（模块与元件统一；不适用处为 `null`/`[]`）：

```json
{
  "id": "mod:power",
  "kind": "module",
  "label": "Power input and regulation",
  "parent": "mod:board",
  "frame": {"offset_mm": [5.0, 5.0], "rotation_deg": 0.0, "known": true},
  "bbox_mm": {"x": 0.0, "y": 0.0, "w": 18.0, "h": 12.0},
  "size_mm": {"w": 18.0, "h": 12.0},
  "allowed_rotations": [0, 90, 180, 270],
  "fixed": false,
  "confidence": 0.92,
  "children": ["mod:usb", "mod:ldo"],
  "components": [],
  "unknowns": []
}
```

- `kind` ∈ `module` / `component`；元件 `label` 取 `designator`，`children`/`components`
  为 `[]`，`confidence` 为 `null`。
- `frame`：相对**父节点**的偏移与旋转（根为 `offset_mm:[0,0]`、`rotation_deg:0`、
  `known:true`）；未知时 `offset_mm:null`、`rotation_deg:null`、`known:false`。
- `bbox_mm`：该节点在**自身未旋转局部帧**中的轴对齐包络（**不做锚点归一**，x/y 可为负，
  根节点也不会被平移到 (0,0)）；不是板坐标；未知为 `null`。元件 bbox 固定为
  `{"x":0,"y":0,"w":w,"h":h}`。子项 AABB 的推导见下方第 2 条。
- `size_mm`：输入声明的尺寸（模块/元件）；未声明为 `null`。它不替代 bbox 推导。
- 层级：`depth(根)=0`；模块子节点 +1；元件的 depth = 所属叶子模块 depth + 1。
  `levels` 按 depth 升序，每层 `nodes` 按 id 字典序；`normalized_constraints` 按
  `(from, to, id)` 排序；`findings`/`unknowns` 稳定排序。
- bbox 推导（自底向上）：
  1. 元件：`size_mm` 已知 → `(0,0,w,h)`；否则 `null` + `size_unknown`。
  2. 模块的“子项” = 树子模块 + 自身 `components`。对每个子项：若与模块同属一个 CCG
     连通分量，则相对位姿已知，子项矩形按锚点旋转（绕其原点）后取 AABB 并入；
     若不同分量或子项 bbox 为 `null` → 本模块 `bbox=null` + `size_unknown`。
  3. 无子项且声明了 `size_mm` 的叶子：bbox = `(0,0,w,h)`；两者都没有 → `null`。
  4. 模块声明了 `size_mm` 且推导 bbox 超出 `[0,w]×[0,h]`（超出量 > `position_tolerance_mm`）
     → finding `module_size_exceeded`（review）。
- 兄弟重叠：对每个模块，若其全部直接子项 bbox 与相对帧都可算，则把子项 AABB 变换到
  该模块帧两两求交；交叠面积大于 `position_tolerance_mm²` → `sibling_overlap`
  （review），`details` 给 `{"a": <id>, "b": <id>, "dx_mm": ..., "dy_mm": ...}`。
  不可算时不做该父模块的检查，并在 `not_checked` 追加说明。**重叠只降级为
  `review_required`，不是 invalid，也不是通过**。
- `planned_constraints_only` 下若部分 bbox 可推导，仍输出该 bbox；状态只表示整体信息
  不足以给出完整计划。

## 8. `explain` 输出 `easycirq.placement-intent.explain/v1`

只读重放：内部执行 `validate` + 相对帧合成，不写文件。`--constraint ID` 或 `--module ID`
二选一（同时给出 → exit 4）。都不给时输出总览。

```json
{
  "schema": "easycirq.placement-intent.explain/v1",
  "tool": {"name": "placement_intent", "version": "0.1.0"},
  "input": {"path": "...", "sha256": "<64hex>", "bytes": 1234},
  "subject": {"type": "constraint", "id": "ccg:2"},
  "status": "explained",
  "constraint": {
    "id": "ccg:2", "from": "mod:power", "to": "mod:ldo",
    "dx_mm": 20.0, "dy_mm": 0.0, "rotation_deg": 0, "weight": 0.8,
    "source": {"kind": "guideline", "ref": "doc:power-layout#L12"},
    "aliases": []
  },
  "synthesis": {
    "anchor_node": "mod:root",
    "path": ["mod:root", "mod:power", "mod:ldo"],
    "steps": [
      {"edge": "ccg:1", "from": "mod:root", "to": "mod:power",
       "dx_mm": 5.0, "dy_mm": 5.0, "rotation_deg": 0,
       "origin_before_mm": [0.0, 0.0], "rotation_before_deg": 0.0,
       "origin_after_mm": [5.0, 5.0], "rotation_after_deg": 0.0}
    ],
    "target_origin_mm": [25.0, 5.0],
    "target_rotation_deg": 0.0,
    "alternate_paths": [
      {"path": ["mod:root", "mod:ldo"],
       "origin_mm": [25.0, 5.0], "rotation_deg": 0.0, "consistent": true}
    ],
    "consistent": true
  },
  "conflicts": [],
  "unknowns": [],
  "not_checked": ["..."],
  "notes": ["Path length is a constraint-graph path; it is not a physical routing path."]
}
```

- `status`：`explained` / `invalid_input`（exit 2）/ `unknown_subject`（exit 2）。
- `--module ID`：`subject.type="module"`，输出该模块的树信息、`frame`、`bbox_mm`、
  `components`、`related_constraints`（作为 from 或 to 的边 id）、`unknowns`。
- 总览：`subject.type="overview"`，给层级、状态、finding/unknown 计数、约束条数。
- `explain` 不因 `plan` 会是 `review_required`/`planned_constraints_only` 而失败：
  只要输入合法就 exit 0；输入非法 exit 2。

## 9. 单位、只读、原子写、复现

- 单位换算只在读入时做一次；报告只出现 mm（`*_mm` 字段）并另记原始单位。
  等价 mil/mm 输入（如 `1000 mil` 与 `25.4 mm`）规范化结果在 `position_tolerance_mm`
  内一致；JSON 浮点书写差异不构成语义差异。
- `--out` 原子写；`--out == --input` 拒绝（按解析后的绝对路径比较，Windows 大小写不敏感）。
- 输入只读；`validate`/`plan`/`explain` 都不在输入旁写任何文件（`--out` 除外）。
- 输出无时间戳、无随机、无环境相关字段（除输入 `path` 原样回显）。
- 数组顺序不影响语义：`modules`/`components`/`constraints`/`unknowns` 任意重排，
  `plan`/`validate` 的实质结果（状态、bbox、帧、finding 集合）不变；输出本身已排序。

## 10. 边界（NOT RUN）

本模块证明的只是“给定的 HMT/CCG 表示自洽且可离线重放”。它不证明、也不声称：

- 任何真实 EDA 工程被读取、修改、保存或重开（`real_eda:"NOT RUN"`，`eda_calls:0`）；
- 布局已应用（`placement_applied:false`）、布线可通（`routing_verified:false`）、
  DRC/连通性/SI/PI/EM/热通过；
- HPWL/密度/无重叠等代理指标等价于“可布通”或“电磁性能好”；
- 制造、装配、上电与实物功能。

论文 *ModuPlace*（DOI `10.1145/3770743.3803892`）只借鉴 HMT/CCG 的**表示**思路；
本 PoC 不含其数据、权重、训练（SFT/GRPO）或仿真评估。

## 11. 完整示例

### 11.1 合法输入（`benchmarks/placement-intent/cases/valid-three-modules.json` 的等价内容）

```json
{
  "schema": "easycirq.placement-intent.input/v1",
  "project": {"project_id": "demo-3mod", "revision": "r1", "document_id": "sheet-1"},
  "snapshot": {"captured_at": "2026-10-27T09:00:00+08:00",
               "content_sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
               "source_type": "synthetic_fixture", "missing_fields": []},
  "units": {"length": "mm"},
  "board": {"width_mm": 40.0, "height_mm": 30.0},
  "modules": [
    {"id": "mod:board", "name": "Demo board", "parent": null,
     "children": ["mod:power", "mod:sense"], "components": [],
     "size_mm": {"w": 40.0, "h": 30.0}, "allowed_rotations": [0],
     "source": {"kind": "user"}},
    {"id": "mod:power", "name": "Power", "parent": "mod:board",
     "children": ["mod:ldo"], "components": [], "confidence": 0.92,
     "size_mm": {"w": 14.0, "h": 8.0}, "allowed_rotations": [0],
     "source": {"kind": "user"}},
    {"id": "mod:ldo", "name": "LDO block", "parent": "mod:power",
     "children": [], "components": ["cmp:U1", "cmp:C1", "cmp:C2"],
     "size_mm": {"w": 8.0, "h": 6.0}, "allowed_rotations": [0],
     "source": {"kind": "user"}},
    {"id": "mod:sense", "name": "Sensor", "parent": "mod:board",
     "children": [], "components": ["cmp:U2", "cmp:R1"],
     "size_mm": {"w": 10.0, "h": 6.0}, "allowed_rotations": [0],
     "source": {"kind": "user"}}
  ],
  "components": [
    {"instance_id": "cmp:U1", "designator": "U1", "kind": "ldo", "mpn": "TLV75533PDBV",
     "package": "SOT-23-5", "size_mm": {"w": 3.0, "h": 3.0}, "fixed": false,
     "allowed_rotations": [0], "source": {"kind": "user"}},
    {"instance_id": "cmp:C1", "designator": "C1", "kind": "capacitor",
     "size_mm": {"w": 1.0, "h": 2.0}, "allowed_rotations": [0]},
    {"instance_id": "cmp:C2", "designator": "C2", "kind": "capacitor",
     "size_mm": {"w": 1.0, "h": 2.0}, "allowed_rotations": [0]},
    {"instance_id": "cmp:U2", "designator": "U2", "kind": "sensor",
     "size_mm": {"w": 4.0, "h": 4.0}, "allowed_rotations": [0]},
    {"instance_id": "cmp:R1", "designator": "R1", "kind": "resistor",
     "size_mm": {"w": 1.0, "h": 2.0}, "allowed_rotations": [0]}
  ],
  "constraints": [
    {"id": "ccg:1", "from": "mod:board", "to": "mod:power",
     "dx_mm": 5.0, "dy_mm": 5.0, "rotation_deg": 0, "weight": 0.9,
     "source": {"kind": "guideline", "ref": "doc:power-layout#L12"}},
    {"id": "ccg:2", "from": "mod:board", "to": "mod:sense",
     "dx_mm": 25.0, "dy_mm": 5.0, "rotation_deg": 0, "weight": 0.7},
    {"id": "ccg:3", "from": "mod:power", "to": "mod:ldo",
     "dx_mm": 3.0, "dy_mm": 2.0, "rotation_deg": 0, "weight": 0.8},
    {"id": "ccg:4", "from": "mod:ldo", "to": "cmp:U1",
     "dx_mm": 1.0, "dy_mm": 1.0, "rotation_deg": 0, "weight": 0.9},
    {"id": "ccg:5", "from": "mod:ldo", "to": "cmp:C1",
     "dx_mm": 5.0, "dy_mm": 1.0, "rotation_deg": 0, "weight": 0.6},
    {"id": "ccg:6", "from": "mod:ldo", "to": "cmp:C2",
     "dx_mm": 1.0, "dy_mm": 4.0, "rotation_deg": 0, "weight": 0.6},
    {"id": "ccg:7", "from": "mod:sense", "to": "cmp:U2",
     "dx_mm": 1.0, "dy_mm": 1.0, "rotation_deg": 0, "weight": 0.9},
    {"id": "ccg:8", "from": "mod:sense", "to": "cmp:R1",
     "dx_mm": 6.0, "dy_mm": 1.0, "rotation_deg": 0, "weight": 0.5}
  ],
  "policy": {"max_depth": 6, "default_allowed_rotations": [0],
             "position_tolerance_mm": 1e-6, "weight_epsilon": 1e-9},
  "provenance": {"kind": "synthetic", "sources": [],
                 "note": "Synthetic fixture for the placement-intent contract; not a real board."},
  "unknowns": []
}
```

该输入：root 帧 `(0,0)`；`mod:power` `(5,5)`；`mod:ldo` `(8,7)`；
`cmp:U1` `(9,8)`、`cmp:C1` `(13,8)`、`cmp:C2` `(9,11)`；
`mod:sense` `(25,5)`；`cmp:U2` `(26,6)`、`cmp:R1` `(31,6)`（均为根帧，rotation=0）。

自底向上的 bbox（均在各自节点的局部帧，**不归一**）：

- `mod:ldo` 子项 U1 `(1,1,3,3)`、C1 `(5,1,1,2)`、C2 `(1,4,1,2)` →
  `{"x":1,"y":1,"w":5,"h":5}`（x 1–6，y 1–6；在声明的 8×6 内）。
- `mod:power` 的子项 `mod:ldo` 在 power 帧 `(3,2)`，其 bbox 框再叠加 → x 4–9，y 3–8 →
  `{"x":4,"y":3,"w":5,"h":5}`（在声明的 14×8 内）。
- `mod:sense` 子项 U2 `(1,1,4,4)`、R1 `(6,1,1,2)` → `{"x":1,"y":1,"w":6,"h":4}`。
- `mod:board`：power 块在 board 帧 → x 9–14，y 8–13；sense 块 → x 26–32，y 6–10；
  并集 → `{"x":9,"y":6,"w":23,"h":7}`（在声明的 40×30 内）。
- 兄弟重叠：ldo 的 U1/C1 只在 x=4/5 贴边（面积 0），C2 与 U1 只在 y=4 贴边；board 的
  power/sense 不相交 → 无 `sibling_overlap`。因此该输入为 `planned_with_scope`。

### 11.2 `plan` 片断

```json
{
  "schema": "easycirq.placement-intent.plan/v1",
  "status": "planned_with_scope",
  "exit_code": 0,
  "anchor": "top-left",
  "levels": [
    {"depth": 0, "nodes": [
      {"id": "mod:board", "kind": "module", "label": "Demo board", "parent": null,
       "frame": {"offset_mm": [0.0, 0.0], "rotation_deg": 0.0, "known": true},
       "bbox_mm": {"x": 9.0, "y": 6.0, "w": 23.0, "h": 7.0},
       "size_mm": {"w": 40.0, "h": 30.0}, "allowed_rotations": [0],
       "fixed": false, "confidence": null,
       "children": ["mod:power", "mod:sense"], "components": [], "unknowns": []}]}
  ],
  "placement_applied": false,
  "routing_verified": false,
  "physical_validation": "NOT RUN",
  "real_eda": "NOT RUN",
  "eda_calls": 0
}
```

### 11.3 `explain`（`--constraint ccg:3`）

```json
{
  "schema": "easycirq.placement-intent.explain/v1",
  "subject": {"type": "constraint", "id": "ccg:3"},
  "status": "explained",
  "constraint": {"id": "ccg:3", "from": "mod:power", "to": "mod:ldo",
                 "dx_mm": 3.0, "dy_mm": 2.0, "rotation_deg": 0,
                 "weight": 0.8, "source": null, "aliases": []},
  "synthesis": {"anchor_node": "mod:board",
                "path": ["mod:board", "mod:power", "mod:ldo"],
                "steps": [
                  {"edge": "ccg:1", "from": "mod:board", "to": "mod:power",
                   "origin_before_mm": [0.0, 0.0], "rotation_before_deg": 0.0,
                   "origin_after_mm": [5.0, 5.0], "rotation_after_deg": 0.0},
                  {"edge": "ccg:3", "from": "mod:power", "to": "mod:ldo",
                   "origin_before_mm": [5.0, 5.0], "rotation_before_deg": 0.0,
                   "origin_after_mm": [8.0, 7.0], "rotation_after_deg": 0.0}],
                "target_origin_mm": [8.0, 7.0], "target_rotation_deg": 0.0,
                "alternate_paths": [], "consistent": true},
  "conflicts": [],
  "unknowns": [],
  "not_checked": ["path is a constraint-graph path, not a copper route"],
  "notes": []
}
```

### 11.4 mil 输入

`{"units": {"length": "mil"}}` 下 `dx_mm: 1000` 表示 `1000 mil = 25.4 mm`；
报告 `units.scale_to_mm = 0.0254`，`normalized_constraints[].dx_mm = 25.4`。
等价 mm 输入（`dx_mm: 25.4`）在 `position_tolerance_mm` 容差内得到同一计划。

---

**本契约结束。** 契约之外的能力（求解绝对坐标、应用放置、布线、DRC、仿真、训练）
一律 `NOT RUN`；实现不得为了“跑通”而补默认值、吞 unknown 或把重叠当成通过。
