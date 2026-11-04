# ACE 评审与自主迭代决策记录（ADR）

> 状态：accepted（2026-10-29）。范围：ACE 评审器（确定性快照规则）、错误注入度量、评审门禁、非矩形可打印区、块模板与保存后回读这 6 项取舍；不记录实现细节。
> 评审清单：[ace-review-checklist.md](ace-review-checklist.md)。布局引擎设计：[layout-engine-v2.md](layout-engine-v2.md)；其 v2 ADR：[layout-engine-adr.md](layout-engine-adr.md)。
> 规则：与 [layout-engine-adr.md](layout-engine-adr.md) 相同——口径/阈值改动必须在这里留记录，写明来源与复测触发；被推翻的条目保留并标 `superseded by ADR-xxx`，不删除。

## 0. 索引

| ADR | 决策 | 状态 | 一句话后果 |
|---|---|---|---|
| [ADR-001](#adr-001-确定性快照评审不用-llm) | 评审只读快照、规则是纯函数，不用 LLM | accepted | 评审可复现、可回归、可批量；只覆盖快照能表达的东西 |
| [ADR-002](#adr-002-错误注入用-applicabledetected-度量评审能力) | 错误注入用 `applicable/detected` 度量评审能力 | accepted | 能力与设计质量分开；不可注入项本身是结论 |
| [ADR-003](#adr-003-评审门禁在-apply-前-fail-closed) | 评审门禁在 apply 前 fail-closed | accepted（门禁实现 PENDING） | error 级评审结果直接阻止落点，不再只是建议 |
| [ADR-004](#adr-004-非矩形可打印区用矩形并集表达) | 非矩形可打印区用矩形并集表达，zone 仍是矩形 | accepted | 消除"框压标题栏"类错误；跨 region 的 zone 不允许 |
| [ADR-005](#adr-005-块模板-roledxdy-消除落点漂移) | 块模板用 role→(dx,dy) 消除落点漂移 | accepted（role 模板 PENDING） | 落点不再靠真机试错；未收录角色 → `blocked` |
| [ADR-006](#adr-006-save-after-apply-作为流水线不变量) | save + `doc reload` + 回读是流水线不变量 | accepted（真机 NOT RUN） | "命令返回 0"不再等于"已保存、已生效" |

## 实现状态（2026-10-29）

本文把**决策**与**实现状态**分开写：未合并/未实测的条目一律标 PENDING 或 NOT RUN，不写成已完成。

| 组件 | 状态 | 证据/口径 |
|---|---|---|
| 快照 + 确定性规则（#210 起 10 条，#219 扩到 30 条） | 已入 main（#210/#219） | `easycirq-ace-snapshot/v1`、`easycirq-ace-review/v1`；`RULES` 表 30 条；`tests/test_ace_review.py` 64 tests OK |
| 错误注入 harness（`applicable/detected`） | 已入 main（#210；#211 增 additive） | `easycirq-ace-injection/v1`；synthetic clean **17/17**、corpus clean **16/16** 全部检出 |
| 干净/变异语料（golden corpus） | 已入 main（#211） | `easycirq/assets/ace-corpus/`：`clean-reference.json` + expected + 3 个 bad 快照；`tests/test_ace_corpus.py` 13 tests OK |
| 自由布局（freeform L 形 + 矩形并集 zones） | 已入 main（#212） | `tools/layout2/freeform.py`（`subtract_rect` → L 形/矩形补集，zone 按 `rects` + `zone_kind=rect/union` 输出）；`tests/test_layout2_freeform.py` 21 tests OK |
| 规则扩充 10 → 30 条 | 已入 main（#219） | `tools/ace_review.py` 的 `RULES` 表（ID 稳定 R01–R30）；R11–R30 各带正/反例单测（`test_ace_review.py`）；注入器补 R11–R30 变异仍在债务里 |
| 确定性修复计划（fix plan） | 已入 main（#217） | `tools/ace_fix_plan.py`（`easycirq-ace-fix-plan/v1`，有序 `fx-NN` 动作）；`tests/test_ace_fix_plan.py` 6 tests；真实页 actions A/B/C = 22/13/17 |
| 评审门禁（gate）阻塞 apply | 已入 main（#214） | `tools/review_gate.py`（`easycirq-review-gate/v1`，strict 默认 / advisory）；已接入 `tools/run_layout_pipeline.py`（`--require-review`/`--review-advisory`）；`tests/test_review_gate.py` 24 tests OK |
| 非矩形可打印区 + 矩形并集 zones | 资产/规则已入 main，通用判定由 freeform 实现覆盖 | `easycirq/assets/page-template.json` 的 `regions[]`；`hard_rules` R1/R2；freeform 的 `rects[]` |
| 块模板 role→(dx,dy) | 已入 main（#215） | `tools/layout2/role_resolver.py`（确定性 1-1 角色绑定）+ `tools/layout2/templates.py`（`easycirq-block-template/v1`，相对几何 + 纯平移实例化）；`tests/test_layout2_templates.py` 31 tests OK |
| save-after-apply（`doc reload`） | **尚未实现（PENDING）**；真机 **NOT RUN** | 本文 ADR-006 定义流水线尾部与证据字段；当前 apply 路径未接 save/reload/回读 |

## ADR-001 确定性快照评审，不用 LLM

- **状态**：accepted（2026-10-29）
- **决策域**：L2 规则 + L3 工具
- **关联**：评审清单 §数据来源、§规则；设计文档 [layout-engine-v2.md](layout-engine-v2.md) §4

### 背景

"王牌工程师签板前会问什么"本身是稳定的：上拉在哪、去耦离脚多远、地怎么分、EN 默认态是什么。但让 LLM 直接做这件事有三个硬伤：同一份图两次评审结论可能不同（不可回归）、无法批量跑基准（不可度量）、可能给出图里并不存在的"发现"（幻觉）。同时 EDA 是单写者、慢且会卡死，评审不能每次都连真机读页面。

### 决策

1. 评审输入固定为**只读快照** `easycirq-ace-snapshot/v1`：`components`（ref/bbox/pins + pin 的 net）、`connectivity`、`titleblock`；快照由采集脚本 `tools/ace_snapshot.py` 从活动页生成，评审器不碰 EDA。
2. 每条规则是**纯函数** `rule_xxx(snapshot, findings)`，只依赖快照字段；评审入口按固定顺序执行全部规则，输出 `easycirq-ace-review/v1`：`findings[{rule, severity, message, refs}]` + `metrics{errors, warnings, rules}` + `verdict`。
3. verdict 口径：任一 `severity=error` → `blocked`；否则 `pass`。`warn` 只记录、不阻塞（由 gate/人工决定是否升级）。
4. LLM 的职责收窄为"把用户意图变成 block/netlist spec"；**评审、判定、回归全部由脚本完成**。
5. 快照必须可绑定：评审报告记录快照来源（页 UUID、采集时间、组件数）；变更页面后旧报告不得复用。

### 备选与不采用理由

| 备选 | 不采用理由 |
|---|---|
| LLM 直接读页面/截图评审 | 不可复现、不可批量、会幻觉；规则是否执行无法回归 |
| 评审时现场调 EDA 读 | 评审要能离线批量跑；EDA 慢、单写者、会卡死（FX-01） |
| 只用正则/命名规则（不看连通性） | 上拉、去耦、地 tie 都依赖 pin→net 与几何，纯文本不够 |
| 人工评审清单 | 不可批量、易漏项；无法作为 apply 前置门禁 |

### 后果

- **正面**：同一快照同一结论；规则可单测、可注入、可基准；评审可以进 CI 和 scoreboard。
- **代价/风险**：评审上限由快照字段决定（没有 value/封装/多页信息就写不了某些规则）；快照与页面漂移会得到"对旧图正确"的报告。
- **缓解**：快照 schema 版本化；报告带快照绑定字段；新增规则先扩快照再写规则，不从截图猜。

### 复测触发

1. 快照 schema 或采集命令字段变化。
2. 任一规则改判定式/级别（同步评审清单与注入用例）。
3. EDA 读回字段语义变化（bbox 单位、pin number 映射、net 命名）。
4. 出现"快照正确、页面已变"的事故（报告复用于新页面）。

## ADR-002 错误注入用 applicable/detected 度量评审能力

- **状态**：accepted（2026-10-29）
- **决策域**：L4 测试 + L5 决策
- **关联**：评审清单 §错误注入、§当前结果

### 背景

真实板评审出 0 个 error 有两种完全不同的解释：图没问题，或者评审器根本没用。只看 error 数会把"设计质量"和"评审能力"混在一起；只写规则单测又证明不了端到端能检出。必须有一个不依赖真实板、又能直接度量评审器能力的口径。

### 决策

1. **对干净语料做单点变异**：每个变体只改一处（删/移/断/重命名），并声明预期规则 ID。
2. 两个状态字段：
   - `applicable`：目标结构存在且基线未违规——即"能注入"。结构本来就没有（例如板上根本没有上拉），就没有可删除的对象，这一条不计入能力分母；
   - `detected`：变异后**预期规则**出现，且相对基线计数增加或新规则出现（不能只看 verdict 变 blocked）。
3. `detection_rate = detected / applicable`；报告 schema `easycirq-ace-injection/v1`，逐条列出 `mutation / rule / applicable / detected / baseline_verdict / mutated_verdict`。
4. **不可注入项单列**，不混进分母，并作为"结构完整性"证据输出——这是度量设计质量的部分，不是评审器缺陷。
5. 能力验收线：干净语料上 `applicable` 全部 detected（当前 synthetic clean **17/17**、corpus clean **16/16**）；新增规则必须至少带 1 个 applicable 变异，否则规则视为"未证明有效"。R11–R30 目前只有单测正/反例、注入器变异仍是债务（见评审清单）。

### 备选与不采用理由

| 备选 | 不采用理由 |
|---|---|
| 只统计真实板 error 数 | 混淆设计质量与评审能力；0 error 无法区分"好"与"瞎" |
| 只做规则单测（构造 findings） | 证明函数能跑，不证明从快照到结论的链路有效 |
| 人工评审一批板子做 ground truth | 不可批量、成本高、主观；可作为补充证据，不能作为回归基线 |
| 注入后只看 verdict 是否 blocked | warn 级规则不改变 verdict；且无法区分是预期规则触发还是别的规则误触发 |

### 后果

- **正面**：评审器能力可量化、可回归；规则"写了但没测"会被暴露；"不可注入"直接指向结构缺失。
- **代价/风险**：变异器要知道每类结构长什么样（维护成本）；合成语料与真实板分布不同，检出率高不代表真实板全覆盖。
- **缓解**：每条规则 ≥1 变异；语料冻结并哈希；真实板只做补充验证，不替代注入回归。

### 复测触发

1. 新增/修改规则（同步加变异，否则 CI 视为覆盖缺口）。
2. 评审器判定式或快照 schema 变化导致变异语义失效。
3. 语料变更（新增干净参考设计或结构类型）。
4. `applicable` 数量下降（说明语料或变异器开始与真实结构脱节）。

## ADR-003 评审门禁在 apply 前 fail-closed

- **状态**：accepted（2026-10-29）；门禁已入 main（#214，`tools/review_gate.py`）并接入一键流水线；hash 绑定/override 仍是剩余债务
- **决策域**：L2 规则 + L3 工具 + L6 复盘
- **关联**：设计文档 [layout-engine-v2.md](layout-engine-v2.md) §4；本文 ADR-001/002

### 背景

评审如果只产出报告，不阻止落点，本质上还是建议：流程可以带着 error 级问题直接 apply，把问题写进真实工程再靠人发现。布局引擎 v2 已有 R1–R7 几何 validator 做"写之前"门禁，但那只管几何，不管"上拉/去耦/地 tie/EN 默认态"这类电气与结构问题。落点写的是真实工程，错误的代价远高于多跑一步离线检查。

### 决策

1. **位置**：gate 位于 `plan → apply` 之间，是 apply 的前置条件，不是事后报告。
2. **输入**：ACE 快照（`easycirq-ace-snapshot/v1`）。gate 自己调 `tools/ace_review.py` 重新评审，
   不信任调用方自报的 verdict；也可独立当 CLI 用（`python tools/review_gate.py snapshot.json`）。
3. **fail-closed（strict 默认模式）**：
   - 任一 `error` 级 finding → `blocked=True`、`allowed=False`；**未知 severity 按 error 处理**（保守，
     未知不是放行理由）；
   - `--require-review` 且快照缺失/不可读 → 该项目 `review-blocked`（不产生 apply exec spec）；
   - 快照 JSON/结构非法 → 输入错误（exit 2），不是"通过"。
4. **输出** `easycirq-review-gate/v1`（实际字段）：`mode`（strict/advisory）、`strict`、`verdict`
   （pass/blocked）、`blocked`、`allowed`、`errors`、`warnings`、`findings`、`counts`、`rules`、
   `review_verdict`、`review_schema`；advisory 下若有 error 另带 `advisory_errors_allowed`。
   CLI 退出码：0 放行 / 1 阻塞 / 2 非法输入。
5. **两种模式**：strict 是默认与发布路径；advisory 只用于练习/推广，永不阻塞但必须记录
   `review_verdict` 与放行错误数——不能把 advisory 当验收依据。
6. **流水线接线**：`tools/run_layout_pipeline.py` 在离线规划后、写 apply exec spec **前**调用 gate；
   `--require-review` 缺快照即 fail-closed，`--review-advisory` 放行但记录；review-blocked 项目
   跳过（无 exec spec、不碰 EDA），批次继续；`pipeline-report.json` 增加 `review` 汇总，
   dashboard 增加 Review gate 段；退出码 0/1/2 语义不变。
7. **尚未实现（债务，不写成已支持）**：snapshot/plan 的 SHA-256 绑定与 `checked_at` 证据字段；
   未留痕 override 记录；真机 apply 路径（`tools/sch_layout_apply.py`、`tools/layout2/sch_layout_apply2.py`）
   尚未全部接入 gate。
8. **阻塞后的下一步是确定性修复计划**：被 gate 拒绝时，用 `tools/ace_fix_plan.py`
   （schema `easycirq-ace-fix-plan/v1`）把 findings 变成有序、可执行的修复动作
   （`actions[{id: fx-01…, rule, action}]`，同快照同计划）。它**不自动写入** EDA：
   执行仍由 Agent 按计划做并回读；因此 gate（判定）+ fix plan（整改）是同一条确定性链路上的两段，
   不能把 fix plan 的"有动作"当成"已修复"。

### 备选与不采用理由

| 备选 | 不采用理由 |
|---|---|
| 只写报告、不阻塞 | 等于没有门禁；真实工程可能带着 error 落点 |
| 把 ACE 规则塞进几何 validator | 职责混淆：R1–R7 是几何谓词，ACE 需要连通性/器件语义；混在一起无法单独回归 |
| 在 apply 里"顺手 warn" | apply 是真机慢路径，失败代价高；应在离线阶段拒绝 |
| 人工点确认后放行 | 不可批量、易疲劳漏检；只能作为 override 的例外，不能是默认路径 |

### 后果

- **正面**：error 级问题在写 EDA 前被拦住；gate 报告可机读、可审计；离线可重复执行；流水线里被阻塞的项目不会产生 exec spec。
- **代价/风险**：可能拦住"能画但电气不完整"的板，短期降低落点速度；gate 误报会阻塞流程，需要规则级别与 fixture 校准；advisory 模式可能被误用成"放行开关"。
- **缓解**：error 级规则必须有正/负 fixture；误报走"改规则 + 留 ADR"而不是临时 override；advisory 只用于练习/推广并在报告里保留 review_verdict。

### 复测触发

1. 新增 error 级规则或调整级别（尤其"未知 severity 按 error"的口径）。
2. apply 入口变化（新脚本/新路径未接入 gate，或真机 apply 路径开始接入）。
3. 出现"gate pass 但落点后仍有 error 级问题"（说明快照或规则有盲区）。
4. hash 绑定/证据字段接入后（当前债务）需重测审计链路。

## ADR-004 非矩形可打印区用矩形并集表达

- **状态**：accepted（2026-10-29）；矩形并集通用判定属本轮并行分支
- **决策域**：L1 资产 + L2 规则
- **关联**：设计文档 [layout-engine-v2.md](layout-engine-v2.md) §1/§3（R1/R2）；[layout-engine-adr.md](layout-engine-adr.md) ADR-001

### 背景

页面可打印区 = 内框 − 标题栏 keep-out。标题栏在右下角时（y-up 坐标系，低 y、高 x），可用区是 **L 形**，不是矩形。若用一个"大 bbox"近似，会把标题栏区域算成可用区，导致 zone 压标题栏；只用左条或只用上条又会浪费大半页面。而 EDA 的分区框（frame）本身只能画**矩形**，所以"非矩形可用区"只能由"矩形并集 + 每个 zone 完整落在并集内"来表达。

### 决策

1. 模板资产 `easycirq/assets/page-template.json` 的 `regions[]` 是**矩形并集**：由 page + `inner_border` + `title_block.rect` 计算得到（左条 + 右上条），并校验"互不重叠、不压标题栏、并集覆盖可用区"。
2. 可用区 `U = union(regions[i].rect)`；zone 仍是矩形，判定 `zone ⊆ U`，实现口径为：`Σ area(zone ∩ region_i) == area(zone)`（边界相切允许，正面积相交才计）。
3. **跨 region 的 zone 不允许**：允许"跨区"会让一个矩形 frame 同时压标题栏或跨越空白，回读难解释；需要更大区域时，应调整 region 分解或改模板，而不是放宽判定。
4. R1/R2 均以并集为准：R1 判 zone ⊆ U，R2 判 `area(zone ∩ title_block) == 0`；两条都要过。
5. region 分解允许人工覆盖，但覆盖结果必须过同一套校验；分解算法变化（如标题栏换角）要同步 fixture。
6. **已落地实现**（#212）：自由布局 `tools/layout2/freeform.py` 用 `subtract_rect` 从内框减去标题栏得到
   L 形/一般矩形补集，模块在 free-rect 列表上做确定性 first-fit（放置后把剩余拆成 right strip / top strip）；
   凹角处的 zone 跨 region 分割，输出 `rects[]` 并标 `zone_kind=rect|union`，规划 schema 为
   `easycirq-sch-layout-freeform/v1`（`verdict` pass/blocked，带 `title_block_hits`/`page_utilization`/`zone_fill` 指标）。

### 备选与不采用理由

| 备选 | 不采用理由 |
|---|---|
| 用单个大矩形近似可用区 | 标题栏区域被当可用区 → 框压标题栏；历史已出现同类现场 |
| 只用左条或只用上条 | 浪费页面，多页需求被放大 |
| 多边形 zone / 非矩形 frame | EDA frame 是矩形；非矩形将无法落点，也无法用同一谓词回读 |
| 跨 region 的矩形 zone（允许压标题栏旁边空白） | 判定与回读复杂，且容易重新压标题栏；收益小于风险 |

### 后果

- **正面**：R1/R2 有唯一几何口径；"框压标题栏"从"看图发现"变成"离线可判"；换标题栏位置只改资产。
- **代价/风险**：region 分解质量直接影响可用面积；矩形并集判定需要覆盖相切、跨区、完全在外三类 fixture。
- **缓解**：模板校验 + 三类边界 fixture；apply 前 gate 复用同一并集判定，避免离线/真机两套口径。

### 复测触发

1. 模板/标题栏位置、可见性、角点变化。
2. `regions[]` 分解算法或人工覆盖变化。
3. EDA 支持非矩形 frame（则需重新审视本决策）。
4. 出现"zone 在 union 边界相切被判相交/越界"的误报。

## ADR-005 块模板 role→(dx,dy) 消除落点漂移

- **状态**：accepted（2026-10-29）；已入 main（#215，`tools/layout2/role_resolver.py` + `tools/layout2/templates.py`）；真机落点验证仍 **NOT RUN**
- **决策域**：L1 资产 + L3 工具
- **关联**：设计文档 [layout-engine-v2.md](layout-engine-v2.md) §6.1；本文 ADR-006

### 背景

`block-apply --at` 是**锚点**语义：传入坐标不是器件 bbox 的左上角，实际 parts bbox 相对锚点有一个偏移。这个偏移按块不同（实测 11 个块：`easycirq-block-apply-offsets/v1` 的 `dx/dy`），在近边/标题栏附近还可能被 EDA 整体移位（矩阵实测中 `wroom`、`ams1117` 为 `variable_offset`，其余 9 块稳定）。如果 plan 用"目标 bbox"排布、apply 却按未校正的 `at` 落点，实际块与计划框错位，zone/标题栏/重叠指标全部失真；靠落点后 group-move 反复校正既慢，又把校正留在真机循环里。

### 决策

1. **角色绑定是数据问题，不是 LLM 问题**：`tools/layout2/role_resolver.py` 把 block manifest 的语义角色
   确定性绑定到快照里真实存在的器件：按 MPN（可选 `standard-parts.resolved.json`）出候选，再用
   `internal_nets` 拓扑剪枝，最后做确定性的 1-1 回溯分配；无候选/歧义/拓扑不一致 → 显式
   `RoleResolutionError`，不猜。
2. **块模板冻结相对几何**：`tools/layout2/templates.py` 的 `easycirq-block-template/v1` 记录一个块实例的
   相对布局——`origin{role,ref,x,y}`、`parts[{role,designator,dx,dy,rotation,bbox}]`（`dx/dy` 是相对
   origin 器件的 **bbox 中心偏移**，`bbox` 也相对 origin）、`pins[{role,pin,net}]`（保留 manifest 的
   `PIN`/`PORT:`/`*` 语义）与整体相对 `bbox`。
3. **实例化只做平移**：`instantiate_template(template, page, origin_xy)` 把同一份相对几何平移到新页原点，
   网络成员逐字复制，`zone_union` 取绝对 part bbox 的并集；输出顺序跟 manifest/自然位号，确定性。
4. **不再依赖锚点偏移试错**：相对几何来自实测模板，落点坐标 = 模板相对坐标 + 页原点；旧 `block-apply`
   的锚点偏移（`easycirq-block-apply-offsets/v1` 的 `dx/dy`、`variable_offset`、`pinned`）只保留给
   既有执行器的锚点校正，不再作为 plan 的几何来源。role 未收录/解析失败 → `blocked`，不允许默认 0。
5. **回读校验**：落点后实测 part bbox 与模板实例化结果的最大边差（drift）必须 ≤ 容差；超差判失败并留证，
   不回退成"再挪一次试试"。

### 备选与不采用理由

| 备选 | 不采用理由 |
|---|---|
| 让 LLM 猜"哪个件是 U、哪个是第二个 22uF" | 不可复现、不可审计；一个位号猜错，整个模板几何平移错位 |
| 落点后 group-move 校正 | 慢、真机循环、不可离线；校正量本身还需再回读 |
| 用 dry-run/经验常数估偏移 | 已证不可靠（dry-run 块估算会低估高度；偏移还随位置变） |
| 把偏移写死进代码 | 换块即错；无法按项目/EDA 版本更新 |
| 每个块单独手工调参 | 不可复用；新工程重复踩坑，正是"落点漂移"来源 |
| 所有块统一一个 dx,dy | 实测偏移不一致；统一值会把误差放大到 zone 判定 |

### 后果

- **正面**：角色绑定与相对几何都可离线复算、可审计；同一块模板跨工程复用时几何一致；drift 从"每次试"变成"模板平移 + 回读比对"。
- **代价/风险**：模板与 manifest/resolved-parts 必须同步；快照缺 `mpn`/拓扑信息时角色无法解析（显式失败）；EDA 钳制/移位行为变化会让落点偏移失效。
- **缓解**：role resolver 的错误信息带 role/候选；模板走 schema 校验；保留 `block-apply-offsets-matrix` 做锚点校正；drift 回读阈值；模板过期触发重测。

### 复测触发

1. 新增块/新封装/新角色，或 manifest 的 `parts`/`internal_nets` 变化。
2. `standard-parts.resolved.json` 或 MPN 映射变化（角色候选集变化）。
3. EDA 或 `block-apply` 版本升级（锚点语义、近边钳制、标题栏避让可能变化）。
4. 任一工程回读 drift 超容差，或 role resolver 出现新的歧义/无候选。

## ADR-006 save-after-apply 作为流水线不变量

- **状态**：accepted（2026-10-29）；流水线 save-after-apply 步骤**尚未实现（PENDING）**；真机验证 **NOT RUN**
- **决策域**：L3 工具 + L6 复盘
- **关联**：设计文档 [layout-engine-v2.md](layout-engine-v2.md) §4、§6.4；[failure-taxonomy.md](failure-taxonomy.md) FT-01

### 背景

已经出现过"命令返回 ok，但状态没生效"的现场：`sch clear` 返回成功、页面仍有残留器件（FT-01），如果继续落块就会叠加。布局落点同理：`block-apply`/`frame apply` 成功不等于文件已保存，保存也不等于重开后一致。把"命令返回 0"当验收，会在报告里留下一个未持久化、不可复现的"完成"。

### 决策

1. 流水线尾部固定为：**apply → save → `doc reload` → 回读 → 对比 → 记 verdict**；缺任一步不能写 `verified`。
2. 回读内容至少包括：parts 数量、关键块实测 bbox、net/连接计数、标题栏字段；与 plan/预期对比，drift 超容差即 `failed`。
3. 证据绑定：apply 报告记录 `plan_sha256`、快照/回读 hash、`doc reload` 结果、版本（EDA/连接器）与页 UUID；没有回读证据的 apply 只能记 `NOT RUN` 或 `failed`。
4. 失败语义：save/reload/回读任一步失败 → 停止、保留现场、不回退成"用同一个 plan 再 apply 一次"；要重试必须产生新 plan/新哈希并记录原因。
5. `doc reload` 后的回读与离线 plan 使用**同一组谓词**（R1–R5 可测部分），避免"离线和真机两套标准"。

### 备选与不采用理由

| 备选 | 不采用理由 |
|---|---|
| 只信 apply 的退出码 | 已有"ok 但没清空"的反例；退出码不证明持久化 |
| 只看导出图 | 图可能来自内存态；不能证明保存后重开一致 |
| 跳过 save，反正接着读 | 重开即丢；后续流程/他人接手会看到旧状态 |
| 失败后自动重试同一 plan | 掩盖真实差异，可能放大错误；违反"一次落点 + 留证"纪律 |

### 后果

- **正面**：把"命令成功"升级为"持久化且可回读验证"；失败可区分"环境/连接器问题"与"写入结果不一致"；证据链完整。
- **代价/风险**：每次 apply 多一次 save/reload/read 的时间与一次 EDA 读；reload 本身可能受连接器状态影响，需要把它的失败单独归类。
- **缓解**：把 reload 与回读做成固定步骤并计时；失败证据落盘；与 [failure-taxonomy.md](failure-taxonomy.md) 的 FT-01 类问题共用检测口径。

### 复测触发

1. EDA `save` / `doc reload` 命令语义或返回字段变化。
2. apply 流程新增写入步骤（未纳入 save-after-apply 即视为缺口）。
3. 出现"apply 报成功、重开后不一致"的事故。
4. 回读容差或比对谓词调整。

## 7. 失效与复测总表

| 触发 | 需要复测/复核的 ADR |
|---|---|
| 快照 schema / EDA 读回字段变化 | 001、002、003 |
| 规则新增或级别调整 | 001、002、003 |
| 模板/标题栏/角点变化 | 004 |
| 新块/新封装/EDA 升级 | 005、006 |
| apply 路径新增或保存语义变化 | 003、006 |
| 真实板出现"评审通过但落点后有问题" | 001、003、004 |

真机验收一律以回读证据为准；本文所有"已入 main"只代表离线代码/测试存在，不代表真机通过。
