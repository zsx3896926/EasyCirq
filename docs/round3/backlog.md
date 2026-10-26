# 第三轮待办清单（2026-10-22）

基线：`C:/Users/jlc/work/hds-round3` @ `dc62f20`。状态与证据口径见 [task-ledger-round3.md](../task-ledger-round3.md)。
排序依据：本轮 14 条交叉复核 finding 的修正严重度 + 是否会产生“错误 verified/重复写入/会话越权/虚假声明” + 真实硬件风险。P0 先修，P1 次之，P2/P3 随后。每条一行；证据中的 `AUD` = `C:/Users/jlc/work/hw-deepdive-scratch/round3-audit/`。

> **2026-10-22 修复更新**：P0-01～P0-07 与 P1-01/P1-02 已由 [executor-fixes-2026-10-22.md](executor-fixes-2026-10-22.md) 处理。修复后状态：P0-01 PARTIAL（真实故障注入 NOT RUN）、P0-02 DONE、P0-03 DONE、P0-04 PARTIAL、P0-05 DONE（单测）、P0-06 DONE、P0-07 PARTIAL（全快照 hash NOT RUN）；P1-01/P1-02 PARTIAL～DONE。P0-09（AMS1117 电容）换型完成但电源稳定性未实测，P0-10（IO2 悬空）已由 [F1 电气修订](f1-electrical-revision-2026-10-22.md) 修复；P1-05 的网表 diff 工具已完成并加严（无效输入拒绝、纯重排要求整个 diff match），纯重排门禁仍 NOT RUN；P1-06/P1-07 仍待重排。下表保留审计时的原始状态作为历史快照，不再作为当前状态真源。

## P0：先修“错误成功、重复写入、越权、虚假声明、F1 电气阻断”

| 优先级 | ID | 状态 | 任务 | 影响 | 证据 | 下一条具体动作 | 真实 EDA/实物 |
|---|---|---|---|---|---|---|---|
| P0-01 | A-01 | DEFECT | 读取失败不得折叠为 null/空数组 | 一次 getter 异常会让已有器件“消失”，触发重复创建同号器件，且 apply 仍 verified | `eda_exec.py:378-380,458-480,481-498,533-540,553-563`；`AUD/eda-exec/repro_results.json` F1；`AUD/verify-b1-01/` | SNAPSHOT_JS 增加 `read_errors[]`；Python 侧 read_errors 非空即拒绝 apply/reopen-check；补 null designator/缺 pins 单测 | 是（真实 EDA 故障注入） |
| P0-02 | A-02 | DEFECT | 逐项验证必须比对 designator 并使用执行返回的 primitive_id | 改位号未生效仍判 verified；创建回读 R? 反被判失败；验证与真实对象脱钩 | `eda_exec.py:1101-1133,1430-1439`；`APPLY_JS:637-642`；`AUD/eda-exec/repro_results.json` F2；`AUD/B2-01/verify_results.json` S1–S3 | command_apply 传 execution key→primitive_id；逐字段 expected/observed；R? 报 designator_mismatch；补表驱动测试 | 是（真实 EDA modify/create 回读） |
| P0-03 | B-01 | DEFECT | 位号唯一性覆盖计划内、改位号撞车、新器件占用已有位号、跨页 | 会制造重复位号，网表/BOM/装配无法区分，且验证可能通过 | `eda_exec.py:915-1081`；`AUD/eda-exec/probe_b3_b4_b6_b8.py` | reconcile 前做计划 designator 集合冲突；跨页查工程页清单；三类冲突各补单测 | 部分（真实多页工程） |
| P0-04 | B-04 | DEFECT | 超时/失败重试不得重复创建 R? 孤儿 | 重试一次多一个器件；R? 孤儿不会被认领 | `command_apply:1430-1451`；`AUD/eda-exec/probe-output.txt` D/F | 未知结果强制回读；按 position+part+supplier 认领 R?；确认未写入才允许重试；补故障注入 | 是（真实超时/断连注入） |
| P0-05 | B-05 | DEFECT | 会话来源边界：不得向 origin:user 写入，unknown origin 不得关闭 | 可能改动用户正在编辑的工程或关闭用户会话 | `close_owned:1249-1255`；`tests/test_eda_exec.py:329-335` | origin 白名单；unknown 视为 user；写入用户会话需显式 unsafe 并记录；补 unknown origin 测试 | 是（真实多会话） |
| P0-06 | B-06 / B-09 | DEFECT | reopen-check 必须校验工程/页身份，且比较 netports/mirror/attributes/BOM/PCB | 会关闭无关工程；删端口/翻 mirror 仍 match，重开证据是假阳性 | `command_reopen_check:1502-1514`；`compare_snapshots:1163-1211`；F1 快照删端口/翻 mirror 复现 | 先核对 session→project；比较 project/page UUID；扩展比较域；坐标统一容差；失败报 incomplete | 是（真实 F1 工程变异） |
| P0-07 | B-02 / B-03 | DEFECT | apply 写前条件与页身份冻结 | 读后被用户改动的工程会被静默覆盖；current/同名页可能写错页 | `command_apply:1395-1430`；`PAGE_SELECT_JS:376-420` | before 记录 project/page UUID+snapshot hash/time；写前重读比对；current 固化 UUID；写后断言页一致 | 是（真实并发编辑） |
| P0-08 | E-01 | GAP | 给 `eda_exec.py` 增加 PCB 命令族 | Skill 目前完全不能读写/保存/导出 PCB，E2–E10 全被适配器卡住 | `eda_exec.py:1285`；`AUD/pcb-closed-loop/probe-pcb-result.json`、`probe-pcb-write-result.json`、`probe-f1-pcb2.json` | 实现 pcb-read/apply/save/export/reopen-check；用 `dmt_Pcb.getAllPcbsInfo` 选页；doctor 加 PCB 实探；先以 F1 PCB 做回归 | 是（真实 EDA PCB） |
| P0-09 | D-01 | DEFECT | AMS1117 输出电容满足 22µF 钽/ESR 0.3–22Ω 稳定性要求 | 10µF X5R 陶瓷可能使 LDO 不稳定；F1 被当证据会传播错误设计 | `p04-usb-mcu-board.md:26-30`；F1 README:78；`AUD/f1-evidence/datasheets/ams1117_utd.txt:218,235`、`lm1117_ti.txt:718-724` | 改 C103 为满足 ESR/容值的 22µF 钽或加 ESR/换 LDO；补计算与实测计划；未验证前 F1 标 PARTIAL | 是（实物/台架纹波与负载瞬态） |
| P0-10 | D-02 | DEFECT | ESP-01S IO2 不得悬空且无 NC | GPIO2 boot strapping 可能让模块无法正常启动；全页 noConnected=false 掩盖 | `snapshot.json:533`；`AUD/f1-evidence/datasheets/esp8266ex.txt:408` | 加 10k 上拉或明确 NC 并记录 boot 影响；补上电/下载测试；更新 F1 证据 | 是（实物上电/下载） |
| P0-11 | L-01 / L-03 / L-04 | DEFECT | 状态文档、测试数字、doctor 证据与当前代码/证据对齐 | 读者会以为“未做真实 EDA”或“DRC/BOM 可用”；交付可信度受损 | `docs/merge-review.md:35`；`docs/expansion-report.md:10/61`；`README.md:366`；`docs/evidence/eda-2026-10-21/doctor.json` vs `eda_exec.py:1283-1284` | 历史报告加“已被 F1/EvidenceDemo 取代”；改 138→141、20→23；重生成 doctor 或标 stale；加数字核对测试 | 否（文档/证据） |
| P0-12 | J-01 | DEFECT | 删除或证明 README 的“已进行场景试跑” | 与 round2 E1–E5 NOT RUN 矛盾；无原始记录，属过度声明 | `README.md:363-364`；`docs/task-ledger-round2.md:30` | 删除“已试跑”或改“未执行”；若保留，附输入/输出/评分/模型版本/日期；与 K-02/K-03 同步 | 部分（真实 Agent 对话） |

## P1：高严重度电气内容、证据链与核心能力

| 优先级 | ID | 状态 | 任务 | 影响 | 证据 | 下一条具体动作 | 真实 EDA/实物 |
|---|---|---|---|---|---|---|---|
| P1-01 | A-03 / A-04 / A-05 | DEFECT | 完整性标志、属性字段、netflag type/netport direction/mirror/rotation 纳入验证 | `verified` 只核对了部分字段；F1 16 端口“verified”只核网名+坐标 | `eda_exec.py:485-511,1116-1133`；F1 `apply-result.json`；`snapshot.json:2668-2669` | 增加 read_errors/complete 消费；逐字段 expected/observed；getter 不可读时标 unverified_fields；重跑 F1 | 是（真实 EDA 回读） |
| P1-02 | B-07 / B-08 | DEFECT | 客户端版本/在线门禁；未知结果强制回读并使用 execution.results | 任意版本可写；超时后重试重复创建；文档“超时先回读”未实现 | `command_doctor:1268-1300`；`command_apply:1430-1439`；`eda-execution.md:99`；`task-ledger-round2.md:20` | doctor 记录 build/versionMatch/online；写入设最低版本；未知结果先回读；单项 results 对齐 plan key | 是（真实版本/超时） |
| P1-03 | C-01 / C-02 | DEFECT | 8 类基准加精度门禁与对象级期望 | 全 code 假检查器仍 8/8；B2/B3/B6/B7 的未声明发现被隐藏 | `schematic_benchmark.py:35-44`；`tests/test_schematic_benchmarks.py:40`；`AUD/schematic-layout/overreport-control.txt`、`extras-summary.txt` | 增加 `expected_findings`/`forbidden_codes`；runner 对 observed-expected 失败；加全 code 负向测试；修基准引脚坐标 | 否（离线） |
| P1-04 | C-03 / C-04 | GAP/DEFECT | 真实 snapshot→layout 适配器；端点连接语义 | F1 快照直跑失败；近失端点不报悬空，附近异网导线制造假冲突 | `sch_layout_check.py:2`；`AUD/schematic-layout/snapshot-check.txt`、`d6-probes*.txt` | 写转换器（part/pin/wire/flag/port/text bbox）；端点连接只认 pin/flag/port；网名按连通分量；补正反例 | 部分（真实 EDA 导出） |
| P1-05 | D-03 | GAP | C4 重排门禁：pin→net 规范化 diff 为 0 | 现有 netlist+snapshot 不能证明纯排版前后引脚-网络不变；reopen-check 对重排必 mismatch | `reopen-check.json`；`compare_snapshots`；`snapshot.json:2670-2675` | 增加 `netlist diff` 工具；重排前后各导出一次；0 个 pin-net 变化才通过；把哈希/两次导出入库 | 是（真实 EDA 重排/导出） |
| P1-06 | D-07 | DEFECT | 清除 F1 多余导线并让 apply 报告未计划对象 | 2 条悬空 CC 短线 + 10 条零长线；验证只查计划项存在 | `AUD/f1-evidence/geom_check.txt`、`wires.txt`；`verify_against_snapshot` | 删除/合并多余线；apply 增加 extra_objects 报告；C4 diff 计入；重跑 F1 | 是（真实 EDA） |
| P1-07 | D-10 | DEFECT | F1 排版重排并做人工视觉复核 | U102 flag 10 单位间距、U101/J102 文字碰撞；无 layout-check 证据 | `schematic.png` 与裁图；F1 README:74 | 重排 U102/J101/U101/J102；重排前后网表 diff；导出 PNG 人工看图；未过前保持 PARTIAL | 是（真实 EDA + 人工视觉） |
| P1-08 | E-02 | PARTIAL | 铺铜不能只建边框 | `PCB_PrimitivePoured.create` 空操作；pours=2/poured=1；无重算 API | `AUD/pcb-closed-loop/methods/PCB_PrimitivePoured.create2.json`、`probe-outline-pour.json`、`probe-reopen-counts.json` | 找 GUI/在线重算入口或明确“仅边框”；验收同时报 pours/poured；不要声称铺铜完成 | 是（GUI 全在线） |
| P1-09 | E-03 / E-04 / E-05 / E-06 | DEFECT/PARTIAL | PCB 创建/导入/器件/板框核心路径 | createPcb 静默 undefined；importChanges 不建框不布线；component.create 拒绝 state 对象；无板框 API | `AUD/pcb-closed-loop/probe-project-tree.json`、`probe-f1-pcb.json`、`probe-pcb-component.json`、`probe-outline-pour.json` | 封装 createBoard→createPcb；import 后报告 outline/routing/DRC 缺口；统一扁平 component ref；board-outline 命令 | 是（真实 EDA PCB） |
| P1-10 | F-01 / F-02 / F-03 | GAP/PARTIAL/DEFECT | BOM/CPL/Gerber/manifest 能力与证据链 | 无制造资料生成；F1 BOM 草稿不完整；apply/reopen 引用 scratch，无法证明是同一份 | `eda_exec.py:1283-1285,1580`；`AUD/f3-bom/`；`apply-result.json:3`、`reopen-check.json:3-5` | 实现/封装 BOM/CPL/Gerber；`bom_check.py` 标“待查”；生成 manifest（SHA256/时间/build/工程 UUID/plan hash） | 是（真实 EDA/制造导出） |
| P1-11 | F-05 / F-06 | DEFECT | 修正 attributes_complete 语义；扩大 apply/reopen 验证域 | `attributes_included=false` 仍 complete=true；footprint/manufacturer/netports/mirror/add_into_bom 未验证 | `eda_exec.py:507-510,1116-1133,1218`；`snapshot.json:2668-2669` | 未请求属性写 null；CLI 加 include-attributes；统一验证域清单；重生成 F1 snapshot | 是（真实 EDA） |
| P1-12 | G-01 | DEFECT | 修正 Boost IMAXOUT 公式 | 低估输出能力 34–45%，把可通过 0.4A 的 2.5A 限流器件判淘汰 | `power-thermal.md:97`；`p03-boost.md:40/125/184/216`；`AUD/power-thermal/slva372.txt:106-108,316-319` | 改成 `(ILIM(min)−ΔIL/2)·(1−D)`；p03 重跑 3.0/2.5A；§4.3 拆 Buck/Boost；加回归 | 否（离线计算） |
| P1-13 | G-02 | DEFECT | 修正 SLVA118A Figure 5 封装列错位 | SOT-23/SOIC 热数据取错列；普通 SOIC-8 TJ 由 116–172°C 误报 90–107°C | `power-thermal.md:129,250,257-259`；`power-ics.md:68,294`；`AUD/power-thermal/slva118_fig5_crop.png` | 按原表 14 列重新对齐；删 DBV 154–330；SOIC D 用 97–178/55 重算；同步 power-ics；加源表核对记录 | 否（离线计算） |
| P1-14 | H-04 | DEFECT | F14 稳压管钳位必须加电源电压 | 24V+40V+0.7V=64.7V>60V，按“40<60”规则会放行，FET 每次关断进雪崩 | `f14-relay-flyback.md:45,61`；SLVAE59A §3.2.2；`AUD/power/slvae59a.txt` | 改规则为 `VDD(max)+VZ(max)+VF(max) ≤ VDS(max)`；补 24V/40V 算例；测 VDS | 是（继电器台架/示波器） |
| P1-15 | H-05 | DEFECT | 修正 energy-battery §5.2 等比缩放 | 40 次/天实际 58.4 天而非 89 天；90 天需约 16.6 次/天，频次建议偏差 2.4× | `energy-battery.md:259`；`AUD/power/budget_52_40.json` | 用状态表重跑替换缩放；报告 40→58.4、39→59.3、90 天 16–17 次/天；把 JSON 入库 | 否（离线计算） |
| P1-16 | I-01 | DEFECT | 高侧电流采样失调项 10mA→100mA | 低端误差低估 10 倍；0.5A 处 9.9%→22.2%；结论由 CMRR 主导变为 V_os 主导 | `a07-high-side-sense.md:144,146-147,149`；`AUD/analog-interfaces/recompute.log` | 改 100.0mA/1.00%；重算 RSS/worst；改 0.5A 结果；同步 :164-166 | 否（离线计算） |
| P1-17 | I-02 | DEFECT | I²C N-MOS 结论与同文修正一致 | 结论仍写 1.7k/1.5k 满足，实际联合灌电流 4.64mA>3mA，会误导选型 | `i12-level-shift.md:167,188-189,210` | 改 :210 为“单侧边沿候选成立，联合灌电流失败”；保留 :167/188-189；明确未选定最终上拉 | 否（离线计算） |
| P1-18 | J-02 | GAP | 35 场景与 12 必测反例有可执行检查 | 目前仅 5 个 check；7/12 反例只有标签；测试只验字段/路由/文件存在 | `scenarios.json`；`tests/test_scenarios.py`；`AUD` 域 10 | 12 个反例各有检查或明确“未自动化”；增加 must_do/must_not_claim 行为断言；用真实对话记录验收 | 部分（真实 Agent 对话） |
| P1-19 | J-03 | GAP | 运行盲测并保留原始输出/对照组 | 唯一试答非盲、无过程记录、无对照；旧评分不能证明 Skill 增益 | `docs/evidence/deepdives-2026-10-22/README.md`；`pr3-integration-review.md:23-28` | 运行新盲测输入；固定模型/版本；保留原始输出；加无 Skill 基线；答案不随包分发 | 是（真实 Agent 实验） |
| P1-20 | L-02 | GAP | 统一六级交付状态定义 | 仓库状态词混用；“实际 EDA”未拆回读/电气/制造/样机，容易把半成品写成 DONE | `SKILL.md:160`；`product-acceptance.md:7-14`；并发产出 `docs/round3/execution-protocol.md` L1–L6 | 把 L1–L6 并入 `product-acceptance.md`/`SKILL.md`；在 `eda_exec.py` 输出 level/level_status；加 schema/测试；全仓引用 | 否（文档/门禁） |
| P1-21 | L-05 / L-06 | DEFECT | 修正 round2 台账过期项 | G1–G5 仍写“未新增跨模块反例”（PR #3 已加 F23–F33）；A3“超时先回读”未实现 | `task-ledger-round2.md:20,33`；`failures/README.md:30-59`；`command_apply:1430-1439` | 改 G1 状态与证据等级；A3 改为 DEFECT 或先实现回读；加“已被 PR #3 更新”注记 | 部分（代码/证据） |
| P1-22 | A-06 / A-07 | DEFECT/GAP | 统一异常与错误码契约 | save 抛 AttributeError；reopen 抛 FileNotFoundError；超时/页不存在折叠成 EDA_PROJECT_NOT_READY | `command_save:1461-1469`；`command_reopen_check:1502-1508`；`read_with_retry:1226-1239`；`AUD/eda-exec/probe-output.txt` F14/F16/F17 | 所有入口包 EdaCommandError；保留原始 code；补 JSON/退出码/文件缺失/空坐标测试 | 是（真实 CLI 失败模式） |

## P2：中严重度能力/内容缺口

| 优先级 | ID | 状态 | 任务 | 影响 | 证据 | 下一条具体动作 | 真实 EDA/实物 |
|---|---|---|---|---|---|---|---|
| P2-01 | C-05 / C-06 / C-07 / C-08 / C-09 | GAP/DEFECT | 模块框穿线、成员判定、schema 扩展、静默几何、F1 拥挤 | B8 长地线穿三模块不报；B7 成员误报；多页/多单元/文字外框无法表达；F1 拥挤不可发现 | `AUD/schematic-layout/frame-wire-probe.txt`、`extras-summary.txt`、`d4-schema-probes.txt`、`d6-probes*.txt`、`f1-crowding-probe.txt` | 加 wire-frame crossing；成员用完整包含/面积；扩展 schema；补共线/共享端点；接入真实文字外框后再评 F1 排版 | 部分（真实 EDA 几何） |
| P2-02 | E-07 / E-08 / E-09 / E-12 / E-14 | GAP/PARTIAL/NOT RUN | PCB 飞线、制造导出、保存重开、真实布线、DRC 基线 | 只能间接验收连通；适配器导出仅原理图；PCB save/reopen 未接入；无 clean DRC baseline | `AUD/pcb-closed-loop/probe-pcb-result.json`、`probe-pcb-write-result.json`、`probe-reopen-counts.json` | 增加 pcb-export（Gerber/CPL/BOM）；用 DRC+net length+pad 建未布网络报告；记录 DRC 增量；做 pad-to-pad 布线 | 是（真实 EDA PCB） |
| P2-03 | F-04 / F-07 / F-08 / F-09 / F-10 | GAP/DEFECT | CPL、closed_session、制造文档、渠道字段、C 号分级 | 无 PCB/CPL；reopen 未证明关闭后重开；manufacturing-routes 仍称无 EDA 工具；supplier=LCSC 易误读为可贴；C 号无商城核实 | `snapshot.json`；`reopen-check.json:5`；`manufacturing-routes.md:7`；`AUD/f3-bom/` | 生成 CPL；记录 sessionId/关闭时间；改 manufacturing-routes 表述；BOM 加 channel/verified_at/stock；C 号标“库回读/商城待查” | 部分（真实渠道/PCB） |
| P2-04 | G-03 / G-04 / G-05 / G-06 / G-07 / G-08 / G-09 / G-10 / G-11 | DEFECT/GAP | 电源/热文档与计算器修正 | TPS7A02 TJ(max) 误记；p02 负载阶跃/二极管/输入电容 RMS 错；栅极损耗不随频率；ripple_ratio 不一致；计算器缺 ILIM/VFB/IFB；热建议不可执行 | `power-thermal.md` 5.1/5.3；`p01/p02`；`calculate.py`；`thermal_calc.py` | 按清单逐项重算；增加 ILIM/VFB/IFB 输入；统一 ripple_ratio；给铜面积/过孔数值目标；补脚本测试 | 否（离线计算） |
| P2-05 | H-01 / H-03 / H-06 / H-07 / H-08 / H-09 / H-10 | DEFECT/GAP | 电池保护/充电文档修正 | UVP 零余量；CC worst-case 未覆盖 5.5V/56k±20%；PWR-05 无迟滞；5.3 漏系统电流；PWR-06/07 误称未读；PWR-12 引错条款 | `p08`、`p12`、`p05`、`energy-battery.md` §5.3、`p06`、`p07` | 用 min/max 重算 UVP/OCD/CC；补迟滞与系统电流；改“未读”为已读页码；补电感公式；标典型/保证 | 部分（台架 UVP/OCD/CC） |
| P2-06 | I-03 / I-04 / I-05 / I-06 / I-07 | DEFECT/GAP | 模拟/接口文档修正 | 差分拓扑图错；基准温区不自洽；0.0202% 残差缺说明；噪声单位错；SPI 公式缺失 | `a03:74-87,91-100,286/288`；`a05`；`analog-adc.md` 基准表；`a02`；`i03` | 重画拓扑并改逐脚表；改温区/补残差；改 LSB 口径；补 SPI 公式；用 EDA 网表/直流扫描验证 | 部分（EDA 网表/仿真） |
| P2-07 | J-04 / J-05 / J-06 / J-07 / J-08 | PARTIAL/GAP/DEFECT | 安装分层、action-map、数字、场景权重、预算/中断 | 包约 5.6MB/240 文件，单路由可载 121KB；24 条 action-map 不可达；README 22 vs 33、138 vs 141；场景无权重；0 个预算/中断场景 | `design-hardware/`；`SKILL.md` §3；`README.md:71/309/366`；`scenarios.json` | 拆 core/deep；接入 action-map；改数字并加核对测试；加 risk/weight/pass_threshold；补预算/中断场景 | 部分（真实 Agent 长任务） |
| P2-08 | K-01 / K-02 / K-03 / K-04 / K-05 / K-06 / K-07 / K-08 | GAP/NOT RUN/PARTIAL | 行为评测、场景执行、盲测对照、H1–H5、预算/中断、E1–E5、WorkBuddy | 没有 Agent 行为证据；35 场景未执行；旧试答无效；H1–H5 无定义；新手/工程师路径未测；WorkBuddy 未兼容实测 | `docs/evidence/deepdives-2026-10-22/`；`pr3-integration-review.md`；`README.md:211`；`task-ledger-round2.md:30` | 建行为评测协议；先跑 5 个高风险场景；固定模型/版本；加基线；写 H1–H5；测 WorkBuddy | 是（真实 Agent/宿主） |
| P2-09 | L-07 / L-08 / L-09 / L-10 / L-11 / L-12 | GAP/PARTIAL/NOT RUN | 评测定义、历史待办、热专题、PR #3、PARTIAL 判据、NOT RUN 大项 | H1–H5 未定义；expansion-report 五项未结转；热专题 NOT RUN 清单会消失；PR #3 欠账隐藏；PARTIAL 无判据；NOT RUN 无证据 | `docs/` 各报告；`thermal-original-handoff.md:78-149`；`task-ledger-round2.md` | 把未完成项映射到本台账；写 H1–H5；给每个 PARTIAL 通过判据；逐项执行 NOT RUN | 部分（视任务） |
| P2-10 | A-08 / A-09 | PARTIAL/GAP | 测试覆盖与 CLI 入口 | 26/60 函数未执行；reopen/read/save/export 零覆盖；无 include-attributes/max-pins 入口 | `AUD/eda-exec/coverage_report.json`；`eda_exec.py:1218,1577-1585`；`tests/test_eda_exec.py` | 加故障注入/契约测试；CLI 增加 attributes/max-pins；把字符串断言换行为断言 | 部分（真实 EDA 测试） |
| P2-11 | D-04 / D-05 / D-06 / D-08 / D-09 | GAP/PARTIAL | F1 USB-C/UART/复位/封装/热边界 | 壳脚悬空、无 ESD/保险；J102 方向不清；EN/RST 无 RC；网表是符号级；LDO 热/峰值电流未测 | `pins.txt`、`schematic.net:31-39,1152-1188`；`esp8266_hw_guidelines.txt`；F1 README:78-80 | 壳脚接地/NC；加 ESD/保险候选；标 J102 定义；加 100nF；建封装-焊盘映射；补热/峰值实测 | 是（实物/台架） |
| P2-12 | E-10 / L-13 | BLOCKED | 全在线 GUI 复验 | CLI 恒半离线；用户 GUI 会话未授权；在线库/DFM/铺铜重算未验证 | `AUD/pcb-closed-loop/probe-pcb-result.json` env；doctor sessions | 用户在全在线 GUI 执行 F1/PCB 探针；记录 sessionId/build/online/截图；不得用半离线替代 | 是（全在线 GUI） |
| P2-13 | F-14 | BLOCKED | 嘉立创实时数据（库存/价格/MOQ/SMT/DFM/下单） | 无实时数据；不能声称可购/可贴/可下单 | `manufacturing-routes.md:5/614`；`lcsc-verification.md:83-93` | 有授权时逐项核对至少 10 个关键料；只查不买；记录 URL/时间/字段；无授权保持 BLOCKED | 是（真实渠道） |

## P3：低严重度与文档一致性

| 优先级 | ID | 状态 | 任务 | 影响 | 证据 | 下一条具体动作 | 真实 EDA/实物 |
|---|---|---|---|---|---|---|---|
| P3-01 | I-08 / I-09 | DEFECT | 清理重复补丁与最坏相加 | CAN 表断裂、x03 表重复 3 次、a10 跳号；桥式 2.93% vs 3.022% | `i08-can.md`、`x03`、`a10`、`a09` | 去重/修编号；统一 RSS/最坏算法；加链接/结构测试 | 否 |
| P3-02 | F-11 / F-12 | DEFECT/GAP | Mark 开窗口径统一；官方页面存档 | 2mm vs 3mm/2mm 不一致；页面变化无法复核 | `jlc-smt-rules.md`；`manufacturing-routes.md`；`source-register.md` | 以当前官方规则统一；分服务/拼板列值；保存页面截图/PDF 或哈希 | 部分（官方渠道） |
| P3-03 | G-12 | DEFECT | 修正两处手算口径 | x01 用理想 D 回算 ΔIL；5.1 的 10µH 淘汰按 9µH | `x01-buck-loop.md`；`power-thermal.md` 5.1 | 用实际 D 重算；修正淘汰数字或标明 9µH | 否 |
| P3-04 | H-02 | DEFECT | 把 OCD 19% 标为典型并给保证带 | 典型值被当保证余量；热态可能误跳 | `p08:143-145`；SLUSBU9I §6.6/Features | 标“典型 19%”；用 ±10/±15mV 与 Rds(on) max 重算；给误跳条件 | 部分（台架脉冲） |
| P3-05 | J-09 | PARTIAL | 压缩 SKILL 入口与 §0 | 30.5KB/237 行 + 49 行索引偏重；§0 像发布说明 | `SKILL.md` | 压缩 §0；发布说明移出；主索引分层 | 否 |
| P3-06 | L-14 | PARTIAL | 修 README 笔误与 A1/A5 状态 | “PC未实现”应为“PCB未实现”；doctor 可写性未测；A5 证据边界未更新 | `README.md:76`；`doctor.json` | 改笔误；更新 A1/A5；doctor 增加可写性实探或明确 not_tested | 否 |
| P3-07 | E-11 | GAP | 不把 .eprj2 SQLite 表当文档清单真源 | boards=0/documents=2 与运行时 1 board/1 PCB/10 schematics 不一致 | `AUD/pcb-closed-loop/eprj2-schema.txt`、`probe-project-tree.json` | 文档/脚本改用运行时 API 枚举；SQLite 只做辅助；加注记 | 部分（真实工程） |
| P3-08 | C-10 | NOT RUN | 真实多页/图框/阅读顺序验收 | 只有单页证据；B3 仍 PARTIAL | `task-ledger-round2.md:25`；`docs/evidence` 无多页工程 | 用一个真实多页工程执行分页/图框/跨页网络/阅读顺序验收；保存截图/网表/哈希 | 是（真实 EDA 多页） |

## 完成定义（DoD）

- P0 全部关闭：A-01/A-02/B-01/B-04/B-05/B-06/B-09/B-02/B-03/E-01/D-01/D-02/L-01/L-03/L-04/J-01 有代码/文档修改 + 复跑证据；不能只改文档。
- P1 至少关闭与“错误 verified”相关的 A-03/A-04/A-05、C-01/C-02、D-03、F-05/F-06；其余 P1 有明确 owner/依赖/复跑命令。
- P2/P3 保持状态与证据一致；未执行项不得写成 DONE。
- 任何“DONE”必须附：`file:line` 或证据文件路径、复跑命令/输出、实际验证的版本（build/sha256）；真实 EDA/实物项另附会话/仪器/日期。
