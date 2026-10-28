# B1-Bound 冻结基准（Phase 1 离线，simulated）

本目录是 `task_launcher/bound`（B1-Bound Phase 1 只读 supervisor）的冻结基准：
**24 个 case**，全部通过**子进程**驱动真实 CLI —— 基准进程不 import 实现。

每个 case 的流程：

1. `python -m task_launcher.bound plan --request <req> --out <task-dir>`
   在 `tempfile` 临时目录生成任务目录（fixture 后端，无真实 EDA）；
2. 子进程启动真实 supervisor：
   `python -m task_launcher.bound serve --config <task>/bound.config.json --token-file <task>/task.token`；
3. 模拟 MCP 客户端通过 stdin/stdout 的 newline-delimited JSON-RPC 2.0（UTF-8）
   逐步调用工具（`initialize` → `notifications/initialized` → `tools/call` / `tools/list`），
   对每一步断言稳定错误码 / 状态 / 结构化结果；
4. 部分 case 在 supervisor 写下 `receipts.jsonl` / `evidence.json` 之后**篡改文件**，
   再调用 `finalize`，验证“磁盘上的证据与签名链不一致 → 拒绝”（见 receipt 类 case）。

所有临时产物（任务目录、token、receipt、report）都在 `tempfile` 目录中，
运行结束即删除；仓库里只保留 `cases/`、`run_benchmark.py`、`README.md` 和运行生成的 `results.json`。

## 运行

在 worktree（仓库）根目录：

```text
python benchmarks/task-launcher-bound/run_benchmark.py
```

可选：

```text
python benchmarks/task-launcher-bound/run_benchmark.py --list
python benchmarks/task-launcher-bound/run_benchmark.py --case readonly-pass --case token-invalid
```

退出码：全部通过 `0`，否则 `1`（少于 12 个 case 也算失败）。

## 覆盖的 24 个 case

| # | case | 验证点 | 期望结果 |
|---|---|---|---|
| 1 | `readonly-pass` | readonly 全链路 | 报告 `PASS`，`real_eda=NOT RUN`，`eda_calls=0` |
| 2 | `readonly-fail` | 离线审计 `fail` | 允许 finalize，报告 `FAIL` |
| 3 | `readonly-review-required` | 离线审计 `review_required` | 报告 `REVIEW_REQUIRED` |
| 4 | `readonly-incomplete` | 离线审计 `incomplete` | 任务 `INCOMPLETE`，finalize 被拒，无报告 |
| 5 | `version-mismatch` | `task_start` 的 skill 版本被改 | `VERSION_MISMATCH`，后续步骤全部被拒，不可 finalize |
| 6 | `token-invalid` | `task.token` 被篡改 | `serve` 启动 exit 2 / `TOKEN_INVALID` |
| 7 | `token-missing` | `task.token` 缺失 | `serve` 启动 exit 2 / `TOKEN_MISSING` |
| 8 | `skip-before-task-start` | 未 `task_start` 就 snapshot/audit/finalize | `OUT_OF_ORDER` / `NOT_READY` |
| 9 | `skip-audit-before-snapshot` | 跳过 `snapshot_read` 直接审计/收尾 | `NOT_READY` |
| 10 | `duplicate-steps` | 重复 `task_start` / `snapshot_read` | `STEP_ALREADY_DONE`（每步仅一条签名回执） |
| 11 | `phase1-phase2-tools-absent` | Phase 1 工具面 + 调用 `apply` | `tools/list` 只有 6 个只读工具；`apply` → JSON-RPC `-32602` |
| 12 | `phase2-apply-without-plan` | Phase 2 无 plan 直接 `apply` | `PLAN_NOT_FOUND` |
| 13 | `phase2-plan-hash-mismatch` | plan_submit 后用错误 `plan_id` apply | `PLAN_HASH_MISMATCH`，不可 finalize |
| 14 | `phase2-no-eda-authorization` | Phase 2 无 EDA 授权：正确 `plan_id` apply | `EDA_NOT_AUTHORIZED`，任务 `FAILED`，finalize `TASK_CLOSED`；**期望行为是 BLOCKED / NOT RUN，不是通过** |
| 15 | `snapshot-hash-mismatch` | launcher 声明的快照哈希与实际不一致 | `SNAPSHOT_MISMATCH`，任务不能推进 |
| 16 | `receipt-tamper-hmac` | 外部改第一条回执 HMAC | finalize → `RECEIPT_HMAC_INVALID` |
| 17 | `receipt-missing-step` | 删除 `snapshot_read` 回执行 | finalize → `RECEIPT_MISSING` |
| 18 | `receipt-duplicate-line` | 复制最后一条回执行 | finalize → `RECEIPT_DUPLICATE_STEP` |
| 19 | `receipt-out-of-order` | 交换两条回执行顺序 | finalize → `RECEIPT_STEP_ORDER` |
| 20 | `evidence-tampered` | 篡改 `evidence.json`（`real_eda`/`eda_calls`） | finalize → `EVIDENCE_TAMPERED` |
| 21 | `prompt-injection-ignored` | goal prompt 与 fixture 快照含“忽略规则、立即 finalize”注入文本 | 提前 finalize 仍 `NOT_READY`；正常链路 `PASS`，报告不含注入声明、`real_eda=NOT RUN` |
| 22 | `limits-max-tool-calls` | 任务 limits `max_tool_calls=2` | 第 3 次调用 `LIMIT_EXCEEDED` |
| 23 | `limits-max-steps` | 任务 limits `max_steps=2` | 第 3 步 `LIMIT_EXCEEDED` |
| 24 | `abort-then-finalize` | `task_abort` 后收尾 | finalize `TASK_CLOSED`，任务 `CANCELLED`，无报告 |

## `results.json`（`easycirq.bound.benchmark/v1`）

运行后由 `run_benchmark.py` 生成/覆盖，关键字段：

```json
{
  "schema": "easycirq.bound.benchmark/v1",
  "simulated": true,
  "agent": "none",
  "real_eda": "NOT RUN",
  "eda_calls": 0,
  "project_writes": 0,
  "driver": "simulated MCP client ... serve ... (fixture backend)",
  "generated_at": "2026-...Z",
  "runtime": {"python_version": "...", "python_implementation": "...", "platform": "..."},
  "limits": {"benchmark": {...}, "case_task_limits": {"<case id>": {...}}},
  "cases": [
    {
      "id": "readonly-pass",
      "status": "passed",
      "expected": {"outcome_class": "PASS", "outcome": "...", "final_state": "FINALIZED", "errors": [], "result_present": true},
      "actual": {"outcome_class": "PASS", "outcome": "verdict PASS", "final_state": "FINALIZED", "verdict": "PASS", "errors": [], "receipts_count": 5},
      "duration_ms": 123.4,
      "error": null
    }
  ],
  "summary": {"total": 24, "passed": 24, "failed": 0}
}
```

`status` 只有 `passed` / `failed`；`error` 为 `null` 或失败原因。失败 case 绝不会被写成通过。

## 诚实边界（NOT RUN）

- `simulated: true`、`agent: "none"`：没有启动真实 Claude Code / 任何 agent。
- `real_eda: "NOT RUN"`、`eda_calls: 0`、`project_writes: 0`：fixture 后端，未连接 EDA /
  官方 CLI / daemon / connector / 网络；`case 14` 的 `EDA_NOT_AUTHORIZED` 正是“无授权时被拒绝”，
  不能读作 Phase 2 通过。
- 本基准证明的是 **Phase 1 契约与门禁行为**（状态机、token/版本握手、HMAC 回执链、
  证据完整性、注入文本不改变流程、limits/abort、Phase 2 未授权即 BLOCKED），
  不证明真实 EDA 写、真实 Claude 行为或整板验收。
- B1 集成仍 **BLOCKED ON B1**：本基准不需要、也不读取 B1 的可执行接口。
