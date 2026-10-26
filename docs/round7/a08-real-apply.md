# A08：真实 EDA 标签修复闭环（隔离副本）

日期：2026-10-24。目标：在**独立导入副本**上执行 Designator/Name 移动，验证真实保存、重开、身份保持与图面改善。没有写用户的 `temp-alarm-r7-scratch` 或原工程 `test`。

## 1. 隔离副本

| 项 | 值 |
|---|---|
| 源归档 | `before-round7.epro2`，364,810 bytes，SHA-256 `f5f1b33fdd10555c12ee5647864619fabfb1669ad5734a0fff4daa0541bc45e9` |
| 导入项目 | `engine-verify-round7-imported` |
| 项目 UUID | `64ab79c43f24454e8066801ade20d42f` |
| 页 UUID | `6a8364999a809cb4`（导入后保持不变） |
| PCB UUID | `6cde899fca734109` |
| 导入结果 | `created:true`、`verified:true`、`contentVerified:false`；导入后回读 26 器件/65 导线/14 网，与冻结基线一致 |
| 宿主 | EasyEDA Pro 4.1.78 / Connector 1.14.0 / easyeda-agent 1.14.0 |
| 隔离窗口 | 独立 connector window `fdcf9c6f-…`；另一个会话的窗口未被使用 |

## 2. 改前实测

- 引擎 audit：**11 hard / 7 advisory**；TEXT/TITLE_BLOCK/WIRE 问题：
  - 3 文字重叠、2 文字压器件、4 导线穿文字、1 标题文字压图签、1 sheet Name 越页。
- 原生 `sch check`：**5 warnings**（GND marker-overlap、sheet Name out-of-sheet、2 designator-wire-overlap、missing-partition）。
- 原生 `sch drc`：**0**。
- 原生 `layout-score`：**84.2 / good**（frame-fit 76，proximity 38）。

## 3. 执行

用 `plan-labels` 生成 **10 个移动操作**（9 个不同属性；J1.Name 分两批微调），全部通过 `sch attribute-move` 的完整 `expected` 前置检查：

| 批次 | 属性 | 移动 |
|---|---|---|
| 1 | RV1.Designator、Q1.Designator、D6.Name | (850,545)→(830,545)、(930,300)→(930,305)、(990,220)→(990,215) |
| 2 | Q1.Name、D5.Name、D4.Name、J1.Name | Q1.Name→(930,380)、D5.Name→(990,200)、D4.Name→(820,275)、J1.Name→(495,440) |
| 3 | J1.Name、D4.Designator、D6.Designator | J1.Name→(500,440)、D4.Designator→(880,245)、D6.Designator→(990,255) |

每个操作返回 `moved:true`、`verified:true`、`preserved:true`、`partial:false`，项目/文档身份在操作前后一致。随后 `sch save` → `doc reload` → 重新回读。

## 4. 改后实测

| 指标 | 改前 | 改后 |
|---|---|---|
| 引擎 audit hard | 11 | **1** |
| 引擎 audit advisory | 7 | 7 |
| 原生 sch check | 5 warnings | **3 warnings** |
| 原生 sch drc | 0 | **0** |
| 原生 layout-score | 84.2 | **86.7**（frame-fit 76 → 100） |
| 身份 compare | — | **identity match**；changed_pin_nets 0 |
| 保存重开 | — | **match**（after3 vs 重开回读，moved attrs 0） |
| 改动属性 | — | 9 个不同属性（10 次操作） |

剩余 3 条原生警告：

1. `marker-overlap`：两个 GND netflag 视觉重叠；属于旗形/导线，不在 Name/Designator 移动范围。
2. `out-of-sheet`：sheet 的可见属性 `Name` 越页；属于 sheet 属性，不是器件属性。
3. `missing-partition`：26 器件单页未画功能区框；属于 S08/分区工作，不是标签移动。

## 5. 证据

目录：[docs/evidence/round7-apply](../evidence/round7-apply)

- `before/`、`after/`、`after2/`、`after3/`：真实回读、SVG；`after3/sch-after3.png` 为最终导出图。
- `label-plan.json`、`label-plan2.json`、`label-plan3.json` 与对应 `moves*/`：计划与 `sch attribute-move` 参数。
- `apply*-move*.json`：每次移动的 before/after/verified 回执。
- `save*.json`、`reload*.json`：保存与重开。
- `native-after*/sch-check.json`、`sch-drc.json`、`sch-layout-lint.json`、`sch-layout-score.txt`。
- `compare*.json`：改前/改后身份与布局差异。

## 6. 边界

- 只改 Name/Designator 位置；没有移动器件、导线、netflag 或 sheet 属性，没有重排 PCB。
- 没有人工硬件工程师盲审；Agent 检查了 after3 PNG（文字不再重叠，底部仍可见越页的 `Name`），这不等于人工验收。
- 没有断电/重启后的恢复演练；没有制造、样机、热/EMC 实测。
- 导入副本仍保留在用户工程列表中，名称 `engine-verify-round7-imported`，可人工复核或删除。
