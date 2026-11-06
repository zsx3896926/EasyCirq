# 原理图预览交付说明（板2-24V隔离控制板）

> 本文件是入口。每条结论都能用文中的命令复现；跑不出来就是我的问题。

## 结论

| 模块 | 器件 | 状态 | 说明 |
|---|---|---|---|
| M3 5V→3.3V 主逻辑轨 | 7 | **可交付** | 12 条判据 10 PASS / 0 FAIL / 1 N/A / 1 NOT RUN |
| M4 5V→升压轨 | 10 | **可交付** | 同上 |
| M5 升降压 3.8V | 7 | **可交付** | 同上 |
| M1 车辆宽压输入 | 24 | **不交付** | 实测 16 处导线穿位号；渲染门拒绝出图 |
| M2 第二路 buck | 8 | **不交付** | 实测 3 处；同上 |

三条"可交付"的模块，图上五类缺陷全为 0，风格 token 0 违规。

## 一条命令复现

```bash
python scripts/sch_preview_accept.py --work reports/hard-board/board2
python scripts/sch_preview_report.py --work reports/hard-board/board2   # 一页纸报告
python scripts/sch_style_check.py --work reports/hard-board/board2 \
    --frames "M3=reports/hard-board/board2/review/frames-<页名>.json" ...
```

**从零复现**：删掉 `board2` 下除 `composition-*.json` 之外的产物再跑，结论不变（verified）。

## 判据（12 条，来源与现状）

| # | 判据 | 来源 |
|---|---|---|
| 1–4, 6–7 | 内容/导线/框/遮字/网标朝向/重复网名 | 技能 `sch_layout_check --strict` |
| 5 | 标签落在真实端点 | 技能（本设计 N/A）|
| 8 | 交叉无结点 | NOT RUN：需现场结点证据 |
| 9–10 | 图签无重复文字 / 分区阅读顺序 | 本仓补 |
| 11 | 文字审计 | 技能 `sch_text_audit --strict` |
| 12 | 审图 PNG 可读性 | 本仓补（五类缺陷判据）|

每条 PASS 都带**受检对象数量**（`checked` 字段），避免"没查也算过"。

## M1/M2 为什么不交付

**不是算法不行。** 九次尝试（几何目标化 / 求解器预留 / 门驱动 / 写进渲染器 /
两遍渲染 / 迷宫障碍 …）全部记录在 `reports/hard-board/board1/friction.md`。

根因：位号占住的那条带，正是网标命名要用的带。24 件的模块在"避开位号"前提下
排不出；求解器在加 1~4 个预留区后就耗尽命名空间。

要解决需要**布局策略决策**（例：把 24 件拆成两页，或降低密度），
这不属于"预览"能决定的事。当前行为是**拒绝出图**，而不是交一张有缺陷的图。

## 已知差距（不假装完美）

- **纸面利用率**：一页一模块，内容占 6%~11%；参考样图一页 4 分区所以更满。
  解决办法是按内容选纸，代价是图签/网格重排；裁剪画布试过，会让图签压到电路上。
- **自由文字注记**：样图有 `CLOSE TO IC` 这类红色注记，本渲染器无此能力。
- **`sch gate` / `sch layout-score`**：需要活的 EasyEDA，本会话 NOT RUN。

## 证据在哪

| 内容 | 位置 |
|---|---|
| 逐轮记录（136 条）| `reports/hard-board/board1/friction.md` |
| 一页纸验收 | `reports/hard-board/board2/ACCEPTANCE.md` |
| 状态汇总（含过期判定）| `reports/hard-board/board2/STATUS.md` |
| 审图 PNG | `reports/hard-board/board2/review/*.png` |
| 判据与命令 | `easycirq/references/preview-acceptance.md` |
