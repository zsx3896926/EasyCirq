# gate

## summary

已完成只读映射。gate_check.py 现有 G0–G6 离线证据门禁可复用其证据发现/哈希/最新候选选择、Gate 状态机、豁免与报告/退出码；但八个 PCB 阶段中只有 layout-lint、native DRC、key net-path（依赖 state/逐网文件）、save/reload（仅 reopen 角色）和 pcb-check 的 power-not-poured（解析有缺陷）被部分接入。pcb-check-plan、SCH-PCB 逐脚对账、WARN 处置表+图片没有进入 gate_check；两个真实案例的 design-state schema 是 design-engine-state/v1，直接运行 gate_check 会 exit 2，去掉 state 则 7 个门全 BLOCKED。案例证据本身很完整（DRC 0、net-path 15/15 与 14/14、SCH-PCB 0 mismatch、save/reload match、局部改板 unrelated 0），但文件名/角色/证据新鲜度与 gate_check 不匹配。新 pcb_gate.py 应把八个阶段做成 PCB 子门（映射到 G3/G4/G5，不另造 G 别名），复用 gate_check 的基础设施与 design_engine 的几何/约束/diff 能力，新增证据角色、跨工件身份与新鲜度绑定、按 finding 的 WARN 处置 schema、图片 manifest 校验。

## gaps

- 仓库中没有 pcb_gate.py；scripts/ 目录仅有 gate_check.py、pcb_apply_plan.py 与 design_engine 包，八阶段没有统一 PCB 专用入口。
- 两个真实案例的 design-state.json 使用 design-engine-state/v1，gate_check 要求 design-state/v1，直接运行 exit 2；案例也缺 requirements/function_freeze/stackup/routing/manufacturing/sourcing 等 gate_check 需要的结构。
- gate_check 的角色文件名/glob 与案例证据不匹配：netpath-key-connections.json、save-reload-diff.json、placement-check-final.json、sch-pcb-compare.json、power-check-final.json、fabrication-check-final.json、PCB PNG/SVG 都无法被发现或解析。
- 两个案例都没有提交 pcb-layout-lint 的 JSON/TXT 证据文件，README 的 68/moderate 与 80/moderate 无法复算；layout-lint 阶段目前不可机验。
- parse_pcb_check 只读 code/rule/category，真实 pcb-check 用 type；也不读 summary，导致 power-not-poured 被算成 0 并 pass，和 summary.powerNotPoured=1/2 矛盾。
- SCH-PCB 逐脚对账没有可复用生成器：sch-pcb-compare.json 是临时聚合，无 schema；pcb-audit 需要固定 bundle 文件名和 design-engine-ir/v1 sch IR，案例没有；组合脚 A1B12/A4B9 会被当前比较器报不可直接比较，无法复现 0 mismatch。
- key net-path 只有聚合文件，没有逐网原始 JSON；聚合文件既无 schema/顶层 status，也无 project/document/capturedAt 绑定，gate_check 未实现 rows 解析。
- 跨工件身份与新鲜度未绑定：DRC、pcb check、net-path、SCH-PCB、图片都没有 projectUuid/documentUuid/semanticSha256/capturedAt 字段可校验；实测 mtime 显示 MCU 的 check/DRC 早于最终 reload dump，photo 的 netpath/SCH-PCB/图片早于最终 dump。
- WARN 处置没有 schema/解析/门禁：只有 README 人工表和 gate/check 级 waiver，无法证明每条 WARN 都被 fixed/waived/accepted 且理由、证据、复验条件齐全。
- PCB 图片不是证据角色；没有 viewed/审核记录、manifest、sha256 或 blank/stale frame 判定，也没有要求顶/底图与最终 dump 同批次。
- placement-apply-report.json 顶层 status=mismatch 与其 diff 字段不一致（expected_placement_diff 重算为 True），说明 wrapper status/reload.ok 不能直接用于门禁。
- 板 B 没有独立 placement-check 证据：placement-apply-report 内嵌 check 的 constraints 为空、constraint_rows=0，fixed/edge/near-pin/keepout 未被约束校验。
- pcb-diff 对 scoped 编辑正常返回 changed 且 CLI exit 1，容易被误判为失败；gate_check 也没有 unrelated_changes 语义。
- 没有针对这两个真实案例的 gate 回归和 pcb-check 解析负向测试，现有 gate 测试只锚定 temp-alarm。

## recommendations

- 新增 design-hardware/scripts/pcb_gate.py，输出 pcb-gate-report/v1；八个阶段用 PCB 子门 ID（如 PG1_placement、PG2_layout、PG3_drc、PG4_check、PG5_netpath、PG6_sch_pcb、PG7_save_reload、PG8_disposition），并在报告里映射到既有 G3_layout/G4_power_ground/G5_routing，不另造 G0–G6 别名。
- 复用 gate_check.py 的 Evidence/discover 机制（最新可解析候选、sha256/mtime/format/candidates/selected_because/stale_risk/error）、Gate.add/finalize 状态机（PASS/PASS_WITH_WAIVER/BLOCKED/UNSUPPORTED）、find_waiver、render_human 与 0/1/2 退出码；报告继续带 evidence meta、next_command、not_checked、waivers。
- 扩展证据角色与 glob：pcb_layout_lint、pcb_placement_check、pcb_constraints、pcb_intent、net_path_aggregate（netpath*connections*.json 或 net-path*.json）、sch_pcb_compare、save_reload_diff（save-reload-diff*.json/*reload*diff*.json）、pcb_dump_before/after、pcb_image_top/bottom、pcb_actual_svg、pcb_warn_disposition；同时支持 --file ROLE=PATH 覆盖旧命名。
- 阶段1 复用 design_engine pcb-constraints/pcb-check-plan：要求 constraints.status=compiled（允许良性 edge_fixed_requires_pose_check，拒绝 conflicted/incomplete）、placement.status=pass 且 hard_ok=true、0 hard_failed、0 hard_unmeasured、constraints 行数>0 且覆盖 intent 声明的 fixed/edge/near_pin/keepout 类型；校验 plan.base_semantic_sha256 与当前 dump semanticSha256 一致，拒绝 0 约束行的伪通过。
- 阶段2 直接复用 gate_check 的 layout_lint 解析与 G3 阈值：score>=60、crossings<=8、overlap/off-board/short=0，tight 仅 advisory；要求 lint 文件存在且晚于最终 board dump、组件数一致；silkUnchecked/解析失败不得当 pass；把 --min-score/--max-crossings 仅作为本工具阈值，不依赖 CLI 的 --gate。
- 阶段3/4 解析 native DRC 与 pcb check 时以 JSON 字段为准：DRC 要求 passed=true、total=0、counts 中 connection 为 0；pcb check 要求 summary.errors=0，并把 summary 与 findings[].type 都纳入分类（修复 parse_pcb_check 的 type/summary 缺陷）；passed=false 但仅 WARN 时交由阶段8 处置表判定，不直接判 DRC 失败。
- 阶段5 要求每个 routing.key_nets 至少一条证据：优先聚合 rows 中 status=connected、path_kind=exact-centerline、net/from/to 与声明完全匹配；或逐网 net-path JSON 的 found/connected=true；拒绝重复/歧义 proof；明确记录 net-path 不覆盖铺铜，GND/纯铺铜网必须用 DRC+pour-list 证据而非 net_path。
- 阶段6 新增确定性 sch-pcb 比较器（可复用 pcb._reconcile_pin_pads 并扩展）：从 sch-connectivity/sch read 只取 componentType=part，按 designator+padNumber 逐脚比较 pin net，保留重复 pad 号；对 A1B12/A4B9 等组合脚要求显式映射表，无法映射时输出 unmapped 而不是猜；输出 status、schematic_components、pcb_components、pins、mismatches[]，要求双向组件集合一致且 mismatches 为空。
- 阶段7 不信任 pcb_apply_plan 的顶层 status/reload.ok 或 pcb-diff CLI 退出码；用 before/after dump 重新调用 diff_boards。纯持久化要求 status=match 且 before/after semanticSha256 相同、documentUuid 相同；局部改板要求 unrelated_changes=[]、所有 identity/geometry/copper 变化都在 scope.designators/nets/bbox 内，status 可为 changed。
- 阶段8 定义 pcb-warn-disposition/v1：source 绑定 pcb-check 的 path/sha256/capturedAt，findings[] 以 type+designator/net+message 生成稳定 key，每条 ERROR/WARN 必须有 disposition=fixed|waived|accepted|not_applicable、reason、evidence[]、recheck_condition、verified_at；fixed 项必须已从最终 pcb-check 消失，accepted/waived 必须写剩余风险；任何未处置 WARN 判 BLOCKED。
- 阶段8 图片改用 `easyeda pcb stage-snapshot --project <name> --doc <PCB> --stage <label> --out <evidence_dir>` 生成 snapshot.png+data bundle+stage.json（该命令对 blank/corrupt/mismatched-hash 非零退出），要求 top/bottom 两图、PNG signature/尺寸/sha256、manifest 的 blank 与 hash 判定、viewed=true+审图记录；`easyeda pcb layout render --actual --board board.json --side both --out ...svg` 作为辅助几何图，不替代铜层/网络验收。
- 增加跨工件 binding 层：从 dump capture 读 projectUuid/documentUuid/capturedAt/semanticSha256，给 DRC/check/netpath/sch-pcb/diff/images 记录绑定或 mtime 顺序；任何证据早于最终 save/reload dump、组件数不一致、documentUuid 不同或 semanticSha256 不可比时输出 STALE_EVIDENCE 并禁止 PASS；无 capture 元数据的工件至少记录 mtime 并标风险。
- 补回归与负向测试：用 photo-led 与 mcu-i2c 的真实 evidence 建立期望报告（允许 DRC/save-reload 通过，layout-lint 缺失与 WARN 未处置应 BLOCKED/带 stale 标记）；加 pcb-check power-not-poured 解析测试、scoped diff unrelated=0/changed 测试、组合脚 SCH-PCB 测试、图片 manifest 缺失/stale 测试。
- 同步更新 references/pcb-execution.md 与 references/design-gates.md 的证据命名、命令、JSON 字段和阶段映射，避免继续出现 README 有人工数字但目录无对应 JSON 的情况；明确 pcb_gate 是 G3/G4/G5 的 PCB 子门，不是第二套流程。

## facts

### gate_check.py 是离线 G0–G6 阶段门禁：只读 evidence-dir/design-state，不连 EDA、不写工程；报告 schema=design-gate-report/v1，状态为 PASS/PASS_WITH_WAIVER/BLOCKED/UNSUPPORTED；有 BLOCKED 或 UNSUPPORTED 时 exit 1，参数/IO/schema 错误 exit 2，否则 exit 0。

evidence: C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/gate_check.py:1-13,33-40,1058-1105,2102-2103,2192-2206；C:/Users/jlc/work/hds-pcb-round9/design-hardware/SKILL.md:203-213

### gate_check CLI 输入为 --project、--evidence-dir（必填）、--project-dir、--design-state、--file ROLE=PATH、--waiver/--waiver-file、--min-layout-score(默认60)、--max-crossings(默认8)、--strict-advisory、--json/--out/--quiet；输出 report 字段为 schema/project/generated_at/evidence_dir/project_dir/design_state/thresholds/gates/summary/evidence/warnings/waivers/waivers_used/not_checked。state schema=design-state/v1，waiver schema=design-waivers/v1。

evidence: C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/gate_check.py:33-35,1989-2024,2046-2141,2170-2187

### 证据发现机制按 ROLE_PATTERNS glob 每个角色，取最新且可解析的候选；每个结论记录 path/sha256/mtime/size/format/candidates/selected_because/stale_risk/error；selected 为 invalid_json 时按 BLOCKED，staleRisk 只警告；--file 可显式覆盖角色。

evidence: C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/gate_check.py:109-154,263-313,336-395,2046-2070

### 两个案例的 design-state.json 顶层 schema 是 design-engine-state/v1，而 gate_check 只接受 design-state/v1；用案例 state 运行 gate_check 实测报 'design-state.schema=... 期望 design-state/v1' 并 exit 2。案例 state 还缺少 gate_check 需要的 requirements/function_freeze/stackup/routing/manufacturing/sourcing 结构。

evidence: C:/Users/jlc/work/hds-pcb-round9/design-hardware/cases/mcu-i2c-s3-2026-10-26/design-state.json:2；C:/Users/jlc/work/hds-pcb-round9/design-hardware/cases/photo-led-pcb-2026-10-26/design-state.json:2；C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/gate_check.py:34,1989-2002（实测：python gate_check.py --design-state cases/mcu-i2c-s3-2026-10-26/design-state.json 输出 error 且 exit 2）

### 不带 design-state 实测两个案例时，gate_check 只发现 bom、pcb_board、pcb_check、pcb_drc（photo 另加 silk_align），7 个门全 BLOCKED、exit 1。原因是角色文件名不匹配：netpath-key-connections.json 不匹配 net-path*.json/net_path*.json；save-reload-diff.json 不匹配 *reopen*.json/*reload*readback*；placement-check-final.json、sch-pcb-compare.json、power-check-final.json、fabrication-check-final.json、pcb-final-top/bottom.png、pcb-final-actual.svg 都没有对应角色。

evidence: C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/gate_check.py:109-130；C:/Users/jlc/work/hds-pcb-round9/design-hardware/cases/mcu-i2c-s3-2026-10-26/evidence/；C:/Users/jlc/work/hds-pcb-round9/design-hardware/cases/photo-led-pcb-2026-10-26/evidence/（实测 gate_check --json 的 evidence roles 分别为 bom/pcb_board/pcb_check/pcb_drc 与 bom/pcb_board/pcb_check/pcb_drc/silk_align）

### 阶段1 pcb-check-plan / fixed+edge+near_pin+keepout：命令为 `python design_engine_cli.py pcb-constraints --dump board.json --intent pcb-intent.json --out constraints.json --json`，再 `python design_engine_cli.py pcb-check-plan --dump board.json --plan placement.json --constraints constraints.json --json`。constraints 输出 schema=design-engine-pcb-constraints/v1、status=compiled|conflicted|incomplete、constraints[]（id/type/severity/source/unit）、conflicts[]（kind/constraints/objects/message/source）、unknown[]、counts；placement 输出 schema=design-engine-pcb-placement/v1、status=pass|review、hard_ok、findings[]（code/severity/objects/message）、constraints[]（constraint_id/type/status=pass|fail|unmeasured/severity/distance_mil 等）、counts（findings/hard_findings/constraint_rows/hard_failed/hard_unmeasured）、measurement_note。

evidence: C:/Users/jlc/work/hds-pcb-round9/design-hardware/references/pcb-execution.md:97-107；C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/design_engine/cli.py:953-968；C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/design_engine/pcb_workflow.py:341-585,611-899

### 阶段1 语义：pcb-constraints 只有无 hard conflict 且 unknown 为空才 status=compiled；edge+fixed 共存的 kind=edge_fixed_requires_pose_check 是良性提示，不把整体判 conflicted。pcb-check-plan 只有无 hard findings、无 hard 约束 fail、无 hard 约束 unmeasured 才 status=pass/hard_ok=true，否则 review；CLI 也只在 pass 时 exit 0。该能力已在 design_engine 实现，但 gate_check 完全没有对应角色/解析/检查。

evidence: C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/design_engine/pcb_workflow.py:569-584,880-899；C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/design_engine/cli.py:608,626；C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/gate_check.py:42-50,109-154（无 placement/constraints 角色）

### 阶段1 案例证据：板 A（photo-led）有 placement-check-final.json，status=pass、hard_ok=true、14 条约束行全部 pass、0 hard_failed/0 hard_unmeasured，constraints.json status=compiled（14 条、hard 8、preferred 6、conflicts 1 为良性 edge_fixed）。板 B（MCU）没有独立的 placement-check 文件，placement-apply-report.json 内嵌 check 的 constraints 为空、constraint_rows=0，因此板 B 的 fixed/edge/near-pin/keepout 通过约束校验这一点并未被机器证据证明。

evidence: C:/Users/jlc/work/hds-pcb-round9/design-hardware/cases/photo-led-pcb-2026-10-26/evidence/placement-check-final.json:2-4,166-173；同目录 constraints.json:2-3,213-235；C:/Users/jlc/work/hds-pcb-round9/design-hardware/cases/mcu-i2c-s3-2026-10-26/evidence/placement-apply-report.json:3-16（check.constraints 为空，constraint_rows=0）；C:/Users/jlc/work/hds-pcb-round9/design-hardware/cases/mcu-i2c-s3-2026-10-26/README.md:57-58

### 阶段2 layout-lint：命令为 `easyeda pcb layout-lint --json --project <name> --doc <PCB> > evidence/pcb-layout-lint.json`（可选 --min-gap；--min-score/--max-crossings 只在已废弃的 --gate 兼容显示，不授权布线）。gate_check 消费的 JSON 字段为 score、crossings、components/comps/componentCount、short、overlap/overlaps、offBoard/off_board/offboard、tight、silkOverPad/silk_over_pad，或 counts 下的同名键；文本回退解析 'PCB layout-lint'、'score N/100'、'N crossings'、'N comps' 等。

evidence: C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/gate_check.py:598-647；C:/Users/jlc/work/hds-pcb-round9/design-hardware/references/design-gates.md:138-149；C:/Users/jlc/work/hds-pcb-round9/tests/test_gate_check.py:74-88,219-224

### 阶段2 当前门禁语义（gate_check G3）：score>=--min-layout-score(默认60)、crossings<=--max-crossings(默认8)、overlap=0/off_board=0/short=0 才 pass；tight 只作 advisory；silk_over_pad>0 只给非阻断 warn。若 lint 早于最终 board dump 或组件数与 dump 不一致，判 STALE_EVIDENCE、blocking 且不可豁免；缺 lint 或解析失败判 BLOCKED 不可豁免。已实现于 gate_check；但两个案例都没有提交 pcb-layout-lint JSON，只有 README 中的 68/moderate 与 80/moderate 文字，因此该阶段目前无法从证据复现。

evidence: C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/gate_check.py:1415-1465；C:/Users/jlc/work/hds-pcb-round9/design-hardware/cases/mcu-i2c-s3-2026-10-26/README.md:31；C:/Users/jlc/work/hds-pcb-round9/design-hardware/cases/photo-led-pcb-2026-10-26/README.md:28（两目录 evidence/ 均无 pcb-layout-lint*.json）

### 阶段3 native pcb drc：命令为 `easyeda pcb drc --json --timeout 120 --project <name> --doc <PCB> > evidence/pcb-drc.json`（PCB 必须是前台/活动文档；超时先切前台一次，不循环重试；原生 verdict 为 false 或不可用时 CLI 非零退出）。JSON 字段为 passed、total、counts{rule->count}、violations[]（rule/objType/ruleName/net/x/y/layer/objs/message/globalIndex）、nativeResult{passed,violations}。gate_check 还兼容文本 'pcb drc: N violation'。

evidence: C:/Users/jlc/work/hds-pcb-round9/design-hardware/references/design-gates.md:189-192；C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/gate_check.py:650-713；C:/Users/jlc/work/hds-pcb-round9/design-hardware/cases/temp-alarm-2026-10-24/evidence/pcb-drc.json:1-20；easyeda pcb drc --help（本机 1.15.0）

### 阶段3 门禁语义：gate_check 要求 passed=true 且 counts 中 connection-error/connection 合计为 0 才 pass；缺证据、JSON 不可解析或 invalid_json 判 fail/BLOCKED 且不可豁免；connection_errors>0 另加一条 blocking/不可豁免 fail。已在 gate_check.py 实现，pcb-audit 也会把任何 DRC violation 当 hard。两个案例的 pcb-drc-final.json 均为 passed=true、total=0、counts={}、nativeResult.passed=true。

evidence: C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/gate_check.py:678-690,692-713,1706-1728；C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/design_engine/pcb.py:120-136,427-434；C:/Users/jlc/work/hds-pcb-round9/design-hardware/cases/mcu-i2c-s3-2026-10-26/evidence/pcb-drc-final.json:1-9；C:/Users/jlc/work/hds-pcb-round9/design-hardware/cases/photo-led-pcb-2026-10-26/evidence/pcb-drc-final.json:1-9

### 阶段4 pcb check：命令为 `easyeda pcb check --json --spec S0.json --project <name> --doc <PCB> > evidence/pcb-check.json`。JSON 字段为 passed、summary（danglingEnds/acuteAngles/nonOrthogonal/trackOverPad/clearance/silkscreenFlipped/overlappingVias/singleLayerVias/widthMismatches/duplicateSegments/parallelCoupling/antennaKeepout/netlessPours/viaCrossesPlane/floatingIslands/powerNotPoured/netlessViaInPad/widthUnderSpec/silkOverPad/silkOffBoard/decapTooFar/viaInPad/copperNearEdge/fiducialMissing/zoneViolation/internalOnEdge/connectorPlugClearance/connectorMatingBlocked/connectorOpeningInward/errors/warnings/total）、trackCount、viaCount、padCount、findings[]（type/level/net/nets/designator/primitives/widths/angleDeg/message/at）、incomplete、coverage{complete,componentsInventoryKnown,padsInventoryKnown,componentCount,totalPads,knownGeometryPads,unsupportedGeometryPads,unknownGeometryPads,legacyGeometryPads}。

evidence: C:/Users/jlc/work/hds-pcb-round9/design-hardware/references/design-gates.md:163-173；C:/Users/jlc/work/hds-pcb-round9/design-hardware/cases/mcu-i2c-s3-2026-10-26/evidence/pcb-check-final.json:1-215；C:/Users/jlc/work/hds-pcb-round9/design-hardware/cases/photo-led-pcb-2026-10-26/evidence/pcb-check-final.json:1-122；easyeda pcb check --help（本机 1.15.0：默认信息模式 exit 0，--strict 才因 WARN/ERROR 非零）

### 阶段4 门禁语义：官方 pcb check 的 passed=false 表示存在任意 issue（含 WARN/INFO），不是只有 ERROR 才 false；默认 exit 0，只有 --strict 才非零。gate_check 只在 G4 用它做 pcb_check_power：从 counts 里找 power-not-poured/gnd-not-poured，>0 才 fail（blocking、可豁免）；未运行只给非阻断 warn。gate_check 没有 overall errors==0 检查，也没有 WARN 逐条处置。

evidence: C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/gate_check.py:1691-1700；C:/Users/jlc/work/hds-pcb-round9/design-hardware/references/design-gates.md:173；easyeda pcb check --help

### 阶段4 实测解析缺陷：parse_pcb_check 只用 findings[].code/rule/category 分类，真实 pcb-check JSON 的 finding 类型字段是 type；它也不读取 summary。对两个案例实测 counts 均为 {'unknown': 14} 与 {'unknown': 6}，于是 G4 输出 'power-not-poured=0' 并 pass，尽管 MCU summary.powerNotPoured=1、photo summary.powerNotPoured=2。这是新 pcb_gate 必须修复的实质 bug。

evidence: C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/gate_check.py:716-741,1695-1698；C:/Users/jlc/work/hds-pcb-round9/design-hardware/cases/mcu-i2c-s3-2026-10-26/evidence/pcb-check-final.json:19,33-35,183；C:/Users/jlc/work/hds-pcb-round9/design-hardware/cases/photo-led-pcb-2026-10-26/evidence/pcb-check-final.json:19-24,33-35（本机 import gate_check.parse_pcb_check 实测 counts={'unknown':14}/{'unknown':6}）

### 阶段5 key net-path：逐网命令为 `easyeda pcb net-path --from D.PAD --to D.PAD --net <net> --json --project <name> --doc <PCB> > evidence/net-path-<net>.json`，支持 --through 有序中间 pad、--layer 限定单层；只证明 listed routed line/arc/via/pad 铜，不覆盖铺铜/填充/PLANE。案例使用聚合文件 netpath-key-connections.json，字段为 rows[]{from,to,net,status,length_mil,vias,layers,path_kind}（photo 另有 widths[]），本批全部 status=connected、path_kind=exact-centerline。

evidence: C:/Users/jlc/work/hds-pcb-round9/design-hardware/references/design-gates.md:194,200；C:/Users/jlc/work/hds-pcb-round9/design-hardware/cases/mcu-i2c-s3-2026-10-26/evidence/netpath-key-connections.json:1-188；C:/Users/jlc/work/hds-pcb-round9/design-hardware/cases/photo-led-pcb-2026-10-26/evidence/netpath-key-connections.json:1-216；easyeda pcb net-path --help

### 阶段5 门禁语义：gate_check G5 要求 design-state routing.key_nets 非空，且每个网满足其一——routing.key_net_proofs[net].found=true 且 evidence 路径存在（只查文件存在，不解析内容），或发现一条 parse_net_path 结果为 found=true 且 net/from/to/文件名匹配的逐网证据；任一网缺证明即 fail/BLOCKED 且不可豁免。该实现是部分实现：聚合文件不被角色发现（文件名无 net-path），state 证明可自证 found；net_path 解析支持 found/ok + net/from/to/path，但没有聚合 rows 解析，也没有 capture 身份/新鲜度绑定。

evidence: C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/gate_check.py:891-915,1735-1788；C:/Users/jlc/work/hds-pcb-round9/design-hardware/references/design-gates.md:193-200；C:/Users/jlc/work/hds-pcb-round9/design-hardware/cases/mcu-i2c-s3-2026-10-26/README.md:34；C:/Users/jlc/work/hds-pcb-round9/design-hardware/cases/photo-led-pcb-2026-10-26/README.md:32

### 阶段6 SCH-PCB 逐脚对账：回读命令为 `easyeda sch read --project <name> --out sch-read.json`（或 `easyeda sch connectivity --all-pages`）与 `easyeda pcb dump --project <name> --doc <PCB> --include-copper --out board.json` / `easyeda pcb list --include-pads`。案例聚合证据 sch-pcb-compare.json 字段为 status、schematic_components、pcb_components、pins、mismatches[]；MCU 为 23/23、104 脚、match、mismatches=[]，photo 为 19/19、47 脚、match、mismatches=[]。仓库没有生成该聚合文件的脚本，它是案例作者临时对账的产物。

evidence: C:/Users/jlc/work/hds-pcb-round9/design-hardware/references/pcb-execution.md:31-37；C:/Users/jlc/work/hds-pcb-round9/design-hardware/cases/mcu-i2c-s3-2026-10-26/evidence/sch-pcb-compare.json:1-7；C:/Users/jlc/work/hds-pcb-round9/design-hardware/cases/photo-led-pcb-2026-10-26/evidence/sch-pcb-compare.json:1-7；easyeda sch read --help / easyeda sch connectivity --help

### 阶段6 现有实现只在 design_engine pcb-audit：`python design_engine_cli.py pcb-audit --bundle <dir> --sch-ir <ir.json>`；_reconcile_pin_pads 逐 designator、逐 pin number 比较 sch pin net 与 pcb pad net，输出 status=match|review、issues[]（component_missing_in_pcb/pad_number_not_directly_comparable/pad_net_mismatch/component_missing_in_schematic）、coverage。audit_pcb 输出 schema=design-engine-pcb-audit/v1、status=blocked|incomplete|pass、findings、hard_count、checks_run/skipped、drc、pin_pad_reconciliation、electrical_verified=false、visual_verified=false。

evidence: C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/design_engine/pcb.py:333-376,379-466；C:/Users/jlc/work/hds-pcb-round9/design-hardware/references/design-engine.md:4.6 pcb-audit 命令段

### 阶段6 与案例不兼容：pcb-audit 的 bundle 固定读取 pcb-dump.json、pcb-drc.json、pcb-check.json，案例文件名是 pcb-dump-final.json/pcb-drc-final.json/pcb-check-final.json；--sch-ir 需要 design-engine-ir/v1，案例只有 sch-connectivity.json / sch-read.json，没有 ingest 出的 IR。另外当前比较器按 pin number 逐字匹配，J1 的 A1B12/A4B9/B1A12 等组合脚会被报 pad_number_not_directly_comparable，无法复现案例声称的 0 mismatch；需要显式组合脚映射与重复 pad 号保留规则。

evidence: C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/design_engine/pcb.py:43-51,333-376；C:/Users/jlc/work/hds-pcb-round9/design-hardware/cases/mcu-i2c-s3-2026-10-26/evidence/sch-connectivity.json（pins 含 A1B12/A4B9 等）；同目录 sch-pcb-compare.json:1-7；C:/Users/jlc/work/hds-pcb-round9/design-hardware/references/design-engine.md:1（bundle 文件表）

### 阶段7 save→reload→fresh dump pcb-diff：命令为 `easyeda pcb save --project <name> --doc <PCB>`；`easyeda doc reload <PCB> --project <name> --json`；`easyeda pcb dump --project <name> --doc <PCB> --include-copper --out after.json`；`python design_engine_cli.py pcb-diff --before before.json --after after.json --scope scope.json --json`。输出 schema=design-engine-pcb-diff/v1、status=match|changed|mismatch、identity_changes[]、geometry_changes[]、copper_changes[]、unrelated_changes[]、counts{identity,geometry,copper,unrelated}、scope、note；语义为无任何变化才 match，有变化且 unrelated 为空为 changed，unrelated 非空为 mismatch。

evidence: C:/Users/jlc/work/hds-pcb-round9/design-hardware/references/pcb-execution.md:194-220；C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/design_engine/pcb_workflow.py:1789-1920；C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/design_engine/cli.py:991-998,667-679

### 阶段7 现有门禁语义：gate_check 只认 reopen_check 角色（*reopen*.json 或 *reload*readback*）且 parse_reopen 要求 match=true，或 design-state routing.save_reload 的 status 为 pass/confirmed 等；缺回读则 fail/BLOCKED 不可豁免。它不读 save-reload-diff.json，也没有 scoped-edit 的 unrelated_changes 语义。已实现 pcb-diff 本体与 pcb_apply_plan 的 save/reload/fresh dump 适配器，但 gate 侧只是部分实现。

evidence: C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/gate_check.py:918-929,1799-1810；C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/pcb_apply_plan.py:124-145；C:/Users/jlc/work/hds-pcb-round9/design-hardware/references/design-gates.md:196

### 阶段7 案例证据：两个案例的 save-reload-diff.json 均为 status=match、四个 changes 数组为空、counts 全 0；两板 before/after dump 的 semanticSha256 分别完全相同（MCU a8345917...，photo 6f9dae9a...），capture.documentUuid/projectUuid 也一致。局部改板 edit-add-decap-save-reload-diff.json 同样 match；edit-add-decap-scoped-diff.json 为 status=changed、identity +1(C99)、copper 135、unrelated []、counts.unrelated=0、scope.designators=[C99]、scope.nets=[+3V3,GND]，说明 scoped 编辑不能用 match 作为唯一通过条件。

evidence: C:/Users/jlc/work/hds-pcb-round9/design-hardware/cases/mcu-i2c-s3-2026-10-26/evidence/save-reload-diff.json:1-16；C:/Users/jlc/work/hds-pcb-round9/design-hardware/cases/photo-led-pcb-2026-10-26/evidence/save-reload-diff.json:1-16；两目录 pcb-dump-final.json 与 pcb-dump-after-reload.json 的 semanticSha256/capture 字段；C:/Users/jlc/work/hds-pcb-round9/design-hardware/cases/mcu-i2c-s3-2026-10-26/evidence/edit-add-decap-save-reload-diff.json:1-16；同目录 edit-add-decap-scoped-diff.json:3,553-568

### 阶段7 一个可靠性反例：placement-apply-report.json 顶层 status=mismatch，reload.ok=false、dump.ok=false，但其 diff 为 status=changed、identity/copper/unrelated 全空、只有 23 条 scoped pose_changed；用当前 pcb_apply_plan.expected_placement_diff 重算该 diff 返回 True。说明 wrapper 的 status/reload.ok 不能直接作为 gate 结论，新门禁应从 diff 字段和实际 dump 重新计算。

evidence: C:/Users/jlc/work/hds-pcb-round9/design-hardware/cases/mcu-i2c-s3-2026-10-26/evidence/placement-apply-report.json:2,320-333,707-743；C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/pcb_apply_plan.py:54-59,139-145（本机重算 expected_placement_diff=True）

### 阶段8 WARN 处置表+图片：目前没有任何 schema、解析器或 gate 检查。gate_check 的豁免只到 gate/check 级别（find_waiver 按 gate 或 G3 短名 + check id 匹配，reason>=4 字符），不能对单条 pcb-check finding 做处置；也没有 PCB 图片角色，只有 G2 的 schematic_png/png_review。当前案例用 README 人工表：MCU 第 3 节问题处置表和第 6 节剩余 WARN（13 WARN/0 ERROR），photo 第 3 节与第 6 节（6 WARN/0 ERROR）；这些表不是机器可校验证据。

evidence: C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/gate_check.py:1108-1120,1385-1401,109-130（无 PCB image role）；C:/Users/jlc/work/hds-pcb-round9/design-hardware/cases/mcu-i2c-s3-2026-10-26/README.md:40-52,98-110；C:/Users/jlc/work/hds-pcb-round9/design-hardware/cases/photo-led-pcb-2026-10-26/README.md:40-51,98-105

### 阶段8 图片证据现状：两案例都有 pcb-final-top.png、pcb-final-bottom.png、pcb-final-actual.svg；PNG 均有效（signature 正确、1608×714），但没有任何 viewed/审核元数据文件。mtime 显示 MCU 的 pcb-check-final.json(13:38:57Z) 与 pcb-drc-final.json(13:39:01Z) 早于最终 pcb-dump-final(13:40:13Z)/after-reload(13:40:45Z)；photo 的 netpath(12:48:37Z)、sch-pcb-compare(12:50:25Z)、top/bottom PNG(12:49:05-48Z) 早于最终 dump/check(12:51:18-29Z)。若严格按“最终保存后重跑”语义，这些证据带 STALE_EVIDENCE 风险。

evidence: C:/Users/jlc/work/hds-pcb-round9/design-hardware/cases/mcu-i2c-s3-2026-10-26/evidence/（pcb-final-top.png 192823B、pcb-final-bottom.png 102986B、pcb-final-actual.svg 76782B；mtime 如上）；C:/Users/jlc/work/hds-pcb-round9/design-hardware/cases/photo-led-pcb-2026-10-26/evidence/（top 164801B、bottom 144024B、svg 65936B；mtime 如上）；C:/Users/jlc/work/hds-pcb-round9/design-hardware/references/pcb-execution.md:245

### gate_check 当前 G3/G4/G5 的检查集合：G3 包含 evidence_freshness、layout_lint_score/crossings/geometry、silk_over_pad(warn)、board_outline、mounting_holes、connector_escape、auto_place_comparison、layout_frozen；G4 包含 stackup_declared/decision/power_ground_strategy/inner_layers/drc_rules_recorded、gnd_pours、gnd_thin_traces、via_audit、pcb_check_power；G5 包含 pcb_drc_passed、connection_errors、key_nets_declared、key_net_proofs、routing_plan、save_reload、silk_over_pad、stop_rule。

evidence: C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/gate_check.py:1415-1567,1572-1701,1706-1848；C:/Users/jlc/work/hds-pcb-round9/design-hardware/references/design-gates.md:138-204

### gate_check 的跨工件新鲜度/身份绑定很有限：只有 G3 比较 layout-lint 与 board dump 的 mtime/组件数，以及 G4 检查 via 证据的 staleRisk；DRC、pcb check、net-path、SCH-PCB 对账、diff 都没有校验 projectUuid/documentUuid/capturedAt/semanticSha256，也不要求它们晚于最终 save/reload。

evidence: C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/gate_check.py:1425-1444,1667-1669；其余解析器 650-741,891-929 均无 capture 字段检查；C:/Users/jlc/work/hds-pcb-round9/design-hardware/cases/.../evidence/pcb-dump-final.json 的 capture/semanticSha256 字段

### gate_check 很多关键检查依赖 design-state 自述布尔值：requirement_status 把 status=confirmed/pass/done/verified/applied 直接当 pass，把 assumed 当 warn；G5 的 routing_plan、save_reload（无 reopen 证据时）、silk_align 都可能仅凭 state 通过，G4 的 drc_rules_recorded 也可仅凭 stackup 字段。PASS 不等于每个证据文件都被解析和绑定。

evidence: C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/gate_check.py:1123-1162,1560-1566,1615-1621,1790-1827

### design_engine CLI 退出码语义与 gate 需求不同：pcb-constraints 仅 status=compiled 时 exit 0；pcb-check-plan 仅 status=pass 时 exit 0；pcb-diff 仅 status=match 时 exit 0（scoped 编辑的 changed 会 exit 1）；pcb-power/pcb-fabrication 仅 status=pass 时 exit 0；参数/IO/schema 错误由 main 统一 exit 2。新 pcb_gate 必须读 JSON 字段，不能拿子命令退出码直接当门禁结论。

evidence: C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/design_engine/cli.py:608,626,679,696,711,1060-1067；C:/Users/jlc/work/hds-pcb-round9/design-hardware/references/design-engine.md:4（退出码 0/1/2）

### 现有自动测试只覆盖 temp-alarm 回归案例：test_gate_check.py 的 RegressionCase/CLI 测试固定 temp-alarm，FullPassFixture 用合成证据；没有针对 photo-led 或 mcu-i2c 案例的 gate 回归，也没有 pcb-check power-not-poured 解析的反例测试。

evidence: C:/Users/jlc/work/hds-pcb-round9/tests/test_gate_check.py:17,128-170,172-382；C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/skill_selftest.py:54,355-513（仅 CASE_REL=temp-alarm）
