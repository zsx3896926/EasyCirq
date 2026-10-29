# 失败分类目录（2026-10-29 夜间训练）

> 范围：2026-10-29 夜间训练在 EasyEDA Pro 4.1.78（easyeda.com）+ easycirq 执行层上实际出现的失败；只收**影响原理图布局流水线**的条目。
> 命令级通用陷阱（前台要求、连接器超时、JSON 混行等）仍以 [EDA 工具动作陷阱](../../easycirq/references/tool-gotchas.md) 为准；本文是布局流程的**现场失败账本**。
> 用法：新失败先查表 → 命中则追加复现证据；未命中新建 ID → 按 [棘轮规则](schematic-layout-thinking.md#5-棘轮规则失败--分类--自动检查--工具守卫) 固化。
> 沉淀方式见 [知识沉淀协议](sedimentation-protocol.md)。

## 0. 编号、状态与总则

| 前缀 | 类别 | 含义 | 条目 |
|---|---|---|---|
| FX | 环境/宿主 | daemon、window、连接器、frame 应用状态 | FX-01 … FX-03 |
| FT | 命令语义 | CLI 返回与实际结果不一致、参数语义陷阱 | FT-01 … FT-07 |
| FG | 几何 | 包络/bbox/分区/标题的几何错误 | FG-01 … FG-06 |
| FD | 数据/资产 | 包络表、parts、站点数据的错误或过期 | FD-01 … FD-03 |
| FP | 流程/方法 | 顺序、验收、处置方式导致的问题 | FP-01 … FP-08 |

状态标记：

| 标记 | 含义 |
|---|---|
| ✅ | 工具/测试自动挡住，失败可机判 |
| ⚠️ | 工具自动检测/挡住，但缺测试，或只覆盖部分场景 |
| 📝 | 只有文档/协议，靠人执行 |
| ❌ | 欠账：目前没有自动检测或守卫 |
| 🟡 | 修复进行中（未合并/未验证） |

总则：

1. **检测必须是命令/字段/regex。** 写不出检测方法的条目只能算观察记录，不能算已分类。
2. **自动化状态要诚实。** 文档写了但工具没挡 = 没修完；真机专属守卫没有单测 = ⚠️ 不是 ✅。
3. **ID 稳定。** 后续同类失败追加"复现"证据，不重新编号；根因变化时新建条目并在旧条目链接。

## 1. 环境/宿主类（FX）

| ID | 症状 | 根因 | 检测 | 修复/守卫 | 状态 |
|---|---|---|---|---|---|
| FX-01 | 连续写入后单个 CLI 调用挂到 15 min；文本含 `write/document transition is being verified` 且状态不释放 | daemon 的写/文档过渡校验未结束就继续排队，后续动作等同一个锁 | 单次调用超时且输出含 `document transition is being verified` | 工具内命中该文本重试（sleep 8s ×6）；夜间协议：`easycirq daemon stop` → 重启（connector 自动重连、doctor 恢复 ok）后继续 | ⚠️ |
| FX-02 | daemon 重启/连接器重连后 `project open failed: window ... is not connected` | windowId 会变；spec/脚本里的 `--window` 是旧值 | 对照 `project info` 的 `windowId` 与硬编码值；错误文本含 `is not connected` | `tools/sch_layout_apply.py` 打开工程前用 `project info` 取 live windowId（兼容 `context.windowId`） | ⚠️ |
| FX-03 | `sch frame apply` 一次返回失败/未 applied，稍后再试却 `verified:true, applied:N` | 写入过渡期 guard 未就绪；frame apply 需要等页面/daemon 稳定 | 首次返回非 0 且未带 `applied`；重试后出现 `verified:true` | apply 用统一 `cli()` 重试 + 调用后 sleep；夜间记录"重试 + sleep 后成功" | ⚠️ |

### FX-01 详解：daemon 写过渡卡死

- **现象**：2026-10-29 05:00–06:20，连续写入若干轮后，单条 CLI 调用挂到 15 min 超时；页面没有响应，但 daemon 进程还在。
- **根因边界**：能确认的只是"写/文档过渡校验状态不释放导致排队"；不要写成"连接器队列被永不结束的动作独占"（该机制未经证实，[tool-gotchas §23](../../easycirq/references/tool-gotchas.md) 有同类边界说明）。
- **处理阶梯**：先分类（`no EasyEDA connector is available` = 没连上，等待/刷新无用）→ 命中 `document transition is being verified` 才按写过渡卡死处理 → `daemon stop` → 重启 → 等 connector 自动重连、`doctor` 恢复 ok → 重新回读现场再继续，**不复用卡死前的批次**。
- **剩余风险**：daemon 重启仍是手工协议，没有自动恢复；工具只重试 6 次，超时后不会自己重启 daemon，也无测试。

### FX-02 详解：windowId churn

- **现象**：daemon 重启或连接器重连后，hardcode 的 `--window` 失效，`project open failed: window ... is not connected`；B/C 工程曾因此整体失败。
- **正确处理**：每次运行先从 `project info` 取 live `windowId`；spec 里的 `window` 只作注释/回退，不作为可信输入。
- **剩余风险**：live-only 逻辑，无单测；多窗口时 `project info` 可能只给活动窗口，仍需 `--project`/`--doc` 路由（见 tool-gotchas）。

### FX-03 详解：frame apply 的就绪窗口

- **现象**：zone 数据正确、坐标已取整，`sch frame apply` 首次仍可能失败；等几秒重试后 `verified:true, applied:N`。
- **处理**：按"调用 → 读回执 → 未 applied 则等待重试一次"处理；不要因为一次失败就重画 zone。
- **剩余风险**：等待时间（4 s）是本机经验值，慢机器/大页可能需要更久；未做成"读 verified 字段再重试"的严格逻辑。

## 2. 命令语义类（FT）

| ID | 症状 | 根因 | 检测 | 修复/守卫 | 状态 |
|---|---|---|---|---|---|
| FT-01 | `sch clear` 返回 ok，但页面仍有 12 个 part；随后落块在残留上叠加 | clear 的"成功"只表示命令收下，不保证页面空；未知 flag/状态可能静默 no-op | clear 后 `schematic.components.list` 的 `componentType=="part"` 数 > 0 | apply 循环 clear 至多 10 次，校验 `code==0 且 parts==0`，否则写 `blocked` 报告并中止（不落块） | ⚠️ |
| FT-02 | `sch block-apply --json` 卡分钟级不返回 | 真实落块 + JSON 汇总的开销不可控 | 命令无返回超过 120 s | 不传 `--json`；用落块前后 designator 差集识别新器件 | ⚠️ |
| FT-03 | frame 回读浮点误差：`width: got 419.7, expected 419.66408`，`frame apply` 直接失败 | zone 坐标带小数，回读校验用精确比较 | 错误文本 `got ... expected ...`；zone 坐标非整数 | planner 与 apply 的 zone 坐标全部取整（`int()`/`int(round())`） | ⚠️ |
| FT-04 | 按块名找不到 provenance group，`group-move` 不动块；或只动器件不带桩线/netflag | `sch group list` 的组名是 `<short-id>(<instance>)/<net>`（无 `block.` 前缀）；`--json` 结构是 `{groupsByPage:{pageUuid:[...]}}`；必须 `--groups g1,g2,...` 才带附件 | 组名不匹配 `short + "("`；group-move 后 bbox 不变 | apply 用 `name.startswith(short + "(")` 解析，再 `group-move --groups` | ⚠️ |
| FT-05 | 落块后块包络落在锚点上方/右下，各块偏移不同，计划位置与实际错位 | `block-apply --at` 的锚点语义不是"包络左上角"；偏移随块/符号变化 | 落块后实测 bbox 与计划 bbox 差 > 8 raw | 落块后读实测 bbox → `group-move` 校正；planner 的 `at=x+50,y+50` 只作粗锚点 | ⚠️ |
| FT-06 | designator 差集为空（落块失败）或含旧位号（页面残留）；重复位号使并集 bbox 异常（B 工程 WROOM 宽 729） | 差集依赖"落块前页面干净"；残留/重复位号会污染差集与 bbox 并集 | 差集大小与预期不符；bbox 与包络表差 >2 倍 | clear 校验后落块；差集 + 实测 bbox；不用 `--json` 判定成功 | ⚠️ |
| FT-07 | 块自动连线每组仍有 1–7 个引脚失败（PARTIAL）；第一轮没有任何量化记录 | autoconnect 只保证"选中方向/部分成功"，不保证每脚连通 | 输出 `PARTIAL: x succeeded, y failed`；`wires.failed>0` | apply 解析 `new/PARTIAL` 写入 `wires{total,ok,failed}`；scoreboard 汇总速率 | ⚠️ |

### FT-01 详解：clear 返回 ok 但页面没清空

- **现象**：2026-10-29 06:20–08:30，`sch clear` 返回 ok，`components.list` 仍报 12 个 part；若继续落块就会得到重复/叠加页面。仓库既有案例（[tool-gotchas §24](../../easycirq/references/tool-gotchas.md)）还记录了 `sch clear --json` 的未知 flag 被静默忽略、清除根本没发生。
- **检测**：clear 之后独立读 `schematic.components.list`，数 `componentType=="part"`；>0 即失败。
- **守卫**：`tools/sch_layout_apply.py` 的 clear 分支：最多 10 次，每次 sleep 5 s 后回读；`code==0 and not comps` 才算清空；否则写 `error: clear did not empty the page; refusing to place blocks on top of stale parts` 并**中止**（不落块、不导出）。
- **剩余风险**：无单测（真机专属）；若 10 次都失败，工具中止但不会尝试 `doc reload`/重启 daemon。

### FT-02 详解：`block-apply --json` 卡死

- **现象**：真实落块加 `--json` 可能长时间不返回（分钟级），把夜间流程拖停。
- **处置**：落块命令不带 `--json`；用"落块前 designator 集合 → 落块后集合"的差集识别新器件，再量 bbox。
- **边界**：差集不是 100% 可靠（见 FT-06）；但它比等 JSON 可靠，且失败可被 bbox 校验发现。
- **剩余风险**：若落块实际失败，差集为空，工具会跳过校正并继续——依赖后续 fits/overlaps 指标暴露问题。

### FT-03 详解：frame 回读浮点误差

- **现象**：zone 坐标带小数时，`frame apply` 的宽度回读校验失败：`width: got 419.7, expected 419.66408`。这不是"误差容忍"问题，是工具直接拒收。
- **处理**：所有进入 frame apply 的坐标取整；planner 的 `zonePad/titleGap` 先 `int()`，apply 重建 zone 用 `int(round(...))`。
- **边界**：取整会带来 ≤0.5 raw 的视觉偏差，可接受；不要为了"精确"传浮点。
- **剩余风险**：planner 输出 `at` 仍是字符串 `"x,y"`（整数），但若外部 spec 手填浮点仍可能触发；工具没有对输入 spec 做整数校验。

### FT-04 详解：provenance group 命名

- **现象**：`sch group list` 里块实例组名是 `<block-short-id>(<instance>)/<net>`，例如 `es8311_codec_i2s(1)/...`，不带 `block.` 前缀；用完整 id 或 guessed 名字找不到组，`group-move` 不动块。
- **必须用 `--groups`**：只移动器件本体不足以带动桩线和 netflag，必须按 provenance 组移动。
- **处理**：apply 取 `short = id.split(".",1)[-1]`，匹配 `name.startswith(short + "(")`，`--groups` 传入所有匹配组。
- **剩余风险**：解析基于名字前缀，同名/多实例时可能误匹配；组列表为空时会回退 `--group blk-%02d`，该名字未必是真实组，校正可能静默失败（欠账）。

### FT-05 详解：`--at` 是锚点不是左上角

- **现象**：2026-10-29 08:30–09:00，块落位后包络落在锚点上方/右下，不同块偏移不同；计划 bbox 与实际 bbox 错位，必须实测后校正。
- **处理**：planner 只给粗锚点（`x+50, y+50`）；apply 落块后读实测 bbox，`dx/dy > 8 raw` 时 `group-move` 到计划 bbox。
- **边界**：`8 raw` 是本机经验阈值；小于它的偏移视为可接受，避免为 1–2 raw 反复移动。
- **剩余风险**：移动后未重新量 bbox 之外的附件范围；若移动带动 netflag，zone 重建使用的是移动后 bbox（正确），但线/标签是否随组移动取决于 provenance 组完整性。

### FT-06 详解：designator 差集陷阱

- **现象**：B 工程 WROOM 落位后 bbox 宽 729（正常 245），microSD/BMI 被挤掉；怀疑页面残留或差集把旧器件算进新块。
- **为什么不可靠**：差集假设"落块前页面干净、位号唯一"；一旦有残留（J1/J2 重复、R5–R8）、或某块位号与旧块重叠，差集会把旧器件并进新块 bbox。
- **守卫**：clear 校验（FT-01）+ 差集 + 实测 bbox 三重检查；bbox 与包络表差 >2 倍时应当报错，当前仅记录。
- **剩余风险**：B 工程的 729 异常**未定位**（FP-07），差集结果没有字段级校验。

### FT-07 详解：autoconnect PARTIAL 未收敛

- **现象**：第一轮"块自动连线部分失败后没有量化记录"（每组 1–7 脚）；后续 apply 解析 `connection(s)`/`PARTIAL: x succeeded, y failed` 写入 `wires{total,ok,failed}`，scoreboard 能看到成功率，但**没有自动重试**。
- **判据**：wire success 是趋势指标，不单独阻塞（见 [思考框架 §1](schematic-layout-thinking.md#1-动手前先定义判据)）。
- **欠账**：`sch connect` 二次重试与收敛率记录尚未实现；失败引脚仍靠下一轮人工/脚本。

## 3. 几何类（FG）

| ID | 症状 | 根因 | 检测 | 修复/守卫 | 状态 |
|---|---|---|---|---|---|
| FG-01 | 规划 overlaps=0，真机落块却互相压；某块只有更远的位置放得下（microSD 在 `660,560` 才能放，`660,600+` 皆 overlap） | 块除器件本体外还有 marker 晕圈/桩线/flag 附着；先落块的块占住晕圈；规划器只按包络与 gap 计算，halo 未建模 | 落块后实测 bbox 相交，或"只有更远位置能放下"；块间距 <80 raw | 夜间约定 `gap=80`；无自动 halo 检测 | ❌ 🟡 |
| FG-02 | 相邻分区框重叠，`sch frame apply` 直接拒收 | zone = 块包络 + `zonePad` + `titleGap`；相邻块 padding 相撞 | plan `overlaps>0`；frame apply 返回重叠拒绝 | planner 每边按最近邻块中点封顶（`±2 raw`），再做安全 trim；apply 重建时再裁一次；测试 `test_frames_do_not_overlap_each_other` | ✅ |
| FG-03 | 分区标题与相邻块网络标签同高度相压（MEMS 区标题压 ES8311 右侧标签） | 标题只保证在本块上方 `titleGap`，未对相邻块的标签/其他标题避让 | 导出 PNG 肉眼可见；plan `title_clearance_violations>0`（只算本块） | `titleGap=36` + 标题净空 metric/扣分；几何避让未做 | ⚠️ |
| FG-04 | trim 后 zone 出现 `minX > maxX` 的非法矩形 | 按固定轴（y）一刀切，上下堆叠时把 x 范围切反 | zone 矩形非法/面积为负；frame apply 拒绝 | trim 选重叠较小的轴（`ox<=oy` 切 x，否则切 y）；planner 已按此实现 | ✅ |
| FG-05 | 规划/报告报 overlaps>0，实测 bbox 两两却不相交 | 用 `(x,y,w,h)` 的位置去套 `[minX,minY,maxX,maxY]` bbox，语义混用 | 重算同构 bbox 交叠后不一致 | 统一用 bbox 列表求交（planner `boxes`、apply metrics） | ⚠️ |
| FG-06 | 分区框与块错位、旧 frame 标题残留 | 用计划 bbox（而非实测 bbox）重建 zone；或落块前先画 frame | 导出图错位；zones 与 report 的 actual bbox 不一致 | 流程固定：落块 → 量实测 bbox → 重建 zone → 一次性 frame apply | ⚠️ |

### FG-01 详解：块 halo / marker 晕圈

- **现象**：2026-10-29 08:30–09:00，microSD 在 `660,560` 才能放下，`660,600` 以上均 overlap；块重叠很多来自附件（stub/flag）而非器件本体。
- **有效经验**：加大块间距（`gap=80`）比反复微调原点有效；微调会让块在晕圈里"看起来没压、实际压"。
- **为什么没自动化**：规划器的 `envelope` 包含附件后的整体 bbox，但 halo 是"落块占位 + 标记晕圈"的运行时现象，静态包络不完全等价；需要把 halo 作为规划输入（🟡 进行中）。
- **当前守卫**：夜间 spec 统一 `gap=80`；planner 默认只保证 `max(40, titleGap+6)` 的标题净空下限，**不是** 80。两者含义不同，别把 42 当视觉间距。

### FG-02 详解：zone 重叠被 frame apply 拒收

- **现象**：按 `包络 + padding + titleGap` 生成的相邻 zone 互相重叠，`sch frame apply` 直接拒绝（不能带病分区）。
- **根因**：padding 与 titleGap 都是"向外扩"，相邻块间距不够时两张框必然相交。
- **修复**：planner 对每条边取 `min(自身外扩, 最近邻块边界 ∓2 raw)` 的中点封顶；仍有交叠时按较小重叠轴 trim；apply 用实测 bbox 重建时再跑一次同样的 trim。
- **为什么可自动判**：`test_frames_do_not_overlap_each_other` 直接断言两两矩形不交叠。

### FG-03 详解：标题/标签碰撞

- **现象**：第一轮"分区标题与块内网络标签打架（同一高度）"；后续 MEMS 区标题仍可能压到 ES8311 右侧网络标签（夜间日志"已知残留"）。
- **根因**：`titleY = zone.maxY - 8` 只保证标题在**本块**上方，没有把相邻块的标签/标题纳入避让。
- **现在能检测的部分**：`metrics.title_clearance_violations` 统计"标题 Y 低于本块 bbox 底 +10"的情况并扣分，但**不检测**标题压到别的块的标签。
- **欠账**：需要文字 bbox/渲染分析（style audit 或导图后视觉检查），目前靠人看导出图。

### FG-04 详解：trim 轴选错

- **现象**：第二轮"按 y 一刀切会把上下堆叠的 zone x 范围切反（minX > maxX）"。
- **修复**：比较两矩形在 x/y 方向的重叠量，选较小的轴切；planner 安全 trim 已实现该逻辑。
- **边界**：安全 trim 在正确封顶后本应是 no-op；`zones_trimmed` 计数 >0 说明封顶逻辑仍有漏网，值得回看。

### FG-05 详解：bbox 与 `(x,y,w,h)` 混用

- **现象**：块重叠判定用 `(x,y,w,h)` 去套 bbox，误报 review（实测并不重叠）。
- **修复**：所有几何比较统一成 `[minX,minY,maxX,maxY]`；planner 与 apply 的 overlaps 计算都按 bbox 列表两两求交。
- **边界**：包络表存的是 `w/h`，使用时必须先转 bbox 再比较，不能直接塞进位置判断。

### FG-06 详解：用计划 bbox 重建 zone

- **现象**：第二轮"分区框与块的包含关系必须用实测 bbox 重建：先在空页落块，量 bbox，再一次性画 frames；否则旧 frame 标题会残留、分区与块错位"。
- **处理**：apply 在全部块落位并校正后，用 `actual` bbox 重建 `*.zones.json`（整数、+16 pad、+36 title gap、越界 clamp），然后一次性 `frame apply`。
- **剩余风险**：若某块 `actual` 缺失（落块失败），该块没有 zone，指标会显示 `blocks` 少一块但不会显式失败——靠 scoreboard 的 `blocks` 对比暴露。

## 4. 数据/资产类（FD）

| ID | 症状 | 根因 | 检测 | 修复/守卫 | 状态 |
|---|---|---|---|---|---|
| FD-01 | 包络估算偏小：WROOM dry-run 报 460×100，实测 245×420；按估算排的块顶出图纸/压标题栏 | dry-run 的"块估算"低估高度（模组本体 420） | dry-run `w/h` 与实测 bbox 差 >20% | 只用实测包络表；planner 缺包络直接 blocked；pipeline 明令禁用 dry-run 估算 | ✅ |
| FD-02 | 所有块落块失败；parts 的 `deviceUuid` 在当前客户端解析不到 | `standard-parts.json` 的 deviceUuid 是 lceda.cn 站点的，当前 EasyEDA 是 easyeda.com | 落块失败；deviceUuid/库站点与当前客户端不符 | 用 `lib search`/`lib by-lcsc` 按站点解析，生成 `standard-parts.resolved.json`；**未产品化** | ❌ |
| FD-03 | 同一块同一晚两轮测量不一致（ES8311 560×340 → 521×309）；基准脚本的包络与资产表不一致 | 包络是版本化资产；测量方法/附件范围不同；脚本各自存一份旧数 | 资产表 `measured_at`/数值 vs 基准脚本 `ENVELOPES` | 单一数据源（资产表）+ `measured_at` + 重测 SOP；基准改为读资产表 | 📝 |

### FD-01 详解：dry-run 估算不可信

- **证据**：WROOM dry-run 460×100 vs 真实落位 bbox 245×420（高度差 4.2 倍）；第一轮因此器件顶出图纸、压标题栏。
- **为什么会错**：dry-run 只给粗略块尺寸估计，不包含模组本体高度/附件；不能作为规划输入。
- **守卫**：`sch_layout_plan.py` 的 `plan()` 对每个块要求 `envelope{w,h}`；缺了就查资产表；仍缺则 `ValueError` → verdict blocked。这个守卫有测试（`test_envelope_table_fills_missing_sizes`、`test_missing_envelope_is_blocked`）。

### FD-02 详解：站点 parts 不匹配

- **现象**：第一轮所有块落块失败；根因是 `standard-parts.json` 的 deviceUuid 属于 lceda.cn 站点，而当前客户端是 easyeda.com。
- **临时处理**：用 `lib search`/`lib by-lcsc` 按站点解析出 `standard-parts.resolved.json`（手工/临时脚本）。
- **欠账**：站点 parts 同步尚未做成 `easycirq parts sync`（Go 命令），解析结果没有版本化、没有测试；换机器/换站点会再次踩。

### FD-03 详解：包络的版本与单一数据源

- **现象**：ES8311 第一轮 560×340、最终资产表 521×309；`docs/nightly-training/bench_layout_planner.py` 的 `ENVELOPES` 仍是更早的估算（wroom 460×100）。这说明"包络"不能散落在脚本里。
- **规则**：包络只信 `easycirq/assets/block-envelopes.json`（带 `measured_at` 与测量说明）；其他脚本/基准读它，不各存一份。
- **检测**：对比基准脚本与资产表的数值；`measured_at` 超过 30 天或块定义变化 → 重测（SOP 见 [沉淀协议 §3](sedimentation-protocol.md#3-l1-数据资产层把量过的东西变成尺子)）。

## 5. 流程/方法类（FP）

| ID | 症状 | 根因 | 检测 | 修复/守卫 | 状态 |
|---|---|---|---|---|---|
| FP-01 | 未量尺寸就落点：器件顶出图纸、压标题栏、分区框按"看着差不多"画 | 先摆再调，坐标来自猜测 | planner 缺包络 blocked；落块前 spec 无 `envelope` | 流程改为"先量后放"；planner 硬校验 | ✅ |
| FP-02 | 旧 frame 标题残留、分区与块错位、页面出现重复块 | 先画 frame 再落块；或落块后未按实测 bbox 重建；clear 后未校验 | 导出图肉眼可见；zones 与 actual bbox 不一致；重复位号 | 固定顺序：clear 校验 → 落块 → 量 bbox → 重建 zone → 一次性 frame apply | ⚠️ |
| FP-03 | 页面残留（重复 J1/J2、R5–R8）时重放，出现重复块 | 没确认页面已清空就重放；clear 的假成功（FT-01） | 位号重复/零件数 > 预期 | clear 校验 parts=0 后重放，否则中止（FT-01 守卫） | ⚠️ |
| FP-04 | 每次卡死都手动 kill daemon、手改 window、加 sleep | 处置方式 ad hoc，没有写进工具/协议 | 处理记录里出现手工 stop/start、硬编码 window | 写进 pipeline §3 环境坑与本文 FX-01；仍无自动恢复 | 📝 |
| FP-05 | 只看 fits=3 就宣布"跑通"；连线/风格/导出未记录 | 单一指标当验收 | 报告缺 `wires`/`zones`/`export`/style 字段 | 判据分层（硬门禁/趋势/质量/参考）+ scoreboard 必填字段 | ⚠️ |
| FP-06 | 一轮里同时改 gap/zonePad/顺序，失败无法归因 | 多变量并行；没有对照记录 | 夜间日志同一轮改 ≥2 参数 | 单变量 + 每轮记录表（思考框架 §4） | 📝 |
| FP-07 | B 工程 WROOM 落位后 bbox 宽 729（正常 245），microSD/BMI 被挤掉 | **未定位**；怀疑页面残留/designator 差集误判 | 实测 bbox 与包络表差 >2 倍 | 无；下一轮单独排查 | ❌ |
| FP-08 | 关键路径只存在于夜间临时脚本（`layout_exec.py`、`standard-parts.resolved.json`） | 一次性脚本没产品化 | 换机器/换人无法重跑 | 执行器已产品化 `tools/sch_layout_apply.py`；parts 同步仍未产品化 | ⚠️ |

### FP-05 详解：单指标验收

- **现象**：第四轮 A 工程"blocks=3, fits=3, overlaps=0, zones=0, export=0"被当作跑通；但连线成功率、风格分当时都没测（第一轮还完全没量化）。
- **判据分层**（[思考框架 §1](schematic-layout-thinking.md#1-动手前先定义判据)）：fits/overlaps/zone containment 是硬门禁；wire success 是趋势；style score 是交付前质量；visual similarity 只作参考。
- **为什么仍然 ⚠️**：scoreboard 汇总了 wires，但按设计"连线成功率单独看趋势，不单独阻断"，所以 fits 全绿 + 连线 60% 的工程仍会显示 pass。报告必须同时写 `wires`，不能只引用 `verdict`。

### FP-07 详解：B 工程 WROOM bbox 异常（开放）

- **现象**：2026-10-29 08:30–09:10，B 工程 WROOM 落位后 bbox 异常宽（729，正常 245），microSD/BMI 被挤掉；其余两工程正常。
- **可疑方向**：页面残留（重复位号/R5–R8）→ designator 差集把旧器件并进 WROOM 的 bbox；或该页坐标/差集误判。
- **处理**：B 工程下一轮先 `sch clear` + 校验 parts=0，再单独落 WROOM 量 bbox；对比差值。定位前 B 不标 pass。

### FP-08 详解：临时脚本 vs 工具

- **现象**：夜间关键执行逻辑最初只在 `layout_exec.py`；站点 parts 解析结果是 `standard-parts.resolved.json`，都在仓库外/临时目录。
- **已沉淀**：执行器 → `tools/sch_layout_apply.py`（参数化 + report + guards）。
- **未沉淀**：parts 站点同步（FD-02）、B 工程排查脚本；这些仍是 FP-08 欠账。

## 6. 欠账清单（未自动化，按优先级）

| 优先级 | 条目 | 现在靠什么 | 为什么没自动 | 下一步 |
|---|---|---|---|---|
| P0 | FP-07 B 工程 bbox 729 | 下一轮单独排查 | 根因未定位 | 空页单块复现 → 对比差集/位号 |
| P0 | FG-01 block halo | `gap=80` 约定 | 规划器未建模运行时 halo | 把 halo 作为规划输入（🟡） |
| P1 | FD-02 站点 parts | 临时 `standard-parts.resolved.json` | 未做 `easycirq parts sync` | 产品化 + 版本化 + 测试 |
| P1 | FG-03 标题压相邻块标签 | 人看导出图 + 本块净空 metric | 需要文字 bbox/渲染分析 | 接入 style audit / 导图碰撞检查 |
| P1 | FT-06 差集结果校验 | 记录 bbox 但不报错 | 缺"bbox vs 包络表"阈值断言 | 加 2 倍差告警/blocked |
| P2 | FT-07 连线重试 | 只统计不重试 | 重试策略未设计 | `sch connect` 二次重试 + 收敛率 |
| P2 | FX-01 自动恢复 | 手工 daemon restart | 自动重启风险高 | 协议保持手工，工具记录事件 |
| P2 | FX-03 frame apply 等待 | 固定 sleep 4s | 无 verified 轮询 | 读 `verified/applied` 再重试 |
| P2 | FT-04 空组回退 | `--group blk-NN` 回退 | 回退名可能不存在 | 组为空时显式报错，不静默 |
| P3 | FP-06 单变量纪律 | 文档约定 | 需要流程记录 | 日志模板强制字段 |

## 7. 新增一条失败的模板

复制下面字段，编号取该类下一个空号；**检测**必须能执行：

```markdown
| ID | 症状（一句话，含可观察文本/数值） | 根因（能证实的边界；不确定写"未定位"） | 检测（命令/字段/regex/测试） | 修复/守卫（文件+函数/测试名） | 状态 |
```

填好后：

1. 在对应类别表追加一行；重要条目再加详解（现象/处理/边界/剩余风险）。
2. 按 [棘轮规则](schematic-layout-thinking.md#5-棘轮规则失败--分类--自动检查--工具守卫) 加检查/守卫；没加就标 ❌/📝，不要标 ✅。
3. 在 L4 加测试或在 L6 夜间日志记录复现证据。
4. 若涉及参数，补 L5 决策记录（来源/有效条件/重评触发）。

## 8. 相关文档

- [原理图布局思考框架](schematic-layout-thinking.md) — 判据、离在线、单变量、棘轮、magic number
- [知识沉淀协议](sedimentation-protocol.md) — L0–L6、DoD、失败沉淀 SOP
- [布局流水线](../../easycirq/references/schematic-layout-pipeline.md) — 工具协议与固定步骤
- [EDA 工具动作陷阱](../../easycirq/references/tool-gotchas.md) — 命令级通用陷阱与失败预算
- [夜间训练日志 2026-10-29](../nightly-training/2026-10-29.md) — 上述现象的时间线与原始数字
