# 执行结果协议（EDA / 制造 / 样机）

| 项 | 值 |
|---|---|
| 文档 | `docs/round3/execution-protocol.md` |
| 协议版本 | `hds-execution-result/1`（2026-10-22） |
| 审计基线 | `dc62f20`（`origin/main`） |
| 适用对象 | `design-hardware/SKILL.md`、`design-hardware/scripts/eda_exec.py`、证据包、Agent 交付说明 |
| 文档性质 | **规范（specification）**，不是实现声明，也不是真机验收记录 |
| 协议自身验证状态 | `NOT RUN`：本协议未在真实 EDA 会话、PCB、制造或样机上执行；现有能力状态见 §7.3 |

> **先读这一条。** 本文件定义“结果应该怎样被判定和表述”，不证明 `eda_exec.py` 已经具备这些字段。除 §7.3 明确标为 `DONE` 的现有能力外，其余均为下一轮实现要求；在实现并通过 §7.4 的测试之前，不得引用本协议宣称某项能力已可用或已在真实 EDA 中验证。
>
> 本协议解决四类常见虚假完成：把“写进画布”说成“核对通过”，把“保存返回 true”说成“已持久化”，把“DRC 没跑”说成“没有问题”，把“方案/候选包”说成“可打样/可生产”。

---

## 0. 目的与硬规则

### 0.1 目的

统一 Agent、执行桥、证据包和交付说明对“做到哪一步”的判定，使每个结论都能落到：

1. 一个明确的等级（§1）；
2. 一个明确的作用域（项目/页/对象/产品）；
3. 一组可复核的字段和证据（§2、§5）；
4. 一句不超出证据的表述（§6）。

### 0.2 硬规则

1. **一级一证**：等级由字段和证据判定，不由语气、文件名、截图数量或测试总数判定。
2. **不可跳级**：`L(n+1)` 要求 `L(n)` 在同一作用域内为 `passed` 或显式 `not_applicable`；`partial` 不得升级。
3. **快照不完整不得核对**：`truncated` 只能支持未受截断影响的对象级结论；`read_failed`、`timeout`、`page_not_active` 不支持任何“核对通过”。
4. **写入不等于保存**：`apply` 成功只证明编辑器接受了动作；`save.saved=true` 才证明保存调用成功；`reopen.match=true` 才证明重开后仍在。
5. **保存不等于电气正确**：`L3` 只证明结构/属性/连接与计划一致，不证明电路设计正确。
6. **检查通过不等于可制造**：`L4` 只证明已执行的检查在已声明规则下通过；`L5` 才涉及制造资料。
7. **部分成功必须显式**：任何 `partial` 必须列出已写入、失败、冲突、未执行的 key；不得用“基本完成”掩盖。
8. **原始证据与人工解释分离**：`manifest.json` 只放机器事实；人的判断放 `interpretation.json`，并引用 manifest 的 artifact id。
9. **双层表达事实一致**：新手层与工程师层共享同一个 `level`/`level_status`；任一层都不得省略限制。
10. **未执行标 `not_run`，环境缺失标 `blocked`，执行后矛盾标 `failed`**；不得把三者互相替代。

---

## 1. 统一结果等级

### 1.1 等级枚举

| 序号 | 机器码 | 中文名 | 一句话定义 | 前置 |
|---:|---|---|---|---|
| 1 | `PLAN_READY` | 方案已准备 | 需求、约束、计划、计算/来源已形成，可复核；未写入 EDA | 无（可离线） |
| 2 | `WRITTEN` | 已写入 EDA | 编辑器接受了至少一个受控动作；对象可能只在内存 | `L1` 通过，写入前条件通过 |
| 3 | `READBACK_VERIFIED` | 已回读核对 | 写入后用完整快照逐项、逐字段比对，计划项全部一致 | `L2` 通过，回读快照完整 |
| 4 | `ELECTRICAL_CHECKED` | 电气检查已执行 | ERC/DRC/网表等价性等检查已实际执行并记录结果 | `L3` 通过，检查绑定同一内容哈希 |
| 5 | `MANUFACTURING_VERIFIED` | 制造资料已核对 | BOM/CPL/Gerber/钻孔/层叠/DFM 与同一工程版本交叉核对 | `L4` 通过，制造资料齐全 |
| 6 | `PROTOTYPE_VERIFIED` | 样机功能已验证 | 实物样机在记录的条件下完成测试并达到验收阈值 | `L5` 通过，有实物与测试记录 |

等级只表示“证据覆盖到哪一层”，不表示“设计一定正确”。每一级都必须在 `scope` 内成立；项目级等级要求项目级证据，不能用单页证据外推。

### 1.2 状态枚举

| 状态 | 含义 | 与审计标记对应 | 允许的总体表述 |
|---|---|---|---|
| `passed` | 该级在该作用域内全部条件成立，证据齐全 | `DONE` | “已到达 X 级” |
| `partial` | 只覆盖部分对象/检查/测试；未满足该级全部条件 | `PARTIAL` | “部分完成/仅 X 项” |
| `not_run` | 没有执行记录 | `NOT RUN` | “未执行/未开始” |
| `blocked` | 外部前提缺失（无 EDA、无 PCB、无样机、无授权） | `BLOCKED` | “被 X 阻断” |
| `failed` | 已执行，但结果与期望矛盾或出现缺陷 | `DEFECT` | “失败/不一致/缺陷” |
| `not_applicable` | 本次交付范围明确不包含该级，且有范围说明 | 无 | “不在本次范围” |

`failed` 必须带 `failure_kind`：`mismatch`（回读/比较不一致）、`defect`（代码或资料缺陷）、`regression`（回归失败）、`tool_error`（工具错误）。

### 1.3 六级判定表

以下每一级给出：判定字段、必须证据、允许的部分通过、禁止的表述。字段路径均相对于一次运行的结果包（§1.5）。

#### 1.3.1 `L1 PLAN_READY`（方案已准备）

**判定字段**

```json
{
  "level": "PLAN_READY",
  "level_index": 1,
  "level_status": "passed",
  "plan": {
    "validated": true,
    "schema_version": 1,
    "sha256": "…",
    "based_on_snapshot_content_sha256": null
  },
  "scope": {"kind": "page", "project_uuid": null, "page_uuid": null},
  "eda": {"write_attempted": false},
  "preconditions": {"status": "not_checked"}
}
```

条件：

- `plan.validated=true`，`plan.schema_version=1`，`plan.sha256` 非空；
- `scope.kind` 属于 `item|page|project|product`，且 `scope.declared=true`；
- `eda.write_attempted=false`；
- `not_run[]` 明确列出未做的 EDA/检查/制造/样机项；
- 若 EDA 不可用，`level_status=blocked` 且 `blocked_by[]` 非空，而不是 `not_run`。

**必须证据**

- 计划 JSON 文件 + SHA256（`artifacts[].role="plan"`）；
- 需求/约束摘要或设计 brief；
- 关键计算、选型依据、原厂资料来源（可为离线）；
- 明确的“未写入”声明（`not_run[]` 或 `limitations[]`）。

**允许的部分通过**

- 计划只覆盖部分功能/页面时，`level_status=partial`，`scope.excluded[]` 列出排除项；可以写“部分方案已准备（仅 X）”。
- 允许计划基于离线假设；但必须写 `assumptions[]`，不得把假设写成实测。

**禁止的表述**

- “已写入/已画好/已改好/已经在 EDA 里”；
- “已核对/已确认正确”；
- “已保存/已持久化”；
- “可打样/可生产/可直接下单”。

#### 1.3.2 `L2 WRITTEN`（已写入 EDA）

**判定字段**

```json
{
  "level": "WRITTEN",
  "level_index": 2,
  "level_status": "passed",
  "preconditions": {"status": "passed"},
  "execution": {
    "state": "completed",
    "results": [{"key": "part-R1", "ok": true}],
    "written_keys": ["part-R1"],
    "failed_keys": [],
    "conflict_keys": []
  },
  "snapshot": {
    "before": {
      "integrity": {"status": "complete"},
      "content_sha256": "…"
    }
  },
  "persistence": {"state": "in_memory"}
}
```

条件：

- `preconditions.status="passed"`（§3）；
- `execution.state` 属于 `completed|partial`；
- `execution.results` 非空，且每个结果有 `key/ok`；
- `execution.written_keys` 非空；
- `snapshot.before.integrity.status="complete"`；
- `snapshot.before.content_sha256 = plan.based_on_snapshot_content_sha256`；
- `persistence.state` 属于 `in_memory|saved|reopened`。

**必须证据**

- `apply-result.json`：`execution.results`、`written_keys`、`failed_keys`、`conflict_keys`；
- 写入前的完整快照及哈希、时间；
- 计划文件及哈希；
- 工具版本、客户端版本、会话来源、工程/页 UUID；
- 若 `--save`：`save.saved`、保存后回读计数；若未保存，`persistence.state="in_memory"`。

**允许的部分通过**

- `execution.state=partial` 时 `level_status=partial`；只能按 key 说“已写入 X 项”，并列出 `failed_keys`、`conflict_keys`、`unknown_keys`。
- `--allow-partial` 只允许执行无冲突项；部分写入后**禁止自动保存**，除非所有已执行项 `verification=verified`。

**禁止的表述**

- “已核对/已确认正确/逐项通过”（未回读）；
- “已保存/已持久化”（除非 `save.saved=true` / `reopen.match=true`）；
- “电气正确/连接正确/DRC 通过”；
- “页面已改好/全部完成”。

#### 1.3.3 `L3 READBACK_VERIFIED`（已回读核对）

**判定字段**

```json
{
  "level": "READBACK_VERIFIED",
  "level_index": 3,
  "level_status": "passed",
  "snapshot": {
    "after": {
      "integrity": {"status": "complete"},
      "content_sha256": "…",
      "captured_at_utc": "…"
    }
  },
  "verification": {
    "status": "verified",
    "items": [{"key": "part-R1", "verification": "verified"}],
    "diff": [],
    "fields_compared": ["designator", "unique_id", "component", "supplier_id", "footprint", "x", "y", "rotation", "mirror", "add_into_bom", "add_into_pcb"]
  },
  "identity": {
    "project_uuid_before": "…",
    "project_uuid_after": "…",
    "page_uuid_before": "…",
    "page_uuid_after": "…",
    "match": true
  }
}
```

条件：

- `snapshot.after.integrity.status="complete"`；
- `verification.status="verified"`；
- `verification.items` 中每个计划项 `verification="verified"`；
- `verification.diff=[]`；
- `verification.fields_compared` 覆盖 §7.6 的必需字段集；
- `identity.match=true`，且前后页 UUID 与请求的页 UUID 一致；
- `execution.results` 的 `primitive_id/unique_id/designator` 被用于定位和比对，而不是被丢弃。

**必须证据**

- 写入后完整快照 + `snapshot_sha256` + `content_sha256` + 时间；
- 写入前快照 + 哈希；
- 逐项 `expected` / `observed` 字段差异表；
- 每个操作类型的必需字段（§7.6）；
- 页/工程身份；
- 没有 `conflicts`，没有 `failed` 项；
- 若 `persistence.state="reopened"`：`reopen.match=true` 且比较域覆盖 §7.6。

**允许的部分通过**

- 只有部分对象/字段通过时 `verification.status=partial`，`level_status=partial`；只能写“已回读核对 X 项；Y 项未核对/失败”。
- 快照为 `truncated` 时，只有未被截断影响的对象可以标 `verified`；必须写 `snapshot_scope_exclusions[]`，不能写“整页核对通过”。

**禁止的表述**

- “电气正确/全部连接正确/电路没有问题”；
- “DRC 通过/ERC 通过”（未执行 L4）；
- “可制造/可打样/可贴片”；
- “整页核对通过”（当只核对了部分对象或快照不完整）。

#### 1.3.4 `L4 ELECTRICAL_CHECKED`（电气检查已执行）

**判定字段**

```json
{
  "level": "ELECTRICAL_CHECKED",
  "level_index": 4,
  "level_status": "passed",
  "electrical": {
    "based_on_snapshot_content_sha256": "…",
    "checks": [
      {
        "kind": "erc",
        "executed": true,
        "tool": "lceda-pro",
        "version": "4.1.78.34f5b8d9",
        "rules_sha256": "…",
        "raw_output_sha256": "…",
        "violations": [],
        "waivers": []
      }
    ],
    "unwaived_violations": 0,
    "checks_not_run": []
  }
}
```

条件：

- `electrical.based_on_snapshot_content_sha256 = snapshot.after.content_sha256`；
- `checks` 非空，每项 `executed=true`，且有 `tool/version/rules_sha256/raw_output_sha256`；
- `unwaived_violations=0`；
- 该作用域要求的检查全部在 `checks_not_run` 之外；
- 任何 waiver 必须有 `reason/owner/date/scope`，且不能覆盖安全/间距/连接性硬规则。

**必须证据**

- 原始 ERC/DRC 报告文件 + SHA256；
- 规则集/阈值及其哈希或版本；
- 网表导出文件 + 引脚-网络比对结果；
- 若做了 PCB：连通性/DRC 报告、层叠/规则版本；
- 工具版本、执行时间、页/板 UUID、工程文件哈希；
- `waivers[]` 及批准记录（如适用）。

**允许的部分通过**

- 只执行了部分检查时 `electrical.status=partial`；`checks_not_run[]` 列出未执行项；只能写“已执行 ERC；DRC 未执行”。
- 有 waiver 时只能写“在 waiver 范围内通过”，不能写“无问题”。

**禁止的表述**

- “电气设计正确/全部检查通过/没有错误”；
- “可生产/可制造/可打样”；
- 把“检查未运行”写成“检查通过”。

#### 1.3.5 `L5 MANUFACTURING_VERIFIED`（制造资料已核对）

**判定字段**

```json
{
  "level": "MANUFACTURING_VERIFIED",
  "level_index": 5,
  "level_status": "passed",
  "manufacturing": {
    "based_on": {
      "project_file_sha256": "…",
      "pcb_uuid": "…",
      "schematic_uuids": ["…"],
      "exported_at": "…"
    },
    "artifacts": [
      {"role": "bom", "path": "artifacts/bom.csv", "sha256": "…"},
      {"role": "cpl", "path": "artifacts/cpl.csv", "sha256": "…"},
      {"role": "gerber", "path": "artifacts/gerber.zip", "sha256": "…"}
    ],
    "cross_checks": [
      {"kind": "bom_vs_schematic", "status": "passed"},
      {"kind": "cpl_vs_pcb", "status": "passed"},
      {"kind": "gerber_layers", "status": "passed"},
      {"kind": "drill_vs_pads", "status": "passed"}
    ],
    "orders": {"placed": false}
  }
}
```

条件：

- `based_on` 绑定同一工程版本（工程文件 SHA256、PCB UUID、图页 UUID 列表、导出时间）；
- 制造资料角色至少包含 `bom/cpl/gerber/drill/stackup/dfm_report`（按交付路线裁剪时必须写明 `not_applicable_reason`）；
- 每件资料有 `sha256/generated_by/generated_at`；
- `cross_checks` 全部 `passed`；
- `orders.placed=false`（本协议不授权下单）。

**必须证据**

- BOM（含 MPN/制造商/位号/数量/DNP/替代料声明）；
- CPL（含面别、坐标、旋转、封装中心）；
- Gerber/钻孔/层叠/钢网（按路线）；
- DFM/厂方审核记录（若声称已审核）；
- 交叉核对报告；
- 工程文件前后哈希；
- 若声称库存/价格/SMT 可贴：真实渠道查询记录（日期、渠道、C 号、库存、MOQ、可贴状态），否则写 `not_verified`。

**允许的部分通过**

- 只生成候选包、未交叉核对时 `manufacturing.status=partial`；只能写“制造候选资料包已生成，未核对”。
- 缺少 PCB/CPL/Gerber 时 `level_status=blocked`，`blocked_by=["PCB_NOT_IMPLEMENTED"]` 或 `["NO_PCB"]`；不能写“制造资料已核对”。

**禁止的表述**

- “可打样/可贴片/可量产/可下单”；
- “已通过厂方审核/DFM 通过”（无真实审核记录）；
- “库存已核实/价格已确认”（无实时渠道证据）；
- 用原理图快照的坐标/旋转冒充 CPL。

#### 1.3.6 `L6 PROTOTYPE_VERIFIED`（样机功能已验证）

**判定字段**

```json
{
  "level": "PROTOTYPE_VERIFIED",
  "level_index": 6,
  "level_status": "passed",
  "prototype": {
    "build": {"serial": "…", "built_at": "…", "assembly_record": "artifacts/build.md"},
    "firmware": {"version": "…", "sha256": "…"},
    "tests": [
      {
        "id": "T-01",
        "procedure": "…",
        "input": "…",
        "expected": "…",
        "observed": "…",
        "instrument": "…",
        "uncertainty": "…",
        "result": "passed"
      }
    ],
    "sample_size": 1,
    "environment": {"temperature": "…", "supply": "…", "notes": "…"},
    "traces": ["manufacturing.artifacts[0]"]
  }
}
```

条件：

- `build.serial` 非空，且有装配/接线记录；
- `firmware.version` 与 `firmware.sha256` 非空（若适用）；
- `tests` 非空，每项有 `procedure/input/expected/observed/instrument/result`；
- 所有 `result="passed"` 且 `observed` 在声明阈值内；
- `sample_size` 与实际样机数一致；
- `environment` 记录温度、供电、负载、连接等条件；
- `traces` 能追溯到 `L5` 的板版本/制造资料。

**必须证据**

- 样机序列号/装配记录；
- 固件/配置版本与哈希；
- 测试计划与原始测试日志（仪器截图/CSV/照片）；
- 仪器型号、量程、不确定度；
- 测试日期、操作者、环境；
- 失败/异常记录与复测记录。

**允许的部分通过**

- 只测了部分功能/条件时 `prototype.status=partial`；`tests_not_run[]` 列出未测项；只能写“在条件 X 下通过测试 Y；Z 未测”。
- 样机数量不足以支持统计结论时，写 `sample_size` 并限制结论，不能外推到量产。

**禁止的表述**

- “全部功能正常/所有样机通过/量产可用/通过认证/长期可靠/全环境适用”；
- 用一次上电、截图、串口日志代替功能验收；
- 把仿真、离线计算或 mock 数据写成样机实测。

### 1.4 等级推进、作用域与声明

1. **连续推进**：`level_reached` 是同一 `scope` 内从 `L1` 起连续 `passed`（或 `not_applicable` 且有范围说明）的最高级。
2. **作用域**：`scope.kind` 为 `item|page|project|product`；`claims[]` 每项必须带自己的 `scope`。单页证据只能支持 `page` 级，不能支持 `project`/`product` 级。
3. **声明上限**：`claims[].level` 不得超过该 claim 作用域的 `level_reached`。更窄作用域的 claim 可以高于总体 `level_reached`，但必须逐项列 `item_keys`。
4. **部分通过**：某级 `partial` 时，总体只能声明上一级；对该级的已通过子集可单独列 claim，状态仍为 `partial`。
5. **not_applicable**：只允许在 `scope.excluded[]` 明确说明“本次交付不包含该级”时使用；不得用它掩盖失败或未执行。
6. **highest_attempted** 与 `level_reached` 分开记录：尝试过但失败，不等于到达。

示例：某次运行 `L1 passed`、`L2 partial`（3 个器件写入，1 条导线失败）、`L3 not_run`。允许的 claim 是：

```json
{
  "claims": [
    {"level": "PLAN_READY", "status": "passed", "scope": {"kind": "page", "page_uuid": "..."}},
    {"level": "WRITTEN", "status": "partial", "scope": {"kind": "item", "item_keys": ["part-R1", "part-R2", "part-R3"]}}
  ]
}
```

不允许写“该页已写入”或“已核对”。

### 1.5 结果包顶层结构

所有 `eda_exec.py` 子命令输出（stdout JSON）统一为以下外壳；不适用的级用 `status:"not_run"` 填充，不得省略字段。

```json
{
  "schema": "hds-execution-result/1",
  "run_id": "4f3c2a1e-9b7d-4c2a-8f10-2d6e5b7c9a01",
  "command": "apply",
  "protocol_status": "specification_only",
  "level": "READBACK_VERIFIED",
  "level_index": 3,
  "level_status": "passed",
  "level_reached": "READBACK_VERIFIED",
  "highest_attempted": "READBACK_VERIFIED",
  "scope": {
    "kind": "page",
    "project_uuid": "…",
    "schematic_uuid": "…",
    "page_uuid": "…",
    "item_keys": []
  },
  "claims": [
    {"level": "READBACK_VERIFIED", "status": "passed", "scope": {"kind": "page", "page_uuid": "…"}, "evidence_refs": ["art-003", "art-004"]}
  ],
  "preconditions": {},
  "snapshot": {"before": {}, "after": {}},
  "execution": {},
  "verification": {},
  "electrical": {"status": "not_run", "checks": [], "checks_not_run": ["erc", "drc", "netlist_equivalence"]},
  "manufacturing": {"status": "not_run", "artifacts": [], "cross_checks": [], "not_run": ["bom", "cpl", "gerber", "drill"]},
  "prototype": {"status": "not_run", "tests": [], "not_run": ["build", "functional_test"]},
  "persistence": {"state": "saved", "save": {"saved": true}, "reopen": {"status": "not_run"}},
  "evidence": {"manifest": "evidence/run-…/manifest.json", "artifacts": []},
  "limitations": [],
  "not_run": ["erc", "drc", "pcb", "manufacturing", "prototype"],
  "message": {"beginner": "…", "engineer": "…"}
}
```

`read`、`save`、`export` 等不产生交付等级的只读/辅助命令使用：

```json
{
  "schema": "hds-execution-result/1",
  "command": "read",
  "result_kind": "read",
  "level": null,
  "level_status": "not_applicable",
  "claims": []
}
```

`reopen-check` 也不独立定级：它只写入 `persistence.reopen`。只有比较域覆盖 §7.6、`identity.match=true` 且 `reopen.match=true` 时，才能把 `L3` 的 `persistence.state` 置为 `reopened`；否则只能记录 `reopen.status=mismatch/partial`，不得提升等级。`save` 单独成功只证明保存调用成功，不能替代写入或回读。

---

## 2. 快照完整性与可信度

### 2.1 完整性状态枚举

| `integrity.status` | 触发条件 | 允许用途 | 禁止用途 |
|---|---|---|---|
| `complete` | 所有必需 getter 成功；必需集合完整；计数一致；页身份与请求一致；若请求引脚/属性则完整 | 读取、dry-run、写入前条件、`L3` 逐项核对、重开比较 | 不能单独证明电气正确 |
| `truncated` | 引脚预算耗尽、属性超过上限、集合被截断、计数不一致但非致命 | 读取；dry-run 需警告；仅未被截断影响的对象可逐项核对 | 整页“核对通过”；写入涉及截断域的对象 |
| `read_failed` | 必需 getter 抛错、`ok:false`、必需集合缺失、JSON 不可解析 | 仅诊断；保留错误现场 | 任何写入、任何“核对通过”、任何“对象不存在”推断 |
| `timeout` | CLI `invoke` 超时、无完整 JSON 返回 | 仅诊断；必须重新读取 | 任何写入、任何核对、任何“未找到”推断、整批重放 |
| `page_not_active` | 请求页未被激活/当前文档 UUID 不匹配/选择无法唯一解析 | 仅诊断；重新激活并重读 | 导出 PNG/网表、写入、核对、重开比较 |

### 2.2 字段定义

```json
{
  "integrity": {
    "schema_version": 2,
    "status": "complete",
    "captured_at_utc": "2026-10-22T04:34:56.789Z",
    "captured_at_local": "2026-10-22T12:34:56.789+08:00",
    "client_time": "2026-10-22T12:34:56.700+08:00",
    "snapshot_sha256": "…",
    "content_sha256": "…",
    "counts_consistent": true,
    "counts": {
      "components": 60,
      "parts": 16,
      "netflags": 27,
      "netports": 16,
      "other_components": 1,
      "wires": 44,
      "attributes": 0
    },
    "required_collections": ["parts", "netflags", "netports", "wires"],
    "read_errors": [],
    "truncated": [],
    "pins": {"requested": true, "complete": true, "used": 56, "budget": 6000},
    "attributes": {"requested": false, "included": false, "complete": null, "count": null, "truncated": false},
    "active_document": {"uuid": "f6d41a58df3fa849", "document_type": 1, "confirmed": true},
    "page_identity": {
      "project_uuid": "…",
      "schematic_uuid": "7156417783355f32",
      "page_uuid": "f6d41a58df3fa849",
      "selection_basis": "page_uuid"
    }
  }
}
```

`read_errors[]` 条目：

```json
{
  "path": "parts[3].designator",
  "primitive_id": "84931dadefea5b69",
  "getter": "getState_Designator",
  "error": "TypeError: ...",
  "severity": "fatal"
}
```

- `severity="fatal"`：该对象/集合无法用于核对，整体 `integrity.status="read_failed"`。
- `severity="degraded"`：字段缺失但对象其余字段可用，整体 `integrity.status="truncated"`，并在 `truncated[]` 写明影响域。
- 任何 getter 失败不得折叠成 `null`/`[]` 后继续；必须记录并影响完整性判定。

### 2.3 判定规则

1. **空值语义**：`null` 表示“不可用/读取失败”；`[]` 表示“已确认空”。必需字段为 `null` 时，该对象不能用于 `L3`。例外：`attributes.complete=null` 表示“未请求属性”，不是读取失败，必须结合 `attributes.requested=false` 判断；`counts.attributes=null` 同理。
2. **计数一致**：`counts.components == counts.parts + counts.netflags + counts.netports + counts.other_components`。`other_components` 用于容纳未分类图元，避免把正常图元误判为缺失（F1 实测 `components=60`，`parts+netflags+netports=59`，另有 1 个其他图元）。
3. **`attributes_complete` 三态**：未请求时必须是 `null`，不能是 `true`；请求但超过 500 条时是 `false`，并列入 `truncated[]`。
4. **`pins_complete`**：引脚预算耗尽时为 `false`，必须记录 `pins_used`、`pins_budget`，受影响器件列入 `truncated[]`。
5. **页身份**：`page_identity.page_uuid` 必须等于请求页；`active_document.confirmed=true` 且 UUID 一致，否则 `page_not_active`。
6. **集合读取失败**：`parts`/`netflags`/`netports`/`wires` 任一必需集合读取失败时，不得返回空数组冒充“没有对象”；应返回 `null` 或缺失，并置 `read_failed`。
7. **去重**：同一 `primitive_id` 出现在多个集合、designator 重复、同一 net+position 的重复 flag/port，都必须进入 `integrity.anomalies[]`，不能静默合并。

### 2.4 快照哈希与时间

- `snapshot_sha256`：对完整快照 JSON（含 `primitive_id`、`captured_at` 等全部字段，去除 `snapshot_sha256` 自身）做规范化 JSON 后的 SHA256，用于证据完整性。
- `content_sha256`：对语义投影做规范化 JSON 后的 SHA256，用于“内容是否漂移”。投影规则见 §7.7；必须排除易变的 `primitive_id`，保留 `unique_id`、位号、库身份、坐标（保留 3 位小数）、旋转、镜像、BOM/PCB 标志、网络、方向、类型、归一化线段。
- `captured_at_utc` 由宿主 Python 在收到快照后生成；`client_time` 可选，仅作参考，不用于排序或 freshness 判断。
- `max_age_ms` 默认 300000（5 分钟）；`apply` 必须在写入前重新读取，不依赖计划生成时的旧快照。计划中的 `based_on_snapshot_content_sha256` 必须与写入前快照的 `content_sha256` 相等；不等即 `SNAPSHOT_DRIFT`。
- `snapshot_sha256` 用于 manifest 校验；`content_sha256` 用于对账、写入前条件和重开比较。两者不得混用。

### 2.5 不完整快照使用矩阵

| 完整性状态 | 只读 `read` | `apply --dry-run` | `apply` 写入 | `L3` 核对 | 导出 PNG | 导出网表 | `reopen-check` |
|---|---|---|---|---|---|---|---|
| `complete` | 允许 | 允许 | 允许（其余前置通过） | 允许 | 允许（页已激活） | 允许（页已激活） | 允许 |
| `truncated` | 允许，标注 | 允许，标注 | **禁止**涉及截断域；其余对象需 `snapshot_scope_exclusions` | 仅未受影响对象可逐项核对 | 允许，但需页激活 | 允许，但需页激活 | 仅未受影响对象；总体不得 `match` |
| `read_failed` | 仅诊断 | 禁止 | 禁止 | 禁止 | 禁止 | 禁止 | 禁止 |
| `timeout` | 仅诊断 | 禁止 | 禁止 | 禁止 | 禁止 | 禁止 | 禁止 |
| `page_not_active` | 仅诊断 | 禁止 | 禁止 | 禁止 | 禁止 | 禁止 | 禁止 |

**规则**：不完整快照不得支持“核对通过”。`truncated` 的部分通过必须写明截断域和未覆盖对象；`read_failed`/`timeout`/`page_not_active` 只能用于诊断和重试，不能用于任何完成声明。

---

## 3. 写入前条件检查

### 3.1 检查清单

| # | 检查 | 必需字段 | 通过条件 | 失败码 | 失败时 |
|---:|---|---|---|---|---|
| 1 | 工程身份 | `project.uuid` | 期望 UUID 与实测 UUID 相等，且 `project.path` 存在 | `PROJECT_MISMATCH` | 阻断，零写入 |
| 2 | 工程版本 | `project.file_sha256_before` | 与计划/授权副本一致；写入前记录 | `PROJECT_REVISION_MISMATCH` | 阻断 |
| 3 | 页 UUID | `page.page_uuid` | 显式给出且能唯一解析；写入禁止 `current:true` | `PAGE_NOT_RESOLVED` | 阻断 |
| 4 | 页激活 | `active_document.uuid` | 等于请求页 UUID，`confirmed=true` | `PAGE_NOT_ACTIVE` | 阻断 |
| 5 | 快照完整 | `snapshot.before.integrity.status` | `complete` | `SNAPSHOT_INCOMPLETE` | 阻断 |
| 6 | 快照漂移 | `snapshot.before.content_sha256` | 等于 `plan.based_on_snapshot_content_sha256` | `SNAPSHOT_DRIFT` | 阻断；重新读+对账 |
| 7 | 计划有效 | `plan.validated/sha256` | `true` 且哈希非空 | `PLAN_INVALID` | 阻断 |
| 8 | 位号唯一 | `designators`（§3.2） | 工程级无冲突；或显式 `page_only` 并限制声明 | `DESIGNATOR_CONFLICT` | 阻断 |
| 9 | 会话来源 | `session.origin` | `cli` 且由本桥打开；`user` 需显式授权 | `USER_SESSION_NOT_AUTHORIZED` | 阻断 |
| 10 | 单写者 | `write_lock` | 无其他写锁/写会话 | `CONCURRENT_WRITER` | 阻断 |
| 11 | 能力支持 | `capabilities` | 计划中的 op 均受支持 | `UNSUPPORTED_OP` | 阻断 |
| 12 | 保存策略 | `persistence.mode` | `--project` 临时会话必须 `--save` 或显式保留会话 | `NEEDS_SAVE` | 阻断（退出 2） |

检查结果写入：

```json
{
  "preconditions": {
    "status": "passed",
    "checked_at": "2026-10-22T04:35:01.123Z",
    "project": {"expected_uuid": "…", "observed_uuid": "…", "match": true, "path": "C:/work/copy.eprj2", "file_sha256_before": "…"},
    "page": {"requested": {"page_uuid": "f6d41a58df3fa849"}, "resolved": {"schematic_uuid": "7156417783355f32", "page_uuid": "f6d41a58df3fa849", "page_name": "P1"}, "basis": "page_uuid", "match": true},
    "snapshot": {"path": "artifacts/snapshot-before.json", "sha256": "…", "content_sha256": "…", "captured_at_utc": "…", "age_ms": 1200, "integrity": "complete"},
    "plan": {"path": "artifacts/plan.json", "sha256": "…", "based_on_snapshot_content_sha256": "…", "match": true},
    "designators": {"scope": "project", "checked": true, "pages_scanned": ["…"], "conflicts": []},
    "session": {"id": "…", "origin": "cli", "owned": true, "project_uuid": "…"},
    "write_lock": {"acquired": true, "owner": "run-…", "expires_at": "…"},
    "failed_checks": []
  }
}
```

失败时：

```json
{
  "preconditions": {
    "status": "failed",
    "failed_checks": [
      {"check": "snapshot_drift", "code": "SNAPSHOT_DRIFT", "expected": "abc…", "observed": "def…", "action": "re-read and reconcile"}
    ]
  },
  "status": "precondition_failed",
  "writes_sent": false
}
```

### 3.2 工程级位号唯一性

位号唯一性是**工程级**，不是当前页级。写入前必须：

1. 枚举工程内所有原理图页（`dmt_Schematic.getAllSchematicsInfo`）；
2. 逐页读取 `parts[].designator/unique_id/primitive_id`，建立索引；
3. 检查计划内部重复：同一 `designator` 出现在多个 create/modify 目标 → `DESIGNATOR_PLAN_DUPLICATE`；
4. 检查 create 占用：目标 `designator` 在任一页已存在（且不是本次同一对象）→ `DESIGNATOR_PROJECT_EXISTS`；
5. 检查 modify 撞车：目标新位号被另一个非目标对象占用 → `DESIGNATOR_MODIFY_COLLISION`；
6. 检查未解析位号：`designator` 为 `null`、空串、`R?`、`C?` 等 → `DESIGNATOR_UNRESOLVED`；
7. 检查计划内 modify 的旧值：修改位号时必须同时记录 `expected_old_designator`，回读时比对。

```json
{
  "designators": {
    "scope": "project",
    "checked_at": "2026-10-22T04:35:00.000Z",
    "pages_scanned": ["7156417783355f32/f6d41a58df3fa849", "…"],
    "index": {
      "R1": [{"page_uuid": "…", "primitive_id": "…", "unique_id": "…"}],
      "C1": [{"page_uuid": "…", "primitive_id": "…", "unique_id": "…"}]
    },
    "plan_conflicts": [],
    "project_conflicts": [],
    "unresolved": [],
    "project_unique": true
  }
}
```

**当前实现差距**：`reconcile` 只使用当前页快照（`eda_exec.py:917`），没有跨页扫描；因此下一轮实现前，只能写 `scope:"page_only"`、`project_unique:null`，并在 `limitations` 中写“未验证工程级位号唯一性”。不得宣称工程级唯一。

### 3.3 冲突与部分成功语义

冲突条目必须包含 `key`、`reason`、`expected`、`observed`、`severity`、`blocking`：

```json
{
  "key": "part-R1",
  "reason": "designator_project_exists",
  "expected": {"designator": "R1", "page_uuid": "new-page"},
  "observed": {"designator": "R1", "page_uuid": "existing-page", "primitive_id": "…"},
  "severity": "high",
  "blocking": true
}
```

冲突原因枚举：

| reason | 含义 | 默认阻断 |
|---|---|---|
| `ambiguous_match` | 多个候选匹配同一身份 | 是 |
| `part_identity_changed` | 已有器件的型号与计划不符 | 是 |
| `supplier_identity_changed` | 供应商/C 号与计划不符 | 是 |
| `designator_plan_duplicate` | 同一计划内位号重复 | 是 |
| `designator_project_exists` | 新位号已被工程内其他页占用 | 是 |
| `designator_modify_collision` | 改位号撞上其他对象 | 是 |
| `wire_segment_net_conflict` | 导线与异网线段重叠 | 是 |
| `stale_snapshot` | 计划依据的快照内容哈希与当前不一致 | 是 |
| `page_identity_changed` | 请求页与实际页不一致 | 是 |
| `snapshot_incomplete` | 快照不完整 | 是 |
| `unsupported_op` | 本桥不支持该操作（如网络标签、PCB） | 是 |
| `user_session` | 目标是用户会话且未授权 | 是 |

运行状态语义：

| `status` | 写入情况 | 允许声明 | 禁止声明 |
|---|---|---|---|
| `dry_run` | 0 | “已对账，未写入” | “已写入” |
| `blocked` | 0（有冲突，未 `--allow-partial`） | “被冲突阻断，未写入” | “部分完成” |
| `preflight_failed` | 0（库器件未解析） | “预检失败，未写入” | “已尝试写入” |
| `partial` | >0 且 <计划数，或存在失败 key | “已写入 X 项；Y 项失败/冲突/未执行” | “页面已完成” |
| `verified` | 计划项全部写入且回读一致 | “已写入并回读核对” | “电气正确” |
| `save_failed` | 已写入/已验证但保存失败 | “内存中已验证；保存失败” | “已持久化” |
| `timeout` | 未知 | “结果未知，已停止，需回读” | “未写入”/“已写入” |
| `unknown` | 未知（传输/调用错误） | “结果未知，需回读” | 任何完成声明 |

**部分成功规则**

1. 默认冲突零写入；只有显式 `--allow-partial` 才执行非冲突项。
2. 部分写入后**禁止自动保存**，除非所有已执行项 `verification=verified`；否则 `persistence.state="in_memory"`，并提示先处理失败项。
3. `execution.results[].ok=false` 的 key 进入 `failed_keys`；必须回读全部 key，不能只读成功项。
4. 用户在执行期间手动改图：立即停止后续动作，重新读快照，报告差异；不得覆盖用户修改。
5. `timeout`/`unknown`：先回读；回读成功前不得再次写入；不得整批重放（§4.5）。

示例（部分成功）：

```json
{
  "status": "partial",
  "level": "WRITTEN",
  "level_status": "partial",
  "execution": {
    "state": "partial",
    "written_keys": ["part-R1", "part-R2"],
    "failed_keys": ["wire-w1"],
    "conflict_keys": ["part-R3"],
    "unknown_keys": []
  },
  "persistence": {"state": "in_memory", "save": {"not_attempted": "verification not passed"}},
  "claims": [
    {"level": "WRITTEN", "status": "partial", "scope": {"kind": "item", "item_keys": ["part-R1", "part-R2"]}}
  ],
  "limitations": ["wire-w1 未写入", "part-R3 冲突未写入", "未保存"]
}
```

### 3.4 失败返回与退出码

| 退出码 | 含义 | 适用 |
|---:|---|---|
| `0` | 操作完成，且没有需要复核的冲突/不一致 | `read`、`dry_run` 无冲突、`verified` 且保存成功 |
| `1` | 冲突、部分、验证不一致、保存失败 | `blocked`、`partial`、`failed`、`save_failed` |
| `2` | 输入/前置条件不合法或不安全 | `INVALID_INPUT`、`PRECONDITION_FAILED`、`NEEDS_SAVE`、用户会话未授权 |
| `3` | CLI 不可用或命令在结果前失败 | `EDA_UNAVAILABLE`、`EDA_COMMAND_FAILED` |
| `4` | 调用超时；对象可能存在 | `EDA_TIMEOUT`；必须回读，禁止重放 |

前置条件失败统一输出：

```json
{
  "schema": "hds-execution-result/1",
  "status": "precondition_failed",
  "level": "PLAN_READY",
  "level_status": "blocked",
  "writes_sent": false,
  "error": {"code": "SNAPSHOT_DRIFT", "message": "plan snapshot does not match live content", "detail": {}},
  "failed_checks": [],
  "message": {"beginner": "…", "engineer": "…"}
}
```

---

## 4. 重试与幂等

### 4.1 状态机

```text
read(before, complete)
  -> reconcile(plan)
  -> preconditions
  -> apply(actions)                         # 唯一写入口
  -> read(after, complete)
  -> verify(item-by-item, field-by-field)
  -> [save] -> [reopen-check]

timeout/unknown:
  apply(state=unknown)
  -> read(after)                            # 必须先做
  -> reconcile(plan vs after)
  -> 仅补 missing keys（新 attempt）
  -> read/verify
```

### 4.2 只补差异

1. 写入失败/超时/部分成功后，先读取完整快照；
2. 用 `reconcile(after, plan)` 重新对账，得到 `skip/modify/create/conflict`；
3. 只对 `create`（且确认不存在）或 `modify`（旧值仍匹配）发动作；
4. 不重发 `skip`，不重发已 `verified` 的 key；
5. 任何 `conflict` 停止并报告，不猜；
6. 新 attempt 记录 `supersedes`、`reason`、新的 `based_on_snapshot_content_sha256`。

### 4.3 重复创建风险

| 对象 | 创建动作 | 重复风险 | 幂等键 | 检测方式 | 允许自动重试 |
|---|---|---|---|---|---|
| 器件 | `create_part` | 同位号/同 unique_id/同位置重复器件 | `designator` + `unique_id` + 库身份 | 完整快照按位号/unique_id/位置查重 | 仅当回读确认不存在且位号工程级空闲 |
| 电源/地标记 | `create_net_flag` | 同网名同位置重复标记 | `net` + `round(x,3)` + `round(y,3)` + `type` | 快照按 net+position 查重；type 不符走 modify | 仅当不存在同 net+position |
| 网络端口 | `create_net_port` | 同网名同位置重复端口 | `net` + `round(x,3)` + `round(y,3)` + `direction` | 快照按 net+position 查重；direction 不符走 modify | 仅当不存在同 net+position |
| 导线 | `create_wire` | 重复/重叠线段；编辑器合并/拆分 | `net` + 归一化线段集合 | 按网名+线段覆盖判断 | 仅当缺失线段且无跨网重叠 |
| 器件修改 | `modify_part` | 不重复创建，但会覆盖用户修改 | `primitive_id` + 旧值 | 写入前后旧值/新值比对 | 仅当旧值仍匹配且新值未生效 |
| 保存 | `save` | 重复保存通常安全 | 内容哈希 | 保存后回读 | 允许重试，但不得在 partial 时保存 |
| 导出/读取 | `read/export` | 只读；页未激活会导出错页 | 页 UUID | `active_document.confirmed` | 允许重试（需重新激活） |
| 网络标签 | `create_net_label` | 本桥未实现；重复写入无幂等保证 | 无 | 无 | **禁止写入** |

### 4.4 重试策略

- **读重试**：最多 3 次，间隔 1s/2s；保留每次的错误码到 `errors[]`，不得把 `EDA_TIMEOUT`/`page_not_found` 折叠成统一的 `EDA_PROJECT_NOT_READY`（原始错误必须留在 `errors[].last`）。
- **写重试**：默认不自动重试。只有“完整回读 + 对账确认 missing + 前置条件重新通过”才允许新 attempt。
- **超时**：`state="unknown"`，`retry.allowed=false`，`required_action="read_after"`；回读完成前不得再次写入。
- **部分成功**：只补 `failed_keys`/`missing_keys`，不重发 `written_keys`。
- **幂等令牌**：`apply_id`（UUID）+ `attempt`（从 1 递增）+ `plan_sha256` + `based_on_snapshot_content_sha256`；同一 `apply_id` 的重复调用必须能被识别为同一意图。
- **并发**：同一工程/页只允许一个写者；`write_lock` 获取失败 → `CONCURRENT_WRITER`，零写入。
- **用户会话**：默认只写 `origin:"cli"` 且由本桥打开的会话；写 `origin:"user"` 会话必须显式 `--allow-user-session`，并在证据中记录用户授权语句/时间。

超时结果示例：

```json
{
  "status": "timeout",
  "execution": {
    "apply_id": "…",
    "attempt": 1,
    "state": "unknown",
    "invoked_at": "2026-10-22T04:40:00.000Z",
    "retry": {
      "allowed": false,
      "reason": "timeout_result_unknown",
      "required_action": "read_after"
    }
  },
  "writes_sent": true,
  "writes_confirmed": false
}
```

重试 attempt 示例：

```json
{
  "execution": {
    "apply_id": "…",
    "attempt": 2,
    "supersedes": "attempt-1",
    "state": "completed",
    "reason": "missing_after_readback",
    "missing_keys": ["part-R1"],
    "retry": {"allowed": true, "reason": "missing_after_readback"}
  }
}
```

### 4.5 禁止整批重放

以下任一情况禁止把原计划整批重发：

1. `timeout` 或 `unknown`，尚未完成 `read_after`；
2. `after` 快照不是 `complete`；
3. 页/工程身份与写入前不一致；
4. 检测到用户修改或 `SNAPSHOT_DRIFT`；
5. 任一 `create_*` 已成功但回读未完成（可能产生重复对象）；
6. 计划哈希或 `based_on_snapshot_content_sha256` 已变化；
7. 存在其他写者/写锁；
8. 上一次 attempt 为 `partial`，未逐 key 对账。

正确做法：读取 → 对账 → 只补差异 → 新 attempt → 回读 → 验证。不能确认时保持 `unknown`/`blocked`，交人工检查。

---

## 5. 证据 manifest 格式

### 5.1 目录布局

```text
evidence/<run-id>/
  manifest.json                 # 机器事实，唯一清单
  interpretation.json           # 人工解释，引用 manifest artifact id
  commands/
    cmd-001.stdout.json
    cmd-001.stderr.txt
    cmd-002.stdout.json
  artifacts/
    plan.json
    snapshot-before.json
    apply-result.json
    snapshot-after.json
    reopen-check.json
    schematic.png
    schematic.net
    erc-report.json
    bom.csv
    cpl.csv
    gerber.zip
    ...
```

所有 `path` 必须是 run 目录内的相对路径；不得使用 `<scratch>`、`<path>`、`C:/Users/...` 之类占位或未脱敏绝对路径作为交付路径。外部文件必须复制进 run 目录，或在 `external` 字段记录绝对路径 + SHA256 + 来源说明。

### 5.2 `manifest.json` 字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `schema` | string | 是 | `hds-evidence-manifest/1` |
| `manifest_id` | uuid | 是 | 本次证据包 id |
| `run_id` | uuid | 是 | 与结果包一致 |
| `created_at` | ISO8601 | 是 | UTC，含时区 |
| `project` | object | 是 | name/uuid/path/file_sha256_before/file_sha256_after/revision/pcb_uuid/schematic_uuids |
| `tool` | object | 是 | name/version/bridge_path/bridge_sha256/python |
| `environment` | object | 是 | os/mode（online/half_offline/offline）/session_origin/locale/timezone |
| `commands` | array | 是 | id/argv/cwd/started_at/finished_at/duration_ms/exit_code/stdout/stdout_sha256/stderr/stderr_sha256 |
| `artifacts` | array | 是 | id/role/path/sha256/bytes/media_type/generated_by/generated_at/raw |
| `levels` | array | 是 | level/status/scope/evidence_refs/verifier/notes |
| `checks` | object | 是 | all_hashed/paths_relative/no_placeholders/timestamps_present/tool_version_present/project_bound |
| `manifest_sha256` | string | 是 | 对去掉本字段后的规范化 JSON 计算 |

`artifacts[].role` 枚举：

`plan`、`snapshot_before`、`snapshot_after`、`apply_result`、`save_result`、`reopen_check`、`netlist_before`、`netlist_after`、`erc_report`、`drc_report`、`png_full`、`png_crop`、`bom`、`cpl`、`gerber`、`drill`、`stackup`、`dfm_report`、`firmware`、`test_log`、`photo`、`measurement`、`other`。

示例（节选，保持合法 JSON）：

```json
{
  "schema": "hds-evidence-manifest/1",
  "manifest_id": "6b1f1d7e-3c2a-4a9b-9e10-8d7c6b5a4f32",
  "run_id": "4f3c2a1e-9b7d-4c2a-8f10-2d6e5b7c9a01",
  "created_at": "2026-10-22T04:50:00.000Z",
  "project": {
    "name": "F1-USB-MCU-C",
    "uuid": "…",
    "path": "copy.eprj2",
    "file_sha256_before": "…",
    "file_sha256_after": "…",
    "revision": "editor-save-1",
    "pcb_uuid": null,
    "schematic_uuids": ["7156417783355f32"]
  },
  "tool": {
    "name": "lceda-pro",
    "version": "4.1.78.34f5b8d9",
    "bridge_path": "design-hardware/scripts/eda_exec.py",
    "bridge_sha256": "…",
    "python": "3.11.9"
  },
  "environment": {
    "os": "Windows 11 10.0.26200",
    "mode": "half_offline",
    "session_origin": "cli",
    "locale": "zh-CN",
    "timezone": "Asia/Shanghai"
  },
  "commands": [
    {
      "id": "cmd-001",
      "argv": ["python", "design-hardware/scripts/eda_exec.py", "read", "--session", "…", "--page", "f6d41a58df3fa849", "--output", "artifacts/snapshot-before.json"],
      "cwd": "C:/work/hds-round3",
      "started_at": "2026-10-22T04:35:00.000Z",
      "finished_at": "2026-10-22T04:35:02.500Z",
      "duration_ms": 2500,
      "exit_code": 0,
      "stdout": "commands/cmd-001.stdout.json",
      "stdout_sha256": "…",
      "stderr": null,
      "stderr_sha256": null
    }
  ],
  "artifacts": [
    {"id": "art-001", "role": "plan", "path": "artifacts/plan.json", "sha256": "…", "bytes": 12000, "media_type": "application/json", "generated_by": "human", "generated_at": "2026-10-22T04:30:00.000Z", "raw": true},
    {"id": "art-002", "role": "snapshot_before", "path": "artifacts/snapshot-before.json", "sha256": "…", "bytes": 180000, "media_type": "application/json", "generated_by": "cmd-001", "generated_at": "2026-10-22T04:35:02.500Z", "raw": true},
    {"id": "art-003", "role": "apply_result", "path": "artifacts/apply-result.json", "sha256": "…", "bytes": 90000, "media_type": "application/json", "generated_by": "cmd-002", "generated_at": "2026-10-22T04:40:00.000Z", "raw": true}
  ],
  "levels": [
    {"level": "PLAN_READY", "status": "passed", "scope": {"kind": "page", "page_uuid": "f6d41a58df3fa849"}, "evidence_refs": ["art-001"], "verifier": "machine", "notes": ""},
    {"level": "WRITTEN", "status": "passed", "scope": {"kind": "page", "page_uuid": "f6d41a58df3fa849"}, "evidence_refs": ["art-002", "art-003"], "verifier": "machine", "notes": ""}
  ],
  "checks": {
    "all_hashed": true,
    "paths_relative": true,
    "no_placeholders": true,
    "timestamps_present": true,
    "tool_version_present": true,
    "project_bound": true
  },
  "manifest_sha256": "…"
}
```

### 5.3 原始证据与人工解释

- `manifest.json` **只允许机器可复核事实**：路径、哈希、命令、退出码、时间、版本、计数、字段值。不得写“设计正确”“基本完成”“应该没问题”等判断。
- `interpretation.json` 单独存放人的判断：

```json
{
  "schema": "hds-evidence-interpretation/1",
  "manifest_sha256": "…",
  "author": "…",
  "created_at": "2026-10-22T05:00:00.000Z",
  "claims": [
    {
      "level": "WRITTEN",
      "status": "passed",
      "scope": {"kind": "page", "page_uuid": "f6d41a58df3fa849"},
      "artifact_refs": ["art-002", "art-003"],
      "statement": "16 个器件、27 个电源标记、16 个端口、34 条归一化线段已写入；尚未逐项回读。"
    }
  ],
  "not_verified": ["readback", "erc", "drc", "pcb", "manufacturing", "prototype"],
  "limitations": ["半离线会话", "未做全在线 GUI 复验"],
  "notes": "人写的背景，不替代原始证据。"
}
```

规则：

1. 每个 claim 必须有 `artifact_refs`，且引用的 artifact 存在于 manifest；
2. claim 的 `level/status` 不得高于 manifest 的 `levels[]`；
3. `interpretation.json` 的 `manifest_sha256` 必须与 manifest 一致；不一致时以 manifest 为准；
4. 人的测量记录可以作为原始证据，但必须有 `source:"human"`、操作者、时间、仪器、原始文件与 SHA256；不能只有结论；
5. 人工解释不得修改 manifest 中的数字；发现数字错误应重新生成 manifest，而不是在解释里“修正”。

### 5.4 生成与校验

建议由 `eda_exec.py` 提供（当前 `NOT IMPLEMENTED`）：

```bash
python design-hardware/scripts/eda_exec.py manifest --run-dir evidence/run-… --project copy.eprj2
python design-hardware/scripts/eda_exec.py manifest verify --run-dir evidence/run-…
```

校验清单：

1. 每个 artifact 文件存在，`sha256`/`bytes` 与 manifest 一致；
2. 每个 command 的 stdout/stderr 存在且哈希一致；
3. `paths_relative=true`，无 `<scratch>`/`<path>` 占位；
4. `timestamps_present=true`，时间可解析且带时区；
5. `tool_version_present=true`，客户端版本与 `doctor` 一致；
6. `project.file_sha256_before/after` 与工程副本实际哈希一致；
7. `levels[].evidence_refs` 均能解析到 artifact；
8. `manifest_sha256` 重算一致；
9. `interpretation.json` 的引用和哈希一致；
10. 不通过时退出 1，并列出失败项，不得输出 `ok`。

### 5.5 与当前证据的差距

现有 F1 证据 `docs/evidence/f1-2026-10-22/` 只有 `README.md` 对 `schematic.png`、`schematic.net` 给出 SHA256；`apply-result.json` 的 `plan` 是 `<scratch>` 路径，`reopen-check.json` 的 `closed_session=null`，没有覆盖全部文件的 manifest，也没有工具版本/命令/环境的结构化记录。这属于**证据链不完整**（GAP），不代表 F1 的结论一定错误；下一轮任何新证据包必须按 §5.2 生成 manifest，旧证据只能作为历史材料引用并标注其边界。

---

## 6. 新手与工程师双层输出

### 6.1 `message` 结构

每个结果包必须包含：

```json
{
  "message": {
    "code": "READBACK_VERIFIED_PASSED",
    "beginner": "原理图已经写入并逐项读回核对：16 个器件、27 个电源标记、16 个端口都在。下一步：导出网表做电气检查。注意：DRC/ERC 还没做。",
    "engineer": "READBACK_VERIFIED passed | page f6d41a58df3fa849 | parts 16/16, netflags 27/27, netports 16/16, wire segments 34/34 | verification.status=verified | designator_scope=page_only | electrical=not_run | evidence=manifest.json#art-003,art-004",
    "next_action": {
      "code": "RUN_ERC_DRC",
      "owner": "agent",
      "text": "在已保存的工程副本上运行 ERC/DRC，并导出网表做引脚-网络比对。",
      "command": null,
      "note": "当前 eda_exec.py 未实现 drc/erc；需使用客户端 API、其他执行工具或人工执行，并在证据中记录工具与版本。"
    },
    "limitations": ["netport direction/rotation 未比对", "未做 PCB/制造/样机"],
    "forbidden_phrases_removed": ["全部正确", "没有问题", "可生产"]
  }
}
```

字段说明：

- `code`：稳定的机器码，供 UI/测试使用；
- `beginner`：面向非工程师，≤200 个中文字符，最多一个下一步动作，必须包含至少一个限制；
- `engineer`：面向工程师，包含等级、状态、作用域、计数、关键 ID、证据引用、限制；
- `next_action.owner`：`agent|user|none`；`user` 时必须给一个可观察的成功标志；
- `limitations`：与结果包顶层 `limitations` 一致；
- `forbidden_phrases_removed`：记录被替换的过度声明，便于审查。

### 6.2 状态到文本映射

| `level_status` | 新手层前缀 | 工程师层前缀 | 允许 | 禁止 |
|---|---|---|---|---|
| `passed` | “已完成/已通过（该级）” | `LEVEL passed` | 与等级相符的完成表述 | 超出等级的“电气正确/可生产/量产” |
| `partial` | “部分完成（仅 X）” | `LEVEL partial` | 列出已通过子集 | “基本完成/全部完成/只剩一点” |
| `not_run` | “还没做” | `LEVEL not_run` | 明确下一步 | “默认没问题/应该可以” |
| `blocked` | “被 X 挡住，暂时做不了” | `LEVEL blocked | blocked_by=[…]` | 说明阻塞与解阻条件 | “失败/已完成” |
| `failed` | “这一步失败了：X” | `LEVEL failed | failure_kind=…` | 给失败现象与复现 | “小问题/不影响使用” |
| `not_applicable` | “这次不需要做 X” | `LEVEL not_applicable | reason=…` | 说明范围 | 用它掩盖未执行 |

### 6.3 六级通过示例

> 以下仅示范“到达该级时应该怎样说”，不代表当前桥已支持 ERC/DRC、PCB、制造或样机；当前能力状态见 §7.3。L4 及以上的检查/测试可由客户端 API、其他执行工具或人工完成，但必须按 §5 记录工具、版本、原始证据与时间。

**L1**

- 新手：`方案和元件清单已经准备好，还没有写进 EDA。下一步：确认工程副本后开始写入。注意：这只是方案，不是已完成的图纸。`
- 工程师：`PLAN_READY passed | plan sha256=… | 0 writes | preconditions=not_checked | evidence=manifest.json#art-001`

**L2**

- 新手：`已经写进 EDA 了，但还没有逐项读回来核对。下一步：回读并逐项检查。注意：现在还不能说“改好了”。`
- 工程师：`WRITTEN passed | actions=93, failed=0, conflicts=0 | persistence=in_memory | readback=not_run | evidence=manifest.json#art-002,art-003`

**L3**

- 新手：`已经写入并逐项读回核对：16 个器件、27 个电源标记、16 个端口、34 段导线都对上了。下一步：做 ERC/DRC 和网表检查。注意：这不代表电路设计一定正确。`
- 工程师：`READBACK_VERIFIED passed | page f6… | parts 16/16, netflags 27/27, netports 16/16, segments 34/34 | fields_compared=12 | electrical=not_run | designator_scope=page_only | evidence=manifest.json#art-003,art-004`

**L4**

- 新手：`电气检查已经跑完：ERC 和网表比对通过，DRC 也跑了。下一步：准备制造资料。注意：检查通过不等于可生产。`
- 工程师：`ELECTRICAL_CHECKED passed | erc=0 unwaived, drc=0 unwaived, netlist_equivalence=pass | rules_sha256=… | based_on=… | manufacturing=not_run | evidence=manifest.json#art-005..007`

**L5**

- 新手：`制造资料已经核对：BOM、坐标、Gerber、钻孔和层叠互相对得上。下一步：确认渠道和下单授权。注意：还没有下单，也没有厂方审核。`
- 工程师：`MANUFACTURING_VERIFIED passed | bom/cpl/gerber/drill/stackup cross-checks=5/5 | project_sha256=… | pcb_uuid=… | orders.placed=false | channel=not_verified | evidence=manifest.json#art-010..015`

**L6**

- 新手：`样机功能已经验证：在记录的供电和环境下，测试 T-01..T-06 全部达到阈值。下一步：记录限制并决定是否进入小批。注意：这只是一台样机的结果，不代表量产。`
- 工程师：`PROTOTYPE_VERIFIED passed | sample_size=1 | fw sha256=… | tests 6/6 passed | environment=… | traces=manufacturing.artifacts[0] | limitations=single sample, room temperature only | evidence=manifest.json#art-020..024`

### 6.4 双层表达规则

1. **事实同源**：两层都从同一 `level`/`level_status`/`limitations` 生成；不得一层说“通过”、另一层说“失败”。
2. **禁止越级**：新手层不得出现高于 `level_reached` 的词（如 L3 时说“电气没问题”）。
3. **限制必须出现**：新手层至少一个限制；工程师层列出全部 `not_run`/`limitations`。
4. **下一步唯一**：新手层只给一个下一步动作；工程师层可给命令但不得堆流程。
5. **不用行话**：新手层避免 `ERC/DRC/CPL/Gerber/unique_id` 等术语，必要时用“电气检查/制造资料”替代；工程师层保留精确术语。
6. **不诱导**：不得用“只需点击下一步”“马上就好”等话术掩盖阻塞；阻塞时给解阻条件。
7. **语言**：默认中文；字段名、命令、路径保持英文；不使用 emoji。

---

## 7. `eda_exec.py` 实现映射

### 7.1 CLI 扩展（提案；当前 `NOT IMPLEMENTED`）

| 命令 | 新增参数 | 输出/行为 |
|---|---|---|
| `read` | `--expect-project-uuid`、`--expect-page-uuid`、`--include-attributes`、`--max-pins` | 输出 `integrity`；UUID 不符返回 `PROJECT_MISMATCH`/`PAGE_MISMATCH` |
| `apply` | `--expect-project-uuid`、`--expect-page-uuid`、`--based-on-snapshot`、`--apply-id`、`--attempt`、`--manifest-dir`、`--allow-user-session`、`--allow-unrelated-drift` | 先做 §3 条件检查；输出 `preconditions`、`execution`、`level` |
| `save` | `--expect-project-uuid`、`--expect-page-uuid` | 保存前校验页身份；输出 `save.saved` 与保存后 `content_sha256` |
| `reopen-check` | `--expect-project-uuid`、`--expect-page-uuid`、`--compare-domains` | 比较域含 netports/attributes/mirror/BOM/PCB 标志；缺快照文件返回 `INVALID_INPUT` 而非 traceback |
| `manifest` | `--run-dir`；`manifest verify --run-dir` | 生成/校验 §5 的 manifest |
| `drc` / `erc` | `--session`、`--page`、`--output` | 当前未实现；实现前 `doctor` 必须保持 `not_implemented_in_this_adapter` |

参数命名可调整，但字段语义不得改变。所有命令必须输出 §1.5 的统一外壳；错误也必须是 JSON，不得抛 Python traceback。

### 7.2 函数级改动

| 位置 | 改动 |
|---|---|
| `SNAPSHOT_JS`（`eda_exec.py:431-565`） | 用 `readField(obj, getter, path)` 收集 `read_errors[]`；`safe()`/`safeAsync()` 不再把异常折叠为 `null/[]` 后静默继续；增加 `integrity`、`active_document`、`page_identity`、`captured_at`、`content_sha256`；`attributes_complete` 未请求时为 `null` |
| `read_snapshot`（`:1218-1223`） | 校验 `integrity.status`；非 `complete` 抛 `EdaCommandError(code="EDA_SNAPSHOT_INCOMPLETE", detail=integrity)` |
| `read_with_retry`（`:1226-1239`） | 保留最后一次原始错误码；返回 `errors[]`；不得把所有失败折叠为 `EDA_PROJECT_NOT_READY` |
| `validate_plan`（`:727-857`） | 增加 `plan.sha256`、`based_on_snapshot_content_sha256`、`apply_id`（可选）；拒绝写入用 `page.current` |
| `reconcile`（`:915-1081`） | 增加 `preconditions`/`integrity` 检查；增加计划内/跨页位号检查；`designator` 为 `null/R?` 时冲突；漂移检测 |
| `verify_against_snapshot`（`:1084-1160`） | 签名增加 `execution`；优先用执行返回的 `primitive_id`；逐字段比较 `designator/unique_id/component/supplier_id/footprint/x/y/rotation/mirror/add_into_bom/add_into_pcb/net_flag.type/net_port.direction`；输出 `expected/observed/diff` |
| `compare_snapshots`（`:1163-1203`） | 比较域增加 `netports`（net/direction/x/y/rotation/mirror）、`attributes`（按需）、`mirror`、`add_into_bom/add_into_pcb`、工程/页身份；坐标口径统一为 `round(3)` 并显式声明容差 |
| `command_apply`（`:1395-1458`） | 构建 `preconditions`；把 `execution.results` 传给验证；输出 `level/level_status/claims`；partial 时不保存；未知结果标记 `unknown` |
| `command_save`（`:1461-1469`） | 校验返回是 dict；非 dict 抛 `EdaCommandError`；保存后回读 `content_sha256` |
| `command_reopen_check`（`:1502-1522`） | 快照文件缺失/JSON 错误转 `EdaInputError`；比较域按 §7.6；输出 `identity`/`integrity` |
| `main`（`:1608-1637`） | 所有异常输出统一外壳；增加 `message`；`EXIT_TIMEOUT` 结果带 `execution.state="unknown"` |
| 新增 `canonical_content(snapshot)` | 生成 `content_sha256`（§7.7） |
| 新增 `classify_snapshot(snapshot)` | 返回 `complete/truncated/read_failed/timeout/page_not_active` |
| 新增 `check_preconditions(...)` | 执行 §3.1 清单 |
| 新增 `classify_level(...)` | 计算 `level/level_status/level_reached/claims` |
| 新增 `render_message(...)` | 生成 §6 双层文本 |
| 新增 `write_manifest(...)` | 生成/校验 §5 manifest |

### 7.3 当前实现状态（基线 `dc62f20`）

> 下表只陈述代码事实；未在真实 EDA 会话重跑。`DONE` 表示基础能力存在，不表示已满足本协议全部字段。

| 协议能力 | 当前状态 | 代码/证据 | 说明 |
|---|---|---|---|
| 计划 schema 校验 | `DONE`（基础） | `eda_exec.py:727-857` | 已有严格字段/类型校验；缺 `plan.sha256`、`based_on_snapshot_content_sha256` |
| 快照基础读取 | `DONE`（基础） | `eda_exec.py:431-565`、`:1218-1223` | 能读 parts/flags/ports/wires/pins |
| 快照完整性/读取错误 | `DEFECT` | `:378-379`、`:458-480`、`:481-498`、`:485-488`、`:506-515`、`:553-563` | `safe()`/`safeAsync()` 把失败折叠为 `null/[]`；`coverage` 在 Python 侧无消费者；`attributes_complete` 未请求时为 `true`；需按 §2 重做 |
| 写入前条件 | `NOT RUN` | `:1399-1401` | `command_apply` 只用计划页参数，无工程/页 UUID、快照哈希校验 |
| 工程级位号唯一性 | `NOT RUN` | `:917`、`:933-1007` | `reconcile` 只用当前页快照；无跨页扫描 |
| 对账/幂等（已存在则 skip） | `PARTIAL` | `:915-1081` | 成功后的重复 apply 会 skip；但位号/漂移/工程级冲突未覆盖 |
| 逐项回读验证 | `PARTIAL/DEFECT` | `:1084-1160`、`:1430-1439` | 不比较 `designator` 值、不使用 `execution.results` 的 `primitive_id`；net flag type、net port direction/rotation/mirror、BOM 标志未比对 |
| 保存 | `PARTIAL` | `:1461-1469` | `save.saved` 是弱信号；未绑定保存后内容哈希 |
| 重开比较 | `PARTIAL/DEFECT` | `:1163-1203`、`:1502-1522` | 只比较 parts/wires/netflags；缺 netports/attributes/mirror/BOM 标志/页身份；缺文件时抛 `FileNotFoundError` |
| 超时/未知结果 | `PARTIAL` | `:1226-1239`、`:1618-1622` | 超时有警告；但读重试把原始错误折叠为 `EDA_PROJECT_NOT_READY`；无 `attempt/retry` 字段 |
| manifest | `NOT RUN` | 无命令；F1 README 仅 PNG/NET 哈希 | 需按 §5 实现 |
| 电气检查（ERC/DRC/网表等价） | `NOT RUN` | `:1284`（doctor `sch_drc=not_implemented`） | `export` 只支持 png/netlist/svg（`:1580`） |
| BOM/PCB/制造资料 | `NOT RUN` | `:1283-1285`、`:1580` | `sch_export_bom`、`pcb_read_write` 未实现 |
| 样机验证 | `NOT RUN` | 不在适配器范围 | 必须由外部测试记录提供 |
| 双层 message | `NOT RUN` | 当前 stdout 只有原始 JSON | 需按 §6 增加 |
| 协议测试覆盖 | `PARTIAL` | `tests/test_eda_exec.py` 23 项 | 未覆盖不完整快照、位号冲突、漂移、超时、partial、manifest、双层输出 |

### 7.4 协议验收测试（下一轮直接执行）

| ID | 场景 | 期望 |
|---|---|---|
| `P-01` | 注入 `getState_Designator` 抛错 / `parts=[]` 且 `counts.components>0` | `integrity=read_failed`；`apply` 退出 1/2；零写入；不得产生 `create_part` |
| `P-02` | 计划 create `R1`，工程另一页已有 `R1` | `DESIGNATOR_PROJECT_EXISTS`；零写入 |
| `P-03` | 同一计划两个 create 都用 `R1` | `DESIGNATOR_PLAN_DUPLICATE`；零写入 |
| `P-04` | modify `R1→R5`，回读仍是 `R1` | `verification=failed`，`reason=designator_mismatch`，`observed.designator=R1` |
| `P-05` | create 回读 `R?` | `verification=failed`，`observed.designator=R?`；不得再建一个 `R?` |
| `P-06` | net flag 计划 `Power`，回读 `Ground` | `verification=failed`，`reason=net_flag_type_mismatch` |
| `P-07` | net port 计划 `IN`，回读 `OUT`；或 mirror 翻转 | `verification=failed`，`reason=net_port_direction_mismatch`/`mirror_mismatch` |
| `P-08` | `add_into_bom=false` 但回读 true | `verification=failed`，`reason=add_into_bom_mismatch` |
| `P-09` | 计划依据快照与写入前 `content_sha256` 不同 | `SNAPSHOT_DRIFT`；零写入；要求重新对账 |
| `P-10` | `invoke` 超时 | `status=timeout`、`execution.state=unknown`、`retry.allowed=false`；后续必须先 `read` |
| `P-11` | `--allow-partial` 下 1 项失败 | `status=partial`；`written_keys/failed_keys` 正确；不保存；`level_status=partial` |
| `P-12` | 重开后删除 1 个 netport | `reopen-check` `mismatch`；difference 含 netports |
| `P-13` | 重开后翻转 part.mirror | `reopen-check` `mismatch`；difference 含 mirror |
| `P-14` | 请求页 UUID 与实际激活页不同 | `page_not_active`/`PAGE_MISMATCH`；禁止导出/写入 |
| `P-15` | manifest 缺 artifact 哈希 | `manifest verify` 退出 1；列出缺失项 |
| `P-16` | L3 结果生成 message | 两层 `level/level_status` 一致；新手层含限制；无禁用短语 |
| `P-17` | 对角线导线 `[0,0,10,10]` 解析 | 不得静默丢弃；应报 `unsupported_geometry` 或正确解析 |
| `P-18` | 坐标 `300.0` vs `300.004` | apply/reopen 使用同一容差口径（建议 `round(3)` 或声明 0.01），不得一个 verified 一个 mismatch |

### 7.5 非目标与未声明能力

本协议**不**声明以下能力已存在：

- 不在真实 `lceda-pro` 会话上执行任何新命令；
- 不实现 PCB 读取/布局/布线/铺铜/DRC/制造导出；
- 不实现 BOM/CPL/Gerber/钻孔/DFM 生成；
- 不实现 ERC/DRC 封装；
- 不实现网络标签写入；
- 不提供事务/回滚；EDA 侧没有跨动作事务，幂等只能靠客户端对账；
- 不提供密码学签名/不可抵赖审计；manifest 的 SHA256 只证明文件一致性；
- 不证明全在线 GUI、厂方审核、实时库存/价格、样机功能。

### 7.6 `L3` 必需比对字段

| 对象 | 必需字段 |
|---|---|
| `part` | `designator`、`unique_id`、`component.name`、`supplier_id`、`footprint.name`、`x`、`y`、`rotation`、`mirror`、`add_into_bom`、`add_into_pcb`；计划声明时再加 `manufacturer`、`manufacturer_id`、`supplier`、`name`、`other_property` |
| `net_flag` | `net`（name）、`type`、`x`、`y`、`rotation`、`mirror` |
| `net_port` | `net`、`direction`、`x`、`y`、`rotation`、`mirror` |
| `wire` | `net`、归一化线段集合（覆盖判断）、端点是否落在目标 pin/flag/port |
| 页/工程 | `project_uuid`、`schematic_uuid`、`page_uuid`、`selection_basis` |
| 快照 | `integrity.status=complete`、`content_sha256`、`captured_at_utc` |
| 执行 | 每个 key 的 `ok`、`primitive_id`、`unique_id`、`designator`（来自 `execution.results`） |

### 7.7 `content_sha256` 规范化

```text
projection = {
  "project_uuid": <uuid or null>,
  "page_uuid": <uuid>,
  "parts": sorted by (designator, unique_id, primitive_id) of {
      designator, unique_id, component.name, supplier_id, footprint.name,
      round(x,3), round(y,3), rotation, mirror, add_into_bom, add_into_pcb,
      manufacturer, manufacturer_id, supplier, name, other_property
  },
  "netflags": sorted by (name, round(x,3), round(y,3), type) of {
      name, type, round(x,3), round(y,3), rotation, mirror
  },
  "netports": sorted by (net, round(x,3), round(y,3), direction) of {
      net, direction, round(x,3), round(y,3), rotation, mirror
  },
  "wires": sorted by (net, segment tuple) of {
      net, normalized_segments [[x1,y1,x2,y2], ...]
  },
  "attributes": sorted by (name, x, y) of {...}  // 仅在 attributes.requested=true 时纳入
}
content_sha256 = sha256(json.dumps(projection, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
```

规则：

- 排除 `primitive_id`（跨会话易变）；保留 `unique_id`；
- 坐标统一 `round(3)`；比较时显式声明容差，apply 与 reopen 使用同一口径；
- 线段先归一化（方向无关、合并共线、去零长）再排序；
- `null` 与 `[]` 语义不同，不得在投影中互换；
- `content_sha256` 与 `snapshot_sha256` 都写入 manifest，前者用于漂移，后者用于证据完整性。

---

## 8. 附录

### A. 枚举速查

```text
level: PLAN_READY | WRITTEN | READBACK_VERIFIED | ELECTRICAL_CHECKED | MANUFACTURING_VERIFIED | PROTOTYPE_VERIFIED
level_status: passed | partial | not_run | blocked | failed | not_applicable
integrity.status: complete | truncated | read_failed | timeout | page_not_active
execution.state: completed | partial | preflight_failed | unknown | timeout
persistence.state: in_memory | saved | reopened
conflict.reason: ambiguous_match | part_identity_changed | supplier_identity_changed | designator_plan_duplicate | designator_project_exists | designator_modify_collision | wire_segment_net_conflict | stale_snapshot | page_identity_changed | snapshot_incomplete | unsupported_op | user_session
failure_kind: mismatch | defect | regression | tool_error
```

### B. 退出码

| 码 | 含义 |
|---:|---|
| 0 | 完成，无复核项 |
| 1 | 冲突/部分/验证不一致/保存失败 |
| 2 | 输入或前置条件不合法/不安全 |
| 3 | CLI 不可用/命令失败 |
| 4 | 超时，结果未知，必须回读 |

### C. 证据角色

`plan`、`snapshot_before`、`snapshot_after`、`apply_result`、`save_result`、`reopen_check`、`netlist_before`、`netlist_after`、`erc_report`、`drc_report`、`png_full`、`png_crop`、`bom`、`cpl`、`gerber`、`drill`、`stackup`、`dfm_report`、`firmware`、`test_log`、`photo`、`measurement`、`other`。

### D. 术语

| 术语 | 含义 |
|---|---|
| 快照 | 某一时刻从 EDA 读取的页内容与元数据 |
| 内容哈希 | 语义投影的 SHA256，用于判断内容是否漂移 |
| 完整快照 | `integrity.status=complete` 的快照 |
| 写入 | `apply` 发送受控动作；不等于保存 |
| 回读 | 写入后重新读取并逐项比对 |
| 部分成功 | 计划中一部分动作成功、一部分失败/冲突/未执行 |
| 未知结果 | 超时/传输错误后无法确认实际写入状态 |
| manifest | 机器可复核的证据清单 |
| interpretation | 人对证据的解释，必须引用 manifest |

### E. 变更记录

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-10-22 | 1.0 | 首版：六级结果、快照完整性、写入前条件、重试幂等、manifest、双层输出、实现映射与验收测试 |
