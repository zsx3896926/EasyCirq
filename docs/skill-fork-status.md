# Skill 副本状态（2026-10-31，第 30 轮更新）

## 事实

| 位置 | SKILL.md 契约 | `.version` |
|---|---|---|
| `~/.agents/skills/easycirq`（生效） | v3.5（与仓库一致） | 4.0.0 |
| 仓库 `easycirq/` | v3.5 | 1.1.0 |

**第 30 轮已把生效副本与仓库对齐**，逐文件 SHA-256 校验：

| 文件 | 状态 |
|---|---|
| `SKILL.md` | same |
| `references/schematic-offline-first.md` | same |
| `references/customer-journey.md` | same |
| `metrics/schematic-kpi.v1.json` | same |
| `scripts/sch_status.py` | same |
| `scripts/sch_delivery_card.py` | same |
| `scripts/sch_kpi.py` | same |

两份 `skill_selftest.py` 均 **6 PASS**。

## 为什么这轮要同步

生效副本落后了 5 个文件，其中三个是**行为修复**不是文档：

- `sch_status.py` / `sch_delivery_card.py`：PASS 但缺证据时不再说「可以打样」（1.2.1 的不虚报守卫）
- `sch_kpi.py`：gate 令牌记录 `project_uuid`，uuid 定向写入才能通过 daemon 校验

也就是说：**如果 agent 走 Python 路径而不是 CLI，之前会拿到旧行为**。

## 同步流程（必须遵守）

```bash
# 1. 二进制复制（不要用 Get-Content/Set-Content，会改换行导致哈希不一致）
Copy-Item easycirq/SKILL.md ~/.agents/skills/easycirq/SKILL.md -Force
# 2. 复制改动的 scripts / references
# 3. 两份 selftest 都必须 6 PASS
python easycirq/scripts/skill_selftest.py
python ~/.agents/skills/easycirq/scripts/skill_selftest.py
```

第 16 轮踩过的坑：只复制文件、没跑 selftest，导致链接失效；第 30 轮又踩了一次
`Get-Content -Raw` + `Set-Content` 改换行——改用 `Copy-Item` 后哈希一致。

## 版本号说明

内容一致，`.version` 不同（4.0.0 vs 1.1.0）。`.version` 是分发元数据，
对外宣称版本时用它，并注明 SKILL.md 契约是 v3.5。
