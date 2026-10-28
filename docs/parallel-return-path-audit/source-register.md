# 一手技术资料来源登记（reference-path audit）

本表只收录**芯片/接口厂商、标准组织**的一手文档，用于支撑规则的*方向性*依据。
规则阈值（corridor、return-via 距离等）**不**来自本表；它们必须由项目/接口声明，
报告里标为 `project_configured`。本工具不把任何接口的经验值当作通用高速标准。

## 核验等级（本环境实测）

本会话的网络能力受限：通用 web 搜索端点返回 401；`web_fetch` 只能取 HTML，
PDF 返回 `unsupported content type`。因此核验等级必须如实标注：

| 等级 | 含义 |
|---|---|
| `V1` | 实际打开并读到正文（仅 HTML 可行） |
| `V2` | URL 解析成功（HTTP 200）且内容类型表明文档存在，但正文未能在本环境解析 |
| `V3` | 由本项目既有 references 引用登记（[G05]/[G06] 等），本轮未重新核验 URL |
| `V0` | 付费/不可达，未核验 |

> 结论：本轮的规则依据以 **V2/V3** 为主，**没有**任何一条规则声称已核验到具体页码/节号。
> 报告中 `source_ids` 只表示“该规则属于此来源支持的方向”，不表示页码已核验。
> 复核条件：具备 PDF 解析与联网检索的环境下，应逐条补页码/节号并升级为 V1。

访问日期：2026-10-27（Asia/Shanghai）。

## 来源清单

### SRC-01 — TI SLLA414（高速接口布局）
- 发布方：Texas Instruments
- 标题/编号：*SLLA414*（High-Speed Interface Layout Guidelines 系列；本项目既有引用记为
  [G06]「高速差分、过孔、回流和 ESD 章节」）
- URL：https://www.ti.com/lit/an/slla414/slla414.pdf
- 核验：`V2` — HTTP 200，`application/pdf`（正文未解析）；`V3` — 本项目
  `design-hardware/references/design-experience.md` G06 已登记其支持“高速差分、过孔、回流和 ESD”。
- 适用条件：文档面向其所述接口/速率；**不**外推为所有高速接口通用阈值。
- 支撑：R2（参考平面连续性/回流）、R3（过孔与换层回流）、R4（差分对布局）。
- 引用页码：**未核验**（本环境无法读取 PDF 正文）。

### SRC-02 — Analog Devices MT-031（接地与回流）
- 发布方：Analog Devices
- 标题/编号：*MT-031 Tutorial — Grounding Data Converters and Solving the Mystery of "AGND" and "DGND"*
- URL：https://www.analog.com/media/en/training-seminars/tutorials/MT-031.pdf
- 核验：`V2` — HTTP 200，`application/pdf`；`V3` — 项目 references G05 已登记。
- 适用条件：数据转换器/混合信号接地方法；用于说明“回流按电流路径理解”，不是通用平面分割标准。
- 支撑：R1（参考/接地方向性）、R5（不能只看网络名判断回流）。
- 引用页码：**未核验**。

### SRC-03 — AMD/Xilinx UG583（UltraScale 架构 PCB 设计）
- 发布方：AMD (Xilinx)
- 标题/编号：*UG583 — UltraScale Architecture PCB Design User Guide*
- URL：https://docs.amd.com/v/u/en-US/ug583-ultrascale-pcb-design
- 核验：`V2` — HTTP 200，页面为 JS 文档查看器，正文未能在本环境提取。
- 适用条件：UltraScale 器件/接口的 PCB 设计建议；不自动适用于其他器件。
- 支撑：R1（层叠/参考平面）、R2（平面连续性）、R3（stitching/return via）。
- 引用页码：**未核验**。

### SRC-04 — IPC-2221（印制板通用设计标准）
- 发布方：IPC / Global Electronics Association
- 标题/编号：*IPC-2221B — Generic Standard on Printed Board Design*（B 版为常用修订；
  本环境未能打开正文确认当前修订字母）
- URL：https://www.ipc.org/ipc-standards（标准入口；具体文档为付费/登录）
- 核验：`V0` — 付费标准，正文与修订均未核验；仅作为“行业设计标准存在”的引用，
  **不**用于任何阈值。
- 支撑：R1/R2 的背景性依据（不用于具体判定）。
- 引用页码：**未核验**。

### SRC-05 — USB-IF USB 2.0 Specification（版本元数据）
- 发布方：USB Implementers Forum
- 标题/编号：*Universal Serial Bus Specification, Revision 2.0*；页面标注 2025-06-03，
  原始规范 2000-04-27，含至 2025 的 ECN/errata 列表
- URL：https://www.usb.org/document-library/usb-20-specification
- 核验：`V1` — 页面正文已打开（版本、发布日期、ECN 清单可见）；规范 PDF 本体未逐页核验。
- 适用条件：仅用于“接口/速率需要按具体 revision 引用”的方法论；USB 2.0 电气/布局要求
  不得外推到 USB 3.x/其他接口。
- 支撑：R1/R4 的“接口特定依据”入口（本项目接口阈值仍须另行声明）。
- 引用页码：**未核验**。

## 规则族 → 来源映射

| 规则族 | 内容 | 支持来源 | 证据性质 |
|---|---|---|---|
| R1 | 层叠/参考意图：物理层序、相邻参考、网络一致性 | SRC-03, SRC-04, SRC-05 | 方向性（定性） |
| R2 | 参考平面连续性：跨分割/孔洞/窄走廊 | SRC-01, SRC-03, SRC-04 | 方向性（定性） |
| R3 | 换层回流：via span、stitching/return via、电容桥接 | SRC-01, SRC-03 | 方向性（定性） |
| R4 | 差分参考对称性 | SRC-01, SRC-05 | 方向性（定性） |
| R5 | 证据边界：几何不能证明电连接 | 工具自身的证据政策（非厂商文档） | 方法学声明 |

## 明确没有一手数值阈值的内容

以下阈值**没有**在本轮核验到一手数值依据，全部保持 `project_configured`，报告不得暗示为通用标准：

- `constraints.corridor`（参考铜边缘检查走廊）
- `constraints.max_return_via_distance`（回流候选过孔距离）
- `constraints.min_split_gap`（同网微缝关注阈值）
- `constraints.via_search_radius`（附近过孔扫描半径）
- 任何接口的串扰/阻抗/损耗具体数值

## 未完成事项（NOT RUN）

- 未能在本环境解析任何 PDF 正文，因此**没有**逐条记录“页码/图号”。
- 未做器件级 layout 指南的逐接口检索（搜索端点 401）。
- 复核方式：具备 PDF 解析与可用检索时，补 `SRC-01/02/03` 的具体章节并升级核验等级；
  在 `sources.py` 中同步。
