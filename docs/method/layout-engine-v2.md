# 布局引擎 v2：离线优先 + 硬规则（设计）

> 状态：设计定稿（docs-only）。实现由 `tools/layout2/` 的并行分支完成；本文不声称任何模块已实现、已跑通或已验收。
> 契约：`layout-engine-v2-contract.md`（`hds-verifier` 检出的 `feat/layout-engine-contract` 分支；schema、模块清单与硬规则以它为准，本文负责解释设计与集成口径）。
> 决策记录：[layout-engine-adr.md](layout-engine-adr.md)。方法背景：[schematic-layout-thinking.md](schematic-layout-thinking.md)、[failure-taxonomy.md](failure-taxonomy.md)、[sedimentation-protocol.md](sedimentation-protocol.md)。
> 几何口径：坐标单位 raw（0.01 inch）；A4 横向页面 1170×825，边距 12；画布 **y 向上**，原点在左下角，标题栏位于右下角（低 y、高 x）。

## 0. 一句话

**先量（模板 / 器件 / 文字）→ 再分页 → 再落位 → 再放标签 → 硬规则全过 → 才允许真机一次落点。** 任何一条硬规则不过，整份 page plan 返回 `blocked`，不打开 EDA。

相对 v1 的三个结构性变化：

1. **模板是实测数据。** 页面尺寸、边距、标题栏 keep-out 全部来自 `sch sheet-geometry`，不再把 A4、1170×825、右下角或 `610..1170 × 12..380` 写死在求解器里。
2. **分页先于落位。** 页数由规划决定；模块是布局原子，不跨页、不因“排不下”在求解阶段偷偷加页。
3. **文字碰撞离线解决。** 用字号度量 + 标签求解在落点前算清文字 bbox；不再依赖导出图肉眼发现标题压网络标签（对应 `failure-taxonomy.md` 的 FG-03）。

范围：只重排“标准模块 + 固定模板”的原理图版式，不改电气拓扑、不换器件、不删网络。PCB 与制造不在本文范围。

## 1. 架构与流水线

```text
easycirq/assets/page-template.json ──┐
easycirq/assets/device-metrics.json ─┼──> layout_engine.py（只编排，不算几何）
easycirq/assets/text-metrics.json ───┘             │
模块清单（id/title/members/亲和组/流向）───────────┤
                                                   ▼
                                        pagination.py        页数与每页模块分配
                                                   ▼
                                        zone_solver.py       region → frames + block bbox + zone
                                                   ▼
                                        label_solver.py      端口/网络标签/文字落点
                                                   ▼
                                        hard_rules.py        R1–R7 → findings + verdict
                                                   ▼
                             easycirq-sch-layout-v2/v1 page plans（含 validator）
                                                   ▼
                    sch_layout_apply2.py   唯一 EDA 触点：命令/playbook，一次执行
                                                   ▼
                             回读验收：实测 bbox / 文字 / 标题栏 / 导出图
```

各阶段的输入、输出与失败策略：

| # | 阶段 | 输入 | 模块（`tools/layout2/`） | 输出 | 位置 | 失败策略 |
|---|---|---|---|---|---|---|
| 1 | 模板加载 | `page-template.json` | `page_template.py` | 页面、边距、标题栏矩形、`regions` | 离线 | schema/缺字段 → `blocked` |
| 2 | 度量 | 模板、器件表、字号表、模块清单 | `device_metrics.py`、`text_metrics.py` | 模块实测 bbox + halo、文字 bbox | 离线 | 器件/字号未收录 → `blocked`（不估算） |
| 3 | 分页 | 模块清单 + 亲和组 + 模板 | `pagination.py` | 页数 N、每页模块分配、页间阅读顺序 | 离线 | 达到页数上限仍放不下 → `blocked`（见 Q7） |
| 4 | 分区 | 单页模块 + `regions` | `zone_solver.py` | `frames`、`blocks[].bbox`、`blocks[].zone` | 离线 | 硬约束无解 → `blocked`（只允许离线换候选，不落真机） |
| 5 | 标签 | 单页分区 + 引脚/网络信息 | `label_solver.py` | `labels[]`（text/bbox/anchor） | 离线 | 文字无解或压框 → `blocked` |
| 6 | 门禁 | 整份 page plan | `hard_rules.py` | `{verdict, findings[]}` | 离线 | 任一 violation → `blocked` |
| 7 | 落点 | validator=pass 的 page plan | `sch_layout_apply2.py` | `easycirq` 命令 / playbook | 真机（唯一） | verdict≠pass、plan 哈希不符、页面身份不符 → 拒绝执行 |
| 8 | 回读验收 | 落点后的实际页面 | `sch_layout_apply2.py` | 实测 bbox/文字/标题栏 + 导出图 | 真机 | 与 plan 漂移 → 停止并留证，不做盲目重试 |

编排约束：

- `layout_engine.py` 只做加载、调用、组装；不实现几何算法，也不读写 EDA。
- 每个离线阶段都是纯函数式：相同输入（含资产版本）→ 相同 page plan；不允许随机种子、当前时间或页面 UUID 影响坐标。
- 阶段失败必须带**定位信息**（页码、模块 id、规则号、矩形），不要只抛一句 `failed`。

## 2. 数据流

### 2.1 输入

| 输入 | 来源 | 必需内容 | 备注 |
|---|---|---|---|
| 模块清单 | 电气设计（netlist / 模块计划） | `id`、`title`、成员位号、亲和组（同电源域/同接口）、阅读顺序 | 模块是原子；成员必须恰好覆盖一次 |
| `page-template.json` | `easycirq sch sheet-geometry` | 页面宽高、边距、标题栏矩形、provenance、regions | schema `easycirq-page-template/v1` |
| `device-metrics.json` | 真机单执行器测量 | 每个标准器件的符号尺寸、引脚数、位号/参数尺寸、四向 halo | schema `easycirq-device-metrics/v1` |
| `text-metrics.json` | 真机单执行器测量 | 7/8/9/10/12/14/20 号字的行高、CJK/Latin/空格宽、上下留白 | schema `easycirq-text-metrics/v1` |

三份资产是**唯一数据源**：代码、测试 fixture、benchmark 不得各自复制一份数字。资产缺失、schema 不符或版本过期 → `blocked`，不允许“先用默认值跑跑看”。

### 2.2 中间产物与最终产物

```text
模块清单 + 三份资产
  → [分页]   {page_count, pages:[{page, modules:[...]}]}
  → [分区]   {frames:[...], blocks:[{id, bbox, zone}]}
  → [标签]   {labels:[{text, bbox, anchor}]}
  → [门禁]   {validator:{verdict, findings}}
  → page plans（easycirq-sch-layout-v2/v1）
  → [apply]  easycirq 命令/playbook + 回读报告
```

最终产物 schema（与契约一致，字段不增不减）：

```json
{"schema":"easycirq-sch-layout-v2/v1","pages":[
  {"page": 1, "frames": [],
   "blocks": [{"id":"...","bbox":[0,0,0,0],"zone":[0,0,0,0]}],
   "labels": [{"text":"...","bbox":[0,0,0,0],"anchor":[0,0]}],
   "validator": {"verdict":"pass","findings":[]}}
]}
```

数据流纪律：

1. **单一来源。** 页面/器件/字号只从 L1 资产读；资产是“尺子”，尺子过期则所有下游结果不可信。
2. **失败关闭。** 任一阶段缺数据、越界或未收录，返回 `blocked` 并保留中间结果用于诊断；`blocked` 的 plan 可以落盘，但 apply 必须拒绝。
3. **验证后冻结。** `verdict=pass` 的 plan 计算 SHA-256；apply 只接受哈希匹配的 plan，防止“验证的是 A、执行的是 B”。
4. **证据可回放。** 每次 apply 记录 plan 哈希、资产版本、EDA/连接器版本、页面 UUID、窗口 id、命令清单与回读结果。

## 3. 硬规则（Hard rules）

以下 7 条对**任意一张图**都必须成立；违反任一条，validator 返回 `blocked`，不得进入 EDA。

| 编号 | 规则 | 判定式（离线） | 主要检测 | 违反后果 |
|---|---|---|---|---|
| R1 | 所有模块 `zone` 完全落在可用页面区域内（页面减边距、减标题栏 keep-out） | 对每个 `zone`：`zone ⊆ usable_regions` 的并集 | `page_template.usable_regions()` + 矩形包含 | `blocked` |
| R2 | `zone` 与标题栏 keep-out 矩形不相交 | `area(zone ∩ title_block) == 0` | `page_template.title_block_hit(rect)` | `blocked` |
| R3 | 每个模块的实测 bbox + 附件晕圈 halo 完全落在其 `zone` 内 | `bbox ⊕ halo ⊆ zone`（按边分别外扩） | `device_metrics.with_halo(bbox)` | `blocked` |
| R4 | 任意两个模块 bbox 不相交；相邻模块间距 ≥ `min_gap` | 两两 `area(bbox_i ∩ bbox_j) == 0` 且 `gap(i,j) ≥ min_gap` | 矩形求交 + Chebyshev 间隔 | `blocked` |
| R5 | 任意两个文字 bbox 不相交（含标题、网络标签、位号、参数）；文字不得压模块框线 | 两两 `area(text_i ∩ text_j) == 0`；`text ∩ frame_stroke == ∅` | `text_metrics.collisions()` + 框线净空 | `blocked` |
| R6 | 页数 = 规划结果；每页恰好一份标题栏；跨页信号用同名网络标签/端口表达 | `len(pages) == planned_page_count`；每页 `title_block_count == 1`；跨页网名可解析 | plan 结构检查 + 模板 | `blocked` |
| R7 | 同一模块不得跨页拆分（模块是布局原子） | 每个模块 id 只出现在一页 | plan 结构检查 | `blocked` |

判定细则：

- **“不相交”**：矩形交集面积为 0 即通过；边界接触不算相交。R4 的间距仍需 ≥ `min_gap`，不能靠“贴边”规避。
- **`gap(i,j)`**：两个不相交 bbox 在 x、y 方向的间隔取较大者（Chebyshev 间隔）；斜向相邻也按同一口径计。
- **R5 的“文字”**：分区标题、网络标签、位号、参数/值、注释；框线按实际描边宽度外扩后参与求交，避免“bbox 没压线、笔画压线”。
- **R6 的“一份标题栏”**：以模板的标题栏矩形为准；隐藏标题栏的模板必须在资产里显式声明 provenance，否则 `blocked`。
- **R7 的“模块”**：以模块清单的 id 为原子；一个模块的成员位号不得被拆到两页，也不得因页数变化被拆开。

verdict 语义：

| 状态 | 含义 | 后续动作 |
|---|---|---|
| `pass` | R1–R7 全部成立，findings 为空 | 允许生成 apply playbook |
| `blocked` | 存在至少一条 violation | 不生成 EDA 命令；保留 findings 供修复或换候选 |

真机落点后，apply 模块必须用同一组谓词对**回读结果**再跑一遍（R1–R5 的可测部分）；回读与 plan 的差异超过容差即判失败。离线 `pass` 只证明“计划自洽”，不等于真机验收通过。

## 4. 离线 / EDA 边界

| 能力 | 离线 | 真机（EDA） |
|---|---|---|
| 模板读取与校验 | ✅ `page_template.py` | ❌ |
| 器件/文字度量计算 | ✅ `device_metrics.py`、`text_metrics.py` | ❌ |
| 分页、分区、标签求解 | ✅ `pagination.py`、`zone_solver.py`、`label_solver.py` | ❌ |
| 硬规则验证、评分、benchmark | ✅ `hard_rules.py`、`benchmark.py` | ❌ |
| page plan 组装 | ✅ `layout_engine.py` | ❌ |
| 转命令 / playbook | ✅（纯文本生成，不执行） | ❌ |
| 执行落点、回读、导出 | ❌ | ✅ 仅 `sch_layout_apply2.py` |
| 模板/度量资产的原始测量 | ❌ | ✅ 单执行器串行测量后写回资产 |

边界规则：

1. **只有 `sch_layout_apply2.py` 可以依赖/调用 EDA。** 其余模块不得 import 执行器、CLI 或连接器；CI 应有一个 import 边界测试，防止离线模块偷偷连 EDA。
2. **单写者。** 同一工程副本同一时间只有一个 apply 写者；开始前取 live `windowId`，不硬编码。
3. **一次落点。** apply 只按已验证的 plan 执行一次；不在真机上试 gap/zonePad/halo，不做“失败→改参数→重试”的循环。失败就保留证据、回到离线改 plan。
4. **离线通过 ≠ 验收通过。** 没有回读与导出图的 apply 只能记为 `NOT RUN`；禁止把“命令返回 0”写成“布局通过”。
5. **`blocked` 不进 EDA。** validator 不是建议而是门禁；apply 在执行前校验 verdict 与 plan 哈希。
6. **测量也是真机动作。** 资产测量必须单执行器串行完成，写回 `measured_at`、EDA/连接器版本、站点、命令与样本量；测量结果不是“顺手估一个”。
7. **预算。** 一个 page plan 对应一次 apply；需要第二次落点必须产生新 plan 哈希并留下原因，不能悄悄重跑。

状态机（建议在 apply 报告里显式记录）：

```text
draft ──> solved ──> validated(pass) ──> applied ──> verified
  │          │              │                │
  └──────────┴──────────────┴────────────────┴──> blocked / failed（保留现场，不回退成“重试”）
```

## 5. 指标定义

指标分两类：**门禁指标**（违反即 `blocked`）与**质量指标**（用于候选排序/复盘，不单独放行）。所有指标离线可算，进入 scoreboard。

| 指标 | 定义 | 单位 | 目标/通过线 | 类别 | 计算模块 |
|---|---|---|---|---|---|
| `page_utilization` | 每页模块 bbox 面积之和 / 该页可用区面积；多页取总量比 | 比率 | 0.45–0.7（0.45 为推荐中心，0.7 为拥挤上界） | 质量 | `benchmark.py` / scoreboard |
| `zone_fill` | 单模块 bbox 面积 / 该模块 zone 面积；页级取均值 | 比率 | 0.55–0.85 | 质量 | `benchmark.py` |
| `label_collisions` | 可见文字 bbox 两两相交的对数 | 对 | 必须 0 | 门禁（R5） | `text_metrics.collisions()` |
| `block_overlaps` | 模块 bbox 两两相交的对数 | 对 | 必须 0 | 门禁（R4） | `hard_rules.py` |
| `title_block_hits` | zone / 文字 / 模块 bbox 与标题栏 keep-out 相交的计数 | 次 | 必须 0 | 门禁（R1/R2） | `hard_rules.py` |
| `page_count` | 规划得到的页数 | 页 | 越少越好，但不得牺牲可读性与硬规则 | 质量/预算 | `pagination.py` |
| `whitespace_balance` | 各 zone 空白率 `1 - zone_fill` 的总体标准差 | 比率 | 越小越好；建议 ≤0.15（待 benchmark 定，见 Q8） | 质量 | `benchmark.py` |
| `fits` | 完全落在可用区内的模块数 | 个 | 必须等于模块总数 | 门禁（R1） | `hard_rules.py` |
| `min_gap_violations` | 相邻模块间距 < `min_gap` 的对数 | 对 | 必须 0 | 门禁（R4） | `hard_rules.py` |
| `unsupported_metric_refs` | 未收录的器件/字号引用数 | 个 | 必须 0 | 门禁 | `device_metrics.py` / `text_metrics.py` |
| `apply_drift` | 回读实测与 plan 的几何偏差（bbox 最大边差 / 文字 bbox 最大边差） | raw | 容差内；超差即失败 | 验收 | `sch_layout_apply2.py` |

口径说明：

- **面积按 bbox 计，不按符号轮廓。** 这与“先量包络”的方法一致；轮廓面积只用于视觉参考。
- **质量指标不能互相抵消。** `page_utilization` 高不能弥补 `label_collisions`；`score` 只用于排序候选，放行只看硬规则。
- **page_utilization 的 0.45–0.7 与 planner-v3 的 `area_usage` 中心 0.45 不矛盾**：0.45 是评分最偏好的点，0.7 是可接受带的上界；超过 0.7 视为拥挤，优先拆页或换模板。
- **zone_fill 的 0.55–0.85 与既有 planner 的 `zone_fill_ratio` 一致**；低于下界说明框大块小，高于上界说明框贴块、没有标签余量。
- **`whitespace_balance` 是页内均衡度**，不是页面整体留白；先按 zone 算空白率再取标准差，避免大 zone 掩盖小 zone 的拥挤。
- 几何指标按“每页 + 全文档”两级输出（至少给出均值与最差值），禁止只报一个全局平均；`page_count`/`apply_drift` 按整份 plan 记录。

## 6. 集成清单

### 6.1 资产

| 文件 | schema | 必需字段 | 校验/失败 |
|---|---|---|---|
| `easycirq/assets/page-template.json` | `easycirq-page-template/v1` | `page{width,height,margin}`、`title_block{rect,provenance}`、`regions[]` | 缺字段/schema 不符 → `blocked`；`provenance=fallback-ratio` 要显式告警 |
| `easycirq/assets/text-metrics.json` | `easycirq-text-metrics/v1` | 至少 7/8/9/10/12/14/20 号字的行高、CJK/Latin/空格宽、上下留白 | 未收录字号 → `blocked`，不插值 |
| `easycirq/assets/device-metrics.json` | `easycirq-device-metrics/v1` | 每个标准器件：`symbol{w,h}`、`pins`、`designator{size,w}`、`value{size,w}`、`halo{left,right,top,bottom}` | 未收录器件 → `blocked`；halo 缺边 → `blocked` |

Halo 的定义：自动连线后 stub / flag / net label 的典型外扩，按四边分别记录，取实测分布的 P90；不允许用单一标量糊住四边。来源与重测触发见 [layout-engine-adr.md](layout-engine-adr.md) 的 ADR-005。

### 6.2 模块（按依赖顺序）

文件路径均为 `tools/layout2/<file>`；模块清单与契约 §2 一一对应，不得增删文件名或改路径。测试文件为 `tests/test_layout2_<module>.py`。

| # | 文件 | 职责 | 上游依赖 | 测试最低覆盖 | 完成判据 |
|---|---|---|---|---|---|
| 1 | `page_template.py` | 读取/校验模板；`usable_regions()`；`title_block_hit(rect)` | 无 | 正常、边界相切、标题栏隐藏/fallback | 不 import EDA；R1/R2 所需几何可复算 |
| 2 | `text_metrics.py` | 读取字号表；`text_bbox(text,size,anchor)`；`collisions()` | 无 | CJK、Latin、混排、未收录字号 | 返回 `{w,h,bbox}`；未收录 → `blocked` |
| 3 | `device_metrics.py` | 读取器件表；`with_halo(bbox)` | 无 | 四边 halo、缺失器件、缺边 | 不估算；未收录 → `blocked` |
| 4 | `pagination.py` | 模块列表 + 模板 → 页数与每页分配（保持亲和组、面积均衡） | 1、3 | 亲和组不拆、面积下界、N0 溢出 N0+1、页数上限 | 模块不跨页；结果确定 |
| 5 | `zone_solver.py` | 每页把模块排进 regions，输出 frames + block bbox（硬约束） | 1、3、4 | R1–R4、无解、贴边、标题栏相邻 | 无解返回 `blocked`，不越界 |
| 6 | `label_solver.py` | 在引脚周围放 net label / 文字，避免文字互撞与压框 | 1、2、5 | 密集标签、框线净空、锚点越界、无解 | R5 全过或 `blocked` |
| 7 | `hard_rules.py` | 对一份 page plan 跑 R1–R7，返回 findings/verdict | 1、2、3 | 每条规则一个 pass fixture + 一个 violation fixture | R1–R7 均可机判；findings 带定位 |
| 8 | `layout_engine.py` | 编排：device/text metrics → pagination → zone_solver → label_solver → page plans | 1–7 | 确定性、blocked 传播、schema 合法 | 同输入同输出；不 import EDA |
| 9 | `benchmark.py` | 合成模块组合语料，批量求解并打分（利用率/填充/碰撞/页数） | 1–8 | 语料固定、分数确定、回归基线 | 指标可复现；不依赖 EDA |
| 10 | `sch_layout_apply2.py` | page plans → `easycirq` 命令/playbook，真机一次执行 | 7、8 | 命令生成（离线）、拒绝 blocked、哈希不符、回读漂移 | 唯一 EDA 触点；失败留证不重试 |

接口以契约为准；契约点名的签名是：`usable_regions()`、`title_block_hit(rect)`、`text_bbox(text,size,anchor) -> {w,h,bbox}`、`collisions()`、`with_halo(bbox)`，以及 hard_rules 的 `findings/verdict`。其余内部签名由实现自定，但不得改变 page plan schema。

### 6.3 测试与 CI

- [ ] 每个模块都有 `tests/test_layout2_<module>.py`，至少覆盖：正常、边界、违反硬规则。
- [ ] fixture 全部是固定 JSON，不依赖 EDA、不访问网络、不读当前时间。
- [ ] 统一命令：`python -m unittest discover -s tests -p "test_layout2_*.py"`，全绿才可合并。
- [ ] import 边界测试：离线模块不得 import `sch_layout_apply2`、`easycirq` CLI 或连接器。
- [ ] `hard_rules.py` 的 R1–R7 每条至少一个 violation fixture，防止“规则写了但没测”。
- [ ] benchmark 有固定语料与基线；指标变化必须能解释（资产变更 / 算法变更 / 缺陷）。
- [ ] 文档中的阈值与实现默认值一致（例如 `min_gap`、`zone_fill` 带、字号表）。

### 6.4 apply 前置检查（真机）

- [ ] `validator.verdict == "pass"`，`findings == []`。
- [ ] plan 的 SHA-256 与执行时一致；plan 内页面 UUID / 页号与当前文档一致。
- [ ] 资产版本（模板/器件/字号）与生成 plan 时一致，过期则拒绝。
- [ ] live `windowId` 由 `project info` 取得，不硬编码。
- [ ] 页面为空或已确认可覆盖；残留器件数必须为 0，否则中止。
- [ ] 执行前生成命令清单/playbook 供审计；执行后回读 bbox、文字、标题栏并导出 PNG/SVG。
- [ ] 回读偏差在容差内才记 `verified`；超差或命令失败 → 停止、留证、回离线改 plan，不自动重试。
- [ ] 失败证据（stdout/stderr、退出码、页面标识、版本）落到 `docs/evidence/` 或夜间日志，供 taxonomy 归类。

### 6.5 文档与决策同步

- [ ] 任何阈值/权重改动写进 [layout-engine-adr.md](layout-engine-adr.md)，注明来源与复测触发。
- [ ] 资产 schema 变更升 `/v1` 版本；旧 plan 不得在新资产上静默重放。
- [ ] page plan schema 变更先改契约，再改本文与模块，最后改 apply。
- [ ] 指标字段进入 scoreboard，并与 apply 回读报告使用同一命名。

## 7. 开放问题

| ID | 问题 | 影响 | 建议下一步 | 阻塞实现？ |
|---|---|---|---|---|
| Q1 | 标题栏几何以哪份为准：`schematic-style.md` 写“右下角、5 mm 边距”，契约示例是 `610..1170 × 12..380`，而 `sheet-geometry` 实测示例是 `460..1160 × 10..190` | 模板/可用区全错 | 统一以 `sch sheet-geometry` 实测 + provenance 为准；示例数字只作示意；在 ADR-001 记录 | 是 |
| Q2 | y-up 坐标与“顶部/底部”命名容易混（标题栏在低 y） | region/标题/标签方向错 | 所有文档与字段统一用“低 y / 高 y”，禁用“上/下”单独表述 | 是 |
| Q3 | `min_gap` 取值：现场经验 `gap=80`，planner 默认 `40`，契约只写 `≥ min_gap` | R4 过松/过紧 | 用 benchmark 扫 40/60/80，按 halo 与标签密度分档；结果写 ADR | 是 |
| Q4 | halo 的 P90 样本量与分边统计口径 | R3 的净空是否够 | 固定样本量（如每器件 ≥20 次落点）、记录站点/EDA 版本；不足则 `blocked` | 是 |
| Q5 | 文字 bbox 的 anchor 语义（左上/中心/基线）、旋转文字、CJK+Latin 混排 | R5 误判 | 在 `text-metrics.json` 里固定 anchor 定义并加旋转字段；未支持 → `blocked` | 是 |
| Q6 | 亲和组从哪来：netlist 电源域/接口，还是人工模块计划 | 分页质量 | 优先从模块计划读；netlist 只做校验；无亲和组时按单模块成组 | 否 |
| Q7 | 页数上限与“N0+1 直到放下”的终止条件 | 可能一模块一页 | 定义 `max_pages`（按项目规模）与可读性下限；超限 `blocked` 并建议拆功能 | 是 |
| Q8 | `whitespace_balance` 的通过线 | 质量指标无法判定 | benchmark 定基线（建议先 ≤0.15），写 ADR-002/005 的复测触发 | 否 |
| Q9 | `label_solver` 是否允许移动位号/参数，还是只放 net label | 与 EDA 自动摆放冲突 | 先只放 net label/端口；位号/参数由器件符号决定，移动需单列能力 | 否 |
| Q10 | apply 回读的几何容差与文字识别方式 | 验收可能误判 | bbox 容差按 raw 定（待实测），文字用回读 bbox 而非 OCR；容差写 ADR | 是 |
| Q11 | 跨页网络标签/端口的命名与 ERC 等价性 | R6 连接正确性 | 同名网标 + 端口白名单；跨页网表 diff 作为验收项 | 是 |
| Q12 | 资产 owner 与过期天数 | 尺子腐烂 | 指定 owner；模板/器件/字号任一超过 30 天或版本变化即重测 | 否 |

## 8. 相关文档

- [layout-engine-adr.md](layout-engine-adr.md) — 本文 5 条关键取舍的背景、备选、后果与复测触发。
- [schematic-layout-thinking.md](schematic-layout-thinking.md) — 判据先行、先量后放、离线/真机分层的方法论。
- [failure-taxonomy.md](failure-taxonomy.md) — FG-01（halo）、FG-02（zone 重叠）、FG-03（标题/标签碰撞）等现场失败。
- [sedimentation-protocol.md](sedimentation-protocol.md) — L0–L6 分层与资产过期检查。
- [README.md](README.md) — `docs/method/` 索引。
