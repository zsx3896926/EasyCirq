# PCB round 9 报告（2026-10-26）

## 1. 一句话结论

两块真实双层 PCB 已在嘉立创EDA专业版完成布局、布线、GND 铺铜、丝印、原生 DRC 0、SCH-PCB 逐脚对账、保存重开一致和 BOM 导出；第三项“局部改板”在其中一块的独立副本上完成“加去耦”一项。制造 Gerber/CPL 被当前 typed CLI 能力阻断，未宣称可制造。

## 2. 真实工程与入口

| 板 | 工程 / PCB | 真实结果 | 入口 |
|---|---|---|---|
| A 5V 光控 LED（THT/混装，90×60mm，4×M3） | `photo-led-pcb-20261026` / `PCB1` `99b8366b0bdc971f` | 19 件/47 焊盘；DRC 0；14/14 关键 net-path；save/reload diff match；丝印 0 压焊盘/越框/倒置 | `easycirq/cases/photo-led-pcb-2026-10-26/` |
| B MCU+I²C（ESP32-S3-WROOM-1 + SHT40，SMT，65.79×45mm，2×M2.5） | `mcu-i2c-s3-20261026` / `PCB2` `40b81985cfb4a5ed` | 23 件/15 网/104 脚；DRC 0；15/15 关键 net-path；23/23、104/104 SCH-PCB 0 mismatch；save/reload match | `easycirq/cases/mcu-i2c-s3-2026-10-26/` |
| B 局部改板副本 | `mcu-i2c-s3-edit-20261026` / 同 PCB UUID | 加 C99 100nF；只重布 +3V3/GND；DRC 0；scoped diff unrelated 0；save/reload match | `mcu-i2c-s3-2026-10-26/evidence/edit-*` |

图：

- A 顶/底：`cases/photo-led-pcb-2026-10-26/evidence/pcb-final-top.png`、`pcb-final-bottom.png`
- B 顶/底：`cases/mcu-i2c-s3-2026-10-26/evidence/pcb-final-top.png`、`pcb-final-bottom.png`

## 3. 工作包状态

| WP | 状态 | 证据/边界 |
|---|---|---|
| WP01 实测几何 | 已实现 + 自动测试 + 真机使用 | `normalize_board`/`transform_component`；板 A/B dump 实际用于布局与检查。无 IPC courtyard，明确用渲染 bbox 替代；发现 dump 丝印 BBox 与 `pcb check` 实时字框不一致，已记录。 |
| WP02 约束/冲突 | 已实现 + 自动测试 + 真机使用 | 9 类约束、稳定 id/source/unit/hard-soft、keepout/channel/fixed/near-pin 冲突；板 A `placement-check-final` pass，板 B near-pin 全 pass。 |
| WP03 多候选 | 已实现 + 自动测试 + 板 A 使用 | signal-chain/density/mechanical；硬失败先淘汰；板 A 选 signal-chain；B 用实测 placement + typed apply（未强行套候选）。 |
| WP04 局部模板 | 已实现 + 自动测试 + 板 A 真机使用 4 类 | 9 个模板（ic-decap、connector-protection、opamp-feedback、low-side-driver、ldo-caps、i2c-sensor、mcu-debug、crystal、module-decap）；条件不符/网络不符拒绝。板 B 的 LDO/I²C 使用约束而非模板求解。 |
| WP05 逃线预判 | 已实现 + 自动测试 + 真实路由 | 代理 corridor；板 A route-short dry-run/官方路由；板 B 发现 sensor no-wires 阻塞 I²C 后改为 no-pours 并重布。 |
| WP06 布局—布线联合 | 已实现（预算化 joint loop）+ 真实迭代 | 板 A 布局 2 轮、VREF 先布；板 B 首轮 12/14、+3V3/GND 重布、J1 边距/板框调整、传感器 keepout 修正，DRC 45→0。 |
| WP07 路由器 | 官方路由器真机；route-short 只 dry-run 对比 | 板 A VREF 同条件对比：route-short 14 段/3066.9mil vs 官方 12 段/2946mil/0 via；板 B 官方路由器。外部路由器未引入。 |
| WP08 电源/地/关键连接 | 已实现 + 真机 | IPC-2221 筛查、pour 检查、15/15 板 B net-path、14/14 板 A；net-path 不含铺铜，GND 由 DRC 0 + 铺铜回读补充。 |
| WP09 铺铜/过孔 | 真机部分 | 双面 GND pour + rebuild + DRC；天线 keepout；板 B 局部天线口径 WARN 未清；孤岛/细颈未逐项工具化。 |
| WP10 丝印 | 已实现工具链 + 真机 | `silk-align`/`silk-set`；两板 over-pad/off-board/flipped 0；实际看图。 |
| WP11 局部改板 | 一项完成（加去耦）；两项 NOT RUN | 板 B 副本 C99；换封装、移动接口未做。 |
| WP12 模块复用 | 离线实现+测试；真机跨工程 NOT RUN | `pcb-extract-module`/`pcb-reuse-plan`；铜复用 `not_supported`。 |
| WP13 事务/漂移/恢复 | 适配器 + 测试 + 板 B 真机 | stale plan/primitiveId 拒绝、逐件 verified、部分失败停止、scoped diff；板 B apply 23/23 verified；未构造 EDA 故障注入。 |
| WP14 四板矩阵 | A/B 完成；C/D NOT RUN | 没有为凑数复制板。 |
| WP15 受控基线 | 部分 | 记录两板首个候选、返工轮次、失败机制、路由对比；没有同条件原流程/新流程完整百分数。 |
| WP16 制造/交付 | BOM + 图 + 可编辑工程；Gerber/CPL BLOCKED | 两板 BOM 身份完整性 pass；未下单/未做板厂 DFM。 |

## 4. 关键真实失败与修复

1. 板 A 初始 C1/D1、R1/R5 重叠 + R4 距离：离线先修，0 发现后写入。
2. 板 A J1 开口朝内、D1 挡插拔走廊：rotation 90→270，清零并锁定。
3. 板 A +5V/VIN 本地铺铜边界存在但材料化铜为 0：删除空铺铜，10 mil 电源轨 + 计算；DRC 0。
4. 板 B J1 shell pad 距板边 2.1 mil：板框 2559→2590 mil；J1 保持 2320/180，连接器开口/插拔 0。
5. 板 B sensor no-wires region 阻塞 I²C/3V3 入焊盘：改 no-pours，重布。
6. 板 B 手工 +3V3/GND 短桩 20 条 clearance：rip-up 受影响网络，官方路由器重布，DRC 0。
7. 板 B 天线 keepout 官方命令扩成整条底边：改用局部区域；CLI 仍报口径 WARN，保留。
8. SHT40 datasheet 与原库 EP 冲突：EP NC + 传感器下方 no-pours；未把 EP 接 GND。
9. AMS1117 陶瓷输出电容：保留但标 `stability NOT VERIFIED`。

## 5. 明确未完成/限制

- Gerber/drill/CPL：typed CLI 无导出，制造包 BLOCKED；BOM/`.epro2` 已导出。
- 板 B：天线 keepout CLI 口径、+3V3 未铺铜、GND 10 mil、5 条 decap 距离、4 条 parallel coupling、1 条 acute、fiducial INFO；未清零。
- SHT40 EP 焊盘仍存在；LDO 稳定性、USB SI、热/EMC/实物/固件未验证。
- 换封装/移动接口两种局部改板、跨工程铜复用、四板矩阵 C/D、受控 A/B 效率对照：NOT RUN。
- 未合入 PR、未发 Release、未采购/下单。
