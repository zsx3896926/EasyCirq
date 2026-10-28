# PCB 执行工作流：实测几何、约束、局部模板与回读

本页只覆盖本轮已打通的范围：**低压、低速、小规模、双层 PCB**。它把 `easycirq pcb dump` / `sch read` 的实测数据接到可执行的约束、局部模板、候选与回读检查上；不承诺高速 DDR、复杂 FPGA、RF、离线市电、安规隔离或大功率变换器的自动设计。

先读 [PCB 工程习惯](pcb.md) 与 [EDA 执行](eda-execution.md)。执行器仍是 `easycirq pcb ...` / `apply` 的 typed 动作；本页的离线引擎不连接 EDA、不写工程。命令、参数与返回字段以当前 `easycirq pcb <cmd> --help` 为准；逐命令的 argv、必需/可选参数、输出角色与校验点见 [PCB 命令映射](pcb-command-map.json)。

本轮工具链按阶段串起，任何一步都不能用后一步的“通过”补前一步的缺口：

| 阶段 | 工具 | 作用 | 失败边界 |
|---|---|---|---|
| 落位前 | `scripts/pcb_preflight.py` | 用实测 dump/约束/plan 判 `ready/review/blocked` | `review/blocked/incomplete` 不是通过 |
| 批量写入 | `scripts/pcb_apply_plan.py` | 编译 playbook v1，一次 `easycirq apply` 后回读 | dry-run 外任何 save/reload/journal/dump 失败都不算 verified |
| 交付前 | `scripts/pcb_gate.py` | 只读 case 证据，PG1–PG8 阶段门禁 | 缺证据 `blocked`/`not_run`，不能写 pass |
| 证据归档 | `scripts/pcb_case.py` | 实时采集或组装 case manifest 与哈希 | `status=incomplete`，产物不能宣称最终 |

## 1. 四层证据，不互相替代

| 层 | 意义 | 成立依据 | 不成立时 |
|---|---|---|---|
| 命令存在 | `easycirq pcb <cmd> --help` 可读 | 当前 CLI 实际输出 | 不猜接口 |
| 离线可运行 | `design_engine pcb-*` 在真实 dump 上产出报告 | 输入 SHA/coverage、退出码 | 不把结构检查当 EDA 验收 |
| 真机可写入 | typed `pcb modify` / `pcb track` / `pcb via` / `pcb pour` 等返回 `verified` | 写入后 fresh dump | 只写“计划” |
| 保存重开已验证 | save → `doc reload` → fresh dump + `pcb-diff` | 身份/几何/铜一致 | 不宣称持久化完成 |

`pcb dump` 的 `availability` 必须逐类看：板框需要 PCB 为前台；缺 bbox/pad/铜时输出 `incomplete`，不得用 bbox 或空数组补签。

## 2. 输入

### 2.1 实测板

```bash
easycirq pcb dump --project <name> --doc <PCB> --include-copper --out board.json
easycirq pcb list --project <name> --doc <PCB> --include-bbox
easycirq pcb drc-rules --project <name> --doc <PCB>
easycirq pcb layers --project <name> --doc <PCB>
```

`board.json` 是本轮所有布局/布线/丝印/检查的共同几何来源。单位是 mil，y-up；`x/y` 是 footprint anchor，不是 bbox 中心。旋转、顶层/底层、pad 旋转、槽/安装孔都以实测字段为准。

### 2.2 原理图引脚—网络

在原理图为活动文档时：

```bash
easycirq sch read --project <name> --out sch-read.json
```

`components[].pins[].number/name/net` 是模板绑定的真实依据。不能仅凭器件名、位号前缀或网络名推断“这是去耦电容”“这是保护器件”。

### 2.3 工程意图（JSON）

一个项目一份 `pcb-intent.json`，至少包含：

```json
{
  "units": "mil",
  "constraints": [
    {"id": "FIX-J1", "type": "fixed", "severity": "hard",
     "source": "外壳图纸/接口方向", "designator": "J1", "x": 250, "y": 550,
     "rotation": 270, "layer": 1, "unit": "mil"},
    {"id": "EDGE-J1", "type": "edge", "severity": "hard",
     "source": "接口靠左板边", "designator": "J1", "edge": "left",
     "max_inset_mil": 150, "facing_rotation": 270, "unit": "mil"},
    {"id": "NP-C2-U1", "type": "near_pin", "severity": "hard",
     "source": "LM358 数据手册 VCC 去耦", "part": "C2", "pad": "1",
     "owner": "U1", "owner_pad": "8", "max_mil": 200, "unit": "mil"},
    {"id": "KO-MH-TL", "type": "keepout", "severity": "hard",
     "source": "M3 垫圈禁布", "shape": "circle", "center": [195, 2167.2],
     "radius": 118, "unit": "mil"}
  ],
  "modules": [
    {"id": "power-input", "template": "connector-protection-core",
     "target": {"x": 250, "y": 550, "rotation": 270},
     "roles": {
       "connector": {"designator": "J1", "pads": {"out": "1", "return": "2"}},
       "series": {"designator": "D1", "pads": {"anode": "2", "cathode": "1"}},
       "bulk": {"designator": "C1", "pads": {"power": "1", "gnd": "2"}},
       "core": {"designator": "U1", "pads": {"power": "8", "gnd": "4"}}
     }}
  ],
  "power_nets": [
    {"net": "+5V", "strategy": "pour", "current_a": 0.025,
     "copper_oz": 1.0, "temp_rise_c": 10, "source": "负载计算与实际器件"}
  ]
}
```

硬约束与优化偏好分开写 `severity: hard|preferred`。每条约束有稳定 `id`、`source`、单位；距离字段必须给 `unit`。硬失败不能用其他项的总分抵消。

### 2.4 从绑定原理图导入到空 PCB

EasyEDA 4.1.78 + 前代执行器 1.15.0 实测：Board 已绑定原理图/Pcb、PCB 仍为空时，`pcb import-changes` 能把**通过 API 放置**的原理图器件导入 PCB。2026-10-27 的双路按键板返回 `imported:true`、`componentsBefore:0`、`componentsAfter:12`、`partial:false`、`verified:true`，导入后 `sch` 与 `pcb` 的 28 个引脚/pad 网名一致。

```bash
easycirq doc open <PCB_UUID> --project <name>
easycirq pcb import-changes --project <name> --doc <PCB_UUID>
easycirq pcb save --project <name> --doc <PCB_UUID>
easycirq doc reload <PCB_UUID> --project <name>
easycirq pcb dump --project <name> --doc <PCB_UUID> --include-copper --out board.json
```

导入后仍必须回读：`import-changes` 不删除原理图已移除的器件（见 [工具陷阱](tool-gotchas.md) 第 8 节）；返回 0 件时不要反复重跑，改用 `pcb add-component --unique-id ... --nets ...` 逐件补。导入成功只证明器件/网表进入 PCB，不证明封装几何、布局或布线。该 1.15.0 实测证据在外部 `dual-button-led-night-20261027` 任务工作区，未随本仓库提交。

## 3. 约束模型与冲突诊断

支持类型：

| type | 关键字段 | 说明 |
|---|---|---|
| `fixed` | designator, x/y/rotation/layer | 绝对固定；写入后回读比对 |
| `locked` | designator（可省略 pose） | 保持实测 pose；省略 pose 时以实测值作为锁定基准 |
| `edge` | edge, max_inset_mil, facing_rotation | 靠指定板边；接口朝向独立核验 |
| `spacing` | min_gap_mil | 同层器件 bbox 最小间隙；也可用 intent 顶层 `min_component_spacing_mil` 生成 |
| `near_pin` | part/pad, owner/owner_pad, max_mil | 真实物理 pad 的关系；中心距不是铜路径 |
| `ordered_chain` | parts[], axis, max_gap_mil | 信号链顺序；用 bbox 中心投影 |
| `keepout` | circle/rect | 机械/电气禁布；与 fixed 冲突直接报 |
| `allowed_layer` | designator, layers[] | 允许的装配层 |
| `allowed_rotation` | designator, angles[] | 允许的 0/90/180/270 等 |
| `group` | members[], rigid, max_spread_mil | 需保持局部关系的器件 |
| `route_channel` | rect, nets[], width_mil | 预留出线通道；被固定件占用即冲突 |

```bash
python design_engine_cli.py pcb-constraints \
  --dump board.json --intent pcb-intent.json --out constraints.json --json

python design_engine_cli.py pcb-check-plan \
  --dump board.json --plan placement.json --constraints constraints.json --json
```

`pcb-constraints` 遇到未知 designator/pad、同件两个 fixed、near-pin 两端网络不一致、keepout 压 fixed、route-channel 被 fixed 占用，都会给出具体 constraint id、对象和原因；`status=conflicted|incomplete` 不是通过。`pcb-check-plan` 逐项输出 `pass/fail/unmeasured`，并额外检查越框、同层 bbox 重叠、pad 越框。硬失败或硬项未测量都使 `hard_ok=false`。

`near_pin` 的距离固定标注 `measurement=pad-centre-euclidean`、`copper_path_verified=false`。要证明真实铜路径，布完后用 `easycirq pcb net-path`；它不包含铺铜，铺铜网络另用 DRC/实际铜层核对。

### 3.1 落位前预检 `pcb_preflight.py`

```bash
python scripts/pcb_preflight.py --dump board.json [--schematic sch-read.json] \
  [--intent pcb-intent.json] [--constraints constraints.json] [--plan placement.json] \
  [--identity component-identity.json] [--project <name>] [--doc <PCB>] \
  [--partial] [--out preflight.json] [--json]
```

- 输入都是本地 JSON；不连接 EDA、不写工程。`--plan` 只接受 placement proposal（`{"placements":[...]}`）；playbook/`ops` 由 `pcb_apply_plan.py` 消费，preflight 不解释它。`--partial` 只校验列出的 designator。真实 dump 的 capture 通常只有 `documentUuid`、没有文档名，因此 `--doc` 优先传 PCB UUID；只传名称会得到 hard unmeasured。
- 输出 `design-engine-pcb-preflight/v1`：`status=ready|review|blocked|incomplete|invalid_input`，`checks[]` 每项含 `id/status(pass|fail|unmeasured|skipped)/severity(hard|advisory)/objects/message/source`，`counts` 分 `pass/fail/unmeasured/hard_fail/hard_unmeasured`，另有 `board/notes/not_checked`。`invalid_input` 是输入/schema 无法解释的终态，不是测量结论。
- 退出码：`ready`→0，`review`→1，`blocked|incomplete|invalid_input`→2。
- 硬检查（unmeasured 即 `blocked`）：dump 的组件/板框 coverage complete；`--project`/`--doc` 与 dump `source` 一致（若给）；constraints `status=compiled`（`conflicts` 只放行 `edge_fixed_requires_pose_check`）；placement `hard_ok=true` 且 `hard_failed=0`、`hard_unmeasured=0`；plan `base_semantic_sha256` 与 dump 一致（若给）；每个 placement 的 `primitive_id` 在 dump 中存在且唯一；plan 中每个 designator 已实测。
- 审查项（unmeasured 只降为 `review`）：每件 bbox/pad 实测、焊盘数与原理图引脚数、EP/热焊盘、fixed/edge/near_pin/keepout、连接器开口/RF 禁布/传感器禁铜、fabrication hard findings、power 非 pass、`component_identity_check.py` 结果。
- 没有输入证据的检查只能写 `unmeasured` + `not_checked` 原因，不能写 pass。`review` 必须把未测量项带进下一步，不等于可以放行。

## 4. 局部模板库

`assets/pcb-placement-templates.json` 保存角色、真实引脚映射和**相对**位置，不保存单板绝对坐标。当前模板：

- `ic-decap-gnd`：IC 电源脚—去耦电容—地。
- `connector-protection-core`：接口—保护/串联—核心输入。
- `opamp-feedback`：运放/比较器反馈、分压/采样与滤波。
- `low-side-driver-load-return`：低侧晶体管—基极网络—负载—返回。
- `ldo-caps`：LDO 输入/输出电容。
- `i2c-sensor`：I²C 传感器、上拉与去耦。
- `mcu-debug`：MCU 下载接口、复位/启动。
- `crystal-guard`：晶振与负载电容。
- `dual-channel-switch-led`：两路按键—LED—限流电阻的并列相对布局；`offline-tested`，在 2026-10-27 双路按键板的实测基线上复现了六个位姿，仍是参考不是已验证实例。

绑定规则：

1. 角色必须绑定到实测 designator 和**物理 pad 号**。
2. 模板的 `net_roles` 要求同一角色组落在同一实测网络（如 core.power 与 cap.power 都是 `+5V`）；网络不一致直接 `rejected`，不按“都是电容”猜。
3. `conditions` 用实测 bbox 长/短边做适用性检查；缺少 bbox、超出范围、相对位置缺失都返回 `rejected/incomplete`，不猜坐标。
4. `frame: core` 的相对位置随核心旋转；`frame: board` 保持板坐标流向（例如连接器为插拔旋转，但下游仍沿板内流向）。
5. 模板缺少实测几何或适用条件不满足时明确拒绝或待复核；模板不是已验证实例。

```bash
python design_engine_cli.py pcb-template-plan --dump board.json \
  --template ic-decap-gnd --binding binding.json --anchor 1500,1200,0 --json
```

`pcb-template-plan` 只输出相对布局候选；写入必须走 typed `pcb modify`，写后回读；不能用模板数据宣称已经画好。

## 5. 多候选与选择

```bash
python design_engine_cli.py pcb-candidates \
  --dump board.json --intent pcb-intent.json --out candidates.json --json
```

三种策略使用同一板框、层数、规则和器件：

1. `signal-chain`：按 intent 的模块顺序/目标，沿信号链放置。
2. `density`：在板内按模块 bbox 行式紧凑装箱。
3. `mechanical`：先放有明确目标的机械/接口模块，其余模块在剩余空间行式放置。

选择顺序：先淘汰硬约束失败候选；再比较关键局部连接失败数、逃线预判阻塞数、HPWL、模块面积。**不输出综合总分**。没有可行候选时返回 `no_feasible_candidate`，不把“预算耗尽”写成“无解”。

候选差异至少给：硬失败具体 code、近引脚失败项、阻塞逃线、HPWL、模块面积、相对参考改动的器件。执行前必须 fresh dump 对照；旧候选的 primitiveId/几何不能复用。`no_feasible_candidate` 的 `feasibility_note` 明确这是固定种子/预算内未找到，不是无解证明；`routing_verified=false` 始终保留。

### 5.1 交付门禁的 provenance 与冲突

`pcb_gate.py` 读取 case 目录时：

- 有 `manifest.json` 时优先使用 manifest 声明的 artifact 路径；`sha256`、`source_dump_sha256`、`produced_at` 是绑定依据，文件缺失不会回退到旁边的同名文件。
- 证据哈希与 manifest 不一致、源 dump 变化、项目身份不一致 → 该阶段 `EVIDENCE_BINDING` 失败；多个候选项目/页身份不同 → `EVIDENCE_IDENTITY_CONFLICT`；内容不同但可归一的多个候选 → `EVIDENCE_AMBIGUOUS`，选中的文件在报告中列出。普通角色的歧义为 advisory；**check 角色在无 manifest/`--check` 绑定时为 hard fail**，因为选错 DFM 报告会掩盖真实 finding。
- 只有文件 mtime 时，新鲜度只作辅助并在 `not_checked` 标 `freshness_basis`；复制旧证据再改时间不能变成内容绑定。
- `--sch` + `--dump-after` 计算 SCH↔PCB 时可用 `--pin-aliases` 与
  `--ignore-designators`；全部 designator 被排除是 `not_comparable`，不是完整验证。
- `compare_sch_pcb` 的 `match_with_renames` 表示引脚分组不变、仅网名变化；门禁按 advisory 处理，`partition_match=false` 才是连接差异。

## 6. 逃线与布线联合迭代

```bash
python design_engine_cli.py pcb-escapes --dump board.json --length 100 --json
```

`pcb-escapes` 只做 axis-snapped 短走廊预判，明确 `proxy=true`、`routing_verified=false`；飞线交叉数不等于不可布通，clear 也不等于可布。

实际闭环：

1. 先用本工具或 `easycirq pcb escape-plan` 找具体被堵 pad、网络、障碍物。
2. 调整相关器件（只动有关系的模块/局部），重新 `pcb-check-plan`/`pcb-candidates`。
3. 重新 dump，重复预判。
4. 至少用两次实际局部路由尝试验证预判：关键网用官方路由器或 `route-short`，读取真实 created/failed 与 DRC。
5. 若仍不可布，改变策略（换朝向/通道/层数评估/拆分模块），不缩小板框、不降低间距、不移走固定接口。

关键网顺序：实测识别出的关键局部连接 → 有具体宽度/压降要求的电源路径 → 普通信号 → 电源/地铜与缝合 → 丝印/制造。

## 7. 路由器选择

| 场景 | 首选 | 验证 |
|---|---|---|
| 关键局部短线/可预测的短跳 | `easycirq pcb autoroute --net <关键网> --layers 1,2` | 逐网 created/failed、`net-path`、DRC |
| 稀疏普通短线 | `easycirq pcb route-short` | `--dry-run` 先看 skipped/failed；完成后 DRC |
| 剩余普通网 | `easycirq pcb autoroute` | 同层/规则/器件不变；记录版本与参数 |
| 有明确收益的外部路由器 | 仅在现有路径缺失/可测收益时引入 | 同一布局/规则/网络，记录 DSN/SES、未连接、过孔、线长、DRC |

板 A 的实测经验：官方路由器 `--net VREF_2V5 --layers 1,2` 生成 12 段、0 过孔、底层走线；这是候选，不是“参考网络已合格”的证明。`route-short` 对 THT pad 可能给出 layer 12（MULTI）走线，必须读回 layer/线宽再决定是否采用；不要因为“命令返回成功”就接受。

重布只处理受影响网络或精确拥有对象。禁止默认清空全板走线/铺铜/重建器件；`rip-up` 只在有基线、有证据、明确范围的测试副本上使用。

## 8. 电源、地与真实连通

1. 先声明策略：2 层优先 GND 双面铺铜 + 必要缝合；电源网络按实际电流/压降/铜厚决定铺铜或走线。
2. 线宽计算必须有输入：`pcb-power` 使用 `current_a`、`copper_oz`、`temp_rise_c` 计算 IPC-2221 筛查宽度；没有电流输入就是 `unmeasured`，不能默认 20 mil。
3. 铺铜后 `pcb pour-rebuild`，读 `pcb pour-list` / `poured-list` / 实际铜层；创建回执不是最终铜。
4. `net-path` 不包含铺铜；GND/电源铺铜网络必须用原生 DRC + 实际铜/`poured-list`； `pcb-power` 的 pour 检查只证明“有该网铺铜对象”，不证明每个 pad 真正连通。
5. 检查孤岛、细颈、热焊盘、过孔目标层；`pcb check` 的 `netless-pour`、`power-not-poured`、`width-under-spec`、`dangling-end`、`floating-islands` 是入口，不是全部。
6. 去耦连接用 `near_pin` 约束 + 布后 `net-path`（从电容 pad 到 IC 电源 pad）；有铺铜时明确 `not_checked` 范围，人工看实际铜。

## 9. 写入、保存、重开、局部改板

写入固定项目/文档身份：

```bash
easycirq pcb modify --project <name> --doc <PCB> --id <pid> --patch '{"x":...}'
easycirq pcb save --project <name> --doc <PCB>
easycirq doc reload <PCB> --project <name>
easycirq pcb dump --project <name> --doc <PCB> --include-copper --out after.json
python design_engine_cli.py pcb-diff --before before.json --after after.json --scope scope.json --json
```

批量写入走受控适配器 `pcb_apply_plan.py`：它先把计划与 fresh dump 对账，再编译 `easycirq apply` playbook v1，一次 apply 后回读 journal、fresh dump 和 scoped diff；不再逐件调用 `pcb modify`。

```bash
python scripts/pcb_apply_plan.py --dump before.json --plan playbook.json \
  --constraints constraints.json --project <name> --doc <PCB> \
  --out-dump after.json --report apply-report.json [--apply] \
  [--playbook-out playbook.json] [--journal journal.jsonl] [--timeout 120] \
  [--no-reload] [--partial] [--allow-identity-change] [--yes] \
  [--easycirq <path>] [--json]
```

### 9.1 playbook 批量路径

`--plan` 接受三种形状：

1. 旧 `{"placements":[...]}`（anchor 坐标，默认整板；`--partial` 或 plan `partial:true` 只校验列出的 designator）；
2. `{"schema":"design-engine-pcb-playbook/v1","ops":[...],"scope":{...},"base":{...}}`；
3. 省略 schema 的 `{"ops":[...],"scope":{...}}`。

```json
{"op":"place","designator":"C99","primitive_id":"...",
 "from":{"x":0,"y":0,"rotation":0,"layer":1},
 "to":{"x":0,"y":0,"rotation":0,"layer":1},"reason":"..."}
{"op":"track","net":"+3V3","layer":1,"width_mil":10,"points":[[0,0],[100,0]]}
{"op":"via","net":"GND","x":0,"y":0,"hole_mil":12,"diameter_mil":24}
{"op":"pour","net":"GND","layer":1,"points":[[0,0],[100,0],[100,100]],"fill":"solid"}
```

`scope` 为 `{"designators":[],"nets":[],"bbox":[minX,minY,maxX,maxY]?}`；缺省从 ops 推导。坐标单位 mil，y-up，place 的 `x/y` 是 footprint anchor（不是 bbox 中心）。

适配器行为与失败边界：

1. `normalize_board` 后校验 plan `base.semantic_sha256`；与 dump 不一致或无法证明新鲜即整批 `refused`。
2. placement 用 `validate_placement`；硬失败整批拒绝。`preferred` 约束失败只记 `preferred`，不得让 `hard_ok=false`。
3. track/via/pour 做几何校验：坐标/多边形在实测 board polygon 内（凹板按 polygon，不只 bbox）、layer 在实测层数内、net 非空且存在于 dump、width/diameter>0，线宽/直径/keepout 计入边界；`arc-polyline` 标近似，无 polygon 的 arc 板拒绝；不满足即 `refused`。实测 pose 缺 x/y/rotation/layer 时拒绝，不默认成原点/顶层；目标缺 rotation/layer 继承实测值并在 `pose_defaults` 列出。
4. 编译 playbook：place 一次 patch 写完整 pose（`assert $.verified=true`）；track 每段一个 `pcb.line.create`；via 一个 `pcb.via.create`；pour 一个 `pcb.pour.create`；save 是真实 `pcb.save`（`assert $.saved=true`，`checkpoint` 不保存）；reload 为 `run doc reload`（`--no-reload` 时省略）；最后 `pcb dump --include-copper`。所有步骤 `retry:0`、`continueOnError:false`、`timeoutSec=--timeout`。目标 pose 与实测相同（含 0/360 等价角度）记 `noops`，不生成写入步骤；全为 no-op 时 `status=no_op`，不写 playbook、不调用 CLI。
5. 默认 dry-run：只写 playbook 与 report（`status=dry_run`），零 CLI 调用；相同输入产生确定的 playbook 字节序列。
6. `--apply`：只执行一次 `easycirq apply <playbook> --project <name> --doc <PCB>`（`--yes` 只在显式授权时传），随后校验 journal、out-dump 存在且可解析。journal 每步状态为 `planned|sent|confirmed|failed|unknown`；`unknown` 表示已发出但无确认。报告 `recovery.safe_to_retry=false`，必须先取 fresh dump；不把已发出当已生效。
7. 独立 `diff_boards`：纯 place 要求 `status in (match, changed)` 且 `identity_changes/copper_changes/unrelated_changes` 为空；含 track/via/pour 时 `unrelated_changes` 必须为空、`copper_changes` 允许、`identity_changes` 仅 `--allow-identity-change`、`geometry_changes` 必须在 scope.designators 内。

报告 schema `design-engine-pcb-apply-plan/v1`，`status=dry_run|no_op|refused|invalid_input|unverified|mismatch|verified`，记录 playbook 路径/SHA/步骤、journal states、`recovery`、save/reload、out-dump SHA、diff、argv 与版本；`transaction.atomic_rollback=false`，不宣称事务回滚。退出码：`dry_run|no_op|verified`→0；`refused|unverified|mismatch`→1；`invalid_input`（计划/dump/scope 无法解释）→2。报告原子写入（临时文件 + `os.replace`），半份 JSON 不会被后续当成完整证据。

- 写入前 fresh dump；primitiveId 过期/几何变化则拒绝旧计划。
- 超时/部分失败先回读，禁止盲目重放；重复执行只能补差异，不能重复创建。
- 保存前后、重开后分别比较：器件身份/封装/pad-net、板框/层叠/规则、位置/朝向/层/锁定、走线/过孔/网络归属、铺铜边界与 `poured`/`fills`/`regions` 语义几何、修改范围外对象。铺铜材料化几何没有稳定的 primitiveId，按去掉 ID 后的语义签名集合比较；纯持久化（空 scope）下任何铺铜变化都使 `match` 失败。
- `pcb-diff`/`diff_boards` 的 `scope` 只允许声明范围内的变化；`unrelated_changes` 非空即 `mismatch`。
- 局部改板只重布受影响网络/对象，保留无关区域；改封装、移接口、加去耦都按这个边界执行。
- save/reload/journal/dump 任一失败都只能报 `unverified`，不能写 `verified`。
- track/via/pour op 没有 no-op 检测，同一份铜计划执行两次就会叠出重复铜和重叠过孔。中断后拿 fresh `track-list`/`via-list` 按几何比对（网络+层+线宽，端点容差约 1 mil，可反向；过孔按网络+坐标），只把缺失的 op 组成新计划再 apply。PocketCam X1 的 1495 op 计划在第 647 步被 120 s 默认超时打断，按此比对得出 648 已落地、847 缺失，补齐后没有重复铜。
- `--timeout` 同时限制每一步和整个进程。大批量铜计划按 op 数估算（该板实测量级：约 0.3 s/op 加上 save/reload 余量），或拆成每份不超过 500 op 的计划，每份单独 apply 和回读。
- 含铜计划在 save/reload 后若报 `mismatch`：先看 diff 的实际类别（`unrelated_changes`、`copper_geometry_changes`、`identity_changes`）。`pcb_workflow` 已按语义签名匹配重开后变化的 primitiveId，纯 ID churn 不会单独构成 mismatch；`--allow-identity-change` 只对 component identity 生效，不是消除走线/过孔 ID 变化的开关。此时不能写 `verified`；按 journal 全部 `confirmed`、save/reload 成功、新增铜几何全部属于计划网络这三条逐项核对，并如实记录 mismatch 的实际类别与范围，不要把原因一律写成“ID 重开不稳定”。
- 改铜后的固定顺序：apply → `pcb pour-rebuild` → save → `doc reload` → DRC。铺铜没重建时 DRC 会报大量假错误（实测一次 1910 条、一次 375 条，重建后回到真实值）。`pcb via-bond` 只给焊盘内的无网络过孔赋网，不是每次必跑。

### 9.2 模块布局复用（不复制铜）

```bash
python design_engine_cli.py pcb-extract-module --dump board.json \
  --members U1,C2,R4 --anchor U1 --out module.json --json
python design_engine_cli.py pcb-reuse-plan --module module.json --target target.json \
  --binding binding.json --anchor 1500,1200,0 --net-map net-map.json --json
```

`pcb-extract-module` 只保存成员身份、pad 号→网络、相对位姿和 anchor，不保存绝对坐标。`pcb-reuse-plan` 要求目标器件身份/层/pad 集合一致（或显式 `allowed_substitutes`）、每个 pad 的网络在 `net_map` 后与目标一致；任一项不满足即 `rejected`。旋转/平移按 anchor 重算，不反推旧坐标。

`copper_reuse.status` 固定 `not_supported`：不复制造线/过孔/铺铜，因为源板的障碍、网络归属和铺铜回流条件不同。复用后必须重新布局检查、重新布线/铺铜/DRC；不能把源板铜坐标复制到目标板。

### 9.3 局部移动前空间检查

任何局部移动（尤其是“LED 上移 2 mm”“电容靠近芯片”这类看起来很小的改动）先做离线空间预检：

```bash
python scripts/check_move_clearance.py --dump before.json \
  --designator D4 --dx 0 --dy 78.74 --clearance 10 --edge-clearance 20 --json
```

它只比较**器件本体 bbox**与同面板框/其他器件，输出 `clear|conflict|blocked|invalid_input`；不证明铜间距、走线、丝印、keepout 或 DRC。`conflict` 时不得写入；`clear` 也不是写授权，写完必须 fresh dump + DRC。

真实负例：`cases/dual-button-led-night-20261027/negative-direct-move/` 保留了首次 LED2 直接上移 2 mm 的输入。第一基线 D4 顶部到 R3 底部只有 73.559 mil，+78.74 mil 会重叠 5.181 mil；`pcb-check-plan` 和本工具都必须拒绝它。接受版先下移 D3/D4 30 mil 预留空间，再做同样的 +2 mm 改板。不要把这个返工从报告里删掉，也不要把它写成“任意既有布局都能自主解决冲突”。

### 9.4 DRC 收敛中的删除与补连

- 删除粒度：器件用 `pcb delete --ids`，它只认器件，传走线或过孔 id 会被拒绝（`PRECONDITION_REFUSED`）。单段走线和单个过孔用 `pcb track-delete --ids` / `pcb via-delete --ids`；整个网络才用 `rip-up --net`。删除后重新 `track-list` / `via-list` 确认这些 id 已不存在，不要只看链式命令末尾的 `saved:true`。
- 重建铺铜并重开后，电源/地焊盘仍报 disconnected 时按顺序排查：(1) 是否是焊盘内过孔，`pcb check` 的 `via-in-pad` 说明它不算连通，改成 dog-bone 短线加过孔；(2) 用 `poured-list` 确认过孔确实落在该网铺铜/平面内；(3) 仍不通，在平面层画一段显式走线，接到 DRC 已判连通的同网过孔，不要再反复等铺铜。PocketCam X1 的 C20.2 就是靠第 (3) 步收敛的；根因未能确定，不写成“DRC 不认铺铜连接”。新增铜先离线算到异网铜的最小间距，低于规则就不写。

## 10. 交付前门禁 `pcb_gate.py`

```bash
python scripts/pcb_gate.py --case <case-dir> [--profile full|regression] \
  [--baseline-manifest manifest.json] [--key-nets key-nets.json] \
  [--warn-disposition warn-disposition.json] \
  [--dump-before F] [--dump-after F] [--constraints F] [--plan F] [--intent F] \
  [--check F] [--drc F] [--lint F] [--netpath F] [--sch-pcb F] [--sch F] \
  [--images DIR] [--edit-scope scope.json] [--file ROLE=PATH] \
  [--out gate-report.json] [--strict-advisory] [--json]
```

- 只读 case 证据目录：按角色 glob 发现文件（`pcb-drc*.json`、`pcb-check*.json`、`pcb-layout-lint*.json`、`netpath*connections*.json`/`net-path*.json`、`sch-pcb-compare*.json`、`save-reload-diff*.json`、`pcb-dump-final.json`/`pcb-dump-after-reload.json`、`pcb-final-top.png` 等），优先 `*-final*`，`--file ROLE=PATH` 可覆盖任一角色。角色与命令见 [PCB 命令映射](pcb-command-map.json)。有 `manifest.json` 时按 manifest 路径/哈希/`source_dump_sha256`/`produced_at` 绑定；文件缺失不回退，哈希或源 dump 变化、项目身份不一致都是 `EVIDENCE_BINDING` 失败。多个候选身份冲突见 `EVIDENCE_IDENTITY_CONFLICT`，内容分歧见 `EVIDENCE_AMBIGUOUS`（check 角色未由 hash-bound manifest/`--check` 绑定时 hard，其他角色 advisory）。check 角色还要求 DFM `summary` 计数器与逐条 findings 一致、`trackCount`/`padCount` 来源计数，placement-check 不能冒充；新出现但 shape/解析被拒绝的 check-like 候选另见 `EVIDENCE_CANDIDATE_REJECTED`，旧报告不能静默 pass。比较内容差异用 `semantic_sha256`，原始 `sha256` 只作审计；同内容不同格式不判歧义。
- 输出 `design-engine-pcb-gate/v1`：`status=pass|pass_with_gaps|fail|blocked`，`stages[]` 每项 `status=pass|fail|blocked|not_run` + `required/findings/evidence/metrics`，另有 `counts/not_checked/next_command`。
- 退出码：`pass|pass_with_gaps`→0；`fail|blocked`→1；输入/schema 错误→2。

| 阶段 | 检查 | full | regression |
|---|---|---|---|
| `PG1_placement` | constraints compiled；placement `status=pass/hard_ok=true/hard_failed=0/hard_unmeasured=0/constraint_rows>0`；plan base hash 与 dump 一致 | 必需 | 可选 |
| `PG2_layout` | lint `coverage_complete=true`、`score>=60`、`crossings<=8`、`overlap=off_board=short=0`；lint 必须晚于最终 dump | 必需 | 可选 |
| `PG3_drc` | 原生 DRC `ok`；DRC 必须晚于最终 dump（否则 `STALE_EVIDENCE`） | 必需 | 必需 |
| `PG4_check` | `pcb check` `errors==0`；每条 WARN/INFO 由 `--warn-disposition` 处置 | 必需 | 不运行 |
| `PG5_netpath` | `evaluate_netpath().status=pass`；required 来自 `--key-nets` | 必需 | 不运行 |
| `PG6_sch_pcb` | SCH-PCB `status=match`/`match_with_renames`，组件/引脚数一致；`not_comparable` 失败；有 `--sch`+`--dump-after` 时现算，可加 `--pin-aliases`/`--ignore-designators` | 必需 | 必需 |
| `PG7_save_reload` | before/after dump 可解析；`diff_boards` 纯持久化要求 `match`，`--edit-scope` 允许 `changed` 但 `unrelated_changes=[]` | 必需 | 必需 |
| `PG8_delivery` | 顶/底 PNG 签名与尺寸、actual SVG、BOM、`.epro2` 存在并记 SHA；`--baseline-manifest` 角色哈希变化即 fail | 必需 | 必需 |

整体判定：任一 `fail`→`fail`；否则必需阶段 `blocked`/`not_run`→`blocked`；否则 optional `not_run`→`pass_with_gaps`；否则 `pass`。`--strict-advisory` 把 advisory finding 升级为 fail。缺证据只能 `blocked`/`not_run`，不能写 pass；报告必须列 `not_checked`。

## 11. 丝印与交付

交付前逐项核对 [PCB 交付检查清单](../assets/pcb-delivery-checklist.md)：身份/范围、原理图、PCB、局部改板、BOM、原生归档、图片与限制口径。清单是提醒，不替代 DRC、原厂资料、实物测试或制造审核。

```bash
python design_engine_cli.py pcb-fabrication --dump board.json --json
```

`pcb-fabrication` 从实测 dump 检查可见丝印 bbox 压同面焊盘/越框/倒置、无网络铺铜、边界无材料化铜、无网络过孔/过孔在焊盘内网络不符。它只读 dump BBox；`pcb check` 可能用更大的实时渲染字框，两者不一致时以实际导图和写后回读为准，不能单凭一方判“丝印合格”。

- `pcb silk-align` / `silk-plan` / `silk-set` 使用实测文字 bbox；写后读真实 bbox、层、朝向，再复跑 `pcb check`（silk-over-pad / silkscreen-flipped）。
- 接口方向、极性、1 脚、电源标识必须与实际引脚一致；文字不压焊盘、不越板框、不遮挡装配后标记。
- 交付图用官方导出或 `stage-snapshot`/`layout render --actual`；3D 只补充装配检查，不能代替顶层/底层铜层与网络验收。
- 制造包导出后做离线完整性核对；未导出 Gerber/钻孔/CPL 时如实写 `BLOCKED`。

## 12. 案例证据归档 `pcb_case.py`

```bash
python scripts/pcb_case.py --case <case-dir> --project <name> --doc <PCB> \
  [--schematic F] [--key-nets F] [--warn-disposition F] [--easycirq PATH] \
  [--steps dump,drc,check,lint,netpath,sch-pcb,save-reload,images,bom,archive,gate] \
  [--skip-live] [--no-gate] [--gate-script F] [--before-dump F] \
  [--out manifest.json] [--archive <case>.epro2] [--timeout SEC] [--json]
```

- 实时模式按固定顺序采集：`doc switch` 到 PCB → fresh dump（受控改板用 `--before-dump` 导入 edit 前 dump）→ `pcb dump`（save 前）→ `pcb save` → `doc reload` → fresh dump + `diff_boards` → DRC/check/lint → 关键网 `pcb net-path`（逐对 argv 聚合）→ 逐页 `sch read` + dump 比对 SCH-PCB → 顶/底图与 actual SVG → BOM → `.epro2` 归档 → 调用 `pcb_gate.py --profile full` 生成 `gate-report.json`。检查在最终 reload 之后运行并绑定最终 dump。
- `--skip-live` 只组装并校验 case 目录中已有产物与哈希，绝不调用 `easycirq`；适合复核已采集证据。
- 输出 `<case>/manifest.json`，schema `design-engine-pcb-case/v1`：`status=complete|incomplete|failed`、`project/versions/source/artifacts/commands/steps/gate/failures/not_run/waivers/verification`。每个产物记录 `sha256/bytes/source_dump_sha256/run_after_final_reload`，检查早于最终 reload 时必须标 `run_after_final_reload=false`，不能宣称最终。只有 gate 报告为新生成且 `status=pass` 时 manifest 才能是 `complete`；`--no-gate` 只能得到 `incomplete`。
- 退出码：`complete`→0；`incomplete|failed`（缺产物或存在 failure）→1；参数/输入错误→2。
- 所有写入限制在 case 目录内；默认 `.epro2` 存在时不覆盖；已存在的有效归档会被复用并在 manifest 标 `reused`。命令失败如实写 `failures`，缺产物写 `not_run`，不把未采集项写成通过。

## 13. 本轮真实案例与能力边界

- 5V 光控 LED 板：THT/混装，90×60mm，4 个 M3 孔；约束/模板/候选在真实 dump 上运行，官方路由器布 VREF，后续信号/铺铜/丝印/DRC/保存重开按本页执行。
- MCU + I²C 传感器小板：SMT，独立工程，USB-C/下载接口、LDO、传感器与上拉；模板/候选复用同一引擎。
- 已在离线测试覆盖：实测几何归一化、约束冲突、模板绑定/拒绝、三候选、逃线代理、前后 diff、电源宽度/IPC-2221、CLI。
- 四个阶段工具由 `tests/test_pcb_preflight.py`、`test_pcb_apply_plan.py`、`test_pcb_gate.py`、`test_pcb_case.py` 用 fake `easycirq` 覆盖；测试不调用真实 EDA，也不代表任何真实工程已写入或已交付。
- 未由本页证明：高速/阻抗/回流、EMC/热、铺铜连通性、安规、RF、复杂封装、制造 DFI、实物功能。
- 未执行/工具不支持的项必须写 `NOT RUN` / `BLOCKED`；DRC 清零不等于电路、EMC 或热设计通过。
