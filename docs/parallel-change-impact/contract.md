# ECO 变更影响分析契约（change-impact）

本契约定义 `easycirq/scripts/change_impact/` 的输入、输出、模块边界与
退出语义。工具只做离线、只读、确定性的分析：不调用 EDA/执行器/Connector，
不写设计，不宣称“已验证/已应用”。所有结论必须可追溯到声明的对象、依赖边、
变更记录和验证目录条目；缺少数据时输出 `unknown`，不得用空结果代替。

- 工具版本：`TOOL_VERSION = 0.1.0`，`IMPLEMENTATION = change-impact`
- 输入 schema：`hds-change-impact-input/v1`
- 报告 schema：`hds-change-impact-analysis/v1`
- 计划 schema：`hds-change-impact-plan/v1`
- 对比输入：`hds-change-impact-compare-input/v1`，对比报告：`hds-change-impact-compare/v1`
- 解释报告：`hds-change-impact-explain/v1`
- 总体状态只有：`planned_with_scope`、`incomplete`、`no_change`（成功路径）与
  `input_invalid`（失败路径）。**不存在 `design_pass`/`verified`/`applied`。**

## 1. 运行方式

```text
python -m change_impact validate  INPUT.json
python -m change_impact analyze   INPUT.json [--output OUT.json] [--format json|human]
python -m change_impact plan      INPUT.json [--output OUT.json]
python -m change_impact compare   COMPARE.json [--output OUT.json]
python -m change_impact explain   INPUT.json [--object ID] [--change ID] [--format json|human]
```

`python -m` 需要 `easycirq/scripts` 在 `sys.path` 上（仓库内测试通过
`PYTHONPATH=easycirq/scripts` 调用；包内 `__main__.py` 也能从脚本目录直接
运行）。默认只读：不写任何输出文件；`--output` 时才写一份报告。

约定：

- **stdout** 只输出一份机器 JSON（`--format human` 时输出确定性 Markdown 交接
  文本，属于显式例外，供人工复核）；诊断信息走 **stderr**。
- 退出码：`0` 成功（`planned_with_scope`/`no_change`）、`2` 输入/参数无效
  （`input_invalid`）、`4` 分析不完整（预算耗尽、未解析 unknown、证据缺口导致
  计划无法完整）、`1` 内部错误。失败时 stdout 只有错误 JSON（含
  `failure_class`），**不留下或复用旧报告**；`--output` 失败时不会创建/覆盖目标
  文件（先写临时文件再原子替换，失败即清理）。
- 不接受输入中声明的绝对路径、`..` 路径或任何脚本/外部链接；工具不执行输入中
  的任何内容。
- 确定性：相同输入字节 → 相同 stdout 字节。所有列表显式排序；不产生时间戳、
  主机名或随机 ID；不读取环境/网络/EDA。`--output` 写入使用 UTF-8、`\n`、
  `sort_keys=True`、`allow_nan=False`。

## 2. 输入模型

```jsonc
{
  "schema": "hds-change-impact-input/v1",
  "project": {"name": "sensor-board", "id": "PRJ-1"},
  "baseline":  {"project": "sensor-board", "document": "main", "revision": "r1",
                "content_hash": "sha256:<64hex>",
                "source_type": "normalized_model",        // normalized_model|feedback_observation|design_engine_ir|snapshot_json|simulated_synthetic
                "snapshot_scope": ["component_instance","net","pin"],  // 本快照完整覆盖的对象类
                "missing_fields": [],                     // 缺失字段清单
                "complete": false, "notes": ""},
  "candidate": { "...同上，revision/content_hash 必须不同..." },
  "objects": [ { "id": "cmp:U1", "kind": "component_instance",
                 "attributes": {"mpn": "...", "footprint": {"uuid": "..."},
                                "placement": {"x": 10, "y": 20},
                                "pins": {"1": {"net": "net:+5V"}}},
                 "baseline_attributes": {"mpn": "OLD-MPN"},   // 仅列与 attributes 不同的基线值
                 "present": {"baseline": true, "candidate": true},
                 "display_name": "U1", "simulated": false,
                 "provenance": {"source": "..."} } ],
  "dependencies": [ { "id": "dep:1", "from": "cmp:U1", "to": "net:+5V",
                      "semantic": "power_supply", "direction": "forward",
                      "conditions": ["rail enabled"], "certainty": "declared",
                      "evidence": {"source": "schematic_snapshot"} } ],
  "changes": [ { "id": "chg:1", "change_type": "modify",   // modify|add|remove
                 "kind": "power_requirement",               // 可省略，由属性路径推导
                 "object": "net:+5V", "attribute": "voltage.nominal",
                 "before": 5.0, "after": 3.3,
                 "authorized": true,
                 "authorized_scope": {"objects": ["net:+5V"], "attributes": ["voltage.nominal"]},
                 "source": {"type": "declared", "ref": "ECO-12"},
                 "conditions": [], "note": "" } ],
  "observed_diff": [ { "object": "cmp:R1", "attribute": "value",
                       "before": 1000, "after": 2200, "source": "observed" } ],
  "constraints": [ { "id": "con:+5V:range", "kind": "voltage_range",
                      "object": "net:+5V", "attribute": "voltage",
                      "value": {"min": 4.75, "max": 5.25}, "hard": true,
                      "source": "requirement:REQ-1" } ],
  "verification_catalog": [ { "id": "chk:voltage_drop",
                              "title": "LDO 压差核算", "kind": "offline",
                              "cost": 0.5, "mandatory": true, "approval": false,
                              "module": "electrical-review",
                              "covers": [{"object": "cmp:U2", "impact": "power_integrity",
                                          "attribute": "voltage"}],
                              "requires": [], "requires_inputs": ["vin_range"] } ],
  "prior_evidence": [ { "id": "ev:1", "check": "chk:voltage_drop", "result": "pass",
                        "tool_version": "0.9.0", "revision": "r1",
                        "content_hash": "sha256:<64hex>",
                        "coverage": {"objects": ["cmp:U2"], "attributes": ["voltage"]},
                        "dependency_fingerprint": "sha256:<64hex>",
                        "conditions": [], "simulated": false,
                        "captured_at": "2026-01-01T00:00:00Z", "valid_until": null,
                        "host": {"id": "pc-1", "receipt": "..."}, "scope_complete": true } ],
  "budget": {"max_depth": 8, "max_paths": 500, "max_cost": 1000, "max_checks": null},
  "model_scope": {"declared_kinds": ["component_instance","net","pin","interface"],
                  "unknown_objects": [], "dependencies_complete": false,
                  "notes": "只有已声明依赖，未声明即未知"},
  "simulated": true,
  "analysis_time": "2026-01-02T00:00:00Z"
}
```

### 2.1 ID 与类型

对象 ID 必须是 `<类型前缀>:<稳定名>`，前缀与 `kind` 严格对应：

| kind | 前缀 | kind | 前缀 |
|---|---|---|---|
| component_instance | `cmp:` | bom_line | `bom:` |
| pin | `pin:` | firmware_contract | `fw:` |
| net | `net:` | test | `test:` |
| power_domain | `pwr:` | artifact | `art:` |
| interface | `if:` | requirement | `req:` |
| layout_region | `region:` | document | `doc:` |
| mechanical_anchor | `anchor:` | | |

依赖 ID `dep:`、变更 `chg:`、约束 `con:`、检查 `chk:`、证据 `ev:`。重复 ID、
前缀与 kind 冲突、未知对象引用一律 `input_invalid`。**同样的网名字符串不是身份**：
网络身份由 `id` 决定；重命名由 `name`/`net_name` 属性变化表示，与网络分区变化
（`members`/连接关系变化）分开报告。

### 2.2 变更类别（J1）

`kind` 可省略，由属性路径推导；显式 `kind` 与路径推导冲突时拒绝（除
`parameter`↔`power_requirement` 的显式细化）。推导表：

| 属性路径前缀/精确名 | 类别 | 说明 |
|---|---|---|
| `display.` `annotation.` `text_style.` `label_offset.` `silk_text.` `visual.` `doc_note.` | `display_only` | 仅图面文字/位置，不默认使固件/采购失效 |
| `name` `net_name` `designator` `display_name` `instance_name` | `identity_rename` | 重命名，与身份/分区变化分开；分区证据缺失即 `unknown` |
| `mpn` `manufacturer` `lcsc` `device.uuid` `instance_uuid` `part_number` | `component_identity` | 实例/器件身份；同封装不证明电气等价 |
| `footprint.` `package.` `symbol.` | `footprint` | 封装/符号 |
| `power.` `supply.` `voltage_range.` `current_requirement.` | `power_requirement` | 电源范围 |
| `value` `resistance` `capacitance` `inductance` `tolerance` `rating.` `parameters.` | `parameter` | 参数 |
| `pins.` `pin.` `pinout.` `pin_function` | `pin_mapping` | 引脚功能/映射 |
| `net` `nets` `connectivity.` `electrical.` | `connectivity` | 连接/分区 |
| `placement.` `position.` `rotation` `mirror` `layer` `layers.` `stackup.` | `mechanical_pose` | pose/层 |
| `board.outline` `outline` `hole` `holes` `mounting_hole` `board_frame` `edge.` | `board_outline` | 板框/孔位 |
| `dnp` `bom.` `assembly.` `variant.` `delivery.` `fitted` `population.` | `delivery_config` | 交付配置 |
| `firmware.` `peripheral.` `register.` `clock.` `io_contract.` | `firmware_contract` | 固件契约 |
| `test.` `limit.` `threshold.` `acceptance.` | `test_criterion` | 测试判据 |
| `requirement.` `requirement_id` `trace.` | `requirement` | 需求 |
| `document.` `title_block.` `revision` `sheet.` | `document_metadata` | 文档元数据 |
| 其它 | `unknown_attribute` | **显式未知，不得归为显示变更** |

### 2.3 依赖语义

`power_supply`、`signal_path`、`pin_mapping`、`footprint_binding`、
`mechanical_constraint`、`enclosure_constraint`、`artifact_source`、
`verification_coverage`、`requirement_ref`、`firmware_consumer`、`test_reference`、
`document_reference`。方向 `forward`/`bidirectional`；`certainty` 为
`declared|observed|inferred|unknown`。**只记录已知依赖**：没有边不是无影响，模型
覆盖范围由 `model_scope` 与快照 `snapshot_scope` 声明。

### 2.4 验证目录与证据

- 检查 `kind`：`offline`（本工具可规划、不执行）、`host`（宿主 DRC/保存重开/官方
  导图）、`manual`（人工/实物）。`mandatory` 与 `approval` 分开：前者是质量门禁，
  后者是项目定义的行政审批点。`covers` 条目按 `(object, impact)` 或
  `(impact, null)` 通用覆盖匹配；无匹配即 `coverage_gaps`，不用无关检查凑覆盖率。
- 证据必须带 `check`、`result`、`revision`、`content_hash`、`tool_version`、
  `coverage` 才能参与“可复用”判断；缺任一项 → `unknown`。`simulated: true`
  的证据永远不能作为宿主/实物检查的有效依据，也不升级为真实回执。
- 过期（`valid_until` 早于 `analysis_time`）判 `invalidated`，原因 `expired`。

## 3. 模块接口（并行实现边界）

所有模块只依赖 `__init__`、`canonical`、`errors`、`model`、`graph` 及自身。
函数入参 `model` 为 `model.Model` 实例，`graph` 为 `graph.Graph` 实例。

### `propagate.py`（J2）

```python
def propagate(model, graph, classification, *, budget=None) -> dict
```

返回：

```python
{
  "impact_paths": [  # 排序：target, impact, path_id
    {"path_id": "path:0001", "target": "cmp:U2", "target_kind": "component_instance",
     "impact": "power_integrity", "change_ids": ["chg:1"], "confidence": "certain",
     "steps": [{"from": "net:+5V", "to": "cmp:U2", "edge": "dep:1",
                "semantic": "power_supply", "conditions": []}],
     "trigger_rule": "R1_power_requirement", "stop_reason": "leaf_object",
     "conditions": [], "evidence": [{"edge_id": "dep:1", "certainty": "declared"}],
     "undetermined": false}
  ],
  "impacted_objects": [
    {"object": "cmp:U2", "kind": "component_instance",
     "impacts": ["power_integrity"], "confidence": "certain",
     "change_ids": ["chg:1"], "path_ids": ["path:0001"],
     "direct": false}
  ],
  "unknown": [{"code": "missing_edge_data", "object": "...", "reason": "...",
               "change_ids": [...]}],
  "truncated": false,
  "budget": {"max_depth": 8, "max_paths": 500, "used_paths": 3, "max_depth_used": 2,
             "frontier": []},
  "cycles": [["cmp:U1", "net:N2"]],
  "rules_applied": ["R1_power_requirement", "..."],
}
```

规则必须按变更类别与依赖语义匹配（不得全图扩散）；每类变更至少一条规则；
必须实现（详见 `propagation-rules.md`）：电源范围、实例替换、封装变化、引脚
重映射、接口 pose、重命名、仅显示属性、板框/孔位、层/叠层、交付配置、固件契约、
测试判据、参数。循环有 `cycle_detected` 终止与去重；预算到顶 `truncated=true`
并在 `budget.frontier` 留下未遍历节点（`unknown` 中说明未遍历≠无影响）。
多个源变更合并时 `change_ids` 保留完整来源集合，不覆盖解释。

### `evidence.py`（J3）

```python
def assess(model, graph, impacts, *, analysis_time=None) -> dict
```

返回：

```python
{
  "assessments": [
    {"evidence_id": "ev:1", "check": "chk:voltage_drop", "status": "invalidated",
     "reasons": [{"code": "covered_attribute_changed", "detail": "...",
                  "change_ids": ["chg:1"]}],
     "reuse": null,  # 或 {"basis": "dependency_fingerprint_match",
                          #     "computed_fingerprint": "sha256:...",
                          #     "covered_objects": [...],
                          #     "preserved_capture": {"captured_at": ..., "revision": "r1",
                          #                            "tool_version": "...", "host": {...}},
                          #     "limits": ["only covers ..."]}
     "original": {...}, "coverage": {...},
     "valid_for": ["offline"],  # 该证据可支持的检查类型；simulated 永远不含 host/manual
     "notes": []}
  ],
  "unknown": [{"code": "evidence_missing_binding", "evidence_id": "ev:2",
               "reason": "..."}],
  "counts": {"invalidated": 1, "reusable_bound": 0, "reusable_with_assessment": 0,
             "not_applicable": 0, "unknown": 0},
  "simulated_only": false,
  "notes": [...]
}
```

状态：`invalidated`、`reusable_bound`（证据绑定的 revision/content_hash 恰为
候选且覆盖未变——仍需说明覆盖范围）、`reusable_with_assessment`（候选 hash 不同
但覆盖属性指纹一致，保留原始捕获绑定，不伪造新时间/新回执）、`not_applicable`、
`unknown`。touch/复制/重写 manifest 不能恢复有效性。

### `verify_plan.py`（J4）

```python
def build_plan(model, graph, impacts, evidence_assessment, *, budget=None) -> dict
```

返回：

```python
{
  "required": [entry], "conditional": [entry], "optional": [entry], "blocked": [entry],
  "approvals": [entry],  # catalog 中 approval=true 的检查，独立于质量门禁
  "coverage_gaps": [{"object": "...", "impact": "firmware_compatibility",
                     "reason": "no catalog check covers this impact",
                     "change_ids": [...]}],
  "selection": {"algorithm": "greedy_bounded_set_cover",
                "budget": {...}, "selected_cost": 1.5, "considered": 12,
                "skipped_optional": [...], "optimal": false},
  "unknown": [...],
}
# entry = {"check": "chk:...", "title": "...", "kind": "offline|host|manual",
#          "priority": "required|conditional|optional|blocked", "cost": 0.5,
#          "mandatory": true, "approval": false, "module": "...",
#          "covered_impacts": [{"object": "...", "impact": "..."}],
#          "covered_change_ids": [...], "reasons": [{"code": "...", "detail": "..."}],
#          "conditions": ["..."], "blocked_reasons": [...], "requires": [...]}
```

`required`：覆盖确定影响且无有效可复用证据的检查，或 `mandatory`；`conditional`：
可能/未知影响或依赖未满足输入；`optional`：低风险/已有可复用覆盖/预算修剪（记录
被修剪项）；`blocked`：缺输入、前置未满足、依赖环、`host`/`manual` 检查（本工具
只计划不执行，`blocked_reasons` 含 `not_runnable_offline`）。**mandatory 与
approval 不得因预算被静默丢弃**；预算只修剪 optional，并报告算法与预算，不宣称
全局最优。缺覆盖 → `coverage_gaps`，不用无关检查补位。

### `compare.py`（J5）

```python
def compare(compare_input, *, analyze) -> dict
```

输入：`{"schema": "hds-change-impact-compare-input/v1", "base": {<analyze input 去掉 changes>},
"candidates": [{"id": "eco-a", "label": "...", "changes": [...], "budget": {...}},
               {"id": "eco-b", "input": {<完整 analyze input>}}],
"hard_constraints": {"max_required_cost": 6, "must_not_affect": ["if:USB-C"],
                     "require_known_impacts": true}}`。`analyze(dict) -> report` 由
调用方注入（CLI 传 `report.analyze_input`）。

返回：每个候选的 `affected_objects`、`direct`/`indirect` 计数、`unknown` 数、
`required_cost`、`mandatory_cost`、`coverage_gap` 数、`blocked` 数、
`hard_constraint_violations`；排序先按硬约束可行（不可行者垫底并注明原因），再按
未知数升序、成本升序；`recommendation` 只给带理由的建议，不自动执行、不因“检查
少”推荐更危险方案。

### `report.py` / `cli.py`（Lead）

`report.analyze_input(data) -> dict` 组装报告；`report.render_human(report) -> str`；
`cli.main(argv=None) -> int`。CLI 负责文件、原子写、退出码、`explain` 投影，不含
分析规则。

## 4. 报告结构（J6）

```jsonc
{
  "schema": "hds-change-impact-analysis/v1",
  "tool_version": "0.1.0",
  "status": "planned_with_scope",
  "target": {"project": "...", "baseline": {...}, "candidate": {...},
             "input_sha256": "sha256:...", "model_fingerprint": "sha256:..."},
  "model_scope": {...},
  "changes": {"declared": [...], "declared_not_observed": [...],
              "observed_not_declared": [...], "unauthorized_declared": [...],
              "observation_available": false, "comparison_complete": false},
  "impact_paths": [...], "impacted_objects": [...],
  "evidence_assessments": {"assessments": [...], "counts": {...}, "unknown": [...]},
  "verification_plan": {"required": [], "conditional": [], "optional": [],
                        "blocked": [], "approvals": [], "coverage_gaps": [],
                        "selection": {...}},
  "coverage_gaps": [...],
  "unknown": [{"code": "...", "where": "...", "reason": "...",
               "change_ids": [...], "consequence": "..."}],
  "cycles": [...],
  "budget": {"requested": {...}, "used": {...}},
  "not_run": ["eda_read", "host_drc", "save_and_reopen", "official_plot",
              "physical_test", "manufacturing_order"],
  "executed": ["offline_change_impact_analysis"],
  "simulated": false,
  "notes": ["建议不自动执行；本报告不是 EDA 写入授权，也不代表设计正确。"],
  "human_summary": {...}
}
```

`status` 规则：任一路径预算截断/未知对象/关键证据 unknown 且影响选择 →
`incomplete`；否则 `planned_with_scope`；无变化且声明完整 → `no_change`（必须有
完整快照声明与差异核对，两个空输入不能判相同：空模型/同 hash 无声明 → 输入无效）。

## 5. 明确不做 / NOT RUN

不调用 EDA（含只读）、旧执行器/Connector、仪器、烧录、上电、下单；不写设计文件；
不修改 `SKILL.md`、现有 references、README/CHANGELOG/版本、runtime/connector/
protocol、distribution、CI、feedback、compose、design_engine 及其他并行任务目录；
不执行输入中的 shell/脚本/链接。宿主 DRC、保存重开、官方导图、实物/制造检查只在
计划中列为 `blocked`（`not_runnable_offline`）并进入 `not_run`，不是 `pass`。

## 6. 与现有模块的适配（只读）

- **A（observation/diff/scope）**：A 的 `hds-diff/v1` 可映射为本文 `observed_diff`；
  A 的 `hds-observation/v1` 可映射为 `objects`/`baseline`/`candidate` 快照。
  J 的输出**不能**替代 A 的写入授权；A 仍须独立做写前/写后 scope 检查。
- **B/E（电气/回流规则）**：规则 ID 进入 `verification_catalog` 的 `covers`，检查
  仍由原模块执行；J 只选择和排序。
- **C（制造交付）**：CPL/ Gerber/装配产物声明为 `artifact` 对象与
  `artifact_source` 依赖；封装/pose/板框变化使版本绑定证据失效。
- **F（参数化电路）**：参数与端口声明为 `parameter`/`interface` 对象；参数变化经
  `power_supply`/`signal_path` 依赖传播。
- **G（机械布局）**：机械锚点 `mechanical_anchor`、`enclosure_constraint` 依赖；
  接口 pose 变化传播到壳体开口与差分/贴装产物。
- **H（BOM）**：`bom_line` 对象与 `artifact_source` 依赖；DNP/替代属于
  `delivery_config`。
- **I（首板测试）**：`test` 对象与 `test_reference` 依赖；判据变化只影响该测试
  及其证据，不扩散到无关电气证据。
