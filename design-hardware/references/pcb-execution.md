# PCB 执行工作流：实测几何、约束、局部模板与回读

本页只覆盖本轮已打通的范围：**低压、低速、小规模、双层 PCB**。它把 `easyeda pcb dump` / `sch read` 的实测数据接到可执行的约束、局部模板、候选与回读检查上；不承诺高速 DDR、复杂 FPGA、RF、离线市电、安规隔离或大功率变换器的自动设计。

先读 [PCB 工程习惯](pcb.md) 与 [EDA 执行](eda-execution.md)。执行器仍是 `easyeda pcb ...` / `apply` 的 typed 动作；本页的离线引擎不连接 EDA、不写工程。命令、参数与返回字段以当前 `easyeda pcb <cmd> --help` 为准。

## 1. 四层证据，不互相替代

| 层 | 意义 | 成立依据 | 不成立时 |
|---|---|---|---|
| 命令存在 | `easyeda pcb <cmd> --help` 可读 | 当前 CLI 实际输出 | 不猜接口 |
| 离线可运行 | `design_engine pcb-*` 在真实 dump 上产出报告 | 输入 SHA/coverage、退出码 | 不把结构检查当 EDA 验收 |
| 真机可写入 | typed `pcb modify` / `pcb track` / `pcb via` / `pcb pour` 等返回 `verified` | 写入后 fresh dump | 只写“计划” |
| 保存重开已验证 | save → `doc reload` → fresh dump + `pcb-diff` | 身份/几何/铜一致 | 不宣称持久化完成 |

`pcb dump` 的 `availability` 必须逐类看：板框需要 PCB 为前台；缺 bbox/pad/铜时输出 `incomplete`，不得用 bbox 或空数组补签。

## 2. 输入

### 2.1 实测板

```bash
easyeda pcb dump --project <name> --doc <PCB> --include-copper --out board.json
easyeda pcb list --project <name> --doc <PCB> --include-bbox
easyeda pcb drc-rules --project <name> --doc <PCB>
easyeda pcb layers --project <name> --doc <PCB>
```

`board.json` 是本轮所有布局/布线/丝印/检查的共同几何来源。单位是 mil，y-up；`x/y` 是 footprint anchor，不是 bbox 中心。旋转、顶层/底层、pad 旋转、槽/安装孔都以实测字段为准。

### 2.2 原理图引脚—网络

在原理图为活动文档时：

```bash
easyeda sch read --project <name> --out sch-read.json
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

## 3. 约束模型与冲突诊断

支持类型：

| type | 关键字段 | 说明 |
|---|---|---|
| `fixed` | designator, x/y/rotation/layer | 绝对固定；写入后回读比对 |
| `edge` | edge, max_inset_mil, facing_rotation | 靠指定板边；接口朝向独立核验 |
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

`near_pin` 的距离固定标注 `measurement=pad-centre-euclidean`、`copper_path_verified=false`。要证明真实铜路径，布完后用 `easyeda pcb net-path`；它不包含铺铜，铺铜网络另用 DRC/实际铜层核对。

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

绑定规则：

1. 角色必须绑定到实测 designator 和**物理 pad 号**。
2. 模板的 `net_roles` 要求同一角色组落在同一实测网络（如 core.power 与 cap.power 都是 `+5V`）；网络不一致直接 `rejected`，不按“都是电容”猜。
3. `conditions` 用实测 bbox 长/短边做适用性检查；缺少 bbox、超出范围、相对位置缺失都返回 `rejected/incomplete`，不猜坐标。
4. `frame: core` 的相对位置随核心旋转；`frame: board` 保持板坐标流向（例如连接器为插拔旋转，但下游仍沿板内流向）。
5. 模板缺少实测几何或适用条件不满足时明确拒绝或待复核；模板不是已验证实例。

模板只生成候选坐标，写入必须走 typed `pcb modify`，写后回读；不能用模板数据宣称已经画好。

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

候选差异至少给：硬失败具体 code、近引脚失败项、阻塞逃线、HPWL、模块面积、相对参考改动的器件。执行前必须 fresh dump 对照；旧候选的 primitiveId/几何不能复用。

## 6. 逃线与布线联合迭代

```bash
python design_engine_cli.py pcb-escapes --dump board.json --length 100 --json
```

`pcb-escapes` 只做 axis-snapped 短走廊预判，明确 `proxy=true`、`routing_verified=false`；飞线交叉数不等于不可布通，clear 也不等于可布。

实际闭环：

1. 先用本工具或 `easyeda pcb escape-plan` 找具体被堵 pad、网络、障碍物。
2. 调整相关器件（只动有关系的模块/局部），重新 `pcb-check-plan`/`pcb-candidates`。
3. 重新 dump，重复预判。
4. 至少用两次实际局部路由尝试验证预判：关键网用官方路由器或 `route-short`，读取真实 created/failed 与 DRC。
5. 若仍不可布，改变策略（换朝向/通道/层数评估/拆分模块），不缩小板框、不降低间距、不移走固定接口。

关键网顺序：实测识别出的关键局部连接 → 有具体宽度/压降要求的电源路径 → 普通信号 → 电源/地铜与缝合 → 丝印/制造。

## 7. 路由器选择

| 场景 | 首选 | 验证 |
|---|---|---|
| 关键局部短线/可预测的短跳 | `easyeda pcb autoroute --net <关键网> --layers 1,2` | 逐网 created/failed、`net-path`、DRC |
| 稀疏普通短线 | `easyeda pcb route-short` | `--dry-run` 先看 skipped/failed；完成后 DRC |
| 剩余普通网 | `easyeda pcb autoroute` | 同层/规则/器件不变；记录版本与参数 |
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
easyeda pcb modify --project <name> --doc <PCB> --id <pid> --patch '{"x":...}'
easyeda pcb save --project <name> --doc <PCB>
easyeda doc reload <PCB> --project <name>
easyeda pcb dump --project <name> --doc <PCB> --include-copper --out after.json
python design_engine_cli.py pcb-diff --before before.json --after after.json --scope scope.json --json
```

也可用受控适配器一次完成“校验 → 逐件 typed modify → save/reload/fresh dump → scoped diff”：

```bash
python scripts/pcb_apply_plan.py --dump before.json --plan plan.json \
  --constraints constraints.json --project <name> --doc <PCB> \
  --out-dump after.json --report apply-report.json --apply
```

适配器默认 dry-run；计划有硬失败、base hash 过期或 primitiveId 不匹配时整批拒绝；首件返回 `verified:false` 即停止，不盲目重放。`--report` 记录每件命令、返回与 scoped diff。

- 写入前 fresh dump；primitiveId 过期/几何变化则拒绝旧计划。
- 超时/部分失败先回读，禁止盲目重放；重复执行只能补差异，不能重复创建。
- 保存前后、重开后分别比较：器件身份/封装/pad-net、板框/层叠/规则、位置/朝向/层/锁定、走线/过孔/铜区/网络归属、修改范围外对象。
- `pcb-diff` 的 `scope` 只允许声明范围内的变化；`unrelated_changes` 非空即 `mismatch`。
- 局部改板只重布受影响网络/对象，保留无关区域；改封装、移接口、加去耦都按这个边界执行。

## 9.1 模块布局复用（不复制铜）

```bash
python design_engine_cli.py pcb-extract-module --dump board.json \
  --members U1,C2,R4 --anchor U1 --out module.json --json
python design_engine_cli.py pcb-reuse-plan --module module.json --target target.json \
  --binding binding.json --anchor 1500,1200,0 --net-map net-map.json --json
```

`pcb-extract-module` 只保存成员身份、pad 号→网络、相对位姿和 anchor，不保存绝对坐标。`pcb-reuse-plan` 要求目标器件身份/层/pad 集合一致（或显式 `allowed_substitutes`）、每个 pad 的网络在 `net_map` 后与目标一致；任一项不满足即 `rejected`。旋转/平移按 anchor 重算，不反推旧坐标。

`copper_reuse.status` 固定 `not_supported`：不复制造线/过孔/铺铜，因为源板的障碍、网络归属和铺铜回流条件不同。复用后必须重新布局检查、重新布线/铺铜/DRC；不能把源板铜坐标复制到目标板。

## 10. 丝印与交付

- `pcb silk-align` / `silk-plan` / `silk-set` 使用实测文字 bbox；写后读真实 bbox、层、朝向，再复跑 `pcb check`（silk-over-pad / silkscreen-flipped）。
- 接口方向、极性、1 脚、电源标识必须与实际引脚一致；文字不压焊盘、不越板框、不遮挡装配后标记。
- 交付图用官方导出或 `stage-snapshot`/`layout render --actual`；3D 只补充装配检查，不能代替顶层/底层铜层与网络验收。
- 制造包导出后做离线完整性核对；未导出 Gerber/钻孔/CPL 时如实写 `BLOCKED`。

## 11. 本轮真实案例与能力边界

- 5V 光控 LED 板：THT/混装，90×60mm，4 个 M3 孔；约束/模板/候选在真实 dump 上运行，官方路由器布 VREF，后续信号/铺铜/丝印/DRC/保存重开按本页执行。
- MCU + I²C 传感器小板：SMT，独立工程，USB-C/下载接口、LDO、传感器与上拉；模板/候选复用同一引擎。
- 已在离线测试覆盖：实测几何归一化、约束冲突、模板绑定/拒绝、三候选、逃线代理、前后 diff、电源宽度/IPC-2221、CLI。
- 未由本页证明：高速/阻抗/回流、EMC/热、铺铜连通性、安规、RF、复杂封装、制造 DFI、实物功能。
- 未执行/工具不支持的项必须写 `NOT RUN` / `BLOCKED`；DRC 清零不等于电路、EMC 或热设计通过。
