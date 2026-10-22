# 第 4 轮交付报告：复杂设计中的工程决策能力

日期：2026-10-22。仓库：`zsx3896926/hardware-design-skill`。分支：`feat/engineering-decisions-round4`；PR 分支从 `origin/main` `0fe5cf8` 拉出，只含本轮决策资产。

## 1. 十二个工作包状态

| 包 | 状态 | 交付 | 主要缺口 |
|---|---|---|---|
| A 架构方案比较与决策记录 | DONE | `a01-architecture-decision.md`、A01/A02 案例、共享决策记录模板 | 备选成本数据仍待用户/供应链输入 |
| B 主控引脚与外设资源 | DONE | `b01-pin-resource-planning.md`、pin-plan 模板/示例、B01 案例、`pin_plan_check.py` | ESP32-C3 物理脚/pinmux/ADC/封装 NC 待查 |
| C 工作状态与转换 | DONE | `c01-state-transition-contract.md`、状态模板/示例、C01 案例 | POR/BOR、总线释放、部分供电实测 NOT RUN |
| D 参数容差与最坏情况 | DONE | `d01-tolerance-and-worst-case.md`、容差模板、D01 案例、P02 §4.4 复算 | 实际 ADC/基准/运放与温度数据待查 |
| E 跨模块接口契约 | DONE | `e01-interface-contract.md`、接口模板/示例、E01 案例、`interface_contract_check.py` | 连接器额定、配对件、门限保证值待查 |
| F 线束、连接器与板外系统 | DONE | `f01-harness-and-board-external.md`、线束模板/示例、F01 案例、`harness_check.py` | 无连接器原厂图纸、压接/拉脱/整机实测 |
| G 产品型号与装配变体 | DONE | `g01-product-variants.md`、变体模板/示例、G01 案例、`variant_bom.py` | P5 为 constructed；无真实 MPN/C 号/价格/库存 |
| H 校准、配置与设备身份 | DONE | `h01-calibration-and-identity.md`、校准模板/示例、H01 案例、`decision_record_check.py` | 无校准源、恒温箱、序列号、存储耐久 |
| I 工程变更与影响分析 | DONE | `i01-change-impact.md`、变更/影响图模板与示例、I01 案例 | 无真实出货批次/after 快照；F1 只作基线 |
| J 有依据的电路模块复用 | DONE | `j01-module-reuse.md`、复用合同模板/示例、J01 案例 | BQ24074 对 4.20 V 电芯判 rejected；替代型号待查 |
| K 受控设计实验与优化 | DONE | `k01-controlled-experiment.md`、实验模板、K01 案例、复算 JSON | 无 bench/SPICE/实测；只到 model-consistent |
| L 工程资产检索与有效性 | DONE | `l01-asset-validity.md`、资产索引模板/示例、L01 案例、`decision_asset_check.py` | EOL/PCN/许可、原厂最终裁决待查 |

全部案例：`E3 / OFFLINE_PLANNING / hardware_execution: NOT RUN`。没有 EDA 回读、打板、样机或实测。

## 2. 新增能力与触发条件

- **决策深度门**：D0 不建记录；D1 只记一个不可逆决定；D2 才启用备选比较与完整包。12 个包各自写触发/跳过条件，简单项目不被迫填 12 张表。
- **可执行检查**：6 个脚本分别检查引脚资源冲突、接口契约字段、线束包、变体 BOM 闭包、校准/变更记录、资产索引。缺字段输出 `unknown`，不输出“通过”。
- **案例分析而非百科**：13 个案例覆盖六个验证载体（P1–P6），每个案例有初始错误决定、判定依据、修正决定、代价、停止条件与复评触发。
- **五类记录**：被推翻假设、保留未知、需求变化跨模块更新、纯局部变更、拒绝复用；每类有 owner case 与实质字段。
- **任务路由**：SKILL.md §3 增加 5 行入口，§3.1 写决策库边界，§6 写 6 个脚本；`decisions/README.md` 是唯一索引。

## 3. 与旧内容的去重

| 现有内容 | 已有职责 | 本轮只补 |
|---|---|---|
| `module-integration.md` | 12 条接口判据、组合失败、状态快照 | 一条接口一行、状态×接口矩阵、stale |
| `project-coherence.md` | 变更传播表、版本对应 | 有向影响图、闭包、旧件失效状态 |
| `part-selection.md` | DNP/变体原则 | 双销售配置闭包、变体 BOM 生成、防混料 |
| `calculations/` | 公式、假设、算例、不能证明 | 跨电路逐项预算、角点决策、主导项动作 |
| `design-cards/` | 60 张拓扑/参数/逐脚卡 | 不改卡；J 只给 opt-in 复用合同 |
| `projects/` | 4 个项目样本 | 在 P01/P02 事实上做决策对照，不改项目文件 |
| `failures/` | 33 个故障案例 | 只引用判据，不复制故障叙事 |
| `manufacturing-routes.md` | 变体表、线束表、制造路线 | 线束包受控字段、变体闭包与生成规则 |

没有新增 SC/PL/RT/MF/DM 编号，没有改 60 张卡、35 个场景或 4 个项目样本。

## 4. 专项案例与证据入口

| 项目 | 案例 | 证据入口 |
|---|---|---|
| R4-P1 多外设主控板 | A02、B01 | `references/decisions/cases/r4-case-a02-*.md`、`r4-case-b01-*.md` |
| R4-P2 电池+外电共存 | A01、C01、J01 | `r4-case-a01-*.md`、`c01-*.md`、`j01-*.md` |
| R4-P3 测量采集 | D01、H01、K01 | `r4-case-d01-*.md`、`h01-*.md`、`k01-*.md` |
| R4-P4 多板控制 | E01、F01 | `r4-case-e01-*.md`、`f01-*.md` |
| R4-P5 双销售配置 | G01 | `r4-case-g01-*.md`（constructed） |
| R4-P6 旧版改型 | I01、L01 | `r4-case-i01-*.md`、`l01-*.md` |

索引：`design-hardware/references/decisions/README.md`；族谱与 canonical facts：`design-hardware/references/decisions/cases/README.md`。

## 5. 计算、工具与人工复核

- **P02 §4.4 复算**：`adc-settle.r4p3.recompute.json` 用两节点 RC 闭式解重算。
  - 直接不进缓冲：单极点代理 3905.53 LSB（复现 P02 表），两节点 3740.25 LSB；两者都失败，结论不变。
  - 缓冲 + 1 nF：单极点 0.5239 LSB，两节点约 2.27e-36 LSB；“临界失败”是代理模型结论，不能当物理事实。
  - 470 pF/10 µs：两节点约 4.26e-80 LSB；仍只是模型，不是实测。
- **D01 容差预算**：共用基准、两通道串扰、校准残差、温度场相关组分别列出；角点给出 23.05/63.05/32.05/108.05 µA，并给主导项→动作。
- **脚本实跑**：6 个脚本均输出单 JSON、退出码 0/1/2、`board_verified:false`；正常与非法输入均有测试。
- **测试**：全量 **434 tests OK**；其中工作流决策测试 271、集成索引 13、CE 文档测试 2；其余为既有测试。所有决策测试的期望值来自手写 fixture、独立公式或独立实现，不用被测脚本生成期望。
- **人工复核**：终审逐项检查 12 参考/13 案例/14 模板/6 脚本/6 测试、五个 record owner、191 条完整路径锚点、25 个 Markdown 相对链接与 25 个来源 ID；未发现未登记来源、假 C 号或 `[TODO`。

## 6. 未知参数与未执行项

- 全部案例仍是纸面规划：无 EDA 回读、打板、贴片、样机、校准、线束压接、整机或 EMC 实测。
- ESP32-C3 物理脚/pinmux/ADC 限制/封装 NC；J1/J2 连接器 MPN、每针额定、配对端子、压接工具；线束长度/线规/屏蔽。
- BQ24074 θJA、KILIM/KISET/KITERM 常数、NTC 曲线、具体后缀；P01 4.2 V 电芯与 4.23 V max 的兼容性未解决。
- P02 实际 ADC/基准/运放、Csh/Rsw、校准源不确定度、恒温箱、老化/温漂；校准记录 `CAL-P3-001` 是结构示例，`status=uncalibrated`。
- P02 V1.1 的 MCU/Flash/EEPROM 型号、隔离器/隔离电源、隔离耐压、批次/序列号；F1 重排的 after 快照未产生。
- 变体的 MPN/C 号/价格/库存/MOQ/包装/交期/可贴状态；P5 是 constructed，不是真实双销售产品。
- 资产 EOL/PCN/许可、PWR-S01/PWR-S11 的原厂最终日期、PWR-S05 正文。

## 7. 修正过的错误假设

1. **BQ24074 终止电压不是三档可选**：4.16/4.20/4.23 V 是同一固定调节的 min/typ/max。A01/J01 原先“锁定 4.20 V 档”被推翻；对 4.20 V 电芯，4.23 V max 已超出，判 rejected，除非电芯/保护板书面确认允许 ≥4.23 V。
2. **P01 的 25 块是计划/路线选择，不是已走 SMT 的事实**：P01 的制造状态是 NOT RUN；A01/J01 已改为“计划首发 25 块、选择路线 B”。
3. **P02 §4.4 的 0.524 LSB 是单极点代理值**：两节点闭式解约 2.27e-36 LSB；“1 nF 临界失败”不能作为物理结论沿用；470 pF 的选择仍是保守设计，不是实测。
4. **A02 的过度设计门推翻了“新增状态 LED/第二串口都该进首版”**：两项被拒绝或延后，B01 的 pin-plan 把候选与已分配分开，不再把被拒资源计入 `resources`。
5. **J01 的“充电块整体可复用”被拆开**：BQ24074 子块 rejected，TPS63802 子块 accepted-with-conditions；不再用单一结论概括整块。

## 8. 新手负担是否增加

没有增加。决策记录由 Agent 创建和维护，模板头部明确“Agent 填写，用户不填”；案例第 5 节只给用户三行：决定、代价、下一个检查或待查。D0/D1/D2 深度门让简单项目跳过完整包；SKILL 不要求用户先选择深度或填 12 张表。

## 9. 工程师接手是否更方便

更方便，但边界更清楚：

- 一个入口 `references/decisions/README.md` 能查到 12 包、13 案例、14 模板、6 脚本、D0/D1/D2 与分工。
- 每个案例有 canonical facts、初始错误决定、判定依据、修正决定、代价、停止条件与复评触发；比只给结论更容易复核。
- 每个脚本只做结构/记录检查，明确写 `board_verified:false` 与 `not_checked`；不会把退出码 0 当成电气通过。
- 与现有 module-integration、project-coherence、part-selection、calculations、manufacturing-routes 的分工写在索引与各参考 §9，减少同义文档。

## 10. 后续维护与接续

- 新增/修改决策资产必须同时更新 `decisions/README.md` 与 `cases/README.md`；未登记资产不得标 `active`。
- 来源只用 `source-register.md` 已登记 ID；许可不明、EOL/PCN 未核、旧项目未验证、来源未登记时，状态只能 `conditional`/`blocked`/`planned`。
- 同一对象、同一参数、同一条件、不同值才是冲突；版本/范围差异记 `applicability-only`。索引自检命令见 `decisions/README.md` §8。
- 共享 `decision-record.template.md` 的 schema 由集成人统一改；各工作流只提交变更请求。
- 下一轮优先补真实器件手册与一次 EDA 回读，把接口/资源表与真实网表对账；仍未覆盖 PCB、制造、校准、线束与样机。
- 并发提示：本轮开工时共享检出被另一会话切到 `feat/common-hardware-coverage`；本轮已隔离到独立 worktree，未触碰另一会话文件。后续同一机器多会话时应各自使用独立 worktree，避免分支/工作区混写。
