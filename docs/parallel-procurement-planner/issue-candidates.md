# 公共修改候选（任务 H 未执行）

> 这些修改涉及 `SKILL.md`、已有 references、README/CHANGELOG、CI、版本或主
> handoff，超出任务 H 允许路径，因此只记录建议，不在本分支修改。维护者可
> 在任务 A/D 或发布流程中统一处理。

| # | 文件/位置 | 建议 | 原因 | 风险 |
|---|---|---|---|---|
| 1 | `SKILL.md` “商城配单/采购”段落 | 增加一句：离线采购规划可用 `easycirq/scripts/procurement_planner`，并指向 `docs/parallel-procurement-planner/contract.md` | 让 Agent 在“配齐元件/批量用量/缺料替代”时找到可执行工具，而不是只写文档 | 需确认不超过 SKILL.md 导航长度预算；不要复制整篇契约 |
| 2 | `easycirq/references/lcsc-sourcing.md` §8.3 或 `selection/README.md` | 增加“采购数量/费用/替代分级计算”指针到本任务 docs | 现有 references 已讲流程，但无程序化数量/阶梯价/库存池算法 | 避免与已有商城规则重复；只加链接 |
| 3 | `README.md` 文档索引 / `docs` 索引 | 登记 `docs/parallel-procurement-planner/` | 并行任务文档可发现 | 维护者需决定并行任务文档是否保留在主线 |
| 4 | `.gitattributes` | 对本目录 `easycirq/scripts/procurement_planner/**`、`tests/procurement_planner/**`、`docs/parallel-procurement-planner/**`、`benchmarks/procurement-planner/**` 强制 `text eol=lf` | 现有规则对部分目录强制 LF，Py 测试跨平台 | 纯格式；需维护者确认 |
| 5 | `.github/workflows/validate.yml` | 现有 `unittest discover` 已覆盖新增测试，无需改；可选增加 benchmark 步骤 | 冻结基准目前不在 CI 运行，可能随时间/依赖漂移 | 基准含时序，CI 只应跑 `--check`；不要设性能阈值 |
| 6 | `easycirq/.version` / `CHANGELOG.md` | 由发布流程决定是否记入本任务 | 本任务不打包/不发版 | 按仓库发布策略 |
| 7 | 任务 A 导出器 | 输出 `bom_source_sha256` + `bom_revision` + 位号组/装配方式 | 规划器需要来源版本，避免旧 BOM/旧价格 | 需 A 的实现确认字段 |
| 8 | 供应数据适配层（未来） | 官方/授权 API 导出 `offers[]`/`supply_snapshots[]` | 真实采购需要来源、时间、渠道、税/包装/MOQ 字段 | 涉及账号/授权/网络，不在本任务范围 |
| 9 | 任务 C 交付审计 | 只读引用采购计划，不把它当制造 BOM/CPL | 避免采购状态被误当制造放行 | 需文档说明字段边界 |
| 10 | 任务 F 参数化生成 | 把生成参数映射为替代候选的 `application.requirements` | 让替代判断带设计条件 | 需 F 输出契约稳定后再接 |

**不做的事：** 不在本分支改 SKILL.md/references/README/CHANGELOG/版本/主
handoff/CI/依赖/其他任务目录；不把公共修改伪装成“顺手完成”。
