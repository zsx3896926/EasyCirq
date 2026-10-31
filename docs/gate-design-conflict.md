# 门禁与「从零建板」的死锁（2026-10-31 实测，当日已解决）

## 结论

目标里写着两条要求，它们互相冲突：

> 未过离线门禁，任何写入被 daemon 拒绝——是 403，不是建议。

> AI 可以独立完成，但每一步都必须先离线跑通再上真机。

**实测**：在空页面上放第一个器件，daemon 返回

```
GATE_REQUIRED
这次写入被拦下了：还没有这一页通过离线检查的通行证
```

而通行证要求该页 `verdict=PASS` 且 `apply_allowed=true`。空页面永远不满足
（悬空/缺证据），于是：

**不画完过不了检查 → 过不了检查就画不了第一笔。**

## 为什么之前没发现

所有验证都是「检查已有工程」：

- RetroCam-02 P1/P2：已经在 EDA 里画好的图，只做读检查
- `KPI_S5_Verify`：先有 R1/R2/R3，再验证保存/回读
- 所有 fixture：从既有快照出发

**从来没有从空页面开始过。** 目标说「AI 可以独立完成」，但这一条从未被测试。

## 实测过程

```
$ easycirq --project KPI_S5_Verify sch place --lib ... --uuid <0805-LED> --designator D1
{"ok": false, "error": {"code": "GATE_REQUIRED",
 "message": "这次写入被拦下了：还没有这一页通过离线检查的通行证"}}
```

## 可选解法

### A. 分阶段门禁（推荐）

把写入按**意图**分成两类：

| 类别 | 例子 | 门禁 |
|---|---|---|
| 建板写入 | 放器件、连线、标网络、放 GND | **不拦**，但记录到变更日志 |
| 交付写入 | 导出 Gerber/BOM、生成制造文件 | 必须 PASS + 有令牌 |

理由：目标自己也说「门槛低在入口，不是低在标准」。**从零画图不该被门禁挡，
说"这块板可以打样"才该被挡。**

实现代价：`ActionSpec` 需要按 action 区分；daemon 的 `mutatingSpecs` 分成两档；
客户卡片的语义不变（仍然只在 PASS + 令牌时说可以打样）。

### B. 增量门禁（更保守）

写入前后各跑一次 KPI，**只禁止新增 blocker**：

- 空页面 → 放一个器件 → 仍是 blocked，但 blocker 没有增加 → 放行
- 已有 1 个悬空 → 再放一个悬空 → blocker 从 1 变 2 → 拒绝

代价：每次写入要跑两遍检查（慢），且"不增加 blocker"这个判据本身可能被钻空子。

### C. 空页面豁免

页面零器件时放行。一旦有器件就锁死——第二个器件就过不去，等于没解决。

## 我的判断

选 **A**。它保住目标的核心不变量（交付前必须过门禁），同时解开死锁（画图不被拦）。
B 的代价太高且判据脆弱；C 不成立。

但这是**产品语义变更**，需要你拍板：

- 如果你要「任何写入都必须过门禁」的严格版A，那目标里的「AI 独立完成一块板」就不成立
  （至少"从零画"这一半不成立，只能"改已有图"）。
- 如果你要「AI 能独立完成」，就得放开建板阶段的写入。

## 当前状态

- 门禁实现与真机验证都是按「全部 mutating action 都要令牌」做的
- 结论：**目标的两条要求在今天的实现下不可同时满足**
- 这不是 bug，是设计取舍，所以我停在这里问你，而不是自己改掉门禁

## 解决（2026-10-31 晚，1.3.0）

采用方案 A（分阶段门禁），已实现并真机验证。

`ActionSpec` 新增 `GateRequired` 字段，只有**交付类**动作标 true：

| 动作 | GateRequired |
|---|---|
| `pcb.manufacture.gerber` | true |
| `pcb.manufacture.cpl` | true |
| `pcb.manufacture.netlist` | true |
| 其余 111 个 mutating（建板/布局/布线） | false（不再受门禁约束） |

daemon 的门禁索引从 `mutatingSpecs`（Mutates）改为 `deliverySpecs`（GateRequired）。

真机验证（1.3.0）：

| 动作 | 结果 |
|---|---|
| `sch place`（放 LED） | `ok: true` —— 放行 |
| `call pcb.manufacture.gerber` | `GATE_REQUIRED` —— 拦截 |

不变量保留：**没有证据就不能声称可以交付**。死锁解开：**画图不再被门禁挡住**。

新增测试：`TestBuildActionsAreNotGated`、`TestDeliveryActionsAreGated`；
gate 测试全套 12 项通过。
