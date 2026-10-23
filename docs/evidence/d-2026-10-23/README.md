# D 包：真实 EDA 图页进入排版检查（2026-10-23）

## 做了什么

- 新增 `design-hardware/scripts/layout_from_snapshot.py`：把 `eda_exec` 原理图快照转换为
  `sch_layout_check.py` 的输入契约。
- 用 B 包最终快照 `docs/evidence/f1-b-2026-10-22/v5-snapshot-final.json`（21 器件 / 57 线 / 20 端口 / 37 标志）
  生成输入并实际运行检查器。

## 输入覆盖（诚实边界）

| 检查器字段 | 本转换 | 说明 |
|---|---|---|
| `wires` | 已提供（47 条可绘制折线） | 零长度退化导线（10 条，承载端口—引脚连接）被排除；连续重复点已合并 |
| `attachment_points` | 102 个（全部引脚 + 电源标志） | 来自快照实际坐标 |
| `label_anchors` | 20 个（全部网络端口） | 仅锚点，无文本边界 |
| `page_bbox` | [0,0,1170,825] | 来自图页宽高 |
| `components` / `texts` | **空** | 快照不含符号本体矩形与文字边界；检查器据此报告覆盖不足 |
| `title_block` / `module_frames` | **未提供** | `checks_skipped` 明确列出 |

## 实际结果

`docs/evidence/d-2026-10-23/f1-layout-check.json`：

- `status: review_required`
- `counts: {components: 0, texts: 0, wires: 47}`
- `checks_skipped: ["title_block…", "module_frames…"]`
- 发现类别：`dangling_wire_endpoint`（导线端点未落在声明的连接点/端口锚点上，属待核查候选）

**对 dangling 端点的解释**：被排除的 10 条零长度导线正是端口到引脚的同点连接；它们的相邻导线在该点
现在被计为悬空。这是覆盖/转换导致的可解释候选，不是电气缺陷（网表 60 引脚全部连接，见 B 包 golden 网表）。
按检查器契约，重叠/悬空都是「待核查候选」，不能当自动改线指令。

## 未覆盖（不能判排版通过）

- 文字—文字、文字—导线、文字—符号碰撞：缺文字边界。
- 导线穿无关引脚、模块框：缺符号本体矩形/模块框。
- 图签：未提供 title_block 矩形。
- 因此本包只证明「真实图页能进入流程并给出可定位候选」，**不证明 F1 排版无碰撞**；
  排版视觉结论仍以 `v5-layout.png` 人工/AI 目检为准（B 包证据）。

## 下一步

- 获取符号本体与文字边界（GUI 导出或 API）后重跑，关闭 components/texts 覆盖。
- 修复前后各跑一次，解释候选变化（D 验收剩余项）。
