# 交接：J 变更影响分析与增量验证计划

## 状态

- 分支：`feat/parallel-change-impact`（独立 worktree，基线 `main @ 9a951edc21481dc3ae91460acc11aa3e08a7be8a`）
- 交付：可运行的离线 ECO 变更影响分析工具 + 231 项测试 + 50 个冻结 CLI 基准 +
  8 份文档；已推送并创建独立 PR（不合并、不发版、不替换安装）
- 状态语义：`planned_with_scope` / `incomplete` / `no_change` / `input_invalid`；
  **没有 `design_pass`，没有“已验证/已应用”**
- EDA/宿主 DRC/保存重开/官方导图/烧录/上电/下单/实物：**NOT RUN**

## 快速开始

```bash
cd <repo>
export PYTHONPATH=$PWD/design-hardware/scripts     # Windows: $env:PYTHONPATH="$PWD\design-hardware\scripts"

# 1) 只校验输入模型（不给影响结论）
python -m change_impact validate benchmarks/change-impact/scenarios/power_5v_to_3v3.json

# 2) 影响分析（JSON 报告；--format human 输出人工交接）
python -m change_impact analyze benchmarks/change-impact/scenarios/power_5v_to_3v3.json
python -m change_impact analyze <input.json> --format human --output eco-handover.md

# 3) 只看增量验证计划
python -m change_impact plan <input.json>

# 4) 解释单个变更/受影响对象
python -m change_impact explain <input.json> --change chg:1
python -m change_impact explain <input.json> --object cmp:U2 --format human

# 5) 多候选 ECO 比较
python -m change_impact compare benchmarks/change-impact/compare/compare_two_candidates.json
```

退出码：`0` 成功（`planned_with_scope`/`no_change`）、`2` 输入/用法无效、
`4` 分析不完整（`incomplete`）、`1` 内部错误。默认只读；`--output` 原子写入且
**不得等于输入**，失败不会留下旧报告。

## 输入与输出

- 输入契约：`docs/parallel-change-impact/contract.md`（`hds-change-impact-input/v1`）；
  报告 `hds-change-impact-analysis/v1`；计划 `hds-change-impact-plan/v1`；
  比较 `hds-change-impact-compare-input/v1` / `hds-change-impact-compare/v1`；
  解释 `hds-change-impact-explain/v1`。
- 必读字段：`baseline`/`candidate`（project/document/revision/content_hash/
  source_type/snapshot_scope/missing_fields）、`objects`（带类型前缀的稳定 ID）、
  `dependencies`（语义/方向/确定性）、`changes`（before/after + 授权范围）、
  `verification_catalog`、可选的 `prior_evidence`、`budget`、`model_scope`。
- 未知语义：缺数据 → `unknown`/`unknown_objects`/`missing_fields`，不会用空列表
  或“无影响”代替；`dependencies_complete=false` 时缺边只能是 `unknown`。

## 文件清单（仅本任务允许路径）

```text
design-hardware/scripts/change_impact/
  __init__.py __main__.py cli.py canonical.py errors.py model.py classify.py
  graph.py propagate.py evidence.py verify_plan.py compare.py report.py
tests/change_impact/
  __init__.py _fixtures.py test_bootstrap.py test_model_validation.py
  test_classify.py test_propagation.py test_evidence.py
  test_verification_plan.py test_compare.py test_cli_contract.py test_benchmarks.py
benchmarks/change-impact/
  README.md build_scenarios.py run_benchmark.py manifest.json
  scenarios/ (25) scenarios/invalid/ (11) composite/ (2) holdout/ (4)
  variants/ (6) compare/ (2) expected/ (50)
docs/parallel-change-impact/
  contract.md propagation-rules.md evidence-reuse-policy.md
  verification-selection.md acceptance-matrix.md report.md
  integration-proposal.md handoff-current.md
```

未修改任何共享入口或其他并行任务目录（`SKILL.md`、references、README/CHANGELOG/
版本、runtime/connector/protocol、distribution、CI、顶层依赖、feedback、compose、
design_engine 均未触碰）。

## 验证方法（接手者可复现）

```bash
# 本任务全部测试（231 项）
python -m unittest discover -s tests -p "test_model_validation.py"
python -m unittest discover -s tests -p "test_classify.py"
python -m unittest discover -s tests -p "test_propagation.py"
python -m unittest discover -s tests -p "test_evidence.py"
python -m unittest discover -s tests -p "test_verification_plan.py"
python -m unittest discover -s tests -p "test_compare.py"
python -m unittest discover -s tests -p "test_cli_contract.py"
python -m unittest discover -s tests -p "test_benchmarks.py"
python -m unittest discover -s tests -p "test_bootstrap.py"

# 冻结基准（真实 CLI 子进程，50/50 通过）
python benchmarks/change-impact/run_benchmark.py

# 语料可重建性（应无差异）
python benchmarks/change-impact/run_benchmark.py --freeze   # 仅刻意改语料时
```

测试导入说明：`tests/change_impact/__init__.py` 把实现包以 `change_impact_impl`
别名加载，避免 `unittest discover -s tests` 的顶层包名与实现包名冲突（Python 3.10
与 3.13 均适用）；测试内使用 `from . import load` 后 `load('model')` 等。

## 已知限制

1. 只分析声明的对象图与依赖；不补全真实电路语义，不保证影响集合完备（unknown
   边界显式存在）。
2. 合成基准/组合案例只演示分析，不代表真实工程；接入真实工程需按
   `integration-proposal.md` 提供规范化快照与显式依赖。
3. 影响规则是保守推断：`possible` 表示需要人工判断，不是“已确认需要改”。
4. 证据复用依赖 `revision`/`content_hash`/`coverage`/`dependency_fingerprint`
   等可验证字段；缺字段一律 `unknown`，不默认有效。
5. `host`/`manual` 检查永远只计划（blocked）；宿主 DRC、保存重开、官方导图、
   实物/制造检查未执行，也无法由本工具执行。
6. 全部 `ignore`/空目录录不会判“完整验证”：缺目录会进入 gap/unknown。

## 明确的 NOT RUN

`eda_read`、`eda_write`、`host_drc`、`save_and_reopen`、`official_plot`、
`physical_test`、`manufacturing_order`。本任务不连接 EDA、不调用旧执行器/
Connector、不使用仪器、不烧录、不上电、不下单、不修改共享环境。

## 后续可做（不属于本 PR）

- 由集成 PR 添加 A/F/G/H/I 的只读适配器（observation/diff → 输入模型）；
- 把 B/C/E/I 的规则 ID 映射进 `verification_catalog`（检查仍由原模块执行）；
- schema 演进时升版本号并同步测试/基准（不要静默改字段语义）。
