# Holdout 场景说明（独立设计 / 分离评阅阶段）

- 交付物：`benchmarks/skill-knowledge-audit/scenarios/holdout.json`（`schema: ska-scenarios/v1`，`split: holdout`，5 个场景 `holdout-01`…`holdout-05`）
- 冻结基线：`9a951edc21481dc3ae91460acc11aa3e08a7be8a`；冻结目录版本：`2026-10-27.1`
- 设计者：并行任务 D 的独立场景设计者（teammate `scenario-holdout`）
- 阶段性质：**分离评阅（separated review）阶段，不是盲测（blind test）**。本文件给出设计依据与预期，但设计者没有运行实现、没有观测模型行为、没有做端到端验证；详见 NOT RUN。

## 1. 设计者独立性声明

- **未读** `benchmarks/skill-knowledge-audit/scenarios/dev.json`，**未读** `benchmarks/skill-knowledge-audit/scenarios/README.md`；这两个文件由并行队友编写，本场景集与之没有共享 id、措辞或选择。
- **未读** `design-hardware/scripts/skill_knowledge_audit/` 的实现代码，**未运行** `plan`/`benchmark` 命令，**未查看** 任何 planner 输出（设计时也不存在可抄的输出）。
- 场景 id、措辞、任务组合与期望值独立决定，未与 dev 集协调；期望值是按契约 §6–§7 与 `design-hardware/SKILL.md` 的显式触发文本推导的，不是对实现行为的反推。
- 独立起草完成后，只用仓库内的 `benchmarks/skill-knowledge-audit/scenarios/validate_scenarios.py` 的**通用校验函数**检查过本文件（未读该脚本会加载的 `dev.json`，也未运行它的 `main` 去校验 dev 集），并按其中标注为 Lead-frozen 的**跨集合口径**（always 文档、门禁范围内任务需 `design-gates.md`、门禁 token 命名、`may_include` 上限）做了对齐；这只调整 schema 级口径，没有改动任何场景内容。
- 因不是盲测，读者不应把本 holdout 当作"实现从未见过"的干净测试；它只是"未针对 dev 调参、未偷看实现"的独立场景集。

## 2. 派生方法

1. 先读 `docs/parallel-skill-knowledge-audit/contract.md` §6（intent / 计划 / 缓存 / 预算）与 §7（场景 schema 与判定语义），把可用枚举抄成硬约束：`task_type`、`stage`、`unknown.code`、`execution_contract.actions`、`approval_gates`。
2. 完整读 `design-hardware/SKILL.md`，只从其中**显式触发句**派生任务文档，例如：
   - "内部设计始终遵循 [工程工作流] 和 [证据与工程记录]"（`workflow.md`、`evidence.md`）；
   - "设计审查、故障排查、样机上电 → [审查与验证]"（`review.md`）；
   - "验收仍使用 [图面验收标准]"（`schematic-layout.md`）；
   - "真实PCB任务先读 [PCB执行工作流]"（`pcb-execution.md`）；
   - "每个采购相关任务读 [立创商城选型与配单]"、"用户要求选型、换料或BOM → [选型与装配变体]"（`lcsc-sourcing.md`、`part-selection.md`）；
   - "绘制/整理/换料/建库 → [原理图工程习惯]"（`schematic.md`）；
   - "打板/贴片任务同时执行 [生产规则接入]"（`jlc-handoff.md` → `jlc-production.md`）；
   - "SMT工艺边/Mark/拼板/可焊性/BOM坐标/DFM → [嘉立创SMT生产规则]"（`jlc-smt-rules.md`）；
   - §3.2 阶段门禁 G0–G6 与 `design-gates.md`、G6 的 Gerber/钻孔/CPL 只能由用户在 EDA GUI 导出。
3. 为每个场景选一组彼此不同的自然语言组合（禁止 EDA、冻结原理图、仅 BOM、小预算、缺制造证据），避免"标准教科书式"提问；中文原话 4 个（`holdout-01`、`03`、`04`、`05`），英文工程师口吻 1 个（`holdout-02`），以测试中文/英文同义表达与条件句解析。
4. 只把**有明确原文依据**的文件放进 `must_include`；把握较低但合理可能被选中的放进 `may_include`（按冻结口径最多 4 个）；跨任务类型明显不该出现的放 `must_exclude`。`required_unknown`/`required_approval_gates` 按契约 §7.1 作为**期望子集**（实际计划多出不判失败），只写与 intent 字段一一对应、可机器判定的项；`required_approval_gates` 的 token 同时写进 `intent.user_decision_pending`，因为冻结口径要求"planner 只复制、不推断"。
5. 所有路径都用脚本逐条 `os.path.isfile` 校验存在（相对仓库根的 `design-hardware/...`），未引用任何不存在的路径；不写行号、不编造引文。

## 3. 逐场景：为什么是公平 holdout

### holdout-01 禁止 EDA 与联网的原理图文档评审

- 任务类型 `review_only`、阶段 `check`，intent 明确 `eda_available:false` 并禁止 EDA/联网/改图；`notes` 是完整中文生活化原话，而不是"帮我 review 原理图"这类教科书句。
- 公平性：`must_include` 只含 always 三件（`SKILL.md`、`workflow.md`、`evidence.md`）加两份有显式触发文本的文件——`review.md`（"设计审查、故障排查、样机上电 → [审查与验证]"）与 `schematic-layout.md`（用户点名图面可读性，对应"验收仍使用 [图面验收标准]"）。契约 §6.2 已声明"仅评审不要求连接 EDA"，因此不要求 `eda_unavailable`（若设为期望会与契约冲突），改用 `forbidden_plan_actions` 断言不出现 `read_eda`/`write_eda`/`network`/`install`/`order_parts`。
- 泛化点：把"禁止动作"当作一等约束，而不是"用户说 review 就默认拉全套 PCB/采购文档"。

### holdout-02 自主推进中途的范围扩张（加 CAN / 缩板框 / 压成本）

- 任务类型 `pcb_route`、阶段 `route`、`autonomous_authorized:true`；用户先说"原理图别动、别每阶段问我、一直做到 DRC"，随后追加新范围与新机械/成本目标。
- 公平性：`design-gates.md` 因用户要求做到 DRC 且 G3/G4 是布线并列前置而必然适用；`pcb-execution.md` 有"真实PCB任务先读"原文；`workflow.md`/`evidence.md`/`SKILL.md` 为 always。`required_approval_gates` 只取 `user_decision_pending` 两条冻结 token（`scope_change`、`mechanical_change`），不额外要求 `cost_change`/`interface_change`（避免把"默认谨慎"写成门禁）。`wait_user_approval` 进 forbidden 是因为契约 §6.2 明写"授权自主：不得自动生成'等待用户批准'步骤"，且用户明确说不需要每阶段确认。
- 泛化点：新范围进来时是"列决策 + 继续无依赖部分"，还是"停下来等批准"或"悄悄改原理图"。

### holdout-03 Skill 更新后已读缓存过期（只改一处限流电阻）

- 任务类型 `schematic_edit`，`already_read` 两条分别指向 `SKILL.md` 与 `workflow.md`，绑定旧 sha256 与旧 `rules_version: 2026-10-20.1`，而请求冻结目录版本为 `2026-10-27.1`。
- 公平性：契约 §6.3 明写"文件变化、目录版本变化、任务扩展（scope hash 变化）都必须失效；不使用 mtime"，因此 `already_read_stale` 是唯一直接命中的 `unknown` code；`already_read` 指向的 `SKILL.md`/`workflow.md` 因此必须重读，剩下 required 来自"始终遵循"（`evidence.md`）、换料行（`part-selection.md`）、原理图习惯行（`schematic.md`），并按冻结口径补 `design-gates.md`（`schematic_edit` 属门禁范围任务）。
- 泛化点：缓存失效必须重读，而不是"用户说读过就跳过"；同时不要因缓存问题扩大到完整产品/SMT 文档。

### holdout-04 仅 BOM 配单：现货证据缺失与小预算

- 任务类型 `bom_only`、阶段 `delivery`，`eda_available:false`；用户强调"别碰工程、别下单、没查到就写待查、上下文很小"，并声明自己手焊。
- 公平性：`lcsc-sourcing.md` 有"每个采购相关任务读"，`part-selection.md` 有 BOM 行，`evidence.md` 覆盖"缺报价不填0 / 来源与查询时间 / 实时证据缺失写待查"，另有 always 的 `SKILL.md`/`workflow.md`。`budget_chars: 1200` 明显小于本次实测 required 五份文件的 chars 合计约 35319（`SKILL.md` 24988、`workflow.md` 1986、`evidence.md` 917、`lcsc-sourcing.md` 4078、`part-selection.md` 3350），按契约 §6.4"required 超预算时不裁剪 required，标 `incomplete` 列 `uncovered`"，`budget_insufficient` 是机器可判定的期望。
- 泛化点：小预算下仍保留 always/保护主题与任务必需文档，而不是把 required 裁剪成空；同时按"仅 BOM 排除布线"正确排除布线/贴片文档。

### holdout-05 交付审计：制造文件导出不可用，缺证据即停

- 任务类型 `delivery_audit`、阶段 `delivery`，`eda_available:false`；用户要求按 G0–G6 审交付包、内部检查点自主通过，但"EDA 连不上、Gerber/钻孔/坐标导不出来"，并明确"缺证据就别替我判通过——停下来告诉我缺什么"。
- 公平性：`design-gates.md` 是 G0–G6 的定义，且明写 G6 的 Gerber/钻孔/CPL 只能由用户在 EDA GUI 导出、缺人工证据时仍 `BLOCKED`；`evidence.md` 有"未找到问题必须附已覆盖范围 / 关键资料缺失=待确认"；`jlc-handoff.md` 有"打板/贴片任务同时执行生产规则接入"与按路线裁剪交付清单；`jlc-smt-rules.md` 覆盖工艺边/Mark/BOM 坐标/DFM 与"厂方审核未执行"的记录方式。`eda_unavailable` 对应 intent 的 `eda_available:false` 与导不出来；`missing_evidence` 是用户明确要求的暂停条件（契约允许"用户明确要求"的门）。
- 泛化点：本场景**允许、但不要求** `wait_user_approval` 语义（contract §10.2 已冻结"wait 只在用户显式给 `before_*` 门时加入"，`missing_evidence` 以 `decisions_required` 表达），正好与 holdout-02 的"禁止自动等待"形成对照——自主/评审边界取决于用户是否显式要求暂停，而不是实现里的固定套路。评阅实测该计划 actions 无 wait，期望字段也未要求 wait，故不影响判定。

## 4. 覆盖表

| 要求维度 | 覆盖场景 | 证据锚点 |
|---|---|---|
| 范围扩张（mid-task scope expansion） | holdout-02 | 追加 CAN + 缩到 40×30 mm + 压成本；`user_decision_pending` 两条 |
| 缓存失效（cache invalidation） | holdout-03 | `already_read` 旧 sha256 + 旧 `rules_version 2026-10-20.1`；期望 `already_read_stale` |
| 证据不足 / 缺数据（insufficient evidence） | holdout-04、holdout-05 | 现货/价格证据缺失→待查；制造文件导出不可用→`eda_unavailable` + `missing_evidence` |
| 用户明示禁止（explicit prohibition） | holdout-01、holdout-02、holdout-04 | 禁 EDA/联网/改图；原理图冻结；不碰工程/不下单 |
| 自主 vs 评审边界（autonomous vs review） | holdout-02、holdout-05 | 02：自主推进、禁止自动等待；05：用户显式要求缺证据即停 |
| 至少两个中文真实口吻 | holdout-01、03、04、05（4 个） | `intent.notes` 直接给中文原话 |
| 至少一个 `already_read` 旧 sha256/rules_version | holdout-03 | 见上 |
| 至少一个需要决定门（`required_approval_gates` 非空） | holdout-02、holdout-05 | `scope_change`+`mechanical_change`；`missing_evidence` |
| 至少一个 `budget_insufficient` + 小 `budget_chars` | holdout-04 | `budget_chars:1200` vs required ≈35319 chars |
| `must_include` 3–8 个真实路径 | 全部 5 个 | 5/5/6/5/6 个，脚本逐条校验存在 |
| `must_exclude` 2–6 个 | 全部 5 个 | 3/3/3/4/3 个，均为跨任务类型的明显越界文档 |
| `may_include` 不超过冻结上限 | 全部 5 个 | 每个场景 4 个，且与 must/exclude 不重叠 |
| `max_selected_bytes` 为 null | 全部 5 个 | 本阶段不度量实际选择字节 |

任务类型分布：`review_only`、`pcb_route`、`schematic_edit`、`bom_only`、`delivery_audit`（全部取自契约 §6.1 允许列表）。

## 5. 过度拟合 planner 的预期失败模式

1. **只按关键词扩充文档**：看到"原理图"就拉 `schematic-authoring.md`/`schematic-layout.md` 全套，导致 holdout-01 的 `must_exclude`（PCB/采购/SMT 文档）命中、`unrelated_bytes` 升高；或 holdout-04 为"BOM"顺带拉布线/热设计文档。
2. **把"用户已读"当缓存命中**：holdout-03 若只比较文件名/不比较 sha256 与目录版本，会漏掉 `already_read_stale` 并跳过重读，`required_unknown` 与 `must_include` 双失败。
3. **任何决策都变成等待**：holdout-02 若一有新范围就输出 `wait_user_approval`，或干脆把原理图也改掉，会命中 forbidden 动作或 must_exclude。
4. **缺证据时默认通过**：holdout-05 若在无 Gerber/钻孔/CPL 证据时仍给 PASS、且不产出 `eda_unavailable`/`missing_evidence`，是本任务书最想抓的"假绿"。
5. **预算按需裁剪 required**：holdout-04 若为满足 1200 字符把 required 裁空，会漏 `must_include` 且不产出 `budget_insufficient`。
6. **按场景编号/标题分支**：实现若对 `holdout-0x`、标题文字或中文原话写死特判，会在变形（同义表达、否定/条件变化、预算变小）下失效；本集刻意让同一维度出现在不同任务类型（范围扩张在 PCB 任务、缺证据在 BOM 与交付两类任务）以避免单点映射。

## 6. NOT RUN / 未验证（必须如实声明）

- **NOT RUN：模型/planner 行为**。没有运行 `plan`、`benchmark` 或任何实现，本文件不声称这些期望能被满足，也不声称 holdout 已通过。
- **NOT RUN：EDA / Connector / 真实工程**。没有连接 EDA、没有读写工程、没有导出 Gerber/CPL、没有执行 DRC。
- **NOT RUN：盲测**。设计者未读 dev 集与实现，但这是分离评阅阶段；不存在"实现完全未见过的场景"这一意义上的盲测保证。
- **NOT RUN：基准指标**。`selected_bytes`、`unrelated_bytes`、`required_recall`、`stable` 等指标未计算；`max_selected_bytes` 一律为 `null`，表示本阶段不度量。
- **NOT RUN：dev 集校验**。没有运行 `validate_scenarios.py` 的默认入口（那会校验 `dev.json`），只在自己的临时校验脚本里复用了它的通用 `_check_scenario` 函数来检查 holdout。
- **未验证：`already_read` 的旧 sha256 不是 git 历史证据**。`holdout-03` 中的两个 sha256 由占位文本的 SHA-256 计算（`design-hardware@0.8.1 snapshot: SKILL.md` 与 `... references/workflow.md`），仅用于构造"旧快照"以触发缓存失效；`rules_version 2026-10-20.1` 也是场景设定值，不是对某个历史发布的取证。仓库当前文件内容与版本未做任何改动。
- **未验证：`topics.json` 主题映射**。`must_include` 依据 `SKILL.md` 显式触发句与 references 原文推导，尚未与本任务实际 `catalog/topics.json`（另一并行交付物）对表；按独立性要求没有读取实现与目录文件，因此可能存在"文档有触发句但目录未映射"的差异，需要基准运行时再核对。
- **未验证：Python 3.10**。本机校验用 Python 3.13.15 完成；场景文件本身是纯 JSON，不依赖运行时语法，但未在 3.10 下重跑校验脚本。
- **门禁 token 命名已冻结**：contract §10.2 明确使用 `scope_change`（不是 `user_scope_change`）等 9 个 token，且 planner 只复制 `intent.user_decision_pending`、不自行推断。本文件按该冻结口径写 `scope_change`，`holdout-02` 的 `user_decision_pending` 与 `required_approval_gates` 各一处，二者一致；此前的命名歧义已由契约补充说明消除。

## 7. 本地校验记录（只写本工作树内的两个交付文件）

- `python -c "json.load(...)"`：通过；`schema`/`split`/`frozen` 与 5 个场景 id 正确。
- 枚举校验：`task_type`、`stage`、`required_unknown`、`forbidden_plan_actions`、`required_approval_gates` 全部落在契约允许集合内；`max_selected_bytes` 均为 `null`。
- 路径校验：`must_include ∪ must_exclude ∪ may_include` 共 31 条**去重路径**逐条 `os.path.isfile` 全部存在（相对仓库根）；无重复 id、无重复 must_include、must/exclude/may 三类互不重叠。
- 冻结口径校验：复用 `validate_scenarios.py` 的通用 `_check_scenario`（不加载 `dev.json`、不运行其 `main`）检查 holdout，结果为 0 个错误；覆盖 always 三件、门禁范围任务的 `design-gates.md`、`may_include` 上限、门禁 token 属于 `intent.user_decision_pending` 等规则。
- 字符数抽测（用于 holdout-04 预算论证）：`SKILL.md` 24988 chars、`workflow.md` 1986 chars、`evidence.md` 917 chars、`lcsc-sourcing.md` 4078 chars、`part-selection.md` 3350 chars，合计 35319 chars ≫ `budget_chars:1200`。
- 未写 `dev.json`、未改 `README.md`、未改 `SKILL.md`/references/脚本；除本目录两个交付文件外无工作树写入。
