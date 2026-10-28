# 反例审查记录（任务 B）

> **独立性声明：** 本文件由 Lead 自行执行“分开的反例攻击 + 代码复核”，**不冒充独立审查**。
> 原计划的独立反例审查成员（adversarial-reviewer）在运行中失败/中断，未产出报告；
> 其在开发过程中报告的一个 blocker（`_validate_references` 把顶层 evidence 定义 dict
> 当 id，导致 TypeError）已由 Lead 修复并复验。其余条目为 Lead 自审结果，未声称独立。

## 1. 实际攻击（仓库外临时输入，真实 CLI）

命令模板（仓库根）：

```bash
$env:PYTHONPATH="design-hardware\scripts"
python -m electrical_review review <attack>.json
```

| # | 攻击 | 实际结果 | 期望 | 结论 |
|---|---|---|---|---|
| 1 | 证据引用不存在的 evidence id | invalid_input, exit 2 | 非法输入，不复用旧 PASS | 通过（修复后） |
| 2 | fact_ids 指向不存在的 fact | invalid_input, exit 2 | 非法输入 | 通过（修复后） |
| 3 | R1 期望 CP/CN，实际 p1=CP,p2=CP_ALIAS 且 CP_ALIAS 是 CP 别名 | fail；`endpoint_net_set_mismatch` | 两端同一真实分区必须违规 | 通过（按集合/分区比较） |
| 4 | R1 两脚交换（set 语义，非极性电容） | pass_with_scope | 集合相同则不因脚序误报 | 通过 |
| 5 | R2 耐压值存在但无 evidence | review_required；`rating_without_source` | unknown，不能拿无来源额定值判超额 | **修复后通过**（修复前误报 hard over_rated_voltage） |
| 6 | R2 降额恰好等于阈值（25 V×0.8=20 V，应力 20 V） | pass_with_scope | 边界不误报 | 通过 |
| 7 | R3 显式 `forbidden_pressed_nets`（VIN–GND） | fail；`forbidden_pressed_short` | 命中禁止直连必须违规 | 通过 |
| 8 | R3 使用脚号不被原厂内部组覆盖（5/6） | review_required；`fact_missing_used_pin` | 脚号映射不一致不能判错 | **修复后通过**（修复前可能误报 never_connect） |
| 9 | R4 输出脚挂在用户自定义网名 `IN`，无 pin_roles | 无 R4 finding；整体 incomplete（无可审查对象） | 不因网名判错 | 通过（未误报） |
| 10 | R4 事实为输出（EN 输入），intent 声明 output | fail；`pin_capability_conflict` | 能力冲突 hard | 通过 |
| 11 | R5 EP 缺失但 `mapping_complete=false` | review_required；`required_pin_unmapped` | 未声明完整性不能判遗漏 | 通过 |
| 12 | R5 无 pad_map 事实但 EP 接 GND | 无 R5 要求；整体 incomplete | 中心焊盘不默认 GND/不默认必须 | 通过 |
| 13 | R6 local_decoupling 无项目阈值 | review_required；`distance_constraint_missing` | 不用 100/150 mil 默认阈值 | 通过 |
| 14 | R6 目标脚坐标缺失 | review_required；`geometry_missing` | 不用器件中心代替焊盘 | 通过 |

其余已由 49 个 unittest 与 31 个冻结场景覆盖：重复 ID/位号/脚号、NaN/inf/bool、负耐压、
未知单位、空输入、矛盾网络、旧 PASS 覆盖、短接正确飞跨电容必失败、mil/mm 与 mV 变换、
组件/引脚重排、网名重命名、位号改名但 instance_id 不变、封装/修订不匹配。

## 2. 发现并修复

| 严重度 | 问题 | 修复 |
|---|---|---|
| blocker | `_validate_references` 把顶层 `evidence` 定义当字符串 id，任意含 evidence 的输入崩溃 | 跳过 dict 定义，只校验字符串引用；补悬空引用非法输入 |
| major | R2 耐压属性无 evidence 时仍参与比较，误报 hard `over_rated_voltage` | 增加 `rating_without_source` unknown，先判来源 |
| major | R3 原厂内部组未覆盖实际脚号时可能误报 hard | 改为 `fact_missing_used_pin` unknown |
| major | R5 无地/电源分类证据时可能把“未分类”误判为错网 | `_role_ok` 无证据返回 None → unknown |
| minor | R4 供电越限 constraint 只显示 min | 显示 min..max；补封装/修订不匹配+供电声明 unknown |

## 3. 仍未消除的误判风险（诚实列出）

- 输入完全依赖 intent/device_facts 的正确性；若用户把错误角色/错误网络声明为“意图”，
  审查会以该声明为准，只能通过证据来源分层提示，不能替代人工。
- R2 的 DC 区间推导假定两网在稳态 DC；若实际存在未声明的瞬态/开关行为，可能低估应力。
- R3 的“电源短接”只按声明 net_roles/supplies 判断；复杂限流/负载路径可能被误判，
  需要人工 disposition。
- R6 只有直线距离代理；铜/回流/ESL/EMI 未建模，不能作为高频合格证明。
- R5 的 `mapping_complete` 由输入声明；若用户错误声明为 true 且实际映射不完整，
  可能误报遗漏或漏报。
- 器件资料只覆盖已提供 facts 的型号/封装/修订；换型号/封装/版本必须重新取资料。

## 4. 未冒充的独立审查

独立成员失败后，Lead 没有把自审包装成独立审查；`handoff-current.md` 与 `acceptance.md`
已如实记录。若需要真正独立审查，可在 PR 合并前另起一次独立 agent/人工复验。
