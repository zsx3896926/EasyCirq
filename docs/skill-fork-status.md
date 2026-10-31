# Skill 副本状态（2026-10-31，第 17 轮更新）

## 事实

| 位置 | SKILL.md 契约版本 | `.version` | 说明 |
|---|---|---|---|
| `~/.agents/skills/easycirq`（生效） | v3.5（已合并双模式） | 4.0.0 | 客户端实际加载的副本 |
| 仓库 `easycirq/` | v3.5（已合并双模式） | 1.1.0 | 开发仓库 |

两份 **SKILL.md 内容一致**（第 16 轮同步时以仓库为准覆盖），差异只剩 `.version` 元数据。

## 已合并的内容

- 双模式判定（咨询 R0–R12 / 施工 build-mode.md）
- §4「原理图：离线先行」四步 + 客户旅程指针
- `references/build-mode.md`、`references/customer-journey.md`、`references/schematic-offline-first.md`
- `metrics/schematic-kpi.v1.json`（skill 内副本，防漂移测试覆盖）

## 第 16 轮踩到的坑

同步 SKILL.md 到安装副本时**只复制文件、没跑 selftest**，导致：

1. 安装副本的 SKILL 被仓库 v3.5 覆盖（原为 v4.0），版本号与内容暂时不一致；
2. v3.5 引用的两个文件在安装副本里不存在（`pcb-placement-benchmarks.md`、
   `engineering-deepdives/exercises-pcb/`），selftest 报 2 条链接失效。

已补齐文件，两份 selftest 均为 6 PASS。

## 现在的同步流程（必须遵守）

```bash
# 1. 复制 SKILL.md 与新增 references
# 2. 必须跑两份 selftest
python easycirq/scripts/skill_selftest.py                    # 仓库
python ~/.agents/skills/easycirq/scripts/skill_selftest.py   # 生效副本
# 3. 两者都 6 PASS 才能说“技能已更新”
```

## 判定

内容一致、版本号不同（`.version` 4.0.0 vs 1.1.0）。版本号属于分发元数据，
不影响运行；但对外宣称版本时以 `.version` 为准，并注明 SKILL.md 契约是 v3.5。
