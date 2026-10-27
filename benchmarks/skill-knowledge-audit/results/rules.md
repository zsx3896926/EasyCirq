# 规则候选与冲突审查

- 规则记录：12，机器候选：400，候选张力：200，已审查关系：10，确认冲突：0
- 夹具：16 对，分类正确 16 对

> 本结果只证明静态文档结构与引用关系，不证明 Skill 被客户端加载、模型遵守规则、阅读行为改变或硬件设计正确。 规则分类是启发式/人工审查，不是运行时行为证明；未运行模型会话，未测量实际审批次数或阅读 token。

## 已审查关系

### REL-01 — different_stage

- 规则：R-SKILL-001
- 重叠条件：默认自主评审节奏与布局冻结后的变更门禁同时被读到
- 触发场景：布局已冻结，为布线移动器件，同时用户未要求暂停
- 例外/处置：design-gates 153 是阶段顺序/证据要求，不是用户审批等待；用户显式要求时才在检查点等待
- 建议：无需改规则；在布局冻结变更说明中注明这是 G3 重开而非审批门，避免被读成强制等待
- 证据：`design-hardware/SKILL.md:96` — 方案、原理图、布局、交付设为四个可见检查点。默认在任务已授权范围内自查、汇报并继续；用户说“先评审”“这步给我看”“确认后再布线”时，在对应边界等待。不要把工程检查点一律变成权限停顿点。真正改变已确认接口/尺寸/成本目标、涉及关键未知量时，先处理该决定，同时推进无依赖部分。
- 证据：`design-hardware/references/design-gates.md:153` — **豁免规则：** score、crossings、overlap/off-board/short 和板框不可豁免；安装孔、连接器逃逸、自动摆放对比、冻结时间可豁免并写明剩余风险。布局冻结后若为了布线移动器件，必须先重开 G3 并作废受影响布线。

### REL-02 — different_scope

- 规则：R-START-009, R-START-010
- 重叠条件：新任务启动时是否先做更新/EDA 探测
- 触发场景：用户要求纯资料分析，Agent 考虑是否先跑 skill_update check / doctor
- 例外/处置：R-START-009 措辞为 may（可用），R-START-010 明确纯分析无需提前探测
- 建议：保持 may；计划中纯分析不产生 install/network 动作，实际读写工程前再检查
- 证据：`design-hardware/SKILL.md:15` — 新硬件任务开始前可用当前安装目录的 `scripts/skill_update.py check` 统一检查本 Skill 与 easyeda-agent 的 CLI/Skill/daemon/Connector（24 小时缓存）；
- 证据：`design-hardware/SKILL.md:104` — 纯方案/资料分析任务无需提前连接、安装或探测EDA；准备实际读写工程或用户要求接通环境时，再执行本节。

### REL-03 — coexist

- 规则：R-LAY-011
- 重叠条件：绘制/整理原理图时局部与跨区连接介质
- 触发场景：局部反馈网络与跨区信号同时存在
- 例外/处置：两处文本方向一致：局部直连、跨区用标签/端口
- 建议：保留一处为正文，另一处改链接，减少重复阅读（proposal P-06）
- 证据：`design-hardware/references/schematic-layout.md:74` — - 局部连接优先直接画线；只有跨区、跨页或长距离才用标签。为减少一条线而增加一串标签，通常让拓扑更难读。
- 证据：`design-hardware/SKILL.md:120` — 简单工程优先一页，按信号方向组织主链、把供电/参考放辅助行；局部反馈、分压、滤波和去耦保留可追踪导线，跨区信号才考虑端口。已有工程保留器件身份与连接，按受影响模块修正；一次候选失败先读取具体冲突，同一失败机制重复两次就换布局方法或记录能力缺口，不继续盲改坐标。

### REL-04 — default_with_exception

- 规则：R-LAY-011, R-LAY-012
- 重叠条件：已有符号难以直连的局部连接
- 触发场景：库符号引脚位置不适合直连，但 pin-pad 映射必须保留
- 例外/处置：R-LAY-012 的“既有符号难以直连”是 R-LAY-011 的覆盖例外
- 建议：无需改规则；可把例外合并到同一条（proposal P-06）
- 证据：`design-hardware/references/schematic-layout.md:74` — - 局部连接优先直接画线；只有跨区、跨页或长距离才用标签。为减少一条线而增加一串标签，通常让拓扑更难读。
- 证据：`design-hardware/references/schematic-layout.md:54` — 物理脚号顺序不等于原理图阅读顺序。优先使用可信库中已核对的功能分组符号/单元；不能为了好看直接改库脚号、交换引脚或临时重画芯片。既有符号难以直连时用短引线与明确标签化解，不牺牲pin-pad映射。

### REL-05 — coexist

- 规则：R-GATE-005
- 重叠条件：缺执行通道但需继续可做部分
- 触发场景：Connector 不可用，但仍需离线分析并报告未写入项
- 例外/处置：R-GATE-005 限制“不得声称通过”，另一条允许继续可做部分并如实标注
- 建议：无需改规则；在 BLOCKED 说明中补一句“只影响依赖链路”即可（P-07）
- 证据：`design-hardware/references/design-gates.md:63` — 6. **缺证据就是 `BLOCKED`，不是 `PASS`。** 未运行、未导出、未回读的检查保持 `待确认`；报告写 `NOT RUN`，不写“应该没问题”。
- 证据：`design-hardware/SKILL.md:112` — - 缺少执行通道时仍可完成方案、计算或离线规划；明确列出未写入项，不把文本、JSON、图片或探针结果说成用户工程已完成。

### REL-06 — ambiguity

- 规则：
- 重叠条件：“做个板子”是否等于“用户明确要定制板”未定义
- 触发场景：新用户说“做个板子”，同时现成模块能更快验证
- 例外/处置：SKILL.md 未给出判别标准
- 建议：增加定义：仅当用户拒绝模块路线或明说定制/画板时按定制板推进（P-03）
- 证据：`design-hardware/SKILL.md:42` — - 问“做个板子”默认推进适合目标的原理图及PCB候选；问“做个设备/实现这个idea”同时建立功能、硬件、程序、结构、制造和验收的适用任务，先给最小可验证方案并继续；“先方案/先别画”只做方案。学习示例板、现成模块拼装、自制PCB分别解释和交付，不擅自把用户要的PCB替换成接线教程。
- 证据：`design-hardware/SKILL.md:84` — 自定义PCB不是所有idea的必经之路：现成模块能更快验证效果时，解释后作为适用路线；用户明确要定制板时保留定制交付，不悄悄换成购买开发板。服务选择围绕功能、成本和交付，不为增加业务环节强推服务。

### REL-07 — different_scope

- 规则：R-READ-006
- 重叠条件：“始终遵循”与“按需读取”同时出现
- 触发场景：新任务开工，Agent 判断是否加载全部 references
- 例外/处置：“始终”只覆盖 workflow.md 与 evidence.md，其余按任务表加载
- 建议：无需改规则；可在 L134 明说“仅这两份始终读”以降低误读
- 证据：`design-hardware/SKILL.md:134` — 内部设计始终遵循 [工程工作流](references/workflow.md) 和 [证据与工程记录](references/evidence.md)，内容由Agent消化，不要求用户读完。按任务加载：
- 证据：`design-hardware/SKILL.md:132` — ## 3. 按需读取，不加载规则百科

### REL-08 — ambiguity

- 规则：R-GATE-004
- 重叠条件：检查点等待与新决定处理是否同一触发
- 触发场景：布局前发现尺寸必须变化，同时用户要求先评审
- 例外/处置：两处文本对“新决定”是否属于检查点等待未说明
- 建议：明确“新决定=改变已确认接口/尺寸/成本/范围”，不属于检查点等待（P-04）
- 证据：`design-hardware/references/design-gates.md:7` — 门禁是**阶段退出证据门，不是审批门**。Agent 在用户已授权的设计/修改范围内自查、记录并继续；门禁不新增等待点，也不要求用户逐项签批。只有用户明确说“先评审 / 这步给我看 / 确认后再布线”时，才在方案、原理图、布局、交付四个可见检查点等待。
- 证据：`design-hardware/references/interaction.md:30` — 只有用户要求分阶段确认，或真正需要新决定时才等待。用户只说“先方案”时严格不画图；用户要求“直接做完”时不要在四个点各问一次许可。

### REL-09 — different_scope

- 规则：
- 重叠条件：完整产品验收终点与局部任务范围
- 触发场景：用户只要求画图/评审，却同时提到最终设备目标
- 例外/处置：任务范围词不相交，完整产品验收只在完整产品范围成立
- 建议：无需改规则；计划层按 task_type 区分，不把整机验收强加给局部任务
- 证据：`design-hardware/SKILL.md:8` — 让用户描述想实现的效果，由正在运行的Agent持续推进到任务范围内的真实成果；完整产品任务以实物是否实现原始用途验收，画完图、买齐料或贴片完成都不是默认终点。此Skill是Agent的协作与工程方法包；Agent负责读信息、问关键问题、推荐选择、调用工具、处理失败和交付，EDA执行Skill/CLI/连接器负责实际编辑。安装此Skill本身不会获得本机访问、EDA连接、软件安装或制造下单能力。
- 证据：`design-hardware/SKILL.md:30` — - 用户只要求画图、review、换料、PCB或先方案时，仍按该范围交付，不强行追加App、外壳、采购或完整产品开发。

### REL-10 — coexist

- 规则：R-EXEC-007
- 重叠条件：合批提速与失败未验证
- 触发场景：多模块合批写入后 save/reload 失败
- 例外/处置：R-EXEC-007 同段自带“不能为提速跳过身份/连接/DRC/最终保存重开”
- 建议：无需改规则；保持例外与 unverified 条款并列可检索
- 证据：`design-hardware/SKILL.md:130` — 多个独立 PCB 放置模块来自同一实测快照时，按 [批量执行与提速](references/execution-efficiency.md) 使用 `pcb_apply_plan.py --module-plan ... --module-plan ...`：一次读取/标准化、联合检查模块与固定对象，再生成一次 apply 和保存重载链。简单整板已有单个计划时继续用 `--plan`，无需为合批拆模块。批次间有依赖、需观察中间结果或源快照变化时重新采集并分批；不能为提速跳过身份、连接、DRC 或最终保存重开。只读分析复用冻结快照，写入后旧快照失效，不按每颗器件重复探测。原理图沿用 compose/现有模板路径，不用 PCB 放置批处理冒充原理图或布线完成。
- 证据：`design-hardware/references/pcb-execution.md:306` — - save/reload/journal/dump 任一失败都只能报 `unverified`，不能写 `verified`。

## 夹具分类

| pair | expected | actual | result |
|---|---|---|---|
| FX-01 | true_conflict | true_conflict | PASS |
| FX-02 | default_with_exception | default_with_exception | PASS |
| FX-03 | different_stage | different_stage | PASS |
| FX-04 | different_scope | different_scope | PASS |
| FX-05 | stale_reference | stale_reference | PASS |
| FX-06 | ambiguity | ambiguity | PASS |
| FX-07 | user_authorized | user_authorized | PASS |
| FX-08 | technical_limit | technical_limit | PASS |
| FX-09 | negation | negation | PASS |
| FX-10 | code_example | code_example | PASS |
| FX-11 | coexist | coexist | PASS |
| FX-12 | coexist | coexist | PASS |
| FX-13 | different_scope | different_scope | PASS |
| FX-14 | coexist | coexist | PASS |
| FX-15 | default_with_exception | default_with_exception | PASS |
| FX-16 | coexist | coexist | PASS |

## 候选张力（不是确认冲突）

- `C-0001` approval_vs_autonomy：`M-29413c900f` ↔ `M-314afa5e96`
- `C-0002` approval_vs_autonomy：`M-da200a8af4` ↔ `M-314afa5e96`
- `C-0003` approval_vs_autonomy：`M-421e3c865f` ↔ `M-314afa5e96`
- `C-0004` full_load_vs_on_demand：`M-f986420599` ↔ `M-cf9f7b59ef`
- `C-0005` full_load_vs_on_demand：`M-f986420599` ↔ `M-de11b6c47e`
- `C-0006` full_load_vs_on_demand：`M-f986420599` ↔ `M-ea8926a126`
- `C-0007` full_load_vs_on_demand：`M-f986420599` ↔ `M-0f337a24ba`
- `C-0008` full_load_vs_on_demand：`M-f986420599` ↔ `M-8aeb9ff9dc`
- `C-0009` full_load_vs_on_demand：`M-f986420599` ↔ `M-9056c6a963`
- `C-0010` full_load_vs_on_demand：`M-f986420599` ↔ `M-b994f70719`
- `C-0011` full_load_vs_on_demand：`M-f1a411d180` ↔ `M-a8dc9718dc`
- `C-0012` full_load_vs_on_demand：`M-f1a411d180` ↔ `M-d3dc6b426c`
- `C-0013` full_load_vs_on_demand：`M-f1a411d180` ↔ `M-abf25985d1`
- `C-0014` full_load_vs_on_demand：`M-f1a411d180` ↔ `M-cf9f7b59ef`
- `C-0015` full_load_vs_on_demand：`M-f1a411d180` ↔ `M-d9a3a874a1`
- `C-0016` full_load_vs_on_demand：`M-f1a411d180` ↔ `M-de11b6c47e`
- `C-0017` full_load_vs_on_demand：`M-f1a411d180` ↔ `M-bc8c74f431`
- `C-0018` full_load_vs_on_demand：`M-f1a411d180` ↔ `M-5e64502de0`
- `C-0019` full_load_vs_on_demand：`M-f1a411d180` ↔ `M-217cb4ba31`
- `C-0020` full_load_vs_on_demand：`M-f1a411d180` ↔ `M-5e2b56f400`
- `C-0021` full_load_vs_on_demand：`M-f1a411d180` ↔ `M-ea4a7c4eec`
- `C-0022` full_load_vs_on_demand：`M-f1a411d180` ↔ `M-60ab6504c1`
- `C-0023` full_load_vs_on_demand：`M-f1a411d180` ↔ `M-ea8926a126`
- `C-0024` full_load_vs_on_demand：`M-f1a411d180` ↔ `M-0f337a24ba`
- `C-0025` full_load_vs_on_demand：`M-f1a411d180` ↔ `M-fbdf7ced79`
- `C-0026` full_load_vs_on_demand：`M-f1a411d180` ↔ `M-ed43a223a7`
- `C-0027` full_load_vs_on_demand：`M-f1a411d180` ↔ `M-8aeb9ff9dc`
- `C-0028` full_load_vs_on_demand：`M-f1a411d180` ↔ `M-1f7b0f1b41`
- `C-0029` full_load_vs_on_demand：`M-f1a411d180` ↔ `M-9056c6a963`
- `C-0030` full_load_vs_on_demand：`M-f1a411d180` ↔ `M-b86434900a`
