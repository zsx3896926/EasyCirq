# docs/method — 原理图布局方法论

让 AI 画出好原理图的三件事：先想清楚（判据/离在线/测量/单变量/棘轮），按层沉淀（L0–L6），失败分类不重犯；再让 ACE 评审把"王牌工程师会问的问题"变成可回归的离线检查。

- [schematic-layout-thinking.md](schematic-layout-thinking.md) — 思考框架：判据先行、先量后放、单变量闭环、失败→检查→守卫的棘轮、magic number 决策记录、反模式表。
- [sedimentation-protocol.md](sedimentation-protocol.md) — 沉淀协议：L0 证据 → L1 数据 → L2 规则 → L3 工具 → L4 测试 → L5 决策 → L6 复盘，每层含 owner/更新触发/过时检查与 executable+checkable+reusable 的 DoD。
- [failure-taxonomy.md](failure-taxonomy.md) — 失败分类：FX/FT/FG/FD/FP 共 27 条（症状/根因/检测/守卫/自动化现状），含欠账清单与新增模板。
- [layout-engine-v2.md](layout-engine-v2.md) — 布局引擎 v2 设计：模板/度量 → 分页 → 分区 → 标签 → 硬规则 → 单次落点；离线/真机边界、指标定义与集成清单；含自主迭代补充（门禁、矩形并集、块模板、save-after-apply）。
- [layout-engine-adr.md](layout-engine-adr.md) — v2 的 5 条 ADR：实测模板、先分页后落位、validator 门禁、离线文字求解 + 单次 apply、版本化度量资产。
- [layout-engine-v2-contract.md](layout-engine-v2-contract.md) — v2 契约：page plan schema、模块清单与硬规则 R1–R7 的冻结接口（实现以契约为准）。
- [ace-review-checklist.md](ace-review-checklist.md) — ACE 评审清单：10 条已实现规则 + 向 30 条扩展的口径、错误注入 applicable/detected 度量、评审门禁与语料库。
- [ace-review-adr.md](ace-review-adr.md) — ACE 与自主迭代的 6 条 ADR：确定性快照评审、错误注入度量、评审门禁、矩形并集可用区、role→(dx,dy) 块模板、save-after-apply 不变量。
- 配套：[布局流水线](../../easycirq/references/schematic-layout-pipeline.md) · [风格规范](../../easycirq/references/schematic-style.md) · [看图验收](../../easycirq/references/schematic-layout.md) · [EDA 动作陷阱](../../easycirq/references/tool-gotchas.md) · [夜间日志 2026-10-29](../nightly-training/2026-10-29.md)。
