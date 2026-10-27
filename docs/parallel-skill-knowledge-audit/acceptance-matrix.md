# 验收矩阵（对照任务书 D1–D5 与工程质量要求）

状态：**PASS** = 有可运行证据；**PASS WITH CAVEAT** = 有证据但范围受限；
**NOT RUN** = 明确未做，不得宣称。证据路径均相对仓库根。

## 1. 边界与隔离

| 要求 | 证据 | 状态 |
|---|---|---|
| 独立 worktree/分支，固定 main SHA | `feat/parallel-skill-knowledge-audit` @ `9a951ed`；`source-baseline.md` | PASS |
| 只改允许目录 | `git status`：仅四个任务目录新增；主 SKILL/references/CI/docs 未改 | PASS |
| 只读 Skill，不操作 EDA/Connector/浏览器 | 工具无 subprocess/socket/urllib 导入；测试与命令均未调用 | PASS |
| 建议只写 proposal | `recommendations.md`、`integration-proposal.md`；无源文件补丁 | PASS |
| 不合并、不发布、不装客户端 | 只创建 PR；未执行合并/发布/安装 | PASS |

## 2. D1 知识图谱与引用审计

| 要求 | 证据 | 状态 |
|---|---|---|
| 扫描 Markdown/标题/锚点/相对链接/脚本/入口 | `scan` 输出 `files[].headings/links/script_refs`；309 文件/2480 链接 | PASS |
| 保留路径、行号、标题、哈希、扫描版本 | `files[].path/line/sha256`；`catalog_version` | PASS |
| 区分必读/条件/示例/背景/脚本/外链/未知 | `links[].role` + `role_evidence`；只有明确“先读/必须”才 required | PASS |
| 失效路径/锚点/大小写/越界/重复锚点/循环/孤立/过深/同主题 | `findings` + `graph.cycles/orphans/duplicate_topics/over_deep_required` | PASS |
| 符号链接不逃出根 | `symlink_escape`；单测覆盖（Windows 权限下跳过创建） | PASS WITH CAVEAT |
| 外链只记录不联网 | `external:true`、`external_verified:false`；无网络代码 | PASS |
| 占位路径不报坏引用 | `placeholder_link` info；测试覆盖 | PASS |
| 忽略声明有理由/精确对象/范围，不假绿 | `ska-ignore/v1` 校验；`ignored:true` 保留；测试覆盖无理由/通配拒绝 | PASS |
| JSON + Markdown 索引，可定位 | `results/scan.json`、`results/scan.md`（7,584 行） | PASS |
| 扫描前后源文件不变 | 测试 `tree_hashes` 前后一致；真实基线同样断言 | PASS |

## 3. D2 规则结构与冲突审计

| 要求 | 证据 | 状态 |
|---|---|---|
| rule schema 全字段 | `catalog/rules.json` 12 条；`rules` 输出；字段校验拒绝缺失/重复 ID | PASS |
| 确定性抽取 + 人工/模型审查区分 | `machine_rules_sample`（400 条，`machine_extracted`）vs `rules`（12 条 `maintainer_declared`） | PASS |
| 条件未知记 unknown，不编造 | 抽取器 `condition:"unknown"`；审查记录逐条条件 | PASS |
| 同范围相反/默认例外/新旧/证据/工具限制/审批/全量冲突检查 | `reviewed_relations` 10 对，分类覆盖 | PASS |
| 字符串相似/关键词只产生 candidate | `candidates` 200 条全部 `classification:"candidate"`；`confirmed_conflicts=0` | PASS |
| 真冲突列原文/重叠/场景/例外/建议 | `catalog/rules.json` relations 含 `evidence`/`overlap`/`scenario`/`exception`/`resolution` | PASS |
| 至少 12 对夹具，覆盖 12 类 | `fixtures/rule-pairs.json` 16 对；`fixtures.accuracy=1.0` | PASS |
| 不自动删规则、不以“更快”弱化完整性 | 仅 proposal；无源文件修改；建议均标“不改变工程保护”或“收紧” | PASS |
| 找到 0 冲突时报告“未发现”并保留候选/驳回 | `rule-review.md` §3 明确“未发现确定性冲突”+ 9 条驳回记录 | PASS |

## 4. D3 任务驱动最小阅读计划

| 要求 | 证据 | 状态 |
|---|---|---|
| intent 支持任务类型/授权/EDA/交付物/约束/阶段/缓存 | `plan` schema；`normalise_intent` 校验；CLI 覆盖参数 | PASS |
| 输出 required/conditional/optional/excluded/unknown + 原因 | `plans/*.json`；每项 `reasons`/`topic` | PASS |
| 不跳过身份/目标绑定/证据真实性保护 | `protect.workflow-evidence` 对所有非 knowledge 任务 required；`protected_constraints` | PASS |
| 纯 BOM 不读完整差分布线/热设计 | `dev-07`/`holdout-04`：5 个 required，排除 pcb-routing-details/thermal | PASS |
| 仅离线审查不连接 EDA、不生成写步骤 | `holdout-01`/`dev-08`/`dev-10`：无 read/write EDA，`writes_allowed=false` | PASS |
| 授权自主不自动等待；新增范围提示决策 | `dev-12` 无 wait；`dev-15`/`holdout-02` 产 decisions 不自动 wait；`dev-13` 用户显式 before_route 才 wait | PASS |
| 特定阶段只给阶段相关读物，后续阶段留入口 | `next_stage_entry`；pcb execution 主题按 stage 过滤 | PASS |
| 缓存绑定内容哈希/规则版本/任务范围，变化重算 | `already_read_stale`、`cache_invalidated`；测试覆盖哈希/版本变化 | PASS |
| 预算按字符/字节/区间报告，不把字符/4 当 token | `budget.token_estimate` 标注 `not a tokenizer`；不运行 tokenizer | PASS WITH CAVEAT |
| 预算不足列未覆盖要求并标 incomplete，不裁保护 | `dev-14`/`holdout-04`：required 不裁剪、`uncovered`、`incomplete` | PASS |
| 计划只是导航，不证明加载/遵守 | 所有 plan 带 `not_proof`；报告 NOT RUN | PASS |

## 5. D4 真实 Skill 报告与建议

| 要求 | 证据 | 状态 |
|---|---|---|
| 对固定基线跑真实工具 | `results/scan.json`、`rules.json`、`main.json`、`plans/` | PASS |
| 引用图/闭包/冲突/重复/失效/任务计划/缺口 | `report.md` §2–§5 | PASS |
| 建议含触发场景/原文/影响/变化/保护/验证 | `recommendations.md` R1–R10 | PASS |
| 最多 10 条高价值建议 + 完整机器清单 | 10 条；完整候选/关系在 `results/rules.json`、`rule-review.md` | PASS |
| 不虚构冲突，未发现就报告 | `confirmed_conflicts=0`；明确“未发现” | PASS |
| 结论来自实际读过的文件 | 引文逐条核到行；`rules` 证据不符退出 2 | PASS |

## 6. D5 冻结场景与可重复评测

| 要求 | 证据 | 状态 |
|---|---|---|
| ≥18 场景，覆盖 18 类情形 | 20 场景（15 dev + 5 holdout），见 `scenarios/README.md` 与 `holdout-rationale.md` | PASS |
| 每场景记录 intent/允许禁止/必要覆盖/unknown/动作/冻结哈希 | 场景 JSON 全字段；`frozen.git_sha/catalog_version` | PASS |
| 预期有理由，不照 planner 倒填 | 场景 `rationale` 由人工先写；holdout 独立设计 | PASS WITH CAVEAT（非盲测） |
| dev/holdout 分开，holdout ≥4 且不同措辞 | 15+5；holdout 由未读 dev 的评阅者设计 | PASS |
| 实现不写死场景编号 | 单测扫描包代码无场景 ID | PASS |
| 基准跑真实 CLI，指标齐全 | `benchmark` CLI；`results/main.json` 含 recall/遗漏/无关字节/稳定性/耗时/预算缺口 | PASS |
| 关键保护遗漏显式失败 | `missing_critical>0`、禁止动作/阅读、缺 unknown/门 → FAIL；单测构造失败 | PASS |
| 全量 vs 最小计划对比并说明基线性质 | `selected_vs_all_ratio`；`README`/`report` 明确 baseline 是策略 | PASS |
| 变形测试 8 类 | `transforms` 7 项（含排序/换行合并、背景链接、标题、哈希、同义、否定/条件、预算、外部修改） | PASS |
| 不相关变化不破坏必要覆盖 | 单测 `test_unrelated_document_changes...`；变形全 PASS | PASS |

## 7. CLI 与工程质量

| 要求 | 证据 | 状态 |
|---|---|---|
| `python -m` scan/rules/plan/benchmark；root/intent/rules/budget/out 参数 | `cli.py`；`cli.md` 示例 | PASS |
| stdout JSON 纯净，诊断 stderr | 所有命令输出单 JSON；CLI 测试断言 stdout 可解析且 stderr 为空 | PASS |
| 结构版本/源哈希/工具版本/确定性排序/原子输出/退出码 | 结果字段；排序；`atomic_write_text`；退出码测试 | PASS |
| 非法输入/抽取失败不沿用旧 PASS | 非法 JSON→2；证据不符→2；空规则→2；基准失败→1 | PASS |
| 输出不自我污染 | 输出必须位于扫描根外；根内路径退出 2；测试断言不创建文件 | PASS |
| 防路径遍历/越界链接/超大输入/NaN/bool 预算/重复规则 ID/空规则/占位 | 单测覆盖；`unsafe_target`/`AuditError` | PASS |
| 不执行源文档代码块 | 无 eval/exec/import 源文档；仅正则/文本解析 | PASS |
| 只读工具不调用 shell 执行源文件 | `subprocess` 只出现在测试，不在包内 | PASS |
| 最低 Python 实测或注明限制 | 3.13.15 实测；3.10 语法审查 + CI，NOT RUN | PASS WITH CAVEAT |
| 专属测试/真实 CLI/场景基准/现有只读回归 | 53 tests OK；真实 CLI 均已跑；`skill_selftest.py` 5 PASS | PASS |
| 不改公共测试框架 | 仅新增 `tests/skill_knowledge_audit/` | PASS |

## 8. 独立评阅对照

| 评阅发现 | 处理 | 复核证据 |
|---|---|---|
| F1 schematic 在 EDA 不可用时缺 `eda_unavailable`/只写不读 | 已修：schematic 纳入 EDA 任务集；EDA 可用 read+write，不可用 no write + unknown | `test_plan.SchematicEda`；`plan` CLI |
| F2 holdout-02/03 预算过小 | 未改 holdout（避免事后调参）；作为已知缺口披露，基准输出预算计数 | `main.json.metrics`；`report.md` §5 |
| F5 pass 不看预算/plan ok | 已缓解：新增预算/plan_ok 指标与 limitations | `main.json.metrics` |
| F6 18/4 下限仅 flag | 已修：`--split all` 默认强制，结果记录 `requirements` | `main.json.requirements` |
| F7 字段名/稳定性/路径校验 | 已修：契约字段名、digest 扩展、路径不存在退出 2 | 测试与 CLI |
| F8 报告缺失/来源声明 | 已补报告/验收/交接；topics 披露 holdout 参与验收；闭包深度统一为 2 | 本目录文件 |
| F10 输出自我污染 | 已修：输出必须位于扫描根外，根内路径退出 2（跨命令也不会被后续 scan 读到） | `test_cli.test_output_inside_root_is_refused` |

## 9. 不得宣称（验收口径）

- **NOT RUN**：模型是否真正加载/遵守、审批次数与 token 的实际变化、真实 EDA/Connector、
  DRC/制造/样机、端到端画板速度、Python 3.10 运行时、外链有效性。
- **不声称**：本任务已改变客户端实际加载行为、已提速、工程质量已通过。
- **已知覆盖缺口**：holdout-02（90k < 130k）与 holdout-03（40k < 64k）计划标
  `incomplete`，但 expected 未含 `budget_insufficient`，基准仍通过。`main.json`
  已输出 `budget_incomplete_total=4`、`plan_ok_false_total=4`；`ok/pass` 不代表预算完整。
  未事后调大 holdout 预算（避免调参），留给维护者决定。
- **独立评阅**：`independent-review.md` 结论 PASSED WITH CAVEATS；F1/F5/F6/F7/F8 已修复，
  F2 作为已知缺口保留，F4/F9 已披露为契约语义/场景重合而非缺陷。
