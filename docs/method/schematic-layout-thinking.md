# 原理图布局思考框架（AI 版）

> 适用：把"标准功能块"排成一张能验收的原理图页面（EasyEDA Pro + easycirq 执行层）。
> 工具与协议见 [布局流水线](../../easycirq/references/schematic-layout-pipeline.md)；版式 token 见 [风格规范](../../easycirq/references/schematic-style.md)；图面判据见 [排版与看图验收](../../easycirq/references/schematic-layout.md)。
> 失败条目见 [failure-taxonomy.md](failure-taxonomy.md)；知识分层见 [sedimentation-protocol.md](sedimentation-protocol.md)。
> 本文只讲"怎么想"；参数以脚本 `--help`、`easycirq capabilities` 与页面实测为准。

## 0. 一句话

**先定判据 → 再量尺寸 → 离线排 → 真机只验一次 → 失败归类并固化成检查/守卫。**

本文来自 2026-10-29 夜间训练（[夜间日志](../nightly-training/2026-10-29.md)）。第一轮的反例是：没有量块尺寸就落点，器件顶出图纸、压标题栏、分区框与标题打架，整轮返工。

## 1. 动手前先定义判据

**没有判据不落点。** 判据写在 spec 或本页表格里，执行时逐项读数，而不是画完再"看着还行"。

| 判据 | 定义 | 通过线 | 数据来源 | 阻塞级别 |
|---|---|---|---|---|
| fits | 每块实测 bbox 完全在内容区内（x∈[12,1158]，y∈[12,813]） | `fits == blocks` | `.report.json` → `metrics.fits` | 硬门禁 |
| overlaps | 实测 bbox 两两相交对数 | `0` | `metrics.overlaps` | 硬门禁 |
| zone containment | 每个分区框包含所属块，标题在块上方（`titleGap` 36 raw） | 全部包含且标题不压块 | `*.zones.json` + frame 回读 | 硬门禁（frame apply 拒收重叠分区） |
| wire success | autoconnect 成功数 / 总数 | 趋势记录：逐轮看 `wires.failed` 是否下降；样本不足，暂不设硬阈值、不单独阻塞 | autoconnect 输出 `new/PARTIAL` → `wires{total,ok,failed}` | 趋势 |
| style score | 风格审计 PASS/REVIEW/BLOCKED | 交付前 PASS 或已修 | `easycirq/scripts/sch_style_audit.py` | 质量 |
| visual similarity | 与参考图粗相似度（长宽比/色板/灰度） | 仅参考，不作通过线 | `easycirq/scripts/sch_style_visual.py` | 参考 |
| planner score | 离线规划质量 0–100 | ≥90 进真机；70–90 调参；<70 拆页/换块 | `plan.metrics.score` | 候选筛选 |

判定顺序固定：**硬门禁 → 趋势 → 质量 → 参考**。后层不能抵消前层：`fits=3 / overlaps=0` 只证明"块在页内且不重叠"，不证明连线成功、风格通过、电气正确。

两条口径：

- 每项判据必须落到命令/字段/阈值；写不出来的判据不算判据，只是感觉。
- 单一指标不构成验收。fits 通过就宣布完成，是 2026-10-29 第六轮之前的典型误判。

## 2. 离线与在线分层

EDA 是慢资源：单窗口、单写者、会卡死；离线是快资源：可枚举、可并行。**能离线判的判决不上真机。**

| 层 | 做什么 | 工具 | 单次成本 | 可并行 | 预算 |
|---|---|---|---|---|---|
| 离线规划 | 单方案排布 / 组合枚举 | `easycirq/scripts/sch_layout_plan.py`、`sch_layout_batch.py` | 毫秒–秒 | 是 | 实测 `--sizes 2,3` 共 220 组合、210 pass |
| 离线评分 | 质量分、zone_slack、标题净空 | `plan.metrics.score` | 毫秒 | 是 | — |
| 离线风格 | 风格审计、与参考图粗比 | `sch_style_audit.py`、`sch_style_visual.py` | 秒 | 是 | — |
| 真机落点 | 打开→清空→落块→量 bbox→校正→重建 zone→导出 | `tools/sch_layout_apply.py` | 分钟级/工程；可能 15 min 超时 | 否（单窗口单写者） | 每工程 1 次，候选 1–3 个 |
| 汇总 | scoreboard | `tools/metrics_scoreboard.py` | 毫秒 | 是 | — |

执行规则：

1. 先离线枚举出"值得上机"的候选集（batch 排序，取 top 1–3）。
2. 真机只做验证，**不在真机上试参数**。在真机里改 gap/zonePad 属于烧预算。
3. 离线通过 ≠ 验收通过；测试/mock 的结论必须标 simulated，不能写"已通过"。
4. EDA 同一时间只允许一个写者；两个 Agent 抢窗口时，后者的失败会被误判成工具 bug。
5. 离线 blocked / `score < 70` 不要带病上机；先拆页、换块或换页面。

## 3. 先测量，后落点

**坐标不能来自猜测。** 所有落点、分区、判据必须来自"实测包络"与"实测 bbox"。

### 3.1 包络的定义与来源

- 包络 = 块在页面上**渲染后的完整可见边界**：符号本体 + 引脚文字 + 位号/值 + 网络标签 + 短桩线/flag + 标题标记，取并集 bbox。
- 单位是 raw（0.01 inch）：A4 横向页面 1170×825，不要自行换算成 mm 再猜。
- 唯一合法来源：空页落块 → `schematic.components.list --payload '{"includeBBox":true}'` → 对块内 designator 求并集 → 写进 `easycirq/assets/block-envelopes.json`。
- 每次测量记录：`measured_at`、EDA 版本、客户端站点、页面几何、测量命令。

| 测量对象 | 怎么测 | 记录字段 | 失效条件 |
|---|---|---|---|
| 块包络 W×H | 空页单块落位，读 `includeBBox` 并集 | `w,h`（raw） | 块的器件/附件/符号变化 |
| 页面与标题栏 | 页面属性 + 图签矩形回读 | `page{width,height,margin}`、`title_block{minX,minY,maxX,maxY}` | 换图幅/模板 |
| 落位后实测 bbox | 落块后读同块 designator 并集 | `actual[minX,minY,maxX,maxY]` | 每次落位都要重读，不能复用 |
| 附件（stub/flag）范围 | 包络已含；单看器件 bbox 会漏 | 与器件 bbox 的差值 | 换网络标签风格 |

### 3.2 为什么要实测（三条证据）

1. `block-apply --dry-run` 的"块估算"不可靠：WROOM dry-run 报 460×100，真实落位 bbox 是 245×420（模组本体高 420，高度差 4.2 倍）。
2. 同一晚两轮测量也不一致（ES8311 第一轮 560×340，最终资产表 521×309）。包络是**有版本的资产**，以 `block-envelopes.json` 的 `measured_at` 为准，不引用聊天记录里的旧数。
3. 落位锚点不等于包络左上角：`block-apply --at` 按锚点解释，包络会落在锚点上方/右下且各块偏移不同，必须落位后实测再 `group-move` 校正（见 [failure-taxonomy](failure-taxonomy.md) FT-05）。

### 3.3 落点前检查清单

- [ ] 每个块在 `block-envelopes.json` 有实测条目；没有 → planner 直接 blocked，不要手填。
- [ ] `page` 与 `titleBlock` 来自当前页面/模板，不是沿用上一版。
- [ ] 计划里的 bbox 是整数 raw；与页边距/图签没有交集。
- [ ] 候选方案已经过离线 planner（`fits`/`overlaps`/`title_clearance_violations` 已读数）。
- [ ] 页面是空的（`components.list` 零件数 = 0）；残留页面会制造重复块。
- [ ] 记录 `windowId`（由 `project info` 现场取，不硬编码）。

## 4. 单变量实验闭环

已经有判据和数据后，调参一次只动一个变量；否则失败无法归因。

```text
假设 → 只改一个变量 → 离线重排/评分 → 选 top 候选上机 → 量 bbox/指标
     → 与上一轮对比 → 记录 → 继续 或 停止
```

允许的单变量集合（其余全部冻结）：

| 变量 | 例子 | 观察指标 |
|---|---|---|
| `gap` | 40 → 80 | block overlaps、能放下的块数 |
| `zonePad` | 16 | zone 是否包含块、zone_slack |
| `titleGap` | 36 | 标题净空违规数 |
| 块顺序/组合 | 高度降序 vs 面积降序 | fits、area_usage |
| 页面/图幅 | 单页 vs 拆页 | score、可读性 |
| 包络来源 | dry-run 估算 vs 实测 | fits 稳定性（这是数据层修正，不是审美调参） |

每轮记录表（写进夜间日志或报告）：

| 轮 | 变量 | 值 | fits | overlaps | score | 失败签名 | 结论 |
|---|---|---|---|---|---|---|---|

表头固定，每轮填当轮 `.report.json`/plan 的实测数字；不允许凭记忆回填。

### 4.1 什么时候停

| 停止条件 | 阈值 | 动作 |
|---|---|---|
| 分数平台期 | 连续 3 轮 `Δscore < 1` 且 fits/overlaps 不变 | 停止调参，接受当前方案或改结构（拆页/换块） |
| 同一失败签名 | 连续 2 次出现 → 停原样重试；第 3 次必须是不同路径或 `BLOCKED` | 按 [failure-taxonomy](failure-taxonomy.md) 归类，换工具路径或固化守卫；沿用仓库"失败预算"规则（[tool-gotchas](../../easycirq/references/tool-gotchas.md)） |
| 真机预算 | 每工程 1 次验收；同工程第 3 次仍 blocked | 记录 `NOT RUN` 与复现条件，不带病宣布完成 |
| 单命令 | 15 min 无返回（daemon 卡死高发） | 停 daemon → 重启 → 记录事件，不无限重试 |
| 用户停止 | — | 立即停，保留现场与未完成项 |

禁止：一次改两个参数、改完不记录、只看分数不看失败签名、为了分数把块挤到不可读。

## 5. 棘轮规则：失败 → 分类 → 自动检查 → 工具守卫

同一类失败不允许"手工修第二次"。每次失败必须向上走一层：

| 步 | 产物 | 放哪 | 完成判据 |
|---|---|---|---|
| 1 现象 | 原始输出/截图/指标（L0 证据） | 夜间输出目录 / `docs/evidence/<topic>-<date>/` | 有命令、时间、工程/页、退出码 |
| 2 归类 | 稳定 ID（FX/FT/FG/FD/FP） | [failure-taxonomy.md](failure-taxonomy.md) | 症状能一句话复述，且有检测方法 |
| 3 自动检查 | 命令字段/regex/单元测试 | `tests/`、脚本输出、report 字段 | 机器能判 PASS/FAIL，不靠肉眼 |
| 4 工具守卫 | 前置校验、默认值、拒绝执行 | `easycirq/scripts/`、`tools/` | 失败时工具自己挡住，不靠人记得 |
| 5 删除手工步骤 | 协议/文档更新 | pipeline、SKILL、本文 | 手工步骤从流程里消失 |

今晚已经落到工具守卫的棘轮（缺测试的条目在 taxonomy 里标 ⚠️，不冒充 ✅）：

| 失败 | 分类 | 自动检查/守卫 | 现在在哪 |
|---|---|---|---|
| `sch clear` 返回 ok 但页面没清空 | FT-01 | 落块前 `components.list` 零件数必须 = 0，否则中止 | `tools/sch_layout_apply.py` clear 分支 |
| windowId 会变 | FX-02 | `project info` 现场取 live windowId | `sch_layout_apply.py` 打开工程前 |
| 落块 `--json` 卡分钟级 | FT-02 | 不用 `--json`，用落块前后 designator 差集 | `sch_layout_apply.py` 落块循环 |
| zone 浮点坐标被 frame apply 拒绝 | FT-03 | zone 坐标全部 `int()` | planner + apply 重建 zone |
| 分区框互相重叠被拒 | FG-02 | 最近邻中点封顶 + 安全裁剪 | planner caps/trim、apply 重建时再裁 |
| 没有实测包络 | FD-01 | planner 缺包络直接 blocked | `sch_layout_plan.py` plan() 入参校验 |

判定"修完"的标准：**有一处代码在失败时自动挡住 + 有一个测试或字段能证明它挡住了 + 手工步骤已删除。** 只写进文档 = 没修完，标欠账。

## 6. 每个 magic number 一条决策记录

常数不是凭空来的；必须写清"值 + 单位 + 来源 + 有效条件 + 重测触发"。禁止裸数字散落在代码/聊天里。

| 参数 | 值 | 单位 | 来源 | 有效条件 | 重测/失效触发 |
|---|---|---|---|---|---|
| 页面 | 1170×825 | raw | `block-envelopes.json` page；A4 横向实测 | EasyEDA Pro 4.1.78 / easyeda.com | 换图幅或客户端 |
| 标题栏 | (610,12)–(1170,380) | raw | 同上（默认图签） | 当前模板 | 换模板 |
| 内容边距 `margin` | 12 | raw | planner 默认 + apply clamp 边界 12..1158 / 813 | 当前模板 | 改页边距 |
| `gap` | 80 | raw | 夜间 05:00–06:20 实测：块重叠多来自附件（stub/flag）而非器件本体，加大间距比微调原点有效 | 单页 ≤3 块、2026-10-29 包络表 | 块数/附件变化；halo 建模后重定 |
| `gap` 下限 | `max(40, titleGap+6)` = 42 | raw | `sch_layout_plan.py`：只保证堆叠时上方 zone 标题有净空，不是视觉间距 | 同上 | 改 titleGap |
| `zonePad` | 16 | raw | planner/apply 分区框内边距 | 20 pt 标题、当前风格 token | 风格规范改 2 mm 时复核 |
| `titleGap` | 36 | raw | planner 默认；apply 重建 zone 用 `y2 + 16 + 36` | 20 pt 分区标题 | 字号/字体变化 |
| zone 标题偏移/字号/色 | 8 / 20 / `#AA00AA` | raw / pt / hex | `easycirq-sch-layout/v1` frames | 当前风格 token | style token 变更 |
| 评分权重 | 重叠 −25/对、未落块 −30/个、`abs(usage−0.45)×40`、slack>0.25 再 −60×超出、标题违规 −8/处 | 分 | `sch_layout_plan.py` metrics.score | 与流水线 §5 同步 | 调权重必须同时改 pipeline 文档 |
| 进机阈值 | ≥90 直接验收；70–90 调参；<70 拆页 | 分 | [pipeline](../../easycirq/references/schematic-layout-pipeline.md) §5 | 同上 | 权重变化时重标定 |
| group-move 阈值 | 8 | raw | apply：`abs(dx)>8 或 abs(dy)>8` 才校正 | daemon 落位偏移通常 <8 | 换客户端/大页 |
| 校正/回读等待 | 3 / 7 / 5 / 4 | s | apply 的 sleep（落块后、bbox 前、group-move 后、zone 后） | 本机 EDA 响应 | 慢机器/大页 |

记录方式：

- 本文表格是**索引**；每条决策按 [决策记录模板](../../easycirq/assets/decisions/decision-record.template.md) 补"备选/代价/重评触发"，写进工程 `engineering-notes.md` 或 `docs/method/` 的决策记录。
- 代码里引用参数时在注释写决策 ID 或本文条目名，方便反向查找。
- 决策被推翻时标 `superseded`，保留旧条目和推翻原因，不直接改数字。

## 7. 反模式表（今晚真实踩过）

| # | 反模式 | 症状 | 代价 | 正确做法 | 现有守卫 |
|---|---|---|---|---|---|
| 1 | 先落块再量尺寸 | 器件顶出图纸、压标题栏 | 整轮返工 | 先量包络再排 | planner 缺包络 blocked（FD-01） |
| 2 | 把 dry-run 估算当包络 | WROOM 460×100 vs 实测 245×420 | 分区/落点全错 | 空页落块读 bbox | 资产表 + planner 校验 |
| 3 | 在残留页面上叠加 | 重复 J1/J2、残留 R5–R8、重复块 | 图不可用 | `sch clear` 后校验零件数=0 | apply clear 分支（FT-01） |
| 4 | 硬编码 windowId | `project open failed: window ... not connected` | 每工程都失败 | `project info` 取 live windowId | apply 已改为动态（FX-02） |
| 5 | 落块 `--json` | 单次卡分钟级 | 夜间流程停摆 | designator 差集识别新器件 | apply 不带 `--json`（FT-02） |
| 6 | zone 用浮点坐标 | `width: got 419.7, expected 419.66408` | frame apply 全失败 | 坐标取整 | planner/apply `int()`（FT-03） |
| 7 | 先画 frame 再落块 | 旧 frame 标题残留、分区与块错位 | 反复返工 | 先落块量 bbox，再一次性重建 zone | 流程第 7 步（FP-02） |
| 8 | 用 `(x,y,w,h)` 判块重叠 | 实测 bbox 不相交却报 review | 误判阻塞 | 只对同构 bbox 求交 | apply/planner 用 bbox 列表（FG-05） |
| 9 | 分区边不封顶 | 相邻 zone 重叠，`frame apply` 拒收 | 分区失败 | 最近邻块中点封顶 | planner caps/trim（FG-02） |
| 10 | trim 按固定轴切 | 上下堆叠时 `minX > maxX` | 分区坐标非法 | 选重叠较小的轴 | planner 按 ox/oy 比较（FG-04） |
| 11 | 一次改多个参数 | 失败无法归因 | 反复试错 | 单变量 + 每轮记录 | 本文 §4 |
| 12 | 只看 fits 宣布完成 | 连线/风格/标题未验 | 交付后被退回 | 判据分层 + scoreboard | 本文 §1 + scoreboard |
| 13 | daemon 卡住就手动 kill 重来 | 每次同类故障都靠人 | 不可复用 | 分类→重试→守卫/协议 | FX-01 部分自动化，仍是欠账 |
| 14 | 把某工程坐标当模板 | 换工程越界 | 直接失败 | 实测页面/几何 | 页面/标题栏进资产表 |

## 8. 下一轮 checklist（0–12 步）

```bash
# 0) 一次只一个 EDA 写者；确认连接
easycirq doctor

# 1) 离线：批量选候选（秒级）
python easycirq/scripts/sch_layout_batch.py --sizes 2,3 --top 10 --out batch.json

# 2) 单工程规划（缺包络会 blocked）
python easycirq/scripts/sch_layout_plan.py spec.json \
  --envelopes easycirq/assets/block-envelopes.json --out plan.json

# 3) 真机：project info 取 live windowId → 打开工程/页 → 等 reads 稳定
# 4) sch clear 后校验 components.list 零件数=0，否则中止
# 5) 逐块 block-apply（不带 --json），量实测 bbox，group-move 校正 + margin clamp
# 6) 按实测 bbox 重建 zone（整数、titleGap 36、最近邻中点封顶），一次性 frame apply
# 7) layout-lint → export-image PNG
# 8) 写 <name>.report.json：fits/overlaps/zones_reapplied/export/wires
# 9) 汇总
python tools/metrics_scoreboard.py --reports <dir> --out scoreboard.json
# 10) 失败 → failure-taxonomy 归类 → 新增检查/守卫
# 11) 更新夜间日志与决策记录（L5/L6）
# 12) 记录 NOT RUN 与剩余风险，不把计划写成已完成
```

## 9. 相关文档

- [布局流水线（离线优先）](../../easycirq/references/schematic-layout-pipeline.md) — 工具协议与阈值
- [原理图排版与看图验收](../../easycirq/references/schematic-layout.md) — 图面表达与验收规则
- [风格规范](../../easycirq/references/schematic-style.md) — 模板/分区/字号/标题栏
- [EDA 工具动作陷阱](../../easycirq/references/tool-gotchas.md) — 命令级陷阱与失败预算
- [失败分类目录](failure-taxonomy.md) — 本文引用的 FX/FT/FG/FD/FP 条目
- [知识沉淀协议](sedimentation-protocol.md) — L0–L6 分层与 DoD
- [夜间训练日志 2026-10-29](../nightly-training/2026-10-29.md) — 原始过程与实测数字
