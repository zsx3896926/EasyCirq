---
id: EXEC-LAYER-RETIRE-01
title: 执行层架构决策：自建 easycirq runtime 的去留（“退 A”分阶段迁移方案）
last_reviewed: 2026-10-28
status: draft
sources: [PR-75, PR-97, release.yml, distribution/build_release.py]
---

# 执行层架构决策：自建 easycirq runtime 的去留（“退 A”分阶段迁移方案）

> 用途：把“是否退掉自建 A 执行层（`runtime/` + `connector/` + `protocol/`）、改走官方 `lceda-pro` CLI/MCP”这件跨模块、不可逆的决定，写成可复核的分阶段方案与重评门禁。
> 证据边界：本记录是 `E3` 方法整理（基于仓库现状、CI/发布配置与在途 PR 的离线材料），**未做真实 EDA 写入回读、未做硬件验证**；不证明官方 CLI 与自建 runtime 已对等。

## 1. 决策头

| 字段 | 值 |
|---|---|
| 决策 ID / 标题 | EXEC-LAYER-RETIRE-01 / 自建 easycirq runtime 的去留 |
| 需求来源 | 复盘 `skill-shortcomings.md`（执行层维护负担）与在途 spike PR #75、删除 PR #97 |
| 状态 | **draft**（未冻结；冻结条件见 §7） |
| 冻结条件 | 官方 CLI 在真实工程上完成全部 11 个工作流的对等证明后，才从 draft 转 frozen |
| 决定人/日期 | 2026-10-28（Agent 记录；owner 决定 go/no-go） |
| 受影响对象 | `runtime/**`、`connector/**`、`protocol/**`、`distribution/**`、`.github/workflows/release.yml`、`easycirq/**`（SKILL 执行面）、`tests/**`、B1 task-launcher 的 plugin/agent 注入、全套文档与证据 |

## 2. 背景与现状（已核实）

- 自建 A 执行层 = `runtime/`（Go daemon + `cmd/easycirq`，**1009 个 tracked 文件**）+ `connector/`（`.eext`）+ `protocol/`（合计再 141 个文件）。
- 它不是遗留死代码：`.github/workflows/release.yml` 正在把 `runtime/cmd/easycirq` `go build` 成 `easycirq.exe` / `easycirq_windows_amd64.exe`，再由 `distribution/build_release.py` 打进 `easycirq-toolchain-<version>.zip`；Skill 的 `easycirq doctor/capabilities/sch/pcb/project/doc/apply/dump/drc/save/reload…` 全部跑在它上面。
- 在途材料：
  - **PR #75**（`spike/a2-thin-layer`，draft）：官方 `lceda-pro` CLI/MCP 覆盖度 spike，结论 `decision-provisional` / **medium confidence**——只证了一次性 write probe（W04/W05/W09 在临时副本上 `covered`）+ Gerber/CPL 导出。
  - **PR #97**（`chore/retire-a-runtime`，draft / “migration pending”）：一次性删除 `runtime/`+`connector/`+`protocol/` 并回退到官方 CLI 基线。

## 3. 备选方案

| 备选 | 功能满足 | 关键约束 | 代价（维护/风险/周期/能力） | 排除判据 | 什么条件下重新考虑 |
|---|---|---|---|---|---|
| A：保留自建 runtime | 全部现有 `easycirq <cmd>` 面可用 | 自建 ~1700 文件是持续维护负担，且与官方 CLI 重复实现 EDA 执行 | 维护成本持续；官方 CLI 更新不自动跟进 | 官方 CLI 长期缺写通道（当前已局部证到 write probe covered） | 官方 CLI 出现不可接受的能力回退或稳定性问题时 |
| B：一次性删除切官方（#97 现状） | 官方 CLI 覆盖“已测”工作流 | medium confidence 不足以支撑不可逆大删；删除面远大于“69 skill 文件 + 24 测试文件” | 一次性切断执行面/installer/release/B1 注入/全套测试；迁移未完成即删 | **证据不足（medium confidence）、迁移未完成、删除面被低估** | 对等证明做到高置信后，作为“清死代码”收尾而非 big-bang |
| C：分阶段迁移（本记录） | 阶段门禁保证每一级不丢能力 | 需在真实工程上做对等证明；期间双路径并跑 | 短期多一套薄适配层；周期较长 | 无 | 被选方案 |

## 4. 被选方案与代价

- **选择**：C（分阶段迁移），把 #97 从“big-bang 删除”降级为“迁移完成后的收尾删除”。
- **依据**：`runtime/` 是当前仍在构建/发布的执行核心；#75 只是 medium confidence；官方 CLI 是第三方表面，存在版本漂移与能力空档风险。
- **接受的代价**：双路径并跑期多维护一个薄适配层；退 A 周期拉长；迁移完成前不自删、不回退文档。
- **假设与有效期**：
  - 官方 `lceda-pro` CLI/MCP 的写通道（W04/W05/W09）在 2026-10-28 之后保持可用（有效期：官方 CLI 每次版本升级需重核）。
  - 自建 runtime 的 192 个 CLI 条目里，除“已测覆盖”项外没有官方 CLI 拿不到的关键能力（**未证，待对等矩阵补齐**）。
- **重评触发**：官方 CLI 版本升级；write probe 或其它 workflow 由 covered 回退；自建 runtime 出现关键 bug 需要立即修；owner 改变产品/交付策略。

## 5. 分阶段迁移计划（门禁制）

| 阶段 | 动作 | 门禁（满足才进下一阶段） |
|---|---|---|
| S1 并行落地 | 把 #75 的薄适配层（`official_cli.py` 等）作为**并行非默认**路径落地，与 `easycirq` runtime 并跑 | 薄适配层可被现有测试/基准驱动 |
| S2 对等证明 | 用官方 CLI 跑完一个**真实项目**，逐 workflow 补齐对等矩阵（全部 11 个，不只 write probe） | 对等矩阵 0 空档；稳定性/错误处理无 runtime-only 回归 |
| S3 冻结 | 冻结 `runtime/`：停新功能，仍构建/发布作兜底 | 连续 N 个真实项目无 runtime-only 回归（N 待 owner 定） |
| S4 切换 | 文档/installer/tests 切到官方路径；`easycirq` 命令变薄壳或 `easycirq call` 兜底 | 切换后全量 + `offline_suite` 全绿，无断点 |
| S5 删除 | 这时才把 `runtime/`/`connector/`/`protocol/` 当“清死代码”干净删掉（重做版 #97） | 删除后全量 + `offline_suite` + 发布流水线（skill-only）全绿 |

## 6. 关键风险与未知（unknown-retained）

- **官方 CLI 版本漂移**：薄适配层依赖第三方 `lceda-pro` CLI/MCP，其升级可能破坏写通道或参数；owner：官方 CLI 每次升级重跑对等矩阵。
- **能力空档**：自建 runtime 的 192 条目是否被官方 CLI 全覆盖，只有 write probe + 导出已证，其余未证；owner：S2 补齐。
- **删除面被低估**：#97 body 写“69 skill 文件 + 24 测试文件”，但实际还牵连 release 流水线、installer、B1 launcher 注入、全套证据；owner：S5 前重新盘点。
- **回退不可逆**：删除后若要恢复自建 runtime，代价等于重建；owner：S3 冻结前保留可回退基线。

## 7. 冻结与重评

- **冻结条件**：S2 对等矩阵 0 空档 + S4 切换全绿之后，本记录从 draft 转 frozen。
- **重评触发**：官方 CLI 升级；write probe/对等项回退；owner 改变方向；出现官方 CLI 无法替代的关键能力。

## 8. 验证与边界

- **已执行**：仓库现状盘点（`runtime/` 1009 文件、`connector/`+`protocol/` 141 文件、release.yml 构建 `runtime/cmd/easycirq`）、在途 PR #75/#97 材料核对。
- **未执行（NOT RUN）**：真实 EDA 写入回读、真实工程对等矩阵、官方 CLI 稳定性长测、S1–S5 各阶段落地。
- **结论状态**：**有条件满足 / draft**（方案成立，但门禁证据未集齐）。
- **不能证明**：本记录不证明官方 CLI 与自建 runtime 已对等，不证明删除无回退风险，不证明硬件/EDA 工程已验证。

## 9. 与在途 PR 的关系

- **#75（spike）**：保留，作为 S2 对等矩阵的证据来源与“为什么退”的决策依据。
- **#97（删除）**：不开工，降级为“S5 才执行的收尾删除”的 checklist；其“migration pending”与“删除面 69+24”需在 S5 前重写为完整盘点。

## 10. 使用位置

本记录由 repo owner / 集成人维护；`used_by`：PR #75、PR #97。这是仓库/toolchain 架构决策，与 `references/decisions/`（A–L 硬件设计决策库）并列，不并入其 12 文件索引。
