# ACE 评审清单（王牌问题评审器）

目的：把"王牌工程师签板前会问的问题"变成**确定性、可回归、离线**的检查；
LLM 只负责把用户意图变成 block/netlist spec，评审由脚本完成。
决策记录见 [ace-review-adr.md](ace-review-adr.md)；布局侧约束见 [layout-engine-v2.md](layout-engine-v2.md)。

## 数据来源与输出

`tools/ace_snapshot.py` 从活动页抓只读快照：components（ref/bbox/pins）、
connectivity（pin→net）、title block；多页时用 `ace_snapshot.merge(...)` 合并，
自动生成 `nets_by_page` 与 `cross_page_nets`。快照格式 `easycirq-ace-snapshot/v1`。

评审器 `tools/ace_review.py` 只读快照，不碰 EDA；规则注册表是模块级 `RULES`
（30 条，ID 稳定 R01–R30）。输出 `easycirq-ace-review/v1`：

- `findings[{rule,severity,message,refs}]`；`severity ∈ {error, warn}`；
- `metrics{errors,warnings,rules,rules_checked}`；`verdict = pass | blocked`；
- 任一 `error` finding → `verdict=blocked`，否则 `pass`；`warn` 不阻塞但必须可见。

### 可选字段（R11–R30 依赖；缺了只 warn/跳过，不崩）

| 字段 | 位置 | 用途 |
|---|---|---|
| `value` / `mpn` | component | 容值/耐压/极性关键词、BOM 完整性（R11–R14、R29） |
| `type` | component | `ceramic`/`electrolytic`/`tantalum`/`led`/`tvs`/`fuse`/`crystal`/`switch`/`ldo` |
| `voltage` | component | 电容耐压（R13）；也可从 `value` 的 `16V` 解析 |
| `polarity` | component | 电解/钽电容极性是否已知（R12） |
| `params.dropout_mv` | component | LDO 压差（R14），>10 视为 mV |
| `i2c_address` | component | I2C 地址选型是否记录（R24） |
| `keyed` | component | 连接器防反/键控（R25） |
| `page` | component | 多页归属（merge 填充） |
| `net_voltage` | snapshot | 网络→电压（R13/R14）；缺省从网名推断（3V3→3.3、5V→5） |
| `nets_by_page` / `cross_page_nets` | snapshot | 跨页一致性（R28），`merge()` 生成 |

`ace_snapshot.build()` 会从宿主组件 properties/attributes 尽力提取上述字段；宿主
没给的留空，评审按"缺数据"处理。

## 缺数据处理（强制约定）

| 情况 | 行为 |
|---|---|
| 规则需要的属性缺失（如电容没记耐压、LDO 没记压差） | **不判**：整条规则跳过，不猜值 |
| 规则看到对象但无法完成判定（如有耐压但网压不可知） | `warn`，消息含 `unknown`，不升级为 error |
| 快照里没有任何引脚/连通性数据 | 结构性规则（如 R04 地 tie）跳过，不凭空报 error |
| 组件缺 bbox/pins/value | 相关检查降级或跳过，其他规则继续 |
| 任何畸形/缺键输入 | 不抛异常（`review({})` 返回 pass + findings 列表） |

**为什么没有 `info` 级别**：评审门禁（`tools/review_gate.py`）把未知 severity 当作
阻塞证据（fail-closed）。缺数据若用 `info` 会让干净快照被 gate 拦下，因此缺数据
统一用 `warn` + "unknown" 措辞，既不猜、也不误阻塞。

## 已实现规则（30 条，均为纯函数）

| ID | 规则 | 级别 | 王牌问题 | 快照依赖 |
|---|---|---|---|---|
| R01 | 浮空引脚 | warn | 这些脚是有意 NC，还是漏连？ | pins.net / nc |
| R02 | I2C 无上拉 | error | SCL/SDA 上拉在哪？阻值按速率/容性算过吗？ | net、resistor |
| R03 | 电源脚附近无去耦电容 | error | 每个电源脚 100nF 在哪？离脚多远？ | pins、bbox |
| R04 | AGND/DGND 与 GND 的 tie 不是恰好一个 | error | 地怎么分、在哪一点汇合？会不会地环路？ | net |
| R05 | 反馈网络没有电容 | warn | 反馈点取自输出电容之后吗？ | FB net |
| R06 | EN/CE/SHDN 悬空 | error | 上电默认状态是什么？会不会误使能？ | pins.net |
| R07 | 连接器网络无串阻/ESD/TVS | warn | 外部接口的 ESD 路径在哪？ | connector net |
| R08 | 电源网络无测试点 | warn | 上电怎么量？产线怎么测？ | testpoint |
| R09 | 自动生成网络名（C1_N9 之类） | warn | 网络名能不能表达意图、方便评审？ | net 名 |
| R10 | 标题栏字段为空 | warn | 版本/页/作者/日期齐全吗？ | titleblock |
| R11 | 每个电源轨缺 bulk 或陶瓷组合 | warn | 这条轨上 10uF 和 100nF 都有吗？ | cap `type` + 容值、net |
| R12 | 电解/钽电容极性未知 | warn | 有极性电容正极朝哪、封装方向对吗？ | `type`/`polarity`/value |
| R13 | 电容耐压相对网名电压降额不足 | warn | 3V3 上用 4V 电容？降额够吗？ | `voltage`、`net_voltage` |
| R14 | LDO 压差余量不足 | warn | 5V→3.3V 用 1.5V 压差的 LDO 够吗？ | `dropout_mv`、`net_voltage` |
| R15 | 反馈分压不完整（缺上/下臂） | warn | FB 到输出和到 GND 的电阻都在吗？ | FB 网、resistor |
| R16 | 晶振脚缺负载电容 | warn | XIN/XOUT 负载电容在哪？CL 算过吗？ | crystal、capacitor |
| R17 | 复位/BOOT/STRAP 脚未 tied 或未 pull | warn | 上电/复位默认状态确定吗？ | pins、resistor |
| R18 | LED 无串联限流电阻 | warn | LED 电流怎么定？会不会烧？ | diode/led、resistor |
| R19 | 按键缺上拉或去抖电容 | warn | 松开时电平确定吗？抖动怎么处理？ | switch、R、C |
| R20 | 未用脚没有显式 NC | warn | NC/DNU 脚是悬空还是显式 NC？ | pins.nc |
| R21 | USB 差分对缺串阻/ESD | warn | D+/D- 的串阻和 ESD 在哪？ | USB net、connector |
| R22 | 差分对命名不是成对 _P/_N | warn | 差分对能按名配对、不靠猜吗？ | net 名 |
| R23 | SPI CS 无上拉 | warn | 上电/复位期间从机会不会被误选中？ | CS pin、resistor |
| R24 | I2C 地址 strap 未记录 | warn | 地址脚怎么接、地址值写进文档了吗？ | ADDR pin、`i2c_address` |
| R25 | 连接器电源脚无防反保护 | warn | 反接会不会烧板？有键控/二极管/保险吗？ | connector、diode/fuse |
| R26 | 输入轨无保险/防反 | warn | 输入短路/反接时第一道防线是什么？ | fuse、input rail |
| R27 | 外部连接器网络无 TVS/ESD | warn | 静电从接口进来时去哪？ | connector net、TVS |
| R28 | 跨页网络未声明一致 | warn | 同名网跨页是同一张网吗？作用域对吗？ | `nets_by_page` |
| R29 | BOM 值仍是 `{Value}` 占位符 | warn | 值/型号能直接下单吗？ | value/mpn |
| R30 | 每个电源脚的去耦数量不足 | warn | 2 个电源脚只放 1 个电容够吗？ | pins、bbox、caps |

实现口径（避免误报）：

- R11 只在电容带显式 `type` 时判定（只看容值给不出 bulk/陶瓷分类）；无 `type` 的老快照跳过。
- R13 只在快照记录/解析出耐压时判定；没有耐压 = 不判（不猜）。
- R14 只在有 `dropout_mv` 时判定；只有 "LDO" 名字不算规格。
- R15 对"FB 直连自身 VOUT"的固定输出版本跳过（没有外部分压是正常的）。
- R22 只对显式 `_P/_N` 命名配对判定；`D+` 单端老命名不误报，成对 `+/-` 才提示改 `_P/_N`。
- R28 没有 `nets_by_page` 时跳过；只有声明了跨页网但缺页数据时给 warn（unknown）。

### 与 #213 文档中"扩展规则 PENDING 口径"的关系

`docs/method/ace-review-checklist.md`（#213）曾给出一版 R11–R30 的 PENDING 验收口径，
与本实现的任务书映射不同。**实现以本表为准**；旧口径的检查项被拆/并到不同 ID：

| 旧 PENDING 条目 | 本实现覆盖 |
|---|---|
| 连接器防反/极性保护 | R25 |
| 外部接口 TVS 钳位 | R27（与 R07 互补） |
| 晶振负载电容 | R16 |
| 电源域 bulk 储能 | R11 |
| 反馈节点分压电阻 | R15 |
| 浮空脚显式 NC | R20 |
| 同名网络跨页不一致 | R28 |
| 差分/总线命名 | R22 |
| 去耦数量/距离 | R30（R03 已有距离判定） |
| 需要 zone/评审元数据的条目（旧 R25/R30 等） | 未实现（快照无数据，NOT RUN） |

## 错误注入（能力度量）

`tools/ace_inject.py` 对快照做单点变异（`deletion` 删除结构 / `additive` 追加缺陷），
检查评审器是否用**预期规则**报出：

- 删除去耦电容 / 移远去耦电容 → R03
- 删除 I2C 上拉 → R02
- 破坏地 tie / 追加第二个地 tie → R04
- 浮空电源脚 / EN / 追加浮空脚 → R01/R03、R06、R01
- 删除反馈电容 → R05
- 删除连接器串阻/ESD / 追加无 ESD 连接器 → R07
- 删除电源测试点 → R08
- 把网络改成自动名 / 追加自动网名 → R09
- 清空标题栏 → R10

度量口径（ADR-002）：

- `applicable`：目标结构存在且基线未违规（否则无法"移除"来注入）；
- `detected`：变异后预期规则出现（且计数增加或新规则出现）；
- `detection_rate = detected / applicable`；
- 不可注入的变异**单列**，不混进分母——它是"结构完整性"证据，不是评审器缺陷。
- R11–R30 的正确性由单元测试保证：**每条新规则一个正例 + 一个反例**
  （`tests/test_ace_review.py`）。给注入器补 R11–R30 变异仍在债务里。

## 评审门禁（gate）

评审结果不是建议，是 apply 前置门禁（ADR-003，`tools/review_gate.py` 已入 main #214）：

- **位置**：`plan → apply` 之间；gate 自己调 `ace_review.py` 重跑规则，不信任调用方自报 verdict。
- **strict（默认）**：任一 `error` → `blocked/allowed=False`；**未知 severity 也按 error 处理**；`warn` 不阻塞但保留在 `warnings`。
- **fail-closed**：`--require-review` 且快照缺失/不可读 → 项目 `review-blocked`；快照 JSON/schema 非法 → 输入错误（exit 2），不是通过。
- **输出** `easycirq-review-gate/v1`（实际字段）：`mode`、`strict`、`verdict`、`blocked`、`allowed`、
  `errors`、`warnings`、`findings`、`counts`、`rules`、`review_verdict`、`review_schema`
  （advisory 有 error 时另带 `advisory_errors_allowed`）。
- **CLI**：`python tools/review_gate.py snapshot.json [--json] [--advisory]`，exit 0 放行 / 1 阻塞 / 2 非法输入。
- **流水线**：`tools/run_layout_pipeline.py` 在离线规划后、写 apply exec spec 前 gate，支持 `--require-review` / `--review-advisory`；review-blocked 项目无 exec spec、不碰 EDA，批次继续；pipeline-report 有 `review` 汇总、dashboard 有 Review gate 段。
- **advisory**：只用于练习/推广，永不阻塞但保留 `review_verdict` 与放行错误数，不能当发布依据。
- **尚未实现（债务）**：snapshot/plan 的 SHA-256 绑定与 `checked_at` 证据字段（当前 gate 结果里**没有**这两个字段）、未留痕 override、真机 apply 路径（`sch_layout_apply.py` / `sch_layout_apply2.py`）全部接 gate。

## 修复计划生成（fix plan）

被 gate 阻塞后，下一步不是让人凭感觉改图，而是把 finding 变成**确定性、有序的修复动作**
（`tools/ace_fix_plan.py`，schema `easycirq-ace-fix-plan/v1`；已入 main #217）：

- 输入同一份 ACE 快照（可选 review 报告）；输出 `actions[{id: fx-01…, rule, action{type,kind,…}}]` + `counts.actions`；
- 动作是具体建议（如 `add_component` resistor/capacitor、`add_tie`、`rename_net`、移动/补去耦位置），
  顺序稳定、同快照同计划；**不调用 EDA、不用 LLM、不自动写入**——执行仍由 Agent 按计划做并回读；
- 验收：`tests/test_ace_fix_plan.py` 6 tests（clean 无动作、缺上拉→加电阻、缺地 tie→补 tie、
  自动网名→改名、缺去耦→补/移电容、确定性）；
- 真实页产出规模（2026-10-29 快照）：A **22 actions**、B **13 actions**、C **17 actions**；
  数量只说明"待修结构"的规模，不代表电气正确性或已修复。

## 语料库（corpus）

`easycirq/assets/ace-corpus/`（#211）：

| 文件 | 用途 |
|---|---|
| `clean-reference.json` | 干净参考设计（电源/接口/去耦/地/反馈结构齐全） |
| `clean-reference.expected.json` | 期望评审（`easycirq-ace-expected/v1`：verdict pass、errors/warnings 0、rules []） |
| `bad-decoupling-too-far.json` | 去耦距离负例（预期 R03） |
| `bad-ground-tie-broken.json` | 地 tie 负例（预期 R04） |
| `bad-missing-i2c-pullup.json` | I2C 上拉缺失负例（预期 R02） |

- 语料是**规范 JSON、无时间戳**，可逐字节比对；`tests/test_ace_corpus.py`（13 tests）
  校验：文件齐全、schema 合法、expected 与评审一致、bad 快照各自命中预期规则、
  删除类与追加类变异都能检出、输出可复现。
- **30 条规则下干净参考仍须 0 finding**（本 PR 的兼容性验收）：R11–R30 的"可判定门槛"
  因此写成"数据不足就跳过"，语料不需要为新增规则改写。
- 边界：合成语料不是真实板；真实板只作补充验证，不能替代注入回归。

## 当前结果（30 条规则，2026-10-29）

| 项 | 结果 |
|---|---|
| 规则数 | 30（`RULES` 表，ID 稳定） |
| 干净参考设计 `clean-reference.json` | `pass`，**0 errors / 0 warnings**（R01–R30 全部不误报） |
| 干净合成基准（test_ace_review） | `pass`，**0 findings**（30/30 规则满足） |
| 错误注入（synthetic clean） | **17/17 全部检出**（13 deletion + 4 additive，`detection_rate=1.0`） |
| 错误注入（corpus clean） | **16/16 全部检出**（12 deletion + 4 additive，`detection_rate=1.0`） |
| 单元测试 | `test_ace_review.py` **64 tests OK**；`test_ace_corpus.py` **13 tests OK**；`test_review_gate.py` **24 tests OK** |
| 块模板/角色解析（#215） | `test_layout2_templates.py` **31 tests OK**；`tools/layout2/role_resolver.py` + `templates.py`，与评审清单的 R11–R30 互不替代 |
| 修复计划生成 | `tests/test_ace_fix_plan.py` **6 tests OK**；同一快照 → 同一 `easycirq-ace-fix-plan/v1` 动作序列 |
| 缺数据行为 | 空/畸形快照不崩；缺属性→跳过或 `warn`（含 `unknown`）；无连通性数据不凭空报 R04 |

真实 A/B/C 页面（2026-10-29 快照，10 条规则版本的历史记录，R11–R30 未重跑）：

- A：7 errors / 19 warnings（6×去耦距离、1×地 tie、2×电源测试点、17×自动网名）；fix plan **22 actions**
- B：4 errors / 52 warnings（2×I2C 无上拉、1×去耦、1×地 tie）；fix plan **13 actions**
- C：1 error / 16 warnings（地 tie）；fix plan **17 actions**
- 注入可测数 A 3/3、B 2/2、C 2/2，全部检出。
- 其余变异"不可测"——因为设计本身已缺失该结构（没有上拉/测试点/ESD，去耦已太远）。
  **这本身就是结论：当前设计与王牌水准的差距首先在"结构完整性"，不在"能不能画出来"。**

> R11–R30 在真实页面上的表现 **NOT RUN**：真实快照目前只带 `value/mpn` 的粗文本，
> 极性/耐压/压差/地址等字段需要宿主补全或人工补录；补全后重跑
> `ace_snapshot.build` + `review` 即可得到真实增量（不改 R01–R10 结论）。

## 边界与下一步（剩余债务）

1. **真实页面重跑 R11–R30**：补录可选字段（voltage/polarity/dropout/i2c_address/keyed）
   后重跑，不把合成基准当真实板结论。
2. **注入器补 R11–R30 变异**：现在新规则只有单测正/反例，没有注入器 `applicable` 变异；
   补齐后才算达到"每条规则至少 1 个 applicable 变异"的验收线（PENDING）。
3. **gate 接入全部 apply 路径**（含 `tools/sch_layout_apply.py` 与布局引擎 v2）；
   补"gate pass 但落点有问题"的回归负例。
4. **阈值校准**：去耦距离 180 raw、降额系数（陶瓷 2.0×/电解 1.5×）、LDO 余量 0.2V、
   CS/I2C 上拉范围等用真实板/原厂资料校准，结果写 ADR 复测触发。
5. **不含 zone/模块/评审元数据的条目**（旧口径的模块归属、评审元数据）仍需快照扩展，
   当前明确 NOT RUN，不用截图猜。
6. **流水线 save-after-apply 尚未实现**（apply → save → `doc reload` → 回读 → 对比；
   见 ADR-006）；没有回读证据前不能把 apply 记成 `verified`。
