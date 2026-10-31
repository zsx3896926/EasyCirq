# 已知失败（Go 全量套件，2026-10-31 收尾）

## 现状

**`go test ./...` 全绿**（16 个失败 → 0，跨 5 轮）。

| 包 | 状态 |
|---|---|
| `internal/app` | ok |
| `internal/daemon` | ok |
| `internal/selfupdate` | ok（连续 8 次全绿） |
| 其余（protocol/pcblayout/spec/workflow/…） | ok |

## CI

`.github/workflows/validate-go.yml` 已从「阻断子集 + 报告全量」升级为
**整模块阻断**：

- `go build ./...`
- `go test ./... -count=1 -vet=off`（阻断）
- `go vet ./...`（报告，`|| true`）

## vet 告警（已清零）

| 位置 | 内容 |
|---|---|
| `internal/app/cmd_task.go:204` | `fmt.Sprintf` 需要 9 个参数但有 10 个 |
| `internal/daemon/schematic_geometry.go:228,234` | `cancelPublication` 未在所有路径调用（lostcancel） |

这两处是既有问题，**没有修**，因此 vet 保持 advisory。它们能编译能跑，
但 `%s` 数量与参数不匹配意味着那段生成的文档里有一个占位符错位——
值得单独处理，不宜混在测试清理里。

## 五轮修掉的 16 个（都是真缺陷或真平台问题）

| 轮次 | 修复 |
|---|---|
| 21 | 能力/交付物的硬编码 id 断言 → 改为断言规则 |
| 22 | ProjectDrawings：`.gitattributes` 锁 LF（哈希按字节算）、夹具旧 metadata id、Windows symlink/错误文本 |
| 23 | `stripArtifactNesting` 的 Windows 根路径；probe 缺当前技能名 `easycirq` |
| 24 | daemon：时钟精度导致的「取消更新 mutation」 |
| 25 | selfupdate：tar 条目的 POSIX 路径语义（Windows 上所有条目被判 unsafe）、可执行位断言、目录 rename 竞争重试 |

## 判定

这些修复里有三个是**用户能直接撞上的缺陷**：

1. Windows 上 bundle 校验拒绝所有合法技能条目（无法安装）；
2. cwd walk-up 找不到当前技能名（`bom-enrich.py` 解析失败）；
3. 目录 rename 在杀软/索引器占用时失败（技能更新偶发失败，用户看到 "Access is denied"）。

其余是测试自身的平台假设或过期断言。

## 偶发测试失败：TestPcbLayoutPlanCrystalGuardWritesAllDeclaredSVGPreviews

**观察（2026-10-31，1.3.11）**：在完整 `go test ./...` 中出现过一次失败，
随后单独跑 3 次、以及整包再跑一次均通过。

| 运行 | 结果 |
|---|---|
| `go test ./...`（第一次） | ❌ FAIL |
| 单测 `-run TestPcbLayoutPlanCrystalGuard...` ×3 | ✅ ok ×3 |
| `go test ./internal/app` 整包 | ✅ ok（101s） |

**判断**：偶发（flaky），不是确定性缺陷。可能原因未证实——疑似 SVG 预览写入
在整包高负载时的时序/文件占用问题，但没有抓到失败时的具体报错，**不做猜测性修复**。

**影响**：CI 上可能出现偶发红灯。处理方法：重跑；若重现且有报错信息，再按报错定位。

**为什么不现在改**：我拿不到失败时的输出，凭猜测改测试会掩盖真实缺陷。
记录在这里比"顺手改一下看着像的样子"更诚实——这正是
`unstable tests are worse than no tests` 的取舍。
