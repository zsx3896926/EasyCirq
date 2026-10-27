# `skill_knowledge_audit` — 只读 Skill 知识结构审计

本工具回答四个问题：引用是否有效；哪些规则可能冲突；某个任务应读哪些文件；哪些阅读是无关成本。
它只读扫描、只输出分析与建议，不修改 `SKILL.md`/references，不执行文档代码块，不调用 EDA，不联网。

## 最快上手（仓库内）

```bash
cd design-hardware/scripts

# 1. 扫描引用图（JSON + Markdown 索引）
python -m skill_knowledge_audit scan --root .. \
  --out ../../benchmarks/skill-knowledge-audit/results/scan.json --format both

# 2. 规则候选、已审关系与 16 对夹具分类
python -m skill_knowledge_audit rules --root .. --strict \
  --out ../../benchmarks/skill-knowledge-audit/results/rules.json --format both

# 3. 仅 BOM 任务的最小阅读计划
python -m skill_knowledge_audit plan --root .. \
  --task bom_only --stage read --no-eda --deliverable bom \
  --constraint "只核对 BOM 与配单" \
  --out ../../benchmarks/skill-knowledge-audit/results/plans/bom.json

# 4. 20 个冻结场景（15 dev + 5 holdout）+ 变形检查
# --split all（默认）会自动强制 >=18 场景、>=4 holdout；也可显式加 flag
python -m skill_knowledge_audit benchmark --root .. \
  --out ../../benchmarks/skill-knowledge-audit/results/main.json \
  --require-18 --require-holdout --transforms
```

`--root` 指向 `design-hardware` 目录（含 `SKILL.md`）。不传时按当前目录自动推断。
`--out` 的父目录必须已存在，且输出必须位于扫描根之外（根内路径直接退出 2，防止
自我污染）；输出用同目录临时文件 + `os.replace` 原子写入。

## 输入与输出契约

- stdout **只**输出一个 JSON 对象（`ensure_ascii=false`、`sort_keys=true`）；诊断信息只写 stderr。
- 退出码：`0` 成功/无必须失败项；`1` 有需要处理的问题（扫描错误、计划 incomplete、
  基准失败、`--strict` 夹具失败）；`2` 用法/IO/输入非法/抽取失败。
- 结果结构版本 `skill-knowledge-audit/v1`，目录版本 `2026-10-27.1`，工具版本 `0.1.0`。
- `scan` 不验证外链（只记录 URL），不执行脚本；脚本引用只检查路径是否存在。
- `plan` 是导航计划，不证明模型加载或遵守；不调用 EDA。
- `benchmark` 的“全量读取所有 .md”只是对照基线策略，不是用户先前行为；减少阅读量不等于画板提速。
  `ok/pass` 不代表计划预算完整：同时看 `budget_incomplete_total` 与 `plan_ok_false_total`。

## 目录

```
skill_knowledge_audit/
  scan.py      D1 文件/标题/锚点/链接/脚本引用/引用图
  rules.py     D2 规则抽取、证据校验、候选张力、夹具分类
  plan.py      D3 intent → required/conditional/optional/excluded/unknown
  bench.py     D5 场景、指标、变形
  cli.py       scan / rules / plan / benchmark
  catalog/
    topics.json      任务→主题→文件映射（人工审查）
    rules.json       12 条已审规则 + 10 条已审关系
```

## 自定义输入

`plan --intent <file>` 接受：

```json
{
  "schema": "ska-intent/v1",
  "task_type": "pcb_layout",
  "stage": "layout",
  "autonomous_authorized": true,
  "eda_available": true,
  "deliverables": ["pcb"],
  "constraints": ["保留板框与安装孔"],
  "user_decision_pending": ["before_route"],
  "already_read": [
    {"path": "design-hardware/references/pcb.md",
     "sha256": "<64 hex>", "rules_version": "2026-10-27.1", "scope": "layout"}
  ],
  "budget_chars": 120000,
  "notes": "只移动 U3/C7"
}
```

`--budget/--task/--stage/--notes/--deliverable/--constraint/--pending` 可在命令行覆盖文件字段。
`--eda/--no-eda` 与 `--autonomous/--no-autonomous` 控制布尔项。

## 忽略声明

`scan --ignore-file <json>`：

```json
{"schema": "ska-ignore/v1", "rules": [
  {"id": "IGN-001", "check": "broken_link", "target": "references/x.md",
   "reason": "外部规范要求保留历史锚点", "scope": "file:references/x.md"}
]}
```

每条忽略必须有理由、精确 target、受限 scope；被忽略的发现仍出现在结果里（`ignored:true`），
不会从输出中消失。通配/无理由/无 scope 的规则会被拒绝（退出 2）。

## 兼容性

只用 Python 标准库；语法按 Python 3.10+ 编写。本机实测 Python 3.13.15；3.10 由 CI 覆盖，
本任务未在 3.10 运行时实测。
