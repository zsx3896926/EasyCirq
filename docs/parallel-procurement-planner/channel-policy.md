# 渠道策略：商城采购与嘉立创 SMT 分离

> 本文是任务 H 的渠道语义说明。它不查询任何商城/订单页，也不把历史字段当
> 当前状态。所有结论只对“输入快照 + 捕获时间 + 渠道”成立。

## 1. 两条履约路径不是一回事

| 维度 | 立创商城购料（`lcsc_mall`） | 嘉立创 SMT（`jlc_smt`） |
|---|---|---|
| 回答的问题 | 能否买到该商品/数量 | 工厂能否按该订单贴装，费用多少 |
| 库存来源 | 商城快照 | SMT 订单/选料页快照 |
| 可贴状态 | **不是**商城库存能推断的 | 基础库/扩展库/consigned/未知是独立字段 |
| 价格 | 商品价 + 商城运费/税费 | SMT 料价 + 扩展料费/板费/钢网等 |
| 交期 | 商城/供应商声明 | SMT 排产与备料 |
| 预留 | 本工具不锁库存 | 本工具不锁库存/不建单 |

**硬规则：**
1. C 号存在、商城有库存、EDA 库里有器件，都不能推出 SMT 可贴。
2. SMT 基础/扩展库状态也不能反过来当商城库存或实时可买证据。
3. 两个渠道的 offer 分别带自己的 `snapshot_id`；快照 `channel` 与 offer
   `channel` 不一致时，该 offer 的证据不可信（warning + 不作为已知满足）。
4. 同一 MPN 可以同时有商城 offer 与 SMT offer；数量/价格/库存分别计算，不
   互相抵扣。

## 2. offer 上的渠道字段

```json
{
  "offer_id": "OF-MALL-1",
  "channel": "lcsc_mall",
  "supplier": "LCSC",
  "product_id": "C1001",
  "mpn": "R-10K",
  "footprint": "R0603",
  "currency": "CNY",
  "tax_basis": "incl",
  "stock": {"qty": 5000, "status": "in_stock", "reserved": 0,
             "independent": true, "pool_id": "POOL-C1001"},
  "lead_time": {"kind": "in_stock", "days_min": 0, "days_max": 0},
  "snapshot_id": "SNAP-MALL"
}
```

SMT offer 额外带独立的 `smt` 对象：

```json
{
  "channel": "jlc_smt",
  "smt": {
    "attachability": "basic|extended|consigned|unknown|not_applicable",
    "evidence": {"source": "订单页/官方导出说明", "captured_at": "...",
                  "note": "..."},
    "min_placement_qty": 5,
    "feed_type": "tape|tray|...",
    "fee_ref": "FEE-SMT-EXT"
  },
  "snapshot_id": "SNAP-SMT"
}
```

`attachability` 与 `evidence` 是唯一允许支撑 SMT 候选结论的字段；缺字段时
一律 `smt_status_unknown`，不按“有 C 号/有库存”补全。`fee_ref` 只引用费用
条目，不内嵌费率；费率/金额来自 fees，未声明即未知。

## 3. 输出的渠道结论

### 3.1 商城

| `channel_conclusions.mall.status` | 含义 |
|---|---|
| `purchasable_with_snapshot_evidence` | 有匹配、渠道正确、快照未过期且库存已知的商城 offer；仍不是实时可买、未锁库 |
| `listed_stock_unknown` | 有商品/价格记录但库存未知；未知库存不视作有货 |
| `no_known_stock` | 有 offer 但无已知可用库存 |
| `stale_or_untrusted_snapshot` | 快照过期或渠道不符，不能当当前可买 |
| `no_mall_offer` | 没有匹配的商城 offer |

### 3.2 SMT

| `channel_conclusions.smt.status` | 含义 |
|---|---|
| `candidate_with_evidence` | `attachability=basic/extended` 且 `smt.evidence` 有来源；只表示“有证据的候选”，不是当日订单确认 |
| `claim_without_evidence` | 声明可贴但无独立来源；待核 |
| `consigned_only` | 仅 consigned/自备料路径，需确认工厂接受与入库 |
| `smt_status_unknown` | SMT 字段缺失/未知 |
| `no_smt_offer` | 没有匹配的 `jlc_smt` offer |
| `not_requested` | 需求未选择 SMT 渠道 |
| `not_applicable_tht` | THT/手焊行不走全自动 SMT 贴装 |

### 3.3 手焊/自备

`hand_solder.status`：`allowed_by_policy`、`allowed_with_difficulty`
（0402/1005 等手焊难度提示）、`not_recommended`（0201）、
`not_allowed_by_policy`、`not_required`（DNP）。手焊/自备路线单列，**不能**把
它当成“SMT 全自动完成”。

## 4. 装配方式与渠道可履约性

- `assembly=smt`：可走商城（自己/代焊）或 `jlc_smt`；若只允许 `jlc_smt` 且
  没有 SMT 证据，SMT 结论为 unknown，不伪造可贴。
- `assembly=tht|hand`：SMT 渠道不承接全自动贴装；若需求只给 `jlc_smt`，该行
  产生 `tht_not_supported_by_smt` 阻塞（`unsatisfied`），并单列手焊路线。
- `assembly=dnp`：不采购、不贴装，保留在需求报告里。
- 需求 `assembly_strategy=hand_solder` 时，SMT 渠道不参与该行采购；商城/手焊
  路线仍要求合格料与装配能力。

## 5. 费用：按渠道、按订单、显式来源

`fees[]` 中每条费用带 `channel`（或 `any`）与 `basis`：

- `shipping`：通常 `per_order`，可带免运门槛 `waiver.min_subtotal`；
- `tax`：`percent_of_subtotal` + `rate`，`tax_basis` 必须与商品口径匹配；
- `smt_extended_part_fee`：通常 `per_part`；
- `smt_board_fee` / `stencil`：通常 `per_board`；
- 未声明的运费、税费、SMT 费用一律进入 `fees.unknown`，即使已知商品小计存在也
  不改写成 0；受影响的预算状态为 `undetermined_unknowns`。
- 促销、账号优惠、固定免运、某版贴片费率都不默认成立；需要当前来源与
  `captured_at` 才会被当作已知。

## 6. 报告语义

- `supply.live_supply_query` 恒为 `NOT RUN`；`limits.simulated_data` 在选中
  订单含合成快照时为 true。
- `orders[]` 每行带 `channel`、`supplier`、`product_id`、`snapshot_id`、
  `snapshot_source`、`snapshot_truth`、`stock_pool`、库存扣减前后、交期性质。
- `strategy.channel_split` 只是“优先渠道 + 少拆单”的有界候选，不证明渠道更优；
  `known_cost` 也不跨渠道合成虚假总价。
- 商城 offer 的库存与 SMT offer 的库存永远不合并成一个大数字。

## 7. 未做与限制

- 不登录、不抓取商城、不调用任何未公开 API、不绕过 WAF。
- 不查实时库存/价格/MOQ/交期；这些字段只能来自输入快照。
- 不判断封装/钢网/供料方式是否被工厂实际接受；SMT 结论只是“字段 + 来源”
  级别。
- 不锁库存、不下单、不询价、不发邮件。
