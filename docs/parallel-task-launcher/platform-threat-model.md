# 平台验证范围与 token 威胁模型（B1 task launcher）

本文记录 `task_launcher/` 只读 PoC 的平台覆盖与 token 文件的安全边界。**不是**一次新的验收结论：
未执行的项目保持 `NOT RUN`。

## 1. 已验证平台

| 平台 | 验证内容 | 状态 |
|---|---|---|
| Windows 11 + Python 3.13.15 | 任务套件 98 tests（后增至 120）、冻结基准 12/12、全量套件、`taskkill /T` 进程树终止、含空格/中文路径 | **已执行**（本机） |
| Ubuntu（GitHub Actions）+ Python 3.10 / 3.13 | `python3 -m unittest discover -s tests -v`（含 task_launcher 测试）、`benchmarks/task-launcher/run_benchmark.py`（CI job） | **已由 CI 覆盖** |
| macOS | 任务套件、基准、`killpg` 实际路径 | **NOT RUN**（本次没有 macOS 环境） |
| Windows token 文件 ACL 加固 | 仅 best-effort（见 §2）；未做 ACL 加固与低权限同机用户实测 | **NOT RUN** |

POSIX 的 `killpg` 分支由 Ubuntu CI 覆盖；Windows 分支由本机 `taskkill /T` 实测。macOS 与 Linux 的
行为差异（默认临时目录、文件权限、进程组）未单独实测。

## 2. Token 文件威胁模型

launcher 只绑定 `127.0.0.1`，所有端点（除 `GET /health`）要求
`Authorization: Bearer <token>`；token 来源是 `--token-file` 或默认
`<state-dir>/launcher.token`（随机 `secrets.token_urlsafe(32)`）。token 不进 argv、子进程环境、
工作区证据或结果。

| 平台 | 权限处理 | 残余风险 |
|---|---|---|
| POSIX | 创建 token 文件时尝试 `chmod 0600` | 失败只记录为 best-effort；同机同用户进程、root 或备份工具可读取 |
| Windows | 仅依赖文件系统继承 ACL，没有显式 `chmod` 等价加固 | **同机低权限用户可能读取** token（取决于 `%LOCALAPPDATA%` 的 ACL 继承） |

结论与建议：

1. **不要把 launcher token 交给 EDA 插件/connector 长期保存**。若 Phase 2 由 daemon 转发任务，
   推荐 token 只由 daemon 持有，connector 仅调用 daemon 的本地接口（见 `integration-proposal.md` §3.1）。
2. 仅在本机、单用户场景使用当前 PoC；需要更强隔离时，给 token 文件加平台 ACL 或把 launcher
   置于受控父进程/服务账户下。
3. 泄露 token 的后果是“同机可提交只读任务/读取任务证据”，**不会**获得 EDA 工程写权限；
   `mode=write` 在任何情况下都会被拒绝（`422 WRITE_MODE_NOT_SUPPORTED`）。
4. token 轮换：删除 token 文件并重启 launcher 即生成新 token；旧 token 立即失效。

## 3. 任务书 §3.3 示例勘误（IC-15）

任务书 `b1-task-launcher-task-book.md` §3.3 的示例把 `context.snapshot_sha256` 写成 `null`，但
`missing_fields` 未包含 `"snapshot_sha256"`。在严格校验下该示例会被拒绝：

```text
422 MISSING_SNAPSHOT_DECLARATION
```

**正确写法**：`snapshot_sha256: null` 时必须在 `missing_fields` 中显式声明
`"snapshot_sha256"`（未知信息不得猜测）。仓库内的规范示例见
[`contract.md` §2.1](contract.md)，差异说明见 [`contract.md` §12.1](contract.md)。任务书本身在
仓库外，由任务 owner 维护；本仓库不复制第二份“任务书示例”。

## 4. 不证明什么

- 平台测试通过不等于真实 EDA 工程可用、DRC 通过或硬件实测完成。
- fake agent 结果不代表真实模型的 Skill 依从性；真实 Claude 验收用例默认跳过（`NOT RUN`）。
- token 威胁模型是静态分析 + 本机行为记录，不是渗透测试。
