# 第三轮任务台账（2026-10-22）

- 仓库/基线：`C:/Users/jlc/work/hds-round3`，审计基线 `dc62f20`；执行修复已同步到 `origin/main` `0fe5cf8` 之上（`feat/round3-engineering`）。
- 本轮性质：11 个审计域只读审计 + 综合台账 + P0 执行器修复。审计阶段除台账/协议/矩阵/覆盖复核外未改代码；修复阶段改 `eda_exec.py`、执行契约、测试与证据，详见 [executor-fixes-2026-10-22.md](round3/executor-fixes-2026-10-22.md)。
- 测试基线：审计时 `Ran 141 tests / OK`；修复后 `Ran 181 tests / OK`（其中 `tests.test_eda_exec` 53 项、`tests.test_netlist_diff` 10 项）。
- 真实 EDA：F1/EDA 证据来自嘉立创EDA专业版 `4.1.78.34f5b8d9` 半离线会话；第三轮仅 PCB 能力探针在 scratch 副本上真机执行，其余审计为代码走查、仓库证据复核与离线复现。
- 证据根：`AUD = C:/Users/jlc/work/hw-deepdive-scratch/round3-audit/`。仓库内路径均相对仓库根。
- 本轮审计产出：14 条经交叉复核的 `confirmed_findings`（13 DEFECT + 1 GAP；0 条被否决，0 个审计域失败），另有各审计域未进入交叉复核的 `AREA` 级发现。两者分开标注，不混为同一证据等级。
- 交叉复核后的严重度分布：critical 1（F-01，严重度仍有 critical/medium 分歧）、high 8、medium 4、low 1。`AREA` 级发现未参与该分布。

## 0.1 2026-10-22 P0 执行器修复覆盖（优先于下文旧状态）

下表是修复后的实际状态；未列出的任务仍按下文审计快照。所有修复均在独立副本、CLI 自有 headless 会话中验证，未操作用户 GUI 会话。

| ID | 修复后状态 | 证据 |
|---|---|---|
| B1-01 读取失败折叠为空 | PARTIAL（适配器已修，真实故障注入 NOT RUN） | `docs/round3/executor-fixes-2026-10-22.md` §1；`docs/evidence/round3-2026-10-22/round3-fix-snapshot.json` |
| B2-01 位号/执行 id 不参与验证 | DONE（真实 create 已验证） | `apply-r999.json`；50 项 EDA 单测 |
| B2-02 / B3-02 位号唯一性 | DONE（计划/页/工程三级） | `dry-r1.json`（7 个跨页占用者）；`f1-designators.json` |
| B2-03 标记类型/端口方向 | DONE（真实回读） | `f1-dryrun.json` 93/93 skip；单测 `NetMarkerVerification` |
| B2-04 属性/BOM 标志 | PARTIAL（属性已验；已有器件 BOM/PCB 修改明确不支持） | 单测 `VerificationCoverage` |
| B3-01 工程级位号 | DONE | 10 页/78 器件/13 组重复；`designators` + `--project-designators` |
| B4-01 写前条件 | PARTIAL（单对象 expected 已实现；全快照 hash NOT RUN） | 单测 `stale_target`；代码 |
| B4-02 页身份冻结 | DONE | 真机 apply 固定 `page_uuid`；多页 schematic 拒绝猜测 |
| B6-01 / B6-03 孤儿与超时 | PARTIAL（代码+单测，真实超时注入 NOT RUN） | 代码；`partial_unknown` 路径 |
| B7-01/B7-02/B7-03 重开比较 | DONE | `reopen-post2.json` match（17/27/16/34）；`reopen-pre.json` mismatch；零长度线归一 |
| B8-01/B8-02/B8-03 版本与会话 | DONE/PARTIAL | 版本门禁、origin 门禁、reopen 会话工程核对；错误会话关闭未真机注入 |
| T-01 测试覆盖 | PARTIAL | 23→53 EDA 测试、新增 10 个网表 diff 测试；全仓 181 通过；函数级覆盖 NOT RUN |

## 0.2 2026-10-22 F1 电气修订（rev3）

| 项 | 状态 | 证据 |
|---|---|---|
| C103 10µF 陶瓷 → C107 22µF 35V 钽 | PARTIAL（换型完成，稳定性未实测） | `docs/evidence/f1-rev3-2026-10-22/`；ESR 500mΩ；网表 `C107-1=3V3, C107-2=GND`；未取得 C2891839 原厂手册，未验证并联网络/环路稳定性/负载瞬态 |
| IO2 10k 上拉 | DONE | 网表 `IO2: U101-2, R107-2`；DRC 悬空列表移除 IO2 |
| EN/RST 100nF RC | DONE | 网表 EN/RST 均含新电容与原有引脚 |
| U101 本地 10µF | DONE（原理图） | C106 加入 3V3/GND；PCB 近端约束未执行 |
| VBUS TVS / USB-C 壳脚 GND | DONE（原理图） | D102 SMBJ5.0A；J101-1..4 在 GND |
| CC/D+/D- ESD、VBUS 保险、J102 串阻 | NOT RUN | 见 F1 修订报告 §6 |
| 重排 C3 | NOT RUN | 图面仍拥挤；标题栏仍 V1.0 |
| DRC | PARTIAL | 5 warn（4 超框 + 6 未用 USB 数据脚），0 error；无豁免表 |
| 网表 diff | DONE（本次电气修订） | `pin_net_changed=0`；纯重排前后 diff 未做 |
| 人工审图 C6 | NOT RUN | — |
| 门禁复核（零长线/网表/删除 expected） | DONE（单测+真机重开） | 零长线纳入重开比较；网表严格拒绝无效输入；删除按类型强制 expected；191 tests OK；`f1-gatecheck-reopen.json` match |

## 0. 状态与证据口径

| 状态 | 定义 | 反例（不得记 DONE） |
|---|---|---|
| DONE | 本轮复跑/复核有可复核证据，交付物与声明范围一致 | 只有文档描述、只有目录/数量、只在旧轮次记录 |
| PARTIAL | 有可用交付物，但覆盖范围、精度或验收明显小于声明 | 8/8 只证明 recall；F1 连接通过但排版/电气未过 |
| NOT RUN | 没有执行记录或证据 | 文档写了步骤、但没有实际运行产物 |
| BLOCKED | 需要外部条件（全在线 GUI、账号、实物、仪器）才能继续 | 把半离线结论当全在线；把计算当实测 |
| DEFECT | 已证实的实现/内容错误，会产生错误结果或错误“通过” | 用“设计意图”解释与代码/数据不符 |
| GAP | 能力、证据或契约缺口；未证明为错误实现 | 把“未实现”写成“已验证” |

判定规则：同一任务同时存在已完成部分与 DEFECT 时，按最低状态记，并在“未完成边界”说明已完成部分。来源列：`R2` = 第二轮结转；`A-CONF` = 本轮交叉复核确认；`A-AREA` = 本轮单域审计发现（未交叉复核）；`A-GATE` = 本轮基线/证据复核。

## 1. 本轮结论摘要

> 下表是审计时状态，不是修复后的当前状态；已修复项见 §0.1，详细证据见 [executor-fixes-2026-10-22.md](round3/executor-fixes-2026-10-22.md)。

| 工作包 | 主题 | 本轮最高状态 | 一句话结论 |
|---|---|---|---|
| A | 执行桥读取完整性与回读验证 | DEFECT | 读取失败被折叠为 null/空数组，验证不比对位号，`verified` 可比真实对象宽 |
| B | 写入安全、身份、重试、版本、测试 | DEFECT | 位号唯一性、写前条件、会话来源、重开身份均未闭合；23 项测试只覆盖理想路径 |
| C | 原理图几何检查与 8 类基准 | DEFECT | 8/8 只验证 recall；真实快照不能直接喂入；近失端点/异网导线被误判 |
| D | F1 原理图证据与 C2/C4 | DEFECT | 连接与保存证据成立；AMS1117 输出电容、IO2 悬空、多余导线与排版仍不合格 |
| E | PCB 纵向闭环 | GAP | 客户端 PCB API 真机可用，但 `eda_exec.py` 完全没有 PCB 路径 |
| F | 制造与供应链 | GAP | 文档能区分商城/SMT，但无 BOM/CPL/Gerber/manifest 能力与实时数据 |
| G | 电源与热计算 | DEFECT | Boost IMAXOUT 公式错误、SLVA118A 封装列错位，已传播到选型文档 |
| H | 电源与电池 | DEFECT | PWR-08 UVP 零余量、F14 钳位漏电源电压、续航缩放错误 |
| I | 模拟采集与接口 | DEFECT | 高侧采样失调差 10 倍、I²C 结论与同文修正矛盾、差分拓扑图错 |
| J | Skill L1/L2/L5 | DEFECT | README 宣称场景试跑但无证据；场景检查、盲测、安装分层均不足 |
| K | 评测与新手/工程师路径 | GAP | 没有 Agent 行为评测；35 个场景未真实执行；旧试答评分无效 |
| L | 台账、状态、交付门禁 | DEFECT | 多份状态文档与真实证据冲突；无统一六级交付定义；round2 台账有过期项 |

### 1.1 工作包 A-L 与审计域映射

| 工作包 | 本轮审计域 | 主要文件 |
|---|---|---|
| A | 域 1：EDA 执行桥读取完整性/回读/保存重开/测试 | `design-hardware/scripts/eda_exec.py`、`tests/test_eda_exec.py`、`design-hardware/references/eda-execution.md` |
| B | 域 2：位号/跨页身份、快照并发、重试幂等、版本与会话边界 | 同上（`eda_exec.py` 的 reconcile/apply/reopen/doctor） |
| C | 域 3：原理图排版几何检查与 8 类离线基准 | `design-hardware/scripts/sch_layout_check.py`、`schematic_benchmark.py`、`assets/schematic-benchmarks/benchmarks.json` |
| D | 域 4：F1 原理图证据与 C2/C4 | `docs/evidence/f1-2026-10-22/`、`references/projects/p04-usb-mcu-board.md` |
| E | 域 5：PCB 纵向闭环 | `eda_exec.py`（PCB 路径）、嘉立创EDA Pro 4.1.78 CLI、`AUD/pcb-closed-loop/` |
| F | 域 6：制造/供应链与 F1 制造候选包 | `references/manufacturing-routes.md`、`jlc-*`、`selection/lcsc-verification.md`、`AUD/f3-bom/` |
| G | 域 7：电源与热计算 | `references/calculations/power-thermal.md`、`design-cards/power/p01-p03`、`scripts/calculate.py`、`thermal_calc.py` |
| H | 域 8：电源与电池 | `references/calculations/energy-battery.md`、`design-cards/power/p05-p08/p12`、`failures/f02/f09/f13/f14` |
| I | 域 9：模拟采集与接口 | `references/calculations/analog-adc.md`、`interconnect.md`、`design-cards/analog/a01-a10`、`interfaces/i01-i12` |
| J | 域 10：Skill L1/L2/L5 与检索分层 | `design-hardware/SKILL.md`、`references/` 引用关系、`README.md` |
| K | 域 10（H 评测 / I 新手路径）+ 域 11（A2/H5） | `assets/scenarios.json`、`tests/test_scenarios.py`、`docs/evidence/deepdives-2026-10-22/` |
| L | 域 11：A5 未完成事项去重 + A2 交付状态分级 + 跨域门禁 | `docs/task-ledger-round2.md`、`merge-review.md`、`expansion-report.md`、`doctor.json`、`product-acceptance.md` |

> 说明：A–L 是第三轮工作包编号，与 round2 的 A1–H5 不是同一套编号；round2 项在 §2 单独映射，不能按字母直接对应。

## 2. round2 结转与状态修正

第二轮台账的 DONE 项并非全部仍成立。本轮按“实际证据”重判如下；未完成项全部保留，不因第三轮新增内容而删除。

| round2 项 | round2 记录 | 本轮复核结论 | 第三轮状态 | 去向 |
|---|---|---|---|---|
| A1 执行能力诊断 | DONE | doctor 分层存在，但 `project_writable` 仍为 `not_tested`；写入只在 F1 scratch 副本发生，未由 doctor 证明 | PARTIAL | L-14, A-06 |
| A2 意图到动作映射 | DONE | 能力矩阵存在且范围基本诚实；PCB、BOM、DRC、网络标签均明确未实现 | DONE（范围限定） | E-01, F-01 |
| A3 中断恢复与重复执行 | DONE | “超时先回读”未实现；`execution.results` 不参与验证；重试会留下 R? 孤儿并重复创建 | DEFECT | B-04, B-08 |
| A4 对象身份与局部修改 | DONE | 身份字段有回读，但验证不比对 designator，且丢弃执行返回的 primitive_id；改位号未生效仍 verified | DEFECT | A-02, A-04 |
| A5 保存、重开与交付核验 | DONE | save/reopen 主链路成立；但 reopen 比较域缺 netports/attributes/mirror/BOM/PCB，`closed_session=null`，且可关闭无关会话 | PARTIAL | B-06, B-09, F-07 |
| B1 原理图排版基准集 | DONE | 8/8 可执行，但只验证 expected_codes 子集；任意全 code 假检查器仍 8/8 | PARTIAL | C-01, C-02 |
| B2 模块内部几何设计 | DONE（方法+真机案例） | “按引脚不按外框”方法成立；多单元/隐藏电源脚仍未真机验证，且基准引脚声明落在本体内制造误报 | PARTIAL | C-02, C-10 |
| B3 页面组合与阅读顺序 | PARTIAL | 仍无真实多页工程、图框尺寸切换或阅读顺序验收；只有单页 F1/EvidenceDemo | PARTIAL | C-10 |
| B4 连线与标签边界 | DONE | 网络端口按名合并有真机证据；总线/差分作用域仍只写规则，网络标签无 op、reopen 不比较 netports | PARTIAL | A-05, B-09 |
| B5 图面检查与修复循环 | DONE | 检查器有标题栏/模块框/悬空/一脚多网/标签落点；但 D6 近失/异网误判、模块框不查穿线、F1 拥挤不可发现 | PARTIAL | C-04 至 C-09 |
| C1–C5 PCB | NOT RUN | 客户端 PCB API 已在 scratch 真机验证；适配器仍无 PCB 路径。C1/C2/C3/C5 达到手工探针 PARTIAL，C4 真实布线仍 NOT RUN | PARTIAL / NOT RUN | E-01 至 E-15 |
| D1–D5 嘉立创业务 | NOT RUN | 文档层已区分商城购料/SMT/寄料/已下单；实时库存、价格、MOQ、SMT 可贴、DFM、下单仍无数据 | PARTIAL（文档）/ BLOCKED（实时） | F-09, F-10, F-14 |
| E1–E5 新手/工程师行为 | NOT RUN | 场景资产与路由存在，但没有真实 Agent 对话试验；35 个场景只做结构/路由检查 | NOT RUN | K-01 至 K-08 |
| F1 USB 供电 MCU 小板 | PARTIAL | 连接/网表/保存/重开证据成立；新增电气 DEFECT（AMS1117 输出电容、IO2 悬空）、多余导线、排版不合格 | PARTIAL + DEFECT | D-01 至 D-12 |
| F2–F5 | NOT RUN | 未开始；无可复核项目证据 | NOT RUN | D-12, K-08 |
| G1–G5 | NOT RUN | round2 台账“未新增跨模块反例”已过期：PR #3 已加入 F23–F33 与“跨模块 12 类覆盖”表；但均为构造案例，G2–G5 未做 | G1 PARTIAL；G2–G5 NOT RUN | L-05 |
| H1–H5 | PARTIAL | H2 回归可复跑（141 tests）；H3 路由存在；H4 只覆盖 PNG/NET 哈希；H1 关键资料抽样审计、H5 独立集成复核未完整覆盖 EDA 桥 | H1 NOT RUN；H2 DONE；H3 DONE；H4 PARTIAL；H5 PARTIAL | K-05, L-07 |

## 3. 工作包 A：执行桥读取完整性与回读验证

范围：`design-hardware/scripts/eda_exec.py` 的 SNAPSHOT_JS、`read_snapshot`、`read_with_retry`、`verify_against_snapshot`，以及 `tests/test_eda_exec.py` 的覆盖。

| ID | 状态 | 来源/复核 | 证据 | 未完成边界 | 依赖 | 解阻条件 |
|---|---|---|---|---|---|---|
| A-01 | DEFECT | A-CONF B1-01（严重度由 critical 下调为 high） | `eda_exec.py:378-380` safe/safeAsync 吞异常；`:458-480` 每字段 safe；`:481-498` 按 ComponentType 过滤，getter 失败时图元从 parts/netflags/netports 同时消失；`:533-540` counts 仍计入；`:553-563` coverage；`:1218-1239` Python 侧无 consumer。复现 `AUD/eda-exec/repro_results.json` F1；独立复现 `AUD/verify-b1-01/` | 未在真实客户端注入 `getState_Designator` 异常；编辑器是否允许重复位号未验证；“真实工程出现两个 R1”仍是注入级结论 | 无 | SNAPSHOT_JS 增加 `read_errors[]`；coverage 有 Python consumer；read_errors 非空时 apply 拒绝、reopen-check 报 incomplete；补 null designator/缺 pins 单测 |
| A-02 | DEFECT | A-CONF B2-01（critical 下调 high） | `eda_exec.py:1101-1133` designator 只用于定位，候选比较无 designator；`:1430-1439` execution 只在输出中，不进验证；`APPLY_JS:637-642` 已返回 primitive_id/designator/unique_id。复现 `AUD/eda-exec/repro_results.json` F2；`AUD/B2-01/verify_results.json` S1–S3 | 真实计划 18 个 part 操作均无 match.position，S2 路径可触发；真实编辑器自动编号 R? 未观测；modify 位号静默丢弃未在真机复现 | A-01 | command_apply 传 execution key→primitive_id；逐字段比较 designator/unique_id/component/supplier/footprint/x/y/rotation/mirror；R? 报 designator_mismatch 而非 part_not_found |
| A-03 | DEFECT | A-AREA（域 1） | `eda_exec.py:485-488` 引脚读取失败返回 `[]` 且 `pinsComplete` 保持 true；`:509-510` 属性读取失败时 `attributesComplete=0<=500` 为 true；`:553-563` 标志无 consumer；`docs/evidence/f1-2026-10-22/snapshot.json:2668-2669` `attributes_included=false` 仍 `attributes_complete=true` | attributes 分支经 CLI 当前不可达（`read_snapshot` 默认 False，无调用者传 True）；未做截断/读取失败注入 | A-01 | 区分“读取成功但为空”与“读取失败”；pins/attributes 失败即 incomplete；CLI 增加 attributes 入口 |
| A-04 | DEFECT | A-AREA（域 1、域 6） | `eda_exec.py:1116-1133` 只比 part/supplier/x/y/rotation；`APPLY_JS:626-641` 写入 manufacturer/manufacturer_id/supplier/name/other_property；`references/eda-execution.md:48` 却声明回读这些字段；F1 `apply-result.json` 的 observed 无 footprint/manufacturer | 客户端 `sch_PrimitiveComponent.modify` 对 manufacturerId/supplierId/otherProperty 字段名接受度未真机验证 | A-02 | 每个计划字段产生 expected/observed；写入未生效即 failed；补字段表驱动测试 |
| A-05 | DEFECT | A-AREA（域 1） | `SNAPSHOT_JS` netflag 只读 name/x/y/rotation/mirror，无 type；netport 只读 net/name/x/y/rotation，无 direction/mirror；`verify_against_snapshot:1120-1131` 只按网名+坐标。F1 `apply-result.json` 16 个 net_port 的 observed 只有 `{net,at,found}`；plan 实际使用 BI 12/OUT 2/IN 2、Power 14/Ground 13 | 客户端是否有 netflag type/netport direction 的可读 getter 未确认；rotation 读回但未比较 | A-02 | 先 `doc api`/真机确认 getter；能读则逐项比较，不能读则 verification 标 `unverified_fields`，不得写 verified |
| A-06 | DEFECT | A-AREA（域 1） | `command_save:1461-1469` 在 CLI stdout 只有日志 JSON 时抛 AttributeError；`command_reopen_check:1502-1508` 快照缺失抛 FileNotFoundError；`AUD/eda-exec/probe-output.txt` F14/F16 | 只验证了异常类型，未验证所有 CLI 失败模式的 JSON/退出码契约 | 无 | 所有命令入口包 EdaCommandError；补 save 输出形状/文件缺失/坐标为空测试 |
| A-07 | GAP | A-AREA（域 1） | `eda_exec.py:1226-1239` 3 次失败统一抛 `EDA_PROJECT_NOT_READY`，原始 `EDA_TIMEOUT` 只在 `detail.last`；`AUD/eda-exec/probe-output.txt` F17 | 未做真实超时/页不存在注入 | 无 | 保留原始错误码；区分 timeout/page_not_found/project_not_ready；测试断言 code |
| A-08 | PARTIAL | A-AREA（域 1） | `tests/test_eda_exec.py` 23 项通过；`AUD/eda-exec/coverage_report.json` 23 个测试只执行 60 个函数中的 34 个、459/1641 行；`command_reopen_check/read/save/export/_extract_json/LcedaPro._run` 零覆盖；`tests/test_eda_exec.py:321` 只是源码字符串断言 | 只覆盖理想路径；无读取失败、位号冲突、漂移、会话来源、版本、重开身份用例；未在真实 EDA 跑 | A-01 至 A-07 | 增加故障注入与契约测试；把字符串断言替换为行为断言；目标覆盖 reopen/read/save/export |
| A-09 | GAP | A-AREA（域 1、域 6） | `eda_exec.py:1218` `include_attributes=False` 且 argparse 无 `--include-attributes`/`--max-pins`；CLI 快照 `attributes=[]`、`counts.attributes=null`、pins 预算恒 6000 | 无；属入口缺失 | A-03 | CLI 增加 `read --include-attributes`、`--max-pins`；文档写清默认边界 |

## 4. 工作包 B：写入安全、身份、并发、重试、版本与测试

范围：`reconcile`、`command_apply`、`command_save`、`command_reopen_check`、`command_close`、`command_doctor`、`PAGE_SELECT_JS`、计划校验与测试。

| ID | 状态 | 来源/复核 | 证据 | 未完成边界 | 依赖 | 解阻条件 |
|---|---|---|---|---|---|---|
| B-01 | DEFECT | A-AREA（域 2 B3） | `eda_exec.py:915-1081` reconcile 只按当前快照匹配；`tests/test_eda_exec.py:116-121` 只覆盖成功后重复 apply；`AUD/eda-exec/probe_b3_b4_b6_b8.py` 证明计划内重复位号、改位号撞车、新器件占用已有位号均放行 | 位号唯一性只查当前页；跨页/工程级重复未查；真实多页工程无证据 | A-01 | 计划级先做 designator 集合冲突；跨页用工程页清单查重；新器件占用已有位号必须 conflict；补三类单测 |
| B-02 | DEFECT | A-AREA（域 2 B4） | `command_apply:1395-1430` 读前快照后直接写；不校验工程/页 UUID、快照时间、内容哈希；读后被用户改动会被静默覆盖 | 真实并发编辑未注入；未验证客户端是否另有乐观锁 | 无 | plan 记录 before 的 project/page UUID + snapshot hash/time；写前重读并比对；漂移则拒绝并给出 diff |
| B-03 | DEFECT | A-AREA（域 2 B4） | `PAGE_SELECT_JS:376-420` 请求 current 时解析一次，写后 `command_apply:1401` 再解析一次；仅 `schematic_name` 时取 `s.page[0]`；写后不校验 page UUID | 真实多窗口/多工程/同名页未验证 | 无 | 选择结果冻结为 page_uuid；写后重读 selection 并断言一致；`schematic_name` 多页时要求 page_name/uuid |
| B-04 | DEFECT | A-AREA（域 2 B6） | `command_apply:1430-1451`；`AUD/eda-exec/probe-output.txt` D/F；超时/失败后重试会重复创建，R? 孤儿不会被认领 | 真实超时未注入；编辑器对 R? 的自动分配规则未验证 | A-01 | 创建前按 planned position+part+supplier 认领 R? 孤儿；未知结果先回读；重试只在确认未写入后允许 |
| B-05 | DEFECT | A-AREA（域 2 B8） | `close_owned:1249-1255` 只拒绝 `origin=='user'`，未知 origin 可被 `--destroy`；`--session` 可指向用户会话并写入；`tests/test_eda_exec.py:329-335` 只测 user | 其他客户端版本的 origin 取值未验证 | 无 | origin 白名单（self/cli/headless）；未知 origin 视为 user；写入用户会话需显式 unsafe 开关并记录 |
| B-06 | DEFECT | A-AREA（域 2 B8） | `command_reopen_check:1502-1514` 传 `--session` 即 `close_owned`，不校验该会话属于目标工程；比较只比内容，不比 project/page 身份；netports 完全不比较 | 真实多工程同时打开未验证 | B-05 | 关闭前核对 session→project 映射；比较 project UUID/page UUID；netports/flags/mirror/BOM/PCB 纳入 |
| B-07 | DEFECT | A-AREA（域 2 B8） | `command_doctor:1268-1300` 不检查 `versionMatch`/`resultChannel`/online 状态；任意客户端版本都可写入；`doctor.json` 仍声称 DRC/BOM available（见 L-04） | 其他版本行为未测；全在线门禁未设计 | 无 | doctor 记录 build/versionMatch/online；写入命令设最低版本与半离线提示；不匹配时 EXIT_UNAVAILABLE |
| B-08 | DEFECT | A-AREA（域 2 B6） | `command_apply:1430-1439` 不保存/不使用 `execution.results` 的单项 ok 与 id；结果不明时不自动回读；`references/eda-execution.md:99` 与 `docs/task-ledger-round2.md:20` 声称“超时先回读”，代码无此路径 | 无真实超时注入；未验证客户端异步丢弃频率 | 无 | 未知结果强制回读；单项 results 与 plan key 对齐；执行返回 id 进验证 |
| B-09 | DEFECT | A-AREA（域 1、域 2 B7） | `compare_snapshots:1163-1211` 只比 parts/wires/netflags；不含 netports、attributes、mirror、add_into_bom/add_into_pcb；`AUD/schematic-layout` 与 `AUD/eda-exec` 复现：F1 快照删 1 个 netport 仍 match、翻转 mirror 仍 match、删两个同号件之一仍 match；对角导线 `line=[0,0,10,10]` 解析为空且删线仍 match；坐标 `300.0 vs 300.004` 报 mismatch 而 apply 侧 0.01 容差判 verified | 真实 F1 工程未做删端口/翻 mirror 实验；编辑器取整规则未测 | A-01 | 比较域扩展；坐标统一容差；netport 按 net+at+identity 比较；解析失败必须报 incomplete |
| B-10 | PARTIAL | A-AREA（域 2） | `tests/test_eda_exec.py` 23 项；覆盖报告见 A-08；无位号唯一性、漂移、会话来源、版本、重开身份用例 | 只覆盖理想路径；无真实 EDA 故障注入矩阵 | A-01 至 B-09 | 以 B-01 至 B-09 每条至少一个失败用例为退出标准 |
| B-11 | GAP | A-AREA（域 1） | `validate_plan:727-755` 接受 `page.current=true` 和 `settle_ms`；`command_apply:1401` 的 page_args 只保留 page_uuid/schematic_name/page_name；`settle_ms` 全仓库除校验外无使用点 | `current` 没有页身份；`settle_ms` 被静默丢弃；未验证是否本应影响异步等待 | B-03 | `current` 解析一次后固化为 UUID；`settle_ms` 要么实现要么删除并报 input error |
| B-12 | DEFECT | A-AREA（域 1） | `SNAPSHOT_JS` netflag x/y 走 safe，坐标读空为 null；`compare_snapshots` 的 `_round(None)`/排序会让 reopen-check 崩溃（域 1 报告 F14 同类） | 未在真实空坐标快照上执行 reopen-check；只做代码路径判断 | B-09 | 对 netflag 坐标做 None 检查并报 incomplete，不让 `_round` 抛 TypeError |

## 5. 工作包 C：原理图几何检查与 8 类离线基准

范围：`design-hardware/scripts/sch_layout_check.py`、`design-hardware/scripts/schematic_benchmark.py`、`design-hardware/assets/schematic-benchmarks/benchmarks.json`、`design-hardware/references/schematic-benchmarks.md`、`design-hardware/references/schematic-layout.md`。

| ID | 状态 | 来源/复核 | 证据 | 未完成边界 | 依赖 | 解阻条件 |
|---|---|---|---|---|---|---|
| C-01 | DEFECT | A-CONF R3-SCH-01（high 下调 medium） | `schematic_benchmark.py:35-44` 只算 `expected_codes - observed`；`tests/test_schematic_benchmarks.py:40` 只断言子集；`AUD/schematic-layout/overreport-control.txt` 全 code 假检查器仍 8/8；`AUD/verify-R3-SCH-01/` 确认全仓其他测试会在 `tests/test_offline_tools.py` 拦截全 code 假实现 | 只影响 8 个基准的精度门禁；不影响检查器 `electrical_verified=false` 的自我声明 | 无 | benchmarks 增加 `expected_findings`（code+objects）或 `forbidden_codes`；runner 对 `observed-expected` 失败；加“全 code 假检查器必须失败”负向测试 |
| C-02 | DEFECT | A-AREA（域 3） | `benchmarks.json` B2 的 w-vin/CIN、B3 的 w-fb/A1、B6 的 w-brake/M1 是引脚声明落在器件 bbox 内造成的未声明 `wire_enters_bbox`；`AUD/schematic-layout/extras-summary.txt` 6/8 有未声明发现、5/8 有未声明 code；B7 的 A1/frame-main 是真实边界穿越 | 只有 B7 是真实几何；B2/B3/B6 属基准自身声明问题；未逐张对照 8 张真机图（仓库没有） | C-01 | 修正基准引脚坐标或显式声明该候选；对象级 expected 集合；CI 对未声明发现失败 |
| C-03 | GAP | A-AREA（域 3） | `sch_layout_check.py:2` 自述只读调用者 JSON；analyze 只读 components/texts/wires；F1 `snapshot.json` 直跑退出 2，`missing=['components','coordinate_units','texts']`；快照只有 16 part 原点/旋转/镜像、56 pin、44 wire、27 flag、16 port，无符号本体/text bbox；`AUD/schematic-layout/snapshot-check.txt` | 没有 EDA→layout 转换器；没有符号本体轮廓/字体度量/文字外框；F1 的合成适配是敏感性实验，不是真实测量 | 无 | 新增 snapshot→layout 适配器；明确矩形近似误差/置信度；无符号本体或文字 bbox 时拒绝给出通过结论 |
| C-04 | DEFECT | A-AREA（域 3 D6） | `AUD/schematic-layout/d6-probes.txt` 等：端点距异网导线 0.6（tolerance=1）不报 dangling；pin 附近 2 远的异网导线触发 pin_multiple_nets；标签附近 1.5 远的平行异网导线触发 label_net_mismatch；同网四向交叉/异网共线重叠/异网共享端点均 no_candidates | 合成探针，不是真实 F1 图；tolerance 语义未与真实编辑器端点规则对照 | C-03 | 端点连接必须是 pin/flag/port 命中，不能任意导线 tolerance 内即算连接；网名集合按实际连通分量而非附近并集；补正反例 |
| C-05 | GAP | A-AREA（域 3） | `AUD/schematic-layout/frame-wire-probe.txt`：模块框内穿线 no_candidates；B8 长 GND 穿三个模块仍 no_candidates；`sch_layout_check.py` 无 wire-frame crossing 检查 | 只验证合成 B8；真实模块框/导线坐标未测 | C-03 | 增加 wire 与 module_frame 边/内部的穿越检查；B8 作为回归 |
| C-06 | DEFECT | A-AREA（域 3） | 模块成员判定用 bbox 中心且边界包含；`AUD/schematic-layout/extras-summary.txt` B7 把 A1 同时算作 frame-rf 成员并报 frame-main 缺员；另有 3 条未声明 frame_border_crosses_object | B7 的 A1 同时真实跨界，成员误报与真实穿越并存；真实模块框未测 | C-01 | 成员判定用完整包含/面积占比并显式处理跨界；边界点不默认属于两侧 |
| C-07 | GAP | A-AREA（域 3 D4） | `AUD/schematic-layout/d4-schema-probes.txt`：`rotation`、`mirror`、`unit`、`pages`、`page_name`、`pin`、`scope`、`shape`、`expected_inventory`、`min_clearance` 均被严格字段校验拒绝 | 多页/多单元/引脚身份/旋转镜像 provenance/真实文字外框/最小间距无法表达；无真实多页工程 | C-03 | 扩展 schema；至少支持 pages/page_name/unit/pin/scope/rotation/mirror/text_bbox/min_clearance；补 schema 测试 |
| C-08 | GAP | A-AREA（域 3 D6） | `AUD/schematic-layout/d6-probes2.txt`、`d6-probes3.txt`：同网四向交叉、异网共线重叠、异网共享端点/沿元件或模块边的导线全部静默 | 合成探针；电气语义仍需 netlist 交叉验证 | C-03 | 增加共线重叠/共享端点/沿边导线的候选规则；与 `netlist_check.py` 的 pin-net 结果交叉 |
| C-09 | GAP | A-AREA（域 3） | `AUD/schematic-layout/f1-crowding-probe.txt`；F1 `snapshot.json` 无 text bbox、无脚名、无最小间距；`schematic.png` 目视 J101/J102/U101 拥挤；检查器直跑即失败 | 未在 EDA 画布中缩放/拖动复核；只有提交的 PNG 与裁图 | C-03 | 先建立真实几何输入（文字外框/脚名/间距），再把 F1 拥挤作为验收项；否则明确“当前检查器不能评价 F1 排版” |
| C-10 | NOT RUN | R2 B3 | `docs/task-ledger-round2.md:25`；仓库 `docs/evidence` 只有单页 EvidenceDemo 与单页 F1，无真实多页工程 | 无真实多页/图框尺寸切换/阅读顺序验收 | 无 | 用一个真实多页工程执行分页、图框、跨页网络与阅读顺序验收；保存截图/网表/哈希 |
| C-11 | PARTIAL | A-GATE | `python design-hardware/scripts/schematic_benchmark.py` 8/8；`python -X utf8 -m unittest tests.test_schematic_benchmarks -v` 5 tests OK；`AUD/schematic-layout/benchmark-run.json` | 仅 recall；无精度门禁；不是 8 张真机图 | C-01 | 保留可执行回归，但 README/台账表述改为“recall-only”，直到 C-01 完成 |

## 6. 工作包 D：F1 原理图证据与 C2/C4

范围：`docs/evidence/f1-2026-10-22/`、`design-hardware/references/projects/p04-usb-mcu-board.md`、F1 的网表/快照/PNG。

| ID | 状态 | 来源/复核 | 证据 | 未完成边界 | 依赖 | 解阻条件 |
|---|---|---|---|---|---|---|
| D-01 | DEFECT | A-AREA（域 4，必须修改项） | `p04-usb-mcu-board.md:26-30` C103 10µF；F1 README:78 稳定性未算；AMS1117 家族手册要求 22µF 钽，TI LM1117 §9.2.2.1.3 要求 ESR 0.3–22Ω；`AUD/f1-evidence/datasheets/ams1117_utd.txt:218,235`、`lm1117_ti.txt:718-724`；C103 为 10µF X5R 陶瓷 | 未取得永裕泰 AMS1117-3.3 精确原厂手册；未做纹波/负载瞬态/温升实测 | 无 | 改 C103 为满足 ESR/容值的 22µF 钽或加 ESR 电阻/换 LDO；在 F1 证据中附计算与实测计划；未验证前标 PARTIAL |
| D-02 | DEFECT | A-AREA（域 4，必须修改项） | `snapshot.json:533` U101 IO2 无网络；全页 `noConnected=false`、无 NC 标记；ESP8266 boot strapping 需 GPIO2 高（`AUD/f1-evidence/datasheets/esp8266ex.txt:408`） | 未做上电/下载/启动实测；ESP-01S 模块 revision 未确认 | D-06 | 给 IO2 10k 上拉或明确 NC 并记录 boot 影响；补上电与下载测试；未验证前不得称“启动边界已验证” |
| D-03 | GAP | A-AREA（域 4，C4 门禁） | `reopen-check.json` 比较 x/y/rotation 与归一化导线；纯重排必 mismatch；`compare_snapshots` 忽略 netport/pin/零长线；现有 `schematic.net` 只导出一次，无第二次导出/diff 工具；`snapshot.json:2670-2675` 自述 netlist pin-net equivalence 未检查 | 无重排前后网表 diff；无 C4 验收脚本；未重跑重排 | D-01, D-02 | 增加 `netlist diff`（pin→net 规范化）与 C4 门禁：重排前后 0 个 pin-net 变化；保留两次导出与哈希 |
| D-04 | GAP | A-AREA（域 4） | J101 壳脚 1–4 无网络、无 NC（`pins.txt`、`schematic.net:31-39`）；VBUS/CC 无 ESD/保险；J101 无 Manufacturer/Datasheet | 未做 USB-C 兼容性/ESD/浪涌测试；未核对原厂 MPN | 无 | 壳脚接地或明确 NC；加 VBUS/CC ESD 与保险候选；补 J101 原厂 MPN/数据手册；标注“候选，未实测” |
| D-05 | GAP | A-AREA（域 4） | J102 网表映射 1/2/3/4 = 3V3/TXD/RXD/GND（`schematic.net:1152,1172,1183,1188`）；3.3V UART 无电平保护；3V3 直出无保险 | 排针方向/定义未在实物上核对；未测外接负载 | 无 | 在 README/原理图标注 J102 引脚定义与方向；加串阻/保险候选；首板用万用表核对 |
| D-06 | GAP | A-AREA（域 4） | EN/RST 只有 10k 上拉，无 100nF RC（`AUD/f1-evidence/datasheets/esp8266_hw_guidelines.txt:486-487,527,545-563`）；复位使用 RST 而非 CHIP_EN | 未做复位时序/上电波形实测；模块内部是否已有 RC 未确认 | D-02 | 加 EN/RST 100nF 与复位电路复核；示波器测上电/复位；记录是否改用 CHIP_EN |
| D-07 | DEFECT | A-AREA（域 4） | `AUD/f1-evidence/geom_check.txt`：2 条悬空 CC 短线 + 10 条零长度导线；apply 验证只查计划项存在，不查多余对象（`verify_against_snapshot` 不遍历 after 中未计划对象） | 未在 EDA 中删除后重跑；未确认零长线是否编辑器自动生成 | A-02 | 删除/合并多余导线；apply 增加“未计划对象”报告；C4 diff 把多余导线计入 |
| D-08 | GAP | A-AREA（域 4） | F1 README:6 写“物理脚-网络”；`schematic.net` 是符号级网表；封装焊盘映射未验证；`snapshot.json` 无 pad 映射 | 无 PCB/封装焊盘数据；未做 footprint 与物理脚对照 | D-03 | 把“物理脚”改为“符号引脚”；建封装-焊盘映射表；PCB 导入后核对 56 焊盘 |
| D-09 | PARTIAL | A-AREA（域 4） | `AUD/f1-evidence/power_calc.txt`；F1 README:78-80 明确 LDO 热/压差/峰值电流未算未测；ESP 本地 10µF+100nF 未体现 | 只有计算，无热像/热电偶/示波器；无 ESP 峰值电流实测 | D-01 | 补 LDO 热/电流裕量计算与首板实测计划；加 ESP 本地去耦；未测前标 PARTIAL |
| D-10 | DEFECT | A-AREA（域 4） | `schematic.png` 与裁图：U102 的 5V/3V3/GND flag 间距 10 单位，U101 的 RXD/10kΩ、J102 的 GND/1kΩ 文字重叠；F1 README:74 自述拥挤；无 layout-check 证据；检查器不能喂入 snapshot（C-03） | 未在 EDA 画布中缩放/拖动复核；未做重排 | C-03 | 重排 U102/J101/U101/J102 四处；重排前后网表 diff 为 0；导出 PNG 并人工复核；在 README 保留 PARTIAL 直到通过 |
| D-11 | DONE | R2 F1 | D101-1(A)=LED_A、D101-2(K)=GND，R106-2=LED_A、R106-1=3V3；电流 0.9–1.5mA（`schematic.net:1201-1205,1149`） | LED 偏暗是设计取舍，不是缺陷；需在 README 记录 | 无 | 保留 1k 或按亮度目标调整；在 F1 证据中记录电流与可接受性 |
| D-12 | NOT RUN | R2 F1、F2–F5 | F1 README:81 与 `docs/task-ledger-round2.md:31-32`：PCB、DRC/ERC、制造、样机、固件均未做；F2–F5 未开始 | 无 PCB/DRC/ERC/制造/样机/固件证据；无其他项目样本 | E-01 | 先完成 E-01 PCB 适配器，再按 F1→F2 顺序建立真实项目证据；未执行项保持 NOT RUN |

## 7. 工作包 E：PCB 纵向闭环

范围：嘉立创EDA Pro 4.1.78 半离线 CLI + `design-hardware/scripts/eda_exec.py`。本轮在 scratch 副本上真机验证了 PCB API；未操作用户 GUI 会话。

| ID | 状态 | 来源/复核 | 证据 | 未完成边界 | 依赖 | 解阻条件 |
|---|---|---|---|---|---|---|
| E-01 | GAP | A-CONF F-01（critical；交叉复核对严重度有 critical/medium 分歧，能力事实已证实） | `eda_exec.py:1285` 唯一 PCB 字样为 `pcb_read_write=not_implemented_in_this_adapter`；全文件无 `pcb_*`/`PCB_*` 调用；SNAPSHOT/SAVE/EXPORT/reopen 全走 `sch_*`/`dmt_Schematic`；`AUD/pcb-closed-loop/probe-pcb-result.json`、`probe-pcb-write-result.json`、`probe-f1-pcb2.json` 证明客户端 PCB 读写/保存/导出可用 | E2–E10 在适配器内全部不可做；手动 CLI 已做部分；未做真实 pad-to-pad 布线 | 无 | 增加 `pcb-read`、`pcb-apply`（outline/place/route/via/pour）、`pcb-save`、`pcb-export`、`pcb-reopen-check`；用 `dmt_Pcb.getAllPcbsInfo`+`openDocument/activateDocument`+`getCurrentDocumentInfo` 选页；doctor 加 PCB 实探 |
| E-02 | PARTIAL | A-AREA（域 5） | `PCB_PrimitivePoured.create` 文档标注“不支持新建，调用无任何效果”；创建第二个 POUR 后 modify/DRC/save/reopen 仍 `pours=2, poured=1`；`AUD/pcb-closed-loop/methods/PCB_PrimitivePoured.create2.json`、`probe-outline-pour.json`、`probe-reopen-counts.json` | headless 半离线不生成填充；GUI/全在线是否自动重算未验证；无重算 API | 无 | 找到 GUI/在线重算入口或明确“仅边框”；PCB 验收必须同时报告 pours 与 poured；不要声称铺铜完成 |
| E-03 | DEFECT | A-AREA（域 5） | `DMT_Pcb.createPcb` 对不存在的板名静默返回 undefined；F1 建 PCB 必须先 `createBoard(schematicUuid)` 再 `createPcb(boardName)`；`AUD/pcb-closed-loop/probe-project-tree.json`、`probe-f1-pcb.json` | 其他板名/重名/多板行为未测 | 无 | 适配器封装两步创建；createPcb 返回 undefined 时报错；补重名/不存在板名测试 |
| E-04 | PARTIAL | A-AREA（域 5） | `importChanges(F1 uuid,true)` 返回 true，得到 16 components/56 pads/11 nets/0 lines；不建板框、不布线；DRC 仍报 Netlist Error；`AUD/pcb-closed-loop/probe-f1-pcb.json` | 只验证 F1 单页导入；未验证多页/多板/封装缺失；未做真实连通性 | E-01 | 导入后强制报告 outline/routing/DRC 缺口；加板框与布线步骤；建立 clean DRC baseline |
| E-05 | DEFECT | A-AREA（域 5） | `PCB_PrimitiveComponent.create` 拒绝 `getState_Component()`/`getState_Footprint()`（Error: [object Object]）；扁平 `{libraryUuid, uuid:string}` 成功并自动分配 DC2；`lib_Device.search` 也成功；`AUD/pcb-closed-loop/probe-pcb-component.json` | 只验证 DC005/DC2/DC3；未验证所有库器件/多封装/极性 | E-01 | 适配器统一用扁平引用；创建后回读 designator/footprint/position；补失败路径 |
| E-06 | PARTIAL | A-AREA（域 5） | 板框无专用 API；`pcb_PrimitivePolyline.create('',11,poly,10,false)` 在 layer 11 建闭合折线成功，delete true；importChanges 不自动建框；`AUD/pcb-closed-loop/probe-outline-pour.json` | 未验证复杂板框/圆弧/槽/拼板；未与板厂规则核对 | E-01 | 封装 board-outline 命令；校验闭合/层/线宽；导出 Gerber 后独立查看板框 |
| E-07 | GAP | A-AREA（域 5） | 飞线几何无 API；只能通过 DRC Connection Error、`getNetLength`、焊盘坐标间接验收；`AUD/pcb-closed-loop/doc-api-classes.json` | 未验证 DRC 错误与未布网络的映射；未做全网络连通性 | E-01 | 用 DRC+net length+pad 坐标建“未布网络”报告；不要声称能读飞线 |
| E-08 | GAP | A-AREA（域 5） | `getGerberFile('audit-probe')` 返回 1,292,201 B；`getPickAndPlaceFile('audit-probe','csv','mm')` 返回 16,610 B；适配器 `export` 只有 png/netlist/svg（`eda_exec.py:1580`） | Gerber 未用独立查看器逐层核对；BOM/DFM/下单未测 | E-01 | 增加 `pcb-export`（Gerber/CPL/BOM）；记录层列表/单位/原点/钻孔；独立查看器复核 |
| E-09 | PARTIAL | A-AREA（域 5） | `pcb_Document.save()` 返回 true；关闭重开后 line/via/pour 与 F1 PCB 的 16 器件/56 焊盘/11 网络保持；`AUD/pcb-closed-loop/probe-pcb-write-result.json`、`probe-f1-reopen.json` | 适配器 `save`/`reopen-check` 是原理图专用；PCB 重开未接入 | E-01 | Pcb save/reopen-check 复用同一事务与身份校验；比较 components/pads/nets/outline |
| E-10 | BLOCKED | A-AREA（域 5） | `probe-pcb-result.json` env `online:false, half_offline:true, version:4.1.78`；两个 alive 会话都是 `origin=user` 的 GUI；本轮未操作 | 全在线库/库存/价格、在线 DFM、GUI 铺铜重算均未验证 | 用户 GUI 会话授权 | 由用户在 GUI 全在线会话执行同一 PCB 探针；记录 sessionId/build/online 与截图；不得用半离线替代 |
| E-11 | GAP | A-AREA（域 5） | `base-copy.eprj2` 是 SQLite 3 单文件，表计数 boards=0/documents=2/schematics=1；运行时工程树 1 board+1 PCB+10 schematics；`AUD/pcb-closed-loop/eprj2-schema.txt`、`probe-project-tree.json` | SQLite 表不能作为文档清单真源；未验证其他 .eprj2 结构 | 无 | 用运行时 API 枚举工程树；SQLite 只做辅助；文档/脚本不要按表计数判断板/页 |
| E-12 | NOT RUN | R2 C1–C5、A-AREA | 未做真实 pad-to-pad 布线、全网络连通性、自动布线/布局、BOM/DFM/下单、多层/盲埋孔/阻抗/板厂规则、独立 Gerber 查看、clean DRC baseline | 全部未执行；只有原语级探针 | E-01 至 E-09 | 按 F1 网络逐网布线并核对每个焊盘；建立 DRC 基线；用独立工具看 Gerber；再谈 PCB DONE |
| E-13 | PARTIAL | A-GATE | 手工 CLI 已读 33 components/83 pads/17 nets；创建 line/via/pour、save/reopen、Gerber 1,292,201 B、CPL 16,610 B；`AUD/pcb-closed-loop/probe-pcb-result.json`、`probe-pcb-write-result.json`、`probe-reopen-counts.json` | 不在适配器内；未做真实布线；未验证 DRC 归零 | E-01 | 把这些探针固化为适配器回归；同一命令在 F1 PCB 上重跑；保留原始 JSON |
| E-14 | GAP | A-AREA（域 5） | `pcb_Drc.check(false,false,false)` 返回 false；verbose 数组报 Netlist Error；样例 PCB 基线已有错误；`AUD/pcb-closed-loop/probe-pcb-result.json` | 没有 clean baseline；未比较错误增量；未做 DRC 规则配置 | E-04 | 先建立“导入前/导入后/布线后”错误集合；每轮报告新增/消失错误；不得只报 bool |
| E-15 | PARTIAL | A-AREA（域 5） | `createBoard(F1 uuid)`→`createPcb('F1-USB-MCU-C')`→`importChanges`→16 components/56 pads/11 nets→save→reopen 仍 16/56/11；`AUD/pcb-closed-loop/probe-f1-pcb.json`、`probe-f1-pcb2.json`、`probe-f1-reopen.json` | 只有器件/网络搬运；无板框、布局、布线、铺铜、DRC 归零 | E-03, E-04 | 继续完成板框/布局/布线/铺铜/DRC；每步保存并重开；最终以 F1 PCB 证据单独报告 |

## 8. 工作包 F：制造与供应链

范围：`design-hardware/references/jlc-handoff.md`、`lcsc-sourcing.md`、`jlc-smt-rules.md`、`jlc-pcb-rules.md`、`manufacturing-routes.md`、`selection/lcsc-verification.md`、`docs/evidence/f1-2026-10-22/`、BOM 草稿。

| ID | 状态 | 来源/复核 | 证据 | 未完成边界 | 依赖 | 解阻条件 |
|---|---|---|---|---|---|---|
| F-01 | GAP | A-AREA（域 6） | `eda_exec.py:1283-1285` `sch_export_bom`/`sch_drc`/`pcb_read_write=not_implemented`；`export` choices 只有 png/netlist/svg（`:1580`）；仓库 `git ls-files` 无 CSV/XLSX/GBR/DRL/ZIP；无 manifest | 无 BOM/CPL/Gerber/钻孔/装配图/钢网/DFM 生成能力；无下单/上传 | E-01 | 实现或封装 BOM/CPL/Gerber 导出；`scripts/bom_check.py` 输出草稿并显式标“待查”；在 `eda-execution.md` 写明未实现 |
| F-02 | PARTIAL | A-AREA（域 6） | `AUD/f3-bom/f1-bom-draft.csv` 11 行/16 位号；J101/C101/C103 无 manufacturer；J101/C101/C103/J102 是通用库名非可订购 MPN；8/16 无结构化 Value；快照无 DNP/变体/替代/自备料字段；`AUD/f3-bom/f1-bom-coverage.json` | 草稿不是完整 BOM；P04:136 口头“无 DNP”但无机器可读 `dnp:[]`；未查商城 MPN/库存 | F-01, F-10 | 补 manufacturer/MPN/Value/DNP/变体/替代/自备料字段；从 EDA 库映射可订购料；BOM 输出标“草稿/待核” |
| F-03 | DEFECT | A-AREA（域 6） | `apply-result.json:3`、`reopen-check.json:3-4` 引用 `<scratch>` 路径；README:87-88 只有 PNG/NET 两个 SHA256；无 manifest/生成时间/客户端 build/工程 UUID/plan hash；`reopen-check.json:5` `closed_session=null` | 仓库内 plan/snapshot 不能证明就是执行/比较的那份；`base-copy.eprj2` 不在仓库 | F-01 | 增加 `docs/evidence/f1-2026-10-22/manifest.json`：所有文件 SHA256/大小/生成时间/客户端 build/工程 UUID/plan/snapshot hash；apply/reopen 写仓库路径或哈希 |
| F-04 | GAP | A-AREA（域 6） | 无 PCB/CPL 数据；`snapshot.json` 的 x/y/rotation/mirror 是原理图画布坐标与符号变换；16 个 `other_property.PCB Layer` 全 `Default`；`eda_exec.py:1283-1285` 声明 PCB 未实现 | 无 CPL/原点/面别/极性/封装中心；不能把 snapshot 当 CPL | E-01 | PCB 完成后再生成 CPL；明确 Top/Bottom、原点、旋转、极性；用首板核对 |
| F-05 | DEFECT | A-AREA（域 6） | `SNAPSHOT_JS:507-510` `attributesComplete` 初始 true，只有 `include_attributes` 时才更新；`read_snapshot:1218` 默认 False；`snapshot.json:2668-2669` `attributes_included=false` 仍 `attributes_complete=true`；CLI 无 attributes 入口 | 属性截断 500；未验证真实属性数量 | A-09 | 修正语义：未请求属性时写 `attributes_included=false, attributes_complete=null`；增加 CLI 入口；重生成 F1 snapshot |
| F-06 | DEFECT | A-AREA（域 6） | `verify_against_snapshot:1116-1133` 不验证 footprint/manufacturer/netports/mirror/add_into_bom；`compare_snapshots:1163-1211` 不比较这些；`apply-result.json` observed 无 footprint | 与 A-02/A-04/A-05/B-09 重叠；真机字段接受度未验证 | A-02 | 统一验证域清单；F1 重新 apply/reopen 并记录新字段；旧证据标“范围窄” |
| F-07 | GAP | A-AREA（域 6） | `reopen-check.json:5` `closed_session=null`；README:5/68 与 P04:164 写“关闭后重开”；代码只在传 `--session` 时 close；apply 自有会话隐式关闭但未记录 | 无法证明是同一工程副本的关闭后重开；无 sessionId/关闭时间 | B-05 | reopen-check 记录 sessionId、project UUID、关闭前后时间；F1 重跑并更新证据 |
| F-08 | DEFECT | A-AREA（域 6） | `manufacturing-routes.md:7` 仍写“本环境没有 EDA 工具，也未制造、未打样、未做功能实测”；与 `README:85`、`docs/evidence/f1-2026-10-22/` 的真实 EDA 证据矛盾 | 该句所在章节是离线规划样本，但表述未限定 | 无 | 改为“F1/EvidenceDemo 已在 4.1.78 半离线会话完成原理图读写；本文第 9 节样本仍是离线规划”；不要删除真实证据边界 |
| F-09 | GAP | A-AREA（域 6） | F2 文档已区分商城购料/SMT 可贴/寄料/已下单（`jlc-handoff.md:15/18`、`lcsc-sourcing.md:19`、`jlc-smt-rules.md:3`、`manufacturing-routes.md:45/167/524`）；但数据层无渠道字段；snapshot 只有 `supplier=LCSC` 与 `JLCPCB Part Class` 库标签；`supplier=LCSC` 易被当成当前可贴 | 无实时渠道数据；无 SMT 可贴/库存/价格字段 | F-10 | 在 BOM/采购卡增加 `channel`（mall/SMT/self）、`verified_at`、`stock`、`price`、`MOQ`；未查写“待查” |
| F-10 | GAP | A-AREA（域 6） | `manufacturing-routes.md:5/614` 全部写“待查”；`:609-612` 记录 2026-10-20 LCSC 搜索 code:500/系统异常；`selection/lcsc-verification.md:83-93` 同；F1 README:28-42 只写“真实库回读”，未给商城核实日期/库存；C9900216560、C9900012828 为 10 位数字需真实渠道确认 | 未访问 LCSC/JLC 实时页面；无账号/下单授权 | F-09 | 有授权时按 `lcsc-verification.md` 逐项核对至少 10 个关键料；记录 URL/时间/库存/价格/MOQ/包装/交期/SMT；无授权则保持 BLOCKED |
| F-11 | DEFECT | A-AREA（域 6） | `jlc-smt-rules.md` 写 Mark 开窗 2mm；`manufacturing-routes.md` 写“不写固定值/3mm vs 2mm”；两处口径不一致 | 未核对当前官方页面；不同服务/拼板条件未分列 | 无 | 以当前官方 SMT 规则为准统一；分服务/拼板条件列值；加来源/日期 |
| F-12 | GAP | A-AREA（域 6） | `jlc-pcb-rules.md:3`、`jlc-smt-rules.md:3` 为 2026-10-20 来源快照；`source-register.md:3/48-64` 有 URL/页面日期/查阅范围；无原始页面存档 | 页面变化后无法复核；无截图/PDF 存档 | 无 | 保存官方页面截图/PDF 或哈希；登记查阅范围；定期重查 |
| F-13 | DONE | A-AREA（域 6） | 文档层已区分商城购料、SMT 可贴、寄料、已下单；failure f20 专门描述“商城有货但 SMT 不可贴” | 仅文档层；不代表任何 C 号当前可贴 | 无 | 保留文档；在 BOM/采购卡中落实 F-09 字段后才可谈执行 |
| F-14 | BLOCKED | A-AREA（域 6） | 未查询 LCSC/JLC 实时页面；无账号库存/价格/MOQ/SMT 可贴；无下单授权；`manufacturing-routes.md:5/614`、`lcsc-verification.md:83-93` 明确待查 | 实时数据全缺；DFM/厂方审核/打样/SMT/下单未做 | 用户账号与授权 | 用户提供可登录环境与最小授权；只查不买；记录 URL/时间/字段；不得下单/支付/上传工程 |
| F-15 | NOT RUN | A-AREA（域 6） | 仓库无 BOM/CPL/Gerber/manifest 数据文件；无打样/SMT/装配/首板测试 | 无制造实物证据 | E-01, F-01 | 先完成 PCB 与制造资料，再打样；首板按 P04 §9 测试计划执行并记录 |

## 9. 工作包 G：电源与热计算

范围：`references/calculations/power-thermal.md`、`design-cards/power/p01-ldo.md`、`p02-buck.md`、`p03-boost.md`、`examples/x01-buck-loop.md`、`x02-ldo-thermal.md`、`scripts/calculate.py`、`scripts/thermal_calc.py`。本轮用独立 Python 复算 12 组算例，并核对 TI/Vishay 原文。

| ID | 状态 | 来源/复核 | 证据 | 未完成边界 | 依赖 | 解阻条件 |
|---|---|---|---|---|---|---|
| G-01 | DEFECT | A-CONF PT-01（high） | `power-thermal.md:97`、`p03-boost.md:40/125/184/216` 写 `IMAXOUT=ILIM(min)·(1−D)−ΔIL/2`；SLVA372D §8 Eq.16 为 `(ILIM(min)−ΔIL/2)·(1−D)`；`AUD/power-thermal/slva372.txt:106-108,316-319`；`AUD/power-thermal/corrections.out` | 未做台架验证；只影响文档/选型，不是 EDA 执行 | 无 | 两处公式改写；p03 用 3.0A/2.5A 重跑；§4.3 判据拆 Buck/Boost；加 Eq.16 回归或 `ilim_min_A` 字段 |
| G-02 | DEFECT | A-CONF PT-02（high） | `power-thermal.md:129,250,257-259` 与 `selection/power-ics.md:68,294` 把 SLVA118A Figure 5 的 YEA/YZA 154–330 当作 SOT-23 DBV、把 PowerPAD DGK 58–83 当作 SOIC D；`AUD/power-thermal/slva118_fig5_crop.png`、`slva118_raw.txt:284-286`；普通 SOIC-8 按 97–178 复算 TJ=116–172°C 而非 90–107°C | 未逐页复核 SLVA118A 全部表；TPS7A02 DBV 实际 181.9°C/W（原审计称空行被推翻）；未做热实测 | 无 | 按原表 14 列重新对齐；删除“DBV 154–330”；SOIC D 用 97–178/55 两列重算；同步 power-ics.md；加源表核对记录 |
| G-03 | DEFECT | A-AREA（域 7） | TPS7A02 手册 §6.3 明写 TJ(max)=125°C（`AUD/power-thermal/tps7a02.txt`），p01 却记为“未读到”；热判定未对真实上限 | 未做热实测；只影响 p01 结论 | 无 | 改 p01 并按 125°C 重算；把 TJ(max) 来源页码写进卡片 |
| G-04 | DEFECT | A-AREA（域 7） | p02 负载阶跃写“1 A（10–90%）”，但 2 A 负载的 10–90% 是 1.6 A；输出电容按 1 A 选导致瞬态目标不成立 | 未做负载瞬态实测/仿真 | 无 | 改 1.6 A 重算 Cout/过冲；补负载阶跃条件表 |
| G-05 | DEFECT | A-AREA（域 7） | p02 把 SLVA477C Eq.8 误记为 `PD=IF·VF·D`；原文 `PD=IF·VF` | 未复核所有二极管损耗算例 | 无 | 改公式并重算；加原文页码 |
| G-06 | DEFECT | A-AREA（域 7） | p02 输入电容 RMS 只按 VIN(max) 的 D 计算，漏掉 D=0.5 的最坏点（1.0 A vs 0.978 A） | 未做全输入区间扫描 | 无 | 按 D=0.5 与端点同时取最大；补区间极值检查 |
| G-07 | DEFECT | A-AREA（域 7） | `power-thermal.md` 5.3 频率表把栅极损耗固定为 20 kHz 的 4 mW，未随 fS 缩放 | 只影响该表；未做 MOSFET 实测 | 无 | 用 `Qg·Vgs·fS` 逐频重算；表内写公式与条件 |
| G-08 | DEFECT | A-AREA（域 7） | `ripple_ratio` 在 Buck/Boost/脚本中定义不一致（ΔIL/IOUT vs ΔIL/IIN） | 未统一所有卡片/范例 | 无 | 统一为 ΔIL/IOUT 或分拓扑明确定义；脚本输出字段名区分 |
| G-09 | GAP | A-AREA（域 7） | `calculate.py` buck/boost 缺 ILIM(min)/VFB/IFB 输入，无法执行限流/分压判据；L 公式多乘 η | 未独立复算所有脚本模式；未做 CLI 边界测试 | 无 | 增加 `ilim_min_A`/`vfb_V`/`ifb_A`；修正 L 公式；补正常/边界/无效输入测试 |
| G-10 | GAP | A-AREA（域 7） | `power-thermal.md` 未引用 `thermal_calc.py`，且仍称“MOSFET 开关/SOA 没有封装脚本” | 未审计 thermal_calc.py 全部模式 | 无 | 加脚本入口与命令示例；删除过期声明；把 29 项回归纳入文档 |
| G-11 | GAP | A-AREA（域 7） | 热建议“足够铜面积/过孔”无数值目标或验收标准 | 未做热仿真/实测 | 无 | 给铜面积/过孔数/热阻目标与验收方法；按封装/功耗给表 |
| G-12 | DEFECT | A-AREA（域 7，low） | x01 用理想 D 回算 ΔIL；5.1 的 10µH 淘汰数字按 9µH 算出 | 只影响示例 | 无 | 用实际 D 重算；修正淘汰数字或标明按 9µH |
| G-13 | NOT RUN | A-AREA（域 7） | p04–p14 电源卡未逐卡审计；power.md/selection 只抽查 θJA 传播；未做 SPICE/热仿真/实测 | 审计范围限制；不是缺陷 | 无 | 下一轮按高风险卡（市电/隔离、热插拔、MOS SOA、电池保护）逐卡复算 |
| G-14 | DONE | A-GATE | 12 组独立复算与文档一致（Buck 5.1、LDO 5.2、Boost 5.7、p01–p03、x02、MOSFET 5.3/5.6、thermal_calc ldo/mosfet/heatsink/via/enclosure）；`AUD/power-thermal/verify_power.out` | 只覆盖抽样算例；不代表全部电源内容 | 无 | 保留复算脚本与输出；作为后续修改的回归基线 |

## 10. 工作包 H：电源与电池

范围：`references/calculations/energy-battery.md`、`design-cards/power/p05`、`p06`、`p07`、`p08`、`p12`、`failures/f02`、`f09`、`f13`、`f14`。

| ID | 状态 | 来源/复核 | 证据 | 未完成边界 | 依赖 | 解阻条件 |
|---|---|---|---|---|---|---|
| H-01 | DEFECT | A-CONF PWR-R3-01（high 下调 medium） | `p08-battery-protection.md:135` 以 UVP 标称 2.800V 与电芯最小 2.75V 得“50mV 余量”；`:98-99` 判据未取 min；BQ29700 UVP 精度 ±50mV（`AUD/power-battery/p6_words.txt`、SLUSBU9I §6.6），min=2.750V，最坏余量 0mV；:167“OVP 最紧”被 25mV OVP 余量推翻 | 电芯限值是假设；未做 UVP 点实测；**不要**按原建议改用 BQ29703 2.3V（会过放） | 无 | 用 `V_UVP(min)=2.750V` 重写判据并标 0mV；换更高 UVP/更高精度保护 IC 或改电芯下限；补 UVP 迟滞/延时/IR 跌落角落表；台架扫 UVP |
| H-02 | DEFECT | A-CONF PWR-R3-02（high 下调 low） | `p08:143-145` 用 ±5mV（典型）得 3.57A/19% 余量；SLUSBU9I §6.6 保证值 ±10mV（25°C）/±15mV（−40–85°C）；5mV 是 90–200mV/5mV 步进，但 Features 也标 ±5mV typical；按 85mV/28mΩ=3.036A，余量约 1.2%；30mΩ 时 2.83A 会误跳 | 卡片已标“典型”；FET 值为演示假设；未做热态脉冲实测 | H-01 | 把 19% 标为典型；用 ±10/±15mV 与最高 Tj/最低 Vgs 的 Rds(on) max 重算保证带；给误跳条件；补热/冷脉冲实测 |
| H-03 | DEFECT | A-CONF PWR-R3-03（high 下调 medium） | `p12-usbc-sink.md:100/114` 假设 5V±5%、Rp±5%；:120 对 default 用 56k±5%；:145/152 称 1.5A 下端 41mV 最紧；USB-C R2.4 Table 4-27 为 56k±20%（±5% 仅 A-to-C），Rp 上拉 4.75–5.5V；5.5V/Rd 5.61k 复算 default 0.61208V、1.5A 1.16390V、3A 2.04203V；电流源模型 1.5A 下端约 14.1mV | 核心推荐 5.1k±10%/1.5A 仍满足规范窗口；真正风险是控制器保证门限（如 TUSB320 1.16V）；未做真实 source/线缆测试 | 无 | 用 5.5V、56k±20%、电阻+电流源双模型重算；选有保证门限/迟滞的 CC 控制器；实测 5.5V 条件 |
| H-04 | DEFECT | A-CONF PWR-R3-04（high） | `f14-relay-flyback.md:45` 只按 VF 或 VZ+VF 估算线圈电压并与驱动管额定比较；:61 规则“稳压值必须低于 VDS 额定”；SLVAE59A §3.2.2 给出低边开关节点为 VDD+VZ+VF；24V+40V+0.7V=64.7V>60V，而 40<60 会放行 | 未做继电器关断实测；其他卡（d03/d01/e1）有正确公式但 F14 是独立入口 | 无 | 改规则为 `VDD(max)+VZ(max)+VF(max) ≤ VDS(max)` 并留裕量；补 24V/40V 算例；差分/隔离探头测 VDS |
| H-05 | DEFECT | A-CONF PWR-R3-05（high） | `energy-battery.md:259` 把总日耗 28.288mAh/天按 40/288 等比缩放为 3.93mAh/天，得 89 天；但睡眠 100µA 固定 2.368mAh/天；`AUD/power/budget_52_40.json` 重跑 5.996mAh/天→58.38 天；仅 radio 40 次/天→45.84 天；90 天需约 16.6 次/天 | 未做实测续航；电芯/温度/自放电未建模 | 无 | 用状态表重跑替换等比缩放；报告 40→58.4 天、39→59.3 天、90 天需 16–17 次/天；把 JSON 加入证据 |
| H-06 | DEFECT | A-AREA（域 8） | PWR-05 把无迟滞阈值当下降门限；实际 4.35/4.58V 而非 4.49/4.72V | 未做比较器实测 | 无 | 按迟滞上下限重算；给门限窗口与容差 |
| H-07 | DEFECT | A-AREA（域 8） | `energy-battery.md` §5.3 线性充电热表漏掉 300mA 系统电流，TJ 低估约 20°C | 未做热实测 | 无 | 把系统电流并入功耗；重算 TJ/降额；标计算边界 |
| H-08 | DEFECT | A-AREA（域 8） | PWR-06 称 θJA/KITERM/RISET“未读”，实际在 SLUS810N p.11/p.13（自称已读的 1–31 页内） | 未逐页复核其他常数 | 无 | 改“已读”并补页码；核对 KITERM/RISET 算例 |
| H-09 | GAP | A-AREA（域 8） | PWR-07 断言来源没有电感公式，实际 BQ25619 §8.2.2.1（p.48）给出 ISAT/IRIPPLE 公式 | 未实际计算 ΔIL/ISAT 数值 | 无 | 补公式与算例；按 1.0µH/2.2µH 算 ISAT/IRIPPLE |
| H-10 | GAP | A-AREA（域 8，low） | PWR-12 把 Type-C Table 4-2 的 source 未供电电容上限当成 sink 输入电容限制 | 规范版本差异未核 | 无 | 改引 sink 输入电容条款；标页码/版本 |
| H-11 | NOT RUN | A-AREA（域 8） | 所有抽样设计仍为离线规划；无 EDA/PCB/热/EMC/安规/样机/台架实测 | 未执行；不是缺陷 | 无 | 选 1–2 个高风险设计（PWR-08 保护、F14 继电器）做台架实测；记录仪器/条件/波形 |
| H-12 | DONE | A-GATE | 15+ 个结论独立复算一致（p06 PD/θJA、p07 IIN/TJ、p08 FET/短路、p05 holdup、p12 CC、energy-battery 5.1/5.2/5.5/5.6、f13 TSTART）；原厂值已核对（SLUS810N/SLUSDF8F/SLUSBU9I/SLVA673A/SLVAE59A/SLVAEI4A/TPS7A02/TUSB320/ST AN5225/USB-C R2.4） | 只覆盖抽样结论；R2.5 正文未取得 | 无 | 保留复算输出作为回归；补 R2.5/其他变体后再扩展 |
| H-13 | PARTIAL | A-AREA（域 8） | f09-usbc-cc 的 CC 表与 p12 同源；f13 的 TSTART 公式与数值积分一致（`AUD/power/recompute-output.json`）；f02 只做交叉抽查；三者均未逐页核对原厂/实测 | f02/f09/f13 未逐页审计；f09 的 CC 窗口只与 p12 交叉，不替代 Type-C 合规测试；f13 的热插拔 SOA 未实测 | 无 | 把 f09/f13 的公式/页码补进 H-03/H-04 的交叉引用；f02 补审；高风险项做台架波形/热测试 |

## 11. 工作包 I：模拟采集与接口

范围：`references/calculations/analog-adc.md`、`interconnect.md`、`design-cards/analog/a01–a10`、`interfaces/i01–i12`、`examples/x03–x10`。本轮抽样并独立复算。

| ID | 状态 | 来源/复核 | 证据 | 未完成边界 | 依赖 | 解阻条件 |
|---|---|---|---|---|---|---|
| I-01 | DEFECT | A-CONF R3-ANA07-01（high） | `a07-high-side-sense.md:144` 100µV RTI 记为 10mA/0.10%；R_SH=1mΩ，应为 100mA/1.00%；复算 RSS 158.46mA/1.585%、worst 315.5mA/3.155%；0.5A 处 RSS 111.07mA/22.21%；`AUD/analog-interfaces/recompute.log` | 卡片低端工况是 0.5A，不是 0.1A；未做实测 | 无 | 改 :144 为 100.0mA/1.00%；重算 :146-147 与 :149；明确 V_os 主导；同步 :164-166 结论 |
| I-02 | DEFECT | A-CONF R3-IF12-01（high） | `i12-level-shift.md:167/188-189` 已写 5V/1.7k+3.3V/1.5k 合计 4.64mA>3mA 不满足；:210 结论仍写“1.7k/1.5k 满足”；复算 2.706+1.933=4.639mA | 未做 I²C 波形/灌电流实测；结论节是读者摘要入口 | 无 | 改 :210 为“单侧边沿候选成立，联合灌电流失败”；保留 :167/188-189；明确未选定最终上拉 |
| I-03 | DEFECT | A-CONF R3-ANA03-01（high 下调 medium） | `a03-diff-amp.md:74-87` ASCII 图 R2 从 R1 节点接 V_out、R4 从 R3 节点接 V_REF，运放上端标“−”、下端标“+”；:91-100 方程要求 R2 同相端接 V_REF、R4 反相端接输出；:286/288 逐脚表同样错位；`AUD/analog/a03-circuit-check.txt` 按图得 `Vout=Vref−G(Vin+−Vin−)` | 图标注“分析草图，非 EDA 产物”；不是所有读法都无负反馈；实际影响是反相/返工 | 无 | 重画 74-87（R1→+IN，R2→V_REF，R3→−IN，R4→V_out）；改 286/288；用 EDA 网表/直流扫描验证 |
| I-04 | DEFECT | A-AREA（域 9，medium） | 基准卡把温漂跨度写成 40…125°C（85°C），与 990ppm/6ppm/°C 不自洽 | 未逐页核对基准手册 | 无 | 改温区；按 6ppm/°C 重算 990ppm；标来源页码 |
| I-05 | GAP | A-AREA（域 9，medium） | 基准算例 0.0202% 行缺 198ppm 温漂残差说明；表内四项无法复现 | 只影响该表 | 无 | 加 198ppm 残差行/脚注；把四项与总误差对齐 |
| I-06 | DEFECT | A-AREA（域 9，medium） | 运放噪声 66µV 被写成 3.5 LSB；实际是 3.5 个半 LSB（1.75 个 16 位 LSB） | 未做噪声实测 | 无 | 改单位/换算；明确 12/16 位 LSB 口径 |
| I-07 | GAP | A-AREA（域 9，medium） | SPI 串阻上限只写“上限公式”却缺公式，且插入句打断列表 | 未核对原厂 IBIS/驱动能力 | 无 | 补公式与假设；恢复列表结构 |
| I-08 | DEFECT | A-AREA（域 9，low） | 重复补丁造成 CAN 表断裂、x03 表重复 3 次、a10 编号跳号 | 只影响可读性/引用 | 无 | 去重并修编号；加链接/结构测试 |
| I-09 | DEFECT | A-AREA（域 9，low） | 桥式前端最坏情况相加 2.93% 与表内六项之和 3.022% 不一致 | 只影响该算例 | 无 | 统一按 RSS/最坏相加重算；标明方法 |
| I-10 | NOT RUN | A-AREA（域 9） | 未直接打开原厂 PDF/标准正文逐页核对；未做 EDA/PCB/SPICE/TDR/VNA/眼图/温升/噪声/校准/EMC/ESD/浪涌实测 | 审计范围限制；不是缺陷 | 无 | 对高风险接口（USB-C、RS-485、CAN、以太网）逐页核对原厂/标准；做 SI/EMC 实测计划 |
| I-11 | DONE | A-GATE | 15 条抽样算例与文档一致（分压、ADC 建立、运放噪声、电流采样、基准四项、I²C、RS-485、CAN、USB device、USB-C data、以太网、SPI、RTD、interconnect、低侧采样）；`AUD/analog-interfaces/recompute.log` | 只覆盖抽样；不代表全部卡片 | 无 | 保留复算日志；下一轮扩大抽样 |
| I-12 | GAP | A-AREA（域 9） | i04/i05 只读到前 180 行；x11/x12、a02/a08 供应链/选型段未逐条核对；未审计 power/thermal/digital/mcu/wireless 卡与大部分 failures | 审计范围限制 | 无 | 下一轮按风险补审；不要用本轮“多数一致”宣称全库正确 |

## 12. 工作包 J：Skill L1/L2/L5 与结构

范围：`design-hardware/SKILL.md`、`design-hardware/references/` 引用关系、`design-hardware/assets/scenarios.json`、`tests/test_scenarios.py`、`tests/test_skill.py`、`references/beginner-journey.md`、`agent-collaboration.md`、`task-scenarios.md`、`README.md`。

| ID | 状态 | 来源/复核 | 证据 | 未完成边界 | 依赖 | 解阻条件 |
|---|---|---|---|---|---|---|
| J-01 | DEFECT | A-AREA（域 10，high） | `README.md:363` 写“已进行缺少工程/连接、未知参数、新手首次使用、工程师改板、采购数量/阶梯价、商城与SMT分流、缺货替代、完整产品目标及功能验收等场景试跑”；仓库无试跑输入/输出/评分证据；`docs/task-ledger-round2.md:30` 明确 E1–E5 NOT RUN；README:364 自相矛盾地承认“场景试跑不等于真实EDA或首板验收” | 没有原始对话记录、模型版本、判据、结果；可能只是作者口头试跑 | 无 | 删除“已进行场景试跑”或改为“未执行”；若保留，附输入/输出/评分/模型版本/日期；与 round2 E1–E5 状态一致 |
| J-02 | GAP | A-AREA（域 10，high） | `scenarios.json` 35 个场景、12 个 required_negative_cases、仅 5 个 `check`（S06/S13/S14/S29/S34）；`tests/test_scenarios.py` 只验证字段/路由/文件存在；审计称 7/12 必测反例只有标签；本轮 `python -I` 确认 `check` 非空仅 5 个 | 没有真实 Agent 行为断言；没有风险权重/通过阈值 | J-01 | 12 个必测反例至少各有可执行检查或明确“未自动化”；增加 must_do/must_not_claim 的行为断言；用真实对话记录验收 |
| J-03 | GAP | A-AREA（域 10，high） | `docs/evidence/deepdives-2026-10-22/README.md` 与 `docs/pr3-integration-review.md:23-28`：唯一 Agent 试答非盲、无原始过程记录、无对照组；新盲测输入存在但未运行；答案随 Skill 分发 | 无盲测、无基线对照、无固定模型/版本；旧评分不能证明 Skill 增益 | J-01 | 先运行新盲测输入；固定模型/版本；保留原始输出；加无 Skill 基线对照；答案不随测试包分发 |
| J-04 | PARTIAL | A-AREA（域 10，high） | 安装包 `design-hardware/` 约 5.6MB、240 个文件（本轮 `du/find` 实测；审计记录 5.1MB/235，差异来自计量口径）；31 个参考 >40KB；单条热设计路由一次可加载 121KB | 安装包未分层；测试/证据/历史文档未与运行包分离；大文件按需加载未强制 | 无 | 拆 `references/core` 与 `references/deep`；SKILL 路由只加载必要文件；安装包排除 tests/docs/evidence；给出包大小预算 |
| J-05 | GAP | A-AREA（域 10，medium） | `SKILL.md` §3 是 49 行平表；24 条 action-map 触发式条目无任何 markdown 链接可达（孤儿 `engineering-deepdives/action-map.md`、`casebook/index.md`） | 检索靠扫表；action-map 不在主路径 | 无 | 把 action-map 接入 SKILL 的按需路由；主索引按任务/阶段分组；加链接检查 |
| J-06 | DEFECT | A-AREA（域 10，medium） | `README.md:71/309` 故障 22 个 vs 实际 33 个（`failures/README.md` F01–F33）；`README.md:366` 138 tests vs 实际 141；README 称“有证据”但 F23–F33 是 11 个构造案例（`failures/README.md:59`） | 数字漂移；构造案例被计入“有证据” | 无 | 改 22→33、138→141；把“有证据”拆成“作者记录/原厂来源/构造案例/未证实”；加测试核对数字 |
| J-07 | GAP | A-AREA（域 10，medium） | 35 个场景验收标准一律 4 条 must_do / 3 条 must_not_claim / 3 条 evidence；无风险权重与通过阈值 | 无法区分关键场景与普通场景 | J-02 | 增加 risk_level/weight/pass_threshold；高风险场景要求更强证据 |
| J-08 | GAP | A-AREA（域 10，medium） | 预算限制、长任务接续、新手真实路径只有文档；35 个场景 0 个覆盖预算或中断接续 | 无对应行为试验 | J-02 | 增加预算/中断/接续场景与检查；用真实长任务记录验收 |
| J-09 | PARTIAL | A-AREA（域 10，low） | `SKILL.md` 30,538 B/237 行；§0 仍是发布说明口吻；49 行索引偏重 | 入口可用但偏长；不是错误 | 无 | 压缩 §0；把发布说明移出 SKILL；主索引分层 |
| J-10 | DONE | A-GATE | 全部 markdown 相对链接通过 `tests/test_skill.py`；从 SKILL.md 出发 213 个 .md 中 211 个可达，孤儿仅 `engineering-deepdives/action-map.md`、`casebook/index.md` | 可达性不等于内容正确；两个孤儿需 J-05 处理 | 无 | 保留链接检查；把孤儿接入或删除 |
| J-11 | DONE | A-GATE | SKILL 与 references 的 ≥15 字句子逐字重合 0 条；与 README 的 8-gram Jaccard 0.043；入口主要是任务分流/纪律/导航 | 只证明不重复，不证明内容正确 | 无 | 保留去重检查；内容正确性靠领域审计 |

## 13. 工作包 K：评测、新手/工程师路径与行为验证

范围：`docs/evidence/deepdives-2026-10-22/`、`docs/pr3-integration-review.md`、`references/beginner-journey.md`、`agent-collaboration.md`、`task-scenarios.md`、`assets/scenarios.json`。

| ID | 状态 | 来源/复核 | 证据 | 未完成边界 | 依赖 | 解阻条件 |
|---|---|---|---|---|---|---|
| K-01 | GAP | A-AREA（域 10、11） | H 只有内容层知识练习与目录检查；没有 Agent 行为评测；`tests/` 无对话级断言 | 无行为评测框架/基线 | J-02 | 设计行为评测：任务输入、期望动作、禁止宣称、证据要求、评分；固定模型/版本 |
| K-02 | GAP | A-AREA（域 10、11） | 35 个场景未真实执行；无原始 transcript；12 个必测反例中 7 个只有标签 | 没有真实对话证据 | K-01 | 先跑 5 个高风险场景（F1 类、改板、换料、采购分流、失败恢复）；保存原始输入/输出 |
| K-03 | GAP | A-AREA（域 11） | 历史试答非盲、无对照、旧评分无效；`pr3-integration-review.md:23-28` 明确 196/200、197/200 不能证明题型盲判或 Skill 增益；新盲测输入未运行 | 无有效 Skill 效果证据 | K-01 | 运行新盲测；加无 Skill 基线；固定模型/版本；保留原始输出；重新评分 |
| K-04 | NOT RUN | A-AREA（域 11） | 无基线对照、无固定模型/版本、无评分 rubric 执行记录 | 未执行 | K-03 | 建立对照实验协议；记录模型/版本/温度/日期；用同一评分 rubric |
| K-05 | PARTIAL | A-AREA（域 11） | 仓库没有 H1–H5 定义；`docs/pr3-integration-review.md` 的独立复核未覆盖 round2 EDA 桥；round2 台账只写 H1/H5 未完成 | H1–H5 定义缺失；H5 范围不足 | 无 | 在 docs 写明 H1–H5 定义/验收；H5 增加 EDA 桥独立复核；保留原始评审记录 |
| K-06 | GAP | A-AREA（域 10、11） | 35 个场景 0 个覆盖预算限制/长任务接续/中断恢复；只有文档描述 | 无行为证据 | J-08 | 增加预算/中断/接续场景；用真实长任务验收 |
| K-07 | NOT RUN | R2 E1–E5 | `docs/task-ledger-round2.md:30`：未做真实新手/工程师 Agent 对话试验；本轮未补 | 无真实用户路径证据 | K-01 | 至少各做 3 个新手/工程师任务；保存输入/输出/判据；标注模型/版本 |
| K-08 | GAP | A-AREA（域 10） | `README.md:211` 自述 WorkBuddy 端到端兼容未实测；easyeda-agent 安装器不保证装入 WorkBuddy | 未测宿主兼容性 | 无 | 在 WorkBuddy 实机安装并跑一条最小任务；记录版本/截图/失败点 |

## 14. 工作包 L：台账、状态、交付门禁与回归

范围：`README.md`、`docs/merge-review.md`、`docs/expansion-report.md`、`docs/task-ledger-round2.md`、`docs/evidence/eda-2026-10-21/doctor.json`、`design-hardware/references/product-acceptance.md`、`design-hardware/SKILL.md`。

| ID | 状态 | 来源/复核 | 证据 | 未完成边界 | 依赖 | 解阻条件 |
|---|---|---|---|---|---|---|
| L-01 | DEFECT | A-CONF（域 11，high） | `docs/merge-review.md:35` 仍写“没有运行真实EDA绘图/网表回读/DRC/制造输出”；`docs/expansion-report.md:10/61` 仍写“本机没有 easyeda CLI…未绘制/回读/导出/DRC 任何真实工程”；与 `README.md:85`、`docs/evidence/f1-2026-10-22/` 的真实 EDA 证据冲突 | 这些是历史报告，但未标“历史状态”；读者会误判当前能力 | 无 | 在报告开头加“历史快照，已被 F1/EvidenceDemo 取代”并链接新证据；或更新状态段；不要删除历史记录 |
| L-02 | GAP | A-CONF（域 11，high） | 仓库既有文档无统一六级交付定义：`SKILL.md:160` 用“资料分析/离线规划/实际EDA/制造/样机/功能实测”6 级；`product-acceptance.md:7-14` 用 5 层（图纸回读/构建离线/生产装配/烧录启动/端到端）；中间三级未拆开；无每级证据/禁止宣称。本轮并发产出的 `docs/round3/execution-protocol.md` 已提出 L1–L6 六级与状态枚举，但尚未回写 `product-acceptance.md`/`SKILL.md`/代码，也无自动判定字段 | 状态词混用；“实际 EDA”不等于“回读核对/电气检查/制造资料/样机”；协议仍是提案，未成为仓库门禁 | 无 | 把 `docs/round3/execution-protocol.md` 的 L1–L6 并入 `product-acceptance.md` 与 `SKILL.md`；在 `eda_exec.py` 输出 level/level_status；加 schema/测试；全仓引用后再关闭 L-02 |
| L-03 | DEFECT | A-AREA（域 10、11，medium） | `README.md:366` 写 138 项 unittest；本轮实测 141；同段写“EDA 桥 20 项”，实际 `tests/test_eda_exec.py` 23 项；`docs/task-ledger-round2.md:10` 也写 138 | 文档数字过期；不影响代码 | 无 | 改 141/23；加测试或脚本核对 README 数字；合并前跑一次 |
| L-04 | DEFECT | A-AREA（域 11，medium） | `docs/evidence/eda-2026-10-21/doctor.json` capabilities 写 `sch_export_bom/sch_drc=available`；当前 `eda_exec.py:1283-1284` 明确 `not_implemented_in_this_adapter`；`project_writable=not_tested` 也未更新 | 旧证据未标注过期；读者会以为 DRC/BOM 可用 | 无 | 重生成 doctor.json 或加 `stale:true` + 新 doctor 输出；README 链接指向最新；把 capabilities 测试化 |
| L-05 | DEFECT | A-AREA（域 11，medium） | `docs/task-ledger-round2.md:33` 仍写 G1–G5“未新增跨模块反例”；`design-hardware/references/failures/README.md:30-59` 已有 F23–F33 与“跨模块 12 类覆盖”表；`docs/pr3-integration-review.md:51` 记录并入 dc62f20 | 台账过期；F23–F33 是构造案例，不是真实用户故障 | 无 | 改 G1 为 PARTIAL/DONE（按证据等级），G2–G5 仍 NOT RUN；在 round2 台账加“已被 PR #3 更新”注记 |
| L-06 | DEFECT | A-AREA（域 11，medium） | `docs/task-ledger-round2.md:20` 写“超时先回读”；`references/eda-execution.md:99` 写“超时后仍要先回读”；`command_apply:1430-1439` 无此路径；`execution.results` 不参与验证 | 台账/文档与代码不一致；实际重试会重复创建 | B-08 | 实现“未知结果强制回读”后再保留该声明；否则改文档；补故障注入测试 |
| L-07 | GAP | A-AREA（域 11，medium） | H1–H5 在仓库内无定义；H5“独立集成复核”未覆盖 round2 EDA 桥；round2 台账只写 H1/H5 未完成 | 评测任务不可验收 | K-05 | 在 docs 写 H1–H5 定义/验收；H5 增加 EDA 桥复核；保留评审记录 |
| L-08 | GAP | A-AREA（域 11，medium） | `expansion-report.md:66-82` 五项“未完成/下一步”未按当前状态结转：1 项 PARTIAL（F1），其余仍 NOT RUN；当前状态文档未逐项引用 | 历史待办会丢失 | 无 | 把五项映射到本台账 D/E/F/K 任务；在 expansion-report 加“当前状态见 round3 台账” |
| L-09 | GAP | A-AREA（域 11，medium） | 热专题 `docs/thermal-original-handoff.md:78-149` 的 NOT RUN/BLOCKED 清单未进入当前状态文档；7.6 主题与 JEDEC/IPC 缺口面临消失 | 热专题边界可能被误读为已验收 | 无 | 把热专题未完成项并入 L/G 台账；在 `references/thermal/topic.md` 标 NOT RUN |
| L-10 | GAP | A-AREA（域 11，medium） | PR #3 深潜/审图试验的未完成项未进入台账；旧评分不能作为 Skill 效果证据；新盲测未运行 | 评测欠账隐藏 | K-03 | 把 PR #3 未完成项并入 K；保留旧评分“历史记录”标签；运行新盲测 |
| L-11 | PARTIAL | A-AREA（域 11，medium） | round2 的 PARTIAL 项仍准确（B3 多页、F1 排版/DRC），但缺可执行验收判据；`docs/task-ledger-round2.md:25/31/52` 只有描述 | 无法判断何时从 PARTIAL 转 DONE | 无 | 为每个 PARTIAL 写“通过判据+证据+复跑命令”；本台账 C-10/D-03/D-10 已给 |
| L-12 | NOT RUN | A-AREA（域 11，medium） | round2 的 NOT RUN 大项仍无完成证据：A3/A4/B1/B2/B4 边界、WorkBuddy 兼容性；`README.md:211` 未测 | 未执行；不得因新增文档转 DONE | 无 | 按 K-08/E-12/C-10 逐项执行；每项保留证据 |
| L-13 | BLOCKED | A-AREA（域 11、域 5，medium） | 全在线 GUI 复验仍 BLOCKED：CLI 会话恒半离线；两个 alive 会话都是 `origin=user` 的 GUI；本轮未操作 | 需用户 GUI 授权 | 用户 GUI 会话 | 用户在全在线 GUI 会话执行同一 F1/PCB 探针；记录 sessionId/build/online/截图；不得用半离线替代 |
| L-14 | PARTIAL | A-AREA（域 11，low） | `doctor.json` `project_writable=not_tested`；A5 close→reopen 证据边界未更新；`README.md:76` “PC未实现”是笔误（应为“PCB未实现”） | 只影响可读性/状态精度 | 无 | 改笔误；更新 A1/A5 状态；doctor 增加可写性实探或明确 not_tested |
| L-15 | DONE | A-GATE | 141 tests OK；F1 `apply-result.json` 93/93 verified、`save.saved=true`、`saved_readback 16/27/16/44`；`reopen-check.json match`、parts 16/16、wires 34/34；4 个证据文件 SHA256 与 README 一致（`AUD/a5-a2/unittest-full.log`、`benchmark.log`） | 证据自洽不等于验证域完整；A-02/A-04/A-05/B-09 已指出 verified 口径过宽 | 无 | 保留为基线；修完 A/B 后重跑 F1 并生成新证据，旧证据标“范围窄” |

## 15. 跨域门禁与下一步退出标准

第三轮结束前，以下条件必须同时满足；否则只能按 PARTIAL/NOT RUN 报告，不得写“第三轮完成”。

1. **读取完整性**：SNAPSHOT_JS 产生 `read_errors[]`；`pins_complete`/`attributes_complete` 被 Python 消费；任何 incomplete 快照不得进入 apply/reopen-check。
2. **回读真实性**：`verify_against_snapshot` 逐字段比较 designator/unique_id/component/supplier/footprint/x/y/rotation/mirror；使用 execution 返回的 primitive_id；改位号未生效、创建回读 R? 均必须 failed 且 reason 可区分。
3. **位号唯一性**：同一计划内重复、改位号撞车、新器件占用已有位号、跨页重复均在 apply 前 conflict；有单测。
4. **写入安全**：apply 校验 project/page UUID + 快照时间/哈希；漂移拒绝；unknown 结果强制回读；不向 `origin:user` 会话写入；reopen-check 不关闭无关会话，比较 project/page 身份与 netports。
5. **测试**：新增失败用例覆盖 A/B 每条 DEFECT；`tests/test_eda_exec.py` 覆盖 read/save/export/reopen-check；全仓 141+ 新用例 OK。
6. **PCB**：`eda_exec.py` 有 pcb-read/apply/save/export/reopen 命令；F1 PCB 完成板框/导入/布局/布线/过孔/铺铜边框/DRC/导出/保存重开；每个步骤有 JSON 证据；DRC 有 clean baseline 与增量。
7. **F1 电气/排版**：D-01/D-02/D-06 修正；D-03 C4 门禁把重排前后 pin-net diff 做到 0；D-07 多余导线清除；D-10 重排后人工看图通过；未测项标 NOT RUN。
8. **电气文档**：G-01/G-02、H-04/H-05、I-01/I-02 修正并重算；I-03 重画；每个修改附复算输出/原厂页码。
9. **状态可信**：L-01/L-03/L-04/L-05/L-06 修正；README/doctor/round2 台账与当前代码/证据一致；L-02 六级状态定义落地。
10. **评测**：J-01 删除无证据的“已试跑”或补证据；K-03 新盲测运行并保留原始输出/基线对照；否则 README 只能写“未执行”。

## 16. 证据索引

| 领域 | 证据根（`AUD/` 下） | 关键文件 |
|---|---|---|
| EDA 执行桥（读取/验证/重开/测试） | `eda-exec/`、`eda-exec-verify/`、`b1-verify/`、`B2-01/`、`codepath/`、`code-path-repro/` | `repro_results.json`、`probe-output.txt`、`coverage_report.json`、`unittest_eda_exec.txt`、`verify_results.json` |
| 原理图几何/基准 | `schematic-layout/`、`verify-R3-SCH-01/` | `benchmark-run.json`、`extras-summary.txt`、`d6-probes*.txt`、`f1-crowding-probe.txt`、`snapshot-check.txt` |
| F1 证据 | `f1-evidence/`、`a5-a2/` | `geom_check.txt`、`pins.txt`、`wires.txt`、`datasheets/`、`unittest-full.log` |
| PCB 闭环 | `pcb-closed-loop/` | `probe-pcb-result.json`、`probe-pcb-write-result.json`、`probe-f1-pcb.json`、`probe-f1-reopen.json`、`probe-reopen-counts.json` |
| 制造/供应链 | `f3-bom/` | `f1-bom-draft.csv`、`f1-bom-coverage.json`、`audit-evidence.txt` |
| 电源/热 | `power-thermal/`、`power/`、`power-battery/` | `verify_power.out`、`corrections.out`、`slva118_fig5_crop.png`、`budget_52_40.json`、`recompute-output.json` |
| 模拟/接口 | `analog-interfaces/`、`analog/` | `recompute.log`、`adversarial-ana07-recompute.log`、`a03-circuit-check.txt` |
| Skill/评测 | 仓库内 `docs/evidence/deepdives-2026-10-22/`、`design-hardware/assets/scenarios.json`、`tests/` | README、scenarios.json、test_skill.py、test_scenarios.py |

> 说明：`docs/round3/capability-matrix.md` 与 `docs/round3/execution-protocol.md` 是本轮并发产物，不是本台账写入的文件；本台账只引用其状态口径（L1–L6）作为 L-02 的解阻输入，不把它们当作已验收证据。若这两个文件后续被修改，以它们各自的版本为准。

## 17. 非声明

- 本台账不声称 141 项测试通过等于工程正确；测试主要验证工具、结构、路由与已编码反例。
- 本台账不声称 F1 是可生产板；F1 仅完成原理图连接/保存/重开证据，PCB/DRC/ERC/制造/样机/固件均 NOT RUN。
- 本台账不声称 PCB 已闭环；客户端 API 探针可用，但 Skill 适配器未实现。
- 本台账不声称任何 C 号当前可购/可贴；所有实时库存、价格、MOQ、交期、SMT 状态仍待真实渠道核对。
- 本台账不声称电气设计已实测；所有电源/电池/模拟结论仍是离线计算或文档审查，除非明确写“实测”。
