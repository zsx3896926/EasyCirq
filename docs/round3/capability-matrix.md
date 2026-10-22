# 第三轮能力矩阵（基线 dc62f20）

- 审计对象：`C:/Users/jlc/work/hds-round3`，HEAD `dc62f2073b99764a5a15cdd31020c856da75e50e`（`feat/round3-engineering`），审计开始时 `git status` 干净。
- 审计日期：2026-10-22。
- 范围：综合本轮各审计域的结论、仓库内真实 EDA 证据与官方 `doc api` 只读探测。本矩阵不新增 EDA 写入，不连接商城，不下单，不做烧录或样机测试。
- 基线漂移：审计期间 `origin/main` 已到 `0fe5cf80ab0dd8196c900ed9878bad40d4f6c8b9`（`dc62f20` 之后 3 个提交，仅涉及 `README.md`、`NOTICE`、`docs/readme-technical.md`）。本矩阵按任务指定基线 `dc62f20`，不覆盖这 3 个提交；它们不改变 EDA、PCB、制造与供应链结论。
- 写入边界：本文件是能力矩阵综合产物；同期还写入了 `execution-protocol.md`、`coverage-review.md`、`../task-ledger-round3.md`、`backlog.md`，以及执行器修复报告与证据。临时证据在 `C:/Users/jlc/work/hw-deepdive-scratch/round3-audit/`。
- **2026-10-22 修复后口径**：原理图快照完整性、字段级回读、工程级位号、页身份冻结、重开比较域与会话/版本门禁已在 `eda_exec.py` 实现并有真机证据；本文件第 2 节中“未比对 designator/mirror/端口方向”“netports 不在重开比较域”等描述是审计时状态，已被修复，阅读时以 [executor-fixes-2026-10-22.md](executor-fixes-2026-10-22.md) 为准。F1 的 C103 输出电容与 IO2 悬空已在 [F1 电气修订](f1-electrical-revision-2026-10-22.md) 中修正；重排与 PCB 仍未完成。PCB 适配器仍未实现。

## 0. 结论先行

本轮共判定 42 项：**VERIFIED 12 项、PARTIAL 10 项、NOT VERIFIED 19 项、BLOCKED 1 项**。

1. **原理图闭环有真实执行证据，但证据宽度小于台账措辞**：F1 在嘉立创EDA专业版 4.1.78 半离线会话中完成 16 器件、27 电源标记、16 网络端口、44 段导线的创建，93 个动作逐项 `verified`、`save.saved=true`、重开 `match`，并导出 PNG 与 Protel 网表。读取、创建、连接、保存重开、PNG/网表导出可判 VERIFIED。
2. **原理图的修改、删除、网络标签、SVG 导出、BOM 导出、DRC/ERC 没有真机执行记录**，只能判 NOT VERIFIED。F1 的 93/93 也不是全属性验证：逐项回读不比对 `designator`、`footprint`、`mirror`、`manufacturer`、`supplier` 文本、`other_property`、net flag 类型、net port 方向；netports 不在重开比较域内。
3. **PCB 客户端原始 API 已打通大部分操作，但 `eda_exec.py` 没有 PCB 路径**。原始 CLI 探针已跑通 PCB 读取、建板/建 PCB、原理图导入、走线、过孔、板框折线、铺铜边框、DRC、保存重开、Gerber/CPL 导出（DRC 与导出仅 PARTIAL，见第 3 节）；`eda_exec.py:1285` 仍写 `pcb_read_write=not_implemented_in_this_adapter`，全文件 `pcb_`/`PCB_` 调用仅 1 处。PCB 的 VERIFIED 均指“原始 CLI 探针”，不是 Skill 适配器能力。
4. **铺铜填充、层叠修改、设计规则、真实 pad-to-pad 布线、自动布线/自动布局未验证**；PCB DRC 与 Gerber/CPL 只到 PARTIAL，因为样例板基线不干净、导出文件未用独立查看器核对、F1 PCB 没有板框和布线。
5. **商城选型、库存/价格/MOQ/交期、替代料、SMT 可贴性、下单/DFM、烧录、样机测试均无真实执行记录**。仓库文档确实区分了“商城库存 / SMT 可贴 / 寄料”，但这是规则，不是渠道数据；2026-10-20 的 LCSC 搜索实测返回 `code:500/系统异常`，此后没有新的查询记录。
6. **全在线 GUI 验收 BLOCKED**：CLI 会话恒为半离线（`online:false`、`half_offline:true`），两个存活会话都是 `origin:user` 的 GUI，本轮未操作。半离线证据不能写成全在线验收。

## 1. 状态、环境与证据口径

### 1.1 状态定义

| 状态 | 判定规则 |
|---|---|
| VERIFIED | 能力所属环境有真实执行记录，且本项成功判据被实际检查。EDA 能力要求真实客户端执行；离线工具要求真实运行脚本或测试。VERIFIED 不等于无缺陷，必须同时读“限制”列。 |
| PARTIAL | 有真实执行，但只覆盖部分范围或部分判据，或关键产物未独立复核。 |
| NOT VERIFIED | 没有执行记录；仅有文档、API 存在、代码路径、单测或 Fake。不能根据文档/API 推断已验证。 |
| BLOCKED | 环境或授权明确阻断，且有阻断记录。 |

本矩阵中的 `VERIFIED` 只表示“该行描述的能力在所列入口和环境里跑通过并有证据”，不表示电气设计正确、可制造、可下单或可生产。

### 1.2 环境代码

| 代码 | 环境 |
|---|---|
| ENV-A | Windows 11；嘉立创EDA专业版 `4.1.78.34f5b8d9`；CLI 会话（PCB 探针为 headless）；`online:false`、`half_offline:true`；未驱动全在线 GUI。 |
| ENV-B | 同一客户端的官方 `doc api` 只读查询；只证明接口存在，不证明执行成功。 |
| ENV-C | Windows 11；Python `3.13.15`；仓库 `dc62f20`；纯离线脚本/单测，无 EDA。 |
| ENV-D | 仓库文档/代码静态核对；无执行。 |
| ENV-E | 外部 Web 未查询；仅保留 2026-10-20 的失败记录。 |

`raw-doctor.json` 实测：`connected:true`、`versionMatch:true`、`bridgeVersion:4.1.78.34f5b8d9`、`resultChannel:true`。`final-sessions.json` 实测有 2 个 `alive` 会话，`origin` 均为 `user`，`headless:false`。

### 1.3 证据分级与索引

- **A**：真实 EDA 客户端执行（4.1.78，半离线），有回读或产物文件。
- **B**：官方 API 查询（`doc api`），只证明接口存在。
- **C**：本地离线脚本、单测或代码复现，无 EDA。
- **D**：文档或代码静态声明，无执行。

| 证据 ID | 级别 | 路径 | 覆盖内容 |
|---|---|---|---|
| EV-01 | A | `C:/Users/jlc/work/hds-round3/docs/evidence/f1-2026-10-22/` | F1 `README.md`、`apply-result.json`、`snapshot.json`、`reopen-check.json`、`plan.json`、`schematic.png`、`schematic.net`；16 parts/27 flags/16 ports/44 wires；93/93 verified；save；reopen；PNG 与网表哈希。 |
| EV-02 | A | `C:/Users/jlc/work/hds-round3/docs/evidence/eda-2026-10-21/` | EvidenceDemo：2 parts/2 flags/0 ports/3 wires；apply/save/reopen/PNG/网表。 |
| EV-03 | A | `C:/Users/jlc/work/hw-deepdive-scratch/round3-audit/pcb-closed-loop/probe-pcb-result.json` | PCB 读取：33 components/98 lines/24 polylines/0 vias/1 pour/1 poured/83 pads/289 layers/17 nets；DRC；Gerber/CPL；env。 |
| EV-04 | A | `.../pcb-closed-loop/probe-pcb-write-result.json`、`.../probe-reopen-counts.json` | line/via/pour 创建、save、关闭重开；99 lines/1 via/2 pours/1 poured。 |
| EV-05 | A | `.../pcb-closed-loop/probe-outline-pour.json` | 板框折线 layer 11 创建/删除；铺铜边框创建、modify、DRC、Poured 未生成。 |
| EV-06 | A | `.../pcb-closed-loop/probe-f1-pcb2.json`、`.../probe-f1-reopen.json`、`.../probe-f1-pcb.json` | `createBoard`/`createPcb`/`importChanges`；F1 PCB 16 components/56 pads/11 nets；重开保持。 |
| EV-07 | A | `.../pcb-closed-loop/probe-pcb-component.json` | `PCB_PrimitiveComponent.create` 的 flat ref 成功（DC2）；`lib_Device.search` 成功（DC3）；state 对象签名失败。 |
| EV-08 | A | `.../pcb-closed-loop/raw-doctor.json`、`.../final-sessions.json` | doctor connected/versionMatch；2 个 alive user 会话；CLI 会话半离线。 |
| EV-10 | B | `.../pcb-closed-loop/doc-api-classes.json`、`class-PCB_*.json`、`methods/*.json` | 官方 `doc api` 共 388 个类型；PCB_* 类与关键方法。 |
| EV-11 | B | `C:/Users/jlc/work/hw-deepdive-scratch/round3-audit/capability-matrix/sch-component-api.json`、`sch-manufacture-api.json`、`sch-drc-api.json`、`sch-attribute-api.json` | 官方 SCH API：`SCH_PrimitiveComponent.delete/modify`、`getBomFile`、`getSvgFile`、`placeSmtComponentsOrder`、`SCH_Drc.check`、`createNetLabel`。 |
| EV-12 | C | `C:/Users/jlc/work/hw-deepdive-scratch/round3-audit/eda-exec/`（`coverage_report.json`、`repro_results.json`、`unittest_eda_exec.txt`） | 23 tests OK；60 个函数中 26 个从未执行（459/1641 行）；B1/B2 缺陷复现。 |
| EV-13 | C | `C:/Users/jlc/work/hw-deepdive-scratch/round3-audit/schematic-layout/`（`snapshot-check.txt`、`benchmark-run.json`、`overreport-control.txt`、`extras-summary.txt`、`f1-synthetic-sensitivity.txt`） | 真实 F1 snapshot 直跑检查器失败；8/8 recall-only；全 code 假检查器仍 8/8；敏感性实验。 |
| EV-14 | C | `C:/Users/jlc/work/hw-deepdive-scratch/round3-audit/f3-bom/`（`f1-bom-draft.csv`、`f1-bom-coverage.json`） | 从 F1 snapshot 生成 11 行/16 位号 BOM 草稿；字段缺口。 |
| EV-15 | D | `design-hardware/references/selection/lcsc-verification.md:83-93`、`design-hardware/references/manufacturing-routes.md:5/605-612/804`、`design-hardware/references/jlc-smt-rules.md:3`、`design-hardware/references/jlc-handoff.md:15/18` | 2026-10-20 商城搜索失败、待查纪律、商城/SMT/寄料状态区分。 |
| EV-16 | D | `design-hardware/scripts/eda_exec.py`、`design-hardware/references/eda-execution.md:45-61`、`docs/task-ledger-round2.md:15-30`、`design-hardware/SKILL.md:212` | 桥的能力声明、实现边界、台账口径。 |
| EV-17 | D | `docs/evidence/f1-2026-10-22/README.md:74-81` | F1 图面拥挤；DRC/ERC、PCB、制造、样机、固件 NOT RUN。 |
| EV-18 | A | `C:/Users/jlc/work/hw-deepdive-scratch/round3-audit/f1-evidence/geom_check.txt` | 网表 11 nets/45 pins；56 pins 中 11 个未连；2 条悬空 CC 短线、10 条零长线。 |

关键数字复核：F1 `apply-result.json` 的 93 个 action 全部是 `create_*`（16 part/27 net_flag/16 net_port/34 wire），93 个 verification 全部 `verified`；`schematic.png` SHA256 为 `F6656AB5...ED433B2`，`schematic.net` 为 `70A39BA8...94F8EC7`，与 README 一致。`doc api` 类型数为 388，包含 `PCB_Document`、`PCB_PrimitiveComponent`、`PCB_PrimitiveLine`、`PCB_PrimitiveVia`、`PCB_PrimitivePour`、`PCB_PrimitivePoured`、`PCB_Layer`、`PCB_Net`、`PCB_Drc`、`PCB_ManufactureData` 等。

下表的“验证日期”取证据生成日期；F1 与 PCB 探针是本轮审计域已保存的执行记录，不是本矩阵重跑。

官方 API 探测命令（2026-10-22，只读）：`lceda-pro doc api`（388 types）；`--class-name SCH_PrimitiveComponent`（create/delete/modify/get/getAllPinsByPrimitiveId）；`--class-name SCH_ManufactureData`（getBomFile/getSvgFile/getNetlistFile/placeSmtComponentsOrder）；`--class-name SCH_Drc`（check）；`--class-name SCH_PrimitiveAttribute`（createNetLabel）；`--class-name PCB_Document`、`PCB_ManufactureData`、`PCB_Layer`、`PCB_Drc`（见 EV-10）。

## 2. 原理图能力矩阵

> 本节只覆盖原理图。PCB 见第 3 节；本节 VERIFIED 不代表 PCB 可用。

| 能力项 | 执行入口 | 工具版本 / 环境 | 验证日期 | 证据 | 限制 | 状态 |
|---|---|---|---|---|---|---|
| 读取：页快照（器件/引脚/网络标记/端口/导线） | `eda_exec.py read --session/--project ... --output snapshot.json`（`SNAPSHOT_JS`） | `eda_exec @ dc62f20`；`4.1.78.34f5b8d9`；ENV-A | 2026-10-22 | EV-01：16 parts/27 netflags/16 netports/44 wires/56 pins；EV-02：2/2/0/3；EV-18 | 仅单页；默认 `include_attributes=false`；读取异常会被 `safe()` 折叠成 null/空数组（EV-12，B1-01）；`coverage` 在 Python 侧无消费者 | VERIFIED |
| 读取完整性 / coverage 可信度 | 同上（`snapshot.coverage`） | `eda_exec @ dc62f20`；ENV-A | 2026-10-22（代码/复现） | EV-01：`attributes_included=false` 但 `attributes_complete=true`；EV-12：`designator=null` 时 reconcile 产出 `create_part`；`eda_exec.py:378-380/458-511/1218-1239` | 无 `read_errors`；`pins_complete` 在 getter 失败时仍为 true；空/部分读取可被当成“不存在”；F1 真实快照未出现 null，故这是代码/合成复现，不是真机故障注入 | PARTIAL |
| 创建：器件/电源标记/网络端口/导线 | `eda_exec.py apply --plan ... --save`（create_part/create_net_flag/create_net_port/create_wire） | `eda_exec @ dc62f20`；`4.1.78.34f5b8d9`；ENV-A | 2026-10-22 | EV-01：93 actions（16/27/16/34）、93/93 verified、`save.saved=true`、after 16/27/16/44；EV-02：7 动作 | 逐项验证只比 part/supplier/x/y/rotation（`eda_exec.py:1116-1133`）；不比较 designator/footprint/mirror/manufacturer/other_property；执行返回的 `primitive_id` 未用于验证（`:1430-1439`）；位号重复风险见 B1-01；位号验证风险见 B2-01 | VERIFIED |
| 修改：已有器件位号/属性/位置 | `eda_exec.py apply`（`modify_part`，`APPLY_JS:643-658`；reconcile `:974`） | `eda_exec @ dc62f20`；ENV-A（无既有对象修改执行） | —（无既有对象修改记录） | EV-01：F1 的 16 个 create 后各执行一次 `modify` 设置位号；EV-12：`modify_part` 未在真机执行，计划 R1→R5 未生效仍 `verified`，创建后回读 `R?` 报 `part_not_found_after_apply`；F1 的 93 个与 EDA-2026-10-21 的 7 个动作全为 create | 无既有对象 modify 真机记录；创建后 modify 只覆盖 designator，属性集合窄；位号/属性回读不比对；`eda-execution.md:48/109` 的“属性/位号回读”声明宽于实现；异步 modify 语义未验证 | NOT VERIFIED |
| 删除：器件/导线/标记/端口 | 无（`OP_KEYS` 只有 part/net_flag/net_port/wire，`eda_exec.py:50-55`；无 delete 命令） | `4.1.78.34f5b8d9`；ENV-B | — | EV-11：`SCH_PrimitiveComponent.delete` 存在；EV-12：`eda_exec.py` 无 delete/remove | 桥不暴露删除；官方 API 存在不等于已验证；无删除依赖、幂等、回读规则 | NOT VERIFIED |
| 连接：导线+电源标记+网络端口+网表 | `eda_exec.py apply`（wire/net_flag/net_port） | `eda_exec @ dc62f20`；`4.1.78.34f5b8d9`；ENV-A | 2026-10-22 | EV-01：34 wires/27 flags/16 ports；EV-18：11 nets/45 pins；reopen 34/34；`schematic.net` SHA256 `70A3...` | netflag type、netport direction/mirror、rotation 未回读（apply-result 的 observed 只有 net/at/found）；F1 有 2 条悬空 CC 短线 + 10 条零长线；reopen 不比较 netports | VERIFIED |
| 跨页/网络标签/总线 | 无 net_label op；netport 仅单页；官方 `SCH_PrimitiveAttribute.createNetLabel` 未封装 | `eda_exec @ dc62f20`；`4.1.78.34f5b8d9`；ENV-B/D | — | EV-11：`createNetLabel` 存在；EV-16：`eda_exec.py:50-55` 无 net_label，doctor `net_label_idempotent_apply=not_implemented`（`:1286`）；仓库只有单页证据 | 无网络标签幂等写入；无多页工程/跨页作用域证据；总线/差分未验证 | NOT VERIFIED |
| 排版：按坐标放置/重排 | `part.place {x,y,rotation,mirror}`；wire points | `eda_exec @ dc62f20`；ENV-A | 2026-10-22 | EV-01：16 器件按计划坐标放置；EV-17：README:74 图面拥挤；EV-13：`snapshot-check` 无法直喂 | 无自动布局/文字/模块框/网络标签；无碰撞避免；F1 视觉未通过排版验收；无真实 layout-check 证据 | PARTIAL |
| 排版几何检查（离线） | `python design-hardware/scripts/sch_layout_check.py layout.json`；`schematic_benchmark.py` | `Python 3.13.15`；`repo dc62f20`；ENV-C | 2026-10-22 | EV-13：`snapshot-check.txt` exit 2（missing components/coordinate_units/texts）；benchmark 8/8；全 code 假检查器仍 8/8；6/8 未声明发现；文字宽度 10→20 使 bbox 56→64，补 netflag/netport 使 dangling 33→2 | 只吃手写 JSON；无符号本体/文字 bbox；8/8 只证 recall；无精度门禁；不判电气/视觉 | PARTIAL |
| 导出：PNG/网表 | `eda_exec.py export --kind png/netlist` | `eda_exec @ dc62f20`；`4.1.78.34f5b8d9`；ENV-A | 2026-10-22 | EV-01：`schematic.png` 330,106 B SHA256 `F665...`；`schematic.net` 18,457 B SHA256 `70A3...`；EV-18：11 nets/45 pins；EV-02 同类 | 导出跟随活动文档，必须先 `activateDocument`；仅 Protel2 网表；无重开后再导出/网表 diff（C4 缺第二次导出）；PNG 未做视觉验收 | VERIFIED |
| 导出：SVG | `eda_exec.py export --kind svg`（`EXPORT_JS:700-720`） | `eda_exec @ dc62f20`；`4.1.78.34f5b8d9`；ENV-A（无执行） | — | EV-11：`getSvgFile` 存在；仓库无 SVG 文件、无执行记录 | 代码路径存在但从未执行；多页 SVG 可能是 zip；未做视觉检查 | NOT VERIFIED |
| 导出：BOM | 无（`eda_exec` doctor `sch_export_bom=not_implemented`；官方 `getBomFile` 未封装） | `4.1.78.34f5b8d9`；ENV-B；ENV-C 草稿 | —（EDA BOM 未导出） | EV-11：`getBomFile` 存在；EV-14：草稿 11 行/16 位号；EV-16：`eda_exec.py:1283` | 无 EDA BOM 导出；草稿缺 3 个 manufacturer、4 个可订购 MPN、8 个 Value、DNP/变体/替代/自供；无库存价格 | NOT VERIFIED |
| 保存 + 关闭重开 | `eda_exec.py apply --save` / `save` / `reopen-check` | `eda_exec @ dc62f20`；`4.1.78.34f5b8d9`；ENV-A | 2026-10-22 | EV-01：`save.saved=true`、after 60/44；reopen `status=match`、16 parts/34 wires；EV-02 同类 | `save` 返回 true 只是调用成功；F1 `reopen-check` 的 `closed_session=null`（未记录显式关闭，可能由 apply 自有会话隐式关闭）；无页身份校验 | VERIFIED |
| 重开一致性判据 | `eda_exec.py reopen-check`（`compare_snapshots`） | `eda_exec @ dc62f20`；ENV-A/C | 2026-10-22 | `eda_exec.py:1163-1200` 只比 parts/wires；EV-01 reopen comparison 只有 parts/wires；EV-12：F1 快照删 1 个 netport 仍 match、翻 mirror 仍 match、同号重复删一个仍 match | 缺 netports、网络标签/attributes、mirror、BOM/PCB 标志、页身份；坐标 `round(3)` 精确相等与 apply 0.01 容差口径不一致 | PARTIAL |
| 原理图 DRC/ERC | 无（官方 `SCH_Drc.check` 未封装） | `4.1.78.34f5b8d9`；ENV-B | — | EV-11：`SCH_Drc.check` 存在；EV-16：`eda_exec.py:1284` `sch_drc=not_implemented`；EV-17：README:81 明确未运行 | 无 DRC/ERC；DRC 通过也不能替代连接回读/看图 | NOT VERIFIED |

## 3. PCB 能力矩阵

> **重要边界**：本节所有 `VERIFIED` 均来自原始 `lceda-pro invoke` 探针，不是 `eda_exec.py`。`eda_exec.py` 没有 PCB 命令族（见第 3 节末行）；Skill 用户目前不能通过本桥执行本节任何一项。原始探针的工程是 scratch 副本，所有写入只落在 `probe*-copy.eprj2`，原始 `base-copy.eprj2` 的 mtime 与 SHA256 未变。

| 能力项 | 执行入口 | 工具版本 / 环境 | 验证日期 | 证据 | 限制 | 状态 |
|---|---|---|---|---|---|---|
| 读取：PCB 图元/焊盘/网络/层 | `lceda-pro invoke --ext-uuid eda` + probe JS（`PCB_PrimitiveComponent.getAll`、`PCB_PrimitiveLine.getAll`、`PCB_Layer.getAllLayers`、`PCB_Net.getAllNets`） | `4.1.78.34f5b8d9`；ENV-A（半离线 headless） | 2026-10-22 | EV-03：33 components/98 lines/24 polylines/0 vias/1 pour/1 poured/83 pads/289 layers/17 nets；EV-06：F1 PCB 16/56/11 | 原始 CLI 探针，不是 `eda_exec`；页选择/激活手工；无全在线 | VERIFIED |
| 建板/建 PCB | `dmt_Board.createBoard(schUuid)` → `dmt_Pcb.createPcb(boardName)` | `4.1.78.34f5b8d9`；ENV-A | 2026-10-22 | EV-06：`create_pcb=f474561fe8e183f1`；`boards_after` 含 `F1-USB-MCU-C`；EV-03 工程树 | `createPcb` 对不存在的板名静默返回 undefined（审计 F-01）；必须先 `createBoard`；适配器未实现 | VERIFIED |
| 原理图→PCB 导入（器件/网络） | `pcb_Document.importChanges(schUuid, true)` | `4.1.78.34f5b8d9`；ENV-A | 2026-10-22 | EV-06：`import_result=true`；counts 16 components/56 pads/11 nets/0 lines；重开仍 16/56/11 | 只导入器件/网络；不建板框、不布线；DRC 报 Connection Error；适配器未实现 | VERIFIED |
| 器件单体创建/放置 | `PCB_PrimitiveComponent.create(flatRef, ...)`；`lib_Device.search` | `4.1.78.34f5b8d9`；ENV-A | 2026-10-22 | EV-07：flat ref 在 layer 1、x=2800、y=-1000 成功创建 DC2；`lib_Device.search('DC005-T20')` 在 x=3200 创建 DC3；`getState_Component`/`getState_Footprint` 均失败 `[object Object]` | 只验证 layer 1、rotation 0、mirror false 的单点坐标创建；旋转/镜像/多层未验证；state 对象签名不接受 | VERIFIED |
| 板框 | `PCB_MathPolygon` + `PCB_PrimitivePolyline.create('', 11, poly, 10, false)` | `4.1.78.34f5b8d9`；ENV-A | 2026-10-22 | EV-05：`poly_ok=true`、layer 11、polys 24→25、delete=true→24 | 无专用板框 API；必须 layer 11；`importChanges` 不自动建框；闭合/尺寸未独立复核 | VERIFIED |
| 布线/过孔 | `PCB_PrimitiveLine.create`、`PCB_PrimitiveVia.create` | `4.1.78.34f5b8d9`；ENV-A | 2026-10-22 | EV-04：line `6251...` GND layer1 w10；via `8f33...` hole20 dia40；`saved=true`；reopen 99 lines/1 via 保持 | 只验证自由区段；未做 pad-to-pad 逐网布线；F1 PCB lines=0；无连通性闭合；autoRouting 未运行 | PARTIAL |
| 铺铜/铜区 | `PCB_PrimitivePour.create/modify`、`PCB_PrimitivePoured.create` | `4.1.78.34f5b8d9`；ENV-A | 2026-10-22 | EV-05：pour `75d6...` 创建；pours 1→2、poured 1；modify/DRC/save/reopen 后仍 2/1；`Poured.create` 文档为空操作 | 只建边框，不生成填充；headless 半离线不重算；GUI 重算未验证 | PARTIAL |
| 层叠 | `PCB_Layer.getAllLayers`（读）；`setTheNumberOfCopperLayers`（API，未执行） | `4.1.78.34f5b8d9`；ENV-B | — | EV-03：layers 289；EV-10：`class-PCB_Layer.json` 有 `setTheNumberOfCopperLayers` | 只枚举层；未改铜层数/叠层/阻抗/盲埋孔 | NOT VERIFIED |
| 设计规则 | `PCB_Drc.get/saveRuleConfiguration`（API，未执行） | `4.1.78.34f5b8d9`；ENV-B | — | EV-10：`class-PCB_Drc.json` 有规则配置读写方法 | 无规则读取/写入/净类/差分对/间距实测 | NOT VERIFIED |
| DRC | `pcb_Drc.check(false, false, false)`；verbose array | `4.1.78.34f5b8d9`；ENV-A | 2026-10-22 | EV-03：`drc=false` + verbose `[Netlist Error]`；EV-04：DRC `[Clearance Error Track-Track 0mm < 0.152mm]`；EV-06：F1 DRC Connection Error | 基线不干净；无错误增量/清零门禁；bool false 语义弱；未跑全规则 | PARTIAL |
| 制造导出：Gerber/CPL | `pcb_ManufactureData.getGerberFile`、`getPickAndPlaceFile` | `4.1.78.34f5b8d9`；ENV-A | 2026-10-22 | EV-03：Gerber size 1,292,201 B；PickPlace size 16,610 B | 只记录文件大小；未用独立查看器核对层/钻孔/原点/板框；样例板不是 F1；F1 无板框/布线 | PARTIAL |
| PCB 保存/重开 | `pcb_Document.save()` + close/reopen | `4.1.78.34f5b8d9`；ENV-A | 2026-10-22 | EV-04：`saved=true`；reopen 33/99/1/2/1，line/via/pour id 保持；EV-06：F1 16/56/11 | 原始 CLI；`eda_exec` 的 save/reopen-check 是原理图专用；重开后未跑全量 DRC | VERIFIED |
| 自动布线/自动布局 | `PCB_Document.autoRouting/startAutoRouting/autoLayout/startAutoLayout`（API，未执行） | `4.1.78.34f5b8d9`；ENV-B | — | EV-10：`class-PCB_Document.json` 列有 alpha/beta 方法 | 未运行；质量/可制造性未知 | NOT VERIFIED |
| `eda_exec` PCB 适配器 | 无 | `eda_exec @ dc62f20`；ENV-D | 2026-10-22（代码核对） | `eda_exec.py:1285` `pcb_read_write=not_implemented_in_this_adapter`；全文件 `pcb_`/`PCB_` 调用仅此 1 处（另有 `:560` coverage 文案与 `:1290` `not_checked`）；SNAPSHOT/SAVE/EXPORT 全 `sch_*` | Skill 用户无法通过 `eda_exec` 做 PCB；只能原始 CLI；doctor 也不实探 PCB | NOT VERIFIED |

## 4. 商城/供应链能力矩阵

| 能力项 | 执行入口 | 工具版本 / 环境 | 验证日期 | 证据 | 限制 | 状态 |
|---|---|---|---|---|---|---|
| EDA 库内器件定位（非商城） | `lib_Device.search(name, ..., 10, 1)` + `supplier_id` 匹配；`lib_Device.getByLcscIds`（API） | `4.1.78.34f5b8d9`；ENV-A | 2026-10-22 | EV-01：16 parts 创建前 `lib_Device.search` 匹配；EV-07：DC3；EV-10：`LIB_Device` | 库元数据，不是商城库存/价格；C 号只是库绑定；`getByLcscIds` 未执行 | VERIFIED |
| 商城选型（商品页/参数筛选） | LCSC Web（无脚本入口） | —；ENV-E | —（2026-10-20 尝试失败） | EV-15：`lcsc-verification.md:83-93` 搜索 `code:500/系统异常`；首页可读；商品页未打开 | 无任何 C 号/参数/价格结果；不能把首页可读当选型能力 | NOT VERIFIED |
| 库存/价格/MOQ/交期/生命周期 | LCSC/JLC Web（无 API；`doc api` 无 stock/price 类） | —；ENV-E | — | EV-15：`manufacturing-routes.md:5/609/804`；`lcsc-verification.md:93` | 全部“待查”；无查询日期/库存/价格 | NOT VERIFIED |
| BOM 生成/核对 | 无 EDA BOM；scratch `make_bom_draft.py` 从 snapshot 生成草稿；官方 `getBomFile` 未封装 | `Python 3.13.15`；ENV-C；`4.1.78`；ENV-B | 2026-10-22（草稿） | EV-14：`f1-bom-draft.csv` 11 行/16 位号；coverage：3 无 manufacturer、4 通用名非 MPN、8 无 Value、无 DNP/替代/自供/变体 | 草稿不是 EDA BOM；无实时商城匹配；无变体/DNP 机器字段 | PARTIAL |
| 替代料 | 无 | —；ENV-D | — | EV-14：`no_alternate_field` 16/16；snapshot 无 alternates 字段 | 无替代料字段/交叉参考/电气等价检查 | NOT VERIFIED |
| 渠道状态：商城库存/SMT 可贴/寄料 | 文档规则；无数据层字段 | `repo dc62f20`；ENV-D | — | EV-15：`jlc-handoff.md:15/18`、`jlc-smt-rules.md:3`、`manufacturing-routes.md:45/167/524`；snapshot `supplier=LCSC`、`other_property.PCB Layer` 全 `Default` | 文档区分状态不等于数据层有渠道字段；`supplier=LCSC` 不是当前可贴 | NOT VERIFIED |

## 5. SMT/制造/烧录/测试能力矩阵

| 能力项 | 执行入口 | 工具版本 / 环境 | 验证日期 | 证据 | 限制 | 状态 |
|---|---|---|---|---|---|---|
| SMT 渠道/可贴性/报价/交期 | JLC SMT Web；官方 `placeSmtComponentsOrder`（API，未执行） | `4.1.78`；ENV-B；—；ENV-E | — | EV-15：`jlc-smt-rules.md:3`（2026-10-20 静态快照）；`manufacturing-routes.md:612`（SMT 帮助页不可读） | 无报价/可贴/库存/交期；无订单 | NOT VERIFIED |
| 制造资料：Gerber/钻孔/CPL/装配图/钢网 | `pcb_ManufactureData.getGerberFile/getPickAndPlaceFile`；其他未执行 | `4.1.78.34f5b8d9`；ENV-A | 2026-10-22 | EV-03：Gerber 1,292,201 B / CPL 16,610 B；无钻孔/装配图/钢网文件 | 只有两件样例板文件；未独立核对；F1 无 PCB 板框/布线，不能生成可制造包 | PARTIAL |
| BOM/CPL/制造文件一致性 | 无 | —；ENV-D | — | EV-14：无 CPL；EV-01：snapshot x/y 是原理图坐标，`other_property.PCB Layer` 全 `Default` | 无 PCB/CPL；无 BOM-CPL-坐标对账 | NOT VERIFIED |
| 下单/DFM/工程审核 | 官方 `placePcbOrder/placeSmtComponentsOrder/placeComponentsOrder`（API，未执行） | `4.1.78.34f5b8d9`；ENV-B | — | EV-10：`class-PCB_ManufactureData.json`；EV-11：`placeSmtComponentsOrder` | 未授权、未执行；无 DFM/报价/工程审核 | NOT VERIFIED |
| 烧录 | 无 | — | — | 无执行记录；EV-17：README:81 明确 NOT RUN | 无编程器/固件/芯片 | NOT VERIFIED |
| 测试/样机 | 无 | — | — | EV-17：README:81；无台架/样机记录 | 无功能/热/EMC/可靠性实测 | NOT VERIFIED |

## 6. 全在线与跨域门槛

| 能力项 | 执行入口 | 工具版本 / 环境 | 验证日期 | 证据 | 限制 | 状态 |
|---|---|---|---|---|---|---|
| 全在线 GUI 验收 | 用户 GUI 会话（`origin=user`） | `4.1.78.34f5b8d9`；ENV-A | 2026-10-22（探测到 2 个 alive user 会话） | EV-08：`final-sessions.json` 2 个 alive `origin=user`；EV-03/EV-01：`online:false`、`half_offline:true` | CLI 会话恒半离线；未操作用户 GUI；全在线结论只能由用户 GUI 复验 | BLOCKED |

## 7. 不能据此宣称

- 不能宣称“Skill 已支持 PCB”：PCB 的所有 VERIFIED 都是原始 CLI 探针；`eda_exec.py` 没有 PCB 路径（见第 3 节末行）。也不能把原始 API 的 `placePcbOrder/placeSmtComponentsOrder` 当成已下单或已验证。
- 不能宣称“修改/删除已验证”：修改只有 Fake/复现代码路径，删除连桥入口都没有；官方 API 的 `delete` 只是存在性探测。
- 不能宣称“93/93 verified 等于全属性验证”：逐项验证不比较位号值、封装、镜像、制造商/供应商文本、`other_property`、net flag 类型、net port 方向；netports 也不在重开比较域内。F1 的 93/93 应表述为“计划项存在性与网名/坐标/旋转等窄字段通过”。
- 不能宣称“重开 match 等于所有内容一致”：F1 的 reopen 只比 parts 与 wires；删除一个 netport、翻转 mirror、删除同号重复件之一，仍可能返回 match。
- 不能宣称“8/8 基准是验收”：benchmark 只验证 `expected_codes` 子集，任意返回全部 code 的假检查器也能 8/8；真实 F1 snapshot 不能直接喂入检查器。
- 不能宣称 BOM/库存/价格/SMT 可贴/DFM/烧录/测试已验证：这些没有真实执行记录；文档中的规则和 2026-10-20 的失败记录不能替代数据。
- 不能宣称全在线验收：所有 EDA 证据均为半离线；全在线只能由用户 GUI 会话复验。

## 8. 下一轮可直接执行的入口（按优先级）

1. **PCB 适配器**：在 `eda_exec.py` 增加 `pcb-read`、`pcb-outline`、`pcb-place`、`pcb-route`、`pcb-via`、`pcb-pour`、`pcb-drc`、`pcb-save`、`pcb-export`、`pcb-reopen-check`；页选择用 `dmt_Pcb.getAllPcbsInfo` + `openDocument/activateDocument` + `getCurrentDocumentInfo` 校验；doctor 增加 `pcb_read/pcb_write/pcb_export/pcb_drc` 实探。
2. **修回读与验证链**：SNAPSHOT_JS 增加 `read_errors`；`pins_complete/attributes_complete` 真正被 Python 消费；逐项比较 `designator/footprint/mirror/manufacturer/supplier/other_property`；使用执行返回的 `primitive_id`；创建前做工程级位号唯一性检查；reopen 比较加入 netports、attributes/网络标签、mirror、BOM/PCB 标志与页身份。
3. **补删除与网络标签**：封装 `SCH_PrimitiveComponent.delete` 与 `SCH_PrimitiveAttribute.createNetLabel`，定义匹配键、幂等、冲突与回读规则；先在副本上做删除/重建回归。
4. **BOM/CPL/manifest**：封装 `sch_ManufactureData.getBomFile` 与 `pcb_ManufactureData.getBomFile/getPickAndPlaceFile`；生成 BOM、CPL、manifest（SHA256、大小、生成时间、客户端 build、工程/页 UUID、plan/snapshot hash）；BOM 草稿显式标注 `待查`。
5. **供应链与 SMT**：用真实 LCSC/JLC 页面建立查询记录（C 号、价格、库存、MOQ、包装、交期、生命周期、SMT 可贴），分“商城库存 / SMT 可贴 / 寄料”三列；没有查询日期与来源的不写数字；下单/支付/上传工程保持不执行，除非用户明确授权。
6. **全在线 GUI 验收**：由用户在自己的全在线 GUI 会话中复验 F1 或后续板；在此之前，所有“全在线”结论保持 BLOCKED。烧录与样机测试单独建立台架记录，不能用 EDA/文档证据替代。

## 9. 审计边界

- 本矩阵未新增真实 EDA 写入；引用的 F1、EDA-2026-10-21、PCB 探针均为本轮审计域已保存的真实执行证据。官方 `doc api` 查询是本轮新增的只读探测。
- F1 的 `base-copy.eprj2` 不在仓库；`apply-result.json`/`reopen-check.json` 中部分路径为 `<scratch>`。因此 F1 证据可核验产物与回读结果，但不能仅凭仓库重放真实写入；重放需要同版本客户端和已授权工程副本。
- 未连接 LCSC/JLC 实时页面，未询价、未下单、未上传工程、未支付。
- 未做电气/热/EMC/SI/DFI/DFM/安规/可靠性/烧录/样机测试；这些不因本矩阵的 VERIFIED 而被验证。
- 未审计 `origin/main` 在 `dc62f20` 之后的 3 个 docs-only 提交；未审计仓库全量测试之外的其他脚本内容正确性。
