# 第六轮实现契约（内部）

> 目的：让 `design-gates.md`、`gate_check.py`、`SKILL.md`、回归案例和并行文档使用同一套名字、状态与字段。
> 本文件是施工契约，不面向用户；最终入口仍是 `easycirq/SKILL.md`。

## 1. 门禁与状态

| 键 | 显示名 | 进入下一阶段的条件 |
|---|---|---|
| `G0_requirements` | G0 需求 | 需求边界已回答或显式默认 |
| `G1_function_freeze` | G1 功能冻结 | 必需/可选件冻结；冻结后增删有变更影响 |
| `G2_schematic` | G2 原理图 | DRC 0、电气检查 0、网表/图签/看图/单引脚网有证据 |
| `G3_layout` | G3 布局 | 目标板框、lint 达标、安装孔/连接器逃逸、布局冻结 |
| `G4_power_ground` | G4 电源地 | 层数与电源/地策略先声明、GND 铺铜、过孔审计 |
| `G5_routing` | G5 布线 | PCB DRC 0、关键网证明、保存重载、丝印、停止规则 |
| `G6_manufacturing` | G6 制造 | Gerber/钻孔/坐标/BOM、工艺档案、库存/SMT、恢复演练、测试计划 |

状态词只有四个：

- `PASS`：所有必需检查通过。
- `PASS_WITH_WAIVER`：没有未处理的失败，但至少有一个失败/警告被带理由的豁免覆盖。
- `BLOCKED`：存在未豁免的失败，或缺少可判定证据。
- `UNSUPPORTED`：必需检查在当前工具链没有可用检查路径，且没有可接受的人工证据；不能当 PASS。

判定优先级：`BLOCKED` > `UNSUPPORTED` > `PASS_WITH_WAIVER` > `PASS`。
`--strict-advisory` 可把 advisory 警告升级为失败；默认警告只记录。

## 2. 豁免

豁免不是“跳过”，必须落盘：

```json
{
  "schema": "design-waivers/v1",
  "waivers": [
    {
      "gate": "G2",
      "check": "style_warnings",
      "reason": "为什么可以接受；影响了什么；何时复验",
      "scope": "10 条风格/结构警告",
      "approved_by": "项目负责人/交接记录",
      "date": "2026-10-24",
      "evidence": ["sch-check-final2.json"]
    }
  ]
}
```

规则：

- `reason` 为空、只有“忽略/暂时”之类无信息文本 → 无效豁免，不得改变状态。
- 每个门禁有不可豁免检查（见 `design-gates.md`）：电气的 DRC/网表、PCB DRC、关键网证明、保存重载、Gerber/BOM/恢复演练。
- `--waiver G2:reason` 只覆盖该门禁的可豁免检查；`--waiver G2.style_warnings:reason` 只覆盖单项。
- 豁免被使用 → 该门禁至少 `PASS_WITH_WAIVER`；未被使用的豁免在报告里标 `unused`。

## 3. `design-state.json`（schema `design-state/v1`）

项目工作区唯一状态载体。字段可以按项目裁剪，但门禁读取的键名固定：

```json
{
  "schema": "design-state/v1",
  "project": {"name": "temp-alarm", "board_revision": "rev0", "stage": "G3", "updated": "2026-10-24"},
  "requirements": {
    "delivery_level": {"status": "confirmed", "value": "原理图+PCB+DRC0"},
    "size_limit": {"status": "confirmed", "value": {"width_mm": 90.9, "height_mm": 55.3, "source": "user"}},
    "enclosure_mounting": {"status": "not_applicable", "reason": "裸板首板，无外壳"},
    "assembly": {"status": "confirmed", "value": "SMT + 直插件手焊"},
    "quantity_budget": {"status": "confirmed", "value": {"qty": 5, "budget_cny": 300}},
    "usb_role": {"status": "confirmed", "value": "power-only"},
    "test_points": {"status": "confirmed", "value": ["+5V", "GND", "NODE", "VREF", "GATE"]},
    "display": {"status": "not_applicable", "reason": "无显示"},
    "firmware": {"status": "not_applicable", "reason": "纯模拟，无 MCU"},
    "threshold_interaction": {"status": "confirmed", "value": "RV1 多圈电位器"},
    "alarm_behavior": {"status": "confirmed", "value": "超阈值亮灯+蜂鸣；回差约1.7°C；自动解除"},
    "environment_accuracy": {"status": "confirmed", "value": "室内 0–40°C，±2°C 目标"}
  },
  "function_freeze": {
    "status": "frozen",
    "frozen_at": "2026-10-24",
    "required": [{"designator": "U1", "role": "比较器"}],
    "optional": [],
    "removed_after_freeze": [
      {"designator": "J2", "reason": "调试排针非必需", "change_impact": "docs/change-impact-j2.md"}
    ]
  },
  "schematic": {
    "netlist_audit": {"status": "pass", "evidence": "16 网逐针核对"},
    "titleblock": {"status": "pass", "name": "室内温度报警板", "version": "rev0"},
    "png_review": {"status": "pass", "evidence": "evidence/schematic-final.png"},
    "single_pin_nets": {"status": "pass", "count": 0},
    "net_naming": {"status": "pass", "style": "functional"}
  },
  "layout": {
    "board_outline": {"status": "confirmed", "width_mm": 90.9, "height_mm": 55.3},
    "mounting_holes": {"status": "confirmed", "count": 4, "diameter_mm": 3.2},
    "connector_escape": {"status": "pass", "max_distance_mm": 4.2, "slot_clear": true},
    "auto_place_used": true,
    "auto_place_metrics": {"before": {"score": 41, "crossings": 21}, "after": {"score": 58, "crossings": 14}, "decision": "kept"},
    "frozen": true,
    "frozen_at": "2026-10-24"
  },
  "stackup": {
    "layers": 2,
    "decision": {"choice": "2-layer", "rationale": "成本优先，信号 <20MHz"},
    "power_ground_strategy": {"mode": "pour_priority", "gnd_layers": ["top", "bottom"], "power_nets": ["+5V"]},
    "drc_rules_recorded": true,
    "rules_verified_at": "2026-10-24"
  },
  "routing": {
    "plan": {"status": "pass", "file": "assets/routing-plan-filled.md"},
    "key_nets": ["+5V", "GND", "NODE", "VREF", "OUT", "GATE", "BUZ_D"],
    "key_net_proofs": {"+5V": {"found": true, "evidence": "evidence/net-path-5v.json"}},
    "save_reload": {"status": "pass", "evidence": "evidence/doc-reload.json"},
    "silk_align": {"status": "pass", "evidence": "evidence/silk-align.json"},
    "drc_rounds": [{"round": 1, "total": 18}, {"round": 2, "total": 14}, {"round": 3, "total": 12}],
    "stop_rule_triggered": false
  },
  "manufacturing": {
    "artifacts": [
      {"role": "gerber", "path": "manufacturing/gerber.zip"},
      {"role": "drill", "path": "manufacturing/drill.zip"},
      {"role": "cpl", "path": "manufacturing/cpl.csv"},
      {"role": "bom", "path": "BOM.csv"}
    ],
    "profile": {"status": "pass", "file": "docs/manufacturing-profile.md"},
    "project_export": {"path": "project.epro2", "sha256": "…", "restore_verified": true},
    "test_plan": {"path": "docs/test-plan.md", "status": "pass"}
  },
  "sourcing": {
    "stock_checked_at": "2026-10-24",
    "smt_checked_at": "2026-10-24",
    "smt_required": true
  },
  "waivers": [],
  "assumptions": [{"id": "A1", "text": "…", "impact": "…"}],
  "risks": [{"id": "R1", "text": "…", "status": "open"}],
  "open_items": [{"id": "O1", "text": "…", "blocking": false}]
}
```

字段值统一支持两种写法：

- 标量/数组/对象：视为已确认的值。
- `{"status": "...", ...}`：`status` ∈ `confirmed | assumed | not_applicable | pending | blocked`；`assumed` 必须带 `assumption`/`source`，`not_applicable` 必须带 `reason`，`pending/blocked` 一律阻塞。

## 4. 证据角色与自动发现

`gate_check.py` 在 `--evidence-dir` 下按角色找最新文件；`--file role=path` 可显式覆盖。

| role | 默认匹配 | 期望内容 |
|---|---|---|
| `sch_drc` | `sch-drc*.json`, `sch_drc*.json` | JSON 或 human 文本；fatal/error 计数 |
| `sch_check` | `sch-check*.json`, `sch_check*.json` | JSON findings 或 human 计数 |
| `sch_nets` | `sch-nets*.json`, `sch_nets*.json` | 单引脚网审计 |
| `schematic_png` | `schematic*.png`, `sch*.png` | 原理图导出图 |
| `pcb_layout_lint` | `pcb-layout-lint*`, `*layout*lint*` | 必须是 PCB 版（文本含 `PCB layout-lint:` 或 JSON 含 `crossings`） |
| `pcb_drc` | `pcb-drc*.json`, `pcb_drc*.json` | `passed/total/counts/violations` 或 flat JSON |
| `pcb_check` | `pcb-check*.json` | DFM findings |
| `pcb_board` | `pcb-board*.json`（排除 `.capture.json`） | components/outline/copper/rules |
| `pcb_pours` | `pcb-pour*.json`, `pcb_pours*.json` | `result.pours` |
| `pcb_vias` | `pcb-vias*.json`, `pcb_via*.json` | `result.vias` + `staleRisk` |
| `pcb_mount_holes` | `*mount-hole*`, `*mount_hole*` | `pcb mount-holes` 回执 |
| `silk_align` | `*silk-align*`, `*silk_align*` | `pcb silk-align` 回执 |
| `net_path` | `net-path*.json`, `net_path*.json` | 每网一条证明 |
| `reopen_check` | `*reopen*.json`, `*reload*readback*` | `doc reload` 后回读 |
| `project_export` | `project-export*.json`, `project_export*.json` | `restoreVerified` |
| `bom` | `BOM*.csv`, `bom*.csv` | 原始 BOM CSV |
| `gerber` | `*.gbr`, `*.g??`, `gerber*` | 制造层 |
| `drill` | `*.drl`, `*drill*` | 钻孔 |
| `cpl` | `*cpl*.csv`, `*pos*.csv`, `*pick*place*` | 坐标 |

报告里的每个证据带 `path / sha256 / mtime / format / candidates / selected_because`。
`format` ∈ `json | text | csv | file | invalid_json`。
JSON 解析失败但内容像 JSON → `invalid_json`，对应检查 `BLOCKED`，不崩溃。
`staleRisk` 非空的回执 → 警告且不作为权威证据。

## 5. `gate_check.py` CLI

```text
python scripts/gate_check.py --project NAME --evidence-dir DIR
  [--project-dir DIR] [--design-state FILE] [--brief FILE]
  [--waiver GATE[:CHECK]:REASON ...] [--waiver-file FILE]
  [--file ROLE=PATH ...]
  [--min-layout-score 60] [--max-crossings 8]
  [--strict-advisory] [--json] [--out FILE] [--quiet]
```

退出码：

- `0`：没有任何 `BLOCKED`/`UNSUPPORTED`。
- `1`：至少一个 `BLOCKED`/`UNSUPPORTED`。
- `2`：参数、IO 或 design-state schema 错误。

默认输出 human 摘要；`--json` 输出 `design-gate-report/v1`；`--out` 同时落盘。
`next_commands` 只写当前 CLI 真实存在的命令，用 shell 重定向落盘，不编造 `--out` 参数。

## 6. 回归案例目标

`cases/temp-alarm-2026-10-24/` 的预期（dry-run，只读证据）：

| 门禁 | 预期 |
|---|---|
| G0 | `BLOCKED` |
| G1 | `BLOCKED` |
| G2 | `PASS_WITH_WAIVER` |
| G3 | `BLOCKED` |
| G4 | `BLOCKED` |
| G5 | `BLOCKED` |
| G6 | `BLOCKED` |

如果全 PASS，说明门禁没覆盖住这次错误；如果 G2 不是 `PASS_WITH_WAIVER`，说明风格警告/豁免链路没接上。

## 7. 本轮文件所有权（并行时不重叠）

主 Agent 独占：

- `easycirq/SKILL.md`
- `easycirq/references/design-gates.md`
- `easycirq/scripts/gate_check.py`
- `tests/test_gate_check.py`
- `easycirq/assets/design-state.example.json`
- `easycirq/cases/temp-alarm-2026-10-24/**`
- `docs/round6-contract.md`、`docs/round6-change-plan.md`、`docs/task-ledger-round6.md`

并行 Agent 独占：

- A：`references/pcb-routing-strategy.md`、`assets/routing-plan.md`、`assets/docs/thermal-sensor.md`、`references/pcb.md`
- B：`references/tool-gotchas.md`、`references/eda-execution.md`、`references/schematic.md`
- C：`assets/design-brief.md`、`assets/docs/mechanical.md`、`assets/docs/silk-assembly.md`
- D：`references/agent-collaboration.md`、`references/part-selection.md`、`references/lcsc-sourcing.md`、`assets/design-calc.md`
- E：`assets/docs/manufacturing-package.md`、`assets/docs/verification.md`、`assets/parts.example.json`、`scripts/bom_check.py`、`tests/test_bom_check.py`
- F：`assets/pinmap.example.json`、`scripts/pin_plan_check.py`、`tests/test_pinmap.py`
- G：`scripts/skill_selftest.py`、`easycirq/CHANGELOG.md`、`easycirq/.version`、`references/beginner-journey.md`

所有 Agent：不跑 EDA、不改 `SKILL.md`/`design-gates.md`/`gate_check.py`/`cases`、不提交、不覆盖其他 Agent 的文件。

## 8. 已核对的真实命令（easyeda-agent v1.14.0）

`--help` 原样落盘：`docs/evidence/round6-2026-10-24/cli-help.txt`。

- 原理图：`easyeda sch drc [--json] [--strict]`、`sch check [--json] [--strict] [--page]`、`sch connectivity [--all-pages]`、`sch nets [--all] [--json] [--strict]`、`sch export-image --format png|svg|pdf`、`sch save`。
- PCB：`easyeda pcb drc [--json] [--strict] [--timeout]`、`pcb layout-lint [--json] [--min-score] [--max-crossings]`（`--gate` 是 deprecated compatibility；阈值不自动阻断）、`pcb list --include-pads`、`pcb net-path --from A.1 --to B.2 [--net N] [--json]`、`pcb check [--json] [--strict]`、`pcb drc-rules`、`pcb stackup show|set`、`pcb mount-holes [--dry-run]`、`pcb silk-align`、`pcb save`、`pcb snapshot`、`pcb outline-fit [--dry-run]`、`pcb power-pour [--dry-run]`、`pcb route-short [--dry-run]`、`pcb import-changes --schematic <uuid>`。
- 文档：`easyeda doc reload [--json]`、`doc switch <name|uuid> --project <name>`。
- BOM/工程：`easyeda bom export --type csv|xlsx [--enrich=false]`、`bom enrich <bom.tsv>`、`project export --out <file> --project-uuid <uuid>`。

不要写不存在的 `--out`、`--save`、`--force` 组合；输出落盘用 `>` 重定向。
