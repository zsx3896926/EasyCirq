# 原理图绘图执行方法（0.9）

先确定电气连接，再生成几何；让下一次任务复用角色、约束和失败处理，而不是上一次工程的绝对坐标。

## 1. 开始时只做一轮能力盘点

记录本机 CLI / Connector / EDA 版本、当前项目/页、可用的实测引脚/符号/文字接口。以本机 `--help` / typed action catalog 为准，不依据版本号猜接口；连接不可达时继续离线部分，并将真机写入/回读标 BLOCKED。不要反复探测同一个失败通道。

能力按操作分别记录：

| 能力 | 缺失后的下一步 |
|---|---|
| 引脚、符号 bbox、朝向和器件身份 | 先测量，不能靠封装名估计符号几何 |
| 所有可见文字的 bbox | 保留可测子集；缺的类别逐项列出，用官方导出人工复核，不声称完整自动检查 |
| 自动线名显示控制 | 先在隔离测试页验证“网络名仍保留、只隐藏显示”；不支持时重画局部直连，减少额外标签，不删除网络名冒充修复 |
| 受保护的移动/重连/回读 | 按官方 typed 工具局部执行；不要跨过工具限制使用任意 JS |
| 离线 layout-plan / sheet-plan | 用实测候选与模板；不能为了调用成功丢弃反馈路径、改成全标签或自动加页 |

## 2. 用拓扑决定空间

1. 列出主信号链、辅助供电/参考、反馈回路、外部接口。器件仅归属一个功能模块，模块之间列出实际网络。
2. 用 [模板](schematic-recipes.md) 绑定角色到实际位号/引脚。先确认符号的正反相端、B/C/E、IN/OUT/GND 等真实映射，再实例化相对布局；器件更换或旋转后重测。
3. 以核心器件为局部原点。外围器件按它服务的引脚摆放：输入侧放分压/输入电阻，输出侧放驱动，反馈留专用绕行通道，去耦靠电源脚。间距取实测符号及所有文字外包框加留白，不能只取 anchor 间距。
4. 同一功能区内的短连接优先直连；分压中点到输入、输出到反馈电阻再回输入，图上应能跟着导线走。输出网络分支与反馈关系由真实 netlist 校验，不通过模板自动决定。
5. 候选模块尺寸确定后才装页。简单检测电路先试“主信号链一行，供电/参考辅助行”，再试两行阅读顺序；不预先画四个等宽竖框。局部反馈不能为了框对齐被拆开。
6. 模块外包框包含器件、所有文字、导线/标记，再加标题、用途和边距生成框。整页留白为阅读服务；不为了填满纸张拉长导线，也不把主链挤在上方狭窄条带。

已有布局管线使用 [布局引擎](schematic-layout-engine.md)。其预览是简化符号，非官方工程导出；候选失败时不能拿这张预览交付为实际完成。

## 3. 一个模块闭环后再复制

先做最有代表性的模块，执行“候选 → 局部写入 → pin-net 回读 → 官方导图局部复核”。将自动线名与显式标签叠印、位号压值、输入标记压引脚名等问题在这个阶段暴露。样板尚未过关，不批量复制到另一通道。

对每次失败只记录：对象 ID、预期、实际、证据、改变了哪个参数。一次只修对应原因；同一种机制两次失败就改变方法，例如从旗标堆叠改为直接连线，从等宽分区改为内容尺寸装页。该次数是防止盲重试的默认策略，并不是两次就向用户宣布无法完成。

修改前固定项目/页和快照哈希。移动与重连使用执行器的受保护计划；移动器件后旧线不能留在原位。写入部分失败/超时先回读并只补差量，不全页删除重建。身份/连线/布局分别对比，保留无关模块。

## 4. 文字检查接入真实导出

优先收集官方 API 的实测 bbox，保留原始响应。例如历史测量载荷格式：

```json
{"count":1,"items":[{"id":"text-id","bbox":[0,0,20,10],"content":"OUT","parentId":"wire-id"}],"unmeasured":[],"coverage":{"designators":false,"values":false,"pin_names":false,"net_labels":true,"wire_names":false,"free_text":false,"title_block":false}}
```

`coverage` 的七类只有实际完整采集才填 true；没有该类对象也要通过页清单核对，不能因数组为空就填 true。自动导线网名和符号内引脚名常不在属性/普通文字清单中。零面积 bbox 不等于隐藏；仅有明确 `visible:false` 才排除。

```bash
python scripts/sch_text_audit.py visible-text-bboxes.json --strict --out text-audit.json
```

返回 2 表示覆盖不全或输入无效；1 表示文字冲突候选；0 仅表示该测量集合通过。`text_tight` 是小于 `--gap`（默认源坐标 2 单位）的候选，边界相接与真实重叠分开。不得把 bbox 候选直接宣称为像素重叠，须看局部官方图。该脚本不检查文字与导线/符号关系，后者交给完整几何检查及看图。

缺少某类实测文字时，不能靠伪造宽度补齐。官方图中仍看不清则保留未验收；已看清的人工复核可记录单独结果，不能把自动检查改成 PASS。

### 自动线名与显式标签重复

EasyEDA 会为已命名网络在导线上画网名，netflag/netport 的网名又是符号自身文字；这两类都不在
`visible_text.bboxes` 里。实际重复的三种来源：

1. 同一节点既放了 netflag/netport，又加了同名的 net_label；
2. 导线自动网名与附近的显式 net_label 同时显示；
3. 旧布局遗留、已无导线绑定的游离标签（可能连网表都不再引用）。

处理顺序：先用 `sch read`/netlist 确认该节点的真实网名与绑定；同一节点只保留一种表示
（跨区信号用 netport/netflag，局部直连不用标签）；重复的显式标签用官方 typed 删除或
`sch text.move` 移开，不能靠隐藏显示冒充修复；游离标签先确认它是否仍绑定网络，未绑定才
删除，并在记录中写明锚点、网名和判定依据。`sch check` 的 `duplicate-net-marker` 与
`sch_layout_check.py` 的 `duplicate_net_text/unanchored_net_text/unowned_visible_text`
分别覆盖电气与渲染两层。

## 6. 回读→实测文字→几何验收

官方导出 SVG 后先测全部渲染文字，再构建严格几何输入：

```bash
easyeda sch list --include-bbox --include-pins --include-wires \
  --include-page-primitives --page <page> > list.json
easyeda sch sheet-geometry --from-svg page.svg --json > sheet.json
python scripts/svg_text_bbox.py page.svg --out svg-text.json
python scripts/layout_from_easyeda.py --list list.json \
  --visible-text visible-text.json --sheet-geometry sheet.json \
  --rendered-text svg-text.json --min-text-wire-clearance 5 \
  --expect-rotation GND=0 --expect-rotation +5V=0 --out layout.json
python scripts/sch_layout_check.py layout.json --strict --out layout-check.json
python scripts/pin_net_intent_check.py docs/netlist-intent.json sch-read.json \
  --out pin-net-diff.json
```

`pin_net_intent_check.py` 按物理引脚连通组比较设计意图与 `easyeda sch read`，不比较
网名拼写；极性器件的功能脚名用组件内 `pinMap` 落到实际脚号，缺映射按输入无效处理，
不猜脚号。

`--out` 由 Python 以 UTF-8 落盘；PowerShell 的 `>` 重定向可能把中文按控制台代码页写出，
证据文件不要用 shell 重定向生成。

`visible_text.bboxes` 不是完整文字清单；同页 72 条与 SVG 实际 134 条文字的差值包括图框
行列号、图签字段、符号内脚名/脚号、netflag 网名。没有渲染测量时只能报告覆盖不足，不能
用 API 子集标 complete。适配器把无法归属的可见文字标 `unowned`，这正是“图上有一个名字，
但 API 和网表都不认识它”的检测口。

验收顺序仍是：pin-net/网表 → 原生 `sch check`/`gate`/DRC → 渲染文字与几何 → 官方整页
和局部图 → 保存重开。任何一层 PASS 都不能替代另一层；`info_only` 只表示没有阻塞候选，
不表示图面已合格。

### 2026-10-26 真实结果（EasyEDA Pro 4.1.78 / easyeda-agent 1.15.0）

- `photo-led-5v-20261026` P1：v18 编号 1→4 按阅读顺序、标题左上、图签重复消除；
  137 条渲染文字无 text-text overlap，R3 Name 与 zone2 purpose 的 blocking 接触已修；
  strict 只剩 3 条有宿主证据的无结点交叉 hint + 3 条 5 raw 内贴线 hint。
- 7 个反向旗：**不要原地旋转修**。按桩方向重建 flag 虽能让原生 `reversedNetFlags`
  归零，但会产生竖排电源/地文字并引入新的 blocking 文字接触；本项目已回退到
  rot=0 的 v18，保留 7 条原生 reversed 作为已知限制。正确修法是改桩线走向或
  数据驱动 compose。
- BOM：项目本地 MPN→C 号映射可把 enrichment 从 0/15 提升到 15/15；
  `bom_cnumber_check.py` 对 RV1=10kΩ 及全部 15 行 pass（库存/价格未核对）。
  SCH↔PCB：PCB1 已 linked 但 0 器件，BLOCKED。
- `ne555-blinker-1hz-20261026` P1：10 器件/7 网，gate PASS，pin-net intent match，
  save→reload 保持；残留为 5 个竖排电源/地标记、3 处文字/本体接触、无 purpose 文字。
- `ams1117-3v3-20261026` P1：6 器件/3 网，gate PASS，pin-net intent match，
  save→reload 保持；残留为 8 个竖排标记、22µF 陶瓷输出电容的稳定性未验证、
  无 purpose 文字、未做负载/热测试。
- 因此三张图都没有标成 `eda-verified`；当前证据等级是“真实写入/保存重开/导图，
  仍有已列视觉或选型残留”。竖排标记来自水平管脚上的 flag 方向；要全水平需
  逐脚改成短桩+旋转 0 的 flag，不能靠隐藏文字。

**水平管脚全水平 flag 的可复用做法（2026-10-27 实测）**：`sch connect --pin R1:1 --direction left` 会在水平管脚上生成 rotation 90/270 的 netflag，文字竖排；`sch modify` 不能改 netflag（仅元件类型可用）。可删掉旧 flag、保留/延长桩线成 L 形到管脚上方或下方，再用 `sch netflag --kind power|gnd --net <name> --x <end> --y <end> --rotation 0` 放在桩线端点；GND 放在下方、+5V 放在上方。移动后必须重跑 `sch check` 与官方导图，确认不是把竖排换成了倒置接地。

**先写 frame 元数据，再写 frame（2026-10-27 反哺）**：`sch frame apply` 每个 frame 只创建一个 `title` 文本，而 `sch_layout_check.py --strict` 要求 `order`、`title_text_id` 和**不同的** `purpose_text_id`。生成流程必须先在 frame plan 中填 `order`、`title`、`purpose`，运行：

```bash
python scripts/sch_frame_meta_check.py --plan frames.json --json
```

缺 `purpose_text_id` 默认 `blocked`（退出 2），不能先写 frame 再在 strict 阶段才发现；若当前执行器确实无法单独创建 purpose 文本，只能显式 `--allow-title-only` 得到 `review` 并保持 `strict_layout_complete=false`，报告写“电气检查通过、布局检查不完整”，不能写“原理图全面验收通过”。示例见 `assets/schematic-frame-plan.example.json`。上述 2026-10-27 实测证据在外部双路按键 LED 任务工作区，未随本仓库提交。

- 平台限制：free text 的 `move/setState/SDK delete` 不持久，删除需 `sch prim-delete`；
  新 free text 必须 `alignMode=2` 才左对齐；titleblock 的可见 Drawed 字段会与
  sheet 属性各渲染一次，填作者会产生两处重复；typed API 当前没有自由文本创建入口。

## 5. 从项目经验晋升为模板

经验必须有可复用资产：角色/连接条件、相对位置约束、实测输入、失败样例、成功证据和失效条件。不得只追加“下次注意”。

模板验证分三级：`candidate`（只有方法）、`offline-tested`（实际跑过离线输入）、`eda-verified`（指定版本下写入、官方导图、连接与保存重开证据齐全）。新符号/新朝向/新工具版本需要复核受影响能力，不能继承旧工程绝对坐标和视觉结论。

0.9 的固定任务是 555 闪灯、光控 LED、稳压电源；必须用不同符号尺寸或引脚朝向检验可迁移性。记录首个候选是否可用、局部返工次数、重复机制、实际官方图结果。单元测试数量、DRC 的 PASS、简化预览都不替代这些指标。
