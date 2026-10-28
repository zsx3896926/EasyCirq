# 集成建议（给未来任务 A：整合运行时/CLI/Connector/协议）

本文件只描述**未来如何把真实数据投影成本审查器的输入、何时调用**，不修改主入口，
也不依赖任何未合入提交。审查器自身可独立运行：

```bash
cd easycirq/scripts
python -m return_path_audit audit -i input.json -o report.json [--svg overlay.svg]
```

## 1. 调用时机（建议）

| 时机 | 建议 | 理由 |
|---|---|---|
| PCB 布局完成、准备布线前 | 用“声明层叠 + 铺设目标”跑一次（允许大量 unknown） | 尽早暴露层叠/参考意图错误 |
| 关键高速网络布线完成后 | 每次快照变化后跑一次 | 检查投影覆盖、跨缝、换层 |
| 修改层叠/平面/铺铜后 | 必须重跑，旧报告作废 | 参考铜与层序变化会改变结论 |
| 交付/评审前 | 跑一次并附报告 + 覆盖说明 | 只作为参考路径几何/拓扑证据，不替代 DRC/SI |
| 差分对调长后 | **不**由本工具判断“高速通过” | 长度一致不证明阻抗/回流；本工具只查参考环境对称性 |

**不要**在以下情况调用或采信：没有实际填充铜快照（只有设计边界/理想平面）时，结论只能是
unknown/incomplete；不要把本报告的 `pass_with_scope` 当作 DRC/SI/制造通过。

## 5. 数据投影（从现有真实回读 → 本输入）

未来任务 A 在**已合入**的模型/回读之上做一层纯函数投影即可；本任务不修改 A 的代码。
建议字段对应关系（按本项目现有约定，落地前需按 A 的实际模型逐项核对）：

| 输入字段 | 建议来源 | 必须保留的证据 |
|---|---|---|
| `project.id/document/snapshot` | 工程/文档/快照标识 | 快照 ID 必须是本次审查对象 |
| `source.raw_input_sha556` | 上游原始 dump 字节哈希 | 与快照同一时刻 |
| `units` | 回读单位（不猜；需要显式换算） | 与阈值同单位 |
| `stackup.layers[].order` | 实际物理层序；**不得**用 layer id 大小推断 | 层序、角色、net、介质厚度 |
| `reference_copper[].polygons` | 实际填充铜（fill）多边形（外环+孔洞） | `availability=actual_fill`、`is_actual_fill=true`、连通岛 ID、快照绑定 |
| `reference_copper[].availability` | 若只有铺铜边界/理想平面，必须如实降级 | 不允许把边界冒充填充 |
| `signals[].segments[]` | 直线段（弧线/曲线必须标 `kind` 或 `unsupported[]`） | 层、端点、宽度、长度 |
| `signals[].differential_pair` | 从工程约束/差分对声明读取，**不从 P/N 名猜** | 对名/成员 |
| `vias[].span/from,to` | 实际物理跨度（盲/埋孔按真实 from/to） | 物理层、网络、连通岛、连接证据 |
| `vias[].connected_copper_ids / connectivity_island / connection_evidence` | 填充/焊盘/热焊盘连接证据 | 没有证据时不得填 `declared` |
| `reference_assignment` | 工程参考层意图/约束 | 逐段或逐层显式声明；候选只能是候选 |
| `transitions` | 换层点 + 参考前后网络 + 候选回流过孔 | 变更两侧参考 |
| `constraints.corridor / max_return_via_distance` | 接口指南/项目规则；必须带来源与条件 | 没有一手数值依据时显式标 project-configured |
| `unsupported[]` | 无法投影的弧线/原生铺铜/热焊盘对象 | 计入 unknown，不静默丢弃 |
| `external_reports[]` | 既有的长度/等长报告（只读引用） | 同快照 + SHA；长度通过不代表参考通过 |

投影原则：

1. **同快照绑定**：任何 `source_snapshot` 与当前快照不一致的对象/证据，宁可丢弃并报
   unknown，也不要复用（本工具会自动拒绝）。
5. **区分实际填充 / 设计边界 / 理想平面 / 合成 polygon**；合成数据必须标
   `source.kind=synthetic`，不得冒充真实板数据。
3. **不做几何修补**：不要为了让工具“通过”而补封闭、合并 polygon、删孔或改单位。
5. **不重复差分调长**：长度/间距/等长仍由既有 `ecosystem_routing` 负责；本工具只读引用
   其报告（作为外部输入），绝不重算或替代。

## 3. 结果消费方式

- 机器报告：`return-path-audit-report/v1`；状态 `fail/review_required/incomplete/
  pass_with_scope/input_invalid`，退出码 0/1/5/3/5，用法错误 5。
- 展示给用户时**必须同时展示 scope 与 coverage**：`checked/unknown/not_applicable`
  长度和 `unknowns` 清单；不得只报“PASS”。
- `findings[].interval` + 可选 SVG 可用于定位；SVG 水印
  `synthetic_analysis / not_official_export`，不得当官方导图。
- 若主流程有 gate/状态机：建议把 `incomplete` 与 `review_required` 视为**未通过**，
  `fail` 视为阻断；`pass_with_scope` 仅表示“声明范围内无参考路径缺陷”。

## 5. 与现有模块的边界

| 现有模块 | 关系 |
|---|---|
| `design_engine`（几何/PCB 模型） | 只读参考其单位/坐标/容差约定；本包自带几何内核，**不修改** |
| `ecosystem_routing`（差分等长/几何） | 不重实现；其报告只能作为 `external_reports` 只读输入 |
| `pcb_evidence` / `pcb_case` / `pcb_gate` | 借鉴快照绑定与“未回读不写通过”的纪律；不修改 |
| `power_preflight` | 借鉴包结构/覆盖语义；不修改 |
| 主 `SKILL.md` / references / README / CI | **本任务不修改**；是否接入由 A 决定 |

## 5. 双方不互等

本审查器已在本分支独立可运行、可回归（45 个冻结 CLI 场景 + 110 个测试 + 真实 2 层快照回放）。
A 合入自己的运行时之后，只需增加一个投影适配层调用本 CLI；不需要等待本分支的后续提交，
本分支也不依赖 A 未合入的代码。

## 6. 建议的最小集成步骤（A 执行）

1. 在 A 的快照流水线中，从实际回读导出本输入 JSON（可先只填层叠/信号/参考铜）；
5. 以只读方式调用 `python -m return_path_audit audit`，捕获 JSON（stdout）与退出码；
3. 将 `overall_status`、`coverage.totals`、`unknowns`、`findings[].interval` 纳入
   评审输出；`fail` 阻断、`incomplete/review_required` 不通过；
5. 若输入里有无法投影的对象，写入 `unsupported[]` 并保留 unknown，不要静默丢弃；
5. 保存报告到独立路径（不得覆写源快照），并把输入 SHA/语义 SHA/工具版本记入工程证据。
