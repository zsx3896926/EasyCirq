# 封装内嵌 Board Outline 缺陷：现场结论与修复路径

> 现场实测：2026-10-28，EasyEDA Pro 4.1.78，自有 easycirq 运行时 0.2.2-dev +
> easycirq-connector 0.1.2。证据：`evidence/outline-foreign/`。

## 现象

器件 `C2980113 / YTS1C0172BWJ00`（封装 `SW-SMD_2P-YTS1C0172B`）放到 PCB 后，
原生 DRC 报 **4 条** `Board Outline to SMD Pad — Clearance Error in the same footprint`
（最小间距 0.0275 mm < 规则 0.03 mm，影响该器件 4 个焊盘）。布线与铺铜怎么改都无法消除。

## 根因（实测）

* 违规对象是一个 **component 子图元**（id 与器件同前缀，如 `50806a65edafeecee19`），
  类型在 DRC 里显示为 `Board Outline`；
* 它**不是** layer-11 的普通图元：`pcb_PrimitiveLine/Arc/Polyline.getAll()` 都枚举不到它；
* 按 id 调 `pcb_PrimitiveLine.delete([id])` 返回 `true`，但 **save + reload 之后该对象又出现**
  （`getPrimitivesBBox([id])` 仍返回 bbox），DRC 继续报同一对象 → **删除不可靠**。

## 修复路径（已验证有效）

1. 诊断：`python tools/easycirq_footprint_outline_diagnose.py`
   → 点名器件、违规条数、受影响焊盘、对象 id、建议。
2. 换器件（不是删图元）：
   `easycirq sch replace --id <器件 primitiveId> --lcsc <无内嵌 outline 的同类器件>`
3. 同步与复验：`doc open <pcb>` → `pcb import-changes` → `pcb save` → `doc reload` → `pcb drc`
4. 实测结果：**4 条违规 → 0 违规（DRC passed）**；证据 `17-drc-after-replace.json`。

替代路径：`sch rebind-footprint` 换封装（同电气不同 footprint），或直接改库删除该图形（根因）。

## 产品决策

* **不从工具侧宣称"能删除封装内 outline 图形"**：connector 里的
  `pcb.outline.foreign.scan/delete` 已从 runtime action catalog 移除（枚举不到子图元、删除被重建）。
  它们继续留在 0.1.2 连接器里但不作为能力发布。
* **支持的能力是"诊断 + 器件/封装级替换 + 保存重开 DRC 复验"**，已封装为
  `tools/easycirq_footprint_outline_diagnose.py`。
* 根因在库/封装数据：封装不应内嵌板框图形。

## 复现方式（可重复）

测试工程 `outline-foreign-repro-20261028-013032`（P1 + PCB1）；
放置 `C2980113` → 同步 PCB → `pcb drc` 必现该违规；按上面路径处理后转为 0。
