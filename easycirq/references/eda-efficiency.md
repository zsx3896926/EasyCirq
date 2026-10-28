# EDA 执行效率、批量写入与可恢复交付

本文件用于“设计已经能画，但写得慢、写坏了、回读不可信”的任务。目标不是追求更少的
调用本身，而是在**不降低连接一致性、原生检查和保存重开验收**的前提下，减少零碎调用、
重复读取、无效重试与返工。

适用：多页原理图、双通道/重复模块、批量放置/连线、跨原理图与 PCB 的纵向闭环。
不适用：纯知识问答、只读评审、只写方案不落图。

## 1. 不可交换的硬约束

1. **同一工程同一时间只有一个写入者。** 多 Agent 只能并行做只读准备/审查；EDA 写入
   由主协调者串行执行。发现其它会话的 `document.open`/写入时，停写并核对现场。
2. **每次写入后要能证明落点。** 超时、`DISPATCH_FAILED`、`partial`、`verified:false`
   都不等于失败或成功；先轻读目标，再决定是否重发。禁止盲重试。
3. **连接一致性优先于排版。** 排版可以分轮；连接、NC、跨页网名、保存重开不能降级。
4. **0 floating 不是图面验收。** 原生 `sch check` 通过后仍要导图看文字、标签、框线
   和阅读顺序；`layout-score` 也不是可读性门。
5. **缓存只用于相同读取，不用于写决策。** 保存/重开/任何 mutation 后必须换版本标签
   或失效；缓存命中不能证明画布当前状态。

## 2. 开工前：先花 10 分钟，省 1 小时返工

### 2.1 需求冻结与页面盘点

- 先读设计源和交接，区分“原任务强制项 / 设计推导值 / 本轮新增想法”。新增指标未获
  批准时不进入首版。
- 用 `design_inventory.py` 把设计源 `parts[]` 与每页 `sch list --include-pins` 对齐：

```bash
python design-hardware/scripts/design_inventory.py \
  --design design.json \
  --eda P1=page-P1.json --eda P2=page-P2.json \
  --check P1=check-P1.json --check P2=check-P2.json \
  --out inventory.json
```

输出区分：计划件数、实际件数、缺失/多余位号、空页/未计划页、每页 native check 的
floating 与 finding 分类。**件数完整不等于连线完成**（P7/P8/P9 可能件数齐但几十个
floating），报告必须把两列分开。

### 2.2 通道模板复用与网络映射

重复通道不要“照着再画一遍”。先定义一个已验证通道的映射文件，再用
`channel_map_check.py` 机械核对：

```json
{
  "schemaVersion": 1,
  "referencePage": "P1",
  "instancePage": "P3",
  "refMap": {"J1": "J2", "R101": "R201", "K1": "K201"},
  "netMap": {"RELAY1": "RELAY4"},
  "netRules": [{"fromPrefix": "CH1_", "toPrefix": "CH2_"}],
  "sharedNets": ["GND", "+5V1", "+24V_FILT", "-24V_FILT", "+3V3"]
}
```

```bash
python design-hardware/scripts/channel_map_check.py \
  --reference page-P1.json --instance page-P3.json --mapping ch1_to_ch2.json
```

它按位号映射和网名规则逐引脚比较；未映射的网、缺失/多余位号、网名不一致都失败。
设计源和 EDA 回读都支持。设计源通过只证明“模板对称”；EDA 回读通过才证明“实例真的
对称”。两者都要做。

### 2.3 画图前的批量器件库预检

```bash
python design-hardware/scripts/library_precheck.py \
  --design design.json --devices devices.json --out library.json
```

检查：位号唯一、value/mpn、package、lib/dev UUID、LCSC（或显式 non_lcsc）、同一
deviceUuid 的 package/mpn 冲突、身份表覆盖。它不证明 symbol/footprint/pin-pad 正确；
这些仍需库回读与放置实例核对。

### 2.4 工具链预检（PCB 通道尤其重要）

在**隔离副本/一次性小工程**上先验证，不把整页原理图投进去才发现 PCB 不可用：

```text
sch place 1 件 → sch connect → sch save → doc reload → 读回
pcb 激活 PCB1 → pcb import-changes → 回读 componentsAfter/partial/verified
pcb outline-round → outline-get → save → reload → 再读
```

硬判据：
- `pcb import-changes` 必须 `imported:true` **且** `partial:false` **且**
  `verified:true`，回读 `componentsAfter` 等于已放置页的器件数；
- 板框必须回读到 `width/height/radius/locked`，保存重开后不变；
- 只看 `imported:true` 不算导入成功。`componentsAfter:0` + `partial:true` 是失败。

**实测工具事实（EasyEDA 4.1.78 / easyeda-agent 1.14.0）**：PCB 导入失败的一个真实
原因是 PCB 不是活动文档。先 `doc open <pcb-uuid>`/激活 PCB1，再 import；同一工程
导入 212 件得到 `partial:false, verified:true`。不要因为一次 `imported:true` 就重复
 import；先看 `componentsAfter` 与 `partial`。

## 3. 批量执行：按功能模块组织，按批次回读

### 3.1 批次与检查点

- 以**功能模块/页**为批次，不以“一个引脚一个进程”为默认。
- 每批控制在可回读的规模（原理图 10–20 件/批，PCB 10–20 件/批）；批次之间做
  **局部回读**，阶段结束再做全量 `sch check`/`connectivity`/`pcb list`。
- 检查点记录：批次 id、动作、对象稳定 id（位号/primitiveId）、请求参数、返回
  `ok/appliedDelta/partial`、耗时、回读哈希。恢复时从第一个未确认批次继续。
- 不把“返回 ok”当落地证据；检查点里必须有回读字段。

### 3.2 局部回读与全量验收

- 普通操作：只回读受影响位号/引脚/网络，或只读 `sch list --page` 的摘要。
- 阶段结束：`sch check --page`、`sch connectivity --page`、`pcb list`、`pcb outline-get`。
- 交付前：`save → doc reload → 全量回读`，比较器件身份、pin→net、网络分组、
  NC 标志；PCB 比较 components 计数/位号/板框。

### 3.3 超时后的对账（最重要的一条）

超时/断连/`DISPATCH_FAILED` 后，**先生成一条轻读**：

```text
sch list --page <page> --include-pins   # 目标 pin 的 net 是否已经变了？
pcb list                                # 目标 designator 是否已在目标位？
```

- 已落地：记录为 `landed-by-readback`，不要重发。
- 未落地：只重发失败对象；不要重放整批。
- 不确定：保存/`doc reload` 后再读；仍不确定就停，保留证据。

`group-move` 的 `appliedDelta` 被钳位、`recoveredFromReadback:true`、
`Mutation may have landed`、`假成功/假失败` 都走这条规则。

### 3.4 不要用 clear/整页重做解决局部问题

整页 `sch clear`/`pcb clear` 会把已成功连接清掉，产生 re-place/re-connect 和更多
save，是上一轮 192 min 的主要浪费之一。只有页面被证明损坏、且已保存好可恢复快照时
才清页；优先 `prim-delete` 单对象、`disconnect` 单 pin、局部重连。

## 4. 版本化缓存：带失效条件，缺失即未命中

`eda_cache.py` 提供最小机制：

- 键：`project + document + action + SHA256(canonical params) + toolVersion`；
  影响结果的调用方/工具版本必须进键，不能只放在条目里事后比较；
- 值：读取结果 + `storedAt` + 调用方 `versionTag` + CLI/connector 版本 + `toolVersion`；
- 失效：工程/文档变化、`versionTag` 变化（保存/重开/任何 mutation 后必须 bump）、
  CLI/连接器版本变化、`toolVersion` 变化、TTL、显式 invalidate、条目损坏；
- **fail-closed**：任何不匹配都返回 `miss` 与原因，绝不返回旧值。

```bash
python design-hardware/scripts/eda_cache.py put --cache .cache/eda \
  --project <uuid> --document <page> --action schematic.components.list \
  --params '{"page":"P1","includePins":true}' --version-tag save-42 \
  --cli-version 1.14.0 --tool-version layout-v3 --value page.json

python design-hardware/scripts/eda_cache.py get --cache .cache/eda \
  --project <uuid> --document <page> --action schematic.components.list \
  --params '{"page":"P1","includePins":true}' --version-tag save-42 \
  --tool-version layout-v3
```

版本标签建议来自 `doc ready`/`sch save` 后的页快照哈希、保存序号或 `@Update Time`。
没有可靠版本标签时，写决策与验收读取一律不走缓存。

## 5. 分区、标题、用途说明与碰撞

### 5.1 页/区规划

- 先按功能分页，再页内分区；一页不要为“每几个器件”单独建区，也不要为凑页数拆页。
- 每区必须有：功能标题、简短用途说明、信号方向/网络名、关键参数（区分目标/计算/实测）。
- 分区框不能穿过器件、文字、导线；框之间留 12 raw（工具默认）；图签 keep-out 是硬约束。
- 去耦器件跟随对应芯片，不为框的外观集中移走。

### 5.2 可用的绘图入口与边界

- `sch frame apply --from frames.json`：显式矩形 + 单行标题，回读 `verified`、`unchanged`。
  **标题只接受单行**；多行会被拒。
- 用途说明：typed action 目录没有 `schematic.text.create`（只有 list/move）。可用
  `easyeda debug exec` 调用 `eda.sch_PrimitiveText.create(x,y,content,rotation,null,null,fontSize)`
  作为受控 escape hatch，创建后用 `sch text-list` 回读；这是工具缺口，不是首选路径。
- `sch zone-draw`/`sch zone-arrange` 读虚拟组/zone 认领；手工页先用
  `sch group create --members ... --name ...` 建组。
- `sch zone-arrange --apply` 的断言①只接受“桩线+标记”可重建的连接；普通导线直连
  （树上无标记）会被拒绝。`sch netflag --kind net_label` 创建的 net label 不被
  `components.list` 返回，zone-arrange 看不到它——这是实测缺口。绕过方式：
  - 用 `sch group-move --group <g> --dx --dy` 做整组刚移（会带桩线/旗）；
  - 或把连接改成 netport/可见 power flag 后再规划；
  - 不要把“补了 net_label”当成 zone-arrange 已能识别。

### 5.3 碰撞治理

- 先用原生 `sch check --page` 拿到 marker-overlap/designator-overlap/out-of-sheet/
  floating-pin；再用 `sch layout-lint`/`sch clusters` 与独立质量检查补充。
- 原生检查的 `marker-overlap` 用标记本体/文字带包围盒；`designator-overlap` 可能只有
  0.5 raw 的擦边。对每条 finding 记录：对象 id、重叠尺寸、是否合法接触（标签锚点在自己
  的导线上、引脚文字、图签字段）。
- `sch destagger --apply` 只处理标记；遇到“成员的连线树同时触及非成员 pin（共享导线）”
  会拒绝，不能用它硬清。此时手工 `disconnect` 单 pin + `connect` 改方向/短桩，或移动
  整个组。
- 修复顺序：先连接（0 floating），再清除会遮挡引脚/网名的重叠，最后做视觉美化。
  连续两轮没有改善或连接器降级时停止，报告残留与下一动作。

## 6. 阶段验收与停止条件

每个阶段至少四类证据：

| 类别 | 证据 |
|---|---|
| 连接 | `sch check`（0 floating）、`sch connectivity` 前后 pin→net diff、NC 标志 |
| 身份 | 位号/库身份/uniqueId 前后一致；`design_inventory` 缺失/多余为 0 |
| 持久化 | `save → doc reload → 回读`，页 UUID/工程 UUID 不漂移 |
| 图面 | 官方/离线导图实际查看；框、标题、说明、标签可读；越界/压字有结论 |
| PCB | `import-changes` partial:false/verified:true、`outline-get` 尺寸/圆角、保存重开 |

停止条件（满足任一即停并报告）：
- 验收项全部通过且没有新的 blocking finding；
- 连续两轮修改没有改善（质量指标/重叠数/可读性）；
- 连接器连续降级、ACTION_BUSY、读超时，无法证明现场；
- 预算/上下文到达阶段上限；保留最佳候选与恢复入口。

`0 floating`、`DRC 0`、`layout-score` 高、`gate` 绿都只证明各自子项，不替代看图与
保存重开。

## 7. 性能记录：把墙钟、工具时间和思考分开

- `easyeda audit cost --day ... --since ... --until ... --json` 给出墙钟、daemon 时间、
  `components.list`、probe、失败与 top actions。
- 注意：`audit cost` 的 `think = wall − Σduration` 会忽略并发；多窗口/后台时用调用
  区间并集（union）而不是 Σduration。报告要写清用的是哪一个口径。
- 记录：calls、failures、probes、mutations、`components.list` 次数/秒、place/connect
  失败、save 次数、document.open 次数、clear/re-place/re-connect 次数。
- token 不在审计日志里；要报就由调用方自报，不能估算冒充实测。
- 对比必须同对象、同完成标准、同连接器状态；不同页/不同密度/后台并发不可直接外推。

### 本轮实测（2026-10-26，EasyEDA 4.1.78 / easyeda-agent 1.14.0）

| 指标 | 上一轮双通道会话 | 本轮隔离副本会话 |
|---|---:|---:|
| 窗口 | 348c362f | 6c8f658f |
| 墙钟 | 192.5 min | ~51 min（06:13–07:04 UTC） |
| EDA 调用 | 9593 | 3047 |
| 失败 | 259（2.70%） | 55（1.8%） |
| `components.list` | 3892 次 / 3435 s | 759 次 |
| 上下文探测（current+pages+pcb docs） | 2847 / 123.9 s | 1231 |
| 工具并集 | 90.9 min（复算） | 16.9 min |
| 结果 | 多页部分完成、PCB 0 件 | P1 0 floating + 212 件 PCB verified + 板框持久化 |

两个会话任务不同，**不能当作受控 A/B**。受控微基准：同一页 5 次读，单进程
playbook 5.75 s / 12 条审计（4 个上下文探测）vs 5 个独立进程 8.12 s / 30 条
（15 个探测）——读批处理约 −29% 墙钟、探测 −73%。这支持“批处理读”，不支持
“总耗时 −50%”的宣称。

## 8. 多 Agent：并行只用于可并行的部分

- **主协调/EDA 写入者**：唯一写者；串行执行 EDA，维护检查点与验收。
- **设计准备**（只读）：架构/数据手册复核、设计源一致性、页面盘点、器件库预检、
  碰撞方法设计。可并行。
- **独立审查**（只读）：对关键结论做反证，必须查原厂资料/设计源，不能沿用主写者
  的结论；输出 CONFIRMED/REFUTED/UNVERIFIED 与证据。
- 记录角色、开始/结束、等待时间、集成返工。**不要用 Agent 数量或同时运行数当提速
  成果**；只有同对象、同标准的墙钟/调用/返工对比才算。
- 本轮实测：5 个只读准备角色并行约 24 min 完成（文件最后写入 14:15–14:19）；
  单写入者在其间因另一会话 `document.open` 触发 `ACTION_BUSY`，21 页探测全部失败，
  这是并发集成返工的直接证据。EDA 关键路径仍是串行。

## 9. 常见工具陷阱（本轮实测）

| 现象 | 处理 |
|---|---|
| `document.current failed: write/document transition is being verified` | 另一个写入者在收尾；等、轻读，不要切页/写 |
| 连续写入后 `DISPATCH_FAILED / context deadline exceeded` | 停写；轻读 `doc ready`/`sch list`；仍失败则 `doc reload` 或换窗口；保存恢复入口 |
| `sch group-move` 返回 ok=false 但输出“对账绿/appliedDelta” | 以回读为准；记录 `appliedDelta`，不要重发 |
| `group-move` 钳位到图纸边 | 目标坐标先做边界预检；留 ≥30 raw 边距，避开图签 keep-out |
| `sch zone-arrange --apply` 断言①拒绝普通导线 | 不要补 net_label 硬试；用 group-move 或改可见标记 |
| `sch destagger` 拒绝共享树 | 手工 disconnect/connect 单 pin，或把邻件并组 |
| `sch frame apply` 多行标题被拒 | 单行标题；用途说明另走 text create（受控 escape hatch） |
| 图签 Name/Description 渲染到图框外左下角 | A4 模板无对应行；保留字段值但 `showValue:false`，用现有行/图上说明 |
| `pcb import-changes` 0 件/partial | 先激活 PCB1；再看 componentsAfter；不要重复 import |
| `pcb snapshot` 报 tab hidden | 用 `pcb dump --include-copper --out` + `pcb layout render --actual` 离线出图；标注“辅助图” |
| `sch list --all-pages` 数量少/位号空 | 非活动页浅读；逐页 `--page` + `--include-pins --include-bbox` |

## 10. 证据与交付分类

最终报告必须分开：

- **已实现**：代码/文档已提交，入口可运行；
- **离线通过**：单元测试/离线工具/合成数据通过；
- **真实 EDA 通过**：真机写入、回读、保存重开、原生检查、导图；
- **BLOCKED**：工具/环境阻塞，附最小复现与恢复入口；
- **NOT RUN**：未执行，不能写成通过。

性能记录、前后图、连接 diff、PCB 回读、缓存命中/失效日志都放证据目录；对话只给
结论、必要错误摘要和路径。
