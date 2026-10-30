# EDA 负载纪律（真机批量操作运维手册）

真机 EDA 写入不是"越快越好"：连接器在高频写入后会进入 `degraded`，表现为
**假失败**（写入可能已落地）、`power.connect_pin` 拒绝、`document.current` 超时，
甚至 `daemon restart` 挂起。以下纪律来自 2026-10-29/30 的实战（A/B/C 修复、
整页重放 48 器件、区域重放 43 器件）。

## 1. 批量规模

| 操作类型 | 建议上限 |
|---|---|
| 连续 `sch place` | ≤ 50 次/批 |
| 连续 `sch connect` | ≤ 60 次/批 |
| 单批总命令数 | **≤ 100**（`easycirq-replay-plan/v1` 默认值） |

批尾必须做检查点：

```
easycirq doc reload <page> --project <project>   # 保存并重开
easycirq daemon health                            # 看 degraded
```

`easycirq-replay-plan/v1` 的 `batches[].checkpoint` 已内置这两条。

## 2. 验证优先于重试（假失败定律）

连接器返回失败时**不要盲重试**。先做轻量读（`doc ready` / `sch connectivity`）
确认写入是否已落地：

- 已落地 → 继续下一步；
- 未落地且 `degraded=true` → **中止本批**，执行第 3 节恢复流程。

单引脚多方向重试会把耗时指数级放大（5 offset × 4 direction × 2s ≈ 40s/失败引脚）。

## 3. 连接器恢复流程（degraded / 超时 / restart 挂起）

1. `Get-Process easycirq-agent | Stop-Process -Force`
2. `Get-Process lceda-pro | Stop-Process -Force`
3. 重新启动 EasyEDA：`C:\Users\jlc\AppData\Local\Programs\lceda-pro\lceda-pro.exe`
4. 等待 40–60s，`easycirq health` 应显示新 `windowId`、`status: ok`、`degraded: false`
5. 用新 windowId（或 `--project` 路由）重新打开工程与页面
6. **先回读**上次改动（快照 + 评审），确认数据未丢失，再继续

## 4. 数据安全

- 每批结束 `doc reload`（保存+关闭+重开）——EasyEDA 的改动只在内存，重启会丢；
- 批量前先 `easycirq project export` 或确认工程已保存；
- 失败恢复后必须**重新快照评审**，不能假设状态未变。

## 5. 重放选型

| 场景 | 选择 |
|---|---|
| 复现已验证的好页面 | 整页模板（`tools/page_template.py` + `--replay`） |
| 只复用某个块 | 区域模板（`tools/region_template.py`，信号闭包） |
| 区域与整页等价（闭包后 ≈ 全页） | 直接整页，少一层变量 |

已知边界：电源/地轨不参与信号闭包，所以区域重放可能出现 R04（地 tie 在区域外）
和 R08（测试点在区域外）——这是选型结果，不是缺陷；需要全绿就用整页模板。
