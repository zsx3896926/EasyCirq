# GameForge-X1 实战教训 → Skill 默认执行路径

- 来源：用户提供的“GameForge-X1 实战教训”9 条要求（2026-10-27 转交）。
- 写入目标：不是新增一份建议清单，而是把每条规则嵌入 Agent 默认会读、默认会执行的文件与流程。
- 本文件记录：每条要求 → 决定（采纳/改造/不采纳）→ 落点文件:行 → 验收方式 → 证据级别。
- 相关 guard：`tests/test_skill_rules_present.py`（宽松关键词匹配，防止后续被删）。

## 0. 证据声明（必须如实）

用户报告中的现场路径 `D:/Users/27675/...` 在本机**不可访问**：已实测 `D:\Users\27675` 不存在（`Test-Path` 为 false）。因此：

- **未取得**现场补丁/快照、未读取现场工程或截图，**未复现** GameForge-X1 的具体故障；
- 本文件中的 9 条只按用户描述纳入为流程/设计规则，现场案例本身的**证据级别为 D（未证实）**；
- 不得写成“已吸收现场经验/已复现/已验证该现场修复”；要复现需用户提供该路径的补丁、快照或可访问副本；
- 规则中涉及器件事实（第 8 条）与交付能力（第 3 条）的部分，必须在当前型号/修订/库件和当前 `zhigou capabilities` 上重新核对后才能升级证据级别，不能继承本文件里的 D。

> 编号说明：用户消息列出的编号为 1、2、3、5、6、7、8、9；**第 4 条未在消息中给出**。本文件按实际收到的 8 条逐条落实，不虚构第 4 条内容；若后续补充，按同一格式追加一行。

## 1. 落地总表

| 条 | 要求摘要 | 决定 | 落点 | 验收方式 | 证据级别 |
|---|---|---|---|---|---|
| 1 | 调整默认画法：功能分区＋短引线＋清晰网络标签；局部拓扑（去耦/反馈/晶振/匹配等）保留短线直连；跨区/密集数字优先标签；跨页用正确作用域端口 | 采纳（默认路径改写） | `easycirq/SKILL.md:123`；`easycirq/references/schematic-authoring.md:44`；`easycirq/references/schematic-layout.md:42` | guard 断言三处关键词；人工审查正反例可读性；真机导图复核 | 流程规则（可自动）；现场案例 D |
| 2 | 先验证代表模块：绘制→保存重开→逐脚核对→官方导图视觉检查，再批量扩展；属自主自检，不设用户审批停顿 | 采纳（已有雏形，补全为强制默认步骤） | `easycirq/SKILL.md:125`；`easycirq/references/schematic-authoring.md:55`；`easycirq/references/workflow.md:36`；`easycirq/references/design-gates.md:130` | guard 断言；G2 报告需含 `schematic.representative_module` 证据 | 流程规则（可自动）；真机写入/导图只能真机 |
| 3 | 开工即核对交付能力：原理图/PCB 同步/层叠/布线/DRC/3D/BOM/Gerber/钻孔/CPL，分别记录“已实测/API存在未测/GUI路径/需要开发/不支持”；用 `zhigou capabilities` 预检，接口存在≠已验证 | 采纳（新增交付能力盘点，绑定现有 capabilities 契约） | `easycirq/SKILL.md:108`；`easycirq/references/workflow.md:12`；`easycirq/references/schematic-authoring.md:19` | guard 断言五类标签与 `zhigou capabilities`；真机核对每项真实状态 | 流程规则（可自动）；能力真实状态仅真机 |
| 5 | 失败预算：同类失败连续 2 次重新诊断、禁止原样重试；到阶段预算切换已验证替代路径；预算不得绕过质量检查/放弃交付 | 采纳（并入既有预算机制） | `easycirq/SKILL.md:273`；`easycirq/references/feedback-loop.md:74`；`easycirq/references/tool-gotchas.md:290`；`easycirq/references/design-gates.md:66` | guard 断言；feedback-loop 状态机单测覆盖预算/停止条件 | 流程规则（可自动）；真机失败复现只能真机 |
| 6 | 统一自主执行规则：用户授权整板自主后，布局自检+记录+展示即可继续布线；只有新增范围/关键约束冲突/确需用户选择时暂停 | 采纳（写进评审节奏与交互契约） | `easycirq/SKILL.md:98`；`easycirq/references/interaction.md:32` | guard 断言；人工走查评审节奏不再逐点等许可 | 流程规则（可自动）；真实长任务行为只能真机/人工 |
| 7 | 保护电气设计：禁止浮空支撑脚、改网络、删器件、降约束消几何告警；电气变化必须有依据+影响分析+变更记录；误判修检查器 | 采纳（补进底线、通用门禁规则与审查纪律） | `easycirq/SKILL.md:275`；`easycirq/references/design-gates.md:65`、`:159`；`easycirq/references/review.md:31` | guard 断言；门禁规则与审查清单人工复核 | 流程规则（可自动）；电气正确性只能设计审查/实测 |
| 8 | 核实器件专项案例：按键常通组、型号/修订引脚能力、合并焊盘映射、裸露焊盘功能、摇杆机械尺寸、多单元符号几何；从原厂资料+真实库件核对，先验证再沉淀，不推广 | 采纳（新增器件专项核对表与沉淀格式） | `easycirq/references/design-experience.md:22`、`:70`；`easycirq/references/failures/README.md:61` | guard 断言六类专项与“先验证再沉淀”；实际核对只能对原厂资料+真库件 | 规则（可自动）；事实本身需 E1/A-B 证据，当前未核对（D） |
| 9 | 现场证据缺失如实标注：`D:/Users/27675/...` 本机不可访问；未取得、未复现，仅按用户描述纳入；不得写成已吸收/已复现 | 采纳（本文件第 0 节 + 经验库引用） | 本文件 §0；`easycirq/references/design-experience.md:35` | guard 断言“不可访问/未取得/未复现/仅按用户描述/证据级别 D”存在且无“已复现现场”字样 | 文档规则（可自动）；现场复现需用户证据 |

## 2. 验收方式与结果

```powershell
# 规则存在性（新增 guard）
python -m pytest tests/test_skill_rules_present.py -q
# 期望：passed；断言 1/2/3/5/6/7/8 规则关键词 + 第 9 条证据声明 + 落点文件存在

# Skill 包自检（链接、门禁命名、案例、脚本编译）
python easycirq/scripts/skill_selftest.py
# 期望：5 PASS, 0 FAIL -> exit 0

# 全量离线测试
python -m pytest tests -q
# 期望：全部通过（离线、无真实 EDA）
```

本次实际运行结果（2026-10-27，本机 Windows / PowerShell 7 / Python 3.13）：

| 命令 | 结果 | 证据文件 |
|---|---|---|
| `python -m pytest tests/test_skill_rules_present.py -q` | **6 passed, 51 subtests passed**, exit 0 | — |
| `python -m pytest tests -q` | **1838 passed, 1071 subtests passed**, exit 0 | `docs/toolchain-integration/evidence/skill-migration/field-lessons-pytest.log`、`.exit.txt` |
| `python easycirq/scripts/skill_selftest.py` | **5 PASS, 0 FAIL, 0 NOT RUN**, exit 0 | `docs/toolchain-integration/evidence/skill-migration/field-lessons-selftest.log`、`.exit.txt` |

注意：以上只证明**规则文本已进入默认路径、包结构与离线测试通过**，不证明任何真实 EDA 图纸/PCB 已按新默认画法完成，也不证明现场 GameForge-X1 故障已复现（见 §0 与 §3）。

## 3. 只能真机验证的条目

以下内容无法由离线测试证明，报告中必须保持 `NOT RUN`/`D`，不能因规则存在就宣称已验证：

- 第 1 条的实际图面可读性：需要在真实工程上按默认画法绘制，并用官方导图整页+局部检视；
- 第 2 条的代表模块闭环：真实 `save`→重开→逐脚/pin-net 回读→官方导图，依赖已连接的 EasyEDA 与 connector；
- 第 3 条的交付能力真实状态：`gerber.export`/`drill.export`/`cpl.export`/`pcb.export-3d` 等在实际 EDA/连接器下是否真正产出非空可用文件；
- 第 5 条的真机失败恢复：真实超时/部分写入后的重新诊断与替代路径效果；
- 第 6 条的长任务自主推进：真实整板任务的行为，需要人工观察是否只在允许条件暂停；
- 第 7 条的电气正确性：几何告警修复后是否保持电气等价，需要网表/DRC/实测复核；
- 第 8 条的器件事实：按键内部常通组、型号/修订引脚能力、合并焊盘、裸露焊盘、摇杆尺寸、多单元符号，必须逐项查原厂资料与真实库件；
- 第 9 条的现场证据：在用户提供可访问的补丁/快照并复现之前，保持“未取得、未复现、仅按用户描述纳入（D）”。
