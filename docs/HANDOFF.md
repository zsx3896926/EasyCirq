# 会话交接（截至 2026-11-01，第 155 轮）

> 目的：这个会话跨了上百轮，上下文随时可能被压缩。这一页是**给下一个接手的人（或压缩后的自己）**看的：
> 现在到哪了、哪些已验证、哪些还是空白、下一步做什么。

## 一句话现状

**一块"测温度、超温就响"的板，从一句话做到了可下单的 12 层 Gerber，全程有证据；
但它没打样，所以"会不会响"仍然未知。**

## 已验证（附证据位置）

| 结论 | 怎么验的 | 证据 |
|---|---|---|
| 从零建板 → 卡片 | 报警器 9 器件 / 15 连接全 ok | `docs/traceability-alarm.md` |
| 离线门禁 17 项 | 两轮 PASS 才签发写入许可 | `reports/alarm-r132/` |
| PCB 走通 | autoroute 7/7、DRC 0 | 同上 + `reports/pcb-drc-r132.json` |
| Gerber | 12 层含两套钻孔 | `deliverables/alarm/board-gerber.zip` |
| 客户零术语 | 六文件静态扫描 | `tests/test_customer_language.py` |
| 四向一致性 | 仓库 ↔ 包 ↔ 副本 | `tools/check_release_consistency.py` |
| 可复现 | 同机重跑 17 项数值一致 | `docs/traceability-alarm.md` |
| 能力边界 | MCU 引脚实测九字段 | `easycirq/references/scope-limits.md` |
| 全量回归 | 4820 passed / 16 Go 包 | 最近一次 commit |

## 五个真实缺陷（都是这块板暴露的）

| # | 缺陷 | 怎么发现的 | 现在的防线 |
|---|---|---|---|
| 1 | 建板写入门禁死锁 | 从零画板卡住 | 分阶段门禁（1.3.0） |
| 2 | 电源网名 `VCC` 被静默改写成 `GND` | 人工读网络表 | 连接守则 + KPI 16 |
| 3 | 蜂鸣器开集输出驱动方向错 | 人工读电路 | （无自动检查，见下方空白） |
| 4 | 图改了 PCB 没同步无检查 | 人工比对 | KPI 17 |
| 5 | 我移器件把引脚与导线撕开 | DRC warn 增加 | 顺序：断开→移动→连接 |

## 明确的空白（不要以为已覆盖）

| 空白 | 为什么还在 |
|---|---|
| **电路功能是否正确** | 17 项全是结构/连接/供电/一致性；没有任何一项验证电气行为 |
| **实物是否可用** | 没打样 |
| **跨机器复现** | 只有同机 + 隔离目录 |
| `VCC` 映射的根因 | connector 是打包的 `.eext`，无可读源码 |
| 原理图 6 项 warn | 5 个网络标签在框外 + 1 个孤立网名；排版问题，不阻断 |

## 下一步（按优先级）

1. **打样**：`deliverables/alarm/board-gerber.zip` 下单（约 ¥8–15/板，¥50–80/5 片）。
2. 板回来后按 `deliverables/alarm/electrical-checklist.md` 测六个值，特别注意
   **`NTC_MID` 必须随温度下降**（接反时它上升，只测"响不响"发现不了）。
3. 填 `acceptance.example.json` 的格式，跑 `easycirq acceptance`。
4. 有条件时做跨机器复现（第二台机器装 bundle）。

## 关键文件在哪

| 要找什么 | 位置 |
|---|---|
| 客户交付包（9 文件） | `deliverables/alarm/` |
| 报警器的完整经过 | `docs/alarm-functional-defect.md` |
| 逐条命令的可追溯台账 | `docs/traceability-alarm.md` |
| 能做什么/不能做什么 | `easycirq/references/scope-limits.md` |
| 发版检查单 | `docs/release-checklist.md` |
| 已知 flaky 测试 | `docs/known-failures.md` |

## 环境快照

```
easycirq 1.3.30      daemon 端口 23111     connector 已连接（EasyEDA Pro 4.1.78）
KPI 定义 17 项（metrics/schematic-kpi.v1.json，版本 1.2.0）
测试：4820 passed / 5 skipped；go test 16 包 ok
临时工程：KPI-S5-Verify（含报警器 P2 页 + PCB1）
```

## 路径注意

仓库在会话工作目录的 **子目录** \hds-a-method/\ 下：

\C:\Users\jlc\Documents\deepseek-harness\default-workspace\   <- 会话 cwd
└── hds-a-method/                                                <- 仓库根（.git 是文件）
\
本文件里所有相对路径都相对**仓库根**。命令前先 \cd hds-a-method\。

## 分支已发布（2026-11-01）

此前 `feat/agent-ace-rules` **不在远端** —— 222 个提交、155 轮的全部成果只存在于一块磁盘上。
现已推送并配置 upstream：

```
local   4a63e5cb
remote  4a63e5cb   origin/feat/agent-ace-rules
未推送提交 0
```

另存了一份单文件备份：`../.backup/agent-ace-rules-20261101.bundle`（相对仓库根，仓库的上一级目录）
（40.3 MB；`git bundle verify` 报 "records a complete history"；还原克隆后 794 提交，
HEAD 与本地一致）。

### 为什么记这一条

「可复现」不只是「同一台机器重跑结果一致」——**代码本身必须在别处也有一份**。
一个只存在于本地分支的实现，别人无法复现，磁盘坏了也无法恢复。

## 全部本地分支已发布（2026-11-01 第二轮）

第一次只推了 `feat/agent-ace-rules`，然后核了其余分支，发现范围远不止一条：

| 项 | 之前 | 之后 |
|---|---|---|
| 远端分支 | 30 | **174** |
| 本地分支 | 165 | 165 |
| **tip 在远端不可达的分支** | **122** | **0** |

较长的那几个：`backup/local-balanced-pack`(88 个独有提交)、
`feat/balanced-pack-rebase`(84)、`feat/eda-load-doc`(63)、
`feat/agent-docs-round24`(60)。

### 两条被拒的推送（**没有**强推）

```
! [rejected]  feat/balanced-pack  (non-fast-forward)
! [rejected]  main                (non-fast-forward)
```

两条都是「本地比远端旧」。`git push --force` 会覆盖远端历史，
**所以没做**。改为把本地 main 推成独立备份分支：

```
* [new branch]  main -> backup/local-main-20261101   (d39b8ed1)
```

### 本地 main 确实有 3 个未发布的提交

```
d39b8ed1  docs(easycirq): add Agent entry contract page for routing_lab tools
92a45799  docs(easycirq): add router A/B worked example
2e75ddae  docs(easycirq): add router A/B comparability reference
```

其中两个文件**在 origin/main 上不存在**：

```
easycirq/references/pcb-router-agent-entry.md   on origin/main: False
easycirq/references/pcb-router-ab.md            on origin/main: False
```

它们现在保存在 `backup/local-main-20261101` 上。**是否要把这两个文档合进主线，是产品决定，不是我能替你定的。**

### 备份文件

```
.backup/agent-ace-rules-20261101.bundle   40.3 MB
.backup/all-refs-20261101.bundle          45.9 MB   265 refs，还原后 166 个分支
```

两个都通过 `git bundle verify`（"records a complete history"）并实际还原验证过。

### 教训

第一次检查时我只问「**我的分支**发布了没有」，答案是"没有"，修完就以为完事了。
真正该问的是「**有没有任何**本地成果没发布」——一问就多出 122 个分支和 3 个提交。

**检查范围又一次小于它看起来的范围。**

## `tools/check_published.py`（2026-11-01）

把上一轮那个教训变成可重复的检查：不问「某一条分支发布了没有」，而是
一次列出**所有**本地分支，逐个判断 tip 是否在远端可达。

```
python tools/check_published.py
  remote origin: 174 branch(es)
  local: 165 branch(es)
  every local branch tip is reachable from the remote      -> exit 0
```

有未发布的就列出来并 `exit 1`。`tests/test_check_published.py` 用临时仓库
造了「未推送分支」和「已推送分支」两种情况，确认它既不漏报也不误报。

## 另一个 worktree 在活跃工作（2026-11-01 观察到）

`hds-verifier/` 这个 worktree 停在分支 `fix/designator-integrity` 上，**有活跃提交**：

```
5dbe1f04 2026-11-01  research(layout): fine budget sweep at 5 mil finds a better point
04e62559 2026-11-01  feat(layout): the routing grid is a first-class parameter
2188949d 2026-11-01  research(layout): at 5 mil the board finally gets 0 dead legs AND 0 pour islands
```

而且它的工作树里有**未提交的改动**（`tools/layout/ec_layout.py`、`tools/layout/reproduce.py`、
`tests/test_ec_layout.py`）。

处理：只推送了它的**提交**（`04e62559..5dbe1f04`，快进，无冲突），
**没有碰它的工作树，没有 commit 它的未提交改动**。那是另一个会话的活。

### 这次是工具抓到实时的，不是测试

上一次跑 `check_published.py` 是"全绿"；这轮再跑，它报出

```
UNPUBLISHED: 1 branch(es)
  fix/designator-integrity    5dbe1f04
```

因为在我的两次运行之间，那个 worktree 新提交了一次。
**检查在真实数据上生效了，而不只是在测试夹具里。**

### 值得记住的一点

「本地分支全发布了」是一个**会过期的结论**——只要还有别的 worktree 在跑。
所以这个检查不能只做一次，应该放进发版检查单（已放）。

## 第一幕（开工前那句确认）现在有答案了

客户说「做一个能测温度、超温就响的板子」之后的三个问题：

| 客户问 | 现在怎么答 | 证据形态 |
|---|---|---|
| 能不能做 | 能 | 必查 14/14、PCB DRC 0、Gerber 12 层、图板一致、BOM 一致 |
| 多少钱 | **给板厂 5 个数**，价格不编 | `quote_facts.py` 算出的板子属性 |
| 多久 | 同上，标 NOT RUN | 看排产 |

### `easycirq/scripts/quote_facts.py`

```
板框      19.49 x 21.72 mm  (4.23 cm²)
铜层      2
器件      9 个（顶层 9 / 底层 0）
贴片点    8
直插件    1
BOM       6 种料，总用量 9
钻孔      需要
```

它**故意不输出价格**：

```python
"price": None,
"price_status": "NOT RUN",
```

价格是订单的属性（打几片、贴不贴片、加不加急、喷锡还是沉金），不是板子的。
给一个数，客户就会拿它做预算。有一个测试专门钉这条：
`test_price_is_never_invented`。

### 报价与交期仍未核实（NOT RUN）

2026-11-01 尝试联网查嘉立创当前报价，搜索接口返回**上游 403**。
所以报价表里只给驱动因素，不给数字。有网络时应当补一次真实询价。

## 回归（1.3.33，2026-11-01）

| 检查 | 结果 |
|---|---|
| `pytest tests` | **4842 passed, 5 skipped** |
| `go test ./...` | **16 包 ok，0 测试失败** |
| `go vet ./...` | 干净 |
| `check_release_consistency.py` | `CONSISTENT`（四向） |
| `check_published.py` | 全部本地分支已发布 |
| 隔离安装 | `healthy` |
| 包内含 `quote_facts.py` | 是 |

## 客户视角走查（1.3.34）

docs/customer-walkthrough.md 记录了在**隔离安装**里按输出提示走完四步的实际输出与退出码。

| 步骤 | 命令 | 退出码 | 结论 |
|---|---|---|---|
| 装好 | setup | 0 | 四行全绿 |
| 说需求 / 看状态 | status | 2（无数据时） | 提示清楚，2 是 incomplete 的既定码 |
| 卡片 | card | 0 | 必查 14/14 |
| 验收 | cceptance | 0 | **用示例数据**，真实数据未跑过 |


## 回归（2026-11-01，1.3.34 之后）

| 检查 | 结果 |
|---|---|
| `pytest tests` | **4849 passed, 5 skipped**（1570 subtests） |
| `go test ./...` | **16 包 ok，0 测试失败** |
| `go vet ./...` | 干净 |
| `tools/check_release_consistency.py` | `CONSISTENT`（四向） |
| `tools/check_deliverable.py` | **交付包自检通过** |
| `tools/check_published.py` | 全部本地分支已发布 |

### 这一轮补上的验证

`tests/test_acceptance_judgement.py`（5 项）——验收卡**能判红**：

| 输入 | 输出 | 退出码 |
|---|---|---|
| 写 pass 但证据为空 | 「⏳ 还差实测证据」 | 1 |
| `function` 填 fail | 「❌ 这块板还不能算可用」 | 1 |
| 三项实测 pass 带读数 | 「✅ 这块板可以交付使用」 | 0 |
| 记录不存在 | 「⏳ 还没有验收记录」 | 2 |

第四条最要紧：**写了 pass 但没读数，不会变成绿灯**。

### 三个仓库级自检器（都带测试）

| 脚本 | 守什么 | 什么时候跑 |
|---|---|---|
| `tools/check_release_consistency.py` | 仓库 ↔ 包 ↔ 副本，四向 | 发版前 |
| `tools/check_deliverable.py` | 交付包自身的断链/清单/校验和/数字 | 发版前 |
| `tools/check_published.py` | 有没有任何本地分支没发布 | 发版前 |

## 回归（2026-11-01，1.3.35 + 可复现输入入库）

**串行跑，一次一个**（并行会让 IO 敏感的用例假失败，见 `docs/known-failures.md`）：

| 检查 | 结果 |
|---|---|
| `pytest tests` | **4849 passed, 5 skipped** |
| `go test ./...` | **16 包 ok，0 失败** |
| `go vet ./...` | 干净 |
| `tools/check_deliverable.py` | **交付包自检通过** |
| `tools/check_release_consistency.py` | `CONSISTENT`（四向） |
| `tools/check_published.py` | 全部本地分支已发布 |

交付包现在 **22 个文件 / 233.5 KB**（含 `design/` 里 11 个可复现输入）。

## 「可复现」现在到哪一步了

| 层次 | 状态 | 证据 |
|---|---|---|
| 同机重跑结果一致 | ✅ | 多次 18 项数值一致 |
| **只拿仓库文件重跑** | ✅ | `deliverables/alarm/design/` 9 个快照文件 → `verdict: PASS, kpis: 18` |
| 换一台机器重跑 | ❌ **NOT RUN** | 仍是同一台机器上验证的 |
| 从零重画这张图 | ❌ **NOT RUN** | EasyEDA 工程不在仓库里 |

### 上一轮那个教训值得单独记

第一次把"看起来重要"的 7 个文件入库，跑出来是：

```
offline pipeline: BLOCKED
  missing  #14 netlist_diff
  #15 readback
```

缺 `connectivity-before.json` / `connectivity-reopen.json`——KPI 14/15 要拿
"写入前 / 重开后"两份快照做比对。

**入库的文件要按管线的实际依赖核对，不能按重要性猜。**
这和之前"检查范围小于看起来的范围"是同一类错误的另一种形式。

## 回归（2026-11-01，1.3.36）

串行跑，一次一个：

| 检查 | 结果 |
|---|---|
| `pytest tests` | **4852 passed, 5 skipped** |
| `go test ./...` | **16 包 ok，0 失败** |
| `go vet ./...` | 干净 |
| `skill_selftest.py`（已安装副本） | **6 PASS** |
| `tools/check_handoff.py` | 所有引用都能找到（70 个） |
| `tools/check_deliverable.py` | 交付包自检通过 |
| `tools/check_release_consistency.py` | `CONSISTENT`（四向） |
| `tools/check_published.py` | 全部本地分支已发布 |

## 四个仓库级自检器（每个都有测试）

| 脚本 | 守什么 | 第一次跑抓到什么 |
|---|---|---|
| `check_release_consistency.py` | 仓库 ↔ 包 ↔ 副本，四向 | 256 个过时文件 |
| `check_deliverable.py` | 交付包的断链/清单/校验和/数字 | 一个 `../docs/` 断链 |
| `check_published.py` | 有没有本地分支没发布 | 122 个分支 + 3 个提交 |
| `check_handoff.py` | 交接文档里 70 个路径引用 | 一个只在上一级成立的路径 |

**四个都是「发现问题 → 固化成检查」的产物，而且四个都在第一次运行时抓到了真东西。**

### 一个反复出现的教训

`check_handoff.py` 自己有两个 bug，都被它自己的测试抓到：

1. `easycirq/` 开头的路径被当成命令行跳过 → 文档里所有 `easycirq/scripts/...`
   的引用**从没被检查过**（覆盖数 66 → 70）。
2. 输出在 Windows 上是 GBK，中文判定乱码 → 四个仓库工具现在都强制 UTF-8。

**检查器本身也需要被检查。** 如果它没配测试，我会一直以为"所有引用都能找到"是真的。
