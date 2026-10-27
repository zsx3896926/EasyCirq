# 证据失效与复用策略（J3 `evidence.py`）

本文档描述 `design-hardware/scripts/change_impact/evidence.py` 的实现规则，是
`docs/parallel-change-impact/contract.md` §2.4/§3 的展开说明。模块只回答一个问题：
**对于候选版本，之前捕获的验证证据还能否被依赖？如果能，限制是什么？** 它不执行
检查、不写设计、不调用 EDA/仪器、不联网，也不产生任何新时间戳或宿主回执。

- 入口：`assess(model, graph, impacts, *, analysis_time=None) -> dict`
- `model`：`model.Model`（`validate_model` 的产物），只读取 `model.evidence`、
  `model.checks`、`model.changes`、`model.observed_diff`、`model.candidate` 与
  `model.analysis_time`
- `graph`：`graph.Graph`；本模块不需要它（J2 已解析出影响集合），保留参数是为了与
  其它模块的接口对称
- `impacts`：`propagate.propagate(...)` 的返回字典，使用
  `impacted_objects`、`impact_paths`、`unknown`、`truncated`
- 返回：`{assessments, unknown, counts, simulated_only, notes}`，所有列表显式排序，
  同一输入产生相同输出

> 核心不变量：**没有可验证的绑定就没有复用**。缺字段、缺覆盖、无法解析的过期时间、
> 无法重算的指纹一律进入 `unknown`，既不会被默认判为有效，也不会被凭空判为失效。

---

## 1. 状态机

状态取值来自 `__init__.py` 的 `EVIDENCE_STATES`：

| 状态 | 含义 | 是否可复用 |
|---|---|---|
| `reusable_bound` | 证据的 `revision` 与 `content_hash` 恰好等于候选快照，且 `scope_complete=true`；原捕获原样保留 | 是（按检查类型受限） |
| `reusable_with_assessment` | 候选 hash 不同，但本次影响未实际命中覆盖范围，且覆盖属性的候选指纹等于记录的 `dependency_fingerprint`；原捕获原样保留 | 是（按检查类型受限） |
| `invalidated` | 有证据表明覆盖已失效：覆盖被实际命中、指纹不一致、已过期、模拟证据冒充宿主/实物检查 | 否 |
| `not_applicable` | 检查覆盖与本次影响集合完全无交集，本 ECO 不需要它 | 否（也不代表“通过”） |
| `unknown` | 数据不足以证明可复用，也不足以判定失效（缺绑定字段、缺覆盖、缺指纹、过期时间不可解析等） | 否 |

判定按**固定顺序**执行，先命中先返回，后续规则不再覆盖：

```text
evidence
  │
  ├─(1) check 不存在（防御）──────────────────────────────► unknown  evidence_unknown_check
  ├─(2) result/revision/content_hash/tool_version 缺失 ───► unknown  evidence_missing_binding
  ├─(3) valid_until 存在且有 analysis_time
  │        ├─ 解析失败 ──────────────────────────────────► unknown  unparseable_expiry
  │        └─ valid_until < analysis_time ────────────────► invalidated expired
  ├─(4) simulated=true 且 check.kind ∈ {host, manual} ────► invalidated simulated_cannot_satisfy_host_check
  ├─(5) coverage 为 null 或 objects/attributes/impacts 全空 ► unknown  evidence_missing_coverage
  ├─(6) revision+content_hash == 候选
  │        ├─ scope_complete=false ───────────────────────► unknown  evidence_incomplete_scope
  │        └─ 否则 ───────────────────────────────────────► reusable_bound
  └─(7) revision 或 content_hash 不同
           ├─ 覆盖被实际命中 ─────────────────────────────► invalidated covered_attribute_changed
           ├─ 无任何交集 ─────────────────────────────────► not_applicable no_overlap
           ├─ 有潜在关联但无 dependency_fingerprint ──────► unknown  evidence_missing_fingerprint
           ├─ 指纹无法重算 ───────────────────────────────► unknown  fingerprint_unverifiable
           ├─ 重算指纹 == 记录指纹 ───────────────────────► reusable_with_assessment
           └─ 重算指纹 != 记录指纹 ───────────────────────► invalidated dependency_fingerprint_mismatch
```

没有 `analysis_time`（或它不可解析）时**不做过期判定**：证据不会被因为“没时间”而
默认有效，`notes` 会明确写出“expiry was not evaluated”。`analysis_time` 参数优先于
`model.analysis_time`。

---

## 2. 绑定：内容绑定（content binding）

“可复用”首先要求**内容绑定**，而不是“文件还在”“manifest 还在”“时间很新”：

| 绑定字段 | 来源 | 缺失/不匹配的后果 |
|---|---|---|
| `revision` | 证据记录 vs `model.candidate.revision` | 缺失 → `unknown`；不同 → 进入覆盖/指纹判定 |
| `content_hash` | 证据记录 vs `model.candidate.content_hash` | 缺失 → `unknown`；不同 → 进入覆盖/指纹判定 |
| `tool_version` | 证据记录 | 缺失 → `unknown`（无法说明捕获工具语义） |
| `coverage` | 证据记录 | 缺失或空 → `unknown`（无法界定复用范围） |
| `result` | 证据记录 | 缺失 → `unknown`（没有结论就谈不上复用） |
| `scope_complete` | 证据记录 | `false` → 即使 revision/hash 匹配也 `unknown`（部分捕获不能当完整绑定） |

`revision` 与 `content_hash` **同时**匹配候选快照、且 `scope_complete=true` 时判
`reusable_bound`。此时 `reuse.basis = "same_revision_and_content_hash"`，模块只列
限制，不改写任何捕获字段。

### 2.1 内容绑定 vs 语义可复用

- **内容绑定（`reusable_bound`）**：证据就是在候选内容上捕获的，捕获本身覆盖了
  候选版本。这是最强的复用依据。
- **语义可复用（`reusable_with_assessment`）**：整体 hash 已变，但证据所覆盖的**那部分
  属性**在候选侧与捕获时语义相同（指纹一致）。它说明“这个检查覆盖的东西没变”，
  **不**说明“整个设计没变”，也不说明“设计正确/已验证”。
- 两种复用都保留原始捕获，不得把语义复用写成新的 `captured_at`、`revision`、
  `content_hash`、`host` 或“新回执”。

---

## 3. 覆盖命中、潜在关联与无关

J2 的输出按对象建立索引后，对每条证据的 `coverage` 分三种情况：

### 3.1 实际命中（`invalidated`，`covered_attribute_changed`）

满足任一条件即视为覆盖被实际命中：

1. 声明变更（或 `observed_diff`）直接改到被覆盖对象的**被覆盖属性**：
   属性路径相等、互为前缀（`voltage` 覆盖 `power.voltage`），或末段同名；
   整对象 add/remove（`attribute=None`）视为触及全部覆盖属性。
2. 被覆盖对象出现在 `impacted_objects` 中，且证据声明的 `coverage.impacts`
   与该对象的影响类别有交集。
3. 被覆盖对象被影响，且证据**没有**声明 `coverage.attributes`（对象级覆盖），
   影响类别中存在非 `documentation_only` 的类别。
4. 证据未声明对象、只声明 `coverage.impacts`（检查级覆盖）时，传播出的影响类别
   与它有交集。

命中原因的 `detail` 列出具体对象、属性/影响和变更标签，`change_ids` 附上可追溯的
声明变更 ID（观测差异没有 `chg:` ID，如实留空并在 `detail` 说明）。

### 3.2 潜在关联但未命中（由指纹决定）

以下情况说明覆盖对象**可能**受影响，但没有直接证据证明覆盖内容变了：

- 被覆盖对象被影响，但证据声明了 `coverage.attributes`，而该影响是间接影响
  （例如网络电压变化传播到器件，而证据只覆盖器件的 `mpn`）；
- 被覆盖对象被影响，但 `coverage.impacts` 过滤条件不匹配（例如证据只覆盖
  `electrical_state`，传播结果是 `power_integrity`）；
- 被覆盖对象出现在 J2 的 `unknown` 列表中（影响边界未定）；
- 被覆盖对象有声明/观测变更，但只涉及显示类属性且不匹配覆盖属性。

此时：
- 有 `dependency_fingerprint` → 重算候选指纹后比较；
- 无 `dependency_fingerprint` → `unknown`（`evidence_missing_fingerprint`）：
  “不能证明可复用，也不能凭空否定”，交给人或后续检查。
- 只有 `documentation_only` 影响、且证据的覆盖过滤器不包含它时，不算潜在关联：
  图签文字变化不得否定独立电气证据。

### 3.3 完全无交集（`not_applicable`，`no_overlap`）

覆盖对象不在受影响集合、覆盖影响类别与传播影响无交集、也没有命中覆盖属性的
变更。此时该检查与本 ECO 无关，标 `not_applicable`，**不比较指纹**：避免把无关
证据标记成“可复用”，也避免它们的绑定问题影响本次结论。`not_applicable` 不是
“检查通过”，只是“本次不需要”。

---

## 4. 覆盖属性指纹（`dependency_fingerprint`）

### 4.1 计算约定

`evidence.covered_attribute_fingerprint(model, coverage)`：

1. 对 `coverage.objects` 中的每个对象、`coverage.attributes` 中的每个属性路径，
   取**候选侧**值；路径不存在（`MISSING`）时跳过该对；
2. 生成标签对 `(object_id + ':' + attribute_path, candidate_value)`；
3. `coverage.impacts` 中每个影响类别追加标签对 `('impact:' + impact, impact)`；
4. 按标签排序，用 `canonical.fingerprint`（即规范 JSON 的 SHA-256）得到
   `sha256:<64hex>`。

示例（对象 `cmp:U2` 的 `mpn`，覆盖影响 `electrical_state`）：

```text
pairs = [("cmp:U2:mpn", "LDO1"), ("impact:electrical_state", "electrical_state")]
dependency_fingerprint = canonical.fingerprint(pairs)
```

### 4.2 比较规则

- `coverage` 未列出属性、也未列出影响（只有对象）时，无法在不臆造约定的前提下
  重算指纹 → `unknown`（`fingerprint_unverifiable`），不会“大概相同就复用”。
- 指纹字段缺失 → `unknown`（`evidence_missing_fingerprint`）。
- 重算值等于记录值 → `reusable_with_assessment`，`reuse.basis =
  "dependency_fingerprint_match"`，并返回
  `reuse.computed_fingerprint`、`reuse.preserved_capture` 与 `reuse.limits`。
- 重算值不等于记录值 → `invalidated`（`dependency_fingerprint_mismatch`）：候选侧
  被覆盖的属性值已经不同，原捕获不再覆盖候选内容。

---

## 5. 模拟证据边界

`simulated: true` 的证据只能作为**离线参考**：

- `valid_for` 至多为 `["offline"]`，**永远不含 `host`/`manual`**；
- 若记录声称检查种类是 `host` 或 `manual` → 直接 `invalidated`
  （`simulated_cannot_satisfy_host_check`），即使覆盖命中、revision/hash 匹配也
  不能把它升级为宿主/实物通过依据；
- 可复用的模拟证据在 `reuse.limits` 中固定包含：
  “模拟证据，仅离线参考，不得作为宿主/实物通过依据”；
- `simulated_only=true` 表示“本次全部 prior_evidence 都是模拟证据”，报告会在
  `notes` 中提示这一点。

`valid_for` 的完整语义：可复用状态列出该证据能支持的检查种类（`offline`/`host`/
`manual` 的子集，模拟证据限 `offline`）；`invalidated`/`not_applicable`/`unknown`
为 `[]`。

---

## 6. 过期与未知

- `valid_until` 存在、`analysis_time` 可解析且 `valid_until < analysis_time` →
  `invalidated`（`expired`）。
- ISO 8601 字符串按 `datetime.fromisoformat` 解析；兼容结尾 `Z`；无时区按 UTC
  处理；解析失败 → `unknown`（`unparseable_expiry`），**不得**当作未过期。
- 没有 `analysis_time` → 不做过期判定，`notes` 明确“expiry was not evaluated”；
  这不是“有效”。
- 时间比较只看声明的 `analysis_time` 或显式参数，不读取系统时钟、文件 mtime。

---

## 7. 禁止事项（不可用能力）

以下操作**不能**让证据恢复有效性，实现与测试都按此约束：

1. 不得改写 `captured_at`、`revision`、`content_hash`、`tool_version`、`host`：
   `original` 与 `reuse.preserved_capture` 都原样复制这些字段。
2. 不得生成新的捕获时间、新的宿主回执或“已验证/已通过”标记。
3. `touch` 文件、复制证据目录、重写 manifest、改文件名/顺序都不构成绑定：
   绑定只来自 `revision + content_hash + scope_complete` 或指纹一致。
4. 不得把“找不到证据/缺字段”当成“无需验证”或“有效”；缺数据一律 `unknown`。
5. 不得把 `not_applicable` 读成“检查通过”；它只表示本次变更与其覆盖无关。
6. 不执行输入中的任何内容，不调用 EDA/仪器，不写设计文件，不联网。

---

## 8. 输出结构

```text
{
  "assessments": [                      # 按 evidence_id 排序，一条证据一条记录
    {"evidence_id": "ev:1", "check": "chk:voltage_drop",
     "status": "reusable_with_assessment",
     "reasons": [{"code": "...", "detail": "...", "change_ids": ["chg:1"]}],
     "reuse": {"basis": "dependency_fingerprint_match",
               "computed_fingerprint": "sha256:...",
               "covered_objects": ["cmp:U2"], "covered_attributes": ["mpn"],
               "covered_impacts": ["electrical_state"],
               "preserved_capture": {"captured_at": "...", "revision": "r1",
                                     "content_hash": "sha256:...",
                                     "tool_version": "...", "simulated": false,
                                     "host": {...}},
               "limits": ["覆盖对象仅限：...", "..."]},
     "original": {...},                # 原证据记录逐字段原样
     "coverage": {...},
     "valid_for": ["offline"],
     "notes": [...]}
  ],
  "unknown": [{"code": "evidence_missing_fingerprint",
               "evidence_id": "ev:2", "reason": "..."}],
  "counts": {"invalidated": 1, "reusable_bound": 0,
             "reusable_with_assessment": 1, "not_applicable": 1,
             "unknown": 1, "total": 4},
  "simulated_only": false,
  "notes": ["..."]
}
```

- 所有 `model.evidence` 记录都出现在 `assessments` 中，**不丢弃任何一条**；重复
  评估同一条证据不可能发生（`model` 已保证 evidence id 唯一）。
- `unknown` 顶层列表列出所有 `status=unknown` 的证据及其首个原因代码，便于报告层
  汇总；`counts` 含五种状态与 `total` 且自洽。
- `reasons` 只描述判定依据，不是执行日志；`change_ids` 排序去重，观测差异没有
  `chg:` ID 时为空。
- `notes` 全局提示覆盖：无证据、模拟证据、未评估过期、传播被预算截断、传播存在
  `unknown`、以及“原捕获原样保留、未生成新回执”。

---

## 9. 示例判定表

| # | revision/hash | scope_complete | coverage | 本次影响 | simulated | 判定 | 原因代码 |
|---|---|---|---|---|---|---|---|
| 1 | 等于候选 | true | `cmp:U2.mpn` | 无交集 | false | `reusable_bound` | `same_revision_and_content_hash` |
| 2 | 等于候选 | false | `cmp:U2.mpn` | 无交集 | false | `unknown` | `evidence_incomplete_scope` |
| 3 | 旧版本 | true | `net:+5V.power.voltage` | 电压变更直接命中覆盖属性 | false | `invalidated` | `covered_attribute_changed` |
| 4 | 旧版本 | true | `cmp:U2.mpn`（无影响过滤） | `cmp:U2` 被 `power_integrity` 命中 | false | `invalidated` | `covered_attribute_changed` |
| 5 | 旧版本 | true | `cmp:U2.mpn` + 过滤 `electrical_state` | `cmp:U2` 被 `power_integrity` 影响 | false | 指纹一致 → `reusable_with_assessment`；否则 `invalidated` | `dependency_fingerprint_match` / `dependency_fingerprint_mismatch` |
| 6 | 旧版本 | true | `cmp:U9.mpn`（未被影响） | 与本检查无关 | false | `not_applicable` | `no_overlap` |
| 7 | 旧版本 | true | `cmp:U2.mpn` + 过滤 `electrical_state` | `cmp:U2` 被 `power_integrity` 影响 | false | 无指纹 → `unknown` | `evidence_missing_fingerprint` |
| 8 | 旧版本 | true | 任意 | 任意 | true 且 check 为 `host`/`manual` | `invalidated` | `simulated_cannot_satisfy_host_check` |
| 9 | 旧版本 | true | 任意 | 任意 | true 且 check 为 `offline` | 仅 `offline` 复用，`limits` 含模拟声明 | 同上（复用分支） |
| 10 | 缺 `content_hash` | true（且 `captured_at` 很新） | 任意 | 任意 | false | `unknown`（复制/touch 不能恢复） | `evidence_missing_binding` |
| 11 | 旧版本 | true | `valid_until=2025-12-01`，`analysis_time=2026-02-01` | 任意 | false | `invalidated` | `expired` |
| 12 | 旧版本 | true | `valid_until=not-a-date` 且给出 `analysis_time` | 任意 | false | `unknown` | `unparseable_expiry` |
| 13 | 旧版本 | true | `coverage=null` | 任意 | false | `unknown` | `evidence_missing_coverage` |

---

## 10. 明确局限

- 指纹只覆盖 `coverage` 显式声明的对象/属性/影响；未声明部分不在复用范围内，
  `reuse.limits` 会逐条列出。没有属性路径的“对象级覆盖”不参与语义复用，
  只能靠内容绑定。
- 指纹重算依赖声明模型里的候选侧属性值；模型没有声明的属性视为缺失（跳过），
  不能反推真实设计内容。
- `coverage` 引用了模型中不存在的对象、或属性路径无法解析时，指纹判
  `unknown`（`fingerprint_unverifiable`），不会猜测。
- 本模块不判断证据结果本身是否正确：`result=pass/fail/unknown` 都只按绑定性评估；
  失败/未知结果不会被复用“升级”为通过（`reuse.limits` 会注明原始结果）。
- 只评估 `model.evidence` 中实际存在的记录；检查自引用等模型一致性问题由
  `model.validate_model` 负责，不在此重复处理。
- 传播被预算截断时，`not_applicable` 只代表“与已知影响集合无交集”，不代表
  “一定无影响”（`notes` 会提示）。
- 测试：`tests/change_impact/test_evidence.py`（stdlib unittest，39 个用例，覆盖
  正/反/unknown、模拟边界、过期、指纹一致/不一致、无关变化不误伤、确定性），运行：

  ```text
  python -m unittest discover -s tests -p "test_evidence.py" -v
  ```
