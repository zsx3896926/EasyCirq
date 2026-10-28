# PCB布线策略：层数、电源地与布线计划

本页解决 S4 内的三个连续问题：板子做几层、电源和地怎么给、先布什么以及怎样证明布通。它接在 G3 布局冻结之后使用；G4 电源地策略与 G3 并列，必须在真正布线前声明；G5 是布线退出条件。

先读 [PCB工程习惯](pcb.md) 与 [工程工作流](workflow.md)。阶段门禁名称、状态词与证据细节见 [design-gates.md](design-gates.md)。逐项电气细节在 [布线与回流细节](pcb-routing-details.md)（RT 编号）与 [PCB布局细节](pcb-placement-details.md)（PL 编号）；本页只引用编号，不复制条款正文。层数、铜厚、孔/槽与工艺能力按 [嘉立创PCB生产规则](jlc-pcb-rules.md) 的当期订单条件核对，本页不复述能力数值。计划落到可填写表格：[布线计划模板](../assets/routing-plan.md)。

## 0. 使用边界

- 本页输出的是“计划 + 证据 + 判定”，不是布线完成证明；不能替代原厂 layout 指南、叠层阻抗计算、SI/PI 仿真与样机实测。
- 门禁是证据门，不是审批门。Agent 在已授权范围内自查、记录并继续；缺证据只暂停依赖它的链路，其余工作照常推进。只有用户明确说“先评审”“这步给我看”“确认后再布线”时，才在对应检查点等待。
- 状态词：`PASS` 表示已验证（写明方法/对象/版本/范围）；`PASS_WITH_WAIVER` 表示没有未处理失败但关键失败被带理由的豁免覆盖（写明理由、条件、剩余风险），不能当 `PASS`；`BLOCKED` 表示不满足或证据缺失；`UNSUPPORTED` 表示当前 CLI 无覆盖，必须进 `not_checked`。判定优先级 `BLOCKED` > `UNSUPPORTED` > `PASS_WITH_WAIVER` > `PASS`。
- 数字与案例只作为条件化经验。换板、换层叠、换器件或换工艺后重新核对，不沿用旧结论。

## 1. 层数决策：2 层与 4 层

### 1.1 决策矩阵

| 维度 | 2 层 | 4 层 | 本项目怎么判断 |
|---|---|---|---|
| 成本 | 板材与工序少，通常更省；实际差价随数量、工艺与渠道变化，本页不写具体价格 | 层压、对位与成品率因素增加成本；打样与批量价差不同 | 用当期渠道报价核对；不为省成本接受不可布，也不为“看起来专业”无理由加层 |
| 可布性 | 只有两层走线，靠通道规划与铺铜腾空间；交叉多时容易反复 | 内层可做平面，外层走线压力小；但过孔与平面开窗更复杂 | 看 `easycirq pcb layout-lint --json` 的 score/crossings 与关键逃线；2 层多轮重排仍不收敛再评估升级 |
| 电源完整性 | GND 靠双面铺铜与缝合孔，回流路径受开槽、器件和走线切割影响 | 完整参考平面与电源平面，回流更连续；前提是平面划分与过孔位置正确 | 有连续参考、阻抗控制或多电源域需求时倾向 4 层；2 层必须证明 GND 连续 |
| EMC/回流 | 无完整参考平面，回流靠双面铺铜与缝合；接口、开槽与长支路需额外控制共模与辐射路径 | 完整平面有利于回流与辐射控制，但平面分割、过孔和接口处理不当仍会失败 | 有 EMC/认证要求或高速/接口较多时优先 4 层；2 层必须逐段核对回流与缝合 |
| 装配与嘉立创工艺 | 常规双面板，贴装/手焊/返修可见性好；无内层对位问题 | 压合与对位步骤多，内层不可见，返修与改板成本高 | 按实际装配方式（SMT/手焊）与当期订单工艺核对 [jlc-pcb-rules.md](jlc-pcb-rules.md)；本页不替代报价与工艺确认 |
| 首板风险 | 改板可用割线、飞线补救，调试可见；但 GND 不连续不容易第一眼发现 | 内层不可见，错误往往要改层叠或重投；层数变更使既有布局/布线结论失效 | 首板优先可调试、可返修；选 4 层就必须做过孔审计与平面连通回读 |
| 返工风险 | 割铜、飞线会改变回流与外观，改后必须重跑 DRC 与关键网 | 内层改动成本高；换层、换叠构通常重新打样 | 任何层数或层叠变更后按 RT32 重验受影响网络、间距与铜区，不沿用旧 DRC |

### 1.2 默认倾向

- 小信号、低速、单电源域、器件数不多、无连续参考层要求，且 2 层方案能达到布局阈值时，默认 2 层。
- 2 层板必须 GND 双面铺铜并做缝合；只有单面铺铜不算满足 G4。
- 2 层的“能布”由 `layout-lint` 的 score 与 crossings 支撑，不靠目测稀疏。Skill 默认阈值为 score≥60、crossings≤8；阈值是判断工具，不是自动授权。
- `layout-lint --gate` 已废弃：它只显示历史阈值，不授权、不阻断布线。是否继续布线由当前计划与证据决定。

### 1.3 何时倾向 4 层

满足任一条件时，把 4 层作为候选并写清理由：

- 关键链路需要连续参考层或受控阻抗，而 2 层无法保证参考不被开槽与走线切断。
- 主控、连接器或密集封装的逃线在 2 层上反复交叉，重排后 `layout-lint` 仍明显低于默认阈值。
- 存在多个电源域或较大电流分配，需要独立电源平面降低压降与回路面积。
- 2 层试排后仍只能靠大量过孔和跳线连通，首板调试与返修风险不可接受。

4 层同样有条件：

- 必须声明内层类型（PLANE/SIGNAL/GND/POWER），并说明每层职责；缺内层声明时 G4 不能通过。
- 必须使用 `easycirq pcb power-planes` 建立电源/地平面，而不是把“命名为 GND 的层”当已正确铺铜。
- 必须做过孔审计：层跨度、孔径/外径、是否穿过平面开窗，以及 `pcb check` 的 `via-crosses-plane`、`single-layer-via` 等项。
- 内层错误不可见，首板前应结合 `pcb dump` 与逐层视图核对，而不是只看顶层效果图。

### 1.4 决策记录与失效

- 用 `easycirq pcb stackup show` 回读实际层数；用 `easycirq pcb stackup set` 修改（实际参数以 `stackup set --help` 为准）时必须确认当前工程与目标层数一致。
- 在工程状态中记录 `stackup.layers`、`stackup.decision`（选择与理由）、`stackup.inner_layers`（4 层以上）、`stackup.power_ground_strategy` 与 `stackup.drc_rules_recorded`。
- 层数、铜厚、叠层或板厂工艺变化后，既有铺铜、过孔、阻抗与 DRC 结论全部按失效处理，重新回读再判定。
- 不把自动布线能否跑通当作层数依据；路由器在 2 层上给出结果，不代表布局与回流合格。

## 2. 电源与地策略

### 2.1 先声明再用铜

布线前必须二选一写清策略，并落到工程状态：

- **一层一网**：同一铜层只放一个电源网络（含 GND）的铺铜，优先保证 GND；其他电源用走线或换层分配。
- **铺铜优先级**：同层允许多个网络铺铜，但必须给出明确优先级、间距和回读结果，不能靠创建回执。

2 层用 `easycirq pcb power-pour`：

- `--gnd-layers both` 做 GND 双面铺铜；`--rails pour|skip` 决定是否同时铺电源网络。
- 同层多网时用 `--margin`、`--inset` 控制边界，用 `--replace` 或 `--rebuild` 重铺后必须回读。
- 创建回执不是最终状态。真实案例中创建回执为 priority 1/1/2 且 `priorityVerified:false`，重载后 `pcb pour-list` 读到 GND L1 的 priority 变成 3；以重载后的 `pour-list` 为准。

4 层用 `easycirq pcb power-planes`：

- 该命令需要至少 4 层；2 层会被拒绝并提示改用 `power-pour`，不要反复重试。
- 用 `easycirq pcb power-planes` 建立电源/地平面（层号、gnd/power 层与是否改叠层的参数以 `power-planes --help` 为准）；平面建立后回读 `stackup show` 与 `pour-list`，确认层号、网络与连通，不把命令回执当完成。

### 2.2 GND：双层铺铜加缝合

- 2 层板 GND 必须覆盖两层；4 层板至少一个完整地平面，其余层按回流需要铺铜。
- 铺铜后用 `easycirq pcb via-stitch` 增加缝合孔，再用 `easycirq pcb via-list` 审计；确认缝合孔真的落到目标平面或铺铜上（RT30），不是等距排满全板就算完成。
- 用 `easycirq pcb pour-list` 与 `easycirq pcb dump` 检查孤岛、狭颈与意外分割（RT27、RT28）。轮廓、网名和颜色都不证明已铺铜。
- 同层多网铺铜要回读优先级和实际连通；`netless-pour`、`power-not-poured` 是 `pcb check` 的直接信号，不能忽略。
- 铺铜后重新计算连接与 DRC；铺铜前后各留一份 DRC 与 pour 回读，作为对比基线。

### 2.3 铺铜板上不布 GND 细线

- GND 连通优先由铺铜、缝合孔和短而宽的铜皮出口完成；不要在已经铺铜的板上用大量 GND track 代替铜区。
- 真实案例：在已有 4 个铺铜的板上执行 `easycirq pcb route-short --route-power`，产生 73 条 route（GND 45、+5V 21、VREF 7；2 条 VREF 失败），实际 drawn 71、vias 14；随后 DRC 93（71 Clearance + 22 Connection），其中 net=GND 的 Clearance 68 条。
- 这批 GND track 是 20 mil，不属于“细线”。问题不是线太细，而是铺铜板上把大量 GND 改成走线，和既有铜/焊盘产生间隙冲突。把“GND 20 mil”当成根因会修错方向。
- 确需 GND 走线时，按 net class 给足宽度并说明为什么铺铜不能覆盖，改完重新铺铜、重新 DRC。
- GND 走线宽度与是否存在要在计划中给出依据；是否有自动检查以 [design-gates.md](design-gates.md) 与实际门禁实现为准，不要用“看起来够粗”代替回读。

### 2.4 电源线宽按 net class

- 先用 `easycirq pcb net-classes` 回读当前网络类，确认 +5V、VREF 等电源网属于哪个类，再决定宽度；没有类就先建类，不逐段随手改宽。
- 线宽依据是载流、允许温升、铜厚、压降、环境与脉冲/持续负载（RT01、RT02、RT03），不是“1 mm 几安”的口诀。
- `+5V` 与 `VREF` 分别按各自负载与允许压降给宽；VREF 还要考虑采样精度，不能为了走线方便随意变宽或换层。
- `route-short --width` 只能作为候选宽度，最终以 net class 与 `pcb check` 的 `width-under-spec`、`width-mismatch` 为准。
- `+5V` 的回路与回流一起检查：输入滤波/保护靠近连接器或入口，主干到负载的回路面积尽量小；回流经连续 GND 铺铜/平面，跨分割处补缝合，避免长悬空支路。
- 高电流同时检查过孔、焊盘颈缩、端子和热连接；只加宽中间长线不解决最窄瓶颈。

### 2.5 过孔审计

- 用 `easycirq pcb via-list` 与 `easycirq pcb dump` 回读全部过孔，核对孔径、外径、层跨度与所在网络，并与 `pcb drc-rules`、net class 和板厂能力对照。
- 过孔证据带 `staleRisk` 时不能作为权威结果；必须保存工程、`easycirq doc reload` 后重新回读。
- 4 层板重点看 `via-crosses-plane`、`single-layer-via`、`overlapping-via`；缝合孔还要确认没有把 GND 与电源平面短接。
- 过孔数量与位置服从回流、屏蔽、散热与制造需要（RT30、RT16），不是越多越好；散热焊盘上的孔另行核对塞孔/填孔与焊料流失。

## 3. 自动布线只作候选

自动布线是加速手段，不是完成标志。`route-short` 与 `pcb autoroute` 都按候选处理。

### 3.1 先 dry-run

- 先运行 `easycirq pcb route-short --dry-run`，检查计划布多少条、跳过哪些网络、准备打多少过孔；再决定是否执行。
- 重点看 skipped nets：电源、地、关键信号被跳过时，不能把剩余条数当作完成度。
- 执行后核对实际 routes 与 vias；命令返回的数量是动作回执，不等于电气连通。

### 3.2 不在铺铜板上 `--route-power`

- `route-short` 默认跳过 power/GND；`--route-power` 会强制把电源/地布成 track。其帮助自述这是第一号 DRC 来源。
- 已经在板上铺了 GND/电源铜时，不要再跑 `--route-power`。真实案例正是铺铜后执行该选项，DRC 从 30 升到 93，其中 68 条是 GND Clearance。
- 若确实需要电源走线分配，应在铺铜前完成，或在 net class 中给出足够宽度并接受重新铺铜与重新 DRC 的代价。

### 3.3 `pcb autoroute` 同样是候选

- `easycirq pcb autoroute` 走外部 Freerouting 流程：导出 DSN、外部布线、回导 SES、导入、再 DRC。
- 回导后必须重新检查网络、规则、层与机械约束（RT35），不能把“DSN 导出成功”或“路由完成”当 PCB 完成。
- 外部路由器不了解你的 G3/G4 约束，跳过的网络、错误的层、过孔与平面冲突都要自己复核。

### 3.4 候选的验收动作

无论哪种自动布线，采纳前至少完成：

1. `easycirq pcb drc --json` 并读取完整结果，不用截断文件。
2. `easycirq pcb check --json` 查 `dangling-end`、`acute-angle`、`width-under-spec`、`power-not-poured` 等。
3. 关键网逐条 `easycirq pcb net-path`。
4. `easycirq pcb dump` 回读真实铜与过孔。
5. 保存工程、`easycirq doc reload`、重新回读。

## 4. 布线顺序与计划

### 4.1 布线前的前置条件

- G3 布局已冻结：目标板框、安装孔、连接器逃逸已记录，`layout-lint` 达标，器件不再随意移动。
- G4 电源地策略已声明：层数、内层类型、铺铜/平面方式、GND 策略与 DRC 规则已写入。
- 网络类已建立并回读；关键网清单已确定。
- 已保存一份布线前 DRC 基线。没有基线，后续无法区分“新引入”和“原本就有”。

### 4.2 顺序

| 顺序 | 内容 | 进入条件 | 退出证据 |
|---|---|---|---|
| 1 | 电源/地：铺铜、平面、缝合孔、必要的电源走线 | G4 声明完成，层叠回读一致 | `pour-list`、`via-list`、`pcb check` 无 `power-not-poured` |
| 2 | 关键信号：时钟、模拟/采样、反馈、差分、复位/使能、保护泄放 | 电源地稳定，关键网清单已记录 | 逐网 `net-path` 与局部铜回读 |
| 3 | 普通信号与剩余网络 | 关键信号完成且 DRC 无新增阻断 | 完整 DRC、未布网络清单 |

- 顺序不是教条：电源地未稳定就布关键信号，后面会被铺铜和回流改动推翻。
- 每完成一组就回读一次真实铜与 DRC；不要等全部布完再发现电源地策略错了。
- 布线期间移动已布器件按 RT32 处理：重查关联铜、过孔、参考、热焊盘与丝印（PL31）。

### 4.3 层、通道与过孔计划

- 每层写清角色（信号/地/电源/混合）、主要走向与禁布区；通道在连接器与主控之间预留，不靠布线时临时挤。
- 连接器密集区、QFN/BGA 逃线先试排；拥挤区域不能靠自动布局总分证明能布（PL29）。
- 可用 `easycirq pcb layout-plan`、`easycirq pcb place-constrained` 辅助规划禁布与通道；它们只生成计划/约束，不代表实际铜已连。
- 过孔计划写明类型、孔径/外径、允许层跨度、用途与数量预期；4 层以上还要写平面开窗与反焊盘要求。
- 任何 `--no-avoid`、`--no-multilayer` 之类的放宽选项默认不用；确需使用时记录理由与复验范围。

### 4.4 连接器逃逸

- 接口无源件（USB-C 的 CC 电阻、TVS/ESD、滤波）距连接器 ≤5 mm，放在连接器同侧、被保护节点之前，不做长支路；超过 5 mm 视为不满足，写入 `layout.connector_escape.max_distance_mm`。
- TVS/ESD 必须位于连接器与受保护网络之间的逃逸路径上，先泄放到参考，再进入板内（PL15、RT08）；不能放在全板末端。
- 连接器 slot 与开槽区域禁止走线、铺铜和放孔；记录 `slot_clear`，并逐层核对铜与孔到槽的距离（RT31）。
- 采用 SOP 式成组放件：连接器 → CC/限流电阻 → TVS/ESD → 被保护网络，按固定顺序同向摆放，便于目检、返修与自动检查。
- 可用 `easycirq pcb escape-plan` 生成逃逸规划（实际参数以 `escape-plan --help` 为准），再与真实布局回读对照。
- G3 记录 `layout.connector_escape`（`max_distance_mm`、`slot_clear`）；未记录时按 BLOCKED 处理，不靠口头说明。

### 4.5 温度传感器热设计（NTC/RTD/数字）

- 位置远离蜂鸣器、LDO/稳压器、USB 连接器、功率电阻和 MCU 等热源；测的是目标环境温度，不是隔壁器件的板温。
- 铜与开槽：不要给 NTC 挂大面积铜（热质量拖慢响应并把板温当环境温）；必要时在传感器与热源之间开槽或做细颈，权衡板强度与回流影响。
- 气流与外壳：传感器靠近外壳气孔/气流路径，避开死腔；涂覆、灌封和安装姿态都会改变响应，需与机械一起确认。
- 远程探头选项：NTC 可外接导线到远端，响应更真实但增加连接器、线束固定与抗干扰成本；在布局前决定并记录取舍。
- 距离用实际焊盘/封装几何测量，不填估算值；记录模板与证据要求见 [温度传感器记录](../assets/docs/thermal-sensor.md)。G3 未记录位置/热源距离时按待确认处理，实测精度未做标 `NOT RUN`。

### 4.6 停止条件

- 连续 3 轮 DRC 改善都小于 30% 时触发停止规则（`DRC_PLATEAU`）：停止在同一布局上重复同一操作。
- 改善率 =（上一轮 total − 本轮 total）/ 上一轮 total；上一轮为 0 时已达标。停止时记录触发轮次与前后总数，不能只写“效果不好”。
- 触发后选择一条路并写清理由：重排关键器件、改层/改通道、评估 4 层、拆分功能，或如实报告剩余问题。
- 在工程状态中记录 `routing.drc_rounds` 每轮 total 与 `routing.stop_rule_triggered`；停止不是失败，反复打地鼠才是。
- `pcb drc` 需要 PCB 为活动前台；后台或遮挡窗口会算不完。超时后切前台重跑一次，不循环重试。

## 5. 关键网证明

### 5.1 选哪些网

关键网清单写入 `routing.key_nets`，至少覆盖：功能连续性的信号主路径、反馈/采样、时钟、复位/使能、保护泄放，以及以走线分配而非铺铜分配的电源。

- 铺铜或内电层承担的 GND/电源，不要写成“已由 net-path 证明”。计划里单独列 pour/plane 证据，并注明 net-path 不覆盖。
- 关键网清单由设计决定，不由路由器输出决定。

### 5.2 `net-path` 的用法

- 逐网运行：`easycirq pcb net-path --from D.PAD --to D.PAD --net NAME --json`，必要时加 `--through`、`--layer`。
- 每次结果单独落盘，一条证据对应一个网；写入 `routing.key_net_proofs`。
- `--from`/`--to` 用真实位号与焊盘号，不用网名代替对象；`--net` 用于消除同名歧义。

### 5.3 `net-path` 的边界

- 它只证明列出的已布铜（routed copper）能连通首尾；铺铜、内电层、填充区域不计入。
- 失败表示“未被走线证明”，不等于全板断连；反过来，成功也不证明载流、回流或 SI/PI 合格。
- 因此：以走线承担的关键信号必须有 `net-path`；以铺铜/平面承担的电源地必须另有 `pour-list` 与 `dump` 证据。两者不能互相替代。
- 当某个关键网只能靠铺铜连通时，如实标注“net-path 不覆盖”，按门禁的证据规则处理；不能用一句“铺铜应该连着”写成 `PASS`。若使用 `PASS_WITH_WAIVER`，必须写明理由、条件和剩余风险。

### 5.4 保存与重载

- 布线、铺铜、移件、改层或改规则后，保存工程并执行 `easycirq doc reload`，再重新回读。
- 重新回读至少包括：`pcb drc`、关键网 `net-path`、`pcb pour-list`、`pcb via-list`、`pcb dump`。
- 回读结果与保存前一致才谈 G5；`save` 回执、截图或旧 JSON 都不能代替重开后的新鲜读回。

## 6. 与 RT/PL 编号的关系

本页只给出流程与判定，不复制条款正文。需要具体检查方法时按主题打开对应文档：

| 主题 | 引用编号 | 文档 |
|---|---|---|
| 载流、线宽、电源分配 | RT01–RT03 | [布线与回流细节](pcb-routing-details.md) |
| 参考层、换层回流、地路径 | RT04–RT06 | [布线与回流细节](pcb-routing-details.md) |
| Kelvin、保护泄放、栅驱、隔离 | RT07–RT10 | [布线与回流细节](pcb-routing-details.md) |
| 阻抗、差分、时序、串扰、过孔与支路 | RT11–RT20 | [布线与回流细节](pcb-routing-details.md) |
| 模拟、时钟、RF | RT21–RT26 | [布线与回流细节](pcb-routing-details.md) |
| 铜区、孤岛、热连接、缝合、铜到边 | RT27–RT31 | [布线与回流细节](pcb-routing-details.md) |
| 移动后重验、实际连通、视觉复核、诚实记录 | RT32–RT35 | [布线与回流细节](pcb-routing-details.md) |
| 电源回路放件、输入电容、保护靠边界 | PL09–PL15 | [PCB布局细节](pcb-placement-details.md) |
| 去耦、敏感节点、参考与采样 | PL17–PL18、PL21–PL23 | [PCB布局细节](pcb-placement-details.md) |
| 通道预留、移动后重验、布局验收 | PL29、PL31–PL32 | [PCB布局细节](pcb-placement-details.md) |

- 编号只有上述两份文档有权定义；本页不新增、不改写、不扩写编号含义。
- 若本页与编号原文冲突，以编号原文和当前器件/板厂资料为准，并回改本页。
- 证据记录方式见 [证据与轻量记录](evidence.md)；EDA 前台/重载/保存边界见 [EDA执行](eda-execution.md)。

## 7. 真实反例

以下均来自同一块温度报警板的实际执行记录，数字按现场证据保留。

### 7.1 布局门禁未过就布线

- 15:38:01 `outline-fit --margin 100` 得到板框 3577.55 × 2176.76 mil；15:38:28 `pcb layout-lint` 为 score 48/100（hard）：28 个器件，0 short、0 overlap、0 off-board、0 tight，13 个信号网、ratsnest 17073 mil、13 crossings。
- 默认阈值是 score≥60、crossings≤8；这次两项都不满足。15:38:54 仍然执行 `route-short`，得到 74 routes、26 vias。
- 教训：`layout-lint --gate` 已废弃，不会阻断；Skill 自己定的阈值也不会自动拦住命令。门禁结论是 `BLOCKED` 时，布线依赖链应暂停，先把布局改到可布，而不是先跑路由器。

### 7.2 没有基线，铺铜后的 27 条断连无法归因

- `power-pour` 默认 `railsMode=pour`，创建了 4 个铺铜：GND L1、GND L2、+5V L1、VREF L1。
- 铺铜后首次 DRC 为 30（3 Clearance + 27 Connection）。此前没有 DRC 基线，因此“27 条断连由铺铜造成”只是时间顺序推断，不能写成已证明。
- 教训：布线前、铺铜前、每次大改后各留一份完整 DRC。没有基线时，只能报告“观察到 27 条 Connection”，不能报告“铺铜导致了 27 条”。

### 7.3 `--route-power` 把 30 变成 93

- 在已铺铜的板上执行 `easycirq pcb route-short --route-power`：计划 73 条 route（GND 45、+5V 21、VREF 7；2 条 VREF 失败），实际 drawn 71、vias 14。
- 随后 DRC 为 93（71 Clearance + 22 Connection），其中 net=GND 的 Clearance 68 条。GND track 宽度是 20 mil。
- 教训：铺铜板上不要用 `--route-power` 把 GND 改成大量走线；20 mil 不是“细线”，根因是走线与铺铜/焊盘的间隙冲突。出现这种结果应回退该批 GND 走线、恢复铺铜连通，而不是继续调线宽。

### 7.4 先布线后移件，净长大幅变化

- 布线 15:38:54 开始；15:50:47 才把 R1/R2 从 (1359.2,-1326.9)/(126.0,-410.5) 移到 J1 旁的 (820,-1750)/(950,-1750)。
- D1_N4 长度从 2519.2 mil 变为 343.8 mil；D1_N3 从 1234.2 mil 变为 493.5 mil。
- 教训：布局未冻结就布线，后续移件会改写关键网长度与回流路径，之前的关键网证明与 DRC 全部失效。按 RT32、PL31 重验，不能沿用旧报告。

### 7.5 铺铜优先级以重载回读为准

- `power-pour` 创建回执的 priority 为 1/1/2，且 `priorityVerified:false`；重载后 `pcb pour-list` 读到 GND L1 的 priority=3。
- 教训：创建回执不是最终状态。同层多网铺铜必须保存、重载、回读，确认优先级和实际连通后再继续。

### 7.6 最终状态：2 层通道冲突与 DRC 18

- 项目为 2 层板，90.87 × 55.29 mm、26 个器件、GND 双层铺铜；CC/VBUS、REF_TOP、VREF、OUT 在 2 层上争同一通道，连接器上方与 R15/R16/GATE 附近反复过近。
- 最终 `pcb drc --json` 为 18 条（16 Clearance + 2 Connection，`passed:false`），`layout-lint` 为 48/100（hard）、13 crossings，且没有安装孔；只能算布线草稿，不能导出 Gerber 下单。
- 教训：G3 的 48/100 与 13 crossings 已低于默认门槛（60/8），应冻结布局并重排或改 4 层；G4 未预先声明 2 层下的电源/地分配与通道规划；G5 未按轮次记录并执行停止规则，才会在 18 条时继续逐条挪线。证据见项目 `evidence/pcb-drc-11.json` 与 `evidence/layout-lint-all.json`。

## 8. 布线前与退出检查表

| 检查项 | 证据 | 门禁 | 通过条件 |
|---|---|---|---|
| 层数与内层 | `stackup show` 回读、`stackup.layers`、`inner_layers` | G4 | 声明层数 = 实际层数；4 层有内层类型 |
| 层数决策 | `stackup.decision`（选择、理由、成本/可布性/风险取舍） | G4 | 有明确选择与条件，不是默认值 |
| 电源地策略 | `stackup.power_ground_strategy`、`pour-list` | G4 | 一层一网或优先级已声明并回读 |
| GND 铺铜 | `pour-list`、`dump` | G4 | 2 层双层 GND；无孤岛与意外分割 |
| GND 细线 | `pcb dump` 的 GND 线宽审计 | G4 | 不存在低于规则下限的 GND 线 |
| 过孔审计 | `via-list`、`dump`、重载后回读 | G4 | 孔径/外径/层跨度可核对，无 `staleRisk` |
| DRC 规则 | 布线前记录 clearance/线宽/过孔/net class | G4 | 已记录且与实际板一致 |
| 布局冻结 | `layout-lint`、板框、安装孔、连接器逃逸 | G3 | score/crossings 达标，0 overlap/off-board，逃逸 ≤5 mm 且避开 slot |
| 布线计划 | [布线计划模板](../assets/routing-plan.md) 填写结果 | G5 | 层/通道/过孔/net class/顺序/停止条件齐全 |
| 完整 DRC | `easycirq pcb drc --json` 完整文件 | G5 | `passed:true`，0 Connection |
| 关键网证明 | 逐网 `net-path --json` | G5 | 每个 `routing.key_nets` 有证据；铺铜承担的网另证 |
| 保存重载 | 保存 → `easycirq doc reload` → 新鲜回读 | G5 | 内容一致，无 stale |
| 丝印 | `easycirq pcb silk-align` 回读 | G5 | 无压焊盘、极性/位号可读 |
| 停止规则 | `routing.drc_rounds`、`stop_rule_triggered` | G5 | 连续 3 轮改善 <30% 时已停止并改策略 |

- 表中任一项缺证据 → `BLOCKED`；带理由和剩余风险的例外 → `PASS_WITH_WAIVER`；无 CLI 覆盖的人工项 → `UNSUPPORTED` 并进 `not_checked`。
- `PASS` 必须写清方法、对象、版本与范围；不要把“跑过命令”写成 `PASS`。
- 门禁失败只暂停依赖链路：布线不能继续时，仍可补证据、改布局、更新计划或做不依赖该结果的检查。

## 9. 常见误用

- 把 `layout-lint --gate` 当布线授权，或把 score 当电气合格证明。
- 把 `route-short` 的 routes 数量、`pcb autoroute` 的完成提示当布线完成。
- 在铺铜板上执行 `--route-power`，然后用调线宽继续救 DRC。
- 把 GND 网名、绿色铺铜外观或 `pour-list` 里的网名当真实连通。
- 把 `net-path` 失败直接判为全板断连，或把铺铜连通写成 `net-path` 已证明。
- 没有 DRC 基线就归因；没有 `doc reload` 就用旧回读。
- 布局未冻结先布线，移件后不重验关键网与 DRC。
- 把 `PASS_WITH_WAIVER` 当 `PASS` 汇报，不写理由、条件与剩余风险。
