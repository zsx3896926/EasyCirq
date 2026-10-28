# 物料核对清单（G6 待办，本轮 NOT RUN）

> 规则：不脚本直连未获官方支持的商城接口、不伪造查询时间。`sourcing.stock_checked_at`
> 保持空 → gate `sourcing_check` 为 fail，这是**如实**状态，不是遗漏。

| 位号 | C 号 | 需核对字段 | 商城入口 | 查询时间 | 结果 |
|---|---|---|---|---|---|
| J1 | C9900024210 | 库存/价格/MOQ/封装一致性 | 立创商城搜 C9900024210 | 未查 | NOT RUN |
| F1 | C9900012139 | 同上 | C9900012139 | 未查 | NOT RUN |
| C1 | C9900013340 | 同上 | C9900013340 | 未查 | NOT RUN |
| R1/R2 | C2889365 | 同上（220Ω 0402） | C2889365 | 未查 | NOT RUN |
| D1/D2 | C28105 | 同上（LED 0805） | C28105 | 未查 | NOT RUN |
| SW1/SW2 | C9900015641 | 同上 | C9900015641 | 未查 | NOT RUN |

**注意**：`C9900xxx` 为系统库内部编号，不是商城订货号；核对时应按"器件名+封装+参数"在商城
检索对应商品，或替换为有明确 C 号的器件后再核。查到后把时间写入
`design-state.sourcing.stock_checked_at`（ISO 时间）与每行结果。

## 2026-10-28 编号有效性探测（真实结果）

| 位号 | C 号 | 商品页 | 结论 |
|---|---|---|---|
| R1,R2 | C2889365 | 存在：`0402 ±5% 220Ω | Chip Resistor | VO` | 真实商城编号，规格与 BOM 一致 |
| D1,D2 | C28105 | **Page Not Found** | 不是商城订货号（系统库内部编号） |
| C1 | C9900013340 | **Page Not Found** | 同上 |
| F1 | C9900012139 | **Page Not Found** | 同上 |
| J1 | C9900024210 | **Page Not Found** | 同上 |
| SW1,SW2 | C9900015641 | **Page Not Found** | 同上 |

探测方式：直接 GET `https://www.lcsc.com/product-detail/<C>.html` 并读 `<title>`；原始记录
`evidence/gates/sourcing-probe.json`。

**因此**：6 行里只有 1 行有真实订货号；其余 5 行必须先替换为真实商城料号，才谈得上核对库存/价格。
库存/价格本身仍 **NOT RUN**（页面为 JS 渲染，未取到数字；不填写 `stock_checked_at`）。

## 2026-10-28 12:40 实际核对结果（LCSC 商品页 JSON-LD/内嵌 state）

| 位号 | C 号 | 结论 | 详情 |
|---|---|---|---|
| R1,R2 | C2889365 | orderable code but OUT OF STOCK; min packet 10000 | 库存 0；OutOfStock；最小包装 10000；价格 $0.00 |
| D1,D2 | C28105 | no LCSC order code (Page Not Found) -> replace the part number | — |
| C1 | C9900013340 | no LCSC order code (Page Not Found) -> replace the part number | — |
| F1 | C9900012139 | no LCSC order code (Page Not Found) -> replace the part number | — |
| J1 | C9900024210 | no LCSC order code (Page Not Found) -> replace the part number | — |
| SW1,SW2 | C9900015641 | no LCSC order code (Page Not Found) -> replace the part number | — |

**核对结论：当前 BOM 不能直接下单** —— R1/R2 的 C2889365 库存 0（最小包装 10000）；其余 5 行在商城 Page Not Found（系统库内部编号，没有订货号）。需要先换料再核。
证据：`evidence/gates/sourcing-check.json`（逐行 URL/库存/价格/判断）。