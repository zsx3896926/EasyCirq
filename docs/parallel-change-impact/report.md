# 变更影响分析结果报告（J）

本报告记录 `feat/parallel-change-impact` 的实际交付与验证结果。所有结论来自
本机离线运行；EDA、宿主 DRC、保存重开、官方导图、制造与实物检查均 **NOT RUN**。

## 1. 交付范围

| 路径 | 内容 |
|---|---|
| `design-hardware/scripts/change_impact/` | 工具实现：`__init__`/`__main__`/`cli`/`canonical`/`errors`/`model`/`classify`/`graph`/`propagate`/`evidence`/`verify_plan`/`compare`/`report` |
| `tests/change_impact/` | 单元/契约/基准测试（9 个文件，包含共享 fixture 与导入别名包装） |
| `benchmarks/change-impact/` | 50 个冻结 CLI 场景 + 期望断言 + 生成器 + runner + manifest + README |
| `docs/parallel-change-impact/` | `contract.md`、`propagation-rules.md`、`evidence-reuse-policy.md`、`verification-selection.md`、`acceptance-matrix.md`、`report.md`、`integration-proposal.md`、`handoff-current.md` |

未修改：`SKILL.md`、现有 references、README/CHANGELOG/版本、runtime/connector/
protocol、distribution、CI、顶层依赖、feedback、compose、design_engine 及其他
并行任务目录。

## 2. 实际命令与结果

### 2.1 单元与契约测试

```bash
cd <worktree>
python -m unittest discover -s tests -p "test_model_validation.py"   # 70 OK
python -m unittest discover -s tests -p "test_classify.py"          # 20 OK
python -m unittest discover -s tests -p "test_propagation.py"       # 46 OK
python -m unittest discover -s tests -p "test_evidence.py"          # 39 OK
python -m unittest discover -s tests -p "test_verification_plan.py" # 14 OK
python -m unittest discover -s tests -p "test_compare.py"           # 13 OK
python -m unittest discover -s tests -p "test_cli_contract.py"      # 22 OK
python -m unittest discover -s tests -p "test_benchmarks.py"        # 4 OK
python -m unittest discover -s tests -p "test_bootstrap.py"         # 3 OK
```

合计 **231** 个本任务测试全部通过。全仓库回归命令
`python -m unittest discover -s tests` 也通过（见 §5 收尾记录）。

### 2.2 冻结 CLI 基准

```bash
python benchmarks/change-impact/run_benchmark.py
→ 50/50 benchmark cases passed (0 failed)
```

覆盖：25 个分析场景、11 个非法输入、2 个组合案例、4 个 holdout、6 个变形、
2 个候选比较。每个用例真实子进程运行 `python -m change_impact`，输入与期望
SHA-256 冻结在 `manifest.json`。

### 2.3 CLI 快速验证

```bash
python -m change_impact validate  benchmarks/change-impact/scenarios/power_5v_to_3v3.json
python -m change_impact analyze   benchmarks/change-impact/scenarios/power_5v_to_3v3.json
python -m change_impact analyze   ... --format human
python -m change_impact plan      ...
python -m change_impact explain   ... --change chg:1
python -m change_impact compare   benchmarks/change-impact/compare/compare_two_candidates.json
```

退出码：0 成功（`planned_with_scope`/`no_change`）、2 输入无效、4 分析不完整
（`incomplete`）、1 内部错误；stdout 单份 JSON（`--format human` 为唯一文本例外），
诊断走 stderr，`--output` 原子写入且失败不留下报告。

## 3. 实现要点

1. **可解释传播**：17 条显式规则按「变更类别 × 依赖语义」匹配，路径带
   `trigger_rule`/`stop_reason`/`steps`/`change_ids`/置信度；缺边、未遍历、预算
   截断、循环全部进入 `unknown`/`cycles`/`frontier`，不冒充“无影响”。
2. **证据复用是评估**：仅当证书绑定（revision+content_hash）或覆盖属性指纹可
   重算一致时才允许复用；保留原 `captured_at`/`tool_version`/host 回执，不生成
   新时间或假回执；模拟证据 `valid_for` 仅 offline。
3. **验证计划**：mandatory 与 approval 分开且不受预算裁剪；有界贪心集合覆盖只
   修剪 optional，报告 `algorithm`/`budget`/`optimal:false`；缺覆盖报 gap。
4. **候选比较**：硬约束优先、unknown 优先于成本排序，未知更多更便宜的方案不能
   胜出；建议不自动执行。
5. **严格输入**：见 `acceptance-matrix.md` §严格性；非法输入不接受旧报告。
6. **确定性**：相同输入字节 → 相同输出字节（排序、无时间/随机/环境依赖）。

## 4. 开发中发现并修复的问题

| 问题 | 修复 |
|---|---|
| `voltage.nominal`、`pose.*`、`criterion`、`io_voltage`/`io_contract.*` 属性未被分类，导致合法变更被误判 `unknown_attribute` | 扩充属性类别表（电源/pose/测试/固件），并允许 `layer_stack` 与 pose 类显式细化 |
| `bom_line`/`region` 等对象使用 `bbox` 表达板框时无法归类 | 基准统一改用 `board.outline`，板框语义显式 |
| 无观测 diff 时把所有声明变更误报为 `declared_not_observed` | `compare_declared_to_observed` 只在确实提供 `observed_diff` 时做差异核对 |
| 依赖/变更/约束 ID 重复未校验 | 增加 `duplicate_dependency_id`/`duplicate_change_id`/`duplicate_constraint_id` |
| 指纹依赖输入顺序 | `Model.fingerprint` 先排序对象与依赖 |
| 声明差异但未声明变更时直接拒绝，无法给出“不可归因”结论 | 改为合法输入但 `status=incomplete` + `undeclared_difference` unknown |
| 证据复用只覆盖 certain 影响，possible 影响复用仍判 conditional，与契约“复用→降级”不符 | 复用检查提前到置信度分流之前，复用即降级为 optional |
| 生成器在候选比较 base 中缺少基线值、若干场景 after 值与候选模型不一致 | 修正冻结场景并重新冻结 SHA |

## 5. 收尾记录

- 基线：`main @ 9a951edc21481dc3ae91460acc11aa3e08a7be8a`；
- 分支：`feat/parallel-change-impact`（独立 worktree，未切换他人分支、未
  stash/reset/强推、未混提交）；
- 提交与 PR：仅提交本任务四个允许路径，推送并创建独立 PR，不合并、不发版、
  不替换安装；
- 全仓库回归：`python -m unittest discover -s tests`（结果见 PR 前的最终运行）；
- 未执行：EDA 读/写、宿主 DRC、保存重开、官方导图、烧录、上电、下单、实物测试。

## 6. 限制与不承诺

- 只分析**声明的**对象图与依赖；`dependencies_complete=false` 时缺边只能是
  unknown，工具不会补全真实电路语义。
- 不保证影响集合完备（unknown 边界显式存在），不宣称设计正确、不宣称验证通过、
  不宣称缩短真实 EDA/DRC/制造时间。
- 合成基准数据不代表真实工程；真实工程接入需要 A/F/G/H/I 等模块提供规范化快照
  与显式依赖（见 `integration-proposal.md`）。
- 宿主 DRC、保存重开、官方导图、实物/制造检查永远只进入计划（blocked/NOT RUN）。
- 规则表是当前声明模型下的保守推断；新增对象类型/依赖语义时需要同步扩展规则并
  更新测试与文档。
