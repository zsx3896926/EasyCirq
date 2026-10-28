# D2 规则审查：阅读成本、审批等待与执行复杂度

- 任务：`skill-knowledge-audit` / 并行任务 D（规则结构化与冲突审查）
- 工作树：`hds-ska-worktree`；分支 `feat/parallel-skill-knowledge-audit`；固定基线 `9a951edc21481dc3ae91460acc11aa3e08a7be8a`
- 目录版本：`2026-10-27.1`；工具版本：`0.1.0`；结构版本：`skill-knowledge-audit/v1`
- 本文只做审查与 proposal，**不修改** `SKILL.md` 或任何 references。
- 配套夹具：`benchmarks/skill-knowledge-audit/fixtures/rule-pairs.json`（16 对，覆盖契约 §5.4 全部 12 类）。

## 1. 方法与局限

**本次实际读过（静态阅读，1-based 行号）**

| 文件 | 行数 | 读取范围 |
|---|---:|---|
| `easycirq/SKILL.md` | 323 | 全文逐行 |
| `references/evidence.md` | 29 | 全文 |
| `references/workflow.md` | 50 | 全文 |
| `references/agent-collaboration.md` | 140 | 全文 |
| `references/design-gates.md` | 410 | 全文 |
| `references/interaction.md` | 39 | 全文 |
| `references/review.md` | 36 | 全文 |
| `references/schematic-authoring.md` | 147 | 全文 |
| `references/schematic-layout.md` | 138 | 全文 |
| `references/pcb-execution.md` | 401 | 全文 |
| `references/execution-efficiency.md` | 60 | 全文 |
| `references/offline-tools.md` | 173 | 全文 |
| `references/installation-updates.md` | 134 | 全文 |
| `references/lcsc-sourcing.md` | 74 | 全文 |
| `references/sources.md` | 62 | 全文 |
| `references/manufacturing-routes.md` | 815 | 抽读 1–80、330–439、690–815；其余未逐行读（README 级 skim） |
| `easycirq/.version` / `CHANGELOG.md` | — | `.version`=`1.0.1`；CHANGELOG 头部 1.0.0/1.0.1 |

定位候选时另用只读 grep 看过 `tool-gotchas.md`、`pcb-routing-strategy.md`、`pcb.md`、`eda-efficiency.md`、`eda-execution.md`、`client-compatibility.md` 的命中行，**未**全读这些文件。

**方法与局限（必须与"已验证"区分）**

- 方法：人工/模型逐条静态阅读 + 对候选行做人工裁定；不以正则结果直接作为已审规则。本文件全部 12 条记录 `provenance=maintainer_declared`、`extraction.method=curated|manual`，即 **reviewed**；不是 `machine_extracted`。
- 引用校验：每条 quote 由任务内只读 Python 脚本核对该子串确实出现在声明文件/行；行号与引文不靠记忆。
- **未运行模型会话**：本审查不是模型行为实验，不能证明 Agent 实际遵守或违反任何规则；不证明加载行为、阅读轮次或审批次数变化。
- 未调用 EDA/Connector、未启动浏览器、未联网、未执行源文档代码块；除只读校验脚本外未运行仓库工具。
- 分类是启发式人工判断（依契约 §5.3 判定顺序），**不是确定性证明**；条件/例外只能按文本判定，无法验证运行时语义。
- 行号绑定固定基线 9a951ed；源文件后续变化会使行号漂移。
- `manufacturing-routes.md`、`tool-gotchas.md` 只做了定位级抽读，涉及它们的结论只限命中行，不外推到全文。

## 2. 已审规则记录（12 条）

以下 JSON 可直接供 `catalog/rules.json` 使用；`text` 均 ≤500 字符且已核到行。

```json
[
{"rule_id":"R-SKILL-001","text":"方案、原理图、布局、交付设为四个可见检查点。默认在任务已授权范围内自查、汇报并继续；用户说“先评审”“这步给我看”“确认后再布线”时，在对应边界等待。不要把工程检查点一律变成权限停顿点。真正改变已确认接口/尺寸/成本目标、涉及关键未知量时，先处理该决定，同时推进无依赖部分。","source":{"path":"easycirq/SKILL.md","line_start":96,"line_end":96},"condition":"用户已要求设计/修改且未明确要求分阶段确认（默认）；或用户明确说“先评审/这步给我看/确认后再布线”","task_scope":["requirements","concept","schematic","pcb","delivery"],"action":"在已授权范围内自查、汇报并继续；仅在用户明确要求时于对应边界等待；关键未知量先处理决定并推进无依赖部分","strength":"must","exception":"用户明确要求分阶段确认时在对应边界等待","evidence_required":["用户明确要求暂停/评审的原话"],"priority_declared":"用户明确指令优先于默认评审节奏","version_applicability":"v1.0.1","provenance":"maintainer_declared","extraction":{"method":"curated","confidence":"high","notes":"任务 D 人工逐行审查；解决“自主完成 vs 必须等待”的主要依据"},"review_note":"默认不停顿、等待需用户显式触发；这是“审批等待”抱怨的正当出口而非新增负担。"},
{"rule_id":"R-SKILL-002","text":"用户已要求设计/修改时，常规选型、读取、计算、绘图和检查属于任务范围；沿用宿主的实际权限要求，不自建额外审批。","source":{"path":"easycirq/SKILL.md","line_start":62,"line_end":62},"condition":"用户已要求设计/修改","task_scope":["requirements","concept","schematic","pcb","check"],"action":"把常规选型/读取/计算/绘图/检查视为任务范围内工作，不新增自建审批","strength":"must","exception":"宿主实际权限要求","evidence_required":["宿主权限/工具授权状态"],"priority_declared":"宿主权限优先；用户任务范围优先","version_applicability":"v1.0.1","provenance":"maintainer_declared","extraction":{"method":"curated","confidence":"high","notes":"与 R-SKILL-001 互补，限定审批来源"},"review_note":"把“审批”限定为宿主权限与用户要求，压缩自造等待空间。"},
{"rule_id":"R-GATE-003","text":"门禁是**阶段退出证据门，不是审批门**：在用户已授权的设计/修改范围内自查、记录并继续，不新增等待点；只有证据缺失或门禁失败时停住依赖链路。G0–G6 是 S1–S5 的退出条件，不是第二套流程；定义、命令、证据与豁免见 [阶段门禁](references/design-gates.md)。","source":{"path":"easycirq/SKILL.md","line_start":226,"line_end":226},"condition":"G0–G6 阶段退出证据判定","task_scope":["design_gate","schematic","pcb","check","delivery"],"action":"自查、记录并继续，不新增等待点；仅证据缺失/门禁失败时停住依赖链路","strength":"must","exception":"证据缺失或门禁失败时暂停依赖链路","evidence_required":["门禁证据文件/失败项"],"priority_declared":"用户明确要求优先；不可豁免项优先","version_applicability":"v1.0.1","provenance":"maintainer_declared","extraction":{"method":"manual","confidence":"high","notes":"与 design-gates.md:7 近乎重复"},"review_note":"证据门≠审批门；“不新增等待点”是机器可检索的关键句。"},
{"rule_id":"R-GATE-004","text":"门禁是**阶段退出证据门，不是审批门**。Agent 在用户已授权的设计/修改范围内自查、记录并继续；门禁不新增等待点，也不要求用户逐项签批。只有用户明确说“先评审 / 这步给我看 / 确认后再布线”时，才在方案、原理图、布局、交付四个可见检查点等待。","source":{"path":"easycirq/references/design-gates.md","line_start":7,"line_end":7},"condition":"阶段门禁执行；用户未明确要求分阶段确认","task_scope":["design_gate","schematic","pcb","delivery"],"action":"默认自查记录继续；仅用户明确要求时在四个检查点等待","strength":"must","exception":"用户明确要求分阶段确认时等待","evidence_required":["用户明确要求等待的原话","门禁证据"],"priority_declared":"用户明确要求优先","version_applicability":"v1.0.1","provenance":"maintainer_declared","extraction":{"method":"manual","confidence":"high","notes":"与 SKILL.md:96/226、interaction.md:30、design-gates.md:395 重复陈述"},"review_note":"同类规则在 5 处重复，是“规则越多读得越久”的典型来源，建议合并（P-02）。"},
{"rule_id":"R-GATE-005","text":"6. **缺证据就是 `BLOCKED`，不是 `PASS`。** 未运行、未导出、未回读的检查保持 `待确认`；报告写 `NOT RUN`，不写“应该没问题”。","source":{"path":"easycirq/references/design-gates.md","line_start":63,"line_end":63},"condition":"检查未运行/未导出/未回读","task_scope":["design_gate","schematic","pcb","check","delivery"],"action":"判 BLOCKED/待确认，报告写 NOT RUN，不写“应该没问题”","strength":"must","exception":"unknown（豁免清单仅适用于可豁免项，缺证据本身不因谨慎而通过）","evidence_required":["实际运行/导出/回读的证据文件"],"priority_declared":"不可豁免清单优先","version_applicability":"v1.0.1","provenance":"maintainer_declared","extraction":{"method":"manual","confidence":"high","notes":"防伪通过规则；与离线继续工作不冲突（见 CT-05/CT-10）"},"review_note":"这条正是“信息不足但假通过”的解药；不应被读成“证据不足就整任务停止”。"},
{"rule_id":"R-READ-006","text":"内部设计始终遵循 [工程工作流](references/workflow.md) 和 [证据与工程记录](references/evidence.md)，内容由Agent消化，不要求用户读完。按任务加载：","source":{"path":"easycirq/SKILL.md","line_start":134,"line_end":134},"condition":"内部设计任务（原理图/PCB/交付）","task_scope":["concept","schematic","pcb","check","delivery"],"action":"始终遵循 workflow.md 与 evidence.md；其余参考资料按任务表行按需加载","strength":"must","exception":"按任务表未命中的资料不加载；不要求用户阅读","evidence_required":["任务类型与阶段（用于选择加载行）"],"priority_declared":"unknown","version_applicability":"v1.0.1","provenance":"maintainer_declared","extraction":{"method":"manual","confidence":"high","notes":"“始终”只约束 2 个文件，其余 on-demand"},"review_note":"“始终遵循”与“不加载规则百科”并存，范围不同（见 CT-07），不应读成全量预载。"},
{"rule_id":"R-EXEC-007","text":"批次间有依赖、需观察中间结果或源快照变化时重新采集并分批；不能为提速跳过身份、连接、DRC 或最终保存重开。","source":{"path":"easycirq/SKILL.md","line_start":130,"line_end":130},"condition":"批量写入/合批提速","task_scope":["pcb","schematic","execution"],"action":"依赖存在时重新采集并分批；保留身份/连接/DRC/最终保存重开","strength":"must","exception":"批次间无依赖且快照不变时可合批（同段前文）","evidence_required":["fresh snapshot 哈希","apply/report","DRC 与回读证据"],"priority_declared":"证据完整性优先于提速","version_applicability":"v1.0.1","provenance":"maintainer_declared","extraction":{"method":"manual","confidence":"high","notes":"自带例外，是“提速 vs 不减验收”的覆盖条款"},"review_note":"例外写在同段，使提速规则可执行；不要把“合批”读成“降低验收”。"},
{"rule_id":"R-EXEC-008","text":"- 小任务、现成完整计划：直接使用现有 `--plan`，不要额外拆模块。","source":{"path":"easycirq/references/execution-efficiency.md","line_start":5,"line_end":5},"condition":"小任务且已有现成完整计划","task_scope":["pcb","execution"],"action":"直接使用现有 --plan，不额外拆模块","strength":"must","exception":"同快照多独立放置模块，或有依赖/需观察中间结果（同文件 6–8 行）","evidence_required":["现有 plan 与快照基线"],"priority_declared":"unknown","version_applicability":"v1.0.1","provenance":"maintainer_declared","extraction":{"method":"manual","confidence":"high","notes":"与 R-EXEC-007 同向"},"review_note":"示例命令 FX-10（多 --module-plan）只是调用示例，不构成“必须拆模块”。"},
{"rule_id":"R-START-009","text":"新硬件任务开始前可用当前安装目录的 `scripts/skill_update.py check` 统一检查本 Skill 与 easyeda-agent 的 CLI/Skill/daemon/Connector（24 小时缓存）；","source":{"path":"easycirq/SKILL.md","line_start":15,"line_end":15},"condition":"新硬件任务开始前；或用户要求检查更新","task_scope":["installation","update","startup"],"action":"可运行 skill_update.py check 统一检查（24 小时缓存），先确认实际客户端与安装路径","strength":"may","exception":"网络失败不阻塞原工程任务（16 行）；不在画板中途替换技能（17 行）；只在用户要求升级且无进行中操作时更新","evidence_required":["check 输出、客户端/安装路径、缓存时间"],"priority_declared":"用户升级要求优先；空闲时机优先","version_applicability":"v1.0.1","provenance":"maintainer_declared","extraction":{"method":"manual","confidence":"high","notes":"措辞为“可用”，是 may 而不是义务"},"review_note":"“开始前检查”是可选启动成本，非强制预载；与 R-START-010 不冲突（CT-02）。"},
{"rule_id":"R-START-010","text":"纯方案/资料分析任务无需提前连接、安装或探测EDA；准备实际读写工程或用户要求接通环境时，再执行本节。","source":{"path":"easycirq/SKILL.md","line_start":104,"line_end":104},"condition":"纯方案/资料分析任务","task_scope":["concept","analysis","schematic","pcb"],"action":"把 §2 执行能力检查推迟到实际读写工程或用户要求接通时","strength":"may","exception":"需要实际读写工程或用户要求接通环境时执行 §2","evidence_required":["任务类型判定（纯分析 vs 需写工程）"],"priority_declared":"unknown","version_applicability":"v1.0.1","provenance":"maintainer_declared","extraction":{"method":"manual","confidence":"high","notes":"“无需”是解除前置义务，非禁止"},"review_note":"与 R-START-009 同属可选，二者组合不产生审批或强制加载义务。"},
{"rule_id":"R-LAY-011","text":"局部连接优先直接画线；只有跨区、跨页或长距离才用标签。","source":{"path":"easycirq/references/schematic-layout.md","line_start":74,"line_end":74},"condition":"绘制或整理原理图","task_scope":["schematic"],"action":"局部连接优先直接画线；跨区/跨页/长距离才用标签","strength":"should","exception":"既有符号难以直连时用短引线+明确标签（同文件 54 行）","evidence_required":["pin-net/网表回读","官方导图"],"priority_declared":"项目既有图面风格优先","version_applicability":"v1.0.1","provenance":"maintainer_declared","extraction":{"method":"manual","confidence":"high","notes":"与 R-LAY-012 构成 default+exception；与 SKILL.md:120 重复"},"review_note":"“直连 vs 标签”是默认+例外，不是二选一的冲突。"},
{"rule_id":"R-LAY-012","text":"既有符号难以直连时用短引线与明确标签化解，不牺牲pin-pad映射。","source":{"path":"easycirq/references/schematic-layout.md","line_start":54,"line_end":54},"condition":"既有符号难以直连","task_scope":["schematic"],"action":"允许短引线+明确标签，但不得改库脚号/交换引脚","strength":"may","exception":"unknown","evidence_required":["符号/引脚身份回读","pin-pad 映射"],"priority_declared":"pin-pad 映射正确性优先","version_applicability":"v1.0.1","provenance":"maintainer_declared","extraction":{"method":"manual","confidence":"high","notes":"前半句允许(may)，后半句硬约束(must)"},"review_note":"显式例外条款，覆盖 R-LAY-011 的“优先直连”。"}
]
```

## 3. 确认冲突

**未发现确定性冲突。** 本次审查没有找到同时满足契约 §5.3 第 8 条（动作族相反、条件与范围重叠、均非历史/示例/否定、且无覆盖例外、并需列出两段原文）的规则对。不把候选当已确认冲突。

被驳回的候选（保留记录，供后续版本重查）：

| 候选 | 表面冲突 | 为什么不是 true_conflict |
|---|---|---|
| CT-01 | “不新增等待点” vs “布局冻结后必须先重开 G3” | 作用阶段不同：G3 是阶段顺序/证据要求，不是审批等待；无同一触发场景 |
| CT-02 | “开始前检查更新” vs “纯分析任务无需提前探测” | task_scope 不相交；且前者 strength=may（“可用”），无义务 |
| CT-03 | “局部直连” vs “跨区用标签” | 两处方向一致，仅表达介质不同（标签/端口）；coexist |
| CT-04 | “优先直连” vs “用短引线+标签化解” | 后者是“既有符号难以直连”的显式例外，覆盖前者 |
| CT-05 | “缺证据=BLOCKED” vs “缺执行通道仍可继续” | 前者约束“结论/通过”，后者约束“工作连续”；方向一致 |
| CT-06 | “问做个板子→默认PCB” vs “自定义PCB非必经” | “做个板子”是否等于“明确要定制板”未定义 → ambiguity |
| CT-07 | “内部设计始终遵循…” vs “按需读取，不加载规则百科” | “始终”只覆盖 workflow/evidence 两个文件，其余按任务表加载 → different_scope |
| CT-08 | “只在用户要求时在检查点等待” vs “真正需要新决定时才等待” | 覆盖关系不可静态判定（检查点等待 vs 新决定处理）→ ambiguity |
| CT-09 | “完整产品不是默认终点” vs “局部任务不追加范围” | 任务范围词不相交（完整产品 vs 局部任务） |
| CT-10 | “合批提速” vs “任一步失败只能 unverified” | 前者自带“不能为提速跳过…最终保存重开”的例外，二者同向 |

## 4. 候选张力（10 对，均未确认）

> 格式：A / B 均为可核对原文（`path:line`，取该行子串）；“分类”按契约 §5.3 分类词。

**CT-01 自主推进 vs 布局后等待**
- A：`SKILL.md:96` “默认在任务已授权范围内自查、汇报并继续；用户说……时，在对应边界等待。不要把工程检查点一律变成权限停顿点。”
- B：`design-gates.md:153` “布局冻结后若为了布线移动器件，必须先重开 G3 并作废受影响布线。”
- 为何像冲突：A 要求默认继续，B 要求“先重开 G3”，读起来像布局后强制暂停/审批。
- 分类：`different_stage`。B 是阶段顺序/证据要求（布局冻结后的变更回到 G3），不是等待用户；A 的例外只由用户显式触发。无重叠触发场景 → 非冲突。

**CT-02 启动即检查 vs 先离线推进**
- A：`SKILL.md:15` “新硬件任务开始前可用当前安装目录的 `scripts/skill_update.py check` 统一检查……”
- B：`SKILL.md:104` “纯方案/资料分析任务无需提前连接、安装或探测EDA……”
- 为何像冲突：一个说开工前检查，一个说无需提前探测，像“速度优先 vs 全量加载”。
- 分类：`different_scope`。A 的 scope 是更新/安装检查且为 may；B 的 scope 是纯分析任务的 EDA 探测。即使重叠，A 只是可选 → 非冲突。

**CT-03 直接导线 vs 网名标签（正题）**
- A：`schematic-layout.md:74` “局部连接优先直接画线；只有跨区、跨页或长距离才用标签。”
- B：`SKILL.md:120` “局部反馈、分压、滤波和去耦保留可追踪导线，跨区信号才考虑端口。”
- 为何像冲突：A 提“标签”、B 提“端口”，用户可能读成两种互斥表达。
- 分类：`coexist`（近乎重复）。“直连”与“跨区标签/端口”是同一条规则的不同措辞，非冲突。

**CT-04 优先直连 vs 允许标签**
- A：`schematic-layout.md:74` “局部连接优先直接画线；只有跨区、跨页或长距离才用标签。”
- B：`schematic-layout.md:54` “既有符号难以直连时用短引线与明确标签化解，不牺牲pin-pad映射。”
- 为何像冲突：A 似乎禁止局部标签，B 明确允许局部用标签。
- 分类：`default_with_exception`。B 的条件“既有符号难以直连”是 A 的覆盖例外，条件不冲突。

**CT-05 严格检查 vs 缺信息假通过**
- A：`design-gates.md:63` “缺证据就是 `BLOCKED`，不是 `PASS`。”
- B：`SKILL.md:112` “缺少执行通道时仍可完成方案、计算或离线规划；明确列出未写入项，不把文本、JSON、图片或探针结果说成用户工程已完成。”
- 为何像冲突：A 像“没证据就停”，B 像“没通道也继续”。
- 分类：`coexist`。A 约束“不得声称通过”，B 约束“继续可做的部分并如实标注”；二者方向一致。

**CT-06 “做个板子”默认路线**
- A：`SKILL.md:42` “问“做个板子”默认推进适合目标的原理图及PCB候选……”
- B：`SKILL.md:84` “自定义PCB不是所有idea的必经之路：现成模块能更快验证效果时，解释后作为适用路线；用户明确要定制板时保留定制交付……”
- 为何像冲突：A 把“做个板子”默认映射到 PCB 候选，B 允许模块路线替代。
- 分类：`ambiguity`。“做个板子”是否等于“明确要定制板”未定义，静态阅读无法判定条件是否重叠；需维护者补充判别（P-03），不能判 true_conflict。

**CT-07 始终遵循 vs 不加载百科**
- A：`SKILL.md:134` “内部设计始终遵循 [工程工作流]……按任务加载：”
- B：`SKILL.md:132` “## 3. 按需读取，不加载规则百科”
- 为何像冲突：“始终遵循”像全量预载，“不加载规则百科”像禁止预载。
- 分类：`different_scope`。A 的“始终”只覆盖 2 个文件（workflow/evidence），其余按任务表加载；B 约束的是一般参考资料。非冲突。

**CT-08 检查点等待 vs 新决定等待**
- A：`design-gates.md:7` “只有用户明确说“先评审 / 这步给我看 / 确认后再布线”时，才在……四个可见检查点等待。”
- B：`interaction.md:30` “只有用户要求分阶段确认，或真正需要新决定时才等待。”
- 为何像冲突：A 把等待条件限定为用户明确要求，B 额外加入“真正需要新决定”。
- 分类：`ambiguity`。“四个可见检查点等待”与“新决定处理”的覆盖关系无法从文本确定（`SKILL.md:96` 的“先处理该决定”也未说明是否等待）→ 需维护者明确（P-04），不能判 true_conflict。

**CT-09 完整产品终点 vs 局部范围**
- A：`SKILL.md:8` “完整产品任务以实物是否实现原始用途验收，画完图、买齐料或贴片完成都不是默认终点。”
- B：`SKILL.md:30` “用户只要求画图、review、换料、PCB或先方案时，仍按该范围交付，不强行追加App、外壳、采购或完整产品开发。”
- 为何像冲突：A 像“必须做到实物”，B 像“做完图纸就停”。
- 分类：`different_scope`。A 的 scope 是完整产品/设备任务，B 的 scope 是局部任务，范围不相交。

**CT-10 合批提速 vs 完整验收**
- A：`SKILL.md:130` “批次间有依赖、需观察中间结果或源快照变化时重新采集并分批；不能为提速跳过身份、连接、DRC 或最终保存重开。”
- B：`pcb-execution.md:306` “- save/reload/journal/dump 任一失败都只能报 `unverified`，不能写 `verified`。”
- 为何像冲突：A 鼓励一次合批写入，B 要求对任一步失败保持未验证。
- 分类：`coexist`。A 同段自带“不能跳过最终保存重开/DRC”的例外，与 B 同向 → 非冲突。

## 5. 夹具类别覆盖（契约 §5.4 的 12 类）

| 契约类别 | 夹具 pair_id | 说明 |
|---|---|---|
| 真冲突 | FX-01 | 构造侧“逐门禁签批” vs `design-gates.md:7`；仅测试分类器，不代表仓库存在该冲突 |
| 默认+例外 | FX-02、FX-15 | 直连/标签；更新前提“仅当…无进行中任务”覆盖“用户一说就执行” |
| 不同阶段 | FX-03 | 一般评审节奏 vs 布局冻结后重开 G3 |
| 不同工程范围 | FX-04、FX-13 | 完整产品 vs 局部任务；新任务启动检查 vs 纯分析 |
| 引用过时 | FX-05 | 已废弃 `layout-lint --gate` 仍被当作放行依据 |
| 语言歧义 | FX-06 | “做个板子”是否等于“明确要定制板”未定义 |
| 用户授权条件 | FX-07 | “不重复求确认” vs “在边界等待”，由用户指令覆盖 |
| 技术限制 | FX-08 | Agent 推进 vs v1.14.0 无 Gerber/钻孔/CPL CLI |
| 否定句 | FX-09 | “才等待” vs “不要把检查点变成权限停顿点” |
| 代码示例 | FX-10 | 示例命令多 `--module-plan` vs “无需为合批拆模块” |
| 中英混合/跨段 | FX-12 | `warn` 不阻塞（§4 第 1 条）vs 缺证据 `BLOCKED`（第 6 条） |
| 共存（补充） | FX-11、FX-14、FX-16 | 局部直连重合；缺证据 vs 离线继续；合批 vs unverified |

夹具文件校验：16 对、12 类全部覆盖；非构造侧 quote 已逐条核到声明行（只读脚本，0 mismatch）。

## 6. 解决建议（proposal only，不改源文件）

| ID | 触发场景 | 原文位置 | 影响 | 建议变化（仅提案） | 是否改变工程保护 | 验证场景 |
|---|---|---|---|---|---|---|
| P-01 | Agent 反复自造审批/超时等待 | `SKILL.md:96`、`:226`、`design-gates.md:7` | 审批等待增加、执行变慢 | 在 3 处统一加一句“等待必须能回指用户明确原话或不可豁免门禁”，其余一律继续 | 否（收紧而非放松） | 用 2 个 intent（自主/分阶段）对比 plan 的 `approval_gates` 是否只含用户/新范围决策 |
| P-02 | 同一“门禁不是审批”规则在 5 处重复 | `SKILL.md:96,226`、`design-gates.md:7,395`、`interaction.md:30` | 阅读轮次与 token 增加 | 保留 `design-gates.md:7` 为唯一正文，其余改“见链接”一句 | 否 | D1 引用图：重复主题数下降且必读闭包不变 |
| P-03 | “做个板子”路线选择有歧义 | `SKILL.md:42`、`:84` | 误判用户意图，产生返工 | 增加定义：仅当用户拒绝模块路线或明说“定制/画板”才视为“明确要定制板” | 否（澄清默认路线） | 2 个场景：现成模块 vs 明确定制板，检查 must_include 与后续动作 |
| P-04 | 检查点等待 vs 新决定等待边界不清 | `design-gates.md:7`、`interaction.md:30` | 可能多等或多问 | 明确“新决定=改变已确认接口/尺寸/成本/范围”，并说明其不属于检查点等待 | 否 | 场景：布局前出现尺寸变更，检查是否只触发 `decisions_required` 而非通用 gate 等待 |
| P-05 | 启动即做更新/环境检查导致首轮变慢 | `SKILL.md:15`、`:104`、`:110` | 首轮延迟、离线任务被打断 | 把“可”保持为可选，并注明纯分析任务直接跳过、仅在实际读写工程前运行 | 否 | 纯分析 intent 计划不得含 `install`/`network` 动作；新任务 intent 允许 |
| P-06 | “直连 vs 标签”分散在 5+ 处 | `schematic-layout.md:13,54,74`、`SKILL.md:120`、`workflow.md:31` | 重复阅读、易误读为互斥 | 以 `schematic-layout.md:74`+`:54` 为唯一“默认+例外”条目，其余改链接 | 否 | D1 检查该主题重复数；夹具 FX-02/FX-11 分类稳定 |
| P-07 | “缺证据=BLOCKED”被误读为“整任务停止” | `design-gates.md:63`、`SKILL.md:112` | 过度停顿或反向假通过 | 在 63 行后补一句“BLOCKED 只影响依赖链路，其余离线工作继续” | 否 | 夹具 FX-14 与场景 forbidden_plan_actions 校验 |
| P-08 | 门禁字段枚举与“前六个字段”表述不一致 | `design-gates.md:76`、`:80` | 维护者需重读比对，易误配豁免 | 在 80 行按字段名重复列出而非“前六个字段” | 否（不改变不可豁免集合） | 构造 design-state 缺 `environment_accuracy`，应仍判 BLOCKED |
| P-09 | 示例命令使用旧版本号，易被当成当前版本 | `installation-updates.md:65,66,67,81`（`0.8.0`）vs `.version`=`1.0.1` | 阅读者误判当前版本/复制旧命令 | 把示例版本改为 `<version>` 占位并加“示例版本”注明 | 否 | 文档 lint/夹具 FX-10 类代码示例分类 |
| P-10 | 分类算法需要“已审关系”证据 | `catalog/rules.json`（待建） | 候选被误当确认冲突 | 只把本文 §4 的 10 对与 §3 驳回记录写入 `relations`，`true_conflict` 仅保留构造/证据充分者 | 否 | `rules` 命令的 `reviewed_relations` 与夹具分类准确率 |
