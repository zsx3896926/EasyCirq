# 设计：可校验的放置意图（HMT + CCG）离线 PoC

本文件说明任务 L（PLACE-INTENT）为什么采用“分层模块树 + 相对约束图”的放置意图表示，
它和 ModuPlace 的对应关系与刻意不做的部分，以及 SE(2) 合成、一致性校验、包络推导、
重叠检查、固定冲突、单位换算的算法与复杂度。字段级规范以 `contract.md` 为准；本文件
不新增字段、状态或退出码。

## 1. 目标与边界

本模块读取一个 JSON 输入，离线校验“HMT（分层模块树）+ CCG（相对约束图）”是否自洽，
并在几何信息自足时导出**仅计划**的分层相对布局。它不写工程、不调用 EDA/daemon/
connector、不联网、不训练/推理任何模型。

**证明的**：给定的放置意图表示是结构合法的、约束在声明容差内一致的、可确定性重放
（同一输入两次运行字节一致）的；尺寸/板框/约束完整时，可导出模块相对帧与轴对齐包络。

**不证明的**：布局已应用（`placement_applied:false`）、布线可通
（`routing_verified:false`）、DRC/连通性/SI/PI/EM/热通过、可制造或可上电。所有这些
在输出中固定为 `physical_validation:"NOT RUN"`、`real_eda:"NOT RUN"`、`eda_calls:0`。

## 2. 为什么是“可校验的放置意图”，而不是绝对坐标或训练模型

### 2.1 绝对坐标的问题

1. **不可校验**：LLM 或人给出 `(x, y, θ)` 后，任意浮点数看起来都“精确”，但工具没有
   证据判断它是否合理；绝对坐标只绑定某一版工程/板框，无法跨快照复用。
2. **过早承诺**：绝对坐标把“意图”和“某块板的当前几何”绑死，输入快照一变就全部失效；
   而设计意图（谁应该在谁左侧 3 mm、相对旋转 90°）才是可交接、可复核的部分。
3. **鼓励假通过**：一旦输出绝对坐标，很容易被误读为“已放置”。本任务刻意让输出停在
   模块相对帧与可选 bbox，并显式标注 `placement_applied:false`。
4. **不可证明部分必须保持 unknown**：绝对坐标无法区分“算出来的”和“猜出来的”；
   相对约束的未知是离散的（缺边、缺尺寸、缺板框），可以逐项报告、逐项补。

### 2.2 相对约束（CCG）的可校验性

- CCG 边是 `(from, to, dx, dy, θ, w)`；在给定根节点 `(0,0,0)` 后，沿路径的 SE(2) 合成
  是纯确定性计算，**不需要求解器、不需要优化、不需要搜索**。
- 同一对节点若存在多条路径，合成结果必须一致 → 直接暴露“约束自相矛盾”；
  环的合成必须是恒等 → 直接暴露“绕一圈回不到原处”。
- 约束数量、旋转域、权重、单位都可以在结构层校验；缺信息时产生显式 `unknown`，
  绝不补默认值。
- 表示对**整体平移**不变（约束只含相对量），对数组顺序不敏感，适合在不同快照、
  不同单位（mm/mil）之间重放。

### 2.3 为什么不做训练

- 论文的训练部分需要专家 CCG 数据与多卡算力，仓库与任务都没有这个前提；
- 我们的执行层是 EDA 工具链 + 计划/回读，不是端到端学习系统；训练模型会带来
  不可复现、不可审计、无法离线验证的结果；
- 生成 CCG 的“智能”属于 Skill/LLM 侧，本任务只提供**确定性、离线、可审查的表示与
  校验器**，供上游生成、下游集成使用。

## 3. 与 ModuPlace 的对应关系（只借鉴表示，不借鉴训练）

论文：*ModuPlace: LLM-Assisted Modular PCB Placement via Preference-Optimized
Constraint Graph Generation*，Yaohui Han 等，DAC '26，DOI
[10.1145/3770743.3803892](https://doi.org/10.1145/3770743.3803892)（CC-BY 4.0）。
本仓库只做短引，不复制正文/图表/数据，也不把论文结论写成我们的实测。

| 论文概念 | 本任务对应 | 借鉴程度 |
|---|---|---|
| HMT（分层模块树） | `modules[]`：`parent/children/components/confidence/size_mm` | **借鉴表示**：树形功能划分、叶子持元件、可选置信度 |
| CCG（综合约束图） | `constraints[]`：`from/to/dx_mm/dy_mm/rotation_deg/weight/source` | **借鉴表示**：边携带相对偏移 + 相对旋转 + 权重 + 来源 |
| 分层放置（模块面积约束子模块） | `plan` 的层级相对帧 + 自底向上 bbox 推导 + `module_size_exceeded` | **借鉴思路**：只在模块相对帧内推导，不产生板坐标 |
| NHG 异构图 + 子电路匹配 | 无 | **不做**：无网表输入，不引入图学习/匹配 |
| 专家 CCG 数据 + SFT/GRPO + 偏好排序 | 无 | **不做**：无数据、无权重、无训练 |
| LLM 生成约束图 | 无（由 Skill 侧上游完成） | **不做**：本任务只校验已给定的约束图 |
| 详细放置、布线后 WL/过孔、ADS IL/XT 仿真 | 无 | **不做**：`real_eda:"NOT RUN"`；不声称任何布局/布线/EM 指标 |
| “低 HPWL 不一定可布通”的结论 | 写进边界声明 | **只作为边界提醒**，不是我们的实验结论 |

**关键区别**：论文用训练模型**生成**约束图并做分层详细放置；我们把“约束图”当作
**输入契约**，只做确定性校验与相对计划。因此本任务不宣称任何放置质量改进，也不
复用论文的数据/权重/评估口径。

## 4. 架构与文件职责

```text
design-hardware/scripts/placement_intent/
  __init__.py   工具名/版本/schema 常量、固定 NOT RUN 与 limits 文案、rotations/anchors 常量
  __main__.py   python -m placement_intent 的入口
  cli.py        validate / plan / explain 参数解析、退出码、--out 原子写、stdout 纪律
  io.py         严格 JSON（重复键/NaN/Infinity 拒绝，utf-8-sig）、SHA-256、稳定+原子写
  contract.py   输入结构/类型/枚举/必填/额外字段/取值范围校验、树校验、规范化输入
  findings.py   finding/unknown 统一形状、severity→status、稳定排序、unknown id 去冲突
  geometry.py   SE(2) 刚体变换（90° 倍数精确旋转）、旋转矩形 AABB、交叠面积、包含判断
  ccg.py        图构建、旋转域、重复/矛盾去重、BFS 生成树合成、多路径一致、环恒等
  plan.py       分层相对计划、自底向上 bbox、兄弟重叠、固定冲突、状态与计数、explain 支撑
  explain.py    只读重放：约束/模块/总览解释
```

职责边界：

- `io.py` 与 `contract.py` 只负责“输入是否可解释”，不产生几何；
- `ccg.py` 只产生**相对帧**（每节点相对根/分量的位姿）与一致性 finding，不做布局优化；
- `geometry.py` 只做纯几何原语，尺寸未知时由 `plan.py` 保持 `null` + `size_unknown`；
- `plan.py` 汇总状态：`invalid_input > incomplete > review_required >
  planned_constraints_only > planned_with_scope`（严格按 `contract.md` §7.1）；
- CLI 层保证：stdout 只有一个 JSON、诊断走 stderr、`--out` 原子写、输入只读、
  同一输入重复运行字节一致。

## 5. 算法

### 5.1 SE(2) 路径合成（`contract.md` §4.4）

根节点 `p_root=(0,0)`、`r_root=0`。沿边 `from → to`：

```text
p_to = p_from + R(r_from) · (dx, dy)
r_to = (r_from + rotation_deg) mod 360
R(a) = [[cos a, -sin a], [sin a, cos a]]
```

反向沿同一条边 `to → from`：

```text
r_from = (r_to - rotation_deg) mod 360
p_from = p_to - R(r_from) · (dx, dy)
```

对每个 CCG 连通分量，选分量中 **id 字典序最小**的节点为过程锚点，用 BFS/生成树给
分量内所有节点赋相对位姿；含根的分量即得到根相对位姿（根固定 `(0,0,0)`）。与根不在
同一分量的节点位置/旋转保持 `known:false` 并产生 `no_constraint` unknown；节点与根
连通、但其树父不在根分量时，父相对帧不可知，产生 `frame_unknown` unknown。

**为什么用 BFS 生成树而不是解线性方程组**：边是 SE(2) 的相对变换，生成树足以给每个
节点一个候选位姿；所有非树边都变成一致性约束（多路径），无需最小二乘——不一致就是
输入矛盾，而不是待拟合噪声。这与“CCG 是意图、不是测量”的定位一致。

### 5.2 多路径一致性

对任意两节点，若存在多条路径，合成位姿必须一致：

- 平移差 `<= policy.position_tolerance_mm`（默认 `1e-6` mm，换算后的 mm）；
- 旋转差 `mod 360` 在固定 `1e-6` 度内为 0（容差不可配置）。

实现上把每个非树边的目标位姿与生成树位姿比较；不一致 → `constraint_path_mismatch`
（`invalid_input`）。**不择一、不取平均、不做最小二乘**。

### 5.3 环恒等

沿环一周的合成必须是恒等变换：平移长度 `<= position_tolerance_mm` 且旋转 `mod 360`
在 `1e-6` 度内为 0 → info `constraint_cycle_identity`；否则
`constraint_cycle_nonidentity` → `invalid_input`。闭合且恒等的环是合法且常见的
（例如同一模块组的两条互相印证路径），非恒等环说明约束自相矛盾。

### 5.4 重复与矛盾

同一 `(from, to)`：

- `dx/dy`（按 `position_tolerance_mm`）、`rotation_deg`（按 `1e-6` 度）、`weight`
  （按 `weight_epsilon`，默认 `1e-9`）全部相同 → 去重，保留输入顺序第一条，其余 id
  进 `aliases`，记 info `constraint_duplicate_deduped`；
- 任一字段不同 → `constraint_duplicate_conflict`（`invalid_input`）。

反向边 `(to, from)` 不是重复边：它是另一个方向的约束，参与多路径一致性校验。
自环 `from == to` → `constraint_self_loop`；端点不存在 → `constraint_endpoint_unknown`。

### 5.5 轴对齐包围盒（bbox）近似

`plan` 的 `bbox_mm` 是节点在**自身未旋转局部帧**中的轴对齐包络（可含负 x/y），
`bbox_approx:"axis_aligned_rotated_rects"`，不是板坐标：

1. 元件：`size_mm` 已知 → 局部矩形 `(0,0,w,h)`；缺失 → `null` + `size_unknown`。
   元件 bbox 固定为 `{"x":0,"y":0,"w":w,"h":h}`（元件是原子节点，不再分解）。
2. 模块：对每个子项（树子模块 + 自身 `components`），若与模块同属一个 CCG 连通分量，
   取子项矩形（锚点偏移后），绕其原点旋转 `θ`（子项相对模块的累积旋转），再平移
   子项相对帧偏移，得到 4 个角点的 AABB，并入父模块 bbox。
3. 任一处缺尺寸/缺帧（不同分量、bbox 为 `null`）→ 本模块 `bbox=null` +
   `size_unknown`，其所有祖先同样为 `null`（unknown 逐级传播，不填补）。
4. 无子项但声明了 `size_mm` 的叶子 → `(0,0,w,h)`；两者都没有 → `null`。
5. 模块声明了 `size_mm` 且推导 bbox 超出 `[0,w]×[0,h]`（超出量
   `> position_tolerance_mm`）→ finding `module_size_exceeded`（review）。

**为什么叫近似**：旋转矩形的真实包络是旋转后的精确凸多边形；我们只保留其轴对齐
外接矩形（AABB），因此面积/重叠判断比真实几何保守。它足以做“明显重叠/明显超出”
的风险提示，但**不是** DRC、不是精确几何证明。

锚点语义（`--anchor`）：**v1 只支持 `top-left`**（默认，也是唯一支持值）。帧原点 =
节点的左上锚点；`top-right`/`bottom-left`/`bottom-right`/`center` 对 `plan`/`explain`
一律 exit 4（用法错误），不会静默按 `top-left` 处理；`validate` 不做几何，接受并忽略
`--anchor`。模块的帧原点由约束链决定，**不等于**其推导包络的左上角：包络可以落在
原点的负方向（`bbox_mm` 的 x/y 可为负），工具**不做**“把 bbox 平移到 (0,0)”的归一化
（`contract.md` §4.1）。多锚点是 v1 明确的能力缺口，见 `issue-candidates.md`。

### 5.6 兄弟重叠

对每个模块，若其全部直接子项的 bbox 与相对帧都可算，则把子项 AABB 变换到该模块帧，
两两求交；交叠面积 `> position_tolerance_mm²` → finding `sibling_overlap`
（`details` 给 `{a, b, dx_mm, dy_mm}`），`plan` 状态降为 `review_required`。

**重叠是 review，不是 invalid，更不是 pass**：CCG 是意图表示，兄弟包络重叠可能是
“尺寸声明偏保守/锚点选择不同/意图本身需要人工确认”，工具必须报告而不是替人决定。
不可算时不做该父模块的检查，产生 `impact:none` 的 `overlap_not_checked` unknown
（不改变状态），并在 `not_checked` 保持固定的未覆盖项清单。

### 5.7 固定节点冲突

`fixed:true` 节点表示不可移动，只用于冲突报告，不参与求解。声明位置来源：
`board.fixed_positions_mm` 与 `components[].position_mm`（模块只能用前者）。

1. **旋转冲突**：固定节点已声明 `rotation_deg`，且其 CCG 合成旋转（相对根）与声明值
   在 `1e-6` 度内不一致 → `fixed_conflict`（review）。
2. **相对距离冲突**：两个固定节点 A、B 都声明了位置、又能在同一 CCG 连通分量内算出
   相对位移；若 `|declared_B - declared_A|` 与合成距离之差超过
   `position_tolerance_mm` → `fixed_conflict`（review）。
3. 固定节点有声明位置但没有约束边 → 无可证明的移动要求，不产生冲突。
4. 固定节点出现在约束中但未声明位置 → warning `fixed_position_unknown`，不改变状态。

**只用相对信息**：比较的是“声明的相对位移”与“合成的相对位移”，不是绝对板坐标；
这保证输出不引入板坐标，同时仍能发现“约束要求移动一个固定件”。

### 5.8 单位换算

输入所有“长度字段”（字段名带 `_mm` 后缀只是标记）按 `units.length` 读入：
`"mm"` → scale 1.0；`"mil"` → scale 0.0254（`1 mil = 0.0254 mm`）。只在读入时换算
一次；报告写 `units.input_length`、`units.normalized_length="mm"`、
`units.scale_to_mm`。未声明单位或单位不在白名单 → 非法（**不按 mm 猜**）。
等价 mil/mm 输入在 `position_tolerance_mm` 内得到同一规范化结果。

### 5.9 确定性

- 输出无时间戳/随机/环境依赖字段（除输入 `path` 原样回显）；
- `levels` 按 depth 升序、层内按 id 字典序；`normalized_constraints` 按
  `(from, to, id)`；`findings/unknowns` 稳定排序（severity/code/subject/path）；
- `unknown.id` 稳定可复现：`unk:<code>:<subject or "global">`，冲突时追加 `:2`、`:3`…；
- 输入数组任意重排不改变实质结果；整体平移不改变相对结果。

## 6. 状态机

```text
validate:  valid(exit 0) / invalid_input(exit 2) / 用法·IO(exit 4)

plan:      invalid_input(2) > incomplete(3) > review_required(1)
           > planned_constraints_only(1) > planned_with_scope(0)
```

- `planned_with_scope`：输入合法、约束一致、所有节点帧已知、所有 bbox 可推导、
  板框已知。**仍是计划**。
- `planned_constraints_only`：约束一致但信息不足；`levels` 与
  `normalized_constraints` 仍输出，不可推导处一律 `null`。
- `review_required`：固定冲突、兄弟重叠、模块包络超出声明尺寸、来源不足等可解释风险。
- `incomplete`：无模块/无元件、快照绑定关键字段缺失等。
- 任何 `unknown`/`review_required`/`incomplete` 都不会被提升为 `planned_with_scope`。

## 7. 复杂度

设 `V` = 节点数（模块 + 元件），`E` = CCG 边数，`deg(m)` = 模块 `m` 的直接子项数。

| 步骤 | 复杂度 | 说明 |
|---|---|---|
| 严格 JSON 解析 | O(bytes) | 单次扫描；重复键/NaN 在解析期拒绝 |
| 结构/树校验 | O(V) | 父引用表、DFS、深度、元件归属各一次 |
| 单位换算 | O(V+E) | 只做乘法 |
| CCG 图构建 + BFS 合成 | O(V+E) | 每个连通分量一次生成树；每边常数次三角运算 |
| 多路径一致性 | O(E) | 每条非树边一次比较 |
| 重复/矛盾去重 | O(E)（哈希表） | 同一 `(from,to)` 分组 |
| bbox 自底向上 | O(V) | 每子项 4 角点 × 一次旋转；每节点汇总一次 |
| 兄弟重叠 | O(Σ_m deg(m)²) | 每个父模块内两两求交；最坏 O(V²)（星形树） |
| 固定冲突 | O(F²)，F = 有声明位置的固定节点数 | 同一分量内两两比较，最坏 O(V²) |
| 确定性排序 | O(E log E + V log V) | 排序主导 |
| 内存 | O(V+E) | 邻接表 + 每节点位姿/bbox |

对常见的“浅层模块树 + 稀疏 CCG”（几十到几百节点），实际是线性量级；本任务不做
速度/提效声明，benchmark 的 timing 只记录 CLI 执行成本。

## 8. 已知限制

- **不求解绝对坐标、不应用放置**：输出只有相对帧与可选 AABB；`placement_applied:false`。
- **bbox 是轴对齐外接矩形**：旋转矩形的真实包络更大/更小都可能被 AABB 放大；重叠与
  超出判断是保守提示，不是几何证明。
- **不做布线/连通性/DRC/仿真/制造**：`routing_verified:false`、`real_eda:"NOT RUN"`、
  `eda_calls:0`；不评估 HPWL/密度/EM/热。
- **不训练/不推理模型**：不生成 CCG；上游（LLM/人）给出约束图，本模块只校验。
- **尺寸未知即 unknown**：不用封装名猜尺寸、不用默认旋转/默认位置补齐。
- **固定冲突只用相对信息**：没有声明位置或没有约束边时不能证明冲突，只记 warning。
- **跨模块边按路径累积旋转**：分量内锚点选择（字典序最小）虽确定，但不同锚点选择
  不会改变“是否一致”的结论（一致性是平移/旋转不变的）。
- **v1 不实现多锚点**：`--anchor` 只支持 `top-left`；`top-right`/`bottom-left`/
  `bottom-right`/`center` 在 `plan`/`explain` 上 exit 4，扩展需先定义模块包络与帧原点的
  锚点语义（见 `issue-candidates.md`）。
- **Python 3.10 语义靠 CI**：本机只有 3.13，3.10 通过仓库 CI 矩阵验证（见 `report.md`）。
