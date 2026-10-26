# EDA 工具动作陷阱

本文件记录 easyeda-agent 操作嘉立创EDA专业版时，已经被现场证据确认的动作级陷阱：命令返回成功但对象没有按预期改变，或者同一条命令只因前台/活动页状态不同就失败。这里只写“现象、原因、正确动作、证据/边界与本案例”；工程方法、能力矩阵和保存/重开流程仍看 [eda-execution.md](eda-execution.md)，门禁定义、证据角色与豁免规则看 [design-gates.md](design-gates.md)，2 层/4 层与电源地取舍看 [pcb-routing-strategy.md](pcb-routing-strategy.md)。

本案例指 2026-10-24 室内温度报警小板复盘；案例列引用该项目的原始证据文件名。未加前缀的文件在 `temp-alarm-20261024/evidence/` 根目录；`pcb-check.json`、`pcb-list.json`、`pcb-layers.json`、`pcb-stackup.json`、`sch-nets.json`、`sch-export-png.log` 与作为混排示例的 `pcb-drc.json` 位于其 `round7/baseline/` 子目录。技能内回归案例是 [cases/temp-alarm-2026-10-24](../cases/temp-alarm-2026-10-24/README.md)，只收录门禁读取所需的证据子集。

## 适用范围与版本基线

- 适用工具：easyeda-agent `v1.14.0`。
- 适用客户端：嘉立创EDA专业版 `4.1.78.34f5b8d9`。
- 证据时间：2026-10-24 的 Windows 实机会话，以及 `docs/evidence/` 下的现场记录。
- 命令和参数只写到本文件已核对的 v1.14.0 命令面；未列出的动作、参数和返回字段不作承诺，执行前用当前 `--help` 复核。
- 不同客户端版本、不同工程和不同窗口状态都可能改变结果；一次成功不等于通用保证。
- 文档中的门禁不是审批。Agent 在已授权范围内按证据记录 `PASS`/`BLOCKED`/`PASS_WITH_WAIVER`/`UNSUPPORTED`，不新增等待点；`PASS_WITH_WAIVER` 只表示有条件满足并写明理由、条件和剩余风险，不能当成 `PASS`，`UNSUPPORTED` 也不能当成 `PASS`。

## 三条总原则

### 1. 先落盘，再读内容

支持 `--json` 的检查先加 `--json`，并把完整 stdout 和 stderr 写入文件；不支持 JSON 的命令也重定向完整 stdout/stderr。不要只保留终端最后几十行，也不要用 `Select-Object -First N` 截断 JSON 数组。文件名以 `.json` 结尾不代表内容一定是 JSON，后文单列。

### 2. 先回读，再决定是否重试

超时、`partial:true`、`ok:false`、`noChanges:true` 都不是“再跑一次”的信号。先读当前对象和网络，确认哪些动作已经生效，再只补差异；整批重放可能制造重复器件、重复导线，或把一次局部失败扩大成多处修改。

### 3. 前台要求按动作区分

| 动作 | 前台/活动状态要求 | 结论 |
|---|---|---|
| `sch check` | 目标页必须是 active document | 窗口是否可见不是要求；非活动页会被拒绝或只返回 shallow data |
| `pcb drc` | PCB 必须是 active/foreground | 后台或遮挡窗口会算不完 |
| `pcb snapshot` | PCB 必须在前台且 tab 可见 | hidden tab 直接 `PRECONDITION_REFUSED` |
| `sch export-image` | 无前台要求 | 后台可导出；不要写成“所有导出都要前台” |

## 总表

| 门禁 | 现象 | 原因 | 正确动作 | 证据/边界与本案例 |
|---|---|---|---|---|
| G2 | `sch drc` 全 0，但 `sch check` 还有一批发现；两个命令结论不一致 | `sch drc` 是官方 SDK 的 DRC 门禁，可能只返回布尔/聚合结果；`sch check` 从图元与制造网表重建逐项发现，覆盖浮空脚、网标/导线网名不符、交叉、压脚与风格 | 分层判：DRC 看 fatal/error=0；`sch check --json` 的电气类必须 0，风格/结构类修复或按 [design-gates.md](design-gates.md) 豁免。两个都跑，不能互相替代 | `sch drc` 只在 fatal 计数 >0 时非零，warn 可退出 0；`sch check` 默认 0 退出，`--strict` 才用发现数当门禁。本案例 `sch-drc.json` 0 违规，`sch-check-final2.json` 10 条风格/结构发现 |
| G2 | `sch check` 报 `Active schematic document instance is unavailable` | 目标页不是 active document | 用 `--page NAME\|UUID` 指定目标页，或 `doc switch` 后回读活动页，再检查 | 切换后成功；要求是目标页活动，不是窗口可见。本案例单页 P1，未触发 |
| G2 | `sch check` 报 `peripheral-not-direct`，但 DRC 与网表都过 | 同名网标只证明“网名相同”，不证明“实际导线直连”；模块重建工具把标签连接判为断开的 physical wire islands，并明确“同名标签不算直连” | 动笔前先定风格；选同名网标就在 `design-state.json`/豁免中写 `peripheral-not-direct`，注明范围、理由与复验证据；不要用“网表里有这个网”反驳它 | `sch nets` 是全工程网表审计（同轨异名、单引脚网），看不到“标签代替直连”；直连证明必须来自导线几何或豁免记录。本案例 `sch-check-final2.json` 报 J1、C1、RV1、U1、Q1 共 5 条；`sch-nets.json` 同时报 14 张网、0 单引脚网 |
| G2 | `zone-arrange` 的 `--apply` 反复拒绝 | plan terms 只有 `netflag`，没有 `net_label`；C1 pin1 直连树无标记 | 先消除无标记直连；补 netport 后仍要重跑并回读；不要把推断写成日志原话 | 29 项 term 均为 netflag；`zone-arrange-apply-3.log` 仍失败。本案例日志原文“C1 pin1 经普通导线直连(树上无标记)” |
| G1/G3 | `pcb import-changes` 返回 `noChanges:true`，PCB 仍有已删件 | 同步只导入/更新，不删除原理图已移除器件 | 用 `pcb delete --ids ...`、`track-delete` 或 `rip-up` 显式删除并回读 | 28→28，J2 仍在；`pcb-drc-5.json` 报 netlist mismatch。本案例 `pcb-import-after-j2-removal.log`/`pcb-import-after-usb-removal.log` |
| G3 | `outline-fit` 被当成布局完成 | 它只改板框，不移动器件；板框跟随器件 bbox，不预留安装孔边距、连接器插拔空间或外壳壁厚 | 先 `place-constrained` 或人工布局，再 `outline-fit`，完成后重读器件位置；目标尺寸必须来自需求，不能由 fit 反推 | parts=28、partExtent 3377.55×1976.76、newOutline 3577.55×2176.76、utilBefore 0。本案例最终框 90.87×55.29 mm，`holes: 0` |
| G3 | `layout-lint --gate` 想当布线门禁 | 参数已废弃，只显示历史阈值，不授权也不阻断 | 读 score、crossings、overlap、off-board，按 Skill 阈值和 G3/G4 证据判定 | 默认 score≥60、crossings≤8；实测 48/100、13 crossings。本案例 `pcb-layout-lint-2.log` |
| G3/G5 | 布局分数好看，但丝印压焊盘、标签互压没被算进去 | `layout-lint` v1 是器件 bbox 级近似，只判 overlap/off-board/tight/crossings；它复用 `pcb check` 的 `silk-over-pad`/`silk-off-board` 放在 `silk` 段，WARN 不计分；标签-标签/标签-器件重叠不在其判定范围 | 丝印用 `silk-align`/`silk-set` 修并回读；原理图标签重叠另跑 `sch clusters`；最终以实际 PNG/渲染图为准 | 分数高不等于可读可装配。本案例 `pcb-layout-lint-2.log` 4 条 silk-over-pad；`pcb-check.json` 另报 2 条 silk-over-pad 与 2 条 silkscreen-flipped |
| G4 | `power-pour` 同层多网的 priority 对不上 | 创建回执 `priorityVerified:false`，重载后值会变；`pour-list` 也可能不返回实际成铜状态 | 用 `pour-list` 按层按网回读 priority；用 `poured-list`/dump 铜确认实际成铜；同层多网必须复核 | 回执可见 priority 1/1/2；重载后 GND L1 priority=3。本案例 `pcb-power-pour-apply.log`/`pcb-pour-list.json` 同此；`pour-list` 的 pour 项没有 `poured` 字段，不能默认已填充 |
| G4/G5 | `route-short --route-power` 后 DRC 暴增 | 强制把电源/地布成 track，默认本应跳过 | 铺铜板保持默认跳过；必须用时先 `--dry-run`，检查宽度、vias、skipped nets | GND 是 20 mil，不是细线；DRC 93 = 71 Clearance + 22 Connection。本案例 `pcb-route-power-dryrun.log` 计划 +5V 20 mil L 形穿焊盘区；`pcb-tracks-gnd.json` 44 段 GND 线 |
| G4 | `pcb power-planes` 在 2 层板上失败 | 需要 ≥4 层，2 层会被拒绝 | 2 层改用 `power-pour`；不要为了用 power-planes 临时改层叠 | 2 层被拒绝并提示改用 power-pour。本案例为 2 层板 |
| G4/G6 | `pcb stackup` 只打印帮助，`pcb-stackup.json` 里没有层数 | `stackup` 是命令组，不带子命令只显示用法 | 读 `pcb stackup show` 或 `pcb layers`；改 `pcb stackup set`；把结果写进 `design-state.stackup` | 回执没有 `copperLayerCount` 就是帮助文本。本案例 `round7/baseline/pcb-stackup.json` 实际是 help 文本，同批 `pcb-layers.json` 才给出铜层数 |
| G5 | `pcb drc` 超时或一直算不完 | PCB 不在前台/活动窗口 | 切到 PCB 前台，用 `--timeout SEC` 跑一次；不要循环重试 | 后台/遮挡窗口的现场表现；超时也是非零退出，`--json` 保留 `nativeResult` |
| G5 | `pcb snapshot` 返回 `PRECONDITION_REFUSED` | tab hidden，画布未重绘，截图会过期 | 切前台重试；不能用截图时改用 `pcb dump --include-copper` 取几何，或 actual 读回渲染并标注“非官方前台截图” | 错误原文含 `The EasyEDA tab is hidden...`；本案例 `pcb-snapshot-top.json` 被拒，改用 `pcb-render-final.svg` |
| G5 | `doc switch` 被当成保存/重载 | switch 只切前台；只有 reload 才 save→close→reopen；ready 只读 | 需要持久化就显式保存后重开并回读；mutating 动作用 `--doc` 钉住页面；多窗口用 `--project` 路由 | `--doc` 在 live `document.current` 不匹配时拒绝。本案例 `pcb-list.json` 因前台是原理图被拒，错误信息直接建议 `--doc`/`doc switch` |
| G4/G5 | 修改后回执带 `staleRisk`，`via.list`/`components.list` 是旧数据 | PCB mutation 后宿主枚举可能没刷新；staleRisk 只是提示，不是拒绝 | `pcb save` → `easyeda doc reload` → 重新读取；刷新失败按不可用处理 | staleRisk 回执只作诊断，不能当最终约束证据；G4 过孔审计遇到 staleRisk 直接失败。本案例 `pcb-vias-4.json`（route.delete 后）与 `pcb-import-after-usb-removal.log` 都带 staleRisk |
| G2/G5 | `sch snapshot` 找不到 | v1.14.0 已移除，由 `sch export-image` 取代 | 用 `sch export-image --format svg\|png\|pdf`；它无前台要求 | 只替代原理图快照，不等于 PCB 截图。本案例 `sch-export-png.log` 在 hidden 下成功 |
| G4/G5 | `net-path` 失败被当成整板断连 | 只证明 listed routed copper；铺铜、内电层、填充区不计入 | 先补 track 或改用铺铜/连接性证据，再用 DRC 与回读判断 | 失败=未被走线证明，不等于全板断连。本案例 GND 靠双层铺铜加 44 段 GND 线；G5 最终 DRC 仍有 2 条 Connection（+5V） |
| G4/G5/G6 | `pcb check --strict` 非零，或 `pcb check` 0 退出就以为 DFM 通过 | `pcb check` 是重建 DFM 审计，默认信息模式 0 退出；`--strict` 把 WARN/ERROR 都变成非零；它与 `pcb drc` 规则集不同 | 分层看：`pcb drc` 管 clearance/连接；`pcb check` 管 dangling/锐角/过孔/铺铜/3W/丝印等；报告分别列 ERROR/WARN/INFO 与修/豁免 | 0 退出只代表信息模式没报错，不是 DFM 全证明。本案例 `pcb-check.json` 40 issue（ERROR=13、WARN=17，其余 INFO）加 power-not-poured；同板 `pcb-drc-11.json` 18 条（16 Clearance、2 Connection） |
| G6 | `bom export` 抛 `TypeError` | `bom-enrich.py` 遇到 `value=null` 且 BOM Value 为空 | 用 `--enrich=false` 保留原始；把 enrichment 失败当非阻断 warning | `sequence item 5: expected str instance, NoneType found`。本案例 `bom-export.log` 原样包含该 traceback 与 “file left un-enriched” |
| G6 | `project export` 缺参数报错；`restoreVerified:false` 被当成恢复演练 | 命令要求显式 `--out` 与 `--project-uuid`，且不覆盖；恢复验证要在副本上重开，导出本身不做 | 先保存文档再导出；把 zip 完整性（`zipIntegrityVerified`）与恢复演练分开记录；恢复演练后写 `restore_verified` | `restoreVerified:false` = 未演练，G6 的 `epro2_restore` 直接失败。本案例 `project-export.log` 缺参报错，`project-export-2.log` 导出成功但 `restoreVerified:false` |
| G6 | 找不到 Gerber/钻孔/CPL 命令 | v1.14.0 无 CLI/typed action；Gerber API 仍 @beta 且未包装 | 由用户在 EDA GUI 导出并落证据；子项标 `UNSUPPORTED`，缺证据时 G6 `BLOCKED` | 不得编造命令，也不得把 GUI 导出写成 CLI 已验证。本案例 G6 因缺 Gerber/CPL/恢复演练 BLOCKED |
| G2–G6 | `.json` 文件里是纯文本、JSON 加人类行或 traceback | CLI 可能先输出 JSON 再追加摘要；有些命令只输出 human 文本；stdout/stderr 合流也会污染 | 落盘时分离流：`> out.json 2> out.err`；记录 `format`；不要盲目解析；截断或损坏按 `BLOCKED` 处理 | `sch-drc.json` 等纯文本；`pcb-drc-1.json` 末尾有 CLI 行；`round7/baseline/pcb-drc.json` 第 1323 行混入人类摘要导致整份解析失败；`bom-export.log` 含 traceback |

## 逐条说明

### 1. `sch check`：目标页必须是 active document（G2）

**现象**：目标页不是当前活动原理图页时，命令报 `Active schematic document instance is unavailable`；即使命令能返回，非活动页也可能只给出 shallow data，pins/bbox 为空。

**原因**：检查对象绑定的是活动文档实例，不是“窗口看起来在前台”。窗口可见但活动页是另一页，同样会失败。

**正确动作**：先用 `--page NAME|UUID` 指向目标页，或用 `doc switch` 切换后再确认活动页；随后执行 `easyeda sch check --json --page NAME|UUID`。若仍返回 shallow data，先修活动页状态，不把空 pins 解释成“没有引脚”。

**证据/边界与本案例**：现场错误原文如上报；切换到原理图目标页后检查成功。这个前台要求只属于 `sch check` 的活动文档语义，不要扩大成“原理图检查都必须把窗口摆到最前”。本案例单页 P1，未触发；同族要求在 PCB 侧由 `pcb-list.json` 的 `PRECONDITION_REFUSED` 直接体现。

### 2. `pcb drc`：前台状态决定能否跑完（G5）

**现象**：PCB 在后台或被窗口遮挡时，DRC 长时间没有结果，最终超时；`--json` 可能只剩错误或空结果。

**原因**：DRC 依赖当前 PCB 画布的活动/可见状态；后台或遮挡窗口不会正常完成计算。这里的“超时”通常不是规则太多。

**正确动作**：把 PCB tab 切到前台，使用 `easyeda pcb drc --json --timeout SEC` 跑一次，并把完整输出落盘。超时后先检查 PCB 是否真的在前台，再做一次干净重跑；不要在不改变窗口状态的情况下循环重试。

**证据/边界与本案例**：`--json` 输出包含 `passed`、`total`、`counts`、`violations`、`nativeResult`，每条 violation 有 `rule/objType/ruleName/net/x/y/layer/objs/message`，x/y 是真实 mil。前台要求只约束 DRC 的可靠执行，不要外推到所有只读命令。本案例 PCB DRC 返回 18 条；`pcb-list.json`/`pcb-layers.json` 因前台是原理图被拒。

### 3. `pcb snapshot`：hidden tab 直接拒绝（G5）

**现象**：`easyeda pcb snapshot` 返回 `PRECONDITION_REFUSED`，消息为 `The EasyEDA tab is hidden...`，并明确说没有捕获到图像。

**原因**：hidden tab 的画布没有重绘，截图会是过期画面；工具宁可直接拒绝，也不返回假图。

**正确动作**：把 PCB 窗口切到前台再抓图。无法切前台时，改用 `easyeda pcb dump --include-copper` 读取几何，再用 DRC、`pour-list` 和回读判断；原理图图面改用 `sch export-image`。

**证据/边界与本案例**：snapshot 只是视口 PNG，不渲染 filled copper/cutouts，不能拿它证明铺铜、开槽、连接或制造状态。反过来，`sch export-image` 明确无前台要求；不要把 PCB 的前台限制写成“所有导出都要前台”。本案例 `pcb-snapshot-top.json` 被拒，证据改用 `pcb-render-final.svg`（actual 读回渲染，非官方前台截图）。

### 4. `power-pour`：同层多网的 priority 回执不可信（G4）

**现象**：默认 `power-pour` 在本轮创建 4 个铺铜：GND L1、GND L2、+5V L1、VREF L1。创建回执里可见 priority 1/1/2，且 `priorityVerified:false`；重载后 `pcb pour-list` 读到 GND L1 priority=3，与回执不一致。

**原因**：同层存在多个网络铺铜时，SDK 创建回执的 priority 只是当次写入值，工具自己也没有把它标记为已验证；实际优先级由重载后的文档模型决定。

**正确动作**：同层多网铺铜后必须用 `easyeda pcb pour-list` 按层、按网回读 priority 和 basic 属性；需要确认实际成铜时用 `pcb poured-list` 或 `pcb dump` 的铜几何（`pour-list` 的 pour 项可能没有 `poured` 字段，不能默认已填充）。需要调整时用已核对参数重跑或重建，再回读，不要修改或复述回执字段当作最终结果。随后用 `pcb drc` 和 `pcb check` 复核连接与铺铜。

**证据/边界与本案例**：铺铜后首次 DRC 为 30（3 Clearance + 27 Connection）。此前没有 DRC 基线，因此“27 条 Connection 是铺铜造成的”只是时间顺序推断，不是已证明的因果；写作时不要把它写成铺铜必然导致断连。同层多网 priority 的最终值只以 `pour-list` 回读为准。本案例 `pcb-power-pour-apply.log` 创建 4 个 pour，`pcb-pour-list.json` 回读 GND L1=3、+5V=1、VREF=2。

### 5. `route-short --route-power`：把电源/地当 track（G4/G5）

**现象**：在已铺铜的板上加 `--route-power` 后，命令生成 73 条 route（GND 45、+5V 21、VREF 7；2 条 VREF 失败），实际 drawn 71、vias 14；随后 DRC 升到 93（71 Clearance + 22 Connection），其中 net=GND 的 Clearance 68 条。

**原因**：`route-short` 默认跳过 power/ground，因为电源地应由铺铜承担；`--route-power` 强制把它们布成普通 track，help 自述这是 #1 DRC source。GND 的 track 宽度是 20 mil，不是“细线”；问题在于铺铜板上多出与铺铜竞争的走线，而不是线宽本身。

**正确动作**：铺铜板保持默认行为，不加 `--route-power`；先跑 `easyeda pcb route-short --dry-run`，检查 routes、skipped nets、vias 和宽度，再决定是否落图。若必须临时用 `--route-power`，把它当候选而非完成，落图后逐项看 DRC 与 GND 项，必要时撤销这些 track 后重布。2 层/4 层的完整取舍见 [pcb-routing-strategy.md](pcb-routing-strategy.md)。

**证据/边界与本案例**：73/71/14 是入参和实际绘制的现场结果，不代表以后每次相同；93 条 DRC 是该轮状态，不是通用阈值。不要把 GND 20 mil 误写成细线，也不要用 route 数量证明连通。本案例 `pcb-route-power-dryrun.log` 计划 +5V 20 mil L 形穿焊盘区；`pcb-tracks-gnd.json` 有 44 段 GND 线；最终 DRC 16 条 Clearance 含 +5V/OUT、+5V/VREF、+5V/REF_TOP。

### 6. `zone-arrange`：net_label 不在 plan term 模型里（G2）

**现象**：`zone-arrange` 的 plan 判为 pass，但 `--apply` 拒绝，日志原文是“C1 pin1 经普通导线直连(树上无标记)”；补 netport 后重试仍失败，`zone-arrange-apply-3.log` 依旧是同一断言。

**原因**：该轮 plan 的 29 项 term 全部是 `netflag`，没有 `net_label`。C1 pin1 靠普通导线直连，重建指令覆盖不到这种无标记树。由此可以推断 term 模型不识别净标签，但“工具不认 net-label”是从 term 结构推断出来的，不是日志里的原话。

**正确动作**：先手工梳理 C1 pin1 的无标记直连，把目标连接改成 plan 可识别的 term，再重跑计划并检查 apply 日志；不要只补一个 netport 就假定能通过，也不要反复重跑同一失败计划。若 apply 仍拒绝，保留原图并改用已核对的手工移动路径。连接风格（直连 vs 同名网标）要在动笔前定好，不要交替重跑互相提出相反要求的工具。

**证据/边界与本案例**：plan terms 29 项均为 netflag；`zone-arrange-apply.log`、`zone-arrange-apply-2.log`、`zone-arrange-apply-3.log` 记录同一失败。不要写“日志说 zone-arrange 不支持 net_label”，只能说从 term 模型推断其未覆盖 net_label。本案例 `sch-check-final2.json` 同时有 5 条 peripheral-not-direct（J1、C1、RV1、U1、Q1）。

### 7. `bom-enrich.py`：value=null 触发 TypeError（G6）

**现象**：`easyeda bom export` 已经写出 CSV artifact，随后 enrichment 抛 traceback，进程退出 1，并打印 `warning: BOM exported but enrichment failed (file left un-enriched)`。

**原因**：`standard-parts.json` 中有 `value=null` 的 part，而 BOM 的 Value 为空；`bom-enrich.py` 执行 `'\t'.join(r)` 时，第 5 个字段是 `None`，抛出 `TypeError: sequence item 5: expected str instance, NoneType found`。

**正确动作**：用 `easyeda bom export --type csv --enrich=false` 保留原始导出；原始 Supplier Part 已带 C 号时，先核对每行 C 号、位号、数量和封装。把 enrichment 失败当作非阻断 warning，不要因此宣称整个 BOM 导出失败；需要补全时修源数据或单独修脚本，再重跑。

**证据/边界与本案例**：`bom-export.log` 同时包含 JSON、人类可读行和 traceback，不能当纯 JSON 解析。C 号存在不等于库存、价格或 SMT 状态已实时核对。本案例 `bom-export-raw.log` 用 `--enrich=false` 导出成功（同一 SHA-256）。

### 8. `pcb import-changes`：不删除原理图已移除的器件（G1/G3）

**现象**：原理图删掉 J2 后执行 `pcb import-changes`，返回 `noChanges:true`、`componentsBefore:28`、`componentsAfter:28`；`pcb-list-after-j2.json` 里 J2 仍然存在。之后的 `pcb-drc-5.json` 出现 `PCB and schematic netlist does not match`。

**原因**：`import-changes` 负责把原理图网表/器件同步进 PCB，但不会删除 PCB 上已经存在、原理图已经移除的器件。`noChanges:true` 和数量不变不能证明两边网表一致。

**正确动作**：先用 `easyeda pcb list --include-pads` 找到 J2 的实际对象和 ID，再用 `pcb delete --ids ...` 显式删除；需要时配合 `track-delete` 或 `rip-up` 清掉关联铜，最后重读 `pcb list`、重跑 DRC 并保存证据。删除动作要有回读，不要只依赖会话记录。

**证据/边界与本案例**：28→28 和 J2 仍在是现场事实；手动 delete/track-delete/rip-up 只出现在会话记录里，evidence 目录没有对应输出，因此不能作为已验收证据。不要用 `noChanges:true` 推断“已同步”。本案例 `pcb-import-after-j2-removal.log` 与 `pcb-import-after-usb-removal.log` 记录两次导入。

### 9. JSON/human 混行：`.json` 文件名不可信（G2–G6）

**现象**：`sch-drc.json`、`sch-check-final2.json`、`layout-lint-all.json` 实际是纯文本；`pcb-drc-1.json` 是 JSON 后追加一行 CLI 摘要；`bom-export.log` 是 JSON、人类可读行和 traceback 混在一起。另有截断文件 `pcb-drc-2.json` 2152 bytes、`pcb-nets-after-route.json` 1172 bytes，完整重跑分别为 238706 bytes 和 3848 bytes。

**原因**：CLI 可能先输出 JSON，再追加人类摘要；有些命令本来只输出 human 文本；PowerShell 管道截断或 `Select-Object -First N` 会把数组切在半截；stdout/stderr 合流也会把摘要写进 JSON 文件。

**正确动作**：完整 stdout 先落文件（建议 `> out.json 2> out.err` 分离流），再单独探测格式；解析失败时保留 raw 文件并记录 `format:"text"` 或 `format:"mixed"`，不要让解析器猜。需要结构化证据时，重跑一次并完整落盘，不用被截断的 `-2` 文件补结论。

**证据/边界与本案例**：`gate_check.py` 识别 JSON 优先，也识别 `sch drc`/`sch check`/`pcb layout-lint` 的 human 摘要并标 `format:"text"`；截断或损坏应判 `BLOCKED`，不崩溃。`.json` 只是文件名，不是格式声明。本案例 `round7/baseline/pcb-drc.json` 第 1323 行混入 `pcb drc: native verdict failed; inspect the returned violations`，整份解析失败。

### 10. `outline-fit`：只改板框，不是布局（G3）

**现象**：`outline-fit --margin 100` 的 summary 显示 parts=28、partExtent 3377.55×1976.76、newOutline 3577.55×2176.76、utilBefore 0；有人据此认为布局已经完成。

**原因**：`outline-fit` 只计算并设置板框，器件坐标没有因此移动。`utilBefore:0` 是板框计算前的利用率，不是“板上没有器件”；器件实际移动 9 个来自 `place-constrained`，不是 outline-fit。板框跟随器件 bbox，也不会预留安装孔边距、连接器插拔空间或外壳壁厚。

**正确动作**：需要布局时先跑 `place-constrained` 或人工放置，再 `outline-fit`；完成后读回器件坐标、板框尺寸、孔/开槽与边缘间距。目标尺寸必须来自需求，不能由 fit 出来的宽高反推；板框变更后重新做布局检查和 DRC，不沿用旧的布局结论。

**证据/边界与本案例**：最终板框 3577.55×2176.76 mil = 90.87×55.29 mm，margin 100；`holes: 0` 来自 `pcb-place-constrained-apply.log`，outline-fit 不创建安装孔。outline-fit 不是布局，也不是机械设计验收。本案例板框是器件云 bbox 结果，无安装孔，G3 失败。

### 11. `doc switch`/`reload`/`ready` 与 `--doc`（G5）

**现象**：有人把 `doc switch` 当作保存并重载，或者把 `doc ready` 当作已经打开目标页；改动后回读到的仍是旧页或旧状态。

**原因**：`doc switch` 只把目标文档切到前台；`doc reload` 才执行 save→close→reopen；`doc ready` 只读，不 save/open/switch。全局 `--project` 负责路由，`--doc` 只对 mutating action 生效，并会在 live `document.current` 不匹配时拒绝执行。

**正确动作**：要确认持久化，显式保存后 `doc reload`，再回读文档 UUID、页 UUID、器件和网络；要写某个原理图页或 PCB，给 mutating 动作加 `--doc <uuid|name>` 钉住目标，并用 `doc ls`/live 回读确认。`doc ready` 只用来判断就绪，不产生保存或切换。多窗口下用 `--project` 路由。

**证据/边界与本案例**：`--doc` 的设计目的就是消除“前台页被换掉，修改落到别页”的竞态；不匹配即拒绝，不能绕过。`doc switch` 成功不等于保存成功，`doc reload` 成功也不等于内容正确。本案例 `pcb-list.json`/`pcb-layers.json` 因前台是原理图被拒，错误信息直接建议 `--doc` 或 `doc switch`；import 后带 staleRisk，但尚未留下 reload 回执。

### 12. `sch export-image` 取代已移除的 `sch snapshot`（G2/G5）

**现象**：旧流程还在调用 `easyeda sch snapshot`，升级后命令不存在；或者把原理图导出也当成必须切前台。

**原因**：v1.14.0 已移除 `sch snapshot`，由 `sch export-image` 取代；原理图导出在后台可以执行，和 PCB 的 `pcb snapshot` 不是同一套前台约束。

**正确动作**：用 `easyeda sch export-image --format svg|png|pdf`，按需要加 `--ids`、`--scope selection|page|project`、`--page`、`-o out`；导出后实际打开图检查整页与局部。不要把旧命令名写进脚本或证据。

**证据/边界与本案例**：`sch export-image` 明确无前台要求；`pcb snapshot` 仍有前台要求。两者不要混写，也不要把 PCB 截图当作原理图导出。本案例 `sch-export-png.log` 在 `pageVisibility:hidden` 下成功导出 531083 bytes。

### 13. `layout-lint --gate`：历史阈值不是布线门禁（G3）

**现象**：把 `pcb layout-lint --gate` 的返回当成“可以布线”的授权，或者看到旧阈值通过就跳过布局检查。

**原因**：`--gate` 已废弃，只显示历史阈值，不授权、不阻断布线。真正的判定要看 score、verdict、crossings、overlap、off-board 等输出，以及 Skill 侧的 G3/G4 证据。

**正确动作**：用 `easyeda pcb layout-lint --json` 读取完整结果，按默认门槛 score≥60、crossings≤8 以及 0 overlap/off-board 判断；不满足时先改布局，或按证据记 `BLOCKED`/`PASS_WITH_WAIVER`，写明理由、条件和剩余风险。不要用 `--gate` 的旧阈值放行。

**证据/边界与本案例**：本轮实测 `score 48/100 (hard)`、28 comps、0 short/0 overlap/0 off-board/0 tight、13 signal nets、ratsnest 17073 mil、13 crossings；按默认门槛并不通过。CLI 不替 Agent 做门禁结论，门禁也不是审批。本案例证据 `pcb-layout-lint-2.log`。

### 14. `net-path`：只证明 listed routed copper（G4/G5）

**现象**：`pcb net-path` 对 GND 或电源网络失败，就被写成“整板断连”；或者反过来，把一次成功当成全板连通证明。

**原因**：`net-path --from D.PAD --to D.PAD` 只检查列出的 routed copper，铺铜、内电层和 filled regions 不计入。失败只说明没有被走线证明，不代表没有铺铜连通。

**正确动作**：信号关键网用 `net-path` 逐条证明；GND/电源先看 `pour-list`、`pcb check` 的 `power-not-poured`、DRC Connection 和实际填充几何。失败时补 track、修铺铜或换用能覆盖该对象的证据，再重跑；不要只凭一次 net-path 失败就重做全板。仅靠铺铜连接的 GND 不要放进 `key_nets` 的 net-path 清单。

**证据/边界与本案例**：`net-path` 的输出边界来自命令定义；它的成功和失败都只覆盖 listed routed copper。要在报告中写明“走线已证明”还是“铺铜未覆盖”，两者不能互相替代。本案例 GND 靠双层铺铜加 44 段 GND 线；G5 最终 DRC 仍有 2 条 Connection（+5V）。

### 15. Gerber/钻孔/CPL：v1.14.0 没有 CLI（G6）

**现象**：在 CLI 里找不到 Gerber、钻孔文件或 CPL/pick-place 命令；有人尝试用历史命令或临时脚本补一个“导出成功”。

**原因**：v1.14.0 没有这些 CLI/typed action。Gerber 的官方 API `eda.pcb_ManufactureData.getGerberFile` 仍标 @beta、未包装；钻孔文件没有 CLI；坐标文件 CPL 也没有 CLI/typed action。

**正确动作**：由用户在 EDA GUI 中导出 Gerber、钻孔和 CPL，保存到证据目录，记录导出时间、工程版本和文件哈希；`gate_check` 把这些子项标 `UNSUPPORTED` 并放进 `not_checked`，缺证据时 G6 为 `BLOCKED`。Agent 可以继续做不依赖这些文件的检查，不新增等待点，但不得宣称 G6 已通过。

**证据/边界与本案例**：`UNSUPPORTED` 不等于 `PASS`，也不等于 `PASS_WITH_WAIVER`；只有写明理由、条件和剩余风险才可豁免。G6 通过也不等于可量产，报告要给出交付级别和证据范围。本案例 G6 因缺 Gerber/CPL/恢复演练 BLOCKED。

### 16. `sch drc` 与 `sch check`：两层证据，不能互相替代（G2）

**现象**：`sch drc` 报 0，就认为原理图“完全无问题”；或者 `sch check` 报一批 WARN，就认为 DRC 失败。

**原因**：`sch drc` 走官方 SDK，可能只返回布尔/聚合结果，退出码只在 fatal（error+fatal）>0 时非零；`sch check` 从图元与官方制造网表重建逐项发现，覆盖浮空脚、网标/导线网名不符、多网导线、交叉、压脚、零长线、悬空线以及风格/结构问题。两者的规则层和证据角色不同。

**正确动作**：G2 同时要求两项：`sch drc --json` 的 fatal/error=0；`sch check --json` 的电气类发现=0。风格/结构类（marker-overlap、out-of-sheet、missing-partition、peripheral-not-direct 等）修复或带理由豁免。把两份完整输出分别落盘，报告里分别引用。

**证据/边界与本案例**：`sch drc` 的 warn 不影响退出码，不能拿退出码 0 当“无警告”；`sch check` 默认也是 0 退出，必须看 findings 分类或加 `--strict`。本案例 `sch-drc.json` 0 违规，`sch-check-final2.json` 10 条发现（1 marker-overlap、1 out-of-sheet、2 designator-wire-overlap、1 missing-partition、5 peripheral-not-direct）。

### 17. `peripheral-not-direct`：同名网标不是直连（G2）

**现象**：`sch check` 报 `peripheral-not-direct`，但 DRC 为 0、`sch nets` 也显示网络正常；容易被当成误报。

**原因**：同名网标只保证“网名相同”，不保证“实际导线直连”。模块重建/整理工具把每个模块核心与外围之间的连接判为 physical wire islands；帮助原文明确“supply/ground connectivity and same-name labels cannot replace this branch — 同名标签不算直连”。

**正确动作**：动笔前先定风格。要直连就用实际导线重建（按输出提示走 `sch lib-layout` → `sch compose --preserve-instances`，或手工梳理）；要网标风格就在 `design-state.json`/豁免记录里写 `peripheral-not-direct`，注明范围、理由与复验证据（DRC + 网表逐针）。不要在两种风格之间反复切换，也不要反复重跑要求直连的工具。

**证据/边界与本案例**：`sch nets` 是全工程网表审计（同轨异名、单引脚网），它看不到“标签代替直连”；网表通过不等于直连通过。本案例 `sch-check-final2.json` 报 J1、C1、RV1、U1、Q1 共 5 条 peripheral-not-direct；`sch-nets.json` 同时报 14 张网、0 单引脚网。G2 预期为 `PASS_WITH_WAIVER` 的前提正是这 5 条有带理由的豁免，而不是“没有警告”。

### 18. `staleRisk`：保存重载后才算证据（G4/G5）

**现象**：PCB mutation 之后立刻读 `pcb.via.list`、`pcb.components.list`、`pcb drc`，回执顶层带 `staleRisk`，数据却是修改前的状态；有人直接拿它写报告。

**原因**：写操作之后宿主枚举/引擎状态可能还没刷新；CLI 用 `staleRisk` 提示“该读取可能来自旧状态”，但不会拒绝读取。即时结果可用于定位明显差异，不能作为最终约束证据。

**正确动作**：`pcb save` → `easyeda doc reload --json` → 重新读取（vias/list/DRC/pour）。reload 回执要核对文档 UUID 与 `activeRestored`；刷新失败时按数据不可用处理，不沿用旧回执。把带 staleRisk 的即时文件另存为诊断，不要和最终证据混在一起。

**证据/边界与本案例**：`gate_check.py` 对带 `staleRisk` 的 via 证据直接判 G4 失败；不要手工删除 staleRisk 字段来“通过”。本案例 `pcb-vias-4.json` 在 `route.delete` 后带 staleRisk；`pcb-import-after-usb-removal.log` 在 import 后也带 staleRisk，而 evidence 中没有对应的 reload 回读，因此 G5 的 save_reload 仍缺证据。

### 19. `layout-lint`：只判器件本体，丝印另算（G3/G5）

**现象**：`pcb layout-lint` 分数及格、0 overlap/off-board，就认为布局可读可装配；但丝印位号压在焊盘上、标签互相重叠、器件被丝印外框挤在一起。

**原因**：`layout-lint` v1 是器件 bbox 级近似，只判 overlap/off-board/tight-spacing/ratsnest/crossings；它复用 `pcb check` 的 `silk-over-pad`/`silk-off-board` 放在报告的 `silk` 段，只给 WARN、不计分。标签-标签、标签-器件的重叠不在它的判定范围；原理图侧的标签重叠还要另跑 `sch clusters`。丝印或板框读不到时它会写 `silkUnchecked`，不能当作通过。

**正确动作**：把丝印问题当独立项，用 `pcb silk-align`/`pcb silk-set` 修复并回读；原理图标签重叠另跑对应检查；最终以实际 PNG/渲染图检查整页与局部。G3 的布局分数和 G5 的丝印证据分别记录，不能用一个分数覆盖。

**证据/边界与本案例**：分数高不等于可读可装配；`silk-over-pad` 在 G5 仍可能让门禁失败（可豁免项）。本案例 `pcb-layout-lint-2.log` 报 4 条 silk-over-pad；`pcb-check.json` 另报 2 条 silk-over-pad 与 2 条 silkscreen-flipped；`layout-lint-all.json` 是原理图版，自述只判器件本体，标签重叠不在其中。

### 20. `pcb check --strict`：DFM 不等于 DRC（G4/G5/G6）

**现象**：`pcb check` 0 退出就认为制造检查通过；或者 `--strict` 非零退出后把它和 `pcb drc` 的失败混为一谈。

**原因**：`pcb check` 是重建 DFM 审计（dangling-end、acute-angle、overlapping-via、single-layer-via、width-mismatch、duplicate-segment、parallel-coupling、netless-pour、via-crosses-plane、floating-track-island、power-not-poured、width-under-spec、silk-over-pad、decap-too-far、via-in-pad、fiducial-missing 等），默认信息模式 0 退出；`--strict` 才把 WARN/ERROR 变成非零。它与 `pcb drc`（规则间距/连接）是不同规则集。

**正确动作**：分层记录：`pcb drc` 管 clearance/连接；`pcb check` 管 DFM 与可制造性。报告分别列 ERROR/WARN/INFO、修复项与豁免项；0 退出只代表信息模式没报错，不是 DFM 全证明。丝印、去耦距离、过孔在焊盘上等 WARN 要修或带理由豁免。

**证据/边界与本案例**：两套检查的数字不能互相替代；`--strict` 的非零退出不能直接当 DRC 失败。本案例 `pcb-check.json` 40 issue（ERROR=13、WARN=17，其余 INFO）加 power-not-poured；同板 `pcb-drc-11.json` 18 条（16 Clearance、2 Connection）。

### 21. `project export`：导出与恢复演练分开（G6）

**现象**：`project export` 报缺参数；或者看到 `.epro2` 已生成、`zipIntegrityVerified:true`，就认为工程可恢复。

**原因**：命令要求显式 `--out <新文件>` 与 `--project-uuid <uuid>`，且不覆盖已有文件；`restoreVerified` 只有在副本上重开、核对工程/页/器件后才可能为 true，导出动作本身不做恢复演练。

**正确动作**：先保存文档再导出；把 `zipIntegrityVerified`（zip 完整）与 `restoreVerified`（恢复演练）分开记录。恢复演练在副本上打开 `.epro2`，核对工程 UUID、页 UUID、器件清单、网表与关键网络，再写 `restore_verified:true`。缺参时按 `--help` 补齐，不猜参数。

**证据/边界与本案例**：`restoreVerified:false` = 未演练，G6 的 `epro2_restore` 直接失败且不可豁免；zip 完整不等于可恢复。本案例 `project-export.log` 报 `explicit --window and --project-uuid are required`；`project-export-2.log` 导出成功（364810 bytes，`zipIntegrityVerified:true`）但 `restoreVerified:false`。

## apply 的 no-op 与 journal 状态

`pcb_apply_plan.py` 会把目标 pose 等于实测 pose 的 place 记入 `plan.noops`，不生成写入步骤；全部为 no-op 时 `status=no_op`，不写 playbook、不调用 CLI。不要为了“看起来执行过”重跑一个 no_op 计划。

`--apply` 后 journal 每步只有 `planned`、`sent`、`confirmed`、`failed`、`unknown` 五种状态；`confirmed` 的 status 以 ok 开头，`unknown` 表示已发出但无确认。**`unknown` 不是成功**：报告 `recovery.safe_to_retry=false`，必须先取 fresh dump 看实际状态，再只补差异。`report`/playbook 原子写入；不要读取或继续使用半份 JSON。适配器没有事务回滚，不要宣称“失败自动回滚”。

## 什么时候不要重试

- **DRC 超时但 PCB 仍在后台**：不要重跑，先切前台；重复执行只会重复超时。
- **`pcb snapshot` 返回 `PRECONDITION_REFUSED`**：不要对同一个 hidden tab 再抓，先切前台或改走 dump/几何证据。
- **`sch check` 报活动文档不可用**：不要重复同一条命令，先切目标页或加 `--page`。
- **`sch check` 返回 shallow data**：不要把空 pins/bbox 当结果，也不要靠重复执行“等它变全”。
- **`import-changes` 返回 `noChanges:true` 但对象仍在**：不要重跑，显式删除并回读。
- **`apply`/`import` 返回 partial 或 `ok:false`**：不要整批重放，先读实际状态再补差异。
- **回执带 `staleRisk`**：不要继续引用该数据；`save` → `doc reload` → 重新回读。
- **`bom-enrich.py` 抛 `TypeError`**：不要原样重跑，改用 `--enrich=false` 或修源数据。
- **`zone-arrange` 同一断言连续失败**：不要重复同一 plan，先处理无标记直连或改用手工路径。
- **JSON 解析失败或文件明显截断**：不要猜字段，也不要拿半截数组统计，完整重跑一次。
- **`layout-lint` 分数不够**：不要用 `--gate` 历史阈值绕过，先改布局或记录 `BLOCKED`/`PASS_WITH_WAIVER`。
- **`route-short --route-power` 后 DRC 暴增**：不要继续加 `--route-power` 覆盖，先撤掉这些 track 或改铺铜策略。
- **`net-path` 失败**：不要直接判整板断连，先查铺铜/内电层和 DRC。
- **`pcb check` 0 退出**：不要当 DFM 通过，读报告内容并分层记录。
- **`project export` 的 `restoreVerified:false`**：不要当恢复演练完成，副本重开后再写结论。
- **Gerber/钻孔/CPL 找不到命令**：不要搜索或编造 CLI，改走 GUI 导出并标 `UNSUPPORTED`。

## 证据落盘

- **完整输出先落文件**：stdout 和 stderr 都写文件（建议 `> out.json 2> out.err` 分离流）；不要用 `Select-Object -First N` 截断 JSON 数组。
- **记录命令上下文**：命令行、工作目录、easyeda-agent 版本、EDA Pro 版本、工程/页 UUID、开始与结束时间、退出码、窗口可见性。
- **记录格式**：每个证据文件标明 `json`、`text` 或 `mixed`；解析失败保留 raw，不要覆盖。
- **DRC 证据**：保留完整 `--json`，包括 `passed`、`total`、`counts`、`nativeResult` 和全部 violations；不要只留一句“0 fatal”。
- **写入证据**：保留 before/after 对象和计数、实际 ID、逐项回读结果；`verified:true`、`noChanges:true` 都不能单独作为结论。
- **staleRisk 证据**：即时读取单独保存并标 `staleRisk`；最终约束证据必须是 save → doc reload → fresh readback。
- **图像证据**：保存实际导出文件，记录格式、尺寸和 SHA-256，并实际看图；截图不能证明铺铜填充、开槽或底层连接。
- **BOM 证据**：保留原始 CSV、enrichment 日志、C 号核对结果；enrichment 失败要保留 warning，不要用后处理覆盖原始文件。
- **不支持项**：在证据里明确写 `UNSUPPORTED`、缺失文件、GUI 导出路径和用户操作结果；缺证据时门禁保持 `BLOCKED`。
- **文件名不等于格式**：`.json` 可能包含人类行或 traceback；先探测，再解析。

## 与 `eda-execution.md` 的分工

本文件只写单个动作的现场陷阱：前台/活动页要求、超时与重试、返回格式、已废弃动作和不支持项。能力矩阵、工程可写探针、先读后写的对账、`apply`/verify/reopen、保存与重开、会话来源控制，仍按 [eda-execution.md](eda-execution.md) 执行。

工程习惯分别看 [pcb.md](pcb.md) 与 [schematic.md](schematic.md)；用户可见的定位与下一步表达看 [troubleshooting.md](troubleshooting.md)；证据分层与最小记录看 [evidence.md](evidence.md)。两边说法不一致时，执行前以当前 `--help`、live 回读和实际窗口状态为准，不用旧记忆覆盖现场事实。
