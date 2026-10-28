# 现场需求落地矩阵：GameForge-X1 实战教训（9 条）

> 来源：用户 2026-10-27 追加需求（"这批属于工具链整合的优先需求，应该现在纳入；
> 差分优化、自研路由等扩展能力排在后面"）。
> 本文件记录**每条要求落到哪个默认执行路径、用什么验证、证据级别**，不把"新增文档"
> 当作落地。

代表性工程状态（用户认定）：原理图完成、PCB 初步布局，84 件逐脚网络一致 —— 这是有效
成果，但**不能替代布线与制造交付**。因此本轮把"默认画法、代表模块先验证、开工能力预检、
协议兼容、失败预算、自主执行边界、电气保护、器件专项核实、现场证据纪律"写进默认路径。

## 一览

| # | 要求 | 落点 | 状态 | 验证方式 |
| --- | --- | --- | --- | --- |
| 1 | 默认画法：分区＋短引线＋标签，拓扑型局部电路保留短线直连，跨页用正确作用域端口 | `easycirq/SKILL.md`、`references/schematic-authoring.md`、`references/schematic-layout.md` | 已纳入（Skill 侧） | guard 测试断言默认规则存在；真机导图复核（BLOCKED 至连接器导入） |
| 2 | 先验证代表模块再批量扩展（自主自检，不设审批停顿） | `SKILL.md` 绘图流程、`references/workflow.md` | 已纳入（Skill 侧） | 同上 |
| 3 | 开工即核对交付能力，五态记录（实测/API 存在未测/GUI 路径/需要开发/不支持） | **运行时**：`zhigou capabilities` 新增 `deliverables[]`（`measured` / `api_untested` / `gui_only` / `needs_development` / `unsupported`）；**Skill**：开工预检必须调用 | **运行时代码已实现并单测**；Skill 引用待纳入 | `go test ./internal/app -run TestDeliverables`；`evidence/m1/capabilities.json` |
| 4 | 修复 `pagePrimitives.pins` 导致的 compose 拒绝，补夹具与兼容/缺字段负例，不取消完整性检查 | `runtime/internal/app/sch_compose_source_guard.go` + `sch_compose_source_guard_pins_test.go` | **已修复并回归**（5 用例） | `go test ./internal/app -run TestComposeGuard` |
| 5 | 失败预算：同类连续 2 次必须换诊断、禁止原样重试；阶段预算触发换已验证路径 | `SKILL.md`、`references/feedback-loop.md`、`references/tool-gotchas.md` | 已纳入（Skill 侧） | guard 测试；真机由验收脚本记录重试次数 |
| 6 | 统一自主执行规则：授权整板后布局自检+记录即可继续布线 | `SKILL.md` 评审节奏、`references/interaction.md` | 已纳入（Skill 侧） | guard 测试 |
| 7 | 保护电气设计：不得用浮空脚/改网/删件/降约束消告警；误判修检查器 | `SKILL.md` 底线、`references/design-gates.md`、`references/review.md` | 已纳入（Skill 侧） | guard 测试 + 既有 gate 负例 |
| 8 | 器件专项核实（按键常通组/型号修订引脚/合并焊盘/裸焊盘/摇杆/多单元几何）先验证再沉淀 | `references/design-experience.md`、`references/failures/`、`field-lessons.md` | 已纳入（Skill 侧） | 新增条目带适用条件与证据级别 |
| 9 | 现场证据纪律：`D:/Users/27675/...` 不可访问则明确缺件，不宣称已吸收/已复现 | 本文件 §9 | **已按缺件记录** | 本文与 `evidence/` 中不出现"已复现"表述 |

## 4. 协议兼容修复（重点说明）

**现场问题**：真实 EasyEDA Pro Connector 的 `schematic.components.list
--include-page-primitives` 响应里，`pagePrimitives` 多了一个**附加类 `pins`**；
compose 的来源快照校验用 `len(page) != len(required)` 比较**类数量**，于是把一份完整快照
判成 "incomplete class inventory" 并拒绝。

**修复方式（没有取消完整性检查）**：

* 必需类仍然逐个强制（缺任何一个都报错，测试 `TestComposeGuardStillRequiresEveryKnownClass` 覆盖 10 个类）；
* 只有**白名单内的附加类**（当前仅 `pins`）被容忍，且要求它是数组、元素是对象，否则拒绝
  （`TestComposeGuardRejectsMalformedPinsClass`）；
* **未知**附加类仍然拒绝（可能是有身份的对象，不能默认不保护：
  `TestComposeGuardRejectsUnknownExtraClass`）；
* 没有 `pins` 的旧快照继续可用（`TestComposeGuardAcceptsSnapshotWithoutPinsClass`）。

**证据级别（重要）**：现场 Connector 原始响应与执行器补丁**未取得** —— 报告中的
`D:/Users/27675/...` 在本机不存在（`Test-Path D:\Users\27675` = False），因此本轮
夹具是**按现场描述构造的合成夹具**，不是抓包回放。要完成"真实响应脱敏夹具"这一步，
需要把现场响应 JSON（可脱敏）放到本机任意可读路径，然后用同一组断言回放。代码路径已
按该形状修好，不会因为拿到真实响应再改一次结构。

## 9. 现场证据缺件记录

| 证据 | 状态 | 说明 |
| --- | --- | --- |
| `D:/Users/27675/...` 现场补丁/快照 | **未取得** | 本机无该路径（另一台机器）；不得宣称已吸收/复现 |
| 现场 Connector 原始响应（pins 类） | **未取得** | 夹具为合成；修复按描述的形状完成 |
| 现场执行器补丁 | **未取得** | 需用户提供补丁文件后才可对照 |

## 验收要求对应

| 验收要求 | 本轮落实 |
| --- | --- |
| 规则进入实际默认执行路径 | Skill 侧修改默认流程段落（不是附录）；运行时侧 `capabilities.deliverables` 直接出现在开工预检输出里 |
| 协议修复进入代码并有回归 | 已修 + 5 个 Go 用例（兼容/缺类/未知类/畸形/旧快照） |
| 用新任务证明代表模块策略、标签画法、能力预检生效 | 真机验收脚本 `tools/zhigou_acceptance.py` 已把能力预检设为硬前置；代表模块与标签画法的"生效"需连接器导入后由 M2/M3 证据证明 —— 当前 **BLOCKED**，不冒充 |
| 分别报告耗时、返工、图面与电气结果 | `docs/toolchain-integration/performance.md` 定义基准；真机数据待 M2–M4 |
| 不以文档数量/测试数量代表体验改善 | 本文件只记录落点与验证手段；体验改善以真机 M2–M4 的耗时/返工/图面/电气结果判定 |
