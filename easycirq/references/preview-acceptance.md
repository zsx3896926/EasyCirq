# 原理图预览 · 图面验收

> 本文是**产品文档**，说明"离线预览图在交付前必须过哪些判据、怎么复现、缺证据时怎么办"。
> 与 `references/schematic-layout.md`（图面表达规则）互补：那份讲"怎么画好"，
> 这份讲"**怎么证明它够好**"。

## 为什么需要一条验收链

一张图"看起来还行"和"能交付"是两件事。判据能证明的只有**已知缺陷类型不成立**，
它不证明图漂亮，也不证明电气正确。

所以本链的目标是：**把"我觉得画完了"变成"有证据说明哪些项已测、哪些没测"**。

## 四种结论，必须分清

| 结论 | 含义 | 该做什么 |
|---|---|---|
| **PASS** | 已测且无缺陷 | 无 |
| **FAIL** | 已测且有缺陷 | 修，或明确接受 |
| **NOT RUN** | 有对象、缺证据 | 按给出的命令补证据 |
| **N/A** | **没有对象可测** | 无需处理，但必须写明理由 |

> `NOT RUN` 和 `N/A` 混为一谈，会让人既判断不了进度也判断不了成本。
> 例：本图不使用端口标签 → "标签落在真实端点"是 N/A，不是缺证据。

## 判据清单

| 判据 | 工具 | 依赖 |
|---|---|---|
| 内容不越框 | `sch_layout_check.py --strict` | 器件/导线/模块框几何 |
| 导线不穿器件本体 | 同上 | 同上 + 位号预留区（`textBboxes`）|
| 模块框不切器件/导线 | 同上 | 模块框矩形 |
| 遮字 / 文字相压 | 同上 | **实测文字框** |
| 重复网名 / 孤立文字 | 同上 | 实测文字框 |
| 分区阅读顺序 | 同上 | 分区标题 |
| 文字互压（独立一项） | `sch_text_audit.py --strict` | 实测文字框 + 覆盖声明 |
| 标签落在真实端点 | 同上 | netport/netlabel 图元；本图无 → N/A |
| 不同网络导线交叉无结点 | 同上 | **宿主** junction 报告；离线 → NOT RUN |
| 图签无重复文字 | 同上 | titleBlock 数据；排版稿不含 → N/A |

## 当前状态：看 `sch_preview_status.py` 的输出，不看手写总结

```bash
python scripts/sch_preview_status.py --work reports/hard-board/board2
```

它把**目标点名的每条判据**逐模块列出来，并附上**直接跑**技能检查器的结果
（不经本仓封装）。产物早于排版稿的模块会被标 🕒 并按 NOT RUN 处理 ——
手写状态会过期，这个不会。

## 什么时候必须现场：两条命令只能 NOT RUN

| 命令 | 依赖 | 离线能跑吗 |
|---|---|---|
| `easycirq sch gate` | 前台 EasyEDA 窗口（`drc` 是最后一步且需要前台）| N |
| `easycirq sch layout-score` | daemon + 活页（五维可读性打分，自带可执行修复建议）| N |
| `easycirq sch layout-render --from <zones>` | 纯文件 | Y |
| 本仓 `sch_preview_accept.py` 整链 | 纯文件 + 上述离线命令 | Y |

离线跑 `sch layout-score` 会直接报：

```
no easycirq-agent daemon found on 127.0.0.1:23111-23120 (start it with `easycirq daemon start`)
```

**没有对象可测就写 NOT RUN，不要拿"我跑过验收"暗示覆盖了这两条。**

## 审图 PNG 的五类缺陷判据

PNG 是交付物本身，所以它有自己的门（`sch_layout_review.py --gate`），
与 SVG 侧判据**并行**存在、互不替代。

| # | 判据 | 判据来源 | 现状 |
|---|---|---|---|
| 1 | 文字相压（含 **4 px 最小间距**）| 放大看图发现 `GNDL5` 粘连 | 0 |
| 2 | 导线穿过文字 | 放大看图发现 `+5V`/`GND` 被线穿过 | 0 |
| 3 | 图形符号贴文字（间距 < 2 px）| 放大看图发现网标符号压住网名 | 0 |
| 4 | 位号落在自己本体内（**只查位号**，引脚名不算）| 目检怀疑 → 数据推翻 | 0 |
| 5 | 器件压叠 / 导线穿器件本体 | 原有 | 0 |

**第 1—3 条都是"放大看图"发现的**：自动判据当时一条都没覆盖。

### 判据要界定适用域

第 4 条第一版把**引脚名**也算进去，一次报出 5/9/10 处假缺陷 ——
引脚名本来就画在符号内部（`PG`/`FB`/`VOUT`/`EN`…），那是标准画法。
收窄成"只查位号"后归零。

同理第 1 条的 4 px：只判"相交"会放过"贴边"，那样读起来是 `GNDL5`。

### 验收里必须**分类统计**

`K_png_readability` 曾经只解析 `文字相压 (\d+) 处`，
于是缺陷属于另外四类时计数显示 **0**，而门其实是 fail —— 数字与结论打架。
现在五类都解析，`detail` 写成 `各类缺陷：overlap=0, wire_text=0, ...`。

复现：

```
python scripts/sch_layout_review.py --composition composition-M3-placed.json \
    --page-name "P3_5V转3V3主逻辑轨" --out-dir reports/hard-board/board2/review --gate
```

## 判据清单（12 条，其中 2 条来自技能本身）

| # | 判据 | 来源 |
|---|---|---|
| 1 | 内容不越框 | 技能 `sch_layout_check --strict` |
| 2 | 导线不穿器件本体 | 技能 |
| 3 | 模块框不切器件/导线 | 技能 |
| 4 | 遮字/文字相压 | 技能 |
| 5 | 标签落在真实端点、朝向一致 | 技能（本设计 N/A）|
| 6 | 网标朝向一致 | 技能 |
| 7 | 重复网名/孤立文字 | 技能 |
| 8 | 不同网络导线交叉无结点 | 需现场结点证据（NOT RUN）|
| 9 | 图签无重复文字 | 本仓补 |
| 10 | 分区阅读顺序 | 本仓补 |
| 11 | **文字审计（技能自检）** | 技能 `sch_text_audit --strict` |
| 12 | 审图 PNG 可读性 | 本仓补（五类缺陷）|

### 文字审计的输入结构（踩过）

`sch_text_audit` 要求：

```json
{"count": N, "items": [{id, bbox}], "unmeasured": [], "coverage": {"designators": true, ...}}
```

- 缺 `count` → `count must match items`
- 缺 `unmeasured` → `unmeasured array required`
- `coverage` 要覆盖 `designators/values/pin_names/net_labels/wire_names/free_text/title_block`
- **直接喂 `items` 数组**会报 `object required`

所以预览链的 `visible-*.json` 里同时带这几项，才能直接跑审计。

## 一键复现

```bash
# 1) 排版：带位号预留区求解，解不出自动回退并标注
python scripts/sch_layout_reserve.py \
    --input one-M3.json --out-dir reports/hard-board/board2

# 2) 归位（只平移，不改相对几何）
python scripts/sch_layout_normalize.py \
    --composition composition-M3.json --out composition-M3-placed.json

# 3) 出图 + 出框 + 质量判据
python scripts/sch_layout_review.py \
    --composition composition-M3-placed.json --page-name "P3_3V3主逻辑" \
    --out-dir reports/hard-board/board2/review --gate

# 4) 走完整验收链（渲染 → 实测文字 → 严格检查 → 分类结论）
python scripts/sch_preview_accept.py --work reports/hard-board/board2 --modules M3

# 6) 风格 token（图面合规）：`--frames` 必须指向**审图渲染器产出的** frames 文件
#    位置：<review 目录>/frames-<页名>.json
#    不给 --frames 才会按器件外框估算；给了但文件不存在 → **硬报错**（不给假结论）
python scripts/sch_style_check.py --work reports/hard-board/board2 \
    --frames "M3=reports/hard-board/board2/review/frames-P3_3V3主逻辑.json"

# 5) 一页纸报告
python scripts/sch_preview_report.py --work reports/hard-board/board2
```

## 文字处理的三个坑（都踩过）

1. **排版稿不带文字几何。** 自己编一组坐标会产出大量假缺陷（见过 83/115 项全假）。
   必须用 `sch layout-render` 渲染后再由 `svg_text_bbox.py` 实测。
2. **渲染器不带 `sheet` 时会自己装行**，坐标与器件不是一套 → 越页/相压全是假象。
   渲染输入必须带 `sheet.bounds`。
3. **键名大小写是契约**：`textBboxes`（小写 b）。写成 `textBBoxes` 会被严格解码器
   当未知字段**静默忽略**，于是"约束看起来加了却从没生效"。

4. **`--frames` 给错路径会得到假违规。** 检查器曾静默回退到"按器件外框估算"，
   报出面积 10.9% / 内距 0.00 mm（真实值 73.1% / 14.92 mm）。现在缺文件会硬报错；
   文档也写明 frames 的真实位置：`review/frames-<页名>.json`。

## 已知限制（如实记录，未绕过）

### 后果：两个模块不可交付，且这是**实测的**结论

| 模块 | 器件数 | 导线穿文字（实测）|
|---|---|---|
| M1 | 24 | **16 处**（`C6`、`C2`、`C1`、`D2`…）|
| M2 | 8 | **3 处**（`C12`、`L2`、`D4`）|
| M3 / M4 / M5 | 7 / 10 / 7 | **0** ✅ |

复现（任选一个模块，换成 M1 即同上表第一行）：

```
python scripts/sch_preview_zones.py composition-M1-placed.json z.json --no-label-boxes
# 用驱动内部的 widen 放大画布后渲染 probe，再由 svg_text_bbox + sch_preview_text
# 得到每段文字的实测框（框在 visible.items[].bbox，小写）
python scripts/sch_preview_label_boxes.py --zones z.json
```

**注意**：`sch_preview_text.py` 的输出里，`texts[]` 只有
`primitiveId / Content / X / Y / FontSize`，**框在 `visible.items[].bbox`**，
按 `id` 关联。早先一次"0 穿线"就是因为读错了字段（循环体从未执行）。

### 根因：位号占住的那条带，正是网标命名要用的带

实测：7–10 器件的模块可解且 0 穿线；24 件模块在"避开位号"前提下排不出。

| 措施 | 结果 |
|---|---|
| 位号挪到本体下方 | 掉出模块框（`frame_border_crosses_object`）|
| 位号顶边左右换端 | 无改善 |
| 位号画进本体内 | 可解，但与体内引脚名相撞（验收倒退）|
| 加纸 A2→A0 | 无效，说明不是容量 |

### 预留区三种施加方式，实测都不收敛

| 方式 | 做法 | 结果 |
|---|---|---|
| 全量 | 每个器件都加预留区 | M3/M4/M5 秒解且 0 穿线；**M1/M2 在 100 万候选上限内排不出** |
| 几何目标化 | 先不加解一遍，只给"导线穿位号 / 位号压别人本体"的器件加 | 几何上收敛，但门还查"网标文字撞位号"，判据少一条 → 门拒绝 |
| 门驱动目标化 | 解析门的报错点名器件，逐个加 | M2 加 1 个就排不出；M1 加到第 4 个排不出（C6→C2→C1→D2 逐个暴露）|

> 三次的共同结论：**每加一个预留区，命名搜索就少一条合法引线**；
> 加到 1~4 个时求解器已经排不出。

### 求解器其实**已经**会拒绝穿文字的边

`validateLibRoutingEdge`（`sch_layout_maze.go`）对
`plSegmentTouchesBox(a, b, box)` 直接返回 `wire-text` 不许布线。
但**求解时计划里没有位号框**（`TextBBoxes` 只在渲染输入里给），
所以布线根本不知道要避让 —— 这才是结构性缺口。

要让 M1/M2 可交付，必须让**求解输入**带上位号框（或给求解器更多面积）。
这超出渲染层，属布局策略改动。

### 交付现状

| 模块 | 验收 | 说明 |
|---|---|---|
| M3 / M4 / M5 | **9 PASS / 0 FAIL / 1 N/R / 1 N/A** | 可交付 |
| M1 / M2 | 渲染被拒 | **实测有 16 / 3 处导线穿位号**，不交付 |

**正确的下一步**：位号位置在**布局阶段与网标联合决策**（方案 B），
或**增大位号与网标的可用空间**（更大的纸 + 自适应的模块框）。
两者都是结构性改动，不是补丁。

## 加一条新判据的步骤

1. 在 `sch_layout_acceptance.py` 的 `CRITERIA` 里加一条：`id` / `title` / `codes`
2. 声明依赖：`requires`（覆盖度）或 `requires_kind`（图元类型）或 `na_when_missing`
3. 若依赖新证据，在 `needs` 里写**可直接粘贴的命令**
4. 加至少一条测试：PASS 的条件、以及**缺数据不许判 PASS**
5. 同步到四个技能目录（有测试强制）

> 顺序有讲究：**适用性判定必须写在循环最前面**，否则会被更早的分支截胡（踩过）。
