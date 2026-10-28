# 独立评阅报告：skill-knowledge-audit（holdout、基准完整性与冻结产物）

- 评阅人：`scenario-holdout`（并行任务 D 的独立队友；**holdout 场景的设计者**）
- 评阅阶段：分离评阅（separated review），**不是盲测**。设计阶段未读 `dev.json`/`scenarios/README.md`、未写实现；本次作为评阅者首次读实现、基准与报告。
- 工作树：`hds-ska-worktree`，HEAD `9a951edc21481dc3ae91460acc11aa3e08a7be8a`（`feat/parallel-skill-knowledge-audit`）
- 环境：Windows，Python 3.13.15；运行设置 `PYTHONDONTWRITEBYTECODE=1`，所有输出只写 `%TEMP%` 或 `%TEMP%` 下的 `easycirq` 副本；工作树内只新增本文件（`git status --porcelain` 只显示既有未跟踪目录）。
- 评阅对象（实际读取）：`bench.py`/`plan.py`/`cli.py`/`catalog/topics.json`；`tests/skill_knowledge_audit/{test_benchmark,test_cli}.py`；`scenarios/holdout.json`、`holdout-rationale.md`、`validate_scenarios.py`；`results/main.json`、`results/{scan,rules}.json`、`results/plans/*`；`docs/parallel-skill-knowledge-audit/{contract,cli,source-baseline,report,acceptance-matrix}.md`；`easycirq/SKILL.md` 及 holdout 期望相关 references。
- **评阅期间产物在变化（如实记录）**：开始评阅（00:13:52）时 `report.md`/`acceptance-matrix.md` **不存在**，按 Lead 指示用工具 + `results/main.json`；`report.md`（00:20:10）、`acceptance-matrix.md`（00:21:18）、`recommendations.md`、`integration-proposal.md`、`handoff-current.md` 与 `contract.md` 修订（00:21:35，21,181→23,946 B，新增 §10 M1–M3 冻结补充）在评阅过程中出现；`results/main.json` 也被重写（见 F11）。本报告区分"运行当时"与"00:24 后的最终复核"两套数字。
- 独立性限制：对 holdout 场景本身是**作者自评**；对 `plan.py`/`bench.py`/`topics.json`/基准/报告的评阅独立于实现作者。dev 场景文件未读，但为泄漏/重合核对读取了派生结果 `main.json` 与 `results/plans/dev-07-plan.json`。

## 1. 直接回答 Lead 的问题

| 问题 | 结论 | 依据 |
|---|---|---|
| holdout 泄漏（id/措辞/期望清单硬编码） | **未发现实质泄漏**；有两处调参风险声明/计划重合，见 F9、§2.5 | §2.5 |
| holdout 期望是否可从 `SKILL.md`/references 辩护 | **总体可辩护**；`always`/`design-gates` 已由 contract §10.1/§10.2 冻结（不再只是 catalog 口径）；弱项与错项见 F2/F3/F9 | §2.2、§3 |
| 基准是否真的检查它声称的东西 | **核心失败语义真实**（缺 must、禁读、禁动作、缺 unknown/门禁均退出 1；非法输入退出 2）；**预算 incomplete 是否失败由场景 `required_unknown` 决定**（contract §10.5，属设计而非疏漏，见 F5）；holdout/数量下限仅 flag 强制（F6） | §2.3、F5、F6 |
| `eda_available=false` 是否避免 EDA 动作 | **holdout-01/04/05 均无 `read_eda`/`write_eda`** ✅；发现 schematic 任务在 EDA 不可用时不产出 `eda_unavailable`（F1） | §2.4、F1 |
| 自主 intent 是否避免自动 `wait_user_approval` | 5 个 holdout 计划均无自动 wait ✅；实现只在 `before_*` 门加 wait（contract §10.2 已冻结该语义），因此 holdout-02 的禁止项**结构上不可能被违反**（F4） | §2.4、F4 |
| 冻结结果可复现 | 重新跑 holdout，5 个 `plan_digest` 与**现行** `results/main.json` 完全一致 | §2.1 |
| `report.md` 数字可核对 | 大部分可核对（309/2480/67/0/16、闭包 263,026 B、规则 12/10/400/200/16、20 场景、7/7 变形、52 tests、5 PASS）；**3 处不一致/缺口**见 F8 | §2.6 |

## 2. 实际运行记录（命令、退出码、关键输出）

### 2.1 真实 CLI benchmark（holdout）

```bash
# 工作目录：easycirq/scripts；输出在 %TEMP%
python -m skill_knowledge_audit benchmark --root .. --split holdout --out %TEMP%\ska-holdout-<uuid>.json
```

运行当时（约 00:15）：`EXIT=0`；`{total:5, dev:0, holdout:5, passed:5, failed:0}`；`required_recall:1.0`；`missing_critical_total:0`；`forbidden_selected_total:0`；`forbidden_actions_total:0`；`missing_approval_gates_total:0`；`missing_required_unknown_total:0`；`stable_scenarios:5`；`unrelated_bytes_total:45,126`；`duration_ms:4,932.5`。

最终复核（00:24 后的 `results/main.json`，27,408 B，含 `source/tool/transforms`）：`{dev:15, holdout:5, total:20, passed:20}`、`ok:true`、`required_recall:1.0`、`stable_scenarios:20`、`unrelated_bytes_total:194,520`、`transforms.ok:true`（7/7，scenario=dev-01）、`duration_ms:2,576.4`。**本次重跑的 5 个 holdout digest 与现行 main.json 逐一相同**（`d8028b83…`、`1a9dc9c3…`、`664923fb…`、`c8538134…`、`df69f5ea…`）。

逐场景（重跑，最终复核一致）：

| 场景 | digest | budget_status | selected_bytes | unrelated_bytes | actions | gates |
|---|---|---|---|---|---|---|
| holdout-01 | `d8028b83…` | within | 81,996 | 0 | offline_analysis, read_skill | — |
| holdout-02 | `1a9dc9c3…` | **incomplete** | 233,554 | 38,690 | read_eda, read_skill, write_eda | scope_change, mechanical_change |
| holdout-03 | `664923fb…` | **incomplete** | 117,074 | 0 | offline_analysis, read_skill, write_eda | — |
| holdout-04 | `c8538134…` | **incomplete** | 74,321 | 0 | offline_analysis, read_skill | — |
| holdout-05 | `df69f5ea…` | within | 142,594 | 6,436 | offline_analysis, read_skill | missing_evidence |

### 2.2 逐场景 `plan` CLI（工作目录 `easycirq/scripts`）

```bash
python -m skill_knowledge_audit plan --root .. --intent %TEMP%\<id>-intent.json --out %TEMP%\<id>-plan.json
```

| 场景 | exit | ok | required / required_chars / limit | unknown | 备注 |
|---|---|---|---|---|---|
| holdout-01 | 0 | true | 5 / 38,018 / 60,000（within） | — | required 恰为 5 个 `must_include`；无 EDA 动作 |
| holdout-02 | **1** | **false** | 14 / **130,048** / 90,000（incomplete） | budget_insufficient | F2；report.md 已披露该缺口 |
| holdout-03 | **1** | **false** | 6 / **64,267** / 40,000（incomplete） | already_read_stale, cache_invalidated, budget_insufficient | F2：**报告未披露**；`write_eda` 允许但无 `read_eda`（F1） |
| holdout-05 | 0 | true | 10 / 75,181 / 200,000（within） | eda_unavailable | gates=[missing_evidence]；无 wait 动作 |

### 2.3 测试

```bash
python -m unittest tests.skill_knowledge_audit.test_benchmark   # 9 tests, OK, EXIT=0 (27.3 s)
python -m unittest tests.skill_knowledge_audit.test_cli         # 8 tests, OK, EXIT=0 (13.4 s)
python -m unittest discover -s tests/skill_knowledge_audit -t . # 52 tests, OK (skipped=1), 42.0 s  ← 与 report.md 声明一致
python easycirq/scripts/skill_selftest.py                # 5 PASS / 0 FAIL / 0 NOT RUN, EXIT=0 ← 与 report.md 一致
```

### 2.4 对抗式变异（复制 holdout 到 `%TEMP%`，逐项修改，`--scenarios <temp 文件> --split holdout`）

| 变异 | 命令要点 | exit | 关键证据 |
|---|---|---|---|
| A：`must_include` 改成不存在文档 | `benchmark --root .. --scenarios mut-a.json --split holdout --out …` | **1** | `pass:false`，`missing_critical:["references/not-a-real-doc.md"]` |
| B：`forbidden_plan_actions:["read_skill"]`（计划确会发出） | 同上 | **1** | `forbidden_actions:["read_skill"]` |
| C：`must_exclude += references/review.md`（计划确会选中） | 同上 | **1** | `forbidden_selected:["references/review.md"]` |
| D：`required_unknown:["not_a_contract_code"]` | 同上 | **2** | `AuditError: holdout-01: unknown required_unknown code`（stderr + stdout JSON） |
| E：holdout-01 `budget_chars:800` | 同上 | **0** | `ok:true, pass:true`，但计划 `budget_status:"incomplete"`；与 contract §10.5 一致（由 `required_unknown` 决定是否失败），但说明 `ok` 不等于计划完整（F5） |
| F：holdout-01 `required_unknown:["eda_unavailable"]`（计划不产出） | 同上 | **1** | `missing_required_unknown:["eda_unavailable"]` |
| G：holdout-01 `required_approval_gates:["missing_evidence"]`（计划不产出） | 同上 | **1** | `missing_approval_gates:["missing_evidence"]` |

结论：**核心失败语义真实存在**，基准不是"永远 PASS"。

补充实验：

- 仅 dev 的临时场景目录：`benchmark --scenarios <tempdir 只含 dev.json>` → `EXIT=0, ok:true, total 15, holdout 0` → holdout/18 下限只在 `--require-holdout`/`--require-18` 下强制（F6）。
- holdout 变形：`benchmark --root .. --split holdout --transforms --out %TEMP%\…` → `EXIT=0`，`transforms.scenario:"holdout-01"`，7/7 `ok:true`。
- 边界计划：`schematic_edit` + `eda_available:false` → `EXIT=0, unknown:[]`；`schematic_new` + `eda_available:false` → `EXIT=0, unknown:["domain_unspecified"]`；两者**都没有 `eda_unavailable`**（F1）。`before_route` gate 的计划在 `autonomous_authorized:true/false` 下**都**含 `wait_user_approval`（F4）。
- 扫描根内输出隔离（contract §10.6 声称"`--out` 若落在根内会自动排除并记录，二次扫描不得自我污染"）：把 `easycirq` 复制到 `%TEMP%`，`plan --root <副本> --format both --out <副本>\reports\bom-plan.md` → `EXIT=0`；随后 `scan --root <副本>` → `files:310`（基线 309）、`excluded_outputs` **不含** `bom-plan.md`、`bom-plan.md` 被当作源文件扫描 → **该契约声明未实现于 `plan`**（`cli.py:120-138` 只有 `cmd_scan` 传 `exclude_abs`；`cmd_plan`/`cmd_benchmark` 在 `cli.py:141-170,173-208` 未传）。见 F10。

### 2.5 泄漏与来源核查

- 在 `easycirq/scripts/skill_knowledge_audit/**` 与 `tests/**` 搜索 `holdout-0[1-5]|dev-0[0-9]`：除 `validate_scenarios.py`（只约定 dev id 顺序）、`bench.py/cli.py` 的通用 split 字符串外，**无场景 id**；`test_benchmark.py:39` 也断言包内 `.py` 不含场景 id。
- 搜索 holdout 中文特征短语（"缩板框/限流电阻/配齐/导不出来/上下文很小/别连 EDA/客户要求增加/40×30"）：命中仅为无关的 `docs/round5/*.py` 旧评测脚本与 holdout 自身文档；catalog/实现中无场景措辞。
- `catalog/topics.json`（1,019 行）通读：关键词均为通用领域词（CAN/贴片/图面/门禁等），无 holdout id/期望清单；但 `topics.json:5` 声明 "reviewed against 20 scenarios"（F9）。
- 计划重合：20 个场景中 `dev-04=dev-05`、`dev-07=holdout-04`、`dev-09=holdout-05`（digest 相同）；`results/plans/dev-07-plan.json` 与 `holdout-04-plan.json` 的 selected 路径逐一相同（F9）。
- SKILL.md 行号引用抽查：`topics.json` 20 处 `SKILL.md L###`（L90/122/134/145/149/150/154/155/156/164/165/167/172/174/180/200/205/226/231/296）**逐一与原文相符**；`source-baseline.md` 的 4 个关键 SHA-256 与字节数（SKILL.md 50,163 B、workflow 5,240 B、evidence 2,433 B、design-gates 47,186 B）**全部一致**；夹具 16 对（`cli.md:16`、contract §5.4 要求 ≥12）。

### 2.6 `report.md` / `acceptance-matrix.md` 交叉核对（评阅期间出现，spot-check）

已逐项核对的声明（全部与 `results/*.json` 一致）：

- `scan`：309 `.md`、2,480 链接、67 显式必读、失效路径/锚点 0（`counts.errors:0`）、结构警告 16（`anchor_prefix_match 15` + `anchor_compat_match 1`）；`scan.md` 7,584 行。
- 必读闭包：17 文件、字节 263,026（= 7,049,351 的 3.7%）；引用环 15（最大 SCC 184）、孤立 7、重复主题 1 组。
- `rules`：12 条已审规则、10 对已审关系、`machine_candidates:400`、`candidate_tensions:200`、`confirmed_conflicts:0`、夹具 16/16（`accuracy:1.0`）。
- `benchmark`：20 场景全过、召回 1.0、禁止项 0、稳定 20/20；选中/全量比 **0.87% / 2.10%（中位）/ 3.42%**；变形 7/7。
- 测试与自检：52 tests OK（1 skipped）、`skill_selftest` 5 PASS / 0 FAIL（本报告 §2.3 实测）。

发现的不一致/缺口：

1. `report.md` §1/§2（"必读闭包 17 个文件、最大深度 3"与表格"17 / 3"）与 `results/scan.json` 的 `graph.required_depth = 2` **不一致**，也与修订后 contract §10.3"深度 ≤2"不一致——需要统一"深度=边数还是层数"并写清。
2. `report.md` §5 只披露 **holdout-02** 的预算缺口（130,048 > 90,000），**未披露 holdout-03**（64,267 > 40,000，实测 `plan` 退出 1）；同一类不一致应在报告里一并列出（F2）。
3. `report.md` §5 "基准完整计划耗时约 2.9 s" 与现行 `main.json` 的 `duration_ms:2,576.4` 有差（更早一次运行的值）；属"约数/旧值"，但报告未标注取样时间，且 `main.json` 在评阅期间被重写（F11）。

## 3. 发现（按严重性）

### F1（中）schematic 任务在 EDA 不可用时缺少 `eda_unavailable`，且写动作缺读动作

- 观察：`schematic_edit` + `--no-eda` → `EXIT=0, unknown:[]`；`schematic_new` + `--no-eda` → `EXIT=0, unknown:["domain_unspecified"]`；两者 actions 都只有 `[offline_analysis, read_skill]`，均无 `eda_unavailable`。
- 契约依据：contract §6.2 第 6 条把"EDA 不可用导致无法回读"列为信息不足，应进 `unknown`（`eda_unavailable`）；同目录 `pcb_layout/pcb_route/full_product/delivery_audit` 在 EDA 不可用时都会产出该 code（`plan.py:328-333`；`topics.json` 的 `offline.pcb`/`pcb.execution`），唯独 schematic 系列没有。
- 根因：`plan.py:21-24` 中 `WRITE_TASKS` 含 `schematic_new/schematic_edit`，但 `EDA_TASKS` 只含 `pcb_layout/pcb_route/full_product`；于是 schematic 任务 `eda_required=false`、无 `read_eda`，而 `writes_allowed=true`（`plan.py:450-459`）。holdout-03 的计划即 `[offline_analysis, read_skill, write_eda]`：只授权写、不要求读。
- 与源文档冲突：`SKILL.md:261` 要求"先形成源数据/变更计划，再执行和回读……read → 对账 → 只补差异 → 回读"；`SKILL.md:161` 在 EDA 执行入口写明"先读后写"。
- 影响：holdout/dev 都未覆盖"schematic + EDA 不可用"这一组合，基准全绿但该路径行为未验证。建议：把 `schematic_*` 纳入 `EDA_TASKS` 并加 `read_eda`，或明确"EDA 不可用时 schematic 只能离线计划"并产出 `eda_unavailable`。

### F2（中）holdout-02/03 预算缺口：02 已披露，03 未披露

- 实测：holdout-02 required **130,048** > 90,000（report.md §5 已作为已知覆盖缺口披露）；holdout-03 **64,267** > 40,000（`plan` `EXIT=1, ok:false`，`unknown` 含 `budget_insufficient`；**report.md 未列**）。
- 契约现状：contract §10.5 明确"预算 `incomplete` 由场景 `required_unknown` 决定是否失败"，故两者 benchmark 仍 `pass:true` 是**设计如此**，不是虚假通过；但 `holdout-rationale.md` 未声明 03 也会 incomplete，report 只披露 02，读者会误以为只有 02 有问题。
- 影响：holdout-04 "`budget_insufficient`" 的覆盖不再唯一（02/03 也产出），预算维度判别力下降。
- 建议（未修改文件）：holdout-02 预算提到 ≥ 140,000、holdout-03 ≥ 70,000，或把两处缺口都写进 report 与 rationale。

### F3（低）holdout-05 rationale 关于 `wait_user_approval` 的措辞超出实际行为

- `holdout-rationale.md` §3 holdout-05 写"本场景允许/期待 `wait_user_approval` 语义"，但 contract §10.2 已冻结"wait 只在 `before_*` 门加入"（`plan.py:449`），`missing_evidence` 不产生 wait；实测该计划 actions 无 wait。期望字段未要求 wait，基准不受影响；建议 rationale 改为"允许、不要求；以 decisions_required 表达"。

### F4（低）holdout-02 的 `forbidden_plan_actions:["wait_user_approval"]` 结构上不可违反；autonomy 标志无行为影响

- 实测：同一 `pcb_route` intent 在 `autonomous_authorized:true/false` 下 actions/gates 完全相同；wait 只由 `before_*` token 触发（`plan.py:449`），holdout-02 的 gate 是 `scope_change/mechanical_change`。
- 影响：该 forbidden 项是"空检验"；`autonomous_authorized` 目前只是元数据（contract §10 未要求它改变计划）。若要真正测边界，需要"`before_*` 门 + 自主授权"的组合并定义预期（属待定设计，不是实现 bug）。

### F5（低，文档沟通）benchmark 的 `ok/pass` 不表示计划完整

- 代码：`bench.py:147-148` 只聚合 `missing_critical/forbidden_selected/missing_unknown/forbidden_actions/missing_gates/over_budget`；`plan["ok"]`、`budget_status=="incomplete"` 不参与 pass。
- 实测：变异 E（budget 800）→ `ok:true, pass:true` 但计划 incomplete；`main.json` 在 4/20 场景 incomplete（`dev-14, holdout-02/03/04`）时仍 `ok:true`。
- 契约现状：contract §10.5 已把"预算 incomplete 是否失败"交给场景 `required_unknown`，**属设计**；问题只在结果可读性：`ok:true` 未同时给出"n 个计划 incomplete"，易被读成"全部计划完整"。建议加 `budget_incomplete_total` 或在 `limitations` 明写。

### F6（低）holdout/场景数量下限只在显式 flag 下强制

- `cli.py:189-204`：`--require-holdout`（<4 失败）、`--require-18`（<18 失败）为 opt-in；实跑"只含 dev.json 的临时目录"→ `EXIT=0, ok:true, holdout:0`。`cli.md`/`source-baseline.md` 的推荐命令带 flag，但结果不记录是否使用。建议默认强制或把 flag 状态写入结果。

### F7（低）结果字段名与契约 §7.2 不一致；稳定性只比较选择集合

- 字段名：契约 §7.2 写 `unknown_expected_missing`、`baseline_all_markdown_bytes`；实现为 `missing_required_unknown`（`bench.py:159`）、`all_markdown_bytes`（`bench.py:165`）。
- 稳定性：`stable` 比较两次 `build_plan` 的 selected 路径集合 digest（`bench.py:169,190-193`），不比较 unknown/gates/reasons/预算；未做对抗实验（NOT RUN）。
- `load_scenarios`（`bench.py:86-112`）不校验期望路径存在：路径笔误会以 `missing_critical` 退出 1，而非输入错误退出 2；冻结集有 `test_benchmark.py:30-37` 兜底，自定义场景没有。

### F8（低，文档一致性）`report.md` 的 3 处不一致/缺口

见 §2.6：必读闭包"最大深度 3" vs `required_depth:2`（且 contract §10.3 写"深度 ≤2"）；holdout-03 预算缺口未披露；耗时"约 2.9 s"未与现行 `main.json`（2,576.4 ms）对齐。`acceptance-matrix.md` 只做了抽样浏览（未逐项复核），`recommendations.md`/`integration-proposal.md`/`handoff-current.md` 未评阅。

### F9（低，holdout 质量）2/5 holdout 计划与 dev 重合；unrelated_bytes 偏大；部分期望依赖策略常量

- 重合：`holdout-04=dev-07`、`holdout-05=dev-09`（selected 集合逐一相同，digest 相同）；`dev-04=dev-05`。说明 2 个 holdout 主要复测 catalog 已覆盖行为。
- `unrelated_bytes`：holdout-02 38,690（6 份 catalog 主题/依赖带入但不在 `may_include` 的文档）、holdout-05 6,436；契约 §7.2 只当指标，但显示 `must/may_include` 低估了 required 闭包。
- `topics.json:5` "reviewed against 20 scenarios" 声明 catalog 审查覆盖了 holdout，无法证明 holdout 期望相对 catalog 未经调参；不过 contract §10.1/§10.2 已把 always/门禁/token 冻结，`holdout-rationale.md` 也如实写了该口径对齐，故属"已披露的独立性限制"而非隐瞒。
- 相对缓解：holdout-01（38,018 chars）、holdout-02（14 required）等场景仍覆盖 dev 未覆盖的组合；holdout-03 是唯一 `already_read_stale` 场景。

### F10（中，契约偏差，已实测）`plan` 的 `--out` 落在扫描根内时不自动排除、会造成二次扫描自污染

- 实测（`%TEMP%` 副本，未改工作树）：`plan --root <copy> --format both --out <copy>\reports\bom-plan.md` → `EXIT=0`；随后 `scan --root <copy>` → `files:310`（基线 309）、`excluded_outputs` 不含该文件、`bom-plan.md` 作为源文件被扫描。
- 契约冲突：contract §10.6 明确"`--out` 若落在根内会自动排除并记录，二次扫描不得自我污染"；实现只有 `cmd_scan` 传 `exclude_abs`（`cli.py:120-138`），`cmd_plan`/`cmd_benchmark`（`cli.py:141-170,173-208`）未传。`cache-out` 同理未检查（未实测，静态判断）。
- 影响：若用户按示例把 plan 输出写进 `easycirq`（并非推荐路径，但契约承诺支持），下一次 `scan`/`plan` 会把该报告当成 Skill 文档，可能引起结论漂移。建议修 `cli`（对 plan/benchmark/cache 输出计算并排除、写入 `excluded_outputs`），或把 §10.6 改成"仅 `scan` 支持"。

### F11（中，冻结产物稳定性）评阅期间 `results/main.json`、`contract.md`、`report.md` 被重写

- 时间线（文件 mtime/大小）：`report.md` 00:20:10；`recommendations.md` 00:20:49；`acceptance-matrix.md`、`integration-proposal.md` 00:21:18；`contract.md` 00:21:35（21,181→23,946 B）；`handoff-current.md` 00:22:05；`results/main.json` 初读 27,063 B → 现 27,408 B（00:24:12，新增 `source/tool` 字段）；00:23:5x 曾观察到一版 `main.json` **缺 `transforms` 键**，00:24:12 版本又恢复 7/7 变形结果。仓库根 00:22:11/00:22:30 曾出现 `_be.txt`(0 B)/`_bo.json`(28,449 B)，00:24 前已消失（非本评阅产生；我的输出均在 `%TEMP%`）。
- 影响：`report.md`/`source-baseline.md` 把 `main.json` 当冻结证据，但该文件在评阅窗口内至少两版；若最终交付后再被重写，"冻结"结论无法复现核对。当前最终版 digest 与我重跑一致（§2.1），**内容可复现**，但缺少 SHA-256 钉扎与生成时间记录。
- 建议：在 `report.md`/`handoff-current.md` 记录每个 `results/*.json` 的 SHA-256 与生成命令/时间；冻结后不再重写；若必须重跑，更新哈希并说明差异。

## 4. 与契约逐条对照（摘要）

- §6.2 unknown codes / actions / gates 枚举：holdout 使用的 `scope_change/mechanical_change/missing_evidence/eda_unavailable/already_read_stale/budget_insufficient` 均合法（`contract.md` §10.2 已冻结 token 列表，`user_scope_change` 的旧写法不再有效；`holdout-rationale.md` 里"待确认命名差异"一段因此已过期，属文档 staleness，不影响 holdout 数据）。
- §6.3 缓存失效：`already_read_stale` + `cache_invalidated` 实测出现（holdout-03），符合"文件变化/目录版本变化都失效"。
- §6.4 预算：required 不裁剪、`incomplete` + `uncovered` 实测正确；是否判失败由 §10.5 与场景 `required_unknown` 决定。
- §7.1 schema/frozen/20 场景/≥4 holdout/must 缺失→失败/forbidden 命中→失败：**实测符合**（§2.4 变异 A/B/C/F/G）。
- §7.2 指标：除 F7 两处命名漂移外均输出；全量基线策略与"减少阅读≠提速"免责声明在 `limitations/not_proof` 中。
- §7.3 变形：7 项在 dev-01（`main.json`）与 holdout-01（本次运行）均 `ok:true`；负例实测通过（D→2，A→1）。
- §10.6 输出隔离：**未实现于 plan/benchmark**（F10）；§10.3 闭包深度 ≤2 与 report 的"3"不一致（F8）。
- §9 验收最低线：CLI 可运行、真实扫描报告、12 对夹具、18+ 场景（20）、0 关键保护遗漏、测试通过——本次实测均满足；PR 创建未评阅（未查 git remote/PR 状态）。

## 5. 残余限制与 NOT RUN

- **NOT RUN：模型/Agent 行为**。未运行模型会话，不证明"AI 会按计划加载/遵守"，也未测阅读 token 或等待次数变化。
- **NOT RUN：EDA / Connector / 硬件**。未连接 EDA、未读写工程、未导出 Gerber/CPL/DRC；不证明任何硬件结果或画板速度。
- **NOT RUN：Python 3.10**。全部运行在 3.13.15；3.10 只有静态声明（`cli.md:100-101`、`source-baseline.md:13-14`）。
- **NOT RUN：`--cache-out` 的输出隔离**；只实测了 `plan --format both --out`（F10）。
- **NOT RUN：稳定性对抗变异**（同选择、不同 unknown/gates 的两轮是否误判 stable）；只确认同一 intent 两次 build 的选择集合一致、跨进程 digest 与冻结结果一致。
- **NOT RUN：`report.md` 之外的报告**。`acceptance-matrix.md` 仅抽样浏览；`recommendations.md`/`integration-proposal.md`/`handoff-current.md`/`rule-review.md` 未逐条评阅（只浏览关键词）。
- **NOT RUN：PR/CI/git 远端状态**；未查 PR 是否创建、CI 是否通过。
- 独立性限制：holdout 作者自评 holdout；dev 场景文件未读，但为泄漏/重合核对读取了派生结果（`main.json`、`results/plans/dev-07-plan.json`）。
- 评阅期间工作树被并发写入（F11）；本报告"最终复核"以 00:24 后文件状态为准，若之后再次改动需重跑 §2.1/§2.6。

## 6. 结论（verdict）

**Independent review: PASSED WITH CAVEATS（通过，但需修复/如实标注以下问题）**

- 通过部分：无 holdout id/措辞/期望清单硬编码泄漏；基准关键失败语义真实（变异 A/B/C/F/G 退出 1、D 退出 2）；holdout 5/5 通过、0 关键遗漏、跨进程与冻结结果 digest 一致；`eda_available=false` 的三个 holdout 计划无 EDA 动作；52 tests OK（1 skipped）、self-test 5 PASS；`report.md` 的大部分数字可核对（309/2480/67/0/16、闭包 263,026 B、规则 12/10/400/200/16、20 场景、7/7 变形）；SKILL 行号与基线哈希可核对。
- 需处理（按优先级）：
  1. **F10**：`plan`/`benchmark`（及 `cache-out`）的输出落在扫描根内时未按 contract §10.6 排除/记录；已用 `%TEMP%` 副本实测自污染（files 309→310），需修 CLI 或收窄契约措辞。
  2. **F1**：`schematic_new/schematic_edit` + EDA 不可用时无 `eda_unavailable`，且写动作缺读动作（与 contract §6.2 第 6 条、`SKILL.md:161/261` 不一致）；需修实现或记为已知限制。
  3. **F2/F8**：holdout-03 的预算缺口未在 `report.md`/`holdout-rationale.md` 披露（holdout-02 已披露）；`report.md`"闭包深度 3"与 `required_depth:2`/contract §10.3 不一致；建议下次冻结时统一（改预算或补披露）。
  4. **F11**：`results/main.json`、`contract.md`、`report.md` 在评阅窗口内被重写；当前内容与重跑一致，但需在交付前做一次最终重跑并记录 `results/*.json` 的 SHA-256/生成时间，冻结后不再改写。
- 低优先级（文档/表述）：F3（holdout-05 rationale 的 wait 措辞）、F4（holdout-02 禁止项结构性不可违反）、F5（`ok` 与预算完整性的可读性）、F6（默认不强制 holdout/18 下限）、F7（结果字段名对齐契约 §7.2）、F9（holdout/dev 计划重合与 `topics.json` 出处声明）。

## 7. Post-review addendum (Lead fixes verified 2026-10-28 00:26–00:30)

> 本节为评阅人在 Lead 修复后追加的复审记录。§1–§6 是首次评阅的原始记录，**保持原样不回写**；本节只更新"修复后实测状态"与最终 verdict。复审命令均只读运行，输出写 `%TEMP%`；输出隔离实验使用 `%TEMP%` 下的 `easycirq` 副本。

### 7.1 复审时间与代码/产物版本

- 修复代码 mtime：`plan.py` 00:24:59；`bench.py`、`cli.py` 00:25:33。
- 产物 mtime：`catalog/topics.json` 00:26:28；`results/main.json` 00:27:24（28,694 B，SHA-256 `fb2b1737efaec7ff078fdfdafb4178968c9b4e0d0a1475d8d9974aa70556dc38`）；`report.md`/`cli.md`/`handoff-current.md` 00:28:46、`contract.md`/`acceptance-matrix.md` 00:28:58。
- 复审实测窗口：00:26–00:30（Python 3.13.15，`PYTHONDONTWRITEBYTECODE=1`）。

### 7.2 复审命令与结果（exit code 均为实测）

| # | 命令（工作目录 `easycirq/scripts`） | exit | 关键结果 | 对应发现 |
|---|---|---|---|---|
| 1 | `plan --root .. --task schematic_edit --stage schematic --no-eda --out %TEMP%\…` | **0** | `actions:[offline_analysis, read_skill]`、`eda_required:false`、`writes_allowed:false`、`unknown:["eda_unavailable"]` | **F1 已修** |
| 2 | `plan --root .. --task schematic_edit --stage schematic --eda --out %TEMP%\…` | **0** | `actions:[read_eda, read_skill, write_eda]`、`eda_required:true`、`writes_allowed:true`、`unknown:[]` | **F1 已修** |
| 3 | `benchmark --root .. --split holdout --out %TEMP%\…` | **0** | 5/5 pass、recall 1.0、`unknown_expected_missing_total:0`、`stable_scenarios:5`；新 `budget_incomplete_total:3`（holdout-02/03/04）、`plan_ok_false_total:3`；行字段已含 `unknown_expected_missing`/`baseline_all_markdown_bytes`/`selected_vs_baseline_ratio`；limitations 含 "ok/pass does not mean every plan is budget-complete" | **F5 已缓解 / F7 已修** |
| 4 | `benchmark --root .. --scenarios <%TEMP% 仅 dev.json 目录>`（默认 `--split all`） | **1** | `ok:false`、`requirements:{enforced:true, min_scenarios:18, min_holdout:4}`、`holdout_error` + `scenario_count_error` 均出现 | **F6 已修** |
| 5 | 变异 A：`must_include` 改为不存在路径，`benchmark --scenarios <副本> --split holdout` | **2** | `AuditError: holdout-01: expected.must_include path does not exist` | **F7 输入校验已修** |
| 6 | 变异 B：`forbidden_plan_actions:["read_skill"]`，同上 | **1** | `forbidden_actions:["read_skill"]` | 核心失败语义未回归 |
| 7 | `python -m unittest discover -s tests/skill_knowledge_audit -t .` | **0** | **53 tests OK (skipped=1)**（首评 52 项，新增 1 项） | 修复未破坏测试 |
| 8 | `%TEMP%` 副本：`plan --format both --out <副本>\reports\bom-plan.md`，随后独立 `scan --root <副本> --out %TEMP%\…` | 0 / 1 | `plan` 成功；随后 `scan` `files:310`（基线 309）、`excluded_outputs` **不含** `bom-plan.md`、该 `.md` 仍被当作源文件扫描 | **F10 部分修复**（见 7.3） |
| 9 | 读取 `results/main.json`（00:27:24 版） | — | 20/20 pass、recall 1.0、stable 20、`budget_incomplete_total:4`（`dev-14` + `holdout-02/03/04`）、`plan_ok_false_total:4`、`requirements.enforced:true`、`transforms.ok:true`；与 `report.md` §5/`acceptance-matrix.md` 新数字一致 | F5/F8 产物对齐 |

### 7.3 原发现状态更新

| 发现 | 复审状态 | 证据 |
|---|---|---|
| F1 schematic EDA-off 缺 `eda_unavailable`、写缺读 | **已修（verified）** | 7.2 #1/#2；`plan.py:23` `EDA_TASKS` 已含 `schematic_new/schematic_edit` |
| F2 holdout-02/03 预算缺口 | **保持为已披露 known gap（holdout 未改）** | `report.md` §5 与 `acceptance-matrix.md` 已同时披露 02/03；`main.json.metrics.budget_incomplete_scenarios` 列出 `dev-14, holdout-02, holdout-03, holdout-04` |
| F3 holdout-05 rationale 的 wait 措辞 | **已修正（本文件同轮）** | `holdout-rationale.md` 改为"允许、不要求"并说明 contract §10.2 只对 `before_*` 门加 wait |
| F4 holdout-02 禁止项结构性不可违反 | **仍为观察项（非 bug）** | contract §10.2 冻结"wait 只来自 `before_*`"；保留为测试覆盖建议 |
| F5 `ok/pass` 不表示预算完整 | **已缓解（verified）** | 7.2 #3/#9；`bench.py` metrics + limitations + report/acceptance 新表述 |
| F6 默认不强制 holdout/18 下限 | **已修（verified）** | 7.2 #4；`cli.py` `auto_all` + `requirements` 字段 |
| F7 字段名/稳定性/路径校验 | **已修（verified）** | 7.2 #3/#5；`bench.py:160/166/167/171`（新字段与扩展到 selected+unknown+gates+actions 的 digest）、`bench.py:188-195`（期望路径不存在 → `AuditError` → exit 2） |
| F8 报告数字/产物 | **大部分已处理**：`report.md`/`acceptance-matrix.md`/`cli.md`/`handoff-current.md` 已更新；02/03 缺口已披露；`topics.json:5` provenance 已改为 "catalog informed by contract, dev scenarios and the holdout acceptance set (holdout is not blind and was not used to hardcode ids/answers)" | **残余**：`report.md:13/40` 仍写"必读闭包 17 个文件、最大深度 3"，而 `results/scan.json` 的 `graph.required_depth=2`、contract §10.3 写"深度 ≤2" → 深度口径仍不一致（首次评阅时已指出，本轮复核仍存在） |
| F10 `--out` 落在扫描根内 | **部分修复**：`cli.py` 新增 `_exclude_outputs`，`cmd_plan`/`cmd_rules`/`cmd_benchmark` 把输出传给扫描排除（同命令内不再自我污染） | **跨命令仍自污染**：7.2 #8 的独立 `scan` 仍读到先前 `plan` 写下的 `bom-plan.md`（files 309→310、`excluded_outputs` 不含它）。contract §10.6 "二次扫描不得自我污染"若指后续独立 `scan`，则仍未满足；建议收窄措辞（"同一命令内"）或增加输出清单持久排除 |
| F9 `topics.json` provenance / holdout-dev 重合 | **provenance 已修正**（见 F8 行）；计划重合（holdout-04=dev-07、holdout-05=dev-09）与 `unrelated_bytes` 仍为场景质量观察项 | `topics.json:5`；`main.json` digest |
| F11 冻结产物被重写/无哈希钉扎 | **部分处理**：`main.json` 已收敛为 00:27:24 版本（见 7.1 的 SHA-256），但 `report.md`/`handoff-current.md` 尚未记录 `results/*.json` 的 SHA-256 与生成时间 | 建议把 7.1 的 `main.json` SHA-256 写入 handoff/report，冻结后不再重写 |

### 7.4 更新后的 verdict

**Post-review verdict: PASSED WITH CAVEATS（修复经实测确认，仍有 2 项残余 + 1 项待钉扎）**

- 已确认修复：F1（schematic + EDA-off 现在产出 `eda_unavailable` 且无写动作；EDA 可用时含 `read_eda+write_eda`）、F5（预算/plan_ok 指标与 limitations）、F6（默认强制 ≥18 场景/≥4 holdout，`requirements` 记录）、F7（契约字段名、稳定性 digest 扩展、期望路径不存在 → exit 2）。全量测试 53 OK（1 skipped），holdout 仍 5/5 pass、0 关键遗漏。
- F2 作为已披露 known gap 接受（holdout 不变，避免事后调参；报告已同时披露 02/03）。
- 残余需 Lead 决定：**F10**（跨命令输出自污染 vs contract §10.6 措辞；建议收窄措辞或加持久排除）、**F8 残余**（`report.md` 闭包"深度 3" vs `required_depth=2`/contract §10.3 "≤2"）、**F11**（在 `report.md`/`handoff-current.md` 记录 `results/*.json` 的 SHA-256 与生成时间）。
- 原始 §1–§6 结论仍然有效：无 holdout 泄漏、基准核心失败语义真实、holdout 5/5 且可复现。本节不改变首次评阅对 F3/F4/F9 的判断。
