# 阶段门禁：G0–G6

> 本文定义 G0–G6 阶段退出证据门禁。阶段本身（S0–S5）与五状态词以 [SKILL.md](../SKILL.md) §4 为准；工程推进叙事见 [工程工作流](workflow.md)；证据记录纪律见 [证据与工程记录](evidence.md)。本文只补“离开一个阶段前，用什么证据证明它真的完成了”。

## 1. 定位与边界

门禁是**阶段退出证据门，不是审批门**。Agent 在用户已授权的设计/修改范围内自查、记录并继续；门禁不新增等待点，也不要求用户逐项签批。只有用户明确说“先评审 / 这步给我看 / 确认后再布线”时，才在方案、原理图、布局、交付四个可见检查点等待。

- 门禁失败只暂停依赖链路，其余工作继续（与 [工程工作流](workflow.md) S1 的“只暂停依赖部分”一致）。例如 G4 因铺铜策略未定而 BLOCKED 时，原理图修正与 BOM 整理照常进行。
- 门禁不是质量总分，也不替代实测。`PASS` 只说明列出的检查在给定对象、版本、范围内通过；没有覆盖的内容仍是 `待确认`。
- 门禁可在离线证据上复核：`gate_check.py` 只读证据目录，不连 daemon、不写工程、不代替 Agent 执行检查。
- 每个门禁的“通过”都有范围。G6 通过也只说明制造资料达到当前交付级别，不代表样机功能、可靠性或量产验证。
- 只做只读评审、纯资料分析或知识问答时，不新建 `design-state.json`、不要求补证据；按现有证据报告门禁状态并标 `NOT RUN`，不把未执行的检查写成通过。

## 2. G 与 S 的固定映射

G 编号不是第二套流程，而是 S0–S5 的退出条件。映射固定如下，不按项目另立顺序。

| 门禁 | 状态文件中的键 | 对应阶段 | 执行时机 | 通过后的允许动作 |
|---|---|---|---|---|
| G0 需求边界 | `G0_requirements` | S1 退出 | 需求摘要与状态文件建立后 | 进入 S2 方案与核算 |
| G1 功能冻结 | `G1_function_freeze` | S2 退出 / S3 进入前 | 方案、关键选型、电源树确定后 | 开始或继续画原理图 |
| G2 原理图完成 | `G2_schematic` | S3 退出 / S4 进入前 | 原理图保存并回读后 | 导入 PCB、开始布局 |
| G3 布局完成 | `G3_layout` | S4 内，布线前 | 板框与器件放置确定后 | 开始布线；与 G4 并列 |
| G4 电源地策略 | `G4_power_ground` | S4 内，布线前 | 层叠与铺铜/平面策略确定后 | 开始布线；与 G3 并列 |
| G5 布线完成 | `G5_routing` | S4 退出 | 布线、铺铜、丝印整理后 | 进入 S5 交付检查 |
| G6 制造交付 | `G6_manufacturing` | S5 | 制造资料与 BOM 准备后 | 报告交付级别与证据范围 |

G3 与 G4 是并列前置条件：布线必须在两者都满足后开始，不能先布完再补声明。任何一门禁失败后，依赖它的下游动作（如 G3 未过就 `route-short`）属于越门禁操作，即使工具能执行也不构成通过。

### 2.1 四结论词与五状态词

`gate_check.py` 输出四个门禁结论；工程记录沿用 SKILL.md §4 的五个状态词。两者按下表对应，不另造“部分通过”。

| 门禁结论 | 判定含义 | 对应五状态词 | 记录要求 |
|---|---|---|---|
| `PASS` | 所有必需检查通过，未被覆盖项已列明 | `已验证` | 写明方法、对象、版本、范围 |
| `BLOCKED` | 已证实违反，或缺可判定证据 | `不满足`（已证实）或 `待确认`（证据缺失） | 给出违反项或缺失项与 `next_command` |
| `PASS_WITH_WAIVER`（正文简称 `WAIVED`） | 无未处理失败，但有失败/警告被带理由的豁免覆盖 | `有条件满足` | 写明理由、范围、剩余风险、复验条件 |
| `UNSUPPORTED` | 当前 CLI 无检查路径，且没有可接受的人工证据 | `待确认` | 进入 `not_checked`，不得按 `PASS` 处理 |

单项检查在报告里是 `pass` / `fail` / `warn` / `waived` / `unsupported`；门禁结论由这些单项聚合，不能拿单项 `warn` 冒充门禁 `PASS`。`warn` 默认不阻塞，`--strict-advisory` 可把它升级为失败。

## 3. 门禁总览

| 门禁 | 对应阶段 | 阻塞条件（一句话） | 主要命令（v1.14.0） | 证据角色 | 不适用条件 |
|---|---|---|---|---|---|
| G0 需求边界 | S1 | 12 个需求字段缺失/`待确认`，或存在 blocking open item | `gate_check.py --design-state` | `design-state.json` | 只读评审或纯知识问答，不进入设计 |
| G1 功能冻结 | S2→S3 | 未冻结、必需件为空，或冻结后增删无 change-impact 文件 | `gate_check.py`；`easyeda pcb import-changes` | `design-state.function_freeze`、`change-impact.md` | 只读评审，不修改工程 |
| G2 原理图完成 | S3→S4 | `sch drc` fatal/error>0、电气类 check>0，或网表/图签/看图证据缺失 | `easyeda sch gate --json`；`sch drc/check/netlist/export-image` | `sch_drc`、`sch_check`、`netlist_diff`、`schematic_png` | 仅 PCB 任务且原理图基线未改；复用基线证据须标日期与版本 |
| G3 布局完成 | S4 布线前 | score<60、crossings>8、overlap/off-board>0，或板框/安装孔/冻结缺失 | `easyeda pcb layout-lint --json`；`outline-get`；`mount-holes --dry-run`；`pcb dump` | `pcb_layout_lint`、`pcb_board`、`pcb_mount_holes` | 只交付原理图，不进入 PCB |
| G4 电源地策略 | S4 布线前 | 层数与板不符、策略未在布线前声明、GND 未铺、过孔未审计 | `pcb stackup show`；`power-pour`；`pour-list`；`via-list`；`pcb check` | `pcb_pours`、`pcb_vias`、`pcb_board`、`pcb_check` | 无 PCB 任务；进入 S4 后不能整门禁跳过 |
| G5 布线完成 | S4 退出 | `pcb drc` 未 `passed:true` 或仍有 Connection、关键网未证明、保存重载无回读 | `pcb drc --json`；`net-path`；`doc reload`；`silk-align` | `pcb_drc`、`net_path`、`reopen_check`、`silk_align` | 用户只要求布局，交付级别写“PCB 候选（未布线）” |
| G6 制造交付 | S5 | Gerber/钻孔/CPL 缺证据、BOM 缺 C 号、库存/SMT 未核、恢复演练未做、无测试计划 | `bom export`；`project export`；制造文件由 GUI 导出 | `gerber`、`drill`、`cpl`、`bom`、`project_export` | 交付级别止于 PCB/DRC 0；交付说明仍须写 G6 `NOT RUN` |

## 4. 通用判定规则

1. **证据优先 JSON，也接受人读摘要。** `sch drc`、`sch check`、`pcb layout-lint` 的 `--json` 输出优先；若只有 human 摘要，解析器标 `format:"text"` 并按摘要行计数。JSON 解析失败但内容像 JSON（`invalid_json`）、文件截断或字段缺失时，对应检查判 `BLOCKED`，不猜测内容、不崩溃。
2. **每条结论绑定证据身份。** `pcb_gate.py`/`pcb_case.py` 的 PCB case 报告为每个结论记录 `path / sha256 / semantic_sha256 / mtime / freshness_basis / format / candidates / selected_because`；同一角色有多个候选时优先 `*-final*` 且可解析者并写明理由，项目/页身份冲突不静默择一。证据早于最终板框或组件数不一致时标 `STALE_EVIDENCE`，不得作为 `PASS` 依据；回执带 `staleRisk` 时只作警告，需 save → reload → fresh readback。case 目录有 `manifest.json` 时以其 `sha256/source_dump_sha256/produced_at` 为绑定依据；文件缺失不回退，哈希/源 dump/项目身份不一致即 `EVIDENCE_BINDING` 失败。只有 mtime 时在 `not_checked` 标 `freshness_basis`，复制旧文件改时间不恢复内容绑定。`gate_check.py` 的 G0–G6 仍只按自身证据发现规则（形状+文件时间）工作，不声称已实现上述 manifest/semantic 绑定；PCB case 交付以 `pcb_gate.py` 为准。
3. **advisory 不是豁免。** 默认警告只记录并在报告中列出；`--strict-advisory` 提升为失败。`pcb layout-lint` 的 tight spacing、orphan stub、非致命 DRC 属建议项，不能因为“只是警告”就写进 `not_checked` 之外当已处理。
4. **豁免必须落盘。** 豁免写在 `--waiver GATE[:CHECK]:REASON` 或 `--waiver-file`（`design-waivers/v1`）；`reason` 少于 4 个字符或只有“忽略/暂时”之类无信息文本时不生效。豁免只覆盖 `waivable` 检查；电气 DRC、网表审计、PCB DRC、关键网证明、保存重载、Gerber/BOM/恢复演练等不可豁免。使用豁免后门禁至少为 `PASS_WITH_WAIVER`；未使用的豁免在报告中标 `unused`。`design-state.waivers` 只是项目记录，不参与当前脚本判定。
5. **`UNSUPPORTED` 必须显式列出。** 当前 CLI 没有检查路径的项不能默认通过，也不能静默删除；写入 `not_checked` 并给出人工证据要求。缺人工证据时，所在门禁整体 `BLOCKED`。
6. **缺证据就是 `BLOCKED`，不是 `PASS`。** 未运行、未导出、未回读的检查保持 `待确认`；报告写 `NOT RUN`，不写“应该没问题”。
7. **退出码。** `gate_check.py`：`0` = 没有 `BLOCKED`/`UNSUPPORTED`；`1` = 至少一个 `BLOCKED`/`UNSUPPORTED`；`2` = 参数、IO 或 `design-state` schema 错误。退出码 0 只说明脚本判定，不证明硬件。

## 5. G0_requirements 需求边界

**目的：** 在画图前把会改变拓扑、板框、装配和验收的需求固定下来，避免用工具输出反推需求。

**必需输入：** 对话、参考工程、外壳/结构资料、既有 BOM 与用户约束；写入 `design-state.json` 的 `requirements`。模板见 [需求摘要](../assets/design-brief.md)。

| check id | 判定 | 命令 | 证据 | 通过条件 | 不支持时 |
|---|---|---|---|---|---|
| `design_state` | 文件存在且可解析 | `python scripts/gate_check.py --evidence-dir <dir> --design-state <file>` | `design-state.json` | `schema` 为 `design-state/v1` | 缺文件或 schema 不符 → `BLOCKED`；先复制 [示例状态文件](../assets/design-state.example.json) |
| `requirements_section` | 结构 | 同上 | `requirements` 对象 | 存在且为对象 | 缺失 → `BLOCKED` |
| `req_delivery_level`、`req_size_limit`、`req_enclosure_mounting`、`req_assembly`、`req_quantity_budget`、`req_usb_role`、`req_test_points`、`req_display`、`req_firmware`、`req_threshold_interaction`、`req_alarm_behavior`、`req_environment_accuracy` | 逐字段 | 同上 | `requirements.<key>` | 标量/数组/对象视为已确认；`not_applicable` 必须带 `reason`；`assumed` 必须带 `assumption`/`source` | `pending`、空值、空列表或未知 status → `BLOCKED` |
| `blocking_open_items` | 列表 | 同上 | `open_items` | 没有 `blocking:true` 的未决项 | 未记录 `open_items` 时只给 advisory `warn` |
| `assumptions`、`risks` | 列表 | 同上 | `assumptions`、`risks` | 至少记录一条，或项目确实无假设/风险并说明 | 缺失只给 advisory `warn`，不阻断 |

前六个字段（`delivery_level`、`size_limit`、`enclosure_mounting`、`assembly`、`quantity_budget`、`environment_accuracy`）是不可豁免的物理/合同边界；其余字段可带理由豁免，但豁免后仍记 `PASS_WITH_WAIVER`。

**退出条件：** 12 个字段全部有值、`not_applicable` 带理由、没有 blocking 未决项。满足后 Agent 直接进入 S2，无需用户签批。

**豁免规则：** 只有非物理边界字段可豁免；豁免理由要说明“为什么该值不影响当前交付级别”。`size_limit` 或 `assembly` 未定不能靠豁免放行。

**真实反例：** 温度报警板复盘没有 design-brief，最终板框 3577.55 × 2176.76 mil（90.87 × 55.29 mm）是 `pcb outline-fit --margin 100` 的结果（`utilBefore 0`、`parts 28`），不是需求上限；`holes: 0`；装配方式未定，器件却混用 0402（R1、R2、R11、R12、R14、R15、R17）与直插 RV1、BZ1。若 G0 先执行，这些字段会在画图前被问清或显式标不适用。

## 6. G1_function_freeze 功能冻结

**目的：** 固定必需件与可选件，防止“先画后删”让原理图、PCB、BOM 和网表分叉；冻结后的每一次增删都要有影响分析。

**必需输入：** 方案与关键选型、电源树、功能清单；写入 `function_freeze`，冻结后增删记录 `removed_after_freeze` 或 `changes` 并附 `change_impact` 文件。

| check id | 判定 | 命令 | 证据 | 通过条件 | 不支持时 |
|---|---|---|---|---|---|
| `frozen` | 状态 | `python scripts/gate_check.py --evidence-dir <dir> --design-state <file>` | `function_freeze.status` | `frozen` 或 `frozen_with_changes` | 其他值 → `BLOCKED`（不可豁免） |
| `required_parts` | 列表 | 同上 | `function_freeze.required` | 非空 | 空或缺失 → `BLOCKED` |
| `change_impact` | 逐项文件存在 | 同上；变更影响可用 `python scripts/decision_record_check.py` 复核记录结构 | `removed_after_freeze[].change_impact`、`changes[].change_impact` | 每个冻结后增删都有存在的 `change-impact.md` | 缺失、文件不存在或无 impact → `BLOCKED` |
| `reimport`（G1 证据，非独立 id） | 回读 | `easyeda pcb import-changes --schematic <uuid>`；`easyeda pcb list --include-pads`；`easyeda pcb net-path` | `pcb-list-*.json`、`netlist-diff.json` | 原理图删除件在 PCB 中确实消失，网表一致 | 只跑导入不回读 → 仍 `待确认` |

**退出条件：** 冻结状态成立、必需件非空、冻结后每项变更都有影响记录且重新导入已回读。满足后进入 S3。

**豁免规则：** 冻结状态、必需件清单和 change-impact 均不可豁免；`frozen_with_changes` 不是豁免，它要求变更记录齐全。

**真实反例：** 15:37 首次导入 28 件（含 J2、D2），J2 到 15:45、D2 到 15:48 才删。删 J2 后 `pcb import-changes` 返回 `noChanges:true`（28→28），`pcb-list-after-j2.json` 仍含 J2，`pcb-drc-5.json` 报 `PCB and schematic netlist does not match`；手动 delete/track-delete/rip-up 只在会话记录里，evidence 目录没有输出。冻结后删除若没有 change-impact 与重新导入证据，G1 必须 `BLOCKED`。

## 7. G2_schematic 原理图完成

**目的：** 证明原理图电气连接成立、图面可读、网表与设计意图一致，再进入 PCB。

**必需输入：** 已保存并回读的原理图；计划网表与实际网表；整页导出图；图签信息。适用检查提示见 [原理图细节](schematic-details.md) 的 SC 条目与 [原理图工程习惯](schematic.md)。

| check id | 判定 | 命令（v1.14.0） | 证据 | 通过条件 | 不支持时 |
|---|---|---|---|---|---|
| `sch_drc_electrical` | 计数 | `easyeda sch drc --json > evidence/sch-drc.json` | `sch_drc`（JSON 或 human 摘要） | fatal=0 且 error=0；warn/info 记录 | 缺证据、截断或 `invalid_json` → `BLOCKED` |
| `sch_check_electrical` | 电气类计数 | `easyeda sch check --json --page <page> > evidence/sch-check.json` | `sch_check` | floating pin、net-marker/wire-name mismatch、multi-net wire、wire crossing、wire-over-pin 等电气类为 0 | 目标页非 active 时报 `Active schematic document instance is unavailable`；先 `--page` 或 `doc switch`，不能当作通过 |
| `style_warnings` | 风格/结构类计数 | 同上 | `sch_check` | 0，或逐条修复/带理由豁免 | 非空且未豁免 → `BLOCKED`（可豁免） |
| `netlist_audit` | 网表 diff | `easyeda sch netlist --type protel` 导出计划与实际网表；`python scripts/netlist_diff.py before.net after.net --output netlist-diff.json` | `netlist_diff` | `status=match`；电气修订只允许逐条白名单差异 | `invalid` 或缺一侧网表 → `BLOCKED`，不能当审计通过 |
| `single_pin_nets` | 单引脚网 | `easyeda sch nets --all --json --strict > evidence/sch-nets.json` | `sch_nets` | 0 个单引脚网 | 缺失或不可判定 → `BLOCKED`（可豁免）；单脚网可能是漏连，也可能是测试点，需逐条解释 |
| `titleblock` | 图签 | `easyeda sch titleblock-get --page <uuid>` | 状态记录或 `sch_check` 分类 | 板名、版本、图签完整；无 missing-titleblock/titleblock-overlap | 缺失 → `BLOCKED`（可豁免） |
| `png_review` | 看图 | `easyeda sch export-image --format png --scope page --page <page> -o <file>` | `schematic_png` + `schematic.png_review` | 实际看过整页与关键局部，记录遮挡/歧义/绕线问题 | 只有 DRC 没有导图 → `BLOCKED`（可豁免） |
| `net_naming` | 风格 | 阅读原理图与网表 | `schematic.net_naming` | 功能网名有语义（如 VBUS/CC1/CC2/NODE/VREF/GATE/BUZ_D） | 缺失只给 advisory `warn` |

`easyeda sch gate --json [--strict] [--all-pages]` 是组合入口，固定顺序 layout-lint → check → bridge-check → drc，三态 verdict 为 `pass`/`fail`/`blocked`；阻塞规则是 layout-lint overlap/pin-coincidence、check fatal+error、bridge-check bridge、drc fatal。组合命令方便一次跑完，但每个子项的证据仍要落盘，不能用一行 `pass` 代替。

**退出条件：** DRC 0 fatal/0 error、电气检查 0、网表 match、单引脚网已解释、图签与看图记录存在；风格警告已修复或豁免。满足后导入 PCB。

**豁免规则：** 电气 DRC、网表审计不可豁免；单引脚网、图签、看图、风格警告可豁免，但要在豁免里写清哪条、为什么、何时复验。同名网标签不是实际导通的证据，不能靠改名消除检查项。

**真实反例：** 最终 `sch check` 10 findings，`peripheral-not-direct` 5 条（J1、C1、RV1、U1、Q1），不是 4 条；0 floating pin。它们属风格/结构类，必须修复或带理由豁免，不能写成“0 告警”。D5 曾反接：`page-d5-check.json` 中 `pin2 K = PWR_LED_A`、`pin1 A = ""`，修正后才为 `pin2 K = GND`、`pin1 A = PWR_LED_A`。C1 pin1 经普通导线直连、树上无标记（`zone-arrange-apply.log` 原文），补 netport 重试仍失败（`zone-arrange-apply-3.log`）；“工具不认 net-label”只是从 term 模型推断，不是日志原话。

## 8. G3_layout 布局完成

**目的：** 在布线前证明板框、安装、连接器逃逸和可布性达到项目阈值，并冻结布局；避免用布线去掩盖布局问题。

**必需输入：** 目标板框与尺寸上限、安装孔要求、连接器位置、器件放置结果；`pcb dump`（含 components/outline/copper）与 `pcb layout-lint`。

| check id | 判定 | 命令（v1.14.0） | 证据 | 通过条件 | 不支持时 |
|---|---|---|---|---|---|
| `layout_lint_score` | 阈值 | `easyeda pcb layout-lint --json > evidence/pcb-layout-lint.json` | `pcb_layout_lint` | score ≥ 60（可用 `--min-layout-score` 调整） | 缺证据或解析失败 → `BLOCKED`；原理图 layout-lint 不算 |
| `layout_lint_crossings` | 阈值 | 同上 | `pcb_layout_lint` | crossings ≤ 8（可用 `--max-crossings` 调整） | 同上 → `BLOCKED` |
| `layout_lint_geometry` | 计数 | 同上 | `pcb_layout_lint` | overlap=0、off-board=0、short=0；tight 只作 advisory | 任一几何错误 → `BLOCKED`（不可豁免） |
| `board_outline` | 尺寸 | `easyeda pcb outline-get > evidence/pcb-outline.json`；`easyeda pcb dump --out evidence/pcb-board.json` | `pcb_board` | 实际宽高不超过 `layout.board_outline` 或 `requirements.size_limit` 的目标 +0.5 mm | 目标未记录 → `BLOCKED`；不能用 `outline-fit` 反推目标 |
| `mounting_holes` | 记录/回执 | `easyeda pcb mount-holes --dry-run > evidence/pcb-mount-holes.json` | `pcb_mount_holes` | 数量/孔径/内缩已记录，或 `not_applicable` 带理由 | 无记录 → `BLOCKED`（可豁免）；该命令铣 BoardCutout，不是导入安装孔器件 |
| `connector_escape` | 距离/禁布 | `easyeda pcb dump --out board.json`；`easyeda pcb list --include-pads` | `layout.connector_escape` | 接口无源件（CC/VBUS/TVS/ESD）距连接器 ≤5 mm，且避开 slot 禁布 | 板上有连接器但未记录 → `BLOCKED`（可豁免） |
| `auto_place_comparison` | 前后对比 | `easyeda pcb auto-place` 前后各跑一次 `layout-lint` | `layout.auto_place_metrics` | 记录 before/after；变差则回退 | 用了自动摆放但无指标 → `BLOCKED`（可豁免） |
| `layout_frozen` | 状态 | 状态文件 | `layout.frozen`、`layout.frozen_at` | 已冻结并记录时间 | 未冻结 → `BLOCKED`（可豁免）；冻结后移动器件要重开 G3 |

`easyeda pcb layout-lint --gate` 已废弃：它只显示历史阈值，不授权、不阻断布线。Skill 自己定阈值（默认 score≥60、crossings≤8）；CLI 的 `--min-score`/`--max-crossings` 只有在兼容 `--gate` 时用于显示，不能当作放行依据。

**退出条件：** 分数与交叉达标、几何 0 错误、板框与目标一致、安装孔与连接器逃逸有记录、布局冻结。满足后与 G4 一起进入布线。

**豁免规则：** score、crossings、overlap/off-board/short 和板框不可豁免；安装孔、连接器逃逸、自动摆放对比、冻结时间可豁免并写明剩余风险。布局冻结后若为了布线移动器件，必须先重开 G3 并作废受影响布线。

**真实反例：** 15:38:01 `outline-fit --margin 100` 得到 3577.55 × 2176.76 mil；15:38:28 `pcb layout-lint` 仅为 `score 48/100 (hard)`、13 crossings（28 comps、0 short/overlap/off-board/tight、13 signal nets、ratsnest 17073 mil）；15:38:54 仍执行 `route-short`（v1.14.0 默认非 dry-run；当时日志写作 `--apply`，该参数不在 v1.14.0 help 中），74 routes、26 vias。随后 R1、R2 在 15:50:47 才从 `(1359.2,-1326.9)/(126.0,-410.5)` 移到 J1 旁 `(820,-1750)/(950,-1750)`，布局变更使已布线路由结论失效。

## 9. G4_power_ground 电源地策略

**目的：** 在布线前声明层数、电源/地分配和铺铜/平面策略，证明 GND 铺铜、过孔与规则可回读；避免“先布线再铺铜”造成大面积返工。

**必需输入：** 层叠决策（2 层 vs 4 层）、电源树、地策略、DRC 规则、铺铜/平面回执、过孔清单。方法细节见 [布线与回流细节](pcb-routing-details.md) 的 RT 条目与 [PCB 工程习惯](pcb.md)。

| check id | 判定 | 命令（v1.14.0） | 证据 | 通过条件 | 不支持时 |
|---|---|---|---|---|---|
| `stackup_declared` | 层数一致性 | `easyeda pcb stackup show`；`easyeda pcb dump --out board.json` | `pcb_board`、`stackup.layers` | 声明 2/4/6/8 层且与 PCB 实际 `copperLayers` 一致 | 不一致或缺失 → `BLOCKED`（不可豁免） |
| `stackup_decision` | 决策记录 | 同上 | `stackup.decision` | 有 2 层 vs 4 层的理由与代价记录 | 缺失 → `BLOCKED`（可豁免） |
| `power_ground_strategy` | 策略声明 | `easyeda pcb power-pour --dry-run`；`easyeda pcb power-planes --dry-run` | `stackup.power_ground_strategy` | 布线前声明一层一网或铺铜优先级、GND 层、非 GND 电源归属 | 缺失 → `BLOCKED`（不可豁免） |
| `inner_layers` | 内层 | `easyeda pcb stackup show` | `stackup.inner_layers` | 4 层以上声明 PLANE/SIGNAL/GND/POWER | 缺失 → `BLOCKED`（不可豁免） |
| `drc_rules_recorded` | 规则 | `easyeda pcb drc-rules > evidence/pcb-drc-rules.json` | `stackup.drc_rules_recorded` | clearance/线宽/过孔/net class 在布线前记录 | 缺失 → `BLOCKED`（可豁免） |
| `gnd_pours` | 铺铜回读 | `easyeda pcb power-pour` 后 `easyeda pcb pour-list --net GND` | `pcb_pours` | 2 层板 GND 在 L1、L2 均有铺铜；多网同层需回读 priority | 回执与回读不一致、`priorityVerified:false` → 不得当已确认；缺铺铜 → `BLOCKED` |
| `gnd_thin_traces` | 线宽审计 | `easyeda pcb dump --include-copper --out board.json` | `pcb_board` | 无低于 `max(10 mil, 2×trackWidthMinMil)` 的 GND 线 | 缺 dump → `BLOCKED`（不可豁免）；铺铜板上不应靠细 GND 线连通 |
| `via_audit` | 过孔 | `easyeda pcb via-list > evidence/pcb-vias.json` | `pcb_vias` | 回读新鲜、drill/diameter 可核对、无 `staleRisk` | 缺证据或字段不完整 → `BLOCKED`/`warn`；4 层板必须有 |
| `pcb_check_power` | DFM | `easyeda pcb check --json --spec S0.json > evidence/pcb-check.json` | `pcb_check` | `power-not-poured` 为 0 | 未运行只给 advisory `warn`；有该项 → `BLOCKED`（可豁免） |

`power-planes` 需要 ≥4 层，2 层会被拒绝并提示改用 `power-pour`。`power-pour` 默认 `railsMode=pour`，会为 GND 与电源轨创建铺铜；多层多网铺铜的 priority 必须以重载后的 `pour-list` 为准。

**退出条件：** 层数与板一致、层叠决策与电源/地策略在布线前记录、GND 双层铺铜可回读、过孔审计完成、`power-not-poured` 为 0。满足后与 G3 一起进入布线。

**豁免规则：** 层数、策略声明、GND 铺铜、GND 细线、过孔审计不可豁免；层叠决策、DRC 规则、`pcb check` 项可豁免并写剩余风险。铺铜回执不是铺铜几何本身，必须 `pour-list` 或 dump 回读。

**真实反例：** `power-pour` 创建 4 个铺铜（GND L1、GND L2、+5V L1、VREF L1）；创建回执 priority 1/1/2 且 `priorityVerified:false`，重载后 `pour-list` 读到 GND L1 priority=3，回执与回读不一致。铺铜后首次 DRC 30（3 Clearance + 27 Connection），但之前没有 DRC 基线，27 条断连与铺铜的因果只是时间顺序推断，不能写成已证明。随后 `route-short --route-power`：73 routes（GND 45、+5V 21、VREF 7；2 条 VREF 失败）、drawn 71、vias 14，GND 走线 20 mil（不是细线）；再跑 DRC 93（71 Clearance + 22 Connection，其中 net=GND 的 Clearance 68 条）。在铺铜板上用 `--route-power` 把电源/地布成 track，是 G4 未过就布线的典型后果。

### 电源主干的条件复核

涉及载流主干设计或线宽整改时，补充 [电源路径与走廊预检](power-routing-preflight.md) 的源/负载、电流依据、逐段瓶颈、压降和热模型适用条件。未达目标的加宽计划、未知跨度或未覆盖铺铜不能当通过；需要改道或给出有依据的替代方案。项目温升目标与几何阈值显式记录，不统一规定10K或150mil。

这是G4/G5的工程复核项，当前并未增加gate_check.py/pcb_gate.py自动检查ID；其现有PASS不意味着此项已核验。模型覆盖不全时通过适当原生连接证据与工程分析补足，不伪造脚本PASS。

## 10. G5_routing 布线完成

**目的：** 证明布线、铺铜和丝印整理后的板子可回读、可复现，关键连接有逐网证明；防止把“DRC 数字在变”当成布线完成。

**必需输入：** 布线计划、关键网清单、完整 DRC、关键网 `net-path` 证明、保存重载回读、丝印检查、DRC 轮次记录。计划模板见 [布线计划](../assets/routing-plan.md)。

| check id | 判定 | 命令（v1.14.0） | 证据 | 通过条件 | 不支持时 |
|---|---|---|---|---|---|
| `pcb_drc_passed` | 通过判定 | `easyeda pcb drc --json --timeout 120 > evidence/pcb-drc.json` | `pcb_drc` | `passed:true`；PCB 必须是前台/活动文档 | 后台/遮挡窗口永远算不完；超时切前台跑一次，不循环重试；缺证据 → `BLOCKED` |
| `connection_errors` | 连接错误 | 同上 | `pcb_drc.counts` | `Connection` 为 0 | 非 0 → `BLOCKED`（不可豁免） |
| `key_nets_declared` | 清单 | 状态文件 | `routing.key_nets` | 非空，覆盖电源、主信号、参考/阈值、输出/驱动、接口 | 缺失 → `BLOCKED`（不可豁免） |
| `key_net_proofs` | 逐网证明 | `easyeda pcb net-path --from D.PAD --to D.PAD --net <net> --json > evidence/net-path-<net>.json` | `net_path` | 每个关键网 `found:true` | `found:false` 表示未走线证明，不等于全板断连；缺证明 → `BLOCKED`（不可豁免） |
| `routing_plan` | 计划 | 阅读 [布线计划](../assets/routing-plan.md) | `routing.plan` | 层/通道/过孔/net class/顺序/停止条件齐全 | 缺失 → `BLOCKED`（不可豁免） |
| `save_reload` | 持久化 | `easyeda pcb save`；`easyeda doc reload`；再 `pcb dump`/`pcb drc` 回读 | `reopen_check` 或 `routing.save_reload` | 重载后对象与 DRC 结论 match | `save` 返回成功不算；缺回读 → `BLOCKED`（不可豁免） |
| `silk_over_pad` | 丝印 | `easyeda pcb silk-align`；`pcb dump`/`layout-lint` | `silk_align` | 0 处丝印压焊盘，或已整理并回读 | 缺失 → `BLOCKED`（可豁免） |
| `stop_rule` | DRC 轮次 | 状态文件 `routing.drc_rounds` | `drc_rounds`、`stop_rule_triggered` | 未出现连续 3 轮改善 <30%；触发时已停止并记录重排/改 4 层/拆页/如实报告 | 轮次不足只给 advisory `warn`；触发未处理 → `BLOCKED`（可豁免） |

`pcb net-path` 只证明已列出的走线铜（线段/弧/过孔/焊盘），不覆盖铺铜、平面和填充区域。仅靠铺铜连接的 GND 不要放进 `key_nets` 的 `net-path` 清单，应以 `pcb drc` 的 Connection 结论加 `pour-list` 回读证明；`net-path` 失败也不等于全板断连。

**退出条件：** `pcb drc` `passed:true` 且 0 Connection、关键网逐条证明、保存重载 match、丝印与停止规则有记录。满足后进入 S5。

**豁免规则：** PCB DRC、Connection、关键网证明、保存重载、布线计划不可豁免；丝印和停止规则可豁免，但停止规则触发时不能只豁免数字，必须记录结构决定（重排/4 层/拆页/如实报告）。

**真实反例：** DRC 完整序列为 93 → 50 → 31 → 28 → 23 → 31 → 28 → 22 → 16 → 18，不是单调下降，最终 18 比上一轮 16 更差；18 条中 6 条在 J1 的 VBUS(D1_N1)、CC1(D1_N3)、CC2(D1_N4) 焊盘行。只贴最后一轮会漏掉平台期与回升；G5 要求 `passed:true` 且 0 Connection，而不是“看起来在下降”。

## 11. G6_manufacturing 制造交付

**目的：** 证明制造资料、BOM、装配与恢复演练达到当前交付级别，并如实标注工具不支持项。

**必需输入：** Gerber、钻孔、CPL/坐标、BOM、工艺档案、工程导出包、库存/SMT 核对时间、测试计划。制造细节见 [制造与首板细节](manufacturing-details.md)、[生产规则接入](jlc-production.md) 与 [制造与交付路线](manufacturing-routes.md)。

| check id | 判定 | 命令 | 证据 | 通过条件 | 不支持时 |
|---|---|---|---|---|---|
| `gerber_files` | 文件存在 | easyeda v1.14.0 无 CLI/typed action；由用户在 EDA GUI 导出 | `gerber` | 文件存在、登记在 `manufacturing.artifacts`、版本与最终板一致 | CLI 无路径 → 属 `UNSUPPORTED` 能力；缺人工证据 → `BLOCKED`（不可豁免） |
| `drill_files` | 文件存在 | 无 CLI | `drill` | 钻孔文件存在且孔径/层与叠层一致 | 同上 |
| `cpl_files` | 文件存在 | 无 CLI/typed action | `cpl` | CPL/坐标存在，位号/封装/面/旋转/原点与 BOM 一致 | 同上 |
| `bom_c_numbers` | 逐行 | `easyeda bom export --type csv --enrich=false > BOM.csv` | `bom` | 每行数量>0 的器件都有 C 号 | 缺 C 号 → `BLOCKED`（不可豁免）；缺 MPN/厂家只给 advisory `warn` |
| `manufacturing_profile` | 记录 | 按 [工艺档案模板](../assets/manufacturing-profile.md) 填写 | `manufacturing.profile` | 层叠/铜厚/阻焊/表面处理/装配方式齐全 | 缺失 → `BLOCKED`（不可豁免） |
| `epro2_integrity` | 完整性 | `easyeda project export --out <file> --project-uuid <uuid>` | `project_export`、`.epro2` | zip 完整可打开；`zipIntegrityVerified:true` | 损坏/缺失 → `BLOCKED`；完整性不等于可恢复 |
| `epro2_restore` | 恢复演练 | 在副本上重开并回读 | `restoreVerified` | `restoreVerified:true`，记录重开后对象/连接仍在 | 缺失 → `BLOCKED`（不可豁免）；只做 `zipIntegrityVerified` 不够 |
| `sourcing_check` | 时间戳 | 查询立创商城/SMT 渠道当前状态 | `sourcing.stock_checked_at`、`smt_checked_at` | 库存与 SMT 可贴状态有核对日期；`smt_required:false` 必须带理由 | 缺失或只有历史 BOM → `BLOCKED`（不可豁免） |
| `test_plan` | 文件存在 | 按验证模板编写 | `docs/test-plan.md` | 上电、阈值、边界、失效测试项齐全 | 缺失 → `BLOCKED`（可豁免） |

**G6 的支持边界（必须写清）：** Gerber、钻孔、CPL 在 easyeda v1.14.0 没有 CLI 或 typed action（官方 `eda.pcb_ManufactureData.getGerberFile` 仍为 beta 且未包装）。这三项属 `UNSUPPORTED` 能力：gate_check 不会判 `PASS`，必须由用户在 EDA GUI 导出并落证据；缺人工证据时整门禁 `BLOCKED`。G6 通过也只输出交付级别（概念方案 / 原理图候选 / PCB 候选 / 制造候选 / 样机验证）与证据范围，不等于项目完成或可量产。

**退出条件：** 三类制造文件、BOM、工艺档案、工程恢复演练、库存/SMT 核对时间、测试计划全部有证据，且 gate_check 无 `BLOCKED`/`UNSUPPORTED`。

**豁免规则：** Gerber/钻孔/CPL、BOM C 号、工艺档案、恢复演练、库存/SMT 时间不可豁免；测试计划可豁免并写明为什么当前交付级别不需要。文件“存在”不等于内容正确，仍需核对层、单位、方向、DNP 与版本。

**真实反例：** 交付只有 BOM 21 行 26 件（全部有 C 号）、`docs/test-plan.md` 和 `.epro2`（364,810 bytes、SHA-256 `6dcf4d...00d9e`、`zipIntegrityVerified:true`、`restoreVerified:false`）；Gerber、钻孔、CPL 均无，未做恢复演练，BOM 的库存/价格/SMT 可贴也未实时核对。若按 G6 检查，这些缺项必须 `BLOCKED`，不能因“文件都齐了”或“BOM 有 C 号”就写可打板。

## 12. 与既有编号体系的关系

G 门禁引用既有检查体系，不替代、不复制条款正文。

### 12.1 SC / PL / RT / MF / DM 编号

- **SC**（[原理图细节](schematic-details.md)）用于 G2 的逐脚、电源单元、特殊脚与封装核对；例如 SC01 完整型号、SC02 引脚三方对照、SC04 特殊脚分类。G2 要求证据显示适用条目已落实，不在本文复述条目内容。
- **PL**（[PCB 布局细节](pcb-placement-details.md)）用于 G3 的机械外形、安装孔、接口插拔、正反面与高度分区；例如 PL01 外形先确定、PL02 孔不只是圆、PL03 接口可插拔。
- **RT**（[布线与回流细节](pcb-routing-details.md)）用于 G4/G5 的载流、参考层、换层回流、铜区与最终状态；例如 RT27 铜区真实状态、RT30 缝合有目的、RT32 移动后重验、RT33 实际连通性。
- **MF**（[制造与首板细节](manufacturing-details.md)）用于 G6 的焊盘、成品孔、阻焊/钢网、散热焊盘与 DNP；例如 MF01 实物焊接面、MF02 成品孔公差、MF08 DNP 钢网。
- **DM**（[领域易漏项](domain-design-details.md)）按具体硬件类型补充 G2/G3/G4 的适用项；领域覆盖不等于该领域已验证。
- 条目选择方法见 [工程经验库与来源](design-experience.md)：按当前对象选适用条目，不整库加载，也不把“读过清单”当通过证据。

### 12.2 netlist_diff 网表门禁

`python scripts/netlist_diff.py before.net after.net --output netlist-diff.json` 比较器件身份字段与物理引脚→网络映射，不比较坐标或格式。G2 的 `netlist_audit` 直接消费该结果：`status=match` 才允许声明“连接未变”；纯排版要求整个 diff 为 `match`，电气修订只允许逐条白名单差异；`invalid` 输入不能作为验收证据。G1 的冻结后重新导入也可用它证明 PCB 网表与原理图一致。网表不包含未连引脚，单靠网表不能证明 NC 状态。

### 12.3 connectivity 硬门禁

[连接表契约](connectivity.md) 的 `python scripts/netlist_check.py design.json --json` 在声明数据上检查结构冲突与显式装配要求：位号重复、同脚连接与 NC 冲突、完整引脚表比较、显式电源/地分类冲突、显式上拉要求未满足等。它是“声明数据上的硬门禁”：出现结构冲突或显式要求不满足时不能声称连接正确；但所有结果带 `board_verified:false`，不读取 EDA、不判真实铜连接，不能替代 `sch drc` 或 PCB DRC。缺少 `physical_pins` 时结果是 `incomplete`，不能算覆盖完整。按 SKILL.md §6，它不是每次修改的强制前置。

### 12.4 decision 有效性门禁

[设计决策库](decisions/README.md) 的 D0/D1/D2 决定哪些决策需要记录。G0/G1/G3/G4 引用相关决策（A 架构、D 容差、I 变更、J 复用、L 资产）的路径与结论；`decision_record_check.py` 检查校准/变更记录的结构与自洽，`decision_asset_check.py` 检查索引字段、重复 ID、悬空依赖、状态枚举与文件存在。两者通过只证明记录结构成立，不证明决策技术正确或硬件已执行；G 门禁引用判定，不重判工程结论。

## 13. 证据目录与状态文件

### 13.1 目录约定

建议把证据放在项目工作区的 `evidence/`，状态文件放项目根；文件名可自定，`gate_check.py` 按角色模式发现最新可解析文件，必要时用 `--file role=path` 显式指定。

```text
project/
  design-state.json
  docs/change-impact-<ref>.md
  docs/test-plan.md
  manufacturing/            # Gerber、钻孔、CPL、BOM
  evidence/
    sch-drc.json
    sch-check.json
    sch-nets.json
    pcb-layout-lint.json
    pcb-drc.json
    pcb-board.json
    pcb-pours.json
    pcb-vias.json
    net-path-<net>.json
    doc-reload-readback.json
```

### 13.2 证据角色

| role | 默认匹配 | 期望内容 |
|---|---|---|
| `sch_drc` | `sch-drc*.json`、`sch_drc*.json` | `sch drc` JSON 或 human 摘要；fatal/error 计数 |
| `sch_check` | `sch-check*.json`、`sch_check*.json` | findings JSON 或 human 计数 |
| `sch_nets` | `sch-nets*.json`、`sch_nets*.json` | 单引脚网审计 |
| `schematic_png` | `schematic*.png`、`sch*.png` | 实际导出的原理图 |
| `netlist_diff` | `netlist-diff*.json`、`netlist_diff*.json` | `status=match` 或白名单差异 |
| `pcb_layout_lint` | `pcb-layout-lint*`、`*layout*lint*` | 必须是 PCB 版（JSON 含 `crossings`，文本含 `PCB layout-lint`） |
| `pcb_drc` | `pcb-drc*.json`、`pcb_drc*.json` | `passed/total/counts/violations` 或 flat JSON |
| `pcb_check` | `pcb-check*.json`、`pcb_check*.json` | DFM findings |
| `pcb_board` | `pcb-board*.json`、`pcb-dump*.json` | components/outline/copper/rules |
| `pcb_pours` | `pcb-pour*.json`、`pcb-pours*.json` | `result.pours` / `pours` |
| `pcb_vias` | `pcb-vias*.json`、`pcb_via*.json` | `result.vias` 与 `staleRisk` |
| `pcb_mount_holes` | `*mount-hole*`、`*mount_hole*` | `pcb mount-holes` 回执 |
| `silk_align` | `*silk-align*`、`*silk_align*` | `pcb silk-align` 回执 |
| `net_path` | `net-path*.json`、`net_path*.json` | 每网一条证明 |
| `reopen_check` | `*reopen*.json`、`*reload*readback*` | 保存重载后的回读 match |
| `project_export` | `project-export*.json`、`project_export*.json` | `restoreVerified`/`zipIntegrityVerified` |
| `bom` | `BOM*.csv`、`bom*.csv` | 原始 BOM CSV |
| `gerber` | `*.gbr`、`*.g??`、`gerber*` | 制造层 |
| `drill` | `*.drl`、`*drill*` | 钻孔 |
| `cpl` | `*cpl*.csv`、`*pos*.csv`、`*pick*place*` | 坐标 |

`format` 取值：`json` / `text` / `csv` / `file` / `invalid_json`。JSON 解析失败但内容像 JSON 时，对应检查 `BLOCKED`；截断文件同理，不猜测剩余内容。文件名是 `.json` 不代表内容是 JSON（见 §14）。

### 13.3 design-state.json schema

状态文件统一使用 `design-state/v1`。门禁读取固定键名；字段可裁剪，缺省即按 `BLOCKED` 处理并列出缺项。

```json
{
  "schema": "design-state/v1",
  "project": {"name": "<name>", "board_revision": "<rev0>", "stage": "G0", "updated": "<YYYY-MM-DD>"},
  "requirements": {
    "delivery_level": {"status": "confirmed", "value": "<原理图|PCB|DRC0|Gerber|实物>"},
    "size_limit": {"status": "confirmed", "value": {"width_mm": 0, "height_mm": 0, "source": "<user|enclosure>"}},
    "enclosure_mounting": {"status": "not_applicable", "reason": "<裸板首板>"},
    "assembly": {"status": "confirmed", "value": "<self-solder|jlc-smt|mixed>"},
    "quantity_budget": {"status": "confirmed", "value": {"qty": 0, "budget_cny": 0}},
    "usb_role": {"status": "confirmed", "value": "power-only|data|none"},
    "test_points": {"status": "confirmed", "value": ["+5V", "GND"]},
    "display": {"status": "not_applicable", "reason": "<无显示>"},
    "firmware": {"status": "not_applicable", "reason": "<纯模拟>"},
    "threshold_interaction": {"status": "confirmed", "value": "<RV1|按键|菜单>"},
    "alarm_behavior": {"status": "confirmed", "value": "<LED+蜂鸣|自动解除>"},
    "environment_accuracy": {"status": "confirmed", "value": "<0-40 C, +/-2 C>"}
  },
  "function_freeze": {
    "status": "frozen", "frozen_at": "<YYYY-MM-DD>", "required": [], "optional": [],
    "removed_after_freeze": [{"designator": "J2", "reason": "<...>", "change_impact": "docs/change-impact-j2.md"}]
  },
  "schematic": {
    "netlist_audit": {"status": "pass", "evidence": "evidence/netlist-diff.json"},
    "titleblock": {"status": "pass"}, "png_review": {"status": "pass", "evidence": "evidence/schematic.png"},
    "single_pin_nets": {"status": "pass", "count": 0}, "net_naming": {"status": "pass"}
  },
  "layout": {
    "board_outline": {"status": "confirmed", "width_mm": 0, "height_mm": 0},
    "mounting_holes": {"status": "confirmed", "count": 0, "diameter_mm": 0},
    "connector_escape": {"status": "pass", "max_distance_mm": 0, "slot_clear": true},
    "auto_place_used": false, "auto_place_metrics": {}, "frozen": true, "frozen_at": "<YYYY-MM-DD>"
  },
  "stackup": {
    "layers": 2, "decision": {"status": "pass"}, "power_ground_strategy": {"status": "pass"},
    "inner_layers": [], "drc_rules_recorded": true
  },
  "routing": {
    "plan": {"status": "pass"}, "key_nets": ["+5V", "NODE"],
    "key_net_proofs": {"+5V": {"found": true, "evidence": "evidence/net-path-5v.json"}},
    "save_reload": {"status": "pass"}, "silk_align": {"status": "pass"},
    "drc_rounds": [{"round": 1, "total": 18}], "stop_rule_triggered": false
  },
  "manufacturing": {
    "artifacts": [{"role": "gerber", "path": "manufacturing/gerber.zip"}],
    "profile": {"status": "pass"},
    "project_export": {"path": "project.epro2", "restore_verified": false},
    "test_plan": {"path": "docs/test-plan.md", "status": "pass"}
  },
  "sourcing": {"stock_checked_at": "<YYYY-MM-DD>", "smt_checked_at": "<YYYY-MM-DD>", "smt_required": true},
  "waivers": [], "assumptions": [], "risks": [], "open_items": []
}
```

字段值支持两种写法：标量/数组/对象视为已确认；`{"status": ...}` 的 `status` 取 `confirmed`、`assumed`、`not_applicable`、`pending`、`blocked`。`assumed` 必须带 `assumption` 或 `source`，`not_applicable` 必须带 `reason`，`pending`/`blocked` 一律阻塞。早期草案使用的 `gates.json` 文件名与 `design-gates/v1`、camelCase（如 `functionFreeze`、`boardSizeMaxMm`）不被当前脚本识别；迁移时改成上面的 snake_case 键，文件名可保留但 `schema` 必须是 `design-state/v1`。

### 13.4 gate_check 调用

```text
python scripts/gate_check.py --project <name> --evidence-dir <dir>
  [--project-dir <dir>] [--design-state <file>] [--brief <file>]
  [--waiver GATE[:CHECK]:REASON ...] [--waiver-file <file>]
  [--file ROLE=PATH ...]
  [--min-layout-score 60] [--max-crossings 8] [--strict-advisory]
  [--json] [--out <report.json>] [--quiet]
```

- `--brief` 仅为兼容保留；G0 读取的是 `--design-state` 指向的状态文件，不是 Markdown 摘要。
- 状态文件用 `--design-state` 传入；当前实现没有 `--gates` 或 `--epro2` 参数，`.epro2` 路径写在 `manufacturing.project_export.path`。
- `--json` 输出 `design-gate-report/v1`；`--out` 同时落盘；默认 human 摘要只列非 `pass` 项与 `next_command`。
- 缺失检查项的 `next_command` 只写当前 CLI 真实存在的命令；落盘用 shell 重定向，不编造不存在的 `--out` 组合。

## 14. 常见误用

- **把门禁当审批。** 门禁不新增等待点；Agent 在已授权范围内自查、记录、继续。只有用户明确要求“先评审/这步给我看/确认后再布线”时，才在四个可见检查点等待。把每个 G 都做成“请用户确认”会违反 SKILL.md §1 的评审节奏。
- **用 `layout-lint --gate` 当授权。** `--gate` 已废弃，只显示历史阈值，不授权、不阻断布线。复盘里 score 48/100、13 crossings 仍执行了 `route-short`（当时日志带 `--apply`），说明 CLI 不拦不等于门禁通过。
- **用自动布线救布局。** 布局未达标时先布线，只会把布局问题变成 DRC 问题：48/100 的布局布出 74 routes、26 vias，后续 DRC 到 93。`route-short`/`autoroute` 都只是候选结果，不是布局通过或布线完成。
- **DRC 清零当布线完成。** 复盘 DRC 从未到 0，序列最低 16 又回升到 18；即使某一轮为 0，仍需关键网 `net-path`、保存重载、铺铜回读与丝印检查。DRC 也不证明 SI/PI、EMC 或样机功能。
- **G6 当项目完成。** G6 只到“制造候选”；Gerber/钻孔/CPL 无 CLI，样机、固件、功能实测是另外的验收。不能因为 G6 通过就说“可量产/已可用”。
- **把 `.json` 文件名当 JSON。** 复盘里 `sch-drc.json`、`sch-check-final2.json`、`layout-lint-all.json` 是纯文本；`pcb-drc-1.json` 是 JSON 后追加 CLI 行；`bom-export.log` 是 JSON+人类行+traceback。解析器按内容判 `format`，文件名只用于角色发现；内容像 JSON 但解析失败会判 `invalid_json` 并 `BLOCKED`。
- **缺证据当通过，或用旧证据。** 未运行写 `NOT RUN`，不写“应该没问题”；证据早于最终板或组件数不一致会标 `STALE_EVIDENCE`，必须重跑受影响检查，不能沿用旧结论。
- **把 `UNSUPPORTED` 当 `PASS`。** Gerber/钻孔/CPL、无 CLI 覆盖的检查项必须进 `not_checked` 并要求人工证据；缺人工证据时整门禁 `BLOCKED`。

## 15. 变更记录

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-10-24 | 0.6.0 | 首次建立 G0–G6 门禁、四结论词与五状态词映射、`design-state/v1` 状态文件、`gate_check.py` 离线复核与温度报警板回归案例；命令面按 easyeda-agent v1.14.0 核对 |
| 2026-10-24 | 0.6.0 | 明确 G 门禁是阶段退出证据门而非审批；G3/G4 并列于布线前；G6 的 Gerber/钻孔/CPL 标 `UNSUPPORTED`，缺人工证据整门禁 `BLOCKED` |
| 2026-10-24 | 0.6.0 | 状态文件由早期草案的 `gates.json`/`design-gates/v1`/camelCase 统一为 `design-state.json`/`design-state/v1`/snake_case；旧稿字段不再被识别 |
