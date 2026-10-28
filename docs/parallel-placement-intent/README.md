# 任务 L：可校验的放置意图（HMT + CCG）离线 PoC

本目录是任务 L（PLACE-INTENT）的完整交付说明。模块是一个**独立、离线、只读**的
CLI：读取一个 JSON 文件，校验“分层模块树（HMT）+ 相对约束图（CCG）”是否自洽，并在
输入自足时导出**仅计划**的分层相对布局。它当前**不接入主执行流程**，不修改共享入口；
接入建议见 `integration-proposal.md`。

**它不写工程、不调用 EDA/daemon/connector、不联网、不训练/推理任何模型。**
`planned_with_scope` 只表示“意图自洽 + 几何自足”，不是已放置、可布通、DRC/制造/上电
通过；所有计划输出固定携带 `placement_applied:false`、`routing_verified:false`、
`physical_validation:"NOT RUN"`、`real_eda:"NOT RUN"`、`eda_calls:0`。

## 验收状态

| 验收项 | 结果 |
|---|---|
| 基线 `origin/main` | `1d1fcbd984d670905cf2fd4c7acf2c89f7e04347`（PR #72 合并后；本分支已 rebase 到该点，ahead 5 / behind 0） |
| 代码/测试/基准/结果冻结 HEAD | `ad0c170749fc7c32e45b0f88152641a322339ec2`（docs 收口提交紧随其后） |
| 单包测试（`unittest discover -s tests/placement_intent_tests -t tests`） | **Ran 239 tests in 45.900s — OK**，exit 0 |
| 官方全量（`python -m unittest discover -s tests`） | **Ran 3565 tests in 390.108s — OK (skipped=3)**，exit 0；新测试已被 discovery 发现 |
| 冻结基准（`python benchmarks/placement-intent/run_benchmark.py`） | **38/38 pass**，exit 0；`simulated:true`、`real_eda="NOT RUN"`、`eda_calls:0`；`--runs 2` 同样 38/38 |
| Skill 自检（`skill_selftest.py`） | **5 PASS / 0 FAIL**，exit 0 |
| 真实 EDA 调用 | **0**（无 daemon/connector/网络；不写工程） |
| Python 3.10 / 3.13 | 本机实际 3.13.15；**3.10 仅 CI 验证**（仓库 matrix `3.10`/`3.13`） |
| 清洁 checkout | **PASS**：`git archive` 导出的临时副本上重跑单包 **239 tests OK**、基准 **38/38 pass / exit 0**（见 `report.md` §5） |
| PR | **未创建**（网络禁用，未 push）；分支 `feat/parallel-placement-intent` 待推送，PR 目标 `main`、OPEN 未合并 |

`planned_with_scope` 只证明“给定的 HMT/CCG 表示自洽 + 所声明尺寸下推出的相对 bbox”，
不是已放置、可布通、DRC、保存重开、制造或上电验收。完整记录见
`acceptance-matrix.md`、`report.md` 与 `handoff-current.md`。

## 文档索引

| 文件 | 内容 |
|---|---|
| `contract.md` | 输入/输出 JSON 契约、坐标系与锚点、旋转约定、容差、退出码、unknown、原子写、只读保证（Lead 维护，权威） |
| `README.md` | 本文件：定位、命令速查、状态/退出码、NOT RUN 边界、验证结果摘要 |
| `design.md` | 设计动机（为什么是意图而非绝对坐标/训练）、与 ModuPlace 的 HMT/CCG 对应、架构、SE(2)/bbox/重叠/固定冲突算法、复杂度、已知限制 |
| `source-review.md` | 论文可借鉴/不可借鉴点、仓库既有 `design_engine` 候选/模板/module-plan 与 `routing_verified=false` 的关系、证书与边界声明 |
| `acceptance-matrix.md` | 任务书 §10 每条验收 ↔ 测试/基准/命令/真实结果；NOT RUN 单列 |
| `report.md` | 实际命令、测试数、基准结果、skill_selftest、全量套件、清洁 checkout 复跑、已修问题、限制、真实 vs 合成边界、Python 3.10 说明 |
| `integration-proposal.md` | 如何接入 `design_engine` module-plan/候选与 `easycirq_mcp` 工具层（本任务**不改**这些文件）；`verdict_class`/NOT RUN 字段映射 |
| `handoff-current.md` | 交接：分支、PR、精确 HEAD、允许路径核对、命令与结果、文件清单、已知限制、NOT RUN、下一步 |
| `issue-candidates.md` | 越界但值得主分支处理的事项（模块计划重名、相对意图缺失、`frame: board` 语义、单位换算、多锚点） |

## 代码与测试路径

| 路径 | 内容 |
|---|---|
| `easycirq/scripts/placement_intent/` | stdlib-only 包与 `python -m placement_intent` CLI |
| `tests/placement_intent_tests/` | 专属测试（子进程调用真实 CLI，不 import 实现；带 `__init__.py`，官方 discover 可识别） |
| `benchmarks/placement-intent/` | 冻结 CLI 场景（cases + expected.json）、驱动 `run_benchmark.py`、`results.json` |
| `docs/parallel-placement-intent/` | 本目录 |

## 命令速查

所有命令在仓库根目录执行；CLI 本身从 `easycirq/scripts` 运行。

```bash
# 工具自检
cd easycirq/scripts
PYTHONPATH=. python -m placement_intent --version

# 校验（只读输入；stdout 只有一个 JSON）
PYTHONPATH=. python -m placement_intent validate \
  --input ../../benchmarks/placement-intent/cases/valid-three-modules/input.json

# 计划（仅计划，不执行；--out 原子写，且不得等于输入）
PYTHONPATH=. python -m placement_intent plan \
  --input ../../benchmarks/placement-intent/cases/valid-three-modules/input.json \
  --out /tmp/plan.json

# 解释某条边/某个模块（只读重放）
PYTHONPATH=. python -m placement_intent explain \
  --input ../../benchmarks/placement-intent/cases/valid-three-modules/input.json \
  --constraint ccg:1

# 专属测试（官方入口也能发现）
cd ../..
python -m unittest discover -s tests/placement_intent_tests -t tests -p "test_*.py"

# 冻结基准（真实子进程调用 CLI；0 EDA）
python benchmarks/placement-intent/run_benchmark.py

# Skill 自检与全量套件
python easycirq/scripts/skill_selftest.py
python -m unittest discover -s tests
```

## 状态与退出码

| status | exit | 含义 |
|---|---|---|
| `valid` | 0 | `validate`：输入结构/语义合法（允许 warning/unknown） |
| `invalid` | 2 | `validate`：结构/语义非法（重复 JSON 键、NaN/Inf、树错误、矛盾约束等） |
| `planned_with_scope` | 0 | `plan`：输入合法、约束一致、所有节点帧已知、所有 bbox 可推导、板框已知 |
| `planned_constraints_only` | 1 | `plan`：约束一致但存在缺尺寸/缺板框/缺帧/无约束等 unknown；只给约束与层级 |
| `review_required` | 1 | `plan`：固定冲突、兄弟重叠、模块包络超出声明尺寸、来源不足等需人工处置的风险 |
| `incomplete` | 3 | `plan`：信息不足以规划（无模块/无元件、快照绑定关键字段缺失） |
| 用法/IO 错误 | 4 | 文件不存在、参数错误、`--out` 等于输入、`--anchor` 非 `top-left`（`plan`/`explain`）等 |

- `validate` 只输出 0 或 2（输入文件层面的 4 除外）；`planned_*`/`review_required`/
  `incomplete` 只由 `plan` 产生。
- `explain`：成功 exit 0；输入非法或目标 ID 不存在 exit 2；用法错误 exit 4。
- **任何 unknown/review_required/incomplete 都不会被提升为 `planned_with_scope`。**
- `--anchor`：v1 只支持 `top-left`（默认）；`plan`/`explain` 传其它取值 exit 4，
  `validate` 接受并忽略。
- 单位：`units.length` 只接受 `"mm"`/`"mil"`（`1 mil = 0.0254 mm`），内部统一 mm；
  **不按 mm 猜**。比较容差：平移 `position_tolerance_mm`（默认 `1e-6` mm）、
  旋转固定 `1e-6` 度、权重 `weight_epsilon`（默认 `1e-9`）。

## NOT RUN 边界

本模块证明的只是“给定的 HMT/CCG 表示自洽且可离线重放”。以下全部 **NOT RUN**，
不读取、不修改、不声称：

- 任何真实 EDA 工程被读取/修改/保存/重开（`real_eda:"NOT RUN"`、`eda_calls:0`）；
- 布局已应用（`placement_applied:false`）、布线可通（`routing_verified:false`）、
  DRC/连通性/SI/PI/EM/热通过；
- HPWL/密度/无重叠等代理指标等价于“可布通”或“电磁性能好”；
- 制造、装配、上电与实物功能；
- 论文（ModuPlace，DOI `10.1145/3770743.3803892`）的任何实验结论；本 PoC 只借鉴
  HMT/CCG 的**表示**思路，不含其数据、权重、训练（SFT/GRPO）或仿真评估。
