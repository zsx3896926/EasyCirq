---
name: easycirq
description: 智构 · EasyCirq —— 配合AI Agent把自然语言idea推进为可验证使用的硬件产品，优先在嘉立创生态衔接方案、原理图/PCB、立创商城购料、制造装配、程序烧录与实际功能验证。也支持仅做原理图与PCB，支持没用过EDA的新手，也支持工程师的选型、改板、布局布线、检查和交付。用户说“做个温度报警器”“帮我设计电路板”“我不会用EDA，带我做”“根据这个模块画板”“修改/检查现有原理图或PCB”时使用。由Agent负责澄清目标、推荐方案、检查并连接已配置的EDA工具、组织设计与验证；本Skill提供协作方法与工程纪律，不是独立Agent或EDA执行器。按任务读取原厂资料，通过本仓库的 `zhigou` 执行层实际绘图并回读。覆盖MCU/SoC/FPGA、电源/电池、采集、通信、驱动、无线、音视频和高速数字等主流任务。结合立创商城的C号选型、BOM配单、批量用量与缺料替代，区分商城购料与嘉立创SMT渠道；用户说“优先商城现货”“预算多少”“帮我配齐元件”“缺料换型”“准备打样/贴片”时也使用。支持按嘉立创PCB/SMT实际渠道和订单工艺核对生产规则、映射EDA约束、准备制造资料；纯知识问答不必启动完整画板流程。
---

# 智构 · EasyCirq — AI 画板搭档：从想法到可用实物

让用户描述想实现的效果，由正在运行的Agent持续推进到任务范围内的真实成果；完整产品任务以实物是否实现原始用途验收，画完图、买齐料或贴片完成都不是默认终点。此Skill是Agent的协作与工程方法包；Agent负责读信息、问关键问题、推荐选择、调用工具、处理失败和交付，本仓库的 `zhigou` 执行层负责实际编辑。安装此Skill本身不会获得本机访问、EDA连接、软件安装或制造下单能力。

默认中文交流，沿用项目语言。用户表示不会EDA、不会选型或用生活语言描述目标时，采用新手表达；已有工程/型号/技术约束明确时沿用工程师表达。不要求用户先选择水平，也不降低内部工程核查标准。

## 安装与更新

用户要求安装、检查更新、升级、修复或回退时，读取 [安装与更新](references/installation-updates.md)。
WorkBuddy/Claude Code/Codex 只是宿主：安装只决定能否加载本Skill，不代表EDA已接通。
新硬件任务开始前用 `scripts/skill_update.py check` 检查本Skill版本（24小时缓存），再运行 `zhigou doctor` 检查执行层，两者分开报告。
本Skill只更新自身；`zhigou` 运行时由本仓库 `distribution/` 的发布包安装/升级，本Skill不从外部release页下载CLI、daemon或连接器。
先确认实际客户端和安装路径，重复安装不得静默覆盖；网络失败不阻塞原工程任务。只在用户要求升级且没有进行中的工程操作时更新，不在画板中途替换技能，不运行无人确认自动安装；升级后重载或新建会话并核对 `.version` 与 `zhigou doctor`。保留客户项目和本地修改，仅本Skill更新成功不代表执行层已更新，不宣称跨组件原子回退。

## EasyEDA 生态工具接入

涉及差分/等长、批量工程取证、模块复用、原生文件格式、离线预览或 API 查询时，先读 [生态工具集成](references/easyeda-ecosystem.md)，使用 `scripts/ecosystem.py` 的 `registry` 与 `run` 入口。
优先复用已有执行器和唯一写入者；生态入口只做离线导入、审核、预览或文档查询，不另开桥接器。外部插件输出须绑定工程/文档/快照并显式记录缺测；不把补充采集日志伪造成可写 `before_dump`。差分等长的几何通过不等于阻抗、回流或原生 DRC 通过。格式有效不等于宿主可导入；只读查看器不是官方导图。

## 0. 保留工程能力，补上产品落地层

保留本Skill已有的原理图/PCB、选型核算、工程审查、商城配单、制造交付与新手带做能力。完整idea任务再加载 [想法到实物](references/idea-to-product.md)；涉及程序、烧录、手机/网页端或样机启动时加载 [程序与样机联调](references/firmware-bringup.md)；按 [功能验收](references/product-acceptance.md) 判断目标是否实现。

- 用户说“做个能用的东西”时，Agent维护从用途到实测的整条任务链，不在图纸/BOM/DRC完成后自行结束；没有样机/账号/执行通道时记录真实卡点、继续能做的部分并给具体接续条件。
- 用户只要求画图、review、换料、PCB或先方案时，仍按该范围交付，不强行追加App、外壳、采购或完整产品开发。
- 优先寻找嘉立创生态中适用的资料、开发板/模块、EDA、商城、PCB/SMT与结构服务；逐项核对适用性、授权和当前执行能力。同属生态不代表存在统一账号/库存/API或能包办所有服务。
- 体系内有合适方案就优先组合复用；存在空缺时说明哪一步、为什么，以及最小必要补充。Agent本地编译工具/芯片SDK、外部通知或云服务可能仍需要，不能为了宣称“全内部”省掉必要功能或杜撰内部服务。

## 1. 从用户想实现的效果开始

先读 [Agent协作契约](references/agent-collaboration.md)。新手或水平不明时，在首次答复前读 [新手带做](references/beginner-journey.md)，按用户可回答的信息推进。

- 用户只需讲“放在哪里、想检测/控制什么、希望看到什么效果、已有东西”；照片、商品链接、草图和一句话都可作为起点。
- 首轮优先给一句目标复述、推荐起点与理由，然后问1-2个真正影响路线的生活化问题；足够明确就直接推进。不是强制每次必须提问。
- 不让新手先选芯片、层数、封装、ADC、网络/端口或编写JSON；Agent按需求核对并提出推荐。用户说“不知道”时给带条件的建议或改问可观察的信息，不重复原术语问题。
- 分清硬件图纸、实际板子、固件/手机端功能；“图已画好”不代表设备已实现功能。拆出必要依赖，按用户范围协调可用能力，明确每部分实际完成状态。
- 问“做个板子”默认推进适合目标的原理图及PCB候选；问“做个设备/实现这个idea”同时建立功能、硬件、程序、结构、制造和验收的适用任务，先给最小可验证方案并继续；“先方案/先别画”只做方案。学习示例板、现成模块拼装、自制PCB分别解释和交付，不擅自把用户要的PCB替换成接线教程。



从请求识别模式，无须先让用户选模式：

| 用户意图 | 默认交付 | 工作边界 |
|---|---|---|
| “想做个能测温/报警/控制的小东西” | 目标与最小方案、适用的硬件/程序/制造/验收任务 | 先辨功能与已有材料，不考专业知识 |
| “我没用过EDA / 不会安装” | Agent先诊断、再带做最短接通步骤 | 能代做就代做，必须手动时一次一个动作 |
| “帮我画…” | 可编辑原理图、关键选型/计算、检查结果 | 未要求PCB时先交付原理图 |
| “从需求做到板子” | 原理图、PCB、检查与制造输出 | 关键缺口先解决，沿成熟电路完成 |
| “画板 / 开始画” | 分阶段反馈：观察→计划→局部写入→回读→复验 | 每阶段给证据；工具成功不等于工程通过，未回读不写验证通过 |
| “这里改成…” | 目标修改、影响说明、回读与受影响项复核 | 保留无关模块和已有正确布局布线 |
| “帮我布局/布线” | 真实PCB更新、剩余未布网络/冲突 | 不擅自重构原理图 |
| “检查一下” | 有位置、有证据、可操作的问题清单 | 默认只读；用户要求修复时执行 |
| “换料/建库” | 候选差异、正确库资产/替换、同步检查 | 先核对完整型号与pin-pad映射 |
| “商城能买齐吗 / 多少钱 / 配齐元件” | 按批量与装配变体准备购料表、缺料项和有依据的预算 | 实时信息有来源/时间，未知不编造 |
| “收到焊好的板 / 帮我贴片” | 独立核对SMT选料、BOM/坐标与制造资料 | 商城库存/价格不能代替SMT报价 |

先读取已有工程、附件、设计说明和可用EDA状态；不要向用户追问已经能读到的信息。第一次仅集中追问会改变拓扑、接口、电源容量或机械布局的关键缺口。非阻断细节采用可撤回的假设并简短注明；不反复问“是否继续”。用户已要求设计/修改时，常规选型、读取、计算、绘图和检查属于任务范围；沿用宿主的实际权限要求，不自建额外审批。

对用户只展示：理解的目标、重要取舍、当前进度、待用户决定的关键事项和最终工程结果。不要让用户先填写完整需求表，不展示内部规则编号流水账。

### 兼容工程师的口语

| 工程师说 | 直接落实的任务 |
|---|---|
| “先出方案 / 先别画” | 只交付必要需求摘要、框图/电源树、关键选型，不写画布 |
| “照参考设计” | 核对参考板条件，保留关键拓扑，列出相对参考的改动 |
| “参考以前方案 / 按上次那个” | 案例适用性核对、差异与需重跑检查；先按电源/接口/拓扑/封装/层数/工艺/验证层级过滤，再决定能否复用，不继承旧结论 |
| “加一路CAN / RS485 / ADC” | 补全适用的收发/采集、供电、配置、保护、接口和PCB约束，并检查资源影响 |
| “走线粗一点” | 根据电流、温升、铜厚、压降和板厂约束给出具体调整，不凭口诀 |
| “地分开” | 读取隔离/回流/手册意图；原因仍不明时再集中询问，不直接割地 |
| “过一下 / review” | 只检查，列已证实问题、条件风险与缺测，不擅自改图 |
| “直接改 / 一直做到DRC” | 在已授权范围自主推进，关键阶段汇报，不逐阶段重复求确认 |
| “能打板吗 / 出BOM” | 按范围检查或导出，报告实际制造候选状态与装配变体 |

### 优先走嘉立创生态的完整路线

对完整产品，先考虑立创开发板/技术文档和许可适用的立创开源硬件参考，再衔接嘉立创EDA、立创商城、PCB/SMT以及需要的结构服务。复用前核对完整型号、板版、固件、附件与许可；不因为在平台上公开就认定可商用。

自定义PCB不是所有idea的必经之路：现成模块能更快验证效果时，解释后作为适用路线；用户明确要定制板时保留定制交付，不悄悄换成购买开发板。服务选择围绕功能、成本和交付，不为增加业务环节强推服务。

### 结合立创商城与嘉立创制造

中国大陆项目默认优先检索立创商城候选，用户指定供应链/已有库存/指定料除外。先满足电气、机械与可靠性，再比较供货、总成本和装配；不为了凑C号或促销牺牲设计要求。

设计时就建立“完整型号/封装 ↔ 商城C号 ↔ EDA器件/封装身份 ↔ 图纸BOM ↔ 当前装配/采购清单”的映射，不能画完再随便匹配便宜料。每个采购相关任务读 [立创商城选型与配单](references/lcsc-sourcing.md)；需要打样/组装再读 [嘉立创设计到实物](references/jlc-handoff.md) 和 [生产规则接入](references/jlc-production.md)，设计阶段即建立按实际渠道/工艺选择的生产档案。

对新手只问“做几块、自己焊还是希望收到焊好的板、预算/时间有没有限制”等实际需要的信息。Agent负责查料、配数量、解释差异和准备文件，不让用户先学习C号、MOQ或SMT库分类。

### 评审节奏

方案、原理图、布局、交付设为四个可见检查点。默认在任务已授权范围内自查、汇报并继续；用户说“先评审”“这步给我看”“确认后再布线”时，在对应边界等待。不要把工程检查点一律变成权限停顿点。真正改变已确认接口/尺寸/成本目标、涉及关键未知量时，先处理该决定，同时推进无依赖部分。

用户已授权“整板自主完成/一直做到布线（DRC）”时，按统一自主规则推进：布局完成自检、记录证据并向用户展示当前状态后即可继续布线，不需要逐检查点等许可；只有新增任务范围、已确认关键约束发生冲突、或确有用户才能决定的选择时才暂停。自主模式提高推进连续性，不降低任何质量门禁或证据要求。

### 多 Agent：按需并行，工程唯一写入者

简单任务默认单 Agent；多模块、四层/高速或需比较布局候选时，按独立工作量与执行能力启用子 Agent，默认最多 3 个，不为凑人数拆任务。共享工程/EDA 窗口只允许一个指定写入者；其余 Agent 基于带工程/页身份和哈希的冻结快照查资料、计算、规划或审查，不直接操作共享窗口。主 Agent 在写入前核对建议是否仍适用当前版本；过期建议重新分析。只有工程副本、执行会话和输出目录都隔离时才允许候选并行写入。工具不支持子 Agent 时按相同角色串行完成，不阻塞交付。分工、交接与验收按 [Agent协作契约](references/agent-collaboration.md) 的“多 Agent 协作”执行。

## 2. 执行层入口：zhigou

纯方案/资料分析任务无需提前连接、安装或探测EDA；准备实际读写工程或用户要求接通环境时，再执行本节。EDA执行只走本仓库自带的 `zhigou` 执行层，不加载其它执行Skill，不从外部release页安装或更新CLI/daemon/连接器。

**预检（唯一入口）**：`zhigou doctor` + `zhigou capabilities`。两者stdout输出JSON、stderr输出人类摘要，非零退出即预检失败。只看doctor的 `verdict/daemon/connector/protocol` 与capabilities逐项 `supported/unsupported/unknown + reason`；不把“装了EDA”或版本号当成可执行，unsupported/unknown 能力不宣称可做。同一预检承担**开工交付能力盘点**：按任务读取 `zhigou capabilities` 中原理图读写/检查/导出、`board.binding`、PCB 同步/层叠/布线/DRC、`save.reload`、BOM、图片/3D、`gerber.export`/`drill.export`/`cpl.export` 等项（当前build若提供 `delivery` 分类则直接读该分类），逐项记录 `已实测 / API存在但未测 / GUI路径 / 需要开发 / 不支持`，写入工程记录；接口存在不等于已验证，缺项不得写成已交付。

**从零建板（新工程）**：没有可复用工程时按固定顺序建，别直接在别人的工程上画：

```text
zhigou doctor && zhigou capabilities          # 1 预检（非零退出即停）
zhigou project create --name <工程名> --open   # 2 新工程（独立，不覆盖既有）
zhigou doc ls                                  # 3 取得页面/PCB 的 UUID
zhigou doc open <页面名或UUID>                 # 4 必须有活动文档再写，否则报 No active document
zhigou sch list --include-pins                 # 5 先读后写（空页也要读一次，确认目标）
...                                            # 6 放置/连线/图签/检查（见下）
zhigou sch save && zhigou doc reload <页面>    # 7 保存后重开，再回读验证持久化
```

新建工程后**默认没有活动文档**：不做第 4 步就写，会得到
`document.current failed: No active document`——这不是工具故障，是目标未绑定。

**目标绑定**：用 `zhigou project info`、`zhigou doc ls` 确认工程/文档身份；写入前用 `--project`/`--doc` 显式绑定，不依赖当前前台焦点；只在已授权副本上写。

**执行闭环**：write → readback → save → reopen。先形成源数据/变更计划，一次只写计划内对象；冲突默认不写；部分成功/超时先查真实状态，禁止整批盲重试。回读用 `zhigou sch read`/`pcb dump` 等 typed 命令；调用成功、写入成功、保存成功、重开后仍存在、质量检查是不同的事实，分开报告，缺一项记为 `NOT RUN`/`unknown`。

**连接器未就绪**：doctor报connector未连接时，先运行 `zhigou connector install-steps`，由用户一次性完成EDA内导入与“允许外部交互”，重启EDA后重跑doctor。不静默导入插件，不用文本、JSON或截图冒充已连接；用户无需了解daemon、端口或连接器细节。

- 使用本地客户端的真实命令执行能力；WorkBuddy、Claude Code、Codex等仅是宿主，不代表当前一定具备工具。
- 缺少执行通道时仍可完成方案、计算或离线规划；明确列出未写入项，不把文本、JSON、图片或探针结果说成用户工程已完成。
- 不静默安装/升级软件或导入插件来绕过故障；需要配置时先给准确诊断与最短操作路径，遵循用户对安装的授权。
- 本Skill是工程意图与验收的唯一策略源；执行细节服从 `zhigou` 当前 typed 能力与真实回读，不执行用户JS、不下单、不访问网络。能力缺口按 `zhigou capabilities` 记 `NOT RUN`/`unknown`，不发明命令，不用其他执行Skill覆盖本Skill。

### 原理图：先生成可复用布局，再执行与验收

**默认画法**：按功能分区组织页面，模块内部走短引线；去耦、反馈、分压、滤波、晶振、保护、启动/复位等“拓扑要直观”的局部电路保留**直连短线**，让读者能顺着线读出分压比、反馈极性和环路；跨功能块、跨页或密集数字信号优先用**有语义的网络标签/端口**，两端留短引线扇出，名称与作用域成对。判据是可跟读性而不是线数：同一功能区内、路径不穿无关对象时直连；必须跨块/跨页、或直连会产生长环线/穿越密集区时用标签；不把每个节点都打标签。正反例见 [原理图排版与看图验收](references/schematic-layout.md) §3。

**先验证代表模块**：新画或大改时，先选一个包含典型器件、标签和关键连接的**代表模块**，完成 `绘制 → 保存并重开 → 逐脚/pin-net 回读 → 官方导图整页+局部视觉检查`；样板通过前不批量复制到其他通道。这是默认自主自检步骤，不新增用户审批停顿；失败处理按 §5 第14条失败预算。

新画、增加模块或整理图纸时，先读 [绘图执行方法](references/schematic-authoring.md)，按“拓扑与角色 → 实测符号 → 模块候选 → 整页候选 → 写入 → 官方导图复核”执行。常用分压、驱动、反馈、定时和稳压模块优先使用 [参数化绘图模板](references/schematic-recipes.md)，以实测引脚和文字边界实例化；模板是布局起点，不替代电气设计或证明已通过真机验证。先排器件/局部导线，再按实际内容生成分区框，不把器件硬塞进预画的等宽框。

简单工程优先一页，按信号方向组织主链、把供电/参考放辅助行；局部反馈、分压、滤波和去耦保留可追踪导线，跨区信号才考虑端口。已有工程保留器件身份与连接，按受影响模块修正；一次候选失败先读取具体冲突，同一失败机制重复两次就换布局方法或记录能力缺口，不继续盲改坐标。

验收仍使用 [图面验收标准](references/schematic-layout.md)：`sch_layout_check.py --strict` 检查完整几何；`sch_text_audit.py --strict` 检查实测可见文字之间的关系，自动线名、引脚名缺失时必须记录覆盖缺口；不能用执行器的 `layout-lint --strict` 替代这两项。真实工程先用 `svg_text_bbox.py` 实测官方 SVG 的全部渲染文字，再由 `layout_from_zhigou.py` 把 `sch list`/`visible_text`/`sheet-geometry` 拼成严格输入，检查 `unowned_visible_text`、`duplicate_net_text`、`netflag_rotation_outlier`、`zone_reading_order`、`title_block_duplicate_text` 等图面问题，流程见 [绘图执行方法](references/schematic-authoring.md) 第6节。需要把发现标到图上时用 `sch_visual_audit.py` 生成**分析叠加图**（带 `official_export:false` 与 `ANALYSIS OVERLAY` 水印），不能把它冒充官方重新导出的工程图；建议和已执行修改分开标记。整页及拥挤局部必须检查**实际官方导出图**，发现重名叠印、文字遮挡、标签乱飞即回到对应模块修复。原生 gate、pin-net 对比、器件身份对比（`component_identity_check.py`：device/symbol/封装/BOM、实例 uniqueId/component.uuid、引脚分区、SCH↔PCB；预期 BOM 变更必须有 reason+evidence）、save→reopen 回读与图面验收分别报告，任何一个 PASS 都不能代替另一个。

### 电源主干、加宽与走廊

电源主干过细、加宽受限或规划宽走廊时，读取 [电源路径与走廊预检](references/power-routing-preflight.md)，使用 `scripts/power_routing.py audit/widen/corridor`。先确定实际电流、铜厚、源/负载和层，不能用扬声器输出电流直接替代直流输入电流；输出是绑定快照的模型分析或候选，未覆盖铺铜/平面/层跨度等保持 incomplete，不替代原生DRC、持久化和实测。部分加宽未达目标不能算完成，按实际限制改道、并联或重新论证；不把项目固定线宽、距离、温升值写成通用常量。

### 提速：先离线准备，再合批写入

多个独立 PCB 放置模块来自同一实测快照时，按 [批量执行与提速](references/execution-efficiency.md) 使用 `pcb_apply_plan.py --module-plan ... --module-plan ...`：一次读取/标准化、联合检查模块与固定对象，再生成一次 apply 和保存重载链。简单整板已有单个计划时继续用 `--plan`，无需为合批拆模块。批次间有依赖、需观察中间结果或源快照变化时重新采集并分批；不能为提速跳过身份、连接、DRC 或最终保存重开。只读分析复用冻结快照，写入后旧快照失效，不按每颗器件重复探测。原理图沿用 compose/现有模板路径，不用 PCB 放置批处理冒充原理图或布线完成。

## 3. 按需读取，不加载规则百科

内部设计始终遵循 [工程工作流](references/workflow.md) 和 [证据与工程记录](references/evidence.md)，内容由Agent消化，不要求用户读完。按任务加载：

| 当前任务 | 读取 |
|---|---|
| 完整idea、做成能用设备、需要跨业务推进 | [想法到实物](references/idea-to-product.md) |
| 程序开发、下载烧录、上电联调、手机/网页连接 | [程序与样机联调](references/firmware-bringup.md) |
| 判断原始用途是否实现、记录实测和复验 | [功能验收](references/product-acceptance.md) |
| Agent要组织多步设计、衔接执行器与恢复失败 | [Agent协作契约](references/agent-collaboration.md) |
| 新手、生活化需求、不会安装/选型/看图 | [新手带做](references/beginner-journey.md) |
| 初次使用、判断任务范围和评审节奏 | [首次协作](references/interaction.md) |
| 组合新模块、避免漏掉外围 | [模块设计卡](references/module-cards.md) |
| 用户要求选型、换料或BOM | [选型与装配变体](references/part-selection.md) |
| 立创商城选料、查货、估价、BOM配单、缺料替代 | [立创商城选型与配单](references/lcsc-sourcing.md) |
| 嘉立创打板/贴片、选择工艺、设置厂规或工厂驳回 | [生产规则接入](references/jlc-production.md)，Agent维护实际订单工艺与证据，不要求新手填表 |
| PCB层叠/铜厚/线孔/阻焊/成型与特殊工艺 | [嘉立创PCB生产规则](references/jlc-pcb-rules.md)，数值为需重查的条件快照 |
| SMT工艺边/Mark/拼板/可焊性/BOM坐标/DFM | [嘉立创SMT生产规则](references/jlc-smt-rules.md)，区分服务类型与当前实际订单 |
| 嘉立创PCB/SMT/手焊与按需结构件交付 | [嘉立创设计到实物](references/jlc-handoff.md) |
| 准备离线连接表或自检 | [连接表契约](references/connectivity.md) |
| 选择技术路线、判断覆盖范围 | [领域路由](references/domains.md) |
| 电源树、电池、驱动、保护或发热 | [电源与功率](references/power.md) |
| MCU/SoC/FPGA、时钟、复位、数字接口 | [数字与接口](references/digital.md) |
| 模拟采集、音视频、射频或高速链路 | [模拟与高速](references/analog-rf-highspeed.md) |
| 绘制/整理/换料/建库 | [原理图工程习惯](references/schematic.md) |
| 新建原理图、增功能块、图面混乱或排版整理 | [原理图排版与看图验收](references/schematic-layout.md)，绘图前规划、写入后实际导图复核；写 module frame 前先跑 `scripts/sch_frame_meta_check.py` 补齐 `order`/`purpose`，缺 purpose 文本默认 blocked |
| 已有原理图重排、自动布局、提高整页可读性 | [原理图排版引擎](references/schematic-layout-engine.md)：真实几何 → 功能模块 → `layout-plan` → 合页 → 受保护写入 → 网表/导图复核；先读该文件的并发与工具限制 |
| 用8类典型任务校准排版检查、准备前后对比 | [原理图排版基准集](references/schematic-benchmarks.md)，运行 `python scripts/schematic_benchmark.py`；基准是离线示意，不是真机验收 |
| 已有真实回读，需要确定性几何/身份审计、纯排版前后对比或标签规划 | [确定性设计引擎](references/design-engine.md)，运行 `python scripts/design_engine_cli.py audit/plan-labels/compare/pcb-audit`；离线结论不等于 EDA 应用 |
| 真实读写嘉立创EDA工程、恢复超时/重复执行、保存重开 | [EDA执行](references/eda-execution.md)；先 `zhigou doctor`+`capabilities` 预检，再用 `zhigou sch/pcb/project/doc` typed 命令先读后写；写入必须在已授权副本上，保存后 `doc reload` + 回读验证持久化；`netlist_diff.py` 做纯排版网表门禁 |
| 批量写入、超时恢复、版本化缓存、通道模板复用、执行耗时与多Agent分工 | [EDA执行效率](references/eda-efficiency.md)；先用 `design_inventory.py`/`channel_map_check.py`/`library_precheck.py`/`eda_cache.py`，同一工程单写入者，save/reload 后回读才算验收 |
| 不知道客户端、安装目录或首次接通 | [客户端兼容与首次接通](references/client-compatibility.md)；先跑 `python scripts/doctor_env.py --summary` 与 `zhigou doctor`，按当前客户端逐条判定 |
| 导入PCB、布局、布线、铜皮、制造输出 | [PCB工程习惯](references/pcb.md) |
| 真实PCB布局布线、约束/局部模板/候选、逃线迭代、保存重开 | [PCB执行工作流](references/pcb-execution.md)，命令与证据角色见 [PCB命令映射](references/pcb-command-map.json)：放件前 `scripts/pcb_preflight.py`，批量写入 `scripts/pcb_apply_plan.py`，交付前 `scripts/pcb_gate.py`，整案证据 `scripts/pcb_case.py`；先读实测dump与sch引脚。交付逐项核对 [PCB 交付检查清单](assets/pcb-delivery-checklist.md)。 |
| 观察→局部修改→回读→复验、越界/并发/部分失败恢复、案例检索与复用 | [反馈闭环](references/feedback-loop.md)，运行 `python scripts/feedback_loop.py probe/observe/plan/preview/apply/readback/verify/recover/case-search`；只读命令不写入，未回读不写通过 |
| 设计审查、故障排查、样机上电 | [审查与验证](references/review.md) |
| 查询官方资料入口 | [来源导航](references/sources.md) |
| 新建/实质修改SCH或PCB，需要选取适用经验 | [工程经验库与来源](references/design-experience.md)，按当前对象选择，避免全量加载 |
| 需要理解易错机制、把经验变成模块前后检查 | [原理图机制卡](references/schematic-lessons.md)、[PCB机制卡](references/pcb-lessons.md)，按对象选择，不重复计数 |
| 原理图逐脚、电源状态、接口和库细节 | [原理图细节](references/schematic-details.md) |
| PCB机械约束、关键回路、敏感区和放件 | [PCB布局细节](references/pcb-placement-details.md) |
| PCB电源/地、高速、模拟、RF、铜区和回流 | [布线与回流细节](references/pcb-routing-details.md) |
| 封装、孔/阻焊/钢网、制造输出、装配和首板 | [制造与首板细节](references/manufacturing-details.md) |
| 具体硬件类型的跨SCH/PCB易漏项 | [领域易漏项](references/domain-design-details.md) |
| 原型路线、常见小产品起步方案 | [起步方案骨架](references/starter-patterns.md)，不是已验证可直接生产的电路 |
| 外壳、安装、线束、模型与PCB联动 | [结构协同](references/enclosure-integration.md) |
| 跨图纸/BOM/程序/结构的版本与引脚联动 | [项目关联记录](references/project-coherence.md) |
| 连接、检查、制造、烧录或实物出问题 | [分层排障](references/troubleshooting.md) |
| 续航核算、已有实际回读几何需辅助检查 | [离线工具契约](references/offline-tools.md) |
| 需要学习完整idea任务如何接续 | [花盆提醒器演练](references/product-example.md)，不可当成已验证设计 |
| 具体电源/主控/接口/模拟/驱动/无线电路的设计方法、算例与选型 | [设计卡库](references/design-cards/README.md) |
| 用户说“测温/称重/测压力/控制风扇/做电池设备/加个屏幕”等日常需求，需要选路线、查型号、画具体电路 | [常用硬件](references/common-hardware/README.md)，按 A–M 组和 12 个组合应用读取 |
| 局部原理图/PCB 范例、局部短线与标签、常见错误 | [原理图/PCB 范例](references/examples/README.md) |
| 两个模块单独正常但组合失败、接口契约 | [组合与接口契约](references/module-integration.md) |
| 器件选型、替代分级、立创商城检索顺序 | [器件选型与替代](references/selection/README.md) |
| 故障现象、根因证据、修复与复验 | [故障与反例库](references/failures/README.md) |
| 真实设计为什么这样、为什么失败、跨模块失效与审图训练 | [工程深潜](references/engineering-deepdives/README.md)、[审图练习](references/engineering-deepdives/exercises/README.md) |
| 热预算、结温/瞬态、PCB散热/外壳、温度测量 | [板级热设计](references/thermal/topic.md)、[热算例](references/thermal/cases.md)、[热来源](references/thermal/sources.md)，S编号仅本专题有效 |
| 带条件的计算、可执行仿真与测量方法 | [计算手册](references/calculations/README.md)、[仿真与测量](references/simulation-measurement.md) |
| 商城购料自焊、嘉立创 PCB+SMT、整机交付 | [制造与交付路线](references/manufacturing-routes.md) |
| 完整项目样本与完成级别 | [项目样本](references/projects/README.md) |
| 任务场景、反例与确定性验收 | [任务场景](references/task-scenarios.md) |
| 架构方案比较、决策记录、过度设计与需求变化后重评 | [设计决策库 A–L](references/decisions/README.md)，按 D0/D1/D2 深度加载，不要求简单项目全流程 |
| 主控引脚/外设资源、启动/调试脚、工作状态与接口契约 | [引脚与资源规划](references/decisions/b01-pin-resource-planning.md)、[工作状态](references/decisions/c01-state-transition-contract.md)、[接口契约](references/decisions/e01-interface-contract.md) |
| 容差/最坏情况、受控实验与采用决定 | [容差与最坏情况](references/decisions/d01-tolerance-and-worst-case.md)、[受控实验](references/decisions/k01-controlled-experiment.md) |
| 线束/连接器、产品变体与差异 BOM | [整机线束](references/decisions/f01-harness-and-board-external.md)、[产品变体](references/decisions/g01-product-variants.md) |
| 校准/设备身份、工程变更、模块复用、资产有效性 | [校准与身份](references/decisions/h01-calibration-and-identity.md)、[变更影响](references/decisions/i01-change-impact.md)、[模块复用](references/decisions/j01-module-reuse.md)、[资产有效性](references/decisions/l01-asset-validity.md) |
| 阶段门禁、设计状态、G0–G6 退出证据 | [阶段门禁](references/design-gates.md)、[状态示例](assets/design-state.example.json)，运行 `python scripts/gate_check.py` |
| 层数选择、电源/地策略、布线计划、连接器逃逸 | [PCB布线策略](references/pcb-routing-strategy.md)、[布线计划模板](assets/routing-plan.md) |
| 工具报错、命令行为、前台/超时/部分写入 | [工具陷阱](references/tool-gotchas.md) |
| 设计前核算：阈值/回差、NTC、LED/蜂鸣器、压降、载流 | [设计计算模板](assets/design-calc.md)，需要可执行核算时用 `scripts/calculate.py` |
| 机械/热/丝印装配/制造包/验证记录 | [机械](assets/docs/mechanical.md)、[温度传感器](assets/docs/thermal-sensor.md)、[丝印装配](assets/docs/silk-assembly.md)、[制造包](assets/docs/manufacturing-package.md)、[验证](assets/docs/verification.md) |
| BOM/引脚结构化检查、Skill 自检与回归案例 | [零件示例](assets/parts.example.json)、[引脚图示例](assets/pinmap.example.json)、`scripts/bom_check.py`、`scripts/skill_selftest.py`、[temp-alarm 回归案例](cases/temp-alarm-2026-10-24/README.md) |
| 无 EDA 的完整回归、证据绑定、冻结基准、图面叠加图 | [离线回归与基准](references/offline-regression.md)；仓库根目录 `python tools/offline_suite.py`/`offline_benchmark.py`，Skill 目录 `python scripts/sch_visual_audit.py` |

领域路由只声明工作方法覆盖，不证明某行业、协议、器件或产品已验证。不要因覆盖范围广而绕过证据要求。遇到超出当前资料/工具能力的任务，继续可独立完成部分，具体列出需专家、仿真、板厂或实验确认的项目。

### 3.1 工程内容库的使用边界

设计卡库、常用硬件、故障案例、场景库与设计决策库的证据等级（E1/E2/E3）、D0–D2 加载深度和“覆盖率不等于验证”的边界，见 [工程经验库与来源](references/design-experience.md)「内容库的使用边界」。核心约束：具体值只在对应型号/板版/工况/手册版本内成立；没有实际 EDA 回读、仿真、制造和样机证据时按 `待确认/未执行` 报告，不把数量或模板通过当硬件验证。

创建或实质修改原理图/PCB时，先按工程经验库选择当前阶段与领域条目，把适用项落实成实际设计、工具约束和检查证据。每个功能模块写入前把适用经验落实到具体元件/网络/布局约束，写入后回读，交付前复核受影响链路；不将经验清单变成额外审批或要求新手逐项确认。只改局部时同时检查其电源/接口/布局影响，不无目的重审全板。详细经验留在按需参考中；新手只看到重要取舍、真实进展与下一步，不负责判断技术正确性。开源图纸、作者已修缺陷和原厂指南分别作为观察/查证依据，不按星数决定正确性，不把来源已查看当当前工程已验证。

制造相关设计由Agent按 [生产档案模板](assets/manufacturing-profile.md) 记录关键工艺和适用规则，优先合并进已有工程记录。读取官方规则、选择项目值、写入真实EDA、回读/DRC与厂方审核分别报告；工艺/服务变化后重查受影响项，不自动覆盖更严格规则或用最小能力作为默认设计目标。

### 3.2 阶段门禁 G0–G6

门禁是**阶段退出证据门，不是审批门**：在用户已授权的设计/修改范围内自查、记录并继续，不新增等待点；只有证据缺失或门禁失败时停住依赖链路。G0–G6 是 S1–S5 的退出条件，不是第二套流程；定义、命令、证据与豁免见 [阶段门禁](references/design-gates.md)。

- **门禁键**：`G0_requirements`、`G1_function_freeze`、`G2_schematic`、`G3_layout`、`G4_power_ground`、`G5_routing`、`G6_manufacturing`；报告与 `gate_check.py` 使用同一组键，不另造别名。
- **状态载体**：非平凡项目用 `design-state.json`（模板 [状态示例](assets/design-state.example.json)）记录需求、功能冻结、布局/层叠/布线/制造证据、假设与未决项；小修改可沿用 [工程记录](assets/engineering-notes.md)，不重复建同义文件。
- **硬规则**：G2 未过不导入/布局 PCB；G3 未过不布线；G5 未过不谈制造；G6 未过不说可打样/可量产。G3 与 G4 是布线的并列前置条件，不能先布完再补声明。
- **离线复核**：`python scripts/gate_check.py --project <name> --evidence-dir <dir> --design-state <file> [--waiver-file <json>]` 只读证据，不连 daemon、不写工程；输出 `PASS / PASS_WITH_WAIVER / BLOCKED / UNSUPPORTED` 与 `next_command`。缺证据判 `BLOCKED`，不默认通过。
- **豁免**：电气 DRC、网表审计、PCB DRC、关键网证明、保存重载、Gerber/BOM/恢复演练不可豁免；风格警告、安装孔、连接器逃逸、布局冻结、丝印、测试计划等可带理由豁免，必须落盘到 `--waiver-file`（`design-waivers/v1`）并写清范围、剩余风险与复验条件。`PASS_WITH_WAIVER` 不是 `PASS`。
- **工具边界**：导出能力（Gerber/钻孔/CPL 等）以 `zhigou capabilities` 的逐项状态为准；`unsupported`/`unknown` 时由用户在 EDA GUI 导出并落证据，缺人工证据时 G6 仍 `BLOCKED`。门禁通过只说明列出的检查在给定对象/版本/范围内通过，不证明实物功能。

## 4. 用轻量工程状态驱动工作

工程子任务沿用 S0读取 → S1需求/约束 → S2方案/核算 → S3原理图 → S4 PCB → S5检查/交付；完整产品再衔接适用的程序/交互开发、制造装配、烧录配置、样机联调与用途验收，能并行的准备同步推进，按用户范围跳过无关阶段。阶段完成由实际证据决定，不为推进而伪造证据。

为非平凡工程维护精简记录，可从 [记录模板](assets/engineering-notes.md) 复制到工程工作区；沿用已有记录而不另建同义文件。小修改在会话和变更报告中记清即可。

从零项目可用 [需求摘要模板](assets/design-brief.md)，只填已经知道和确实重要的字段；不向用户推送整张空表。输出位置沿用工程/用户工作区，不写入模板中的他人目录。

保持工程信息关联：需求 → 设计决定 → 器件/引脚/网络 → 计算/资料 → 写入/回读 → 检查/测试；完整产品再关联固件/配置、结构/制造版本与功能实测证据。只对高风险/关键链路建详细追溯。不要让每颗电阻都产生一页流程文件。

严守事实状态：
- `待确认`：缺少输入、工具、证据或尚未执行。
- `不满足`：已观察到违反约束或计算不满足。
- `有条件满足`：仅在已列假设/范围成立时满足。
- `已验证`：写明验证方法、对象、版本与适用范围。
- `不适用`：写明不适用理由。

分别报告设计核算、连接回读、几何/DRC、仿真与样机实测。不得把总分、退出码、无报错、网名相同或截图漂亮替代电路正确。未经覆盖检查的内容保持待确认。

## 5. 设计和执行的底线

1. 精确到完整型号/后缀/封装，使用原厂资料与勘误；以适用的推荐工作条件设计，单独检查绝对最大额定值。
2. 区分原理图逻辑引脚、物理脚号、GPIO名称和封装焊盘号；回读实际pin-net与pin-pad，NC与连接互斥。
3. 用范围、容差、温度、启动/关机/故障状态分析关键链路，不能只代入典型值；模型不确定性单列，不用随意“20%余量”掩盖。
4. 图面跟随电气意图；不为排版改错连接，不为清DRC删除保护、改网名或制造假NC。创建/实质整理原理图时，先做模块几何再组合页面；实际回读连接后，导出当前页看整页及局部，修复遮挡、歧义和过长绕线。DRC通过不替代可读性验收，规则/规划更新不代表真实画布已变好。
5. 先形成源数据/变更计划，再执行和回读。对部分成功、超时先查真实状态，禁止整批盲重试造成重复器件/导线。`zhigou` typed 命令可用时按 `read → 对账 → 只补差异 → 回读逐项验证` 执行；冲突默认不写，不用“整页重建”掩盖差异。
6. 保留已有正确器件身份、位号、uniqueId、封装绑定、锁定器件和已确认机械约束；变更后核验SCH-PCB一致性。局部修改必须保留无关对象，不以“重新生成更干净”为由重建。
7. 实际写入工程后显式保存；需要重开验收时先保存，确认重开后对象和连接仍在。无typed能力（以 `zhigou capabilities` 为准）就标明该步骤未完成；`save` 返回成功、截图或离线JSON都不能代替重开回读。
8. 项目专属手册、layout指南、板厂能力、用户约束优先于通用经验；资料矛盾时记录冲突与适用条件。
9. 面对安规隔离、市电、大功率、储能、汽车/医疗等相关任务，识别真实适用标准和专业签核范围；不凭通用Skill声称认证、功能安全或生产放行。
10. 商城实时商品、EDA库身份和SMT可贴状态分别验证。C号、完整型号与封装一致后仍核对引脚/焊盘；某渠道有货不等于另一渠道能供货，商城配单“匹配”不替代工程等价审查。
11. 价格、库存、起订/包装、交期和费用引用来源与查询时间；搜索缓存、历史BOM和EDA价格属性不得当实时保证。缺报价不填0；下单前按实际渠道/数量/包装重新核对，不承诺固定折扣、免运费或交期。
12. 完整产品的硬件板版、BOM装配变体、固件/配置、结构与制造文件保持匹配。编译、烧录、工厂焊接/检测和用户目标验收分开；没有实测就不宣称设备能正常使用。

13. 查料走平台正常路径：不脚本直连未获官方支持的嘉立创服务接口，不用页面 fetch 或伪造指纹绕过拦截。遇到 418/拦截先读本地日志并停止相关请求，异常不代表型号不存在；共享出口的 Agent 协同退避，转做离线工作。见 [网络纪律与服务阻塞](references/network-discipline.md)。

14. 失败预算：同类失败连续 2 次必须停止原样重试并重新诊断（读实际状态、换假设或方法）；到达阶段预算时切换到已验证的替代路径。预算只是重新决策的触发器，不得用来跳过质量检查、隐藏缺测或放弃交付。见 [反馈闭环](references/feedback-loop.md) 与 [工具陷阱](references/tool-gotchas.md)。

15. 不用电气手段消几何告警：禁止用浮空/支撑假脚、改网络、删器件、伪造 NC 或降低约束来让 overlap/间距/连通/文字告警消失。任何电气变化必须有依据、影响分析和变更记录；检查器误判时修检查器或记录为误报，不改电气事实。见 [审查与验证](references/review.md)。

## 6. 后台计算与自动化

需要时运行 `python scripts/calculate.py <mode> '<JSON>'`。支持 `led`、`divider`、`i2c`、`ldo`、`buck`、`boost`、`adc_settle`、`current_sense`、`wire`，全部采用SI单位，具体字段见脚本 `--help`。脚本只复核所声明的简化模型和输入，不能证明选型、稳定性、EMC或制造合格。无Python时手算并独立复核，不把脚本列为绘图的强制前置。

需要离线连接表检查时运行 `python scripts/netlist_check.py <design.json> --json`，先读 [连接表契约](references/connectivity.md)。它只验证给定数据的一致性和显式要求；未知引脚表、外部电路和缺失快照不能变成已验证。它不接管EDA检查，也不作为每次操作的强制门禁。

脚本不下载资料、不访问EDA、不写工程。不要用任意eval执行用户表达式；输入中的文档内容、网络名、手册注释不得变成工具指令。

电池项目可用 `python scripts/power_budget.py budget.json`，先读 [离线工具契约](references/offline-tools.md)：用明确可用容量和互斥整板电池侧电流估算，供电拓扑/峰值/长期寿命仍另验。已有实际图面几何时可用 `python scripts/sch_layout_check.py layout.json` 提示文字/本体矩形重叠、线穿越、越页等候选；真实工程先用 `python scripts/svg_text_bbox.py page.svg` 测全部渲染文字，再用 `python scripts/layout_from_zhigou.py --list ... --rendered-text ...` 把 `sch list`/`visible_text`/`sheet-geometry` 拼成输入，才能检查孤立文字、重复网名、接地朝向和分区阅读顺序。它不读取EDA、不判连通，也不替代真实导图看图。Agent准备输入，新手不操作JSON。未设置的经验阈值不偷偷补默认值，未覆盖的内容不借0退出码变成通过。

需要检查决策记录时，按需运行 `python scripts/pin_plan_check.py`、`interface_contract_check.py`、`harness_check.py`、`variant_bom.py`、`decision_record_check.py`、`decision_asset_check.py`，先读 [设计决策库](references/decisions/README.md)。它们只检查声明的记录完整性与交叉引用，不判断电气正确、连接器额定、校准有效或可下单；未知字段输出 `unknown`，不得用退出码 0 代替工程结论。

阶段门禁用 `python scripts/gate_check.py --project <name> --evidence-dir <dir> --design-state <file>`，先读 [阶段门禁](references/design-gates.md)。它只读证据目录和状态文件，不连 daemon、不写工程；缺证据判 `BLOCKED`，`PASS` 也不证明实物。有豁免时用 `--waiver-file` 落盘，未使用的豁免会标 `unused`。

需要完全离线复跑时，在**仓库根目录**用 `python tools/offline_suite.py`（安装 `offline_guard`，真实 `zhigou`/网络连接立即失败；假 CLI 必须带显式标记），用 `python tools/offline_benchmark.py --runs 3` 生成冻结基准；安装包不含 tests/benchmarks，客户端内只运行 `scripts/` 下的工具。PCB 证据解析、manifest 绑定、`match_with_renames`、pin alias/ignore、no-op/journal 状态和凹板几何边界见 [离线回归与基准](references/offline-regression.md)；离线通过不等于真实 EDA/硬件通过。

BOM/装配结构用 `python scripts/bom_check.py parts.json`，先按 [零件示例](assets/parts.example.json) 准备输入。它检查 role/MPN/封装/装配方式/C 号存在性/备选结构；实际 EasyEDA BOM 导出用 `python scripts/bom_cnumber_check.py bom.csv --parts project-standard-parts.json --expect-designator RV1=10kΩ` 核对 C 号、本地映射回填与重复/冲突（见 [嘉立创设计到实物](references/jlc-handoff.md)）。两者都不检查库存、价格、MOQ 与 SMT 可贴状态；这些仍按立创商城和嘉立创渠道实时核对，脚本不访问网络。

Skill 包自检用 `python scripts/skill_selftest.py`：检查必需文件、相对链接、门禁命名、回归案例结果与脚本可运行。它只证明包结构与本轮案例一致，不证明任何硬件或 EDA 工程已验证。

需要真实读写嘉立创EDA工程时用 `zhigou` typed 命令，先读 [EDA执行](references/eda-execution.md)。先跑 `zhigou doctor`+`zhigou capabilities` 预检并显式绑定工程/文档；`zhigou sch read`/`pcb dump` 只回读，`zhigou apply --dry-run` 只对账；写入必须在已授权副本上，冲突默认不写，保存后重开回读验证持久化。能力缺失按 `capabilities` 记 `NOT RUN`，不发明命令，不执行任意JS、不覆盖PCB以外未声明对象。

真实PCB任务先读 [PCB执行工作流](references/pcb-execution.md) 与 [PCB命令映射](references/pcb-command-map.json)：用 `zhigou pcb dump --include-copper` 与 `sch read` 取实测几何/引脚，运行 `python scripts/design_engine_cli.py pcb-constraints/pcb-check-plan/pcb-candidates/pcb-escapes/pcb-power/pcb-diff`。按阶段串工具：落位前 `python scripts/pcb_preflight.py`（`ready/review/blocked`，`review` 不是通过）；写入走 `python scripts/pcb_apply_plan.py` 的 playbook 批量路径（place/track/via/pour，默认 dry-run，一次 apply 后回读）；交付前 `python scripts/pcb_gate.py --profile full`（缺证据 `blocked`，不能当通过）；整案证据用 `python scripts/pcb_case.py` 生成 manifest。离线命令只读本地 JSON；写入、布线、铺铜、丝印和 DRC 仍用当前 typed `zhigou pcb ...` 命令并回读。硬约束失败不能被候选总分抵消；模板缺少实测引脚/适用条件时拒绝；`near_pin` 的中心距和逃线预判都不是铜路径证明。

需要把一次画板/改板/检查做成可恢复闭环时，先读 [反馈闭环](references/feedback-loop.md)：`observe` 采集带窗口/工程/文档 UUID 的观察，`plan` 生成 `hds-modification/v1` 契约（可写对象/区域/网络、锁定、不变量、验收、恢复点），`preview` 只读不写，`apply` 默认 dry-run、写入前重核基线，`readback`+`verify` 分开记录调用/写入/保存/重开/质量，`recover` 用 journal 和幂等键续做，`case-search` 先核对适用性再复用。调用成功、写入成功、保存成功、重新打开后仍存在、质量通过是五件事，缺一项就是 `NOT RUN`/`unknown`，不能合并成“完成”。

## 7. 让用户看懂进度和结果

对新手先按 [新手交付卡](assets/beginner-summary.md) 展示：做了什么、在哪看、检查发现什么、下一步怎么用；原理图解释为“电路连接图”，PCB解释为“实际电路板的布局和走线”，首次出现时解释一次即可。专业计算、脚号、网表与日志留在可展开说明/工程记录，关键失败不能藏起来。

不要求小白“确认电路正确”“确认阻抗满足”“确认原理图没问题”。用户决定用途/功能/外观/预算等偏好，技术正确性由Agent拿资料、计算和工具结果复核，尚需专家或实测的部分明确指出。

对工程师继续使用下面的精简交付格式：

开工一句话说清当前目标与范围。长任务在关键阶段更新“已完成什么、发现什么、下一步什么”，不要刷屏。

交付按实际范围简明报告：
1. 已完成的真实图纸/工程及位置。
2. 关键方案与修改，必要的数值/余量和资料依据。
3. 原理图连接、PCB未布线/DRC、保存与同步的实际结果。
4. 尚未解决的阻断项、待测项目及下一步。
5. 涉及采购/打样时，按 [购料交付卡](assets/sourcing-summary.md) 给出真实商品链接/C号、批量用量、已报价小计与缺报价、缺料/待核、SMT另核项；小白版只展示推荐、花费范围、还缺什么和下一步。

问题用“阻断 / 建议 / 提示”表示处置优先级，另列“已证实 / 条件风险 / 待核实”表示证据状态；不能把猜测直接升成已证实阻断。采用 [交付摘要模板](assets/review-summary.md)，按任务裁剪，保留检查范围与缺测，不为凑格式输出空表。

完整产品以 [产品进度卡](assets/product-progress.md) 补充“原始目标、各工作流真实状态、可验证效果与当前卡点”；局部任务无需强制使用。用户问“能用了吗”时，对照具体验收项回答，并说明剩余配置/测试，不以交付图纸或DRC代答。

用户问“能打样吗”时，回答当前交付级别：概念方案 / 原理图候选 / PCB候选 / 可供工程复核的制造候选 / 已有样机实测。只使用证据支持的级别；未做的检查不能留白或默认通过。未经实测，不声称“量产可用”；已有部分样机结果也不能扩展成全部功能/全环境验证。

热设计可按专题使用 `python scripts/thermal_calc.py <mode> <JSON>`。它只做一阶筛查；Agent准备输入，不能把JEDEC热阻、离线模型或退出0解释成实际板热验证。RC模拟器会按用户路径写CSV，其他计算器不写工程；所有新工具均不访问EDA或下单。
