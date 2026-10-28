# 任务 L（PLACE-INTENT）交接

- 分支 / worktree / 基线 `main` SHA：
  - 分支：`feat/parallel-placement-intent`
  - worktree：`C:\Users\jlc\Documents\deepseek-harness\default-workspace\hds-pi-worktree`
  - 基线 `origin/main`：`91b03e50127291d40276dd37941065fe42c904a1`（PR #99 合并后，统一品牌为智构 / EasyCirq；本分支已 rebase 到该点，`ahead 7 / behind 0`）
  - **目录/命名适配**：#99 把 `design-hardware/` 重构为 `easycirq/`，schema 命名空间
    `zhigou.*` 统一为 `easycirq.*`。本分支新增文件已落在新布局的等价允许路径内：
    `easycirq/scripts/placement_intent/`、`tests/placement_intent_tests/`、
    `benchmarks/placement-intent/`、`docs/parallel-placement-intent/`。
  - 说明：rebase 后验收用的 `git diff --name-status origin/main...HEAD` 三点 diff 的
    merge-base 即 `91b03e5`，diff 只包含本任务新增的 79 个文件。若主分支在评审前继续合并
    其它并行任务，由维护者在合并时 rebase/CI；本分支不再自动追。
- PR：**#100**（https://github.com/zsx3896926/EasyCirq/pull/100，`OPEN` **未合并**；
  base `main`、head `feat/parallel-placement-intent`；创建时 head `d738e83`）。
- 精确 HEAD：**`a182ae423d4386cf21ba8532de1738565e5a9617`**（PR #100 当前 head）
  - 代码/测试/基准/结果冻结提交为 `9b408cf`；`d81280c` 为 EasyCirq 布局/命名端口提交，
    `results.json.implementation.git_commit` 即 `d81280c`；
  - `a182ae4` 仅修一处跨平台测试路径字面量（Linux CI 下 `.\valid.json` 不是相对路径），
    本地与 CI 复跑均通过；docs 收口提交若晚于该 SHA，以 `git rev-parse HEAD` 为准。
- 允许路径核对（`git diff --name-status origin/main...HEAD`，在最终 docs 提交上实际运行）：
  **79 个新增文件，全部为 `A`**（无 `M`/`D`/`R`），且都在任务书 §3 四个允许路径的新布局
  等价位置内：

```text
A  easycirq/scripts/placement_intent/**        10 个 .py（包 + CLI）
A  tests/placement_intent_tests/**                    16 个（__init__.py + support.py + fixtures.py + 13 个 test_*.py）
A  benchmarks/placement-intent/**                     44 个（38 个 cases/*/input.json + 6 个文件：
                                                     expected.json / run_benchmark.py / results.json /
                                                     README.md / .gitattributes / derive_mcu_i2c_plan.py）
A  docs/parallel-placement-intent/**                  9 个 .md（contract.md + 8 个任务文档）
```

  复核命令：`git diff --name-status origin/main...HEAD | Where-Object { $_ -notmatch '^A\s' }`
  应无输出（Linux/macOS 用 `grep -v '^A'`）。未修改 `SKILL.md`、`references/*`、
  `design_engine`、`easycirq_mcp`、CI、依赖、版本号、LICENSE/NOTICE、README/CHANGELOG、
  主 `docs/handoff-current.md`，也未改其它 `docs/parallel-*`。
- 测试：命令 / 数量 / 结果
  - `python -m unittest discover -s tests/placement_intent_tests -t tests -p "test_*.py"`
    → **Ran 239 tests in 45.586s — OK**，exit 0
  - `python -m unittest discover -s tests`（官方全量）→
    **Ran 3569 tests in 323.075s — OK (skipped=3)**，exit 0；官方 discovery 已发现
    `placement_intent_tests` 的 239 个测试。
- 基准：命令 / 通过数 / 结果文件
  - `python benchmarks/placement-intent/run_benchmark.py` → **38/38 pass**，exit 0
    （`--runs 2` 同样 38/38）；结果文件 `benchmarks/placement-intent/results.json`，
    `simulated:true`、`real_eda:"NOT RUN"`、`eda_calls:0`、`correctness 38/38`、
    `implementation.git_commit=9b408cf…`
- 全量套件 / Skill 自检：
  - 全量见上（3569 tests OK，skipped=3）
  - `python easycirq/scripts/skill_selftest.py` → **5 PASS, 0 FAIL, 0 NOT RUN**，exit 0
- 3.10 / CI 状态：本机无 3.10（实际 3.13.15）；**CI 已全绿**（PR #100 head `a182ae4`）：
  `validate (3.10)` pass、`validate (3.13)` pass、`updater (ubuntu-latest)` /
  `updater (windows-latest)` pass、`publish` skipping。工作流：
  `.github/workflows/validate.yml`（matrix `['3.10','3.13']`，ubuntu 上跑
  `python3 -m unittest discover -s tests -v`）。
- 已知限制 / NOT RUN：
  - bbox = 旋转矩形的轴对齐外接矩形（仅 0/90/180/270），保守近似；
  - 只输出模块相对帧与可选 bbox，**不输出绝对板坐标、不应用放置**；
  - v1 只支持 `--anchor top-left`（其余 `plan`/`explain` exit 4；`validate` 忽略）；
  - 约束只校验不求解/不优化；矛盾即 `invalid_input`；unknown 只报告不补齐；
  - **NOT RUN**：真实 EDA 读取/修改/保存/重开、宿主 DRC、布线/铜连通、SI/PI/EM/热、
    制造/装配/上电/实物、ModuPlace 训练（SFT/GRPO）与仿真结论、本机 Python 3.10；
    `placement_applied:false`、`routing_verified:false`、`physical_validation:"NOT RUN"`、
    `real_eda:"NOT RUN"`、`eda_calls:0` 在所有 plan/validation 输出中固定保留。
- 下一步（评审关注点、可选的 MCP/design_engine 适配）：
  1. **已推送并创建 PR #100**（目标 `main`，OPEN 未合并，由主维护者评审）；后续仅按评审意见小步追加提交；
  2. 评审重点：`docs/parallel-placement-intent/contract.md` 的 v1 收窄口径（anchor）、
     `unknown` 不补齐、`review_required` 不降级；SE(2) 合成/多路径/环的实现与契约一致；
  3. 清洁 checkout 复跑（**已在冻结 HEAD `9b408cf` 上完成**）：`git archive` 导出临时副本后
     重跑单包测试 → **239 tests OK**、基准 → **38/38 pass / exit 0**（详见 `report.md` §5）；
  4. 后续集成 PR（本任务**不改**这些文件）：`design_engine` module-plan/候选前置校验、
     `easycirq_mcp` 新增 `offline_placement_intent_validate` /
     `offline_placement_intent_plan`（接口与 `verdict_class` 映射见
     `integration-proposal.md`）；
  5. 越界事项见 `issue-candidates.md`（两个 module plan 重名、相对意图校验缺失、
     `frame: board` 语义、mil 单位换算、多锚点）。

## 文件清单

| 路径 | 内容 |
|---|---|
| `easycirq/scripts/placement_intent/`（10 个 .py） | stdlib-only 包与 `python -m placement_intent` CLI |
| `tests/placement_intent_tests/`（`__init__.py` + `support.py` + `fixtures.py` + 13 个 `test_*.py`） | 239 个测试，子进程调用真实 CLI |
| `benchmarks/placement-intent/`（`cases/` 38 个、`expected.json`、`run_benchmark.py`、`results.json`、`README.md`、`.gitattributes`、`derive_mcu_i2c_plan.py`） | 冻结基准 |
| `docs/parallel-placement-intent/` | `contract.md`（Lead）+ `README.md`、`design.md`、`source-review.md`、`acceptance-matrix.md`、`report.md`、`integration-proposal.md`、`handoff-current.md`、`issue-candidates.md`（本任务文档负责人） |

## 复跑命令（复制即用）

```bash
cd <worktree>
python -m unittest discover -s tests/placement_intent_tests -t tests -p "test_*.py"
python -m unittest discover -s tests
python benchmarks/placement-intent/run_benchmark.py
python easycirq/scripts/skill_selftest.py
```

CLI 冒烟：

```bash
cd easycirq/scripts
PYTHONPATH=. python -m placement_intent --version          # placement_intent 0.1.0
PYTHONPATH=. python -m placement_intent validate \
  --input ../../benchmarks/placement-intent/cases/valid-three-modules/input.json
PYTHONPATH=. python -m placement_intent plan \
  --input ../../benchmarks/placement-intent/cases/valid-three-modules/input.json --out /tmp/plan.json
PYTHONPATH=. python -m placement_intent explain \
  --input ../../benchmarks/placement-intent/cases/valid-three-modules/input.json --constraint ccg:1
```

## PR 描述（可直接粘贴）

```markdown
# feat(placement-intent): 离线可校验的放置意图（HMT + CCG）PoC

## 目标
为 PCB 放置增加一个**显式、可校验、可交接的放置意图中间表示**：LLM/人给出模块树
（HMT）+ 相对约束图（CCG），工具离线校验一致性与完整性，并在尺寸已知时导出“仅计划”
的分层相对布局；所有无法证明的部分保持 unknown。不训练模型、不调用 EDA/联网、不写工程。

## 契约摘要
- 输入 `easycirq.placement-intent.input/v1`：project/snapshot/units(mm|mil)/board/
  modules(HMT)/components/constraints(CCG)/policy/provenance/unknowns；
  严格 JSON（拒绝重复键、NaN/Inf、bool 伪装数字），`additionalProperties:false`。
- 输出 `validation/v1`、`plan/v1`、`explain/v1`；plan 状态：
  `planned_with_scope(0)`、`planned_constraints_only(1)`、`review_required(1)`、
  `incomplete(3)`、`invalid_input(2)`；用法/IO 错误 4。
- CCG：`dx/dy + rotation_deg + weight`；SE(2) 路径合成、多路径一致、环恒等、
  重复去重/矛盾拒绝；`--anchor` v1 仅 `top-left`。
- 所有输出固定 `placement_applied:false`、`routing_verified:false`、
  `physical_validation:"NOT RUN"`、`real_eda:"NOT RUN"`、`eda_calls:0`。
- 只新增允许路径内文件（implementation/tests/benchmarks/docs），未改 SKILL.md/
  references/design_engine/easycirq_mcp/CI/依赖/版本号。

## 适配仓库重构（#99）
本任务书基线使用旧布局/命名；已适配 main 的 #99 重构：
`design-hardware/` → `easycirq/`、schema 命名空间 `zhigou.*` → `easycirq.*`
（与仓库既有 `easycirq.electrical-review.*` / `easycirq.mcp.*` 一致），
新增文件全部落在新布局的等价允许路径内。

## 实际命令与结果（本机 Windows 11 / Python 3.13.15；真实 EDA 调用 0）
- 单包测试：`python -m unittest discover -s tests/placement_intent_tests -t tests -p "test_*.py"`
  → 239 tests OK
- 官方全量：`python -m unittest discover -s tests` → 3569 tests OK (skipped=3)
- 基准：`python benchmarks/placement-intent/run_benchmark.py` → 38/38 pass，exit 0，
  `simulated:true`、`real_eda:"NOT RUN"`、`eda_calls:0`
- Skill 自检：`python easycirq/scripts/skill_selftest.py` → 5 PASS / 0 FAIL

## NOT RUN
真实 EDA 读取/修改/保存/重开、宿主 DRC、布线/铜连通、SI/PI/EM/热、制造/装配/上电/
实物、ModuPlace 训练与仿真结论、本机 Python 3.10（仅 CI matrix 验证）。
`planned_with_scope` 只表示意图自洽 + 几何自足，不表示已放置/可布通。

## 允许路径核对
`git diff --name-status origin/main...HEAD` 全部为 `A`（仅新增允许路径文件）。

## HEAD
`9b408cf9180a44aded543c1ac9c2ae2b7370aa6c`
```
