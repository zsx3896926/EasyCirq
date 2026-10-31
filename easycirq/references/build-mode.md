# 施工模式（Build Mode）—— 长跑任务的工程契约

> 适用：用户要求"把板子做出来 / 改完 / 跑通 / 按这个方案做"，或任务需要真机 EDA 写入、
> 多轮布局迭代、批量验证。**咨询模式（R0–R12）仍用于问答/选型/快速检查**；
> 判定为施工模式后，本节优先于 R1–R12 中的预算条款（R4/R5/R8 的诚实性要求不变）。

## B0 判定与开局

- 判据（任一）：用户说"做/改/跑通/落地"；需要写 EDA；需要 ≥3 轮迭代；需要产出图纸/PNG/BOM 等交付物。
- 开局必须先声明三件事（可见文字）：
  1. **目标与验收物**（如"两页原理图 + 评审通过 + 导出 PNG"）；
  2. **模式**（施工模式）与**当前阶段**（规划 / 写入 / 验证 / 交付）；
  3. **预算**：每阶段工具调用上限、单次写入批量上限、预计检查点数量。
- 用户明确说"先别动/只分析"时按咨询模式处理，不进入写入阶段。

## B1 单一设计模型（IR）优先

校验、规划、写入必须共享**同一个模型**（parts / nets / ports / decoupling / pages / fixes）。
禁止"快照、计划、页面"三套事实来源各自判断——这是返工与自相矛盾的根源。
参考实现：`hds-verifier/tools/schematic_ir.py`（本机存在该仓库时）。

## B2 可读性在布局期解决，不做事后返工

规划阶段必须通过可读性约束（缺一不可）：

| 规则 | 要求 |
|---|---|
| 网络命名 | 禁内部后缀（`_L0`、`_L3B_AU`）、禁 `NET12` 类自动名、禁空格 |
| 去耦就近 | IC 电源轨的电容在规划坐标下 ≤120 单位（优先贴同一子模块） |
| 信号流 | 列序固定 `input → conversion → core → interface`，输入在左 |
| 测试点 | 每个 TP 必须有标注（信号 + 预期电平） |
| 标题栏 | 图纸名 / 设计者 / 版本 / 日期 / 页号 必填 |
| 分组 | 同一功能模块的卡片不跨页；同类器件对齐成列 |
| 位号 | 同一族位号在块内连续 |

参考实现：`hds-verifier/tools/layout_policy.py`、`readability.py`（R31–R36）。

## B3 标签通道与分页

- 标签是页面里"尺寸不可选"的对象，布局必须为它预留通道：
  `每侧通道 = 桩线 20 + 该侧最宽标签宽`；同侧引脚间距 < 标签高时按 **shelf 分层**（offset = 20 + N×(标签宽+6)）；
- 卡片尺寸 = `union(器件, 标签) + 2`，标签出框在几何上不可能；
- 分页：同模块不跨页、页负载均衡（按面积装入最轻页）、两列平衡、行满换行/换页。

参考实现：`hds-verifier/tools/channel_layout.py`、`stub_planner.py`；
方法文档：`docs/method/label-channel-layout.md`。

## B4 EDA 写入纪律（硬约束）

**会话绑定（先于一切写入）**：写入前必须绑定"恰好一个窗口打开目标工程"，
绑定落盘 `session.json`；之后所有写命令只用绑定里的 windowId。
多窗口、未绑定、context.projectName 不符 → **拒绝开始**。
契约与事故链见 `hds-verifier/docs/method/eda-session-contract.md`。


1. **写前**：verify（计划器件/引脚 vs 页面实际，缺件立刻停）+ preflight（桩线越界/零长度拒绝）+ 清理 `sch check` 报出的零长度线；
2. **批量**：每批 ≤10 次写，批间 `doc reload` + `daemon health`；
3. **失败分级**：`ok / geometry / plan / effect / degraded`；`plan` 类永不重试；
4. **degraded**：立即停，不重试；记录断点后请用户重启 EasyEDA，或用 journal 续跑；
5. **断点续跑**：每步写 JSONL journal，中断后只补未完成项；
6. **禁止**：在 degraded 下全量重试；未清理坏线就继续写；未分组核对器件总数就开写。

参考实现：`hds-verifier/tools/apply_engine.py`；
文档：`docs/method/eda-load-discipline.md`。

## B3.5 落盘纪律

每批写后必须 `doc reload`（真正写盘）并**回读校验**：器件数 / 网络成员数与计划一致，
一致才把该批记入 journal 为 committed；不一致则本批不推进。重启后页面为空时，
按 journal + 计划重放缺口，不从零开始。

## B5 验证闭环（缺一标 NOT RUN）

```
ace_snapshot → ace_review(30 规则) → net_integrity → readability(R31–R36)
            → sch check（零长度/悬浮件） → 导出 PNG → 与规划预览逐页对比
```

- 每项给出数字（errors / warnings / dead nets / out-of-frame / overlaps）；
- 预览与实机不一致时，逐条列出差异（坐标、标签、框），不要只说"基本一致"。

## B6 度量资产化

禁止魔法数。所有间距/尺寸来自实测资产：`block-envelopes.json`、`text-metrics.json`、
`pin-geometry`（在线抓取）。参数改动必须写进 plan 并留痕。

## B7 交付物规范

```
deliverables/
  <board>/snapshot.json / review.json / net-audit.json
  <board>/plan.json / ir.json / journal.jsonl
  <board>/preview.png / live.png / compare.png
  README.md   （每块的阶段、数字、未完成项、下一步）
```

- 每次交付前更新 scoreboard（已完成 / 部分 / 未做 / NOT RUN）；
- 中间态页面（未连完、实验性重放）必须清空或标注"草稿"，不与交付物混放。

## B8 事故档案（反模式，必须避免）

| 症状 | 真因 | 禁止做法 | 正确做法 |
|---|---|---|---|
| 65 次连线全失败 → degraded → 雪崩 | 分组漏 3 个器件，失败率超阈值 | 继续全量重试 | 写前 verify 器件总数；分批 + 断点 |
| 几何校验拒连（`SCHEMATIC_GEOMETRY_INVALID`） | 同侧标签互相压（引脚间距 10 < 标签高 12） | 在 EDA 上换方向反复试 | 布局期通道预留 + shelf 分层 |
| 清空重建后又乱 | 布局未预留标签通道 | 手工塞器件调位置 | 通道布局 + union 卡片 |
| 预览与实机不一致 | 规划坐标与写入批次脱节 | 只出预览就宣称完成 | 逐页 PNG 对比 + 差异清单 |
| 位号/网络反复"修不好" | 三个真相源 | 校验看快照、修改变计划 | 统一 IR，先规范化再校验 |

## B9 阶段汇报

每个阶段结束必须给：**做了什么（含数字）、当前状态、阻塞项、下一步**。禁止长时间无输出。

## B10 Skill 自身的 smoke 用例（升级后自测）

1. "给一块 A4 三模块音频板" → 期望：plan（含通道）、预览、评审数字、PNG；
2. "把这块板的死网清掉" → 期望：net audit 前后数字 + 修改清单；
3. "检查这张图能不能读" → 期望：R31–R36 报告 + 每条修法；
4. "把 C 板重排成两页" → 期望：两页预览 + 块不跨页 + 标签 0 出框。
