# 任务 H 交接（procurement planner）

> 本文件是任务 H 的专属交接，**不改**仓库主 `docs/handoff-current.md`。
> 分支：`feat/parallel-procurement-planner`；独立 worktree：
> `C:\Users\jlc\Documents\deepseek-harness\default-workspace\hds-pp-worktree`；
> 开工 main SHA：`9a951edc21481dc3ae91460acc11aa3e08a7be8a`。
> 最终交付提交 SHA 与 PR 见 [report.md](report.md) / PR 页面。

## 1. 已完成

| 工作包 | 结果 |
|---|---|
| H1 需求展开 | 位号组/每板数量/批量/DNP/比例+固定+最小备损/自备抵扣/MOQ+MPQ 取整/超购与剩余，逐步输出 |
| H2 价格/库存/费用 | total_tier + progressive + per_pack；Decimal 金额；共享库存池；预留；交期性质；运费/税费/SMT 费/免运；未知不当 0 |
| H3 渠道分离 | `lcsc_mall` 与 `jlc_smt` 独立 offer/快照/字段；SMT 可贴靠独立证据；THT/手焊单列 |
| H4 替代 | 五类分级；被动件/有源件字段比较；来源必需；pin/footprint/mode 证据；两个真实原厂来源样例 |
| H5 多策略 | `known_cost`、`channel_split`、`conservative_substitution`；有界贪心；未知/unsatisfied 不参与最低成本排序 |
| CLI/输出 | `validate`/`demand`/`plan`/`alternates`/`explain`；JSON stdout；Markdown/采购 CSV；原子写；退出码 |
| 测试 | 78 个测试（全部真实 CLI 子进程）；4 个 holdout；9 组手算；变形/反例 |
| 基准 | 6 个冻结 case，输入 SHA/评估时刻/预期值；`result.json` 记录 timing 与 NOT RUN 标记 |
| 文档 | contract/channel/substitution/source-register/acceptance/report/integration/handoff + issue-candidates |

## 2. 文件位置

```
easycirq/scripts/procurement_planner/     # 包（__main__ / cli / model / planner / ...）
tests/procurement_planner/                       # 78 个测试 + fixtures（含 4 holdout）
benchmarks/procurement-planner/                  # run_benchmark.py, expected.json, result.json
docs/parallel-procurement-planner/               # 8 份文档 + issue-candidates + 来源研究日志
```

## 3. 快速验收命令

```powershell
cd hds-pp-worktree

# 1) 业务测试
python -m unittest discover -s tests/procurement_planner -t tests -p "test_*.py"

# 2) 冻结基准（必须 6/6，退出码 0）
python benchmarks/procurement-planner/run_benchmark.py --check --write-result

# 3) 手工演示
cd easycirq/scripts
python -m procurement_planner plan `
  --input ..\..\tests\procurement_planner\fixtures\basic.json `
  --out $env:TEMP\plan.json --markdown $env:TEMP\plan.md `
  --procurement-csv $env:TEMP\procurement.csv
python -m procurement_planner alternates `
  --input ..\..\tests\procurement_planner\fixtures\alternates-real.json
```

## 4. 设计要点（接续者必读）

1. **数量公式唯一**：`orderable = ceil(max(need,MOQ)/MPQ)*MPQ`；`max()` 会漏
   包装倍数，禁止改成两段 `max`。
2. **备损顺序固定**：`ratio -> fixed -> minimum`；DNP 为 0；自备只抵扣同身份
   且合格数量。
3. **金额**：输入金额必须是字符串/整数，拒绝 float；最终按币种最小单位量化；
   多币种不合成假总价。
4. **库存池**：显式 `pool_id` 同池跨行只扣一次；池内数量取最小；同供应 ID
   无池只 warning 不合并；未知库存不算满足。
5. **快照时效**：以 `--as-of`/`evaluation.as_of` 重放；过期快照不因文件时间
   变新；模拟快照必标 `synthetic_not_live`，计划状态最高
   `planned_with_unknowns`。
6. **渠道**：商城库存/SMT 可贴/手焊是三种结论；不能互相推断。
7. **替代**：来源必需（document/revision/page/https URL）；`drop_in_verified`
   永远 false；不自动改 BOM。
8. **状态**：只用四个；`unsatisfied` 与 `planned_with_unknowns` 区分“已知
   不可满足”和“数据不足”。
9. **排序**：有界贪心，不声称全局最优；未知费用/风险不按 0 参与最低成本。

## 5. 已知限制（不要当已验证）

- 无实时商城/SMT/EDA 查询；所有数据来自输入快照或合成夹具。
- SMT 结论只到字段+来源级；未验证工厂当日接受/费用。
- 被动件真实样例的料号由订购规则解码，独立料号页未取得；见
  [source-register.md](source-register.md) §2.4。
- 主动件样例只覆盖一类比较器；未做热/EMC/实物/封装几何验证。
- 有界搜索可能因拆单/超购上限产生已知缺料；不是全局最优。
- 未改 SKILL.md/references/README/CHANGELOG/版本/主 handoff/CI/其他任务。

## 6. 后续建议

1. 维护者评审后按 [issue-candidates.md](issue-candidates.md) 处理公共导航。
2. 任务 A 若提供统一 BOM 导出，按 [integration-proposal.md](integration-proposal.md)
   §1 接入。
3. 真实供应数据必须走官方/授权适配层，不抓页面、不绕 WAF。
4. 若要扩展替代族，优先补有源器件（LDO/MOSFET/接口）与更多来源样例。
5. PR 未合并前不要把本分支当发布版本，也不要把采购计划当订单/制造 BOM。
