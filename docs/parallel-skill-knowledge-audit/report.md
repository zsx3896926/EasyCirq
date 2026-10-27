# D4 真实 Skill 审计报告（固定基线 9a951ed）

- 任务：并行任务 D — Skill 规则一致性、引用审计与最小阅读路径
- 基线：`9a951edc21481dc3ae91460acc11aa3e08a7be8a`，产品 `v1.0.1`
- 工具：`skill_knowledge_audit 0.1.0`；结构 `skill-knowledge-audit/v1`；目录 `2026-10-27.1`
- 环境：Windows + Python 3.13.15；**Python 3.10 运行时 NOT RUN**（语法/标准库按 3.10 编写，CI 覆盖）
- 证据文件：`benchmarks/skill-knowledge-audit/results/{scan,rules,main}.json` 与 `plans/`
- 本报告不修改任何源 Skill；所有建议见 `recommendations.md`，不直接套用。

## 1. 结论摘要

1. **引用图是干净的不是“规则多=引用坏”**：309 个 `.md`、2,480 条链接，失效路径/锚点 **0**；
   67 条链接有明确“先读/必须”措辞，必读闭包 17 个文件、最大深度 2。
2. **16 条锚点结构警告**：15 条是 `#g1-ldo` 这类“标题括号前截断”的约定式锚点，1 条是
   `I²C` 与 `I2C` 的 Unicode 兼容折叠差异。它们在 GitHub 精确 slug 下不是同一锚点，
   但在本仓库的写法中可被前缀/折叠匹配；按结构提示处理，不判失效。
3. **没有发现确定性规则冲突**：12 条已审规则、10 对已审候选关系，`true_conflict = 0`。
   用户感受到的“矛盾”主要是**不同阶段/范围/用户授权/显式例外**，以及**同一条规则重复 5 处**
   与**两个边界表述不清**（“做个板子”路线、检查点等待 vs 新决定）。
4. **规则确实存在重复阅读成本**：“门禁不是审批门”在 `SKILL.md:96/226`、
   `design-gates.md:7/395`、`interaction.md:30` 重复；直连/标签规则散在 5+ 处。
   这不是“长文档坏”，而是同一规则的入口过多。
5. **最小阅读计划可运行**：仅 BOM 任务 5 个必读、35,319 字符，不读布线/热设计/排版；
   离线评审不产生 EDA 读写动作；自主整板不自动插入等待；预算不足时 required 不裁剪并标
   `incomplete`；缓存按 SHA-256 + 目录版本失效。
6. **20 个场景全部通过（15 dev + 5 holdout）**：必要约束召回 1.0、关键遗漏 0、禁止阅读/动作 0、
   计划稳定 20/20；计划选中字节中位数是“读取全部 .md”基线的 **2.1%**（最大 3.4%）。
   **这不等于画板提速**：没有运行模型，也没有 EDA 端到端计时。

## 2. D1 引用图与索引（`scan`）

| 指标 | 数值 |
|---|---:|
| Markdown 文件 | 309 |
| 链接总数 | 2,480 |
| 显式必读链接 | 67 |
| 失效路径 | 0 |
| 缺失锚点（精确） | 0 |
| 结构警告 | 16（15 prefix + 1 NFKC） |
| 必读闭包文件 / 最大深度 | 17 / 2 |
| 引用环 SCC | 15（最大 SCC 184 个文件） |
| 孤立资料 | 7 |
| 重复主题（basename） | 1 组（`sources.md` × 3） |
| JSON / Markdown 索引 | 3.4 MB / 7,584 行 |

引用角色分布：`unknown 1,982`、`example 164`、`conditional_read 125`、
`background 72`、`external_reference 70`、`required_read 67`。大量 `unknown` 是
“文本没有明确表达必读/条件读”的链接；工具**不把普通链接自动升级为必读**，这是刻意保守。

必读闭包：`SKILL.md`、`workflow.md`、`evidence.md`、`design-gates.md`、
`agent-collaboration.md`、`beginner-journey.md`、`connectivity.md`、`eda-execution.md`、
`pcb-execution.md`、`pcb.md`、`schematic-layout-engine.md`、`offline-tools.md`、
`network-discipline.md`、`jlc-handoff.md`、`jlc-production.md`、两个 assets。
闭包字节数 263,026，是全部 `.md`（7,049,351 B）的 **3.7%**。

结构提示不是 bug：

- 15 个 SCC 中最大的 184 文件 SCC 是“索引/专题互相引用”形成的连通分量，不是引用错误；
- 7 个孤立资料是 `CHANGELOG.md`、三个 case README、两个 deepdive 索引等，属于入口未链接或
  只从外部入口进入，按上下文分类为结构提示；
- `sources.md` 同名三处（`references/`、`engineering-deepdives/`、`thermal/`）是不同范围资料，
  不能仅凭同名合并。

## 3. D2 规则审查（`rules`）

- 已审规则记录 **12 条**（`maintainer_declared`，全部逐条核到行）。
- 已审关系 **10 对**（`reviewed_relations`）：`coexist 3`、`different_scope 3`、
  `ambiguity 2`、`default_with_exception 1`、`different_stage 1`
  （完整分类见 `benchmarks/skill-knowledge-audit/results/rules.json`）。
- **确认冲突 0**：无一对满足“动作族相反、条件与范围重叠、无覆盖例外、需列两段原文”。
- 机器候选 **400** 条规则（模式抽取，未审），确定性候选张力 **200** 条（上限截断），
  全部标 `candidate`，**不**计入冲突。
- 16 对夹具 **16/16** 分类正确，覆盖契约 §5.4 全部 12 类；非构造引文 100% 核到声明行；
  证据不符时 `rules` 直接退出 2，不会沿用旧报告。

用户抱怨的四个张力，经证据审查后的结论：

| 张力 | 结论 | 依据 |
|---|---|---|
| 自主完成 vs 布局后必须等确认 | 非全局冲突；等待只在用户明确要求或新决定时发生 | `SKILL.md:96`、`:226`、`design-gates.md:7` |
| 速度优先 vs 开工加载全部资料 | 非冲突；只有 workflow/evidence 始终读，其余按任务表按需 | `SKILL.md:132/134`、`interaction.md:30` |
| 实体直连 vs 标签连通 | 默认+例外；局部直连，跨区/跨页/长距离或符号难直连时用标签 | `schematic-layout.md:54/74`、`SKILL.md:120` |
| 检查严格 vs 信息不足假通过 | 方向一致；缺证据判 BLOCKED，但只停依赖链路，其余离线工作继续 | `design-gates.md:63`、`SKILL.md:112` |

真正的阅读成本来自**重复陈述**与**边界歧义**，不是“存在互斥规则”。详见
`rule-review.md` 的 10 条候选与 9 条驳回记录。

## 4. D3 最小阅读计划（`plan`）

| 场景 intent | 必读文件 | 必读字符 | 计划字节 | 状态 | 动作 | unknown / 决策门 |
|---|---:|---:|---:|---|---|---|
| 简单原理图（域未知） | 8 | 76,324 | 150,724 | within | read_skill, read_eda, write_eda, offline_analysis | domain_unspecified |
| 仅 BOM | 5 | 35,319 | 74,321 | within | read_skill, offline_analysis | stage_unspecified |
| 离线开发 | 7 | 58,791 | 116,189 | within | read_skill, offline_analysis | eda_unavailable |
| 自主整板 | 10 | 112,105 | 200,173 | within | read_skill, read_eda, write_eda | — |
| 确认后再布线 | 13 | 128,943 | 230,934 | within | read_skill, read_eda, write_eda, wait_user_approval | before_route |
| 中途扩展范围 | 16 | 133,913 | 241,107 | within | read_skill, read_eda, write_eda | cache_invalidated / scope_change |
| 仅评审 | 5 | 38,018 | 81,996 | within | read_skill, offline_analysis | — |
| 小预算（holdout-04） | 5 | 35,319 | 74,321 | incomplete | read_skill, offline_analysis | budget_insufficient |

关键行为（均有测试）：

- 仅 BOM 不要求 `pcb-routing-details.md`、`thermal/topic.md`、`schematic-layout-engine.md`；
- 离线/禁止 EDA 时 `writes_allowed=false`、无 `read_eda/write_eda`，EDA 文档进入 excluded；
- `autonomous_authorized=true` 且无 pending 门时不插入 `wait_user_approval`；
- `before_route` 只来自用户显式 `user_decision_pending`，不由 planner 猜测；
- `scope_change` 产生 `decisions_required`，但不自动变成等待；
- required 超过预算不裁剪，列 `uncovered` 并标 `incomplete`；
- `already_read` 的 SHA-256 变化 → `already_read_stale`；规则版本变化 → `cache_invalidated`；
- 计划只导航，不证明模型加载或遵守（`not_proof` 字段固定输出）。

## 5. D5 冻结场景与基准（`benchmark`）

- 场景 **20 个**：dev 15 + holdout 5；全部通过；必要约束召回 **1.0**；
  关键遗漏 **0**、禁止阅读 **0**、禁止动作 **0**、缺决策门 **0**、缺 unknown 码 **0**；
  计划稳定 **20/20**。
- 计划读取量（选中字节 / 全部 `.md`）：最小 0.87%，中位 **2.10%**，最大 3.42%；
  即相对“读取所有可达 `.md`”的对照策略减少约 97.9%。该对照**只是策略基线**，
  不是用户先前实际执行，也不代表画板速度。
- 变形 7/7 通过：CRLF、增加普通背景链接、标题改名、内容哈希变化、任务同义表达、
  预算变小、无关文件外部修改，均未破坏 required 覆盖；小预算场景正确标 `incomplete`。
- 负例：missing must_include、forbidden selected/action、重复场景 ID、非法枚举、
  超预算不 complete、空规则集、重复规则 ID、证据不符、非法 JSON、越界 root 均明确失败。
- 基准完整计划耗时约 4.0 s（不含变形复制），变形检查另计；结果见
  `benchmarks/skill-knowledge-audit/results/main.json`。

**已知覆盖缺口（budget incomplete）**：`main.json` 的 `budget_incomplete_total=4`
（`dev-14`、`holdout-02`、`holdout-03`、`holdout-04`），`plan_ok_false_total=4`。
其中 holdout-02（90,000 < required 130,048）与 holdout-03（40,000 < required 64,267）
的 expected 未要求 `budget_insufficient`，因此基准仍判通过；这是**场景预算与必读集规模
不一致**，不是保护规则遗漏。按独立评阅建议，本任务**没有在看到实现结果后调大 holdout
预算**（避免事后调参），而是把该缺口作为已知限制交给维护者决定：提高预算或缩小必读集。
`ok/pass` 不代表所有计划预算完整，必须同时看 `budget_incomplete_total` 与
`plan_ok_false_total`。不得据此宣称“预算已足够”。

## 6. 独立评阅与修复

独立队友（holdout 设计者，非盲测）对 holdout、catalog 与基准做了对抗式评阅，
报告在 `independent-review.md`，结论 **PASSED WITH CAVEATS**。已处理：

- F1：schematic 任务纳入 EDA 任务集；EDA 可用时 `read_eda + write_eda`，
  EDA 不可用时 `writes_allowed=false` 且报 `eda_unavailable`（不再“只写不读”）。
- F5：基准新增 `budget_incomplete_total` / `budget_incomplete_scenarios` /
  `plan_ok_false_total`，并在 limitations 明写 `ok` 不代表预算完整；pass 语义按契约保留。
- F6：默认 `--split all` 自动强制 ≥18 场景、≥4 holdout，结果记录 `requirements`。
- F7：输出字段改为契约名 `unknown_expected_missing` / `baseline_all_markdown_bytes`；
  稳定性 digest 覆盖 selected + unknown + gates + actions；自定义场景的期望路径不存在
  视为输入错误（退出 2）。
- F10：输出必须位于扫描根之外；根内 `--out`/`--cache-out` 直接退出 2，
  因此跨命令也不会出现“后续 scan 读到上次报告”的自我污染。
- F8：本报告、`acceptance-matrix.md`、`handoff-current.md` 已存在，catalog 的
  `reviewed_by` 已如实披露 holdout 参与验收（非盲测）。

残余：F2（holdout 02/03 预算过小）按上述作为已知缺口保留；F4（autonomy 标志目前
不改变计划，wait 仅由 `before_*` 门决定）是当前契约语义，不作为缺陷；F9（部分
holdout 与 dev 的 selected 集合重合）已在 `holdout-rationale.md`/本报告披露。

## 7. 复现命令

```bash
cd design-hardware/scripts
python -m skill_knowledge_audit scan --root .. \
  --out ../../benchmarks/skill-knowledge-audit/results/scan.json --format both
python -m skill_knowledge_audit rules --root .. --strict \
  --out ../../benchmarks/skill-knowledge-audit/results/rules.json --format both
python -m skill_knowledge_audit benchmark --root .. \
  --out ../../benchmarks/skill-knowledge-audit/results/main.json \
  --require-18 --require-holdout --transforms
```

测试：`python -m unittest discover -s tests/skill_knowledge_audit -t .`
→ **53 tests OK**（1 个 Windows 符号链接用例跳过）。
既有回归：`python design-hardware/scripts/skill_selftest.py` → **5 PASS / 0 FAIL**。

### 冻结产物哈希（2026-10-28 00:41，之后不再改写）

| 文件 | 大小 | SHA-256 | 生成时间 |
|---|---:|---|---|
| `scan.json` | 3,448,013 B | `3d48246547373231f6adbc1b0d2fb6cccac62cfe69beacb6397ccf43ead20fd1` | 2026-10-28 00:40:43 |
| `rules.json` | 180,613 B | `b2ec2b8483b107c9ada258644aff47cf6b921e9525d1820f3ca7d759b5f854db` | 2026-10-28 00:40:48 |
| `main.json` | 28,693 B | `6f338c054d5923e6b6609413cd52378d1b0f2efd31c5fbc1120fec701547d046` | 2026-10-28 00:41:20 |

本表用于复核冻结结果；重跑命令见上，重跑会产生新的扫描时间与哈希，属正常。

## 8. 明确 NOT RUN / 不声称

- 未运行模型会话：不证明 Agent 实际加载、遵守、等待次数或阅读 token 变化；
- 未调用 EDA/Connector/daemon，未运行真实画板：不证明图纸质量、DRC、制造或端到端速度；
- 外链 70 条只记录、未联网验证，`external_verified=false`；
- 未运行 tokenizer：只报告字符/字节与保守区间，不把字符数当精确 token；
- 未在本机运行 Python 3.10，仅按 3.10 语法编写并由 CI 覆盖；
- holdout 由独立评阅者设计，但不是盲测；
- 未修改客户端、安装包、CI 或主 `SKILL.md`；本任务不宣称已改变实际加载行为。
