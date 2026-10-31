# 已知失败（Go 全量套件，2026-10-31 更新）

## 现状

| 包 | 状态 |
|---|---|
| `runtime/internal/app` | **0 失败**（14 → 0，三轮） |
| `runtime/internal/daemon` | **0 失败**（本轮修） |
| `runtime/internal/selfupdate` | **不稳定**：连续两次全量分别为 2 失败 / 0 失败 |

## selfupdate：不稳定（flaky）

连续两次 `go test ./internal/selfupdate -count=1 -vet=off`：

```
run 1: FAIL TestSkillSyncChecksumsAndPackageValidation
       FAIL TestStartupSyncPinsSkillToRunningCLI
run 2: ok
```

单独跑 `TestFetchSkillTree_TraversalGuard` 也通过，全量跑偶发失败。
错误形态是 `rename ...: Access is denied`，属 Windows 文件系统竞争/句柄未释放，
**需要单独定位**，不适合用 skip 掩盖。

### 本轮已修的两个真实缺陷

| 缺陷 | 影响 | 修法 |
|---|---|---|
| `local.go` 用 `filepath.Clean` 校验 tar 条目名 | Windows 上把 `references/test.md` 变成 `references\test.md`，**所有合法条目都被判 unsafe** —— Windows 用户根本无法校验技能包 | 改用 `path.Clean` / `path.IsAbs`（tar 名字是 POSIX 语义） |
| `cli_test.go` 断言可执行位 | Windows 没有执行位，普通文件 mode 是 `-rw-rw-rw-`，断言恒失败 | 该断言只在非 Windows 生效（`.exe` 与 mode 无关） |

## CI 策略

`.github/workflows/validate-go.yml`：

- **阻断**：`TestGate*`（daemon）与 `TestStatus|TestSetup|TestCard|TestAcceptance`（app）
- **只报告**：`go test ./...` 与 `go vet ./...`（`|| true`）

app 与 daemon 已全绿，可把阻断范围扩大到这两个包；selfupdate 保持报告，
因为它是 flaky 而非稳定失败。

## 历史修复记录

| 轮次 | 修复内容 |
|---|---|
| 21 | 能力/交付物的过期断言改为断言规则 |
| 22 | ProjectDrawings 7 个：换行破坏哈希、旧 metadata id、Windows symlink 与错误文本 |
| 23 | app 剩余 6 个：`stripArtifactNesting` 的 Windows 根路径、probe 缺当前技能名、环境 skip |
| 24 | daemon 2 个：时钟精度导致的误取消 |
| 25 | selfupdate 2 个：tar 条目的 POSIX 路径语义、可执行位断言 |

## 待办

1. 定位 selfupdate 的 Windows 文件系统竞争（哪个测试留下未关闭的句柄或目录）。
2. 稳定后把 `validate-go.yml` 的阻断范围扩大到 app + daemon + selfupdate。
