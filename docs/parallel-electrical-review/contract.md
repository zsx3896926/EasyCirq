# 离线电气意图审查：输入/输出契约（v1）

本模块只分析输入 JSON，不修改设计、不联网、不调用 EDA/旧执行器/Connector。
入口：`design-hardware/scripts/electrical_review`，CLI 为 `python -m electrical_review`。

- 输入 schema：`zhigou.electrical-review.input/v1`
- 输出 schema：`zhigou.electrical-review.report/v1`
- 工具版本：`0.1.0`
- Python 目标：≥3.10；仓库 CI `validate (3.10)` / `validate (3.13)` 已通过（#48、#52 及本
  docs-only PR）。本机直接运行版本为 3.13.15，代码按 3.10 语法编写，见 acceptance.md。

## 1. 命令与退出码

```bash
cd design-hardware/scripts
python -m electrical_review validate INPUT.json
python -m electrical_review review INPUT.json [--out REPORT.json]
python -m electrical_review explain REPORT.json [--finding-id ID] [--rule R1]
```

| 退出码 | 整体 status | 含义 |
|---|---|---|
| 0 | `pass_with_scope` | 所列规则、给定输入范围内均已证明满足，且无 unknown |
| 1 | `fail` | 至少一条已证明的硬性电气意图违反（severity=hard） |
| 2 | `invalid_input` | 输入/用法/报告非法；不执行或终止审查，绝不产生 PASS |
| 3 | `review_required` | 无硬性违反，但有 unknown/证据不足或项目策略违反 |
| 4 | `incomplete` | 未提供 intent，或没有可审查对象/部分规则因整段输入缺失未评估 |

- stdout 始终是纯 JSON（`review` 无 `--out` 时输出完整报告；有 `--out` 时输出摘要对象）；
  诊断信息只写 stderr。
- `--out` 使用同目录临时文件 + `os.replace` 原子写入；即使输入非法也会写入
  `invalid_input` 报告，避免旧 PASS 残留。`--out` 与输入同一路径会被拒绝。
- `explain` 只读报告，不重新审查；`--finding-id`/`--rule` 过滤。

## 2. 输入结构

```jsonc
{
  "schema": "zhigou.electrical-review.input/v1",
  "design": {
    "project_id": "工程 ID", "document_id": "页面/文档 ID",
    "title": "可选",
    "units": {"length": "mil|mm|in", "voltage": "V|mV",
              "capacitance": "F|uF|nF|pF", "resistance": "ohm|kohm"},
    "source_type": "host_export|manual_declaration|synthetic_fixture|derived",
    "source": {"producer": "...", "captured_at": "...",
               "snapshot_sha256": "64hex（声明值，本模块不重新读宿主）",
               "description": "..."}
  },
  "evidence": [
    {"id": "E1", "kind": "host_export|manual_declaration|synthetic_fixture|derived|vendor_datasheet|project_policy|measurement",
     "source": "...", "url": "可选", "sha256": "可选", "captured_at": "可选", "note": "可选"}
  ],
  "components": [{
    "instance_id": "稳定实例 ID（位号改了也不变）",
    "ref": "U1",
    "kind": "capacitor|resistor|inductor|diode|switch|ic|connector|other",
    "mpn": "精确型号或 null", "mpn_status": "exact|unknown",
    "manufacturer": "可选", "value": "可选",
    "attributes": {
      "capacitance": {"value": 1e-7, "unit": "F", "evidence": ["E1"]},
      "rated_voltage": {"value": 16, "unit": "V", "conditions": "DC",
                        "evidence": ["E1"]},
      "max_differential_stress": {"value": 24, "unit": "V",
                                  "basis": "declared worst case", "evidence": ["E1"]},
      "resistance": {"value": 10000, "unit": "ohm", "evidence": ["E1"]}
    },
    "pins": [{
      "number": "1", "name": "VCC", "net": "3V3|null",
      "pads": ["1", "TAB"], "pad_nets": {"TAB": "3V3"},
      "no_connect": false, "state": "connected|nc|unknown",
      "position": {"x": 0, "y": 0, "units": "mil"}
    }],
    "mapping_complete": true,
    "footprint": {"name": "SOT-223", "evidence": ["E1"]},
    "placement": {"x": 0, "y": 0, "units": "mil", "rotation": 0},
    "internal_groups": [{"pins": ["1", "2"], "behavior": "always_closed|pressed_closed|normally_open|normally_closed",
                         "evidence": ["E1"]}],
    "evidence": ["E1"]
  }],
  "connectivity": {
    "pin_nets": {"U1.1": "3V3"},           // 可替代/补充 pin.net；两者冲突=非法输入
    "internal_groups": [{"component": "SW1", "pins": ["1","2"], "behavior": "always_closed"}],
    "net_aliases": [["GND", "VSS"]],       // 网名别名只在“同一真实分区”语义下合并
    "measurement": {"available": false, "source": "宿主网表", "gaps": ["未回读铜"]},
    "coverage": {"complete": false, "notes": ["仅本页"]}
  },
  "intent": {
    "source": "user_declaration|datasheet|derived",
    "supplies": [{"net": "VIN", "min_v": 24, "max_v": 24, "kind": "dc", "evidence": ["E1"]}],
    "net_roles": {"GND": "ground", "VIN": "power", "SW": "switching", "EN": "signal"},
    "capacitor_roles": [{
      "component": "C1", "role": "bulk|local_decoupling|filter|flying|unknown",
      "role_source": "datasheet|user_declaration|project_constraint|derived",
      "expected_terminals": [{"pin": "1", "net": "CP"}, {"pin": "2", "net": "CN"}],
      "evidence": ["E1"], "fact_ids": ["F-MAX3232"]
    }],
    "switch_requirements": [{
      "component": "SW1", "function": "reset", "used_pins": ["1","3"],
      "pressed_connection": ["1","3"], "forbidden_pressed_nets": [["VIN","GND"]],
      "evidence": ["E1"]
    }],
    "pin_roles": [{"component": "U1", "pin": "4", "role": "input|output|bidirectional|open_drain|push_pull|power|ground|passive", "evidence": ["E1"]}],
    "decoupling_targets": [{
      "capacitor": "C1", "target_component": "U1", "target_pins": ["8"],
      "max_distance": {"value": 150, "unit": "mil"},
      "basis": "euclidean_proxy", "source": "project rule", "evidence": ["E1"]
    }],
    "derating": {"max_voltage_fraction": 0.8, "source": "project policy", "evidence": ["E1"]},
    "assumptions": ["..."]
  },
  "device_facts": [{
    "fact_id": "F1", "mpn": "TPS62130RGTR", "manufacturer": "TI",
    "package": "VQFN-16 (RGT)", "revision": "SLVSAG7F",
    "source": {"kind": "datasheet|erratum|package_drawing|project_policy|synthetic_fixture",
               "url": "https://...", "revision": "...", "retrieved_at": "2026-10-27",
               "pages": "3", "table": "Table 6-1", "sha256": "64hex"},
    "applies_to": {"mpn": ["TPS62130RGTR"], "packages": ["VQFN-16","RGT"], "revisions": []},
    "facts": [
      {"type": "capacitor_rated_voltage", "value": {"value": 16, "unit": "V", "conditions": "..."}},
      {"type": "switch_internal_groups", "value": {
        "always_closed_groups": [["1","2"], ["3","4"]],
        "pressed_connects_groups": true, "pressed_closes": [],
        "terminal_numbering": "原厂图明确"}},
      {"type": "pin_functions", "value": {
        "pins": {"4": {"name": "PG", "type": "open_drain"},
                 "16": {"name": "VCC", "type": "power"},
                 "11": {"name": "DIN1", "type": "input", "max_v": 5.5}},
        "supply": {"min_v": 3, "max_v": 5.5, "unit": "V", "conditions": "..."}}},
      {"type": "pad_map", "value": {"package": "VQFN-16",
        "pins": [{"pin": "EP", "pads": ["17"], "required_net_role": "ground",
                  "note": "Must be connected to AGND/PGND"}]}},
      {"type": "flying_capacitor", "value": {"pins": {"positive": "1", "negative": "3"},
        "note": "C1+ / C1- flying capacitor leads"}}
    ]
  }],
  "operating_conditions": {
    "net_voltages": [{"net": "VIN", "min_v": 4.5, "max_v": 5.5, "kind": "dc|ac|switching|unknown", "evidence": ["E1"]}],
    "ambient": {"min_c": -40, "max_c": 85},
    "notes": ["..."]
  }
}
```

规则：

- `components[].instance_id`、`components[].ref`、`evidence[].id`、`device_facts[].fact_id`
  全局唯一；重复 `instance_id`/`ref`/脚号/焊盘映射 = 非法输入。
- `pin.net` 与 `connectivity.pin_nets` 同时出现且不一致 = 非法输入；仅单边出现时以该值为准，
  两边都没有 = unknown（不是 NC）。
- 数字拒绝 bool/NaN/Infinity；耐压/电容值必须 >0；单位必须在白名单内。
- 器件事实只在“精确 MPN + 封装/修订适用”时使用；封装/修订不匹配 → unknown，不套用。
- `device_facts[].source` 为 `datasheet/erratum/package_drawing` 时必须有 URL。
- 最小输入必须含 `design/components/connectivity`；`intent/device_facts/operating_conditions`
  可缺省，缺省时对应规则不适用或 unknown，不会产生 PASS 依据。

## 3. finding / summary 语义

每条 finding 至少含：

| 字段 | 说明 |
|---|---|
| `rule_id` | R1–R6；输入级为 INPUT |
| `state` | `violated` / `insufficient` / `not_applicable` / `invalid_input` |
| `severity` | `hard`（已证明硬违反）/`review`（策略或证据不足）/`info` |
| `certainty` | `proven` / `derived` / `declared` / `unverified` |
| `subjects` | 组件/引脚/网络（可定位对象） |
| `actual` / `constraint` / `unit` | 实际值/约束/单位；不可判定时为 null |
| `evidence` | 证据 id、来源、URL、页码/表、资料修订、本地 sha |
| `explanation` / `recommendation` | 解释与只读审查建议（不生成自动修改命令） |
| `unverified` | 该结论仍未证明的项 |

summary 分别给 `checked/satisfied/violations/unknown/not_applicable/invalid_input`；
`pass_with_scope` 只证明“列出的规则 + 给定输入覆盖范围”，报告 `not_checked` 明确列出
未覆盖的 EDA/DRC/波形/铜/热/EMC/制造/上电等。**没有 finding 不等于整电路通过。**

## 4. 哈希与重放

- `input.sha256`：输入文件原始字节的 SHA-256（含格式差异）。
- `input.semantic_sha256`：解析后 JSON 的稳定语义形式（对象键排序、数组排序）的 SHA-256；
  组件/引脚/网络重排不改变语义哈希，工程身份/内容变化会改变。
- `design.source.snapshot_sha256` 只是上游声明值；报告标记 `verified=false`，不重新读取宿主。
- 报告不含时间戳，稳定排序（`sort_keys`），同一输入同一路径可字节级重放。
- 非法输入时 `semantic_sha256` 可能为 null，但 `input.sha256` 仍绑定到实际文件。

## 5. 证据来源分层

- `host_export`：宿主回读，未经本模块重新读取；
- `manual_declaration`：人工声明；
- `synthetic_fixture`：合成夹具；
- `derived`：由上述证据离线派生（报告必须写清派生关系）；
- `vendor_datasheet`：原厂资料（device fact 的 source 字段）；
- `project_policy`：项目自定阈值/降额策略。

格式适配不得把人工意图变成宿主测量；本模块不做此类转换。
