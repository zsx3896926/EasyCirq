# 第三轮工作包覆盖复核（coverage review）

- 复核对象：`docs/round3/execution-protocol.md`、`docs/round3/capability-matrix.md`、`docs/round3/backlog.md`、`docs/task-ledger-round3.md`。
- 复核基线：worktree `C:/Users/jlc/work/hds-round3`，`HEAD=dc62f2073b99764a5a15cdd31020c856da75e50e`；复核时 `origin/main=0fe5cf80ab0dd8196c900ed9878bad40d4f6c8b9`（比 `dc62f20` 多 3 个 docs-only 提交）。
- 复核性质：只读；除本文件外未修改仓库文件；未提交、未推送、未执行 EDA 写入。
- 证据根：`AUD = C:/Users/jlc/work/hw-deepdive-scratch/round3-audit/`；仓库内路径相对仓库根。

## 0. 复核口径

### 0.1 两个状态维度

本文把“工作包覆盖”与“交付状态”分开，避免把“审计写到了”误读成“能力已完成”：

| 维度 | 取值 | 判定 |
|---|---|---|
| 审计覆盖 | `COVERED` / `PARTIAL` / `MISSING` / `CONTRADICTORY` | 四份文档是否对该工作包的每个子项给出了可定位判断，即使判断是 `NOT RUN`/`BLOCKED` |
| 交付状态 | `DONE` / `PARTIAL` / `NOT RUN` / `BLOCKED` / `DEFECT` / `GAP` | 沿用 `docs/task-ledger-round3.md:13-20` 的定义；同一项同时有完成部分与缺陷时按最低状态记 |

`COVERED` 只表示“审计有判断”，不表示“交付已完成”。例如 B 组（回读/属性/身份等）审计覆盖为 `COVERED`，但交付状态是 `DEFECT`。

### 0.2 任务书原文不在仓库

本轮任务说明给出的工作包是 `A1-A5 / B1-B8 / C1-C7 / D1-D7 / E1-E10 / F1-F8 / G1-G8 / H1-H8 / I1-I7 / J1-J7 / K / L1-L7`，共 83 个编号位。仓库内没有这份任务书原文，也没有逐项清单：

- `grep -rn "C1–C7\|D1–D7\|H6" docs/` 无匹配；
- `docs/task-ledger-round3.md:58` 只说明“A–L 是第三轮工作包编号，与 round2 的 A1–H5 不是同一套编号”，但没有给出与第三轮任务书编号的映射；
- `docs/task-ledger-round3.md:41-56` 的 A–L 是**审计域**编号，不是任务书编号：台账 C 是几何、台账 D 是 F1、台账 K 是评测；任务书 C 是 F1、任务书 D 是几何、任务书 K 是项目组合。

因此本文只能按任务说明中的组名和编号区间做**组级**复核；任务书若还有组内子项定义，本文无法逐项证明覆盖。这是 CR-01 的直接来源。

### 0.3 本次复核实际执行的命令与结果

```text
git rev-parse HEAD                          -> dc62f2073b99764a5a15cdd31020c856da75e50e
git rev-parse origin/main                   -> 0fe5cf80ab0dd8196c900ed9878bad40d4f6c8b9
git log --oneline dc62f20..origin/main      -> 3 commits (0fe5cf8, a2fc97a, f0068c8)
python -B -m unittest discover -s tests     -> Ran 141 tests in 6.315s / OK
```

统计脚本结果：

```text
capability-matrix.md 状态行                  -> 42 行：VERIFIED 12 / PARTIAL 10 / NOT VERIFIED 19 / BLOCKED 1
task-ledger-round3.md 任务 ID                -> 147 条（A 9, B 12, C 11, D 12, E 15, F 15, G 14, H 13, I 12, J 11, K 8, L 15）
backlog.md 条目                              -> 55 条（P0 12 / P1 22 / P2 13 / P3 8）
台账 ID 在 backlog 中被引用                  -> 126/147；21 条未被引用
execution-protocol.md 的 json 代码块         -> 22 个，22 个均可解析
```

四份文档的文件事实（用于 CR-07 的可追溯性判断）：

| 文件 | 字节 | SHA256 前 16 位 | mtime |
|---|---:|---|---|
| `docs/round3/execution-protocol.md` | 69,437 | `cca25467e3ae4d64` | 2026-10-22 15:43:22 |
| `docs/task-ledger-round3.md` | 78,176 | `392aaa9f32b93da5` | 2026-10-22 15:45:58 |
| `docs/round3/backlog.md` | 24,236 | `d52581b8f5141108` | 2026-10-22 15:46:13 |
| `docs/round3/capability-matrix.md` | 31,177 | `8002148e0e6dfe3b` | 2026-10-22 15:47:34 |

### 0.4 本文不复述的内容

台账已经逐条记录的实现缺陷（A-01/A-02/B-01/B-09、C-01/C-03、D-01/D-02、E-01/E-03、G-01/G-02、H-04/H-05、I-01/I-02 等）不在本文重复描述；本文只回答“任务书工作包有没有被覆盖、覆盖状态是否自洽、证据是否可追溯、有没有超出证据的声明”。

## 1. 结论摘要

- 12 个工作包组中，审计覆盖 `COVERED` 5 组（B/C/D/E/F）、`PARTIAL` 5 组（A/G/I/J/L）、`MISSING` 2 组（H/K）。没有任何一组可以判为“全部完成”。
- 最严重的三个覆盖缺口：任务书工作包没有映射表（CR-01）；H1-H8 评测工作包基本不存在（CR-02）；backlog 漏掉 9 个仍未关闭的台账项（CR-03）。
- 最严重的过度声明：F1 的“保存/重开”和 93/93 `verified` 在矩阵顶层与台账 L-15 中被写成 VERIFIED/DONE，而同一批文档的 B-09/A-02/A-04/A-05 已证明比较域会产生假阳性（CR-04）。
- 状态口径未统一：E/F 组汇总写 `GAP`，组内却有多个 `DEFECT`；协议 §7.3 又给 `DONE` 下了与台账不同的定义（CR-05）。
- 基线、写入边界与证据清单的追溯性不足：台账称 `dc62f20=origin/main`（实际已是 `0fe5cf8`），矩阵称“唯一写入文件”（实际四份文档并存且矩阵最后写入），多数证据没有逐文件哈希（CR-06/CR-07/CR-12）。

## 2. 工作包覆盖总表

| 任务书工作包 | 名称 | 审计覆盖 | 交付状态 | 主要对应产物 | 必须先补的事 |
|---|---|---|---|---|---|
| A1-A5 | 能力地图/等级/证据清单/风险验收/未完成汇总 | PARTIAL | PARTIAL | matrix §0-§6；protocol §1；ledger §1/§15/§16；backlog | A4 风险登记缺失；A1 缺分类边界；A3 证据清单无逐文件哈希；A5 有 21 条台账项未进 backlog |
| B1-B8 | 回读/属性/跨页身份/过期快照/故障注入/幂等/保存重开/版本会话 | COVERED | DEFECT | ledger A/B；protocol §2-§4 | 8 个子项均已有判断，但“故障注入”没有测试套件；保存/重开状态被过度声明 |
| C1-C7 | F1 样板 | COVERED | PARTIAL + DEFECT | ledger D；`docs/evidence/f1-2026-10-22/` | 只有原理图；PCB/DRC/ERC/制造/样机 NOT RUN；C4 网表 diff 缺失 |
| D1-D7 | 几何与排版 | COVERED | PARTIAL + DEFECT | ledger C；matrix 排版行；ledger D-10 | 无 snapshot→layout 适配器；8/8 只证 recall；协议无排版等级 |
| E1-E10 | PCB 闭环 | COVERED | GAP + PARTIAL | ledger E；matrix §3；`AUD/pcb-closed-loop/` | `eda_exec.py` 无 PCB 命令族；真实布线/DRC 基线/全在线 NOT RUN 或 BLOCKED |
| F1-F8 | 嘉立创衔接 | COVERED | GAP + BLOCKED | ledger F；matrix §4-§5 | BOM/CPL/Gerber/manifest 缺失；实时库存/价格/SMT/DFM/下单 BLOCKED |
| G1-G8 | 内容审计 | PARTIAL | DEFECT | ledger G/H/I/J | G-13/I-12 明确仍有未审内容；无内容覆盖矩阵；3 个脚本未审 |
| H1-H8 | 评测 | MISSING | NOT RUN | ledger K；J-02/J-03；protocol §6 | H1-H5 无定义、H6-H8 从未出现；无评测计划、无原始 transcript |
| I1-I7 | 新手与工程师 | PARTIAL | NOT RUN | ledger K-06/K-07；J-08；protocol §6 | 无真实新手/工程师试验；双层 message 只是规范 |
| J1-J7 | 产品化 | PARTIAL | PARTIAL | ledger J-04/J-05/J-06/J-09；K-08；L-02 | 无干净机安装/升级/回滚/宿主矩阵；包分层未做 |
| K | 项目组合 | MISSING | NOT RUN | 仅 ledger D-12 一句 F2-F5 NOT RUN | 无项目组合台账、目标等级、选择标准、F2-F5 计划 |
| L1-L7 | 结构维护 | PARTIAL | PARTIAL | ledger L-01..L-15；J-10/J-11 | 有一次性状态修正，无 CI/维护流程；证据 manifest 校验未落地 |

## 3. 覆盖映射（任务书编号 → 审计产物）

这张表用于消除编号歧义；没有它，读者会把台账 C（几何）当成任务书 C（F1）、把台账 K（评测）当成任务书 K（项目组合）。

| 任务书 | 名称 | 对应台账章节 | 对应矩阵/协议 | 映射问题 |
|---|---|---|---|---|
| A1-A5 | 能力地图/等级/证据清单/风险验收/未完成汇总 | 无单一章节；散在 §1、§15、§16 | matrix §0-§6；protocol §1 | 无汇总表；A4 无对应物 |
| B1-B8 | 回读/属性/跨页身份/过期快照/故障注入/幂等/保存重开/版本会话 | §3 A-01..A-09；§4 B-01..B-12 | protocol §2-§4 | 基本逐项可对应；故障注入只有复现脚本，没有测试矩阵 |
| C1-C7 | F1 样板 | §6 D-01..D-12 | matrix F1 行；`docs/evidence/f1-2026-10-22/` | 台账 C 是几何，不是 F1；必须显式写“C→D” |
| D1-D7 | 几何与排版 | §5 C-01..C-11；§6 D-10 | matrix 排版两行 | 台账 D 是 F1，不是几何；必须显式写“D→C” |
| E1-E10 | PCB 闭环 | §7 E-01..E-15 | matrix §3；protocol §7.5 | 可对应；协议没有 PCB 比较域 |
| F1-F8 | 嘉立创衔接 | §8 F-01..F-15 | matrix §4-§5 | 可对应；实时数据 BLOCKED |
| G1-G8 | 内容审计 | §9 G、§10 H、§11 I、§12 J-06 | 无 | 分散在四个台账章节；无内容覆盖表 |
| H1-H8 | 评测 | §13 K-01..K-08；§14 L-07 | protocol §6（仅输出层） | 台账 K 是评测；H6-H8 没有任何文字 |
| I1-I7 | 新手与工程师 | §13 K-06/K-07；§12 J-08 | protocol §6 | 只有“NOT RUN”与规范，没有试验 |
| J1-J7 | 产品化 | §12 J-04/J-05/J-06/J-09；§13 K-08；§14 L-02 | 无 | 无安装/升级/回滚条目 |
| K | 项目组合 | 无；仅 §6 D-12 提 F2-F5 NOT RUN | 无 | 台账 K 不是项目组合 |
| L1-L7 | 结构维护 | §14 L-01..L-15；§12 J-10/J-11 | 无 | 有状态修正，无维护机制 |

## 4. Findings（12 条，按严重度排序）

### CR-01 [high] 任务书工作包没有可复核的覆盖映射，编号互相冲突

**结论**：四份文档没有任何一处按任务书的 83 个编号位逐项回答“覆盖/未覆盖”。台账的 A–L 是审计域编号，与任务书编号在 C/D/K 三处含义不同；任务书原文也不在仓库，导致覆盖结论无法独立复核。

**证据**：

- `docs/task-ledger-round3.md:41-56` 把 A–L 定义为审计域；`:58` 只提醒“与 round2 的 A1–H5 不是同一套编号”，没有提第三轮任务书编号。
- 任务书 C 是 F1 样板，台账 C 是“原理图几何检查与 8 类基准”（`docs/task-ledger-round3.md:30`），F1 实际在台账 D（`:31`）。
- 任务书 K 是项目组合，台账 K 是“评测、新手/工程师路径与行为验证”（`docs/task-ledger-round3.md:38`）。
- `grep -rn "C1–C7\|D1–D7\|H6" docs/` 无匹配；仓库没有任务书原文或逐项清单。

**影响**：读者无法判断 83 个编号位哪些真的被审计过；用台账 ID 汇报时会把 C/D/K 的意思弄反；下一轮无法按任务书逐项销账。

**下一轮动作**：在 `docs/round3/` 增加 `workpackage-coverage.md`（或在本文追加）一张 83 行表：任务书 ID、组名、对应台账 ID、审计覆盖、交付状态、证据路径、缺口。给任务书 ID 加前缀（如 `TB-C1`），给台账 ID 保留 `C-01`，禁止裸用字母。把任务书清单的只读副本或摘要提交进仓库，作为复核输入。

### CR-02 [high] H1-H8 评测工作包基本不存在：H6-H8 从未出现，H1-H5 也没有定义

**结论**：任务书要求 H1-H8 评测，四份文档最多提到 H1-H5，且明确说“仓库没有 H1-H5 定义”；H6、H7、H8 在 `docs/round3/` 和台账中零出现。没有任何评测计划、评测用例、原始 transcript 或评分记录。

**证据**：

- `docs/task-ledger-round3.md:82` 只列 H1–H5；`:288`（K-05）和 `:305`（L-07）写“仓库没有 H1–H5 定义”。
- `grep -rn "H6\|H7\|H8" docs/round3 docs/task-ledger-round3.md` 无结果。
- `docs/round3/backlog.md:61-62` 的 P2-08/P2-09 也只写 H1–H5。
- `docs/evidence/deepdives-2026-10-22/README.md` 的旧试答按 J-03 是非盲、无过程记录、无对照；新盲测未运行（`docs/task-ledger-round3.md:268`）。

**影响**：8 个评测项中至少 3 个完全没有定义，另外 5 个不可验收；K-01..K-08 的“评测”实际是评测欠账清单，不是评测结果。

**下一轮动作**：新增 `docs/round3/evaluation-plan.md`，为 H1-H8 各写：目标、输入资产、期望行为、禁止宣称、证据要求、通过阈值、当前状态。至少把 H1-H5 与现有 `scenarios.json`、`tests/test_scenarios.py`、141 项回归、深潜试答映射起来；H6-H8 若本轮不做，必须写 `NOT RUN` 与解阻条件。先执行 5 个高风险场景并保存原始输入/输出/评分。

### CR-03 [high] backlog 漏掉 21 个台账项，其中 9 个仍是未关闭的 DEFECT/GAP/NOT RUN

**结论**：台账 147 条任务，backlog 只有 55 条，且只引用了 126 个台账 ID；21 个 ID 完全未出现。被漏掉的不是只有 DONE 项，还包括 B-11、B-12、D-12、F-15、G-13、H-11、H-13、I-10、I-12 等仍未关闭的项。A5“未完成汇总”因此不完整。

**证据**：

- 统计：147 个台账 ID，126 个在 backlog 中被引用，21 个未引用。
- 未引用的活动项：`B-11`（`settle_ms` 被静默丢弃，`docs/task-ledger-round3.md:116`；代码 `eda_exec.py:727-755` 接受、`:1401` 丢弃）、`B-12`（netflag 空坐标会让 `_round` 抛错，`:117`；代码 `eda_exec.py:1186`）、`D-12`（F2-F5 NOT RUN，`:154`）、`F-15`（制造/样机 NOT RUN，`:198`）、`G-13`（p04-p14 未审，`:218`）、`H-11`（电池台架 NOT RUN，`:237`）、`H-13`（f02/f09/f13 未逐页，`:239`）、`I-10`（原厂 PDF/实测 NOT RUN，`:256`）、`I-12`（数字/MCU/无线卡未审，`:258`）。
- `docs/round3/backlog.md:83` 的 DoD 要求 P0 项“有代码/文档修改 + 复跑证据；不能只改文档”，但 P0 中 L-01/L-03/L-04/J-01 本身就是文档项，按字面永远无法关闭。

**影响**：下一轮按 backlog 执行会漏掉真实缺陷和审计欠账；“P0 全部关闭”的 DoD 自相矛盾，无法作为验收门禁。

**下一轮动作**：在 backlog 增加 `未纳入本轮排期` 表，对 21 个未引用 ID 逐条写原因/owner/解阻条件；至少把上述 9 个活动项转成 P1/P2 条目。把 DoD 拆成三类：代码类（必须改代码+复跑）、文档类（必须改文档+核对命令）、证据类（必须新增原始证据）。加一个脚本/测试：台账中状态非 DONE 的 ID 必须出现在 backlog 或 deferral 表中。

### CR-04 [high] F1 的“保存/重开”和 93/93 verified 被写成 VERIFIED/DONE，但同一批文档已证明比较域会产生假阳性

**结论**：矩阵顶层把“保存重开”列为可判 VERIFIED，台账 L-15 也以 93/93 verified、reopen match 判 DONE；但矩阵自己的“重开一致性判据”行是 PARTIAL，台账 B-09 明确说删 1 个 netport、翻 mirror、删同号重复件之一仍会 match。把“保存调用成功/窄域比较通过”写成“保存重开已验证”，正是任务要求重点检查的过度声明。

**证据**：

- `docs/round3/capability-matrix.md:13`：“读取、创建、连接、保存重开、PNG/网表导出可判 VERIFIED。”
- `docs/round3/capability-matrix.md:96`：“保存 + 关闭重开”行状态 VERIFIED，但限制列写 `save` 返回 true 只是调用成功、`closed_session=null`、无页身份校验。
- `docs/round3/capability-matrix.md:97`：“重开一致性判据”行 PARTIAL，明确列出删 netport/翻 mirror 仍 match。
- `docs/task-ledger-round3.md:114`（B-09）：比较域只有 parts/wires/netflags；删 netport/mirror/同号件仍 match。
- `docs/task-ledger-round3.md:313`（L-15）：以 93/93 verified、`reopen-check.json match` 判 DONE。
- F1 证据本身：`docs/evidence/f1-2026-10-22/reopen-check.json` 的 `closed_session=null`，比较只覆盖 parts/wires。

**影响**：读者会把“保存调用成功 + 窄域比较”引用为“持久化已验证”；后续 PCB/制造/交付会继承这个假阳性基线。

**下一轮动作**：把矩阵该行拆成两行：`save 调用`（VERIFIED，仅证明调用成功）与 `持久化/重开核对`（PARTIAL，比较域未闭合）。把矩阵 `:13` 改为“保存调用成功；重开核对仅 PARTIAL”。把台账 L-15 降为 PARTIAL，或改名为“基线可复跑（但 F1 验证域窄）”。加一条状态规则：当比较域自身为 PARTIAL 时，引用它的持久化行不得标 VERIFIED。

### CR-05 [medium] 状态词与“最高状态”没有统一定义：E/F 汇总与组内 DEFECT 冲突，协议的 DONE 又与台账 DONE 冲突

**结论**：台账 §1 的“本轮最高状态”没有定义优先级。E 组汇总写 GAP，但 E-03/E-05 是 DEFECT；F 组汇总写 GAP，但 F-03/F-05/F-08/F-11 是 DEFECT。更严重的是，协议 §7.3 用 `DONE` 表示“代码事实存在、未在真实 EDA 重跑”，而台账 `:15` 用 `DONE` 表示“本轮复跑/复核有可复核证据、交付物与声明范围一致”。同一个词在两份文档里含义不同。

**证据**：

- `docs/task-ledger-round3.md:32-33`：E/F 最高状态均写 GAP。
- 组内 DEFECT：E-03 `:164`、E-05 `:166`；F-03 `:186`、F-05 `:188`、F-08 `:191`、F-11 `:194`。
- `docs/task-ledger-round3.md:15` 的 DONE 定义。
- `docs/round3/execution-protocol.md:1206`：“下表只陈述代码事实；未在真实 EDA 会话重跑。`DONE` 表示基础能力存在，不表示已满足本协议全部字段。”
- `docs/round3/backlog.md:83`：P0 的“不能只改文档”与文档类 P0 冲突（见 CR-03）。

**影响**：同一组任务在不同文档里可能被读成不同严重度；“最高状态”无法排序；协议与台账的 DONE 不能互相引用；L-02 想统一的六级定义被协议自己先破坏。

**下一轮动作**：定义唯一的状态优先级（建议 `DEFECT > BLOCKED > PARTIAL > GAP > NOT RUN > DONE`，并在台账 §0 写明），把 §1 的“最高状态”改为按优先级计算或直接给状态计数。协议 §7.3 把 `DONE` 改名为 `IMPLEMENTED_BASIC`/`CODE_ONLY`，并加一句“本表 DONE 不沿用台账 DONE 定义”。backlog DoD 按代码/文档/证据分类（同 CR-03）。

### CR-06 [medium] 基线自相矛盾：台账称 `dc62f20=origin/main`，矩阵称 `origin/main=0fe5cf8`

**结论**：台账头部把审计基线写成 `dc62f20` 且等于 `origin/main`；矩阵头部明确写 `origin/main` 已到 `0fe5cf8`。`git rev-parse origin/main` 实测为 `0fe5cf8`，且该提交时间 2026-10-22 14:19 早于台账写入时间 15:45；这说明该提交在台账写入前已存在，台账至少没有重新核对远端 ref，或使用了过期的本地 ref。

**证据**：

- `docs/task-ledger-round3.md:3`：“HEAD `dc62f20`（= `origin/main`...）”。
- `docs/round3/capability-matrix.md:6`：“审计期间 `origin/main` 已到 `0fe5cf80...`（`dc62f20` 之后 3 个提交）。”
- 实测：`git rev-parse origin/main` = `0fe5cf80ab0dd8196c900ed9878bad40d4f6c8b9`；`git log --oneline dc62f20..origin/main` = 3 个 docs-only 提交；`0fe5cf8` 提交时间 2026-10-22 14:19:58 +0800。

**影响**：读者会误以为四份文档覆盖了当前 `origin/main`；实际上 3 个 README/NOTICE 提交未审。基线不一致也会让“本轮唯一基线”无法引用。

**下一轮动作**：把台账 `:3` 改为“审计基线 `dc62f20`；复核时 `origin/main=0fe5cf8`，3 个 docs-only 提交未覆盖”。在证据索引/运行清单中保存 `git rev-parse HEAD`、`git rev-parse origin/main`、`git log --oneline dc62f20..origin/main` 的原始输出。四份文档使用同一句基线声明。

### CR-07 [medium] 矩阵称“本轮唯一写入仓库的文件”，但四份文档并存且矩阵最后写入；没有运行清单可追溯

**结论**：矩阵 `:7` 写“本文件是本轮唯一写入仓库的文件”，但同目录已有 execution-protocol、task-ledger、backlog 三份文档；文件 mtime 显示矩阵 15:47 最后写入，晚于协议 15:43、台账 15:45、backlog 15:46，因此该声明在写入时已不成立。四份文档没有共同的 SHA256/mtime/author/来源清单。

**证据**：

- `docs/round3/capability-matrix.md:7` 的唯一写入声明。
- `docs/task-ledger-round3.md:4` 说本轮只写台账与 backlog，并指出矩阵/协议是“并发产物”。
- 文件 mtime 表见 §0.3；矩阵 mtime 15:47:34 晚于其余三份。
- `git status --porcelain` 显示 `?? docs/round3/` 与 `?? docs/task-ledger-round3.md`，全部未跟踪，没有提交时间可裁决。

**影响**：无法确定哪份文档是权威版本、哪份被谁在何时写入；“本轮唯一写入”这类声明无法复核，影响交付可信度。

**下一轮动作**：新增 `docs/round3/run-manifest.json`：每份文档的 path/SHA256/bytes/mtime/author/source，以及生成命令。把矩阵 `:7` 改为“本审计域写入；同期另有 execution-protocol/task-ledger/backlog 并发产出”。四份文档一起提交或明确标注为未提交工作区产物。

### CR-08 [medium] A4“风险验收”缺失：没有风险登记/waiver 记录

**结论**：任务书 A4 要求风险验收，但四份文档没有任何风险登记表、接受人、接受日期、残余风险或复评触发条件。协议允许 waiver（`execution-protocol.md:280,294`），但没有实际 waiver 记录；backlog 的 P0/P1 只是修复排序，不是风险接受。

**证据**：

- `grep -rni "风险登记\|risk register\|accepted risk\|waiver.*登记" docs/round3 docs/task-ledger-round3.md` 无结果。
- `docs/round3/execution-protocol.md:280` 要求 waiver 有 `reason/owner/date/scope`；`:294` 说只能写“在 waiver 范围内通过”；全文没有 waiver 实例。
- `docs/round3/backlog.md` 只有优先级/影响/证据，没有接受人/日期/残余风险。
- 台账有 14 条 confirmed findings（`:8`）和 3 条 BLOCKED（E-10/F-14/L-13），但没有“接受/修复/延后”的决策表。

**影响**：无法区分“已知并接受的风险”和“待修缺陷”；交付时无法说明哪些风险由谁承担；下一轮可能把已接受的风险重新当缺陷，或把未接受的风险当已完成。

**下一轮动作**：新增 `docs/round3/risk-register.md` 或在 backlog 增加一节：risk ID、关联 finding、严重度/概率、影响工作包/等级、决策（fix/accept/defer）、owner、日期、残余风险、复评触发。先填入 14 条 confirmed findings 与 3 条 BLOCKED。

### CR-09 [medium] K“项目组合”缺失：只有 F1 + EvidenceDemo，没有 F2-F5 计划、目标等级或选择标准

**结论**：任务书 K 是项目组合，但四份文档没有任何项目组合台账。台账 `D-12` 只有一句“F2–F5 未开始”；backlog 没有 F2-F5 条目；仓库证据只有 F1 与 EvidenceDemo 两个项目。没有目标等级、选择标准、依赖关系或下一项目优先级。

**证据**：

- `docs/task-ledger-round3.md:154`（D-12）：“F2–F5 未开始；无可复核项目证据”。
- `docs/task-ledger-round3.md:80`（round2 映射）：F2–F5 NOT RUN。
- `grep -rni "项目组合\|portfolio" docs/round3 docs/task-ledger-round3.md` 无结果。
- `docs/evidence/` 只有 `f1-2026-10-22` 与 `eda-2026-10-21`（EvidenceDemo）。

**影响**：任务书 K 没有交付物；无法回答“下一个项目做什么、做到哪级、需要什么证据”；F1 是唯一真实样板且只到原理图，不能支撑组合级结论。

**下一轮动作**：新增 `docs/round3/project-portfolio.md`：项目 ID（F1-F5 + EvidenceDemo）、目标等级（L1-L6）、当前等级、证据路径、依赖（如 E-01 才能做 PCB）、选择标准（风险/学习价值/复用度）、下一项目。F2-F5 明确标 `NOT RUN`，不要用 F1 的证据外推。

### CR-10 [medium] 六层协议没有 PCB/排版比较域，E1-E10 与 D1-D7 无法按协议定级

**结论**：协议 §7.6 的 L3 必需字段只有原理图 part/net_flag/net_port/wire/page，没有 PCB 的 components/pads/nets/outline/layers/stackup/DRC；§7.1 CLI 扩展没有 `pcb-*` 命令；§7.5 明确“不实现 PCB”。但 L4/L5 又要求 PCB UUID、Gerber、DRC 报告，导致 PCB 在协议里“不能 L3、却能 L4/L5”。同时 L1-L6 没有排版/可读性等级，D1-D7 的几何与排版验收无法表达。

**证据**：

- `docs/round3/execution-protocol.md:1263-1273`：§7.6 字段表只有原理图对象。
- `docs/round3/execution-protocol.md:1171-1178`：§7.1 命令表没有 `pcb-*`。
- `docs/round3/execution-protocol.md:1255`：§7.5“不实现 PCB 读取/布局/布线/铺铜/DRC/制造导出”。
- `docs/round3/execution-protocol.md:54-55`：L5 要求 `pcb_uuid` 与 Gerber；`:282-289` L4 证据要求“若做了 PCB：连通性/DRC 报告、层叠/规则版本”。
- `docs/task-ledger-round3.md:32` 与 `:30`：任务书 E/D 两个工作包分别是 PCB 与几何排版。

**影响**：E1-E10 的最高可达等级没有定义；D1-D7 的排版验收无法在六级体系里表达；实现 PCB 后也无法用同一协议判 L3。

**下一轮动作**：二选一并在协议头部写明：(a) 协议增加 PCB 比较域（components/pads/nets/outline/layers/stackup/DRC）与 `pcb-*` 命令映射，manifest 增加 PCB 角色；(b) 明确本协议只适用于原理图，另写 `pcb-execution-protocol.md`。无论哪种，都增加 `layout_review` claim 或第 7 级，定义机器检查（文字重叠/间距/模块框）+ 人工看图签核的证据字段。

### CR-11 [medium] J1-J7 产品化缺少干净机安装/升级/回滚与宿主矩阵验证

**结论**：产品化工作包目前只有“包大小/文件数”和“WorkBuddy 未测”两条。没有干净机安装、卸载、升级、回滚、路径/依赖检查，也没有 Claude Code/WorkBuddy/其他宿主的版本矩阵。J-04 只做 `du/find`，K-08 只写“未实测”。

**证据**：

- `docs/task-ledger-round3.md:269`（J-04）：约 5.6MB/240 文件、31 个参考 >40KB、单路由 121KB；没有安装测试。
- `docs/task-ledger-round3.md:291`（K-08）：WorkBuddy 端到端兼容未实测；安装器不保证装入 WorkBuddy。
- `grep -rn "安装\|install" docs/task-ledger-round3.md docs/round3/backlog.md` 只有 J-04/K-08 两处，没有 install/upgrade/rollback/uninstall 记录。
- `docs/round3/backlog.md:60`（P2-07）只列“安装分层”，没有安装验收。

**影响**：无法证明 Skill 能在干净环境安装并使用；升级/回滚失败会直接影响用户；宿主差异（Claude Code 版本、WorkBuddy）没有基线。

**下一轮动作**：在干净 Windows 沙箱执行：安装包复制到宿主 skills 目录 → 启动 → 跑一条最小任务 → 卸载 → 升级到下一版本 → 回滚。记录宿主名称/版本、安装路径、文件数/大小、权限、失败点、截图。新增 `docs/install-verification.md`；至少覆盖 Claude Code 与 WorkBuddy；把包版本写入 manifest。

### CR-12 [medium] 证据清单不是 artifact 级：EV-09 缺失、绝大多数证据无哈希；manifest_sha256 规范化未定义

**结论**：矩阵的证据索引是“证据 ID → 目录/文件”的索引，不是可校验的 artifact 清单：EV-09 不存在；只有 EV-01 的 PNG/NET 有 SHA256；EV-03..08、EV-12..18 只有路径。协议 §5.2 要求 `manifest_sha256`，但只写“规范化 JSON”，没有定义 canonicalization；§7.7 只定义了 `content_sha256` 的规范化。示例还把 Python 写成 3.11.9，与实际 3.13.15 不符。

**证据**：

- `docs/round3/capability-matrix.md` 的 EV 序列：`EV-01..EV-08, EV-10..EV-18`，缺 `EV-09`。
- 同文件 `:54`（EV-01）与 `:55`（EV-02）的 README 只对 `schematic.png`/`schematic.net` 给出 SHA256；`:56-70` 的 EV-03..08/12..18 只有路径或大小，没有统一 SHA256/bytes/mtime。
- `docs/task-ledger-round3.md:330-341` 的证据索引是领域目录级，不是文件级。
- `docs/task-ledger-round3.md:313`（L-15）声称“4 个证据文件 SHA256 与 README 一致”，但只列出 `AUD/a5-a2/unittest-full.log`、`benchmark.log` 两个路径（第二个还是相对路径，按上下文应为 `AUD/a5-a2/benchmark.log`），另外两个未列出。
- `docs/round3/execution-protocol.md:940`：“`manifest_sha256`：对去掉本字段后的规范化 JSON 计算”；全文没有定义 `sort_keys/separators/ensure_ascii/NaN` 等 canonical 规则；`:1297` 只为 `content_sha256` 定义了 `json.dumps(..., sort_keys=True, separators=(",", ":"))`。
- `docs/round3/execution-protocol.md:969` 示例 `"python": "3.11.9"`；实际环境是 Python 3.13.15（`docs/round3/capability-matrix.md:39`）。

**影响**：证据无法逐文件复核；不同实现计算出的 manifest 哈希会不同；示例值可能被复制到真实 manifest，造成错误的环境记录。

**下一轮动作**：生成 `docs/round3/evidence-index.json`：每个 EV 和台账引用的 AUD 文件一行，含 path/sha256/bytes/mtime/producer/role；补齐 EV-09 或说明编号跳号。协议增加 `manifest canonicalization` 小节（UTF-8、`sort_keys=True`、`separators=(",", ":")`、拒绝 NaN），并给出一个固定测试向量。示例改用实际 Python 3.13.15，或全部写 `<placeholder>` 并标注“不可复制”。

## 5. 逐工作包明细

以下只写“覆盖判定 + 缺口 + 必须补做”，不复述台账已记录的缺陷细节。

### 5.1 A1-A5：能力地图/等级/证据清单/风险验收/未完成汇总

- **审计覆盖**：PARTIAL。A1/A3/A5 有内容，A2 只有提案，A4 缺失。
- **A1 能力地图**：矩阵 42 项覆盖原理图/PCB/商城/SMT，但没有声明分类边界；`design-hardware/scripts/` 中 `power_budget.py`、`rc_settle_sim.py`、`netlist_check.py` 未进入矩阵；`references/design-cards/` 的 mcu/wireless/drive 等内容域未进入能力地图。补充：矩阵标题是“能力矩阵”，不是“EDA 能力矩阵”，读者会把它当全量。
- **A2 等级**：协议 L1-L6 定义完整，但 `docs/task-ledger-round3.md:300`（L-02）明确“尚未回写 product-acceptance/SKILL/代码，也无自动判定字段”；协议 `:10` 自标 `NOT RUN`。因此等级仍是提案，不是可执行门禁。
- **A3 证据清单**：见 CR-12；EV-09 缺失，绝大多数条目没有逐文件哈希。
- **A4 风险验收**：见 CR-08；完全缺失。
- **A5 未完成汇总**：见 CR-03；147 条台账 vs 55 条 backlog，21 条未引用，9 条活动项漏排。
- **必须补做**：先建 A4 风险登记；再建 A3 artifact 级 evidence-index；给 A1 加“覆盖/未覆盖”分类表；把 A2 的 L1-L6 并入 `product-acceptance.md` 与 `SKILL.md` 并在 `eda_exec.py` 输出 `level/level_status`；给 A5 加台账→backlog 覆盖检查。

### 5.2 B1-B8：回读/属性/跨页身份/过期快照/故障注入/幂等/保存重开/版本会话

- **审计覆盖**：COVERED。8 个子项都能在台账 A/B 与协议 §2-§4 找到判断。
- **B1 回读**：A-02/B-09 已记录；没有修复，也没有对应行为测试。
- **B2 属性**：A-03/A-09/F-05 已记录；CLI 无 `--include-attributes`/`--max-pins`，`attributes_complete` 语义未修。
- **B3 跨页身份**：B-01/B-03/B-06 已记录；工程级位号扫描、page UUID 冻结、跨页查重均未实现。
- **B4 过期快照**：B-02 已记录；`content_sha256`、写前重读、漂移拒绝均未实现。
- **B5 故障注入**：只有 `AUD/eda-exec/repro_defects*.py` 的合成复现；`tests/test_eda_exec.py` 23 项无故障注入；协议 §7.4 的 P-01..P-18 只是下一轮清单。**这是 B 组唯一没有测试套件的子项。**
- **B6 幂等**：B-04/B-08 已记录；未知结果强制回读、R? 孤儿认领未实现。
- **B7 保存重开**：B-09/F-07 已记录；状态被过度声明（CR-04）。
- **B8 版本会话**：B-05/B-07 已记录；协议 §3.1 只写 `cli`/`user`，没有对未知 origin 默认拒绝（代码 `close_owned:1249-1255` 只拒绝 `user`）。
- **必须补做**：新增 `tests/test_eda_exec_faults.py`，把 P-01..P-18 落成可执行用例；真实 EDA 故障注入另建矩阵并标注 synthetic/real；协议 §3.1 增加 origin 白名单（`cli/self/headless`，未知一律拒绝）；B7 状态按 CR-04 降级。

### 5.3 C1-C7：F1 样板

- **审计覆盖**：COVERED（台账 D-01..D-12 对 F1 的证据、电气、排版、网表、封装、热边界都有判断）。
- **交付状态**：PARTIAL + DEFECT。原理图连接/保存/重开/PNG/网表有真实证据；PCB、DRC/ERC、制造、样机、固件 NOT RUN；D-01（AMS1117 输出电容）、D-02（IO2 悬空）、D-06（EN/RST RC）、D-07（多余导线）、D-10（排版）仍未修。
- **缺口**：C4 网表 diff 不存在（D-03）；F1 的“物理脚-网络”表述把符号引脚说成物理脚（D-08）；样板范围没有定义“只做原理图”还是“原理图+PCB+制造”。
- **必须补做**：先定义 F1 样板的验收范围与目标等级；完成 D-01/D-02/D-06/D-07/D-10；增加 `netlist diff`（pin→net 规范化）并在重排前后各导出一次；PCB 依赖 E-01 完成后再补 F1 PCB。

### 5.4 D1-D7：几何与排版

- **审计覆盖**：COVERED（台账 C-01..C-11 + D-10）。
- **交付状态**：PARTIAL + DEFECT。8/8 只证 recall；真实 F1 snapshot 不能直喂；schema 缺 rotation/mirror/unit/pages/pin/text_bbox；近失端点/异网导线误判；F1 拥挤不可发现。
- **缺口**：没有 `snapshot→layout` 适配器；没有精度门禁（全 code 假检查器仍 8/8）；协议没有排版等级（CR-10）；模块框穿线检查缺失（C-05）。
- **必须补做**：写适配器（part/pin/wire/flag/port/text bbox）；benchmark 加 `expected_findings`/`forbidden_codes` 与负向测试；扩展 schema 至少支持 pages/page_name/unit/pin/scope/rotation/mirror/text_bbox/min_clearance；在协议中增加 layout claim 或第 7 级。

### 5.5 E1-E10：PCB 闭环

- **审计覆盖**：COVERED（台账 E-01..E-15 对读取/建板/导入/器件/板框/布线/过孔/铺铜/DRC/导出/保存重开/在线都有判断）。
- **交付状态**：GAP + PARTIAL。`eda_exec.py:1285` 仍 `pcb_read_write=not_implemented`；原始 CLI 探针已做读取/建板/导入/放置/板框/走线/过孔/铺铜边框/DRC/保存重开/Gerber+CPL，但真实 pad-to-pad 布线、全网络连通、DRC clean baseline、层叠/规则/自动布线未做；铺铜只有边框（pours=2/poured=1）；E-10 全在线 GUI BLOCKED。
- **缺口**：适配器命令族、PCB 页选择、PCB 比较域、DRC 增量报告、F1 PCB 板框/布局/布线/铺铜、独立 Gerber 查看。
- **必须补做**：按 E-01 增加 `pcb-read/apply/save/export/reopen-check`；用 F1 PCB 走通“建板→导入→板框→布局→布线→过孔→铺铜→DRC→Gerber/CPL→保存重开”；每步保存 JSON 与哈希；建立 DRC 前/后错误集合；全在线复验由用户 GUI 执行并记录 sessionId/build/online。

### 5.6 F1-F8：嘉立创衔接

- **审计覆盖**：COVERED（台账 F-01..F-15 + 矩阵 §4-§5）。
- **交付状态**：GAP + BLOCKED。BOM/CPL/Gerber/manifest 无能力；F1 BOM 草稿 11 行/16 位号，缺 manufacturer/MPN/Value/DNP/替代/自供；F1 证据无 manifest、`closed_session=null`、apply/reopen 引用 `<scratch>`；实时库存/价格/MOQ/交期/SMT 可贴/DFM/下单全部 BLOCKED；SMT Mark 开窗 2mm vs 3mm 口径冲突。
- **缺口**：BOM/CPL/manifest 生成与对账；渠道字段（mall/SMT/self、verified_at、stock、price、MOQ）；官方页面存档；真实渠道查询授权。
- **必须补做**：先实现/封装 BOM/CPL/Gerber 导出与 manifest；BOM 草稿标“待查”；统一 SMT 规则并加来源/日期；在获得用户账号与最小授权后，按 `lcsc-verification.md` 核对至少 10 个关键料，只查不买；无授权保持 BLOCKED。

### 5.7 G1-G8：内容审计

- **审计覆盖**：PARTIAL。台账 G/H/I 对电源、电池、模拟、接口做了大量复算，J-06 对 README 内容做了核对；但 G-13 明确 p04-p14 电源卡未逐卡审计，I-12 明确 power/thermal/digital/mcu/wireless 卡与大部分 failures 未审。
- **缺口**：没有“已审/未审”内容覆盖矩阵；`power_budget.py`、`rc_settle_sim.py`、`netlist_check.py` 未审；failures F01-F22 大部分未审（仅 f02/f09/f13/f14 抽查，见 `docs/task-ledger-round3.md:258`）；`references/design-cards/` 的 mcu/wireless/drive 未进入审计；内容结论的抽样率没有声明。
- **必须补做**：建 `docs/round3/content-audit-coverage.md`：按 references 子目录/卡片/脚本列出已审、未审、抽样率、证据路径；下一轮按高风险补审 p04-p14（市电/隔离、热插拔、MOS SOA、电池保护）、digital/MCU/wireless、F01-F22；明确“本轮内容审计不是全库正确性证明”。

### 5.8 H1-H8：评测

- **审计覆盖**：MISSING。见 CR-02。
- **缺口**：H1-H5 无定义；H6-H8 从未出现；没有评测计划、评测用例、原始 transcript、评分 rubric、基线对照；35 个场景未真实执行；旧试答非盲、无对照。
- **必须补做**：先写 H1-H8 定义与验收；再用 5 个高风险场景做首轮行为评测（F1 类、改板、换料、采购分流、失败恢复），固定模型/版本、保存原始输入输出、加无 Skill 基线；最后补全 35 场景的检查。

### 5.9 I1-I7：新手与工程师

- **审计覆盖**：PARTIAL。台账 K-07 明确 E1-E5 NOT RUN；K-06/J-08 指出 0 个预算/中断场景；协议 §6 定义了双层 message，但没有执行记录。
- **缺口**：没有真实新手/工程师任务；没有 transcript、判据、模型版本；没有验证“新手层不越级/工程师层不丢限制”；没有预算限制/长任务接续/中断恢复场景。
- **必须补做**：至少各做 3 个新手任务与 3 个工程师任务（含一次改板、一次缺货替代、一次中断续跑），保存输入/输出/评分/模型版本；用协议 §6 检查双层 message 的 `level/level_status` 一致性与禁用短语；补预算/中断场景。

### 5.10 J1-J7：产品化

- **审计覆盖**：PARTIAL。J-04 包大小/文件数、J-05 action-map 不可达、J-06 数字漂移、J-09 SKILL 偏长、K-08 WorkBuddy 未测、L-02 六级未落地都有判断。
- **缺口**：没有干净机安装/卸载/升级/回滚；没有宿主矩阵；没有版本/发布流程；没有权限/安全审查；包分层（core/deep）未做。
- **必须补做**：见 CR-11；另加包版本号/变更记录、安装脚本 dry-run、失败回滚说明；把 `tests/docs/evidence` 从运行包分离。

### 5.11 K：项目组合

- **审计覆盖**：MISSING。见 CR-09。
- **缺口**：没有项目组合台账；F2-F5 只有 NOT RUN；没有目标等级、选择标准、依赖、下一项目；F1 是唯一真实样板且只到原理图。
- **必须补做**：新增 `docs/round3/project-portfolio.md`；给每个项目写目标 L 级/当前 L 级/证据/依赖/优先级；明确 F2-F5 NOT RUN，不得用 F1 外推；把 E-01（PCB 适配器）标为 F2+ 的前置。

### 5.12 L1-L7：结构维护

- **审计覆盖**：PARTIAL。L-01..L-15 对历史报告、README 数字、doctor 过期、round2 台账、H1-H5、expansion-report、热专题、PR #3、PARTIAL 判据、NOT RUN 大项都有判断；J-10/J-11 有链接/去重检查。
- **缺口**：没有 CI/维护流程；没有“证据 manifest 校验”脚本；没有 stale 证据策略；没有 owner/复评周期；L-01..L-15 是一次性修正，不是持续维护；backlog DoD 与文档类 P0 冲突（CR-03）。
- **必须补做**：新增 `scripts/check_docs.py` 或 `make check`：跑 141 tests、链接检查、README 数字核对、evidence-index 哈希校验、台账→backlog 覆盖检查；定义每月/每次合并前的维护清单与 owner；把 `doctor.json` 的 stale 标记纳入检查。

## 6. 特别检查：四类过度声明

| 检查项 | 结论 | 证据 | 残余风险/下一动作 |
|---|---|---|---|
| “API 存在”写成“已执行” | **基本未违反**。矩阵把 `doc api` 查询单列为 EV-10/EV-11（B 级），并把 `SCH_Drc.check`、`getBomFile`、`createNetLabel`、PCB 层叠/规则/自动布线均标 NOT VERIFIED；协议 §7.1 把新命令标 `NOT IMPLEMENTED`。 | `docs/round3/capability-matrix.md:38,62-63,113-114,118`；`docs/round3/execution-protocol.md:1169-1178` | 协议 §7.3 用 `DONE` 描述“代码事实存在”（`:1206`），属于同类语义滑移；改名为 `IMPLEMENTED_BASIC`（CR-05）。 |
| “网表正确”写成“ERC 通过” | **未违反**。F1 README 只写“网表核对”，并明确“未运行原理图 DRC/ERC”；矩阵 DRC/ERC 行 NOT VERIFIED；台账 D-12 明确 DRC/ERC NOT RUN。 | `docs/evidence/f1-2026-10-22/README.md`（结论与“电气未验证”节）；`docs/round3/capability-matrix.md:98`；`docs/task-ledger-round3.md:154` | 矩阵“连接”行 VERIFIED 只代表网表/端口级，建议在该行限制列加一句“electrical_checked=not_run”，避免读者把“连接 VERIFIED”当 ERC。 |
| “DRC 通过”写成“可生产” | **未违反**。协议 L4/L5 明确分离“电气检查”与“制造资料核对”；矩阵 DRC 只到 PARTIAL；F1 明确“不得当可生产板”。 | `docs/round3/execution-protocol.md:245-300,302-362`；`docs/round3/capability-matrix.md:115`；`docs/evidence/f1-2026-10-22/README.md` | 矩阵“制造资料 PARTIAL”行应同时写“不可生产/未下单”，防止被断章取义。 |
| “单元测试通过”写成“真实故障已验证” | **部分违反**。A-08/B-10 明确 23 项测试只覆盖理想路径；但 L-15 与矩阵“保存重开 VERIFIED”把测试/窄域证据写成 DONE/VERIFIED。 | `docs/task-ledger-round3.md:97,115,313`；`docs/round3/capability-matrix.md:13,96`；`docs/task-ledger-round3.md:114`（B-09 假阳性） | 按 CR-04 降级保存/重开；在结果包增加 `test_scope`（unit/synthetic/real_eda），禁止用单元测试数量证明故障已真实注入。 |

## 7. 下一轮执行顺序（可直接照做）

1. **修覆盖映射（CR-01）**：建 `docs/round3/workpackage-coverage.md`，83 行表；给任务书 ID 加 `TB-` 前缀；提交任务书清单摘要。
2. **修状态口径（CR-05/CR-04）**：定义状态优先级；协议 §7.3 `DONE→IMPLEMENTED_BASIC`；矩阵保存/重开拆行；L-15 降 PARTIAL。
3. **补 H1-H8（CR-02）**：写 `evaluation-plan.md`；先跑 5 个高风险场景；保存原始 transcript 与基线。
4. **补 backlog 覆盖（CR-03）**：21 个未引用 ID 逐条处置；至少把 B-11/B-12/D-12/F-15/G-13/H-11/H-13/I-10/I-12 转成 P1/P2；DoD 分代码/文档/证据。
5. **补 A4 风险登记（CR-08）**：14 条 confirmed findings + 3 条 BLOCKED 填入 `risk-register.md`。
6. **补 K 项目组合（CR-09）**：写 `project-portfolio.md`；F1-F5 目标等级/证据/依赖。
7. **修基线/写入边界（CR-06/CR-07）**：统一基线声明；建 `run-manifest.json`；四份文档一起提交或明确未提交。
8. **补证据链（CR-12）**：`evidence-index.json` 逐文件 SHA256/bytes/mtime；修 EV-09；定义 manifest canonicalization 与测试向量。
9. **补 PCB/排版协议（CR-10）**：PCB 比较域或独立协议；`layout_review` claim；与 E-01/D1-D7 对接。
10. **补产品化（CR-11）**：干净机安装/卸载/升级/回滚 + Claude Code/WorkBuddy 宿主矩阵。
11. **最后再做真实 EDA/PCB/制造**：按 E-01→F1 PCB→DRC 基线→Gerber/CPL/BOM→全在线 GUI 的顺序；没有原始 JSON/哈希/会话记录的步骤不得写 DONE。

## 8. 复核边界与非声明

- 本文没有重新执行 EDA、PCB、DRC、制造或样机；没有修改仓库代码；没有修改四份被复核文档。
- 本文对台账/矩阵/协议的领域结论只做抽样复核（关键路径、文件存在性、行号、计数、状态一致性），没有替代各审计域的原始证据复核。
- `python -B -m unittest discover -s tests` 复跑结果为 141 tests OK；这是离线测试结果，不证明 EDA 真实故障已注入。
- 任务书原文不在仓库，本文的 83 个编号位是按任务说明的区间计数的组级口径；若任务书有组内子项，需按 CR-01 的映射表补齐后才能声称逐项覆盖。
- 本文的 `AUD` 证据存在性已抽查（`repro_results.json`、`coverage_report.json`、`probe-pcb-result.json`、`benchmark-run.json`、`f1-bom-coverage.json`、`ams1117_utd.txt` 等存在），但未逐文件复算全部哈希；逐文件哈希是 CR-12 的下一轮动作。
