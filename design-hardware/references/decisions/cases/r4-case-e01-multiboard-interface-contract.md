---
id: R4-CASE-E01
project: R4-P4
family: P02
parent: P02
facts_source: design-hardware/references/module-integration.md
packages: [E]
title: 三块板控制系统的接口契约
evidence: E3
execution: OFFLINE_PLANNING
hardware_execution: NOT RUN
last_reviewed: 2026-10-22
sources: [IF-S01, IF-S02, IF-S03, IF-S06, IF-S11, IF-S12, PWR-S06, PWR-S07, MCU-S09, D-S08]
record_types: [interface-contract, unknown-retained]
---
# 三块板控制系统的接口契约
> 完成级别：纸面接口契约。J1 十条接口一行已建，J2 因无引脚表未建行；未做 EDA/实测，连接器 MPN/额定/配对/压接全部待查。
## 1. 触发与用户任务
R4-P4 是 P02 派生的三块板控制系统：控制板 A、I/O 板 B、电源板 C。用户要求“把 A–B 排线接口冻结，A–C 电源接口一起定”。A–B 以 `design-hardware/references/module-integration.md:698-711` 的 10-pin J1 为纸面起点；A–C 没有仓库引脚表。
## 2. 产品与真实材料
- 仓库事实：J1 10-pin 表（`design-hardware/references/module-integration.md:698-711`）与 12 条纸面核对（`:713-729`）；C04 的 EN 浮空结论（`:424-432`）；状态表（`:156-170`）。
- 构造事实：三块板划分、J2/J3 的连接器号与网络、整机线束包是 R4-P4 假设（E3），仓库无对应引脚表；不得把它们写成已核对。
- 未知：J1/J2 的 MPN、每针额定、配对端子、压接工具、高度/锁扣；U2 地址与驱动；Q1 的 Ioff；板版 ID；BOM/CPL/变体。本轮未重开原厂正文。
## 3. 初始决定（错在哪）
1. 把 §17.3 的 12 行整表当“整个系统通过”，没有落到每条接口。错在一条接口可能同时违反多条，整表通过不能说明哪根线安全。
2. 把 I2C 的“同域 CMOS”当门限通过。错在开漏上升沿、上拉所有权与总线电容没有逐行写。
3. SPARE 双向、默认高阻，没写谁驱动、何时释放。错在多驱动没有仲裁。
4. 3V3_SW 是负载开关可关断轨，没写 off_behavior。错在 Q1 关断后 B 的输入是否经 ESD 二极管从 A 取电未定义。
5. 把 J1 当“内部排线，不会热插拔”而不写插合序列。错在装配/维修时仍可能带电插拔；没有连接器长短针证据就不成立。
## 4. 判定依据（path:start-end）
- `design-hardware/references/module-integration.md:698-711`：J1 十条网络的器件.脚、方向、电压域与备注。
- 同文件 `:713-729`：12 条纸面核对，第 3、6 条明确状态与反灌待查。
- 同文件 `:424-432`：C04，B 复位时 GPIO 高阻，A 的 EN 浮空。
- 同文件 `:156-170`：状态表，A 复位/断电/掉电都要求列出总线状态。
- 同文件 `:51-68`：12 条契约的判据与阻断条件；本文只落字段，不重写。
- 同文件 `:575-598`：换连接器/换料的 1/2/3/4 类分级。
## 5. 修正后的决定、代价与三行用户可见摘要
修正决定：J1 十条接口一行（示例 JSON）；8 行有 finding（8 行 unknown、2 行 blocking，SPARE 与 3V3_SW 兼有），2 行字段齐全但仍不代表电气通过；J2 不建行，列入 unresolved；没有一行写“通过”。SENSOR_ALERT 复用 C01 的状态×接口矩阵，写 A/B 复位与断电四态；A 的 GPIO5 必须有本地上拉/串联限流，B 在自身断电时不得驱动（待查）。
- 决定：接口按一行一网络记录；多驱动/可关断轨/用户插拔三项缺证据即 blocking；连接器额定与配对件未核前不冻结脚序。
- 代价：J1/J2 选型与板级冻结延后；SPARE 需定义仲裁或改单向；3V3_SW 需补 Q1 Ioff/串阻或改理想二极管；A–C 接口需补引脚表。
- 下一个检查或待查：J1/J2 MPN、每针额定、配对端子、压接工具；U2 ALERT 在 A 复位/断电时的状态；Q1 Ioff；SPARE 仲裁；U2 地址。
## 6. 记录类型与 typed block
### interface-contract
```json
{"record_type":"interface-contract","connector":"J1","interfaces":10,"blocking":2,"unknown":36,"rows_with_findings":8,"basis":"design-hardware/references/module-integration.md:698-711","stale":false}
```
### unknown-retained
- J2 无引脚表、连接器额定/配对/压接未知、Q1 Ioff 未知；缺任一项不得冻结 A–C 接口或下单。
## 7. 验证与证据状态
- 已执行：`python design-hardware/scripts/interface_contract_check.py design-hardware/assets/decisions/interface-contract.r4p4.example.json`；输出 10 条接口、blocking 2、unknown 36（含 6 条 unresolved 汇总），退出码 1。
- 未执行：连接器插拔/通断、门限测量、反灌、总线释放、热插拔、整机线束；均 NOT RUN。
- 不能证明：接口电气安全、连接器额定、配对/压接、固件方向控制；脚本通过不等于接口通过。
## 8. 未知、停止与重评
- 未知：J1/J2 全部采购/额定字段、U2 地址/驱动、Q1 Ioff、板版 ID、BOM/CPL/变体、整机线束长度/线规。
- 停止：多驱动无仲裁、可关断轨无 off_behavior、用户插拔无序列、连接器额定未知时，不得冻结脚序、下单或写“接口通过”。
- 重评：换连接器/线束、换料/换封装、电源树/负载变化、固件引脚/状态变化、新增变体/DNP、`module-integration.md` 行号漂移。
## 9. 与现有资产分工
- 接口方法与字段见 [`e01-interface-contract.md`](../e01-interface-contract.md)；本文只做 R4-P4 案例。
- 12 条与 J1 表见 `design-hardware/references/module-integration.md:51-68`、`:698-711`、`:713-729`；本文不重写。
- 状态×接口矩阵回链 [`r4-case-c01-battery-plus-external-supply-states.md`](r4-case-c01-battery-plus-external-supply-states.md)；本文不新增 C 案例。
- 变更分级见 `design-hardware/references/module-integration.md:575-598`；连接器/线束细目见 `design-hardware/references/manufacturing-routes.md:124-170`。
