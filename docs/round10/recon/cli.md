# cli

## summary

easyeda apply 的 playbook v1 是一个严格校验、顺序执行的 JSON 队列：每步只能是 action+payload、run+flags/args 或 notify 三者之一；执行器 fail-fast、写 journal、支持 --resume，但没有事务/回滚、条件分支、循环或算术。对 PCB 批量写入，核心写操作同时存在 typed action（pcb.component.modify / pcb.line.create / pcb.via.create / pcb.pour.create / pcb.save / pcb.pour.rebuild / pcb.drc.check / pcb.route.auto）和 CLI 薄封装（pcb modify/track/via/pour/save/pour-rebuild/drc/autoroute），所以 action 步骤与 CLI 子命令能表达同一批写入，主要差别在字段命名和 CLI 包装逻辑。必须记住的契约点：(1) pcb add-component 与 pcb.component.modify patch 的 x/y 都是 footprint anchor（封装原点），不是 bbox 中心；唯一的 bbox-center 写入是 CLI `pcb modify --center --x --y`，且不能与 rotation 变更同一步，必须先旋转再居中；(2) checkpoint:true 只是日志标记，绝不保存，必须显式 pcb.save；(3) ${VAR} 替换是纯字符串替换，不能生成 JSON number/bool/array/object，因此 action payload 的数值/数组字段不能用变量，run 步骤的 JSON 字符串 flag 才能安全模板化几何；(4) 变更步骤默认 retry=0、只读默认 retry=2（DRC 请显式 retry:0），action 默认超时仅 20s；(5) result.partial=true 或非空 notApplied 会让 apply 判定该步失败，pour 边界未验证是硬停；(6) pcb.drc.check 在 passed:false 时仍返回 ok:true，必须用 assert 卡住，connector 侧 strict 默认竟是 true；(7) PCB mutation 后枚举/DRC 可能读到旧引擎状态，最终证据必须 save → doc reload → fresh readback/DRC。版本漂移是实质性的：design-apply-playbook.md、pcb.playbook.json 与 _actions-catalog.json 来自 v1.14.0 源码树，而本机 CLI/skill 是 1.15.0；live `easyeda actions` 已多出 pcb.add_component，且 `easyeda apply examples/esp32-mini/pcb.playbook.json --dry-run` 在 1.15.0 上 186 步全部 preflight 通过，证明 onFail/run/notify/checkpoint 仍被接受。本次未执行任何写入、未接触真实 EDA 窗口；dry-run 不校验 run 步骤的 flag 名，也不执行命令，因此 run 步骤参数仍需现场冒烟验证。

## gaps

- 本次严格只读：没有执行任何 PCB 写入、没有 doc reload、没有实际运行 DRC，也没有接触用户真实 EDA 窗口；所有“执行语义”结论来自 v1.14.0 源码、live --help 与 dry-run，不是真机写后回读验收。
- 源码 checkout 是 v1.14.0，本机二进制是 1.15.0；1.15.0 的 apply 内部实现无法核对，只能靠 --dry-run 和 --help 推断。onFail、verify、retry/timeout 在 1.15.0 的实际执行行为尚未验证（dry-run 只证明解析接受）。
- 没有 dry-run 一个包含 pcb.add_component action 的 playbook，因为任务禁止创建/修改文件；只确认了 live catalog 中存在该 action 与 needsConfirm:true，未确认 apply preflight 在该二进制里对它的接受路径。
- doc reload --json 的成功 status="passed"、saved/closed 字段来自 v1.14.0 源码，未在 1.15.0 上实际重载验证。
- DRC strict 默认值存在文档/实现矛盾（CLI help 像是 opt-in，connector 代码默认 true），未用 1.15.0 connector 现场跑 DRC 核对；也未确认当前打开窗口的 connector 版本是否与 CLI 1.15.0 匹配。
- dry-run 不执行 run 子命令，也不校验 run flags 的名称与类型；所有 run 写法的 flag 名只由 1.15.0 --help 证明存在，未证明 apply 拼装后能成功执行（尤其布尔 flag 的传值、数组 flag 的重复形式）。
- 未验证 1.15.0 是否把 timeoutSec 应用到 run 步骤；该结论来自 v1.14.0 源码。
- 未检查 1.15.0 是否新增了 playbook 步骤字段；若有，v1.14.0 文档不会列出，且严格解析会拒绝未知字段，需以现场 dry-run 为准。
- 未验证真实坐标约定在 1.15.0 connector 中是否仍为 anchor；结论来自 1.14 connector create/modify 实现与 pcb-layout 文档。
- 没有评估具体板子的 DRC 规则数值、层 id、板框与铺铜可行性；本报告只给契约，不给具体工程参数。

## recommendations

- PCB 批量写入优先用 action 步骤：pcb.component.modify（移动/旋转/翻转）、pcb.line.create、pcb.via.create、pcb.pour.create、pcb.save、pcb.pour.rebuild、pcb.drc.check。它们返回结构化 result，便于 capture/assert，且避免 Windows/PowerShell 的 JSON 引号问题。
- 必须用 run 步骤的三类：新建器件 `pcb add-component`（或确认 1.15 后用 action pcb.add_component）、按板框铺铜 `pcb pour-fit`、真实重载 `doc reload`；bbox-center 放置用 `pcb modify --center`（先单独旋转，再居中）。
- 所有坐标先离线算成 footprint anchor 再写进 action payload；如果上游给的是 bbox center，要么离线换算，要么用 run `pcb modify --center` 分两步写。绝不要把 layout-plan 的 xMil/yMil 当成 bbox center，也不要把 bbox center 塞进 pcb.component.modify 的 patch。
- 写操作统一 retry:0；action 的 timeoutSec 按操作设（普通 60-120s，pour 120s，autoroute 600s+）；DRC 必须 retry:0 并确保 PCB 在前台 tab。不要对变更步骤开 retry，超时可能已落地。
- 每个稳定点显式 `pcb.save` 并 assert $.saved:"true"；不要依赖 checkpoint。最终验收链固定为 pcb.save → doc reload →（必要时 pour-rebuild → pcb.save）→ fresh readback（pcb list/track-list/via-list/pour-list/poured-list）→ DRC；mutation 后立即读可能 stale。
- 新建 PCB 的铺铜顺序固定为 rules 写入 → pour → pcb.save → doc reload → pcb.pour.rebuild（第二次）→ pcb.save，否则 reflow 仍用创建时 rules snapshot。
- 带 ${} 模板化几何时用 run 步骤 + JSON 字符串 flag（如 points、patch、nets），不要用 action payload；action payload 只放字面量数字/数组/对象。布尔 flag 也必须是字面 JSON bool，不能来自变量字符串。
- 无人值守执行时用 `easyeda apply <file> --doc <pcb-uuid> --yes`（--yes 仅在确认已授权 confirm 类步骤时使用）；meta.doc 只做一次初始 doc switch，不能防止中途切 tab，--doc 才会逐步钉住。
- 先 `easyeda apply <file> --dry-run` 验证 schema/action/vars，再做一次最小单步冒烟（例如 pcb.save 或一次 track）验证 run flag 拼装；dry-run 不校验 run flags，也不执行命令。
- 以 live `easyeda actions` 为 action schema 真源；不要直接引用 C:/Users/jlc/work/hds-pcb-round9/_actions-catalog.json，它缺少 1.15.0 的 pcb.add_component。
- 对 pcb.component.modify 的结果同时 assert verified:true 和关键几何（如 $.component.x）；对 pcb.pour.create 同时 assert verified:true 与 poured:true；对 autoroute assert router.success:true 与 lockedLost:len==0。
- 若需要 gate DRC 但又不希望非零退出中断，用 action pcb.drc.check + assert；若只是记录，run `pcb drc --json` + onFail:continue，但后者无法再 assert/capture。

## facts

### Playbook v1 顶层形状为 {"version":1,"requireFullExecution":bool?,"meta":{"name","description"?,"project"?,"window"?,"doc"?},"defaults":{"timeoutSec"?,"retry"?,"continueOnError"?},"vars":{K:V},"steps":[...]}。解析使用 encoding/json DisallowUnknownFields，未知字段是硬错误；version 必须为 1，meta.name 必填，steps 不能为空，requireFullExecution 要求 meta.doc。

evidence: C:/Users/jlc/work/_round6-scratch/easyeda-agent-src/internal/app/cmd_apply.go L37-95、L239-245、L304-347；C:/Users/jlc/work/_round6-scratch/easyeda-agent-src/docs/design-apply-playbook.md L30-67。

### 每步必须且只能有 action / run / notify 之一，preflight 对 0 个或多于 1 个直接报错。action+payload 调用内嵌 catalog 中的 typed daemon action；run 是 CLI 子命令行（不是 shell），可带 flags 对象和位置 args；notify 是 system.notify {message,type:"info"} 的语法糖。

evidence: cmd_apply.go stepKind L291-302、preflight L349-367、executeOnce L1114-1145、runSubcommand L1253-1281。

### run 字符串按空格拆成 argv，args 先追加，flags 键即不带 -- 的 flag 名：JSON bool → --k=true/false，数组 → 每项一个 --k item，其它 → --k value；执行器还会自动追加 --project、--host、--ports，并在命令支持时追加 --window，在设置了 cfg.doc 时追加 --doc。

evidence: cmd_apply.go runSubcommand L1253-1281。

### ${NAME} 会替换 payload（literalPayloadKeys 列出的顶层键除外）、flags、args、notify、expectSchematic、verify 的 payload/flags/args；preflight 要求每个 NAME 已由 vars 提供或被更早步骤 capture。替换是 string→string，不能产生 JSON number/bool/array/object；action payload 的数值字段经 connector requireNumber 会因字符串被拒，pcb.pour.create.points 也必须是真正的 [[x,y],...] 数字数组。run 步骤不受此限，因为 Cobra/JSON 会重新解析字符串。

evidence: cmd_apply.go L399-443、L482-513、L1149-1167；C:/Users/jlc/work/_round6-scratch/easyeda-agent-src/extension/src/util.ts L176-185；extension/src/actions.ts L13659-13667。

### capture 是 {变量名: 结果内 JSON 路径}，路径相对 response 的 result，只支持 .key 与 [index]，不支持筛选表达式；值统一存成字符串（对象/数组则 JSON 序列化）。assert 先于 capture 执行，assert 失败就不会 capture。--resume 从 journal 中 status 以 ok 开头的条目恢复 captured 变量。

evidence: cmd_apply.go L515-566、L1387-1408、L853-856。

### assert 是 {JSON 路径: 判定式}，支持 exists、true、false、数值 >、>=、<、<=、==、!=、字符串 ==/!=、以及 len==/len>=/len<=/len>/len<（数组/map/string，null 视为 len 0）。没有正则、contains、也没有两个路径互相比较；例如 {"$.passed":"true","$.violations":"len==0"} 合法，"$.rebuilt == $.pours" 不合法。

evidence: cmd_apply.go L568-651。

### checkpoint:true 只写 journal 和 stdout 标记，不做任何保存，真实落盘必须另有 pcb.save 步骤。verify:{action|run,payload|flags/args,assert} 只在原步骤失败（含 assert 失败）后执行；若只读回读+断言通过，该步按成功处理（文档称 ok(verified)，v1.14 代码实际记 ok），verify 结果不能被 capture；expectSchematic、pour 边界未验证、PCB import 未验证、silk/library 未验证等硬错误不能被 verify 救回。

evidence: design-apply-playbook.md L76-77；cmd_apply.go L921-931、L1089-1096、L1411-1458、L1058-1065。

### confirm 未显式给出时：action 步骤取 catalog 的 needsConfirm，run 步骤按子串嗅探 delete/clear/rip-up/import-changes/import-autoroute。--yes 自动放行；非交互会话没有 --yes 会直接报错；用户回答 no 则停止整个 playbook。注意 action needsConfirm 与 run 嗅探并不等价：pcb.add_component 和 pcb.route.auto action 是 needsConfirm:true，但 `pcb add-component`/`pcb autoroute` 这两个 run 字符串不会被自动门控。

evidence: cmd_apply.go L269-289、L773-784、L907-915、L1461-1471；2026-10-26 live `easyeda actions` 输出。

### continueOnError 是 defaults/步骤级策略；步骤级 onFail 取值 stop|continue|prompt，显式设置时优先于 continueOnError；未设 onFail 时 continueOnError=true 映射为 continue，否则 stop。continue 会把该步记 fail 后继续；prompt 交互询问。硬错误类始终 stop。

evidence: cmd_apply.go L45-58、L797-819、L953-1011。

### action 默认超时 defaultActionTimeout=20s；retry 内置默认 2 次（只读），变更步骤默认 0 次；显式 step/default retry 对变更步骤也生效（超时重放可能重复写入，PCB 写务必 retry:0）。timeoutSec 传给 action dispatch；v1.14 的 runSubcommand 没有 timeout 参数，run 步骤由子命令自身 --timeout 控制。

evidence: C:/Users/jlc/work/_round6-scratch/easyeda-agent-src/internal/app/dispatch.go L35；cmd_apply.go L797-819、L1028-1036、L1253。

### journal 默认 <playbook>.journal.jsonl，头部 {playbookSha256,name,project,startedAt}，逐步 {idx,id,status,ms,captured,error}。--resume 拒绝文件哈希变化、跳过已 ok 步骤并恢复 captured。requireFullExecution:true（且要求 meta.doc）或任一步含 expectedConnectivity 会变成 guarded 计划：禁止 --resume/--from/--to，也禁止改目标工程/文档。PCB playbook 默认非 guarded，可选择加 requireFullExecution 作保护。

evidence: cmd_apply.go L99-114、L144-161、L190-214、L821-859；design-apply-playbook.md L22-28、L141-149。

### apply 不提供事务和回滚，已落地步骤不会撤销；变更步骤超时只说明“可能已生效”，恢复方式是读回真实状态后修正或重新规划（guarded 计划必须完整重生成）。action 返回 ok:true 但 result.partial=true 或 notApplied 非空时，apply 判该步失败；pcb.pour.create / pcb.fill.create 的 verified:false、partial:true 或空 primitiveId 会抛 unverifiedPourBoundaryError，onFail/continueOnError/verify/retry 都不能绕过。

evidence: cmd_apply.go L1204-1240；dispatch.go L225-247；design-apply-playbook.md L141-149。

### 推荐骨架：{"version":1,"meta":{"name":"pcb-batch-writes","project":"<project>","doc":"<pcb-doc-uuid>"},"defaults":{"timeoutSec":60,"retry":0},"vars":{"UID_U1":"gge1"},"steps":[...]}。meta.doc 会在执行前用 `doc switch` 切到目标；无人值守时再加 `easyeda apply <file> --doc <pcb-uuid>`，让每个 mutating action 都经 document.current 实时钉住，避免用户中途切 tab 写错板。

evidence: cmd_apply.go L884-892；dispatch.go L953-1014；design-apply-playbook.md L27-28。

### 新建器件 run 写法：{"id":"place-u1","run":"pcb add-component","timeoutSec":60,"flags":{"library":"<libraryUuid>","uuid":"<deviceUuid>","x":700,"y":849.5,"layer":1,"designator":"U1","unique-id":"${UID_U1}","nets":"{\"2\":\"+3V3\",\"41\":\"GND\"}","rotation":0},"capture":{"U1_PID":"$.primitiveId"}}。flag 名是 --library/--uuid/--x/--y/--layer/--rotation/--designator/--unique-id/--nets，nets 是 JSON 字符串；CLI 调 pcb.add_component，dispatch 输出完整 JSON envelope，apply 会解包并 capture $.primitiveId。x/y 是 footprint anchor。

evidence: cmd_pcb.go L957-992；actions.ts L11801-11812；C:/Users/jlc/work/_round6-scratch/easyeda-agent-src/examples/esp32-mini/pcb.playbook.json L36-48。

### 新建器件 action 写法（1.15.0）：{"id":"place-u1","action":"pcb.add_component","timeoutSec":60,"payload":{"libraryUuid":"<libraryUuid>","uuid":"<deviceUuid>","x":700,"y":849.5,"layer":1,"designator":"U1","uniqueId":"${UID_U1}","nets":{"2":"+3V3","41":"GND"},"rotation":0},"capture":{"U1_PID":"$.primitiveId"}}。该 action 在 live `easyeda actions`（1.15.0）中存在且 needsConfirm:true（需 --yes 或显式 confirm），但不在 repo 的 _actions-catalog.json 中；payload.nets 必须是真对象，若用 ${NETS} 字符串，connector 的 typeof payload.nets === 'object' 判断会静默得到空 map，等于不连网。

evidence: 2026-10-26 live `easyeda actions`；actions.ts L11786-11800。

### pcb.add_component 的 x/y 原样传给 pcb_PrimitiveComponent.create，是封装原点/anchor；pcb.component.modify 的 patch x/y 也是 anchor（help 明说 usually NOT the bbox center，offset 随旋转变化）；layout-plan 生成的 candidate apply 文件 meta 明确写 footprint-anchor coordinates，place-X 步骤直接 pcb.component.modify patch {x,y,rotation}。只有 `pcb modify --center --x --y` 是 bbox-center 语义：读 live bbox、换算成 anchor 再 dispatch；要求 --x 和 --y 同时给出，patch 中不能含 x、y 或 rotation，旋转必须在前一步单独完成。`pcb list --include-bbox` 会在 CLI 侧给每个 component 加 center:{x,y}，而 pcb.components.list action 只给 bbox min/max。

evidence: cmd_pcb.go L1005-1058、L637-645；C:/Users/jlc/.claude/skills/easyeda-agent/references/pcb-layout.md L16；C:/Users/jlc/.claude/skills/easyeda-agent/references/examples/260919-at32f415/layout-candidates-can-current-board/candidate-02.apply.json 与 candidate-02.json。

### 组件移动/旋转 action：{"id":"move-d1","action":"pcb.component.modify","timeoutSec":60,"payload":{"primitiveId":"${D1_PID}","patch":{"x":2741.5,"y":1528.151,"rotation":270,"layer":1}},"assert":{"$.verified":"true","$.component.x":"==2741.5"}}。patch 合法键：layer、x、y、rotation、primitiveLock（别名 locked/lock）、addIntoBom、designator、name、uniqueId、manufacturerId、supplierId、manufacturer、supplier、otherProperty；未知键会被 connector 直接拒绝。action 已做 fresh readback 并返回 verified/applied/notApplied，可在同一步 assert。

evidence: _actions-catalog.json L2878-2899；actions.ts L12330-12351、L12473-12546。

### 组件居中 run 写法：{"id":"center-d1","run":"pcb modify","flags":{"id":"${D1_PID}","center":true,"x":1500,"y":2200}}。必须先有一个单独的 rotation 步骤，因为 --center 与 patch 中的 rotation 互斥；--center 也不能与 patch 的 x/y 同用。若需要旋转+居中，写成两步：先 action/run 改 rotation，再 run modify --center。

evidence: cmd_pcb.go L1041-1058；pcb-layout.md L16。

### 走线 action：{"id":"track-1","action":"pcb.line.create","payload":{"startX":220,"startY":926.5,"endX":180,"endY":926.5,"layer":1,"lineWidth":10,"net":"+3V3"},"capture":{"T1_PID":"$.primitiveId"}}。run 等价：{"id":"track-1","run":"pcb track","flags":{"x1":220,"y1":926.5,"x2":180,"y2":926.5,"layer":1,"width":10,"net":"+3V3"}}。字段映射 startX/startY/endX/endY/lineWidth ↔ x1/y1/x2/y2/width；layer 默认 1，lineWidth 默认 6，坐标 mil、y-up。

evidence: _actions-catalog.json L3224-3250；cmd_pcb.go L1670-1691；actions.ts L13560-13567。

### 过孔 action：{"id":"via-1","action":"pcb.via.create","payload":{"x":180,"y":690,"net":"+3V3","holeDiameter":12,"diameter":24}}。run 等价：{"id":"via-1","run":"pcb via","flags":{"x":180,"y":690,"net":"+3V3","hole":12,"diameter":24}}。action 默认 holeDiameter=12、diameter=24；CLI 的 --hole 映射到 holeDiameter。

evidence: _actions-catalog.json L3253-3277；cmd_pcb.go L1707-1733；actions.ts L13591-13601。

### 铺铜 action：{"id":"pour-gnd-l1","action":"pcb.pour.create","timeoutSec":120,"payload":{"points":[[0,0],[2600,0],[2600,1500],[0,1500]],"net":"GND","layer":1,"fill":"solid","name":"GND_L1","lineWidth":0.2},"assert":{"$.verified":"true","$.poured":"true"}}。net 必填且非空；points 必须是 >=3 组 [x,y] 数字；fill=solid|grid|grid45；边界线宽只允许省略或 0.2 mil；action 在边界回读通过后会自动 rebuild，verified 描述边界、poured 描述材料化，二者分开断言。run 等价把 points 写成 JSON 字符串：{"run":"pcb pour","flags":{"points":"[[0,0],[2600,0],[2600,1500],[0,1500]]","net":"GND","layer":1,"fill":"solid","name":"GND_L1","width":0.2}}。

evidence: _actions-catalog.json L3680-3723；cmd_pcb.go L2069-2088；actions.ts L13656-13759。

### 按板框自动铺铜是 run-only：{"id":"pour-gnd-l1","run":"pcb pour-fit","flags":{"net":"GND","layer":1,"inset":15,"replace":false}}。没有对应 typed action；它读取板框 bbox 并按 inset 生成矩形铺铜，默认 replace=true 会先清同网同层旧铺铜；v1 对异形板框仍只铺矩形。

evidence: 2026-10-26 live `easyeda pcb pour-fit --help`；_actions-catalog.json 中无 pcb.pour.fit。

### 保存步骤：{"id":"save-copper","action":"pcb.save","assert":{"$.saved":"true"},"checkpoint":true}。checkpoint 只是日志标记；保存动作本身是 action（等价 run: "pcb save"）。每个稳定检查点都要显式保存并断言 saved:true。

evidence: _actions-catalog.json L3280-3290；cmd_apply.go L921-931；pcb.md L235-240。

### 重载步骤：{"id":"reload-pcb","run":"doc reload","flags":{"json":true},"args":["<pcb-doc-uuid>"],"assert":{"$.status":"==passed","$.saved":"true","$.closed":"true"},"timeoutSec":120}。doc reload 是先保存、再关 tab、再重开；它会刷新每个 PCB 文档的枚举缓存，并且对“本次会话新建、从未 reload 过”的 PCB 刷新创建时 rules snapshot（否则规则写入和 pour-rebuild 对 reflow 无效）。--json 输出 receipt，v1.14 源码成功 status="passed"，含 saved/closed/reloaded/activeRestored。没有 doc reload 的 typed action；system.page_reload action 是更重的整页 Web 重载（需 projectUuid+documentUuid 并验证 connector 重注册），不是同一操作。

evidence: 2026-10-26 live `easyeda doc reload --help`；C:/Users/jlc/work/_round6-scratch/easyeda-agent-src/internal/app/doc_reload_receipt.go L21-40、L80-99；pcb.md L245、L286-305。

### 重灌铺铜：{"id":"pour-rebuild","action":"pcb.pour.rebuild","payload":{},"timeoutSec":120} 或 {"run":"pcb pour-rebuild","flags":{"net":"GND"}}。返回 {pours,rebuilt}，rebuilt 是成功重灌数量，单个 pour 失败被吞掉（best-effort），因此 rebuilt<pours 不报错；要证明实际铜面应再查 pcb.poured.list 并跑 DRC。对新建 PCB 的顺序必须是 rules → pour → pcb.save → doc reload → pcb.pour.rebuild（第二次）→ pcb.save。

evidence: _actions-catalog.json L3790-3804；actions.ts L14083-14098；examples/esp32-mini/pcb.playbook.json L2122-2152；pcb.md L245。

### DRC action 卡口：{"id":"drc-final","action":"pcb.drc.check","payload":{"strict":true},"retry":0,"timeoutSec":120,"assert":{"$.passed":"true"}}。connector 的 pcb.drc.check 在 violations 为空时 passed=true，否则仍返回 ok:true 并带 passed:false/violations（可附 binding 诊断），所以 assert 才是 gate；strict 在 connector 侧的默认值是 true（optionalBoolean !== false），显式传 false 才放宽。action 默认 20s 且只读默认 retry=2，DRC 必须 retry:0、timeoutSec 加够，并要求 PCB 在前台 tab（后台窗口会超时，重试会加重 webview 负担）。

evidence: _actions-catalog.json L3093-3106；actions.ts L13255-13293；dispatch.go L35；2026-10-26 live `easyeda pcb drc --help`。

### DRC run 写法及限制：{"id":"drc-final","run":"pcb drc","flags":{"json":true,"timeout":120},"retry":0,"onFail":"continue"}。`pcb drc` 在 passed:false 或结论不可用时直接非零退出，apply 会在 assert 之前就判该步失败，所以想“记录 DRC 结果但不中断”只能 onFail:continue，且无法再 assert/capture；想用 assert 卡口请用 action。--json 会给出 passed/total/counts/violations（坐标转为真实 mil）并保留 nativeResult。

evidence: cmd_pcb.go L475-543；C:/Users/jlc/work/_round6-scratch/easyeda-agent-src/internal/app/pcb_drc_flat.go L65-71；2026-10-26 live `easyeda pcb drc --help`。

### 自动布线 action：{"id":"autoroute","action":"pcb.route.auto","timeoutSec":600,"confirm":true,"payload":{"nets":["SIG1"],"ignoreNets":["GND"],"layers":[1,2],"cornerStyle":"45","optimization":"completion"},"assert":{"$.router.success":"true","$.lockedLost":"len==0"}}。official router 会保留现有 track/via；action needsConfirm:true；返回 router{success,totalNetsCount,successNetsCount,failedNets,duration}、created、lockedBefore/lockedLost。run 等价：{"run":"pcb autoroute","flags":{"layers":[1,2],"ignore-net":"GND","corner":"45","optimize":"completion","timeout":"10m"}}；外部 router 只有 run 的 --router 支持。

evidence: _actions-catalog.json L3634-3661；2026-10-26 live `easyeda pcb autoroute --help`。

### pcb track/via/pour/save/pour-rebuild 都是对相应 action 的薄封装：`pcb track` dispatch pcb.line.create，`pcb via` dispatch pcb.via.create，`pcb pour` dispatch pcb.pour.create，`pcb pour-rebuild` dispatch pcb.pour.rebuild。因此 action payload 能表达同样的写入，差别主要是字段名（x1/width vs startX/lineWidth、hole vs holeDiameter、points 字符串 vs 数字数组）和 CLI 侧附加逻辑。

evidence: cmd_pcb.go L1670-1691、L1707-1726、L2069-2084、L2184-2189。

### action payload 的主要限制：1) 无 --center，bbox-center 只能 run `pcb modify --center`；2) 无 --patch-file，但 action payload 本身就是 JSON 对象，反而绕开 PowerShell 引号问题；3) 无 --break-group，pcb.component.modify action 直连 daemon，不经过 CLI 的虚拟 group 完整性守卫，可能移动组成员而��报错；4) 无 --replace，pour-fit 的替换逻辑只在 CLI；5) add-component 的 nets 对象与 pour 的 points 数组不能用 ${} 模板化；6) 数值字段不能来自 vars；7) 没有 pcb.components.get，verify 只能按数组下标读，脆弱。

evidence: cmd_pcb.go L1005-1077、L1041-1058、L11801+；cmd_apply.go L482-513；pcb-layout.md L222。

### run 步骤只做 trailing JSON 解析（parseTrailingJSON 会把 {ok,result,...} 解包为 result），文本输出无法 assert/capture；`doc reload` 必须加 --json。v1.14 的 runSubcommand 没有 timeout 参数，所以 timeoutSec 不约束 run 步骤，需用子命令自己的 --timeout。显式 retry 对 run 步骤同样生效，变更类命令不要设 retry。

evidence: cmd_apply.go L1253-1321、L1344-1385、L1028-1036。

### 版本漂移：源码树 HEAD 7cde1ae1769d3e8c50fd9ada43f9bcc166d69d70 是 v1.14.0（2026-10-17），本机 `easyeda --version` 与 skill `.version` 是 1.15.0。design-apply-playbook.md 是 SCH 中心文档，示例只写 `easyeda sch apply`，且未记录 onFail（但代码与 esp32 pcb playbook 都在用）；文档说 verify 成功记 ok(verified)，v1.14 代码实际写 "ok"。1.15.0 的实际字段集未从二进制核对，严格 DisallowUnknownFields 意味着新增字段只能靠 dry-run 现场确认。

evidence: C:/Users/jlc/work/_round6-scratch/easyeda-agent-src 的 git log；C:/Users/jlc/.claude/skills/easyeda-agent/.version；cmd_apply.go L79、L109；design-apply-playbook.md 全文。

### live 1.15 验证：2026-10-26 执行 `easyeda apply C:/Users/jlc/work/_round6-scratch/easyeda-agent-src/examples/esp32-mini/pcb.playbook.json --dry-run`，186 步 preflight 通过、EXIT=0，证明 1.15.0 仍接受 onFail、run、notify、checkpoint、action pcb.save、vars、assert 以及该示例的全部字段；同一命令 dry-run candidate-02.apply.json 也通过，证明 pcb.component.modify + pcb.save action 步骤可用。dry-run 不会执行 run 命令、也不会校验 run 的 flag 名。

evidence: 上述两条命令的实际输出：esp32 示例最后一行 "dry-run: preflight passed, nothing executed"、EXIT=0；candidate-02 同样 EXIT=0。

### catalog 已过时：repo 的 C:/Users/jlc/work/hds-pcb-round9/_actions-catalog.json 不含 pcb.add_component，但 live `easyeda actions`（1.15.0）包含它，且其 needsConfirm:true；说明该 catalog 文件是旧版/裁剪产物。应以 `easyeda actions` 的实时输出为准，而不是仓库内 JSON。

evidence: grep _actions-catalog.json 无 pcb.add_component；2026-10-26 live easyeda actions 列出 pcb.add_component 及其完整 schema。

### 其他现场注意：pcb.drc.check 的 strict 默认在 connector 代码里是 true，而 CLI help 把 --strict 描述成 opt-in，二者矛盾，需现场确认 1.15 connector 实际行为；pcb.pour.rebuild 对单个 pour 失败静默；pcb save 后立刻读仍可能 staleRisk，最终验收必须 save → doc reload → fresh readback（pcb list/track-list/via-list/pour-list/poured-list/drc）。

evidence: actions.ts L13256；pcb.md L286-305；cmd_pcb.go L4908。
