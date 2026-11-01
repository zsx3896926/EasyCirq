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

## 偶发：test_offline_mcp_uses_the_module_that_exists

**观察（2026-11-01，加了 MCP acceptance 工具之后）**：

| 运行 | 结果 |
|---|---|
| `pytest tests`（全量，串行） | ❌ 1 failed（就是这一个），4866 passed |
| 该用例单独跑 | ✅ 通过 |
| 该文件单独跑 ×3 | ✅ 7 passed / 7 / 7 |

**判断**：与套件顺序或模块缓存有关，不是本次改动引入的逻辑错误——
`easycirq_acceptance` 只往 `TOOLS` 里加了一项，没有改 `easycirq_mcp` 的模块解析。

**不做的处理**：没有抓到失败时的断言细节就改代码，等于把红灯弄灭。
留着，等它再出一次并带出具体断言，或者单独安排一轮用 `-p no:randomly`
与固定顺序复现。

**影响**：CI 偶发红灯，重跑即可。与已有的
`test_failed_upgrade_leaves_previous_version_intact` 属于同一类。

## 我自己的失误：把失败细节扔掉了

第一次看到 `test_offline_mcp_uses_the_module_that_exists` 失败时，我是这样跑的：

```powershell
python -m pytest tests -q 2>&1 | Select-Object -Last 3
```

**`-q` 加 `Select-Object -Last 3` 只留下了汇总行，断言细节全被丢掉。**
于是手上只有「有一个测试失败了」，没有「它断言了什么、实际值是多少」，
只能记录成 flaky，无法修。

正确做法：

```powershell
python -m pytest tests -q 2>&1 | Tee-Object -FilePath reports/pytest-full-<date>.log
```

**先存盘，再截取。** 失败的完整输出留得住，下一轮才有东西可查。

已按这个方式重跑，日志在 `reports/pytest-full-20261101.log`（6.1 KB，
4867 passed）。这个文件不入库（`reports/` 只跟踪少量历史报告）。

### 复现尝试（已做，未复现）

| 尝试 | 结果 |
|---|---|
| 该用例单独跑 | 通过 |
| 该文件单独跑 ×4 | 4 次全过（7 passed each） |
| 该文件所在目录全跑 | 127 passed |
| 先跑 MCP 相关两个套件再跑它 | 33 passed |
| 全量 ×2（14:26、15:03） | 4862 / 4867 passed，0 失败 |
| 全量 ×1（15:14，带日志） | 4867 passed |

**结论：一次性偶发，未能复现。** 不改代码——没有断言细节就改，等于把红灯弄灭。
下次再出现时，日志里会有可查的证据。

## 真缺陷（已复现）：失败的任务有时不留 `result.json`

**这是产品缺口，不是测试问题。**

### 症状

```
FAILED tests/task_launcher_tests/test_bound_integration.py::
       BoundGateTests::test_claude_profile_without_supervisor_report_fails_the_task
  FileNotFoundError: ...\state\tasks\task-bound-gate-001\result.json
```

任务以 `returncode == 1` 结束（测试第一步就通过了），但
**`result.json` 根本不存在**，于是没法读到失败原因。

### 复现率

跑了 16 次 `pytest tests/task_launcher_tests/test_bound_integration.py`：

| 结果 | 次数 |
|---|---|
| 通过 | 14 |
| **失败** | **2**（约 12%，不是必现） |

完整日志：`reports/repro-result-json.log`（`reports/*` 不入库）。

### 为什么这是缺陷而不是测试太严

测试期望的是**正确行为**：

```python
self.assertEqual(completed.returncode, 1, ...)
workspace = state_dir / "tasks" / task_id
result = read_json(workspace / "result.json")     # <- 这里炸
self.assertEqual(result["status"], "failed", result)
self.assertEqual(result["agent"], "claude-code")
```

任务失败时应当**留下一份说明**（status / agent / bound 细节），
否则调用方只拿到一个退出码——正是「缺证据」的反面。

而且这和之前几次是同一类：**报告成功/失败与真正落盘不一致**。

### 尚未做的

没改代码。原因：还没定位到"哪条失败路径提前返回、跳过了写 result.json"。
下一轮要读 `task_launcher` 的失败分支，找出没有写出结果的路径。

（这一轮先把复现率和日志固定下来——**没有这一步，下一轮又会从零开始猜**。）

### 第二次尝试：改法改变了失败形态，已回滚

我在 `_run_task` 里包了一层：

```python
try:
    status = self._apply_bound_gate(task, status)
except Exception as exc:
    task.gate_error = ...
    status = TASK_FAILED
try:
    self._finalize(...)
except Exception as exc:
    # 兜底写一个最小 result.json
```

**结果更糟：**

| 版本 | 16 次里的失败 | 失败形态 |
|---|---|---|
| 原始 | 2 | `result.json` 不存在（exit 1） |
| 我的修改 | **4** | **`returncode == 2`**（不是 1） |

失败形态从「没有结果文件」变成「退出码不对」，说明我的代码**自己引入了一条新的
异常路径**。检查过：`Task` 没有 `__slots__`、`workspace` 是 `Path`，
理论上 `task.gate_error = ...` 和 `workspace.mkdir()` 都不会炸——
**但观察到的事实是行为变了，而我没找到原因。**

所以按规矩**回滚**（`git checkout -- task_launcher/tasks.py`），
回滚后跑 8 次是 1 次失败，与原始基线一致。

**教训**：给"偶发缺陷"打补丁时，如果补丁改变了失败形态而我说不清为什么，
那不是在修，是在叠一个新的不确定性。回滚比留着强。

### 下一轮该做的

不带任何改动，先在这个用例上反复跑到失败，**把 `stderr[-2000:]` 打出来**
（测试断言里已经带了这段，只是被 `-q` 截掉了）。现在的日志
`reports/repro-result-json2.log` 里只有断言行，没有 stderr 内容——
因为 `assertEqual` 的 message 只在失败时拼进断言文本，而 `-q` 的输出被 Tail 截断。

正确做法：`pytest ... -x --tb=long` 并且**不截断**，直接看完整 traceback。

### 第三次：找到原因的一半，并让它下次能自己说出来

**用 `--tb=long` 不截断地抓到断言原文：**

```
AssertionError: 2 != 1 :
```

冒号后面**是空的**——`completed.stderr[-2000:]` 取不到任何东西。

顺着这个查 `cmd_run`（`task_launcher/cli.py`）：

```python
except LauncherError as exc:
    _print_json(exc.to_payload())      # <- 打到 stdout
    return EXIT_PROTOCOL_ERROR         # <- 2
```

**LauncherError 的 payload 只写 stdout，stderr 是空的。**
所以测试（以及任何只读 stderr 的调用方）看到的就是"退出码 2 + 一句空话"。

偶发的不是"任务失败"（那本来就该 exit 1），而是**有时抛了 LauncherError**，
于是退出码变成 2、结果文件不写、stderr 空。

### 独立复现：40 次全过

写了 `tools/repro_bound_gate.py`，把测试的调用原样搬出来跑 40 次：
**0 次失败**。所以触发条件在 pytest 进程里，不在这个场景本身。
不再追——没有稳定复现条件就改代码，就是第二次试图制造新的不确定性。

### 已经做的改动（安全、只增加信息）

`except LauncherError` 里加一行到 stderr：

```python
code = getattr(exc, "code", type(exc).__name__)
message = getattr(exc, "message", str(exc))
print(f"task_launcher run: {code}: {message}", file=sys.stderr)
```

**不改任何行为**，只是让失败在两路输出上都能被看见。

验证（故意发一个非法请求）：

```
{"error": {"code": "UNKNOWN_FIELD", ...}}                      <- stdout
task_launcher run: UNKNOWN_FIELD: unknown field(s): bogus      <- stderr（新增）
exit=2
```

**下一次它再偶发时，断言消息里就会带着真正的错误码**，不用再从零查。

### 第四次：找到并修好了 —— 是一个竞态

**40 次连跑 0 失败**（修前 2/16 ≈ 12%）。根因是顺序，不是玄学：

```python
task.finished_at = iso_now()
task.set_status(status)      # <- 这里任务变成 terminal
task.kill_info = ...
self._finalize(...)          # <- 结果文件在这之后才写
```

而 CLI 侧的 `_terminal_result` 是这样等的：

```python
while ...:
    task = manager.get_task(task_id)
    if task.terminal:              # <- 看到 terminal 就返回
        return manager.result(task_id)   # <- 此时文件可能还没落盘
```

**任务被标记为终态，与结果文件落盘之间，有一个窗口。**
调用方（测试、脚本）在进程退出后立刻读文件，就会撞上这个窗口。

这也解释了为什么两种失败形态都出现过：
- 撞上窗口 → `result.json` 不存在（exit 1）
- 撞上另一条路径 → `LauncherError`（exit 2，payload 只在 stdout）

### 修法：CLI 侧补一次幂等写入

进程退出前，手里已经有完全相同的 `result` 对象；如果文件不在，就把它写下去：

```python
workspace = info.get("task_dir") or info.get("workspace") or manager.get_task(...).workspace
result_path = workspace / "result.json"
if not result_path.is_file():
    manager._write_json(result_path, result)
```

幂等：worker 赢了竞态就是 no-op。异常不再静默吞掉，而是打到 stderr。

### 为什么第一次修失败了

第一版用 `manager.get_task(info["task_id"]).workspace`，外面套了 `except Exception: pass`。
**`get_task` 对已回收的任务会抛，于是兜底自己被吞掉、什么都没写**——
看起来加了防护，实际一次都没执行。

第二版改成优先用 `info` 里已有的路径，并把异常打到 stderr。
**静默的 except 是这次绕远路的直接原因。**

### 验证

| 检查 | 结果 |
|---|---|
| `test_bound_integration.py` ×20（第一批） | **0 失败** |
| 同上 ×20（第二批） | **0 失败** |
| `tests/task_launcher_tests` 全量 | **127 passed, 2 skipped** |

修复前基线：16 次 2 次失败。

## 检查脚本自身的两个缺陷（2026-11-01 修）

`tools/run_all_checks.ps1` 第一次全量跑时报告：

```
FAILED (2):
  pytest (exit 1)  -> ...\pytest.log
  check_published (exit 1)
```

**读日志才发现 pytest 那份只有 3.9 KB、停在 73%、没有汇总行**——
它不是失败，是**被杀掉了**。单独跑同一条：4875 passed。

### 缺陷 1：多包了一层 `pwsh -Command`

第一版把每条检查交给嵌套 pwsh 执行：

```powershell
& pwsh -NoProfile -Command $Command 2>&1 | Tee-Object ...
```

多一层进程就多一个没人监控的生命周期，pytest 跑到 73% 被杀，而脚本只知道
"退出码非零"。现在直接在当前进程里跑 scriptblock，pytest 跑完是 458s、正常汇总。

### 缺陷 2：把"没跑完"当成"失败"

这两个是不同的结论，混在一起会让人去修没问题的代码。现在每条检查带一个
`-Expect` 标记（pytest 要 `\d+ (passed|failed)`，go test 要 `^(ok|FAIL)`），
日志里没有这个标记就判 **INCOMPLETE**，并且输出里写明：

> INCOMPLETE 表示它没跑完（被杀或超时），不是代码失败——先看日志末尾停在哪一步。

### 验证

| 运行 | 结果 |
|---|---|
| 只跑四个审计 + 技能自检 | 全部 `ok` |
| 只跑 pytest（进程内） | `ok`，458.7s，4875 passed |

## 同一类缺陷在两个语言里各修了一次（2026-11-01）

`test_skill_update.py` 有两个用例偶发失败：

```
FAILED ...UpdaterTests::test_downgrade_blocked
FAILED ...UpdaterTests::test_install_update_rollback
PermissionError: [WinError 5] 拒绝访问:
  ...\.easycirq-stage-69exym3u -> ...\home\.agents\skills\easycirq
```

**这和 163 轮在 Go 里修的是同一件事**：Windows 上目录改名时，只要还有任何东西
持有那个目录的句柄（索引器、杀毒、刚关掉的进程），rename 就返回 access denied。

| 位置 | 语言 | 当时的处置 |
|---|---|---|
| `runtime/internal/app/cmd_pcb_layout_plan.go` | Go | 163 轮加了 `renameWithRetry` |
| `easycirq/scripts/skill_update.py` | Python | **一直没加**，直到这次 |

### 修法：同一思路，照着 Go 那份写

只对 `PermissionError` 和 WinError 5 或 32（access denied / sharing violation）
重试（10 次，20ms×n），其余错误立刻抛出。`install()` 里四处目录改名全部改用它。

### 验证

| 检查 | 结果 |
|---|---|
| `tests/test_skill_update.py` ×12 | **0 失败** |
| `pytest tests` 全量 | **4875 passed, 5 skipped** |

### 教训

**修一个缺陷时，要问一句「同一类问题在别处还有没有」。**

上次修完 Go 那边就收工了，因为当时只盯着眼前那个失败。
Python 这边一直带着同样的毛病，直到它自己撞上来——
而它撞上来的样子，恰好是"偶发测试"。
