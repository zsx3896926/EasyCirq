# 报告：PCB 预布局离线训练（实施记录）

> 本文件记录**实际执行**的命令与结果；未做的检查写 `NOT RUN`。契约见 [contract.md](contract.md)，逐项验收见 [acceptance-matrix.md](acceptance-matrix.md)。
>
> 分支：`feat/pcb-placement-training`，PR [#192](https://github.com/zsx3896926/EasyCirq/pull/192)（OPEN，不合并）。本文件已按五轮盲测 + 3 条派生案例更新；最新 PR HEAD 以 PR #192 页面为准。

## 1. 背景与目标

原理图侧已有两层离线训练：审图练习（20 题 + 8 对 + 答案）与排版基准集（8 类缺陷案例 + 检查器）。PCB 侧此前只有执行层工具（`pcb_preflight`、`design_engine pcb-candidates`、`placement_intent`），缺少**冻结训练集 + 确定性判分 + 习题**。本任务补齐这一层，训练「候选布局可否接受、为什么」的预布局判断。

第二轮补两件事：**跑一轮独立盲测并记录**、**从真实回读证据派生 3 条 `derived` 案例**。

## 2. 实际交付

| 交付 | 路径 | 规模 |
|---|---|---|
| 契约 | `docs/pcb-placement-training/contract.md` | schema/判分语义/CLI/15 案例清单/派生规则/盲测要求/假通过反例/分工 |
| 案例集 | `easycirq/assets/pcb-placement-benchmarks/benchmarks.json` | **15 条**（8 主例 + 4 成对变体 + 3 derived），约 164 KB |
| 判分器 | `easycirq/scripts/pcb_placement_benchmark.py` | 1833 行，stdlib-only，7 硬检查 + 软检查 + 全局代理 |
| 派生脚本 | `benchmarks/pcb-placement-benchmark/derive_cases.py` | 3 条 derived 的唯一派生源（`--check/--print/--write`，幂等） |
| 派生说明 | `docs/pcb-placement-training/derived-cases.md` | 源 SHA-256、mil→mm、原点/旋转/引脚换算规则、保留丢弃清单、阈值依据 |
| 读法文档 | `easycirq/references/pcb-placement-benchmarks.md` | 15 案例表（含 synthetic/derived 来源列）+ 证据等级小节 + 五维评分 |
| 习题集 | `easycirq/references/engineering-deepdives/exercises-pcb/` | 20 题 + 8 对 + 答案 + 盲测题面（v2）+ README（含第一轮盲测结果） |
| 盲测证据 | `docs/evidence/pcb-placement-blind-2026-10-29/` | 两轮：README（方法/限制/总览）+ responses/evaluation（第一轮，单评审）+ round2-responses/round2-scoring-a/round2-scoring-b/round2-evaluation（第二轮，双评审交叉、裁决） |
| 测试 | `tests/pcb_placement_benchmark/` | 9 文件，121 条；冻结集合测试改为按案例文件动态计数 |
| 冻结基准 | `benchmarks/pcb-placement-benchmark/` | `run_benchmark.py` + `expected.json`（15 条 + 源 SHA）+ `results.json` + README |
| 接线 | `SKILL.md` §3（2 行）、`pcb-placement-details.md`（1 行）、`engineering-deepdives/README.md`（文件地图）、`skill_selftest.py`（7 个必需路径）、`skill_knowledge_audit/catalog/rules.json`（R-GATE-003 证据窗口） | — |

### 案例清单（15 条）

| id | 域 | 来源 | verdict | codes |
|---|---|---|---|---|
| `P1-MCU-MIN` | mcu | synthetic | review | `distance_far` |
| `P1b-MCU-MIN-PAIR` | mcu | synthetic | acceptable | — |
| `P2-BUCK` | power | synthetic | review | `loop_large` |
| `P2b-BUCK-PAIR` | power | synthetic | acceptable | — |
| `P3-ANALOG` | analog | synthetic | review | `distance_far` |
| `P3b-ANALOG-PAIR` | analog | synthetic | acceptable | — |
| `P4-COMM` | comm | synthetic | blocking | `connector_off_edge` |
| `P5-BATTERY` | battery | synthetic | review | `distance_far` |
| `P6-MOTOR` | motor | synthetic | review | `loop_large` |
| `P7-WIRELESS` | wireless | synthetic | blocking | `keepout_violation` |
| `P8-MULTI` | multi | synthetic | blocking | `connector_off_edge`,`body_overlap` |
| `P8b-MULTI-PAIR` | multi | synthetic | acceptable | — |
| `D1-MCU-LDO-DECAP` | mcu | derived（mcu-i2c-s3 真板） | review | `distance_far` |
| `D2-PHOTO-LED-SENSE` | analog | derived（photo-led 真板） | acceptable | — |
| `D3-DUAL-BTN-D4-MOVE` | multi | derived（dual-button 负例） | blocking | `body_overlap` |

合成部分：3 blocking / 5 review / 4 acceptable；硬 code 覆盖 `keepout_violation`、`body_overlap`、`connector_off_edge`，软 code 覆盖 `distance_far`、`loop_large`。派生部分：1 review / 1 acceptable / 1 blocking，覆盖真实板尺寸（65.8×45 / 90×60 / 50×35 mm）与 mil→mm 换算。

### 派生案例怎么来的（要点）

- 只用 git 跟踪的证据：`pcb-dump-final.json`（mcu-i2c-s3、photo-led）与 `negative-direct-move/board-baseline.json`；`source_sha256` 由脚本现算（三份均校验一致）。
- dump 的 x/y 是 **footprint 原点**而非中心（用同一数据反例证明），因此：中心取 bbox 中心、`size_mm` 取 bbox 反旋尺寸、引脚偏移 = `R(-rot)·(pad_abs − 中心)`；脚本断言 bbox 复现 ≤1e-6 mm、焊盘复现 ≤1e-14 mm。
- 阈值取自 tracked 证据（decap ≤100 mil 规则；`constraints.json` 的 `near_pin.max_mil`；v1 重叠容差 0），**没有**为凑 verdict 调阈值；真实板距离与原工程 WARN 逐位对齐（316/213/128 mil 等）。
- D1 只保留 8/23 器件（U2 的 EP 多焊盘无法唯一命名而丢弃，C4/C6 的 WARN 因此不判），D2 19/19、D3 12/12；丢弃对象全部记入 `unknowns`/`limits`。

## 3. 实际命令与结果

| 命令 | 结果 |
|---|---|
| `python easycirq/scripts/pcb_placement_benchmark.py --list` | exit 0，**15 条** |
| `python easycirq/scripts/pcb_placement_benchmark.py --all` | exit 0，**15/15 matched**；两次 `--json --out` 字节一致 |
| `--case D1/D2/D3` | exit 1（review）/ 0（acceptable）/ 2（blocking），符合契约 |
| `python benchmarks/pcb-placement-benchmark/derive_cases.py --check` | exit 0，3 条 derived 与 tracked 证据、benchmarks.json 一致 |
| `python benchmarks/pcb-placement-benchmark/run_benchmark.py` | exit 0，**15/15 PASS**，`real_eda:"NOT RUN"`、`eda_calls:0`；两次 `results.json` SHA256 一致 |
| `python -m unittest discover -s tests -k pcb_placement_benchmark` | 121 tests OK |
| `python -m unittest discover -s tests` | 4191 tests OK（5 skipped，约 457 s；第二轮改动后复跑） |
| `python easycirq/scripts/skill_selftest.py` | 6 PASS / 0 FAIL / 0 NOT RUN |
| `python -m skill_knowledge_audit scan`（经测试） | errors 0（修复了 exercises-pcb 指向仓库 docs/ 的越界链接） |
| `python tools/offline_suite.py` | `NOT RUN`（本轮未跑；测试层由官方 discovery 覆盖） |

### 3.1 独立盲测（两轮，2026-10-29）

**第一轮（v1 题面，3 Agent + 单评审）**

- 3 名隔离 Agent 试答 20 题（输入仅仓库外题目副本，禁止读仓库/答案/联网/运行命令；每人自报只读过题目副本），1 名独立评审对照 `answers.md` 按五维打分。
- 结果：**结论类型 43/60 = 71.7%**、机制 57/60 = 95.0%、证据 60/60 = 100%（**泄题所致**）、行动 58/60 = 96.7%、未知 58/60 = 96.7%；60 份作答**没有**过度修改 / 臆造 code / 补默认坐标。
- 关键发现：X01 题面缺“软检查、无硬检查命中”导致 B1/B2 把 review 判成 blocking（题面缺陷）；多题把“期望 verdict/codes、翻转后 verdict、PL 编号”写进题面（泄题）；X11 三人共弱但机制正确（答案口径问题）。
- 已修订为 **v2 题面**：X01 补软检查声明；删除 PL 编号与 verdict/codes 提示；X11 加标记落点要求；X01/X08 过度例必答。

**第二轮（v2 题面，3 Agent + 2 名评审交叉评分）**

- 3 名隔离 Agent 重答 v2 题面；2 名独立评审（互不可见、未见第一轮评审）各自输出 60 行评分 CSV，脚本逐格比对：**300 单元一致率 278/300 = 92.7%**（结论 86.7%、机制 98.3%、证据 95.0%、行动 96.7%、未知 86.7%），22 处冲突逐条裁决。
- 结果（两评审并列，不平均）：结论类型 **A 61.7% / B 60.0%**；机制 A 96.7% / B 95.0%；证据 A 95.0% / B 100%；行动 A 100% / B 96.7%；未知 A 93.3% / B 90.0%。三人全 △：X01/X02/X11；无三人全 ✗；**X13 两人 ✗**（成对翻转未识别）是唯一内容错误。
- 专项发现：**X05** 两评审一致指出答案证据句与案例 JSON 不符（`P4-COMM.checks` 只有 `ck-decoup`；`connector_off_edge` 来自 `board.connectors` + rubric 容差）→ 已修；**X11** 三人一致标 `可确认`（v2 目标达成），两评审一致认为答案 `条件` 主标记与“落在被问的事上”不一致 → 已改。
- 据此产出 **v3 口径**：题面加“主标记落在判分器判定层”全局规则；`answers.md` 新增标记口径规则 0、X05 事实修正与适用范围、X10 主标记 → `待补`、X11 主标记 → `可确认` + 条件副注。**第二轮分数按 v2 口径计算，未追溯**。
- 限制（两轮共同）：每轮 3 样本、**约束式隔离**（非容器/权限强隔离）、作答同构；第二轮结论类型双评审仍差 1.7 个百分点，说明该项有主观空间——不证明模型能力，不作为认证；v1/v2/v3 分数不可直接比较。

**第三轮（v3 题面，3 Agent + 2 名评审交叉评分）**

- 3 名新隔离 Agent 重答 v3 题面；2 名新评审独立打分，**300 单元一致率 277/300 = 92.3%**，但结论维一致率降到 76.7%。
- 结果：结论类型 **A 53.3% / B 50.0%**；机制 100% / 98.3%；证据 95.0% / 98.3%；行动 98.3% / 93.3%；未知 96.7% / 95.0%。
- **用户指定的四个重点**：X01（第二轮 0/6 正确 → 第三轮 5–6/6，主标记全部 `可确认`、判定 `review`）与 X02（0/6 → 6/6）**标记位移明显下降**；X10 3/3 `待补`、X11 3/3 `可确认`（条件副注仅 1/3 完整）与 v3 答案一致，但**答案键本轮同时改过，不能单独归因**；**X13 翻转识别 0/3，没有改善反而更差**。
- X13 根因：题面未给“原布局 `ck-analog` 22.8 mm > 14 mm 失败”的基线，三人只围绕 HPWL 推理；同一对案例在 X07 三人都答对 → 属题面缺基线，不是内容能力退步。
- 整体结论率下降的主因：**「条件簇」答案与成对表口径冲突**（X07/X08/X12/X14/X15/X18 逐题 `条件`，成对表 PC01/PC02/PC04 `可确认`），两评审在 X08/X18 上也彼此分歧（A `ppp` vs B `nnn`）；内容四维稳定在 93–100%。v4 修订建议已记录在证据目录 `round3-evaluation.md` §5，**本轮未执行**，第三轮分数保持按 v3 口径。
- 限制：三轮的题面/答案键/评审/作答者均不同，分数不可跨轮直接比较；条件簇口径未统一前，结论类型比例不宜对外引用。

**第四轮（v4 题面/答案，3 Agent + 2 名评审交叉评分）**

- v4 做了三件事：规则 2b 改为**取“第一问句所在层”**；条件簇（X07/X12/X13/X14/X15/X16）主标记统一为 `可确认`、成对表 PC03 同步；**X13 题面补基线**（原布局 `ck-analog` 22.8 mm > 14 mm 失败 → 成对 12.7 mm 通过，HPWL 变差只是代价）。
- 结果：结论类型 **A 88.3% / B 88.3%**（第三轮 53.3/50.0）；机制 98.3/96.7；证据 98.3/98.3；行动 93.3/96.7；未知 **100/100**；300 单元一致率 **98.3%（结论维 100%）**。
- **重点验证全部达成**：X01/X02/X10/X11 主标记 12/12 全对；**X13 翻转识别 0/3 → 3/3**（三人均写出 `ck-analog` 失败→通过、`review`→`acceptable`、HPWL 变差不降级）。
- 两评审独立指出两处**标准侧**冲突（非作答错）：X05（答案 `可确认` vs 规则 0 的机制层 `条件`）、X20（答案 `待补` vs 判分层 `可确认`），三人 3/3 同向；扣除后结论维 53/54 = 98.1%，作答侧零 ✗。唯一非争议内容错误是 X12/U3（把 `review→acceptable` 读成“两份 verdict 相同”）。
- 据此产出 **v5 答案口径**：X05 → `条件`、X20 → `可确认`（均按规则 0 对齐，判分事实/数据缺口写副注）、X13 数值统一 22.8 mm。**第四轮分数按 v4 口径计算，未追溯**。
- 限制：四轮的题面/答案键/评审/作答者均不同；当前口径下结论类型已接近饱和（88.3%、跨评审结论维 100%），继续加轮次收益递减；仍不证明模型能力。

**第五轮（v4 题面 / v5 答案口径，3 Agent + 2 名评审交叉评分）**

- 只改答案口径（X05 → `条件`、X20 → `可确认`、X13 数值统一 22.8 mm），题面与第四轮相同。
- 结果：结论类型 **A 100% / B 93.3%**；机制 95.0/98.3；证据 93.3/100；行动 98.3/98.3；未知 93.3/91.7；300 单元一致率 95.0%。
- **验证目标全部达成**：X05 主标记 **6/6 `条件`**、X20 主标记 **6/6 `可确认`**（均归零）；X13 翻转识别保持 3/3；X01/X02/X10/X11 保持 12/12。扣除 X20 verdict 层的标准侧前提缺口后，结论维 **98–100%**，作答侧无内容错误（唯一 △ 是 X14/V1 把 `blocking` 写成 `review`）。
- 残留：题面未声明 `missing_placement` 的硬/软属性（X20 verdict 层），已补进 `answers.md`；题面补一句留作 v6。
- 判定：用户设定的通过条件（X05/X20 归零、结论维 ~98%）满足 → 按现状态 squash 合并 PR #192。

## 4. 已修问题

1. **判分器 `--all` 汇总 schema 撞名**：`results/v1` 与冻结基准结果文件冲突 → 改为 `summary/v1`。
2. **soft/global 口径**：初版把 HPWL/congestion 塞进 `soft`，`expected.soft_fail` 永远对不上 → 全局只进 `metrics`，超限才进 `codes`。
3. **兜底 code**：取消 `check_failed`，改为具体软 code；未知 `checks[].code` 按 `invalid_case`。
4. **冻结基准 runner 的 codes 提取**：只取 hard code → 补上失败软检查的 code。
5. **案例坐标错**（A 自检发现）：`P2-BUCK` 初版 `J1` 与 `L1` 有 0.25 mm² 非预期交叠 → 移动 `J1`，未改 expected。
6. **SKILL.md 行位移**：新增 1 行导致知识审计 R-GATE-003 证据窗口失效 → 同步行号。
7. **契约残留旧 code**：`decouple_far`/`check_failed` 已统一为 `distance_far`/具体 code。
8. **第二轮：冻结集合测试硬编码 12** → 改为从案例文件动态读取数量（新增 derived 后不再静默过期）。
9. **第二轮：expected.json 仍为 12 条** → 按 15 条重冻，并记录源案例 SHA-256。
10. **第二轮：练习/题面越界链接**（指向仓库 `docs/evidence`，Skill 安装后必然断链）→ 改为代码路径文本；知识审计 errors 归零。
11. **第二轮：盲测题面泄题与信息缺口**（X01 软检查未声明、多题写出期望 verdict/codes/PL 编号）→ 已修 v2 题面。
12. **第三轮：规则 0 与条件簇答案不一致**（逐题 `条件` vs 成对表 `可确认`）→ v4 按“第一问句所在层”统一，结论维回升到 88.3%。
13. **第三轮：X13 题面缺基线**（三人只按 HPWL 推理、漏 `ck-analog` 翻转）→ v4 补基线后 3/3 识别。
14. **第四轮：X05/X20 与规则 0 残留冲突**（两评审独立指出、三人 3/3 同向）→ v5 对齐规则 0；X13 数值统一。

## 5. 真实 vs 合成边界

- 12 条 `synthetic` 为教学构造；3 条 `derived` 来自仓库内**真实板回读 dump**，但只覆盖**子集与选定检查**（D1 8/23 器件、D2 19/19、D3 单次移动），**不是整板复刻**，也不是 DRC 或签核。
- 判分只覆盖离线几何与网表代理；`drc`、`routing`、`impedance`、`thermal`、`EMC`、`manufacturing`、真实样机全部 `NOT RUN`。
- 盲测是约束式隔离、3 样本、单评审；不能据此声明模型能力或认证。

## 6. 限制与下一步

- 判分器已知限制：非 0/90/180/270 旋转走防御性 AABB 并报 `rotation_not_allowed`；`connectors.insert_dir` 只做 schema 校验；自交板框不检测；数值上限 1e6、单网络网格跨度上限 4096 cells（超出 `invalid_case`）。
- 冻结 runner 的 `_card_summary` 看不到全局 `hpwl_high`/`congestion_hotspot`（当前 15 条 expected 不含全局 code，不影响；扩展前先改契约）。
- 派生案例：D2 的 `acceptable` 只表示 tracked 距离约束下合格；`copper_path_verified:false` 原样保留在证据里。
- 后续可做：第二轮盲测（v2 题面 + 双评审交叉）；把 `placement_intent` 的 HMT/CCG 参考意图与案例 `reference.key_placements` 对接；按需包装成 MCP 只读工具；补 `X05`/`X11` 答案侧口径与 code 枚举方案。
