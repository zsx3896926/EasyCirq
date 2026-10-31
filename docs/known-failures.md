# 已知失败（Go 全量套件，2026-10-31 更新）

## 现状

`go test ./...` 在 Windows 上仍有 **15 个失败**（上一轮 16，本轮修掉 1 个：
`TestBuildCapabilitiesUnsupportedItemsStayUnsupported`）。

## CI 策略

`.github/workflows/validate-go.yml`：

- **阻断**：`TestGate*`（daemon）与 `TestStatus|TestSetup|TestCard|TestAcceptance`（app）
- **只报告**：`go test ./...` 与 `go vet ./...`（`|| true`）

## 已取证的归类

| 测试 | 现象 | 归类 |
|---|---|---|
| `TestBuildCapabilitiesUnsupportedItemsStayUnsupported` | 期望 gerber/drill/cpl 为 unsupported，实际 supported | **已修**：这三个能力 2026-10-28 已有 typed action（`pcb.manufacture.gerber/.cpl`），测试硬编码的 id 列表过期；改为断言「无 action 的能力不得 supported」 |
| `TestExplicitSaveCancelsOnlyConfirmedOlderTarget`（daemon） | 显式保存取消了更新的变更 | **基线已确认**：`git stash` 后同样失败，非本轮引入 |
| `TestStripArtifactNesting` | `rooted pair: got ".", want "\\"` | **Windows 路径差异**：测试期望根前缀 `\`，实现返回 `.` |
| `TestResolveEnrichScriptNotFoundListsProbedPaths` | 期望找不到脚本时报错，实际未报错 | **环境依赖**：本机存在 vendored `bom-enrich.py` 副本，测试前提（仓库内无副本）不成立 |
| `TestProjectDrawings*`（7 个） | `schematic readback: evidence SHA256 mismatch` 等 | **渲染/回读证据 hash 不匹配**，与渲染器输出或夹具版本有关 |

## 未取证的

`TestDeliverablesGerberDrillCplAreGuiOnly`、`TestSchDesignatorsOutputAliasesRejected`、
`TestLayoutReportRefusesPathAliasesBeforeWriting`、daemon 的
`TestExplicitSaveHTTPInFlightKeepsNewMutationPending` 未逐条看错误，**不归类**。

## 待办

1. 逐个确认剩余失败是环境差异还是真实缺陷；
2. 若是平台差异，测试应按 `runtime.GOOS` 分支，而不是放宽断言；
3. 修完后把 `validate-go.yml` 的「报告」改为「阻断」。
