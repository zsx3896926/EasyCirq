---
id: R4-I
title: 变更影响：四类场景、闭包与旧件状态
packages: [I]
evidence: E3
last_reviewed: 2026-10-22
sources: [MFG-S05, MFG-S06]
---

# 变更影响：四类场景、闭包与旧件状态

> 用途：把“改一点”从口头约定变成有向影响图、旧件状态和复验范围，防止旧原理图、旧 Gerber、旧 BOM 或旧测试结论混入新版本。证据等级 E3（离线方法整理；本轮未重开原厂正文、未改工程、未回读、未实测）。不能替代工程变更评审、EDA 回读、首件与批次追溯。

## 目录
1 触发条件；2 输入；3 Agent 可独立完成的判断；4 必须停下的条件；5 决策规则与表；6 改变哪个工程决定；7 完整案例；8 证据与验证方式；9 与现有资产的分工；10 来源、未知与重评触发。

## 1. 触发条件
**触发：** 样机冻结后改料、改封装、改电路拓扑、改布局、改连接器/线序、改板框或改固件接口；同一版硬件存在 V1/V1.1 或多销售配置；已投板、已备料或已有验收记录。**不触发/跳过：** 同一草稿内未冻结的注释/丝印文字修正且不导出任何工件；纯文档错别字；变更未离开编辑器且无旧产物。跳过写理由，不留下“已评估”的假记录。**深度：** D0 只改注释或文本且不影响任何工件；D1 单工件、单模块、无接口变化（仍要写前后对照）；D2 跨原理图/PCB/BOM/坐标/固件/线束、等级 2–3、已投板或已出货（完整影响图、闭包、批次/序列号与回滚）。

## 2. 输入
- **Agent 能自己读：** 变更请求、当前版本/保存快照、BOM/CPL/Gerber 的版本与哈希、既有变体表、测试记录、`manufacturing-routes.md` 的替代与 ECO 表。
- **必须问用户/缺失即停：** 哪些板/批次/序列号已出货或在制；现场能否返修/换板；是否涉及认证、安规或客户合同；可接受的停线/报废范围。变更前基线身份不明、已出货却无批次/序列号记录、声称“已验证”却没有 E1 证据、涉及隔离/安规却无耐压与认证依据、没有 after 快照/网表 diff 却要写“网表未变”，任一项只能停。

## 3. Agent 可独立完成的判断
- 把变更归入四类场景并映射既有 1/2/3/4 级；同一变更单含多场景时逐条映射，不用最高等级掩盖低等级项。建立有向影响图：节点是工件/旧件/接口，边是“更新/失效/需复验”；从失效节点做闭包，找仍为 unchanged 的下游。写变更摘要（I3）、旧件状态（I5）、复验范围（I4）、批次/序列号生效范围、回滚/撤回/报废处置。区分“方向”与“事实”：没有 after 快照、网表 diff、回读或实测时，只能写计划方向或 NOT RUN。

## 4. 必须停下的条件
- 等级 3 变更却无原理图/PCB/封装访问权限，或想用飞线/割铜冒充正式变更；加隔离、改安规边界却无隔离耐压、爬电/间隙与认证数据。
- 变更已涉及出货批次，但没有批次/序列号范围；只能停在“未定义”，不能默认全量或零影响。
- 用 F1（前轮 E1 基线）充当本次改型证据；F1 只能作真实基线，不能证明 V1.1。没有 E1 证据却把复验项写成 pass；没有 after 网表/BOM diff 却写“未变”。

## 5. 决策规则与表
### 5.1 四类变更场景与既有等级
| 场景 | 典型动作 | 映射等级 | 必须重做 |
|---|---|---|---|
| 换分流（shunt-change） | 100 Ω 改 50 Ω 或换精度/功率 | 等级 2：改阻容/增益/配置 | 重算误差与合规、改增益/固件参数、重跑精度测试 |
| 换 MCU 封装（mcu-package-change） | 同系列不同封装/引脚 | 等级 3：改原理图/封装/PCB | 重画符号/封装、重布、重导、重对账、重映射固件 |
| 加隔离（isolation-add） | V1 非隔离 → V2 隔离 | 等级 3：改拓扑/原理图/PCB | 隔离器与隔离电源、爬电/间隙、耐压/共模测试、重导 |
| 纯重排布局（layout-only） | 不改网表/BOM，只挪位置/走线 | local-only：不套用 1–4 级 | 网表 diff、DRC/ERC、装配/丝印复核；无 diff 即 NOT RUN |

等级定义以 `design-hardware/references/manufacturing-routes.md:539-562` 为准；本文不另造分级。local-only 不是“免检”，只是不触发替代等级。

### 5.2 BOM delta（每类场景至少一行；未知写“待查”）
| 场景 | 位号 | 旧值/MPN | 新值/MPN | 数量 | DNP | 原因 |
|---|---|---|---|---|---|---|
| 换分流（shunt-change） | R_SHUNT | 100 Ω、0.1%、2512（MPN 待查） | 50 Ω（MPN 待查） | 2 | 否 | 量程与合规裕量重算；增益改 2 |
| 换 MCU 封装（mcu-package-change） | U5 | STM32F4 类（后缀/封装待查） | 待查 | 1 | 否 | 封装/引脚变化，固件重映射 |
| 加隔离（isolation-add） | 待查（隔离器/隔离 DC/DC）、U4 | 无 / 3.3 V 半双工收发器（MPN 待查） | 数字隔离器 + 隔离 DC/DC（MPN 待查）/ 隔离侧收发器（MPN 待查） | 待查 | 否 | 隔离侧新增与重选 |
| 纯重排布局（layout-only） | 全部 | 不变 | 不变 | 0 | 不变 | BOM 不变，CPL/坐标变化，NOT RUN |

BOM delta 只写方向和位号；无 MPN/C 号/价格/库存就写待查。纯重排布局不得用“BOM 未变”替代 CPL/坐标 diff，无 after 快照即 NOT RUN。

### 5.3 有向影响图与闭包
- **节点：** schematic、netlist、pcb、gerber、bom、cpl、firmware、test-plan、production-snapshot、enclosure、labels、certification、old-part、F1-baseline；每个节点写 `state` 与证据。**边：** `updates`（上游变化要求下游更新）、`invalidates`（上游失效使下游旧件失效）、`requires-reverification`（下游必须重验）；边必须有方向，不写“相关”这种无向词。
- **闭包与旧件：** 从所有 `invalidated` 节点出发沿出边遍历；任何可达节点仍为 `unchanged` 即阻断，标 `stale_downstream_artifact`。`reverified` 必须有 E1 证据；`updated` 表示已生成新件但仍需按范围复验。每个被替换/受影响的旧件单独列 `unchanged/updated/invalidated/reverified/not_applicable`；不得只写“旧版作废”而不列位号/版本。

### 5.4 变更单字段（I3）
| 字段 | 必填内容 |
|---|---|
| `change_id` / `title` / `date` / `status` | 唯一编号、标题、日期；draft/frozen/superseded/withdrawn |
| `baseline` | 产品基线、EDA 基线（如 F1）、等级、本轮是否重跑、角色（baseline_only/revision_evidence） |
| `changes[]` / `affected_artifacts[]` | 场景、等级、from/to、原因、计划状态、BOM delta（位号/旧值/新值/数量/DNP/原因）；工件、旧版本/哈希、状态；不虚构 MPN/C 号/价格/库存 |
| `batch_scope` / `verification` / `rollback` | 批次/序列号范围；复验项与证据等级；回滚处置 |

### 5.5 旧件状态与批次/序列号生效范围
| 状态 | 含义 | 允许写法 |
|---|---|---|
| `unchanged` | 未受本次变更影响 | 必须有网表/BOM diff 或明确的结构理由；否则 NOT RUN |
| `updated` / `reverified` | 已生成新版本 / 已按新版本重验 | updated 写新版本/哈希，未生成不得写；reverified 必须有 E1 证据，E3 模型一致不算 |
| `invalidated` | 旧件不得再用 | 写隔离/报废/返修处置 |
| `not_applicable` | 本变更不涉及 | 写理由，不写“默认没事”；只用于确认没有出货/在制批次 |

**批次/序列号：** 有出货记录时写 `range` 或 `serial-list` 及起止；无记录时写 `unknown` 并停在影响评估，不得写“全部”或“无影响”。`not_applicable` 只用于确认没有出货/在制批次。

### 5.6 回滚、撤回、报废与复验范围
- **处置：** `rework` 用于可安全返修的旧板，记录返修方法、工位、复验项、数量；`scrap` 用于不能安全返修或混版风险高的旧板/旧料，记录隔离、数量、报废凭证；`use-as-is` 只用于偏差在验收范围内且有 E1 证据，记录偏差评估、授权人、批次范围；`not_applicable` 只用于未投产/未出货并写理由。**复验范围：** 等级 2 重算受影响误差/时序并重跑对应测试；等级 3 整套重导、重对账、重跑电气/机械/热与首件；local-only 至少做网表 diff、DRC/ERC 与装配复核。撤回/替代用 `superseded`/`withdrawn` 记录，不删除旧记录；已出货批次按 5.5 范围处理。ECO 流程不另写：以 `design-hardware/references/manufacturing-routes.md:539-562` 与 `design-hardware/references/project-coherence.md:18-27` 为准。

## 6. 改变哪个工程决定
变更影响图决定版本冻结、生产快照保留、BOM/CPL/Gerber 重导范围、固件版本与接口兼容、旧库存处置、测试抽样与客户通知。等级 2/3 不能在旧板上“先飞线试试”后直接放行。

## 7. 完整案例
[R4-CASE-I01：旧版产品 V1 → V1.1 的四类改型](cases/r4-case-i01-legacy-product-revision.md)（R4-P6，E3 / OFFLINE_PLANNING / hardware_execution NOT RUN）。
- 决定：换分流按等级 2、换 MCU 封装与加隔离按等级 3、纯重排按 local-only；先建影响图与闭包，再谈复验。
- 代价：等级 2 要重算/重测，等级 3 要整套重导重对账；local-only 仍需网表 diff，不能用 F1 代替。
- 下一个检查或待查：after 快照/网表 diff、出货批次/序列号范围、隔离耐压数据、F1 重跑，均 NOT RUN/待查。

## 8. 证据与验证方式
本轮为 E3 离线规划：只读现有项目记录、制造路线与来源登记，未重开原厂正文、未改工程、未回读、未实测。`scripts/decision_record_check.py change|graph <record>` 只检查字段、场景-等级映射、每场景 bom_delta、旧件状态闭包与 F1 证据边界；pass 证据必须是可解析的 path:start-end 或来源 ID，reverified 的复验 scope 必须对应工件；脚本不证明变更已执行或硬件通过。输出固定 `board_verified:false`、`execution:OFFLINE_PLANNING`、`hardware_execution:NOT RUN`。

## 9. 与现有资产的分工
- `design-hardware/references/manufacturing-routes.md:539-562`：给替代等级与 ECO 流程；本文只做场景映射、影响图和闭包，不另造分级。`design-hardware/references/project-coherence.md:18-27`：给跨工件变更传播表；本文把它变成有向边与旧件状态。`design-hardware/references/projects/p02-industrial-rs485-analog.md:360-368`：给 P02 的 V1/V2 变体事实；案例只引用，不新增器件参数。
- `docs/evidence/f1-2026-10-22/README.md:1-20`：F1 是本轮之前的 E1 原理图基线；本文把它限定为 baseline_only，不作改型证据。

## 10. 来源、未知与重评触发
| 来源 ID | 实际查阅范围 | 本轮是否重开原厂正文 |
|---|---|---|
| MFG-S05 | 全文（§2 BOM 字段/DNP、§3 坐标字段、§4 一致性）；BOM/CPL 与变体口径 | 未重开，沿用登记范围 |
| MFG-S06 | 正文各节（坐标格式、单位、字段顺序、最简格式）；坐标字段独立印证 | 未重开，沿用登记范围 |

**未知：** 出货批次/序列号、after 快照与网表 diff、隔离耐压/认证数据、替代料完整 MPN 与库存、产线返修能力，均待查。**重评触发：** 变更场景或等级变化；新增出货批次；隔离/安规要求变化；EDA/制造文件格式或版本更新；F1 重跑或新的 E1 基线出现；客户/合同变更。
