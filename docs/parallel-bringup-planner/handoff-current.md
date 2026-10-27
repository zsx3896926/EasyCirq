# 并行任务 I 交接（bringup-planner）

> 最后更新：2026-10-28（PR #39 已合并；M0–M4 证据清单已补，见 `acceptance-matrix.md` §7）

## 交付状态：已合并 + 证据清单待审查

| 项 | 值 |
|---|---|
| **状态** | **已合并（PR #39）** — merge commit `9a4622eb46a8ff3d336729726ab6ed056b5f650a`，`mergedAt=2026-10-27T16:53:24Z`，由仓库账号 `zsx3896926` 合并；**本任务未执行合并、未发布、未安装客户端**。本次证据清单更新 PR 待审查 |
| 合并源 HEAD | `b407d72f11237001d7c7e1260beb8de770f46f1e`（PR #39 `headRefOid`；changedFiles=175） |
| 证据采集 HEAD | `3f21897d9d1b93b4ac7e2ef523fe923685f59b08`（基于合并后 main 的 worktree）；采集时 `origin/main` 已前进到 `acbcc18c…`（其他并行任务） |
| 证据清单 | `acceptance-matrix.md` §7（逐命令/退出码/摘要/HEAD/PASS-NOT RUN）+ `evidence-m0-m4.json` + 复现脚本 `benchmarks/bringup-planner/tools/collect_m0_m4_evidence.py` |
| 证据结论 | 本任务软件检查 **33 PASS**；唯一 FAIL 是当前 main 上其他任务测试包导致的 47 个 `offline_suite` discovery errors（`bringup_planner_tests` 0 error，非本任务）；**硬件/仪器动作全部 NOT RUN** |

## 身份与基线

| 项 | 值 |
|---|---|
| 任务 | 智构并行任务 I：首板上电、功能测试与故障定位计划生成器 |
| worktree | 实现：`C:/Users/jlc/Documents/deepseek-harness/default-workspace/hds-bp-worktree`；证据更新：`hds-bp-evidence` |
| 分支 | 实现：`feat/parallel-bringup-planner`（已合并）；证据更新：`docs/bringup-planner-m0-m4-evidence` |
| 基线 main | `9a951edc21481dc3ae91460acc11aa3e08a7be8a`（`test: make Chinese fixture portable across Windows locales`） |
| 基线 remote | `origin/main` 同 SHA（开工时核对）；合并后已由其他并行任务推进 |
| 提交/PR | 实现提交 `c61d62c`/`3bb3496`/`d35ff34`/`b407d72`；PR #39 已合并（commit `9a4622e`）；证据清单更新 PR 见仓库 PR 列表（待审查）；**不合并、不发布、不安装客户端** |

## 允许路径（本任务只改这些）

```
design-hardware/scripts/bringup_planner/
tests/bringup_planner_tests/      # 集成合并后由 tests/bringup_planner/ 迁入（集成者处理）
benchmarks/bringup-planner/
docs/parallel-bringup-planner/
```

未修改：`SKILL.md`、现有 `references/`、README/CHANGELOG/版本/主 handoff、runtime/connector/protocol、distribution、CI、顶层依赖、feedback、compose、design_engine 及其他任务目录。需要共享修复的项写在 `issue-candidates.md`（如无则为空）。

## 交付物

- 可运行 CLI：`python -m bringup_planner validate|plan|explain|evaluate`（在 `design-hardware/scripts` 下运行）
- 六组能力：I1 断电检查、I2 分域上电/限流、I3 电源/时钟/复位/通信测量、I4 负载/接口模板、I5 有限故障树与 STOP、I6 独立结果评估
- JSON 契约 + Markdown 检查表 + 空白结果 JSON/CSV + `manifest.json`（哈希/原子写）
- 两个组合板案例（`benchmarks/bringup-planner/cases/mcu-sensor-board`、`load-control-board`）
- 24+ CLI 冻结场景 + 4+ holdout/变形 + `run_benchmark.py`（真实子进程）
- 一手资料：11 个官方来源、143 条 facts（78 条带页码；ESP32-C3、TPS62130、TLV700、LM393、CSD17578Q3A、Fluke 87、Rigol DS1000Z 等）
- 文档：`contract.md`、`supported-scope.md`、`source-register.md`、`measurement-policy.md`、`acceptance-matrix.md`、`report.md`、`integration-proposal.md`、本文件、`issue-candidates.md`

## 运行方式

```bash
cd design-hardware/scripts
python -m bringup_planner validate --input <input.json> --json
python -m bringup_planner plan --input <input.json> --out <out-dir> --json
python -m bringup_planner explain --input <input.json> [--step <id>] --json
python -m bringup_planner evaluate --plan <out>/plan.json --results <results.json> \
    --evidence-root <evidence-dir> --out <out2> --json
```

测试与基准（worktree 根目录）：

```bash
python -m unittest discover -s tests/bringup_planner_tests -p "test_*.py"
python benchmarks/bringup-planner/run_benchmark.py --out /tmp/bringup-benchmark.json
python tools/offline_suite.py          # 仓库离线套件；当前 main 含其他任务测试包，见 §7.5
```

## 当前状态

- **实现已合并（PR #39，merge commit `9a4622e`）；M0–M4 证据清单已补，更新 PR 待审查。**
- 证据（2026-10-28）：专属测试 172 PASS；冻结基准 41/41 PASS、类别 30/30；`skill_selftest` 5 PASS；PR #39 范围 175 files、允许路径外 0；硬件/仪器动作全部 **NOT RUN**。逐项见 `acceptance-matrix.md` §7。
- 仓库 `offline_suite`：在 PR #39 合并 HEAD `b407d72` 上 1783 tests PASS；当前 main 上 47 errors 全部来自其他任务测试包（`bringup_planner_tests` 0 error，见 §7.5 与 `issue-candidates.md` A.6）。
- 评估器 `PASS` 只是离线记录一致性结论；`eval-pass-real-evidence` 是 NO INSTRUMENT CONNECTED 的契约 fixture，不是硬件 PASS。
- 已知边界：首期只支持低压直流（≤30 V 工作 / ≤60 V 绝对）；市电/高压/电池充放电/射频认证标 unsupported/needs_specialist。
- 集成建议见 `integration-proposal.md`；未改 A/C/F 代码、不依赖其他会话未合入提交。

## 后续入口

1. 读 `contract.md` 了解输入/输出/退出码/绑定语义。
2. 读 `report.md` 看验收命令、实测结果、已修问题与剩余限制。
3. 读 `acceptance-matrix.md` 看六组能力与场景映射。
4. 若要把本任务接入 A/C/F：读 `integration-proposal.md`，按版本化 JSON + 哈希绑定；不要在本分支改对方代码。

## Integration note (2026-10-28, main integrator)

This branch was merged to `main` by the integration lead. Two review findings were fixed
on `main`, not by changing this task's code:

1. `tests/bringup_planner/` was not discovered by the official CI command (no package
   marker, and the directory name collided with the implementation package). It moved to
   `tests/bringup_planner_tests/` with an `__init__.py`, so the official discovery runs
   all 172 tests.
2. `baseline.json` hashes had been frozen over LF bytes, while a normal Windows checkout
   produced CRLF, so 9 benchmark tests failed there. `benchmarks/bringup-planner/.gitattributes`
   now pins LF for that tree, so the frozen hashes reproduce on Windows and Linux.

Still not claimed: real instruments, power-up, flashing, serial/JTAG and EDA operations
remain NOT RUN. This planner is an independent capability, not yet wired into a main
workflow.

## Evidence update (2026-10-28, task I)

`acceptance-matrix.md` §7 now lists every M0–M4 evidence command, exit code, key output,
HEAD SHA and PASS / NOT RUN status; machine-readable backing is
`docs/parallel-bringup-planner/evidence-m0-m4.json`, reproducible with
`benchmarks/bringup-planner/tools/collect_m0_m4_evidence.py`. The only non-PASS row is
the repo-level `tools/offline_suite.py` on the current main (47 discovery errors from
other parallel tasks' test packages; the 172 `bringup_planner_tests` are not among them).
