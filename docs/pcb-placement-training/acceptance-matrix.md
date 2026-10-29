# 验收矩阵（PCB 预布局离线训练）

> 每条要求 ↔ 命令 ↔ 实际结果（2026-10-29 本机执行）。**未执行一律写 `NOT RUN`**，不得留空或默认通过。
> 状态取值：`PASS` / `BLOCKED` / `NOT RUN` / `N/A`。

## A. 交付物存在与结构

| 要求 | 命令 | 结果 |
|---|---|---|
| 契约冻结 | `docs/pcb-placement-training/contract.md`（258 行，§9 分工与写作用域） | PASS |
| 12 条案例 + schema 合法 | `python easycirq/scripts/pcb_placement_benchmark.py --list` | PASS（12 条，`--list` exit 0） |
| 判分器 CLI 可用 | `python easycirq/scripts/pcb_placement_benchmark.py --case P7-WIRELESS` | PASS（exit 2 = blocking，scorecard schema 正确） |
| 全量对账 | `python easycirq/scripts/pcb_placement_benchmark.py --all` | PASS（12/12 matched，exit 0） |
| 读法文档 | `easycirq/references/pcb-placement-benchmarks.md` | PASS（146 行，相对链接可解析） |
| 习题集 5 文件 | `easycirq/references/engineering-deepdives/exercises-pcb/` | PASS（README/exercises/paired-cases/answers/blind-prompts） |
| 冻结基准 | `python benchmarks/pcb-placement-benchmark/run_benchmark.py` | PASS（12/12，exit 0） |

## B. 测试与自检

| 要求 | 命令 | 结果 |
|---|---|---|
| 判分器测试 | `python -m unittest discover -s tests -k pcb_placement_benchmark` | PASS（121 tests OK，约 16 s） |
| 官方 discovery 发现新测试 | `python -m unittest discover -s tests` | PASS（exit 0；4191 tests OK，5 skipped，约 646 s，含 121 条新测试；rebase 后复跑） |
| Skill 自检 | `python easycirq/scripts/skill_selftest.py` | PASS（6 PASS / 0 FAIL / 0 NOT RUN，exit 0；48 必需路径、2147 相对链接、294 脚本编译） |
| 冻结基准 | 见 A | PASS |
| 确定性（`--all --json` 两次） | `sha256sum` 比对 | PASS（字节一致） |
| 确定性（`run_benchmark.py` 两次 `results.json`） | `Get-FileHash` 比对 | PASS（SHA256 相同） |
| 离线套件（可选） | `python tools/offline_suite.py` | `NOT RUN`（本轮未跑；全量 discovery 已覆盖测试层） |

## C. 接线与边界

| 要求 | 检查 | 结果 |
|---|---|---|
| SKILL.md 接线 | §3 表格 2 行：`references/pcb-placement-benchmarks.md`、`exercises-pcb/README.md` | PASS |
| PL 细节交叉链接 | `pcb-placement-details.md` 末尾指向基准集 | PASS |
| skill_selftest 必需清单 | `REQUIRED_FILES` 含 7 个新路径 | PASS |
| 深潜 README 文件地图 | 含 `exercises-pcb/` | PASS |
| 输出写死边界字段 | scorecard `drc:"NOT RUN"`、`routing_verified:false`、`placement_applied:false`、`eda_calls:0` | PASS（单测覆盖） |
| 不越界 | `git diff --name-status origin/main...HEAD` | PASS（见 report.md §2 文件清单） |

## D. 证据状态

| 项 | 状态 |
|---|---|
| 案例分析坐标手算复核 | 已完成（A：12/12 独立复算与判分器逐条相同，见 report.md §3） |
| 案例↔判分器对账 | 已完成（12/12；两次字节一致） |
| 成对变体不变量 | 已完成（4 对：除声明的一组坐标外 components/nets/checks/rubric/board 全等，verdict 全部翻转） |
| 习题盲测（独立 Agent 试答） | `NOT RUN`（`blind-prompts.md` 仅为输入，未运行） |
| 真实 EDA 回读/DRC/布线/仿真/制造/实物 | `NOT RUN`（超出本任务范围，离线代理不能替代） |
