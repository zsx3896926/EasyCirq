# EDA 会话契约（插件 / 运行时 / Skill 三层）

> 2026-10-30 C 板写入事故复盘后定稿。目标：**"写错窗口 / degraded 下硬写 / 重启后从零再来"三类事故在机制上不可能发生。**

## 事故链（真实证据）

1. EasyEDA 注册了**两个窗口**；`health` 汇总两窗口健康，读到的是 A 窗口 `degraded:false`；
2. 写请求按 `--window` 落到 B 窗口，B 的 `writeHealth.degraded=true`；
3. 109 次 `connect_pin` 全部返回 `{"ok":false,"result":{"degraded":{...}}}`，**一次都没进入几何校验**；
4. 器件放置"成功"但从未 `save` 落盘；重启后页面回到空白，43 器件全部丢失。

## 三层职责

### A. EasyEDA 插件（`connector/src/`）

| 能力 | 现状缺口 | 应实现 |
|---|---|---|
| 上下文上报 | `context` 只保证有 `pageVisibility`；无工程时缺 `projectUuid/documentUuid/documentType` | 连接与每次响应都带完整上下文，无工程时显式 `{"projectBound": false}` |
| 写前置校验 | 无工程也接受写请求 | 写类 action 在**无工程绑定时直接拒绝**，返回 `NO_PROJECT_BOUND` |
| 健康上报 | `writeHealth` 只有样本/失败率 | 每次失败附 `{phase: preflight|apply|verify, code, action, degraded}` 与**进入/解除 degraded 的条件** |
| 落盘语义 | 存在"放置成功但未保存" | 提供幂等 `save` / `reload` 并回读 hash；`dirty` 状态随上下文上报 |
| 单写者 | 无限制 | 同文档同一时刻只接受一个 `sessionId` 写入 |

落点：`connector/src/eda-context.ts`（上下文）、`connector/src/actions.ts`（dispatch 前门控）、`connector/src/schematic-readiness.ts`（前置校验扩展）、`connector/src/protocol.ts`（新错误码/字段）。

### B. 连接器/运行时（CLI + agent）

| 能力 | 现状缺口 | 应实现 |
|---|---|---|
| 会话绑定 | 每条命令各自传 `--window`，多窗口时歧义 | `easycirq session bind --project <uuid>` 要求"恰好一个窗口打开该工程"，落盘 `session.json` |
| 写入门控 | 无统一检查 | 写前检查：绑定有效 + `degraded:false` + `failureRate:0` + context 匹配；任一不过即拒写 |
| 恢复 | 只能人工重启 | `session recover`：daemon restart → connector reload → 提示重启 → 重新绑定；`session resume` 从 journal 续跑 |
| 幂等 + journal | 在脚本层临时实现 | 下沉为运行时能力：place 已存在则 skip、pin 已在目标网则 skip，操作级 journal |
| 健康语义 | 布尔 degraded | 返回"是否可自愈 + 建议动作" |

### C. Skill（工程纪律）

- **B4 写入纪律**：写入必须经 session；多窗口/未绑定/degraded 时**停止并报告**；禁止临时脚本直连 CLI 批量写。
- **B3.5 落盘纪律**：每批写后 `reload` + **回读校验**（器件数/网络成员数 == 计划）才算提交。
- **B7 交付物**：`session.json` / `journal.jsonl` / `writeHealth.json` 必须随交付物提供。
- **B8 事故档案**：收录本次链条（多窗口 → degraded → 109 连败 → 重启空页）。
- **B10 smoke**：新增"只写一半 → 重启 EDA → 从 journal 续跑 → 43/109 校验"用例。

## 验收判据（缺一不可）

1. 绑定阶段：窗口数 ≠ 1 → 拒绝开始，并说明原因；
2. 写入阶段：任一批出现 `degraded` → 立即停，恢复后从 journal 续跑；
3. 落盘阶段：每批回读数量与计划一致，否则该批不算提交；
4. 恢复阶段：重启后 `session resume` 能把未完成的 43 器件 / 109 连线补齐，不需要从零重放；
5. 追溯阶段：任何失败都能从 `session.json` + `writeHealth.json` 定位到"窗口、阶段、错误码"。
