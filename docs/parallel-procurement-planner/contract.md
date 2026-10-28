# 采购规划器契约（procurement-planner/v1）

> 状态：并行任务 H 首期离线契约。工具不联网、不登录商城、不调用 EDA、不下单、
> 不预留库存、不改写输入 BOM。所有价格/库存/费用都必须来自带来源与
> `captured_at` 的快照；合成夹具只能标 `synthetic_not_live`。
>
> schema：`procurement-input/v1`；报告 schema：`procurement-plan/v1`、
> `procurement-demand/v1`、`procurement-validation/v1`、
> `procurement-alternates/v1`、`procurement-explanation/v1`；
> `tool_version = 0.1.0`。

## 1. 运行入口

代码位于 `easycirq/scripts/procurement_planner/`，从该目录运行：

```powershell
cd easycirq/scripts

# 只校验输入（退出码 0=valid，2=input_invalid）
python -m procurement_planner validate --input ..\..\tests\procurement_planner\fixtures\basic.json

# 需求展开：位号组×板数、备损、自备、采购需求
python -m procurement_planner demand --input ..\..\tests\procurement_planner\fixtures\basic.json

# 多策略规划（stdout 机器 JSON）
python -m procurement_planner plan `
  --input ..\..\tests\procurement_planner\fixtures\basic.json `
  --out plan.json --markdown plan.md --procurement-csv procurement.csv

# 替代候选分级
python -m procurement_planner alternates `
  --input ..\..\tests\procurement_planner\fixtures\alternates-real.json

# 解释某一行：需求链、候选报价、选中订单、渠道/替代结论
python -m procurement_planner explain `
  --input ..\..\tests\procurement_planner\fixtures\basic.json --line L1
```

CSV 导入必须同时给 `--bom-csv` 与 `--column-map`；列名不做猜测：

```powershell
python -m procurement_planner plan --input input.json `
  --bom-csv bom.tsv --column-map column-map.json --as-of 2026-10-27T12:00:00+08:00
```

`--as-of` 是声明的评估时刻（RFC3339，带时区），优先级高于输入
`evaluation.as_of`。没有时默认取输入声明；都没有才取系统时间，并在
`evaluation.as_of_source=system` 中显式标出。

## 2. 退出码与输出通道

| 退出码 | 含义 |
|---|---|
| 0 | validate/demand/alternates：无 blocking；plan/explain：`planned_with_evidence` 或 `planned_with_unknowns` |
| 1 | plan/explain：`unsatisfied`（已知缺料、预算超限或策略硬约束） |
| 2 | 输入/用法错误：`input_invalid`；stdout 仍是一个 JSON 错误/校验对象 |

- stdout：恰好一个 JSON 对象，UTF-8，`sort_keys` 稳定排序。
- stderr：一行诊断（命令、status、行数/订单数/缺料数）。
- `--out`/`--markdown`/`--procurement-csv`：原子写入（同目录临时文件 +
  `os.replace`），拒绝覆盖任何输入文件；Markdown 与采购 CSV 带
  `NOT_ORDER | NOT_LIVE_QUOTE` 水印。
- 内部 MPN 原值不改；只有导出 CSV 的单元格做公式注入防护（前导
  `= + - @` 前缀 `'`），JSON 中保持原值。

## 3. 输入顶层结构

```json
{
  "schema": "procurement-input/v1",
  "project": {"name": "...", "bom_revision": "rev-A",
               "board_quantity": 10, "allow_zero_boards": false},
  "evaluation": {"as_of": "2026-10-27T12:00:00+08:00",
                  "freshness": {"max_age_hours": "24"}},
  "policies": {
    "attrition": {"ratio": "0.1", "fixed": 0, "minimum": 0,
                   "order": ["ratio", "fixed", "minimum"]},
    "overbuy": {"max_extra_qty": 50, "max_extra_ratio": "0.20",
                 "allow_price_break_extra": true},
    "order_policy": "moq_mpq",
    "substitution": {"enabled": true,
                      "allowed_grades": ["exact_identity",
                                          "evidence_supported_candidate"]},
    "search": {"max_search_steps": 10000},
    "channel_preference": ["lcsc_mall", "jlc_smt"]
  },
  "bom": {"revision": "rev-A", "rows": []},
  "demand": {"channels": ["lcsc_mall", "jlc_smt"],
              "assembly_strategy": "smt", "hand_solder_allowed": false,
              "self_supply_allowed": true, "due_date": "2026-11-15T00:00:00+08:00",
              "budget": {"amount": "500.00", "currency": "CNY"},
              "split_policy": {"allow_multi_offer": true,
                                "max_orders_per_line": 3,
                                "max_orders_total": null}},
  "supply_snapshots": [], "offers": [], "fees": [],
  "fx_rates": [], "alternates": []
}
```

### 3.1 BOM 行

`line_id`（唯一、不能含路径分隔符/`..`）、`designators`（大写位号数组）、
`qty_per_board`、`mpn`、`manufacturer`、`supply_ids`（`{"lcsc": "C123"}` 或
`{"other": "..."}`）、`footprint`、`package`、`assembly`
（`smt|tht|hand|dnp`）、`dnp`、`consigned_qty`、`consigned_qualified`（默认
true）、`params`、`unknown_fields`、`identity_source`
（`kind`/`source`/`captured_at`）。

- `designators` 与 `qty_per_board` 同时给出时必须相等；只有位号时数量取位号数；
  只有数量时允许但产生“位号追溯缺失” warning。
- 全 BOM 位号唯一；同 MPN 不同封装给 warning，身份不互相替代。
- `dnp=true` 或 `assembly=dnp` 不进入采购需求，保留在报告里。
- 自备数量只在 `self_supply_allowed=true` 且 `consigned_qualified=true` 时
  抵扣同一行身份；超过需求时截断并 warning。

### 3.2 需求策略

- `channels`/`allowed_channels`：允许的履约渠道，取值
  `lcsc_mall | jlc_smt | other_supplier`。
- `assembly_strategy`：`smt | hand_solder | mixed`；THT/手焊行不能由仅 SMT
  渠道“全自动完成”。
- `due_date`：RFC3339 或 `YYYY-MM-DD`（日期按 UTC 当日 23:59:59 处理）。
- `budget`：金额字符串 + 支持币种；不同币种不合成假总价。
- `split_policy.max_orders_{per_line,total}`：显式拆单上限；触限产生
  `split_limit_reached` / `max_orders_total_reached` 阻塞，不静默忽略。

### 3.3 供应快照

`snapshot_id`、`source`（`synthetic_fixture | user_provided |
official_api_export | manual_table`）、`declared_truth`
（`synthetic_not_live | user_provided_unverified | manual_table_unverified |
official_export`）、`captured_at`、`valid_until`（可选）、`channel`
（必填）、`sha256`（可选）、`live_supply_query`（只有 official export 可为
true）。合成快照必须声明 `synthetic_not_live`，否则输入无效。

时效规则：以声明评估时刻重放；`captured_at` 晚于评估时刻=非法输入；
`valid_until` 过期或 `age > evaluation.freshness.max_age_hours` 时快照
`stale=true`。过期快照不因文件修改/导入时间变新，其价格/库存不参与满足性
判断；对应行进入 unknown 而不是“现货”。

### 3.4 offer

必填：`offer_id`（唯一）、`supplier`、`channel`、`product_id`、`mpn`、
`footprint`、`currency`、`tax_basis`（`incl|excl|unknown`）、`price_mode`
（`total_tier|progressive`）、`price_tiers`、`price_unit`、`moq`、`mpq`、
`stock`、`snapshot_id`。可选：`manufacturer`、`package`、`lead_time`、
`smt`、`packaging`、`notes`。

价格档：

```json
{"min_qty": 1, "max_qty": null, "unit_price": "0.0100"}
```

- 必须从 `min_qty=1` 开始、按 `min_qty` 严格升序、区间不重叠；倒序/重复/重叠
  都是 `input_invalid`（不静默重排）。
- 金额必须是字符串/整数（`"0.01"`），拒绝二进制 float、bool、NaN/Infinity、
  负数；币种必须是支持列表（CNY/USD/EUR/HKD/GBP/SGD/TWD/JPY，JPY 0 位小数）。
- `price_unit.kind=per_pack` 必须给 `pack_qty`；`per_each` 不得带 `pack_qty`。
- `total_tier`：数量落在哪档就整档用该单价；未写 `max_qty` 时上限由下一档
  `min_qty-1` 推断。`progressive`：分段累进，段内各自单价，最后一段可开口。
- 价格阶梯存在无法覆盖的缺口时，该数量的价格记为 unknown，不猜价。
- 搜索是有界贪心（`policies.search.max_search_steps`）；不声称全局最优。

库存：

```json
{"qty": 5000, "status": "in_stock", "reserved": 0,
 "independent": true, "pool_id": "POOL-C123"}
```

`status`：`in_stock|low|out_of_stock|unknown|not_applicable`。
`available = max(0, qty - reserved)`；`unknown`/数量缺失/不独立且无 pool 时
可用量未知。同一 `pool_id` 的 offer 视为同一物理库存，跨行只扣一次；池内数量
不一致取最小值并 warning；pool 被不同供应身份复用则按身份拆分并 warning。
没有显式池但同一供应 ID 出现在多个 offer 时给“可能重叠”warning，不静默合并。

交期：

```json
{"kind": "in_stock|estimated|committed|unknown|not_applicable",
 "days_min": 0, "days_max": 0, "captured_at": "..."}
```

缺 `lead_time`/天数时 `lead_time.status=unknown`，不能判按时。`in_stock`
只表示快照显示现货（不是承诺、也未预留），有截止日期时按
`stock_snapshot_only` 报告，不升级为“按时”。

### 3.5 费用与汇率

费用：`fee_id`、`kind`（`shipping|tax|smt_extended_part_fee|smt_board_fee|
stencil|handling|other`）、`channel`（或 `any`）、`amount` 或 `rate`、`currency`、
`basis`（`per_order|per_line|per_part|per_board|percent_of_subtotal`）、
`tax_basis`、可选免运 `waiver`、`source`、`captured_at`、`unknown`。
未知费用必须 `unknown=true` 且不得同时给 amount/rate；未声明运费/税费/SMT 费用
也会被列为未知，不按 0 计。

汇率：`{"base":"USD","quote":"CNY","rate":"7.2000","source":"...",
"captured_at":"..."}`，语义为 1 base = rate quote。仅当汇率来源存在且未超过
`max_age_hours` 时才用于预算比较；否则分币种报告并 `undetermined_currency`。

### 3.6 替代候选

`alternates[]`：`alt_id`（唯一）、`line_id`、`original`/`candidate`
（`mpn`/`manufacturer`/`footprint`/`facts`/`sources`）、`application.requirements`、
`evidence`（`pin_map`/`footprint`/`mode`）、`approval_scope`
（`procurement_only|design_review_required|not_approved`）、`notes`。
每个参与比较的字段都必须有来源：`document`、`revision`、`page`、`url`（https）、
可选 `table`/`condition`/`accessed_at`。详见
[substitution-policy.md](substitution-policy.md)。

## 4. 计算契约

### 4.1 需求展开

```
assembled = qty_per_board × board_quantity              （DNP 行为 0）
spare_ratio = ceil(assembled × ratio)
spare_after_fixed = spare_ratio + fixed
spare_total = max(spare_after_fixed, minimum)
target = assembled + spare_total
consigned_applied = min(consigned_qty, target)           （仅合格且允许自备）
purchase_need = max(0, target - consigned_applied)
```

顺序固定为 `ratio -> fixed -> minimum`，其他顺序是非法输入；DNP 不参与备损/
自备/采购；零板数需 `allow_zero_boards=true`，否则 `input_invalid`。

### 4.2 可下单数量（MOQ 与 MPQ 组合，唯一公式）

```
orderable(need) = 0                                          if need <= 0
                = ceil(max(need, MOQ) / MPQ) × MPQ            otherwise
```

即：可下单量是“满足 MOQ 的最小 MPQ 整数倍”，不是 `max(need, MOQ)`，也不是
只取其中一项。报告同时给 `base_qty`、`ordered_qty`、`overbuy_qty`、
`remaining_after_assembly_qty`。

### 4.3 有界超购

超购只用于比较“更高价格档是否降低总价”，上限明确：

```
allowed_extra = min(max_extra_qty, floor(orderable_base × max_extra_ratio))
max_extra_qty_total = orderable_base + floor(allowed_extra / MPQ) × MPQ
```

只在 `total_tier` 模式、库存已知、且候选数量不超过库存时搜索；未知库存不打开
超购搜索。默认 `max_extra_qty=50`、`max_extra_ratio=0.20`，可用
`demand.overbuy` 覆盖。工具不声称全局最优，`bounded_search.global_optimum_claimed
= false`。

### 4.4 搜索预算（确定性，代替墙钟超时）

`policies.search.max_search_steps`（默认 10000）限制每种策略的贪心尝试步数；
用确定性步数预算而不是墙钟超时，避免测试/基准随机器速度漂移。预算用尽时：

- 当前行加入 `unknown_reasons.code=search_budget_exhausted`，剩余数量按未知；
- 计划状态为 `planned_with_unknowns`（不是“已知缺料”）；
- `bounded_search.search_steps/max_search_steps/search_budget_exhausted`
  显式记录，仍不声称全局最优。

### 4.5 金额与税

内部用 `Decimal`；行总价/费用/预算换算在输出时按币种最小单位量化
（`ROUND_HALF_UP`）。同一币种不同 `tax_basis` 分别报告；商品为税前价但没有
税费用时税是未知而非 0。多币种不合并成单一“总成本”。

### 4.5 覆盖与状态

- 行状态：`covered`、`covered_with_unknowns`、`partial_unknown`、
  `uncovered_known`、`not_required`。
- 计划状态只用四个：`planned_with_evidence`、`planned_with_unknowns`、
  `unsatisfied`、`input_invalid`；绝不使用 `order_ready` /
  `procurement_verified`。
- `unsatisfied`：已知缺料（out_of_stock、已知库存不足、策略上限）或预算超限。
- `planned_with_unknowns`：无已知不可满足，但存在未知库存/价格/费用/交期、过期
  或未验证快照、合成数据、替代证据不足。
- `planned_with_evidence`：全部覆盖且快照为 `official_export`、无未知费用/价格/
  交期；仍不代表实时可买或订单就绪。

多策略（默认三种）：`known_cost`（已知成本优先）、`channel_split`
（渠道/拆单减少）、`conservative_substitution`（替代保守）。比较只对已知子集
排序；`unsatisfied` 策略不参与最低成本比较；未知费用/风险不当 0。

## 5. CSV 导入

映射文件 schema `procurement-csv-map/v1`：

```json
{
  "schema": "procurement-csv-map/v1",
  "encoding": "utf-16",
  "delimiter": "tab",
  "designator_separator": ",",
  "columns": {
    "line_id": "No.", "quantity_per_board": "Quantity",
    "designators": "Designator", "footprint": "Footprint",
    "mpn": "Manufacturer Part", "manufacturer": "Manufacturer",
    "supply_part": "Supplier Part", "description": "Comment"
  },
  "defaults": {"assembly": "smt", "dnp": false},
  "dnp_values": ["DNP", "DNF", "NOFIT"]
}
```

- 编码只接受显式 `utf-8`/`utf-8-sig`/`utf-16`/`utf-16-le`/`utf-16-be` 或
  `auto`（仅根据 BOM 前缀判断 UTF-8/UTF-16）；解码失败即报错，不猜 GBK。
- 列名必须与表头精确匹配；缺列、重复表头、未知规范列都报错。
- 没有 assembly 列时必须在 `defaults.assembly` 显式声明，不能默认猜 `smt`。
- 位号数与 Quantity 不一致是 blocking。
- 限制：JSON ≤ 4 MiB、CSV ≤ 8 MiB、CSV ≤ 5000 数据行；不执行单元格内容。
- CSV 导出对公式注入做防护，但内部/JSON 的 MPN 原值保持不变。

## 6. 输入安全与只读边界

- 输入文件只读；输出不能与任何输入路径相同。
- 标识符（line_id/offer_id/snapshot_id/fee_id/alt_id/pool_id）拒绝路径分隔符、
  `..`、控制字符；文本字段拒绝控制字符。
- 拒绝重复 JSON key、NaN/Infinity、bool 冒充数字、负数需求/价格/库存、
  非法/未来时间、非法币种、负价、倒序/重叠价格档、包装单位缺失、
  重复费用/替代 ID。
- 同 MPN 不同封装、同供应 ID 不同 MPN/制造商、同池不同身份：warning +
  拒绝互相替代，不静默合并。
- 不联网、不抓商城、不登录、不调用 EDA/Connector、不下单、不锁库存、不上传
  工程。所有 `not_checked` 项在报告中原样列出。

## 7. 输出报告关键字段

`procurement-plan/v1` 顶层：`status`、`tool_version`、`input`（schema/sha256/
csv 哈希）、`project`（BOM revision、声明/计算源哈希、板数）、`evaluation`、
`supply`（快照来源/时间/新鲜度、`live_supply_query=NOT RUN`）、`currency`、
`demand`、`preferred_strategy`、`strategies`、`comparison`、`plan`
（lines/orders/fees/budget/counts/blockers/unknowns）、`alternates`、`blockers`、
`warnings`、`unknowns`、`limits`（`not_order`、`not_live_quote`、`real_eda=NOT
RUN`、`simulated_data`）、`not_checked`、`report_notes`。

每行包含：需求链（`demand`）、候选/冲突、选中订单（数量、单价依据、价格档
候选、库存池扣减前后、快照来源/真伪、交期）、覆盖/缺料/超购/剩余、已知费用、
渠道结论、替代分级、trace。未知原因区分 `stock_unknown`、`price_unknown`、
`stale_or_untrusted_snapshot`、`no_supply_evidence`、
`substitution_candidate_without_offer`。

## 8. 版本与兼容

- 首期契约 `procurement-input/v1`/`procurement-plan/v1`；
  `tool_version=0.1.0`。字段扩展向后兼容时增加可选字段，不改变已有语义；破坏性
  变更必须升 schema 版本。
- 契约测试：`python -m unittest discover -s tests/procurement_planner -t tests
  -p "test_*.py"`；冻结基准：
  `python benchmarks/procurement-planner/run_benchmark.py --check`。
