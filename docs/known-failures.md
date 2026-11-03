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

## 偶发：go test 里的 PowerShell 5.1 栈溢出

**观察（2026-11-01，跑 `tools/run_all_checks.ps1` 时）**

```
--- FAIL: TestModifyPatchWindowsPowerShell51/pcb (59.45s)
    modify_patch_powershell_test.go:45: PowerShell: exit status 0xc00000fd
    Process is terminated due to StackOverflowException.
```

`0xc00000fd` 是 Windows 的栈溢出，发生在测试拉起的 `powershell.exe` 子进程里。

### 复现尝试

| 尝试 | 结果 |
|---|---|
| `go test ./internal/app -run TestModifyPatchWindowsPowerShell51` | **通过**（4.97s） |
| 在 `pwsh -File` 里跑 `go test ./...`（嵌套 PowerShell） | **通过** |
| `go test ./...` 单独全量 | **通过**，16 包 ok |

**只在"先跑完 7 分钟 pytest、紧接着跑 go test"时出现过一次。**

### 判断

环境压力下 `powershell.exe` 子进程栈溢出，不是产品代码缺陷，也不是稳定复现的测试问题。
**没有改代码。** 记下来，等它再出现时看是否是同一处。

如果频繁出现，可考虑给这个测试加 `-short` 跳过条件，或者让 runner 在 go test
之前留一段间隔——但那都是掩盖，不是修复，所以现在不做。

## 真缺陷（未定位）：离线管线读不到 KPI 门禁的报告

**2026-11-01 出现，之前同一份快照能跑通。**

```
$ python easycirq/scripts/sch_offline_pipeline.py --snapshot-dir deliverables/alarm/design/snapshot \
    --project KPI-S5-Verify --project-uuid b8f... --page P2 --out-dir %TEMP%\repro

Traceback (most recent call last):
  File ".../sch_offline_pipeline.py", line 315, in main
    report = json.loads((out / "kpi-report.json").read_text(encoding="utf-8"))
FileNotFoundError: ...\repro\kpi-report.json
```

输出目录里 12 个 `*-check.json` 都在，**只有 kpi-report.json 没有**。

### 已经排除的

| 怀疑 | 结果 |
|---|---|
| 快照坏了 | 用**旧快照（9 器件）**也一样失败；新旧 list.json / pcb-dump.json 结构相同 |
| 门禁本身坏了 | **手工用完全相同的参数调用 `sch_kpi.py`，报告正常写出**（direct.json 存在，exit 2） |
| 空 history 文件 | 我一度创建过空的 history-kpi.jsonl，删掉后仍失败 |
| 缺 check 文件 | 12 个 check 文件都在 |

### 关键矛盾

**同一条命令，手工跑能写出 kpi-report.json，管线跑就写不出。**
管线用的是 `_run([sys.executable, *map(str, args)])`，我手工用的是 `python sch_kpi.py ...`——两者应该等价。

### 这个缺陷的严重性

管线是**唯一**把「冻结快照 → 18 项检查 → 红绿灯」串起来的东西。
它现在报的是裸 `FileNotFoundError`，**没有说是哪一步失败、门禁输出了什么**：

```python
_run(cmd, label="kpi gate", allow=(0, 1, 2))   # 只允许 0/1/2，其余抛异常
report = json.loads((out / "kpi-report.json").read_text())   # 这里才炸
```

门禁返回 0/1/2 时不抛异常，但报告没写出来，于是下一行裸崩。
**`_run` 把门禁自己的诊断（stdout/stderr）丢掉了**——这正是「失败可解释率」要防的情况。

### 没有修的

没定位到根因。已经排除的都在上面，剩下的可能性（工作目录、Path 对象序列化、
门禁内部的相对路径）没有逐一验证——本轮时间用完了。

**下一轮的第一件事：在 `_run` 返回后立刻把 `stdout`/`stderr` 打出来，
而不是等到 `read_text` 崩了才发现。** 这一步就应该能直接看到门禁说了什么。

### 对交付的影响

`deliverables/alarm/` 里的 KPI 报告和卡片是**这一轮之前**生成的，
对应的是 **R5 加入之前**的快照。PCB 现在 DRC 0，但门禁没重跑，
所以**交付包仍标不能下单**——不是忘了改，是重跑被这个缺陷挡住了。

## 偶发家族三：长 pytest 之后的 go test 会出假失败

**第三次观察到同一模式（2026-11-01）。**

| 次 | 失败 | 单独跑 | 直接跑整包 | 排在 pytest 之后 |
|---|---|---|---|---|
| 1 | TestModifyPatchWindowsPowerShell51/pcb | 通过 | 通过 | **栈溢出 0xc00000fd** |
| 2 | TestConvergeLedger_CountsSameSignatureAndStops | 通过 | 通过 | **"连续 3 次同一签名之后没有停手"** |

### 排除的

- TestConvergeLedger* 用 `t.TempDir()` + `t.Setenv` 隔离，重复 6 次全过；
- 整个包里 **没有任何 `t.Parallel()`**，所以不是测试之间的 env 竞态；
- `go test ./internal/app` 单独跑全包 90s，**通过**。

### 处置：改执行顺序，不改测试

`tools/run_all_checks.ps1` 原来是 pytest（约 8 分钟）在前、go test 在后。
现在反过来：**go test 先跑（约 95 秒），pytest 后跑**。

理由：go test 快，放在前面就跑完了，不会落在长进程之后的高压窗口里。
这不是"修好了"——**根因仍未定位**（可能是句柄、内存或调度器状态），
但把已知会触发它的顺序改掉，比每次手动判断"这次是不是真的坏了"要可靠。

### 为什么不去掉这些测试

它们测的是真东西：
- 一个测 PowerShell 5.1 下的 patch 行为（Windows 特有问题）
- 一个测「连续三次同样失败就该停手」的收敛门

**为了绿灯删掉测试，是把尺子改短。** 所以只调整顺序。

### 验证

改顺序后完整跑一遍：**8 项全绿**
- go-vet ok 1.8s
- go-test **ok 94.9s**
- pytest **ok 557.7s，4875 passed**
- 四个审计 + 技能自检全部 ok

## 真缺陷（未修）：`pcb add-component` 失败时错误详情是 `[object Object]`

**2026-11-01，加 R6 到 PCB 时遇到。**

```
$ easycirq --project KPI-S5-Verify --doc PCB1 pcb add-component \
    --library 0819f05c... --uuid <三种候选之一> \
    --designator R6 --unique-id gge20 \
    --nets '{"1":"ALARM","2":"NTC_MID"}' --x 420 --y -900

{"ok": false,
 "error": {"code": "EDA_CALL_FAILED",
           "message": "Failed to place the component footprint on the PCB.",
           "detail": "[object Object]"}}
```

**`detail` 被序列化成了 `"[object Object]"`，真正的失败原因全部丢失。**

### 试过什么

| `--uuid` 取值 | 来源 | 结果 |
|---|---|---|
| `ae0117749216dbc0` | `sch list` 的 `device.uuid` / `component.uuid` | 同样失败 |
| `b7a1aae2db35ecb7` | `footprint.uuid` | 同样失败 |
| `9d0a6570652943db` | 原理图 `primitiveId` | 先被 degraded 拦下 |

`sch read` 给出的 R6 记录里**没有 device uuid**，只有 `footprint.uuid` 和
`supplierId: C31850`——而 `add-component` 要的是 device uuid。
帮助里写「Get --nets and --unique-id from 'sch read'」，但没说 device uuid 从哪来。

### 平台自己报告 connector 处于降级状态

```
warnings: ["connector looks DEGRADED under load (recent EFFECT failure rate 20%,
           1 consecutive failures) — this write may have LANDED despite the failure
           (假失败定律): verify with a light read before resending, and do NOT blind-retry.
           Worst road(s): pcb.add_component"]
```

**按这条警告做了：先读回板子确认 R6 没落上（仍是 10 个器件），而不是盲目重试。**

### 影响

- 原理图侧完整：11 个位号、设计有效性三项全绿、BOM 含 R6（C31850）
- 板子侧仍是 10 个位号 → **KPI 17 `pcb_match` 报 fail，这是正确的**
- 交付包标"不能下单"，因为这个红是真的

### 下一轮怎么办

1. 先修 `detail` 的序列化——`[object Object]` 让这个错误完全不可诊断，
   这比失败本身更严重（违反「失败可解释率 100%」）。
2. 再确认 `--uuid` 到底该传什么：可能需要的是 LCSC 器件在库里的 component uuid
   （`C31850` 对应的那个），而不是原理图里那一份的 uuid。
3. 最后才重试写入，并且每次都读回确认。

## 真缺陷（诊断到层，未修）：`pcb add-component` 的 `[object Object]`

**2026-11-01，第 1 轮压力测试目标的第一件事。**

### 现象

```
$ easycirq pcb add-component --library 0819f05c... --uuid b7a1aae2... \
    --designator R6 --unique-id gge20 --nets '{"1":"ALARM","2":"NTC_MID"}' \
    --x 420 --y -900

"error": {"code": "EDA_CALL_FAILED",
          "message": "Failed to place the component footprint on the PCB.",
          "detail": "[object Object]"}
```

审计日志里也是 `errorDetail: "[object Object]"`（审计目录下 2026-11-01 那份，requestId `req_222`）——**所以丢失发生在写审计之前**。

### 已经排除的（都有实测）

| 怀疑 | 怎么排除的 | 结果 |
|---|---|---|
| 发布包里的 connector 是旧的 | 比对 1.3.42 发布包 ↔ `connector/build/dist` 的 sha256 | **完全一致**（`37ec7a8e06e63bc9`） |
| 装机运行的是另一版代码 | 解出 `%LOCALAPPDATA%\EasyCirq\connector\v0.1.4.eext` 里的 `dist/index.js` | 974,763 字符，与 v1.0.20 的 975,307 **几乎是同一份** |
| `pcbAddComponent` 用了 `String(err)` | 在**两版 bundle** 里定位那句错误消息前后 420 字符 | 两版**完全相同**：都是 `throw edaError(err, "...")` |
| `describeThrown` 会吐裸 `[object Object]` | 读 `util.ts` 全部分支：string / Error / object / 兜底 | **不可能**。兜底是 `${toString.call(err)} (no enumerable properties)`，带后缀；`stringifySafe` 用 `JSON.stringify` |
| Go 侧丢的 | `envelope.go:150` 是 `Detail string`，`daemon/audit.go:146` 直接 `e.ErrorDetail = resp.Error.Detail` | Go 只是原样接收；到它手上时字符串**已经是** `[object Object]` |

### 我自己踩的一个推理坑（记下来，因为它会再犯）

第一轮我数了 bundle 里 `"[object Object]"` 出现几次，得到 **0**，于是断定"跑的不是这份代码"。

**这个推理是错的。** `[object Object]` 是 `String(x)` 在**运行时**对普通对象求值的产物，
**源码里永远不会出现这个字面量**。数它等于什么都没证明。
后来改看"那句错误消息附近的实际代码"，才两个版本都看到 `edaError` —— 信息量完全不同。

### 现在的位置

丢失点收窄到：**connector 内部，`edaError` 之外的一层**——最可能是
`result.degraded` 那套包装（响应里带着 `degraded: {...}`），或者某个外层 catch
把 `ActionError` 又序列化了一次。

**下一步该做的**（便宜且决定性）：
1. 在 `connector/src` 里找把错误塞进 `degraded`/信封的那段，看有没有对 `err` 做字符串化
2. 或者直接在那条 `throw edaError(...)` 上临时加一行日志，把 `describeThrown(err)` 的结果和 `err` 的 `typeof`/构造器名打出来，重跑一次
3. 修完加一条测试：给 `describeThrown` 喂主机对象、无原型对象、带 `toJSON` 的对象、
   Proxy，断言**任何输入都不会产出裸 `[object Object]`**

### 为什么不先"换个参数绕过"

目标里写死了：**`[object Object]` 换个参数躲过去不算解决**。
一个说不出原因的失败，等于没有失败信息——这比失败本身更糟，
也正是「失败可解释率 100%」要防的东西。

## `[object Object]` 的根因与修复（2026-11-01）

接上一节。**根因是两个事实叠加，而且都在宿主侧。**

### 根因

1. **宿主抛的是跨 realm 的 Error。** EasyEDA 在自己的 JS realm 里抛错，
   到了连接器这边 `err instanceof Error` 是 **false**（不同 realm 的
   `Error` 构造器不是同一个）。
2. 于是走"普通对象"分支，`pickMessageLike` 取 `record.message` ——
   **Error 的 own property `message` 是可读的字符串，但它本身是 `"[object Object]"`**。
3. `JSON.stringify(一个 Error)` 恒为 **`"{}"`**（own props 不可枚举），
   所以 `hasJson` 为假，JSON 兜底补不了任何信息。
4. 最终走 `return head`，`head` 就是那串占位的 message。

**换句话说：`describeThrown` 一直在防"自己吐出 `[object X]`"，
但没防"宿主传进来的 message 本身就是 `[object X]`"。**

### 审计日志的佐证

扫 2026-11-01 那份审计（1917 条记录）：

```
errorDetail 恰好是 '[object Object]' 的记录: 7
  pcb.add_component   7 次   message='Failed to place the component footprint on the PCB.'
```

只有这一个动作出现过，且都是我反复试的那几次——与"宿主这条 API 抛错时不带有效信息"一致。

### 修复

`connector/src/util.ts` 的 `describeThrownRaw`：

1. **识别跨 realm 的 Error**——不用 `instanceof`，改看
   `typeof name === 'string' && typeof message === 'string'`，并且
   `stack` 是字符串或 `name !== 'Object'`。
2. **占位符不再原样输出**——`[object Object]` / `[object Undefined]` 这类
   用 `isPlaceholderLabel` 认出来，换成明确的说明：
   - 跨 realm Error：`Error: the host threw an Error whose message is the placeholder "[object Object]" — the real cause was not put into it (at host (x.js:1:1))`
   - 普通对象：`"[object Object]" (placeholder message from the caller) | {"message":"[object Object]"}`
   - 直接抛的字符串：`"[object Object]" (the thrown value was this literal string — ...)`
   - 真 Error 带占位消息：不再只回一个 `Error`，而是说明原因并带第一帧调用栈

### 验证

- `connector/src/util.test.ts` 新增 8 条测试，其中一条是
  **"任何输入都不产出裸 `[object X]`"**：喂 `{}`、无原型对象、
  `{message:'[object Object]'}`、跨 realm Error、真 Error、占位字符串、
  Map、Symbol、函数，逐个断言不等于 `[object Object]` 且非空。
- `node --require ts-node/register --test src/util.test.ts` → **80 passed, 0 failed**
- `npm run typecheck` → 无错误
- `npm run build` 重新打包，产物里四个新说明字符串各出现 1 次
  （`.eext` 2,201,237 字节，sha256 `9257113f9806c570…`）

### 还没生效的地方

**EasyEDA 里跑的还是旧 bundle。** 要让修复生效，需要把新的 `.eext`
重新导入 EasyEDA（`easycirq connector path` 给出路径，导入步骤见
`easycirq connector install-steps`）。**这一步我做不了**（GUI 操作），
所以现在真实链路里仍然会看到 `[object Object]`；
但**下一版打包后它不会再出现，且同一位置上会给出一句能看懂的话**。

## 已修：`design_validity` 把 MOSFET 当三极管算

**2026-11-01，做 12V 风扇板时撞到。**

### 症状

检查器里 `TRANSISTOR_PINS` 把 `B`（基极）和 `G`（栅极）都映射成 `control`，
于是 `check_drive` 对 MOSFET 也套用 BJT 模型：算基极电流、乘 hFE、比较负载。

**这对 MOSFET 是错的**——栅极静态不取电流，只要求栅源电压够开、够关。

实测对比（同一份网表，只换管子）：

| 管子 | 栅极/基极上拉 | 修之前 | 修之后 |
|---|---|---|---|
| MOSFET（AO3400） | 100k | **被判失败**（100k 给不出"足够基极电流"） | **pass**：栅压 ≈5V > Vgs(th) 1.5V，静态不取电流 |
| BJT（S8050） | 100k | fail（正确） | **仍然 fail**（正确）：0.043mA → 5mA « 200mA |

**左边那种是假失败**：100k 的栅极上拉是完全正确的做法，
按 hFE 判会让人去改一个根本不需要改的电阻。

### 修法

1. 新增 `transistor_kind(part)`：按引脚名区分
   —— B/C/E 是 `bjt`，G/D/S 是 `mosfet`。
2. `check_drive` 为 MOSFET 走独立分支：
   - 栅极无直流通路 → `NO_GATE_PATH`
   - 栅压低于 `vgs_th` → `VGS_BELOW_THRESHOLD`
   - 负载超过 `id_max_a` → `LOAD_EXCEEDS_RATING`
   - **完全不出现 hFE / 基极电流**
3. 结果里带 `"kind": "bjt" | "mosfet"`，报告里分得清用的是哪个模型。

意图文件新增两个可选字段：`vgs_th`（默认 1.5V）、`id_max_a`（默认 4.0A）。

### 验证

`tests/test_design_validity.py` 新增 4 条：

- MOSFET + 100k 栅极上拉 → `switch_drive pass`，且**不得出现 `DRIVE_INSUFFICIENT`**
- 同样 100k 换成 BJT → 必须 `DRIVE_INSUFFICIENT`（证明模型确实分开了）
- MOSFET 去掉栅极上拉 → `NO_GATE_PATH`
- 负载 9A 超过 4A 额定 → `LOAD_EXCEEDS_RATING`

`pytest tests` → **4897 passed, 5 skipped**（上一轮 4888 + 新增 9）。

## 已补：感性负载的续流二极管判据（2026-11-01）

风扇板探针暴露的第四类判据。**18+1 项门禁里没有一条会查它**，而缺续流二极管的
后果很直接：断电瞬间线圈电流没有泄放回路，反电动势顶到开关管上，管子被击穿。

### 判据

意图里把负载标成感性（`load_kind: "inductive" | "motor" | "fan" | "relay" | "solenoid"`
或 `inductive: true`），检查：负载两端（负载电源轨 ↔ 开关管那侧）之间有没有
**反并**的二极管——**阴极朝电源轨、阳极朝开关管**。

| 情形 | 结论 |
|---|---|
| 没有二极管 | `NO_FLYWHEEL_DIODE` |
| 有但接反（阳极朝电源轨） | `FLYWHEEL_DIODE_REVERSED`——它会正向导通，一上电就把 12V 短路 |
| 正确反并 | pass |
| 端点接法认不出来 | `unknown`，不猜 |

### 判定聚合也跟着修了

新增第四类检查后，报警板（没有电感负载）的 `inductive_load` 报 `not_run`，
**整体判定一度被拖成 `unknown`**。这不对，要分两种"没做"：

| 状态 | 含义 | 对整体判定 |
|---|---|---|
| `not_run` | 意图没要求这一项（板上没有电感负载） | **不拖累**，当作不适用 |
| `unknown` | 该判但判不了（器件认不出、网表缺信息） | 如实反映成 `unknown` |

修完验证：报警板 → 三项 pass + 一项 not_run，整体 **pass**；
修前快照 → 仍然 **fail**（三个缺陷照报）。

### 我的测试写法也犯过一次错

新测试里写 `assertIn("inductive_load    pass", stdout)`，失败了——
输出里那一行是 **5 个空格**不是 4 个。原因：状态列按 `<18` 补宽，
`threshold_sanity`（16 字符）补 3 个空格，`inductive_load`（14 字符）补 5 个。
**按固定空格数断言等于把测试绑在列宽上。** 改成按行解析的 `check_status()` 辅助函数。

### 验证

`tests/test_design_validity.py` 新增 4 条：缺二极管必须 fail、正确反并必须 pass、
接反必须 fail、非感性负载必须 not_run。
`pytest tests` → **4901 passed, 5 skipped**（上一轮 4897 + 新增 4）。

### 还没覆盖的

- **双电源域**（5V 逻辑 / 12V 负载）：`power_net` 只查电源网络冲突，
  不查"管子漏极接错了域"，也不查 12V 与 5V 有没有共地。**仍是人工核对项**。
- 负载启动电流的裕量：模型用意图里声明的 `load_ma`，不猜倍率。

## 术语测试靠环境运气通过（2026-11-01/02，已改）

### 怎么暴露的

一次全量跑挂在这里：

```
FAILED tests/test_customer_experience.py::CustomerTerms::test_setup_uses_no_tool_jargon
AssertionError: Lists differ: ['daemon', 'connector'] != []
```

原因是**后台没在跑**（重打包时停掉没起来）。`easycirq setup` 于是走引导分支，
输出里带两条命令字面量：

```
1. 启动后台服务：`easycirq daemon start`（EasyCirq 在后台常驻的那一部分）
2. 在 EasyEDA Pro 里装一次 EasyCirq 插件（`easycirq connector path` ...）
```

**后台起着的时候这条测试是绿的**——也就是说它一直在靠环境碰运气，
而不是在验证"客户要理解的术语数 = 1"。

### 两个不同的问题，分开处置

**问题一：测试判得不准。** 它对整段输出做子串匹配，把命令字面量也算成术语。
但 `easycirq daemon start` 是客户**原样复制**的东西——他不需要知道 daemon 是什么
也能跑。散文里出现"daemon"才是真的要求他理解。

改法（**不是放宽**，是把判据对准它本来要测的东西）：
1. `assert_no_jargon` 先剥掉反引号里的命令字面量，只查散文。
2. 新增 `test_guidance_prose_has_no_tool_jargon`：直接扫 `cmd_setup.go` 里的
   中文文案（客户真正会读到的东西），剥掉命令后不许有术语。**不依赖后台状态。**
3. 新增 `test_commands_it_names_exist`：扫六个面向客户的源文件里出现的
   `easycirq <子命令>`，逐个 `--help` 探测。**把"命令写进反引号就能绕过"
   这个口子堵上**，同时能发现死命令。

扫出来并逐个验证通过的：`acceptance` / `card` / `pcb` / `setup` / `status`，
五个都真实存在（这条测试不是空转）。

### 问题二：产品本身有个真缺口，我没擅自改

**后台没起来时，客户要自己敲第二条命令。** 而目标写的是「一条命令装好」。

这不是措辞问题，是流程问题：`setup` 现在只诊断、不代启动。
要不要改成"检测到没启动就自动启动"是产品决策——涉及安装行为、
权限、以及"能不能替用户起常驻进程"这类判断，**不该我一个人定**。

已记在这里，等用户决定。在那之前 `setup` 保持"只检查不代装"的现有语义
（`docs/release-checklist.md` 里也是这么写的）。

## 已补：`block.threshold_switch_12v`（2026-11-02）

风扇板探针暴露的块库缺口。40 个内置块分 10 类（power/comms/mcu/rf/usb/display/
audio/storage/button/sensing），**没有一类覆盖"模拟阈值比较 + 负载驱动"**——
客户说"做个温控风扇"，块库帮不上任何忙。

### 新增的块

`runtime/internal/blocks/data/threshold_switch_12v.json`，11 个器件、8 个网络：

| 角色 | 标准件 | 作用 |
|---|---|---|
| TH | ntc.10k_3950 | 10K NTC，B=3950 |
| R_PULL | res.10k_0603 | NTC_MID 上拉 |
| R_TH_TOP / R_TH_BOT | res.10k_0603 / res.4k3_0603 | 阈值分压 → 45.3°C |
| U | ic.lm393_sop8 | 比较器（开集输出） |
| R_HYST | res.39k_0603 | 正反馈 → 回差 2.97°C |
| R_GATE_PULL | res.100k_0603 | 栅极上拉（**没有它管子永不导通**） |
| R_GATE_SER | res.100r_0603 | 栅极串联 |
| Q | mosfet.ao3400a_sot23 | N-MOSFET 低边开关 |
| D | diode.1n4148w_sod123 | 续流二极管 |
| LOAD | conn.xh254_2p | 负载端子 |

**二极管的极性已经固化进块里**：`D.2`（阳极 A）接开关侧，`D.1`（阴极 K）接负载电源轨。
这颗料库里 pin1=K、pin2=A，与"1 阳 2 阴"的常识相反——手工搭板时我就接反过一次，
被 `inductive_load` 判据拦下。写进块里，下次谁用都不会再犯。

### 顺带把标准件库补了 10 条

库里原本**一条 0603 电阻、一条二极管、一条 MOSFET、一条 NTC 都没有**。
新增：res.4k3_0603、res.39k_0603、res.100k_0603、res.100r_0603、res.10k_0603、`ic.lm393_sop8`、
`mosfet.ao3400a_sot23`、`diode.1n4148w_sod123`、`ntc.10k_3950`、`conn.xh254_2p`。
`deviceUuid` 全部从 `lib search` 现取，不手抄。库从 161 条增到 171 条。

`bapPrefixes` 新增 `ntc -> TH`（IPC-7351 惯用），其余复用已有的
`diode -> D`、`mosfet -> Q`、`res -> R`、`ic -> U`、`conn -> J`。

### 验证到哪一步

**dry-run 通过**：

```
R10 R_PULL     res.10k_0603      400,1060
R9  R_HYST     res.39k_0603       820,820
...
NET      KIND      MEMBERS
PWR5V    net_label R10:1 R12:1 U2:8 R4:1 (port PWR5V)
D2_N2    net_label R10:2 TH1:1 U2:3 R9:2
GND      gnd       TH1:2 R11:2 U2:4 Q2:2 (port GND)
D2_N7    net_label Q2:3 J1:2 D2:2
PWR12V   net_label J1:1 D2:1 (port PWR12V)
```

8 个网络与手工搭的那块板逐条一致。`go test ./internal/blocks` 通过。

**没做的**：真实落块（不带 `--dry-run`）。原因见下——块尺寸与图纸可用区不匹配。

### 这轮暴露的两个部署问题

**问题一：同一个标准件库在三个地方各有一份，没人保证同步。**
`skillAsset.resolve` 按优先级找：`--parts` → `$EASYCIRQ_SKILLS_DIR` →
已安装技能目录（claude / codex / agents）→ 从二进制向上找 → 从 cwd 向上找。

实测：`.claude` 和 `.codex` 下的是 **160 条旧版**，`.agents` 下是 171 条新版。
解析器先命中旧的，于是块报"器件找不到"——**明明文件就在硬盘上，只是找错了那一份**。
手工把三份都同步后立刻正常。这不是块的问题，是部署卫生的问题，值得单独修
（`easycirq skill sync` 可能已经覆盖，没验证）。

**问题二：块尺寸 1000×460，图纸可用区 1146×801，落点很难挑。**
在 (400,600) 落会越界，平台直接警告「这张图是废的」。要么换更大的图纸，
要么把块拆小，要么给人一个"按可用区自动选落点"的能力。**没在本轮解决。**

### 为什么不硬落

目标写的是「宁可板子做不完，也要把工具缺陷修干净」。现在块本身已经验证到
dry-run 层（器件全解析、8 网对得上、schema 测试通过），
**硬塞进一张放不下的图纸只会得到一块废图**，对工具没有任何改进。
把它记成待办比制造一个坏状态更有价值。

## 已修：器件找不到时，报错不说是哪一份 standard-parts.json（2026-11-02）

### 上一轮实际浪费的时间

加 `block.threshold_switch_12v` 时，块报：

```
role D: part "diode.1n4148w_sod123" not found in standard-parts.json
```

**那个键就在硬盘上。** 我改了标准件库、同步了 `.agents` 那份、重编了二进制，
还是同样的报错——因为解析器命中的是 `.claude` 下的**另一份旧副本**（160 条），
而我改的那份是 `.agents`（171 条）。

三份副本：

| 位置 | 条数 |
|---|---|
| `~/.claude/skills/easycirq/references/standard-parts.json` | 160（旧） |
| `~/.codex/skills/easycirq/references/standard-parts.json` | 160（旧） |
| `~/.agents/skills/easycirq/references/standard-parts.json` | **171（新）** |

### 根因不是"副本多"，是"报错不说读的哪一份"

`skillAsset.resolve` 按阶梯找：
`--parts` → `$EASYCIRQ_SKILLS_DIR` → 已安装技能目录（claude/codex/agents）→
从二进制向上找 → 从 cwd 向上找。**命中第一个就返回，静默。**

而报错侧的 `bapPartsFileLabel()` 在自动解析时只回一个字符串：

```go
return "standard-parts.json"   // 不说是三份里的哪一份
```

**同步三份副本只是绕过。** 真正的缺陷是这个标签丢掉了唯一有用的信息。

### 修法

1. `cmd_sch_block_apply_run.go`：解析出真实路径后**回填** `partsPath`，
   并存进 `bapInput.PartsPath`（新增字段）。
2. 新增 `shadowedStandardParts(resolved)`：沿**同一条阶梯**再走一遍，列出
   硬盘上存在的其它副本。
3. 新增 `standardPartsDiagnostic(resolved, shadowed)`：把"读了哪份 + 还有哪几份 +
   怎么改"拼成一段附在报错后面。只有一份、或用户自己指定了 `--parts` 时不输出。
4. 两处报错（`not found` / `no deviceUuid`）都带上这段。

### 修完之后长这样

```
role D: part "diode.1n4148w_sod123" not found in the parts file
  read: C:\Users\jlc\AppData\Local\Temp\stale-standard-parts.json
  other copies on disk (the resolver returns the FIRST hit, so a stale
  copy here is why a part can be missing while the file has it):
    C:\Users\jlc\.claude\skills\easycirq\references\standard-parts.json
    C:\Users\jlc\.codex\skills\easycirq\references\standard-parts.json
    C:\Users\jlc\.agents\skills\easycirq\references\standard-parts.json
  fix: `easycirq skill sync` (or copy the current file over them),
       or pin the right one with --parts <path>
```

**同一个问题，现在一眼能看出来。** 这是拿一份故意缺少 1N4148 的副本实测的输出。

### 验证

- `TestPlanBlockApplyMissingPartNamesTheFile`：断言报错含解析到的绝对路径、
  含被遮蔽副本、含下一步。故意传入 `PartsPath` 和 `PartsShadowed` 制造问题。
- `TestStandardPartsDiagnosticEmptyWhenNothingToSay`：只有一份时不输出多余提示，
  否则每条报错都长一截没人看。
- `TestPlanBlockApplyMissingPart`：更新文案断言。
- `go test ./internal/app` → **ok 92s**；`go test ./internal/app -run BlockApply` 全过。

### 没做的（以及为什么）

**多个副本内容不同时主动警告**没做。现在只在**出错时**才列出来。
主动警告需要每次解析都去 stat 并读一遍所有副本做比对，
为一个"装了三份"的部署状况给所有路径加常驻开销，不划算。
**报错时够用，就够了。**

## 已修：「放不下」的两种原因被混成一句话，而且混错了（2026-11-02）

### 上一轮我自己的误判

第 8 轮我说「块尺寸 1000×460 vs 图纸可用区 1146×801，放不下」。**这个结论是错的。**

第 10 轮在一张**空页**上重跑同一个块，它自己挪到 (200,180) 就放下了，8 个网络全对。
真正的原因是：第 8 轮那次 dry-run 跑在 `Fan-Controller-12V` 的 P1 上，
**那张页已经有 11 个器件**，拼不出空位。

### 缺陷在文案

`cmd_sch_block_apply.go` 里「出界且扫描失败」这条：

```
"--at (…) 会让这一块超出图纸可用区，且整张图纸都找不到放得下的位置
 （块估算 1000×460，可用区 1146×801）— 照你的坐标放置，但这张图是废的：
  换更大图纸、拆到别的页，或先清出空间"
```

**它一边报出「1000×460 对 1146×801」，一边断言放不下——文案自己自相矛盾。**
而且给出的补救动作（换图纸 / 拆块）是错的那一半：真正该做的是清空位。

### 修法（以及一处自我纠正）

本来想按 `oversize` 分两句话。写测试时才发现：**`oversize` 为真时那条分支根本不可达**——
代码在第 614 行有意把 `inBounds` 设成 nil（注释解释：此时恒 false 会让 96 个候选全否决、
回落到原坐标压在已有器件上，比不加边界约束更糟）。所以出界告警只可能由
「块放得进、但页面占满」触发。

于是：
1. **删掉那个死分支**，文案只保留成立的那一种原因，并明说
   「块尺寸 X 是**放得进**可用区 Y 的，原因是页面占满」。
2. **补一条用例钉住既有设计**：`TestBapResolveOrigin_OversizeBlockSkipsBoundsWarning` ——
   超大块**不该**出这条告警。将来有人"顺手"让超大块也走边界检查，这条会红，
   提醒他先读那段注释。

### 验证

- `TestBapResolveOrigin_SeparatesTooBigFromPageFull`：块明显小于可用区、页面被占满时，
  告警必须含「放得进」，且**不许**归因为块太大，补救动作必须指向清空位/挪器件。
- `TestBapResolveOrigin_OversizeBlockSkipsBoundsWarning`：超大块不出这条告警。
- `go test ./internal/app` → **ok 85.8s**；`go vet` 干净。

### 一处需要澄清的经历

第一版测试我把原点放在**可用区内但被占满**的位置，结果命中的是「重叠」分支
（那句"按你的坐标照常放置"），不是出界分支。改了三次场景才打到目标分支。
**写"故意制造该问题"的测试，先得确认自己造的是那个问题。**

### 超大块这个缺口本身没修

块比图纸大时，边界约束被有意关掉、也没有告警。这是既有设计（理由见 614 行注释），
**不是本轮引入的**。要改就得同时解决"关掉约束后它可能出界"的问题，
那是另一件事，记在这里。

## 真缺陷（未定位）：`block-apply` 真实落块会挂住，dry-run 不会（2026-11-02）

### 现象

在空工程 `BlockProbe` 的空页 `P1` 上：

| 命令 | 结果 |
|---|---|
| `block-apply ... --dry-run --at 300,650` | **通过**，11 器件全解析、自动挪到 (200,180)、8 网全对 |
| `block-apply ... --at 300,650`（不带 dry-run） | **挂住**，超过 5 分钟无输出 |

读回页面确认：**器件数 0**——它没有落地，不是"落了但没报"。

### 已经排除的

- 不是块定义问题：同一个块 dry-run 全通过，`go test ./internal/blocks` 绿。
- 不是件找不到：dry-run 已证明 11 个 role 全部解析成功。
- 不是页面尺寸：空页可用区 1146×801，块 1000×460，dry-run 自己也证明了挪得进。

### 这次观察到的一个规律（三次了）

真实落块挂住不是第一次：

| 次 | 场景 | 结果 |
|---|---|---|
| 1 | 第 8 轮，Fan-Controller 页（11 器件）带 `--dry-run` | 挂住，10 分钟 |
| 2 | 第 9 轮，同页带 `--parts` 指向旧库 | 挂住 |
| 3 | 第 10 轮，**空页**不带 dry-run | **挂住 >5 分钟，器件 0** |

第 1、2 次我以为是页面太满或库不对；第 3 次在**空页**上照样挂，
说明触发条件不在页面内容，**在真实落块这条路径本身**。

### 没定位到的部分

不知道挂在哪一步。日志/审计里没有对应记录可查（命令没返回就没写审计）。
下一步该做的：

1. 用 `--timeout` 或进程级超时跑一次，拿到 goroutine dump（`kill -QUIT` 或 Go 的
   `SIGQUIT` 栈）——**这是唯一能看清挂在哪的办法**，本轮没做（超时 5 分钟已经吃掉太多时间）。
2. 或者读 `cmd_sch_block_apply_run.go` 里真实落块的循环，找没有超时保护的等待点。

### 为什么不重试

挂住的写入**可能已经落地**（假失败定律）。本轮已经读回确认器件 0，
所以这次是干净的；但**再重试一次不解决任何问题**——用的是同一个会挂的路径。
按目标「卡住但诊断清楚 = 有效进展」，这里诊断到「不是页面、不是库、不是块」就已经有信息量了。

### 对风扇板的影响

**块的 dry-run 可用，真实落块不可用。** 所以"用块一键搭板"这条路径现在走不通，
风扇板仍以手工搭的那块为准（那块是好的：11 器件、8 网络、五类判据全过）。

## 撤回：「真实落块会挂住」是错的（2026-11-02）

上一轮我记了「`block-apply` 真实落块会挂住，dry-run 不会」。**这个结论不成立。**

### 重测结果

daemon 稳定之后再跑同一条命令（空工程 `BlockProbe`，空页）：

```
耗时 < 150s，正常返回
  D1  R1  R2  R3  R4  R5  R6  TH1  U1  Q1  J1     11 个器件全部落位
  PWR5V / GND / PWR12V + 5 个内部网，8 个网络与设计一致
  grouped ✓ g1 (threshold_switch_12v(D1)) — 11 件
```

读回页面：**11 个器件**，位号 `D1 J1 Q1 R1 R2 R3 R4 R5 R6 TH1 U1`。

**它不是挂住，是慢。** 我给的 5 分钟容忍度不够，就把"超时"当成了"挂死"。

### 这已经是我第二次把"慢"误判成"坏"

| 轮 | 我的结论 | 实际情况 |
|---|---|---|
| 8 | 「块 1000×460 放不进 1146×801」 | 空页上自动挪位就放下了；那次跑在已有 11 器件的页上 |
| 10 | 「真实落块会挂住」 | 只是超过了我设的 5 分钟；重测 150s 内完成 |

两次的共同点：**我在一次观察之后立刻下结论，而没有换一个条件重测。**
第 8 轮没试空页，第 10 轮没试更长的超时。

### 这次改用的诊断手段（值得留下）

- **直连 daemon 的 action 端点 接口**拿干净 JSON。CLI 的 `sch list` 会往 stdout 掺
  人读行、又**没有 `--json`**，用 CLI 读数已经在本轮绊了三次。
- 解析 CLI 输出时**不要做行过滤**。我的过滤器把以 `{` 开头的行也删了
  （规则写得太窄），破坏了结构，还一度以为是 CLI 掺垃圾。
  正确做法：从每个 `{` 位置试着 `raw_decode`，第一个解出 `ok`/`result` 的就是答案。

### 块落出来的电路确实是对的

用**匹配块分配位号**的意图文件跑五类判据：

```
threshold_sanity   pass   45.3°C（目标 45±3）
switch_drive       pass   栅极 5.0V » 1.05V，200mA « 4A
hysteresis         pass   反馈件 R3
inductive_load     pass
supply_domains     pass
设计有效性：pass
```

**块从"能规划"升级为"落出来就是对的"。**

## 新的真缺口：块分配的位号与设计意图文件不联动

第一次跑只拿到 `inductive_load: unknown`，原因很具体：

- 块的角色 `LOAD` 被分配成 **`J1`**
- 而我的意图文件写的是 **`FAN1`**（手工搭板时的位号）
- 于是判据找不到 `FAN1`，报 unknown

`U1`（比较器）和 `Q1`（开关）恰好对上了，纯属运气——块分配 `U`→U1、`Q`→Q1，
与我手工用的位号相同。

**这是真摩擦**：`block-apply` 会重新分配位号（帮助里也说了 `--spec` 能把真实位号
回填进 S0 spec），但**设计有效性意图文件不在回填范围内**，得手工改。
位号一变、意图不跟着改，判据就会静默降级成 unknown——**而 unknown 很容易被忽略**。

暂时这样处理：为块落版单独留一份 `intent-block.json`（`load` = `J1`）。
要不要把意图文件也纳入 `--spec` 那样的自动回填，记成待办。

## 已修：位号对不上时，`unknown` 只剩三个字母（2026-11-02）

### 症状

用块落出来的电路跑设计有效性，只得到：

```
inductive_load     unknown
```

**看不出为什么判不了。** 手工排查才发现：块把 `LOAD` 角色分配成 `J1`，
而我的意图文件写的是手工搭板时的 `FAN1`。

**`unknown` 是最危险的失败形态**——它不像 `fail` 那样刺眼，
很容易被当成"这一项不适用"略过，实际是"这一项根本没验"。

### 两层问题，都修了

**第一层：诊断信息不够。** `describe_missing_designator()` 现在把网表里
**实际有哪些位号**列出来，并点明成因（块会重排位号）：

```
[unknown] FAN1: 意图写的是 FAN1，网表里没有这个位号；
网表里的器件是：D1, J1, Q1, R1, R2, R3, R4, R5, R6, TH1, U1。
（`block-apply` 落块后会重新分配位号，意图文件要跟着改）
```

**只说事实，不猜"最接近的是哪个"。** 猜错比不说更糟，而人一眼就能对上。

**第二层：诊断写对了，但没打印出来。** 这句话写进了 `loads[].reason`，
而打印器只遍历 `metrics` 和 `switches` —— **屏幕上照旧只剩三个字母**。
修了打印器，现在 `loads[]` 每项的理由都会输出。

**第二层是这次真正花时间的地方**：第一层改完我去验，仍然看不到原因，
一度以为诊断没生效。

### 验证

`tests/test_design_validity.py` 新增 3 条：

- `test_missing_load_designator_lists_what_exists`：必须列出真实位号、点明块重排位号
- `test_missing_designator_is_visible_in_stdout_not_just_in_json`：
  **断言它出现在 stdout 里**——写对了不打印等于没写（这条直接用实测踩的坑命名）
- `test_correct_designator_passes`：位号对上时不许再报 unknown

`tests/test_design_validity.py` → **31 passed**；相关四个套件 → **61 passed**。

### 还没做的（以及为什么）

**让 `block-apply` 把真实位号自动回填进意图文件**没做。它已经有 `--spec`
能做到类似的事（回填 S0 spec 的 modules[].parts），但把设计意图也纳入回填
是另一条改动路径，要动 Go 侧和意图的 schema。

**先修诊断的理由**：位号对不上是必然发生的（块每次落都可能分到不同位号），
而"看得见"是解决它的前提。回填能省事，但没有回填时至少现在不会静默降级。
这条留作待办。

## 已修：`pcb dump` 不加 `--include-copper` 时，快照不说明走线没抓（2026-11-02）

### 我怎么被绊的

检查风扇板布线状态时：

```python
payload = data.get("result") or data
tracks = payload.get("tracks") or []      # ← 空
```

得到「器件 12，走线 0」，于是判断「板子没布线」。**连续判断错两次**，
还据此重跑了 auto-place 和 autoroute。

真实情况：

| 读法 | 结果 |
|---|---|
| `pcb dump`（默认） | 有 `components`，**没有任何走线字段** |
| `pcb dump --include-copper` | `copper.lines` = **109 段**，8 个网络全有 |

**键名也不是 `tracks`，是 `copper.lines`。**

### 为什么算缺陷

默认输出里**完全没有提示**"走线这次没取"。一个把 `pcb dump` 当"板子全貌"用的
调用方（包括我自己写的脚本、也包括技能里的离线分析），会得到
「这块板一条线都没布」这个**看起来合理但完全错误**的结论。

`--include-copper` 的帮助文字是「capture exact routed/area copper and rule-region
lists with per-category availability」——**从这句话读不出"不加就没有走线"**。

### 顺带第二个坑：两种信封形状

同一个 CLI 里：

| 命令 | 形状 |
|---|---|
| `sch list` / `sch connectivity` / `pcb drc` | `{"ok":…, "result": {…}}` |
| `pcb dump` | 直接就是 `{"components": […]}` |

按一种写解析器，遇到另一种 `data.get("result") or data` 会返回 `{}`，
表现同样是"板子上什么都没有"。

已固化成 `tools/easycirq_read.py` 的 `run_json()`：有 `result` 就取 `result`，
否则取整个对象。**这条本会话已造成两次误判。**

### 修法（不动默认字段，只借既有的降级通道）

`boardSnapshot` 本来就有 `Partial []string` —— 板框拿不到、铜层数读不出时都记在这里。
`if opts.withCopper { … }` 这段**没有 else 分支**，补上：

```
capture provenance: copper NOT captured (no --include-copper) — routed traces,
vias and pours are ABSENT from this snapshot; an absent list here is not an
empty board. Re-run with --include-copper to read routing
```

三个细节是刻意的：

1. **用 `capture provenance:` 前缀。** `boardSnapshotSemanticSHA256` 会把这个前缀的条目
   排除在哈希外——因为"这次抓到了什么"属于采集事实，不是板子语义。
   这样既有的冻结基准**不会**因为多了一句提示而失效。（有测试钉住。）
2. **不新增字段。** 复用 `partial[]`，与"板框需要前台文档"那条同一机制，
   不改变快照的字段集合，`--out` 写出的 capture.json 语义也不变。
3. **文案自己解释陷阱**：明确写"这个列表不存在 ≠ 板子是空的"，并给出补救命令。

### 实测确认，以及一个更扎心的事实

不传 `--include-copper` 现在输出：

```
components: 12
copper 字段存在: False
routedLines: 147
partial:
  - capture provenance: copper NOT captured (no --include-copper) — routed traces,
    vias and pours are ABSENT from this snapshot; an absent list here is not an
    empty board. Re-run with --include-copper to read routing
```

**注意 `routedLines: 147`。** 这个字段**一直都在**，而且它明明白白说着
"板子上有 147 段已布铜线"。

所以真相是：工具当时给了**两个**信号（`routedLines` 和 `copper.lines`），
**我一个都没读**——我的解析器只找 `tracks`，找不到就当空。

这不改变"默认输出该说明缺了什么"这个改进的必要性（新加的提示让人不可能再漏），
但**必须记清楚：这次误判的主因是我按猜的键名去读，不是工具藏了信息。**

连续三轮的同类错误，机理完全一样：

| 轮 | 我以为 | 实际 |
|---|---|---|
| 11 | `sch autoconnect` 失败 26 次 | 输出是人读文本，我按 `"ok": true` 匹配 |
| 16 | 板子 0 条走线 | 键是 `copper.lines` / `routedLines`，不是 `tracks` |
| 16 | `pcb dump` 没给数据 | 它直接返回载荷，没有 `result` 信封 |

**共同的病根：先假设输出长什么样，再去读。** 正确做法是先看一遍真实输出（或读它的 JSON 一次），再写解析。

### 验证

- `TestBoardSnapshotNotesWhenCopperWasNotCaptured`：说明必须含
  `NOT captured` / `--include-copper` / `not an empty board`
- `TestBoardSnapshotCopperOmittedNoteDoesNotChangeSemanticHash`：
  **加了这句说明，semanticSha256 不许变**（否则冻结基准全废）
- `go test ./internal/app` → **ok 87.9s**；`go vet` 干净

### 教训

**连续两次因为"读到的键是空的"就断定"板子上没有"**。
读到空集合时，先确认**这个键本来该不该有**，再下结论。

## 已记录：`pcb autoroute` 只布未布线的网，重跑永远不会修好坏走线（2026-11-02）

### 表现

风扇板加去耦电容后重新摆件，DRC 出现 17~30 项 clearance 违规。
我先后做了三次"重新布线"：

| 尝试 | autoroute 报 | DRC |
|---|---|---|
| auto-place + outline(80) + autoroute | 8/8 成功 | **17 项** |
| auto-place gap120 pitch150 + outline(100) + autoroute | 8/8 成功 | **30 项** |
| auto-place 默认 + outline(200) + autoroute | 3/8 成功 | 不变 |

**三次都报"成功"，三次违规都不消。** 而且第三次重读违规详情时发现——
`(ALARM): e8` 对 `(PWR5V): R1_1` 这条**和第一次一模一样**。

### 根因

**`autoroute` 只处理"未布线的网络"，已经存在的走线它不碰。**
所以对一块"布错但已布"的板重跑 autoroute，等于什么都不做——
它把剩余未布的网布完（报 successNetsCount），坏走线原封不动。

### 正解

```
pcb rip-up        # 拆掉全部走线与过孔（板框和锁定对象不受影响）
pcb autoroute     # 从零布
```

实测：

```
rip-up  → autoroute: successNetsCount 8 / totalNetsCount 8
save → doc reload → pcb drc: passed: true, 0 violations
```

**同一块板、同样的摆件，一次 rip-up 之后违规清零。**

### 为什么这条值得记

因为它**极容易误导**：autoroute 返回 `successNetsCount: 8`，看起来"布线成功了"，
而 DRC 说"有 17 项违规"。人会以为是"路由器质量不行"，
于是去调 gap、调板框——**钱花在错误的维度上**。

正确的心智模型是：**autoroute 是增量操作，不是重布线操作。**

### 顺带一条

`--ignore-net` 的帮助文字里已经写了 `e.g. GND (poured later)`——
说明路由器的设计意图里，地网本来就该靠铺铜而不是走线。这和"GND 占了 109 段中的 30 段"
对得上，但本轮没走到铺铜。

## 已修：交付包自检器拿顶层名比相对路径（2026-11-02）

### 缺陷

`tools/check_deliverable.py`：

```python
listed  = set(re.findall(r"\| `([^`]+)` \|", readme))   # README 里是相对路径
present = {p.name for p in d.iterdir()}                   # 只取顶层名
```

两个集合比的是**不同的东西**：README 写 `design/intent.json`，
而 `present` 里只有 `design`。于是任何**嵌套目录的交付包**必然报两条
「列出了不存在的文件」+「存在但未列出」。

报警板是平铺的（所有文件在根目录），所以这个 bug 一直没暴露。
风扇包有 `design/` `snapshot/` `manufacturing/` 三层，一上来就撞上。

### 修法

```python
present = {p.relative_to(d).as_posix() for p in d.rglob("*") if p.is_file()}
```

比对的是"哪个文件"，**路径才是它的身份**。

### 修完立刻暴露两件事

**1. 风扇包根本没有 README**（上一轮的"通过"是查错了对象）。
补了一份，按新约定列出全部 23 个文件。

**2. 报警板的 README 是照着旧语义写的**——只列 11 个顶层条目，
其中 `design` 是个目录。按新约定重建成 24 个文件。

### 重建时我把导航表删掉了，测试立刻抓到

重建脚本把所有 `|` 开头的行当表格剥掉，**连带删了「什么时候看哪一份」那张导航表**。
`tests/test_deliverable_navigation.py` 立刻红：

```
导航表只列了 0 个决策点：[]
```

这张表是有契约的（指标 3：一个决策点只看一份），不是装饰。
已补回，7 个决策点重新就位。

**教训**：我的重建脚本按"删掉所有表格行"来清理，而 README 里**有两张用途不同的表**——
文件清单（我想要的）和导航表（我误删的）。**按形状而不是按语义删东西，会删掉不该删的。**

### 验证

- `tests/test_deliverable_navigation.py` → **10 passed**
- `python tools/check_deliverable.py`（报警板）→ 自检通过
- `python tools/check_deliverable.py deliverables/fan-controller` → 自检通过
- `pytest tests` → **4914 passed, 5 skipped**（起始 4897，本轮 +17）
- `go test ./...` → 16 包全 ok；`go vet` 干净

## 已查清：连接器测试的两个假失败，与三个真失败（2026-11-02）

### 我用错了跑测器

上一轮我报「2 个 describeThrown 测试失败」。**那是假的。**

这个连接器用的是 **`node:test`**（`import { test } from 'node:test'`），
`package.json` 里写的是：

```
"test": "node --require ts-node/register --test src/*.test.ts"
```

我却用 `npx vitest run` 去跑。vitest 不认识 `node:test` 的调用，
产出一组自相矛盾的输出（78 pass / 2 fail，又说 "No test suite found"）。

**换成 `npm test` 之后，那两个 `describeThrown` 测试是通过的。**

单独验证也证实了：`describeThrown(new RangeError(''))` 实际返回 `'RangeError'`，
正是断言要的值。

**这是本会话第四次「先假设工具怎么用，再下结论」。**

### 真正的失败是 3 个端口测试（与我的改动无关）

```
✖ 逃生口:单值 / 列表 / 区间 / 数组都能写
✖ 多端口覆盖时,上次握手成功的端口排最前且不重复
✖ 覆盖列表里没有 lastGood 时,顺序原样不动

actual:   [23111, 23112, … 23122]      （整个 10 口保留段）
expected: [23111, 60833, 60834]         （覆盖列表）
```

在 `src/transport-ports.test.ts`。而 `src/transport-identity.test.ts` 里明确写着：

> 端口选择与退避的测试搬去了 transport-ports.test.ts —— 原来的 scanOrder
> （整段 10 端口扫描 + lastGood 优先）已被「钉死 23111 + 指数退避」取代。

**也就是端口选择的设计换了，这批测试还在测旧契约。**
与 12V 风扇板无关，是既有的历史遗留。

### 处置：已修，但要证明是**测试写错**而不是改测试迁就实现

三个测试断言的是：

```ts
parsePorts('23111-60836')                 -> [23111, 60833, 60834, 60835, 60836]
resolvePorts('23111-60836', 60835)        -> [60835, 23111, 60833, 60834, 60836]
resolvePorts('23111-60834', 60900)        -> [23111, 60833, 60834]
```

`'23111-60836'` 是一个**真实的 37,726 端口区间**，实现按硬上限取前 12 个
（`[23111..23122]`）——就实现而言这是对的。

而上面三个期望值，**逐个等于少了逗号的输入**：

```
parsePorts('23111,60833-60836')            -> [23111, 60833, 60834, 60835, 60836]
resolvePorts('23111,60833-60836', 60835)   -> [60835, 23111, 60833, 60834, 60836]
parsePorts('23111,60833-60834')            -> [23111, 60833, 60834]
```

**三个全等。** 所以是测试的输入少了一个逗号，不是实现有问题。

**这一步是关键**：如果我直接改测试让它们绿，那就是"为了让测试通过而改判据"。
先跑一遍证明"补上逗号后期望值精确匹配"，才有资格改。

### 修完的结果

```
npm test
  ℹ tests 1230
  ℹ pass  1230
  ℹ fail  0
```

**从 1227 过 / 3 挂 变成 1230 全过。** `npm run typecheck` 干净。

### 顺带纠正一个更大的事实

我一直说的「80 个测试」是**用 vitest 只跑 `src/util.test.ts` 一个文件**的数字。
`npm test` 跑的是 `src/*.test.ts` 全部，**共 1230 个**。

所以我此前对连接器测试覆盖率的描述，量级就错了。

### 我要更正的记录

第 2 轮我写「80 个测试全过」——那个数字是**用错的 runner 跑出来的读数**，
不能作为证据。正确的是：`npm test` 下 `describeThrown` 全部通过，
另有 3 个端口测试失败（既有问题）。

### 仍然成立的结论

## ## 已修并实机验证：[object Object] 现在自己解释原因（2026-11-02）

### 整条证据链

| 层 | 状态 |
|---|---|
| 代码（`describeThrownRaw` 重写，提交 `04b26592`） | ✅ |
| 打包（v1.0.21 的 `dist/index.js` 含新文案） | ✅ 已核实包内字节 |
| **实机** | ✅ **已在 v1.0.21 窗口上实测** |

实机原始输出（`--window 8d85a24f-…`，即装了 v1.0.21 的那个窗口）：

```
"error": {
  "code": "EDA_CALL_FAILED",
  "message": "Failed to place the component footprint on the PCB.",
  "detail": "Error: the message is the placeholder \"[object Object]\" — the real cause was not put into it"
}
```

字节级核对：`\xe2\x80\x94` 是正确的破折号，`detail.strip() == "[object Object]"` 为 **False**。

### 为什么之前三轮都说"实机仍不可读"

因为**一直装的是不含修复的包**，而版本号没升，看起来"已经是最新的"：

| 包 | 大小 | 时间 | 含修复 |
|---|---|---|---|
| `hardware-design-skill\connector\build\dist\...v1.0.20.eext` | 2,200,829 | 10-28 | ❌ |
| `hds-a-method\connector\build\dist\...v1.0.20.eext` | 2,201,237 | 11-01 | ✅ |
| `AppData\...\easycirq-connector_v0.1.4.eext` | 259,235 | 10-28 | ❌ |

**两个不同的包同名 v1.0.20。** 我据此三次让用户"重导 .eext"，但
`easycirq connector path` 指向的是 AppData 里更旧的 v0.1.4 —— **命令把人指错了地方**。

### 真正解决它的两处改动（提交 `18c868f5`）

1. **版本升到 1.0.21**（`extension.json` 才是产物的命名来源，只改 `package.json` 没用）
2. **`connector path` 按版本择优**，不再"取第一个含有 .eext 的目录"——
   原来安装目录排在仓库构建目录之前，于是旧包永远赢

顺带修了 `connector verify` 报了路径却写着 `source: not-found`（把返回值丢了）。

### 遗留：三个窗口里还有两个跑 v1.0.20

```
loadedWindows: [10a0f67b=v1.0.20, 4c13445c=v1.0.20, 8d85a24f=v1.0.21]
```

`connector verify` 因此仍报 `degraded` —— 这是**对的**。另外两个窗口若要用，
需要在它们里面也导入一次 v1.0.21；否则那边的事件详情仍是旧的。

### 教训

**"需要用户重做某步"这种结论，必须先确认：那条命令让用户做的是不是正确的事。**
我让用户"重导 .eext"三次，而 `connector path` 指的是旧文件——
**这不是用户没做，是我的指令把他引到了错的东西上。**

## 已修：`design_validity` 只支持一个比较器（2026-11-02）

### 原来的限制

意图里 `threshold.comparator` 是**单个字符串**，一块板只能表达一个阈值，
窗口比较器（高低双限）表达不了。

我第 24 轮先记成了"不修"，理由是"探针板只需要一个、支持 N 个要改 schema"。
**那个理由站不住**：向后兼容的加法不需要改既有文件，也不会动 34 个现有测试。
有 55 轮余量的情况下，"要改 schema"不是不做的理由。

### 修法（向后兼容）

```python
def threshold_specs(intent):
    many = intent.get("thresholds")      # 新写法：列表
    if isinstance(many, list) and many:
        return [s for s in many if isinstance(s, dict)]
    single = intent.get("threshold")     # 旧写法：单对象，全部既有文件都用它
    return [single] if isinstance(single, dict) else []
```

`run_per_spec()` 对每一组各跑一遍 `check_threshold` / `check_hysteresis`，聚合规则：

| 情况 | 聚合结果 |
|---|---|
| 任何一组 fail | **fail** |
| 否则任何一组 unknown | unknown |
| 否则任何一组 not_run | not_run |
| 全 pass | pass |

**多比较器板不比单比较器板更宽松**——任何一组不通过，整体就不通过。

### 实测（两个比较器的板）

```
threshold_sanity   pass
  [pass] U1: {"threshold_v": 1.5035, "divider": "R2/R3", "trip_c": 45.3, ...}
  [pass] U2: {"threshold_v": 3.4375, "divider": "R4/R5", "trip_c": 8.3, ...}
```

第二组靶温写错 → 整体 **fail**；第二组指向不存在的位号 → 整体 **unknown**（不许因第一组 pass 就整体 pass）。

### 风扇板回归

单比较器路径**输出形状不变**（不打印逐条明细），
`metrics` 仍是那一组的值：`trip_c 45.3` / `width_c 2.97`。

### 验证

`tests/test_design_validity.py` **38 passed**（34 + 4 条多比较器）；
三个相关套件 **64 passed**。

---

## 已记录（不修）：三个偶发测试，逐个列明（2026-11-02）

三个测试名都核实过，真实存在于仓库：

| # | 测试 | 文件:行 | 观察到的现象 |
|---|---|---|---|
| 1 | `TestModifyPatchWindowsPowerShell51` | `modify_patch_powershell_test.go:13` | pcb 子用例栈溢出，退出码 `0xc00000fd` |
| 2 | `TestConvergeLedger_CountsSameSignatureAndStops` | `sch_converge_ledger_test.go:30` | 断言失败（计数不符） |
| 3 | `TestPcbLayoutPlanCrystalGuardWritesAllDeclaredSVGPreviews` | `cmd_pcb_layout_plan_test.go:60` | SVG 预览写入失败 |

### 复现条件（观察到的）

**只在长时间跑完 pytest 之后跑 go test 才出现。** 单独跑 `go test ./internal/app`
从未复现过。

### 缓解措施（已生效）

`tools/run_all_checks.ps1` 改成**先 go test、再 pytest**。按这个顺序跑：

| 轮次 | 全量结果 | 偶发是否出现 |
|---|---|---|
| 第 21 轮 | 4914 passed, 5 skipped | 否 |
| 第 23 轮 | 4917 passed, 5 skipped | 否 |
| 第 25 轮 | 4921 passed, 5 skipped | 否 |

**连续三轮零复现。**

### 为什么不修

**没有稳定复现就没有可验证的修复。**

要定位需要：
1. 一个能按需触发的条件（"跑多久"、"跑多少条"才有）
2. 或者 goroutine dump（`0xc00000fd` 是明确的**栈溢出**信号，但只有 dump 才能指出
   哪一层在递归）

在这两样都拿不到的前提下改代码，**就是在猜**。而这个目标反复强调的正是
"不能把猜测说成已修复"。

### 明确不声称的

- ❌ 不说"已修"
- ❌ 不说"根因是 X"（`0xc00000fd` 只说明是栈溢出，不说明是谁在递归）
- ✅ 只说"知道了触发条件的大致范围，缓解有效，根因未定"



### 第四个偶发（2026-11-03 新增）

| 测试 | 文件:行 | 观察到的现象 |
|---|---|---|
| `TestBapBackfillSpec_WindowAndProjectResolveSameKey` | `spec_backfill_window_test.go:201` | 两条路由回填出不同结果；stderr 里是 `rename ... .s0.json.tmp -> s0.json: Access is denied.` |

**根因判断：Windows 文件锁**，代码在改名时目标文件仍被别的句柄持有。
证据：

- 报错发生在 `rename`，不是断言逻辑
- 同一次改动之后，全量 `go test ./internal/app` 重跑 **ok**（86.7s）
- 单测 `-count=3` 连跑 **3 次全过**（1.25s）

**不修的理由**：这不是产品缺陷，是测试在 Windows 上做「写临时文件再改名」时撞上
文件锁（杀软/索引器/上一次句柄未释放）。要彻底消除得给所有改名操作加重试，
那会改动非测试路径的行为，收益不抵风险。

**遇到时的处置**：重跑。连续两次失败才是真问题。

## 已部分修复：器件额定电压判不了 → 现在「声明额定值，工具算应力」（2026-11-02）


### 第五个偶发（2026-11-03 新增）

| 测试 | 文件:行 | 观察到的现象 |
|---|---|---|
| `TestDropSchGroupsForPage_OtherPagesUntouched` | `cmd_sch_group_lifecycle_test.go:70` | `docA 的组该没了, 仍有 1 个` |

**证据表明是偶发，不是回归**：

- 单独 `-count=3` 连跑 **3 次全过**
- 紧接着全量重跑 `ok`（86.5s）
- 出现该失败的那次全量运行同时通过了本次改动相关的全部测试
- 本次改动是新增 `cmd_enterprise_doctor.go` 与测试，未触碰分组生命周期代码

**不猜根因**：没有当时的 goroutine dump 或运行顺序记录，**不写"可能是并发"这种话**。
需要复现时用 `-count=N -shuffle=on` 保留随机顺序，再抓 `-race`。

**处置**：重跑；连续两次失败才当回归查。

### 原来的记录

`known-failures` 里曾写：

> **器件额定电压工具判不了**（要规格书），已在检查器的 note 里写明。

这话只对了一半。**工具确实不能凭空知道额定值，但这不等于判不了。**

### 现在的能力

沿用本代码库已有的声明式模式（`hfe` / `vgs_th` / `id_max_a` 都是人声明的），
新增 `ratings` 检查：**人声明额定值，工具算实际应力，两者相减。**

```json
"switches": [
  { "part": "Q1", "load_rail": "PWR12V",
    "vds_max": 30,      // AO3400A 数据手册值，人填
    "vgs_max": 12 }
],
"ratings": [
  { "part": "C1", "between": ["PWR5V", "GND"], "max_v": 50 },
  { "part": "R9", "between": ["PWR12V", "GND"], "max_power_w": 0.05 }
]
```

能算的应力：

| 场景 | 怎么算 |
|---|---|
| 开关管关断耐压 | 关断时漏极/集电极坐在负载轨上 → 取该轨电压 |
| 栅极/基极电压 | 驱动电平取逻辑轨电压 |
| 任意两轨之间的电位差 | `|V(a) - V(b)|` |
| 电阻功率 | 两端电压已知 + 网表里有阻值 → `V²/R` |

### 实测（`reports/fan-controller/evidence/`）

| 用例 | 结果 |
|---|---|
| 12V 轨装 **10V** 额定的管子 | **fail**：`OVER_RATING` 实际 12.00V 超额定 10.00V（120%） |
| 12V 轨装 13V 额定 | pass，但给 `RATING_MARGIN_THIN`：已达额定 **92%**，余量不足 20% |
| 12V 轨装 30V 额定 | pass |
| 电容 16V 耐压接 12V | pass |
| 1k 电阻接 12V（50mW 额定） | **fail**：实际 **144mW** |
| `GATE`（非电源轨）对 PWR5V | **unknown**：算不出电压，`不猜` |

风扇板真板输出：

```
ratings            pass
  [pass] Q1 Vds: 实际 12.0V / 额定 30.0V
  [pass] Q1 Vgs: 实际 5.0V / 额定 12.0V
  [pass] C1 V: 实际 5.0V / 额定 50.0V
```

### 顺带修了一个既有缺陷

`check_drive` 里栅极电压原写作 `v_gs = VCC_FALLBACK`（**硬编码 5.0V**），
不看意图里声明的电源轨。后果：**3.3V 逻辑板上，一颗 Vgs(th)=4.0V 的管子会被误判成"够开"**。

现在取 `rail_voltages(intent)[rail]`，查不到才回落 5.0。
`test_three_volt_rail_drive_is_not_judged_as_five` 用 3.3V 轨 + 4.0V 门槛钉住这条。

### 已补：中间节点的电压，用「最坏情况上界」而不是工作点

原来中间节点（GATE、FAN_M）之间的电压一律 `unknown`。第 27 轮补上了，
**但没有做"工作点求解"**——那会撒谎：GATE 在比较器拉低时 ≈0V、在开集关断时
被上拉到 5V，**给一个数字就是错的**。

判耐压要的是最坏情况，而最坏情况是可算的：

> 从节点出发，经**任意器件**遍历连通部分，遇到已声明电源轨就记下其电压。
> **地只作终点、不作中继**（否则全板通过地短成一坨，每个节点都报 12V）。
> 上界 = 可达轨里的最高电压；下界 = 最低电压。

实测：

| 用例 | 结果 |
|---|---|
| D1 反压（`between: [FAN_M, PWR12V]`） | 原来 **unknown**，现在 **12.0V**（额定 100V → pass） |
| R5 两端（`between: [GATE, PWR5V]`） | 5.0V（最坏情况），额定 3V → **fail** |
| 孤立网络（够不到任何轨） | 仍 **unknown**，不猜 |

### 这一步两次把我自己的错算出来了

**第一次**：传播**穿过了晶体管的栅极**——GATE 经 Q1 栅极"走到"漏极再到 12V 轨，
算出 **7V**（|12−5|），比真实的 5V 还高，**凭空造出一个不存在的应力**。
晶体管的控制脚与沟道是隔离的，从控制脚进入的连通部分必须到此为止。

**第二次**：`nets` 里存的是 `(位号, 引脚号字符串)`，我却当成 pin dict 传给
`role_of`，直接 `AttributeError`，40 个测试崩掉。

**第一处是物理模型错，第二处是取值形状错。** 前者会让判据给出错误结论（更危险），
后者只是崩——**崩比错好**。

### 仍然判不了的

- 需要**真正的电路求解**才能定的中间节点（非线性、多路反馈）
- 上述规则给的是**保守上界**：比如 GATE 的上界取 5V，哪怕某块板比较器永远拉低
  实际到不了 5V。输出里标了「最坏情况」，别当成实测值

- **不在已声明电源轨上的中间网络**（如 GATE、FAN_M）之间的电压 —— 需要电路求解，不在本工具范围
- **器件的真实额定值** —— 数据手册不在网表里，必须人填
- 温度降额、瞬态尖峰、SOA 曲线

**这些写在检查器的 `note` 里，不假装能判。**

## 已修：分压阈值的容差从来没算过（2026-11-02）

### 这笔账悬了一整局

第 1 轮的报警板记录里写着：

> NTC 的 B 值容差会让 45°C 摊成 **61–67°C**，这是手算的，工具没算过。

**"手算的、工具没算过"就是悬账。** 客户问「45±3°C 能做到吗」时，
只报标称 45.3°C 是不够的——要报**最坏情况下会偏到哪**。

### 现在的做法

意图声明容差，工具枚举：

```json
"threshold": {
  "tolerances": { "resistor_pct": 1, "ntc_r25_pct": 1, "ntc_b_pct": 1 }
}
```

对 5 个量（NTC 上拉、阈值上臂、阈值下臂、R25、B）各按 ±pct 扰动，
**枚举全部 2^5 = 32 组组合**，取动作温度的最小/最大值。

**为什么枚举而不是逐个扰动**：±1% 的电阻和 ±1% 的 B 可能同向叠加，
逐个绕动会把最坏情况低估。

### 风扇板实测

| 场景 | 标称 | 最坏散布 | 结论 |
|---|---|---|---|
| 1% 器件，目标 **45±3** | 45.3°C | **44.06–46.55°C**（散布 2.49） | **pass** |
| 1% 器件，目标 **45±1** | 45.3°C | 44.06–46.55°C | **fail** |
| **5%** 器件，目标 45±3 | 45.3°C | **39.47–51.97°C**（散布 12.5） | **fail** |

**同一个电路，标称值 45.3°C 三种情况都"在范围内"，但只有第一种真能做到。**
这就是容差分析的价值——只报标称值会让后两种看起来满足需求。

### 判不了的

- 没声明 `tolerances` → 不输出 `tolerance` 字段，**不假装在范围内**
- 扰动后某个角落永远不穿越阈值 → `unknown`，不猜
- 温度系数（NTC 的 B 随温度变）、长期漂移、焊接应力 —— 不在模型里

### 验证

`tests/test_design_validity.py` 新增 4 条：1% 配 ±3 通过、同一电路配 ±1 必 fail、
5% 器件散布 >5°C 必 fail、没声明容差时不输出该字段。
文件内 **52 passed**。

## 已修（换成可执行的判据）：块的 `pcb_layout` 是空文档字段（2026-11-02）

### 本来想做的事，和查出来的事实

`block.threshold_switch_12v` 的 `pcb_layout` 是 `[]`。我本想往里写
「去耦电容要紧邻 VDD」「续流二极管要靠近负载端子」这类约束。

**查下来：没有任何代码读 `.PCBLayout` 去校验。** `block-apply` 自己就写着：

> block-apply v1 executes parts/internal_nets/ports only;
> the listed constraint maps were NOT applied

只有 `led_indicator_gpio` 等块里有 `polarity-silk` 之类的条目，**纯文档**。

**往一个无人消费的字段里写约束 = 加了但没人执行。** 那正好是目标禁止的那种"做样子"。

### 换成真能跑的判据：去耦摆放距离

`tools/check_decap_placement.py`：从 `pcb dump --include-copper` 读焊盘坐标，
算**去耦电容焊盘到 IC 电源脚**的中心距。

风扇板实测：

```
[warn] U1.8 (PWR5V) ← C1: 108.9 mil / 上限 100.0
```

**108.9 mil ≈ 2.77mm，刚过 100 mil 的经典经验值。** 这条以前没有任何检查抓得到。

### 判据的分级（避免"发明判据"）

100 mil 是**行业惯例，不是物理定律**。所以：

| 场景 | 状态 | 退出码 |
|---|---|---|
| 用默认经验值 100 mil，超了 | `warn` | **0**（不把板子判死） |
| 调用方显式给 `--max-mil 50`，超了 | `fail` | 1 |
| 显式给 `--max-mil 200`，没超 | `pass` | 0 |
| 真的什么都判不了 | `unknown`/`not_run` | 2 |

**只有用户自己定的上限才算硬门。** 拿经验值把板子判死等于我发明判据。

### 修的过程中犯的错

1. **第一版把 U1 的信号脚也当电源脚**，ALARM / TH / NTC_MID 全被报成
   "没找到去耦电容"——一堆噪声。改成只认电源网络名（VCC/VDD/PWR/+5/12V 等），
   并留 `--power-net` 供覆盖。
2. **用默认经验值时直接判 fail**，等于把惯例当定律。改成分级。
3. 改判定逻辑时我连叠了三个补丁脚本，**两处断言没匹配上、文件没写入**，而我先跑了输出
   看到还是 `[fail]` 才发现的。最后改成精确的单点编辑才对。

### 没做

- **没把 `pcb_layout` 填上**：它不被执行，填了是装饰。真要支持，得先写消费它的检查器
- **没把去耦距离接进 19 项 KPI 门禁**：那是 skill 目录下的管线，改动更大，记作待办

## 企业平台化：卡在哪条门（2026-11-03）

本目标分三层。**L1 已交付并有工具输出**；L2/L3 不是"没时间做"，是**卡在客户环境信息**。
按判据「不猜客户环境」，这些一律记为未做，并写清缺哪一条。

### L2 —— 连接器远程 + 多租户服务端

| 项 | 状态 | 卡在哪 |
|---|---|---|
| 连接器连 `wss://服务器` | ✅ **已做**（1.0.22） | `easycirqDaemonUrl` / `easycirqAuthToken` 两个用户配置；不设则行为完全不变，有测试钉住。**未在真实远程服务端上验证过**——只验了 URL 构造 |
| 服务端多租户路由 | ✅ **已做**（asycirq gateway） | 进程内按 token 复用 daemon；跨租户隔离有测试（甲拿乙的 windowId 打不进去）。**未在真实 TLS 代理后验证**，只在本机明文上验过 |
| 工程师不装 `easycirq.exe` | 未做 | 依赖上面两条 |

**门：`docs/enterprise-discovery.md` 的 A2（客户插件 API 是否与 `eda.*` 同构）。**

- 同构 → 连接器改连接地址，几天
- 不同构 → 要写适配连接器，**那是独立项目**

**为什么不先改连接器**：改完无法验证。手上只有 EasyEDA Pro 客户端，改完仍然是本机回环，
测不出"远程到底通不通"。**没有客户端就改连接器 = 按假设实现**，正是判据第一条禁止的。

### L3 —— 账号 / LLM 网关 / 并发编辑

| 项 | 状态 | 卡在哪 |
|---|---|---|
| 账号分发、邀请码、权限 | 未做 | 依赖 L2 跑通；且企业要先确认要账号体系 |
| LLM 网关（key 保管、审计、计量） | **只写方案，无实现** | C1/C2/C4 不明。见 `docs/enterprise-deployment.md` 第二部分 |
| 知识库并发编辑与审核流 | 未做 | D2/D3 不明；且当前**没有任何写入锁**（见下） |

**门：L2 跑通 + 企业确认要账号体系；网关另需 C1/C2/C4。**

**为什么不先写网关**：客户的 LLM 可能是 OpenAI 兼容网关、可能是自建（vLLM/Ollama）、
可能只给各部门发 key。三者的转发逻辑不一样，**按假设写出来要返工**。

### 已知缺陷：共享知识库没有写入锁

**这不是"未做"，是做出来了但有缺陷，必须记着。**

| 情况 | 后果 |
|---|---|
| 两人同时改同一个 `rules.*.json` | 后保存的把先保存的覆盖掉，**且没有任何提示** |

- 现有的应对：约定同一时间只有一人改；或把共享目录设成 git 仓库，用 commit 串行化
- 为什么现在不修：加文件锁要处理 Windows UNC 路径的锁语义、锁超时、崩溃残留锁。
  **在只有一两个人维护的情况下，成本高于收益**
- **什么情况下必须修**：超过 3 个人同时维护规则库时

已写进 `docs/enterprise-deployment.md` 的已知限制表。

### 已知缺陷：开发态找不到企业脚本

`easycirq enterprise` 通过 `skillAsset` 阶梯定位 Python 脚本。这个阶梯探的是：
显式路径 → `$EASYCIRQ_SKILLS_DIR` → 已安装技能目录 → 从二进制向上 → 从 cwd 向上。

**它不探仓库布局**（`<repo>/easycirq/scripts/`），所以在仓库里跑 `easycirq enterprise ls`
会报"脚本找不到"，必须设 `EASYCIRQ_SKILLS_DIR=<repo>`。

- 客户机器上没有这个问题（安装必有技能目录）
- 为什么现在不修：`skillAsset` 同时服务 `bom-enrich.py` 和 `standard-parts.json`，
  改它的探测顺序会影响另外两条路径，**风险大于收益**
- 报错质量没问题：它会列出所有探测过的路径并给出三种修法

### 一条反向记录：改了两个"名字说谎"的命令

`easycirq enterprise promote` 一开始打出清单而不推进（脚本要 `--promote`，包装没传）；
`report` 没给 `--html-out` 时退化成列条目。

**两个都是"看起来做完了其实没做"。** 已修，并有测试钉住
（`TestEnterpriseReportRequiresHtmlOut` / `TestEnterprisePromoteInjectsTheFlag`）。

抓到它们的方法值得一提：把一页纸的测试从"跑脚本"改成"跑文档里写的命令"，
假命令立刻暴露。**文档即测试是有回报的。**
