# 与并行任务 A/B/C/E/F/G/H/I 的集成建议

**本文只是适配建议，不修改任何其他并行任务的代码。** J 的输出不能替代 A 的
写入授权，也不接管现有 feedback scope 检查：现有 scope 判断“实际修改是否越界”，
J 判断“理论上影响什么、哪些证据失效、需要重跑什么”，两者互补。

## 1. 总原则

1. J 只读消费**已冻结的规范化快照/模型**，不直连 EDA、不读取实时工程、不调用
   执行器。任何模块都不应把 J 的报告当作“可以写入”的许可。
2. 拥有检查的模块（B/E 电气规则、C 制造审计、I 测试计划等）仍然是检查的唯一
   执行者；J 只在 `verification_catalog` 中选择、排序、标注 gap。
3. 依赖必须**显式声明**。没有边不是无影响：适配层必须把“未知”写成
   `model_scope.unknown_objects` / `snapshot.missing_fields`，而不是省略。
4. 适配代码应作为后续独立集成 PR 提供，不与其他任务互相 cherry-pick 未稳定提交；
   schema 变更走版本号（`hds-change-impact-input/v1` → `/v2`）。
5. J 的输出状态只有 `planned_with_scope` / `incomplete` / `no_change` /
   `input_invalid`，没有 `design_pass`；宿主/人工检查永远是计划/NOT RUN。

## 2. A（运行时/Connector/observation/diff/scope）

| A 的产物 | 映射到 J 输入 | 说明 |
|---|---|---|
| `hds-observation/v1`（PCB/原理图快照） | `objects[]`（component_instance/pin/net/...）+ `baseline`/`candidate` 快照字段 | 用 observation 的 project/document/revision/内容哈希填 `baseline.content_hash`；`snapshot_scope` 填实际读取成功的对象类，失败项进 `missing_fields` |
| `hds-diff/v1` | `observed_diff[]` | 每个 changed 对象/属性映射为 `{object, attribute, before, after, source:"observed"}`；未读取的类别不得当作空差异 |
| A 的 writable scope（contract.scope） | `changes[].authorized` / `authorized_scope` | **仅用于标注授权与归因**。J 的 `planned_with_scope` 不构成写入授权；A 仍须独立执行写前/写后 scope 检查 |
| 对象 identity（UUID/designator/net id） | `objects[].id`（`cmp:`/`net:`/`pin:`…） | 身份以 ID 为准，网名/位号是属性；重命名与分区变化分开声明 |

注意：A 的 diff 结果与 J 的“声明变更”不一致时，J 会把未声明的实际差异列为
`observed_not_declared`（不自动允许）并把状态置为 `incomplete`，这正是两者互补
的地方，不应在适配层抹平。

## 3. B/E（电气审查/高速回流）

- 把 B/E 的每条规则映射为一个 `verification_catalog` 条目：
  `id`（如 `chk:electrical.ldo_dropout`）、`kind: "offline"`、
  `covers: [{"object": "...", "impact": "power_integrity"}]`、
  `module: "electrical-review"`、`mandatory`/`approval` 按项目门禁声明。
- 规则依赖的输入（如输入电压范围、叠层参数）写 `requires_inputs`；J 会把这些
  检查标为 conditional 并列出条件，而不是假装可执行。
- 检查仍由 B/E 执行；J 不重复实现规则，只选择与报告 gap。

## 4. C（制造交付审计）

- CPL/Gerber/装配图/贴装坐标等产物映射为 `artifact` 对象；来源关系
  `artifact_source`（component/BOM/layout_region → artifact）。
- 封装、pose、板框/孔位、叠层变化会使相应版本绑定证据失效（J3 的
  `invalidated`），C 的审计结果应带 `revision`/`content_hash`/`coverage` 以便
  复用判定；缺绑定字段时 J 只会给 `unknown`，不会默认有效。
- 制造类检查 `kind` 用 `offline`（若 C 可离线核对）或 `host`/`manual`
  （J 只计划为 blocked，标 `not_runnable_offline`）。

## 5. F（参数化电路）

- 参数与端口映射为 `parameter`（对象属性上的 `value/resistance/...`）与
  `interface` 对象；参数变化经 `power_supply`/`signal_path`/`pin_mapping`
  依赖传播。
- 参数合法域/约束写入 `constraints`（`voltage_range`/`current_limit`/
  `impedance`…），J 在影响解释中引用该约束来源。
- 参数化生成器产生的对象 ID 必须稳定且带类型；同一参数不同单位不改变 ID。

## 6. G（机械布局）

- 机械锚点/壳体开口/安装孔映射为 `mechanical_anchor`；接口与锚点关系用
  `mechanical_constraint`/`enclosure_constraint`。
- 接口 pose、板框、器件高度/封装变化会沿这些语义传播到 `mechanical_fit`/
  `enclosure_interface`/`assembly_fit`；即使网络未变也会列影响。
- 机械检查通常 `kind: "manual"`，J 只列为 blocked（NOT RUN）。

## 7. H（采购/BOM）

- 器件/BOM 行映射为 `bom_line`，关系 `artifact_source`（component → bom_line →
  artifact）；DNP/替代/装配变体用 `delivery_config` 变更类别。
- 采购/缺料替代的影响（BOM 变体、贴装产物）由 J 传播；库存/价格检查属于 H，
  可声明为 `optional` 或 `approval` 检查，不混入质量门禁。

## 8. I（首板测试计划）

- 测试项映射为 `test` 对象；测试引用关系用 `test_reference`/
  `verification_coverage`；判据变化用 `test_criterion` 变更类别。
- 测试判据变化只影响该测试与其证据，不扩散到无关电气证据（R12）。
- 实测结果作为 `prior_evidence` 输入时必须带 revision/content_hash/coverage/
  tool_version 与 `simulated` 标记；模拟/台架证据不能升级为实物通过。

## 9. 通用映射示例（最小）

```jsonc
// A 的 observation/diff → J 输入（片段）
{
  "schema": "hds-change-impact-input/v1",
  "baseline":  {"project": "board", "document": "main", "revision": "r3",
                "content_hash": "sha256:…", "source_type": "feedback_observation",
                "snapshot_scope": ["component_instance", "net", "pin", "bom_line"],
                "missing_fields": [], "complete": false},
  "candidate": {"project": "board", "document": "main", "revision": "r4",
                "content_hash": "sha256:…", "source_type": "feedback_observation",
                "snapshot_scope": ["component_instance", "net", "pin", "bom_line"],
                "missing_fields": [], "complete": false},
  "objects": [
    {"id": "cmp:U1", "kind": "component_instance",
     "attributes": {"mpn": "MCU-B", "footprint": {"uuid": "fp:qfn32"}},
     "baseline_attributes": {"mpn": "MCU-A"}},
    {"id": "net:USB_DP", "kind": "net", "attributes": {"name": "USB_DP"}}
  ],
  "dependencies": [
    {"id": "dep:1", "from": "cmp:U1", "to": "net:USB_DP",
     "semantic": "signal_path", "direction": "forward", "certainty": "observed"}
  ],
  "changes": [
    {"id": "chg:1", "object": "cmp:U1", "attribute": "mpn",
     "before": "MCU-A", "after": "MCU-B", "authorized": true,
     "source": {"type": "declared", "ref": "ECO-7"}}
  ],
  "observed_diff": [
    {"object": "cmp:U1", "attribute": "mpn", "before": "MCU-A",
     "after": "MCU-B", "source": "observed"}
  ],
  "verification_catalog": [
    {"id": "chk:electrical.mcu_power", "title": "MCU 供电与去耦", "kind": "offline",
     "cost": 0.5, "mandatory": true, "module": "electrical-review",
     "covers": [{"object": "cmp:U1", "impact": "power_integrity"}]}
  ],
  "prior_evidence": [
    {"id": "ev:1", "check": "chk:electrical.mcu_power", "result": "pass",
     "tool_version": "…", "revision": "r3", "content_hash": "sha256:…",
     "coverage": {"objects": ["cmp:U1"], "attributes": ["mpn"],
                  "impacts": ["power_integrity"]},
     "simulated": false, "captured_at": "…", "scope_complete": true}
  ],
  "budget": {"max_depth": 8, "max_paths": 500, "max_cost": 100},
  "model_scope": {"declared_kinds": ["component_instance", "net", "pin", "bom_line"],
                  "unknown_objects": [], "dependencies_complete": false,
                  "notes": "A 未提供的边保持 unknown，不当作无影响"}
}
```

## 10. 协调方式与禁止事项

- J 的 schema 与状态语义由 `docs/parallel-change-impact/contract.md` 固定；
  其他模块需要新增字段时先提 schema 变更 PR，不直接改 J 的输入。
- 不在集成中 cherry-pick 其他并行任务未稳定的提交；不复制现有 diff 引擎；需要
  before/after 差异时由适配层调用 A 的只读输出，J 只做语义分类。
- J 的报告不得写回设计、不得自动触发 B/C/I 执行、不得改变 A 的授权结论。
- 所有“已执行”声明必须由实际执行模块给出；J 侧永远是
  `executed: ["offline_change_impact_analysis"]` 与 `not_run` 清单。
