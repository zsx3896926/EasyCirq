# 来源审阅：论文、仓库既有能力与“只做相对约束”的理由

本文件记录任务 L（PLACE-INTENT）在动工前对**论文**与**仓库既有实现**的只读审阅结论，
用于说明本任务的借鉴边界与证书边界。论文只做短引，**未复制正文/图表/数据**，也未把
论文结论写成我们的实测。审阅过程 0 次 EDA 调用、不联网。

## 1. 论文来源

- 题名：*ModuPlace: LLM-Assisted Modular PCB Placement via Preference-Optimized
  Constraint Graph Generation*
- 作者：Yaohui Han 等（CUHK / CUHK-Shenzhen / 中南大学 / Index）
- 会议：DAC '26；DOI [10.1145/3770743.3803892](https://doi.org/10.1145/3770743.3803892)；
  许可 CC-BY 4.0
- 本地只读参考：任务书 §1.1 给出的 PDF 路径；**未入仓、未重新分发**，本仓库不包含
  论文正文、图片或数据。

### 1.1 我们可以借鉴的（表示层）

1. **HMT 分层模块树**：按功能把元件递归划分为模块；叶子持有元件，内部节点只做分组。
   本任务把它落成 `modules[]`（`parent/children/components/confidence/size_mm`），
   但 `confidence` 只作为数据与报告字段，**不据此自动继续/停止划分**。
2. **CCG 综合约束图**：边携带“相对位置偏移 + 相对旋转 + 权重”，而不是直接生成坐标。
   本任务落成 `constraints[]`（`dx_mm/dy_mm/rotation_deg/weight/source`），并把它作为
   **输入契约**：工具只校验已给定的约束图，不生成它。
3. **“生成约束比生成坐标更安全/可检查”的表示论点**：这是论文的动机陈述，我们把它
   当作设计假设接受，并用确定性校验（多路径一致性、环恒等、重复/矛盾）来兑现
   “可检查”这三个字；**不把论文里的任何实验数字当作我们的结果**。

### 1.2 我们明确不借鉴/不实现的

| 论文能力 | 本任务处理 | 原因 |
|---|---|---|
| NHG 异构图 + 子电路匹配简化网表 | 不实现 | 本任务输入不含网表/连通性，只含模块树与相对约束 |
| 专家 CCG 数据集 | 不使用 | 无数据、无授权、不复制 |
| SFT + GRPO 两阶段训练、偏好排序 | **不实现** | 无权重/无算力/不可离线审计；任务书明确禁止 |
| LLM 生成约束图 | 不实现（由 Skill 侧上游完成） | 本任务是表示与校验器，不是生成模型 |
| 分层详细放置、模块面积约束下的最终摆放 | 只做“仅计划”的相对布局与 bbox 推导 | 最终放置属于 EDA 执行层，本任务不写工程 |
| 布线后 WL/过孔、ADS IL/XT 仿真评估 | 不做 | `real_eda:"NOT RUN"`、`eda_calls:0`；不声称任何布局/布线/EM 指标 |
| “低 HPWL 不一定可布通”等结论 | 只作为边界提醒引用 | 不是我们的实验结论，不能迁移成能力声明 |

**一句话**：我们只借“树 + 带相对位姿的边”这一数据结构，其余（数据、训练、生成、
详细放置、仿真评估）全部不借。

## 2. 仓库既有能力审阅（只读）

### 2.1 `design_engine` 的放置候选

- `pcb_workflow.py::plan_candidates` 用 `assets/pcb-placement-templates.json` 的角色/
  物理脚绑定，生成 `signal-chain` / `density` / `mechanical` 三种候选；先硬过滤
  （板内、重叠、固定/锁定、edge、keepout、spacing），再按近引脚失败、逃线阻塞、HPWL、
  模块面积比较，**不输出综合总分**。输出 `routing_verified:false`，候选是计划而非
  已放置；`no_feasible_candidate` 表示固定种子/预算内未找到，不是无解证明。
- 参考 `references/design-engine.md`、`references/offline-regression.md`、
  `references/pcb-execution.md`（本任务未修改这些文件）。

### 2.2 放置模板（`assets/pcb-placement-templates.json`）

- schema `design-engine-pcb-templates/v1`；模板保存**角色、真实引脚映射、相对位置**
  （`dx/dy` + `rotation`，单位 mil，`frame: core` 随核心旋转），不保存单板绝对坐标。
- 模板是 `E3` 级方法数据（`status: offline-validated` / `method-only`），**不是某块
  已画完并验证的板**；绑定要求角色绑定到实测 designator + 物理 pad 号，`net_roles`
  不一致直接 `rejected`。
- 与本任务的关系：模板的相对偏移可映射成 CCG 边（见 `integration-proposal.md`），
  但本任务**不建立运行期耦合**、不 import `design_engine`，只在自己的输入契约里
  表达同类信息。

### 2.3 模块计划（`assets/layout-modules/*.module-plan.json`）

- 以 `temperature-alarm.module-plan.json` 为例：`schemaVersion`、`zones[]`
  （`core` + `members` 按位号）、`defaultNetPolicies`、`readingOrder`；**没有绝对坐标**。
- `pcb_apply_plan.py --module-plan` 把多个模块计划合批（`merge_module_plans`），要求
  每份 `partial:true`、同一 `base_semantic_sha256`、designator 唯一、项目/文档一致，
  然后交给下游 `validate_placement`。它校验的是“批次一致性 + 硬几何合法”，
  **没有 HMT/CCG 自洽性概念**（例如：两份模块计划对同一模块组的相对意图是否矛盾）。

### 2.4 `routing_verified=false` 的既有口径

- `plan_candidates`、`pcb-escapes`、`pcb-template-plan` 等既有能力都明确标注
  `routing_verified:false`，HPWL/逃线只是代理；本任务**沿用同一口径**，并进一步固定
  `placement_applied:false`、`physical_validation:"NOT RUN"`、`real_eda:"NOT RUN"`、
  `eda_calls:0`。
- 本任务不读取任何 EDA 回读、不写工程、不修改 `design_engine`/`pcb_apply_plan`。

### 2.5 为什么本任务只用相对约束（不引入绝对坐标）

1. 仓库既有模板与 module-plan 已经是**相对**表示；本任务若引入绝对坐标，会与既有
   数据模型冲突，也会把“意图”绑死到某块板的当前几何。
2. 本任务输入要能由 LLM/人**离线**给出，并在没有 EDA session 的环境下校验；
   相对约束满足这一点，绝对坐标则依赖真实回读。
3. 绝对坐标会诱导“已放置”的误读；相对输出 + 显式 `placement_applied:false` 更安全。
4. 相对约束可以在不求解的情况下做多路径/环一致性校验；绝对坐标没有可比的独立证据。

## 3. 证书与边界声明

### 3.1 本任务能证明的

- 给定输入的 JSON 结构合法（严格解析、必填/类型/枚举/额外字段/取值域）；
- HMT 是单根、无环、父子一致、深度受限、元件唯一归属的树；
- CCG 边合法（端点存在、无自环、有限数值、权重 >0、旋转在允许域内），且
  在声明容差内路径一致、环恒等、重复边可去重、矛盾边被拒绝；
- 尺寸/板框/约束自足时，可确定性推导模块相对帧与轴对齐 bbox，并在同样自足时
  检查兄弟重叠与固定冲突；
- 同一输入重复运行输出字节一致；输入未被修改；非法运行不残留旧 PASS。

### 3.2 本任务不能证明、也不声称的

- 任何 EDA 工程被读取/修改/保存/重开（`real_eda:"NOT RUN"`，`eda_calls:0`）；
- 布局已应用（`placement_applied:false`）、布线可通（`routing_verified:false`）、
  DRC/连通性/SI/PI/EM/热通过、可制造/可装配/可上电；
- HPWL/密度/无重叠等价于“可布通”或“电磁性能好”；
- 论文的任何实验结论（包括“模块化 + 偏好对齐改善布线后指标/EM”）适用于本仓库；
- 上游 LLM 生成的 CCG 是“正确”的——本任务只证明它**自洽**。

### 3.3 真实 vs 合成

- 仓库内 benchmark 场景以**合成夹具**（`synthetic_fixture`）为主，引用真实仓库数据
  派生的场景标 `derived` 并记录源 SHA-256；它们都不是真实板验收。
- 本任务未使用真实 EDA 回读、未使用真实板、未做任何实物验证。

## 4. 参考资料清单（只读）

| 文件 | 用途 |
|---|---|
| `placement-intent-task-book.md` | 任务书：目标/非目标/契约/验收/里程碑 |
| `docs/parallel-placement-intent/contract.md` | 权威输入/输出契约（Lead 维护） |
| `easycirq/references/design-engine.md` | `plan_candidates`/模板/候选的既有口径 |
| `easycirq/references/pcb-execution.md` | 模板库、候选选择、preflight 门禁 |
| `easycirq/references/offline-regression.md` | `routing_verified=false` 与代理指标口径 |
| `easycirq/assets/pcb-placement-templates.json` | 相对偏移/旋转/角色绑定的既有表示 |
| `easycirq/assets/layout-modules/temperature-alarm.module-plan.json` | 模块计划只含成员、无绝对坐标 |
| `easycirq/scripts/design_engine/pcb_workflow.py` | `plan_candidates` 只读理解（未修改） |
| `docs/easycirq-mcp/` | 已合并的 MCP 工具层口径（本任务不改） |
| `docs/parallel-electrical-review/` | 既有并行任务的文档风格与验收口径样例 |
