# 高速信号参考平面与回流风险审查 — 输入/输出契约

版本：`return-path-audit-input/v1` → `return-path-audit-report/v1`
工具：`python -m return_path_audit`（`easycirq/scripts/return_path_audit/`）
性质：离线几何/拓扑审查。不调用 EDA、不做电磁场求解、不修改设计。

## 1. 边界与结论语义

- 只审查**已声明的**层叠、参考铜、信号投影、换层与证据。
- `pass_with_scope` 仅表示“在本次声明范围内未发现参考路径几何/拓扑缺陷”，
  **不**表示阻抗匹配、SI/EMI、DRC、制造或功能通过。
- 几何不能证明电连接、不能证明真实回流充足时，一律输出 `unknown`，不输出
  `recovered_return_path=true`。
- 工具只读输入；报告永远写到输入之外（`--out` 与输入同一路径会被拒绝）。

## 2. 输入 JSON

```jsonc
{
  "schema": "return-path-audit-input/v1",
  "project": {"id": "...", "document": "...", "snapshot": "..."},
  "source": {"kind": "offline_export|synthetic", "producer": "...",
             "captured_at": "2026-10-27T14:00:00Z",
             "raw_input_sha256": "<64 hex>"},
  "units": "mm|mil",
  "stackup": {"complete": true, "layers": [Layer, ...]},
  "board": {"outline": Ring, "holes": [Ring, ...], "complete": true,
            "geometry_tolerance": 0.01},
  "reference_copper": [Copper, ...],
  "signals": [Signal, ...],
  "vias": [Via, ...],
  "reference_assignment": [Assignment, ...],
  "transitions": [Transition, ...],
  "constraints": {...},
  "unsupported": [{"kind": "arc_trace", "signal": "sig1", "segment": "sig1.1",
                   "reason": "..."}],
  "external_reports": [{"kind": "length_match", "source_snapshot": "...",
                        "sha256": "<64 hex>", "summary": "read-only"}]
}
```

### 2.1 基本类型

- `Ring`：闭合点环，`[[x,y], ...]`，**首点必须等于末点**，≥4 个点（3 个不同顶点 + 重复首点）。
  自交、零面积、未闭合 → `input_invalid`，不做静默修复。
- 所有长度共用 `units`；`bool` 不当数字；`NaN/inf` 拒绝；宽度必须 > 0。
- 层引用一律使用 `copper_layer_id`，**物理顺序只由 `order` 决定**，禁止按 ID 排序猜测。

### 2.2 Stackup

```jsonc
{"order": 1, "copper_layer_id": "L1", "role": "signal|plane", "net": null,
 "material": "FR-4", "thickness": {"value": 0.035, "unit": "mm"},
 "dielectric_below": {"value": 0.2, "unit": "mm"}}
```

- `order` 必须从 1 连续到 N，不可重复；`role=plane` 必须声明 `net`。
- 支持任意层数与非标准四层（例如 L1 信号 / L2 信号 / L3 GND / L4 PWR），不写死角色。
- `dielectric_below` 表示“本铜层到下一铜层”的介质厚度；缺失时无法判断“更近参考”，
  结果必须是 `unknown`（`RP-E1-112`），不得估算。

### 2.3 Board

`outline`/`holes` 为 `Ring`；`holes` 必须在板框内。`geometry_tolerance` 是唯一的
几何容差来源（用于退化判定与“容差附近”分类），不是“放大容差消风险”的开关。

### 2.4 Reference copper（参考铜）

```jsonc
{"id": "rc-gnd-l2", "layer": "L2", "net": "GND",
 "availability": "actual_fill|pour_boundary|ideal_plane|unknown",
 "is_actual_fill": true, "connectivity_island": "gnd-l2",
 "source_snapshot": "snap-1",
 "polygons": [{"id": "poly-1",
               "outer": Ring, "holes": [Ring, ...]}]}
```

- `availability=actual_fill` ⇔ `is_actual_fill=true`；`pour_boundary`/`ideal_plane`
  必须 `false`。矛盾 → `input_invalid`。
- **实际已填充铜 / 铺铜设计边界 / 理想无限平面 / 合成 polygon 必须区分**：
  只有 `actual_fill` 能计入 `checked_length`；`ideal_plane` 只能得到
  “声明理想化下的潜在结论”，`pour_boundary`/`unknown` 只能是 unknown。
- `connectivity_island` 是电气连通岛标识；几何相接但岛不同/未声明时，连接仍是 unknown。

### 2.5 Signal / Segment

```jsonc
{"id": "sig-dp", "net": "USB_DP", "differential_pair": "DP1|null",
 "segments": [{"id": "sig-dp.1", "kind": "straight|arc|polyline|unsupported",
               "layer": "L1", "start": [20,40], "end": [80,40], "width": 0.2,
               "branch": null, "direction_evidence": null,
               "source_snapshot": "snap-1"}]}
```

- 差分对成员**只来自 `differential_pair` 声明**，不从 P/N 名称猜。
- `kind=straight` 必须给 `start/end/width`；其它 kind 必须给 `length`（否则 unknown）。
- **任何非直线几何一律视为不支持**：既可以在 `unsupported[]` 里显式声明，也可以直接用
  `kind=arc/polyline/unsupported` 声明；两种通道都会产生 `RP-E5-502` 并把该段长度计入
  `unknown_length`。**不得**忽略非直线对象后把整网标 PASS。

### 2.6 Via

```jsonc
{"id": "via-1", "net": "GND", "center": [10,10], "diameter": 0.45,
 "span": {"from": "L1", "to": "L4"}, "via_type": "through|blind|buried",
 "connectivity_island": "gnd-l2", "connected_copper_ids": ["rc-gnd-l2"],
 "connection_evidence": "pad|thermal|fill|declared|none|null",
 "source_snapshot": "snap-1"}
```

- `via_type` 必须与物理跨度一致：`through`=顶层到低层，`blind`=一端在外层，
  `buried`=两端都在内层；不一致 → `input_invalid`。
- 候选回流的连接证据只认：`connected_copper_ids` 指向实际填充铜，或同
  `connectivity_island`，且 `connection_evidence ∈ {pad, thermal, fill}`；
  仅“同网名 + 距离近”不够（`RP-E3-309`）。

### 2.7 Reference assignment

```jsonc
{"id": "ra-1", "target": {"signal": "sig-dp", "segment": "sig-dp.1"},
 "reference_layer": "L2", "reference_net": "GND", "basis": "declared|candidate",
 "evidence": "...", "candidates": [{"layer": "L3", "net": "P3V3"}],
 "source_snapshot": "snap-1"}
```

- `target` 可为 `{signal, segment}`、`{signal, layer}` 或 `{signal}`。
- 多个匹配且参考不同 → `RP-E1-110`（冲突，不自动选赢家）。
- `basis=candidate` → 意图未声明，只能 unknown；最近铜层**不自动等于**有效参考。
- `source_snapshot` 与项目快照不同 → 证据拒绝复用（unknown）。

### 2.8 Transition

```jsonc
{"id": "tr-1", "signal": "sig-dp", "via": "via-2",
 "layer_from": "L1", "layer_to": "L4",
 "segment_before": "sig-dp.1", "segment_after": "sig-dp.4",
 "reference_before": {"layer": "L2", "net": "GND"},
 "reference_after": {"layer": "L3", "net": "P3V3"},
 "candidate_return_vias": ["via-3"],
 "decoupling_caps": [{"id": "C1", "net_from": "P3V3", "net_to": "GND",
                      "evidence": "placed+connected per dump",
                      "frequency_basis": "interface note section",
                      "source_snapshot": "snap-1"}]}
```

- 换层时参考网变化（GND→电源）**不**自动建议“加 GND via 解决”；去耦电容只能作为
  有条件候选，且必须有端点、连接证据、适用频率依据与快照绑定（`RP-E3-313`）。

### 2.9 Constraints（项目/接口阈值）

```jsonc
"constraints": {
  "interface": "USB 2.0 HS",
  "source_ref": "SRC-01",
  "corridor": {"value": 0.2, "source_ref": "SRC-02", "conditions": "..."},
  "max_return_via_distance": {"value": 2.0, "source_ref": "SRC-03"},
  "min_split_gap": 0.1,
  "via_search_radius": 2.0,
  "tolerance": 0.01
}
```

- 阈值可为裸数字或 `{value, source_ref, conditions}`。没有一手来源的阈值必须显式
  标为 project-configured（报告 `threshold.project_configured=true`），不得伪装成标准。
- `corridor` 缺失时按 0 处理，并在报告 scope 中记录该假设（`assume_zero_corridor`）。

## 3. 严格校验（`validate`）

拒绝而非修复：重复 ID（全局对象 ID 唯一）、缺失单位/非法层、bool/NaN/inf、负宽度、
未闭合/自交 polygon、缺失 via span、零长线段、层序不连续、via 类型与跨度矛盾、
polygon 孔洞不在外环内。失败输出 `return-path-audit-validation/v1` 与 issue 列表，
退出码 4，不产生审计结论。

## 4. 报告（`return-path-audit-report/v1`）

必含：`schema/tool/tool_version`、`input`（字节 SHA256 + 语义 SHA256 + project/source/
binding）、`overall_status`、`scope`（含 not_claimed）、`coverage`、`findings`、
`unknowns`、`suggestions`、`evidence_sources`、`run`（`simulated=true`、
`real_eda=NOT RUN`）、`limits`。

每条 finding：`rule_id/group/title/severity/determinism`、`signal_ids/segment_ids/
copper_ids/polygon_ids/via_ids`、`layer`、`interval`（t0/t1/起止坐标/长度）、
`unit`、`measured`、`threshold`（值+来源+条件）、`explanation`、`recommendation`、
`source_family/source_ids`。

`determinism ∈ {proven, potential, unknown}`；`severity ∈ {error, warning, info}`。

### 状态与退出码

| 状态 | 退出码 | 含义 |
|---|---|---|
| `pass_with_scope` | 0 | 声明范围内未发现参考路径缺陷（不代表 SI/DRC/制造通过） |
| `fail` | 1 | 存在 **proven** error（如跨不同网络分割、参考铜缺失、via 跨度不足） |
| `review_required` | 2 | 存在 warning、非 proven 的 error，或任何 `determinism=potential` 的结论（需工程复核） |
| `incomplete` | 3 | 覆盖不足/未知，审计无法下结论（空路径、全 unknown、未声明参考） |
| `input_invalid` | 4 | 输入未通过严格校验，审计未执行 |
| 用法/IO 错误 | 5 | 参数缺失、路径不可读、拒绝覆写输入等 |

优先级：`input_invalid > fail > review_required > incomplete > pass_with_scope`。
`unknowns` 非空或 `unknown_length>0` 时永不返回 `pass_with_scope`。
**注意**：一个“合格的回流候选”（`RP-E3-310`，`determinism=potential`）也属于
`review_required`——候选不是已证明的回流路径，不能据此判 pass。

### 覆盖状态语义

- `checked`：参考铜是实际填充、几何受支持、已做覆盖判定；
- `wrong_reference_net`：投影落在其它网络铜上（计入覆盖风险，`RP-E2-201`）；
- `void` / `corridor_insufficient` / `borderline`：见 geometry-support.md；
- `unknown`：参考意图、实际填充铜、几何支持或快照绑定任一不满足；
- `not_applicable`：线段落在非信号层（`RP-E5-505`）。

连续的多个非 safe 区间合并为一条 finding（`measured.void_length / corridor_length /
wrong_net_length` 保留分量），定位信息在 `interval` 与可选 SVG 叠加图中。

### 覆盖记账（E5）

每个网络/线段给出 `checked_length / unknown_length / not_applicable_length` 与原因。
未支持几何、非实际填充铜、缺失/冲突参考、陈旧证据均计入 unknown，**不得**忽略后
把整网标 PASS。

## 5. CLI

```bash
cd easycirq/scripts
python -m return_path_audit validate -i input.json [-c constraints.json]
python -m return_path_audit audit    -i input.json [-c constraints.json] \
       [-o report.json] [--svg overlay.svg]
python -m return_path_audit explain  --report report.json
python -m return_path_audit explain -i input.json
```

- stdout 只放机器 JSON（`explain` 为纯文本）；日志/错误走 stderr。
- 报告原子写：临时文件 + `os.replace`；失败不留下旧的 PASS 文件。
- `--out/--svg` 与输入同路径会被拒绝；不覆写源快照。
- SVG 为本地分析叠加图，带 `synthetic_analysis / not_official_export` 水印，
  不是官方导图，也不代表宿主渲染正确。

## 6. 变形稳定性约定

对象排序、网络一致重命名、无关铜增加不改变规则结论；整体平移/90° 旋转/合法单位换算
（mm↔mil 同步换算坐标与阈值）语义等价。字节哈希始终随输入字节更新；语义哈希按规范化
几何+证据计算（见 `model.semantic_projection`）。
