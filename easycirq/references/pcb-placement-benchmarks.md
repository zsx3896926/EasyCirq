# PCB 预布局基准集（12 案例）

这是一组**故意有缺陷的离线几何/网表快照**：每块虚拟小板给出板框、禁布区、固定件、器件、网络，以及一份**待判的候选布局**。用途是让 Agent 和工程师在“预布局决策”这一类任务上有一致的最低验收面，并练习区分 `blocking` / `review` / `acceptable`。

它不是 12 块可直接打样的板，也不是真实 EDA 工程的替代品。**任何案例通过都不代表真实工程通过**；离线判分不覆盖 DRC、可布通、阻抗、EMC、热与装配。

运行（在 `easycirq/` 目录下；数据默认在 `assets/pcb-placement-benchmarks/benchmarks.json`，可用 `--cases` 覆盖）：

```bash
python scripts/pcb_placement_benchmark.py --list
python scripts/pcb_placement_benchmark.py --case P1-MCU-MIN
python scripts/pcb_placement_benchmark.py --case P1-MCU-MIN --json --out card.json
python scripts/pcb_placement_benchmark.py --all
python scripts/pcb_placement_benchmark.py --all --json --out results.json
```

退出码：`0` = 案例 acceptable / 全案例与 expected 匹配；`1` = 案例 review / 存在不匹配；`2` = 案例 blocking；`3` = 案例数据非法；`4` = 用法或 IO 错误。`--json` 时 stdout 只有一个 JSON，人读信息进 stderr；`--out` 原子写，不得等于输入。

`expected` 只表示**该案例应复现这些 finding**，不是电气结论；12 个案例也没有在真实 EDA 中逐个绘制、回读、DRC 或打样。

## 1. 十二个案例

单位均为 `mm`，角度 `deg`（逆时针为正）。坐标是教学构造，**不要**把任何案例坐标抄进真实工程。

| ID | 域 | 候选布局的问题 | 可接受布局的目标 | 期望判定（codes） | 真实工程还要看什么（不得写成已检查） |
|---|---|---|---|---|---|
| `P1-MCU-MIN` | mcu | 去耦电容放在板子对角的远端（晶体保持靠近 `XIN`/`XOUT`） | 去耦焊盘到 `VDD`/`GND` 焊盘回路短且不绕行；晶体贴近时钟脚 | review：`distance_far` | 去耦地过孔/共用段与层叠位置、晶体负载电容与负阻裕度、起振与频偏、晶体地屏蔽/禁布区 |
| `P1b-MCU-MIN-PAIR` | mcu | 只把 `C1`/`C2` 移到 `VDD`/`GND` 焊盘旁，其余不变 | 与 `P1-MCU-MIN` 同，只改这一组坐标 | acceptable：无 | 同 `P1`；翻转只证明“这组坐标是主导项”，不证明整板可布 |
| `P2-BUCK` | power | 输入电容远离 `SW` 回路（反馈件在阈值内，取样点/补偿作人工复核项） | 输入电容靠开关管/电感闭合高频回路，反馈从规定取样点引出 | review：`loop_large` | 高 `di/dt` 回路面积与电容端子、`SW` 铜面积、反馈取样点/补偿、地回流与热 |
| `P2b-BUCK-PAIR` | power | 只把输入电容与 `SW` 电感靠拢，其余不变 | 与 `P2-BUCK` 同，只改这一组坐标 | acceptable：无 | 同上；靠拢后反馈、散热与测试点是否被挤走 |
| `P3-ANALOG` | analog | 传感器入口与基准件放在 Buck 电感/二极管旁 | 模拟链远离功率级，保护泄放不污染小信号参考 | review：`distance_far` | 耦合路径与回路、参考旁路/采样回流、护环与漏电、屏蔽/分区、入口保护位置 |
| `P3b-ANALOG-PAIR` | analog | 只把模拟链整体挪到远离功率级一侧 | 与 `P3-ANALOG` 同，只改这一组坐标 | acceptable：无 | 挪远后 HPWL/走线长度、入口保护与连接器是否仍成立 |
| `P4-COMM` | comm | 隔离器/终端布局与连接器朝向冲突：终端电阻跨隔离侧 | 连接器贴声明边，终端在隔离侧内，保护先于被保护端 | blocking：`connector_off_edge` | 插头壳体/卡扣/线缆弯曲半径（3D 与实物）、隔离爬电/间隙、A/B 极性与终端位置 |
| `P5-BATTERY` | battery | 保护 IC/检流电阻远离电池端子；热敏贴在充电 IC 上 | 保护/检流靠端子，NTC 测电池温度而不是充电 IC | review：`distance_far` | 保护响应回路、检流 Kelvin 与功率回路分段、NTC 热路径/电池热阻、电池/外壳热耦合与机械 |
| `P6-MOTOR` | motor | 栅极驱动回路跨越大电流地；分流器取样从远端绕回 | 驱动器/栅阻/源回路成组，分流器从采样端取 Kelvin | review：`loop_large` | 开关 `di/dt` 与共阻抗、栅极振荡/米勒、分流器方向与功率流、SOA 与热 |
| `P7-WIRELESS` | wireless | 模组压在天线净空里；净空区被电容/固定件占用 | 净空区无器件；铜/过孔/固定件按该模组指南另查 | blocking：`keepout_violation` | 天线全层净空、参考地与馈线/匹配、外壳/电池/螺钉、实际 OTA/SAR |
| `P8-MULTI` | multi | 连接器不在板边；连接器与固定件让位区相交；逃线通道被大件堵死 | 接口贴边、不进入固定件让位区、关键逃线通道预留 | blocking：`connector_off_edge`、`body_overlap` | 插拔空间与装配顺序、螺钉头工具扫掠、BGA/QFN 逃线、3D/机械干涉 |
| `P8b-MULTI-PAIR` | multi | 只把连接器推到板边并让开固定件，其余不变 | 与 `P8-MULTI` 同，只改这一组坐标 | acceptable：无 | 同上；逃线通道仍可能不足——离线判分只看几何，不等于能布 |

8 个主例覆盖硬/软两类失败；4 个 `*-PAIR` 变体各自只改一组坐标，用来训练“只改一个条件、结论是否翻转”。

> `P1-MCU-MIN` 的晶体与 `P2-BUCK` 的反馈件在阈值内，**不**是判分失败项；它们仍是真实工程的人工复核点（`inspection`），不要因为离线没报就写成“已确认没问题”。最终案例数据以 `benchmarks.json` 为准。

## 2. 案例与 PL 条目对应

编号按 [PCB 布局细节](pcb-placement-details.md) 的现有条目引用（契约 §2 里的 `basis` 只是示意；编号与条目文本冲突时，以该文件条目文本为准）。机制解释见 [PCB 机制卡](pcb-lessons.md) 与 [PCB 工程习惯](pcb.md)。

| 案例 | 主要 PL 条目 | 判据落点 |
|---|---|---|
| `P1-MCU-MIN` / `P1b-MCU-MIN-PAIR` | PL17、PL18、PL19 | 去耦按焊盘回路；晶体局部区贴近时钟脚 |
| `P2-BUCK` / `P2b-BUCK-PAIR` | PL09、PL10、PL11、PL12 | 先画电流回路；输入电容端子落点；`SW` 铜范围；反馈取样点 |
| `P3-ANALOG` / `P3b-ANALOG-PAIR` | PL21、PL22、PL23 | 模拟链顺序与保护泄放；高阻节点；参考/采样回路 |
| `P4-COMM` | PL03、PL04、PL15 | 接口可插拔；正反面与观察方向；保护靠边界 |
| `P5-BATTERY` | PL14、PL15、PL16、PL24 | 分流器方向与采样端；保护靠边界；测温位置测目标而非隔壁热源 |
| `P6-MOTOR` | PL13、PL14、PL09 | 栅极回路成组；分流器采样端；大电流回流 |
| `P7-WIRELESS` | PL26、PL27 | RF 路径位置优先；天线全层净空 |
| `P8-MULTI` / `P8b-MULTI-PAIR` | PL03、PL05、PL29 | 连接器贴边可插拔；高度/堆叠；预留走线通道 |

## 3. 判分语义怎么读

scorecard 分 `hard`、`soft`、`metrics` 三块。**硬检查只报 code 与对象，不做因果推断**；同一缺陷按 `code` + 对象去重。

**硬检查（任一命中 → `blocking`）**

| code | 判定 |
|---|---|
| `missing_placement` | 非固定件缺 `placement` 项（数据/布局不完整） |
| `out_of_board` | 器件包围盒超出板框（容差 0） |
| `body_overlap` | 两个器件包围盒相交面积 > `overlap_tol_mm2`（v1 只判同面） |
| `keepout_violation` | 器件包围盒与 `board.keepouts[].rect_mm` 相交面积 > 0 |
| `rotation_not_allowed` | `rot_deg` 不在 `allowed_rotations` |
| `fixed_moved` | `fixed:true` 的坐标与 `fixed_xy_mm` 不一致 |
| `connector_off_edge` | 声明了 `board.connectors`，但器件到声明边距离 > `connector_edge_tol_mm` |

**软检查（不阻断，但降级为 `review`）**

| code | 来源 | 说明 |
|---|---|---|
| `distance_far` | `checks[].code=max_distance` | 所列焊盘两两最大距离 > `max_mm`；去耦/晶振/模拟入口等都用它，靠 `basis` 说明为什么 |
| `loop_large` | `checks[].code=loop_span` | 所列焊盘两两最大距离（回路跨度代理）> `max_mm` |
| `hpwl_high` | 全局 | `Σ_net (max_x-min_x + max_y-min_y)` > `rubric.hpwl_max_mm`；按 `class` 分项只记录，不进阈值 |
| `congestion_hotspot` | 全局 | 2 mm 网格上每个网络按焊盘 bbox 覆盖 cell 计数，`max cell 计数` > `rubric.congestion_max` |

口径（与契约 §3.3 一致）：

- `soft` 数组**只放 `case.checks` 的逐项结果**，每项含 `check_id/code/value_mm/max_mm/ok/basis`。
- 全局代理（HPWL/congestion）**只进 `metrics`**；超限时以 `hpwl_high` / `congestion_hotspot` 进 `expected.codes`，**不**进 `soft`。
- `expected.codes` = 硬检查 code ∪ 软检查具体 code（`distance_far` / `loop_large` / `hpwl_high` / `congestion_hotspot`）。v1 **没有**笼统的兜底 code；未知 `checks[].code` 的案例数据应判 `invalid_case`，不产出软检查 code。
- `expected.soft_fail` 只比较 `case.checks` 的 id（如 `ck-decoup`），不含任何全局项。

**verdict 与训练中的结论类型**

| verdict | 触发条件 | 结论类型 | 允许怎么表述 |
|---|---|---|---|
| `blocking` | 任一硬检查命中 | `可确认`（仅限该案例几何/网表前提） | “在本案例数据下可确认越界/相交/净空/贴边失败” |
| `review` | 无硬检查命中，但任一软检查失败 | `条件` | “在这里可确认超阈值；真实后果取决于层叠/回路/器件” |
| `acceptable` | 无硬检查命中、无软检查失败 | `可确认`（限本案例未触发检查项） | “本案例数据未触发检查”**不是**“这块板能布/能打样” |

判分器输出固定字段 `placement_applied:false`、`routing_verified:false`、`drc:"NOT RUN"`、`eda_calls:0`——这四个字段是本契约的边界声明，不能改写成 `true` 或“已验证”。

## 4. 五维评分维度

用来给“人的预布局判断”打分（也用于 [审题练习](engineering-deepdives/exercises-pcb/README.md)）。

| 维度 | 看什么 | 合格表现 | 不合格表现 |
|---|---|---|---|
| 结论类型 | 是否区分 `可确认` / `条件` / `待补`，是否把软件失败说成硬错误 | “本案例内硬检查可确认”与“真实工程需复核”分开说 | 把 `review` 说成 `acceptable`，或把软检查超阈值说成已证实会失效 |
| 机制 | 能否说出电流回路/回流路径、耦合、热路径、机械干涉 | 指出去耦按焊盘回路、Buck 高 `di/dt` 回路、栅驱共阻抗等具体机制 | 只重复 code 名称或“布局不整齐” |
| 证据 | 能否指到案例 id、finding code、检查 id、PL 条目；真实工程再指手册/网表 | “`P2-BUCK` 的 `loop_large` 对应 PL09/PL10” | 只说“感觉有问题”、不引用任何编号 |
| 行动 | 修复是否与判定匹配、是否过度 | `blocking` 先改硬约束；`review` 先改主导软项；`acceptable` 不扩写成放行 | 见 `review` 就整板重排，或只改一个不相关坐标 |
| 未知 | 是否列出本案例不能回答的项并停止判断 | 明确写 `NOT RUN`：DRC、布线、阻抗、热、装配 | 用离线分数推断“能布通/能打样” |

## 5. 常见“假通过”

实现与审题时都要主动避免：

1. 缺尺寸/缺 placement 时补默认值，凑出一个 `acceptable`；缺数据只能 `invalid_case` 或 `待补`。
2. 去耦距离用器件中心距，而不是焊盘/回路距离。
3. 连接器在板内但没贴边，被判 `acceptable`。
4. 天线净空只查器件中心点，不查包围盒相交。
5. HPWL 低就判 `acceptable`（必须另有硬检查与显式软检查；HPWL 只进 `metrics`，超限才以 `hpwl_high` 进 `codes`）。
6. 只改一个坐标的成对案例结论不翻转——说明该条件不是主导项，应重设案例而不是强行解释。
7. `--all` 不看 `expected`，只要脚本不崩就 exit 0。
8. 把 `review` 当 `acceptable` 汇报，或把 `blocking` 说成“只是风格问题”。

## 6. 边界

- **离线几何/网表代理**：v1 只判矩形包围盒、引脚坐标、网络连通与三类代理指标。它不读铜、不读叠层、不读 3D。
- **不是 DRC**：只判同面本体相交，不判线距/焊盘间距/丝印/阻焊/孔环/板边铜。
- **不是可布通**：`hpwl_high` 与 `congestion_hotspot` 只是便宜代理，不能证明或否定可布通。
- **不是阻抗/热/EMC/机械/装配**：这些都要真实叠层、仿真、测量或 3D/实物；案例里的 `inspection` 字段与本文“真实还要看什么”列只列检查方向。
- **不是真机验证**：12 个案例是 `synthetic` 教学构造，未在真实 EDA 中绘制、未回读、未 DRC、未打样。任何输出都固定 `drc:"NOT RUN"`。

因此：

- 训练结论只覆盖“本案例的预布局判断”，不外推到“这块板能打样/能布通/满足阻抗”。
- 引用案例时用 `id` + `code`，不要抄坐标；真实工程必须从自己的 EDA/库回读实际焊盘与约束。
- 需要升级为“真实案例”时，至少要有：真实工程副本、器件/封装身份、引脚与网络回读、实际导图、DRC 与打样记录；缺一项就保持“离线示意/未执行”。

## 7. 使用顺序

1. 先读案例的 `problem` / `target` / `inspection`，理解要解决什么，**不抄坐标**。
2. `--list` 看全 12 条；`--case <ID> --json` 导出 scorecard，逐项读 `hard` / `soft` / `metrics` / `expected_match`。
3. 对每个 finding 判断：是真实硬约束命中、软代理超阈值，还是数据缺失造成的 `invalid_case`。
4. 用 [审题练习](engineering-deepdives/exercises-pcb/README.md) 检验自己能否区分“明确错误 / 条件风险 / 有意取舍 / 看似异常实际合理 / 信息不足”；独立试答用无题型提示版。
5. 真实任务中按 [PCB 工程习惯](pcb.md) 的布局顺序执行，并按 [PCB 布局细节](pcb-placement-details.md) 选择具体 PL 条目落到实际工具约束；离线判分只作预筛，不作验收。
