# Round 12 真机纵向验证证据（独立导入副本）

本目录只记录 **EasyEDA Pro 真实宿主** 上的独立副本验证，不是模拟宿主结果。
所有写入都发生在本目录对应的独立导入副本；原工程与其它会话工程均未写入。

## 1. 目标与来源

| 项 | 值 |
|---|---|
| 独立副本 | `feedback-loop-r12-verify-20261027a` |
| 工程 UUID | `f37160f4acb64e13a80f1eb9c0a67fa3` |
| 窗口 | `c3d23f2b-8877-4ff2-b6c5-1849f2ef2dd7` |
| 原理图 / PCB 文档 | `10f78b14a3282fb6` / `49c8e7a5dc2e8f59` |
| 源文件 | `C:\Users\jlc\work\dual-button-led-night-20261027\case\evidence\case.epro2` |
| 源文件 SHA256 | `3c3d985353553fde412d71065b12fa911180c0a9d79649ac56b67bf81ddb9fc9` |
| 导入结果 | `import.json`：`ok=true`、`created=true`、`uuid=f37160f4...`、`sourceSha256` 与上表一致 |

窗口归属：jlc-b9 已在跨会话消息中明确释放该窗口并声明不再写入；随后
`doc-ready-after-move.json` 显示该窗口的 PCB 文档 `ready=true`、工程/文档 UUID 正确、
12 个器件、2/2 稳定采样；本轮没有其它写入者。`project-info.json` 的
`context.projectUuid` 与独立副本一致。用户 GUI 窗口
`5175351c-a00b-4788-a922-2f6e0bd80756` 未被抢占或写入。

## 2. 最终一轮（round 2）结果

### 2.1 移动 D4（+1.26 mil 于 Y）

| 事实 | 证据 |
|---|---|
| 观察前 | `observation-round2-before.json`：整体观察哈希 `87d9fcde...`，PCB `semanticSha256=240dee0a...`，D4 `(1595.0898, 808.74, 180)` |
| plan / preview / dry-run | `contract-round2.json`、`plan-round2-move.json`、`preview-round2-move.json`、`apply-round2-dry.json`；preview `writes_sent=0` |
| apply | `apply-round2-move.json`：`status=verified`、`writes_sent=1`、`call_ok/write_confirmed/save_confirmed/reopen_confirmed=true`、`quality_passed=null` |
| 回读差异 | 2 个范围内变化：D4 pose + `hole-owner:D4`；`outside_scope=0`；12 条锁定状态 unknown |
| 回读后 | `observation-round2-after-move.json`：PCB `semanticSha256=25d934fe...`，D4 `(1595.0898, 810, 180)` |
| 原生 DRC | `drc-round2-after-move.json`：`passed=false`、`total=4`，均为 `Clearance Error`（GND 铜箔与 D4 焊盘 8.8mil，要求 ≥10mil） |
| 评价 | `evaluate-round2-move.json`：`verdict=fail`，hard fail 4 条 `drc-clearance-error`；工程质量 warn `power-not-poured`；可读性 unknown |
| verify | `verify-round2-move-with-drc.json`：`verdict=fail`、`completed=false`、`target_met=true`、`quality_passed=false`；目标只要求“范围内至少 1 项且范围外 0 项”，因此 `target_met` 为 true，但质量失败使 `completed` 为 false |

这一轮故意移动了会靠近 GND 铜箔的 THT 器件；反馈闭环正确地把 DRC 回归判为
硬失败，没有把“写入成功”当成“质量通过”。

### 2.2 恢复 D4 并复验

| 事实 | 证据 |
|---|---|
| 观察前 | `before-round2-restore.json` / plan 绑定；观察整体哈希 `96856550...`，PCB `25d934fe...` |
| apply | `apply-round2-restore.json`：`status=verified`、`writes_sent=1`、四事实 true、`quality_passed=null` |
| 回读差异 | 2 个范围内变化、`outside_scope=0` |
| 回读后 | `observation-round2-after-restore.json`：整体观察哈希回到 `87d9fcde...`，PCB 回到 `240dee0a...`，D4 回到 `(1595.0898, 808.74, 180)` |
| 原生 DRC | `drc-round2-after-restore.json`：`passed=true`、`total=0` |
| 评价 | `evaluate-round2-restore.json`：`verdict=pass_with_warnings`，hard pass，engineering warn `power-not-poured`，可读性 unknown；`drc_zero_but_quality_issues=true` |
| verify | `verify-round2-restore-with-eval.json`：`verdict=unknown`、`completed=false`、`target_met=true`、四执行事实 true、`quality_passed=true`；不变量 `pcb_locked`/`pcb_unrelated` 仍为 unknown，因为宿主不返回锁定状态 |

恢复后 PCB 语义哈希与原始独立副本一致；源 `.epro2` 未被修改，SHA256 仍为上表值。

### 2.3 哈希口径说明

- `observation*.json` 的 `revision.semantic_sha256` 是**整体观察**哈希（原理图 + PCB），
  例如 `87d9fcde...` / `96856550...`。
- `apply*.json` 的 `baseline.after` 以及 `diff*.json` 的 `after.semantic_sha256`
  来自 **PCB dump**，是 PCB 单板哈希（`240dee0a...` / `25d934fe...`）。
  两者不同度量口径，不能直接比较；真实保存/重开是否回到原状以
  `observation-round2-after-restore.json` 的整体哈希为准。
- `apply` 的 `after_observation` 是“新鲜整体观察 + 回读 PCB dump”组合出的内部对象，
  不冒充一次完整重开观察；完整重开观察另存为 `observation-round2-after-*.json`。

## 3. 历史轮次（不用于最终验收）

- `observation-before.json`、`apply-move.json`、`diff-move.json`、`apply-restore.json`
  等是第一轮探索；第一轮声明的验收目标是 `inside == 1`，对 THT 移动过窄，
  且当时代码尚未修复 hole 归属/铜形状归一化。第一轮 keep 作历史对照，不作为最终结果。
- `apply-restore-refused-no-easyeda.json`：一次**写前拒绝**证据；未提供显式 easyeda
  路径时返回 `host_unavailable`、`writes_sent=0`，证明拒绝路径不会写入。
- `diff-move-fixed.json`：第一轮回读用修复后的 diff 重新计算，hole 变化已归入 D4。
- `observe-evidence*/`、`round2-before/after/restored/`：`observe` 命令的实际输出目录，
  每个目录含 `04-pcb-dump.json` 原始 dump；用于核对 JSON 与截图/DOM 之外的结构化事实。

## 4. 已知边界

- `pcb_locked` / `pcb_unrelated` 在真实宿主上仍为 `unknown`：适配器不回读器件锁定状态。
  工具没有把 unknown 当 pass；因此恢复后的 `verify` 是 `unknown`，不是 `pass`。
- 本轮只验证 D4 这一处 PCB 局部移动/恢复；没有执行 C2 去耦专项、原理图文本移动、
  track/via 全链路、真实并发写入或部分写恢复。
- 原生 DRC 的 `context_verified`/`identity_verified` 为 false（命令未把窗口上下文
  写入该 DRC 载荷）；DRC 的窗口归属由同一窗口的 `doc ready` 与观察捕获绑定，
  不是由 DRC 载荷单独证明。
- 本轮没有安装新客户端版本，没有发布 Release；安装版仍为 0.9.2。
