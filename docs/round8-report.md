# Round 8：执行效率、原理图可读性与真实纵向闭环

日期：2026-10-26。分支 `feat/execution-efficiency-round8`，基线 `origin/main`
（`9f237b8`）。验证对象：`dual-scope-instrument-01` 的隔离副本
`dual-scope-r8-isolated`（UUID `ac26e6ad34d24573ab2d82d383b96643`）。

> 状态口径：**已实现**（代码/文档）、**离线通过**（单元测试/离线工具）、
> **真实 EDA 通过**（写入+回读+保存重开）、**BLOCKED**、**NOT RUN**。
> 本文件只写实际发生的事；没有执行的项单列。

## 1. 本轮改了什么

### 新增工具（离线，纯 Python，无网络/无 EDA 写入）

| 文件 | 作用 | 关键边界 |
|---|---|---|
| `design-hardware/scripts/design_inventory.py` | 设计源 `parts[]` vs 每页 `sch list --include-pins`；缺失/多余/空页/未计划页 + 可选 native check 汇总 | 只比较位号集合；电气正确性需 `--check`，不替代 `sch check` |
| `design-hardware/scripts/channel_map_check.py` | 参考通道→实例通道的位号/网名映射逐引脚核对；支持设计源与 EDA list | 只证明映射后结构一致，不证明拓扑本身正确 |
| `design-hardware/scripts/library_precheck.py` | 批量器件身份/值/封装/LCSC/device UUID 覆盖与冲突 | 不查库存/价格/SMT，不证明 footprint/pin-pad |
| `design-hardware/scripts/eda_cache.py` | 版本化、fail-closed 的 EDA 读取缓存；键=project+document+action+params | 不用于写决策；保存/重开/任何 mutation 后必须换版本标签 |

### 新增/修改文档

- `design-hardware/references/eda-efficiency.md`：批量执行、检查点/断点、超时对账、
  缓存失效、分区/标题/说明、碰撞治理、阶段验收/停止条件、性能口径、多 Agent
  单写入者与角色计时、实测工具陷阱。
- `design-hardware/SKILL.md`：新增“批量写入/超时恢复/缓存/通道复用/多 Agent”路由。
- `design-hardware/references/eda-execution.md`：指向效率文档与新工具，不重复规则。

### 测试

新增 4 个测试文件、23 个测试：

```text
tests/test_design_inventory.py       4
tests/test_channel_map_check.py      5
tests/test_library_precheck.py       6
tests/test_eda_cache.py              8
```

已运行：
- 23 个新测试全部通过；
- `tests/test_skill.py` 11、`tests/test_offline_tools.py` 26、
  `tests/test_project_assets.py` 3 通过；
- `design-hardware/scripts/skill_selftest.py`：5 PASS / 0 FAIL / 0 NOT RUN。

未运行全仓所有测试（NOT RUN）；未重新安装到用户 Skill 目录（不升级用户执行器）。

## 2. 真实 EDA 验证结果

### 2.1 页面盘点（工作包 A）

- 设计源 337 件 / 1115 条 pin-net；隔离副本实际 213 件；缺 126、多 2。
- P11–P16/P21 空白；P6 16/17、P10 24/28、P17 1 缺 1 多；P7/P8/P9 件数齐但
  23/8/30 floating。
- 明细见 `docs/evidence/round8/design-inventory-baseline.json` 与
  `docs/evidence/round8/README.md`。

### 2.2 拓扑修正（工作包 B/E）

- P1 删除旧拓扑遗留 K2（1× 直通），K3:2 改 `CH1_10X_TAP`；P3 K203:2 改
  `CH2_10X_TAP`。P1 其余 50 pin、P3 其余 50 pin 零变化；网
  `CH1_ATT_OUT`/`CH2_ATT_OUT`/`RELAY2` 消失。
- EDA P1↔P3 通道映射：16 件、51 pin、0 缺失/多余/网名不一致。
- 设计源 P1↔P3、P2↔P4 各 51 pin/0 差异。

### 2.3 P1 可读性（工作包 C）

- 三块功能区：输入与保护 / 耦合与量程 / 高压缓冲；每块有单行标题 + 用途说明。
- `sch frame apply`：3 框 verified；用途说明通过受控 SDK text create（typed 目录
  没有 `schematic.text.create`，这是本轮实测缺口）。
- `sch check`：0 floating；缺分区/缺图签清零；残余 1 marker-overlap（3.5×2.5 raw）、
  1 位号擦边（0.5 raw）、3 条 peripheral-not-direct 警告。
- `save → doc reload → 回读`：16 件、51 pin，0 差异；6 文本、3 框 unchanged。
- 前后图：`docs/evidence/round8/before-P1.png`、`after-P1-v3.png`。

### 2.4 PCB 通道（工作包 B/E）

- 先激活 PCB1，再 `pcb import-changes`：
  `imported:true / partial:false / verified:true / componentsAfter:212`。
- 保存重开仍 212 件；板框 6299×4331 mil（160×110 mm）、R118、4 native arcs、
  locked；保存重开保持。
- CH1 16 件移入板内（初步布局种子），保存重开 16/16 仍在板内。
- 未做：全板布局/布线/铺铜/DRC/Gerber/CPL。

## 3. 执行效率（工作包 D）

### 3.1 基线（上一轮）

192.48 min 墙钟 / 9593 调用 / 259 失败 / 2847 上下文探测；
`components.list` 3892 次 / 3435.2 s；`place` 585 次 / 57 失败；
`connect_pin` 1159 次 / 23 失败；`save` 118 次 / 454.5 s。
明细：`docs/evidence/round8/audit-cost-20261026.json`。

### 3.2 隔离会话

约 51 min / 3047 调用 / 55 失败 / 759 次 `components.list` / 1231 个上下文探测 /
工具并集 16.9 min。任务范围不同，**不是受控 A/B**。

### 3.3 受控微基准（只读批量）

| 方式 | 墙钟 | 审计条数 | 上下文探测 | components.list |
|---|---:|---:|---:|---:|
| 单进程 `sch apply` 5 步 | 5.75 s | 12 | 4 | 7 |
| 5 个独立 `sch list` | 8.12 s | 30 | 15 | 15 |

结论：批量读约 −29% 墙钟、−73% 上下文探测。**不宣称总耗时 −50%**。

### 3.4 失败与返工（如实记录）

- 14 组 `group-move` 批量后连接器降级（`DISPATCH_FAILED/context deadline`），
  出现钳位、假失败/假成功；按“轻读→doc reload→回读”恢复，耗时约 10 min。
- 21 页探测被另一会话 `document.open` 的 `ACTION_BUSY` 打断，全部失败；同一时刻
  `sch list --all-pages` 成功。这是并发集成返工的直接证据。
- `frame apply` 多行标题被拒、图签 Name/Description 渲染到图框外，各修正一次。
- 未发现无 mutation 的重复 save。

## 4. 架构独立复核（工作包 B）

5 个只读审查员被要求**反证**，结果 4/5 已返回：

| ID | 结论 | 处理 |
|---|---|---|
| PWR-01 LM2663 -24V | CONFIRMED | 列入阻断项；需 ≥30V 反相方案 |
| DRV-01 AD8138 无反馈 | CONFIRMED | 列入阻断项；需补 RF/RG |
| FPGA-POWER-01 | 原 claim REFUTED，但发现真正电源轨接反 | 64/67/78 应 +3V3，pin12 应 +1V8 |
| ADC-01 S1/S2 standby | REFUTED | S1=+3V3/S2=GND 为 Normal Operation，不改图 |

高风险组（5/5，逐项）：H1 3.3V buck 3.095V < 屏 VDDIO 3.135V **CONFIRMED**；
H2 VOCM 0.9V < AD8138 最小 1.0V **CONFIRMED**（ADC CM 0.99V 仍低 10mV）；
H3 滤波器首个 -3dB 约 8.9MHz、25MHz 相对 -21.5dB **CONFIRMED**；
H4 端接约 53.6% 满度 **CONFIRMED**；H5 PSRAM 100MHz 是 memory clock、
用户时钟 50MHz，未越 166MHz **REFUTED**（400MB/s 为峰值，持续余量乐观）。
这说明“先派独立审查、再落结论”确实能拦住看似合理的错误结论；Skill 的
`eda-efficiency.md` 已把这条写成多 Agent 纪律。

原始结论：`docs/evidence/round8/architecture-verification-raw.txt`。

## 5. 已知限制与未完成

- **BLOCKED/NOT RUN**：P1 残余 1 marker-overlap（共享导线树，destagger 拒绝）、
  1 位号擦边、K1/K3 网名密度；全仓测试；原理图原生批量导入专项对照；
  阻断电气项修复；P6–P10 补线、P11–P16/P21 放置；PCB 全板布局/布线/DRC/Gerber；
  实物性能。
- `design_inventory` 的 “complete” 只表示位号集合一致；P7/P8/P9 是反例。
- `channel_map_check` 只证明映射后结构一致，不证明拓扑正确。
- `library_precheck` 不查库存/价格/SMT，不证明 symbol/footprint/pin-pad。
- `eda_cache` 未接入 `eda_exec.py` 读取路由；本轮只用 CLI 演示。
- PCB 图是离线辅助渲染（`pcb dump` + `pcb layout render`），不是官方画布截图。

## 6. 证据索引

见 `docs/evidence/round8/README.md`。原始项目报告与交接在
`C:\Users\jlc\work\dual-scope-20261026\docs\round8-report.md`、
`docs/handoff-current.md`（本轮更新）。

## 7. PR

待创建：`feat/execution-efficiency-round8` → `main`。不合并、不打标签、不发布
Release、不升级用户执行器。
