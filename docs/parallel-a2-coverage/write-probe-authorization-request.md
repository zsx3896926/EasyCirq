# 写探针授权申请（W04 / W05 / W09-save）

- 日期：2026-10-28
- 申请人：A2-COVERAGE 任务（AI 会话，分支 `spike/a2-eda-coverage` / PR #75）
- 目的：把覆盖矩阵里 W04（原理图写）、W05（PCB 写）、W09（保存→关闭→重开→回读）
  从 `blocked (authorization)` 变为 `covered`，从而解除 Step 3（退役 PR）的门禁。
- 当前状态：`decision-provisional`，仅缺这三格；其余 8 个工作流已有真实回执。

## 授权后会发生什么（精确范围）

| 项 | 内容 |
| --- | --- |
| 工程 | **仅** `%TEMP%` 下的**一次性副本**：脚本把只读源工程复制到 `<project_root>\run-<时间戳>\`，所有写操作只作用于该副本 |
| 源工程 | 只读；脚本前后对源文件做 sha256，写入回执证明源未被修改 |
| 用户窗口 | 不激活、不刷新、不关闭；只驱动脚本自己 `open --headless` 的 `origin:"cli"` 会话，结束 `session close --destroy` |
| W04 写 | 在副本原理图放置 1 个系统库器件（`0402`）、1 条导线 `A2PROBE_NET`、1 个网络标签、1 个电源网络标识 `A2PROBE_VCC`，调用 `save`，回读确认 |
| W05 写 | 在副本上 `importChanges`（原理图→PCB），移动 1 个已有 PCB 器件 +50/+50（原始单位），`save`，回读确认 |
| W09 | 关闭会话→重开副本→回读：网络标识/导线/器件仍在，PCB 器件位置与保存前一致；工程文件哈希变化作为持久化证据 |
| 生成证据 | `docs/evidence/a2-coverage-2026-10-28/write-probe/`（命令、退出码、回执、前后哈希、会话快照） |
| 成功标记 | `write-probe-passed.json`（只有全部检查通过才写；Step 3 门禁读取它） |
| 不做 | 不写用户工程、不装/卸扩展、不联网（除 GitHub 推送已在 PR 流程中）、不发布、不合并 |
| 清理 | 临时副本保留供复核，评审后删除 `%TEMP%\a2-write-probe-20261028\` 整个目录即可 |

## 需要你给出的授权（二选一）

**方式 A：直接回复**“授权 W04/W05/W09 写探针”即可（本会话内会记录授权人与时间）。

**方式 B：写授权文件**（脚本强制校验；路径与内容如下），然后运行：

```powershell
$Auth = "$A2\docs\evidence\a2-coverage-2026-10-28\write-probe\authorization.json"
New-Item -ItemType Directory -Force -Path (Split-Path $Auth) | Out-Null
@'
{
  "schema": "zhigou.a2-coverage.write-authorization/v1",
  "granted_by": "jlc",
  "granted_at": "2026-10-28T12:40:00+08:00",
  "scope": ["W04", "W05", "W09"],
  "fixture_source": "C:/Users/jlc/AppData/Local/Temp/a2-spike-20261028-1050/fixture/a2spike-quickstart.eprj2",
  "project_root": "C:/Users/jlc/AppData/Local/Temp/a2-write-probe-20261028",
  "expires_at": "2026-10-29T00:00:00+08:00",
  "notes": "one-time disposable-project write probe; no user project/window"
}
'@ | Set-Content -Encoding utf8 $Auth

python $A2\spike\a2-coverage\probe_writes.py `
  --authorization $Auth `
  --fixture "C:\Users\jlc\AppData\Local\Temp\a2-spike-20261028-1050\fixture\a2spike-quickstart.eprj2"
```

## 门禁与回滚

- 授权文件缺 `granted_by`、scope 不含三项、`project_root` 不在系统临时目录、源不在临时目录、
  已过期 → 脚本直接退出 2，不启动 EDA。
- 探针失败（退出 4）不会写成功标记，覆盖矩阵维持 `blocked`；证据保留供排查。
- 成功后才允许执行 Step 3（`chore/retire-a-runtime`，1,147 个删除），并按 `decision.md`
  重新生成矩阵、更新 PR #75。

## 风险说明（如实）

- 写入只发生在 `%TEMP%` 副本；最坏情况是副本损坏，删除目录即可，不影响任何用户工程。
- `importChanges` 会按原理图重建该副本 PCB；这是预期行为，仅影响一次性副本。
- 仍需人工确认：临时副本是否保留、何时删除。
