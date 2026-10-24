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

## 7. 测试与可复现性

- `python -m unittest discover -s tests` → **628 tests, OK**（基线 589；新增 39）。
- 新增测试覆盖：单位/旋转/镜像、IR 身份与重复脚号、真实 bundle 结构、pin/net 对账、审计规则、标签计划与校验、路由有解/无解/不同网、装箱/超大模块、12 模板绑定、PCB 真实 bundle 与合成反例、CLI 退出码、容错 JSON。
- 证据 manifest 记录 22 个文件的 SHA-256；基线 bundle 另有 manifest。

## 8. 没有做到的部分

- 没有在真实 EDA 中应用任何移动/布线/装箱；没有保存重开、没有 after 导图、没有人工审图。
- 没有实现 S06（ELK）、S07（libavoid）、P02/P03/P05/P06/P07/P08、R01–R03/R06、M01–M06、H01–H04、U02。
- S05 只是候选生成器：29/51 条被自己的验证器拒绝，尚不能作为可应用布线。
- S09 只覆盖“属性/标签局部修复”，没有器件/导线簇修复；S08 的模块来源是诊断组，不是已声明功能区。
- 铺铜连通、原生网表 diff、ERC、DFM、制造文件、实物功能均未验证。
- 没有改动用户原工程 `test`；冻结对象是 `temp-alarm-r7-scratch` 副本。

## 9. 下一步

1. 在一个**独占** scratch 副本上执行 4 个 `attribute-move`，重新回读、重新 audit、导出 PNG，确认硬问题 10→≤4 且网表身份不变。
2. 用 `layout_from_snapshot.py` 接入带 `parts[].bbox` 的真实快照，验证 `sch_layout_check.py` 的 `coverage` 路径；本轮的 eda_exec 快照读取尚未扩展 bbox 字段。
3. 针对 S05 的 29 条拒绝样本调障碍模型（逐段验证、端点法向引出），或明确保留为候选并停止声称可用。
4. 用真实声明功能区替换诊断组，再评估 S08；用原生网表 diff 复核纯排版。
5. 如果要继续 PCB，先做 P04 的真实旋转轮廓/庭院/层规则，再做 R01 DSN/SES。

## 10. 并发说明

本轮开始时另一个会话已在 `hds-round7` 与 `temp-alarm-r7-scratch` 上做原理图重排。发现后本会话立即把自己的文件迁到独立 worktree `hds-engine`，未再对共享 EDA 工程写入；只读探测与冻结证据复制不改变对方画布。两个分支的成果不应直接互相合并，需先比较再集成。
