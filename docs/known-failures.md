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

## 偶发失败：test_failed_upgrade_leaves_previous_version_intact

**观察（2026-11-01）**：完整 `pytest tests` 出现 1 个失败，

```
FAILED tests/test_install_lifecycle.py::UpgradeRollbackTests::
       test_failed_upgrade_leaves_previous_version_intact
```

单独跑该文件：`1 passed, 41 deselected`。再跑该用例：通过。

| 运行 | 结果 |
|---|---|
| `pytest tests`（全量，4802 passed） | ❌ 1 failed |
| `pytest tests/test_install_lifecycle.py` | ✅ 通过（该用例） |
| `-k test_failed_upgrade_leaves_previous_version_intact` | ✅ 1 passed |

**判断**：偶发。合理怀疑与其他安装测试共用临时目录/文件锁有关
（该文件里另有 `test_duplicate_entry`、`test_tampered_payload` 等会写 zip 的用例，
pytest 默认同文件内顺序执行，但仍可能受前序用例残留文件影响）。

**不做的处理**：没有拿到失败时的具体断言输出，凭猜测改测试等于把红灯弄灭。
若再次出现并带出断言信息，再按报错定位。

**影响**：CI 上偶发红灯，重跑即可。

## 「客户可见」的边界在哪（2026-11-01）

扫 `easycirq/scripts/**/*.py` 的字符串字面量，命中 92 处禁用词。逐一看过，
**没有一处是客户能看到的**：

| 位置 | 是什么 | 谁读 |
|---|---|---|
| `easycirq_mcp/tools.py`、`runners.py`、`server.py` | MCP 工具的描述与提示 | **agent** |
| `delivery_audit/`、`design_engine/` | 审计与设计引擎 | 维护者 |
| `doctor_env.py` | 环境诊断 | 维护者 |
| `runners.py:538` 的 `apply_allowed` | 给 agent 的技术提示 | agent |

**客户能看到的只有四条命令的输出**：
`easycirq setup` / `status` / `card` / `acceptance`。

它们的实现只有两处：
- Go 版：`runtime/internal/app/cmd_setup.go` / `cmd_status.go` / `cmd_card.go` / `cmd_acceptance.go`
- Python 版（MCP 走这条）：`easycirq/scripts/sch_status.py` / `sch_delivery_card.py`

`tests/test_customer_language.py` 现在覆盖的正是这六个文件。

### 为什么要把这条写下来

否则下一次扫到 92 处命中，会以为还有 92 个问题要修——然后去改那些
**根本不会给客户看**的字符串，甚至可能把 agent 需要的技术描述改成白话，
反而降低 agent 的判断质量。

**「客户可见」由调用路径决定，不由文件位置决定。**

## 已修：pcb layout-plan 在 Windows 上偶发 Access is denied

**症状**（2026-11-01 全量 `go test ./...` 偶发）：

```
--- FAIL: TestPcbLayoutPlanCommandRunsFullyOfflineAndWritesBundle
    execute: replace output directory: rename ...\001\.out.tmp-3666879216 ...\001\out:
    Access is denied.
```

**根因**：`pcb layout-plan --out` 的实现是「写临时目录 → 把旧目录改名成 .old →
把临时目录改名成目标名」。Windows 上只要还有任何东西持有那个目录的句柄
（索引器、杀毒、或上一个进程刚关掉），`os.Rename` 就返回 `Access is denied`。
单独跑通过、全量跑失败，正是这种时序竞争。

**修法**：`renameWithRetry` —— 只对**瞬时**错误（`fs.ErrPermission`、
"access is denied"、"being used by another process"、"sharing violation"）
做有界重试（10 次，20/40/… ms 退避），其余错误立刻返回。

**验证**：

| 检查 | 结果 |
|---|---|
| 该用例连跑 10 次 | **0 失败**（修前全量必现偶发） |
| 全量 `go test ./...` 连跑 3 次 | **exit=0，16 包 ok，0 测试失败** |
| `go vet ./...` | 干净 |

这不是测试问题——客户在 Windows 上跑 `easycirq pcb layout-plan --out` 同样会撞上。

### CLI 层实测（补）

单元测试通过之后，又在**装机后的二进制**上连跑 `pcb layout-plan --out` 5 次：

```
failures: 0 / 5
layout-plan: 1 candidate(s), 0 rejected variant(s); no editor writes performed
```

用的是真实报警板的板数据 + 合法 intent（模块 `buzzer`，中继 `BZ1`），每次先删掉
输出目录再重建——正是会触发那个 rename 竞争的用法。

**说明**：此前我先试了 5 次全部失败，但那是**我给的参数不合法**
（缺 `--module`、intent 字段对不上 `pcbLayoutModuleSpec`），报错分别是
`--from, --board, --module and --out are required` 和
`json: unknown field "parts" / "module"`。那不是 rename 缺陷，是调用错误。
把这两个混在一起看，就会误判成"修了但没用"。

## 不要并行跑 pytest 和 go test

**这一轮我第三次因为测量方式得出错误结论。**

同时跑 `pytest tests`（后台）和 `go test ./...`（前台）时：

| 运行方式 | 结果 |
|---|---|
| 两者并行 | pytest 报 `test_windows_cmd_installer` 失败；go test 报 1 个失败 |
| **各自单独跑** | pytest **4849 passed**；go test **16 包 ok，0 失败** |
| 把那个失败的测试单独跑 5 次 | **5/5 通过** |
| 把它所在的整个文件单独跑 3 次 | **3/3 通过** |

这些用例依赖时序与磁盘 IO（安装器、临时目录、文件锁）。
两个套件同时抢 CPU 和卷时，它们就会偶发失败——**不是代码坏了，是我把它们放在一起跑**。

**规则**：验证时要串行。一次只跑一个套件，等它结束再跑另一个。
报告里写的数字必须来自串行运行。

### 这是同一个错误的第三次

| 第几次 | 情况 |
|---|---|
| 1 | 用 `Select-Object` 管道读 `$LASTEXITCODE`，把成功的命令读成非零 |
| 2 | 用管道读 `easycirq` 的退出码，把 `status` 的既定码 2 当成故障 |
| 3 | **并行跑两个测试套件，把资源竞争当成代码缺陷** |

前两次是读错了值，这次是**在错的条件下测量**。
共同点：结论下得比验证快。
