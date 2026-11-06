# 原理图预览 · 可审计状态汇总

> 由 `sch_preview_status.py` 从**真实产物**算出，不是手填。
> 产物早于对应排版稿即判 🕒 STALE，按 NOT RUN 处理。

## 目标判据 → 状态

| 判据 | M1 | M2 | M3 | M4 | M5 |
|---|---|---|---|---|---|
| 内容不越框 | 🕒 | 🕒 | ✅ | ✅ | ✅ |
| 导线不穿器件本体 | 🕒 | 🕒 | ✅ | ✅ | ✅ |
| 模块框不切器件/导线 | 🕒 | 🕒 | ✅ | ✅ | ✅ |
| 遮字 / 文字相压 | 🕒 | 🕒 | ✅ | ✅ | ✅ |
| 标签落在真实端点、朝向一致 | 🕒 | 🕒 | ➖ | ➖ | ➖ |
| 网标朝向一致 | 🕒 | 🕒 | ✅ | ✅ | ✅ |
| 重复网名 / 孤立文字 | 🕒 | 🕒 | ✅ | ✅ | ✅ |
| 不同网络导线交叉无结点 | 🕒 | 🕒 | ⛔ | ⛔ | ⛔ |
| 图签无重复文字 | 🕒 | 🕒 | ✅ | ✅ | ✅ |
| 分区阅读顺序 | 🕒 | 🕒 | ✅ | ✅ | ✅ |

## 直接跑技能自带检查器（不经封装）

| 模块 | sch_layout_check --strict | sch_text_audit --strict |
|---|---|---|
| M1 | 🕒 输入陈旧 | 🕒 输入陈旧 |
| M2 | 🕒 输入陈旧 | 🕒 输入陈旧 |
| M3 | incomplete（blocking 27） | 实测 24 / 缺陷 0 |
| M4 | incomplete（blocking 38） | 实测 37 / 缺陷 0 |
| M5 | incomplete（blocking 31） | 实测 29 / 缺陷 0 |

## 🕒 无有效结论的模块

- **M1**：产物早于排版稿 —— 需重跑流水线
- **M2**：产物早于排版稿 —— 需重跑流水线

## 复现命令

```bash
# 全链：排版 → 归位 → 出图 → 渲染 → 实测文字 → 严格检查 → 验收
python scripts/sch_preview_accept.py --work reports\hard-board\board2
# 本汇总
python scripts/sch_preview_status.py --work reports\hard-board\board2
```
