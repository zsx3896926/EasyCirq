# 可选离线辅助：续航与原理图几何

Agent负责从资料/实际回读整理输入，新手不写JSON。两脚本只读本地文件、无网络/EDA/写入；不是绘图前置门禁。先用现有执行器的原生检查，离线工具补充可审查的计算与候选问题，不重复造一个独立EDA验证器。

需要完整离线回归、证据 manifest 绑定、冻结基准或图面叠加图时，先读 [离线回归与基准](offline-regression.md)：仓库根目录 `python tools/offline_suite.py` 在 `HDS_OFFLINE=1` 下拦截真实 `zhigou` 与网络；`python tools/offline_benchmark.py` 生成 correctness/coverage/timing；Skill 目录 `python scripts/sch_visual_audit.py` 输出明确标注的分析叠加图。

## 续航：先换算到电池输入侧

运行 `python scripts/power_budget.py budget.json`。输入见 [虚构续航算例](../assets/example-power-budget.json)。

| 字段 | 含义/限制 |
|---|---|
| `capacity_Ah` | 整组电池在适用负载/截止条件下的标称容量，单位Ah；串联增加电压不增加Ah，不能把两节各2000mAh相加成4000mAh |
| `usable_fraction` | 明确填写的可用容量比例，范围(0,1]；依据温度、负载、截止等给出条件，不默认七折 |
| `current_basis` | 固定为`battery_input`，确认所有电流已换算到同一输入侧 |
| `sleep_current_A` | 整板电池端总睡眠电流，单位A，包含稳压/分压/LED/保护/外设漏电；必须明确填写 |
| `states` | 互不重叠的完整工作状态，每项有唯一`name`、总电流`current_A`、单次`duration_s`、每日`events_per_day`；可用平均每日次数，合计不超过86400秒 |
| `target_days` | 可选、正数，模型寿命低于该值退出1 |

各状态为整板总电流，不是“睡眠电流之上的额外电流”；状态有重叠就先合成互斥状态，避免重复计时。余下时间才算睡眠。模型按每日Ah求平均，输出状态耗电、平均电流、估算天数及尚未验证项。

负载侧电流不能直接与电池Ah相除。转换器可用`I_bat≈V_load×I_load/(V_bat×η)+I_q`初估，并注明各电压/效率与Iq是否已计；LDO的电流关系和损耗另按具体器件，不把功率转换式中的效率重复计算。电压变化明显时分状态/范围计算，不能用一个典型效率保证寿命。

分别做典型/不利场景：低温/老化容量、弱网重试、传感器预热/稳定、连接/发送/确认、唤醒/关机和睡眠。峰值供电、启动/掉压、电池内阻、自放电与长期曲线不由本脚本验证；容量折算不能弥补供电拓扑不工作。

退出0仅表示本次模型已计算或零耗电模型不足；看`status`与`model_meets_target`。全零耗电返回`estimated_days:null`，不输出无限续航或通过目标。退出2表示输入错误，包括非有限数、重复JSON键、错字段和时长溢出。算例完全虚构，不能当任何芯片的保证电流。

## 图面几何：检查实际边界，不猜电气

运行 `python scripts/sch_layout_check.py layout.json`。从当前EDA读入每页的几何，必要时拆页。输入见 [虚构几何算例](../assets/example-layout.json)。此版本的输入契约与来稿的同名脚本不同，不能直接混用JSON。

| 字段 | 含义/限制 |
|---|---|
| `coordinate_units` | 明确坐标单位，与回读一致；不自动换算像素/英寸 |
| `components` | 每项`id,bbox`，bbox为符号本体受保护矩形，不含向外引脚；复杂符号采用矩形近似会误报，需实际导图复核 |
| `texts` | 每项`id,bbox`，包括外部位号、值、网名、注释/标题的完整实际边界；可选`owner`指向实际父对象ID（如器件primitiveId）、`kind`（`attribute/free_text/zone_title/pin_name/pin_number/netflag/net_label/wire_name/title_block/border/symbol_text/unowned`）、`net`、`anchor_id`、`anchored`、`measurement`（`bbox`/`estimated`）、`field`、`content`。`kind` 为引脚名/脚号或符号图形文字且 owner 是该符号时，符号本体重叠不再是碰撞候选；未声明 kind 时保持旧行为。`anchor_id` 指向文字所属导线：仅当该线只在文字 bbox 边缘（`policy.label_own_wire_edge_tolerance`，默认1 raw）接触时记 `label_own_wire_edge_contact` info；**穿入文字主体仍报 `wire_enters_bbox`（带 `own_wire:true`）**，其他导线穿字始终报 |
| `wires` | 每项`id,points`，至少两个不同连续点；可给`net`以提示不同命名导线的内部交叉；不得据此合并/改名。可选 `primitive_id` 表示同一 EasyEDA 导线图元的分段；适配器把 `rawEncoding=flat-segments` 的每 4 个数作为一条独立线段，不能当连续折线读，否则会伪造斜线穿符号 |
| `page_bbox` | 可选、页面实际可用范围；采用`[min_x,min_y,max_x,max_y]`，与坐标朝向无关，四值有序且边长为正 |
| `expected_counts` | 可选，来自实际回读的components/texts/wires数量，用于发现提取漏项；数目相同仍不能证明身份、版本和几何完整 |
| `policy.max_wire_length` | 可选、项目自行指定的导线长度提示阈值，单位与坐标一致；不设默认通用格数 |
| `title_block` | 可选、图签实际矩形；检查器件/文字压图签、导线穿图签、图签越页 |
| `title_block_owned` | 可选、图签自身字段的文字ID列表；仅豁免这些文字与图签矩形的重叠，仍参与其他文字/导线碰撞检查。ID必须存在于`texts`，否则输入无效 |
| `policy.self_text_contact_tolerance` | 可选、非负数，单位与坐标一致；仅当文字`owner`等于某器件ID、且重叠深度不超过该值时，把贴边接触记为`symbol_text_edge_contact`（info），不当作普通`bbox_overlap`。默认0，不为真实叠字开脱 |
| `module_frames` | 可选、每项`id,bbox`与可选`contains`成员ID列表；检查框越页/压图签/互相重叠/框线切器件/成员缺失或成员在框外 |
| `attachment_points` | 可选、每项`id,x,y,kind`，声明的真实引脚/网络标识/端口/标签连接点；配合`connection_tolerance`检查导线端点悬空与同一连接点多网 |
| `label_anchors` | 可选、每项`id,net,x,y`；配合`connection_tolerance`检查标签是否落在导线/连接点、标签网名是否与所在导线一致、同点不同网 |
| `policy.connection_tolerance` | 使用端点/标签检查时必填、正数；单位与坐标一致。未填时这些检查跳过并写入`checks_skipped`，不偷偷用经验默认值 |
| `policy.wire_endpoint_check` | 可选布尔，默认true。EasyEDA 折线用中间顶点连接时端点检查会产生假悬空；回读适配器设false，连通性以 `zhigou sch check` 为准 |
| `policy.min_text_wire_clearance` | 可选非负值；文字与**非自身**导线距离不超过该值时报告 `text_wire_clearance`（`severity=info`、`category=readability_hint`，不阻塞）。标签所属导线由 `anchor_id` 豁免；引脚名/脚号、符号文字、netflag/图签/边框文字不参与。真正穿入文字框仍由 `wire_enters_bbox` 作为阻塞候选 |
| `policy.label_own_wire_edge_tolerance` | 默认1.0 raw；只用于**自身导线**：线段进入文字 bbox 但未进入内缩该值的内部时，记 `label_own_wire_edge_contact` info；进入内部仍报 blocking `wire_enters_bbox`。把“归属”当“合法遮挡”会漏掉导线穿过自己网名的情况 |
| `policy.junction_tolerance` | 默认1.0 raw；`no_junction_crossings` 声明点与真实交点的匹配半径 |
| `no_junction_crossings` | 可选列表，每项必须 `{x,y,wires:[两段导线ID]}`；只有同时提供页/哈希绑定的 `junction_evidence` 才接受，否则输入无效。仅当交点、两条导线 ID 与声明完全匹配时降为 hint；未列出的交叉仍 blocking。共线重叠始终 blocking |
| `junction_evidence` | 对象 `{source,page_id,snapshot_sha256}`：说明无结点清单来自哪次宿主检查，并绑定页 ID 与快照哈希；任一不匹配按 stale evidence 拒绝，防止改线后旧证明继续生效。没有它不得把交叉降为提示 |
| `policy.duplicate_net_distance` | 默认40；同网文字中心距不超过该值且至少一方是 net_label/wire_name 时报告 `duplicate_net_text`；同一 `anchor_id` 上的同网文字始终报告。`kind=net_label` 且 `anchored=false` 报告 `unanchored_net_text` |
| `net_flags` | 每项`id,net,bbox,rotation`，可选`kind,anchor,text_id`；按 `policy.netflag_rotation` 检查普通电源/地符号的朝向一致性。`allowed` 显式列出有理由的例外，`requireHorizontalText` 检查网名文字是否竖排 |
| `module_frames[].order` | 可选正整数；按上到下、左到右排序后必须递增，否则报告 `zone_reading_order`。没有 order 时不能检查阅读顺序 |
| `policy.reading_order` | 布尔；严格模式要求全部模块框都有 order |
| `policy.require_rendered_texts` | 布尔；严格模式要求 `coverage.rendered_texts.status=complete`，即官方 SVG 中每个渲染文字都有实测 bbox |
| `policy.require_measured_texts` | 布尔；严格模式要求每个文字 `measurement=bbox`，估算框不能通过 |
| `policy.title_block_repeat_allow` | 字符串数组；图签内允许重复的模板常量（公司名、图名、版本等），避免把模板重复当缺陷 |
| `policy.netflag_rotation` | 形如 `{"GND":{"expectedRotation":0,"allowed":["id"],"requireHorizontalText":true}}`；按网名声明普通符号的期望朝向，例外必须逐项列出 |

所有对象ID唯一；矩形坐标必须有限且有序。标签只有锚点没有文本边界时，不得用锚点冒充已检查文字；无法量边界就保持覆盖不足并实际看图。不要为取得工具0退出而删去难处理的对象。

### 从 前代执行器 v1.15 回读构建输入

`layout_from_zhigou.py` 把真实 CLI 响应拼成上述输入，不连 daemon：

```bash
zhigou sch list --include-bbox --include-pins --include-wires \
  --include-page-primitives --page <page> > list.json
zhigou sch sheet-geometry --from-svg page.svg --json > sheet.json
python scripts/svg_text_bbox.py page.svg --out svg-text.json
python scripts/layout_from_zhigou.py --list list.json \
  --visible-text visible-text.json --sheet-geometry sheet.json \
  --rendered-text svg-text.json --min-text-wire-clearance 5 \
  --expect-rotation GND=0 --expect-rotation +5V=0 --out layout.json
python scripts/sch_layout_check.py layout.json --strict --out layout-check.json
python scripts/pin_net_intent_check.py docs/netlist-intent.json sch-read.json \
  --out pin-net-diff.json
```

`--out` 以 UTF-8 落盘；不要用 PowerShell `>` 生成证据 JSON（控制台代码页可能写出非 UTF-8）。

- `visible_text.bboxes` 只含自由文字与已显示属性（光控页 72 条），不含符号内脚名/脚号、图框行列号、图签字段和 netflag 网名。`svg_text_bbox.py` 用无头 Chromium 实测官方 SVG 的全部 `<text>`（同页 134 条），输出 SVG 用户坐标；`layout_from_zhigou.py` 翻转为 y-up。
- 适配器按几何与 API 身份分类：`pin_name/pin_number/symbol_text` 归属符号，`netflag` 归属标记，`title_block` 归属图签，`border` 为图框，无法归属的可见文字标 `unowned`。这就是“有显示但 API 列举不到”的孤立文字检测入口。
- 估算的脚名/脚号标 `measurement=estimated`，coverage 保持 partial；只有全部渲染文字都有实测 bbox 时才允许 `require_rendered_texts` 严格通过。不得把估算框冒充实测。
- `wire_endpoint_check` 默认关闭：EasyEDA 折线可在中间顶点连接，按首尾端点会误报悬空；连通性使用 `zhigou sch check`/`sch read`，本检查器只负责几何与文字。
- `netflag_rotation` 是项目声明的普通符号朝向约定；因引脚方向必须横放的标记用 `allowed` 逐项豁免并看图确认，不能为了全绿机械旋转有特殊用途的符号。
- 新增候选：`unowned_visible_text`、`unanchored_net_text`、`duplicate_net_text`、`netflag_rotation_outlier`、`netflag_text_vertical`、`zone_reading_order`、`title_block_duplicate_text`、`text_wire_clearance`。`severity=info` 的贴边接触不算阻塞；`--fail-on-info` 可把它们升级为退出1。
- 导线适配器必须按 `flat-segments` 拆段，不能把无序段列表当折线；否则会从 (430,230) 直接连到 (240,195)，伪造“导线穿 U1 本体”。`wire_name` 文字通过 `anchor_id` 绑定到所属导线；适配器同时把每个 wire-name 文字写入 `label_anchors`，因此 `label_anchors` 覆盖不再只依赖 netport/netlabel 组件。
- 自身导线豁免是**边缘级**而不是归属级：`anchor_id` 只证明“这条线是它的”，导线若穿进文字主体仍报 `wire_enters_bbox(own_wire=true)`；只有内缩统一容差内不进入时才记 `label_own_wire_edge_contact` info。正反例见 `tests/test_sch_acceptance.py`。
- 无结点正交交叉 `different_named_wires_cross` 只有在 `no_junction_crossings` 列出该交点、且 `junction_evidence` 指明宿主检查来源时才降为 `severity=info`；没有清单/证据或交点未列出仍 blocking。同向共线重叠 `different_named_wires_collinear_overlap` 始终 blocking。近距贴线 `text_wire_clearance` 是 hint；真正穿字 `wire_enters_bbox`、符号本体重叠 `bbox_overlap` 仍是阻塞候选。报告要分开“真实几何候选”和“可读性提示”，不要把 hint 数量归零当成验收通过。
- `layout_from_zhigou.py --junction-report` 接受宿主 `sch read`/`sch check` 的已验证无结点 JSON（`verified/source/pageId/snapshotSha256/noJunctionCrossings`，每条含 `x,y,wires` 两个导线 ID）；适配器先算快照哈希，页/哈希/导线 ID 任一不匹配即按 stale evidence 拒绝，不会自行推断结点。没有该输入时交叉保持 blocking。`--page-id` 用于绑定 schematic 页 UUID。
- `pin_net_intent_check.py` 比较设计意图与 `sch read` 的物理引脚连通组：网名可不同
  （`DISCH` vs `$1N117`），但每个意图网络必须恰好等于一个真实网络的引脚集合；
  多脚、少脚、拆网、并网、未声明连接都会列出。极性/功能脚名用 `pinMap` 显式落号。

工具提示矩形重叠、线穿本体/文字、越页、指定的长线及不同命名导线交叉；边缘相切不按进入矩形处理。带可选字段时还提示压图签、模块框问题、悬空导线端点、同一连接点多网、标签悬空/错网。不判真实短路、连接点/端口作用域、NC、去耦的电气距离、模块内边距或阅读质量，也不自动证明同网线相连。`attachment_points`/`contains` 只是输入声明，不完整时会产生误报或漏报；`checks_skipped` 明确列出未运行的检查。重叠/交叉/悬空都是待核查候选，不是自动改线指令。

`symbol_text_edge_contact` 只把已声明owner的浅贴边从普通重叠中分流为info，必须仍看局部图；文字深入自身符号本体仍报`bbox_overlap`。`title_block_owned` 只说明“这段文字属于图签自身字段”，不表示图签排版正确；未声明的文字压图签仍报`overlaps_title_block`。两者都不能把coverage标成complete，也不能替代实际导图检查。

退出0表示未发现候选，输入可能不完整；1表示存在候选；2表示格式错误。只有有对象且声明数量匹配时可输出`no_candidates`，其余无候选结果为`incomplete`；`electrical_verified`和`visual_verified`始终为false。即便有计数匹配，仍要执行实际网络回读和官方导图的整页/局部验收。

## 器件身份与 SCH↔PCB 绑定

重放/换库/批量改属性之后，网表一致不能证明器件身份没变。用
`python scripts/component_identity_check.py --before before-list.json --after
after-list.json [--pcb pcb-list.json] --out identity.json` 比较两份
`zhigou sch list --include-device-identity --include-page-primitives
--include-pins --include-wires` 回读：

| 检查 | 判据 |
|---|---|
| 器件身份 | `device.libraryUuid/uuid/name`、`symbol.libraryUuid/uuid/name` 逐位号比较；变化为 blocking |
| 封装 | `otherProperty.Footprint/Supplier Footprint`（或 device/pcb footprint）变化为 blocking |
| BOM 属性 | Manufacturer Part、Supplier Part、LCSC Part Name、Value、Footprint、JLCPCB Part Class、Description、Add into BOM/PCB；逐键列出 before/after |
| 引脚 | 脚号→脚名变化为 blocking；网络变化按**引脚集合分区**比较：仅网名从 `$1N…` 改为标签名为 info（`net_names_changed`），分区变化才是 blocking（`net_partition_changed`） |
| 位号/实例 | 位号新增/删除 blocking；`uniqueId` 或 `component.uuid` 变化 blocking（实例身份变了，不能只靠位号/库身份）；仅 `primitiveId` 变化为 info；缺 `uniqueId` 报 `instance_identity_unavailable` blocking |
| BOM 属性 | Manufacturer Part、Supplier Part、LCSC Part Name、Value、Footprint、JLCPCB Part Class、Description、Add into BOM/PCB；逐键列出 before/after。`--expected-changes declared.json` 可把**有 reason+evidence 且 before/after 完全匹配**的变更降为 `expected_change` info；未列出、声明不匹配或缺少证据仍 blocking，未用到的声明报 `expected_change_unused` |
| SCH↔PCB | 提供 `pcb list`/`pcb components list` 时，按位号找 PCB 器件并比较封装；缺件/封装不一致 blocking，PCB 多出的安装孔等记 info。未提供 PCB 输入时明确 `pcb_binding: not_run`，状态 `pass_sch_only`；这不等于 PCB 绑定已验 |
| BOM 导出 | 脚本比较的是 SCH 属性，不读取 BOM.csv；实际 BOM 导出需另跑并核对（本环境 CLI 无导出时如实 NOT RUN） |

脚本不判电气正确性、不替代 `sch read`/`pin_net_intent_check.py`，也不判 PCB
封装可制造性。退出 0 仅表示 `pass`/`pass_sch_only`；1 表示 review；2 表示输入
不完整/无位号。真实光控板 v14 的 before/after 回读用它得到：19/19 位号、
`uniqueId`、`component.uuid`、device/symbol/封装/引脚名未变；12 个网只是
`$1N…`→标签名（info）；RV1 的 `Value` 从 `-` 改成 `10kΩ` 已用
`--expected-changes` 声明为有依据的显示值变更（info）；实际 BOM 导出与
SCH↔PCB 绑定均为 NOT RUN（原工程无 PCB 输入）。

## 其他脚本思路如何使用

保留来稿中“项目档案对账、BOM成本汇总、制造包清点”的目标，按本Skill的现有记录、商城配单、制造和验收流程落实，不默认执行未合入的脚本或不存在的`parts-select.py`。只核对网名集合不能证明GPIO/物理脚正确；猜Gerber文件名/坐标不能证明板框闭合、圆弧尺寸、钻孔工艺或可制造性。

## PCB 实测几何与约束

有真实 `zhigou pcb dump` 与 `sch read` 时，用 `pcb-constraints` / `pcb-check-plan` / `pcb-candidates` / `pcb-escapes` / `pcb-power` / `pcb-diff` 做离线约束、局部模板、候选与回读比较，详见 [PCB执行工作流](pcb-execution.md)。这些命令只读本地 JSON，不连接 EDA；`near_pin` 是 pad 中心距，`pcb-escapes` 是代理预判，二者都不是铜路径/可布通证明。写入必须走 typed `zhigou pcb ...`，保存重开后用 fresh dump 再比较。

## 新增可执行计算与仿真

- `calculate.py` 新增 `buck`、`boost`、`adc_settle`、`current_sense`、`wire` 模式；字段、公式前提和不能证明的内容见 [计算手册](calculations/README.md)。它们仍是简化模型，不证明补偿、稳定性、EMC、SOA 或整机精度。
- `rc_settle_sim.py` 是可执行的二阶 RC 采样网络数值仿真（后向欧拉，不是 SPICE）。输入 `--help` 查看；输出 CSV 和 JSON，含 `simulation_executed:true`、`board_verified:false` 与模型限制。`assets/simulation/rc_sample.cir` 是同一网络的 SPICE 计划文件，当前标注 `NOT RUN`，不能声称已运行。
- [仿真与测量](simulation-measurement.md) 给出测点、仪器、探头接法、带宽/负载、预期范围、停止条件和安全边界；没有执行的项目保持 `未执行`。

## 原理图严格模式

创建/实质整理图面时使用 `python scripts/sch_layout_check.py layout.json --strict`。
原有无参数模式保留为辅助提示，不能用其退出0代替严格模式。
严格模式要求 page_bbox、title_block、module_frames、attachment_points、label_anchors、
connection_tolerance、匹配的 expected_counts，以及 coverage 中 components/texts/wires/
module_frames/attachment_points/label_anchors 各项 status=complete。
无对象的种类也用空数组并如实声明已盘点；非空器件页至少有一个功能模块框。
所有标签/端口/电源标记的可见文字必须计入 texts，内部脚名也需提取或明确缺测。
不能为了通过而把未知边界写成0或把 coverage 标成complete。快照必须来自本轮真实回读。

严格模式缺证据/不完整返回2，有阻塞候选返回1，只有info级贴边接触返回0（`status=info_only`，
`--fail-on-info` 可改回1），无候选返回0；electrical_verified 与 visual_verified 始终为false。
0仅说明输入范围内未找到候选，功能分区用途、页面数合理性、文字测量准确性和实际看图仍需
单独验收。coverage 保留输入声明，geometry_scope 描述算法范围。`status=review_required`
不等于电气错误，`no_candidates` 也不等于视觉合格。
不同网络的正长度共线重叠新增 different_named_wires_collinear_overlap 候选；端点接触不算重叠，
同网线树语义和真实短路仍需宿主检查。容差从实际网格推导，禁止为了过检随意放大。

严格模式中，每个 label_anchors 项提供 text_id，指向 texts 的实际标签文字边界；
每个 module_frames 项提供 title_text_id 和 purpose_text_id，分别指向框内两段不同文字。
缺少关联或关联对象不存在均为 incomplete，不能用标签锚点代替文字测量。
这些关联在普通模式为可选项；框/文本的内容语义和用途是否准确仍需实际检视。
`texts[].owner`、`title_block_owned` 与 `self_text_contact_tolerance` 是可选的分类声明，
不是strict通过条件，也不能弥补texts覆盖不足；未声明时行为与旧版一致。

严格模式要求每个模块 contains 明确列出成员，每个器件完整且唯一地归属于一个功能模块。
标签锚点和真实连接点也检查页边界；同点连接不豁免越框。框成员、标题和用途不以中心点替代完整边界。
