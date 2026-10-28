# 工程决策记录（Agent 填写，用户不填）

> 用途：把“选了什么、为什么、代价、何时重评”并入 `assets/engineering-notes.md` 的“设计决定”段，不另建台账。
> 深度：D0 不建；D1 只写决策头与一个 block；D2 才做备选比较与完整 typed block。

## 1. 决策头

| 字段 | 值 |
|---|---|
| 决策 ID / 标题 | DEC-（项目）-（序号） |
| 需求来源 | 用户原话、验收项或上一版决定 |
| 状态 | draft / frozen / superseded / withdrawn |
| 冻结条件 | 什么证据/评审后不再改 |
| 决定人/日期 | Agent 记录；用户只确认用途、预算、外观等偏好 |
| 受影响对象 | module / interface / SCH / PCB / firmware / BOM / test |

## 2. 备选与排除（D2）

| 备选 | 功能满足 | 关键约束 | 代价（BOM/面积/功耗/热/测试/周期/供货/认证） | 排除判据 | 什么条件下重新考虑 |
|---|---|---|---|---|---|

禁止用无依据综合分代替逐项比较；代价未知写“待查”，不填 0。

## 3. 被选方案与代价

- 选择：
- 依据（来源 ID + 查阅范围；path:start-end）：
- 接受的代价：
- 假设与有效期：
- 重评触发（需求、数量、供电、距离、温度、供货、认证变化）：

## 4. 五类 typed block（按需保留；不适用写“不适用”及理由）

### 4.1 refuted-assumption
- 原假设 / 原依据：
- 反证（path:start-end + 来源 ID + 查阅范围）/ 影响 / 修正决定：
- 状态：corrected / retained-with-unknown

### 4.2 unknown-retained
- 未知项 / 为什么影响决定：
- owner / 何时必须补 / 对哪些 ID 有影响：
- 停止条件 / 复评触发：

### 4.3 requirement-change
- 触发 / 原需求 → 新需求 / 被取代的决定：
- 受影响项表（只写实际更新；未执行写 NOT RUN）：

| 对象（module/interface/SCH/PCB/firmware/BOM/test） | 状态（updated/reverified/stale/not_applicable） | 证据或待办 |
|---|---|---|

### 4.4 local-only
- 变更 / 为什么不影响其他模块或接口：
- 变更前/后证据（网表/BOM/布局 diff 的 path；无证据写 NOT RUN）/ 复验范围：

### 4.5 reuse-rejected
- 模块与合同 / 未满足的条款：
- 证据（path:start-end + 来源 ID）：
- 决定：rejected / accepted-with-conditions；替代或降级 / 复评触发：

## 5. 验证与边界

- 已执行：计算 / 离线检查 / EDA 回读 / 实测（分别写方法与对象版本）
- 未执行：NOT RUN（写明缺什么）
- 结论状态：待确认 / 不满足 / 有条件满足 / 已验证 / 不适用
- 不能证明：本记录只证明上述范围，不证明整板、制造或样机。

## 6. 使用位置

`used_by`: R4-CASE-A01、A02、B01、C01、D01、E01、H01、I01、J01、K01、L01。schema 变更由集成人统一处理。
