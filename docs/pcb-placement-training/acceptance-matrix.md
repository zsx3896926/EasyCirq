# 验收矩阵（PCB 预布局离线训练）

> 每条要求 ↔ 命令 ↔ 实际结果（2026-10-29 本机执行，第二轮后更新）。**未执行一律写 `NOT RUN`**，不得留空或默认通过。
> 状态取值：`PASS` / `BLOCKED` / `NOT RUN` / `N/A`。

## A. 交付物存在与结构

| 要求 | 命令 | 结果 |
|---|---|---|
| 契约冻结（含 15 案例清单与派生规则） | `docs/pcb-placement-training/contract.md` | PASS |
| 15 条案例 + schema 合法 | `python easycirq/scripts/pcb_placement_benchmark.py --list` | PASS（15 条：12 synthetic + 3 derived） |
| 判分器 CLI 可用 | `python easycirq/scripts/pcb_placement_benchmark.py --case P7-WIRELESS` / `--case D1-MCU-LDO-DECAP` | PASS（exit 2 / exit 1，scorecard schema 正确） |
| 全量对账 | `python easycirq/scripts/pcb_placement_benchmark.py --all` | PASS（15/15 matched，exit 0；两次 `--json` 字节一致） |
| 派生案例可复算 | `python benchmarks/pcb-placement-benchmark/derive_cases.py --check` | PASS（源 SHA-256、单位/坐标换算、期望判定一致） |
| 读法文档（15 案例、synthetic/derived 证据等级） | `easycirq/references/pcb-placement-benchmarks.md` | PASS（相对链接可解析） |
| 习题集 5 文件（含 v2 盲测题面） | `easycirq/references/engineering-deepdives/exercises-pcb/` | PASS（README/exercises/paired-cases/answers/blind-prompts；20 题、8 对、题型分布 6/5/4/3/2 未变） |
| 盲测证据（3 份原文 + 评审） | `docs/evidence/pcb-placement-blind-2026-10-29/` | PASS（README/responses/evaluation） |
| 冻结基准 | `python benchmarks/pcb-placement-benchmark/run_benchmark.py` | PASS（15/15，exit 0） |

## B. 测试与自检

| 要求 | 命令 | 结果 |
|---|---|---|
| 判分器测试 | `python -m unittest discover -s tests -k pcb_placement_benchmark` | PASS（121 tests OK） |
| 官方 discovery 发现新测试 | `python -m unittest discover -s tests` | PASS（exit 0；4191 tests OK，5 skipped，约 457 s，含 121 条新测试） |
| Skill 自检 | `python easycirq/scripts/skill_selftest.py` | PASS（6 PASS / 0 FAIL / 0 NOT RUN） |
| 知识审计（真实基线） | `python -m unittest tests.skill_knowledge_audit.test_real_baseline` | PASS（errors 0；修复越界链接后） |
| 确定性（`--all --json` 两次） | `Get-FileHash`/`sha256sum` 比对 | PASS（字节一致） |
| 确定性（`run_benchmark.py` 两次 `results.json`） | `Get-FileHash` 比对 | PASS（SHA256 相同） |
| 离线套件（可选） | `python tools/offline_suite.py` | `NOT RUN`（本轮未跑；测试层由官方 discovery 覆盖） |

## C. 接线与边界

| 要求 | 检查 | 结果 |
|---|---|---|
| SKILL.md 接线 | §3 表格 2 行：`references/pcb-placement-benchmarks.md`、`exercises-pcb/README.md` | PASS |
| PL 细节交叉链接 | `pcb-placement-details.md` 末尾指向基准集 | PASS |
| skill_selftest 必需清单 | `REQUIRED_FILES` 含 7 个新路径 | PASS |
| 深潜 README 文件地图 | 含 `exercises-pcb/` | PASS |
| 输出写死边界字段 | scorecard `drc:"NOT RUN"`、`routing_verified:false`、`placement_applied:false`、`eda_calls:0` | PASS（单测覆盖；derived 案例同样） |
| 不越界 | `git diff --name-status origin/main...HEAD` | PASS（见 report.md §2 文件清单） |

## D. 证据状态

| 项 | 状态 |
|---|---|
| 合成案例分析坐标手算复核 | 已完成（12/12 独立复算与判分器逐条相同） |
| 派生案例溯源 | 已完成（3/3 源 SHA-256 现算并校验；bbox/焊盘复现误差 ≤1e-6 mm / ≤1e-14 mm；真实距离与原工程 tracked 值逐位对齐） |
| 案例↔判分器对账 | 已完成（15/15；两次字节一致） |
| 成对变体不变量 | 已完成（4 对：除声明的一组坐标外 components/nets/checks/rubric/board 全等，verdict 全部翻转） |
| 第一轮盲测（3 Agent 试答 + 单评审） | 已完成（结论类型 71.7%、机制 95%、证据 100% 但泄题、行动/未知 96.7%；已修订 v2 题面） |
| 第二轮盲测（3 Agent 试答 + 2 名评审交叉评分） | 已完成（v2 题面；300 单元一致率 92.7%；结论类型 A 61.7% / B 60.0%；X13 两人 ✗ 为唯一内容错误；据此修订 v3 题面与 answers X05/X10/X11，未追溯分数） |
| 第三轮盲测（v3 题面 + 双评审交叉） | 已完成（300 单元一致率 92.3%；结论 A 53.3% / B 50.0%；X01/X02 标记位移明显下降 0/6→5–6/6；X10/X11 与 v3 口径一致；**X13 翻转识别仍 0/3**；结论率下降归因为条件簇答案口径冲突，v4 建议已记录、未执行） |
| 第四轮盲测（v4 题面 + 双评审交叉） | 已完成（结论 A 88.3% / B 88.3%；300 单元一致率 98.3%、结论维 100%；X01/X02/X10/X11 主标记 12/12；**X13 翻转识别 0/3 → 3/3**；扣除 X05/X20 标准侧冲突后 53/54 = 98.1%；据此产出 v5 答案口径，未追溯分数） |
| 第五轮盲测（v5 口径） | 已完成（结论 A 100% / B 93.3%；X05/X20 主标记归零 6/6+6/6；X13 保持 3/3；扣除 X20 标准侧前提缺口后结论 98–100%；据此判定通过并合并 PR） |
| 真实 EDA 回读/DRC/布线/仿真/制造/实物 | `NOT RUN`（超出本任务范围，离线代理不能替代） |
