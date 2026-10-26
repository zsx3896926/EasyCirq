# EDA真实执行契约

制造规则写入遵循 [生产规则接入](jlc-production.md)：先读现有规则和当前执行器能力，再将适用工艺映射为真实支持的字段/对象，保留有效的更严格规则并回读；不编造导入厂规、DFM上传或下单命令。无法表达的条件列人工/几何检查，不宣称已被DRC覆盖。

本文件描述“怎样把工程意图变成真实画布动作并回读”。它不是某个版本的万能命令表；命令、参数和返回字段一律以当前客户端的 `--help` 与 `doc api` 为准。

## 常见陷阱（使用 easyeda-agent CLI 时）

`easyeda-agent`（v1.14.0）的页面/文档语义与前台焦点、引擎缓存强相关；遇到异常先查 [工具陷阱](tool-gotchas.md)，再按本节规则重试。本文件讲通用执行契约，不重复该版本的具体坑。

- **前台与页面**：页面类命令作用于前台文档；非活动页数据可能变浅。能传 `--page` 或 `--doc` 就显式传，不依赖当前焦点。
- **staleRisk**：回执带 `staleRisk` 时不得作为权威证据；执行 `save` → `easyeda doc reload` → 重新回读。
- **证据落盘**：完整 JSON 先用 `>` 落盘再摘要，记录命令、退出码、CLI/daemon/EDA 版本与文件 SHA-256；扩展名 `.json` 不代表内容是 JSON，解析失败按不可用处理。

## 0. 先判断执行能力，不把“装了软件”当成“能改工程”

按下面四层分别判断，任何一层不成立都不能宣称可执行：

| 层 | 检查 | 成立依据 | 不成立时 |
|---|---|---|---|
| 工具存在 | 找到 `lceda-pro` 可执行文件 | `--exe`、`LCEDA_PRO_EXE`、PATH 或常见安装目录命中 | 只做方案/离线文件；给最小安装或路径信息，不甩整页文档 |
| 工具连通 | `lceda-pro doctor` | `connected:true`、`versionMatch:true`、`resultChannel:true` | 启动客户端/检查端点；不要把命令存在当成已连通 |
| 工程可读 | 打开目标工程并读取工程/图页/器件 | 回读到 project、schematic、page、parts | 检查路径、登录、窗口、工程是否被占用；不伪造工程路径 |
| 工程可写 | 在**已授权的副本**上执行一次可回滚写入并回读 | `apply` 的逐项 `verified` 与保存/重开结果 | 明确写“未验证可写”；只交付方案或约束，不说“已改好” |

推荐命令（在Skill目录下，所有输出为JSON）：

```bash
python scripts/eda_exec.py doctor
python scripts/eda_exec.py doctor --project /path/to/copy.eprj2
python scripts/eda_exec.py read --project /path/to/copy.eprj2 --schematic Demo --page-name P1
```

`doctor --project` 只读，不会写目标工程；`project_writable` 在未做写探针时必须是 `not_tested`，不能根据“工程能打开”推断可写。真正写入用 `apply`，并在**副本**上先 `--dry-run`。

## 1. 当前已验证的客户端与通道

2026-10-21 在本机 Windows 11 实测；2026-10-22/23 追加原理图文本图元、PCB 命令族与建板/布局/布线/板框探针（结论见下表与 `docs/evidence/`）：

- 客户端：嘉立创EDA专业版 `4.1.78.34f5b8d9`。
- 官方 CLI：`C:\Users\jlc\AppData\Local\Programs\lceda-pro\lceda-pro.exe`。
- 调用方式：`lceda-pro invoke --session <id> --ext-uuid eda --code-file <fixed.js>`。
- `--ext-uuid eda` 是独立脚本权限；执行 `ok:true` 只代表代码跑完，不代表业务成功。业务结果必须在代码内返回/抛错，并由回读确认。
- CLI 打开的会话当前为半离线（`isHalfOfflineMode:true`）。半离线可以完成真实读写/保存/网表/导图，但不能写成“全在线模式验收”；全在线结论只能来自用户自己的全在线 GUI 会话。
- 不操作用户正在使用的窗口；不关闭 `origin:"user"` 的会话。`eda_exec.py` 现在对 `read/apply/save/export/designators` 统一检查会话来源：`origin:"user"` 默认拒绝，只有显式 `--allow-user-session` 才继续；`close` 只自动关闭 `origin:"cli"`，未知来源必须 `--force`。
- 写入还要求客户端版本在已探测白名单（`4.1.78`）内；其他版本默认拒绝 `apply`，需显式 `--allow-unverified-version`。`doctor` 同时检查 `connected/versionMatch/resultChannel`。

`easyeda-agent` 或其他执行Skill若已存在，仍按其 `health`/`--help`/实际协议使用；本桥不覆盖它们，也不假设它们一定安装。没有 `easyeda` 命令时，不要编造 `easyeda health` 的输出。

## 2. 工程意图到动作的能力矩阵

以下“可执行”指官方 `eda` API 在 4.1.78 上可用，并且本桥有受控动作；不表示任意版本都一致。

| 工程意图 | 真实动作 | 本桥状态 | 回读/限制 |
|---|---|---|---|
| 放置真实器件 | `sch_PrimitiveComponent.create(device, x, y, ...)` | 可执行（`part`） | 必须用库搜索结果或完整身份；创建后异步提交，立即改属性会被丢弃 |
| 配置位号/属性 | `sch_PrimitiveComponent.modify(id, {designator,...})` | 可执行（`properties`） | 创建后至少等待约0.8s再改；回读 `designator/name/manufacturer/supplier/otherProperty` |
| 绑定封装/库身份 | `create` 传入库器件；回读 `component/symbol/footprint` | 可执行 | 不在本桥中“换封装”；换料必须核对 pin-pad，单列变更 |
| 连接物理引脚与网络 | `sch_PrimitiveWire.create(flatPoints, net)` | 可执行（`wire`） | 端点取自 `getAllPinsByPrimitiveId` 的实际 `x/y`；扁平坐标路径，不是 `[x,y]` 点数组；新器件提交前画线会失败 |
| 电源/地标记 | `sch_PrimitiveComponent.createNetFlag(type, net, x, y)` | 可执行（`net_flag`） | 同名标记已在别处时冲突，不复制第二个；先决定是否移动/复用 |
| 跨模块端口 | `sch_PrimitiveComponent.createNetPort(direction, net, x, y)` | 可执行（`net_port`） | 方向 IN/OUT/BI 从 `symbol.name`（`Netport-BI`）回读；同时核对 rotation/mirror |
| 工程级位号清单 | `designators` 遍历全部原理图页读取 part 位号 | 可执行（`designators`） | 扫描会切换自有 CLI 会话的活动页；返回 `complete/errors/duplicates`，用于 `apply --project-designators` |
| 删除图元 | `sch_PrimitiveWire.delete` / `sch_PrimitiveComponent.delete` | 可执行（`delete`，需 `--allow-delete`） | 必须带 `primitive_id` + 完整 `expected`：part=designator/component/x/y，net_flag=name/x/y，net_port=net/direction/x/y，wire=net；删除后回读确认不存在；不允许按位号模糊删除 |
| 快照完整性 | 每个 `safe()` 字段读取失败写入 `integrity.read_errors` | 已实现 | `status!=complete` 时 `apply` 拒绝对账/写入，`reopen-check` 不返回 match |
| 网络标签 | `sch_PrimitiveAttribute.createNetLabel(x, y, net)` | API可用，本桥不写网络标签 | 动作集没有 net_label；不要把它当作已实现的幂等写入 |
| 说明文字 | `sch_PrimitiveText.create/modify/delete` | 可执行（`text` / `text_modify`；delete 已接线） | 4.1.78 半离线实测：create 持久且渲染；delete 与 modify **仅内存生效**（save 返回 true 但重开复原），放错只能靠新副本重做；不要用装饰框冒充电气连接 |
| 修改已有工程 | 先 `read` 快照，再 `modify`/补缺失 | 可执行 | 以 `primitive_id`/`unique_id`/位号定位；身份不符即冲突，不重建 |
| 保存 | `sch_Document.save()` | 可执行 | 返回 `true` 仍需重开回读；保存成功不等于内容正确 |
| 导出图 | `sch_ManufactureData.getPngFile/getSvgFile` | 可执行 | 导出**活动文档**；`openDocument` 只开标签页，必须 `activateDocument(tabId)` 并回读当前文档UUID；多页SVG可能是zip；必须实际看图 |
| 导出网表 | `sch_ManufactureData.getNetlistFile('Protel2')` | 可执行 | 跟随活动文档；未激活目标页会导出旧页/工程级网表；用于核对物理脚-网络，内容必须与计划比对 |
| 原理图DRC | `sch_Drc.check(strict, false, true)` | 可执行，本桥暂未封装 | 阈值来自当前规则；DRC通过不替代连接回读/看图 |
| PCB 读/写 | `pcb read/apply/save/drc/export/reopen-check` | 已实现（beta） | 线/过孔/铜区边框/器件（flat ref、search）真机验证；铺铜填充不重算；DRC 仅布尔；导出 getter 返回空对象 |
| PCB 建板/导入 | `pcb import`、`DMT_Pcb.createPcb`、`DMT_Board.createBoard` | 建板可用；导入不可用 | `importChanges` 返回 true 但 0 物化（半离线）；导入与板框需 GUI 会话 |
| PCB 布局/布线 | `pcb layout`、`pcb route` | 可执行 | `autoLayout` 33/33；`autoRouting` 13–16/17，`failedNets` 必须逐条核对；success 标志不等于连通 |
| PCB 板框 | `pcb outline` | **不可用** | `pcb_PrimitiveLine.create` 拒绝 layer 11 的所有网络变体；需 GUI |
| 下单/采购/库存 | 无本桥动作 | 不支持 | 不做付费采购、生产下单或外部消息发送 |

`lceda-pro doc api` 可逐类查当前版本；常用类包括 `SCH_PrimitiveComponent`、`SCH_PrimitiveWire`、`SCH_PrimitiveAttribute`、`SCH_Document`、`SCH_ManufactureData`、`SCH_Drc`、`DMT_Schematic`、`DMT_SelectControl`、`DMT_Project`。不要凭旧教程写 `--fn runCliAgent`：4.1.78 的 `--fn` 只接受常量 `run`。

## 3. 写入流程：先读、再对账、只补差异

本桥的固定流程：

1. **读快照**：当前页的工程/图页身份、页面宽高、器件（含 `primitive_id/unique_id/designator/component/symbol/footprint/supplier_id`、`mirror/add_into_bom/add_into_pcb`）、引脚实际坐标、网络标识（含 `flag_type`）、端口（含 `direction`）、导线、计数。快照同时给出 `integrity.status/read_errors/pins_complete/components_consistent`；不完整快照不能进入写入。
2. **Python对账**：把计划的每一项与快照比较，得到 `skip / modify / create / conflict`。有冲突默认不写；只有显式 `--allow-partial` 才执行无冲突项。位号先在当前页查重，再按 `--project-designators` 的工程级清单查重；未提供清单时结果明确标 `designator_scope=page`，不能宣称已做工程级检查。
3. **冻结页身份**：`page.current` 或 `schematic_name` 在读取后解析为 `page_uuid`；before/apply/after 三次调用使用同一 `page_uuid`，写后核对页 UUID 与工程 UUID 未变化。`page.current` 不允许在写入阶段重新解析。
4. **受控动作**：只发送本文件定义的原语动作（创建器件/改位号位置/建网络标识/建端口/建导线），不发送用户JS。`modify_part` 带 `expected` 状态，目标漂移返回 `stale_target`；`create_part` 前检查位号占用，并认领同位置/同料号的 `R?` 孤儿。
5. **回读逐项验证**：重新读同一页，逐字段核对计划中的 `designator/unique_id/component/supplier/footprint/x/y/rotation/mirror/manufacturer/supplier/other_property/add_into_bom/add_into_pcb`，以及标记类型/端口方向；写入返回成功不算验证。回读 `R?` 时返回 `designator_not_applied`，不是 `part_not_found`。
6. **保存**：`apply --save` 仅在逐项 `verified` 时保存；保存返回失败必须作为失败报告。若计划没有写入动作，apply 不会顺手保存当前文档。独立的 `save` 子命令是显式人工保存，不代表该工程已经通过设计验证。
7. **重开**：关闭自有会话，重新打开工程，比较工程/页身份、器件全字段、重复位号、电源标记类型/几何、端口方向/几何、导线（含不可解析线）、属性；任一不可比较项（如斜线）强制 `mismatch`，不能宣称持久化完成。

示例计划见 [EDA计划示例](../assets/eda/plan-example.json)。坐标单位是当前原理图的画布单位（A4图页实测 `Width=1170, Height=825`），不是毫米/像素；必须从页面回读取值，不能写死。

```bash
python scripts/eda_exec.py designators --project /path/to/copy.eprj2 --output designators.json
python scripts/eda_exec.py apply --session <id> --plan plan.json --dry-run
python scripts/eda_exec.py apply --session <id> --plan plan.json --project-designators designators.json --save
python scripts/eda_exec.py read --session <id> --schematic Demo --page-name P1 --output snapshot.json
python scripts/eda_exec.py export --session <id> --schematic Demo --page-name P1 --kind png --output page.png --width 1600
python scripts/eda_exec.py export --session <id> --schematic Demo --page-name P1 --kind netlist --output page.net
python scripts/eda_exec.py close --session <id>
python scripts/eda_exec.py reopen-check --project /path/to/copy.eprj2 --snapshot snapshot.json --schematic Demo --page-name P1
```

临时 `--project` 会话在 `apply` 时必须带 `--save`，否则关闭会话会丢失未保存修改；工具会返回 `needs_save` 而不是悄悄丢弃。已有 `--session` 不会被隐式关闭。

页面选择必须能唯一解析到指定UUID/原理图与页名，或真实当前活动原理图页。请求 `current` 却无法读取活动原理图时返回 `page_not_found`；只给 `schematic_name` 而该原理图有多页时返回 `ambiguous_schematic_page`，不自动退回第一页，避免把写操作落到错误页面。

## 4. 中断、超时与重复执行

- **超时/无响应**：`apply` 的 invoke 超时后会尝试一次短回读，返回 `partial_unknown`（含 `partial_counts/partial_integrity`），不自动重放。调用方必须先 `read` 当前页，按 `unique_id/位号/网络` 查实际对象，再只补缺失项。不能整批重跑；重复 `create` 会制造重复器件/导线。
- **部分成功**：逐项看 `execution.results` 的 `ok/error` 与回读；已存在的对象保留，不为了“干净”删除无关正确内容。
- **用户在执行期间手动改图**：`read` 后快照带 `integrity`；写入时每个 `modify_part` 带 `expected`（位号/unique_id/坐标/旋转/镜像），目标漂移返回 `stale_target` 且不发送该动作。`create_part` 前再次检查同页位号占用。重开/切页后以当前页 UUID 为准，不能拿旧快照继续写。
- **重复执行同一需求**：对账会把已匹配项标 `skip`，只补差异；这是本桥的幂等边界。网络标签不在动作集内，本桥不写标签，也不把“未重复写标签”当作已验证。
- **打开页不等于激活页**：4.1.78 的 `openDocument` 返回 `tabId`；必须 `activateDocument(tabId)`，再回读 `getCurrentDocumentInfo().uuid` 与目标页一致。否则导图/网表会跟随旧的活动页，出现“文件名是目标页、内容是旧页”的假证据。未确认激活时应失败（`page_not_activated`），不要继续导出。
- **引脚旁走线**：新增导线不得从另一个引脚上穿过。F1 修订中 `U101-2(IO2)` 的竖直走线穿过 `U101-1(GND)`，编辑器把该段并入 GND，验证立即失败。连接前先用快照列出同器件所有引脚坐标，路径与任何其他引脚保持至少一个栅格。
- **创建后立即改属性/画线**：4.1.78 的渲染器异步提交新图元；本桥在新器件后等待约0.8s再 `modify`，在首批导线前额外等待约2.5s，并在创建后轮询位号直到生效。固定等待不是协议保证，超时后仍要先回读。
- **零长度导线不是垃圾**：4.1.78 的 `[x,y,x,y]` 零长度导线可能是引脚与网络端口/标记之间的实际连接图元；删除它会切断网络（F1 修订中 EN/RST/TXD/RXD 曾因此丢失）。清理前必须逐条确认该引脚仍有其他连接。重开比较不做几何解析，但会把零长度线的 `(net,x,y)` 集合纳入比较：删除、增补或改网都会强制 `mismatch`，不能再把零长线当作可忽略差异。斜线/多段非正交线进入 `unparsed_wires` 并强制 `mismatch`。
- **同网导线批量创建会被合并**：一次 apply 创建多条不相连的同网导线时，4.1.78 会把它们合并成一条折线并插入连接段/斜线，产生不可解析几何甚至假连接。重排或新增连接应逐条 apply（标记/端口 + 一条短导线到引脚），每条回读后再写下一條；不要用批量同网导线做重排。
- **保存后重开**：关闭自有会话再打开工程；比较工程/页 UUID、器件全字段（含 designator/mirror/manufacturer/add_into_bom/add_into_pcb）、重复位号、电源标记类型与几何、端口方向与几何、导线网名与段集合、属性。`primitive_id` 可能变化，不作为跨会话稳定键。

## 5. 对象身份与局部修改

- 稳定身份优先级：`unique_id`（若库/工程提供）→ 位号 → 实际位置（仅作辅助，不作为唯一依据）。本桥要求 `part` 操作提供 `designator` 或 `unique_id`，避免“同名/同封装”误改。
- **位号唯一性是工程级，不是单页级**：新增页复用其他页的 `R1/LED1` 会造成跨页冲突，网表/装配/BOM无法区分。先用 `designators --project <copy>` 扫描全部页，再用 `apply --project-designators designators.json` 对账；未提供工程清单时结果标 `designator_scope=page`，不能宣称工程级唯一。F1 页因此使用 `R101.../C101...` 号段。局部新增也要做同样的工程级检查。
- 保留：无关器件的 `primitive_id/unique_id/位号/库绑定/封装/锁定/已有导线`。本桥只对计划中明确列出的对象发 `modify`；不会批量重建页面。
- 冲突：位号存在但完整型号/供应商不符、同名网络标识在别处、同网导线端点相同但路径不同、同一计划 key 重复——一律 `conflict`，不猜。
- 迁移/换料：先核对完整MPN、封装、pin-pad映射；本桥不做自动替换，换料后必须重新读引脚并重画受影响连接。
- 位号/属性修改必须回读；创建返回的 `designator` 可能是 `R?`，以回读为准。

## 5.1 改图/重排的连接门禁

纯排版或局部改图前后各导出一次 Protel 网表，先跑确定性 diff：

```bash
python scripts/netlist_diff.py before.net after.net --output netlist-diff.json
```

`status=match` 才允许宣称“连接未变”。工具比较器件身份字段（位号/型号/封装/BOM/PCB/供应商料号）和物理引脚→网络映射，不比较坐标、线段或格式。**纯排版要求整个 diff 为 `match`**：器件增删、身份字段变化、引脚增删、改网都必须为 0；`pin_net_changed=0` 只说明没有改网，不能覆盖器件增删或字段变化。只有电气修订才允许逐条列出的白名单差异。无效输入（缺 `PROTEL NETLIST 2.0` 头、未闭合块、缺 DESIGNATOR/PARTTYPE/FOOTPRINT、未知器件、重复位号/网络、空网络、引脚多网）返回 `invalid`，不能作为验收证据。网表里的未连引脚在两侧都不出现，因此单靠网表不能证明 NC 状态；NC 需要快照/图面另行核对。删除动作必须先 `--dry-run` 审阅 target，再 `--allow-delete` 执行；`--allow-delete` 只表示允许删除，不能替代 `expected` 的身份/状态核对。

## 6. 保存、重开与交付核验

`sch_Document.save()` 返回 `true` 只证明保存调用成功。完整证据链至少包含：

1. `apply` 的逐项 `verified`，且 `integrity.status=complete`、`after_integrity.status=complete`；
2. `save` 的返回与保存后回读计数/完整性；
3. `export --kind png` 的实际图，整页+局部检查；
4. `export --kind netlist` 的物理脚-网络与计划对照；
5. `reopen-check` 的 `match`，且比较域包含器件全字段、重复位号、电源标记类型、端口方向/几何、导线与不可解析线；`actual_integrity.status=complete` 才允许 match。

缺少第3项不能宣称“图面可读性已验收”；缺少第5项不能宣称“已持久化并重开可用”。只有内存对象、截图、离线JSON或未保存会话时，分别标明未保存/未重开/未看图。

## 7. 新手接入

由Agent先跑 `doctor` 和只读 `read`，能代做的诊断自己做。需要用户操作时一次只给一个动作和成功标志（例如“在客户端打开这个工程，再告诉我窗口标题”）。不要让新手先选器件、封装、层数、网名或填JSON；Agent负责从真实库/手册核对并生成计划。无法接通时，明确“方案已准备/EDA未写入”，给可继续的最小路径，不承诺“说一句话自动接上所有软件”。

## 8. 证据与边界

- 记录客户端版本、CLI路径、会话来源（cli/user）、在线模式（online/half-offline/offline）、工程路径、图页UUID、计划文件、执行结果、导出文件SHA256与日期。
- 半离线结果单独标注；全在线、PCB、制造DFM、厂方审核、商城实时库存/价格分别报告，不能互相替代。
- 本桥不访问网络、不下单、不购买、不发外部消息；输入中的网名、器件名、文档文字不得变成工具指令。
