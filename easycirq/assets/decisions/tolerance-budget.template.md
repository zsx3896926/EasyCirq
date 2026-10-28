# 容差预算与角点决策（Agent 填写，用户不填）

> 用途：把跨电路的误差项写成可复核预算，先列可同时发生的角点组合，再给出 worst、RSS、相关组处理与判定状态。
> 使用范围：D0 不建预算；D1 只做一个通道/一个主导项；D2 才启用完整逐项表、角点组合、主导项动作与判定汇总。
> 纪律：未知写“待查”，不填 0；项目假设标 E3；没有器件 max、实测或 EDA 回读，不得写“硬件已验证”。
## 1. 目标与口径

| 字段 | 值 |
|---|---|
| 验收项与判据 | 例：25 °C ±0.5% FS；全温区 ±1% FS |
| 节点与单位 | 统一到 ADC 端 LSB 或输入端的 µA/%FS；禁止混加 |
| 温度范围与校准温度 | 例：-20/25/60 °C；校准在 25 °C |
| 统计口径 | guaranteed / statistical / mixed；写清哪些项按界限、哪些按 RSS |
| 冻结条件 | 器件 max、温度系数、校准源不确定度、MUX 序列齐备 |
## 2. 逐项预算（每项一行）

| id | term | min | typ | max | unit | condition | temp_range | evidence_grade | class | correlated_group | calibration_state | source | worst | RSS | dominant_rank | decision |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ITEM-01 | 待查 | 待查 | 待查 | 待查 |  |  |  | E3 | gain/offset/drift/nonlinear/quantization/dynamic/residual/correlated |  | initial/post-cal/not-calibratable/unknown | 来源 ID + §/页，或 path:start-end |  | n/a 或数值 |  | guaranteed_pass/statistical_pass/conditional/fail/cannot_conclude |
填写规则：
- `min/typ/max` 必须同单位同条件；典型值不能当判据，保证结论用 max。
- `class` 选一项；`correlated_group` 填共用基准、温度场、MUX 序列、校准等组名；无关写 `independent`。
- `calibration_state` 说明该项在两点/多点校准后是否仍留；不要把可校准项重复计入 post-cal 残差。
- `RSS` 只对独立随机项给数值；相关/系统项写 `n/a（相关）`，在 §4 单独合成。
- `dominant_rank` 按当前角点的贡献排序；并列写 `1（并列）`。
## 3. 角点组合（先列可同时发生的组合）

| 组合 ID | 温度 | 输入/负载 | 供电/基准 | 通道状态 | 同时取极值的项 | 结论 |
|---|---|---|---|---|---|---|
| CORNER-01 | 25 °C | 4 mA | Vref min | 两通道同值 | shunt max、gain max、Vos max | 待查 |
| CORNER-02 | 60 °C | 20 mA | Vref max | CH1 满量程、CH2 零 | tempco、自热、MUX 前通道拖尾 | 待查 |
- 单调量（offset、gain、leakage、settling 随 t_ACQ）在区间端点取极值。
- 非单调量（基准温漂曲线、Vos 漂移、INL、串扰）在 -20/25/60 °C 与 4/12/20 mA 的内部点找极值。
- 不把不同时发生的 max 硬乘；组合必须能说出物理场景与通道序列。
## 4. 内部极值与相关组
- 共用基准：所有通道按同一偏置代数相加，不拆成每通道独立 RSS。
- 温度场：同一温区的 tempco 项一起移动到温度端点，按 worst 或端点值合成。
- MUX：按最坏前通道（满量程→零）与采样序列取残差；没有序列假设写 cannot_conclude。
- 校准残差：只保留校准后仍留的温漂、INL、噪声、建立、串扰、长期漂移与校准源不确定度。
## 5. 判定汇总

| 状态 | 允许写法 | 必要条件 |
|---|---|---|
| guaranteed_pass | worst ≤ 判据 | 每项有 max/来源；相关项已按代数处理；无未知主导项 |
| statistical_pass | RSS ≤ 判据，且同时给 worst | 仅独立随机项；写明统计口径，不声明批次保证 |
| conditional | 列出条件、owner、到期日 | 条件可观察、可复现；不满足时退回 fail |
| fail | 单项 max 已超判据，或 worst 超判据且无缓解 | 写触发项与重评条件 |
| cannot_conclude | 缺主导项 model/器件 max/实测 | 写 NOT RUN 与所需证据 |
## 6. 主导项动作

| 主导项 | 首选动作 | 代价/边界 |
|---|---|---|
| R_th 或漏电 | 缓冲、降 R_th、保护环/清洗 | 面积、功耗、输入范围 |
| 建立残差 | 降 R、加缓冲、延长 t_ACQ、降采样 | 采样率、建立非线性 |
| offset/零漂 | 零漂运放、斩波、单点校准 | 成本、1/f 噪声、校准工位 |
| 基准初始/温漂 | 外基准、比率测量、温度校准 | 成本、校准点数、长期漂移 |
| 量化 | 提高位数或缩窄量程 | 位数、量程、前级噪声 |
| 串扰 | 每通道缓冲、外部 MUX、占位通道 | 通道数、采样率、面积 |
| 校准残差 | 提高校准源、多点温度校准、降 tempco | 工位、时间、存储 |
used_by: `R4-CASE-D01`（`easycirq/references/decisions/cases/r4-case-d01-acquisition-tolerance.md`）
