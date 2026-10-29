# PCB 预布局离线训练：契约 v1（M0 冻结）

> 本文件是本任务的**唯一契约源**。案例数据、判分脚本、文档、习题集都按本文件实现；实现与本文冲突时以本文为准，改契约必须先改本文并在此登记。
>
> 定位：给 Agent 和工程师一套**离线、确定性、可复算**的 PCB 预布局（placement）训练与判分，类似原理图的「审图练习 + 排版基准集」。
>
> 边界：只判「预布局决策」。**不判** DRC、可布通、阻抗、EMC、热、制造。所有输出固定写 `placement_applied:false`、`routing_verified:false`、`drc:"NOT RUN"`、`eda_calls:0`。

---

## 0. 为什么可以离线判

预布局的判据大多是可离线复算的：板框/禁布/固定件/连接器朝向是几何；去耦、晶振、功率回路、逃线通道是可度量的代理指标；「为什么这样放」可以用显式约束（引用 PL 条目）表达。因此它比布线更适合做冻结基准与审题训练。反过来，**任何离线分数都不能替代真实 DRC/布线/仿真**，本契约在输出里写死这一点。

## 1. 交付物与路径

| 路径 | 归属 | 说明 |
|---|---|---|
| `easycirq/assets/pcb-placement-benchmarks/benchmarks.json` | 案例集 | 冻结案例数据（本契约 §2–§3） |
| `easycirq/scripts/pcb_placement_benchmark.py` | 判分器 | 离线 CLI，stdlib only（本契约 §4） |
| `easycirq/references/pcb-placement-benchmarks.md` | 读法 | 案例表 + 判据 + 评分维度 + 边界 |
| `easycirq/references/engineering-deepdives/exercises-pcb/` | 习题集 | `README.md`/`exercises.md`/`paired-cases.md`/`answers.md`/`blind-prompts.md` |
| `tests/pcb_placement_benchmark/` | 测试 | 官方 `unittest discover -s tests` 可发现 |
| `benchmarks/pcb-placement-benchmark/` | 冻结基准 | `run_benchmark.py`/`expected.json`/`results.json`/`README.md` |
| `docs/pcb-placement-training/` | 任务文档 | 本契约、验收矩阵、交接 |

## 2. 案例 schema `easycirq.pcb-placement-case/v1`

一个案例 = 一块虚拟小板 + 一份**待判的候选布局** + 显式检查项 + 期望判定。全部长度单位 `mm`，角度 `deg`（逆时针为正，`mod 360`）。

```jsonc
{
  "schema": "easycirq.pcb-placement-case/v1",
  "id": "P1-MCU-MIN",
  "title": "MCU 最小系统",
  "domain": "mcu",                       // mcu|power|analog|comm|battery|motor|wireless|multi
  "pair_with": null,                     // 成对案例：填另一 case id；否则 null
  "problem": "一句话：这份候选布局错在哪",
  "target": "一句话：可接受布局必须做到什么",
  "inspection": "人工/真实工程还要看什么（不得写成已检查）",
  "evidence_level": "synthetic",         // synthetic | derived（derived 必须给 provenance.source_sha256）
  "provenance": {"kind": "synthetic", "source": "authored for offline training", "source_sha256": null, "note": "坐标与器件为教学构造，不代表任何真实板"},
  "units": {"length": "mm"},
  "board": {
    "width_mm": 40.0,
    "height_mm": 30.0,
    "outline_mm": [[0,0],[40,0],[40,30],[0,30]],   // 可选；缺省按矩形 width×height
    "keepouts": [                                   // 可选；硬约束
      {"id": "ko-antenna", "rect_mm": [30, 0, 40, 10], "kind": "antenna_clearance", "reason": "模组天线净空"}
    ],
    "connectors": [                                 // 可选；声明就必须检查朝向/贴边
      {"ref": "J1", "edge": "left", "insert_dir": "left"}
    ]
  },
  "components": [
    {
      "ref": "U1", "kind": "mcu", "package": "LQFP-48",
      "size_mm": {"w": 7.0, "h": 7.0},              // 器件本体（不含引脚外伸）
      "height_mm": 1.6,                              // 可选；仅记录，不参与 v1 判分
      "fixed": false,
      "fixed_xy_mm": null,                           // fixed:true 时必填 [x,y]
      "allowed_rotations": [0, 90, 180, 270],
      "pins": [{"name": "VDD", "x_mm": -1.5, "y_mm": 2.25}]   // 相对器件中心的焊盘坐标，未旋转
    }
  ],
  "nets": [
    {"name": "3V3", "class": "power", "pins": [["U1","VDD"], ["C1","1"]]}   // class: power|signal|analog|rf|ground
  ],
  "placement": {"U1": {"x_mm": 12.0, "y_mm": 15.0, "rot_deg": 0}},          // 待判布局；中心坐标系
  "checks": [                                     // 软检查（显式、可引用 PL 条目）
    {"id": "ck-decoup", "code": "max_distance", "refs": ["C1","U1"],
     "pins": [["C1","1"], ["U1","VDD"]], "max_mm": 4.0,
     "basis": "PL16/PL17", "reasoning": "去耦按焊盘回路算，不按器件中心"},
    {"id": "ck-loop", "code": "loop_span", "refs": ["C1","U1","L1"], "pins": [["C1","1"],["U1","SW"],["L1","1"]],
     "max_mm": 12.0, "basis": "PL09/PL10", "reasoning": "Buck 高频脉动回路面积"},
    {"id": "ck-xtal", "code": "max_distance", "refs": ["Y1","U1"], "pins": [["Y1","1"],["U1","XIN"]],
     "max_mm": 6.0, "basis": "PL19", "reasoning": "晶体靠近时钟脚"}
  ],
  "rubric": {
    "connector_edge_tol_mm": 2.0,     // 连接器外沿与声明边的最大间距
    "overlap_tol_mm2": 0.0,           // 同面本体相交面积容差
    "hpwl_max_mm": 180.0,             // 全局 HPWL 代理上限
    "congestion_max": 4               // 2 mm 网格上同一 cell 被多少网络的 bbox 覆盖的上限
  },
  "expected": {
    "verdict": "blocking",            // blocking | review | acceptable
    "codes": ["keepout_violation", "distance_far"],       // 必须全部复现
    "soft_fail": ["ck-decoup"]        // 必须失败的软检查 id
  },
  "reference": {
    "module_order": ["power", "mcu", "io"],
    "key_placements": [{"ref": "C1", "rule": "U1 VDD 焊盘 2 mm 内，回路到 GND 焊盘不绕行", "basis": "PL16"}],
    "acceptable_alternatives": ["C1 可放背面正对 VDD/GND 焊盘，但必须同版图可连"],
    "rationale": ["..."],
    "not_checked": ["实际 DRC", "布线", "阻抗", "热"]
  },
  "limits": ["离线几何/网表代理；不是 DRC，不是可布通证明"]
}
```

**硬性数据规则**

1. `id` 唯一且大写简短；`schema` 固定字符串；未知字段一律拒绝（`invalid_case`）。
2. `placement` 必须覆盖所有 `fixed:false` 器件；`fixed:true` 器件可不出现在 `placement`（用 `fixed_xy_mm`）。
3. `nets[].pins` 只能引用存在的 `ref` 与 `pin.name`；空网络、单脚网络允许但不计 HPWL。
4. `checks[].pins` 同理；`code` 仅允许 `max_distance` / `loop_span`。
5. 数值必须是有限数字（拒绝 NaN/Inf/字符串数字/bool）；长度 > 0。
6. `evidence_level:"derived"` 必须给 `provenance.source_sha256`，否则 `invalid_case`。
7. 案例文件必须是 UTF-8、无重复 JSON 键（判分器用 `object_pairs_hook` 拒绝重复键）。

## 3. 判分语义（确定性）

### 3.1 几何

- **器件包围盒**：以 `(x_mm, y_mm)` 为中心，尺寸 `size_mm`；`rot_deg` 为 90/270 时宽高互换。器件**不**做任意角度旋转（`allowed_rotations` 只允许 0/90/180/270）。
- **坐标原点**：板框左下角 `(0,0)`，x 向右、y 向上。
- **引脚坐标**：未旋转的 `(x_mm,y_mm)` 相对器件中心；按 `rot_deg` 逆时针旋转后平移到器件中心，得到绝对焊盘坐标。
- **板框**：给了 `outline_mm` 用多边形（凸/凹均可，射线法），否则用 `[0,0,w,h]` 矩形。

### 3.2 硬检查（任一命中 → `blocking`）

| code | 判定 | 说明 |
|---|---|---|
| `missing_placement` | 非固定件缺少 `placement` 项 | 数据/布局不完整 |
| `out_of_board` | 器件包围盒超出板框（容差 0） | 越界 |
| `body_overlap` | 两个器件包围盒相交面积 > `overlap_tol_mm2` | 同面本体干涉（v1 只判同面） |
| `keepout_violation` | 器件包围盒与任一 `board.keepouts[].rect_mm` 相交面积 > 0 | 净空/禁布 |
| `rotation_not_allowed` | `rot_deg` 不在 `allowed_rotations` | |
| `fixed_moved` | `fixed:true` 且 `placement` 给了与 `fixed_xy_mm` 不一致的坐标 | |
| `connector_off_edge` | 声明了 `board.connectors`，但该器件包围盒到声明边的距离 > `connector_edge_tol_mm` | 朝向/可插拔代理 |

**只报 code 与对象**，不做因果推断；同一缺陷只报一条（按 `code` + 对象去重）。

### 3.3 软检查（不阻断，但降级为 `review`）

| code | 来源 | 公式 |
|---|---|---|
| `distance_far` | `checks[].code=max_distance` | 所列焊盘两两最大距离 > `max_mm`（去耦/晶振/模拟入口等都用它，`basis` 说明为什么） |
| `loop_large` | `checks[].code=loop_span` | 所列焊盘两两最大距离（回路跨度代理）> `max_mm` |
| `hpwl_high` | 全局 | `Σ_net (max_x-min_x + max_y-min_y)` > `rubric.hpwl_max_mm`（按 `class` 分项只记录，不进阈值） |
| `congestion_hotspot` | 全局 | 2 mm 网格：每个网络按其焊盘 bbox 覆盖的 cell 各 +1；`max cell 计数` > `rubric.congestion_max` |

约定（实现必须一致）：

- `soft` 数组**只放 `case.checks` 的逐项结果**，每项字段 `check_id/code/value_mm/max_mm/ok/basis`；全局代理（HPWL/congestion）只出现在 `metrics`，超限时以 `hpwl_high`/`congestion_hotspot` 进 `codes`，**不**进 `soft`。
- `expected.soft_fail` 只比较 `case.checks` 的 id（如 `ck-decoup`），不含任何 `global:*` 项。
- `expected.codes` = 硬检查 code ∪ 软检查具体 code（`distance_far`/`loop_large`/`hpwl_high`/`congestion_hotspot`）。v1 **不使用任何笼统兜底 code**；遇到未知 `checks[].code` 时按 `invalid_case`（exit 3）处理，不产出软检查 code。

### 3.4 verdict

```
任一硬检查命中            → blocking
无硬检查命中，任一软检查失败 → review
其余                      → acceptable
```

**禁止**把 `review`/`blocking` 四舍五入成 `acceptable`；缺数据不得补默认值来凑 `acceptable`。

### 3.5 每个案例必须复现的期望

`expected.verdict`、`expected.codes`（集合全等）、`expected.soft_fail`（集合全等）。`--all` 模式只有全部复现才 exit 0。

## 4. 判分器 CLI 契约

```bash
python scripts/pcb_placement_benchmark.py --list
python scripts/pcb_placement_benchmark.py --case P1-MCU-MIN [--json] [--out card.json]
python scripts/pcb_placement_benchmark.py --all [--json] [--out results.json]
```

- 默认路径：脚本从自身位置解析 `../assets/pcb-placement-benchmarks/benchmarks.json`；`--cases` 可覆盖。
- `--case`：判一个案例，输出 scorecard；退出码见下。
- `--all`：判全部案例并与 `expected` 对账；输出汇总表（人读）或 JSON；全部匹配 exit 0，否则 exit 1。
- `--json`：stdout **仅一个 JSON**；人读信息进 stderr。
- `--out`：原子写（临时文件 + `os.replace`），`--out` 不得等于输入。
- 只读、无网络、无 EDA、无随机、无时间戳（或时间戳来自输入）；同一输入两次运行字节一致。
- Python 3.10 语法；纯标准库。

**退出码**

| code | 含义 |
|---|---|
| 0 | `--case`：acceptable；`--all`：全部与 expected 匹配 |
| 1 | `--case`：review；`--all`：存在不匹配 |
| 2 | `--case`：blocking |
| 3 | 案例数据非法（schema/数值/引用） |
| 4 | 用法/IO 错误（文件不存在、`--out` 等于输入等） |

**输出 scorecard `easycirq.pcb-placement-benchmark.scorecard/v1`**

```jsonc
{
  "schema": "easycirq.pcb-placement-benchmark.scorecard/v1",
  "case_id": "P1-MCU-MIN",
  "verdict": "blocking",
  "hard": [{"code": "keepout_violation", "refs": ["U2"], "detail": "bbox [31.0,1.0,39.0,9.0] intersects ko-antenna"}],
  "soft": [{"check_id": "ck-decoup", "code": "distance_far", "value_mm": 9.4, "max_mm": 4.0, "ok": false, "basis": "PL16/PL17"}],
  "metrics": {"hpwl_mm": 96.2, "hpwl_by_class": {"power": 40.1}, "congestion_max": 3},
  "expected_match": {"verdict": true, "codes": false, "soft_fail": true, "mismatches": ["missing code: distance_far"]},
  "limits": ["offline geometry/net proxy", "not DRC", "not routability", "not impedance/thermal"],
  "placement_applied": false,
  "routing_verified": false,
  "drc": "NOT RUN",
  "eda_calls": 0,
  "provenance": {"kind": "synthetic", "source": "...", "source_sha256": null}
}
```

## 5. 案例清单（15 条：12 条合成 + 3 条真实板派生）

| id | 域 | 候选布局的缺陷（问题） | 期望 verdict | 期望 codes（草案，实施时可微调但必须与 expected 一致） |
|---|---|---|---|---|
| `P1-MCU-MIN` | mcu | 去耦电容放背面远端；晶体离 XIN 过远 | review | `distance_far` |
| `P1b-MCU-MIN-PAIR` | mcu | 只把 C1/C2 移到 VDD/GND 焊盘旁（其余不变） | acceptable | 无 |
| `P2-BUCK` | power | 输入电容远离 SW 回路；反馈取样点从远端取 | review | `loop_large` |
| `P2b-BUCK-PAIR` | power | 只把输入电容与 SW 电感靠拢 | acceptable | 无 |
| `P3-ANALOG` | analog | 传感器入口与基准件放在 Buck 电感/二极管旁 | review | `distance_far` |
| `P3b-ANALOG-PAIR` | analog | 只把模拟链整体挪到远离功率级一侧 | acceptable | 无 |
| `P4-COMM` | comm | 隔离器/终端布局与连接器朝向冲突：终端电阻跨隔离侧 | blocking | `connector_off_edge` |
| `P5-BATTERY` | battery | 保护 IC/检流电阻远离电池端子，热敏贴在充电 IC 上 | review | `distance_far` |
| `P6-MOTOR` | motor | 栅极驱动回路跨越大电流地；分流器取样从远端绕回 | review | `loop_large` |
| `P7-WIRELESS` | wireless | 模组压在天线净空里；净空区被电容/固定件占用 | blocking | `keepout_violation` |
| `P8-MULTI` | multi | 连接器不在板边；固定件压器件；逃线通道被大件堵死 | blocking | `connector_off_edge`,`body_overlap` |
| `P8b-MULTI-PAIR` | multi | 只把连接器推到板边并让开固定件 | acceptable | 无 |

> 4 个成对变体各自只改一组坐标（写进 `pair_with` 与 `reference.rationale`），用于训练「只改一个条件、结论翻转」。8 主例里必须有 **≥3 个 blocking、≥4 个 review**，且至少各 1 个 `keepout_violation`、`body_overlap`、`connector_off_edge`、`loop_large`、`distance_far`。
>
> 固定件（`fixed:true`）没有独立的旋转字段：判分时其 `rot_deg` 视为 `0`，位置以 `fixed_xy_mm` 为准；这是 schema 缺省而不是为凑 `acceptable` 补数据。

### 5.1 真实板派生案例（`evidence_level:"derived"`）

| id | 域 | 派生源 | 期望 verdict | 期望 codes | 说明 |
|---|---|---|---|---|---|
| `D1-MCU-LDO-DECAP` | mcu | `easycirq/cases/mcu-i2c-s3-2026-10-26/evidence/pcb-dump-final.json` | review | `distance_far` | 保留 8/23 器件；3 条去耦焊盘距离 316/213/128 mil > 100 mil 规则 |
| `D2-PHOTO-LED-SENSE` | analog | `easycirq/cases/photo-led-pcb-2026-10-26/evidence/pcb-dump-final.json` | acceptable | 无 | 19/19 器件；5 条 tracked near-pin 全部合格，用于训练「真实板基线 ≠ 可签核」 |
| `D3-DUAL-BTN-D4-MOVE` | multi | `easycirq/cases/dual-button-led-night-20261027/negative-direct-move/board-baseline.json` | blocking | `body_overlap` | D4 移动后与 R3 重叠 0.484 mm² |

派生规则（实现见 `benchmarks/pcb-placement-benchmark/derive_cases.py`，说明见 `docs/pcb-placement-training/derived-cases.md`）：

1. 只用 git 跟踪的证据文件；`provenance.source_sha256` 由脚本对源文件字节计算，不手填。
2. 单位与坐标：mil → mm（× 0.0254，精确英寸）；dump 的 x/y 是 footprint 原点而非中心 → 中心取 bbox 中心、`size_mm` 取 bbox 反旋尺寸、引脚偏移 = `R(-rot)·(pad_abs − 中心)`；脚本断言 bbox 复现 ≤1e-6 mm、焊盘复现 ≤1e-14 mm。
3. 只做坐标/单位换算与对象筛选；缺 pad/net 的器件、旋转非 0/90/180/270 的器件一律丢弃并记入 `unknowns`/`limits`，不猜。
4. 阈值必须取自 tracked 证据（如 decap ≤100 mil 规则、`constraints.json` 的 `near_pin.max_mil`）或契约默认容差；禁止为凑 verdict 调阈值。
5. 全局代理（HPWL/congestion）阈值只作**本布局基线回归界**，不参与这 3 条案例的 verdict，并写入 `limits`。

## 6. 证据与边界

- `synthetic`：教学构造，坐标/器件不代表真实板；**不得**写成真实工程验证。
- `derived`：从仓库冻结回读派生，必须记录源文件与 SHA-256；派生时只做坐标/单位换算，不改电气事实。
- 任何输出都固定 `drc:"NOT RUN"`、`routing_verified:false`、`eda_calls:0`。
- 训练结论只覆盖「本案例的预布局判断」，不外推到「这块板能打样/能布通」。

## 7. 必须主动设计的「假通过」反例

1. 缺尺寸/缺 placement 时补默认值算出一个 acceptable。
2. 去耦距离用器件中心距离而不是焊盘距离。
3. 连接器在板内但没贴边，被判 acceptable。
4. 天线净空只查器件中心不查包围盒相交。
5. HPWL 低就判 acceptable（必须另有硬检查与显式软检查）。
6. 只改一个坐标的成对案例结论不翻转（说明该条件不是主导项，要重设案例）。
7. `--all` 不看 expected，只要脚本不崩就 exit 0。
8. 把 `review` 当 `acceptable` 汇报。

## 8. 验收标准（本任务）

- [ ] `benchmarks.json` 15 条案例（12 synthetic + 3 derived），全部通过 schema 校验，`--all` exit 0（15/15 与 expected 匹配）。
- [ ] `python -m unittest discover -s tests` 全绿，新增 `tests/pcb_placement_benchmark/` 测试 ≥ 25 条并被官方 discovery 发现。
- [ ] `python easycirq/scripts/skill_selftest.py` 全部 PASS、0 FAIL（新增文件已接入必需清单）。
- [ ] `python benchmarks/pcb-placement-benchmark/run_benchmark.py` exit 0（15/15），`simulated:true`、`real_eda:"NOT RUN"`、`eda_calls:0`。
- [ ] 文档：`references/pcb-placement-benchmarks.md`（15 案例）+ 习题集（20 题 + 8 对 + 答案 + blind prompts）齐全，相对链接全部可解析。
- [ ] 盲测轮：至少 1 轮 2–3 名隔离 Agent 试答 + 独立评审，响应/评估/修订记录进 `docs/evidence/pcb-placement-blind-<date>/`，限制（样本数/单评审/约束式隔离）写明。
- [ ] SKILL.md 至少 2 处接线（PCB 训练入口 + 深潜训练入口），gate 文档未被污染。
- [ ] 清洁 checkout 可复现（`git archive` 或新 worktree 复跑）。
- [ ] 未改禁止路径；不合并 PR。

## 9. 分工与写作用域（互不重叠）

| 角色 | 写作用域 |
|---|---|
| Lead | `docs/pcb-placement-training/`、`docs/evidence/pcb-placement-blind-<date>/`、`SKILL.md`、`easycirq/scripts/skill_selftest.py`、`easycirq/references/engineering-deepdives/README.md`、`benchmarks/pcb-placement-benchmark/`、`easycirq/references/offline-regression.md`（如需接线） |
| 案例（A） | `easycirq/assets/pcb-placement-benchmarks/` |
| 判分器（B） | `easycirq/scripts/pcb_placement_benchmark.py`、`tests/pcb_placement_benchmark/` |
| 文档/习题（C） | `easycirq/references/pcb-placement-benchmarks.md`、`easycirq/references/engineering-deepdives/exercises-pcb/` |
| 派生案例（D，第二轮） | `easycirq/assets/pcb-placement-benchmarks/`（追加）、`benchmarks/pcb-placement-benchmark/derive_cases.py`、`docs/pcb-placement-training/derived-cases.md` |
| 文档/题面修订（E，第二轮） | `easycirq/references/pcb-placement-benchmarks.md`、`easycirq/references/engineering-deepdives/exercises-pcb/` |

改动越界或需要改契约时，先在本文件登记再动。
