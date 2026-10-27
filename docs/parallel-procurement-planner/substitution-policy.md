# 替代候选分级策略（substitution-policy/v1）

> 任务 H 只做“候选 + 风险分级”，不自动替换 BOM、不改工程、不改封装、不写
> EDA。即使所有已知字段兼容，也不输出“已验证直接替换”；
> `drop_in_verified` 恒为 `false`。真实来源样例见
> [source-register.md](source-register.md)。

## 1. 五个状态（只用这五个）

| 状态 | 含义 | 典型条件 |
|---|---|---|
| `exact_identity` | 候选与原始是同厂同 MPN 同一器件 | MPN、制造商、封装一致；仍不是采购/库存证据 |
| `evidence_supported_candidate` | 已知字段全部有来源且相容，pin/footprint/mode 证据齐全 | 仅表示“有证据的候选”，不是实物/EDA 已验证 |
| `requires_design_review` | 需要工程师核对/改设计后才能判断 | 引脚定义/封装/外围/模式不同，或关键字段/证据缺失 |
| `incompatible` | 已证实存在硬性不兼容 | 额定电压/容差/温度/输出级/标称值等硬条件不满足 |
| `insufficient_evidence` | 资料不足以形成可复核判断 | 被动件关键字段或来源缺失；器件族无法确定 |

判定顺序：先看硬性冲突（`incompatible`），再看资料不足，再看是否需要设计
评审；只有全部通过才可能 `evidence_supported_candidate`。`approval_scope` 与
状态是两件事：状态回答“证据到什么程度”，`approval_scope` 回答“允许用在哪
（采购/需设计评审/未批准）”。

## 2. 来源要求（每个参与比较的字段）

```json
"voltage_rating_v": {
  "document": "厂商数据手册标题",
  "revision": "文档版本/日期",
  "page": "页码",
  "table": "表号/章节/图号",
  "url": "https://厂商域名/...",
  "condition": "该值适用的电压/温度/测试条件",
  "accessed_at": "2026-10-27"
}
```

- 必须有 `document`、`revision`、`page`、`https://` URL；缺任何一项该字段视为
  无来源。
- `condition` 缺失不直接判错，但报告会保留为空，读者必须知道“值不等于在目标
  工况成立”。
- 分销商页面、搜索摘要、记忆值、库存/价格都不能作为原厂来源。
- 本仓库的 `source-register.md` 只登记本轮实际下载/读取的原厂文档；没有页码的
  HTML 规则页必须标“页码 unknown”，不能伪装成 PDF 正文。

## 3. 被动件比较（电阻/电容/电感）

| 字段 | 判据 |
|---|---|
| `component_kind` | 必须一致（capacitor/resistor/inductor） |
| 标称值 `capacitance_f`/`resistance_ohm`/`inductance_h` | 必须相同；不同值就是不同器件 |
| `tolerance_percent` | 候选容差不得宽于要求（更紧可接受） |
| `voltage_rating_v` | 候选必须 ≥ 要求/原值；更低是硬不兼容 |
| `power_rating_w` | 候选必须 ≥ 原值/要求（电阻等） |
| `package` / `footprint` | 必须一致；不同封装需要改 PCB/钢网 |
| 温度范围 | 候选范围必须覆盖要求范围；缺字段=资料不足 |
| `dielectric` | 要求介质时必须一致；X7R→X5R 即使容值/封装相同也不能默认等价 |
| `esr_max_ohm` / `frequency_limit_hz` | 应用有约束时必须满足；缺数据=资料不足 |

**反例规律：** “额定更高就一定等价”不成立。介质、偏压特性、ESR、频率特性、
封装尺寸都可能改变；高耐压但介质更差仍可能需要设计评审。

## 4. 有源件比较（至少覆盖一类，如比较器/LDO）

| 字段 | 判据 |
|---|---|
| `component_kind` / `function` | 必须一致；功能/拓扑不同直接淘汰 |
| `output_type` | 推挽 vs 开漏是不同输出级；用显式 family 比较，不按名称猜测 |
| 供电范围 `supply_min_v`/`supply_max_v` | 应用供电电压必须落在候选范围内 |
| 温度范围 | 候选必须覆盖应用范围 |
| `pin_count` / `pinout` | 脚数一致是最低要求；逐脚定义不同→需设计评审；只有同名同功能且有 pin_map 证据才可能候选 |
| `package` / 尺寸 | 不同封装/焊盘/散热需要改 PCB/钢网 |
| 时序/驱动/失调/静态电流/热 | 应用有约束时必须满足；关键条件缺失→需设计评审 |
| `external_networks` | 候选需要不同外围（上拉、补偿、限流）→需设计评审 |
| `mode`/配置 | 模式脚、shutdown、地址、增益等不同不能按采购换料 |

**字段缺失给 needs_review：** 有源件关键字段（pinout、Vos、Iq、tpd 条件、
封装尺寸等）缺失时，不会因为“同封装同名字”就判 `drop_in`；状态至少是
`requires_design_review`，证据接近空白时为 `insufficient_evidence`。

## 5. 证据门槛

- 被动件：比较字段 + 封装/footprint 证据。
- 有源件：比较字段 + `pin_map` + `footprint` + `mode` 三类证据。
- 任一证据缺失：`requires_design_review`（有源件）或
  `insufficient_evidence`（被动件关键字段/来源缺失）。
- 即使三类证据齐全、所有字段相容，也只输出 `evidence_supported_candidate`，
  且 `drop_in_verified=false`；不声称 EDA/封装/实物已验证。

## 6. 本轮两个真实来源样例（摘要）

| 样例 | 原始 → 候选 | 判级 | 理由摘要 |
|---|---|---|---|
| `PASS-001` | KEMET `C0603C104K5RACTU`（50 V X7R）→ `C0603C104K3RACTU`（25 V X7R） | `incompatible` | 同容值/容差/封装/介质，但额定电压 50 V→25 V 低于原设计硬上限；详见 source-register |
| `ACT-001` | TI `TLV3201AIDBVR` → ADI `ADCMP600BRJZ-R2` | `requires_design_review` | 供电/温度/脚数相容，但引脚名与功能集不同、静态电流相差约 75×、时序测试条件不同；不能当采购换料 |

两个样例都**不代表**当前有货、有价格或可直接替换；`source-register.md` 记录
文档版本、页码、表号、URL 与条件。

## 7. 与规划器的关系

- `plan` 的 `conservative_substitution` 策略只在原始 MPN 无法覆盖时，使用
  `exact_identity`/`evidence_supported_candidate` 的候选；`incompatible`/
  `requires_design_review`/`insufficient_evidence` 不会被自动采用。
- 替代采用会在订单上标 `substitution=true`、`alternate_id`、
  `alternate_grade`，并保留 `approval_scope`。
- 规划器不修改 BOM；替代是否批准、是否改图、是否重跑检查由工程流程决定。
- 替代候选的风险（需设计评审、来源缺失）不会被当作 0 成本/0 风险参与最低
  总成本排序。

## 8. 禁止事项

- 不因为库存有货就判可替代。
- 不把“同封装/同系列/平台匹配”当作等价证明。
- 不用分销商页面或价格/库存推断电气等价。
- 不自动改 BOM/封装/PCB/固件。
- 不把 `evidence_supported_candidate` 写成“已验证 drop-in”。
