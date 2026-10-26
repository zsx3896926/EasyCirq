# 第七轮工作包台账（引擎纵切片）

分支：`feat/design-engine-round7`；worktree：`C:\Users\jlc\work\hds-engine`；基线：`fe950d3`。
状态词：`DONE`（有代码/测试/证据）、`PARTIAL`（有可运行子集，验收未全过）、`NOT RUN`（未开始）。
“真实 EDA 应用”单列；离线通过不等于真机通过。

## 1. 汇总

| 包 | 状态 | 产物/证据 | 未过项 |
|---|---|---|---|
| A01 | DONE | [a01-baseline-freeze.md](round7/a01-baseline-freeze.md)、[bundle](../evidence/round7-baseline-2026-10-24/manifest.json) | 未做恢复演练；未改原工程 |
| A02 | DONE | [a02-capability-matrix.md](round7/a02-capability-matrix.md) | 仅只读探测；写命令未实测 |
| A03 | DONE | [a03-source-license.md](round7/a03-source-license.md) | 无第三方代码采用，故无 NOTICE 变更 |
| A04 | DONE | `design_engine/ir.py`、`tests/test_design_engine.py` | 无 |
| A05 | PARTIAL | `adapters.py`、`layout_from_snapshot.py`、`sch_layout_check.py` | eda_exec 快照未扩展 `parts[].bbox`；只用冻结 bundle |
| A06 | DONE | `geometry.py` + 变换/单位测试 | 任意角文本 AABB 只有合成测试 |
| A07 | PARTIAL | `audit.reconcile_pins`、`pcb._reconcile_pin_pads` | 组合脚名按原样比较；未拆壳脚/多单元件 |
| A08 | PARTIAL | [真实应用](round7/a08-real-apply.md)；`labels.py`、`compare.py`、`cli.py`、move 参数 | 已真机 9 移动/保存/重开；无算法切换/超时真机
| S01 | PARTIAL | SVG 文字 + GDI/字宽表 + 原生位号 bbox | 缓存未按编辑器版本区分；非 Windows 用估宽 |
| S02 | DONE | `templates.py` 12 类 + 物理脚绑定测试 | 无真实实例验证 |
| S03 | PARTIAL | `instantiate_plan` 相对位置/重叠检查 | 未真机应用；未处理引脚方向逃逸 |
| S04 | PARTIAL | 真实 9 个 Designator/Name 移动；audit 11→1；原生 check 5→3 | 只支持 Name/Designator；净标签/旗形不移动 |
| S05 | PARTIAL | `router.py`、`route-sweep.json` | 47 routed / 4 no_solution；仅 22/51 通过独立验证 |
| S06 | NOT RUN | — | — |
| S07 | NOT RUN | — | — |
| S08 | PARTIAL | `pack.py`、`pack-candidate.json` | 用 L1 诊断组而非声明功能区；未应用 |
| S09 | PARTIAL | 真实标签局部修复 + `compare.py`；after3 PNG 已检视 | 无器件/导线簇修复；无人工视觉差分 |
| S10 | DONE | `audit.py` 规则/覆盖 | 电气/视觉已明确不验证 |
| P01 | PARTIAL | PCB 板框 bbox、焊盘中心越框、本体外伸 | 无凹板框/内孔/高度/插拔空间 |
| P02 | DONE（离线） | `constraints.py`：hard/preferred/unknown、单位、冲突、evaluate | 无真机约束写入 |
| P03 | PARTIAL | `critical.py`：4 个去耦距离与原生 DFM 数值一致；保护/晶振/反馈距离 | 无换流回路/Kelvin/参考面 |
| P04 | PARTIAL | 同层器件本体重叠检查 | 无旋转轮廓/庭院/钻孔/异侧规则 |
| P05 | PARTIAL | `placement.py`：5 候选、硬合法、HPWL/拥塞/整齐度；force-2 HPWL -17.7% | 关键回路仍 5 条；无 PCB 移动执行器 |
| P06 | PARTIAL | `routability.py`：拥塞栅格、最近异网焊盘、异网包围盒；`route_rate NOT RUN` | 无实际布通率 |
| P07 | PARTIAL | `reuse.py`：封装/脚表一致才复用；只移动目标模块 | 无真实多路实例 |
| P08 | PARTIAL | `silk.py`：2 处压焊盘、R1/R2 侧向与原生 DFM 一致；2 条位置建议 | 未应用 |
| R01 | NOT RUN | — | — |
| R02 | NOT RUN | — | — |
| R03 | NOT RUN | — | — |
| R04 | PARTIAL | 18 条原生 DRC 身份归一 | 无修复闭环/豁免/未覆盖项比较 |
| R05 | PARTIAL | 走线/过孔连通；+5V 2 组与原生一致 | 铺铜/热焊盘/孤岛 `not_checked` |
| R06 | NOT RUN | — | — |
| M01 | PARTIAL | `sourcing.py`：真实 BOM 21 行/26 件，MPN/C号/封装齐全；精确候选匹配 | 库存/价格/SMT 未查 |
| M02 | PARTIAL | `manufacturing.py`：角色/空文件/位号集合/单位/manifest 哈希 | 无真实 Gerber/drill 包 |
| M03 | PARTIAL | `gerber.py`：层函数/单位/EOF/钻孔头/孔数检查 | 无真实制造文件；未渲染/重开 |
| M04 | PARTIAL | `variants.py`：DNP/变体/替代影响闭包 | 无真实销售变体 |
| M05 | PARTIAL | `assembly.py`：26 行 CPL、J1 70.7 mil 质心差、BOM 一致；generic JSON 候选 | IHMB 兼容性未验证 |
| M06 | NOT RUN | — | — |
| Q01 | PARTIAL | `benchmarks.py` 12/12 合成基准；1 个真实几何 + 1 个真实网表 | 未达两个独立真实几何金样 |
| Q02 | PARTIAL | A/B/消融表：原生 5 警告、引擎 10 hard、标签 10→4、placement 5 候选、router 22/51 | 无多算法同预算完整 A/B |
| Q03 | PARTIAL | 噪声/截断/缺几何/重复位号/过期计划/身份变化/证据哈希测试；真实保存/重开 match | 超时/页切换/人工并发：NOT RUN |
| Q04 | NOT RUN | — | 无人工盲审 |
| U01 | PARTIAL | CLI 入口 | 无新手一句话入口 |
| U02 | NOT RUN | — | — |
| U03 | PARTIAL | `state.py`：阶段/最佳候选/未决项/下一条/证据哈希 | 无真机中断恢复 |
| H01–H04 | NOT RUN | — | — |

## 2. 本轮实际运行

```text
python -m unittest discover -s tests
Ran 658 tests in 22.9s — OK
```

真实数据：

- 原理图 IR：26 part / 65 wire / 14 net / 65 connection / 31 flag-port / 34 net-label / 96 layout attributes。
- 冻结基线 audit：10 hard / 7 advisory；导入隔离副本 live before：11 hard / 7 advisory（标题栏高度不同）。
- 标签计划：冻结基线 4 个移动，模拟 10 → 4 hard；真实副本 3 批共 9 个不同属性移动。
- **真实 EDA 应用**：隔离项目 `engine-verify-round7-imported`（UUID `64ab79c4…`）；audit 11 → **1 hard**；原生 check 5 → **3 warnings**；原生 DRC **0**；layout-score **84.2 → 86.7**；identity match；保存重开 match。
- 路由扫查：51 对同网引脚，47 routed / 4 no_solution；22 通过验证，29 被拒绝。
- 装箱：26 个诊断组 → 1 页，无重叠；`allow_diagnostic_groups: true`。
- PCB：26 器件 / 71 焊盘 / 123 走线 / 39 过孔 / 2 铺铜；DRC 18（16+2）；+5V 2 个断开组；GND 铺铜 `not_checked`。

所有产物在 [docs/evidence/round7-engine](../evidence/round7-engine/manifest.json)；manifest 记录 62 个文件的 SHA-256。

## 3. 明确未执行

- 真实 EDA 应用：9 个 Name/Designator 移动（3 批），保存重开与 after3 导图已完成；器件/导线/旗形移动与 PCB 写入：`NOT RUN`。
- 人工盲审、断电重启、制造/样机：`NOT RUN`。
- 原生网表 diff（纯排版最终门禁）：`NOT RUN`；本轮用导出 pin/net 的 `compare` 做辅助身份核验。
- 铺铜连通、ERC、DFM、制造文件、样机：`NOT RUN`。
- S06/S07、P02/P03/P05/P06/P07/P08、R01–R03/R06、M01–M06、H01–H04、U02：`NOT RUN`。
- 12 电路基准、多算法 A/B、故障注入、人工盲审：`NOT RUN`。

## 4. 下一条具体操作

1. 在独占 scratch 副本执行 4 个 `attribute-move`，重新回读、audit、导图；若 10→≤4 且身份不变，再把该路径写入 `a08` 证据。
2. 扩展 eda_exec 快照 `parts[].bbox`/可见属性 bbox（需要真机验证），把 `layout_from_snapshot` 的 `coverage` 从“bundle 路径”提升到“执行器路径”。
3. 把 S05 的 29 条拒绝样本作为回归集，先修端点法向引出与逐段验证，再谈可用布线。
4. 用真实声明功能区替换诊断组后复跑 S08；补 S09 的器件/导线簇修复。
