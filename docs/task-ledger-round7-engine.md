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
| A08 | PARTIAL | `labels.py`、`compare.py`、`cli.py`、move 参数文件 | 未真机 apply/回读/重开 |
| S01 | PARTIAL | SVG 文字 + GDI/字宽表 + 原生位号 bbox | 缓存未按编辑器版本区分；非 Windows 用估宽 |
| S02 | DONE | `templates.py` 12 类 + 物理脚绑定测试 | 无真实实例验证 |
| S03 | PARTIAL | `instantiate_plan` 相对位置/重叠检查 | 未真机应用；未处理引脚方向逃逸 |
| S04 | PARTIAL | 4 个 Designator/Name 移动计划、模拟 10→4 | 只支持 Name/Designator；净标签/旗形不移动 |
| S05 | PARTIAL | `router.py`、`route-sweep.json` | 47 routed / 4 no_solution；仅 22/51 通过独立验证 |
| S06 | NOT RUN | — | — |
| S07 | NOT RUN | — | — |
| S08 | PARTIAL | `pack.py`、`pack-candidate.json` | 用 L1 诊断组而非声明功能区；未应用 |
| S09 | PARTIAL | 标签局部修复 + `compare.py` | 无器件/导线簇修复；无视觉差分 |
| S10 | DONE | `audit.py` 规则/覆盖 | 电气/视觉已明确不验证 |
| P01 | PARTIAL | PCB 板框 bbox、焊盘中心越框、本体外伸 | 无凹板框/内孔/高度/插拔空间 |
| P02 | NOT RUN | — | — |
| P03 | NOT RUN | — | — |
| P04 | PARTIAL | 同层器件本体重叠检查 | 无旋转轮廓/庭院/钻孔/异侧规则 |
| P05 | NOT RUN | — | — |
| P06 | NOT RUN | — | — |
| P07 | NOT RUN | — | — |
| P08 | NOT RUN | — | — |
| R01 | NOT RUN | — | — |
| R02 | NOT RUN | — | — |
| R03 | NOT RUN | — | — |
| R04 | PARTIAL | 18 条原生 DRC 身份归一 | 无修复闭环/豁免/未覆盖项比较 |
| R05 | PARTIAL | 走线/过孔连通；+5V 2 组与原生一致 | 铺铜/热焊盘/孤岛 `not_checked` |
| R06 | NOT RUN | — | — |
| M01–M06 | NOT RUN | — | — |
| Q01 | PARTIAL | 1 个真实基线 + 合成反例 | 未做 12 电路基准 |
| Q02 | PARTIAL | `compare.py` 身份/布局比较 | 无多算法/消融预算 |
| Q03 | PARTIAL | 证据 manifest/前后 IR 能力 | 无故障注入/重开回归 |
| Q04 | NOT RUN | — | 无人工盲审 |
| U01 | PARTIAL | CLI 入口 | 无新手一句话入口 |
| U02 | NOT RUN | — | — |
| U03 | PARTIAL | `manifest.json` + 交接 | 无持久化任务状态/恢复点 |
| H01–H04 | NOT RUN | — | — |

## 2. 本轮实际运行

```text
python -m unittest discover -s tests
Ran 628 tests in 22.9s — OK
```

真实数据：

- 原理图 IR：26 part / 65 wire / 14 net / 65 connection / 31 flag-port / 34 net-label / 96 layout attributes。
- 审计：`blocked`，10 hard / 7 advisory；覆盖 `complete`。
- 标签计划：4 个移动，模拟 10 → 4 hard；`verify_plan` match。
- 路由扫查：51 对同网引脚，47 routed / 4 no_solution；22 通过验证，29 被拒绝。
- 装箱：26 个诊断组 → 1 页，无重叠；`allow_diagnostic_groups: true`。
- PCB：26 器件 / 71 焊盘 / 123 走线 / 39 过孔 / 2 铺铜；DRC 18（16+2）；+5V 2 个断开组；GND 铺铜 `not_checked`。

所有产物在 [docs/evidence/round7-engine](../evidence/round7-engine/manifest.json)；manifest 记录 22 个文件的 SHA-256。

## 3. 明确未执行

- 真实 EDA 应用：0 次；保存重开、after 导图、人工审图：`NOT RUN`。
- 原生网表 diff（纯排版最终门禁）：`NOT RUN`。
- 铺铜连通、ERC、DFM、制造文件、样机：`NOT RUN`。
- S06/S07、P02/P03/P05/P06/P07/P08、R01–R03/R06、M01–M06、H01–H04、U02：`NOT RUN`。
- 12 电路基准、多算法 A/B、故障注入、人工盲审：`NOT RUN`。

## 4. 下一条具体操作

1. 在独占 scratch 副本执行 4 个 `attribute-move`，重新回读、audit、导图；若 10→≤4 且身份不变，再把该路径写入 `a08` 证据。
2. 扩展 eda_exec 快照 `parts[].bbox`/可见属性 bbox（需要真机验证），把 `layout_from_snapshot` 的 `coverage` 从“bundle 路径”提升到“执行器路径”。
3. 把 S05 的 29 条拒绝样本作为回归集，先修端点法向引出与逐段验证，再谈可用布线。
4. 用真实声明功能区替换诊断组后复跑 S08；补 S09 的器件/导线簇修复。
