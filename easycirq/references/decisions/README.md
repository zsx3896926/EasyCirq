# 工程设计决策库（A–L）

> 用途：把“选哪个方案、依据什么、接受什么代价、什么时候必须重评、哪些证据还缺”落成可检查的记录。本页是索引，不是百科；正文按需加载。
>
> 证据边界：12 份参考文档都是 `E3` 方法整理（本轮未重开原厂正文）；13 个案例都是 `execution: OFFLINE_PLANNING`、`hardware_execution: NOT RUN`。模板、脚本、索引通过只证明结构与记录自洽，不证明器件、板子、制造或样机已验证。
>
> 不替代：[组合与接口契约](../module-integration.md) 的 12 条判据、[项目关联记录](../project-coherence.md) 的变更传播、[选型与装配变体](../part-selection.md) 的 DNP 原则、[计算手册](../calculations/README.md) 的公式与算例、[设计卡库](../design-cards/README.md) 的拓扑、[项目样本](../projects/README.md) 的完成级别。

## 1. 什么时候加载：D0 / D1 / D2

- **D0 不建记录**：决定可逆、只影响一个局部对象、没有跨模块后果；沿用现有表格或会话记录。
- **D1 轻记录**：一个不可逆或跨模块决定；只写决策头、选择、代价、重评触发。
- **D2 完整包**：多个方案有实质取舍、涉及安全/供电/接口/变体/校准/变更，或证据不足会影响下游；启用备选比较、typed block、模板与脚本。

| 包 | 触发（满足任一） | 不触发/跳过 | 最小深度 |
|---|---|---|---|
| A 架构 | 供电方式、接口距离、成本/功耗/体积目标冲突；用户要求“先方案” | 单颗 LED/按键；直接沿用已核对参考且无改动 | D1；有备选取舍时 D2 |
| B 资源 | 主控/模组有复用脚、启动脚、调试口、模拟脚、Bank 或封装约束 | 无主控；固定模块且不新增外设 | D1；有冲突或换型号时 D2 |
| C 状态 | 电池+外电共存、休眠、可关断轨、热插拔、多复位源、升级/调试 halt | 单电源常开且状态不影响接口电平 | D1；部分供电/反灌时 D2 |
| D 容差 | 精度、阈值、限流、稳压、采样或时序受容差/温度影响 | 纯数字逻辑且无定量判据 | D1；有角点/主导项时 D2 |
| E 接口 | 跨板、连接器/排线、双向/多驱动、跨电压域、可关断轨、热插拔 | 同一张原理图内的短网络且无状态耦合 | D1；多驱动/热插拔时 D2 |
| F 线束 | 两块及以上板、面板、传感器/执行器、装壳、现场维护 | 单板、无板外连接、只做板级测试 | D0/D1；含电源/屏蔽/热插拔时 D2 |
| G 变体 | 同一 PCB/产品族两种及以上销售配置；装/不装、固件/丝印/包装随配置变 | 单配置、单 BOM、单固件 | D0/D1；共板多配置时 D2 |
| H 校准 | 有精度承诺、出厂参数、设备身份、现场/工厂配置边界 | 无精度承诺且无可写存储 | D1；要写校准记录时 D2 |
| I 变更 | 换封装/换电源/改接口/改程序/改布局/换料 | 只改注释或纯文本且不影响产物 | D1；涉及 SCH/PCB/BOM/固件时 D2 |
| J 复用 | 复用成熟电路块/模块/参考设计 | 新设计；只把资料当学习材料 | D1；跨产品复用时 D2 |
| K 实验 | 要比较布局、阻值、滤波、供电方案，或优化指标 | 没有基线、没有可控变量、无法绑定版本 | D1；要采用结论时 D2 |
| L 资产 | 旧资产被新项目/新板版引用；来源换版、冲突、EOL/PCN | 同项目、同版本、同条件复读 | D0/D1；有冲突/依赖链时 D2 |

**加载顺序：** 先读对应参考的 §1（触发）与 §4（停下条件），再读一个已填案例；只有要动手填写时才打开模板/脚本。不要一次加载 12 份。

## 2. 十二个工作包

| 包 | 参考 | 一句话 | 主要案例 | 脚本 |
|---|---|---|---|---|
| A | [R4-A01 架构决策记录](a01-architecture-decision.md) | 备选、排除判据、代价、冻结与重评 | A01、A02 | — |
| B | [R4-B01 引脚与资源规划](b01-pin-resource-planning.md) | 分配顺序、冲突检查、换型号/封装 diff | B01 | `pin_plan_check.py` |
| C | [R4-C01 工作状态与转换](c01-state-transition-contract.md) | 三轴、entry/exit/completion、恢复与 POR | C01 | — |
| D | [R4-D 容差与最坏情况](d01-tolerance-and-worst-case.md) | 逐项预算、角点同时性、主导项→动作 | D01 | — |
| E | [R4-E01 跨模块接口契约](e01-interface-contract.md) | 一条接口一行、阻断、stale | E01 | `interface_contract_check.py` |
| F | [R4-F 整机线束](f01-harness-and-board-external.md) | 线束包、配对件、逐线记录、防误接 | F01 | `harness_check.py` |
| G | [R4-G 产品变体](g01-product-variants.md) | requires/conflicts/forbidden 闭包、防混料 | G01 | `variant_bom.py` |
| H | [R4-H 校准与身份](h01-calibration-and-identity.md) | 记录结构、A/B 槽、无效参数、工厂/现场 | H01 | `decision_record_check.py` |
| I | [R4-I 变更影响](i01-change-impact.md) | 四类场景、影响图、旧件失效闭包 | I01 | `decision_record_check.py` |
| J | [R4-J 模块复用](j01-module-reuse.md) | opt-in 合同、兼容矩阵、实例化验证、退役 | J01 | — |
| K | [R4-K 受控实验](k01-controlled-experiment.md) | 预注册、基线、单变量、采用决定 | K01 | — |
| L | [R4-L 资产有效性](l01-asset-validity.md) | 冲突定义、依赖、历史/当前、维护 | L01 | `decision_asset_check.py` |

## 3. 十三个案例（R4-P1…P6）

| 案例 | 项目 | 族 | 包 | record_types |
|---|---|---|---|---|
| [R4-CASE-A01 需求变化](cases/r4-case-a01-requirement-change.md) | R4-P2 | P01 | A | requirement-change |
| [R4-CASE-A02 过度设计门](cases/r4-case-a02-overdesign-gate.md) | R4-P1 | P01 | A | refuted-assumption |
| [R4-CASE-B01 引脚冲突](cases/r4-case-b01-pin-allocation-conflict.md) | R4-P1 | P01 | B | unknown-retained |
| [R4-CASE-C01 电池+外电状态](cases/r4-case-c01-battery-plus-external-supply-states.md) | R4-P2 | P01 | C | state-transition, unknown-retained |
| [R4-CASE-D01 采集容差](cases/r4-case-d01-acquisition-tolerance.md) | R4-P3 | P02 | D | refuted-assumption |
| [R4-CASE-E01 多板接口](cases/r4-case-e01-multiboard-interface-contract.md) | R4-P4 | P02 | E | interface-contract, unknown-retained |
| [R4-CASE-F01 多板线束](cases/r4-case-f01-multiboard-harness.md) | R4-P4 | P02 | F | refuted-assumption, unknown-retained |
| [R4-CASE-G01 双销售配置](cases/r4-case-g01-two-sales-configs-one-board.md) | R4-P5 | P02（constructed） | G | refuted-assumption, unknown-retained |
| [R4-CASE-H01 测量节点校准](cases/r4-case-h01-measurement-node-calibration.md) | R4-P3 | P02 | H | unknown-retained |
| [R4-CASE-I01 旧版改型](cases/r4-case-i01-legacy-product-revision.md) | R4-P6 | P02 | I | local-only |
| [R4-CASE-J01 充电块复用](cases/r4-case-j01-charger-power-path-reuse.md) | R4-P2 | P01 | J | reuse-rejected, unknown-retained |
| [R4-CASE-K01 单变量实验](cases/r4-case-k01-acquisition-single-variable.md) | R4-P3 | P02 | K | unknown-retained |
| [R4-CASE-L01 资产冲突](cases/r4-case-l01-asset-validity-conflict.md) | R4-P6 | P02 | L | unknown-retained |

案例族谱、canonical facts 与五类 record 的 owner 见 [cases/README.md](cases/README.md)。案例是决策对照，不是项目样本、故障库或 EDA 证据。

## 4. 十四个模板

| 模板 | 谁用 | 用途 |
|---|---|---|
| [decision-record.template.md](../../assets/decisions/decision-record.template.md) | 所有 A–L 案例 | 决策头 + 五类 typed block |
| [pin-plan.template.json](../../assets/decisions/pin-plan.template.json) | B01 | 引脚/资源/候选/未决项 |
| [state-transition.template.json](../../assets/decisions/state-transition.template.json) | C01 | 三轴状态、转换、POR、部分供电 |
| [interface-contract.template.json](../../assets/decisions/interface-contract.template.json) | E01 | 一条接口一行 |
| [tolerance-budget.template.md](../../assets/decisions/tolerance-budget.template.md) | D01 | 逐项预算与角点 |
| [experiment-record.template.md](../../assets/decisions/experiment-record.template.md) | K01 | 预注册、基线、单变量、采用 |
| [harness-package.template.md](../../assets/decisions/harness-package.template.md) | F01 | 整机线束包 |
| [variant-matrix.template.md](../../assets/decisions/variant-matrix.template.md) | G01 | 变体闭包与差异 |
| [variant-bom.template.json](../../assets/decisions/variant-bom.template.json) | G01 | master BOM → 变体 needed |
| [calibration-record.template.json](../../assets/decisions/calibration-record.template.json) | H01 | 校准记录、槽位、CRC、身份 |
| [change-record.template.json](../../assets/decisions/change-record.template.json) | I01 | 变更单、旧件状态、BOM delta |
| [change-impact-graph.template.json](../../assets/decisions/change-impact-graph.template.json) | I01 | 有向影响图与闭包 |
| [module-reuse-record.template.md](../../assets/decisions/module-reuse-record.template.md) | J01 | 10 组复用合同字段 |
| [asset-index.template.md](../../assets/decisions/asset-index.template.md) | L01 | 资产指针、依赖、冲突 |

已填示例放在 `assets/decisions/*.example.*` 与 `*.r4p*.json`；示例不是模板，不得把示例值复制到新项目。

## 5. 六个检查脚本

| 脚本 | 检查 | 退出码 | 不证明 |
|---|---|---|---|
| [pin_plan_check.py](../../scripts/pin_plan_check.py) | 重复/未知脚、ADC 当输出、strap/调试脚被占、候选混入已分配 | 0/1/2 | 物理脚/pinmux 已核对 |
| [interface_contract_check.py](../../scripts/interface_contract_check.py) | 字段完整性、多驱动仲裁、off_behavior、插合序列、stale | 0/1/2 | 接口电气已通过 |
| [harness_check.py](../../scripts/harness_check.py) | 线束包版本、配对件、逐线证据、防误接矩阵 | 0/1/2 | 线束可加工/已压接 |
| [variant_bom.py](../../scripts/variant_bom.py) | requires/conflicts/forbidden 闭包、DNP、混料、needed 数量 | 0/1/2 | 可下单/价格/库存 |
| [decision_record_check.py](../../scripts/decision_record_check.py) | 校准记录、变更单、影响图的结构与状态机 | 0/1/2 | 校准有效/改型已验证 |
| [decision_asset_check.py](../../scripts/decision_asset_check.py) | 索引列、重复 ID、悬空依赖、冲突字段、状态、路径、来源 | 0/1/2 | 资产内容正确 |

脚本只读取声明的 JSON/Markdown，不联网、不读写工程；所有输出 `board_verified: false`。运行方式见各参考 §8。

## 6. 五类 typed record

| 类型 | owner case | 必填核心字段 |
|---|---|---|
| refuted-assumption | A02、D01、F01、G01 | 原假设、反证 path、影响、修正决定 |
| unknown-retained | B01、C01、E01、F01、G01、H01、J01、K01、L01 | 未知项、影响、owner、停止条件、复评触发 |
| requirement-change | A01 | 触发、新旧需求、被取代决定、affected_artifacts 表 |
| local-only | I01 | before/after 证据或 NOT RUN、为何不影响其他模块、复验 |
| reuse-rejected | J01 | 合同、未满足条款、证据、接受/拒绝、替代、复评 |

## 7. 与现有资产的分工

| 现有资产 | 负责 | 本库只补 |
|---|---|---|
| [module-integration.md](../module-integration.md) | 12 条接口判据、组合失败案例、状态快照 | 一条接口一行、状态×接口矩阵、stale |
| [project-coherence.md](../project-coherence.md) | 变更传播与版本对应 | 有向影响图、闭包、旧件失效状态 |
| [part-selection.md](../part-selection.md) | DNP/变体的工程原则 | 双销售配置闭包、变体 BOM 生成与防混料 |
| [calculations/](../calculations/README.md) | 公式、假设、算例、不能证明 | 跨电路逐项预算、角点决策、主导项动作 |
| [design-cards/](../design-cards/README.md) | 拓扑、参数步骤、逐脚 | 不做卡片；J 只给 opt-in 复用合同 |
| [projects/](../projects/README.md) | 项目样本与完成级别 | 在其事实上做决策对照，不改项目文件 |
| [failures/](../failures/README.md) | 单点故障与复验 | 只引用判据，不复制故障叙事 |
| [manufacturing-routes.md](../manufacturing-routes.md) | 变体表、线束表、制造路线 | 线束包受控字段、变体闭包与生成规则 |

## 8. 维护与准入

- 新增参考/案例/模板/脚本必须在本页与 [cases/README.md](cases/README.md) 登记；未登记资产不得写 `active`。
- 来源只用 [source-register.md](../source-register.md) 已登记 ID；许可不明、EOL/PCN 未核、旧项目未验证、来源未登记时，状态只能 `conditional`/`blocked`/`planned`。
- 同一对象、同一参数、同一条件、不同值才叫冲突；版本/范围差异记 `applicability-only`，不判冲突。
- 修改共享 `decision-record.template.md` 的 schema 由集成人统一处理；各工作流只提交变更请求。
- 索引自检：`python easycirq/scripts/decision_asset_check.py easycirq/assets/decisions/asset-index.r4p6.example.md --source-register easycirq/references/source-register.md`。示例只是 J/L 切片，完整覆盖以本页与 cases/README 为准。
