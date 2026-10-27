# 并行任务 D 交接（skill-knowledge-audit）

状态：**已完成 M0–M4 的离线工具、真实基线审计、20 场景基准、测试与建议包；未合并、未发布、未安装客户端。**
最后更新：2026-10-28（Asia/Shanghai）

## 1. 交付物

| 路径 | 内容 |
|---|---|
| `design-hardware/scripts/skill_knowledge_audit/` | 只读 CLI：scan/rules/plan/benchmark + catalog |
| `tests/skill_knowledge_audit/` | 53 个 unittest（含负例、变形、真实基线只读断言） |
| `benchmarks/skill-knowledge-audit/` | 15 dev + 5 holdout 场景、16 对规则夹具、真实结果与计划样例 |
| `docs/parallel-skill-knowledge-audit/` | 契约、基线、规则审查、建议、集成、验收、报告、CLI 文档、本交接 |

关键文档：`contract.md`（含 §10 实施决策）、`source-baseline.md`、`rule-review.md`、
`recommendations.md`、`integration-proposal.md`、`acceptance-matrix.md`、`report.md`。

## 2. 结果摘要（固定基线 9a951ed）

- 扫描：309 个 `.md`、2,480 条链接、67 条显式必读；失效路径/锚点 **0**；
  16 条锚点结构警告（15 prefix + 1 NFKC）；必读闭包 17 文件、深度 2。
- 规则：12 条已审规则、10 对已审关系、**确认冲突 0**；16/16 夹具分类正确；
  400 条机器候选与 200 条候选张力均未升级为冲突。
- 计划：BOM 5 个必读/35,319 字符；离线评审无 EDA 读写；自主整板无自动等待；
  预算不足不裁 required；缓存按 SHA-256 + 目录版本失效。
- 基准：20/20 通过（15 dev + 5 holdout），必要约束召回 1.0、关键遗漏 0、
  禁止阅读/动作 0、稳定 20/20；计划选中字节中位数为“读全部 .md”基线的 2.1%；
  `budget_incomplete_total=4`、`plan_ok_false_total=4`（预算缺口已披露）。
- 独立评阅：`independent-review.md`，结论 PASSED WITH CAVEATS；F1/F5/F6/F7/F8/F10 已修复，
  F2 作为已知预算缺口保留（不事后调参）。F11（冻结哈希）见下方。
- 冻结产物（2026-10-28 00:31 后不再改写）：
  `scan.json` 3,448,013 B `726bd291…a625ba`；`rules.json` 180,613 B `63fbf14c…fff05e`；
  `main.json` 28,692 B `636318ac…5571f0`。
- 测试：53 tests OK（1 个 Windows 符号链接用例跳过）；既有
  `skill_selftest.py` 5 PASS / 0 FAIL；未运行全套既有测试（只读回归按需运行）。
- 真实 EDA 调用 **0**；模型会话 **0**；外链联网验证 **0**；Python 3.10 运行时 **NOT RUN**。

## 3. 复跑

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

```bash
cd <repo root>
python -m unittest discover -s tests/skill_knowledge_audit -t . -v
python design-hardware/scripts/skill_selftest.py
```

## 4. 已知限制 / 不要过度声称

- 计划只导航：不证明模型加载、遵守或阅读 token 改变；不会提升画板速度。
- 未调用 EDA/Connector，未验证图纸、DRC、制造、样机。
- 70 条外链只记录未验证；token 估计是字符类区间，不是 tokenizer。
- holdout 由独立队友设计但非盲测；holdout-02 的 90k 预算低于 required 130k，
  计划标 `incomplete`，而该场景 expected 未含 `budget_insufficient`，基准仍判通过；
  已作为覆盖缺口记录，需维护者下次冻结时处理。
- 本机 Python 3.13.15；3.10 由 CI 覆盖，未在本机实测。
- 输出必须位于扫描根外；根内路径退出 2（F10 修复）。
- 扫描的 16 条锚点警告不影响正文阅读，但在 GitHub 精确 slug 下不是同一锚点。

## 5. 给任务 A / 主维护者

- 集成方式见 `integration-proposal.md`；本任务不修改主 Skill、runtime、connector、
  distribution、CI，也不与 A 的未稳定提交互相等待。
- 应用建议前请逐条复核 `recommendations.md` 的“是否改变工程保护”；不要把本分支
  直接 cherry-pick 到主 Skill。
- 修改 `SKILL.md`/references 后必须重跑 `rules --strict`；行号/引文漂移会退出 2，
  不会静默沿用旧结论。

## 6. Git / PR

- 分支：`feat/parallel-skill-knowledge-audit`，固定开工 `9a951ed`。
- 只提交四个允许目录；创建独立 PR，不合并、不发布。
- commit / PR 链接：见 PR 描述与 `git log -1`（本文件随提交更新时记录）。
