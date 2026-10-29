# 原理图布局流水线（离线优先）

目标：把"先量尺寸 → 算可用区 → 排布 → 落点 → 校验 → 导出"变成可重复的流水线，
并拆成**离线**（快、可批量）与**真机**（慢、只做验收）两段。

> 图面表达与验收规则见 [原理图排版与看图验收](schematic-layout.md)；
> 本文只讲"块布局"这一层的工具与协议。

## 1. 量尺寸（一次性，块变更时重测）

`assets/block-envelopes.json` 记录每个标准块在 EasyEDA Pro 上的真实渲染包络：

```json
{"block.es8311_codec_i2s": {"w": 521, "h": 309}}
```

来源：空页落块 → `schematic.components.list includeBBox` → `minX/minY/maxX/maxY`。
**不要用 `block-apply --dry-run` 的"块估算"**：它会低估高度（WROOM 实测 245×420，
dry-run 报 460×100）。

## 2. 离线批量规划（秒级，不走 EDA）

```bash
python easycirq/scripts/sch_layout_batch.py --sizes 2,3 --top 10 --out batch.json
```

- 枚举块组合 → `sch_layout_plan.plan` 排布 → 打分排序；
- 页面 1170×825，标题栏矩形（610..1170 × 12..380）；
- 输出：`fits / overlaps / area_usage / zone_slack / title_clearance_violations / score`；
- 只把 `top` 的 1–3 个方案拿去真机验收。

单工程规划：

```bash
python easycirq/scripts/sch_layout_plan.py spec.json --envelopes assets/block-envelopes.json
```

## 3. 真机落点（每个工程一次）

`tools/sch_layout_apply.py` 的固定协议：

1. `project info` 取 **live windowId**（daemon 重启/连接器重连后 window id 会变）；
2. `project open` + `document.open`，等 reads 稳定；
3. `sch clear` 后**校验 parts=0**，否则中止（不能带病落块）；
4. 逐块 `block-apply --at <planned origin>`（**不要加 `--json`**：真实执行会卡分钟级）；
5. 落块前后 designator 差集识别新器件 → 读实测 bbox → `sch group-move --groups`
   （provenance group 名是 `<short-block-id>(<instance>)/...`）校正；
6. 越出页边距再用 group-move 拉回（margin clamp）；
7. 按**实测 bbox** 重建每块 zone（标题净空、重叠修剪、坐标取整），一次性 `frame apply`；
8. `layout-lint` → 导出 PNG → 写 `.report.json`。

环境坑：daemon 的 write-transition guard 会卡死 → `daemon stop/start`；frame 回读
不接受浮点坐标 → zone 全部取整。

## 4. 指标自动化

```bash
python tools/metrics_scoreboard.py --reports <dir> --out scoreboard.json
```

汇总每个工程的：块数、fits、overlaps、zones ok、export ok、连线成功率
（`wires_ok / wires_total`，从 autoconnect 输出的 `new/already/PARTIAL` 解析）。
字段含义、缺失值回退与通过条件见 §6。

验收通过条件：`fits == blocks && overlaps == 0 && zones_ok && export_ok`；
连线成功率单独看趋势，不单独阻断。

## 5. 评分与阈值

规划器 `score`（0–100）：重叠 −25/对，未落块 −30/个，面积占比偏离 0.45 −40×差，
zone 空白超出 0.25 −60×超出，标题净空违规 −8/处。

- `score ≥ 90`：可直接进真机验收；
- `70–90`：先调整块组合/gap/zonePad；
- `< 70`：拆页或换块。

## 6. 指标定义（planner / scoreboard）

规划器输出 `easycirq-sch-layout/v1`，看板输出 `easycirq-sch-layout-scoreboard/v1`；字段名相近但口径不同，验收只看
`fits / overlaps / zones_ok / export_ok`，`score` 只作排序与调参依据。

| 字段 | 出现在 | 定义 / 计算 | 通过条件 |
|---|---|---|---|
| `metrics.fits` | planner | 规划 bbox 完整落在页边距内的块数 | `fits == len(blocks)` |
| `unplaced[]` | planner | 排不进任何可用区或越出页边距的块 id 列表 | 必须为空，否则 `verdict=blocked`、exit 2 |
| `metrics.overlaps` | planner | 块 bbox 两两相交对数（交面积 > 0） | 必须为 0，否则 `verdict=review`、exit 1 |
| `metrics.zones_contain_blocks` | planner | 成功生成"包含块"分区框的块数 | 等于 `fits` 时分区完整 |
| `metrics.zones_trimmed` | planner | 安全裁剪分区框的次数；边缘已按最近邻中点封顶，正常应为 0 | 仅诊断，不单独判失败 |
| `metrics.area_usage` | planner | Σ 块 bbox 面积 / 页面面积，保留 3 位小数 | 目标 0.45，偏离进入 `score` 罚分 |
| `metrics.zone_slack` | planner | Σ 分区框面积 / 页面面积 − `area_usage`（分区内空余占比） | > 0.25 开始按 60×超出罚分 |
| `metrics.title_clearance_violations` | planner | 分区标题压到块上方的块数（`titleY < bbox.maxY + 10`） | 0，否则每处 −8 分 |
| `metrics.regions` | planner | 可用区名：`left`（标题栏左侧整条）、`top-right`（标题栏上方）、无标题栏时为 `page` | 诊断用，确认是否只用了部分区域 |
| `metrics.score` | planner | 0–100 质量分，公式见 §5；下限 0、1 位小数 | ≥90 进真机；70–90 调参；<70 拆页/换块 |
| `verdict` | planner 顶层 | `pass` / `review` / `blocked` | 分别对应进程退出码 0 / 1 / 2 |
| `reports` / `passed` | scoreboard 顶层 | 读到的 `*.report.json` 数 / 其中验收通过的工程数 | `passed == reports` 时 exit 0 |
| `rows[].project` | scoreboard | 工程名：`report.project`，缺省为文件名去掉 `.report` | 仅展示 |
| `rows[].page` | scoreboard | 页标识（`report.page`） | 仅展示 |
| `rows[].blocks` | scoreboard | 块数：`metrics.blocks`，缺省 `len(report.blocks)` | 验收分母 |
| `rows[].fits` | scoreboard | 实测落页块数（落块后实测 bbox 在页边距内） | `fits == blocks` |
| `rows[].overlaps` | scoreboard | 实测块重叠对数，缺省 0 | `== 0` |
| `rows[].zones_ok` | scoreboard | `report.zones_reapplied == 0`（frame apply 退出码 0） | `true` |
| `rows[].export_ok` | scoreboard | `report.export == 0`（导出 PNG 退出码 0） | `true` |
| `rows[].wires_total/ok/failed` | scoreboard | 优先取 `metrics.wires_*`；缺失时按 `blocks[].wires` 求和 | 只记趋势，不阻断 |
| `rows[].wire_rate` | scoreboard | `wires_ok / wires_total`，保留 3 位小数；总数为 0 时为 `null` | 只记趋势，不单独阻断 |
| `rows[].verdict` | scoreboard | `fits == blocks && overlaps == 0 && zones_ok && export_ok` 为 `pass`，否则 `review` | `pass` 才算验收通过 |

两个口径的区别：planner 的 `blocked` 只在有块排不下时出现，scoreboard 只有 `pass/review`；
planner 的 `overlaps` 是规划 bbox 的重叠，scoreboard 是落块后实测 bbox 的重叠。
不要把 `score` 当验收，也不要把规划 `pass` 当成真机通过。

批量规划 `easycirq-sch-layout-batch/v1` 的返回：顶层 `pool_size / sizes / evaluated / passed / results / top`；
每条 result 是 `{blocks, verdict, score, metrics{fits, overlaps, area_usage, zone_slack, title_clearance_violations}, unplaced}`。
`passed == 0` 时退出码 2；`top` 里的 1–3 个组合才拿去做真机验收。

## 7. 两小时并行冲刺流程

目的：把规划器、执行器、风格门禁和文档的剩余工作放进一个 2 小时时间盒，多 Agent 并行、离线优先；
每人只写自己的路径，最后由 Lead 集成复核。

### 7.1 时间盒

| 时段 | 动作 | 产出 |
|---|---|---|
| T+0–10 min | 冻结基线（`git rev-parse origin/main`），给每个 Agent 划 worktree/branch、允许写路径、指定测试与验收目标 | 基线 SHA + 分工表 |
| T+10–75 min | 并行实现；离线优先，不碰 EDA/daemon | 各自分支的代码/文档/测试 |
| T+55–80 min | 各自跑指定离线套件，记录**精确计数**（多少 tests、OK/FAILED、退出码） | 可复现的 QA 记录 |
| T+75–95 min | commit → push → 开 PR（Agent 不合并 PR）；等 CI checks | PR 号 + commit SHA |
| T+90–120 min | Lead 集成复核：文档字段与代码一致、测试全绿、变更边界清楚 | 合并顺序或交接说明 |

### 7.2 工作流与写边界

| workstream | 交付 | 写边界 | 验收 |
|---|---|---|---|
| planner | 规划器质量分/评分改进 + 对应测试 | `easycirq/scripts/sch_layout_*`、`tests/test_sch_layout_*` | 规划器套件全绿，新指标写入 `metrics` |
| runner | 一键离线/EDA 流水线 runner + 看板 + 测试 | runner 工具与测试 | 单命令可跑；离线路径不依赖真机 |
| style | 风格审计 + 视觉相似度接入 scoreboard | style 脚本、`tools/metrics_scoreboard.py`、相关测试 | scoreboard 行含风格/相似度字段且有测试覆盖 |
| docs | 流水线文档、交叉链接、夜间日志、离线 QA | 仅文档路径 | 字段与代码一致；QA 计数可复现 |
| method | 思维方法、沉淀协议、失败分类 | method 文档 | 可被 SKILL 引用，不改执行器 |
| lead | 集成与合并决策 | 全部（只复核，不代写） | CI validate 绿；不一致项清零 |

### 7.3 硬规则

1. 每人独立 worktree/branch，只写分工表里的路径；要改别人的文件先报 Lead，不并行改同一文件。
2. 冲刺内不做真机 EDA/daemon 操作；确需真机验收的单独立项，并在日志里用 `NOT RUN` 标出，不能拿离线结果冒充真机。
3. 验收写命令与精确计数（`Ran 8 tests ... OK`），不写"基本通过"；失败要带测试名和报错首行。
4. Agent 不合并 PR；CI 红了先确认是不是自己改动引起，再报 Lead。
5. 文档只描述已实测行为。其他分支尚未合并的字段（例如风格分进 scoreboard）只能写"计划中/本分支未包含"。

### 7.4 离线 QA 入口

逐个套件跑，避免一个套件的 import/sys.path 问题掩盖其他结果：

```bash
python -m unittest discover -s tests -p "test_sch_layout_plan.py"
python -m unittest discover -s tests -p "test_sch_layout_batch.py"
python -m unittest discover -s tests -p "test_metrics_scoreboard.py"
python -m unittest discover -s tests -p "test_sch_style_audit.py"
python -m unittest discover -s tests -p "test_sch_style_plan_check.py"
python -m unittest discover -s tests -p "test_sch_delivery_check.py"
python -m unittest discover -s tests -p "test_sch_delivery_hook.py"
python -m unittest discover -s tests -p "test_sch_style_visual.py"
```

入口用 `discover -s tests`（与 CI `validate.yml` 的 `python3 -m unittest discover -s tests -v` 一致）；
直接 `-m unittest tests.test_xxx` 不走 discover 的 sys.path 处理，个别用例（如
`test_sch_layout_plan.py` 里的 `import sch_layout_plan`）会报 `ModuleNotFoundError`，不能当成功能失败。

## 8. 与风格门禁的关系

布局流水线只保证"块在页内、分区框包含块、不重叠"；审美与规范仍由
`sch_style_audit.py`（色板/字号/标题栏）和 `sch_style_visual.py`（参考图并排+粗相似度）
在交付前检查。
