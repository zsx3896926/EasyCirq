# PCB 预布局审题：第一轮独立盲测（2026-10-29）

> 对象：[exercises-pcb 盲测题面 v1](../../../easycirq/references/engineering-deepdives/exercises-pcb/blind-prompts.md)（20 题 X01–X20）。
>
> 结论先说：**盲测可跑、机制与"不臆造"纪律达标；但结论类型维只有 71.7%，且题面存在泄题与信息缺口**。题面已按评审修订为 v2（见 [evaluation.md](evaluation.md) §4–§5），本轮分数与 v2 不可直接比较。

## 1. 方法

| 项 | 做法 |
|---|---|
| 试答者 | 3 名独立 Agent（B1/B2/B3），互相不可见 |
| 输入 | 只给题目副本（放在仓库外 `.tmp-test-run/blind/prompts.md`，内容与 v1 题面一致） |
| 隔离方式 | **约束式**：明确禁止读仓库/答案/案例、禁止联网、禁止运行命令；每人结尾自报"读过文件"，3 人均只有题目副本路径 |
| 评审 | 1 名独立评审 Agent：对照 [answers.md](../../../easycirq/references/engineering-deepdives/exercises-pcb/answers.md) 与五维口径逐题打分 |
| 评分 | 结论类型/机制/证据/行动/未知 五维，`✓ / △ / ✗` |

## 2. 结果摘要

| 维度 | ✓ 比例 | 说明 |
|---|---|---|
| 结论类型 | **43/60 = 71.7%** | 失分几乎全是"条件/待补/可确认"标记位移；真正内容错误只有 X01 的 review→blocking |
| 机制 | 57/60 = 95.0% | 三人共同弱项在 X05（代理压缩 vs 只声明一个硬检查） |
| 证据 | 60/60 = 100% | **饱和，原因是题面泄题**（案例 id + PL 编号直接给） |
| 行动 | 58/60 = 96.7% | 两处漏答"过度例"子问 |
| 未知 | 58/60 = 96.7% | 两处漏 `NOT RUN` |

按 Agent：B1 结论类型 14/20、B2 15/20、B3 14/20；60 份作答中**没有**过度修改、臆造 code、补默认坐标的越界行为。

## 3. 评审发现（详见 [evaluation.md](evaluation.md) §4）

1. **X01 题面缺"软检查/无硬检查命中"** → B1/B2 把 review 判成 blocking/fail，属题面缺陷（已修）。
2. **题面泄题**：多题直接写出"期望 blocking/codes 只有 X""从 review 翻到 acceptable"，证据维因此 100%（已修：只留案例 id，删 PL 与 verdict/codes 提示）。
3. **X11 三人共弱**：答案只写"条件"，未拆"哪部分可确认、哪部分条件"（题面已加标记落点要求）。
4. X03/X04 未给 code 名，三人正确地"不臆造"（保留该训练目标，v2 注明口径）。
5. X01/X08 的"过度例"子问未被当作必答（已修）。

## 4. 这轮盲测能证明 / 不能证明

**能**：题面足以支撑机制解释与修复动作选择；"不臆造、不补数据、不整板重排"的纪律在盲测下可复现；题面泄题与信息缺口被定位并修订。

**不能**：3 个样本、单评审人、约束式隔离（非容器/权限强隔离）、三份作答高度同构——**不能**据此推断模型能力，不能作为认证或对外能力声明；本轮分数不代表 v2 题面难度。

## 5. 文件

- [responses.md](responses.md)：3 份作答原文（未编辑）
- [evaluation.md](evaluation.md)：逐题评分、统计、发现与修订结论
- 题面：[blind-prompts.md](../../../easycirq/references/engineering-deepdives/exercises-pcb/blind-prompts.md)（v1 已试答，v2 修订后用于下一轮）
- 答案与评分维度：[answers.md](../../../easycirq/references/engineering-deepdives/exercises-pcb/answers.md)、[exercises-pcb/README.md](../../../easycirq/references/engineering-deepdives/exercises-pcb/README.md)

## 6. 复跑方式（下一轮）

1. 复制当前 `blind-prompts.md`（v2）到仓库外目录；
2. 起 2–3 个新会话，只给该文件，明确禁止读仓库/答案/联网/运行命令；
3. 用 `answers.md` + 五维口径独立评审（建议两人交叉评分）；
4. 记录"读过文件"声明，并在本目录新增 `round2-*.md`，不要覆盖本轮证据。
