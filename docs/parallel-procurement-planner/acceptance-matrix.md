# 验收矩阵与冻结基准

> 首期验收全部离线：真实 CLI 子进程、合成供应快照、冻结输入 SHA 与声明评估
> 时刻。`real_eda=NOT RUN`、`live_supply_query=NOT RUN`、`network_access=NOT
> RUN`。基准通过只说明“给定输入下规划结果一致”，不证明任何器件当前可采购。

## 1. 复现命令

```powershell
# 业务测试（78 个，全部通过真实 CLI 子进程）
python -m unittest discover -s tests/procurement_planner -t tests -p "test_*.py"

# 整个仓库回归（包含本任务新增测试）
python -m unittest discover -s tests -v

# 冻结基准：6 个 case（含 4 个 holdout），校验失败退出 1
python benchmarks/procurement-planner/run_benchmark.py --check --write-result
```

## 2. 场景覆盖（78 个测试，≥24 个 CLI 场景）

| 类别 | 场景（测试） | 预期 |
|---|---|---|
| 输入契约 | invalid JSON / wrong schema / duplicate designator / qty≠位号 / 负数量 / 零板策略 / float·bool·负价 / NaN / 倒序·重叠阶梯 / 非法币种 / 未来时间 / 重复 offer / 不安全 ID / 未知顶层字段 / strict | 正常输入 `valid`；违约 `input_invalid` 且退出码 2 |
| 需求展开 | 单板/批量、位号组展开、DNP、比例+固定+最小备损、自备抵扣、自备超需求截断 | 每一步显式输出；DNP 采购为 0；超需求只抵扣并 warning |
| MOQ/MPQ/价格 | MOQ+MPQ 组合公式、higher-tier 更低总价、超购上限、progressive、per_pack、价格缺口未知 | 数量/总价与手算一致；未知价不猜 |
| 费用与税 | 税前商品+税率、未声明运费、已声明免运、SMT 费用、未知费用 | 已知费用入小计；未知费用不按 0；预算状态区分 |
| 库存 | 已知缺货、未知库存、预留扣减、共享池跨行、池数量冲突、非独立库存无池 | 已知缺货 `unsatisfied`；未知库存 `planned_with_unknowns`；共享池只扣一次 |
| 渠道 | 商城有货≠SMT 可贴、SMT 独立证据、THT 仅 SMT、渠道策略差异 | 商城/SMT 结论分开；THT 阻塞；策略差异可见 |
| 交期 | 预计交期晚于截止、缺交期 | `late` / `unknown`；不承诺按时 |
| 币种/预算 | 多币种无汇率、有来源汇率、预算超限 | 分币种报告；有汇率才换算；超预算 `unsatisfied` 并列出受影响行 |
| 替代 | 真实被动件不兼容、真实有源件需评审、exact_identity、证据不足、来源缺失、synthetic evidence candidate | 五类状态按证据判级；`drop_in_verified=false`；不改 BOM |
| CSV | UTF-16 EasyEDA 风格 BOM、显式列映射、缺列、位号数量不一致、5000 行限制、公式注入 | 映射失败/超限 `input_invalid`；CSV 防注入、JSON MPN 原值 |
| 输出 | JSON/Markdown/采购 CSV、水印、确定性、输入不可变、explain、单策略 | 原子写出；两次运行 stdout 相同；输入哈希不变 |
| 搜索预算 | `max_search_steps=1` 的有界搜索耗尽 | `search_budget_exhausted` 显式 unknown，不伪装成已知缺料/全局最优 |
| 变形 | BOM/offer 顺序反转、金额等价写法、单位换算、无关渠道 | 总额/行数量不变（价格档变化时按真实价制断言） |
| Holdout | H1 备损+自备+MOQ/MPQ、H2 共享池+未知、H3 汇率+预算、H4 保守替代 | 冻结 SHA/评估时刻/状态/数量/成本 |

**明确覆盖的负例：** 同 MPN 不同封装（身份不互相替代）、同供应 ID 不同
MPN/制造商（identity conflict）、负价/倒序价格档、快照渠道缺失、pool 被不同
身份复用、未知费用、过期快照、未来时间、未知顶层字段。

## 3. 独立手算样例（≥6）

以下期望值由公式手算后写入测试，不读取实现输出回填。

### H-1 批量与比例备损

10 板 × 每板 2 只 = 20；比例 10% → `ceil(20×0.10)=2`；固定 0、最小 0 →
备损 2；采购需求 22。测试 `test_demand_expansion_exact_numbers`。

### H-2 比例→固定→最小备损 + 自备 + MOQ/MPQ

7 板 × 3 只 = 21；比例 5% → `ceil(1.05)=2`；+固定 2 = 4；最小 3 → 取 4；
target=25；自备 2 抵扣 → purchase_need=23；MOQ 10、MPQ 5 →
`ceil(max(23,10)/5)×5 = ceil(4.6)×5 = 25`；100 pcs 内 0.20/只 → 5.00；
商城运费 5.00（未达免运门槛）→ 已知合计 10.00。测试
`test_holdout_1_attrition_moq` + 基准 `holdout-h1-attrition`。

### H-3 更高价格档降低总价（有界）

需 90；档位 `1–99: 0.10`、`100+: 0.08`。买 90 → 9.00；买 100 → 8.00。
超购上限 `min(50, floor(90×0.20))=18`，100 在允许范围内 → 选 100，超购 10。
测试 `test_higher_tier_can_lower_total_within_overbuy_cap`。

### H-4 分段累进价

15 pcs：第一段 1–9（9 pcs×1.00）+ 第二段 10–99（6 pcs×0.80）
= 9.00 + 4.80 = 13.80。测试 `test_progressive_pricing_total`。

### H-5 MOQ/MPQ 组合

需 30、MOQ 100、MPQ 50 → `ceil(max(30,100)/50)×50 = 100`，超购 70。
测试 `test_moq_mpq_rounding_uses_single_formula`。

### H-6 包装单位换算

每 100 pcs 5.00，需 120 → 单价 5.00/100=0.05 → 120×0.05=6.00。测试
`test_per_pack_price_unit_is_converted_to_each`。

### H-7 基础夹具费用

商品：22×0.01=0.22；33×0.02=0.66；11×2.20=24.20；11×0.50=5.50 →
30.58 CNY。费用：商城运费 8.00（商城小计 6.38 < 99 免运门槛，未免）；
SMT 运费 0（声明）；SMT 扩展料费 3.00/part × 1；板费 0（声明）→ 11.00。
已知合计 41.58，预算 500 内。测试 `tests/.../test_planning.py` 多个断言
+ 基准 `basic-plan`。

### H-8 汇率

5 × 1.20 USD = 6.00 USD；1 USD = 7.2000 CNY → 6.00×7.2 = 43.20 CNY；
预算 100 CNY 内。测试 `test_fx_rate_allows_budget_comparison_without_fake_total`
+ 基准 `holdout-h3-fx`。

### H-9 预留扣减

库存 5、预留 3 → 可用 2；需 10 → 只能买 2，缺 8。测试
`test_reserved_stock_reduces_available`。

## 4. Holdout（4 组合，冻结输入 SHA + 评估时刻）

| ID | 输入（`tests/procurement_planner/fixtures/holdout/`） | 冻结 SHA256 前缀 | 评估时刻 | 预期 |
|---|---|---|---|---|
| H1 | `h1-attrition.json` | `d0415dbdc7db8fc8…` | 2026-10-27T04:00:00Z | `planned_with_unknowns`；need 23、order 25、goods 5.00、fees 5.00、budget 10.00 |
| H2 | `h2-shared-pool.json` | `09f6a2a5c7323c4c…` | 同上 | `planned_with_unknowns`；L1 20、L2 10 缺 10、共享池不重复 |
| H3 | `h3-multicurrency-fx.json` | `042540e7fa08e164…` | 同上 | `planned_with_unknowns`；USD 6.00、预算换算 43.20 |
| H4 | `h4-substitution.json` | `5e309b10306a839d…` | 同上 | `planned_with_unknowns`；保守策略选中 ALT-R、order 2、0.04；known_cost 为 unsatisfied |

完整 SHA 与期望值在
`tests/procurement_planner/fixtures/holdout/expected.json`；基准另存于
`benchmarks/procurement-planner/expected.json`。测试禁止按场景 ID 特判，所有
holdout 走同一 CLI 与同一断言逻辑。

## 5. 冻结基准

`benchmarks/procurement-planner/result.json`（最近一次运行）：

| case | status | 耗时量级 | 关键校验 |
|---|---|---|---|
| `basic-plan` | `planned_with_unknowns` | ~0.1 s | 4 订单、goods 30.58、fees 11.00、budget 41.58 |
| `real-alternates` | `valid` | ~0.1 s | PASS-001 `incompatible`；ACT-001 `requires_design_review` |
| `holdout-h1-attrition` | `planned_with_unknowns` | ~0.1 s | need 23 / order 25 / budget 10.00 |
| `holdout-h2-shared-pool` | `planned_with_unknowns` | ~0.1 s | L1 20、L2 10/缺 10 |
| `holdout-h3-fx` | `planned_with_unknowns` | ~0.1 s | USD 6.00、43.20 CNY |
| `holdout-h4-substitution` | `planned_with_unknowns` | ~0.1 s | 保守替代、0.04 |

- 6/6 通过；`simulated=true`；`real_eda=NOT RUN`；`live_supply_query=NOT RUN`；
  `network_access=NOT RUN`。
- 输入 SHA 不匹配时基准失败；每次运行记录每个 case 的 `duration_ms` 与
  `input_sha256`。
- 基准不访问网络、不调用 EDA、不登录商城、不下单。

## 6. 变形与反例审查

- **顺序变形：** 反转 BOM rows 与 offers 顺序，行数量/费用总额不变。
- **金额等价：** `"5.0"`/`"5.00"` 与整数金额表示在 Decimal 下等价；float 被
  拒绝（防止二进制结算）。
- **数量单位：** per-pack 与等价 per-each 价格得到相同行总价。
- **需求增加：** 有界超购下采购数量不下降（价格档可能让总价下降，断言按真实
  阶梯规则，不强行要求总价上升）。
- **未知不补零：** 未声明运费/税费、未知库存、未知价格均进入 unknown；比较
  最低成本时排除 unknown/unsatisfied，不把未知当 0。
- **不静默删行：** 所有 BOM 行（含 DNP/缺料/未知）都出现在 `plan.lines`。

## 7. 已知限制

- 全部价格/库存/费用为合成夹具或用户声明快照；没有实时商城/API 查询。
- SMT 结论只到“字段 + 来源”级，不证明工厂当日接受或费用。
- KEMET 两个料号由订购规则解码，独立料号页未取得（见 source-register）。
- 有源替代样例只覆盖一类比较器；未覆盖 EDA 封装/热仿真/EMC/实物。
- 有界贪心搜索不声称全局最优；拆单/超购上限是策略约束，可能产生已知缺料。
