# R1–R50 覆盖表

> 任务书第 3 节每条实战问题 → 门禁/规则 → 落地文件。没有“无对应”。
> 门禁键与 `gate_check.py`、`design-gates.md`、`SKILL.md` 一致；`PASS_WITH_WAIVER` 不是 `PASS`。

| R | 问题 | 对应门禁/规则 | 落地文件/证据 |
|---|---|---|---|
| R1 | 验收合同（交付到哪一级） | G0 `req_delivery_level` | `design-gates.md` §5、`assets/design-brief.md` |
| R2 | 环境与精度（范围/精度/回差/断电恢复） | G0 `req_environment_accuracy` | `design-brief.md`、`design-gates.md` §5 |
| R3 | 报警行为（自锁/静音/解除/LED 节奏） | G0 `req_alarm_behavior` | `design-brief.md`、`beginner-journey.md` |
| R4 | 阈值交互（电位器/按键/显示/标定） | G0 `req_threshold_interaction` | `design-brief.md`、`beginner-journey.md` |
| R5 | 尺寸与安装（板框/外壳/孔/插头空间） | G0 `req_size_limit`、`req_enclosure_mounting`；G3 `board_outline`、`mounting_holes` | `design-brief.md`、`assets/docs/mechanical.md` |
| R6 | 装配与预算（自焊/SMT/数量/层数成本） | G0 `req_assembly`、`req_quantity_budget` | `design-brief.md`、`part-selection.md`、`lcsc-sourcing.md` |
| R7 | 假设/风险/未测项显式记录 | G0 `assumptions`、`risks`、`open_items` | `design-state.example.json`、`design-brief.md` |
| R8 | 层数决策（2 vs 4 层） | G4 `stackup_decision` | `pcb-routing-strategy.md` §1、`design-gates.md` §9 |
| R9 | 封装与手焊难度 | 选型规则：先定手焊/SMT 再定封装；手焊默认 0603 | `part-selection.md`、`design-brief.md` |
| R10 | footprint/land pattern 与厂家 drawing | G2 建库/逐脚核对；G3 布局核对 | `schematic.md` §建库、`pcb.md` §机械与同步 |
| R11 | 关键参数逐项核对（蜂鸣器/ MOS / NTC / 电位器 / LED） | 设计计算与选型记录 | `assets/design-calc.md`、`part-selection.md` |
| R12 | 备选料/库存/MOQ/SMT 分类 | G6 `sourcing_check`；BOM 结构检查 | `lcsc-sourcing.md`、`scripts/bom_check.py`、`design-gates.md` §11 |
| R13 | 极性/方向/装配图 | G5 `silk_over_pad`；G2 polarity outlier | `assets/docs/silk-assembly.md`、`tool-gotchas.md` |
| R14 | 连接器选型（只供电 vs 数据；6P vs 16P） | G0 `req_usb_role`；G3 `connector_escape` | `design-brief.md`、`pcb-routing-strategy.md` §6 |
| R15 | 接口无源件靠连接器（CC/TVS/ESD ≤5 mm） | G3 `connector_escape`（`max_distance_mm`） | `pcb-routing-strategy.md` §6、`pcb.md` |
| R16 | TVS/ESD 逃逸通道（避开 slot/不抢 CC/VBUS） | G3 `connector_escape`（`slot_clear`） | `pcb-routing-strategy.md` §6、`tool-gotchas.md` |
| R17 | 机械可达性（声孔/螺丝刀/LED/USB 插拔） | G3 `mounting_holes`、`connector_escape` | `assets/docs/mechanical.md`、`thermal-sensor.md` |
| R18 | 功能网名（VBUS/CC1/CC2/NODE/VREF/GATE/BUZ_D） | G2 `net_naming`（advisory） | `schematic.md` §网名、`design-gates.md` §7 |
| R19 | 图面注释（NTC R25/B、阈值、回差、有源/无源、测试点电压） | G2 `png_review` | `schematic.md` §注释、`assets/design-calc.md` |
| R20 | 功能分区框 | G2 `style_warnings`（`missing-partition`） | `schematic.md`、`design-gates.md` §7、豁免示例 |
| R21 | 测试点策略（+5V/GND/NODE/VREF/GATE） | G0 `req_test_points`；G2 图面 | `design-brief.md`、`schematic.md`、`beginner-journey.md` |
| R22 | 标题栏/版本/板名 | G2 `titleblock` | `design-gates.md` §7、`schematic.md` |
| R23 | 直连 vs 网标风格；`peripheral-not-direct` 豁免 | G2 `style_warnings` + 落盘豁免 | `schematic.md` §画图风格、`waivers.json` 示例 |
| R24 | 网表/引脚/NC 审计 | G2 `netlist_audit`、`single_pin_nets`；G1 重新导入回读 | `design-gates.md` §7/§12.2、`tool-gotchas.md`（import-changes 不删件） |
| R25 | 图面视觉检查（导 PNG 实际看） | G2 `png_review` | `design-gates.md` §7、`tool-gotchas.md` |
| R26 | 目标板框先定再摆放 | G3 `board_outline`（不得用 outline-fit 反推） | `design-gates.md` §8、`pcb-routing-strategy.md` |
| R27 | 布局 lint 阈值/前后记录 | G3 `layout_lint_score`、`layout_lint_crossings`、`layout_lint_geometry` | `design-gates.md` §8、`pcb.md` |
| R28 | 自动摆放前后对比，没改善就回退 | G3 `auto_place_comparison` | `design-gates.md` §8、`pcb-routing-strategy.md` |
| R29 | 电源/地策略（一层一网或铺铜优先级；GND 双层铺铜；不布 GND 细线） | G4 `power_ground_strategy`、`gnd_pours`、`gnd_thin_traces` | `pcb-routing-strategy.md` §2/§3 |
| R30 | DRC 规则先设（clearance/线宽/过孔/net class/叠层/铜厚） | G4 `drc_rules_recorded` | `design-gates.md` §9、`pcb.md` |
| R31 | 布线计划（层/通道/过孔/顺序） | G5 `routing_plan` | `assets/routing-plan.md`、`pcb-routing-strategy.md` §4 |
| R32 | 停止规则（连续 3 轮改善 <30% 就停） | G5 `stop_rule` | `agent-collaboration.md`、`pcb-routing-strategy.md` §5 |
| R33 | 机械/安装孔/板边/插头空间 | G3 `mounting_holes`、`connector_escape` | `assets/docs/mechanical.md`、`design-gates.md` §8 |
| R34 | NTC 热设计（远离蜂鸣器/电源、开槽/细颈、气流） | G3 布局 + 热设计记录 | `assets/docs/thermal-sensor.md`、`pcb-routing-strategy.md` §7 |
| R35 | 丝印/DFM（极性/1 脚/板名/DNP） | G5 `silk_over_pad`；G6 工艺档案 | `assets/docs/silk-assembly.md`、`tool-gotchas.md`（layout-lint 只判本体） |
| R36 | 用 Skill 模板（brief/notes/manufacturing/review/beginner） | G0/G6 记录 | `assets/design-brief.md`、`manufacturing-profile.md`、`review-summary.md`、`beginner-summary.md` |
| R37 | 用 Skill 脚本（calculate/netlist/sch_layout/pin_plan/interface） | 离线检查边界 | `SKILL.md` §6、`scripts/`、`offline-tools.md` |
| R38 | 设计 diff（`sch design-diff`/`connectivity-diff`） | G2 `netlist_audit` | `design-gates.md` §12.2、`tool-gotchas.md` |
| R39 | 关键网 `net-path` 证明 | G5 `key_nets_declared`、`key_net_proofs` | `assets/routing-plan.md`、`design-gates.md` §10 |
| R40 | 证据 manifest（命令/退出码/时间/版本/hash） | `gate_check.py` 证据元数据；证据协议 | `design-gates.md` §4/§13、`agent-collaboration.md` |
| R41 | staleRisk / 保存重载后 fresh readback | G5 `save_reload`；G4 `via_audit` | `design-gates.md` §9/§10、`tool-gotchas.md`、`agent-collaboration.md` |
| R42 | 时间盒/迭代预算 | G5 `stop_rule` | `agent-collaboration.md`、`pcb-routing-strategy.md` §5 |
| R43 | 命令/版本记录（CLI/daemon/connector/EDA） | 证据协议与报告字段 | `agent-collaboration.md`、`design-gates.md` §4 |
| R44 | 视觉检查（原理图 PNG、PCB render） | G2 `png_review`；G3/G5 渲染/看图 | `tool-gotchas.md`（snapshot 前台）、`design-gates.md` §7 |
| R45 | 变更影响/回归案例 | G1 `change_impact` | `cases/temp-alarm-2026-10-24/change-log.md`、`design-gates.md` §6 |
| R46 | 门禁可执行（design-state + gate_check） | `G0`–`G6` 四结论 | `scripts/gate_check.py`、`tests/test_gate_check.py` |
| R47 | 执行器边界（design-hardware vs easyeda-agent） | SKILL §2/§6；门禁只读证据 | `SKILL.md`、`design-gates.md`、`eda-execution.md` |
| R48 | 横向检查（装配/可测试/机械/热/丝印/制造包） | G3/G6 + 5 份模板 | `assets/docs/*.md` |
| R49 | 项目状态载体（状态/决策/假设/风险/BOM/DRC 集中） | `design-state.json` | `assets/design-state.example.json`、`design-gates.md` §13.3 |
| R50 | Skill 自检（链接/命名/案例/脚本） | `skill_selftest.py` | `scripts/skill_selftest.py`、`tests/test_skill.py` |

## 覆盖说明

- `advisory` 项（如 R18 网名）默认只警告；`--strict-advisory` 可升级为失败。
- 可豁免项只限 `design-gates.md` 列出的 `waivable` 检查；电气 DRC、网表、PCB DRC、关键网、保存重载、Gerber/BOM/恢复演练不可豁免。
- R11/R34 的“逐项核对”是设计方法要求，最终由 G2/G3 的逐脚、布局和热设计记录承载；没有实际证据时仍标 `待确认`。
