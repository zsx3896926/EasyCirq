# 确定性设计引擎：IR、几何审计与标签规划

`scripts/design_engine/` 是离线、stdlib-only 的确定性层，用于把真实 EDA 回读变成可复核的 IR、覆盖报告、问题和可应用计划。它**不连接 EDA、不写工程、不下单**；执行仍由 `eda_exec.py` 或 easyeda-agent 的受控命令完成。

适用场景：真实回读后的几何/身份审计；纯排版前后的差异与网表身份比较；Designator/Name 标签的确定性重排候选；PCB 板框、焊盘、走线连通和原生 DRC 的独立复核。仅做方案或没有真实回读时，不启动本引擎。

## 1. 输入：同一批次的证据包

一个 bundle 是同一工程、同一页、同一会话捕获的文件目录。当前适配器读取：

| 文件 | 用途 | 缺失时 |
|---|---|---|
| `sch-list-full.json` | 器件本体 bbox、引脚 x/y/net/NC、可见属性、导线分段 | 不能构建原理图 IR |
| `sch-connectivity.json` | 网络、连接、pin/net 关系 | 退化为从引脚表推导，标记 `partial` |
| `sch-designator-geometry.json` | 原生 SDK 量取的位号文字 bbox | 位号退回 SVG/字体度量 |
| `sch-baseline.svg` | 全部可见文字的锚点、字号、字体、旋转 | 文字覆盖不完整 |
| `sheet-geometry.json` | 图幅、内框、图签矩形、keepout | 图签/越界检查降级 |
| `sch-titleblock.json` | 图签字段与可见性 | 字段缺省 |
| `sch-text-list.json` | 独立文字图元计数（本批次为 0） | 仍可从 SVG 读文字 |
| `sch-clusters.json` | L1 诊断组；只作候选分组，不当作功能区 | 无组 |
| `pcb-dump.json` | 板框、器件、焊盘、走线、过孔、铺铜 | 不能构建 PCB IR |
| `pcb-drc.json` | 原生 DRC 逐条违规 | DRC 检查标记 absent |
| `pcb-check.json` | DFM 文本摘要 | DFM 标记 absent |

同一页的表格和几何必须来自同一批次；页/板 UUID 漂移、快照截断、字段不可读都使对应覆盖变为 `partial` 或 `absent`。`load_json_tolerant` 只修复“有效 JSON 中夹了一行 CLI 噪声”的捕获问题，并在 `source.notes` 记录被删除的行；它不会修复截断的 JSON，也不会把文本摘要升级成几何。

## 2. 规范 IR

`design_engine/ir.py` 定义 `design-engine-ir/v1`。关键规则：

- 电气层：`components[].pins`（物理脚号、名称、net、NC、原生 primitive id）、`nets`、`connections`；布局层：`placement`、`body_bbox`、`attributes[].bbox`、`wires`、`labels`、`net_labels`、`texts`；两层分开保存。
- `components[].native`、`pins[].native`、`attributes[].native` 保留原对象，未知字段不丢。
- 重复物理脚号（USB 壳脚等）保留为多个 pin 实体，`duplicate_pin_numbers` 记录计数，绝不按编号去重。
- 同一 `designator` 重复、连接指向未知网络、pin id 重复时，`validate_ir` 明确失败，不猜。
- 网络标签（wire name）是 `pagePrimitives.attributes[Key=Name]` 且 `ParentPrimitiveId` 属于导线；它是 `net_labels`，不是器件属性。把它丢掉会把正常导线端误报成悬空。
- 0 长度导线在 IR 中保留（`zero_length_wires`），只在可绘制几何中排除；布局代码不得顺手清理。
- 坐标单位显式：原理图为 `sch_unit`（0.01 inch，100 unit = 1 inch = 25.4 mm）；PCB dump 为 mil。SVG 的 `(x, -y)` 到原理图 `(x, y)` 只在 `parse_svg_texts` 中转换，其他位置不猜。

## 3. 覆盖与门禁

覆盖状态只有 `complete` / `partial` / `absent`。`audit` 只有在所有必需覆盖为 `complete` 且没有硬问题时才返回 `pass`；有硬问题时 `blocked`；覆盖不足时 `incomplete`。`incomplete` 不是通过，也不是“没问题”。

- 硬问题（`hard`）：器件本体重叠、文字重叠、文字压到无关器件本体、导线穿无关本体/文字、越页、压图签、悬空导线端点、同一连接点多个网络、网名标签与所属导线不同名、pin 表与 connectivity 不一致。
- 建议（`advisory`）：紧间距、off-grid、未声明分区框、不同网导线交叉、网络标签互相重叠、连接器本体越过板框（需机械确认）。
- `electrical_verified` 与 `visual_verified` 永远为 `false`：引擎只证明它测量到的几何/身份，不替代原生网表、ERC、DRC 和人工看图。

## 4. 命令

在 `design-hardware/scripts/` 下运行：

```bash
python design_engine_cli.py ingest --bundle <bundle> --out ir.json --json
python design_engine_cli.py audit --ir ir.json --out audit.json
python design_engine_cli.py plan-labels --ir ir.json --out plan.json --moves-dir moves/
python design_engine_cli.py verify-plan --ir ir.json --plan plan.json --out verify.json
python design_engine_cli.py compare --before before.json --after after.json --out diff.json
python design_engine_cli.py templates --list
python design_engine_cli.py route --ir ir.json --start 120,500 --end 400,500 --net NODE
python design_engine_cli.py pack --ir ir.json --allow-groups --out pack.json
python design_engine_cli.py pcb-ingest --bundle <bundle> --out pcb-ir.json
python design_engine_cli.py pcb-audit --bundle <bundle> --sch-ir ir.json --out pcb-audit.json
```

退出码：`0` 无候选/身份 match；`1` 有 review/blocked/几何不足；`2` 参数、IO 或 schema 错误。

### 4.1 标签计划

`plan-labels` 只移动 **Designator/Name** 属性（easyeda-agent 的 `sch attribute-move` 只支持这两类）。每个候选位置都在当前 IR 副本上检查：页内、图签、其他器件本体、其他文字、网络标签、导线；按确定性的环搜索取第一个合法位置，并重新审计后再处理下一个问题。净标签和网络旗形属于导线/符号，移动锚点会脱离所属对象，因此只报告 `unplanned`，不伪造坐标。

计划是声明式的：

```json
{"op":"move_attribute","attribute_id":"attr:...","primitive_id":"...",
 "from":{"x":850,"y":545},"to":{"x":830,"y":545},
 "reason":"text_overlap","finding_ids":["finding:text_overlap:..."]}
```

`--moves-dir` 生成 `sch attribute-move --from` 所需的 JSON：`projectUuid`、`documentUuid`、`primitiveId`、`x`、`y`、`expected`（完整原始属性记录）。应用后必须重新回读、重新 `audit`、重新导出图；计划里的模拟结果不是 EDA 验收。

### 4.2 前后比较

`compare` 分开报告：

- 电气身份：器件增删、物理脚增删、pin-net 变化、网络集合。纯排版要求全部 `match`。
- 布局变化：器件位置/旋转/镜像、属性位置/文本、导线数量。
- `electrical_verified=false`：这是从导出表推导的身份，不替代 `netlist_diff.py` 的原生网表门禁。

### 4.3 局部正交连线（S05）

`route` 在 5 unit 网格上做正交 A*，把器件本体、非页框文字、网络标签/旗形、不同网导线按 2 unit 间隙设为障碍；同网导线允许重叠。端点若是 0 长度连接，返回 `zero_length` 并保留，不转成可见线。

输出是候选折线，`validate_route` 会独立检查：不穿器件/文字、不碰不同网导线、不出页。它**不**判定 T 形结点、交叉点、短路或电气连通；这些仍需编辑器回读与网表 diff。找不到路径时返回 `no_solution`，不缩小文字、不删对象、不改网名。

### 4.4 模块装箱与分页（S08）

`pack` 把每个模块视为刚体，只平移，不旋转、不缩放、不改内部画法。按给定顺序或面积降序做“从左到右、从上到下”的货架装箱，避开图签，超过页高自动分页；单模块大于页面时返回 `unsolved`，不通过放大板/缩字/删模块“解决”。

`sch-clusters.json` 的 L1 组是诊断分组，不是声明功能区；默认拒绝装箱。只有显式 `--allow-groups` 才把它们当候选，并在结果中保留 `allow_diagnostic_groups: true`。

### 4.5 PCB 审计

`pcb-audit` 检查板框 bbox 包含、同层器件本体重叠、焊盘中心越框、pin/pad 逐脚对账、走线/过孔连通和原生 DRC 身份。

- 连接器本体越过板框是 `advisory`，因为 USB-C 等连接器常合法外伸；焊盘中心越框才是硬问题。
- 走线连通按 net + layer 建图：焊盘/过孔/线段按实际几何距离合并；`layer=12` 与过孔视为跨层。T 形连接按点到线段距离处理。
- 有铺铜的网络标记 `not_checked`：filled polygon 含孤岛和热焊盘，简化成实心平面会伪造“已连通”。因此 GND 的铺铜连通性不在本引擎结论内。
- `pcb-drc.json` 的每一条违规按 `rule/objType/net/layer/x/y/objs` 保留身份，不按类别数量比较。

## 5. 常用画法模板

`design_engine/templates.py` 提供 12 类：电源入口、LDO、Buck、MCU 最小系统、晶振、复位监控、USB-C 取电、I2C 传感器、分压采样、运放/比较器、MOS 负载、RS485/CAN。

模板把**物理脚号**绑定到角色；`bind_template` 要求声明的脚号真实存在于回读 pin 表，缺脚/多角色显式失败，不按型号字符串猜。`instantiate_plan` 只做相对候选位置与硬重叠检查，`eeada_apply` 恒为 `NOT RUN`。模板本身是 `E3` 方法数据，不是某块已画完并验证的板。

## 6. 已知边界

- 不检查：原生网表/ERC、导线结点与短路的完整拓扑、铺铜连通、阻抗/SI/EMC/热、丝印可读性、装配、制造文件、实物功能。
- 文字宽度：位号用原生 SDK bbox；其他可见文字在 Windows 上用 GDI 字体度量，其他平台用保守字宽表。两者都标记来源，不冒充原生 bbox。
- SVG 只用于文字锚点与字号/字体，不把图形轮廓当成可编辑图元。
- 没有实时 EDA 连接时，任何 `eeada_apply` / `visual_review` 保持 `NOT RUN`；不得用离线模拟、截图或计划文件代替。
- PCB 的 `pcb-check.json` 是人类摘要，只做参考；DFM 结论以当前工具和实际订单工艺为准。

## 7. 与现有脚本的关系

- `eda_exec.py`：受控读写执行器；本引擎不替代它。
- `layout_from_snapshot.py`：把 `eda_exec` 快照转成 `sch_layout_check.py` 输入；现在会在快照带 `parts[].bbox` / `texts[].bbox` 时输出真实 `components/texts`，否则在 `coverage` 中明示缺失，检查器返回 `incomplete`。
- `sch_layout_check.py`：矩形/折线候选检查器；新增 `coverage` 字段后，不再把“没读到几何”误报成 `no_candidates`。
- `netlist_diff.py`：原生网表门禁；纯排版的最终电气验收仍以它为准。
