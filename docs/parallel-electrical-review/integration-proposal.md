# 与任务 A / 主执行流程的集成建议（只建议，不直接改共享文件）

本文件是任务 B 的轻量集成接口。任务 A 不需要等待本模块；本 PR 可独立合入，
再由任务 A 或后续集成 PR 接入。**本文件不修改 SKILL.md、references、feedback、
design_engine、pcb_gate、runtime、connector、protocol、distribution、CI、依赖或版本号。**

## 1. 现有宿主证据 → 本模块输入（最小映射）

| 本模块字段 | 可用的现有来源（示例） | 注意 |
|---|---|---|
| `design.project_id/document_id` | `design-state.json` 的 `project.name/uuid`；`sch-connectivity.json` 的 `projectId`；页面 `pageId/pageName` | 只作身份/追溯，不用于电气判断 |
| `components[].instance_id` | 宿主 primitiveId / `sch-connectivity.components[].id` 或 `uniqueId` | 位号改了不能变；用于跨重命名重放 |
| `components[].ref` | `components[].ref` / Designator 属性 | 重复位号必须报非法输入 |
| `components[].mpn/footprint` | BOM/identity 读回的 Manufacturer Part、Footprint；`pcb-dump.components[].device` | 型号未知写 null + `mpn_status=unknown`；不要猜 |
| `components[].pins[].number/name/net` | `sch-connectivity.components[].pins[].number/name` + `connections`/pin net | 引脚网络用宿主回读；人工意图另放 intent |
| `components[].pins[].pads` | PCB dump 的 `pads` 与封装焊盘名/号 | 当前 dump 的 pad 可能没有脚号；没有映射证据就 `mapping_complete=false`，R5 给 unknown |
| `components[].pins[].position` | `pcb-dump` pad 的 `x/y`（宿主坐标） | 坐标是宿主回读；旋转已在绝对坐标中体现；不要用器件中心代替焊盘 |
| `connectivity.pin_nets` | `sch-connectivity` 的 connections；或内联在 pin | 两处同时给出且冲突 = 非法输入 |
| `connectivity.net_aliases` | 宿主跨页/别名信息（如果有）；否则不要把近似网名自动合并 | 只合并有证据的别名 |
| `connectivity.measurement` | 宿主回读能力/缺口 | 缺铜/路径时明确 unknown |
| `intent.capacitor_roles` | 用户/原厂/项目声明（如 MAX3232 C1 飞跨、去耦角色） | 不能从 100 nF/10 µF 或位号推断；角色必须有 source |
| `intent.switch_requirements` | 按键功能、实际使用脚号 | 4 脚按键只按原厂脚号；不按符号左右 |
| `intent.pin_roles` | 用户/模块声明的输入/输出/开漏/电源角色 | 网名 “IN/OUT” 不是能力证据 |
| `intent.supplies/net_roles/operating_conditions` | 电源树/接口约束/用户输入 | 16 V 电容是否够由节点应力决定，不是全板统一 |
| `intent.decoupling_targets/derating` | 项目约束/降额策略 | 阈值必须带来源，不用全局 100/150 mil |
| `device_facts` | 原厂 datasheet 摘录（型号、封装、修订、页/表、URL、sha256） | 只对精确 MPN/封装/修订生效；本模块不内置资料库 |
| `evidence[]` | 宿主回读/manual/derived 记录 | 必须区分 host_export/manual/synthetic/derived |

### 最小输入例子（只读已有读回，不新增 EDA 调用）

```json
{
  "schema": "easycirq.electrical-review.input/v1",
  "design": {"project_id": "mcu-i2c-s3-20261026", "document_id": "P2",
             "units": {"length": "mil", "voltage": "V", "capacitance": "uF"},
             "source_type": "derived"},
  "evidence": [{"id": "E-PCB", "kind": "derived",
                "source": "cases/.../pcb-dump-final.json", "sha256": "42acfe23..."}],
  "components": [{
    "instance_id": "iU1", "ref": "U1", "kind": "ic", "mpn": "AMS1117-3.3",
    "mapping_complete": true, "footprint": {"name": "SOT-223", "evidence": ["E-PCB"]},
    "pins": [
      {"number": "1", "name": "GND", "net": "GND", "pads": ["1"]},
      {"number": "2", "name": "VOUT", "net": "+3V3", "pads": ["2", "TAB"]},
      {"number": "3", "name": "VIN", "net": "VBUS_5V", "pads": ["3"]}
    ]
  }],
  "connectivity": {"pin_nets": {}},
  "device_facts": [{"fact_id": "F-AMS1117", "mpn": "AMS1117-3.3",
                    "package": "SOT-223",
                    "source": {"kind": "datasheet", "url": "http://.../ds1117.pdf",
                               "pages": "1", "sha256": "189a..."},
                    "facts": [{"type": "pad_map", "value": {"pins": [
                      {"pin": "2", "pads": ["2", "TAB"]}]}}]}],
  "intent": {"net_roles": {"GND": "ground", "+3V3": "power", "VBUS_5V": "power"}}
}
```

对应真实重放场景：`benchmarks/electrical-review/cases/real-mcu-i2c-ams-tab/input.json`。

## 2. 调用契约

```bash
PYTHONPATH=easycirq/scripts python -m electrical_review review INPUT.json \
  --out electrical-review-report.json
```

- stdout 纯 JSON；stderr 诊断；`--out` 原子写、旧 PASS 不会被保留。
- 退出码：0 `pass_with_scope`；1 `fail`（hard）；2 `invalid_input`；
  3 `review_required`；4 `incomplete`。
- `report.summary.totals` 分 checked/satisfied/violations/unknown/not_applicable/
  invalid_input；`report.status` 与退出码一一对应。
- `schema` 固定为 `easycirq.electrical-review.input/v1`；报告 `easycirq.electrical-review.report/v1`。
  不兼容变更需升版本号，不静默改语义。
- 缺少证据的语义：`review_required`/`incomplete`，不是 `pass`；报告 `not_checked` 列出
  本模块不覆盖的 EDA/DRC/波形/铜/热/EMC/制造/上电。

## 3. 建议调用点

1. **代表模块完成、PCB 同步/apply 之前**：用当前 sch read + intent + device facts 跑一次；
   对与该模块相关的 hard finding（R1–R5）阻断该模块的电气推进；unknown 要求补充证据或
   人工 disposition。不要把所有 unrelated 排版/布局工作一起锁死。
2. **关键电气变更后**（电源/去耦/按键/引脚重映射/封装替换）：对变更 scope 重跑；
   输入哈希必须变化，不能沿用旧报告。
3. **交付/验收前证据补充**：`pass_with_scope` 只能作为“所列规则在给定输入范围内满足”的
   证据，不是 DRC/保存重开/制造/上电通过。`review_required` 项应进入待办清单而不是
   永久全局阻止。
4. **不接入 EDA 执行器**：本模块只在宿主读回之后、写回之前离线运行；不调用
   easyeda CLI/daemon/connector，不联网，不修改设计。

## 4. 集成策略建议（由主维护者最终决定）

- `hard` finding（R1–R5 已证明电气违反，R2 硬超额）：阻止相关模块的电气推进；
- `review` finding（降额策略、R6 距离、证据不足）：要求人工 disposition 或补证据，
  不自动改线，不永久锁死无关任务；
- `invalid_input`：禁止复用旧 PASS；修复输入后重跑；
- `pass_with_scope`：只对列出的规则和输入覆盖成立，继续由现有 DRC/保存重开/实测覆盖
  其余质量门。

## 5. SKILL.md 建议补丁（文档 diff 片段，不直接修改）

在 SKILL.md 的“原理图/PCB 检查”或“验证”章节附近增加（措辞可按仓库风格调整）：

```diff
+### 电气意图审查（离线，可选但推荐）
+
+在网表/连通性检查之后、PCB 同步或关键电气变更之前，运行：
+
+```bash
+PYTHONPATH=easycirq/scripts python -m electrical_review review <input>.json --out <report>.json
+```
+
+- 退出码 0=pass_with_scope、1=fail、2=invalid_input、3=review_required、4=incomplete；
+- 它检查飞跨电容端点、电容耐压/应力、四脚按键内部常通组、特殊引脚/电源域、
+  裸焊盘/合并焊盘、电容角色与局部距离；**不调用 EDA/不联网**；
+- `pass_with_scope` 只证明所列规则和输入范围，不表示整板/DRC/制造/上电通过；
+- hard finding 阻断相关电气推进；unknown 要求补证据/人工 review，不是自动改线。
+  详见 `docs/parallel-electrical-review/`。
```

## 6. references 建议补丁（文档 diff 片段，不直接修改）

在 `references/connectivity.md`（或等价连通性说明）增加一段：

```diff
+> **连通性/网表一致 ≠ 电气正确。** `pin_net_intent_check.py` 的 `match` 只证明宿主实现
+> 与 intent 的连接组一致；若 intent 本身把飞跨电容两端接到同一网、把四脚按键的常通组
+> 当成两个节点、或忽略电容耐压/引脚能力，网表仍会“匹配”。需要设计意图审查时，使用
+> `easycirq/scripts/electrical_review`（离线，0 EDA 调用），并按
+> `docs/parallel-electrical-review/contract.md` 提供 intent/device_facts。其
+> `pass_with_scope` 不是整板电气通过。
```

## 7. 版本与兼容

- 输入/报告 schema 版本独立于 skill 版本；本模块首期不要求主流程/任务 A 代码变更。
- 任务 A 可先只读调用、记录报告；确认稳定后再把 exit 1/3 映射到 gate。
- 若任务 A 的 observation 字段变化，优先在适配层转换，不要把宿主协议复制进本模块。
