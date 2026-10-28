# 产品变体矩阵模板（Agent 填写，用户不填）

> 用途：以 `easycirq/references/manufacturing-routes.md` 的 §2.4 与 §9.4 变体表为唯一权威，本模板只补 requires/conflicts/forbidden 闭包、机器可检字段与每变体差异；未知写“待查”。

## 1. 变体头

| variant | 类型（G1） | boards | attrition_rate | min_spare | 装配状态 | 订单标识 |
|---|---|---|---|---|---|---|
| V1 | 装配变体 | 待查 | 0.05 | 2 | planned | 板/盒/订单写 V1 |

类型只取：装配变体、销售配置、固件配置、包装配置；一个变体可以同时属于多类，但必须逐类写清。

## 2. 闭包字段

| variant | requires | conflicts | forbidden | dnp |
|---|---|---|---|---|
| V1 | [K1, Q1, J3] | [[K1, Q2]] | [Q2, Rg, TVS] | [Q2, Rg, TVS] |

规则：requires 做传递闭包；conflicts 是互斥对，两侧同时在闭包即拒绝；forbidden 是闭包中出现即拒绝；dnp 与 requires 不得相交；同一 exclusive_group 不得有两件同时进闭包。

## 3. 装配与差异

| variant | 装 | 不装（DNP） | 依赖 | BOM/CPL | 固件配置 | 丝印/程序 | 测试差异 | 采购量差异 |
|---|---|---|---|---|---|---|---|---|
| V1 | （位号） | （位号） | （requires） | V1 BOM + V1 CPL | （配置） | （标识） | （测试项） | 按本变体 needed 单独算 |

## 4. master BOM 到变体 BOM

```text
base   = per_board × boards
spare  = max(ceil(attrition_rate × base), min_spare)
needed = base + spare
order_qty = ceil(needed / package_step) × package_step   # 仅当步进已核
```

包装步进未知时省略 `order_qty`，写 `order_qty_status:"待查"`；不得填入虚构的 MOQ、价格、库存或包装数。

## 5. 非法组合（必须拒绝）

- required 与 forbidden 相交，或 dnp 与 required 相交。
- 同一 exclusive_group 两件同时进闭包，或 conflict 两侧同时在闭包。
- 用“默认版”代替 variant ID，或 variant ID 不出现在订单、包装标签、固件版本与验收记录中。
- 一个位号同时列两个待选件；替代候选必须与最终装配清单分开。

## 6. 脚本与边界

- `python easycirq/scripts/variant_bom.py <变体包.json>`：只生成 needed 与闭包检查，不判断可贴、不查库存、不报价。
- exit 0 只表示闭包自洽；混料风险、DNP/CPL 与实物一致性仍未核，写入 not_checked。
