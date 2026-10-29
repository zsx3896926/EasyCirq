# 知识沉淀协议（L0–L6）

> 目标：让每次夜间训练产生的经验，落到**可执行、可检查、可复用**的层，而不是留在聊天记录或某个人脑子里。
> 配套：[原理图布局思考框架](schematic-layout-thinking.md)（怎么想）、[失败分类目录](failure-taxonomy.md)（怎么不重犯）。

## 0. 三条基本规则

1. **只向上沉淀，不跨层跳。** L0 证据不能直接当 L2 规则用；"我在聊天里看到 gap 用 80" 是不可复用的传说。
2. **每层有 owner 和过时检查。** 没有 owner 的层会腐烂；没有过时检查的层会骗人。
3. **沉淀的完成标准是机器能判。** 写不出检查命令/阈值/测试的条目，只能放 L0/L6，不能冒充 L2/L3。

## 1. 分层总表

| 层 | 名称 | 存什么 | 放哪 | 谁拥有 | 更新触发 | 过时检查 |
|---|---|---|---|---|---|---|
| L0 | 证据 | 原始输出、渲染图、report、日志、失败现场 | `docs/evidence/<topic>-<date>/`；夜间临时输出目录 | 执行者（runner） | 每次真机运行（成功也要） | 有日期/工程/页/HEAD/EDA 版本；无版本的证据视为过期 |
| L1 | 数据资产 | 实测包络表、参考图、风格 token、已解析 parts、页面/图签几何 | `easycirq/assets/` | 数据/风格维护者 | 块器件变化、EDA/符号库版本变化 | `measured_at` + 版本字段；与当前块定义/客户端不符即重测 |
| L2 | 规则/契约 | SKILL 规则（R0–R12）、风格规范、流水线协议、图面判据 | `easycirq/SKILL.md`、`easycirq/references/` | Skill 维护者 | 新失败类、重复手工决策、工具行为变化 | 文档默认值 vs 代码默认值；链接可解析；规则可被检查 |
| L3 | 工具 | planner / batch / apply / scoreboard | `easycirq/scripts/`、`tools/` | 工具维护者 | 任何新守卫、默认值、协议步骤 | `--help` 与实际行为一致；输出 schema 有版本；有测试 |
| L4 | 测试/回归 | 单元测试、fixture、基准、golden report | `tests/`、`benchmarks/`、`docs/nightly-training/bench_layout_planner.py` | 测试维护者 | 每个失败类至少加一个测试/基准 | CI 绿；测试数与文档一致；基准输入与 L1 同步 |
| L5 | 决策记录 | magic number、协议取舍、被推翻的结论 | `docs/method/`（参数索引）+ `easycirq/assets/decisions/` | 决策提出者 | 新增/修改参数、改协议、推翻旧结论 | 有效条件与重评触发；旧条目标 `superseded` |
| L6 | 夜间复盘 | 每轮目标、数字、失败、下一轮 | `docs/nightly-training/YYYY-MM-DD.md` | 夜间执行者 | 每次训练结束 | 数字能与 L0/report 对上；下一轮任务有闭环 |

一句话记法：**L0 是事实，L1 是尺子，L2 是规矩，L3 是手，L4 是护栏，L5 是理由，L6 是日志。**

## 2. L0 证据层：先保住现场

**存什么**

- 真机运行的完整 stdout/stderr、退出码；`.report.json`、`*.zones.json`、`scoreboard.json`。
- 官方导出 PNG/SVG（`sch export-image`），失败现场截图。
- 失败时的完整报错原文（如 `document transition is being verified`、`width: got 419.7, expected 419.66408`）。

**放哪**

- 仓库内长期证据：`docs/evidence/<topic>-<date>/`（示例：`docs/evidence/eda-2026-10-21/README.md`）。
- 夜间临时产物（renders/report）可以放仓库外目录，但**结论所依赖的最小证据**（导出图 + report + 命令清单）必须回填仓库或夜间日志。

**owner / 触发 / 过时**

| 项 | 要求 |
|---|---|
| owner | 执行者（跑这条命令的人/Agent） |
| 更新触发 | 每次真机运行；失败也必须留证 |
| 最小字段 | 命令、工作目录、时间、工程/页 UUID、`windowId`、工具/daemon/connector/EDA 版本、退出码、输出格式（json/text/mixed）、文件 SHA-256 |
| 过时检查 | 证据文件必须能追溯到工程版本（HEAD/文件哈希）与 EDA 版本；缺任一字段 → 只能作参考，不能作验收 |

**纪律**：原始输出不手改；`.json` 文件名不等于内容是 JSON（见 [tool-gotchas](../../easycirq/references/tool-gotchas.md) §9）；失败证据比成功证据更有价值，不许为了好看删掉。

## 3. L1 数据资产层：把"量过的东西"变成尺子

**存什么**

- `easycirq/assets/block-envelopes.json`：块实测包络（raw）、页面与标题栏几何、`measured_at`。
- `easycirq/assets/style-reference/`：参考图 + `style-tokens.json`。
- 已解析的 parts 清单（站点 `easyeda.com` vs `lceda.cn` 的 deviceUuid 不能混用）。
- 需要复用的规划 spec / 页面模板。

**放哪 / owner / 触发**

| 项 | 要求 |
|---|---|
| 路径 | `easycirq/assets/`（机器可读，schema 带 `/v1`） |
| owner | 数据/风格维护者 |
| 更新触发 | 块内器件/附件变化；EDA 或符号库升级；页面模板变化；首次进入某块 |
| 过时检查 | `measured_at` 与版本字段；与当前块定义/客户端不符 → 重测，不沿用 |

**今晚的反例（必须记住）**：`docs/nightly-training/bench_layout_planner.py` 里的 `ENVELOPES` 还是早期估算（wroom 460×100、es8311 560×340），与资产表实测值（245×420、521×309）不一致。这说明基准/脚本不能各自存一份包络——**单一数据源**是资产表，其他脚本应读它。

**重测 SOP**

1. 空页落一个块（`sch block-apply`，不带 `--json`）。
2. `schematic.components.list --payload '{"includeBBox":true}'` 读全部 part bbox。
3. 对块内 designator 求并集 → 写 `w/h` 与 `measured_at`。
4. 跑 planner 测试与 batch，确认新包络不把原有组合打成 blocked。
5. 在夜间日志记录"重测哪个块、旧值→新值、影响哪些工程"。

## 4. L2 规则/契约层：写成能被检查的规矩

**存什么**

- `easycirq/SKILL.md` 的 R0–R12（尤其 R12 先版式后器件）。
- `references/schematic-style.md`（模板/分区/字号/标题栏）、`references/schematic-layout.md`（图面验收）、`references/schematic-layout-pipeline.md`（工具协议）。
- 本文与 `schematic-layout-thinking.md` 的方法规则。

**owner / 触发 / 过时**

| 项 | 要求 |
|---|---|
| owner | Skill 维护者 |
| 更新触发 | 新失败类；同类手工决策出现第 2 次；工具默认值变化 |
| 过时检查 | ① 文档里的默认值与代码默认值一致（例：`gap` 文档 80 vs planner 默认 `max(40, titleGap+6)`，两者都要写明"哪个是视觉间距、哪个是净空下限"）；② 相对链接可解析；③ 每条规则有判据/命令/阈值 |

**纪律**：规则不写"注意美观""尽量整齐"这类不可检查的话；写成"标题在块上方 ≥36 raw""分区不重叠""overlaps=0"。规则与工具冲突时以当前工具行为和页面实测为准，并立刻回写文档，不长期双轨。

## 5. L3 工具层：把手艺变成手

**存什么**

| 工具 | 输入 | 输出 | 守卫 | 消费方 |
|---|---|---|---|---|
| `easycirq/scripts/sch_layout_plan.py` | `easycirq-sch-layout-plan/v1` + 包络表 | `easycirq-sch-layout/v1`（frames/placements/metrics） | 缺包络 blocked；分区中点封顶；整数坐标 | batch、人工 |
| `easycirq/scripts/sch_layout_batch.py` | 组合池/尺寸 | `easycirq-sch-layout-batch/v1`（排序结果） | 未知块跳过并告警 | 夜间流程 |
| `tools/sch_layout_apply.py` | plan + parts + 工程/页 | `.report.json` + PNG + zones | live windowId、clear 校验、designator 差集、margin clamp、整数 zone | scoreboard |
| `tools/metrics_scoreboard.py` | `*.report.json` | `easycirq-sch-layout-scoreboard/v1` + Markdown | 缺字段按 0/None 处理 | 夜间汇报 |

**owner / 触发 / 过时**

- owner：工具维护者。
- 更新触发：任何新守卫/默认值/协议步骤都必须同时改工具与文档（工具优先）。
- 过时检查：`--help` 与实际行为一致；输出 schema 版本变化要通知消费方；工具内每个 magic number 有来源注释（引 L5）。

**纪律**：一次性脚本（如夜间临时 `layout_exec.py`）不许直接当工具用；要沉淀就先抽象成参数化工具 + 测试，再进 L3。工具必须输出 metrics，否则无法进 L4/L6。

## 6. L4 测试/回归层：让"修好了"可证明

**存什么**

| 资产 | 当前内容 | 覆盖的失败类 |
|---|---|---|
| `tests/test_sch_layout_plan.py` | 8 个用例：三块避让标题栏、分区含块且标题在上、分区互不重叠、块太多 blocked、无标题栏用满页、缺包络查表、缺包络 blocked、非法输入 blocked | FD-01、FG-02、FG-04 |
| `tests/test_sch_layout_batch.py` | 5 个用例：排序、未知块跳过、全池确定性 | 离线批量 |
| `tests/test_metrics_scoreboard.py` | 3 个用例：全 pass、混合 review/fail 退出码、fits 不足判 review | 指标汇总 |
| `docs/nightly-training/bench_layout_planner.py` | 组合基准（离线） | 规划稳定性（**注意**：其包络需改为读 L1 资产表） |

**owner / 触发 / 过时**

| 项 | 要求 |
|---|---|
| owner | 测试维护者 |
| 更新触发 | 每新增一个失败类 → 至少一个测试或基准断言；每个守卫 → 一个"不满足时拒绝"的用例 |
| 过时检查 | CI 绿；测试数与 README/日志一致；基准输入与 L1 同步；`simulated` 标记不被当成真机 |

**纪律**：测试断言失败签名，不只断言返回码。例：clear 校验的测试要断言"零件数 > 0 时工具中止"，不是"函数返回了 dict"。

## 7. L5 决策记录层：每个数字都有出处

**存什么**

- magic number：`gap=80`、`zonePad=16`、`titleGap=36`、`margin=12`、评分权重、8 raw 校正阈值、各步 sleep。
- 协议取舍：为什么不用 `block-apply --json`、为什么 zone 要整数、为什么先量后画。
- 被推翻的结论（保留旧条目 + 原因）。

**放哪**

- 索引：[schematic-layout-thinking.md §6](schematic-layout-thinking.md#6-每个-magic-number-一条决策记录)。
- 完整决策：按 [决策记录模板](../../easycirq/assets/decisions/decision-record.template.md) 写进工程 `engineering-notes.md`，或在本目录新增 `decisions/NNNN-*.md`。

**owner / 触发 / 过时**

| 项 | 要求 |
|---|---|
| owner | 决策提出者（谁改参数谁记录） |
| 更新触发 | 新增/修改参数、改协议、旧结论被推翻 |
| 过时检查 | 有"有效条件 + 重评触发"；被替代时链接到新条目；代码引用决策 ID 能对上 |

**最小格式**：值 / 单位 / 来源（证据路径） / 有效条件 / 重评触发 / 状态（`active`/`superseded`）。六项缺一不算决策记录。

## 8. L6 夜间复盘层：把一天变成下一轮的输入

**存什么**

`docs/nightly-training/YYYY-MM-DD.md`：目标、每轮做了什么、**数字**（fits/overlaps/zones/export/wires/score）、失败与根因、下一轮任务。

**owner / 触发 / 过时**

| 项 | 要求 |
|---|---|
| owner | 夜间执行者 |
| 更新触发 | 每次训练结束（当晚） |
| 过时检查 | ① 数字与 `.report.json`/scoreboard 对得上；② "下一轮"任务在后续日志有闭环（完成/改向/放弃及原因）；③ 新增失败已进 L5/taxonomy |

**纪律**：复盘里不写形容词，写数字和签名。"今天效果不错"无效；"A/C fits=3/3、overlaps=0、zones ok、export ok；B 缺块"有效。

## 9. 完成定义（DoD）：executable + checkable + reusable

沉淀物必须同时过三关，缺一只能算草稿：

| 关卡 | 判据 | 反例 | 正例 |
|---|---|---|---|
| **可执行** | 有命令、有输入、有输出；新 Agent 不读聊天记录也能跑出同样结果 | "我改了一下参数就好了" | `python easycirq/scripts/sch_layout_plan.py spec.json --envelopes ...` |
| **可检查** | 机器能判 PASS/FAIL（退出码、字段阈值、测试断言） | "看起来不重叠" | `metrics.overlaps == 0`；`test_frames_do_not_overlap_each_other` |
| **可复用** | 换工程/块/页面仍成立；参数带有效条件，无硬编码工程 UUID/坐标 | 某工程 `(660,560)` 坐标当模板 | `gap=80` + "单页 ≤3 块、包络表 2026-10-29" 条件 |

按层看 DoD：

| 层 | executable | checkable | reusable |
|---|---|---|---|
| L0 | 命令能重放 | 有退出码/输出 | 换工程仍可重放（只作参考） |
| L1 | 重测脚本/命令 | schema + 字段校验 | 包络表对所有工程通用 |
| L2 | 规则能落到命令 | 判据/阈值明确 | 不绑定单一工程 |
| L3 | 一条命令 | 工具自己有校验/拒绝 | 参数化 |
| L4 | 测试命令 | 断言 | fixture 可换 |
| L5 | 决策可追溯 | 有效条件可验证 | 重评触发明确 |
| L6 | 日志可读 | 数字可与 report 对账 | 下一轮可直接用 |

## 10. 一次失败如何沉淀：6 步 SOP

| 步 | 动作 | 产物 | 放哪 | 验收 |
|---|---|---|---|---|
| 1 | 保住现场 | 原始输出 + 截图/report | L0 | 命令/版本/退出码齐全 |
| 2 | 归类 | FX/FT/FG/FD/FP 稳定 ID | [failure-taxonomy.md](failure-taxonomy.md) | 症状一句话 + 检测方法 |
| 3 | 加自动检查 | 测试 / report 字段 / regex | L4 / L3 | 机器能判 PASS/FAIL |
| 4 | 加工具守卫 | 前置校验、默认值、拒绝执行 | L3 | 失败时工具自己挡住 |
| 5 | 更新规则与决策 | 规则条目 + magic number 决策记录 | L2 / L5 | 手工步骤从流程删除 |
| 6 | 复盘 | 数字 + 根因 + 下一轮 | L6 | 与 report 对账 |

超过 3 天仍未走到第 3 步的失败，在 taxonomy 里标 `欠账`，不要假装已修完。

## 11. 层间一致性检查（建议每次夜间收口跑）

| 检查 | 命令/方法 | 失败后果 |
|---|---|---|
| 文档默认值 vs 代码默认值 | `grep -n "gap" easycirq/scripts/sch_layout_plan.py` 与本文 §6 对照 | 按错误 gap 规划 |
| 包络资产是否过期 | 读 `block-envelopes.json` 的 `measured_at`；超 30 天或块变更 → 重测 | 落点/分区全错 |
| 基准包络是否跟资产表同步 | 对照 `bench_layout_planner.py` 的 `ENVELOPES` 与资产表 | 基准结果不可信 |
| 测试数与文档一致 | `python -m unittest discover -s tests -p "test_sch_layout*.py"` | 文档虚报覆盖 |
| 相对链接可解析 | 遍历 md 链接检查目标文件存在 | 文档导航断裂 |
| taxonomy 条目有检测方法 | 抽查 5 条：是否写了命令/字段 | 分类退化成故事 |
| 决策记录有有效条件 | 抽查 magic number：六项是否齐全 | 参数变成裸魔法 |

## 12. 目录映射与相关文档

| 层 | 现有路径 |
|---|---|
| L0 | `docs/evidence/`、夜间输出目录（renders/report） |
| L1 | `easycirq/assets/block-envelopes.json`、`easycirq/assets/style-reference/` |
| L2 | `easycirq/SKILL.md`、`easycirq/references/schematic-*.md`、`docs/method/*.md` |
| L3 | `easycirq/scripts/sch_layout_plan.py`、`sch_layout_batch.py`、`tools/sch_layout_apply.py`、`tools/metrics_scoreboard.py` |
| L4 | `tests/test_sch_layout_plan.py`、`test_sch_layout_batch.py`、`test_metrics_scoreboard.py`、`docs/nightly-training/bench_layout_planner.py` |
| L5 | `easycirq/assets/decisions/`、本文与 thinking §6 |
| L6 | `docs/nightly-training/2026-10-29.md`（及后续日期） |

相关： [布局流水线](../../easycirq/references/schematic-layout-pipeline.md) · [思考框架](schematic-layout-thinking.md) · [失败分类](failure-taxonomy.md) · [EDA 动作陷阱](../../easycirq/references/tool-gotchas.md) · [反馈闭环](../../easycirq/references/feedback-loop.md) · [离线回归](../../easycirq/references/offline-regression.md)
