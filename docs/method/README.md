# docs/method — 原理图布局方法论

让 AI 画出好原理图的三件事：先想清楚（判据/离在线/测量/单变量/棘轮），按层沉淀（L0–L6），失败分类不重犯。

- [schematic-layout-thinking.md](schematic-layout-thinking.md) — 思考框架：判据先行、先量后放、单变量闭环、失败→检查→守卫的棘轮、magic number 决策记录、反模式表。
- [sedimentation-protocol.md](sedimentation-protocol.md) — 沉淀协议：L0 证据 → L1 数据 → L2 规则 → L3 工具 → L4 测试 → L5 决策 → L6 复盘，每层含 owner/更新触发/过时检查与 executable+checkable+reusable 的 DoD。
- [failure-taxonomy.md](failure-taxonomy.md) — 失败分类：FX/FT/FG/FD/FP 共 27 条（症状/根因/检测/守卫/自动化现状），含欠账清单与新增模板。
- 配套：[布局流水线](../../easycirq/references/schematic-layout-pipeline.md) · [风格规范](../../easycirq/references/schematic-style.md) · [看图验收](../../easycirq/references/schematic-layout.md) · [EDA 动作陷阱](../../easycirq/references/tool-gotchas.md) · [夜间日志 2026-10-29](../nightly-training/2026-10-29.md)。
