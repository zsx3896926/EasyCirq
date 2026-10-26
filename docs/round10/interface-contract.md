# PCB round10 接口契约（rev4）

本文件是四个新工具的**唯一接口真源**。实现 agent 只改自己名下的文件；共享模块已由
主会话写好，不得改签名。所有坐标单位 `mil`，y-up；placement 的 `x/y` 是 **footprint
anchor**（与 `pcb_workflow.normalize_board` / `pcb dump` 一致），不是 bbox 中心。

## 0. 文件归属

| 归属 | 文件 |
|---|---|
| 已写好，只读 | `scripts/pcb_cli.py`、`scripts/pcb_evidence.py` |
| Agent P | `scripts/pcb_preflight.py`、`tests/test_pcb_preflight.py` |
| Agent A | `scripts/pcb_apply_plan.py`、`scripts/design_engine/pcb_workflow.py`（仅以下列出的改动）、`tests/test_pcb_apply_plan.py`、`tests/test_pcb_workflow.py`（仅必要修正） |
| Agent G | `scripts/pcb_gate.py`、`tests/test_pcb_gate.py` |
| Agent C | `scripts/pcb_case.py`、`tests/test_pcb_case.py`、`references/pcb-command-map.json` |
| 主会话/Agent D | `references/pcb-execution.md`、`SKILL.md`、`CHANGELOG.md`、`.version`、`scripts/skill_selftest.py` |

禁止改 `_pcb_cli.py`/`pcb_evidence.py` 的现有函数签名；需要新函数时在自己的文件里实现。
禁止改 `design-hardware/scripts/design_engine/cli.py` 的现有子命令。

## 1. 共享模块

`pcb_cli.py`：
- `run(args, easyeda=None, timeout=120, cwd=None, env=None)` → `{argv, exit, ok, error,
  stdout, stderr, payload, started_at, ended_at}`；不抛异常。
- `result(payload)`、`payload_ok(record)`、`command_record(record, stdout_path=None,
  stderr_path=None)`、`file_record(path, role=None, stage=None)`、`load_json`、
  `write_json`、`sha256_file`、`utc_now`。
- 测试必须传 `--easyeda <fake>` 或 `EASYEDA_CLI`，不得依赖 PATH。

`pcb_evidence.py`：
- `compare_sch_pcb(sch, dump, pin_aliases=None, ignore_designators=None)` → schema
  `design-engine-pcb-sch-pcb-compare/v1`，`status=match|mismatch`，含
  `component_mismatches`、`mismatches`、`rows`。
- `parse_pcb_check(payload)` → `{schema, passed, summary, counts, errors, warnings,
  infos, findings}`；`passed` 只按 `errors==0`。
- `parse_drc(payload)` → `{passed, total, counts, violations, connection_violations,
  ok}`。
- `parse_layout_lint(payload)` → `{score, crossings, components, overlap, off_board,
  short, tight, silk_over_pad, coverage_complete, incomplete}`。
- `evaluate_netpath(rows, required)` → `{status, required, connected, rows, missing,
  failed}`；只认 `status=connected` 且 `path_kind=exact-centerline`。
- `finding_key(finding)`、`validate_warn_disposition(disposition, check_report,
  check_sha256)`、`artifact_hashes(...)`、`compare_artifact_baseline(...)`。

## 2. `pcb_preflight.py`（Agent P）

命令：
```bash
python scripts/pcb_preflight.py --dump board.json [--schematic sch.json]
  [--intent intent.json] [--constraints constraints.json] [--plan plan.json]
  [--identity identity.json] [--project NAME] [--doc PCB]
  [--partial] [--out preflight.json] [--json]
```
输出 schema `design-engine-pcb-preflight/v1`：
```json
{"schema":"design-engine-pcb-preflight/v1","status":"ready|review|blocked|incomplete",
 "checks":[{"id","status":"pass|fail|unmeasured|skipped","severity":"hard|advisory",
            "objects":{},"message","source"}],
 "counts":{"pass":0,"fail":0,"unmeasured":0,"hard_fail":0,"hard_unmeasured":0},
 "board":{...},"notes":[],"not_checked":[]}
```
退出码：`ready`→0；`review`→1；`blocked|incomplete|invalid input`→2。

硬检查（unmeasured 即 blocked）：dump 组件/板框 coverage complete；`--project`/`--doc`
与 dump `source` 一致（若给了）；constraints `status=compiled`（`conflicts` 只允许
`edge_fixed_requires_pose_check`）；placement `hard_ok=true` 且 `hard_failed=0`、
`hard_unmeasured=0`；plan `base_semantic_sha256` 与 dump 一致（若给了）；每个 placement
的 `primitive_id` 存在于 dump 且唯一；每个 plan designator 已实测。

审查项（unmeasured 只 `review`，不 blocked）：
- 每个器件 bbox/pad 实测；pad 数 vs `--schematic` 的引脚数（若给了）不一致 → fail。
- EP/热焊盘：pad 号/名称含 `EP`/`9` 等不猜；若 `intent.components[].ep` 为真而 dump
  无对应 pad → fail；否则 unmeasured。
- fixed/edge/near_pin/keepout：来自 `validate_placement`；`near_pin` 的 `role=decap|
  feedback` 要求 owner pad 存在且两端网络一致（从 dump pads 判断）→ 不满足 fail。
- `intent.connectors[].opening` / `intent.rf[].antenna_keepout` /
  `intent.sensors[].no_copper_under`：有声明才检查，缺声明 → unmeasured（advisory）。
- `audit_fabrication` 的 hard findings → fail；其余 review。
- `audit_power` 非 pass → review。
- `--identity` 来自 `component_identity_check.py`；`status!=pass` → fail，未给 → unmeasured。

禁止猜：没有输入证据的检查写 `unmeasured` + `not_checked` 原因，不能写 pass。

## 3. `pcb_apply_plan.py`（Agent A）

保留现有参数 `--dump --plan --constraints --project --doc --out-dump --report --apply`
和 `expected_placement_diff`。新增：
`--playbook-out PATH`、`--easyeda PATH`、`--timeout SEC`（默认 120）、`--journal PATH`、
`--no-reload`、`--partial`、`--allow-identity-change`、`--json`。

`--plan` 接受三种形状：
1. 旧 `{"placements":[...]}`（anchor 坐标，整板）；
2. `{"schema":"design-engine-pcb-playbook/v1","ops":[...],"scope":{...},"base":{...}}`；
3. `{"ops":[...],"scope":{...}}`。

ops：
```json
{"op":"place","designator":"C99","primitive_id":"...",
 "from":{"x":0,"y":0,"rotation":0,"layer":1},
 "to":{"x":0,"y":0,"rotation":0,"layer":1},"reason":"..."}
{"op":"track","net":"+3V3","layer":1,"width_mil":10,"points":[[0,0],[100,0]]}
{"op":"via","net":"GND","x":0,"y":0,"hole_mil":12,"diameter_mil":24}
{"op":"pour","net":"GND","layer":1,"points":[[0,0],[100,0],[100,100]],"fill":"solid"}
```
`scope`：`{"designators":[],"nets":[],"bbox":[minX,minY,maxX,maxY]?}`；缺省从 ops 推导。

行为：
1. 读 dump → `normalize_board`；若 plan 有 `base`，校验 `semantic_sha256` 与 dump 一致，
   否则 `refused`/exit 1。
2. placement 用 `validate_placement(..., partial=--partial or plan.partial)`；硬失败拒绝。
   新增 `partial` 参数：为真时只校验列出的 designator，不报未列出的
   `unplaced_component`；默认 false 保持旧行为。
3. 修正 `validate_placement` 的一个质量缺陷：preferred 约束失败时 finding 的
   `severity` 必须是 `preferred`（不得是 hard），不得让 `hard_ok=false`。hard 约束保持原样。
   （如现有测试断言旧行为，修正测试并在报告里说明原因。）
4. track/via/pour 做几何校验：点/坐标在板框内、layer 在实测层数内、net 非空且存在
   （净名以 dump `nets`/pads 为准）、width>0；不满足 `refused`。
5. 编译 `easyeda apply` playbook v1（不手写 shell）：
   - place → `{"run":"pcb modify","flags":{"id":pid,"patch":"{\"x\":..,\"y\":..,
     \"rotation\":..,\"layer\":..}"},"assert":{"$.verified":"true"}}`；一次 patch 写完整
     pose（anchor 语义）。
   - track → 每段一个 `{"action":"pcb.line.create","payload":{"startX":..,"startY":..,
     "endX":..,"endY":..,"layer":..,"lineWidth":..,"net":..},
     "assert":{"$.primitiveId":"exists"}}`。
   - via → `{"action":"pcb.via.create","payload":{"x":..,"y":..,"holeDiameter":..,
     "diameter":..,"net":..},"assert":{"$.primitiveId":"exists"}}`。
   - pour → `{"action":"pcb.pour.create","payload":{"points":[[..]],"net":..,
     "layer":..,"fill":..},"assert":{"$.verified":"true"}}`。
   - save → `{"action":"pcb.save","assert":{"$.saved":"true"},"checkpoint":true}`。
   - reload → `{"run":"doc reload","args":["<doc>"]}`（`--no-reload` 时不加）。
   - dump → `{"run":"pcb dump","flags":{"include-copper":true,"out":"<out-dump>"}}`。
   所有默认 `retry:0`、`timeoutSec:--timeout`、`continueOnError:false`。
6. 默认 dry-run：写 playbook + report（`status=dry_run`），不调用 CLI。
7. `--apply`：一次 `easyeda apply <playbook> --project <project> --doc <doc>`（不加
   `--yes` 除非显式 `--yes`）；然后校验 journal、out-dump 存在、dump 可解析。
8. 独立 `diff_boards(before, after, scope)`：
   - 纯 placement：`status in (match, changed)`、`identity_changes`/`copper_changes`/
     `unrelated_changes` 为空；否则 `mismatch`。
   - 含 track/via/pour：`unrelated_changes` 必须为空；`identity_changes` 仅当
     `--allow-identity-change`；`copper_changes` 允许；`geometry_changes` 必须在
     scope.designators 内。
9. 报告记录：playbook 路径、journal 路径、每步 status、save/reload 结果、dump
   sha256、diff、argv、版本。任何 save/reload/dump 失败都不能 `verified`。

## 4. `pcb_gate.py`（Agent G）

命令：
```bash
python scripts/pcb_gate.py --case DIR [--profile full|regression]
  [--baseline-manifest FILE] [--key-nets FILE] [--warn-disposition FILE]
  [--dump-before F] [--dump-after F] [--constraints F] [--plan F] [--intent F]
  [--check F] [--drc F] [--lint F] [--netpath F] [--sch-pcb F] [--sch F]
  [--images DIR] [--out report.json] [--json] [--strict-advisory]
```
输出 schema `design-engine-pcb-gate/v1`：
```json
{"schema":"design-engine-pcb-gate/v1","status":"pass|pass_with_gaps|fail|blocked",
 "profile":"full|regression","stages":[{"id","title","status":"pass|fail|blocked|not_run",
 "required":true,"findings":[],"evidence":[],"metrics":{}}],
 "counts":{...},"not_checked":[],"next_command":"..."}
```
退出码：`pass|pass_with_gaps`→0；`fail|blocked`→1；输入/schema 错误→2。

阶段：
- `PG1_placement`（full 必需；regression 可选）：constraints `status=compiled`（只放行
  `edge_fixed_requires_pose_check`）；placement `status=pass`、`hard_ok=true`、
  `counts.hard_failed=0`、`hard_unmeasured=0`、`constraint_rows>0`；plan base hash 与
  dump 一致（若有）。缺证据 → full `blocked` / regression `not_run`。
- `PG2_layout`（full）：lint 存在且 `coverage_complete=true`、`score>=60`、
  `crossings<=8`、`overlap=off_board=short=0`；lint 晚于最终 dump（mtime 或 capture），
  否则 `fail`（STALE_EVIDENCE）。缺 → full `blocked` / regression `not_run`。
- `PG3_drc`（两者必需）：`parse_drc().ok`；DRC 文件必须晚于最终 dump（否则 fail）。
- `PG4_check`（full）：`parse_pcb_check().counts.errors==0`；每条 WARN/INFO 由
  `--warn-disposition` 处置；缺处置 → `blocked`。regression `not_run`。
- `PG5_netpath`（full）：`evaluate_netpath().status=pass`；required 来自 `--key-nets`；
  缺 key-nets → `blocked`。regression `not_run`。
- `PG6_sch_pcb`（两者必需）：`status=match`，组件/引脚数一致；有 `--sch` + `--dump-after`
  时现算，否则读 `--sch-pcb`。
- `PG7_save_reload`（两者必需）：before/after dump 存在且可解析；`diff_boards`；
  纯持久化要求 `status=match`，编辑模式（`--edit-scope`）允许 `changed` 但
  `unrelated_changes=[]`。after dump 必须晚于 save/reload 证据。
- `PG8_delivery`（两者必需）：顶/底 PNG 存在且 PNG 签名/尺寸有效、actual SVG 存在、
  BOM 存在、`.epro2` 存在并记录 SHA；若给 `--baseline-manifest`，比较角色哈希，
  任何变化 → fail（图片/BOM 不变）。缺 → `blocked`。

整体：任一 `fail` → `fail`；否则任一必需 `blocked`/`not_run` → `blocked`；否则若有
optional `not_run` → `pass_with_gaps`；否则 `pass`。`--strict-advisory` 把 advisory
finding 升级为 fail。报告必须列 `not_checked`，不能把未测量写成通过。

文件发现：按角色 glob（`pcb-drc*.json`、`pcb-check*.json`、`pcb-layout-lint*.json`、
`netpath*connections*.json`/`net-path*.json`、`sch-pcb-compare*.json`、
`save-reload-diff*.json`/`*reload*diff*.json`、`pcb-dump-final.json`/
`pcb-dump-after-reload.json`、`pcb-final-top.png` 等），`--file ROLE=PATH` 可覆盖。

## 5. `pcb_case.py`（Agent C）

命令：
```bash
python scripts/pcb_case.py --case DIR --project NAME --doc PCB
  [--key-nets FILE] [--warn-disposition FILE] [--easyeda PATH]
  [--steps dump,drc,check,lint,netpath,sch-pcb,save-reload,images,bom,archive,gate]
  [--skip-live] [--out manifest.json] [--json]
```
输出 `<case>/manifest.json` schema `design-engine-pcb-case/v1`：
```json
{"schema":"design-engine-pcb-case/v1","case_id","created_at",
 "project":{"name","uuid","doc","doc_uuid"},
 "versions":{"skill","easyeda_agent","connector","python","os","git_head"},
 "source":{"dump_before":{"path","sha256"},"dump_after":{"path","sha256"}},
 "artifacts":[{"role","stage","path","sha256","bytes","produced_at",
               "source_dump_sha256","run_after_final_reload","command":{...}}],
 "commands":[...],"gate":{"path","sha256","status"},"failures":[],"not_run":[],
 "waivers":[]}
```
实时步骤（`--skip-live` 时只组装已有文件并校验哈希）：
1. `doc switch <doc>` 到 PCB；fresh `pcb dump --include-copper`。
2. `pcb drc --json`、`pcb check --json`、`pcb layout-lint --json`。
3. `--key-nets` 逐对 `pcb net-path --from D.PAD --to D.PAD --net NET --json`，聚合
   `netpath-key-connections.json`（保留逐条 argv）。
4. `sch read`（或 `sch list --include-pins`）+ `pcb dump` → `compare_sch_pcb`。
5. `pcb save` → `doc reload` → fresh dump → `diff_boards`。
6. `pcb stage-snapshot --stage top` / `bottom`（若命令存在；先 `pcb view` 切面），
   `pcb layout render --actual --board <dump> --side both --out ...svg`。
7. `bom export --type csv`（必要时切到原理图，再切回）。
8. `project export --project-uuid <uuid> --out <case>.epro2`（不覆盖）。
9. 调用 `pcb_gate.py --case DIR --profile full` 生成 `gate-report.json`。
每个产物记录 `source_dump_sha256`；任何检查早于最终 reload 必须标
`run_after_final_reload=false`，不能宣称最终。命令失败如实写 `failures`。

## 6. 测试要求

统一 `unittest`；每个新测试文件必须能在无 EDA、无 PATH `easyeda` 的环境通过。
- 给每个工具加 `--easyeda` 注入；测试用临时目录写 fake `.cmd`/`.sh` 或 patch
  `pcb_cli.run`。**测试绝不能调用真实 `easyeda`**；断言 argv[0] 是 fake。
- `test_pcb_preflight.py`：ready/review/blocked、stale hash、stale primitiveId、
  缺失 outline、preferred 不阻塞、decap owner pin 缺失、模板条件不满足。
- `test_pcb_apply_plan.py`：dry-run 零调用；playbook 步骤顺序；一次 apply；
  首步 failed 停止；save saved=false；reload 失败；dump 缺失；diff mismatch；
  identity/copper/unrelated 边界；旧 `--plan {placements}` 兼容。
- `test_pcb_gate.py`：full pass；缺 lint → blocked；DRC 旧于 dump → fail；
  WARN 未处置 → blocked；SCH-PCB mismatch → fail；save/reload unrelated → fail；
  baseline 图片哈希变化 → fail；regression profile 的 optional not_run →
  pass_with_gaps。
- `test_pcb_case.py`：`--skip-live` 组装 manifest 并校验哈希；缺产物 → not_run/fail；
  fake CLI 回放 live 步骤顺序；manifest 不写 case 目录外。
- 现有 `test_pcb_workflow.py`：保持 25 个测试通过；如 preferred 修正导致断言变化，
  只改必要断言并说明。

## 6.1 复核后的补充（2026-10-26 晚）

独立复核发现的 fail-open 路径已修，接口相应补充：

- `pcb_apply_plan.py`：空 scope（无 designators/nets/bbox）直接 `invalid_input`；未识别的
  非空 `base` 也拒绝，不再静默关闭 stale 检查。
- `pcb_evidence.py`：DRC/lint/pcb-check 解析器带 `measured`；缺 total/crossings/summary
  字段时 `measured=false`，gate 判 `blocked`，不再默认 0 通过；WARN 处置必须写
  `source.sha256` 并与 check 报告绑定。
- `pcb_workflow.diff_boards`：铺铜边界 `source` 与 `poured`/`fills`/`regions` 语义签名
  纳入比较；scoped 编辑把材料化铺铜变化记入 `copper_geometry_changes`，纯持久化仍要求
  `match`；outline bbox 同时接受 dict/list。
- `pcb_gate.py`：PG1 的 plan base 优先对 `plan_base_dump`（edit 前 dump）校验；PG7 用
  `dump_before`（save 前 dump）；PG2/PG3/PG4 缺测量字段即 `blocked`。
- `pcb_case.py`：`--before-dump` 导入 edit 前 dump（role `pcb-dump-plan-base`），
  save/reload 另取 save 前 fresh dump（role `pcb-dump-before-reload`）；gate 报告先轮转
  再要求本次新报告且 case 路径一致；`--no-gate` 只能得到 `incomplete`；archive 存在时
  复用有效 zip 并标 `reused`；sch-pcb 逐页 `sch read` 合并，不再使用不存在的
  `sch read --out`。
- `pcb_preflight.py`：plan 的 fabrication/keepout/connector/near-pin 检查针对候选板
  （applied placements），不再用 edit 前未落位器件的外框；`--doc` 仍优先 UUID；输入
  异常统一 `invalid_input`/exit 2。

## 7. 非目标

- 不改 Gerber/CPL 导出（CLI 无能力，继续 BLOCKED）。
- 不引入外部路由器。
- 不改 `photo-led-5v-20261026`、`mcu-i2c-s3-20261026`、`boardB-final.epro2`。
- 不合并 PR、不发 Release、不下单。
