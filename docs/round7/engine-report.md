# 第七轮：确定性设计引擎纵切片报告

日期：2026-10-24。基线代码 `fe950d3`；工作分支 `feat/design-engine-round7`；实现提交 `6468d0f`；隔离 worktree `C:\Users\jlc\work\hds-engine`。
本报告只描述本轮实际写入、实际运行和实际测量的内容；没有执行的项目明确标 `NOT RUN`。

## 1. 本轮完成什么

新增离线、stdlib-only 的 `design-hardware/scripts/design_engine/`：

| 模块 | 内容 | 对应工作包 |
|---|---|---|
| `ir.py` | `design-engine-ir/v1`、身份校验、未知字段保留、重复脚号保留 | A04/A07 |
| `geometry.py` | 矩形/线段/旋转/镜像、显式单位、SVG 文字解析、GDI/字宽表文字度量 | A06/S01 |
| `adapters.py` | easyeda 回读 bundle → IR；容错 JSON；净标签识别 | A05/A07/A08 |
| `audit.py` | 硬/建议规则、覆盖门、pin/net 对账 | S10/A07 |
| `labels.py` | Designator/Name 确定性位置搜索、计划、独立模拟校验、attribute-move 参数文件 | S04/A08 |
| `router.py` | 5-unit 网格正交 A*、障碍、不同网接触验证、0 长度保留 | S05 |
| `pack.py` | 模块刚体货架装箱、图签避让、分页、超大模块 unsolved | S08 |
| `templates.py` | 12 类常用画法、物理脚号绑定、相对候选 | S02/S03 |
| `pcb.py` | 板框/器件/焊盘/走线/过孔/铺铜 IR、DRC 身份、走线连通、pin/pad 对账 | A07/P01/P04/R04/R05 |
| `compare.py` | 电气身份与布局变化分开比较 | A08/S09 |
| `cli.py` | `ingest/audit/plan-labels/verify-plan/route/pack/templates/compare/pcb-*` | A08/U01 |

同时修改：

- `layout_from_snapshot.py`：快照含 `parts[].bbox` / `texts[].bbox` 时输出真实 `components/texts`；缺失时写 `coverage`，不再用空数组掩盖。
- `sch_layout_check.py`：读取 `coverage`；覆盖不足时返回 `incomplete`，不再把“没几何”报成 `no_candidates`。
- `SKILL.md`：增加一行“确定性设计引擎”路由；不把 49 个工作包塞进主入口。
- `references/design-engine.md`：输入契约、IR、覆盖、命令、边界。

## 2. 冻结基线的实测数字

证据：[docs/evidence/round7-baseline-2026-10-24](../evidence/round7-baseline-2026-10-24/manifest.json)

原理图：

- 26 个 part、65 段导线、14 个网络、65 条连接、31 个 netflag/netport、34 个净标签、96 个布局属性。
- 文字 bbox：26 个位号来自原生 SDK，70 个来自 Windows GDI 字体度量；覆盖 `complete`。
- 原生检查：`sch check` 5 条（1 marker-overlap、1 out-of-sheet、2 designator-wire-overlap、1 missing-partition）；`sch drc` 0；`layout-score` 84.2（proximity 37.7）。

PCB：

- 26 个器件、71 个焊盘、123 条走线、39 个过孔、2 个 GND 铺铜。
- 原生 DRC 18 条：16 Clearance + 2 Connection；DFM 摘要 40 项。
- `pcb-drc.json` 中间夹了一行 CLI 文本；引擎记录并删除该行后解析，未把文件当作完整 JSON。

## 3. 原理图审计与标签计划

命令与输出：[docs/evidence/round7-engine](../evidence/round7-engine/manifest.json)。

- 审计：`blocked`，10 个硬问题、7 个建议。硬问题包括 3 个文字重叠、2 个文字压器件、4 个导线穿文字、1 个越页；建议包括 1 个网旗重叠、4 个净标签互相重叠、1 个 off-grid、1 个未分区。
- 没有 `dangling_wire_endpoint`：识别出 34 个导线自有 `Name` 属性（净标签）后，原先 30+ 个“悬空”误报消失。
- pin/net 对账：65 条连接全部对应；无 `pin_net_mismatch`、无 NC 冲突。
- 计划：4 个 Designator/Name 移动，模拟后硬问题 10 → 4；`verify_plan` 为 `match`，所有前置身份/位置检查通过。
- 未规划：2 个属性在 40 unit 内无合法位置；净标签/旗形、sheet Name 属于导线/图签，不移动。
- `eda_apply`：**NOT RUN**。生成了 4 个 `sch attribute-move --from` 参数文件，但没有对真实工程执行；因此不能声称图面已改善。

## 4. 局部正交连线

- 对 51 对同网相邻引脚做候选路由：47 条 `routed`，4 条 `no_solution`。
- 独立验证：22 条 `valid`，29 条被拒绝（仍穿器件/文字或接触不同网导线）。这说明网格障碍模型不够细，候选不能直接应用。
- 0 长度连接返回 `zero_length` 并保留，不转成可见线。
- 真实应用/编辑器结点检查：**NOT RUN**。

## 5. 模块装箱

- 用 26 个 L1 诊断组作为候选，`--allow-groups` 显式允许，装箱为 1 页、无重叠。
- 这些组不是声明功能区；结果标记 `allow_diagnostic_groups: true`，不能当作“已完成分区”。
- 真实应用：**NOT RUN**。

## 6. PCB 审计

- 板框 bbox 包含检查：J1 本体外伸 44 mil，列为 `advisory`（连接器合法外伸）；无焊盘中心越框。
- 同层器件本体重叠：0。
- pin/pad 逐脚对账：`match`；组合脚名按原样比较，不拆分。
- 走线/过孔连通：只有 `+5V` 报告 2 个断开焊盘组，与原生 DRC 的 2 条 Connection Error 一致；GND 有铺铜，标记 `not_checked`，没有把填充简化成实心平面。
- 原生 DRC 18 条按 `rule/objType/net/layer/x/y/objs` 逐条保留；状态 `blocked`。
- 电气/视觉/制造/实物：全部未验证。

## 6.1 扩展包（P02–P08、M01–M05、Q01/Q03、U03）

- **P02 约束**：`constraints.py` 编译 hard/preferred/unknown，支持 mm/mil/in/V/A、单位显式、硬冲突 `unsolvable`；本页 5 hard + 1 preferred + 2 unknown，状态 `incomplete`（未知不冒充 false）。
- **P03 关键回路**：`critical.py` 用真实焊盘坐标得到 C2/C3/C4/C5 与 U1 的去耦距离 **442.2 / 790.8 / 1698.9 / 1432.8 mil**，与原生 DFM 摘要逐项一致；D3 距 J1 GND 212.7 mil。换流回路/Kelvin/参考面未检查。
- **P05 布局候选**：`placement.py` 生成 reference + 3 force + critical-snap 共 5 个候选；全部硬合法；force-2 选中，HPWL 25,078.7 → 20,779.6 mil（-17.7%），拥塞 overflow 2186 → 1756；关键回路仍 5 条，没有把“候选”说成已改善。
- **P06 可布性**：`routability.py` 拥塞 max 6、overflow 76、不同网包围盒重叠 42、最近异网焊盘 28 mil；实际布通率 `NOT RUN`。
- **P07 复用**：`reuse.py` 要求封装/脚表一致才复用，只移动目标模块；无真实多路实例。
- **P08 丝印**：`silk.py` 找出 2 处压焊盘（C5/R12.1、R14/R16.2）和 R1/R2 侧向，与原生 DFM 摘要一致；给出 2 条位置建议，未应用。
- **M01 选型**：真实 BOM 21 行/26 件，MPN/C号/封装齐全；只做精确 MPN+封装匹配，库存/价格/SMT `NOT CHECKED`。
- **M02 制造包**：`manufacturing.py` 检查 Gerber/drill/BOM/CPL 角色、空文件、位号集合、单位、manifest 哈希；真实项目没有 Gerber/drill，状态 `BLOCKED`，未冒充可制造。
- **M04 变体**：DNP/销售变体/替代料影响闭包；封装/脚数变化必须复核。
- **M05 装配**：26 行 CPL、全部顶层；J1 原点与焊盘质心差 70.7 mil、Q1 13.1、U1 10.2；BOM 一致；generic JSON 标 `IHMB NOT VERIFIED`。
- **Q01 基准**：12 个合成几何用例全部复现声明候选；真实几何只有温度报警板一个，F1 是真实网表但无 bbox，不能算几何金样。
- **Q03 故障**：噪声 JSON、截断、缺几何、重复位号、过期计划、身份变化、证据哈希均有用例；保存重开/超时/并发仍 `NOT RUN`。
- **U03 状态**：`state.py` 记录阶段、最佳候选、未决项、下一条动作、预算与证据哈希；没有真机中断恢复演练。

## 6.2 真实 EDA 应用（隔离副本）

详见 [a08-real-apply.md](a08-real-apply.md)。

- 将 `before-round7.epro2`（SHA-256 `f5f1…`）导入独立项目 `engine-verify-round7-imported`（UUID `64ab79c4…`），页 UUID 保持 `6a8364999a809cb4`。
- 3 批共 9 个不同 Name/Designator 属性移动；每次 `moved/verified/preserved=true`。
- 引擎 audit：11 hard → **1 hard**（剩余 sheet Name 越页）；原生 `sch check` 5 → **3 warnings**；原生 DRC **0**；原生 layout-score **84.2 → 86.7**（frame-fit 76 → 100）。
- 身份 compare：`identity.match=true`，`changed_pin_nets=0`；保存后重开回读与 after3 一致（moved attrs 0）。
- 剩余 3 条原生警告都不在 Name/Designator 移动范围：GND 旗形重叠、sheet Name 越页、未画分区框。
- 未做：器件/导线/旗形移动、PCB 写入、人工盲审、断电重启、制造/样机。

## 7. 测试与可复现性

- `python -m unittest discover -s tests` → **658 tests, OK**（基线 589；新增 69）。
- 新增测试覆盖：单位/旋转/镜像、IR 身份与重复脚号、真实 bundle 结构、pin/net 对账、审计规则、标签计划与校验、路由有解/无解/不同网、装箱/超大模块、12 模板绑定、PCB 真实 bundle 与合成反例、CLI 退出码、容错 JSON；另有约束冲突、关键回路、布局候选、可布性、丝印、CPL、制造包、Gerber 层、选型、变体、复用、基准、状态与故障注入。
- 引擎证据 manifest 记录 62 个文件的 SHA-256；真实应用证据另见 [docs/evidence/round7-apply/manifest.json](../evidence/round7-apply/manifest.json)（195 个文件）。

## 8. 没有做到的部分

- 没有在真实 EDA 中应用器件/布线/装箱；只应用了 9 个 Name/Designator 移动。没有人工审图、断电重启、制造/样机。
- 没有实现 S06（ELK）、S07（libavoid）、R01–R03/R06、M03/M06、H01–H04、U02；P02/P03/P05/P06/P07/P08、M01/M02/M04/M05 只有离线子集。
- S05 只是候选生成器：29/51 条被自己的验证器拒绝，尚不能作为可应用布线。
- S09 只覆盖“属性/标签局部修复”，没有器件/导线簇修复；S08 的模块来源是诊断组，不是已声明功能区。
- P05 布局候选只证明离线指标变化，未证明可布通或可制造；关键回路仍 5 条，没有解决。
- 铺铜连通、原生网表 diff、ERC、DFM、真实制造文件、实物功能均未验证。
- 没有改动用户原工程 `test`；冻结对象是 `temp-alarm-r7-scratch` 副本。

## 9. 下一步

1. 在一个**独占** scratch 副本上执行 4 个 `attribute-move`，重新回读、重新 audit、导出 PNG，确认硬问题 10→≤4 且网表身份不变。
2. 用 `layout_from_snapshot.py` 接入带 `parts[].bbox` 的真实快照，验证 `sch_layout_check.py` 的 `coverage` 路径；本轮的 eda_exec 快照读取尚未扩展 bbox 字段。
3. 针对 S05 的 29 条拒绝样本调障碍模型（逐段验证、端点法向引出），或明确保留为候选并停止声称可用。
4. 用真实声明功能区替换诊断组，再评估 S08；用原生网表 diff 复核纯排版。
5. 如果要继续 PCB，先做 P04 的真实旋转轮廓/庭院/层规则，再做 R01 DSN/SES。

## 10. 并发说明

本轮开始时另一个会话已在 `hds-round7` 与 `temp-alarm-r7-scratch` 上做原理图重排。发现后本会话立即把自己的文件迁到独立 worktree `hds-engine`，未再对共享 EDA 工程写入；只读探测与冻结证据复制不改变对方画布。两个分支的成果不应直接互相合并，需先比较再集成。
