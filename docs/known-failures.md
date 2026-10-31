# 已知失败（Go 全量套件，2026-10-31 更新）

## 现状

`runtime/internal/app`：**0 失败**（本轮从 6 降到 0；累计从 14 降到 0）。

剩余 4 个，全部不在本次改动范围内：

| 包 | 测试 | 性质 |
|---|---|---|
| `daemon` | `TestExplicitSaveHTTPInFlightKeepsNewMutationPending` | 顺序依赖：单独跑 ok，全量跑 FAIL |
| `daemon` | `TestExplicitSaveCancelsOnlyConfirmedOlderTarget` | 同上（且已确认在基线上也失败） |
| `selfupdate` | `TestUpdateCLIReplacesBinaryAndVerifiesChecksum` | 本轮首次暴露，未取证 |
| `selfupdate` | `TestLocalBundleChecksContentsNotMarkers` | 本轮首次暴露，未取证 |

## CI 策略

`.github/workflows/validate-go.yml`：

- **阻断**：`TestGate*`（daemon）与 `TestStatus|TestSetup|TestCard|TestAcceptance`（app）
- **只报告**：`go test ./...` 与 `go vet ./...`（`|| true`）

app 现已全绿，下一轮可以把「阻断」范围扩大到整个 app 包。

## 本轮修掉的（app 6 → 0）

| 测试 | 根因 | 修法 |
|---|---|---|
| `TestStripArtifactNesting` | **真实 bug**：Windows 上根相对路径 `\.easycirq\artifacts` 的 `filepath.IsAbs` 为 false，返回值从 `\` 变成 `.` | 实现改为 `IsAbs(clean) || HasPrefix(clean, sep)` |
| `TestResolveEnrichScript*`（2） | **真实缺口**：cwd walk-up 的技能名清单缺 `easycirq`（只有 design-hardware / easycirq-agent / easycirq-schematic） | 名单加上 `easycirq/scripts/` |
| 同上（主机侧断言） | 本机真的装了 skill，installed rung 先于 cwd 命中 | 用行为检测 `realInstallWins` 显式 skip 并说明 |
| `TestSchDesignatorsOutputAliasesRejected/symlink` | Windows 创建符号链接需提权 | 共享 helper `skipWithoutSymlinkPrivilege` |
| `TestLayoutReportRefusesPathAliasesBeforeWriting` | 同上 | 同上 |
| `TestResolveEnrichScriptNotFoundListsProbedPaths` | 同「真实缺口」+ 主机安装 | 名单修复 + 行为 skip |

## 上一轮修掉的（app 14 → 6）

见 git 历史：能力/交付物的过期断言（改为断言规则）、ProjectDrawings 的换行/旧 metadata id/平台假设。

## 待办

1. daemon 两个 `TestExplicitSave*` 的顺序依赖：找出污染源（哪个前置测试留下的状态）。
2. `selfupdate` 两个失败取证。
3. 全绿后把 `validate-go.yml` 的阻断范围扩大。
