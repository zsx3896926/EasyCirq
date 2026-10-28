# 报告：放置意图（HMT + CCG）离线 PoC 实际执行记录

本文件记录任务 L 在本机（Windows 11 / Python 3.13.15）**真实运行**的命令与结果。
所有数字均来自 worktree 根目录的实际执行；未运行项在 §8 单列。`planned_with_scope`
只表示“意图自洽 + 几何自足”，不是已放置/可布通/DRC/制造/上电通过。

## 1. 基线与环境

| 项 | 值 |
|---|---|
| 仓库 | https://github.com/zsx3896926/EasyCirq |
| 分支 | `feat/parallel-placement-intent` |
| worktree | `C:\Users\jlc\Documents\deepseek-harness\default-workspace\hds-pi-worktree` |
| 基线 `origin/main` | `91b03e50127291d40276dd37941065fe42c904a1`（PR #99 合并后：统一品牌为智构 / EasyCirq；本分支已 rebase 到该点，`ahead 7 / behind 0`） |
| 仓库重构适配 | #99 将 `design-hardware/` 重构为 `easycirq/`，schema 命名空间 `zhigou.*` 统一为 `easycirq.*`；本任务的包/测试/基准/文档已端口到新布局（提交 `d81280c`），schema 与仓库其它模块一致 |
| 代码/测试/基准/结果冻结 HEAD | `9b408cf9180a44aded543c1ac9c2ae2b7370aa6c`（其后只有 docs 收口提交） |
| 操作系统 | Windows 11 10.0.26200 SP0（AMD64） |
| Python（本机实际运行） | **3.13.15** |
| 最低 Python 声明 | 3.10（`from __future__ import annotations`；仅标准库） |
| 3.10 验证状态 | **仅 CI**：本机无 3.10；仓库 `.github/workflows/validate.yml` 的 matrix 含 `3.10`/`3.13` |
| 依赖 | 仅 Python 标准库；未新增依赖，未改顶层依赖文件 |
| EDA 调用 | **0**（未调用 easyeda/lceda CLI、daemon、connector；未切换窗口/刷新页面/装扩展） |
| 网络 | **实现/测试/基准运行期 0**（工具不联网）；收口后由负责人按指令用 `git push` + `gh pr create` 发布分支/PR（非工具运行期调用，PR 编号见 handoff） |

## 2. 实际执行命令

```bash
cd <worktree>

# 1) 单包测试（真实子进程调用 CLI）
python -m unittest discover -s tests/placement_intent_tests -t tests -p "test_*.py"

# 2) 官方全量（确认新测试被 discovery 发现、无 import 遮蔽/回归）
python -m unittest discover -s tests

# 3) 冻结基准（真实子进程调用 CLI）
python benchmarks/placement-intent/run_benchmark.py

# 4) Skill 自检
python easycirq/scripts/skill_selftest.py

# 5) 清洁 checkout 复跑（见 §5）
git archive HEAD | tar -x -C <临时目录>
cd <临时目录> && python -m unittest discover -s tests/placement_intent_tests -t tests -p "test_*.py"
cd <临时目录> && python benchmarks/placement-intent/run_benchmark.py
```

## 3. 测试结果（实际）

| 命令 | 结果 |
|---|---|
| `python -m unittest discover -s tests/placement_intent_tests -t tests -p "test_*.py"` | **Ran 239 tests in 45.586s — OK**，exit 0 |
| `python -m unittest discover -s tests`（官方全量） | **Ran 3569 tests in 323.075s — OK (skipped=3)**，exit 0；官方 discovery 能发现 `placement_intent_tests` 的 239 个测试。docs 收口提交后再复跑：**Ran 3569 tests in 323.075s — OK (skipped=3)**，exit 0 |
| 测试包结构 | `tests/placement_intent_tests/` 含 `__init__.py`、`support.py`（子进程 CLI 调用器）、`fixtures.py`、13 个 `test_*.py` |
| 实现导入纪律 | 测试**不 import** 实现，只用 `python -m placement_intent` 子进程（`test_scope_no_eda.test_implementation_imports_only_the_standard_library` 等交叉验证） |

覆盖要点（对应任务书 §7，逐条见 `acceptance-matrix.md` §B）：正例手算 bbox、
仅约束降级、unknown 传播/优先级、严格 JSON（重复键/NaN/Inf/BOM/UTF-8）、结构/类型/
枚举/空串/负权重/自环/端点不存在、矛盾（同 pair/多路径/非恒等环/恒等环）、树错误
（双根/环/父子不一致/归属/深度/非叶子带元件）、固定冲突、兄弟重叠、mm/mil 等价、
变形（数组顺序/id 重命名/整体平移/旋转/确定性/输入只读）、CLI/IO（退出码矩阵、
stdout 纯 JSON、`--out` 原子覆盖旧 PASS、`--out`=输入拒绝、`explain` 只读）、
0 EDA/0 网络。

## 4. 冻结基准结果（实际）

`python benchmarks/placement-intent/run_benchmark.py` → **38/38 pass，exit 0**；
`results.json`（`--runs` 默认 1，`--runs 2` 同样 38/38）：

| 指标 | 值 |
|---|---|
| `status` | **pass** |
| `correctness` | **38 / 38** |
| `simulated` | true |
| `real_eda` | **"NOT RUN"** |
| `eda_calls` | **0** |
| 场景分布 | `planned_with_scope` 6、`planned_constraints_only` 6、`review_required` 3、invalid 23；类别：positive 6、constraints_only 3、review 2、invalid_input 22、derived 1、holdout 4 |
| 来源类别 | `synthetic_fixture`、`synthetic_invalid_input`、`derived_offline_from_frozen_case`、`holdout_independent`、`holdout_counterexample` |
| 输入 SHA-256 | 每个 case 冻结；源文件改动则基准失败（不是“通过”） |
| timing（1 run，仅记录成本） | 38 场耗时合计 **5.802 s**；单场 min **0.128 s**、max **0.217 s**（Python 3.13.15 / Windows 11 / AMD64；仅成本，无提速声明） |
| 实现绑定 | `results.json.implementation.git_commit = 9b408cf…`、`git_branch = feat/parallel-placement-intent`、`tracked_worktree_dirty=false` |
| `limits` | 冻结合成/派生 JSON 上的 CLI 行为；不是“板可放置”；bbox 是相对 AABB；timing 不是性能声明 |
| `not_covered` | 真实 EDA、绝对坐标/应用/保存重开、布线/DRC/SI-PI-EM-热、制造/装配/实测、LLM 生成与 ModuPlace 训练、真实 `.epro2` 回读 |

`derived-mcu-i2c-plan`：从仓库冻结工程 `easycirq/cases/mcu-i2c-s3-2026-10-26/`
的只读数据**离线文本派生**（`derive_mcu_i2c_plan.py`），把 23 个绝对 mil 坐标按功能分成
5 个块并差分得到相对约束；源无尺寸 → 不声明 `size_mm`，因此全为 `size_unknown`、
bbox 全 null → `planned_constraints_only`（不冒充 `planned_with_scope`）。
**它不读取 `.epro2`、未调用 EDA，不是真实回读。**

## 5. 清洁 checkout 复跑（PASS）

在 rebase 后的分支 HEAD（代码/测试/基准/结果冻结于 `9b408cf…`；`tests/`、`benchmarks/`、
docs 均已提交）上用 `git archive` 导出清洁副本执行：

```bash
cd <worktree>
git archive --format=zip -o <临时目录>/repo.zip HEAD
# 解压到 <临时目录>/repo 后
cd <临时目录>/repo
python -m unittest discover -s tests/placement_intent_tests -t tests -p "test_*.py"
python benchmarks/placement-intent/run_benchmark.py
python easycirq/scripts/skill_selftest.py
```

- 结果：单包 **Ran 239 tests in 46.983s — OK**（exit 0）；基准 **38/38 pass，exit 0**
  （`results.json.status=pass`、`real_eda="NOT RUN"`、`eda_calls=0`）；
  `skill_selftest.py` **5 PASS / 0 FAIL / 0 NOT RUN**。与 worktree 结果一致。
- 换行敏感：`benchmarks/placement-intent/.gitattributes` 已固定 `* text eol=lf`，
  避免 Windows CRLF 与 Linux LF 造成冻结 SHA-256 不一致（任务 B 曾踩过该坑）。
- 清洁副本在临时目录，未回写任何仓库文件。

## 6. Skill 自检（实际）

`python easycirq/scripts/skill_selftest.py` → **5 PASS, 0 FAIL, 0 NOT RUN → exit 0**。
其中包含 `markdown-links`（2068 relative links / 312 Markdown files）与
`python-compile`（275 scripts compile）；本任务新增文件未破坏自检。

## 7. 本轮发现并修复的问题

1. **契约与实现的 anchor 不一致**：初版 `contract.md` 声明 `--anchor` 支持 5 种锚点，
   但实现只支持 `top-left`（其它值 exit 4）。Lead 裁定收窄契约：v1 固定
   `anchor="top-left"`，`plan`/`explain` 传其余合法枚举 → exit 4（用法错误），
   `validate` 接受并忽略；`contract.md` §1/§4.1/§7.2 已同步。多锚点扩展移到
   `issue-candidates.md` IC-5。
2. **严格 JSON 根节点/派生来源/位号 warning**（提交 `c7eb7d9`，rebase 前为 `cc6e4e0`）：
   修正非对象根的 finding code、`provenance.kind="derived"` 缺源 SHA-256 的非法判定、
   重复 designator 只记 warning；`contract.md` 同步澄清（`overlap_not_checked`、
   `frame_unknown` 等 unknown code 也加入 §5 表）。
3. **测试与夹具在开发中随契约收紧**：单包测试从红（初版 233 tests、110 failures）逐步
   收敛到 **239 tests OK**；期间修复了重复 `instance_id`、derived 无 SHA-256 等用例，
   断言未被削弱（测试只依赖契约 CLI 行为）。
4. **基准 derived 场景的诚实降级**：源冻结工程无尺寸，派生场景固定为
   `planned_constraints_only`，不为了让基准“全绿好看”而编造 `size_mm`。
5. **`overlap_not_checked` unknown**：重叠不可算时以 `impact:none` 明确记录，而不是
   静默跳过；不改变 plan 状态。
6. **适配仓库 #99 重构（提交 `d81280c`）**：main 统一品牌为「智构 / EasyCirq」后，
   `design-hardware/` → `easycirq/`、schema 命名空间 `zhigou.*` → `easycirq.*`。
   本任务把包、测试、基准（含 38 个 case 的 `input_sha256` 重冻结与 derived 源
   README 新 SHA `0bd97330…e4fb`）、文档端口到新布局；重跑后 239 单包测试与 38/38
   基准仍全绿。`results.json.implementation.git_commit` 记录执行时 HEAD `d81280c`。

## 8. 限制与 NOT RUN

限制：

- bbox 是旋转矩形的**轴对齐外接矩形**（仅 0/90/180/270），是保守近似，不是精确几何；
- 只输出**模块相对帧**与可选 bbox，不输出绝对板坐标、不应用放置；
- 约束只做一致性校验，不求解/不优化/不做最小二乘；矛盾即 `invalid_input`；
- v1 只实现 `top-left` 锚点；
- unknown 只报告不补齐；缺尺寸/缺帧/缺板框会降级状态；
- 固定冲突只用相对信息，缺位置/缺约束时不能证明冲突；
- 不建模布线、DRC、SI/PI/EM、热、制造、装配、上电。

**NOT RUN（不证明、未运行）**：

| 项 | 状态 |
|---|---|
| 真实 EDA 工程读取/修改/保存/重开 | `real_eda:"NOT RUN"`、`eda_calls:0` |
| 布局已应用 | `placement_applied:false` |
| 布线/铜连通/宿主 DRC/SI/PI/EM/热 | `routing_verified:false`、`physical_validation:"NOT RUN"` |
| 制造/装配/上电/实物 | NOT RUN |
| 本机 Python 3.10 运行时 | 仅 CI（本机 3.13.15） |
| ModuPlace 训练（SFT/GRPO）/仿真结论 | 未训练、未仿真；只借鉴 HMT/CCG 表示 |
| 清洁 checkout | **PASS**：见 §5（`git archive` 副本上 239 tests OK、38/38 基准 pass） |

## 9. 真实 vs 合成边界

- **合成**：38 个基准场景中绝大多数是 `synthetic_fixture`/`synthetic_invalid_input`
  （手写 JSON 夹具，用于契约符合性）；`holdout_*` 由独立于实现的设计产生（4 个，含
  2 个反例）。
- **派生**：仅 `derived-mcu-i2c-plan`，从仓库冻结工程的**只读数据离线派生**，记录
  源 SHA-256 与单位换算，标 `provenance.kind="derived"`；不是真实板回读。
- **真实**：无。本任务没有使用任何真实 EDA 回读、真实板、实测数据；任何
  “低 HPWL/无重叠 = 可布通/EM 好”的说法都不成立，输出固定
  `routing_verified:false` + NOT RUN。

## 10. Python 3.10 说明

- 本机只有 **Python 3.13.15**，无法在本地执行 3.10 运行时验证。
- 代码按要求使用 Python 3.10 语法/标准库（`from __future__ import annotations`，
  无 3.11+ 特性）；**3.10 仅 CI 验证**：仓库 `.github/workflows/validate.yml` 的
  matrix `['3.10', '3.13']` 在 PR HEAD 上运行 `python3 -m unittest discover -s tests -v`。
- PR 尚未创建（本任务禁止网络），CI 结果需在分支推送/PR 打开后确认；在此之前
  3.10 状态为 **NOT RUN（仅 CI 待验证）**，不写成“已通过”。
