# Skill 知识结构审计基准（D5）

本目录冻结并行任务 D 的场景、夹具与真实基线结果。它评估**阅读导航**，不评估模型回答质量、
不证明工程正确，也不测量画板速度。

## 文件

```
scenarios/
  dev.json                15 个开发场景（期望由独立阅读规则给出，非 planner 输出）
  holdout.json            5 个 holdout（由未读 dev 集的独立评阅者设计）
  holdout-rationale.md    holdout 独立性、公平性与过拟合失败模式
  README.md               dev 集说明、覆盖矩阵、指标定义
  validate_scenarios.py   场景结构/路径/枚举校验器
fixtures/
  rule-pairs.json         16 对规则分类夹具（12 类全覆盖）
results/
  scan.json / scan.md     真实基线扫描的机器 JSON 与 Markdown 索引
  rules.json / rules.md   规则候选、已审关系、夹具结果
  main.json               benchmark 完整结果（含变形检查）
  plans/                  代表性 intent 与 plan 输出（BOM/离线/自主/评审/扩展等）
```

## 场景约定

- 场景固定基线 `9a951edc21481dc3ae91460acc11aa3e08a7be8a`，目录版本 `2026-10-27.1`。
- `must_include`：正确最小计划必须选为 required 的文件；任一遗漏 → 场景失败。
- `must_exclude`：不得被选中；`forbidden_plan_actions`：不得出现在执行契约中。
- `required_unknown`：计划必须报告的 unknown code；`required_approval_gates`：必须出现的决策门。
- 场景编号不得写进实现分支；实现只读取 intent/expected 数据。

## 复跑

```bash
cd design-hardware/scripts
python -m skill_knowledge_audit benchmark --root .. \
  --out ../../benchmarks/skill-knowledge-audit/results/main.json \
  --require-18 --require-holdout --transforms
```

`--split all`（默认）会自动强制 >=18 场景、>=4 holdout；只跑 dev/holdout 子集时
可用 `--split dev|holdout` 且不触发下限。`ok/pass` 不代表每个计划预算完整：
看 `budget_incomplete_total` / `plan_ok_false_total`。

## 结果口径（必须与“已验证”区分）

- `selected_bytes / baseline_all_markdown_bytes` 中的 baseline 是“读取全部 .md”的对照策略，
  不是用户先前实际执行的路径。
- 字节数是静态文件大小，不是 token；工具不运行 tokenizer。
- `stable` 只说明同一输入两次运行选择一致，不说明模型行为稳定。
- holdout 由独立评阅者设计，但本任务没有多盲协议，因此**不是盲测**。
- NOT RUN：真实模型加载与遵守、真实 EDA/Connector、端到端画板耗时、Python 3.10 运行时。
