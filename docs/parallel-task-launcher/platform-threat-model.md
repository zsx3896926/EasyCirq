# 平台验证范围与 token 威胁模型（B1 task launcher）

本文记录 `task_launcher/` 只读 PoC 的平台覆盖与 token 文件的安全边界。**不是**一次新的验收结论：
未执行的项目保持 `NOT RUN`。

## 1. 已验证平台

| 平台 | 验证内容 | 状态 |
|---|---|---|
| Windows 11 + Python 3.13.15 | 任务套件 98 tests（后增至 120）、冻结基准 12/12、全量套件、`taskkill /T` 进程树终止、含空格/中文路径 | **已执行**（本机） |
| Ubuntu（GitHub Actions）+ Python 3.10 / 3.13 | `python3 -m unittest discover -s tests -v`（含 task_launcher 测试）、`benchmarks/task-launcher/run_benchmark.py`（CI job） | **已由 CI 覆盖** |
| macOS | 任务套件、基准、`killpg` 实际路径 | **已由 CI 覆盖**（`macos-latest` job：任务套件 + 基准，见 `.github/workflows/validate.yml`） |
| Windows token 文件 ACL 加固 | `icacls` 去继承、仅授当前用户 + SYSTEM + Administrators，低权限同机用户拒绝 | **已执行**（本机，`tests/task_launcher_tests/test_token_acl.py` 断言） |

POSIX 的 `killpg` 分支由 Ubuntu 与 `macos-latest` CI 覆盖；Windows 分支由本机 `taskkill /T` 实测，
Windows token ACL 由本机 `test_token_acl.py` 实测。

## 2. Token 文件威胁模型

launcher 只绑定 `127.0.0.1`，所有端点（除 `GET /health`）要求
`Authorization: Bearer <token>`；token 来源是 `--token-file` 或默认
`<state-dir>/launcher.token`（随机 `secrets.token_urlsafe(32)`）。token 不进 argv、子进程环境、
工作区证据或结果。

| 平台 | 权限处理 | 残余风险 |
|---|---|---|
| POSIX | 创建/读取 token 文件时都尝试 `chmod 0600`；`test_token_acl.py` 在 Ubuntu/macOS CI 验证 | 失败只记录为 best-effort；同机同用户进程、root 或备份工具可读取 |
| Windows | launcher 每次启动用 `icacls /inheritance:r /grant:r` 去掉继承，仅授当前用户 + `*S-1-5-18`(SYSTEM) + `*S-1-5-32-544`(Administrators)；`test_token_acl.py` 断言 `BUILTIN\Users`/`Everyone` 已被移除 | Administrators 组内其他管理员仍可读取（预期）；普通低权限用户已拒绝 |

结论与建议：

1. **不要把 launcher token 交给 EDA 插件/connector 长期保存**。若 Phase 2 由 daemon 转发任务，
   推荐 token 只由 daemon 持有，connector 仅调用 daemon 的本地接口（见 `integration-proposal.md` §3.1）。
2. token 文件现在会做平台加固（POSIX 0600 / Windows ACL 去继承）；如需更强的审计或服务账户
   隔离，可把 launcher 置于受控父进程/服务账户下，并配合平台审计策略。
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
