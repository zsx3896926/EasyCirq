# 集成建议（给任务 A / 主维护者，不互等、不自动套用）

本任务不修改 runtime、connector、protocol、distribution、CI、主 `SKILL.md` 或安装包。
以下是把本工具接入现有仓库/任务 A 的最小方式；全部为 proposal，需由对应 owner 评审后实施。

## 1. 已经稳定、可直接消费的接口

- 包位置：`design-hardware/scripts/skill_knowledge_audit/`（仅标准库，只读）。
- 命令：`scan` / `rules` / `plan` / `benchmark`（见 `cli.md`）。
- 结构版本：`skill-knowledge-audit/v1`；目录版本：`2026-10-27.1`；工具版本：`0.1.0`。
- 退出码：`0` 成功；`1` 有问题（扫描错误、计划 incomplete、基准失败、strict 夹具失败）；
  `2` 用法/IO/输入非法/抽取失败。**任何异常都不会输出旧 PASS。**
- 机器输出：`benchmarks/skill-knowledge-audit/results/{scan,rules,main}.json`；
  所有结论可按 `source.path + line` 回查。
- 稳定字段（建议 A 只依赖这些）：
  - scan：`files[].path/sha256/links[].role/line/target/resolved`、`graph.required_closure`、
    `findings[].severity/check/source/line`；
  - rules：`rules[]`、`reviewed_relations[]`、`confirmed_conflicts[]`、`fixtures.accuracy`；
  - plan：`required/conditional/optional/excluded/unknown`、`budget`、`execution_contract`、
    `cache`、`not_proof`；
  - benchmark：`scenarios`、`metrics`、`results[]`、`transforms`。

## 2. 建议的接入点

### 2.1 可选：给客户端/安装包加一个薄入口（由 A 或维护者实施）

`python -m skill_knowledge_audit` 要求 `design-hardware/scripts` 在 `PYTHONPATH`/当前目录。
如果希望从仓库根直接运行，可新增 `design-hardware/scripts/skill_knowledge_audit_cli.py`
（本任务**没有**创建，因为不在允许目录内）：

```python
# proposal only: design-hardware/scripts/skill_knowledge_audit_cli.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from skill_knowledge_audit.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
```

这样维护者可在仓库根执行：

```bash
python design-hardware/scripts/skill_knowledge_audit_cli.py scan --root design-hardware
```

不加入客户端运行时默认路径：它面向维护者，不参与普通画板任务。

### 2.2 CI（由维护者实施，本任务不改 `.github/workflows`）

建议新增独立 job，不替换现有 `unittest discover -s tests`：

```yaml
# proposal only
- name: Skill knowledge audit tests
  run: python -m unittest discover -s tests/skill_knowledge_audit -t . -v
- name: Skill knowledge audit evidence
  run: |
    cd design-hardware/scripts
    python -m skill_knowledge_audit scan --root .. \
      --out ../../benchmarks/skill-knowledge-audit/results/ci-scan.json
    python -m skill_knowledge_audit rules --root .. --strict \
      --out ../../benchmarks/skill-knowledge-audit/results/ci-rules.json
```

注意：`scan` 在源文件有失效引用时退出 1；`rules --strict` 在夹具分类失败或已审引文
与当前源不一致时退出 2。两者都应在 PR 中阻止合并，而不是只 warning。

### 2.3 `skill_selftest.py`（由维护者决定）

不建议把完整 `scan` 塞进 `skill_selftest.py`：两者职责不同（selftest 验包结构，
本工具验知识与导航）。若需要单一入口，可在 `skill_selftest.py` 里调用
`python -m skill_knowledge_audit scan --root .` 并把结果作为附加检查；
失败时输出 `BLOCKED`，不要把本工具结果合并成“硬件已验证”。

### 2.4 任务 A 的执行器

- A 不应在普通画板路径自动运行本工具；本工具只给维护者/分析会话使用。
- 若 A 想复用任务阅读计划，可只读调用 `plan`，把 `required/conditional` 作为“建议读取清单”，
  但**不得**把 `plan` 结果当作“模型已加载”或“规则已遵守”的证据。
- 不要把 `execution_contract.actions` 直接当 EDA 执行授权；它只是计划声明。

## 3. 维护流程（建议写入维护者文档）

1. 修改 `SKILL.md`/references 后：
   - 重跑 `rules --strict`。若行号/引文漂移，`catalog/rules.json` 会直接失败（退出 2）。
   - 只更新 `catalog/rules.json` 中受影响规则的 `source.line_*`/`text`，并用 `rule-review.md`
     重新标注条件/例外；不要用相似度自动改写。
2. 修改任务映射/新增 task_type 时：
   - 更新 `catalog/topics.json` 的 `task_types`/`match`/`files`；
   - 更新 `benchmarks/skill-knowledge-audit/scenarios/*.json` 的 `frozen.catalog_version`；
   - 重跑 benchmark，确保 `missing_critical=0`；若必须放宽，记录理由与保护影响。
3. 修改锚点/引用约定时：
   - 重跑 `scan`，把 `anchor_prefix_match`/`anchor_compat_match` 清零或写入有理由的忽略文件。
4. 版本发布时：
   - 目录版本递增（如 `2026-11-xx.1`），旧 plan/cache 自动失效（`rules_version_mismatch`）；
   - 不要复用旧结果文件冒充新版本 PASS。

## 4. 与任务 A/B/C 的边界

- 本工具不写 `design-hardware/` 源文档；A 若要应用 `recommendations.md` 的改动，
  由 A/维护者分别提交，不能把本分支当补丁直接 cherry-pick 到主 Skill。
- B/C 的离线审查/交付包结论不依赖本工具；本工具也不依赖 A 的执行器。
- 本任务未合并、未发布、未安装客户端，不阻塞 A 的稳定提交。

## 5. 风险与回退

| 风险 | 处理 |
|---|---|
| 目录/规则更新后行号漂移 | `rules` 证据校验失败即停（退出 2） |
| 场景过拟合 planner | holdout 独立设计；新增场景必须由未看实现的人写 rationale |
| 锚点约定变化 | `scan` 警告可定位；忽略声明必须带理由 |
| 把导航计划当行为证明 | 所有输出带 `not_proof`；报告明确 NOT RUN |
| 误把候选当冲突 | `confirmed_conflicts` 只来自 `catalog/rules.json` 的 `true_conflict`，机器候选永远标 `candidate` |

回退：删除本任务新增四个目录即可，不影响运行时与安装包；主 Skill 未被修改。
