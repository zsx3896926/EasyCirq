---
id: R4-J
title: 模块复用合同：边界、兼容与退役
packages: [J]
evidence: E3
last_reviewed: 2026-10-22
sources: [PWR-S07, PWR-S09, MCU-S09, PWR-S06]
---

# 模块复用合同：边界、兼容与退役

> 一句话用途：判断一个电路块或模块能否被另一个产品复用，把“照着原理图抄一遍”改成有边界、有条件、可复评的合同；证据等级 E3，不能替代目标板的 EDA 回读、热测试、EMC 与样机验证。

## 目录

1 触发条件；2 输入；3 Agent 可独立完成的判断；4 必须停下的条件；5 决策规则与表；6 改变哪个工程决定；7 完整案例；8 证据与验证方式；9 与现有资产分工；10 来源、未知与重评触发

## 1. 触发条件

**触发：** 把一个项目中已经做过的电路块、模块或子系统用到另一个产品、另一个板版或另一个供应商；或要求“沿用上一版电源/接口/采集电路”。

**不触发/跳过：** 同一产品、同一板版、同一 BOM 的维修或复购；只读方法卡做学习；模块边界尚未定义，此时先做模块划分，不进入复用合同。

**深度：** D0 为单板、单次、不可逆性低且无跨项目复制，不建合同；D1 为同项目内复用单个电路块且接口与负载不变，只写合同头、拒绝条款与实例化检查表；D2 为跨项目/跨供应商、涉及安全/隔离/认证、或产量与环境变化，要求完整合同、兼容矩阵、实例化验证与退役计划。

## 2. 输入

- **Agent 可自己读：** 源项目原理图/连接表、BOM、板版与变体、测试记录、`source-register.md` 登记范围。缺连接表或 BOM 时不得声称“接口一致”。
- **必须问用户：** 目标产品功能与非目标、负载曲线、外壳/散热、产量与寿命、许可与商务约束。问不清就按 D1 上限处理，不进入 D2；模块边界、接口定义、来源与版本、许可状态、目标环境中任一项缺失，结论只能是 `blocked` 或 `待查`。

## 3. Agent 可独立完成的判断

- 合同完整性：10 组字段（`function`、`interface`、`input / load / environment / dependencies`、`immutable`、`allowed`、`recompute`、`source / version / licence`、`compatibility matrix`、`instantiation verification`、`status / retirement`）是否填到可核对程度，而不是“字段有名字”。
- 兼容矩阵：逐条比较源值、目标要求与证据，结论只用 `pass`/`fail`/`unknown`；再按不可变/允许/必须重算三分，并列出实例化验证计划与退役影响（目标板要重跑哪些测试，退役后哪些产品、BOM、测试记录失效）。

## 4. 必须停下的条件

- 许可不明或不允许再分发/再制造：不得写“可复用”。
- EOL/PCN 未核且已有产量承诺：不得写“已验证”，只能 `blocked`。
- 旧项目只有离线规划、没有 EDA 回读或实测：不得把旧结论升级为目标板证据；模块边界跨隔离、接地、安规或认证责任时，必须由人确认责任边界。
- 同一对象、同一参数、同一条件出现不同值且无裁决：先登记冲突，不选值。

## 5. 决策规则与表

**复用合同是 opt-in。** 只有以下字段组全部填到“可核对”程度，模块才进入复用候选；缺任一组，结论只能是 `not-a-module` 或 `blocked`。

| 字段组 | 可核对的最低内容 | 不足时的处理 |
|---|---|---|
| function / interface | 功能、非目标、失败模式；电压域/门限/方向、协议、机械与连接器 | 只写“电源模块”或只写网名不算 |
| input / load / environment / dependencies | 输入范围、负载曲线、温度/湿度/振动、上下游依赖 | 只写标称值不算 |
| immutable / allowed / recompute | 不可变项、允许调整项、必须重算项，各自列清单 | 缺“必须重算”即视为不可复用 |
| source / version / licence | 来源项目与版本、原厂来源 ID、许可与再分发条件 | 许可不明即 `blocked` |
| compatibility matrix / instantiation verification / status / retirement | 逐条源值/目标值/证据/结论；目标板验证项；替换与退役影响 | 缺矩阵或退役计划不得写 `reusable`，不得用于量产 |

**结论只用四种：** `reusable` 表示合同完整、矩阵全 pass、实例化验证已执行；`accepted-with-conditions` 表示存在可测试条件，条件写进测试计划，未满足即回到 `blocked`；`rejected` 表示至少一个条款 fail 且无法降级，不复制，改用替代方案或重做；`not-a-module` 表示只有方法卡或零散器件，先做模块划分。

**拒绝条款示例：P01 充电器 + power path 块。**

| 拒绝条款 | 判定 | 证据 |
|---|---|---|
| 充电调节电压上限高于电芯硬上限 | 电芯规格书确认硬上限 ≤4.20 V 时，4.23 V max 不通过；仅知标称 4.20 V 或设计范围时，兼容性 `blocked`/待核，不得直接判不通过或按 typ 放行 | `easycirq/references/design-cards/power/p06-linear-charger.md:104-106`；PWR-S07 §8.5 |
| 把 500 mA 当默认能力 | 500 mA 只在开盖/良好散热条件成立；密封壳按 300 mA 设计 | `easycirq/references/projects/p01-low-power-wireless-sensor.md:168-174` |
| 单输入块直接用于双源节点 | 模块边界只有 USB 输入，不含第二路电源选择/ORing | `easycirq/references/projects/p01-low-power-wireless-sensor.md:59-66` |
| 25 块试产结论外推到 1000 台 | 供应、PCN、寿命与一致性未核，不能写 `reusable` | `easycirq/references/projects/p01-low-power-wireless-sensor.md:318-320` |

**条件必须可测试：** “注意散热”不是条件；“密封壳内 25 °C 环境、300 mA 充电、连续 2 h，芯片表面 ≤60 °C 且不触发热调节”才是条件。实例化验证至少重跑接口电压/门限、上电顺序、负载瞬态、热、异常恢复（欠压/拔插/短路）与旧产物对账；只读源项目测试记录不算。退役必须写替代模块、受影响产品/变体、旧 BOM/测试记录的失效方式；退役模块保留索引行并标 `retired`，不删除。

## 6. 改变哪个工程决定

- 从“这个模块好用，直接抄”改为“哪些不可变、哪些必须重算、哪些必须重测”；复用结论会改变 BOM、热设计、测试计划和供应策略，任一变化都要回到兼容矩阵重判。“替代料”是同一模块内的等级 1–3，“复用”是跨模块的合同，两者不能互相替代。

## 7. 完整案例

`easycirq/references/decisions/cases/r4-case-j01-charger-power-path-reuse.md`（R4-P2，E3 / OFFLINE_PLANNING / hardware_execution NOT RUN）。

- 决定：分两档。① 电芯规格书确认硬上限 ≤4.20 V → 充电器 + power path 子块 `rejected`（4.23 V max 超出硬上限 30 mV）。② 仅知标称 4.20 V 或设计范围、硬上限未确认 → `blocked`/待核，暂不放行，不能直接判 `rejected`。R4-P2 当前是②，电芯型号待查。保护板 OVP/允许电压只作保护协调，不能替代电芯规格书对充电条件的允许。TPS63802 升降压子块单独判 `accepted-with-conditions`（3.3 V 轨、输入范围、电感/输出电容与热测试为条件）。
- 代价：先补电芯规格书与允许充电条件；若确认硬上限 4.20 V，换 `VBAT(REG)` max ≤4.20 V 的型号；若规格书允许 ≥4.23 V，保留依据后重评。充电时间与热测试仍要补，第二路电源选择不在块内。
- 下一个检查或待查：电芯型号/硬上限/允许充电条件；BQ24074 具体后缀的 `VBAT(REG)` min/typ/max、`KILIM`/`KISET`、θJA、NTC 曲线，均待查；保护板 OVP 只作协调。TPS63802 电感/输出电容与密封壳热测试 `NOT RUN`。

## 8. 证据与验证方式

- 本轮为离线规划：只读现有项目记录、设计卡与来源登记，未重开原厂正文，未做 EDA 回读或实测。现有 60 张设计卡仍是**方法卡**，不是复用合同；不能把卡的存在当成模块已验证。
- 通过判据为合同字段齐全、兼容矩阵无 `unknown`、实例化验证有目标板证据；本轮均 `NOT RUN`，输出固定写 `board_verified:false`、`execution:OFFLINE_PLANNING`、`hardware_execution:NOT RUN`。

## 9. 与现有资产的分工

- `easycirq/references/projects/p01-low-power-wireless-sensor.md:84-92`：P01 给器件条件与既有决定；本文给复用合同与拒绝条款，不复制器件参数。
- `easycirq/references/design-cards/power/p06-linear-charger.md:104-106`：卡片给 4.23 V 条款的器件级依据；本文把它变成合同拒绝条款之一。
- `easycirq/assets/decisions/decision-record.template.md:71-78`：模板给 typed block 字段；本文给合同判定流程。

## 10. 来源、未知与重评触发

- PWR-S07：SLUS810N §8.1–8.5、§9.3.4–9.3.6（登记范围）；本轮未重开原厂正文。用于 `VBAT(REG)` 4.16/4.20/4.23 V（min/typ/max）、RILIM 1.1–8 kΩ、热调节 125 °C。
- PWR-S09：SLVSEU9D §6.5、§9.3–9.4、§10.2.2（登记范围）；本轮未重开原厂正文。用于 3.3 V 轨、电感/电容与模式。
- MCU-S09：§6.1–6.5（登记范围）；本轮未重开原厂正文。用于模组 3.0–3.6 V、≥0.5 A。
- PWR-S06：SLVAE57B §2–§6（登记范围）；本轮未重开原厂正文。用于反接保护与反向电流阻断的区别。

**未知：** P01 电芯型号、硬上限与允许充电条件未确认，因此 BQ24074 4.23 V max 的兼容性为 `blocked`，不是已判 `rejected`；充电器 θJA、`KILIM`/`KISET` 常数、NTC 曲线、模组完整物理脚表、所有 C 号与库存字段，均待查。

**重评触发：** 电芯规格书确认硬上限或允许充电条件；充电电流或外壳散热改变；输入从单 USB 改为双源；产量跨过试产；原厂发布 PCN/EOL；许可条件变化。
