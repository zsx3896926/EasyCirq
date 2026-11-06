# 原理图预览 · 图面验收报告

> 由 `sch_preview_report.py` 从真实执行产物生成；表格里每个状态都能用下方命令复现。

## 判据总表

| 判据 | M1 | M2 | M3 | M4 | M5 |
|---|---|---|---|---|---|
| 内容不越框 | ✅ | ✅ | ✅ | ✅ | ✅ |
| 导线不穿器件本体 | ❌ | ❌ | ✅ | ✅ | ✅ |
| 模块框不切器件/导线 | ✅ | ❌ | ✅ | ✅ | ✅ |
| 遮字/文字相压 | ✅ | ✅ | ✅ | ✅ | ✅ |
| 标签落在真实端点、朝向一致 | ➖ | ➖ | ➖ | ➖ | ➖ |
| 网标朝向一致 | ✅ | ✅ | ✅ | ✅ | ✅ |
| 重复网名/孤立文字 | ✅ | ✅ | ✅ | ✅ | ✅ |
| 不同网络导线交叉无结点 | ⛔ | ⛔ | ⛔ | ⛔ | ⛔ |
| 图签无重复文字 | ✅ | ✅ | ✅ | ✅ | ✅ |
| 分区阅读顺序 | ✅ | ✅ | ✅ | ✅ | ✅ |
| 审图 PNG 可读性 | ✅ | ✅ | ✅ | ✅ | ✅ |

## 逐块统计

| 模块 | 判定 | 通过 | 失败 | 缺证据 | 不适用 | 已知误报 |
|---|---|---|---|---|---|---|
| M1 | BLOCKED | 8 | 1 | 1 | 1 | 76 |
| M2 | BLOCKED | 7 | 2 | 1 | 1 | 23 |
| M3 | INCOMPLETE | 10 | 0 | 1 | 1 | 24 |
| M4 | INCOMPLETE | 10 | 0 | 1 | 1 | 37 |
| M5 | INCOMPLETE | 10 | 0 | 1 | 1 | 29 |

## 未通过 / 未测 / 不适用（逐条）

### 导线不穿器件本体 — ❌

理由：

涉及模块：M1、M2（各 16 项）
样例：`['w-M1-3#0', 'svgtext-88']`

### 模块框不切器件/导线 — ❌

理由：

涉及模块：M2（各 1 项）
样例：`['frame-M2', 'svgtext-3']`

### 标签落在真实端点、朝向一致 — ➖

理由：本图没有 netport/netlabel 图元（只有电源/地符号与网标），该判据无对象可测

### 不同网络导线交叉无结点 — ⛔

理由：no host no-junction evidence for this crossing

下一步：`easycirq sch junction-report --page <P>`

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

- **位号贴在本体角上**：56 项 —— 预览渲染器的排版约定
- **引脚名画在自己本体内**：133 项 —— 箱形符号的正常画法
