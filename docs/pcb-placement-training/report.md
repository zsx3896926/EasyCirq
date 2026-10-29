# 报告：PCB 预布局离线训练（实施记录）

> 本文件记录**实际执行**的命令与结果；未做的检查写 `NOT RUN`。契约见 [contract.md](contract.md)，逐项验收见 [acceptance-matrix.md](acceptance-matrix.md)。
>
> 分支：`feat/pcb-placement-training`（基线 `origin/main @ 78e5d53`）。

## 1. 背景与目标

原理图侧已有两层离线训练：审图练习（20 题 + 8 对 + 答案）与排版基准集（8 类缺陷案例 + 检查器）。PCB 侧此前只有执行层工具（`pcb_preflight`、`design_engine pcb-candidates`、`placement_intent`），缺少**冻结训练集 + 确定性判分 + 习题**。本任务补齐这一层，训练「候选布局可否接受、为什么」的预布局判断。

## 2. 实际交付

| 交付 | 路径 | 规模 |
|---|---|---|
| 契约 | `docs/pcb-placement-training/contract.md` | 268 行；schema/判分语义/CLI/12 案例清单/假通过反例/分工 |
| 案例集 | `easycirq/assets/pcb-placement-benchmarks/benchmarks.json` | 12 条（8 主例 + 4 成对变体），157 KB，全部 `synthetic` |
| 判分器 | `easycirq/scripts/pcb_placement_benchmark.py` | 1833 行，stdlib-only，7 硬检查 + 软检查 + 全局代理 |
| 读法文档 | `easycirq/references/pcb-placement-benchmarks.md` | 146 行 |
| 习题集 | `easycirq/references/engineering-deepdives/exercises-pcb/` | 5 文件：20 题 + 8 对 + 答案 + 盲测输入 + README |
| 测试 | `tests/pcb_placement_benchmark/` | 9 文件，121 条 |
| 冻结基准 | `benchmarks/pcb-placement-benchmark/` | `run_benchmark.py` + `expected.json` + `results.json` + README |
| 接线 | `SKILL.md` §3（2 行）、`pcb-placement-details.md`（1 行）、`engineering-deepdives/README.md`（文件地图）、`skill_selftest.py`（7 个必需路径） | — |
| 既有资料维护 | `skill_knowledge_audit/catalog/rules.json`（R-GATE-003 证据窗口 278–285 → 279–286） | 因 SKILL.md 新增 1 行导致的证据行号同步 |

### 案例清单

| id | 域 | verdict | codes |
|---|---|---|---|
| `P1-MCU-MIN` | mcu | review | `distance_far` |
| `P1b-MCU-MIN-PAIR` | mcu | acceptable | — |
| `P2-BUCK` | power | review | `loop_large` |
| `P2b-BUCK-PAIR` | power | acceptable | — |
| `P3-ANALOG` | analog | review | `distance_far` |
| `P3b-ANALOG-PAIR` | analog | acceptable | — |
| `P4-COMM` | comm | blocking | `connector_off_edge` |
| `P5-BATTERY` | battery | review | `distance_far` |
| `P6-MOTOR` | motor | review | `loop_large` |
| `P7-WIRELESS` | wireless | blocking | `keepout_violation` |
| `P8-MULTI` | multi | blocking | `connector_off_edge`,`body_overlap` |
| `P8b-MULTI-PAIR` | multi | acceptable | — |

分布：3 blocking / 5 review / 4 acceptable；硬 code 覆盖 `keepout_violation`、`body_overlap`、`connector_off_edge`，软 code 覆盖 `distance_far`、`loop_large`，各 ≥1。

## 3. 实际命令与结果

| 命令 | 结果 |
|---|---|
| `python easycirq/scripts/pcb_placement_benchmark.py --list` | exit 0，12 条 |
| `python easycirq/scripts/pcb_placement_benchmark.py --all` | exit 0，**12/12 matched**；两次 `--json` 输出字节一致（sha256 由 A 与 B 分别复核） |
| `python easycirq/scripts/pcb_placement_benchmark.py --case P7-WIRELESS` | exit 2（blocking），scorecard `keepout_violation` × 2 对象（MOD1/C3） |
| `python benchmarks/pcb-placement-benchmark/run_benchmark.py` | exit 0，**12/12 PASS**，`real_eda:"NOT RUN"`、`eda_calls:0`；两次 `results.json` SHA256 一致 |
| `python -m unittest discover -s tests -k pcb_placement_benchmark` | 121 tests OK（约 16 s） |
| `python -m unittest discover -s tests` | 4177 tests，**OK**（约 8.5 min；本机此前两个并发 discover 会互相等子进程，单实例通过） |
| `python easycirq/scripts/skill_selftest.py` | 6 PASS / 0 FAIL / 0 NOT RUN（48 必需路径、2147 相对链接、294 脚本编译） |
| `python tools/offline_suite.py` | `NOT RUN`（本轮未跑；测试层已由官方 discovery 覆盖） |

独立复核（A）：12 条案例的 `expected` 先由缺陷意图手算确定，再用手写复算程序（旋转 bbox/焊盘、7 硬检查、4 软指标、2 mm 网格）验证，最后与判分器逐条比对；`metrics.hpwl_mm`/`congestion_max` 与判分器逐条相同。成对变体经程序化不变量检查：除声明的一组坐标外 `components/nets/checks/rubric/board` 全等，4 对 verdict 全部翻转。

## 4. 已修问题

1. **判分器 `--all` 汇总 schema 撞名**：`results/v1` 与冻结基准结果文件冲突 → 改为 `summary/v1`。
2. **soft/global 口径**：初版把 HPWL/congestion 塞进 `soft`，会让 `expected.soft_fail` 永远对不上 → 改为全局只进 `metrics`，超限才进 `codes`。
3. **兜底 code**：取消 `check_failed`，改为具体软 code（`distance_far`/`loop_large`），未知 `checks[].code` 按 `invalid_case`。
4. **冻结基准 runner 的 codes 提取**：只取 hard code → 补上失败软检查的 code，12/12 才与 expected 对齐。
5. **案例坐标错**（A 自检发现）：`P2-BUCK` 初版 `J1` 与 `L1` 有 0.25 mm² 非预期本体交叠 → 移动 `J1` 消除；未改 expected。
6. **SKILL.md 行位移**：新增 1 行导致知识审计 R-GATE-003 证据窗口失效 → 同步 `rules.json` 行号（279–286），审计 17 条测试复绿。
7. **契约残留旧 code**：`contract.md` 示例里的 `decouple_far`/`check_failed` 已统一。

## 5. 真实 vs 合成边界

- 12 条案例全部 `synthetic`（教学构造），**不是**真实板回读，**未**在 EDA 中放置/导图/DRC。
- 判分只覆盖离线几何与网表代理；`drc`、`routing`、`impedance`、`thermal`、`EMC`、`manufacturing`、真实样机全部 `NOT RUN`。
- 习题盲测（独立 Agent 试答）未运行：`blind-prompts.md` 只是待用输入，README 已标 `NOT RUN`。

## 6. 限制与下一步

- 判分器已知限制：非 0/90/180/270 旋转走防御性 AABB 并报 `rotation_not_allowed`；`connectors.insert_dir` 只做 schema 校验，v1 只判声明边距离；自交板框不检测；数值上限 1e6、单网络网格跨度上限 4096 cells（超出 `invalid_case`）。
- 冻结 runner 的 `_card_summary` 从 hard + 失败 soft 推 codes，看不到全局 `hpwl_high`/`congestion_hotspot`；当前 12 条 expected 不含全局 code，故不影响。若后续案例需要，应先改契约再扩展 runner。
- 后续可做：盲测执行与评分记录；从仓库冻结回读派生 1–2 个 `derived` 案例；把 `placement_intent` 的 HMT/CCG 参考意图与案例 `reference.key_placements` 对接；按需包装成 MCP 只读工具。
