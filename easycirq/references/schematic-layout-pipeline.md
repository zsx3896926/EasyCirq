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

规划器排布细节（planner workstream 合并后）：

- 每块可带可选 `halo`（网络标签/引脚桩净空，spec 或实测包络里给）：分区 padding 取
  `max(zonePad, halo)`，且该块与货架邻居的水平间距抬到 `prev_pad + next_pad + 2`、上下层间距抬到
  `titleGap + upper_pad + lower_pad + 2`。halo 预留不会被"排不下"直接吃掉：先按
  full → half → plain gap 逐级降级预留，降级后仍排不下才 unplaced，残余压缩计入 `halo_clipped`。
  负数 `halo` 直接报错、`blocked`；placement 会带 `halo` 便于审计。
- 候选生成：nominal gap 起步，再按 `0.75/0.5/0.25/0` 倍 gap × halo 预留比例 × 反向区域顺序生成去重候选。
  选择层级：放置块数最多 → 优先 nominal gap → halo 保留最多 → `score` 最高（同分保留更早的确定性候选），
  因此输出确定且是这批候选里最好的布局。收紧 gap 造成的标题净空损失计入 `title_clearance_violations`。
- 分区框不得压标题栏：面向标题栏的边会被裁到净空外，`zone_title_block_overlaps` 是回归守卫（应为 0）。

单工程规划（在**仓库根目录**执行；包络路径相对仓库根）：

```bash
python easycirq/scripts/sch_layout_plan.py spec.json --envelopes easycirq/assets/block-envelopes.json
```

`--envelopes` 也可省略：脚本默认读 `easycirq/assets/block-envelopes.json`；写成 `assets/...`
只有当前目录是 `easycirq/` 时才有效，否则报 `No such file or directory` 并 `blocked`（exit 2）。

spec 最小示例（`easycirq-sch-layout-plan/v1`）：

```json
{
  "schema": "easycirq-sch-layout-plan/v1",
  "page": {"width": 1170, "height": 825, "margin": 12},
  "titleBlock": {"minX": 610, "minY": 12, "maxX": 1170, "maxY": 380},
  "blocks": [
    {"id": "block.es8311_codec_i2s", "title": "音频编解码 ES8311", "halo": 24}
  ],
  "options": {"gap": 40, "zonePad": 16, "titleGap": 36}
}
```

块只给 `id/title` 时由 `--envelopes` 补包络；`envelope`、`halo`、`options` 都可省
（options 缺省 gap 40 / zonePad 16 / titleGap 36，且 gap 会被抬到至少 `titleGap + 6`）。
`block-envelopes.json` 目前不含 `halo` 字段，需要净空时在 spec 里给。

### 2.1 离线自检（2026-10-29 实测）

在仓库根目录跑这三个命令，确认工具与本节的输出字段仍一致（planner-v3 合并后复测）：

- `sch_layout_batch.py --sizes 2,3 --top 5`：`pool_size=11, evaluated=220, passed=210`，top 分 `99.9`，前 3 个组合均 `fits=3, overlaps=0, area_usage≈0.45, title_clearance_violations=0`；
- 音频三块（ES8311 + MEMS + AW8737）单工程规划：`verdict=pass, fits=3, zones_contain_blocks=3, overlaps=0, area_usage=0.366, zones_trimmed=1, halo_clipped=0, zone_title_block_overlaps=0, zone_slack=0.09, zone_fill_ratio=0.803, layout_balance=2.105, title_clearance_violations=0, score=92.6`（面积偏离扣 3.4、`layout_balance>1.6` 扣 4.0）；
- scoreboard 对 1 个通过 + 2 个 review 的报告：`reports=3, passed=1`，exit `1`；全部通过时 exit `0`，Markdown 表含 `wires ok/total` 与 `rate` 列。

这些数字只证明离线规划/汇总在该快照上可复现，不是真机落点结果。

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

### 3.1 常见失败与处理

| 现象 | 原因 | 处理 |
|---|---|---|
| `project open failed: window ... is not connected` | daemon 重启/连接器重连后 window id 变了 | 先 `project info` 取 **live windowId**，不硬编码 |
| `block-apply --json` 长时间不返回 | 真实落块加 `--json` 会卡分钟级 | 去掉 `--json`，用落块前后 designator 差集识别新器件 |
| `sch clear` 返回 ok 但零件数 > 0 | 页面残留未清空 | 落块前校验 parts=0，否则中止，先清理再放 |
| `frame apply` 报 `width: got ..., expected ...` | zone 坐标带小数 | zone 坐标全部取整 |
| 写入长时间挂起、guard 不释放 | daemon write-transition guard 卡死 | `easycirq daemon stop/start`，等连接器重连再继续 |
| 块间重叠多 | 多来自桩线/netflag 等附件占位，不是器件本体 | 加大 gap（实测 80 有效），比反复微调原点稳 |
| 块被挤掉/越出页边距 | `--at` 锚点解释与包络偏移因块而异 | 读实测 bbox → `group-move` 校正 → margin clamp |

真机现象与逐轮处置记录见 `docs/nightly-training/2026-10-29.md`；这些处理不改变"落点后必须回读 + 按实测重建 zone"的协议。

### 3.2 一键流水线（run_layout_pipeline.py）

把"读包络 → 规划 → 打分排序 →（真机 apply）→ scoreboard"串成一条命令：

```bash
python tools/run_layout_pipeline.py --project specs/demo.project.json --dry-run
python tools/run_layout_pipeline.py --projects specs --out-dir pipeline-out
python tools/run_layout_pipeline.py --projects specs --skip-eda   # --dry-run 别名
```

`*.project.json` 形如 `{name, project_uuid, page, blocks[], gap}`；也可给
`{"plan": "out/x.plan.json"}` 复用已有计划。输出到 `--out-dir`（默认 `./pipeline-out`）：
`<name>.plan.json`、`<name>.decision-record.md`（选中方案 + top-3 离线候选 + 一句理由）、
`<name>.exec.json`（仅真机 apply）、`<name>.report.json` / `<name>.png`、`scoreboard.json`、
`pipeline-report.json`、`dashboard.md`。

- `--dry-run` / `--skip-eda` 只做离线规划与打分，打印 `offline plan OK, EDA would run`，
  不需要 daemon 或 EasyEDA 窗口；
- 去掉这两个 flag 才对每个工程跑 `tools/sch_layout_apply.py`，需要 daemon + 已连接窗口，
  以及 spec 里的 `project_uuid` / `page`；
- 退出码：全部规划（或 apply）无管线错误 0；任一工程失败或 `blocked` 1；参数/输入非法 2。
  `review` 仍是 0——管线只报布局质量，不冒充验收证据。

## 4. 指标自动化

```bash
python tools/metrics_scoreboard.py --reports <dir> --out scoreboard.json
python tools/metrics_scoreboard.py --reports <dir> \
  --style-input-dir <dir> --export-dir <dir> --out scoreboard.json
```

汇总每个工程的：块数、fits、overlaps、zones ok、export ok、连线成功率
（`wires_ok / wires_total`，从 autoconnect 输出的 `new/already/PARTIAL` 解析）。
字段含义、缺失值回退与通过条件见 §6。

可选风格/视觉列（**只作参考，不改通过判定和退出码**）：

- `--style-input-dir`：对每个工程读 `<project>.style.json`（`easycirq-sch-style-input/v1`），
  用 `easycirq/scripts/sch_style_audit.py` 审计，行上增加 `style_verdict / style_score / style_problems`；
- `--export-dir`：对每个工程读 `<project>.png`，与参考图
  `easycirq/assets/style-reference/esp32-schematic.png` 用 `easycirq/scripts/sch_style_visual.py` 粗比，
  行上增加 `visual_verdict / visual_similarity`。

文件缺失、未装 Pillow 或视觉比较失败 → 对应字段为 `null`（Markdown 列只在至少一行有值时出现）；
style 输入坏掉不崩溃，记 `blocked` / 0 分并把报错放进 `style_problems`。风格分只对同一份
`<project>.style.json` 有效，相似度只对同页/同修订导出的 PNG 有效，都不能当作电气或制造证据。

验收通过条件：`fits == blocks && overlaps == 0 && zones_ok && export_ok`；
连线成功率、风格分与视觉相似度单独看趋势，不单独阻断。

## 5. 评分与阈值

规划器 `score`（0–100，`_score()` 实现）：重叠 −25/对，未落块 −30/个，面积占比偏离 0.45
−40×差；`zone_fill_ratio` 偏离 0.55–0.85 区间 −70×偏离；`layout_balance` 超过 1.6
−8×超出；zone 空白超出 0.25 −60×超出；标题净空违规 −8/处；`halo_clipped` −4/块；
`zone_title_block_overlaps` −10/处。

- `score ≥ 90`：可直接进真机验收；
- `70–90`：先调整块组合/gap/zonePad；
- `< 70`：拆页或换块。

## 6. 指标定义（planner / scoreboard）

规划器输出 `easycirq-sch-layout/v1`，看板输出 `easycirq-sch-layout-scoreboard/v1`；字段名相近但口径不同，验收只看
`fits / overlaps / zones_ok / export_ok`，`score` 只作排序与调参依据。

| 字段 | 出现在 | 定义 / 计算 | 通过条件 |
|---|---|---|---|
| `blocks[].halo` | planner 输入 | 每块可选净空（给网络标签/引脚桩）；分区 padding 取 `max(zonePad, halo)`，排不下时按 full→half→plain gap 降级预留，placement 回带 `halo` | 缺省 0；负数 → 报错、`blocked` |
| `metrics.fits` | planner | 规划 bbox 完整落在页边距内的块数 | `fits == len(blocks)` |
| `unplaced[]` | planner | 排不进任何可用区或越出页边距的块 id 列表 | 必须为空，否则 `verdict=blocked`、exit 2 |
| `metrics.overlaps` | planner | 块 bbox 两两相交对数（交面积 > 0） | 必须为 0，否则 `verdict=review`、exit 1 |
| `metrics.zones_contain_blocks` | planner | 成功生成"包含块"分区框的块数 | 等于 `fits` 时分区完整 |
| `metrics.halo_clipped` | planner | halo 预留降级后仍被页边或邻居削掉的块数（实际 zone 与 `bbox + 预留` 差 > 0.5 即计） | 0 最理想；>0 只说明净空被压缩，不单独判失败，每块 −4 分 |
| `metrics.zone_title_block_overlaps` | planner | 分区框覆盖标题栏矩形的个数；面向标题栏的边会被裁开 | 回归守卫，必须 0，否则每处 −10 分 |
| `metrics.zones_trimmed` | planner | 安全裁剪分区框的次数；边缘按最近邻中点封顶不足时，由兜底裁剪消除重叠。0 是理想值，音频三块规划实测为 1 | 仅诊断，不单独判失败 |
| `metrics.area_usage` | planner | Σ 块 bbox 面积 / 页面面积，保留 3 位小数 | 目标 0.45，偏离进入 `score` 罚分 |
| `metrics.zone_slack` | planner | Σ 分区框面积 / 页面面积 − `area_usage`（分区内空余占比） | > 0.25 开始按 60×超出罚分 |
| `metrics.zone_fill_ratio` | planner | Σ 块 bbox 面积 / Σ 分区框面积，3 位小数；高=分区紧、低=分区空 | 0.55–0.85 不罚分，区间外按 70×偏离罚分 |
| `metrics.layout_balance` | planner | 最大分区面积 / 最小分区面积，3 位小数；单分区恒为 1.0 | ≤ 1.6，超出按 8×超出罚分 |
| `metrics.title_clearance_violations` | planner | 分区标题压到块上方的块数（`titleY < bbox.maxY + 10`） | 0，否则每处 −8 分 |
| `metrics.regions` | planner | 可用区名：`left`（标题栏左侧整条）、`top-right`（标题栏上方）、无标题栏时为 `page` | 诊断用，确认是否只用了部分区域 |
| `metrics.score` | planner | 0–100 质量分，罚分项见 §5；下限 0、1 位小数 | ≥90 进真机；70–90 调参；<70 拆页/换块 |
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
| `rows[].style_verdict` | scoreboard（`--style-input-dir`） | `<project>.style.json` 经 `sch_style_audit.py` 的 `pass/review/blocked` | advisory，不改行 `verdict` 与退出码 |
| `rows[].style_score` | scoreboard | `100 − 15×blocked 问题数 − 4×review 问题数`，0–100 | advisory，只看趋势 |
| `rows[].style_problems` | scoreboard | 扣分背后的 `[{severity, message}]`；坏 style 输入时记 `blocked`/0 分并带报错 | advisory |
| `rows[].visual_verdict` | scoreboard（`--export-dir`） | `<project>.png` 与参考图经 `sch_style_visual.py` 的 `pass/review/blocked` | advisory |
| `rows[].visual_similarity` | scoreboard | 0–1 粗相似度（0.4 灰度相关 + 0.3 直方图余弦 + 0.3 色板出现率），不是审美判断 | advisory |
| `rows[].verdict` | scoreboard | `fits == blocks && overlaps == 0 && zones_ok && export_ok` 为 `pass`，否则 `review` | `pass` 才算验收通过 |

风格/视觉字段在未给目录、文件缺失、未装 Pillow 或比较失败时为 `null`；Markdown 的 style/visual 列
只在至少一行有值时出现。这两类字段只作参考，row `verdict` 和进程退出码仍只看
`fits/overlaps/zones_ok/export_ok`。

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
在交付前检查。scoreboard 可用 `--style-input-dir / --export-dir` 把这两项汇总成
`style_* / visual_*` 列，但那是**参考指标**：行 `verdict` 与退出码仍只看
`fits/overlaps/zones_ok/export_ok`，交付门禁以 `sch_delivery_check.py` / `sch_delivery_hook.py` 为准。
