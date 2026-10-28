# 任务 B：离线电气设计审查与回归基准（独立模块）

本目录是任务 B 的完整交付说明。模块当前**不接入主执行流程**，不修改共享入口；
集成建议见 `integration-proposal.md`。任务 A 可独立完成自己的工作，无需等待本模块。

## 验收状态（2026-10-28 最终复验）

| 验收项 | 结果 |
|---|---|
| `main` 验收基线 | `acbcc18c821e08ddff2401015eb7a16eaee733c8`（含 #48 LF 修复、#52 P1/P2 修复） |
| 任务 B PR 状态 | **#38 CLOSED**（内容由 #48 合入 main）；P1/P2 修复 **#52 已合入 main** |
| `python -m unittest discover -s tests -k electrical_review` | **55 tests OK**（3.579 s，exit 0） |
| 全量 `python -m unittest discover -s tests` | **3144 tests OK（skipped=2）**（314.0 s，exit 0） |
| `python benchmarks/electrical-review/run_benchmark.py --runs 3` | **31/31 pass**，exit 0 |
| 基准状态 / EDA | `status=pass`；`simulated=true`、`real_eda="NOT RUN"`、`eda_calls=0` |
| 场景分布 | pass_with_scope 9、fail 11、review_required 6、incomplete 1、invalid_input 4 |
| 基准 timing（3 runs） | 31 场 min 合计 4.862 s；单场 max 193.0 ms（不宣称画板提速） |
| Python 3.10 / 3.13 | **CI `validate (3.10)` / `validate (3.13)` 已通过**（#48、#52、本 docs PR） |
| 独立审查遗留 | Codex P1（pad_nets 冲突）/ P2（按键外部旁路）已由 #52 修复并补回归测试 |

`pass_with_scope` 只证明所列规则和给定输入覆盖，不是整板、DRC、保存重开、制造或上电验收。
完整记录见 `acceptance.md` 与 `handoff-current.md`。

## 文档索引

| 文件 | 内容 |
|---|---|
| `contract.md` | 输入/输出 JSON 契约、状态语义、退出码、哈希/原子写、证据分层 |
| `design.md` | 架构、R1–R6 实现口径、状态机、为什么不是关键词扫描、已知限制 |
| `sources.md` | 原厂资料核验（型号/版本/页/表/URL/PDF SHA-256）、适用条件、真实/合成/重放分界 |
| `fact-research.md` | 资料核验成员的原始记录（ALPS SKHH / C&K PTS645 / MCP23017 更正） |
| `acceptance.md` | 基线、环境、实际命令与结果、测试/基准数字、0 EDA 核查、未完成项 |
| `integration-proposal.md` | 给任务 A 的字段映射、调用点、退出码策略、SKILL.md/references diff 片段 |
| `issue-candidates.md` | 现有公共模块的审查盲区候选（含独立复现，不越界修改） |
| `adversarial-review.md` | 反例审查记录（Lead 自审；独立成员失败，文件内如实声明） |
| `handoff-current.md` | 专属交接：基线、范围、命令、证据、未知项、接入说明 |

## 代码与测试路径

| 路径 | 内容 |
|---|---|
| `design-hardware/scripts/electrical_review/` | 独立模块与 `python -m electrical_review` CLI |
| `tests/electrical_review/` | 专属测试与夹具（带 `__init__.py`，既有 discover 可识别） |
| `benchmarks/electrical-review/` | 31 个冻结 CLI 场景、expected、驱动、result |
| `docs/parallel-electrical-review/` | 本目录 |

## 入口

```bash
cd design-hardware/scripts
python -m electrical_review validate INPUT.json
python -m electrical_review review INPUT.json [--out REPORT.json]
python -m electrical_review explain REPORT.json [--rule R1]
```

退出码：0 pass_with_scope / 1 fail / 2 invalid_input / 3 review_required / 4 incomplete。
`pass_with_scope` 只证明所列规则和输入覆盖，不是整板、DRC、制造或上电通过。
