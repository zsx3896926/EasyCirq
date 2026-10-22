---
id: F09
title: USB-C CC 电阻缺失/错误
evidence_grade: B
source_ids: [PWR-S16, PWR-S15, PWR-S17]
last_reviewed: 2026-10-20
---

# F09 USB-C CC 电阻缺失/错误

> **证据等级：** `B`。ST AN5225 Rev 7 的 Table 6/7 给出 sink 侧 `Rd` 与 source 能力电压窗，Table 5 给出 source 侧 `Rp`；TI TUSB320 数据手册给出 `Rd` 阻值、DFP 电流源与检测门限。这些是原厂器件/应用资料，能支持“CC 缺失或错值导致不供电/电流档错误”的机理；具体这块板是漏贴、错值还是短接，仍需电阻与电压测量确认（正文标注）。USB-IF Type-C 规范 Release 2.5 本次只读到文档库元数据（PWR-S17），未读正文，因此本案例不引用任何规范条款号。
>
> **适用边界：** 只适用于 5 V、无 USB PD 的 Type-C sink（受电端）。source 侧 `Rp`、DRP、PD 协商、e-marked 线缆的高级行为不在本案例范围；不同连接器/不同板版的 CC 网络必须分别核对。
>
> **关联：** 设计卡 [PWR-12 USB-C 5V Sink](../design-cards/power/p12-usbc-sink.md)、[PWR-13 USB-C 5V Source](../design-cards/power/p13-usbc-source.md)、[IF-10 USB-C 数据](../design-cards/interfaces/i10-usbc-data.md)；范例 [x08 USB-C 受电端](../examples/x08-usbc.md)；检查项 [SC30、SC31、PL15](../schematic-details.md)，以及 [DM29](../domain-design-details.md)。

## 目录

- 现象
- 工况
- 原因假设
- 区分假设的检查
- 根因证据
- 修复
- 复验
- 适用边界

## 现象

C-to-C 充电器或主机不供电，A-to-C 线却正常；或设备能被识别但只拿到 500 mA；正反插一面正常、一面不正常；两个 CC 短接后某些线缆不工作；用带 e-marker 的线缆异常。典型表现：

- 插 C-to-C 时 VBUS 一直是 0 V；插 A-to-C 时有 5 V。
- 设备能枚举，但大电流负载时掉压/复位，因为 source 只广告了默认电流。
- 换一根线或翻一面就好，说明方向检测或 CC1/CC2 连接有问题。
- 发生阶段在插入/枚举时；影响范围与连接器、线缆、source 类型相关。

## 工况

- 设备：USB-C sink；5 V；无 PD；USB 2.0 数据；CC1/CC2 各接 `Rd` 到 GND。
- 连接器：Type-C 插座；CC1/CC2 是否独立；外壳/屏蔽是否误短 CC。
- 线缆：A-to-C、C-to-C、带 e-marker 的 C-to-C；仅充电线。
- Source：PC C 口、C 口充电器、A 口充电器 + A-to-C 线。
- 负载：枚举后拉到额定电流；温度与线缆压降。

## 原因假设

- **H1 CC 没有 `Rd`（漏贴/未接）。** 若成立：CC 对地电阻无穷大；source 检测不到 sink，VBUS 不启动；A-to-C 可能仍供电（A 口不依赖 CC）。
- **H2 `Rd` 值错（10 kΩ、56 kΩ、贴错料）。** 若成立：CC 电压落在错误窗口；source 可能判为未连接或错误电流档；测电阻可证实。
- **H3 CC1/CC2 短接成同一个节点。** 若成立：两个 CC 电压相同，source 无法判方向；某些 source/线缆组合失败；正反插表现不同。
- **H4 VBUS 检测/使能错。** 若成立：CC 正常、VBUS 有 5 V，但系统不启动；查 VBUS_DET/EN 分压与固件。
- **H5 线缆是 e-marked/仅充电/Type-A 适配器。** 若成立：换线改变现象；CC 行为随线缆不同；不是板端 `Rd` 单独能解释。
- **H6 PD 控制器或 D+/D− 电路占用 CC。** 若成立：CC 上有额外电路；不是简单 sink；需要按该控制器手册分析。

## 区分假设的检查

按“先安全、再无损、再侵入”的顺序：

**安全（不上电、不拆焊）**

1. 查原理图：CC1、CC2 是否各自独立；每个是否有 `Rd` 到 GND；阻值与容差；是否与其他网络短接；VBUS 路径与检测。可排除 H1–H4 的纸面错误。
2. 查 BOM：`Rd` 的料号、阻值、容差、是否 DNP；连接器 CC 脚是否与屏蔽/外壳误连。
3. 查连接器脚序与焊接面；确认 CC1/CC2 没有在封装内被短接。

**无损（上电测量，不改变硬件）**

4. 断电测 CC1、CC2 对 GND 电阻；应各自约 5.1 kΩ（按设计），不能是 0 Ω、无穷大或 10 kΩ。
5. 插入 source，测 CC1、CC2 对地电压；对照 sink 读取 source 能力的窗口：0.25–0.61 V（default）、0.70–1.16 V（1.5 A）、1.31–2.04 V（3 A）。
6. 测 VBUS 是否有 5 V；分别用 A-to-C、C-to-C、正反插、不同线缆。
7. 读 source 的电流广告/设备枚举信息；确认是“没检测到”还是“检测到但电流档错”。

**侵入（更换、断开、飞线）**

8. 更换 `Rd` 或补贴；断开 CC1/CC2 的误短；每次只改一处。
9. 用已知 DFP 源/USB-C 表测试；不要用未知来源的充电器做唯一判据。
10. 不改固件来“修复”CC 电平；简单 sink 的 CC 是硬件行为。

## 根因证据

- **原厂判据（B）：** ST AN5225 Rev 7（2023-06；本次核对第 1–11 页）：
  - §4：source 在 CC1/CC2 上呈现 `Rp` 上拉；sink 呈现 `Rd` 下拉；电子线缆在 VCONN 上呈现 `Ra` 到地；线缆中只有一根 CC 连通，因此 DFP 要同时监视 CC1、CC2 判方向。
  - Table 5：DFP 的 `Rp`：default 80 µA ±20% 或 56 kΩ ±20%（3.3 V 时 36 kΩ）；1.5 A 180 µA ±8% 或 22 kΩ ±5%（3.3 V 时 12 kΩ）；3.0 A 330 µA ±8% 或 10 kΩ ±5%（3.3 V 时 4.7 kΩ）。
  - Table 6：UFP 的 `Rd`：±20% 电阻到地 5.1 kΩ（不能检测功率，CC 最大 2.18 V）；±10% 电阻到地 5.1 kΩ（可检测功率，CC 最大 2.04 V）。
  - Table 7：sink 读取 source 能力的电压窗：`vRd-USB` 0.25–0.61 V（门限 0.66）；`vRd-1.5` 0.70–1.16 V（门限 1.23）；`vRd-3.0` 1.31–2.04 V。
  - **窗口版本差异：** PWR-12/IF-S12 引用的 USB Type-C 规范 Table 4-36 为 0.277–0.612 V / 0.746–1.164 V / 1.369–2.042 V，与 ST AN5225 Rev 7 的 Table 7 不完全相同。按产品声明/采用的规范版本选一套并记录，不要把两套窗口混用；门限器件（TUSB320 等）以自身手册为准。
- **器件判据（B）：** TI TUSB320 SLLSEN9F（2015-05，修订 2022-03；本次核对第 1–25 页）：
  - UFP/DRP 模式下 CC 下拉 `RCC_D = 4.6/5.1/5.6 kΩ`（min/typ/max）；dead-battery 模式 `4.1/5.1/6.1 kΩ`。
  - DFP 电流源 default 80 µA（64–96）、medium 180 µA（166–194）、high 330 µA（304–356）。
  - UFP 检测窗：default 0.25–0.61 V；1.5 A 0.70–1.16 V；3 A 1.31–2.04 V。
  - `VBUS_DET` 需外接 900 kΩ（855–920 kΩ）到 VBUS；`VBUS_THR` 2.95/3.30/3.80 V。
  - 器件只写 “USB Type-C specification 1.1”，不支持 e-marking；不能当 Type-C 2.x/PD 方案。
- **算例（C，按上述数值）：** 5.1 kΩ × 80 µA = 0.408 V → default 窗；5.1 kΩ × 330 µA = 1.683 V → 3 A 窗。若 `Rd=10 kΩ` 且 source 330 µA → 3.3 V，超出 2.04 V 上限，source 可能判为未连接/异常。若 CC 悬空 → 无电流，source 不启动 VBUS。若 CC1/CC2 短接 → 两个脚同电位，方向检测失效。
- **未核对（入口，不作为证据）：** USB-IF Type-C Cable and Connector Specification Release 2.5 只读到文档库元数据（PWR-S17），正文未打开；本案例不引用条款号、表号或规范数值，所有数值来自 PWR-S15/PWR-S16。
- **合理推断（C）：** 具体这块板是漏贴、错值还是短接，需要电阻与电压测量；本案例不填实测值。
- **仍待验证：** 线缆 e-marker、source 的具体实现、连接器内部是否短接 CC、VBUS 路径的压降。

## 修复

- **原理图（主修复）：** CC1、CC2 各自独立接 `Rd` 到 GND，不短接、不共用一只电阻；VBUS 检测/使能按器件手册。
- **BOM：** 5.1 kΩ，容差按是否需要检测功率选 ±10%（AN5225 Table 6 的两种）；不要用 10 kΩ/56 kΩ 代替；确认贴装、不是 DNP。
- **布局：** CC 走线短；ESD 器件不引入漏电；连接器 CC 脚不被外壳/屏蔽短接；VBUS 路径按电流能力。
- **固件：** 简单 sink 不需要固件；若用 TUSB320 类控制器，按手册配置角色与 `EN_N` 时序，不能靠固件改 CC 电阻。
- **装配变体：** 不同连接器/不同板版不能共用 CC BOM 行；DNP 的 `Rd` 必须在装配图上明确。
- **结构：** 连接器外壳与 CC 的隔离要核对；不要用金属外壳压到 CC 焊盘。

## 复验

- **条件：** 至少 3 种 source（A-to-C 充电器、C-to-C 充电器、PC C 口）、正反插、含 e-marked 线缆；测 CC1/CC2 电压与 VBUS；负载到额定电流；记录线缆型号。
- **通过标准：** 两种插向都能得到 VBUS；CC 电压落在对应电流窗；能拿到 source 广告的电流（不虚标）；无过热；数据枚举正常；不同线缆组合无失败。
- **实际结果：** 未执行。没有这块板的 CC 电压、VBUS 或线缆组合记录。

## 适用边界

- **适用：** 5 V、无 PD 的 Type-C sink；CC1/CC2 各自 `Rd` 的简单受电端。
- **需要重新分析：** source 侧 `Rp` 与电流广告；DRP/双角色；USB PD 协商（PWR-S15/S16 未覆盖 PDO/APDO）；e-marked 线缆与 VCONN；USB 3.x 高速数据。
- **不能证明：** 不能证明所有 C-to-C 失败都是 CC；VBUS 路径、连接器、线缆、source 兼容性都可能；不能把 5.1 kΩ 当所有 Type-C 角色；不能引用 USB-IF 规范条款号；不能把 3 A 广告能力等同于板端可长期输出 3 A。
