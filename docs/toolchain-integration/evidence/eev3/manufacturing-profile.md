# 生产档案：zhigou-dual-button-led-eev3-final

> 按 `design-hardware/assets/manufacturing-profile.md` 填写。数据来自 eev3-final 工程的真实回读
> （2026-10-28，pcb drc / layout-lint / pcb check / BOM / 制造导出）。
> 规则边界与建议值分开记录；**不把推荐值当硬性放行，也不私自豁免**。

## 任务/渠道/版本

- 工程保存版本：`zhigou-dual-button-led-eev3-final`（uuid `f178aba5a861455b944edb9f8a1a1b65`），
  从 `eev3-before-dfm-fix.epro2` 恢复；PCB 文档 `56a25fb38c54cb1b`。
- 交付目标：单件样板（手焊自测），交付级别 = **PCB 候选（DRC 0）**。
- 渠道/服务：**嘉立创 PCB 打样（默认）+ 自行手焊**；未下 SMT 订单、未选拼板/工艺边。
- 规则查询日期：2026-10-28（skill `references/jlc-production.md` 的纪律执行；具体工艺数值
  按嘉立创当前页面核对为**待确认**，本档案不硬编码）
- 现有产物：`evidence/eev3/manufacturing/eev3-gerber.zip`（9 层 + PTH 钻孔）、`eev3-cpl.csv`（9 行）、
  `BOM-v3.csv`（6 行，含 C 号/型号/厂家）。

## 工艺选择与依据

| 对象 | 当前选择/候选及依据 | 来源/条件 | 已确认/候选/待确认 |
|---|---|---|---|
| 基材/层数/层叠与各层铜厚 | FR-4，2 层（TOP/BOTTOM），1 oz | `pcb.layers`=2；`pcb.pour.list`=2 层 GND 铺铜 | 已确认（按嘉立创标准档） |
| 板厚/尺寸/公差/表面处理/油墨 | 1.6 mm；**47.84 × 20.36 mm**（1883.5 × 801.7 mil）；HASL 无铅；绿油白字 | 板框实测：`outline.bbox` = -1293.448..590.0375 × -400.867..400.867 mil | 尺寸已实测；工艺档位**待按嘉立创页面确认** |
| 孔/槽/塞孔/盖帽/特殊工艺 | **2 个 PTH 插件孔**（J1 TH 排针，2 pad；`Drill_PTH_Through.DRL`）；**过孔 0**（`pcb.via.list` count=0）；无槽/塞孔 | 制造导出：`Drill_PTH_Through.DRL`；via.list=0 | 已确认 |
| 阻抗网络/层别/管控和报告 | 不适用 | 无高速/受控阻抗网络（两路 LED 指示） | 已确认 |
| 单/双面贴装与插件/后焊/回流 | 单面 TOP 贴装 8 件 + J1 插件（TH 直插，手焊/后焊） | BOM 9 件；J1 为 TH（HDR-TH_2P-P2.54-V-M-1） | 已确认 |
| 出货/拼板/工艺边/Mark/定位孔 | 单片交付，无拼板/工艺边/Mark/安装孔 | `requirements.enclosure_mounting=not_applicable` | 已确认 |
| 供料/包装/备损/MSL/清洗/测试 | 自购物料（6 行可下单）；不做 SMT 供料；无清洗；测试见 `test-plan.md`（NOT RUN） | BOM-v3.csv；库存已核 | 部分待人工执行 |

## 适用规则及实际落实

| 规则/实际对象 | 测量定义/单位/适用工艺 | 官方边界/建议及来源定位 | 本项目设计值/理由 | EDA字段与修改前后或人工复核方式 | 实际回读/文件检查/状态 |
|---|---|---|---|---|---|
| 最小线宽/间距 | mil；双面 1 oz 标准工艺 | 嘉立创标准常见 **6/6 mil**（**待按当前页面复核**） | 走线主要 10 mil；**layout-lint minGap = 5.98 mil**（D1 周边 `LED1_A × LED1_K`，D2 同模式） | `pcb drc` 规则 `lineClearance=0.254mm≈10mil`，**DRC 0 违规**；但 lint 以 6 mil 建议口径报 5.98 | **推荐值边界**：不违反本工程 DRC；严格按 ≥6 mil 建议**待人工微调**（不私自豁免，见冲突与例外） |
| 过孔孔径/环宽 | mm/mil | 标准档 | 无过孔（via.list=0） | 不适用 | 已确认 |
| 板框到铜距离 | mil | 建议 ≥20 mil | 铺铜内缩 20 mil（`pour-fit` 默认） | `pcb check` copperNearEdge=0 | 通过 |
| 阻焊开窗/丝印 | mm/mil | 标准 | J1 丝印已移回板内（`pcb silk-set`）；DFM silkOffBoard=0 | `pcb check` findings 无 silk-off-board | 通过 |
| 电源铺铜/线宽 | mil；1 oz 载流 | 建议电源铺铜而非细线 | +5V 无铺铜（4 pads）；+5V/GND 各 5 条 10 mil | `pcb check`：powerNotPoured=1、widthUnderSpec=2 | **WARN（未闭环）**：9–14 mA 级电流由 10 mil 走线承载，可按设计接受；若按 DFM 建议需加铺铜/加宽 |

## 冲突与例外

| 对象/冲突来源及条件 | 功能/成本/交期影响 | 当前处理/候选 | 厂方或项目依据/范围/版本 | 待复验与状态 |
|---|---|---|---|---|
| **5.98 mil 最小间距**（D1 周边 LED1_A/LED1_K） | 低于 6 mil 推荐值 0.02 mil；实际制造公差内通常可做 | 记录为**推荐值边界**，不按 DRC 违规处理；候选：人工挪 1–2 格到 ≥6 mil，或向嘉立创确认 5.98 mil 工艺档位 | 嘉立创标准工艺（待页面复核）；本工程 DRC 规则 10 mil 更严 | **待人工微调/厂方确认**；复验方式：调整后重跑 `pcb drc` + `layout-lint` |
| +5V 未铺铜、10 mil 电源线 | 电流 9–14 mA，压降可忽略；DFM 建议电源铺铜 | 保留（设计选择）；候选：`pour-fit --net +5V` 或加宽 | DFM 规范 §5.2（电源铺铜建议） | 待定（可不改） |
| J1 自动布线后逃逸线走向 | 全板重布替换原手工布线；电气正确（DRC 0） | 保留；制造前人工复核走线观感 | 项目决策（自动化优先） | 待人工复核 |

## 输出与状态

- **同版制造文件**：`eev3-gerber.zip`（9 层：GTL/GBL/GTO/GBO/GTS/GBS/GTP/GKO/GDL + GDD 钻孔图 + `Drill_PTH_Through.DRL`）、
  `eev3-cpl.csv`（9 行 × 18 列）、`BOM-v3.csv`（6 行，C 号/型号/厂家）。
- **EDA 规则回读**：`pcb drc` = passed，0 违规（`lineClearance` 0.254 mm ≈ 10 mil）；
  `layout-lint` score 76（minGap 5.98 mil、crossing 1、J1 outside-outline 属设计使然）；
  `pcb check` = 0 error / 3 WARN（powerNotPoured +5V、widthUnderSpec ×2）。
- **SMT/DFM 闭环**：未下 SMT；DFM 已复核（WARN 见上）；厂方生产稿/DFM 意见**未提交**。
- **报价/库存/订单**：BOM 6 行已核库存（C112291/C125205/C51933311/C845159/C49296724/C124375）；
  报价/订单**未进行**。
- **工厂检测/烧录/功能测试**：未购买、未执行（实物 V2–V11 全部 NOT RUN）。
- **仍阻碍制造**：5.98 mil 推荐值边界待处理（微调或厂方确认）；+5V 铺铜/线宽为可选 WARN；
  人工走线复核、实物验证未做。
- **变更触发**：任何走线/规则调整后需重跑 `pcb drc` + `layout-lint` + `pcb check` 并重导制造文件。

> 结论只限实际完成范围；本档案不构成放行/下单/量产结论。
