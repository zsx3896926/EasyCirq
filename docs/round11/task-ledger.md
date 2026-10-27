# round11 任务表 — 离线能力强化

基线：`origin/main` `066a74b`（2026-10-26，PR #22 后）。执行分支：
`feat/offline-toolchain-round11`。本轮 **EDA 调用 0 次**。

| 包 | 内容 | 状态 | 证据 |
|---|---|---|---|
| A | 真正离线的测试入口、fake runner/DI、import 副作用、负例 | DONE | `tools/offline_suite.py`、`offline_guard.py`、`tests/test_offline_guard.py` |
| B | 证据解析与空数据/矛盾响应/类型/计数一致性 | DONE | `pcb_evidence.py`、`tests/test_pcb_evidence_contract.py` |
| C | SCH↔PCB 别名/重复/分区/身份/排除 | DONE | `compare_sch_pcb`、同一测试文件 |
| D | 证据来源、manifest 绑定、冲突、mtime 辅助、语义哈希、缓存键 | DONE | `pcb_gate.py`、`test_pcb_gate_provenance.py`、`eda_cache.py` |
| E | 计划编译/执行分离、默认值、no-op、journal、恢复、原子写 | DONE | `pcb_apply_plan.py`、`test_pcb_apply_plan.py` |
| F | mm/旋转/角度/凹板/keepout/线宽几何 | DONE | `geometry.py`、`pcb_workflow.py`、`test_geometry_primitives.py` |
| G | 硬约束优先、候选评分、可行性措辞、模块复用 | DONE | `placement.py`、`pcb_workflow.py`、`reuse.py`、`test_pcb_workflow.py`、`test_design_engine.py` |
| H | 图面回归、误报保留、对象/建议、分析叠加图、字体不确定性 | DONE | `sch_visual_audit.py`、`test_sch_visual_audit.py` |
| I | 冻结基准、来源/哈希/预期、变形、性能口径、holdout | DONE | `benchmarks/offline-round11/`、`tools/offline_benchmark.py` |
| J | Skill/文档/交接/全量测试/PR | DONE（PR #24） | `SKILL.md`、`references/offline-regression.md`、`docs/handoff-current.md` |
| K | 安装/缓存/兼容性演练（临时目录） | NOT RUN（扩展，本轮未实施） | — |
| L | 输入安全与批量回放（归档穿越/大输入/汇总） | NOT RUN（扩展，本轮未实施） | — |
