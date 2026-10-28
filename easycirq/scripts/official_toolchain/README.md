# official_toolchain —— 官方 lceda-pro CLI/MCP 薄适配层（并行、非默认）

这是「退 A」决策里 **S1** 阶段的落地：把 spike #75 的官方 CLI 薄适配层作为**并行非默认**路径引入，与自建 `easycirq` runtime 并跑。

## 定位（非默认）

- **默认执行路径仍是自建 `easycirq` runtime**（`runtime/` Go daemon + `cmd/easycirq`）。本目录**不**替换它，也不在任何 CLI 入口/installer/发布流水线里被默认调用。
- 本目录只是官方 `lceda-pro` CLI/MCP 的**薄封装**，供对等矩阵维护、官方能力探测与将来 S4 切换时使用。

## 模块

| 文件 | 职责 | 是否启动 EDA |
|---|---|---|
| `official_cli.py` | 官方 CLI 薄封装（`find_exe` / `run` / `open_project` / `invoke` / `close_session` …） | 仅在**显式调用**时；`find_exe` 惰性定位 |
| `workflows.py` | W01–W11 工作流定义（数据，离线可校验） | 否 |
| `build_matrix.py` | 对等矩阵/rubric 计算（`evaluate_rubric` 纯函数） | 否 |
| `common.py` | stdlib 工具（JSON/hash/路径） | 否 |
| `mcp_stdio.py` | 官方 `--mcp stdio` 探测 | 仅在**显式调用**时 |

## 边界

- 本目录**不含** spike 的 operator 驱动脚本（`probe_official.py`/`probe_writes.py`/`capture_api_catalog.py`/`hash_self_evidence.py`/`plan_pr36_split.py`/`run_spike.py`）与原始证据回执（`docs/evidence/a2-coverage-2026-10-28/`）——那些是一次性 EDA 探针，保留在 spike 分支，其结论已并入 `docs/toolchain-integration/`。
- 本目录不证明官方 CLI 与 `easycirq` runtime 已对等；对等判定见 `docs/toolchain-integration/a2-parity-diff.md` 与 `easycirq/references/execution-layer-retirement.md`。
- 写探针必须由 operator 显式驱动，且只在一次性副本上进行（不做任何默认写入）。
