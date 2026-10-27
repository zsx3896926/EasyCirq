# 影响传播规则（J2 `propagate.py`）

本文档描述 `design-hardware/scripts/change_impact/propagate.py` 的实现规则，是
`docs/parallel-change-impact/contract.md` §3 `propagate.py` 的展开说明。实现只做
离线、只读、确定性的推断：不调用 EDA/执行器/仪器，不写设计，不执行输入内容；
所有结论都必须能追溯到声明的对象、依赖边、变更记录。**没有边不是无影响**：
缺数据进入 `unknown`，而不是进入空结果。

- 入口：`propagate(model, graph, classification, *, budget=None) -> dict`
- `model`：`model.Model`（`validate_model` 的产物）
- `graph`：`graph.Graph`
- `classification`：`classify.compare_declared_to_observed(model)` 的返回 dict
  （读取其 `declared` 列表），也可直接传等价的分类列表
- 返回：`impact_paths`、`impacted_objects`、`unknown`、`truncated`、`budget`、
  `cycles`、`rules_applied`

---

## 1. 总原则

1. **按类别匹配传播，不全图扩散。** 一条依赖边只有在「变更类别 + 依赖语义」被某条
   规则显式配对时才被跟随。规则 ID 为 `R1..R14`（契约要求的 14 类）加
   `R15..R17`（连接性、文档元数据、未知属性，覆盖 `CHANGE_KINDS` 全集）。
2. **每条规则声明：触发变更类别、允许的依赖语义、产生的 impact（取自
   `IMPACT_KINDS`）、基础 confidence（取自 `CONFIDENCES`）、停止条件、依据。**
   规则表在模块里以 `RULES` / `RULE_IDS` 暴露，导入时校验其取值全部落在
   `__init__.py` 的枚举内，因此规则表本身不会写出契约外的 impact/confidence。
3. **confidence 只表达“这条推断有多确定”，不表达“设计正确/已验证”。**
   `certain` = 该影响必然需要复核；`possible` = 语义上可能、需要人工判断；
   `unknown` = 目前无法判定。任何路径都不会被宣称为“无影响”。
4. **直接与间接都记录。** 被改对象本身产生 0 步 direct 记录；每一步传播产生到
   下一对象的路径记录；中间载体对象也会被记录，但其记录标为
   `stop_reason="deduplicated"`，表示它只是更长解释的前缀，不能当作链条终点。
5. **循环、预算、缺数据都必须显式可见**（`cycles`、`truncated`/`frontier`、
   `unknown`），不能靠“遍历结束”暗示安全。

---

## 2. 规则表

`Mechanical pose` 规则按属性路径分流：`layer` / `layers.*` / `stackup*` 归
`R9_layer_stack`，其余 pose 归 `R5_mechanical_pose`；显式声明
`kind=layer_stack` 时也归 R9。

| ID | 触发变更（change kind） | 允许跟随的依赖语义 | 产生 impact | 基础 confidence | 停止条件（摘要） | 依据 |
|---|---|---|---|---|---|---|
| R1_power_requirement | `power_requirement`（电源范围/电压/电流要求） | `power_supply` | `power_integrity`；direct=`electrical_state` | certain | 无 power_supply 边、到达自然消费者、其他语义边即 semantic_mismatch | 契约 §2.2/§2.3；电源范围只沿供电关系传播 |
| R2_component_identity | `component_identity`（MPN/manufacturer/LCSC/UUID） | `footprint_binding`、`power_supply`、`signal_path`、`artifact_source`、`firmware_consumer` | `footprint_compatibility`、`electrical_state`、`signal_integrity`、`bom_variant`/`manufacturing_output`、`firmware_compatibility`；direct=`electrical_state` | possible（BOM/封装绑定可 certain） | 到达交付/消费端点；电气后果保持“未证明等价” | 契约 §2.2；相同封装不证明电气等价 |
| R3_footprint | `footprint`（footprint./package./symbol.） | `footprint_binding`、`mechanical_constraint`、`enclosure_constraint`、`artifact_source` | `footprint_compatibility`、`mechanical_fit`、`enclosure_interface`、`assembly_fit`/`manufacturing_output`；direct=`footprint_compatibility` | certain（enclosure 为 possible） | 无封装/机械/壳体边 | 契约 §2.2、§6 C/G |
| R4_pin_mapping | `pin_mapping`（pins./pin./pinout./pin_function） | `pin_mapping`、`signal_path`、`power_supply`、`firmware_consumer` | `pin_compatibility`、`signal_integrity`、`electrical_state`、`firmware_compatibility`；direct=`pin_compatibility` | certain（固件消费 possible） | 无引脚/电气/固件边 | 契约 §2.2 |
| R5_mechanical_pose | `mechanical_pose`（placement./position./rotation/mirror，非层/叠层） | `mechanical_constraint`、`enclosure_constraint`、`artifact_source`、`signal_path` | `mechanical_fit`、`enclosure_interface`、`assembly_fit`/`manufacturing_output`、`signal_integrity`；direct=`mechanical_fit` | certain（壳体/产物/信号 possible） | 无机械/壳体/装配边 | 契约 §2.2、§6 G（接口 pose → 壳体开口与贴装产物） |
| R6_identity_rename | `identity_rename`（name/net_name/designator/display_name/instance_name） | `document_reference`、`signal_path`、`power_supply`、`pin_mapping`、`firmware_consumer`、`artifact_source` | `documentation_only`；电气类 impact 按分区证据降级；direct=`electrical_state` | possible / unknown（见 §3.3） | 文档引用为 certain；电气链条受分区证据约束 | 契约 §2.1（重命名 vs 分区）、classify 保守重命名 |
| R7_display_only | `display_only`（display./annotation./text_style./label_offset./silk_text./visual./doc_note.） | 仅 `document_reference` | `documentation_only` | certain | **显式显示边界**：只追加文档引用；电气/交付语义边一律不跟随，`stop_reason=display_only_boundary` | 契约 §2.2；显示文字不使固件/BOM/电气失效 |
| R8_board_outline | `board_outline`（board.outline/outline/hole(s)/mounting_hole/board_frame/edge.） | `mechanical_constraint`、`enclosure_constraint`、`artifact_source` | `mechanical_fit`、`enclosure_interface`、`manufacturing_output`；direct=`mechanical_fit` | certain（壳体 possible） | 无机械/壳体/制造产边 | 契约 §2.2、§6 C/G |
| R9_layer_stack | `mechanical_pose` + layer/layers/stackup 路径，或 `layer_stack` | `signal_path`、`power_supply`、`artifact_source` | `signal_integrity`、`power_integrity`、`manufacturing_output`；direct=`signal_integrity` | certain（电源 possible） | 无信号/电源/制造产边 | 契约 §2.2；叠层改变影响阻抗/参考面与制造输出 |
| R10_delivery_config | `delivery_config`（dnp/bom./assembly./variant./delivery./fitted/population.） | `artifact_source`、`footprint_binding`、`test_reference`、`verification_coverage` | `bom_variant`（BOM 目标）/`manufacturing_output`（artifact）、`assembly_fit`、`test_criterion_change`；direct=`bom_variant` | certain（装配/测试 possible） | 无交付/装配/测试边 | 契约 §2.2、§6 C/H（DNP、替代） |
| R11_firmware_contract | `firmware_contract`（firmware./peripheral./register./clock./io_contract.） | `firmware_consumer`、`signal_path`、`pin_mapping`、`requirement_ref` | `firmware_compatibility`、`signal_integrity`、`pin_compatibility`、`requirement_trace`；direct=`firmware_compatibility` | certain（电气/需求 possible） | 无固件/电气/需求边 | 契约 §2.2 |
| R12_test_criterion | `test_criterion`（test./limit./threshold./acceptance.） | `test_reference`、`verification_coverage`、`requirement_ref` | `test_criterion_change`、`requirement_trace`；direct=`test_criterion_change` | certain | 只到引用该判据的测试/证据与需求，不扩散到无关电气证据 | 契约 §2.2、§6 I |
| R13_parameter | `parameter`（value/resistance/capacitance/inductance/tolerance/rating./parameters.） | `power_supply`、`signal_path`、`pin_mapping`、`test_reference`、`verification_coverage` | `electrical_state`、`signal_integrity`、`pin_compatibility`、`test_criterion_change`；direct=`electrical_state` | certain（引脚/测试 possible） | 无电气/测试边 | 契约 §2.2、§6 F |
| R14_requirement | `requirement`（requirement./requirement_id/trace.） | `requirement_ref`、`verification_coverage`、`document_reference` | `requirement_trace`、`test_criterion_change`、`documentation_only`；direct=`requirement_trace` | certain（覆盖/文档 possible） | 无追踪/覆盖/文档边 | 契约 §2.2 |
| R15_connectivity | `connectivity`（net/nets/connectivity./electrical.，即网络分区变化） | `signal_path`、`power_supply`、`pin_mapping`、`firmware_consumer`、`test_reference` | `signal_integrity`、`power_integrity`、`pin_compatibility`、`firmware_compatibility`、`test_criterion_change`；direct=`electrical_state` | certain | 无电气/固件/测试边 | 契约 §2.2 connectivity |
| R16_document_metadata | `document_metadata`（document./title_block./revision/sheet.） | `document_reference`、`artifact_source`、`requirement_ref` | `documentation_only`、`manufacturing_output`、`requirement_trace`；direct=`documentation_only` | certain（产物/需求 possible） | 无文档/产物/追踪边 | 契约 §2.2 |
| R17_unknown_attribute | `unknown_attribute`（未映射属性，不得归为显示变更） | 无（不传播） | `unknown` | unknown | 属性类别未映射，影响范围不明；只报 direct unknown，不猜 | 契约 §2.2 显式未知 |

补充：

- `artifact_source` 的 impact 由**目标对象 kind** 细化：`bom_line → bom_variant`、
  `artifact → manufacturing_output`、`document → documentation_only`，其余保持
  规则表中该语义的默认值。
- 每条规则还声明 `terminal_kinds`（自然消费者/终点对象类），用于区分“链条在此
  语义性结束”和“图里缺边”。当前终点类为：
  `component_instance, power_domain, interface, layout_region, mechanical_anchor,
  bom_line, firmware_contract, test, artifact, requirement, document`。
  `net` 与 `pin` 是**纯载体**，刻意不是终点：它们在缺边时会进入
  `missing_edge_data`，从而暴露“未遍历≠无影响”。
- 规则表本身不做 I/O，不读环境，不依赖输入列表顺序。

---

## 3. 路径如何生成

### 3.1 直接（direct）记录

每条被分类的变更先产生一条 0 步路径：`target` 就是被改对象，
`target_kind` 取其 kind，`impact`/`confidence` 由规则的 direct 语义决定
（`R1` 为 `electrical_state/certain`、`R2` 为 `electrical_state/possible`、
`R6` 按分区证据、`R17` 为 `unknown/unknown` 等）。`impacted_objects` 中该对象
`direct=true`。direct 记录的 `change_ids` 精确到该变更；多个变更命中同一
(target, impact, 规则, 路由) 时会合并并保留完整 `change_ids`（见 §4）。

### 3.2 传播与 confidence 链

从 direct 记录出发做确定性 BFS。每一步：

- 只取 `graph.successor_edges(node, rule.semantics)` 中与规则语义匹配的边；前向边
  正向走，`direction=bidirectional` 的边可反向走；**声明为 forward 的边不会为了
  电气传播而反向遍历**。
- 每步 impact 由「规则 × 该步语义 × 目标 kind」决定；confidence 为
  `weakest(链上 confidence, edge.confidence(该步基础 confidence))`。
  `Edge.confidence` 的映射：`declared/observed` 保持基础 confidence，
  `inferred` 把 `certain` 降为 `possible`，`unknown` 直接降为 `unknown`。
- 链上 confidence 从 `certain` 起算；direct 记录的 confidence 是规则自己的直接
  confidence，不会被“更保守的 direct 推断”人为拖累下游（例如 R2 的 direct 是
  possible，但经 `artifact_source` 到 BOM 的影响仍是 certain）。
- 传播路径的 confidence 若为 `unknown`，或语义未定（重命名分区未知、未知属性、
  缺边数据），路径 `undetermined=true`。

### 3.3 重命名（R6）不是短路

`identity_rename` 只声明“名字变了”，不声明“分区没变”：

- `partition_evidence=proven_same`：明确写入条件
  `partition_evidence=proven_same: the partition did not change, but a rename is
  not proof of no impact`；电气类 impact 的 confidence 降为 `possible`（不会被
  判成 `certain`，也不会被当作无影响）。
- `partition_evidence=changed`：电气类影响升级为 `certain`。
- 分区证据缺失（`unknown`）：电气类 impact 的 confidence 为 `unknown`，
  路径 `undetermined=true`，并产生 `unknown` 条目
  `{code: "rename_partition_unknown", object: 被改对象, ...}`。
- `document_reference` 方向的 `documentation_only` 始终 `certain`：改名确实要更新
  文档引用。

### 3.4 仅显示属性（R7）

`display_only` 只允许 `document_reference` 语义。遇到电气（`power_supply` /
`signal_path` / `pin_mapping` / `firmware_consumer`）、交付
（`artifact_source`）等边时，**不会跟随**，路径以
`stop_reason="display_only_boundary"` 结束；不产生 firmware/BOM/电气类 impact。
该边界是规则显式语义（显示文字本来就不改变电气），因此不依赖“图里有没有边”，
也不产生 missing-edge 的 unknown。若存在 `document_reference`，则继续到
documentation_only。

### 3.5 路径字段

| 字段 | 含义 |
|---|---|
| `path_id` | `path:0001` 形式，先按 `(target, impact, trigger_rule, 路由, change_ids)` 排序后统一编号，稳定可复现 |
| `target` / `target_kind` | 受影响对象及其 kind |
| `impact` | 该目标上的影响类别（`IMPACT_KINDS`） |
| `change_ids` | 完整来源集合（合并后不丢失任何来源，排序去重） |
| `confidence` | `certain/possible/unknown`，取整条解释链最弱者 |
| `steps` | `[{from,to,edge,semantic,conditions}]`，按传播顺序；direct 为空列表 |
| `trigger_rule` | 规则 ID（`RULES` 中的值） |
| `stop_reason` | 见 §6，取值来自 `STOP_REASONS` |
| `conditions` | 变更自身条件 + 各步边条件 + 规则特殊说明（重命名分区、相似性陷阱、未知属性）+ 电气类目标上的硬约束 `constraint:<id>`，排序去重 |
| `evidence` | `[{edge_id, certainty}]`，逐步来源边及其声明 certainty；direct 为空 |
| `undetermined` | 影响范围/置信是否未定（重命名分区未知、未知属性、缺边、`unknown` 置信） |

---

## 4. 聚合、去重与多源合并

- **路径去重**：同一 `(target, impact, trigger_rule, 完整路由)` 的路径视为同一
  解释，合并为一条：`change_ids` 取并集（完整保留多源），`confidence` 取最弱，
  `conditions`/`evidence` 取并集，`undetermined` 取或；`stop_reason` 优先保留
  真正的终止原因而不是 `deduplicated`。
- **不同解释不合并**：同一 `(target, impact)` 但路由/规则不同的路径分别保留，
  `impacted_objects.path_ids` 列出全部 `path_id`，不覆盖任何一条解释。
- **`impacted_objects`**：按 `(kind, object)` 排序；每条
  `object/kind/impacts/confidence/change_ids/path_ids/direct`；
  `impacts` 升序去重，`confidence` 取该对象所有路径的最弱者，`change_ids` 为所有
  路径来源并集，`path_ids` 升序去重，`direct` 表示是否存在 0 步记录。
- 多源示例：同一网络上的 `power.voltage` 与 `power.rated_current` 两条
  `power_requirement` 变更经同一条 `power_supply` 边到达同一器件时，该路径
  `change_ids=["chg:1","chg:2"]`，不丢失任一来源。
- **中间载体记录**：如果对象还能继续传播，它的记录以
  `stop_reason="deduplicated"` 标记为“更长路径的前缀”，避免把“链条经过它”误读
  成“链条终止于它”；真正的终点才使用 `leaf_object`、`declared_boundary`、
  预算/循环等终止原因。若某个对象的所有后继都已被访问（菱形/并行路由），新增
  记录用 `already_visited`；若后继是当前路径的祖先，用 `cycle_detected`。

---

## 5. 缺失数据与未知边界

`unknown` 条目统一为 `{code, object, reason, change_ids}`，按 `(code, object)` 排序，
同一 `(code, object)` 的 `change_ids` 取并集。当前 code：

| code | 触发条件 | 含义 |
|---|---|---|
| `missing_edge_data` | 非显示规则在 `net`/`pin` 等载体对象上无**规则兼容**的后继边，且 `graph.boundary()` 返回 `missing_edge_data` | 未声明边不是无影响；该传播路径的 confidence 置 `unknown`、`undetermined=true` |
| `budget_exhausted` | 预算截断时 frontier 中的对象 | “未遍历≠无影响”，并列入 `budget.frontier` |
| `rename_partition_unknown` | R6 且分区证据缺失 | 重命名电气影响未定，不能当短路 |
| `unknown_attribute_change` | R17（属性未映射） | 影响类别未知，不得归为显示变更 |
| `unknown_change_object` | 分类记录指向图中不存在的对象 | 无法传播，显式报未知 |
| `invalid_change_record` | 分类记录缺少 `change_id` | 无法追溯，显式报未知 |

边界判定顺序（无兼容后继时）：

1. R7 → `display_only_boundary`（显式语义边界，不产生 unknown）；
2. 目标 kind 命中规则 `terminal_kinds` → `leaf_object`（规则语义链自然终点）；
3. 对象存在其他语义的出边 → `semantic_mismatch`（有依赖但类别不匹配，不是缺数据）；
4. 否则调用 `graph.boundary()`：显式 `declared_boundary` 才允许作为
   `stop_reason="declared_boundary"`（不加 unknown）；返回
   `missing_edge_data` 时必须输出 unknown，**不能用 leaf 静默代替**。

`_make_path` 不会修改 model/graph；`unknown` 只是报告事实，不是失败状态。

---

## 6. 停止原因（`STOP_REASONS`）

| stop_reason | 何时使用 |
|---|---|
| `leaf_object` | 规则语义链到达自然消费者/终点点（`terminal_kinds`），无需继续 |
| `semantic_mismatch` | 对象有出边，但没有一条属于本规则允许的语义（不是缺数据） |
| `display_only_boundary` | R7 拒绝跨入电气/交付语义（显式显示边界；direct 与文档 target 都可能出现） |
| `declared_boundary` | `graph.boundary()` 明确声明“已声明依赖到此结束”，仅此时可用 |
| `already_visited` | 同一对象+impact 已被更早路径访问且不是当前路径祖先（菱形/并行路由） |
| `cycle_detected` | 后继是当前路径的祖先（真环） |
| `depth_budget` | 到达 `max_depth`，未能展开 |
| `path_budget` | 预算保留枚举值；当前实现在队列入口统一截断并以 frontier/unknown 表达，故通常不单独产出该值 |
| `deduplicated` | 该对象是仍在继续传播的中间载体，其记录只是更长解释的前缀 |
| `missing_edge_data` | 载体对象缺规则兼容后继且 `graph.boundary()` 为 missing（同时产生 unknown） |

任何停止原因都**不是**“设计无影响”的证明；只有显式 `declared_boundary` 才允许
被下游读成“已声明依赖范围内没有更多传播”，且仍需结合 `model_scope`。

---

## 7. 循环

- `cycles` 直接来自 `graph.cycles`（Tarjan SCC 结果，按对象排序），确定性输出。
- 遍历使用 `visited` 集合，键为 `(对象, impact)`：同一对象上不同 impact 可以各
  自展开一次，但同 `(对象, impact)` 只展开一次，保证收敛。
- 后继已在 visited 时：若后继是当前路径的祖先 → `cycle_detected`，否则
  `already_visited`；两种情况都只新增终止记录、不入队，因此有环图必然终止。
- 环不是错误，但也不能被当作“传播完成”；环所在的路径保留完整 steps 与来源。

---

## 8. 预算

- 默认取 `model.budget` 的 `max_depth` / `max_paths`（默认 8 / 500），可用
  `budget=` 参数覆盖；只读取这两个键，其他预算键（如 `max_cost`）由后续模块负责。
- 达到 `max_depth`：节点记录 `stop_reason="depth_budget"`，不再展开，节点进入
  `budget.frontier`，`truncated=true`。
- 达到 `max_paths`：队列中尚未展开的对象进入 `budget.frontier`，
  `truncated=true`，不再创建新路径记录。
- `budget` 输出：`{max_depth, max_paths, used_paths, max_depth_used, frontier}`；
  `used_paths` 为最终路径记录数，`max_depth_used` 为最终路径的最大步数，
  `frontier` 为因预算未展开的对象（排序去重）。
- 每个 frontier 对象产生 `unknown` 条目 `code="budget_exhausted"`，说明
  “未遍历≠无影响”；`truncated=true` 时下游报告状态应为 `incomplete`。
- `max_paths` 为 0 的退化输入不产生路径记录，但其对象会进入 frontier/unknown，
  不会被静默丢弃。

---

## 9. 确定性

- 所有列表显式排序：路径先按 `(target, impact, trigger_rule, 路由, change_ids)`
  编号再按 `(target, impact, path_id)` 输出；`impacted_objects` 按
  `(kind, object)`；`unknown` 按 `(code, object)`；`rules_applied`、`cycles`、
  `budget.frontier` 均排序。
- 遍历顺序由 `graph` 的边排序（semantic, edge id）与分类记录排序
  `(change_id, object, attribute)` 决定，不依赖输入对象/依赖/变更列表的书写顺序。
- 不读取环境变量、时间、随机数、网络；不产生时间戳或随机 ID。同一输入（含列表
  乱序）得到相同输出。

---

## 10. 明确局限

- 只在**声明的依赖图**上推理；`model_scope.dependencies_complete=false` 时，缺边
  只能报 `unknown`，不能补全。真实 EDA 连接/DRC/保存重开/官方导图/实物测试都
  不在本模块能力内（见契约 §5 的 `not_run`）。
- 规则表是保守的“可能影响”语义，不是正确性证明；`possible` 不表示“大概没问题”。
- 重命名的分区证据依赖 `classify` 提供的 `partition_evidence`（或对象上
  `members/pins/membership/partition` 属性的两侧比较）；没有证据即 `unknown`。
- 层/叠层与普通 pose 共用 `mechanical_pose` 变更类别，靠属性路径前缀
  （`layer`/`layers.`/`stackup`）分流；属性路径写法超出该前缀时按 pose 处理。
- `artifact_source` 的具体 impact 依赖目标对象 kind；kind 缺失或非常见组合时使用
  规则默认 impact，并保持同样保守的 confidence。
- `display_only` 只追加 `document_reference → documentation_only`。`artifact`
  对象同时包含 Gerber/CPL 等制造产物，仅凭 kind 无法可靠区分“图面/绘图产物”，
  因此不把显示变更自动扩展为 `artifact_source` 制造影响；如果图面产物本身需要
  复核，应在模型里用 `document_reference` 显式声明。（这是保守的少报，避免把
  图面文字变更误升级为制造/采购失效。）
- `deduplicated` 是对“中间载体记录”的显式标记，避免把它误读为链条终止；下游
  （J3 证据评估、J4 验证计划、J6 报告）应把 `stop_reason` 与其 `undetermined`
  一起消费，而不是只看是否有路径。
- 测试：`tests/change_impact/test_propagation.py`（stdlib unittest，46 个用例，
  含“每条规则正/负/unknown”的表驱动覆盖），运行：

  ```text
  python -m unittest discover -s tests -p "test_propagation.py" -v
  ```
