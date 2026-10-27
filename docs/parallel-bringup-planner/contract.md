# 首板测试计划生成器输入/输出契约（bringup-planner v1）

> 状态：并行任务 I 的冻结契约。工具只做**离线计划生成与结果评估**，不连接仪器、不执行 shell、不烧录、不上电、不调用 EDA。
> 代码入口：`design-hardware/scripts/bringup_planner/`；运行方式见 [`report.md`](report.md) 与 [快速开始](#12-快速开始)。

## 1. 目的与边界

`bringup_planner` 把"设计意图 + 已有证据 + 声明设备能力"转换为按依赖排序的、由人执行的**首板上电与功能测试计划**，并提供一个独立的结果评估器：

- 计划生成（validate / plan / explain）与结果评估（evaluate）是**两个不同阶段**；生成计划从不等于执行测试。
- 缺关键参数时输出 `unknown` / `blocked` / 缺口，**不填默认电压、默认限流、默认电阻阈值或默认时间窗**。
- 所有退出码、状态、哈希绑定都是机器可读契约；文件原子写入，stdout 不混日志，诊断走 stderr。

## 2. CLI

```bash
# 在 design-hardware/scripts 目录下运行（或把该目录加入 PYTHONPATH）
python -m bringup_planner validate --input plan-input.json [--json]
python -m bringup_planner plan     --input plan-input.json --out out/ [--json]
python -m bringup_planner explain  --input plan-input.json [--step STEP_ID] [--json]
python -m bringup_planner evaluate --plan out/plan.json --results results.json \
    --out out/ [--evidence-root evidence/] [--json]
```

| 命令 | 行为 | 退出码 |
|---|---|---|
| `validate` | 只读输入，做结构/语义校验；不生成文件 | 0=valid（可有 warning）；1=invalid 输入；2=用法/IO 错误 |
| `plan` | 生成 `plan.json`/`plan.md`/`results-template.json`/`results-template.csv`/`manifest.json` | 0=已生成（即使含 blocked/unsupported 步骤）；2=输入非法，**不写计划并清理旧生成物** |
| `explain` | 输出范围判定、电源域顺序、步骤/阻塞原因 | 0=成功；1=`--step` 不存在；2=输入非法 |
| `evaluate` | 读取计划与结果，输出 `evaluation.json`/`evaluation.md` | 0=PASS；1=FAIL；2=INVALID（绑定/结构/单位矛盾）；3=INCOMPLETE/BLOCKED/SYNTHETIC_ONLY |

- `--json` 时 stdout 只输出一个 JSON 对象；默认输出人类可读文本。诊断与警告始终写 stderr。
- `--out` 不允许等于输入文件所在目录（`E_OUTPUT_INSIDE_INPUT`）；工具绝不修改输入。
- 非法输入时，`plan`/`evaluate` 只删除自己生成过（带 `generator`/工具标记）的产物，并写 `input-invalid.json`；不会删除用户文件。
- 所有 JSON 用 `allow_nan=False`、UTF-8、2 空格缩进、结尾换行；Markdown/CSV 同样原子写入。

## 3. 输入文档：`bringup-plan-input/v1`

顶层必须包含（缺组=invalid；组内空列表允许，由 plan 报缺口）：

| 字段 | 必需 | 说明 |
|---|---|---|
| `schema` | 是 | 固定 `bringup-plan-input/v1` |
| `project` | 是 | 工程身份、revision、快照哈希、BOM/装配版本、范围声明 |
| `power_domains` | 是，≥1 | 电源域、工作/绝对最大范围、依赖、电流、保护 |
| `assemblies` | 是 | DNP、跳线、变体、可拆负载、外部供电路径、短路判据 |
| `interfaces` | 是 | 连接器/引脚/角色/电平/固件前提/回灌风险/输出类型 |
| `testpoints` | 是 | 真实测点、所在网络、参考地、接触方式、可达性声明 |
| `equipment` | 是 | 电源/万用表/示波器/电子负载能力（未知能力=缺口） |
| `operating_conditions` | 是 | 环境、负载、限流策略、观察窗口、容差、必需状态 |
| `device_facts` | 是 | 原厂资料事实（型号/修订/页节/URL/条件） |
| `user_policy` | 是 | 仅计划模式、允许/禁止操作、电压电流上限、人工确认点 |
| `evidence_sources` | 是 | 已有证据（DRC/网表/BOM/装配/制造/目视）及 revision/哈希 |
| `input_completeness` | 否 | 输入方自报完整度（不代替工具计算） |
| `notes` | 否 | 自由文本；**不参与任何判据**，也不进入语义哈希 |

### 3.1 project

```json
{"name":"...", "revision":"rev-A", "source_snapshot_hash":"<64 hex>",
 "bom_version":"...", "assembly_version":"...",
 "scope":{"supply_class":"dc_low_voltage",
          "operations":["visual_inspection","deenergized_continuity",
                        "powered_dc_measurement","digital_interface",
                        "analog_measurement","low_side_load"],
          "notes":"..."}}
```

- `revision`、`source_snapshot_hash`、`bom_version`、`assembly_version` 都是结果绑定的一部分。
- `supply_class` 允许 `dc_low_voltage` 与声明为超出范围的 `mains_ac` / `high_voltage_dc` / `battery_charging` / `rf_certification` / `mixed_energy`；后几类判 `unsupported`/`needs_specialist`。
- `operations` 是 lower_snake_case 操作声明；是否支持按与所需操作的交集判断，**不按项目名或自由文本猜**。

### 3.2 power_domains

```json
{"id":"VDD_3V3","net":"+3V3","ground_net":"GND",
 "nominal_v":3.3,"operating_min_v":3.14,"operating_max_v":3.46,
 "absolute_max_v":4.0,
 "source":"U2 LDO output",
 "depends_on":[{"domain":"VIN_5V","reason":"LDO input"}],
 "startup_current":{"value":0.05,"basis":"project_requirement","source_ref":"EV-01"},
 "static_current":{"basis":"unknown"},
 "runtime_current":{"value":0.04,"basis":"datasheet","fact_id":"F-021"},
 "load":"MCU + sensor",
 "protection":{"reverse_blocking":"none","current_limit_a":0.5},
 "removable_load":false}
```

- 电压/电流字段可写**裸数值**（按 SI 单位：V/A）或 `{"value":...,"unit":"..."}`；单位未知/量纲不符=invalid。
- 校验：`operating_min<=operating_max<=absolute_max`、`nominal` 在声明工作范围内、无负电压/负电流；`absolute_max` 只是越界上限，**不是测试目标**。
- `startup_current` / `runtime_current` / `static_current` 的 `basis` 属于 `datasheet|calculation|project_requirement|measurement|estimate|unknown`；`unknown` 必须不带数值（不得猜），按此判断限流能否生成。
- `depends_on` 构成上电 DAG；自依赖、缺依赖、环路都是 invalid/gap，不会"按顺序猜"。

### 3.3 assemblies

- `dnp[]`：`{designator, part?, reason?}`
- `jumpers[]`：`{id, default_state, configurations[], required_state_for_test}` — 生成配置核对步骤。
- `variants[]`、`removable_loads[]`：可拆负载/装配变体与默认连接状态。
- `protection_and_polarity`：保护与极性说明。
- `external_supply_paths[]`：`{id, net, can_backfeed, disconnect_required_for_deenergized_tests}` — 与电源域同名网络且无 ORing/防反接时，生成的断电测量与上电步骤必须要求断开/标 blocked。
- `short_check_criterion`：**可选** `{max_ohm, basis, source_ref, conditions}`。未声明时断电电阻步骤的判据是 `undefined`/`needs_interpretation`，工具**不输出通用欧姆阈值**。

### 3.4 interfaces

```json
{"id":"J1_USB","type":"usb",
 "pins":[{"pin":"A4","net":"VBUS","role":"power"},{"pin":"A1","net":"GND","role":"ground"}],
 "logic_level_v":3.3,"firmware_prerequisite":"USB-Serial/JTAG 固件尚未烧录",
 "backfeed_risk":true,"output_type":"single_ended_ground_referenced"}
```

- `type` ∈ connector/usb/uart/i2c/spi/gpio/analog_input/analog_output/led/button/load_output/bridge_output/debug/other。
- `output_type` ∈ `single_ended_ground_referenced|bridge_tied_load|differential|floating_unknown`；`bridge_tied_load` 时禁止单端接地示波器测量，缺差分能力相关步骤 blocked。
- 同网络同时声明 power 与 ground、电源网络回灌无防反接 → 校验错误/警告。
- 固件/主机前提缺失时，通信步骤只能写"未烧录前不应期待业务通信"。

### 3.5 testpoints / equipment

- 测点：`{id, net, reference_net, contact, reachability_verified, location?}`。`reachability_verified` 必须显式声明——**手工声明测点不等于已证明可达**；未声明 → invalid。
- 设备：`supplies[]{id,model,max_voltage_v,max_current_a,...}`、`multimeters[]{id,model,dc_voltage_max_v,diode_mode,...}`、`oscilloscopes[]{id,model,bandwidth_mhz,channels,grounding,probe{type,bandwidth_mhz,max_voltage_v}}`、`electronic_loads[]{...}`。能力不足/未声明 → 设备缺口，相关步骤 blocked，不假定"应该够"。

### 3.6 operating_conditions / device_facts / user_policy / evidence_sources

- `current_limit_policy`：`{value,basis,source_ref?,conditions?}`；缺失时不生成默认限流。
- `observation_window_s`：`{value,basis,...}`；缺失时观察窗口标待确认，不编秒数。
- `tolerances`：可选 `{voltage,current,temperature}` 比例。
- `device_facts[]`：`{id,kind,device,manufacturer?,document,revision,section,page?,url,conditions?,facts[{key,value,unit?,qualifier?,typical?,page?,quote?}],unverified?}`；URL 必须 http(s)，数值 fact 必须有单位；`typical=true` 只作量级参考。
- `user_policy`：`mode` 只能 `plan_only`（其他值→unsupported）、`allowed_operations`、`forbidden_operations`、`max_input_voltage_v`、`max_current_a`、`human_confirmation_points`。缺少安全边界时不上电。
- `evidence_sources[]`：`{id,kind,path,sha256?,revision,captured_at?}`；路径必须相对、无 `..`/盘符/URL；revision 与 project 不一致 → 警告并作为旧证据处理。

## 4. 归一化与哈希

- 所有集合按稳定 `id` 排序；数值统一换算为 SI 后存储；重复 JSON key、NaN/Infinity、bool 冒充数字、未知单位 → invalid。
- `input.sha256`：原始文件字节哈希；`input.semantic_sha256`：归一化后（去掉 `notes`/路径/自哈希）的规范 JSON 哈希。
- 计划哈希 `plan_sha256`：计划文档去掉 `generated_at`、输入路径、`hashes`、自由 `notes` 后的规范 JSON 哈希。**输入对象重排/单位换算不改变计划哈希；revision 改变一定改变绑定。**
- 输出目录另有 `manifest.json` 记录每个产物的字节数与 SHA-256。

## 5. 校验错误码（节选）

`E_TYPE`、`E_REQUIRED`、`E_UNKNOWN_FIELD`、`E_ENUM`、`E_RANGE`、`E_UNIT`、`E_NONFINITE`、`E_DUPLICATE_ID`、`E_ID_FORMAT`、`E_HASH`、`E_TIMESTAMP`、`E_FUTURE_TIMESTAMP`、`E_PATH_ESCAPE`、`E_SCHEMA`、`E_DAG_SELF_DEPENDENCY`、`E_DAG_MISSING_DEPENDENCY`、`E_ROLE_CONFLICT`、`E_BACKFEED_RISK`（警告）、`E_NO_TESTPOINT`（警告）、`E_EVIDENCE_REVISION`（警告）、`E_POLICY_RANGE`（警告）。完整列表见 `model.py`。

## 6. 范围判定（scope gate）

`plan.scope.status` ∈ `supported | needs_information | needs_specialist | unsupported`；只有 `supported` 时 `energize_allowed=true`。

- 声明 `supply_class` 非 `dc_low_voltage` → unsupported/needs_specialist；不生成通用上电步骤。
- 最高工作电压 > 30 V 或绝对最大值 > 60 V → 超出首期低压包线（`needs_specialist`）。
- 所需操作未在 `project.scope.operations` 声明、未被 `user_policy.allowed_operations` 授权、或被 forbidden → 相应缺口/unsupported。
- `mode != plan_only` → unsupported（工具从不执行）。
- 安全边界缺失/矛盾 → `needs_information`，上电步骤 blocked；只输出缺口与待确认项。

## 7. 计划文档：`bringup-plan/v1`

顶层：`schema`、`generator`、`tool_version`、`generated_at`、`input{path,sha256,semantic_sha256,completeness}`、`design{project,revision,source_snapshot_hash,bom_version,assembly_version}`、`scope`、`power_domains`、`dag{domains,steps}`、`supply_conflicts`、`steps[]`、`fault_trees[]`、`gaps[]`、`unknowns[]`、`equipment_gaps[]`、`summary`、`hashes.plan_sha256`、`notes`。

### 7.1 步骤对象

| 字段 | 说明 |
|---|---|
| `step_id` | 稳定 ID（由组别+对象 ID 派生，不依赖迭代顺序/自由文本） |
| `group` | `I1` 断电检查 / `I2` 首次上电 / `I3` 电源时钟复位通信 / `I4` 负载与接口 |
| `status` | `ready` / `blocked` / `unsupported` / `advisory` |
| `blocked_reason` + `missing_information[]` | 缺什么、为什么不能执行 |
| `required` | 是否属于整板 PASS 必需步骤；advisory 步骤不参与 PASS |
| `execution` / `auto_execute` | 固定 `manual_only` / `false` |
| `prerequisites[]` | `{kind:"step",step_id,reason}` 或 `{kind:"condition",text,source_ref}` |
| `equipment[]` | `{equipment_id,capability,settings,verified}` |
| `wiring` | `{measure_at,reference,probe,notes}` |
| `procedure[]` | 人工操作步骤（不包含任何由工具执行的命令） |
| `measurement` | `{quantity,point,reference,range{min,max,unit},criterion_status,basis,source_refs,notes}` |
| `expected_behavior` | 预期现象 |
| `stop_conditions[]` | `{code,description,threshold?,action}`；阈值只来自项目/资料 |
| `failure_branches[]` | 指向故障树 id |
| `required_evidence[]` | `{kind,description,verifiable,synthetic_forbidden}` |
| `source_refs`、`safety`、`notes` | 依据与人工安全说明 |

`criterion_status` ∈ `defined|undefined|needs_interpretation|qualitative`。非 `defined` 的定量步骤不能由评估器自动判 PASS。

### 7.2 故障树

`{"id":"FT-<step>","symptom","entry_steps","boundary","nodes":[{node_id,kind,text,evidence,decidable,next,terminal}]}`，`kind` ∈ check/measure/stop/unknown/resolution；树是**假设与下一步**，不是"已确定某器件损坏"。

## 8. 结果文档：`bringup-result/v1`

```json
{"schema":"bringup-result/v1",
 "plan_binding":{"plan_sha256":"...","input_sha256":"...","input_semantic_sha256":"...",
                 "revision":"rev-A","tool_version":"1.0.0"},
 "executed_by":"...", "source_kind":"real_measurement",
 "results":[{"step_id":"I2-SEQ-VIN_5V","status":"pass",
             "source":"real_measurement",
             "instrument":{"equipment_id":"PSU1","model":"...","settings":"5.0V/200mA"},
             "measured":{"quantity":"voltage","value":5.02,"unit":"V","at":"2026-10-27T12:00:00+08:00"},
             "evidence":[{"kind":"meter_reading","path":"evidence/vin-5v.jpg","sha256":"...","description":"..."}],
             "executed_by":"...","executed_at":"...","stop_triggered":false,
             "notes":"","exceptions":[]}],
 "notes":"..."}
```

- `status` ∈ `pass|fail|unknown|blocked|not_run`；`source` ∈ `real_measurement|synthetic|manual_declaration|unset`。
- `measured.value` 必须是有限数值；`unit` 必须已知且与步骤 quantity 兼容（`mV`/`V` 等可换算，量纲不符=invalid）。
- 证据路径相对 `--evidence-root`，禁止绝对路径/`..`；声明了 `sha256` 时评估器校验。
- 未给 `--evidence-root` 时证据视为未核实，整板 verdict 不能 PASS。

## 9. 评估语义（`bringup-evaluation/v1`）

- 绑定不符（plan hash / input hash / revision / tool_version）→ `INVALID`，旧结果绝不复用。
- `pass` 需要：实测数值（定量步骤）、单位兼容、落在步骤声明范围、`required_evidence` 齐全、来源为 `real_measurement`（或明确的受控人工判读，且不能构成整板 PASS）。超范围却写 pass、缺证据、步骤缺失、状态矛盾 → 不通过并列入 findings。
- `criterion_status != defined` 的步骤不能自动 pass；缺测/未测保持 `unknown`/`not_run`，**未测不默认 normal**。
- 全 synthetic 通过 → `verdict=SYNTHETIC_ONLY`、`hardware_pass=false`；混合时 synthetic 不计入硬件 PASS。
- STOP 或失败步骤的传递依赖步骤标 `blocked`；依赖中已记录的 pass 标 `INVALIDATED_BY_STOP`；独立分支按声明继续。
- `verdict`：`PASS`（全部 required 且 plan 中 ready 的步骤真实通过、证据已验证）/`FAIL`（任何 fail/stop）/`INCOMPLETE`（unknown/blocked/not_run）/`INVALID`（绑定/结构/单位矛盾）/`SYNTHETIC_ONLY`。`completion_ratio` 只报告，**不掩盖阻断**。
- 评估器只做离线一致性判定，不证明安规、EMC、温升、可靠性或量产一致性。

## 10. 确定性与变形

- 输入对象重排、单位等价换算（5000 mV ↔ 5 V）、`notes` 同义改写：不得改变计划哈希/步骤判据。
- 新增无关模块：只允许新增自身步骤，不得改变既有步骤的判据/状态。
- revision 改变：旧结果绑定失效（`INVALID`/`STALE_REVISION`），必须重新生成计划并重测。
- 场景/基准禁止按场景 ID 特判。

## 11. 明确不证明的内容

- 不证明焊好的板能工作、不证明仪器读数真实、不证明安规/EMC/温升/可靠性/量产一致性。
- 计划中的脚本/烧录/仪器操作只以**人工说明**出现；工具不通过 shell 执行任何东西。
- 任何 `pass` 都是对"记录与声明"的一致性判定；真实测量仍需人工记录、照片/SHA 证据与复核。

## 12. 快速开始

```bash
cd design-hardware/scripts
python -m bringup_planner validate --input ../../benchmarks/bringup-planner/cases/mcu-sensor-board/input.json
python -m bringup_planner plan --input ../../benchmarks/bringup-planner/cases/mcu-sensor-board/input.json --out ../../.bringup-out/mcu
python -m bringup_planner explain --input ... --step I2-SEQ-VIN_5V
python -m bringup_planner evaluate --plan ../../.bringup-out/mcu/plan.json \
    --results <填好的 results.json> --evidence-root evidence/ --out ../../.bringup-out/mcu
```

输出目录应位于输入文件目录之外；所有命令默认只读输入。完整场景见 `benchmarks/bringup-planner/`，来源见 [`source-register.md`](source-register.md)，范围见 [`supported-scope.md`](supported-scope.md)。
