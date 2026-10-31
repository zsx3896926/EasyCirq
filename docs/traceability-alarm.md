# 可追溯台账：温度报警器（2026-10-31）

> 指标 7 要求「"我要什么" → "能打样" 全链路可追溯 100%」。
> 这份台账逐条列出：**结论 → 用什么命令得出 → 证据留在哪**。
> 复现方式：按顺序执行命令即可（工程 `KPI-S5-Verify`，页 `P2`）。

## 0. 一句话需求

| 结论 | 命令 | 证据 |
|---|---|---|
| 能做，约 ¥8–15，3–5 天 | 人工估算（含库内器件价格） | `docs/temp-alarm-proposal.md` |
| 三个必须先问的问题 | — | 同上 |

## 1. 选型（器件确实存在）

| 结论 | 命令 | 证据 |
|---|---|---|
| 10K 热敏电阻存在 | `easycirq lib search NTC 10K` | C9900004021 |
| LM393 存在 | `easycirq lib search LM393` | C504553 |
| 贴片蜂鸣器存在 | `easycirq lib search --query '5025贴片蜂鸣器'` | C9900027059 |
| 100nF 0603 存在 | `easycirq lib search 100nF 0603` | C9900013340 |

## 2. 画原理图（15 次写入）

| 结论 | 命令 | 证据 |
|---|---|---|
| 新页创建 | `sch page-new --schematic 2be28e1c36e37dfe` | pageUuid `9d9dd9e46f53880e` |
| 7 个器件落位 | `sch place` ×7 | 每个 `ok: true` |
| 15 条连接 | `sch connect --pin ... --kind ... --net ...` ×15 | 全部 `ok: true`；`sch connectivity` 的 `connections` 16 条（含合并） |
| 未用引脚标不接 | `call schematic.pin.set_no_connect` | U1:5/6/7、BZ1:3 |
| 建板不需令牌 | — | 每次 `sch place` 都 `ok`，无 `GATE_*` |

## 3. 原理图检查（两轮 PASS）

| 结论 | 命令 | 证据 |
|---|---|---|
| 快照齐备 | `sch connectivity` / `sch list --include-bbox --include-pins` / `sch sheet-geometry --json` | `%TEMP%\alarm-snap5\*.json` |
| ERC | `sch drc --json` | `drc.json` |
| BOM | `bom export --type csv` | `bom.tsv` |
| 回读一致 | `doc reload` 前后各读一次 | `connectivity-before/reopen.json` 一致 |
| 引脚计划 | `pin_plan_check.py .easycirq/pinplan-alarm.json` | `status: passed`，`pin_mux_conflicts: 0` |
| **门禁第 1 轮** | `sch_offline_pipeline.py --project-uuid ...` | `PASS (apply_allowed=False)` |
| **门禁第 2 轮** | 同上 | `PASS (apply_allowed=True)` → 签发令牌 |
| **卡片** | `easycirq card --kpi-report ...` | `✅ 可以打样`，必查 11/11 |

## 4. PCB（0 违规）

| 结论 | 命令 | 证据 |
|---|---|---|
| 网表同步 | `pcb import-changes` | 9 器件（含 LED 页 2 个） |
| 布局 | `pcb auto-place` | `ok` |
| 板框 | `pcb outline-fit --margin 60` | 877×869 mil |
| 布线 | `pcb autoroute` | `success=true, 5/5 nets, 15139ms` |
| **DRC** | `pcb drc --json` | `passed: true, total: 0` |
| 权威重读 | `pcb save` → `doc reload` → 再 DRC | 仍 `total: 0` |

## 5. 制造文件

| 结论 | 命令 | 证据 |
|---|---|---|
| 令牌有效 | 管线两轮 | `apply_allowed: true` |
| Gerber 导出 | `call pcb.manufacture.gerber` | `ok: true`，11 层 |
| 层清单含钻孔 | 解压 zip | `Drill_PTH_Through.DRL` |

## 6. 交付包

| 结论 | 命令 | 证据 |
|---|---|---|
| 原理图可读 | `sch export-image --format svg` | 92,410 字节，81 text，NTC/LM393/BZ1 |
| 整板卡片 | `card --kpi-report ... --pcb-drc reports/pcb-drc.json` | `✅ 可以下单（原理图与 PCB 都通过）` |
| 客户部分零术语 | 扫描 11 个禁用词 | 附录之前 0 命中 |

## 清晰的 NOT RUN

| 项目 | 为什么没做 |
|---|---|
| **实物打样** | 需要下单与收货，非 AI 可完成 |
| **打样后验收**（焊接/上电/功能） | 没有实物，`acceptance` 从未收到真实数据 |
| **第二台机器安装** | 只有隔离目录安装验证，没有另一台机器 |
| **原理图视觉效果** | 本机无确定性 SVG→PNG 工具链，"看起来对不对"未验证 |

## 这一路的工具缺陷（都由这块板暴露并修掉）

| 缺陷 | 影响 | 修复版本 |
|---|---|---|
| 建板写入被门禁死锁 | 无法从零画板 | 1.3.0 分阶段门禁 |
| 管线不传 `--sheet-geometry` | 新页布局失败 | 1.3.0 |
| 纯标签页面无导线报错 | 连线度量中断 | 1.3.0 |
| `sch list` 缺 bbox | 器件全被丢弃 | 1.3.0（文档） |
| `anchor: null` 崩溃 | 布局检查中断 | 1.3.0 |
| 快照缺 `--include-pins` | NC 全被判悬空 | 1.3.1（文档） |
| `pin_plan_check` 强求 MCU 字段 | 模拟器件无法通过 | 1.3.2 |
| `pin_plan_check` 缺 `verdict`/`metrics` | KPI 恒判 unknown | 1.3.2 |
| `card` 不读 PCB | 原理图结论冒充整板 | 1.3.2 |

## 一句话

从「一句话」到「可下单的 Gerber」，**每一步都有命令与输出可查**；
**没做的那三件事（下单、实测、第二台机器）明确标着 NOT RUN**。

## 复现验证（本轮实做）

按上面的命令，用**全新的快照目录**把整条链路重跑了一遍，与首次结果逐项对比：

| 项 | 首次 | 复现 |
|---|---|---|
| verdict | PASS | PASS |
| KPI 项数 | 15 | 15 |
| 逐项 status / value | — | **无差异** |
| apply_allowed | true | true |
| 卡片 | ✅ 可以下单 | ✅ 可以下单 |

```
verdict PASS / PASS
kpi count 15 15
differences none
apply_allowed True / True
```

**这就是"可复现"的实物证据**：不是"我跑通过"，而是"换一个快照目录按同样命令
再跑，当时那 16 个指标连数值都不变"。

（注：复现用的是同一台机器、同一个 EDA 工程。跨机器复现未做——见 NOT RUN。）

## 回归状态（1.3.2）

改完 `cmd_card.go`（PCB 判定）、`pin_plan_check.py`（verdict/metrics）、
`sch_kpi.py` 之后的重跑：

| 检查 | 结果 |
|---|---|
| `go vet ./...` | 干净 |
| `go test ./...` | **16 个包全部 ok** |
| `pytest -k "sch or mcp or customer or pin or kpi"` | **678 passed** |
| 两份 `skill_selftest.py` | 6 PASS / 6 PASS |

没有回归。


## MCP 端到端（stdio 协议）

不只测 Python 函数，还用真实的 JSON-RPC over stdio 跑了一遍：

| 请求 | 结果 |
|---|---|
| initialize | 协议版本 2024-11-05 |
| 	ools/call easycirq_card {kpi_report, pcb_drc} | state: ready，✅ 可以下单（原理图与 PCB 都通过） |
| 	ools/call easycirq_card {kpi_report} | state: ready，✅ 原理图可以打样（PCB 未检查） |

三条路径（Go CLI / Python 脚本 / MCP 工具）现在给出**一致的结论与措辞**。

## 指标 1：首次可用时间（1.3.6 实测）

指标定义是「装到第一条审计 ≤5 分钟」。之前记的 3.6s 是旧版本的工具层耗时，
这一轮用 1.3.6 的完整 bundle 实测：

| 步骤 | 耗时 |
|---|---|
| `easycirq_install.py install`（806 文件解包） | **2.6s** |
| `easycirq_install.py verify`（逐个文件核对） | **0.5s** |
| `easycirq setup`（第一次看到状态） | **1.4s** |
| **合计** | **4.5s** |

对照目标 ≤300s（5 分钟），余量极大。

### 这 4.5 秒不包含什么

必须分开报告——这三点都**没有计时**：

| 未计入 | 为什么 |
|---|---|
| EasyEDA Pro 安装 | 客户多半已经有了；不是本工具的事 |
| 导入连接器插件（.eext）+ 重启 EasyEDA | 要人在 GUI 里点，无法在脚本里计时 |
| `easycirq connector path` 找文件 | 只打印路径，几毫秒，但客户要拿它去 GUI 粘贴 |

所以「4.5 秒」是**工具链本身**的时间，不是「从零到能用 EDA」的时间。
诚实说法：工具侧 4.5 秒，剩下的是装 EasyEDA 和点一次插件——那部分取决于人。

## 全量回归（1.3.19，2026-11-01）

| 检查 | 结果 |
|---|---|
| `pytest tests`（全量） | **4789 passed, 5 skipped**, 1570 subtests |
| `go vet ./...` | 干净 |
| `go test ./...` | **16 个包 ok**（另有 2 个包无测试文件） |
| `check_release_consistency.py` | `CONSISTENT`（12/12 双向） |
| `skill_selftest.py`（两份） | 6 PASS |

### 上一轮的那个失败

全量第一次跑时 `test_owned_files_are_utf8_lf_without_todo` 在
`pin_plan_check.py` 上失败——755 行 CRLF。查下去发现**我新建的每个 .py 都是 CRLF**，
只是那个测试只查自己的 owned 清单，所以只报了一个。

根因是 `.gitattributes` 只有逐文件规则。已加通配 `*.py text eol=lf`，
`git check-attr` 对抽样文件均返回 `eol: lf`，1.3.19 的 bundle 里
`sch_kpi.py` 的 CRLF 计数为 0。

**教训**：一个只覆盖白名单的检查，会让人以为"只剩这一个问题"。

## 回归（1.3.22，2026-11-01）

改完打包器与一致性检查器后重跑：

| 检查 | 结果 |
|---|---|
| `pytest tests`（全量） | **4795 passed, 5 skipped**, 1570 subtests |
| `go vet ./...` | 干净 |
| `go test ./...` | **16 个包 ok** |
| `check_release_consistency.py` | `CONSISTENT`（327 文件三方一致） |
| 隔离安装 | `healthy`，808 文件 |
| 包内 Python 行尾 | **LF 308 / CRLF 0** |
| `skill_selftest.py` | 6 PASS |

### 这一版修的是什么

1.3.21 **发布后无法安装**：打包时把文本转成 LF，但 `bundle.json` 里的哈希仍按
工作树的 CRLF 计算，安装器判定 `Corrupt bundle payload`。

回滚后用「一个函数决定发出去的字节」重做：

```
shipped_bytes(path)   文本转 LF，其余不动
shipped_sha(path)     对 shipped_bytes 求哈希
shipped_inventory()   整棵树 {路径: 哈希}，跳过 __pycache__
```

manifest、zip 写入、技能清单、复制后比对四处全部走它。

**教训**：把"内容"定义在一个地方，而不是在每个用到的地方各自定义一次。

## 回归（1.3.25，2026-11-01）

| 检查 | 结果 |
|---|---|
| `pytest tests`（全量） | **4809 passed, 5 skipped**, 1570 subtests |
| `go vet ./...` | 干净 |
| `go test ./...` | **16 个包 ok** |
| `check_release_consistency.py` | `CONSISTENT`（四向） |
| 隔离安装 | `healthy` |
| `skill_selftest.py` | 6 PASS |

### 1.3.24 / 1.3.25 改的是什么

两版都在做同一件事：**把客户可见文案里最后的工具术语换掉**。

| 版本 | 改动 | 怎么发现的 |
|---|---|---|
| 1.3.24 | 卡片上的 `PCB` → `板子` | 把四张卡拼起来人眼扫描 |
| 1.3.25 | `status` 的「回读」→「关掉重开，确认东西都还在」 | **新加的静态扫描测试** |

第二版不再依赖人的注意力：`tests/test_customer_language.py` 每次跑测试都扫
`cmd_setup/status/card/acceptance` 四个文件里的字符串字面量，命中禁用词就红。

同一次测试还钉住两件事：卡片不能再出现 `PCB`；验收卡必须仍有「焊接 / 上电 / 功能」
三项——删掉一项也不会静默通过。


（注：该段记录的是当时门禁 16 项时的复现结果；现在门禁是 17 项。）

## 文档一致性守卫（2026-11-01）

三次同类漂移之后，加了两组测试，把「靠人记住」换成「每次跑都数一遍」：

| 测试 | 检查什么 | 第一次跑的结果 |
|---|---|---|
| `tests/test_doc_numbers.py` | 文档里的 `N 项 KPI/指标/门禁/定义` 必须等于 `metrics/schematic-kpi.v1.json` 的实际项数 | 抓到 `traceability-alarm.md` 还写着 16 项 |
| `tests/test_customer_language.py` | `cmd_setup/status/card/acceptance` 的字符串里不许出现 daemon / connector / KPI / gate token / 快照 / 回读 | 抓到 `status` 里的「回读」 |

两组都在第一次运行就抓到了真问题——不是"加了个检查"，是"这个检查立刻证明了有用"。

### 为什么是数字

15 → 16 → 17 每次只改了当时正在看的那份文档，其余继续说着旧数字。
**数字最容易被读者无条件相信，所以也最危险。**

### 同时钉住的还有

- 卡片上不能再出现 `PCB`（目标只允许「板子」）；
- 验收卡必须仍有「焊接 / 上电 / 功能」三项——删掉一项也不会静默通过；
- SKILL.md 必须引导读者核对 Gerber 的**层清单**，而不是记一个固定层数
  （11 → 12 已经发生过）。

## 最终回归（1.3.27，2026-11-01）

| 检查 | 结果 |
|---|---|
| \pytest tests\（全量） | **4814 passed, 5 skipped**, 1570 subtests |
| \go vet ./...\ | 干净 |
| \go test ./...\ | **16 个包 ok** |
| \check_release_consistency.py\ | \CONSISTENT\（四向） |
| \skill_selftest.py\ | 6 PASS |
| 隔离安装 | \healthy\ |
| 包内 Python 行尾 | LF 308 / CRLF 0 |

测试数量从 4809 增到 4814，多出的是这一轮加的两组文档守卫
（\	est_doc_numbers.py\ 5 项 + \	est_customer_language.py\ 6 项，
部分与其他文件共用命名空间）。
