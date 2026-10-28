# Acceptance evidence（M2/M3/M4 真机验收证据）

本目录由 `tools/easycirq_acceptance.py` 生成，记录**真机验收**的原始证据与本次（无连接器状态下的）阻塞证明。
所有状态只用 `PASS / FAIL / NOT RUN / BLOCKED / UNKNOWN`；**没有执行过的步骤不计为通过**。

## 当前状态（2026-10-27 21:4x）

- `easycirq 0.2.0-dev` 已构建，daemon 隔离运行于 `127.0.0.1:23111`。
- 自有连接器 `.eext` 未在 EasyEDA Pro 内导入 → `connector.status=disconnected`。
- 因此 M2/M3/M4 的宿主步骤全部 **NOT RUN**，脚本以**退出码 2（BLOCKED）**结束。
  这不是失败，也不是通过；解锁条件见 `../acceptance-matrix.md`。

## 文件

| 文件 | 内容 |
| --- | --- |
| `self-test.json` | 脚本纯逻辑自检（快照比较/解析/脱壳），12/12 通过，退出码 0 |
| `summary.json` | 最近一次运行的机器可读汇总（schema `easycirq-acceptance/v1`） |
| `summary-blocked-dryrun.json` | `--stage all --dry-run --json` 的完整汇总（BLOCKED 路径证据） |
| `summary-m2-blocked-dryrun.json` | `--stage m2 --dry-run --json` |
| `blocked-dryrun.stderr.log` / `m2-blocked-dryrun.stderr.log` | 对应的人类可读摘要（stderr，UTF-8） |
| `preflight/` | 真实执行的只读前置检查：`doctor.json`、`capabilities.json`、`connector-verify.json`、`connector-path.json`、`health.json` + 每步 `.cmd/.stdout/.stderr/.meta` |
| `cli-help/` | 本次验收所依据的 CLI 命令面快照（42 个 `--help` 输出 + `INDEX.txt`） |
| `commands.jsonl` | 命令级日志（argv、退出码、耗时、sha256），最近一次运行 |
| `artifacts/` | 真机运行时导出的产物（当前为空：无宿主通道） |

## 复跑

```powershell
# 1) 纯逻辑自检（无需连接器）
python tools/easycirq_acceptance.py --self-test --evidence-dir docs/toolchain-integration/evidence/acceptance --json

# 2) 阻塞路径 / 计划自检（会真实执行只读 preflight，然后退出 2）
python tools/easycirq_acceptance.py --stage all `
  --project-dir docs/toolchain-integration/evidence/acceptance `
  --evidence-dir docs/toolchain-integration/evidence/acceptance --dry-run --json

# 3) 解锁后（连接器已导入、doctor connector=connected）
python tools/easycirq_acceptance.py --stage m2 --project-dir <设计工作区> --evidence-dir <证据目录> --json
python tools/easycirq_acceptance.py --stage m3 --project-dir <设计工作区> --evidence-dir <证据目录> --json
python tools/easycirq_acceptance.py --stage m4 --m4-device R1 --project-dir <设计工作区> --evidence-dir <证据目录> --json
```

约定：`easycirq_acceptance.py` 与 `easycirq` 一样 **JSON→stdout、人类摘要→stderr**；不加 `--json` 时 stdout 为空。

## 不应如何解读

- `preflight/*.json` 全部 `PASS` 只证明**只读诊断命令可运行**，不证明任何 EDA 写操作可用。
- `summary-*.json` 里出现的 `NOT RUN` 一律带原因；把 `NOT RUN` 当作通过属于伪造证据。
- `doctor.verdict=degraded` 表示连接器未接入；`blocked` 才会在 preflight 直接阻断（两者都不允许继续跑宿主步骤）。
