# Round 12 任务表

> 目标：把“观察—计划—执行—回读—评价—修复—复验”变成 Skill 的正常工作流程，
> 并留下可执行工具、数据契约、真实/离线证据与失败恢复证据。
> 状态词：PASS / FAIL / BLOCKED / NOT RUN。实现与验证分开写。

## P0

| ID | 工作 | 实现 | 离线验证 | 真机验证 | 证据 |
|---|---|---|---|---|---|
| P0-1 | 基线盘点 | 完成 | PASS | 只读探测 PASS | `docs/round12/baseline-inventory.md` |
| P0-2 | 能力探测（A1） | `feedback/observe.py: probe_capabilities` | PASS（fake runner） | BLOCKED（用户要求停机） | `docs/round12/evidence/` |
| P0-3 | 观察契约（A2/A3） | `feedback/observe.py: collect_observation` | PASS | BLOCKED | 契约 `hds-observation/v1` |
| P0-4 | 修改契约 + 差异/不变量（D1–D3） | `feedback/scope.py` | PASS | BLOCKED | `hds-modification/v1`、`hds-diff/v1` |
| P0-5 | 执行/回读/保存/重开（B） | `feedback/scope.py: apply_scoped` + `feedback_loop.py` | PASS（simulated） | BLOCKED | 五类事实分开记录 |
| P0-6 | 一个真实纵向案例 | 已准备步骤 | 离线纵向案例 PASS（simulated） | BLOCKED | `docs/round12/offline-vertical-case.md` |
| P0-7 | 环路状态/预算/停止（B） | `feedback/loop.py` | PASS | N/A | `hds-feedback-loop/v1` |

## P1

| ID | 工作 | 实现 | 离线验证 | 真机验证 | 证据 |
|---|---|---|---|---|---|
| P1-1 | 恢复/部分成功（D4） | `feedback/scope.py: recover` | PASS（fault injection） | BLOCKED | `hds-recovery/v1` |
| P1-2 | 分层质量评价（C2/C3） | `feedback/evaluate.py` | PASS | BLOCKED | `hds-quality-eval/v1` |
| P1-3 | 候选比较/拒绝更整齐但更差 | `feedback/evaluate.py: compare_candidates` | PASS | N/A | `hds-candidate-compare/v1` |
| P1-4 | 案例库/检索/复用（E） | `feedback/cases.py` + `cases/index.json` | PASS | N/A | `hds-case/v1` |
| P1-5 | 验收矩阵 | `docs/round12/acceptance-matrix.md` + `tools/feedback_benchmark.py` | PASS | BLOCKED | `benchmarks/offline-round12/` |
| P1-6 | Skill 正常入口（F） | `SKILL.md` + `references/feedback-loop.md` | PASS（静态/自检） | 未实测 | 意图表/参考索引 |
| P1-7 | 三个案例（原理图可读性、电源/去耦、接口锁定） | `design-hardware/cases/feedback-r12/` | PASS（structural） | NOT RUN | `hds-case/v1` |

## P2（本轮不做，不用数量充交付）

- 更多模块/专项场景（市电、射频、高速、隔离、大电流）；
- 其它客户端（Codex/WorkBuddy）实测；
- 性能优化与更大基准；
- 完整可视化工作台/DOM 镜像/网页拖拽器/意图预测（任务书明确暂不开发）。

## 完成门槛对照

| 门槛 | 状态 | 说明 |
|---|---|---|
| 1. 正常语言入口可触发 | 部分 PASS | SKILL.md 已加“画板/这里改一下/参考以前方案”路由；未在客户端安装新版本实测 |
| 2. 一个真实任务观察→修复→回读→保存→重开 | BLOCKED | 用户要求停止真机；离线模拟完成全链路并标 simulated |
| 3. 局部边界实际差异检查/识别越界 | PASS（离线） | `tests/test_feedback_scope.py` |
| 4. 质量改善有证据、不被美观/总分掩盖 | PASS（离线） | `feedback/evaluate.py` + 验收矩阵 |
| 5. 至少一种部分失败可识别并恢复/安全接续 | PASS（故障注入） | journal + 幂等键 |
| 6. 案例有适用条件/验证层级/证据，可拒绝复用 | PASS（离线） | 案例库 + `reuse_check` |
| 7. 未知/未执行如实记录、版本对应明确 | PASS | 所有输出含 unknown/degradations；报告分状态 |

整体：**部分完成**。真机写/保存/重开/DRC 复验为 `BLOCKED`，不宣称全通过。
