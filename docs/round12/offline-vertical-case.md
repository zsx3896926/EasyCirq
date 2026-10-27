# Round 12 离线纵向案例（photo-led 冻结夹具）

> **证据性质**：本文全部宿主行为来自 `tests/fixtures/feedback/fake_easyeda.py` 与
> `tests/feedback_sim.py` 的模拟宿主，响应带 `simulated: true`。它证明契约、状态机、
> 差异与恢复逻辑可运行，**不是真实 EasyEDA 写入/保存/重开/DRC 证据**。真实宿主本轮
> 只做了只读探测，写/保存/重开/DRC 为 `NOT RUN`，用户已要求停止真机操作。
>
> **基准产物**：`benchmarks/offline-round12/result.json`（16/16 PASS，simulated host，
> `real_eda=NOT RUN`，2026-10-27 收尾轮实跑）。三个案例 JSON 的证据路径均已
> 指向该现存文件，证据链闭合。
>
> **真机状态（2026-10-27 12:15 +08）**：独立工程副本的真实纵向验证尚未执行；
> 当时 EasyEDA 窗口由另一会话用于其受控写入，本会话已确认不写该窗口/工程。
> 真实写、保存、重开、DRC 全部 `NOT RUN`。
>
> 夹具是 photo-led 工程的只读采集冻结副本；为可重复性，文件内窗口/工程 ID 已归一化为
> `win-sim` / `proj-sim-0001` / `pcb-sim-0001` / `sch-sim-0001`，不是当前在线工程 UUID。

## 1. 输入夹具（精确路径）

| 文件 | 内容 |
|---|---|
| `tests/fixtures/feedback/board-before.json` | PCB 只读 dump：19 个器件、67 条走线、0 过孔、2 块铺铜；含 U1/C2/J1 焊盘与网络 |
| `tests/fixtures/feedback/schematic-before.json` | 原理图只读 read：37 条 component 记录（其中 19 个有位号）、12 个网络、8 条自由文本、sch DRC 1 条 ATTRMATCHCODE warn |
| `tests/fixtures/feedback/fake_easyeda.py` | 模拟 easyeda CLI；`simulated: true`；支持 timeout/garbage/wrong_context/partial/save_fail/reload_lost 等故障注入 |
| `tests/feedback_sim.py` | 用夹具构造模拟宿主状态与 `FakeRunner`；不解析 PATH 上的真实 `easyeda` |
| `benchmarks/offline-round12/result.json` | 16 个离线基准结果；`real_eda=NOT RUN`；本轮验收引用的基准产物 |
| `docs/round12/evidence/live-baseline/copy-pcb-check-before.json` | 真实只读 `pcb check`：native DRC 0，但 C1 890mil、C2 150mil decap-too-far，另有 power-not-poured/width-under-spec |
| `docs/round12/evidence/live-baseline/copy-sch-score.json` | 真实只读排版评分：frame-fit 88，attribution “text 7000fc9074f2508d overlaps text ed1db1e2379b6cfd by 55.01×12.00 raw（文本带为估算）” |
| `docs/round12/evidence/live-baseline/copy-drc-before.json` | PCB DRC `passed=true,total=0`（只读基线，不是本轮复验） |

## 2. 模拟链路（实际执行结果）

### 2.1 observe

`collect_observation(runner=FakeRunner(...), window='win-sim', project='proj-sim-0001',
sch_doc='sch-sim-0001', pcb_doc='pcb-sim-0001')`

- 读回 PCB 19 器件 / 67 走线 / 2 铺铜；原理图 19 个有位号器件 / 8 文本；
- PCB DRC 为 0；原理图 DRC 为 1 条 warn（ATTRMATCHCODE）；
- `unknown[]` 明确记录：原理图 rotation/mirror/device/symbol、pin primitive_id、
  PCB 多数器件的 locked、PCB unrouted；
- 响应 context 与目标 window/project/document 一致；没有任何写入。
- 基准用例 `observe_contract` 复核同一批计数与 `semantic_sha256`
  `96e97b2d…7868c`，并确认 `degradations=[]`、`simulated=true`。

### 2.2 intent

`infer_intent` 输出网络聚类、电源网络候选和固定件：J1 因 `locked=true` 进入
`fixed`；功能名保持 `cluster-N`，不把网络名直接改写成功能模块。J1 也是锁定不变量
的对象。

### 2.3 evaluate（三层，无总分）

`evaluate(observation, intent)` 实际输出：

- `verdict = pass_with_warnings`；`hard = pass`，`engineering = warn`，`readability = warn`；
- `drc_zero_but_quality_issues = true`（原生 DRC 0 不等于工程质量通过）；
- `confirmed_issues` 6 条：C1 decap 890mil、C2 decap 150mil、+5V/VIN power-not-poured、
  +5V/VIN width-under-spec；
- `suggestions` 1 条：`text-overlap`（标题 `ed1db1e2379b6cfd` 与说明
  `7000fc9074f2508d`，55.01×12.00 raw，估算文本带，advisory）；
- 基准用例 `drc_zero_but_poor` 复核 `verdict=pass_with_warnings`、
  `drc_zero_but_quality_issues=true`、`hard=pass`、`engineering=warn`、confirmed codes
  `decap-too-far/power-not-poured/width-under-spec`；
- **文本证据不一致**：`tests/fixtures/photo-led-acceptance.json` 中同名标题的
  primitiveId 是 `e176a846f166e131`、bbox 为 793..805，说明文字 bbox 778..790，
  按该 bbox 并不重叠；而案例/score 用的是 `ed1db1e2379b6cfd`、y=792。两者不是同一
  快照，55.01×12.00 只能按 layout-score 估算值引用，不能当作官方 bbox 测量；
- **角色区分（已修）**：C1 是 10µF bulk、890mil，评价层现判为 `bulk`，只给
  conditional，不触发 `drc_zero_but_quality_issues`，也不驱动自动移动；C2 是
  RAD104 100nF、150mil，判为 `local-decoupling` 候选。无法从元件值或声明判定的
  电容判 `unknown`，`auto_action_allowed=false`。容值解析仍是启发式，阈值仍需人工/
  规则复核。

### 2.4 范围化计划（只动 C2 / 只动文本）

**PCB 分支**：契约 `hds-modification/v1`，`writable.objects=['C2']`、
`writable.nets=['+5V','GND']`，允许 `move_component/save/reload`，不变量默认包含
原理图连接/身份、PCB 焊盘网络、板框、锁定、范围外变化、DRC。计划只含 `place C2`。

- 第一次候选 `(1546.84,1450)`：placement validation 直接拒绝，`bbox_overlap C2/U1`，
  `writes_sent=0`——说明“算出一个坐标”不等于可落位；
- 改用 `(1050,1350,rotation=180)`：C2 本体在 U1 左侧、不重叠；C2 的 +5V 焊盘
  到 U1.8 中心距约 103.16mil，比原始 150mil 改善，但**没有达到案例目标 ≤100mil**，
  且未做真实 DRC/铜连接复核；
- `preview` 返回 `ok=true`、`writes_sent=0`，步骤
  `place-C2 → save → reload → dump`，每步 `in_scope`；
- **PCB 写入契约**：执行 apply 时，plan 必须携带原始实测 dump（`before_dump`，
  例如 `pcb dump --include-copper` 的结果）。若只给规范化 observation，
  `_pcb_dump_from_view` 会从 `pcb.tracks/vias/pours` 重建铜层，但铺铜几何不完整，
  委托的适配器可能误报 pour 变化。

**原理图分支**：契约 `writable.objects=['7000fc9074f2508d']`，允许
`move_text/save`；计划把说明文字移到 `(250,778)`。`preview` 返回
`writes_sent=0`，步骤 `move_text-0 (schematic.text.move) → save`。

### 2.5 模拟 apply / readback / invariants

PCB 局部移动的执行路径由基准用例 `pcb_local_apply` 在模拟宿主验证通过。该用例
把 R4 移动 10mil，plan 携带原始 `before_dump`：

| 事实 | 结果 | 说明 |
|---|---|---|
| `preview_writes_sent` | 0 | 预览没有发送写入 |
| 整体 `status` | **verified** | 契约/范围/回读一致 |
| `call_ok` | true | 模拟调用返回成功 |
| `write_confirmed` | true | 模拟回读确认 R4 位置变化 |
| `save_confirmed` | true | 模拟保存回执 ok |
| `reopen_confirmed` | true | 模拟 `doc reload` + dump ok |
| `quality_passed` | null | 未在本用例重跑质量评价 |
| 范围内变化 | 1（R4 pose） | `1600,850,0,1 -> 1600,860,0,1` |
| 范围外变化 | 0 | `outside_changes=0` |
| adapter diff | 仅 R4 pose | identity/copper/unrelated 计数均为 0 |
| invariants | 4 pass + 2 unknown | `pcb_locked`、`pcb_unrelated` 仍为 unknown |
| `simulated` | true | 不是真实宿主证据 |

- 原理图文本分支由基准用例 `text_move_vertical` 验证：preview `writes_sent=0`；
  apply `status=verified`；`call_ok/write_confirmed/save_confirmed=true`，
  `reopen_confirmed=null`（适配器未实现原理图重开，明确记为 NOT RUN）；
  diff 恰好 1 条范围内变化（文本 `7000fc9074f2508d` 的 x 由 42 改为 250），
  范围外 0；不变量 4 pass + 2 unknown；移动后文本位于 `(250,778)`；
- **C2 专项 apply 未单独执行**：本文的 C2 分支停在 preview；候选距离约 103.16mil，
  没有达到 ≤100mil，也没有真实 DRC/铜连接复核。旧版全链路失败结论已不再适用——
  该问题已通过 `before_dump` / 铜层重建修复路径解决，当前基准的 PCB 局部 apply
  是 `verified`；
- 保存/重开只发生在模拟宿主：`report.save=ok`、`report.reload=ok`，不是真实宿主保存；
- invariants 总体为 `unknown`（4 pass + 2 unknown），**不是 pass**。

### 2.6 案例注册与检索

- `design-hardware/cases/feedback-r12/` 下 3 个 `hds-case/v1` 文件均通过
  `validate_case`；`design-hardware/cases/index.json` 收录 3 例；
- 实跑 `case-search`：`{interfaces:['KF301-2P'],layers:[2],
  verification_level_min:'structural'}` 命中 2 例（`pcb-decap-c2-local-photo-led`、
  `pcb-locked-connector-preserve-photo-led`，score 均为 0.75），拒绝 1 例
  （`sch-text-overlap-photo-led`，接口/层数为 unknown）；`{text:'光敏检测'}` 命中
  `sch-text-overlap-photo-led`（1.0）；
- 基准用例 `case_library` 复核：2 匹配、1 拒绝、`reuse_rechecks=[layers,version]`、
  `can_inherit=false`；
- 案例只把 `structural` 标 `pass`，`host_readback/erc_drc/simulation/manufacturing/
  physical` 全部 `not_run`；复用检查在版本/封装/层数/工艺变化时强制复核，不继承旧结论；
- **证据链已闭合**：三个案例 JSON 都引用 `benchmarks/offline-round12/result.json`，
  该文件与 `tools/feedback_benchmark.py` 现已存在并实跑 16/16 PASS；覆盖计数
  机器可读为 3 cases / 1 project / 3 scenarios；
- **共享来源**：三个案例的 `provenance.source_project` 都是
  `photo-led-pcb-20261026`，只能算同一项目的三个场景，不是三个独立项目覆盖。

## 3. 结论

| 链路环节 | 结果 |
|---|---|
| observe → intent → evaluate | 模拟 PASS；DRC 0 + decap/text-overlap 均被分层记录（`observe_contract`、`drc_zero_but_poor`） |
| scoped plan / preview | PASS；只含 C2 或只含文本，`writes_sent=0` |
| simulated apply / readback | PASS（模拟）；`pcb_local_apply` 与 `text_move_vertical` 均为 `status=verified`，五事实分开记录；原理图 `reopen_confirmed=null` |
| invariants | 4 项 pass、2 项 unknown；整体 unknown，不是通过 |
| 案例注册/检索 | PASS（structural 层）；benchmark 证据路径已闭合；三例共享源工程 |

**不能宣称**：本案例完成真实改板、真实保存重开或真实 DRC 通过。C2 专项 apply 仍是
NOT RUN；下一步是在用户明确授权后，用真实窗口/文档 UUID 重跑同一链路，PCB 写入携带
原始 `before_dump`，并完成真实 DRC/保存/重开复验。
