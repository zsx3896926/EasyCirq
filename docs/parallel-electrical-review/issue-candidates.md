# 现有公共模块的问题候选（只记录，不越界修改）

本文件记录任务 B 在只读研究现有脚本时发现的“现有检查无法证明不存在某类电气错误”的
候选问题。**没有修改任何公共模块**；复现在仓库外临时文件完成，0 次 EDA 调用。
建议由主维护者或任务 A 决定是否修复/接入，本任务只提供证据与建议。

## IC-1 `pin_net_intent_check.py` 对“设计源本身把飞跨电容两端接到同一网”返回 `match`

- 文件：`easycirq/scripts/pin_net_intent_check.py`
- 现象：当 intent 和宿主回读都把 C1.1/C1.2 放在同一网 `BOOT` 时，工具输出
  `status: "match"`、`findings: []`、exit 0。它证明“实现忠实于设计源”，但无法发现
  “设计源把飞跨电容旁路”这一真实电气错误。
- 复现（2026-10-27 本机执行，0 EDA）：

```bash
# intent_same.json: C1 pins 1/2 -> BOOT ; nets.BOOT=[C1.1,C1.2]
# read_same.json:   C1 pin 1/2 net BOOT
python easycirq/scripts/pin_net_intent_check.py intent_same.json read_same.json
# 实际: status=match, findings=[], exit 0
```

- 影响：该 `match` 容易被误读为电气正确；真实教训正是“网表逐脚一致只说明忠实于设计源”。
- 建议：不改变该脚本“连接组比较”的职责；在它之前/之后增加本模块 R1/R2 的意图审查，
  并在调用文档中明确 `match` 不是电气通过。本任务 `integration-proposal.md` 给出调用点。

## IC-2 `netlist_check.py` 对两端同网电容只给 `建议`，退出码 0

- 文件：`easycirq/scripts/netlist_check.py`（`same_net_passive` 分支）
- 现象：C1 两端同网时输出 `level=建议, code=same_net_passive`，整体 `status=needs_review`，
  exit 0。它明确写了“不能由此推断电源地短路”，这是合理边界；但该“建议”不会阻断推进，
  也没有角色/耐压/预期网络证据，无法区分“正确的滤波电容两端同网”与“飞跨电容被旁路”。
- 复现：

```bash
python easycirq/scripts/netlist_check.py same_net.json --json
# 实际: status=needs_review, exit 0, issues[0].code=same_net_passive, level=建议
```

- 建议：保留该脚本的通用连通性定位；飞跨/耦合角色明确的电容由本模块 R1 给出
  `hard` finding，并在集成策略中让 hard finding 阻断相关电气推进。

## IC-3 局部去耦距离的默认经验阈值容易跨角色误用

- 相关文件：`easycirq/scripts/design_engine/critical.py`
  （`audit_critical(..., decap_limit_mm=2.54, ...)`）、
  `easycirq/scripts/feedback/evaluate.py`（`decap-too-far` / `decap-too-far-bulk`）、
  `easycirq/scripts/pcb_preflight.py`（`near_pin` 约束）。
- 现象：仓库内已区分 `decap` 与 `bulk` 的反馈类别，但在缺少项目约束时仍存在
  2.54 mm（100 mil）级默认阈值/经验告警；`easycirq/cases/mcu-i2c-s3-2026-10-26/README.md`
  记录“5 条 decap 距离超过 100 mil 经验阈值；保留 WARN 并解释”。这类 WARN 可作为
  布局提示，但不能证明高频回路/ESL/EMI，也不应把 bulk 与 local decoupling 套同一阈值。
- 复现（只读代码与已有真实案例，无需 EDA）：

```bash
grep -n "decap_limit_mm" easycirq/scripts/design_engine/critical.py
grep -n "decap-too-far" easycirq/scripts/feedback/evaluate.py
grep -n "decap" easycirq/cases/mcu-i2c-s3-2026-10-26/README.md
```

- 建议：项目约束显式输入阈值与来源；bulk 与 local_decoupling 分开；报告标注
  “Euclidean/距离代理，不证明回流/ESL/EMI”。本模块 R6 采用该口径，可作为集成参考。

## IC-4 任务书/资料中的 MCP23017 文档号不一致（已核实，不硬编码）

- 任务书提到 “MCP23017 等具体型号”的说法必须查原厂资料；实际核验发现：
  Microchip 现行 MCP23017/MCP23S17 数据手册为 **DS20001952D**（©2005-2022，40 页，
  SHA-256 `63cb5f2bec44434c...`），任务书写的 **DS20001921E 未取得/未证实**
  （尝试下载得到 HTML）。本模块因此**不内置 MCP23017 行为、不硬编码其引脚/文档号**，
  只在 `sources.md` 记录更正与已核实要点。
- 建议：若后续资料需要引用 MCP23017，统一用 DS20001952D 并记录页/表；不要把
  DS20001921E 当事实来源。任务书中的说法保留为“被反驳案例”。

## 未越界声明

以上均未修改 `SKILL.md`、`references/`、`feedback/`、`design_engine/`、`pcb_gate/`、
`runtime/connector/protocol/distribution`、CI、依赖、版本号、README、CHANGELOG 或
`docs/handoff-current.md`。复现输入放在仓库外临时目录，不随 PR 提交。
