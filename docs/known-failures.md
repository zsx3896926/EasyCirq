# 已知失败（Go 全量套件，2026-10-31 更新）

## 现状

| 范围 | 失败数 | 说明 |
|---|---|---|
| `runtime/internal/app` | 12 | 本轮从 13 降到 12（修掉 `TestDeliverablesGerberDrillCplAreGuiOnly`） |
| `runtime/internal/daemon` | 0（单独跑）/ 2（全量跑） | `TestExplicitSave*` 单独跑通过，全量跑失败 → **测试顺序依赖** |

上一轮修掉了 `TestBuildCapabilitiesUnsupportedItemsStayUnsupported`。

## CI 策略

`.github/workflows/validate-go.yml`：

- **阻断**：`TestGate*`（daemon）与 `TestStatus|TestSetup|TestCard|TestAcceptance`（app）
- **只报告**：`go test ./...` 与 `go vet ./...`（`|| true`）

## 已取证的归类

| 测试 | 现象 | 归类 |
|---|---|---|
| `TestBuildCapabilitiesUnsupportedItemsStayUnsupported` | 期望 gerber/drill/cpl unsupported，实际 supported | **已修**：改为断言「无 action 的能力不得 supported」 |
| `TestDeliverablesGerberDrillCplAreGuiOnly` | 期望 `gui_only`，实际 `api_untested` | **已修**：改为断言「gui_only ⇔ 无 typed action」，并断言这三项现在必须有 action |
| `TestExplicitSave*`（daemon，2 个） | 单独跑 ok，全量跑 FAIL | **顺序依赖**：测试间共享状态；需定位是哪个前置测试污染 |
| `TestStripArtifactNesting` | `rooted pair: got "." , want "\\"` | **Windows 路径差异** |
| `TestResolveEnrichScript*`（2 个） | 期望找不到脚本时报错，实际未报错 | **环境依赖**：本机存在 vendored `bom-enrich.py` 副本 |
| `TestSchDesignatorsOutputAliasesRejected/symlink` | symlink 子用例失败 | **Windows symlink 行为**（创建/解析与 POSIX 不同） |
| `TestProjectDrawings*`（7 个） | `schematic readback: evidence SHA256 mismatch` 等 | **渲染/回读证据 hash 不匹配**，与渲染器输出或夹具版本有关 |

## 未取证的

`TestLayoutReportRefusesPathAliasesBeforeWriting` 未逐条看错误，**不归类**。

## 待办

1. 定位 daemon 两个测试的顺序依赖（找出污染源）；
2. `TestProjectDrawings*` 的 hash 失配需要确认是渲染器版本还是夹具过期；
3. 平台差异类按 `runtime.GOOS` 分支，而不是放宽断言；
4. 全绿后把 `validate-go.yml` 的「报告」改为「阻断」。
