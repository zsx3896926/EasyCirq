# stack

## summary

只读侦察完成：仓库 C:/Users/jlc/work/hds-pcb-round9，HEAD 60f2f2c；未修改任何文件，未执行任何 EDA 写入或 easyeda 命令。pcb_workflow.py 是 2027 行、纯离线、仅标准库的几何/约束引擎，提供 normalize_board、compile_constraints、validate_placement、模板绑定、三候选、逃线代理、制造/电源审计、diff_boards 等公共契约。pcb_apply_plan.py 是 152 行适配器：校验整板 placement 计划后，逐件调用外部 easyeda pcb modify --id <primitiveId> --patch '{x,y,rotation,layer}'，再 save → doc reload → pcb dump --include-copper → scoped diff；默认 dry-run。eda_exec.py 是另一套 lceda-pro 桥，PCB 写 op 只有 line/via/pour_outline/component_flat/component_search，但其 snapshot integrity、typed plan 校验、readback verify、save 确认和 reopen compare 是 gate/apply 的最佳范式。四个新工具可大量复用离线校验和 eda_exec 的验证纪律，但必须先补 write-ready playbook schema、preflight 身份/primitiveId/完整 pose 校验、reload 后重新解析 ID、save/reload 证据门，以及针对 copper/layer/silk/pour 的 gate 语义。外部 easyeda CLI 契约对照了本机源码 checkout C:/Users/jlc/work/_round6-scratch/easyeda-agent-src（案例记录安装版 1.15.0）。

## gaps

- 缺少 write-ready 批处理 schema：candidate/joint_plan 只给 placements，不生成 base_semantic_sha256、primitive_ids、expected final poses 和 scope；pcb_apply_plan 接受任意整板 placements list。
- preflight 缺结构化输入校验：project/doc 与 dump.capture 一致性、primitiveId 存在/唯一、locked/group、client version/write support、live-vs-dump freshness、完整 pose 都未检查；畸形输入抛 traceback。
- 验证与写入对省略 rotation/layer 的语义不同（apply_placements 保留实测值，写 patch 默认 0/1）。
- preferred 约束失败仍生成 hard finding，阻塞 hard_ok。
- validate_placement 强制整板计划（unplaced_component），pcb_apply_plan 的 diff scope 又是全部 designator，unrelated 保护很弱。
- save/reload/dump 不 gate，唯一检查是 out_dump 文件存在；dump 成功信息走 stderr，stdout JSON 解析不可靠。
- primitiveId 跨 reload 不稳定，当前适配器没有 reload 后 re-dump/re-resolve 阶段。
- expected_placement_diff 只适合纯 placement：copper/layer 变化一律失败，silk/poured/pad 几何/net metrics 不比较，无法 gate 布线/铺铜/丝印 playbook。
- diff_boards/gate_check 需要 raw dump；normalized board 会丢 uniqueId/padNumber/copperLayers，不能直接互喂。
- skill 内没有 DRC/check/net-path/connectivity 解释，eda_exec 的 DRC 只有 raw；gate 缺这些证据。
- pcb_apply_plan 无 batch/journal/resume/checkpoint/timeout/retry/幂等/version/concurrency/group 处理。
- pcb_case 没有 manifest/schema/artifact SHA/README 数值交叉核对；state.py 的 design-engine-state/v1 与 gate_check.py 的 design-state/v1 不兼容。
- 没有 manufacturing export gate；案例记录 Gerber/drill/CPL 仍 BLOCKED。
- 容差/几何不一致：fixed 1e-6 vs readback 0.01；normalized outline 比 raw bbox 小约 5 mil；bbox 含丝印/属性。
- 真实 apply 路径没有单测：只有 expected_placement_diff 和 dry-run/refusal 测试（tests/test_pcb_workflow.py:315-359）。

## recommendations

- 定义 versioned design-engine-pcb-playbook/v1：board identity(project/doc/semantic hash)、primitive_ids、ops[{op,designator,pose{x,y,rotation,layer},reason}]、expected_final_poses、scope{designators,nets,bbox}、policy(tolerance/save/reload/diff)；要求完整 pose，禁止隐式 0/1。
- pcb_preflight.py 作为该 playbook 的生产者和校验器：normalize dump→coverage gate→compile_constraints（status 必须 compiled）→validate_placement→primitiveId/hash/project/doc/locked/group/version→target vs current→predict_escapes/audits；输出 status ready|blocked|incomplete + blocking/advisory + evidence，exit 0/1/2；捕获 ValueError/TypeError。
- 升级 pcb_apply_plan.py：优先把 playbook 编译成 easyeda apply 的 action 步（pcb.component.modify）或 run 步（pcb modify --patch-file），利用 preflight/journal/fail-fast/verify；按 apply→save→reload→dump→verify 分阶段，save 必须 saved==true，reload 成功后才 dump，dump 后重新解析 primitiveId。
- pcb_gate.py 定义为阶段 gate：preflight ready、每条 apply record verified、save/reload proof、after dump coverage complete 且 capture identity 一致、expected final pose 在 0.01 mil 内、diff 的 identity/copper/unrelated 明确、audit_fabrication/audit_power、DRC/pcb check、关键 net-path；输出 PASS/WARN/BLOCKED/NOT RUN + evidence hashes。
- gate 不要只用 expected_placement_diff：对 copper/layer/silk/pour playbook 扩展 scope 到 nets/bbox 并按类别比较；layer flip 用显式 expected layer 验证；preferred 约束作为 advisory；修掉 validate_placement 的 finding severity 问题或在 gate 里过滤。
- pcb_case.py 建立在 state.py+gate_check 之上：case manifest（case id、project/doc identity、artifacts+sha256、evidence roles、gate report、claim 状态）；复用 add_evidence/verify_evidence 和 gate_check discover/parse/waiver；统一 design-engine-state/v1 或做 schema 转换；校验 README 数字与 JSON 一致。
- 保留双几何源：pcb dump 用于 bbox/pad/copper 的几何/电气 gate；eda_exec snapshot 只用于 live identity/class coverage；任何 diff/gate_check 输入保持 raw dump，不传 normalize_board 输出。
- 为 apply/gate 增加 fake easyeda 集成测试：成功、partial、save false、reload fail、dump missing、diff mismatch、ID churn、省略 pose、preferred constraint、partial plan；目前只有 dry-run/refusal 和 predicate 测试。
- 所有报告记录 argv、client version、project/doc UUID、dump semantic hash/capture.json SHA、per-op verified/applied、save saved、reload 结果、diff scope；这些是 case 证据与 gate 的输入。
- 对布线/铺铜/丝印 op 明确能力边界：外部 CLI 有 typed track/via/pour/silk 命令，但当前 skill 的 diff/verify 不覆盖；在扩展前不要用 expected_placement_diff 宣称这些 op 已验证。

## facts

### pcb_workflow.py 的契约是纯离线、仅标准库、绝不连接 EDA 或写工程；它定义 board/constraints/placement/template/candidates/escapes/diff/power 等 schema，并对缺失 bbox/pad/net/outline 采用 fail-closed（incomplete/unmeasured，不转成 pass）。

evidence: C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/design_engine/pcb_workflow.py:1-13,21-36

### normalize_board(dump) 输入原始 pcb dump 对象，输出 {schema:'design-engine-pcb-board/v1', source{project_uuid,project_name,document_uuid,captured_at,semantic_sha256}, units:'mil', outline{points,bbox,area_mil2,source,format}, layers{copper_count}, rules, components[], silk, copper, pours, poured, coverage, not_checked}；component 含 id/primitive_id/unique_id/designator/name/device/layer/x/y/rotation/bbox/pads/native，pad 含 id/primitive_id/number/net/layer/x/y/width/height/rotation/shape/native。

evidence: C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/design_engine/pcb_workflow.py:165-203,229-251

### coverage 显式区分 complete/partial/absent：components 仅在 dump.availability.components=='available' 时 complete，outline 仅在有 points 时 complete；courtyard 永远 absent，用 measured rendered bbox 替代，not_checked 列出铺铜连通、impedance/EMC/thermal、丝印可读性和制造文件。normalized outline bbox/area 由 outline.points 重算，不复制 dump.outline.bbox；photo-led fixture 原始 maxX=3548.3，normalized=3543.3（测试断言 3543.3）。

evidence: C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/design_engine/pcb_workflow.py:204-228,249-250; C:/Users/jlc/work/hds-pcb-round9/tests/test_pcb_workflow.py:46-56

### transform_component(component,x,y,rotation=None,layer=None) 把实测 anchor 移到 (x,y)，按 (target-source) CCW 旋转局部几何；当 layer 改变时关于 anchor 的 x 轴镜像局部几何，旋转 bbox/pads，只翻转 SMD pad 的层（THT pad 保持 layer 12 MULTI）。apply_placements(board,placements) 深拷贝 board 并整条替换 normalized component；x/y 是 anchor 不是 bbox 中心；designator 必填、不可重复且必须已实测；rotation/layer 省略时保留实测值。

evidence: C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/design_engine/pcb_workflow.py:254-296,299-322

### compile_constraints(intent,board) 返回 {schema:'design-engine-pcb-constraints/v1', status:compiled|incomplete|conflicted, constraints[], conflicts[], unknown[], counts, note}；每条约束必须有合法 type（fixed/edge/near_pin/ordered_chain/keepout/allowed_layer/allowed_rotation/group/route_channel）、severity hard|preferred 和非空 source；距离统一换算为 mil 并保留 native_unit；未知 designator/pad 进入 unknown 而不是丢弃；intent.keepouts 自动补成 hard keepout。status 只在 hard conflict 时 conflicted（edge_fixed_requires_pose_check 不算 hard），有 unknown 则 incomplete。

evidence: C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/design_engine/pcb_workflow.py:32-36,341-382,510-585

### validate_placement(board,plan,constraint_set=None,placement=None) 接受 placement list 或 {placements:[...]}，返回 {schema:'design-engine-pcb-placement/v1', status:pass|review, hard_ok, findings[{code,severity,objects,message,evidence}], constraints[rows], counts, measurement_note}；hard_ok 只有在无 hard finding、无 hard 约束行 fail、无 hard 约束行 unmeasured 时才为 true。

evidence: C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/design_engine/pcb_workflow.py:611-627,697-704,880-899

### validate_placement 的 stale 防护是 opt-in：只有 plan 带 base_semantic_sha256 时才与 dump semantic hash 比较，只有带 primitive_ids 时才逐件比较；不匹配报 stale_plan/stale_plan_object（hard）。plan 是 list 或缺少这两个键时完全不做 staleness 检查。它还要求每个实测 component 都出现在 placements 中，否则报 hard unplaced_component 并保留 reference pose，因此 pcb_apply_plan 无法接受局部计划；通用检查还包括 outline 必须实测、bbox 必须实测、body 在 outline 内（5 mil 容差）、pad 中心在 outline 内、同层 bbox 重叠。

evidence: C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/design_engine/pcb_workflow.py:631-696

### 约束行覆盖 fixed（1e-6 pose 精确匹配）、edge（max_inset/facing_rotation；min_inset 虽被 compile 解析但 validate 从未执行）、near_pin（仅 pad 中心欧氏距离，copper_path_verified=false）、ordered_chain（bbox 中心投影）、keepout、allowed_layer、allowed_rotation、group（bbox spread）、route_channel（bbox 相交）。注意：所有约束分支都用 severity 'hard' 生成 finding，即使声明的 severity 是 preferred；离线复现中一个 preferred allowed_rotation 失败产生 hard finding 且 hard_ok=False，而行 severity 仍是 preferred。

evidence: C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/design_engine/pcb_workflow.py:398-409,701-704,719-746,759-778,803-818,829-845,859-873,880-888

### load_templates(path=None) 校验 design-engine-pcb-templates/v1 并返回模板文档；bind_template(template,binding,board) 返回 {schema:'design-engine-pcb-template-plan/v1', template, status:bound|rejected, reasons[], roles{role:{designator,pads{pin:{pad,net,x,y,layer,width,height}}}}, net_groups, note}，拒绝缺失 designator/pad、net role 不一致、缺 bbox 和 bbox 尺寸条件不满足；template_placements(...) 返回 {schema, template, status:planned|incomplete|rejected, reasons, placements[{designator,x,y,rotation,layer,role}], core, note}，frame=core 的偏移随核心旋转，frame=board 保持在板坐标，缺 relative 条目明确 incomplete。

evidence: C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/design_engine/pcb_workflow.py:902-929,932-1017,1020-1080

### plan_candidates(board,intent,templates,constraint_set=None) 要求 intent.modules、board outline 和可绑定的 templates，生成 signal-chain/density/mechanical 三个候选；候选含 placements、hard_ok、hard_findings、constraint_report、near_pin_failures、escape_blocked、hpwl_mil、module_area_mil2；非模块器件以 reference pose 加入（因此是整板计划）；选择顺序为 hard 合法性→near-pin 失败数→阻塞逃线数→HPWL→模块面积→策略优先级，不输出加权总分。joint_plan 在其上增加预算化 trial 回调（或 escape proxy），返回 selected candidate、history 和 budget。

evidence: C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/design_engine/pcb_workflow.py:1115-1155,1176-1242,1244-1356,1359-1417

### predict_escapes(board,length_mil=100,...) 返回 {schema:'design-engine-pcb-escapes/v1', status:complete|incomplete, length_mil, clearance_mil, pads[{pad,net,status:blocked|clear|unknown,direction,length_mil,blockers,corridor}], counts, proxy:true, routing_verified:false}；它把 pad 相对 bbox 中心的方向吸附到主轴，用走廊检查 outline、其他 component bbox 和注入的 keepouts；pad width/height 缺失按 0 处理，clear 不等于可布。

evidence: C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/design_engine/pcb_workflow.py:1420-1497

### extract_pcb_module(board,members,anchor=None) 返回 {schema:'design-engine-pcb-module/v1', anchor, members[{designator,device,unique_id,layer,bbox,relative{dx,dy,rotation},pad_nets}], nets, copper_reuse:{status:'not_supported',...}}；plan_pcb_reuse(module,target_board,binding,anchor_pose,constraints=None,net_map=None,allowed_substitutes=None) 返回 {schema:'design-engine-pcb-reuse-plan/v1', status:planned|rejected, reasons, placements, copper_reuse}，要求 device 身份一致（或显式替代）、layer 相同、pad 号集合和映射后网络一致；只有传入 constraints 时才跑 validate_placement。

evidence: C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/design_engine/pcb_workflow.py:1500-1553,1556-1646

### audit_fabrication(board) 返回 {schema:'design-engine-pcb-fabrication/v1', status:review|pass|advisory, findings[], counts{silk_items,visible_silk,pours,vias,findings,hard}, coverage, checks_skipped, note}；检查 layer 3/4 可见丝印的 bbox 缺失/越框/横置/镜像和同面焊盘重叠、铺铜无 net/无 geometry/无 materialized fill、过孔无 net 和过孔在焊盘内 net 不符。audit_power(board,intent) 返回 {schema:'design-engine-pcb-power/v1', status:pass|review, nets[], decaps[], failed[], unmeasured[]}；track 策略用 IPC-2221 计算 required width 并比较实测最小 lineWidth，pour 策略只证明存在该 net 的铺铜对象，decaps 只统计 role 为 decap/bulk/bypass 的 near_pin 约束（pad 中心距，copper_path_verified=false）。

evidence: C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/design_engine/pcb_workflow.py:1660-1786,1923-1934,1937-2027

### diff_boards(before,after,scope=None) 返回 {schema:'design-engine-pcb-diff/v1', status:match|changed|mismatch, identity_changes[], geometry_changes[], copper_changes[], unrelated_changes[], counts, scope, note}；scope 支持 designators/nets/bbox，空 scope 表示全部 in-scope，任何 unrelated change 都判 mismatch。它比较 component 的 uniqueId/device/layer/pad-net 映射和 pose(x,y,rotation,layer)、outline points、rules keys、copperLayers，以及 copper lines/vias/pours；save/reload 后 copper primitiveId 会变，先用 id 匹配，再用 net/layer/geometry/width 的 semantic twin 匹配。

evidence: C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/design_engine/pcb_workflow.py:1789-1920

### diff_boards 和 gate_check.parse_board 需要原始 dump 字段，不是 normalize_board 输出：diff 使用 component.uniqueId（原始）而不是 unique_id（normalized）、pad.padNumber 而不是 pad.number、dump.copperLayers 而不是 layers.copper_count；normalized board 会丢掉 uniqueId/copper layer 变化，并把多 pad 的 net 比较压成一个键。diff_boards 还完全不比较 silk、materialized poured fills、pad 几何和 net 指标。

evidence: C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/design_engine/pcb_workflow.py:190-203,229-247,1823-1826,1841-1855; C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/gate_check.py:744-810

### 现有 CLI 已把离线引擎暴露为 pcb-normalize/pcb-constraints/pcb-check-plan/pcb-candidates/pcb-escapes/pcb-diff/pcb-power/pcb-fabrication/pcb-template-plan/pcb-extract-module/pcb-reuse-plan；退出码约定是 0 pass/no candidates、1 review/blocked/mismatch、2 invalid input。pcb-diff 只在 status=='match' 时返回 0，这对预期发生 placement 变化的 apply 太严格，gate 应直接调用 diff_boards 或用 apply 自己的 predicate。

evidence: C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/design_engine/cli.py:1-5,581-771,946-1013

### pcb_apply_plan.py 是 152 行适配器，CLI 为 --dump（before）、--plan、可选 --constraints、--project、--doc、--out-dump、可选 --report、--apply；默认 dry-run；JSON 用 utf-8-sig 读取；plan 必须提供 placements list，否则输出 {status:'invalid_input'} 并返回 2。

evidence: C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/pcb_apply_plan.py:62-82

### 写入前它调用 validate_placement(board,plan,constraint_set)；hard_ok 为 false 时输出 {status:'refused',check,records:[],note} 并返回 1，不写任何东西；否则 report.status 在 dry-run 时为 dry_run，在 --apply 时为 applied。它不检查 constraint_set.status（conflicted/incomplete 也会继续），也不检查 dump.coverage。

evidence: C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/pcb_apply_plan.py:75-92

### 每个 placement 的 patch 固定为 {'x':float(item['x']),'y':float(item['y']),'rotation':float(item.get('rotation',0)),'layer':int(item.get('layer',1))}，随后执行且只执行：easyeda pcb modify --project <project> --doc <doc> --id <component['primitive_id']> --patch <compact JSON>。primitiveId 来自当前 normalized dump，不来自 plan.primitive_ids；patch 是内联 --patch，没有使用 --patch-file。

evidence: C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/pcb_apply_plan.py:93-106

### _run 用 subprocess.run(capture_output=True, encoding='utf-8') 且只把 stdout 当 JSON 解析；非 JSON 输出变成 {ok:false,stdout,stderr}。只有 returncode==0 且 payload.ok 为真才记 status:'applied'，并记录 verified/applied/error；第一个非 applied 或 verified 不是 exactly True 的器件会置 status:'partial_failure' 并 break。dry-run 记录 command 并返回 0；apply 的部分失败在 save 前返回 1。

evidence: C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/pcb_apply_plan.py:28-36,107-123

### 全部器件 verified 后依次执行：easyeda pcb save --project <p> --doc <d>；easyeda doc reload <d> --project <p>；easyeda pcb dump --project <p> --doc <d> --include-copper --out <out_dump>。save/reload/dump 的 payload 只被记录，返回码和 ok/saved 标志都不检查；唯一 gate 是 os.path.isfile(out_dump)。真实 CLI 带 --out 时把成功行打到 stderr，因此 dump 的 payload 通常是 {ok:false,stdout:'',stderr:'...'} 而文件本身有效。

evidence: C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/pcb_apply_plan.py:124-137; C:/Users/jlc/work/_round6-scratch/easyeda-agent-src/internal/app/cmd_pcb_dump.go:72-92

### 最后加载 after dump，调用 diff_boards(before,after,{'designators':[每个 placement 的 designator]})，并用 expected_placement_diff 判定：diff.status in (match,changed) 且 identity_changes/copper_changes/unrelated_changes 都为空。纯 geometry 变化是预期成功；任何 copper 变化、layer 变化（layer 属于 identity）、组件增删、scope 外的 rules/outline 变化或 unrelated 变化都判 mismatch（verified 返回 0，否则 1）。

evidence: C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/pcb_apply_plan.py:54-59,138-147; C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/design_engine/pcb_workflow.py:1825-1840,1841-1855,1910-1911

### 验证与写入在省略 pose 字段时不一致：apply_placements/transform_component 对 None 保留实测 rotation/layer，而写入 patch 默认 rotation=0、layer=1；离线复现中 apply_placements 对 J1 保留 rotation=-90，而适配器会发送 0。批处理 playbook 必须要求完整 pose（x,y,rotation,layer）或显式从 dump 取默认值。

evidence: C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/pcb_apply_plan.py:101-103; C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/design_engine/pcb_workflow.py:265-268,317-319

### pcb_apply_plan 不过滤 no-op：它写入 plan 中的每一条，包括 plan_candidates 为所有非模块器件加入的 reference pose。结合 unplaced_component 的整板要求和 diff scope=全部 placement designator，一个 23 器件计划会发 23 次 pcb modify，并把所有 designator 都放进 scope；因此任何器件的 pose 变化都会被归为 in-scope geometry，而不会作为 unrelated 被抓住。

evidence: C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/pcb_apply_plan.py:94-106,139; C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/design_engine/pcb_workflow.py:653-657,1196-1205

### eda_exec.py 是另一套执行器：通过 lceda-pro/eda 命令空间和固定 JS 模板工作，不调用 pcb modify。它已校验的 PCB 写 op 只有 line、via、pour_outline、component_flat、component_search；component_move、component_rotate、delete、rule_config_write 标为 not_probed，板框 layer 11 创建和铺铜 fill 重算标为 known_broken。

evidence: C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/eda_exec.py:1-25,1081-1142,2938-2964

### read_pcb_snapshot/read_pcb_with_retry 返回 live snapshot：env、project、pcbs、selection{pcb_uuid,pcb_name}、counts、component rows（id/designator/layer/x/y/rotation/footprint/component refs）、lines、vias、pours、poured、pad rows（只有 id/net）、nets(net,length,primitive_count)、outline line ids/count、rule_config、read_errors、field_notes；没有 bbox、pad 几何、silk、rules 具体值，不能替代 pcb dump 做 placement/几何 gate。

evidence: C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/eda_exec.py:932-1078,2975-3006

### pcb_snapshot_integrity 要求 components/lines/vias/pours/poured/pads 都有 counts、有 pcb_uuid、无 class-level read errors、无 truncated rows、count/total 一致；status 为 complete|incomplete。validate_pcb_plan 定义 version-1 typed creation plan：items 1..200、key 唯一、每 op 有必填/未知字段检查、坐标 finite、width/hole/diameter/w/h 为正、component layer 1|2、copper layer 1..64。

evidence: C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/eda_exec.py:2938,3024-3149

### reconcile_pcb 校验 pcb_uuid、net 存在、line 端点去重、via net+位置去重、pour net/layer/name 去重（component 永远 create 不去重）；verify_pcb_items 只用 execution response 解析 primitive id，所有比较字段从 after snapshot 读取，缺 result/create 失败/无 id/readback 缺失/必读字段不可读都判失败，浮点容差 0.01，并报告 pour fill delta；compare_pcb_snapshots 比较 pcb identity、class counts、对象增删、逐字段几何、nets 和 net metrics，字段不可读时 complete=false。

evidence: C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/eda_exec.py:3167-3217,3220-3333,3335-3432

### command_pcb_apply 是现有最强的 apply/gate 范式：before snapshot incomplete 直接拒绝；reconcile 有 conflict 默认不写；临时 owned session 必须 --save；客户端版本必须在 VERIFIED_CLIENT_PREFIXES=('4.1.78',)（否则拒绝，除非 --allow-unverified-version）；invoke timeout 记 partial_unknown 且不重放；after snapshot 必须 complete 且 pcb_uuid/project uuid 不变；逐 item verify 后才允许 save，且 save 必须返回 saved==true；command_pcb_reopen_check 关闭/重开并 compare snapshots。

evidence: C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/eda_exec.py:79-81,4079-4209,4212-4227,4438-4494

### pcb_preflight.py 可直接复用的部分：normalize_board/coverage/source、compile_constraints、validate_placement（hard_ok/findings/rows）、predict_escapes、audit_fabrication/audit_power、diff_boards，以及 eda_exec 的 pcb_snapshot_integrity/read_pcb_with_retry 做 live identity/coverage。缺口：没有 write-ready plan schema；没有 primitiveId 存在性/唯一性、project/doc 与 dump.capture 一致性、完整 pose、constraint_set.status、locked/group、client version/write-support、live-vs-dump freshness、异常输入处理，以及统一的 blocking/advisory 报告。

evidence: C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/design_engine/pcb_workflow.py:165-251,341-585,611-899,1420-1497,1660-1786,1937-2027; C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/eda_exec.py:2975-3074,4079-4209; C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/pcb_apply_plan.py:83-92

### 升级版 pcb_apply_plan.py 可复用：validate_placement + apply_placements/transform_component 做 dry-run intent，diff_boards/expected_placement_diff 做最终验证，_load/_dump/_run 的 subprocess 模式，以及 eda_exec 的阶段顺序（before integrity→write→after integrity→verify→verified 后 save→reopen）。缺口：单器件 pcb modify、无 batch/事务、无 journal/resume/checkpoint、无 timeout/retry、save/reload/dump 不 gate、reload 后不刷新 primitiveId、没有逐 op expected readback/pose 比较（只信 CLI verified）、无幂等、无 group/concurrency、无 client-version gate，且 op 类型只有 component pose。

evidence: C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/pcb_apply_plan.py:28-36,93-147; C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/design_engine/pcb_workflow.py:254-322,1789-1920; C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/eda_exec.py:4079-4209

### pcb_gate.py 可复用：对显式 expected final pose set 调 validate_placement、diff_boards、audit_fabrication、audit_power，eda_exec 的 compare_pcb_snapshots/verify_pcb_items/pcb_snapshot_integrity，以及 gate_check.py 的 evidence-role discovery、parse_board/parse_pcb_drc/parse_pcb_check/parse_reopen、PASS/BLOCKED/UNSUPPORTED/PASS_WITH_WAIVER 状态和 waivers。缺口：没有 PCB gate schema/policy；expected_placement_diff 只适合纯 placement（拒绝 copper/layer 变化，且整板 scope 很弱）；preferred finding 会阻塞 hard_ok；diff 不看 silk/poured/pad 几何/net metrics；DRC 只有 raw；没有 required-evidence matrix 和 net-path/connectivity gate。

evidence: C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/gate_check.py:14-45,115-148,650-743,744-810,918-931,1108-1122; C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/design_engine/pcb_workflow.py:880-899,1789-1920; C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/eda_exec.py:3346-3432; C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/pcb_apply_plan.py:54-59

### pcb_case.py 可复用：design_engine/state.py 的 evidence SHA256 add/verify 和 state schema，gate_check.py 的 evidence discovery/parsers/waivers，以及全部 pcb_workflow audits/diffs；现有案例目录已经形成事实布局（README.md、design-state.json、evidence/*.json、.epro2、PNG/SVG）。缺口：没有 case manifest/schema、scaffolding/completeness matrix、README 与 JSON 数值交叉核对、capture.json pinning、provenance/version pinning，也没有四个工具共享的 PASS/BLOCKED/NOT RUN 词汇。另有一个具体互操作问题：state.py 写 design-engine-state/v1，而 gate_check.py 只接受 design-state/v1，两个新 PCB 案例正好使用前者。

evidence: C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/design_engine/state.py:13-14,50-72,88-97; C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/gate_check.py:26-34,336-400,1997-2003; C:/Users/jlc/work/hds-pcb-round9/design-hardware/cases/mcu-i2c-s3-2026-10-26/design-state.json:1-3; C:/Users/jlc/work/hds-pcb-round9/design-hardware/cases/temp-alarm-2026-10-24/design-state.json:1-3

### 批处理约束—primitiveId 生命周期：pcb modify --id 必须使用 fresh dump 的 primitiveId，plan.primitive_ids 只是可选的 staleness 断言；copper primitiveId 明确不能跨 doc reload 保持，diff 用 semantic twin 兜底；外部 CLI 在 PCB mutation 后未 doc reload 就读/DRC 会附 staleRisk advisory。save/reload 后必须重新 dump 并重新解析每个 id，不能跨 reload 复用 id。

evidence: C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/design_engine/pcb_workflow.py:640-652,1856-1857,1919; C:/Users/jlc/work/_round6-scratch/easyeda-agent-src/extension/CHANGELOG.md:2364-2366

### 批处理约束—anchor vs bbox center：dump 的 x/y 是 footprint anchor（参考文档明确说明），transform/validate/template/plan 都输出 anchor pose，而 containment/overlap/ordered_chain 用 bbox，near_pin 用 pad 中心。外部 pcb modify 的 x/y 是 anchor；--center --x/--y 表示期望的 bbox 中心，用实时 bbox 换算，且拒绝在同一次 patch 里改 rotation（必须先旋转，再第二次 --center）。playbook 必须声明唯一的 pose frame，不能混用。

evidence: C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/design_engine/pcb_workflow.py:262-275,658-696,759-771; C:/Users/jlc/work/hds-pcb-round9/design-hardware/references/pcb-execution.md:29; C:/Users/jlc/work/_round6-scratch/easyeda-agent-src/internal/app/cmd_pcb.go:1003-1023,1041-1058

### 批处理约束—layer 语义：component layer 1=top、2=bottom；SMD pad 随 component 面变化，THT pad 保持 12 MULTI；flip 关于 anchor 的 x 轴镜像局部几何；同层才检查 bbox overlap；component 写入只接受 1/2，copper 接受 1..64，板框是 layer 11。diff_boards 把 layer 放进 component identity，所以 layer flip 虽然是合法写入，却无法通过 expected_placement_diff。

evidence: C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/design_engine/pcb_workflow.py:267-295,688-696,1825-1826; C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/eda_exec.py:3025-3032,3125-3132; C:/Users/jlc/work/_round6-scratch/easyeda-agent-src/internal/app/cmd_pcb.go:1020-1021

### 批处理约束—save/reload 证据：当前适配器只记录不 gate save/reload/dump；外部 dump 命令把 JSON 写文件、把成功行打到 stderr，stdout 解析无法确认。相反 eda_exec 的 PCB_SAVE_JS 返回 saved/saved_value/counts，command_pcb_save 只有 saved==true 才成功，command_pcb_apply 只有 verify 通过才 save 且 save 失败即失败。批处理 gate 必须检查 saved==true、reload 成功、fresh dump 可解析、capture identity/semantic hash 一致，再做 diff。

evidence: C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/pcb_apply_plan.py:124-137; C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/eda_exec.py:1144-1160,4189-4202,4212-4227; C:/Users/jlc/work/_round6-scratch/easyeda-agent-src/internal/app/cmd_pcb_dump.go:72-92

### 批处理约束—外部 CLI 已有声明式 playbook executor：easyeda apply <playbook.json>，version 1，meta.name/project/doc，step 必须是 action|run|notify 之一，step id 唯一，支持 capture/assert、journal/resume/from/to、dry-run、fail-fast、mutation timeout 不重试、可选 verify block，以及 requireFullExecution（禁止 resume/range/目标覆盖）。这是升级版批处理 playbook 最自然的执行器，当前 pcb_apply_plan.py 没有使用它。

evidence: C:/Users/jlc/work/_round6-scratch/easyeda-agent-src/internal/app/cmd_apply.go:3-13,37-95,127-230,291-400,821-870

### 批处理约束—group/并发/引号：pcb modify 拒绝移动/旋转/flip 多器件 virtual pcb group 的单个成员（除非 --break-group，刚性平移用 pcb group move）；pcb move 是批量相对 dx/dy op，也拒绝只动组的一部分；同一块板两个 session 写入时 CLI 附 concurrentWriter 警告；--patch-file 用于 PowerShell 安全的 JSON。当前适配器用内联 --patch，且没有 group/concurrency 检查。

evidence: C:/Users/jlc/work/_round6-scratch/easyeda-agent-src/internal/app/cmd_pcb.go:1015-1018,1021,1060-1063,1070-1075,1304-1332; C:/Users/jlc/work/_round6-scratch/easyeda-agent-src/extension/CHANGELOG.md:2362-2364

### 批处理约束—容差/几何：outline containment 容差 5 mil；normalized outline 由 points 推导，fixture 中比原始 rendered bbox 小约 5 mil；bbox 含 rendered attributes/silk，偏保守；pad-outside 只查 pad 中心；near_pin 只是 pad 中心距、没有铜路径证明；fixed 约束用 1e-6，而 eda_exec readback 验证用 0.01。写后 gate 应使用明确的 0.01 mil 容差，不能假设 normalized 与 raw dump 的 bbox/outline 完全一致。

evidence: C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/design_engine/pcb_workflow.py:204-214,668,672-682,712-715,759-771; C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/eda_exec.py:3306-3310; C:/Users/jlc/work/hds-pcb-round9/tests/test_pcb_workflow.py:51-56

### 输入健壮性缺口：validate_placement/apply_placements 在 x/y/layer 缺失、designator 未知或重复时会抛 TypeError/ValueError，而 pcb_apply_plan 只检查 placements 不是 list 的情况；畸形 plan/dump 会以 traceback 退出而不是结构化 invalid_input。normalize_board 对非 dict dump 也直接抛 ValueError。

evidence: C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/pcb_apply_plan.py:75-82,93-97; C:/Users/jlc/work/hds-pcb-round9/design-hardware/scripts/design_engine/pcb_workflow.py:171-172,299-322,709-710,823-824
