# 布线计划（项目模板）

复制到工程工作区填写，或把结果写入工程的 `design-state.json`。未确认的项写 `待确认`，表格空格用 `<...>` 占位，不要填示例值或留空后当已完成。本模板是计划与证据清单，不是审批单：门禁是证据门，只有用户明确要求评审时才停下来等确认。

依据与判定见 [PCB布线策略](../references/pcb-routing-strategy.md)；RT/PL 逐项方法见 [布线与回流细节](../references/pcb-routing-details.md) 与 [PCB布局细节](../references/pcb-placement-details.md)，本模板只引用编号。层数/铜厚/工艺能力按 [嘉立创PCB生产规则](../references/jlc-pcb-rules.md) 的当期订单条件核对；证据记录见 [证据与轻量记录](../references/evidence.md)；工艺参数并入 [生产档案](manufacturing-profile.md)。

## 0. 版本与范围

- 工程/板版/填写日期：
- 目标板框（mm）与来源（用户/外壳/机械图）：
- 层数/铜厚/层叠（含内层类型）：
- 当前阶段（G3/G4/布线中/G5）、用户要求的检查点（没有写“无”）与本次不布的区域：

## 1. 层与通道计划

| 层 | 角色（信号/地/电源/混合） | 主要网络 | 走向/通道 | 禁布区 | 备注 |
|---|---|---|---|---|---|
|  |  |  |  |  |  |
|  |  |  |  |  |  |

- 连接器到主控的逃逸通道、已试排的密集区（QFN/BGA/连接器）及结果：
- 布局冻结时间/依据（G3）：

## 2. 网络类

| 类名 | 网络 | 最小线宽 | 目标线宽 | 间距 | 过孔 | 依据（电流/温升/压降/厂规） | 状态 |
|---|---|---|---|---|---|---|---|
|  |  |  |  |  |  |  |  |
|  |  |  |  |  |  |  |  |

- `easycirq pcb net-classes` 回读时间与结果：
- 电源网（+5V/VREF 等）宽度依据；与 `pcb check` 的 `width-under-spec`/`width-mismatch` 对照：

## 3. 电源与地策略

- 模式（一层一网/铺铜优先级/内电层）与理由：
- 2 层 `power-pour` 参数与回读；4 层 `power-planes` 的 gnd/power 层 ID 与回读：
- GND 铺铜层、缝合孔安排与目标平面：
- 同层多网优先级（创建回执与重载后 `pour-list` 对比）：
- 铺铜板上是否出现 GND 走线；若有，宽度与理由：
- 过孔审计（`via-list`/`dump`：孔径/外径/层跨度/`staleRisk`）与相关证据文件：

## 4. 布线顺序

| 顺序 | 内容 | 进入条件 | 退出证据 | 状态 |
|---|---|---|---|---|
| 1 | 电源/地平面与铺铜（声明并创建；随信号变化重铺） | G4 已声明，层叠回读一致 | `pour-list`/`poured-list`/`pcb check` |  |
| 2 | 关键信号（时钟/模拟/反馈/差分/复位/保护）；细间距 FPC/模组逃逸先锁定 | 平面/铺铜已声明，关键网清单已记录 | 逐网 `net-path`、局部铜回读 |  |
| 3 | 普通信号与剩余网络 | 关键信号完成，无新增阻断 | 完整 DRC、未布网络清单 |  |
| 4 | 电源/地补线与缝合孔（走线类铜） | 全部信号网 DRC Connection 0 | `pour-rebuild` 后 DRC、`via-list`、`pcb check` |  |

- 缝合线和缝合孔是固定铜，不会给后布的信号让路；铺铜经 `pour-rebuild` 会。所以缝合放在第 4 步，见 [布线策略 §4.2](../references/pcb-routing-strategy.md)。
- 每组实际起止时间与命令：
- 布线期间是否移动已布器件（是/否；是则按 PL31/RT32 重验）：

## 5. 关键网与证明方法

| 网络 | 起点位号.焊盘 | 终点位号.焊盘 | 为何关键 | 证明命令 | 证据文件 | 状态 |
|---|---|---|---|---|---|---|
|  |  |  |  |  |  |  |
|  |  |  |  |  |  |  |

- `routing.key_nets` / `routing.key_net_proofs` 填写值：
- `net-path` 只证明已布铜，不含铺铜/内电层；由铺铜承担的网另列 `pour-list` + `dump`，并注明“net-path 不覆盖”：
- 保存 → `easycirq doc reload` → 重新回读的时间与结果：

## 6. 过孔策略

| 类型 | 孔径/外径 | 用途 | 允许层跨度 | 数量预期/上限 | 审计证据 |
|---|---|---|---|---|---|
|  |  |  |  |  |  |

- 缝合孔目标平面与回读；平面开窗/反焊盘/盘中孔要求：
- `pcb check` 的 `via-crosses-plane`/`single-layer-via`/`overlapping-via` 结果：

## 7. 连接器逃逸

| 连接器 | 接口无源件（CC/TVS/ESD/滤波） | 距连接器 mm | TVS/ESD 位置 | 是否跨 slot | 证据 | 状态 |
|---|---|---|---|---|---|---|
|  |  |  |  |  |  |  |

- 规则：接口无源件 ≤5 mm；TVS/ESD 在连接器与受保护网络之间；slot 与开槽区禁布；SOP 式成组同向放件：
- 写入 `layout.connector_escape.max_distance_mm` 与 `slot_clear`：

## 8. 自动布线候选记录

- `easycirq pcb route-short --dry-run` 的命令/时间/结果，skipped nets 与实际 routes/vias 差异：
- 是否使用 `--route-power`（默认“否”；若“是”，写理由与铺铜前/后顺序）：
- 是否使用 `easycirq pcb autoroute`（DSN→SES→import→DRC 的回读结果）：
- 采纳/回退决定与理由：

## 9. 停止条件与 DRC 轮次

| 轮次 | 时间 | DRC total | Clearance | Connection | 较上轮改善 | 主要动作 |
|---|---|---|---|---|---|---|
| 基线 |  |  |  |  | — | 布线前 |
| 1 |  |  |  |  |  |  |
| 2 |  |  |  |  |  |  |
| 3 |  |  |  |  |  |  |

- 连续 3 轮改善 <30% 时停止同一策略（定义与出路见 [agent-collaboration](../references/agent-collaboration.md) §停止规则）；是否触发 `DRC_PLATEAU` 及动作：
- `routing.drc_rounds` 与 `routing.stop_rule_triggered`：

## 10. 证据清单

| 角色 | 文件 | 命令 | 时间/版本 | 格式 | 备注 |
|---|---|---|---|---|---|
| DRC（布线前/最终） |  | `easycirq pcb drc --json` |  |  |  |
| 布局检查 |  | `easycirq pcb layout-lint --json` |  |  |  |
| 铺铜与过孔回读 |  | `easycirq pcb pour-list` / `easycirq pcb via-list` |  |  |  |
| 板级铜/网络 |  | `easycirq pcb dump` |  |  |  |
| 关键网证明 |  | `easycirq pcb net-path --json` |  |  |  |
| 保存重载与丝印 |  | `easycirq doc reload` / `easycirq pcb silk-align` |  |  |  |

- 截断或损坏的 JSON 不作为证据；每份记录工程/板版、时间与命令，便于判断是否早于最终板。

## 11. 写回与结论

- `routing.plan` / `key_nets` / `key_net_proofs` / `save_reload` / `silk_align` / `drc_rounds` / `stop_rule_triggered`：
- `stackup.layers` / `decision` / `power_ground_strategy` / `inner_layers` / `drc_rules_recorded`：
- `layout.connector_escape.max_distance_mm` / `slot_clear`：
- 状态（PASS / PASS_WITH_WAIVER / BLOCKED / UNSUPPORTED，选一并写依据）：
- 未覆盖项、剩余风险与下一步：
- `PASS_WITH_WAIVER` 的理由、条件与复验触发（无则写“无”）：
