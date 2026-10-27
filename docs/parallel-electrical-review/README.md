# 任务 B：离线电气设计审查与回归基准（独立模块）

本目录是任务 B 的完整交付说明。模块当前**不接入主执行流程**，不修改共享入口；
集成建议见 `integration-proposal.md`。任务 A 可独立完成自己的工作，无需等待本模块。

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
