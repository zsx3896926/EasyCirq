# 集成建议（只写接口，不修改其他任务）

> 本文件向任务 A/C/F 与后续开发者说明“如何把采购规划器接进现有链路”。
> 任务 H 没有修改 `SKILL.md`、已有 references、runtime/connector/protocol、
> CI、顶层依赖或其他任务目录；以下均为建议，不是已实施的公共变更。

## 1. 任务 A（工具链整合）如何把 BOM 传进来

### 1.1 推荐路径：A 统一导出 `procurement-input/v1`

A 的 BOM/工程导出步骤应输出一个不可变快照，再由规划器读取：

```json
{
  "schema": "procurement-input/v1",
  "project": {
    "name": "<project>",
    "bom_revision": "<BOM/工程 revision>",
    "bom_source_sha256": "<导出 BOM 文件 sha256>",
    "board_quantity": 10
  },
  "bom": {
    "revision": "<same>",
    "source": "<A 导出器名称/版本>",
    "rows": [{"line_id": "...", "designators": ["R1"],
              "qty_per_board": 1, "mpn": "...",
              "manufacturer": "...", "supply_ids": {"lcsc": "C123"},
              "footprint": "...", "assembly": "smt", "dnp": false,
              "identity_source": {"kind": "official_export",
                                   "source": "<A tool>", "captured_at": "..."}}]
  },
  "demand": {}, "offers": [], "supply_snapshots": [], "fees": []
}
```

约束：

- A 负责把 EDA/BOM 导出为**位号组 + 每板数量 + 完整 MPN/封装 + 装配方式 +
  DNP**；规划器不解析 EDA 原生文件。
- A 必须给 BOM 源哈希与 revision；规划器会计算 `bom_source_sha256_computed`
  并在声明值不一致时 blocking。
- A 不应把 C 号/价格/库存“富化结果”当设计身份；规划器把 `supply_ids` 当
  采购身份、`mpn`/`footprint` 当器件身份，二者冲突会拒绝匹配。
- 如果 A 只能输出 CSV，使用本任务的显式 `--column-map`（见
  [contract.md](contract.md) §5），不要新增“按表头猜列”的公共解析器。
- A 不需要 import 本包；CLI 子进程是稳定边界。

### 1.2 读取规划器结果的只读接口

- 只读 `plan.json` 的 `status`、`plan.lines`、`plan.orders`、`plan.fees`、
  `comparison`、`blockers`、`unknowns`、`limits`。
- 不要把 `planned_with_evidence` 当“可下单/已锁库存”；也不要把规划器
  `procurement.csv` 当正式采购订单或制造 BOM。
- A 的 UI/报告层可展示 `preferred_strategy`，但必须同时展示未知项与
  `not_checked`。

## 2. 真实供应查询应由官方/授权数据适配提供

首期完全离线；未来若要接真实数据，建议新增独立适配层（不在本任务范围）：

```
official/authorized supply adapter
  -> offers[] + supply_snapshots[] (+ fees[]/fx_rates[])
  -> procurement_planner plan --input snapshot.json
```

适配层必须提供：

- `snapshot_id/source/declared_truth/captured_at/valid_until/channel/sha256`；
- offer 的 `supplier/channel/product_id/mpn/footprint/currency/tax_basis/
  price_mode/price_tiers/price_unit/moq/mpq/stock/lead_time/smt`；
- 价格档的查询条件、税口径、包装单位；SMT 基础/扩展库状态与服务费的独立
  来源；
- 查询失败/截断/缺字段必须显式写入 `unknown` 或缺失字段，不能填 0/猜测；
- 只有官方导出/授权 API 才可以声明 `live_supply_query=true`；本工具仍然只做
  “快照规划”，不负责登录、购物车、询价、下单或锁库存。

不建议：页面抓取、绕过 WAF、未公开接口、把搜索摘要/缓存当实时库存。

## 3. 任务 F（参数化电路生成）如何约束替代

F 生成的“参数要求”可以直接映射为替代候选的 `application.requirements`：

| F 的电路参数 | 规划器字段（示例） |
|---|---|
| 电阻/电容值、精度 | `resistance_ohm`/`capacitance_f`、`tolerance_percent` |
| 工作电压/耐压 | `voltage_rating_v`、`supply_voltage_v` |
| 功率/电流 | `power_rating_w`、`drive_current_ma`、`supply_current_ua` |
| 封装/引脚数 | `package`、`pin_count`、`pinout_equivalence_required` |
| 工作温度 | `temperature_min_c`/`temperature_max_c` |
| 介质/ESR/频率 | `dielectric`、`esr_max_ohm`、`frequency_hz` |
| 外部网络（上拉/补偿/限流） | `external_networks` |
| 比较器输出级/时序 | `output_type`、`propagation_delay_max_ns` |

约束：

- F 生成的是“设计要求”，不是“已批准替代”；规划器只判证据等级，不选型、
  不写回 F 的生成参数。
- 如果 F 的参数变化会改外围/引脚/封装，替代状态应至少
  `requires_design_review`；规划器不会自动采用这类候选。
- F 不应依赖本任务未合入的代码；接口通过 JSON 文件/CLI 交互，可独立运行。

## 4. 任务 C（制造交付审计）如何只读引用

- C 的 BOM/CPL 一致性审计继续以制造 BOM/坐标为准；采购计划是**另一份**
  决策文档，不能替代制造 BOM，也不证明 BOM/CPL 一致。
- C 可以只读 `plan.json` 的 `demand`/`orders`/`unknowns`，用于核对：
  - DNP 行是否被错误计入采购；
  - 采购数量是否按位号组/批量/备损展开；
  - 缺料/未知项是否在交付报告中保留。
- 采购计划里的 `status` 不是制造放行状态；`limits.not_order`/
  `not_live_quote` 必须保留。
- 不要把 `procurement.csv` 当 CPL/贴片坐标文件，也不要把商城 C 号当
  EDA/PCB 封装身份。

## 5. 公共修改建议（未执行，见 issue-candidates.md）

- `SKILL.md`：在“商城配单/采购”入口增加本规划器的一句话导航与命令示例。
- `easycirq/references/lcsc-sourcing.md` 或 `selection/`：指向本任务的
  `docs/parallel-procurement-planner/contract.md`，避免重复写采购算法。
- 文档索引/README：登记本任务 docs 目录；是否纳入需维护者决定。
- `.gitattributes`：如维护者希望本目录强制 LF，可新增一条（本任务未改）。
- CI：现有 `python3 -m unittest discover -s tests -v` 会递归发现
  `tests/procurement_planner/`，无需改 CI；是否增加独立 benchmark job 由
  维护者决定。
- 版本号/CHANGELOG/主 handoff：按发布流程由维护者统一处理，本任务不改。

## 6. 边界

- 本任务不等待 A/C/F 的未合入提交；规划器可独立运行。
- 本任务不把其他任务的目录/代码作为依赖。
- 集成时如需公共修改，先按 `issue-candidates.md` 提单，不在本分支越界修改。
