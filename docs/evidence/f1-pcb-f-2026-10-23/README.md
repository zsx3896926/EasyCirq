# F 包：F1 PCB 闭环 — 可行性与阻塞证据（2026-10-23）

## 结论（先读）

- **F1 PCB 的自动闭环在当前半离线 CLI 下无法从零完成**：`pcb_Document.importChanges`
  （原理图→PCB 导入）返回 `true` 但**不物化任何器件**；板框层（layer 11）直线创建被客户端拒绝。
  这两个动作需要 GUI 全在线会话各做一次。
- **导入之后的步骤已全部真机验证可用**：`autoLayout`、`autoRouting`（含结果与失败网络）、`save`、
  重开比较。执行器已封装为 `pcb import / layout / route / outline`。
- 本目录的 layout/route 演示跑在工程内既有的 33 器件 PCB（`波形变换电路`，非 F1），
  用于验证管线；**不是 F1 PCB 的产物**。

## 环境与副本

- 客户端 4.1.78（bridge 4.1.78.34f5b8d9），CLI 半离线 headless。
- 基线副本：`f1-b-v5.eprj2`（B 包交付副本，含 10 张审计原理图，F1-USB-MCU-C = `7156417783355f32`，
  页 `f6d41a58df3fa849`；工程内既有 PCB `b2f4d387989c4c63ac68533b05f0eee3` 属旧板）。
- 实验副本：`f1-pcb-f2.eprj2`、`f1-pcb-f3.eprj2`（建板/导入实验）、`f1-pcb-demo.eprj2`（布局/布线演示）。

## 真机结果

| 步骤 | 命令/API | 结果 | 证据 |
|---|---|---|---|
| 建游离 PCB | `DMT_Pcb.createPcb()` | 成功，返回 uuid | probe-min / probe-step-e |
| 按板名建 PCB | `createPcb('F1-USB-MCU-C')` | 成功，PCB 归属该板 | probe-step-e |
| 建板（关联） | `DMT_Board.createBoard(schUuid, pcbUuid)` | 成功，boards 列表含 pcb+sch 双关联 | probe-step-a |
| 原理图→PCB 导入 | `pcb_Document.importChanges({uuid, force:true})` | **返回 true，计数 0→0（无物化）** | `import-noeffect.json`（执行器，exit 1） |
| 自动布局 | `pcb_Document.autoLayout()` | 成功 33/33，16.7s | `layout.json` |
| 板框 | `pcb_PrimitiveLine.create(net, 11, …)` | **所有网络变体均报「参数不正确」**；同坐标 layer 1 + GND 对照成功 | probe-outline-variants3 |
| 自动布线 | `pcb_Document.autoRouting()` | 成功，13/17 网络（重排后）；保存 | `route.json` |
| 保存后重开 | `pcb reopen-check` | match；线 152、各网络均有铜（GND 139 段…） | `reopen.json`、`read-after-route.json` |

补充事实：客户端 `successNetsCount` 与「是否真正连通」不是一回事——4 个 failed 网络在快照里仍有
部分铜（`$1N10660` 仅 1 段 0 长度）；**连通性必须用网络图元覆盖 + DRC 判断，不能只看 success 标志**。

## F 的剩余动作（需要用户一次 GUI 操作）

1. 在 GUI 全在线会话打开工程副本，选 F1-USB-MCU-C 板执行「导入/更新 PCB」；
2. 在 GUI 画板框（或确认导入后已有板框）；
3. 之后可交回 CLI：`pcb layout` → `pcb route --save` → `pcb drc` → `pcb reopen-check`。

## 能力矩阵增量（4.1.78 半离线 CLI）

| 能力 | 状态 |
|---|---|
| PCB 创建 / 板关联 | 可用 |
| 原理图→PCB 导入 | **不可用（返回 true 但无物化）** |
| 自动布局 | 可用 |
| 自动布线 | 可用（结果需按网络覆盖复核） |
| 板框绘制（layer 11） | **不可用（API 拒绝）** |
| 保存 / 重开比较 | 可用 |
| Gerber/CPL/BOM 导出 | 不可用（此前证据：getter 返回空对象） |
