# 设计：离线电气意图审查（任务 B）

## 1. 目标与边界

网表逐脚一致只证明“实现忠实于设计源”，不证明“设计源正确”。本模块把
**设计意图（intent）+ 真实器件事实（device_facts）+ 连通性/几何证据** 三者对齐，
在保存、DRC、连通性检查之外发现可定位的电气意图错误：

- 飞跨/耦合电容两端被命名/短接到同一网络；
- 电容额定耐压与所在节点实际差分应力不匹配（含项目降额策略）；
- 四脚按键内部常通组被当成两个独立节点；
- 特殊引脚能力（输入/输出/开漏/电源域）与声明角色冲突；
- 裸露/合并焊盘遗漏、错网或被默认接地；
- 电容角色不可追溯、局部去耦距离套用经验阈值。

不做：实时 EDA、DRC、仿真、波形求解、任意模拟网络求解、自动改设计、商城/库存、
版本发布。本模块 0 次 EDA 调用，不联网。

## 2. 架构

```
design-hardware/scripts/electrical_review/
  __main__.py        python -m electrical_review
  cli.py             validate / review / explain、退出码、原子写
  contract.py        严格输入校验、归一化、网络别名并查集
  units.py           V/mV、mil/mm/in、F/uF/nF/pF、ohm/kohm；未知单位非法
  io.py              严格 JSON、raw/semantic SHA-256、稳定/原子写
  facts.py           精确 MPN + 封装/修订适用性匹配
  engine.py          validate → R1–R6 → report
  report.py          finding/status/summary/scope 语义
  rules/r1.py … r6.py 六组规则
```

确定性：所有报告字段排序；finding_id 由规则+对象+code 稳定生成；报告无时间戳；
同一输入、同一路径重复运行字节一致。

## 3. R1–R6 规则语义（实现口径）

### R1 飞跨/耦合电容端点

- 只处理 `intent.capacitor_roles` 中 `role=flying` **且有来源**（evidence 或 fact_ids）的电容；
  不按位号/容值/网名猜“应该是飞跨电容”。
- 端点比较使用**真实连通分区**（`connectivity.net_aliases` 并查集），不比较网名字符串。
- 已声明 `expected_terminals`：比较两端网络集合；集合不符 → hard violation；
  两端同一分区 → `flying_capacitor_shorted`。
- 无期望网络时只判定“两端是否同分区”；网络缺失 → unknown（terminal_count/unknown_endpoint_net）。
- 事实 `flying_capacitor` 只作为角色/引脚定义证据，不写死 CPL/CPH、不写死某芯片脚号。

### R2 电容耐压与电压应力

- 耐压来源：组件 `attributes.rated_voltage`（必须有 evidence）或精确匹配的
  `capacitor_rated_voltage` device fact；无来源 → unknown，不猜。
- 应力来源二选一：
  1. 已声明 `max_differential_stress` 且带 evidence（declared）；
  2. 两个端子都有 `operating_conditions.net_voltages` 的 **DC** 区间时，按
     `max(|hi1-lo2|, |hi2-lo1|)` 推导（derived_dc_interval）。
- 任一端为 switching/ac/unknown、含负压、或范围冲突 → unknown；**不用单端对地电压
  代替两端差分电压**。
- `stress > rated` → hard `over_rated_voltage`；项目 `derating.max_voltage_fraction`
  下超限 → `derating_shortfall`（severity=review，明确是项目策略而非全行业标准）。
- “16 V 够不够”只看该电容实际节点应力与条件，不因 24 V 电源把全板 16 V 电容判错。

### R3 按键内部常通组与有效切换

- 只使用精确 MPN 的 `switch_internal_groups` 事实；无事实 → unknown，**不猜四脚按键组别**。
- 使用 `used_pins`（或已连接脚）按脚号判断：同属一个 always-closed 组 → hard
  `always_closed_pair`；按下关系不连通 → hard `used_pins_never_connect`。
- 按下时把两个 power 网络或 power–ground 直连（`net_roles`/`supplies` 证据）→ hard
  `pressed_shorts_power_rails`；网络角色未知 → unknown，不放过也不乱判。
- 只看原厂脚号，符号左右/脚位顺序/旋转不影响结果。

### R4 特殊引脚能力与电源域

- 精确 MPN + 封装/修订匹配的 `pin_functions` 事实才生效；不匹配 → unknown，不套用。
- 声明 `pin_roles` 与事实能力冲突（输入/输出/双向/开漏/电源/地）→ hard。
- 开漏输出要求外部上拉：找到连接到已声明 power 网络的电阻 → satisfied；否则 unknown。
- `supply` 范围与电源脚实际网络范围比较；输入脚 `max_v` 与网络声明范围比较；越限 → hard。
- 只在有 intent/电压范围证据时检查；自定义网名叫 “IN” 不构成错误证据。

### R5 裸焊盘与一对多映射

- 只对精确 MPN 的 `pad_map` 事实检查；**中心焊盘不是天然 GND**，事实没要求就不要求。
- 一个逻辑引脚可映射多个物理焊盘（如 SOT-223 的 VOUT + TAB）；必要焊盘缺失 →
  hard（`mapping_complete=true`）或 unknown（未声明完整性）。
- 重复焊盘映射/冲突要求在输入校验或规则中报 invalid/hard。
- 要求网络角色时，用 `intent.net_roles` 或同器件地/电源脚事实分类，不靠网名；
  无法分类 → unknown。
- 缺少封装或引脚-焊盘映射证据 → unknown，绝不说“封装核验通过”。

### R6 电容角色与局部布置

- 角色必须来自 `intent.capacitor_roles` 且有 `role_source` + evidence/fact_ids；
  无角色/unknown → unknown。100 nF/10 µF 数值不决定角色。
- bulk 明确不套局部去耦距离阈值；local_decoupling 没有项目约束 → unknown，
  不使用 100/150 mil 经验默认值。
- 只支持 `euclidean_proxy`：焊盘级坐标的直线距离；缺坐标/缺目标脚/单位未知 →
  unknown；不声称证明高频回路/ESL/EMI/回流路径。
- 阈值、目标脚、来源由项目输入；报告把测量方法标为 Euclidean proxy。

## 4. 状态机

```
invalid_input  > fail(hard) > review_required(unknown/策略) > incomplete > pass_with_scope
```

- `fail` 只由 severity=hard 的已证明违反触发；derating/距离等策略项为 review。
- `review_required` 覆盖 unknown、证据不足、策略违反；不等同于电气错误。
- `incomplete`：未提供 intent，或没有可审查对象，或某些规则因整段输入缺失未评估。
- `pass_with_scope`：仅对“已评估规则 + 输入覆盖”成立；报告强制列出 not_checked。

## 5. 为什么不是关键词扫描/固定报告

- 每条 finding 来自结构化事实匹配 + 连通分区/数值比较，并带对象、实际值、约束、来源；
- R1 用并查集判断真实分区；R2 用区间推导或声明应力；R3 用原厂内部组表；
  R4 用引脚能力表；R5 用焊盘映射表；R6 用项目阈值 + 坐标；
- 不同输入产生不同 status/finding；至少 31 个冻结 CLI 场景含 pass/fail/review/incomplete/invalid。

## 6. 已知限制

- 不做任意模拟网络求解，按键“电源短接”只按声明网络角色判断；限流/负载路径需人工确认。
- R2 的 DC 推导只适用于双端 DC 区间；开关节点、负压、瞬态、波形一律 unknown。
- R6 只测直线距离，不读取铜/回流路径；不能证明高频性能。
- 器件事实必须由输入提供；模块不内置 datasheet 数据库，也不按型号猜参数。
- 不检查整工程/跨页完整性、PCB 铜连通、热/EMC/安规/固件/制造/上电。
