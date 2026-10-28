# 原理图排版引擎：测量 → 模块布局 → 合页 → 写入 → 复核

本文件用于“把已有电气设计画清楚”的任务：不改拓扑、不换器件、不删网络，只重排器件、导线和标签。它描述一条已经在本机 EasyEDA 4.1.78 + 前代执行器 1.15.0 上跑通过的流水线，以及每个环节的硬门禁、证据和已知限制。

目标不是生成一张“分数高”的图，而是让同一个人能顺着主信号链读完、能定位每个连接、能继续修改。分数、截图和 DRC 都只是其中一项证据。

**执行前强制读取** [图面强制验收](schematic-layout.md#强制验收先规划缺证据不放行)。页面合并/拆分必须遵守页面预算，不能因为求解器失败自动新开页；候选质量检查后还需严格几何检查、实际导图及连接复验，缺几何覆盖时不得把候选分数作为放行依据。

## 1. 先判断任务类型

| 用户说 | 类型 | 默认动作 |
|---|---|---|
| “这张图太乱，帮我画清楚，连接不要变” | 全页重排 | 读现场 → 功能分区 → 局部求解 → 合页 → 写入 → 全量网表复核 |
| “把这一块挪一下 / 这里太挤” | 局部返工 | 冻结其他区，只重算受影响模块；不整页重排 |
| “新画一个电路” | 新建 | 先完成电气设计，再走同一条排版流水线；不要把排版当成设计 |
| “检查一下排版” | 只读 | 跑质量检查与官方 lint/score，输出问题清单，不写入 |

只有用户明确要求改图时才进入写入步骤。用户只给截图、没有工程时，只能做离线候选，并明确“该工程尚未执行”。

## 2. 流水线总览

```text
冻结现场
  → 功能模块计划（角色/核心/成员/网络策略）
  → sch_layout_model.py 构建并校验测量输入
  → sch layout-plan --zones            区内布局与连线
  → sch_sheet_fit.py                   页预算预检（先于合页）
  → sch layout-sheet-plan              合页与图签避让
  → sch layout-render + 质量检查       候选复核
  → sch_compose_input.py               测量证据 → compose 输入
  → sch_bind_component_ids.py          稳定 ID 绑定计划/复核
  → sch compose --layout-page          受保护 Apply 队列
  → sch apply --dry-run / --yes        写入
  → save → reopen → 网表 diff → gate → 导图 → 局部返工
```

职责分工：Agent 决定功能分区、阅读顺序、哪些网络直连或打标签；求解器计算坐标、避让和路径；质量检查器独立报告可读性问题；EDA 执行器只做受控写入和回读。

## 3. 冻结现场

每次重排前先保存同一时刻的完整证据。缺少任一项都不要开始写入。

```bash
zhigou doc ls --project <project>
zhigou sch sheet-geometry --project <project> --doc <page-uuid> --json
zhigou sch sheet-geometry --from-svg <page.svg> --json      # 精确内框/图签
zhigou sch list --project <project> --page <page-uuid> \
  --include-device-identity --include-bbox --include-pins \
  --include-wires --include-page-primitives > page-before.json
zhigou sch connectivity --project <project> --page <page-uuid> > connectivity-before.json
zhigou sch designator-geometry --project <project> --doc <page-uuid> --out designators-before.json
zhigou sch check --project <project> --page <page-uuid> --json > check-before.json
zhigou sch export-image --project <project> --page <page-uuid> --format svg --out before.svg
zhigou sch export-image --project <project> --page <page-uuid> --format png --out before.png
```

工程级的备份优先用 `project export --window <id> --project-uuid <uuid> --out <new.epro2>`；它不覆盖已有文件。记录 SHA-256。

**并发规则**：同一个工程副本同一时间只允许一个写入者。开工前查 `zhigou audit tail`，确认没有其他会话正在写；发现漂移立即停写，不要用 `--resume` 跳过守卫。

## 4. 功能模块计划

模块计划只描述相对关系和画法，不写绝对坐标。示例见
[温度报警模块计划](../assets/layout-modules/temperature-alarm.module-plan.json)。

```json
{
  "schemaVersion": 1,
  "defaultNetPolicies": {"+5V": "local_power", "GND": "local_ground"},
  "readingOrder": ["usb", "sensor", "vref", "comp", "driver", "indicator"],
  "zones": [
    {"id": "comp", "title": "Comparator & hysteresis", "core": "U1",
     "members": ["U1", "R13", "R14", "R15", "C3"],
     "netPolicies": {"OUT": "direct", "GATE": "module_port",
                     "NODE": "module_port", "VREF": "module_port"}}
  ]
}
```

规则：

- `members` 用位号，覆盖页内每一个器件，恰好一次。核心必须在成员内。
- 外围绕核心的引脚组织；不要把“所有电阻”单独成区。
- 分区标题 ≤ 18 个字符。标题带属于模块框的一部分，长标题会撑宽 frame，直接吃掉页预算并触发分页；标题说明放图面注释或交付文档，不要塞进 zone title。
- 先按每区 4–6 个器件切分。8 脚以上、同一电源轨并联、只有电源/地两两相连的区，求解器常无解；在模块计划阶段就拆开，而不是等 `layout-plan` 报预算耗尽。
- 同一区内的短信号默认 `direct`；跨区信号 `module_port`；电源/地 `local_power`/`local_ground`。
- 不要把跨区网络写成 `direct` 再靠标签补连接。
- 一个新的功能模板至少要在两个几何不同的真实符号/配置上验证；不能适配时明确回退，不硬塞坐标。

## 5. 构建并校验测量输入

```bash
python easycirq/scripts/sch_layout_model.py \
  --snapshot page-before.json --connectivity connectivity-before.json \
  --designators designators-before.json --sheet sheet.json \
  --module-plan plan.json --out-dir out/model
```

输出：

| 文件 | 内容 |
|---|---|
| `layout-source.json` | `sch layout-plan --zones` 的输入；器件用连接 IR 的 `cmp-*` 稳定 ID |
| `quality-input.json` | 质量检查输入（页面矩形、位号 bbox、导线、模块） |
| `model-report.json` | 覆盖、阻塞、警告、输入哈希、纸张来源、逐件引脚包络 `envelopes` |

`status=ready` 才继续。`blocked` 时逐条处理，不能把 blocker 当 warning。

`envelopes` 按位号给出 `body`（本体 bbox）、`envelope`（本体与全部引脚端点的并集）和四边 `overhang`。**打包与排页按 `envelope` 留行高和页顶余量**：连接器、排针、晶振的壳脚/固定脚常伸出本体 10–35 raw，按本体算会让这些脚没有合法的出线方向（机理与修法见第 12 节）。`layout-source.json` 仍只放官方 planner 认识的字段，不夹带这一项。

本脚本强制检查：

- 快照与连接 IR 的位号集合一致；每个器件的每个已连引脚在 IR 中有对应网。
- 空网引脚必须显式 NC 或 unconnected；NC 引脚不能有网。
- 每个器件恰好属于一个区；不存在未分配/重复成员。
- 位号文字 bbox 逐件实测；缺失只警告，但最终验收不能声称文字已验证。
- 引脚坐标在 5-raw 网格；锚点与引脚偏移不在网格时，只把锚点参考归一到最近合法网格，并同时给出 `anchor_requires_review` 阻塞。**不要静默改坐标**。
- 纸张内框与图签 keep-out 来自官方 SVG，不用纸张外框冒充内框。

## 6. 区内布局与连线

```bash
zhigou sch layout-plan --zones --from out/model/layout-source.json \
  --out out/zones-geom.json --report out/layout-report.json
```

- `spacing` 默认 10 raw（0.1 inch）。更小的值只用于确实放不下时，并在报告中记录；不要用缩小字体解决拥挤。
- `maxCandidates` 是每个区的共享搜索预算。失败报告会给出最后冲突、阻挡对象和预算状态；有限预算失败不等于全局无解。
- 失败先改源数据/归属/策略/姿态，再重算。不要手改输出坐标或伪造导线。
- `direct` 网络必须形成真实线树；`module_port` 优先直连，无法安全合并时才在边界命名。不能因为路由失败就把所有网络改成标签。
- 区内结果以核心为局部原点；不要把它当页面坐标，也不要二次平移。

## 7. 合页与图签

把 `zones-geom.json` 加上纸张证据：

```json
{
  "schemaVersion": 1,
  "spacing": 10,
  "zones": [ ... ],
  "sheet": {
    "bounds": {"minX": 0, "minY": 0, "maxX": 1170, "maxY": 825},
    "border": {"minX": 10, "minY": 10, "maxX": 1160, "maxY": 815},
    "keepouts": [{"minX": 460, "minY": 10, "maxX": 1160, "maxY": 190}],
    "padding": 10, "gap": 10, "flow": "z"
  }
}
```

```bash
# 页预算预检：只读 frame + 纸张几何，不写 EDA（exit 0 fits / 1 no-fit / 2 invalid）
python easycirq/scripts/sch_sheet_fit.py \
  --zones zones-geom.json --model-report model-report.json \
  --out-page page-packed.json --fixed mcu:20,240

# 官方合页（shelf 打包）
zhigou sch layout-sheet-plan --from render-input.json --out pages.json --flow z
```

预检规则：

- 可用区 = `innerBBox` 内缩 `max(--margin, --gap) + 0.5`（compose 的边框半单位描边），再向内取整到 5-raw 锚点网格；frame 两两间距 ≥ `--gap + 1`；图签 keep-out 外扩 `max(--keepout-clearance, --gap + 0.5)` 并向上取整到网格。
- `sch_sheet_fit.py` 用 MaxRects 多排序尝试，能利用图签旁 L 形空间；`layout-sheet-plan --flow z` 只是按行顶齐的 shelf 打包，密集页报 `needs-pagination` 不代表真的放不下。
- `fits` 时 `--out-page` 直接产出 compose 可用的 packed page（`sheetPosition` 取 frame 左上角，整数 5-raw 坐标，`sheet.flow = fixed`）；frame 宽高必须是 5 的整数倍，否则 compose 会拒绝。`--snap` 默认 5，`--out-page` 不接受非 5 倍数。`fixed` 只用于阅读顺序必须固定的核心模块。
- `no-fit` 时报告会给出最后一个失败模块、所需尺寸和剩余空矩形；先按这些数字缩框/拆区，不要盲目重试或加页。
- 预检通过后仍要跑官方 `layout-sheet-plan` 并逐框复核全局坐标；两者结论不一致时以几何复核为准，记录差异。离线 `fits` 不是 compose 接受或真机通过的替代证据。

- 小电路优先一页；不要固定三页。先调模块顺序/间距/核心选择，再考虑分页。
- `flow:z` 是确定性的从左到右、按行顶齐；它不会回填短框下的空洞。
- `flow:compact` 可能给出更少的页数，但本机 1.15.0 实测出现过**框重叠/越界**的候选；必须逐框用全局坐标复核，不能只看 `pages=1`。
- 图签是硬 keep-out；模块框、导线、标记、文字都不能侵入。
- 一页放不下时，优先调整模块内部几何、阅读顺序、间距，再分页；不要放大纸张掩盖布局失败。

## 8. 候选复核（离线）

```bash
zhigou sch layout-render --from page.json --out layout.svg
python easycirq/scripts/sch_layout_quality.py planned-quality-input.json
```

`layout-render` 输出的是简化符号的离线预览，不是官方导图，也不代表已写入。必须看图，不能只看 JSON。

质量检查器报告具名问题，不做单一“美观分”：

| 代码 | 含义 |
|---|---|
| `page_imbalance`, `mass_asymmetry`, `centroid_offset` | 半页空、器件挤在一侧 |
| `sparse_page`, `low_page_utilization`, `crowded_page` | 页面利用率异常 |
| `module_overlap`, `module_too_close`, `module_near_title_block` | 模块框关系 |
| `module_fragmented` | 模块成员离核心过远（例如 USB 接口孤立） |
| `text_over_symbol`, `wire_over_text`, `missing_text_bbox` | 文字可读性 |
| `symbol_overlap`, `component_over_title_block`, `component_outside_page` | 几何硬冲突 |
| `reading_order_mismatch` | 声明的阅读顺序与页面 Z 顺序不一致（提示，不是错误） |

官方 `layout-lint`/`layout-score` 仍然要跑，但它们不检查页面均衡、模块框架和文字遮挡。真实反例：2026-10-24 温度报警板 `layout-score=94 / excellent`，同时左半页空白、右半页模块互相重叠、USB 接口孤立。**不得用其中一个分数代替看图**。

## 9. 写入：受保护队列

当前推荐路径是 `compose --layout-page` + `--replace --preserve-instances`。它会：

1. 核对整页器件实例、位号、库身份、引脚网络/NC。
2. 只清除授权范围内的导线/标记/页面图形，保留器件实例。
3. 按选定页面平移器件，重画导线和标记。
4. 每步断言，失败即停；不自动回滚已成功的写。

### 9.0 测量证据 → composition

`compose` 只接受一份 composition，而流水线产出的是 connectivity / zones / model-report 三份文件；用适配器合并并校验，不要手拼：

```bash
python easycirq/scripts/sch_compose_input.py \
  --connectivity connectivity-before.json --zones zones-geom.json \
  --model-report model-report.json --sheet sheet.json \
  --out composition.json
```

- 适配器检查：每个器件恰好属于一个区、每个 placement 位号能在 IR 中找到、每个已连引脚的网络与 IR 一致；`blocked` 时不写 composition（exit 1）。
- 它会注入 `connectivity.modules`。缺少这个隐藏字段时 `compose` 报 `layout-page must cover every composition module exactly once`，手工拼 JSON 很容易漏。
- `--sheet` 用 `sheet-geometry --from-svg` 的精确内框/图签；缺省时退回 model-report 的 page 信息并给出 `sheet_border_missing` 警告。
- 导入备份工程后页面 UUID 保留、工程 UUID 改变：用 `--project-id <new-uuid>` 重写，否则 `compose` 报 `before snapshot does not match target project/document`。这是恢复工程的必做步骤。
- `--connection-mode net-labels` 只在明确选择标签连接时使用；默认 `direct`。

```bash
zhigou sch compose --from composition.json --layout-page page.json \
  --out compose-plan.json --before page-before.json \
  --replace --preserve-instances --playbook apply.json
zhigou sch apply apply.json --dry-run
zhigou sch apply apply.json --yes
```

### 9.1 稳定 ID 绑定（preserve-instances 的前置条件）

`preserve-instances` 要求每个 part 的 `otherProperty` 中有：

```text
"EasyEDA Agent Component ID": "cmp-<位号>"
```

手工放置的既有工程通常没有。先用脚本生成/复核逐件命令，再执行；脚本只读快照，不写 EDA：

```bash
# 计划：缺哪个、冲突哪个、每件的 sch modify 命令
python easycirq/scripts/sch_bind_component_ids.py \
  --snapshot page-before.json --connectivity connectivity-before.json \
  --project <project> --doc <page-uuid> --commands-out bind.ps1

# 写入并 save/reload 后复核（必须全部 verified）
python easycirq/scripts/sch_bind_component_ids.py \
  --snapshot page-after.json --connectivity connectivity-before.json \
  --verify page-after.json
```

- `bind` 只补缺失的 `cmp-<位号>`；`rebind` 只在 `--force` 下允许，因为改的是 compose 用来保持实例身份的键。
- 已存在不同 ID、缺位号/primitiveId、位号重复、connectivity 与页面器件集合不一致都会 blocked；blocked 时不写命令脚本。
- 官方 `sch designators plan` 队列仍可用；若场景哈希漂移拒绝，逐件 `sch modify` 并每次回读。绑定只增加自定义属性，不改位号、型号、封装、网络或 PCB 绑定。写后必须逐件回读。

### 9.2 写入前快照归一化

`compose` 守卫按“恰好 10 类 pagePrimitive”校验，而 `sch list --include-page-primitives` 还会返回 `pins` 类（1.15.0 实测仍是 11 类）。直接传入会报 `incomplete class inventory`。处理方式：

- 保留原始快照不动；
- 复制一份，删除 `pagePrimitives.pins`（组件记录里仍有完整 pins）；
- 另存说明 `removedClass/removedCount/reason`；
- 用副本做 compose 的 `--before`，并在报告中记录这是快照归一化，不是删证据。

归一化后的快照会和 apply gate 的 playbook 期望冲突：gate 读源场景时又看到 `pins`，报 `source-drift: pins field present expected=false`。修正 playbook 的 `expectSchematic.pagePrimitives`（`sourceScene` 和顶层两处）加入实时 `pins`，而不是再改回快照；否则 compose 与 gate 会互相打架。记录两边的 class 清单。

### 9.3 锚点不在 5-grid 的符号

某些库符号的引脚相对锚点偏移不是 5 的倍数（实测 D4/KT-0805R：锚点 224，引脚 210，偏移 -14）。求解器会拒绝该器件。当前处理：

- 在测量副本中把锚点参考归一到最近合法网格，记录原始/归一值；
- 标记 `anchor_requires_review`，不允许声称 apply 已验证；
- 写入前用 compose 的引脚断言核对实际平移；若 1 raw 级不一致，把该模块回退为**刚体移动**（`sch group-move`），不要手改队列坐标。
- 更彻底的修复是换用引脚在网格上的等价符号；这属于器件/库变更，需单独评估，不能为排版擅自换料。

### 9.4 区内重排写入（危险）与恢复

`sch zone-arrange` / `sch zone relayout --apply` 会先扫掉区内导线再重建。实测在 10-raw 间距的密集 USB 区失败于 `pin-exit-direction`，J2/R8/R9 的连接已被破坏，工具明确提示 `Mutation may have landed. No automatic rollback.`。

- 不要把 `zone relayout --apply` 当“小步安全操作”；它和整页 compose 一样是破坏性写入。
- 运行前必须已导出 `.epro2` 完整备份，并确认没有其他写入者（`zhigou audit tail`）。
- 失败后立即停写，不要继续 autoconnect 或重放快照。恢复流程：
  1. 保存/关闭当前窗口，确保没有未决写入；
  2. 用 `project import`（或 GUI 导入）把开工前的 `.epro2` 作为**新工程**导入，不覆盖原工程；
  3. `doc ls` 确认页面 UUID 与备份一致；
  4. 用 `sch connectivity` 做恢复工程与冻结 IR 的 diff，必须为 `{}` 才继续；
  5. 在新工程重新绑定 ID（`sch_bind_component_ids.py`），compose 的 `--project-id` 改为新工程 UUID；
  6. 从**新鲜的**恢复后快照重新走测量 → 规划 → compose，不要重放损坏现场的导线/标记快照；
  7. save → reopen → 网表 diff → gate → 导图。
- 快照重放不是恢复手段：垂直 netflag 的**存储 rotation 与视觉 rotation 相反**（传 `--rotation 270` 存成 90），按快照重建标记会留下孤儿短桩和 25 处以上连接漂移。

## 10. 写入后复核

```bash
zhigou sch save --project <project> --doc <page>
zhigou sch connectivity --project <project> --page <page> > connectivity-after.json
zhigou sch gate --project <project>
zhigou sch export-image --project <project> --page <page> --format svg --out after.svg
zhigou sch export-image --project <project> --page <page> --format png --out after.png
```

硬验收：

- 完整网表一致：器件身份/增删、引脚增删、`pin→net` 映射、网络分组全部一致，不能只看 `pin_net_changed=0`。
- 器件实例保留：位号、库身份、`uniqueId`、PCB 绑定、BOM 属性不变。
- `save` 后关闭/重开再读一致；页面 UUID、工程 UUID 未漂移。
- `gate` 的 `blocked` 不等于通过；未执行的阶段单列。strict gate 的既有告警按开工快照建立基线，新增项才计本轮失败。
- 前后图必须来自同一最终状态；截图不能早于最后一次写入。

软验收：

- 质量检查的 error 清零；warning 逐条解释（保留/修复）。
- 导图在正常阅读比例下可读；主信号链可追踪；标签没有把简单拓扑拆碎。
- 与改前相比：模块框不再重叠、页面均衡改善、标签/导线没有明显膨胀。

## 11. 局部返工

发现问题时不要整页重排：

1. 定位模块/器件/网络的稳定 ID。
2. 冻结未受影响模块。
3. 只改该区的成员、核心、网络策略或姿态。
4. 重算该区 → 重新合页 → 重新生成队列 → 全量网表复核。
5. 更新导图与质量对比。

停止条件：合法且可读后停止；连续多轮无改善时报告主要冲突和最好候选，不把“达到次数上限”当通过。

## 12. 已知限制与工具陷阱（实测）

- **并发写入**：多个会话可同时驱动同一个 EDA 窗口。审计日志出现非本会话的 `group-move/prim-delete/connect` 时，现场已不可信；停写、协调、换独占副本。
- **写锁**：`sch modify` 失败后连接器可能进入“write/document transition is being verified”，后续读也超时。等待或 `web reload --project <uuid> --doc <uuid>` 恢复；恢复后重新读现场，不复用旧队列。
- **shelf 行高必须按引脚包络，不能按 bbox**：`layout-sheet-plan --flow z` 与自建打包器只看到器件 bbox，但连接器/排针/晶振的壳脚、固定脚常伸出本体 10–35 raw。行首件的上侧、行内件的下侧因此没有 stub + 标记的空间，`sch autoconnect` 会对这些脚**每个方向**都硬拒（`label leaves the usable sheet area` / `stub crosses a non-target pin`，cost 1e9），表现为“这一页怎么都连不上”，而逐脚看代码却毫无问题。按器件算 `(over_top, over_bot) = 库引脚坐标 − 本体 bbox`，行高 = `over_top + h + over_bot + stub/标记余量 + 行距`，首行另在页顶留同等余量。实测 A4 横向（0..1170 × 0..825 raw，y 向上）可用页顶约 805 raw，端点落在 805 已被判越界；图签 keep-out 在 (468,0)–(1170,198)。
- **行高正确后仍会剩少量人工微调**：相邻连接器的壳脚标记会在行内互相压住，纯 bbox 打包看不出来；本案例需要 3 条 `(page, designator) → (dx, dy)` 的显式偏移。把这类例外写成带原因注释的表，每次重排后重算 bbox 并检查是否被推出内容区，不要只改坐标不留说明——下一轮会被当成噪声删掉。
- **网络自动改名**：`web reload`/保存后，EDA 可能把自动网名从 `D1_N1` 改成 `VBUS` 等。模块计划的网名要与新鲜 IR 对齐；跨会话复用旧 JSON 前先 diff 网名。
- **场景哈希漂移**：官方 `designators verify` 对整页场景做哈希；页面有任何自动保存/属性变化都会拒绝。逐件回读比整页哈希更适合有并发/自动保存的环境。
- **`layout-score` 不是可读性门**：它可以给失衡页面 94 分；必须跑独立质量检查并看图。
- **`layout-score` 的 reversed-label fix 不能照抄**：它按“模块核心方向”判断，不按宿主引脚外法线。实测 `R10.1`/`C1.1`/`R14.1` 的 outward rotation 均为 180°（朝左），fix 却要求 `--direction right`；照做会被 `sch connect` 拒绝或把端口穿进器件。使用前先核对 `pins[].rotation`。
- **`sch clusters` 有逐对/分组两种计数**：同一页可报 24 条逐对 `tight` 或 5 条按簇聚合；都没有 ERROR 时不要当成两套矛盾结论，先统一命令与聚合口径。
- **`layout-render` 是简化预览**：只验证几何转译，不验证官方符号、字体、电气或现场。
- **`layout-sheet-plan` 的 `flow:compact`**：可能输出框重叠；逐框全局坐标复核。
- **`--flow z` 是 shelf 打包**：不会使用图签旁的空洞，密集页的 `needs-pagination` 要用 `sch_sheet_fit.py` 的 MaxRects 预检复核；预检 `fits` 也不能跳过官方合页与逐框复核。
- **`zone relayout --apply` 是破坏性写入**：失败会留下已改连接且不自动回滚；只在有 `.epro2` 备份和独占写锁时使用，失败后按 9.4 恢复。
- **netflag rotation 视觉/存储相反**：`sch netflag --rotation` 传视觉角度，垂直放置时存储值取反（传 270 存 90）。按快照重建标记前先核对 `pins[].rotation`，否则恢复会连错。
- **未标记的直连树会阻断 apply**：同一网络若由多个未命名的直接线树组成，compose 会拒绝；先在模块计划里改成 `module_port` 或补命名，不要用标签掩盖。
- **求解器预算与结构限制**：单区 4–6 件较稳；并联同轨电容对、只有电源/地相连的两件、单器件区常无解或触发 `inner-spacing`；`maxCandidates` 失败只是“本预算内无解”，先拆区/改核心/改网络策略，再谈加页。
- **gate 基线策略**：strict gate 会把改前就存在的图签属性越界、位号文字重叠一并报出。必须在开工快照里建立同名同对象的基线：旧问题保留并逐条记录，新问题必须修复；不能用“非 strict PASS”代替。不得为了消 strict 告警去改图签/属性。
- **文本测量只覆盖位号**：`designator-geometry` 不测型号/参数/自由文字；这些文字的遮挡仍是缺测项，不能声称已验证。
- **PCB 不受益于原理图排版**：原理图的模块邻近不代表 PCB 布局/回流；PCB 另行验收。

## 13. 最小交付证据

一次“排版完成”的交付至少包含：

1. 改前/改后的 `sch list`、`connectivity`、`designator-geometry`、`sheet-geometry` 原始 JSON 与哈希。
2. 模块计划、`layout-source.json`、`zones-geom.json`、`pages.json`、`layout.svg`。
3. 页预算预检 `sch_sheet_fit.py` 报告（fits/no-fit、失败模块与剩余空间）与最终 packed page。
4. composition 适配器报告（blocked/warnings、输入哈希、`connectivity.modules` 注入）与绑定复核（verified N/N）。
5. 质量检查的前后 JSON 与对比；`layout-lint`、`layout-score`、`gate` 结果（含 strict 基线差异）。
6. compose 队列、dry-run 输出、apply journal、save/reopen 回读。
7. 前后 SVG/PNG，且注明“离线预览”或“官方导出”。
8. 未完成/未验证项，逐条标 `NOT RUN`/`BLOCKED`。

没有真实工程时，只能交付离线候选和复现命令，不能写“已改善”。
