# 从零建板：完整闭环已验证（1.3.0，2026-10-31）

> **这是目标「AI 可以独立完成」的第一次完整验证**：从空页面画出电路 →
> 离线检查 PASS → 拿到「可以打样」卡片 → 令牌生效放行交付动作。

## 最终结果

```
$ easycirq card --kpi-report reports/led-mini9/kpi-report.json
✅ 可以打样

检查结果：必查 10/10 通过 · 缺证据 0 · 不适用 4 · 提醒 1
下一步：导出制造文件；打样回来后做验收
exit=0
```

```
$ easycirq --project KPI_S5_Verify call pcb.manufacture.gerber
{"ok": false, "error": {"code": "NO_CONNECTOR"}}   ← 不再是 GATE_*，门禁已放行
```

`NO_CONNECTOR` 是「PCB 文档没打开」，另一回事——**门禁这一关过了**。

## 完整过程

| 阶段 | 命令 | 结果 |
|---|---|---|
| 画 | `sch place` ×2 + `sch connect` ×4 + `sch save` | 全部 `ok: true`（建板不需令牌） |
| 清理 | `call schematic.component.delete` ×6 | 删掉遗留悬空器件 |
| 快照 | `sch connectivity` / `sch list --include-bbox` / `sch sheet-geometry --json` | 3 个文件 |
| 补证据 | `sch drc --json` / `bom export --type csv` / `doc reload` 前后对比 | ERC、BOM、readback |
| 检查第 1 轮 | `sch_offline_pipeline.py` | `PASS (apply_allowed=False)` |
| 检查第 2 轮 | 同上 | `PASS (apply_allowed=True)`，签发令牌 |
| 卡片 | `easycirq card` | **`✅ 可以打样`** |
| 交付 | `call pcb.manufacture.gerber` | 门禁放行（`NO_CONNECTOR` 是 PCB 未打开） |

## 关键数据

| 项 | 值 |
|---|---|
| 电路 | `VCC → R11 → NLED → D1(0805 LED) → GND` |
| 器件 | 2 个（D1、R11） |
| 连接 | 4 条（sch connect 拉的桩 + 网络标签） |
| 网络 | 3 个（VCC / NLED / GND） |
| 必查通过 | 10/10 |
| 缺证据 | 0 |
| 令牌 | `PASS` + `apply_allowed: true` + `rounds_pass: 2` |

## 这一路暴露并修掉的六个问题

| # | 问题 | 性质 |
|---|---|---|
| 1 | 建板写入被门禁拦（空页面永远过不了检查） | **设计缺陷** → 分阶段门禁 |
| 2 | 管线从不传 `--sheet-geometry` | 集成缺陷 |
| 3 | 纯标签连线页面无导线 → 连线度量报错 | 集成缺陷 → 管线记 n/a |
| 4 | `sch list` 不输出 bbox → 布局适配器丢弃所有器件 | **文档缺失** |
| 5 | `net_flags[].anchor` 为 null 时崩溃 | **真实 bug** |
| 6 | 删除器件要用 `call ... --payload '{"primitiveIds":[...]}'` | 文档缺失 |

## 边界（不要夸大）

- 这块板**只有 2 个器件**，是一个 LED 指示灯，不是产品。
- 「可以打样」指的是**离线检查通过**，不是「实物能用」。
- 没有真实打样，`acceptance` 从未收到过真实实测数据。
- PCB 尚未创建，所以制造文件还没真正导出。

## 意义

目标里最难的一条——「AI 可以独立完成」——在工具层面被走通了一次。
这六个问题**没有一个能靠读代码发现**，全部来自真的从零画一遍。
