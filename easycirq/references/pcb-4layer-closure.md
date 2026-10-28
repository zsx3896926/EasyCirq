# 4 层板端到端闭环配方

> 范围：4 层（含内层地/电源平面）、低压低速、以嘉立创 EDA 专业版真实闭环为验收的整板布线收敛。2 层板流程见 [PCB 布线策略](pcb-routing-strategy.md)；本页只补 4 层专有的端到端顺序与停止规则。单板个案结论不外推。

先读 [PCB 执行工作流](pcb-execution.md)、[PCB 布线策略](pcb-routing-strategy.md)、[门禁定义](design-gates.md)。DRC 停止规则全库只有一份，见 [agent-collaboration](agent-collaboration.md) §停止规则；本页不另写第二套收敛循环。

## 12 步

| 步 | 阶段 | 命令/证据 | 退出条件 | 单步预算 |
|---|---|---|---|---|
| 1 | 规则与层叠 | `pcb drc-rules`、`pcb stackup show`、`pcb net-classes` | 规则与层叠回读一致，写入 G4 声明 | 1 轮 |
| 2 | 机械与禁区 | `pcb outline-get`、`pcb antenna-keepout --dry-run` | 板框/孔/槽/禁布区落盘，与外壳一致 | 1 轮 |
| 3 | 布局 | `pcb layout-lint --json` | score/crossings 达标，G3 冻结 | 2–3 轮 |
| 4 | 逃逸 | `pcb escape-plan`，细间距 FPC/模组先逃逸并锁定 | 逃逸规划与真实布局回读一致 | 1 轮 |
| 5 | 关键网 | 逐网 `pcb net-path` | 关键网清单逐条证明 | 每网 1 轮 |
| 6 | 分批信号 | `pcb autoroute` 每批 ≤8 网，或离线补线 | 信号网 DRC Connection 0 | 每批 ≤240 s |
| 7 | 离线补线 | 路由选择表指向 `island_join`（未收编前用项目内临时脚本） | 剩余断网闭合 | 单批预算 |
| 8 | 信号门禁 | `python scripts/pcb_evidence.py drc-summary <drc.json>` | 信号 DRC 干净，写 G5 前证据 | 1 轮 |
| 9 | 电源与地 | 铺铜/内层平面 + 缝合孔 + `pcb pour-rebuild` | 电源/地连通，`poured-list`/`via-list` 一致 | 1–2 轮 |
| 10 | DRC 循环 | `pcb drc --json` → `drc-summary` | total=0（触发见停止规则） | 见停止规则 |
| 11 | DFM 收尾 | `pcb check`、`pcb layout-lint`、丝印 | `dangling-end`/锐角/线宽突变/禁铜为 0 | 1–2 轮 |
| 12 | 交付 | `pcb_gate --profile full` | 8/8 pass（缺证据只 blocked） | 1 轮 |

## 4 层专有的三点

- 内层平面一旦分割/开窗改过，就必须 `pcb pour-rebuild` → `save` → `doc reload` 后再 DRC；未重建的 DRC 记为 `invalid`，不计入停止规则的轮次，也不作为“变差”的依据（见 [agent-collaboration](agent-collaboration.md) §停止规则）。
- 已经 4 层仍不收敛时，出路不是“改 4 层”，而是重排局部区域 / 重新规划逃逸 / 拆板；见停止规则。
- 电源/地缝合线是固定铜，放在信号网 Connection 0 之后，见 [PCB 布线策略](pcb-routing-strategy.md) §4.2。

## 验收样例：PocketCam X1

DRC 轨迹 74 → 61 → 21 → 74 → 1910(假) → 21 → 375(假) → 61 → 35 → 13 → 5 → 2 → 0：

- 74→61→21 每轮改善 ≥30%，继续；21→74 总数变差，触发“恢复上一轮备份”，从 21 的备份继续。
- 1910 与 375 是铺铜未重建的假暴涨：按“未重建的 DRC 无效、不计轮次”跳过，`pour-rebuild` 后回到 21/61，不算平台期也不触发回退。
- 61→35→13→5→2→0 单调收敛，不再触发停止规则。

能对这条轨迹判出“两次假暴涨（1910/375）与一次真实回退（21→74）”，即本配方验收通过。
