# 工程内容扩充报告（2026-10-20）

> 本文件面向 PR 评审者，说明本轮新增了什么、改了什么、证据在哪、哪些没有验证。不是营销页，也不把文档数量当成硬件验证。

## 1. 结论摘要

- 在保留原有新手交互、工程师工作方式、嘉立创生态衔接、190 条检查提示和 4 个离线脚本的基础上，新增 60 张可复用电路设计卡、12 组原理图/PCB 局部范例、22 个证据分级故障案例、选型/替代资料、带条件计算手册、仿真与测量方法、3 条制造交付路线、3 个完整项目样本、35 个任务场景（含任务书指定的 12 个反例）。
- 新增 5 个可执行计算模式（Buck/Boost/ADC 建立/电流采样/PCB 载流）和 1 个可执行 RC 采样网络数值仿真；SPICE 计划文件明确标注 `NOT RUN`。
- 现有 `module-cards.md` 改为“组合检查入口”，详细内容移到设计卡，避免同义重复；`power.md`、`digital.md`、`analog-rf-highspeed.md` 保留为领域摘要并链接到卡片。
- 没有执行真实 EDA 绘图、导图、DRC、制造、SMT、烧录或样机实测；没有取得立创商城实时 C 号/价格/库存/MOQ/交期/SMT 可贴状态。相关结论保持 `未执行/待查`。

## 2. 新增内容索引与数量

| 内容 | 数量 | 位置 | 结构/验收 |
|---|---:|---|---|
| 设计卡 | 60 | `design-hardware/references/design-cards/` | 6 个领域，每张 12 节；E1/E2/E3 证据等级 |
| 原理图/PCB 范例 | 12 | `design-hardware/references/examples/` | 8 节 + 改前改后说明；标注“未在 EDA 中执行” |
| 故障与反例 | 22 | `design-hardware/references/failures/` | 现象→工况→假设→区分检查→根因证据→修复→复验→边界；A/B/C/D 证据等级 |
| 模块组合与接口契约 | 1 份 + 12 个组合失败案例 | `design-hardware/references/module-integration.md` | 电压/门限/状态/复用/连接器/电源/地/固件/机械 |
| 器件选型与替代 | 6 份 | `design-hardware/references/selection/` | 4 类器件表 + 4 级替代分类 + 商城核对 |
| 计算手册 | 4 份 | `design-hardware/references/calculations/` | 模型假设、公式/单位、算例、不能证明 |
| 仿真与测量 | 1 份 | `design-hardware/references/simulation-measurement.md` | 测点/仪器/探头/带宽/停止条件/安全 |
| 制造与交付 | 3 条路线 | `design-hardware/references/manufacturing-routes.md` | 文件/字段/变体/对账/异常处理 |
| 项目样本 | 3 个 | `design-hardware/references/projects/` | 11 节；完成级别如实标注 |
| 任务场景 | 35 个（12 个指定反例） | `design-hardware/assets/scenarios.json`、`references/task-scenarios.md` | 路由/必做/禁止宣称/确定性检查 |
| 来源登记 | 91 条 | `design-hardware/references/source-register.md` | 版本/页码/查阅范围/不能推广 |
| 可执行脚本 | +5 模式 +1 仿真 | `design-hardware/scripts/calculate.py`、`rc_settle_sim.py` | 单元测试覆盖正常/边界/无效输入 |

## 3. 合并、修正与删除

| 对象 | 处理 | 原因 |
|---|---|---|
| `references/module-cards.md` | 重写为 10 类组合入口 + 设计卡链接 | 原文与新增卡片重复；保留“构成/核算/失效与 PCB”三条组合提示 |
| `references/power.md`、`digital.md`、`analog-rf-highspeed.md` | 保留摘要，顶部加设计卡入口 | 避免同一公式/拓扑在两处出现不同版本 |
| `references/design-experience.md` | 保留 P01–P09/G01–G09/T01/M01–M02，新增来源登记入口 | 早期样本与新来源 ID 不混用 |
| `references/part-selection.md`、`lcsc-sourcing.md`、`jlc-handoff.md` | 保留流程，链接替代分类/选型/制造路线 | 流程与参数表分工，避免复制 |
| `references/starter-patterns.md`、`product-example.md` | 保留骨架/演练，链接完整项目样本 | 骨架不等于完整项目 |
| 未计划的 `topics/board-thermal-design/` 草稿 | 移出仓库到研究区，未纳入交付 | 引用了不存在的 `tools/thermal_calc.py`、`cases.md`、`handoff.md`，属不完整草稿 |
| 未计划的 `topics/passive-components/` 草稿 | 移出仓库到研究区；关键内容已吸收到 `selection/passives.md` | 不在任务结构内，避免与选型文档重复、避免未审查内容混入 |
| 原有 190 条检查提示 | 保留，未删除、未改编号 | 新卡片引用 SC/PL/RT/MF/DM，不重复正文 |

## 4. 来源、查阅范围与许可

- 91 条来源登记在 `design-hardware/references/source-register.md`；每条含标题、发布者、版本/日期、实际查阅范围、支持内容、不能推广的部分和 URL。
- 主要来源类型：TI/ADI/ST/Espressif/Raspberry Pi/Infineon/Quectel/u-blox/Sitronix/Winbond/Omron/TE 等原厂手册、应用笔记、勘误/作者修订，以及嘉立创/立创商城官方页面。
- 只做转述和短引用，不打包第三方 PDF、整张图纸或客户工程。各来源许可以发布者条款为准；部分手册标注 Confidential，未复制进仓库。
- 立创商城商品页/搜索页在 2026-10-20 返回 404/系统异常，未取得可核对的实时字段；新增内容不编造 C 号、价格、库存、MOQ、包装、生命周期或 SMT 状态。

## 5. 实际执行与验证

### 已执行

- `python -m unittest discover -s tests -v`：96 项全部通过（2026-10-20），覆盖结构、内部链接、卡片 12 节、范例/故障/项目结构、35 个场景、12 个指定反例、5 个新计算模式、RC 数值仿真。
- `python design-hardware/scripts/calculate.py ...`：Buck/Boost/ADC 建立/电流采样/PCB 载流算例。
- `python design-hardware/scripts/rc_settle_sim.py ...`：二阶 RC 采样网络数值仿真，输出 CSV 和 JSON 摘要。
- `python design-hardware/scripts/netlist_check.py`、`sch_layout_check.py`、`power_budget.py`：在场景/项目样本上运行，记录 `incomplete/target_missed/needs_review` 等真实状态。

### 未执行 / 阻塞

- **真实 EDA**：本机没有 easyeda CLI、KiCad、嘉立创 EDA 插件或可用 daemon；未绘制/回读/导出/DRC 任何真实工程。项目样本是离线规划。
- **SPICE**：本机没有 ngspice/LTspice；`assets/simulation/rc_sample.cir` 标注 `NOT RUN`，没有生成假波形。
- **立创商城/嘉立创订单**：搜索结果与商品页不可用；没有 C 号/价格/库存/MOQ/交期/SMT 可贴状态，没有下单、支付、上传 BOM 或工程文件。
- **制造/样机**：没有打样、SMT、手焊、烧录、功能测试或长期可靠性数据。
- **安全/认证**：没有做市电、隔离、汽车、医疗、功能安全等标准签核；相关卡片只给识别与资料入口。
- **独立内容审查**：尝试启动 4 个只读审查 Agent（卡片两组、故障/选型/制造、计算/范例/组合/仿真）；受 API 并发限制（5 并发/15 排队）影响，审查未完成，未把“独立审查通过”写成结论。已完成的是结构、链接、计算、场景和反例的自动化测试与人工抽查。

## 6. 未完成与下一步

1. 用真实 EDA 打开至少一个项目样本，完成原理图/PCB、网表回读、DRC 和导图，替换“离线规划”状态。
2. 在立创商城/嘉立创实际登录环境核对至少 10 个关键料的 C 号、价格、库存、MOQ、包装、生命周期和 SMT 可贴状态，更新 `selection/lcsc-verification.md`。
3. 运行 `assets/simulation/rc_sample.cir`（ngspice/LTspice）并记录工具、模型、激励、波形和通过标准；当前只有自研数值模型。
4. 对 3 个项目样本做首板：上电、电源/复位/时钟/下载、接口、负载、环境与功能验收，记录实际结果。
5. 由独立硬件工程师复核高风险卡片（市电/隔离、热插拔、MOSFET SOA、电池保护、4-20mA 隔离）和故障案例的证据等级。

## 7. 复现

```bash
python -m unittest discover -s tests -v
python design-hardware/scripts/calculate.py buck '{"vin_min_V":4.5,"vin_max_V":5.5,"vout_V":3.3,"iout_max_A":2,"fsw_min_Hz":500000,"efficiency":0.9,"ripple_ratio":0.3,"vout_ripple_max_V":0.033}'
python design-hardware/scripts/rc_settle_sim.py --out rc.csv
python design-hardware/scripts/netlist_check.py design-hardware/assets/projects/p01-connectivity.json --json
```

测试通过只证明这些自动化检查通过，不证明硬件设计已验证。
