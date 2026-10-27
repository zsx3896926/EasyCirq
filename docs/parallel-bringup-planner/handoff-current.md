# 并行任务 I 交接（bringup-planner）

> 最后更新：2026-10-28（PR #39 复核后状态：**待审查**；最终数据以 `report.md` 为准）

## 交付状态：待审查

| 项 | 值 |
|---|---|
| **状态** | **待审查（PENDING REVIEW）** — 2026-10-28 复核通过，等待主分支/审查人处理 |
| PR | https://github.com/zsx3896926/hardware-design-skill/pull/39 （OPEN / MERGEABLE / 非 draft；**未合并、未发布、未安装客户端**） |
| 复核时 HEAD | `3bb3496e9bb1c4a8e101e3c513bd11de9224f6c0`（本状态提交后以 PR 页面最新 HEAD 为准） |
| 复核结论 | PR diff 175 files（复核时 `3bb3496`：+44735/−0，精确以 PR 页面为准），全部位于下方允许路径；无越界文件；报告数字与实测一致（已修正 3 处表述/数字，见 `report.md` §13） |

## 身份与基线

| 项 | 值 |
|---|---|
| 任务 | 智构并行任务 I：首板上电、功能测试与故障定位计划生成器 |
| worktree | `C:/Users/jlc/Documents/deepseek-harness/default-workspace/hds-bp-worktree` |
| 分支 | `feat/parallel-bringup-planner` |
| 基线 main | `9a951edc21481dc3ae91460acc11aa3e08a7be8a`（`test: make Chinese fixture portable across Windows locales`） |
| 基线 remote | `origin/main` 同一 SHA（开工时核对） |
| 提交/PR | 首个实现提交 `c61d62c`；独立 PR https://github.com/zsx3896926/hardware-design-skill/pull/39 （OPEN/MERGEABLE，状态：待审查）；**不合并、不发布、不安装客户端** |

## 允许路径（本任务只改这些）

```
design-hardware/scripts/bringup_planner/
tests/bringup_planner/
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
python -m unittest discover -s tests/bringup_planner -p "test_*.py"
python benchmarks/bringup-planner/run_benchmark.py --out /tmp/bringup-benchmark.json
python tools/offline_suite.py          # 既有仓库离线套件，不应回归
```

## 当前状态

- **交付状态：待审查**（2026-10-28 复核，PR #39 OPEN/MERGEABLE，未合并）。
- 代码/契约/测试/资料/文档已落地；`report.md` 记录实测结果（172 tests、41/41 基准、30/30 类别、1783 既有离线测试、skill_selftest 5 PASS）与已修问题。
- 复核记录（PR diff 175 files +44735/−0、允许路径核对、报告一致性修正）见 `report.md` §13。
- 所有真实仪器、上电、烧录、串口/JTAG、EDA 操作为 **NOT RUN**；评估器 `PASS` 只是离线记录一致性结论。
- 已知边界：首期只支持低压直流（≤30 V 工作 / ≤60 V 绝对）；市电/高压/电池充放电/射频认证标 unsupported/needs_specialist。
- 集成建议见 `integration-proposal.md`；未改 A/C/F 代码、不依赖其他会话未合入提交。

## 后续入口

1. 读 `contract.md` 了解输入/输出/退出码/绑定语义。
2. 读 `report.md` 看验收命令、实测结果、已修问题与剩余限制。
3. 读 `acceptance-matrix.md` 看六组能力与场景映射。
4. 若要把本任务接入 A/C/F：读 `integration-proposal.md`，按版本化 JSON + 哈希绑定；不要在本分支改对方代码。
