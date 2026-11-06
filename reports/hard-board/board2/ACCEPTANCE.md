# 原理图预览 · 图面验收报告

> 由 `sch_preview_report.py` 从真实执行产物生成；表格里每个状态都能用下方命令复现。

## 判据总表

| 判据 | M1 | M2 | M3 | M4 | M5 |
|---|---|---|---|---|---|

## 逐块统计

| 模块 | 判定 | 通过 | 失败 | 缺证据 | 不适用 | 已知误报 |
|---|---|---|---|---|---|---|
| M1 | REFUSED | 0 | 0 | 0 | 0 | 0 |
| M2 | REFUSED | 0 | 0 | 0 | 0 | 0 |
| M3 | INCOMPLETE | 10 | 0 | 1 | 1 | 24 |
| M4 | INCOMPLETE | 10 | 0 | 1 | 1 | 37 |
| M5 | INCOMPLETE | 10 | 0 | 1 | 1 | 29 |

## 未通过 / 未测 / 不适用（逐条）

## 复现命令

```bash
# 一条命令跑完整条链（排版稿 → 渲染 → 实测文字 → 严格检查 → 验收）
python scripts/sch_preview_accept.py --work reports\hard-board\board2

# 文字审计（独立一项判据）
python scripts/sch_preview_textaudit.py --texts reports\hard-board\board2/texts-M3.json \
    --visible reports\hard-board\board2/visible-M3.json --out reports\hard-board\board2/visible-M3.audit.json
python <skill>/scripts/sch_text_audit.py reports\hard-board\board2/visible-M3.audit.json --strict

# 本报告
python scripts/sch_preview_report.py --work reports\hard-board\board2
```

## 已知误报（不计入失败）

- **位号贴在本体角上**：24 项 —— 预览渲染器的排版约定
- **引脚名画在自己本体内**：66 项 —— 箱形符号的正常画法
